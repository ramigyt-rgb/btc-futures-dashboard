
1 de 2,649
fut_core_alertas_pro

Rami Char <ramigyt@gmail.com>
Archivos adjuntos
1:55 p.m. (hace 0 minutos)
para rami-albo

 Un archivo adjunto
  •  Analizado por Gmail
import os
import hashlib
import time
from datetime import datetime

import ccxt
import numpy as np
import pandas as pd

try:
    import requests
except Exception:
    requests = None

# =========================
# CONFIG GENERAL
# =========================

SIGNALS_FILE = os.getenv("SIGNALS_FILE", "signals_log.csv")
AUTO_SIGNALS_FILE = os.getenv("AUTO_SIGNALS_FILE", "auto_signals_log.csv")
ALERTS_FILE = os.getenv("ALERTS_FILE", "alerts_sent_log.csv")
MARKET_STATE_FILE = os.getenv("MARKET_STATE_FILE", "market_state.csv")
MARKET_SNAPSHOTS_FILE = os.getenv("MARKET_SNAPSHOTS_FILE", "market_snapshots.csv")
FVG_LOG_FILE = os.getenv("FVG_LOG_FILE", "fvg_log.csv")
USERS_FILE = os.getenv("USERS_FILE", "users.csv")

SYMBOL = os.getenv("SYMBOL", "BTC/USDT:USDT")
LIMIT = int(os.getenv("LIMIT", "300"))
ACCESS_KEY = os.getenv("ACCESS_KEY", "1234")

ALERT_INTERVAL_SECONDS = int(os.getenv("ALERT_INTERVAL_SECONDS", "60"))
TELEGRAM_ENABLED = os.getenv("TELEGRAM_ENABLED", "1") == "1"

STRATEGIES = [
    "Tendencia + Liquidez",
    "Pullback EMA50",
    "Sweep de Liquidez",
    "Ruptura de Estructura",
    "Reversión Extrema",
    "FVG + Tendencia",
]

# =========================
# HELPERS
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


def hash_password(password: str) -> str:
    return hashlib.sha256(str(password).encode("utf-8")).hexdigest()


def safe_read_csv(file_path):
    if os.path.exists(file_path):
        try:
            return pd.read_csv(file_path)
        except Exception:
            return pd.DataFrame()
    return pd.DataFrame()


def save_row(file_path, row):
    new = pd.DataFrame([row])
    old = safe_read_csv(file_path)
    out = pd.concat([old, new], ignore_index=True) if not old.empty else new
    out.to_csv(file_path, index=False)


def save_rows(file_path, rows, key_col=None):
    if not rows:
        return 0
    old = safe_read_csv(file_path)
    new = pd.DataFrame(rows)
    if key_col and key_col in new.columns:
        old_keys = set(old[key_col].astype(str)) if (not old.empty and key_col in old.columns) else set()
        new = new[~new[key_col].astype(str).isin(old_keys)]
    if new.empty:
        return 0
    out = pd.concat([old, new], ignore_index=True) if not old.empty else new
    out.to_csv(file_path, index=False)
    return len(new)


def init_users_file():
    if not os.path.exists(USERS_FILE):
        pd.DataFrame([{"usuario": "demo", "password_hash": hash_password("demo"), "rol": "cliente"}]).to_csv(USERS_FILE, index=False)


def check_login(usuario, password):
    init_users_file()
    users = safe_read_csv(USERS_FILE)
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
# TELEGRAM
# =========================

def get_secret_value(key, default=""):
    return os.getenv(key, default)


def get_telegram_credentials(token_override="", chat_id_override=""):
    token = token_override or get_secret_value("TELEGRAM_BOT_TOKEN", "")
    chat_id = chat_id_override or get_secret_value("TELEGRAM_CHAT_ID", "")
    return str(token).strip(), str(chat_id).strip()


def send_telegram_message(text, token_override="", chat_id_override=""):
    if requests is None:
        return False, "requests no instalado. Ejecutá: pip install requests"
    token, chat_id = get_telegram_credentials(token_override, chat_id_override)
    if not token or not chat_id:
        return False, "Falta TELEGRAM_BOT_TOKEN o TELEGRAM_CHAT_ID en variables de entorno."
    try:
        url = f"https://api.telegram.org/bot{token}/sendMessage"
        r = requests.post(
            url,
            data={"chat_id": chat_id, "text": text, "parse_mode": "HTML", "disable_web_page_preview": True},
            timeout=15,
        )
        return r.ok, r.text[:700]
    except Exception as e:
        return False, str(e)


def alert_already_sent(alert_key):
    df = safe_read_csv(ALERTS_FILE)
    return not df.empty and "alert_key" in df.columns and str(alert_key) in set(df["alert_key"].astype(str))


def save_alert_sent(alert_key, tipo, canal, mensaje, response=""):
    save_row(ALERTS_FILE, {
        "fecha": datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S"),
        "alert_key": str(alert_key),
        "tipo": tipo,
        "canal": canal,
        "mensaje": str(mensaje)[:1500],
        "response": str(response)[:700],
    })


def send_alert_once(alert_key, tipo, mensaje, telegram_on=True, token_override="", chat_id_override=""):
    if alert_already_sent(alert_key):
        return False, "Alerta ya enviada"
    if not telegram_on:
        return False, "Telegram desactivado"
    ok, resp = send_telegram_message(mensaje, token_override, chat_id_override)
    if ok:
        save_alert_sent(alert_key, tipo, "telegram", mensaje, resp)
    return ok, resp


def send_heartbeat_once_per_hour(row):
    hour_key = datetime.utcnow().strftime("%Y-%m-%d %H")
    key = f"HEARTBEAT_{hour_key}_{row['vela_5m']}"
    msg = build_yellow_info_msg(row, title="🟡 BTC BOT ACTIVO", subtitle="Chequeo horario del worker")
    return send_alert_once(key, "heartbeat", msg, TELEGRAM_ENABLED)

# =========================
# DATA
# =========================

def make_exchange():
    return ccxt.okx({"enableRateLimit": True, "options": {"defaultType": "swap"}})


def get_ohlcv(timeframe, limit=LIMIT):
    data = make_exchange().fetch_ohlcv(SYMBOL, timeframe=timeframe, limit=limit)
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
    targets = {k: v for k, v in clean.items() if (v > price if direction == "LONG" else v < price)}
    if not targets:
        return None, np.nan, np.nan
    name, level = min(targets.items(), key=lambda item: abs(item[1] - price))
    return name, level, abs(level - price)


def detect_fvg_zones(df, min_atr_mult=0.20, lookback=120):
    if df is None or df.empty or len(df) < 5:
        return pd.DataFrame()
    d = df.tail(lookback).copy().reset_index(drop=True)
    zones = []
    for i in range(2, len(d)):
        c0 = d.iloc[i - 2]
        c2 = d.iloc[i]
        atr = safe_float(d["atr"].iloc[i], np.nan)
        min_gap = atr * min_atr_mult if not pd.isna(atr) and atr > 0 else 0
        bull_gap = c2["low"] - c0["high"]
        bear_gap = c0["low"] - c2["high"]
        if bull_gap > min_gap:
            zones.append({
                "tipo": "BULLISH_FVG",
                "direction": "LONG",
                "time": c2["time"],
                "x0": c0["time"],
                "x1": c2["time"],
                "low": c0["high"],
                "high": c2["low"],
                "mid": (c0["high"] + c2["low"]) / 2,
                "gap_pts": bull_gap,
                "gap_atr": bull_gap / atr if not pd.isna(atr) and atr > 0 else np.nan,
                "mitigated": False,
            })
        if bear_gap > min_gap:
            zones.append({
                "tipo": "BEARISH_FVG",
                "direction": "SHORT",
                "time": c2["time"],
                "x0": c0["time"],
                "x1": c2["time"],
                "low": c2["high"],
                "high": c0["low"],
                "mid": (c2["high"] + c0["low"]) / 2,
                "gap_pts": bear_gap,
                "gap_atr": bear_gap / atr if not pd.isna(atr) and atr > 0 else np.nan,
                "mitigated": False,
            })
    out = pd.DataFrame(zones)
    if out.empty:
        return out
    for idx, z in out.iterrows():
        future = d[d["time"] > z["time"]]
        if future.empty:
            continue
        out.at[idx, "mitigated"] = bool((future["low"] <= z["mid"]).any() if z["direction"] == "LONG" else (future["high"] >= z["mid"]).any())
    out["fvg_key"] = out.apply(lambda r: f"{r['time']}_{r['tipo']}_{round(float(r['low']), 2)}_{round(float(r['high']), 2)}", axis=1)
    return out.sort_values("time").reset_index(drop=True)


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
        if long_score >= short_score and nearest_fvg(price, fvg_df, "LONG", True):
            return "LONG"
        if short_score > long_score and nearest_fvg(price, fvg_df, "SHORT", True):
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


def technical_levels(direction, df_5m, entry, rr_target, fvg_zone=None):
    recent = df_5m.tail(30)
    atr = df_5m["atr"].iloc[-1]
    if pd.isna(atr) or atr <= 0:
        atr = 250
    buffer = atr * 0.35
    if direction == "LONG":
        base_low = recent["low"].min()
        if fvg_zone and not pd.isna(fvg_zone.get("low", np.nan)):
            base_low = min(base_low, fvg_zone["low"])
        sl = base_low - buffer
        risk_points = entry - sl
        tp = entry + risk_points * rr_target
    elif direction == "SHORT":
        base_high = recent["high"].max()
        if fvg_zone and not pd.isna(fvg_zone.get("high", np.nan)):
            base_high = max(base_high, fvg_zone["high"])
        sl = base_high + buffer
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


def strategy_filter(estrategia, direction, df_1h, df_15m, df_5m, levels, structure, market_bias, fvg_df=None, use_fvg_filter=False, fvg_max_distance_atr=1.5):
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
        if direction == "LONG" and not (trend_state(df_1h) == "BULL" or trend_state(df_15m) == "BULL"):
            motivos.append("FVG + Tendencia: falta tendencia alcista en 1H/15M.")
        if direction == "SHORT" and not (trend_state(df_1h) == "BEAR" or trend_state(df_15m) == "BEAR"):
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


def is_allowed_trading_time(ts, use_filter=True, avoid_weekends=True):
    if pd.isna(ts):
        return False
    if avoid_weekends and ts.weekday() >= 5:
        return False
    if not use_filter:
        return True
    return (7 <= ts.hour < 10) or (13 <= ts.hour < 16)


def validate_trade(estrategia, direction, long_score, short_score, min_score, risk_pct, rr_real, min_rr, risk_points, atr_15m, market_bias, structure, price, levels, max_atr_multiplier, df_1h, df_15m, df_5m, use_time_filter=False, avoid_weekends_filter=False, fvg_df=None, use_fvg_filter=False, fvg_max_distance_atr=1.5):
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
    motivos.extend(strategy_filter(estrategia, direction, df_1h, df_15m, df_5m, levels, structure, market_bias, fvg_df, use_fvg_filter, fvg_max_distance_atr))
    return len(motivos) == 0, motivos

# =========================
# MENSAJES PRO
# =========================

def signal_key(row):
    return f"{row['vela_5m']}_{row['estrategia']}_{row['decision']}_{row['direccion_calculada']}"


def direction_score(direction, long_score, short_score):
    return long_score if direction == "LONG" else short_score


def _levels_text(levels, price):
    rows = []
    for name, value in levels.items():
        if not pd.isna(value):
            dist = abs(float(value) - float(price))
            rows.append((dist, f"{name}: {fmt0(value)} ({fmt0(dist)} pts)"))
    rows = sorted(rows, key=lambda x: x[0])[:4]
    return "\n".join([r[1] for r in rows]) if rows else "—"


def _motivos_text(motivos, max_items=6):
    if not motivos:
        return "- Sin bloqueos críticos."
    return "\n".join([f"- {m}" for m in motivos[:max_items]])


def build_green_signal_msg(row, levels, motivos=None):
    emoji = "🟢" if row["decision"] == "LONG" else "🔴"
    title = "SEÑAL LONG VÁLIDA" if row["decision"] == "LONG" else "SEÑAL SHORT VÁLIDA"
    return f"""{emoji} <b>{title} - BTC DASHBOARD PRO</b>

<b>OPERACIÓN APROBADA POR SISTEMA</b>

Par: {SYMBOL}
Estrategia: {row['estrategia']}
Calidad: <b>{row['calidad_setup']} {row['calidad_score']}/10</b>
Escenario: {row['escenario']}
Estructura 5M: {row['estructura']}
FVG: {row['fvg_estado']}

<b>NIVELES</b>
Entrada: <b>{fmt0(row['entrada'])}</b>
SL: <b>{fmt0(row['sl'])}</b>
TP: <b>{fmt0(row['tp'])}</b>
RR: <b>{format_number(row['rr_real'], 2)}</b>
Distancia SL: {fmt0(row['distancia_sl_pts'])} pts
Distancia TP: {fmt0(row['distancia_tp_pts'])} pts
TP en ATR: {format_number(row['tp_atr_multiple'], 2)} ATR

<b>RIESGO / TAMAÑO</b>
Cuenta: {format_number(row['cuenta_usdt'], 2)} USDT
Riesgo real: {format_number(row['riesgo_usdt_real'], 2)} USDT
Ganancia TP estimada: {format_number(row['ganancia_tp_usdt'], 2)} USDT
Nocional real: {format_number(row['notional_real'], 2)} USDT
Nocional máx: {format_number(row['notional_max'], 2)} USDT
Capado por margen: {row['notional_capado']}

<b>CONFIRMACIONES</b>
Long Score: {row['long_score']}/10
Short Score: {row['short_score']}/10
RSI 15M: {format_number(row['rsi_15m'], 2)}
ATR 15M: {fmt0(row['atr_15m'])} pts
24H: {row['24h']} | 4H: {row['4h']} | 1H: {row['1h']} | 15M: {row['15m']} | 5M: {row['5m']}

<b>LIQUIDEZ CERCANA</b>
{_levels_text(levels, row['precio'])}

Vela 5M: {row['vela_5m']}
Generado UTC: {row['fecha']}"""


def build_yellow_setup_msg(row, levels, motivos):
    return f"""🟡 <b>SETUP EN FORMACIÓN - BTC DASHBOARD PRO</b>

Todavía <b>NO ES ENTRADA</b>.
Dirección probable: <b>{row['direccion_calculada']}</b>
Par: {SYMBOL}
Estrategia: {row['estrategia']}
Calidad actual: {row['calidad_setup']} {row['calidad_score']}/10
Escenario: {row['escenario']}
FVG: {row['fvg_estado']}

<b>NIVELES TEÓRICOS</b>
Entrada: {fmt0(row['entrada'])}
SL: {fmt0(row['sl'])}
TP: {fmt0(row['tp'])}
RR: {format_number(row['rr_real'], 2)}
Distancia SL: {fmt0(row['distancia_sl_pts'])} pts
TP en ATR: {format_number(row['tp_atr_multiple'], 2)} ATR

<b>SCORES</b>
Long Score: {row['long_score']}/10
Short Score: {row['short_score']}/10
RSI 15M: {format_number(row['rsi_15m'], 2)}
ATR 15M: {fmt0(row['atr_15m'])} pts
24H: {row['24h']} | 4H: {row['4h']} | 1H: {row['1h']} | 15M: {row['15m']} | 5M: {row['5m']}

<b>FALTA PARA VALIDAR</b>
{_motivos_text(motivos)}

<b>LIQUIDEZ CERCANA</b>
{_levels_text(levels, row['precio'])}

Vela 5M: {row['vela_5m']}
Generado UTC: {row['fecha']}"""


def build_red_no_trade_msg(row, levels, motivos):
    return f"""🔴 <b>NO OPERAR - BTC DASHBOARD PRO</b>

El sistema bloquea entrada.
Dirección calculada: <b>{row['direccion_calculada']}</b>
Par: {SYMBOL}
Estrategia: {row['estrategia']}
Calidad: {row['calidad_setup']} {row['calidad_score']}/10
Escenario: {row['escenario']}
FVG: {row['fvg_estado']}

<b>MOTIVOS DE BLOQUEO</b>
{_motivos_text(motivos)}

<b>LECTURA ACTUAL</b>
Precio: {fmt0(row['precio'])}
Long Score: {row['long_score']}/10
Short Score: {row['short_score']}/10
RSI 15M: {format_number(row['rsi_15m'], 2)}
ATR 15M: {fmt0(row['atr_15m'])} pts
Estructura 5M: {row['estructura']}
24H: {row['24h']} | 4H: {row['4h']} | 1H: {row['1h']} | 15M: {row['15m']} | 5M: {row['5m']}

<b>NIVELES TEÓRICOS NO OPERABLES</b>
Entrada: {fmt0(row['entrada'])}
SL: {fmt0(row['sl'])}
TP: {fmt0(row['tp'])}
RR: {format_number(row['rr_real'], 2)}
Distancia SL: {fmt0(row['distancia_sl_pts'])} pts
TP en ATR: {format_number(row['tp_atr_multiple'], 2)} ATR

<b>LIQUIDEZ CERCANA</b>
{_levels_text(levels, row['precio'])}

Vela 5M: {row['vela_5m']}
Generado UTC: {row['fecha']}"""


def build_yellow_info_msg(row, title="🟡 BTC DASHBOARD PRO", subtitle="Lectura informativa"):
    return f"""{title}

<b>{subtitle}</b>

Precio: {fmt0(row['precio'])}
Decisión: {row['decision']}
Dirección calculada: {row['direccion_calculada']}
Calidad: {row['calidad_setup']} {row['calidad_score']}/10
Long Score: {row['long_score']}/10 | Short Score: {row['short_score']}/10
RSI 15M: {format_number(row['rsi_15m'], 2)}
ATR 15M: {fmt0(row['atr_15m'])} pts
FVG: {row['fvg_estado']}
24H: {row['24h']} | 4H: {row['4h']} | 1H: {row['1h']} | 15M: {row['15m']} | 5M: {row['5m']}

Vela 5M: {row['vela_5m']}
UTC: {row['fecha']}"""

# =========================
# ANALYZE
# =========================

def analyze_market(config=None):
    c = {
        "estrategia": os.getenv("ESTRATEGIA", "FVG + Tendencia"),
        "account_usd": float(os.getenv("ACCOUNT_USD", "500")),
        "risk_pct_input": float(os.getenv("RISK_PCT_INPUT", "1.0")),
        "leverage": float(os.getenv("LEVERAGE", "5")),
        "min_score": int(os.getenv("MIN_SCORE", "7")),
        "rr_target": float(os.getenv("RR_TARGET", "2.0")),
        "min_rr": float(os.getenv("MIN_RR", "1.8")),
        "max_atr_multiplier": float(os.getenv("MAX_ATR_MULTIPLIER", "2.0")),
        "filter_hours": os.getenv("FILTER_HOURS", "1") == "1",
        "avoid_weekends": os.getenv("AVOID_WEEKENDS", "1") == "1",
        "fvg_min_atr": float(os.getenv("FVG_MIN_ATR", "0.20")),
        "fvg_max_distance_atr": float(os.getenv("FVG_MAX_DISTANCE_ATR", "1.5")),
        "use_fvg_filter": os.getenv("USE_FVG_FILTER", "0") == "1",
    }
    if config:
        c.update(config)

    df_1d, df_4h, df_1h, df_15m, df_5m = load_all_data()
    levels = liquidity_levels(df_15m)
    fvg_df = detect_fvg_zones(df_15m, c["fvg_min_atr"], 120)

    price = df_5m["close"].iloc[-1]
    current_candle_time = df_5m["time"].iloc[-1].strftime("%Y-%m-%d %H:%M:%S")
    t1d, t4, t1, t15, t5 = trend_state(df_1d), trend_state(df_4h), trend_state(df_1h), trend_state(df_15m), trend_state(df_5m)
    rsi_15 = df_15m["rsi"].iloc[-1]
    atr_15m = df_15m["atr"].iloc[-1]
    structure = structure_state(df_5m)

    long_score = score_direction("LONG", df_4h, df_1h, df_15m, df_5m, levels, fvg_df, c["fvg_max_distance_atr"])
    short_score = score_direction("SHORT", df_4h, df_1h, df_15m, df_5m, levels, fvg_df, c["fvg_max_distance_atr"])
    escenario, market_bias = detect_market_intention(price, df_4h, df_1h, df_15m, levels)
    candidate_direction = choose_candidate_direction(c["estrategia"], long_score, short_score, t1d, t4, structure, price, df_15m, df_5m, levels, fvg_df)

    fvg_label, fvg_zone, fvg_distance_atr, fvg_valid = fvg_state(price, atr_15m, fvg_df, candidate_direction, c["fvg_max_distance_atr"])
    sl_calc, tp_calc, risk_points_calc = technical_levels(candidate_direction, df_5m, price, c["rr_target"], fvg_zone)
    tp_distance_calc = abs(tp_calc - price) if not pd.isna(tp_calc) else np.nan
    tp_atr_multiple = tp_distance_calc / atr_15m if not pd.isna(tp_distance_calc) and not pd.isna(atr_15m) and atr_15m > 0 else np.nan
    rr_real = calculate_rr(price, sl_calc, tp_calc, candidate_direction)
    risk_pct = c["risk_pct_input"] / 100

    trade_valid, motivos_bloqueo = validate_trade(
        c["estrategia"], candidate_direction, long_score, short_score, c["min_score"], risk_pct, rr_real, c["min_rr"],
        risk_points_calc, atr_15m, market_bias, structure, price, levels, c["max_atr_multiplier"],
        df_1h, df_15m, df_5m, c["filter_hours"], c["avoid_weekends"], fvg_df, c["use_fvg_filter"], c["fvg_max_distance_atr"]
    )
    decision = candidate_direction if trade_valid else "NO_OPERAR"

    btc_size, notional, risk_usd, margin_needed, risk_usd_target, notional_capped, max_notional = position_size(price, sl_calc, c["account_usd"], risk_pct, c["leverage"])
    quality_score, quality_label = setup_quality(long_score, short_score, candidate_direction, rr_real, risk_points_calc, atr_15m, trade_valid, fvg_valid)

    row = {
        "fecha": datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S"),
        "vela_5m": current_candle_time,
        "estrategia": c["estrategia"],
        "decision": decision,
        "direccion_calculada": candidate_direction,
        "calidad_setup": quality_label,
        "calidad_score": quality_score,
        "escenario": escenario,
        "market_bias": market_bias,
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
        "cuenta_usdt": c["account_usd"],
        "riesgo_pct": c["risk_pct_input"],
        "riesgo_usdt_objetivo": risk_usd_target,
        "riesgo_usdt_real": risk_usd,
        "notional_max": max_notional,
        "notional_real": notional,
        "notional_capado": notional_capped,
        "margen_necesario": margin_needed,
        "tamaño_btc": btc_size,
        "ganancia_tp_usdt": risk_usd * c["rr_target"],
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

    state_key = f"{market_bias}_{t4}_{t1}_{t15}_{t5}_{structure}_{fvg_label}_{decision}_{candidate_direction}"
    return {
        "row": row,
        "fvg_df": fvg_df,
        "levels": levels,
        "dfs": (df_1d, df_4h, df_1h, df_15m, df_5m),
        "trade_valid": trade_valid,
        "motivos": motivos_bloqueo,
        "market_state_key": state_key,
        "config": c,
    }

# =========================
# ALERT ENGINE CADA 1 MIN
# =========================

def should_send_almost(row, motivos, config):
    raw_score = direction_score(row["direccion_calculada"], row["long_score"], row["short_score"])
    min_score = int(config.get("min_score", 7))
    rr_ok = not pd.isna(row["rr_real"]) and row["rr_real"] >= float(config.get("min_rr", 1.8))
    atr_ok = not pd.isna(row["distancia_sl_pts"]) and not pd.isna(row["atr_15m"]) and row["distancia_sl_pts"] <= row["atr_15m"] * float(config.get("max_atr_multiplier", 2.0))
    close_score = raw_score >= max(1, min_score - 1)
    return row["decision"] == "NO_OPERAR" and row["direccion_calculada"] in ["LONG", "SHORT"] and close_score and rr_ok and atr_ok


def run_alert_cycle(config=None, send_no_trade_on_new_5m=True, send_heartbeat=False):
    analysis = analyze_market(config)
    row = analysis["row"]
    levels = analysis["levels"]
    motivos = analysis["motivos"]
    cfg = analysis["config"]

    # Guarda snapshot cada minuto para que el sistema recopile información solo.
    snapshot_key = f"SNAPSHOT_{datetime.utcnow().strftime('%Y-%m-%d %H:%M')}_{row['vela_5m']}"
    snap = row.copy()
    snap["snapshot_key"] = snapshot_key
    save_rows(MARKET_SNAPSHOTS_FILE, [snap], key_col="snapshot_key")

    # Guarda FVG nuevos.
    fvg_df = analysis["fvg_df"]
    if fvg_df is not None and not fvg_df.empty:
        fvg_rows = fvg_df.to_dict("records")
        for r in fvg_rows:
            for k, v in list(r.items()):
                if isinstance(v, pd.Timestamp):
                    r[k] = v.strftime("%Y-%m-%d %H:%M:%S")
        save_rows(FVG_LOG_FILE, fvg_rows, key_col="fvg_key")

    sent = []

    # VERDE / ROJA: señal válida LONG/SHORT. Se manda una vez por vela 5M y estrategia.
    if row["decision"] in ["LONG", "SHORT"]:
        row_auto = row.copy()
        row_auto["signal_key"] = signal_key(row_auto)
        save_rows(AUTO_SIGNALS_FILE, [row_auto], key_col="signal_key")
        color_tipo = "verde_long" if row["decision"] == "LONG" else "roja_short"
        key = f"VALID_{signal_key(row)}"
        msg = build_green_signal_msg(row, levels, motivos)
        ok, resp = send_alert_once(key, color_tipo, msg, TELEGRAM_ENABLED)
        sent.append((color_tipo, ok, resp))

    # AMARILLA: setup casi listo. Una vez por vela 5M.
    elif should_send_almost(row, motivos, cfg):
        key = f"YELLOW_SETUP_{row['vela_5m']}_{row['estrategia']}_{row['direccion_calculada']}_{row['calidad_score']}"
        msg = build_yellow_setup_msg(row, levels, motivos)
        ok, resp = send_alert_once(key, "amarilla_setup", msg, TELEGRAM_ENABLED)
        sent.append(("amarilla_setup", ok, resp))

    # ROJA: no operar. Para no spamear, solo 1 vez por vela 5M.
    elif send_no_trade_on_new_5m:
        key = f"RED_NO_TRADE_{row['vela_5m']}_{row['estrategia']}_{row['direccion_calculada']}"
        msg = build_red_no_trade_msg(row, levels, motivos)
        ok, resp = send_alert_once(key, "roja_no_operar", msg, TELEGRAM_ENABLED)
        sent.append(("roja_no_operar", ok, resp))

    # Cambio fuerte de estado/sesgo.
    previous_state = load_market_state()
    current_state = analysis["market_state_key"]
    if previous_state and previous_state != current_state:
        key = f"BIAS_CHANGE_{row['vela_5m']}_{current_state}"
        msg = build_yellow_info_msg(row, title="🟡 CAMBIO DE SESGO BTC", subtitle=f"Nuevo estado: {row['market_bias']} | {row['escenario']}")
        ok, resp = send_alert_once(key, "cambio_sesgo", msg, TELEGRAM_ENABLED)
        sent.append(("cambio_sesgo", ok, resp))
    if previous_state != current_state:
        save_market_state(current_state)

    if send_heartbeat:
        ok, resp = send_heartbeat_once_per_hour(row)
        sent.append(("heartbeat", ok, resp))

    return {"row": row, "sent": sent, "motivos": motivos}


def worker_loop(config=None):
    print("BTC Futures Worker iniciado. Envía alertas y guarda snapshots cada 1 minuto.")
    print("Para cortar: CTRL + C")
    while True:
        started = time.time()
        try:
            result = run_alert_cycle(config=config, send_no_trade_on_new_5m=True, send_heartbeat=False)
            row = result["row"]
            print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] {row['decision']} | {row['direccion_calculada']} | Precio {fmt0(row['precio'])} | Calidad {row['calidad_score']}/10 | Alertas: {result['sent']}")
        except Exception as e:
            error_msg = f"🔴 <b>ERROR WORKER BTC</b>\n\n{str(e)[:900]}\n\nUTC: {datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')}"
            print(error_msg)
            send_alert_once(f"WORKER_ERROR_{datetime.utcnow().strftime('%Y-%m-%d_%H:%M')}", "error_worker", error_msg, TELEGRAM_ENABLED)
        elapsed = time.time() - started
        time.sleep(max(5, ALERT_INTERVAL_SECONDS - elapsed))


if __name__ == "__main__":
    worker_loop()