"""
Data Fetcher — downloads Nifty 50 OHLCV data via jugaad-data (free, no API key).
Saves to data/ folder as CSV, ready for both backtester files.

Install:  pip install jugaad-data requests-cache
Run:
    # Fetch 1 year of 5-min intraday data (for backtest.py)
    python -m backtester.data_fetcher --mode intraday --from 2025-01-01 --to 2026-03-27

    # Fetch daily data (for backtest_daily.py)
    python -m backtester.data_fetcher --mode daily --from 2025-01-01 --to 2026-03-27
"""

import argparse
import logging
import os
import sys
from datetime import date, datetime, timedelta

import pandas as pd

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

os.makedirs("data", exist_ok=True)


# --------------------------------------------------------------------------- #
#  JUGAAD FETCHERS                                                             #
# --------------------------------------------------------------------------- #

def fetch_intraday_jugaad(from_date: date, to_date: date, interval: int = 5) -> pd.DataFrame:
    """
    Fetch minute-level Nifty 50 data using jugaad-data.
    interval: 1 or 5 (minutes)
    Note: jugaad-data fetches from NSE directly — works for recent ~1-2 years.
    """
    try:
        from jugaad_data.nse import NSELive
    except ImportError:
        raise ImportError(
            "jugaad-data not installed.\n"
            "Run: pip install jugaad-data requests-cache"
        )

    try:
        # jugaad-data nse_df fetches index intraday data
        from jugaad_data.nse import index_df as nse_index_df
        logger.info("Fetching %d-min Nifty 50 data from %s to %s ...", interval, from_date, to_date)

        frames = []
        current = from_date
        # Fetch week by week (NSE rate limits large requests)
        while current <= to_date:
            week_end = min(current + timedelta(days=6), to_date)
            try:
                df = nse_index_df(
                    symbol="NIFTY 50",
                    from_date=current,
                    to_date=week_end,
                )
                if df is not None and len(df) > 0:
                    frames.append(df)
                    logger.info("  Fetched %d rows for %s → %s", len(df), current, week_end)
            except Exception as e:
                logger.warning("  Week %s → %s failed: %s", current, week_end, e)
            current = week_end + timedelta(days=1)

        if not frames:
            raise ValueError("No data returned from jugaad-data for the given date range.")

        df = pd.concat(frames).drop_duplicates().sort_index()
        return df

    except Exception as e:
        logger.error("jugaad intraday fetch failed: %s", e)
        raise


def fetch_daily_jugaad(from_date: date, to_date: date) -> pd.DataFrame:
    """
    Fetch daily Nifty 50 OHLCV using jugaad-data.
    """
    try:
        from jugaad_data.nse import index_df as nse_index_df
    except ImportError:
        raise ImportError("Run: pip install jugaad-data requests-cache")

    logger.info("Fetching daily Nifty 50 data from %s to %s ...", from_date, to_date)
    df = nse_index_df(symbol="NIFTY 50", from_date=from_date, to_date=to_date)
    if df is None or len(df) == 0:
        raise ValueError("No data returned.")
    return df.sort_index()


def normalise_jugaad(df: pd.DataFrame, mode: str) -> pd.DataFrame:
    """
    Normalise jugaad-data output columns to standard open/high/low/close/volume.
    jugaad returns columns like: CH_OPENING_PRICE, CH_TRADE_HIGH_PRICE, etc.
    """
    df.columns = [c.strip().lower() for c in df.columns]
    logger.info("Raw jugaad columns: %s", list(df.columns))

    # jugaad-data column name mappings (they change across versions)
    col_map = {
        # jugaad v2 style
        "ch_opening_price":    "open",
        "ch_trade_high_price": "high",
        "ch_trade_low_price":  "low",
        "ch_closing_price":    "close",
        "ch_tot_trd_qnty":     "volume",
        "ch_timestamp":        "datetime",
        # jugaad v1 / alternate style
        "open":    "open",
        "high":    "high",
        "low":     "low",
        "close":   "close",
        "volume":  "volume",
        "date":    "datetime",
        "time":    "time",
        # sometimes returned as these
        "ltp":     "close",
        "tottrdqty": "volume",
    }

    rename = {c: col_map[c] for c in df.columns if c in col_map}
    df = df.rename(columns=rename)

    # If separate date + time, combine
    if "datetime" not in df.columns and "date" in df.columns and "time" in df.columns:
        df["datetime"] = pd.to_datetime(df["date"].astype(str) + " " + df["time"].astype(str))
    elif "datetime" not in df.columns and "date" in df.columns:
        df["datetime"] = pd.to_datetime(df["date"])

    if "datetime" in df.columns and not isinstance(df.index, pd.DatetimeIndex):
        df = df.set_index("datetime")

    if df.index.tz is not None:
        df.index = df.index.tz_convert("Asia/Kolkata").tz_localize(None)

    required = {"open", "high", "low", "close"}
    missing = required - set(df.columns)
    if missing:
        raise ValueError(
            f"Normalisation failed. Missing: {missing}\n"
            f"Columns after rename: {list(df.columns)}\n"
            "jugaad-data may have changed its column names. "
            "Please open an issue or use --csv with a manual download."
        )

    if "volume" not in df.columns:
        df["volume"] = 0

    df = df[["open", "high", "low", "close", "volume"]]
    df = df.apply(pd.to_numeric, errors="coerce").dropna().sort_index()
    return df


# --------------------------------------------------------------------------- #
#  SAVE                                                                        #
# --------------------------------------------------------------------------- #

def save_csv(df: pd.DataFrame, path: str):
    df.to_csv(path)
    logger.info("Saved %d rows → %s", len(df), path)
    print(f"\nData saved to: {path}")
    print(f"Rows: {len(df)}")
    print(f"Date range: {df.index[0]}  →  {df.index[-1]}")
    print(f"Columns: {list(df.columns)}")
    print(f"\nNow run the backtest:")
    if "5m" in path or "intraday" in path:
        print(f"  python -m backtester.backtest --csv {path} --capital 50000")
    else:
        print(f"  python -m backtester.backtest_daily --csv {path} --capital 50000")


# --------------------------------------------------------------------------- #
#  CLI                                                                         #
# --------------------------------------------------------------------------- #

def main():
    parser = argparse.ArgumentParser(
        description="Download Nifty 50 OHLCV data via jugaad-data",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Fetch 1 year of 5-min intraday (for intraday backtester)
  python -m backtester.data_fetcher --mode intraday --from 2025-01-01 --to 2026-03-27

  # Fetch daily data (for daily backtester)
  python -m backtester.data_fetcher --mode daily --from 2025-01-01 --to 2026-03-27

  # Custom output path
  python -m backtester.data_fetcher --mode intraday --from 2025-01-01 --to 2026-03-27 --out data/my_nifty.csv
        """
    )
    parser.add_argument("--mode",   choices=["intraday", "daily"], default="intraday",
                        help="intraday = 5-min bars | daily = EOD bars")
    parser.add_argument("--from",   dest="from_date", required=True,
                        help="Start date YYYY-MM-DD")
    parser.add_argument("--to",     dest="to_date",   required=True,
                        help="End date YYYY-MM-DD")
    parser.add_argument("--out",    dest="output",    default=None,
                        help="Output CSV path (auto-named if not set)")
    parser.add_argument("--interval", type=int, default=5,
                        help="Bar interval in minutes for intraday (default: 5)")
    args = parser.parse_args()

    from_date = datetime.strptime(args.from_date, "%Y-%m-%d").date()
    to_date   = datetime.strptime(args.to_date,   "%Y-%m-%d").date()

    if args.output:
        out_path = args.output
    elif args.mode == "intraday":
        out_path = f"data/NIFTY50_{args.interval}m_{args.from_date}_to_{args.to_date}.csv"
    else:
        out_path = f"data/NIFTY50_daily_{args.from_date}_to_{args.to_date}.csv"

    os.makedirs("data", exist_ok=True)

    try:
        if args.mode == "intraday":
            raw = fetch_intraday_jugaad(from_date, to_date, args.interval)
        else:
            raw = fetch_daily_jugaad(from_date, to_date)

        df = normalise_jugaad(raw, args.mode)
        save_csv(df, out_path)

    except ImportError as e:
        print(f"\nERROR: {e}")
        sys.exit(1)
    except Exception as e:
        logger.error("Fetch failed: %s", e)
        print(f"\nFetch failed: {e}")
        print("\nFallback options:")
        print("  1. TradingView: open Nifty 5-min chart → right-click → 'Download chart data'")
        print("  2. Dhan API:    https://dhanhq.co/docs/v2/historical/")
        print("  3. NSE:         https://www.nseindia.com/all-reports (bhavcopy)")
        sys.exit(1)


if __name__ == "__main__":
    main()
