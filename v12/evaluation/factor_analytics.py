"""Factor-analytics / ablation engine.

Turns aggregate metrics into a per-factor-family verdict, so we admit or reject a
factor on evidence, not on whether the headline number wiggled:

  * Ablation: leave-one-family-out marginal OOS IC + standalone IC per family.
  * Significance: fold-level t-stat (folds are non-overlapping -> honest, unlike
    the overlap-inflated per-date ICIR).
  * Decay: composite rank-IC vs forward horizon (alpha half-life intuition).
  * Redundancy: feature correlation clusters (|corr| > threshold).

Uses the same purged walk-forward + leakage-checked panel as the backtest.
"""
from __future__ import annotations

from typing import Dict, List

import numpy as np
import pandas as pd

from .metrics import information_coefficient


def factor_families(feature_cols: List[str]) -> Dict[str, List[str]]:
    """Group feature columns into orthogonal factor families."""
    trend = {"adx", "kama_dist", "hull_dist", "supertrend", "trend_slope", "trend_r2"}
    volume = {"rel_volume", "obv_z", "cmf", "vwap_dist", "vol_accel"}
    meanrev = {"boll_z", "ema_dist", "pct_rank_60", "rsi"}

    def has(c, *subs):
        return any(c.startswith(s) for s in subs)

    fams: Dict[str, List[str]] = {
        "momentum": [c for c in feature_cols if c.startswith("mom_")],
        "trend": [c for c in feature_cols if c in trend],
        "volume": [c for c in feature_cols if c in volume],
        "volatility": [c for c in feature_cols
                       if has(c, "realized_vol", "atr_pct", "parkinson", "yang_zhang", "vol_of_vol")],
        "mean_reversion": [c for c in feature_cols if c in meanrev],
        "relative_strength": [c for c in feature_cols if has(c, "rs_", "beta_")],
        "breadth": [c for c in feature_cols if c.startswith("breadth_")],
        "cross_sectional": [c for c in feature_cols if c.startswith("csrank_")],
        "fundamental": [c for c in feature_cols if c.startswith("f_")],
        "insider": [c for c in feature_cols if c.startswith("i_")],
    }
    return {k: v for k, v in fams.items() if v}


def select_features(panel, feature_cols: List[str], keep_families=None,
                    prune_corr: float = None) -> List[str]:
    """Restrict to chosen factor families and/or greedily drop redundant features.

    Evidence-driven pruning: the ablation showed only volatility + cross_sectional
    add marginal alpha, and 73 feature pairs are |corr|>0.7 — a smaller, lower-
    redundancy set should generalize better.
    """
    cols = list(feature_cols)
    if keep_families:
        fams = factor_families(feature_cols)
        keep = set()
        for f in keep_families:
            keep |= set(fams.get(f, []))
        cols = [c for c in feature_cols if c in keep]
    if prune_corr and len(cols) > 1:
        corr = panel[cols].corr().abs()
        kept: List[str] = []
        for c in cols:
            if all(corr.loc[c, k] <= prune_corr for k in kept):
                kept.append(c)
        cols = kept
    return cols


def ablation(panel, feature_cols, folds, model_name, cfg_models) -> Dict:
    """Full IC + per-family standalone and leave-one-out marginal IC."""
    from experiments.run_experiment import _walk_forward_predict

    def _ic(cols):
        if not cols:
            return float("nan"), []
        oos, fold_ics, _ = _walk_forward_predict(panel, cols, list(folds), model_name, cfg_models)
        return float(np.nanmean(fold_ics)), fold_ics

    full_ic, full_folds = _ic(feature_cols)
    fams = factor_families(feature_cols)
    rows = {}
    for fam, cols in fams.items():
        ic_only, _ = _ic(cols)
        ic_without, _ = _ic([c for c in feature_cols if c not in cols])
        rows[fam] = {
            "n": len(cols),
            "standalone_ic": ic_only,
            "ic_without": ic_without,
            "marginal_ic": full_ic - ic_without,  # how much the family ADDS
        }
    return {"full_ic": full_ic, "full_fold_ics": full_folds, "families": rows}


def ic_significance(fold_ics: List[float]) -> Dict[str, float]:
    """Honest fold-level significance (folds are non-overlapping OOS windows)."""
    ics = np.array([x for x in fold_ics if x == x])
    n = len(ics)
    if n < 2:
        return {"mean": float("nan"), "std": float("nan"), "t_stat": float("nan"), "n_folds": n}
    mean, std = ics.mean(), ics.std(ddof=1)
    t = mean / (std / np.sqrt(n)) if std > 0 else float("nan")
    return {"mean": float(mean), "std": float(std), "t_stat": float(t), "n_folds": n}


def signal_decay(oos_pred: pd.Series, close: pd.DataFrame, names: List[str],
                 horizons=(5, 10, 20, 40, 60, 120)) -> Dict[int, float]:
    """Composite rank-IC of the OOS prediction vs de-meaned forward returns at
    several horizons — the alpha-decay curve."""
    out = {}
    for h in horizons:
        fwd = close[names].shift(-h) / close[names] - 1.0
        tgt = fwd.sub(fwd.mean(axis=1), axis=0).stack()
        tgt.index.names = ["date", "ticker"]
        ic = information_coefficient(oos_pred, tgt.reindex(oos_pred.index))
        out[h] = ic["ic_mean"]
    return out


def ic_by_regime(oos_pred: pd.Series, target: pd.Series, regime: pd.Series) -> Dict[str, dict]:
    """Mean per-date rank-IC within each market regime (the reversal diagnosis)."""
    df = pd.DataFrame({"pred": oos_pred, "y": target}).dropna()
    if df.empty:
        return {}
    dates = df.index.get_level_values("date")
    df = df.assign(regime=regime.reindex(dates).values)
    out = {}
    for reg, sub in df.groupby("regime"):
        by_date = sub.groupby(level="date").apply(
            lambda g: g["pred"].corr(g["y"], method="spearman")).dropna()
        if len(by_date):
            out[str(reg)] = {"ic_mean": float(by_date.mean()), "n_days": int(len(by_date))}
    return out


def redundancy(panel, feature_cols, threshold: float = 0.7) -> List:
    """Highly-correlated feature pairs (candidates for pruning)."""
    corr = panel[feature_cols].corr()
    pairs = []
    for i, a in enumerate(feature_cols):
        for b in feature_cols[i + 1:]:
            c = corr.loc[a, b]
            if pd.notna(c) and abs(c) > threshold:
                pairs.append((a, b, float(c)))
    return sorted(pairs, key=lambda x: -abs(x[2]))


def ic_by_year(oos_pred: pd.Series, target: pd.Series) -> Dict[int, float]:
    df = pd.DataFrame({"pred": oos_pred, "y": target}).dropna()
    if df.empty:
        return {}
    years = df.index.get_level_values("date").year
    out = {}
    for yr in sorted(set(years)):
        sub = df[years == yr]
        by_date = sub.groupby(level="date").apply(
            lambda g: g["pred"].corr(g["y"], method="spearman"))
        out[int(yr)] = float(by_date.dropna().mean())
    return out
