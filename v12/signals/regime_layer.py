"""S1 — Composite cross-market regime-state layer. OBSERVE-ONLY shadow.

A transparent, rules-based composite of several *cross-market* risk-regime
indicators (deliberately NOT a black-box HMM yet — start simple, add complexity
only if the simple version earns it). Each sub-signal votes risk-on / risk-off;
the composite score maps to a suggested equity exposure multiplier.

Sub-signals (each computed defensively; skipped if its data is unavailable):
  1. VIX term structure   ^VIX3M / ^VIX  (>1 contango = calm; <1 backwardation = stress)
  2. Credit ratio trend   HYG / LQD 50-day trend (rising = risk-on)
  3. Market breadth        % of a stock universe above its 200-day MA
  4. Stock-bond corr       rolling corr(SPY, AGG) — informational regime flag

This records a SUGGESTED multiplier only. It allocates nothing and modifies none
of the 7 paper tests. It EXTENDS (does not alter) the existing classify_regime_6.
Synthetic data (no network) is stamped and for pipeline validation only.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional

import numpy as np
import pandas as pd

from ..config import ExperimentConfig, BROAD_UNIVERSE
from ..data import load_prices

BOOK = "regime_timer"
MACRO_TICKERS = ["SPY", "AGG", "HYG", "LQD", "^VIX", "^VIX3M"]
BREADTH_MA = 200
MULT = {"risk_on": 1.0, "neutral": 0.6, "risk_off": 0.3}


@dataclass
class RegimeLayerResult:
    date: pd.Timestamp
    votes: Dict[str, Optional[float]]   # sub-signal -> +1 risk-on / -1 risk-off / None
    score: float                        # mean of available votes, in [-1, 1]
    state: str
    suggested_mult: float
    source: str
    market_close: pd.Series = field(repr=False, default=None)

    def as_record(self) -> Dict:
        v = {k: (None if x is None else round(float(x), 3)) for k, x in self.votes.items()}
        return {"asset": "SPY", "votes": v, "score": round(self.score, 4),
                "state": self.state, "suggested_mult": round(self.suggested_mult, 4),
                "reasoning": f"composite regime score {self.score:+.2f} -> {self.state}",
                "sources": f"VIX term / credit / breadth / stock-bond corr [{self.source}]"}


def _state(score: float) -> str:
    if score >= 0.25:
        return "risk_on"
    if score <= -0.25:
        return "risk_off"
    return "neutral"


def _asof(s: pd.Series, d) -> Optional[float]:
    s = s.dropna()
    if s.empty:
        return None
    val = s.asof(d)
    return None if pd.isna(val) else float(val)


def build_regime_layer(end: str = "2026-06-20", start: str = "2010-01-01",
                       breadth_universe: Optional[List[str]] = None) -> Optional[RegimeLayerResult]:
    """Compute the latest composite cross-market regime state."""
    breadth_u = list(breadth_universe or BROAD_UNIVERSE)
    cfg = ExperimentConfig(name="signal_regime")
    cfg.data.universe = list(dict.fromkeys(MACRO_TICKERS + breadth_u))
    cfg.data.benchmark = "SPY"
    cfg.data.rs_refs = ["SPY"]
    cfg.data.start, cfg.data.end = start, end
    data = load_prices(cfg.data)
    close = data.close
    if "SPY" not in close.columns:
        return None
    spy = close["SPY"].dropna()
    d = spy.index.max()

    votes: Dict[str, Optional[float]] = {"vix_term": None, "credit": None,
                                         "breadth": None, "stock_bond_corr": None}

    # 1. VIX term structure: VIX3M/VIX > 1 => calm (risk-on)
    if "^VIX" in close and "^VIX3M" in close:
        vix = _asof(close["^VIX"], d)
        vix3m = _asof(close["^VIX3M"], d)
        if vix and vix3m and vix > 0:
            votes["vix_term"] = 1.0 if (vix3m / vix) >= 1.0 else -1.0

    # 2. Credit ratio trend: HYG/LQD rising over 50d => risk-on
    if "HYG" in close and "LQD" in close:
        ratio = (close["HYG"] / close["LQD"]).dropna()
        if len(ratio) > 55:
            votes["credit"] = 1.0 if ratio.iloc[-1] > ratio.iloc[-50] else -1.0

    # 3. Breadth: % of breadth universe above its 200-DMA
    breadth_cols = [c for c in breadth_u if c in close.columns]
    if breadth_cols:
        above = []
        for c in breadth_cols:
            s = close[c].dropna()
            if len(s) >= BREADTH_MA:
                above.append(1.0 if s.iloc[-1] > s.tail(BREADTH_MA).mean() else 0.0)
        if above:
            frac = float(np.mean(above))
            votes["breadth"] = 1.0 if frac >= 0.5 else -1.0

    # 4. Stock-bond correlation regime (informational): positive corr => less hedge
    if "AGG" in close:
        joint = pd.concat([spy.pct_change(), close["AGG"].pct_change()], axis=1).dropna()
        if len(joint) > 63:
            corr = joint.tail(63).iloc[:, 0].corr(joint.tail(63).iloc[:, 1])
            if not pd.isna(corr):
                # high positive stock-bond corr historically accompanies risk-off (2022);
                # negative corr = normal hedging = risk-on
                votes["stock_bond_corr"] = -1.0 if corr > 0.3 else 1.0

    present = [x for x in votes.values() if x is not None]
    if not present:
        return None
    score = float(np.mean(present))
    state = _state(score)
    return RegimeLayerResult(date=d, votes=votes, score=score, state=state,
                             suggested_mult=float(MULT[state]), source=data.source,
                             market_close=spy)
