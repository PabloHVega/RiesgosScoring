"""
DS4B Risk Score Analyzer: interfaz Streamlit de la API de riesgos (A11).

La app NO contiene lógica de ML: formulario -> [dict] -> POST /score -> visualización.
PD, EAD, LGD y pérdida esperada los calcula la API; aquí solo se presentan.
"""

import os
import time
from pathlib import Path

import plotly.graph_objects as go
import requests
import streamlit as st

# =====================================================================
# CONFIGURACIÓN (única fuente de verdad de URLs y endpoints)
# =====================================================================
# Variable de entorno API_BASE_URL (p. ej. http://127.0.0.1:8000 en local); si no existe, la de Render
API_BASE_URL = os.environ.get("API_BASE_URL", "https://riesgosscoring.onrender.com")
SCORE_ENDPOINT = "/score"
WARMUP_ENDPOINT = "/health"
DEFAULT_TIMEOUT = 60  # POST de scoring
WARMUP_TIMEOUT = 10  # cada GET de warmup (menor que DEFAULT_TIMEOUT)
WARMUP_MAX_WAIT = 180  # tiempo total máximo despertando la API
ENABLE_WARMUP = True
SCORING_RETRIES = 1  # 0-1 (timeout o fallo de conexión)
BLOQUEO_RETRIES = 3  # reintentos ante 429/503 (protección anti-bots de Render/Cloudflare)
DEBUG_MODE = False
# User-Agent propio e identificable en lugar del genérico "python-requests"
HEADERS = {"User-Agent": "RiesgosScoring-App/1.0", "Accept": "application/json"}
SESION = requests.Session()
SESION.headers.update(HEADERS)

APP_TITLE = "Risk Score Analyzer"
ASSETS = Path(__file__).parent / "assets"

# Clientes con historial en la API (api/data/demo_03_riesgos.csv; también en GET /clientes)
CLIENTES = [
    677882,
    142068051,
    142161762,
    494539,
    95167938,
    11976361,
    10150621,
    101282342,
    2367916,
    139644159,
    60810161,
    88993385,
    21241683,
    136754424,
    88924450,
    113617495,
    63184585,
    131517728,
    7371520,
    3379997,
]

# Etiqueta en pantalla -> valor que espera la API (categorías reales, por frecuencia)
FINALIDADES = {
    "Consolidación de deudas": "debt_consolidation",
    "Tarjeta de crédito": "credit_card",
    "Reformas del hogar": "home_improvement",
    "Otros": "other",
    "Compra importante": "major_purchase",
    "Gastos médicos": "medical",
    "Pequeño negocio": "small_business",
    "Coche": "car",
    "Vacaciones": "vacation",
    "Mudanza": "moving",
    "Vivienda": "house",
    "Boda": "wedding",
    "Energías renovables": "renewable_energy",
    "Educación": "educational",
}
VIVIENDAS = {"Hipoteca": "MORTGAGE", "Propia": "OWN", "Alquiler": "RENT"}
# El modelo solo se entrenó con 36 y 60 meses: el resto se evalúa con la duración conocida más cercana
DURACIONES = {12: 36, 24: 36, 36: 36, 48: 60, 60: 60}  # mostrada -> enviada a la API

# Nivel de riesgo según la pérdida esperada en % del importe
UMBRAL_MEDIO, UMBRAL_ALTO = 5.0, 10.0
NIVELES = {
    "bajo": ("#2E7D32", "Riesgo bajo"),
    "medio": ("#F9A825", "Riesgo medio"),
    "alto": ("#D32F2F", "Riesgo alto"),
}


# =====================================================================
# UTILIDADES DE IMÁGENES Y FORMATO
# =====================================================================
def asset(nombre):
    """Ruta de una imagen de assets/ o None si no existe (la app nunca falla por una imagen)."""
    ruta = ASSETS / nombre
    return str(ruta) if ruta.exists() else None


def eur(valor, decimales=2):
    """Formato español: 12.345,67 €"""
    texto = (
        f"{valor:,.{decimales}f}".replace(",", "_").replace(".", ",").replace("_", ".")
    )
    return f"{texto} €"


def pct(valor, decimales=1):
    return f"{valor:.{decimales}f}".replace(".", ",") + " %"


# =====================================================================
# CLIENTE HTTP
# =====================================================================
def wake_api():
    """Despierta la API (autosuspensión en Render) con GET al warmup y backoff suave."""
    inicio, espera = time.time(), 2
    while time.time() - inicio < WARMUP_MAX_WAIT:
        try:
            r = SESION.get(API_BASE_URL + WARMUP_ENDPOINT, timeout=WARMUP_TIMEOUT)
            if r.status_code in (200, 204):
                return True
        except requests.RequestException:
            pass
        time.sleep(espera)
        espera = min(espera * 1.5, 10)
    return False


def enviar_scoring(payload):
    """POST a la API. Devuelve siempre {ok, status_code, data, error_message, raw_text}."""
    resultado = {
        "ok": False,
        "status_code": None,
        "data": None,
        "error_message": None,
        "raw_text": None,
    }
    fallos_red, bloqueos = 0, 0
    while True:
        try:
            r = SESION.post(
                API_BASE_URL + SCORE_ENDPOINT, json=payload, timeout=DEFAULT_TIMEOUT
            )
        except (requests.Timeout, requests.ConnectionError) as e:
            resultado["error_message"] = (
                "La API ha tardado demasiado en responder."
                if isinstance(e, requests.Timeout)
                else "No se ha podido conectar con la API. Comprueba que está arrancada."
            )
            fallos_red += 1
            if fallos_red > SCORING_RETRIES:
                return resultado
            continue

        resultado["status_code"], resultado["raw_text"] = r.status_code, r.text
        if r.status_code in (429, 503) and bloqueos < BLOQUEO_RETRIES:
            bloqueos += 1
            time.sleep(3 * bloqueos)  # backoff: 3, 6, 9 s
            continue
        if r.status_code == 200:
            try:
                resultado.update(ok=True, data=r.json(), error_message=None)
            except ValueError:
                resultado["error_message"] = (
                    "La API ha respondido, pero no con un JSON válido."
                )
        elif r.status_code == 404:
            resultado["error_message"] = (
                "El cliente seleccionado no tiene historial en la API."
            )
        elif r.status_code in (400, 422):
            resultado["error_message"] = (
                "Los datos enviados no son compatibles con la API (payload incompatible)."
            )
        elif r.status_code == 429:
            resultado["error_message"] = (
                "La API está limitando las peticiones (429). Espera unos segundos y vuelve a intentarlo."
            )
        else:
            resultado["error_message"] = (
                f"La API ha devuelto un error ({r.status_code})."
            )
        return resultado


# =====================================================================
# PAYLOAD (campos de Entrada en api/schemas.py)
# =====================================================================
def construir_payload(cliente, importe, tipo_interes, duracion, finalidad, vivienda):
    return [
        {
            "id_cliente": int(cliente),
            "principal": float(importe),
            "tipo_interes": float(tipo_interes),
            "num_cuotas": f" {DURACIONES[duracion]} months",
            "finalidad": FINALIDADES[finalidad],
            "vivienda": VIVIENDAS[vivienda],
        }
    ]


# =====================================================================
# UI
# =====================================================================
st.set_page_config(
    page_title=APP_TITLE,
    page_icon=asset("favicon.png") or "📉",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.markdown(
    """<style>
  .badge {display:inline-block; padding:0.35rem 0.9rem; border-radius:999px;
          color:#fff; font-weight:600; font-size:1rem;}
  .gauge-sub {text-align:center; font-size:1.1rem; margin-top:-1rem;}
</style>""",
    unsafe_allow_html=True,
)

with st.sidebar:
    if asset("logo.png"):
        st.image(asset("logo.png"), width="stretch")
    st.header("Simulador de riesgo crediticio")
    cliente = st.selectbox("Seleccionar cliente", CLIENTES, key="cliente")

    st.divider()
    st.subheader("Características del préstamo")
    importe = st.slider("Importe (€)", 1000, 40000, 10000, step=500, key="importe")
    tipo_interes = st.slider(
        "Tipo de interés (%)", 1.0, 31.0, 10.0, step=0.1, key="tipo_interes"
    )
    duracion = st.radio(
        "Duración (meses)", list(DURACIONES), index=2, horizontal=True, key="duracion"
    )
    if DURACIONES[duracion] != duracion:
        st.caption(
            f"ℹ️ El modelo solo conoce préstamos a 36 y 60 meses: "
            f"{duracion} meses se evalúa como {DURACIONES[duracion]} (aproximación)."
        )

    st.divider()
    st.subheader("Perfil del préstamo")
    finalidad = st.selectbox("Finalidad", list(FINALIDADES), key="finalidad")
    vivienda = st.radio(
        "Situación vivienda", list(VIVIENDAS), horizontal=True, key="situacion_vivienda"
    )

    calcular = st.button(
        "Calcular riesgo", type="primary", width="stretch", key="calcular"
    )
    st.caption(
        "Si la API está en un servicio con autosuspensión, la primera llamada puede tardar."
    )

st.title(APP_TITLE)

if calcular:
    payload = construir_payload(
        cliente, importe, tipo_interes, duracion, finalidad, vivienda
    )
    with st.spinner("Calculando el riesgo del préstamo..."):
        if ENABLE_WARMUP:
            wake_api()
        respuesta = enviar_scoring(payload)
    st.session_state["respuesta"] = respuesta
    st.session_state["entrada"] = {
        "cliente": cliente,
        "importe": importe,
        "duracion": duracion,
        "tipo_interes": tipo_interes,
    }


# =====================================================================
# VISUALIZACIÓN
# =====================================================================
def gauge(titulo, valor, color):
    fig = go.Figure(
        go.Indicator(
            mode="gauge+number",
            value=valor,
            number={"suffix": " %", "valueformat": ".1f"},
            title={"text": titulo, "font": {"size": 16}},
            gauge={
                "axis": {"range": [0, 100]},
                "bar": {"color": color},
                "bgcolor": "rgba(128,128,128,0.08)",
                "borderwidth": 0,
            },
        )
    )
    fig.update_layout(
        height=260,
        margin=dict(l=25, r=25, t=60, b=10),
        separators=",.",
        paper_bgcolor="rgba(0,0,0,0)",
    )
    return fig


def barra_impacto(el_pct, el_eur, color):
    maximo = max(30, el_pct * 1.15)
    fig = go.Figure(
        go.Bar(
            x=[el_pct],
            y=[""],
            orientation="h",
            marker_color=color,
            width=0.5,
            text=f"{eur(el_eur)} · {pct(el_pct, 2)}",
            textposition="auto",
            insidetextanchor="middle",
            textfont=dict(color="white"),
            hoverinfo="skip",
        )
    )
    fig.add_vline(
        x=UMBRAL_ALTO,
        line_dash="dash",
        line_color="#D32F2F",
        annotation_text=f"Umbral {UMBRAL_ALTO:.0f}%",
        annotation_position="top",
    )
    fig.update_layout(
        height=150,
        margin=dict(l=10, r=10, t=35, b=10),
        showlegend=False,
        xaxis=dict(range=[0, maximo], ticksuffix=" %", showgrid=False),
        yaxis=dict(showticklabels=False),
        separators=",.",
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(128,128,128,0.08)",
    )
    return fig


respuesta = st.session_state.get("respuesta")
if respuesta is None:
    st.info(
        "Selecciona un cliente, configura el préstamo en el panel lateral y pulsa **Calcular riesgo**."
    )

elif not respuesta["ok"] or not respuesta["data"]:
    st.error(
        respuesta["error_message"]
        or "La API no ha devuelto resultados para este cliente."
    )
    st.caption(
        "Puedes volver a pulsar **Calcular riesgo**: si la API estaba dormida, el segundo intento suele funcionar."
    )
    with st.expander("Detalle técnico"):
        st.write(
            {"status_code": respuesta["status_code"], "raw_text": respuesta["raw_text"]}
        )

else:
    fila = respuesta["data"][0]
    entrada = st.session_state["entrada"]
    importe_usado = entrada["importe"]
    pd_pct, ead_pct, lgd_pct = fila["pd"] * 100, fila["ead"] * 100, fila["lgd"] * 100
    el_eur = fila["perdida_esperada"]
    el_pct = el_eur / importe_usado * 100
    ead_eur = fila["ead"] * importe_usado
    nivel = (
        "alto"
        if el_pct > UMBRAL_ALTO
        else "medio" if el_pct >= UMBRAL_MEDIO else "bajo"
    )
    color, texto_nivel = NIVELES[nivel]

    with st.container(border=True):
        aprox = (
            ""
            if DURACIONES[entrada["duracion"]] == entrada["duracion"]
            else f" (evaluado como {DURACIONES[entrada['duracion']]})"
        )
        st.caption(
            f"Cliente {fila['id_cliente']} · préstamo de {eur(importe_usado, 0)} · "
            f"{pct(entrada['tipo_interes'])} · {entrada['duracion']} meses{aprox}"
        )
        c1, c2 = st.columns([1, 1])
        with c1:
            st.metric(
                "Pérdidas esperadas (EL)",
                eur(el_eur),
                help="EL = PD × EAD × LGD × importe",
            )
        with c2:
            st.markdown("Riesgo de tipo")
            st.markdown(
                f'<span class="badge" style="background:{color}">{texto_nivel}</span>',
                unsafe_allow_html=True,
            )
        st.markdown("**Impacto de la pérdida sobre el préstamo**")
        st.plotly_chart(
            barra_impacto(el_pct, el_eur, color),
            width="stretch",
            config={"displayModeBar": False},
        )
        st.markdown(f"**Porcentaje sobre el principal:** {pct(el_pct, 2)}")

    g1, g2, g3 = st.columns(3)
    with g1:
        st.plotly_chart(
            gauge("Probabilidad de impago (PD)", pd_pct, color),
            width="stretch",
            config={"displayModeBar": False},
        )
    with g2:
        st.plotly_chart(
            gauge("Exposición al incumplimiento (EAD)", ead_pct, "#455A64"),
            width="stretch",
            config={"displayModeBar": False},
        )
        st.markdown(
            f'<div class="gauge-sub">{eur(ead_eur)}</div>', unsafe_allow_html=True
        )
    with g3:
        st.plotly_chart(
            gauge("Pérdida dado el impago (LGD)", lgd_pct, "#455A64"),
            width="stretch",
            config={"displayModeBar": False},
        )

    if DEBUG_MODE:
        with st.expander("Detalle técnico"):
            st.json(respuesta)
