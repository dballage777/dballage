"""0-100 asset scoring (the monitoring spec's ASSET SCORING MODEL).

The spec lists 12 factors. We compute the ones backed by data we actually have
and trust, and we are explicit about the rest: factors whose feed is missing, or
which ablation showed add no out-of-sample edge, carry **weight 0** and a status
flag — they are listed (so the schema matches the spec) but cannot silently
inflate a score.

Live factors (price/volume-derived, point-in-time):
    expected_value   - model EV proxy (the validated signal), if supplied
    trend_strength   - price vs its 200-day SMA
    momentum         - trailing 60-day return
    low_volatility   - inverse trailing realized vol (low-vol preference)
    liquidity        - average dollar volume

Each factor is cross-sectionally percentile-ranked to 0-100, then weighted into a
0-100 composite. Ranking is relative within the scored universe on the date.
"""
from __future__ import annotations

from typing import Dict, Optional

import numpy as np
import pandas as pd

# weight 0 + status != 'live' => declared but does not contribute (honest schema)
FACTOR_WEIGHTS: Dict[str, float] = {
    "expected_value": 0.30,
    "trend_strength": 0.20,
    "momentum": 0.20,
    "low_volatility": 0.15,
    "liquidity": 0.15,
    # --- declared but not contributing (no trustworthy feed / no proven edge) ---
    "fundamental_quality": 0.0,
    "sentiment": 0.0,
    "insider_activity": 0.0,
    "institutional_activity": 0.0,
    "macro_alignment": 0.0,
    "developer_activity": 0.0,
    "community_conviction": 0.0,
}

FACTOR_STATUS: Dict[str, str] = {
    "expected_value": "live", "trend_strength": "live", "momentum": "live",
    "low_volatility": "live", "liquidity": "live",
    "fundamental_quality": "shadow_only (ablation: no OOS edge)",
    "sentiment": "infeasible (no real-time news/social feed)",
    "insider_activity": "shadow_only (ablation: no OOS edge)",
    "institutional_activity": "not_implemented (13F connector)",
    "macro_alignment": "not_implemented (FRED connector)",
    "developer_activity": "not_implemented (GitHub connector)",
    "community_conviction": "infeasible (no Reddit/Discord feed)",
}


def _pct_rank(s: pd.Series) -> pd.Series:
    """Cross-sectional percentile rank -> 0-100 (NaN-safe)."""
    r = s.rank(pct=True)
    return (r * 100.0).fillna(50.0)


def score_assets(close: pd.DataFrame, volume: Optional[pd.DataFrame] = None,
                 model_ev: Optional[Dict[str, float]] = None,
                 asof: Optional[pd.Timestamp] = None) -> pd.DataFrame:
    """Return a per-asset factor + composite score table (0-100) for one date.

    ``close``/``volume`` are wide [date x ticker] frames. ``model_ev`` maps ticker
    -> EV proxy (e.g. the sleeve's per-asset ev_score). Missing inputs degrade
    gracefully (the factor ranks neutral) rather than fabricate a value.
    """
    asof = asof or close.index.max()
    hist = close.loc[:asof]
    if len(hist) < 60:
        # not enough history to rank trend/momentum honestly
        idx = close.columns
        return pd.DataFrame({"composite": pd.Series(50.0, index=idx)})

    last = hist.iloc[-1]
    sma200 = hist.tail(200).mean()
    trend = last / sma200 - 1.0
    momentum = last / hist.iloc[-60] - 1.0
    rvol = hist.pct_change().tail(20).std()
    low_vol = -rvol                       # lower vol -> higher score
    if volume is not None:
        vol = volume.loc[:asof]
        dollar = (close.loc[:asof] * vol).tail(20).mean()
        liquidity = np.log1p(dollar)
    else:
        liquidity = pd.Series(0.0, index=close.columns)
    ev = pd.Series(model_ev or {}, dtype=float).reindex(close.columns)

    factors = {
        "expected_value": _pct_rank(ev),
        "trend_strength": _pct_rank(trend),
        "momentum": _pct_rank(momentum),
        "low_volatility": _pct_rank(low_vol),
        "liquidity": _pct_rank(liquidity),
    }
    out = pd.DataFrame(factors)
    live_w = {k: FACTOR_WEIGHTS[k] for k in factors}
    wsum = sum(live_w.values()) or 1.0
    out["composite"] = sum(out[k] * (live_w[k] / wsum) for k in factors)
    return out.sort_values("composite", ascending=False)
