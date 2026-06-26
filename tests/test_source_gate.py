"""Source-validation gate: the paired per-fold IC verdict logic."""
from v12.evaluation.factor_analytics import source_verdict


def test_clear_pass():
    # candidate improves every fold by ~0.02, consistently -> PASS
    base = [0.05, 0.04, 0.06, 0.05, 0.05]
    full = [0.07, 0.06, 0.08, 0.07, 0.07]
    v = source_verdict(base, full, min_gain=0.002, t_threshold=2.0)
    assert v["verdict"] == "PASS" and v["passed"]
    assert v["mean_gain"] > 0


def test_hurts():
    # candidate lowers IC consistently -> HURTS (the fundamentals/insider case)
    base = [0.05, 0.05, 0.05, 0.05, 0.05]
    full = [0.03, 0.03, 0.02, 0.03, 0.03]
    v = source_verdict(base, full)
    assert v["verdict"] == "HURTS" and not v["passed"]


def test_no_edge_when_noisy():
    # average gain ~0 with noise -> NO_EDGE (not significant)
    base = [0.05, 0.04, 0.06, 0.05, 0.05]
    full = [0.06, 0.03, 0.07, 0.04, 0.05]
    v = source_verdict(base, full)
    assert not v["passed"]
    assert v["verdict"] in ("NO_EDGE", "HURTS")


def test_tiny_consistent_gain_below_threshold_fails():
    # consistent but below min_gain -> NO_EDGE (not enough to matter)
    base = [0.0500, 0.0500, 0.0500, 0.0500, 0.0500]
    full = [0.0505, 0.0505, 0.0505, 0.0505, 0.0505]
    v = source_verdict(base, full, min_gain=0.002, t_threshold=2.0)
    assert not v["passed"]
    assert v["verdict"] == "NO_EDGE"


def test_insufficient_folds():
    v = source_verdict([0.05, 0.06], [0.07, 0.08])
    assert v["verdict"] == "INSUFFICIENT_FOLDS" and not v["passed"]


def test_nan_folds_dropped():
    base = [0.05, float("nan"), 0.06, 0.05, 0.05]
    full = [0.07, 0.06, 0.08, 0.07, 0.07]
    v = source_verdict(base, full)
    assert v["n_folds"] == 4   # the NaN-paired fold is dropped
