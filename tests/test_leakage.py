"""Tests for the anti-leakage machinery — the most important guarantees in V12."""
import os
import sys

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from v12.validation import PurgedWalkForward, assert_no_leakage


def _toy_panel(n_dates=400, n_tickers=5, horizon=5, seed=0):
    rng = np.random.default_rng(seed)
    dates = pd.bdate_range("2020-01-01", periods=n_dates)
    tickers = [f"T{i}" for i in range(n_tickers)]
    idx = pd.MultiIndex.from_product([dates, tickers], names=["date", "ticker"])
    df = pd.DataFrame({
        "f1": rng.normal(size=len(idx)),
        "f2": rng.normal(size=len(idx)),
        "target": rng.normal(size=len(idx)),
    }, index=idx)
    return df, ["f1", "f2"], horizon


def test_train_test_disjoint_and_purged():
    panel, feats, h = _toy_panel()
    wf = PurgedWalkForward(n_splits=4, train_min_days=100, test_days=40,
                           embargo_days=h, horizon=h)
    folds = list(wf.split(panel))
    assert len(folds) > 0
    dates = panel.index.get_level_values("date")
    for tr, te, info in folds:
        assert not (set(tr) & set(te)), "train/test overlap"
        # purge gap: max train date strictly before min test date
        assert dates[tr].max() < dates[te].min()


def test_assert_no_leakage_passes_on_clean_panel():
    panel, feats, h = _toy_panel()
    wf = PurgedWalkForward(4, 100, 40, h, h)
    assert assert_no_leakage(panel, feats, wf.split(panel), h) is True


def test_assert_no_leakage_catches_contaminated_feature():
    panel, feats, h = _toy_panel()
    panel["leaky"] = panel["target"]  # blatant leak
    feats = feats + ["leaky"]
    wf = PurgedWalkForward(4, 100, 40, h, h)
    with pytest.raises(AssertionError):
        assert_no_leakage(panel, feats, wf.split(panel), h)


def test_embargo_enforced_at_least_horizon():
    from v12.config import ExperimentConfig
    cfg = ExperimentConfig()
    cfg.features.target_horizon = 10
    cfg.validation.embargo_days = 2
    cfg.__post_init__()
    assert cfg.validation.embargo_days >= cfg.features.target_horizon
