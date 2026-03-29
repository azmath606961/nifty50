# NIFTY 50 BOT — CLAUDE + GPT HYBRID PROMPT SYSTEM
**Built by Lyra | Based on: NIFTY50_BOT_SPEC.md | March 2026**

---

## ⚙️ ARCHITECTURE OVERVIEW

```
CLAUDE (Think)                          GPT-4o (Build)
──────────────────────                  ──────────────────────
• Analyse bugs & root causes        →   • Fix specific files
• Design new features               →   • Write complete code
• Strategy logic decisions          →   • Debug errors
• Decide what to build & how        →   • Implement improvements
• Produce GPT instruction packets   →   • Run and iterate

USE CLAUDE: Once per problem          USE GPT: Every coding session
SAVE every Claude output              Paste Claude packet → build
```

---
---

# ════════════════════════════════════════
# PART 1 — CLAUDE PROMPT (The Brain)
# ════════════════════════════════════════

## HOW TO USE:
Paste this ENTIRE prompt into Claude when you need to:
- Fix a bug
- Add a new feature
- Change strategy logic
- Plan an improvement

Replace the [TASK] section at the bottom with your actual request.
Claude will output a clean GPT Instruction Packet — paste that into GPT.

---

```
You are a senior quantitative trading systems architect.
You have full context of an existing Nifty 50 intraday trading bot.
Your job is THINKING ONLY — no code, no explanations, no fluff.
You will output a structured GPT Instruction Packet that another AI will use to write code.

════════════════════════════════════════
EXISTING BOT — FULL CONTEXT
════════════════════════════════════════

INSTRUMENT     : Nifty 50 (NSE) — Intraday only
BROKER API     : Dhan (dhanhq >= 2.0.1)
BASE CAPITAL   : ₹50,000 compounding
RISK PER TRADE : 3% of current capital (1.5% if VIX > 20)
RR RATIO       : 1:1.5 (fixed)
MAX TRADES/DAY : 2
SESSIONS       : 09:30–11:30 and 13:30–14:45 IST
TIME STOP      : Force exit at 14:45

────────────────────────────────────────
INDICATORS (exact settings)
────────────────────────────────────────
EMA Fast       : period=20, ewm(span=20, adjust=False), on close, both 5m & 15m
EMA Slow       : period=50, ewm(span=50, adjust=False), on close, both 5m & 15m
RSI            : period=14, Wilder via ewm(com=13, adjust=False), on close
VWAP           : intraday reset daily, typical_price=(H+L+C)/3, cumulative, 5m only
Volume Ratio   : current_volume / SMA(volume, 20), threshold >= 1.5
Crossover      : fresh if occurred within last 3 candles

────────────────────────────────────────
13-GATE ENTRY LOGIC
────────────────────────────────────────
GATE 1  : Time within 09:30–11:30 OR 13:30–14:45
GATE 2  : trades_today < 2
GATE 3  : consecutive_losses < 2
GATE 4  : daily_pnl > -(capital × 0.06)
GATE 5  : 15m market structure = trending_up (LONG) or trending_down (SHORT)
            trending_up   = EMA20_15m > EMA50_15m AND close_15m > VWAP_15m
            trending_down = EMA20_15m < EMA50_15m AND close_15m < VWAP_15m
GATE 6  : EMA20_5m crossed above/below EMA50_5m within last 3 candles
GATE 7  : close_5m > VWAP_5m (LONG) | close_5m < VWAP_5m (SHORT)
GATE 8  : RSI_5m > 50 (LONG) | RSI_5m < 50 (SHORT)
GATE 9  : volume_ratio_5m >= 1.5
GATE 10 : VIX not < 12 (if feed connected; skip gate if feed offline)
GATE 11 : no open position
GATE 12 : SL distance > 0
GATE 13 : calculated_quantity >= 1

LONG  SL    : MIN(signal_candle_low, prev_candle_low)
SHORT SL    : MAX(signal_candle_high, prev_candle_high)
TARGET      : entry ± (SL_distance × 1.5)

────────────────────────────────────────
EXIT LOGIC
────────────────────────────────────────
EXIT 1 : SL hit — LONG: bar_low <= sl | SHORT: bar_high >= sl → LOSS
EXIT 2 : Target hit — LONG: bar_high >= target | SHORT: bar_low <= target → WIN
EXIT 3 : Time stop at 14:45 → exit at market
EXIT 4 : consecutive_losses >= 2 → close + no more trades today

────────────────────────────────────────
POSITION SIZING
────────────────────────────────────────
risk_amount = capital × risk_pct
sl_distance = abs(entry − sl_price)
quantity    = floor(risk_amount / sl_distance)
VIX > 20    → risk_pct = 0.015 (halved)
VIX < 12    → skip trade entirely

────────────────────────────────────────
FILE STRUCTURE (all complete unless noted)
────────────────────────────────────────
config.py                        ✅ Complete
core/dhan_client.py              ✅ Complete
core/indicators.py               ✅ Complete
core/risk_manager.py             ✅ Complete
strategies/ema_crossover.py      ✅ Complete
bot.py                           ✅ Complete
utils/trade_logger.py            ✅ Complete
backtester/backtest.py           ✅ Complete
backtester/backtest_daily.py     ✅ Complete
backtester/data_fetcher.py       ✅ Complete
nifty50_strategy.pine            ✅ Complete
nifty50_dashboard.pine           ✅ Complete

────────────────────────────────────────
KNOWN BUGS (for reference)
────────────────────────────────────────
B1 : VIX feed returns None — gates skipped silently | bot.py _get_vix()
B2 : Options security_id is placeholder string — critical for live options | bot.py _enter_trade()
B3 : 15m VWAP in Pine Script may not reset correctly inside request.security()
B4 : Daily backtester: only 3 trades on 246 bars — EMA cross rare on daily (expected)
B5 : jugaad-data column names change across versions — normalise_jugaad() may break
B6 : Backtester produces 0 trades on flat/random data (expected)

────────────────────────────────────────
PENDING IMPROVEMENTS (for reference)
────────────────────────────────────────
P1  : Connect India VIX via Dhan API security_id=28           [HIGH]
P2  : Dynamic options security_id from Dhan option chain API  [HIGH]
P3  : Trailing SL — move to breakeven at 0.5× target distance [MEDIUM]
P4  : Partial exit — 50% at 1:1, rest at 1:1.5               [MEDIUM]
P5  : Webhook receiver for TradingView → Dhan orders          [MEDIUM]
P6  : ORB strategy as second signal source                    [MEDIUM]
P7  : Weekly performance report (auto, every Friday)          [LOW]
P8  : Telegram/WhatsApp alerts                                [LOW]
P9  : Multi-year backtest with jugaad rate-limit handling      [LOW]
P10 : Streamlit dashboard — equity curve, live stats          [LOW]

════════════════════════════════════════
YOUR TASK
════════════════════════════════════════
[REPLACE THIS SECTION WITH YOUR REQUEST]

Examples:
- "Fix bug B1 — connect real VIX feed"
- "Fix bug B2 — resolve options security_id dynamically"
- "Implement improvement P3 — trailing stop loss"
- "Implement improvement P8 — Telegram alerts"
- "Implement improvement P10 — Streamlit dashboard"
- "Add ORB strategy (P6) alongside existing EMA crossover"
- "Design webhook receiver (P5) for TradingView to Dhan"

════════════════════════════════════════
OUTPUT FORMAT — MANDATORY
════════════════════════════════════════
Produce ONLY a GPT Instruction Packet in this exact structure.
No explanations. No prose. No preamble. Only the packet.

---
## GPT INSTRUCTION PACKET
**Task ID:** [short label]
**Bot Version:** Nifty50 v1.0 (March 2026)

### CONTEXT SUMMARY
[2–3 lines max — what exists, what is broken or missing]

### ROOT CAUSE / DESIGN DECISION
[1–3 lines — why it is broken or the design rationale for the new feature]

### EXACT CHANGES REQUIRED
[File by file. Be precise. One action per line.]

File: [filename]
- Action: [CREATE | MODIFY | ADD FUNCTION | REPLACE FUNCTION | ADD LINES]
- What: [exact description of what to write]
- Logic: [boolean conditions, formulas, or rules to implement — no ambiguity]
- Do NOT change: [list anything GPT must leave untouched]

### INTEGRATION POINTS
[How new/fixed code connects to existing modules]

### ACCEPTANCE CRITERIA
[Numbered list — how GPT knows the implementation is correct]

### CONSTRAINTS
- Language: Python 3.10+
- Style: match existing codebase style
- No new dependencies unless listed here: [list if any]
- Write complete functions — never truncate
- Add inline comments on non-obvious logic only
---
```

---
---

# ════════════════════════════════════════
# PART 2 — GPT-4o PROMPT (The Hands)
# ════════════════════════════════════════

## HOW TO USE:
1. Get the GPT Instruction Packet from Claude
2. Open a fresh GPT-4o chat
3. Paste the SESSION OPENER below (one time per session)
4. Then paste the Claude Instruction Packet
5. Use the COMMAND SHORTCUTS for everything after that

---

### SESSION OPENER (paste once at the start of every GPT session)

```
You are a senior Python developer building a Nifty 50 intraday trading bot.
You write complete, production-grade, modular Python code.

RULES — follow without exception:
1. Write COMPLETE files and functions — never truncate, never use "..." or "# rest of code"
2. Match existing code style — same naming conventions, same structure
3. Never add unrequested features
4. Never remove existing logic unless explicitly told to
5. If a task requires changing multiple files, do them one at a time and wait for confirmation
6. After each file, state: "File complete. Ready for next file: [filename]"
7. If anything in the instruction packet is ambiguous, choose the safest/most conservative implementation

EXISTING STACK:
- Python 3.10+
- dhanhq >= 2.0.1 (Dhan broker API)
- pandas >= 2.0.0
- numpy >= 1.24.0
- jugaad-data >= 0.28
- requests-cache >= 1.1.0
- matplotlib >= 3.7.0
- schedule >= 1.2.0

EXISTING FILE STRUCTURE:
config.py
core/
  dhan_client.py
  indicators.py
  risk_manager.py
strategies/
  ema_crossover.py
bot.py
utils/
  trade_logger.py
backtester/
  backtest.py
  backtest_daily.py
  data_fetcher.py

I will now give you a Claude Instruction Packet. Read it fully before writing any code.
Wait for me to say "Build it" before starting.
```

---

### COMMAND SHORTCUTS (use these after the session opener)

```
"Build it"
→ Start building exactly what the instruction packet says.
   Do file 1 first. Wait for my confirmation before file 2.

"Continue"
→ Move to the next file in the instruction packet.

"Debug [filename] — [paste error]"
→ Fix only the error shown. Do not refactor or change other logic.

"Rewrite [function_name] in [filename]"
→ Rewrite only that function. Keep everything else identical.

"Test plan for [filename]"
→ Give me a step-by-step manual test checklist for that file only.

"Show diff"
→ Show only the lines that changed vs the original. No full file reprint.

"Integrate [filename] with [filename]"
→ Show exactly how to connect two modules. No full rewrites.

"Status"
→ Print current build status table showing complete/in-progress/not-started for all files.
```

---
---

# ════════════════════════════════════════
# PART 3 — PRE-BUILT CLAUDE PACKETS
# (Ready to paste — no Claude needed)
# ════════════════════════════════════════

## These are ready-made GPT Instruction Packets for your 6 bugs and top improvements.
## Skip Claude entirely for these — paste directly into GPT after the session opener.

---

## 🔴 BUG FIX: B1 — VIX Feed (High Priority)

```
## GPT INSTRUCTION PACKET
**Task ID:** BUG-B1-VIX-FEED
**Bot Version:** Nifty50 v1.0 (March 2026)

### CONTEXT SUMMARY
bot.py has a _get_vix() function that currently returns None.
This causes GATE 10 to always be skipped silently.
VIX-based position sizing (halve at VIX>20, skip at VIX<12) never triggers.

### ROOT CAUSE / DESIGN DECISION
_get_vix() is not calling the Dhan API with the correct security_id.
India VIX on Dhan API = security_id="28", exchange_segment="NSE_EQ".
The function needs to fetch the LTP of this security and return it as a float.

### EXACT CHANGES REQUIRED

File: bot.py
- Action: REPLACE FUNCTION _get_vix()
- Logic:
    Call self.dhan.get_ltp(securities={"NSE_EQ": ["28"]})
    Extract LTP value from response dict
    Return as float
    On any exception → log warning → return None (gates skip gracefully)
    If dhan client not connected (paper mode) → return None silently
- Do NOT change: any other function in bot.py

File: config.py
- Action: ADD LINES under risk parameters section
- What: Add two constants
    VIX_HIGH_THRESHOLD = 20   # halve position size above this
    VIX_LOW_THRESHOLD  = 12   # skip trade entirely below this
- Do NOT change: any existing constants

### INTEGRATION POINTS
_get_vix() is called once per signal check loop in bot.py.
Return value is passed to risk_manager.py get_risk_pct(vix) function.
If None is returned, existing gate-skip behaviour is preserved.

### ACCEPTANCE CRITERIA
1. _get_vix() returns a float when Dhan API is connected
2. _get_vix() returns None gracefully when in paper mode or on API error
3. A WARNING log line is printed when VIX returns None
4. config.py has VIX_HIGH_THRESHOLD and VIX_LOW_THRESHOLD constants
5. No other functions in bot.py are modified

### CONSTRAINTS
- Language: Python 3.10+
- No new dependencies
- Write complete function — never truncate
- Log format must match existing bot.py log style
```

---

## 🔴 BUG FIX: B2 — Options Security ID (Critical)

```
## GPT INSTRUCTION PACKET
**Task ID:** BUG-B2-OPTIONS-SECURITY-ID
**Bot Version:** Nifty50 v1.0 (March 2026)

### CONTEXT SUMMARY
bot.py _enter_trade() uses a hardcoded placeholder string for options security_id.
This makes live options order placement impossible.
Need to resolve the real Dhan security_id dynamically from the option chain.

### ROOT CAUSE / DESIGN DECISION
Dhan API provides an option chain endpoint.
Given Nifty spot price, expiry date, option type (CE/PE), and strike interval (50 pts),
we can calculate ATM/OTM strike and fetch the correct security_id from the chain.

### EXACT CHANGES REQUIRED

File: core/dhan_client.py
- Action: ADD FUNCTION get_option_security_id()
- Parameters: option_type (str: "CE" or "PE"), otm_offset (int: 0=ATM, 1=one OTM)
- Logic:
    Step 1: Fetch current Nifty spot LTP via get_ltp({"NSE_EQ": ["13"]})
    Step 2: Calculate ATM strike = round(spot / 50) × 50
    Step 3: If otm_offset=1 → strike = ATM + 50 (CE) or ATM − 50 (PE)
    Step 4: Get nearest weekly Thursday expiry date (calculate from today)
    Step 5: Call Dhan option chain API for Nifty with that expiry
    Step 6: Find the row matching strike + option_type
    Step 7: Extract and return security_id as string
    On any failure → raise ValueError with descriptive message
- Do NOT change: any existing functions in dhan_client.py

File: bot.py
- Action: MODIFY FUNCTION _enter_trade()
- What: Replace hardcoded options security_id with a call to
    self.dhan_client.get_option_security_id(option_type, otm_offset=0)
- Wrap the call in try/except — on ValueError log error and abort trade
- Do NOT change: any other logic in _enter_trade()

### INTEGRATION POINTS
get_option_security_id() is called inside _enter_trade() only.
otm_offset=0 for ATM (default), otm_offset=1 for 1-strike OTM when VIX <= 20.

### ACCEPTANCE CRITERIA
1. get_option_security_id("CE", 0) returns a valid Dhan security_id string
2. get_option_security_id("PE", 0) returns a valid Dhan security_id string
3. ATM strike is correctly calculated as nearest 50-point multiple to spot
4. Weekly Thursday expiry is correctly identified
5. If option chain API fails, trade is aborted with a clear error log — no crash

### CONSTRAINTS
- Language: Python 3.10+
- No new dependencies
- Complete functions only — no truncation
- Match existing dhan_client.py error handling style
```

---

## 🟡 IMPROVEMENT: P3 — Trailing Stop Loss

```
## GPT INSTRUCTION PACKET
**Task ID:** IMPROVE-P3-TRAILING-SL
**Bot Version:** Nifty50 v1.0 (March 2026)

### CONTEXT SUMMARY
Currently SL is static after entry. No trailing mechanism exists.
P3 requires: move SL to breakeven when price moves 0.5× target distance in favour.

### ROOT CAUSE / DESIGN DECISION
Trailing SL improves RR without changing entry logic.
Trigger: when unrealised profit >= 0.5 × (target − entry), move SL to entry price.
This locks in a breakeven result at minimum, eliminating full-loss risk after partial move.

### EXACT CHANGES REQUIRED

File: core/risk_manager.py
- Action: ADD FUNCTION check_trailing_sl()
- Parameters: entry (float), current_price (float), sl (float),
              target (float), direction (str: "LONG" or "SHORT"),
              breakeven_triggered (bool)
- Logic:
    half_target_dist = abs(target − entry) × 0.5
    LONG:
      favourable_move = current_price − entry
      if favourable_move >= half_target_dist AND NOT breakeven_triggered:
        return entry (new SL), True (breakeven_triggered flag)
      else: return sl (unchanged), breakeven_triggered
    SHORT:
      favourable_move = entry − current_price
      same logic, new SL = entry
- Returns: tuple (new_sl: float, breakeven_triggered: bool)
- Do NOT change: any existing functions in risk_manager.py

File: bot.py
- Action: MODIFY price monitoring loop (the section that checks exits)
- What: After EXIT 1 and EXIT 2 checks, add trailing SL check:
    Call check_trailing_sl() with current bar data
    If returned SL != current SL:
      Update self.current_sl to new SL
      Cancel old Dhan SL order
      Place new Dhan SL order at new SL price
      Log: "Trailing SL moved to breakeven at [price]"
- Add breakeven_triggered boolean to trade state (default False, reset on new trade)
- Do NOT change: any entry logic, gate logic, or exit logic

File: backtester/backtest.py
- Action: MODIFY per-bar exit simulation loop
- What: Add trailing SL check using same check_trailing_sl() logic
    Track breakeven_triggered per trade
    If SL updates → use new SL for subsequent bars
- Do NOT change: any other backtest logic

### INTEGRATION POINTS
check_trailing_sl() called inside bot.py monitoring loop and backtest.py bar loop.
Sits between EXIT 2 check and end of loop iteration.

### ACCEPTANCE CRITERIA
1. Trailing SL triggers when price moves >= 50% of target distance
2. SL moves to exact entry price (breakeven) — not to a different level
3. Trailing SL triggers only once per trade (breakeven_triggered flag prevents repeat)
4. Dhan SL order is cancelled and replaced when SL moves in live bot
5. Backtest correctly simulates trailing SL on historical bars
6. A log line is printed every time trailing SL triggers

### CONSTRAINTS
- Language: Python 3.10+
- No new dependencies
- Complete functions — no truncation
- Trailing SL must NOT affect entry gate logic
```

---

## 🟡 IMPROVEMENT: P8 — Telegram Alerts

```
## GPT INSTRUCTION PACKET
**Task ID:** IMPROVE-P8-TELEGRAM-ALERTS
**Bot Version:** Nifty50 v1.0 (March 2026)

### CONTEXT SUMMARY
No notification system exists. P8 requires Telegram alerts on:
signal detected, trade entry, SL hit, target hit, daily summary at 15:31.

### ROOT CAUSE / DESIGN DECISION
Telegram Bot API (HTTP, no SDK needed — just requests).
New file alerts/telegram_alert.py — keeps alerting isolated from core logic.
bot.py calls alert functions at the right moments.

### EXACT CHANGES REQUIRED

File: alerts/telegram_alert.py (CREATE NEW FILE)
- Action: CREATE
- Functions required:

  send_message(text: str) → None
    POST to https://api.telegram.org/bot{TOKEN}/sendMessage
    chat_id and TOKEN read from config.py
    On failure: log warning, do not raise (alerts must never crash the bot)

  alert_signal(direction: str, gate_scores: dict) → None
    Message: "🔔 SIGNAL: {direction} | Gates: {passed}/{total} | Time: {IST}"

  alert_entry(direction: str, entry: float, sl: float,
              target: float, qty: int, risk_amt: float) → None
    Message: "✅ ENTRY {direction} @ {entry} | SL: {sl} | Target: {target}
              Qty: {qty} | Risk: ₹{risk_amt}"

  alert_exit(result: str, exit_price: float, pnl: float,
             new_balance: float) → None
    Message: "{'🟢 WIN' if result=='WIN' else '🔴 LOSS'} Exit @ {exit_price}
              P&L: ₹{pnl} | Balance: ₹{new_balance}"

  alert_daily_summary(trades: int, wins: int, losses: int,
                      daily_pnl: float, balance: float) → None
    Message: "📊 DAILY SUMMARY | Trades: {trades} | W: {wins} L: {losses}
              P&L: ₹{daily_pnl} | Balance: ₹{balance}"

File: config.py
- Action: ADD LINES in a new TELEGRAM section
    TELEGRAM_TOKEN   = ""   # paste bot token here
    TELEGRAM_CHAT_ID = ""   # paste chat ID here
    TELEGRAM_ENABLED = False # set True to activate

File: bot.py
- Action: ADD CALLS at correct points (do not restructure bot.py):
    After signal confirmed     → alert_signal()
    After entry order placed   → alert_entry()
    After SL hit exit          → alert_exit(result="LOSS")
    After target hit exit      → alert_exit(result="WIN")
    At 15:31 daily reset       → alert_daily_summary()
- Import: from alerts.telegram_alert import *
- Guard all calls with: if config.TELEGRAM_ENABLED

### INTEGRATION POINTS
alerts/telegram_alert.py is standalone — imports only config and requests.
bot.py imports and calls alert functions at 5 trigger points.
config.py holds credentials and on/off switch.

### ACCEPTANCE CRITERIA
1. All 5 alert functions send correctly formatted Telegram messages
2. TELEGRAM_ENABLED = False completely disables all alerts (no API calls)
3. Telegram failures never crash or pause the bot
4. Credentials stored only in config.py — not hardcoded in alert file
5. Daily summary fires at exactly 15:31 IST daily reset point

### CONSTRAINTS
- Language: Python 3.10+
- New dependency allowed: none (use built-in requests already in stack)
- No telegram SDK — use raw HTTP only
- Complete file — no truncation
```

---

## 🟢 IMPROVEMENT: P10 — Streamlit Dashboard

```
## GPT INSTRUCTION PACKET
**Task ID:** IMPROVE-P10-STREAMLIT-DASHBOARD
**Bot Version:** Nifty50 v1.0 (March 2026)

### CONTEXT SUMMARY
No web dashboard exists. Currently stats are log-file only.
P10 requires a Streamlit dashboard showing live equity curve,
open position, and daily stats — reading from existing CSV trade log.

### ROOT CAUSE / DESIGN DECISION
Read from trade_log CSV (already written by utils/trade_logger.py).
Auto-refresh every 60 seconds using st.rerun().
No direct connection to Dhan API needed — dashboard is read-only display.

### EXACT CHANGES REQUIRED

File: dashboard/streamlit_app.py (CREATE NEW FILE)
- Action: CREATE
- Sections required:

  SECTION 1 — Header
    Title: "Nifty 50 Bot — Live Dashboard"
    Show current IST time. Auto-refresh every 60s.

  SECTION 2 — Key Metrics Row (st.metric cards)
    Current Balance | Today's P&L | Win Rate % | Trades Today | Open Position

  SECTION 3 — Equity Curve Chart
    Read trade log CSV
    Plot cumulative balance over all trades using st.line_chart
    X-axis: trade number | Y-axis: balance in ₹

  SECTION 4 — Open Position Panel
    If a trade is currently open (last row has no exit price):
      Show: Direction, Entry, SL, Target, Current P&L (unrealised)
    Else: "No open position"

  SECTION 5 — Trade Log Table
    Show last 20 trades from CSV in st.dataframe
    Colour WIN rows green, LOSS rows red using pandas Styler

  SECTION 6 — Daily Stats Bar Chart
    Show win/loss count per day for last 10 trading days

- Read from: path in config.py TRADE_LOG_PATH
- On file not found: show "No trade data yet" cleanly

File: config.py
- Action: ADD LINE
    TRADE_LOG_PATH = "logs/trade_log.csv"   # adjust if different

File: requirements_dashboard.txt (CREATE NEW FILE)
- Action: CREATE with content:
    streamlit>=1.30.0

### INTEGRATION POINTS
Dashboard reads TRADE_LOG_PATH from config.py.
No write access to any file — read-only.
Run separately: streamlit run dashboard/streamlit_app.py

### ACCEPTANCE CRITERIA
1. Dashboard loads without error when trade_log CSV exists
2. Dashboard shows "No trade data yet" cleanly when CSV is missing
3. Equity curve plots correctly from CSV balance column
4. Auto-refresh works every 60 seconds
5. Trade log table shows last 20 rows with win/loss colouring
6. Dashboard runs independently of bot.py (separate process)

### CONSTRAINTS
- Language: Python 3.10+
- New dependency allowed: streamlit >= 1.30.0 only
- Complete file — no truncation
- No direct Dhan API calls in dashboard
```

---
---

# ════════════════════════════════════════
# PART 4 — SESSION CONTINUITY TEMPLATE
# ════════════════════════════════════════

## Paste this at the START of every new GPT session to resume work:

```
Continue building my Nifty 50 trading bot.

[CURRENT BUILD STATUS]
config.py                        ✅ Complete
core/dhan_client.py              ✅ Complete
core/indicators.py               ✅ Complete
core/risk_manager.py             ✅ Complete
strategies/ema_crossover.py      ✅ Complete
bot.py                           ✅ Complete
utils/trade_logger.py            ✅ Complete
backtester/backtest.py           ✅ Complete
backtester/backtest_daily.py     ✅ Complete
backtester/data_fetcher.py       ✅ Complete
alerts/telegram_alert.py         [STATUS]
dashboard/streamlit_app.py       [STATUS]
BUG B1 (VIX feed)                [STATUS]
BUG B2 (Options security_id)     [STATUS]
TRAILING SL (P3)                 [STATUS]

Last session: [describe what was done]
Current error / next task: [describe]

[PASTE RELEVANT INSTRUCTION PACKET BELOW]
```

---
---

# ════════════════════════════════════════
# PART 5 — RULES TO NEVER HIT LIMITS
# ════════════════════════════════════════

```
RULE 1 → NEVER ask Claude to write code — not one line
RULE 2 → NEVER ask Claude to debug errors — that's GPT's job
RULE 3 → NEVER regenerate the Claude base prompt — it's saved in this doc
RULE 4 → Use the Pre-Built Packets (Part 3) for the 6 known bugs/improvements
         — these skip Claude entirely
RULE 5 → Only open Claude when you need NEW strategy thinking or NEW feature design
RULE 6 → Save every Claude output immediately — never regenerate
RULE 7 → One task per GPT session — finish before starting another
RULE 8 → Always paste Session Continuity Template at start of new GPT chat
         — eliminates all "remind me of the context" back-and-forth
```

---

## USAGE DECISION TREE

```
Got a task? →

Is it a BUG from B1–B6?
  YES → Use Pre-Built Packet from Part 3 → Paste into GPT
  NO  ↓

Is it an IMPROVEMENT from P1–P10?
  YES → Is there a Pre-Built Packet in Part 3?
    YES → Use it → Paste into GPT
    NO  → Go to Claude with Part 1 prompt → Get packet → Paste into GPT
  NO  ↓

Is it a NEW FEATURE or STRATEGY CHANGE?
  YES → Go to Claude with Part 1 prompt → Get packet → Paste into GPT
  NO  ↓

Is it a CODE ERROR or DEBUG?
  YES → Go directly to GPT → "Debug [filename] — [paste error]"
```

---

*Built by Lyra — Hybrid Prompt System for Nifty50 Bot v1.0 | March 2026*
*Claude = Think Once. GPT = Build Always. Save Everything.*
