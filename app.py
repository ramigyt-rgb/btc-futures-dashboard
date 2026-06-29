# =========================
# APP PRINCIPAL
# =========================
import streamlit as st
st.set_page_config(
    page_title="BTCUSDT Futures Dashboard Pro",
    layout="wide",
    initial_sidebar_state="expanded"
)
from login import check_access

if check_access():
    from ui import render_dashboard
    render_dashboard()
else:
    st.info("Ingrese la clave de acceso para abrir el dashboard.")
