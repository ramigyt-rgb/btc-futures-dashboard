# =========================
# APP
# =========================
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

from config import *
from helpers import *
from exchange import *
from analysis import *
from backtest import *
from ui import *
from sidebar import *
from login import *
from telegram import *
from alertas import *

st.title("BTC/USDT FUTUROS")
init_open_trade_file()
st.caption("Sistema objetivo: tendencia + liquidez + estructura + score + riesgo + FVG + backtesting + Monte Carlo + alertas estratégicas. No es consejo financiero.")
render_dashboard()