"""
Dhan API Client — wraps dhanhq SDK for order placement, market data, positions.
Docs: https://dhanhq.co/docs/v2/
"""

import logging
from typing import Optional
from datetime import datetime

logger = logging.getLogger(__name__)

try:
    from dhanhq import dhanhq
    DHAN_AVAILABLE = True
except ImportError:
    DHAN_AVAILABLE = False
    logger.warning("dhanhq not installed. Run: pip install dhanhq")


class DhanClient:
    """
    Thin wrapper around dhanhq SDK.
    All order/position calls are paper-trade safe — if phase='paper' they log
    but never hit the API.
    """

    def __init__(self, client_id: str, access_token: str, paper_trade: bool = True):
        self.client_id = client_id
        self.access_token = access_token
        self.paper_trade = paper_trade
        self._dhan = None

        if not paper_trade:
            if not DHAN_AVAILABLE:
                raise RuntimeError("dhanhq package required for live trading.")
            self._dhan = dhanhq(client_id, access_token)
            logger.info("Dhan live client initialised for client_id=%s", client_id)
        else:
            logger.info("Paper trade mode — no real orders will be placed.")

    # ─── MARKET DATA ──────────────────────────────────────────────────────────

    def get_ltp(self, security_id: str, exchange_segment: str) -> Optional[float]:
        """Last traded price."""
        if self.paper_trade:
            logger.debug("Paper: get_ltp(%s)", security_id)
            return None
        try:
            resp = self._dhan.get_ltp_data(
                security_id=security_id,
                exchange_segment=exchange_segment
            )
            return float(resp["data"]["last_price"])
        except Exception as e:
            logger.error("get_ltp error: %s", e)
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
        Fetch OHLCV candles.
        interval: '1', '5', '15', '25', '60' (minutes) or 'D' (daily)
        """
        if self.paper_trade:
            logger.debug("Paper: get_historical_data(%s, %s)", security_id, interval)
            return None
        try:
            resp = self._dhan.historical_minute_charts(
                symbol=security_id,
                exchange_segment=exchange_segment,
                instrument_type=instrument_type,
                expiry_code=0,
                from_date=from_date,
                to_date=to_date,
            )
            return resp
        except Exception as e:
            logger.error("get_historical_data error: %s", e)
            return None

    def get_option_chain(self, underlying: str, expiry: str) -> Optional[dict]:
        """Fetch option chain for strike selection."""
        if self.paper_trade:
            logger.debug("Paper: get_option_chain(%s)", underlying)
            return None
        try:
            resp = self._dhan.get_option_chain(
                underlying=underlying,
                expiry=expiry
            )
            return resp
        except Exception as e:
            logger.error("get_option_chain error: %s", e)
            return None

    # ─── ORDER MANAGEMENT ─────────────────────────────────────────────────────

    def place_market_order(
        self,
        security_id: str,
        exchange_segment: str,
        transaction_type: str,   # "BUY" or "SELL"
        quantity: int,
        product_type: str = "INTRADAY",
    ) -> Optional[dict]:
        """Place a market order."""
        order_info = {
            "security_id": security_id,
            "exchange_segment": exchange_segment,
            "transaction_type": transaction_type,
            "quantity": quantity,
            "product_type": product_type,
            "order_type": "MARKET",
            "timestamp": datetime.now().isoformat(),
        }
        if self.paper_trade:
            logger.info("PAPER ORDER: %s", order_info)
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
            logger.info("Order placed: %s", resp)
            return resp
        except Exception as e:
            logger.error("place_market_order error: %s", e)
            return None

    def place_sl_order(
        self,
        security_id: str,
        exchange_segment: str,
        transaction_type: str,
        quantity: int,
        trigger_price: float,
        price: float,
        product_type: str = "INTRADAY",
    ) -> Optional[dict]:
        """Place a stop-loss order (SL-M)."""
        order_info = {
            "security_id": security_id,
            "transaction_type": transaction_type,
            "quantity": quantity,
            "trigger_price": trigger_price,
            "price": price,
        }
        if self.paper_trade:
            logger.info("PAPER SL ORDER: %s", order_info)
            return {"status": "paper", "order_id": f"PAPER_SL_{datetime.now().strftime('%H%M%S')}"}
        try:
            resp = self._dhan.place_order(
                security_id=security_id,
                exchange_segment=exchange_segment,
                transaction_type=transaction_type,
                quantity=quantity,
                order_type=self._dhan.SL,
                product_type=self._dhan.INTRA,
                price=price,
                trigger_price=trigger_price,
            )
            return resp
        except Exception as e:
            logger.error("place_sl_order error: %s", e)
            return None

    def cancel_order(self, order_id: str) -> Optional[dict]:
        if self.paper_trade:
            logger.info("PAPER: cancel_order(%s)", order_id)
            return {"status": "paper_cancelled"}
        try:
            return self._dhan.cancel_order(order_id)
        except Exception as e:
            logger.error("cancel_order error: %s", e)
            return None

    def get_positions(self) -> Optional[list]:
        if self.paper_trade:
            return []
        try:
            resp = self._dhan.get_positions()
            return resp.get("data", [])
        except Exception as e:
            logger.error("get_positions error: %s", e)
            return []

    def get_order_book(self) -> Optional[list]:
        if self.paper_trade:
            return []
        try:
            resp = self._dhan.get_order_list()
            return resp.get("data", [])
        except Exception as e:
            logger.error("get_order_book error: %s", e)
            return []

    def get_funds(self) -> Optional[dict]:
        if self.paper_trade:
            return {"availabelBalance": 50000}
        try:
            resp = self._dhan.get_fund_limits()
            return resp.get("data", {})
        except Exception as e:
            logger.error("get_funds error: %s", e)
            return {}
