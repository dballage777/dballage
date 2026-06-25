"""Multi-horizon signal blend (GOAL strategy horizons: long + medium).

Blends per-horizon model scores (e.g. 60-day long + 20-day medium) into one
signal. Each horizon's scores are rank-standardized to [-0.5, 0.5] before
blending so different-scale predictions combine fairly. Short/intraday is NOT
included — it requires intraday data this system does not have (see GOAL audit).
"""
from __future__ import annotations

from typing import Dict

import pandas as pd


def blend_horizons(scores_by_horizon: Dict[int, pd.Series],
                   weights: Dict[int, float]) -> pd.Series:
    total = sum(weights.get(h, 0.0) for h in scores_by_horizon) or 1.0
    out = None
    for h, s in scores_by_horizon.items():
        w = weights.get(h, 0.0) / total
        if w == 0:
            continue
        z = s.rank(pct=True) - 0.5                  # rank-standardize
        out = z * w if out is None else out.add(z * w, fill_value=0.0)
    return out if out is not None else pd.Series(dtype=float)
