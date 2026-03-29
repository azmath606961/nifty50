# NIFTY 50 INTRADAY TRADING BOT — SPECIFICATION DOCUMENT
**Version:** Current (as of March 2026)
**Instrument:** Nifty 50 Index (NSE) — Intraday only
**Execution:** Dhan broker API
**Base Capital:** ₹50,000

---

## 1. STRATEGY RULES

### 1.1 Strategy Name
**EMA Crossover + RSI + VWAP + Volume — 3-Confirmation Model**

### 1.2 Timeframes
| Role | Timeframe | Purpose |
|------|-----------|---------|
| Signal generation | 5-minute | EMA crossover detection, RSI, VWAP, Volume |
| Trend filter | 15-minute | Higher-timeframe trend direction confirmation |

### 1.3 Market Structure Classification
The market is classified on every bar into one of four states using the 15-min chart:

| State | Condition | Action |
|-------|-----------|--------|
| trending_up | EMA20 > EMA50 AND close > VWAP | LONG setups only |
| trending_down | EMA20 < EMA50 AND close < VWAP | SHORT setups only |
| ranging | Neither trending_up nor trending_down | NO TRADE |
| volatile | VIX > 20 (if VIX feed enabled) | Halve position size |
| low_vol | VIX < 12 (if VIX feed enabled) | Skip entirely |

### 1.4 Options Translation
| Signal | Action | Rationale |
|--------|--------|-----------|
| LONG signal | Buy ATM Call (CE) | Bullish directional |
| SHORT signal | Buy ATM Put (PE) | Bearish directional |
| Ranging market | No trade | Capital protection |
| Strong trend + VIX ≤ 20 | 1 OTM strike | Lower cost, higher reward |
| VIX > 20 | ATM only | Avoid gamma risk |

Strike interval: 50 points. Expiry preference: weekly (Thursday).

---

## 2. INDICATORS AND EXACT SETTINGS

### 2.1 EMA — Exponential Moving Average
- **Fast EMA:** Period = 20, applied to close price, exponential smoothing (adjust=False)
- **Slow EMA:** Period = 50, applied to close price, exponential smoothing (adjust=False)
- **Method:** Standard EWM (span=period)
- **Applied on:** Both 5-min and 15-min charts independently

### 2.2 RSI — Relative Strength Index
- **Period:** 14
- **Applied to:** Close price
- **Method:** Wilder smoothing via EWM (com = period - 1, adjust=False)
- **Thresholds:** Midline = 50 (bull side > 50, bear side < 50)

### 2.3 VWAP — Volume Weighted Average Price
- **Type:** Intraday VWAP — resets at the start of each trading day
- **Formula:** Cumulative(Typical Price × Volume) / Cumulative(Volume)
- **Typical Price:** (High + Low + Close) / 3
- **Applied on:** 5-min chart only

### 2.4 Volume
- **Baseline:** 20-period Simple Moving Average of volume
- **Ratio:** Current bar volume ÷ 20-period SMA
- **Threshold:** Ratio must be ≥ 1.5× for a valid signal

### 2.5 EMA Crossover Detection
- **Bullish crossover:** EMA20 crosses from below to above EMA50 (signal = +1)
- **Bearish crossover:** EMA20 crosses from above to below EMA50 (signal = −1)
- **Freshness window:** Signal is valid if the crossover occurred within the last 3 candles

---

## 3. ENTRY & EXIT LOGIC — BOOLEAN CONDITIONS

### 3.1 LONG Entry — ALL conditions must be TRUE simultaneously

```
GATE 1  (Time)       : current_time >= 09:30 AND current_time <= 11:30
                       OR current_time >= 13:30 AND current_time <= 14:45

GATE 2  (Daily limit): trades_taken_today < 2

GATE 3  (Loss limit) : consecutive_losses < 2

GATE 4  (Daily P&L)  : daily_pnl > -(capital × 0.06)

GATE 5  (Market)     : 15min_market_structure == "trending_up"
                         (EMA20_15m > EMA50_15m AND close_15m > VWAP_15m)

GATE 6  (Crossover)  : EMA20_5m crossed above EMA50_5m within last 3 candles

GATE 7  (VWAP)       : close_5m > VWAP_5m

GATE 8  (RSI)        : RSI_5m > 50

GATE 9  (Volume)     : volume_ratio_5m >= 1.5

GATE 10 (VIX)        : VIX not < 12  (if VIX feed connected)

GATE 11 (Flat)       : no open position currently held

GATE 12 (SL valid)   : (entry - sl_price) > 0

GATE 13 (Qty valid)  : calculated_quantity >= 1
```

**Entry price:** Close of the signal candle (market order)
**Stop Loss:** MIN(low of signal candle, low of previous candle)
**Target:** Entry + (SL distance × 1.5)

### 3.2 SHORT Entry — ALL conditions must be TRUE simultaneously

```
GATE 1  (Time)       : same session windows as LONG

GATE 2  (Daily limit): trades_taken_today < 2

GATE 3  (Loss limit) : consecutive_losses < 2

GATE 4  (Daily P&L)  : daily_pnl > -(capital × 0.06)

GATE 5  (Market)     : 15min_market_structure == "trending_down"
                         (EMA20_15m < EMA50_15m AND close_15m < VWAP_15m)

GATE 6  (Crossover)  : EMA20_5m crossed below EMA50_5m within last 3 candles

GATE 7  (VWAP)       : close_5m < VWAP_5m

GATE 8  (RSI)        : RSI_5m < 50

GATE 9  (Volume)     : volume_ratio_5m >= 1.5

GATE 10 (VIX)        : VIX not < 12  (if VIX feed connected)

GATE 11 (Flat)       : no open position currently held

GATE 12 (SL valid)   : (sl_price - entry) > 0

GATE 13 (Qty valid)  : calculated_quantity >= 1
```

**Entry price:** Close of the signal candle (market order)
**Stop Loss:** MAX(high of signal candle, high of previous candle)
**Target:** Entry − (SL distance × 1.5)

### 3.3 Exit Conditions (checked on every bar while in trade)

```
EXIT 1 (Stop Loss hit) :
  LONG  → current_bar_low  <= sl_price   → exit at sl_price, result = LOSS
  SHORT → current_bar_high >= sl_price   → exit at sl_price, result = LOSS

EXIT 2 (Target hit) :
  LONG  → current_bar_high >= target     → exit at target, result = WIN
  SHORT → current_bar_low  <= target     → exit at target, result = WIN

EXIT 3 (Time Stop) :
  current_time >= 14:45                  → exit at market close, result = WIN/LOSS/BE

EXIT 4 (Daily consecutive loss stop) :
  consecutive_losses >= 2               → close position, no new trades rest of day
```

---

## 4. RISK MANAGEMENT PARAMETERS

### 4.1 Position Sizing Formula
```
Risk Amount  = Current Capital × Risk %
SL Distance  = ABS(Entry Price − Stop Loss Price)
Quantity     = FLOOR(Risk Amount / SL Distance)
Target Dist  = SL Distance × 1.5
Target Price = Entry + Target Dist  (LONG)
             = Entry − Target Dist  (SHORT)
```

### 4.2 Core Parameters
| Parameter | Value | Notes |
|-----------|-------|-------|
| Starting Capital | ₹50,000 | Compounds as balance grows |
| Risk per Trade | 3% | Of current running capital |
| Reward:Risk Ratio | 1.5 | Fixed, hardcoded |
| Max Trades per Day | 2 | Hard stop |
| Max Consecutive Losses | 2 | Hard stop for the day |
| Daily Loss Limit | 6% | = 2 full losing trades at 3% each |
| Max Drawdown Target | 15% | Monitoring metric, not a hard cut |

### 4.3 VIX Adjustments
| VIX Level | Action |
|-----------|--------|
| VIX > 20 | Risk % halved to 1.5% (position size halved) |
| 12 ≤ VIX ≤ 20 | Normal 3% risk |
| VIX < 12 | Skip trade entirely — market too calm |

### 4.4 Trading Phase System (90-Day Roadmap)
| Phase | Risk % | Condition to advance |
|-------|--------|----------------------|
| paper (Days 1–30) | 0% — signals only, no real orders | 30+ trades, 65%+ win rate |
| half (Days 31–60) | 1.5% | Profitable 4 weeks, no 2 losing weeks in a row |
| full (Days 61–90) | 3% | Full compounding active |

### 4.5 Trading Windows (IST)
| Window | Time | Status |
|--------|------|--------|
| Prime Session 1 | 09:30 – 11:30 | TRADE |
| Dead Zone | 11:30 – 13:30 | NO TRADE |
| Prime Session 2 | 13:30 – 14:45 | TRADE |
| Time Stop | 14:45 | EXIT ALL |
| Opening Chaos | 09:15 – 09:30 | NO TRADE |
| Close Manipulation | 14:45 – 15:30 | NO TRADE |

---

## 5. FEATURES BUILT

### 5.1 Python Bot (production-ready)

| Module | File | Status |
|--------|------|--------|
| Configuration | config.py | Complete |
| Dhan API client | core/dhan_client.py | Complete — paper-safe, all order types |
| Indicators | core/indicators.py | Complete — EMA, RSI, VWAP, Volume |
| Risk manager | core/risk_manager.py | Complete — all 13 gates, position sizing, daily tracking |
| Signal generator | strategies/ema_crossover.py | Complete — 3-confirmation model |
| Live bot loop | bot.py | Complete — polls every 60s, entry+SL orders, time stop |
| Trade logger | utils/trade_logger.py | Complete — CSV output matching Excel Trade Log format |
| Intraday backtester | backtester/backtest.py | Complete — walk-forward, skip diagnostics |
| Daily backtester | backtester/backtest_daily.py | Complete — works with NSE daily CSV |
| Data fetcher | backtester/data_fetcher.py | Complete — jugaad-data integration |

### 5.2 Data Fetching
- Auto-detects any CSV column format (Dhan, NSE, TradingView, jugaad)
- Handles date+time split columns, single datetime, unix timestamps
- Strips timezone / fake timestamps automatically
- Resamples 5-min data to 15-min internally
- `--fetch` flag on both backtest commands downloads data via jugaad-data without needing a separate step

### 5.3 Backtester Features
- Walk-forward simulation (no lookahead bias)
- Per-bar SL / Target / Time-stop exit simulation
- Daily trade counter and consecutive loss counter reset each day
- Skip-reason diagnostics (counts bars filtered by each gate)
- Outputs: trade log CSV + summary CSV
- Metrics: Win rate, Profit Factor, Max Drawdown, Sharpe Ratio, Avg Win/Loss

### 5.4 TradingView Pine Script
- Strategy script (nifty50_strategy.pine) — all 13 gates implemented in Pine v5
- Dashboard indicator (nifty50_dashboard.pine) — RSI panel, volume ratio bars, gate score 0–7
- HTF 15-min trend pulled via request.security()
- Trading Phase dropdown (Paper / Half / Full) changes effective risk
- Live info table: capital, net P&L, win rate, trades today, session status, 15m trend, RSI
- Alert conditions wired for all signal types including time stop and loss limit
- Session background shading (green = Session 1, blue = Session 2)
- SL and Target dashed lines drawn on signal bars
- EMA ribbon fill (green = bull, red = bear, gray = range)

### 5.5 Live Bot Features
- Simultaneous entry order + SL order placement on signal
- Price monitoring loop every 60 seconds (configurable)
- Automatic SL order cancellation on target exit
- Force-close all positions at 14:45
- Daily stats reset at market close (15:31)
- Paper trade mode generates synthetic candles for testing without Dhan connection

---

## 6. KNOWN BUGS AND PENDING IMPROVEMENTS

### 6.1 Known Bugs

| # | Bug | Location | Impact |
|---|-----|----------|--------|
| B1 | VIX feed not connected in live bot — VIX gates always skipped | bot.py `_get_vix()` | Medium — VIX size halving never triggers |
| B2 | Option security_id for live orders is a placeholder string, not real Dhan ID | bot.py `_enter_trade()` | Critical for live options trading |
| B3 | 15-min VWAP in Pine Script uses current chart's VWAP inside request.security() — may not reset correctly on higher TF | nifty50_strategy.pine line 94 | Low — minor inaccuracy in HTF VWAP |
| B4 | Daily backtester has only 3 trades on 246 daily bars — EMA20/50 cross is rare on daily | backtest_daily.py | Low — expected behaviour, not a code bug |
| B5 | jugaad-data column names change across library versions — normalise_jugaad() may need updating | data_fetcher.py | Medium — fetch will error if columns change |
| B6 | Intraday backtester produces 0 trades on random/flat data — `no_signal` count dominates | backtest.py | Low — expected on non-trending synthetic data |

### 6.2 Pending Improvements

| # | Improvement | Priority | Notes |
|---|-------------|----------|-------|
| P1 | Connect real India VIX feed via Dhan API (security_id=28) | High | Currently returns None, gates skipped |
| P2 | Resolve Nifty options security_id dynamically from Dhan option chain API | High | Required before any live options order |
| P3 | Add trailing stop loss — move SL to breakeven after price moves 0.5× target distance | Medium | Not in original spec, would improve RR |
| P4 | Add partial exit — book 50% at 1× RR, let rest run to 1.5× RR | Medium | Reduces win rate but improves avg trade |
| P5 | Webhook receiver to accept TradingView alerts and auto-place Dhan orders | Medium | Bridge between Pine Script signals and Python execution |
| P6 | Add ORB (Opening Range Breakout) as a second strategy alongside EMA crossover | Medium | Complementary — fires in first 15 min |
| P7 | Weekly performance report auto-generated every Friday (mirrors Excel Weekly Review) | Low | Nice to have |
| P8 | Telegram/WhatsApp alert on every signal, entry, exit, and daily summary | Low | Notification layer |
| P9 | Multi-year backtest support via jugaad batch fetching with rate-limit handling | Low | jugaad NSE limits large requests |
| P10 | Dashboard web UI (Flask/Streamlit) showing live equity curve, open position, daily stats | Low | Currently log-file only |

### 6.3 Data Limitations
- jugaad-data provides NSE data going back approximately 1–2 years for intraday bars
- NSE website (manual download) provides daily OHLCV only — no intraday
- TradingView free plan limits historical data export to ~1,500 bars (≈ 5 trading days on 5-min)
- TradingView paid plan (Pro+) needed for full 1-year 5-min export

---

## 7. SYSTEM DEPENDENCIES

### 7.1 Python Packages
| Package | Version | Purpose |
|---------|---------|---------|
| dhanhq | ≥ 2.0.1 | Dhan broker API |
| pandas | ≥ 2.0.0 | Data manipulation |
| numpy | ≥ 1.24.0 | Numerical operations |
| jugaad-data | ≥ 0.28 | NSE data download |
| requests-cache | ≥ 1.1.0 | Caching jugaad requests |
| matplotlib | ≥ 3.7.0 | Optional charting |
| schedule | ≥ 1.2.0 | Daily reset scheduling |

### 7.2 External Services
| Service | Purpose | Required For |
|---------|---------|-------------|
| Dhan account | Order execution, market data | Live trading |
| Dhan API credentials | Client ID + Access Token | Live + paper (with connection) |
| TradingView account (free) | Pine Script strategy + paper trading | TradingView workflow |
| NSE website | Daily OHLCV CSV download | Daily backtest |
| jugaad-data / NSE | 5-min intraday OHLCV | Intraday backtest |

---

*Document auto-generated from codebase — March 2026*
