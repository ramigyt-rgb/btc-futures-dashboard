# fut_app.py

# Ejecutar:

# py -m streamlit run fut_app.py



import os

from datetime import datetime



import ccxt

import numpy as np

import pandas as pd

import plotly.graph_objects as go

import streamlit as st





# =========================

# CONFIG GENERAL

# =========================



st.set_page_config(

    page_title="BTCUSDT Futures Dashboard Pro",

    layout="wide",

    initial_sidebar_state="expanded"

)



SIGNALS_FILE = "signals_log.csv"

SYMBOL = "BTC/USDT:USDT"

LIMIT = 300





# =========================

# SIDEBAR

# =========================



st.sidebar.title("Configuración")



estrategia = st.sidebar.selectbox(

    "Estrategia",

    [

        "Tendencia + Liquidez",

        "Pullback EMA50",

        "Sweep de Liquidez",

        "Ruptura de Estructura",

        "Reversión Extrema"

    ]

)



account_usd = st.sidebar.number_input(

    "Cuenta USDT",

    min_value=10.0,

    value=500.0,

    step=10.0

)



risk_pct_input = st.sidebar.number_input(

    "Riesgo por operación %",

    min_value=0.1,

    max_value=5.0,

    value=1.0,

    step=0.1

)



risk_pct = risk_pct_input / 100



leverage = st.sidebar.selectbox(

    "Apalancamiento sugerido",

    [3, 5, 10, 20],

    index=1

)



min_score = st.sidebar.slider(

    "Score mínimo para operar",

    1,

    10,

    7

)



rr_target = st.sidebar.number_input(

    "Riesgo/Beneficio objetivo",

    min_value=1.0,

    max_value=10.0,

    value=2.0,

    step=0.1

)



min_rr = st.sidebar.number_input(

    "RR mínimo aceptado",

    min_value=1.0,

    max_value=10.0,

    value=1.8,

    step=0.1

)



max_atr_multiplier = st.sidebar.number_input(

    "Máximo SL permitido en ATR",

    min_value=0.5,

    max_value=5.0,

    value=2.0,

    step=0.1

)



show_levels_when_no_trade = st.sidebar.checkbox(

    "Mostrar SL/TP aunque sea NO OPERAR",

    value=False

)



st.sidebar.divider()



if st.sidebar.button("🔄 Actualizar datos"):

    st.rerun()





# =========================

# EXCHANGE

# =========================



exchange = ccxt.okx({

    "enableRateLimit": True,

    "options": {"defaultType": "swap"}

})





# =========================

# DATA

# =========================



@st.cache_data(ttl=60)

def get_ohlcv(timeframe):

    data = exchange.fetch_ohlcv(SYMBOL, timeframe=timeframe, limit=LIMIT)



    df = pd.DataFrame(

        data,

        columns=["time", "open", "high", "low", "close", "volume"]

    )



    df["time"] = pd.to_datetime(df["time"], unit="ms", utc=True)

    return df





def add_indicators(df):

    df = df.copy()



    df["ema20"] = df["close"].ewm(span=20, adjust=False).mean()

    df["ema50"] = df["close"].ewm(span=50, adjust=False).mean()

    df["ema200"] = df["close"].ewm(span=200, adjust=False).mean()



    delta = df["close"].diff()

    gain = delta.clip(lower=0)

    loss = -delta.clip(upper=0)



    avg_gain = gain.rolling(14).mean()

    avg_loss = loss.rolling(14).mean()



    rs = avg_gain / avg_loss

    df["rsi"] = 100 - (100 / (1 + rs))



    tr1 = df["high"] - df["low"]

    tr2 = (df["high"] - df["close"].shift()).abs()

    tr3 = (df["low"] - df["close"].shift()).abs()



    df["tr"] = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)

    df["atr"] = df["tr"].rolling(14).mean()



    df["range"] = df["high"] - df["low"]

    df["body"] = (df["close"] - df["open"]).abs()

    df["upper_wick"] = df["high"] - df[["open", "close"]].max(axis=1)

    df["lower_wick"] = df[["open", "close"]].min(axis=1) - df["low"]



    return df





def load_all_data():

    df_1d = add_indicators(get_ohlcv("1d"))

    df_4h = add_indicators(get_ohlcv("4h"))

    df_1h = add_indicators(get_ohlcv("1h"))

    df_15m = add_indicators(get_ohlcv("15m"))

    df_5m = add_indicators(get_ohlcv("5m"))



    return df_1d, df_4h, df_1h, df_15m, df_5m





# =========================

# ANALISIS

# =========================



def safe_float(value):

    try:

        if pd.isna(value):

            return np.nan

        return float(value)

    except Exception:

        return np.nan





def trend_state(df):

    last = df.iloc[-1]



    if last["close"] > last["ema20"] > last["ema50"] > last["ema200"]:

        return "BULL"



    if last["close"] < last["ema20"] < last["ema50"] < last["ema200"]:

        return "BEAR"



    return "NEUTRAL"





def trend_icon(state):

    if state == "BULL":

        return "🟢 BULL"



    if state == "BEAR":

        return "🔴 BEAR"



    return "⚪ NEUTRAL"





def rsi_state(value):

    if value < 30:

        return "SOBREVENTA"



    if value > 70:

        return "SOBRECOMPRA"



    if 45 <= value <= 60:

        return "OK"



    return "NEUTRO"





def structure_state(df):

    recent = df.tail(20)



    last_high = recent["high"].iloc[-1]

    last_low = recent["low"].iloc[-1]



    prev_high = recent["high"].iloc[:-1].max()

    prev_low = recent["low"].iloc[:-1].min()



    if last_high > prev_high:

        return "BREAK_UP"



    if last_low < prev_low:

        return "BREAK_DOWN"



    return "SIN_RUPTURA"





def liquidity_levels(df):

    data = df.copy()

    data["date"] = data["time"].dt.date

    data["hour"] = data["time"].dt.hour



    dates = sorted(data["date"].unique())



    if len(dates) < 2:

        return {}



    today = dates[-1]

    yesterday = dates[-2]



    today_df = data[data["date"] == today]

    yesterday_df = data[data["date"] == yesterday]



    asia = today_df[(today_df["hour"] >= 0) & (today_df["hour"] < 7)]

    london = today_df[(today_df["hour"] >= 7) & (today_df["hour"] < 10)]

    ny = today_df[(today_df["hour"] >= 13) & (today_df["hour"] < 16)]



    return {

        "Máx día anterior": yesterday_df["high"].max(),

        "Mín día anterior": yesterday_df["low"].min(),

        "Máx Asia": asia["high"].max() if len(asia) else np.nan,

        "Mín Asia": asia["low"].min() if len(asia) else np.nan,

        "Máx Londres": london["high"].max() if len(london) else np.nan,

        "Mín Londres": london["low"].min() if len(london) else np.nan,

        "Máx NY": ny["high"].max() if len(ny) else np.nan,

        "Mín NY": ny["low"].min() if len(ny) else np.nan,

    }





def nearest_liquidity(price, levels, direction):

    clean_levels = {

        k: v for k, v in levels.items()

        if not pd.isna(v)

    }



    if direction == "LONG":

        targets = {

            k: v for k, v in clean_levels.items()

            if v > price

        }

    else:

        targets = {

            k: v for k, v in clean_levels.items()

            if v < price

        }



    if not targets:

        return None, np.nan, np.nan



    name, level = min(

        targets.items(),

        key=lambda item: abs(item[1] - price)

    )



    distance = abs(level - price)

    return name, level, distance





def detect_market_intention(price, df_4h, df_1h, df_15m, levels):

    t4 = trend_state(df_4h)

    t1 = trend_state(df_1h)

    t15 = trend_state(df_15m)



    rsi = df_15m["rsi"].iloc[-1]

    ema20 = df_15m["ema20"].iloc[-1]

    ema50 = df_15m["ema50"].iloc[-1]

    ema200 = df_15m["ema200"].iloc[-1]



    atr = df_15m["atr"].iloc[-1]



    upside_name, upside_level, upside_distance = nearest_liquidity(price, levels, "LONG")

    downside_name, downside_level, downside_distance = nearest_liquidity(price, levels, "SHORT")



    near_upside_liquidity = not pd.isna(upside_distance) and upside_distance <= atr * 0.7

    near_downside_liquidity = not pd.isna(downside_distance) and downside_distance <= atr * 0.7



    if t4 == "BULL" and t1 == "BULL" and price > ema20 > ema50 > ema200:

        if near_upside_liquidity:

            return "ALCISTA CON LIQUIDEZ SUPERIOR CERCA", "LONG_CON_CUIDADO"



        return "TENDENCIA ALCISTA", "LONG"



    if t4 == "BEAR" and t1 == "BEAR" and price < ema20 < ema50 < ema200:

        if near_downside_liquidity:

            return "BAJISTA CON LIQUIDEZ INFERIOR CERCA", "SHORT_CON_CUIDADO"



        return "TENDENCIA BAJISTA", "SHORT"



    if 45 <= rsi <= 55:

        return "RANGO / COMPRESIÓN", "NEUTRAL"



    return "SIN INTENCIÓN CLARA", "NEUTRAL"





def score_direction(direction, df_4h, df_1h, df_15m, df_5m, levels):

    score = 0



    t4 = trend_state(df_4h)

    t1 = trend_state(df_1h)

    t15 = trend_state(df_15m)

    t5 = trend_state(df_5m)



    rsi_value = df_15m["rsi"].iloc[-1]

    rsi_ok = rsi_state(rsi_value)



    structure = structure_state(df_5m)

    price = df_5m["close"].iloc[-1]



    liquidity_name, liquidity_level, liquidity_distance = nearest_liquidity(

        price,

        levels,

        direction

    )



    if direction == "LONG":

        if t4 == "BULL":

            score += 2



        if t1 == "BULL":

            score += 2



        if t15 == "BULL":

            score += 1



        if t5 == "BULL":

            score += 1



        if rsi_ok in ["OK", "NEUTRO"]:

            score += 1



        if structure == "BREAK_UP":

            score += 1



        if liquidity_name:

            score += 1



    if direction == "SHORT":

        if t4 == "BEAR":

            score += 2



        if t1 == "BEAR":

            score += 2



        if t15 == "BEAR":

            score += 1



        if t5 == "BEAR":

            score += 1



        if rsi_ok in ["OK", "NEUTRO"]:

            score += 1



        if structure == "BREAK_DOWN":

            score += 1



        if liquidity_name:

            score += 1



    return score





def technical_levels(direction, df_5m, entry, rr_target):

    recent = df_5m.tail(30)

    atr = df_5m["atr"].iloc[-1]



    if pd.isna(atr) or atr <= 0:

        atr = 250



    buffer = atr * 0.35



    if direction == "LONG":

        sl = recent["low"].min() - buffer

        risk_points = entry - sl

        tp = entry + risk_points * rr_target



    elif direction == "SHORT":

        sl = recent["high"].max() + buffer

        risk_points = sl - entry

        tp = entry - risk_points * rr_target



    else:

        sl = np.nan

        tp = np.nan

        risk_points = np.nan



    return sl, tp, risk_points





def calculate_rr(entry, sl, tp, direction):

    if direction == "LONG":

        risk = entry - sl

        reward = tp - entry



    elif direction == "SHORT":

        risk = sl - entry

        reward = entry - tp



    else:

        return np.nan



    if risk <= 0:

        return np.nan



    return reward / risk





def position_size(entry, sl, account_usd, risk_pct, leverage):

    risk_usd = account_usd * risk_pct



    if pd.isna(sl):

        return 0, 0, risk_usd, 0



    distance = abs(entry - sl)



    if distance <= 0:

        return 0, 0, risk_usd, 0



    btc_size = risk_usd / distance

    notional = btc_size * entry

    margin_needed = notional / leverage



    return btc_size, notional, risk_usd, margin_needed





def validate_trade(

    direction,

    long_score,

    short_score,

    min_score,

    risk_pct,

    rr_real,

    min_rr,

    risk_points,

    atr_15m,

    market_bias,

    structure,

    price,

    levels

):

    motivos = []



    if direction is None:

        motivos.append("No hay dirección dominante clara.")

        return False, motivos



    if direction == "LONG":

        if long_score < min_score:

            motivos.append(f"Long Score insuficiente: {long_score}/{min_score}.")



        if long_score <= short_score:

            motivos.append("Long no supera claramente al Short Score.")



        if structure != "BREAK_UP":

            motivos.append("Falta ruptura alcista en 5M.")



        if market_bias not in ["LONG", "LONG_CON_CUIDADO"]:

            motivos.append("La intención de mercado no favorece LONG.")



    if direction == "SHORT":

        if short_score < min_score:

            motivos.append(f"Short Score insuficiente: {short_score}/{min_score}.")



        if short_score <= long_score:

            motivos.append("Short no supera claramente al Long Score.")



        if structure != "BREAK_DOWN":

            motivos.append("Falta ruptura bajista en 5M.")



        if market_bias not in ["SHORT", "SHORT_CON_CUIDADO"]:

            motivos.append("La intención de mercado no favorece SHORT.")



    if risk_pct > 0.01:

        motivos.append("Riesgo mayor al 1% por operación.")



    if pd.isna(rr_real) or rr_real < min_rr:

        motivos.append(f"RR real insuficiente. Mínimo requerido: {min_rr}.")



    if not pd.isna(risk_points) and not pd.isna(atr_15m):

        if risk_points > atr_15m * max_atr_multiplier:

            motivos.append("SL demasiado lejos respecto al ATR.")



    nearest_name, nearest_level, nearest_distance = nearest_liquidity(

        price,

        levels,

        direction

    )



    if nearest_name and not pd.isna(nearest_distance) and not pd.isna(atr_15m):

        if nearest_distance < atr_15m * 0.35:

            motivos.append(f"Entrada demasiado cerca de liquidez: {nearest_name}.")



    valid = len(motivos) == 0

    return valid, motivos





def format_number(value, decimals=2):

    if pd.isna(value):

        return "—"



    return f"{value:,.{decimals}f}"





# =========================

# APP

# =========================



st.title("BTC/USDT FUTUROS DASHBOARD PRO")



st.caption(

    "Sistema objetivo: tendencia + liquidez + estructura + score + riesgo. "

    "No es consejo financiero."

)



try:

    df_1d, df_4h, df_1h, df_15m, df_5m = load_all_data()



    levels = liquidity_levels(df_15m)



    price = df_5m["close"].iloc[-1]



    t1d = trend_state(df_1d)

    t4 = trend_state(df_4h)

    t1 = trend_state(df_1h)

    t15 = trend_state(df_15m)

    t5 = trend_state(df_5m)



    rsi_15 = df_15m["rsi"].iloc[-1]

    rsi_label = rsi_state(rsi_15)



    atr_15m = df_15m["atr"].iloc[-1]

    structure = structure_state(df_5m)



    long_score = score_direction("LONG", df_4h, df_1h, df_15m, df_5m, levels)

    short_score = score_direction("SHORT", df_4h, df_1h, df_15m, df_5m, levels)



    escenario, market_bias = detect_market_intention(

        price,

        df_4h,

        df_1h,

        df_15m,

        levels

    )



    if long_score > short_score:

        candidate_direction = "LONG"

    elif short_score > long_score:

        candidate_direction = "SHORT"

    else:

        candidate_direction = None



    sl_calc, tp_calc, risk_points_calc = technical_levels(

        candidate_direction,

        df_5m,

        price,

        rr_target

    )



    rr_real = calculate_rr(

        price,

        sl_calc,

        tp_calc,

        candidate_direction

    )



    trade_valid, motivos_bloqueo = validate_trade(

        candidate_direction,

        long_score,

        short_score,

        min_score,

        risk_pct,

        rr_real,

        min_rr,

        risk_points_calc,

        atr_15m,

        market_bias,

        structure,

        price,

        levels

    )



    if trade_valid:

        decision = candidate_direction

    else:

        decision = "NO_OPERAR"



    if decision == "NO_OPERAR" and not show_levels_when_no_trade:

        sl = np.nan

        tp = np.nan

        risk_points = np.nan

        rr_display = np.nan

    else:

        sl = sl_calc

        tp = tp_calc

        risk_points = risk_points_calc

        rr_display = rr_real



    btc_size, notional, risk_usd, margin_needed = position_size(

        price,

        sl_calc if not pd.isna(sl_calc) else np.nan,

        account_usd,

        risk_pct,

        leverage

    )



    profit_usd = risk_usd * rr_target if decision != "NO_OPERAR" else 0

    profit_pct = (profit_usd / account_usd) * 100

    loss_pct = (risk_usd / account_usd) * 100



    # =========================

    # DECISION PRINCIPAL

    # =========================



    if decision == "LONG":

        st.success("🟢 LONG PERMITIDO")

    elif decision == "SHORT":

        st.error("🔴 SHORT PERMITIDO")

    else:

        st.warning("⚪ NO OPERAR")



    with st.expander("📌 Motivo de la decisión", expanded=True):

        st.write(f"**Estrategia:** {estrategia}")

        st.write(f"**Escenario:** {escenario}")

        st.write(f"**Estructura 5M:** {structure}")

        st.write(f"**Long Score:** {long_score}/9")

        st.write(f"**Short Score:** {short_score}/9")

        st.write(f"**RR real:** {format_number(rr_real, 2)}")

        st.write(f"**ATR 15M:** {format_number(atr_15m, 2)} puntos")

        st.write(f"**Distancia SL:** {format_number(risk_points_calc, 2)} puntos")



        if trade_valid:

            st.success("Setup válido. Condiciones mínimas cumplidas.")

        else:

            for motivo in motivos_bloqueo:

                st.warning(motivo)



    # =========================

    # METRICAS PRINCIPALES

    # =========================



    col1, col2, col3, col4 = st.columns(4)



    col1.metric("Precio BTCUSDT", format_number(price, 2))

    col2.metric("Long Score", f"{long_score}/9")

    col3.metric("Short Score", f"{short_score}/9")

    col4.metric("RSI 15M", f"{rsi_15:.2f}", rsi_label)



    st.divider()



    c1, c2, c3, c4, c5 = st.columns(5)



    c1.metric("24H", trend_icon(t1d))

    c2.metric("4H", trend_icon(t4))

    c3.metric("1H", trend_icon(t1))

    c4.metric("15M", trend_icon(t15))

    c5.metric("5M", trend_icon(t5))



    st.divider()



    g1, g2, g3, g4, g5, g6 = st.columns(6)



    g1.metric("Cuenta", f"{account_usd:.2f} USDT")

    g2.metric("Riesgo", f"{risk_usd:.2f} USDT", f"{loss_pct:.2f}%")

    g3.metric("Ganancia TP", f"+{profit_usd:.2f} USDT", f"{profit_pct:.2f}%")

    g4.metric("Tamaño", f"{btc_size:.5f} BTC")

    g5.metric("Nocional", f"{notional:.2f} USDT")

    g6.metric("Margen", f"{margin_needed:.2f} USDT")



    r1, r2, r3, r4 = st.columns(4)



    r1.metric("Entrada", format_number(price, 2))

    r2.metric("SL técnico", format_number(sl, 2))

    r3.metric("TP automático", format_number(tp, 2))

    r4.metric("RR real", format_number(rr_display, 2))



    st.divider()



    # =========================

    # GRAFICO

    # =========================



    chart_df = df_15m.tail(150).copy()



    fig = go.Figure()



    fig.add_trace(go.Candlestick(

        x=chart_df["time"],

        open=chart_df["open"],

        high=chart_df["high"],

        low=chart_df["low"],

        close=chart_df["close"],

        name="BTCUSDT"

    ))



    fig.add_trace(go.Scatter(

        x=chart_df["time"],

        y=chart_df["ema20"],

        mode="lines",

        name="EMA 20",

        line=dict(color="#ff6b57", width=2)

    ))



    fig.add_trace(go.Scatter(

        x=chart_df["time"],

        y=chart_df["ema50"],

        mode="lines",

        name="EMA 50",

        line=dict(color="#18c29c", width=2)

    ))



    fig.add_trace(go.Scatter(

        x=chart_df["time"],

        y=chart_df["ema200"],

        mode="lines",

        name="EMA 200",

        line=dict(color="#9b5cff", width=2)

    ))



    for name, value in levels.items():

        if not pd.isna(value):

            fig.add_hline(

                y=value,

                line_dash="dot",

                line_color="white",

                annotation_text=name,

                annotation_position="right"

            )



    if decision != "NO_OPERAR" or show_levels_when_no_trade:

        if not pd.isna(sl_calc):

            fig.add_hline(

                y=sl_calc,

                line_color="red",

                line_width=3,

                annotation_text="SL",

                annotation_position="right"

            )



        if not pd.isna(tp_calc):

            fig.add_hline(

                y=tp_calc,

                line_color="green",

                line_width=3,

                annotation_text="TP",

                annotation_position="right"

            )



        fig.add_hline(

            y=price,

            line_color="black",

            line_width=3,

            annotation_text="Entrada",

            annotation_position="right"

        )



    fig.update_layout(

        template="plotly_dark",

        height=700,

        xaxis_rangeslider_visible=False,

        title="BTCUSDT 15M - Velas + EMAs + Liquidez + SL/TP",

        margin=dict(l=20, r=20, t=50, b=20)

    )



    st.plotly_chart(fig, use_container_width=True)



    st.divider()



    # =========================

    # GUARDAR SEÑAL

    # =========================



    if st.button("💾 Guardar señal"):

        nueva_senal = pd.DataFrame([{

            "fecha": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),

            "estrategia": estrategia,

            "decision": decision,

            "escenario": escenario,

            "precio": price,

            "long_score": long_score,

            "short_score": short_score,

            "rsi_15m": rsi_15,

            "atr_15m": atr_15m,

            "cuenta_usdt": account_usd,

            "riesgo_pct": risk_pct_input,

            "riesgo_usdt": risk_usd,

            "ganancia_tp_usdt": profit_usd,

            "entrada": price,

            "sl": sl_calc,

            "tp": tp_calc,

            "rr_real": rr_real,

            "24h": t1d,

            "4h": t4,

            "1h": t1,

            "15m": t15,

            "5m": t5,

            "estructura": structure,

            "motivos_bloqueo": " | ".join(motivos_bloqueo)

        }])



        if os.path.exists(SIGNALS_FILE):

            historial = pd.read_csv(SIGNALS_FILE)

            historial = pd.concat([historial, nueva_senal], ignore_index=True)

        else:

            historial = nueva_senal



        historial.to_csv(SIGNALS_FILE, index=False)

        st.success("Señal guardada correctamente.")



    # =========================

    # HISTORIAL

    # =========================



    st.subheader("📊 Historial de señales")



    if os.path.exists(SIGNALS_FILE):

        historial = pd.read_csv(SIGNALS_FILE)



        st.dataframe(

            historial.tail(20),

            use_container_width=True

        )



        st.download_button(

            "⬇️ Descargar historial CSV",

            data=historial.to_csv(index=False),

            file_name="signals_log.csv",

            mime="text/csv"

        )

    else:

        st.info("Todavía no hay señales guardadas.")



    # =========================

    # REGLAS

    # =========================



    with st.expander("📘 Reglas del sistema"):

        st.write("""

        - Score menor al mínimo configurado = NO OPERAR.

        - RR real menor al mínimo configurado = NO OPERAR.

        - Riesgo mayor al 1% = NO OPERAR.

        - No operar si Long y Short Score están empatados.

        - No operar contra la intención principal de mercado.

        - No operar si el SL queda demasiado lejos respecto al ATR.

        - No operar si la entrada queda pegada a una liquidez inmediata.

        - 4H y 1H mandan el contexto.

        - 15M confirma estructura.

        - 5M sirve para ejecutar.

        - No mover el SL.

        - No operar para recuperar pérdidas.

        """)



    st.caption(

        f"Última actualización local: "

        f"{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"

    )



except Exception as e:

    st.error("Hubo un error cargando el dashboard.")

    st.exception(e)