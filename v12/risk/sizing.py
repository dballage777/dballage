"""Risk sizing & overlays: volatility targeting, Kelly, CVaR, cash regime."""
from __future__ import annotations

import numpy as np
import pandas as pd


def vol_target_scalar(portfolio_rets: pd.Series, target_annual: float,
                      window: int = 20, max_leverage: float = 1.0) -> float:
    """Exposure multiplier to steer realised vol toward ``target_annual``.

    Capped at ``max_leverage`` (default 1.0 = no leverage, cash-only de-risking).
    """
    if target_annual is None or len(portfolio_rets) < 5:
        return 1.0
    realized = portfolio_rets.tail(window).std() * np.sqrt(252)
    if realized == 0 or np.isnan(realized):
        return 1.0
    return float(min(target_annual / realized, max_leverage))


def kelly_fraction(rets: pd.Series, cap: float = 0.5) -> float:
    """Fractional-Kelly exposure from mean/variance of recent returns."""
    mu = rets.mean()
    var = rets.var()
    if var == 0 or np.isnan(var):
        return 0.0
    return float(np.clip(mu / var, 0, cap))


def cvar(rets: pd.Series, alpha: float = 0.05) -> float:
    """Conditional Value-at-Risk (expected shortfall) at level ``alpha``."""
    if len(rets) == 0:
        return 0.0
    var = np.quantile(rets, alpha)
    tail = rets[rets <= var]
    return float(tail.mean()) if len(tail) else float(var)


def cash_regime_scalar(breadth_pct_above_200: float, market_vol: float,
                       vol_ceiling: float = 0.30) -> float:
    """Risk-off overlay: scale exposure down in weak-breadth / high-vol regimes.

    Returns a multiplier in [0, 1]. This is the 'cash regime' from the directive
    — capital simply goes uninvested when conditions are hostile.
    """
    breadth_score = np.clip(breadth_pct_above_200 / 0.5, 0, 1)  # 0.5 => full risk
    vol_score = np.clip(vol_ceiling / max(market_vol, 1e-6), 0, 1)
    return float(np.clip(0.5 * breadth_score + 0.5 * vol_score, 0, 1))
