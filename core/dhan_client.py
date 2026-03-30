"""
Dhan API Client — wraps dhanhq SDK v2.1+ for order placement and market data.
Correct method names as of dhanhq >= 2.1.0:
  - intraday_minute_data(security_id, exchange_segment, instrument_type)  [FREE - last 5 days]
  - historical_daily_data(security_id, exchange_segment, instrument_type, expiry_code, from_date, to_date)
  - v2 REST /charts/intraday for multi-day intraday history  [PAID plan]
"""

import logging
import requests as _requests
from typing import Optional
from datetime import datetime

logger = logging.getLogger(__name__)

try:
    from dhanhq import dhanhq, DhanContext
    DHAN_AVAILABLE = True
    DHAN_V2 = True
except ImportError:
    try:
        from dhanhq import dhanhq
        DhanContext = None
        DHAN_AVAILABLE = True
        DHAN_V2 = False
    except ImportError:
        DHAN_AVAILABLE = False
        DhanContext = None
        logger.warning("dhanhq not installed. Run: pip install dhanhq")


class DhanClient:
    """
    Thin wrapper around dhanhq SDK.
    Paper-trade safe — if paper_trade=True, logs all calls but never hits the API.
    """

    def __init__(self, client_id: str, access_token: str, paper_trade: bool = True):
        self.client_id    = client_id
        self.access_token = access_token
        self.paper_trade  = paper_trade
        self._dhan        = None

        if not paper_trade:
            if not DHAN_AVAILABLE:
                raise RuntimeError("dhanhq package required. Run: pip install dhanhq")
            if DhanContext:
                ctx = DhanContext(client_id, access_token)
                self._dhan = dhanhq(ctx)
            else:
                self._dhan = dhanhq(client_id, access_token)
            logger.info("[DHAN] Live client initialised for client_id=%s...", client_id[:6])
        else:
            logger.info("[DHAN] Paper trade mode — no real orders will be placed.")

    # ── MARKET DATA ──────────────────────────────────────────────────────────

    def get_ltp(self, security_id: str, exchange_segment: str) -> Optional[float]:
        """Last traded price."""
        if self.paper_trade:
            return None
        try:
            resp = self._dhan.get_ltp_data(
                security_id=security_id,
                exchange_segment=exchange_segment,
            )
            return float(resp["data"]["last_price"])
        except Exception as e:
            logger.error("[DHAN] get_ltp error: %s", e)
            return None

    def get_historical_data(
        self,
        security_id: str,
        exchange_segment: str,
        instrument_type: str,
        interval: str,
        from_date: str,
        to_date: str,
    ) -> Optional[dict]:
        """
        Historical intraday OHLCV via Dhan v2 REST API.
        interval: '1', '5', '15', '25', '60'
        from_date / to_date: 'YYYY-MM-DD'

        NOTE: Requires paid Data API plan (Rs 499/month).
              Free accounts only get last 5 days via get_intraday_today().
              Returns dict with keys: open, high, low, close, volume, timestamp (epoch int list)
        """
        if self.paper_trade:
            return None
        try:
            url = "https://api.dhan.co/v2/charts/intraday"
            headers = {
                "Content-Type": "application/json",
                "access-token": self.access_token,
            }
            payload = {
                "securityId":      security_id,
                "exchangeSegment": exchange_segment,
                "instrument":      instrument_type,
                "interval":        str(interval),
                "oi":              False,
                "fromDate":        f"{from_date} 09:15:00",
                "toDate":          f"{to_date} 15:30:00",
            }
            resp = _requests.post(url, headers=headers, json=payload, timeout=15)
            data = resp.json()
            if resp.status_code == 200 and "timestamp" in data and data["timestamp"]:
                return data
            logger.warning("[DHAN] get_historical_data: %s", str(data)[:200])
            return None
        except Exception as e:
            logger.error("[DHAN] get_historical_data error: %s", e)
            return None

    def get_intraday_today(
        self,
        security_id: str,
        exchange_segment: str,
        instrument_type: str,
    ) -> Optional[dict]:
        """
        FREE on all Dhan accounts — last 5 trading days of 1-min data.
        Correct v2.1 method: intraday_minute_data(security_id, exchange_segment, instrument_type)
        """
        if self.paper_trade:
            return None
        try:
            resp = self._dhan.intraday_minute_data(
                security_id=security_id,
                exchange_segment=exchange_segment,
                instrument_type=instrument_type,
            )
            return resp
        except Exception as e:
            logger.error("[DHAN] get_intraday_today error: %s", e)
            return None

    def get_daily_history(
        self,
        security_id: str,
        exchange_segment: str,
        instrument_type: str,
        from_date: str,
        to_date: str,
    ) -> Optional[dict]:
        """
        Daily OHLCV — FREE on all accounts, goes back to inception.
        Correct v2.1 method: historical_daily_data(security_id, ...) — NOT symbol.
        """
        if self.paper_trade:
            return None
        try:
            resp = self._dhan.historical_daily_data(
                security_id=security_id,
                exchange_segment=exchange_segment,
                instrument_type=instrument_type,
                expiry_code=0,
                from_date=from_date,
                to_date=to_date,
            )
            return resp
        except Exception as e:
            logger.error("[DHAN] get_daily_history error: %s", e)
            return None

    def get_option_chain(self, underlying: str, expiry: str) -> Optional[dict]:
        if self.paper_trade:
            return None
        try:
            return self._dhan.get_option_chain(underlying=underlying, expiry=expiry)
        except Exception as e:
            logger.error("[DHAN] get_option_chain error: %s", e)
            return None

    # ── ORDER MANAGEMENT ─────────────────────────────────────────────────────

    def place_market_order(
        self,
        security_id: str,
        exchange_segment: str,
        transaction_type: str,
        quantity: int,
        product_type: str = "INTRADAY",
    ) -> Optional[dict]:
        order_info = {
            "security_id": security_id,
            "transaction_type": transaction_type,
            "quantity": quantity,
            "timestamp": datetime.now().isoformat(),
        }
        if self.paper_trade:
            logger.info("[PAPER] MARKET ORDER: %s", order_info)
            return {"status": "paper", "order_id": f"PAPER_{datetime.now().strftime('%H%M%S')}"}
        try:
            resp = self._dhan.place_order(
                security_id=security_id,
                exchange_segment=exchange_segment,
                transaction_type=transaction_type,
                quantity=quantity,
                order_type=self._dhan.MARKET,
                product_type=self._dhan.INTRA,
                price=0,
            )
            logger.info("[DHAN] Order placed: %s", resp)
            return resp
        except Exception as e:
            logger.error("[DHAN] place_market_order error: %s", e)
            return None

    def place_sl_order(
        self,
        security_id: str,
        exchange_segment: str,
        transaction_type: str,
        quantity: int,
        trigger_price: float,
        price: float,
    ) -> Optional[dict]:
        if self.paper_trade:
            logger.info("[PAPER] SL ORDER: %s qty=%d trigger=%.2f", security_id, quantity, trigger_price)
            return {"status": "paper", "order_id": f"PAPER_SL_{datetime.now().strftime('%H%M%S')}"}
        try:
            return self._dhan.place_order(
                security_id=security_id,
                exchange_segment=exchange_segment,
                transaction_type=transaction_type,
                quantity=quantity,
                order_type=self._dhan.SL,
                product_type=self._dhan.INTRA,
                price=price,
                trigger_price=trigger_price,
            )
        except Exception as e:
            logger.error("[DHAN] place_sl_order error: %s", e)
            return None

    def cancel_order(self, order_id: str) -> Optional[dict]:
        if self.paper_trade:
            logger.info("[PAPER] cancel_order(%s)", order_id)
            return {"status": "paper_cancelled"}
        try:
            return self._dhan.cancel_order(order_id)
        except Exception as e:
            logger.error("[DHAN] cancel_order error: %s", e)
            return None

    def get_positions(self) -> list:
        if self.paper_trade:
            return []
        try:
            resp = self._dhan.get_positions()
            return resp.get("data", [])
        except Exception as e:
            logger.error("[DHAN] get_positions error: %s", e)
            return []

    def get_funds(self) -> dict:
        if self.paper_trade:
            return {"availabelBalance": 50000}
        try:
            resp = self._dhan.get_fund_limits()
            return resp.get("data", {})
        except Exception as e:
            logger.error("[DHAN] get_funds error: %s", e)
            return {}
