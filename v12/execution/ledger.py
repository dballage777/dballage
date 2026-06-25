"""Shadow ledger — append-only record of decisions + per-sleeve paper NAV, and
the learning-loop substrate.

Every run logs the day's governed decisions (per sleeve) and advances a paper NAV
from realized returns, so over a 90-180 day shadow period we accumulate honest,
forward, survivorship-free performance per sleeve. ``rolling_performance`` turns
that into the metrics the learning loop uses to re-weight sleeves.
"""
from __future__ import annotations

import json
import os
from typing import Dict, List, Optional

import numpy as np
import pandas as pd


class ShadowLedger:
    def __init__(self, path: str = "results/shadow_ledger.jsonl"):
        self.path = path
        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)

    def log(self, date: str, sleeve: str, status: str, decisions: List[dict],
            day_return: Optional[float] = None) -> None:
        n_long = sum(1 for d in decisions if d.get("target_weight", 0) > 0)
        rec = {"date": str(date), "sleeve": sleeve, "status": status,
               "n_positions": n_long, "day_return": day_return,
               "decisions": decisions}
        with open(self.path, "a") as f:
            f.write(json.dumps(rec, default=float) + "\n")

    def load(self) -> pd.DataFrame:
        if not os.path.exists(self.path):
            return pd.DataFrame()
        rows = [json.loads(l) for l in open(self.path) if l.strip()]
        return pd.DataFrame(rows)

    def rolling_performance(self, sleeve: str, window: int = 63) -> Dict[str, float]:
        """Rolling paper performance per sleeve — the learning-loop input."""
        df = self.load()
        if df.empty:
            return {}
        s = df[(df["sleeve"] == sleeve) & df["day_return"].notna()]
        if s.empty:
            return {"n_days": 0}
        r = pd.Series(s["day_return"].astype(float).values).tail(window)
        sd = r.std()
        return {
            "n_days": int(len(r)),
            "cum_return": float((1 + r).prod() - 1),
            "sharpe": float(r.mean() / sd * np.sqrt(252)) if sd > 0 else float("nan"),
            "max_day_loss": float(r.min()),
            "win_rate": float((r > 0).mean()),
        }
