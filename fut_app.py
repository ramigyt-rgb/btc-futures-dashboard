# fut_app.py

# Ejecutar: py -m streamlit run fut_app.py



import os

from datetime import datetime

import numpy as np

import pandas as pd

import plotly.graph_objects as go

import streamlit as st

import streamlit.components.v1 as components

from fut_core import *



st.set_page_config(

    page_title="BTCUSDT Futures Dashboard Pro",

    layout="wide",

    initial_sidebar_state="expanded"

)



st.markdown("""

<style>

div[data-testid="stMetricValue"]{font-size:1.5rem!important}

.block-container{padding-top:2rem}

@media(max-width:768px){

div[data-testid="stMetricValue"]{font-size:1.05rem!important}

h1{font-size:1.7rem!important}

h2{font-size:1.35rem!important}

}

</style>

""", unsafe_allow_html=True)





def get_msgs_safe(a, row, config):

    msgs = a.get("msgs", {})

    if not isinstance(msgs, dict):

        msgs = {}



    decision = row.get("decision", "NO_OPERAR")

    symbol = SYMBOL

    estrategia = row.get("estrategia", config.get("estrategia", "FVG + Tendencia"))

    price = row.get("precio", np.nan)

    sl = row.get("sl", np.nan)

    tp = row.get("tp", np.nan)

    rr = row.get("rr_real", np.nan)

    quality_label = row.get("calidad_setup", "—")

    quality_score = row.get("calidad_score", 0)

    long_score = row.get("long_score", 0)

    short_score = row.get("short_score", 0)

    rsi = row.get("rsi_15m", np.nan)

    atr = row.get("atr_15m", np.nan)

    vela = row.get("vela_5m", "—")

    fvg_label = row.get("fvg_estado", "SIN_FVG")

    direction = row.get("direccion_calculada", "—")

    motivos = str(row.get("motivos_bloqueo", "")).split(" | ") if row.get("motivos_bloqueo", "") else []



    if "valid" not in msgs:

        msgs["valid"] = build_valid_signal_msg(

            decision, symbol, estrategia, price, sl, tp, rr,

            quality_label, quality_score, long_score, short_score,

            rsi, atr, vela, fvg_label

        )



    if "almost" not in msgs:

        msgs["almost"] = build_almost_msg(

            direction, symbol, estrategia,

            direction_score(direction, long_score, short_score),

            config.get("min_score", 7),

            price, sl, tp, rr, long_score, short_score,

            rsi, motivos, vela, fvg_label

        )



    if "bias" not in msgs:

        msgs["bias"] = build_bias_msg(

            symbol,

            row.get("market_bias", "NEUTRAL"),

            row.get("escenario", "SIN DATOS"),

            row.get("4h", "—"),

            row.get("1h", "—"),

            row.get("15m", "—"),

            row.get("5m", "—"),

            row.get("estructura", "—"),

            price,

            rsi,

            vela

        )



    if "risk" not in msgs:

        msgs["risk"] = build_risk_msg(

            symbol,

            direction,

            price,

            sl,

            tp,

            row.get("distancia_sl_pts", np.nan),

            row.get("tp_atr_multiple", np.nan),

            rr,

            vela

        )



    return msgs





st.sidebar.title("Configuración")

st.sidebar.subheader("🔐 Acceso")



if "auth" not in st.session_state:

    st.session_state.auth = False



try:

    if st.query_params.get("auth") == "1":

        st.session_state.auth = True

except Exception:

    pass



if not st.session_state.auth:

    clave = st.sidebar.text_input("Clave de acceso", type="password", key="access_key_input")

    if not clave:

        st.warning("Ingrese la clave de acceso para abrir el dashboard.")

        st.stop()

    if clave != ACCESS_KEY:

        st.error("Clave incorrecta.")

        st.stop()

    st.session_state.auth = True

    try:

        st.query_params["auth"] = "1"

    except Exception:

        pass

    st.rerun()

else:

    st.sidebar.success("Acceso habilitado")

    if st.sidebar.button("Cerrar acceso", key="logout_access_btn"):

        st.session_state.auth = False

        try:

            st.query_params.clear()

        except Exception:

            pass

        st.rerun()



with st.sidebar.expander("🔐 Login de usuarios", expanded=False):

    st.caption("Login simple local. Usuario demo: demo / demo")

    use_login = st.checkbox("Activar login", value=False, key="use_login_chk")

    usuario_login = st.text_input("Usuario", value="demo", key="user_login_input")

    password_login = st.text_input("Contraseña", value="demo", type="password", key="password_login_input")

    if use_login:

        if check_login(usuario_login, password_login):

            st.success(f"Usuario activo: {usuario_login}")

        else:

            st.error("Usuario o contraseña incorrectos.")

            st.stop()



estrategia = st.sidebar.selectbox("Estrategia", STRATEGIES, index=5, key="estrategia_select")

account_usd = st.sidebar.number_input("Cuenta USDT", min_value=10.0, value=500.0, step=10.0, key="account_usd_input")

risk_pct_input = st.sidebar.number_input("Riesgo por operación %", min_value=0.1, max_value=5.0, value=1.0, step=0.1, key="risk_pct_input")

leverage = st.sidebar.selectbox("Apalancamiento sugerido", [1, 2, 3, 5, 10, 20], index=3, key="leverage_select")

min_score = st.sidebar.slider("Score mínimo para operar", 1, 10, 7, key="min_score_slider")

rr_target = st.sidebar.number_input("Riesgo/Beneficio objetivo", min_value=1.0, max_value=10.0, value=2.0, step=0.1, key="rr_target_input")

min_rr = st.sidebar.number_input("RR mínimo aceptado", min_value=1.0, max_value=10.0, value=1.8, step=0.1, key="min_rr_input")

max_atr_multiplier = st.sidebar.number_input("Máximo SL permitido en ATR", min_value=0.5, max_value=5.0, value=2.0, step=0.1, key="max_atr_input")

show_levels_when_no_trade = st.sidebar.checkbox("Mostrar SL/TP aunque sea NO OPERAR", value=True, key="show_levels_chk")



st.sidebar.divider()

st.sidebar.subheader("FVG profesional")

use_fvg_filter = st.sidebar.checkbox("Usar filtro FVG en validación", value=False, key="use_fvg_filter_chk")

show_fvg_zones = st.sidebar.checkbox("Mostrar zonas FVG", value=True, key="show_fvg_zones_chk")

fvg_min_atr = st.sidebar.number_input("FVG mínimo en ATR", min_value=0.05, max_value=2.0, value=0.20, step=0.05, key="fvg_min_atr_input")

fvg_max_distance_atr = st.sidebar.number_input("Distancia máx. al FVG en ATR", min_value=0.1, max_value=5.0, value=1.50, step=0.1, key="fvg_max_distance_atr_input")



st.sidebar.divider()

st.sidebar.subheader("Filtros")

filter_hours = st.sidebar.checkbox("Filtro horario: Londres / Londres + NY", value=True, key="filter_hours_chk")

avoid_weekends = st.sidebar.checkbox("Evitar fines de semana", value=True, key="avoid_weekends_chk")

validate_after_hours = st.sidebar.number_input("Validar señales después de horas", min_value=1, max_value=72, value=24, step=1, key="validate_hours_input")



st.sidebar.divider()

st.sidebar.subheader("Producto Pro")

auto_capture_enabled = st.sidebar.checkbox("Captura automática de señales válidas", value=True, key="auto_capture_chk")

mobile_compact = st.sidebar.checkbox("Modo móvil compacto", value=False, key="mobile_compact_chk")

auto_refresh_enabled = st.sidebar.checkbox("Auto actualizar para alertas", value=False, key="auto_refresh_chk")

auto_refresh_seconds = st.sidebar.number_input("Actualizar cada segundos", min_value=60, max_value=900, value=120, step=30, key="auto_refresh_seconds_input")



with st.sidebar.expander("🔔 Alertas estratégicas", expanded=False):

    st.caption("El worker usa variables de entorno/Secrets. Acá probás Telegram desde dashboard.")

    telegram_enabled = st.checkbox("Activar Telegram", value=True, key="telegram_enabled_chk")

    telegram_bot_token = st.text_input("Telegram bot token opcional", value="", type="password", key="telegram_token_input")

    telegram_chat_id = st.text_input("Telegram chat ID opcional", value="", key="telegram_chat_id_input")

    alert_valid_signals = st.checkbox("Avisar señales válidas", value=True, key="alert_valid_chk")

    alert_almost_setups = st.checkbox("Avisar setups en formación", value=True, key="alert_almost_chk")

    alert_bias_change = st.checkbox("Avisar cambio fuerte de sesgo", value=True, key="alert_bias_chk")

    alert_risk_warning = st.checkbox("Avisar TP/SL demasiado exigente", value=False, key="alert_risk_chk")

    almost_score_gap = st.slider("Setup en formación: a cuántos puntos del score", 1, 3, 1, key="almost_gap_slider")



    if st.button("📲 Probar Telegram", key="test_telegram_btn"):

        ok, resp = send_telegram_message("🚀 BTC Dashboard Pro conectado correctamente.", telegram_bot_token, telegram_chat_id)

        st.success("Mensaje enviado.") if ok else st.error(resp)



st.sidebar.divider()

if st.sidebar.button("🔄 Actualizar datos", key="refresh_btn"):

    st.rerun()



if auto_refresh_enabled:

    components.html(

        f"<script>setTimeout(function(){{window.parent.location.reload();}}, {int(auto_refresh_seconds) * 1000});</script>",

        height=0

    )



st.title("BTC/USDT FUTUROS DASHBOARD PRO")

st.caption("Dashboard visual + worker 24/7 separado. No es consejo financiero.")



config = {

    "estrategia": estrategia,

    "account_usd": account_usd,

    "risk_pct_input": risk_pct_input,

    "leverage": leverage,

    "min_score": min_score,

    "rr_target": rr_target,

    "min_rr": min_rr,

    "max_atr_multiplier": max_atr_multiplier,

    "filter_hours": filter_hours,

    "avoid_weekends": avoid_weekends,

    "fvg_min_atr": fvg_min_atr,

    "fvg_max_distance_atr": fvg_max_distance_atr,

    "use_fvg_filter": use_fvg_filter

}



try:

    a = analyze_market(config)



    row = a.get("row", {})

    msgs = get_msgs_safe(a, row, config)

    fvg_df = a.get("fvg_df", pd.DataFrame())

    levels = a.get("levels", {})

    dfs = a.get("dfs", (pd.DataFrame(), pd.DataFrame(), pd.DataFrame(), pd.DataFrame(), pd.DataFrame()))

    df_1d, df_4h, df_1h, df_15m, df_5m = dfs



    trade_valid = a.get("trade_valid", row.get("decision") in ["LONG", "SHORT"])

    motivos_bloqueo = a.get("motivos", [])

    if not motivos_bloqueo and row.get("motivos_bloqueo"):

        motivos_bloqueo = str(row.get("motivos_bloqueo")).split(" | ")



    price = row.get("precio", np.nan)

    candidate_direction = row.get("direccion_calculada", "NEUTRAL")

    decision = row.get("decision", "NO_OPERAR")

    sl_calc = row.get("sl", np.nan)

    tp_calc = row.get("tp", np.nan)

    risk_points_calc = row.get("distancia_sl_pts", np.nan)

    tp_distance_calc = row.get("distancia_tp_pts", np.nan)

    tp_atr_multiple = row.get("tp_atr_multiple", np.nan)

    rr_real = row.get("rr_real", np.nan)

    long_score = row.get("long_score", 0)

    short_score = row.get("short_score", 0)

    rsi_15 = row.get("rsi_15m", np.nan)

    atr_15m = row.get("atr_15m", np.nan)

    fvg_label = row.get("fvg_estado", "SIN_FVG")

    quality_label = row.get("calidad_setup", "—")

    quality_score = row.get("calidad_score", 0)

    current_candle_time = row.get("vela_5m", datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S"))

    raw_direction_score = direction_score(candidate_direction, long_score, short_score)



    row["signal_key"] = signal_key(row)



    auto_saved_now = False

    alert_events = []



    if auto_capture_enabled and trade_valid:

        auto_saved_now = save_rows(AUTO_SIGNALS_FILE, [row], key_col="signal_key") > 0



    if alert_valid_signals and trade_valid:

        ok, resp = send_alert_once(f"VALID_{row['signal_key']}", "señal_valida", msgs["valid"], telegram_enabled, telegram_bot_token, telegram_chat_id)

        if ok:

            alert_events.append("🚨 Señal válida enviada por alerta.")



    almost_condition = (

        alert_almost_setups

        and not trade_valid

        and candidate_direction in ["LONG", "SHORT"]

        and raw_direction_score >= max(1, min_score - almost_score_gap)

        and long_score != short_score

        and not pd.isna(rr_real)

        and rr_real >= min_rr

        and not pd.isna(risk_points_calc)

        and not pd.isna(atr_15m)

        and risk_points_calc <= atr_15m * max_atr_multiplier

    )



    if almost_condition:

        ok, resp = send_alert_once(

            f"ALMOST_{current_candle_time}_{estrategia}_{candidate_direction}_{raw_direction_score}_{min_score}_{fvg_label}",

            "setup_en_formacion",

            msgs["almost"],

            telegram_enabled,

            telegram_bot_token,

            telegram_chat_id

        )

        if ok:

            alert_events.append("⚠️ Setup en formación enviado.")



    previous_state_key = load_market_state()

    current_state_key = a.get("market_state_key", f"{row.get('escenario','')}_{candidate_direction}_{fvg_label}")



    if alert_bias_change and previous_state_key and previous_state_key != current_state_key:

        ok, resp = send_alert_once(

            f"BIAS_{current_candle_time}_{current_state_key}",

            "cambio_sesgo",

            msgs["bias"],

            telegram_enabled,

            telegram_bot_token,

            telegram_chat_id

        )

        if ok:

            alert_events.append("🔄 Cambio de sesgo enviado.")



    if previous_state_key != current_state_key:

        save_market_state(current_state_key)



    risk_warning_condition = (

        alert_risk_warning

        and candidate_direction in ["LONG", "SHORT"]

        and not pd.isna(tp_atr_multiple)

        and tp_atr_multiple >= 4

        and not pd.isna(risk_points_calc)

        and not pd.isna(atr_15m)

        and risk_points_calc >= atr_15m * max_atr_multiplier

    )



    if risk_warning_condition:

        ok, resp = send_alert_once(

            f"RISK_{current_candle_time}_{estrategia}_{candidate_direction}_{round(float(tp_atr_multiple), 1)}",

            "riesgo_objetivo_exigente",

            msgs["risk"],

            telegram_enabled,

            telegram_bot_token,

            telegram_chat_id

        )

        if ok:

            alert_events.append("⚠️ Alerta de riesgo enviada.")



    if decision == "LONG":

        st.success("🟢 LONG PERMITIDO")

    elif decision == "SHORT":

        st.error("🔴 SHORT PERMITIDO")

    else:

        st.warning(f"⚪ NO OPERAR | Escenario calculado: {candidate_direction}")



    if auto_saved_now:

        st.info("📡 Señal válida capturada automáticamente.")



    if row.get("notional_capado", False):

        st.warning(f"⚠️ Notional limitado: máximo {fmt0(row.get('notional_max', np.nan))} USDT. Riesgo real: {format_number(row.get('riesgo_usdt_real', np.nan), 2)} USDT.")



    for event in alert_events:

        st.info(event)



    st.markdown(f"## Calidad del setup: {quality_label} · {quality_score}/10")

    st.divider()



    q1, q2, q3, q4, q5 = st.columns(5)

    q1.metric("Calidad", quality_label, f"{quality_score}/10")

    q2.metric("Distancia SL", f"{risk_points_calc:,.0f} pts" if not pd.isna(risk_points_calc) else "—", f"ATR: {atr_15m:,.0f}" if not pd.isna(atr_15m) else "—")

    q3.metric("Setup calculado", candidate_direction, f"RR: {rr_real:.2f}" if not pd.isna(rr_real) else "—")

    q4.metric("Distancia TP", f"{tp_distance_calc:,.0f} pts" if not pd.isna(tp_distance_calc) else "—", f"{tp_atr_multiple:.2f} ATR" if not pd.isna(tp_atr_multiple) else "—")

    q5.metric("FVG", str(fvg_label).replace("_", " "), f"{format_number(row.get('fvg_dist_atr', np.nan), 2)} ATR" if not pd.isna(row.get("fvg_dist_atr", np.nan)) else "—")



    with st.expander("📌 Motivo de la decisión", expanded=not mobile_compact):

        for k in ["estrategia", "escenario", "direccion_calculada", "estructura", "fvg_estado"]:

            st.write(f"**{k}:** {row.get(k, '—')}")

        st.write(f"**Long Score:** {long_score}/10")

        st.write(f"**Short Score:** {short_score}/10")

        st.write(f"**RR real:** {format_number(rr_real, 2)}")

        st.write(f"**ATR 15M:** {format_number(atr_15m, 2)} puntos")



        if trade_valid:

            st.success(f"Setup válido para estrategia: {estrategia}.")

        else:

            for motivo in motivos_bloqueo:

                if motivo:

                    st.warning(motivo)



    col1, col2, col3, col4 = st.columns(4)

    col1.metric("Precio BTCUSDT", format_number(price, 2))

    col2.metric("Long Score", f"{long_score}/10")

    col3.metric("Short Score", f"{short_score}/10")

    col4.metric("RSI 15M", f"{rsi_15:.2f}" if not pd.isna(rsi_15) else "—", rsi_state(rsi_15))

    st.divider()



    c1, c2, c3, c4, c5 = st.columns(5)

    c1.metric("24H", trend_icon(row.get("24h", "NEUTRAL")))

    c2.metric("4H", trend_icon(row.get("4h", "NEUTRAL")))

    c3.metric("1H", trend_icon(row.get("1h", "NEUTRAL")))

    c4.metric("15M", trend_icon(row.get("15m", "NEUTRAL")))

    c5.metric("5M", trend_icon(row.get("5m", "NEUTRAL")))

    st.divider()



    btc_size, notional_tmp, risk_tmp, margin_tmp, *_ = position_size(price, sl_calc, account_usd, risk_pct_input / 100, leverage)



    g1, g2, g3, g4, g5, g6, g7 = st.columns(7)

    g1.metric("Cuenta", f"{account_usd:.0f} USDT")

    g2.metric("Riesgo real", f"{row.get('riesgo_usdt_real', 0):.1f} USDT", f"Obj: {row.get('riesgo_usdt_objetivo', 0):.2f}")

    g3.metric("Ganancia TP", f"+{row.get('ganancia_tp_usdt', 0):.1f} USDT")

    g4.metric("Tamaño", f"{btc_size:.4f} BTC")

    g5.metric("Nocional real", f"{row.get('notional_real', 0):.0f} USDT")

    g6.metric("Máx nocional", f"{row.get('notional_max', 0):.0f} USDT")

    g7.metric("Margen", f"{margin_tmp:.0f} USDT")



    r1, r2, r3, r4, r5, r6 = st.columns(6)

    r1.metric("Entrada", f"{price:,.0f}" if not pd.isna(price) else "—")

    r2.metric("SL técnico", f"{sl_calc:,.0f}" if not pd.isna(sl_calc) else "—")

    r3.metric("TP automático", f"{tp_calc:,.0f}" if not pd.isna(tp_calc) else "—")

    r4.metric("Distancia SL", f"{risk_points_calc:,.0f} pts" if not pd.isna(risk_points_calc) else "—")

    r5.metric("Distancia TP", f"{tp_distance_calc:,.0f} pts" if not pd.isna(tp_distance_calc) else "—")

    r6.metric("RR real", f"{rr_real:.0f}" if not pd.isna(rr_real) else "—")

    st.divider()



    st.subheader("🧱 FVG detectados")

    if isinstance(fvg_df, pd.DataFrame) and not fvg_df.empty:

        fvg_show = fvg_df.tail(12).copy()

        fvg_show["time"] = fvg_show["time"].astype(str)

        cols_fvg = [c for c in ["time", "tipo", "direction", "low", "mid", "high", "gap_pts", "gap_atr", "mitigated"] if c in fvg_show.columns]

        st.dataframe(fvg_show[cols_fvg], use_container_width=True)

    else:

        st.info("No hay FVG relevantes en el lookback actual.")



    chart_df = df_15m.tail(100 if mobile_compact else 150).copy()

    fig = go.Figure()



    fig.add_trace(go.Candlestick(

        x=chart_df["time"],

        open=chart_df["open"],

        high=chart_df["high"],

        low=chart_df["low"],

        close=chart_df["close"],

        name="BTCUSDT"

    ))



    fig.add_trace(go.Scatter(x=chart_df["time"], y=chart_df["ema20"], mode="lines", name="EMA 20", line=dict(color="#ff6b57", width=2)))

    fig.add_trace(go.Scatter(x=chart_df["time"], y=chart_df["ema50"], mode="lines", name="EMA 50", line=dict(color="#18c29c", width=2)))

    fig.add_trace(go.Scatter(x=chart_df["time"], y=chart_df["ema200"], mode="lines", name="EMA 200", line=dict(color="#9b5cff", width=2)))



    if show_fvg_zones and isinstance(fvg_df, pd.DataFrame) and not fvg_df.empty:

        x0 = chart_df["time"].iloc[0]

        x1 = chart_df["time"].iloc[-1]

        open_fvgs = fvg_df[~fvg_df["mitigated"].astype(bool)].tail(8) if "mitigated" in fvg_df.columns else fvg_df.tail(8)



        for _, z in open_fvgs.iterrows():

            fill = "rgba(0,180,80,0.14)" if z["direction"] == "LONG" else "rgba(220,0,0,0.12)"

            line = "rgba(0,120,60,0.45)" if z["direction"] == "LONG" else "rgba(180,0,0,0.45)"

            fig.add_shape(

                type="rect",

                xref="x",

                yref="y",

                x0=max(z["time"], x0),

                x1=x1,

                y0=z["low"],

                y1=z["high"],

                fillcolor=fill,

                line=dict(color=line, width=1),

                layer="below"

            )



    for name, value in levels.items():

        if not pd.isna(value):

            fig.add_hline(y=value, line_dash="dot", line_color="gray", annotation_text=name, annotation_position="right")



    if (trade_valid or show_levels_when_no_trade) and not pd.isna(sl_calc):

        fig.add_hline(y=sl_calc, line_color="red", line_width=3, annotation_text="SL")



    if (trade_valid or show_levels_when_no_trade) and not pd.isna(tp_calc):

        fig.add_hline(y=tp_calc, line_color="green", line_width=3, annotation_text="TP")



    if not pd.isna(price):

        fig.add_hline(y=price, line_color="black", line_width=3, annotation_text="Entrada")



    fig.update_layout(

        template="plotly_white",

        height=500 if mobile_compact else 700,

        xaxis_rangeslider_visible=False,

        title="BTCUSDT 15M - EMAs + Liquidez + FVG + SL/TP",

        margin=dict(l=20, r=20, t=50, b=20)

    )



    st.plotly_chart(fig, use_container_width=True)

    st.divider()



    st.subheader("🤖 Estado del worker / recopilación automática")

    snap = safe_read_csv(MARKET_SNAPSHOTS_FILE)



    if snap.empty:

        st.warning("Todavía no hay snapshots del worker. Ejecutá: py worker.py")

    else:

        st.success(f"Worker registró {len(snap)} lecturas. Última: {snap['fecha'].iloc[-1]}")

        st.dataframe(snap.tail(20), use_container_width=True)

        st.download_button("⬇️ Descargar snapshots CSV", data=snap.to_csv(index=False), file_name="market_snapshots.csv", mime="text/csv")



    st.subheader("📊 Historial de señales")

    historial = safe_read_csv(SIGNALS_FILE)

    auto_historial = safe_read_csv(AUTO_SIGNALS_FILE)



    pieces = []

    if not historial.empty:

        pieces.append(historial.assign(origen="manual"))

    if not auto_historial.empty:

        pieces.append(auto_historial.assign(origen="auto_worker"))



    combined_hist = pd.concat(pieces, ignore_index=True) if pieces else pd.DataFrame()



    if not combined_hist.empty:

        show_cols = [

            c for c in [

                "fecha", "vela_5m", "origen", "estrategia", "decision",

                "direccion_calculada", "calidad_score", "entrada", "sl", "tp",

                "resultado", "r_multiple", "rr_real", "fvg_estado",

                "notional_real", "riesgo_usdt_real", "motivos_bloqueo"

            ]

            if c in combined_hist.columns

        ]

        st.dataframe(combined_hist[show_cols].tail(50), use_container_width=True)

        st.download_button("⬇️ Descargar historial completo CSV", data=combined_hist.to_csv(index=False), file_name="signals_log_completo.csv", mime="text/csv")

    else:

        st.info("Todavía no hay señales guardadas.")



    st.subheader("🔔 Historial de alertas")

    alerts_df = safe_read_csv(ALERTS_FILE)



    if not alerts_df.empty:

        st.dataframe(alerts_df.tail(30), use_container_width=True)

        st.download_button("⬇️ Descargar alertas CSV", data=alerts_df.to_csv(index=False), file_name="alerts_sent_log.csv", mime="text/csv")

    else:

        st.info("Todavía no hay alertas enviadas.")



    with st.expander("📘 Cómo activar el worker 24/7"):

        st.code("py worker.py", language="bash")

        st.write("En tu PC funciona mientras la terminal esté abierta. Para 24/7, subí estos archivos a Railway/Render/VPS y definí TELEGRAM_BOT_TOKEN y TELEGRAM_CHAT_ID.")



    st.caption(f"Última actualización local: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")



except Exception as e:

    st.error("Hubo un error cargando el dashboard.")

    st.exception(e)

