"""Factor scorecard: per-family marginal alpha, significance, decay, redundancy.

Mirrors run_experiment's data/feature loading, then runs the ablation engine
instead of a backtest. The output answers, factor family by factor family:
"does this add statistically meaningful out-of-sample alpha?"

    python -m experiments.factor_analysis --broad --horizon 60 --fundamentals \
        --sector-neutral --insider --start 2015-01-01 --end 2026-06-20 --folds 34 \
        --models ridge --name v13_scorecard
"""
from __future__ import annotations

import argparse
import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import warnings
warnings.filterwarnings("ignore")

from v12.config import ExperimentConfig, BROAD_UNIVERSE
from v12.data import load_prices
from v12.features import build_dataset
from v12.validation import PurgedWalkForward, assert_no_leakage
from v12.evaluation.factor_analytics import (ablation, ic_significance, signal_decay,
                                             redundancy, ic_by_year)
from experiments.run_experiment import _walk_forward_predict
from v12.utils import get_logger

log = get_logger("factor_analysis")


def _fmt(v):
    return "n/a" if v != v else f"{v:+.4f}"


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--broad", action="store_true")
    p.add_argument("--horizon", type=int, default=None)
    p.add_argument("--fundamentals", action="store_true")
    p.add_argument("--sector-neutral", action="store_true")
    p.add_argument("--insider", action="store_true")
    p.add_argument("--start", default=None)
    p.add_argument("--end", default=None)
    p.add_argument("--folds", type=int, default=None)
    p.add_argument("--model", default="ridge")  # ridge: uses all features -> clean ablation
    p.add_argument("--name", default="factor_scorecard")
    args = p.parse_args()

    cfg = ExperimentConfig(name=args.name)
    if args.broad:
        cfg.data.universe = list(BROAD_UNIVERSE)
    if args.start:
        cfg.data.start = args.start
    if args.end:
        cfg.data.end = args.end
    if args.folds:
        cfg.validation.n_splits = args.folds
    if args.horizon:
        cfg.features.target_horizon = args.horizon
        cfg.__post_init__()
    cfg.features.use_fundamentals = args.fundamentals
    cfg.features.sector_neutral = args.sector_neutral
    cfg.features.use_insider = args.insider
    cfg.models.candidates = [args.model]

    # --- load data + features (same path as run_experiment) ---
    data = load_prices(cfg.data)
    names = [t for t in cfg.data.universe if t in data.close.columns]
    fundamentals = insider = None
    if cfg.features.use_fundamentals:
        from v12.data.fundamentals import load_fundamentals
        fundamentals = load_fundamentals(cfg.data.universe, cfg.data.cache_dir, cfg.data.sec_user_agent or None)
    if cfg.features.use_insider:
        from v12.data.insider import load_insider
        insider = load_insider(cfg.data.universe, cfg.data.cache_dir, cfg.data.sec_user_agent or None,
                               start_year=int(cfg.data.start[:4]), end_year=int(cfg.data.end[:4]))
    panel, feature_cols = build_dataset(data, cfg.features, cfg.data, fundamentals, insider)

    wf = PurgedWalkForward(cfg.validation.n_splits, cfg.validation.train_min_days,
                           cfg.validation.test_days, cfg.validation.embargo_days,
                           cfg.features.target_horizon)
    folds = list(wf.split(panel))
    assert_no_leakage(panel, feature_cols, iter(folds), cfg.features.target_horizon)
    log.info("Panel %d rows, %d features, %d folds.", len(panel), len(feature_cols), len(folds))

    # --- analytics ---
    log.info("Running ablation (this fits the model many times)...")
    abl = ablation(panel, feature_cols, folds, args.model, cfg.models)
    sig = ic_significance(abl["full_fold_ics"])
    oos_pred, _, _ = _walk_forward_predict(panel, feature_cols, folds, args.model, cfg.models)
    decay = signal_decay(oos_pred, data.close, names)
    yearly = ic_by_year(oos_pred, panel["target"])
    redun = redundancy(panel, feature_cols, 0.7)

    # --- report ---
    L = [f"# Factor Scorecard — `{cfg.name}`",
         f"_model: {args.model} · {len(folds)} folds · horizon {cfg.features.target_horizon}d · "
         f"{len(feature_cols)} features · data {data.source}_", ""]
    L.append(f"**Composite OOS rank-IC = {_fmt(abl['full_ic'])}** · fold t-stat "
             f"**{sig['t_stat']:.2f}** (n={sig['n_folds']} non-overlapping folds; "
             f"|t|>2 ≈ significant)")

    L.append("\n## Factor family contribution (the verdict)")
    L.append("| family | #feat | standalone IC | marginal IC (leave-one-out) | verdict |")
    L.append("|---|---|---|---|---|")
    for fam, r in sorted(abl["families"].items(), key=lambda kv: -(kv[1]["marginal_ic"] if kv[1]["marginal_ic"]==kv[1]["marginal_ic"] else -9)):
        m = r["marginal_ic"]
        verdict = "ADDS" if m > 0.002 else ("neutral" if m > -0.002 else "HURTS")
        L.append(f"| {fam} | {r['n']} | {_fmt(r['standalone_ic'])} | {_fmt(m)} | {verdict} |")

    L.append("\n## Alpha decay (composite IC by holding horizon)")
    L.append("| horizon (d) | " + " | ".join(str(h) for h in decay) + " |")
    L.append("|" + "---|" * (len(decay) + 1))
    L.append("| rank-IC | " + " | ".join(_fmt(v) for v in decay.values()) + " |")

    if yearly:
        L.append("\n## IC by year")
        L.append("| year | " + " | ".join(str(y) for y in yearly) + " |")
        L.append("|" + "---|" * (len(yearly) + 1))
        L.append("| IC | " + " | ".join(_fmt(v) for v in yearly.values()) + " |")

    L.append(f"\n## Redundancy (|corr|>0.7): {len(redun)} pairs")
    for a, b, c in redun[:15]:
        L.append(f"- {a} ↔ {b}: {c:+.2f}")

    os.makedirs(cfg.output_dir, exist_ok=True)
    path = os.path.join(cfg.output_dir, f"{cfg.name}_factor_analysis.md")
    report = "\n".join(L) + "\n"
    open(path, "w").write(report)
    log.info("Scorecard -> %s", path)
    print("\n" + report)


if __name__ == "__main__":
    main()
