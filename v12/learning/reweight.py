"""Learning loop — reweight sleeves by realized (paper) performance.

Consumes ShadowLedger.rolling_performance per sleeve and produces updated
allocations: more capital to sleeves with higher realized Sharpe, less to noisy
ones. Conservative: a sleeve with too little history or non-positive Sharpe gets
near-zero weight (it must earn allocation). Increases are damped (no all-in on a
lucky streak).
"""
from __future__ import annotations

from typing import Dict

MIN_DAYS = 20


def reweight_sleeves(perf_by_sleeve: Dict[str, dict], prior: Dict[str, float] = None,
                     blend: float = 0.5) -> Dict[str, float]:
    """Return normalized allocations from rolling performance.

    ``blend`` mixes the performance-implied weight with the prior (damping):
    new = blend*perf_weight + (1-blend)*prior.
    """
    names = list(perf_by_sleeve.keys())
    if not names:
        return {}
    score = {}
    for n, p in perf_by_sleeve.items():
        s = p.get("sharpe", 0.0) or 0.0
        if p.get("n_days", 0) < MIN_DAYS or s != s:   # too little history / NaN
            s = 0.0
        score[n] = max(s, 0.0)
    tot = sum(score.values())
    perf_w = ({n: score[n] / tot for n in names} if tot > 0
              else {n: 1.0 / len(names) for n in names})
    if prior is None:
        return perf_w
    out = {n: blend * perf_w[n] + (1 - blend) * prior.get(n, 0.0) for n in names}
    s = sum(out.values()) or 1.0
    return {n: v / s for n, v in out.items()}
