"""
Backtester - Nifty 50 Intraday Trading System
Run as: python -m backtester.backtest --csv data/NIFTY_50-...csv --capital 50000
Or:     python backtester/backtest.py  --csv data/NIFTY_50-...csv --capital 50000
"""

import argparse
import csv
import logging
import os
import sys
from datetime import datetime, time
from typing import Optional

import pandas as pd
import numpy as np

# Works for both `python -m` and direct execution
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from core.indicators import add_indicators, detect_ema_crossover, market_structure
from strategies.ema_crossover import generate_signal
import config

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)


# --------------------------------------------------------------------------- #
#  CSV LOADER  — auto-detects any Nifty data export format                    #
# --------------------------------------------------------------------------- #

def load_csv(path: str) -> pd.DataFrame:
    """
    Handles all common Nifty CSV formats:
      Dhan export   : date, time, open, high, low, close, volume
      NSE/Zerodha   : Date, Open, High, Low, Close, Volume
      TradingView   : time (unix), open, high, low, close, volume
      Generic       : datetime, open, high, low, close, volume
    """
    df = pd.read_csv(path)
    df.columns = [c.strip().lower() for c in df.columns]

    logger.info("CSV columns detected : %s", list(df.columns))
    logger.info("CSV shape            : %d rows x %d cols", *df.shape)
    logger.info("First row            : %s", df.iloc[0].to_dict())

    # -- Build datetime index ------------------------------------------------
    if "datetime" in df.columns:
        df["_dt"] = pd.to_datetime(df["datetime"])

    elif "date" in df.columns and "time" in df.columns:
        df["_dt"] = pd.to_datetime(
            df["date"].astype(str) + " " + df["time"].astype(str),
        )

    elif "date" in df.columns:
        df["_dt"] = pd.to_datetime(df["date"])

    elif "timestamp" in df.columns:
        ts = df["timestamp"]
        if pd.api.types.is_numeric_dtype(ts) and ts.iloc[0] > 1_000_000_000:
            df["_dt"] = pd.to_datetime(ts, unit="s")
        else:
            df["_dt"] = pd.to_datetime(ts)

    elif "time" in df.columns:
        df["_dt"] = pd.to_datetime(df["time"])

    else:
        raise ValueError(
            "Cannot find a datetime column.\n"
            "Expected one of: datetime | date+time | timestamp | date | time\n"
            "Columns found: " + str(list(df.columns))
        )

    df = df.set_index("_dt")
    df.index.name = "datetime"

    # -- Normalise OHLCV column names ----------------------------------------
    rename = {}
    for col in df.columns:
        c = col.lower()
        if c in ("open", "o"):              rename[col] = "open"
        elif c in ("high", "h"):            rename[col] = "high"
        elif c in ("low", "l"):             rename[col] = "low"
        elif c in ("close", "c", "ltp"):    rename[col] = "close"
        elif c in ("volume", "vol", "v"):   rename[col] = "volume"
    df = df.rename(columns=rename)

    missing = {"open", "high", "low", "close", "volume"} - set(df.columns)
    if missing:
        raise ValueError(
            "Missing required columns: " + str(missing) + "\n"
            "Columns available: " + str(list(df.columns))
        )

    df = df[["open", "high", "low", "close", "volume"]].copy()
    df = df.apply(pd.to_numeric, errors="coerce").dropna().sort_index()

    # Strip timezone so comparisons are simple IST naive timestamps
    if df.index.tz is not None:
        df.index = df.index.tz_convert("Asia/Kolkata").tz_localize(None)

    logger.info("Loaded %d bars | %s  ->  %s", len(df), df.index[0], df.index[-1])

    # Warn if data doesn't look like intraday 5-min bars
    if len(df) > 2:
        gap = df.index.to_series().diff().dropna().mode().iloc[0]
        logger.info("Detected bar interval: %s", gap)
        if gap >= pd.Timedelta("60min"):
            logger.warning(
                "Data looks like %s bars - backtester needs 5-minute bars. "
                "Please export 5-min OHLCV data.", gap
            )

    return df


def resample_to_15m(df_5m: pd.DataFrame) -> pd.DataFrame:
    return df_5m.resample("15min").agg(
        open=("open", "first"),
        high=("high", "max"),
        low=("low", "min"),
        close=("close", "last"),
        volume=("volume", "sum"),
    ).dropna()


# --------------------------------------------------------------------------- #
#  BACKTESTER                                                                  #
# --------------------------------------------------------------------------- #

class Backtester:

    def __init__(
        self,
        df_5m: pd.DataFrame,
        df_15m: pd.DataFrame,
        initial_capital: float = 50_000,
        risk_pct: float = 0.03,
        rr_ratio: float = 1.5,
        max_trades_per_day: int = 2,
        max_consec_losses: int = 2,
        output_csv: str = "logs/backtest_results.csv",
        min_bars: int = 30,
    ):
        self.df_5m  = df_5m.sort_index()
        self.df_15m = df_15m.sort_index()
        self.initial_capital = initial_capital
        self.capital = initial_capital
        self.risk_pct = risk_pct
        self.rr_ratio = rr_ratio
        self.max_trades_per_day = max_trades_per_day
        self.max_consec_losses = max_consec_losses
        self.output_csv = output_csv
        self.min_bars = min_bars

        self.trades: list[dict] = []
        self.equity_curve: list[float] = [initial_capital]

        self._day_trades = 0
        self._day_consec_losses = 0
        self._current_date = None

        # Skip-reason counters for diagnosis
        self._skip = {
            "outside_session":  0,
            "daily_limit":      0,
            "consec_loss_stop": 0,
            "in_trade":         0,
            "insufficient_bars":0,
            "no_signal":        0,
            "zero_sl_dist":     0,
            "zero_qty":         0,
        }

    def _in_prime_session(self, t: time) -> bool:
        return (time(9, 30) <= t <= time(11, 30)) or \
               (time(13, 30) <= t <= time(14, 45))

    def _reset_day(self, date):
        self._current_date = date
        self._day_trades = 0
        self._day_consec_losses = 0

    def _get_window(self, df, ts, n):
        return df[df.index <= ts].tail(n)

    def _simulate_trade(self, direction, entry_ts, entry_price, sl, target, qty):
        future = self.df_5m[self.df_5m.index > entry_ts]
        for ts, row in future.iterrows():
            if ts.time() >= time(14, 45):
                exit_price = row["close"]
                pnl = (exit_price - entry_price) * qty \
                      if direction == "LONG" else (entry_price - exit_price) * qty
                result = "WIN" if pnl > 0 else "LOSS" if pnl < 0 else "BE"
                return result, round(pnl, 2), ts

            if direction == "LONG":
                if row["low"] <= sl:
                    return "LOSS", round((sl - entry_price) * qty, 2), ts
                if row["high"] >= target:
                    return "WIN", round((target - entry_price) * qty, 2), ts
            else:
                if row["high"] >= sl:
                    return "LOSS", round((entry_price - sl) * qty, 2), ts
                if row["low"] <= target:
                    return "WIN", round((entry_price - target) * qty, 2), ts

        return "BE", 0.0, entry_ts

    def run(self) -> dict:
        logger.info("=" * 60)
        logger.info("BACKTEST START")
        logger.info("Capital    : Rs %.0f", self.initial_capital)
        logger.info("5m bars    : %d  (%s to %s)",
                    len(self.df_5m), self.df_5m.index[0], self.df_5m.index[-1])
        logger.info("15m bars   : %d", len(self.df_15m))
        logger.info("Risk/trade : %.1f%%  |  RR: %.1f", self.risk_pct*100, self.rr_ratio)
        logger.info("=" * 60)

        skip_until: Optional[pd.Timestamp] = None

        for ts, row in self.df_5m.iterrows():
            date = ts.date()

            if date != self._current_date:
                self._reset_day(date)

            if skip_until and ts <= skip_until:
                self._skip["in_trade"] += 1
                continue

            if not self._in_prime_session(ts.time()):
                self._skip["outside_session"] += 1
                continue

            if self._day_trades >= self.max_trades_per_day:
                self._skip["daily_limit"] += 1
                continue

            if self._day_consec_losses >= self.max_consec_losses:
                self._skip["consec_loss_stop"] += 1
                continue

            df5  = self._get_window(self.df_5m,  ts, self.min_bars)
            df15 = self._get_window(self.df_15m, ts, max(10, self.min_bars // 3))

            if len(df5) < self.min_bars or len(df15) < 10:
                self._skip["insufficient_bars"] += 1
                continue

            sig = generate_signal(df5, df15)
            if sig["signal"] == "NONE":
                self._skip["no_signal"] += 1
                continue

            entry   = row["close"]
            sl      = sig["sl"]
            sl_dist = abs(entry - sl)

            if sl_dist <= 0:
                self._skip["zero_sl_dist"] += 1
                continue

            risk_amount = self.capital * self.risk_pct
            qty = int(risk_amount / sl_dist)

            if qty < 1:
                self._skip["zero_qty"] += 1
                continue

            target_dist = sl_dist * self.rr_ratio
            target = entry + target_dist if sig["signal"] == "LONG" else entry - target_dist

            logger.info("[%s] %s entry=%.1f  sl=%.1f  target=%.1f  qty=%d",
                        ts, sig["signal"], entry, sl, target, qty)

            result, pnl, exit_ts = self._simulate_trade(
                sig["signal"], ts, entry, sl, target, qty)

            self.capital += pnl
            self.equity_curve.append(self.capital)
            self._day_trades += 1
            self._day_consec_losses = 0 if result in ("WIN", "BE") else self._day_consec_losses + 1

            self.trades.append({
                "date":          str(date),
                "entry_time":    ts.strftime("%H:%M"),
                "exit_time":     exit_ts.strftime("%H:%M"),
                "setup":         sig["setup"],
                "direction":     sig["signal"],
                "entry":         round(entry, 2),
                "sl":            round(sl, 2),
                "target":        round(target, 2),
                "qty":           qty,
                "risk_rs":       round(risk_amount, 2),
                "target_profit": round(target_dist * qty, 2),
                "result":        result,
                "pnl":           pnl,
                "balance":       round(self.capital, 2),
                "growth_pct":    round((self.capital - self.initial_capital) / self.initial_capital, 4),
            })
            skip_until = exit_ts
            logger.info("  -> %s  pnl=%.0f  balance=%.0f", result, pnl, self.capital)

        # ------------------------------------------------------------------- #
        #  Post-run diagnostics                                                #
        # ------------------------------------------------------------------- #
        logger.info("=" * 60)
        logger.info("BACKTEST COMPLETE | Trades generated: %d", len(self.trades))
        logger.info("Skip breakdown:")
        for k, v in self._skip.items():
            logger.info("  %-25s : %d", k, v)
        logger.info("=" * 60)

        if not self.trades:
            msg = (
                "\n\nNO TRADES GENERATED. Diagnosis:\n"
                f"  outside_session   = {self._skip['outside_session']}  "
                "(timestamps not in 9:30-11:30 / 13:30-14:45 IST?)\n"
                f"  insufficient_bars = {self._skip['insufficient_bars']}  "
                "(fewer than min_bars={} rows in window?)\n"
                f"  no_signal         = {self._skip['no_signal']}  "
                "(EMA crossovers found but other filters blocked them)\n\n"
                "Quick fixes to try:\n"
                "  1. Run with --debug to see your data's actual timestamps\n"
                "  2. Run with --min-bars 15 to lower the warmup threshold\n"
                "  3. Confirm CSV has 5-minute bars (not daily/hourly)\n"
                "  4. Confirm timestamps are in IST (not UTC)\n"
            ).format(self.min_bars)
            logger.error(msg)
            return {"error": "No trades generated", "skip_counts": self._skip}

        return self._compute_metrics()

    def _compute_metrics(self) -> dict:
        wins   = [t for t in self.trades if t["result"] == "WIN"]
        losses = [t for t in self.trades if t["result"] == "LOSS"]

        total_win  = sum(t["pnl"] for t in wins)
        total_loss = abs(sum(t["pnl"] for t in losses))

        win_rate      = len(wins) / len(self.trades)
        profit_factor = round(total_win / total_loss, 2) if total_loss else float("inf")

        equity = pd.Series(self.equity_curve)
        max_dd = round((equity.cummax() - equity).max(), 2)
        max_dd_pct = round(max_dd / self.initial_capital * 100, 2)

        pnl_s  = pd.Series([t["pnl"] for t in self.trades])
        sharpe = round((pnl_s.mean() / pnl_s.std()) * (252 ** 0.5), 2) \
                 if pnl_s.std() > 0 else 0

        max_consec = cur = 0
        for t in self.trades:
            cur = cur + 1 if t["result"] == "LOSS" else 0
            max_consec = max(max_consec, cur)

        net_pnl = self.capital - self.initial_capital
        m = {
            "total_trades":           len(self.trades),
            "wins":                   len(wins),
            "losses":                 len(losses),
            "win_rate":               f"{win_rate:.1%}",
            "avg_win_rs":             round(total_win / len(wins), 2) if wins else 0,
            "avg_loss_rs":            round(total_loss / len(losses), 2) if losses else 0,
            "profit_factor":          profit_factor,
            "max_consecutive_losses": max_consec,
            "max_drawdown_rs":        max_dd,
            "max_drawdown_pct":       f"{max_dd_pct:.1f}%",
            "net_pnl_rs":             round(net_pnl, 2),
            "final_capital_rs":       round(self.capital, 2),
            "return_pct":             f"{net_pnl / self.initial_capital:.1%}",
            "sharpe_ratio":           sharpe,
        }
        self._save_results(m)
        self._print_report(m)
        return m

    def _save_results(self, metrics):
        out_dir = os.path.dirname(self.output_csv)
        if out_dir:
            os.makedirs(out_dir, exist_ok=True)
        with open(self.output_csv, "w", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=list(self.trades[0].keys()))
            writer.writeheader()
            writer.writerows(self.trades)
        summary = self.output_csv.replace(".csv", "_summary.csv")
        with open(summary, "w", newline="") as f:
            w = csv.writer(f)
            w.writerow(["Metric", "Value"])
            for k, v in metrics.items():
                w.writerow([k, v])
        logger.info("Trade log : %s", self.output_csv)
        logger.info("Summary   : %s", summary)

    def _print_report(self, m):
        print("\n" + "=" * 60)
        print("  BACKTEST REPORT — Nifty 50 Intraday (3-Confirmation Model)")
        print("=" * 60)
        print(f"  Total Trades         : {m['total_trades']}")
        print(f"  Wins / Losses        : {m['wins']} / {m['losses']}")
        print(f"  Win Rate             : {m['win_rate']}")
        print(f"  Avg Win              : Rs {m['avg_win_rs']:,.0f}")
        print(f"  Avg Loss             : Rs {m['avg_loss_rs']:,.0f}")
        print(f"  Profit Factor        : {m['profit_factor']}")
        print(f"  Max Consec. Losses   : {m['max_consecutive_losses']}")
        print(f"  Max Drawdown         : Rs {m['max_drawdown_rs']:,.0f}  ({m['max_drawdown_pct']})")
        print(f"  Net P&L              : Rs {m['net_pnl_rs']:,.0f}")
        print(f"  Final Capital        : Rs {m['final_capital_rs']:,.0f}")
        print(f"  Return               : {m['return_pct']}")
        print(f"  Sharpe Ratio         : {m['sharpe_ratio']}")
        print("=" * 60 + "\n")


# --------------------------------------------------------------------------- #
#  ENTRY POINT — works for both python -m and python file.py                  #
# --------------------------------------------------------------------------- #

def main():
    parser = argparse.ArgumentParser(
        description="Nifty 50 Intraday Backtester",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Use existing CSV
  python -m backtester.backtest --csv data/nifty_5m.csv --capital 50000

  # Auto-download via jugaad-data, then backtest (requires: pip install jugaad-data)
  python -m backtester.backtest --fetch --from 2025-01-01 --to 2026-03-27 --capital 50000
        """
    )
    # Data source — either --csv or --fetch
    src = parser.add_mutually_exclusive_group(required=True)
    src.add_argument("--csv",    help="Path to existing 5-min OHLCV CSV")
    src.add_argument("--fetch",  action="store_true",
                     help="Download data from NSE via jugaad-data (requires pip install jugaad-data)")

    # jugaad fetch options (only used with --fetch)
    parser.add_argument("--from", dest="from_date", default=None,
                        help="Fetch start date YYYY-MM-DD (required with --fetch)")
    parser.add_argument("--to",   dest="to_date",   default=None,
                        help="Fetch end date YYYY-MM-DD (required with --fetch)")

    # Backtest options
    parser.add_argument("--capital",  type=float, default=50_000)
    parser.add_argument("--risk",     type=float, default=0.03,  help="e.g. 0.03 = 3%%")
    parser.add_argument("--rr",       type=float, default=1.5,   help="Reward:Risk ratio")
    parser.add_argument("--output",   default="logs/backtest_results.csv")
    parser.add_argument("--min-bars", type=int,   default=30,    help="Indicator warmup bars")
    parser.add_argument("--debug",    action="store_true",       help="Print first 20 rows of loaded data")
    args = parser.parse_args()

    # ── Load data ─────────────────────────────────────────────────────────────
    if args.fetch:
        from backtester.data_fetcher import explain_intraday_options
        explain_intraday_options()
        print("ERROR: --fetch is not available for intraday backtest.")
        print("jugaad-data only provides daily bars, not 5-min intraday.")
        print("Use --csv with a TradingView export or Dhan paid API data.")
        sys.exit(1)
    else:
        df5 = load_csv(args.csv)

    if args.debug:
        print("\n-- First 20 rows of loaded data --")
        print(df5.head(20).to_string())
        print(f"\nIndex dtype  : {df5.index.dtype}")
        print(f"Index sample : {df5.index[:3].tolist()}")
        print(f"Columns      : {list(df5.columns)}\n")

    df15 = resample_to_15m(df5)

    bt = Backtester(
        df_5m=df5, df_15m=df15,
        initial_capital=args.capital,
        risk_pct=args.risk,
        rr_ratio=args.rr,
        output_csv=args.output,
        min_bars=args.min_bars,
    )
    bt.run()


if __name__ == "__main__":
    main()
