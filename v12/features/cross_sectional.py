"""Cross-sectional ranking.

Each date, rank names against each other on a base feature. Ranks are scaled to
[-0.5, 0.5] so they are comparable across dates regardless of universe size.
This is computed *within* each date only — no time-series leakage.
"""
from __future__ import annotations

import pandas as pd


def cross_sectional_rank(panel: pd.DataFrame) -> pd.DataFrame:
    """``panel`` indexed by date, columns = tickers -> rank in [-0.5, 0.5]."""
    return panel.rank(axis=1, pct=True) - 0.5


def winsorize_cross_section(panel: pd.DataFrame, pct: float = 0.01) -> pd.DataFrame:
    if pct <= 0:
        return panel
    lo = panel.quantile(pct, axis=1)
    hi = panel.quantile(1 - pct, axis=1)
    return panel.clip(lower=lo, upper=hi, axis=0)
