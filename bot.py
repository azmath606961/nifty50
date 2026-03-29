"""
Nifty 50 Intraday Trading Bot — Live Execution Engine
Connects to Dhan, fetches real-time data, runs signals, places orders.

Usage:
    python bot.py                      # paper trade (default)
    python bot.py --phase half         # half-size live
    python bot.py --phase full         # full live
    python bot.py --interval 60        # poll every 60 seconds
"""

import argparse
import logging
import time
import sys
import os
from datetime import datetime, date

import pandas as pd

# Add parent dir to path when running directly
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import config
from core.dhan_client import DhanClient
from core.indicators import add_indicators, market_structure
from core.risk_manager import RiskManager
from strategies.ema_crossover import generate_signal
from utils.trade_logger import TradeLogger, TradeRecord

# ─── LOGGING SETUP ────────────────────────────────────────────────────────────
os.makedirs("logs", exist_ok=True)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(message)s",
    handlers=[
        logging.FileHandler(f"logs/bot_{date.today()}.log"),
        logging.StreamHandler(sys.stdout),
    ],
)
logger = logging.getLogger(__name__)


class TradingBot:

    def __init__(self, phase: str = "paper", poll_interval: int = 60):
        self.phase = phase
        self.poll_interval = poll_interval
        self.is_paper = (phase == "paper")

        logger.info("=" * 65)
        logger.info("  🏦 Nifty 50 Intraday Bot starting | Phase=%s | Paper=%s",
                    phase.upper(), self.is_paper)
        logger.info("=" * 65)

        # Initialise components
        self.dhan = DhanClient(
            client_id=config.DHAN_CLIENT_ID,
            access_token=config.DHAN_ACCESS_TOKEN,
            paper_trade=self.is_paper,
        )
        self.risk = RiskManager(capital=config.INITIAL_CAPITAL, phase=phase)
        self.trade_log = TradeLogger(
            csv_path=config.TRADE_LOG_CSV,
            initial_capital=config.INITIAL_CAPITAL,
        )

        self.open_trade: dict | None = None    # Currently open position
        self._last_signal_date = None

    # ─── DATA FETCHING ────────────────────────────────────────────────────────

    def _fetch_candles(self, interval: str, bars: int = 100) -> pd.DataFrame | None:
        """Fetch historical minute candles from Dhan."""
        today = date.today().strftime("%Y-%m-%d")
        # Dhan needs from_date ~30 days back for intraday
        from_date = pd.Timestamp.today() - pd.Timedelta(days=30)
        from_date_str = from_date.strftime("%Y-%m-%d")

        raw = self.dhan.get_historical_data(
            security_id=config.SECURITY_ID,
            exchange_segment=config.SEGMENT,
            instrument_type="INDEX",
            interval=interval,
            from_date=from_date_str,
            to_date=today,
        )

        if raw is None:
            # Paper mode — generate synthetic flat data for testing
            logger.debug("Paper: generating dummy candles")
            return self._dummy_candles(interval, bars)

        try:
            df = pd.DataFrame(raw["data"])
            df["datetime"] = pd.to_datetime(df["timestamp"], unit="s")
            df = df.set_index("datetime")
            df = df.rename(columns={
                "open": "open", "high": "high",
                "low": "low", "close": "close", "volume": "volume"
            })
            return df.tail(bars)
        except Exception as e:
            logger.error("Error parsing candle data: %s", e)
            return None

    def _dummy_candles(self, interval: str, bars: int) -> pd.DataFrame:
        """Generate realistic-looking synthetic Nifty data for paper testing."""
        import numpy as np
        np.random.seed(42)
        freq = f"{interval}min"
        idx = pd.date_range(end=pd.Timestamp.now(), periods=bars, freq=freq)
        base = 22000
        prices = base + np.cumsum(np.random.randn(bars) * 30)
        noise = np.random.randn(bars) * 10
        df = pd.DataFrame({
            "open":   prices + noise,
            "high":   prices + abs(noise) + np.random.uniform(5, 30, bars),
            "low":    prices - abs(noise) - np.random.uniform(5, 30, bars),
            "close":  prices,
            "volume": np.random.randint(50000, 200000, bars).astype(float),
        }, index=idx)
        return df

    def _get_vix(self) -> float | None:
        """Fetch India VIX. Returns None if unavailable."""
        # VIX security_id on NSE: 28 (India VIX)
        vix = self.dhan.get_ltp(security_id="28", exchange_segment="NSE")
        return vix

    # ─── OPTION STRIKE SELECTION ──────────────────────────────────────────────

    def _select_strike(self, spot: float, option_type: str, vix: float = None) -> tuple[int, str]:
        """
        Returns (strike, expiry_str).
        ATM for moderate signal, 1 OTM for strong trend.
        """
        # Round spot to nearest 50 (Nifty strike interval)
        atm = round(spot / 50) * 50

        # OTM if strong trend and VIX ≤ 20
        if vix and vix <= config.VIX_HIGH:
            if option_type == "CE":
                strike = atm + 50   # 1 OTM call
            else:
                strike = atm - 50   # 1 OTM put
        else:
            strike = atm            # ATM when VIX high

        # Weekly expiry (Thursday)
        today = pd.Timestamp.today()
        days_to_thursday = (3 - today.weekday()) % 7
        if days_to_thursday == 0 and today.hour >= 15:
            days_to_thursday = 7
        expiry = (today + pd.Timedelta(days=days_to_thursday)).strftime("%Y-%m-%d")

        return strike, expiry

    # ─── ORDER EXECUTION ──────────────────────────────────────────────────────

    def _enter_trade(self, signal: dict, vix: float = None):
        """Execute entry: place main order + SL order."""
        direction = signal["signal"]
        entry = signal["entry"]
        sl = signal["sl"]

        qty, risk_amt, target, target_profit = self.risk.calculate_quantity(entry, sl, vix)

        logger.info("─" * 55)
        logger.info("🚀 ENTERING %s TRADE", direction)
        logger.info("   Entry  : ₹%.2f", entry)
        logger.info("   SL     : ₹%.2f", sl)
        logger.info("   Target : ₹%.2f", target)
        logger.info("   Qty    : %d  | Risk: ₹%.0f | Target P&L: ₹%.0f",
                    qty, risk_amt, target_profit)

        tx_type = "BUY" if direction == "LONG" else "SELL"
        sl_tx_type = "SELL" if direction == "LONG" else "BUY"

        # For options trading
        option_type = signal.get("option")
        if option_type:
            strike, expiry = self._select_strike(entry, option_type, vix)
            logger.info("   Option : Nifty %s %d %s (expiry %s)",
                        option_type, strike, expiry, expiry)
            # In live mode this would use option security_id lookup
            security_id = f"NIFTY_{strike}_{option_type}_{expiry}"
        else:
            security_id = config.SECURITY_ID

        # Place entry order
        entry_order = self.dhan.place_market_order(
            security_id=security_id,
            exchange_segment=config.OPTION_EXCHANGE,
            transaction_type=tx_type,
            quantity=qty,
        )

        if entry_order is None:
            logger.error("Failed to place entry order — skipping trade")
            return

        # Place SL order
        sl_order = self.dhan.place_sl_order(
            security_id=security_id,
            exchange_segment=config.OPTION_EXCHANGE,
            transaction_type=sl_tx_type,
            quantity=qty,
            trigger_price=sl,
            price=sl * (0.99 if direction == "LONG" else 1.01),  # small buffer
        )

        self.open_trade = {
            "direction": direction,
            "entry": entry,
            "sl": sl,
            "target": target,
            "qty": qty,
            "risk": risk_amt,
            "target_profit": target_profit,
            "setup": signal.get("setup", ""),
            "option_type": option_type,
            "security_id": security_id,
            "entry_order_id": entry_order.get("order_id"),
            "sl_order_id": sl_order.get("order_id") if sl_order else None,
            "entry_time": datetime.now(),
            "entry_price": entry,
        }
        logger.info("✅ Trade open | Entry order: %s", entry_order.get("order_id"))

    def _exit_trade(self, exit_price: float, reason: str):
        """Close the open position."""
        if not self.open_trade:
            return

        t = self.open_trade
        direction = t["direction"]

        if direction == "LONG":
            pnl = (exit_price - t["entry"]) * t["qty"]
        else:
            pnl = (t["entry"] - exit_price) * t["qty"]

        result = "WIN" if pnl > 0 else "LOSS" if pnl < 0 else "BE"

        # Cancel SL order if still open
        if t.get("sl_order_id"):
            self.dhan.cancel_order(t["sl_order_id"])

        # Close position
        exit_tx = "SELL" if direction == "LONG" else "BUY"
        self.dhan.place_market_order(
            security_id=t["security_id"],
            exchange_segment=config.OPTION_EXCHANGE,
            transaction_type=exit_tx,
            quantity=t["qty"],
        )

        self.risk.record_trade(pnl)
        balance = self.risk.capital
        growth = (balance - config.INITIAL_CAPITAL) / config.INITIAL_CAPITAL

        # Log to CSV
        now = datetime.now()
        record = TradeRecord(
            date=now.strftime("%Y-%m-%d"),
            time=t["entry_time"].strftime("%H:%M"),
            setup_type=t["setup"],
            direction=direction,
            entry=t["entry"],
            sl=t["sl"],
            target=t["target"],
            qty=t["qty"],
            risk=t["risk"],
            target_profit=t["target_profit"],
            result=result,
            pnl=round(pnl, 2),
            balance=round(balance, 2),
            growth_pct=round(growth, 4),
            notes=f"Exit: {reason}",
        )
        self.trade_log.log(record)

        logger.info("─" * 55)
        logger.info("🏁 TRADE CLOSED | %s | P&L=₹%.0f | Balance=₹%.0f",
                    result, pnl, balance)
        logger.info("   Reason: %s", reason)
        self.open_trade = None

    # ─── MAIN LOOP ────────────────────────────────────────────────────────────

    def _check_open_trade(self, current_price: float) -> bool:
        """
        Check if open trade has hit SL, Target, or Time Stop.
        Returns True if trade was closed.
        """
        if not self.open_trade:
            return False

        t = self.open_trade
        direction = t["direction"]
        now = datetime.now()

        # Time stop
        if self.risk.is_time_stop(now):
            self._exit_trade(current_price, "Time stop 14:45")
            return True

        if direction == "LONG":
            if current_price <= t["sl"]:
                self._exit_trade(t["sl"], "Stop loss hit")
                return True
            if current_price >= t["target"]:
                self._exit_trade(t["target"], "Target hit ✅")
                return True
        else:
            if current_price >= t["sl"]:
                self._exit_trade(t["sl"], "Stop loss hit")
                return True
            if current_price <= t["target"]:
                self._exit_trade(t["target"], "Target hit ✅")
                return True

        return False

    def run(self):
        """Main event loop — runs during market hours."""
        logger.info("Bot running. Press Ctrl+C to stop.")

        while True:
            now = datetime.now()

            # ── Pre-market / post-market ──────────────────────────────────
            if now.hour < 9 or (now.hour == 9 and now.minute < 15):
                logger.info("Market not open yet. Waiting...")
                time.sleep(60)
                continue

            if now.hour >= 15 and now.minute >= 31:
                logger.info("Market closed. Resetting daily stats.")
                self.risk.reset_daily()
                if self.open_trade:
                    ltp = self.dhan.get_ltp(config.SECURITY_ID, config.SEGMENT) or self.open_trade["entry"]
                    self._exit_trade(ltp, "Market close")
                # Sleep until next morning
                time.sleep(3600)
                continue

            # ── Fetch live price ──────────────────────────────────────────
            ltp = self.dhan.get_ltp(config.SECURITY_ID, config.SEGMENT)
            if ltp is None and not self.is_paper:
                logger.warning("LTP fetch failed — retrying in 10s")
                time.sleep(10)
                continue

            # ── Check existing trade ──────────────────────────────────────
            if self.open_trade:
                price = ltp or self.open_trade["entry"]
                self._check_open_trade(price)
                time.sleep(self.poll_interval)
                continue

            # ── Gate checks ───────────────────────────────────────────────
            if not self.risk.is_prime_session(now):
                logger.debug("Outside prime session — waiting")
                time.sleep(30)
                continue

            if self.risk.daily.trades_taken >= config.MAX_TRADES_PER_DAY:
                logger.info("Max trades/day reached (%d). Done for today.",
                            config.MAX_TRADES_PER_DAY)
                time.sleep(300)
                continue

            if self.risk.daily.consecutive_losses >= config.MAX_CONSECUTIVE_LOSSES:
                logger.info("Consecutive losses %d reached — stopped for today.",
                            self.risk.daily.consecutive_losses)
                time.sleep(300)
                continue

            # ── Fetch candles and generate signal ─────────────────────────
            df5  = self._fetch_candles("5",  bars=80)
            df15 = self._fetch_candles("15", bars=80)
            vix  = self._get_vix()

            if df5 is None or df15 is None:
                logger.warning("Candle fetch failed — retrying")
                time.sleep(30)
                continue

            signal = generate_signal(df5, df15, vix)

            if signal["signal"] != "NONE":
                can_trade, reasons = self.risk.validate_trade(
                    market_structure=market_structure(add_indicators(df15)),
                    direction=signal["signal"],
                    rsi=add_indicators(df5).iloc[-1]["rsi"],
                    vol_ratio=add_indicators(df5).iloc[-1]["vol_ratio"],
                    price_vs_vwap="above" if signal["signal"] == "LONG" else "below",
                    vix=vix,
                    now=now,
                )
                if can_trade:
                    self._enter_trade(signal, vix)
                else:
                    for r in reasons:
                        logger.info("⛔ %s", r)
            else:
                logger.debug("No signal: %s", signal["reason"])

            time.sleep(self.poll_interval)


# ─── CLI ──────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Nifty 50 Intraday Trading Bot")
    parser.add_argument(
        "--phase", choices=["paper", "half", "full"], default="paper",
        help="Trading phase: paper (no real money) | half (1.5%% risk) | full (3%% risk)"
    )
    parser.add_argument("--interval", type=int, default=60,
                        help="Poll interval in seconds (default: 60)")
    args = parser.parse_args()

    bot = TradingBot(phase=args.phase, poll_interval=args.interval)
    try:
        bot.run()
    except KeyboardInterrupt:
        logger.info("Bot stopped by user.")
        if bot.open_trade:
            logger.warning("⚠️  There is an open trade — please close manually in Dhan!")
        summary = bot.trade_log.get_summary()
        if summary:
            logger.info("Session summary: %s", summary)
