"""Variant 2 — the full GOAL-conditioned STOCK sleeve (shadow).

This assembles *every* GOAL condition for the equity book into one
decision pipeline, reusing the already-validated components rather than
inventing new signal:

    full stock universe                  -> BROAD_UNIVERSE (54 names)
    validated features                   -> volatility + cross_sectional (pruned),
                                            sector-neutral
    multi-horizon blend                  -> long (60d) + medium (20d), GOAL weights
    6-state regime exposure              -> classify_regime_6 -> REGIME6_EXPOSURE
    fractional-Kelly risk budget         -> kelly_exposure (25% cap)
    EV gate / confidence / no-trade      -> DecisionEngine (default = CASH)
    correlation-overload check           -> DecisionEngine (de-risk on crowding)
    graduated (conviction) sizing        -> DecisionEngine
    per-position cap (stocks 8%)         -> DecisionEngine max_weight
    asset-class cap (stocks <= 70%)      -> SleeveManager
    microcap caps (10% agg / 1% pos)     -> enforce_microcap_caps
    shadow sleeve + paper ledger         -> SleeveManager / ShadowLedger

It runs as a SHADOW sleeve: decisions are logged and performance-tracked,
never allocated real or paper capital, until it passes its gate. It does
not place orders. PAPER/DECISION LOGIC ONLY.

The point of building this as a parallel shadow horse is to test whether
the heavier GOAL machinery (6-regime exposure, multi-horizon blend, Kelly,
class caps) actually beats the simple validated 2-state low-vol sleeve —
in honest forward paper, not in a re-optimized backtest.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional

import numpy as np
import pandas as pd

from ..config import ExperimentConfig, BROAD_UNIVERSE
from ..data import load_prices
from ..features import build_dataset
from ..evaluation.factor_analytics import select_features
from ..models import build_model
from ..regime import classify_regime_6, REGIME6_EXPOSURE
from ..risk.sizing import kelly_exposure
from ..strategies.blend import blend_horizons
from ..portfolio.sleeves import Sleeve, SleeveManager
from ..portfolio.microcap import enforce_microcap_caps
from ..execution import DecisionEngine, Decision

SLEEVE_NAME = "equity_full_goal"

# GOAL strategy horizons: long-term 70-80%, medium-term 15-25%. Short-term
# (intraday/event) is infeasible without intraday data, so its 5-10% is folded
# into the medium bucket. Weights are on the *blended signal*, not capital.
HORIZON_WEIGHTS = {60: 0.75, 20: 0.25}
STOCK_CLASS_CAP = 0.70           # GOAL: stocks 0-70% of capital
STOCK_POSITION_CAP = 0.08        # GOAL: stocks 5-8% per position
KELLY_FRACTION = 0.25            # GOAL: fractional Kelly, max 25%


@dataclass
class SleeveResult:
    date: pd.Timestamp
    regime: str
    regime_exposure: float
    kelly_mult: float
    governor_exposure: float
    corr_flag: bool
    decisions: List[Decision]
    targets: Dict[str, float]      # post class/microcap caps
    sources: str = "price+volatility (validated), 6-regime, multi-horizon"

    @property
    def n_positions(self) -> int:
        return sum(1 for w in self.targets.values() if w > 0)

    @property
    def stock_exposure(self) -> float:
        return float(sum(self.targets.values()))


def _score_horizon(data, cfg: ExperimentConfig, horizon: int,
                   feats: Optional[List[str]]) -> tuple[pd.Series, List[str], pd.Timestamp]:
    """Train the validated model for one horizon and score the latest date."""
    cfg.features.target_horizon = horizon
    cfg.__post_init__()
    panel, all_feats = build_dataset(data, cfg.features, cfg.data)
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


def build_stock_sleeve(end: str = "2026-06-20",
                       universe: Optional[List[str]] = None,
                       log_path: Optional[str] = None) -> SleeveResult:
    """Run the full GOAL-conditioned stock sleeve for the latest date.

    Returns a :class:`SleeveResult` with the GOAL-required per-decision output
    and the capped target weights. If ``log_path`` is given, appends the run to
    the shadow ledger as a SHADOW sleeve.
    """
    cfg = ExperimentConfig(name="paper_v2")
    cfg.data.universe = list(universe or BROAD_UNIVERSE)
    cfg.data.start, cfg.data.end = "2015-01-01", end
    cfg.features.sector_neutral = True

    data = load_prices(cfg.data)

    # ---- multi-horizon blend (long 60d + medium 20d) ----
    scores_by_h: Dict[int, pd.Series] = {}
    feats = None
    last_date = None
    for h in HORIZON_WEIGHTS:
        s, feats, last_date = _score_horizon(data, cfg, h, feats)
        scores_by_h[h] = s
    scores = blend_horizons(scores_by_h, HORIZON_WEIGHTS)

    # ---- 6-state regime exposure (point-in-time) ----
    reg6 = classify_regime_6(data.close[cfg.data.benchmark])
    regime = str(reg6.reindex([last_date]).fillna("unknown").iloc[0])
    regime_exposure = REGIME6_EXPOSURE.get(regime, 0.0)

    # ---- fractional-Kelly risk budget from recent benchmark behaviour ----
    bench_rets = data.close[cfg.data.benchmark].pct_change().dropna().tail(60)
    kelly_mult = kelly_exposure(bench_rets, fraction=KELLY_FRACTION, max_exposure=1.0)
    # Don't let a flat-but-positive Kelly zero out an otherwise-valid bull book:
    # Kelly *scales* exposure within the regime budget, floor at a small base so
    # the regime gate stays the dominant lever (Kelly trims, regime gates).
    kelly_mult = float(np.clip(kelly_mult, 0.0, 1.0))
    governor_exposure = regime_exposure * (0.5 + 0.5 * kelly_mult)

    # ---- recent returns for the correlation-overload check ----
    recent = data.close[cfg.data.universe].pct_change().dropna().tail(60)

    # ---- governed decisions (EV gate, no-trade, graduated sizing, caps) ----
    eng = DecisionEngine(max_weight=STOCK_POSITION_CAP,
                         top_quantile=cfg.backtest.top_quantile)
    decisions = eng.decide(scores, regime_risk_on=(regime_exposure > 0),
                           governor_exposure=governor_exposure,
                           recent_returns=recent,
                           sources="price+volatility (validated), 6-regime, multi-horizon")
    corr_flag = eng._correlation_overload(
        set(scores.sort_values(ascending=False).index[:max(int(len(scores) * 0.30), 1)]),
        recent, 0.80)

    # ---- asset-class cap (stocks <= 70%) via the sleeve manager ----
    raw_tgt = pd.Series({d.asset: d.target_weight for d in decisions if d.target_weight > 0})
    mgr = SleeveManager()
    mgr.register(Sleeve(name=SLEEVE_NAME, asset_class="stocks", allocation=1.0,
                        status="live", max_class_weight=STOCK_CLASS_CAP, bucket="core"))
    combined = mgr.combine({SLEEVE_NAME: raw_tgt}) if not raw_tgt.empty else pd.Series(dtype=float)
    # ---- microcap caps (scaffolding; no microcaps in this universe) ----
    combined = enforce_microcap_caps(combined)
    targets = {k: float(v) for k, v in combined.items()}

    result = SleeveResult(date=last_date, regime=regime, regime_exposure=regime_exposure,
                          kelly_mult=kelly_mult, governor_exposure=governor_exposure,
                          corr_flag=corr_flag, decisions=decisions, targets=targets)

    if log_path is not None:
        from ..execution.ledger import ShadowLedger
        led = ShadowLedger(log_path)
        led.log(date=f"{last_date:%Y-%m-%d}", sleeve=SLEEVE_NAME, status="shadow",
                decisions=DecisionEngine.to_records(decisions), day_return=None)
    return result
