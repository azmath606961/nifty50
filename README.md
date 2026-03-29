# 🏦 Nifty 50 Intraday Trading Bot
### Built from `Nifty50_Trading_System.xlsx` — all 10 laws, 13 gates, 3-confirmation model

---

## 📁 Project Structure

```
nifty50_bot/
├── config.py                  ← All parameters (capital, risk, timeframes, Dhan creds)
├── bot.py                     ← 🤖 Main live trading bot
├── requirements.txt
│
├── core/
│   ├── dhan_client.py         ← Dhan API wrapper (paper-safe)
│   ├── indicators.py          ← EMA, VWAP, RSI, Volume
│   └── risk_manager.py        ← Position sizing, 13-gate validation, daily limits
│
├── strategies/
│   └── ema_crossover.py       ← EMA cross + RSI + VWAP + Volume signal generator
│
├── backtester/
│   └── backtest.py            ← Full walk-forward backtester
│
├── utils/
│   └── trade_logger.py        ← CSV logger (mirrors Excel Trade Log sheet)
│
├── logs/                      ← Auto-created: daily bot logs, trade CSV
└── data/                      ← Put your OHLCV CSV here for backtesting
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
DHAN_CLIENT_ID   = "your_client_id"
DHAN_ACCESS_TOKEN = "your_access_token"
```
Get these from: **Dhan → My Profile → API Access**

### 3. Run in paper trade mode (safe — no real orders)
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

## 📉 Backtesting

### Prepare your data CSV
Your CSV must have these columns:
```
datetime,open,high,low,close,volume
2024-01-02 09:15:00,21500,21550,21480,21530,125000
...
```

Download Nifty 5-min data from: NSE website, Dhan historical API, or Zerodha Kite.

### Run backtest
```bash
python backtester/backtest.py --csv data/nifty_5m.csv --capital 50000
```

Options:
```
--csv       Path to 5-min OHLCV CSV (required)
--capital   Starting capital (default: 50000)
--risk      Risk per trade as decimal (default: 0.03 = 3%)
--rr        Reward:Risk ratio (default: 1.5)
--output    Output CSV path (default: logs/backtest_results.csv)
```

---

## 🧠 Strategy Logic (3-Confirmation Model)

### LONG Entry — ALL must be true:
| Gate | Condition |
|------|-----------|
| ⏰ Time | Within 9:30–11:30 or 13:30–14:45 IST |
| 📈 15-min Trend | EMA20 > EMA50 **and** Price > VWAP |
| ↗️ 5-min Signal | EMA20 crosses above EMA50 (fresh, last 3 candles) |
| 📊 RSI | RSI > 50 on 5-min |
| 💧 Volume | Current bar volume ≥ 1.5× 20-period avg |
| 🌊 VWAP | Price above VWAP |

### SHORT Entry — mirror of above (all bearish)

### Options Translation:
- LONG signal → **Buy ATM Call (CE)**
- SHORT signal → **Buy ATM Put (PE)**
- Strong trend + VIX ≤ 20 → **1 OTM strike** (lower cost, higher reward)
- VIX > 20 → **ATM only** (avoid gamma risk)

---

## ⚖️ The 10 Unbreakable Laws (all enforced in code)

1. Never risk more than 3% per trade
2. No trade outside prime time windows
3. Always set SL before entry (SL order placed automatically)
4. Target = 1.5× SL distance (hardcoded RR ratio)
5. Max 2 trades per day
6. Stop after 2 consecutive losses
7. No trade in ranging market
8. VIX > 20 → halve position size
9. VIX < 12 → paper trade only
10. 14:45 time stop → exit everything

---

## 📊 Position Sizing Formula

```
Risk Amount  = Capital × 3%
SL Distance  = |Entry − Stop Loss|
Quantity     = Risk Amount ÷ SL Distance
Target       = Entry + (SL Distance × 1.5)   [for LONG]
```

Example with ₹50,000 capital:
- Risk = ₹1,500
- Entry = 21,500 | SL = 21,430 → SL Distance = 70 pts
- Qty = 1500 ÷ 70 = **21 lots**
- Target = 21,500 + 105 = **21,605**

---

## 🗺 90-Day Roadmap Integration

| Phase | Command | Risk | Description |
|-------|---------|------|-------------|
| Days 1–30 | `--phase paper` | 0% | Zero real money, build confidence |
| Days 31–60 | `--phase half` | 1.5% | Half-size live, real psychology |
| Days 61–90 | `--phase full` | 3% | Full compounding active |

Upgrade phase only when:
- 65%+ win rate maintained
- No 2 losing weeks in a row
- 30+ trades at current phase

---

## 📝 Trade Log

All trades are saved to `logs/trade_log.csv` — same columns as the Excel Trade Log:
`Date, Time, Setup Type, Direction, Entry, SL, Target, Qty, Risk, Target Profit, Result, P&L, Balance, Growth%`

---

# 1. Install dependencies (one time)
pip install -r requirements.txt

# 2a. Intraday backtest — auto-download 5-min data then backtest
python -m backtester.backtest --fetch --from 2025-01-01 --to 2026-03-27 --capital 50000

# 2b. Daily backtest — auto-download daily data then backtest
python -m backtester.backtest_daily --fetch --from 2025-01-01 --to 2026-03-27 --capital 50000

# 2c. Daily backtest — use your existing NSE CSV (still works as before)
python -m backtester.backtest_daily --csv data/NIFTY_50-29-03-2025-to-29-03-2026.csv --capital 50000

# 3. Or fetch data separately and inspect it first
python -m backtester.data_fetcher --mode intraday --from 2025-01-01 --to 2026-03-27
python -m backtester.data_fetcher --mode daily    --from 2025-01-01 --to 2026-03-27

## ⚠️ Disclaimer

This is a personal trading tool. Past backtest performance does not guarantee future results.
Options trading involves substantial risk of loss. Always start in paper trade mode.
The author is not responsible for any financial losses.
