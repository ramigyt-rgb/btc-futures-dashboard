# =========================
# LOGIN PRO
# =========================
import streamlit as st
from config import ACCESS_KEY
def check_access():
    if "auth" not in st.session_state:
        st.session_state.auth = False
    if st.session_state.auth:
        return True
    st.markdown("""
    <style>
    [data-testid="stSidebar"] {
        display: none;
    }
    .stApp {
        background: radial-gradient(circle at top, #1f2937 0%, #05070d 55%, #020308 100%);
    }
    .login-card {
        max-width: 430px;
        margin: 12vh auto 0 auto;
        padding: 38px 34px;
        border-radius: 24px;
        background: rgba(15, 23, 42, 0.92);
        border: 1px solid rgba(255, 255, 255, 0.10);
        box-shadow: 0 28px 80px rgba(0,0,0,0.45);
        text-align: center;
    }
    .login-logo {
        font-size: 46px;
        margin-bottom: 10px;
    }
    .login-title {
        font-size: 30px;
        font-weight: 800;
        color: #ffffff;
        margin-bottom: 6px;
    }
    .login-subtitle {
        color: #94a3b8;
        font-size: 15px;
        margin-bottom: 24px;
    }
    .login-footer {
        margin-top: 24px;
        color: #64748b;
        font-size: 13px;
    }
    .login-version {
        margin-top: 8px;
        color: #94a3b8;
        font-size: 12px;
    }
    div[data-testid="stTextInput"] label {
        color: #cbd5e1 !important;
        font-weight: 600 !important;
    }
    div[data-testid="stTextInput"] input {
        background-color: #0f172a !important;
        color: white !important;
        border-radius: 12px !important;
        border: 1px solid #334155 !important;
    }
    div.stButton > button {
        width: 100%;
        height: 48px;
        border-radius: 14px;
        font-weight: 800;
        background: linear-gradient(90deg, #ef4444, #f97316);
        color: white;
        border: none;
        margin-top: 10px;
    }
    </style>
    """, unsafe_allow_html=True)
    st.markdown(
        """
        <div style="text-align:center; margin-top:20px;">
            <div style="font-size:48px;">₿</div>
            <h1 style="color:white; margin-bottom:0;">BTC Dashboard Pro</h1>
            <p style="color:#94a3b8;">Acceso exclusivo al panel operativo</p>
        </div>
        """,
        unsafe_allow_html=True
    )
    col1, col2, col3 = st.columns([1, 1.15, 1])
    with col2:
        clave = st.text_input(
            "Clave de acceso",
            type="password",
            key="access_key_input"
        )
        if st.button("🚀 Ingresar", key="login_btn"):
            if clave == ACCESS_KEY:
                st.session_state.auth = True
                st.rerun()
            else:
                st.error("Clave incorrecta.")
        st.markdown("""
        
    return False