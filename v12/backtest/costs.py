"""Transaction cost model: commission + slippage charged on turnover."""
from __future__ import annotations


def turnover_cost(turnover: float, commission_bps: float, slippage_bps: float) -> float:
    """Cost as a fraction of NAV for a given one-way turnover.

    ``turnover`` is sum(|w_new - w_old|). Each unit traded pays commission +
    slippage on one side; we treat the summed absolute change as the traded
    notional, which already counts both buys and sells.
    """
    return turnover * (commission_bps + slippage_bps) / 1e4
