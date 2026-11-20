# Explicación paso a paso (versión alineada a las clases 8–11 y al formato del TP1)

## 0. Cómo correrlo

```bash
pip install -r requirements.txt
python scripts/build_data.py        # Excel -> limpieza -> 16 controles assert -> Parquet curado (≈15 s)
streamlit run app.py                # dashboard
python scripts/generar_informe.py   # informe Word con el formato del TP1 y los números reales
```

## 1. Qué cambió respecto de la primera versión y por qué

| Clase | Qué se vio | Qué hice |
|---|---|---|
| 8 | Capa curada en Parquet (Snappy, `index=False`), nombres `snake_case`, validar con `assert` | `calidad.py`: 16 `assert` (sin duplicados, notas entre 0 y el máximo, fechas sin nulos, columnas `snake_case`…) y exportación a `curado/*.parquet` con Snappy. Además `estudiantes_curado.parquet`: la tabla analítica, lista para cualquier herramienta. |
| 8 | DuckDB: SQL analítico sobre DataFrames | `sql_kpis.py`: los KPIs por asignatura, la distribución de condiciones y la situación de matrícula se calculan con SQL. Dejé un `verificar()` que compara SQL contra pandas con `assert`: dan lo mismo en tres configuraciones distintas. |
| 9 | Streamlit: `st.metric` con delta, `st.tabs`, descarga CSV, `st.warning` + `st.stop` | Cada tarjeta muestra la variación contra 7 días antes de la fecha de corte. Pestaña "Explorador de datos" con filtros y descarga CSV. Control de estado vacío. `st.divider()` entre secciones. |
| 10 | `@st.cache_data` para DataFrames | Toda la carga y los cálculos pesados usan `cache_data`. La clave de caché incluye el origen de los datos (repo o zip subido) para no mostrar resultados viejos. |
| 11 | Deploy: `app.py`, `requirements.txt`, `.gitignore`, `.streamlit/config.toml`, rutas relativas, `file_uploader` híbrido | Los cuatro archivos están creados. Rutas con `Path(__file__).parent`. Sube un `.zip` con la misma estructura que `data/` y se analiza solo en esa sesión. |

No incorporé el simulador what-if / Machine Learning de la clase 10 porque la consigna del TFI no lo pide.

## 2. El informe: cómo copié el formato del TP1

1. Abrí tu TP1 y medí todo: A4, márgenes 2,54 cm, Arial 12 pt, interlineado 1,5, texto justificado, título negro + subtítulo azul (`1c4587`), encabezado "Objetivo" en azul (`1155cc`), tabla de KPIs con encabezado negro y letras blancas.
2. Estructura: **Objetivo** (4 preguntas + tabla KPI | Fórmula | Unidad | Dimensión) → **Limpieza de los datos** → **Análisis en [herramienta]** → **Conclusión** (hallazgo con números, "Lo interesante es por qué pasa esto", recomendaciones, limitación).
3. Para que el formato sea idéntico, `generar_informe.py` **usa tu TP1 como plantilla** (`informe/plantilla_TP1.docx`): clona los párrafos y la tabla originales y solo cambia el texto.
4. Todas las cifras del texto salen del pipeline (no están escritas a mano).
5. Mantuve el estilo: voz en "nosotros", frases directas, números concretos, sin figuras (tu TP1 no tenía).

Trabajo individual: la línea bajo el título dice "Trabajo individual: Bernardita Robles".

## 3. Pipeline de datos (sin cambios de fondo)

- **Carga dinámica** (`loaders.py`): detecta carpetas, encabezados y todos los `calificaciones_*`. Si el profe suma un archivo, entra solo.
- **Limpieza**: padrón con 14 inscripciones repetidas (gana la aceptada más reciente), 699 eventos duplicados, 19 acciones nulas imputadas, docentes/tutores/coordinadores excluidos, nombres de instrumentos decodificados (HTML/emojis), notas pasadas a número y normalizadas a 0–100.
- **Sesiones**: 30 min sin eventos cortan la sesión; el tiempo calculado correlaciona 0,98 con el del LMS.
- **Fecha de corte**: filtra todo hasta esa fecha; las notas se fechan con la primera "Realizar evaluación" de la trazabilidad.
- **Condición final**: normalizar cada nota por su máximo y promediar lo rendido (criterio de clase). Recuperatorio de Probabilidad reemplaza al original.

## 4. Supuestos a confirmar con el profe

1. **Álgebra**: umbrales 60/85 sobre puntos (de 120) o sobre % normalizado. Con puntos crudos y solo 45 disponibles, el 100 % queda libre. Por defecto uso % normalizado.
2. **Evaluaciones no rendidas**: por defecto no cuentan. Si cuentan como 0, los libres suben a 20–50 %.

## 5. Deploy (clase 11)

El código ya está en https://github.com/bernarditarobles/BI-robles (rama `main`, `app.py` en la raíz, incluye `curado/` y `data/`). Falta solo el paso en Streamlit Cloud, que se hace con tu cuenta:

1. Entrar a share.streamlit.io → **Create app** → elegir el repo `bernarditarobles/BI-robles`, rama `main`, archivo `app.py`.
2. En *Advanced settings* elegir Python 3.11 o superior.
3. Deploy. Si falla un módulo, revisar `requirements.txt` en "Manage app".

El repo tiene que ser público (o tenés que darle acceso a Streamlit a tu cuenta de GitHub).
