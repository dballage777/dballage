"""Factor-analytics engine sanity checks."""
import os
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from v12.evaluation.factor_analytics import (factor_families, ic_significance,
                                             redundancy, ic_by_year, select_features)


def test_select_features_keeps_families_and_prunes_redundancy():
    idx = pd.MultiIndex.from_product([pd.bdate_range("2021-01-01", periods=40), ["A", "B"]],
                                     names=["date", "ticker"])
    rng = np.random.RandomState(0)
    x = rng.normal(size=len(idx))
    panel = pd.DataFrame({
        "realized_vol_20": x,
        "atr_pct": x + rng.normal(0, 0.001, len(idx)),  # ~identical to realized_vol_20
        "csrank_vol": rng.normal(size=len(idx)),
        "mom_5": rng.normal(size=len(idx)),             # different family -> dropped
    }, index=idx)
    cols = ["realized_vol_20", "atr_pct", "csrank_vol", "mom_5"]
    # keep only volatility + cross_sectional
    kept = select_features(panel, cols, keep_families=["volatility", "cross_sectional"])
    assert "mom_5" not in kept and "csrank_vol" in kept
    # prune the near-duplicate volatility feature
    kept2 = select_features(panel, cols, keep_families=["volatility"], prune_corr=0.95)
    assert len(kept2) == 1  # one of the two collinear vols dropped


def test_factor_families_grouping():
    cols = ["mom_5", "mom_120", "adx", "rs_SPY", "beta_SPY", "f_roe",
            "i_insider_buy_count_90d", "csrank_vol", "realized_vol_20", "breadth_pct_above_50"]
    fams = factor_families(cols)
    assert fams["momentum"] == ["mom_5", "mom_120"]
    assert "f_roe" in fams["fundamental"]
    assert "i_insider_buy_count_90d" in fams["insider"]
    assert "rs_SPY" in fams["relative_strength"] and "beta_SPY" in fams["relative_strength"]
    assert "realized_vol_20" in fams["volatility"]


def test_significance_strong_vs_noise():
    strong = [0.05, 0.04, 0.06, 0.05, 0.045, 0.055]  # consistent positive
    noise = [0.05, -0.06, 0.02, -0.04, 0.07, -0.05]  # mean ~0, high var
    assert ic_significance(strong)["t_stat"] > 3
    assert abs(ic_significance(noise)["t_stat"]) < 1.5


def test_redundancy_flags_correlated_pair():
    idx = pd.MultiIndex.from_product([pd.bdate_range("2021-01-01", periods=50), ["A", "B"]],
                                     names=["date", "ticker"])
    rng = np.random.RandomState(0)
    x = rng.normal(size=len(idx))
    panel = pd.DataFrame({"a": x, "b": x + rng.normal(0, 0.01, len(idx)),  # ~identical
                          "c": rng.normal(size=len(idx))}, index=idx)
    pairs = redundancy(panel, ["a", "b", "c"], 0.7)
    assert any({p[0], p[1]} == {"a", "b"} for p in pairs)
    assert not any("c" in (p[0], p[1]) for p in pairs)


def test_ic_by_year_runs():
    idx = pd.MultiIndex.from_product(
        [pd.bdate_range("2020-01-01", "2021-12-31", freq="W"), ["A", "B", "C"]],
        names=["date", "ticker"])
    rng = np.random.RandomState(1)
    pred = pd.Series(rng.normal(size=len(idx)), index=idx)
    tgt = pd.Series(rng.normal(size=len(idx)), index=idx)
    out = ic_by_year(pred, tgt)
    assert set(out.keys()) == {2020, 2021}
