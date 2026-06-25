"""Regime classifier: correct labels + point-in-time (no look-ahead)."""
import os
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from v12.regime import classify_regime, regime_label


def _series(n=600, seed=0):
    rng = np.random.default_rng(seed)
    return pd.Series(100 * np.exp(np.cumsum(rng.normal(0.0003, 0.01, n))),
                     index=pd.bdate_range("2018-01-01", periods=n))


def test_regime_is_point_in_time():
    """Perturbing a FUTURE price must not change a PAST regime label."""
    c = _series()
    r1 = classify_regime(c)
    c2 = c.copy()
    c2.iloc[-1] *= 1.5
    r2 = classify_regime(c2)
    pd.testing.assert_frame_equal(r1.iloc[:-1], r2.iloc[:-1])


def test_bull_bear_trend_detected():
    # strong uptrend then crash -> bull early, bear after the crash
    up = np.linspace(100, 200, 300)
    down = np.linspace(200, 120, 60)
    c = pd.Series(np.concatenate([up, down]),
                  index=pd.bdate_range("2019-01-01", periods=360))
    r = classify_regime(c, trend_window=100)
    assert r["bull"].iloc[250] == 1.0      # in the uptrend
    assert r["bull"].iloc[-1] == 0.0       # after the crash, below SMA


def test_risk_on_requires_bull_and_not_stressed():
    c = _series()
    r = classify_regime(c)
    sub = r.dropna()
    # risk_on must imply bull and vol not top-tercile
    ron = sub[sub["risk_on"] == 1.0]
    assert (ron["bull"] == 1.0).all()
    assert (ron["vol_state"] < 2).all()


def test_regime_label_strings():
    row = pd.Series({"bull": 1.0, "vol_state": 2.0})
    assert regime_label(row) == "bull-stressed"
