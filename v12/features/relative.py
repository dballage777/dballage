"""Relative-strength features: each name vs a set of reference series (SPY, QQQ,
sector ETFs). All point-in-time."""
from __future__ import annotations

import numpy as np
import pandas as pd


def relative_strength(close: pd.Series, ref_close: pd.Series, window: int = 60) -> pd.Series:
    """Trailing relative return of a name vs a reference over ``window`` days."""
    ratio = close / ref_close.reindex(close.index).ffill()
    return ratio.pct_change(window)


def rolling_beta(close: pd.Series, ref_close: pd.Series, window: int = 60) -> pd.Series:
    r = close.pct_change()
    rm = ref_close.reindex(close.index).ffill().pct_change()
    cov = r.rolling(window).cov(rm)
    var = rm.rolling(window).var()
    return cov / var.replace(0, np.nan)
