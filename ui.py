# =========================
# TARJETA COMERCIAL / RESUMEN EJECUTIVO
# =========================
from analysis import * 
from config import *
from helpers import *
from exchange import load_all_data
from sidebar import render_sidebar
from backtest import (
    performance_stats,
    stats_by_strategy,
    last_30_days_stats,
    run_simple_backtest,
    validate_saved_signals,
    monte_carlo_simulation,
    build_r_multiples_from_sources,
    signal_key,
)
from alertas import (
    send_alert_once,
    load_market_state,
    save_market_state,
)
from telegram import (
    build_valid_signal_msg,
    build_almost_msg,
    build_bias_msg,
    build_risk_msg,
    build_market_update_msg,
)
import os
import json
import uuid
import hashlib
from pathlib import Path
from datetime import datetime
import ccxt
import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st
import streamlit.components.v1 as components

# Compatibilidad UI: variables visuales opcionales que antes vivían en fut_app.py
try:
    mobile_compact
except NameError:
    mobile_compact = False
try:
    show_fvg_zones
except NameError:
    show_fvg_zones = use_fvg_filter if "use_fvg_filter" in globals() else True
try:
    show_fvg_filter
except NameError:
    show_fvg_filter = show_fvg_zones

try:
    import requests
except Exception:
    requests = None


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
    st.markdown("""
    <style>
    .block-container{
        padding-top:1rem !important;
        padding-bottom:1rem !important;
        padding-left:2rem !important;
        padding-right:2rem !important;
        max-width:none !important;
    }
    div[data-testid="stMetric"]{
        padding:.20rem .10rem !important;
    }
    div[data-testid="stMetricLabel"]{
        font-size:.75rem !important;
        font-weight:600 !important;
    }
    div[data-testid="stMetricValue"]{
        font-size:1.35rem !important;
        font-weight:700 !important;
        line-height:1.1 !important;
    }
    div[data-testid="stMetricDelta"]{
        font-size:.65rem !important;
    }
    h1{font-size:34px !important;}
    h2{font-size:28px !important;}
    h3{font-size:22px !important;}
    h4{font-size:18px !important;}
    button[data-baseweb="tab"]{
        font-size:15px !important;
        font-weight:600 !important;
        padding:.45rem .65rem !important;
    }
    section[data-testid="stSidebar"]{
        min-width:300px !important;
        max-width:330px !important;
    }
    section[data-testid="stSidebar"] > div{
        padding-top:1rem !important;
        overflow-y:auto !important;
    }
    section[data-testid="stSidebar"] label{
        font-size:.78rem !important;
    }
    @media (max-width:1200px){
        .block-container{
            padding-left:1rem !important;
            padding-right:1rem !important;
            max-width:none !important;
        }
        section[data-testid="stSidebar"]{
            min-width:260px !important;
            max-width:280px !important;
        }
        div[data-testid="stMetricValue"]{
            font-size:0.95rem !important;
            line-height:1 !important;
        }
        div[data-testid="stMetricLabel"]{
            font-size:0.62rem !important;
        }
        div[data-testid="stMetricDelta"]{
            font-size:0.55rem !important;
        }
        h2{font-size:22px !important;}
        h3{font-size:18px !important;}
        h4{font-size:16px !important;}
        button[data-baseweb="tab"]{
            font-size:13px !important;
            padding:.35rem .45rem !important;
        }
    }
    @media (max-width:700px){
        div[data-testid="stMetricValue"]{
            font-size:0.85rem !important;
        }
        div[data-testid="stMetricLabel"]{
            font-size:0.58rem !important;
        }
        div[data-testid="stMetricDelta"]{
            font-size:0.52rem !important;
        }
    }
    </style>
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
        <div style="font-size:18px; font-weight:800; margin-bottom:12px;">
            ═══════════════════════════════<br>
            ESTADO DEL MERCADO BTC
        </div>
        <div style="font-size:14px; line-height:1.9;">
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
            Calidad: <b>{quality_label}</b> · <b>{quality_score}/10</h2>
        </div>
        <hr>
        <div style="font-size:18px; font-weight:900; color:{color};">
            DECISIÓN: {decision_txt}
        </div>
        <div style="margin-top:10px; color:#92400e; font-size:12px;">
            <b>Bloqueos / advertencias:</b><br>
            {bloqueos_txt}
        </div>
        <div style="font-size:18px; font-weight:800; margin-top:14px;">
            ═══════════════════════════════
        </div>
    </div>
    """, unsafe_allow_html=True)

# =========================
# BTC QUANT TERMINAL ULTRA PRO
# Capa adicional: mercado, derivados, inversión y riesgo.
# Diseñada para degradar de forma segura si una API externa no responde.
# =========================

def _q_float(value, default=np.nan):
    try:
        x = float(value)
        return x if np.isfinite(x) else default
    except Exception:
        return default


def _q_pct(value, digits=2):
    x = _q_float(value)
    return "—" if pd.isna(x) else f"{x:.{digits}f}%"


def _q_money(value, digits=0):
    x = _q_float(value)
    return "—" if pd.isna(x) else f"${x:,.{digits}f}"


def _q_last(series, default=np.nan):
    try:
        s = pd.to_numeric(series, errors="coerce").dropna()
        return float(s.iloc[-1]) if len(s) else default
    except Exception:
        return default


def _q_safe_div(a, b, default=np.nan):
    a, b = _q_float(a), _q_float(b)
    if pd.isna(a) or pd.isna(b) or b == 0:
        return default
    return a / b


def _q_rsi(close, period=14):
    close = pd.to_numeric(close, errors="coerce")
    delta = close.diff()
    gain = delta.clip(lower=0).ewm(alpha=1 / period, adjust=False).mean()
    loss = (-delta.clip(upper=0)).ewm(alpha=1 / period, adjust=False).mean()
    rs = gain / loss.replace(0, np.nan)
    out = 100 - (100 / (1 + rs))
    return out.fillna(50)


def _q_atr(df, period=14):
    high = pd.to_numeric(df["high"], errors="coerce")
    low = pd.to_numeric(df["low"], errors="coerce")
    close = pd.to_numeric(df["close"], errors="coerce")
    prev_close = close.shift(1)
    tr = pd.concat([
        high - low,
        (high - prev_close).abs(),
        (low - prev_close).abs(),
    ], axis=1).max(axis=1)
    return tr.ewm(alpha=1 / period, adjust=False).mean()


def _q_adx(df, period=14):
    high = pd.to_numeric(df["high"], errors="coerce")
    low = pd.to_numeric(df["low"], errors="coerce")
    close = pd.to_numeric(df["close"], errors="coerce")
    up_move = high.diff()
    down_move = -low.diff()
    plus_dm = pd.Series(np.where((up_move > down_move) & (up_move > 0), up_move, 0.0), index=df.index)
    minus_dm = pd.Series(np.where((down_move > up_move) & (down_move > 0), down_move, 0.0), index=df.index)
    atr = _q_atr(df, period).replace(0, np.nan)
    plus_di = 100 * plus_dm.ewm(alpha=1 / period, adjust=False).mean() / atr
    minus_di = 100 * minus_dm.ewm(alpha=1 / period, adjust=False).mean() / atr
    dx = 100 * (plus_di - minus_di).abs() / (plus_di + minus_di).replace(0, np.nan)
    return dx.ewm(alpha=1 / period, adjust=False).mean().fillna(0), plus_di.fillna(0), minus_di.fillna(0)


def _q_mfi(df, period=14):
    high = pd.to_numeric(df["high"], errors="coerce")
    low = pd.to_numeric(df["low"], errors="coerce")
    close = pd.to_numeric(df["close"], errors="coerce")
    volume = pd.to_numeric(df["volume"], errors="coerce").fillna(0)
    typical = (high + low + close) / 3
    flow = typical * volume
    direction = typical.diff()
    pos = flow.where(direction > 0, 0.0).rolling(period).sum()
    neg = flow.where(direction < 0, 0.0).rolling(period).sum().abs()
    ratio = pos / neg.replace(0, np.nan)
    return (100 - 100 / (1 + ratio)).fillna(50)


def _q_cmf(df, period=20):
    high = pd.to_numeric(df["high"], errors="coerce")
    low = pd.to_numeric(df["low"], errors="coerce")
    close = pd.to_numeric(df["close"], errors="coerce")
    volume = pd.to_numeric(df["volume"], errors="coerce").fillna(0)
    spread = (high - low).replace(0, np.nan)
    mfm = ((close - low) - (high - close)) / spread
    mfv = mfm.fillna(0) * volume
    return mfv.rolling(period).sum() / volume.rolling(period).sum().replace(0, np.nan)


def _q_obv(df):
    close = pd.to_numeric(df["close"], errors="coerce")
    volume = pd.to_numeric(df["volume"], errors="coerce").fillna(0)
    direction = np.sign(close.diff()).fillna(0)
    return (direction * volume).cumsum()


def prepare_quant_frame(df):
    """Agrega indicadores robustos sin modificar el dataframe original."""
    if df is None or len(df) == 0:
        return pd.DataFrame()
    q = df.copy()
    if "time" in q.columns:
        q["time"] = pd.to_datetime(q["time"], errors="coerce", utc=True)
        q = q.sort_values("time")
    for col in ["open", "high", "low", "close", "volume"]:
        if col in q.columns:
            q[col] = pd.to_numeric(q[col], errors="coerce")
    if "close" not in q.columns:
        return pd.DataFrame()
    close = q["close"]
    q["ret"] = close.pct_change()
    q["log_ret"] = np.log(close / close.shift(1))
    for p in [9, 20, 21, 50, 100, 200]:
        q[f"ema{p}"] = close.ewm(span=p, adjust=False).mean()
    for p in [20, 50, 200]:
        q[f"sma{p}"] = close.rolling(p).mean()
    q["rsi14"] = q["rsi"] if "rsi" in q.columns else _q_rsi(close, 14)
    q["atr14"] = q["atr"] if "atr" in q.columns else _q_atr(q, 14)
    q["atr_pct"] = q["atr14"] / close.replace(0, np.nan) * 100
    macd = close.ewm(span=12, adjust=False).mean() - close.ewm(span=26, adjust=False).mean()
    q["macd"] = macd
    q["macd_signal"] = macd.ewm(span=9, adjust=False).mean()
    q["macd_hist"] = q["macd"] - q["macd_signal"]
    mid = close.rolling(20).mean()
    std = close.rolling(20).std(ddof=0)
    q["bb_mid"] = mid
    q["bb_upper"] = mid + 2 * std
    q["bb_lower"] = mid - 2 * std
    q["bb_width_pct"] = (q["bb_upper"] - q["bb_lower"]) / mid.replace(0, np.nan) * 100
    q["bb_pos"] = (close - q["bb_lower"]) / (q["bb_upper"] - q["bb_lower"]).replace(0, np.nan)
    q["zscore20"] = (close - mid) / std.replace(0, np.nan)
    q["donchian_high20"] = pd.to_numeric(q.get("high", close), errors="coerce").rolling(20).max()
    q["donchian_low20"] = pd.to_numeric(q.get("low", close), errors="coerce").rolling(20).min()
    q["roc10"] = close.pct_change(10) * 100
    q["roc20"] = close.pct_change(20) * 100
    q["volatility20"] = q["log_ret"].rolling(20).std(ddof=0)
    q["volume_sma20"] = pd.to_numeric(q.get("volume", pd.Series(index=q.index, dtype=float)), errors="coerce").rolling(20).mean()
    q["volume_std20"] = pd.to_numeric(q.get("volume", pd.Series(index=q.index, dtype=float)), errors="coerce").rolling(20).std(ddof=0)
    q["volume_z"] = (pd.to_numeric(q.get("volume", 0), errors="coerce") - q["volume_sma20"]) / q["volume_std20"].replace(0, np.nan)
    if all(c in q.columns for c in ["high", "low", "volume"]):
        q["mfi14"] = _q_mfi(q, 14)
        q["cmf20"] = _q_cmf(q, 20)
        q["obv"] = _q_obv(q)
        adx, plus_di, minus_di = _q_adx(q, 14)
        q["adx14"] = adx
        q["plus_di"] = plus_di
        q["minus_di"] = minus_di
    else:
        q["mfi14"] = np.nan
        q["cmf20"] = np.nan
        q["obv"] = np.nan
        q["adx14"] = np.nan
        q["plus_di"] = np.nan
        q["minus_di"] = np.nan
    return q


def timeframe_quant_snapshot(df, label):
    q = prepare_quant_frame(df)
    if q.empty:
        return {"tf": label, "score": 0, "bias": "SIN DATOS"}
    last = q.iloc[-1]
    close = _q_float(last.get("close"))
    ema20 = _q_float(last.get("ema20"))
    ema50 = _q_float(last.get("ema50"))
    ema200 = _q_float(last.get("ema200"))
    rsi = _q_float(last.get("rsi14"), 50)
    adx = _q_float(last.get("adx14"), 0)
    macd_hist = _q_float(last.get("macd_hist"), 0)
    roc20 = _q_float(last.get("roc20"), 0)
    cmf = _q_float(last.get("cmf20"), 0)
    mfi = _q_float(last.get("mfi14"), 50)
    bb_pos = _q_float(last.get("bb_pos"), 0.5)
    atr_pct = _q_float(last.get("atr_pct"), 0)
    volume_z = _q_float(last.get("volume_z"), 0)
    score = 0.0
    weights = 0.0
    def add(cond_bull, cond_bear, weight):
        nonlocal score, weights
        weights += weight
        if cond_bull:
            score += weight
        elif cond_bear:
            score -= weight
    add(close > ema20, close < ema20, 12)
    add(ema20 > ema50, ema20 < ema50, 14)
    if not pd.isna(ema200):
        add(ema50 > ema200, ema50 < ema200, 18)
        add(close > ema200, close < ema200, 16)
    add(rsi >= 55, rsi <= 45, 10)
    add(macd_hist > 0, macd_hist < 0, 10)
    add(roc20 > 0, roc20 < 0, 8)
    add(cmf > 0.05, cmf < -0.05, 6)
    add(mfi >= 55, mfi <= 45, 4)
    if adx >= 20:
        add(_q_float(last.get("plus_di"), 0) > _q_float(last.get("minus_di"), 0), _q_float(last.get("minus_di"), 0) > _q_float(last.get("plus_di"), 0), 8)
    score = 100 * score / weights if weights else 0
    if score >= 45:
        bias = "ALCISTA FUERTE"
    elif score >= 15:
        bias = "ALCISTA"
    elif score <= -45:
        bias = "BAJISTA FUERTE"
    elif score <= -15:
        bias = "BAJISTA"
    else:
        bias = "NEUTRAL"
    return {
        "tf": label,
        "price": close,
        "score": round(score, 1),
        "bias": bias,
        "rsi": rsi,
        "adx": adx,
        "macd_hist": macd_hist,
        "roc20": roc20,
        "atr_pct": atr_pct,
        "bb_pos": bb_pos,
        "volume_z": volume_z,
        "cmf": cmf,
        "mfi": mfi,
        "ema20": ema20,
        "ema50": ema50,
        "ema200": ema200,
        "zscore20": _q_float(last.get("zscore20"), 0),
        "bb_width_pct": _q_float(last.get("bb_width_pct"), 0),
    }


def daily_risk_metrics(df_1d):
    q = prepare_quant_frame(df_1d)
    if q.empty or len(q) < 10:
        return {}
    close = q["close"].dropna()
    ret = close.pct_change().dropna()
    if ret.empty:
        return {}
    equity = (1 + ret).cumprod()
    peak = equity.cummax()
    drawdown = equity / peak - 1
    downside = ret[ret < 0]
    ann_vol = ret.std(ddof=0) * np.sqrt(365) * 100
    ann_return = ret.mean() * 365 * 100
    sharpe = _q_safe_div(ret.mean(), ret.std(ddof=0), 0) * np.sqrt(365)
    downside_std = downside.std(ddof=0) if len(downside) else np.nan
    sortino = _q_safe_div(ret.mean(), downside_std, 0) * np.sqrt(365)
    max_dd = drawdown.min() * 100
    calmar = _q_safe_div(ann_return, abs(max_dd), 0)
    var95 = np.percentile(ret, 5) * 100
    var99 = np.percentile(ret, 1) * 100
    cvar95 = ret[ret <= np.percentile(ret, 5)].mean() * 100
    cvar99 = ret[ret <= np.percentile(ret, 1)].mean() * 100
    current_dd = (close.iloc[-1] / close.cummax().iloc[-1] - 1) * 100
    ath = close.cummax().iloc[-1]
    vol30 = ret.tail(30).std(ddof=0) * np.sqrt(365) * 100 if len(ret) >= 10 else np.nan
    vol90 = ret.tail(90).std(ddof=0) * np.sqrt(365) * 100 if len(ret) >= 30 else np.nan
    vol_series = ret.rolling(30).std(ddof=0) * np.sqrt(365) * 100
    vol_pctile = (vol_series.rank(pct=True).iloc[-1] * 100) if vol_series.notna().sum() else np.nan
    ulcer = np.sqrt(np.nanmean(np.square(drawdown * 100)))
    return {
        "ann_vol": ann_vol,
        "ann_return": ann_return,
        "sharpe": sharpe,
        "sortino": sortino,
        "max_dd": max_dd,
        "current_dd": current_dd,
        "ath": ath,
        "var95": var95,
        "var99": var99,
        "cvar95": cvar95,
        "cvar99": cvar99,
        "vol30": vol30,
        "vol90": vol90,
        "vol_percentile": vol_pctile,
        "ulcer": ulcer,
        "best_day": ret.max() * 100,
        "worst_day": ret.min() * 100,
        "positive_days": (ret > 0).mean() * 100,
        "sample_days": len(ret),
    }



def historical_regime_analogs(df_1d):
    """Busca episodios históricos con régimen parecido y mide retornos posteriores."""
    q = prepare_quant_frame(df_1d)
    if q.empty or len(q) < 260:
        return {}, pd.DataFrame()
    q = q.copy()
    q["vol30_ann"] = q["ret"].rolling(30).std(ddof=0) * np.sqrt(365) * 100
    q["vol30_med"] = q["vol30_ann"].rolling(180, min_periods=60).median()
    q["bull200"] = q["close"] > q["ema200"]
    q["mom20"] = q["roc20"] > 0
    q["highvol"] = q["vol30_ann"] > q["vol30_med"]
    q["rsi_bucket"] = pd.cut(q["rsi14"], bins=[-np.inf, 35, 45, 55, 65, np.inf], labels=[0, 1, 2, 3, 4])
    cur = q.iloc[-1]
    mask = (
        (q["bull200"] == bool(cur["bull200"])) &
        (q["mom20"] == bool(cur["mom20"])) &
        (q["highvol"] == bool(cur["highvol"])) &
        (q["rsi_bucket"] == cur["rsi_bucket"])
    )
    x = q.loc[mask, ["time", "close", "rsi14", "vol30_ann", "bull200", "mom20"]].copy()
    for days in [7, 30, 90]:
        q[f"fwd_{days}"] = q["close"].shift(-days) / q["close"] - 1
        x[f"fwd_{days}"] = q.loc[x.index, f"fwd_{days}"]
    x = x.iloc[:-1] if len(x) and x.index[-1] == q.index[-1] else x
    valid30 = x["fwd_30"].dropna()
    if valid30.empty:
        return {}, x
    stats = {
        "samples": int(len(valid30)),
        "p_up_7": float((x["fwd_7"].dropna() > 0).mean() * 100) if x["fwd_7"].notna().any() else np.nan,
        "p_up_30": float((valid30 > 0).mean() * 100),
        "p_up_90": float((x["fwd_90"].dropna() > 0).mean() * 100) if x["fwd_90"].notna().any() else np.nan,
        "median_7": float(x["fwd_7"].dropna().median() * 100) if x["fwd_7"].notna().any() else np.nan,
        "median_30": float(valid30.median() * 100),
        "median_90": float(x["fwd_90"].dropna().median() * 100) if x["fwd_90"].notna().any() else np.nan,
        "p10_30": float(valid30.quantile(0.10) * 100),
        "p90_30": float(valid30.quantile(0.90) * 100),
    }
    return stats, x.sort_values("time", ascending=False)


def kelly_fraction(winrate_pct, payoff_ratio):
    p = np.clip(_q_float(winrate_pct, 0) / 100, 0, 1)
    b = max(_q_float(payoff_ratio, 0), 1e-9)
    q = 1 - p
    full = max(p - q / b, 0)
    return {"full": full, "half": full / 2, "quarter": full / 4}


def drawdown_recovery_table():
    rows = []
    for dd in [5, 10, 15, 20, 25, 30, 40, 50, 60, 70, 80, 90]:
        recovery = (1 / (1 - dd / 100) - 1) * 100
        rows.append({"Drawdown": f"-{dd}%", "Ganancia necesaria para recuperar": f"+{recovery:.1f}%", "Capital restante": f"{100-dd}%"})
    return pd.DataFrame(rows)

def detect_quant_regime(day_snap, risk):
    score = _q_float(day_snap.get("score"), 0)
    adx = _q_float(day_snap.get("adx"), 0)
    vol_pctile = _q_float(risk.get("vol_percentile"), 50)
    bb_width = _q_float(day_snap.get("bb_width_pct"), 0)
    if score >= 35 and adx >= 20:
        trend = "BULL TREND"
    elif score <= -35 and adx >= 20:
        trend = "BEAR TREND"
    elif abs(score) < 20 and adx < 20:
        trend = "RANGE"
    else:
        trend = "TRANSICIÓN"
    if vol_pctile >= 80:
        vol = "VOLATILIDAD EXTREMA"
    elif vol_pctile >= 60:
        vol = "VOLATILIDAD ALTA"
    elif vol_pctile <= 25:
        vol = "VOLATILIDAD COMPRIMIDA"
    else:
        vol = "VOLATILIDAD NORMAL"
    if bb_width and bb_width < 3:
        expansion = "SQUEEZE / COMPRESIÓN"
    else:
        expansion = "EXPANSIÓN NORMAL"
    return trend, vol, expansion


def blank_external_btc_metrics():
    return {
        "fear_greed": np.nan, "fear_greed_label": "No conectado",
        "funding_rate": np.nan, "mark_price": np.nan, "index_price": np.nan,
        "open_interest_btc": np.nan, "open_interest_change_pct": np.nan,
        "global_long_short": np.nan, "taker_buy_sell": np.nan,
        "orderbook_imbalance": np.nan, "market_cap_usd": np.nan,
        "volume_24h_usd": np.nan, "change_24h_pct": np.nan,
        "change_7d_pct": np.nan, "sources_ok": [], "errors": [],
    }


@st.cache_data(ttl=60, show_spinner=False)
def fetch_btc_external_metrics():
    """Datos públicos opcionales en paralelo. Si fallan, el motor local sigue intacto."""
    out = {
        "fear_greed": np.nan, "fear_greed_label": "No disponible",
        "funding_rate": np.nan, "mark_price": np.nan, "index_price": np.nan,
        "open_interest_btc": np.nan, "open_interest_change_pct": np.nan,
        "global_long_short": np.nan, "taker_buy_sell": np.nan,
        "orderbook_imbalance": np.nan, "market_cap_usd": np.nan,
        "volume_24h_usd": np.nan, "change_24h_pct": np.nan,
        "change_7d_pct": np.nan, "sources_ok": [], "errors": [],
    }
    if requests is None:
        out["errors"].append("requests no disponible")
        return out

    headers = {"User-Agent": "BTC-Quant-Terminal/1.0"}
    endpoints = {
        "fg": ("https://api.alternative.me/fng/", {"limit": 1}),
        "ticker": ("https://api.alternative.me/v2/ticker/bitcoin/", {"convert": "USD"}),
        "premium": ("https://fapi.binance.com/fapi/v1/premiumIndex", {"symbol": "BTCUSDT"}),
        "oi": ("https://fapi.binance.com/fapi/v1/openInterest", {"symbol": "BTCUSDT"}),
        "oih": ("https://fapi.binance.com/futures/data/openInterestHist", {"symbol": "BTCUSDT", "period": "5m", "limit": 30}),
        "ls": ("https://fapi.binance.com/futures/data/globalLongShortAccountRatio", {"symbol": "BTCUSDT", "period": "5m", "limit": 1}),
        "tk": ("https://fapi.binance.com/futures/data/takerlongshortRatio", {"symbol": "BTCUSDT", "period": "5m", "limit": 1}),
        "book": ("https://data-api.binance.vision/api/v3/depth", {"symbol": "BTCUSDT", "limit": 100}),
    }

    def fetch_one(name, spec):
        url, params = spec
        try:
            r = requests.get(url, params=params, headers=headers, timeout=2.5)
            r.raise_for_status()
            return name, r.json(), None
        except Exception as e:
            return name, None, type(e).__name__

    results = {}
    try:
        from concurrent.futures import ThreadPoolExecutor, as_completed
        with ThreadPoolExecutor(max_workers=len(endpoints)) as pool:
            futs = [pool.submit(fetch_one, name, spec) for name, spec in endpoints.items()]
            for fut in as_completed(futs):
                name, data, err = fut.result()
                results[name] = data
                if err:
                    out["errors"].append(f"{name}: {err}")
    except Exception as e:
        out["errors"].append(f"parallel-fetch: {type(e).__name__}")
        return out

    fg = results.get("fg")
    if isinstance(fg, dict):
        row = (fg.get("data") or [{}])[0]
        out["fear_greed"] = _q_float(row.get("value"))
        out["fear_greed_label"] = str(row.get("value_classification", "No disponible"))
        out["sources_ok"].append("Alternative.me F&G")

    ticker = results.get("ticker")
    if isinstance(ticker, dict):
        data = ticker.get("data", {})
        row = next(iter(data.values())) if isinstance(data, dict) and data else {}
        quote = row.get("quotes", {}).get("USD", {}) if isinstance(row, dict) else {}
        out["market_cap_usd"] = _q_float(quote.get("market_cap"))
        out["volume_24h_usd"] = _q_float(quote.get("volume_24h"))
        out["change_24h_pct"] = _q_float(quote.get("percentage_change_24h"))
        out["change_7d_pct"] = _q_float(quote.get("percentage_change_7d"))
        out["sources_ok"].append("Alternative.me BTC ticker")

    premium = results.get("premium")
    if isinstance(premium, dict):
        out["funding_rate"] = _q_float(premium.get("lastFundingRate")) * 100
        out["mark_price"] = _q_float(premium.get("markPrice"))
        out["index_price"] = _q_float(premium.get("indexPrice"))
        out["sources_ok"].append("Binance Futures premium index")

    oi = results.get("oi")
    if isinstance(oi, dict):
        out["open_interest_btc"] = _q_float(oi.get("openInterest"))
        out["sources_ok"].append("Binance Futures OI")

    hist = results.get("oih")
    if isinstance(hist, list) and len(hist) >= 2:
        first = _q_float(hist[0].get("sumOpenInterest"))
        last = _q_float(hist[-1].get("sumOpenInterest"))
        out["open_interest_change_pct"] = (_q_safe_div(last, first, 1) - 1) * 100 if first else np.nan
        out["sources_ok"].append("Binance Futures OI history")

    ls = results.get("ls")
    if isinstance(ls, list) and ls:
        out["global_long_short"] = _q_float(ls[-1].get("longShortRatio"))
        out["sources_ok"].append("Binance Long/Short")

    tk = results.get("tk")
    if isinstance(tk, list) and tk:
        out["taker_buy_sell"] = _q_float(tk[-1].get("buySellRatio"))
        out["sources_ok"].append("Binance Taker ratio")

    book = results.get("book")
    if isinstance(book, dict):
        bids = sum(_q_float(x[1], 0) for x in book.get("bids", []))
        asks = sum(_q_float(x[1], 0) for x in book.get("asks", []))
        out["orderbook_imbalance"] = _q_safe_div(bids - asks, bids + asks, 0) * 100 if (bids + asks) else np.nan
        out["sources_ok"].append("Binance Spot order book")
    return out

def build_quant_rulebook(snaps, risk, ext, trade_context):
    """Rule engine auditable. Cada regla devuelve evidencia, no una promesa de rentabilidad."""
    d = snaps.get("1D", {})
    h4 = snaps.get("4H", {})
    h1 = snaps.get("1H", {})
    m15 = snaps.get("15M", {})
    m5 = snaps.get("5M", {})
    rows = []
    def rule(category, name, value, bull=None, bear=None, weight=1, info=""):
        sign = 0
        state = "ℹ️"
        if bull is True:
            sign, state = 1, "✅"
        elif bear is True:
            sign, state = -1, "❌"
        elif bull is False or bear is False:
            sign, state = 0, "⚠️"
        rows.append({
            "Categoría": category,
            "Regla": name,
            "Estado": state,
            "Peso": weight,
            "Impacto": sign * weight,
            "Valor": value,
            "Lectura": info,
        })
    # Tendencia y estructura
    for label, s in [("1D", d), ("4H", h4), ("1H", h1), ("15M", m15), ("5M", m5)]:
        p, e20, e50, e200 = (_q_float(s.get(k)) for k in ["price", "ema20", "ema50", "ema200"])
        rule("Tendencia", f"{label}: precio > EMA20", f"{p:,.0f} / {e20:,.0f}", p > e20, p < e20, 2 if label in ["1D", "4H"] else 1)
        rule("Tendencia", f"{label}: EMA20 > EMA50", f"{e20:,.0f} / {e50:,.0f}", e20 > e50, e20 < e50, 2 if label in ["1D", "4H"] else 1)
        if not pd.isna(e200):
            rule("Tendencia", f"{label}: precio > EMA200", f"{p:,.0f} / {e200:,.0f}", p > e200, p < e200, 3 if label == "1D" else 1)
            rule("Tendencia", f"{label}: EMA50 > EMA200", f"{e50:,.0f} / {e200:,.0f}", e50 > e200, e50 < e200, 3 if label == "1D" else 1)
    # Momentum
    for label, s in [("1D", d), ("4H", h4), ("1H", h1), ("15M", m15)]:
        rsi = _q_float(s.get("rsi"), 50)
        rule("Momentum", f"{label}: RSI momentum", f"{rsi:.1f}", rsi >= 55 and rsi < 75, rsi <= 45 and rsi > 25, 2)
        mh = _q_float(s.get("macd_hist"), 0)
        rule("Momentum", f"{label}: MACD hist", f"{mh:,.2f}", mh > 0, mh < 0, 2)
        roc = _q_float(s.get("roc20"), 0)
        rule("Momentum", f"{label}: ROC20", f"{roc:+.2f}%", roc > 0, roc < 0, 1)
    # Fuerza de tendencia y volumen
    for label, s in [("1D", d), ("4H", h4), ("1H", h1), ("15M", m15)]:
        adx = _q_float(s.get("adx"), 0)
        rule("Fuerza", f"{label}: ADX >= 20", f"{adx:.1f}", adx >= 20, None, 1, "Confirma que el movimiento tiene fuerza; no define dirección por sí solo.")
        cmf = _q_float(s.get("cmf"), 0)
        rule("Flujo", f"{label}: CMF", f"{cmf:+.3f}", cmf > 0.05, cmf < -0.05, 1)
        vz = _q_float(s.get("volume_z"), 0)
        rule("Volumen", f"{label}: volumen anómalo", f"z={vz:+.2f}", vz >= 1.5, None, 1, "Volumen alto aumenta relevancia del movimiento, no implica dirección.")
    # Volatilidad y riesgo
    vp = _q_float(risk.get("vol_percentile"), 50)
    rule("Riesgo", "Volatilidad 30D no extrema", f"percentil {vp:.0f}", vp < 80, vp >= 90, 2)
    cdd = _q_float(risk.get("current_dd"), 0)
    rule("Riesgo", "Drawdown desde ATH", f"{cdd:.1f}%", cdd > -15, cdd <= -30, 2)
    var95 = _q_float(risk.get("var95"), 0)
    rule("Riesgo", "VaR diario 95%", f"{var95:.2f}%", var95 > -5, var95 <= -8, 1)
    # Sentimiento / derivados
    fg = _q_float(ext.get("fear_greed"))
    if not pd.isna(fg):
        rule("Sentimiento", "Fear & Greed no eufórico", f"{fg:.0f} · {ext.get('fear_greed_label')}", fg < 80, fg >= 90, 2)
        rule("Sentimiento", "Fear & Greed zona de oportunidad", f"{fg:.0f}", fg <= 35, fg >= 75, 1, "Lectura contraria; no es señal independiente.")
    funding = _q_float(ext.get("funding_rate"))
    if not pd.isna(funding):
        rule("Derivados", "Funding no sobrecalentado", f"{funding:+.4f}%", abs(funding) < 0.03, abs(funding) >= 0.08, 2)
        rule("Derivados", "Funding direccional", f"{funding:+.4f}%", funding > 0 and funding < 0.03, funding < 0 and funding > -0.03, 1)
    oi_chg = _q_float(ext.get("open_interest_change_pct"))
    if not pd.isna(oi_chg):
        rule("Derivados", "Cambio OI 150m", f"{oi_chg:+.2f}%", 0 < oi_chg < 5, abs(oi_chg) >= 8, 1, "Aumento extremo puede elevar riesgo de squeeze/liquidaciones.")
    ls = _q_float(ext.get("global_long_short"))
    if not pd.isna(ls):
        rule("Derivados", "Long/Short no crowded", f"{ls:.2f}", 0.75 <= ls <= 1.35, ls >= 1.8 or ls <= 0.55, 2)
    tk = _q_float(ext.get("taker_buy_sell"))
    if not pd.isna(tk):
        rule("Derivados", "Taker flow", f"{tk:.2f}", tk > 1.03, tk < 0.97, 1)
    ob = _q_float(ext.get("orderbook_imbalance"))
    if not pd.isna(ob):
        rule("Microestructura", "Order book imbalance", f"{ob:+.1f}%", ob >= 5, ob <= -5, 1)
    # Contexto del setup actual
    direction = trade_context.get("candidate_direction")
    long_score = _q_float(trade_context.get("long_score"), 0)
    short_score = _q_float(trade_context.get("short_score"), 0)
    rr = _q_float(trade_context.get("rr_real"), 0)
    quality = _q_float(trade_context.get("quality_score"), 0)
    rule("Setup", "Score direccional dominante", f"L {long_score:.0f} / S {short_score:.0f}", long_score >= short_score + 2, short_score >= long_score + 2, 3)
    rule("Setup", "RR >= 1.8", f"{rr:.2f}R", rr >= 1.8, rr < 1.2, 3)
    rule("Setup", "Calidad >= 7/10", f"{quality:.1f}/10", quality >= 7, quality < 5, 3)
    rule("Setup", "Trade validado por motor principal", str(trade_context.get("trade_valid")), bool(trade_context.get("trade_valid")), not bool(trade_context.get("trade_valid")), 4)
    # Alineación multi-TF
    scores = [_q_float(snaps[x].get("score"), 0) for x in ["1D", "4H", "1H"] if x in snaps]
    if scores:
        rule("Alineación", "1D + 4H + 1H alineados alcistas", ", ".join(f"{x:+.0f}" for x in scores), all(x >= 15 for x in scores), all(x <= -15 for x in scores), 4)
    return pd.DataFrame(rows)


def quant_rulebook_score(rule_df):
    if rule_df is None or rule_df.empty:
        return 0.0
    weights = pd.to_numeric(rule_df["Peso"], errors="coerce").abs().sum()
    impact = pd.to_numeric(rule_df["Impacto"], errors="coerce").sum()
    return float(np.clip(100 * impact / weights, -100, 100)) if weights else 0.0


def build_investment_matrix(snaps, risk, ext, trade_context):
    d, h4, h1, m15 = snaps["1D"], snaps["4H"], snaps["1H"], snaps["15M"]
    fg = _q_float(ext.get("fear_greed"), 50)
    volp = _q_float(risk.get("vol_percentile"), 50)
    dd = _q_float(risk.get("current_dd"), 0)
    rows = []
    def add(name, horizon, score, regime, requirements, risk_label):
        score = int(np.clip(round(score), 0, 100))
        state = "🟢 FAVORABLE" if score >= 70 else "🟡 SELECTIVO" if score >= 50 else "🔴 DESFAVORABLE"
        rows.append({"Estrategia": name, "Horizonte": horizon, "Score": score, "Estado": state, "Regla principal": regime, "Qué exige": requirements, "Riesgo": risk_label})
    longterm = (_q_float(d.get("score"), 0) + 100) / 2
    add("HODL / Spot", "1–5 años", 55 + 0.35 * (longterm - 50) + (5 if dd <= -20 else 0) - (8 if fg >= 85 else 0), "Prioriza tendencia secular y supervivencia", "Sin apalancamiento, horizonte largo, tolerancia a drawdowns", "Alto por volatilidad BTC; sin riesgo de liquidación")
    add("DCA", "6–60 meses", 70 + (10 if fg <= 35 else 0) + (7 if dd <= -20 else 0) - (8 if fg >= 85 else 0), "Reduce riesgo de timing", "Aporte periódico fijo y plan disciplinado", "Medio/alto, dispersado en el tiempo")
    add("DCA adaptativo", "6–60 meses", 68 + (12 if dd <= -20 else 0) + (8 if fg <= 30 else 0) - (5 if volp >= 90 else 0), "Aumenta aportes en debilidad y reduce en euforia", "Reglas objetivas; no perseguir precio", "Medio/alto")
    trend_score = np.mean([_q_float(d.get("score"), 0), _q_float(h4.get("score"), 0), _q_float(h1.get("score"), 0)])
    add("Trend Following Spot", "Semanas–meses", 50 + trend_score * 0.35 + (_q_float(d.get("adx"), 0) - 20) * 0.5, "Busca tendencias persistentes", "EMA/ADX y stop dinámico; acepta falsas rupturas", "Medio/alto")
    swing_score = 50 + _q_float(h4.get("score"), 0) * 0.25 + _q_float(h1.get("score"), 0) * 0.25
    add("Swing Spot", "Días–semanas", swing_score, "Confluencia 4H + 1H", "Entradas por estructura, invalidación técnica y RR", "Alto")
    mr = 60 - abs(_q_float(h1.get("zscore20"), 0)) * 5 if _q_float(h1.get("adx"), 0) < 20 else 40
    if _q_float(h1.get("rsi"), 50) <= 30 or _q_float(h1.get("rsi"), 50) >= 70:
        mr += 12
    add("Mean Reversion Spot", "Horas–días", mr, "Mejor en rangos, peor en tendencia fuerte", "RSI/Z-score extremos + soporte/resistencia", "Alto; riesgo de atrapar tendencia")
    futures = 35 + _q_float(trade_context.get("quality_score"), 0) * 5 + max(_q_float(trade_context.get("rr_real"), 0) - 1.0, 0) * 6
    if bool(trade_context.get("trade_valid")):
        futures += 12
    if volp >= 90:
        futures -= 12
    add("Futuros tácticos", "Minutos–días", futures, "Solo cuando el edge y el RR justifican el apalancamiento", "SL obligatorio, tamaño por riesgo, funding/OI/crowding", "Muy alto + riesgo de liquidación")
    add("Grid / Range", "Horas–días", 70 if abs(_q_float(h1.get("score"), 0)) < 20 and _q_float(h1.get("adx"), 0) < 20 else 35, "Funciona mejor en rango estable", "Límites superior/inferior definidos, sin breakout activo", "Alto si rompe el rango")
    return pd.DataFrame(rows).sort_values("Score", ascending=False).reset_index(drop=True)


def simulate_dca_history(df_1d, periodic_usd=200.0, initial_usd=0.0, frequency="Mensual", adaptive=False):
    q = prepare_quant_frame(df_1d)
    if q.empty or "time" not in q.columns:
        return pd.DataFrame(), {}
    q = q.dropna(subset=["time", "close"]).copy()
    if len(q) < 2:
        return pd.DataFrame(), {}
    freq = {"Semanal": "W-MON", "Quincenal": "2W-MON", "Mensual": "MS"}.get(frequency, "MS")
    indexed = q.set_index("time")
    buys = indexed.resample(freq).first().dropna(subset=["close"]).copy()
    if buys.empty:
        return pd.DataFrame(), {}
    qty = 0.0
    invested = 0.0
    records = []
    first_price = float(buys["close"].iloc[0])
    if initial_usd > 0:
        qty += initial_usd / first_price
        invested += initial_usd
    for ts, row in buys.iterrows():
        contribution = float(periodic_usd)
        if adaptive:
            ema200 = _q_float(row.get("ema200"))
            px = _q_float(row.get("close"))
            rsi = _q_float(row.get("rsi14"), 50)
            mult = 1.0
            if not pd.isna(ema200):
                if px < ema200:
                    mult += 0.50
                elif px > ema200 * 1.25:
                    mult -= 0.35
            if rsi <= 35:
                mult += 0.25
            elif rsi >= 70:
                mult -= 0.20
            contribution *= float(np.clip(mult, 0.35, 1.75))
        px = float(row["close"])
        qty += contribution / px
        invested += contribution
        value = qty * px
        records.append({"Fecha": ts, "Precio": px, "Aporte": contribution, "Invertido": invested, "BTC": qty, "Valor": value, "PNL": value - invested})
    out = pd.DataFrame(records)
    if out.empty:
        return out, {}
    final_price = float(q["close"].iloc[-1])
    final_value = qty * final_price
    total_budget = invested
    lump_qty = total_budget / first_price if first_price else 0
    lump_value = lump_qty * final_price
    avg_price = invested / qty if qty else np.nan
    stats = {
        "invested": invested,
        "btc": qty,
        "avg_price": avg_price,
        "final_value": final_value,
        "pnl": final_value - invested,
        "return_pct": (_q_safe_div(final_value, invested, 1) - 1) * 100 if invested else 0,
        "lump_value": lump_value,
        "lump_return_pct": (_q_safe_div(lump_value, total_budget, 1) - 1) * 100 if total_budget else 0,
        "first_price": first_price,
        "final_price": final_price,
        "purchases": len(out),
    }
    return out, stats


def leverage_survival_table(price, account_usd, risk_pct):
    rows = []
    for lev in [1, 2, 3, 5, 7, 10, 15, 20, 25, 50, 100]:
        approx_liq = 100 / lev if lev > 1 else np.nan
        risk_budget = account_usd * risk_pct
        rows.append({
            "Leverage": f"{lev}x",
            "Movimiento teórico a liquidación*": "No aplica" if lev == 1 else f"~{approx_liq:.1f}%",
            "Nocional máximo por margen": account_usd * lev,
            "Riesgo objetivo por trade": risk_budget,
            "Comentario": "Spot / sin liquidación" if lev == 1 else ("Extremo" if lev >= 20 else "Muy alto" if lev >= 10 else "Alto" if lev >= 5 else "Moderado"),
        })
    return pd.DataFrame(rows)


def portfolio_scenario_table(price, btc_usd, cash_usd):
    rows = []
    btc_qty = btc_usd / price if price else 0
    base = btc_usd + cash_usd
    for move in [-80, -70, -50, -30, -20, -10, 0, 10, 25, 50, 100, 200, 500]:
        px = price * (1 + move / 100)
        value = btc_qty * px + cash_usd
        rows.append({"Movimiento BTC": f"{move:+d}%", "Precio escenario": px, "Valor cartera": value, "PNL": value - base, "Retorno cartera %": (_q_safe_div(value, base, 1) - 1) * 100 if base else 0})
    return pd.DataFrame(rows)


def render_quant_header(score, regime, vol_regime, source_count):
    if score >= 35:
        label, icon = "SESGO ALCISTA", "🟢"
    elif score <= -35:
        label, icon = "SESGO BAJISTA", "🔴"
    else:
        label, icon = "SESGO MIXTO / SELECTIVO", "🟡"
    st.markdown(f"""
    <div style="border:1px solid #dbeafe;border-radius:18px;padding:18px 20px;background:linear-gradient(135deg,#eff6ff 0%,#ffffff 70%);margin:4px 0 14px 0;">
      <div style="font-size:12px;font-weight:800;letter-spacing:.12em;color:#1d4ed8;">BTC QUANT TERMINAL</div>
      <div style="font-size:24px;font-weight:900;margin-top:4px;">{icon} {label} · {score:+.0f}/100</div>
      <div style="font-size:13px;color:#475569;margin-top:6px;">Régimen: <b>{regime}</b> · Riesgo: <b>{vol_regime}</b> · Fuentes externas activas: <b>{source_count}</b></div>
    </div>
    """, unsafe_allow_html=True)



# =========================================================
# ACCESO ABIERTO + GESTIÓN DE USUARIOS (SIN CONTRASEÑAS)
# =========================================================
# Esta UI no exige autenticación. Los usuarios funcionan como perfiles
# operativos/organizativos para asignar roles y permisos, NO como una barrera
# de seguridad. Si el router principal del proyecto tiene un login propio,
# debe quedar desactivado allí también.
BTC_AUTH_REQUIRED = False
BTC_PASSWORD_REQUIRED = False
BTC_ACCESS_MODE = "OPEN"

_BTC_USER_ROLES = ["Administrador", "Trader", "Analista", "Inversor", "Observador"]
_BTC_USER_MODULES = [
    "Decisión", "Gráfico", "Confluencias", "Trade", "Backtest",
    "Market Intel", "Inversión", "Riesgo", "Quant Rules", "Configuración",
]
_BTC_ROLE_DEFAULTS = {
    "Administrador": _BTC_USER_MODULES.copy(),
    "Trader": ["Decisión", "Gráfico", "Confluencias", "Trade", "Backtest", "Market Intel", "Riesgo", "Quant Rules"],
    "Analista": ["Decisión", "Gráfico", "Confluencias", "Backtest", "Market Intel", "Inversión", "Riesgo", "Quant Rules"],
    "Inversor": ["Decisión", "Gráfico", "Market Intel", "Inversión", "Riesgo", "Quant Rules"],
    "Observador": ["Decisión", "Gráfico", "Market Intel", "Inversión", "Riesgo"],
}


def _btc_users_file() -> Path:
    configured = os.getenv("BTC_USERS_FILE", "").strip()
    if configured:
        return Path(configured).expanduser()
    try:
        return Path(__file__).resolve().with_name("btc_users.json")
    except Exception:
        return Path("btc_users.json")


def _btc_now() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _btc_default_user_store() -> dict:
    owner_id = "owner"
    return {
        "version": 1,
        "access_mode": "open",
        "active_user_id": owner_id,
        "updated_at": _btc_now(),
        "users": [
            {
                "id": owner_id,
                "nombre": "Administrador",
                "usuario": "admin",
                "email": "",
                "rol": "Administrador",
                "activo": True,
                "permisos": _BTC_USER_MODULES.copy(),
                "notas": "Perfil principal creado automáticamente. No requiere contraseña.",
                "created_at": _btc_now(),
                "updated_at": _btc_now(),
            }
        ],
    }


def _btc_normalize_user_store(store) -> dict:
    if not isinstance(store, dict):
        store = _btc_default_user_store()
    users = store.get("users")
    if not isinstance(users, list):
        users = []
    normalized = []
    seen_ids = set()
    seen_usernames = set()
    for raw in users:
        if not isinstance(raw, dict):
            continue
        uid = str(raw.get("id") or uuid.uuid4().hex).strip()
        if not uid or uid in seen_ids:
            uid = uuid.uuid4().hex
        username = str(raw.get("usuario") or "").strip().lower()
        if not username:
            username = f"usuario_{len(normalized)+1}"
        base = username
        suffix = 2
        while username in seen_usernames:
            username = f"{base}_{suffix}"
            suffix += 1
        role = str(raw.get("rol") or "Observador").strip()
        if role not in _BTC_USER_ROLES:
            role = "Observador"
        permissions = raw.get("permisos")
        if not isinstance(permissions, list):
            permissions = _BTC_ROLE_DEFAULTS.get(role, []).copy()
        permissions = [p for p in _BTC_USER_MODULES if p in permissions]
        normalized.append({
            "id": uid,
            "nombre": str(raw.get("nombre") or username).strip(),
            "usuario": username,
            "email": str(raw.get("email") or "").strip(),
            "rol": role,
            "activo": bool(raw.get("activo", True)),
            "permisos": permissions,
            "notas": str(raw.get("notas") or "").strip(),
            "created_at": str(raw.get("created_at") or _btc_now()),
            "updated_at": str(raw.get("updated_at") or _btc_now()),
        })
        seen_ids.add(uid)
        seen_usernames.add(username)

    if not normalized:
        return _btc_default_user_store()

    active_id = str(store.get("active_user_id") or "")
    active_ids = {u["id"] for u in normalized if u["activo"]}
    if active_id not in active_ids:
        active_id = next(iter(active_ids), normalized[0]["id"])
    return {
        "version": 1,
        "access_mode": "open",
        "active_user_id": active_id,
        "updated_at": str(store.get("updated_at") or _btc_now()),
        "users": normalized,
    }


def _btc_load_user_store(force: bool = False) -> dict:
    cache_key = "btc_user_store_cache"
    if not force and cache_key in st.session_state:
        return _btc_normalize_user_store(st.session_state[cache_key])

    path = _btc_users_file()
    store = None
    try:
        if path.exists():
            store = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        store = None
    store = _btc_normalize_user_store(store or _btc_default_user_store())
    st.session_state[cache_key] = store
    return store


def _btc_save_user_store(store: dict) -> tuple[bool, str]:
    store = _btc_normalize_user_store(store)
    store["updated_at"] = _btc_now()
    st.session_state["btc_user_store_cache"] = store
    path = _btc_users_file()
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(path.suffix + ".tmp")
        tmp.write_text(json.dumps(store, ensure_ascii=False, indent=2), encoding="utf-8")
        tmp.replace(path)
        return True, str(path)
    except Exception as exc:
        # La sesión sigue funcionando aunque el entorno no permita persistir archivos.
        return False, f"{type(exc).__name__}: {exc}"


def _btc_active_user(store: dict | None = None) -> dict:
    store = _btc_normalize_user_store(store or _btc_load_user_store())
    active_id = str(store.get("active_user_id") or "")
    for user in store.get("users", []):
        if user.get("id") == active_id and user.get("activo", True):
            return user
    for user in store.get("users", []):
        if user.get("activo", True):
            return user
    return store.get("users", [{}])[0]


def _btc_open_access_bootstrap() -> None:
    """Marca la sesión como acceso abierto antes de construir cualquier UI local."""
    os.environ["BTC_APP_AUTH_DISABLED"] = "1"
    os.environ["BTC_AUTH_REQUIRED"] = "0"
    for key in (
        "authenticated", "is_authenticated", "logged_in", "login_ok",
        "auth_ok", "password_ok", "btc_authenticated", "btc_auth_ok",
    ):
        st.session_state[key] = True
    st.session_state["btc_access_mode"] = "open"
    st.session_state["btc_password_required"] = False


def require_login() -> bool:
    """Compatibilidad: esta versión nunca solicita usuario ni contraseña."""
    _btc_open_access_bootstrap()
    return True


def require_btc_login() -> bool:
    """Compatibilidad explícita para routers que importen una puerta BTC."""
    return require_login()


def _btc_user_table(store: dict) -> pd.DataFrame:
    rows = []
    active_id = str(store.get("active_user_id") or "")
    for u in store.get("users", []):
        rows.append({
            "Activo actual": "●" if u.get("id") == active_id else "",
            "Nombre": u.get("nombre", ""),
            "Usuario": u.get("usuario", ""),
            "Rol": u.get("rol", ""),
            "Estado": "Activo" if u.get("activo", True) else "Desactivado",
            "Permisos": len(u.get("permisos", [])),
            "Email": u.get("email", ""),
            "Actualizado": u.get("updated_at", ""),
        })
    return pd.DataFrame(rows)


def render_btc_user_management() -> None:
    store = _btc_load_user_store(force=True)
    users = store.get("users", [])
    active_user = _btc_active_user(store)

    st.markdown("### 👥 Centro de Usuarios")
    st.caption("Acceso abierto: no existen contraseñas. Los usuarios son perfiles operativos para roles, permisos y trazabilidad interna.")

    total = len(users)
    active_count = sum(1 for u in users if u.get("activo", True))
    admin_count = sum(1 for u in users if u.get("rol") == "Administrador" and u.get("activo", True))
    k1, k2, k3, k4 = st.columns(4)
    k1.metric("Usuarios", total)
    k2.metric("Activos", active_count)
    k3.metric("Administradores", admin_count)
    k4.metric("Modo de acceso", "ABIERTO")

    st.info(f"Usuario activo en esta sesión: **{active_user.get('nombre', 'Administrador')}** · {active_user.get('rol', 'Administrador')} · sin contraseña")

    overview_tab, create_tab, edit_tab, backup_tab = st.tabs([
        "📋 Directorio", "➕ Crear usuario", "🛠️ Editar y permisos", "💾 Backup / Restaurar"
    ])

    with overview_tab:
        df_users = _btc_user_table(store)
        st.dataframe(df_users, use_container_width=True, hide_index=True)
        st.caption("El perfil activo no autentica identidad: sirve para personalizar roles y organización interna sin pedir clave al iniciar.")

        active_options = [u for u in users if u.get("activo", True)]
        if active_options:
            labels = [f"{u['nombre']} · @{u['usuario']} · {u['rol']}" for u in active_options]
            id_by_label = {label: u["id"] for label, u in zip(labels, active_options)}
            current_label = next((label for label, u in zip(labels, active_options) if u["id"] == store.get("active_user_id")), labels[0])
            selected_label = st.selectbox(
                "Usuario activo de la sesión",
                labels,
                index=labels.index(current_label),
                key="btc_cfg_active_user_selector",
            )
            if st.button("Aplicar usuario activo", type="primary", key="btc_apply_active_user"):
                store["active_user_id"] = id_by_label[selected_label]
                ok, msg = _btc_save_user_store(store)
                st.success("Usuario activo actualizado.")
                if not ok:
                    st.warning("Se aplicó en esta sesión, pero el entorno no permitió persistir el archivo local.")
                st.rerun()

    with create_tab:
        st.markdown("#### Alta de perfil")
        with st.form("btc_create_user_form", clear_on_submit=True):
            c1, c2, c3 = st.columns(3)
            nombre = c1.text_input("Nombre y apellido")
            usuario = c2.text_input("Usuario / alias", placeholder="ej: trader_1")
            email = c3.text_input("Email (opcional)")
            c4, c5 = st.columns([1, 2])
            rol = c4.selectbox("Rol", _BTC_USER_ROLES, index=2)
            permisos = c5.multiselect(
                "Permisos iniciales",
                _BTC_USER_MODULES,
                default=_BTC_ROLE_DEFAULTS.get("Analista", []),
            )
            notas = st.text_area("Notas internas", placeholder="Responsabilidad, estrategia, horario, alcance, etc.")
            submitted = st.form_submit_button("Crear usuario", type="primary", use_container_width=True)

        if submitted:
            username = usuario.strip().lower().replace(" ", "_")
            if not nombre.strip() or not username:
                st.error("Completá Nombre y Usuario.")
            elif any(str(u.get("usuario", "")).lower() == username for u in users):
                st.error("Ese usuario ya existe.")
            else:
                store["users"].append({
                    "id": uuid.uuid4().hex,
                    "nombre": nombre.strip(),
                    "usuario": username,
                    "email": email.strip(),
                    "rol": rol,
                    "activo": True,
                    "permisos": [p for p in _BTC_USER_MODULES if p in permisos],
                    "notas": notas.strip(),
                    "created_at": _btc_now(),
                    "updated_at": _btc_now(),
                })
                ok, msg = _btc_save_user_store(store)
                st.success(f"Usuario @{username} creado sin contraseña.")
                if not ok:
                    st.warning("Se creó para esta sesión, pero no se pudo escribir el archivo local de usuarios.")
                st.rerun()

    with edit_tab:
        if not users:
            st.info("No hay usuarios para editar.")
        else:
            labels = [f"{u['nombre']} · @{u['usuario']}" for u in users]
            selected = st.selectbox("Seleccionar usuario", labels, key="btc_cfg_edit_user")
            idx = labels.index(selected)
            user = users[idx]

            e1, e2, e3 = st.columns(3)
            new_name = e1.text_input("Nombre", value=user.get("nombre", ""), key="btc_edit_name")
            new_username = e2.text_input("Usuario", value=user.get("usuario", ""), key="btc_edit_username")
            role_index = _BTC_USER_ROLES.index(user.get("rol")) if user.get("rol") in _BTC_USER_ROLES else 0
            new_role = e3.selectbox("Rol", _BTC_USER_ROLES, index=role_index, key="btc_edit_role")
            new_email = st.text_input("Email", value=user.get("email", ""), key="btc_edit_email")
            new_permissions = st.multiselect(
                "Módulos permitidos",
                _BTC_USER_MODULES,
                default=[p for p in user.get("permisos", []) if p in _BTC_USER_MODULES],
                key="btc_edit_permissions",
            )
            new_notes = st.text_area("Notas", value=user.get("notas", ""), key="btc_edit_notes")
            new_active = st.toggle("Usuario activo", value=bool(user.get("activo", True)), key="btc_edit_active")

            b1, b2, b3 = st.columns(3)
            if b1.button("💾 Guardar cambios", type="primary", use_container_width=True, key="btc_save_user_changes"):
                username_norm = new_username.strip().lower().replace(" ", "_")
                duplicate = any(
                    i != idx and str(other.get("usuario", "")).lower() == username_norm
                    for i, other in enumerate(users)
                )
                if not new_name.strip() or not username_norm:
                    st.error("Nombre y usuario no pueden quedar vacíos.")
                elif duplicate:
                    st.error("Ese nombre de usuario ya pertenece a otro perfil.")
                else:
                    user.update({
                        "nombre": new_name.strip(),
                        "usuario": username_norm,
                        "email": new_email.strip(),
                        "rol": new_role,
                        "activo": bool(new_active),
                        "permisos": [p for p in _BTC_USER_MODULES if p in new_permissions],
                        "notas": new_notes.strip(),
                        "updated_at": _btc_now(),
                    })
                    if not user["activo"] and store.get("active_user_id") == user.get("id"):
                        replacement = next((u for u in users if u.get("id") != user.get("id") and u.get("activo", True)), None)
                        if replacement:
                            store["active_user_id"] = replacement["id"]
                    ok, msg = _btc_save_user_store(store)
                    st.success("Cambios guardados.")
                    if not ok:
                        st.warning("Los cambios viven en esta sesión, pero no se pudieron persistir en disco.")
                    st.rerun()

            if b2.button("⚡ Aplicar permisos del rol", use_container_width=True, key="btc_apply_role_defaults"):
                user["permisos"] = _BTC_ROLE_DEFAULTS.get(new_role, []).copy()
                user["rol"] = new_role
                user["updated_at"] = _btc_now()
                _btc_save_user_store(store)
                st.success("Permisos del rol aplicados.")
                st.rerun()

            delete_disabled = len(users) <= 1 or user.get("id") == "owner"
            if b3.button("🗑️ Eliminar usuario", use_container_width=True, disabled=delete_disabled, key="btc_delete_user"):
                removed_id = user.get("id")
                store["users"] = [u for u in users if u.get("id") != removed_id]
                if store.get("active_user_id") == removed_id:
                    store["active_user_id"] = store["users"][0]["id"]
                _btc_save_user_store(store)
                st.success("Usuario eliminado.")
                st.rerun()

    with backup_tab:
        st.markdown("#### Portabilidad de usuarios")
        st.caption("Útil especialmente si desplegás en un entorno donde el disco local puede ser temporal.")
        payload = json.dumps(store, ensure_ascii=False, indent=2)
        st.download_button(
            "⬇️ Exportar usuarios JSON",
            data=payload,
            file_name="btc_users_backup.json",
            mime="application/json",
            use_container_width=True,
            key="btc_export_users",
        )
        upload = st.file_uploader("Restaurar backup JSON", type=["json"], key="btc_import_users")
        if upload is not None:
            try:
                imported = json.loads(upload.getvalue().decode("utf-8"))
                imported = _btc_normalize_user_store(imported)
                st.success(f"Backup válido: {len(imported.get('users', []))} usuarios detectados.")
                if st.button("Restaurar este backup", type="primary", key="btc_restore_users"):
                    _btc_save_user_store(imported)
                    st.success("Backup restaurado.")
                    st.rerun()
            except Exception as exc:
                st.error(f"JSON inválido: {exc}")

        st.divider()
        st.markdown("#### Reinicio controlado")
        st.warning("Restablecer borra los perfiles personalizados y deja únicamente el Administrador abierto, sin contraseña.")
        confirm_reset = st.checkbox("Confirmo restablecer los usuarios", key="btc_confirm_reset_users")
        if st.button("Restablecer usuarios", disabled=not confirm_reset, key="btc_reset_users"):
            _btc_save_user_store(_btc_default_user_store())
            st.success("Usuarios restablecidos.")
            st.rerun()


def render_btc_configuration() -> None:
    st.subheader("⚙️ Configuración")
    st.caption("Administración del terminal BTC, perfiles y estado del acceso.")

    users_tab, access_tab, system_tab = st.tabs(["👥 Usuarios", "🔓 Acceso", "🧩 Sistema"])
    with users_tab:
        render_btc_user_management()

    with access_tab:
        st.markdown("### 🔓 Acceso de la aplicación")
        st.success("**Acceso abierto activado.** Esta versión no solicita contraseña al iniciar.")
        st.write("- Contraseña requerida: **No**")
        st.write("- Login obligatorio: **No**")
        st.write("- Perfiles operativos: **Sí**")
        st.write("- Cambio de perfil: **Configuración → Usuarios**")
        st.caption("Importante: sin login, los roles/permisos organizan la app pero no constituyen seguridad real frente a terceros.")

    with system_tab:
        store = _btc_load_user_store()
        active = _btc_active_user(store)
        st.markdown("### 🧩 Estado del sistema")
        s1, s2, s3, s4 = st.columns(4)
        s1.metric("Modo", "OPEN")
        s2.metric("Password", "OFF")
        s3.metric("Usuarios", len(store.get("users", [])))
        s4.metric("Perfil activo", active.get("rol", "Administrador"))
        st.code(str(_btc_users_file()), language=None)
        st.caption("Ruta del archivo local de usuarios. Podés cambiarla con la variable de entorno BTC_USERS_FILE.")


def render_dashboard():
    _btc_open_access_bootstrap()
    config = render_sidebar()

    estrategia = config.get("estrategia")

    account_usd = config.get("account_usd", 500.0)

    risk_pct = config.get("risk_pct", 0.01)
    risk_pct_input = risk_pct

    leverage = config.get("leverage", 5)

    min_score = config.get("min_score", 7)

    rr_target = config.get("rr_target", 2.0)

    min_rr = config.get("min_rr", 1.8)

    max_atr_multiplier = config.get("max_atr_multiplier", 2.0)

    show_levels_when_no_trade = config.get("show_levels_when_no_trade", True)

    modo_operativo = config.get("modo_operativo", "Normal")

    filter_hours = config.get("filter_hours", False)

    avoid_weekends = config.get("avoid_weekends", True)

    use_fvg_filter = config.get("use_fvg_filter", False)

    show_fvg_zones = config.get("show_fvg_zones", True)

    show_mitigated_fvg = config.get("show_mitigated_fvg", True)

    fvg_min_atr = config.get("fvg_min_atr", 0.20)

    fvg_max_distance_atr = config.get("fvg_max_distance_atr", 1.50)

    backtest_period = config.get("backtest_period", "3 meses")

    backtest_tf = config.get("backtest_tf", "15m")

    validate_after_hours = config.get("validate_after_hours", 24)

    mc_enabled = config.get("mc_enabled", True)

    mc_trades_horizon = config.get("mc_trades_horizon", 50)

    mc_paths = config.get("mc_paths", 5000)

    mc_start_capital = config.get("mc_start_capital", account_usd)

    mc_max_daily_trades = config.get("mc_max_daily_trades", 3)

    mc_use_backtest = config.get("mc_use_backtest", True)

    mc_manual_wr = config.get("mc_manual_wr", 45.0)

    mc_manual_rr = config.get("mc_manual_rr", rr_target)

    mc_ruin_dd_pct = config.get("mc_ruin_dd_pct", 30.0)

    auto_capture_enabled = config.get("auto_capture_enabled", True)

    mobile_compact = config.get("mobile_compact", False)

    auto_refresh_enabled = config.get("auto_refresh_enabled", False)

    auto_refresh_seconds = config.get("auto_refresh_seconds", 120)

    telegram_enabled = config.get("telegram_enabled", True)

    telegram_bot_token = config.get("telegram_bot_token", "")

    telegram_chat_id = config.get("telegram_chat_id", "")

    discord_enabled = config.get("discord_enabled", False)

    discord_webhook_url = config.get("discord_webhook_url", "")

    alert_valid_signals = config.get("alert_valid_signals", True)

    alert_almost_setups = config.get("alert_almost_setups", True)

    alert_bias_change = config.get("alert_bias_change", True)

    alert_risk_warning = config.get("alert_risk_warning", False)

    almost_score_gap = config.get("almost_score_gap", 1)

    alert_market_updates = config.get("alert_market_updates", True)

    market_update_minutes = config.get("market_update_minutes", 5)

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
        raw_direction_score = (long_score if candidate_direction == "LONG" else short_score)
        tab1, tab2, tab3, tab4, tab5, tab6, tab7, tab8, tab9, tab10 = st.tabs([
            "🧠 Decisión",
            "📈 Gráfico",
            "🔬 Confluencias",
            "🎯 Trade",
            "📊 Backtest",
            "🌐 Market Intel",
            "💼 Inversión",
            "🛡️ Riesgo",
            "🧬 Quant Rules",
            "⚙️ Configuración"
        ])

        delta_15m = df_15m["volume_delta"].iloc[-1]
        delta_strength_15m = df_15m["delta_strength"].iloc[-1]
        vol_ratio_15m = df_15m["vol_ratio"].iloc[-1]

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

        with tab1:
            st.markdown(
                f"<div style='font-size:20px; font-weight:700;'>"
                f"Calidad del setup: {quality_label} · {quality_score}/10"
                f"</div>",
                unsafe_allow_html=True
            )    
            st.divider()
            col1, col2, col3, col4 = st.columns(4)
            col1.markdown(f"**Precio BTCUSDT**  \n{format_number(price, 2)}")
            col2.markdown(f"**Long Score**  \n{long_score}/10")
            col3.markdown(f"**Short Score**  \n{short_score}/10")
            col4.markdown(f"**RSI 15M**  \n{rsi_15:.2f}  \n{rsi_label}")
            st.divider()

            q1, q2, q3, q4, q5 = st.columns(5)
            q1.markdown(f"**Calidad**\n\n{quality_label}\n\n{quality_score}/10")
            q2.markdown(
                f"**Distancia SL**\n\n{risk_points_calc:.0f} pts\n\nATR 15M: {risk_points_calc:.0f}"
            )
            q3.markdown(
                f"**Setup**\n\n{display_direction(candidate_direction)}\n\nRR: {rr_real:.2f}"
            )
            q4.markdown(
                f"**Distancia TP**\n\n{tp_distance_calc:.0f} pts"
            )
            q5.markdown(
                f"**FVG**\n\n{fvg_label.replace('_',' ')}\n\n{format_number(fvg_distance_atr,2)} ATR"
            )
            st.divider()

            c1, c2, c3, c4, c5 = st.columns(5)
            c1.markdown(f"**24H**\n\n{trend_icon(t1d)}")
            c2.markdown(f"**4H**\n\n{trend_icon(t4)}")
            c3.markdown(f"**1H**\n\n{trend_icon(t1)}")
            c4.markdown(f"**15M**\n\n{trend_icon(t15)}")
            c5.markdown(f"**5M**\n\n{trend_icon(t5)}")
            st.divider()

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
            st.divider()
            st.subheader("🎯 Zonas profesionales Daytrade")
            zonas_daytrade = detectar_zonas_daytrade(
                df_15m=df_15m,
                asia_high=None,
                london_high=None,
                max_zonas=3
            )
            
        with tab2:
            st.subheader("📈 Gráfico operativo intradía")

            modo_grafico = st.radio(
                "Modo de gráfico",
                ["Simple", "Pro", "Institucional"],
                horizontal=True,
                index=1
            )

            # =========================
            # CAPAS DEL GRÁFICO
            # =========================
            if modo_grafico == "Simple":
                show_emas = True
                show_trade_levels = True
                show_profile = True
                show_liquidez = False
                show_fvg = False
                show_order_blocks = False
                show_eq_levels = False
                show_volumen = False
                show_barridos = False
                show_labels_extra = False
            elif modo_grafico == "Pro":
                show_emas = True
                show_trade_levels = True
                show_profile = True
                show_liquidez = True
                show_fvg = True
                show_order_blocks = False
                show_eq_levels = False
                show_volumen = False
                show_barridos = True
                show_labels_extra = False
            else:  # Institucional
                show_emas = True
                show_trade_levels = True
                show_profile = True
                show_liquidez = True
                show_fvg = True
                show_order_blocks = True
                show_eq_levels = True
                show_volumen = True
                show_barridos = True
                show_labels_extra = True

            grafico_operativo_slot = st.container()
            chart_df = df_15m.tail(150).copy()
            fig = go.Figure()
            fig.add_trace(go.Candlestick(
                x=chart_df["time"],
                open=chart_df["open"],
                high=chart_df["high"],
                low=chart_df["low"],
                close=chart_df["close"],
                name="BTC/USDT"
            ))
            fig.add_trace(go.Scatter(
                x=chart_df["time"],
                y=chart_df["ema20"],
                mode="lines",
                name="EMA 20"
            ))
            fig.add_trace(go.Scatter(
                x=chart_df["time"],
                y=chart_df["ema50"],
                mode="lines",
                name="EMA 50"
            ))
            fig.add_trace(go.Scatter(
                x=chart_df["time"],
                y=chart_df["ema200"],
                mode="lines",
                name="EMA 200"
            ))
            

        with tab3:

            st.subheader("🔥 Delta de Volumen PRO")     
            delta_15m = df_15m["volume_delta"].iloc[-1]
            delta_strength_15m = df_15m["delta_strength"].iloc[-1]
            vol_ratio_15m = df_15m["vol_ratio"].iloc[-1]
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
            st.divider()

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
            st.divider()
        

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
            st.divider()

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

        with tab4:
            g1, g2, g3, g4, g5, g6, g7 = st.columns(7)
            g1.metric("Cuenta", f"{account_usd:.0f} USDT")
            g2.metric("Riesgo real", f"{risk_usd:.2f} USDT", f"Obj: {risk_usd_target:.2f}")
            g3.metric("Ganancia TP", f"+{profit_usd:.2f} USDT", f"{profit_pct:.2f}%")
            g4.metric("Tamaño", f"{btc_size:.4f} BTC")
            g5.metric("Nocional real", f"{notional:.0f} USDT")
            g6.metric("Máx nocional", f"{max_notional:.0f} USDT")
            g7.metric("Margen", f"{margin_needed:.0f} USDT")
            st.divider()
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
        with tab5:
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
                            equity["equity_r"] = pd.to_numeric(
                                equity["r_multiple"], errors="coerce"
                            ).fillna(0).cumsum()
                            eq_fig = go.Figure()
                            eq_fig.add_trace(
                                go.Scatter(
                                    x=equity["fecha"],
                                    y=equity["equity_r"],
                                    mode="lines+markers",
                                    name="Equity R"
                                )
                            )
                            eq_fig.update_layout(
                                template="plotly_white",
                                height=350,
                                title="Curva de equity del backtest en R"
                            )
                            st.plotly_chart(
                                eq_fig,
                                use_container_width=True,
                                config={"responsive": True},
                                key="equity_backtest"
                            )
                        st.dataframe(bt_results.tail(50), use_container_width=True)
                        st.download_button(
                            "⬇️ Descargar backtest CSV",
                            data=bt_results.to_csv(index=False),
                            file_name="backtest_results.csv",
                            mime="text/csv",
                            key="download_bt"
                        )
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
                # acá va TODO el bloque de backtest, Monte Carlo, historial, alertas, FVG detectados, reglas
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
            "risk_pct": risk_pct,
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

        with tab1:
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
            st.divider()     

            with st.expander("📌 Motivo de la decisión", expanded=not mobile_compact):
                st.write(f"**Estrategia activa:** {estrategia}")
                st.write(f"**Escenario:** {escenario}")
                st.write(f"**Dirección calculada:** {display_direction(candidate_direction)}")
                st.write(f"**Estructura 5M:** {structure}")
                st.write(f"**Long Score:** {long_score}/10")
                st.write(f"**Short Score:** {short_score}/10")
                st.write(f"**FVG:** {fvg_label}")
                if fvg_zone:
                    st.write(f"**Zona FVG:** {fmt0(fvg_zone['low'])} - {fmt0(fvg_zone['high'])} | MID {fmt0(fvg_zone['mid'])} | Gap {fmt0(fvg_zone['gap_pts'])} pts")
                st.write(f"**Distancia SL:** {format_number(risk_points_calc, 2)} puntos")
                st.write(f"**Score PRO:** {quality_detail['score_100']}/100")
                st.write(f"**Distancia TP:** {format_number(tp_distance_calc, 2)} puntos")
                
                st.write("**Factores positivos:**")
                for p in quality_detail["positivos"]:
                    st.success(p)
                st.write("**Factores negativos / faltantes:**")
                for n in quality_detail["negativos"]:
                    st.warning(n)
                
                
                

        # ===== ORDER BLOCKS EN GRÁFICO =====
        if show_order_blocks and ob_df is not None and not ob_df.empty:
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


        # ====== PERFIL DE LIQUIDEZ EN GRÁFICO ======

        if show_liquidez and liq_profile_df is not None and not liq_profile_df.empty:
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
        if show_volumen and inst_vol_df is not None and not inst_vol_df.empty:
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
        if show_volumen: 
            for name, value in levels.items():
                if not pd.isna(value):
                    fig.add_hline(y=value, line_dash="dot", line_color="gray", annotation_text=name, annotation_position="right")
        should_show_trade_levels = trade_valid or show_levels_when_no_trade
        if should_show_trade_levels and not pd.isna(sl_calc):
            fig.add_hline(y=sl_calc, line_color="red", line_width=3, annotation_text="SL")
        if should_show_trade_levels and not pd.isna(tp_calc):
            fig.add_hline(y=tp_calc, line_color="green", line_width=3, annotation_text="TP")
        fig.add_hline(y=price, line_color="black", line_width=3, annotation_text="Entrada")
        if show_profile and volume_profile:
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
        fig.update_layout(template="plotly_white", height=700, xaxis_rangeslider_visible=False, title="BTCUSDT 15M - Velas + EMAs + Liquidez + FVG + SL/TP", margin=dict(l=20, r=20, t=50, b=20))
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
                config={"responsive": True},
                key="grafico_operativo"
            )
        with tab4:
            

            
    
            

            if st.button("💾 Guardar señal manual", key="save_manual_signal"):
                save_signal_row(SIGNALS_FILE, current_signal_row)
                st.success("Señal guardada correctamente.")

        with tab5:
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
                    st.plotly_chart(dd_fig, use_container_width=True,config={"responsive": True}, key="mc_dd_hist")
                with mc_tabs[1]:
                    curves_fig = go.Figure()
                    x = list(range(1, int(mc_trades_horizon) + 1))
                    for i, curve in enumerate(mc["sample_curves"][:20]):
                        curves_fig.add_trace(go.Scatter(x=x, y=curve, mode="lines", name=f"Escenario {i+1}", opacity=0.35, showlegend=False))
                    curves_fig.add_hline(y=mc_start_capital, line_dash="dot", annotation_text="Capital inicial")
                    curves_fig.add_hline(y=mc_start_capital * (1 - float(mc_ruin_dd_pct) / 100), line_dash="dash", annotation_text=f"Alerta DD {mc_ruin_dd_pct:.0f}%")
                    curves_fig.update_layout(template="plotly_white", height=380, title="Curvas de equity simuladas", xaxis_title="Trade", yaxis_title="Capital USDT", margin=dict(l=20, r=20, t=60, b=20))
                    st.plotly_chart(curves_fig, use_container_width=True,config={"responsive": True}, key="mc_curves")
                with mc_tabs[2]:
                    summary_df = pd.DataFrame([{
                        "fuente": mc_source,
                        "escenarios": mc["paths"],
                        "trades_horizonte": mc["horizon"],
                        "capital_inicial": mc["start_capital"],
                        "riesgo_por_trade_%": mc.get("risk_pct", 0.01),
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
                st.plotly_chart(real_fig, use_container_width=True,config={"responsive": True}, key="equity_real")
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
    

        # ================================================================
        # BTC QUANT TERMINAL — módulos institucionales adicionales
        # ================================================================
        with tab6:
            st.subheader("🌐 BTC Market Intelligence")
            st.caption("Lectura multi-timeframe + riesgo estadístico + derivados/sentimiento públicos opcionales. Ningún dato externo es obligatorio para que la app funcione.")

            quant_snaps = {
                "1D": timeframe_quant_snapshot(df_1d, "1D"),
                "4H": timeframe_quant_snapshot(df_4h, "4H"),
                "1H": timeframe_quant_snapshot(df_1h, "1H"),
                "15M": timeframe_quant_snapshot(df_15m, "15M"),
                "5M": timeframe_quant_snapshot(df_5m, "5M"),
            }
            quant_risk = daily_risk_metrics(df_1d)
            external_live_enabled = st.toggle(
                "🌐 Conectar derivados + sentimiento en vivo",
                value=False,
                key="quant_external_live",
                help="Consulta endpoints públicos de Binance y Alternative.me. El análisis local funciona igual si lo dejás apagado."
            )
            external_btc = fetch_btc_external_metrics() if external_live_enabled else blank_external_btc_metrics()
            trade_context_q = {
                "candidate_direction": candidate_direction,
                "long_score": long_score,
                "short_score": short_score,
                "rr_real": rr_real,
                "quality_score": quality_score,
                "trade_valid": trade_valid,
            }
            quant_rules = build_quant_rulebook(quant_snaps, quant_risk, external_btc, trade_context_q)
            quant_score = quant_rulebook_score(quant_rules)
            regime, vol_regime, expansion_regime = detect_quant_regime(quant_snaps["1D"], quant_risk)
            render_quant_header(quant_score, regime, vol_regime, len(external_btc.get("sources_ok", [])))

            mk1, mk2, mk3, mk4, mk5, mk6 = st.columns(6)
            mk1.metric("BTC", f"{price:,.0f} USDT")
            mk2.metric("Régimen", regime)
            mk3.metric("Score Quant", f"{quant_score:+.0f}/100")
            mk4.metric("Vol 30D anual.", _q_pct(quant_risk.get("vol30"), 1))
            mk5.metric("DD desde ATH", _q_pct(quant_risk.get("current_dd"), 1))
            fg_v = _q_float(external_btc.get("fear_greed"))
            mk6.metric("Fear & Greed", "—" if pd.isna(fg_v) else f"{fg_v:.0f}/100", external_btc.get("fear_greed_label", ""))

            st.divider()
            st.markdown("### 🧭 Radar multi-timeframe")
            tf_rows = []
            for tf_name in ["1D", "4H", "1H", "15M", "5M"]:
                s = quant_snaps[tf_name]
                tf_rows.append({
                    "TF": tf_name,
                    "Sesgo": s.get("bias"),
                    "Score": s.get("score"),
                    "RSI": round(_q_float(s.get("rsi"), 50), 1),
                    "ADX": round(_q_float(s.get("adx"), 0), 1),
                    "ROC20 %": round(_q_float(s.get("roc20"), 0), 2),
                    "ATR %": round(_q_float(s.get("atr_pct"), 0), 2),
                    "CMF": round(_q_float(s.get("cmf"), 0), 3),
                    "MFI": round(_q_float(s.get("mfi"), 50), 1),
                    "Vol Z": round(_q_float(s.get("volume_z"), 0), 2),
                    "BB Pos": round(_q_float(s.get("bb_pos"), 0.5), 2),
                })
            tf_table = pd.DataFrame(tf_rows)
            st.dataframe(tf_table, use_container_width=True, hide_index=True)

            radar_fig = go.Figure()
            radar_fig.add_trace(go.Bar(
                x=tf_table["TF"],
                y=tf_table["Score"],
                text=[f"{x:+.0f}" for x in tf_table["Score"]],
                textposition="outside",
                name="Score TF",
            ))
            radar_fig.add_hline(y=0, line_dash="dot")
            radar_fig.update_layout(template="plotly_white", height=320, title="Dirección cuantitativa por timeframe", yaxis_title="Score -100 a +100", margin=dict(l=20, r=20, t=50, b=20))
            st.plotly_chart(radar_fig, use_container_width=True, config={"responsive": True}, key="quant_tf_radar")

            st.divider()
            st.markdown("### 🧬 Régimen de mercado")
            rg1, rg2, rg3, rg4, rg5 = st.columns(5)
            rg1.metric("Tendencia", regime)
            rg2.metric("Volatilidad", vol_regime)
            rg3.metric("Compresión", expansion_regime)
            rg4.metric("ADX 1D", f"{_q_float(quant_snaps['1D'].get('adx'), 0):.1f}")
            rg5.metric("Percentil vol", _q_pct(quant_risk.get("vol_percentile"), 0))
            st.caption("El régimen combina tendencia, fuerza y volatilidad. Sirve para elegir el tipo de estrategia; no es una orden de compra/venta.")

            st.divider()
            st.markdown("### 🏦 Derivados, sentimiento y microestructura")
            d1, d2, d3, d4, d5, d6 = st.columns(6)
            funding = _q_float(external_btc.get("funding_rate"))
            oi_btc = _q_float(external_btc.get("open_interest_btc"))
            oi_chg = _q_float(external_btc.get("open_interest_change_pct"))
            ls_ratio = _q_float(external_btc.get("global_long_short"))
            taker_ratio = _q_float(external_btc.get("taker_buy_sell"))
            book_imb = _q_float(external_btc.get("orderbook_imbalance"))
            d1.metric("Funding", "—" if pd.isna(funding) else f"{funding:+.4f}%")
            d2.metric("Open Interest", "—" if pd.isna(oi_btc) else f"{oi_btc:,.0f} BTC", "—" if pd.isna(oi_chg) else f"{oi_chg:+.2f}% ~150m")
            d3.metric("Global Long/Short", "—" if pd.isna(ls_ratio) else f"{ls_ratio:.2f}")
            d4.metric("Taker Buy/Sell", "—" if pd.isna(taker_ratio) else f"{taker_ratio:.2f}")
            d5.metric("Book imbalance", "—" if pd.isna(book_imb) else f"{book_imb:+.1f}%")
            mark = _q_float(external_btc.get("mark_price"))
            index_p = _q_float(external_btc.get("index_price"))
            premium_bps = (_q_safe_div(mark, index_p, 1) - 1) * 10000 if not pd.isna(mark) and not pd.isna(index_p) else np.nan
            d6.metric("Mark premium", "—" if pd.isna(premium_bps) else f"{premium_bps:+.1f} bps")

            ext_table = pd.DataFrame([
                {"Métrica": "Fear & Greed", "Valor": "—" if pd.isna(fg_v) else f"{fg_v:.0f}", "Lectura": external_btc.get("fear_greed_label", "")},
                {"Métrica": "Market Cap BTC", "Valor": _q_money(external_btc.get("market_cap_usd")), "Lectura": "Dato de mercado público opcional"},
                {"Métrica": "Volumen 24h", "Valor": _q_money(external_btc.get("volume_24h_usd")), "Lectura": "Dato de mercado público opcional"},
                {"Métrica": "Cambio 24h", "Valor": _q_pct(external_btc.get("change_24h_pct")), "Lectura": "Momentum corto"},
                {"Métrica": "Cambio 7d", "Valor": _q_pct(external_btc.get("change_7d_pct")), "Lectura": "Momentum semanal"},
            ])
            st.dataframe(ext_table, use_container_width=True, hide_index=True)
            ok_sources = external_btc.get("sources_ok", [])
            if ok_sources:
                st.success("Fuentes externas activas: " + " · ".join(ok_sources))
            if external_btc.get("errors"):
                with st.expander("Diagnóstico de fuentes externas"):
                    st.write(" · ".join(external_btc["errors"]))
                    st.caption("Esto no invalida el motor local: OHLCV, riesgo y reglas cuantitativas siguen funcionando.")
            st.caption("Fear & Greed: Alternative.me. Datos de derivados/order book: endpoints públicos de Binance cuando están disponibles.")

            st.divider()
            st.markdown("### 📉 Riesgo estadístico de BTC")
            rs1, rs2, rs3, rs4, rs5, rs6 = st.columns(6)
            rs1.metric("VaR 95% diario", _q_pct(quant_risk.get("var95"), 2))
            rs2.metric("CVaR 95% diario", _q_pct(quant_risk.get("cvar95"), 2))
            rs3.metric("Máx. DD muestra", _q_pct(quant_risk.get("max_dd"), 1))
            rs4.metric("Sharpe", f"{_q_float(quant_risk.get('sharpe'), 0):.2f}")
            rs5.metric("Sortino", f"{_q_float(quant_risk.get('sortino'), 0):.2f}")
            rs6.metric("Ulcer Index", f"{_q_float(quant_risk.get('ulcer'), 0):.1f}")
            st.caption(f"Muestra diaria disponible: {int(quant_risk.get('sample_days', 0))} retornos. VaR/CVaR son estimaciones históricas, no límites garantizados de pérdida.")

            qd = prepare_quant_frame(df_1d)
            if not qd.empty:
                chart_qd = qd.tail(365).copy()
                market_fig = go.Figure()
                market_fig.add_trace(go.Scatter(x=chart_qd["time"], y=chart_qd["close"], mode="lines", name="BTC"))
                market_fig.add_trace(go.Scatter(x=chart_qd["time"], y=chart_qd["ema50"], mode="lines", name="EMA50"))
                market_fig.add_trace(go.Scatter(x=chart_qd["time"], y=chart_qd["ema200"], mode="lines", name="EMA200"))
                market_fig.update_layout(template="plotly_white", height=420, title="BTC diario · precio + régimen tendencial", yaxis_title="USDT", margin=dict(l=20, r=20, t=50, b=20))
                st.plotly_chart(market_fig, use_container_width=True, config={"responsive": True}, key="quant_daily_regime")

            st.divider()
            st.markdown("### 🧪 Análogos históricos del régimen actual")
            analog_stats, analog_df = historical_regime_analogs(df_1d)
            if analog_stats:
                an1, an2, an3, an4, an5, an6 = st.columns(6)
                an1.metric("Casos comparables", int(analog_stats.get("samples", 0)))
                an2.metric("Prob. +7D", _q_pct(analog_stats.get("p_up_7"), 0))
                an3.metric("Mediana +7D", _q_pct(analog_stats.get("median_7"), 1))
                an4.metric("Prob. +30D", _q_pct(analog_stats.get("p_up_30"), 0))
                an5.metric("Mediana +30D", _q_pct(analog_stats.get("median_30"), 1))
                an6.metric("Rango P10–P90 30D", f"{_q_pct(analog_stats.get('p10_30'),1)} / {_q_pct(analog_stats.get('p90_30'),1)}")
                st.caption("Compara únicamente episodios pasados con coincidencia en régimen EMA200, momentum, volatilidad y bucket de RSI. No es una probabilidad predictiva garantizada.")
                with st.expander("Ver episodios históricos comparables"):
                    cols = [c for c in ["time", "close", "rsi14", "vol30_ann", "fwd_7", "fwd_30", "fwd_90"] if c in analog_df.columns]
                    st.dataframe(analog_df[cols].head(100), use_container_width=True, hide_index=True)
            else:
                st.info("Todavía no hay suficiente histórico diario para formar un conjunto robusto de análogos.")

        with tab7:
            st.subheader("💼 BTC Investment Lab")
            st.caption("Comparador de enfoques: HODL, DCA, DCA adaptativo, trend following, swing, mean reversion, grid y futuros tácticos. Los scores son de contexto, no recomendaciones personalizadas.")

            # Los módulos anteriores se ejecutan aunque la pestaña no esté visualmente abierta.
            if "quant_snaps" not in locals():
                quant_snaps = {"1D": timeframe_quant_snapshot(df_1d, "1D"), "4H": timeframe_quant_snapshot(df_4h, "4H"), "1H": timeframe_quant_snapshot(df_1h, "1H"), "15M": timeframe_quant_snapshot(df_15m, "15M"), "5M": timeframe_quant_snapshot(df_5m, "5M")}
                quant_risk = daily_risk_metrics(df_1d)
                external_btc = blank_external_btc_metrics()
                trade_context_q = {"candidate_direction": candidate_direction, "long_score": long_score, "short_score": short_score, "rr_real": rr_real, "quality_score": quality_score, "trade_valid": trade_valid}

            inv_matrix = build_investment_matrix(quant_snaps, quant_risk, external_btc, trade_context_q)
            best_inv = inv_matrix.iloc[0] if not inv_matrix.empty else None
            if best_inv is not None:
                st.markdown(f"**Mejor encaje con el régimen actual:** {best_inv['Estrategia']} · {best_inv['Score']}/100 · {best_inv['Estado']}")
            st.dataframe(inv_matrix, use_container_width=True, hide_index=True)

            st.divider()
            st.markdown("### 🪙 Simulador histórico de acumulación")
            i1, i2, i3, i4 = st.columns(4)
            dca_initial = i1.number_input("Capital inicial USDT", min_value=0.0, value=500.0, step=100.0, key="quant_dca_initial")
            dca_periodic = i2.number_input("Aporte periódico USDT", min_value=1.0, value=200.0, step=25.0, key="quant_dca_periodic")
            dca_freq = i3.selectbox("Frecuencia", ["Semanal", "Quincenal", "Mensual"], index=2, key="quant_dca_freq")
            dca_mode = i4.selectbox("Modo", ["DCA fijo", "DCA adaptativo"], key="quant_dca_mode")
            dca_df, dca_stats = simulate_dca_history(df_1d, dca_periodic, dca_initial, dca_freq, adaptive=(dca_mode == "DCA adaptativo"))
            if dca_stats:
                a1, a2, a3, a4, a5, a6 = st.columns(6)
                a1.metric("Invertido", _q_money(dca_stats.get("invested"), 0))
                a2.metric("BTC acumulado", f"{_q_float(dca_stats.get('btc'), 0):.6f}")
                a3.metric("Precio medio", _q_money(dca_stats.get("avg_price"), 0))
                a4.metric("Valor final", _q_money(dca_stats.get("final_value"), 0))
                a5.metric("Retorno DCA", _q_pct(dca_stats.get("return_pct"), 1))
                a6.metric("Lump-sum mismo presupuesto", _q_pct(dca_stats.get("lump_return_pct"), 1))
                dca_fig = go.Figure()
                dca_fig.add_trace(go.Scatter(x=dca_df["Fecha"], y=dca_df["Valor"], mode="lines", name="Valor estrategia"))
                dca_fig.add_trace(go.Scatter(x=dca_df["Fecha"], y=dca_df["Invertido"], mode="lines", name="Capital aportado"))
                dca_fig.update_layout(template="plotly_white", height=380, title=f"{dca_mode} · evolución histórica", yaxis_title="USDT", margin=dict(l=20, r=20, t=50, b=20))
                st.plotly_chart(dca_fig, use_container_width=True, config={"responsive": True}, key="quant_dca_chart")
                with st.expander("Ver compras simuladas"):
                    st.dataframe(dca_df.tail(100), use_container_width=True, hide_index=True)
                    st.download_button("⬇️ Descargar simulación DCA", dca_df.to_csv(index=False), "btc_dca_simulation.csv", "text/csv", key="download_quant_dca")
            else:
                st.info("No hay suficiente histórico diario para simular DCA.")

            st.divider()
            st.markdown("### 🎯 Constructor de posición Spot / Cash")
            p1, p2, p3 = st.columns(3)
            inv_capital = p1.number_input("Capital total USDT", min_value=0.0, value=float(max(account_usd, 100.0)), step=100.0, key="quant_inv_capital")
            btc_alloc = p2.slider("Asignación BTC %", 0, 100, 70, 5, key="quant_btc_alloc")
            reserve_pct = 100 - btc_alloc
            p3.metric("Reserva cash", f"{reserve_pct}%")
            btc_usd = inv_capital * btc_alloc / 100
            cash_usd = inv_capital - btc_usd
            btc_qty_plan = btc_usd / price if price else 0
            z1, z2, z3, z4 = st.columns(4)
            z1.metric("BTC a precio actual", f"{btc_qty_plan:.6f} BTC")
            z2.metric("Exposición BTC", _q_money(btc_usd, 0))
            z3.metric("Cash / dry powder", _q_money(cash_usd, 0))
            z4.metric("Precio BTC", _q_money(price, 0))
            scenario_df = portfolio_scenario_table(price, btc_usd, cash_usd)
            st.dataframe(scenario_df, use_container_width=True, hide_index=True)

            st.divider()
            st.markdown("### 🧠 Reglas por estilo de inversión")
            style = st.selectbox("Analizar estilo", inv_matrix["Estrategia"].tolist(), key="quant_style_selector") if not inv_matrix.empty else None
            if style:
                row = inv_matrix[inv_matrix["Estrategia"] == style].iloc[0]
                st.markdown(f"**{row['Estrategia']} · {row['Score']}/100 · {row['Estado']}**")
                st.write(f"**Horizonte:** {row['Horizonte']}")
                st.write(f"**Régimen ideal:** {row['Regla principal']}")
                st.write(f"**Requisitos:** {row['Qué exige']}")
                st.write(f"**Riesgo principal:** {row['Riesgo']}")

        with tab8:
            st.subheader("🛡️ BTC Risk & Survival Lab")
            st.caption("El objetivo de esta pestaña es supervivencia: dimensionamiento, drawdown, VaR/CVaR, leverage y escenarios de estrés.")

            if "quant_risk" not in locals():
                quant_risk = daily_risk_metrics(df_1d)

            rsk1, rsk2, rsk3, rsk4, rsk5, rsk6 = st.columns(6)
            rsk1.metric("Vol 30D", _q_pct(quant_risk.get("vol30"), 1))
            rsk2.metric("Vol 90D", _q_pct(quant_risk.get("vol90"), 1))
            rsk3.metric("VaR 99%", _q_pct(quant_risk.get("var99"), 2))
            rsk4.metric("CVaR 99%", _q_pct(quant_risk.get("cvar99"), 2))
            rsk5.metric("Peor día muestra", _q_pct(quant_risk.get("worst_day"), 2))
            rsk6.metric("Días positivos", _q_pct(quant_risk.get("positive_days"), 1))

            st.divider()
            st.markdown("### 📐 Position Sizing independiente")
            ps1, ps2, ps3, ps4 = st.columns(4)
            ps_account = ps1.number_input("Cuenta USDT", min_value=1.0, value=float(account_usd), step=100.0, key="quant_ps_account")
            ps_risk = ps2.slider("Riesgo por trade %", 0.10, 5.00, float(min(max(risk_pct * 100, 0.1), 5.0)), 0.10, key="quant_ps_risk")
            ps_stop = ps3.number_input("Stop técnico %", min_value=0.10, value=1.50, step=0.10, key="quant_ps_stop")
            ps_lev = ps4.slider("Leverage máximo", 1, 50, int(min(max(leverage, 1), 50)), 1, key="quant_ps_lev")
            risk_budget = ps_account * ps_risk / 100
            raw_notional = risk_budget / (ps_stop / 100) if ps_stop else 0
            max_notional_ps = ps_account * ps_lev
            final_notional_ps = min(raw_notional, max_notional_ps)
            btc_size_ps = final_notional_ps / price if price else 0
            actual_risk_ps = final_notional_ps * ps_stop / 100
            sz1, sz2, sz3, sz4, sz5 = st.columns(5)
            sz1.metric("Budget de riesgo", _q_money(risk_budget, 2))
            sz2.metric("Nocional por stop", _q_money(raw_notional, 0))
            sz3.metric("Nocional permitido", _q_money(final_notional_ps, 0))
            sz4.metric("Tamaño BTC", f"{btc_size_ps:.5f}")
            sz5.metric("Riesgo real", _q_money(actual_risk_ps, 2))
            if raw_notional > max_notional_ps:
                st.warning("El tamaño calculado por stop supera el nocional permitido por margen. Se capó automáticamente al máximo por leverage.")

            st.divider()
            st.markdown("### 🎲 Kelly Criterion · referencia estadística")
            bt_wr = _q_float(bt_stats.get("winrate", np.nan)) if "bt_stats" in locals() else np.nan
            bt_payoff = _q_float(bt_stats.get("rr_promedio", np.nan)) if "bt_stats" in locals() else np.nan
            kc1, kc2 = st.columns(2)
            k_win = kc1.number_input("Win rate %", min_value=1.0, max_value=99.0, value=float(bt_wr if not pd.isna(bt_wr) and 1 <= bt_wr <= 99 else 45.0), step=1.0, key="quant_kelly_wr")
            k_rr = kc2.number_input("Payoff ganador/perdedor", min_value=0.10, max_value=10.0, value=float(bt_payoff if not pd.isna(bt_payoff) and bt_payoff > 0 else max(rr_target, 0.1)), step=0.10, key="quant_kelly_rr")
            k = kelly_fraction(k_win, k_rr)
            kk1, kk2, kk3 = st.columns(3)
            kk1.metric("Kelly completo", _q_pct(k["full"] * 100, 1))
            kk2.metric("½ Kelly", _q_pct(k["half"] * 100, 1))
            kk3.metric("¼ Kelly", _q_pct(k["quarter"] * 100, 1))
            st.caption("Kelly es muy sensible a estimaciones erróneas del edge. En trading real suele usarse fraccionado y con límites de riesgo mucho menores.")

            st.divider()
            st.markdown("### ⚠️ Tabla de supervivencia por leverage")
            lev_df = leverage_survival_table(price, ps_account, ps_risk / 100)
            st.dataframe(lev_df, use_container_width=True, hide_index=True)
            st.caption("*El movimiento a liquidación es una aproximación educativa 1/leverage. La liquidación real depende de maintenance margin, fees, mark price y reglas del exchange.")

            st.divider()
            st.markdown("### 💥 Stress test de una posición")
            stress1, stress2, stress3 = st.columns(3)
            stress_notional = stress1.number_input("Nocional de posición USDT", min_value=0.0, value=float(max(notional, 0.0)), step=100.0, key="quant_stress_notional")
            stress_dir = stress2.selectbox("Dirección", ["LONG", "SHORT"], index=0 if candidate_direction != "SHORT" else 1, key="quant_stress_dir")
            stress_account = stress3.number_input("Equity cuenta USDT", min_value=1.0, value=float(account_usd), step=100.0, key="quant_stress_account")
            stress_rows = []
            for mv in [-30, -20, -15, -10, -7.5, -5, -3, -2, -1, 1, 2, 3, 5, 7.5, 10, 15, 20, 30]:
                pnl_s = stress_notional * mv / 100 * (1 if stress_dir == "LONG" else -1)
                eq_s = stress_account + pnl_s
                stress_rows.append({"Movimiento BTC %": mv, "PNL USDT": pnl_s, "Equity estimada": eq_s, "Impacto cuenta %": _q_safe_div(pnl_s, stress_account, 0) * 100, "Estado": "🔴 RUINA" if eq_s <= 0 else "🟠 CRÍTICO" if eq_s < stress_account * 0.7 else "🟡 ALTO" if eq_s < stress_account * 0.85 else "🟢"})
            stress_df = pd.DataFrame(stress_rows)
            st.dataframe(stress_df, use_container_width=True, hide_index=True)

            st.divider()
            st.markdown("### 🧯 Matemática de recuperación de drawdown")
            st.dataframe(drawdown_recovery_table(), use_container_width=True, hide_index=True)

            st.divider()
            st.markdown("### 📊 Distribución de retornos diarios")
            qd_risk = prepare_quant_frame(df_1d)
            rets = qd_risk["ret"].dropna() * 100 if not qd_risk.empty else pd.Series(dtype=float)
            if not rets.empty:
                ret_fig = go.Figure()
                ret_fig.add_trace(go.Histogram(x=rets, nbinsx=60, name="Retorno diario %"))
                if not pd.isna(_q_float(quant_risk.get("var95"))):
                    ret_fig.add_vline(x=quant_risk["var95"], line_dash="dash", annotation_text="VaR95")
                if not pd.isna(_q_float(quant_risk.get("var99"))):
                    ret_fig.add_vline(x=quant_risk["var99"], line_dash="dot", annotation_text="VaR99")
                ret_fig.update_layout(template="plotly_white", height=360, title="Distribución histórica de retornos diarios BTC", xaxis_title="Retorno %", yaxis_title="Frecuencia", margin=dict(l=20, r=20, t=50, b=20))
                st.plotly_chart(ret_fig, use_container_width=True, config={"responsive": True}, key="quant_return_hist")

            st.divider()
            with st.expander("🧾 Reglas de supervivencia obligatorias", expanded=True):
                st.write("""
                - El stop técnico define el tamaño; el tamaño nunca define dónde poner el stop.
                - No aumentar leverage para compensar una entrada tardía.
                - Riesgo total simultáneo debe considerar todas las posiciones correlacionadas como una sola exposición BTC.
                - Funding, OI y crowding son factores de contexto, no señales independientes.
                - Si la volatilidad entra en percentiles extremos, reducir tamaño o frecuencia suele ser más robusto que ampliar stops sin límite.
                - VaR y CVaR describen el histórico disponible; no contienen el peor caso futuro.
                - Nunca usar el precio de liquidación como stop operativo.
                - Si el trade invalida la tesis, salir; no convertir un trade apalancado en una inversión forzada.
                """)

        with tab9:
            st.subheader("🧬 Quant Rules · Motor auditable")
            st.caption("Cada fila muestra una regla, su evidencia, peso e impacto. El score final se puede inspeccionar y exportar.")

            if "quant_snaps" not in locals():
                quant_snaps = {"1D": timeframe_quant_snapshot(df_1d, "1D"), "4H": timeframe_quant_snapshot(df_4h, "4H"), "1H": timeframe_quant_snapshot(df_1h, "1H"), "15M": timeframe_quant_snapshot(df_15m, "15M"), "5M": timeframe_quant_snapshot(df_5m, "5M")}
                quant_risk = daily_risk_metrics(df_1d)
                external_btc = blank_external_btc_metrics()
                trade_context_q = {"candidate_direction": candidate_direction, "long_score": long_score, "short_score": short_score, "rr_real": rr_real, "quality_score": quality_score, "trade_valid": trade_valid}
            if "quant_rules" not in locals():
                quant_rules = build_quant_rulebook(quant_snaps, quant_risk, external_btc, trade_context_q)
            quant_score = quant_rulebook_score(quant_rules)

            if quant_score >= 35:
                score_state = "🟢 Contexto cuantitativo favorable al lado comprador"
            elif quant_score <= -35:
                score_state = "🔴 Contexto cuantitativo favorable al lado vendedor"
            else:
                score_state = "🟡 Contexto mixto: priorizar selectividad"
            qr1, qr2, qr3, qr4 = st.columns(4)
            qr1.metric("Quant Score", f"{quant_score:+.0f}/100")
            qr2.metric("Reglas evaluadas", len(quant_rules))
            qr3.metric("Positivas", int((quant_rules["Impacto"] > 0).sum()))
            qr4.metric("Negativas", int((quant_rules["Impacto"] < 0).sum()))
            st.markdown(f"**{score_state}**")

            cat_summary = quant_rules.groupby("Categoría", as_index=False).agg(Reglas=("Regla", "count"), Impacto=("Impacto", "sum"), Peso=("Peso", "sum"))
            cat_summary["Score categoría"] = np.where(cat_summary["Peso"] > 0, 100 * cat_summary["Impacto"] / cat_summary["Peso"], 0)
            cat_summary = cat_summary.sort_values("Score categoría", ascending=False)
            st.dataframe(cat_summary, use_container_width=True, hide_index=True)

            cat_fig = go.Figure()
            cat_fig.add_trace(go.Bar(x=cat_summary["Categoría"], y=cat_summary["Score categoría"], text=[f"{x:+.0f}" for x in cat_summary["Score categoría"]], textposition="outside"))
            cat_fig.add_hline(y=0, line_dash="dot")
            cat_fig.update_layout(template="plotly_white", height=360, title="Score por familia de reglas", yaxis_title="-100 a +100", margin=dict(l=20, r=20, t=50, b=20))
            st.plotly_chart(cat_fig, use_container_width=True, config={"responsive": True}, key="quant_rules_category")

            st.divider()
            f1, f2 = st.columns([1, 2])
            categories = sorted(quant_rules["Categoría"].dropna().unique().tolist())
            selected_categories = f1.multiselect("Filtrar categorías", categories, default=categories, key="quant_rule_categories")
            state_filter = f2.multiselect("Filtrar estados", ["✅", "⚠️", "❌", "ℹ️"], default=["✅", "⚠️", "❌", "ℹ️"], key="quant_rule_states")
            rules_view = quant_rules[quant_rules["Categoría"].isin(selected_categories) & quant_rules["Estado"].isin(state_filter)]
            st.dataframe(rules_view, use_container_width=True, hide_index=True)
            st.download_button("⬇️ Descargar rulebook CSV", quant_rules.to_csv(index=False), "btc_quant_rulebook.csv", "text/csv", key="download_quant_rulebook")

            positives = quant_rules.sort_values("Impacto", ascending=False).head(8)
            negatives = quant_rules.sort_values("Impacto", ascending=True).head(8)
            cpos, cneg = st.columns(2)
            with cpos:
                st.markdown("#### ✅ Mayores confluencias")
                for _, rr in positives.iterrows():
                    if rr["Impacto"] > 0:
                        st.write(f"**+{rr['Impacto']:.0f}** · {rr['Regla']} · {rr['Valor']}")
            with cneg:
                st.markdown("#### ❌ Mayores riesgos / contradicciones")
                for _, rr in negatives.iterrows():
                    if rr["Impacto"] < 0:
                        st.write(f"**{rr['Impacto']:.0f}** · {rr['Regla']} · {rr['Valor']}")

            st.divider()
            st.markdown("### 🌎 Macro + On-chain + Event Risk · capa manual auditable")
            st.caption("Estos factores no se inventan: se dejan en 'No informado' hasta que cargues un dato confiable. Así el score no finge conocer ETF flows, DXY, MVRV o SOPR cuando no hay una fuente conectada.")
            mc1, mc2, mc3, mc4 = st.columns(4)
            dxy_state = mc1.selectbox("DXY", ["No informado", "Bajando", "Neutral", "Subiendo"], key="quant_dxy")
            yields_state = mc2.selectbox("US10Y", ["No informado", "Bajando", "Neutral", "Subiendo"], key="quant_us10y")
            etf_flow = mc3.selectbox("ETF BTC net flow", ["No informado", "Fuerte entrada", "Entrada", "Neutral", "Salida", "Fuerte salida"], key="quant_etf")
            exch_flow = mc4.selectbox("Exchange netflow", ["No informado", "Fuerte salida BTC", "Salida BTC", "Neutral", "Entrada BTC", "Fuerte entrada BTC"], key="quant_exchange_flow")
            oc1, oc2, oc3, oc4 = st.columns(4)
            mvrv = oc1.selectbox("MVRV", ["No informado", "Infravalorado", "Normal", "Elevado", "Extremo"], key="quant_mvrv")
            sopr = oc2.selectbox("SOPR", ["No informado", "Capitulación", "Debajo de 1", "Cerca de 1", "Encima de 1", "Euforia"], key="quant_sopr")
            stable = oc3.selectbox("Liquidez stablecoins", ["No informado", "Contrayendo", "Neutral", "Expandiendo"], key="quant_stable")
            hashtrend = oc4.selectbox("Hashrate", ["No informado", "Cayendo", "Lateral", "Subiendo"], key="quant_hash")

            ev1, ev2, ev3 = st.columns(3)
            high_macro_event = ev1.checkbox("Evento macro de alto impacto <24h", key="quant_macro_event")
            options_expiry = ev2.checkbox("Vencimiento importante opciones <24h", key="quant_options_expiry")
            exchange_incident = ev3.checkbox("Incidente exchange / liquidez", key="quant_exchange_incident")

            manual_points = 0
            manual_max = 0
            mapping = [
                {"Bajando": 2, "Neutral": 0, "Subiendo": -2}.get(dxy_state, None),
                {"Bajando": 1, "Neutral": 0, "Subiendo": -1}.get(yields_state, None),
                {"Fuerte entrada": 3, "Entrada": 2, "Neutral": 0, "Salida": -2, "Fuerte salida": -3}.get(etf_flow, None),
                {"Fuerte salida BTC": 2, "Salida BTC": 1, "Neutral": 0, "Entrada BTC": -1, "Fuerte entrada BTC": -2}.get(exch_flow, None),
                {"Infravalorado": 2, "Normal": 0, "Elevado": -1, "Extremo": -3}.get(mvrv, None),
                {"Capitulación": 1, "Debajo de 1": 1, "Cerca de 1": 0, "Encima de 1": 1, "Euforia": -2}.get(sopr, None),
                {"Contrayendo": -1, "Neutral": 0, "Expandiendo": 1}.get(stable, None),
                {"Cayendo": -1, "Lateral": 0, "Subiendo": 1}.get(hashtrend, None),
            ]
            for val in mapping:
                if val is not None:
                    manual_points += val
                    manual_max += 3
            event_penalty = (3 if high_macro_event else 0) + (2 if options_expiry else 0) + (5 if exchange_incident else 0)
            manual_score = 100 * manual_points / manual_max if manual_max else 0
            adjusted_score = float(np.clip(quant_score * 0.8 + manual_score * 0.2 - event_penalty * 2, -100, 100)) if manual_max else float(np.clip(quant_score - event_penalty * 2, -100, 100))
            ma1, ma2, ma3 = st.columns(3)
            ma1.metric("Score automático", f"{quant_score:+.0f}")
            ma2.metric("Score manual macro/on-chain", "Sin datos" if not manual_max else f"{manual_score:+.0f}")
            ma3.metric("Score ajustado", f"{adjusted_score:+.0f}", f"penalización eventos: -{event_penalty * 2}")

            with st.expander("📚 Rulebook maestro · principios que nunca deben saltarse"):
                st.write("""
                **Datos y contexto**
                - No usar una única métrica para decidir. Exigir confluencia y distinguir tendencia, momentum, volatilidad y flujo.
                - Un dato externo caído debe figurar como no disponible, nunca convertirse en cero o en una señal falsa.
                - Separar timeframe de entrada del timeframe de tesis. Un 5M alcista no invalida por sí solo un 1D bajista.
                - Un indicador retrasado confirma; no anticipa automáticamente.

                **Spot / acumulación**
                - DCA reduce riesgo de timing, no elimina riesgo de drawdown.
                - Lump-sum aumenta exposición temporal; su conveniencia depende de horizonte y tolerancia al riesgo.
                - Mantener reserva de liquidez si el plan contempla comprar drawdowns.
                - No financiar una inversión spot de largo plazo con deuda que pueda exigir liquidación forzada.

                **Futuros**
                - El leverage es una herramienta de eficiencia de margen, no una licencia para aumentar el riesgo de cuenta.
                - El riesgo por trade debe medirse sobre equity, no sobre margen usado.
                - Funding extremo + OI creciente + crowding aumenta riesgo de squeeze.
                - Nunca mover SL para evitar reconocer una invalidación.
                - No promediar pérdidas apalancadas sin una regla explícita de tamaño máximo agregado.

                **Riesgo**
                - El drawdown compuesto requiere más retorno porcentual para recuperarse: -50% necesita +100%.
                - VaR/CVaR históricos no incluyen todos los gaps, fallas de exchange ni eventos de cola futuros.
                - Correlaciones aumentan en crisis; varias posiciones crypto pueden ser una sola apuesta de riesgo.
                - La prioridad es evitar ruina. Una estrategia sin supervivencia no tiene oportunidad de expresar su edge.
                """)


            st.caption(f"Última actualización local: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

        with tab10:
            render_btc_configuration()

    except Exception as e:
        st.error("Hubo un error cargando el dashboard.")
        st.exception(e)
