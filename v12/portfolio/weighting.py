"""Position weighting schemes for the selected long basket.

All schemes take a recent returns window (DataFrame: dates x selected tickers)
and return a weight Series summing to 1, capped at ``max_weight``.
"""
from __future__ import annotations

import numpy as np
import pandas as pd


def _cap_and_norm(w: pd.Series, max_weight: float) -> pd.Series:
    w = w.clip(lower=0)
    if w.sum() == 0:
        return pd.Series(1.0 / len(w), index=w.index)
    w = w / w.sum()
    # iterative cap to respect max_weight while staying normalised
    for _ in range(10):
        over = w > max_weight
        if not over.any():
            break
        excess = (w[over] - max_weight).sum()
        w[over] = max_weight
        under = ~over
        if under.any():
            w[under] += excess * w[under] / w[under].sum()
    return w / w.sum()


def equal_weight(rets: pd.DataFrame, max_weight: float) -> pd.Series:
    return _cap_and_norm(pd.Series(1.0, index=rets.columns), max_weight)


def inverse_vol(rets: pd.DataFrame, max_weight: float) -> pd.Series:
    vol = rets.std().replace(0, np.nan)
    inv = 1.0 / vol
    inv = inv.fillna(inv.mean())
    return _cap_and_norm(inv, max_weight)


def risk_parity(rets: pd.DataFrame, max_weight: float, iters: int = 200) -> pd.Series:
    """Simple iterative equal-risk-contribution solver."""
    cov = rets.cov().values
    n = cov.shape[0]
    if n == 0:
        return pd.Series(dtype=float)
    w = np.ones(n) / n
    for _ in range(iters):
        mrc = cov @ w                     # marginal risk contribution
        rc = w * mrc                      # risk contribution
        target = rc.mean()
        w *= (target / (rc + 1e-12)) ** 0.5
        w = np.clip(w, 0, None)
        w /= w.sum()
    return _cap_and_norm(pd.Series(w, index=rets.columns), max_weight)


def compute_weights(scheme: str, rets: pd.DataFrame, max_weight: float) -> pd.Series:
    return {
        "equal": equal_weight,
        "inverse_vol": inverse_vol,
        "risk_parity": risk_parity,
    }[scheme](rets, max_weight)
