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

import streamlit as st

st.sidebar.title("Configuración")

st.sidebar.subheader("🔐 Acceso")

if "auth" not in st.session_state:

    st.session_state.auth = False

clave = st.sidebar.text_input("Clave de acceso", type="password")

if clave == ACCESS_KEY:

    st.session_state.auth = True

if st.session_state.auth:

    st.sidebar.success("Acceso habilitado")

    if st.sidebar.button("Cerrar acceso"):

        st.session_state.auth = False

        st.rerun()

    from ui import render_dashboard

    render_dashboard()

else:

    st.info("Ingrese la clave de acceso para abrir el dashboard.")

if check_access():

    render_dashboard()

else:

    st.info("Ingrese la clave de acceso para abrir el dashboard.")
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
