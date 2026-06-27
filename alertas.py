# =========================
# ALERTAS
# =========================
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
    

def get_secret_value(key, default=""):
    try:
        return st.secrets.get(key, default)
    except Exception:
        return default


def get_telegram_credentials(token_override="", chat_id_override=""):
    token = token_override or get_secret_value("TELEGRAM_BOT_TOKEN", "")
    chat_id = chat_id_override or get_secret_value("TELEGRAM_CHAT_ID", "")
    return str(token).strip(), str(chat_id).strip()


def send_telegram_message(text, token_override="", chat_id_override=""):
    if requests is None:
        return False, "requests no instalado. Agregá requests en requirements.txt."
    token, chat_id = get_telegram_credentials(token_override, chat_id_override)
    if not token or not chat_id:
        return False, "Falta TELEGRAM_BOT_TOKEN o TELEGRAM_CHAT_ID en Secrets."
    try:
        url = f"https://api.telegram.org/bot{token}/sendMessage"
        r = requests.post(url, data={"chat_id": chat_id, "text": text, "parse_mode": "HTML", "disable_web_page_preview": True}, timeout=10)
        return r.ok, r.text[:500]
    except Exception as e:
        return False, str(e)


def send_discord_message(webhook_url, text):
    if not webhook_url or requests is None:
        return False, "Falta webhook o librería requests."
    try:
        clean_text = text.replace("<b>", "**").replace("</b>", "**")
        r = requests.post(webhook_url, json={"content": clean_text}, timeout=10)
        return r.ok, r.text[:500]
    except Exception as e:
        return False, str(e)


def alert_already_sent(alert_key):
    df = safe_read_csv(ALERTS_FILE)
    if df.empty or "alert_key" not in df.columns:
        return False
    return str(alert_key) in set(df["alert_key"].astype(str))


def save_alert_sent(alert_key, tipo, canal, mensaje, response=""):
    row = pd.DataFrame([{
        "fecha": datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S"),
        "alert_key": str(alert_key),
        "tipo": tipo,
        "canal": canal,
        "mensaje": str(mensaje)[:700],
        "response": str(response)[:500],
    }])
    old = safe_read_csv(ALERTS_FILE)
    out = pd.concat([old, row], ignore_index=True) if not old.empty else row
    out.to_csv(ALERTS_FILE, index=False)


def send_alert_once(alert_key, tipo, mensaje, telegram_on, discord_on, discord_url="", token_override="", chat_id_override=""):
    if alert_already_sent(alert_key):
        return False, "Alerta ya enviada"
    sent_any = False
    responses = []
    if telegram_on:
        ok, resp = send_telegram_message(mensaje, token_override, chat_id_override)
        responses.append(f"Telegram: {resp}")
        if ok:
            sent_any = True
            save_alert_sent(alert_key, tipo, "telegram", mensaje, resp)
    if discord_on and discord_url:
        ok, resp = send_discord_message(discord_url, mensaje)
        responses.append(f"Discord: {resp}")
        if ok:
            sent_any = True
            save_alert_sent(alert_key, tipo, "discord", mensaje, resp)
    return sent_any, " | ".join(responses) if responses else "Alertas desactivadas"


def load_market_state():
    df = safe_read_csv(MARKET_STATE_FILE)
    if df.empty or "state_key" not in df.columns:
        return ""
    return str(df["state_key"].iloc[-1])


def save_market_state(state_key):
    pd.DataFrame([{
        "fecha": datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S"),
        "state_key": state_key,
    }]).to_csv(MARKET_STATE_FILE, index=False)
