# =========================
# BACKTEST / ESTADISTICAS / MONTE CARLO
# =========================
from config import *
from helpers import *
from analysis import *
from exchange import get_ohlcv, add_indicators, resample_ohlcv
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
    


def outcome_from_future(future_df, direction, sl, tp, rr_value):
    if future_df.empty or pd.isna(sl) or pd.isna(tp):
        return "SIN_DATOS", 0.0
    for _, row in future_df.iterrows():
        if direction == "LONG":
            hit_sl, hit_tp = row["low"] <= sl, row["high"] >= tp
        else:
            hit_sl, hit_tp = row["high"] >= sl, row["low"] <= tp
        if hit_sl and hit_tp:
            return "SL", -1.0
        if hit_tp:
            return "TP", rr_value if not pd.isna(rr_value) else rr_target
        if hit_sl:
            return "SL", -1.0
    return "NINGUNO", 0.0
def performance_stats(results):
    if results is None or results.empty or "resultado" not in results.columns:
        return {"operaciones": 0, "winrate": 0, "profit_factor": 0, "drawdown": 0, "expectancy": 0, "rr_promedio": 0}
    closed = results[results["resultado"].isin(["TP", "SL"])].copy()
    if closed.empty:
        return {"operaciones": 0, "winrate": 0, "profit_factor": 0, "drawdown": 0, "expectancy": 0, "rr_promedio": 0}
    closed["r_multiple"] = pd.to_numeric(closed["r_multiple"], errors="coerce").fillna(0)
    wins = closed[closed["resultado"] == "TP"]
    losses = closed[closed["resultado"] == "SL"]
    gross_profit, gross_loss = wins["r_multiple"].sum(), abs(losses["r_multiple"].sum())
    profit_factor = gross_profit / gross_loss if gross_loss > 0 else np.inf
    equity = closed["r_multiple"].cumsum()
    drawdown = (equity - equity.cummax()).min()
    return {
        "operaciones": len(closed),
        "winrate": (len(wins) / len(closed)) * 100,
        "profit_factor": profit_factor,
        "drawdown": drawdown,
        "expectancy": closed["r_multiple"].mean(),
        "rr_promedio": wins["r_multiple"].mean() if len(wins) else 0,
    }
def stats_by_strategy(df):
    if df is None or df.empty or "estrategia" not in df.columns:
        return pd.DataFrame()
    rows = []
    for strat, group in df.groupby("estrategia"):
        s = performance_stats(group)
        rows.append({"estrategia": strat, "operaciones": s["operaciones"], "winrate_%": round(s["winrate"], 1), "profit_factor": np.inf if s["profit_factor"] == np.inf else round(s["profit_factor"], 2), "drawdown_R": round(s["drawdown"], 2), "expectativa_R": round(s["expectancy"], 2)})
    out = pd.DataFrame(rows)
    if not out.empty:
        out = out.sort_values(["expectativa_R", "profit_factor", "winrate_%"], ascending=False)
        out.insert(0, "ranking", range(1, len(out) + 1))
    return out
def last_30_days_stats(df):
    if df is None or df.empty or "fecha" not in df.columns:
        return performance_stats(pd.DataFrame()), pd.DataFrame()
    h = df.copy()
    h["fecha_dt"] = pd.to_datetime(h["fecha"], utc=True, errors="coerce")
    cutoff = pd.Timestamp.utcnow() - pd.Timedelta(days=30)
    h30 = h[h["fecha_dt"] >= cutoff]
    return performance_stats(h30), h30
@st.cache_data(ttl=300, show_spinner=False)
def run_simple_backtest(timeframe, period_label, estrategia, min_score, rr_target, min_rr, max_atr_multiplier, use_time_filter, avoid_weekends_filter, fvg_min_atr_param, fvg_max_distance_atr_param, use_fvg_filter_param):
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
        fvg_bt = detect_fvg_zones(df_15_bt, fvg_min_atr_param, 120)
        price_bt = df_5_bt["close"].iloc[-1]
        structure_bt = structure_state(df_5_bt)
        long_score_bt = score_direction("LONG", df_4h_bt, df_1h_bt, df_15_bt, df_5_bt, levels_bt, fvg_bt, fvg_max_distance_atr_param)
        short_score_bt = score_direction("SHORT", df_4h_bt, df_1h_bt, df_15_bt, df_5_bt, levels_bt, fvg_bt, fvg_max_distance_atr_param)
        escenario_bt, market_bias_bt = detect_market_intention(price_bt, df_4h_bt, df_1h_bt, df_15_bt, levels_bt)
        direction_bt = choose_candidate_direction(estrategia, long_score_bt, short_score_bt, trend_state(df_1d_bt), trend_state(df_4h_bt), structure_bt, price_bt, df_15_bt, df_5_bt, levels_bt, fvg_bt)
        fvg_zone_bt = nearest_fvg(price_bt, fvg_bt, direction_bt, True)
        sl_bt, tp_bt, risk_points_bt = technical_levels(direction_bt, df_5_bt, price_bt, rr_target, fvg_zone_bt)
        rr_bt = calculate_rr(price_bt, sl_bt, tp_bt, direction_bt)
        valid_bt, motivos_bt = validate_trade(estrategia, direction_bt, long_score_bt, short_score_bt, min_score, 0.01, rr_bt, min_rr, risk_points_bt, df_15_bt["atr"].iloc[-1], market_bias_bt, structure_bt, price_bt, levels_bt, max_atr_multiplier, df_15_bt, df_5_bt, use_time_filter, avoid_weekends_filter, fvg_bt, use_fvg_filter_param, fvg_max_distance_atr_param, df_1h_bt)
        if not valid_bt:
            continue
        future = df.iloc[i + 1:i + 1 + horizon]
        result, r_mult = outcome_from_future(future, direction_bt, sl_bt, tp_bt, rr_bt)
        rows.append({"fecha": df_5_bt["time"].iloc[-1], "estrategia": estrategia, "direccion": direction_bt, "entrada": price_bt, "sl": sl_bt, "tp": tp_bt, "rr": rr_bt, "long_score": long_score_bt, "short_score": short_score_bt, "resultado": result, "r_multiple": r_mult, "escenario": escenario_bt, "fvg": fvg_zone_bt.get("tipo") if fvg_zone_bt else "SIN_FVG", "motivos": " | ".join(motivos_bt)})
    res = pd.DataFrame(rows)
    return res, performance_stats(res)
def validate_saved_signals(historial, current_df_5m, hours_after=24):
    if historial is None or historial.empty:
        return historial
    h = historial.copy()
    if "resultado" not in h.columns:
        h["resultado"] = ""
    else:
        h["resultado"] = h["resultado"].astype(str)
    if "r_multiple" not in h.columns:
        h["r_multiple"] = np.nan
    if "validado_hasta" not in h.columns:
        h["validado_hasta"] = ""
    else:
        h["validado_hasta"] = h["validado_hasta"].astype(str)
    now_utc = current_df_5m["time"].max()
    for idx, row in h.iterrows():
        if str(row.get("resultado", "nan")) in ["TP", "SL", "NINGUNO", "NO_OPERAR"]:
            continue
        fecha = pd.to_datetime(row.get("fecha"), utc=True, errors="coerce")
        if pd.isna(fecha) or now_utc < fecha + pd.Timedelta(hours=hours_after):
            continue
        direction = row.get("direccion_calculada", row.get("decision", ""))
        if direction not in ["LONG", "SHORT"]:
            h.at[idx, "resultado"] = "NO_OPERAR"
            h.at[idx, "r_multiple"] = 0.0
            continue
        try:
            sl, tp = float(row["sl"]), float(row["tp"])
        except Exception:
            continue
        future = current_df_5m[(current_df_5m["time"] > fecha) & (current_df_5m["time"] <= fecha + pd.Timedelta(hours=hours_after))]
        rr_value = pd.to_numeric(row.get("rr_real", np.nan), errors="coerce")
        result, r_mult = outcome_from_future(future, direction, sl, tp, rr_value)
        h.at[idx, "resultado"] = result
        h.at[idx, "r_multiple"] = r_mult
        h.at[idx, "validado_hasta"] = (fecha + pd.Timedelta(hours=hours_after)).strftime("%Y-%m-%d %H:%M:%S")
    return h

def max_drawdown_pct(equity_curve):
    eq = np.asarray(equity_curve, dtype=float)
    if len(eq) == 0:
        return 0.0
    peak = np.maximum.accumulate(eq)
    dd = (peak - eq) / np.where(peak == 0, np.nan, peak)
    return float(np.nanmax(dd) * 100) if len(dd) else 0.0

def max_losing_streak(r_values):
    max_streak = 0
    streak = 0
    for r in r_values:
        if r < 0:
            streak += 1
            max_streak = max(max_streak, streak)
        else:
            streak = 0
    return max_streak

@st.cache_data(ttl=300, show_spinner=False)
def monte_carlo_simulation(r_multiples_tuple, account_usd, risk_pct, paths=5000, horizon=50, ruin_dd_pct=30.0, seed=42):
    rng = np.random.default_rng(seed)
    r_multiples = np.array(r_multiples_tuple, dtype=float)
    r_multiples = r_multiples[np.isfinite(r_multiples)]
    if len(r_multiples) == 0:
        r_multiples = np.array([-1.0, 2.0])
    paths = int(paths)
    horizon = int(horizon)
    all_dd = np.zeros(paths)
    final_equity = np.zeros(paths)
    max_loss_streaks = np.zeros(paths)
    ruin_hits = np.zeros(paths, dtype=bool)
    sample_curves = []
    for p in range(paths):
        sampled_r = rng.choice(r_multiples, size=horizon, replace=True)
        pnl = sampled_r * (account_usd * risk_pct)
        equity = account_usd + np.cumsum(pnl)
        all_dd[p] = max_drawdown_pct(equity)
        final_equity[p] = equity[-1]
        max_loss_streaks[p] = max_losing_streak(sampled_r)
        ruin_hits[p] = all_dd[p] >= ruin_dd_pct or equity.min() <= account_usd * (1 - ruin_dd_pct / 100)
        if p < 30:
            sample_curves.append(equity)
    summary = {
        "paths": paths,
        "horizon": horizon,
        "start_capital": account_usd,
        "risk_pct": risk_pct,
        "dd_median": float(np.percentile(all_dd, 50)),
        "dd_p75": float(np.percentile(all_dd, 75)),
        "dd_p95": float(np.percentile(all_dd, 95)),
        "dd_p99": float(np.percentile(all_dd, 99)),
        "final_median": float(np.percentile(final_equity, 50)),
        "final_p05": float(np.percentile(final_equity, 5)),
        "final_p95": float(np.percentile(final_equity, 95)),
        "ruin_probability": float(np.mean(ruin_hits) * 100),
        "loss_streak_median": float(np.percentile(max_loss_streaks, 50)),
        "loss_streak_p95": float(np.percentile(max_loss_streaks, 95)),
        "loss_streak_p99": float(np.percentile(max_loss_streaks, 99)),
        "dd_values": all_dd,
        "final_equity": final_equity,
        "sample_curves": sample_curves,
    }
    return summary

def build_r_multiples_from_sources(bt_results, combined_hist, use_backtest, manual_wr, manual_rr):
    source = "manual"
    r_values = []
    if use_backtest and bt_results is not None and not bt_results.empty and "r_multiple" in bt_results.columns:
        closed = bt_results[bt_results["resultado"].isin(["TP", "SL"])].copy()
        if len(closed) >= 10:
            r_values = pd.to_numeric(closed["r_multiple"], errors="coerce").dropna().tolist()
            source = "backtest"
    if not r_values and combined_hist is not None and not combined_hist.empty and "r_multiple" in combined_hist.columns:
        closed = combined_hist[combined_hist["resultado"].isin(["TP", "SL"])].copy()
        if len(closed) >= 10:
            r_values = pd.to_numeric(closed["r_multiple"], errors="coerce").dropna().tolist()
            source = "historial real"
    if not r_values:
        wins = max(1, int(round(manual_wr)))
        losses = max(1, 100 - wins)
        r_values = [float(manual_rr)] * wins + [-1.0] * losses
        source = "manual"
    return tuple(float(x) for x in r_values if np.isfinite(x)), source
def signal_key(row):
    return f"{row['vela_5m']}_{row['estrategia']}_{row['decision']}_{row['direccion_calculada']}"

def direction_score(direction, long_score, short_score):
    return long_score if direction == "LONG" else short_score
# ========