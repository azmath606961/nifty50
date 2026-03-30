"""
Data Fetcher — Nifty 50 OHLCV data for backtesting.

PRIORITY ORDER FOR DATA SOURCES
────────────────────────────────
1. jugaad-data  (daily EOD via NSEIndexHistory — free, no key)
2. NSE CSV      (manual download from nseindia.com)
3. Synthetic    (expand daily bars into realistic 5-min intraday — offline, always works)

WHY THERE IS NO JUGAAD INTRADAY
────────────────────────────────
jugaad-data has NO intraday (1-min / 5-min) endpoint.
index_df() / index_raw() fetch DAILY closing data from niftyindices.com.
True 5-min intraday data requires a paid feed (Dhan, Zerodha, Upstox) or
a TradingView manual export.  The --mode intraday flag below converts daily
bars into synthetic 5-min bars so the full intraday backtester can still run.

USAGE
─────
  # Use existing daily CSV (always works — offline)
  python -m backtester.data_fetcher --mode daily --csv data/NIFTY_50-29-03-2025-to-29-03-2026.csv

  # Generate synthetic 5-min bars from daily CSV (offline — always works)
  python -m backtester.data_fetcher --mode intraday --csv data/NIFTY_50-29-03-2025-to-29-03-2026.csv

  # Generate AND immediately backtest
  python -m backtester.data_fetcher --mode intraday --csv data/NIFTY_50-29-03-2025-to-29-03-2026.csv --backtest

  # Download fresh daily data via jugaad (needs internet + NSE accessible)
  python -m backtester.data_fetcher --mode daily --from 2025-01-01 --to 2026-03-27
"""

import argparse
import logging
import os
import sys
from datetime import date, datetime

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

os.makedirs("data", exist_ok=True)


# ─────────────────────────────────────────────────────────────────────────────
#  SECTION 1 — DAILY FETCHER VIA JUGAAD
# ─────────────────────────────────────────────────────────────────────────────

def fetch_daily_jugaad(from_date: date, to_date: date) -> pd.DataFrame:
    """
    Fetch daily Nifty 50 OHLCV from NSE via jugaad-data.
    Returns raw DataFrame with jugaad's original column names.
    Raises ImportError if jugaad not installed, ConnectionError if NSE unreachable.
    """
    try:
        from jugaad_data.nse import NSEIndexHistory
    except ImportError:
        raise ImportError(
            "jugaad-data not installed.\n"
            "Run:  pip install jugaad-data requests-cache"
        )

    logger.info("Fetching daily Nifty 50 from NSE via jugaad | %s -> %s", from_date, to_date)
    ih = NSEIndexHistory()

    try:
        raw = ih.index_raw(symbol="NIFTY 50", from_date=from_date, to_date=to_date)
    except Exception as e:
        raise ConnectionError(
            f"jugaad-data could not reach NSE: {e}\n"
            "Possible causes:\n"
            "  - NSE website temporarily down\n"
            "  - Your network blocks niftyindices.com / nseindia.com\n"
            "  - You are behind a corporate/ISP proxy\n"
            "Workaround: download the CSV manually from nseindia.com and use --csv"
        ) from e

    if not raw:
        raise ValueError("jugaad returned an empty response for the given date range.")

    df = pd.DataFrame(raw)
    logger.info("jugaad returned %d rows | columns: %s", len(df), list(df.columns))
    return df


def normalise_jugaad(df: pd.DataFrame) -> pd.DataFrame:
    """
    Normalise jugaad NSEIndexHistory.index_raw() output to standard OHLCV.

    jugaad v0.28 NSEIndexHistory.index_raw() returns records with keys:
        INDEX_NAME, OPEN_INDEX_VALUE, HIGH_INDEX_VALUE, LOW_INDEX_VALUE,
        CLOSING_INDEX_VALUE, POINTS_CHANGE, CHANGE_PERCENT, VOLUME,
        TURNOVER_RS_CR, PE_RATIO, PB_RATIO, DIV_YIELD, TIMESTAMP

    Bug B5 fix: the old code mapped CH_OPENING_PRICE / CH_TRADE_HIGH_PRICE
    which belong to the equity history endpoint — completely wrong for index data.
    """
    df = df.copy()
    df.columns = [str(c).strip().lower() for c in df.columns]
    logger.info("Normalising jugaad columns: %s", list(df.columns))

    # Map jugaad v0.28 NSEIndexHistory columns (and older fallback names)
    col_map = {
        # jugaad v0.28 NSEIndexHistory.index_raw (verified)
        "open_index_value":    "open",
        "high_index_value":    "high",
        "low_index_value":     "low",
        "closing_index_value": "close",
        "volume":              "volume",
        "timestamp":           "datetime",
        # older jugaad equity-style columns (wrong for index but kept as fallback)
        "ch_opening_price":    "open",
        "ch_trade_high_price": "high",
        "ch_trade_low_price":  "low",
        "ch_closing_price":    "close",
        "ch_tot_trd_qnty":     "volume",
        "ch_timestamp":        "datetime",
        # generic / already-normalised
        "open":       "open",
        "high":       "high",
        "low":        "low",
        "close":      "close",
        "date":       "datetime",
        "ltp":        "close",
        "tottrdqty":  "volume",
        # alternate date column names seen in some jugaad versions
        "index_date": "datetime",
        "tradeddate": "datetime",
        "ind_date":   "datetime",
    }

    rename = {c: col_map[c] for c in df.columns if c in col_map}
    df = df.rename(columns=rename)

    # Build datetime index
    if "datetime" not in df.columns:
        raise ValueError(
            "Cannot find a date column in jugaad output.\n"
            f"Available columns: {list(df.columns)}\n"
            "jugaad-data may have changed its column names. Use --csv instead."
        )

    df["datetime"] = pd.to_datetime(df["datetime"], dayfirst=True, errors="coerce")
    df = df.dropna(subset=["datetime"]).set_index("datetime")

    if df.index.tz is not None:
        df.index = df.index.tz_convert("Asia/Kolkata").tz_localize(None)

    # Validate required OHLC columns
    required = {"open", "high", "low", "close"}
    missing = required - set(df.columns)
    if missing:
        raise ValueError(
            f"Normalisation failed — missing columns: {missing}\n"
            f"Columns after rename: {list(df.columns)}\n"
            "jugaad-data column names may have changed. Use --csv instead."
        )

    if "volume" not in df.columns:
        df["volume"] = 0

    df = df[["open", "high", "low", "close", "volume"]]
    df = df.apply(pd.to_numeric, errors="coerce").dropna().sort_index()
    logger.info("Normalised: %d daily bars | %s -> %s", len(df), df.index[0], df.index[-1])
    return df


# ─────────────────────────────────────────────────────────────────────────────
#  SECTION 2 — NSE CSV LOADER (manual download — always works offline)
# ─────────────────────────────────────────────────────────────────────────────

def _detect_dayfirst(sample: str) -> bool:
    """
    Detect whether a date string is day-first (DD/MM/YYYY) or year-first (YYYY-MM-DD).

    Rules:
      - If the first numeric segment before '/' or '-' has 4 digits → YYYY-first (ISO).
        Examples: "2024-04-15 09:15:00"  "2024-04-15"
      - If it has 1 or 2 digits → day-first (DD/MM/YYYY or DD-Mon-YYYY).
        Examples: "27/03/2026 10:30"  "15/04/2024"  "01-Jan-2024"

    Why this matters:
      pandas uses the FIRST row to infer a format for the whole column when
      dayfirst=True is set.  For ISO dates like "2024-04-01", pandas infers
      format "%Y-%d-%m %H:%M:%S" (year-DAY-MONTH).  This works fine while
      the day value is ≤ 12 (looks like a valid month), but raises a
      ValueError the first time it encounters day > 12 — e.g. "2024-04-15"
      at row 681 of a Dhan 5-min CSV.
    """
    import re
    m = re.match(r"^(\d+)[/\-]", str(sample).strip())
    if m:
        return len(m.group(1)) <= 2   # 1-2 digit prefix → DD/MM style
    return False                       # default to ISO (year-first)


def load_nse_csv(path: str) -> pd.DataFrame:
    """
    Load an OHLCV CSV from any of these sources:
      - Dhan API fetcher output : datetime column, YYYY-MM-DD HH:MM:SS (ISO)
      - NSE bhavcopy            : Date column, DD/MM/YYYY HH:MM
      - TradingView export      : time (unix) or YYYY-MM-DD
      - BOM in UTF-8 files      : encoding='utf-8-sig' strips it automatically

    Date format is auto-detected from the first data row so that both
    Dhan 5-min CSVs (ISO) and NSE bhavcopy (DD/MM/YYYY) parse correctly
    without raising ValueError at row N when day > 12.
    """
    df = pd.read_csv(path, encoding="utf-8-sig")
    df.columns = [c.strip() for c in df.columns]
    logger.info("CSV raw columns: %s", list(df.columns))

    # Find the date column (case-insensitive search)
    date_col = next(
        (c for c in df.columns if c.lower() in ("date", "datetime", "timestamp")),
        None
    )
    if not date_col:
        raise ValueError(f"No date column found. Columns: {list(df.columns)}")

    # Auto-detect format from first non-null value
    first_val  = df[date_col].dropna().iloc[0]
    dayfirst   = _detect_dayfirst(str(first_val))
    logger.info(
        "Date format detected: '%s' → dayfirst=%s",
        first_val, dayfirst,
    )

    # Use format='ISO8601' for year-first strings — avoids pandas inferring
    # the wrong format from row 1 and then crashing on day>12 rows later.
    if not dayfirst:
        df[date_col] = pd.to_datetime(df[date_col], format="ISO8601", errors="coerce")
    else:
        df[date_col] = pd.to_datetime(df[date_col], dayfirst=True, errors="coerce")

    df = df.dropna(subset=[date_col])
    df = df.sort_values(date_col).set_index(date_col)
    # .normalize() strips the fake 10:30 time suffix NSE adds to bhavcopy dates
    df.index = df.index.normalize()
    df.index.name = "date"

    # Normalise column names to lowercase open/high/low/close/volume
    rename = {}
    for c in df.columns:
        cl = c.lower().strip()
        if cl == "open":                   rename[c] = "open"
        elif cl == "high":                 rename[c] = "high"
        elif cl == "low":                  rename[c] = "low"
        elif cl in ("close", "ltp"):       rename[c] = "close"
        elif cl in ("volume", "vol", "v"): rename[c] = "volume"
    df = df.rename(columns=rename)

    missing = {"open", "high", "low", "close"} - set(df.columns)
    if missing:
        raise ValueError(f"Missing OHLC columns: {missing}  |  Have: {list(df.columns)}")

    if "volume" not in df.columns:
        df["volume"] = 1_000_000   # placeholder so indicators don't crash

    df = df[["open", "high", "low", "close", "volume"]]
    df = df.apply(pd.to_numeric, errors="coerce").dropna()
    logger.info("Loaded %d daily bars from CSV | %s -> %s",
                len(df), df.index[0].date(), df.index[-1].date())
    return df


# ─────────────────────────────────────────────────────────────────────────────
#  SECTION 3 — SYNTHETIC 5-MIN GENERATOR
# ─────────────────────────────────────────────────────────────────────────────
#
#  This is the key fix that makes the intraday backtester work without a
#  paid data feed.  Each daily bar is expanded into 40 realistic 5-min bars
#  across the two prime trading sessions:
#    Session 1: 09:30–11:30  (25 bars)
#    Session 2: 13:30–14:45  (15 bars)
#
#  The Brownian-motion path is seeded from the date so results are
#  reproducible.  Daily High and Low are always respected.
# ─────────────────────────────────────────────────────────────────────────────

# (session_start_hour, session_start_minute, num_5min_bars)
_SESSIONS = [
    (9,  30, 25),   # 09:30 – 11:30
    (13, 30, 15),   # 13:30 – 14:45
]
_TOTAL_BARS = sum(n for _, _, n in _SESSIONS)   # = 40


def _generate_day_5m(row: pd.Series, seed: int) -> list:
    """
    Expand a single daily OHLCV row into a list of 5-min bar dicts.
    Uses Geometric Brownian Motion constrained to daily High and Low.
    """
    rng = np.random.default_rng(seed)

    o = float(row["open"])
    h = float(row["high"])
    l = float(row["low"])
    c = float(row["close"])
    v = float(row["volume"])
    dt = row.name   # Timestamp (date only after .normalize())

    n = _TOTAL_BARS

    # Per-bar volatility proportional to daily range
    daily_range = max(h - l, 1.0)
    bar_sigma   = daily_range / (6.0 * np.sqrt(n))

    # Random walk
    steps = rng.normal(0, bar_sigma, n)
    path  = np.cumsum(steps)

    # Linear drift from open to close
    drift = np.linspace(0, c - o, n)
    path  = o + drift + (path - path[0])

    # Rescale so path min == daily Low and path max == daily High
    cur_min = path.min()
    cur_max = path.max()
    if cur_max > cur_min:
        path = (path - cur_min) / (cur_max - cur_min) * (h - l) + l
    else:
        path = np.full(n, (h + l) / 2.0)

    # Pin endpoints
    path[0]  = o
    path[-1] = c

    bars = []
    idx  = 0

    for sh, sm, n_bars in _SESSIONS:
        for b in range(n_bars):
            if idx >= n:
                break

            p0    = path[idx]
            p1    = path[min(idx + 1, n - 1)]
            bar_o = p0
            bar_c = p1

            # Small random wicks
            wick_h = abs(rng.normal(0, bar_sigma * 0.5))
            wick_l = abs(rng.normal(0, bar_sigma * 0.5))
            bar_h  = min(max(bar_o, bar_c) + wick_h, h)
            bar_l  = max(min(bar_o, bar_c) - wick_l, l)

            # U-shaped volume profile (high at session open/close, low in middle)
            prog       = b / max(n_bars - 1, 1)
            vol_weight = 0.5 + 1.5 * (2 * abs(prog - 0.5)) + abs(rng.normal(0, 0.3))
            bar_vol    = max(0, int(v / n * vol_weight))

            bar_ts = pd.Timestamp(dt.year, dt.month, dt.day, sh, sm) + \
                     pd.Timedelta(minutes=b * 5)

            bars.append({
                "datetime": bar_ts,
                "open":     round(bar_o, 2),
                "high":     round(bar_h, 2),
                "low":      round(bar_l, 2),
                "close":    round(bar_c, 2),
                "volume":   bar_vol,
            })
            idx += 1

    return bars


def generate_intraday_from_daily(df_daily: pd.DataFrame) -> pd.DataFrame:
    """
    Convert a daily OHLCV DataFrame into synthetic 5-min intraday bars.
    Returns a DataFrame with DatetimeIndex at 5-min frequency.
    """
    logger.info("Generating synthetic 5-min bars from %d daily bars ...", len(df_daily))

    all_bars = []
    for i, (ts, row) in enumerate(df_daily.iterrows()):
        seed = int(ts.timestamp()) + i
        all_bars.extend(_generate_day_5m(row, seed))

    df = pd.DataFrame(all_bars).set_index("datetime")
    df.index.name = "datetime"
    df = df.sort_index()

    logger.info("Generated %d synthetic 5-min bars | %s -> %s",
                len(df), df.index[0], df.index[-1])
    return df


# ─────────────────────────────────────────────────────────────────────────────
#  SECTION 4 — SAVE HELPER
# ─────────────────────────────────────────────────────────────────────────────

def save_csv(df: pd.DataFrame, path: str):
    df.to_csv(path)
    logger.info("Saved %d rows -> %s", len(df), path)
    print(f"\nData saved to: {path}")
    print(f"Rows         : {len(df)}")
    print(f"Date range   : {df.index[0]}  ->  {df.index[-1]}")
    print(f"Columns      : {list(df.columns)}")
    if any(x in path for x in ("5m", "intraday", "synthetic")):
        print(f"\nRun intraday backtest:")
        print(f"  python -m backtester.backtest --csv {path} --capital 50000")
    else:
        print(f"\nRun daily backtest:")
        print(f"  python -m backtester.backtest_daily --csv {path} --capital 50000")


# ─────────────────────────────────────────────────────────────────────────────
#  SECTION 5 — CLI
# ─────────────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="Nifty 50 data fetcher and 5-min synthetic generator",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
EXAMPLES
  # Use existing daily CSV (offline — always works)
  python -m backtester.data_fetcher --mode daily --csv data/NIFTY_50-29-03-2025-to-29-03-2026.csv

  # Generate synthetic 5-min bars from daily CSV
  python -m backtester.data_fetcher --mode intraday --csv data/NIFTY_50-29-03-2025-to-29-03-2026.csv

  # Generate 5-min bars AND immediately run the intraday backtest
  python -m backtester.data_fetcher --mode intraday --csv data/NIFTY_50-29-03-2025-to-29-03-2026.csv --backtest

  # Download fresh daily data via jugaad (needs internet)
  python -m backtester.data_fetcher --mode daily --from 2025-01-01 --to 2026-03-27
        """
    )
    parser.add_argument(
        "--mode", choices=["intraday", "daily"], default="intraday",
        help="intraday=generate synthetic 5-min bars | daily=load/download EOD bars"
    )
    src = parser.add_mutually_exclusive_group()
    src.add_argument(
        "--from", dest="from_date",
        help="Fetch start date YYYY-MM-DD (downloads via jugaad, requires internet)"
    )
    src.add_argument(
        "--csv", dest="csv_path",
        help="Path to existing daily OHLCV CSV (offline, always works)"
    )
    parser.add_argument("--to",  dest="to_date",  help="Fetch end date YYYY-MM-DD")
    parser.add_argument("--out", dest="output",   default=None, help="Output CSV path")
    parser.add_argument(
        "--backtest", action="store_true",
        help="After generating data, immediately run the backtest"
    )
    args = parser.parse_args()

    # ── Obtain daily data ────────────────────────────────────────────────────
    if args.csv_path:
        df_daily = load_nse_csv(args.csv_path)

    elif args.from_date:
        if not args.to_date:
            parser.error("--from requires --to")
        from_date = datetime.strptime(args.from_date, "%Y-%m-%d").date()
        to_date   = datetime.strptime(args.to_date,   "%Y-%m-%d").date()
        try:
            raw      = fetch_daily_jugaad(from_date, to_date)
            df_daily = normalise_jugaad(raw)
        except (ConnectionError, ImportError) as e:
            print(f"\nERROR: {e}")
            print("\nFallback — download manually:")
            print("  1. Go to https://www.nseindia.com/reports-indices-historical-data")
            print("  2. Select NIFTY 50, choose date range, click Download")
            print("  3. Run: python -m backtester.data_fetcher --mode intraday --csv <file>")
            sys.exit(1)

    else:
        # Auto-find any CSV in data/
        candidates = [f for f in os.listdir("data") if f.endswith(".csv")]
        if not candidates:
            parser.error("Specify --csv <path> or --from <date> --to <date>")
        chosen = candidates[0]
        print(f"No source specified — using: data/{chosen}")
        df_daily = load_nse_csv(f"data/{chosen}")

    # ── Generate output ──────────────────────────────────────────────────────
    start = df_daily.index[0].date()
    end   = df_daily.index[-1].date()

    if args.mode == "daily":
        out_path = args.output or f"data/NIFTY50_daily_{start}_to_{end}.csv"
        save_csv(df_daily, out_path)
        if args.backtest:
            import subprocess
            subprocess.run(
                [sys.executable, "-m", "backtester.backtest_daily",
                 "--csv", out_path, "--capital", "50000"], check=True
            )

    else:   # intraday — generate synthetic 5-min bars
        df_5m    = generate_intraday_from_daily(df_daily)
        out_path = args.output or f"data/NIFTY50_5m_synthetic_{start}_to_{end}.csv"
        save_csv(df_5m, out_path)
        if args.backtest:
            import subprocess
            subprocess.run(
                [sys.executable, "-m", "backtester.backtest",
                 "--csv", out_path, "--capital", "50000"], check=True
            )


if __name__ == "__main__":
    main()