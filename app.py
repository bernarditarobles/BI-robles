"""Dashboard TFI - Herramienta Integral de Análisis y Seguimiento Académico LMS.

Ejecutar:  streamlit run app.py
"""
from __future__ import annotations

import hashlib
import io
import sys
import tempfile
import zipfile
from pathlib import Path

import numpy as np
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

sys.path.insert(0, str(Path(__file__).resolve().parent / "src"))
from tfi_bi import metrics as M  # noqa: E402
from tfi_bi import sql_kpis as S  # noqa: E402
from tfi_bi.config import COLORES_CONDICION, CURADO_DIR, DATA_DIR, norm, schema_de  # noqa: E402
from tfi_bi.loaders import cargar_datos, firma_datos  # noqa: E402

# Reglas de cálculo fijas (criterio de clase, explicadas en el informe):
# las evaluaciones no rendidas no cuentan y Álgebra se compara en % normalizado (puntos / puntos posibles).
ausentes_cero = False
base_algebra = "normalizado"

st.set_page_config(page_title="TFI · Seguimiento académico LMS", page_icon="📊", layout="wide")

SEMAFORO = {"Promociona": "🟢 Promociona", "Regular": "🟡 Regular", "Libre": "🔴 Libre", "Sin notas": "⚪ Sin notas"}
ORDEN_COND = ["Promociona", "Regular", "Libre", "Sin notas"]
DIAS = ["Lun", "Mar", "Mié", "Jue", "Vie", "Sáb", "Dom"]
COL_SIT = {
    "Matriculado activo": "#2e9e5b", "Matriculado inactivo": "#f2b01e", "Matriculado sin actividad": "#d64545",
    "No matriculado con actividad": "#7b3fbf", "Baja con actividad": "#e07b39",
    "No matriculado sin actividad": "#c9d1d9", "Baja sin actividad": "#9aa5b1",
}
NOMBRES = {
    "nombre_completo": "Alumno", "id": "ID", "materia": "Asignatura", "sesiones": "Sesiones", "horas": "Horas",
    "dias_activos": "Días activos", "ultima": "Última actividad", "estado_actividad": "Actividad",
    "pct_final": "Nota (0-100)", "condicion": "Condición", "dias_desde_ultima": "Días sin entrar",
    "grupo_riesgo": "Grupo", "estado_insc": "Inscripción", "eventos": "Interacciones",
    "situacion_matricula": "Situación",
}


def legible(df: pd.DataFrame) -> pd.DataFrame:
    """Tabla para mostrar: tiempo en horas, nota y fechas redondeadas, nombres de columna en castellano."""
    df = df.copy()
    if "tiempo_min" in df:
        df.insert(df.columns.get_loc("tiempo_min"), "horas", (df.pop("tiempo_min") / 60).round(1))
    if "pct_final" in df:
        df["pct_final"] = df["pct_final"].round(1)
    if "ultima" in df:
        df["ultima"] = pd.to_datetime(df["ultima"]).dt.strftime("%d/%m/%Y %H:%M")
    return df.rename(columns=NOMBRES)


TABLAS = ["matriculados", "participacion", "trazabilidad", "calificaciones", "log_limpieza"]


# ------------------------------------------------------------------ carga (cacheada)
# Regla de la Clase 10: @st.cache_data para DataFrames y consultas; rutas relativas con Path(__file__).parent.
BASE = Path(__file__).resolve().parent


@st.cache_data(show_spinner="Cargando datos del LMS…")
def cargar(firma: str):
    """Capa curada (Parquet) si está al día con los Excel de data/; si no, procesa los Excel.
    `firma` es la huella de data/: si el profe suma un archivo, cambia y se reprocesa solo."""
    archivo_firma = CURADO_DIR / "firma_datos.txt"
    al_dia = archivo_firma.exists() and archivo_firma.read_text().strip() == firma
    if al_dia and all((CURADO_DIR / f"{t}.parquet").exists() for t in TABLAS):
        d = {t: pd.read_parquet(CURADO_DIR / f"{t}.parquet") for t in TABLAS}
    else:
        d = cargar_datos(DATA_DIR, verbose=False)
    return M.preparar(d)


@st.cache_data(show_spinner="Procesando el archivo subido…")
def cargar_zip(contenido: bytes):
    """Patrón híbrido de la Clase 11: el usuario sube un .zip con la misma estructura que data/
    (Matriculados/ + una carpeta por asignatura) y se analiza solo en su sesión."""
    with zipfile.ZipFile(io.BytesIO(contenido)) as z:
        if sum(i.file_size for i in z.infolist()) > 300 * 1024 * 1024:
            raise ValueError("El zip descomprimido supera 300 MB")
        with tempfile.TemporaryDirectory() as tmp:
            z.extractall(tmp)
            mat = [x for x in Path(tmp).rglob("*") if x.is_dir() and "__MACOSX" not in x.parts
                   and norm(x.name) == "matriculados"]
            if not mat:
                raise ValueError("No encontré la carpeta 'Matriculados' dentro del zip")
            return M.preparar(cargar_datos(mat[0].parent, verbose=False))


@st.cache_data(show_spinner="Calculando métricas…")
def tabla(_p, origen, corte, dias_inact, ausentes_cero, base_algebra):
    return M.tabla_estudiantes(_p, corte, dias_inact, ausentes_cero, base_algebra)


@st.cache_data
def heatmap(_p, origen, corte, materia):
    return M.heatmap_semanal(_p, corte, materia)


@st.cache_data
def serie(_p, origen, corte, materia):
    return M.serie_diaria(_p, corte, materia)


with st.sidebar:
    with st.expander("📦 Datos", expanded=False):
        subido = st.file_uploader("Actualizar datos (.zip con la carpeta de datos)", type=["zip"],
                                  help="Misma estructura que data/: Matriculados/ y una carpeta por asignatura. "
                                       "Se analiza solo en tu sesión; no modifica el repositorio.")
origen = "repo"
p = None
if subido is not None:
    try:
        p = cargar_zip(subido.getvalue())
        origen = "zip:" + hashlib.md5(subido.getvalue()).hexdigest()
        st.sidebar.success("Analizando el archivo subido")
    except Exception as e:  # noqa: BLE001
        st.sidebar.error(f"No pude procesar el zip: {e}")
if p is None:
    p = cargar(firma_datos(DATA_DIR))
f_min, f_max = M.fecha_minima(p).date(), M.fecha_maxima(p).date()
materias_all = sorted(p["matriculados"]["materia"].unique())

# ----------------------------------------------------------------------- sidebar
with st.sidebar:
    st.header("Filtros")
    corte = st.date_input("📅 Fecha de corte", value=f_max, min_value=f_min, max_value=f_max,
                          help="Todas las métricas se calculan con lo ocurrido hasta esta fecha (inclusive).")
    materias = st.multiselect("Asignaturas", materias_all, default=materias_all)
    dias_inact = st.slider("Días sin ingresar para considerar 'inactivo'", 7, 60, 14)
    st.caption("Las notas no traen fecha: se fechan con el primer 'Realizar evaluación' del alumno en la trazabilidad.")

if not materias:
    st.warning("Elegí al menos una asignatura.")
    st.stop()

est_all = tabla(p, origen, pd.Timestamp(corte), dias_inact, ausentes_cero, base_algebra)
est_all = est_all[est_all["materia"].isin(materias)]
est = est_all[est_all["matriculado"]]  # los KPIs se calculan sobre matriculados; los no inscriptos van en Matrícula y alertas
if est_all.empty or est.empty:
    st.warning("No hay alumnos para los filtros seleccionados.")  # control de estado vacío (Clase 9, paso 6)
    st.stop()
solo = True
kp = S.kpis_por_materia(est_all, solo)  # SQL analítico con DuckDB
corte_prev = pd.Timestamp(corte) - pd.Timedelta(days=7)
kp_prev = None
if corte_prev.date() >= f_min:  # delta contra 7 días antes de la fecha de corte
    e_prev = tabla(p, origen, corte_prev, dias_inact, ausentes_cero, base_algebra)
    kp_prev = S.kpis_por_materia(e_prev[e_prev["materia"].isin(materias)], solo).set_index("materia")

st.title("📊 Seguimiento académico LMS")
st.caption(f"Datos hasta el **{pd.Timestamp(corte):%d/%m/%Y}** · {len(materias)} asignatura(s) · KPIs sobre matriculados")

tabs = st.tabs(["1 · General", "2 · Participación", "3 · Trazabilidad", "4 · Rendimiento",
                "5 · Notas vs Participación", "6 · Ficha individual", "7 · Matrícula y alertas"])


def fmt(v, dec=1, suf=""):
    return "—" if pd.isna(v) else f"{v:,.{dec}f}{suf}"


def delta(materia, col, suf=""):
    """Variación del KPI contra 7 días antes de la fecha de corte (None si no hay dato previo)."""
    if kp_prev is None or materia not in kp_prev.index:
        return None
    a, b = kp.set_index("materia").loc[materia, col], kp_prev.loc[materia, col]
    if pd.isna(a) or pd.isna(b):
        return None
    v = round(a - b, 1) + 0.0  # evita "-0.0"
    return f"{v:.1f}{suf}" if v == 0 else f"{v:+.1f}{suf}"


# ====================================================================== 1 GENERAL
with tabs[0]:
    st.subheader("Resumen por asignatura")
    cols = st.columns(len(kp))
    for c, (_, r) in zip(cols, kp.iterrows()):
        with c:
            st.markdown(f"**{r['materia']}**")
            st.metric("Matriculados", int(r["matriculados"]))
            st.metric("Activos", fmt(r["pct_activos"], 0, "%"), delta(r["materia"], "pct_activos", " pp"),
                      help=f"Ingresaron en los últimos {dias_inact} días. Delta: vs 7 días antes de la fecha de corte")
            st.metric("Nota promedio", fmt(r["nota_prom"], 1), delta(r["materia"], "nota_prom"))
            st.metric("Promocionan", fmt(r["pct_promociona"], 0, "%"), delta(r["materia"], "pct_promociona", " pp"))
    st.divider()
    a, b = st.columns(2)
    with a:
        g = est_all[est_all["matriculado"]].groupby(["materia", "estado_actividad"]).size().reset_index(name="alumnos")
        fig = px.bar(g, x="materia", y="alumnos", color="estado_actividad", barmode="stack",
                     title="Matriculados activos vs inactivos",
                     color_discrete_map={"Activo": "#2e9e5b", "Inactivo": "#f2b01e", "Sin actividad": "#d64545"})
        st.plotly_chart(fig, width="stretch")
    with b:
        g = S.distribucion_condicion(est).rename(columns={"pct": "%"})
        fig = px.bar(g, x="materia", y="%", color="condicion", title="Distribución por condición final",
                     color_discrete_map=COLORES_CONDICION, category_orders={"condicion": ORDEN_COND})
        st.plotly_chart(fig, width="stretch")
    s = pd.concat([serie(p, origen, pd.Timestamp(corte), m) for m in materias])
    fig = px.line(s, x="dia", y="eventos", color="materia", title="Tendencia general: interacciones por día")
    st.plotly_chart(fig, width="stretch")
    with st.expander("Tabla de KPIs"):
        st.dataframe(kp.rename(columns={
            "materia": "Asignatura", "matriculados": "Matriculados", "alumnos_en_aula": "Alumnos en aula",
            "activos": "Activos", "inactivos": "Inactivos", "pct_activos": "% activos",
            "horas_prom": "Horas prom.", "nota_prom": "Nota prom. (0-100)", "pct_promociona": "% promociona",
            "pct_regular": "% regular", "pct_libre": "% libre", "no_inscriptos_activos": "No inscriptos activos"})
            .drop(columns=["sesiones_prom", "avance_prom"]).round(1),
            width="stretch", hide_index=True)

# ================================================================= 2 PARTICIPACIÓN
with tabs[1]:
    st.subheader("Participación")
    rango = st.slider("Rango de fechas", f_min, pd.Timestamp(corte).date(), (f_min, pd.Timestamp(corte).date()))
    s = pd.concat([serie(p, origen, pd.Timestamp(corte), m) for m in materias])
    s = s[(s["dia"].dt.date >= rango[0]) & (s["dia"].dt.date <= rango[1])]
    a, b = st.columns(2)
    with a:
        st.plotly_chart(px.line(s, x="dia", y="usuarios", color="materia",
                                title="Alumnos distintos que ingresan por día"), width="stretch")
    with b:
        t = p["trazabilidad"]
        t = t[t["materia"].isin(materias) & (t["fecha"].dt.date >= rango[0]) & (t["fecha"].dt.date <= rango[1])]
        sem = (t.assign(semana=t["fecha"].dt.to_period("W").dt.start_time)
                 .groupby(["materia", "semana"])["id"].nunique().reset_index(name="alumnos"))
        st.plotly_chart(px.bar(sem, x="semana", y="alumnos", color="materia", barmode="group",
                               title="Alumnos activos por semana"), width="stretch")
    a, b = st.columns(2)
    with a:
        act = est[est["con_actividad"]]
        st.plotly_chart(px.histogram(act, x=act["tiempo_min"] / 60, color="materia", nbins=30, barmode="overlay",
                                     opacity=0.6, labels={"x": "Horas en plataforma"},
                                     title="Distribución del tiempo de conexión por alumno"), width="stretch")
    with b:
        st.plotly_chart(px.histogram(est, x="avance_pct", color="materia", nbins=20, barmode="overlay", opacity=0.6,
                                     title="Cobertura: % de avance en el aula (reporte LMS)"), width="stretch")
        st.caption("El avance proviene del reporte de participación (exportado el 24/10) y no se recalcula por fecha de corte.")
    st.markdown("**Alumnos más y menos activos** (por tiempo estimado de uso)")
    cols_t = ["nombre_completo", "materia", "sesiones", "tiempo_min", "ultima"]
    base = est[est["con_actividad"]][cols_t].sort_values("tiempo_min")
    x, y = st.columns(2)
    x.markdown("Los 10 con más horas")
    x.dataframe(legible(base.tail(10).iloc[::-1]), hide_index=True, width="stretch")
    y.markdown("Los 10 con menos horas (posible abandono)")
    y.dataframe(legible(base.head(10)), hide_index=True, width="stretch")

# ================================================================= 3 TRAZABILIDAD
with tabs[2]:
    st.subheader("Trazabilidad")
    mat_t = st.selectbox("Asignatura", ["Todas"] + materias, key="mat_traz")
    ms = materias if mat_t == "Todas" else [mat_t]
    t = p["trazabilidad"]
    t = t[t["materia"].isin(ms) & (t["fecha"] <= M._corte(corte))]
    a, b = st.columns(2)
    with a:
        c = t.groupby("categoria").size().reset_index(name="interacciones").sort_values("interacciones")
        st.plotly_chart(px.bar(c, x="interacciones", y="categoria", orientation="h",
                               title="Interacciones por tipo"), width="stretch")
    with b:
        c = t.groupby("accion").size().reset_index(name="interacciones").nlargest(12, "interacciones").sort_values("interacciones")
        st.plotly_chart(px.bar(c, x="interacciones", y="accion", orientation="h",
                               title="Acciones más frecuentes"), width="stretch")
    hm = sum(heatmap(p, origen, pd.Timestamp(corte), m) for m in ms)
    fig = go.Figure(go.Heatmap(z=hm.values, x=list(range(24)), y=DIAS, colorscale="Blues"))
    fig.update_layout(title="Mapa de calor: día de la semana × hora", xaxis_title="Hora del día", height=360)
    st.plotly_chart(fig, width="stretch")
    a, b = st.columns(2)
    with a:
        d = t.assign(dia=t["fecha"].dt.normalize()).groupby("dia").size()
        st.metric("Interacciones promedio por día", f"{d.mean():,.0f}")
        sec = t.groupby("seccion").size().reset_index(name="n").nlargest(10, "n").sort_values("n")
        st.plotly_chart(px.bar(sec, x="n", y="seccion", orientation="h", title="Secciones más visitadas"),
                        width="stretch")
    with b:
        franja = pd.cut(t["fecha"].dt.hour, [-1, 5, 11, 17, 23], labels=["Madrugada (0-5)", "Mañana (6-11)", "Tarde (12-17)", "Noche (18-23)"])
        f = t.assign(franja=franja)
        f = f[f["categoria"].isin(["Evaluaciones", "Lectura de material"])].groupby(["franja", "categoria"], observed=True).size().reset_index(name="n")
        st.plotly_chart(px.bar(f, x="franja", y="n", color="categoria", barmode="group",
                               title="¿Cuándo estudian y cuándo rinden?"), width="stretch")

# ===================================================================== 4 RENDIMIENTO
with tabs[3]:
    st.subheader("Rendimiento académico")
    mat_r = st.selectbox("Asignatura", materias, key="mat_rend")
    sc = schema_de(mat_r)
    st.caption(f"Sistema: **{sc['modo']}** · Regular ≥ {sc['regular']} · Promociona ≥ {sc['promo']}"
               + (f" · máx. {sc['max_total']} pts" if sc["modo"] == "acumulativo" else ""))
    _, cal = M.calificaciones_resumen(p, pd.Timestamp(corte), ausentes_cero, base_algebra)
    cal = cal[cal["materia"] == mat_r]
    ids_ok = set(est_all[est_all["matriculado"] & (est_all["materia"] == mat_r)]["id"])
    cal = cal[cal["id"].isin(ids_ok)]
    a, b = st.columns(2)
    with a:
        fig = px.box(cal, x="instrumento", y="pct", points="outliers",
                     title="Comparación de notas por instrumento (normalizadas a 100)")
        fig.update_xaxes(tickangle=-30, title=None)
        st.plotly_chart(fig, width="stretch")
    with b:
        r = est[(est["materia"] == mat_r) & (est["condicion"] != "Sin notas")]
        fig = px.histogram(r, x="pct_final", color="condicion", nbins=20, color_discrete_map=COLORES_CONDICION,
                           category_orders={"condicion": ORDEN_COND}, title="Histograma de nota final (0-100)")
        st.plotly_chart(fig, width="stretch")
    a, b = st.columns(2)
    with a:
        pr = cal.groupby("instrumento").agg(promedio=("pct", "mean"), rindieron=("id", "nunique")).reset_index()
        st.dataframe(pr.round(1).rename(columns={"instrumento": "Instrumento", "promedio": "Promedio (0-100)", "rindieron": "Alumnos"}),
                     hide_index=True, width="stretch")
    with b:
        cc = r["condicion"].value_counts().reindex(ORDEN_COND[:3], fill_value=0).reset_index()
        cc.columns = ["condicion", "alumnos"]
        st.plotly_chart(px.pie(cc, names="condicion", values="alumnos", color="condicion", hole=0.45,
                               color_discrete_map=COLORES_CONDICION, title="Condición final"), width="stretch")
    st.markdown("**Comparación entre asignaturas**")
    comp = kp[["materia", "nota_prom", "pct_promociona", "pct_regular", "pct_libre"]]
    st.plotly_chart(px.bar(comp.melt("materia", ["pct_promociona", "pct_regular", "pct_libre"]), x="materia", y="value",
                           color="variable", barmode="group", labels={"value": "% de alumnos"},
                           color_discrete_map={"pct_promociona": "#2e9e5b", "pct_regular": "#f2b01e", "pct_libre": "#d64545"}),
                    width="stretch")

# =========================================================== 5 NOTAS VS PARTICIPACIÓN
with tabs[4]:
    st.subheader("Notas vs participación")
    d5 = est[est["condicion"] != "Sin notas"]
    x_var = st.radio("Medida de participación", ["tiempo_min", "sesiones", "eventos", "avance_pct"], horizontal=True,
                     format_func={"tiempo_min": "Tiempo de conexión (min)", "sesiones": "Sesiones",
                                  "eventos": "Interacciones", "avance_pct": "Avance (%)"}.get)
    fig = px.scatter(d5, x=x_var, y="pct_final", color="grupo_riesgo", facet_col="materia",
                     hover_data=["nombre_completo", "id", "condicion"], title="Participación vs nota final",
                     labels={"tiempo_min": "Tiempo (min)", "sesiones": "Sesiones", "eventos": "Interacciones",
                             "avance_pct": "Avance (%)", "pct_final": "Nota (0-100)", "grupo_riesgo": "Grupo"})
    for m in d5["materia"].unique():
        h = d5[d5["materia"] == m][[x_var, "pct_final"]].dropna()
        if len(h) > 5 and h[x_var].nunique() > 1:
            k, c0 = np.polyfit(h[x_var], h["pct_final"], 1)
            xs = np.array([h[x_var].min(), h[x_var].max()])
            idx = list(d5["materia"].unique()).index(m) + 1
            fig.add_trace(go.Scatter(x=xs, y=k * xs + c0, mode="lines", line=dict(color="black", dash="dash"),
                                     showlegend=False), row=1, col=idx)
    st.plotly_chart(fig, width="stretch")
    cr = M.correlaciones(est)
    a, b = st.columns([3, 2])
    with a:
        st.markdown("**Correlación con la nota final**")
        tabla_r = pd.DataFrame({
            "Asignatura": cr["materia"], "Medida": cr["variable"], "Alumnos": cr["n"],
            "r de Pearson": cr["pearson"].round(2),
            "¿Significativa? (p < 0,05)": np.where(cr["p_valor"] < 0.05, "Sí", "No")})
        st.dataframe(tabla_r, hide_index=True, width="stretch")
        st.caption("r va de -1 a 1: cerca de 0 es sin relación. 'Sí' quiere decir que la relación no se explica por azar.")
    with b:
        g = d5.groupby(["materia", "grupo_riesgo"]).size().reset_index(name="alumnos")
        st.plotly_chart(px.bar(g, x="alumnos", y="materia", color="grupo_riesgo", orientation="h",
                               title="Grupos de riesgo"), width="stretch")
    riesgo = d5[d5["grupo_riesgo"].str.startswith(("Riesgo", "Participa"))][
        ["nombre_completo", "id", "materia", "pct_final", "condicion", "tiempo_min", "sesiones", "dias_desde_ultima", "grupo_riesgo"]]
    st.markdown(f"**Alumnos en riesgo ({len(riesgo)})**")
    st.dataframe(legible(riesgo.sort_values("pct_final")), hide_index=True, width="stretch")

# ==================================================================== 6 INDIVIDUAL
with tabs[5]:
    st.subheader("Ficha individual 360°")
    est_i = est_all.sort_values("id")
    lista = est_i.drop_duplicates("id")[["id", "nombre_completo"]]
    opciones = [f"{r.nombre_completo} · {r.id}" for r in lista.itertuples()]
    sel = st.selectbox("Alumno (escribí para buscar por nombre o ID)", opciones, index=0)
    uid = sel.split(" · ")[-1]
    f = est_i[est_i["id"] == uid]
    st.markdown(f"### {f['nombre_completo'].iloc[0]}  ·  `{uid}`")
    vista = f[["materia", "estado_insc", "estado_actividad", "condicion", "pct_final", "puntos", "instrumentos_rendidos",
               "instrumentos_disponibles", "sesiones", "tiempo_min", "avance_pct", "ultima"]].copy()
    vista["condicion"] = vista["condicion"].map(SEMAFORO)
    vista["tiempo_min"] = (vista["tiempo_min"] / 60).round(1)
    vista = vista.rename(columns={
        "materia": "Asignatura", "estado_insc": "Inscripción", "estado_actividad": "Actividad", "condicion": "Semáforo",
        "pct_final": "Nota (0-100)", "puntos": "Puntos", "instrumentos_rendidos": "Rendidas",
        "instrumentos_disponibles": "Disponibles", "sesiones": "Sesiones", "tiempo_min": "Horas", "avance_pct": "Avance %",
        "ultima": "Última actividad"})
    st.dataframe(vista.round({c: 1 for c in vista.select_dtypes("number").columns}), hide_index=True, width="stretch")
    if f["condicion"].eq("Libre").any():
        st.error("Atención: este alumno está en condición LIBRE en al menos una asignatura.")
    if (~f["matriculado"]).any() and f["con_actividad"].any():
        st.warning("Este alumno participa en el aula pero NO figura como matriculado en alguna asignatura.")
    a, b = st.columns(2)
    with a:
        _, cal = M.calificaciones_resumen(p, pd.Timestamp(corte), ausentes_cero, base_algebra)
        mi = cal[cal["id"] == uid][["materia", "instrumento", "pct"]].rename(columns={"pct": "Alumno"})
        if len(mi):
            prom = cal.groupby(["materia", "instrumento"])["pct"].mean().rename("Promedio del curso").reset_index()
            mm = mi.merge(prom, on=["materia", "instrumento"]).melt(["materia", "instrumento"], ["Alumno", "Promedio del curso"])
            fig = px.bar(mm, x="instrumento", y="value", color="variable", barmode="group", facet_row="materia",
                         labels={"value": "Nota (0-100)"}, title="Notas vs promedio del curso", height=260 * mm["materia"].nunique() + 120)
            fig.update_xaxes(tickangle=-30, title=None)
            st.plotly_chart(fig, width="stretch")
        else:
            st.info("Sin notas registradas a la fecha de corte.")
    with b:
        t = p["trazabilidad"]
        t = t[(t["id"] == uid) & (t["fecha"] <= M._corte(corte))]
        if len(t):
            sem = t.assign(semana=t["fecha"].dt.to_period("W").dt.start_time).groupby(["materia", "semana"]).size().reset_index(name="interacciones")
            st.plotly_chart(px.bar(sem, x="semana", y="interacciones", color="materia", title="Actividad semanal"),
                            width="stretch")
            cat = t.groupby("categoria").size().reset_index(name="n")
            st.plotly_chart(px.bar(cat, x="categoria", y="n", title="Qué hace en el aula"), width="stretch")
        else:
            st.info("Sin actividad registrada a la fecha de corte.")

# ======================================================================= 7 MATRÍCULA
with tabs[6]:
    st.subheader("Matrícula y alertas")
    g = S.situacion_matricula(est_all)
    st.plotly_chart(px.bar(g, x="materia", y="alumnos", color="situacion_matricula", color_discrete_map=COL_SIT,
                           title="Situación académica: matriculados vs cursantes reales"), width="stretch")
    cols = st.columns(len(kp))
    for c, (_, r) in zip(cols, kp.iterrows()):
        c.metric(r["materia"], f"{int(r['no_inscriptos_activos'])} no inscriptos activos",
                 f"{int(r['matriculados'])} matriculados", delta_color="off")
    st.markdown("### 🚨 No matriculados pero cursando")
    al = est_all[est_all["alerta_no_inscripto"]][
        ["materia", "id", "nombre_completo", "estado_insc", "eventos", "sesiones", "ultima", "pct_final", "condicion"]]
    st.dataframe(legible(al.sort_values(["materia", "eventos"], ascending=[True, False])), hide_index=True, width="stretch")
    st.download_button("Descargar alertas (CSV)", al.to_csv(index=False).encode("utf-8"), "alertas_no_inscriptos.csv", "text/csv")
    st.markdown("### Matriculados sin participación reciente")
    sp = est_all[est_all["situacion_matricula"].isin(["Matriculado sin actividad", "Matriculado inactivo"])][
        ["materia", "id", "nombre_completo", "situacion_matricula", "dias_desde_ultima", "eventos", "ultima"]]
    st.dataframe(legible(sp.sort_values("dias_desde_ultima", ascending=False)), hide_index=True, width="stretch")
    st.download_button("Descargar (CSV)", sp.to_csv(index=False).encode("utf-8"), "matriculados_sin_participacion.csv", "text/csv")
