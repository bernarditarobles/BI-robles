"""Capa de ingeniería de datos: Excel -> limpieza -> validación (assert) -> Parquet curado.

Uso:  python scripts/build_data.py
"""
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from tfi_bi import metrics as M
from tfi_bi.calidad import exportar_curado, validar_capa_curada
from tfi_bi.config import CURADO_DIR, DATA_DIR
from tfi_bi.loaders import cargar_datos

if __name__ == "__main__":
    t0 = time.time()
    d = cargar_datos(DATA_DIR)
    ctrl = validar_capa_curada(d)
    print(f"[ok] {len(ctrl)} controles de calidad superados")
    p = M.preparar(d)
    est = M.tabla_estudiantes(p, M.fecha_maxima(p))  # tabla analítica a la fecha de corte por defecto
    exportar_curado(d, CURADO_DIR, est)
    for f in sorted(CURADO_DIR.glob("*.parquet")):
        print(f"  {f.name:32s} {f.stat().st_size / 1024:8.0f} KB")
    print(f"Listo en {time.time() - t0:.1f}s")
