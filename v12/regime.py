"""Point-in-time market-regime classification.

The factor scorecard showed the signal *reverses* in stressed/bear years
(2018, 2022) while paying strongly in calm/bull years — so a regime layer that
de-risks in the reversal regimes is the highest-evidence lever.

Regimes use only standard, pre-registered, point-in-time market state (no fitting
to the outcome):
  * trend: benchmark above/below its 200-day SMA  -> bull / bear
  * vol:   benchmark trailing realized vol, percentile-ranked vs its own past
           year -> calm / normal / stressed (terciles)
  * risk_on = bull AND not stressed
Everything is computed from data up to date t (rolling windows), so it is safe to
use as an exposure gate in the walk-forward backtest.
"""
from __future__ import annotations

import numpy as np
import pandas as pd


def classify_regime(benchmark_close: pd.Series, trend_window: int = 200,
                    vol_window: int = 20, vol_lookback: int = 252) -> pd.DataFrame:
    sma = benchmark_close.rolling(trend_window).mean()
    bull = (benchmark_close > sma)

    rvol = benchmark_close.pct_change().rolling(vol_window).std()
    vol_pct = rvol.rolling(vol_lookback).apply(lambda x: (x[-1] >= x).mean(), raw=True)
    # tercile: 0 calm, 1 normal, 2 stressed
    vol_state = pd.cut(vol_pct, [-0.01, 1 / 3, 2 / 3, 1.01], labels=[0, 1, 2]).astype("float")

    risk_on = bull & (vol_state < 2)
    return pd.DataFrame({
        "bull": bull.astype(float),
        "vol_pct": vol_pct,
        "vol_state": vol_state,
        "risk_on": risk_on.astype(float),
    })


def regime_label(row) -> str:
    if pd.isna(row.get("vol_state")):
        return "unknown"
    trend = "bull" if row["bull"] >= 0.5 else "bear"
    vol = {0: "calm", 1: "normal", 2: "stressed"}[int(row["vol_state"])]
    return f"{trend}-{vol}"
