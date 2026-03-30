"""
Nifty 50 Intraday Trading System — Configuration
All parameters pulled from Nifty50_Trading_System.xlsx
"""

# Secrets are kept in `secrets_local.py` (ignored by git).
# This keeps personal API keys out of the repository.
try:
    from secrets_local import (
        DHAN_CLIENT_ID,
        DHAN_ACCESS_TOKEN,
        DHAN_API_KEY,
        DHAN_API_SECRET,
    )
except ImportError:
    DHAN_CLIENT_ID = ""
    DHAN_ACCESS_TOKEN = ""
    DHAN_API_KEY = ""
    DHAN_API_SECRET = ""

# ─── ACCOUNT ─────────────────────────────────────────────────────────────────
# ─── CAPITAL & RISK ───────────────────────────────────────────────────────────
INITIAL_CAPITAL = 50_000        # Starting capital ₹
RISK_PER_TRADE = 0.03           # 3% risk per trade
RR_RATIO = 1.5                  # Reward:Risk = 1:1.5
MAX_TRADES_PER_DAY = 2
MAX_CONSECUTIVE_LOSSES = 2      # Stop after 2 losses in a row
MAX_DAILY_LOSS_PCT = 0.06       # 6% daily loss limit (2 full losses)

# ─── INSTRUMENT ───────────────────────────────────────────────────────────────
UNDERLYING = "NIFTY"
EXCHANGE = "NSE"
SEGMENT = "IDX_I"               # Index segment
SECURITY_ID = "13"              # Nifty 50 security ID on Dhan

# ─── OPTIONS SETTINGS ─────────────────────────────────────────────────────────
OPTION_EXCHANGE = "NSE"
OPTION_SEGMENT = "D"            # Derivatives
LOT_SIZE = 50                   # Nifty lot size
STRIKE_OFFSET = 0               # 0 = ATM, 1 = 1 OTM, -1 = 1 ITM
EXPIRY_PREFERENCE = "weekly"    # weekly or monthly

# ─── TECHNICAL INDICATORS ─────────────────────────────────────────────────────
EMA_FAST = 20
EMA_SLOW = 50
RSI_PERIOD = 14
RSI_BULL_MIN = 50               # RSI must be above 50 for LONG
RSI_BEAR_MAX = 50               # RSI must be below 50 for SHORT
VOLUME_MULTIPLIER = 1.5         # Volume must be 1.5x 20-period avg
VWAP_DEVIATION_PCT = 0.001      # 0.1% tolerance around VWAP

# ─── VIX THRESHOLDS ───────────────────────────────────────────────────────────
VIX_HIGH = 20                   # Reduce size 50% if VIX > 20
VIX_LOW = 12                    # Skip if VIX < 12

# ─── TRADING WINDOWS (IST) ────────────────────────────────────────────────────
PRIME_SESSION_1_START = "09:30"
PRIME_SESSION_1_END   = "11:30"
PRIME_SESSION_2_START = "13:30"
PRIME_SESSION_2_END   = "14:45"
TIME_STOP             = "14:45"  # Exit all positions
DANGER_ZONE_AM_END    = "09:30"
DANGER_ZONE_PM_START  = "14:45"

# ─── TIMEFRAMES ───────────────────────────────────────────────────────────────
SIGNAL_TF  = "5"    # 5-min chart for entry signals (minutes)
TREND_TF   = "15"   # 15-min chart for trend direction (minutes)

# ─── LOGGING ──────────────────────────────────────────────────────────────────
LOG_DIR = "logs"
TRADE_LOG_CSV = "logs/trade_log.csv"
BACKTEST_RESULTS_CSV = "logs/backtest_results.csv"

# ─── PHASE (from 90-Day Roadmap) ─────────────────────────────────────────────
# "paper"    → Days 1–30:  paper trade, zero real money
# "half"     → Days 31–60: live at 1.5% risk (half size)
# "full"     → Days 61–90: full 3% risk, compounding active
TRADING_PHASE = "paper"

PHASE_RISK = {
    "paper": 0.00,   # No real money
    "half":  0.015,  # 1.5%
    "full":  0.03,   # 3%
}
