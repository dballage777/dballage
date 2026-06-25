"""Decision engine — turns model signals into governed, graduated trade decisions.

Implements the GOAL decision hierarchy and required output, and the GOVERNANCE
veto/scale rules, applied to the *validated* low-vol strategy:

    Regime -> EV -> Risk validation -> (correlation) -> Position sizing -> Action

Every decision carries: Asset, Action, EV score, Risk, Confidence, Size,
Reasoning, Data sources. No-trade conditions default to CASH. Sizing is graduated
(conviction-scaled), never binary. This is decision logic only — it does not
place orders (the adapter does, paper-only).
"""
from __future__ import annotations

from dataclasses import dataclass, asdict
from typing import Dict, List, Optional

import numpy as np
import pandas as pd

from ..risk.sizing import graduated_size_multiplier


@dataclass
class Decision:
    asset: str
    action: str          # BUY / HOLD / SELL / NO TRADE / REDUCE
    ev_score: float      # expected value proxy (post-cost), signed
    risk_status: str     # LOW / MEDIUM / HIGH
    confidence: float    # 0-100
    target_weight: float
    reasoning: str
    sources: str


class DecisionEngine:
    """Produces governed decisions for one rebalance.

    ``scores`` — model prediction per asset (cross-sectionally de-meaned forward
    return). ``regime_risk_on`` — point-in-time regime gate. ``governor_exposure``
    — hard-risk-layer exposure in [0,1]. ``cost`` — assumed round-trip cost used
    in the EV filter.
    """

    def __init__(self, max_weight: float = 0.08, top_quantile: float = 0.30,
                 confidence_floor: float = 60.0, cost: float = 0.001):
        self.max_weight = max_weight
        self.top_quantile = top_quantile
        self.confidence_floor = confidence_floor
        self.cost = cost

    def decide(self, scores: pd.Series, current_weights: Optional[pd.Series] = None,
               regime_risk_on: bool = True, governor_exposure: float = 1.0,
               recent_returns: Optional[pd.DataFrame] = None,
               corr_threshold: float = 0.80,
               sources: str = "price+volatility (validated)") -> List[Decision]:
        current_weights = current_weights if current_weights is not None else pd.Series(dtype=float)
        scores = scores.dropna()
        if scores.empty:
            return []

        pct = scores.rank(pct=True) * 100.0           # confidence proxy 0-100
        k = max(int(np.ceil(len(scores) * self.top_quantile)), 1)
        long_set = set(scores.sort_values(ascending=False).index[:k])

        # ---- correlation-overload check (decision hierarchy step 4) ----
        corr_overload = self._correlation_overload(long_set, recent_returns, corr_threshold)

        # raw target weights (graduated) before governance scaling
        raw = {}
        for a in scores.index:
            mult = graduated_size_multiplier(pct[a]) if a in long_set else 0.0
            raw[a] = mult
        total = sum(raw.values())
        base_w = {a: (raw[a] / total if total > 0 else 0.0) for a in raw}

        # global exposure from regime + hard-risk governor (CASH if risk-off/killed),
        # halved on correlation overload (hidden-concentration risk control)
        global_exposure = governor_exposure * (1.0 if regime_risk_on else 0.0)
        if corr_overload:
            global_exposure *= 0.5

        decisions: List[Decision] = []
        for a in scores.index:
            score = float(scores[a])
            conf = float(pct[a])
            ev = score - self.cost                     # EV proxy after cost
            cur = float(current_weights.get(a, 0.0))
            tgt = float(np.clip(base_w[a] * global_exposure, 0.0, self.max_weight))

            # ---- no-trade conditions -> default behaviour ----
            reason, action, risk = self._evaluate(a, ev, conf, cur, tgt,
                                                   regime_risk_on, governor_exposure)
            decisions.append(Decision(
                asset=a, action=action, ev_score=round(ev, 5), risk_status=risk,
                confidence=round(conf, 1), target_weight=round(tgt, 4),
                reasoning=reason, sources=sources))
        return decisions

    @staticmethod
    def _correlation_overload(long_set, recent_returns, threshold) -> bool:
        """Flag if the selected basket is dangerously concentrated in correlated
        names (avg pairwise correlation above ``threshold``)."""
        if recent_returns is None or len(long_set) < 2:
            return False
        cols = [c for c in long_set if c in recent_returns.columns]
        if len(cols) < 2:
            return False
        corr = recent_returns[cols].corr().values
        n = corr.shape[0]
        off = (corr.sum() - n) / (n * n - n)        # mean off-diagonal correlation
        return bool(off > threshold)

    def _evaluate(self, a, ev, conf, cur, tgt, regime_on, gov_exp):
        # GOVERNANCE / no-trade hierarchy (default = cash / no new risk)
        if gov_exp <= 0.0:
            return ("hard-risk governor active (drawdown/loss limit) -> de-risk",
                    "SELL" if cur > 0 else "NO TRADE", "HIGH")
        if not regime_on:
            return ("regime risk-off (bear/stressed) -> reduce to cash",
                    "REDUCE" if cur > tgt else ("NO TRADE" if tgt == 0 else "HOLD"), "HIGH")
        if ev <= 0:
            return ("EV <= 0 after costs -> no edge",
                    "SELL" if cur > 0 else "NO TRADE", "MEDIUM")
        if conf < self.confidence_floor and tgt == 0:
            return (f"confidence {conf:.0f} < {self.confidence_floor:.0f} and not selected",
                    "SELL" if cur > 0 else "NO TRADE", "MEDIUM")
        # actionable
        if tgt > cur + 1e-6:
            return (f"EV>0 (conf {conf:.0f}); scale up to graduated target", "BUY", "LOW")
        if tgt < cur - 1e-6:
            return ("target below current; trim toward graduated size", "REDUCE", "LOW")
        return ("at graduated target; maintain", "HOLD", "LOW")

    @staticmethod
    def to_records(decisions: List[Decision]) -> List[Dict]:
        return [asdict(d) for d in decisions]
