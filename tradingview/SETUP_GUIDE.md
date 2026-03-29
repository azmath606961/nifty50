# 📺 TradingView Setup Guide — Nifty 50 Intraday System

## Files in this folder
| File | Purpose |
|------|---------|
| `nifty50_strategy.pine` | **Main file** — strategy with backtester, paper trade, live signals |
| `nifty50_dashboard.pine` | Companion indicator panel — RSI, volume ratio, gate score |

---

## STEP 1 — Load the Chart

1. Go to [tradingview.com](https://tradingview.com) and log in
2. Search for **`NSE:NIFTY`** in the top search bar
3. Set the timeframe to **5 minutes** (click the "5" in the toolbar)
4. Make sure your chart shows at least **3 months** of data (scroll left)

---

## STEP 2 — Add the Strategy

1. Click **Pine Editor** at the bottom of the screen
2. Clear the default code
3. Open `nifty50_strategy.pine` → copy **all** the code
4. Paste into Pine Editor
5. Click **"Add to chart"** (top right of Pine Editor)
6. A popup asks "Add as strategy?" → click **Yes**

You'll see:
- 🔵 EMA 20 line (blue)
- 🟠 EMA 50 line (orange)
- 🟣 VWAP (purple dots)
- 🟢 Green shading = Prime Session 1 (9:30–11:30)
- 🔵 Blue shading = Prime Session 2 (13:30–14:45)
- ▲ Green triangles = LONG signals
- ▼ Red triangles = SHORT signals
- Info table top-right showing live stats

---

## STEP 3 — Configure Strategy Settings

Right-click the strategy name on chart → **Settings**

### Properties tab:
| Setting | Value |
|---------|-------|
| Initial Capital | 50000 |
| Currency | INR |
| Commission | ₹20 per order (cash) |
| Slippage | 2 |

### Inputs tab (key ones):
| Input | Start with |
|-------|-----------|
| Starting Capital ₹ | 50000 |
| Risk per Trade % | 3 |
| Reward:Risk Ratio | 1.5 |
| Max Trades per Day | 2 |
| **Trading Phase** | **Paper (0%)** ← start here |
| EMA Fast | 20 |
| EMA Slow | 50 |
| RSI Period | 14 |
| Volume Multiplier | 1.5 |

---

## STEP 4 — Run the Backtest (1–2 Months)

1. After adding the strategy, click the **"Strategy Tester"** tab (bottom panel)
2. You'll see three sub-tabs:
   - **Overview** — net P&L, win rate, max drawdown, profit factor
   - **List of Trades** — every trade with entry/exit/P&L
   - **Properties** — backtest date range

### Set backtest date range:
- In Strategy Settings → **Properties** tab
- Set "Date Range" to last 1–2 months
- Uncheck "Use bar magnifier" for speed

### What to look for (targets from your Excel):
| Metric | Target |
|--------|--------|
| Win Rate | ≥ 65% |
| Profit Factor | ≥ 2.0 |
| Max Drawdown | < 15% |
| Sharpe Ratio | > 1.5 |

---

## STEP 5 — Add the Dashboard Indicator

1. Pine Editor → New tab → paste `nifty50_dashboard.pine` → Add to chart
2. This adds a **separate panel below** showing:
   - RSI line (green >50, red <50)
   - Volume ratio bars (lime = passes ≥1.5× filter)
   - Gate score 0–7 (green = all 7 gates passing = valid signal zone)

---

## STEP 6 — Paper Trading on TradingView

TradingView has a built-in paper trading simulator:

1. Click the **"Paper Trading"** button in the bottom broker panel
   (or go to **Trading Panel → Paper Trading**)
2. Set your paper account balance to ₹50,000
3. When you see a LONG/SHORT signal on the chart, manually place the paper trade:
   - Entry at market
   - Set SL at the dashed red line
   - Set target at the dashed green line
4. Log each trade in your Excel Trade Log or the bot's CSV

> 💡 **Tip:** Run paper trading for at least **30 trades** achieving **65%+ win rate** before moving to live — exactly per your 90-Day Roadmap.

---

## STEP 7 — Set Up Alerts (for notification / live bridge)

1. Right-click on chart → **Add Alert**
2. Set **Condition** to your strategy name
3. Available alert conditions:
   - `🚀 LONG Signal` — fires on every valid LONG entry
   - `🔻 SHORT Signal` — fires on every valid SHORT entry
   - `⏹ Time Stop` — fires at 14:45 to remind you to exit
   - `⚠️ Loss Limit` — fires after 2 consecutive losses
4. Set **Notification** to: Email + App notification + Webhook (for live bridge)

### Alert message format (auto-generated):
```
LONG CE | Entry=21500 | SL=21430 | Nifty 5m
```

---

## STEP 8 — Going Live with Dhan

When you're ready (after 30+ paper trades, 65%+ win rate):

### Connect Dhan to TradingView:
1. Log in to TradingView
2. Bottom panel → **Trading Panel** → search for **"Dhan"**
3. Click **Connect** → enter your Dhan credentials
4. Your Dhan account balance and positions sync to TradingView

### Switch the strategy to live:
1. Strategy Settings → Inputs → **Trading Phase → "Full 3%"**
2. Now when you see a signal, click **"Buy"/"Sell"** in the TradingView broker panel
3. Orders go directly to Dhan — no separate app needed

### Or use alerts + webhook:
- Set up a webhook URL pointing to a simple server that calls Dhan API
- The Python bot (`bot.py` from the previous build) can receive these webhooks
- This makes execution fully automatic

---

## Phase Checklist (90-Day Roadmap)

### Days 1–30: Paper Trade
- [ ] Phase set to **"Paper (0%)"** in inputs
- [ ] Run backtest on last 2 months — confirm metrics
- [ ] Paper trade live signals for 30+ trades
- [ ] Achieve 65%+ win rate before proceeding

### Days 31–60: Half-Size Live
- [ ] Phase set to **"Half 1.5%"** in inputs
- [ ] Connect Dhan broker in TradingView
- [ ] Trade for 4 weeks, maintain profitability
- [ ] No 2 losing weeks in a row

### Days 61–90: Full Live
- [ ] Phase set to **"Full 3%"** in inputs
- [ ] Compounding active (capital updates automatically)
- [ ] Review every Friday using Weekly Review sheet

---

## Troubleshooting

| Problem | Fix |
|---------|-----|
| "Script could not be compiled" | Check for copy-paste formatting issues — re-paste cleanly |
| No signals showing | Check timeframe is 5min and chart has enough history (55+ bars) |
| Strategy tester shows 0 trades | Extend date range; ensure NSE:NIFTY is loaded (not NIFTY futures) |
| EMA lines look wrong | Confirm inputs: Fast=20, Slow=50 |
| Session shading not showing | Confirm your TradingView timezone is set to Asia/Kolkata (IST) |
| `request.security` warning | Normal — Pine Script lookahead warning, strategy still works correctly |
