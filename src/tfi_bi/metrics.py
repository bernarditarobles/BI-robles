"""Paso 3-4: modelo analítico. Reglas de calificación, fecha de corte y KPIs.

Todas las funciones reciben la `fecha de corte` (inclusive) y devuelven
DataFrames listos para graficar. Nada acá depende de Streamlit.
"""
from __future__ import annotations

import re

import numpy as np
import pandas as pd

from .config import SESSION_GAP_MIN, norm, schema_de
from .loaders import limpiar_texto

CATEGORIAS_ACCION = [  # (palabra clave en la acción, categoría)
    ("evaluaci", "Evaluaciones"), ("realizaci", "Evaluaciones"), ("encuesta", "Evaluaciones"),
    ("calific", "Calificaciones"), ("notas", "Calificaciones"), ("avances", "Calificaciones"),
    ("tema", "Foros"), ("intervencion", "Foros"), ("respuesta", "Foros"),
    ("mensaje", "Mensajería"), ("recibidos", "Mensajería"), ("enviados", "Mensajería"),
    ("papelera", "Mensajería"),
    ("texto", "Lectura de material"), ("archivo", "Lectura de material"), ("tópico", "Lectura de material"),
    ("descargar", "Lectura de material"), ("noticia", "Lectura de material"), ("unidad", "Lectura de material"),
    ("acceder", "Navegación"), ("categor", "Navegación"), ("listado", "Navegación"),
    ("visualizar", "Calendario y otros"), ("perfil", "Calendario y otros"),
]


def categoria_accion(accion: str) -> str:
    a = str(accion).lower()
    for kw, cat in CATEGORIAS_ACCION:
        if kw in a:
            return cat
    return "Otros"


# ------------------------------------------------------------------ preparación
def preparar(d: dict) -> dict:
    """Prepara tablas base (una vez): solo alumnos, categoría de acción, fechas de evaluación."""
    traz = d["trazabilidad"].copy()
    traz = traz[traz["id"].str.startswith("ALU_") & traz["perfil"].eq("Alumnos")].copy()
    traz["categoria"] = traz["accion"].map(categoria_accion)

    # Fecha de realización de cada evaluación (las notas no traen fecha, pero la
    # trazabilidad registra "Realización de la evaluación '<nombre>' ...").
    ev = d["trazabilidad"]
    ev = ev[ev["accion"].eq("Realizar evaluación")].copy()
    ev["instrumento"] = ev["descripcion"].str.extract(r"evaluaci[oó]n '(.+?)' de la unidad")[0].map(
        lambda s: limpiar_texto(s) if isinstance(s, str) else s)
    fechas = (ev.dropna(subset=["instrumento"]).groupby(["materia", "instrumento", "id"])["fecha"]
                .min().rename("fecha_eval").reset_index())

    cal = d["calificaciones"].copy()
    cal = cal[cal["id"].str.startswith("ALU_")]
    cal = cal.merge(fechas, on=["materia", "instrumento", "id"], how="left")
    med = cal.groupby(["materia", "instrumento"])["fecha_eval"].transform("median")
    cal["fecha_eval_estimada"] = cal["fecha_eval"].isna() & med.notna()
    cal["fecha_eval"] = cal["fecha_eval"].fillna(med)

    part = d["participacion"].copy()
    nombres = (part[part["perfil"].eq("Alumnos")]
               .assign(nombre_completo=lambda x: x["apellido"].astype(str) + ", " + x["nombre"].astype(str))
               .drop_duplicates("id")[["id", "nombre_completo"]])
    return dict(matriculados=d["matriculados"], participacion=part, trazabilidad=traz,
                calificaciones=cal, nombres=nombres, log_limpieza=d["log_limpieza"])


def fecha_maxima(p: dict) -> pd.Timestamp:
    return p["trazabilidad"]["fecha"].max().normalize()


def fecha_minima(p: dict) -> pd.Timestamp:
    return p["trazabilidad"]["fecha"].min().normalize()


def _corte(fecha) -> pd.Timestamp:
    return pd.Timestamp(fecha).normalize() + pd.Timedelta(days=1) - pd.Timedelta(seconds=1)


# --------------------------------------------------------------------- sesiones
def sesiones(traz: pd.DataFrame, gap_min: int = SESSION_GAP_MIN) -> pd.DataFrame:
    """Agrupa eventos en sesiones: cambia de sesión tras `gap_min` minutos de silencio."""
    t = traz.sort_values(["materia", "id", "fecha"])
    gap = t.groupby(["materia", "id"])["fecha"].diff()
    t = t.assign(nueva=(gap.isna() | (gap > pd.Timedelta(minutes=gap_min))).astype(int))
    t["sesion"] = t.groupby(["materia", "id"])["nueva"].cumsum()
    s = (t.groupby(["materia", "id", "sesion"])
           .agg(inicio=("fecha", "min"), fin=("fecha", "max"), eventos=("fecha", "size")).reset_index())
    s["duracion_min"] = (s["fin"] - s["inicio"]).dt.total_seconds() / 60
    return s


# ------------------------------------------------------------------ calificaciones
def calificaciones_resumen(p: dict, fecha_corte, ausentes_cero: bool = False,
                           algebra_base: str = "normalizado") -> tuple[pd.DataFrame, pd.DataFrame]:
    """Devuelve (resumen por alumno/materia, notas consideradas a la fecha de corte).

    * Solo cuentan las notas de evaluaciones realizadas hasta la fecha de corte.
    * Modo 'promedio' (Probab., Algoritmos): promedio de notas normalizadas a 100;
      un recuperatorio REEMPLAZA a su instrumento original (se toma la mejor nota).
    * Modo 'acumulativo' (Álgebra): puntos sumados. Como no están todos los
      instrumentos, se normaliza: puntos / máximo de lo rendido * 100.
      `algebra_base='puntos'` compara los puntos crudos contra los umbrales (60/85 de 120).
    * `ausentes_cero=True`: lo no rendido cuenta como 0 en el denominador.
    """
    corte = _corte(fecha_corte)
    cal = p["calificaciones"]
    cal = cal[cal["fecha_eval"].isna() | (cal["fecha_eval"] <= corte)].copy()
    filas = []
    for materia, g in cal.groupby("materia"):
        sc = schema_de(materia)
        disponibles = g.groupby("instrumento_base").agg(max=("max", "max")).reset_index()
        if sc["modo"] == "acumulativo":
            tot_disp = g.groupby("instrumento")["max"].max().sum()
            for uid, h in g.groupby("id"):
                pts, mx = h["nota"].sum(), h["max"].sum()
                den = tot_disp if ausentes_cero else mx
                pct = pts / den * 100 if den else np.nan
                valor = pts if algebra_base == "puntos" else pct
                filas.append((materia, uid, pts, mx, pct, valor, len(h), g["instrumento"].nunique()))
        else:
            n_disp = len(disponibles)
            for uid, h in g.groupby("id"):
                por_base = h.groupby("instrumento_base")["pct"].max()  # recuperatorio reemplaza
                den = n_disp if ausentes_cero else len(por_base)
                pct = por_base.sum() / den if den else np.nan
                filas.append((materia, uid, h["nota"].sum(), h["max"].sum(), pct, pct, len(por_base), n_disp))
    res = pd.DataFrame(filas, columns=["materia", "id", "puntos", "puntos_max_rendidos", "pct_final",
                                       "valor_condicion", "instrumentos_rendidos", "instrumentos_disponibles"])

    def condicion(r):
        sc = schema_de(r["materia"])
        v = r["valor_condicion"]
        if pd.isna(v):
            return "Sin notas"
        return "Promociona" if v >= sc["promo"] else "Regular" if v >= sc["regular"] else "Libre"

    if len(res):
        res["condicion"] = res.apply(condicion, axis=1)
    else:
        res["condicion"] = []
    return res, cal


# ----------------------------------------------------------------- participación
def participacion_resumen(p: dict, fecha_corte, dias_inactividad: int = 14) -> pd.DataFrame:
    corte = _corte(fecha_corte)
    t = p["trazabilidad"]
    t = t[t["fecha"] <= corte]
    if t.empty:
        return pd.DataFrame()
    s = sesiones(t)
    ag = (t.groupby(["materia", "id"])
            .agg(eventos=("fecha", "size"), primera=("fecha", "min"), ultima=("fecha", "max"),
                 dias_activos=("fecha", lambda x: x.dt.normalize().nunique())).reset_index())
    ss = (s.groupby(["materia", "id"])
            .agg(sesiones=("sesion", "size"), tiempo_min=("duracion_min", "sum")).reset_index())
    out = ag.merge(ss, on=["materia", "id"], how="left")
    cat = (t.pivot_table(index=["materia", "id"], columns="categoria", values="fecha",
                         aggfunc="size", fill_value=0).add_prefix("ev_").reset_index())
    out = out.merge(cat, on=["materia", "id"], how="left")
    out["dias_desde_ultima"] = (corte.normalize() - out["ultima"].dt.normalize()).dt.days
    out["estado_actividad"] = np.where(out["dias_desde_ultima"] <= dias_inactividad, "Activo", "Inactivo")
    return out


# ------------------------------------------------------------ tabla integrada
def tabla_estudiantes(p: dict, fecha_corte, dias_inactividad: int = 14,
                      ausentes_cero: bool = False, algebra_base: str = "normalizado") -> pd.DataFrame:
    """Una fila por (materia, alumno): matrícula + participación + notas + clasificación."""
    corte = _corte(fecha_corte)
    m = p["matriculados"]
    # Universo: todo alumno que aparezca en CUALQUIER fuente (no solo los matriculados)
    ids = pd.concat([
        m[["materia", "id"]],
        p["participacion"].query("perfil == 'Alumnos'")[["materia", "id"]],
        p["trazabilidad"][["materia", "id"]],
        p["calificaciones"][["materia", "id"]],
    ]).drop_duplicates()
    ids = ids[ids["id"].str.startswith("ALU_")]
    df = ids.merge(m[["materia", "id", "estado_insc", "instancia", "comision", "matriculado"]],
                   on=["materia", "id"], how="left")
    df["estado_insc"] = df["estado_insc"].fillna("No inscripto")
    df["matriculado"] = df["matriculado"].fillna(False).astype(bool)

    part = participacion_resumen(p, fecha_corte, dias_inactividad)
    df = df.merge(part, on=["materia", "id"], how="left")
    rep = p["participacion"].query("perfil == 'Alumnos'")[["materia", "id", "avance_pct", "fecha_alta"]]
    df = df.merge(rep, on=["materia", "id"], how="left")
    notas, _ = calificaciones_resumen(p, fecha_corte, ausentes_cero, algebra_base)
    df = df.merge(notas, on=["materia", "id"], how="left")
    df = df.merge(p["nombres"], on="id", how="left")
    df["nombre_completo"] = df["nombre_completo"].fillna(df["id"])

    for c in ["eventos", "sesiones", "tiempo_min", "dias_activos"]:
        df[c] = df[c].fillna(0)
    df["condicion"] = df["condicion"].fillna("Sin notas")
    df["estado_actividad"] = df["estado_actividad"].fillna("Sin actividad")
    df["con_actividad"] = df["eventos"] > 0

    def cat_matricula(r):
        if r["matriculado"]:
            return {"Activo": "Matriculado activo", "Inactivo": "Matriculado inactivo"}.get(
                r["estado_actividad"], "Matriculado sin actividad")
        if r["estado_insc"] == "Baja":
            return "Baja con actividad" if r["con_actividad"] else "Baja sin actividad"
        return "No matriculado con actividad" if r["con_actividad"] else "No matriculado sin actividad"

    df["situacion_matricula"] = df.apply(cat_matricula, axis=1)
    df["alerta_no_inscripto"] = (~df["matriculado"]) & (df["con_actividad"] | (df["condicion"] != "Sin notas"))

    # Grupos de riesgo: nota vs participación
    # Participación baja = tiempo en el 25% inferior de su materia o sin actividad reciente.
    q1 = df[df["con_actividad"]].groupby("materia")["tiempo_min"].quantile(0.25).rename("q1_tiempo")
    df = df.merge(q1, on="materia", how="left")
    baja = (df["tiempo_min"] <= df["q1_tiempo"]) | (df["estado_actividad"] != "Activo")
    libre = df["condicion"].eq("Libre")
    tiene = df["condicion"].ne("Sin notas")
    df["grupo_riesgo"] = np.select(
        [~tiene, libre & baja, libre & ~baja, ~libre & baja],
        ["Sin notas", "Riesgo alto (baja participación y nota baja)",
         "Participa pero no rinde", "Rinde con baja participación"],
        default="En camino (participa y rinde)")
    return df.drop(columns=["q1_tiempo"])


# ----------------------------------------------------------------- KPIs / cruces
def kpis_por_materia(est: pd.DataFrame, solo_matriculados: bool = True) -> pd.DataFrame:
    """KPIs de participación y notas. Por defecto solo cuentan los matriculados oficiales;
    la alerta de no inscriptos siempre se calcula sobre todos los alumnos del aula."""
    rows = []
    for materia, g in est.groupby("materia"):
        mat = g[g["matriculado"]]
        base = mat if solo_matriculados else g
        con_notas = base[base["condicion"] != "Sin notas"]
        rows.append(dict(
            materia=materia,
            matriculados=len(mat),
            alumnos_en_aula=int(g["con_actividad"].sum()),
            activos=int((mat["estado_actividad"] == "Activo").sum()),
            inactivos=int((mat["estado_actividad"] != "Activo").sum()),
            pct_activos=(mat["estado_actividad"] == "Activo").mean() * 100 if len(mat) else np.nan,
            sesiones_prom=mat.loc[mat["con_actividad"], "sesiones"].mean(),
            horas_prom=mat.loc[mat["con_actividad"], "tiempo_min"].mean() / 60,
            avance_prom=mat["avance_pct"].mean(),
            nota_prom=con_notas["pct_final"].mean(),
            pct_promociona=(con_notas["condicion"] == "Promociona").mean() * 100 if len(con_notas) else np.nan,
            pct_regular=(con_notas["condicion"] == "Regular").mean() * 100 if len(con_notas) else np.nan,
            pct_libre=(con_notas["condicion"] == "Libre").mean() * 100 if len(con_notas) else np.nan,
            no_inscriptos_activos=int(g["alerta_no_inscripto"].sum()),
        ))
    return pd.DataFrame(rows)


def correlaciones(est: pd.DataFrame) -> pd.DataFrame:
    """Correlación participación vs nota final (se espera `est` ya filtrado al ámbito elegido)."""
    from scipy import stats
    rows = []
    for materia, g in est[est["condicion"] != "Sin notas"].groupby("materia"):
        for var, lab in [("tiempo_min", "Tiempo de conexión"), ("sesiones", "Sesiones"),
                         ("eventos", "Interacciones"), ("avance_pct", "Avance (%)")]:
            h = g[[var, "pct_final"]].dropna()
            if len(h) > 5 and h[var].nunique() > 1:
                r, pv = stats.pearsonr(h[var], h["pct_final"])
                rho, _ = stats.spearmanr(h[var], h["pct_final"])
                rows.append(dict(materia=materia, variable=lab, n=len(h), pearson=r, spearman=rho, p_valor=pv))
    return pd.DataFrame(rows)


def heatmap_semanal(p: dict, fecha_corte, materia: str | None = None) -> pd.DataFrame:
    t = p["trazabilidad"]
    t = t[t["fecha"] <= _corte(fecha_corte)]
    if materia:
        t = t[t["materia"] == materia]
    h = t.assign(dia=t["fecha"].dt.dayofweek, hora=t["fecha"].dt.hour)
    return h.pivot_table(index="dia", columns="hora", values="id", aggfunc="size", fill_value=0) \
            .reindex(index=range(7), columns=range(24), fill_value=0)


def serie_diaria(p: dict, fecha_corte, materia: str | None = None) -> pd.DataFrame:
    t = p["trazabilidad"]
    t = t[t["fecha"] <= _corte(fecha_corte)]
    if materia:
        t = t[t["materia"] == materia]
    return (t.assign(dia=t["fecha"].dt.normalize())
              .groupby(["materia", "dia"]).agg(eventos=("id", "size"), usuarios=("id", "nunique")).reset_index())
