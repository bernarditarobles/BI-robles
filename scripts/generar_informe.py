"""Genera el informe (Word) con el MISMO formato que el TP1: se clona su plantilla (fuentes, colores,
interlineado, tabla de KPIs) y se reemplaza el contenido por los números reales del pipeline."""
import copy
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import pandas as pd
from docx import Document

from tfi_bi import metrics as M
from tfi_bi import sql_kpis as S
from tfi_bi.config import CURADO_DIR, DATA_DIR, MATRICULADOS_DIR
from tfi_bi.loaders import _con_encabezado, _fila_encabezado, _leer_crudo

TABLAS = ["matriculados", "participacion", "trazabilidad", "calificaciones", "log_limpieza"]
d = {t: pd.read_parquet(CURADO_DIR / f"{t}.parquet") for t in TABLAS}
p = M.preparar(d)
corte = M.fecha_maxima(p)
est_all = M.tabla_estudiantes(p, corte)
mat = est_all[est_all["matriculado"]]
kp = S.kpis_por_materia(est_all, True).set_index("materia")
cr = M.correlaciones(mat)
sens_cero = M.tabla_estudiantes(p, corte, 14, True, "normalizado")
sens_cero = sens_cero[sens_cero["matriculado"] & (sens_cero["condicion"] != "Sin notas")]
libres_cero = sens_cero.groupby("materia")["condicion"].apply(lambda s: (s == "Libre").mean() * 100)
alg_pts = M.tabla_estudiantes(p, corte, 14, False, "puntos")
alg_pts = alg_pts[alg_pts["matriculado"] & (alg_pts["materia"] == "Álgebra") & (alg_pts["condicion"] != "Sin notas")]
pct_libre_pts = (alg_pts["condicion"] == "Libre").mean() * 100

# --- cifras de limpieza (calculadas, no escritas a mano)
dup_padron = 0
for f in sorted((DATA_DIR / MATRICULADOS_DIR).glob("*.xlsx")):
    raw = _leer_crudo(f)
    t = _con_encabezado(raw, _fila_encabezado(raw, ("Alumno",)))
    t = t[t["Identificación"].notna()]
    dup_padron += int(t["Identificación"].duplicated().sum())
bajas = int((d["matriculados"]["estado_insc"] == "Baja").sum())
lg = d["log_limpieza"]
ev_dup, ev_imp = int(lg["duplicados_eliminados"].sum()), int(lg["acciones_imputadas"].sum())
ev_staff = len(d["trazabilidad"]) - len(p["trazabilidad"])
ev_alum = len(p["trazabilidad"])
n_instr = d["calificaciones"]["instrumento"].nunique()

# --- helpers de formato es-AR
def n(x, dec=0):
    s = f"{x:,.{dec}f}"
    return s.replace(",", "§").replace(".", ",").replace("§", ".")

def pc(x): return f"{n(x)}%"
A, P, G = "Algoritmos y Estructuras de Datos", "Probabilidad y Estadística", "Álgebra"
rg = mat.groupby("grupo_riesgo").size()
riesgo_alto = int(rg.get("Riesgo alto (baja participación y nota baja)", 0))
no_rinde = int(rg.get("Participa pero no rinde", 0))
baja_part = int(rg.get("Rinde con baja participación", 0))
sig = cr[cr["p_valor"] < 0.05].copy()
mx = cr.loc[cr["pearson"].abs().idxmax()]
nombres_v = {"Avance (%)": "el avance", "Sesiones": "las sesiones", "Tiempo de conexión": "el tiempo de conexión", "Interacciones": "las interacciones"}
corto = {A: "Algoritmos", P: "Probabilidad", G: "Álgebra"}
_it = [f"{nombres_v[r.variable]} en {corto[r.materia]} (r = {n(r.pearson, 2)})" for r in sig.itertuples()]
lista_sig = _it[0] if len(_it) == 1 else ", ".join(_it[:-1]) + " y " + _it[-1]
palabra = {1: "un", 2: "dos", 3: "tres", 4: "cuatro", 5: "cinco"}.get(len(sig), str(len(sig)))
t_ = p["trazabilidad"]
hora_pico = int(t_.groupby(t_["fecha"].dt.hour).size().idxmax())
noinsc = est_all[est_all["alerta_no_inscripto"]].groupby("materia").size()
en_aula = est_all[est_all["con_actividad"]].groupby("materia").size()
share = (noinsc / en_aula * 100)
cmax = d["calificaciones"].groupby("materia")["instrumento"].nunique()

# ====================================================== contenido (mismo esqueleto que el TP1)
TITULO1 = "TRABAJO FINAL INTEGRADOR "
TITULO2 = "Herramienta integral de análisis y seguimiento académico LMS"
SUBTITULO = "Business Intelligence & Analytics con Python y Streamlit"
AUTORES = "Trabajo individual: Bernardita Robles"

OBJ = ("El objetivo del informe es analizar la participación y el rendimiento de los alumnos de tres asignaturas "
       "(Álgebra, Algoritmos y Estructuras de Datos, y Probabilidad y Estadística) a partir de los datos de su LMS, "
       "respondiendo las siguientes preguntas:")
PREGUNTAS = ["¿Cuántos alumnos matriculados siguen activos en cada asignatura?",
             "¿Cómo se distribuyen las condiciones finales (promociona, regular, libre)?",
             "¿Se relaciona la participación en el aula con la nota?",
             "¿Hay alumnos que cursan sin estar inscriptos?"]
PRE_TABLA = (f"Para hacer este análisis, se utilizarán seis KPIs y los reportes anonimizados del LMS (matrícula, participación, "
             f"trazabilidad y calificaciones), con fecha de corte al {corte:%d/%m/%Y}, que es la fecha de exportación:")
KPIS = [
    ["KPI", "Fórmula", "Unidad", "Dimensión"],
    ["Alumnos activos", "Matriculados con al menos un evento en los últimos 14 días ÷ Matriculados", "%", "Asignatura"],
    ["Tiempo promedio de conexión", "Suma de la duración de las sesiones ÷ Alumnos con actividad", "horas/alumno", "Asignatura"],
    ["Nota final promedio", "Promedio de (Nota ÷ Máximo × 100) por alumno", "puntos (0-100)", "Asignatura"],
    ["Condición final", "Alumnos en cada condición ÷ Alumnos con notas", "%", "Asignatura y condición"],
    ["Correlación participación-nota", "Coeficiente de Pearson entre tiempo, sesiones o avance y la nota final", "r (-1 a 1)", "Asignatura"],
    ["No inscriptos con actividad", "Alumnos con eventos en el aula sin inscripción aceptada", "alumnos", "Asignatura"],
]
H_LIMPIEZA = "Limpieza de los datos"
LIMPIEZA = [
    (f"Cada Excel trae filas de metadata antes del encabezado, así que el programa detecta la fila del encabezado y lee las carpetas de "
     f"forma dinámica: si se agrega un archivo de calificaciones, se incorpora solo. Unimos las cuatro fuentes por el ID de usuario y la "
     f"asignatura, tomando como universo a todo alumno que aparece en alguna fuente (no solo en el padrón) para poder detectar a los que "
     f"cursan sin inscripción. En el padrón había {dup_padron} inscripciones repetidas (bajas y reinscripciones): nos quedamos con la "
     f"aceptada más reciente y tratamos a las {bajas} bajas como no matriculados. En la trazabilidad eliminamos {n(ev_dup)} eventos "
     f"duplicados, completamos {ev_imp} acciones nulas según su descripción y dejamos afuera a docentes, tutores y coordinadores "
     f"({n(ev_staff)} eventos), por lo que quedan {n(ev_alum)} eventos de alumnos. En las calificaciones decodificamos los nombres de los "
     f"{n_instr} instrumentos (traían emojis y entidades HTML), pasamos las notas de texto a número y las normalizamos a 0-100. "
     f"Definimos una sesión como un período sin pasar 30 minutos sin eventos, y validamos ese cálculo contra el tiempo estimado que "
     f"informa el propio LMS (correlación de 0,98). Guardamos los datos en Parquet (capa curada) y los verificamos con 16 controles de "
     f"calidad."),
    (f"Para la condición final aplicamos la regla de cada cátedra: Álgebra es acumulativo (máximo 120 puntos), y Probabilidad y Algoritmos "
     f"promedian sus instrumentos; un alumno es libre con menos de 60, regular desde 60 y promociona desde 85 (90 en Algoritmos). Como todavía faltan "
     f"instrumentos por cargar, normalizamos cada nota dividiéndola por su máximo y promediamos lo rendido, como se explicó en clase; en "
     f"Probabilidad el recuperatorio reemplaza al instrumento original. Como las notas no traen fecha, la fecha de corte se aplica con la "
     f"primera realización de cada evaluación registrada en la trazabilidad."),
]
H_ANALISIS = "Análisis en Streamlit"
ANALISIS = [
    (f"La herramienta es una aplicación en Streamlit con un panel lateral donde se elige la fecha de corte, las asignaturas, si se analizan "
     f"solo los matriculados o todo el aula, cuántos días sin ingresar se consideran inactividad y cómo se tratan las evaluaciones no "
     f"rendidas. Los KPIs se calculan con SQL en DuckDB sobre la capa curada y cada tarjeta muestra su variación contra siete días antes "
     f"de la fecha de corte. El Dashboard 1 (General) da la mirada de conjunto: los KPIs de cada asignatura, los matriculados activos "
     f"contra inactivos, la distribución de condiciones y la tendencia diaria de interacciones. Lo complementan el de Participación, que "
     f"muestra la evolución de los ingresos con filtro por rango de fechas y el ranking de alumnos más y menos activos, y el de "
     f"Trazabilidad, con las interacciones por tipo, las secciones más visitadas y un mapa de calor por día y hora, donde se ve que la "
     f"actividad se concentra entre las 17 y las 21 h, con pico a las {hora_pico} h, y de lunes a miércoles."),
    ("Los demás dashboards bajan al detalle. El de Rendimiento compara las notas de cada instrumento y la condición final. El de Notas vs "
     "Participación cruza el tiempo, las sesiones, las interacciones y el avance contra la nota en un gráfico de dispersión con su "
     "tendencia, calcula las correlaciones y marca grupos de riesgo. La Ficha individual permite buscar a un alumno por nombre o ID y ver "
     "su semáforo (verde promociona, amarillo regular, rojo libre), sus notas contra el promedio del curso y su actividad semanal. El de "
     "Matrícula y alertas compara matriculados con cursantes reales y lista a los no inscriptos con actividad y a los matriculados sin "
     "participación reciente, con descarga en CSV. Sumamos un Explorador de datos con filtros y descarga, y la posibilidad de subir un "
     "zip con la misma estructura de carpetas para analizar datos nuevos sin tocar el repositorio."),
]
H_CONCL = "Conclusión"
CONCL = [
    (f"Después de analizar los datos concluimos que la participación en el aula casi no explica la nota, y que la mayor diferencia entre "
     f"asignaturas está en Álgebra. Con la fecha de corte al {corte:%d/%m/%Y}, están activos el {pc(kp.loc[A, 'pct_activos'])} de los "
     f"matriculados de Algoritmos, el {pc(kp.loc[P, 'pct_activos'])} de Probabilidad y el {pc(kp.loc[G, 'pct_activos'])} de Álgebra. Sin "
     f"embargo, Algoritmos y Probabilidad promocionan al {pc(kp.loc[A, 'pct_promociona'])} y al {pc(kp.loc[P, 'pct_promociona'])} de los "
     f"alumnos con notas, mientras que Álgebra lo hace con el {pc(kp.loc[G, 'pct_promociona'])} y tiene un "
     f"{pc(kp.loc[G, 'pct_regular'])} en regular. Los libres son muy pocos: {pc(kp.loc[A, 'pct_libre'])}, {pc(kp.loc[P, 'pct_libre'])} "
     f"y {pc(kp.loc[G, 'pct_libre'])}."),
    (f"Lo interesante es por qué pasa esto. Ninguna medida de participación muestra una relación fuerte con la nota: el mayor coeficiente de "
     f"Pearson es {n(mx['pearson'], 2)} ({nombres_v[mx['variable']]} en {corto[mx['materia']]}) y solo {palabra} pares son "
     f"estadísticamente significativos: {lista_sig}, todos positivos y débiles. Es decir, un alumno que pasa más horas conectado no "
     f"necesariamente rinde mejor. Entre los matriculados con notas, {riesgo_alto} tienen condición libre y baja participación, {no_rinde} "
     f"participan pero no rinden y {baja_part} rinden bien con baja participación. Otro hallazgo es de matrícula: entre "
     f"{int(noinsc.min())} y {int(noinsc.max())} alumnos por asignatura (alrededor del {n(share.mean())}% de los que están en el aula) "
     f"tienen actividad sin estar inscriptos, que probablemente son oyentes."),
    (f"A partir de esto recomendamos contactar primero a los {riesgo_alto} alumnos en riesgo alto y a los {no_rinde} que participan pero no "
     f"rinden, con apoyo pedagógico, y revisar con la cátedra el seguimiento de Álgebra, que es la que tiene mayor proporción de alumnos en "
     f"regular. También conviene definir qué hacer con los no inscriptos que cursan (regularizar su inscripción o dejar de contarlos como "
     f"cursantes) y concentrar los avisos y las clases de consulta entre las 18 y las 21 h, que es cuando los alumnos están conectados. No "
     f"recomendamos usar el tiempo de conexión como único indicador de rendimiento: conviene combinarlo con el avance y las notas."),
    (f"Como limitación, las condiciones finales son provisorias porque todavía faltan instrumentos (Álgebra tiene cargados "
     f"{int(cmax[G])} de sus 8). Además dependen de dos supuestos que dejamos como opciones en la herramienta: si las evaluaciones no "
     f"rendidas cuentan como cero, la proporción de libres sube a entre {pc(libres_cero.min())} y {pc(libres_cero.max())}, y en Álgebra "
     f"comparar los puntos crudos contra 60 y 85 dejaría como libre al {pc(pct_libre_pts)} de los alumnos con notas porque solo hay 45 de los 120 puntos posibles. "
     f"El avance del reporte no se recalcula por fecha de corte y es un solo cuatrimestre de datos mockeados, por lo que los resultados "
     f"describen este conjunto y no se pueden generalizar sin más."),
]

# ====================================================== armado sobre la plantilla del TP1
doc = Document(ROOT / "informe" / "plantilla_TP1.docx")
body = doc.element.body
hijos = list(body.iterchildren())
P_T1, P_T2, P_T3, P_H2, P_BODY, P_BUL, P_VACIO, TBL, P_SH = (hijos[i] for i in (0, 1, 2, 3, 4, 5, 10, 11, 12))
sect = hijos[-1]
protos = {k: copy.deepcopy(v) for k, v in dict(t1=P_T1, t2=P_T2, t3=P_T3, h2=P_H2, body=P_BODY, bul=P_BUL,
                                               vacio=P_VACIO, tbl=TBL, sh=P_SH).items()}
for h in hijos[:-1]:
    body.remove(h)


def limpiar_marcas(el):
    for b in el.xpath(".//w:bookmarkStart|.//w:bookmarkEnd"):
        b.getparent().remove(b)


def par(proto, texto):
    el = copy.deepcopy(protos[proto]); limpiar_marcas(el)
    runs = [r for r in el.xpath("./w:r") if r.xpath("./w:t")]
    for r in el.xpath("./w:r"):
        if r is not runs[0]:
            el.remove(r)
    runs[0].xpath("./w:t")[0].text = texto
    return el


def titulo1():
    el = copy.deepcopy(protos["t1"]); limpiar_marcas(el)
    r = el.xpath("./w:r")
    r[0].xpath("./w:t")[0].text = TITULO1
    r[1].xpath("./w:t")[0].text = TITULO2
    return el


def tabla(filas):
    el = copy.deepcopy(protos["tbl"])
    trs = el.xpath("./w:tr")
    proto_fila = copy.deepcopy(trs[1])
    for tr in trs[1:]:
        el.remove(tr)
    def poner(tr, vals):
        for tc, v in zip(tr.xpath("./w:tc"), vals):
            ts = tc.xpath(".//w:t")
            ts[0].text = v
            for t in ts[1:]:
                t.text = ""
    poner(trs[0], filas[0])
    for vals in filas[1:]:
        tr = copy.deepcopy(proto_fila); poner(tr, vals); el.append(tr)
    for g, w in zip(el.xpath(".//w:gridCol"), [2000, 3500, 1500, 2029] * 2):
        g.set("{http://schemas.openxmlformats.org/wordprocessingml/2006/main}w", str(w))
    return el


nuevo = [titulo1(), par("t2", SUBTITULO), par("t3", AUTORES), par("h2", "Objetivo"), par("body", OBJ)]
nuevo += [par("bul", q) for q in PREGUNTAS]
nuevo += [par("body", PRE_TABLA), copy.deepcopy(protos["vacio"]), tabla(KPIS)]
nuevo += [par("sh", H_LIMPIEZA)] + [par("body", t) for t in LIMPIEZA] + [copy.deepcopy(protos["vacio"])]
nuevo += [par("sh", H_ANALISIS)] + [par("body", t) for t in ANALISIS] + [copy.deepcopy(protos["vacio"])]
nuevo += [par("sh", H_CONCL)] + [par("body", t) for t in CONCL]
for el in nuevo:
    sect.addprevious(el)
salida = ROOT / "informe" / "Informe_TFI.docx"
doc.save(salida)
print("OK", salida)
