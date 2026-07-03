"""Variant 4 — the FULL SYSTEM (stocks + crypto, learning loop) shadow sleeve.

Combines the variant-2 stock sleeve and the variant-3 crypto sleeve into one
GOAL capital structure and adds the learning loop on top:

    capital structure        -> stocks <= 70% + crypto <= 30%, remainder CASH
                                (independent caps, not a split budget; cash is the
                                 default and absorbs whatever isn't deployed)
    per-book governance       -> each sleeve already applies its own 6-regime
                                 exposure, Kelly, EV gate, correlation check,
                                 graduated sizing, position + class + microcap caps
    learning loop             -> reweight_sleeves() reads each sleeve's realized
                                 paper Sharpe from the shadow ledger and trims the
                                 laggard: multiplier = perf_weight / max(perf_weight),
                                 so the best-performing book runs at its full allowed
                                 exposure and weaker books are scaled down. Cold
                                 start (insufficient history) -> 1.0 for all (no tilt).
    unified output            -> one combined decision report + one shadow NAV row

This is the complete GOAL engine in one runner, as a SHADOW sleeve — logged and
performance-tracked, never allocated real or paper capital. Decision logic only.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional

import pandas as pd

from .stock_sleeve import build_stock_sleeve, SleeveResult, SLEEVE_NAME as STOCK_SLEEVE
from .crypto_sleeve import build_crypto_sleeve, CryptoSleeveResult, SLEEVE_NAME as CRYPTO_SLEEVE
from ..learning.reweight import reweight_sleeves
from ..execution import Decision, DecisionEngine

SYSTEM_SLEEVE = "full_system"


@dataclass
class FullSystemResult:
    date: pd.Timestamp
    stock: SleeveResult
    crypto: CryptoSleeveResult
    learn_weights: Dict[str, float]      # normalized performance weights
    multipliers: Dict[str, float]        # per-sleeve exposure multiplier in [0,1]
    combined_targets: Dict[str, float]   # asset -> weight (post learning + caps)
    learning_active: bool                # False = cold start (no tilt yet)

    @property
    def stock_exposure(self) -> float:
        return float(sum(v for k, v in self.combined_targets.items() if not k.endswith("-USD")))

    @property
    def crypto_exposure(self) -> float:
        return float(sum(v for k, v in self.combined_targets.items() if k.endswith("-USD")))

    @property
    def total_exposure(self) -> float:
        return float(sum(self.combined_targets.values()))

    @property
    def cash(self) -> float:
        return float(max(1.0 - self.total_exposure, 0.0))


def _learning_multipliers(log_path: Optional[str]) -> tuple[Dict[str, float], Dict[str, float], bool]:
    """Turn realized paper Sharpe per sleeve into an exposure multiplier in [0,1].

    multiplier = perf_weight / max(perf_weight): the best book keeps full allowed
    exposure, laggards are trimmed proportionally. Cold start (no/short history)
    -> all 1.0 (no tilt), so the system behaves as independent capped books until
    it has earned an opinion.
    """
    names = [STOCK_SLEEVE, CRYPTO_SLEEVE]
    if not log_path:
        return ({n: 0.5 for n in names}, {n: 1.0 for n in names}, False)
    from ..execution.ledger import ShadowLedger
    led = ShadowLedger(log_path)
    perf = {n: led.rolling_performance(n) for n in names}
    has_history = any(p.get("n_days", 0) >= 1 and p.get("sharpe") is not None
                      and p.get("sharpe") == p.get("sharpe") for p in perf.values())
    weights = reweight_sleeves(perf)
    if not weights or not has_history:
        return ({n: 0.5 for n in names}, {n: 1.0 for n in names}, False)
    top = max(weights.values()) or 1.0
    mult = {n: float(min(weights.get(n, 0.0) / top, 1.0)) for n in names}
    return weights, mult, True


def build_full_system(end: str = "2026-06-20",
                      stock_universe: Optional[List[str]] = None,
                      crypto_universe: Optional[List[str]] = None,
                      log_path: Optional[str] = None,
                      read_log_path: Optional[str] = None,
                      stock_gov_mult: float = 1.0,
                      crypto_gov_mult: float = 1.0,
                      system_gov_mult: float = 1.0,
                      use_fundamentals: bool = False,
                      use_insider: bool = False,
                      reuse_crypto: Optional[CryptoSleeveResult] = None) -> FullSystemResult:
    """Run both sleeves, apply the learning loop, and combine under the GOAL
    capital structure (stocks <= 70% + crypto <= 30%, remainder CASH).

    ``read_log_path`` lets the learning loop read prior realized performance from
    an existing ledger *without* writing to it (the runner does its own
    realized-return logging). If omitted, ``log_path`` is used for both.
    """
    # per-book hard-risk governor multipliers (drawdown / daily-loss / 3-loss)
    # use_fundamentals/use_insider add the SEC data sources (variant 5, maximal).
    stock = build_stock_sleeve(end=end, universe=stock_universe, log_path=None,
                               risk_gov_mult=stock_gov_mult,
                               use_fundamentals=use_fundamentals, use_insider=use_insider)
    # crypto is identical across variant 4 and 5 (no fundamentals/insider) — reuse
    # a precomputed result if given to avoid rebuilding the whole crypto pipeline.
    crypto = reuse_crypto if reuse_crypto is not None else build_crypto_sleeve(
        end=end, universe=crypto_universe, log_path=None, risk_gov_mult=crypto_gov_mult)

    learn_weights, mult, learning_active = _learning_multipliers(read_log_path or log_path)

    # system_gov_mult is the governor on the COMBINED book (full_system's own NAV):
    # 0.0 forces the whole portfolio to cash regardless of the per-book books.
    combined: Dict[str, float] = {}
    for a, w in stock.targets.items():
        combined[a] = combined.get(a, 0.0) + w * mult[STOCK_SLEEVE] * float(system_gov_mult)
    for a, w in crypto.targets.items():
        combined[a] = combined.get(a, 0.0) + w * mult[CRYPTO_SLEEVE] * float(system_gov_mult)
    combined = {k: float(v) for k, v in combined.items() if v > 0}

    # latest date across the two books (they may differ by a day on real data)
    date = max(stock.date, crypto.date)
    result = FullSystemResult(date=date, stock=stock, crypto=crypto,
                              learn_weights=learn_weights, multipliers=mult,
                              combined_targets=combined, learning_active=learning_active)

    if log_path is not None:
        from ..execution.ledger import ShadowLedger
        led = ShadowLedger(log_path)
        # log each book + the combined system, all SHADOW
        led.log(date=f"{stock.date:%Y-%m-%d}", sleeve=STOCK_SLEEVE, status="shadow",
                decisions=DecisionEngine.to_records(stock.decisions), day_return=None)
        led.log(date=f"{crypto.date:%Y-%m-%d}", sleeve=CRYPTO_SLEEVE, status="shadow",
                decisions=DecisionEngine.to_records(crypto.decisions), day_return=None)
        system_decisions = [d for d in (stock.decisions + crypto.decisions)
                            if d.asset in combined]
        led.log(date=f"{date:%Y-%m-%d}", sleeve=SYSTEM_SLEEVE, status="shadow",
                decisions=DecisionEngine.to_records(system_decisions), day_return=None)
    return result


def all_decisions(res: FullSystemResult) -> List[Decision]:
    """Flat list of every decision across both books (for the unified report)."""
    return list(res.stock.decisions) + list(res.crypto.decisions)
