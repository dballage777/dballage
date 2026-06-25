"""Microcap classification + cap enforcement (GOAL: experimental only).

Stocks: microcaps capped at 10% aggregate / 1% per position. Our default
universe contains no microcaps, so this is enforcement scaffolding — a name is
microcap only if explicitly listed or below the market-cap threshold.
"""
from __future__ import annotations

from typing import Dict, Optional, Set

import pandas as pd

MICROCAP_MARKETCAP = 2e9   # < $2B = microcap


def is_microcap(ticker: str, market_cap: Optional[float] = None,
                microcap_set: Optional[Set[str]] = None) -> bool:
    if microcap_set and ticker in microcap_set:
        return True
    if market_cap is not None:
        return market_cap < MICROCAP_MARKETCAP
    return False


def enforce_microcap_caps(weights: pd.Series, microcap_set: Optional[Set[str]] = None,
                          market_caps: Optional[Dict[str, float]] = None,
                          max_agg: float = 0.10, max_pos: float = 0.01) -> pd.Series:
    """Cap each microcap at ``max_pos`` and their aggregate at ``max_agg``."""
    if weights.empty:
        return weights
    market_caps = market_caps or {}
    mc = pd.Series({t: is_microcap(t, market_caps.get(t), microcap_set) for t in weights.index})
    w = weights.copy()
    if not mc.any():
        return w                                   # no microcaps -> nothing to cap
    w[mc] = w[mc].clip(upper=max_pos)              # per-position cap
    agg = w[mc].sum()
    if agg > max_agg and agg > 0:
        w[mc] = w[mc] * (max_agg / agg)            # aggregate cap
    return w
