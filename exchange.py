# =========================
# EXCHANGE / DATA
# =========================
from config import * 
import os
import hashlib
from datetime import datetime
from analysis import add_volume_delta
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
@st.cache_resource(show_spinner=False)
def get_exchange():
    return ccxt.okx({"enableRateLimit": True, "options": {"defaultType": "swap"}})
@st.cache_data(ttl=60, show_spinner=False)
def get_ohlcv(timeframe, limit=300):
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