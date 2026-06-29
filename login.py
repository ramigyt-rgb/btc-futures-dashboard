import streamlit as st

from config import ACCESS_KEY

def check_access():

    if "auth" not in st.session_state:

        st.session_state.auth = False

    if st.session_state.auth:

        return True

    st.markdown(

        "<style>"

        "[data-testid='stSidebar']{display:none;}"

        ".stApp{background:radial-gradient(circle at top,#1e293b 0%,#020617 65%);}"

        ".block-container{padding-top:0rem;}"

        "div.stButton > button{width:100%;height:48px;border-radius:14px;font-weight:800;"

        "background:linear-gradient(90deg,#ef4444,#f97316);color:white;border:none;}"

        "div[data-testid='stTextInput'] label{color:#cbd5e1;font-weight:600;}"

        "</style>",

        unsafe_allow_html=True

    )

    c1, c2, c3 = st.columns([1, 1.15, 1])

    with c2:

        st.markdown(

            "<div style='margin-top:12vh;padding:38px;border-radius:24px;"

            "background:rgba(15,23,42,0.92);border:1px solid rgba(255,255,255,0.12);"

            "box-shadow:0 30px 90px rgba(0,0,0,0.45);text-align:center;'>"

            "<div style='font-size:52px;color:#f97316;font-weight:900;'>₿</div>"

            "<div style='color:white;font-size:30px;font-weight:900;'>BTC Dashboard Pro</div>"

            "<div style='color:#94a3b8;font-size:15px;margin-top:8px;'>Acceso exclusivo al panel operativo</div>"

            "</div>",

            unsafe_allow_html=True

        )

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

        st.markdown(

            "<div style='text-align:center;color:#94a3b8;font-size:13px;margin-top:28px;'>"

            "Powered by Ramigyt<br>v2.0 Pro"

            "</div>",

            unsafe_allow_html=True

        )

    return False
