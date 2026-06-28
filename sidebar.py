# =========================
# SIDEBAR / ACCESO
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
def render_sidebar():    
    estrategia = st.sidebar.selectbox("Estrategia", STRATEGIES, key="estrategia_select")
    account_usd = st.sidebar.number_input("Cuenta USDT", min_value=10.0, value=500.0, step=10.0, key="account_usd_input")
    risk_pct_input = st.sidebar.number_input("Riesgo por operación %", min_value=0.1, max_value=5.0, value=1.0, step=0.1, key="risk_pct_input")
    risk_pct = risk_pct_input / 100
    leverage = st.sidebar.selectbox("Apalancamiento sugerido", [1, 2, 3, 5, 10, 20, 50, 75, 100, 125, 150], index=3, key="leverage_select")
    min_score = st.sidebar.slider("Score mínimo para operar", 1, 10, 7, key="min_score_slider")
    rr_target = st.sidebar.number_input("Riesgo/Beneficio objetivo", min_value=1.0, max_value=10.0, value=2.0, step=0.1, key="rr_target_input")
    min_rr = st.sidebar.number_input("RR mínimo aceptado", min_value=1.0, max_value=10.0, value=1.8, step=0.1, key="min_rr_input")
    max_atr_multiplier = st.sidebar.number_input("Máximo SL permitido en ATR", min_value=0.5, max_value=5.0, value=2.0, step=0.1, key="max_atr_input")
    show_levels_when_no_trade = st.sidebar.checkbox("Mostrar SL/TP aunque sea NO OPERAR", value=True, key="show_levels_chk")

    modo_operativo = st.sidebar.selectbox("Modo de operación", ["Conservador", "Normal", "Agresivo", "Scalping agresivo", "Scalp 15M"], index=1, key="modo_operativo_select")
    if modo_operativo == "Conservador":
        rr_target, max_atr_multiplier, min_score = 2.0, 2.0, 8
    elif modo_operativo == "Normal":
        rr_target, max_atr_multiplier, min_score = 2.0, 2.5, 7
    elif modo_operativo == "Agresivo":
        rr_target, max_atr_multiplier, min_score = 1.5, 1.8, 6
    elif modo_operativo == "Scalping agresivo":
        rr_target, max_atr_multiplier, min_score = 1.2, 1.2, 5
    elif modo_operativo == "Scalp 15M":
        rr_target = 1.2
        min_rr = 1.2
        max_atr_multiplier = 1.0
        min_score = 6
    filter_hours = st.sidebar.checkbox("Filtrar horarios", value=False)
    avoid_weekends = st.sidebar.checkbox("Evitar fines de semana", value=True)

    st.sidebar.divider()
    st.sidebar.subheader("FVG profesional")
    use_fvg_filter = st.sidebar.checkbox("Usar filtro FVG en validación", value=False, key="use_fvg_filter_chk")
    show_fvg_zones = st.sidebar.checkbox("Mostrar zonas FVG", value=True, key="show_fvg_zones_chk")
    show_mitigated_fvg = st.sidebar.checkbox("Mostrar FVG mitigados", value=True, key="show_mitigated_fvg_chk")
    fvg_min_atr = st.sidebar.number_input("FVG mínimo en ATR", min_value=0.05, max_value=2.0, value=0.20, step=0.05, key="fvg_min_atr_input")
    fvg_max_distance_atr = st.sidebar.number_input("Distancia máx. al FVG en ATR", min_value=0.1, max_value=5.0, value=1.50, step=0.1, key="fvg_max_distance_atr_input")

    st.sidebar.divider()
    st.sidebar.subheader("Backtesting")
    backtest_period = st.sidebar.selectbox("Período", ["3 meses", "6 meses", "1 año"], index=0, key="bt_period_select")
    backtest_tf = st.sidebar.selectbox("Timeframe backtest", ["15m", "5m"], index=0, key="bt_tf_select")
    filter_hours = st.sidebar.checkbox("Filtro horario: Londres / Londres + NY", value=True, key="filter_hours_chk")
    avoid_weekends = st.sidebar.checkbox("Evitar fines de semana", value=True, key="avoid_weekends_chk")
    validate_after_hours = st.sidebar.number_input("Validar señales después de horas", min_value=1, max_value=72, value=24, step=1, key="validate_hours_input")

    st.sidebar.divider()
    st.sidebar.subheader("Monte Carlo / Drawdown")
    mc_enabled = st.sidebar.checkbox("Mostrar módulo Monte Carlo", value=True, key="mc_enabled_chk")
    mc_trades_horizon = st.sidebar.number_input("Horizonte simulación: trades", min_value=5, max_value=300, value=50, step=5, key="mc_horizon_input")
    mc_paths = st.sidebar.number_input("Escenarios simulados", min_value=500, max_value=20000, value=5000, step=500, key="mc_paths_input")
    mc_start_capital = st.sidebar.number_input("Capital simulado USDT", min_value=10.0, value=float(account_usd), step=10.0, key="mc_start_cap_input")
    mc_max_daily_trades = st.sidebar.number_input("Máx. trades por día", min_value=1, max_value=20, value=3, step=1, key="mc_max_trades_day_input")
    mc_use_backtest = st.sidebar.checkbox("Usar resultados del backtest para Monte Carlo", value=True, key="mc_use_bt_chk")
    mc_manual_wr = st.sidebar.number_input("Winrate manual %", min_value=1.0, max_value=99.0, value=45.0, step=1.0, key="mc_manual_wr_input")
    mc_manual_rr = st.sidebar.number_input("RR ganador manual", min_value=0.5, max_value=10.0, value=float(rr_target), step=0.1, key="mc_manual_rr_input")
    mc_ruin_dd_pct = st.sidebar.number_input("Umbral de ruina / alerta DD %", min_value=5.0, max_value=100.0, value=30.0, step=5.0, key="mc_ruin_dd_input")

    st.sidebar.divider()
    st.sidebar.subheader("Producto Pro")
    auto_capture_enabled = st.sidebar.checkbox("Captura automática de señales válidas", value=True, key="auto_capture_chk")
    mobile_compact = st.sidebar.checkbox("Modo móvil compacto", value=False, key="mobile_compact_chk")
    auto_refresh_enabled = st.sidebar.checkbox("Auto actualizar para alertas", value=False, key="auto_refresh_chk")
    auto_refresh_seconds = st.sidebar.number_input("Actualizar cada segundos", min_value=60, max_value=900, value=120, step=30, key="auto_refresh_seconds_input")

    with st.sidebar.expander("🔔 Alertas estratégicas", expanded=False):
        st.caption("Usa Secrets de Streamlit. Opcionalmente podés sobrescribir token/chat_id acá.")
        telegram_enabled = st.checkbox("Activar Telegram", value=True, key="telegram_enabled_chk")
        telegram_bot_token = st.text_input("Telegram bot token opcional", value="", type="password", key="telegram_token_input")
        telegram_chat_id = st.text_input("Telegram chat ID opcional", value="", key="telegram_chat_id_input")
        discord_enabled = st.checkbox("Activar Discord", value=False, key="discord_enabled_chk")
        discord_webhook_url = st.text_input("Discord webhook URL", value="", type="password", key="discord_webhook_input")
        alert_valid_signals = st.checkbox("Avisar señales válidas", value=True, key="alert_valid_chk")
        alert_almost_setups = st.checkbox("Avisar setups en formación", value=True, key="alert_almost_chk")
        alert_bias_change = st.checkbox("Avisar cambio fuerte de sesgo", value=True, key="alert_bias_chk")
        alert_risk_warning = st.checkbox("Avisar TP/SL demasiado exigente", value=False, key="alert_risk_chk")
        almost_score_gap = st.slider("Setup en formación: a cuántos puntos del score", 1, 3, 1, key="almost_gap_slider")
        alert_market_updates = st.checkbox("Enviar resumen de mercado automático", value=True, key="alert_market_updates_chk")
        market_update_minutes = st.number_input("Cada cuántos minutos", min_value=5, max_value=60, value=5, step=5, key="market_update_minutes_input")
        if st.button("📲 Probar Telegram", key="test_telegram_btn"):
            ok, resp = send_telegram_message(
                "🚀 BTC Dashboard Pro conectado correctamente.",
                telegram_bot_token,
                telegram_chat_id
            )
            if ok:
                st.success("Mensaje enviado correctamente.")
            else:
                st.error("No se pudo enviar el mensaje de prueba.")
                st.caption(str(resp)[:300])
    st.sidebar.divider()
    if st.sidebar.button("🔄 Actualizar datos", key="refresh_btn"):
        st.rerun()

    if auto_refresh_enabled:
        components.html(f"""
            <script>
            setTimeout(function() {{window.parent.location.reload();}}, {int(auto_refresh_seconds) * 1000});
            </script>
            """, height=0)
    return {

        "estrategia": estrategia,

        "account_usd": account_usd,

        "risk_pct": risk_pct,

        "leverage": leverage,

        "min_score": min_score,

        "rr_target": rr_target,

        "min_rr": min_rr,

        "max_atr_multiplier": max_atr_multiplier,

    }