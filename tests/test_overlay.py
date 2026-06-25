"""Beta-overlay backtest mode: long-biased, tilted toward signal."""
import os
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from v12.config import ExperimentConfig
from v12.backtest import run_backtest


def _setup(seed=0):
    rng = np.random.default_rng(seed)
    dates = pd.bdate_range("2020-01-01", periods=300)
    names = [f"N{i}" for i in range(10)]
    close = pd.DataFrame(100 * np.exp(np.cumsum(rng.normal(0.0003, 0.01, (300, 10)), 0)),
                         index=dates, columns=names)
    bench = pd.Series(100 * np.exp(np.cumsum(rng.normal(0.0004, 0.009, 300))), index=dates)
    idx = pd.MultiIndex.from_product([dates, names], names=["date", "ticker"])
    pred = pd.Series(rng.normal(size=len(idx)), index=idx)
    return pred, close, bench


def test_overlay_is_long_biased_full_universe():
    pred, close, bench = _setup()
    cfg = ExperimentConfig().backtest
    cfg.portfolio_mode = "overlay"
    cfg.rebalance_days = 20
    cfg.use_kelly = False
    cfg.vol_target_annual = None
    r = run_backtest(pred, close, bench, cfg)
    w = r.weights_history.iloc[-1]
    held = w[w != 0]
    assert len(held) >= 8, "overlay should hold ~the whole universe"
    assert (held >= 0).all(), "overlay is long-only"
    assert abs(held.sum() - 1.0) < 1e-6, "overlay fully invested"


def test_neutral_mode_is_concentrated():
    pred, close, bench = _setup()
    cfg = ExperimentConfig().backtest
    cfg.portfolio_mode = "neutral"  # top-quantile
    cfg.rebalance_days = 20
    cfg.use_kelly = False
    cfg.vol_target_annual = None
    r = run_backtest(pred, close, bench, cfg)
    held = r.weights_history.iloc[-1]
    held = held[held != 0]
    # top 30% of 10 names -> ~3 positions, far fewer than the overlay's ~10
    assert len(held) <= 5
