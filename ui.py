# =========================
# TARJETA COMERCIAL / RESUMEN EJECUTIVO
# =========================
from analysis import * 
from config import *
from helpers import *
from exchange import load_all_data
from sidebar import (
    estrategia,
    account_usd,
    risk_pct_input,
    risk_pct,
    leverage,
    min_score,
    rr_target,
    min_rr,
    max_atr_multiplier,
    show_levels_when_no_trade,
    modo_operativo,
    filter_hours,
    avoid_weekends,
    use_fvg_filter,
    show_fvg_zones,
    fvg_min_atr,
    fvg_max_distance_atr,
    backtest_period,
    backtest_tf,
    validate_after_hours,
    mc_enabled,
    mc_trades_horizon,
    mc_paths,
    mc_start_capital,
    mc_max_daily_trades,
    mc_use_backtest,
    mc_manual_wr,
    mc_manual_rr,
    mc_ruin_dd_pct,
    auto_capture_enabled,
    mobile_compact,
    telegram_enabled,
    telegram_bot_token,
    telegram_chat_id,
    discord_enabled,
    discord_webhook_url,
    alert_valid_signals,
    alert_almost_setups,
    alert_bias_change,
    alert_risk_warning,
    almost_score_gap,
    alert_market_updates,
    market_update_minutes,
)
from backtest import (
    performance_stats,
    stats_by_strategy,
    last_30_days_stats,
    run_simple_backtest,
    validate_saved_signals,
    monte_carlo_simulation,
    build_r_multiples_from_sources,
    signal_key,
)
from alertas import (
    send_alert_once,
    load_market_state,
    save_market_state,
)
from telegram import (
    build_valid_signal_msg,
    build_almost_msg,
    build_bias_msg,
    build_risk_msg,
    build_market_update_msg,
)
import os
import hashlib
from datetime import datetime
import ccxt
import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st
import streamlit.components.v1 as components

# Compatibilidad UI: variables visuales opcionales que antes vivían en fut_app.py
try:
    mobile_compact
except NameError:
    mobile_compact = False
try:
    show_fvg_zones
except NameError:
    show_fvg_zones = use_fvg_filter if "use_fvg_filter" in globals() else True
try:
    show_fvg_filter
except NameError:
    show_fvg_filter = show_fvg_zones

try:
    import requests
except Exception:
    requests = None


def render_executive_card(
    decision,
    candidate_direction,
    quality_label,
    quality_score,
    price,
    sl_calc,
    tp_calc,
    risk_usd,
    profit_usd,
    rr_real,
    long_score,
    short_score,
    fvg_label,
    trade_valid,
    motivos_bloqueo
):
    if decision == "LONG":
        status_icon = "🟢"
        status_text = "LONG PERMITIDO"
        status_class = "card-long"
    elif decision == "SHORT":
        status_icon = "🔴"
        status_text = "SHORT PERMITIDO"
        status_class = "card-short"
    else:
        status_icon = "⚪"
        status_text = f"NO OPERAR · Escenario {display_direction(candidate_direction)}"
        status_class = "card-neutral"
    confidence_pct = min(max((quality_score / 10) * 100, 0), 100)
    entrada_txt = f"{price:,.0f}" if not pd.isna(price) else "-"
    sl_txt = f"{sl_calc:,.0f}" if not pd.isna(sl_calc) else "-"
    tp_txt = f"{tp_calc:,.0f}" if not pd.isna(tp_calc) else "-"
    rr_txt = f"{rr_real:.2f}" if not pd.isna(rr_real) else "-"
    riesgo_txt = f"{risk_usd:.2f} USDT" if not pd.isna(risk_usd) else "-"
    profit_txt = f"+{profit_usd:.2f} USDT" if not pd.isna(profit_usd) else "-"
    motivos_html = ""
    if decision == "NO_OPERAR" and motivos_bloqueo:
        motivos_html = "<div class='motivos-card'><b>Bloqueos:</b><br>" + "<br>".join(
            [f"• {m}" for m in motivos_bloqueo[:4]]
        ) + "</div>"
    st.markdown(f"""
    <style>
    .executive-card {{
        border-radius: 22px;
        padding: 26px 28px;
        margin: 22px 0 28px 0;
        border: 1px solid rgba(0,0,0,0.08);
        box-shadow: 0 10px 30px rgba(0,0,0,0.06);
        background: linear-gradient(135deg, #ffffff 0%, #f8fafc 100%);
    }}
    .card-long {{ border-left: 10px solid #16a34a; }}
    .card-short {{ border-left: 10px solid #dc2626; }}
    .card-neutral {{ border-left: 10px solid #9ca3af; }}
    .exec-title {{
        font-size: 34px;
        font-weight: 800;
        margin-bottom: 8px;
        color: #1f2937;
    }}
    .exec-subtitle {{
        color: #6b7280;
        font-size: 15px;
        margin-bottom: 20px;
    }}
    .confidence-bar {{
        width: 100%;
        height: 14px;
        background: #e5e7eb;
        border-radius: 999px;
        overflow: hidden;
        margin: 10px 0 22px 0;
    }}
    .confidence-fill {{
        height: 100%;
        width: {confidence_pct}%;
        background: linear-gradient(90deg, #22c55e, #84cc16);
        border-radius: 999px;
    }}
    .exec-grid {{
        display: grid;
        grid-template-columns: repeat(4, 1fr);
        gap: 14px;
        margin-top: 16px;
    }}
    .exec-box {{
        background: white;
        border: 1px solid #eef2f7;
        border-radius: 16px;
        padding: 16px;
    }}
    .exec-label {{
        color: #6b7280;
        font-size: 13px;
        margin-bottom: 5px;
    }}
    .exec-value {{
        color: #111827;
        font-size: 22px;
        font-weight: 800;
    }}
    .motivos-card {{
        background: #fff7ed;
        border: 1px solid #fed7aa;
        color: #9a3412;
        border-radius: 16px;
        padding: 16px;
        margin-top: 18px;
        font-size: 15px;
    }}
    </style>
    <div class="executive-card {status_class}">
        <div class="exec-title">{status_icon} {status_text}</div>
        <div class="exec-subtitle">
            Asistente operativo BTC intradía · decisión, riesgo y niveles principales.
        </div>
        <div><b>Confianza:</b> {quality_score}/10 · {quality_label}</div>
        <div class="confidence-bar">
            <div class="confidence-fill"></div>
        </div>
        <div class="exec-grid">
            <div class="exec-box"><div class="exec-label">Entrada</div><div class="exec-value">{entrada_txt}</div></div>
            <div class="exec-box"><div class="exec-label">Stop Loss</div><div class="exec-value">{sl_txt}</div></div>
            <div class="exec-box"><div class="exec-label">Take Profit</div><div class="exec-value">{tp_txt}</div></div>
            <div class="exec-box"><div class="exec-label">RR real</div><div class="exec-value">{rr_txt}</div></div>
            <div class="exec-box"><div class="exec-label">Riesgo</div><div class="exec-value">{riesgo_txt}</div></div>
            <div class="exec-box"><div class="exec-label">Objetivo</div><div class="exec-value">{profit_txt}</div></div>
            <div class="exec-box"><div class="exec-label">Score LONG / SHORT</div><div class="exec-value">{long_score}/10 · {short_score}/10</div></div>
            <div class="exec-box"><div class="exec-label">FVG</div><div class="exec-value">{fvg_label}</div></div>
        </div>
        {motivos_html}
    </div>
    """, unsafe_allow_html=True)

def render_trading_assistant_card(
    decision,
    candidate_direction,
    quality_score,
    quality_label,
    escenario,
    price,
    rr_real,
    t4,
    t1,
    t15,
    t5,
    structure,
    fvg_label,
    delta_estado,
    delta_fuerza,
    vol_ratio_15m,
    motivos_bloqueo
):
    if candidate_direction == "LONG":
        tendencia_txt = "ALCISTA"
    elif candidate_direction == "SHORT":
        tendencia_txt = "BAJISTA"
    else:
        tendencia_txt = "NEUTRAL"
    if decision == "LONG":
        decision_txt = "🟢 LONG PERMITIDO"
        color = "#16a34a"
    elif decision == "SHORT":
        decision_txt = "🔴 SHORT PERMITIDO"
        color = "#dc2626"
    else:
        decision_txt = "⚪ NO OPERAR"
        color = "#6b7280"
    prob = min(max(int(quality_score * 10), 0), 100)
    if motivos_bloqueo:
        bloqueos_txt = "<br>".join([f"• {m}" for m in motivos_bloqueo[:4]])
    else:
        bloqueos_txt = "Sin bloqueos críticos."
    st.markdown(f"""
    <div style="
        border: 2px solid {color};
        border-radius: 22px;
        padding: 24px;
        margin: 20px 0;
        background: #ffffff;
        box-shadow: 0 8px 24px rgba(0,0,0,0.08);
        font-family: monospace;
    ">
        <div style="font-size:22px; font-weight:800; margin-bottom:12px;">
            ═══════════════════════════════<br>
            ESTADO DEL MERCADO BTC
        </div>
        <div style="font-size:17px; line-height:1.9;">
            Tendencia: <b>{tendencia_txt}</b> ✅<br>
            Contexto: <b>{escenario}</b><br>
            Precio: <b>{price:,.0f}</b><br>
            Estructura 5M: <b>{structure}</b><br>
            4H / 1H / 15M / 5M: <b>{t4}</b> · <b>{t1}</b> · <b>{t15}</b> · <b>{t5}</b><br>
            FVG: <b>{fvg_label}</b><br>
            Delta: <b>{delta_estado}</b> · fuerza <b>{delta_fuerza}</b><br>
            Volumen relativo: <b>{vol_ratio_15m:.2f}x</b><br>
            RR disponible: <b>{rr_real:.2f}</b><br>
            Probabilidad estimada: <b>{prob}%</b><br>
            Calidad: <b>{quality_label}</b> · <b>{quality_score}/10</b>
        </div>
        <hr>
        <div style="font-size:24px; font-weight:900; color:{color};">
            DECISIÓN: {decision_txt}
        </div>
        <div style="margin-top:12px; color:#92400e; font-size:14px;">
            <b>Bloqueos / advertencias:</b><br>
            {bloqueos_txt}
        </div>
        <div style="font-size:22px; font-weight:800; margin-top:16px;">
            ═══════════════════════════════
        </div>
    </div>
    """, unsafe_allow_html=True)

def render_dashboard():
    try:
        df_1d, df_4h, df_1h, df_15m, df_5m = load_all_data()

        levels = liquidity_levels(df_15m)
        ob_df = detect_order_blocks(df_15m, lookback=120, impulse_atr=1.2)
        liq_profile_df = detect_liquidity_profile(df_15m, lookback=120, tolerance_atr=0.18)
        inst_vol_df = detect_institutional_volume(df_15m, lookback=120, vol_mult=1.8, range_mult=1.4)
        volume_profile = volume_profile_pro(df_15m.tail(120), bins=48)
        price = df_5m["close"].iloc[-1]
        current_candle_time = df_5m["time"].iloc[-1].strftime("%Y-%m-%d %H:%M:%S")

        t1d, t4, t1, t15, t5 = trend_state(df_1d), trend_state(df_4h), trend_state(df_1h), trend_state(df_15m), trend_state(df_5m)
        fvg_df = detect_fvg_zones(
            df_15m,
            min_atr_mult=fvg_min_atr,
            lookback=120,
            trend_filter=t15
        )
        rsi_15 = df_15m["rsi"].iloc[-1]
        rsi_label = rsi_state(rsi_15)
        atr_15m = df_15m["atr"].iloc[-1]
        structure = structure_state(df_5m)
        long_score = score_direction("LONG", df_4h, df_1h, df_15m, df_5m, levels, fvg_df, fvg_max_distance_atr)
        short_score = score_direction("SHORT", df_4h, df_1h, df_15m, df_5m, levels, fvg_df, fvg_max_distance_atr)
        escenario, market_bias = detect_market_intention(price, df_4h, df_1h, df_15m, levels)
        candidate_direction = choose_candidate_direction(estrategia, long_score, short_score, t1d, t4, structure, price, df_15m, df_5m, levels, fvg_df)

        fvg_label, fvg_zone, fvg_distance_atr, fvg_valid = fvg_state(price, atr_15m, fvg_df, candidate_direction, fvg_max_distance_atr)
        sl_calc, tp_calc, risk_points_calc = technical_levels(candidate_direction, df_5m, price, rr_target, fvg_zone,modo_operativo)
        tp_distance_calc = abs(tp_calc - price) if not pd.isna(tp_calc) else np.nan
        tp_atr_multiple = tp_distance_calc / atr_15m if not pd.isna(tp_distance_calc) and not pd.isna(atr_15m) and atr_15m > 0 else np.nan
        rr_real = calculate_rr(price, sl_calc, tp_calc, candidate_direction)
        rr_real = calculate_rr(price, sl_calc, tp_calc, candidate_direction)
        if modo_operativo == "Scalp 15M":
            objetivo_exigente = (
                not pd.isna(tp_atr_multiple)
                and tp_atr_multiple > 1.5
            )
            scalping_no_recomendado = (
                not pd.isna(tp_atr_multiple)
                and tp_atr_multiple > 1.2
            )
        else:
            objetivo_exigente = (
                not pd.isna(tp_atr_multiple)
                and tp_atr_multiple >= 4
            )
            scalping_no_recomendado = (
                not pd.isna(tp_atr_multiple)
                and tp_atr_multiple >= 3
            )
        trade_valid, motivos_bloqueo = validate_trade(
                estrategia, candidate_direction, long_score, short_score, min_score, risk_pct, rr_real, min_rr,
                risk_points_calc, atr_15m, market_bias, structure, price, levels, max_atr_multiplier,
                df_15m, df_5m, filter_hours, avoid_weekends,
                fvg_df, use_fvg_filter, fvg_max_distance_atr, df_1h
            )
        decision = candidate_direction if trade_valid else "NO_OPERAR"


        btc_size, notional, risk_usd, margin_needed, risk_usd_target, notional_capped, max_notional = position_size(price, sl_calc, account_usd, risk_pct, leverage)
        profit_usd = risk_usd * rr_target
        profit_pct = (profit_usd / account_usd) * 100 if account_usd else 0
        quality_score, quality_label, quality_detail = evaluar_setup_pro(

            direction=candidate_direction,

            long_score=long_score,

            short_score=short_score,

            rr_real=rr_real,

            risk_points=risk_points_calc,

            atr_15m=atr_15m,

            tp_atr_multiple=tp_atr_multiple,

            fvg_valid=fvg_valid,

            fvg_label=fvg_label,

            t1d=t1d,

            t4=t4,

            t1=t1,

            t15=t15,

            t5=t5,

            structure=structure,

            price=price,

            df_15m=df_15m,

            df_5m=df_5m,

            levels=levels,

            trade_valid=trade_valid,

            motivos_bloqueo=motivos_bloqueo,

            use_time_filter=filter_hours,

            avoid_weekends_filter=avoid_weekends,

        )
        raw_direction_score = (long_score if candidate_direction == "LONG" else short_score)
        tab1, tab2, tab3, tab4, tab5 = st.tabs([
            "🧠 Decisión",
            "📈 Gráfico",
            "🔬 Confluencias",
            "🎯 Trade",
            "📊 Backtest"
        ])

        delta_15m = df_15m["volume_delta"].iloc[-1]
        delta_strength_15m = df_15m["delta_strength"].iloc[-1]
        vol_ratio_15m = df_15m["vol_ratio"].iloc[-1]

        if delta_15m > 0:
            delta_estado = "🟢 Delta comprador"
        elif delta_15m < 0:
            delta_estado = "🔴 Delta vendedor"
        else:
            delta_estado = "⚪ Delta neutro"
        if abs(delta_strength_15m) >= 1.5:
            delta_fuerza = "Fuerte"
        elif abs(delta_strength_15m) >= 0.8:
            delta_fuerza = "Normal"
        else:
            delta_fuerza = "Débil"

        with tab1:
            col1, col2, col3, col4 = st.columns(4)
            col1.metric("Precio BTCUSDT", format_number(price, 2))
            col2.metric("Long Score", f"{long_score}/10")
            col3.metric("Short Score", f"{short_score}/10")
            col4.metric("RSI 15M", f"{rsi_15:.2f}" if not pd.isna(rsi_15) else "—", rsi_label)
            st.divider()

            q1, q2, q3, q4, q5 = st.columns(5)
            q1.metric("Calidad", quality_label, f"{quality_score}/10")
            q2.metric("Distancia SL", f"{risk_points_calc:,.0f} pts" if not pd.isna(risk_points_calc) else "—", f"ATR 15M: {atr_15m:,.0f} pts" if not pd.isna(atr_15m) else "—")
            q3.metric("Setup", display_direction(candidate_direction), f"RR: {rr_real:.2f}" if not pd.isna(rr_real) else "—")
            q4.metric("Distancia TP", f"{tp_distance_calc:,.0f} pts" if not pd.isna(tp_distance_calc) else "—", f"{tp_atr_multiple:.2f} ATR" if not pd.isna(tp_atr_multiple) else "—")
            q5.metric("FVG", fvg_label.replace("_", " "), f"{format_number(fvg_distance_atr, 2)} ATR" if not pd.isna(fvg_distance_atr) else "—")
            st.divider()

            c1, c2, c3, c4, c5 = st.columns(5)
            c1.metric("24H", trend_icon(t1d))
            c2.metric("4H", trend_icon(t4))
            c3.metric("1H", trend_icon(t1))
            c4.metric("15M", trend_icon(t15))
            c5.metric("5M", trend_icon(t5))
            st.divider()

            st.markdown(f"## Calidad del setup: {quality_label} · {quality_score}/10")
            st.divider()
            
            

            render_trading_assistant_card(
            decision=decision,
            candidate_direction=candidate_direction,
            quality_score=quality_score,
            quality_label=quality_label,
            escenario=escenario,
            price=price,
            rr_real=rr_real,
            t4=t4,
            t1=t1,
            t15=t15,
            t5=t5,
            structure=structure,
            fvg_label=fvg_label,
            delta_estado=delta_estado,
            delta_fuerza=delta_strength_15m,
            vol_ratio_15m=vol_ratio_15m,
            motivos_bloqueo=motivos_bloqueo
        )
            
            
        with tab2:
            st.subheader("📈 Gráfico operativo intradía")
            grafico_operativo_slot = st.container()
            chart_df = df_15m.tail(150).copy()
            fig = go.Figure()
            fig.add_trace(go.Candlestick(
                x=chart_df["time"],
                open=chart_df["open"],
                high=chart_df["high"],
                low=chart_df["low"],
                close=chart_df["close"],
                name="BTC/USDT"
            ))
            fig.add_trace(go.Scatter(
                x=chart_df["time"],
                y=chart_df["ema20"],
                mode="lines",
                name="EMA 20"
            ))
            fig.add_trace(go.Scatter(
                x=chart_df["time"],
                y=chart_df["ema50"],
                mode="lines",
                name="EMA 50"
            ))
            fig.add_trace(go.Scatter(
                x=chart_df["time"],
                y=chart_df["ema200"],
                mode="lines",
                name="EMA 200"
            ))

        with tab3:
            st.subheader("📊 Volume Profile PRO")
            if volume_profile:
                vp1, vp2, vp3 = st.columns(3)
                vp1.metric("POC", fmt0(volume_profile["poc"]))
                vp2.metric("VAH", fmt0(volume_profile["vah"]))
                vp3.metric("VAL", fmt0(volume_profile["val"]))
                st.info(
                    f"**Estado:** {volume_profile['estado']}  \n\n"
                    f"**Lectura:** {volume_profile['lectura']}"
                )
                st.write(
                    "**HVN:** "
                    + ", ".join([fmt0(x) for x in volume_profile["hvn"]])
                )
                st.write(
                    "**LVN:** "
                    + ", ".join([fmt0(x) for x in volume_profile["lvn"]])
                )
            else:
                st.warning("No hay datos suficientes para calcular Volume Profile.")
            st.subheader("🎯 Zonas profesionales Daytrade")
            zonas_daytrade = detectar_zonas_daytrade(
                df_15m=df_15m,
                asia_high=None,
                london_high=None,
                max_zonas=3
            )
            st.subheader("🔥 Delta de Volumen PRO")     
            delta_15m = df_15m["volume_delta"].iloc[-1]
            delta_strength_15m = df_15m["delta_strength"].iloc[-1]
            vol_ratio_15m = df_15m["vol_ratio"].iloc[-1]
            if delta_15m > 0:
                delta_estado = "🟢 Delta comprador"
            elif delta_15m < 0:
                delta_estado = "🔴 Delta vendedor"
            else:
                delta_estado = "⚪ Delta neutro"
            if abs(delta_strength_15m) >= 1.5:
                delta_fuerza = "Fuerte"
            elif abs(delta_strength_15m) >= 0.8:
                delta_fuerza = "Normal"
            else:
                delta_fuerza = "Débil"
            d1, d2, d3 = st.columns(3)
            d1.metric("Delta 15M", delta_estado)
            d2.metric("Fuerza Delta", delta_fuerza, f"{delta_strength_15m:.2f}x")
            d3.metric("Volumen relativo", f"{vol_ratio_15m:.2f}x")
            last_15 = df_15m.iloc[-1]
            absorcion_compradora = (
                last_15["close"] < last_15["open"]
                and delta_strength_15m > 1.0
                and vol_ratio_15m > 1.2
            )
            absorcion_vendedora = (
                last_15["close"] > last_15["open"]
                and delta_strength_15m < -1.0
                and vol_ratio_15m > 1.2
            )
            if absorcion_compradora:
                st.success("🟢 Posible absorción compradora: el precio baja, pero aparece presión compradora.")
            elif absorcion_vendedora:
                st.error("🔴 Posible absorción vendedora: el precio sube, pero aparece presión vendedora.")
            else:
                st.info("Sin absorción clara en la última vela 15M.")

            st.subheader("🧱 Order Blocks automáticos")
            if ob_df is not None and not ob_df.empty:
                ob_open = ob_df[~ob_df["mitigated"].astype(bool)].copy()
                if not ob_open.empty:
                    last_obs = ob_open.tail(5).copy()
                    st.dataframe(
                        last_obs[["time", "tipo", "direction", "low", "mid", "high", "mitigated"]],
                        use_container_width=True
                    )
                else:
                    st.info("Hay Order Blocks detectados, pero ya fueron mitigados.")
            else:
                st.info("No hay Order Blocks relevantes en el lookback actual.")
            st.subheader("💧 Perfil de Liquidez PRO")
            if liq_profile_df is not None and not liq_profile_df.empty:
                liq_show = liq_profile_df.head(8).copy()
                liq_show["time"] = liq_show["time"].astype(str)
                st.dataframe(
                    liq_show[
                        ["time", "tipo", "direction", "nivel", "estado", "distancia_pts", "distancia_atr", "motivo"]
                    ],
                    use_container_width=True
                )
            else:
                st.info("No hay Equal Highs / Equal Lows relevantes ahora.")

            st.subheader("🏦 Volumen Institucional PRO")
            if inst_vol_df is not None and not inst_vol_df.empty:
                inst_show = inst_vol_df.tail(8).copy()
                inst_show["time"] = inst_show["time"].astype(str)
                st.dataframe(
                    inst_show[
                        ["time", "tipo", "direction", "precio", "vol_ratio", "range_ratio", "motivo"]
                    ],
                    use_container_width=True
                )
                ultima_inst = inst_vol_df.iloc[-1]
                if ultima_inst["direction"] == "LONG":
                    st.success("🟢 Última vela institucional detectada: alcista.")
                else:
                    st.error("🔴 Última vela institucional detectada: bajista.")
            else:
                st.info("No hay velas institucionales relevantes en el lookback actual.")
        with tab4:
            st.subheader("🎯 Trade en vivo")
            open_trade = get_open_trade()
            with st.expander("➕ Cargar operación abierta", expanded=open_trade is None):
                col_a, col_b, col_c = st.columns(3)
                manual_direction = col_a.selectbox("Dirección", ["LONG", "SHORT"], key="live_direction")
                manual_entry = col_b.number_input("Entrada", value=float(price), step=1.0, key="live_entry")
                manual_size = col_c.number_input("Tamaño BTC", value=0.001, step=0.001, format="%.4f", key="live_size")
                col_d, col_e, col_f = st.columns(3)
                manual_sl = col_d.number_input("SL", value=float(sl_calc) if not pd.isna(sl_calc) else float(price), step=1.0, key="live_sl")
                manual_tp = col_e.number_input("TP", value=float(tp_calc) if not pd.isna(tp_calc) else float(price), step=1.0, key="live_tp")
                manual_lev = col_f.number_input("Leverage", value=float(leverage), step=1.0, key="live_leverage_select")
                if st.button("✅ Abrir trade en vivo"):
                    save_open_trade({
                        "fecha": datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S"),
                        "direction": manual_direction,
                        "entry": manual_entry,
                        "sl": manual_sl,
                        "tp": manual_tp,
                        "size_btc": manual_size,
                        "leverage": manual_lev,
                        "status": "OPEN",
                    })
                    st.success("Trade abierto correctamente.")
                    st.rerun()
            if open_trade:
                pnl, current_r, distance_tp, distance_sl, estado = calc_live_trade(open_trade, price)
                st.markdown(f"### {estado}")
                a, b, c, d, e = st.columns(5)
                a.metric("Dirección", open_trade["direction"])
                b.metric("Entrada", fmt0(open_trade["entry"]))
                c.metric("Precio actual", fmt0(price))
                d.metric("PNL vivo", f"{pnl:+.2f} USDT")
                e.metric("R actual", f"{current_r:+.2f}R")
                f, g, h = st.columns(3)
                f.metric("Falta TP", f"{max(distance_tp, 0):,.0f} pts")
                g.metric("Falta SL", f"{max(distance_sl, 0):,.0f} pts")
                h.metric("Tamaño", f"{float(open_trade['size_btc']):.4f} BTC")
                progress = min(max((current_r + 1) / 3, 0), 1)
                st.progress(progress)
                close_col1, close_col2 = st.columns(2)
                if close_col1.button("🔒 Cerrar trade al precio actual"):
                    closed = open_trade.copy()
                    closed["fecha_cierre"] = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")
                    closed["precio_cierre"] = price
                    closed["pnl_usdt"] = pnl
                    closed["r_resultado"] = current_r
                    closed["resultado"] = "MANUAL"
                    close_open_trade(closed)
                    st.success("Trade cerrado y guardado en historial.")
                    st.rerun()
                if close_col2.button("🗑️ Cancelar trade abierto"):
                    pd.DataFrame(columns=[
                        "fecha", "direction", "entry", "sl", "tp",
                        "size_btc", "leverage", "status"
                    ]).to_csv(OPEN_TRADE_FILE, index=False)
                    st.warning("Trade abierto eliminado.")
                    st.rerun()
            else:
                st.info("No hay operación abierta cargada.")
        with tab5:
            st.subheader("🧪 Backtesting automático")
            with st.spinner("Calculando backtest..."):
                    bt_results, bt_stats = run_simple_backtest(backtest_tf, backtest_period, estrategia, min_score, rr_target, min_rr, max_atr_multiplier, filter_hours, avoid_weekends, fvg_min_atr, fvg_max_distance_atr, use_fvg_filter)
                    b1, b2, b3, b4, b5 = st.columns(5)
                    b1.metric("Operaciones", int(bt_stats.get("operaciones", 0)))
                    b2.metric("Winrate", f"{bt_stats.get('winrate', 0):.1f}%")
                    pf = bt_stats.get("profit_factor", 0)
                    b3.metric("Profit Factor", "∞" if pf == np.inf else f"{pf:.2f}")
                    b4.metric("Drawdown", f"{bt_stats.get('drawdown', 0):.2f}R")
                    b5.metric("Expectativa", f"{bt_stats.get('expectancy', 0):+.2f}R")
                    if not bt_results.empty:
                        equity = bt_results[bt_results["resultado"].isin(["TP", "SL"])].copy()
                        if not equity.empty:
                            equity["equity_r"] = pd.to_numeric(
                                equity["r_multiple"], errors="coerce"
                            ).fillna(0).cumsum()
                            eq_fig = go.Figure()
                            eq_fig.add_trace(
                                go.Scatter(
                                    x=equity["fecha"],
                                    y=equity["equity_r"],
                                    mode="lines+markers",
                                    name="Equity R"
                                )
                            )
                            eq_fig.update_layout(
                                template="plotly_white",
                                height=350,
                                title="Curva de equity del backtest en R"
                            )
                            st.plotly_chart(
                                eq_fig,
                                use_container_width=True,
                                config={"responsive": True},
                                key="equity_backtest"
                            )
                        st.dataframe(bt_results.tail(50), use_container_width=True)
                        st.download_button(
                            "⬇️ Descargar backtest CSV",
                            data=bt_results.to_csv(index=False),
                            file_name="backtest_results.csv",
                            mime="text/csv",
                            key="download_bt"
                        )
                    else:
                        st.info("No hubo operaciones válidas en el período con estos filtros.")

                    st.subheader("🧮 Expectativa matemática")
                    st.write(f"**Win Rate histórico:** {bt_stats.get('winrate', 0):.1f}%")
                    st.write(f"**RR promedio ganador:** {bt_stats.get('rr_promedio', 0):.2f}")
                    st.write(f"**Expectativa:** {bt_stats.get('expectancy', 0):+.2f}R")
                    if bt_stats.get("expectancy", 0) > 0:
                        st.success("Expectativa positiva en este backtest. Hay posible ventaja estadística.")
                    else:
                        st.warning("Expectativa negativa o insuficiente. No hay ventaja demostrada con estos filtros.")
                # acá va TODO el bloque de backtest, Monte Carlo, historial, alertas, FVG detectados, reglas
        current_signal_row = {
            "fecha": datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S"),
            "vela_5m": current_candle_time,
            "estrategia": estrategia,
            "modo_operativo": modo_operativo,
            "decision": decision,
            "direccion_calculada": candidate_direction,
            "calidad_setup": quality_label,
            "calidad_score": quality_score,
            "escenario": escenario,
            "precio": price,
            "long_score": long_score,
            "short_score": short_score,
            "rsi_15m": rsi_15,
            "atr_15m": atr_15m,
            "fvg_estado": fvg_label,
            "fvg_tipo": fvg_zone.get("tipo") if fvg_zone else "SIN_FVG",
            "fvg_low": fvg_zone.get("low") if fvg_zone else np.nan,
            "fvg_high": fvg_zone.get("high") if fvg_zone else np.nan,
            "fvg_mid": fvg_zone.get("mid") if fvg_zone else np.nan,
            "fvg_dist_atr": fvg_distance_atr,
            "distancia_sl_pts": risk_points_calc,
            "distancia_tp_pts": tp_distance_calc,
            "tp_atr_multiple": tp_atr_multiple,
            "cuenta_usdt": account_usd,
            "riesgo_pct": risk_pct_input,
            "riesgo_usdt_objetivo": risk_usd_target,
            "riesgo_usdt_real": risk_usd,
            "notional_max": max_notional,
            "notional_real": notional,
            "notional_capado": notional_capped,
            "ganancia_tp_usdt": profit_usd,
            "entrada": price,
            "sl": sl_calc,
            "tp": tp_calc,
            "rr_real": rr_real,
            "resultado": np.nan,
            "r_multiple": np.nan,
            "validado_hasta": np.nan,
            "24h": t1d,
            "4h": t4,
            "1h": t1,
            "15m": t15,
            "5m": t5,
            "estructura": structure,
            "motivos_bloqueo": " | ".join(motivos_bloqueo),
        }

        valid_msg = build_valid_signal_msg(decision, SYMBOL, estrategia, price, sl_calc, tp_calc, rr_real, quality_label, quality_score, long_score, short_score, rsi_15, atr_15m, current_candle_time, fvg_label, modo_operativo)
        almost_msg = build_almost_msg(candidate_direction, SYMBOL, estrategia, raw_direction_score, min_score, price, sl_calc, tp_calc, rr_real, long_score, short_score, rsi_15, motivos_bloqueo, current_candle_time, fvg_label)
        bias_msg = build_bias_msg(SYMBOL, market_bias, escenario, t4, t1, t15, t5, structure, price, rsi_15, current_candle_time)
        risk_msg = build_risk_msg(SYMBOL, candidate_direction, price, sl_calc, tp_calc, risk_points_calc, tp_atr_multiple, rr_real, current_candle_time)

        if trade_valid:
            market_color = "GREEN"
        elif candidate_direction in ["LONG", "SHORT"] and raw_direction_score >= max(1, min_score - almost_score_gap):
            market_color = "YELLOW"
        else:
            market_color = "RED"
        market_update_msg = build_market_update_msg(market_color, decision, candidate_direction, SYMBOL, estrategia, price, long_score, short_score, rsi_15, atr_15m, t4, t1, t15, t5, structure, escenario, motivos_bloqueo, current_candle_time)

        auto_saved_now = False
        alert_events = []

        if alert_market_updates and telegram_enabled:
            minute_now = datetime.utcnow().minute
            interval = int(market_update_minutes)
            bucket_minute = (minute_now // interval) * interval
            market_update_key = f"MARKET_UPDATE_{datetime.utcnow().strftime('%Y-%m-%d_%H')}_{bucket_minute:02d}"
            if minute_now % interval == 0:
                ok, resp = send_alert_once(market_update_key, f"market_update_{interval}min", market_update_msg, telegram_enabled, discord_enabled, discord_webhook_url, telegram_bot_token, telegram_chat_id)
                if ok:
                    alert_events.append(f"📡 Resumen de mercado enviado a Telegram cada {interval} min.")

        if auto_capture_enabled and trade_valid:
            auto_df = safe_read_csv(AUTO_SIGNALS_FILE)
            row_auto = current_signal_row.copy()
            row_auto["signal_key"] = signal_key(row_auto)
            existing_keys = set(auto_df["signal_key"].astype(str)) if "signal_key" in auto_df.columns else set()
            if row_auto["signal_key"] not in existing_keys:
                save_signal_row(AUTO_SIGNALS_FILE, row_auto)
                auto_saved_now = True

        if alert_valid_signals and trade_valid:
            valid_key = f"VALID_{signal_key(current_signal_row)}"
            ok, resp = send_alert_once(valid_key, "señal_valida", valid_msg, telegram_enabled, discord_enabled, discord_webhook_url, telegram_bot_token, telegram_chat_id)
            if ok:
                alert_events.append("🚨 Señal válida enviada por alerta.")

        almost_condition = (
            alert_almost_setups and not trade_valid and candidate_direction in ["LONG", "SHORT"]
            and raw_direction_score >= max(1, min_score - almost_score_gap)
            and long_score != short_score and not pd.isna(rr_real) and rr_real >= min_rr
            and not pd.isna(risk_points_calc) and not pd.isna(atr_15m)
            and risk_points_calc <= atr_15m * max_atr_multiplier
        )
        if almost_condition:
            almost_key = f"ALMOST_{current_candle_time}_{estrategia}_{candidate_direction}_{raw_direction_score}_{min_score}_{fvg_label}"
            ok, resp = send_alert_once(almost_key, "setup_en_formacion", almost_msg, telegram_enabled, discord_enabled, discord_webhook_url, telegram_bot_token, telegram_chat_id)
            if ok:
                alert_events.append("⚠️ Setup en formación enviado.")

        current_state_key = f"{market_bias}_{t4}_{t1}_{t15}_{t5}_{structure}_{fvg_label}"
        previous_state_key = load_market_state()
        if alert_bias_change and previous_state_key and previous_state_key != current_state_key:
            bias_key = f"BIAS_{current_candle_time}_{current_state_key}"
            ok, resp = send_alert_once(bias_key, "cambio_sesgo", bias_msg, telegram_enabled, discord_enabled, discord_webhook_url, telegram_bot_token, telegram_chat_id)
            if ok:
                alert_events.append("🔄 Cambio de sesgo enviado.")
        if previous_state_key != current_state_key:
            save_market_state(current_state_key)

        risk_warning_condition = (
            alert_risk_warning and candidate_direction in ["LONG", "SHORT"]
            and not pd.isna(tp_atr_multiple) and tp_atr_multiple >= 4
            and not pd.isna(risk_points_calc) and not pd.isna(atr_15m)
            and risk_points_calc >= atr_15m * max_atr_multiplier
        )
        if risk_warning_condition:
            risk_key = f"RISK_{current_candle_time}_{estrategia}_{candidate_direction}_{round(float(tp_atr_multiple), 1)}"
            ok, resp = send_alert_once(risk_key, "riesgo_objetivo_exigente", risk_msg, telegram_enabled, discord_enabled, discord_webhook_url, telegram_bot_token, telegram_chat_id)
            if ok:
                alert_events.append("⚠️ Alerta de riesgo enviada.")

        with tab1:
            
    
    
            if zonas_daytrade:
                mejor = zonas_daytrade[0]
                st.markdown("### 🧠 Mejor oportunidad detectada")
                st.markdown(
                    f"""
            **{mejor['semaforo']}**  
            **Calidad:** {mejor['color']} {mejor['calidad']} — {mejor['score']}/100 {mejor['estrellas']}  
            **Sesgo:** {mejor['sesgo']}  
            **Zona:** {mejor['desde']:.2f} - {mejor['hasta']:.2f}  
            **Distancia al centro:** {mejor['distancia_pts']:.0f} pts ({mejor['distancia_atr']:.2f} ATR)  
            **Estado:** {mejor['estado']}  
            **Acción:** {mejor['accion']}
            """
                )
                st.markdown("#### Confirmaciones")
                checks = []
                for nombre, ok in mejor["confirmaciones"].items():
                    checks.append(f"{'✅' if ok else '❌'} {nombre}")
                st.write(" | ".join(checks))
                st.markdown(
                    f"""
            **Confirmadas:** {mejor['confirmadas']} / {mejor['total_confirmaciones']}  
            **Falta para habilitar entrada:**  
            {", ".join(mejor["faltan"])}
            """
                )
                st.divider()
                st.markdown("### 📍 Otras zonas relevantes")
                for i, z in enumerate(zonas_daytrade[1:], start=2):
                    st.markdown(
                        f"""
            **Zona {i}: {z['calidad']} — {z['score']}/100 {z['estrellas']}**  
            Rango: **{z['desde']:.2f} - {z['hasta']:.2f}**  
            Estado: {z['estado']}  
            Acción: {z['accion']}  
            Confluencias: {", ".join(z["motivos"])}
            """
                    )
            else:
                st.info("No hay zonas profesionales relevantes cercanas ahora.")
    
            st.divider()     

            with st.expander("📌 Motivo de la decisión", expanded=True):
                st.write(f"**Estrategia activa:** {estrategia}")
                st.write(f"**Escenario:** {escenario}")
                st.write(f"**Dirección calculada:** {display_direction(candidate_direction)}")
                st.write(f"**Estructura 5M:** {structure}")
                st.write(f"**Long Score:** {long_score}/10")
                st.write(f"**Short Score:** {short_score}/10")
                st.write(f"**Score PRO:** {quality_detail['score_100']}/100")
                st.write("**Factores positivos:**")
                for p in quality_detail["positivos"]:
                    st.success(p)
                st.write("**Factores negativos / faltantes:**")
                for n in quality_detail["negativos"]:
                    st.warning(n)
                st.write(f"**RR real:** {format_number(rr_real, 2)}")
                st.write(f"**ATR 15M:** {format_number(atr_15m, 2)} puntos")
                st.write(f"**FVG:** {fvg_label}")
                if fvg_zone:
                    st.write(f"**Zona FVG:** {fmt0(fvg_zone['low'])} - {fmt0(fvg_zone['high'])} | MID {fmt0(fvg_zone['mid'])} | Gap {fmt0(fvg_zone['gap_pts'])} pts")
                st.write(f"**Distancia SL:** {format_number(risk_points_calc, 2)} puntos")
                st.write(f"**Distancia TP:** {format_number(tp_distance_calc, 2)} puntos")
                if trade_valid:
                    st.success(f"Setup válido para estrategia: {estrategia}.")
                else:
                    for motivo in motivos_bloqueo:
                        st.warning(motivo)
    
            
    
            
    
            



        # ===== ORDER BLOCKS EN GRÁFICO =====
        if ob_df is not None and not ob_df.empty:
            ob_open = ob_df[~ob_df["mitigated"].astype(bool)].copy().tail(4)
            x1 = chart_df["time"].iloc[-1]
            for _, ob in ob_open.iterrows():
                fill = "rgba(0, 180, 80, 0.12)" if ob["direction"] == "LONG" else "rgba(220, 0, 0, 0.12)"
                line = "rgba(0, 120, 60, 0.75)" if ob["direction"] == "LONG" else "rgba(180, 0, 0, 0.75)"
                fig.add_shape(
                    type="rect",
                    xref="x",
                    yref="y",
                    x0=ob["time"],
                    x1=x1,
                    y0=ob["low"],
                    y1=ob["high"],
                    fillcolor=fill,
                    line=dict(color=line, width=1),
                    layer="below"
                )
                fig.add_annotation(
                    x=x1,
                    y=ob["mid"],
                    text=ob["tipo"].replace("_", " "),
                    showarrow=False,
                    xanchor="left",
                    font=dict(size=10, color=line)
                )
        # ===== FIN ORDER BLOCKS =====

        # ===== PERFIL DE LIQUIDEZ EN GRÁFICO =====
        if liq_profile_df is not None and not liq_profile_df.empty:
            liq_plot = liq_profile_df.head(8).copy()
            for _, liq in liq_plot.iterrows():
                if liq["tipo"] == "EQUAL_HIGHS":
                    color = "rgba(180, 0, 0, 0.85)"
                    label = "EQH"
                else:
                    color = "rgba(0, 120, 60, 0.85)"
                    label = "EQL"
                dash = "solid" if liq["estado"] == "BARRIDO" else "dot"
                fig.add_hline(
                    y=liq["nivel"],
                    line_color=color,
                    line_width=2,
                    line_dash=dash,
                    annotation_text=f"{label} {liq['estado']}",
                    annotation_position="right"
                )
        # ===== FIN PERFIL LIQUIDEZ =====

        # ===== VOLUMEN INSTITUCIONAL EN GRÁFICO =====
        if inst_vol_df is not None and not inst_vol_df.empty:
            inst_plot = inst_vol_df.tail(5).copy()
            for _, v in inst_plot.iterrows():
                if v["direction"] == "LONG":
                    txt = "🏦 VOL LONG"
                    y = v["low"]
                    ay = 45
                else:
                    txt = "🏦 VOL SHORT"
                    y = v["high"]
                    ay = -45
                fig.add_annotation(
                    x=v["time"],
                    y=y,
                    text=txt,
                    showarrow=True,
                    arrowhead=2,
                    arrowsize=1.4,
                    arrowwidth=2,
                    ax=0,
                    ay=ay
                )
        # ===== FIN VOLUMEN INSTITUCIONAL =====

        for name, value in levels.items():
            if not pd.isna(value):
                fig.add_hline(y=value, line_dash="dot", line_color="gray", annotation_text=name, annotation_position="right")
        should_show_trade_levels = trade_valid or show_levels_when_no_trade
        if should_show_trade_levels and not pd.isna(sl_calc):
            fig.add_hline(y=sl_calc, line_color="red", line_width=3, annotation_text="SL")
        if should_show_trade_levels and not pd.isna(tp_calc):
            fig.add_hline(y=tp_calc, line_color="green", line_width=3, annotation_text="TP")
        fig.add_hline(y=price, line_color="black", line_width=3, annotation_text="Entrada")
        if volume_profile:
            fig.add_hline(
                y=volume_profile["poc"],
                line_color="blue",
                line_width=2,
                line_dash="solid",
                annotation_text="POC"
            )
            fig.add_hline(
                y=volume_profile["vah"],
                line_color="purple",
                line_width=2,
                line_dash="dash",
                annotation_text="VAH"
            )
            fig.add_hline(
                y=volume_profile["val"],
                line_color="purple",
                line_width=2,
                line_dash="dash",
                annotation_text="VAL"
            )
            # ===== DELTA DE VOLUMEN EN GRÁFICO =====
            last_delta = df_15m["volume_delta"].iloc[-1]
            last_delta_strength = df_15m["delta_strength"].iloc[-1]
            if last_delta_strength >= 1.5:
                fig.add_annotation(
                    x=chart_df["time"].iloc[-1],
                    y=chart_df["low"].iloc[-1],
                    text="🟢 Δ BUY",
                    showarrow=True,
                    arrowhead=2,
                    arrowcolor="green",
                    arrowsize=1.5,
                    arrowwidth=2,
                    font=dict(size=13, color="green"),
                    ax=0,
                    ay=45
                )
            elif last_delta_strength <= -1.5:
                fig.add_annotation(
                    x=chart_df["time"].iloc[-1],
                    y=chart_df["high"].iloc[-1],
                    text="🔴 Δ SELL",
                    showarrow=True,
                    arrowhead=2,
                    arrowcolor="red",
                    arrowsize=1.5,
                    arrowwidth=2,
                    font=dict(size=13, color="red"),
                    ax=0,
                    ay=-45
                )
            # ===== FIN DELTA DE VOLUMEN =====
        # ===== ZONAS RR =====
        if (
            should_show_trade_levels
            and not pd.isna(sl_calc)
            and not pd.isna(tp_calc)
        ):
            if candidate_direction == "LONG":
                fig.add_hrect(
                    y0=price,
                    y1=tp_calc,
                    fillcolor="green",
                    opacity=0.08,
                    line_width=0
                )
                fig.add_hrect(
                    y0=sl_calc,
                    y1=price,
                    fillcolor="red",
                    opacity=0.08,
                    line_width=0
                )
            elif candidate_direction == "SHORT":
                fig.add_hrect(
                    y0=tp_calc,
                    y1=price,
                    fillcolor="green",
                    opacity=0.08,
                    line_width=0
                )
                fig.add_hrect(
                    y0=price,
                    y1=sl_calc,
                    fillcolor="red",
                    opacity=0.08,
                    line_width=0
                )
        # ===== FIN ZONAS RR =====
        fig.update_layout(template="plotly_white", height=700, xaxis_rangeslider_visible=False, title="BTCUSDT 15M - Velas + EMAs + Liquidez + FVG + SL/TP", margin=dict(l=20, r=20, t=50, b=20))
        fig.update_layout(
            paper_bgcolor="white",
            plot_bgcolor="white"
        )
        fig.update_yaxes(
            gridcolor="rgba(0,0,0,0.08)"
        )
        fig.update_xaxes(
            gridcolor="rgba(0,0,0,0.05)"
        )
        y_values = [chart_df["low"].min(), chart_df["high"].max()]
        for val in [sl_calc, tp_calc, price]:
            if not pd.isna(val):
                y_values.append(val)
        y_min, y_max = min(y_values), max(y_values)
        padding = max((y_max - y_min) * 0.12, 100)
        fig.update_yaxes(range=[y_min - padding, y_max + padding], autorange=False)
        with grafico_operativo_slot:
            st.plotly_chart(
                fig,
                use_container_width=True,
                config={"responsive": True},
                key="grafico_operativo"
            )
        with tab4:
            st.divider()

            g1, g2, g3, g4, g5, g6, g7 = st.columns(7)
            g1.metric("Cuenta", f"{account_usd:.0f} USDT")
            g2.metric("Riesgo real", f"{risk_usd:.2f} USDT", f"Obj: {risk_usd_target:.2f}")
            g3.metric("Ganancia TP", f"+{profit_usd:.2f} USDT", f"{profit_pct:.2f}%")
            g4.metric("Tamaño", f"{btc_size:.4f} BTC")
            g5.metric("Nocional real", f"{notional:.0f} USDT")
            g6.metric("Máx nocional", f"{max_notional:.0f} USDT")
            g7.metric("Margen", f"{margin_needed:.0f} USDT")
    
            r1, r2, r3, r4, r5, r6 = st.columns(6)
            r1.metric("Entrada", f"{price:,.0f}")
            r2.metric("SL técnico", f"{sl_calc:,.0f}" if not pd.isna(sl_calc) else "—")
            r3.metric("TP automático", f"{tp_calc:,.0f}" if not pd.isna(tp_calc) else "—")
            r4.metric("Distancia SL", f"{risk_points_calc:,.0f} pts" if not pd.isna(risk_points_calc) else "—")
            r5.metric("Distancia TP", f"{tp_distance_calc:,.0f} pts" if not pd.isna(tp_distance_calc) else "—")
            r6.metric("RR real", f"{rr_real:.2f}" if not pd.isna(rr_real) else "—")
            st.divider()

            if st.button("💾 Guardar señal manual", key="save_manual_signal"):
                save_signal_row(SIGNALS_FILE, current_signal_row)
                st.success("Señal guardada correctamente.")

        with tab5:
            st.subheader("📊 Historial de señales")
            historial = safe_read_csv(SIGNALS_FILE)
            if not historial.empty:
                historial = validate_saved_signals(historial, df_5m, validate_after_hours)
                historial.to_csv(SIGNALS_FILE, index=False)
            auto_historial = safe_read_csv(AUTO_SIGNALS_FILE)
            if not auto_historial.empty:
                auto_historial = validate_saved_signals(auto_historial, df_5m, validate_after_hours)
                auto_historial.to_csv(AUTO_SIGNALS_FILE, index=False)
            pieces = []
            if not historial.empty:
                pieces.append(historial.assign(origen="manual"))
            if not auto_historial.empty:
                pieces.append(auto_historial.assign(origen="auto"))
            combined_hist = pd.concat(pieces, ignore_index=True) if pieces else pd.DataFrame()
    
            stats_hist = performance_stats(combined_hist)
            stats_30, hist_30 = last_30_days_stats(combined_hist)
            strat_rank = stats_by_strategy(combined_hist)
    
            h1, h2, h3, h4 = st.columns(4)
            h1.metric("Señales validadas", int(stats_hist.get("operaciones", 0)))
            h2.metric("Winrate real", f"{stats_hist.get('winrate', 0):.1f}%")
            h3.metric("PF real", "∞" if stats_hist.get("profit_factor", 0) == np.inf else f"{stats_hist.get('profit_factor', 0):.2f}")
            h4.metric("Expectativa real", f"{stats_hist.get('expectancy', 0):+.2f}R")
    
            if mc_enabled:
                st.divider()
                st.subheader("🎯 Monte Carlo: riesgo de ruina y Max Drawdown")
                r_mults, mc_source = build_r_multiples_from_sources(bt_results, combined_hist, mc_use_backtest, mc_manual_wr, mc_manual_rr)
                mc = monte_carlo_simulation(r_mults, mc_start_capital, risk_pct, int(mc_paths), int(mc_trades_horizon), float(mc_ruin_dd_pct))
                expected_days = int(np.ceil(int(mc_trades_horizon) / max(int(mc_max_daily_trades), 1)))
                dd_color = "🟢" if mc["dd_p95"] < 10 else "🟡" if mc["dd_p95"] < 20 else "🔴"
                st.caption(f"Fuente usada: {mc_source}. Horizonte aproximado: {mc_trades_horizon} trades ≈ {expected_days} días si hacés hasta {mc_max_daily_trades} trades/día.")
                m1, m2, m3, m4, m5 = st.columns(5)
                m1.metric("DD mediano", f"{mc['dd_median']:.1f}%")
                m2.metric("DD P75", f"{mc['dd_p75']:.1f}%")
                m3.metric("DD P95", f"{mc['dd_p95']:.1f}%", dd_color)
                m4.metric("Racha perdedora P95", f"{mc['loss_streak_p95']:.0f} trades")
                m5.metric("Riesgo ruina", f"{mc['ruin_probability']:.1f}%")
    
                if mc["dd_p95"] >= 20 or mc["ruin_probability"] >= 10:
                    st.error("🔴 Riesgo elevado: con estos parámetros una mala racha puede lastimar fuerte la cuenta. Bajá riesgo por operación o reducí cantidad de trades.")
                elif mc["dd_p95"] >= 10:
                    st.warning("🟡 Riesgo moderado: operable solo con disciplina estricta y sin mover SL.")
                else:
                    st.success("🟢 Riesgo controlado: el drawdown simulado está dentro de un rango más razonable.")
    
                mc_tabs = st.tabs(["Distribución Max Drawdown", "Curvas simuladas", "Tabla resumen"])
                with mc_tabs[0]:
                    dd_fig = go.Figure()
                    dd_fig.add_trace(go.Histogram(x=mc["dd_values"], nbinsx=50, name="Max Drawdown %"))
                    for label, val in [("Mediana", mc["dd_median"]), ("P95", mc["dd_p95"]), ("P99", mc["dd_p99"]), ("Ruina", float(mc_ruin_dd_pct))]:
                        dd_fig.add_vline(x=val, line_dash="dash", annotation_text=f"{label}: {val:.1f}%", annotation_position="top")
                    dd_fig.update_layout(template="plotly_white", height=380, title=f"Distribución del Max Drawdown simulado — Horizonte {mc_trades_horizon} trades", xaxis_title="Max Drawdown (%) por escenario", yaxis_title="Frecuencia", margin=dict(l=20, r=20, t=60, b=20))
                    st.plotly_chart(dd_fig, use_container_width=True,config={"responsive": True}, key="mc_dd_hist")
                with mc_tabs[1]:
                    curves_fig = go.Figure()
                    x = list(range(1, int(mc_trades_horizon) + 1))
                    for i, curve in enumerate(mc["sample_curves"][:20]):
                        curves_fig.add_trace(go.Scatter(x=x, y=curve, mode="lines", name=f"Escenario {i+1}", opacity=0.35, showlegend=False))
                    curves_fig.add_hline(y=mc_start_capital, line_dash="dot", annotation_text="Capital inicial")
                    curves_fig.add_hline(y=mc_start_capital * (1 - float(mc_ruin_dd_pct) / 100), line_dash="dash", annotation_text=f"Alerta DD {mc_ruin_dd_pct:.0f}%")
                    curves_fig.update_layout(template="plotly_white", height=380, title="Curvas de equity simuladas", xaxis_title="Trade", yaxis_title="Capital USDT", margin=dict(l=20, r=20, t=60, b=20))
                    st.plotly_chart(curves_fig, use_container_width=True,config={"responsive": True}, key="mc_curves")
                with mc_tabs[2]:
                    summary_df = pd.DataFrame([{
                        "fuente": mc_source,
                        "escenarios": mc["paths"],
                        "trades_horizonte": mc["horizon"],
                        "capital_inicial": mc["start_capital"],
                        "riesgo_por_trade_%": risk_pct_input,
                        "DD_mediana_%": round(mc["dd_median"], 2),
                        "DD_P95_%": round(mc["dd_p95"], 2),
                        "DD_P99_%": round(mc["dd_p99"], 2),
                        "capital_final_P05": round(mc["final_p05"], 2),
                        "capital_final_mediana": round(mc["final_median"], 2),
                        "capital_final_P95": round(mc["final_p95"], 2),
                        "racha_perdedora_P95": round(mc["loss_streak_p95"], 0),
                        "riesgo_ruina_%": round(mc["ruin_probability"], 2),
                    }])
                    st.dataframe(summary_df, use_container_width=True)
                    st.caption("Este módulo no predice precio. Evalúa supervivencia de cuenta con rachas y drawdown probables.")
    
            st.subheader("🏆 Ranking de estrategias")
            if not strat_rank.empty:
                st.dataframe(strat_rank, use_container_width=True)
            else:
                st.info("Todavía no hay suficientes operaciones validadas por estrategia.")
    
            st.subheader("📅 Estadísticas últimos 30 días")
            l1, l2, l3, l4 = st.columns(4)
            l1.metric("Ops 30D", int(stats_30.get("operaciones", 0)))
            l2.metric("Winrate 30D", f"{stats_30.get('winrate', 0):.1f}%")
            l3.metric("PF 30D", "∞" if stats_30.get("profit_factor", 0) == np.inf else f"{stats_30.get('profit_factor', 0):.2f}")
            l4.metric("Expectativa 30D", f"{stats_30.get('expectancy', 0):+.2f}R")
    
            st.subheader("📈 Equity curve real")
            closed_real = combined_hist[combined_hist["resultado"].isin(["TP", "SL"])].copy() if not combined_hist.empty and "resultado" in combined_hist.columns else pd.DataFrame()
            if not closed_real.empty:
                closed_real["fecha_dt"] = pd.to_datetime(closed_real["fecha"], utc=True, errors="coerce")
                closed_real = closed_real.sort_values("fecha_dt")
                closed_real["r_multiple"] = pd.to_numeric(closed_real["r_multiple"], errors="coerce").fillna(0)
                closed_real["equity_r"] = closed_real["r_multiple"].cumsum()
                real_fig = go.Figure()
                real_fig.add_trace(go.Scatter(x=closed_real["fecha_dt"], y=closed_real["equity_r"], mode="lines+markers", name="Equity real R"))
                real_fig.update_layout(template="plotly_white", height=350, title="Equity curve real de señales guardadas", margin=dict(l=20, r=20, t=50, b=20))
                st.plotly_chart(real_fig, use_container_width=True,config={"responsive": True}, key="equity_real")
            else:
                st.info("La equity curve real aparece cuando haya señales cerradas en TP o SL.")
    
            st.subheader("🖼️ Historial visual de operaciones")
            if not combined_hist.empty:
                show_cols = [c for c in ["fecha", "vela_5m", "origen", "estrategia", "decision", "direccion_calculada", "calidad_score", "entrada", "sl", "tp", "resultado", "r_multiple", "rr_real", "fvg_estado", "notional_real", "riesgo_usdt_real", "motivos_bloqueo"] if c in combined_hist.columns]
                st.dataframe(combined_hist[show_cols].tail(50), use_container_width=True)
                st.download_button("⬇️ Descargar historial completo CSV", data=combined_hist.to_csv(index=False), file_name="signals_log_completo.csv", mime="text/csv", key="download_hist")
            else:
                st.info("Todavía no hay señales guardadas.")
    
            st.subheader("🔔 Historial de alertas")
            alerts_df = safe_read_csv(ALERTS_FILE)
            if not alerts_df.empty:
                st.dataframe(alerts_df.tail(30), use_container_width=True)
                st.download_button("⬇️ Descargar alertas CSV", data=alerts_df.to_csv(index=False), file_name="alerts_sent_log.csv", mime="text/csv", key="download_alerts")
            else:
                st.info("Todavía no hay alertas enviadas.")
            st.subheader("🧱 FVG inteligentes detectados")
            if not fvg_df.empty:
                fvg_show = fvg_df.head(12).copy()
                fvg_show["time"] = fvg_show["time"].astype(str)
                st.dataframe(
                    fvg_show[
                        [
                            "time",
                            "tipo",
                            "direction",
                            "low",
                            "mid",
                            "high",
                            "gap_pts",
                            "gap_atr",
                            "distance_atr",
                            "mitigated",
                            "score",
                            "calidad",
                            "motivo",
                        ]
                    ],
                    use_container_width=True
                )
            else:
                st.info("No hay FVG inteligentes relevantes en el lookback actual.")
            st.subheader("⏰ Filtro horario")
            st.write("Activo" if filter_hours else "Inactivo")
            st.caption("Filtro usado: Londres 07:00-10:00 UTC y NY 13:00-16:00 UTC. Fin de semana bloqueado si está activado.")
    
            with st.expander("📘 Reglas del sistema"):
                st.write("""
                - Score menor al mínimo configurado = NO OPERAR.
                - RR real menor al mínimo configurado = NO OPERAR.
                - Riesgo mayor al 1% = NO OPERAR.
                - Nocional corregido: nunca supera Cuenta x Apalancamiento.
                - Si el tamaño por riesgo exige más margen del posible, el sistema limita el nocional y recalcula el riesgo real.
                - FVG bullish: gap entre high de vela i-2 y low de vela actual.
                - FVG bearish: gap entre high de vela actual y low de vela i-2.
                - FVG se considera mitigado si el precio toca el midpoint del gap.
                - FVG + Tendencia prioriza operar cerca/dentro de zonas FVG abiertas.
                - Monte Carlo mide drawdown, rachas y supervivencia de cuenta. No predice precio.
                - Telegram/Discord envían solo alertas nuevas; se evita spam con alerts_sent_log.csv.
                - Auto refresh mantiene el sistema atento mientras la app esté abierta.
                """)
    
            st.caption(f"Última actualización local: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

    except Exception as e:
        st.error("Hubo un error cargando el dashboard.")
        st.exception(e)