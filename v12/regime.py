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


# --- 6-state regime (GOAL spec) ---------------------------------------------
# Bull / Bear / Chop / HighVol / Crisis / Recovery. NOTE: these boundaries are
# hand-specified (heuristic) and therefore carry overfitting risk — the parallel
# paper horse-race is precisely what tests whether they add value over the simple
# 2-state gate. All point-in-time (rolling windows only).
_REGIME6 = ["crisis", "high_vol", "bull", "recovery", "bear", "chop"]
# GOAL-style exposure weight per regime (capital-preservation tilt)
REGIME6_EXPOSURE = {"bull": 1.0, "recovery": 0.7, "chop": 0.5,
                    "high_vol": 0.3, "bear": 0.2, "crisis": 0.0, "unknown": 0.0}


def classify_regime_6(benchmark_close: pd.Series, trend_window: int = 200,
                      vol_window: int = 20, vol_lookback: int = 252,
                      dd_window: int = 252) -> pd.Series:
    import numpy as np
    sma = benchmark_close.rolling(trend_window).mean()
    above = benchmark_close > sma
    slope = sma.diff(20)
    rvol = benchmark_close.pct_change().rolling(vol_window).std()
    vol_pct = rvol.rolling(vol_lookback).apply(lambda x: (x[-1] >= x).mean(), raw=True)
    dd = benchmark_close / benchmark_close.rolling(dd_window).max() - 1.0
    mom = benchmark_close.pct_change(60)

    cond = [
        (dd <= -0.15) & (vol_pct >= 0.80),                 # crisis
        (vol_pct >= 0.80),                                 # high_vol
        above & (slope > 0) & (vol_pct < 0.66),            # bull
        (~above) & (mom > 0) & (dd > -0.15),               # recovery
        (~above) & (slope < 0),                            # bear
    ]
    out = pd.Series(np.select(cond, _REGIME6[:-1], default="chop"),
                    index=benchmark_close.index)
    out[sma.isna() | vol_pct.isna()] = "unknown"
    return out
