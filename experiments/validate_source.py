"""The evidence gate for a new data source — `validate_source`.

Before any new feed gets weight (or a paid subscription), it must prove it adds
out-of-sample edge over the *validated* baseline (volatility + cross_sectional).
This runs the same purged/embargoed walk-forward used everywhere else, computes
per-fold OOS IC for baseline vs baseline+candidate, and applies a paired
significance test. PASS only if the source improves IC, significantly, across
folds — the exact test that fundamentals and insider FAILED.

    # test a buildable source on a real-data host:
    python -m experiments.validate_source --source fundamentals --broad \
        --horizon 60 --sector-neutral --start 2015-01-01 --end 2026-06-20 --folds 34

    # test any feature family already in the panel:
    python -m experiments.validate_source --family momentum --broad --horizon 60

Verdict is printed and written to results/. Exit code is 0 on PASS, 2 on FAIL,
so n8n/CI can gate on it.
"""
from __future__ import annotations

import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import warnings
warnings.filterwarnings("ignore")

from v12.config import ExperimentConfig, BROAD_UNIVERSE
from v12.data import load_prices
from v12.features import build_dataset
from v12.validation import PurgedWalkForward, assert_no_leakage
from v12.evaluation.factor_analytics import (factor_families, ic_significance,
                                             source_verdict)
from experiments.run_experiment import _walk_forward_predict
from v12.utils import get_logger

log = get_logger("validate_source")

BASELINE_FAMILIES = ["volatility", "cross_sectional"]   # the validated set
# maps a --source name to (build flag, feature family it produces)
SOURCE_TO_FAMILY = {
    "fundamentals": ("use_fundamentals", "fundamental"),
    "insider": ("use_insider", "insider"),
}


def _fmt(v):
    return "n/a" if v != v else f"{v:+.4f}"


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--source", choices=list(SOURCE_TO_FAMILY),
                   help="a buildable source (sets its build flag + tests its family)")
    p.add_argument("--family", help="test any feature family already in the panel (e.g. momentum)")
    p.add_argument("--broad", action="store_true")
    p.add_argument("--horizon", type=int, default=60)
    p.add_argument("--sector-neutral", action="store_true")
    p.add_argument("--start", default="2015-01-01")
    p.add_argument("--end", default="2026-06-20")
    p.add_argument("--folds", type=int, default=None)
    p.add_argument("--model", default="ridge")
    p.add_argument("--min-gain", type=float, default=0.002)
    p.add_argument("--t-threshold", type=float, default=2.0)
    args = p.parse_args()

    if not args.source and not args.family:
        p.error("specify --source or --family")
    cand_family = SOURCE_TO_FAMILY[args.source][1] if args.source else args.family
    label = args.source or args.family

    cfg = ExperimentConfig(name=f"validate_{label}")
    if args.broad:
        cfg.data.universe = list(BROAD_UNIVERSE)
    cfg.data.start, cfg.data.end = args.start, args.end
    if args.folds:
        cfg.validation.n_splits = args.folds
    cfg.features.target_horizon = args.horizon
    cfg.features.sector_neutral = args.sector_neutral
    if args.source:
        setattr(cfg.features, SOURCE_TO_FAMILY[args.source][0], True)
    cfg.__post_init__()
    cfg.models.candidates = [args.model]

    data = load_prices(cfg.data)
    fundamentals = insider = None
    if getattr(cfg.features, "use_fundamentals", False):
        from v12.data.fundamentals import load_fundamentals
        fundamentals = load_fundamentals(cfg.data.universe, cfg.data.cache_dir,
                                          cfg.data.sec_user_agent or None)
    if getattr(cfg.features, "use_insider", False):
        from v12.data.insider import load_insider
        insider = load_insider(cfg.data.universe, cfg.data.cache_dir,
                               cfg.data.sec_user_agent or None,
                               start_year=int(cfg.data.start[:4]), end_year=int(cfg.data.end[:4]))
    panel, feature_cols = build_dataset(data, cfg.features, cfg.data, fundamentals, insider)

    fams = factor_families(feature_cols)
    base_cols = [c for f in BASELINE_FAMILIES for c in fams.get(f, [])]
    cand_cols = fams.get(cand_family, [])
    if not base_cols:
        log.error("No baseline features present — cannot validate.")
        sys.exit(2)
    if not cand_cols:
        print(f"\n=== SOURCE GATE: {label} ===\nVERDICT: NO_FEATURES — the '{cand_family}' "
              f"family produced 0 features. Build/enable the connector first.\n")
        sys.exit(2)

    full_cols = base_cols + cand_cols
    wf = PurgedWalkForward(cfg.validation.n_splits, cfg.validation.train_min_days,
                           cfg.validation.test_days, cfg.validation.embargo_days,
                           cfg.features.target_horizon)
    folds = list(wf.split(panel[full_cols + ["target"]]))
    assert_no_leakage(panel, full_cols, iter(folds), cfg.features.target_horizon)

    log.info("Baseline %d feats vs +%s %d feats over %d folds...",
             len(base_cols), cand_family, len(cand_cols), len(folds))
    _, base_folds, _ = _walk_forward_predict(panel, base_cols, folds, args.model, cfg.models)
    _, full_folds, _ = _walk_forward_predict(panel, full_cols, folds, args.model, cfg.models)

    base_sig = ic_significance(base_folds)
    full_sig = ic_significance(full_folds)
    v = source_verdict(base_folds, full_folds, args.min_gain, args.t_threshold)

    L = [f"# Source Validation Gate — `{label}`",
         f"_model: {args.model} · {v['n_folds']} folds · horizon {args.horizon}d · "
         f"baseline {len(base_cols)} feats + candidate {len(cand_cols)} feats · data {data.source}_", "",
         f"- Baseline OOS IC: **{_fmt(base_sig['mean'])}** (t={base_sig['t_stat']:.2f})",
         f"- Baseline + {label} OOS IC: **{_fmt(full_sig['mean'])}** (t={full_sig['t_stat']:.2f})",
         f"- Mean per-fold IC gain: **{_fmt(v['mean_gain'])}** · paired t = **{v['t_stat']:.2f}** "
         f"(need gain > {args.min_gain} and t > {args.t_threshold})",
         "",
         f"## VERDICT: **{v['verdict']}**  ({'give it weight' if v['passed'] else 'do NOT add weight / do NOT pay'})",
         "",
         "_Same purged/embargoed walk-forward as the validated engine. A source that "
         "cannot beat this gate gets zero weight — no exceptions, including paid feeds._"]
    report = "\n".join(L) + "\n"
    os.makedirs(cfg.output_dir, exist_ok=True)
    path = os.path.join(cfg.output_dir, f"validate_{label}.md")
    open(path, "w").write(report)
    print("\n" + report)
    log.info("Gate report -> %s", path)
    sys.exit(0 if v["passed"] else 2)


if __name__ == "__main__":
    main()
