"""S2 — Variance-Risk-Premium (VRP) equity timer. OBSERVE-ONLY shadow.

The variance risk premium — the gap between option-IMPLIED volatility (VIX) and
subsequently-REALIZED volatility — is one of the more robust equity-premium
predictors in the literature (Bollerslev/Tauchen/Zhou; and many follow-ups). When
the premium is high, forward equity returns have historically been higher; a
compressed or negative premium (realized panic exceeding implied) is a stress tell.

This module computes a point-in-time VRP and turns it into a SUGGESTED equity
exposure multiplier. It does NOT allocate capital and does NOT touch any of the 7
paper tests — the runner records the suggestion + the realized market outcome to a
SEPARATE ledger so we can measure, forward and honestly, whether the timer would
have improved risk-adjusted return versus staying fully invested.

Honest limits: VIX is annualized implied vol in %; realized vol is a 21-day
close-to-close estimate annualized in %. In a sandbox with no network the loader
falls back to SYNTHETIC prices (stamped) — pipeline validation only, not a real
VRP. Real VIX/SPY come from the daily Action / a Codespace.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, Optional

import numpy as np
import pandas as pd

from ..config import ExperimentConfig
from ..data import load_prices

BOOK = "vrp_timer"
VIX_TICKER = "^VIX"
RV_WINDOW = 21           # trading days for realized vol
LOOKBACK = 252           # trailing window for the VRP percentile
# suggested equity exposure multiplier per VRP state (transparent, not fit)
MULT = {"risk_on": 1.0, "neutral": 0.6, "risk_off": 0.3}


@dataclass
class VRPResult:
    date: pd.Timestamp
    vix: float
    realized_vol: float
    vrp: float
    vrp_pct: float           # percentile of latest VRP within the trailing window
    state: str
    suggested_mult: float
    source: str
    market_close: pd.Series = field(repr=False, default=None)

    def as_record(self) -> Dict:
        return {"asset": "SPY", "vix": round(self.vix, 3),
                "realized_vol": round(self.realized_vol, 3), "vrp": round(self.vrp, 3),
                "vrp_pct": round(self.vrp_pct, 4), "state": self.state,
                "suggested_mult": round(self.suggested_mult, 4),
                "reasoning": f"VRP={self.vrp:.2f} (pct {self.vrp_pct:.0%}) -> {self.state}",
                "sources": f"VIX + SPY realized vol [{self.source}]"}


def _classify(pct: float) -> str:
    if pct >= 0.50:
        return "risk_on"
    if pct >= 0.25:
        return "neutral"
    return "risk_off"


def build_vrp_signal(end: str = "2026-06-20",
                     start: str = "2012-01-01") -> Optional[VRPResult]:
    """Compute the latest point-in-time VRP timer state. None if VIX unavailable."""
    cfg = ExperimentConfig(name="signal_vrp")
    cfg.data.universe = [VIX_TICKER, "SPY"]
    cfg.data.benchmark = "SPY"
    cfg.data.rs_refs = ["SPY"]
    cfg.data.start, cfg.data.end = start, end
    data = load_prices(cfg.data)

    if VIX_TICKER not in data.close.columns or "SPY" not in data.close.columns:
        return None

    vix = data.close[VIX_TICKER].dropna()
    spy = data.close["SPY"].dropna()
    if len(vix) < LOOKBACK or len(spy) < RV_WINDOW + 5:
        return None

    # realized vol: annualized std of daily returns over RV_WINDOW, in % to match VIX
    rets = spy.pct_change()
    rv = rets.rolling(RV_WINDOW).std() * np.sqrt(252) * 100.0
    vrp = (vix - rv).dropna()
    if len(vrp) < LOOKBACK:
        return None

    latest = vrp.index.max()
    window = vrp.tail(LOOKBACK)
    pct = float((window <= window.iloc[-1]).mean())   # percentile rank of latest
    state = _classify(pct)

    return VRPResult(
        date=latest, vix=float(vix.reindex([latest]).iloc[0]),
        realized_vol=float(rv.reindex([latest]).iloc[0]), vrp=float(vrp.iloc[-1]),
        vrp_pct=pct, state=state, suggested_mult=float(MULT[state]),
        source=data.source, market_close=spy)
