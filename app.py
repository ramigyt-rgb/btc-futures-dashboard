# =========================

# APP

# =========================

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
