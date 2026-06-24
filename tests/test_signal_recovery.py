"""Fast signal-recovery guard (a compact version of experiments/validate_framework).

Asserts the two non-negotiable properties on synthetic data with a *known*
ground truth:
  * a strong, observable signal is recovered (OOS rank-IC clearly > 0);
  * zero signal yields ~zero IC (no hallucinated alpha).

Kept small (few names / short window / one seed) so it runs in CI quickly; the
full multi-seed dose-response lives in experiments/validate_framework.py.
"""
import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from v12.config import ExperimentConfig
from v12.data import load_prices
from v12.features import build_dataset
from v12.validation import PurgedWalkForward
from experiments.run_experiment import _walk_forward_predict


def _ic(strength, seed=5):
    cfg = ExperimentConfig()
    cfg.data.universe = [f"N{i:02d}" for i in range(12)]
    cfg.data.rs_refs = ["SPY"]
    cfg.data.start, cfg.data.end = "2018-01-01", "2022-01-01"
    cfg.data.signal_strength = strength
    cfg.data.synthetic_seed = seed
    cfg.data.allow_synthetic = True
    cfg.validation.n_splits = 2
    cfg.validation.train_min_days = 252
    cfg.models.candidates = ["lgbm"]
    data = load_prices(cfg.data)
    assert data.source == "synthetic", "test must use synthetic ground truth"
    panel, feats = build_dataset(data, cfg.features, cfg.data)
    wf = PurgedWalkForward(2, 252, cfg.validation.test_days,
                           cfg.validation.embargo_days, cfg.features.target_horizon)
    folds = list(wf.split(panel))
    _, fold_ics, _ = _walk_forward_predict(panel, feats, folds, "lgbm", cfg.models)
    return float(np.nanmean(fold_ics))


def test_strong_signal_is_recovered():
    ic = _ic(strength=10.0)
    assert ic > 0.05, f"strong planted signal not recovered (IC={ic:.4f})"


def test_zero_signal_is_not_hallucinated():
    ic = _ic(strength=0.0)
    assert abs(ic) < 0.08, f"alpha hallucinated on pure noise (IC={ic:.4f})"
