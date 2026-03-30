# Nifty50 Intraday Trading Bot — Project Context

Use this context for every new chat in this repo.

## Source docs (authoritative)
- `README.md`: project structure, data fetching, how to run paper/half/full, and overall pipeline/backtesting usage.
- `NIFTY50_BOT_SPEC.md`: exact strategy gates, indicator settings, risk rules, and entry/exit formulas.

## Strategy (authoritative parameters)
Instrument: Nifty 50 (NSE) — intraday only. Execution: Dhan broker API.

Indicator settings:
- EMA Fast: 20 (EWM span=20, adjust=False) on close
- EMA Slow: 50 (EWM span=50, adjust=False) on close
- RSI: period 14, Wilder smoothing via EWM (com=13, adjust=False); bullish if RSI > 50, bearish if RSI < 50
- VWAP: intraday, resets each trading day; typical price = (H+L+C)/3; cumulative(Typical*Vol)/cumulative(Vol); applied on 5-min only
- Volume confirmation: `volume_ratio = current_volume / SMA(volume, 20)`, require `volume_ratio >= 1.5`
- Crossover freshness: EMA20 crosses EMA50 within last 3 candles

Trading windows (IST):
- Trade only in `09:30–11:30` OR `13:30–14:45`
- Time stop: force-exit at `14:45`

Market structure on every bar (15-min):
- `trending_up`: EMA20_15m > EMA50_15m AND close_15m > VWAP_15m => LONG setups only
- `trending_down`: EMA20_15m < EMA50_15m AND close_15m < VWAP_15m => SHORT setups only
- `ranging`: neither => NO TRADE

Entry logic (13 gates; LONG = all must be TRUE, SHORT = all must be TRUE):
- Gate 1 (Time): within the two prime windows above
- Gate 2 (Daily limit): trades_taken_today < 2
- Gate 3 (Loss limit): consecutive_losses < 2
- Gate 4 (Daily P&L): daily_pnl > -(capital * 0.06)
- Gate 5 (Market): trending_up (LONG) / trending_down (SHORT)
- Gate 6 (Crossover): EMA20_5m crossed above/below EMA50_5m within last 3 candles
- Gate 7 (VWAP): close_5m > VWAP_5m (LONG) / close_5m < VWAP_5m (SHORT)
- Gate 8 (RSI): RSI_5m > 50 (LONG) / RSI_5m < 50 (SHORT)
- Gate 9 (Volume): volume_ratio_5m >= 1.5
- Gate 10 (VIX): if VIX feed enabled, require `VIX not < 12` (skip when VIX < 12)
- Gate 11 (Flat): no open position currently held
- Gate 12 (SL valid): LONG (entry - sl_price) > 0 / SHORT (sl_price - entry) > 0
- Gate 13 (Qty valid): calculated_quantity >= 1

VIX adjustments:
- If VIX > 20: halve position size (risk becomes 1.5% per trade)
- If VIX < 12: skip trade entirely

Options translation:
- LONG => buy ATM Call (CE)
- SHORT => buy ATM Put (PE)
- Strike interval: 50 points
- Expiry preference: weekly (Thursday)
- For VIX <= 20: allow 1 OTM strike (lower cost, higher reward)
- For VIX > 20: ATM only (avoid gamma risk)
- Ranging market => no trade

SL/Target (hard formulas):
- LONG: SL = MIN(signal_candle_low, prev_candle_low); Target = Entry + (SL_dist * 1.5)
- SHORT: SL = MAX(signal_candle_high, prev_candle_high); Target = Entry - (SL_dist * 1.5)

Risk management core:
- Risk per trade: 3% of current capital (or 1.5% if VIX > 20)
- Max trades/day: 2
- Max consecutive losses: 2

## Repo layout (where code lives)
- `config.py`: credentials and core constants (capital, risk, timeframes, thresholds)
- `bot.py`: live/paper trading loop, signal checks, order placement, SL/time-stop handling
- `core/`: Dhan client wrapper, indicators, risk manager
- `strategies/`: signal generator (EMA crossover + confirmation model)
- `backtester/`: intraday + daily backtests + pipelines
- `utils/`: trade logging utilities

## Working rules for the assistant
- Treat `README.md` + `NIFTY50_BOT_SPEC.md` as authoritative when discussing strategy or behavior.
- Match existing code style; do not remove existing logic unless explicitly asked.
- Avoid new dependencies unless required; keep changes focused and minimal.
- Never commit `config.py` to the repo while it contains personal Dhan API keys. Only proceed when you explicitly confirm secrets have been moved out.
- Never commit `secrets_local.py` (contains private Dhan API credentials).
