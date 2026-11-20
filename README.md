# TFI · Seguimiento académico LMS

Dashboard en Streamlit para analizar participación y rendimiento de alumnos en tres asignaturas (Álgebra, Probabilidad y Estadística, Algoritmos y Estructuras de Datos) a partir de los reportes del LMS.

```bash
pip install -r requirements.txt
python scripts/build_data.py        # Excel de data/ -> limpieza -> controles -> Parquet en curado/
streamlit run app.py                # dashboard
python scripts/generar_informe.py   # informe Word en informe/Informe_TFI.docx
```

Estructura: `app.py` (dashboard), `src/tfi_bi/` (carga, limpieza, métricas, KPIs en SQL con DuckDB, controles de calidad), `scripts/` (pipeline e informe), `data/` (Excel crudos), `curado/` (capa curada en Parquet), `informe/` (plantilla TP1 e informe generado).

Las reglas de evaluación por asignatura están en `src/tfi_bi/config.py`. El detalle de decisiones y supuestos está en [EXPLICACION.md](EXPLICACION.md).
