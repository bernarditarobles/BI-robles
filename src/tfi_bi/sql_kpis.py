"""KPIs con SQL analítico (DuckDB), como en la Clase 8.

DuckDB consulta DataFrames de pandas directamente (sin copiar ni servidor). La tabla
`est` es la tabla analítica de `metrics.tabla_estudiantes` (una fila por materia y alumno).
`kpis_por_materia` de metrics.py hace lo mismo en pandas y sirve para verificar (ver `verificar`).
"""
from __future__ import annotations

import duckdb
import pandas as pd


def _con(**tablas: pd.DataFrame) -> duckdb.DuckDBPyConnection:
    con = duckdb.connect()
    for nombre, df in tablas.items():
        con.register(nombre, df)
    return con


def kpis_por_materia(est: pd.DataFrame, solo_matriculados: bool = True) -> pd.DataFrame:
    """KPIs de participación, notas y matrícula por asignatura."""
    en_base = "matriculado" if solo_matriculados else "TRUE"
    q = f"""
        SELECT
            materia,
            COUNT(*) FILTER (WHERE matriculado)                                        AS matriculados,
            COUNT(*) FILTER (WHERE con_actividad)                                      AS alumnos_en_aula,
            COUNT(*) FILTER (WHERE matriculado AND estado_actividad = 'Activo')        AS activos,
            COUNT(*) FILTER (WHERE matriculado AND estado_actividad <> 'Activo')       AS inactivos,
            100.0 * COUNT(*) FILTER (WHERE matriculado AND estado_actividad = 'Activo')
                  / NULLIF(COUNT(*) FILTER (WHERE matriculado), 0)                     AS pct_activos,
            AVG(sesiones)   FILTER (WHERE matriculado AND con_actividad)               AS sesiones_prom,
            AVG(tiempo_min) FILTER (WHERE matriculado AND con_actividad) / 60.0        AS horas_prom,
            AVG(avance_pct) FILTER (WHERE matriculado)                                 AS avance_prom,
            AVG(pct_final)  FILTER (WHERE {en_base} AND condicion <> 'Sin notas')      AS nota_prom,
            100.0 * COUNT(*) FILTER (WHERE {en_base} AND condicion = 'Promociona')
                  / NULLIF(COUNT(*) FILTER (WHERE {en_base} AND condicion <> 'Sin notas'), 0) AS pct_promociona,
            100.0 * COUNT(*) FILTER (WHERE {en_base} AND condicion = 'Regular')
                  / NULLIF(COUNT(*) FILTER (WHERE {en_base} AND condicion <> 'Sin notas'), 0) AS pct_regular,
            100.0 * COUNT(*) FILTER (WHERE {en_base} AND condicion = 'Libre')
                  / NULLIF(COUNT(*) FILTER (WHERE {en_base} AND condicion <> 'Sin notas'), 0) AS pct_libre,
            COUNT(*) FILTER (WHERE alerta_no_inscripto)                                AS no_inscriptos_activos
        FROM est
        GROUP BY materia
        ORDER BY materia
    """
    return _con(est=est).execute(q).df()


def distribucion_condicion(est: pd.DataFrame) -> pd.DataFrame:
    """Cantidad y % de alumnos con notas por asignatura y condición final."""
    q = """
        SELECT materia, condicion, COUNT(*) AS n,
               100.0 * COUNT(*) / SUM(COUNT(*)) OVER (PARTITION BY materia) AS pct
        FROM est WHERE condicion <> 'Sin notas'
        GROUP BY materia, condicion ORDER BY materia, condicion
    """
    return _con(est=est).execute(q).df()


def situacion_matricula(est: pd.DataFrame) -> pd.DataFrame:
    q = """SELECT materia, situacion_matricula, COUNT(*) AS alumnos
           FROM est GROUP BY materia, situacion_matricula ORDER BY materia, alumnos DESC"""
    return _con(est=est).execute(q).df()


def verificar(est: pd.DataFrame) -> None:
    """Chequeo de equivalencia SQL vs pandas (assert), para dejar el cálculo validado."""
    from . import metrics as M
    for solo in (True, False):
        a = kpis_por_materia(est, solo).reset_index(drop=True)
        b = M.kpis_por_materia(est, solo).sort_values("materia").reset_index(drop=True)
        pd.testing.assert_frame_equal(a, b[a.columns], check_dtype=False, rtol=1e-9, atol=1e-9)
