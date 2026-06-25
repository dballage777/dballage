"""Hard risk governor: kill-switch, loss-stop, loss-freeze, point-in-time."""
import os
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from v12.risk.governor import RiskGovernor
from v12.config import ExperimentConfig
from v12.backtest import run_backtest


def test_drawdown_killswitch_flattens_to_cash():
    g = RiskGovernor(max_drawdown=0.20, daily_loss_stop=0.99, max_consec_losses=99)
    # drip down ~25% over many small days
    for _ in range(30):
        assert g.exposure() in (0.0, 1.0)
        g.update(-0.01)
    assert g.killed is True
    assert g.exposure() == 0.0  # in cash after breaching -20%


def test_killswitch_reenters_after_recovery():
    g = RiskGovernor(max_drawdown=0.20, reenter_drawdown=0.10, daily_loss_stop=0.99)
    for _ in range(30):
        g.update(-0.01)          # breach
    assert g.killed
    for _ in range(30):
        g.update(+0.02)          # recover
    assert g.killed is False
    assert g.exposure() == 1.0


def test_daily_loss_stop_triggers_cooldown():
    g = RiskGovernor(daily_loss_stop=0.04, cooldown_days=5, max_drawdown=0.99)
    g.update(-0.05)              # worse than -4%
    assert g.exposure() == 0.0  # cooled down
    for _ in range(5):
        g.update(0.0)
    assert g.exposure() == 1.0  # cooldown elapsed


def test_consecutive_loss_freeze():
    g = RiskGovernor(max_consec_losses=3, cooldown_days=5,
                     daily_loss_stop=0.99, max_drawdown=0.99)
    g.update(-0.001); g.update(-0.001); g.update(-0.001)  # 3 down days
    assert g.exposure() == 0.0


def test_governor_reduces_drawdown_in_backtest():
    rng = np.random.default_rng(3)
    dates = pd.bdate_range("2020-01-01", periods=400)
    names = [f"N{i}" for i in range(8)]
    # inject a sharp crash mid-sample
    rets = rng.normal(0.0003, 0.01, (400, 8))
    rets[150:170] = -0.03
    close = pd.DataFrame(100 * np.exp(np.cumsum(rets, 0)), index=dates, columns=names)
    bench = pd.Series(close.mean(axis=1))
    idx = pd.MultiIndex.from_product([dates, names], names=["date", "ticker"])
    pred = pd.Series(rng.normal(size=len(idx)), index=idx)

    base = ExperimentConfig().backtest
    base.rebalance_days = 10; base.use_kelly = False; base.vol_target_annual = None
    r_off = run_backtest(pred, close, bench, base)

    guarded = ExperimentConfig().backtest
    guarded.rebalance_days = 10; guarded.use_kelly = False; guarded.vol_target_annual = None
    guarded.hard_risk = True; guarded.max_drawdown_stop = 0.15
    r_on = run_backtest(pred, close, bench, guarded)

    dd_off = (r_off.strategy_nav / r_off.strategy_nav.cummax() - 1).min()
    dd_on = (r_on.strategy_nav / r_on.strategy_nav.cummax() - 1).min()
    assert dd_on >= dd_off  # governor must not deepen drawdown
