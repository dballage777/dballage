"""Precious-metals sleeve — the gold/silver book for variant 6 (shadow).

The metals analogue of ``crypto_sleeve``. Same governance machinery, reusing the
validated components, with the metals-specific rules from SYSTEM_SPEC §1 (revised
2026-06-30):

    metals universe                      -> METALS_UNIVERSE (GLD/IAU/SLV/PPLT/PALL/GDX)
    regime benchmark                     -> GLD (gold as the metals "market")
    validated features                   -> volatility + cross_sectional (pruned);
                                            NO sector-neutral (metals have no sectors)
    multi-horizon blend                  -> long 60d + medium 20d
    6-state regime exposure              -> classify_regime_6 on GLD
    fractional-Kelly risk budget         -> kelly_exposure (25% cap)
    EV gate / no-trade / correlation     -> DecisionEngine (default = CASH)
    graduated (conviction) sizing        -> DecisionEngine
    per-position cap (metals 10%)        -> DecisionEngine max_weight
    asset-class cap (metals <= 15%)      -> SleeveManager
    hard-risk governor                   -> risk_gov_mult
    shadow sleeve + paper ledger         -> logged, never allocated capital

Gold is a defensive diversifier (uncorrelated/negative vs equities in crises) —
evidence-backed at the 5-15% range and a stronger crisis hedge than crypto. This
sleeve is SHADOW only until it passes the forward test + validation gate.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Optional

import numpy as np
import pandas as pd

from ..config import ExperimentConfig, METALS_UNIVERSE, METALS_BENCHMARK
from ..data import load_prices
from ..features import build_dataset
from ..evaluation.factor_analytics import select_features
from ..models import build_model
from ..regime import classify_regime_6, REGIME6_EXPOSURE
from ..risk.sizing import kelly_exposure
from ..strategies.blend import blend_horizons
from ..portfolio.sleeves import Sleeve, SleeveManager
from ..execution import DecisionEngine, Decision

SLEEVE_NAME = "metals_full_goal"

HORIZON_WEIGHTS = {60: 0.75, 20: 0.25}
METALS_CLASS_CAP = 0.15          # SPEC: precious metals 0-15% of capital
METALS_POSITION_CAP = 0.10       # SPEC: metals 5-10% per position
KELLY_FRACTION = 0.25            # fractional Kelly, max 25%


@dataclass
class MetalsSleeveResult:
    date: pd.Timestamp
    regime: str
    regime_exposure: float
    kelly_mult: float
    governor_exposure: float
    corr_flag: bool
    decisions: List[Decision]
    targets: Dict[str, float]
    sources: str = "metals price+volatility, 6-regime (GLD), multi-horizon"

    @property
    def n_positions(self) -> int:
        return sum(1 for w in self.targets.values() if w > 0)

    @property
    def metals_exposure(self) -> float:
        return float(sum(self.targets.values()))


def _score_horizon(data, cfg: ExperimentConfig, horizon: int, feats: Optional[List[str]]):
    cfg.features.target_horizon = horizon
    cfg.__post_init__()
    panel, all_feats = build_dataset(data, cfg.features, cfg.data, keep_unlabeled=True)
    if feats is None:
        feats = select_features(panel, all_feats, ["volatility", "cross_sectional"],
                                prune_corr=0.9)
    panel = panel[feats + ["target"]]
    labelled = panel.dropna(subset=["target"])
    model = build_model("elasticnet", cfg.models.random_state)
    model.fit(labelled[feats].values, labelled["target"].values)
    last_date = panel.index.get_level_values("date").max()
    today = panel.xs(last_date, level="date")
    scores = pd.Series(model.predict(today[feats].values), index=today.index)
    return scores, feats, last_date


def build_metals_sleeve(end: str = "2026-06-20",
                        universe: Optional[List[str]] = None,
                        log_path: Optional[str] = None,
                        risk_gov_mult: float = 1.0) -> MetalsSleeveResult:
    """Run the full GOAL-conditioned precious-metals sleeve for the latest date."""
    cfg = ExperimentConfig(name="paper_metals")
    cfg.data.universe = list(universe or METALS_UNIVERSE)
    cfg.data.benchmark = METALS_BENCHMARK
    cfg.data.rs_refs = [METALS_BENCHMARK]          # GLD as the metals "market"
    cfg.data.start, cfg.data.end = "2010-01-01", end
    cfg.features.sector_neutral = False            # metals have no sectors

    data = load_prices(cfg.data)

    scores_by_h: Dict[int, pd.Series] = {}
    feats = None
    last_date = None
    for h in HORIZON_WEIGHTS:
        s, feats, last_date = _score_horizon(data, cfg, h, feats)
        scores_by_h[h] = s
    scores = blend_horizons(scores_by_h, HORIZON_WEIGHTS)

    # ---- 6-state regime exposure on GLD (point-in-time) ----
    reg6 = classify_regime_6(data.close[cfg.data.benchmark])
    regime = str(reg6.reindex([last_date]).fillna("unknown").iloc[0])
    regime_exposure = REGIME6_EXPOSURE.get(regime, 0.0)

    # ---- fractional-Kelly risk budget from recent gold behaviour ----
    bench_rets = data.close[cfg.data.benchmark].pct_change().dropna().tail(60)
    kelly_mult = float(np.clip(kelly_exposure(bench_rets, fraction=KELLY_FRACTION,
                                              max_exposure=1.0), 0.0, 1.0))
    governor_exposure = regime_exposure * (0.5 + 0.5 * kelly_mult) * float(risk_gov_mult)

    recent = data.close[cfg.data.universe].pct_change().dropna().tail(60)

    eng = DecisionEngine(max_weight=METALS_POSITION_CAP, top_quantile=cfg.backtest.top_quantile)
    decisions = eng.decide(scores, regime_risk_on=(regime_exposure > 0),
                           governor_exposure=governor_exposure, recent_returns=recent,
                           sources="metals price+volatility, 6-regime (GLD), multi-horizon")
    corr_flag = eng._correlation_overload(
        set(scores.sort_values(ascending=False).index[:max(int(len(scores) * 0.30), 1)]),
        recent, 0.80)

    # ---- asset-class cap (metals <= 15%) ----
    raw_tgt = pd.Series({d.asset: d.target_weight for d in decisions if d.target_weight > 0})
    mgr = SleeveManager()
    mgr.register(Sleeve(name=SLEEVE_NAME, asset_class="metals", allocation=1.0,
                        status="live", max_class_weight=METALS_CLASS_CAP, bucket="core"))
    combined = mgr.combine({SLEEVE_NAME: raw_tgt}) if not raw_tgt.empty else pd.Series(dtype=float)
    targets = {k: float(v) for k, v in combined.items()}

    result = MetalsSleeveResult(date=last_date, regime=regime, regime_exposure=regime_exposure,
                                kelly_mult=kelly_mult, governor_exposure=governor_exposure,
                                corr_flag=corr_flag, decisions=decisions, targets=targets)

    if log_path is not None:
        from ..execution.ledger import ShadowLedger
        led = ShadowLedger(log_path)
        led.log(date=f"{last_date:%Y-%m-%d}", sleeve=SLEEVE_NAME, status="shadow",
                decisions=DecisionEngine.to_records(decisions), day_return=None)
    return result
