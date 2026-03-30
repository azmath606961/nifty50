"""
Strategy: EMA Crossover + RSI + VWAP + Volume Confirmation
Implements the 3-confirmation model from Nifty50_Trading_System.xlsx.

Entry conditions (LONG):
  1. EMA 20 crosses above EMA 50 (fresh crossover on 5-min)
  2. Price above VWAP
  3. RSI > 50 with momentum
  4. Volume ≥ 1.5× 20-period avg
  5. 15-min trend = trending_up (EMA20 > EMA50 on higher TF)
  6. Within prime trading window

Entry conditions (SHORT): mirror of above.
"""

import logging
import pandas as pd
from core.indicators import add_indicators, detect_ema_crossover, market_structure

logger = logging.getLogger(__name__)

SETUP_NAME = "EMA Crossover + RSI + VWAP"


def generate_signal(
    df_5m: pd.DataFrame,
    df_15m: pd.DataFrame,
    vix: float = None,
) -> dict:
    """
    Analyse candles and return a signal dict.

    Returns:
        {
          "signal":    "LONG" | "SHORT" | "NONE",
          "setup":     str,
          "entry":     float,
          "sl":        float,
          "option":    "CE" | "PE" | None,
          "reason":    str,
        }
    """
    result = {"signal": "NONE", "setup": SETUP_NAME, "entry": 0.0,
              "sl": 0.0, "option": None, "reason": ""}

    if df_5m is None or len(df_5m) < 55:
        result["reason"] = "Insufficient 5-min data"
        return result

    if df_15m is None or len(df_15m) < 55:
        result["reason"] = "Insufficient 15-min data"
        return result

    # Add indicators to both timeframes
    df5  = add_indicators(df_5m)
    df15 = add_indicators(df_15m)

    last5  = df5.iloc[-1]
    last15 = df15.iloc[-1]

    # ── 15-min trend filter ────────────────────────────────────────────────
    trend_15m = market_structure(df15, vix)
    if trend_15m in ("ranging", "low_vol"):
        result["reason"] = f"15-min market is {trend_15m} — no trade"
        return result

    # ── 5-min crossover ────────────────────────────────────────────────────
    crossover = detect_ema_crossover(df5)
    last_cross = crossover.iloc[-1]
    # Allow signal within last 3 candles (crossover is fresh)
    recent_cross = crossover.iloc[-3:].abs().max()
    if recent_cross == 0:
        result["reason"] = "No recent EMA crossover on 5-min"
        return result

    # Determine direction from crossover direction
    recent_signal = crossover.iloc[-3:][crossover.iloc[-3:] != 0]
    if recent_signal.empty:
        result["reason"] = "No directional crossover found"
        return result

    cross_direction = int(recent_signal.iloc[-1])  # +1 or -1

    # ── Volume check ───────────────────────────────────────────────────────
    vol_ratio = last5["vol_ratio"]
    if pd.isna(vol_ratio) or vol_ratio < 1.5:
        result["reason"] = f"Volume {vol_ratio:.2f}x < 1.5× avg"
        return result

    # ── RSI check ──────────────────────────────────────────────────────────
    rsi_val = last5["rsi"]

    # ── VWAP check ─────────────────────────────────────────────────────────
    close = last5["close"]
    vwap_val = last5["vwap"]

    # ── 15-min alignment ───────────────────────────────────────────────────
    if cross_direction == 1:  # Bullish crossover
        if trend_15m != "trending_up":
            result["reason"] = f"15-min trend {trend_15m} ≠ trending_up for LONG"
            return result
        if close <= vwap_val:
            result["reason"] = f"Price Rs{close:.0f} below VWAP Rs{vwap_val:.0f}"
            return result
        if rsi_val <= 50:
            result["reason"] = f"RSI {rsi_val:.1f} ≤ 50 for LONG"
            return result

        # SL = low of signal candle (or prev candle)
        sl = min(df5.iloc[-1]["low"], df5.iloc[-2]["low"])
        result.update({
            "signal": "LONG",
            "entry": close,
            "sl": round(sl, 2),
            "option": "CE",
            "reason": f"[LONG] EMA cross-UP | RSI={rsi_val:.0f} | Vol={vol_ratio:.1f}x | Price>VWAP",
        })

    elif cross_direction == -1:  # Bearish crossover
        if trend_15m != "trending_down":
            result["reason"] = f"15-min trend {trend_15m} ≠ trending_down for SHORT"
            return result
        if close >= vwap_val:
            result["reason"] = f"Price Rs{close:.0f} above VWAP Rs{vwap_val:.0f}"
            return result
        if rsi_val >= 50:
            result["reason"] = f"RSI {rsi_val:.1f} ≥ 50 for SHORT"
            return result

        sl = max(df5.iloc[-1]["high"], df5.iloc[-2]["high"])
        result.update({
            "signal": "SHORT",
            "entry": close,
            "sl": round(sl, 2),
            "option": "PE",
            "reason": f"[SHORT] EMA cross-DN | RSI={rsi_val:.0f} | Vol={vol_ratio:.1f}x | Price<VWAP",
        })

    logger.info("Signal: %s | %s", result["signal"], result["reason"])
    return result
