"""Market-breadth features.

Breadth is a *market-wide* state, computed across the whole universe and then
broadcast to every name (so the model can condition cross-sectional bets on the
regime). Point-in-time: uses only closes up to date t.
"""
from __future__ import annotations

import numpy as np
import pandas as pd


def pct_above_ma(close_panel: pd.DataFrame, n: int) -> pd.Series:
    ma = close_panel.rolling(n).mean()
    above = (close_panel > ma)
    return above.mean(axis=1)


def new_highs_lows(close_panel: pd.DataFrame, n: int = 252) -> pd.DataFrame:
    roll_max = close_panel.rolling(n).max()
    roll_min = close_panel.rolling(n).min()
    nh = (close_panel >= roll_max).mean(axis=1)
    nl = (close_panel <= roll_min).mean(axis=1)
    return pd.DataFrame({"breadth_new_highs": nh, "breadth_new_lows": nl})


def compute_breadth(close_panel: pd.DataFrame, mas=(20, 50, 200)) -> pd.DataFrame:
    out = {}
    for n in mas:
        out[f"breadth_pct_above_{n}"] = pct_above_ma(close_panel, n)
    df = pd.DataFrame(out)
    return pd.concat([df, new_highs_lows(close_panel)], axis=1)
