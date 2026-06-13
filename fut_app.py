
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
def get_ohlcv(timeframe, limit=LIMIT):
    data = exchange.fetch_ohlcv(SYMBOL, timeframe=timeframe, limit=limit)
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

    df["body"] = (df["close"] - df["open"]).abs()
    df["upper_wick"] = df["high"] - df[["open", "close"]].max(axis=1)
    df["lower_wick"] = df[["open", "close"]].min(axis=1) - df["low"]
    return df


def resample_ohlcv(df, rule):
    return df.resample(rule, on="time").agg({
        "open": "first",
        "high": "max",
        "low": "min",
        "close": "last",
        "volume": "sum"
    }).dropna().reset_index()


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

def trend_state(df):
    if df.empty or len(df) < 200:
        return "NEUTRAL"
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
    if pd.isna(value):
        return "—"
    if value < 30:
        return "SOBREVENTA"
    if value > 70:
        return "SOBRECOMPRA"
    if 45 <= value <= 60:
        return "OK"
    return "NEUTRO"


def structure_state(df):
    recent = df.tail(20)
    if len(recent) < 20:
        return "SIN_RUPTURA"
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
    clean_levels = {k: v for k, v in levels.items() if not pd.isna(v)}
    if direction == "LONG":
        targets = {k: v for k, v in clean_levels.items() if v > price}
    else:
        targets = {k: v for k, v in clean_levels.items() if v < price}
    if not targets:
        return None, np.nan, np.nan
    name, level = min(targets.items(), key=lambda item: abs(item[1] - price))
    return name, level, abs(level - price)


def detect_market_intention(price, df_4h, df_1h, df_15m, levels):
    t4 = trend_state(df_4h)
    t1 = trend_state(df_1h)
    rsi = df_15m["rsi"].iloc[-1]
    ema20 = df_15m["ema20"].iloc[-1]
    ema50 = df_15m["ema50"].iloc[-1]
    ema200 = df_15m["ema200"].iloc[-1]
    atr = df_15m["atr"].iloc[-1]
    _, _, upside_distance = nearest_liquidity(price, levels, "LONG")
    _, _, downside_distance = nearest_liquidity(price, levels, "SHORT")
    near_upside_liquidity = not pd.isna(upside_distance) and not pd.isna(atr) and upside_distance <= atr * 0.7
    near_downside_liquidity = not pd.isna(downside_distance) and not pd.isna(atr) and downside_distance <= atr * 0.7
    if t4 == "BULL" and t1 == "BULL" and price > ema20 > ema50 > ema200:
        if near_upside_liquidity:
            return "ALCISTA CON LIQUIDEZ SUPERIOR CERCA", "LONG_CON_CUIDADO"
        return "TENDENCIA ALCISTA", "LONG"
    if t4 == "BEAR" and t1 == "BEAR" and price < ema20 < ema50 < ema200:
        if near_downside_liquidity:
            return "BAJISTA CON LIQUIDEZ INFERIOR CERCA", "SHORT_CON_CUIDADO"
        return "TENDENCIA BAJISTA", "SHORT"
    if not pd.isna(rsi) and 45 <= rsi <= 55:
        return "RANGO / COMPRESIÓN", "NEUTRAL"
    return "SIN INTENCIÓN CLARA", "NEUTRAL"


def score_direction(direction, df_4h, df_1h, df_15m, df_5m, levels):
    score = 0
    t4 = trend_state(df_4h)
    t1 = trend_state(df_1h)
    t15 = trend_state(df_15m)
    t5 = trend_state(df_5m)
    rsi_value = df_15m["rsi"].iloc[-1]
    structure = structure_state(df_5m)
    price = df_5m["close"].iloc[-1]
    liquidity_name, _, _ = nearest_liquidity(price, levels, direction)
    if direction == "LONG":
        if t4 == "BULL": score += 2
        if t1 == "BULL": score += 2
        if t15 == "BULL": score += 1
        if t5 == "BULL": score += 1
        if not pd.isna(rsi_value) and rsi_value > 50: score += 1
        if structure == "BREAK_UP": score += 1
        if liquidity_name: score += 1
    if direction == "SHORT":
        if t4 == "BEAR": score += 2
        if t1 == "BEAR": score += 2
        if t15 == "BEAR": score += 1
        if t5 == "BEAR": score += 1
        if not pd.isna(rsi_value) and rsi_value < 50: score += 1
        if structure == "BREAK_DOWN": score += 1
        if liquidity_name: score += 1
    return score


def detect_sweep_direction(df_5m, levels):
    last = df_5m.iloc[-1]
    price = last["close"]
    upper_name, upper_level, _ = nearest_liquidity(price, levels, "LONG")
    lower_name, lower_level, _ = nearest_liquidity(price, levels, "SHORT")
    if upper_name and last["high"] > upper_level and last["close"] < upper_level:
        return "SHORT"
    if lower_name and last["low"] < lower_level and last["close"] > lower_level:
        return "LONG"
    return None


def choose_candidate_direction(estrategia, long_score, short_score, t1d, t4, structure, price, df_15m, df_5m, levels):
    rsi = df_15m["rsi"].iloc[-1]
    sweep_direction = detect_sweep_direction(df_5m, levels)
    if estrategia == "Reversión Extrema":
        if not pd.isna(rsi) and rsi >= 65:
            return "SHORT"
        if not pd.isna(rsi) and rsi <= 35:
            return "LONG"
    if estrategia == "Sweep de Liquidez" and sweep_direction:
        return sweep_direction
    if estrategia == "Ruptura de Estructura":
        if structure == "BREAK_UP":
            return "LONG"
        if structure == "BREAK_DOWN":
            return "SHORT"
    if long_score > short_score:
        return "LONG"
    if short_score > long_score:
        return "SHORT"
    if structure == "BREAK_UP":
        return "LONG"
    if structure == "BREAK_DOWN":
        return "SHORT"
    ema200 = df_15m["ema200"].iloc[-1]
    if t1d == "BEAR" or t4 == "BEAR":
        return "SHORT"
    if t1d == "BULL" or t4 == "BULL":
        return "LONG"
    if price >= ema200:
        return "LONG"
    return "SHORT"


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


def strategy_filter(estrategia, direction, df_15m, df_5m, levels, structure, market_bias):
    motivos = []
    price = df_5m["close"].iloc[-1]
    last = df_5m.iloc[-1]
    ema50 = df_15m["ema50"].iloc[-1]
    atr = df_15m["atr"].iloc[-1]
    rsi = df_15m["rsi"].iloc[-1]
    sweep_direction = detect_sweep_direction(df_5m, levels)
    if estrategia == "Tendencia + Liquidez":
        if direction == "LONG" and market_bias == "SHORT":
            motivos.append("Estrategia Tendencia + Liquidez: mercado contradice LONG.")
        if direction == "SHORT" and market_bias == "LONG":
            motivos.append("Estrategia Tendencia + Liquidez: mercado contradice SHORT.")
    elif estrategia == "Pullback EMA50":
        distancia_ema50 = abs(price - ema50)
        if not pd.isna(atr) and distancia_ema50 > atr * 0.8:
            motivos.append("Pullback EMA50: el precio está lejos de la EMA50.")
        if direction == "LONG" and price < ema50:
            motivos.append("Pullback EMA50: para LONG el precio debe estar sobre EMA50.")
        if direction == "SHORT" and price > ema50:
            motivos.append("Pullback EMA50: para SHORT el precio debe estar bajo EMA50.")
    elif estrategia == "Sweep de Liquidez":
        if sweep_direction is None:
            motivos.append("Sweep de Liquidez: no hay barrida clara de liquidez.")
        elif sweep_direction != direction:
            motivos.append(f"Sweep de Liquidez: la barrida favorece {sweep_direction}, no {direction}.")
    elif estrategia == "Ruptura de Estructura":
        if direction == "LONG" and structure != "BREAK_UP":
            motivos.append("Ruptura de Estructura: falta ruptura alcista.")
        if direction == "SHORT" and structure != "BREAK_DOWN":
            motivos.append("Ruptura de Estructura: falta ruptura bajista.")
    elif estrategia == "Reversión Extrema":
        if direction == "LONG":
            if pd.isna(rsi) or rsi > 35:
                motivos.append("Reversión Extrema: RSI no está en sobreventa para LONG.")
            if last["lower_wick"] <= last["body"]:
                motivos.append("Reversión Extrema: falta mecha inferior de rechazo.")
        if direction == "SHORT":
            if pd.isna(rsi) or rsi < 65:
                motivos.append("Reversión Extrema: RSI no está en sobrecompra para SHORT.")
            if last["upper_wick"] <= last["body"]:
                motivos.append("Reversión Extrema: falta mecha superior de rechazo.")
    return motivos


def setup_quality(long_score, short_score, direction, rr_real, risk_points, atr_15m, trade_valid):
    base_score = long_score if direction == "LONG" else short_score
    quality_score = int(round((base_score / 9) * 10))
    if not pd.isna(rr_real) and rr_real >= 2:
        quality_score += 1
    if not pd.isna(risk_points) and not pd.isna(atr_15m):
        if risk_points <= atr_15m * 2:
            quality_score += 1
        else:
            quality_score -= 1
    if not trade_valid:
        quality_score = min(quality_score, 4)
    quality_score = max(1, min(10, quality_score))
    if quality_score <= 3:
        label = "MALA"
    elif quality_score <= 5:
        label = "REGULAR"
    elif quality_score <= 7:
        label = "BUENA"
    else:
        label = "EXCELENTE"
    return quality_score, label


def is_allowed_trading_time(ts, use_filter=True, avoid_weekends=True):
    if pd.isna(ts):
        return False
    if avoid_weekends and ts.weekday() >= 5:
        return False
    if not use_filter:
        return True
    hour = ts.hour
    return (7 <= hour < 10) or (13 <= hour < 16)


def validate_trade(estrategia, direction, long_score, short_score, min_score, risk_pct, rr_real, min_rr,
                   risk_points, atr_15m, market_bias, structure, price, levels, max_atr_multiplier,
                   df_15m, df_5m, use_time_filter=False, avoid_weekends_filter=False):
    motivos = []
    if direction is None:
        motivos.append("No hay dirección dominante clara.")
        return False, motivos
    if direction == "LONG":
        if long_score < min_score:
            motivos.append(f"Long Score insuficiente: {long_score}/{min_score}.")
        if long_score <= short_score:
            motivos.append("Long no supera claramente al Short Score.")
    if direction == "SHORT":
        if short_score < min_score:
            motivos.append(f"Short Score insuficiente: {short_score}/{min_score}.")
        if short_score <= long_score:
            motivos.append("Short no supera claramente al Long Score.")
    if risk_pct > 0.01:
        motivos.append("Riesgo mayor al 1% por operación.")
    if pd.isna(rr_real) or rr_real < min_rr:
        motivos.append(f"RR real insuficiente. Mínimo requerido: {min_rr}.")
    if not pd.isna(risk_points) and not pd.isna(atr_15m):
        if risk_points > atr_15m * max_atr_multiplier:
            motivos.append("SL demasiado lejos respecto al ATR.")
    nearest_name, _, nearest_distance = nearest_liquidity(price, levels, direction)
    if nearest_name and not pd.isna(nearest_distance) and not pd.isna(atr_15m):
        if nearest_distance < atr_15m * 0.35:
            motivos.append(f"Entrada demasiado cerca de liquidez: {nearest_name}.")
    if not is_allowed_trading_time(df_5m["time"].iloc[-1], use_time_filter, avoid_weekends_filter):
        motivos.append("Filtro horario: fuera de Londres / NY o fin de semana.")
    motivos.extend(strategy_filter(estrategia, direction, df_15m, df_5m, levels, structure, market_bias))
    return len(motivos) == 0, motivos


def format_number(value, decimals=2):
    if pd.isna(value):
        return "—"
    return f"{value:,.{decimals}f}"


# =========================
# BACKTEST Y VALIDACION
# =========================

def outcome_from_future(future_df, direction, sl, tp, rr_value):
    if future_df.empty or pd.isna(sl) or pd.isna(tp):
        return "SIN_DATOS", 0.0
    for _, row in future_df.iterrows():
        if direction == "LONG":
            hit_sl = row["low"] <= sl
            hit_tp = row["high"] >= tp
        else:
            hit_sl = row["high"] >= sl
            hit_tp = row["low"] <= tp
        if hit_sl and hit_tp:
            return "SL", -1.0
        if hit_tp:
            return "TP", rr_value if not pd.isna(rr_value) else rr_target
        if hit_sl:
            return "SL", -1.0
    return "NINGUNO", 0.0


def performance_stats(results):
    if results.empty:
        return {"operaciones": 0, "winrate": 0, "profit_factor": 0, "drawdown": 0, "expectancy": 0, "rr_promedio": 0}
    closed = results[results["resultado"].isin(["TP", "SL"])].copy()
    if closed.empty:
        return {"operaciones": 0, "winrate": 0, "profit_factor": 0, "drawdown": 0, "expectancy": 0, "rr_promedio": 0}
    closed["r_multiple"] = pd.to_numeric(closed["r_multiple"], errors="coerce").fillna(0)
    wins = closed[closed["resultado"] == "TP"]
    losses = closed[closed["resultado"] == "SL"]
    gross_profit = wins["r_multiple"].sum()
    gross_loss = abs(losses["r_multiple"].sum())
    profit_factor = gross_profit / gross_loss if gross_loss > 0 else np.inf
    equity = closed["r_multiple"].cumsum()
    peak = equity.cummax()
    drawdown = (equity - peak).min()
    rr_promedio = wins["r_multiple"].mean() if len(wins) else 0
    return {
        "operaciones": len(closed),
        "winrate": (len(wins) / len(closed)) * 100,
        "profit_factor": profit_factor,
        "drawdown": drawdown,
        "expectancy": closed["r_multiple"].mean(),
        "rr_promedio": rr_promedio,
    }


@st.cache_data(ttl=300)
def run_simple_backtest(timeframe, period_label, estrategia, min_score, rr_target, min_rr, max_atr_multiplier, use_time_filter, avoid_weekends_filter):
    months_map = {"3 meses": 3, "6 meses": 6, "1 año": 12}
    df = add_indicators(get_ohlcv(timeframe, limit=BACKTEST_LIMIT))
    if df.empty or len(df) < 260:
        return pd.DataFrame(), {}
    cutoff = df["time"].max() - pd.DateOffset(months=months_map[period_label])
    df = df[df["time"] >= cutoff].reset_index(drop=True)
    rows = []
    step = 4 if timeframe == "15m" else 12
    horizon = 96 if timeframe == "15m" else 288
    for i in range(220, len(df) - horizon, step):
        hist = df.iloc[:i + 1].copy()
        df_5_bt = hist
        df_15_bt = hist if timeframe == "15m" else add_indicators(resample_ohlcv(hist, "15min"))
        df_1h_bt = add_indicators(resample_ohlcv(hist, "1h"))
        df_4h_bt = add_indicators(resample_ohlcv(hist, "4h"))
        df_1d_bt = add_indicators(resample_ohlcv(hist, "1d"))
        if len(df_1h_bt) < 210 or len(df_4h_bt) < 60 or len(df_15_bt) < 210 or len(df_1d_bt) < 2:
            continue
        levels_bt = liquidity_levels(df_15_bt)
        price_bt = df_5_bt["close"].iloc[-1]
        structure_bt = structure_state(df_5_bt)
        long_score_bt = score_direction("LONG", df_4h_bt, df_1h_bt, df_15_bt, df_5_bt, levels_bt)
        short_score_bt = score_direction("SHORT", df_4h_bt, df_1h_bt, df_15_bt, df_5_bt, levels_bt)
        escenario_bt, market_bias_bt = detect_market_intention(price_bt, df_4h_bt, df_1h_bt, df_15_bt, levels_bt)
        direction_bt = choose_candidate_direction(estrategia, long_score_bt, short_score_bt, trend_state(df_1d_bt), trend_state(df_4h_bt), structure_bt, price_bt, df_15_bt, df_5_bt, levels_bt)
        sl_bt, tp_bt, risk_points_bt = technical_levels(direction_bt, df_5_bt, price_bt, rr_target)
        rr_bt = calculate_rr(price_bt, sl_bt, tp_bt, direction_bt)
        valid_bt, motivos_bt = validate_trade(
            estrategia, direction_bt, long_score_bt, short_score_bt, min_score, 0.01, rr_bt, min_rr,
            risk_points_bt, df_15_bt["atr"].iloc[-1], market_bias_bt, structure_bt, price_bt,
            levels_bt, max_atr_multiplier, df_15_bt, df_5_bt, use_time_filter, avoid_weekends_filter
        )
        if not valid_bt:
            continue
        future = df.iloc[i + 1:i + 1 + horizon]
        result, r_mult = outcome_from_future(future, direction_bt, sl_bt, tp_bt, rr_bt)
        rows.append({
            "fecha": df_5_bt["time"].iloc[-1],
            "direccion": direction_bt,
            "entrada": price_bt,
            "sl": sl_bt,
            "tp": tp_bt,
            "rr": rr_bt,
            "long_score": long_score_bt,
            "short_score": short_score_bt,
            "resultado": result,
            "r_multiple": r_mult,
            "escenario": escenario_bt,
            "motivos": " | ".join(motivos_bt)
        })
    res = pd.DataFrame(rows)
    return res, performance_stats(res)


def validate_saved_signals(historial, current_df_5m, hours_after=24):
    if historial.empty:
        return historial
    h = historial.copy()
    for col in ["resultado", "r_multiple", "validado_hasta"]:
        if col not in h.columns:
            h[col] = np.nan
    now_utc = current_df_5m["time"].max()
    for idx, row in h.iterrows():
        if str(row.get("resultado", "nan")) in ["TP", "SL", "NINGUNO", "NO_OPERAR"]:
            continue
        try:
            fecha = pd.to_datetime(row["fecha"], utc=True)
        except Exception:
            continue
        if now_utc < fecha + pd.Timedelta(hours=hours_after):
            continue
        direction = row.get("direccion_calculada", row.get("decision", ""))
        if direction not in ["LONG", "SHORT"]:
            h.at[idx, "resultado"] = "NO_OPERAR"
            h.at[idx, "r_multiple"] = 0.0
            continue
        future = current_df_5m[(current_df_5m["time"] > fecha) & (current_df_5m["time"] <= fecha + pd.Timedelta(hours=hours_after))]
        rr_value = pd.to_numeric(row.get("rr_real", np.nan), errors="coerce")
        result, r_mult = outcome_from_future(future, direction, float(row["sl"]), float(row["tp"]), rr_value)
        h.at[idx, "resultado"] = result
        h.at[idx, "r_multiple"] = r_mult
        h.at[idx, "validado_hasta"] = (fecha + pd.Timedelta(hours=hours_after)).strftime("%Y-%m-%d %H:%M:%S")
    return h


# =========================
# APP
# =========================

st.title("BTC/USDT FUTUROS DASHBOARD PRO")
st.caption("Sistema objetivo: tendencia + liquidez + estructura + score + riesgo + backtesting. No es consejo financiero.")

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
    escenario, market_bias = detect_market_intention(price, df_4h, df_1h, df_15m, levels)
    candidate_direction = choose_candidate_direction(estrategia, long_score, short_score, t1d, t4, structure, price, df_15m, df_5m, levels)
    sl_calc, tp_calc, risk_points_calc = technical_levels(candidate_direction, df_5m, price, rr_target)
    tp_distance_calc = abs(tp_calc - price) if not pd.isna(tp_calc) else np.nan
    tp_atr_multiple = (
        tp_distance_calc / atr_15m
        if not pd.isna(tp_distance_calc) and not pd.isna(atr_15m) and atr_15m > 0
        else np.nan
    )
    rr_real = calculate_rr(price, sl_calc, tp_calc, candidate_direction)
    trade_valid, motivos_bloqueo = validate_trade(
        estrategia, candidate_direction, long_score, short_score, min_score, risk_pct, rr_real, min_rr,
        risk_points_calc, atr_15m, market_bias, structure, price, levels, max_atr_multiplier,
        df_15m, df_5m, filter_hours, avoid_weekends
    )
    decision = candidate_direction if trade_valid else "NO_OPERAR"
    btc_size, notional, risk_usd, margin_needed = position_size(price, sl_calc, account_usd, risk_pct, leverage)
    profit_usd = risk_usd * rr_target
    profit_pct = (profit_usd / account_usd) * 100
    loss_pct = (risk_usd / account_usd) * 100
    quality_score, quality_label = setup_quality(long_score, short_score, candidate_direction, rr_real, risk_points_calc, atr_15m, trade_valid)

    if decision == "LONG":
        st.success("🟢 LONG PERMITIDO")
    elif decision == "SHORT":
        st.error("🔴 SHORT PERMITIDO")
    else:
        st.warning(f"⚪ NO OPERAR | Escenario calculado: {candidate_direction}")
    st.markdown(f"## Calidad del setup: {quality_label} · {quality_score}/10")
    st.divider()

    q1, q2, q3, q4 = st.columns(4)
    q1.metric("Calidad del setup", quality_label, f"{quality_score}/10")
    q2.metric(
        "Distancia al SL",
        f"{risk_points_calc:,.0f} pts" if not pd.isna(risk_points_calc) else "—",
        f"ATR 15M: {atr_15m:,.0f} pts" if not pd.isna(atr_15m) else "—"
    )
    q3.metric("Setup calculado", candidate_direction, f"RR: {rr_real:.2f}" if not pd.isna(rr_real) else "—")
    q4.metric(
        "Distancia al TP",
        f"{tp_distance_calc:,.0f} pts" if not pd.isna(tp_distance_calc) else "—",
        f"{tp_atr_multiple:.2f} ATR" if not pd.isna(tp_atr_multiple) else "—"
    )

    with st.expander("📌 Motivo de la decisión", expanded=True):
        st.write(f"**Estrategia activa:** {estrategia}")
        st.write(f"**Escenario:** {escenario}")
        st.write(f"**Dirección calculada:** {candidate_direction}")
        st.write(f"**Estructura 5M:** {structure}")
        st.write(f"**Long Score:** {long_score}/9")
        st.write(f"**Short Score:** {short_score}/9")
        st.write(f"**RR real:** {format_number(rr_real, 2)}")
        st.write(f"**ATR 15M:** {format_number(atr_15m, 2)} puntos")
        st.write(f"**Distancia SL:** {format_number(risk_points_calc, 2)} puntos")
        st.write(f"**Distancia TP:** {format_number(tp_distance_calc, 2)} puntos")
        st.write(f"**TP en ATR:** {format_number(tp_atr_multiple, 2)} ATR")
        if trade_valid:
            st.success(f"Setup válido para estrategia: {estrategia}.")
        else:
            for motivo in motivos_bloqueo:
                st.warning(motivo)

    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Precio BTCUSDT", format_number(price, 2))
    col2.metric("Long Score", f"{long_score}/9")
    col3.metric("Short Score", f"{short_score}/9")
    col4.metric("RSI 15M", f"{rsi_15:.2f}" if not pd.isna(rsi_15) else "—", rsi_label)
    st.divider()

    c1, c2, c3, c4, c5 = st.columns(5)
    c1.metric("24H", trend_icon(t1d))
    c2.metric("4H", trend_icon(t4))
    c3.metric("1H", trend_icon(t1))
    c4.metric("15M", trend_icon(t15))
    c5.metric("5M", trend_icon(t5))
    st.divider()

    g1, g2, g3, g4, g5, g6 = st.columns(6)
    g1.metric("Cuenta", f"{account_usd:.0f} USDT")
    g2.metric("Riesgo", f"{risk_usd:.0f} USDT", f"{loss_pct:.2f}%")
    g3.metric("Ganancia TP", f"+{profit_usd:.0f} USDT", f"{profit_pct:.2f}%")
    g4.metric("Tamaño", f"{btc_size:.4f} BTC")
    g5.metric("Nocional", f"{notional:.0f} USDT")
    g6.metric("Margen", f"{margin_needed:.0f} USDT")

    r1, r2, r3, r4, r5, r6 = st.columns(6)
    r1.metric("Entrada", f"{price:,.0f}")
    r2.metric("SL técnico", f"{sl_calc:,.0f}" if not pd.isna(sl_calc) else "—")
    r3.metric("TP automático", f"{tp_calc:,.0f}" if not pd.isna(tp_calc) else "—")
    r4.metric("Distancia SL", f"{risk_points_calc:,.0f} pts" if not pd.isna(risk_points_calc) else "—")
    r5.metric("Distancia TP", f"{tp_distance_calc:,.0f} pts" if not pd.isna(tp_distance_calc) else "—")
    r6.metric("RR real", f"{rr_real:.2f}" if not pd.isna(rr_real) else "—")
    st.divider()

    chart_df = df_15m.tail(150).copy()
    fig = go.Figure()
    fig.add_trace(go.Candlestick(x=chart_df["time"], open=chart_df["open"], high=chart_df["high"], low=chart_df["low"], close=chart_df["close"], name="BTCUSDT"))
    fig.add_trace(go.Scatter(x=chart_df["time"], y=chart_df["ema20"], mode="lines", name="EMA 20", line=dict(color="#ff6b57", width=2)))
    fig.add_trace(go.Scatter(x=chart_df["time"], y=chart_df["ema50"], mode="lines", name="EMA 50", line=dict(color="#18c29c", width=2)))
    fig.add_trace(go.Scatter(x=chart_df["time"], y=chart_df["ema200"], mode="lines", name="EMA 200", line=dict(color="#9b5cff", width=2)))
    for name, value in levels.items():
        if not pd.isna(value):
            fig.add_hline(y=value, line_dash="dot", line_color="gray", annotation_text=name, annotation_position="right")
    should_show_trade_levels = trade_valid or show_levels_when_no_trade
    if should_show_trade_levels and not pd.isna(sl_calc):
        fig.add_hline(y=sl_calc, line_color="red", line_width=3, annotation_text="SL")
    if should_show_trade_levels and not pd.isna(tp_calc):
        fig.add_hline(y=tp_calc, line_color="green", line_width=3, annotation_text="TP")
    fig.add_hline(y=price, line_color="black", line_width=3, annotation_text="Entrada")
    fig.update_layout(template="plotly_white", height=700, xaxis_rangeslider_visible=False, title="BTCUSDT 15M - Velas + EMAs + Liquidez + SL/TP", margin=dict(l=20, r=20, t=50, b=20))
    st.plotly_chart(fig, use_container_width=True)
    st.divider()

    st.subheader("🧪 Backtesting automático")
    with st.spinner("Calculando backtest..."):
        bt_results, bt_stats = run_simple_backtest(backtest_tf, backtest_period, estrategia, min_score, rr_target, min_rr, max_atr_multiplier, filter_hours, avoid_weekends)
    b1, b2, b3, b4, b5 = st.columns(5)
    b1.metric("Operaciones", int(bt_stats.get("operaciones", 0)))
    b2.metric("Winrate", f"{bt_stats.get('winrate', 0):.1f}%")
    pf = bt_stats.get("profit_factor", 0)
    b3.metric("Profit Factor", "∞" if pf == np.inf else f"{pf:.2f}")
    b4.metric("Drawdown", f"{bt_stats.get('drawdown', 0):.2f}R")
    b5.metric("Expectativa", f"{bt_stats.get('expectancy', 0):+.2f}R")

    if not bt_results.empty:
        equity = bt_results[bt_results["resultado"].isin(["TP", "SL"])].copy()
        equity["equity_r"] = equity["r_multiple"].cumsum()
        eq_fig = go.Figure()
        eq_fig.add_trace(go.Scatter(x=equity["fecha"], y=equity["equity_r"], mode="lines+markers", name="Equity R"))
        eq_fig.update_layout(template="plotly_white", height=350, title="Curva de equity en R", margin=dict(l=20, r=20, t=50, b=20))
        st.plotly_chart(eq_fig, use_container_width=True)
        st.dataframe(bt_results.tail(50), use_container_width=True)
        st.download_button("⬇️ Descargar backtest CSV", data=bt_results.to_csv(index=False), file_name="backtest_results.csv", mime="text/csv")
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

    st.subheader("⏰ Filtro horario")
    st.write("Activo" if filter_hours else "Inactivo")
    st.caption("Filtro usado: Londres 07:00-10:00 UTC y NY 13:00-16:00 UTC. Fin de semana bloqueado si está activado.")
    st.divider()

    if st.button("💾 Guardar señal"):
        nueva_senal = pd.DataFrame([{
            "fecha": datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S"),
            "estrategia": estrategia,
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
            "distancia_sl_pts": risk_points_calc,
            "distancia_tp_pts": tp_distance_calc,
            "tp_atr_multiple": tp_atr_multiple,
            "cuenta_usdt": account_usd,
            "riesgo_pct": risk_pct_input,
            "riesgo_usdt": risk_usd,
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
        }])
        if os.path.exists(SIGNALS_FILE):
            historial = pd.read_csv(SIGNALS_FILE)
            historial = pd.concat([historial, nueva_senal], ignore_index=True)
        else:
            historial = nueva_senal
        historial.to_csv(SIGNALS_FILE, index=False)
        st.success("Señal guardada correctamente.")

    st.subheader("📊 Historial de señales")
    if os.path.exists(SIGNALS_FILE):
        historial = pd.read_csv(SIGNALS_FILE)
        historial = validate_saved_signals(historial, df_5m, validate_after_hours)
        historial.to_csv(SIGNALS_FILE, index=False)
        stats_hist = performance_stats(historial) if "resultado" in historial.columns else {}
        h1, h2, h3, h4 = st.columns(4)
        h1.metric("Señales validadas", int(stats_hist.get("operaciones", 0)))
        h2.metric("Winrate real", f"{stats_hist.get('winrate', 0):.1f}%")
        h3.metric("PF real", "∞" if stats_hist.get("profit_factor", 0) == np.inf else f"{stats_hist.get('profit_factor', 0):.2f}")
        h4.metric("Expectativa real", f"{stats_hist.get('expectancy', 0):+.2f}R")
        st.dataframe(historial.tail(30), use_container_width=True)
        st.download_button("⬇️ Descargar historial CSV", data=historial.to_csv(index=False), file_name="signals_log.csv", mime="text/csv")
    else:
        st.info("Todavía no hay señales guardadas.")

    with st.expander("📘 Reglas del sistema"):
        st.write("""
        - Cada estrategia tiene filtros propios.
        - Tendencia + Liquidez valida dirección contra intención de mercado.
        - Pullback EMA50 exige cercanía a EMA50.
        - Sweep de Liquidez exige barrida real de liquidez.
        - Ruptura de Estructura exige BREAK_UP o BREAK_DOWN.
        - Reversión Extrema exige RSI extremo y mecha de rechazo.
        - Score menor al mínimo configurado = NO OPERAR.
        - RR real menor al mínimo configurado = NO OPERAR.
        - Riesgo mayor al 1% = NO OPERAR.
        - Distancia al TP mide si el objetivo es realista respecto al ATR.
        - Filtro horario opcional: Londres / NY.
        - Validación posterior: TP, SL o NINGUNO después de las horas configuradas.
        - Backtest simple: evalúa señales pasadas y mide operaciones, winrate, profit factor, drawdown y expectativa.
        """)

    st.caption(f"Última actualización local: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

except Exception as e:
    st.error("Hubo un error cargando el dashboard.")
    st.exception(e)
