"""Alpaca broker adapter — PAPER ONLY, hard-guarded.

Safety design:
  * Refuses to initialise against a non-paper endpoint (no real money, ever).
  * ``dry_run=True`` by default — logs intended orders without sending.
  * alpaca-py is imported lazily; absent library -> dry-run only.

This adapter never decides *what* to trade — it only executes target weights the
governed DecisionEngine produced, in a paper account.
"""
from __future__ import annotations

from typing import Dict, List, Optional

from ..utils import get_logger

log = get_logger("alpaca")

_PAPER_URL = "https://paper-api.alpaca.markets"


class AlpacaPaperAdapter:
    def __init__(self, api_key: Optional[str] = None, secret_key: Optional[str] = None,
                 dry_run: bool = True, base_url: str = _PAPER_URL):
        # HARD GUARD: only the paper endpoint is allowed.
        if "paper" not in base_url:
            raise ValueError("AlpacaPaperAdapter refuses non-paper endpoints (real money). "
                             f"Got: {base_url}")
        self.dry_run = dry_run
        self.base_url = base_url
        self._client = None
        if not dry_run:
            self._client = self._connect(api_key, secret_key)

    def _connect(self, api_key, secret_key):
        try:
            from alpaca.trading.client import TradingClient
            client = TradingClient(api_key, secret_key, paper=True)  # paper=True enforced
            acct = client.get_account()
            log.info("Connected to Alpaca PAPER account: status=%s cash=%s",
                     getattr(acct, "status", "?"), getattr(acct, "cash", "?"))
            return client
        except Exception as e:
            log.warning("Alpaca connect failed (%s) -> falling back to DRY-RUN.", e)
            self.dry_run = True
            return None

    def account_equity(self) -> Optional[float]:
        if self._client is None:
            return None
        try:
            return float(self._client.get_account().equity)
        except Exception:
            return None

    def submit_target_weights(self, targets: Dict[str, float], equity: float) -> List[dict]:
        """Translate target weights into (paper) notional orders.

        Returns a list of intended/placed order records. In dry-run, nothing is
        sent — the records are logged for the shadow portfolio.
        """
        orders = []
        for asset, w in targets.items():
            notional = round(equity * max(w, 0.0), 2)
            rec = {"asset": asset, "target_weight": round(w, 4), "notional": notional,
                   "mode": "DRY_RUN" if self.dry_run else "PAPER"}
            if self.dry_run or self._client is None:
                log.info("[DRY_RUN] would target %s -> %.2f%% ($%.2f)", asset, w * 100, notional)
            else:
                try:
                    from alpaca.trading.requests import MarketOrderRequest
                    from alpaca.trading.enums import OrderSide, TimeInForce
                    if notional > 0:
                        self._client.submit_order(MarketOrderRequest(
                            symbol=asset, notional=notional, side=OrderSide.BUY,
                            time_in_force=TimeInForce.DAY))
                        rec["status"] = "submitted"
                except Exception as e:
                    rec["status"] = f"error: {e}"
                    log.warning("Order error %s: %s", asset, e)
            orders.append(rec)
        return orders
