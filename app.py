# =========================
# APP PRINCIPAL
# =========================
import streamlit as st
from login import check_access
st.set_page_config(
    page_title="BTCUSDT Futures Dashboard Pro",
    layout="wide",
    initial_sidebar_state="expanded"
)

