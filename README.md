# TFI · Seguimiento académico LMS

Dashboard en Streamlit para el seguimiento de alumnos de tres asignaturas (Álgebra, Algoritmos y Estructuras de Datos, y Probabilidad y Estadística) a partir de los reportes anonimizados del LMS: matrícula, participación, trazabilidad y calificaciones.

El proyecto se desarrolló y se probó en local. El repositorio se subió completo al final para la entrega, por eso el historial tiene pocos commits.

## Cómo correrlo

```bash
pip install -r requirements.txt
python scripts/build_data.py
streamlit run app.py
```

`build_data.py` lee los Excel de `data/`, los limpia, corre los controles de calidad y guarda la capa curada en `curado/` (Parquet). La app usa esa capa; si detecta que cambiaron los Excel de `data/`, los vuelve a procesar sola.

## Estructura

| Ruta | Contenido |
|---|---|
| `app.py` | Dashboard (7 pestañas) |
| `src/tfi_bi/config.py` | Rutas y reglas de evaluación por asignatura |
| `src/tfi_bi/loaders.py` | Carga dinámica y limpieza de los Excel |
| `src/tfi_bi/calidad.py` | Controles de calidad (`assert`) y exportación a Parquet |
| `src/tfi_bi/metrics.py` | Sesiones, notas, condición final, participación, correlaciones |
| `src/tfi_bi/sql_kpis.py` | KPIs por asignatura en SQL (DuckDB) |
| `scripts/build_data.py` | Pipeline Excel → limpieza → controles → Parquet |
| `data/` | Excel originales, sin modificar |
| `curado/` | Capa curada en Parquet |

## Datos de entrada

`data/Matriculados/` tiene un Excel por asignatura; cada nombre define una asignatura y su carpeta en `data/`. Dentro de cada carpeta van `reporte_participacion_*.xlsx`, `reporte_trazabilidad_*.xlsx` y uno o más `calificaciones_alumnos_*.xlsx`. Para sumar una evaluación nueva, se agrega el archivo en la carpeta de la asignatura con el mismo formato.

## Criterios de cálculo

- **Fecha de corte:** todas las métricas usan lo ocurrido hasta esa fecha. Las notas se fechan con la primera "Realizar evaluación" del alumno en la trazabilidad.
- **Nota final:** cada nota se divide por su máximo y se lleva a 0–100; se promedia lo rendido. En Álgebra (acumulativa) se toman los puntos obtenidos sobre los puntos posibles de lo ya evaluado. Las evaluaciones no rendidas no cuentan.
- **Condición:** libre < 60 ≤ regular < 85 ≤ promociona (90 en Algoritmos). Los umbrales están en `config.py`.
- **Sesión:** se corta tras 30 minutos sin actividad.
- **Activo:** al menos un evento en los últimos N días antes del corte (14 por defecto, configurable).

## Deploy

Streamlit Community Cloud: repositorio `bernarditarobles/BI-robles`, rama `main`, archivo `app.py`.
