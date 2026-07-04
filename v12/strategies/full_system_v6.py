"""Variant 6 — FULL SYSTEM + SEC data + PRECIOUS METALS, revised percentages.

Exactly variant 5 (full system + all available SEC data sources on the stock
book) BUT under the revised capital structure (SYSTEM_SPEC §1, 2026-06-30):

    stocks          <= 65%   (was 70)   — with SEC fundamentals [+ insider]
    precious metals <= 15%   (new)      — GLD/IAU/SLV/PPLT/PALL/GDX book
    crypto          <= 20%   (was 30)
    cash            = remainder (default safe state)

The learning loop now spans THREE books (stocks, metals, crypto), reweighting by
each book's realized paper Sharpe. Everything else — 6-regime exposure, Kelly,
EV gate, correlation, graduated sizing, per-position caps, hard-risk governor —
is inherited unchanged from the sub-sleeves. SHADOW only: logged and
performance-tracked, never allocated real/paper capital, until it passes the gate.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Optional, Set

import pandas as pd

from .stock_sleeve import build_stock_sleeve, SleeveResult, SLEEVE_NAME as STOCK_SLEEVE
from .crypto_sleeve import build_crypto_sleeve, CryptoSleeveResult, SLEEVE_NAME as CRYPTO_SLEEVE
from .metals_sleeve import build_metals_sleeve, MetalsSleeveResult, SLEEVE_NAME as METALS_SLEEVE
from ..config import METALS_UNIVERSE
from ..learning.reweight import reweight_sleeves
from ..execution import Decision, DecisionEngine

SYSTEM6_SLEEVE = "full_system_v6"

# revised capital-structure caps (SYSTEM_SPEC §1, 2026-06-30)
STOCK_CAP_V6 = 0.65
METALS_CAP_V6 = 0.15
CRYPTO_CAP_V6 = 0.20


@dataclass
class FullSystemV6Result:
    date: pd.Timestamp
    stock: SleeveResult
    crypto: CryptoSleeveResult
    metals: MetalsSleeveResult
    learn_weights: Dict[str, float]
    multipliers: Dict[str, float]
    combined_targets: Dict[str, float]
    learning_active: bool
    metals_set: Set[str]

    @property
    def stock_exposure(self) -> float:
        return float(sum(v for k, v in self.combined_targets.items()
                         if not k.endswith("-USD") and k not in self.metals_set))

    @property
    def metals_exposure(self) -> float:
        return float(sum(v for k, v in self.combined_targets.items() if k in self.metals_set))

    @property
    def crypto_exposure(self) -> float:
        return float(sum(v for k, v in self.combined_targets.items() if k.endswith("-USD")))

    @property
    def total_exposure(self) -> float:
        return float(sum(self.combined_targets.values()))

    @property
    def cash(self) -> float:
        return float(max(1.0 - self.total_exposure, 0.0))


def _rescale(targets: Dict[str, float], cap: float) -> Dict[str, float]:
    """Scale a book's weights down so their sum does not exceed ``cap``."""
    tot = sum(targets.values())
    if tot > cap and tot > 0:
        return {k: v * (cap / tot) for k, v in targets.items()}
    return dict(targets)


def _learning_multipliers(log_path: Optional[str], names) -> tuple[Dict, Dict, bool]:
    """3-book learning multipliers: mult = perf_weight / max(perf_weight). Cold
    start (no history) -> all 1.0 (no tilt)."""
    if not log_path:
        return ({n: 1.0 / len(names) for n in names}, {n: 1.0 for n in names}, False)
    from ..execution.ledger import ShadowLedger
    led = ShadowLedger(log_path)
    perf = {n: led.rolling_performance(n) for n in names}
    has_history = any(p.get("n_days", 0) >= 1 and p.get("sharpe") is not None
                      and p.get("sharpe") == p.get("sharpe") for p in perf.values())
    weights = reweight_sleeves(perf)
    if not weights or not has_history:
        return ({n: 1.0 / len(names) for n in names}, {n: 1.0 for n in names}, False)
    top = max(weights.values()) or 1.0
    mult = {n: float(min(weights.get(n, 0.0) / top, 1.0)) for n in names}
    return weights, mult, True


def build_full_system_v6(end: str = "2026-06-20",
                         stock_universe: Optional[List[str]] = None,
                         crypto_universe: Optional[List[str]] = None,
                         metals_universe: Optional[List[str]] = None,
                         read_log_path: Optional[str] = None,
                         stock_gov_mult: float = 1.0, crypto_gov_mult: float = 1.0,
                         metals_gov_mult: float = 1.0, system_gov_mult: float = 1.0,
                         use_fundamentals: bool = True, use_insider: bool = False,
                         reuse_stock: Optional[SleeveResult] = None,
                         reuse_crypto: Optional[CryptoSleeveResult] = None,
                         reuse_metals: Optional[MetalsSleeveResult] = None) -> FullSystemV6Result:
    """Build variant 6: variant-5 machinery + a metals book, under revised caps."""
    # stock book = variant 5's (SEC data). reuse it if already built this run.
    stock = reuse_stock if reuse_stock is not None else build_stock_sleeve(
        end=end, universe=stock_universe, log_path=None, risk_gov_mult=stock_gov_mult,
        use_fundamentals=use_fundamentals, use_insider=use_insider)
    crypto = reuse_crypto if reuse_crypto is not None else build_crypto_sleeve(
        end=end, universe=crypto_universe, log_path=None, risk_gov_mult=crypto_gov_mult)
    metals = reuse_metals if reuse_metals is not None else build_metals_sleeve(
        end=end, universe=metals_universe, log_path=None, risk_gov_mult=metals_gov_mult)

    names = [STOCK_SLEEVE, METALS_SLEEVE, CRYPTO_SLEEVE]
    learn_weights, mult, learning_active = _learning_multipliers(read_log_path, names)

    # revised caps, then learning multiplier + system governor
    s_tgt = _rescale(stock.targets, STOCK_CAP_V6)
    m_tgt = _rescale(metals.targets, METALS_CAP_V6)
    c_tgt = _rescale(crypto.targets, CRYPTO_CAP_V6)
    combined: Dict[str, float] = {}
    for tgt, sleeve in ((s_tgt, STOCK_SLEEVE), (m_tgt, METALS_SLEEVE), (c_tgt, CRYPTO_SLEEVE)):
        for a, w in tgt.items():
            combined[a] = combined.get(a, 0.0) + w * mult[sleeve] * float(system_gov_mult)
    combined = {k: float(v) for k, v in combined.items() if v > 0}

    date = max(stock.date, crypto.date, metals.date)
    return FullSystemV6Result(
        date=date, stock=stock, crypto=crypto, metals=metals,
        learn_weights=learn_weights, multipliers=mult, combined_targets=combined,
        learning_active=learning_active, metals_set=set(metals_universe or METALS_UNIVERSE))


def all_decisions_v6(res: FullSystemV6Result) -> List[Decision]:
    return list(res.stock.decisions) + list(res.metals.decisions) + list(res.crypto.decisions)
