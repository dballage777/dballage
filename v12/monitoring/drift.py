"""S6 — Drift / decay guardian. OBSERVE-ONLY monitor (raises alarms, never acts).

This is not a strategy — it is the safeguard. It reads the EXISTING shadow ledger
(the 7 paper tests) READ-ONLY and, per sleeve, watches for:

  * decay      — rolling realized Sharpe whose lower-confidence bound has fallen
                 to/through zero (the edge is eroding);
  * drift      — a Page-Hinkley change-point alarm on the realized-return stream
                 (the return-generating process has shifted).

Page-Hinkley is a classic, dependency-free change detector (the same family as
ADWIN/DDM in the streaming-ML literature). We implement it in-house rather than
pull the heavy `river` dependency; it is a SIMPLIFIED detector and is documented
as such — it flags candidates for human review, it does not demote anything.

Nothing here modifies the ledger, the sleeves, or any allocation. Alarms are
logged to a separate signal ledger for review.
"""
from __future__ import annotations

from dataclasses import dataclass, asdict
from typing import Dict, List, Optional

import numpy as np

MIN_OBS = 20             # need a meaningful sample before judging
PH_DELTA = 0.0005        # Page-Hinkley magnitude tolerance
PH_LAMBDA = 0.05         # Page-Hinkley alarm threshold (cumulative)


@dataclass
class SleeveHealth:
    sleeve: str
    n: int
    roll_sharpe: Optional[float]
    sharpe_lcb: Optional[float]     # lower confidence bound (approx)
    decay_flag: bool
    drift_flag: bool
    note: str

    def as_record(self) -> Dict:
        return asdict(self)


def _page_hinkley(x: List[float], delta: float = PH_DELTA,
                  lam: float = PH_LAMBDA) -> bool:
    """Two-sided Page-Hinkley change alarm on a return stream. Dependency-free."""
    if len(x) < MIN_OBS:
        return False
    arr = np.asarray(x, dtype=float)
    mean = 0.0
    mt_pos = mt_neg = 0.0
    min_pos = float("inf")
    max_neg = float("-inf")
    alarm = False
    for i, v in enumerate(arr, 1):
        mean += (v - mean) / i
        mt_pos += v - mean - delta
        mt_neg += v - mean + delta
        min_pos = min(min_pos, mt_pos)
        max_neg = max(max_neg, mt_neg)
        if (mt_pos - min_pos) > lam or (max_neg - mt_neg) > lam:
            alarm = True
    return alarm


def _sharpe_with_lcb(rets: List[float]) -> tuple:
    """Annualized rolling Sharpe + a rough lower confidence bound.

    LCB uses the standard error of the Sharpe estimate ~ sqrt((1 + 0.5 S^2)/n),
    a common approximation; we report S - 1.64*SE (~5% one-sided)."""
    r = np.asarray(rets, dtype=float)
    n = len(r)
    sd = r.std(ddof=1) if n > 1 else 0.0
    if n < 2 or sd == 0:
        return (None, None)
    s = r.mean() / sd
    s_ann = s * np.sqrt(252)
    se = np.sqrt((1 + 0.5 * s * s) / n)          # SE of the (per-period) Sharpe
    lcb_ann = (s - 1.64 * se) * np.sqrt(252)
    return (float(s_ann), float(lcb_ann))


def assess_sleeve(sleeve: str, returns: List[float]) -> SleeveHealth:
    n = len(returns)
    if n < MIN_OBS:
        return SleeveHealth(sleeve, n, None, None, False, False,
                            f"warming up ({n}/{MIN_OBS} obs)")
    sharpe, lcb = _sharpe_with_lcb(returns)
    decay = lcb is not None and lcb <= 0.0
    drift = _page_hinkley(returns)
    notes = []
    if decay:
        notes.append("edge decay: Sharpe LCB <= 0")
    if drift:
        notes.append("Page-Hinkley change-point")
    note = "; ".join(notes) if notes else "ok"
    return SleeveHealth(sleeve, n, sharpe, lcb, decay, drift, note)


def scan_ledger(ledger_path: str) -> List[SleeveHealth]:
    """Read the existing shadow ledger READ-ONLY and assess each sleeve."""
    import os
    import json
    if not os.path.exists(ledger_path):
        return []
    rows = []
    for line in open(ledger_path):
        line = line.strip()
        if line:
            rows.append(json.loads(line))
    rows.sort(key=lambda r: r.get("date", ""))
    by_sleeve: Dict[str, List[float]] = {}
    for r in rows:
        dr = r.get("day_return")
        if dr is not None:
            by_sleeve.setdefault(r["sleeve"], []).append(float(dr))
    return [assess_sleeve(s, rets) for s, rets in sorted(by_sleeve.items())]
