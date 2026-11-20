"""Configuración central: rutas y reglas de evaluación por asignatura.

Si cambia una regla (umbral, modo de cálculo) o aparece una asignatura nueva,
SOLO hay que tocar este archivo.
"""
from __future__ import annotations

import re
import unicodedata
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = ROOT / "data"
CURADO_DIR = ROOT / "curado"  # capa curada (Gold): parquet con compresión Snappy
MATRICULADOS_DIR = "Matriculados"

# Una sesión termina cuando pasan más de N minutos sin eventos del usuario.
SESSION_GAP_MIN = 30

# Reglas de evaluación (consigna, sección 5). La clave es el nombre normalizado
# de la asignatura (sin tildes, minúsculas).
SCHEMAS = {
    "algebra": dict(modo="acumulativo", max_total=120, regular=60, promo=85),
    "probabilidad y estadistica": dict(modo="promedio", regular=60, promo=85),
    "algoritmos y estructuras de datos": dict(modo="promedio", regular=60, promo=90),
}
DEFAULT_SCHEMA = dict(modo="promedio", regular=60, promo=85)

COLORES_CONDICION = {
    "Promociona": "#2e9e5b",
    "Regular": "#f2b01e",
    "Libre": "#d64545",
    "Sin notas": "#9aa5b1",
}


def norm(texto: str) -> str:
    """Normaliza un nombre: sin tildes, minúsculas, espacios simples."""
    t = unicodedata.normalize("NFKD", str(texto))
    t = "".join(c for c in t if not unicodedata.combining(c))
    return re.sub(r"\s+", " ", t).strip().lower()


def schema_de(materia: str) -> dict:
    return SCHEMAS.get(norm(materia), DEFAULT_SCHEMA)
