"""
Trade Logger — writes trades to CSV in same format as the Excel Trade Log sheet.
"""

import csv
import os
import logging
from datetime import datetime
from dataclasses import dataclass
from typing import Optional

logger = logging.getLogger(__name__)

HEADERS = [
    "Date", "Time", "Setup Type", "Direction", "Entry ₹", "SL ₹",
    "Target ₹", "Qty", "Risk ₹", "Target Profit ₹", "Result", "P&L ₹",
    "Balance ₹", "Growth %", "Notes"
]


@dataclass
class TradeRecord:
    date: str
    time: str
    setup_type: str
    direction: str
    entry: float
    sl: float
    target: float
    qty: int
    risk: float
    target_profit: float
    result: str        # "WIN", "LOSS", "BE", "OPEN"
    pnl: float
    balance: float
    growth_pct: float
    notes: str = ""


class TradeLogger:

    def __init__(self, csv_path: str, initial_capital: float):
        self.csv_path = csv_path
        self.initial_capital = initial_capital
        os.makedirs(os.path.dirname(csv_path), exist_ok=True)

        # Write headers if new file
        if not os.path.exists(csv_path):
            with open(csv_path, "w", newline="") as f:
                writer = csv.DictWriter(f, fieldnames=HEADERS)
                writer.writeheader()

    def log(self, record: TradeRecord):
        row = {
            "Date": record.date,
            "Time": record.time,
            "Setup Type": record.setup_type,
            "Direction": record.direction,
            "Entry ₹": record.entry,
            "SL ₹": record.sl,
            "Target ₹": record.target,
            "Qty": record.qty,
            "Risk ₹": round(record.risk, 2),
            "Target Profit ₹": round(record.target_profit, 2),
            "Result": record.result,
            "P&L ₹": round(record.pnl, 2),
            "Balance ₹": round(record.balance, 2),
            "Growth %": f"{record.growth_pct:.3%}",
            "Notes": record.notes,
        }
        with open(self.csv_path, "a", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=HEADERS)
            writer.writerow(row)
        logger.info("Trade logged: %s %s @ ₹%.0f | P&L=₹%.0f",
                    record.direction, record.setup_type, record.entry, record.pnl)

    def get_summary(self) -> dict:
        trades = []
        try:
            with open(self.csv_path, "r") as f:
                reader = csv.DictReader(f)
                trades = list(reader)
        except FileNotFoundError:
            return {}

        if not trades:
            return {}

        closed = [t for t in trades if t["Result"] in ("WIN", "LOSS", "BE")]
        wins = [t for t in closed if t["Result"] == "WIN"]
        losses = [t for t in closed if t["Result"] == "LOSS"]

        total_win = sum(float(t["P&L ₹"]) for t in wins)
        total_loss = abs(sum(float(t["P&L ₹"]) for t in losses))
        profit_factor = round(total_win / total_loss, 2) if total_loss else float("inf")
        win_rate = len(wins) / len(closed) if closed else 0

        last_balance = float(trades[-1]["Balance ₹"]) if trades else self.initial_capital

        return {
            "total_trades": len(closed),
            "wins": len(wins),
            "losses": len(losses),
            "win_rate": f"{win_rate:.1%}",
            "net_pnl": round(total_win - total_loss, 2),
            "profit_factor": profit_factor,
            "current_balance": last_balance,
            "growth": f"{(last_balance - self.initial_capital) / self.initial_capital:.1%}",
        }
