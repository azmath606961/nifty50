"""
Daily Backtester — Nifty 50
Works directly with the NSE daily CSV (one row per trading day).

Run:
    python -m backtester.backtest_daily --csv data/NIFTY_50-29-03-2025-to-29-03-2026.csv
    python  backtester/backtest_daily.py --csv data/NIFTY_50-29-03-2025-to-29-03-2026.csv

Strategy (daily swing, same risk rules as the intraday system):
    LONG  : EMA20 crosses above EMA50  AND  RSI > 50  AND  close > open (bull candle)
    SHORT : EMA20 crosses below EMA50  AND  RSI < 50  AND  close < open (bear candle)
    SL    : Low  of entry candle  (LONG)  /  High of entry candle (SHORT)
    Target: Entry + 1.5 x SL-distance
    Exit  : whichever comes first — SL hit, Target hit, or opposite EMA cross
"""

import argparse, csv, logging, os, sys
from datetime import date
import pandas as pd
import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from core.indicators import add_indicators

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)


# ── Loader ──────────────────────────────────────────────────────────────────

def load_nse_daily_csv(path: str) -> pd.DataFrame:
    df = pd.read_csv(path, encoding="utf-8-sig")
    df.columns = [c.strip() for c in df.columns]
    logger.info("Raw columns : %s", list(df.columns))

    date_col = next((c for c in df.columns if c.lower() == "date"), None)
    if not date_col:
        raise ValueError("No 'Date' column. Columns found: " + str(list(df.columns)))

    df[date_col] = pd.to_datetime(df[date_col], dayfirst=True)
    df = df.sort_values(date_col).set_index(date_col)

    # Normalize index to midnight (strips the fake 10:30 timestamp)
    df.index = df.index.normalize()
    df.index.name = "date"

    # Standardise OHLCV column names
    rename = {}
    for c in df.columns:
        cl = c.lower().strip()
        if cl == "open":                rename[c] = "open"
        elif cl == "high":              rename[c] = "high"
        elif cl == "low":               rename[c] = "low"
        elif cl in ("close", "ltp"):    rename[c] = "close"
        elif cl in ("volume", "vol"):   rename[c] = "volume"
    df = df.rename(columns=rename)

    missing = {"open", "high", "low", "close"} - set(df.columns)
    if missing:
        raise ValueError(f"Missing columns: {missing}  |  Have: {list(df.columns)}")

    if "volume" not in df.columns:
        df["volume"] = 1_000_000

    df = df[["open", "high", "low", "close", "volume"]]
    df = df.apply(pd.to_numeric, errors="coerce").dropna()

    logger.info("Loaded %d daily bars | %s → %s",
                len(df), df.index[0].date(), df.index[-1].date())
    return df


# ── Backtester ───────────────────────────────────────────────────────────────

class DailyBacktester:

    def __init__(
        self,
        df: pd.DataFrame,
        initial_capital: float = 50_000,
        risk_pct: float = 0.03,
        rr: float = 1.5,
        output_csv: str = "logs/backtest_daily_results.csv",
    ):
        self.df = df.copy()
        self.initial_capital = initial_capital
        self.capital = initial_capital
        self.risk_pct = risk_pct
        self.rr = rr
        self.output_csv = output_csv
        self.trades: list[dict] = []
        self.equity_curve: list[float] = [initial_capital]

    def run(self) -> dict:
        df = add_indicators(self.df, ema_fast=20, ema_slow=50, rsi_period=14)

        # State
        in_trade  = False
        direction = None
        entry     = sl = target = 0.0
        qty       = 0
        entry_date = None
        risk_amount = 0.0

        logger.info("=" * 60)
        logger.info("DAILY BACKTEST START | Capital=Rs %.0f | Bars=%d", self.initial_capital, len(df))
        logger.info("=" * 60)

        for i in range(1, len(df)):
            today   = df.iloc[i]
            prev    = df.iloc[i - 1]
            ts      = df.index[i]

            fast_above_now  = today["ema_fast"]  > today["ema_slow"]
            fast_above_prev = prev["ema_fast"]   > prev["ema_slow"]
            bull_cross = fast_above_now  and not fast_above_prev
            bear_cross = not fast_above_now and fast_above_prev

            # ── Check exit on open trades ─────────────────────────────────
            if in_trade:
                # Use today's candle to check SL / Target
                if direction == "LONG":
                    if today["low"] <= sl:
                        pnl = round((sl - entry) * qty, 2)
                        self._record("LOSS", pnl, entry_date, ts, direction,
                                     entry, sl, target, qty, risk_amount, "SL hit")
                        in_trade = False
                    elif today["high"] >= target:
                        pnl = round((target - entry) * qty, 2)
                        self._record("WIN", pnl, entry_date, ts, direction,
                                     entry, sl, target, qty, risk_amount, "Target hit")
                        in_trade = False
                    elif bear_cross:
                        pnl = round((today["close"] - entry) * qty, 2)
                        res = "WIN" if pnl > 0 else "LOSS" if pnl < 0 else "BE"
                        self._record(res, pnl, entry_date, ts, direction,
                                     entry, sl, target, qty, risk_amount, "EMA reversal exit")
                        in_trade = False

                elif direction == "SHORT":
                    if today["high"] >= sl:
                        pnl = round((entry - sl) * qty, 2)
                        self._record("LOSS", pnl, entry_date, ts, direction,
                                     entry, sl, target, qty, risk_amount, "SL hit")
                        in_trade = False
                    elif today["low"] <= target:
                        pnl = round((entry - target) * qty, 2)
                        self._record("WIN", pnl, entry_date, ts, direction,
                                     entry, sl, target, qty, risk_amount, "Target hit")
                        in_trade = False
                    elif bull_cross:
                        pnl = round((entry - today["close"]) * qty, 2)
                        res = "WIN" if pnl > 0 else "LOSS" if pnl < 0 else "BE"
                        self._record(res, pnl, entry_date, ts, direction,
                                     entry, sl, target, qty, risk_amount, "EMA reversal exit")
                        in_trade = False

            # ── Look for new entry (only when flat) ───────────────────────
            if not in_trade:
                bull_candle = today["close"] > today["open"]
                bear_candle = today["close"] < today["open"]

                if bull_cross and today["rsi"] > 50 and bull_candle:
                    direction   = "LONG"
                    entry       = today["close"]
                    sl          = today["low"]
                    sl_dist     = entry - sl
                    if sl_dist <= 0:
                        continue
                    risk_amount = self.capital * self.risk_pct
                    qty         = max(1, int(risk_amount / sl_dist))
                    target      = entry + sl_dist * self.rr
                    entry_date  = ts
                    in_trade    = True
                    logger.info("[%s] LONG  entry=%.2f  sl=%.2f  target=%.2f  qty=%d",
                                ts.date(), entry, sl, target, qty)

                elif bear_cross and today["rsi"] < 50 and bear_candle:
                    direction   = "SHORT"
                    entry       = today["close"]
                    sl          = today["high"]
                    sl_dist     = sl - entry
                    if sl_dist <= 0:
                        continue
                    risk_amount = self.capital * self.risk_pct
                    qty         = max(1, int(risk_amount / sl_dist))
                    target      = entry - sl_dist * self.rr
                    entry_date  = ts
                    in_trade    = True
                    logger.info("[%s] SHORT entry=%.2f  sl=%.2f  target=%.2f  qty=%d",
                                ts.date(), entry, sl, target, qty)

        # Force-close any open trade at end of data
        if in_trade:
            last = df.iloc[-1]
            pnl  = round((last["close"] - entry) * qty, 2) if direction == "LONG" \
                   else round((entry - last["close"]) * qty, 2)
            res  = "WIN" if pnl > 0 else "LOSS" if pnl < 0 else "BE"
            self._record(res, pnl, entry_date, df.index[-1], direction,
                         entry, sl, target, qty, risk_amount, "End of data")

        return self._compute_metrics()

    def _record(self, result, pnl, entry_date, exit_date, direction,
                entry, sl, target, qty, risk, note):
        self.capital += pnl
        self.equity_curve.append(self.capital)
        self.trades.append({
            "entry_date":    str(entry_date.date()),
            "exit_date":     str(exit_date.date()),
            "direction":     direction,
            "entry":         round(entry, 2),
            "sl":            round(sl, 2),
            "target":        round(target, 2),
            "qty":           qty,
            "risk_rs":       round(risk, 2),
            "result":        result,
            "pnl":           round(pnl, 2),
            "balance":       round(self.capital, 2),
            "growth_pct":    round((self.capital - self.initial_capital) / self.initial_capital * 100, 2),
            "note":          note,
        })
        logger.info("  -> %s | pnl=Rs %.0f | balance=Rs %.0f | %s",
                    result, pnl, self.capital, note)

    def _compute_metrics(self) -> dict:
        if not self.trades:
            logger.error("No trades generated.")
            return {"error": "No trades"}

        wins   = [t for t in self.trades if t["result"] == "WIN"]
        losses = [t for t in self.trades if t["result"] == "LOSS"]

        total_win  = sum(t["pnl"] for t in wins)
        total_loss = abs(sum(t["pnl"] for t in losses))
        win_rate   = len(wins) / len(self.trades)
        pf         = round(total_win / total_loss, 2) if total_loss else float("inf")

        equity  = pd.Series(self.equity_curve)
        max_dd  = round((equity.cummax() - equity).max(), 2)
        max_dd_pct = round(max_dd / self.initial_capital * 100, 2)

        pnl_s  = pd.Series([t["pnl"] for t in self.trades])
        sharpe = round((pnl_s.mean() / pnl_s.std()) * (252 ** 0.5), 2) if pnl_s.std() > 0 else 0

        net_pnl = self.capital - self.initial_capital
        m = {
            "total_trades":           len(self.trades),
            "wins":                   len(wins),
            "losses":                 len(losses),
            "win_rate":               f"{win_rate:.1%}",
            "avg_win_rs":             round(total_win / len(wins), 2) if wins else 0,
            "avg_loss_rs":            round(total_loss / len(losses), 2) if losses else 0,
            "profit_factor":          pf,
            "max_drawdown_rs":        max_dd,
            "max_drawdown_pct":       f"{max_dd_pct:.1f}%",
            "net_pnl_rs":             round(net_pnl, 2),
            "final_capital_rs":       round(self.capital, 2),
            "return_pct":             f"{net_pnl / self.initial_capital:.1%}",
            "sharpe_ratio":           sharpe,
        }
        self._save(m)
        self._print(m)
        return m

    def _save(self, metrics):
        out_dir = os.path.dirname(self.output_csv)
        if out_dir:
            os.makedirs(out_dir, exist_ok=True)
        with open(self.output_csv, "w", newline="") as f:
            w = csv.DictWriter(f, fieldnames=list(self.trades[0].keys()))
            w.writeheader(); w.writerows(self.trades)
        summary = self.output_csv.replace(".csv", "_summary.csv")
        with open(summary, "w", newline="") as f:
            w = csv.writer(f)
            w.writerow(["Metric", "Value"])
            for k, v in metrics.items(): w.writerow([k, v])
        logger.info("Trade log : %s", self.output_csv)
        logger.info("Summary   : %s", summary)

    def _print(self, m):
        print("\n" + "=" * 60)
        print("  DAILY BACKTEST REPORT — Nifty 50  (EMA20/50 Swing Strategy)")
        print("=" * 60)
        print(f"  Total Trades         : {m['total_trades']}")
        print(f"  Wins / Losses        : {m['wins']} / {m['losses']}")
        print(f"  Win Rate             : {m['win_rate']}")
        print(f"  Avg Win              : Rs {m['avg_win_rs']:>10,.2f}")
        print(f"  Avg Loss             : Rs {m['avg_loss_rs']:>10,.2f}")
        print(f"  Profit Factor        : {m['profit_factor']}")
        print(f"  Max Drawdown         : Rs {m['max_drawdown_rs']:>10,.2f}  ({m['max_drawdown_pct']})")
        print(f"  Net P&L              : Rs {m['net_pnl_rs']:>10,.2f}")
        print(f"  Final Capital        : Rs {m['final_capital_rs']:>10,.2f}")
        print(f"  Return               : {m['return_pct']}")
        print(f"  Sharpe Ratio         : {m['sharpe_ratio']}")
        print("=" * 60)
        print()


# ── CLI ──────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="Nifty 50 Daily Backtester",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Use your existing NSE CSV
  python -m backtester.backtest_daily --csv data/NIFTY_50-29-03-2025-to-29-03-2026.csv

  # Auto-download via jugaad-data, then backtest (requires: pip install jugaad-data)
  python -m backtester.backtest_daily --fetch --from 2025-01-01 --to 2026-03-27
        """
    )
    src = parser.add_mutually_exclusive_group(required=True)
    src.add_argument("--csv",   help="Path to existing daily OHLCV CSV")
    src.add_argument("--fetch", action="store_true",
                     help="Download daily data from NSE via jugaad-data")

    parser.add_argument("--from", dest="from_date", default=None,
                        help="Fetch start date YYYY-MM-DD (required with --fetch)")
    parser.add_argument("--to",   dest="to_date",   default=None,
                        help="Fetch end date YYYY-MM-DD (required with --fetch)")
    parser.add_argument("--capital", type=float, default=50_000)
    parser.add_argument("--risk",    type=float, default=0.03)
    parser.add_argument("--rr",      type=float, default=1.5)
    parser.add_argument("--output",  default="logs/backtest_daily_results.csv")
    args = parser.parse_args()

    if args.fetch:
        if not args.from_date or not args.to_date:
            parser.error("--fetch requires --from YYYY-MM-DD and --to YYYY-MM-DD")
        from backtester.data_fetcher import fetch_daily_jugaad, normalise_jugaad, save_csv
        from datetime import datetime
        from_date = datetime.strptime(args.from_date, "%Y-%m-%d").date()
        to_date   = datetime.strptime(args.to_date,   "%Y-%m-%d").date()
        out_path  = f"data/NIFTY50_daily_{args.from_date}_to_{args.to_date}.csv"
        os.makedirs("data", exist_ok=True)
        raw = fetch_daily_jugaad(from_date, to_date)
        df  = normalise_jugaad(raw, "daily")
        save_csv(df, out_path)
    else:
        df = load_nse_daily_csv(args.csv)

    bt = DailyBacktester(df, args.capital, args.risk, args.rr, args.output)
    bt.run()


if __name__ == "__main__":
    main()
