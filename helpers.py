# =========================
# HELPERS GENERALES
# =========================
import os
import numpy as np
import pandas as pd
from config import OPEN_TRADE_FILE
import hashlib
from datetime import datetime
import ccxt
import plotly.graph_objects as go
import streamlit as st
import streamlit.components.v1 as components
try:
    import requests
except Exception:
    requests = None
    
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