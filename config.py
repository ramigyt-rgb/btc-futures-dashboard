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

    .block-container {

        padding-top: 1rem !important;

        padding-left: 0.7rem !important;

        padding-right: 0.7rem !important;

        max-width: 100% !important;

    }

    h1 {

        font-size: 1.65rem !important;

        line-height: 1.2 !important;

    }

    h2 {

        font-size: 1.25rem !important;

    }

    h3 {

        font-size: 1.05rem !important;

    }

    div[data-testid="stMetricValue"] {

        font-size: 1.1rem !important;

    }

    div[data-testid="stMetricLabel"] {

        font-size: 0.75rem !important;

    }

    .stTabs [data-baseweb="tab"] {

        font-size: 0.75rem !important;

        padding: 0.35rem 0.45rem !important;

    }

    div[data-testid="stDataFrame"] {

        font-size: 0.72rem !important;

    }

    .js-plotly-plot {

        width: 100% !important;

    }

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

