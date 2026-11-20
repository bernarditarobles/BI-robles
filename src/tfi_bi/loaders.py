"""Paso 1-2: lectura DINÁMICA y limpieza de los Excel del LMS.

Principios (los pidió el profe):
  * No se editan los archivos originales; todo se hace en código.
  * No se asume cuántas asignaturas ni cuántos archivos de calificaciones hay:
    se descubren leyendo la carpeta `Matriculados/` y las carpetas hermanas.
  * Cada Excel trae filas de metadata arriba, así que el encabezado se detecta.
"""
from __future__ import annotations

import html
import re
import warnings
from pathlib import Path

import pandas as pd

from .config import DATA_DIR, MATRICULADOS_DIR, norm

warnings.filterwarnings("ignore", category=UserWarning, module="openpyxl")


# ----------------------------------------------------------------- utilidades
def _leer_crudo(path: Path) -> pd.DataFrame:
    return pd.read_excel(path, header=None, dtype=object)


def _fila_encabezado(raw: pd.DataFrame, claves: tuple[str, ...]) -> int:
    """Primera fila cuya primera celda coincide con alguna clave."""
    for i in range(min(len(raw), 40)):
        v = raw.iat[i, 0]
        if isinstance(v, str) and v.strip() in claves:
            return i
    raise ValueError(f"No se encontró encabezado {claves}")


def _con_encabezado(raw: pd.DataFrame, fila: int) -> pd.DataFrame:
    cols = [str(c).strip() if pd.notna(c) else f"col_{j}" for j, c in enumerate(raw.iloc[fila])]
    df = raw.iloc[fila + 1:].copy()
    df.columns = cols
    return df.reset_index(drop=True)


def limpiar_texto(s: str) -> str:
    """Decodifica entidades HTML (&#128073;), quita emojis/símbolos iniciales y espacios."""
    s = html.unescape(str(s))
    s = re.sub(r"^[^\w]+", "", s, flags=re.UNICODE)  # emojis y símbolos al inicio
    return re.sub(r"\s+", " ", s).strip()


def _hhmm_a_min(v) -> float:
    if pd.isna(v):
        return float("nan")
    m = re.match(r"^(\d+):(\d{2})", str(v))
    return int(m.group(1)) * 60 + int(m.group(2)) if m else float("nan")


# ------------------------------------------------------------ cada tipo de archivo
def cargar_matriculados(path: Path, materia: str) -> pd.DataFrame:
    raw = _leer_crudo(path)
    df = _con_encabezado(raw, _fila_encabezado(raw, ("Alumno",)))
    df = df[df["Identificación"].notna()].copy()  # saca el pie "Cantidad de filas"
    df["Identificación"] = df["Identificación"].astype(str).str.strip().str.upper()
    df["fecha_insc"] = pd.to_datetime(df["Fecha inscripción"], dayfirst=True, errors="coerce")
    df["Estado Insc."] = df["Estado Insc."].fillna("Sin estado")
    # Un alumno puede tener varias inscripciones (bajas y reinscripciones).
    # Regla: gana la inscripción Aceptada más reciente; si no hay, la última baja.
    df["_pri"] = (df["Estado Insc."] == "Aceptada").astype(int)
    df = (df.sort_values(["Identificación", "_pri", "fecha_insc"])
            .drop_duplicates("Identificación", keep="last"))
    out = pd.DataFrame({
        "materia": materia,
        "id": df["Identificación"],
        "alumno_matr": df["Alumno"],
        "comision": pd.to_numeric(df["Comisión"], errors="coerce"),
        "estado_insc": df["Estado Insc."],
        "instancia": df["Instancia"].fillna("—"),
        "fecha_insc": df["fecha_insc"],
    })
    out["matriculado"] = out["estado_insc"].eq("Aceptada")
    return out.reset_index(drop=True)


def cargar_participacion(path: Path, materia: str) -> pd.DataFrame:
    raw = _leer_crudo(path)
    df = _con_encabezado(raw, _fila_encabezado(raw, ("Usuario",)))
    df = df[df["Usuario"].notna()].copy()
    # La fila siguiente al encabezado es un sub-encabezado (Cantidad/Cargados) -> ya
    # quedó afuera porque su 'Usuario' es nulo.
    out = pd.DataFrame({
        "materia": materia,
        "id": df["Usuario"].astype(str).str.strip().str.upper(),
        "apellido": df["Apellido"], "nombre": df["Nombre"], "perfil": df["Perfil"],
        "fecha_alta": pd.to_datetime(df["Fecha alta"], dayfirst=True, errors="coerce"),
        "avance_pct": pd.to_numeric(df["Avance"], errors="coerce"),  # 'no aplica' -> NaN
        "interacciones_reporte": pd.to_numeric(df["Interacciones"], errors="coerce"),
        "primera_interaccion": pd.to_datetime(df["Primera interacción"], dayfirst=True, errors="coerce"),
        "ultima_interaccion": pd.to_datetime(df["Última interacción"], dayfirst=True, errors="coerce"),
        "tiempo_reporte_min": df["Tiempo estimado de uso"].map(_hhmm_a_min),
    })
    out = out.drop_duplicates(["materia", "id"], keep="last")
    return out.reset_index(drop=True)


def _accion_faltante(desc: str) -> str:
    d = str(desc).lower()
    if "descarga del archivo adjunto" in d:
        return "Descargar adjunto"
    return "Sin acción registrada"


def cargar_trazabilidad(path: Path, materia: str) -> tuple[pd.DataFrame, dict]:
    raw = _leer_crudo(path)
    df = _con_encabezado(raw, _fila_encabezado(raw, ("Fecha",)))
    n0 = len(df)
    df = df[df["Usuario"].notna()].copy()
    df["Fecha"] = pd.to_datetime(df["Fecha"], errors="coerce")
    df = df[df["Fecha"].notna()]
    n_dup = int(df.duplicated(["Fecha", "Usuario", "Sección", "Acción", "Descripción"]).sum())
    df = df.drop_duplicates(["Fecha", "Usuario", "Sección", "Acción", "Descripción"])
    n_sin_accion = int(df["Acción"].isna().sum())
    df["Acción"] = df["Acción"].where(df["Acción"].notna(), df["Descripción"].map(_accion_faltante))
    out = pd.DataFrame({
        "materia": materia,
        "fecha": df["Fecha"],
        "id": df["Usuario"].astype(str).str.strip().str.upper(),
        "perfil": df["Perfil"],
        "seccion": df["Sección"],
        "accion": df["Acción"],
        "descripcion": df["Descripción"].map(lambda s: html.unescape(str(s))),
    })
    log = dict(materia=materia, filas_originales=n0, duplicados_eliminados=n_dup,
               acciones_imputadas=n_sin_accion, filas_finales=len(out))
    return out.reset_index(drop=True), log


_RE_TIPO = [
    (r"recuperatorio", "Recuperatorio"),
    (r"parcial", "Parcial"),
    (r"autoevaluaci", "Autoevaluación"),
    (r"actividad r", "Actividad rápida"),
    (r"evaluaci[oó]n semanal", "Evaluación semanal"),
]


def _tipo_instrumento(nombre: str) -> str:
    n = nombre.lower()
    for pat, tipo in _RE_TIPO:
        if re.search(pat, n):
            return tipo
    return "Otro"


def cargar_calificaciones(path: Path, materia: str) -> pd.DataFrame:
    raw = _leer_crudo(path)
    nombre = None
    for i in range(min(len(raw), 15)):
        v = raw.iat[i, 0]
        if isinstance(v, str) and v.startswith("Calificación:"):
            nombre = limpiar_texto(v.split(":", 1)[1])
    if nombre is None:
        raise ValueError(f"{path.name}: no se encontró 'Calificación:'")
    df = _con_encabezado(raw, _fila_encabezado(raw, ("Usuario",)))
    df = df[df["Usuario"].notna()].copy()
    nm = df["Nota"].astype(str).str.extract(r"^\s*([\d.,]+)\s*/\s*([\d.,]+)")
    nota = pd.to_numeric(nm[0].str.replace(",", "."), errors="coerce")
    maxi = pd.to_numeric(nm[1].str.replace(",", "."), errors="coerce")
    es_recup = bool(re.search(r"recuperatorio", nombre, re.I))
    base = re.sub(r"^recuperatorio\s*:?\s*", "", nombre, flags=re.I).strip()
    out = pd.DataFrame({
        "materia": materia,
        "id": df["Usuario"].astype(str).str.strip().str.upper(),
        "instrumento": nombre,
        "instrumento_base": base,
        "tipo": _tipo_instrumento(nombre),
        "es_recuperatorio": es_recup,
        "nota": nota.values,
        "max": maxi.values,
        "observaciones": df["Observaciones"].values,
        "archivo": path.name,
    })
    out["pct"] = out["nota"] / out["max"] * 100
    return out[out["nota"].notna()].drop_duplicates(["id", "instrumento"], keep="last")


# ----------------------------------------------------------------- orquestador
def _carpeta_de(materia: str, data_dir: Path) -> Path | None:
    for p in data_dir.iterdir():
        if p.is_dir() and norm(p.name) == norm(materia):
            return p
    return None


def cargar_datos(data_dir: Path = DATA_DIR, verbose: bool = True) -> dict:
    """Lee todo `data_dir` y devuelve un dict de DataFrames + log de limpieza.

    1) Mira Matriculados/*.xlsx -> cada archivo define una asignatura.
    2) Para cada una busca su carpeta y lee trazabilidad, participación y TODOS
       los calificaciones_* que haya (si se suma un archivo nuevo, entra solo).
    """
    data_dir = Path(data_dir)
    mat_dir = next(p for p in data_dir.iterdir() if p.is_dir() and norm(p.name) == norm(MATRICULADOS_DIR))
    matr, part, traz, cal, logs = [], [], [], [], []
    for f in sorted(mat_dir.glob("*.xlsx")):
        materia = f.stem.strip()
        carpeta = _carpeta_de(materia, data_dir)
        if carpeta is None:
            if verbose:
                print(f"[aviso] {materia}: no hay carpeta de datos, se omite")
            continue
        m = cargar_matriculados(f, materia)
        matr.append(m)
        for p in sorted(carpeta.glob("reporte_participacion*.xlsx")):
            part.append(cargar_participacion(p, materia))
        for p in sorted(carpeta.glob("reporte_trazabilidad*.xlsx")):
            t, lg = cargar_trazabilidad(p, materia)
            traz.append(t); logs.append(lg)
        n_cal = 0
        for p in sorted(carpeta.glob("calificaciones_alumnos*.xlsx")):
            cal.append(cargar_calificaciones(p, materia)); n_cal += 1
        if verbose:
            print(f"[ok] {materia}: {len(m)} matriculados, {n_cal} archivos de calificaciones")
    return dict(
        matriculados=pd.concat(matr, ignore_index=True),
        participacion=pd.concat(part, ignore_index=True),
        trazabilidad=pd.concat(traz, ignore_index=True),
        calificaciones=pd.concat(cal, ignore_index=True),
        log_limpieza=pd.DataFrame(logs),
    )
