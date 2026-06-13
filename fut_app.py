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
div[data-testid="stMetricValue"] {font-size: 1.5rem !important;}
.block-container {padding-top: 2rem;}
@media (max-width: 768px) {
    div[data-testid="stMetricValue"] {font-size: 1.05rem !important;}
    h1 {font-size: 1.7rem !important;}
    h2 {font-size: 1.35rem !important;}
}
</style>
""", unsafe_allow_html=True)

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
# CSV / ALERTAS
# =========================

def safe_read_csv(file_path):
    if os.path.exists(file_path):
        try:
            return pd.read_csv(file_path)
        except Exception:
            return pd.DataFrame()
    return pd.DataFrame()


def save_signal_row(file_path, row):
    new = pd.DataFrame([row])
    old = safe_read_csv(file_path)
    out = pd.concat([old, new], ignore_index=True) if not old.empty else new
    out.to_csv(file_path, index=False)


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
        r = requests.post(
            url,
            data={"chat_id": chat_id, "text": text, "parse_mode": "HTML", "disable_web_page_preview": True},
            timeout=10,
        )
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

# Un solo bloque de clave. No dupliques este text_input en otra parte del código.
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
leverage = st.sidebar.selectbox("Apalancamiento sugerido", [3, 5, 10, 20], index=1, key="leverage_select")
min_score = st.sidebar.slider("Score mínimo para operar", 1, 10, 7, key="min_score_slider")
rr_target = st.sidebar.number_input("Riesgo/Beneficio objetivo", min_value=1.0, max_value=10.0, value=2.0, step=0.1, key="rr_target_input")
min_rr = st.sidebar.number_input("RR mínimo aceptado", min_value=1.0, max_value=10.0, value=1.8, step=0.1, key="min_rr_input")
max_atr_multiplier = st.sidebar.number_input("Máximo SL permitido en ATR", min_value=0.5, max_value=5.0, value=2.0, step=0.1, key="max_atr_input")
show_levels_when_no_trade = st.sidebar.checkbox("Mostrar SL/TP aunque sea NO OPERAR", value=True, key="show_levels_chk")

st.sidebar.divider()
st.sidebar.subheader("Backtesting")
backtest_period = st.sidebar.selectbox("Período", ["3 meses", "6 meses", "1 año"], index=0, key="bt_period_select")
backtest_tf = st.sidebar.selectbox("Timeframe backtest", ["15m", "5m"], index=0, key="bt_tf_select")
filter_hours = st.sidebar.checkbox("Filtro horario: Londres / Londres + NY", value=True, key="filter_hours_chk")
avoid_weekends = st.sidebar.checkbox("Evitar fines de semana", value=True, key="avoid_weekends_chk")
validate_after_hours = st.sidebar.number_input("Validar señales después de horas", min_value=1, max_value=72, value=24, step=1, key="validate_hours_input")

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

    st.divider()
    alert_valid_signals = st.checkbox("Avisar señales válidas", value=True, key="alert_valid_chk")
    alert_almost_setups = st.checkbox("Avisar setups en formación", value=True, key="alert_almost_chk")
    alert_bias_change = st.checkbox("Avisar cambio fuerte de sesgo", value=True, key="alert_bias_chk")
    alert_risk_warning = st.checkbox("Avisar TP/SL demasiado exigente", value=False, key="alert_risk_chk")
    almost_score_gap = st.slider("Setup en formación: a cuántos puntos del score", 1, 3, 1, key="almost_gap_slider")

    if st.button("📲 Probar Telegram", key="test_telegram_btn"):
        ok, resp = send_telegram_message("🚀 BTC Dashboard Pro conectado correctamente.", telegram_bot_token, telegram_chat_id)
        if ok:
            st.success("Mensaje enviado.")
        else:
            st.error(resp)

st.sidebar.divider()
if st.sidebar.button("🔄 Actualizar datos", key="refresh_btn"):
    st.rerun()

# Auto refresh: desactivado por defecto para no romper la clave ni saturar. Si lo activás, mantiene la app viva.
if auto_refresh_enabled:
    components.html(
        f"""
        <script>
        setTimeout(function() {{
            window.parent.location.reload();
        }}, {int(auto_refresh_seconds) * 1000});
        </script>
        """,
        height=0,
    )


# =========================
# EXCHANGE / DATA
# =========================

exchange = ccxt.okx({"enableRateLimit": True, "options": {"defaultType": "swap"}})


@st.cache_data(ttl=60)
def get_ohlcv(timeframe, limit=LIMIT):
    data = exchange.fetch_ohlcv(SYMBOL, timeframe=timeframe, limit=limit)
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
    return df


def resample_ohlcv(df, rule):
    if df.empty:
        return df
    return df.resample(rule, on="time").agg({
        "open": "first",
        "high": "max",
        "low": "min",
        "close": "last",
        "volume": "sum",
    }).dropna().reset_index()


def load_all_data():
    return (
        add_indicators(get_ohlcv("1d")),
        add_indicators(get_ohlcv("4h")),
        add_indicators(get_ohlcv("1h")),
        add_indicators(get_ohlcv("15m")),
        add_indicators(get_ohlcv("5m")),
    )


# =========================
# ANALISIS
# =========================

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
    return "🟢 BULL" if state == "BULL" else "🔴 BEAR" if state == "BEAR" else "⚪ NEUTRAL"


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
    if direction == "LONG":
        targets = {k: v for k, v in clean.items() if v > price}
    else:
        targets = {k: v for k, v in clean.items() if v < price}
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


def score_direction(direction, df_4h, df_1h, df_15m, df_5m, levels):
    score = 0
    t4, t1, t15, t5 = trend_state(df_4h), trend_state(df_1h), trend_state(df_15m), trend_state(df_5m)
    rsi_value = df_15m["rsi"].iloc[-1]
    structure = structure_state(df_5m)
    price = df_5m["close"].iloc[-1]
    liquidity_name, _, _ = nearest_liquidity(price, levels, direction)
    if direction == "LONG":
        score += 2 if t4 == "BULL" else 0
        score += 2 if t1 == "BULL" else 0
        score += 1 if t15 == "BULL" else 0
        score += 1 if t5 == "BULL" else 0
        score += 1 if not pd.isna(rsi_value) and rsi_value > 50 else 0
        score += 1 if structure == "BREAK_UP" else 0
        score += 1 if liquidity_name else 0
    else:
        score += 2 if t4 == "BEAR" else 0
        score += 2 if t1 == "BEAR" else 0
        score += 1 if t15 == "BEAR" else 0
        score += 1 if t5 == "BEAR" else 0
        score += 1 if not pd.isna(rsi_value) and rsi_value < 50 else 0
        score += 1 if structure == "BREAK_DOWN" else 0
        score += 1 if liquidity_name else 0
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


def choose_candidate_direction(estrategia, long_score, short_score, t1d, t4, structure, price, df_15m, df_5m, levels):
    rsi = df_15m["rsi"].iloc[-1]
    sweep_direction = detect_sweep_direction(df_5m, levels)
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


def technical_levels(direction, df_5m, entry, rr_target):
    recent = df_5m.tail(30)
    atr = df_5m["atr"].iloc[-1]
    if pd.isna(atr) or atr <= 0:
        atr = 250
    buffer = atr * 0.35
    if direction == "LONG":
        sl = recent["low"].min() - buffer
        risk_points = entry - sl
        tp = entry + risk_points * rr_target
    elif direction == "SHORT":
        sl = recent["high"].max() + buffer
        risk_points = sl - entry
        tp = entry - risk_points * rr_target
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
    risk_usd = account_usd * risk_pct
    if pd.isna(sl):
        return 0, 0, risk_usd, 0
    distance = abs(entry - sl)
    if distance <= 0:
        return 0, 0, risk_usd, 0
    btc_size = risk_usd / distance
    notional = btc_size * entry
    margin_needed = notional / leverage
    return btc_size, notional, risk_usd, margin_needed


def strategy_filter(estrategia, direction, df_15m, df_5m, levels, structure, market_bias):
    motivos = []
    price = df_5m["close"].iloc[-1]
    last = df_5m.iloc[-1]
    ema50 = df_15m["ema50"].iloc[-1]
    atr = df_15m["atr"].iloc[-1]
    rsi = df_15m["rsi"].iloc[-1]
    sweep_direction = detect_sweep_direction(df_5m, levels)
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
    return motivos


def setup_quality(long_score, short_score, direction, rr_real, risk_points, atr_15m, trade_valid):
    base_score = long_score if direction == "LONG" else short_score
    quality_score = int(round((base_score / 9) * 10))
    if not pd.isna(rr_real) and rr_real >= 2:
        quality_score += 1
    if not pd.isna(risk_points) and not pd.isna(atr_15m):
        quality_score += 1 if risk_points <= atr_15m * 2 else -1
    if not trade_valid:
        quality_score = min(quality_score, 4)
    quality_score = max(1, min(10, quality_score))
    label = "MALA" if quality_score <= 3 else "REGULAR" if quality_score <= 5 else "BUENA" if quality_score <= 7 else "EXCELENTE"
    return quality_score, label


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
                   df_15m, df_5m, use_time_filter=False, avoid_weekends_filter=False):
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
    motivos.extend(strategy_filter(estrategia, direction, df_15m, df_5m, levels, structure, market_bias))
    return len(motivos) == 0, motivos


# =========================
# BACKTEST / ESTADISTICAS
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
        rows.append({
            "estrategia": strat,
            "operaciones": s["operaciones"],
            "winrate_%": round(s["winrate"], 1),
            "profit_factor": np.inf if s["profit_factor"] == np.inf else round(s["profit_factor"], 2),
            "drawdown_R": round(s["drawdown"], 2),
            "expectativa_R": round(s["expectancy"], 2),
        })
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


@st.cache_data(ttl=300)
def run_simple_backtest(timeframe, period_label, estrategia, min_score, rr_target, min_rr, max_atr_multiplier, use_time_filter, avoid_weekends_filter):
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
        price_bt = df_5_bt["close"].iloc[-1]
        structure_bt = structure_state(df_5_bt)
        long_score_bt = score_direction("LONG", df_4h_bt, df_1h_bt, df_15_bt, df_5_bt, levels_bt)
        short_score_bt = score_direction("SHORT", df_4h_bt, df_1h_bt, df_15_bt, df_5_bt, levels_bt)
        escenario_bt, market_bias_bt = detect_market_intention(price_bt, df_4h_bt, df_1h_bt, df_15_bt, levels_bt)
        direction_bt = choose_candidate_direction(estrategia, long_score_bt, short_score_bt, trend_state(df_1d_bt), trend_state(df_4h_bt), structure_bt, price_bt, df_15_bt, df_5_bt, levels_bt)
        sl_bt, tp_bt, risk_points_bt = technical_levels(direction_bt, df_5_bt, price_bt, rr_target)
        rr_bt = calculate_rr(price_bt, sl_bt, tp_bt, direction_bt)
        valid_bt, motivos_bt = validate_trade(
            estrategia, direction_bt, long_score_bt, short_score_bt, min_score, 0.01, rr_bt, min_rr,
            risk_points_bt, df_15_bt["atr"].iloc[-1], market_bias_bt, structure_bt, price_bt,
            levels_bt, max_atr_multiplier, df_15_bt, df_5_bt, use_time_filter, avoid_weekends_filter
        )
        if not valid_bt:
            continue
        future = df.iloc[i + 1:i + 1 + horizon]
        result, r_mult = outcome_from_future(future, direction_bt, sl_bt, tp_bt, rr_bt)
        rows.append({
            "fecha": df_5_bt["time"].iloc[-1],
            "estrategia": estrategia,
            "direccion": direction_bt,
            "entrada": price_bt,
            "sl": sl_bt,
            "tp": tp_bt,
            "rr": rr_bt,
            "long_score": long_score_bt,
            "short_score": short_score_bt,
            "resultado": result,
            "r_multiple": r_mult,
            "escenario": escenario_bt,
            "motivos": " | ".join(motivos_bt),
        })
    res = pd.DataFrame(rows)
    return res, performance_stats(res)


def validate_saved_signals(historial, current_df_5m, hours_after=24):
    if historial is None or historial.empty:
        return historial
    h = historial.copy()
    for col in ["resultado", "r_multiple", "validado_hasta"]:
        if col not in h.columns:
            h[col] = np.nan
    now_utc = current_df_5m["time"].max()
    for idx, row in h.iterrows():
        if str(row.get("resultado", "nan")) in ["TP", "SL", "NINGUNO", "NO_OPERAR"]:
            continue
        try:
            fecha = pd.to_datetime(row["fecha"], utc=True)
        except Exception:
            continue
        if now_utc < fecha + pd.Timedelta(hours=hours_after):
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


def signal_key(row):
    return f"{row['vela_5m']}_{row['estrategia']}_{row['decision']}_{row['direccion_calculada']}"


def direction_score(direction, long_score, short_score):
    return long_score if direction == "LONG" else short_score


def build_valid_signal_msg(decision, symbol, estrategia, price, sl, tp, rr, quality_label, quality_score, long_score, short_score, rsi, atr, current_candle_time):
    return f"""🚨 <b>BTC DASHBOARD PRO</b>

<b>SEÑAL VÁLIDA DETECTADA</b>

Dirección: <b>{decision}</b>
Par: {symbol}
Estrategia: {estrategia}

Entrada: {fmt0(price)}
SL: {fmt0(sl)}
TP: {fmt0(tp)}

RR: {format_number(rr, 2)}
Setup: {quality_label} {quality_score}/10

Long Score: {long_score}/9
Short Score: {short_score}/9
RSI 15M: {format_number(rsi, 2)}
ATR 15M: {fmt0(atr)} pts

Vela 5M: {current_candle_time}
"""


def build_almost_msg(direction, symbol, estrategia, score, min_score, price, sl, tp, rr, long_score, short_score, rsi, motivos, current_candle_time):
    motivos_txt = "\n".join([f"- {m}" for m in motivos[:4]]) if motivos else "- Falta confirmación final del sistema."
    return f"""⚠️ <b>SETUP EN FORMACIÓN</b>

Dirección probable: <b>{direction}</b>
Par: {symbol}
Estrategia: {estrategia}

Score dirección: {score}/{min_score}
Long Score: {long_score}/9
Short Score: {short_score}/9
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
Sesgo nuevo: <b>{market_bias}</b>
Escenario: {escenario}

Precio: {fmt0(price)}
4H: {t4}
1H: {t1}
15M: {t15}
5M: {t5}
Estructura 5M: {structure}
RSI 15M: {format_number(rsi, 2)}

Vela 5M: {current_candle_time}
"""


def build_risk_msg(symbol, direction, price, sl, tp, risk_points, tp_atr_multiple, rr, current_candle_time):
    return f"""⚠️ <b>ALERTA DE RIESGO / OBJETIVO EXIGENTE</b>

Par: {symbol}
Dirección calculada: {direction}

Entrada: {fmt0(price)}
SL: {fmt0(sl)}
TP: {fmt0(tp)}
Distancia SL: {fmt0(risk_points)} pts
TP en ATR: {format_number(tp_atr_multiple, 2)} ATR
RR: {format_number(rr, 2)}

Objetivo o stop demasiado amplio. Revisar antes de operar.
Vela 5M: {current_candle_time}
"""


# =========================
# APP
# =========================

st.title("BTC/USDT FUTUROS DASHBOARD PRO")
st.caption("Sistema objetivo: tendencia + liquidez + estructura + score + riesgo + backtesting + alertas estratégicas. No es consejo financiero.")

try:
    df_1d, df_4h, df_1h, df_15m, df_5m = load_all_data()
    levels = liquidity_levels(df_15m)
    price = df_5m["close"].iloc[-1]
    current_candle_time = df_5m["time"].iloc[-1].strftime("%Y-%m-%d %H:%M:%S")

    t1d, t4, t1, t15, t5 = trend_state(df_1d), trend_state(df_4h), trend_state(df_1h), trend_state(df_15m), trend_state(df_5m)
    rsi_15 = df_15m["rsi"].iloc[-1]
    rsi_label = rsi_state(rsi_15)
    atr_15m = df_15m["atr"].iloc[-1]
    structure = structure_state(df_5m)
    long_score = score_direction("LONG", df_4h, df_1h, df_15m, df_5m, levels)
    short_score = score_direction("SHORT", df_4h, df_1h, df_15m, df_5m, levels)
    escenario, market_bias = detect_market_intention(price, df_4h, df_1h, df_15m, levels)
    candidate_direction = choose_candidate_direction(estrategia, long_score, short_score, t1d, t4, structure, price, df_15m, df_5m, levels)
    sl_calc, tp_calc, risk_points_calc = technical_levels(candidate_direction, df_5m, price, rr_target)
    tp_distance_calc = abs(tp_calc - price) if not pd.isna(tp_calc) else np.nan
    tp_atr_multiple = tp_distance_calc / atr_15m if not pd.isna(tp_distance_calc) and not pd.isna(atr_15m) and atr_15m > 0 else np.nan
    rr_real = calculate_rr(price, sl_calc, tp_calc, candidate_direction)

    trade_valid, motivos_bloqueo = validate_trade(
        estrategia, candidate_direction, long_score, short_score, min_score, risk_pct, rr_real, min_rr,
        risk_points_calc, atr_15m, market_bias, structure, price, levels, max_atr_multiplier,
        df_15m, df_5m, filter_hours, avoid_weekends
    )
    decision = candidate_direction if trade_valid else "NO_OPERAR"
    btc_size, notional, risk_usd, margin_needed = position_size(price, sl_calc, account_usd, risk_pct, leverage)
    profit_usd = risk_usd * rr_target
    profit_pct = (profit_usd / account_usd) * 100
    loss_pct = (risk_usd / account_usd) * 100
    quality_score, quality_label = setup_quality(long_score, short_score, candidate_direction, rr_real, risk_points_calc, atr_15m, trade_valid)
    raw_direction_score = direction_score(candidate_direction, long_score, short_score)

    current_signal_row = {
        "fecha": datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S"),
        "vela_5m": current_candle_time,
        "estrategia": estrategia,
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
        "distancia_sl_pts": risk_points_calc,
        "distancia_tp_pts": tp_distance_calc,
        "tp_atr_multiple": tp_atr_multiple,
        "cuenta_usdt": account_usd,
        "riesgo_pct": risk_pct_input,
        "riesgo_usdt": risk_usd,
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

    valid_msg = build_valid_signal_msg(decision, SYMBOL, estrategia, price, sl_calc, tp_calc, rr_real, quality_label, quality_score, long_score, short_score, rsi_15, atr_15m, current_candle_time)
    almost_msg = build_almost_msg(candidate_direction, SYMBOL, estrategia, raw_direction_score, min_score, price, sl_calc, tp_calc, rr_real, long_score, short_score, rsi_15, motivos_bloqueo, current_candle_time)
    bias_msg = build_bias_msg(SYMBOL, market_bias, escenario, t4, t1, t15, t5, structure, price, rsi_15, current_candle_time)
    risk_msg = build_risk_msg(SYMBOL, candidate_direction, price, sl_calc, tp_calc, risk_points_calc, tp_atr_multiple, rr_real, current_candle_time)

    auto_saved_now = False
    alert_events = []

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
        alert_almost_setups
        and not trade_valid
        and candidate_direction in ["LONG", "SHORT"]
        and raw_direction_score >= max(1, min_score - almost_score_gap)
        and long_score != short_score
        and not pd.isna(rr_real)
        and rr_real >= min_rr
        and not pd.isna(risk_points_calc)
        and not pd.isna(atr_15m)
        and risk_points_calc <= atr_15m * max_atr_multiplier
    )
    if almost_condition:
        almost_key = f"ALMOST_{current_candle_time}_{estrategia}_{candidate_direction}_{raw_direction_score}_{min_score}"
        ok, resp = send_alert_once(almost_key, "setup_en_formacion", almost_msg, telegram_enabled, discord_enabled, discord_webhook_url, telegram_bot_token, telegram_chat_id)
        if ok:
            alert_events.append("⚠️ Setup en formación enviado.")

    current_state_key = f"{market_bias}_{t4}_{t1}_{t15}_{t5}_{structure}"
    previous_state_key = load_market_state()
    if alert_bias_change and previous_state_key and previous_state_key != current_state_key:
        bias_key = f"BIAS_{current_candle_time}_{current_state_key}"
        ok, resp = send_alert_once(bias_key, "cambio_sesgo", bias_msg, telegram_enabled, discord_enabled, discord_webhook_url, telegram_bot_token, telegram_chat_id)
        if ok:
            alert_events.append("🔄 Cambio de sesgo enviado.")
    if previous_state_key != current_state_key:
        save_market_state(current_state_key)

    risk_warning_condition = (
        alert_risk_warning
        and candidate_direction in ["LONG", "SHORT"]
        and not pd.isna(tp_atr_multiple)
        and tp_atr_multiple >= 4
        and not pd.isna(risk_points_calc)
        and not pd.isna(atr_15m)
        and risk_points_calc >= atr_15m * max_atr_multiplier
    )
    if risk_warning_condition:
        risk_key = f"RISK_{current_candle_time}_{estrategia}_{candidate_direction}_{round(float(tp_atr_multiple), 1)}"
        ok, resp = send_alert_once(risk_key, "riesgo_objetivo_exigente", risk_msg, telegram_enabled, discord_enabled, discord_webhook_url, telegram_bot_token, telegram_chat_id)
        if ok:
            alert_events.append("⚠️ Alerta de riesgo enviada.")

    if decision == "LONG":
        st.success("🟢 LONG PERMITIDO")
    elif decision == "SHORT":
        st.error("🔴 SHORT PERMITIDO")
    else:
        st.warning(f"⚪ NO OPERAR | Escenario calculado: {candidate_direction}")

    if auto_saved_now:
        st.info("📡 Señal válida capturada automáticamente.")
    for event in alert_events:
        st.info(event)

    st.markdown(f"## Calidad del setup: {quality_label} · {quality_score}/10")
    st.divider()

    if telegram_enabled or discord_enabled:
        st.info("Alertas estratégicas activas. El sistema evita duplicados por vela/estado usando alerts_sent_log.csv.")
        with st.expander("Textos de alerta actuales"):
            st.code(valid_msg, language="text")
            st.code(almost_msg, language="text")
            st.code(bias_msg, language="text")

    q1, q2, q3, q4 = st.columns(4)
    q1.metric("Calidad del setup", quality_label, f"{quality_score}/10")
    q2.metric("Distancia al SL", f"{risk_points_calc:,.0f} pts" if not pd.isna(risk_points_calc) else "—", f"ATR 15M: {atr_15m:,.0f} pts" if not pd.isna(atr_15m) else "—")
    q3.metric("Setup calculado", candidate_direction, f"RR: {rr_real:.2f}" if not pd.isna(rr_real) else "—")
    q4.metric("Distancia al TP", f"{tp_distance_calc:,.0f} pts" if not pd.isna(tp_distance_calc) else "—", f"{tp_atr_multiple:.2f} ATR" if not pd.isna(tp_atr_multiple) else "—")

    with st.expander("📌 Motivo de la decisión", expanded=not mobile_compact):
        st.write(f"**Estrategia activa:** {estrategia}")
        st.write(f"**Escenario:** {escenario}")
        st.write(f"**Dirección calculada:** {candidate_direction}")
        st.write(f"**Estructura 5M:** {structure}")
        st.write(f"**Long Score:** {long_score}/9")
        st.write(f"**Short Score:** {short_score}/9")
        st.write(f"**RR real:** {format_number(rr_real, 2)}")
        st.write(f"**ATR 15M:** {format_number(atr_15m, 2)} puntos")
        st.write(f"**Distancia SL:** {format_number(risk_points_calc, 2)} puntos")
        st.write(f"**Distancia TP:** {format_number(tp_distance_calc, 2)} puntos")
        if trade_valid:
            st.success(f"Setup válido para estrategia: {estrategia}.")
        else:
            for motivo in motivos_bloqueo:
                st.warning(motivo)

    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Precio BTCUSDT", format_number(price, 2))
    col2.metric("Long Score", f"{long_score}/9")
    col3.metric("Short Score", f"{short_score}/9")
    col4.metric("RSI 15M", f"{rsi_15:.2f}" if not pd.isna(rsi_15) else "—", rsi_label)
    st.divider()

    c1, c2, c3, c4, c5 = st.columns(5)
    c1.metric("24H", trend_icon(t1d))
    c2.metric("4H", trend_icon(t4))
    c3.metric("1H", trend_icon(t1))
    c4.metric("15M", trend_icon(t15))
    c5.metric("5M", trend_icon(t5))
    st.divider()

    g1, g2, g3, g4, g5, g6 = st.columns(6)
    g1.metric("Cuenta", f"{account_usd:.0f} USDT")
    g2.metric("Riesgo", f"{risk_usd:.0f} USDT", f"{loss_pct:.2f}%")
    g3.metric("Ganancia TP", f"+{profit_usd:.0f} USDT", f"{profit_pct:.2f}%")
    g4.metric("Tamaño", f"{btc_size:.4f} BTC")
    g5.metric("Nocional", f"{notional:.0f} USDT")
    g6.metric("Margen", f"{margin_needed:.0f} USDT")

    r1, r2, r3, r4, r5, r6 = st.columns(6)
    r1.metric("Entrada", f"{price:,.0f}")
    r2.metric("SL técnico", f"{sl_calc:,.0f}" if not pd.isna(sl_calc) else "—")
    r3.metric("TP automático", f"{tp_calc:,.0f}" if not pd.isna(tp_calc) else "—")
    r4.metric("Distancia SL", f"{risk_points_calc:,.0f} pts" if not pd.isna(risk_points_calc) else "—")
    r5.metric("Distancia TP", f"{tp_distance_calc:,.0f} pts" if not pd.isna(tp_distance_calc) else "—")
    r6.metric("RR real", f"{rr_real:.2f}" if not pd.isna(rr_real) else "—")
    st.divider()

    chart_df = df_15m.tail(100 if mobile_compact else 150).copy()
    fig = go.Figure()
    fig.add_trace(go.Candlestick(x=chart_df["time"], open=chart_df["open"], high=chart_df["high"], low=chart_df["low"], close=chart_df["close"], name="BTCUSDT"))
    fig.add_trace(go.Scatter(x=chart_df["time"], y=chart_df["ema20"], mode="lines", name="EMA 20", line=dict(color="#ff6b57", width=2)))
    fig.add_trace(go.Scatter(x=chart_df["time"], y=chart_df["ema50"], mode="lines", name="EMA 50", line=dict(color="#18c29c", width=2)))
    fig.add_trace(go.Scatter(x=chart_df["time"], y=chart_df["ema200"], mode="lines", name="EMA 200", line=dict(color="#9b5cff", width=2)))
    for name, value in levels.items():
        if not pd.isna(value):
            fig.add_hline(y=value, line_dash="dot", line_color="gray", annotation_text=name, annotation_position="right")
    should_show_trade_levels = trade_valid or show_levels_when_no_trade
    if should_show_trade_levels and not pd.isna(sl_calc):
        fig.add_hline(y=sl_calc, line_color="red", line_width=3, annotation_text="SL")
    if should_show_trade_levels and not pd.isna(tp_calc):
        fig.add_hline(y=tp_calc, line_color="green", line_width=3, annotation_text="TP")
    fig.add_hline(y=price, line_color="black", line_width=3, annotation_text="Entrada")
    fig.update_layout(template="plotly_white", height=500 if mobile_compact else 700, xaxis_rangeslider_visible=False, title="BTCUSDT 15M - Velas + EMAs + Liquidez + SL/TP", margin=dict(l=20, r=20, t=50, b=20))
    st.plotly_chart(fig, use_container_width=True)
    st.divider()

    st.subheader("🧪 Backtesting automático")
    with st.spinner("Calculando backtest..."):
        bt_results, bt_stats = run_simple_backtest(backtest_tf, backtest_period, estrategia, min_score, rr_target, min_rr, max_atr_multiplier, filter_hours, avoid_weekends)
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
            st.plotly_chart(eq_fig, use_container_width=True)
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
    if not combined_hist.empty and "resultado" in combined_hist.columns:
        closed_real = combined_hist[combined_hist["resultado"].isin(["TP", "SL"])].copy()
    else:
        closed_real = pd.DataFrame()

    if not closed_real.empty:
        closed_real["fecha_dt"] = pd.to_datetime(closed_real["fecha"], utc=True, errors="coerce")
        closed_real = closed_real.sort_values("fecha_dt")
        closed_real["r_multiple"] = pd.to_numeric(closed_real["r_multiple"], errors="coerce").fillna(0)
        closed_real["equity_r"] = closed_real["r_multiple"].cumsum()
        real_fig = go.Figure()
        real_fig.add_trace(go.Scatter(x=closed_real["fecha_dt"], y=closed_real["equity_r"], mode="lines+markers", name="Equity real R"))
        real_fig.update_layout(template="plotly_white", height=350, title="Equity curve real de señales guardadas", margin=dict(l=20, r=20, t=50, b=20))
        st.plotly_chart(real_fig, use_container_width=True)
    else:
        st.info("La equity curve real aparece cuando haya señales cerradas en TP o SL.")

    st.subheader("🖼️ Historial visual de operaciones")
    if not combined_hist.empty:
        show_cols = [c for c in ["fecha", "vela_5m", "origen", "estrategia", "decision", "direccion_calculada", "calidad_score", "entrada", "sl", "tp", "resultado", "r_multiple", "rr_real", "motivos_bloqueo"] if c in combined_hist.columns]
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

    st.subheader("⏰ Filtro horario")
    st.write("Activo" if filter_hours else "Inactivo")
    st.caption("Filtro usado: Londres 07:00-10:00 UTC y NY 13:00-16:00 UTC. Fin de semana bloqueado si está activado.")

    with st.expander("📘 Reglas del sistema"):
        st.write("""
        - Score menor al mínimo configurado = NO OPERAR.
        - RR real menor al mínimo configurado = NO OPERAR.
        - Riesgo mayor al 1% = NO OPERAR.
        - Distancia al TP mide si el objetivo es realista respecto al ATR.
        - Filtro horario opcional: Londres / NY.
        - Captura automática guarda señales válidas sin tocar el botón.
        - Telegram/Discord envían solo alertas nuevas; se evita spam con alerts_sent_log.csv.
        - Alertas válidas: solo LONG/SHORT aprobados por el sistema.
        - Setup en formación: avisa cuando falta poco para cumplir el score/filtros.
        - Cambio de sesgo: avisa cuando cambia la lectura fuerte del mercado.
        - Auto refresh mantiene el sistema atento mientras la app esté abierta.
        - Ranking de estrategias muestra cuáles rinden mejor por expectativa.
        - Estadísticas 30D ayudan a saber si el sistema sigue funcionando ahora.
        - Equity curve real usa señales manuales y automáticas ya validadas.
        """)

    st.caption(f"Última actualización local: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

except Exception as e:
    st.error("Hubo un error cargando el dashboard.")
    st.exception(e)
