# 🏦 Nifty 50 Intraday Trading Bot
### EMA Crossover + RSI + VWAP + Volume — 3-Confirmation Model · Dhan Broker API

---

## 📁 Project Structure

```
nifty50/
├── config.py                        ← Credentials, capital, risk, timeframes
├── bot.py                           ← 🤖 Live trading bot (paper-safe)
├── requirements.txt
│
├── core/
│   ├── dhan_client.py               ← Dhan SDK wrapper (order placement, positions)
│   ├── dhan_data_fetcher.py         ← ✨ NEW: Dhan API raw 5-min candle fetcher (2 years)
│   ├── dhan_options_fetcher.py      ← ✨ NEW: Options strike-wise 5-min candle fetcher
│   ├── indicators.py                ← EMA, VWAP, RSI, Volume (exact spec)
│   └── risk_manager.py             ← 13-gate validation, position sizing, daily limits
│
├── strategies/
│   └── ema_crossover.py             ← Signal generator (3-confirmation model)
│
├── backtester/
│   ├── backtest.py                  ← Intraday walk-forward backtester
│   ├── backtest_daily.py            ← Daily OHLCV backtester
│   ├── data_fetcher.py              ← 🔧 FIXED: Date parsing for Dhan + NSE CSV formats
│   └── pipeline.py                  ← ✨ NEW: Fast vectorised pipeline (walk-forward + optimise)
│
├── ema_crossover_backtest.py        ← ✨ NEW: Standalone EMA swing backtest (no ext. libs)
│
├── utils/
│   └── trade_logger.py              ← CSV trade log (mirrors Excel Trade Log sheet)
│
├── tradingview/
│   ├── nifty50_strategy.pine        ← Pine Script v5 strategy (all 13 gates)
│   └── nifty50_dashboard.pine       ← RSI panel, volume bars, gate score 0–7
│
├── data/                            ← OHLCV CSVs saved here
├── logs/                            ← Trade logs, backtest results
└── reports/                         ← Walk-forward and optimisation CSVs
```

---

## ⚡ Quick Start

### 1. Install dependencies
```bash
pip install -r requirements.txt
```

### 2. Add your Dhan credentials
Edit `config.py`:
```python
DHAN_CLIENT_ID    = "your_client_id"
DHAN_ACCESS_TOKEN = "your_access_token"   # expires every 24 hours
```
Get yours from: **web.dhan.co → My Profile → Access DhanHQ APIs**

### 3. Run paper trade mode (safe — no real orders placed)
```bash
python bot.py --phase paper
```

### 4. Run half-size live (Days 31–60 per 90-day roadmap)
```bash
python bot.py --phase half
```

### 5. Full live trading (Days 61–90)
```bash
python bot.py --phase full
```

---

## 📥 Fetching Historical Data

### Nifty 50 Index — 5-min candles (2 years)

Requires an active **Dhan Data API subscription** (₹499/month).

```bash
python core/dhan_data_fetcher.py
```

Or import directly:
```python
from core.dhan_data_fetcher import fetch_nifty50, fetch_equity

# Nifty 50 index — saves to data/NIFTY50_5min_2yr.csv
df = fetch_nifty50()

# Any NSE stock — saves to data/RELIANCE_5min_2yr.csv
df = fetch_equity(security_id="2885", symbol="RELIANCE")
```

**How it works:**
- Fetches from `POST /v2/charts/intraday` in chunks of 75 days (API limit: 90 days/request)
- 2 years = ~10 chunks fetched automatically
- **Incremental updates** — re-running only fetches the missing gap since the last saved timestamp
- Saves as `data/{SYMBOL}_5min_2yr.csv` with IST timestamps (no timezone suffix)
- Timestamps from Dhan are Unix epoch (seconds) → converted to `YYYY-MM-DD HH:MM:SS` IST

**Common issue — token expired:**
```
ERROR: Authentication failed (HTTP 401)
```
Dhan tokens expire every 24 hours. Regenerate at web.dhan.co and update `config.py`.

---

## 📊 Options Chain — Strike-wise 5-Min Candles

> ⚠️ **Not yet run in production** — code is complete and unit-tested, pending live execution.

Fetches 5-min OHLCV + IV + OI data for multiple Nifty options strikes using Dhan's
rolling/expired options endpoint (`POST /v2/charts/rollingoption`).

```python
from core.dhan_options_fetcher import fetch_options_chain_candles

results = fetch_options_chain_candles(
    underlying_id = "13",                               # Nifty 50
    symbol        = "NIFTY50",
    strikes       = ["ATM-2", "ATM-1", "ATM", "ATM+1", "ATM+2"],
    option_types  = ["CALL", "PUT"],
    expiry_flag   = "WEEK",                             # or "MONTH"
    expiry_code   = 0,                                  # 0=nearest, 1=next, 2=far
    lookback_days = 90,
    interval      = "5",
)

# Access individual strikes
atm_call = results["CALL_ATM"]    # DataFrame: open, high, low, close, volume, iv, oi, spot
atm_put  = results["PUT_ATM"]
```

**Saved automatically as:**
```
data/NIFTY50_5min_WEEK_CE_ATM.csv
data/NIFTY50_5min_WEEK_PE_ATM.csv
data/NIFTY50_5min_WEEK_CE_ATMp1.csv    ← ATM+1
data/NIFTY50_5min_WEEK_PE_ATMm2.csv    ← ATM-2
```

**API call estimates — plan before running:**

| Strikes | Types | Lookback | API calls | Est. time |
|---------|-------|----------|-----------|-----------|
| ATM±2   | CE+PE | 90 days  | 40        | ~40 sec   |
| ATM±5   | CE+PE | 1 year   | 308       | ~5 min    |
| ATM±5   | CE+PE | 2 years  | 594       | ~10 min   |
| ATM±10  | CE+PE | 1 year   | 588       | ~10 min   |

**Key differences from the index fetcher:**

| | `dhan_data_fetcher.py` | `dhan_options_fetcher.py` |
|---|---|---|
| Endpoint | `/v2/charts/intraday` | `/v2/charts/rollingoption` |
| Max days/request | 90 | **30** (stricter) |
| Identified by | `securityId` (fixed) | `strike` offset from ATM |
| Extra fields | — | IV, OI, spot price |
| Expired contracts | Yes | Yes, up to 5 years |
| All strikes at once | N/A | No — one strike per request |

---

## 📉 Backtesting

### Option A — Full Pipeline (recommended)

The pipeline backtester supports walk-forward validation and parameter optimisation.
It runs the complete 13-gate strategy with EMA + RSI + VWAP + Volume.

**With real Dhan 5-min data (best results):**
```bash
python -m backtester.pipeline \
  --csv data/NIFTY50_5min_2yr.csv \
  --bar-type intraday \
  --walkforward 5 \
  --optimise
```

**With yfinance daily data (synthetic 5-min, free):**
```bash
python -m backtester.pipeline \
  --source yfinance \
  --from 2019-01-01 \
  --to 2024-12-31 \
  --bar-type daily \
  --walkforward 5 \
  --optimise
```

**`--bar-type` flag — always set this explicitly:**

| Flag | Use when | What happens |
|------|----------|--------------|
| `--bar-type intraday` | CSV is real 5-min data from Dhan | Uses candles directly — no synthetic generation |
| `--bar-type daily` | CSV is daily OHLCV (yfinance, NSE bhavcopy) | Generates synthetic 5-min bars via Brownian motion |
| `--bar-type auto` | Not sure (default) | Detects from rows-per-day automatically |

> Always use `--bar-type intraday` with data from `dhan_data_fetcher.py`.
> Synthetic bars (`--bar-type daily`) are only suitable for strategy logic testing —
> not for realistic P&L estimation.

**All pipeline flags:**
```
--csv PATH          Path to local CSV file
--source yfinance   Download fresh data from Yahoo Finance
--bar-type          intraday | daily | auto  (default: auto)
--from DATE         Start date  (default: 2019-01-01)
--to DATE           End date    (default: today)
--capital FLOAT     Starting capital  (default: 50000)
--risk FLOAT        Risk per trade as decimal  (default: 0.03)
--commission FLOAT  Flat fee per trade in ₹  (default: 20)
--slippage FLOAT    Slippage in index points  (default: 2)
--ema-fast INT      Fast EMA period  (default: 20)
--ema-slow INT      Slow EMA period  (default: 50)
--rsi-period INT    RSI period  (default: 14)
--walkforward INT   Number of walk-forward windows  (default: 0)
--optimise          Run 12-combo parameter grid search
--output PATH       Trade log CSV output path
--prefix STR        Prefix for report filenames
```

**Outputs:**
```
logs/backtest_results.csv           ← Per-trade log
logs/backtest_results_summary.csv   ← Key metrics
logs/backtest_results_equity.csv    ← Equity curve + drawdown %
reports/{prefix}_walkforward.csv    ← Walk-forward window results
reports/{prefix}_optimise.csv       ← Top parameter combinations by Sharpe
```

**Performance:** Fully vectorised — indicators computed once before the main loop,
15-min structure mapped via `merge_asof`, numpy arrays for O(1) access during
trade simulation. Benchmarked at ~4.6 seconds for 1 year of 5-min data including
3 walk-forward windows + 12 optimisation combinations.

---

### Option B — EMA Crossover Standalone Backtest

> ⚠️ **Not yet run with real Dhan data** — code complete and tested with synthetic data.

A simpler standalone swing backtester — EMA 20/50 crossover on daily OHLCV.
Uses only `pandas`, `numpy`, `matplotlib`. No external backtest libraries required.
Includes a full Dhan cost model: brokerage, STT, exchange charges, SEBI, GST, stamp duty.

```bash
python ema_crossover_backtest.py
```

Configure at the top of the file:
```python
DATA_PATH       = "data/NIFTY_50-29-03-2025-to-29-03-2026.csv"  # or folder path
INITIAL_CAPITAL = 5_00_000    # ₹5,00,000
POSITION_FRAC   = 0.20        # deploy 20% of capital per trade (index-friendly)
EMA_FAST        = 20
EMA_SLOW        = 50
```

**Supported CSV formats (auto-detected):**
- NSE index bhavcopy: `Date, Open, High, Low, Close, Volume`
- NSE equity bhavcopy: `SYMBOL, SERIES, OPEN, HIGH, LOW, CLOSE, TIMESTAMP`
- Dhan export / standard: `datetime, open, high, low, close, volume`
- TradingView export: `time (unix), open, high, low, close, volume`
- Folder of CSVs: auto-merges, deduplicates, skips intraday files automatically

**Outputs:**
- Console: full trade log, monthly P&L breakdown, per-trade cost breakdown, summary
- `equity_curve.png`: 3-panel chart — price + EMA lines + entry/exit markers, equity curve vs buy-and-hold, drawdown

**Position sizing note:** Nifty 50 index prices (~₹20,000–25,000/unit) make
standard 2% risk sizing return 0 shares at ₹5L capital. Use `POSITION_FRAC`
instead — `0.20` deploys ₹1L per trade → ~5 units at current prices.

---

### Option C — Original Backtester

```bash
# 5-min intraday backtest
python -m backtester.backtest --csv data/NIFTY50_5min_2yr.csv --capital 50000

# Daily backtest
python -m backtester.backtest_daily --csv data/NIFTY_50-29-03-2025-to-29-03-2026.csv --capital 50000
```

---

## 🧠 Strategy Logic — 13 Gates

### LONG Entry (all must pass simultaneously)

| Gate | Condition |
|------|-----------|
| G1 Time | 09:30–11:30 or 13:30–14:45 IST |
| G2 Daily limit | Trades today < 2 |
| G3 Loss streak | Consecutive losses < 2 |
| G4 Daily P&L | Daily loss < 6% of capital |
| G5 15-min trend | EMA20 > EMA50 **and** Close > VWAP on 15-min chart |
| G6 Crossover | EMA20 crossed above EMA50 within last 3 candles (5-min) |
| G7 VWAP | Close > VWAP on 5-min chart |
| G8 RSI | RSI > 50 on 5-min chart |
| G9 Volume | Volume ≥ 1.5× 20-period average |
| G10 VIX | VIX not < 12 (if feed connected; skip if offline) |
| G11 Flat | No open position currently held |
| G12 SL valid | SL distance > 0 |
| G13 Qty valid | Calculated quantity ≥ 1 |

**SHORT Entry:** all conditions inverted (trending\_down, EMA cross below, Close < VWAP, RSI < 50).

### SL / Target

```
LONG  SL = MIN(signal_candle_low, prev_candle_low)
SHORT SL = MAX(signal_candle_high, prev_candle_high)
Target   = Entry ± (SL_distance × 1.5)
```

### Options Translation

| Signal | Action |
|--------|--------|
| LONG | Buy ATM Call (CE) — weekly expiry preferred |
| SHORT | Buy ATM Put (PE) — weekly expiry preferred |
| Strong trend + VIX ≤ 20 | 1 OTM strike (lower cost, higher reward) |
| VIX > 20 | ATM only (avoid gamma risk) |
| Ranging market | No trade |

---

## ⚖️ The 10 Unbreakable Laws (all enforced in code)

1. Never risk more than 3% per trade
2. No trade outside prime time windows
3. Always set SL before entry — placed as a separate order simultaneously
4. Target = 1.5× SL distance — hardcoded, never overridden
5. Max 2 trades per day — hard stop, no exceptions
6. Stop after 2 consecutive losses — no revenge trading
7. No trade in ranging market (EMA not aligned with VWAP on 15-min)
8. VIX > 20 → halve position size to 1.5% risk
9. VIX < 12 → skip trade entirely (market too calm for momentum)
10. 14:45 IST time stop → force-exit all positions

---

## 📊 Position Sizing

```python
risk_amount = capital × risk_pct            # ₹50,000 × 3% = ₹1,500
sl_distance = abs(entry - sl_price)         # e.g. 70 points
quantity    = floor(risk_amount / sl_dist)  # 1,500 / 70 = 21
target      = entry + (sl_distance × 1.5)  # LONG target
```

**VIX adjustments:**

| VIX | Risk % |
|-----|--------|
| > 20 | 1.5% (halved) |
| 12–20 | 3% (normal) |
| < 12 | Skip trade |

---

## 🗺️ 90-Day Roadmap

| Phase | Command | Risk | Condition to advance |
|-------|---------|------|---------------------|
| Days 1–30 | `--phase paper` | 0% | 30+ trades, 65%+ win rate |
| Days 31–60 | `--phase half` | 1.5% | Profitable 4 weeks, no 2 losing weeks in a row |
| Days 61–90 | `--phase full` | 3% | Full compounding active |

---

## 🐛 Bug Fixes

| # | Bug | File | Status |
|---|-----|------|--------|
| B1 | VIX feed returned None — gates silently skipped | `bot.py` | ✅ Fixed — `get_vix_ltp()` now uses correct `IDX_I` segment |
| B2 | Options `security_id` was a placeholder string, rejected by exchange | `bot.py` | ✅ Fixed — `get_option_security_id()` resolves real ID from live option chain |
| B3 | 15-min VWAP in Pine Script may not reset correctly inside `request.security()` | `nifty50_strategy.pine` line 94 | 🔄 Pending |
| B4 | Daily backtester produces only 3 trades on 246 bars | `backtest_daily.py` | ℹ️ Expected — EMA 20/50 cross is rare on daily timeframe |
| B5 | `dayfirst=True` crashes with `ValueError` at row 681 on Dhan ISO-format CSVs | `data_fetcher.py` | ✅ Fixed — `_detect_dayfirst()` selects `format='ISO8601'` for YYYY-MM-DD files |
| B6 | Pipeline O(N²) bottleneck — 5-year 5-min backtest ran for 7+ hours | `pipeline.py` | ✅ Fixed — full vectorised rewrite, now completes in seconds |

---

## 📝 Trade Log

All live trades logged to `logs/trade_log.csv`:

```
Date, Time, Direction, Entry, SL, Target, Qty, Risk, Result, P&L, Balance, Growth%
```

---

## 📦 Dependencies

```
dhanhq>=2.0.1     # Dhan broker SDK (order placement only)
pandas>=2.0.0
numpy>=1.24.0
requests          # Raw HTTP calls for data fetchers (no SDK)
matplotlib>=3.7.0
schedule>=1.2.0   # Daily reset scheduling in bot.py
yfinance          # Optional — for pipeline --source yfinance
```

```bash
pip install -r requirements.txt
```

---

## ⚠️ Disclaimer

This is a personal trading tool built for educational and research purposes.
Past backtest performance does not guarantee future results.
Options trading carries substantial risk of loss.
Always run in paper trade mode before deploying real capital.
The author is not responsible for any financial losses incurred.