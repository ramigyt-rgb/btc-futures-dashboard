# fut_app.py
# Ejecutar:
# py -m streamlit run fut_app.py

import os
import hashlib
from datetime import datetime

import ccxt
import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st
import streamlit.components.v1 as components

try:
    import requests
except Exception:
    requests = None

# =========================
# CONFIG GENERAL
# =========================

st.set_page_config(
    page_title="BTCUSDT Futures Dashboard Pro",
    layout="wide",
    initial_sidebar_state="expanded"
)

st.markdown("""
<style>
div[data-testid="stMetricValue"] {font-size: 1.0rem !important; font-weight: 600 !important;}
div[data-testid="stMetricLabel"] {font-size: 0.75rem !important;}
div[data-testid="stMetricDelta"] {font-size: 0.70rem !important;}
.block-container {padding-top: 2rem;}
@media (max-width: 768px) {
    div[data-testid="stMetricValue"] {font-size: 0.95rem !important;}
    div[data-testid="stMetricLabel"] {font-size: 0.70rem !important;}
    h1 {font-size: 1.55rem !important;}
    h2 {font-size: 1.20rem !important;}
}
</style>
""", unsafe_allow_html=True)

OPEN_TRADE_FILE = "open_trade.csv"
CLOSED_TRADES_FILE ="closed_trades.csv"
SIGNALS_FILE = "signals_log.csv"
AUTO_SIGNALS_FILE = "auto_signals_log.csv"
ALERTS_FILE = "alerts_sent_log.csv"
MARKET_STATE_FILE = "market_state.csv"
USERS_FILE = "users.csv"
SYMBOL = "BTC/USDT:USDT"
LIMIT = 300
BACKTEST_LIMIT = 1500
ACCESS_KEY = "1234"

STRATEGIES = [
    "Tendencia + Liquidez",
    "Pullback EMA50",
    "Sweep de Liquidez",
    "Ruptura de Estructura",
    "Reversión Extrema",
    "FVG + Tendencia",
]

# =========================
# HELPERS GENERALES
# =========================

def safe_float(value, default=np.nan):
    try:
        if pd.isna(value):
            return default
        return float(value)
    except Exception:
        return default


def format_number(value, decimals=2):
    try:
        if pd.isna(value):
            return "—"
        return f"{float(value):,.{decimals}f}"
    except Exception:
        return "—"


def fmt0(value):
    return format_number(value, 0)


def display_direction(direction):
    if direction == "LONG":
        return "ALZA"
    if direction == "SHORT":
        return "BAJA"
    if direction == "NO_OPERAR":
        return "NO OPERAR"
    if direction in ["BULL", "LONG_CON_CUIDADO"]:
        return "ALZA"
    if direction in ["BEAR", "SHORT_CON_CUIDADO"]:
        return "BAJA"
    return "NEUTRO"


def safe_read_csv(file_path):
    if os.path.exists(file_path):
        try:
            return pd.read_csv(file_path)
        except Exception:
            return pd.DataFrame()
    return pd.DataFrame()
def init_open_trade_file():



    if not os.path.exists(OPEN_TRADE_FILE):



        pd.DataFrame(columns=[



            "fecha", "direction", "entry", "sl", "tp",



            "size_btc", "leverage", "status"



        ]).to_csv(OPEN_TRADE_FILE, index=False)



def get_open_trade():



    init_open_trade_file()



    df = safe_read_csv(OPEN_TRADE_FILE)



    if df.empty:



        return None



    active = df[df["status"].astype(str) == "OPEN"]



    if active.empty:



        return None



    return active.iloc[-1].to_dict()



def save_open_trade(row):



    pd.DataFrame([row]).to_csv(OPEN_TRADE_FILE, index=False)

def close_open_trade(row):

    old = safe_read_csv(CLOSED_TRADES_FILE)
    new = pd.DataFrame([row])
    out = pd.concat([old, new], ignore_index=True) if not old.empty else new
    out.to_csv(CLOSED_TRADES_FILE, index=False)
    pd.DataFrame(columns=[
        "fecha", "direction", "entry", "sl", "tp",
        "size_btc", "leverage", "status"
    ]).to_csv(OPEN_TRADE_FILE, index=False)

def calc_live_trade(trade, current_price):
    direction = trade["direction"]
    entry = float(trade["entry"])
    sl = float(trade["sl"])
    tp = float(trade["tp"])
    size_btc = float(trade["size_btc"])
    if direction == "LONG":
        pnl = (current_price - entry) * size_btc
        risk_pts = entry - sl
        current_r = (current_price - entry) / risk_pts if risk_pts > 0 else 0
        distance_tp = tp - current_price
        distance_sl = current_price - sl
    else:
        pnl = (entry - current_price) * size_btc
        risk_pts = sl - entry
        current_r = (entry - current_price) / risk_pts if risk_pts > 0 else 0
        distance_tp = current_price - tp
        distance_sl = sl - current_price
    if pnl > 0:
        estado = "🟢 GANANDO"
    elif pnl < 0:
        estado = "🔴 PERDIENDO"
    else:
        estado = "🟡 BREAK EVEN"
    return pnl, current_r, distance_tp, distance_sl, estado

def init_open_trade_file():
    if not os.path.exists(OPEN_TRADE_FILE):
        
        pd.DataFrame(columns=[
        "fecha",
        "direccion",
        "entrada",
        "sl",
        "tp",
        "size_btc",
        "leverage",
        "estado"
    ]).to_csv(OPEN_TRADE_FILE, index=False)
    return pd.DataFrame()


def save_signal_row(file_path, row):
    new = pd.DataFrame([row])
    old = safe_read_csv(file_path)
    out = pd.concat([old, new], ignore_index=True) if not old.empty else new
    out.to_csv(file_path, index=False)

# =========================
# LOGIN SIMPLE
# =========================

def hash_password(password: str) -> str:
    return hashlib.sha256(str(password).encode("utf-8")).hexdigest()


def init_users_file():
    if not os.path.exists(USERS_FILE):
        pd.DataFrame([
            {"usuario": "demo", "password_hash": hash_password("demo"), "rol": "cliente"}
        ]).to_csv(USERS_FILE, index=False)


def check_login(usuario, password):
    init_users_file()
    users = pd.read_csv(USERS_FILE)
    if users.empty:
        return False
    usuario = str(usuario)
    password_hash = hash_password(password)
    if "password_hash" in users.columns:
        ok = users[(users["usuario"].astype(str) == usuario) & (users["password_hash"].astype(str) == password_hash)]
        if len(ok) > 0:
            return True
    if "password" in users.columns:
        ok = users[(users["usuario"].astype(str) == usuario) & (users["password"].astype(str) == str(password))]
        if len(ok) > 0:
            return True
    return False

# =========================
# ALERTAS
# =========================

def get_secret_value(key, default=""):
    try:
        return st.secrets.get(key, default)
    except Exception:
        return default


def get_telegram_credentials(token_override="", chat_id_override=""):
    token = token_override or get_secret_value("TELEGRAM_BOT_TOKEN", "")
    chat_id = chat_id_override or get_secret_value("TELEGRAM_CHAT_ID", "")
    return str(token).strip(), str(chat_id).strip()


def send_telegram_message(text, token_override="", chat_id_override=""):
    if requests is None:
        return False, "requests no instalado. Agregá requests en requirements.txt."
    token, chat_id = get_telegram_credentials(token_override, chat_id_override)
    if not token or not chat_id:
        return False, "Falta TELEGRAM_BOT_TOKEN o TELEGRAM_CHAT_ID en Secrets."
    try:
        url = f"https://api.telegram.org/bot{token}/sendMessage"
        r = requests.post(url, data={"chat_id": chat_id, "text": text, "parse_mode": "HTML", "disable_web_page_preview": True}, timeout=10)
        return r.ok, r.text[:500]
    except Exception as e:
        return False, str(e)


def send_discord_message(webhook_url, text):
    if not webhook_url or requests is None:
        return False, "Falta webhook o librería requests."
    try:
        clean_text = text.replace("<b>", "**").replace("</b>", "**")
        r = requests.post(webhook_url, json={"content": clean_text}, timeout=10)
        return r.ok, r.text[:500]
    except Exception as e:
        return False, str(e)


def alert_already_sent(alert_key):
    df = safe_read_csv(ALERTS_FILE)
    if df.empty or "alert_key" not in df.columns:
        return False
    return str(alert_key) in set(df["alert_key"].astype(str))


def save_alert_sent(alert_key, tipo, canal, mensaje, response=""):
    row = pd.DataFrame([{
        "fecha": datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S"),
        "alert_key": str(alert_key),
        "tipo": tipo,
        "canal": canal,
        "mensaje": str(mensaje)[:700],
        "response": str(response)[:500],
    }])
    old = safe_read_csv(ALERTS_FILE)
    out = pd.concat([old, row], ignore_index=True) if not old.empty else row
    out.to_csv(ALERTS_FILE, index=False)


def send_alert_once(alert_key, tipo, mensaje, telegram_on, discord_on, discord_url="", token_override="", chat_id_override=""):
    if alert_already_sent(alert_key):
        return False, "Alerta ya enviada"
    sent_any = False
    responses = []
    if telegram_on:
        ok, resp = send_telegram_message(mensaje, token_override, chat_id_override)
        responses.append(f"Telegram: {resp}")
        if ok:
            sent_any = True
            save_alert_sent(alert_key, tipo, "telegram", mensaje, resp)
    if discord_on and discord_url:
        ok, resp = send_discord_message(discord_url, mensaje)
        responses.append(f"Discord: {resp}")
        if ok:
            sent_any = True
            save_alert_sent(alert_key, tipo, "discord", mensaje, resp)
    return sent_any, " | ".join(responses) if responses else "Alertas desactivadas"


def load_market_state():
    df = safe_read_csv(MARKET_STATE_FILE)
    if df.empty or "state_key" not in df.columns:
        return ""
    return str(df["state_key"].iloc[-1])


def save_market_state(state_key):
    pd.DataFrame([{
        "fecha": datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S"),
        "state_key": state_key,
    }]).to_csv(MARKET_STATE_FILE, index=False)

# =========================
# SIDEBAR / ACCESO
# =========================

st.sidebar.title("Configuración")
st.sidebar.subheader("🔐 Acceso")

if "auth" not in st.session_state:
    st.session_state.auth = False

try:
    if st.query_params.get("auth") == "1":
        st.session_state.auth = True
except Exception:
    pass

if not st.session_state.auth:
    clave = st.sidebar.text_input("Clave de acceso", type="password", key="access_key_input")
    if not clave:
        st.warning("Ingrese la clave de acceso para abrir el dashboard.")
        st.stop()
    if clave != ACCESS_KEY:
        st.error("Clave incorrecta.")
        st.stop()
    st.session_state.auth = True
    try:
        st.query_params["auth"] = "1"
    except Exception:
        pass
    st.rerun()
else:
    st.sidebar.success("Acceso habilitado")
    if st.sidebar.button("Cerrar acceso", key="logout_access_btn"):
        st.session_state.auth = False
        try:
            st.query_params.clear()
        except Exception:
            pass
        st.rerun()

with st.sidebar.expander("🔐 Login de usuarios", expanded=False):
    st.caption("Login simple local. Usuario demo: demo / demo")
    use_login = st.checkbox("Activar login", value=False, key="use_login_chk")
    usuario_login = st.text_input("Usuario", value="demo", key="user_login_input")
    password_login = st.text_input("Contraseña", value="demo", type="password", key="password_login_input")
    if use_login:
        if check_login(usuario_login, password_login):
            st.success(f"Usuario activo: {usuario_login}")
        else:
            st.error("Usuario o contraseña incorrectos.")
            st.stop()

estrategia = st.sidebar.selectbox("Estrategia", STRATEGIES, key="estrategia_select")
account_usd = st.sidebar.number_input("Cuenta USDT", min_value=10.0, value=500.0, step=10.0, key="account_usd_input")
risk_pct_input = st.sidebar.number_input("Riesgo por operación %", min_value=0.1, max_value=5.0, value=1.0, step=0.1, key="risk_pct_input")
risk_pct = risk_pct_input / 100
leverage = st.sidebar.selectbox("Apalancamiento sugerido", [1, 2, 3, 5, 10, 20, 50, 75, 100, 125, 150], index=3, key="leverage_select")
min_score = st.sidebar.slider("Score mínimo para operar", 1, 10, 7, key="min_score_slider")
rr_target = st.sidebar.number_input("Riesgo/Beneficio objetivo", min_value=1.0, max_value=10.0, value=2.0, step=0.1, key="rr_target_input")
min_rr = st.sidebar.number_input("RR mínimo aceptado", min_value=1.0, max_value=10.0, value=1.8, step=0.1, key="min_rr_input")
max_atr_multiplier = st.sidebar.number_input("Máximo SL permitido en ATR", min_value=0.5, max_value=5.0, value=2.0, step=0.1, key="max_atr_input")
show_levels_when_no_trade = st.sidebar.checkbox("Mostrar SL/TP aunque sea NO OPERAR", value=True, key="show_levels_chk")

modo_operativo = st.sidebar.selectbox("Modo de operación", ["Conservador", "Normal", "Agresivo", "Scalping agresivo", "Scalp 15M"], index=1, key="modo_operativo_select")
if modo_operativo == "Conservador":
    rr_target, max_atr_multiplier, min_score = 2.0, 2.0, 8
elif modo_operativo == "Normal":
    rr_target, max_atr_multiplier, min_score = 2.0, 2.5, 7
elif modo_operativo == "Agresivo":
    rr_target, max_atr_multiplier, min_score = 1.5, 1.8, 6
elif modo_operativo == "Scalping agresivo":
    rr_target, max_atr_multiplier, min_score = 1.2, 1.2, 5
elif modo_operativo == "Scalp 15M":
    rr_target = 1.2
    min_rr = 1.2
    max_atr_multiplier = 1.0
    min_score = 6

st.sidebar.divider()
st.sidebar.subheader("FVG profesional")
use_fvg_filter = st.sidebar.checkbox("Usar filtro FVG en validación", value=False, key="use_fvg_filter_chk")
show_fvg_zones = st.sidebar.checkbox("Mostrar zonas FVG", value=True, key="show_fvg_zones_chk")
show_mitigated_fvg = st.sidebar.checkbox("Mostrar FVG mitigados", value=True, key="show_mitigated_fvg_chk")
fvg_min_atr = st.sidebar.number_input("FVG mínimo en ATR", min_value=0.05, max_value=2.0, value=0.20, step=0.05, key="fvg_min_atr_input")
fvg_max_distance_atr = st.sidebar.number_input("Distancia máx. al FVG en ATR", min_value=0.1, max_value=5.0, value=1.50, step=0.1, key="fvg_max_distance_atr_input")

st.sidebar.divider()
st.sidebar.subheader("Backtesting")
backtest_period = st.sidebar.selectbox("Período", ["3 meses", "6 meses", "1 año"], index=0, key="bt_period_select")
backtest_tf = st.sidebar.selectbox("Timeframe backtest", ["15m", "5m"], index=0, key="bt_tf_select")
filter_hours = st.sidebar.checkbox("Filtro horario: Londres / Londres + NY", value=True, key="filter_hours_chk")
avoid_weekends = st.sidebar.checkbox("Evitar fines de semana", value=True, key="avoid_weekends_chk")
validate_after_hours = st.sidebar.number_input("Validar señales después de horas", min_value=1, max_value=72, value=24, step=1, key="validate_hours_input")

st.sidebar.divider()
st.sidebar.subheader("Monte Carlo / Drawdown")
mc_enabled = st.sidebar.checkbox("Mostrar módulo Monte Carlo", value=True, key="mc_enabled_chk")
mc_trades_horizon = st.sidebar.number_input("Horizonte simulación: trades", min_value=5, max_value=300, value=50, step=5, key="mc_horizon_input")
mc_paths = st.sidebar.number_input("Escenarios simulados", min_value=500, max_value=20000, value=5000, step=500, key="mc_paths_input")
mc_start_capital = st.sidebar.number_input("Capital simulado USDT", min_value=10.0, value=float(account_usd), step=10.0, key="mc_start_cap_input")
mc_max_daily_trades = st.sidebar.number_input("Máx. trades por día", min_value=1, max_value=20, value=3, step=1, key="mc_max_trades_day_input")
mc_use_backtest = st.sidebar.checkbox("Usar resultados del backtest para Monte Carlo", value=True, key="mc_use_bt_chk")
mc_manual_wr = st.sidebar.number_input("Winrate manual %", min_value=1.0, max_value=99.0, value=45.0, step=1.0, key="mc_manual_wr_input")
mc_manual_rr = st.sidebar.number_input("RR ganador manual", min_value=0.5, max_value=10.0, value=float(rr_target), step=0.1, key="mc_manual_rr_input")
mc_ruin_dd_pct = st.sidebar.number_input("Umbral de ruina / alerta DD %", min_value=5.0, max_value=100.0, value=30.0, step=5.0, key="mc_ruin_dd_input")

st.sidebar.divider()
st.sidebar.subheader("Producto Pro")
auto_capture_enabled = st.sidebar.checkbox("Captura automática de señales válidas", value=True, key="auto_capture_chk")
mobile_compact = st.sidebar.checkbox("Modo móvil compacto", value=False, key="mobile_compact_chk")
auto_refresh_enabled = st.sidebar.checkbox("Auto actualizar para alertas", value=False, key="auto_refresh_chk")
auto_refresh_seconds = st.sidebar.number_input("Actualizar cada segundos", min_value=60, max_value=900, value=120, step=30, key="auto_refresh_seconds_input")

with st.sidebar.expander("🔔 Alertas estratégicas", expanded=False):
    st.caption("Usa Secrets de Streamlit. Opcionalmente podés sobrescribir token/chat_id acá.")
    telegram_enabled = st.checkbox("Activar Telegram", value=True, key="telegram_enabled_chk")
    telegram_bot_token = st.text_input("Telegram bot token opcional", value="", type="password", key="telegram_token_input")
    telegram_chat_id = st.text_input("Telegram chat ID opcional", value="", key="telegram_chat_id_input")
    discord_enabled = st.checkbox("Activar Discord", value=False, key="discord_enabled_chk")
    discord_webhook_url = st.text_input("Discord webhook URL", value="", type="password", key="discord_webhook_input")
    alert_valid_signals = st.checkbox("Avisar señales válidas", value=True, key="alert_valid_chk")
    alert_almost_setups = st.checkbox("Avisar setups en formación", value=True, key="alert_almost_chk")
    alert_bias_change = st.checkbox("Avisar cambio fuerte de sesgo", value=True, key="alert_bias_chk")
    alert_risk_warning = st.checkbox("Avisar TP/SL demasiado exigente", value=False, key="alert_risk_chk")
    almost_score_gap = st.slider("Setup en formación: a cuántos puntos del score", 1, 3, 1, key="almost_gap_slider")
    alert_market_updates = st.checkbox("Enviar resumen de mercado automático", value=True, key="alert_market_updates_chk")
    market_update_minutes = st.number_input("Cada cuántos minutos", min_value=5, max_value=60, value=5, step=5, key="market_update_minutes_input")
    if st.button("📲 Probar Telegram", key="test_telegram_btn"):
        ok, resp = send_telegram_message(
            "🚀 BTC Dashboard Pro conectado correctamente.",
            telegram_bot_token,
            telegram_chat_id
        )
        if ok:
            st.success("Mensaje enviado correctamente.")
        else:
            st.error("No se pudo enviar el mensaje de prueba.")
            st.caption(str(resp)[:300])
st.sidebar.divider()
if st.sidebar.button("🔄 Actualizar datos", key="refresh_btn"):
    st.rerun()

if auto_refresh_enabled:
    components.html(f"""
        <script>
        setTimeout(function() {{window.parent.location.reload();}}, {int(auto_refresh_seconds) * 1000});
        </script>
        """, height=0)

# =========================
# EXCHANGE / DATA
# =========================

@st.cache_resource(show_spinner=False)
def get_exchange():
    return ccxt.okx({"enableRateLimit": True, "options": {"defaultType": "swap"}})

@st.cache_data(ttl=60, show_spinner=False)
def get_ohlcv(timeframe, limit=LIMIT):
    ex = get_exchange()
    data = ex.fetch_ohlcv(SYMBOL, timeframe=timeframe, limit=limit)
    df = pd.DataFrame(data, columns=["time", "open", "high", "low", "close", "volume"])
    df["time"] = pd.to_datetime(df["time"], unit="ms", utc=True)
    return df


def add_indicators(df):
    df = df.copy()
    if df.empty:
        return df
    df["ema20"] = df["close"].ewm(span=20, adjust=False).mean()
    df["ema50"] = df["close"].ewm(span=50, adjust=False).mean()
    df["ema200"] = df["close"].ewm(span=200, adjust=False).mean()
    delta = df["close"].diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    avg_gain = gain.rolling(14).mean()
    avg_loss = loss.rolling(14).mean()
    rs = avg_gain / avg_loss.replace(0, np.nan)
    df["rsi"] = 100 - (100 / (1 + rs))
    tr1 = df["high"] - df["low"]
    tr2 = (df["high"] - df["close"].shift()).abs()
    tr3 = (df["low"] - df["close"].shift()).abs()
    df["tr"] = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
    df["atr"] = df["tr"].rolling(14).mean()
    df["body"] = (df["close"] - df["open"]).abs()
    df["upper_wick"] = df["high"] - df[["open", "close"]].max(axis=1)
    df["lower_wick"] = df[["open", "close"]].min(axis=1) - df["low"]
    df["vol_ma20"] = df["volume"].rolling(20).mean()
    df["vol_ratio"] = df["volume"] / df["vol_ma20"]
    return df


def resample_ohlcv(df, rule):
    if df.empty:
        return df
    return df.resample(rule, on="time").agg({
        "open": "first", "high": "max", "low": "min", "close": "last", "volume": "sum",
    }).dropna().reset_index()


def load_all_data():
    return (
        add_volume_delta(add_indicators(get_ohlcv("1d"))),
        add_volume_delta(add_indicators(get_ohlcv("4h"))),
        add_volume_delta(add_indicators(get_ohlcv("1h"))),
        add_volume_delta(add_indicators(get_ohlcv("15m"))),
        add_volume_delta(add_indicators(get_ohlcv("5m"))),
    )

# =========================
# FVG / ANALISIS
# =========================
def detect_fvg_zones(df, min_atr_mult=0.20, lookback=120, trend_filter=None):
    """
    FVG inteligente:
    - Detecta bullish/bearish FVG.
    - Filtra por tamaño mínimo en ATR.
    - Calcula distancia al precio.
    - Marca mitigación.
    - Asigna score profesional.
    """
    if df is None or df.empty or len(df) < 20:
        return pd.DataFrame()
    d = df.tail(lookback).copy().reset_index(drop=True)
    zones = []
    current_price = float(d["close"].iloc[-1])
    for i in range(2, len(d)):
        c0 = d.iloc[i - 2]
        c2 = d.iloc[i]
        atr = safe_float(d["atr"].iloc[i], np.nan)
        if pd.isna(atr) or atr <= 0:
            continue
        min_gap = atr * min_atr_mult
        bull_gap = c2["low"] - c0["high"]
        bear_gap = c0["low"] - c2["high"]
        # Bullish FVG
        if bull_gap > min_gap:
            low = float(c0["high"])
            high = float(c2["low"])
            mid = (low + high) / 2
            gap_pts = high - low
            gap_atr = gap_pts / atr
            distance_pts = 0 if low <= current_price <= high else min(abs(current_price - low), abs(current_price - high))
            distance_atr = distance_pts / atr
            zones.append({
                "tipo": "BULLISH_FVG",
                "direction": "LONG",
                "time": c2["time"],
                "x0": c0["time"],
                "x1": c2["time"],
                "low": low,
                "high": high,
                "mid": mid,
                "gap_pts": gap_pts,
                "gap_atr": gap_atr,
                "distance_pts": distance_pts,
                "distance_atr": distance_atr,
                "mitigated": False,
                "score": 0,
                "calidad": "",
                "motivo": "",
            })
        # Bearish FVG
        if bear_gap > min_gap:
            low = float(c2["high"])
            high = float(c0["low"])
            mid = (low + high) / 2
            gap_pts = high - low
            gap_atr = gap_pts / atr
            distance_pts = 0 if low <= current_price <= high else min(abs(current_price - low), abs(current_price - high))
            distance_atr = distance_pts / atr
            zones.append({
                "tipo": "BEARISH_FVG",
                "direction": "SHORT",
                "time": c2["time"],
                "x0": c0["time"],
                "x1": c2["time"],
                "low": low,
                "high": high,
                "mid": mid,
                "gap_pts": gap_pts,
                "gap_atr": gap_atr,
                "distance_pts": distance_pts,
                "distance_atr": distance_atr,
                "mitigated": False,
                "score": 0,
                "calidad": "",
                "motivo": "",
            })
    out = pd.DataFrame(zones)
    if out.empty:
        return out
    # Mitigación
    for idx, z in out.iterrows():
        future = d[d["time"] > z["time"]]
        if future.empty:
            continue
        if z["direction"] == "LONG":
            mitigated = (future["low"] <= z["mid"]).any()
        else:
            mitigated = (future["high"] >= z["mid"]).any()
        out.at[idx, "mitigated"] = bool(mitigated)
    # Score inteligente
    for idx, z in out.iterrows():
        score = 0
        motivos = []
        # Tamaño
        if z["gap_atr"] >= 0.80:
            score += 30
            motivos.append("FVG grande")
        elif z["gap_atr"] >= 0.40:
            score += 22
            motivos.append("FVG medio")
        elif z["gap_atr"] >= min_atr_mult:
            score += 12
            motivos.append("FVG válido")
        # Distancia
        if z["distance_atr"] == 0:
            score += 25
            motivos.append("Precio dentro del FVG")
        elif z["distance_atr"] <= 0.75:
            score += 20
            motivos.append("FVG muy cercano")
        elif z["distance_atr"] <= 1.50:
            score += 12
            motivos.append("FVG cercano")
        else:
            motivos.append("FVG lejano")
        # Mitigación
        if not bool(z["mitigated"]):
            score += 20
            motivos.append("FVG abierto")
        else:
            score -= 15
            motivos.append("FVG mitigado")
        # Tendencia
        if trend_filter is not None:
            if z["direction"] == "LONG" and trend_filter == "BULL":
                score += 15
                motivos.append("Alineado con tendencia alcista")
            elif z["direction"] == "SHORT" and trend_filter == "BEAR":
                score += 15
                motivos.append("Alineado con tendencia bajista")
            else:
                score -= 8
                motivos.append("No alineado con tendencia")
        score = int(max(0, min(100, score)))
        if score >= 80:
            calidad = "EXCELENTE"
        elif score >= 65:
            calidad = "BUENO"
        elif score >= 45:
            calidad = "REGULAR"
        else:
            calidad = "DÉBIL"
        out.at[idx, "score"] = score
        out.at[idx, "calidad"] = calidad
        out.at[idx, "motivo"] = " | ".join(motivos)
    return out.sort_values(["score", "time"], ascending=[False, False]).reset_index(drop=True)


def nearest_fvg(price, fvg_df, direction=None, only_open=True):
    if fvg_df is None or fvg_df.empty:
        return None
    d = fvg_df.copy()
    if direction in ["LONG", "SHORT"]:
        d = d[d["direction"] == direction]
    if only_open and "mitigated" in d.columns:
        d = d[~d["mitigated"].astype(bool)]
    if d.empty:
        return None
    d["distance_pts"] = d.apply(lambda r: 0 if r["low"] <= price <= r["high"] else min(abs(price - r["low"]), abs(price - r["high"])), axis=1)
    return d.sort_values(["distance_pts", "time"], ascending=[True, False]).iloc[0].to_dict()


def fvg_state(price, atr, fvg_df, direction, max_distance_atr=1.5):
    z = nearest_fvg(price, fvg_df, direction=direction, only_open=True)
    if not z:
        return "SIN_FVG", None, np.nan, False
    dist = safe_float(z.get("distance_pts", np.nan))
    dist_atr = dist / atr if not pd.isna(atr) and atr > 0 else np.nan
    inside = z["low"] <= price <= z["high"]
    valid = inside or (not pd.isna(dist_atr) and dist_atr <= max_distance_atr)
    label = f"DENTRO {z['tipo']}" if inside else f"CERCA {z['tipo']}" if valid else f"LEJOS {z['tipo']}"
    return label, z, dist_atr, valid


def trend_state(df):
    if df.empty or len(df) < 200:
        return "NEUTRAL"
    last = df.iloc[-1]
    if last["close"] > last["ema20"] > last["ema50"] > last["ema200"]:
        return "BULL"
    if last["close"] < last["ema20"] < last["ema50"] < last["ema200"]:
        return "BEAR"
    return "NEUTRAL"


def trend_icon(state):
    if state == "BULL":
        return "🟢 ALZA"
    if state == "BEAR":
        return "🔴 BAJA"
    return "⚪ NEUTRO"


def rsi_state(value):
    if pd.isna(value):
        return "—"
    if value < 30:
        return "SOBREVENTA"
    if value > 70:
        return "SOBRECOMPRA"
    if 45 <= value <= 60:
        return "OK"
    return "NEUTRO"


def structure_state(df):
    recent = df.tail(20)
    if len(recent) < 20:
        return "SIN_RUPTURA"
    last_high = recent["high"].iloc[-1]
    last_low = recent["low"].iloc[-1]
    prev_high = recent["high"].iloc[:-1].max()
    prev_low = recent["low"].iloc[:-1].min()
    if last_high > prev_high:
        return "BREAK_UP"
    if last_low < prev_low:
        return "BREAK_DOWN"
    return "SIN_RUPTURA"


def liquidity_levels(df):
    data = df.copy()
    if data.empty:
        return {}
    data["date"] = data["time"].dt.date
    data["hour"] = data["time"].dt.hour
    dates = sorted(data["date"].unique())
    if len(dates) < 2:
        return {}
    today, yesterday = dates[-1], dates[-2]
    today_df = data[data["date"] == today]
    yesterday_df = data[data["date"] == yesterday]
    asia = today_df[(today_df["hour"] >= 0) & (today_df["hour"] < 7)]
    london = today_df[(today_df["hour"] >= 7) & (today_df["hour"] < 10)]
    ny = today_df[(today_df["hour"] >= 13) & (today_df["hour"] < 16)]
    return {
        "Máx día anterior": yesterday_df["high"].max(),
        "Mín día anterior": yesterday_df["low"].min(),
        "Máx Asia": asia["high"].max() if len(asia) else np.nan,
        "Mín Asia": asia["low"].min() if len(asia) else np.nan,
        "Máx Londres": london["high"].max() if len(london) else np.nan,
        "Mín Londres": london["low"].min() if len(london) else np.nan,
        "Máx NY": ny["high"].max() if len(ny) else np.nan,
        "Mín NY": ny["low"].min() if len(ny) else np.nan,
    }


def nearest_liquidity(price, levels, direction):
    clean = {k: v for k, v in levels.items() if not pd.isna(v)}
    targets = {k: v for k, v in clean.items() if v > price} if direction == "LONG" else {k: v for k, v in clean.items() if v < price}
    if not targets:
        return None, np.nan, np.nan
    name, level = min(targets.items(), key=lambda item: abs(item[1] - price))
    return name, level, abs(level - price)


def detect_market_intention(price, df_4h, df_1h, df_15m, levels):
    t4, t1 = trend_state(df_4h), trend_state(df_1h)
    rsi = df_15m["rsi"].iloc[-1]
    ema20 = df_15m["ema20"].iloc[-1]
    ema50 = df_15m["ema50"].iloc[-1]
    ema200 = df_15m["ema200"].iloc[-1]
    atr = df_15m["atr"].iloc[-1]
    _, _, up_dist = nearest_liquidity(price, levels, "LONG")
    _, _, dn_dist = nearest_liquidity(price, levels, "SHORT")
    near_up = not pd.isna(up_dist) and not pd.isna(atr) and up_dist <= atr * 0.7
    near_dn = not pd.isna(dn_dist) and not pd.isna(atr) and dn_dist <= atr * 0.7
    if t4 == "BULL" and t1 == "BULL" and price > ema20 > ema50 > ema200:
        return ("ALCISTA CON LIQUIDEZ SUPERIOR CERCA", "LONG_CON_CUIDADO") if near_up else ("TENDENCIA ALCISTA", "LONG")
    if t4 == "BEAR" and t1 == "BEAR" and price < ema20 < ema50 < ema200:
        return ("BAJISTA CON LIQUIDEZ INFERIOR CERCA", "SHORT_CON_CUIDADO") if near_dn else ("TENDENCIA BAJISTA", "SHORT")
    if not pd.isna(rsi) and 45 <= rsi <= 55:
        return "RANGO / COMPRESIÓN", "NEUTRAL"
    return "SIN INTENCIÓN CLARA", "NEUTRAL"


def score_direction(direction, df_4h, df_1h, df_15m, df_5m, levels, fvg_df=None, fvg_max_distance_atr=1.5):
    score = 0
    t4, t1, t15, t5 = trend_state(df_4h), trend_state(df_1h), trend_state(df_15m), trend_state(df_5m)
    rsi_value = df_15m["rsi"].iloc[-1]
    structure = structure_state(df_5m)
    price = df_5m["close"].iloc[-1]
    init_open_trade_file()
    atr = df_15m["atr"].iloc[-1]
    liquidity_name, _, _ = nearest_liquidity(price, levels, direction)
    _, _, _, fvg_valid = fvg_state(price, atr, fvg_df, direction, fvg_max_distance_atr) if fvg_df is not None else ("", None, np.nan, False)
    if direction == "LONG":
        score += 2 if t4 == "BULL" else 0
        score += 2 if t1 == "BULL" else 0
        score += 1 if t15 == "BULL" else 0
        score += 1 if t5 == "BULL" else 0
        score += 1 if not pd.isna(rsi_value) and rsi_value > 50 else 0
        score += 1 if structure == "BREAK_UP" else 0
        score += 1 if liquidity_name else 0
        score += 1 if fvg_valid else 0
    else:
        score += 2 if t4 == "BEAR" else 0
        score += 2 if t1 == "BEAR" else 0
        score += 1 if t15 == "BEAR" else 0
        score += 1 if t5 == "BEAR" else 0
        score += 1 if not pd.isna(rsi_value) and rsi_value < 50 else 0
        score += 1 if structure == "BREAK_DOWN" else 0
        score += 1 if liquidity_name else 0
        score += 1 if fvg_valid else 0
    return score


def detect_sweep_direction(df_5m, levels):
    last = df_5m.iloc[-1]
    price = last["close"]
    upper_name, upper_level, _ = nearest_liquidity(price, levels, "LONG")
    lower_name, lower_level, _ = nearest_liquidity(price, levels, "SHORT")
    if upper_name and last["high"] > upper_level and last["close"] < upper_level:
        return "SHORT"
    if lower_name and last["low"] < lower_level and last["close"] > lower_level:
        return "LONG"
    return None


def choose_candidate_direction(estrategia, long_score, short_score, t1d, t4, structure, price, df_15m, df_5m, levels, fvg_df=None):
    rsi = df_15m["rsi"].iloc[-1]
    sweep_direction = detect_sweep_direction(df_5m, levels)
    if estrategia == "FVG + Tendencia":
        long_fvg = nearest_fvg(price, fvg_df, "LONG", only_open=True)
        short_fvg = nearest_fvg(price, fvg_df, "SHORT", only_open=True)
        if long_score >= short_score and long_fvg:
            return "LONG"
        if short_score > long_score and short_fvg:
            return "SHORT"
    if estrategia == "Reversión Extrema":
        if not pd.isna(rsi) and rsi >= 65:
            return "SHORT"
        if not pd.isna(rsi) and rsi <= 35:
            return "LONG"
    if estrategia == "Sweep de Liquidez" and sweep_direction:
        return sweep_direction
    if estrategia == "Ruptura de Estructura":
        if structure == "BREAK_UP":
            return "LONG"
        if structure == "BREAK_DOWN":
            return "SHORT"
    if long_score > short_score:
        return "LONG"
    if short_score > long_score:
        return "SHORT"
    if structure == "BREAK_UP":
        return "LONG"
    if structure == "BREAK_DOWN":
        return "SHORT"
    ema200 = df_15m["ema200"].iloc[-1]
    if t1d == "BEAR" or t4 == "BEAR":
        return "SHORT"
    if t1d == "BULL" or t4 == "BULL":
        return "LONG"
    return "LONG" if price >= ema200 else "SHORT"


def technical_levels(direction, df_5m, entry, rr_target, fvg_zone=None, modo_operativo="Normal"):
    atr = df_5m["atr"].iloc[-1]
    if pd.isna(atr) or atr <= 0:
        atr = 250
    if modo_operativo == "Scalp 15M":
        sl_atr = 1.0
        tp_atr = 1.2
    elif modo_operativo == "Scalping agresivo":
        sl_atr = 1.2
        tp_atr = 1.5
    else:
        sl_atr = 1.8
        tp_atr = 2.5
    if direction == "LONG":
        sl = entry - atr * sl_atr
        tp = entry + atr * tp_atr
        risk_points = entry - sl
    elif direction == "SHORT":
        sl = entry + atr * sl_atr
        tp = entry - atr * tp_atr
        risk_points = sl - entry
    else:
        sl, tp, risk_points = np.nan, np.nan, np.nan
    return sl, tp, risk_points

def calculate_rr(entry, sl, tp, direction):
    if direction == "LONG":
        risk, reward = entry - sl, tp - entry
    elif direction == "SHORT":
        risk, reward = sl - entry, entry - tp
    else:
        return np.nan
    return reward / risk if risk > 0 else np.nan


def position_size(entry, sl, account_usd, risk_pct, leverage):
    risk_usd_target = account_usd * risk_pct
    max_notional = account_usd * leverage
    if pd.isna(sl) or pd.isna(entry) or entry <= 0:
        return 0, 0, risk_usd_target, 0, risk_usd_target, False, max_notional
    distance = abs(entry - sl)
    if distance <= 0:
        return 0, 0, risk_usd_target, 0, risk_usd_target, False, max_notional
    btc_by_risk = risk_usd_target / distance
    notional_by_risk = btc_by_risk * entry
    capped = notional_by_risk > max_notional
    notional = min(notional_by_risk, max_notional)
    btc_size = notional / entry
    margin_needed = notional / leverage if leverage > 0 else notional
    real_risk_usd = btc_size * distance
    return btc_size, notional, real_risk_usd, margin_needed, risk_usd_target, capped, max_notional


def strategy_filter(estrategia, direction, df_15m, df_5m, levels, structure, market_bias, fvg_df=None, use_fvg_filter=False, fvg_max_distance_atr=1.5, df_1h=None):
    motivos = []
    price = df_5m["close"].iloc[-1]
    last = df_5m.iloc[-1]
    ema50 = df_15m["ema50"].iloc[-1]
    atr = df_15m["atr"].iloc[-1]
    rsi = df_15m["rsi"].iloc[-1]
    sweep_direction = detect_sweep_direction(df_5m, levels)
    fvg_label, _, fvg_dist_atr, fvg_valid = fvg_state(price, atr, fvg_df, direction, fvg_max_distance_atr)
    if estrategia == "Tendencia + Liquidez":
        if direction == "LONG" and market_bias == "SHORT":
            motivos.append("Estrategia Tendencia + Liquidez: mercado contradice LONG.")
        if direction == "SHORT" and market_bias == "LONG":
            motivos.append("Estrategia Tendencia + Liquidez: mercado contradice SHORT.")
    elif estrategia == "Pullback EMA50":
        distancia_ema50 = abs(price - ema50)
        if not pd.isna(atr) and distancia_ema50 > atr * 0.8:
            motivos.append("Pullback EMA50: el precio está lejos de la EMA50.")
        if direction == "LONG" and price < ema50:
            motivos.append("Pullback EMA50: para LONG el precio debe estar sobre EMA50.")
        if direction == "SHORT" and price > ema50:
            motivos.append("Pullback EMA50: para SHORT el precio debe estar bajo EMA50.")
    elif estrategia == "Sweep de Liquidez":
        if sweep_direction is None:
            motivos.append("Sweep de Liquidez: no hay barrida clara de liquidez.")
        elif sweep_direction != direction:
            motivos.append(f"Sweep de Liquidez: la barrida favorece {sweep_direction}, no {direction}.")
    elif estrategia == "Ruptura de Estructura":
        if direction == "LONG" and structure != "BREAK_UP":
            motivos.append("Ruptura de Estructura: falta ruptura alcista.")
        if direction == "SHORT" and structure != "BREAK_DOWN":
            motivos.append("Ruptura de Estructura: falta ruptura bajista.")
    elif estrategia == "Reversión Extrema":
        if direction == "LONG":
            if pd.isna(rsi) or rsi > 35:
                motivos.append("Reversión Extrema: RSI no está en sobreventa para LONG.")
            if last["lower_wick"] <= last["body"]:
                motivos.append("Reversión Extrema: falta mecha inferior de rechazo.")
        if direction == "SHORT":
            if pd.isna(rsi) or rsi < 65:
                motivos.append("Reversión Extrema: RSI no está en sobrecompra para SHORT.")
            if last["upper_wick"] <= last["body"]:
                motivos.append("Reversión Extrema: falta mecha superior de rechazo.")
    elif estrategia == "FVG + Tendencia":
        if not fvg_valid:
            motivos.append(f"FVG + Tendencia: no hay FVG válido/cercano para {direction}. Estado: {fvg_label}.")
        t_1h = trend_state(df_1h) if df_1h is not None else "NEUTRAL"
        if direction == "LONG" and not (t_1h == "BULL" or trend_state(df_15m) == "BULL"):
            motivos.append("FVG + Tendencia: falta tendencia alcista en 1H/15M.")
        if direction == "SHORT" and not (t_1h == "BEAR" or trend_state(df_15m) == "BEAR"):
            motivos.append("FVG + Tendencia: falta tendencia bajista en 1H/15M.")
    if use_fvg_filter and direction in ["LONG", "SHORT"] and not fvg_valid:
        motivos.append(f"Filtro FVG: precio sin FVG {direction} abierto/cercano. Estado: {fvg_label}. Distancia: {format_number(fvg_dist_atr, 2)} ATR.")
    return motivos


def setup_quality(long_score, short_score, direction, rr_real, risk_points, atr_15m, trade_valid, fvg_valid=False):
    base_score = long_score if direction == "LONG" else short_score
    quality_score = int(round((base_score / 10) * 10))
    if not pd.isna(rr_real) and rr_real >= 2:
        quality_score += 1
    if fvg_valid:
        quality_score += 1
    if not pd.isna(risk_points) and not pd.isna(atr_15m):
        quality_score += 1 if risk_points <= atr_15m * 2 else -1
    if not trade_valid:
        quality_score = min(quality_score, 4)
    quality_score = max(1, min(10, quality_score))
    label = "MALA" if quality_score <= 3 else "REGULAR" if quality_score <= 5 else "BUENA" if quality_score <= 7 else "EXCELENTE"
    return quality_score, label

def evaluar_setup_pro(

    direction,

    long_score,

    short_score,

    rr_real,

    risk_points,

    atr_15m,

    tp_atr_multiple,

    fvg_valid,

    fvg_label,

    t1d,

    t4,

    t1,

    t15,

    t5,

    structure,

    price,

    df_15m,

    df_5m,

    levels,

    trade_valid,

    motivos_bloqueo,

    use_time_filter,

    avoid_weekends_filter,

):

    score = 0

    positivos = []

    negativos = []

    dir_score = long_score if direction == "LONG" else short_score

    # 1) Score base dirección

    score += dir_score * 5

    positivos.append(f"Score dirección {dir_score}/10")

    # 2) Tendencia multi timeframe

    if direction == "LONG":

        if t4 == "BULL":

            score += 10

            positivos.append("4H alineado alcista")

        else:

            negativos.append("4H no acompaña LONG")

        if t1 == "BULL":

            score += 10

            positivos.append("1H alineado alcista")

        else:

            negativos.append("1H no acompaña LONG")

        if t15 == "BULL":

            score += 6

            positivos.append("15M acompaña LONG")

        if t5 == "BULL":

            score += 4

            positivos.append("5M acompaña LONG")

        if structure == "BREAK_UP":

            score += 8

            positivos.append("Estructura 5M con ruptura alcista")

        else:

            negativos.append("Falta ruptura alcista clara")

    elif direction == "SHORT":

        if t4 == "BEAR":

            score += 10

            positivos.append("4H alineado bajista")

        else:

            negativos.append("4H no acompaña SHORT")

        if t1 == "BEAR":

            score += 10

            positivos.append("1H alineado bajista")

        else:

            negativos.append("1H no acompaña SHORT")

        if t15 == "BEAR":

            score += 6

            positivos.append("15M acompaña SHORT")

        if t5 == "BEAR":

            score += 4

            positivos.append("5M acompaña SHORT")

        if structure == "BREAK_DOWN":

            score += 8

            positivos.append("Estructura 5M con ruptura bajista")

        else:

            negativos.append("Falta ruptura bajista clara")

    # 3) RR

    if not pd.isna(rr_real):

        if rr_real >= 2.5:

            score += 12

            positivos.append("RR excelente")

        elif rr_real >= 2:

            score += 10

            positivos.append("RR bueno")

        elif rr_real >= 1.8:

            score += 6

            positivos.append("RR aceptable")

        else:

            score -= 12

            negativos.append("RR insuficiente")

    # 4) SL vs ATR

    if not pd.isna(risk_points) and not pd.isna(atr_15m) and atr_15m > 0:

        sl_atr = risk_points / atr_15m

        if sl_atr <= 1.2:

            score += 10

            positivos.append("SL eficiente respecto al ATR")

        elif sl_atr <= 2:

            score += 5

            positivos.append("SL razonable respecto al ATR")

        else:

            score -= 10

            negativos.append("SL demasiado lejos respecto al ATR")

    # 5) TP vs ATR

    if not pd.isna(tp_atr_multiple):

        if tp_atr_multiple <= 2:

            score += 6

            positivos.append("TP alcanzable para intradía")

        elif tp_atr_multiple <= 3:

            score += 2

            positivos.append("TP algo exigente")

        else:

            score -= 6

            negativos.append("TP demasiado exigente")

    # 6) FVG

    if fvg_valid:

        score += 8

        positivos.append(f"FVG válido: {fvg_label}")

    else:

        negativos.append(f"FVG no válido/cercano: {fvg_label}")

    # 7) Volumen relativo

    try:

        vol_ratio = float(df_15m["vol_ratio"].iloc[-1])

        if vol_ratio >= 1.5:

            score += 8

            positivos.append(f"Volumen fuerte {vol_ratio:.2f}x")

        elif vol_ratio >= 1.0:

            score += 4

            positivos.append(f"Volumen normal {vol_ratio:.2f}x")

        else:

            negativos.append(f"Volumen débil {vol_ratio:.2f}x")

    except Exception:

        negativos.append("Volumen no disponible")

    # 8) RSI

    try:

        rsi = float(df_15m["rsi"].iloc[-1])

        if direction == "LONG" and 45 <= rsi <= 68:

            score += 5

            positivos.append("RSI sano para LONG")

        elif direction == "SHORT" and 32 <= rsi <= 55:

            score += 5

            positivos.append("RSI sano para SHORT")

        else:

            negativos.append("RSI no ideal")

    except Exception:

        pass

    # 9) Liquidez cercana

    try:

        liq_name, _, liq_dist = nearest_liquidity(price, levels, direction)

        if liq_name and not pd.isna(liq_dist) and not pd.isna(atr_15m) and atr_15m > 0:

            liq_atr = liq_dist / atr_15m

            if liq_atr >= 0.5:

                score += 5

                positivos.append(f"Objetivo de liquidez disponible: {liq_name}")

            else:

                score -= 5

                negativos.append(f"Demasiado cerca de liquidez: {liq_name}")

    except Exception:

        pass

    # 10) Horario

    try:

        horario_ok = is_allowed_trading_time(df_5m["time"].iloc[-1], use_time_filter, avoid_weekends_filter)

        if horario_ok:

            score += 5

            positivos.append("Horario operativo válido")

        else:

            score -= 8

            negativos.append("Fuera de horario operativo")

    except Exception:

        pass

    # 11) Bloqueos reales

    if trade_valid:

        score += 10

        positivos.append("Sistema habilita operación")

    else:

        score -= min(20, len(motivos_bloqueo) * 5)

        negativos.extend(motivos_bloqueo[:4])

    score = int(max(1, min(100, score)))

    score_10 = max(1, min(10, round(score / 10)))

    if score >= 80:

        label = "EXCELENTE"

    elif score >= 65:

        label = "BUENA"

    elif score >= 45:

        label = "REGULAR"

    else:

        label = "MALA"

    return score_10, label, {

        "score_100": score,

        "positivos": positivos,

        "negativos": negativos,

    }

def is_allowed_trading_time(ts, use_filter=True, avoid_weekends=True):
    if pd.isna(ts):
        return False
    if avoid_weekends and ts.weekday() >= 5:
        return False
    if not use_filter:
        return True
    return (7 <= ts.hour < 10) or (13 <= ts.hour < 16)


def validate_trade(estrategia, direction, long_score, short_score, min_score, risk_pct, rr_real, min_rr,
                   risk_points, atr_15m, market_bias, structure, price, levels, max_atr_multiplier,
                   df_15m, df_5m, use_time_filter=False, avoid_weekends_filter=False,
                   fvg_df=None, use_fvg_filter=False, fvg_max_distance_atr=1.5, df_1h=None):
    motivos = []
    if direction is None:
        return False, ["No hay dirección dominante clara."]
    if direction == "LONG":
        if long_score < min_score:
            motivos.append(f"Long Score insuficiente: {long_score}/{min_score}.")
        if long_score <= short_score:
            motivos.append("Long no supera claramente al Short Score.")
    if direction == "SHORT":
        if short_score < min_score:
            motivos.append(f"Short Score insuficiente: {short_score}/{min_score}.")
        if short_score <= long_score:
            motivos.append("Short no supera claramente al Long Score.")
    if risk_pct > 0.01:
        motivos.append("Riesgo mayor al 1% por operación.")
    if pd.isna(rr_real) or rr_real < min_rr:
        motivos.append(f"RR real insuficiente. Mínimo requerido: {min_rr}.")
    if not pd.isna(risk_points) and not pd.isna(atr_15m) and risk_points > atr_15m * max_atr_multiplier:
        motivos.append("SL demasiado lejos respecto al ATR.")
    nearest_name, _, nearest_distance = nearest_liquidity(price, levels, direction)
    if nearest_name and not pd.isna(nearest_distance) and not pd.isna(atr_15m) and nearest_distance < atr_15m * 0.35:
        motivos.append(f"Entrada demasiado cerca de liquidez: {nearest_name}.")
    if not is_allowed_trading_time(df_5m["time"].iloc[-1], use_time_filter, avoid_weekends_filter):
        motivos.append("Filtro horario: fuera de Londres / NY o fin de semana.")
    motivos.extend(strategy_filter(estrategia, direction, df_15m, df_5m, levels, structure, market_bias, fvg_df, use_fvg_filter, fvg_max_distance_atr, df_1h))
    return len(motivos) == 0, motivos

def detectar_zonas_daytrade(df_15m, asia_high=None, london_high=None, max_zonas=3):

    """

    Motor profesional de zonas/confluencias para daytrade.

    No predice. Ordena zonas, mide calidad y dice qué falta para operar.

    """

    if df_15m is None or df_15m.empty or len(df_15m) < 80:

        return []

    df = df_15m.copy()

    precio = float(df["close"].iloc[-1])

    atr = float(df["atr"].iloc[-1]) if "atr" in df.columns and not pd.isna(df["atr"].iloc[-1]) else precio * 0.003

    if atr <= 0:

        atr = precio * 0.003

    zonas_base = []

    def nueva_zona(nombre, desde, hasta, tipo, peso, motivo):

        centro = (desde + hasta) / 2

        distancia_pts = centro - precio

        distancia_atr = abs(distancia_pts) / atr

        if distancia_atr <= 5:

            zonas_base.append({

                "nombre": nombre,

                "desde": float(desde),

                "hasta": float(hasta),

                "centro": float(centro),

                "tipo": tipo,

                "peso": peso,

                "motivos": [motivo],

                "distancia_pts": distancia_pts,

                "distancia_atr": distancia_atr

            })

    # =========================

    # EMAS

    # =========================

    if "ema20" in df.columns and not pd.isna(df["ema20"].iloc[-1]):

        ema20 = float(df["ema20"].iloc[-1])

        nueva_zona(

            "EMA20",

            ema20 - atr * 0.12,

            ema20 + atr * 0.12,

            "dinamica",

            10,

            "EMA20 cercana"

        )

    if "ema50" in df.columns and not pd.isna(df["ema50"].iloc[-1]):

        ema50 = float(df["ema50"].iloc[-1])

        nueva_zona(

            "EMA50",

            ema50 - atr * 0.15,

            ema50 + atr * 0.15,

            "dinamica",

            14,

            "EMA50 cercana"

        )

    # =========================

    # ASIA / LONDRES

    # =========================

    if asia_high is not None and not pd.isna(asia_high):

        nivel = float(asia_high)

        nueva_zona(

            "Máximo Asia",

            nivel - atr * 0.18,

            nivel + atr * 0.18,

            "liquidez",

            16,

            "Liquidez de Asia"

        )

    if london_high is not None and not pd.isna(london_high):

        nivel = float(london_high)

        nueva_zona(

            "Máximo Londres",

            nivel - atr * 0.18,

            nivel + atr * 0.18,

            "liquidez",

            18,

            "Liquidez de Londres"

        )

    # =========================

    # SWING HIGHS / RESISTENCIAS

    # =========================

    ultimas = df.tail(90).reset_index(drop=True)

    for i in range(2, len(ultimas) - 2):

        h = float(ultimas["high"].iloc[i])

        if (

            h > ultimas["high"].iloc[i - 1]

            and h > ultimas["high"].iloc[i - 2]

            and h > ultimas["high"].iloc[i + 1]

            and h > ultimas["high"].iloc[i + 2]

        ):

            nueva_zona(

                "Resistencia reciente",

                h - atr * 0.15,

                h + atr * 0.15,

                "resistencia",

                13,

                "Swing high / liquidez superior"

            )

    # =========================

    # BEARISH FVG

    # =========================

    for i in range(2, len(df)):

        high_1 = float(df["high"].iloc[i - 2])

        low_3 = float(df["low"].iloc[i])

        if low_3 > high_1:

            tamaño_atr = abs(low_3 - high_1) / atr

            centro = (high_1 + low_3) / 2

            distancia_atr = abs(precio - centro) / atr

            if tamaño_atr >= 0.20 and distancia_atr <= 5:

                nueva_zona(

                    "Bearish FVG",

                    high_1,

                    low_3,

                    "fvg_bajista",

                    20,

                    "Bearish FVG / ineficiencia"

                )

    # =========================

    # UNIFICAR ZONAS SOLAPADAS

    # =========================

    zonas_base = sorted(zonas_base, key=lambda x: x["peso"], reverse=True)

    zonas = []

    for z in zonas_base:

        fusionada = False

        for f in zonas:

            solapa = not (z["hasta"] < f["desde"] or z["desde"] > f["hasta"])

            if solapa:

                f["desde"] = min(f["desde"], z["desde"])

                f["hasta"] = max(f["hasta"], z["hasta"])

                f["peso"] += z["peso"] * 0.45

                for m in z["motivos"]:

                    if m not in f["motivos"]:

                        f["motivos"].append(m)

                if z["tipo"] not in f["tipo"]:

                    f["tipo"] += " + " + z["tipo"]

                fusionada = True

                break

        if not fusionada:

            zonas.append(z)

    resultado = []

    for z in zonas:

        centro = (z["desde"] + z["hasta"]) / 2

        distancia_pts = centro - precio

        distancia_atr = abs(distancia_pts) / atr

        cantidad_confluencias = len(z["motivos"])

        score = 35

        score += min(30, cantidad_confluencias * 9)

        score += max(0, 20 - distancia_atr * 5)

        if "fvg_bajista" in z["tipo"]:

            score += 10

        if "liquidez" in z["tipo"]:

            score += 8

        if "resistencia" in z["tipo"]:

            score += 6

        score = int(max(0, min(100, score)))

        dentro = z["desde"] <= precio <= z["hasta"]

        if score >= 90:

            calidad = "EXCELENTE"

            color = "🟢"

        elif score >= 80:

            calidad = "MUY BUENA"

            color = "🟢"

        elif score >= 70:

            calidad = "BUENA"

            color = "🟡"

        elif score >= 55:

            calidad = "REGULAR"

            color = "🟠"

        else:

            calidad = "DÉBIL"

            color = "🔴"

        if dentro:

            estado = "🟠 Precio dentro de la zona"

            accion = "Esperar confirmación. No entrar directo."

        elif precio < z["desde"]:

            estado = "⏳ Precio debajo de la zona"

            accion = "Esperar llegada a la zona."

        else:

            estado = "⚠️ Precio ya superó la zona"

            accion = "No perseguir entrada."

        sesgo = "SHORT potencial si hay rechazo"

        confirmaciones = {

            "FVG": "Bearish FVG / ineficiencia" in z["motivos"],

            "Liquidez": any("liquidez" in m.lower() for m in z["motivos"]),

            "EMA20": "EMA20 cercana" in z["motivos"],

            "EMA50": "EMA50 cercana" in z["motivos"],

            "Resistencia": any("swing" in m.lower() for m in z["motivos"]),

            "CHoCH": False,

            "Sweep": False,

            "Volumen": False,

        }

        confirmadas = sum(1 for v in confirmaciones.values() if v)

        total_conf = len(confirmaciones)

        if dentro and confirmadas >= 4:

            semaforo = "🟡 VIGILAR"

        elif dentro and confirmadas >= 5:

            semaforo = "🟢 CASI LISTA"

        elif not dentro and score >= 75:

            semaforo = "🟡 ESPERAR PRECIO"

        else:

            semaforo = "🔴 NO OPERAR TODAVÍA"

        faltan = [k for k, v in confirmaciones.items() if not v]

        resultado.append({

            "desde": z["desde"],

            "hasta": z["hasta"],

            "centro": centro,

            "score": score,

            "calidad": calidad,

            "color": color,

            "estado": estado,

            "accion": accion,

            "sesgo": sesgo,

            "distancia_pts": distancia_pts,

            "distancia_atr": distancia_atr,

            "motivos": z["motivos"],

            "confirmaciones": confirmaciones,

            "confirmadas": confirmadas,

            "total_confirmaciones": total_conf,

            "faltan": faltan,

            "semaforo": semaforo,

            "estrellas": "⭐" * max(1, min(5, round(score / 20)))

        })

    resultado = sorted(resultado, key=lambda x: x["score"], reverse=True)

    return resultado[:max_zonas]
def volume_profile_pro(df, bins=48, value_area_pct=0.70):

    """

    Volume Profile aproximado usando OHLCV.

    Calcula POC, VAH, VAL, HVN y LVN.

    """

    if df is None or df.empty or len(df) < 50:

        return None

    d = df.copy().dropna(subset=["high", "low", "close", "volume"])

    if d.empty:

        return None

    price_min = float(d["low"].min())

    price_max = float(d["high"].max())

    if price_max <= price_min:

        return None

    bin_edges = np.linspace(price_min, price_max, bins + 1)

    volume_by_bin = np.zeros(bins)

    for _, row in d.iterrows():

        high = float(row["high"])

        low = float(row["low"])

        volume = float(row["volume"])

        if high <= low or volume <= 0:

            continue

        touched_bins = np.where((bin_edges[:-1] <= high) & (bin_edges[1:] >= low))[0]

        if len(touched_bins) == 0:

            continue

        volume_share = volume / len(touched_bins)

        for b in touched_bins:

            volume_by_bin[b] += volume_share

    if volume_by_bin.sum() <= 0:

        return None

    bin_centers = (bin_edges[:-1] + bin_edges[1:]) / 2

    poc_idx = int(np.argmax(volume_by_bin))

    poc = float(bin_centers[poc_idx])

    total_volume = volume_by_bin.sum()

    target_volume = total_volume * value_area_pct

    selected = {poc_idx}

    accumulated = volume_by_bin[poc_idx]

    left = poc_idx - 1

    right = poc_idx + 1

    while accumulated < target_volume and (left >= 0 or right < bins):

        left_vol = volume_by_bin[left] if left >= 0 else -1

        right_vol = volume_by_bin[right] if right < bins else -1

        if right_vol >= left_vol:

            selected.add(right)

            accumulated += right_vol

            right += 1

        else:

            selected.add(left)

            accumulated += left_vol

            left -= 1

    selected_prices = [bin_centers[i] for i in selected]

    vah = float(max(selected_prices))

    val = float(min(selected_prices))

    avg_vol = volume_by_bin.mean()

    hvn = []

    lvn = []

    for i, vol in enumerate(volume_by_bin):

        price_level = float(bin_centers[i])

        if vol >= avg_vol * 1.40:

            hvn.append(price_level)

        if vol <= avg_vol * 0.45:

            lvn.append(price_level)

    current_price = float(d["close"].iloc[-1])

    if current_price > vah:

        estado = "Precio arriba del Value Area"

        lectura = "Mercado aceptando precios altos. Buscar continuación si sostiene sobre VAH."

    elif current_price < val:

        estado = "Precio debajo del Value Area"

        lectura = "Mercado debajo del área de valor. Puede buscar VAL/POC si recupera."

    elif abs(current_price - poc) <= (price_max - price_min) / bins:

        estado = "Precio cerca del POC"

        lectura = "Zona de mayor aceptación. Cuidado con rango/chop."

    else:

        estado = "Precio dentro del Value Area"

        lectura = "Mercado en zona de equilibrio. Esperar ruptura o rechazo claro."

    return {

        "poc": poc,

        "vah": vah,

        "val": val,

        "hvn": hvn[:5],

        "lvn": lvn[:5],

        "estado": estado,

        "lectura": lectura,

        "current_price": current_price,

        "bin_centers": bin_centers,

        "volume_by_bin": volume_by_bin,

    }

def detect_order_blocks(df, lookback=120, impulse_atr=1.2):
    """
    Detecta Order Blocks simples:
    - Bullish OB: última vela bajista antes de impulso alcista.
    - Bearish OB: última vela alcista antes de impulso bajista.
    """
    if df is None or df.empty or len(df) < 30:
        return pd.DataFrame()
    d = df.tail(lookback).copy().reset_index(drop=True)
    obs = []
    for i in range(3, len(d) - 3):
        candle = d.iloc[i]
        next1 = d.iloc[i + 1]
        next2 = d.iloc[i + 2]
        atr = safe_float(candle.get("atr", np.nan), np.nan)
        if pd.isna(atr) or atr <= 0:
            continue
        impulso_alcista = (
            next1["close"] > next1["open"]
            and next2["close"] > candle["high"]
            and (next2["high"] - candle["low"]) >= atr * impulse_atr
        )
        impulso_bajista = (
            next1["close"] < next1["open"]
            and next2["close"] < candle["low"]
            and (candle["high"] - next2["low"]) >= atr * impulse_atr
        )
        if candle["close"] < candle["open"] and impulso_alcista:
            obs.append({
                "tipo": "BULLISH_OB",
                "direction": "LONG",
                "time": candle["time"],
                "low": float(candle["low"]),
                "high": float(candle["high"]),
                "mid": float((candle["low"] + candle["high"]) / 2),
                "mitigated": False,
            })
        if candle["close"] > candle["open"] and impulso_bajista:
            obs.append({
                "tipo": "BEARISH_OB",
                "direction": "SHORT",
                "time": candle["time"],
                "low": float(candle["low"]),
                "high": float(candle["high"]),
                "mid": float((candle["low"] + candle["high"]) / 2),
                "mitigated": False,
            })
    out = pd.DataFrame(obs)
    if out.empty:
        return out
    for idx, ob in out.iterrows():
        future = d[d["time"] > ob["time"]]
        if future.empty:
            continue
        if ob["direction"] == "LONG":
            mitigated = (future["low"] <= ob["mid"]).any()
        else:
            mitigated = (future["high"] >= ob["mid"]).any()
        out.at[idx, "mitigated"] = bool(mitigated)
    return out.sort_values("time").reset_index(drop=True)

def detect_liquidity_profile(df, lookback=120, tolerance_atr=0.18):
    """
    Detecta perfil de liquidez:
    - Equal Highs
    - Equal Lows
    - Barridos
    - Liquidez pendiente
    """
    if df is None or df.empty or len(df) < 40:
        return pd.DataFrame()
    d = df.tail(lookback).copy().reset_index(drop=True)
    atr = safe_float(d["atr"].iloc[-1], np.nan)
    if pd.isna(atr) or atr <= 0:
        atr = float((d["high"] - d["low"]).rolling(14).mean().iloc[-1])
    tolerance = atr * tolerance_atr
    rows = []
    # Equal Highs / Equal Lows
    for i in range(5, len(d) - 5):
        level_high = float(d["high"].iloc[i])
        level_low = float(d["low"].iloc[i])
        nearby_highs = d[
            (d.index != i) &
            (abs(d["high"] - level_high) <= tolerance)
        ]
        nearby_lows = d[
            (d.index != i) &
            (abs(d["low"] - level_low) <= tolerance)
        ]
        if len(nearby_highs) >= 2:
            rows.append({
                "tipo": "EQUAL_HIGHS",
                "direction": "SHORT",
                "nivel": level_high,
                "time": d["time"].iloc[i],
                "estado": "PENDIENTE",
                "motivo": "Liquidez superior acumulada"
            })
        if len(nearby_lows) >= 2:
            rows.append({
                "tipo": "EQUAL_LOWS",
                "direction": "LONG",
                "nivel": level_low,
                "time": d["time"].iloc[i],
                "estado": "PENDIENTE",
                "motivo": "Liquidez inferior acumulada"
            })
    out = pd.DataFrame(rows)
    if out.empty:
        return out
    # Sacar duplicados por nivel cercano
    out["nivel_round"] = (out["nivel"] / tolerance).round() * tolerance
    out = out.drop_duplicates(subset=["tipo", "nivel_round"], keep="last").copy()
    # Detectar barridos
    current_price = float(d["close"].iloc[-1])
    for idx, row in out.iterrows():
        future = d[d["time"] > row["time"]]
        if future.empty:
            continue
        if row["tipo"] == "EQUAL_HIGHS":
            swept = ((future["high"] > row["nivel"]) & (future["close"] < row["nivel"])).any()
        else:
            swept = ((future["low"] < row["nivel"]) & (future["close"] > row["nivel"])).any()
        if swept:
            out.at[idx, "estado"] = "BARRIDO"
            out.at[idx, "motivo"] = "Liquidez barrida con rechazo"
    out["distancia_pts"] = abs(out["nivel"] - current_price)
    out["distancia_atr"] = out["distancia_pts"] / atr
    return out.sort_values(["estado", "distancia_atr"]).reset_index(drop=True)

def detect_institutional_volume(df, lookback=120, vol_mult=1.8, range_mult=1.4):
    """
    Detecta velas institucionales:
    - volumen anormal
    - rango grande
    - ruptura de máximo/mínimo reciente
    """
    if df is None or df.empty or len(df) < 50:
        return pd.DataFrame()
    d = df.tail(lookback).copy().reset_index(drop=True)
    d["range"] = d["high"] - d["low"]
    d["range_ma20"] = d["range"].rolling(20).mean()
    d["vol_ma20"] = d["volume"].rolling(20).mean()
    rows = []
    for i in range(25, len(d)):
        row = d.iloc[i]
        prev = d.iloc[:i]
        vol_ok = row["volume"] >= row["vol_ma20"] * vol_mult if row["vol_ma20"] > 0 else False
        range_ok = row["range"] >= row["range_ma20"] * range_mult if row["range_ma20"] > 0 else False
        break_up = row["close"] > prev["high"].tail(20).max()
        break_down = row["close"] < prev["low"].tail(20).min()
        if vol_ok and range_ok and break_up:
            rows.append({
                "time": row["time"],
                "tipo": "VOLUMEN_INSTITUCIONAL_ALCISTA",
                "direction": "LONG",
                "precio": float(row["close"]),
                "high": float(row["high"]),
                "low": float(row["low"]),
                "volume": float(row["volume"]),
                "vol_ratio": float(row["volume"] / row["vol_ma20"]),
                "range_ratio": float(row["range"] / row["range_ma20"]),
                "motivo": "Volumen anormal + rango grande + ruptura alcista válida"
            })
        if vol_ok and range_ok and break_down:
            rows.append({
                "time": row["time"],
                "tipo": "VOLUMEN_INSTITUCIONAL_BAJISTA",
                "direction": "SHORT",
                "precio": float(row["close"]),
                "high": float(row["high"]),
                "low": float(row["low"]),
                "volume": float(row["volume"]),
                "vol_ratio": float(row["volume"] / row["vol_ma20"]),
                "range_ratio": float(row["range"] / row["range_ma20"]),
                "motivo": "Volumen anormal + rango grande + ruptura bajista válida"
            })
    return pd.DataFrame(rows).sort_values("time").reset_index(drop=True) if rows else pd.DataFrame()

def add_volume_delta(df):
    """
    Delta estimado con OHLCV.
    No es delta real de orderflow, pero aproxima presión compradora/vendedora.
    """
    if df is None or df.empty:
        return df
    d = df.copy()
    candle_range = (d["high"] - d["low"]).replace(0, np.nan)
    body = d["close"] - d["open"]
    d["delta_ratio"] = body / candle_range
    d["delta_ratio"] = d["delta_ratio"].clip(-1, 1).fillna(0)
    d["volume_delta"] = d["volume"] * d["delta_ratio"]
    d["buy_volume_est"] = np.where(d["volume_delta"] > 0, d["volume_delta"], 0)
    d["sell_volume_est"] = np.where(d["volume_delta"] < 0, abs(d["volume_delta"]), 0)
    d["delta_ma20"] = d["volume_delta"].rolling(20).mean()
    d["delta_abs_ma20"] = d["volume_delta"].abs().rolling(20).mean()
    d["delta_strength"] = d["volume_delta"] / d["delta_abs_ma20"].replace(0, np.nan)
    d["delta_strength"] = d["delta_strength"].replace([np.inf, -np.inf], np.nan).fillna(0)
    return d
# =========================
# BACKTEST / ESTADISTICAS / MONTE CARLO
# =========================

def outcome_from_future(future_df, direction, sl, tp, rr_value):
    if future_df.empty or pd.isna(sl) or pd.isna(tp):
        return "SIN_DATOS", 0.0
    for _, row in future_df.iterrows():
        if direction == "LONG":
            hit_sl, hit_tp = row["low"] <= sl, row["high"] >= tp
        else:
            hit_sl, hit_tp = row["high"] >= sl, row["low"] <= tp
        if hit_sl and hit_tp:
            return "SL", -1.0
        if hit_tp:
            return "TP", rr_value if not pd.isna(rr_value) else rr_target
        if hit_sl:
            return "SL", -1.0
    return "NINGUNO", 0.0


def performance_stats(results):
    if results is None or results.empty or "resultado" not in results.columns:
        return {"operaciones": 0, "winrate": 0, "profit_factor": 0, "drawdown": 0, "expectancy": 0, "rr_promedio": 0}
    closed = results[results["resultado"].isin(["TP", "SL"])].copy()
    if closed.empty:
        return {"operaciones": 0, "winrate": 0, "profit_factor": 0, "drawdown": 0, "expectancy": 0, "rr_promedio": 0}
    closed["r_multiple"] = pd.to_numeric(closed["r_multiple"], errors="coerce").fillna(0)
    wins = closed[closed["resultado"] == "TP"]
    losses = closed[closed["resultado"] == "SL"]
    gross_profit, gross_loss = wins["r_multiple"].sum(), abs(losses["r_multiple"].sum())
    profit_factor = gross_profit / gross_loss if gross_loss > 0 else np.inf
    equity = closed["r_multiple"].cumsum()
    drawdown = (equity - equity.cummax()).min()
    return {
        "operaciones": len(closed),
        "winrate": (len(wins) / len(closed)) * 100,
        "profit_factor": profit_factor,
        "drawdown": drawdown,
        "expectancy": closed["r_multiple"].mean(),
        "rr_promedio": wins["r_multiple"].mean() if len(wins) else 0,
    }


def stats_by_strategy(df):
    if df is None or df.empty or "estrategia" not in df.columns:
        return pd.DataFrame()
    rows = []
    for strat, group in df.groupby("estrategia"):
        s = performance_stats(group)
        rows.append({"estrategia": strat, "operaciones": s["operaciones"], "winrate_%": round(s["winrate"], 1), "profit_factor": np.inf if s["profit_factor"] == np.inf else round(s["profit_factor"], 2), "drawdown_R": round(s["drawdown"], 2), "expectativa_R": round(s["expectancy"], 2)})
    out = pd.DataFrame(rows)
    if not out.empty:
        out = out.sort_values(["expectativa_R", "profit_factor", "winrate_%"], ascending=False)
        out.insert(0, "ranking", range(1, len(out) + 1))
    return out


def last_30_days_stats(df):
    if df is None or df.empty or "fecha" not in df.columns:
        return performance_stats(pd.DataFrame()), pd.DataFrame()
    h = df.copy()
    h["fecha_dt"] = pd.to_datetime(h["fecha"], utc=True, errors="coerce")
    cutoff = pd.Timestamp.utcnow() - pd.Timedelta(days=30)
    h30 = h[h["fecha_dt"] >= cutoff]
    return performance_stats(h30), h30


@st.cache_data(ttl=300, show_spinner=False)
def run_simple_backtest(timeframe, period_label, estrategia, min_score, rr_target, min_rr, max_atr_multiplier, use_time_filter, avoid_weekends_filter, fvg_min_atr_param, fvg_max_distance_atr_param, use_fvg_filter_param):
    months_map = {"3 meses": 3, "6 meses": 6, "1 año": 12}
    df = add_indicators(get_ohlcv(timeframe, limit=BACKTEST_LIMIT))
    if df.empty or len(df) < 260:
        return pd.DataFrame(), {}
    cutoff = df["time"].max() - pd.DateOffset(months=months_map[period_label])
    df = df[df["time"] >= cutoff].reset_index(drop=True)
    rows = []
    step = 4 if timeframe == "15m" else 12
    horizon = 96 if timeframe == "15m" else 288
    for i in range(220, len(df) - horizon, step):
        hist = df.iloc[:i + 1].copy()
        df_5_bt = hist
        df_15_bt = hist if timeframe == "15m" else add_indicators(resample_ohlcv(hist, "15min"))
        df_1h_bt = add_indicators(resample_ohlcv(hist, "1h"))
        df_4h_bt = add_indicators(resample_ohlcv(hist, "4h"))
        df_1d_bt = add_indicators(resample_ohlcv(hist, "1d"))
        if len(df_1h_bt) < 210 or len(df_4h_bt) < 60 or len(df_15_bt) < 210 or len(df_1d_bt) < 2:
            continue
        levels_bt = liquidity_levels(df_15_bt)
        fvg_bt = detect_fvg_zones(df_15_bt, fvg_min_atr_param, 120)
        price_bt = df_5_bt["close"].iloc[-1]
        structure_bt = structure_state(df_5_bt)
        long_score_bt = score_direction("LONG", df_4h_bt, df_1h_bt, df_15_bt, df_5_bt, levels_bt, fvg_bt, fvg_max_distance_atr_param)
        short_score_bt = score_direction("SHORT", df_4h_bt, df_1h_bt, df_15_bt, df_5_bt, levels_bt, fvg_bt, fvg_max_distance_atr_param)
        escenario_bt, market_bias_bt = detect_market_intention(price_bt, df_4h_bt, df_1h_bt, df_15_bt, levels_bt)
        direction_bt = choose_candidate_direction(estrategia, long_score_bt, short_score_bt, trend_state(df_1d_bt), trend_state(df_4h_bt), structure_bt, price_bt, df_15_bt, df_5_bt, levels_bt, fvg_bt)
        fvg_zone_bt = nearest_fvg(price_bt, fvg_bt, direction_bt, True)
        sl_bt, tp_bt, risk_points_bt = technical_levels(direction_bt, df_5_bt, price_bt, rr_target, fvg_zone_bt)
        rr_bt = calculate_rr(price_bt, sl_bt, tp_bt, direction_bt)
        valid_bt, motivos_bt = validate_trade(estrategia, direction_bt, long_score_bt, short_score_bt, min_score, 0.01, rr_bt, min_rr, risk_points_bt, df_15_bt["atr"].iloc[-1], market_bias_bt, structure_bt, price_bt, levels_bt, max_atr_multiplier, df_15_bt, df_5_bt, use_time_filter, avoid_weekends_filter, fvg_bt, use_fvg_filter_param, fvg_max_distance_atr_param, df_1h_bt)
        if not valid_bt:
            continue
        future = df.iloc[i + 1:i + 1 + horizon]
        result, r_mult = outcome_from_future(future, direction_bt, sl_bt, tp_bt, rr_bt)
        rows.append({"fecha": df_5_bt["time"].iloc[-1], "estrategia": estrategia, "direccion": direction_bt, "entrada": price_bt, "sl": sl_bt, "tp": tp_bt, "rr": rr_bt, "long_score": long_score_bt, "short_score": short_score_bt, "resultado": result, "r_multiple": r_mult, "escenario": escenario_bt, "fvg": fvg_zone_bt.get("tipo") if fvg_zone_bt else "SIN_FVG", "motivos": " | ".join(motivos_bt)})
    res = pd.DataFrame(rows)
    return res, performance_stats(res)


def validate_saved_signals(historial, current_df_5m, hours_after=24):
    if historial is None or historial.empty:
        return historial
    h = historial.copy()
    if "resultado" not in h.columns:
        h["resultado"] = ""
    else:
        h["resultado"] = h["resultado"].astype(str)
    if "r_multiple" not in h.columns:
        h["r_multiple"] = np.nan
    if "validado_hasta" not in h.columns:
        h["validado_hasta"] = ""
    else:
        h["validado_hasta"] = h["validado_hasta"].astype(str)
    now_utc = current_df_5m["time"].max()
    for idx, row in h.iterrows():
        if str(row.get("resultado", "nan")) in ["TP", "SL", "NINGUNO", "NO_OPERAR"]:
            continue
        fecha = pd.to_datetime(row.get("fecha"), utc=True, errors="coerce")
        if pd.isna(fecha) or now_utc < fecha + pd.Timedelta(hours=hours_after):
            continue
        direction = row.get("direccion_calculada", row.get("decision", ""))
        if direction not in ["LONG", "SHORT"]:
            h.at[idx, "resultado"] = "NO_OPERAR"
            h.at[idx, "r_multiple"] = 0.0
            continue
        try:
            sl, tp = float(row["sl"]), float(row["tp"])
        except Exception:
            continue
        future = current_df_5m[(current_df_5m["time"] > fecha) & (current_df_5m["time"] <= fecha + pd.Timedelta(hours=hours_after))]
        rr_value = pd.to_numeric(row.get("rr_real", np.nan), errors="coerce")
        result, r_mult = outcome_from_future(future, direction, sl, tp, rr_value)
        h.at[idx, "resultado"] = result
        h.at[idx, "r_multiple"] = r_mult
        h.at[idx, "validado_hasta"] = (fecha + pd.Timedelta(hours=hours_after)).strftime("%Y-%m-%d %H:%M:%S")
    return h


def max_drawdown_pct(equity_curve):
    eq = np.asarray(equity_curve, dtype=float)
    if len(eq) == 0:
        return 0.0
    peak = np.maximum.accumulate(eq)
    dd = (peak - eq) / np.where(peak == 0, np.nan, peak)
    return float(np.nanmax(dd) * 100) if len(dd) else 0.0


def max_losing_streak(r_values):
    max_streak = 0
    streak = 0
    for r in r_values:
        if r < 0:
            streak += 1
            max_streak = max(max_streak, streak)
        else:
            streak = 0
    return max_streak


@st.cache_data(ttl=300, show_spinner=False)
def monte_carlo_simulation(r_multiples_tuple, account_usd, risk_pct, paths=5000, horizon=50, ruin_dd_pct=30.0, seed=42):
    rng = np.random.default_rng(seed)
    r_multiples = np.array(r_multiples_tuple, dtype=float)
    r_multiples = r_multiples[np.isfinite(r_multiples)]
    if len(r_multiples) == 0:
        r_multiples = np.array([-1.0, 2.0])
    paths = int(paths)
    horizon = int(horizon)
    all_dd = np.zeros(paths)
    final_equity = np.zeros(paths)
    max_loss_streaks = np.zeros(paths)
    ruin_hits = np.zeros(paths, dtype=bool)
    sample_curves = []
    for p in range(paths):
        sampled_r = rng.choice(r_multiples, size=horizon, replace=True)
        pnl = sampled_r * (account_usd * risk_pct)
        equity = account_usd + np.cumsum(pnl)
        all_dd[p] = max_drawdown_pct(equity)
        final_equity[p] = equity[-1]
        max_loss_streaks[p] = max_losing_streak(sampled_r)
        ruin_hits[p] = all_dd[p] >= ruin_dd_pct or equity.min() <= account_usd * (1 - ruin_dd_pct / 100)
        if p < 30:
            sample_curves.append(equity)
    summary = {
        "paths": paths,
        "horizon": horizon,
        "start_capital": account_usd,
        "risk_pct": risk_pct,
        "dd_median": float(np.percentile(all_dd, 50)),
        "dd_p75": float(np.percentile(all_dd, 75)),
        "dd_p95": float(np.percentile(all_dd, 95)),
        "dd_p99": float(np.percentile(all_dd, 99)),
        "final_median": float(np.percentile(final_equity, 50)),
        "final_p05": float(np.percentile(final_equity, 5)),
        "final_p95": float(np.percentile(final_equity, 95)),
        "ruin_probability": float(np.mean(ruin_hits) * 100),
        "loss_streak_median": float(np.percentile(max_loss_streaks, 50)),
        "loss_streak_p95": float(np.percentile(max_loss_streaks, 95)),
        "loss_streak_p99": float(np.percentile(max_loss_streaks, 99)),
        "dd_values": all_dd,
        "final_equity": final_equity,
        "sample_curves": sample_curves,
    }
    return summary


def build_r_multiples_from_sources(bt_results, combined_hist, use_backtest, manual_wr, manual_rr):
    source = "manual"
    r_values = []
    if use_backtest and bt_results is not None and not bt_results.empty and "r_multiple" in bt_results.columns:
        closed = bt_results[bt_results["resultado"].isin(["TP", "SL"])].copy()
        if len(closed) >= 10:
            r_values = pd.to_numeric(closed["r_multiple"], errors="coerce").dropna().tolist()
            source = "backtest"
    if not r_values and combined_hist is not None and not combined_hist.empty and "r_multiple" in combined_hist.columns:
        closed = combined_hist[combined_hist["resultado"].isin(["TP", "SL"])].copy()
        if len(closed) >= 10:
            r_values = pd.to_numeric(closed["r_multiple"], errors="coerce").dropna().tolist()
            source = "historial real"
    if not r_values:
        wins = max(1, int(round(manual_wr)))
        losses = max(1, 100 - wins)
        r_values = [float(manual_rr)] * wins + [-1.0] * losses
        source = "manual"
    return tuple(float(x) for x in r_values if np.isfinite(x)), source


def signal_key(row):
    return f"{row['vela_5m']}_{row['estrategia']}_{row['decision']}_{row['direccion_calculada']}"


def direction_score(direction, long_score, short_score):
    return long_score if direction == "LONG" else short_score

# =========================
# MENSAJES ALERTA
# =========================

def build_valid_signal_msg(decision, symbol, estrategia, price, sl, tp, rr, quality_label, quality_score, long_score, short_score, rsi, atr, current_candle_time, fvg_label="", modo_operativo="Normal"):
    return f"""<b>BTC DASHBOARD PRO</b>

<b>SEÑAL VÁLIDA DETECTADA</b>

Dirección: <b>{display_direction(decision)}</b>
Par: {symbol}
Estrategia: {estrategia}
Modo: {modo_operativo}
Tipo: {"AGRESIVA" if modo_operativo in ["Agresivo", "Scalping agresivo"] else "NORMAL"}
FVG: {fvg_label}

Entrada: {fmt0(price)}
SL: {fmt0(sl)}
TP: {fmt0(tp)}

RR: {format_number(rr, 2)}
Setup: {quality_label} {quality_score}/10
Long Score: {long_score}/10
Short Score: {short_score}/10
RSI 15M: {format_number(rsi, 2)}
ATR 15M: {fmt0(atr)} pts

Vela 5M: {current_candle_time}
"""


def build_almost_msg(direction, symbol, estrategia, score, min_score, price, sl, tp, rr, long_score, short_score, rsi, motivos, current_candle_time, fvg_label=""):
    motivos_txt = "\n".join([f"- {m}" for m in motivos[:4]]) if motivos else "- Falta confirmación final del sistema."
    return f"""⚠️ <b>SETUP EN FORMACIÓN</b>

Dirección probable: <b>{display_direction(direction)}</b>
Par: {symbol}
Estrategia: {estrategia}
FVG: {fvg_label}

Score dirección: {score}/{min_score}
Long Score: {long_score}/10
Short Score: {short_score}/10
RSI 15M: {format_number(rsi, 2)}

Entrada teórica: {fmt0(price)}
SL: {fmt0(sl)}
TP: {fmt0(tp)}
RR: {format_number(rr, 2)}

Todavía NO es entrada.
Falta:
{motivos_txt}

Vela 5M: {current_candle_time}
"""


def build_bias_msg(symbol, market_bias, escenario, t4, t1, t15, t5, structure, price, rsi, current_candle_time):
    return f"""🔄 <b>CAMBIO DE SESGO BTC</b>

Par: {symbol}
Sesgo nuevo: <b>{display_direction(market_bias)}</b>
Escenario: {escenario}
Precio: {fmt0(price)}
4H: {trend_icon(t4)}
1H: {trend_icon(t1)}
15M: {trend_icon(t15)}
5M: {trend_icon(t5)}
Estructura 5M: {structure}
RSI 15M: {format_number(rsi, 2)}
Vela 5M: {current_candle_time}
"""


def build_risk_msg(symbol, direction, price, sl, tp, risk_points, tp_atr_multiple, rr, current_candle_time):
    return f"""⚠️ <b>ALERTA DE RIESGO / OBJETIVO EXIGENTE</b>

Par: {symbol}
Dirección: <b>{display_direction(direction)}</b>
Precio: {fmt0(price)}
SL: {fmt0(sl)}
TP: {fmt0(tp)}
Distancia SL: {fmt0(risk_points)} pts
TP en ATR: {format_number(tp_atr_multiple, 2)}
RR: {format_number(rr, 2)}
Vela 5M: {current_candle_time}
"""


def build_market_update_msg(color, decision, candidate_direction, symbol, estrategia, price, long_score, short_score, rsi, atr, t4, t1, t15, t5, structure, escenario, motivos, current_candle_time):
    if color == "GREEN":
        header = "🟢 <b>ALERTA VERDE — SETUP OPERABLE</b>"
        action = "Puede haber oportunidad válida según reglas."
    elif color == "RED":
        header = "🔴 <b>ALERTA ROJA — NO OPERAR / RIESGO ALTO</b>"
        action = "Mercado peligroso o condiciones débiles. Esperar."
    else:
        header = "🟡 <b>ALERTA AMARILLA — SETUP EN FORMACIÓN</b>"
        action = "Hay intención, pero todavía falta confirmación."
    motivos_txt = "\n".join([f"- {m}" for m in motivos[:5]]) if motivos else "- Sin bloqueos."
    return f"""{header}

Par: {symbol}
Estrategia: {estrategia}
Estado: <b>{display_direction(decision)}</b>
Dirección calculada: <b>{display_direction(candidate_direction)}</b>

Precio: {fmt0(price)}
Long Score: {long_score}/10
Short Score: {short_score}/10
RSI 15M: {format_number(rsi, 2)}
ATR 15M: {fmt0(atr)} pts

Tendencias:
4H: {trend_icon(t4)}
1H: {trend_icon(t1)}
15M: {trend_icon(t15)}
5M: {trend_icon(t5)}

Estructura 5M: {structure}
Escenario: {escenario}
Lectura: {action}

Bloqueos / detalles:
{motivos_txt}

Vela 5M: {current_candle_time}
"""

# =========================
# APP
# =========================

st.title("BTC/USDT FUTUROS")
init_open_trade_file()
st.caption("Sistema objetivo: tendencia + liquidez + estructura + score + riesgo + FVG + backtesting + Monte Carlo + alertas estratégicas. No es consejo financiero.")

# =========================
# TARJETA COMERCIAL / RESUMEN EJECUTIVO
# =========================
def render_executive_card(
    decision,
    candidate_direction,
    quality_label,
    quality_score,
    price,
    sl_calc,
    tp_calc,
    risk_usd,
    profit_usd,
    rr_real,
    long_score,
    short_score,
    fvg_label,
    trade_valid,
    motivos_bloqueo
):
    if decision == "LONG":
        status_icon = "🟢"
        status_text = "LONG PERMITIDO"
        status_class = "card-long"
    elif decision == "SHORT":
        status_icon = "🔴"
        status_text = "SHORT PERMITIDO"
        status_class = "card-short"
    else:
        status_icon = "⚪"
        status_text = f"NO OPERAR · Escenario {display_direction(candidate_direction)}"
        status_class = "card-neutral"
    confidence_pct = min(max((quality_score / 10) * 100, 0), 100)
    entrada_txt = f"{price:,.0f}" if not pd.isna(price) else "-"
    sl_txt = f"{sl_calc:,.0f}" if not pd.isna(sl_calc) else "-"
    tp_txt = f"{tp_calc:,.0f}" if not pd.isna(tp_calc) else "-"
    rr_txt = f"{rr_real:.2f}" if not pd.isna(rr_real) else "-"
    riesgo_txt = f"{risk_usd:.2f} USDT" if not pd.isna(risk_usd) else "-"
    profit_txt = f"+{profit_usd:.2f} USDT" if not pd.isna(profit_usd) else "-"
    motivos_html = ""
    if decision == "NO_OPERAR" and motivos_bloqueo:
        motivos_html = "<div class='motivos-card'><b>Bloqueos:</b><br>" + "<br>".join(
            [f"• {m}" for m in motivos_bloqueo[:4]]
        ) + "</div>"
    st.markdown(f"""
    <style>
    .executive-card {{
        border-radius: 22px;
        padding: 26px 28px;
        margin: 22px 0 28px 0;
        border: 1px solid rgba(0,0,0,0.08);
        box-shadow: 0 10px 30px rgba(0,0,0,0.06);
        background: linear-gradient(135deg, #ffffff 0%, #f8fafc 100%);
    }}
    .card-long {{ border-left: 10px solid #16a34a; }}
    .card-short {{ border-left: 10px solid #dc2626; }}
    .card-neutral {{ border-left: 10px solid #9ca3af; }}
    .exec-title {{
        font-size: 34px;
        font-weight: 800;
        margin-bottom: 8px;
        color: #1f2937;
    }}
    .exec-subtitle {{
        color: #6b7280;
        font-size: 15px;
        margin-bottom: 20px;
    }}
    .confidence-bar {{
        width: 100%;
        height: 14px;
        background: #e5e7eb;
        border-radius: 999px;
        overflow: hidden;
        margin: 10px 0 22px 0;
    }}
    .confidence-fill {{
        height: 100%;
        width: {confidence_pct}%;
        background: linear-gradient(90deg, #22c55e, #84cc16);
        border-radius: 999px;
    }}
    .exec-grid {{
        display: grid;
        grid-template-columns: repeat(4, 1fr);
        gap: 14px;
        margin-top: 16px;
    }}
    .exec-box {{
        background: white;
        border: 1px solid #eef2f7;
        border-radius: 16px;
        padding: 16px;
    }}
    .exec-label {{
        color: #6b7280;
        font-size: 13px;
        margin-bottom: 5px;
    }}
    .exec-value {{
        color: #111827;
        font-size: 22px;
        font-weight: 800;
    }}
    .motivos-card {{
        background: #fff7ed;
        border: 1px solid #fed7aa;
        color: #9a3412;
        border-radius: 16px;
        padding: 16px;
        margin-top: 18px;
        font-size: 15px;
    }}
    </style>
    <div class="executive-card {status_class}">
        <div class="exec-title">{status_icon} {status_text}</div>
        <div class="exec-subtitle">
            Asistente operativo BTC intradía · decisión, riesgo y niveles principales.
        </div>
        <div><b>Confianza:</b> {quality_score}/10 · {quality_label}</div>
        <div class="confidence-bar">
            <div class="confidence-fill"></div>
        </div>
        <div class="exec-grid">
            <div class="exec-box"><div class="exec-label">Entrada</div><div class="exec-value">{entrada_txt}</div></div>
            <div class="exec-box"><div class="exec-label">Stop Loss</div><div class="exec-value">{sl_txt}</div></div>
            <div class="exec-box"><div class="exec-label">Take Profit</div><div class="exec-value">{tp_txt}</div></div>
            <div class="exec-box"><div class="exec-label">RR real</div><div class="exec-value">{rr_txt}</div></div>
            <div class="exec-box"><div class="exec-label">Riesgo</div><div class="exec-value">{riesgo_txt}</div></div>
            <div class="exec-box"><div class="exec-label">Objetivo</div><div class="exec-value">{profit_txt}</div></div>
            <div class="exec-box"><div class="exec-label">Score LONG / SHORT</div><div class="exec-value">{long_score}/10 · {short_score}/10</div></div>
            <div class="exec-box"><div class="exec-label">FVG</div><div class="exec-value">{fvg_label}</div></div>
        </div>
        {motivos_html}
    </div>
    """, unsafe_allow_html=True)

def render_trading_assistant_card(
    decision,
    candidate_direction,
    quality_score,
    quality_label,
    escenario,
    price,
    rr_real,
    t4,
    t1,
    t15,
    t5,
    structure,
    fvg_label,
    delta_estado,
    delta_fuerza,
    vol_ratio_15m,
    motivos_bloqueo
):
    if candidate_direction == "LONG":
        tendencia_txt = "ALCISTA"
    elif candidate_direction == "SHORT":
        tendencia_txt = "BAJISTA"
    else:
        tendencia_txt = "NEUTRAL"
    if decision == "LONG":
        decision_txt = "🟢 LONG PERMITIDO"
        color = "#16a34a"
    elif decision == "SHORT":
        decision_txt = "🔴 SHORT PERMITIDO"
        color = "#dc2626"
    else:
        decision_txt = "⚪ NO OPERAR"
        color = "#6b7280"
    prob = min(max(int(quality_score * 10), 0), 100)
    if motivos_bloqueo:
        bloqueos_txt = "<br>".join([f"• {m}" for m in motivos_bloqueo[:4]])
    else:
        bloqueos_txt = "Sin bloqueos críticos."
    st.markdown(f"""
    <div style="
        border: 2px solid {color};
        border-radius: 22px;
        padding: 24px;
        margin: 20px 0;
        background: #ffffff;
        box-shadow: 0 8px 24px rgba(0,0,0,0.08);
        font-family: monospace;
    ">
        <div style="font-size:22px; font-weight:800; margin-bottom:12px;">
            ═══════════════════════════════<br>
            ESTADO DEL MERCADO BTC
        </div>
        <div style="font-size:17px; line-height:1.9;">
            Tendencia: <b>{tendencia_txt}</b> ✅<br>
            Contexto: <b>{escenario}</b><br>
            Precio: <b>{price:,.0f}</b><br>
            Estructura 5M: <b>{structure}</b><br>
            4H / 1H / 15M / 5M: <b>{t4}</b> · <b>{t1}</b> · <b>{t15}</b> · <b>{t5}</b><br>
            FVG: <b>{fvg_label}</b><br>
            Delta: <b>{delta_estado}</b> · fuerza <b>{delta_fuerza}</b><br>
            Volumen relativo: <b>{vol_ratio_15m:.2f}x</b><br>
            RR disponible: <b>{rr_real:.2f}</b><br>
            Probabilidad estimada: <b>{prob}%</b><br>
            Calidad: <b>{quality_label}</b> · <b>{quality_score}/10</b>
        </div>
        <hr>
        <div style="font-size:24px; font-weight:900; color:{color};">
            DECISIÓN: {decision_txt}
        </div>
        <div style="margin-top:12px; color:#92400e; font-size:14px;">
            <b>Bloqueos / advertencias:</b><br>
            {bloqueos_txt}
        </div>
        <div style="font-size:22px; font-weight:800; margin-top:16px;">
            ═══════════════════════════════
        </div>
    </div>
    """, unsafe_allow_html=True)

try:
    df_1d, df_4h, df_1h, df_15m, df_5m = load_all_data()
    
    levels = liquidity_levels(df_15m)
    ob_df = detect_order_blocks(df_15m, lookback=120, impulse_atr=1.2)
    liq_profile_df = detect_liquidity_profile(df_15m, lookback=120, tolerance_atr=0.18)
    inst_vol_df = detect_institutional_volume(df_15m, lookback=120, vol_mult=1.8, range_mult=1.4)
    volume_profile = volume_profile_pro(df_15m.tail(120), bins=48)
    price = df_5m["close"].iloc[-1]
    current_candle_time = df_5m["time"].iloc[-1].strftime("%Y-%m-%d %H:%M:%S")

    t1d, t4, t1, t15, t5 = trend_state(df_1d), trend_state(df_4h), trend_state(df_1h), trend_state(df_15m), trend_state(df_5m)
    fvg_df = detect_fvg_zones(
        df_15m,
        min_atr_mult=fvg_min_atr,
        lookback=120,
        trend_filter=t15
    )
    rsi_15 = df_15m["rsi"].iloc[-1]
    rsi_label = rsi_state(rsi_15)
    atr_15m = df_15m["atr"].iloc[-1]
    structure = structure_state(df_5m)
    long_score = score_direction("LONG", df_4h, df_1h, df_15m, df_5m, levels, fvg_df, fvg_max_distance_atr)
    short_score = score_direction("SHORT", df_4h, df_1h, df_15m, df_5m, levels, fvg_df, fvg_max_distance_atr)
    escenario, market_bias = detect_market_intention(price, df_4h, df_1h, df_15m, levels)
    candidate_direction = choose_candidate_direction(estrategia, long_score, short_score, t1d, t4, structure, price, df_15m, df_5m, levels, fvg_df)

    fvg_label, fvg_zone, fvg_distance_atr, fvg_valid = fvg_state(price, atr_15m, fvg_df, candidate_direction, fvg_max_distance_atr)
    sl_calc, tp_calc, risk_points_calc = technical_levels(candidate_direction, df_5m, price, rr_target, fvg_zone,modo_operativo)
    tp_distance_calc = abs(tp_calc - price) if not pd.isna(tp_calc) else np.nan
    tp_atr_multiple = tp_distance_calc / atr_15m if not pd.isna(tp_distance_calc) and not pd.isna(atr_15m) and atr_15m > 0 else np.nan
    rr_real = calculate_rr(price, sl_calc, tp_calc, candidate_direction)
    rr_real = calculate_rr(price, sl_calc, tp_calc, candidate_direction)
    if modo_operativo == "Scalp 15M":
        objetivo_exigente = (
            not pd.isna(tp_atr_multiple)
            and tp_atr_multiple > 1.5
        )
        scalping_no_recomendado = (
            not pd.isna(tp_atr_multiple)
            and tp_atr_multiple > 1.2
        )
    else:
        objetivo_exigente = (
            not pd.isna(tp_atr_multiple)
            and tp_atr_multiple >= 4
        )
        scalping_no_recomendado = (
            not pd.isna(tp_atr_multiple)
            and tp_atr_multiple >= 3
        )
    trade_valid, motivos_bloqueo = validate_trade(
            estrategia, candidate_direction, long_score, short_score, min_score, risk_pct, rr_real, min_rr,
            risk_points_calc, atr_15m, market_bias, structure, price, levels, max_atr_multiplier,
            df_15m, df_5m, filter_hours, avoid_weekends,
            fvg_df, use_fvg_filter, fvg_max_distance_atr, df_1h
        )
    decision = candidate_direction if trade_valid else "NO_OPERAR"
    

    btc_size, notional, risk_usd, margin_needed, risk_usd_target, notional_capped, max_notional = position_size(price, sl_calc, account_usd, risk_pct, leverage)
    profit_usd = risk_usd * rr_target
    profit_pct = (profit_usd / account_usd) * 100 if account_usd else 0
    quality_score, quality_label, quality_detail = evaluar_setup_pro(

        direction=candidate_direction,

        long_score=long_score,

        short_score=short_score,

        rr_real=rr_real,

        risk_points=risk_points_calc,

        atr_15m=atr_15m,

        tp_atr_multiple=tp_atr_multiple,

        fvg_valid=fvg_valid,

        fvg_label=fvg_label,

        t1d=t1d,

        t4=t4,

        t1=t1,

        t15=t15,

        t5=t5,

        structure=structure,

        price=price,

        df_15m=df_15m,

        df_5m=df_5m,

        levels=levels,

        trade_valid=trade_valid,

        motivos_bloqueo=motivos_bloqueo,

        use_time_filter=filter_hours,

        avoid_weekends_filter=avoid_weekends,

    )
    raw_direction_score = direction_score(candidate_direction, long_score, short_score)
    
    if delta_15m > 0:
        delta_estado = "🟢 Delta comprador"
    elif delta_15m < 0:
        delta_estado = "🔴 Delta vendedor"
    else:
        delta_estado = "⚪ Delta neutro"
    if abs(delta_strength_15m) >= 1.5:
        delta_fuerza = "Fuerte"
    elif abs(delta_strength_15m) >= 0.8:
        delta_fuerza = "Normal"
    else:
        delta_fuerza = "Débil"

    render_trading_assistant_card(
        decision=decision,
        candidate_direction=candidate_direction,
        quality_score=quality_score,
        quality_label=quality_label,
        escenario=escenario,
        price=price,
        rr_real=rr_real,
        t4=t4,
        t1=t1,
        t15=t15,
        t5=t5,
        structure=structure,
        fvg_label=fvg_label,
        delta_estado=delta_estado,
        delta_fuerza=delta_strength_15m,
        vol_ratio_15m=vol_ratio_15m,
        motivos_bloqueo=motivos_bloqueo
    )

    render_executive_card(
        decision=decision,
        candidate_direction=candidate_direction,
        quality_label=quality_label,
        quality_score=quality_score,
        price=price,
        sl_calc=sl_calc,
        tp_calc=tp_calc,
        risk_usd=risk_usd,
        profit_usd=profit_usd,
        rr_real=rr_real,
        long_score=long_score,
        short_score=short_score,
        fvg_label=fvg_label,
        trade_valid=trade_valid,
        motivos_bloqueo=motivos_bloqueo
    )

    current_signal_row = {
        "fecha": datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S"),
        "vela_5m": current_candle_time,
        "estrategia": estrategia,
        "modo_operativo": modo_operativo,
        "decision": decision,
        "direccion_calculada": candidate_direction,
        "calidad_setup": quality_label,
        "calidad_score": quality_score,
        "escenario": escenario,
        "precio": price,
        "long_score": long_score,
        "short_score": short_score,
        "rsi_15m": rsi_15,
        "atr_15m": atr_15m,
        "fvg_estado": fvg_label,
        "fvg_tipo": fvg_zone.get("tipo") if fvg_zone else "SIN_FVG",
        "fvg_low": fvg_zone.get("low") if fvg_zone else np.nan,
        "fvg_high": fvg_zone.get("high") if fvg_zone else np.nan,
        "fvg_mid": fvg_zone.get("mid") if fvg_zone else np.nan,
        "fvg_dist_atr": fvg_distance_atr,
        "distancia_sl_pts": risk_points_calc,
        "distancia_tp_pts": tp_distance_calc,
        "tp_atr_multiple": tp_atr_multiple,
        "cuenta_usdt": account_usd,
        "riesgo_pct": risk_pct_input,
        "riesgo_usdt_objetivo": risk_usd_target,
        "riesgo_usdt_real": risk_usd,
        "notional_max": max_notional,
        "notional_real": notional,
        "notional_capado": notional_capped,
        "ganancia_tp_usdt": profit_usd,
        "entrada": price,
        "sl": sl_calc,
        "tp": tp_calc,
        "rr_real": rr_real,
        "resultado": np.nan,
        "r_multiple": np.nan,
        "validado_hasta": np.nan,
        "24h": t1d,
        "4h": t4,
        "1h": t1,
        "15m": t15,
        "5m": t5,
        "estructura": structure,
        "motivos_bloqueo": " | ".join(motivos_bloqueo),
    }

    valid_msg = build_valid_signal_msg(decision, SYMBOL, estrategia, price, sl_calc, tp_calc, rr_real, quality_label, quality_score, long_score, short_score, rsi_15, atr_15m, current_candle_time, fvg_label, modo_operativo)
    almost_msg = build_almost_msg(candidate_direction, SYMBOL, estrategia, raw_direction_score, min_score, price, sl_calc, tp_calc, rr_real, long_score, short_score, rsi_15, motivos_bloqueo, current_candle_time, fvg_label)
    bias_msg = build_bias_msg(SYMBOL, market_bias, escenario, t4, t1, t15, t5, structure, price, rsi_15, current_candle_time)
    risk_msg = build_risk_msg(SYMBOL, candidate_direction, price, sl_calc, tp_calc, risk_points_calc, tp_atr_multiple, rr_real, current_candle_time)

    if trade_valid:
        market_color = "GREEN"
    elif candidate_direction in ["LONG", "SHORT"] and raw_direction_score >= max(1, min_score - almost_score_gap):
        market_color = "YELLOW"
    else:
        market_color = "RED"
    market_update_msg = build_market_update_msg(market_color, decision, candidate_direction, SYMBOL, estrategia, price, long_score, short_score, rsi_15, atr_15m, t4, t1, t15, t5, structure, escenario, motivos_bloqueo, current_candle_time)

    auto_saved_now = False
    alert_events = []

    if alert_market_updates and telegram_enabled:
        minute_now = datetime.utcnow().minute
        interval = int(market_update_minutes)
        bucket_minute = (minute_now // interval) * interval
        market_update_key = f"MARKET_UPDATE_{datetime.utcnow().strftime('%Y-%m-%d_%H')}_{bucket_minute:02d}"
        if minute_now % interval == 0:
            ok, resp = send_alert_once(market_update_key, f"market_update_{interval}min", market_update_msg, telegram_enabled, discord_enabled, discord_webhook_url, telegram_bot_token, telegram_chat_id)
            if ok:
                alert_events.append(f"📡 Resumen de mercado enviado a Telegram cada {interval} min.")

    if auto_capture_enabled and trade_valid:
        auto_df = safe_read_csv(AUTO_SIGNALS_FILE)
        row_auto = current_signal_row.copy()
        row_auto["signal_key"] = signal_key(row_auto)
        existing_keys = set(auto_df["signal_key"].astype(str)) if "signal_key" in auto_df.columns else set()
        if row_auto["signal_key"] not in existing_keys:
            save_signal_row(AUTO_SIGNALS_FILE, row_auto)
            auto_saved_now = True

    if alert_valid_signals and trade_valid:
        valid_key = f"VALID_{signal_key(current_signal_row)}"
        ok, resp = send_alert_once(valid_key, "señal_valida", valid_msg, telegram_enabled, discord_enabled, discord_webhook_url, telegram_bot_token, telegram_chat_id)
        if ok:
            alert_events.append("🚨 Señal válida enviada por alerta.")

    almost_condition = (
        alert_almost_setups and not trade_valid and candidate_direction in ["LONG", "SHORT"]
        and raw_direction_score >= max(1, min_score - almost_score_gap)
        and long_score != short_score and not pd.isna(rr_real) and rr_real >= min_rr
        and not pd.isna(risk_points_calc) and not pd.isna(atr_15m)
        and risk_points_calc <= atr_15m * max_atr_multiplier
    )
    if almost_condition:
        almost_key = f"ALMOST_{current_candle_time}_{estrategia}_{candidate_direction}_{raw_direction_score}_{min_score}_{fvg_label}"
        ok, resp = send_alert_once(almost_key, "setup_en_formacion", almost_msg, telegram_enabled, discord_enabled, discord_webhook_url, telegram_bot_token, telegram_chat_id)
        if ok:
            alert_events.append("⚠️ Setup en formación enviado.")

    current_state_key = f"{market_bias}_{t4}_{t1}_{t15}_{t5}_{structure}_{fvg_label}"
    previous_state_key = load_market_state()
    if alert_bias_change and previous_state_key and previous_state_key != current_state_key:
        bias_key = f"BIAS_{current_candle_time}_{current_state_key}"
        ok, resp = send_alert_once(bias_key, "cambio_sesgo", bias_msg, telegram_enabled, discord_enabled, discord_webhook_url, telegram_bot_token, telegram_chat_id)
        if ok:
            alert_events.append("🔄 Cambio de sesgo enviado.")
    if previous_state_key != current_state_key:
        save_market_state(current_state_key)

    risk_warning_condition = (
        alert_risk_warning and candidate_direction in ["LONG", "SHORT"]
        and not pd.isna(tp_atr_multiple) and tp_atr_multiple >= 4
        and not pd.isna(risk_points_calc) and not pd.isna(atr_15m)
        and risk_points_calc >= atr_15m * max_atr_multiplier
    )
    if risk_warning_condition:
        risk_key = f"RISK_{current_candle_time}_{estrategia}_{candidate_direction}_{round(float(tp_atr_multiple), 1)}"
        ok, resp = send_alert_once(risk_key, "riesgo_objetivo_exigente", risk_msg, telegram_enabled, discord_enabled, discord_webhook_url, telegram_bot_token, telegram_chat_id)
        if ok:
            alert_events.append("⚠️ Alerta de riesgo enviada.")

    if decision == "LONG":
        st.success("🟢 ALZA PERMITIDA")
    elif decision == "SHORT":
        st.error("🔴 BAJA PERMITIDA")
    else:
        st.warning(f"⚪ NO OPERAR | Escenario calculado: {display_direction(candidate_direction)}")

    if auto_saved_now:
        st.info("📡 Señal válida capturada automáticamente.")
    if notional_capped:
        st.warning(f"⚠️ Notional limitado por apalancamiento: máximo {fmt0(max_notional)} USDT. El riesgo real baja a {format_number(risk_usd, 2)} USDT.")
    for event in alert_events:
        st.info(event)
    if objetivo_exigente:
        st.warning(
            f"⚠️ Objetivo exigente / no scalping. TP a {tp_atr_multiple:.2f} ATR. "
            "Para intradía rápido conviene esperar un TP más cercano o una mejor entrada."
        )
    elif scalping_no_recomendado:
        st.info(
            f"ℹ️ TP algo lejano para scalping: {tp_atr_multiple:.2f} ATR. "
            "Operación más apta para intradía amplio que para scalp rápido."
        )

    st.markdown(f"## Calidad del setup: {quality_label} · {quality_score}/10")
    st.divider()
    st.subheader("📊 Volume Profile PRO")
    if volume_profile:
        vp1, vp2, vp3 = st.columns(3)
        vp1.metric("POC", fmt0(volume_profile["poc"]))
        vp2.metric("VAH", fmt0(volume_profile["vah"]))
        vp3.metric("VAL", fmt0(volume_profile["val"]))
        st.info(
            f"**Estado:** {volume_profile['estado']}  \n\n"
            f"**Lectura:** {volume_profile['lectura']}"
        )
        st.write(
            "**HVN:** "
            + ", ".join([fmt0(x) for x in volume_profile["hvn"]])
        )
        st.write(
            "**LVN:** "
            + ", ".join([fmt0(x) for x in volume_profile["lvn"]])
        )
    else:
        st.warning("No hay datos suficientes para calcular Volume Profile.")
    st.subheader("🎯 Zonas profesionales Daytrade")
    zonas_daytrade = detectar_zonas_daytrade(

        df_15m=df_15m,

        asia_high=None,

        london_high=None,

        max_zonas=3
    )
    if zonas_daytrade:
        mejor = zonas_daytrade[0]
        st.markdown("### 🧠 Mejor oportunidad detectada")
        st.markdown(
            f"""
    **{mejor['semaforo']}**  
    **Calidad:** {mejor['color']} {mejor['calidad']} — {mejor['score']}/100 {mejor['estrellas']}  
    **Sesgo:** {mejor['sesgo']}  
    **Zona:** {mejor['desde']:.2f} - {mejor['hasta']:.2f}  
    **Distancia al centro:** {mejor['distancia_pts']:.0f} pts ({mejor['distancia_atr']:.2f} ATR)  
    **Estado:** {mejor['estado']}  
    **Acción:** {mejor['accion']}
    """
        )
        st.markdown("#### Confirmaciones")
        checks = []
        for nombre, ok in mejor["confirmaciones"].items():
            checks.append(f"{'✅' if ok else '❌'} {nombre}")
        st.write(" | ".join(checks))
        st.markdown(
            f"""
    **Confirmadas:** {mejor['confirmadas']} / {mejor['total_confirmaciones']}  
    **Falta para habilitar entrada:**  
    {", ".join(mejor["faltan"])}
    """
        )
        st.divider()
        st.markdown("### 📍 Otras zonas relevantes")
        for i, z in enumerate(zonas_daytrade[1:], start=2):
            st.markdown(
                f"""
    **Zona {i}: {z['calidad']} — {z['score']}/100 {z['estrellas']}**  
    Rango: **{z['desde']:.2f} - {z['hasta']:.2f}**  
    Estado: {z['estado']}  
    Acción: {z['accion']}  
    Confluencias: {", ".join(z["motivos"])}
    """
            )
    else:
        st.info("No hay zonas profesionales relevantes cercanas ahora.")
    st.subheader("🔥 Delta de Volumen PRO")
    delta_15m = df_15m["volume_delta"].iloc[-1]
    delta_strength_15m = df_15m["delta_strength"].iloc[-1]
    vol_ratio_15m = df_15m["vol_ratio"].iloc[-1]
    

    st.subheader("🧱 Order Blocks automáticos")
    if ob_df is not None and not ob_df.empty:
        ob_open = ob_df[~ob_df["mitigated"].astype(bool)].copy()
        if not ob_open.empty:
            last_obs = ob_open.tail(5).copy()
            st.dataframe(
                last_obs[["time", "tipo", "direction", "low", "mid", "high", "mitigated"]],
                use_container_width=True
            )
        else:
            st.info("Hay Order Blocks detectados, pero ya fueron mitigados.")
    else:
        st.info("No hay Order Blocks relevantes en el lookback actual.")

    st.subheader("💧 Perfil de Liquidez PRO")
    if liq_profile_df is not None and not liq_profile_df.empty:
        liq_show = liq_profile_df.head(8).copy()
        liq_show["time"] = liq_show["time"].astype(str)
        st.dataframe(
            liq_show[
                ["time", "tipo", "direction", "nivel", "estado", "distancia_pts", "distancia_atr", "motivo"]
            ],
            use_container_width=True
        )
    else:
        st.info("No hay Equal Highs / Equal Lows relevantes ahora.")

    st.subheader("🏦 Volumen Institucional PRO")
    if inst_vol_df is not None and not inst_vol_df.empty:
        inst_show = inst_vol_df.tail(8).copy()
        inst_show["time"] = inst_show["time"].astype(str)
        st.dataframe(
            inst_show[
                ["time", "tipo", "direction", "precio", "vol_ratio", "range_ratio", "motivo"]
            ],
            use_container_width=True
        )
        ultima_inst = inst_vol_df.iloc[-1]
        if ultima_inst["direction"] == "LONG":
            st.success("🟢 Última vela institucional detectada: alcista.")
        else:
            st.error("🔴 Última vela institucional detectada: bajista.")
    else:
        st.info("No hay velas institucionales relevantes en el lookback actual.")

    d1, d2, d3 = st.columns(3)
    d1.metric("Delta 15M", delta_estado)
    d2.metric("Fuerza Delta", delta_fuerza, f"{delta_strength_15m:.2f}x")
    d3.metric("Volumen relativo", f"{vol_ratio_15m:.2f}x")
    last_15 = df_15m.iloc[-1]
    absorcion_compradora = (
        last_15["close"] < last_15["open"]
        and delta_strength_15m > 1.0
        and vol_ratio_15m > 1.2
    )
    absorcion_vendedora = (
        last_15["close"] > last_15["open"]
        and delta_strength_15m < -1.0
        and vol_ratio_15m > 1.2
    )
    if absorcion_compradora:
        st.success("🟢 Posible absorción compradora: el precio baja, pero aparece presión compradora.")
    elif absorcion_vendedora:
        st.error("🔴 Posible absorción vendedora: el precio sube, pero aparece presión vendedora.")
    else:
        st.info("Sin absorción clara en la última vela 15M.")
    st.divider()     
    q1, q2, q3, q4, q5 = st.columns(5)
    q1.metric("Calidad", quality_label, f"{quality_score}/10")
    q2.metric("Distancia SL", f"{risk_points_calc:,.0f} pts" if not pd.isna(risk_points_calc) else "—", f"ATR 15M: {atr_15m:,.0f} pts" if not pd.isna(atr_15m) else "—")
    q3.metric("Setup", display_direction(candidate_direction), f"RR: {rr_real:.2f}" if not pd.isna(rr_real) else "—")
    q4.metric("Distancia TP", f"{tp_distance_calc:,.0f} pts" if not pd.isna(tp_distance_calc) else "—", f"{tp_atr_multiple:.2f} ATR" if not pd.isna(tp_atr_multiple) else "—")
    q5.metric("FVG", fvg_label.replace("_", " "), f"{format_number(fvg_distance_atr, 2)} ATR" if not pd.isna(fvg_distance_atr) else "—")

    with st.expander("📌 Motivo de la decisión", expanded=not mobile_compact):
        st.write(f"**Estrategia activa:** {estrategia}")
        st.write(f"**Escenario:** {escenario}")
        st.write(f"**Dirección calculada:** {display_direction(candidate_direction)}")
        st.write(f"**Estructura 5M:** {structure}")
        st.write(f"**Long Score:** {long_score}/10")
        st.write(f"**Short Score:** {short_score}/10")
        st.write(f"**Score PRO:** {quality_detail['score_100']}/100")
        st.write("**Factores positivos:**")
        for p in quality_detail["positivos"]:
            st.success(p)
        st.write("**Factores negativos / faltantes:**")
        for n in quality_detail["negativos"]:
            st.warning(n)
        st.write(f"**RR real:** {format_number(rr_real, 2)}")
        st.write(f"**ATR 15M:** {format_number(atr_15m, 2)} puntos")
        st.write(f"**FVG:** {fvg_label}")
        if fvg_zone:
            st.write(f"**Zona FVG:** {fmt0(fvg_zone['low'])} - {fmt0(fvg_zone['high'])} | MID {fmt0(fvg_zone['mid'])} | Gap {fmt0(fvg_zone['gap_pts'])} pts")
        st.write(f"**Distancia SL:** {format_number(risk_points_calc, 2)} puntos")
        st.write(f"**Distancia TP:** {format_number(tp_distance_calc, 2)} puntos")
        if trade_valid:
            st.success(f"Setup válido para estrategia: {estrategia}.")
        else:
            for motivo in motivos_bloqueo:
                st.warning(motivo)

    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Precio BTCUSDT", format_number(price, 2))
    col2.metric("Long Score", f"{long_score}/10")
    col3.metric("Short Score", f"{short_score}/10")
    col4.metric("RSI 15M", f"{rsi_15:.2f}" if not pd.isna(rsi_15) else "—", rsi_label)
    st.divider()

    c1, c2, c3, c4, c5 = st.columns(5)
    c1.metric("24H", trend_icon(t1d))
    c2.metric("4H", trend_icon(t4))
    c3.metric("1H", trend_icon(t1))
    c4.metric("15M", trend_icon(t15))
    c5.metric("5M", trend_icon(t5))
    st.divider()

    g1, g2, g3, g4, g5, g6, g7 = st.columns(7)
    g1.metric("Cuenta", f"{account_usd:.0f} USDT")
    g2.metric("Riesgo real", f"{risk_usd:.2f} USDT", f"Obj: {risk_usd_target:.2f}")
    g3.metric("Ganancia TP", f"+{profit_usd:.2f} USDT", f"{profit_pct:.2f}%")
    g4.metric("Tamaño", f"{btc_size:.4f} BTC")
    g5.metric("Nocional real", f"{notional:.0f} USDT")
    g6.metric("Máx nocional", f"{max_notional:.0f} USDT")
    g7.metric("Margen", f"{margin_needed:.0f} USDT")

    r1, r2, r3, r4, r5, r6 = st.columns(6)
    r1.metric("Entrada", f"{price:,.0f}")
    r2.metric("SL técnico", f"{sl_calc:,.0f}" if not pd.isna(sl_calc) else "—")
    r3.metric("TP automático", f"{tp_calc:,.0f}" if not pd.isna(tp_calc) else "—")
    r4.metric("Distancia SL", f"{risk_points_calc:,.0f} pts" if not pd.isna(risk_points_calc) else "—")
    r5.metric("Distancia TP", f"{tp_distance_calc:,.0f} pts" if not pd.isna(tp_distance_calc) else "—")
    r6.metric("RR real", f"{rr_real:.2f}" if not pd.isna(rr_real) else "—")
    st.divider()
    st.subheader("🎯 Trade en vivo")
    open_trade = get_open_trade()
    with st.expander("➕ Cargar operación abierta", expanded=open_trade is None):
        col_a, col_b, col_c = st.columns(3)
        manual_direction = col_a.selectbox("Dirección", ["LONG", "SHORT"], key="live_direction")
        manual_entry = col_b.number_input("Entrada", value=float(price), step=1.0, key="live_entry")
        manual_size = col_c.number_input("Tamaño BTC", value=0.001, step=0.001, format="%.4f", key="live_size")
        col_d, col_e, col_f = st.columns(3)
        manual_sl = col_d.number_input("SL", value=float(sl_calc) if not pd.isna(sl_calc) else float(price), step=1.0, key="live_sl")
        manual_tp = col_e.number_input("TP", value=float(tp_calc) if not pd.isna(tp_calc) else float(price), step=1.0, key="live_tp")
        manual_lev = col_f.number_input("Leverage", value=float(leverage), step=1.0, key="live_leverage_select")
        if st.button("✅ Abrir trade en vivo"):
            save_open_trade({
                "fecha": datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S"),
                "direction": manual_direction,
                "entry": manual_entry,
                "sl": manual_sl,
                "tp": manual_tp,
                "size_btc": manual_size,
                "leverage": manual_lev,
                "status": "OPEN",
            })
            st.success("Trade abierto correctamente.")
            st.rerun()
    if open_trade:
        pnl, current_r, distance_tp, distance_sl, estado = calc_live_trade(open_trade, price)
        st.markdown(f"### {estado}")
        a, b, c, d, e = st.columns(5)
        a.metric("Dirección", open_trade["direction"])
        b.metric("Entrada", fmt0(open_trade["entry"]))
        c.metric("Precio actual", fmt0(price))
        d.metric("PNL vivo", f"{pnl:+.2f} USDT")
        e.metric("R actual", f"{current_r:+.2f}R")
        f, g, h = st.columns(3)
        f.metric("Falta TP", f"{max(distance_tp, 0):,.0f} pts")
        g.metric("Falta SL", f"{max(distance_sl, 0):,.0f} pts")
        h.metric("Tamaño", f"{float(open_trade['size_btc']):.4f} BTC")
        progress = min(max((current_r + 1) / 3, 0), 1)
        st.progress(progress)
        close_col1, close_col2 = st.columns(2)
        if close_col1.button("🔒 Cerrar trade al precio actual"):
            closed = open_trade.copy()
            closed["fecha_cierre"] = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")
            closed["precio_cierre"] = price
            closed["pnl_usdt"] = pnl
            closed["r_resultado"] = current_r
            closed["resultado"] = "MANUAL"
            close_open_trade(closed)
            st.success("Trade cerrado y guardado en historial.")
            st.rerun()
        if close_col2.button("🗑️ Cancelar trade abierto"):
            pd.DataFrame(columns=[
                "fecha", "direction", "entry", "sl", "tp",
                "size_btc", "leverage", "status"
            ]).to_csv(OPEN_TRADE_FILE, index=False)
            st.warning("Trade abierto eliminado.")
            st.rerun()
    else:
        st.info("No hay operación abierta cargada.")
    st.subheader("📈 Gráfico operativo intradía")
    grafico_operativo_slot = st.container()
    st.divider()
    chart_df = df_15m.tail(100 if mobile_compact else 150).copy()
    fig = go.Figure()
    fig.add_trace(go.Candlestick(x=chart_df["time"], open=chart_df["open"], high=chart_df["high"], low=chart_df["low"], close=chart_df["close"], name="BTCUSDT"))
    fig.add_trace(go.Scatter(x=chart_df["time"], y=chart_df["ema20"], mode="lines", name="EMA 20", line=dict(color="#ff6b57", width=2)))
    fig.add_trace(go.Scatter(x=chart_df["time"], y=chart_df["ema50"], mode="lines", name="EMA 50", line=dict(color="#18c29c", width=2)))
    fig.add_trace(go.Scatter(x=chart_df["time"], y=chart_df["ema200"], mode="lines", name="EMA 200", line=dict(color="#9b5cff", width=2)))

    if show_fvg_zones and not fvg_df.empty:
        fvg_open = fvg_df[~fvg_df["mitigated"].astype(bool)].copy()
        fvg_open["distancia"] = (fvg_open["mid"] - price).abs()
        bull_fvg = fvg_open[fvg_open["direction"] == "LONG"].sort_values("distancia").head(2)
        bear_fvg = fvg_open[fvg_open["direction"] == "SHORT"].sort_values("distancia").head(2)
        open_fvg = pd.concat([bull_fvg, bear_fvg]).sort_values("distancia")
        x0 = chart_df["time"].iloc[0]
        x1 = chart_df["time"].iloc[-1]
        for _, z in open_fvg.iterrows():
            if bool(z["mitigated"]):
                fill = "rgba(255, 200, 0, 0.16)"
                line = "rgba(180, 140, 0, 0.55)"
            else:
                fill = "rgba(0, 180, 80, 0.18)" if z["direction"] == "LONG" else "rgba(220, 0, 0, 0.14)"
                line = "rgba(0, 120, 60, 0.65)" if z["direction"] == "LONG" else "rgba(180, 0, 0, 0.65)"
            fig.add_shape(type="rect", xref="x", yref="y", x0=max(z["time"], x0), x1=x1, y0=z["low"], y1=z["high"], fillcolor=fill, line=dict(color=line, width=1), layer="below")
            fig.add_annotation(x=x1, y=z["mid"], text=z["tipo"].replace("_FVG", ""), showarrow=False, xanchor="left", font=dict(size=10, color=line))

    # ===== ORDER BLOCKS EN GRÁFICO =====
    if ob_df is not None and not ob_df.empty:
        ob_open = ob_df[~ob_df["mitigated"].astype(bool)].copy().tail(4)
        x1 = chart_df["time"].iloc[-1]
        for _, ob in ob_open.iterrows():
            fill = "rgba(0, 180, 80, 0.12)" if ob["direction"] == "LONG" else "rgba(220, 0, 0, 0.12)"
            line = "rgba(0, 120, 60, 0.75)" if ob["direction"] == "LONG" else "rgba(180, 0, 0, 0.75)"
            fig.add_shape(
                type="rect",
                xref="x",
                yref="y",
                x0=ob["time"],
                x1=x1,
                y0=ob["low"],
                y1=ob["high"],
                fillcolor=fill,
                line=dict(color=line, width=1),
                layer="below"
            )
            fig.add_annotation(
                x=x1,
                y=ob["mid"],
                text=ob["tipo"].replace("_", " "),
                showarrow=False,
                xanchor="left",
                font=dict(size=10, color=line)
            )
    # ===== FIN ORDER BLOCKS =====

    # ===== PERFIL DE LIQUIDEZ EN GRÁFICO =====
    if liq_profile_df is not None and not liq_profile_df.empty:
        liq_plot = liq_profile_df.head(8).copy()
        for _, liq in liq_plot.iterrows():
            if liq["tipo"] == "EQUAL_HIGHS":
                color = "rgba(180, 0, 0, 0.85)"
                label = "EQH"
            else:
                color = "rgba(0, 120, 60, 0.85)"
                label = "EQL"
            dash = "solid" if liq["estado"] == "BARRIDO" else "dot"
            fig.add_hline(
                y=liq["nivel"],
                line_color=color,
                line_width=2,
                line_dash=dash,
                annotation_text=f"{label} {liq['estado']}",
                annotation_position="right"
            )
    # ===== FIN PERFIL LIQUIDEZ =====

    # ===== VOLUMEN INSTITUCIONAL EN GRÁFICO =====
    if inst_vol_df is not None and not inst_vol_df.empty:
        inst_plot = inst_vol_df.tail(5).copy()
        for _, v in inst_plot.iterrows():
            if v["direction"] == "LONG":
                txt = "🏦 VOL LONG"
                y = v["low"]
                ay = 45
            else:
                txt = "🏦 VOL SHORT"
                y = v["high"]
                ay = -45
            fig.add_annotation(
                x=v["time"],
                y=y,
                text=txt,
                showarrow=True,
                arrowhead=2,
                arrowsize=1.4,
                arrowwidth=2,
                ax=0,
                ay=ay
            )
    # ===== FIN VOLUMEN INSTITUCIONAL =====

    for name, value in levels.items():
        if not pd.isna(value):
            fig.add_hline(y=value, line_dash="dot", line_color="gray", annotation_text=name, annotation_position="right")
    should_show_trade_levels = trade_valid or show_levels_when_no_trade
    if should_show_trade_levels and not pd.isna(sl_calc):
        fig.add_hline(y=sl_calc, line_color="red", line_width=3, annotation_text="SL")
    if should_show_trade_levels and not pd.isna(tp_calc):
        fig.add_hline(y=tp_calc, line_color="green", line_width=3, annotation_text="TP")
    fig.add_hline(y=price, line_color="black", line_width=3, annotation_text="Entrada")
    if volume_profile:
        fig.add_hline(
            y=volume_profile["poc"],
            line_color="blue",
            line_width=2,
            line_dash="solid",
            annotation_text="POC"
        )
        fig.add_hline(
            y=volume_profile["vah"],
            line_color="purple",
            line_width=2,
            line_dash="dash",
            annotation_text="VAH"
        )
        fig.add_hline(
            y=volume_profile["val"],
            line_color="purple",
            line_width=2,
            line_dash="dash",
            annotation_text="VAL"
        )
        # ===== DELTA DE VOLUMEN EN GRÁFICO =====
        last_delta = df_15m["volume_delta"].iloc[-1]
        last_delta_strength = df_15m["delta_strength"].iloc[-1]
        if last_delta_strength >= 1.5:
            fig.add_annotation(
                x=chart_df["time"].iloc[-1],
                y=chart_df["low"].iloc[-1],
                text="🟢 Δ BUY",
                showarrow=True,
                arrowhead=2,
                arrowcolor="green",
                arrowsize=1.5,
                arrowwidth=2,
                font=dict(size=13, color="green"),
                ax=0,
                ay=45
            )
        elif last_delta_strength <= -1.5:
            fig.add_annotation(
                x=chart_df["time"].iloc[-1],
                y=chart_df["high"].iloc[-1],
                text="🔴 Δ SELL",
                showarrow=True,
                arrowhead=2,
                arrowcolor="red",
                arrowsize=1.5,
                arrowwidth=2,
                font=dict(size=13, color="red"),
                ax=0,
                ay=-45
            )
        # ===== FIN DELTA DE VOLUMEN =====
    # ===== ZONAS RR =====
    if (
        should_show_trade_levels
        and not pd.isna(sl_calc)
        and not pd.isna(tp_calc)
    ):
        if candidate_direction == "LONG":
            fig.add_hrect(
                y0=price,
                y1=tp_calc,
                fillcolor="green",
                opacity=0.08,
                line_width=0
            )
            fig.add_hrect(
                y0=sl_calc,
                y1=price,
                fillcolor="red",
                opacity=0.08,
                line_width=0
            )
        elif candidate_direction == "SHORT":
            fig.add_hrect(
                y0=tp_calc,
                y1=price,
                fillcolor="green",
                opacity=0.08,
                line_width=0
            )
            fig.add_hrect(
                y0=price,
                y1=sl_calc,
                fillcolor="red",
                opacity=0.08,
                line_width=0
            )
    # ===== FIN ZONAS RR =====
    fig.update_layout(template="plotly_white", height=1000 if mobile_compact else 700, xaxis_rangeslider_visible=False, title="BTCUSDT 15M - Velas + EMAs + Liquidez + FVG + SL/TP", margin=dict(l=20, r=20, t=50, b=20))
    fig.update_layout(
        paper_bgcolor="white",
        plot_bgcolor="white"
    )
    fig.update_yaxes(
        gridcolor="rgba(0,0,0,0.08)"
    )
    fig.update_xaxes(
        gridcolor="rgba(0,0,0,0.05)"
    )
    y_values = [chart_df["low"].min(), chart_df["high"].max()]
    for val in [sl_calc, tp_calc, price]:
        if not pd.isna(val):
            y_values.append(val)
    y_min, y_max = min(y_values), max(y_values)
    padding = max((y_max - y_min) * 0.12, 100)
    fig.update_yaxes(range=[y_min - padding, y_max + padding], autorange=False)
    with grafico_operativo_slot:
        st.plotly_chart(
            fig,
            use_container_width=True,
            key="grafico_principal"
        )
    st.divider()
    st.subheader("🧪 Backtesting automático")
    with st.spinner("Calculando backtest..."):
        bt_results, bt_stats = run_simple_backtest(backtest_tf, backtest_period, estrategia, min_score, rr_target, min_rr, max_atr_multiplier, filter_hours, avoid_weekends, fvg_min_atr, fvg_max_distance_atr, use_fvg_filter)
    b1, b2, b3, b4, b5 = st.columns(5)
    b1.metric("Operaciones", int(bt_stats.get("operaciones", 0)))
    b2.metric("Winrate", f"{bt_stats.get('winrate', 0):.1f}%")
    pf = bt_stats.get("profit_factor", 0)
    b3.metric("Profit Factor", "∞" if pf == np.inf else f"{pf:.2f}")
    b4.metric("Drawdown", f"{bt_stats.get('drawdown', 0):.2f}R")
    b5.metric("Expectativa", f"{bt_stats.get('expectancy', 0):+.2f}R")

    if not bt_results.empty:
        equity = bt_results[bt_results["resultado"].isin(["TP", "SL"])].copy()
        if not equity.empty:
            equity["equity_r"] = pd.to_numeric(equity["r_multiple"], errors="coerce").fillna(0).cumsum()
            eq_fig = go.Figure()
            eq_fig.add_trace(go.Scatter(x=equity["fecha"], y=equity["equity_r"], mode="lines+markers", name="Equity R"))
            eq_fig.update_layout(template="plotly_white", height=350, title="Curva de equity del backtest en R", margin=dict(l=20, r=20, t=50, b=20))
            st.plotly_chart(eq_fig, use_container_width=True, key="equity_backtest")
        st.dataframe(bt_results.tail(50), use_container_width=True)
        st.download_button("⬇️ Descargar backtest CSV", data=bt_results.to_csv(index=False), file_name="backtest_results.csv", mime="text/csv", key="download_bt")
    else:
        st.info("No hubo operaciones válidas en el período con estos filtros.")

    st.subheader("🧮 Expectativa matemática")
    st.write(f"**Win Rate histórico:** {bt_stats.get('winrate', 0):.1f}%")
    st.write(f"**RR promedio ganador:** {bt_stats.get('rr_promedio', 0):.2f}")
    st.write(f"**Expectativa:** {bt_stats.get('expectancy', 0):+.2f}R")
    if bt_stats.get("expectancy", 0) > 0:



        st.success("Expectativa positiva en este backtest. Hay posible ventaja estadística.")



    else:



        st.warning("Expectativa negativa o insuficiente. No hay ventaja demostrada con estos filtros.")
    st.divider()

    if st.button("💾 Guardar señal manual", key="save_manual_signal"):
        save_signal_row(SIGNALS_FILE, current_signal_row)
        st.success("Señal guardada correctamente.")

    st.subheader("📊 Historial de señales")
    historial = safe_read_csv(SIGNALS_FILE)
    if not historial.empty:
        historial = validate_saved_signals(historial, df_5m, validate_after_hours)
        historial.to_csv(SIGNALS_FILE, index=False)
    auto_historial = safe_read_csv(AUTO_SIGNALS_FILE)
    if not auto_historial.empty:
        auto_historial = validate_saved_signals(auto_historial, df_5m, validate_after_hours)
        auto_historial.to_csv(AUTO_SIGNALS_FILE, index=False)
    pieces = []
    if not historial.empty:
        pieces.append(historial.assign(origen="manual"))
    if not auto_historial.empty:
        pieces.append(auto_historial.assign(origen="auto"))
    combined_hist = pd.concat(pieces, ignore_index=True) if pieces else pd.DataFrame()

    stats_hist = performance_stats(combined_hist)
    stats_30, hist_30 = last_30_days_stats(combined_hist)
    strat_rank = stats_by_strategy(combined_hist)

    h1, h2, h3, h4 = st.columns(4)
    h1.metric("Señales validadas", int(stats_hist.get("operaciones", 0)))
    h2.metric("Winrate real", f"{stats_hist.get('winrate', 0):.1f}%")
    h3.metric("PF real", "∞" if stats_hist.get("profit_factor", 0) == np.inf else f"{stats_hist.get('profit_factor', 0):.2f}")
    h4.metric("Expectativa real", f"{stats_hist.get('expectancy', 0):+.2f}R")

    if mc_enabled:
        st.divider()
        st.subheader("🎯 Monte Carlo: riesgo de ruina y Max Drawdown")
        r_mults, mc_source = build_r_multiples_from_sources(bt_results, combined_hist, mc_use_backtest, mc_manual_wr, mc_manual_rr)
        mc = monte_carlo_simulation(r_mults, mc_start_capital, risk_pct, int(mc_paths), int(mc_trades_horizon), float(mc_ruin_dd_pct))
        expected_days = int(np.ceil(int(mc_trades_horizon) / max(int(mc_max_daily_trades), 1)))
        dd_color = "🟢" if mc["dd_p95"] < 10 else "🟡" if mc["dd_p95"] < 20 else "🔴"
        st.caption(f"Fuente usada: {mc_source}. Horizonte aproximado: {mc_trades_horizon} trades ≈ {expected_days} días si hacés hasta {mc_max_daily_trades} trades/día.")
        m1, m2, m3, m4, m5 = st.columns(5)
        m1.metric("DD mediano", f"{mc['dd_median']:.1f}%")
        m2.metric("DD P75", f"{mc['dd_p75']:.1f}%")
        m3.metric("DD P95", f"{mc['dd_p95']:.1f}%", dd_color)
        m4.metric("Racha perdedora P95", f"{mc['loss_streak_p95']:.0f} trades")
        m5.metric("Riesgo ruina", f"{mc['ruin_probability']:.1f}%")

        if mc["dd_p95"] >= 20 or mc["ruin_probability"] >= 10:
            st.error("🔴 Riesgo elevado: con estos parámetros una mala racha puede lastimar fuerte la cuenta. Bajá riesgo por operación o reducí cantidad de trades.")
        elif mc["dd_p95"] >= 10:
            st.warning("🟡 Riesgo moderado: operable solo con disciplina estricta y sin mover SL.")
        else:
            st.success("🟢 Riesgo controlado: el drawdown simulado está dentro de un rango más razonable.")

        mc_tabs = st.tabs(["Distribución Max Drawdown", "Curvas simuladas", "Tabla resumen"])
        with mc_tabs[0]:
            dd_fig = go.Figure()
            dd_fig.add_trace(go.Histogram(x=mc["dd_values"], nbinsx=50, name="Max Drawdown %"))
            for label, val in [("Mediana", mc["dd_median"]), ("P95", mc["dd_p95"]), ("P99", mc["dd_p99"]), ("Ruina", float(mc_ruin_dd_pct))]:
                dd_fig.add_vline(x=val, line_dash="dash", annotation_text=f"{label}: {val:.1f}%", annotation_position="top")
            dd_fig.update_layout(template="plotly_white", height=380, title=f"Distribución del Max Drawdown simulado — Horizonte {mc_trades_horizon} trades", xaxis_title="Max Drawdown (%) por escenario", yaxis_title="Frecuencia", margin=dict(l=20, r=20, t=60, b=20))
            st.plotly_chart(dd_fig, use_container_width=True, key="mc_dd_hist")
        with mc_tabs[1]:
            curves_fig = go.Figure()
            x = list(range(1, int(mc_trades_horizon) + 1))
            for i, curve in enumerate(mc["sample_curves"][:20]):
                curves_fig.add_trace(go.Scatter(x=x, y=curve, mode="lines", name=f"Escenario {i+1}", opacity=0.35, showlegend=False))
            curves_fig.add_hline(y=mc_start_capital, line_dash="dot", annotation_text="Capital inicial")
            curves_fig.add_hline(y=mc_start_capital * (1 - float(mc_ruin_dd_pct) / 100), line_dash="dash", annotation_text=f"Alerta DD {mc_ruin_dd_pct:.0f}%")
            curves_fig.update_layout(template="plotly_white", height=380, title="Curvas de equity simuladas", xaxis_title="Trade", yaxis_title="Capital USDT", margin=dict(l=20, r=20, t=60, b=20))
            st.plotly_chart(curves_fig, use_container_width=True, key="mc_curves")
        with mc_tabs[2]:
            summary_df = pd.DataFrame([{
                "fuente": mc_source,
                "escenarios": mc["paths"],
                "trades_horizonte": mc["horizon"],
                "capital_inicial": mc["start_capital"],
                "riesgo_por_trade_%": risk_pct_input,
                "DD_mediana_%": round(mc["dd_median"], 2),
                "DD_P95_%": round(mc["dd_p95"], 2),
                "DD_P99_%": round(mc["dd_p99"], 2),
                "capital_final_P05": round(mc["final_p05"], 2),
                "capital_final_mediana": round(mc["final_median"], 2),
                "capital_final_P95": round(mc["final_p95"], 2),
                "racha_perdedora_P95": round(mc["loss_streak_p95"], 0),
                "riesgo_ruina_%": round(mc["ruin_probability"], 2),
            }])
            st.dataframe(summary_df, use_container_width=True)
            st.caption("Este módulo no predice precio. Evalúa supervivencia de cuenta con rachas y drawdown probables.")

    st.subheader("🏆 Ranking de estrategias")
    if not strat_rank.empty:
        st.dataframe(strat_rank, use_container_width=True)
    else:
        st.info("Todavía no hay suficientes operaciones validadas por estrategia.")

    st.subheader("📅 Estadísticas últimos 30 días")
    l1, l2, l3, l4 = st.columns(4)
    l1.metric("Ops 30D", int(stats_30.get("operaciones", 0)))
    l2.metric("Winrate 30D", f"{stats_30.get('winrate', 0):.1f}%")
    l3.metric("PF 30D", "∞" if stats_30.get("profit_factor", 0) == np.inf else f"{stats_30.get('profit_factor', 0):.2f}")
    l4.metric("Expectativa 30D", f"{stats_30.get('expectancy', 0):+.2f}R")

    st.subheader("📈 Equity curve real")
    closed_real = combined_hist[combined_hist["resultado"].isin(["TP", "SL"])].copy() if not combined_hist.empty and "resultado" in combined_hist.columns else pd.DataFrame()
    if not closed_real.empty:
        closed_real["fecha_dt"] = pd.to_datetime(closed_real["fecha"], utc=True, errors="coerce")
        closed_real = closed_real.sort_values("fecha_dt")
        closed_real["r_multiple"] = pd.to_numeric(closed_real["r_multiple"], errors="coerce").fillna(0)
        closed_real["equity_r"] = closed_real["r_multiple"].cumsum()
        real_fig = go.Figure()
        real_fig.add_trace(go.Scatter(x=closed_real["fecha_dt"], y=closed_real["equity_r"], mode="lines+markers", name="Equity real R"))
        real_fig.update_layout(template="plotly_white", height=350, title="Equity curve real de señales guardadas", margin=dict(l=20, r=20, t=50, b=20))
        st.plotly_chart(real_fig, use_container_width=True, key="equity_real")
    else:
        st.info("La equity curve real aparece cuando haya señales cerradas en TP o SL.")

    st.subheader("🖼️ Historial visual de operaciones")
    if not combined_hist.empty:
        show_cols = [c for c in ["fecha", "vela_5m", "origen", "estrategia", "decision", "direccion_calculada", "calidad_score", "entrada", "sl", "tp", "resultado", "r_multiple", "rr_real", "fvg_estado", "notional_real", "riesgo_usdt_real", "motivos_bloqueo"] if c in combined_hist.columns]
        st.dataframe(combined_hist[show_cols].tail(50), use_container_width=True)
        st.download_button("⬇️ Descargar historial completo CSV", data=combined_hist.to_csv(index=False), file_name="signals_log_completo.csv", mime="text/csv", key="download_hist")
    else:
        st.info("Todavía no hay señales guardadas.")

    st.subheader("🔔 Historial de alertas")
    alerts_df = safe_read_csv(ALERTS_FILE)
    if not alerts_df.empty:
        st.dataframe(alerts_df.tail(30), use_container_width=True)
        st.download_button("⬇️ Descargar alertas CSV", data=alerts_df.to_csv(index=False), file_name="alerts_sent_log.csv", mime="text/csv", key="download_alerts")
    else:
        st.info("Todavía no hay alertas enviadas.")
    st.subheader("🧱 FVG inteligentes detectados")
    if not fvg_df.empty:
        fvg_show = fvg_df.head(12).copy()
        fvg_show["time"] = fvg_show["time"].astype(str)
        st.dataframe(
            fvg_show[
                [
                    "time",
                    "tipo",
                    "direction",
                    "low",
                    "mid",
                    "high",
                    "gap_pts",
                    "gap_atr",
                    "distance_atr",
                    "mitigated",
                    "score",
                    "calidad",
                    "motivo",
                ]
            ],
            use_container_width=True
        )
    else:
        st.info("No hay FVG inteligentes relevantes en el lookback actual.")
    st.subheader("⏰ Filtro horario")
    st.write("Activo" if filter_hours else "Inactivo")
    st.caption("Filtro usado: Londres 07:00-10:00 UTC y NY 13:00-16:00 UTC. Fin de semana bloqueado si está activado.")

    with st.expander("📘 Reglas del sistema"):
        st.write("""
        - Score menor al mínimo configurado = NO OPERAR.
        - RR real menor al mínimo configurado = NO OPERAR.
        - Riesgo mayor al 1% = NO OPERAR.
        - Nocional corregido: nunca supera Cuenta x Apalancamiento.
        - Si el tamaño por riesgo exige más margen del posible, el sistema limita el nocional y recalcula el riesgo real.
        - FVG bullish: gap entre high de vela i-2 y low de vela actual.
        - FVG bearish: gap entre high de vela actual y low de vela i-2.
        - FVG se considera mitigado si el precio toca el midpoint del gap.
        - FVG + Tendencia prioriza operar cerca/dentro de zonas FVG abiertas.
        - Monte Carlo mide drawdown, rachas y supervivencia de cuenta. No predice precio.
        - Telegram/Discord envían solo alertas nuevas; se evita spam con alerts_sent_log.csv.
        - Auto refresh mantiene el sistema atento mientras la app esté abierta.
        """)

    st.caption(f"Última actualización local: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

except Exception as e:
    st.error("Hubo un error cargando el dashboard.")
    st.exception(e)