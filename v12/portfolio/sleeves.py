"""Multi-sleeve portfolio manager — the structural backbone for a multi-strategy
system, usable from day one with a single live sleeve.

A *sleeve* is an independent strategy (e.g. "equity_lowvol") with its own capital
allocation and a status: LIVE (counts toward real targets) or SHADOW (logged and
performance-tracked only, never allocated real/paper capital). New ideas enter as
SHADOW and are promoted to LIVE only after passing their gate — enforcing
"validate before deploy" at the portfolio level.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List

import pandas as pd


@dataclass
class Sleeve:
    name: str
    asset_class: str = "stocks"          # stocks | crypto
    allocation: float = 1.0              # share of the LIVE risk budget
    status: str = "shadow"               # shadow | live
    max_class_weight: float = 0.70       # asset-class exposure cap (stocks 70%, crypto 30%)


@dataclass
class SleeveManager:
    sleeves: Dict[str, Sleeve] = field(default_factory=dict)

    def register(self, sleeve: Sleeve) -> None:
        self.sleeves[sleeve.name] = sleeve

    def promote(self, name: str) -> None:
        self.sleeves[name].status = "live"

    def live_sleeves(self) -> List[Sleeve]:
        return [s for s in self.sleeves.values() if s.status == "live"]

    def combine(self, targets_by_sleeve: Dict[str, pd.Series]) -> pd.Series:
        """Combine per-sleeve target weights into one portfolio, scaling each by
        its allocation and capping asset-class exposure. SHADOW sleeves are
        excluded from the real/paper portfolio (they are logged separately)."""
        live = self.live_sleeves()
        if not live:
            return pd.Series(dtype=float)   # nothing live -> cash
        total_alloc = sum(s.allocation for s in live) or 1.0
        combined: Dict[str, float] = {}
        class_used: Dict[str, float] = {}
        for s in live:
            tgt = targets_by_sleeve.get(s.name)
            if tgt is None or tgt.empty:
                continue
            scaled = tgt * (s.allocation / total_alloc)
            # asset-class cap
            cls_sum = scaled.sum()
            room = max(s.max_class_weight - class_used.get(s.asset_class, 0.0), 0.0)
            if cls_sum > room and cls_sum > 0:
                scaled = scaled * (room / cls_sum)
            class_used[s.asset_class] = class_used.get(s.asset_class, 0.0) + scaled.sum()
            for k, v in scaled.items():
                combined[k] = combined.get(k, 0.0) + float(v)
        out = pd.Series(combined)
        return out[out > 0]                 # remainder is CASH
