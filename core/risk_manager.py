"""
Risk Manager — enforces all 10 unbreakable laws from the trading system.
Calculates position size, SL, target and validates trade eligibility.
"""

import logging
from dataclasses import dataclass, field
from datetime import datetime, time
from typing import Optional
import config

logger = logging.getLogger(__name__)


@dataclass
class TradeSetup:
    direction: str          # "LONG" or "SHORT"
    entry: float
    sl: float
    target: float
    quantity: int
    risk_amount: float
    target_profit: float
    setup_type: str = ""
    option_type: str = ""   # "CE" or "PE"
    option_strike: float = 0.0


@dataclass 
class DailyStats:
    trades_taken: int = 0
    wins: int = 0
    losses: int = 0
    consecutive_losses: int = 0
    daily_pnl: float = 0.0
    peak_balance: float = 0.0
    drawdown: float = 0.0


class RiskManager:

    def __init__(self, capital: float, phase: str = "paper"):
        self.capital = capital
        self.phase = phase
        self.daily = DailyStats(peak_balance=capital)
        self._effective_risk = config.PHASE_RISK.get(phase, config.RISK_PER_TRADE)

    # ─── TIME WINDOW CHECKS ───────────────────────────────────────────────────

    def is_prime_session(self, now: Optional[datetime] = None) -> bool:
        """True if current time is inside a prime trading window."""
        now = now or datetime.now()
        t = now.time()
        s1_start = time(9, 30)
        s1_end   = time(11, 30)
        s2_start = time(13, 30)
        s2_end   = time(14, 45)
        return (s1_start <= t <= s1_end) or (s2_start <= t <= s2_end)

    def is_time_stop(self, now: Optional[datetime] = None) -> bool:
        now = now or datetime.now()
        return now.time() >= time(14, 45)

    def is_danger_zone(self, now: Optional[datetime] = None) -> bool:
        now = now or datetime.now()
        t = now.time()
        return t < time(9, 30) or t >= time(14, 45)

    # ─── POSITION SIZING ──────────────────────────────────────────────────────

    def calculate_quantity(self, entry: float, sl: float, vix: float = None) -> tuple:
        """
        Returns (quantity, risk_amount, target_price, target_profit).
        Adjusts for VIX and trading phase.
        """
        risk_pct = self._effective_risk

        # VIX adjustment: halve size if VIX > 20
        if vix and vix > config.VIX_HIGH:
            risk_pct *= 0.5
            logger.info("VIX=%s > 20 — position size halved to %.1f%%", vix, risk_pct * 100)

        risk_amount = self.capital * risk_pct
        sl_distance = abs(entry - sl)

        if sl_distance <= 0:
            raise ValueError("SL distance must be > 0")

        quantity = max(1, int(risk_amount / sl_distance))
        target_distance = sl_distance * config.RR_RATIO
        
        if entry > sl:  # LONG
            target = entry + target_distance
        else:           # SHORT
            target = entry - target_distance

        target_profit = target_distance * quantity
        return quantity, risk_amount, round(target, 2), round(target_profit, 2)

    # ─── TRADE VALIDATION (13-gate checklist) ────────────────────────────────

    def validate_trade(
        self,
        market_structure: str,
        direction: str,
        rsi: float,
        vol_ratio: float,
        price_vs_vwap: str,   # "above" or "below"
        vix: float = None,
        now: Optional[datetime] = None,
    ) -> tuple[bool, list[str]]:
        """
        Runs all 13 pre-trade gates.
        Returns (can_trade: bool, reasons: list[str]).
        """
        reasons = []

        # ── Market condition gates ──────────────────────────────────────────
        if not self.is_prime_session(now):
            reasons.append("SKIP: Outside prime trading window (9:30–11:30 or 13:30–14:45)")

        if market_structure == "ranging":
            reasons.append("SKIP: Market is ranging — no trade")

        if market_structure == "low_vol" or (vix and vix < config.VIX_LOW):
            reasons.append("SKIP: VIX too low (<12) — paper trade only")

        # ── Daily limits ────────────────────────────────────────────────────
        if self.daily.trades_taken >= config.MAX_TRADES_PER_DAY:
            reasons.append(f"SKIP: Max {config.MAX_TRADES_PER_DAY} trades per day reached")

        if self.daily.consecutive_losses >= config.MAX_CONSECUTIVE_LOSSES:
            reasons.append(f"SKIP: {self.daily.consecutive_losses} consecutive losses — stop trading today")

        daily_loss_limit = self.capital * config.MAX_DAILY_LOSS_PCT
        if self.daily.daily_pnl < -daily_loss_limit:
            reasons.append("SKIP: Daily loss limit exceeded")

        # ── Technical gates ─────────────────────────────────────────────────
        if direction == "LONG":
            if rsi <= config.RSI_BULL_MIN:
                reasons.append(f"SKIP: RSI {rsi:.1f} not above 50 for LONG")
            if price_vs_vwap != "above":
                reasons.append("SKIP: Price below VWAP — no LONG")
            if market_structure == "trending_down":
                reasons.append("SKIP: Market trending DOWN — no LONG")

        if direction == "SHORT":
            if rsi >= config.RSI_BEAR_MAX:
                reasons.append(f"SKIP: RSI {rsi:.1f} not below 50 for SHORT")
            if price_vs_vwap != "below":
                reasons.append("SKIP: Price above VWAP — no SHORT")
            if market_structure == "trending_up":
                reasons.append("SKIP: Market trending UP — no SHORT")

        # ── Volume gate ─────────────────────────────────────────────────────
        if vol_ratio < config.VOLUME_MULTIPLIER:
            reasons.append(f"SKIP: Volume {vol_ratio:.2f}x < 1.5x avg — no trade")

        can_trade = len(reasons) == 0
        return can_trade, reasons

    # ─── POST-TRADE TRACKING ──────────────────────────────────────────────────

    def record_trade(self, pnl: float):
        self.daily.trades_taken += 1
        self.daily.daily_pnl += pnl
        self.capital += pnl

        if pnl > 0:
            self.daily.wins += 1
            self.daily.consecutive_losses = 0
        else:
            self.daily.losses += 1
            self.daily.consecutive_losses += 1

        if self.capital > self.daily.peak_balance:
            self.daily.peak_balance = self.capital
        self.daily.drawdown = self.daily.peak_balance - self.capital

        logger.info(
            "Trade recorded | PnL=₹%.0f | Balance=₹%.0f | ConsecLoss=%d",
            pnl, self.capital, self.daily.consecutive_losses
        )

    def reset_daily(self):
        self.daily = DailyStats(peak_balance=self.capital)
        logger.info("Daily stats reset. Capital=₹%.0f", self.capital)
