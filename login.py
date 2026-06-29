import streamlit as st

from config import ACCESS_KEY

def check_access():

    if "auth" not in st.session_state:

        st.session_state.auth = False

    if st.session_state.auth:

        return True

    st.markdown("""

<style>

[data-testid="stSidebar"] {display:none;}

.stApp {

    background: radial-gradient(circle at top, #1e293b 0%, #020617 65%);

}

.login-box {

    max-width: 440px;

    margin: 12vh auto 25px auto;

    padding: 38px;

    border-radius: 24px;

    background: rgba(15, 23, 42, 0.92);

    border: 1px solid rgba(255,255,255,0.12);

    box-shadow: 0 30px 90px rgba(0,0,0,0.45);

    text-align: center;

}

.login-logo {

    font-size: 52px;

    color: #f97316;

    font-weight: 900;

}

.login-title {

    color: white;

    font-size: 30px;

    font-weight: 900;

}

.login-subtitle {

    color: #94a3b8;

    margin-top: 8px;

    font-size: 15px;

}

.footer-login {

    text-align:center;

    color:#94a3b8;

    font-size:13px;

    margin-top:25px;

}

div.stButton > button {

    width: 100%;

    height: 48px;

    border-radius: 14px;

    font-weight: 800;

    background: linear-gradient(90deg, #ef4444, #f97316);

    color: white;

    border: none;

}

</style>

""", unsafe_allow_html=True)

    st.markdown(

        "<div style='text-align:center; padding:35px;'>"
    
        "<div style='font-size:52px; color:#f97316; font-weight:900;'>₿</div>"
    
        "<div style='font-size:30px; color:white; font-weight:900;'>BTC Dashboard Pro</div>"
    
        "<div style='font-size:15px; color:#94a3b8; margin-top:8px;'>Acceso exclusivo al panel operativo</div>"
    
        "</div>",
    
        unsafe_allow_html=True
    
    )

    c1, c2, c3 = st.columns([1, 1.2, 1])

    with c2:

        clave = st.text_input("Clave de acceso", type="password", key="access_key_input")

        if st.button("🚀 Ingresar", key="login_btn"):

            if clave == ACCESS_KEY:

                st.session_state.auth = True

                st.rerun()

            else:

                st.error("Clave incorrecta.")



st.markdown(

    "<div style='text-align:center; color:#94a3b8; font-size:13px; margin-top:25px;'>"

    "Powered by Ramigyt<br>v2.0 Pro"

    "</div>",

    unsafe_allow_html=True

)

    return False
