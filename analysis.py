# =========================
# FVG / ANALISIS
# =========================
def detect_fvg_zones(df, min_atr_mult=0.20, lookback=120, trend_filter=None):
    """
    FVG inteligente:
    - Detecta bullish/bearish FVG.
    - Filtra por tamaño mínimo en ATR.
    - Calcula distancia al precio.
    - Marca mitigación.
    - Asigna score profesional.
    """
    if df is None or df.empty or len(df) < 20:
        return pd.DataFrame()
    d = df.tail(lookback).copy().reset_index(drop=True)
    zones = []
    current_price = float(d["close"].iloc[-1])
    for i in range(2, len(d)):
        c0 = d.iloc[i - 2]
        c2 = d.iloc[i]
        atr = safe_float(d["atr"].iloc[i], np.nan)
        if pd.isna(atr) or atr <= 0:
            continue
        min_gap = atr * min_atr_mult
        bull_gap = c2["low"] - c0["high"]
        bear_gap = c0["low"] - c2["high"]
        # Bullish FVG
        if bull_gap > min_gap:
            low = float(c0["high"])
            high = float(c2["low"])
            mid = (low + high) / 2
            gap_pts = high - low
            gap_atr = gap_pts / atr
            distance_pts = 0 if low <= current_price <= high else min(abs(current_price - low), abs(current_price - high))
            distance_atr = distance_pts / atr
            zones.append({
                "tipo": "BULLISH_FVG",
                "direction": "LONG",
                "time": c2["time"],
                "x0": c0["time"],
                "x1": c2["time"],
                "low": low,
                "high": high,
                "mid": mid,
                "gap_pts": gap_pts,
                "gap_atr": gap_atr,
                "distance_pts": distance_pts,
                "distance_atr": distance_atr,
                "mitigated": False,
                "score": 0,
                "calidad": "",
                "motivo": "",
            })
        # Bearish FVG
        if bear_gap > min_gap:
            low = float(c2["high"])
            high = float(c0["low"])
            mid = (low + high) / 2
            gap_pts = high - low
            gap_atr = gap_pts / atr
            distance_pts = 0 if low <= current_price <= high else min(abs(current_price - low), abs(current_price - high))
            distance_atr = distance_pts / atr
            zones.append({
                "tipo": "BEARISH_FVG",
                "direction": "SHORT",
                "time": c2["time"],
                "x0": c0["time"],
                "x1": c2["time"],
                "low": low,
                "high": high,
                "mid": mid,
                "gap_pts": gap_pts,
                "gap_atr": gap_atr,
                "distance_pts": distance_pts,
                "distance_atr": distance_atr,
                "mitigated": False,
                "score": 0,
                "calidad": "",
                "motivo": "",
            })
    out = pd.DataFrame(zones)
    if out.empty:
        return out
    # Mitigación
    for idx, z in out.iterrows():
        future = d[d["time"] > z["time"]]
        if future.empty:
            continue
        if z["direction"] == "LONG":
            mitigated = (future["low"] <= z["mid"]).any()
        else:
            mitigated = (future["high"] >= z["mid"]).any()
        out.at[idx, "mitigated"] = bool(mitigated)
    # Score inteligente
    for idx, z in out.iterrows():
        score = 0
        motivos = []
        # Tamaño
        if z["gap_atr"] >= 0.80:
            score += 30
            motivos.append("FVG grande")
        elif z["gap_atr"] >= 0.40:
            score += 22
            motivos.append("FVG medio")
        elif z["gap_atr"] >= min_atr_mult:
            score += 12
            motivos.append("FVG válido")
        # Distancia
        if z["distance_atr"] == 0:
            score += 25
            motivos.append("Precio dentro del FVG")
        elif z["distance_atr"] <= 0.75:
            score += 20
            motivos.append("FVG muy cercano")
        elif z["distance_atr"] <= 1.50:
            score += 12
            motivos.append("FVG cercano")
        else:
            motivos.append("FVG lejano")
        # Mitigación
        if not bool(z["mitigated"]):
            score += 20
            motivos.append("FVG abierto")
        else:
            score -= 15
            motivos.append("FVG mitigado")
        # Tendencia
        if trend_filter is not None:
            if z["direction"] == "LONG" and trend_filter == "BULL":
                score += 15
                motivos.append("Alineado con tendencia alcista")
            elif z["direction"] == "SHORT" and trend_filter == "BEAR":
                score += 15
                motivos.append("Alineado con tendencia bajista")
            else:
                score -= 8
                motivos.append("No alineado con tendencia")
        score = int(max(0, min(100, score)))
        if score >= 80:
            calidad = "EXCELENTE"
        elif score >= 65:
            calidad = "BUENO"
        elif score >= 45:
            calidad = "REGULAR"
        else:
            calidad = "DÉBIL"
        out.at[idx, "score"] = score
        out.at[idx, "calidad"] = calidad
        out.at[idx, "motivo"] = " | ".join(motivos)
    return out.sort_values(["score", "time"], ascending=[False, False]).reset_index(drop=True)
def nearest_fvg(price, fvg_df, direction=None, only_open=True):
    if fvg_df is None or fvg_df.empty:
        return None
    d = fvg_df.copy()
    if direction in ["LONG", "SHORT"]:
        d = d[d["direction"] == direction]
    if only_open and "mitigated" in d.columns:
        d = d[~d["mitigated"].astype(bool)]
    if d.empty:
        return None
    d["distance_pts"] = d.apply(lambda r: 0 if r["low"] <= price <= r["high"] else min(abs(price - r["low"]), abs(price - r["high"])), axis=1)
    return d.sort_values(["distance_pts", "time"], ascending=[True, False]).iloc[0].to_dict()
def fvg_state(price, atr, fvg_df, direction, max_distance_atr=1.5):
    z = nearest_fvg(price, fvg_df, direction=direction, only_open=True)
    if not z:
        return "SIN_FVG", None, np.nan, False
    dist = safe_float(z.get("distance_pts", np.nan))
    dist_atr = dist / atr if not pd.isna(atr) and atr > 0 else np.nan
    inside = z["low"] <= price <= z["high"]
    valid = inside or (not pd.isna(dist_atr) and dist_atr <= max_distance_atr)
    label = f"DENTRO {z['tipo']}" if inside else f"CERCA {z['tipo']}" if valid else f"LEJOS {z['tipo']}"
    return label, z, dist_atr, valid
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
        return "🟢 ALZA"
    if state == "BEAR":
        return "🔴 BAJA"
    return "⚪ NEUTRO"


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
    if data.empty:
        return {}
    data["date"] = data["time"].dt.date
    data["hour"] = data["time"].dt.hour
    dates = sorted(data["date"].unique())
    if len(dates) < 2:
        return {}
    today, yesterday = dates[-1], dates[-2]
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
    clean = {k: v for k, v in levels.items() if not pd.isna(v)}
    targets = {k: v for k, v in clean.items() if v > price} if direction == "LONG" else {k: v for k, v in clean.items() if v < price}
    if not targets:
        return None, np.nan, np.nan
    name, level = min(targets.items(), key=lambda item: abs(item[1] - price))
    return name, level, abs(level - price)


def detect_market_intention(price, df_4h, df_1h, df_15m, levels):
    t4, t1 = trend_state(df_4h), trend_state(df_1h)
    rsi = df_15m["rsi"].iloc[-1]
    ema20 = df_15m["ema20"].iloc[-1]
    ema50 = df_15m["ema50"].iloc[-1]
    ema200 = df_15m["ema200"].iloc[-1]
    atr = df_15m["atr"].iloc[-1]
    _, _, up_dist = nearest_liquidity(price, levels, "LONG")
    _, _, dn_dist = nearest_liquidity(price, levels, "SHORT")
    near_up = not pd.isna(up_dist) and not pd.isna(atr) and up_dist <= atr * 0.7
    near_dn = not pd.isna(dn_dist) and not pd.isna(atr) and dn_dist <= atr * 0.7
    if t4 == "BULL" and t1 == "BULL" and price > ema20 > ema50 > ema200:
        return ("ALCISTA CON LIQUIDEZ SUPERIOR CERCA", "LONG_CON_CUIDADO") if near_up else ("TENDENCIA ALCISTA", "LONG")
    if t4 == "BEAR" and t1 == "BEAR" and price < ema20 < ema50 < ema200:
        return ("BAJISTA CON LIQUIDEZ INFERIOR CERCA", "SHORT_CON_CUIDADO") if near_dn else ("TENDENCIA BAJISTA", "SHORT")
    if not pd.isna(rsi) and 45 <= rsi <= 55:
        return "RANGO / COMPRESIÓN", "NEUTRAL"
    return "SIN INTENCIÓN CLARA", "NEUTRAL"


def score_direction(direction, df_4h, df_1h, df_15m, df_5m, levels, fvg_df=None, fvg_max_distance_atr=1.5):
    score = 0
    t4, t1, t15, t5 = trend_state(df_4h), trend_state(df_1h), trend_state(df_15m), trend_state(df_5m)
    rsi_value = df_15m["rsi"].iloc[-1]
    structure = structure_state(df_5m)
    price = df_5m["close"].iloc[-1]
    init_open_trade_file()
    atr = df_15m["atr"].iloc[-1]
    liquidity_name, _, _ = nearest_liquidity(price, levels, direction)
    _, _, _, fvg_valid = fvg_state(price, atr, fvg_df, direction, fvg_max_distance_atr) if fvg_df is not None else ("", None, np.nan, False)
    if direction == "LONG":
        score += 2 if t4 == "BULL" else 0
        score += 2 if t1 == "BULL" else 0
        score += 1 if t15 == "BULL" else 0
        score += 1 if t5 == "BULL" else 0
        score += 1 if not pd.isna(rsi_value) and rsi_value > 50 else 0
        score += 1 if structure == "BREAK_UP" else 0
        score += 1 if liquidity_name else 0
        score += 1 if fvg_valid else 0
    else:
        score += 2 if t4 == "BEAR" else 0
        score += 2 if t1 == "BEAR" else 0
        score += 1 if t15 == "BEAR" else 0
        score += 1 if t5 == "BEAR" else 0
        score += 1 if not pd.isna(rsi_value) and rsi_value < 50 else 0
        score += 1 if structure == "BREAK_DOWN" else 0
        score += 1 if liquidity_name else 0
        score += 1 if fvg_valid else 0
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


def choose_candidate_direction(estrategia, long_score, short_score, t1d, t4, structure, price, df_15m, df_5m, levels, fvg_df=None):
    rsi = df_15m["rsi"].iloc[-1]
    sweep_direction = detect_sweep_direction(df_5m, levels)
    if estrategia == "FVG + Tendencia":
        long_fvg = nearest_fvg(price, fvg_df, "LONG", only_open=True)
        short_fvg = nearest_fvg(price, fvg_df, "SHORT", only_open=True)
        if long_score >= short_score and long_fvg:
            return "LONG"
        if short_score > long_score and short_fvg:
            return "SHORT"
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
    return "LONG" if price >= ema200 else "SHORT"


def technical_levels(direction, df_5m, entry, rr_target, fvg_zone=None, modo_operativo="Normal"):
    atr = df_5m["atr"].iloc[-1]
    if pd.isna(atr) or atr <= 0:
        atr = 250
    if modo_operativo == "Scalp 15M":
        sl_atr = 1.0
        tp_atr = 1.2
    elif modo_operativo == "Scalping agresivo":
        sl_atr = 1.2
        tp_atr = 1.5
    else:
        sl_atr = 1.8
        tp_atr = 2.5
    if direction == "LONG":
        sl = entry - atr * sl_atr
        tp = entry + atr * tp_atr
        risk_points = entry - sl
    elif direction == "SHORT":
        sl = entry + atr * sl_atr
        tp = entry - atr * tp_atr
        risk_points = sl - entry
    else:
        sl, tp, risk_points = np.nan, np.nan, np.nan
    return sl, tp, risk_points

def calculate_rr(entry, sl, tp, direction):
    if direction == "LONG":
        risk, reward = entry - sl, tp - entry
    elif direction == "SHORT":
        risk, reward = sl - entry, entry - tp
    else:
        return np.nan
    return reward / risk if risk > 0 else np.nan


def position_size(entry, sl, account_usd, risk_pct, leverage):
    risk_usd_target = account_usd * risk_pct
    max_notional = account_usd * leverage
    if pd.isna(sl) or pd.isna(entry) or entry <= 0:
        return 0, 0, risk_usd_target, 0, risk_usd_target, False, max_notional
    distance = abs(entry - sl)
    if distance <= 0:
        return 0, 0, risk_usd_target, 0, risk_usd_target, False, max_notional
    btc_by_risk = risk_usd_target / distance
    notional_by_risk = btc_by_risk * entry
    capped = notional_by_risk > max_notional
    notional = min(notional_by_risk, max_notional)
    btc_size = notional / entry
    margin_needed = notional / leverage if leverage > 0 else notional
    real_risk_usd = btc_size * distance
    return btc_size, notional, real_risk_usd, margin_needed, risk_usd_target, capped, max_notional


def strategy_filter(estrategia, direction, df_15m, df_5m, levels, structure, market_bias, fvg_df=None, use_fvg_filter=False, fvg_max_distance_atr=1.5, df_1h=None):
    motivos = []
    price = df_5m["close"].iloc[-1]
    last = df_5m.iloc[-1]
    ema50 = df_15m["ema50"].iloc[-1]
    atr = df_15m["atr"].iloc[-1]
    rsi = df_15m["rsi"].iloc[-1]
    sweep_direction = detect_sweep_direction(df_5m, levels)
    fvg_label, _, fvg_dist_atr, fvg_valid = fvg_state(price, atr, fvg_df, direction, fvg_max_distance_atr)
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
    elif estrategia == "FVG + Tendencia":
        if not fvg_valid:
            motivos.append(f"FVG + Tendencia: no hay FVG válido/cercano para {direction}. Estado: {fvg_label}.")
        t_1h = trend_state(df_1h) if df_1h is not None else "NEUTRAL"
        if direction == "LONG" and not (t_1h == "BULL" or trend_state(df_15m) == "BULL"):
            motivos.append("FVG + Tendencia: falta tendencia alcista en 1H/15M.")
        if direction == "SHORT" and not (t_1h == "BEAR" or trend_state(df_15m) == "BEAR"):
            motivos.append("FVG + Tendencia: falta tendencia bajista en 1H/15M.")
    if use_fvg_filter and direction in ["LONG", "SHORT"] and not fvg_valid:
        motivos.append(f"Filtro FVG: precio sin FVG {direction} abierto/cercano. Estado: {fvg_label}. Distancia: {format_number(fvg_dist_atr, 2)} ATR.")
    return motivos


def setup_quality(long_score, short_score, direction, rr_real, risk_points, atr_15m, trade_valid, fvg_valid=False):
    base_score = long_score if direction == "LONG" else short_score
    quality_score = int(round((base_score / 10) * 10))
    if not pd.isna(rr_real) and rr_real >= 2:
        quality_score += 1
    if fvg_valid:
        quality_score += 1
    if not pd.isna(risk_points) and not pd.isna(atr_15m):
        quality_score += 1 if risk_points <= atr_15m * 2 else -1
    if not trade_valid:
        quality_score = min(quality_score, 4)
    quality_score = max(1, min(10, quality_score))
    label = "MALA" if quality_score <= 3 else "REGULAR" if quality_score <= 5 else "BUENA" if quality_score <= 7 else "EXCELENTE"
    return quality_score, label

def evaluar_setup_pro(

    direction,

    long_score,

    short_score,

    rr_real,

    risk_points,

    atr_15m,

    tp_atr_multiple,

    fvg_valid,

    fvg_label,

    t1d,

    t4,

    t1,

    t15,

    t5,

    structure,

    price,

    df_15m,

    df_5m,

    levels,

    trade_valid,

    motivos_bloqueo,

    use_time_filter,

    avoid_weekends_filter,

):

    score = 0

    positivos = []

    negativos = []

    dir_score = long_score if direction == "LONG" else short_score

    # 1) Score base dirección

    score += dir_score * 5

    positivos.append(f"Score dirección {dir_score}/10")

    # 2) Tendencia multi timeframe

    if direction == "LONG":

        if t4 == "BULL":

            score += 10

            positivos.append("4H alineado alcista")

        else:

            negativos.append("4H no acompaña LONG")

        if t1 == "BULL":

            score += 10

            positivos.append("1H alineado alcista")

        else:

            negativos.append("1H no acompaña LONG")

        if t15 == "BULL":

            score += 6

            positivos.append("15M acompaña LONG")

        if t5 == "BULL":

            score += 4

            positivos.append("5M acompaña LONG")

        if structure == "BREAK_UP":

            score += 8

            positivos.append("Estructura 5M con ruptura alcista")

        else:

            negativos.append("Falta ruptura alcista clara")

    elif direction == "SHORT":

        if t4 == "BEAR":

            score += 10

            positivos.append("4H alineado bajista")

        else:

            negativos.append("4H no acompaña SHORT")

        if t1 == "BEAR":

            score += 10

            positivos.append("1H alineado bajista")

        else:

            negativos.append("1H no acompaña SHORT")

        if t15 == "BEAR":

            score += 6

            positivos.append("15M acompaña SHORT")

        if t5 == "BEAR":

            score += 4

            positivos.append("5M acompaña SHORT")

        if structure == "BREAK_DOWN":

            score += 8

            positivos.append("Estructura 5M con ruptura bajista")

        else:

            negativos.append("Falta ruptura bajista clara")

    # 3) RR

    if not pd.isna(rr_real):

        if rr_real >= 2.5:

            score += 12

            positivos.append("RR excelente")

        elif rr_real >= 2:

            score += 10

            positivos.append("RR bueno")

        elif rr_real >= 1.8:

            score += 6

            positivos.append("RR aceptable")

        else:

            score -= 12

            negativos.append("RR insuficiente")

    # 4) SL vs ATR

    if not pd.isna(risk_points) and not pd.isna(atr_15m) and atr_15m > 0:

        sl_atr = risk_points / atr_15m

        if sl_atr <= 1.2:

            score += 10

            positivos.append("SL eficiente respecto al ATR")

        elif sl_atr <= 2:

            score += 5

            positivos.append("SL razonable respecto al ATR")

        else:

            score -= 10

            negativos.append("SL demasiado lejos respecto al ATR")

    # 5) TP vs ATR

    if not pd.isna(tp_atr_multiple):

        if tp_atr_multiple <= 2:

            score += 6

            positivos.append("TP alcanzable para intradía")

        elif tp_atr_multiple <= 3:

            score += 2

            positivos.append("TP algo exigente")

        else:

            score -= 6

            negativos.append("TP demasiado exigente")

    # 6) FVG

    if fvg_valid:

        score += 8

        positivos.append(f"FVG válido: {fvg_label}")

    else:

        negativos.append(f"FVG no válido/cercano: {fvg_label}")

    # 7) Volumen relativo

    try:

        vol_ratio = float(df_15m["vol_ratio"].iloc[-1])

        if vol_ratio >= 1.5:

            score += 8

            positivos.append(f"Volumen fuerte {vol_ratio:.2f}x")

        elif vol_ratio >= 1.0:

            score += 4

            positivos.append(f"Volumen normal {vol_ratio:.2f}x")

        else:

            negativos.append(f"Volumen débil {vol_ratio:.2f}x")

    except Exception:

        negativos.append("Volumen no disponible")

    # 8) RSI

    try:

        rsi = float(df_15m["rsi"].iloc[-1])

        if direction == "LONG" and 45 <= rsi <= 68:

            score += 5

            positivos.append("RSI sano para LONG")

        elif direction == "SHORT" and 32 <= rsi <= 55:

            score += 5

            positivos.append("RSI sano para SHORT")

        else:

            negativos.append("RSI no ideal")

    except Exception:

        pass

    # 9) Liquidez cercana

    try:

        liq_name, _, liq_dist = nearest_liquidity(price, levels, direction)

        if liq_name and not pd.isna(liq_dist) and not pd.isna(atr_15m) and atr_15m > 0:

            liq_atr = liq_dist / atr_15m

            if liq_atr >= 0.5:

                score += 5

                positivos.append(f"Objetivo de liquidez disponible: {liq_name}")

            else:

                score -= 5

                negativos.append(f"Demasiado cerca de liquidez: {liq_name}")

    except Exception:

        pass

    # 10) Horario

    try:

        horario_ok = is_allowed_trading_time(df_5m["time"].iloc[-1], use_time_filter, avoid_weekends_filter)

        if horario_ok:

            score += 5

            positivos.append("Horario operativo válido")

        else:

            score -= 8

            negativos.append("Fuera de horario operativo")

    except Exception:

        pass

    # 11) Bloqueos reales

    if trade_valid:

        score += 10

        positivos.append("Sistema habilita operación")

    else:

        score -= min(20, len(motivos_bloqueo) * 5)

        negativos.extend(motivos_bloqueo[:4])

    score = int(max(1, min(100, score)))

    score_10 = max(1, min(10, round(score / 10)))

    if score >= 80:

        label = "EXCELENTE"

    elif score >= 65:

        label = "BUENA"

    elif score >= 45:

        label = "REGULAR"

    else:

        label = "MALA"

    return score_10, label, {

        "score_100": score,

        "positivos": positivos,

        "negativos": negativos,

    }

def is_allowed_trading_time(ts, use_filter=True, avoid_weekends=True):
    if pd.isna(ts):
        return False
    if avoid_weekends and ts.weekday() >= 5:
        return False
    if not use_filter:
        return True
    return (7 <= ts.hour < 10) or (13 <= ts.hour < 16)


def validate_trade(estrategia, direction, long_score, short_score, min_score, risk_pct, rr_real, min_rr,
                   risk_points, atr_15m, market_bias, structure, price, levels, max_atr_multiplier,
                   df_15m, df_5m, use_time_filter=False, avoid_weekends_filter=False,
                   fvg_df=None, use_fvg_filter=False, fvg_max_distance_atr=1.5, df_1h=None):
    motivos = []
    if direction is None:
        return False, ["No hay dirección dominante clara."]
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
    if not pd.isna(risk_points) and not pd.isna(atr_15m) and risk_points > atr_15m * max_atr_multiplier:
        motivos.append("SL demasiado lejos respecto al ATR.")
    nearest_name, _, nearest_distance = nearest_liquidity(price, levels, direction)
    if nearest_name and not pd.isna(nearest_distance) and not pd.isna(atr_15m) and nearest_distance < atr_15m * 0.35:
        motivos.append(f"Entrada demasiado cerca de liquidez: {nearest_name}.")
    if not is_allowed_trading_time(df_5m["time"].iloc[-1], use_time_filter, avoid_weekends_filter):
        motivos.append("Filtro horario: fuera de Londres / NY o fin de semana.")
    motivos.extend(strategy_filter(estrategia, direction, df_15m, df_5m, levels, structure, market_bias, fvg_df, use_fvg_filter, fvg_max_distance_atr, df_1h))
    return len(motivos) == 0, motivos

def detectar_zonas_daytrade(df_15m, asia_high=None, london_high=None, max_zonas=3):

    """

    Motor profesional de zonas/confluencias para daytrade.

    No predice. Ordena zonas, mide calidad y dice qué falta para operar.

    """

    if df_15m is None or df_15m.empty or len(df_15m) < 80:

        return []

    df = df_15m.copy()

    precio = float(df["close"].iloc[-1])

    atr = float(df["atr"].iloc[-1]) if "atr" in df.columns and not pd.isna(df["atr"].iloc[-1]) else precio * 0.003

    if atr <= 0:

        atr = precio * 0.003

    zonas_base = []

    def nueva_zona(nombre, desde, hasta, tipo, peso, motivo):

        centro = (desde + hasta) / 2

        distancia_pts = centro - precio

        distancia_atr = abs(distancia_pts) / atr

        if distancia_atr <= 5:

            zonas_base.append({

                "nombre": nombre,

                "desde": float(desde),

                "hasta": float(hasta),

                "centro": float(centro),

                "tipo": tipo,

                "peso": peso,

                "motivos": [motivo],

                "distancia_pts": distancia_pts,

                "distancia_atr": distancia_atr

            })

    # =========================

    # EMAS

    # =========================

    if "ema20" in df.columns and not pd.isna(df["ema20"].iloc[-1]):

        ema20 = float(df["ema20"].iloc[-1])

        nueva_zona(

            "EMA20",

            ema20 - atr * 0.12,

            ema20 + atr * 0.12,

            "dinamica",

            10,

            "EMA20 cercana"

        )

    if "ema50" in df.columns and not pd.isna(df["ema50"].iloc[-1]):

        ema50 = float(df["ema50"].iloc[-1])

        nueva_zona(

            "EMA50",

            ema50 - atr * 0.15,

            ema50 + atr * 0.15,

            "dinamica",

            14,

            "EMA50 cercana"

        )

    # =========================

    # ASIA / LONDRES

    # =========================

    if asia_high is not None and not pd.isna(asia_high):

        nivel = float(asia_high)

        nueva_zona(

            "Máximo Asia",

            nivel - atr * 0.18,

            nivel + atr * 0.18,

            "liquidez",

            16,

            "Liquidez de Asia"

        )

    if london_high is not None and not pd.isna(london_high):

        nivel = float(london_high)

        nueva_zona(

            "Máximo Londres",

            nivel - atr * 0.18,

            nivel + atr * 0.18,

            "liquidez",

            18,

            "Liquidez de Londres"

        )

    # =========================

    # SWING HIGHS / RESISTENCIAS

    # =========================

    ultimas = df.tail(90).reset_index(drop=True)

    for i in range(2, len(ultimas) - 2):

        h = float(ultimas["high"].iloc[i])

        if (

            h > ultimas["high"].iloc[i - 1]

            and h > ultimas["high"].iloc[i - 2]

            and h > ultimas["high"].iloc[i + 1]

            and h > ultimas["high"].iloc[i + 2]

        ):

            nueva_zona(

                "Resistencia reciente",

                h - atr * 0.15,

                h + atr * 0.15,

                "resistencia",

                13,

                "Swing high / liquidez superior"

            )

    # =========================

    # BEARISH FVG

    # =========================

    for i in range(2, len(df)):

        high_1 = float(df["high"].iloc[i - 2])

        low_3 = float(df["low"].iloc[i])

        if low_3 > high_1:

            tamaño_atr = abs(low_3 - high_1) / atr

            centro = (high_1 + low_3) / 2

            distancia_atr = abs(precio - centro) / atr

            if tamaño_atr >= 0.20 and distancia_atr <= 5:

                nueva_zona(

                    "Bearish FVG",

                    high_1,

                    low_3,

                    "fvg_bajista",

                    20,

                    "Bearish FVG / ineficiencia"

                )

    # =========================

    # UNIFICAR ZONAS SOLAPADAS

    # =========================

    zonas_base = sorted(zonas_base, key=lambda x: x["peso"], reverse=True)

    zonas = []

    for z in zonas_base:

        fusionada = False

        for f in zonas:

            solapa = not (z["hasta"] < f["desde"] or z["desde"] > f["hasta"])

            if solapa:

                f["desde"] = min(f["desde"], z["desde"])

                f["hasta"] = max(f["hasta"], z["hasta"])

                f["peso"] += z["peso"] * 0.45

                for m in z["motivos"]:

                    if m not in f["motivos"]:

                        f["motivos"].append(m)

                if z["tipo"] not in f["tipo"]:

                    f["tipo"] += " + " + z["tipo"]

                fusionada = True

                break

        if not fusionada:

            zonas.append(z)

    resultado = []

    for z in zonas:

        centro = (z["desde"] + z["hasta"]) / 2

        distancia_pts = centro - precio

        distancia_atr = abs(distancia_pts) / atr

        cantidad_confluencias = len(z["motivos"])

        score = 35

        score += min(30, cantidad_confluencias * 9)

        score += max(0, 20 - distancia_atr * 5)

        if "fvg_bajista" in z["tipo"]:

            score += 10

        if "liquidez" in z["tipo"]:

            score += 8

        if "resistencia" in z["tipo"]:

            score += 6

        score = int(max(0, min(100, score)))

        dentro = z["desde"] <= precio <= z["hasta"]

        if score >= 90:

            calidad = "EXCELENTE"

            color = "🟢"

        elif score >= 80:

            calidad = "MUY BUENA"

            color = "🟢"

        elif score >= 70:

            calidad = "BUENA"

            color = "🟡"

        elif score >= 55:

            calidad = "REGULAR"

            color = "🟠"

        else:

            calidad = "DÉBIL"

            color = "🔴"

        if dentro:

            estado = "🟠 Precio dentro de la zona"

            accion = "Esperar confirmación. No entrar directo."

        elif precio < z["desde"]:

            estado = "⏳ Precio debajo de la zona"

            accion = "Esperar llegada a la zona."

        else:

            estado = "⚠️ Precio ya superó la zona"

            accion = "No perseguir entrada."

        sesgo = "SHORT potencial si hay rechazo"

        confirmaciones = {

            "FVG": "Bearish FVG / ineficiencia" in z["motivos"],

            "Liquidez": any("liquidez" in m.lower() for m in z["motivos"]),

            "EMA20": "EMA20 cercana" in z["motivos"],

            "EMA50": "EMA50 cercana" in z["motivos"],

            "Resistencia": any("swing" in m.lower() for m in z["motivos"]),

            "CHoCH": False,

            "Sweep": False,

            "Volumen": False,

        }

        confirmadas = sum(1 for v in confirmaciones.values() if v)

        total_conf = len(confirmaciones)

        if dentro and confirmadas >= 4:

            semaforo = "🟡 VIGILAR"

        elif dentro and confirmadas >= 5:

            semaforo = "🟢 CASI LISTA"

        elif not dentro and score >= 75:

            semaforo = "🟡 ESPERAR PRECIO"

        else:

            semaforo = "🔴 NO OPERAR TODAVÍA"

        faltan = [k for k, v in confirmaciones.items() if not v]

        resultado.append({

            "desde": z["desde"],

            "hasta": z["hasta"],

            "centro": centro,

            "score": score,

            "calidad": calidad,

            "color": color,

            "estado": estado,

            "accion": accion,

            "sesgo": sesgo,

            "distancia_pts": distancia_pts,

            "distancia_atr": distancia_atr,

            "motivos": z["motivos"],

            "confirmaciones": confirmaciones,

            "confirmadas": confirmadas,

            "total_confirmaciones": total_conf,

            "faltan": faltan,

            "semaforo": semaforo,

            "estrellas": "⭐" * max(1, min(5, round(score / 20)))

        })

    resultado = sorted(resultado, key=lambda x: x["score"], reverse=True)

    return resultado[:max_zonas]
def volume_profile_pro(df, bins=48, value_area_pct=0.70):

    """

    Volume Profile aproximado usando OHLCV.

    Calcula POC, VAH, VAL, HVN y LVN.

    """

    if df is None or df.empty or len(df) < 50:

        return None

    d = df.copy().dropna(subset=["high", "low", "close", "volume"])

    if d.empty:

        return None

    price_min = float(d["low"].min())

    price_max = float(d["high"].max())

    if price_max <= price_min:

        return None

    bin_edges = np.linspace(price_min, price_max, bins + 1)

    volume_by_bin = np.zeros(bins)

    for _, row in d.iterrows():

        high = float(row["high"])

        low = float(row["low"])

        volume = float(row["volume"])

        if high <= low or volume <= 0:

            continue

        touched_bins = np.where((bin_edges[:-1] <= high) & (bin_edges[1:] >= low))[0]

        if len(touched_bins) == 0:

            continue

        volume_share = volume / len(touched_bins)

        for b in touched_bins:

            volume_by_bin[b] += volume_share

    if volume_by_bin.sum() <= 0:

        return None

    bin_centers = (bin_edges[:-1] + bin_edges[1:]) / 2

    poc_idx = int(np.argmax(volume_by_bin))

    poc = float(bin_centers[poc_idx])

    total_volume = volume_by_bin.sum()

    target_volume = total_volume * value_area_pct

    selected = {poc_idx}

    accumulated = volume_by_bin[poc_idx]

    left = poc_idx - 1

    right = poc_idx + 1

    while accumulated < target_volume and (left >= 0 or right < bins):

        left_vol = volume_by_bin[left] if left >= 0 else -1

        right_vol = volume_by_bin[right] if right < bins else -1

        if right_vol >= left_vol:

            selected.add(right)

            accumulated += right_vol

            right += 1

        else:

            selected.add(left)

            accumulated += left_vol

            left -= 1

    selected_prices = [bin_centers[i] for i in selected]

    vah = float(max(selected_prices))

    val = float(min(selected_prices))

    avg_vol = volume_by_bin.mean()

    hvn = []

    lvn = []

    for i, vol in enumerate(volume_by_bin):

        price_level = float(bin_centers[i])

        if vol >= avg_vol * 1.40:

            hvn.append(price_level)

        if vol <= avg_vol * 0.45:

            lvn.append(price_level)

    current_price = float(d["close"].iloc[-1])

    if current_price > vah:

        estado = "Precio arriba del Value Area"

        lectura = "Mercado aceptando precios altos. Buscar continuación si sostiene sobre VAH."

    elif current_price < val:

        estado = "Precio debajo del Value Area"

        lectura = "Mercado debajo del área de valor. Puede buscar VAL/POC si recupera."

    elif abs(current_price - poc) <= (price_max - price_min) / bins:

        estado = "Precio cerca del POC"

        lectura = "Zona de mayor aceptación. Cuidado con rango/chop."

    else:

        estado = "Precio dentro del Value Area"

        lectura = "Mercado en zona de equilibrio. Esperar ruptura o rechazo claro."

    return {

        "poc": poc,

        "vah": vah,

        "val": val,

        "hvn": hvn[:5],

        "lvn": lvn[:5],

        "estado": estado,

        "lectura": lectura,

        "current_price": current_price,

        "bin_centers": bin_centers,

        "volume_by_bin": volume_by_bin,

    }

def detect_order_blocks(df, lookback=120, impulse_atr=1.2):
    """
    Detecta Order Blocks simples:
    - Bullish OB: última vela bajista antes de impulso alcista.
    - Bearish OB: última vela alcista antes de impulso bajista.
    """
    if df is None or df.empty or len(df) < 30:
        return pd.DataFrame()
    d = df.tail(lookback).copy().reset_index(drop=True)
    obs = []
    for i in range(3, len(d) - 3):
        candle = d.iloc[i]
        next1 = d.iloc[i + 1]
        next2 = d.iloc[i + 2]
        atr = safe_float(candle.get("atr", np.nan), np.nan)
        if pd.isna(atr) or atr <= 0:
            continue
        impulso_alcista = (
            next1["close"] > next1["open"]
            and next2["close"] > candle["high"]
            and (next2["high"] - candle["low"]) >= atr * impulse_atr
        )
        impulso_bajista = (
            next1["close"] < next1["open"]
            and next2["close"] < candle["low"]
            and (candle["high"] - next2["low"]) >= atr * impulse_atr
        )
        if candle["close"] < candle["open"] and impulso_alcista:
            obs.append({
                "tipo": "BULLISH_OB",
                "direction": "LONG",
                "time": candle["time"],
                "low": float(candle["low"]),
                "high": float(candle["high"]),
                "mid": float((candle["low"] + candle["high"]) / 2),
                "mitigated": False,
            })
        if candle["close"] > candle["open"] and impulso_bajista:
            obs.append({
                "tipo": "BEARISH_OB",
                "direction": "SHORT",
                "time": candle["time"],
                "low": float(candle["low"]),
                "high": float(candle["high"]),
                "mid": float((candle["low"] + candle["high"]) / 2),
                "mitigated": False,
            })
    out = pd.DataFrame(obs)
    if out.empty:
        return out
    for idx, ob in out.iterrows():
        future = d[d["time"] > ob["time"]]
        if future.empty:
            continue
        if ob["direction"] == "LONG":
            mitigated = (future["low"] <= ob["mid"]).any()
        else:
            mitigated = (future["high"] >= ob["mid"]).any()
        out.at[idx, "mitigated"] = bool(mitigated)
    return out.sort_values("time").reset_index(drop=True)

def detect_liquidity_profile(df, lookback=120, tolerance_atr=0.18):
    """
    Detecta perfil de liquidez:
    - Equal Highs
    - Equal Lows
    - Barridos
    - Liquidez pendiente
    """
    if df is None or df.empty or len(df) < 40:
        return pd.DataFrame()
    d = df.tail(lookback).copy().reset_index(drop=True)
    atr = safe_float(d["atr"].iloc[-1], np.nan)
    if pd.isna(atr) or atr <= 0:
        atr = float((d["high"] - d["low"]).rolling(14).mean().iloc[-1])
    tolerance = atr * tolerance_atr
    rows = []
    # Equal Highs / Equal Lows
    for i in range(5, len(d) - 5):
        level_high = float(d["high"].iloc[i])
        level_low = float(d["low"].iloc[i])
        nearby_highs = d[
            (d.index != i) &
            (abs(d["high"] - level_high) <= tolerance)
        ]
        nearby_lows = d[
            (d.index != i) &
            (abs(d["low"] - level_low) <= tolerance)
        ]
        if len(nearby_highs) >= 2:
            rows.append({
                "tipo": "EQUAL_HIGHS",
                "direction": "SHORT",
                "nivel": level_high,
                "time": d["time"].iloc[i],
                "estado": "PENDIENTE",
                "motivo": "Liquidez superior acumulada"
            })
        if len(nearby_lows) >= 2:
            rows.append({
                "tipo": "EQUAL_LOWS",
                "direction": "LONG",
                "nivel": level_low,
                "time": d["time"].iloc[i],
                "estado": "PENDIENTE",
                "motivo": "Liquidez inferior acumulada"
            })
    out = pd.DataFrame(rows)
    if out.empty:
        return out
    # Sacar duplicados por nivel cercano
    out["nivel_round"] = (out["nivel"] / tolerance).round() * tolerance
    out = out.drop_duplicates(subset=["tipo", "nivel_round"], keep="last").copy()
    # Detectar barridos
    current_price = float(d["close"].iloc[-1])
    for idx, row in out.iterrows():
        future = d[d["time"] > row["time"]]
        if future.empty:
            continue
        if row["tipo"] == "EQUAL_HIGHS":
            swept = ((future["high"] > row["nivel"]) & (future["close"] < row["nivel"])).any()
        else:
            swept = ((future["low"] < row["nivel"]) & (future["close"] > row["nivel"])).any()
        if swept:
            out.at[idx, "estado"] = "BARRIDO"
            out.at[idx, "motivo"] = "Liquidez barrida con rechazo"
    out["distancia_pts"] = abs(out["nivel"] - current_price)
    out["distancia_atr"] = out["distancia_pts"] / atr
    return out.sort_values(["estado", "distancia_atr"]).reset_index(drop=True)

def detect_institutional_volume(df, lookback=120, vol_mult=1.8, range_mult=1.4):
    """
    Detecta velas institucionales:
    - volumen anormal
    - rango grande
    - ruptura de máximo/mínimo reciente
    """
    if df is None or df.empty or len(df) < 50:
        return pd.DataFrame()
    d = df.tail(lookback).copy().reset_index(drop=True)
    d["range"] = d["high"] - d["low"]
    d["range_ma20"] = d["range"].rolling(20).mean()
    d["vol_ma20"] = d["volume"].rolling(20).mean()
    rows = []
    for i in range(25, len(d)):
        row = d.iloc[i]
        prev = d.iloc[:i]
        vol_ok = row["volume"] >= row["vol_ma20"] * vol_mult if row["vol_ma20"] > 0 else False
        range_ok = row["range"] >= row["range_ma20"] * range_mult if row["range_ma20"] > 0 else False
        break_up = row["close"] > prev["high"].tail(20).max()
        break_down = row["close"] < prev["low"].tail(20).min()
        if vol_ok and range_ok and break_up:
            rows.append({
                "time": row["time"],
                "tipo": "VOLUMEN_INSTITUCIONAL_ALCISTA",
                "direction": "LONG",
                "precio": float(row["close"]),
                "high": float(row["high"]),
                "low": float(row["low"]),
                "volume": float(row["volume"]),
                "vol_ratio": float(row["volume"] / row["vol_ma20"]),
                "range_ratio": float(row["range"] / row["range_ma20"]),
                "motivo": "Volumen anormal + rango grande + ruptura alcista válida"
            })
        if vol_ok and range_ok and break_down:
            rows.append({
                "time": row["time"],
                "tipo": "VOLUMEN_INSTITUCIONAL_BAJISTA",
                "direction": "SHORT",
                "precio": float(row["close"]),
                "high": float(row["high"]),
                "low": float(row["low"]),
                "volume": float(row["volume"]),
                "vol_ratio": float(row["volume"] / row["vol_ma20"]),
                "range_ratio": float(row["range"] / row["range_ma20"]),
                "motivo": "Volumen anormal + rango grande + ruptura bajista válida"
            })
    return pd.DataFrame(rows).sort_values("time").reset_index(drop=True) if rows else pd.DataFrame()

def add_volume_delta(df):
    """
    Delta estimado con OHLCV.
    No es delta real de orderflow, pero aproxima presión compradora/vendedora.
    """
    if df is None or df.empty:
        return df
    d = df.copy()
    candle_range = (d["high"] - d["low"]).replace(0, np.nan)
    body = d["close"] - d["open"]
    d["delta_ratio"] = body / candle_range
    d["delta_ratio"] = d["delta_ratio"].clip(-1, 1).fillna(0)
    d["volume_delta"] = d["volume"] * d["delta_ratio"]
    d["buy_volume_est"] = np.where(d["volume_delta"] > 0, d["volume_delta"], 0)
    d["sell_volume_est"] = np.where(d["volume_delta"] < 0, abs(d["volume_delta"]), 0)
    d["delta_ma20"] = d["volume_delta"].rolling(20).mean()
    d["delta_abs_ma20"] = d["volume_delta"].abs().rolling(20).mean()
    d["delta_strength"] = d["volume_delta"] / d["delta_abs_ma20"].replace(0, np.nan)
    d["delta_strength"] = d["delta_strength"].replace([np.inf, -np.inf], np.nan).fillna(0)
    return d
