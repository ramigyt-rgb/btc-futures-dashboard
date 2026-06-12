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



from datetime import datetime



st.set_page_config(



    page_title="BTCUSDT Futures Dashboard",



    layout="wide",



    initial_sidebar_state="expanded"



)

# =========================

# GUARDAR SEÑAL

# =========================



SIGNALS_FILE = "signals_log.csv"



if st.button("💾 Guardar señal"):

    nueva_senal = pd.DataFrame([{

        "fecha": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),

        "estrategia": estrategia,

        "decision": decision,

        "precio": price,

        "long_score": long_score,

        "short_score": short_score,

        "rsi_15m": rsi_15,

        "cuenta_usdt": account_usd,

        "riesgo_pct": risk_pct,

        "riesgo_usdt": risk_usd,

        "ganancia_tp_usdt": profit_usd,

        "entrada": entry,

        "sl": sl,

        "tp": tp,

        "rr": rr_target,

        "24h": t1d,

        "4h": t4,

        "1h": t1,

        "15m": t15,

        "5m": t5,

        "estructura": structure

    }])



    if os.path.exists(SIGNALS_FILE):

        historial = pd.read_csv(SIGNALS_FILE)

        historial = pd.concat([historial, nueva_senal], ignore_index=True)

    else:

        historial = nueva_senal



    historial.to_csv(SIGNALS_FILE, index=False)

    st.success("Señal guardada correctamente.")


# =========================



# CONFIG



# =========================

st.sidebar.divider()



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



if st.sidebar.button("🔄 Actualizar datos"):

    st.rerun()

SYMBOL = "BTC/USDT:USDT"



LIMIT = 300



st.sidebar.title("Configuración")



account_usd = st.sidebar.number_input("Cuenta USDT", min_value=10.0, value=500.0, step=10.0)



risk_pct = st.sidebar.number_input("Riesgo por operación %", min_value=0.1, max_value=5.0, value=1.0, step=0.1) / 100



leverage = st.sidebar.selectbox("Apalancamiento sugerido", [3, 5, 10, 20], index=1)



min_score = st.sidebar.slider("Score mínimo para operar", 1, 10, 7)



rr_target = st.sidebar.number_input("Riesgo/Beneficio mínimo", min_value=1.0, value=2.0, step=0.1)



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



    df = pd.DataFrame(data, columns=["time", "open", "high", "low", "close", "volume"])



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



    return df



def load_all_data():

    df_1d = add_indicators(get_ohlcv("1d"))
    


    df_4h = add_indicators(get_ohlcv("4h"))



    df_1h = add_indicators(get_ohlcv("1h"))



    df_15m = add_indicators(get_ohlcv("15m"))



    df_5m = add_indicators(get_ohlcv("5m"))

   

    return  df_1d, df_4h, df_1h, df_15m, df_5m



# =========================



# ANALISIS



# =========================



def trend_state(df):



    last = df.iloc[-1]



    if last["ema20"] > last["ema50"] > last["ema200"]:



        return "BULL"



    if last["ema20"] < last["ema50"] < last["ema200"]:



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



    levels = {



        "Máx día anterior": yesterday_df["high"].max(),



        "Mín día anterior": yesterday_df["low"].min(),



        "Máx Asia": asia["high"].max() if len(asia) else np.nan,



        "Mín Asia": asia["low"].min() if len(asia) else np.nan,



        "Máx Londres": london["high"].max() if len(london) else np.nan,



        "Mín Londres": london["low"].min() if len(london) else np.nan,



        "Máx NY": ny["high"].max() if len(ny) else np.nan,



        "Mín NY": ny["low"].min() if len(ny) else np.nan,



    }



    return levels



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



        highs = [v for v in levels.values() if not pd.isna(v) and v > price]



        if highs:



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



        lows = [v for v in levels.values() if not pd.isna(v) and v < price]



        if lows:



            score += 1



    return score





def final_decision(long_score, short_score, risk_pct, rr_target, structure, min_score, min_rr):



    score_ok = max(long_score, short_score) >= min_score

    risk_ok = risk_pct <= 1

    rr_ok = rr_target >= min_rr

    ruptura_ok = structure in ["BREAK_UP", "BREAK_DOWN"]



    if (

        long_score >= min_score

        and long_score > short_score

        and risk_ok

        and rr_ok

        and ruptura_ok

        and structure == "BREAK_UP"

    ):

        return "LONG"



    if (

        short_score >= min_score

        and short_score > long_score

        and risk_ok

        and rr_ok

        and ruptura_ok

        and structure == "BREAK_DOWN"

    ):

        return "SHORT"



    return "NO_OPERAR"



def technical_levels(direction, df_5m, entry):



    recent = df_5m.tail(30)



    atr = df_5m["atr"].iloc[-1]



    if pd.isna(atr):



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



def position_size(entry, sl):



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



# =========================



# APP



# =========================



st.title("BTC/USDT FUTUROS DASHBOARD")



st.caption("Sistema objetivo: tendencia + liquidez + score + riesgo. No es consejo financiero.")



try:



    df_1d, df_4h, df_1h, df_15m, df_5m = load_all_data()



    levels = liquidity_levels(df_15m)



    price = df_5m["close"].iloc[-1]



    t4 = trend_state(df_4h)



    t1 = trend_state(df_1h)



    t15 = trend_state(df_15m)



    t5 = trend_state(df_5m)



    rsi_15 = df_15m["rsi"].iloc[-1]



    rsi_label = rsi_state(rsi_15)



    structure = structure_state(df_5m)



    long_score = score_direction("LONG", df_4h, df_1h, df_15m, df_5m, levels)



    short_score = score_direction("SHORT", df_4h, df_1h, df_15m, df_5m, levels)

    #min_score = 5
    #min_rr = 2.0

    decision = final_decision(

    long_score,

    short_score,

    risk_pct,

    rr_target,

    structure,

    min_score,

    min_rr

)



    decision_calc = decision
    
    if decision == "NO_OPERAR":
        decision_calc = "LONG" if long_score >= short_score else "SHORT"

    st.write("decision_calc=", decision_calc)
    st.write("decision =", decision)
    
    sl, tp, risk_points = technical_levels(decision_calc, df_5m, price)


    btc_size, notional, risk_usd, margin_needed = position_size(price, sl)



    if decision == "LONG":



        st.success("🟢 LONG PERMITIDO")



    elif decision == "SHORT":



        st.error("🔴 SHORT PERMITIDO")



    else:



        st.warning("⚪ NO OPERAR")

    score_ok = max(long_score, short_score) >= min_score



    motivos = []







    motivos.append("")

    motivos.append(f"Long Score = {long_score}/10")

    motivos.append(f"Short Score = {short_score}/10")



    motivos.append("")

    motivos.append(f"Decisión = {decision}")



    motivo_texto = "\n".join(motivos)

    with st.expander("📌 Motivo de la decisión"):

        st.code(motivo_texto)

    col1, col2, col3, col4 = st.columns(4)



    col1.metric("Precio BTCUSDT", f"{price:,.2f}")



    col2.metric("Long Score", f"{long_score}/9")



    col3.metric("Short Score", f"{short_score}/9")



    col4.metric("RSI 15M", f"{rsi_15:.2f}", rsi_label)



    st.divider()



    c1, c2, c3, c4, c5, = st.columns(5)

    c1.metric("24H", trend_icon(t1))


    c2.metric("4H", trend_icon(t4))



    c3.metric("1H", trend_icon(t1))



    c4.metric("15M", trend_icon(t15))



    c5.metric("5M", trend_icon(t5))






    st.divider()

    profit_usd = risk_usd * rr_target if decision != "NO OPERAR" else 0

    profit_pct = (profit_usd / account_usd) * 100

    loss_pct = (risk_usd / account_usd) * 100


    g1, g2, g3, g4, g5, g6 = st.columns(6)



    g1.metric("Cuenta", f"{account_usd:.2f} USDT")



    g2.metric("Riesgo", f"{risk_usd:.2f} USDT")



    g3.metric("Ganancia TP", f"+{profit_usd:.2f} USDT")



    g4.metric("Tamaño", f"{btc_size:.5f} BTC")



    g5.metric("Nocional", f"{notional:.2f} USDT")
    

    g6.metric("Margen", f"{margin_needed:.2f} USDT")



    



    r1, r2, r3 = st.columns(3)



    r1.metric("Entrada", f"{price:,.2f}")



    r2.metric("SL técnico", f"{sl:,.2f}")



    r3.metric("TP automático", f"{tp:,.2f}")



    



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



    for name, value in levels.items():



        if not pd.isna(value):



            fig.add_hline(



                y=value,



                line_dash="dot",



                annotation_text=name,



                annotation_position="right"



            )



    if decision != "NO_OPERAR":



        fig.add_hline(y=price, line_color="blue", annotation_text="Entrada")



        fig.add_hline(y=sl, line_color="red", annotation_text="SL")



        fig.add_hline(y=tp, line_color="green", annotation_text="TP")



    fig.update_layout(



        template="plotly_dark",



        height=700,



        xaxis_rangeslider_visible=False,



        title="BTCUSDT 15M - Velas + EMAs + Liquidez",



        margin=dict(l=20, r=20, t=50, b=20)



    )



    st.plotly_chart(fig, use_container_width=True)



    st.divider()

    # =========================

    # HISTORIAL DE SEÑALES

    # =========================



    st.divider()

    st.subheader("📊 Historial de señales")



    if os.path.exists(SIGNALS_FILE):

        historial = pd.read_csv(SIGNALS_FILE)

        st.dataframe(historial.tail(20), use_container_width=True)



        st.download_button(

            "⬇️ Descargar historial CSV",

            data=historial.to_csv(index=False),

            file_name="signals_log.csv",

            mime="text/csv"

        )

    else:

        st.info("Todavía no hay señales guardadas.")

        st.subheader("Reglas del sistema")

        

        st.write("""



        - Score menor a 7 = NO OPERAR.



        - Riesgo/beneficio menor a 2 = NO OPERAR.



        - Riesgo mayor a 1% = NO OPERAR.



        - Máximo 2 operaciones por día.



        - No mover el SL.



        - No operar para recuperar pérdidas.



        - 4H y 1H mandan el contexto.



        - 15M da la estructura de sesión.



        - 5M sirve para ejecutar.



        """)



    st.caption(f"Última actualización local: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")



except Exception as e:



    st.error("Hubo un error cargando el dashboard.")



    st.exception(e)