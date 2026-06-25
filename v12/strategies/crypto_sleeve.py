"""Variant 3 — the full GOAL-conditioned CRYPTO sleeve (shadow).

The crypto analogue of ``stock_sleeve`` (variant 2). Same governance machinery,
reusing the validated components, but with the GOAL's crypto-specific rules:

    crypto universe (5-12)               -> CRYPTO_UNIVERSE (BTC/ETH + large alts)
    regime benchmark                     -> BTC-USD (crypto "market")
    validated features                   -> volatility + cross_sectional (pruned);
                                            NO sector-neutral (crypto has no sectors)
    multi-horizon blend                  -> long 60d + medium 20d (GOAL weights)
    6-state regime exposure              -> classify_regime_6 -> REGIME6_EXPOSURE
    fractional-Kelly risk budget         -> kelly_exposure (25% cap)
    EV gate / confidence / no-trade      -> DecisionEngine (default = CASH)
    correlation-overload check           -> DecisionEngine (de-risk on crowding)
    graduated (conviction) sizing        -> DecisionEngine
    per-position cap (crypto 12%)        -> DecisionEngine max_weight
    asset-class cap (crypto <= 30%)      -> SleeveManager
    microcap caps (5% agg / 0.5% pos)    -> enforce_microcap_caps (crypto thresholds)
    shadow sleeve + paper ledger         -> SleeveManager / ShadowLedger

Crypto carries higher volatility and is correlation-heavy (alts track BTC), so
the correlation-overload de-risk and the tighter 30% class cap matter more here.
Runs as a SHADOW sleeve: logged and performance-tracked, never allocated real or
paper capital, until it passes its gate. Decision logic only — no order placement.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Optional

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
from ..portfolio.microcap import enforce_microcap_caps
from ..execution import DecisionEngine, Decision

SLEEVE_NAME = "crypto_full_goal"

HORIZON_WEIGHTS = {60: 0.75, 20: 0.25}
CRYPTO_CLASS_CAP = 0.30          # GOAL: crypto 0-30% of capital
CRYPTO_POSITION_CAP = 0.12       # GOAL: crypto 8-12% per position
CRYPTO_MICROCAP_AGG = 0.05       # GOAL: crypto microcaps <= 5% aggregate
CRYPTO_MICROCAP_POS = 0.005      # GOAL: crypto microcaps <= 0.5% per token
KELLY_FRACTION = 0.25            # GOAL: fractional Kelly, max 25%


@dataclass
class CryptoSleeveResult:
    date: pd.Timestamp
    regime: str
    regime_exposure: float
    kelly_mult: float
    governor_exposure: float
    corr_flag: bool
    decisions: List[Decision]
    targets: Dict[str, float]
    sources: str = "crypto price+volatility, 6-regime (BTC), multi-horizon"

    @property
    def n_positions(self) -> int:
        return sum(1 for w in self.targets.values() if w > 0)

    @property
    def crypto_exposure(self) -> float:
        return float(sum(self.targets.values()))


def _score_horizon(data, cfg: ExperimentConfig, horizon: int,
                   feats: Optional[List[str]]):
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


def build_crypto_sleeve(end: str = "2026-06-20",
                        universe: Optional[List[str]] = None,
                        log_path: Optional[str] = None) -> CryptoSleeveResult:
    """Run the full GOAL-conditioned crypto sleeve for the latest date."""
    cfg = ExperimentConfig(name="paper_v3")
    cfg.data.universe = list(universe or CRYPTO_UNIVERSE)
    cfg.data.benchmark = CRYPTO_BENCHMARK
    cfg.data.rs_refs = [CRYPTO_BENCHMARK]          # BTC as the crypto "market"
    cfg.data.start, cfg.data.end = "2018-01-01", end
    cfg.features.sector_neutral = False            # crypto has no sectors

    data = load_prices(cfg.data)

    # ---- multi-horizon blend (long 60d + medium 20d) ----
    scores_by_h: Dict[int, pd.Series] = {}
    feats = None
    last_date = None
    for h in HORIZON_WEIGHTS:
        s, feats, last_date = _score_horizon(data, cfg, h, feats)
        scores_by_h[h] = s
    scores = blend_horizons(scores_by_h, HORIZON_WEIGHTS)

    # ---- 6-state regime exposure on BTC (point-in-time) ----
    reg6 = classify_regime_6(data.close[cfg.data.benchmark])
    regime = str(reg6.reindex([last_date]).fillna("unknown").iloc[0])
    regime_exposure = REGIME6_EXPOSURE.get(regime, 0.0)

    # ---- fractional-Kelly risk budget from recent BTC behaviour ----
    bench_rets = data.close[cfg.data.benchmark].pct_change().dropna().tail(60)
    kelly_mult = float(np.clip(kelly_exposure(bench_rets, fraction=KELLY_FRACTION,
                                              max_exposure=1.0), 0.0, 1.0))
    governor_exposure = regime_exposure * (0.5 + 0.5 * kelly_mult)

    # ---- recent returns for the correlation-overload check (alts track BTC) ----
    recent = data.close[cfg.data.universe].pct_change().dropna().tail(60)

    eng = DecisionEngine(max_weight=CRYPTO_POSITION_CAP,
                         top_quantile=cfg.backtest.top_quantile)
    decisions = eng.decide(scores, regime_risk_on=(regime_exposure > 0),
                           governor_exposure=governor_exposure,
                           recent_returns=recent,
                           sources="crypto price+volatility, 6-regime (BTC), multi-horizon")
    corr_flag = eng._correlation_overload(
        set(scores.sort_values(ascending=False).index[:max(int(len(scores) * 0.30), 1)]),
        recent, 0.80)

    # ---- asset-class cap (crypto <= 30%) ----
    raw_tgt = pd.Series({d.asset: d.target_weight for d in decisions if d.target_weight > 0})
    mgr = SleeveManager()
    mgr.register(Sleeve(name=SLEEVE_NAME, asset_class="crypto", allocation=1.0,
                        status="live", max_class_weight=CRYPTO_CLASS_CAP, bucket="core"))
    combined = mgr.combine({SLEEVE_NAME: raw_tgt}) if not raw_tgt.empty else pd.Series(dtype=float)
    # ---- crypto microcap caps (5% agg / 0.5% pos) ----
    combined = enforce_microcap_caps(combined, max_agg=CRYPTO_MICROCAP_AGG,
                                     max_pos=CRYPTO_MICROCAP_POS)
    targets = {k: float(v) for k, v in combined.items()}

    result = CryptoSleeveResult(date=last_date, regime=regime, regime_exposure=regime_exposure,
                                kelly_mult=kelly_mult, governor_exposure=governor_exposure,
                                corr_flag=corr_flag, decisions=decisions, targets=targets)

    if log_path is not None:
        from ..execution.ledger import ShadowLedger
        led = ShadowLedger(log_path)
        led.log(date=f"{last_date:%Y-%m-%d}", sleeve=SLEEVE_NAME, status="shadow",
                decisions=DecisionEngine.to_records(decisions), day_return=None)
    return result
