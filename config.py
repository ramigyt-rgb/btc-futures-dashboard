# =========================
# CONFIG GENERAL
# =========================
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
FVG_MIN_ATR = 0.20
FVG_MAX_DISTANCE_ATR = 1.50

fvg_min_atr = FVG_MIN_ATR
fvg_max_distance_atr = FVG_MAX_DISTANCE_ATR

STRATEGIES = [
    "Tendencia + Liquidez",
    "Pullback EMA50",
    "Sweep de Liquidez",
    "Ruptura de Estructura",
    "Reversión Extrema",
    "FVG + Tendencia",
]

