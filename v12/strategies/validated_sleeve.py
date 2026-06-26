"""Variant 1 — the VALIDATED baseline sleeve (regime-gated low-vol equity).

This is the strategy the backtest actually validated (Sharpe 0.88 vs SPY 0.74,
−19% max drawdown), expressed as a sleeve so it can race head-to-head against
the heavier GOAL variants in the shadow horse-race. Deliberately *simple*:

    stock universe (BROAD)               -> selection skill on a real universe
    validated features                   -> volatility + cross_sectional (pruned),
                                            sector-neutral
    single long horizon (60d)            -> no multi-horizon blend
    2-state regime gate                  -> classify_regime risk_on (not 6-state)
    EV gate / no-trade / graduated size  -> DecisionEngine (default = CASH)
    per-position cap 8%                  -> DecisionEngine max_weight
    NO crypto, NO Kelly, NO 6-regime     -> that's the point: it's the control arm

Returns the same SleeveResult shape as variant 2 so the runner can treat all
sleeves uniformly. SHADOW / decision logic only.
"""
from __future__ import annotations

from typing import List, Optional

import pandas as pd

from ..config import ExperimentConfig, BROAD_UNIVERSE
from ..data import load_prices
from ..features import build_dataset
from ..evaluation.factor_analytics import select_features
from ..models import build_model
from ..regime import classify_regime
from ..portfolio.microcap import enforce_microcap_caps
from ..execution import DecisionEngine
from .stock_sleeve import SleeveResult, STOCK_POSITION_CAP

SLEEVE_NAME = "equity_validated"


def build_validated_sleeve(end: str = "2026-06-20",
                           universe: Optional[List[str]] = None,
                           log_path: Optional[str] = None) -> SleeveResult:
    """Run the validated low-vol baseline for the latest date (variant 1)."""
    cfg = ExperimentConfig(name="paper_v1")
    cfg.data.universe = list(universe or BROAD_UNIVERSE)
    cfg.data.start, cfg.data.end = "2015-01-01", end
    cfg.features.target_horizon = 60
    cfg.features.sector_neutral = True
    cfg.__post_init__()

    data = load_prices(cfg.data)
    panel, all_feats = build_dataset(data, cfg.features, cfg.data, keep_unlabeled=True)
    feats = select_features(panel, all_feats, ["volatility", "cross_sectional"], prune_corr=0.9)
    panel = panel[feats + ["target"]]

    labelled = panel.dropna(subset=["target"])
    model = build_model("elasticnet", cfg.models.random_state)
    model.fit(labelled[feats].values, labelled["target"].values)

    last_date = panel.index.get_level_values("date").max()
    today = panel.xs(last_date, level="date")
    scores = pd.Series(model.predict(today[feats].values), index=today.index)

    reg = classify_regime(data.close[cfg.data.benchmark])
    risk_on = bool(reg["risk_on"].reindex([last_date]).fillna(0).iloc[0])

    eng = DecisionEngine(max_weight=STOCK_POSITION_CAP, top_quantile=cfg.backtest.top_quantile)
    decisions = eng.decide(scores, regime_risk_on=risk_on, governor_exposure=1.0,
                           sources="price+volatility (validated), 2-state regime")

    raw = pd.Series({d.asset: d.target_weight for d in decisions if d.target_weight > 0})
    targets = {k: float(v) for k, v in enforce_microcap_caps(raw).items()} if not raw.empty else {}

    result = SleeveResult(
        date=last_date, regime=("risk_on" if risk_on else "risk_off"),
        regime_exposure=(1.0 if risk_on else 0.0), kelly_mult=1.0,
        governor_exposure=(1.0 if risk_on else 0.0), corr_flag=False,
        decisions=decisions, targets=targets,
        sources="price+volatility (validated), 2-state regime")

    if log_path is not None:
        from ..execution.ledger import ShadowLedger
        led = ShadowLedger(log_path)
        led.log(date=f"{last_date:%Y-%m-%d}", sleeve=SLEEVE_NAME, status="shadow",
                decisions=DecisionEngine.to_records(decisions), day_return=None)
    return result
