"""
Technical indicators — EMA, VWAP, RSI, Volume.
Works on pandas DataFrames with columns: open, high, low, close, volume.
"""

import pandas as pd
import numpy as np


def ema(series: pd.Series, period: int) -> pd.Series:
    return series.ewm(span=period, adjust=False).mean()


def rsi(series: pd.Series, period: int = 14) -> pd.Series:
    delta = series.diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    avg_gain = gain.ewm(com=period - 1, adjust=False).mean()
    avg_loss = loss.ewm(com=period - 1, adjust=False).mean()
    rs = avg_gain / avg_loss.replace(0, np.nan)
    return 100 - (100 / (1 + rs))


def vwap(df: pd.DataFrame) -> pd.Series:
    """
    Intraday VWAP — resets each day.
    Requires columns: high, low, close, volume, and a DatetimeIndex.
    """
    typical_price = (df["high"] + df["low"] + df["close"]) / 3
    pv = typical_price * df["volume"]

    # Group by date and compute cumulative sums
    dates = df.index.normalize()
    result = pd.Series(index=df.index, dtype=float)
    for date in dates.unique():
        mask = dates == date
        cum_pv = pv[mask].cumsum()
        cum_vol = df.loc[mask, "volume"].cumsum()
        result[mask] = cum_pv / cum_vol.replace(0, np.nan)
    return result


def volume_sma(series: pd.Series, period: int = 20) -> pd.Series:
    return series.rolling(period).mean()


def add_indicators(df: pd.DataFrame, ema_fast: int = 20, ema_slow: int = 50,
                   rsi_period: int = 14, vol_period: int = 20) -> pd.DataFrame:
    """Add all strategy indicators to a OHLCV dataframe."""
    df = df.copy()
    df["ema_fast"] = ema(df["close"], ema_fast)
    df["ema_slow"] = ema(df["close"], ema_slow)
    df["rsi"] = rsi(df["close"], rsi_period)
    df["vwap"] = vwap(df)
    df["vol_sma"] = volume_sma(df["volume"], vol_period)
    df["vol_ratio"] = df["volume"] / df["vol_sma"]
    return df


def detect_ema_crossover(df: pd.DataFrame) -> pd.Series:
    """
    Returns +1 on bullish crossover (fast crosses above slow),
    -1 on bearish crossover, 0 otherwise.
    """
    fast_above = (df["ema_fast"] > df["ema_slow"]).astype(bool)
    prev_fast_above = fast_above.shift(1).fillna(False).astype(bool)
    signal = pd.Series(0, index=df.index)
    signal[fast_above & ~prev_fast_above] = 1    # Bullish crossover
    signal[~fast_above & prev_fast_above] = -1   # Bearish crossover
    return signal


def market_structure(df: pd.DataFrame, vix: float = None) -> str:
    """
    Classify market as: 'trending_up', 'trending_down', 'ranging', 'volatile'.
    Based on last candle vs VWAP and EMA alignment.
    """
    last = df.iloc[-1]
    if vix is not None:
        if vix > 20:
            return "volatile"
        if vix < 12:
            return "low_vol"

    trending_up   = last["ema_fast"] > last["ema_slow"] and last["close"] > last["vwap"]
    trending_down = last["ema_fast"] < last["ema_slow"] and last["close"] < last["vwap"]

    if trending_up:
        return "trending_up"
    if trending_down:
        return "trending_down"
    return "ranging"
