# =========================
# LOGIN SIMPLE
# =========================
from config import *
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
def check_access():
    st.sidebar.subheader("🔐 Acceso")
    if "auth" not in st.session_state:
        st.session_state.auth = False
    if st.session_state.auth:
        st.sidebar.success("Acceso habilitado")
        if st.sidebar.button("Cerrar acceso"):
            st.session_state.auth = False
            st.rerun()
        return True
    clave = st.sidebar.text_input("Clave de acceso", type="password")
    if clave:
        if check_login("demo", clave):
            st.session_state.auth = True
            st.rerun()
        else:
            st.sidebar.error("Clave incorrecta")
    return False

        