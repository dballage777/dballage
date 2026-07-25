"""Aggressive momentum books (stock + crypto) and their combined system.

Reuses the validated machinery (feature pipeline, 6-state regime, Kelly sizing,
EV/correlation decision engine, sleeve caps) but tuned to an aggressive,
evidence-bounded profile:

    signal            -> cross-sectional MOMENTUM (the effect with real crypto
                         evidence: ~weekly winner returns, Sharpe ~0.7-1.3) + the
                         validated cross-sectional features
    horizon           -> SHORT: 5d + 15d blend (days-to-weeks; NOT intraday)
    universe          -> LIQUID mid/large-cap high-beta stocks + top liquid coins
                         (illiquid micro-caps / meme coins deliberately excluded)
    sizing            -> HALF Kelly (0.50) — never full (full Kelly = 50%+ DD / ruin)
    caps              -> stocks <=60%, crypto <=60%, per-position <=20% (aggressive)
    concentration     -> top 20% by score (more concentrated than the core system)
    hard stops        -> looser but REAL: -30% drawdown / -8% daily / 3-loss freeze
                         (applied by the runner via the configurable governor)

SHADOW / paper only. Nothing here allocates real capital or touches the 7 tests.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Set

import numpy as np
import pandas as pd

from ..config import ExperimentConfig, CRYPTO_UNIVERSE, CRYPTO_BENCHMARK
from ..data import load_prices
from ..features import build_dataset
from ..evaluation.factor_analytics import select_features
from ..models import build_model
from ..regime import classify_regime_6, REGIME6_EXPOSURE
from ..risk.sizing import kelly_exposure
from ..strategies.blend import blend_horizons
from ..portfolio.sleeves import Sleeve, SleeveManager
from ..execution import DecisionEngine, Decision

STOCK_BOOK = "aggr_stock_mom"
CRYPTO_BOOK = "aggr_crypto_mom"
SYSTEM_BOOK = "aggressive_system"

# ---- aggressive, evidence-bounded parameters ----
HORIZON_WEIGHTS = {15: 0.6, 5: 0.4}     # SHORT horizon (days-to-weeks), NOT intraday
HALF_KELLY = 0.50                        # aggressive ceiling; never full Kelly
STOCK_CLASS_CAP = 0.60
CRYPTO_CLASS_CAP = 0.60
POSITION_CAP = 0.20                      # up to 20% per name (aggressive)
TOP_QUANTILE = 0.20                      # concentrate in the top 20% by momentum

# LIQUID, higher-beta mid/large-cap stocks (deliberately NOT illiquid micro-caps).
# The aggressive stock "market" benchmark is QQQ (tech/growth heavy).
AGGR_STOCK_BENCHMARK = "QQQ"
AGGR_STOCK_UNIVERSE: List[str] = [
    "NVDA", "AMD", "TSLA", "META", "AMZN", "NFLX", "AVGO", "MU", "SMCI",
    "SHOP", "PYPL", "SQ", "COIN", "MSTR", "PLTR", "CRWD", "SNOW", "NET",
    "DDOG", "ROKU", "UBER", "ABNB", "MRVL", "PANW",
]
# top LIQUID coins (reuse the vetted crypto universe; excludes illiquid micro-caps)
AGGR_CRYPTO_BENCHMARK = CRYPTO_BENCHMARK
AGGR_CRYPTO_UNIVERSE: List[str] = list(CRYPTO_UNIVERSE)


@dataclass
class AggressiveBookResult:
    book: str
    date: pd.Timestamp
    regime: str
    regime_exposure: float
    kelly_mult: float
    governor_exposure: float
    corr_flag: bool
    decisions: List[Decision]
    targets: Dict[str, float]
    source: str = ""

    @property
    def n_positions(self) -> int:
        return sum(1 for w in self.targets.values() if w > 0)

    @property
    def exposure(self) -> float:
        return float(sum(self.targets.values()))


@dataclass
class AggressiveSystemResult:
    date: pd.Timestamp
    stock: AggressiveBookResult
    crypto: AggressiveBookResult
    combined_targets: Dict[str, float]
    crypto_set: Set[str] = field(default_factory=set)

    @property
    def total_exposure(self) -> float:
        return float(sum(self.combined_targets.values()))

    @property
    def crypto_exposure(self) -> float:
        return float(sum(v for k, v in self.combined_targets.items() if k in self.crypto_set))

    @property
    def stock_exposure(self) -> float:
        return float(sum(v for k, v in self.combined_targets.items() if k not in self.crypto_set))

    @property
    def cash(self) -> float:
        return float(max(1.0 - self.total_exposure, 0.0))


def _score_horizon(data, cfg: ExperimentConfig, horizon: int, feats: Optional[List[str]]):
    cfg.features.target_horizon = horizon
    cfg.__post_init__()
    panel, all_feats = build_dataset(data, cfg.features, cfg.data, keep_unlabeled=True)
    if feats is None:
        # MOMENTUM-led selection (the aggressive edge), plus cross-sectional
        feats = select_features(panel, all_feats, ["momentum", "cross_sectional"],
                                prune_corr=0.9)
    panel = panel[feats + ["target"]]
    labelled = panel.dropna(subset=["target"])
    model = build_model("elasticnet", cfg.models.random_state)
    model.fit(labelled[feats].values, labelled["target"].values)
    last_date = panel.index.get_level_values("date").max()
    today = panel.xs(last_date, level="date")
    scores = pd.Series(model.predict(today[feats].values), index=today.index)
    return scores, feats, last_date


def build_aggressive_book(book: str, universe: List[str], benchmark: str,
                          class_cap: float, asset_class: str, start: str,
                          end: str = "2026-06-20",
                          risk_gov_mult: float = 1.0) -> AggressiveBookResult:
    """Build one aggressive short-horizon momentum book for the latest date."""
    cfg = ExperimentConfig(name=f"aggr_{book}")
    cfg.data.universe = list(universe)
    cfg.data.benchmark = benchmark
    cfg.data.rs_refs = [benchmark]
    cfg.data.start, cfg.data.end = start, end
    cfg.data.extra_benchmarks = []                 # keep the report universe clean
    cfg.features.sector_neutral = False

    data = load_prices(cfg.data)

    scores_by_h: Dict[int, pd.Series] = {}
    feats = None
    last_date = None
    for h in HORIZON_WEIGHTS:
        s, feats, last_date = _score_horizon(data, cfg, h, feats)
        scores_by_h[h] = s
    scores = blend_horizons(scores_by_h, HORIZON_WEIGHTS)

    bench = data.close[benchmark] if benchmark in data.close.columns else data.close.iloc[:, 0]
    reg6 = classify_regime_6(bench)
    regime = str(reg6.reindex([last_date]).fillna("unknown").iloc[0])
    regime_exposure = REGIME6_EXPOSURE.get(regime, 0.0)

    # HALF-Kelly risk budget (aggressive ceiling; never full)
    bench_rets = bench.pct_change().dropna().tail(60)
    kelly_mult = float(np.clip(kelly_exposure(bench_rets, fraction=HALF_KELLY,
                                              max_exposure=1.0), 0.0, 1.0))
    governor_exposure = regime_exposure * (0.5 + 0.5 * kelly_mult) * float(risk_gov_mult)

    recent = data.close[cfg.data.universe].pct_change().dropna().tail(60)
    eng = DecisionEngine(max_weight=POSITION_CAP, top_quantile=TOP_QUANTILE)
    src = f"{asset_class} momentum (short 5d+15d), 6-regime ({benchmark})"
    decisions = eng.decide(scores, regime_risk_on=(regime_exposure > 0),
                           governor_exposure=governor_exposure, recent_returns=recent,
                           sources=src)
    corr_flag = eng._correlation_overload(
        set(scores.sort_values(ascending=False).index[:max(int(len(scores) * TOP_QUANTILE), 1)]),
        recent, 0.80)

    raw_tgt = pd.Series({d.asset: d.target_weight for d in decisions if d.target_weight > 0})
    mgr = SleeveManager()
    mgr.register(Sleeve(name=book, asset_class=asset_class, allocation=1.0,
                        status="live", max_class_weight=class_cap, bucket="experimental"))
    combined = mgr.combine({book: raw_tgt}) if not raw_tgt.empty else pd.Series(dtype=float)
    targets = {k: float(v) for k, v in combined.items()}

    return AggressiveBookResult(book=book, date=last_date, regime=regime,
                                regime_exposure=regime_exposure, kelly_mult=kelly_mult,
                                governor_exposure=governor_exposure, corr_flag=corr_flag,
                                decisions=decisions, targets=targets, source=data.source)


def build_aggressive_system(end: str = "2026-06-20",
                            stock_universe: Optional[List[str]] = None,
                            crypto_universe: Optional[List[str]] = None,
                            stock_gov_mult: float = 1.0, crypto_gov_mult: float = 1.0
                            ) -> AggressiveSystemResult:
    """Build both aggressive books and combine them (total exposure capped at 1.0)."""
    stock = build_aggressive_book(
        STOCK_BOOK, list(stock_universe or AGGR_STOCK_UNIVERSE), AGGR_STOCK_BENCHMARK,
        STOCK_CLASS_CAP, "aggr_stock", start="2015-01-01", end=end, risk_gov_mult=stock_gov_mult)
    crypto = build_aggressive_book(
        CRYPTO_BOOK, list(crypto_universe or AGGR_CRYPTO_UNIVERSE), AGGR_CRYPTO_BENCHMARK,
        CRYPTO_CLASS_CAP, "aggr_crypto", start="2018-01-01", end=end, risk_gov_mult=crypto_gov_mult)

    combined: Dict[str, float] = {}
    for tgt in (stock.targets, crypto.targets):
        for a, w in tgt.items():
            combined[a] = combined.get(a, 0.0) + w
    # aggressive but bounded: total invested never exceeds 100%
    total = sum(combined.values())
    if total > 1.0 and total > 0:
        combined = {k: v / total for k, v in combined.items()}
    combined = {k: float(v) for k, v in combined.items() if v > 0}

    date = max(stock.date, crypto.date)
    return AggressiveSystemResult(date=date, stock=stock, crypto=crypto,
                                  combined_targets=combined,
                                  crypto_set=set(crypto_universe or AGGR_CRYPTO_UNIVERSE))


def all_decisions(res: AggressiveSystemResult) -> List[Decision]:
    return list(res.stock.decisions) + list(res.crypto.decisions)
