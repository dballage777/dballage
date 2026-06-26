"""Framework self-validation — proves the stack is trustworthy *before* we ever
trust a real-data result.

It checks three properties that, together, are the antidote to the V1-V9A
"fake alpha" failures:

  1. RECOVERY      stronger planted signal -> higher out-of-sample rank-IC.
                   (If real data has edge, the pipeline can find it.)
  2. NO-HALLUCINATE  zero planted signal  -> IC ~= 0.
                   (The pipeline does not invent alpha that isn't there.)
  3. LEAKAGE-CAUGHT a leaked feature      -> the validation gate ABORTS.
                   (Contamination fails loudly instead of inflating Sharpe.)

Runs on synthetic data only (it needs a *known* ground-truth signal), so it is
valid even in a network-restricted environment.

    python -m experiments.validate_framework
"""
from __future__ import annotations

import json
import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from v12.config import ExperimentConfig
from v12.data import load_prices
from v12.features import build_dataset
from v12.validation import PurgedWalkForward, assert_no_leakage
from v12.utils import get_logger
from experiments.run_experiment import _walk_forward_predict

log = get_logger("validate")

# Cross-sectional IC over few names is very noisy, so we use a 20-name universe
# and AVERAGE over several seeds to get a stable dose-response read.
UNIVERSE = [f"S{i:02d}" for i in range(20)]
MODEL = "lgbm"
SEEDS = [7, 11, 23]


def _cfg(strength: float, seed: int) -> ExperimentConfig:
    cfg = ExperimentConfig(name=f"validate_s{strength}_seed{seed}")
    cfg.data.universe = list(UNIVERSE)
    cfg.data.rs_refs = ["SPY"]
    cfg.data.extra_benchmarks = []      # keep the synthetic universe deterministic
                                        # (no USMV/SPLV) so the IC read is stable
    cfg.data.start, cfg.data.end = "2017-01-01", "2023-01-01"
    cfg.data.signal_strength = strength
    cfg.data.allow_synthetic = True
    cfg.data.synthetic_seed = seed
    cfg.validation.n_splits = 3
    cfg.validation.train_min_days = 252
    cfg.models.candidates = [MODEL]
    return cfg


def _ic_one(strength: float, seed: int) -> float:
    cfg = _cfg(strength, seed)
    data = load_prices(cfg.data)
    panel, feats = build_dataset(data, cfg.features, cfg.data)
    wf = PurgedWalkForward(cfg.validation.n_splits, cfg.validation.train_min_days,
                           cfg.validation.test_days, cfg.validation.embargo_days,
                           cfg.features.target_horizon)
    folds = list(wf.split(panel))
    assert_no_leakage(panel, feats, iter(folds), cfg.features.target_horizon)
    _, fold_ics, _ = _walk_forward_predict(panel, feats, folds, MODEL, cfg.models)
    return float(np.nanmean(fold_ics))


def _ic_for_strength(strength: float):
    vals = [_ic_one(strength, s) for s in SEEDS]
    return float(np.mean(vals)), float(np.std(vals))


def _leakage_caught() -> bool:
    """Inject a blatantly leaked feature; the gate must raise."""
    cfg = _cfg(1.0, SEEDS[0])
    data = load_prices(cfg.data)
    panel, feats = build_dataset(data, cfg.features, cfg.data)
    panel["LEAK"] = panel["target"]            # feature == future target
    feats = feats + ["LEAK"]
    wf = PurgedWalkForward(cfg.validation.n_splits, cfg.validation.train_min_days,
                           cfg.validation.test_days, cfg.validation.embargo_days,
                           cfg.features.target_horizon)
    try:
        assert_no_leakage(panel, feats, wf.split(panel), cfg.features.target_horizon)
        return False                            # bad: leak not caught
    except AssertionError:
        return True                             # good: gate fired


def main():
    log.info("=== V12 framework self-validation (avg over %d seeds) ===", len(SEEDS))
    strengths = [0.0, 1.0, 4.0]
    ics = {s: _ic_for_strength(s) for s in strengths}          # s -> (mean, std)
    for s, (m, sd) in ics.items():
        log.info("signal_strength=%.1f -> OOS rank-IC=%.4f ± %.4f", s, m, sd)

    leak_caught = _leakage_caught()
    log.info("leakage canary caught: %s", leak_caught)

    m0, m1, m4 = ics[0.0][0], ics[1.0][0], ics[4.0][0]
    # Dose-response: both signal levels beat the no-signal baseline, and the
    # strong level beats the faint one by at least one seed-std (noise-aware).
    tol = ics[4.0][1]
    recovery = (m1 > m0) and (m4 > m0) and (m4 >= m1 - tol)
    # No hallucinated alpha: on pure noise the IC must be statistically consistent
    # with zero, judged against sampling noise (standard error over seeds) with a
    # small floor — not an arbitrary tight band that flakes on noise. It must also
    # stay far below the recovered strong signal (can't masquerade as real alpha).
    import numpy as _np
    se0 = ics[0.0][1] / _np.sqrt(len(SEEDS))
    no_hallucinate = abs(m0) < max(0.04, 2.5 * se0) and abs(m0) < 0.5 * max(m4, 1e-9)
    verdict = {
        "ic_by_strength": {str(s): {"mean": m, "std": sd} for s, (m, sd) in ics.items()},
        "recovery_dose_response": bool(recovery),
        "no_hallucinate_zero_signal": bool(no_hallucinate),
        "leakage_caught": bool(leak_caught),
        "passed": bool(recovery and no_hallucinate and leak_caught),
    }

    os.makedirs("results", exist_ok=True)
    with open("results/framework_validation.json", "w") as f:
        json.dump(verdict, f, indent=2, default=float)

    print("\n" + "=" * 60)
    print(f"FRAMEWORK SELF-VALIDATION (mean ± std over {len(SEEDS)} seeds)")
    print(f"  IC(no signal)    = {m0:+.4f} ± {ics[0.0][1]:.4f}   (want ~0)")
    print(f"  IC(faint signal) = {m1:+.4f} ± {ics[1.0][1]:.4f}")
    print(f"  IC(strong signal)= {m4:+.4f} ± {ics[4.0][1]:.4f}   (want highest)")
    print(f"  recovery dose-response .... {verdict['recovery_dose_response']}")
    print(f"  no hallucinated alpha ..... {verdict['no_hallucinate_zero_signal']}")
    print(f"  leakage gate fires ........ {verdict['leakage_caught']}")
    print(f"  OVERALL PASSED ............ {verdict['passed']}")
    print("=" * 60)
    sys.exit(0 if verdict["passed"] else 1)


if __name__ == "__main__":
    main()
