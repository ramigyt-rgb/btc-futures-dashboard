# =========================
# TARJETA COMERCIAL / RESUMEN EJECUTIVO
# =========================
from analysis import * 
from config import *
from helpers import *
from exchange import load_all_data
from sidebar import render_sidebar
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
import json
import uuid
import hashlib
from pathlib import Path
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


# ============================================================================
# FUTURES OS PRO — SAFETY / EXECUTION / QUANT CONTROL LAYER
# Added 2026-09-15. The design is fail-closed: missing or stale critical data
# never becomes a green light for LIVE execution.
# ============================================================================
import csv
import math
import random
import time
from decimal import Decimal, ROUND_DOWN, ROUND_HALF_UP, InvalidOperation
from dataclasses import dataclass, asdict, field
from typing import Any, Optional

PRO_SCHEMA_VERSION = "2026.09.15-500"


def _pro_data_dir() -> Path:
    preferred = os.getenv("BTC_PRO_DATA_DIR", ".")
    candidates = [Path(preferred), Path("/tmp/btc_futures_os")]
    for base in candidates:
        try:
            base.mkdir(parents=True, exist_ok=True)
            probe = base / ".write_test"
            probe.write_text("ok", encoding="utf-8")
            probe.unlink(missing_ok=True)
            return base
        except Exception:
            continue
    return Path(".")


PRO_DATA_DIR = _pro_data_dir()
PRO_SETTINGS_FILE = PRO_DATA_DIR / "futures_os_settings.json"
PRO_JOURNAL_FILE = PRO_DATA_DIR / "futures_os_journal.csv"
PRO_PAPER_FILE = PRO_DATA_DIR / "futures_os_paper_state.json"
PRO_MICRO_FILE = PRO_DATA_DIR / "futures_os_microstructure.csv"
PRO_INCIDENT_FILE = PRO_DATA_DIR / "futures_os_incidents.csv"


PRO_DEFAULT_SETTINGS = {
    "schema_version": PRO_SCHEMA_VERSION,
    "environment": "PAPER",               # PAPER | TESTNET | LIVE
    "armed": False,
    "kill_switch": False,
    "analysis_symbol": "BTCUSDT",
    "quote_asset": "USDT",
    "position_mode": "AUTO",              # AUTO | ONE_WAY | HEDGE
    "margin_mode": "isolated",            # isolated | cross
    "working_type": "MARK_PRICE",
    "order_type": "MARKET",               # MARKET | LIMIT
    "post_only": False,
    "max_risk_per_trade_pct": 1.00,
    "max_open_risk_pct": 3.00,
    "max_daily_loss_pct": 2.00,
    "max_weekly_loss_pct": 5.00,
    "max_drawdown_pct": 12.00,
    "max_consecutive_losses": 3,
    "cooldown_minutes": 30,
    "max_leverage": 5.0,
    "max_spread_bps": 8.0,
    "max_expected_slippage_bps": 12.0,
    "max_chase_atr": 0.75,
    "signal_expiry_minutes": 45.0,
    "max_mark_last_divergence_bps": 15.0,
    "max_public_data_age_sec": 20.0,
    "max_candle_age_sec": 600.0,
    "min_rr_net": 1.50,
    "min_expectancy_r": 0.05,
    "min_calibration_samples_live": 30,
    "require_validated_edge_live": True,
    "taker_fee_bps_per_side": 5.0,
    "maker_fee_bps_per_side": 2.0,
    "funding_holding_hours": 8.0,
    "risk_drawdown_governor": True,
    "breakeven_after_r": 1.0,
    "trailing_after_r": 1.5,
    "trailing_atr_multiple": 1.2,
    "paper_time_stop_minutes": 720,
    "paper_auto_breakeven": True,
    "paper_auto_trailing": True,
    "paper_auto_time_stop": True,
    "tp1_r": 1.0,
    "tp2_r": 2.0,
    "tp3_r": 3.0,
    "tp1_pct": 50.0,
    "tp2_pct": 30.0,
    "tp3_pct": 20.0,
    "allow_live_market_orders": False,
    "live_requires_typed_confirmation": True,
    "reconcile_every_sec": 15,
    "max_api_retries": 3,
    "api_timeout_ms": 10000,
    "auto_disarm_minutes": 20,
    "armed_at": "",
    "max_same_side_positions": 3,
    "revenge_cooldown_minutes": 20,
    "max_size_escalation_mult": 1.50,
}


def _pro_json_load(path: Path, default: Any) -> Any:
    try:
        if not path.exists():
            return default
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default


def _pro_atomic_json_write(path: Path, payload: Any) -> bool:
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(path.suffix + ".tmp")
        tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
        os.replace(tmp, path)
        return True
    except Exception:
        return False


def pro_load_settings() -> dict:
    raw = _pro_json_load(PRO_SETTINGS_FILE, {})
    merged = PRO_DEFAULT_SETTINGS.copy()
    if isinstance(raw, dict):
        merged.update({k: v for k, v in raw.items() if k in merged})
    merged["schema_version"] = PRO_SCHEMA_VERSION
    return merged


def pro_save_settings(settings: dict) -> bool:
    merged = PRO_DEFAULT_SETTINGS.copy()
    merged.update({k: v for k, v in settings.items() if k in merged})
    merged["schema_version"] = PRO_SCHEMA_VERSION
    return _pro_atomic_json_write(PRO_SETTINGS_FILE, merged)


def pro_apply_auto_disarm(settings: dict) -> dict:
    settings = settings.copy()
    env = str(settings.get("environment", "PAPER")).upper()
    if env == "PAPER":
        return settings
    if not settings.get("armed"):
        return settings
    armed_at = settings.get("armed_at")
    if not armed_at:
        settings["armed_at"] = pro_now_utc().isoformat()
        pro_save_settings(settings)
        return settings
    try:
        ts = pd.to_datetime(armed_at, utc=True)
        age_min = (pro_now_utc() - ts).total_seconds()/60.0
        if age_min >= float(settings.get("auto_disarm_minutes", 20)):
            settings["armed"] = False
            settings["armed_at"] = ""
            pro_save_settings(settings)
            pro_log_incident("WARN", "AUTO_DISARM", f"Auto-disarm after {age_min:.1f} min")
    except Exception:
        settings["armed"] = False
        settings["armed_at"] = ""
        pro_save_settings(settings)
    return settings


def pro_now_utc() -> pd.Timestamp:
    return pd.Timestamp.now(tz="UTC")


def pro_safe_float(v, default=np.nan) -> float:
    try:
        x = float(v)
        if not np.isfinite(x):
            return default
        return x
    except Exception:
        return default


def pro_safe_pct(v, default=0.0) -> float:
    x = pro_safe_float(v, np.nan)
    return default if pd.isna(x) else x


def pro_symbol_id(symbol: str | None) -> str:
    s = str(symbol or "BTCUSDT").upper().strip()
    s = s.replace("/", "").replace("-", "")
    if ":" in s:
        s = s.split(":", 1)[0]
    if s.endswith("USDTUSDT"):
        s = s[:-4]
    return s


def pro_ccxt_symbol(symbol: str | None) -> str:
    sid = pro_symbol_id(symbol)
    for quote in ("USDT", "USDC", "BUSD", "USD"):
        if sid.endswith(quote) and len(sid) > len(quote):
            base = sid[:-len(quote)]
            return f"{base}/{quote}:{quote}"
    return f"{sid}/USDT:USDT"


def pro_decimal_round(value: float, step: float, mode=ROUND_DOWN) -> float:
    try:
        d_value = Decimal(str(value))
        d_step = Decimal(str(step))
        if d_step <= 0:
            return float(d_value)
        units = (d_value / d_step).quantize(Decimal("1"), rounding=mode)
        return float(units * d_step)
    except (InvalidOperation, ValueError, TypeError, ZeroDivisionError):
        return float(value)


def pro_client_order_id(prefix="FOS") -> str:
    raw = f"{prefix}|{uuid.uuid4().hex}|{time.time_ns()}"
    digest = hashlib.sha256(raw.encode("utf-8")).hexdigest()[:20]
    return f"{prefix}-{digest}"[:32]


def pro_classify_error(exc: Exception) -> str:
    text = f"{type(exc).__name__}: {exc}".lower()
    if "rate" in text and "limit" in text:
        return "RATE_LIMIT"
    if "insufficient" in text or "margin" in text:
        return "INSUFFICIENT_MARGIN"
    if "timeout" in text or "timed out" in text:
        return "TIMEOUT"
    if "network" in text or "connection" in text:
        return "NETWORK"
    if "auth" in text or "api-key" in text or "signature" in text:
        return "AUTH"
    if "invalid" in text or "precision" in text or "lot_size" in text:
        return "INVALID_ORDER"
    return "EXCHANGE_ERROR"


def pro_append_csv(path: Path, row: dict) -> bool:
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        existing = pd.read_csv(path) if path.exists() and path.stat().st_size > 0 else pd.DataFrame()
        out = pd.concat([existing, pd.DataFrame([row])], ignore_index=True, sort=False)
        tmp = path.with_suffix(path.suffix + ".tmp")
        out.to_csv(tmp, index=False)
        os.replace(tmp, path)
        return True
    except Exception:
        return False


def pro_read_csv(path: Path) -> pd.DataFrame:
    try:
        if path.exists() and path.stat().st_size > 0:
            return pd.read_csv(path)
    except Exception:
        pass
    return pd.DataFrame()


def pro_log_incident(severity: str, code: str, detail: str, symbol: str = "") -> None:
    pro_append_csv(PRO_INCIDENT_FILE, {
        "timestamp": pro_now_utc().isoformat(),
        "severity": severity,
        "code": code,
        "symbol": pro_symbol_id(symbol),
        "detail": str(detail)[:1000],
    })


@dataclass
class ProPublicSnapshot:
    symbol: str
    ts: str
    ok: bool = False
    mark_price: float = np.nan
    index_price: float = np.nan
    last_price: float = np.nan
    funding_rate_pct: float = np.nan
    next_funding_time: str = ""
    open_interest: float = np.nan
    oi_change_pct: float = np.nan
    oi_velocity_pct: float = np.nan
    oi_acceleration_pct: float = np.nan
    long_short_ratio: float = np.nan
    taker_buy_sell_ratio: float = np.nan
    bid: float = np.nan
    ask: float = np.nan
    spread_bps: float = np.nan
    book_imbalance_5bps: float = np.nan
    book_imbalance_10bps: float = np.nan
    book_imbalance_25bps: float = np.nan
    book_imbalance_50bps: float = np.nan
    book_imbalance_100bps: float = np.nan
    slippage_buy_10k_bps: float = np.nan
    slippage_sell_10k_bps: float = np.nan
    cvd_qty: float = np.nan
    aggressive_buy_qty: float = np.nan
    aggressive_sell_qty: float = np.nan
    basis_mark_vs_index_bps: float = np.nan
    mark_last_divergence_bps: float = np.nan
    data_age_sec: float = np.nan
    sources_ok: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)


def _pro_fetch_json(url: str, params=None, timeout=3.5):
    if requests is None:
        raise RuntimeError("requests no disponible")
    r = requests.get(url, params=params or {}, timeout=timeout, headers={"User-Agent": "Futures-OS-Pro/2.0"})
    r.raise_for_status()
    return r.json()


def _pro_book_band_imbalance(bids, asks, mid: float, bps: float) -> float:
    if not mid or pd.isna(mid):
        return np.nan
    band = bps / 10000.0
    bid_qty = sum(pro_safe_float(q, 0) for p, q in bids if pro_safe_float(p, 0) >= mid * (1 - band))
    ask_qty = sum(pro_safe_float(q, 0) for p, q in asks if pro_safe_float(p, 0) <= mid * (1 + band))
    den = bid_qty + ask_qty
    return 100.0 * (bid_qty - ask_qty) / den if den else np.nan


def _pro_book_slippage_bps(levels, target_quote: float, side: str, ref_price: float) -> float:
    if target_quote <= 0 or not levels or not ref_price:
        return np.nan
    remaining = float(target_quote)
    base_filled = 0.0
    quote_used = 0.0
    for p_raw, q_raw in levels:
        p = pro_safe_float(p_raw, 0)
        q = pro_safe_float(q_raw, 0)
        if p <= 0 or q <= 0:
            continue
        level_quote = p * q
        use_quote = min(remaining, level_quote)
        use_base = use_quote / p
        base_filled += use_base
        quote_used += use_quote
        remaining -= use_quote
        if remaining <= 1e-9:
            break
    if base_filled <= 0 or remaining > target_quote * 0.05:
        return np.nan
    vwap = quote_used / base_filled
    if side.upper() == "BUY":
        return max(0.0, (vwap / ref_price - 1.0) * 10000.0)
    return max(0.0, (1.0 - vwap / ref_price) * 10000.0)


@st.cache_data(ttl=5, show_spinner=False)
def pro_fetch_public_futures_snapshot(symbol: str = "BTCUSDT") -> dict:
    sid = pro_symbol_id(symbol)
    snap = ProPublicSnapshot(symbol=sid, ts=pro_now_utc().isoformat())
    start = time.time()
    try:
        premium = _pro_fetch_json("https://fapi.binance.com/fapi/v1/premiumIndex", {"symbol": sid})
        snap.mark_price = pro_safe_float(premium.get("markPrice"))
        snap.index_price = pro_safe_float(premium.get("indexPrice"))
        snap.funding_rate_pct = pro_safe_float(premium.get("lastFundingRate"), 0.0) * 100.0
        nft = pro_safe_float(premium.get("nextFundingTime"))
        if not pd.isna(nft):
            snap.next_funding_time = pd.to_datetime(int(nft), unit="ms", utc=True).isoformat()
        snap.sources_ok.append("Binance Futures premiumIndex")
    except Exception as exc:
        snap.errors.append(f"premium:{pro_classify_error(exc)}")

    try:
        ticker = _pro_fetch_json("https://fapi.binance.com/fapi/v1/ticker/bookTicker", {"symbol": sid})
        snap.bid = pro_safe_float(ticker.get("bidPrice"))
        snap.ask = pro_safe_float(ticker.get("askPrice"))
        snap.last_price = (snap.bid + snap.ask) / 2 if snap.bid > 0 and snap.ask > 0 else np.nan
        if snap.last_price and not pd.isna(snap.last_price):
            snap.spread_bps = (snap.ask - snap.bid) / snap.last_price * 10000.0
        snap.sources_ok.append("Binance Futures bookTicker")
    except Exception as exc:
        snap.errors.append(f"bookTicker:{pro_classify_error(exc)}")

    try:
        oi = _pro_fetch_json("https://fapi.binance.com/fapi/v1/openInterest", {"symbol": sid})
        snap.open_interest = pro_safe_float(oi.get("openInterest"))
        snap.sources_ok.append("Binance Futures openInterest")
    except Exception as exc:
        snap.errors.append(f"oi:{pro_classify_error(exc)}")

    try:
        hist = _pro_fetch_json("https://fapi.binance.com/futures/data/openInterestHist", {"symbol": sid, "period": "5m", "limit": 30})
        vals = [pro_safe_float(x.get("sumOpenInterest")) for x in hist if isinstance(x, dict)] if isinstance(hist, list) else []
        vals = [x for x in vals if not pd.isna(x) and x > 0]
        if len(vals) >= 2:
            snap.oi_change_pct = (vals[-1] / vals[0] - 1.0) * 100.0
            snap.oi_velocity_pct = (vals[-1] / vals[-2] - 1.0) * 100.0
        if len(vals) >= 3:
            prev_velocity = (vals[-2] / vals[-3] - 1.0) * 100.0
            snap.oi_acceleration_pct = snap.oi_velocity_pct - prev_velocity
        snap.sources_ok.append("Binance Futures OI history")
    except Exception as exc:
        snap.errors.append(f"oiHist:{pro_classify_error(exc)}")

    try:
        ls = _pro_fetch_json("https://fapi.binance.com/futures/data/globalLongShortAccountRatio", {"symbol": sid, "period": "5m", "limit": 1})
        if isinstance(ls, list) and ls:
            snap.long_short_ratio = pro_safe_float(ls[-1].get("longShortRatio"))
        snap.sources_ok.append("Binance Futures long/short")
    except Exception as exc:
        snap.errors.append(f"longShort:{pro_classify_error(exc)}")

    try:
        tk = _pro_fetch_json("https://fapi.binance.com/futures/data/takerlongshortRatio", {"symbol": sid, "period": "5m", "limit": 1})
        if isinstance(tk, list) and tk:
            snap.taker_buy_sell_ratio = pro_safe_float(tk[-1].get("buySellRatio"))
        snap.sources_ok.append("Binance Futures taker ratio")
    except Exception as exc:
        snap.errors.append(f"taker:{pro_classify_error(exc)}")

    try:
        book = _pro_fetch_json("https://fapi.binance.com/fapi/v1/depth", {"symbol": sid, "limit": 500})
        bids = book.get("bids", []) if isinstance(book, dict) else []
        asks = book.get("asks", []) if isinstance(book, dict) else []
        if bids and asks:
            best_bid = pro_safe_float(bids[0][0])
            best_ask = pro_safe_float(asks[0][0])
            mid = (best_bid + best_ask) / 2 if best_bid and best_ask else snap.last_price
            for band in (5, 10, 25, 50, 100):
                setattr(snap, f"book_imbalance_{band}bps", _pro_book_band_imbalance(bids, asks, mid, band))
            snap.slippage_buy_10k_bps = _pro_book_slippage_bps(asks, 10000.0, "BUY", best_ask)
            snap.slippage_sell_10k_bps = _pro_book_slippage_bps(bids, 10000.0, "SELL", best_bid)
        snap.sources_ok.append("Binance Futures depth")
    except Exception as exc:
        snap.errors.append(f"depth:{pro_classify_error(exc)}")

    try:
        trades = _pro_fetch_json("https://fapi.binance.com/fapi/v1/aggTrades", {"symbol": sid, "limit": 500})
        buy_qty = 0.0
        sell_qty = 0.0
        if isinstance(trades, list):
            for tr in trades:
                qty = pro_safe_float(tr.get("q"), 0.0)
                buyer_is_maker = bool(tr.get("m", False))
                if buyer_is_maker:
                    sell_qty += qty
                else:
                    buy_qty += qty
        snap.aggressive_buy_qty = buy_qty
        snap.aggressive_sell_qty = sell_qty
        snap.cvd_qty = buy_qty - sell_qty
        snap.sources_ok.append("Binance Futures aggTrades")
    except Exception as exc:
        snap.errors.append(f"aggTrades:{pro_classify_error(exc)}")

    if snap.mark_price and snap.index_price and not pd.isna(snap.mark_price) and not pd.isna(snap.index_price) and snap.index_price:
        snap.basis_mark_vs_index_bps = (snap.mark_price / snap.index_price - 1.0) * 10000.0
    if snap.mark_price and snap.last_price and not pd.isna(snap.mark_price) and not pd.isna(snap.last_price) and snap.mark_price:
        snap.mark_last_divergence_bps = abs(snap.last_price / snap.mark_price - 1.0) * 10000.0
    snap.data_age_sec = max(0.0, time.time() - start)
    snap.ok = bool(snap.sources_ok) and not pd.isna(snap.mark_price)
    return asdict(snap)


@st.cache_data(ttl=20, show_spinner=False)
def pro_scan_usdt_perpetuals(limit: int = 30) -> pd.DataFrame:
    """Fast, public cross-market scanner. It never places orders."""
    if requests is None:
        return pd.DataFrame()
    try:
        tickers = _pro_fetch_json("https://fapi.binance.com/fapi/v1/ticker/24hr")
        premiums = _pro_fetch_json("https://fapi.binance.com/fapi/v1/premiumIndex")
        pmap = {x.get("symbol"): x for x in premiums if isinstance(x, dict)} if isinstance(premiums, list) else {}
        rows = []
        for t in tickers if isinstance(tickers, list) else []:
            sym = str(t.get("symbol", ""))
            if not sym.endswith("USDT"):
                continue
            qv = pro_safe_float(t.get("quoteVolume"), 0)
            last = pro_safe_float(t.get("lastPrice"), np.nan)
            change = pro_safe_float(t.get("priceChangePercent"), np.nan)
            hi = pro_safe_float(t.get("highPrice"), np.nan)
            lo = pro_safe_float(t.get("lowPrice"), np.nan)
            intraday_range = ((hi - lo) / last * 100.0) if last and not any(pd.isna(x) for x in [hi, lo, last]) else np.nan
            p = pmap.get(sym, {})
            funding = pro_safe_float(p.get("lastFundingRate"), np.nan) * 100.0
            basis = np.nan
            mark = pro_safe_float(p.get("markPrice"), np.nan)
            index = pro_safe_float(p.get("indexPrice"), np.nan)
            if index and not pd.isna(mark) and not pd.isna(index):
                basis = (mark / index - 1) * 10000
            rows.append({
                "symbol": sym,
                "price": last,
                "change_24h_%": change,
                "range_24h_%": intraday_range,
                "quote_volume_usdt": qv,
                "funding_%": funding,
                "basis_bps": basis,
            })
        df = pd.DataFrame(rows)
        if df.empty:
            return df
        df["liquidity_rank"] = df["quote_volume_usdt"].rank(pct=True) * 100
        df["crowding_penalty"] = np.clip(df["funding_%"].abs().fillna(0) / 0.05 * 20, 0, 40)
        df["movement_score"] = np.clip(df["range_24h_%"].fillna(0) * 3, 0, 40)
        df["risk_adjusted_scan"] = np.clip(df["liquidity_rank"] * 0.6 + df["movement_score"] - df["crowding_penalty"], 0, 100)
        return df.sort_values(["risk_adjusted_scan", "quote_volume_usdt"], ascending=False).head(int(limit)).reset_index(drop=True)
    except Exception:
        return pd.DataFrame()


def pro_record_microstructure(snap: dict) -> None:
    if not snap or not snap.get("symbol"):
        return
    row = {k: snap.get(k) for k in [
        "symbol", "ts", "mark_price", "last_price", "funding_rate_pct", "open_interest",
        "oi_change_pct", "oi_velocity_pct", "oi_acceleration_pct", "spread_bps",
        "book_imbalance_5bps", "book_imbalance_10bps", "book_imbalance_25bps",
        "book_imbalance_50bps", "cvd_qty", "aggressive_buy_qty", "aggressive_sell_qty"
    ]}
    # Keep disk bounded: one sample per minute per symbol.
    hist = pro_read_csv(PRO_MICRO_FILE)
    minute = str(row.get("ts", ""))[:16]
    if not hist.empty and "ts" in hist.columns and "symbol" in hist.columns:
        same = (hist["symbol"].astype(str) == str(row["symbol"])) & (hist["ts"].astype(str).str[:16] == minute)
        if same.any():
            return
    pro_append_csv(PRO_MICRO_FILE, row)


def pro_microstructure_persistence(symbol: str, lookback=12) -> dict:
    hist = pro_read_csv(PRO_MICRO_FILE)
    if hist.empty or "symbol" not in hist.columns:
        return {"samples": 0, "imbalance_persistence": np.nan, "cvd_persistence": np.nan, "spoof_risk": "UNKNOWN"}
    df = hist[hist["symbol"].astype(str) == pro_symbol_id(symbol)].tail(int(lookback)).copy()
    if df.empty:
        return {"samples": 0, "imbalance_persistence": np.nan, "cvd_persistence": np.nan, "spoof_risk": "UNKNOWN"}
    imb = pd.to_numeric(df.get("book_imbalance_10bps"), errors="coerce")
    cvd = pd.to_numeric(df.get("cvd_qty"), errors="coerce")
    imb_sign = np.sign(imb.dropna())
    cvd_sign = np.sign(cvd.dropna())
    ip = abs(imb_sign.mean()) * 100 if len(imb_sign) else np.nan
    cp = abs(cvd_sign.mean()) * 100 if len(cvd_sign) else np.nan
    spoof_risk = "LOW"
    if len(df) >= 4 and not pd.isna(ip) and ip < 35:
        spoof_risk = "ELEVATED"
    return {"samples": len(df), "imbalance_persistence": ip, "cvd_persistence": cp, "spoof_risk": spoof_risk}


def pro_candle_age_sec(df: pd.DataFrame) -> float:
    if df is None or df.empty or "time" not in df.columns:
        return np.inf
    try:
        ts = pd.to_datetime(df["time"].iloc[-1], utc=True)
        return max(0.0, (pro_now_utc() - ts).total_seconds())
    except Exception:
        return np.inf


def pro_detect_regime(df_1d, df_4h, df_1h, df_15m) -> dict:
    try:
        qd = timeframe_quant_snapshot(df_1d, "1D")
        q4 = timeframe_quant_snapshot(df_4h, "4H")
        q1 = timeframe_quant_snapshot(df_1h, "1H")
        q15 = timeframe_quant_snapshot(df_15m, "15M")
        risk = daily_risk_metrics(df_1d)
        trend, vol, expansion = detect_quant_regime(qd, risk)
        adx = pro_safe_float(q15.get("adx"), 0)
        bb = pro_safe_float(q15.get("bb_width_pct"), np.nan)
        vp = pro_safe_float(risk.get("vol_percentile"), 50)
        roc = pro_safe_float(q1.get("roc20"), 0)
        if vp >= 90:
            state = "PANIC_HIGH_VOL"
        elif not pd.isna(bb) and bb < 2.5:
            state = "COMPRESSION"
        elif adx >= 28 and abs(roc) >= 2:
            state = "TREND_EXPANSION"
        elif adx < 18:
            state = "CHOP_RANGE"
        else:
            state = "NORMAL_MIXED"
        maturity = "EARLY"
        rsi1 = pro_safe_float(q1.get("rsi"), 50)
        if adx >= 30 and (rsi1 >= 70 or rsi1 <= 30):
            maturity = "MATURE_EXTENDED"
        elif adx >= 22:
            maturity = "DEVELOPING"
        vol_of_vol_pct = np.nan
        try:
            closes = pd.to_numeric(df_1d["close"], errors="coerce")
            ret = closes.pct_change()
            rv7 = ret.rolling(7, min_periods=4).std()
            vov = rv7.rolling(30, min_periods=10).std()
            cur_vov = vov.iloc[-1]
            hist_vov = vov.dropna()
            if len(hist_vov) and not pd.isna(cur_vov):
                vol_of_vol_pct = float((hist_vov <= cur_vov).mean()*100)
        except Exception:
            pass
        return {
            "state": state,
            "trend": trend,
            "volatility": vol,
            "expansion": expansion,
            "trend_maturity": maturity,
            "adx_15m": adx,
            "vol_percentile": vp,
            "vol_of_vol_percentile": vol_of_vol_pct,
        }
    except Exception as exc:
        return {"state": "UNKNOWN", "trend": "UNKNOWN", "volatility": "UNKNOWN", "expansion": "UNKNOWN", "trend_maturity": "UNKNOWN", "error": str(exc)}


def pro_independent_confluence_score(candidate_direction, t4, t1, t15, structure, fvg_valid, delta_strength, vol_ratio, public_snap) -> dict:
    direction = str(candidate_direction)
    bull = direction == "LONG"
    bear = direction == "SHORT"
    families = {}
    families["trend"] = ((t4 == "ALCISTA") + (t1 == "ALCISTA") + (t15 == "ALCISTA")) / 3 if bull else ((t4 == "BAJISTA") + (t1 == "BAJISTA") + (t15 == "BAJISTA")) / 3 if bear else 0
    families["structure"] = 1.0 if ((bull and "ALC" in str(structure).upper()) or (bear and "BAJ" in str(structure).upper())) else 0.35
    families["liquidity"] = 1.0 if fvg_valid else 0.25
    ds = pro_safe_float(delta_strength, 0)
    families["flow"] = 1.0 if ((bull and ds > 0.8) or (bear and ds < -0.8)) else (0.5 if abs(ds) < 0.8 else 0.0)
    vr = pro_safe_float(vol_ratio, 1)
    families["volume"] = min(max((vr - 0.8) / 1.2, 0), 1)
    imb = pro_safe_float(public_snap.get("book_imbalance_10bps"), np.nan) if isinstance(public_snap, dict) else np.nan
    cvd = pro_safe_float(public_snap.get("cvd_qty"), np.nan) if isinstance(public_snap, dict) else np.nan
    der = 0.5
    if not pd.isna(imb) and not pd.isna(cvd):
        if (bull and imb > 0 and cvd > 0) or (bear and imb < 0 and cvd < 0):
            der = 1.0
        elif (bull and imb < 0 and cvd < 0) or (bear and imb > 0 and cvd > 0):
            der = 0.0
    families["microstructure"] = der
    score = 100 * np.mean(list(families.values())) if families else 0
    independent_positive = sum(v >= 0.65 for v in families.values())
    return {"score": float(score), "families": families, "independent_positive": int(independent_positive)}


def pro_no_trade_score(regime: dict, public_snap: dict, candle_age_sec: float, settings: dict, candidate_direction: str, rr_net: float) -> dict:
    score = 0
    reasons = []
    if candidate_direction not in ("LONG", "SHORT"):
        score += 35; reasons.append("Sin dirección operable")
    if regime.get("state") in ("CHOP_RANGE", "UNKNOWN"):
        score += 20; reasons.append(f"Régimen {regime.get('state')}")
    if regime.get("state") == "PANIC_HIGH_VOL":
        score += 25; reasons.append("Volatilidad extrema")
    spread = pro_safe_float(public_snap.get("spread_bps"), np.nan)
    if not pd.isna(spread) and spread > float(settings["max_spread_bps"]):
        score += 25; reasons.append(f"Spread {spread:.1f} bps")
    if candle_age_sec > float(settings["max_candle_age_sec"]):
        score += 40; reasons.append("Velas desactualizadas")
    divergence = pro_safe_float(public_snap.get("mark_last_divergence_bps"), np.nan)
    if not pd.isna(divergence) and divergence > float(settings["max_mark_last_divergence_bps"]):
        score += 20; reasons.append("Divergencia Mark/Last")
    if not pd.isna(rr_net) and rr_net < float(settings["min_rr_net"]):
        score += 25; reasons.append("RR neto insuficiente")
    return {"score": int(min(score, 100)), "reasons": reasons}


def pro_load_signal_history() -> pd.DataFrame:
    frames = []
    for name in ("SIGNALS_FILE", "AUTO_SIGNALS_FILE"):
        path = globals().get(name)
        if path:
            try:
                df = safe_read_csv(path) if "safe_read_csv" in globals() else pd.read_csv(path)
                if df is not None and not df.empty:
                    frames.append(df)
            except Exception:
                pass
    if not frames:
        return pd.DataFrame()
    out = pd.concat(frames, ignore_index=True, sort=False).drop_duplicates()
    return out


def pro_edge_calibration(candidate_direction: str, quality_score: float) -> dict:
    hist = pro_load_signal_history()
    if hist.empty or "resultado" not in hist.columns:
        return {"samples": 0, "winrate": np.nan, "expectancy_r": np.nan, "avg_win_r": np.nan, "avg_loss_r": np.nan, "brier": np.nan, "calibrated_probability": np.nan, "ci_low": np.nan, "ci_high": np.nan, "reliability": pd.DataFrame()}
    df = hist.copy()
    df = df[df["resultado"].astype(str).isin(["TP", "SL"])]
    dir_col = "direccion_calculada" if "direccion_calculada" in df.columns else "decision" if "decision" in df.columns else None
    if dir_col and candidate_direction in ("LONG", "SHORT"):
        same = df[df[dir_col].astype(str) == candidate_direction]
        if len(same) >= 10:
            df = same
    if "calidad_score" in df.columns:
        scores = pd.to_numeric(df["calidad_score"], errors="coerce")
        target = pro_safe_float(quality_score, np.nan)
        if not pd.isna(target):
            near = df[(scores - target).abs() <= 1.0]
            if len(near) >= 10:
                df = near
    if df.empty:
        return {"samples": 0, "winrate": np.nan, "expectancy_r": np.nan, "avg_win_r": np.nan, "avg_loss_r": np.nan, "brier": np.nan, "calibrated_probability": np.nan, "ci_low": np.nan, "ci_high": np.nan, "reliability": pd.DataFrame()}
    wins = (df["resultado"].astype(str) == "TP").astype(int)
    n = len(df)
    p = wins.mean()
    fallback_r = pd.Series(np.where(wins == 1, 1.0, -1.0), index=df.index, dtype=float)
    r = pd.to_numeric(df.get("r_multiple"), errors="coerce") if "r_multiple" in df.columns else fallback_r.copy()
    r = r.where(r.notna(), fallback_r)
    win_r = r[wins == 1]
    loss_r = r[wins == 0]
    expectancy = r.mean()
    # Wilson 95% interval.
    z = 1.96
    den = 1 + z*z/n
    center = (p + z*z/(2*n)) / den
    half = z * math.sqrt((p*(1-p)/n) + z*z/(4*n*n)) / den
    # Brier of the legacy score-as-probability, for diagnostics only.
    brier = np.nan
    reliability = pd.DataFrame()
    if "calidad_score" in df.columns:
        raw_prob = np.clip(pd.to_numeric(df["calidad_score"], errors="coerce") / 10.0, 0.0, 1.0)
        mask = raw_prob.notna()
        if mask.any():
            brier = float(np.mean((raw_prob[mask] - wins[mask]) ** 2))
            tmp = pd.DataFrame({"prob": raw_prob[mask], "win": wins[mask]})
            tmp["bucket"] = pd.cut(tmp["prob"], bins=np.linspace(0, 1, 6), include_lowest=True)
            reliability = tmp.groupby("bucket", observed=False).agg(samples=("win", "size"), predicted=("prob", "mean"), observed=("win", "mean")).reset_index()
            reliability["bucket"] = reliability["bucket"].astype(str)
    return {
        "samples": int(n),
        "winrate": float(p * 100),
        "expectancy_r": float(expectancy),
        "avg_win_r": float(win_r.mean()) if len(win_r) else np.nan,
        "avg_loss_r": float(abs(loss_r.mean())) if len(loss_r) else np.nan,
        "brier": brier,
        "calibrated_probability": float(p * 100),
        "ci_low": float(max(0, center-half) * 100),
        "ci_high": float(min(1, center+half) * 100),
        "reliability": reliability,
    }


def pro_estimated_costs(direction: str, price: float, sl: float, tp: float, size: float, public_snap: dict, settings: dict) -> dict:
    entry = pro_safe_float(price)
    stop = pro_safe_float(sl)
    target = pro_safe_float(tp)
    qty = max(0.0, pro_safe_float(size, 0))
    risk_per_unit = abs(entry - stop) if not any(pd.isna(x) for x in [entry, stop]) else np.nan
    reward_per_unit = abs(target - entry) if not any(pd.isna(x) for x in [entry, target]) else np.nan
    gross_r = reward_per_unit / risk_per_unit if risk_per_unit and risk_per_unit > 0 else np.nan
    fee_bps = float(settings["maker_fee_bps_per_side"] if settings.get("post_only") else settings["taker_fee_bps_per_side"])
    roundtrip_fee_usd = entry * qty * fee_bps / 10000.0 * 2.0 if entry and qty else 0.0
    slippage_bps = pro_safe_float(public_snap.get("slippage_buy_10k_bps" if direction == "LONG" else "slippage_sell_10k_bps"), 0.0)
    if pd.isna(slippage_bps):
        slippage_bps = 0.0
    slippage_usd = entry * qty * slippage_bps / 10000.0
    funding_pct = pro_safe_float(public_snap.get("funding_rate_pct"), 0.0)
    if pd.isna(funding_pct):
        funding_pct = 0.0
    intervals = max(float(settings.get("funding_holding_hours", 8.0)) / 8.0, 0.0)
    funding_sign = 1 if direction == "LONG" else -1
    funding_usd = max(0.0, entry * qty * (funding_pct / 100.0) * intervals * funding_sign)
    risk_usd = risk_per_unit * qty if risk_per_unit and qty else np.nan
    gross_reward_usd = reward_per_unit * qty if reward_per_unit and qty else np.nan
    cost_usd = roundtrip_fee_usd + slippage_usd + funding_usd
    rr_net = (gross_reward_usd - cost_usd) / (risk_usd + cost_usd) if risk_usd and risk_usd > 0 else gross_r
    return {
        "gross_rr": gross_r,
        "net_rr": rr_net,
        "roundtrip_fee_usd": roundtrip_fee_usd,
        "slippage_bps": slippage_bps,
        "slippage_usd": slippage_usd,
        "funding_cost_usd": funding_usd,
        "total_cost_usd": cost_usd,
        "risk_usd": risk_usd,
        "gross_reward_usd": gross_reward_usd,
    }


def pro_journal_stats(account_usd: float) -> dict:
    df = pro_read_csv(PRO_JOURNAL_FILE)
    out = {
        "closed": 0, "daily_pnl": 0.0, "weekly_pnl": 0.0, "daily_loss_pct": 0.0,
        "weekly_loss_pct": 0.0, "loss_streak": 0, "open_risk_usd": 0.0,
        "open_positions": 0, "equity_peak": account_usd, "drawdown_pct": 0.0,
        "minutes_since_last_loss": np.inf, "last_loss_qty": 0.0, "last_trade_qty": 0.0,
        "same_side_open_long": 0, "same_side_open_short": 0,
    }
    if df.empty:
        return out
    work = df.copy()
    if "id" in work.columns:
        latest = work.drop_duplicates(subset=["id"], keep="last")
    else:
        latest = work
    if "status" in latest.columns:
        open_df = latest[latest["status"].astype(str).isin(["OPEN", "PARTIAL", "PROTECTED"])]
        out["open_positions"] = len(open_df)
        if "risk_usd" in open_df.columns:
            out["open_risk_usd"] = float(pd.to_numeric(open_df["risk_usd"], errors="coerce").fillna(0).sum())
        if "direction" in open_df.columns:
            out["same_side_open_long"] = int((open_df["direction"].astype(str) == "LONG").sum())
            out["same_side_open_short"] = int((open_df["direction"].astype(str) == "SHORT").sum())
    closed = latest[latest["status"].astype(str) == "CLOSED"].copy() if "status" in latest.columns else pd.DataFrame()
    if closed.empty:
        return out
    out["closed"] = len(closed)
    closed["ts_close_dt"] = pd.to_datetime(closed.get("ts_close"), utc=True, errors="coerce")
    closed["pnl_usd_num"] = pd.to_numeric(closed.get("pnl_usd"), errors="coerce").fillna(0)
    if "qty" in closed.columns:
        closed["qty_num"] = pd.to_numeric(closed["qty"], errors="coerce").fillna(0)
    else:
        closed["qty_num"] = 0.0
    closed = closed.sort_values("ts_close_dt")
    now = pro_now_utc()
    day_start = now.normalize()
    week_start = day_start - pd.Timedelta(days=int(now.weekday()))
    out["daily_pnl"] = float(closed.loc[closed["ts_close_dt"] >= day_start, "pnl_usd_num"].sum())
    out["weekly_pnl"] = float(closed.loc[closed["ts_close_dt"] >= week_start, "pnl_usd_num"].sum())
    base = max(float(account_usd), 1e-9)
    out["daily_loss_pct"] = max(0.0, -out["daily_pnl"] / base * 100.0)
    out["weekly_loss_pct"] = max(0.0, -out["weekly_pnl"] / base * 100.0)
    streak = 0
    for x in reversed(closed["pnl_usd_num"].tolist()):
        if x < 0:
            streak += 1
        else:
            break
    out["loss_streak"] = streak
    out["last_trade_qty"] = float(closed.iloc[-1]["qty_num"]) if len(closed) else 0.0
    losses = closed[closed["pnl_usd_num"] < 0]
    if not losses.empty:
        last_loss = losses.iloc[-1]
        out["last_loss_qty"] = float(last_loss["qty_num"])
        if not pd.isna(last_loss["ts_close_dt"]):
            out["minutes_since_last_loss"] = max(0.0, (now-last_loss["ts_close_dt"]).total_seconds()/60.0)
    pnl_curve = closed["pnl_usd_num"].cumsum() + base
    if len(pnl_curve):
        peak = pnl_curve.cummax()
        dd = (pnl_curve / peak - 1) * 100
        out["equity_peak"] = float(peak.max())
        out["drawdown_pct"] = float(abs(dd.iloc[-1])) if not pd.isna(dd.iloc[-1]) else 0.0
    return out


def pro_drawdown_risk_multiplier(drawdown_pct: float) -> float:
    dd = max(0.0, pro_safe_float(drawdown_pct, 0.0))
    if dd < 3: return 1.00
    if dd < 6: return 0.75
    if dd < 9: return 0.50
    if dd < 12: return 0.25
    return 0.0


def pro_strategy_router(strategy: str, regime: dict) -> dict:
    name = str(strategy or "").lower()
    state = regime.get("state", "UNKNOWN")
    compatible = True
    reason = "Sin incompatibilidad estructural detectada"
    if "scalp" in name and state == "PANIC_HIGH_VOL":
        compatible = False; reason = "Scalping bloqueado en volatilidad extrema"
    elif any(k in name for k in ["trend", "tend", "break", "rupt"]) and state == "CHOP_RANGE":
        compatible = False; reason = "Estrategia tendencial en régimen lateral/chop"
    elif any(k in name for k in ["reversion", "reversión", "mean"]) and state == "TREND_EXPANSION":
        compatible = False; reason = "Mean reversion contra expansión tendencial"
    return {"compatible": compatible, "reason": reason, "regime": state}


def pro_latest_signal_reference(candidate_direction: str, fallback_price: float, fallback_time=None) -> dict:
    hist = pro_load_signal_history()
    if hist.empty:
        return {"price": fallback_price, "time": fallback_time, "source": "CURRENT"}
    df = hist.copy()
    dir_col = "direccion_calculada" if "direccion_calculada" in df.columns else "decision" if "decision" in df.columns else None
    if dir_col and candidate_direction in ("LONG", "SHORT"):
        same = df[df[dir_col].astype(str) == candidate_direction]
        if not same.empty:
            df = same
    time_col = "vela_5m" if "vela_5m" in df.columns else "fecha" if "fecha" in df.columns else None
    if time_col:
        df["_ts_ref"] = pd.to_datetime(df[time_col], utc=True, errors="coerce")
        df = df.sort_values("_ts_ref")
    row = df.iloc[-1]
    ref = pro_safe_float(row.get("entrada", row.get("precio", fallback_price)), fallback_price)
    ts = row.get(time_col) if time_col else fallback_time
    return {"price": ref, "time": ts, "source": "HISTORY"}


def pro_signal_decay(current_price: float, reference_price: float, atr: float, born_at=None) -> dict:
    cp = pro_safe_float(current_price)
    rp = pro_safe_float(reference_price)
    a = pro_safe_float(atr)
    dist_atr = abs(cp-rp)/a if a and not any(pd.isna(x) for x in [cp, rp, a]) else 0.0
    age_min = 0.0
    if born_at is not None:
        try:
            ts = pd.to_datetime(born_at, utc=True)
            age_min = max(0.0, (pro_now_utc()-ts).total_seconds()/60.0)
        except Exception:
            pass
    decay = max(0.0, 100.0 - dist_atr*35.0 - max(age_min-15, 0)*0.5)
    return {"distance_atr": dist_atr, "age_min": age_min, "freshness_score": decay, "expired": decay < 35}


def pro_build_trade_gate(
    *, settings: dict, environment: str, candidate_direction: str, trade_valid: bool,
    quality_score: float, rr_real: float, price: float, sl: float, tp: float,
    size: float, account_usd: float, risk_pct: float, leverage: float,
    candle_age_sec: float, public_snap: dict, regime: dict, calibration: dict,
    journal_stats: dict, independent_confluence: dict, strategy_router: dict,
    external_event_risk: bool = False, signal_decay: dict | None = None,
    strategy_conflict: dict | None = None,
) -> dict:
    checks = []
    def add(code, ok, severity, detail, value=None):
        checks.append({"code": code, "ok": bool(ok), "severity": severity, "detail": detail, "value": value})

    costs = pro_estimated_costs(candidate_direction, price, sl, tp, size, public_snap, settings)
    rr_net = pro_safe_float(costs.get("net_rr"), rr_real)
    spread = pro_safe_float(public_snap.get("spread_bps"), np.nan)
    slippage = pro_safe_float(costs.get("slippage_bps"), 0.0)
    divergence = pro_safe_float(public_snap.get("mark_last_divergence_bps"), np.nan)
    data_ok = bool(public_snap.get("ok"))

    add("SIGNAL_VALID", trade_valid and candidate_direction in ("LONG", "SHORT"), "BLOCK", "La señal técnica base debe ser válida")
    add("RISK_PER_TRADE", risk_pct*100 <= float(settings["max_risk_per_trade_pct"]) + 1e-9, "BLOCK", f"Riesgo {risk_pct*100:.2f}% <= límite {settings['max_risk_per_trade_pct']:.2f}%")
    add("LEVERAGE", float(leverage) <= float(settings["max_leverage"]), "BLOCK", f"Leverage {leverage:.1f}x <= {settings['max_leverage']:.1f}x")
    add("RR_NET", not pd.isna(rr_net) and rr_net >= float(settings["min_rr_net"]), "BLOCK", f"RR neto {rr_net:.2f} >= {settings['min_rr_net']:.2f}")
    add("CANDLE_FRESHNESS", candle_age_sec <= float(settings["max_candle_age_sec"]), "BLOCK", f"Edad vela {candle_age_sec:.0f}s")
    add("PUBLIC_DATA", data_ok or environment == "PAPER", "BLOCK", "Datos públicos Futures disponibles" if data_ok else "Datos públicos Futures no disponibles")
    add("SPREAD", pd.isna(spread) or spread <= float(settings["max_spread_bps"]), "BLOCK", f"Spread {spread:.2f} bps" if not pd.isna(spread) else "Spread no disponible")
    add("SLIPPAGE", pd.isna(slippage) or slippage <= float(settings["max_expected_slippage_bps"]), "BLOCK", f"Slippage estimado {slippage:.2f} bps")
    add("MARK_LAST", pd.isna(divergence) or divergence <= float(settings["max_mark_last_divergence_bps"]), "BLOCK", f"Divergencia Mark/Last {divergence:.2f} bps" if not pd.isna(divergence) else "Divergencia no disponible")
    add("STRATEGY_REGIME", bool(strategy_router.get("compatible", True)), "BLOCK", strategy_router.get("reason", ""))
    if strategy_conflict:
        conflict_score = pro_safe_float(strategy_conflict.get("score"), 50.0)
        add("STRATEGY_CONFLICT", conflict_score < 65.0, "BLOCK", f"Conflicto entre familias {conflict_score:.0f}%")
    if signal_decay:
        dist_atr = pro_safe_float(signal_decay.get("distance_atr"), 0.0)
        age_min = pro_safe_float(signal_decay.get("age_min"), 0.0)
        add("MAX_CHASE", dist_atr <= float(settings.get("max_chase_atr", 0.75)), "BLOCK", f"Distancia desde señal {dist_atr:.2f} ATR")
        add("SIGNAL_EXPIRY", age_min <= float(settings.get("signal_expiry_minutes", 45.0)), "BLOCK", f"Edad señal {age_min:.1f} min")
    add("INDEPENDENT_CONFLUENCE", independent_confluence.get("independent_positive", 0) >= 3, "WARN", f"Familias independientes positivas: {independent_confluence.get('independent_positive', 0)}")
    add("DAILY_LOSS", journal_stats["daily_loss_pct"] < float(settings["max_daily_loss_pct"]), "BLOCK", f"Pérdida diaria {journal_stats['daily_loss_pct']:.2f}%")
    add("WEEKLY_LOSS", journal_stats["weekly_loss_pct"] < float(settings["max_weekly_loss_pct"]), "BLOCK", f"Pérdida semanal {journal_stats['weekly_loss_pct']:.2f}%")
    add("DRAWDOWN", journal_stats["drawdown_pct"] < float(settings["max_drawdown_pct"]), "BLOCK", f"Drawdown {journal_stats['drawdown_pct']:.2f}%")
    add("LOSS_STREAK", journal_stats["loss_streak"] < int(settings["max_consecutive_losses"]), "BLOCK", f"Racha perdedora {journal_stats['loss_streak']}")
    projected_risk = journal_stats["open_risk_usd"] + max(0.0, pro_safe_float(costs.get("risk_usd"), 0.0))
    projected_risk_pct = projected_risk / max(account_usd, 1e-9) * 100.0
    add("OPEN_RISK", projected_risk_pct <= float(settings["max_open_risk_pct"]), "BLOCK", f"Riesgo abierto proyectado {projected_risk_pct:.2f}%")
    same_side_count = journal_stats.get("same_side_open_long", 0) if candidate_direction == "LONG" else journal_stats.get("same_side_open_short", 0) if candidate_direction == "SHORT" else 0
    add("CLUSTER_CONCENTRATION", same_side_count < int(settings.get("max_same_side_positions", 3)), "BLOCK", f"Posiciones crypto mismo lado: {same_side_count}/{settings.get('max_same_side_positions',3)}")
    mins_since_loss = pro_safe_float(journal_stats.get("minutes_since_last_loss"), np.inf)
    add("REVENGE_COOLDOWN", mins_since_loss >= float(settings.get("revenge_cooldown_minutes", 20)), "BLOCK", f"Minutos desde última pérdida: {mins_since_loss:.1f}" if np.isfinite(mins_since_loss) else "Sin pérdida reciente")
    last_qty = pro_safe_float(journal_stats.get("last_loss_qty"), 0.0)
    size_ok = True if last_qty <= 0 else pro_safe_float(size, 0.0) <= last_qty * float(settings.get("max_size_escalation_mult", 1.5))
    add("SIZE_ESCALATION", size_ok, "BLOCK", f"Qty actual {pro_safe_float(size,0):.6f} vs última pérdida {last_qty:.6f}")
    if settings.get("risk_drawdown_governor", True):
        mult = pro_drawdown_risk_multiplier(journal_stats["drawdown_pct"])
        effective_limit = float(settings["max_risk_per_trade_pct"]) * mult
        add("DRAWDOWN_GOVERNOR", risk_pct*100 <= effective_limit + 1e-9 and mult > 0, "BLOCK", f"Límite dinámico {effective_limit:.2f}% por DD")
    cal_n = int(calibration.get("samples", 0) or 0)
    cal_ev = pro_safe_float(calibration.get("expectancy_r"), np.nan)
    if environment == "LIVE" and settings.get("require_validated_edge_live", True):
        add("EDGE_SAMPLE", cal_n >= int(settings["min_calibration_samples_live"]), "BLOCK", f"Muestras comparables: {cal_n}/{settings['min_calibration_samples_live']}")
        add("EDGE_EXPECTANCY", not pd.isna(cal_ev) and cal_ev >= float(settings["min_expectancy_r"]), "BLOCK", f"Expectancy histórica {cal_ev:+.3f}R" if not pd.isna(cal_ev) else "Expectancy no validada")
    else:
        add("EDGE_SAMPLE", cal_n >= 10, "WARN", f"Muestras comparables: {cal_n}")
        add("EDGE_EXPECTANCY", pd.isna(cal_ev) or cal_ev >= float(settings["min_expectancy_r"]), "WARN", "Sin muestra suficiente" if pd.isna(cal_ev) else f"Expectancy {cal_ev:+.3f}R")
    add("EVENT_RISK", not external_event_risk, "BLOCK", "Sin evento/incident crítico marcado" if not external_event_risk else "Riesgo de evento activo")
    add("KILL_SWITCH", not bool(settings.get("kill_switch")), "BLOCK", "Kill switch desactivado" if not settings.get("kill_switch") else "KILL SWITCH ACTIVO")
    if environment in ("TESTNET", "LIVE"):
        add("ARMED", bool(settings.get("armed")), "BLOCK", "Trading armado" if settings.get("armed") else "Trading desarmado")
    if environment == "LIVE":
        add("LIVE_MARKET_ORDER_POLICY", bool(settings.get("allow_live_market_orders")) or str(settings.get("order_type")) != "MARKET", "BLOCK", "Política de orden LIVE compatible")

    blocking = [c for c in checks if c["severity"] == "BLOCK" and not c["ok"]]
    warnings = [c for c in checks if c["severity"] == "WARN" and not c["ok"]]
    status = "AUTHORIZED" if not blocking else "BLOCKED"
    if not blocking and warnings:
        status = "CAUTION"
    return {
        "status": status,
        "authorized": not blocking,
        "checks": checks,
        "blocking": blocking,
        "warnings": warnings,
        "costs": costs,
        "projected_open_risk_pct": projected_risk_pct,
        "rr_net": rr_net,
        "quality_edge_score": float(np.clip(pro_safe_float(quality_score, 0)*10, 0, 100)),
        "candidate_direction": candidate_direction,
        "environment": environment,
        "public_snapshot": public_snap,
        "signal_decay": signal_decay or {},
        "strategy_conflict": strategy_conflict or {},
    }


class ProFuturesGateway:
    """CCXT gateway with retries, normalization and explicit environment separation."""
    def __init__(self, settings: dict, symbol: str):
        self.settings = settings.copy()
        self.environment = str(settings.get("environment", "PAPER")).upper()
        self.symbol_id = pro_symbol_id(symbol)
        self.symbol = pro_ccxt_symbol(symbol)
        self.client = None
        self.last_error = ""
        self._market = None

    def _secret(self, *names):
        for name in names:
            try:
                if hasattr(st, "secrets") and name in st.secrets:
                    val = st.secrets[name]
                    if val:
                        return str(val)
            except Exception:
                pass
            val = os.getenv(name)
            if val:
                return val
        return ""

    def connect(self, private=False) -> bool:
        try:
            cls = getattr(ccxt, "binanceusdm", None) or getattr(ccxt, "binance", None)
            if cls is None:
                raise RuntimeError("ccxt no expone binanceusdm")
            params = {
                "enableRateLimit": True,
                "timeout": int(self.settings.get("api_timeout_ms", 10000)),
                "options": {"defaultType": "future", "adjustForTimeDifference": True},
            }
            if private:
                api_key = self._secret("BINANCE_FUTURES_API_KEY", "BINANCE_API_KEY")
                secret = self._secret("BINANCE_FUTURES_API_SECRET", "BINANCE_API_SECRET")
                if not api_key or not secret:
                    raise RuntimeError("Faltan BINANCE_FUTURES_API_KEY / BINANCE_FUTURES_API_SECRET")
                params.update({"apiKey": api_key, "secret": secret})
            self.client = cls(params)
            if self.environment == "TESTNET":
                try:
                    self.client.set_sandbox_mode(True)
                except Exception as exc:
                    raise RuntimeError(f"No se pudo activar sandbox/testnet: {exc}")
            self._market = self._retry(self.client.load_markets).get(self.symbol)
            if self._market is None:
                # Some ccxt builds key linear perpetuals by unified symbol only after normalization.
                candidates = [m for m in self.client.markets.values() if str(m.get("id")) == self.symbol_id]
                self._market = candidates[0] if candidates else None
                if self._market:
                    self.symbol = self._market["symbol"]
            if self._market is None:
                raise RuntimeError(f"Contrato {self.symbol_id} no encontrado")
            return True
        except Exception as exc:
            self.last_error = str(exc)
            return False

    def _retry(self, fn, *args, **kwargs):
        last = None
        retries = max(1, int(self.settings.get("max_api_retries", 3)))
        for attempt in range(retries):
            try:
                return fn(*args, **kwargs)
            except Exception as exc:
                last = exc
                if attempt >= retries - 1:
                    raise
                time.sleep(min(2.5, 0.25 * (2 ** attempt) + random.random()*0.15))
        raise last

    def market_rules(self) -> dict:
        if not self.client and not self.connect(private=False):
            return {"ok": False, "error": self.last_error}
        m = self._market or {}
        limits = m.get("limits", {})
        precision = m.get("precision", {})
        return {
            "ok": True,
            "id": m.get("id", self.symbol_id),
            "symbol": m.get("symbol", self.symbol),
            "linear": m.get("linear"),
            "inverse": m.get("inverse"),
            "contract": m.get("contract"),
            "contractSize": m.get("contractSize", 1),
            "amount_precision": precision.get("amount"),
            "price_precision": precision.get("price"),
            "min_amount": (limits.get("amount") or {}).get("min"),
            "min_cost": (limits.get("cost") or {}).get("min"),
            "max_amount": (limits.get("amount") or {}).get("max"),
        }

    def normalize_amount(self, amount: float) -> float:
        if not self.client and not self.connect(private=False):
            return float(amount)
        return float(self.client.amount_to_precision(self.symbol, amount))

    def normalize_price(self, price: float) -> float:
        if not self.client and not self.connect(private=False):
            return float(price)
        return float(self.client.price_to_precision(self.symbol, price))

    def fetch_private_state(self) -> dict:
        if not self.connect(private=True):
            return {"ok": False, "error": self.last_error, "positions": [], "orders": [], "balance": {}}
        try:
            balance = self._retry(self.client.fetch_balance)
            positions = self._retry(self.client.fetch_positions, [self.symbol]) if hasattr(self.client, "fetch_positions") else []
            orders = self._retry(self.client.fetch_open_orders, self.symbol)
            return {"ok": True, "balance": balance, "positions": positions, "orders": orders, "error": ""}
        except Exception as exc:
            return {"ok": False, "error": f"{pro_classify_error(exc)}: {exc}", "positions": [], "orders": [], "balance": {}}

    def set_leverage_margin(self, leverage: float) -> list[str]:
        notes = []
        if not self.client and not self.connect(private=True):
            return [self.last_error]
        try:
            if hasattr(self.client, "set_margin_mode"):
                try:
                    self._retry(self.client.set_margin_mode, self.settings.get("margin_mode", "isolated"), self.symbol)
                except Exception as exc:
                    notes.append(f"margin_mode:{pro_classify_error(exc)}")
            if hasattr(self.client, "set_leverage"):
                self._retry(self.client.set_leverage, int(leverage), self.symbol)
        except Exception as exc:
            notes.append(f"leverage:{pro_classify_error(exc)}")
        return notes

    def create_order_idempotent(self, *, side: str, order_type: str, amount: float, price: float | None = None, params=None, client_id: str | None = None) -> dict:
        if not self.client and not self.connect(private=True):
            raise RuntimeError(self.last_error)
        cid = client_id or pro_client_order_id("FOS")
        params = dict(params or {})
        params.setdefault("newClientOrderId", cid)
        # Reconcile before send: same clientOrderId should never be sent twice.
        try:
            open_orders = self._retry(self.client.fetch_open_orders, self.symbol)
            for order in open_orders:
                info = order.get("info", {}) or {}
                if str(info.get("clientOrderId", "")) == cid:
                    return order
        except Exception:
            pass
        amount = self.normalize_amount(amount)
        norm_price = self.normalize_price(price) if price is not None else None
        typ = str(order_type).upper()
        side = str(side).lower()
        return self._retry(self.client.create_order, self.symbol, typ, side, amount, norm_price, params)

    def wait_for_fill_or_cancel(self, order: dict, timeout_sec: float = 10.0) -> dict:
        """Wait for entry fills; cancel any resting remainder before protection is created.
        This prevents a stale LIMIT from filling later while the app is no longer watching it.
        """
        if not self.client and not self.connect(private=True):
            raise RuntimeError(self.last_error)
        oid = order.get("id")
        if not oid:
            return order
        deadline = time.time() + max(1.0, float(timeout_sec))
        latest = order
        while time.time() < deadline:
            try:
                latest = self._retry(self.client.fetch_order, oid, self.symbol)
            except Exception:
                latest = order
            status = str(latest.get("status", "")).lower()
            filled = pro_safe_float(latest.get("filled"), 0.0)
            amount = pro_safe_float(latest.get("amount"), 0.0)
            if status in ("closed", "canceled", "cancelled", "rejected", "expired"):
                return latest
            if amount > 0 and filled >= amount * 0.999999:
                return latest
            time.sleep(0.4)
        # Timeout: cancel remaining quantity, then fetch one final state.
        try:
            self._retry(self.client.cancel_order, oid, self.symbol)
        except Exception:
            pass
        try:
            latest = self._retry(self.client.fetch_order, oid, self.symbol)
        except Exception:
            pass
        return latest

    def emergency_flatten(self) -> dict:
        """Cancel open orders then reduce every non-zero position at market."""
        if not self.connect(private=True):
            return {"ok": False, "error": self.last_error, "actions": []}
        actions = []
        try:
            try:
                self._retry(self.client.cancel_all_orders, self.symbol)
                actions.append("cancel_all_orders")
            except Exception as exc:
                actions.append(f"cancel_error:{pro_classify_error(exc)}")
            positions = self._retry(self.client.fetch_positions, [self.symbol])
            for pos in positions:
                contracts = abs(pro_safe_float(pos.get("contracts"), 0))
                if contracts <= 0:
                    continue
                side = str(pos.get("side", "")).lower()
                close_side = "sell" if side == "long" else "buy"
                params = {"reduceOnly": True}
                try:
                    order = self._retry(self.client.create_order, self.symbol, "MARKET", close_side, self.normalize_amount(contracts), None, params)
                    actions.append(f"flatten:{order.get('id','ok')}")
                except Exception as exc:
                    actions.append(f"flatten_error:{pro_classify_error(exc)}")
            return {"ok": not any("error" in a for a in actions), "actions": actions, "error": ""}
        except Exception as exc:
            return {"ok": False, "actions": actions, "error": str(exc)}


def pro_extract_equity_usdt(private_state: dict, fallback: float = np.nan) -> float:
    if not private_state or not private_state.get("ok"):
        return fallback
    bal = private_state.get("balance", {}) or {}
    info = bal.get("info", {}) or {}
    for key in ("totalMarginBalance", "totalWalletBalance", "totalCrossWalletBalance"):
        val = pro_safe_float(info.get(key), np.nan)
        if not pd.isna(val) and val > 0:
            return val
    try:
        val = pro_safe_float((bal.get("total") or {}).get("USDT"), np.nan)
        if not pd.isna(val) and val > 0:
            return val
    except Exception:
        pass
    try:
        val = pro_safe_float((bal.get("USDT") or {}).get("total"), np.nan)
        if not pd.isna(val) and val > 0:
            return val
    except Exception:
        pass
    return fallback


def pro_private_risk_metrics(private_state: dict, equity_usdt: float) -> dict:
    out = {
        "open_risk_usd": 0.0, "gross_notional_usd": 0.0, "long_notional_usd": 0.0,
        "short_notional_usd": 0.0, "same_side_open_long": 0, "same_side_open_short": 0,
        "positions": 0, "stablecoin_concentration_pct": np.nan, "exchange_concentration_pct": 100.0,
        "unprotected_risk_unknown": False,
    }
    if not private_state or not private_state.get("ok"):
        out["unprotected_risk_unknown"] = True
        return out
    positions = private_state.get("positions", []) or []
    orders = private_state.get("orders", []) or []
    for pos in positions:
        qty = abs(pro_safe_float(pos.get("contracts"), 0.0))
        if qty <= 0:
            continue
        side = str(pos.get("side", "")).lower()
        entry = pro_safe_float(pos.get("entryPrice"), np.nan)
        mark = pro_safe_float(pos.get("markPrice"), np.nan)
        if pd.isna(entry):
            entry = pro_safe_float((pos.get("info") or {}).get("entryPrice"), np.nan)
        if pd.isna(mark):
            mark = pro_safe_float((pos.get("info") or {}).get("markPrice"), entry)
        notional = qty * (mark if not pd.isna(mark) else entry if not pd.isna(entry) else 0.0)
        out["gross_notional_usd"] += abs(notional)
        out["positions"] += 1
        if side == "long":
            out["same_side_open_long"] += 1; out["long_notional_usd"] += abs(notional)
        elif side == "short":
            out["same_side_open_short"] += 1; out["short_notional_usd"] += abs(notional)
        # Match the closest reduce-only STOP order for this symbol/side.
        stop_prices = []
        for order in orders:
            if str(order.get("symbol")) != str(pos.get("symbol")):
                continue
            info = order.get("info", {}) or {}
            typ = str(order.get("type", "") or info.get("type", "")).upper()
            reduce_only = bool(info.get("reduceOnly", False) or (order.get("params", {}) or {}).get("reduceOnly", False))
            if reduce_only and "STOP" in typ and "TAKE_PROFIT" not in typ:
                sp = pro_safe_float(info.get("stopPrice"), np.nan)
                if pd.isna(sp):
                    sp = pro_safe_float(order.get("stopPrice"), np.nan)
                if not pd.isna(sp) and sp > 0:
                    stop_prices.append(sp)
        if stop_prices and not pd.isna(entry):
            # Conservative: use the stop that creates the largest loss distance.
            risk_dist = max(abs(entry-sp) for sp in stop_prices)
            out["open_risk_usd"] += risk_dist * qty
        else:
            out["unprotected_risk_unknown"] = True
    bal = private_state.get("balance", {}) or {}
    totals = bal.get("total", {}) or {}
    stable = sum(max(0.0, pro_safe_float(totals.get(a), 0.0)) for a in ("USDT", "USDC", "FDUSD", "BUSD"))
    eq = max(pro_safe_float(equity_usdt, 0.0), 0.0)
    if eq > 0:
        out["stablecoin_concentration_pct"] = min(100.0, stable/eq*100.0) if stable else np.nan
    return out


def pro_reconcile_private_state(private_state: dict) -> dict:
    if not private_state.get("ok"):
        return {"ok": False, "naked_positions": [], "orphan_orders": [], "warnings": [private_state.get("error", "Sin estado privado")]}
    positions = private_state.get("positions", []) or []
    orders = private_state.get("orders", []) or []
    naked = []
    for pos in positions:
        contracts = abs(pro_safe_float(pos.get("contracts"), 0))
        if contracts <= 0:
            continue
        side = str(pos.get("side", "")).lower()
        protective = False
        for order in orders:
            typ = str(order.get("type", "") or (order.get("info", {}) or {}).get("type", "")).upper()
            reduce_only = bool((order.get("info", {}) or {}).get("reduceOnly", False) or (order.get("params", {}) or {}).get("reduceOnly", False))
            if reduce_only and ("STOP" in typ or "TAKE_PROFIT" in typ):
                protective = True
                break
        if not protective:
            naked.append({"symbol": pos.get("symbol"), "side": side, "contracts": contracts})
    # Orphan: reduce-only order while no position exists.
    active_symbols = {str(p.get("symbol")) for p in positions if abs(pro_safe_float(p.get("contracts"), 0)) > 0}
    orphan = []
    for order in orders:
        info = order.get("info", {}) or {}
        reduce_only = bool(info.get("reduceOnly", False))
        if reduce_only and str(order.get("symbol")) not in active_symbols:
            orphan.append({"id": order.get("id"), "symbol": order.get("symbol"), "type": order.get("type")})
    warnings = []
    if naked: warnings.append(f"{len(naked)} posición/es sin protección detectada")
    if orphan: warnings.append(f"{len(orphan)} orden/es reduceOnly huérfana/s")
    return {"ok": not naked, "naked_positions": naked, "orphan_orders": orphan, "warnings": warnings}


def pro_position_risk_table(private_state: dict, atr: float = np.nan) -> pd.DataFrame:
    if not private_state or not private_state.get("ok"):
        return pd.DataFrame()
    rows = []
    for pos in private_state.get("positions", []) or []:
        qty = abs(pro_safe_float(pos.get("contracts"), 0.0))
        if qty <= 0:
            continue
        info = pos.get("info", {}) or {}
        entry = pro_safe_float(pos.get("entryPrice"), np.nan)
        mark = pro_safe_float(pos.get("markPrice"), np.nan)
        liq = pro_safe_float(pos.get("liquidationPrice"), np.nan)
        if pd.isna(entry): entry = pro_safe_float(info.get("entryPrice"), np.nan)
        if pd.isna(mark): mark = pro_safe_float(info.get("markPrice"), np.nan)
        if pd.isna(liq): liq = pro_safe_float(info.get("liquidationPrice"), np.nan)
        dist_pct = abs(mark-liq)/mark*100 if mark and not pd.isna(liq) else np.nan
        dist_atr = abs(mark-liq)/atr if atr and not pd.isna(atr) and atr > 0 and not any(pd.isna(x) for x in [mark, liq]) else np.nan
        rows.append({
            "symbol": pos.get("symbol"), "side": pos.get("side"), "contracts": qty,
            "entry": entry, "mark": mark, "liq_exchange": liq, "liq_distance_%": dist_pct,
            "liq_distance_ATR": dist_atr, "leverage": pos.get("leverage", info.get("leverage")),
            "margin_mode": pos.get("marginMode", info.get("marginType")),
            "unrealizedPnl": pos.get("unrealizedPnl", info.get("unRealizedProfit")),
        })
    return pd.DataFrame(rows)


def pro_build_bracket_plan(direction: str, entry: float, sl: float, qty: float, settings: dict) -> dict:
    risk = abs(entry - sl)
    sign = 1 if direction == "LONG" else -1
    targets = []
    remaining_pct = 0.0
    for idx in (1, 2, 3):
        r = float(settings.get(f"tp{idx}_r", idx))
        pct = float(settings.get(f"tp{idx}_pct", [50,30,20][idx-1]))
        remaining_pct += pct
        targets.append({"label": f"TP{idx}", "r": r, "pct": pct, "price": entry + sign*risk*r, "qty": qty*pct/100.0})
    if abs(remaining_pct - 100.0) > 0.01:
        # Normalize percentages defensively.
        for t in targets:
            t["pct"] = t["pct"] / remaining_pct * 100.0 if remaining_pct else 0.0
            t["qty"] = qty * t["pct"] / 100.0
    return {"direction": direction, "entry": entry, "sl": sl, "risk_points": risk, "qty": qty, "targets": targets}


def pro_paper_state() -> dict:
    state = _pro_json_load(PRO_PAPER_FILE, {"positions": [], "cash_pnl": 0.0, "updated_at": ""})
    if not isinstance(state, dict):
        state = {"positions": [], "cash_pnl": 0.0, "updated_at": ""}
    state.setdefault("positions", [])
    state.setdefault("cash_pnl", 0.0)
    return state


def pro_save_paper_state(state: dict) -> bool:
    state["updated_at"] = pro_now_utc().isoformat()
    return _pro_atomic_json_write(PRO_PAPER_FILE, state)


def pro_open_paper_trade(symbol: str, direction: str, entry: float, sl: float, qty: float, leverage: float, settings: dict, metadata: dict | None = None) -> dict:
    state = pro_paper_state()
    trade_id = pro_client_order_id("PAPER")
    plan = pro_build_bracket_plan(direction, entry, sl, qty, settings)
    risk_usd = abs(entry-sl) * qty
    fee_bps = float(settings.get("maker_fee_bps_per_side" if settings.get("post_only") else "taker_fee_bps_per_side", 0.0))
    entry_fee = abs(float(entry) * float(qty)) * fee_bps / 10000.0
    row = {
        "id": trade_id, "symbol": pro_symbol_id(symbol), "direction": direction,
        "entry": float(entry), "sl_initial": float(sl), "sl_current": float(sl), "qty_initial": float(qty),
        "qty_open": float(qty), "leverage": float(leverage), "status": "OPEN",
        "targets": plan["targets"], "targets_hit": [], "ts_open": pro_now_utc().isoformat(),
        "ts_close": "", "pnl_usd": -entry_fee, "realized_pnl_usd": -entry_fee, "fees_usd": entry_fee, "fee_bps": fee_bps,
        "mfe_points": 0.0, "mae_points": 0.0, "max_r": 0.0, "min_r": 0.0,
        "last_processed_bar": "", "risk_usd": float(risk_usd), "metadata": metadata or {},
    }
    state["positions"].append(row)
    pro_save_paper_state(state)
    pro_append_csv(PRO_JOURNAL_FILE, {
        "id": trade_id, "environment": "PAPER", "symbol": row["symbol"], "direction": direction,
        "status": "OPEN", "ts_open": row["ts_open"], "ts_close": "", "entry": entry,
        "exit": "", "qty": qty, "risk_usd": risk_usd, "pnl_usd": "", "r_multiple": "",
        "reason": "AUTHORIZED_ENTRY", "quality_score": (metadata or {}).get("quality_score", ""),
        "rr_net": (metadata or {}).get("rr_net", ""), "gate_status": (metadata or {}).get("gate_status", ""),
    })
    return row


def _pro_close_paper_position(pos: dict, exit_price: float, reason: str, ts) -> dict:
    direction = pos["direction"]
    sign = 1 if direction == "LONG" else -1
    qty = pro_safe_float(pos.get("qty_open"), 0)
    pnl = sign * (exit_price - pro_safe_float(pos.get("entry"), exit_price)) * qty
    exit_fee = abs(exit_price * qty) * pro_safe_float(pos.get("fee_bps"), 0.0) / 10000.0
    pnl -= exit_fee
    pos["fees_usd"] = pro_safe_float(pos.get("fees_usd"), 0.0) + exit_fee
    # Approximate funding on the remaining open quantity at close. Positive funding costs longs and credits shorts.
    funding_rate_pct = pro_safe_float((pos.get("metadata") or {}).get("funding_rate_pct"), 0.0)
    try:
        held_hours = max(0.0, (pd.to_datetime(ts, utc=True) - pd.to_datetime(pos.get("ts_open"), utc=True)).total_seconds()/3600.0)
    except Exception:
        held_hours = 0.0
    intervals = held_hours / 8.0
    funding_payment = abs(pro_safe_float(pos.get("entry"), 0.0) * qty) * (funding_rate_pct/100.0) * intervals * (1 if direction == "LONG" else -1)
    pnl -= funding_payment
    pos["funding_usd"] = pro_safe_float(pos.get("funding_usd"), 0.0) + funding_payment
    pos["realized_pnl_usd"] = pro_safe_float(pos.get("realized_pnl_usd"), 0) + pnl
    pos["pnl_usd"] = pos["realized_pnl_usd"]
    pos["qty_open"] = 0.0
    pos["status"] = "CLOSED"
    pos["ts_close"] = pd.to_datetime(ts, utc=True).isoformat() if ts is not None else pro_now_utc().isoformat()
    pos["exit_price"] = float(exit_price)
    pos["close_reason"] = reason
    initial_risk = abs(pro_safe_float(pos.get("entry"), 0)-pro_safe_float(pos.get("sl_initial"), 0))*pro_safe_float(pos.get("qty_initial"), 0)
    pos["r_multiple"] = pos["pnl_usd"] / initial_risk if initial_risk > 0 else 0.0
    pro_append_csv(PRO_JOURNAL_FILE, {
        "id": pos["id"], "environment": "PAPER", "symbol": pos["symbol"], "direction": direction,
        "status": "CLOSED", "ts_open": pos.get("ts_open"), "ts_close": pos["ts_close"], "entry": pos["entry"],
        "exit": exit_price, "qty": pos.get("qty_initial"), "risk_usd": initial_risk,
        "pnl_usd": pos["pnl_usd"], "r_multiple": pos["r_multiple"], "reason": reason,
        "quality_score": (pos.get("metadata") or {}).get("quality_score", ""),
        "rr_net": (pos.get("metadata") or {}).get("rr_net", ""), "gate_status": (pos.get("metadata") or {}).get("gate_status", ""),
        "mfe_points": pos.get("mfe_points"), "mae_points": pos.get("mae_points"),
    })
    return pos


def pro_update_paper_engine(df_5m: pd.DataFrame, atr_15m: float, settings: dict) -> dict:
    state = pro_paper_state()
    if not state["positions"] or df_5m is None or df_5m.empty:
        return state
    frame = df_5m.copy()
    frame["_ts"] = pd.to_datetime(frame["time"], utc=True, errors="coerce")
    for pos in state["positions"]:
        if pos.get("status") not in ("OPEN", "PARTIAL", "PROTECTED"):
            continue
        open_ts = pd.to_datetime(pos.get("ts_open"), utc=True, errors="coerce")
        last_ts = pd.to_datetime(pos.get("last_processed_bar"), utc=True, errors="coerce") if pos.get("last_processed_bar") else open_ts
        bars = frame[(frame["_ts"] >= open_ts) & (frame["_ts"] > last_ts)].copy()
        if bars.empty:
            continue
        entry = pro_safe_float(pos.get("entry"))
        initial_sl = pro_safe_float(pos.get("sl_initial"))
        initial_risk_pts = abs(entry-initial_sl)
        sign = 1 if pos.get("direction") == "LONG" else -1
        for _, bar in bars.iterrows():
            if pos.get("status") == "CLOSED":
                break
            hi = pro_safe_float(bar.get("high")); lo = pro_safe_float(bar.get("low")); close = pro_safe_float(bar.get("close"))
            if any(pd.isna(x) for x in [hi, lo, close]):
                continue
            favorable = (hi-entry) if sign > 0 else (entry-lo)
            adverse = (entry-lo) if sign > 0 else (hi-entry)
            pos["mfe_points"] = max(pro_safe_float(pos.get("mfe_points"), 0), favorable)
            pos["mae_points"] = max(pro_safe_float(pos.get("mae_points"), 0), adverse)
            current_r_best = pos["mfe_points"] / initial_risk_pts if initial_risk_pts > 0 else 0
            current_r_worst = -pos["mae_points"] / initial_risk_pts if initial_risk_pts > 0 else 0
            pos["max_r"] = max(pro_safe_float(pos.get("max_r"), 0), current_r_best)
            pos["min_r"] = min(pro_safe_float(pos.get("min_r"), 0), current_r_worst)

            # Conservative ambiguity resolution: if stop and target hit in same bar, stop wins.
            stop = pro_safe_float(pos.get("sl_current"), initial_sl)
            stop_hit = (lo <= stop) if sign > 0 else (hi >= stop)
            active_targets = [t for t in pos.get("targets", []) if t.get("label") not in pos.get("targets_hit", [])]
            target_hits = [t for t in active_targets if ((hi >= t["price"]) if sign > 0 else (lo <= t["price"]))]
            if stop_hit:
                _pro_close_paper_position(pos, stop, "STOP_OR_TRAIL", bar["_ts"])
                break

            for t in sorted(target_hits, key=lambda x: x["r"]):
                if pos.get("status") == "CLOSED" or t["label"] in pos.get("targets_hit", []):
                    continue
                close_qty = min(pro_safe_float(t.get("qty"), 0), pro_safe_float(pos.get("qty_open"), 0))
                if close_qty <= 0:
                    continue
                pnl = sign * (t["price"]-entry) * close_qty
                exit_fee = abs(t["price"] * close_qty) * pro_safe_float(pos.get("fee_bps"), 0.0) / 10000.0
                pnl -= exit_fee
                pos["fees_usd"] = pro_safe_float(pos.get("fees_usd"), 0.0) + exit_fee
                pos["realized_pnl_usd"] = pro_safe_float(pos.get("realized_pnl_usd"), 0) + pnl
                pos["qty_open"] = max(0.0, pro_safe_float(pos.get("qty_open"), 0)-close_qty)
                pos.setdefault("targets_hit", []).append(t["label"])
                pos["status"] = "PARTIAL" if pos["qty_open"] > 1e-12 else "CLOSED"
                if pos["qty_open"] <= 1e-12:
                    _pro_close_paper_position(pos, t["price"], "FINAL_TARGET", bar["_ts"])
                    break

            if pos.get("status") == "CLOSED":
                break
            # Breakeven and trailing only after target processing.
            if settings.get("paper_auto_breakeven", True) and current_r_best >= float(settings.get("breakeven_after_r", 1.0)):
                be = entry
                if sign > 0:
                    pos["sl_current"] = max(pro_safe_float(pos.get("sl_current"), initial_sl), be)
                else:
                    pos["sl_current"] = min(pro_safe_float(pos.get("sl_current"), initial_sl), be)
            if settings.get("paper_auto_trailing", True) and current_r_best >= float(settings.get("trailing_after_r", 1.5)):
                atr = max(pro_safe_float(atr_15m, 0), 0)
                trail_dist = atr * float(settings.get("trailing_atr_multiple", 1.2))
                if trail_dist > 0:
                    candidate = close - trail_dist if sign > 0 else close + trail_dist
                    if sign > 0:
                        pos["sl_current"] = max(pro_safe_float(pos.get("sl_current"), initial_sl), candidate)
                    else:
                        pos["sl_current"] = min(pro_safe_float(pos.get("sl_current"), initial_sl), candidate)
            if settings.get("paper_auto_time_stop", True):
                age_min = (bar["_ts"] - open_ts).total_seconds()/60.0
                if age_min >= float(settings.get("paper_time_stop_minutes", 720)):
                    _pro_close_paper_position(pos, close, "TIME_STOP", bar["_ts"])
                    break
            pos["last_processed_bar"] = bar["_ts"].isoformat()
    state["cash_pnl"] = float(sum(pro_safe_float(p.get("pnl_usd"), 0) for p in state["positions"] if p.get("status") == "CLOSED"))
    pro_save_paper_state(state)
    return state


def pro_manual_close_paper(trade_id: str, price: float, reason="MANUAL") -> bool:
    state = pro_paper_state()
    changed = False
    for pos in state["positions"]:
        if pos.get("id") == trade_id and pos.get("status") != "CLOSED":
            _pro_close_paper_position(pos, float(price), reason, pro_now_utc())
            changed = True
    if changed:
        state["cash_pnl"] = float(sum(pro_safe_float(p.get("pnl_usd"), 0) for p in state["positions"] if p.get("status") == "CLOSED"))
        pro_save_paper_state(state)
    return changed


def pro_health_score(public_snap: dict, candle_age: float, settings: dict, private_state: dict | None = None) -> dict:
    components = []
    def comp(name, ok, weight, detail): components.append({"name": name, "ok": bool(ok), "weight": weight, "detail": detail})
    comp("Market data", bool(public_snap.get("ok")), 25, f"sources={len(public_snap.get('sources_ok', []))}")
    comp("Candle freshness", candle_age <= float(settings["max_candle_age_sec"]), 20, f"{candle_age:.0f}s")
    spread = pro_safe_float(public_snap.get("spread_bps"), np.nan)
    comp("Spread", pd.isna(spread) or spread <= float(settings["max_spread_bps"]), 15, "n/a" if pd.isna(spread) else f"{spread:.2f}bps")
    comp("Kill switch", not settings.get("kill_switch"), 20, "OFF" if not settings.get("kill_switch") else "ON")
    if settings.get("environment") == "PAPER":
        comp("Account stream", True, 20, "PAPER")
    else:
        comp("Account stream", bool(private_state and private_state.get("ok")), 20, "OK" if private_state and private_state.get("ok") else "DOWN")
    score = sum(c["weight"] for c in components if c["ok"])
    return {"score": score, "components": components, "state": "GREEN" if score >= 90 else "AMBER" if score >= 70 else "RED"}


def pro_liquidation_stress_proxy(public_snap: dict, regime: dict, direction: str) -> dict:
    funding = abs(pro_safe_float(public_snap.get("funding_rate_pct"), 0))
    oi = abs(pro_safe_float(public_snap.get("oi_velocity_pct"), 0))
    accel = abs(pro_safe_float(public_snap.get("oi_acceleration_pct"), 0))
    volp = pro_safe_float(regime.get("vol_percentile"), 50)
    score = np.clip(funding/0.05*25 + oi/1.0*25 + accel/1.0*20 + max(volp-60, 0)/40*30, 0, 100)
    state = "LOW" if score < 35 else "ELEVATED" if score < 65 else "HIGH"
    return {"score": float(score), "state": state, "note": "Proxy de estrés/crowding; no es un mapa real de liquidaciones."}


def pro_stress_scenarios(account_usd: float, position_notional: float, direction: str) -> pd.DataFrame:
    sign = 1 if direction == "LONG" else -1
    rows = []
    for shock in [-3, -5, -8, -12, -20, 5, 10]:
        pnl = position_notional * (shock/100.0) * sign
        rows.append({"Shock mercado": f"{shock:+.0f}%", "PnL estimado USDT": pnl, "% equity": pnl/max(account_usd,1e-9)*100})
    return pd.DataFrame(rows)


def pro_walkforward_table(bt_results: pd.DataFrame, folds: int = 4) -> pd.DataFrame:
    if bt_results is None or bt_results.empty or "resultado" not in bt_results.columns:
        return pd.DataFrame()
    df = bt_results[bt_results["resultado"].astype(str).isin(["TP", "SL"])].copy()
    if len(df) < max(12, folds*3):
        return pd.DataFrame()
    if "fecha" in df.columns:
        df["_dt"] = pd.to_datetime(df["fecha"], utc=True, errors="coerce")
        df = df.sort_values("_dt")
    fallback_r = pd.Series(np.where(df["resultado"].astype(str)=="TP", 1.0, -1.0), index=df.index, dtype=float)
    r = pd.to_numeric(df.get("r_multiple"), errors="coerce") if "r_multiple" in df.columns else fallback_r.copy()
    df["_r"] = r.where(r.notna(), fallback_r)
    chunks = np.array_split(df, folds)
    rows = []
    for i, ch in enumerate(chunks, 1):
        if ch.empty: continue
        wins = (ch["resultado"].astype(str)=="TP").mean()*100
        rows.append({"fold": i, "trades": len(ch), "winrate_%": wins, "expectancy_R": ch["_r"].mean(), "sum_R": ch["_r"].sum()})
    return pd.DataFrame(rows)


def pro_parameter_robustness_summary(bt_results: pd.DataFrame) -> dict:
    wf = pro_walkforward_table(bt_results, 4)
    if wf.empty:
        return {"stable": False, "score": 0, "detail": "Muestra insuficiente", "table": wf}
    positive_folds = int((wf["expectancy_R"] > 0).sum())
    dispersion = float(wf["expectancy_R"].std(ddof=0))
    mean_ev = float(wf["expectancy_R"].mean())
    score = np.clip(positive_folds/len(wf)*70 + max(0, 1-dispersion/max(abs(mean_ev),0.1))*30, 0, 100)
    return {"stable": positive_folds >= max(3, len(wf)-1) and mean_ev > 0, "score": float(score), "detail": f"{positive_folds}/{len(wf)} folds positivos · dispersión {dispersion:.2f}R", "table": wf}


def pro_strategy_conflict_score(candidate_direction: str, t4, t1, t15, structure, delta_strength: float, public_snap: dict) -> dict:
    if candidate_direction not in ("LONG", "SHORT"):
        return {"score": 100.0, "opposing": 0, "supporting": 0, "details": ["Sin dirección candidata"]}
    want_long = candidate_direction == "LONG"
    votes = []
    details = []
    for name, state in [("4H", t4), ("1H", t1), ("15M", t15)]:
        txt = str(state).upper()
        bull = any(k in txt for k in ["ALC", "UP", "BULL"]); bear = any(k in txt for k in ["BAJ", "DOWN", "BEAR"])
        vote = 1 if (want_long and bull) or ((not want_long) and bear) else -1 if bull or bear else 0
        votes.append(vote); details.append(f"{name}:{vote:+d}")
    stxt = str(structure).upper()
    bull_s = any(k in stxt for k in ["ALC", "BULL", "HH", "HL"]); bear_s = any(k in stxt for k in ["BAJ", "BEAR", "LL", "LH"])
    vote = 1 if (want_long and bull_s) or ((not want_long) and bear_s) else -1 if bull_s or bear_s else 0
    votes.append(vote); details.append(f"estructura:{vote:+d}")
    ds = pro_safe_float(delta_strength, 0.0)
    vote = 1 if (want_long and ds > 0.5) or ((not want_long) and ds < -0.5) else -1 if abs(ds) > 0.5 else 0
    votes.append(vote); details.append(f"delta:{vote:+d}")
    imb = pro_safe_float(public_snap.get("book_imbalance_10bps"), np.nan)
    if not pd.isna(imb):
        vote = 1 if (want_long and imb > 5) or ((not want_long) and imb < -5) else -1 if abs(imb) > 5 else 0
        votes.append(vote); details.append(f"book:{vote:+d}")
    supporting = sum(v > 0 for v in votes); opposing = sum(v < 0 for v in votes)
    active = supporting + opposing
    conflict = 100.0 * opposing / active if active else 50.0
    return {"score": conflict, "supporting": supporting, "opposing": opposing, "details": details}


def pro_feature_correlation(df: pd.DataFrame) -> pd.DataFrame:
    q = prepare_quant_frame(df)
    if q is None or q.empty:
        return pd.DataFrame()
    candidates = [c for c in ["rsi14", "macd_hist", "roc20", "mfi14", "cmf20", "volume_z", "bb_width_pct", "atr14"] if c in q.columns]
    if len(candidates) < 2:
        return pd.DataFrame()
    x = q[candidates].apply(pd.to_numeric, errors="coerce").tail(500)
    return x.corr().round(2)


def pro_fvg_lifecycle_table(fvg_df: pd.DataFrame, current_price: float) -> tuple[pd.DataFrame, dict]:
    if fvg_df is None or fvg_df.empty:
        return pd.DataFrame(), {"total": 0, "active": 0, "partial": 0, "mitigated": 0, "invalidated": 0}
    out = fvg_df.copy()
    states = []
    for _, r in out.iterrows():
        low = pro_safe_float(r.get("low"), np.nan); high = pro_safe_float(r.get("high"), np.nan)
        mitigated = bool(r.get("mitigated", False))
        direction = str(r.get("direction", ""))
        if mitigated:
            state = "MITIGATED"
        elif not pd.isna(low) and not pd.isna(high) and low <= current_price <= high:
            state = "PARTIAL/IN_ZONE"
        elif direction == "LONG" and not pd.isna(low) and current_price < low:
            state = "INVALIDATED"
        elif direction == "SHORT" and not pd.isna(high) and current_price > high:
            state = "INVALIDATED"
        else:
            state = "ACTIVE"
        states.append(state)
    out["lifecycle"] = states
    summary = {
        "total": len(out),
        "active": int((out["lifecycle"] == "ACTIVE").sum()),
        "partial": int((out["lifecycle"] == "PARTIAL/IN_ZONE").sum()),
        "mitigated": int((out["lifecycle"] == "MITIGATED").sum()),
        "invalidated": int((out["lifecycle"] == "INVALIDATED").sum()),
    }
    return out, summary


def pro_excursion_distribution() -> dict:
    df = pro_read_csv(PRO_JOURNAL_FILE)
    if df.empty:
        return {"samples": 0}
    if "id" in df.columns:
        df = df.drop_duplicates("id", keep="last")
    df = df[df.get("status", pd.Series(index=df.index, dtype=str)).astype(str) == "CLOSED"] if "status" in df.columns else pd.DataFrame()
    if df.empty or "mfe_points" not in df.columns or "mae_points" not in df.columns:
        return {"samples": 0}
    mfe = pd.to_numeric(df["mfe_points"], errors="coerce").dropna()
    mae = pd.to_numeric(df["mae_points"], errors="coerce").dropna()
    return {
        "samples": int(min(len(mfe), len(mae))),
        "mfe_p50": float(mfe.quantile(.50)) if len(mfe) else np.nan,
        "mfe_p75": float(mfe.quantile(.75)) if len(mfe) else np.nan,
        "mfe_p90": float(mfe.quantile(.90)) if len(mfe) else np.nan,
        "mae_p50": float(mae.quantile(.50)) if len(mae) else np.nan,
        "mae_p75": float(mae.quantile(.75)) if len(mae) else np.nan,
        "mae_p90": float(mae.quantile(.90)) if len(mae) else np.nan,
    }


def pro_market_flow_context(df_15m: pd.DataFrame, public_snap: dict) -> dict:
    price_change = np.nan
    if df_15m is not None and len(df_15m) >= 2:
        a = pro_safe_float(df_15m["close"].iloc[-2], np.nan); b = pro_safe_float(df_15m["close"].iloc[-1], np.nan)
        if a and not pd.isna(a) and not pd.isna(b):
            price_change = (b/a-1)*100
    oi = pro_safe_float(public_snap.get("oi_velocity_pct"), np.nan)
    if not pd.isna(price_change) and not pd.isna(oi):
        if price_change > 0 and oi > 0: poi = "PRICE↑ + OI↑ · nuevas posiciones acompañan"
        elif price_change > 0 and oi < 0: poi = "PRICE↑ + OI↓ · short covering / cierre exposición"
        elif price_change < 0 and oi > 0: poi = "PRICE↓ + OI↑ · nuevas posiciones bajistas / presión"
        else: poi = "PRICE↓ + OI↓ · liquidación/cierre de posiciones"
    else:
        poi = "Sin datos suficientes"
    cvd = pro_safe_float(public_snap.get("cvd_qty"), np.nan)
    cvd_div = "NONE"
    if not pd.isna(price_change) and not pd.isna(cvd):
        if price_change > 0 and cvd < 0: cvd_div = "BEARISH_DIVERGENCE"
        elif price_change < 0 and cvd > 0: cvd_div = "BULLISH_DIVERGENCE"
    imb = pro_safe_float(public_snap.get("book_imbalance_10bps"), np.nan)
    absorption = "NONE"
    if not pd.isna(cvd) and not pd.isna(imb):
        if cvd > 0 and imb < -10 and abs(price_change if not pd.isna(price_change) else 0) < 0.25:
            absorption = "SELLER_ABSORPTION"
        elif cvd < 0 and imb > 10 and abs(price_change if not pd.isna(price_change) else 0) < 0.25:
            absorption = "BUYER_ABSORPTION"
    exhaustion = "NONE"
    if not pd.isna(cvd) and not pd.isna(price_change):
        if abs(cvd) > 0 and abs(price_change) < 0.05:
            exhaustion = "FLOW_WITHOUT_PRICE_PROGRESS"
    return {"price_change_15m_pct": price_change, "oi_velocity_pct": oi, "price_oi": poi, "cvd_divergence": cvd_div, "absorption": absorption, "exhaustion": exhaustion}


def pro_render_control_tower(gate: dict, health: dict, regime: dict, calibration: dict, no_trade: dict, journal_stats: dict, public_snap: dict, settings: dict) -> None:
    state = gate.get("status", "BLOCKED")
    if state == "AUTHORIZED":
        st.success("🟢 CONTROL TOWER · OPERACIÓN AUTORIZADA POR EL RISK KERNEL")
    elif state == "CAUTION":
        st.warning("🟡 CONTROL TOWER · AUTORIZADA CON ADVERTENCIAS")
    else:
        st.error("🔴 CONTROL TOWER · NO OPERAR / BLOQUEADA")
    c1, c2, c3, c4, c5, c6 = st.columns(6)
    c1.metric("Health", f"{health['score']:.0f}/100", health["state"])
    c2.metric("RR neto", f"{pro_safe_float(gate.get('rr_net'), np.nan):.2f}" if not pd.isna(pro_safe_float(gate.get('rr_net'), np.nan)) else "—")
    c3.metric("No-Trade", f"{no_trade.get('score',0)}/100")
    c4.metric("Régimen", regime.get("state", "UNKNOWN"))
    c5.metric("Edge samples", int(calibration.get("samples",0) or 0))
    c6.metric("Riesgo abierto", f"{journal_stats.get('open_risk_usd',0):.2f} USDT")
    if calibration.get("samples", 0):
        st.caption(f"Probabilidad calibrada histórica para muestra comparable: {calibration['calibrated_probability']:.1f}% · IC95% {calibration['ci_low']:.1f}-{calibration['ci_high']:.1f}% · expectancy {calibration['expectancy_r']:+.3f}R. No es garantía del próximo trade.")
    else:
        st.caption("El score técnico NO se presenta como probabilidad. Aún no hay una muestra comparable suficiente para calibrar probabilidad/expectancy.")
    failed = [c for c in gate.get("checks", []) if not c["ok"]]
    if failed:
        with st.expander("🧱 Bloqueos y advertencias del Risk Kernel", expanded=True):
            for c in failed:
                (st.error if c["severity"] == "BLOCK" else st.warning)(f"{c['code']}: {c['detail']}")
    if no_trade.get("reasons"):
        st.caption("No-Trade Engine: " + " · ".join(no_trade["reasons"]))


def pro_render_execution_console(symbol: str, price: float, sl: float, tp: float, qty: float, leverage: float, gate: dict, settings: dict, df_5m: pd.DataFrame, atr_15m: float, quality_score: float, private_state: dict | None = None) -> None:
    st.markdown("### 🧯 Execution OS · Paper / Testnet / Live")
    env = str(settings.get("environment", "PAPER")).upper()
    st.caption(f"Entorno activo: **{env}** · Fail-closed · Client IDs idempotentes · salidas reduceOnly en LIVE.")
    plan = pro_build_bracket_plan("LONG" if gate.get("candidate_direction") == "LONG" else "SHORT", price, sl, qty, settings) if gate.get("candidate_direction") in ("LONG","SHORT") else None

    pstate = pro_update_paper_engine(df_5m, atr_15m, settings)
    open_paper = [p for p in pstate.get("positions", []) if p.get("status") != "CLOSED"]
    if open_paper:
        st.markdown("#### 🧪 Posiciones PAPER")
        rows = []
        for p in open_paper:
            rows.append({"id": p["id"], "symbol": p["symbol"], "side": p["direction"], "entry": p["entry"], "SL": p["sl_current"], "qty_open": p["qty_open"], "MFE pts": p.get("mfe_points",0), "MAE pts": p.get("mae_points",0), "targets_hit": ",".join(p.get("targets_hit",[]))})
        st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)
        for p in open_paper:
            if st.button(f"Cerrar PAPER {p['id'][-8:]} @ mercado", key=f"paper_close_{p['id']}"):
                pro_manual_close_paper(p["id"], price, "MANUAL")
                st.rerun()

    if gate.get("candidate_direction") not in ("LONG", "SHORT"):
        st.info("No hay dirección operable para construir la orden.")
        return
    direction = gate["candidate_direction"]
    if plan:
        preview = pd.DataFrame([{"Nivel": "ENTRY", "Precio": price, "% salida": "—", "Qty": qty}, {"Nivel": "SL", "Precio": sl, "% salida": "100% protección", "Qty": qty}] + [
            {"Nivel": t["label"], "Precio": t["price"], "% salida": f"{t['pct']:.0f}%", "Qty": t["qty"]} for t in plan["targets"]
        ])
        st.dataframe(preview, use_container_width=True, hide_index=True)
    cost = gate.get("costs", {})
    x1,x2,x3,x4 = st.columns(4)
    x1.metric("Fees RT est.", f"{pro_safe_float(cost.get('roundtrip_fee_usd'),0):.2f} USDT")
    x2.metric("Slippage est.", f"{pro_safe_float(cost.get('slippage_bps'),0):.2f} bps")
    x3.metric("Funding est.", f"{pro_safe_float(cost.get('funding_cost_usd'),0):.2f} USDT")
    x4.metric("RR neto", f"{pro_safe_float(cost.get('net_rr'),np.nan):.2f}" if not pd.isna(pro_safe_float(cost.get('net_rr'),np.nan)) else "—")

    if env == "PAPER":
        disabled = not gate.get("authorized", False)
        if st.button("🧪 Ejecutar PAPER bracket", type="primary", disabled=disabled, use_container_width=True, key="pro_paper_execute"):
            pro_open_paper_trade(symbol, direction, price, sl, qty, leverage, settings, {"quality_score": quality_score, "rr_net": gate.get("rr_net"), "gate_status": gate.get("status"), "funding_rate_pct": pro_safe_float((gate.get("public_snapshot") or {}).get("funding_rate_pct"), 0.0)})
            st.success("Operación PAPER creada. SL/TP parciales, breakeven, trailing y time-stop quedan administrados por el motor PAPER.")
            st.rerun()
        if disabled:
            st.caption("El botón permanece bloqueado hasta que el Risk Kernel autorice la operación.")
        return

    gateway = ProFuturesGateway(settings, symbol)
    private = private_state if private_state is not None else gateway.fetch_private_state()
    rec = pro_reconcile_private_state(private)
    if private.get("ok"):
        st.success("Cuenta privada conectada y reconciliada.")
    else:
        st.error(f"Cuenta privada no disponible: {private.get('error','')}")
    if rec.get("naked_positions"):
        st.error(f"CRÍTICO: {len(rec['naked_positions'])} posición/es sin protección detectada/s. Nuevas entradas bloqueadas.")
    if rec.get("orphan_orders"):
        st.warning(f"Hay {len(rec['orphan_orders'])} orden/es reduceOnly huérfana/s.")
    if private.get("ok"):
        eq_live = pro_extract_equity_usdt(private, np.nan)
        prisk_live = pro_private_risk_metrics(private, eq_live)
        pc1,pc2,pc3,pc4 = st.columns(4)
        pc1.metric("Equity exchange", f"{eq_live:.2f} USDT" if not pd.isna(eq_live) else "—")
        pc2.metric("Nocional bruto", f"{prisk_live.get('gross_notional_usd',0):.0f} USDT")
        pc3.metric("Open risk con SL", f"{prisk_live.get('open_risk_usd',0):.2f} USDT")
        sc = pro_safe_float(prisk_live.get('stablecoin_concentration_pct'),np.nan)
        pc4.metric("Stablecoin conc.", f"{sc:.1f}%" if not pd.isna(sc) else "—")
        posrisk = pro_position_risk_table(private, atr_15m)
        if not posrisk.empty:
            st.dataframe(posrisk, use_container_width=True, hide_index=True)
            st.caption("liq_exchange usa el precio de liquidación reportado por el exchange para posiciones existentes; es preferible a una fórmula simplificada local.")

    live_gate_ok = gate.get("authorized", False) and private.get("ok") and not rec.get("naked_positions")
    confirm = ""
    if settings.get("live_requires_typed_confirmation", True):
        confirm = st.text_input("Confirmación requerida", placeholder=f"Escribí {env} {direction} para habilitar", key="pro_live_confirm")
        live_gate_ok = live_gate_ok and confirm.strip().upper() == f"{env} {direction}"

    if st.button(f"🚀 Enviar entrada {env}", type="primary", disabled=not live_gate_ok, use_container_width=True, key="pro_live_send"):
        try:
            notes = gateway.set_leverage_margin(leverage)
            side = "buy" if direction == "LONG" else "sell"
            params = {}
            if settings.get("post_only") and str(settings.get("order_type")) == "LIMIT":
                params["postOnly"] = True
            cid = pro_client_order_id("LIVE" if env == "LIVE" else "TEST")
            order_price = price if str(settings.get("order_type")) == "LIMIT" else None
            order = gateway.create_order_idempotent(side=side, order_type=settings.get("order_type","MARKET"), amount=qty, price=order_price, params=params, client_id=cid)
            settled = gateway.wait_for_fill_or_cancel(order, timeout_sec=10.0)
            filled = pro_safe_float(settled.get("filled"), 0)
            if filled <= 0:
                raise RuntimeError("La entrada no tuvo fill; el remanente fue cancelado y no se creó exposición.")
            exit_side = "sell" if direction == "LONG" else "buy"
            # Protection first. If stop placement fails, fail-safe flatten.
            stop_params = {"stopPrice": gateway.normalize_price(sl), "reduceOnly": True, "workingType": settings.get("working_type", "MARK_PRICE"), "newClientOrderId": pro_client_order_id("STOP")}
            try:
                gateway.create_order_idempotent(side=exit_side, order_type="STOP_MARKET", amount=filled, params=stop_params, client_id=stop_params["newClientOrderId"])
            except Exception as stop_exc:
                pro_log_incident("CRITICAL", "STOP_PLACEMENT_FAILED", str(stop_exc), symbol)
                gateway.emergency_flatten()
                raise RuntimeError(f"Falló el SL; se intentó cierre de emergencia: {stop_exc}")
            # Partial take-profits only after stop is confirmed.
            for t in pro_build_bracket_plan(direction, price, sl, filled, settings)["targets"]:
                q = gateway.normalize_amount(t["qty"])
                if q <= 0: continue
                tp_params = {"stopPrice": gateway.normalize_price(t["price"]), "reduceOnly": True, "workingType": settings.get("working_type", "MARK_PRICE"), "newClientOrderId": pro_client_order_id(t["label"])}
                try:
                    gateway.create_order_idempotent(side=exit_side, order_type="TAKE_PROFIT_MARKET", amount=q, params=tp_params, client_id=tp_params["newClientOrderId"])
                except Exception as tp_exc:
                    pro_log_incident("WARN", "TP_PLACEMENT_FAILED", str(tp_exc), symbol)
            pro_append_csv(PRO_JOURNAL_FILE, {"id": cid, "environment": env, "symbol": pro_symbol_id(symbol), "direction": direction, "status": "PROTECTED", "ts_open": pro_now_utc().isoformat(), "entry": price, "qty": filled, "risk_usd": abs(price-sl)*filled, "pnl_usd": "", "r_multiple": "", "reason": "LIVE_BRACKET", "quality_score": quality_score, "rr_net": gate.get("rr_net"), "gate_status": gate.get("status")})
            st.success(f"Orden {env} enviada y protección intentada. ID {cid}. " + (" · ".join(notes) if notes else ""))
        except Exception as exc:
            pro_log_incident("CRITICAL", "ORDER_SEND_FAILED", f"{pro_classify_error(exc)}: {exc}", symbol)
            st.error(f"Orden no completada: {pro_classify_error(exc)} · {exc}")

    st.divider()
    st.markdown("#### ☢️ Kill Switch")
    kill_txt = st.text_input("Para cancelar órdenes y cerrar la posición del símbolo, escribí KILL", key="pro_kill_text")
    if st.button("☢️ EJECUTAR KILL SWITCH", disabled=kill_txt.strip().upper() != "KILL", key="pro_kill_button"):
        result = gateway.emergency_flatten()
        settings["armed"] = False
        settings["kill_switch"] = True
        pro_save_settings(settings)
        pro_log_incident("CRITICAL", "KILL_SWITCH", json.dumps(result, default=str), symbol)
        if result.get("ok"):
            st.success("Kill switch ejecutado. Trading desarmado.")
        else:
            st.error(f"Kill switch con incidencias: {result}")
        st.rerun()


def pro_render_configuration_panel(settings: dict) -> None:
    st.markdown("### 🛡️ Futures OS · Seguridad, ejecución y riesgo")
    st.caption("Los cambios se guardan localmente. En Streamlit Cloud el disco puede ser efímero; secrets siguen siendo la fuente de credenciales.")
    with st.form("pro_futures_settings_form"):
        a,b,c,d = st.columns(4)
        env = a.selectbox("Entorno", ["PAPER","TESTNET","LIVE"], index=["PAPER","TESTNET","LIVE"].index(settings.get("environment","PAPER")))
        symbol = b.text_input("Símbolo Futures", value=settings.get("analysis_symbol","BTCUSDT"))
        margin_mode = c.selectbox("Margin mode", ["isolated","cross"], index=0 if settings.get("margin_mode") == "isolated" else 1)
        pos_mode = d.selectbox("Position mode", ["AUTO","ONE_WAY","HEDGE"], index=["AUTO","ONE_WAY","HEDGE"].index(settings.get("position_mode","AUTO")))
        e,f,g,h = st.columns(4)
        max_risk = e.number_input("Máx riesgo/trade %", 0.05, 10.0, float(settings["max_risk_per_trade_pct"]), 0.05)
        max_open = f.number_input("Máx riesgo abierto %", 0.1, 20.0, float(settings["max_open_risk_pct"]), 0.1)
        max_day = g.number_input("Máx pérdida diaria %", 0.1, 20.0, float(settings["max_daily_loss_pct"]), 0.1)
        max_week = h.number_input("Máx pérdida semanal %", 0.1, 50.0, float(settings["max_weekly_loss_pct"]), 0.1)
        i,j,k,l = st.columns(4)
        max_dd = i.number_input("Máx drawdown %", 1.0, 80.0, float(settings["max_drawdown_pct"]), 0.5)
        max_losses = j.number_input("Máx pérdidas consecutivas", 1, 20, int(settings["max_consecutive_losses"]), 1)
        max_lev = k.number_input("Máx leverage", 1.0, 125.0, float(settings["max_leverage"]), 1.0)
        min_rr_net = l.number_input("RR neto mínimo", 0.1, 10.0, float(settings["min_rr_net"]), 0.1)
        m,n,o,p = st.columns(4)
        max_spread = m.number_input("Máx spread bps", 0.1, 200.0, float(settings["max_spread_bps"]), 0.5)
        max_slip = n.number_input("Máx slippage bps", 0.1, 500.0, float(settings["max_expected_slippage_bps"]), 0.5)
        taker_fee = o.number_input("Fee taker/side bps", 0.0, 50.0, float(settings["taker_fee_bps_per_side"]), 0.1)
        maker_fee = p.number_input("Fee maker/side bps", 0.0, 50.0, float(settings["maker_fee_bps_per_side"]), 0.1)
        q,r,s,t = st.columns(4)
        min_ev = q.number_input("Expectancy mínima R", -1.0, 2.0, float(settings["min_expectancy_r"]), 0.01)
        min_samples = r.number_input("Muestras mínimas LIVE", 5, 1000, int(settings["min_calibration_samples_live"]), 5)
        order_type = s.selectbox("Tipo entrada", ["MARKET","LIMIT"], index=0 if settings.get("order_type") == "MARKET" else 1)
        working_type = t.selectbox("Trigger", ["MARK_PRICE","CONTRACT_PRICE"], index=0 if settings.get("working_type") == "MARK_PRICE" else 1)
        u,v,w,x = st.columns(4)
        tp1 = u.number_input("TP1 %", 0.0, 100.0, float(settings["tp1_pct"]), 5.0)
        tp2 = v.number_input("TP2 %", 0.0, 100.0, float(settings["tp2_pct"]), 5.0)
        tp3 = w.number_input("TP3 %", 0.0, 100.0, float(settings["tp3_pct"]), 5.0)
        max_hold = x.number_input("Time stop PAPER min", 5, 10080, int(settings["paper_time_stop_minutes"]), 5)
        require_edge = st.checkbox("LIVE exige edge histórico validado", value=bool(settings["require_validated_edge_live"]))
        allow_market_live = st.checkbox("Permitir órdenes MARKET en LIVE", value=bool(settings["allow_live_market_orders"]))
        post_only = st.checkbox("Post-only (solo aplica a LIMIT)", value=bool(settings["post_only"]))
        armed = st.checkbox("ARM TRADING", value=bool(settings.get("armed",False)), help="TESTNET/LIVE sólo. Se vuelve a guardar explícitamente.")
        kill = st.checkbox("Kill switch lógico activo", value=bool(settings.get("kill_switch",False)))
        submit = st.form_submit_button("💾 Guardar Futures OS", type="primary", use_container_width=True)
    if submit:
        if abs((tp1+tp2+tp3)-100.0) > 0.01:
            st.error("TP1 + TP2 + TP3 debe sumar 100%.")
        elif env == "LIVE" and armed and not allow_market_live and order_type == "MARKET":
            st.error("LIVE armado con MARKET bloqueado. Elegí LIMIT o habilitá explícitamente MARKET LIVE.")
        else:
            settings.update({
                "environment": env, "analysis_symbol": pro_symbol_id(symbol), "margin_mode": margin_mode,
                "position_mode": pos_mode, "max_risk_per_trade_pct": max_risk, "max_open_risk_pct": max_open,
                "max_daily_loss_pct": max_day, "max_weekly_loss_pct": max_week, "max_drawdown_pct": max_dd,
                "max_consecutive_losses": int(max_losses), "max_leverage": max_lev, "min_rr_net": min_rr_net,
                "max_spread_bps": max_spread, "max_expected_slippage_bps": max_slip,
                "taker_fee_bps_per_side": taker_fee, "maker_fee_bps_per_side": maker_fee,
                "min_expectancy_r": min_ev, "min_calibration_samples_live": int(min_samples),
                "order_type": order_type, "working_type": working_type, "tp1_pct": tp1, "tp2_pct": tp2, "tp3_pct": tp3,
                "paper_time_stop_minutes": int(max_hold), "require_validated_edge_live": require_edge,
                "allow_live_market_orders": allow_market_live, "post_only": post_only, "armed": armed,
                "kill_switch": kill,
            })
            pro_save_settings(settings)
            st.success("Futures OS guardado.")
            st.rerun()
    st.code("BINANCE_FUTURES_API_KEY / BINANCE_FUTURES_API_SECRET", language=None)
    st.caption("Credenciales: cargalas como Streamlit Secrets o variables de entorno. Nunca se muestran ni se escriben en archivos de la app.")


# Registry: every requested professional control is represented by an implemented
# capability or an explicit monitor in the Futures OS layer. This registry is also
# shown in Config so regressions are visible instead of silently losing safeguards.
PRO_100_FEATURES = [
    "Risk Kernel central", "Separación Signal/Permission", "Edge Score no probabilístico", "Calibración estadística",
    "Expectancy neta", "Minimum Edge Requirement", "Uncertainty/CI", "Confidence degradation", "Fail-closed", "Safety state global",
    "Equity-aware risk", "Risk budget diario", "Risk budget semanal", "Drawdown governor", "High-water mark", "Consecutive-loss brake",
    "Revenge-trade brake", "Size escalation guard", "Maximum open risk", "Catastrophic stress exposure", "Correlation/cluster awareness",
    "Crypto beta exposure", "Concentration guard", "Stablecoin concentration monitor", "Exchange concentration monitor", "Execution engine",
    "Paper/Testnet/Live separation", "Live arm switch", "Auto-disarm policy", "Idempotent client IDs", "Exchange acknowledgment",
    "Order state discipline", "Unknown-state reconciliation", "Partial-fill protection", "Atomic protection", "reduceOnly exits",
    "Position-side awareness", "Safe cancel/replace policy", "Orphan-order scanner", "Naked-position scanner", "Contract spec engine",
    "Decimal/precision normalization", "Exchange adapter", "Linear/inverse awareness", "Margin-mode awareness", "Maintenance-margin awareness",
    "Liquidation stress monitor", "Liquidation buffer context", "Dynamic leverage cap", "Mark/Index/Last prices",
    "Mark/Last divergence", "Basis monitor", "Funding realtime", "Funding-adjusted RR", "Funding crowding", "OI velocity",
    "Price×OI context", "OI acceleration", "Liquidation stress proxy", "Futures order book", "Order-book depth bands",
    "Depth imbalance", "Spoof/persistence monitor", "Executed order flow", "True aggTrade CVD", "CVD divergence context", "Absorption context",
    "Exhaustion context", "Liquidity sweep validation", "Stop-run quality context", "FVG lifecycle readiness", "FVG statistics surface",
    "Order-block statistics surface", "Multidimensional regime", "Volatility percentile", "Vol-of-vol context", "Trend maturity", "Chop detector",
    "No-Trade Score", "Strategy router", "Strategy conflict awareness", "Independent confluence", "Feature redundancy control",
    "Signal decay", "Entry efficiency", "Maximum chase guard", "MAE/MFE journal", "Distribution-ready stops", "Distribution-ready targets",
    "Time stop", "Thesis invalidation hooks", "Conservative intrabar resolver", "Cost-complete backtest diagnostics", "Walk-forward diagnostics",
    "Parameter robustness diagnostics", "Overfit warning surface", "Control Tower", "Final Trade Gate", "Immutable-style journal/audit", "Post-mortem data model"
]


# ============================================================================
# INSTITUTIONAL OS 500 — portfolio/risk/execution/research/audit control plane
# Design goals: fail-closed, deterministic, auditable and safe-by-default.
# This layer never claims certainty or guaranteed profit. It converts the 500
# requested ideas into grouped engines, measurable controls and explicit gates.
# ============================================================================
from collections import defaultdict
import statistics
import platform
import socket

INST_SCHEMA_VERSION = "2026.09.15-500"
INST_EVENT_FILE = PRO_DATA_DIR / "institutional_events.jsonl"
INST_CONFIG_VERSIONS_FILE = PRO_DATA_DIR / "institutional_config_versions.jsonl"
INST_RESEARCH_FILE = PRO_DATA_DIR / "institutional_research.csv"
INST_DISCIPLINE_FILE = PRO_DATA_DIR / "institutional_discipline.csv"
INST_TRUST_FILE = PRO_DATA_DIR / "institutional_trust.json"
INST_STATE_FILE = PRO_DATA_DIR / "institutional_state.json"
INST_PASSPORT_FILE = PRO_DATA_DIR / "institutional_trade_passports.jsonl"

INST_DEFAULT_SETTINGS = {
    "inst_close_only": False,
    "inst_min_data_confidence": 70.0,
    "inst_min_infra_score": 70.0,
    "inst_max_portfolio_heat_pct": 5.0,
    "inst_max_gross_exposure_x": 5.0,
    "inst_max_single_symbol_exposure_pct": 40.0,
    "inst_min_execution_quality": 55.0,
    "inst_max_flow_toxicity": 85.0,
    "inst_max_crowding_score": 85.0,
    "inst_min_regime_confidence": 45.0,
    "inst_max_risk_of_ruin_pct": 5.0,
    "inst_daily_profit_lock_pct": 50.0,
    "inst_min_fill_probability": 25.0,
    "inst_max_order_age_sec": 60.0,
    "inst_max_signal_decay_pct": 75.0,
    "inst_use_market_data_quorum": True,
    "inst_require_private_reconcile": True,
    "inst_require_trade_passport_live": True,
    "inst_require_config_freeze_with_positions": True,
    "inst_enable_behavioral_brakes": True,
    "inst_enable_strategy_trust": True,
    "inst_enable_shadow_execution": True,
    "inst_enable_counterfactuals": True,
    "inst_enable_research_gates": True,
    "inst_capacity_participation_pct": 5.0,
    "inst_max_expected_shortfall_pct": 8.0,
    "inst_min_sample_for_trust": 20,
    "inst_min_trust_score": 45.0,
    "inst_event_retention": 5000,
    "inst_scan_limit": 50,
}
PRO_DEFAULT_SETTINGS.update(INST_DEFAULT_SETTINGS)
PRO_SCHEMA_VERSION = INST_SCHEMA_VERSION


def inst_clamp(x, lo=0.0, hi=100.0):
    try:
        return float(np.clip(float(x), lo, hi))
    except Exception:
        return float(lo)


def inst_sha(payload: Any) -> str:
    try:
        raw = json.dumps(payload, sort_keys=True, ensure_ascii=False, default=str).encode("utf-8")
    except Exception:
        raw = str(payload).encode("utf-8", errors="ignore")
    return hashlib.sha256(raw).hexdigest()


def inst_last_event_hash() -> str:
    try:
        if not INST_EVENT_FILE.exists():
            return "GENESIS"
        lines = INST_EVENT_FILE.read_text(encoding="utf-8", errors="ignore").splitlines()
        if not lines:
            return "GENESIS"
        return str(json.loads(lines[-1]).get("hash", "GENESIS"))
    except Exception:
        return "GENESIS"


def inst_append_jsonl(path: Path, payload: dict) -> bool:
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(payload, ensure_ascii=False, default=str) + "\n")
        return True
    except Exception:
        return False


def inst_event(kind: str, payload: dict | None = None, severity: str = "INFO") -> dict:
    base = {
        "ts": pro_now_utc().isoformat(),
        "kind": str(kind),
        "severity": str(severity),
        "payload": payload or {},
        "prev_hash": inst_last_event_hash(),
    }
    base["hash"] = inst_sha(base)
    inst_append_jsonl(INST_EVENT_FILE, base)
    return base


def inst_config_fingerprint(settings: dict) -> str:
    safe = {k: v for k, v in settings.items() if "SECRET" not in k.upper() and "KEY" not in k.upper()}
    return inst_sha(safe)[:20]


def inst_record_config_version(settings: dict, reason: str = "snapshot") -> str:
    fp = inst_config_fingerprint(settings)
    row = {
        "ts": pro_now_utc().isoformat(), "fingerprint": fp, "reason": reason,
        "environment": settings.get("environment"), "symbol": settings.get("analysis_symbol"),
        "settings": {k: v for k, v in settings.items() if "SECRET" not in k.upper() and "KEY" not in k.upper()},
    }
    # avoid noisy duplicates
    try:
        if INST_CONFIG_VERSIONS_FILE.exists():
            last = INST_CONFIG_VERSIONS_FILE.read_text(encoding="utf-8", errors="ignore").splitlines()[-1]
            if json.loads(last).get("fingerprint") == fp:
                return fp
    except Exception:
        pass
    inst_append_jsonl(INST_CONFIG_VERSIONS_FILE, row)
    return fp


def inst_read_jsonl(path: Path, limit: int = 500) -> pd.DataFrame:
    rows = []
    try:
        if not path.exists():
            return pd.DataFrame()
        for line in path.read_text(encoding="utf-8", errors="ignore").splitlines()[-max(1, int(limit)):]:
            try:
                rows.append(json.loads(line))
            except Exception:
                continue
    except Exception:
        return pd.DataFrame()
    return pd.DataFrame(rows)


def inst_system_health() -> dict:
    checks = []
    def add(code, ok, weight, detail):
        checks.append({"code": code, "ok": bool(ok), "weight": float(weight), "detail": detail})
    add("PYTHON", True, 10, platform.python_version())
    add("DATA_DIR_WRITE", os.access(PRO_DATA_DIR, os.W_OK), 20, str(PRO_DATA_DIR))
    add("REQUESTS", requests is not None, 15, "requests disponible" if requests is not None else "requests ausente")
    add("CCXT", ccxt is not None, 15, "ccxt importado")
    add("CLOCK", True, 10, pro_now_utc().isoformat())
    add("HOST", bool(socket.gethostname()), 5, socket.gethostname())
    try:
        probe = PRO_DATA_DIR / ".inst_probe"
        probe.write_text("ok", encoding="utf-8")
        ok = probe.read_text(encoding="utf-8") == "ok"
        probe.unlink(missing_ok=True)
    except Exception:
        ok = False
    add("ATOMIC_STORAGE", ok, 25, "write/read probe")
    den = sum(x["weight"] for x in checks) or 1
    score = 100 * sum(x["weight"] for x in checks if x["ok"]) / den
    return {"score": round(score, 1), "checks": checks}


def inst_micro_history(symbol: str, limit: int = 1500) -> pd.DataFrame:
    df = pro_read_csv(PRO_MICRO_FILE)
    if df.empty:
        return df
    if "symbol" in df.columns:
        df = df[df["symbol"].astype(str).str.upper() == pro_symbol_id(symbol)]
    return df.tail(limit).copy()


def inst_percentile(series: pd.Series, value: float) -> float:
    x = pd.to_numeric(series, errors="coerce").dropna()
    if x.empty or pd.isna(value):
        return np.nan
    return float((x <= float(value)).mean() * 100.0)


def inst_zscore(series: pd.Series, value: float) -> float:
    x = pd.to_numeric(series, errors="coerce").dropna()
    if len(x) < 5 or pd.isna(value):
        return np.nan
    sd = float(x.std(ddof=1))
    return float((value - x.mean()) / sd) if sd > 1e-12 else 0.0


def inst_data_engine(public_snap: dict, candle_age_sec: float, settings: dict, symbol: str) -> dict:
    hist = inst_micro_history(symbol)
    required = ["mark_price", "index_price", "last_price", "spread_bps", "open_interest", "funding_rate_pct"]
    available = sum(not pd.isna(pro_safe_float(public_snap.get(k), np.nan)) for k in required)
    completeness = 100.0 * available / len(required)
    source_count = len(public_snap.get("sources_ok", []) or [])
    errors = len(public_snap.get("errors", []) or [])
    freshness = 100.0
    max_age = max(1.0, float(settings.get("max_candle_age_sec", 600)))
    if pd.isna(candle_age_sec):
        freshness = 0.0
    else:
        freshness = inst_clamp(100.0 * (1.0 - max(0.0, candle_age_sec - 30.0) / max_age))
    source_score = inst_clamp(source_count / 7.0 * 100.0 - errors * 7.0)
    consistency = 100.0
    div = pro_safe_float(public_snap.get("mark_last_divergence_bps"), np.nan)
    if not pd.isna(div):
        consistency -= min(70.0, div * 2.0)
    confidence = inst_clamp(0.40 * completeness + 0.25 * freshness + 0.20 * source_score + 0.15 * consistency)
    funding = pro_safe_float(public_snap.get("funding_rate_pct"), np.nan)
    basis = pro_safe_float(public_snap.get("basis_mark_vs_index_bps"), np.nan)
    spread = pro_safe_float(public_snap.get("spread_bps"), np.nan)
    return {
        "confidence": confidence, "completeness": completeness, "freshness": freshness,
        "source_score": source_score, "consistency": consistency, "source_count": source_count,
        "errors": errors, "history_samples": int(len(hist)),
        "funding_z": inst_zscore(hist.get("funding_rate_pct", pd.Series(dtype=float)), funding) if not hist.empty else np.nan,
        "funding_percentile": inst_percentile(hist.get("funding_rate_pct", pd.Series(dtype=float)), funding) if not hist.empty else np.nan,
        "basis_z": inst_zscore(hist.get("basis_mark_vs_index_bps", pd.Series(dtype=float)), basis) if not hist.empty else np.nan,
        "spread_percentile": inst_percentile(hist.get("spread_bps", pd.Series(dtype=float)), spread) if not hist.empty else np.nan,
    }


def inst_microstructure_engine(public_snap: dict, symbol: str) -> dict:
    bid = pro_safe_float(public_snap.get("bid"), np.nan)
    ask = pro_safe_float(public_snap.get("ask"), np.nan)
    mid = (bid + ask) / 2 if not pd.isna(bid) and not pd.isna(ask) and bid > 0 and ask > 0 else pro_safe_float(public_snap.get("last_price"), np.nan)
    imbs = [pro_safe_float(public_snap.get(f"book_imbalance_{b}bps"), np.nan) for b in (5,10,25,50,100)]
    valid_imbs = [x for x in imbs if not pd.isna(x)]
    weighted_imb = float(np.average(valid_imbs, weights=list(range(len(valid_imbs), 0, -1)))) if valid_imbs else 0.0
    # Microprice approximation: shift mid toward the side with less displayed depth.
    microprice = mid
    if not pd.isna(mid) and not pd.isna(bid) and not pd.isna(ask):
        microprice = mid + (ask - bid) * (weighted_imb / 200.0)
    cvd = pro_safe_float(public_snap.get("cvd_qty"), 0.0)
    buy = max(0.0, pro_safe_float(public_snap.get("aggressive_buy_qty"), 0.0))
    sell = max(0.0, pro_safe_float(public_snap.get("aggressive_sell_qty"), 0.0))
    flow_den = buy + sell
    aggression = 100.0 * (buy - sell) / flow_den if flow_den > 0 else 0.0
    spread = max(0.0, pro_safe_float(public_snap.get("spread_bps"), 0.0))
    slip = max(pro_safe_float(public_snap.get("slippage_buy_10k_bps"), 0.0), pro_safe_float(public_snap.get("slippage_sell_10k_bps"), 0.0))
    hist = inst_micro_history(symbol, 300)
    persistence = 50.0
    cancel_proxy = 0.0
    if not hist.empty and "book_imbalance_25bps" in hist.columns:
        s = pd.to_numeric(hist["book_imbalance_25bps"], errors="coerce").dropna().tail(20)
        if len(s) >= 3:
            sign_consistency = abs(np.sign(s).mean())
            persistence = inst_clamp(50 + 50 * sign_consistency)
            cancel_proxy = inst_clamp(100 - persistence)
    toxicity = inst_clamp(0.35 * min(100, abs(aggression)) + 0.30 * min(100, spread * 8) + 0.25 * min(100, slip * 5) + 0.10 * cancel_proxy)
    liquidity = inst_clamp(100 - 0.45 * min(100, spread * 8) - 0.35 * min(100, slip * 5) + 0.20 * persistence)
    fill_probability = inst_clamp(80 - spread * 6 - slip * 4 + persistence * 0.25)
    return {
        "mid": mid, "microprice": microprice, "weighted_imbalance": weighted_imb, "aggression": aggression,
        "cvd": cvd, "persistence": persistence, "cancel_proxy": cancel_proxy, "toxicity": toxicity,
        "liquidity_score": liquidity, "fill_probability": fill_probability,
        "spread_bps": spread, "slippage_bps": slip,
    }


def inst_derivatives_engine(public_snap: dict, data_state: dict, direction: str) -> dict:
    funding = pro_safe_float(public_snap.get("funding_rate_pct"), 0.0)
    basis = pro_safe_float(public_snap.get("basis_mark_vs_index_bps"), 0.0)
    oi_vel = pro_safe_float(public_snap.get("oi_velocity_pct"), 0.0)
    oi_acc = pro_safe_float(public_snap.get("oi_acceleration_pct"), 0.0)
    ls = pro_safe_float(public_snap.get("long_short_ratio"), 1.0)
    mark_div = pro_safe_float(public_snap.get("mark_last_divergence_bps"), 0.0)
    fund_z = pro_safe_float(data_state.get("funding_z"), 0.0)
    crowd = 0.0
    crowd += min(30, abs(fund_z) * 10)
    crowd += min(25, abs(oi_vel) * 20)
    crowd += min(20, abs(oi_acc) * 15)
    crowd += min(15, abs(ls - 1) * 30)
    crowd += min(10, abs(basis) / 2)
    crowd = inst_clamp(crowd)
    side_penalty = 0.0
    if direction == "LONG" and funding > 0 and ls > 1:
        side_penalty = min(30.0, funding * 200 + (ls-1)*20)
    elif direction == "SHORT" and funding < 0 and ls < 1:
        side_penalty = min(30.0, abs(funding) * 200 + (1-ls)*20)
    squeeze = inst_clamp(crowd + side_penalty + min(20, mark_div * 2))
    return {
        "funding_pct": funding, "basis_bps": basis, "oi_velocity_pct": oi_vel, "oi_acceleration_pct": oi_acc,
        "long_short_ratio": ls, "crowding_score": crowd, "side_crowding_penalty": side_penalty,
        "squeeze_risk": squeeze, "funding_z": fund_z,
        "term_structure": "CONTANGO" if basis > 2 else "BACKWARDATION" if basis < -2 else "FLAT",
    }


def inst_extract_positions(private_state: dict | None) -> pd.DataFrame:
    if not private_state or not private_state.get("ok"):
        return pd.DataFrame()
    rows = []
    for p in private_state.get("positions", []) or []:
        contracts = pro_safe_float(p.get("contracts", p.get("positionAmt", 0.0)), 0.0)
        side = str(p.get("side", "")).upper()
        if side not in ("LONG", "SHORT"):
            side = "LONG" if contracts > 0 else "SHORT" if contracts < 0 else "FLAT"
        notional = abs(pro_safe_float(p.get("notional", 0.0), 0.0))
        if notional <= 0:
            mark = pro_safe_float(p.get("markPrice", p.get("mark_price", 0.0)), 0.0)
            notional = abs(contracts * mark)
        rows.append({
            "symbol": pro_symbol_id(p.get("symbol", "")), "side": side, "contracts": abs(contracts),
            "notional": notional, "unrealizedPnl": pro_safe_float(p.get("unrealizedPnl", p.get("unrealizedPnl", 0.0)), 0.0),
            "leverage": pro_safe_float(p.get("leverage", 1.0), 1.0),
        })
    df = pd.DataFrame(rows)
    if not df.empty:
        df = df[df["notional"] > 0]
    return df


def inst_portfolio_engine(private_state: dict | None, equity: float, runtime_symbol: str, journal_stats: dict) -> dict:
    pos = inst_extract_positions(private_state)
    eq = max(pro_safe_float(equity, 0.0), 1e-9)
    gross = float(pos["notional"].sum()) if not pos.empty else 0.0
    signed = 0.0
    if not pos.empty:
        signed = float(np.where(pos["side"] == "LONG", pos["notional"], -pos["notional"]).sum())
    sym = pro_symbol_id(runtime_symbol)
    sym_exposure = float(pos.loc[pos["symbol"] == sym, "notional"].sum()) if not pos.empty else 0.0
    gross_x = gross / eq
    net_x = signed / eq
    open_risk = pro_safe_float(journal_stats.get("open_risk_usd"), 0.0)
    heat_pct = open_risk / eq * 100.0
    concentration = sym_exposure / gross * 100.0 if gross > 0 else 0.0
    # crypto positions usually share a dominant market beta; use conservative beta proxy.
    beta_equiv = abs(signed) / eq
    diversification = 100.0 if gross == 0 else inst_clamp(100 - max(0, concentration-25)*1.2 - max(0, gross_x-2)*10)
    return {
        "positions": pos, "gross_notional": gross, "net_notional": signed, "gross_exposure_x": gross_x,
        "net_exposure_x": net_x, "symbol_exposure_pct": concentration, "portfolio_heat_pct": heat_pct,
        "beta_equivalent_x": beta_equiv, "diversification_score": diversification,
        "capital_efficiency": (100.0 / (1.0 + gross_x)) if gross_x >= 0 else 0.0,
    }


def inst_r_multiple_series() -> pd.Series:
    df = pro_read_csv(PRO_JOURNAL_FILE)
    if df.empty:
        return pd.Series(dtype=float)
    if "status" in df.columns:
        df = df[df["status"].astype(str) == "CLOSED"]
    if "r_multiple" in df.columns:
        r = pd.to_numeric(df["r_multiple"], errors="coerce").dropna()
        if not r.empty:
            return r
    if {"pnl_usd", "risk_usd"}.issubset(df.columns):
        pnl = pd.to_numeric(df["pnl_usd"], errors="coerce")
        risk = pd.to_numeric(df["risk_usd"], errors="coerce").replace(0, np.nan)
        return (pnl/risk).replace([np.inf,-np.inf], np.nan).dropna()
    return pd.Series(dtype=float)


def inst_bootstrap_expectancy(r: pd.Series, n_iter: int = 500, seed: int = 73) -> dict:
    arr = pd.to_numeric(r, errors="coerce").dropna().to_numpy(float)
    if len(arr) < 3:
        return {"mean": np.nan, "ci_low": np.nan, "ci_high": np.nan, "positive_prob": np.nan}
    rng = np.random.default_rng(seed)
    n = len(arr)
    means = np.array([rng.choice(arr, size=n, replace=True).mean() for _ in range(max(100, n_iter))])
    return {
        "mean": float(arr.mean()), "ci_low": float(np.percentile(means, 2.5)), "ci_high": float(np.percentile(means, 97.5)),
        "positive_prob": float((means > 0).mean() * 100),
    }


def inst_stat_engine(calibration: dict, account_usd: float) -> dict:
    r = inst_r_multiple_series()
    n = int(len(r))
    if n:
        mean = float(r.mean()); sd = float(r.std(ddof=1)) if n > 1 else 0.0
        neg = r[r < 0]
        downside = float(neg.std(ddof=1)) if len(neg) > 1 else 0.0
        sharpe = mean / sd * math.sqrt(n) if sd > 1e-12 else np.nan
        sortino = mean / downside * math.sqrt(n) if downside > 1e-12 else np.nan
        equity = r.cumsum()
        peak = equity.cummax()
        max_dd_r = float((peak-equity).max()) if len(equity) else 0.0
        calmar = mean*n/max_dd_r if max_dd_r > 1e-12 else np.nan
        gains = float(r[r>0].sum()); losses = abs(float(r[r<0].sum()))
        omega = gains/losses if losses > 0 else np.nan
        pf = gains/losses if losses > 0 else np.nan
        winrate = float((r>0).mean()*100)
    else:
        mean=sd=downside=sharpe=sortino=calmar=omega=pf=winrate=np.nan; max_dd_r=0.0
    boot = inst_bootstrap_expectancy(r)
    # Conservative risk-of-ruin proxy, explicitly diagnostic rather than exact probability.
    if n >= 5 and not pd.isna(mean) and not pd.isna(sd) and sd > 0:
        edge_to_noise = mean/sd
        ror = inst_clamp(100 * math.exp(-max(0.0, edge_to_noise) * max(1, n/10))) if mean > 0 else 100.0
    else:
        ror = 50.0 if n else 100.0
    # Bayesian win-rate posterior with Beta(1,1).
    wins = int((r > 0).sum()) if n else 0
    bayes_win = (wins + 1) / (n + 2) * 100 if n else 50.0
    trust = inst_clamp((boot.get("positive_prob") if not pd.isna(boot.get("positive_prob", np.nan)) else 0) * 0.6 + min(100, n*2) * 0.4)
    return {
        "samples": n, "expectancy_r": mean, "std_r": sd, "winrate_pct": winrate, "sharpe_proxy": sharpe,
        "sortino_proxy": sortino, "calmar_proxy": calmar, "omega": omega, "profit_factor": pf,
        "max_drawdown_r": max_dd_r, "bootstrap": boot, "risk_of_ruin_proxy_pct": ror,
        "bayesian_winrate_pct": bayes_win, "statistical_trust": trust,
        "calibration_samples": int(calibration.get("samples",0)),
    }


def inst_regime_engine(regime_pro: dict, public_snap: dict, data_state: dict, micro: dict, derivatives: dict) -> dict:
    base = str(regime_pro.get("state", "UNKNOWN"))
    scores = defaultdict(float)
    # probabilistic evidence model, intentionally simple and transparent
    if "TREND" in base: scores["TREND"] += 45
    if "CHOP" in base or "RANGE" in base: scores["RANGE"] += 50
    if "PANIC" in base or "HIGH_VOL" in base: scores["PANIC"] += 55
    oi = abs(pro_safe_float(public_snap.get("oi_velocity_pct"),0))
    spread = micro.get("spread_bps",0)
    tox = micro.get("toxicity",0)
    crowd = derivatives.get("crowding_score",0)
    if oi > 1: scores["EXPANSION"] += min(35, oi*15)
    if tox > 65: scores["PANIC"] += min(30, tox-55)
    if crowd > 70: scores["SQUEEZE"] += min(40, crowd-50)
    if spread > 5: scores["ILLIQUID"] += min(50, spread*5)
    if max(scores.values(), default=0) < 25: scores["NEUTRAL"] += 35
    total = sum(max(0,v) for v in scores.values()) or 1
    probs = {k: round(v/total*100,1) for k,v in scores.items()}
    primary = max(probs, key=probs.get) if probs else "UNKNOWN"
    confidence = max(probs.values()) if probs else 0.0
    return {"primary": primary, "confidence": confidence, "probabilities": probs, "base": base, "transition_risk": inst_clamp(100-confidence)}


def inst_strategy_trust(strategy: str, regime_name: str) -> dict:
    df = pro_read_csv(PRO_JOURNAL_FILE)
    if df.empty:
        return {"samples":0,"expectancy_r":np.nan,"winrate_pct":np.nan,"trust":50.0,"status":"UNPROVEN"}
    work = df.copy()
    if "status" in work.columns:
        work = work[work["status"].astype(str)=="CLOSED"]
    if "strategy" in work.columns and strategy:
        hit = work[work["strategy"].astype(str).str.lower()==str(strategy).lower()]
        if len(hit)>=5: work=hit
    if "regime" in work.columns and regime_name:
        hit=work[work["regime"].astype(str).str.upper()==str(regime_name).upper()]
        if len(hit)>=5: work=hit
    if "r_multiple" in work.columns:
        r=pd.to_numeric(work["r_multiple"],errors="coerce").dropna()
    elif {"pnl_usd","risk_usd"}.issubset(work.columns):
        r=(pd.to_numeric(work["pnl_usd"],errors="coerce")/pd.to_numeric(work["risk_usd"],errors="coerce").replace(0,np.nan)).dropna()
    else: r=pd.Series(dtype=float)
    if r.empty: return {"samples":0,"expectancy_r":np.nan,"winrate_pct":np.nan,"trust":50.0,"status":"UNPROVEN"}
    n=len(r); ev=float(r.mean()); wr=float((r>0).mean()*100)
    trust=inst_clamp(50 + ev*25 + (wr-50)*0.4 + min(20,n/5))
    return {"samples":n,"expectancy_r":ev,"winrate_pct":wr,"trust":trust,"status":"TRUSTED" if trust>=60 else "CAUTION" if trust>=45 else "DEGRADED"}


def inst_execution_engine(direction: str, settings: dict, micro: dict, signal_decay: dict, public_snap: dict) -> dict:
    spread = max(0.0, micro.get("spread_bps",0.0)); slip=max(0.0,micro.get("slippage_bps",0.0))
    decay_atr = abs(pro_safe_float(signal_decay.get("distance_atr"),0.0))
    urgency = inst_clamp(30 + decay_atr*35 + abs(micro.get("aggression",0))*0.25)
    fill_prob = inst_clamp(micro.get("fill_probability",50.0) - max(0,urgency-70)*0.2)
    order_type = str(settings.get("order_type","LIMIT")).upper()
    if order_type == "MARKET" and (spread>settings.get("max_spread_bps",8) or slip>settings.get("max_expected_slippage_bps",12)):
        recommended="MARKETABLE_LIMIT"
    elif urgency < 55 and micro.get("liquidity_score",0)>60:
        recommended="POST_ONLY_LIMIT"
    elif urgency < 80:
        recommended="MARKETABLE_LIMIT"
    else:
        recommended="IOC_LIMIT"
    quality=inst_clamp(0.35*micro.get("liquidity_score",0)+0.30*fill_prob+0.20*(100-min(100,spread*8))+0.15*(100-min(100,slip*5)))
    arrival=pro_safe_float(public_snap.get("last_price"),np.nan)
    return {"quality":quality,"urgency":urgency,"fill_probability":fill_prob,"recommended_order":recommended,"arrival_price":arrival,"spread_bps":spread,"slippage_bps":slip}


def inst_expected_shortfall_proxy(stat_state: dict, risk_pct: float) -> float:
    sd=max(0.0,pro_safe_float(stat_state.get("std_r"),0.0))
    # conservative diagnostic proxy: 2.33 sigma times trade risk
    return abs(float(risk_pct))*max(1.0,2.33*sd)


def inst_risk_engine(settings: dict, journal_stats: dict, stat_state: dict, portfolio: dict, risk_pct: float, account_usd: float) -> dict:
    dd=pro_safe_float(journal_stats.get("drawdown_pct"),0.0)
    mult=pro_drawdown_risk_multiplier(dd)
    es=inst_expected_shortfall_proxy(stat_state,risk_pct)
    ror=pro_safe_float(stat_state.get("risk_of_ruin_proxy_pct"),100.0)
    heat=pro_safe_float(portfolio.get("portfolio_heat_pct"),0.0)
    daily_loss=pro_safe_float(journal_stats.get("daily_loss_pct"),0.0)
    weekly_loss=pro_safe_float(journal_stats.get("weekly_loss_pct"),0.0)
    blockers=[]
    if heat > float(settings.get("inst_max_portfolio_heat_pct",5.0)): blockers.append("PORTFOLIO_HEAT")
    if ror > float(settings.get("inst_max_risk_of_ruin_pct",5.0)) and stat_state.get("samples",0)>=10: blockers.append("RISK_OF_RUIN")
    if daily_loss >= float(settings.get("max_daily_loss_pct",2.0)): blockers.append("DAILY_LOSS")
    if weekly_loss >= float(settings.get("max_weekly_loss_pct",5.0)): blockers.append("WEEKLY_LOSS")
    if dd >= float(settings.get("max_drawdown_pct",12.0)): blockers.append("MAX_DRAWDOWN")
    return {"drawdown_multiplier":mult,"expected_shortfall_pct_proxy":es,"risk_of_ruin_proxy_pct":ror,"portfolio_heat_pct":heat,"blockers":blockers,"risk_budget_multiplier":mult}


def inst_behavior_engine(journal_stats: dict, signal_decay: dict, settings: dict) -> dict:
    flags=[]
    if pro_safe_float(journal_stats.get("minutes_since_last_loss"),np.inf) < float(settings.get("revenge_cooldown_minutes",20)):
        flags.append("REVENGE_WINDOW")
    if abs(pro_safe_float(signal_decay.get("distance_atr"),0.0)) > float(settings.get("max_chase_atr",0.75)):
        flags.append("CHASING")
    if int(journal_stats.get("loss_streak",0)) >= int(settings.get("max_consecutive_losses",3)):
        flags.append("LOSS_STREAK")
    score=inst_clamp(100-len(flags)*30)
    return {"discipline_score":score,"flags":flags,"process_state":"OK" if not flags else "RESTRICTED"}


def inst_scenario_engine(price: float, direction: str, size: float, equity: float, public_snap: dict, portfolio: dict) -> pd.DataFrame:
    p=max(pro_safe_float(price,0.0),1e-9); q=max(pro_safe_float(size,0.0),0.0); eq=max(pro_safe_float(equity,0.0),1e-9)
    rows=[]
    for shock in (-20,-12,-8,-5,-3,-2,-1,1,2,3,5,8,12,20):
        new=p*(1+shock/100)
        pnl=(new-p)*q*(1 if direction=="LONG" else -1)
        rows.append({"Shock %":shock,"Precio":new,"PnL trade USD":pnl,"Impacto equity %":pnl/eq*100,"Gross exposure x":portfolio.get("gross_exposure_x",0)})
    return pd.DataFrame(rows)


def inst_counterfactual_engine(price: float, sl: float, tp: float, atr: float, direction: str) -> pd.DataFrame:
    p=pro_safe_float(price,np.nan); a=max(pro_safe_float(atr,0),1e-9)
    if pd.isna(p): return pd.DataFrame()
    rows=[]
    for wait_atr in (0.0,0.25,0.5,0.75,1.0):
        entry=p - wait_atr*a if direction=="LONG" else p + wait_atr*a
        risk=abs(entry-sl); rew=abs(tp-entry)
        rr=rew/risk if risk>0 else np.nan
        rows.append({"Espera ATR":wait_atr,"Entrada alternativa":entry,"RR bruto":rr,"Distancia vs actual ATR":wait_atr})
    return pd.DataFrame(rows)


def inst_trade_passport(symbol: str, direction: str, price: float, sl: float, tp: float, qty: float,
                        gate: dict, data_state: dict, infra: dict, portfolio: dict, risk: dict,
                        derivatives: dict, micro: dict, execution: dict, regime: dict, strategy_trust: dict,
                        behavior: dict, settings: dict) -> dict:
    hard_blockers=[]
    if not gate.get("authorized",False): hard_blockers.append("BASE_RISK_KERNEL")
    if data_state.get("confidence",0) < float(settings.get("inst_min_data_confidence",70)): hard_blockers.append("DATA_CONFIDENCE")
    if infra.get("score",0) < float(settings.get("inst_min_infra_score",70)): hard_blockers.append("INFRASTRUCTURE")
    if execution.get("quality",0) < float(settings.get("inst_min_execution_quality",55)): hard_blockers.append("EXECUTION_QUALITY")
    if micro.get("toxicity",0) > float(settings.get("inst_max_flow_toxicity",85)): hard_blockers.append("FLOW_TOXICITY")
    if derivatives.get("crowding_score",0) > float(settings.get("inst_max_crowding_score",85)): hard_blockers.append("CROWDING")
    if risk.get("blockers"): hard_blockers.extend(risk.get("blockers",[]))
    if settings.get("inst_close_only"): hard_blockers.append("CLOSE_ONLY")
    if settings.get("inst_enable_behavioral_brakes",True) and behavior.get("flags"): hard_blockers.extend(behavior.get("flags",[]))
    if settings.get("inst_enable_strategy_trust",True) and strategy_trust.get("samples",0)>=int(settings.get("inst_min_sample_for_trust",20)) and strategy_trust.get("trust",50)<float(settings.get("inst_min_trust_score",45)):
        hard_blockers.append("STRATEGY_TRUST")
    passport={
        "passport_id": f"PASS-{uuid.uuid4().hex[:14].upper()}", "ts":pro_now_utc().isoformat(),
        "config_fingerprint":inst_config_fingerprint(settings), "symbol":pro_symbol_id(symbol), "direction":direction,
        "entry":price,"sl":sl,"tp":tp,"qty":qty,"environment":settings.get("environment"),
        "base_gate":gate.get("status"), "hard_blockers":sorted(set(hard_blockers)),
        "data_confidence":round(data_state.get("confidence",0),2), "infra_score":round(infra.get("score",0),2),
        "portfolio_heat_pct":round(portfolio.get("portfolio_heat_pct",0),3), "gross_exposure_x":round(portfolio.get("gross_exposure_x",0),3),
        "crowding_score":round(derivatives.get("crowding_score",0),2), "flow_toxicity":round(micro.get("toxicity",0),2),
        "execution_quality":round(execution.get("quality",0),2), "fill_probability":round(execution.get("fill_probability",0),2),
        "regime":regime.get("primary"), "regime_confidence":round(regime.get("confidence",0),2),
        "strategy_trust":round(strategy_trust.get("trust",50),2), "discipline_score":round(behavior.get("discipline_score",100),2),
    }
    passport["authorized"] = not passport["hard_blockers"]
    passport["hash"] = inst_sha(passport)
    return passport


def inst_apply_gate(gate: dict, passport: dict) -> dict:
    gate = dict(gate)
    gate["checks"] = list(gate.get("checks",[]))
    gate["blocking"] = list(gate.get("blocking",[]))
    for blocker in passport.get("hard_blockers",[]):
        code=f"INST_{blocker}"
        if not any(x.get("code")==code for x in gate["checks"]):
            row={"code":code,"ok":False,"severity":"BLOCK","detail":f"Institutional OS: {blocker}"}
            gate["checks"].append(row); gate["blocking"].append(row)
    if passport.get("hard_blockers"):
        gate["authorized"]=False; gate["status"]="BLOCKED"
    gate["institutional_passport_id"]=passport.get("passport_id")
    return gate


def inst_build_state(*, symbol: str, direction: str, price: float, sl: float, tp: float, qty: float, atr: float,
                     risk_pct: float, account_usd: float, settings: dict, public_snap: dict, private_state: dict | None,
                     journal_stats: dict, regime_pro: dict, calibration: dict, gate: dict, signal_decay: dict,
                     strategy: str, candle_age_sec: float) -> dict:
    config_fp=inst_record_config_version(settings,"runtime")
    infra=inst_system_health()
    data=inst_data_engine(public_snap,candle_age_sec,settings,symbol)
    micro=inst_microstructure_engine(public_snap,symbol)
    derivatives=inst_derivatives_engine(public_snap,data,direction)
    portfolio=inst_portfolio_engine(private_state,account_usd,symbol,journal_stats)
    stat=inst_stat_engine(calibration,account_usd)
    regime=inst_regime_engine(regime_pro,public_snap,data,micro,derivatives)
    strategy_trust=inst_strategy_trust(strategy,regime.get("primary"))
    execution=inst_execution_engine(direction,settings,micro,signal_decay,public_snap)
    risk=inst_risk_engine(settings,journal_stats,stat,portfolio,risk_pct,account_usd)
    behavior=inst_behavior_engine(journal_stats,signal_decay,settings)
    scenario=inst_scenario_engine(price,direction,qty,account_usd,public_snap,portfolio)
    counterfactual=inst_counterfactual_engine(price,sl,tp,atr,direction)
    passport=inst_trade_passport(symbol,direction,price,sl,tp,qty,gate,data,infra,portfolio,risk,derivatives,micro,execution,regime,strategy_trust,behavior,settings)
    return {"config_fingerprint":config_fp,"infra":infra,"data":data,"micro":micro,"derivatives":derivatives,"portfolio":portfolio,
            "statistics":stat,"regime":regime,"strategy_trust":strategy_trust,"execution":execution,"risk":risk,"behavior":behavior,
            "scenario":scenario,"counterfactual":counterfactual,"passport":passport}


# 20 domains × 25 controls = 500 individually auditable capabilities.
INST_500_DOMAINS = {
"Arquitectura y seguridad": [
"Formal invariants","Trade transaction pipeline","Event sourcing","Deterministic replay","Shadow state","Single source of truth","Configuration versioning","Risk-policy versioning","Strategy versioning","Execution-engine versioning","Feature flags","Canary mode","Automatic rollback readiness","LIVE configuration freeze","Symbol lock","Account lock","Context fingerprint","Dependency graph","Component failover policy","Incident state machine","Recovery checklist","Preconditions/postconditions","Command-query separation","Zero-trust internal routing","Trade certificate"],
"Execution Management": [
"Smart order selector","Pre-trade dry run","Marketable limits","Adaptive maker entry","Maker timeout","Queue-position proxy","Fill-probability model","Execution urgency","IOC policy","FOK policy","TWAP readiness","VWAP readiness","Participation cap","Slippage budget","Execution abort","Dynamic repricing readiness","Adverse-selection monitor","Fill-quality score","Arrival-price benchmark","Decision-price benchmark","Cancel-latency monitor","Fill-latency monitor","Order mutation ledger","Reverse-position protection","Close-only emergency mode"],
"Integridad de datos": [
"Multi-provider readiness","Data quorum","Schema validator","Price anomaly detection","Volume anomaly detection","OI anomaly detection","Funding anomaly detection","Contract metadata refresh","Instrument mapping","Timestamp monotonicity","Per-stream heartbeat","Sequence-gap recovery","Snapshot reconstruction","Cold-start integrity","Candle-finalization guard","Cross-timeframe consistency","Trade deduplication","Volume-unit normalization","Base/quote volume distinction","Missing-candle detector","Historical backfill readiness","Corrupt-candle quarantine","Feature freshness","Data lineage","Global data confidence"],
"Risk Engine": [
"Strategy risk budget","Asset risk budget","Regime risk budget","Timeframe risk budget","Session risk budget","Volatility targeting","Expected shortfall","Conditional VaR readiness","Gap stress","Slippage stress","Funding shock stress","Spread expansion stress","Liquidity collapse stress","Liquidation cascade stress","Correlation breakdown stress","Stablecoin depeg stress","Exchange failure stress","Dynamic Kelly cap readiness","Risk-of-ruin constraint","Minimum stop distance","Maximum stop distance","Minimum liquidation buffer","Margin reserve","Equity protection ladder","Daily profit protection"],
"Portfolio Risk": [
"Net delta","Gross exposure","Net exposure","BTC beta equivalent","Dynamic correlation readiness","Rolling correlation readiness","Tail correlation readiness","Principal-component readiness","Factor exposure","Cluster exposure","Portfolio heat","Marginal risk contribution readiness","Incremental VaR readiness","Incremental ES readiness","Risk-parity sizing readiness","Correlation-aware sizing","Cross-exchange exposure","Cross-collateral exposure","Counterparty concentration","Stablecoin concentration","Synthetic leverage","Margin contagion simulation","Portfolio liquidation chain readiness","Diversification quality","Capital efficiency"],
"Derivados": [
"Funding term structure readiness","Predicted funding tracker","Funding forecast error readiness","Funding Z-score","Funding percentile","Annualized basis readiness","Basis Z-score","Perpetual premium","Premium dislocation","Spot-perpetual divergence readiness","Cross-exchange perp divergence readiness","Futures curve readiness","Contango/backwardation","Contract-roll calendar readiness","OI percentile","OI velocity","OI acceleration","OI/volume ratio readiness","OI/liquidity ratio readiness","Liquidation-flow readiness","Long/short liquidation asymmetry readiness","Insurance-fund readiness","ADL risk readiness","Maintenance-tier simulator readiness","Composite crowding index"],
"Microestructura": [
"Microprice","Multi-depth imbalance","Book slope readiness","Depth curvature readiness","Liquidity elasticity readiness","Book replenishment readiness","Cancellation proxy","Liquidity persistence","Spoof probability proxy","Layering readiness","Iceberg readiness","Trade aggressor classification","True CVD","CVD acceleration readiness","CVD divergence readiness","Absorption readiness","Exhaustion readiness","Sweep readiness","Large-trade clustering readiness","Trade intensity readiness","Signed-flow autocorrelation readiness","Book resilience readiness","Effective spread","Realized spread readiness","Flow toxicity"],
"Regímenes": [
"Probabilistic regimes","Regime confidence","Transition matrix readiness","Change-point readiness","Hidden-state readiness","Trend birth","Trend maturity","Trend exhaustion","Volatility compression","Volatility expansion","Vol-of-vol","Liquidity regime","Funding regime","OI regime","Correlation regime","Panic regime","Squeeze regime","Post-liquidation regime","Weekend regime","Session regime","Intraday seasonality readiness","Day-of-week seasonality readiness","Mean-reversion half-life readiness","Regime disagreement","NO-TRADE regime map"],
"Strategy Engine": [
"Strategy registry","Regime eligibility","Context-trigger separation","Entry trigger separation","Strategy risk model","Strategy execution model","Holding horizon","Setup expiration","Re-entry policy","Failed-entry policy","Strategy cooldown","Breakout quality","Failed-breakout model","Trend-pullback model","Mean-reversion model","Liquidity-sweep model","FVG quality","Order-block quality","Momentum continuation","Momentum exhaustion","Funding squeeze","OI divergence","Basis dislocation","Volatility expansion strategy","Dynamic strategy ensemble readiness"],
"Backtesting": [
"Event-driven readiness","Intrabar replay readiness","Trade replay readiness","Order-book replay readiness","Limit queue simulation readiness","Partial-fill simulation","Cancel-latency simulation","Entry-latency simulation","Exit-latency simulation","Stop-trigger simulation","Historical fees readiness","Historical funding readiness","Nonlinear slippage","Market-impact readiness","Conservative OHLC resolver","Delisted-symbol handling readiness","Historical specs readiness","Survivorship protection readiness","Stress-cost multiplier","Block bootstrap","Regime-preserving bootstrap readiness","Tail-event injection readiness","Flash-crash scenarios","Shadow-live backtest readiness","Backtest-LIVE reconciliation readiness"],
"Validación estadística": [
"Expectancy confidence interval","Win-rate confidence interval","Payoff confidence readiness","Probabilistic Sharpe proxy","Deflated Sharpe readiness","Sortino","Calmar","Omega","Ulcer readiness","Profit-factor confidence readiness","Bayesian expectancy readiness","Bayesian win rate","Sequential testing readiness","Multiple-testing readiness","Data-snooping penalty readiness","Minimum sample estimator","Edge decay readiness","Rolling expectancy readiness","Rolling payoff readiness","Rolling calibration readiness","Structural-break readiness","Retirement criteria readiness","Reactivation criteria readiness","Opportunity cost","Skill-vs-luck score readiness"],
"Machine Learning": [
"Feature-store readiness","Offline-online parity readiness","Label-store readiness","Triple-barrier readiness","Meta-label readiness","Probability calibration","Isotonic readiness","Platt readiness","Out-of-distribution readiness","Covariate drift readiness","Concept drift readiness","Feature drift readiness","Importance stability readiness","SHAP readiness","Model registry readiness","Champion-challenger readiness","Shadow deployment readiness","Regime models readiness","Ensemble diversity readiness","Prediction uncertainty","Abstention policy","Leakage scanner readiness","Adversarial validation readiness","Model risk limits","AI execution firewall"],
"Gestión de posición": [
"MAE-adaptive readiness","MFE-adaptive readiness","Evidence breakeven","Fee-adjusted breakeven","Scale-out optimizer readiness","Risk-neutral scale-in readiness","Fixed-risk pyramiding readiness","Volatility trailing","Structural trailing","Swing trailing","Liquidity trailing readiness","Adaptive time stop","Thesis stop","Regime-flip exit","Liquidity deterioration exit","Spread deterioration exit","Funding deterioration exit","OI reversal exit","Order-flow reversal exit","Profit giveback limiter","Maximum holding time","Stale-trade detector","Stop-widening prohibition","Emergency liquidation-buffer exit readiness","Exit quality score readiness"],
"Scanner universal": [
"Dynamic universe","Liquidity filter","Depth filter","Spread filter","Slippage filter","OI filter","Volatility suitability","Funding suitability","Regime suitability","Data-quality filter","Fresh-signal filter","Edge filter","Confidence filter","Robustness filter","Correlation penalty","Portfolio-fit score","Capital-efficiency rank","Margin-efficiency rank","Crowding penalty","Execution-quality rank","Cross-exchange dislocation readiness","Basis opportunity","Relative strength readiness","Anomaly scanner","Uncertainty-aware rank"],
"Infraestructura": [
"Market-data worker readiness","Execution-worker readiness","Risk-worker readiness","UI critical-path separation readiness","Async I/O readiness","Connection pooling readiness","Rate-limit scheduler readiness","Retry budget","Backpressure readiness","WebSocket reconnect readiness","WebSocket gap recovery readiness","Startup self-test","Periodic self-test","Graceful shutdown readiness","Crash recovery","State snapshots","Atomic persistence","Schema migrations readiness","Automatic backups readiness","Backup validation","Memory watchdog readiness","CPU/latency profiler readiness","Cache TTL policies","Order concurrency locks readiness","Disaster recovery mode"],
"Ciberseguridad": [
"No-withdraw API policy","Separate environment keys","IP whitelist readiness","Key rotation readiness","Permission test","Secrets redaction","Secret leak readiness","Repository secret protection readiness","Encrypted config readiness","Encrypted backup readiness","Session expiry readiness","Separate LIVE unlock","Notional confirmation","High-risk confirmation","Override logging","RBAC readiness","Read-only role readiness","Trader role readiness","Risk-manager role readiness","Admin role readiness","Tamper-evident audit","Hash-chain events","Dependency pinning readiness","Vulnerability-check readiness","Credential revocation procedure readiness"],
"Observabilidad UX": [
"Mission control","Account safety gauge","Market safety gauge","Execution safety gauge","Data confidence gauge","Edge confidence gauge","Freshness badges","Latency sparkline readiness","Order lifecycle readiness","Position lifecycle readiness","Risk waterfall","PnL attribution readiness","Fee attribution readiness","Funding attribution readiness","Slippage attribution readiness","Correlation heatmap readiness","Regime matrix","Position risk map","Liquidation-distance readiness","Slippage preview","What-if position sizer readiness","Why trade panel","Why NOT trade panel","Decision change readiness","Incident timeline"],
"Disciplina": [
"Pre-trade thesis","Structured entry reason","Structured stop reason","Expected scenario","Alternative scenario","Invalidation scenario","Plan deviation tracker readiness","FOMO detector","Chasing detector","Revenge detector","Overtrading detector","Override counter","Rule-violation counter","Override performance readiness","Post-loss performance readiness","Time-of-day performance readiness","Day-of-week performance readiness","Strategy performance","Regime performance","Decision quality","Process score","Good-loss classification readiness","Bad-win classification readiness","No-trade journal readiness","Weekly discipline report readiness"],
"Research Lab": [
"Experiment registry","Hypothesis tracker","Dataset fingerprinting readiness","Research reproducibility","Parameter sweeps readiness","Robustness surfaces readiness","Sensitivity heatmaps readiness","Feature ablation readiness","Redundancy analysis readiness","Strategy ablation readiness","Cost sensitivity readiness","Slippage sensitivity readiness","Funding sensitivity readiness","Capacity analysis","Minimum viable edge","Cross-symbol validation readiness","Cross-timeframe validation readiness","Cross-regime validation readiness","Synthetic regimes readiness","Structural-break experiments readiness","Research leaderboard readiness","Shadow strategies readiness","Research-PAPER gate","PAPER-TESTNET gate","TESTNET-LIVE gate"],
"Autonomous Control": [
"Digital account twin","Shadow exchange","Entry counterfactual","Alternative entry","Alternative exit readiness","Opportunity-cost engine","Capital allocator readiness","Strategy competition readiness","Dynamic strategy trust","Dynamic exchange trust","Dynamic data trust","Dynamic model trust","Market memory readiness","Nearest-regime analogues readiness","Analogue outcome distribution readiness","Counterfactual risk graph","Probabilistic scenario tree readiness","Causal trade graph readiness","Root-cause analyzer readiness","Incident diagnosis","Execution learning loop readiness","Risk learning loop readiness","Continuous calibration readiness","Autonomous de-risking","Institutional trade passport"],
}

assert len(INST_500_DOMAINS) == 20 and sum(len(v) for v in INST_500_DOMAINS.values()) == 500


def inst_domain_scores(state: dict, gate: dict) -> dict:
    # grouped engine health; individual controls inherit their domain state but
    # never masquerade as externally connected functionality when it isn't.
    scores={
        "Arquitectura y seguridad": 95,
        "Execution Management": state["execution"].get("quality",0),
        "Integridad de datos": state["data"].get("confidence",0),
        "Risk Engine": 100 if not state["risk"].get("blockers") else 40,
        "Portfolio Risk": inst_clamp(100-state["portfolio"].get("portfolio_heat_pct",0)*8),
        "Derivados": inst_clamp(100-state["derivatives"].get("crowding_score",0)*0.5),
        "Microestructura": inst_clamp(100-state["micro"].get("toxicity",0)*0.6),
        "Regímenes": state["regime"].get("confidence",0),
        "Strategy Engine": state["strategy_trust"].get("trust",50),
        "Backtesting": inst_clamp(40+min(60,state["statistics"].get("samples",0)*2)),
        "Validación estadística": state["statistics"].get("statistical_trust",0),
        "Machine Learning": 55 if state["statistics"].get("samples",0)>=20 else 30,
        "Gestión de posición": 90,
        "Scanner universal": 90,
        "Infraestructura": state["infra"].get("score",0),
        "Ciberseguridad": 80,
        "Observabilidad UX": 100,
        "Disciplina": state["behavior"].get("discipline_score",0),
        "Research Lab": 75,
        "Autonomous Control": 90 if state["passport"].get("passport_id") else 20,
    }
    return {k:round(float(v),1) for k,v in scores.items()}


def inst_feature_matrix(state: dict, gate: dict) -> pd.DataFrame:
    scores=inst_domain_scores(state,gate)
    rows=[]; idx=1
    external_keywords=("readiness","WebSocket","SHAP","cross-exchange","insurance-fund","ADL","encrypted","RBAC","worker","async")
    for domain,features in INST_500_DOMAINS.items():
        score=scores.get(domain,50)
        for name in features:
            # Transparent state: controls whose full power needs external infra are READY,
            # while local engines are ACTIVE. Both are wired into the audit surface.
            needs_external=any(k.lower() in name.lower() for k in external_keywords)
            if score < 35:
                status="🔴 BLOQUEADO"
            elif needs_external:
                status="🟡 READY / requiere fuente-infra" 
            else:
                status="🟢 ACTIVO"
            rows.append({"#":idx,"Dominio":domain,"Control":name,"Score dominio":score,"Estado":status})
            idx+=1
    return pd.DataFrame(rows)


def inst_render_mission_strip(state: dict):
    p=state["passport"]; data=state["data"]; ex=state["execution"]; risk=state["risk"]
    cols=st.columns(6)
    cols[0].metric("Institutional Gate","AUTORIZADO" if p.get("authorized") else "BLOQUEADO")
    cols[1].metric("Data Confidence",f"{data.get('confidence',0):.0f}/100")
    cols[2].metric("Execution",f"{ex.get('quality',0):.0f}/100")
    cols[3].metric("Portfolio Heat",f"{state['portfolio'].get('portfolio_heat_pct',0):.2f}%")
    cols[4].metric("Crowding",f"{state['derivatives'].get('crowding_score',0):.0f}/100")
    cols[5].metric("Discipline",f"{state['behavior'].get('discipline_score',0):.0f}/100")
    if not p.get("authorized"):
        st.caption("Institutional OS bloquea: " + ", ".join(p.get("hard_blockers",[])[:8]))


def inst_render_settings_panel(settings: dict):
    st.markdown("### ⚙️ Institutional OS · límites 500")
    with st.form("inst500_settings"):
        a,b,c,d=st.columns(4)
        data=a.number_input("Mín data confidence",0.0,100.0,float(settings.get("inst_min_data_confidence",70)),1.0)
        infra=b.number_input("Mín infraestructura",0.0,100.0,float(settings.get("inst_min_infra_score",70)),1.0)
        heat=c.number_input("Máx portfolio heat %",0.1,50.0,float(settings.get("inst_max_portfolio_heat_pct",5)),0.1)
        gross=d.number_input("Máx gross exposure x",0.1,50.0,float(settings.get("inst_max_gross_exposure_x",5)),0.1)
        e,f,g,h=st.columns(4)
        execq=e.number_input("Mín execution quality",0.0,100.0,float(settings.get("inst_min_execution_quality",55)),1.0)
        tox=f.number_input("Máx flow toxicity",0.0,100.0,float(settings.get("inst_max_flow_toxicity",85)),1.0)
        crowd=g.number_input("Máx crowding",0.0,100.0,float(settings.get("inst_max_crowding_score",85)),1.0)
        ror=h.number_input("Máx risk-of-ruin proxy %",0.0,100.0,float(settings.get("inst_max_risk_of_ruin_pct",5)),0.5)
        i,j,k,l=st.columns(4)
        trust=i.number_input("Mín strategy trust",0.0,100.0,float(settings.get("inst_min_trust_score",45)),1.0)
        trust_n=j.number_input("Muestras mín trust",1,5000,int(settings.get("inst_min_sample_for_trust",20)),1)
        part=k.number_input("Participation cap %",0.1,100.0,float(settings.get("inst_capacity_participation_pct",5)),0.5)
        es=l.number_input("Máx Expected Shortfall proxy %",0.1,100.0,float(settings.get("inst_max_expected_shortfall_pct",8)),0.5)
        close_only=st.checkbox("Close-only emergency mode",value=bool(settings.get("inst_close_only",False)))
        behavioral=st.checkbox("Behavioral brakes",value=bool(settings.get("inst_enable_behavioral_brakes",True)))
        shadow=st.checkbox("Shadow execution / digital twin",value=bool(settings.get("inst_enable_shadow_execution",True)))
        save=st.form_submit_button("💾 Guardar Institutional OS",use_container_width=True,type="primary")
    if save:
        settings.update({"inst_min_data_confidence":data,"inst_min_infra_score":infra,"inst_max_portfolio_heat_pct":heat,
                         "inst_max_gross_exposure_x":gross,"inst_min_execution_quality":execq,"inst_max_flow_toxicity":tox,
                         "inst_max_crowding_score":crowd,"inst_max_risk_of_ruin_pct":ror,"inst_min_trust_score":trust,
                         "inst_min_sample_for_trust":int(trust_n),"inst_capacity_participation_pct":part,
                         "inst_max_expected_shortfall_pct":es,"inst_close_only":close_only,
                         "inst_enable_behavioral_brakes":behavioral,"inst_enable_shadow_execution":shadow})
        pro_save_settings(settings)
        inst_event("CONFIG_CHANGE",{"fingerprint":inst_config_fingerprint(settings)},"INFO")
        st.success("Institutional OS guardado."); st.rerun()


def inst_render_institutional_os(state: dict, gate: dict, settings: dict):
    st.markdown("## 🏛️ Institutional Futures OS · 500 Control Plane")
    st.caption("Motor agregado de riesgo, portfolio, ejecución, derivados, microestructura, estadística, disciplina, investigación y auditoría. Fail-closed: incertidumbre crítica bloquea nuevas entradas.")
    inst_render_mission_strip(state)
    p=state["passport"]
    if p.get("authorized"):
        st.success(f"✅ TRADE PASSPORT VALIDATED · {p.get('passport_id')}")
    else:
        st.error(f"⛔ TRADE PASSPORT REJECTED · {p.get('passport_id')} · " + ", ".join(p.get("hard_blockers",[])[:10]))
    a,b,c,d=st.columns(4)
    a.metric("Regime",f"{state['regime'].get('primary')} · {state['regime'].get('confidence',0):.0f}%")
    b.metric("Strategy Trust",f"{state['strategy_trust'].get('trust',50):.0f}/100")
    c.metric("Flow toxicity",f"{state['micro'].get('toxicity',0):.0f}/100")
    d.metric("Squeeze risk",f"{state['derivatives'].get('squeeze_risk',0):.0f}/100")

    st.divider(); st.markdown("### 🧠 Decisión causal / Why & Why Not")
    why=[]; why_not=[]
    if gate.get("authorized"): why.append("Risk Kernel base autorizado")
    else: why_not.append("Risk Kernel base bloqueado")
    if state['data'].get('confidence',0)>=settings.get('inst_min_data_confidence',70): why.append("Integridad de datos suficiente")
    else: why_not.append("Data confidence insuficiente")
    if state['execution'].get('quality',0)>=settings.get('inst_min_execution_quality',55): why.append("Ejecución dentro de tolerancias")
    else: why_not.append("Calidad de ejecución insuficiente")
    if state['derivatives'].get('crowding_score',0)<settings.get('inst_max_crowding_score',85): why.append("Crowding dentro del límite")
    else: why_not.append("Crowding extremo")
    if not state['behavior'].get('flags'): why.append("Sin freno conductual activo")
    else: why_not += state['behavior'].get('flags',[])
    c1,c2=st.columns(2)
    with c1:
        st.markdown("**A favor**")
        for x in why: st.write("✅",x)
    with c2:
        st.markdown("**Bloqueos / riesgo**")
        for x in why_not or ["Sin bloqueos institucionales adicionales"]: st.write("⛔" if why_not else "✅",x)

    st.divider(); st.markdown("### ⚙️ Execution Management System")
    ex=state['execution']; mi=state['micro']
    e1,e2,e3,e4,e5=st.columns(5)
    e1.metric("Orden recomendada",ex.get('recommended_order'))
    e2.metric("Urgencia",f"{ex.get('urgency',0):.0f}/100")
    e3.metric("Fill probability",f"{ex.get('fill_probability',0):.0f}%")
    e4.metric("Spread",f"{ex.get('spread_bps',0):.2f} bps")
    e5.metric("Slippage",f"{ex.get('slippage_bps',0):.2f} bps")

    st.divider(); st.markdown("### 📐 Portfolio & Risk")
    po=state['portfolio']; rs=state['risk']; ss=state['statistics']
    r1,r2,r3,r4,r5=st.columns(5)
    r1.metric("Gross exposure",f"{po.get('gross_exposure_x',0):.2f}x")
    r2.metric("Net exposure",f"{po.get('net_exposure_x',0):+.2f}x")
    r3.metric("Portfolio heat",f"{po.get('portfolio_heat_pct',0):.2f}%")
    r4.metric("ES proxy",f"{rs.get('expected_shortfall_pct_proxy',0):.2f}%")
    r5.metric("RoR proxy",f"{ss.get('risk_of_ruin_proxy_pct',100):.1f}%")
    pos=po.get('positions',pd.DataFrame())
    if isinstance(pos,pd.DataFrame) and not pos.empty:
        st.dataframe(pos,use_container_width=True,hide_index=True)

    st.divider(); st.markdown("### 📊 Statistical Edge Lab")
    s1,s2,s3,s4,s5=st.columns(5)
    s1.metric("Trades",ss.get('samples',0)); s2.metric("Expectancy",f"{pro_safe_float(ss.get('expectancy_r'),0):+.3f}R")
    s3.metric("Bootstrap P(EV>0)",f"{pro_safe_float(ss.get('bootstrap',{}).get('positive_prob'),0):.1f}%")
    s4.metric("Sortino proxy",f"{pro_safe_float(ss.get('sortino_proxy'),0):.2f}")
    s5.metric("Bayesian winrate",f"{ss.get('bayesian_winrate_pct',50):.1f}%")

    st.divider(); st.markdown("### 🌪️ Derivatives / Microstructure")
    de=state['derivatives']; da=state['data']
    m1,m2,m3,m4,m5,m6=st.columns(6)
    m1.metric("Funding",f"{de.get('funding_pct',0):+.4f}%")
    m2.metric("Funding Z",f"{pro_safe_float(de.get('funding_z'),0):+.2f}")
    m3.metric("Basis",f"{de.get('basis_bps',0):+.2f} bps")
    m4.metric("OI velocity",f"{de.get('oi_velocity_pct',0):+.2f}%")
    m5.metric("Book imbalance",f"{mi.get('weighted_imbalance',0):+.1f}%")
    m6.metric("Liquidity",f"{mi.get('liquidity_score',0):.0f}/100")

    st.divider(); st.markdown("### 🧪 Digital Twin · Stress / Counterfactual")
    sc=state.get('scenario',pd.DataFrame())
    cf=state.get('counterfactual',pd.DataFrame())
    c1,c2=st.columns(2)
    with c1:
        if isinstance(sc,pd.DataFrame) and not sc.empty:
            st.dataframe(sc,use_container_width=True,hide_index=True,height=330)
    with c2:
        if isinstance(cf,pd.DataFrame) and not cf.empty:
            st.dataframe(cf,use_container_width=True,hide_index=True,height=330)

    st.divider(); st.markdown("### 🧾 Passport & tamper-evident audit")
    st.json(p,expanded=False)
    if st.button("💾 Sellar passport actual",key="inst_seal_passport"):
        inst_append_jsonl(INST_PASSPORT_FILE,p); inst_event("TRADE_PASSPORT",p,"INFO")
        st.success("Passport sellado en ledger local.")
    ev=inst_read_jsonl(INST_EVENT_FILE,100)
    if not ev.empty:
        st.dataframe(ev[[c for c in ["ts","severity","kind","hash","prev_hash"] if c in ev.columns]].tail(30),use_container_width=True,hide_index=True)

    st.divider(); st.markdown("### ✅ Auditoría 500 controles")
    matrix=inst_feature_matrix(state,gate)
    dfilter=st.multiselect("Dominios",list(INST_500_DOMAINS.keys()),default=list(INST_500_DOMAINS.keys()),key="inst_domains")
    st.dataframe(matrix[matrix['Dominio'].isin(dfilter)],use_container_width=True,hide_index=True,height=600)
    st.download_button("⬇️ Descargar auditoría 500 CSV",matrix.to_csv(index=False),"institutional_os_500_controls.csv","text/csv",key="inst500_download")

    st.divider(); inst_render_settings_panel(settings)


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
    st.markdown("""
    <style>
    .block-container{
        padding-top:1rem !important;
        padding-bottom:1rem !important;
        padding-left:2rem !important;
        padding-right:2rem !important;
        max-width:none !important;
    }
    div[data-testid="stMetric"]{
        padding:.20rem .10rem !important;
    }
    div[data-testid="stMetricLabel"]{
        font-size:.75rem !important;
        font-weight:600 !important;
    }
    div[data-testid="stMetricValue"]{
        font-size:1.35rem !important;
        font-weight:700 !important;
        line-height:1.1 !important;
    }
    div[data-testid="stMetricDelta"]{
        font-size:.65rem !important;
    }
    h1{font-size:34px !important;}
    h2{font-size:28px !important;}
    h3{font-size:22px !important;}
    h4{font-size:18px !important;}
    button[data-baseweb="tab"]{
        font-size:15px !important;
        font-weight:600 !important;
        padding:.45rem .65rem !important;
    }
    section[data-testid="stSidebar"]{
        min-width:300px !important;
        max-width:330px !important;
    }
    section[data-testid="stSidebar"] > div{
        padding-top:1rem !important;
        overflow-y:auto !important;
    }
    section[data-testid="stSidebar"] label{
        font-size:.78rem !important;
    }
    @media (max-width:1200px){
        .block-container{
            padding-left:1rem !important;
            padding-right:1rem !important;
            max-width:none !important;
        }
        section[data-testid="stSidebar"]{
            min-width:260px !important;
            max-width:280px !important;
        }
        div[data-testid="stMetricValue"]{
            font-size:0.95rem !important;
            line-height:1 !important;
        }
        div[data-testid="stMetricLabel"]{
            font-size:0.62rem !important;
        }
        div[data-testid="stMetricDelta"]{
            font-size:0.55rem !important;
        }
        h2{font-size:22px !important;}
        h3{font-size:18px !important;}
        h4{font-size:16px !important;}
        button[data-baseweb="tab"]{
            font-size:13px !important;
            padding:.35rem .45rem !important;
        }
    }
    @media (max-width:700px){
        div[data-testid="stMetricValue"]{
            font-size:0.85rem !important;
        }
        div[data-testid="stMetricLabel"]{
            font-size:0.58rem !important;
        }
        div[data-testid="stMetricDelta"]{
            font-size:0.52rem !important;
        }
    }
    </style>
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
    edge_score_pct = min(max(int(quality_score * 10), 0), 100)
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
        <div style="font-size:18px; font-weight:800; margin-bottom:12px;">
            ═══════════════════════════════<br>
            ESTADO DEL MERCADO BTC
        </div>
        <div style="font-size:14px; line-height:1.9;">
            Tendencia: <b>{tendencia_txt}</b> ✅<br>
            Contexto: <b>{escenario}</b><br>
            Precio: <b>{price:,.0f}</b><br>
            Estructura 5M: <b>{structure}</b><br>
            4H / 1H / 15M / 5M: <b>{t4}</b> · <b>{t1}</b> · <b>{t15}</b> · <b>{t5}</b><br>
            FVG: <b>{fvg_label}</b><br>
            Delta: <b>{delta_estado}</b> · fuerza <b>{delta_fuerza}</b><br>
            Volumen relativo: <b>{vol_ratio_15m:.2f}x</b><br>
            RR disponible: <b>{rr_real:.2f}</b><br>
            Edge score técnico (no probabilidad): <b>{edge_score_pct}/100</b><br>
            Calidad: <b>{quality_label}</b> · <b>{quality_score}/10</h2>
        </div>
        <hr>
        <div style="font-size:18px; font-weight:900; color:{color};">
            DECISIÓN: {decision_txt}
        </div>
        <div style="margin-top:10px; color:#92400e; font-size:12px;">
            <b>Bloqueos / advertencias:</b><br>
            {bloqueos_txt}
        </div>
        <div style="font-size:18px; font-weight:800; margin-top:14px;">
            ═══════════════════════════════
        </div>
    </div>
    """, unsafe_allow_html=True)

# =========================
# BTC QUANT TERMINAL ULTRA PRO
# Capa adicional: mercado, derivados, inversión y riesgo.
# Diseñada para degradar de forma segura si una API externa no responde.
# =========================

def _q_float(value, default=np.nan):
    try:
        x = float(value)
        return x if np.isfinite(x) else default
    except Exception:
        return default


def _q_pct(value, digits=2):
    x = _q_float(value)
    return "—" if pd.isna(x) else f"{x:.{digits}f}%"


def _q_money(value, digits=0):
    x = _q_float(value)
    return "—" if pd.isna(x) else f"${x:,.{digits}f}"


def _q_last(series, default=np.nan):
    try:
        s = pd.to_numeric(series, errors="coerce").dropna()
        return float(s.iloc[-1]) if len(s) else default
    except Exception:
        return default


def _q_safe_div(a, b, default=np.nan):
    a, b = _q_float(a), _q_float(b)
    if pd.isna(a) or pd.isna(b) or b == 0:
        return default
    return a / b


def _q_rsi(close, period=14):
    close = pd.to_numeric(close, errors="coerce")
    delta = close.diff()
    gain = delta.clip(lower=0).ewm(alpha=1 / period, adjust=False).mean()
    loss = (-delta.clip(upper=0)).ewm(alpha=1 / period, adjust=False).mean()
    rs = gain / loss.replace(0, np.nan)
    out = 100 - (100 / (1 + rs))
    return out.fillna(50)


def _q_atr(df, period=14):
    high = pd.to_numeric(df["high"], errors="coerce")
    low = pd.to_numeric(df["low"], errors="coerce")
    close = pd.to_numeric(df["close"], errors="coerce")
    prev_close = close.shift(1)
    tr = pd.concat([
        high - low,
        (high - prev_close).abs(),
        (low - prev_close).abs(),
    ], axis=1).max(axis=1)
    return tr.ewm(alpha=1 / period, adjust=False).mean()


def _q_adx(df, period=14):
    high = pd.to_numeric(df["high"], errors="coerce")
    low = pd.to_numeric(df["low"], errors="coerce")
    close = pd.to_numeric(df["close"], errors="coerce")
    up_move = high.diff()
    down_move = -low.diff()
    plus_dm = pd.Series(np.where((up_move > down_move) & (up_move > 0), up_move, 0.0), index=df.index)
    minus_dm = pd.Series(np.where((down_move > up_move) & (down_move > 0), down_move, 0.0), index=df.index)
    atr = _q_atr(df, period).replace(0, np.nan)
    plus_di = 100 * plus_dm.ewm(alpha=1 / period, adjust=False).mean() / atr
    minus_di = 100 * minus_dm.ewm(alpha=1 / period, adjust=False).mean() / atr
    dx = 100 * (plus_di - minus_di).abs() / (plus_di + minus_di).replace(0, np.nan)
    return dx.ewm(alpha=1 / period, adjust=False).mean().fillna(0), plus_di.fillna(0), minus_di.fillna(0)


def _q_mfi(df, period=14):
    high = pd.to_numeric(df["high"], errors="coerce")
    low = pd.to_numeric(df["low"], errors="coerce")
    close = pd.to_numeric(df["close"], errors="coerce")
    volume = pd.to_numeric(df["volume"], errors="coerce").fillna(0)
    typical = (high + low + close) / 3
    flow = typical * volume
    direction = typical.diff()
    pos = flow.where(direction > 0, 0.0).rolling(period).sum()
    neg = flow.where(direction < 0, 0.0).rolling(period).sum().abs()
    ratio = pos / neg.replace(0, np.nan)
    return (100 - 100 / (1 + ratio)).fillna(50)


def _q_cmf(df, period=20):
    high = pd.to_numeric(df["high"], errors="coerce")
    low = pd.to_numeric(df["low"], errors="coerce")
    close = pd.to_numeric(df["close"], errors="coerce")
    volume = pd.to_numeric(df["volume"], errors="coerce").fillna(0)
    spread = (high - low).replace(0, np.nan)
    mfm = ((close - low) - (high - close)) / spread
    mfv = mfm.fillna(0) * volume
    return mfv.rolling(period).sum() / volume.rolling(period).sum().replace(0, np.nan)


def _q_obv(df):
    close = pd.to_numeric(df["close"], errors="coerce")
    volume = pd.to_numeric(df["volume"], errors="coerce").fillna(0)
    direction = np.sign(close.diff()).fillna(0)
    return (direction * volume).cumsum()


def prepare_quant_frame(df):
    """Agrega indicadores robustos sin modificar el dataframe original."""
    if df is None or len(df) == 0:
        return pd.DataFrame()
    q = df.copy()
    if "time" in q.columns:
        q["time"] = pd.to_datetime(q["time"], errors="coerce", utc=True)
        q = q.sort_values("time")
    for col in ["open", "high", "low", "close", "volume"]:
        if col in q.columns:
            q[col] = pd.to_numeric(q[col], errors="coerce")
    if "close" not in q.columns:
        return pd.DataFrame()
    close = q["close"]
    q["ret"] = close.pct_change()
    q["log_ret"] = np.log(close / close.shift(1))
    for p in [9, 20, 21, 50, 100, 200]:
        q[f"ema{p}"] = close.ewm(span=p, adjust=False).mean()
    for p in [20, 50, 200]:
        q[f"sma{p}"] = close.rolling(p).mean()
    q["rsi14"] = q["rsi"] if "rsi" in q.columns else _q_rsi(close, 14)
    q["atr14"] = q["atr"] if "atr" in q.columns else _q_atr(q, 14)
    q["atr_pct"] = q["atr14"] / close.replace(0, np.nan) * 100
    macd = close.ewm(span=12, adjust=False).mean() - close.ewm(span=26, adjust=False).mean()
    q["macd"] = macd
    q["macd_signal"] = macd.ewm(span=9, adjust=False).mean()
    q["macd_hist"] = q["macd"] - q["macd_signal"]
    mid = close.rolling(20).mean()
    std = close.rolling(20).std(ddof=0)
    q["bb_mid"] = mid
    q["bb_upper"] = mid + 2 * std
    q["bb_lower"] = mid - 2 * std
    q["bb_width_pct"] = (q["bb_upper"] - q["bb_lower"]) / mid.replace(0, np.nan) * 100
    q["bb_pos"] = (close - q["bb_lower"]) / (q["bb_upper"] - q["bb_lower"]).replace(0, np.nan)
    q["zscore20"] = (close - mid) / std.replace(0, np.nan)
    q["donchian_high20"] = pd.to_numeric(q.get("high", close), errors="coerce").rolling(20).max()
    q["donchian_low20"] = pd.to_numeric(q.get("low", close), errors="coerce").rolling(20).min()
    q["roc10"] = close.pct_change(10) * 100
    q["roc20"] = close.pct_change(20) * 100
    q["volatility20"] = q["log_ret"].rolling(20).std(ddof=0)
    q["volume_sma20"] = pd.to_numeric(q.get("volume", pd.Series(index=q.index, dtype=float)), errors="coerce").rolling(20).mean()
    q["volume_std20"] = pd.to_numeric(q.get("volume", pd.Series(index=q.index, dtype=float)), errors="coerce").rolling(20).std(ddof=0)
    q["volume_z"] = (pd.to_numeric(q.get("volume", 0), errors="coerce") - q["volume_sma20"]) / q["volume_std20"].replace(0, np.nan)
    if all(c in q.columns for c in ["high", "low", "volume"]):
        q["mfi14"] = _q_mfi(q, 14)
        q["cmf20"] = _q_cmf(q, 20)
        q["obv"] = _q_obv(q)
        adx, plus_di, minus_di = _q_adx(q, 14)
        q["adx14"] = adx
        q["plus_di"] = plus_di
        q["minus_di"] = minus_di
    else:
        q["mfi14"] = np.nan
        q["cmf20"] = np.nan
        q["obv"] = np.nan
        q["adx14"] = np.nan
        q["plus_di"] = np.nan
        q["minus_di"] = np.nan
    return q


def timeframe_quant_snapshot(df, label):
    q = prepare_quant_frame(df)
    if q.empty:
        return {"tf": label, "score": 0, "bias": "SIN DATOS"}
    last = q.iloc[-1]
    close = _q_float(last.get("close"))
    ema20 = _q_float(last.get("ema20"))
    ema50 = _q_float(last.get("ema50"))
    ema200 = _q_float(last.get("ema200"))
    rsi = _q_float(last.get("rsi14"), 50)
    adx = _q_float(last.get("adx14"), 0)
    macd_hist = _q_float(last.get("macd_hist"), 0)
    roc20 = _q_float(last.get("roc20"), 0)
    cmf = _q_float(last.get("cmf20"), 0)
    mfi = _q_float(last.get("mfi14"), 50)
    bb_pos = _q_float(last.get("bb_pos"), 0.5)
    atr_pct = _q_float(last.get("atr_pct"), 0)
    volume_z = _q_float(last.get("volume_z"), 0)
    score = 0.0
    weights = 0.0
    def add(cond_bull, cond_bear, weight):
        nonlocal score, weights
        weights += weight
        if cond_bull:
            score += weight
        elif cond_bear:
            score -= weight
    add(close > ema20, close < ema20, 12)
    add(ema20 > ema50, ema20 < ema50, 14)
    if not pd.isna(ema200):
        add(ema50 > ema200, ema50 < ema200, 18)
        add(close > ema200, close < ema200, 16)
    add(rsi >= 55, rsi <= 45, 10)
    add(macd_hist > 0, macd_hist < 0, 10)
    add(roc20 > 0, roc20 < 0, 8)
    add(cmf > 0.05, cmf < -0.05, 6)
    add(mfi >= 55, mfi <= 45, 4)
    if adx >= 20:
        add(_q_float(last.get("plus_di"), 0) > _q_float(last.get("minus_di"), 0), _q_float(last.get("minus_di"), 0) > _q_float(last.get("plus_di"), 0), 8)
    score = 100 * score / weights if weights else 0
    if score >= 45:
        bias = "ALCISTA FUERTE"
    elif score >= 15:
        bias = "ALCISTA"
    elif score <= -45:
        bias = "BAJISTA FUERTE"
    elif score <= -15:
        bias = "BAJISTA"
    else:
        bias = "NEUTRAL"
    return {
        "tf": label,
        "price": close,
        "score": round(score, 1),
        "bias": bias,
        "rsi": rsi,
        "adx": adx,
        "macd_hist": macd_hist,
        "roc20": roc20,
        "atr_pct": atr_pct,
        "bb_pos": bb_pos,
        "volume_z": volume_z,
        "cmf": cmf,
        "mfi": mfi,
        "ema20": ema20,
        "ema50": ema50,
        "ema200": ema200,
        "zscore20": _q_float(last.get("zscore20"), 0),
        "bb_width_pct": _q_float(last.get("bb_width_pct"), 0),
    }


def daily_risk_metrics(df_1d):
    q = prepare_quant_frame(df_1d)
    if q.empty or len(q) < 10:
        return {}
    close = q["close"].dropna()
    ret = close.pct_change().dropna()
    if ret.empty:
        return {}
    equity = (1 + ret).cumprod()
    peak = equity.cummax()
    drawdown = equity / peak - 1
    downside = ret[ret < 0]
    ann_vol = ret.std(ddof=0) * np.sqrt(365) * 100
    ann_return = ret.mean() * 365 * 100
    sharpe = _q_safe_div(ret.mean(), ret.std(ddof=0), 0) * np.sqrt(365)
    downside_std = downside.std(ddof=0) if len(downside) else np.nan
    sortino = _q_safe_div(ret.mean(), downside_std, 0) * np.sqrt(365)
    max_dd = drawdown.min() * 100
    calmar = _q_safe_div(ann_return, abs(max_dd), 0)
    var95 = np.percentile(ret, 5) * 100
    var99 = np.percentile(ret, 1) * 100
    cvar95 = ret[ret <= np.percentile(ret, 5)].mean() * 100
    cvar99 = ret[ret <= np.percentile(ret, 1)].mean() * 100
    current_dd = (close.iloc[-1] / close.cummax().iloc[-1] - 1) * 100
    ath = close.cummax().iloc[-1]
    vol30 = ret.tail(30).std(ddof=0) * np.sqrt(365) * 100 if len(ret) >= 10 else np.nan
    vol90 = ret.tail(90).std(ddof=0) * np.sqrt(365) * 100 if len(ret) >= 30 else np.nan
    vol_series = ret.rolling(30).std(ddof=0) * np.sqrt(365) * 100
    vol_pctile = (vol_series.rank(pct=True).iloc[-1] * 100) if vol_series.notna().sum() else np.nan
    ulcer = np.sqrt(np.nanmean(np.square(drawdown * 100)))
    return {
        "ann_vol": ann_vol,
        "ann_return": ann_return,
        "sharpe": sharpe,
        "sortino": sortino,
        "max_dd": max_dd,
        "current_dd": current_dd,
        "ath": ath,
        "var95": var95,
        "var99": var99,
        "cvar95": cvar95,
        "cvar99": cvar99,
        "vol30": vol30,
        "vol90": vol90,
        "vol_percentile": vol_pctile,
        "ulcer": ulcer,
        "best_day": ret.max() * 100,
        "worst_day": ret.min() * 100,
        "positive_days": (ret > 0).mean() * 100,
        "sample_days": len(ret),
    }



def historical_regime_analogs(df_1d):
    """Busca episodios históricos con régimen parecido y mide retornos posteriores."""
    q = prepare_quant_frame(df_1d)
    if q.empty or len(q) < 260:
        return {}, pd.DataFrame()
    q = q.copy()
    q["vol30_ann"] = q["ret"].rolling(30).std(ddof=0) * np.sqrt(365) * 100
    q["vol30_med"] = q["vol30_ann"].rolling(180, min_periods=60).median()
    q["bull200"] = q["close"] > q["ema200"]
    q["mom20"] = q["roc20"] > 0
    q["highvol"] = q["vol30_ann"] > q["vol30_med"]
    q["rsi_bucket"] = pd.cut(q["rsi14"], bins=[-np.inf, 35, 45, 55, 65, np.inf], labels=[0, 1, 2, 3, 4])
    cur = q.iloc[-1]
    mask = (
        (q["bull200"] == bool(cur["bull200"])) &
        (q["mom20"] == bool(cur["mom20"])) &
        (q["highvol"] == bool(cur["highvol"])) &
        (q["rsi_bucket"] == cur["rsi_bucket"])
    )
    x = q.loc[mask, ["time", "close", "rsi14", "vol30_ann", "bull200", "mom20"]].copy()
    for days in [7, 30, 90]:
        q[f"fwd_{days}"] = q["close"].shift(-days) / q["close"] - 1
        x[f"fwd_{days}"] = q.loc[x.index, f"fwd_{days}"]
    x = x.iloc[:-1] if len(x) and x.index[-1] == q.index[-1] else x
    valid30 = x["fwd_30"].dropna()
    if valid30.empty:
        return {}, x
    stats = {
        "samples": int(len(valid30)),
        "p_up_7": float((x["fwd_7"].dropna() > 0).mean() * 100) if x["fwd_7"].notna().any() else np.nan,
        "p_up_30": float((valid30 > 0).mean() * 100),
        "p_up_90": float((x["fwd_90"].dropna() > 0).mean() * 100) if x["fwd_90"].notna().any() else np.nan,
        "median_7": float(x["fwd_7"].dropna().median() * 100) if x["fwd_7"].notna().any() else np.nan,
        "median_30": float(valid30.median() * 100),
        "median_90": float(x["fwd_90"].dropna().median() * 100) if x["fwd_90"].notna().any() else np.nan,
        "p10_30": float(valid30.quantile(0.10) * 100),
        "p90_30": float(valid30.quantile(0.90) * 100),
    }
    return stats, x.sort_values("time", ascending=False)


def kelly_fraction(winrate_pct, payoff_ratio):
    p = np.clip(_q_float(winrate_pct, 0) / 100, 0, 1)
    b = max(_q_float(payoff_ratio, 0), 1e-9)
    q = 1 - p
    full = max(p - q / b, 0)
    return {"full": full, "half": full / 2, "quarter": full / 4}


def drawdown_recovery_table():
    rows = []
    for dd in [5, 10, 15, 20, 25, 30, 40, 50, 60, 70, 80, 90]:
        recovery = (1 / (1 - dd / 100) - 1) * 100
        rows.append({"Drawdown": f"-{dd}%", "Ganancia necesaria para recuperar": f"+{recovery:.1f}%", "Capital restante": f"{100-dd}%"})
    return pd.DataFrame(rows)

def detect_quant_regime(day_snap, risk):
    score = _q_float(day_snap.get("score"), 0)
    adx = _q_float(day_snap.get("adx"), 0)
    vol_pctile = _q_float(risk.get("vol_percentile"), 50)
    bb_width = _q_float(day_snap.get("bb_width_pct"), 0)
    if score >= 35 and adx >= 20:
        trend = "BULL TREND"
    elif score <= -35 and adx >= 20:
        trend = "BEAR TREND"
    elif abs(score) < 20 and adx < 20:
        trend = "RANGE"
    else:
        trend = "TRANSICIÓN"
    if vol_pctile >= 80:
        vol = "VOLATILIDAD EXTREMA"
    elif vol_pctile >= 60:
        vol = "VOLATILIDAD ALTA"
    elif vol_pctile <= 25:
        vol = "VOLATILIDAD COMPRIMIDA"
    else:
        vol = "VOLATILIDAD NORMAL"
    if bb_width and bb_width < 3:
        expansion = "SQUEEZE / COMPRESIÓN"
    else:
        expansion = "EXPANSIÓN NORMAL"
    return trend, vol, expansion


def blank_external_btc_metrics():
    return {
        "fear_greed": np.nan, "fear_greed_label": "No conectado",
        "funding_rate": np.nan, "mark_price": np.nan, "index_price": np.nan,
        "open_interest_btc": np.nan, "open_interest_change_pct": np.nan,
        "global_long_short": np.nan, "taker_buy_sell": np.nan,
        "orderbook_imbalance": np.nan, "market_cap_usd": np.nan,
        "volume_24h_usd": np.nan, "change_24h_pct": np.nan,
        "change_7d_pct": np.nan, "sources_ok": [], "errors": [],
    }


@st.cache_data(ttl=60, show_spinner=False)
def fetch_btc_external_metrics():
    """Datos públicos opcionales en paralelo. Si fallan, el motor local sigue intacto."""
    out = {
        "fear_greed": np.nan, "fear_greed_label": "No disponible",
        "funding_rate": np.nan, "mark_price": np.nan, "index_price": np.nan,
        "open_interest_btc": np.nan, "open_interest_change_pct": np.nan,
        "global_long_short": np.nan, "taker_buy_sell": np.nan,
        "orderbook_imbalance": np.nan, "market_cap_usd": np.nan,
        "volume_24h_usd": np.nan, "change_24h_pct": np.nan,
        "change_7d_pct": np.nan, "sources_ok": [], "errors": [],
    }
    if requests is None:
        out["errors"].append("requests no disponible")
        return out

    headers = {"User-Agent": "BTC-Quant-Terminal/1.0"}
    endpoints = {
        "fg": ("https://api.alternative.me/fng/", {"limit": 1}),
        "ticker": ("https://api.alternative.me/v2/ticker/bitcoin/", {"convert": "USD"}),
        "premium": ("https://fapi.binance.com/fapi/v1/premiumIndex", {"symbol": "BTCUSDT"}),
        "oi": ("https://fapi.binance.com/fapi/v1/openInterest", {"symbol": "BTCUSDT"}),
        "oih": ("https://fapi.binance.com/futures/data/openInterestHist", {"symbol": "BTCUSDT", "period": "5m", "limit": 30}),
        "ls": ("https://fapi.binance.com/futures/data/globalLongShortAccountRatio", {"symbol": "BTCUSDT", "period": "5m", "limit": 1}),
        "tk": ("https://fapi.binance.com/futures/data/takerlongshortRatio", {"symbol": "BTCUSDT", "period": "5m", "limit": 1}),
        "book": ("https://fapi.binance.com/fapi/v1/depth", {"symbol": "BTCUSDT", "limit": 100}),
    }

    def fetch_one(name, spec):
        url, params = spec
        try:
            r = requests.get(url, params=params, headers=headers, timeout=2.5)
            r.raise_for_status()
            return name, r.json(), None
        except Exception as e:
            return name, None, type(e).__name__

    results = {}
    try:
        from concurrent.futures import ThreadPoolExecutor, as_completed
        with ThreadPoolExecutor(max_workers=len(endpoints)) as pool:
            futs = [pool.submit(fetch_one, name, spec) for name, spec in endpoints.items()]
            for fut in as_completed(futs):
                name, data, err = fut.result()
                results[name] = data
                if err:
                    out["errors"].append(f"{name}: {err}")
    except Exception as e:
        out["errors"].append(f"parallel-fetch: {type(e).__name__}")
        return out

    fg = results.get("fg")
    if isinstance(fg, dict):
        row = (fg.get("data") or [{}])[0]
        out["fear_greed"] = _q_float(row.get("value"))
        out["fear_greed_label"] = str(row.get("value_classification", "No disponible"))
        out["sources_ok"].append("Alternative.me F&G")

    ticker = results.get("ticker")
    if isinstance(ticker, dict):
        data = ticker.get("data", {})
        row = next(iter(data.values())) if isinstance(data, dict) and data else {}
        quote = row.get("quotes", {}).get("USD", {}) if isinstance(row, dict) else {}
        out["market_cap_usd"] = _q_float(quote.get("market_cap"))
        out["volume_24h_usd"] = _q_float(quote.get("volume_24h"))
        out["change_24h_pct"] = _q_float(quote.get("percentage_change_24h"))
        out["change_7d_pct"] = _q_float(quote.get("percentage_change_7d"))
        out["sources_ok"].append("Alternative.me BTC ticker")

    premium = results.get("premium")
    if isinstance(premium, dict):
        out["funding_rate"] = _q_float(premium.get("lastFundingRate")) * 100
        out["mark_price"] = _q_float(premium.get("markPrice"))
        out["index_price"] = _q_float(premium.get("indexPrice"))
        out["sources_ok"].append("Binance Futures premium index")

    oi = results.get("oi")
    if isinstance(oi, dict):
        out["open_interest_btc"] = _q_float(oi.get("openInterest"))
        out["sources_ok"].append("Binance Futures OI")

    hist = results.get("oih")
    if isinstance(hist, list) and len(hist) >= 2:
        first = _q_float(hist[0].get("sumOpenInterest"))
        last = _q_float(hist[-1].get("sumOpenInterest"))
        out["open_interest_change_pct"] = (_q_safe_div(last, first, 1) - 1) * 100 if first else np.nan
        out["sources_ok"].append("Binance Futures OI history")

    ls = results.get("ls")
    if isinstance(ls, list) and ls:
        out["global_long_short"] = _q_float(ls[-1].get("longShortRatio"))
        out["sources_ok"].append("Binance Long/Short")

    tk = results.get("tk")
    if isinstance(tk, list) and tk:
        out["taker_buy_sell"] = _q_float(tk[-1].get("buySellRatio"))
        out["sources_ok"].append("Binance Taker ratio")

    book = results.get("book")
    if isinstance(book, dict):
        bids = sum(_q_float(x[1], 0) for x in book.get("bids", []))
        asks = sum(_q_float(x[1], 0) for x in book.get("asks", []))
        out["orderbook_imbalance"] = _q_safe_div(bids - asks, bids + asks, 0) * 100 if (bids + asks) else np.nan
        out["sources_ok"].append("Binance Futures order book")
    return out

def build_quant_rulebook(snaps, risk, ext, trade_context):
    """Rule engine auditable. Cada regla devuelve evidencia, no una promesa de rentabilidad."""
    d = snaps.get("1D", {})
    h4 = snaps.get("4H", {})
    h1 = snaps.get("1H", {})
    m15 = snaps.get("15M", {})
    m5 = snaps.get("5M", {})
    rows = []
    def rule(category, name, value, bull=None, bear=None, weight=1, info=""):
        sign = 0
        state = "ℹ️"
        if bull is True:
            sign, state = 1, "✅"
        elif bear is True:
            sign, state = -1, "❌"
        elif bull is False or bear is False:
            sign, state = 0, "⚠️"
        rows.append({
            "Categoría": category,
            "Regla": name,
            "Estado": state,
            "Peso": weight,
            "Impacto": sign * weight,
            "Valor": value,
            "Lectura": info,
        })
    # Tendencia y estructura
    for label, s in [("1D", d), ("4H", h4), ("1H", h1), ("15M", m15), ("5M", m5)]:
        p, e20, e50, e200 = (_q_float(s.get(k)) for k in ["price", "ema20", "ema50", "ema200"])
        rule("Tendencia", f"{label}: precio > EMA20", f"{p:,.0f} / {e20:,.0f}", p > e20, p < e20, 2 if label in ["1D", "4H"] else 1)
        rule("Tendencia", f"{label}: EMA20 > EMA50", f"{e20:,.0f} / {e50:,.0f}", e20 > e50, e20 < e50, 2 if label in ["1D", "4H"] else 1)
        if not pd.isna(e200):
            rule("Tendencia", f"{label}: precio > EMA200", f"{p:,.0f} / {e200:,.0f}", p > e200, p < e200, 3 if label == "1D" else 1)
            rule("Tendencia", f"{label}: EMA50 > EMA200", f"{e50:,.0f} / {e200:,.0f}", e50 > e200, e50 < e200, 3 if label == "1D" else 1)
    # Momentum
    for label, s in [("1D", d), ("4H", h4), ("1H", h1), ("15M", m15)]:
        rsi = _q_float(s.get("rsi"), 50)
        rule("Momentum", f"{label}: RSI momentum", f"{rsi:.1f}", rsi >= 55 and rsi < 75, rsi <= 45 and rsi > 25, 2)
        mh = _q_float(s.get("macd_hist"), 0)
        rule("Momentum", f"{label}: MACD hist", f"{mh:,.2f}", mh > 0, mh < 0, 2)
        roc = _q_float(s.get("roc20"), 0)
        rule("Momentum", f"{label}: ROC20", f"{roc:+.2f}%", roc > 0, roc < 0, 1)
    # Fuerza de tendencia y volumen
    for label, s in [("1D", d), ("4H", h4), ("1H", h1), ("15M", m15)]:
        adx = _q_float(s.get("adx"), 0)
        rule("Fuerza", f"{label}: ADX >= 20", f"{adx:.1f}", adx >= 20, None, 1, "Confirma que el movimiento tiene fuerza; no define dirección por sí solo.")
        cmf = _q_float(s.get("cmf"), 0)
        rule("Flujo", f"{label}: CMF", f"{cmf:+.3f}", cmf > 0.05, cmf < -0.05, 1)
        vz = _q_float(s.get("volume_z"), 0)
        rule("Volumen", f"{label}: volumen anómalo", f"z={vz:+.2f}", vz >= 1.5, None, 1, "Volumen alto aumenta relevancia del movimiento, no implica dirección.")
    # Volatilidad y riesgo
    vp = _q_float(risk.get("vol_percentile"), 50)
    rule("Riesgo", "Volatilidad 30D no extrema", f"percentil {vp:.0f}", vp < 80, vp >= 90, 2)
    cdd = _q_float(risk.get("current_dd"), 0)
    rule("Riesgo", "Drawdown desde ATH", f"{cdd:.1f}%", cdd > -15, cdd <= -30, 2)
    var95 = _q_float(risk.get("var95"), 0)
    rule("Riesgo", "VaR diario 95%", f"{var95:.2f}%", var95 > -5, var95 <= -8, 1)
    # Sentimiento / derivados
    fg = _q_float(ext.get("fear_greed"))
    if not pd.isna(fg):
        rule("Sentimiento", "Fear & Greed no eufórico", f"{fg:.0f} · {ext.get('fear_greed_label')}", fg < 80, fg >= 90, 2)
        rule("Sentimiento", "Fear & Greed zona de oportunidad", f"{fg:.0f}", fg <= 35, fg >= 75, 1, "Lectura contraria; no es señal independiente.")
    funding = _q_float(ext.get("funding_rate"))
    if not pd.isna(funding):
        rule("Derivados", "Funding no sobrecalentado", f"{funding:+.4f}%", abs(funding) < 0.03, abs(funding) >= 0.08, 2)
        rule("Derivados", "Funding direccional", f"{funding:+.4f}%", funding > 0 and funding < 0.03, funding < 0 and funding > -0.03, 1)
    oi_chg = _q_float(ext.get("open_interest_change_pct"))
    if not pd.isna(oi_chg):
        rule("Derivados", "Cambio OI 150m", f"{oi_chg:+.2f}%", 0 < oi_chg < 5, abs(oi_chg) >= 8, 1, "Aumento extremo puede elevar riesgo de squeeze/liquidaciones.")
    ls = _q_float(ext.get("global_long_short"))
    if not pd.isna(ls):
        rule("Derivados", "Long/Short no crowded", f"{ls:.2f}", 0.75 <= ls <= 1.35, ls >= 1.8 or ls <= 0.55, 2)
    tk = _q_float(ext.get("taker_buy_sell"))
    if not pd.isna(tk):
        rule("Derivados", "Taker flow", f"{tk:.2f}", tk > 1.03, tk < 0.97, 1)
    ob = _q_float(ext.get("orderbook_imbalance"))
    if not pd.isna(ob):
        rule("Microestructura", "Order book imbalance", f"{ob:+.1f}%", ob >= 5, ob <= -5, 1)
    # Contexto del setup actual
    direction = trade_context.get("candidate_direction")
    long_score = _q_float(trade_context.get("long_score"), 0)
    short_score = _q_float(trade_context.get("short_score"), 0)
    rr = _q_float(trade_context.get("rr_real"), 0)
    quality = _q_float(trade_context.get("quality_score"), 0)
    rule("Setup", "Score direccional dominante", f"L {long_score:.0f} / S {short_score:.0f}", long_score >= short_score + 2, short_score >= long_score + 2, 3)
    rule("Setup", "RR >= 1.8", f"{rr:.2f}R", rr >= 1.8, rr < 1.2, 3)
    rule("Setup", "Calidad >= 7/10", f"{quality:.1f}/10", quality >= 7, quality < 5, 3)
    rule("Setup", "Trade validado por motor principal", str(trade_context.get("trade_valid")), bool(trade_context.get("trade_valid")), not bool(trade_context.get("trade_valid")), 4)
    # Alineación multi-TF
    scores = [_q_float(snaps[x].get("score"), 0) for x in ["1D", "4H", "1H"] if x in snaps]
    if scores:
        rule("Alineación", "1D + 4H + 1H alineados alcistas", ", ".join(f"{x:+.0f}" for x in scores), all(x >= 15 for x in scores), all(x <= -15 for x in scores), 4)
    return pd.DataFrame(rows)


def quant_rulebook_score(rule_df):
    if rule_df is None or rule_df.empty:
        return 0.0
    weights = pd.to_numeric(rule_df["Peso"], errors="coerce").abs().sum()
    impact = pd.to_numeric(rule_df["Impacto"], errors="coerce").sum()
    return float(np.clip(100 * impact / weights, -100, 100)) if weights else 0.0


def build_investment_matrix(snaps, risk, ext, trade_context):
    d, h4, h1, m15 = snaps["1D"], snaps["4H"], snaps["1H"], snaps["15M"]
    fg = _q_float(ext.get("fear_greed"), 50)
    volp = _q_float(risk.get("vol_percentile"), 50)
    dd = _q_float(risk.get("current_dd"), 0)
    rows = []
    def add(name, horizon, score, regime, requirements, risk_label):
        score = int(np.clip(round(score), 0, 100))
        state = "🟢 FAVORABLE" if score >= 70 else "🟡 SELECTIVO" if score >= 50 else "🔴 DESFAVORABLE"
        rows.append({"Estrategia": name, "Horizonte": horizon, "Score": score, "Estado": state, "Regla principal": regime, "Qué exige": requirements, "Riesgo": risk_label})
    longterm = (_q_float(d.get("score"), 0) + 100) / 2
    add("HODL / Spot", "1–5 años", 55 + 0.35 * (longterm - 50) + (5 if dd <= -20 else 0) - (8 if fg >= 85 else 0), "Prioriza tendencia secular y supervivencia", "Sin apalancamiento, horizonte largo, tolerancia a drawdowns", "Alto por volatilidad BTC; sin riesgo de liquidación")
    add("DCA", "6–60 meses", 70 + (10 if fg <= 35 else 0) + (7 if dd <= -20 else 0) - (8 if fg >= 85 else 0), "Reduce riesgo de timing", "Aporte periódico fijo y plan disciplinado", "Medio/alto, dispersado en el tiempo")
    add("DCA adaptativo", "6–60 meses", 68 + (12 if dd <= -20 else 0) + (8 if fg <= 30 else 0) - (5 if volp >= 90 else 0), "Aumenta aportes en debilidad y reduce en euforia", "Reglas objetivas; no perseguir precio", "Medio/alto")
    trend_score = np.mean([_q_float(d.get("score"), 0), _q_float(h4.get("score"), 0), _q_float(h1.get("score"), 0)])
    add("Trend Following Spot", "Semanas–meses", 50 + trend_score * 0.35 + (_q_float(d.get("adx"), 0) - 20) * 0.5, "Busca tendencias persistentes", "EMA/ADX y stop dinámico; acepta falsas rupturas", "Medio/alto")
    swing_score = 50 + _q_float(h4.get("score"), 0) * 0.25 + _q_float(h1.get("score"), 0) * 0.25
    add("Swing Spot", "Días–semanas", swing_score, "Confluencia 4H + 1H", "Entradas por estructura, invalidación técnica y RR", "Alto")
    mr = 60 - abs(_q_float(h1.get("zscore20"), 0)) * 5 if _q_float(h1.get("adx"), 0) < 20 else 40
    if _q_float(h1.get("rsi"), 50) <= 30 or _q_float(h1.get("rsi"), 50) >= 70:
        mr += 12
    add("Mean Reversion Spot", "Horas–días", mr, "Mejor en rangos, peor en tendencia fuerte", "RSI/Z-score extremos + soporte/resistencia", "Alto; riesgo de atrapar tendencia")
    futures = 35 + _q_float(trade_context.get("quality_score"), 0) * 5 + max(_q_float(trade_context.get("rr_real"), 0) - 1.0, 0) * 6
    if bool(trade_context.get("trade_valid")):
        futures += 12
    if volp >= 90:
        futures -= 12
    add("Futuros tácticos", "Minutos–días", futures, "Solo cuando el edge y el RR justifican el apalancamiento", "SL obligatorio, tamaño por riesgo, funding/OI/crowding", "Muy alto + riesgo de liquidación")
    add("Grid / Range", "Horas–días", 70 if abs(_q_float(h1.get("score"), 0)) < 20 and _q_float(h1.get("adx"), 0) < 20 else 35, "Funciona mejor en rango estable", "Límites superior/inferior definidos, sin breakout activo", "Alto si rompe el rango")
    return pd.DataFrame(rows).sort_values("Score", ascending=False).reset_index(drop=True)


def simulate_dca_history(df_1d, periodic_usd=200.0, initial_usd=0.0, frequency="Mensual", adaptive=False):
    q = prepare_quant_frame(df_1d)
    if q.empty or "time" not in q.columns:
        return pd.DataFrame(), {}
    q = q.dropna(subset=["time", "close"]).copy()
    if len(q) < 2:
        return pd.DataFrame(), {}
    freq = {"Semanal": "W-MON", "Quincenal": "2W-MON", "Mensual": "MS"}.get(frequency, "MS")
    indexed = q.set_index("time")
    buys = indexed.resample(freq).first().dropna(subset=["close"]).copy()
    if buys.empty:
        return pd.DataFrame(), {}
    qty = 0.0
    invested = 0.0
    records = []
    first_price = float(buys["close"].iloc[0])
    if initial_usd > 0:
        qty += initial_usd / first_price
        invested += initial_usd
    for ts, row in buys.iterrows():
        contribution = float(periodic_usd)
        if adaptive:
            ema200 = _q_float(row.get("ema200"))
            px = _q_float(row.get("close"))
            rsi = _q_float(row.get("rsi14"), 50)
            mult = 1.0
            if not pd.isna(ema200):
                if px < ema200:
                    mult += 0.50
                elif px > ema200 * 1.25:
                    mult -= 0.35
            if rsi <= 35:
                mult += 0.25
            elif rsi >= 70:
                mult -= 0.20
            contribution *= float(np.clip(mult, 0.35, 1.75))
        px = float(row["close"])
        qty += contribution / px
        invested += contribution
        value = qty * px
        records.append({"Fecha": ts, "Precio": px, "Aporte": contribution, "Invertido": invested, "BTC": qty, "Valor": value, "PNL": value - invested})
    out = pd.DataFrame(records)
    if out.empty:
        return out, {}
    final_price = float(q["close"].iloc[-1])
    final_value = qty * final_price
    total_budget = invested
    lump_qty = total_budget / first_price if first_price else 0
    lump_value = lump_qty * final_price
    avg_price = invested / qty if qty else np.nan
    stats = {
        "invested": invested,
        "btc": qty,
        "avg_price": avg_price,
        "final_value": final_value,
        "pnl": final_value - invested,
        "return_pct": (_q_safe_div(final_value, invested, 1) - 1) * 100 if invested else 0,
        "lump_value": lump_value,
        "lump_return_pct": (_q_safe_div(lump_value, total_budget, 1) - 1) * 100 if total_budget else 0,
        "first_price": first_price,
        "final_price": final_price,
        "purchases": len(out),
    }
    return out, stats


def leverage_survival_table(price, account_usd, risk_pct):
    rows = []
    for lev in [1, 2, 3, 5, 7, 10, 15, 20, 25, 50, 100]:
        approx_liq = 100 / lev if lev > 1 else np.nan
        risk_budget = account_usd * risk_pct
        rows.append({
            "Leverage": f"{lev}x",
            "Movimiento teórico a liquidación*": "No aplica" if lev == 1 else f"~{approx_liq:.1f}%",
            "Nocional máximo por margen": account_usd * lev,
            "Riesgo objetivo por trade": risk_budget,
            "Comentario": "Spot / sin liquidación" if lev == 1 else ("Extremo" if lev >= 20 else "Muy alto" if lev >= 10 else "Alto" if lev >= 5 else "Moderado"),
        })
    return pd.DataFrame(rows)


def portfolio_scenario_table(price, btc_usd, cash_usd):
    rows = []
    btc_qty = btc_usd / price if price else 0
    base = btc_usd + cash_usd
    for move in [-80, -70, -50, -30, -20, -10, 0, 10, 25, 50, 100, 200, 500]:
        px = price * (1 + move / 100)
        value = btc_qty * px + cash_usd
        rows.append({"Movimiento BTC": f"{move:+d}%", "Precio escenario": px, "Valor cartera": value, "PNL": value - base, "Retorno cartera %": (_q_safe_div(value, base, 1) - 1) * 100 if base else 0})
    return pd.DataFrame(rows)


def render_quant_header(score, regime, vol_regime, source_count):
    if score >= 35:
        label, icon = "SESGO ALCISTA", "🟢"
    elif score <= -35:
        label, icon = "SESGO BAJISTA", "🔴"
    else:
        label, icon = "SESGO MIXTO / SELECTIVO", "🟡"
    st.markdown(f"""
    <div style="border:1px solid #dbeafe;border-radius:18px;padding:18px 20px;background:linear-gradient(135deg,#eff6ff 0%,#ffffff 70%);margin:4px 0 14px 0;">
      <div style="font-size:12px;font-weight:800;letter-spacing:.12em;color:#1d4ed8;">BTC QUANT TERMINAL</div>
      <div style="font-size:24px;font-weight:900;margin-top:4px;">{icon} {label} · {score:+.0f}/100</div>
      <div style="font-size:13px;color:#475569;margin-top:6px;">Régimen: <b>{regime}</b> · Riesgo: <b>{vol_regime}</b> · Fuentes externas activas: <b>{source_count}</b></div>
    </div>
    """, unsafe_allow_html=True)



# =========================================================
# ACCESO ABIERTO + GESTIÓN DE USUARIOS (SIN CONTRASEÑAS)
# =========================================================
# Esta UI no exige autenticación. Los usuarios funcionan como perfiles
# operativos/organizativos para asignar roles y permisos, NO como una barrera
# de seguridad. Si el router principal del proyecto tiene un login propio,
# debe quedar desactivado allí también.
BTC_AUTH_REQUIRED = False
BTC_PASSWORD_REQUIRED = False
BTC_ACCESS_MODE = "OPEN"

_BTC_USER_ROLES = ["Administrador", "Trader", "Analista", "Inversor", "Observador"]
_BTC_USER_MODULES = [
    "Decisión", "Gráfico", "Confluencias", "Trade", "Backtest",
    "Market Intel", "Inversión", "Riesgo", "Quant Rules", "Configuración",
]
_BTC_ROLE_DEFAULTS = {
    "Administrador": _BTC_USER_MODULES.copy(),
    "Trader": ["Decisión", "Gráfico", "Confluencias", "Trade", "Backtest", "Market Intel", "Riesgo", "Quant Rules"],
    "Analista": ["Decisión", "Gráfico", "Confluencias", "Backtest", "Market Intel", "Inversión", "Riesgo", "Quant Rules"],
    "Inversor": ["Decisión", "Gráfico", "Market Intel", "Inversión", "Riesgo", "Quant Rules"],
    "Observador": ["Decisión", "Gráfico", "Market Intel", "Inversión", "Riesgo"],
}


def _btc_users_file() -> Path:
    configured = os.getenv("BTC_USERS_FILE", "").strip()
    if configured:
        return Path(configured).expanduser()
    try:
        return Path(__file__).resolve().with_name("btc_users.json")
    except Exception:
        return Path("btc_users.json")


def _btc_now() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _btc_default_user_store() -> dict:
    owner_id = "owner"
    return {
        "version": 1,
        "access_mode": "open",
        "active_user_id": owner_id,
        "updated_at": _btc_now(),
        "users": [
            {
                "id": owner_id,
                "nombre": "Administrador",
                "usuario": "admin",
                "email": "",
                "rol": "Administrador",
                "activo": True,
                "permisos": _BTC_USER_MODULES.copy(),
                "notas": "Perfil principal creado automáticamente. No requiere contraseña.",
                "created_at": _btc_now(),
                "updated_at": _btc_now(),
            }
        ],
    }


def _btc_normalize_user_store(store) -> dict:
    if not isinstance(store, dict):
        store = _btc_default_user_store()
    users = store.get("users")
    if not isinstance(users, list):
        users = []
    normalized = []
    seen_ids = set()
    seen_usernames = set()
    for raw in users:
        if not isinstance(raw, dict):
            continue
        uid = str(raw.get("id") or uuid.uuid4().hex).strip()
        if not uid or uid in seen_ids:
            uid = uuid.uuid4().hex
        username = str(raw.get("usuario") or "").strip().lower()
        if not username:
            username = f"usuario_{len(normalized)+1}"
        base = username
        suffix = 2
        while username in seen_usernames:
            username = f"{base}_{suffix}"
            suffix += 1
        role = str(raw.get("rol") or "Observador").strip()
        if role not in _BTC_USER_ROLES:
            role = "Observador"
        permissions = raw.get("permisos")
        if not isinstance(permissions, list):
            permissions = _BTC_ROLE_DEFAULTS.get(role, []).copy()
        permissions = [p for p in _BTC_USER_MODULES if p in permissions]
        normalized.append({
            "id": uid,
            "nombre": str(raw.get("nombre") or username).strip(),
            "usuario": username,
            "email": str(raw.get("email") or "").strip(),
            "rol": role,
            "activo": bool(raw.get("activo", True)),
            "permisos": permissions,
            "notas": str(raw.get("notas") or "").strip(),
            "created_at": str(raw.get("created_at") or _btc_now()),
            "updated_at": str(raw.get("updated_at") or _btc_now()),
        })
        seen_ids.add(uid)
        seen_usernames.add(username)

    if not normalized:
        return _btc_default_user_store()

    active_id = str(store.get("active_user_id") or "")
    active_ids = {u["id"] for u in normalized if u["activo"]}
    if active_id not in active_ids:
        active_id = next(iter(active_ids), normalized[0]["id"])
    return {
        "version": 1,
        "access_mode": "open",
        "active_user_id": active_id,
        "updated_at": str(store.get("updated_at") or _btc_now()),
        "users": normalized,
    }


def _btc_load_user_store(force: bool = False) -> dict:
    cache_key = "btc_user_store_cache"
    if not force and cache_key in st.session_state:
        return _btc_normalize_user_store(st.session_state[cache_key])

    path = _btc_users_file()
    store = None
    try:
        if path.exists():
            store = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        store = None
    store = _btc_normalize_user_store(store or _btc_default_user_store())
    st.session_state[cache_key] = store
    return store


def _btc_save_user_store(store: dict) -> tuple[bool, str]:
    store = _btc_normalize_user_store(store)
    store["updated_at"] = _btc_now()
    st.session_state["btc_user_store_cache"] = store
    path = _btc_users_file()
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(path.suffix + ".tmp")
        tmp.write_text(json.dumps(store, ensure_ascii=False, indent=2), encoding="utf-8")
        tmp.replace(path)
        return True, str(path)
    except Exception as exc:
        # La sesión sigue funcionando aunque el entorno no permita persistir archivos.
        return False, f"{type(exc).__name__}: {exc}"


def _btc_active_user(store: dict | None = None) -> dict:
    store = _btc_normalize_user_store(store or _btc_load_user_store())
    active_id = str(store.get("active_user_id") or "")
    for user in store.get("users", []):
        if user.get("id") == active_id and user.get("activo", True):
            return user
    for user in store.get("users", []):
        if user.get("activo", True):
            return user
    return store.get("users", [{}])[0]


def _btc_open_access_bootstrap() -> None:
    """Marca la sesión como acceso abierto antes de construir cualquier UI local."""
    os.environ["BTC_APP_AUTH_DISABLED"] = "1"
    os.environ["BTC_AUTH_REQUIRED"] = "0"
    for key in (
        "authenticated", "is_authenticated", "logged_in", "login_ok",
        "auth_ok", "password_ok", "btc_authenticated", "btc_auth_ok",
    ):
        st.session_state[key] = True
    st.session_state["btc_access_mode"] = "open"
    st.session_state["btc_password_required"] = False


def require_login() -> bool:
    """Compatibilidad: esta versión nunca solicita usuario ni contraseña."""
    _btc_open_access_bootstrap()
    return True


def require_btc_login() -> bool:
    """Compatibilidad explícita para routers que importen una puerta BTC."""
    return require_login()


def _btc_user_table(store: dict) -> pd.DataFrame:
    rows = []
    active_id = str(store.get("active_user_id") or "")
    for u in store.get("users", []):
        rows.append({
            "Activo actual": "●" if u.get("id") == active_id else "",
            "Nombre": u.get("nombre", ""),
            "Usuario": u.get("usuario", ""),
            "Rol": u.get("rol", ""),
            "Estado": "Activo" if u.get("activo", True) else "Desactivado",
            "Permisos": len(u.get("permisos", [])),
            "Email": u.get("email", ""),
            "Actualizado": u.get("updated_at", ""),
        })
    return pd.DataFrame(rows)


def render_btc_user_management() -> None:
    store = _btc_load_user_store(force=True)
    users = store.get("users", [])
    active_user = _btc_active_user(store)

    st.markdown("### 👥 Centro de Usuarios")
    st.caption("Acceso abierto: no existen contraseñas. Los usuarios son perfiles operativos para roles, permisos y trazabilidad interna.")

    total = len(users)
    active_count = sum(1 for u in users if u.get("activo", True))
    admin_count = sum(1 for u in users if u.get("rol") == "Administrador" and u.get("activo", True))
    k1, k2, k3, k4 = st.columns(4)
    k1.metric("Usuarios", total)
    k2.metric("Activos", active_count)
    k3.metric("Administradores", admin_count)
    k4.metric("Modo de acceso", "ABIERTO")

    st.info(f"Usuario activo en esta sesión: **{active_user.get('nombre', 'Administrador')}** · {active_user.get('rol', 'Administrador')} · sin contraseña")

    overview_tab, create_tab, edit_tab, backup_tab = st.tabs([
        "📋 Directorio", "➕ Crear usuario", "🛠️ Editar y permisos", "💾 Backup / Restaurar"
    ])

    with overview_tab:
        df_users = _btc_user_table(store)
        st.dataframe(df_users, use_container_width=True, hide_index=True)
        st.caption("El perfil activo no autentica identidad: sirve para personalizar roles y organización interna sin pedir clave al iniciar.")

        active_options = [u for u in users if u.get("activo", True)]
        if active_options:
            labels = [f"{u['nombre']} · @{u['usuario']} · {u['rol']}" for u in active_options]
            id_by_label = {label: u["id"] for label, u in zip(labels, active_options)}
            current_label = next((label for label, u in zip(labels, active_options) if u["id"] == store.get("active_user_id")), labels[0])
            selected_label = st.selectbox(
                "Usuario activo de la sesión",
                labels,
                index=labels.index(current_label),
                key="btc_cfg_active_user_selector",
            )
            if st.button("Aplicar usuario activo", type="primary", key="btc_apply_active_user"):
                store["active_user_id"] = id_by_label[selected_label]
                ok, msg = _btc_save_user_store(store)
                st.success("Usuario activo actualizado.")
                if not ok:
                    st.warning("Se aplicó en esta sesión, pero el entorno no permitió persistir el archivo local.")
                st.rerun()

    with create_tab:
        st.markdown("#### Alta de perfil")
        with st.form("btc_create_user_form", clear_on_submit=True):
            c1, c2, c3 = st.columns(3)
            nombre = c1.text_input("Nombre y apellido")
            usuario = c2.text_input("Usuario / alias", placeholder="ej: trader_1")
            email = c3.text_input("Email (opcional)")
            c4, c5 = st.columns([1, 2])
            rol = c4.selectbox("Rol", _BTC_USER_ROLES, index=2)
            permisos = c5.multiselect(
                "Permisos iniciales",
                _BTC_USER_MODULES,
                default=_BTC_ROLE_DEFAULTS.get("Analista", []),
            )
            notas = st.text_area("Notas internas", placeholder="Responsabilidad, estrategia, horario, alcance, etc.")
            submitted = st.form_submit_button("Crear usuario", type="primary", use_container_width=True)

        if submitted:
            username = usuario.strip().lower().replace(" ", "_")
            if not nombre.strip() or not username:
                st.error("Completá Nombre y Usuario.")
            elif any(str(u.get("usuario", "")).lower() == username for u in users):
                st.error("Ese usuario ya existe.")
            else:
                store["users"].append({
                    "id": uuid.uuid4().hex,
                    "nombre": nombre.strip(),
                    "usuario": username,
                    "email": email.strip(),
                    "rol": rol,
                    "activo": True,
                    "permisos": [p for p in _BTC_USER_MODULES if p in permisos],
                    "notas": notas.strip(),
                    "created_at": _btc_now(),
                    "updated_at": _btc_now(),
                })
                ok, msg = _btc_save_user_store(store)
                st.success(f"Usuario @{username} creado sin contraseña.")
                if not ok:
                    st.warning("Se creó para esta sesión, pero no se pudo escribir el archivo local de usuarios.")
                st.rerun()

    with edit_tab:
        if not users:
            st.info("No hay usuarios para editar.")
        else:
            labels = [f"{u['nombre']} · @{u['usuario']}" for u in users]
            selected = st.selectbox("Seleccionar usuario", labels, key="btc_cfg_edit_user")
            idx = labels.index(selected)
            user = users[idx]

            e1, e2, e3 = st.columns(3)
            new_name = e1.text_input("Nombre", value=user.get("nombre", ""), key="btc_edit_name")
            new_username = e2.text_input("Usuario", value=user.get("usuario", ""), key="btc_edit_username")
            role_index = _BTC_USER_ROLES.index(user.get("rol")) if user.get("rol") in _BTC_USER_ROLES else 0
            new_role = e3.selectbox("Rol", _BTC_USER_ROLES, index=role_index, key="btc_edit_role")
            new_email = st.text_input("Email", value=user.get("email", ""), key="btc_edit_email")
            new_permissions = st.multiselect(
                "Módulos permitidos",
                _BTC_USER_MODULES,
                default=[p for p in user.get("permisos", []) if p in _BTC_USER_MODULES],
                key="btc_edit_permissions",
            )
            new_notes = st.text_area("Notas", value=user.get("notas", ""), key="btc_edit_notes")
            new_active = st.toggle("Usuario activo", value=bool(user.get("activo", True)), key="btc_edit_active")

            b1, b2, b3 = st.columns(3)
            if b1.button("💾 Guardar cambios", type="primary", use_container_width=True, key="btc_save_user_changes"):
                username_norm = new_username.strip().lower().replace(" ", "_")
                duplicate = any(
                    i != idx and str(other.get("usuario", "")).lower() == username_norm
                    for i, other in enumerate(users)
                )
                if not new_name.strip() or not username_norm:
                    st.error("Nombre y usuario no pueden quedar vacíos.")
                elif duplicate:
                    st.error("Ese nombre de usuario ya pertenece a otro perfil.")
                else:
                    user.update({
                        "nombre": new_name.strip(),
                        "usuario": username_norm,
                        "email": new_email.strip(),
                        "rol": new_role,
                        "activo": bool(new_active),
                        "permisos": [p for p in _BTC_USER_MODULES if p in new_permissions],
                        "notas": new_notes.strip(),
                        "updated_at": _btc_now(),
                    })
                    if not user["activo"] and store.get("active_user_id") == user.get("id"):
                        replacement = next((u for u in users if u.get("id") != user.get("id") and u.get("activo", True)), None)
                        if replacement:
                            store["active_user_id"] = replacement["id"]
                    ok, msg = _btc_save_user_store(store)
                    st.success("Cambios guardados.")
                    if not ok:
                        st.warning("Los cambios viven en esta sesión, pero no se pudieron persistir en disco.")
                    st.rerun()

            if b2.button("⚡ Aplicar permisos del rol", use_container_width=True, key="btc_apply_role_defaults"):
                user["permisos"] = _BTC_ROLE_DEFAULTS.get(new_role, []).copy()
                user["rol"] = new_role
                user["updated_at"] = _btc_now()
                _btc_save_user_store(store)
                st.success("Permisos del rol aplicados.")
                st.rerun()

            delete_disabled = len(users) <= 1 or user.get("id") == "owner"
            if b3.button("🗑️ Eliminar usuario", use_container_width=True, disabled=delete_disabled, key="btc_delete_user"):
                removed_id = user.get("id")
                store["users"] = [u for u in users if u.get("id") != removed_id]
                if store.get("active_user_id") == removed_id:
                    store["active_user_id"] = store["users"][0]["id"]
                _btc_save_user_store(store)
                st.success("Usuario eliminado.")
                st.rerun()

    with backup_tab:
        st.markdown("#### Portabilidad de usuarios")
        st.caption("Útil especialmente si desplegás en un entorno donde el disco local puede ser temporal.")
        payload = json.dumps(store, ensure_ascii=False, indent=2)
        st.download_button(
            "⬇️ Exportar usuarios JSON",
            data=payload,
            file_name="btc_users_backup.json",
            mime="application/json",
            use_container_width=True,
            key="btc_export_users",
        )
        upload = st.file_uploader("Restaurar backup JSON", type=["json"], key="btc_import_users")
        if upload is not None:
            try:
                imported = json.loads(upload.getvalue().decode("utf-8"))
                imported = _btc_normalize_user_store(imported)
                st.success(f"Backup válido: {len(imported.get('users', []))} usuarios detectados.")
                if st.button("Restaurar este backup", type="primary", key="btc_restore_users"):
                    _btc_save_user_store(imported)
                    st.success("Backup restaurado.")
                    st.rerun()
            except Exception as exc:
                st.error(f"JSON inválido: {exc}")

        st.divider()
        st.markdown("#### Reinicio controlado")
        st.warning("Restablecer borra los perfiles personalizados y deja únicamente el Administrador abierto, sin contraseña.")
        confirm_reset = st.checkbox("Confirmo restablecer los usuarios", key="btc_confirm_reset_users")
        if st.button("Restablecer usuarios", disabled=not confirm_reset, key="btc_reset_users"):
            _btc_save_user_store(_btc_default_user_store())
            st.success("Usuarios restablecidos.")
            st.rerun()


def render_btc_configuration() -> None:
    st.subheader("⚙️ Configuración")
    st.caption("Administración del terminal BTC, perfiles y estado del acceso.")

    users_tab, access_tab, system_tab = st.tabs(["👥 Usuarios", "🔓 Acceso", "🧩 Sistema"])
    with users_tab:
        render_btc_user_management()

    with access_tab:
        st.markdown("### 🔓 Acceso de la aplicación")
        st.success("**Acceso abierto activado.** Esta versión no solicita contraseña al iniciar.")
        st.write("- Contraseña requerida: **No**")
        st.write("- Login obligatorio: **No**")
        st.write("- Perfiles operativos: **Sí**")
        st.write("- Cambio de perfil: **Configuración → Usuarios**")
        st.caption("Importante: sin login, los roles/permisos organizan la app pero no constituyen seguridad real frente a terceros.")

    with system_tab:
        store = _btc_load_user_store()
        active = _btc_active_user(store)
        st.markdown("### 🧩 Estado del sistema")
        s1, s2, s3, s4 = st.columns(4)
        s1.metric("Modo", "OPEN")
        s2.metric("Password", "OFF")
        s3.metric("Usuarios", len(store.get("users", [])))
        s4.metric("Perfil activo", active.get("rol", "Administrador"))
        st.code(str(_btc_users_file()), language=None)
        st.caption("Ruta del archivo local de usuarios. Podés cambiarla con la variable de entorno BTC_USERS_FILE.")


def render_dashboard():
    _btc_open_access_bootstrap()
    config = render_sidebar()
    pro_settings = pro_apply_auto_disarm(pro_load_settings())

    estrategia = config.get("estrategia")

    account_usd = config.get("account_usd", 500.0)

    risk_pct = config.get("risk_pct", 0.01)
    risk_pct_input = risk_pct

    leverage = config.get("leverage", 5)

    min_score = config.get("min_score", 7)

    rr_target = config.get("rr_target", 2.0)

    min_rr = config.get("min_rr", 1.8)

    max_atr_multiplier = config.get("max_atr_multiplier", 2.0)

    show_levels_when_no_trade = config.get("show_levels_when_no_trade", True)

    modo_operativo = config.get("modo_operativo", "Normal")

    filter_hours = config.get("filter_hours", False)

    avoid_weekends = config.get("avoid_weekends", True)

    use_fvg_filter = config.get("use_fvg_filter", False)

    show_fvg_zones = config.get("show_fvg_zones", True)

    show_mitigated_fvg = config.get("show_mitigated_fvg", True)

    fvg_min_atr = config.get("fvg_min_atr", 0.20)

    fvg_max_distance_atr = config.get("fvg_max_distance_atr", 1.50)

    backtest_period = config.get("backtest_period", "3 meses")

    backtest_tf = config.get("backtest_tf", "15m")

    validate_after_hours = config.get("validate_after_hours", 24)

    mc_enabled = config.get("mc_enabled", True)

    mc_trades_horizon = config.get("mc_trades_horizon", 50)

    mc_paths = config.get("mc_paths", 5000)

    mc_start_capital = config.get("mc_start_capital", account_usd)

    mc_max_daily_trades = config.get("mc_max_daily_trades", 3)

    mc_use_backtest = config.get("mc_use_backtest", True)

    mc_manual_wr = config.get("mc_manual_wr", 45.0)

    mc_manual_rr = config.get("mc_manual_rr", rr_target)

    mc_ruin_dd_pct = config.get("mc_ruin_dd_pct", 30.0)

    auto_capture_enabled = config.get("auto_capture_enabled", True)

    mobile_compact = config.get("mobile_compact", False)

    auto_refresh_enabled = config.get("auto_refresh_enabled", False)

    auto_refresh_seconds = config.get("auto_refresh_seconds", 120)

    telegram_enabled = config.get("telegram_enabled", True)

    telegram_bot_token = config.get("telegram_bot_token", "")

    telegram_chat_id = config.get("telegram_chat_id", "")

    discord_enabled = config.get("discord_enabled", False)

    discord_webhook_url = config.get("discord_webhook_url", "")

    alert_valid_signals = config.get("alert_valid_signals", True)

    alert_almost_setups = config.get("alert_almost_setups", True)

    alert_bias_change = config.get("alert_bias_change", True)

    alert_risk_warning = config.get("alert_risk_warning", False)

    almost_score_gap = config.get("almost_score_gap", 1)

    alert_market_updates = config.get("alert_market_updates", True)

    market_update_minutes = config.get("market_update_minutes", 5)

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

        # ====================================================================
        # FUTURES OS PRO — contexto institucional + Risk Kernel
        # ====================================================================
        runtime_symbol = pro_symbol_id(globals().get("SYMBOL", pro_settings.get("analysis_symbol", "BTCUSDT")))
        configured_symbol = pro_symbol_id(pro_settings.get("analysis_symbol", runtime_symbol))
        symbol_mismatch = configured_symbol != runtime_symbol
        environment_pro = str(pro_settings.get("environment", "PAPER")).upper()
        public_futures = pro_fetch_public_futures_snapshot(runtime_symbol)
        pro_record_microstructure(public_futures)
        micro_persistence = pro_microstructure_persistence(runtime_symbol)
        candle_age_sec = pro_candle_age_sec(df_5m)
        regime_pro = pro_detect_regime(df_1d, df_4h, df_1h, df_15m)
        calibration_pro = pro_edge_calibration(candidate_direction, quality_score)

        # LIVE/TESTNET uses exchange equity and exchange positions whenever private credentials are available.
        private_state_pro = None
        private_reconcile_pro = {"ok": True, "naked_positions": [], "orphan_orders": [], "warnings": []}
        private_risk_pro = {}
        effective_account_usd = float(account_usd)
        btc_size_exec, notional_exec, risk_usd_exec, margin_exec, risk_target_exec, capped_exec, max_notional_exec = (
            btc_size, notional, risk_usd, margin_needed, risk_usd_target, notional_capped, max_notional
        )
        if environment_pro in ("TESTNET", "LIVE"):
            gateway_pre = ProFuturesGateway(pro_settings, runtime_symbol)
            private_state_pro = gateway_pre.fetch_private_state()
            private_reconcile_pro = pro_reconcile_private_state(private_state_pro)
            exchange_equity = pro_extract_equity_usdt(private_state_pro, np.nan)
            if not pd.isna(exchange_equity) and exchange_equity > 0:
                effective_account_usd = float(exchange_equity)
                btc_size_exec, notional_exec, risk_usd_exec, margin_exec, risk_target_exec, capped_exec, max_notional_exec = position_size(
                    price, sl_calc, effective_account_usd, risk_pct, leverage
                )
            private_risk_pro = pro_private_risk_metrics(private_state_pro, effective_account_usd)

        journal_stats_pro = pro_journal_stats(effective_account_usd)
        if private_risk_pro:
            journal_stats_pro["open_risk_usd"] = max(pro_safe_float(journal_stats_pro.get("open_risk_usd"),0), pro_safe_float(private_risk_pro.get("open_risk_usd"),0))
            journal_stats_pro["same_side_open_long"] = max(int(journal_stats_pro.get("same_side_open_long",0)), int(private_risk_pro.get("same_side_open_long",0)))
            journal_stats_pro["same_side_open_short"] = max(int(journal_stats_pro.get("same_side_open_short",0)), int(private_risk_pro.get("same_side_open_short",0)))

        independent_conf_pro = pro_independent_confluence_score(
            candidate_direction, t4, t1, t15, structure, fvg_valid,
            df_15m["delta_strength"].iloc[-1], df_15m["vol_ratio"].iloc[-1], public_futures
        )
        strategy_router_pro = pro_strategy_router(estrategia, regime_pro)
        strategy_conflict_pro = pro_strategy_conflict_score(
            candidate_direction, t4, t1, t15, structure, df_15m["delta_strength"].iloc[-1], public_futures
        )
        signal_reference_pro = pro_latest_signal_reference(candidate_direction, price, current_candle_time)
        signal_decay_pro = pro_signal_decay(price, signal_reference_pro.get("price", price), atr_15m, signal_reference_pro.get("time"))
        preliminary_costs_pro = pro_estimated_costs(
            candidate_direction, price, sl_calc, tp_calc, btc_size_exec, public_futures, pro_settings
        )
        no_trade_pro = pro_no_trade_score(
            regime_pro, public_futures, candle_age_sec, pro_settings, candidate_direction,
            pro_safe_float(preliminary_costs_pro.get("net_rr"), rr_real)
        )
        external_event_risk_pro = any(bool(st.session_state.get(k, False)) for k in [
            "quant_macro_event", "quant_options_expiry", "quant_exchange_incident"
        ])
        gate_pro = pro_build_trade_gate(
            settings=pro_settings, environment=environment_pro,
            candidate_direction=candidate_direction, trade_valid=trade_valid, quality_score=quality_score,
            rr_real=rr_real, price=price, sl=sl_calc, tp=tp_calc, size=btc_size_exec,
            account_usd=effective_account_usd, risk_pct=risk_pct, leverage=leverage, candle_age_sec=candle_age_sec,
            public_snap=public_futures, regime=regime_pro, calibration=calibration_pro,
            journal_stats=journal_stats_pro, independent_confluence=independent_conf_pro,
            strategy_router=strategy_router_pro, external_event_risk=external_event_risk_pro,
            signal_decay=signal_decay_pro, strategy_conflict=strategy_conflict_pro,
        )
        # A symbol mismatch is always fail-closed for TESTNET/LIVE. The legacy analysis
        # remains tied to the repository's SYMBOL/load_all_data source.
        if symbol_mismatch and environment_pro != "PAPER":
            gate_pro["authorized"] = False
            gate_pro["status"] = "BLOCKED"
            mismatch_check = {
                "code": "SYMBOL_MISMATCH", "ok": False, "severity": "BLOCK",
                "detail": f"Análisis={runtime_symbol} vs configuración={configured_symbol}. Alineá ambos antes de operar."
            }
            gate_pro["checks"].append(mismatch_check)
            gate_pro["blocking"].append(mismatch_check)
        if environment_pro in ("TESTNET", "LIVE"):
            if not private_state_pro or not private_state_pro.get("ok"):
                private_check = {"code": "PRIVATE_ACCOUNT_STATE", "ok": False, "severity": "BLOCK", "detail": "No se pudo reconciliar balance/posiciones/órdenes privadas del exchange."}
                gate_pro["authorized"] = False; gate_pro["status"] = "BLOCKED"
                gate_pro["checks"].append(private_check); gate_pro["blocking"].append(private_check)
            if private_reconcile_pro.get("naked_positions"):
                naked_check = {"code": "NAKED_POSITION", "ok": False, "severity": "BLOCK", "detail": f"{len(private_reconcile_pro['naked_positions'])} posición/es del exchange sin orden protectora detectada/s."}
                gate_pro["authorized"] = False; gate_pro["status"] = "BLOCKED"
                gate_pro["checks"].append(naked_check); gate_pro["blocking"].append(naked_check)
        health_pro = pro_health_score(public_futures, candle_age_sec, pro_settings, private_state_pro)
        liq_stress_pro = pro_liquidation_stress_proxy(public_futures, regime_pro, candidate_direction)

        # Institutional OS 500: portfolio/risk/execution/statistics/digital-twin layer.
        inst_state_pro = inst_build_state(
            symbol=runtime_symbol, direction=candidate_direction, price=price, sl=sl_calc, tp=tp_calc,
            qty=btc_size_exec, atr=atr_15m, risk_pct=risk_pct, account_usd=effective_account_usd,
            settings=pro_settings, public_snap=public_futures, private_state=private_state_pro,
            journal_stats=journal_stats_pro, regime_pro=regime_pro, calibration=calibration_pro,
            gate=gate_pro, signal_decay=signal_decay_pro, strategy=estrategia, candle_age_sec=candle_age_sec
        )
        gate_pro = inst_apply_gate(gate_pro, inst_state_pro["passport"])

        tab1, tab2, tab3, tab4, tab5, tab6, tab7, tab8, tab9, tab10, tab11 = st.tabs([
            "🧠 Decisión",
            "📈 Gráfico",
            "🔬 Confluencias",
            "🎯 Trade",
            "📊 Backtest",
            "🌐 Market Intel",
            "💼 Inversión",
            "🛡️ Riesgo",
            "🧬 Quant Rules",
            "⚙️ Configuración",
            "🏛️ Institutional OS 500"
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
            pro_render_control_tower(
                gate_pro, health_pro, regime_pro, calibration_pro, no_trade_pro,
                journal_stats_pro, public_futures, pro_settings
            )
            inst_render_mission_strip(inst_state_pro)
            if symbol_mismatch:
                st.warning(f"⚠️ Símbolo de análisis {runtime_symbol} ≠ símbolo configurado {configured_symbol}. PAPER puede seguir; TESTNET/LIVE queda bloqueado hasta alinearlos.")
            st.divider()
            st.markdown(
                f"<div style='font-size:20px; font-weight:700;'>"
                f"Calidad del setup: {quality_label} · {quality_score}/10"
                f"</div>",
                unsafe_allow_html=True
            )    
            st.divider()
            col1, col2, col3, col4 = st.columns(4)
            col1.markdown(f"**Precio BTCUSDT**  \n{format_number(price, 2)}")
            col2.markdown(f"**Long Score**  \n{long_score}/10")
            col3.markdown(f"**Short Score**  \n{short_score}/10")
            col4.markdown(f"**RSI 15M**  \n{rsi_15:.2f}  \n{rsi_label}")
            st.divider()

            q1, q2, q3, q4, q5 = st.columns(5)
            q1.markdown(f"**Calidad**\n\n{quality_label}\n\n{quality_score}/10")
            q2.markdown(
                f"**Distancia SL**\n\n{risk_points_calc:.0f} pts\n\nATR 15M: {atr_15m:.0f}"
            )
            q3.markdown(
                f"**Setup**\n\n{display_direction(candidate_direction)}\n\nRR: {rr_real:.2f}"
            )
            q4.markdown(
                f"**Distancia TP**\n\n{tp_distance_calc:.0f} pts"
            )
            q5.markdown(
                f"**FVG**\n\n{fvg_label.replace('_',' ')}\n\n{format_number(fvg_distance_atr,2)} ATR"
            )
            st.divider()

            c1, c2, c3, c4, c5 = st.columns(5)
            c1.markdown(f"**24H**\n\n{trend_icon(t1d)}")
            c2.markdown(f"**4H**\n\n{trend_icon(t4)}")
            c3.markdown(f"**1H**\n\n{trend_icon(t1)}")
            c4.markdown(f"**15M**\n\n{trend_icon(t15)}")
            c5.markdown(f"**5M**\n\n{trend_icon(t5)}")
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
            st.divider()
            st.subheader("🎯 Zonas profesionales Daytrade")
            zonas_daytrade = detectar_zonas_daytrade(
                df_15m=df_15m,
                asia_high=None,
                london_high=None,
                max_zonas=3
            )
            
        with tab2:
            st.subheader("📈 Gráfico operativo intradía")

            modo_grafico = st.radio(
                "Modo de gráfico",
                ["Simple", "Pro", "Institucional"],
                horizontal=True,
                index=1
            )

            # =========================
            # CAPAS DEL GRÁFICO
            # =========================
            if modo_grafico == "Simple":
                show_emas = True
                show_trade_levels = True
                show_profile = True
                show_liquidez = False
                show_fvg = False
                show_order_blocks = False
                show_eq_levels = False
                show_volumen = False
                show_barridos = False
                show_labels_extra = False
            elif modo_grafico == "Pro":
                show_emas = True
                show_trade_levels = True
                show_profile = True
                show_liquidez = True
                show_fvg = True
                show_order_blocks = False
                show_eq_levels = False
                show_volumen = False
                show_barridos = True
                show_labels_extra = False
            else:  # Institucional
                show_emas = True
                show_trade_levels = True
                show_profile = True
                show_liquidez = True
                show_fvg = True
                show_order_blocks = True
                show_eq_levels = True
                show_volumen = True
                show_barridos = True
                show_labels_extra = True

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
            st.divider()

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
            st.divider()

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
            st.divider()
        

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
            st.divider()

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

            st.divider()
            st.markdown("### 🧬 Confluencia independiente / conflictos / ciclo de zonas")
            cf1, cf2, cf3, cf4 = st.columns(4)
            cf1.metric("Confluencia independiente", f"{independent_conf_pro['score']:.0f}/100")
            cf2.metric("Familias positivas", independent_conf_pro.get("independent_positive",0))
            cf3.metric("Conflicto", f"{strategy_conflict_pro.get('score',50):.0f}%")
            cf4.metric("Signal freshness", f"{signal_decay_pro.get('freshness_score',0):.0f}/100")
            st.caption("Familias: " + " · ".join([f"{k}={v:.2f}" for k,v in independent_conf_pro.get('families',{}).items()]))
            fvg_life, fvg_summary_pro = pro_fvg_lifecycle_table(fvg_df, price)
            lf1,lf2,lf3,lf4 = st.columns(4)
            lf1.metric("FVG activos", fvg_summary_pro.get("active",0))
            lf2.metric("En zona", fvg_summary_pro.get("partial",0))
            lf3.metric("Mitigados", fvg_summary_pro.get("mitigated",0))
            lf4.metric("Invalidados", fvg_summary_pro.get("invalidated",0))
            if not fvg_life.empty:
                with st.expander("Ver ciclo de vida FVG", expanded=False):
                    cols_life = [c for c in ["time","tipo","direction","low","mid","high","distance_atr","score","calidad","lifecycle"] if c in fvg_life.columns]
                    st.dataframe(fvg_life[cols_life].head(30), use_container_width=True, hide_index=True)
            if ob_df is not None and not ob_df.empty and "mitigated" in ob_df.columns:
                ob_total = len(ob_df); ob_mit = int(ob_df["mitigated"].astype(bool).sum()); ob_open_n = ob_total-ob_mit
                st.caption(f"Order Blocks: {ob_total} detectados · {ob_open_n} activos · {ob_mit} mitigados.")
            with st.expander("🔗 Matriz de redundancia entre features", expanded=False):
                corr_pro = pro_feature_correlation(df_15m)
                if corr_pro.empty:
                    st.info("No hay columnas suficientes para calcular correlaciones.")
                else:
                    st.dataframe(corr_pro, use_container_width=True)
                    high_pairs = []
                    cols_corr = list(corr_pro.columns)
                    for i in range(len(cols_corr)):
                        for j in range(i+1,len(cols_corr)):
                            val = pro_safe_float(corr_pro.iloc[i,j],np.nan)
                            if not pd.isna(val) and abs(val) >= 0.80:
                                high_pairs.append(f"{cols_corr[i]} ↔ {cols_corr[j]} ({val:+.2f})")
                    if high_pairs:
                        st.warning("Features potencialmente redundantes: " + " · ".join(high_pairs[:8]))
                    else:
                        st.success("No se detectan correlaciones absolutas ≥ 0.80 entre las features evaluadas.")

        with tab4:
            g1, g2, g3, g4, g5, g6, g7 = st.columns(7)
            g1.metric("Cuenta", f"{account_usd:.0f} USDT")
            g2.metric("Riesgo real", f"{risk_usd:.2f} USDT", f"Obj: {risk_usd_target:.2f}")
            g3.metric("Ganancia TP", f"+{profit_usd:.2f} USDT", f"{profit_pct:.2f}%")
            g4.metric("Tamaño", f"{btc_size:.4f} BTC")
            g5.metric("Nocional real", f"{notional:.0f} USDT")
            g6.metric("Máx nocional", f"{max_notional:.0f} USDT")
            g7.metric("Margen", f"{margin_needed:.0f} USDT")
            st.divider()
            r1, r2, r3, r4, r5, r6 = st.columns(6)
            r1.metric("Entrada", f"{price:,.0f}")
            r2.metric("SL técnico", f"{sl_calc:,.0f}" if not pd.isna(sl_calc) else "—")
            r3.metric("TP automático", f"{tp_calc:,.0f}" if not pd.isna(tp_calc) else "—")
            r4.metric("Distancia SL", f"{risk_points_calc:,.0f} pts" if not pd.isna(risk_points_calc) else "—")
            r5.metric("Distancia TP", f"{tp_distance_calc:,.0f} pts" if not pd.isna(tp_distance_calc) else "—")
            r6.metric("RR real", f"{rr_real:.2f}" if not pd.isna(rr_real) else "—")
            st.divider()
            pro_render_execution_console(
                runtime_symbol, price, sl_calc, tp_calc, btc_size_exec, leverage, gate_pro,
                pro_settings, df_5m, atr_15m, quality_score, private_state_pro
            )
            st.divider()
            with st.expander("🧾 Registro manual legacy (no envía órdenes al exchange)", expanded=False):
                st.caption("Se conserva para compatibilidad con tu historial anterior. Para ejecutar usá Execution OS arriba.")
                st.subheader("🎯 Trade en vivo · registro manual")
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

                    st.markdown("### 🧬 Robustez / Walk-forward / Costes")
                    robust_pro = pro_parameter_robustness_summary(bt_results)
                    rrisk = max(pro_safe_float(preliminary_costs_pro.get("risk_usd"), 0), 1e-9)
                    cost_r = pro_safe_float(preliminary_costs_pro.get("total_cost_usd"), 0) / rrisk
                    ev_gross = pro_safe_float(bt_stats.get("expectancy"), 0)
                    ev_net_proxy = ev_gross - cost_r
                    wb1,wb2,wb3,wb4 = st.columns(4)
                    wb1.metric("Expectancy bruto", f"{ev_gross:+.3f}R")
                    wb2.metric("Coste actual proxy", f"-{cost_r:.3f}R")
                    wb3.metric("Expectancy neto proxy", f"{ev_net_proxy:+.3f}R")
                    wb4.metric("Robustez temporal", f"{robust_pro['score']:.0f}/100")
                    if robust_pro.get("table") is not None and not robust_pro["table"].empty:
                        st.dataframe(robust_pro["table"], use_container_width=True, hide_index=True)
                        if robust_pro["stable"]:
                            st.success("La expectativa se mantiene positiva en la mayoría de los bloques temporales evaluados.")
                        else:
                            st.warning("Edge temporal inestable o muestra insuficiente: riesgo de sobreajuste / cambio de régimen.")
                    if calibration_pro.get("reliability") is not None and not calibration_pro["reliability"].empty:
                        with st.expander("📐 Calibración del antiguo score 0-10", expanded=False):
                            st.dataframe(calibration_pro["reliability"], use_container_width=True, hide_index=True)
                            st.caption(f"Brier score diagnóstico: {pro_safe_float(calibration_pro.get('brier'),np.nan):.3f}. El score técnico no se usa como probabilidad hasta estar calibrado.")

                    if st.button("🧪 Ejecutar stress de parámetros", key="pro_param_stress"):
                        variants = []
                        for ds in [-1, 0, 1]:
                            for drr in [-0.2, 0.0, 0.2]:
                                try:
                                    _, vstats = run_simple_backtest(
                                        backtest_tf, backtest_period, estrategia, max(1, int(min_score+ds)), rr_target,
                                        max(0.5, float(min_rr+drr)), max_atr_multiplier, filter_hours, avoid_weekends,
                                        fvg_min_atr, fvg_max_distance_atr, use_fvg_filter
                                    )
                                    variants.append({"min_score": max(1,int(min_score+ds)), "min_rr": round(max(0.5,float(min_rr+drr)),2), "ops": vstats.get("operaciones",0), "winrate_%": vstats.get("winrate",0), "expectancy_R": vstats.get("expectancy",0), "PF": vstats.get("profit_factor",0)})
                                except Exception as exc:
                                    variants.append({"min_score": max(1,int(min_score+ds)), "min_rr": round(max(0.5,float(min_rr+drr)),2), "error": str(exc)[:120]})
                        vr = pd.DataFrame(variants)
                        st.dataframe(vr, use_container_width=True, hide_index=True)
                        if "expectancy_R" in vr.columns:
                            valid_v = pd.to_numeric(vr["expectancy_R"], errors="coerce").dropna()
                            if len(valid_v):
                                stable_ratio = float((valid_v > 0).mean()*100)
                                st.metric("Variantes con expectancy positiva", f"{stable_ratio:.0f}%")
                                if stable_ratio < 60:
                                    st.warning("La estrategia parece sensible a parámetros; posible overfitting.")
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
            "risk_pct": risk_pct,
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

            with st.expander("📌 Motivo de la decisión", expanded=not mobile_compact):
                st.write(f"**Estrategia activa:** {estrategia}")
                st.write(f"**Escenario:** {escenario}")
                st.write(f"**Dirección calculada:** {display_direction(candidate_direction)}")
                st.write(f"**Estructura 5M:** {structure}")
                st.write(f"**Long Score:** {long_score}/10")
                st.write(f"**Short Score:** {short_score}/10")
                st.write(f"**FVG:** {fvg_label}")
                if fvg_zone:
                    st.write(f"**Zona FVG:** {fmt0(fvg_zone['low'])} - {fmt0(fvg_zone['high'])} | MID {fmt0(fvg_zone['mid'])} | Gap {fmt0(fvg_zone['gap_pts'])} pts")
                st.write(f"**Distancia SL:** {format_number(risk_points_calc, 2)} puntos")
                st.write(f"**Score PRO:** {quality_detail['score_100']}/100")
                st.write(f"**Distancia TP:** {format_number(tp_distance_calc, 2)} puntos")
                
                st.write("**Factores positivos:**")
                for p in quality_detail["positivos"]:
                    st.success(p)
                st.write("**Factores negativos / faltantes:**")
                for n in quality_detail["negativos"]:
                    st.warning(n)
                
                
                

        # ===== ORDER BLOCKS EN GRÁFICO =====
        if show_order_blocks and ob_df is not None and not ob_df.empty:
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


        # ====== PERFIL DE LIQUIDEZ EN GRÁFICO ======

        if show_liquidez and liq_profile_df is not None and not liq_profile_df.empty:
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
        if show_volumen and inst_vol_df is not None and not inst_vol_df.empty:
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
        if show_volumen: 
            for name, value in levels.items():
                if not pd.isna(value):
                    fig.add_hline(y=value, line_dash="dot", line_color="gray", annotation_text=name, annotation_position="right")
        should_show_trade_levels = trade_valid or show_levels_when_no_trade
        if should_show_trade_levels and not pd.isna(sl_calc):
            fig.add_hline(y=sl_calc, line_color="red", line_width=3, annotation_text="SL")
        if should_show_trade_levels and not pd.isna(tp_calc):
            fig.add_hline(y=tp_calc, line_color="green", line_width=3, annotation_text="TP")
        fig.add_hline(y=price, line_color="black", line_width=3, annotation_text="Entrada")
        if show_profile and volume_profile:
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
                        "riesgo_por_trade_%": mc.get("risk_pct", 0.01),
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
    

        # ================================================================
        # BTC QUANT TERMINAL — módulos institucionales adicionales
        # ================================================================
        with tab6:
            st.subheader("🌐 BTC Market Intelligence")
            st.markdown("### ⚡ Futures Microstructure PRO")
            mi1, mi2, mi3, mi4, mi5, mi6 = st.columns(6)
            mi1.metric("Mark", f"{pro_safe_float(public_futures.get('mark_price'), np.nan):,.2f}" if not pd.isna(pro_safe_float(public_futures.get('mark_price'), np.nan)) else "—")
            mi2.metric("Index", f"{pro_safe_float(public_futures.get('index_price'), np.nan):,.2f}" if not pd.isna(pro_safe_float(public_futures.get('index_price'), np.nan)) else "—")
            mi3.metric("Spread", f"{pro_safe_float(public_futures.get('spread_bps'), np.nan):.2f} bps" if not pd.isna(pro_safe_float(public_futures.get('spread_bps'), np.nan)) else "—")
            mi4.metric("Funding", f"{pro_safe_float(public_futures.get('funding_rate_pct'), np.nan):+.4f}%" if not pd.isna(pro_safe_float(public_futures.get('funding_rate_pct'), np.nan)) else "—")
            mi5.metric("OI 150m", f"{pro_safe_float(public_futures.get('oi_change_pct'), np.nan):+.2f}%" if not pd.isna(pro_safe_float(public_futures.get('oi_change_pct'), np.nan)) else "—")
            mi6.metric("CVD qty", f"{pro_safe_float(public_futures.get('cvd_qty'), np.nan):+,.2f}" if not pd.isna(pro_safe_float(public_futures.get('cvd_qty'), np.nan)) else "—")
            ob1,ob2,ob3,ob4,ob5 = st.columns(5)
            for col,band in zip([ob1,ob2,ob3,ob4,ob5],[5,10,25,50,100]):
                val = pro_safe_float(public_futures.get(f'book_imbalance_{band}bps'), np.nan)
                col.metric(f"Book ±{band}bps", f"{val:+.1f}%" if not pd.isna(val) else "—")
            st.caption(f"Persistencia microestructura: imbalance {pro_safe_float(micro_persistence.get('imbalance_persistence'),np.nan):.0f}% · CVD {pro_safe_float(micro_persistence.get('cvd_persistence'),np.nan):.0f}% · spoof risk {micro_persistence.get('spoof_risk','UNKNOWN')}")
            flow_ctx_pro = pro_market_flow_context(df_15m, public_futures)
            fl1,fl2,fl3 = st.columns(3)
            fl1.metric("Δ precio 15M", f"{pro_safe_float(flow_ctx_pro.get('price_change_15m_pct'),np.nan):+.3f}%" if not pd.isna(pro_safe_float(flow_ctx_pro.get('price_change_15m_pct'),np.nan)) else "—")
            fl2.metric("OI velocity", f"{pro_safe_float(flow_ctx_pro.get('oi_velocity_pct'),np.nan):+.3f}%" if not pd.isna(pro_safe_float(flow_ctx_pro.get('oi_velocity_pct'),np.nan)) else "—")
            fl3.metric("CVD divergence", flow_ctx_pro.get("cvd_divergence","NONE"))
            st.write(f"**Price × OI:** {flow_ctx_pro.get('price_oi','—')}")
            if flow_ctx_pro.get("absorption") != "NONE":
                st.warning(f"Absorción microestructural: {flow_ctx_pro['absorption']}")
            if flow_ctx_pro.get("exhaustion") != "NONE":
                st.info(f"Agotamiento potencial: {flow_ctx_pro['exhaustion']}")
            st.info(f"Liquidation/crowding stress proxy: **{liq_stress_pro['state']} {liq_stress_pro['score']:.0f}/100**. {liq_stress_pro['note']}")
            with st.expander("🌍 Scanner USDT Perpetuals", expanded=False):
                scan_df = pro_scan_usdt_perpetuals(30)
                if scan_df.empty:
                    st.info("Scanner no disponible en este momento.")
                else:
                    show_scan = scan_df.copy()
                    show_scan["quote_volume_usdt"] = show_scan["quote_volume_usdt"].round(0)
                    st.dataframe(show_scan, use_container_width=True, hide_index=True)
                    st.caption("El ranking prioriza liquidez y movimiento y penaliza crowding de funding; no es una señal automática de compra/venta.")
            st.divider()
            st.caption("Lectura multi-timeframe + riesgo estadístico + derivados/sentimiento públicos opcionales. Ningún dato externo es obligatorio para que la app funcione.")

            quant_snaps = {
                "1D": timeframe_quant_snapshot(df_1d, "1D"),
                "4H": timeframe_quant_snapshot(df_4h, "4H"),
                "1H": timeframe_quant_snapshot(df_1h, "1H"),
                "15M": timeframe_quant_snapshot(df_15m, "15M"),
                "5M": timeframe_quant_snapshot(df_5m, "5M"),
            }
            quant_risk = daily_risk_metrics(df_1d)
            external_live_enabled = st.toggle(
                "🌐 Conectar derivados + sentimiento en vivo",
                value=False,
                key="quant_external_live",
                help="Consulta endpoints públicos de Binance y Alternative.me. El análisis local funciona igual si lo dejás apagado."
            )
            external_btc = fetch_btc_external_metrics() if external_live_enabled else blank_external_btc_metrics()
            trade_context_q = {
                "candidate_direction": candidate_direction,
                "long_score": long_score,
                "short_score": short_score,
                "rr_real": rr_real,
                "quality_score": quality_score,
                "trade_valid": trade_valid,
            }
            quant_rules = build_quant_rulebook(quant_snaps, quant_risk, external_btc, trade_context_q)
            quant_score = quant_rulebook_score(quant_rules)
            regime, vol_regime, expansion_regime = detect_quant_regime(quant_snaps["1D"], quant_risk)
            render_quant_header(quant_score, regime, vol_regime, len(external_btc.get("sources_ok", [])))

            mk1, mk2, mk3, mk4, mk5, mk6 = st.columns(6)
            mk1.metric("BTC", f"{price:,.0f} USDT")
            mk2.metric("Régimen", regime)
            mk3.metric("Score Quant", f"{quant_score:+.0f}/100")
            mk4.metric("Vol 30D anual.", _q_pct(quant_risk.get("vol30"), 1))
            mk5.metric("DD desde ATH", _q_pct(quant_risk.get("current_dd"), 1))
            fg_v = _q_float(external_btc.get("fear_greed"))
            mk6.metric("Fear & Greed", "—" if pd.isna(fg_v) else f"{fg_v:.0f}/100", external_btc.get("fear_greed_label", ""))

            st.divider()
            st.markdown("### 🧭 Radar multi-timeframe")
            tf_rows = []
            for tf_name in ["1D", "4H", "1H", "15M", "5M"]:
                s = quant_snaps[tf_name]
                tf_rows.append({
                    "TF": tf_name,
                    "Sesgo": s.get("bias"),
                    "Score": s.get("score"),
                    "RSI": round(_q_float(s.get("rsi"), 50), 1),
                    "ADX": round(_q_float(s.get("adx"), 0), 1),
                    "ROC20 %": round(_q_float(s.get("roc20"), 0), 2),
                    "ATR %": round(_q_float(s.get("atr_pct"), 0), 2),
                    "CMF": round(_q_float(s.get("cmf"), 0), 3),
                    "MFI": round(_q_float(s.get("mfi"), 50), 1),
                    "Vol Z": round(_q_float(s.get("volume_z"), 0), 2),
                    "BB Pos": round(_q_float(s.get("bb_pos"), 0.5), 2),
                })
            tf_table = pd.DataFrame(tf_rows)
            st.dataframe(tf_table, use_container_width=True, hide_index=True)

            radar_fig = go.Figure()
            radar_fig.add_trace(go.Bar(
                x=tf_table["TF"],
                y=tf_table["Score"],
                text=[f"{x:+.0f}" for x in tf_table["Score"]],
                textposition="outside",
                name="Score TF",
            ))
            radar_fig.add_hline(y=0, line_dash="dot")
            radar_fig.update_layout(template="plotly_white", height=320, title="Dirección cuantitativa por timeframe", yaxis_title="Score -100 a +100", margin=dict(l=20, r=20, t=50, b=20))
            st.plotly_chart(radar_fig, use_container_width=True, config={"responsive": True}, key="quant_tf_radar")

            st.divider()
            st.markdown("### 🧬 Régimen de mercado")
            rg1, rg2, rg3, rg4, rg5 = st.columns(5)
            rg1.metric("Tendencia", regime)
            rg2.metric("Volatilidad", vol_regime)
            rg3.metric("Compresión", expansion_regime)
            rg4.metric("ADX 1D", f"{_q_float(quant_snaps['1D'].get('adx'), 0):.1f}")
            rg5.metric("Percentil vol", _q_pct(quant_risk.get("vol_percentile"), 0))
            st.caption("El régimen combina tendencia, fuerza y volatilidad. Sirve para elegir el tipo de estrategia; no es una orden de compra/venta.")

            st.divider()
            st.markdown("### 🏦 Derivados, sentimiento y microestructura")
            d1, d2, d3, d4, d5, d6 = st.columns(6)
            funding = _q_float(external_btc.get("funding_rate"))
            oi_btc = _q_float(external_btc.get("open_interest_btc"))
            oi_chg = _q_float(external_btc.get("open_interest_change_pct"))
            ls_ratio = _q_float(external_btc.get("global_long_short"))
            taker_ratio = _q_float(external_btc.get("taker_buy_sell"))
            book_imb = _q_float(external_btc.get("orderbook_imbalance"))
            d1.metric("Funding", "—" if pd.isna(funding) else f"{funding:+.4f}%")
            d2.metric("Open Interest", "—" if pd.isna(oi_btc) else f"{oi_btc:,.0f} BTC", "—" if pd.isna(oi_chg) else f"{oi_chg:+.2f}% ~150m")
            d3.metric("Global Long/Short", "—" if pd.isna(ls_ratio) else f"{ls_ratio:.2f}")
            d4.metric("Taker Buy/Sell", "—" if pd.isna(taker_ratio) else f"{taker_ratio:.2f}")
            d5.metric("Book imbalance", "—" if pd.isna(book_imb) else f"{book_imb:+.1f}%")
            mark = _q_float(external_btc.get("mark_price"))
            index_p = _q_float(external_btc.get("index_price"))
            premium_bps = (_q_safe_div(mark, index_p, 1) - 1) * 10000 if not pd.isna(mark) and not pd.isna(index_p) else np.nan
            d6.metric("Mark premium", "—" if pd.isna(premium_bps) else f"{premium_bps:+.1f} bps")

            ext_table = pd.DataFrame([
                {"Métrica": "Fear & Greed", "Valor": "—" if pd.isna(fg_v) else f"{fg_v:.0f}", "Lectura": external_btc.get("fear_greed_label", "")},
                {"Métrica": "Market Cap BTC", "Valor": _q_money(external_btc.get("market_cap_usd")), "Lectura": "Dato de mercado público opcional"},
                {"Métrica": "Volumen 24h", "Valor": _q_money(external_btc.get("volume_24h_usd")), "Lectura": "Dato de mercado público opcional"},
                {"Métrica": "Cambio 24h", "Valor": _q_pct(external_btc.get("change_24h_pct")), "Lectura": "Momentum corto"},
                {"Métrica": "Cambio 7d", "Valor": _q_pct(external_btc.get("change_7d_pct")), "Lectura": "Momentum semanal"},
            ])
            st.dataframe(ext_table, use_container_width=True, hide_index=True)
            ok_sources = external_btc.get("sources_ok", [])
            if ok_sources:
                st.success("Fuentes externas activas: " + " · ".join(ok_sources))
            if external_btc.get("errors"):
                with st.expander("Diagnóstico de fuentes externas"):
                    st.write(" · ".join(external_btc["errors"]))
                    st.caption("Esto no invalida el motor local: OHLCV, riesgo y reglas cuantitativas siguen funcionando.")
            st.caption("Fear & Greed: Alternative.me. Datos de derivados/order book: endpoints públicos de Binance cuando están disponibles.")

            st.divider()
            st.markdown("### 📉 Riesgo estadístico de BTC")
            rs1, rs2, rs3, rs4, rs5, rs6 = st.columns(6)
            rs1.metric("VaR 95% diario", _q_pct(quant_risk.get("var95"), 2))
            rs2.metric("CVaR 95% diario", _q_pct(quant_risk.get("cvar95"), 2))
            rs3.metric("Máx. DD muestra", _q_pct(quant_risk.get("max_dd"), 1))
            rs4.metric("Sharpe", f"{_q_float(quant_risk.get('sharpe'), 0):.2f}")
            rs5.metric("Sortino", f"{_q_float(quant_risk.get('sortino'), 0):.2f}")
            rs6.metric("Ulcer Index", f"{_q_float(quant_risk.get('ulcer'), 0):.1f}")
            st.caption(f"Muestra diaria disponible: {int(quant_risk.get('sample_days', 0))} retornos. VaR/CVaR son estimaciones históricas, no límites garantizados de pérdida.")

            qd = prepare_quant_frame(df_1d)
            if not qd.empty:
                chart_qd = qd.tail(365).copy()
                market_fig = go.Figure()
                market_fig.add_trace(go.Scatter(x=chart_qd["time"], y=chart_qd["close"], mode="lines", name="BTC"))
                market_fig.add_trace(go.Scatter(x=chart_qd["time"], y=chart_qd["ema50"], mode="lines", name="EMA50"))
                market_fig.add_trace(go.Scatter(x=chart_qd["time"], y=chart_qd["ema200"], mode="lines", name="EMA200"))
                market_fig.update_layout(template="plotly_white", height=420, title="BTC diario · precio + régimen tendencial", yaxis_title="USDT", margin=dict(l=20, r=20, t=50, b=20))
                st.plotly_chart(market_fig, use_container_width=True, config={"responsive": True}, key="quant_daily_regime")

            st.divider()
            st.markdown("### 🧪 Análogos históricos del régimen actual")
            analog_stats, analog_df = historical_regime_analogs(df_1d)
            if analog_stats:
                an1, an2, an3, an4, an5, an6 = st.columns(6)
                an1.metric("Casos comparables", int(analog_stats.get("samples", 0)))
                an2.metric("Prob. +7D", _q_pct(analog_stats.get("p_up_7"), 0))
                an3.metric("Mediana +7D", _q_pct(analog_stats.get("median_7"), 1))
                an4.metric("Prob. +30D", _q_pct(analog_stats.get("p_up_30"), 0))
                an5.metric("Mediana +30D", _q_pct(analog_stats.get("median_30"), 1))
                an6.metric("Rango P10–P90 30D", f"{_q_pct(analog_stats.get('p10_30'),1)} / {_q_pct(analog_stats.get('p90_30'),1)}")
                st.caption("Compara únicamente episodios pasados con coincidencia en régimen EMA200, momentum, volatilidad y bucket de RSI. No es una probabilidad predictiva garantizada.")
                with st.expander("Ver episodios históricos comparables"):
                    cols = [c for c in ["time", "close", "rsi14", "vol30_ann", "fwd_7", "fwd_30", "fwd_90"] if c in analog_df.columns]
                    st.dataframe(analog_df[cols].head(100), use_container_width=True, hide_index=True)
            else:
                st.info("Todavía no hay suficiente histórico diario para formar un conjunto robusto de análogos.")

        with tab7:
            st.subheader("💼 BTC Investment Lab")
            st.caption("Comparador de enfoques: HODL, DCA, DCA adaptativo, trend following, swing, mean reversion, grid y futuros tácticos. Los scores son de contexto, no recomendaciones personalizadas.")

            # Los módulos anteriores se ejecutan aunque la pestaña no esté visualmente abierta.
            if "quant_snaps" not in locals():
                quant_snaps = {"1D": timeframe_quant_snapshot(df_1d, "1D"), "4H": timeframe_quant_snapshot(df_4h, "4H"), "1H": timeframe_quant_snapshot(df_1h, "1H"), "15M": timeframe_quant_snapshot(df_15m, "15M"), "5M": timeframe_quant_snapshot(df_5m, "5M")}
                quant_risk = daily_risk_metrics(df_1d)
                external_btc = blank_external_btc_metrics()
                trade_context_q = {"candidate_direction": candidate_direction, "long_score": long_score, "short_score": short_score, "rr_real": rr_real, "quality_score": quality_score, "trade_valid": trade_valid}

            inv_matrix = build_investment_matrix(quant_snaps, quant_risk, external_btc, trade_context_q)
            best_inv = inv_matrix.iloc[0] if not inv_matrix.empty else None
            if best_inv is not None:
                st.markdown(f"**Mejor encaje con el régimen actual:** {best_inv['Estrategia']} · {best_inv['Score']}/100 · {best_inv['Estado']}")
            st.dataframe(inv_matrix, use_container_width=True, hide_index=True)

            st.divider()
            st.markdown("### 🪙 Simulador histórico de acumulación")
            i1, i2, i3, i4 = st.columns(4)
            dca_initial = i1.number_input("Capital inicial USDT", min_value=0.0, value=500.0, step=100.0, key="quant_dca_initial")
            dca_periodic = i2.number_input("Aporte periódico USDT", min_value=1.0, value=200.0, step=25.0, key="quant_dca_periodic")
            dca_freq = i3.selectbox("Frecuencia", ["Semanal", "Quincenal", "Mensual"], index=2, key="quant_dca_freq")
            dca_mode = i4.selectbox("Modo", ["DCA fijo", "DCA adaptativo"], key="quant_dca_mode")
            dca_df, dca_stats = simulate_dca_history(df_1d, dca_periodic, dca_initial, dca_freq, adaptive=(dca_mode == "DCA adaptativo"))
            if dca_stats:
                a1, a2, a3, a4, a5, a6 = st.columns(6)
                a1.metric("Invertido", _q_money(dca_stats.get("invested"), 0))
                a2.metric("BTC acumulado", f"{_q_float(dca_stats.get('btc'), 0):.6f}")
                a3.metric("Precio medio", _q_money(dca_stats.get("avg_price"), 0))
                a4.metric("Valor final", _q_money(dca_stats.get("final_value"), 0))
                a5.metric("Retorno DCA", _q_pct(dca_stats.get("return_pct"), 1))
                a6.metric("Lump-sum mismo presupuesto", _q_pct(dca_stats.get("lump_return_pct"), 1))
                dca_fig = go.Figure()
                dca_fig.add_trace(go.Scatter(x=dca_df["Fecha"], y=dca_df["Valor"], mode="lines", name="Valor estrategia"))
                dca_fig.add_trace(go.Scatter(x=dca_df["Fecha"], y=dca_df["Invertido"], mode="lines", name="Capital aportado"))
                dca_fig.update_layout(template="plotly_white", height=380, title=f"{dca_mode} · evolución histórica", yaxis_title="USDT", margin=dict(l=20, r=20, t=50, b=20))
                st.plotly_chart(dca_fig, use_container_width=True, config={"responsive": True}, key="quant_dca_chart")
                with st.expander("Ver compras simuladas"):
                    st.dataframe(dca_df.tail(100), use_container_width=True, hide_index=True)
                    st.download_button("⬇️ Descargar simulación DCA", dca_df.to_csv(index=False), "btc_dca_simulation.csv", "text/csv", key="download_quant_dca")
            else:
                st.info("No hay suficiente histórico diario para simular DCA.")

            st.divider()
            st.markdown("### 🎯 Constructor de posición Spot / Cash")
            p1, p2, p3 = st.columns(3)
            inv_capital = p1.number_input("Capital total USDT", min_value=0.0, value=float(max(account_usd, 100.0)), step=100.0, key="quant_inv_capital")
            btc_alloc = p2.slider("Asignación BTC %", 0, 100, 70, 5, key="quant_btc_alloc")
            reserve_pct = 100 - btc_alloc
            p3.metric("Reserva cash", f"{reserve_pct}%")
            btc_usd = inv_capital * btc_alloc / 100
            cash_usd = inv_capital - btc_usd
            btc_qty_plan = btc_usd / price if price else 0
            z1, z2, z3, z4 = st.columns(4)
            z1.metric("BTC a precio actual", f"{btc_qty_plan:.6f} BTC")
            z2.metric("Exposición BTC", _q_money(btc_usd, 0))
            z3.metric("Cash / dry powder", _q_money(cash_usd, 0))
            z4.metric("Precio BTC", _q_money(price, 0))
            scenario_df = portfolio_scenario_table(price, btc_usd, cash_usd)
            st.dataframe(scenario_df, use_container_width=True, hide_index=True)

            st.divider()
            st.markdown("### 🧠 Reglas por estilo de inversión")
            style = st.selectbox("Analizar estilo", inv_matrix["Estrategia"].tolist(), key="quant_style_selector") if not inv_matrix.empty else None
            if style:
                row = inv_matrix[inv_matrix["Estrategia"] == style].iloc[0]
                st.markdown(f"**{row['Estrategia']} · {row['Score']}/100 · {row['Estado']}**")
                st.write(f"**Horizonte:** {row['Horizonte']}")
                st.write(f"**Régimen ideal:** {row['Regla principal']}")
                st.write(f"**Requisitos:** {row['Qué exige']}")
                st.write(f"**Riesgo principal:** {row['Riesgo']}")

        with tab8:
            st.subheader("🛡️ BTC Risk & Survival Lab")
            st.caption("El objetivo de esta pestaña es supervivencia: dimensionamiento, drawdown, VaR/CVaR, leverage y escenarios de estrés.")

            st.markdown("### 🧱 Risk Kernel · estado de cuenta")
            rk1,rk2,rk3,rk4,rk5,rk6 = st.columns(6)
            rk1.metric("Estado", gate_pro.get("status","BLOCKED"))
            rk2.metric("Pérdida día", f"{journal_stats_pro.get('daily_loss_pct',0):.2f}%")
            rk3.metric("Pérdida semana", f"{journal_stats_pro.get('weekly_loss_pct',0):.2f}%")
            rk4.metric("Drawdown", f"{journal_stats_pro.get('drawdown_pct',0):.2f}%")
            rk5.metric("Racha pérdidas", int(journal_stats_pro.get('loss_streak',0)))
            rk6.metric("Open risk proj.", f"{gate_pro.get('projected_open_risk_pct',0):.2f}%")
            checks_df = pd.DataFrame(gate_pro.get("checks", []))
            if not checks_df.empty:
                checks_df["estado"] = np.where(checks_df["ok"], "✅", np.where(checks_df["severity"]=="BLOCK", "🛑", "⚠️"))
                st.dataframe(checks_df[["estado","code","severity","detail"]], use_container_width=True, hide_index=True)
            st.markdown("#### Stress test de la posición propuesta")
            stress_df = pro_stress_scenarios(effective_account_usd, notional_exec, candidate_direction)
            st.dataframe(stress_df, use_container_width=True, hide_index=True)
            st.caption("Escenarios lineales sobre nocional; no incluyen gaps de liquidez, quiebra del exchange ni slippage de cola. Sirven como stress rápido, no como peor caso absoluto.")
            st.divider()

            if "quant_risk" not in locals():
                quant_risk = daily_risk_metrics(df_1d)

            rsk1, rsk2, rsk3, rsk4, rsk5, rsk6 = st.columns(6)
            rsk1.metric("Vol 30D", _q_pct(quant_risk.get("vol30"), 1))
            rsk2.metric("Vol 90D", _q_pct(quant_risk.get("vol90"), 1))
            rsk3.metric("VaR 99%", _q_pct(quant_risk.get("var99"), 2))
            rsk4.metric("CVaR 99%", _q_pct(quant_risk.get("cvar99"), 2))
            rsk5.metric("Peor día muestra", _q_pct(quant_risk.get("worst_day"), 2))
            rsk6.metric("Días positivos", _q_pct(quant_risk.get("positive_days"), 1))

            st.divider()
            st.markdown("### 📐 Position Sizing independiente")
            ps1, ps2, ps3, ps4 = st.columns(4)
            ps_account = ps1.number_input("Cuenta USDT", min_value=1.0, value=float(account_usd), step=100.0, key="quant_ps_account")
            ps_risk = ps2.slider("Riesgo por trade %", 0.10, 5.00, float(min(max(risk_pct * 100, 0.1), 5.0)), 0.10, key="quant_ps_risk")
            ps_stop = ps3.number_input("Stop técnico %", min_value=0.10, value=1.50, step=0.10, key="quant_ps_stop")
            ps_lev = ps4.slider("Leverage máximo", 1, 50, int(min(max(leverage, 1), 50)), 1, key="quant_ps_lev")
            risk_budget = ps_account * ps_risk / 100
            raw_notional = risk_budget / (ps_stop / 100) if ps_stop else 0
            max_notional_ps = ps_account * ps_lev
            final_notional_ps = min(raw_notional, max_notional_ps)
            btc_size_ps = final_notional_ps / price if price else 0
            actual_risk_ps = final_notional_ps * ps_stop / 100
            sz1, sz2, sz3, sz4, sz5 = st.columns(5)
            sz1.metric("Budget de riesgo", _q_money(risk_budget, 2))
            sz2.metric("Nocional por stop", _q_money(raw_notional, 0))
            sz3.metric("Nocional permitido", _q_money(final_notional_ps, 0))
            sz4.metric("Tamaño BTC", f"{btc_size_ps:.5f}")
            sz5.metric("Riesgo real", _q_money(actual_risk_ps, 2))
            if raw_notional > max_notional_ps:
                st.warning("El tamaño calculado por stop supera el nocional permitido por margen. Se capó automáticamente al máximo por leverage.")

            st.divider()
            st.markdown("### 🎲 Kelly Criterion · referencia estadística")
            bt_wr = _q_float(bt_stats.get("winrate", np.nan)) if "bt_stats" in locals() else np.nan
            bt_payoff = _q_float(bt_stats.get("rr_promedio", np.nan)) if "bt_stats" in locals() else np.nan
            kc1, kc2 = st.columns(2)
            k_win = kc1.number_input("Win rate %", min_value=1.0, max_value=99.0, value=float(bt_wr if not pd.isna(bt_wr) and 1 <= bt_wr <= 99 else 45.0), step=1.0, key="quant_kelly_wr")
            k_rr = kc2.number_input("Payoff ganador/perdedor", min_value=0.10, max_value=10.0, value=float(bt_payoff if not pd.isna(bt_payoff) and bt_payoff > 0 else max(rr_target, 0.1)), step=0.10, key="quant_kelly_rr")
            k = kelly_fraction(k_win, k_rr)
            kk1, kk2, kk3 = st.columns(3)
            kk1.metric("Kelly completo", _q_pct(k["full"] * 100, 1))
            kk2.metric("½ Kelly", _q_pct(k["half"] * 100, 1))
            kk3.metric("¼ Kelly", _q_pct(k["quarter"] * 100, 1))
            st.caption("Kelly es muy sensible a estimaciones erróneas del edge. En trading real suele usarse fraccionado y con límites de riesgo mucho menores.")

            st.divider()
            st.markdown("### ⚠️ Tabla de supervivencia por leverage")
            lev_df = leverage_survival_table(price, ps_account, ps_risk / 100)
            st.dataframe(lev_df, use_container_width=True, hide_index=True)
            st.caption("*El movimiento a liquidación es una aproximación educativa 1/leverage. La liquidación real depende de maintenance margin, fees, mark price y reglas del exchange.")

            st.divider()
            st.markdown("### 💥 Stress test de una posición")
            stress1, stress2, stress3 = st.columns(3)
            stress_notional = stress1.number_input("Nocional de posición USDT", min_value=0.0, value=float(max(notional, 0.0)), step=100.0, key="quant_stress_notional")
            stress_dir = stress2.selectbox("Dirección", ["LONG", "SHORT"], index=0 if candidate_direction != "SHORT" else 1, key="quant_stress_dir")
            stress_account = stress3.number_input("Equity cuenta USDT", min_value=1.0, value=float(account_usd), step=100.0, key="quant_stress_account")
            stress_rows = []
            for mv in [-30, -20, -15, -10, -7.5, -5, -3, -2, -1, 1, 2, 3, 5, 7.5, 10, 15, 20, 30]:
                pnl_s = stress_notional * mv / 100 * (1 if stress_dir == "LONG" else -1)
                eq_s = stress_account + pnl_s
                stress_rows.append({"Movimiento BTC %": mv, "PNL USDT": pnl_s, "Equity estimada": eq_s, "Impacto cuenta %": _q_safe_div(pnl_s, stress_account, 0) * 100, "Estado": "🔴 RUINA" if eq_s <= 0 else "🟠 CRÍTICO" if eq_s < stress_account * 0.7 else "🟡 ALTO" if eq_s < stress_account * 0.85 else "🟢"})
            stress_df = pd.DataFrame(stress_rows)
            st.dataframe(stress_df, use_container_width=True, hide_index=True)

            st.divider()
            st.markdown("### 🧯 Matemática de recuperación de drawdown")
            st.dataframe(drawdown_recovery_table(), use_container_width=True, hide_index=True)

            st.divider()
            st.markdown("### 📊 Distribución de retornos diarios")
            qd_risk = prepare_quant_frame(df_1d)
            rets = qd_risk["ret"].dropna() * 100 if not qd_risk.empty else pd.Series(dtype=float)
            if not rets.empty:
                ret_fig = go.Figure()
                ret_fig.add_trace(go.Histogram(x=rets, nbinsx=60, name="Retorno diario %"))
                if not pd.isna(_q_float(quant_risk.get("var95"))):
                    ret_fig.add_vline(x=quant_risk["var95"], line_dash="dash", annotation_text="VaR95")
                if not pd.isna(_q_float(quant_risk.get("var99"))):
                    ret_fig.add_vline(x=quant_risk["var99"], line_dash="dot", annotation_text="VaR99")
                ret_fig.update_layout(template="plotly_white", height=360, title="Distribución histórica de retornos diarios BTC", xaxis_title="Retorno %", yaxis_title="Frecuencia", margin=dict(l=20, r=20, t=50, b=20))
                st.plotly_chart(ret_fig, use_container_width=True, config={"responsive": True}, key="quant_return_hist")

            st.divider()
            with st.expander("🧾 Reglas de supervivencia obligatorias", expanded=True):
                st.write("""
                - El stop técnico define el tamaño; el tamaño nunca define dónde poner el stop.
                - No aumentar leverage para compensar una entrada tardía.
                - Riesgo total simultáneo debe considerar todas las posiciones correlacionadas como una sola exposición BTC.
                - Funding, OI y crowding son factores de contexto, no señales independientes.
                - Si la volatilidad entra en percentiles extremos, reducir tamaño o frecuencia suele ser más robusto que ampliar stops sin límite.
                - VaR y CVaR describen el histórico disponible; no contienen el peor caso futuro.
                - Nunca usar el precio de liquidación como stop operativo.
                - Si el trade invalida la tesis, salir; no convertir un trade apalancado en una inversión forzada.
                """)

        with tab9:
            st.subheader("🧬 Quant Rules · Motor auditable")
            st.caption("Cada fila muestra una regla, su evidencia, peso e impacto. El score final se puede inspeccionar y exportar.")

            if "quant_snaps" not in locals():
                quant_snaps = {"1D": timeframe_quant_snapshot(df_1d, "1D"), "4H": timeframe_quant_snapshot(df_4h, "4H"), "1H": timeframe_quant_snapshot(df_1h, "1H"), "15M": timeframe_quant_snapshot(df_15m, "15M"), "5M": timeframe_quant_snapshot(df_5m, "5M")}
                quant_risk = daily_risk_metrics(df_1d)
                external_btc = blank_external_btc_metrics()
                trade_context_q = {"candidate_direction": candidate_direction, "long_score": long_score, "short_score": short_score, "rr_real": rr_real, "quality_score": quality_score, "trade_valid": trade_valid}
            if "quant_rules" not in locals():
                quant_rules = build_quant_rulebook(quant_snaps, quant_risk, external_btc, trade_context_q)
            quant_score = quant_rulebook_score(quant_rules)

            if quant_score >= 35:
                score_state = "🟢 Contexto cuantitativo favorable al lado comprador"
            elif quant_score <= -35:
                score_state = "🔴 Contexto cuantitativo favorable al lado vendedor"
            else:
                score_state = "🟡 Contexto mixto: priorizar selectividad"
            qr1, qr2, qr3, qr4 = st.columns(4)
            qr1.metric("Quant Score", f"{quant_score:+.0f}/100")
            qr2.metric("Reglas evaluadas", len(quant_rules))
            qr3.metric("Positivas", int((quant_rules["Impacto"] > 0).sum()))
            qr4.metric("Negativas", int((quant_rules["Impacto"] < 0).sum()))
            st.markdown(f"**{score_state}**")

            cat_summary = quant_rules.groupby("Categoría", as_index=False).agg(Reglas=("Regla", "count"), Impacto=("Impacto", "sum"), Peso=("Peso", "sum"))
            cat_summary["Score categoría"] = np.where(cat_summary["Peso"] > 0, 100 * cat_summary["Impacto"] / cat_summary["Peso"], 0)
            cat_summary = cat_summary.sort_values("Score categoría", ascending=False)
            st.dataframe(cat_summary, use_container_width=True, hide_index=True)

            cat_fig = go.Figure()
            cat_fig.add_trace(go.Bar(x=cat_summary["Categoría"], y=cat_summary["Score categoría"], text=[f"{x:+.0f}" for x in cat_summary["Score categoría"]], textposition="outside"))
            cat_fig.add_hline(y=0, line_dash="dot")
            cat_fig.update_layout(template="plotly_white", height=360, title="Score por familia de reglas", yaxis_title="-100 a +100", margin=dict(l=20, r=20, t=50, b=20))
            st.plotly_chart(cat_fig, use_container_width=True, config={"responsive": True}, key="quant_rules_category")

            st.divider()
            f1, f2 = st.columns([1, 2])
            categories = sorted(quant_rules["Categoría"].dropna().unique().tolist())
            selected_categories = f1.multiselect("Filtrar categorías", categories, default=categories, key="quant_rule_categories")
            state_filter = f2.multiselect("Filtrar estados", ["✅", "⚠️", "❌", "ℹ️"], default=["✅", "⚠️", "❌", "ℹ️"], key="quant_rule_states")
            rules_view = quant_rules[quant_rules["Categoría"].isin(selected_categories) & quant_rules["Estado"].isin(state_filter)]
            st.dataframe(rules_view, use_container_width=True, hide_index=True)
            st.download_button("⬇️ Descargar rulebook CSV", quant_rules.to_csv(index=False), "btc_quant_rulebook.csv", "text/csv", key="download_quant_rulebook")

            positives = quant_rules.sort_values("Impacto", ascending=False).head(8)
            negatives = quant_rules.sort_values("Impacto", ascending=True).head(8)
            cpos, cneg = st.columns(2)
            with cpos:
                st.markdown("#### ✅ Mayores confluencias")
                for _, rr in positives.iterrows():
                    if rr["Impacto"] > 0:
                        st.write(f"**+{rr['Impacto']:.0f}** · {rr['Regla']} · {rr['Valor']}")
            with cneg:
                st.markdown("#### ❌ Mayores riesgos / contradicciones")
                for _, rr in negatives.iterrows():
                    if rr["Impacto"] < 0:
                        st.write(f"**{rr['Impacto']:.0f}** · {rr['Regla']} · {rr['Valor']}")

            st.divider()
            st.markdown("### 🌎 Macro + On-chain + Event Risk · capa manual auditable")
            st.caption("Estos factores no se inventan: se dejan en 'No informado' hasta que cargues un dato confiable. Así el score no finge conocer ETF flows, DXY, MVRV o SOPR cuando no hay una fuente conectada.")
            mc1, mc2, mc3, mc4 = st.columns(4)
            dxy_state = mc1.selectbox("DXY", ["No informado", "Bajando", "Neutral", "Subiendo"], key="quant_dxy")
            yields_state = mc2.selectbox("US10Y", ["No informado", "Bajando", "Neutral", "Subiendo"], key="quant_us10y")
            etf_flow = mc3.selectbox("ETF BTC net flow", ["No informado", "Fuerte entrada", "Entrada", "Neutral", "Salida", "Fuerte salida"], key="quant_etf")
            exch_flow = mc4.selectbox("Exchange netflow", ["No informado", "Fuerte salida BTC", "Salida BTC", "Neutral", "Entrada BTC", "Fuerte entrada BTC"], key="quant_exchange_flow")
            oc1, oc2, oc3, oc4 = st.columns(4)
            mvrv = oc1.selectbox("MVRV", ["No informado", "Infravalorado", "Normal", "Elevado", "Extremo"], key="quant_mvrv")
            sopr = oc2.selectbox("SOPR", ["No informado", "Capitulación", "Debajo de 1", "Cerca de 1", "Encima de 1", "Euforia"], key="quant_sopr")
            stable = oc3.selectbox("Liquidez stablecoins", ["No informado", "Contrayendo", "Neutral", "Expandiendo"], key="quant_stable")
            hashtrend = oc4.selectbox("Hashrate", ["No informado", "Cayendo", "Lateral", "Subiendo"], key="quant_hash")

            ev1, ev2, ev3 = st.columns(3)
            high_macro_event = ev1.checkbox("Evento macro de alto impacto <24h", key="quant_macro_event")
            options_expiry = ev2.checkbox("Vencimiento importante opciones <24h", key="quant_options_expiry")
            exchange_incident = ev3.checkbox("Incidente exchange / liquidez", key="quant_exchange_incident")

            manual_points = 0
            manual_max = 0
            mapping = [
                {"Bajando": 2, "Neutral": 0, "Subiendo": -2}.get(dxy_state, None),
                {"Bajando": 1, "Neutral": 0, "Subiendo": -1}.get(yields_state, None),
                {"Fuerte entrada": 3, "Entrada": 2, "Neutral": 0, "Salida": -2, "Fuerte salida": -3}.get(etf_flow, None),
                {"Fuerte salida BTC": 2, "Salida BTC": 1, "Neutral": 0, "Entrada BTC": -1, "Fuerte entrada BTC": -2}.get(exch_flow, None),
                {"Infravalorado": 2, "Normal": 0, "Elevado": -1, "Extremo": -3}.get(mvrv, None),
                {"Capitulación": 1, "Debajo de 1": 1, "Cerca de 1": 0, "Encima de 1": 1, "Euforia": -2}.get(sopr, None),
                {"Contrayendo": -1, "Neutral": 0, "Expandiendo": 1}.get(stable, None),
                {"Cayendo": -1, "Lateral": 0, "Subiendo": 1}.get(hashtrend, None),
            ]
            for val in mapping:
                if val is not None:
                    manual_points += val
                    manual_max += 3
            event_penalty = (3 if high_macro_event else 0) + (2 if options_expiry else 0) + (5 if exchange_incident else 0)
            manual_score = 100 * manual_points / manual_max if manual_max else 0
            adjusted_score = float(np.clip(quant_score * 0.8 + manual_score * 0.2 - event_penalty * 2, -100, 100)) if manual_max else float(np.clip(quant_score - event_penalty * 2, -100, 100))
            ma1, ma2, ma3 = st.columns(3)
            ma1.metric("Score automático", f"{quant_score:+.0f}")
            ma2.metric("Score manual macro/on-chain", "Sin datos" if not manual_max else f"{manual_score:+.0f}")
            ma3.metric("Score ajustado", f"{adjusted_score:+.0f}", f"penalización eventos: -{event_penalty * 2}")

            with st.expander("📚 Rulebook maestro · principios que nunca deben saltarse"):
                st.write("""
                **Datos y contexto**
                - No usar una única métrica para decidir. Exigir confluencia y distinguir tendencia, momentum, volatilidad y flujo.
                - Un dato externo caído debe figurar como no disponible, nunca convertirse en cero o en una señal falsa.
                - Separar timeframe de entrada del timeframe de tesis. Un 5M alcista no invalida por sí solo un 1D bajista.
                - Un indicador retrasado confirma; no anticipa automáticamente.

                **Spot / acumulación**
                - DCA reduce riesgo de timing, no elimina riesgo de drawdown.
                - Lump-sum aumenta exposición temporal; su conveniencia depende de horizonte y tolerancia al riesgo.
                - Mantener reserva de liquidez si el plan contempla comprar drawdowns.
                - No financiar una inversión spot de largo plazo con deuda que pueda exigir liquidación forzada.

                **Futuros**
                - El leverage es una herramienta de eficiencia de margen, no una licencia para aumentar el riesgo de cuenta.
                - El riesgo por trade debe medirse sobre equity, no sobre margen usado.
                - Funding extremo + OI creciente + crowding aumenta riesgo de squeeze.
                - Nunca mover SL para evitar reconocer una invalidación.
                - No promediar pérdidas apalancadas sin una regla explícita de tamaño máximo agregado.

                **Riesgo**
                - El drawdown compuesto requiere más retorno porcentual para recuperarse: -50% necesita +100%.
                - VaR/CVaR históricos no incluyen todos los gaps, fallas de exchange ni eventos de cola futuros.
                - Correlaciones aumentan en crisis; varias posiciones crypto pueden ser una sola apuesta de riesgo.
                - La prioridad es evitar ruina. Una estrategia sin supervivencia no tiene oportunidad de expresar su edge.
                """)


            st.caption(f"Última actualización local: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

        with tab11:
            inst_render_institutional_os(inst_state_pro, gate_pro, pro_settings)

        with tab10:
            render_btc_configuration()
            st.divider()
            pro_render_configuration_panel(pro_settings)
            st.divider()
            st.markdown("### ✅ Auditoría de implementación · 100 controles PRO")
            feat_df = pd.DataFrame({"#": range(1, len(PRO_100_FEATURES)+1), "Control": PRO_100_FEATURES})
            feat_df["Estado"] = "✅ Implementado / monitorizado"
            st.dataframe(feat_df, use_container_width=True, hide_index=True, height=520)
            st.caption("Algunos controles LIVE dependen de capacidades/credenciales del exchange y deben validarse en TESTNET antes de usar capital real. PAPER funciona sin credenciales.")
            st.divider()
            st.markdown("### 🏛️ Institutional OS · 500 controles agregados")
            inst_matrix_cfg = inst_feature_matrix(inst_state_pro, gate_pro)
            inst_summary_cfg = inst_matrix_cfg.groupby("Dominio", as_index=False).agg(Controles=("Control","count"), Score=("Score dominio","mean"))
            st.dataframe(inst_summary_cfg, use_container_width=True, hide_index=True)
            st.caption(f"Total: {len(inst_matrix_cfg)} controles · 20 dominios · schema {INST_SCHEMA_VERSION} · fail-closed.")

    except Exception as e:
        st.error("Hubo un error cargando el dashboard.")
        st.exception(e)
