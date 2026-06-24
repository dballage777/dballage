"""Tests for feature correctness & point-in-time safety."""
import os
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from v12.config import DataConfig, FeatureConfig
from v12.data.loader import _synthetic, PriceData
from v12.features import build_dataset
from v12.features import technical as T


def _series(n=300, seed=1):
    rng = np.random.default_rng(seed)
    px = pd.Series(100 * np.exp(np.cumsum(rng.normal(0, 0.01, n))),
                   index=pd.bdate_range("2020-01-01", periods=n))
    return px


def test_momentum_is_pointwise():
    c = _series()
    mom = T.log_momentum(c, 20)
    # momentum at t must equal log(c[t]) - log(c[t-20]); no future info
    expected = np.log(c.iloc[40]) - np.log(c.iloc[20])
    assert abs(mom.iloc[40] - expected) < 1e-9


def test_features_have_no_lookahead():
    """Changing a FUTURE price must not change a PAST feature value."""
    c = _series()
    f1 = T.bollinger_z(c, 20)
    c2 = c.copy()
    c2.iloc[-1] *= 1.5  # perturb only the last point
    f2 = T.bollinger_z(c2, 20)
    # all but the final value must be identical
    pd.testing.assert_series_equal(f1.iloc[:-1], f2.iloc[:-1])


def test_yang_zhang_positive():
    rng = np.random.default_rng(2)
    n = 200
    close = pd.Series(100 * np.exp(np.cumsum(rng.normal(0, 0.01, n))),
                      index=pd.bdate_range("2020-01-01", periods=n))
    high = close * 1.01
    low = close * 0.99
    open_ = close.shift(1).fillna(close.iloc[0])
    yz = T.yang_zhang_vol(open_, high, low, close).dropna()
    assert (yz >= 0).all()


def test_build_dataset_runs_and_is_balanced():
    dcfg = DataConfig(universe=["A", "B", "C", "D"], rs_refs=["SPY"], benchmark="SPY",
                      start="2020-01-01", end="2022-06-01")
    fields = _synthetic(["A", "B", "C", "D", "SPY"], dcfg.start, dcfg.end, 3)
    data = PriceData(**fields, source="synthetic")
    panel, cols = build_dataset(data, FeatureConfig(), dcfg)
    assert len(panel) > 0
    assert "target" in panel.columns
    assert len(cols) > 20  # rich feature set
    assert not panel.isna().any().any()  # warmup rows dropped
