"""Validación de la capa curada con `assert` (Reto 1 de la Clase 8) y exportación a Parquet.

Principio de la clase: separar almacenamiento eficiente (Parquet + Snappy) del
cómputo analítico (DuckDB / pandas). Todo lo que sale de acá es "fuente única de la verdad".
"""
from __future__ import annotations

import re
from pathlib import Path

import pandas as pd

TABLAS = ["matriculados", "participacion", "trazabilidad", "calificaciones", "log_limpieza"]


def validar_capa_curada(d: dict) -> pd.DataFrame:
    """Corre los controles de calidad. Si alguno falla, lanza AssertionError con el motivo."""
    m, p, t, c = d["matriculados"], d["participacion"], d["trazabilidad"], d["calificaciones"]
    checks: list[tuple[str, bool]] = []

    def chk(nombre: str, cond: bool):
        checks.append((nombre, bool(cond)))
        assert cond, f"Falló el control: {nombre}"

    for nombre, df in d.items():
        chk(f"{nombre}: columnas en snake_case", all(re.fullmatch(r"[a-z0-9_]+", c_) for c_ in df.columns))
    chk("matriculados: sin duplicados (materia, id)", not m.duplicated(["materia", "id"]).any())
    chk("matriculados: todos los IDs tienen formato ALU_", m["id"].str.match(r"^ALU_\d+$").all())
    chk("matriculados: estado de inscripción sin nulos", m["estado_insc"].notna().all())
    chk("participacion: sin duplicados (materia, id)", not p.duplicated(["materia", "id"]).any())
    chk("trazabilidad: fecha sin nulos y tipo datetime", pd.api.types.is_datetime64_any_dtype(t["fecha"]) and t["fecha"].notna().all())
    chk("trazabilidad: acción sin nulos", t["accion"].notna().all())
    chk("trazabilidad: sin eventos duplicados exactos",
        not t.duplicated(["materia", "fecha", "id", "seccion", "accion", "descripcion"]).any())
    chk("calificaciones: sin duplicados (materia, instrumento, id)", not c.duplicated(["materia", "instrumento", "id"]).any())
    chk("calificaciones: máximo > 0", (c["max"] > 0).all())
    chk("calificaciones: 0 <= nota <= máximo", ((c["nota"] >= 0) & (c["nota"] <= c["max"])).all())
    chk("todas las asignaturas de matriculados tienen trazabilidad y participación",
        set(m["materia"]) <= set(t["materia"]) and set(m["materia"]) <= set(p["materia"]))
    return pd.DataFrame(checks, columns=["control", "ok"])


def exportar_curado(d: dict, carpeta: Path, estudiantes: pd.DataFrame | None = None, firma: str | None = None) -> None:
    """Escribe cada tabla como Parquet (Snappy, sin índice) y la huella de los Excel de origen."""
    carpeta.mkdir(exist_ok=True)
    for k, df in d.items():
        df.to_parquet(carpeta / f"{k}.parquet", compression="snappy", index=False)
    if estudiantes is not None:
        estudiantes.to_parquet(carpeta / "estudiantes_curado.parquet", compression="snappy", index=False)
    if firma is not None:
        (carpeta / "firma_datos.txt").write_text(firma)
