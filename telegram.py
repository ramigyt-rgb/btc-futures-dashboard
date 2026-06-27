=================
# MENSAJES ALERTA
# =========================

def build_valid_signal_msg(decision, symbol, estrategia, price, sl, tp, rr, quality_label, quality_score, long_score, short_score, rsi, atr, current_candle_time, fvg_label="", modo_operativo="Normal"):
    return f"""<b>BTC DASHBOARD PRO</b>

<b>SEÑAL VÁLIDA DETECTADA</b>

Dirección: <b>{display_direction(decision)}</b>
Par: {symbol}
Estrategia: {estrategia}
Modo: {modo_operativo}
Tipo: {"AGRESIVA" if modo_operativo in ["Agresivo", "Scalping agresivo"] else "NORMAL"}
FVG: {fvg_label}

Entrada: {fmt0(price)}
SL: {fmt0(sl)}
TP: {fmt0(tp)}

RR: {format_number(rr, 2)}
Setup: {quality_label} {quality_score}/10
Long Score: {long_score}/10
Short Score: {short_score}/10
RSI 15M: {format_number(rsi, 2)}
ATR 15M: {fmt0(atr)} pts

Vela 5M: {current_candle_time}
"""


def build_almost_msg(direction, symbol, estrategia, score, min_score, price, sl, tp, rr, long_score, short_score, rsi, motivos, current_candle_time, fvg_label=""):
    motivos_txt = "\n".join([f"- {m}" for m in motivos[:4]]) if motivos else "- Falta confirmación final del sistema."
    return f"""⚠️ <b>SETUP EN FORMACIÓN</b>

Dirección probable: <b>{display_direction(direction)}</b>
Par: {symbol}
Estrategia: {estrategia}
FVG: {fvg_label}

Score dirección: {score}/{min_score}
Long Score: {long_score}/10
Short Score: {short_score}/10
RSI 15M: {format_number(rsi, 2)}

Entrada teórica: {fmt0(price)}
SL: {fmt0(sl)}
TP: {fmt0(tp)}
RR: {format_number(rr, 2)}

Todavía NO es entrada.
Falta:
{motivos_txt}

Vela 5M: {current_candle_time}
"""


def build_bias_msg(symbol, market_bias, escenario, t4, t1, t15, t5, structure, price, rsi, current_candle_time):
    return f"""🔄 <b>CAMBIO DE SESGO BTC</b>

Par: {symbol}
Sesgo nuevo: <b>{display_direction(market_bias)}</b>
Escenario: {escenario}
Precio: {fmt0(price)}
4H: {trend_icon(t4)}
1H: {trend_icon(t1)}
15M: {trend_icon(t15)}
5M: {trend_icon(t5)}
Estructura 5M: {structure}
RSI 15M: {format_number(rsi, 2)}
Vela 5M: {current_candle_time}
"""


def build_risk_msg(symbol, direction, price, sl, tp, risk_points, tp_atr_multiple, rr, current_candle_time):
    return f"""⚠️ <b>ALERTA DE RIESGO / OBJETIVO EXIGENTE</b>

Par: {symbol}
Dirección: <b>{display_direction(direction)}</b>
Precio: {fmt0(price)}
SL: {fmt0(sl)}
TP: {fmt0(tp)}
Distancia SL: {fmt0(risk_points)} pts
TP en ATR: {format_number(tp_atr_multiple, 2)}
RR: {format_number(rr, 2)}
Vela 5M: {current_candle_time}
"""


def build_market_update_msg(color, decision, candidate_direction, symbol, estrategia, price, long_score, short_score, rsi, atr, t4, t1, t15, t5, structure, escenario, motivos, current_candle_time):
    if color == "GREEN":
        header = "🟢 <b>ALERTA VERDE — SETUP OPERABLE</b>"
        action = "Puede haber oportunidad válida según reglas."
    elif color == "RED":
        header = "🔴 <b>ALERTA ROJA — NO OPERAR / RIESGO ALTO</b>"
        action = "Mercado peligroso o condiciones débiles. Esperar."
    else:
        header = "🟡 <b>ALERTA AMARILLA — SETUP EN FORMACIÓN</b>"
        action = "Hay intención, pero todavía falta confirmación."
    motivos_txt = "\n".join([f"- {m}" for m in motivos[:5]]) if motivos else "- Sin bloqueos."
    return f"""{header}

Par: {symbol}
Estrategia: {estrategia}
Estado: <b>{display_direction(decision)}</b>
Dirección calculada: <b>{display_direction(candidate_direction)}</b>

Precio: {fmt0(price)}
Long Score: {long_score}/10
Short Score: {short_score}/10
RSI 15M: {format_number(rsi, 2)}
ATR 15M: {fmt0(atr)} pts

Tendencias:
4H: {trend_icon(t4)}
1H: {trend_icon(t1)}
15M: {trend_icon(t15)}
5M: {trend_icon(t5)}

Estructura 5M: {structure}
Escenario: {escenario}
Lectura: {action}

Bloqueos / detalles:
{motivos_txt}

Vela 5M: {current_candle_time}
"""
