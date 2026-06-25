"""The 6 feasible GOAL-gap closers + honest source stubs."""
import os
import sys

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from v12.portfolio.microcap import is_microcap, enforce_microcap_caps
from v12.portfolio.sleeves import Sleeve, SleeveManager
from v12.learning import reweight_sleeves
from v12.execution.cash_manager import CashManager
from v12.strategies import blend_horizons
from v12.sources import source_available, get_signal, SOURCE_STATUS
from v12.execution import DecisionEngine


# 1. correlation-overload check
def test_correlation_overload_halves_exposure():
    eng = DecisionEngine(top_quantile=0.5, max_weight=1.0)  # uncapped to expose the halving
    names = [f"T{i}" for i in range(6)]
    scores = pd.Series(np.linspace(0.05, 0.01, 6), index=names)
    dates = pd.bdate_range("2024-01-01", periods=80)
    # make the top-half names near-perfectly correlated
    base = np.random.RandomState(0).normal(size=80)
    rets = pd.DataFrame({n: (base + np.random.RandomState(i).normal(0, 0.001, 80)
                             if i < 3 else np.random.RandomState(i).normal(size=80))
                         for i, n in enumerate(names)}, index=dates)
    d_no = eng.decide(scores, regime_risk_on=True, governor_exposure=1.0)
    d_corr = eng.decide(scores, regime_risk_on=True, governor_exposure=1.0,
                        recent_returns=rets, corr_threshold=0.8)
    max_no = max(x.target_weight for x in d_no)
    max_corr = max(x.target_weight for x in d_corr)
    assert max_corr < max_no                     # exposure cut under correlation overload


# 2. multi-horizon blend
def test_blend_horizons_combines_ranks():
    idx = [f"T{i}" for i in range(5)]
    s60 = pd.Series([5, 4, 3, 2, 1], index=idx)
    s20 = pd.Series([1, 2, 3, 4, 5], index=idx)   # opposite ordering
    blended = blend_horizons({60: s60, 20: s20}, {60: 0.75, 20: 0.25})
    assert blended["T0"] > blended["T4"]          # long horizon dominates (0.75)


# 3. microcap caps
def test_microcap_caps_enforced():
    w = pd.Series({"BIG": 0.10, "TINY": 0.08})
    out = enforce_microcap_caps(w, microcap_set={"TINY"}, max_agg=0.10, max_pos=0.01)
    assert out["TINY"] <= 0.01 and out["BIG"] == 0.10
    assert not is_microcap("BIG") and is_microcap("TINY", microcap_set={"TINY"})


# 4. core/experimental split
def test_experimental_sleeve_capped_at_5pct():
    m = SleeveManager()
    m.register(Sleeve("core_eq", status="live", allocation=1.0, bucket="core"))
    m.register(Sleeve("exp", status="live", allocation=1.0, bucket="experimental"))
    combined = m.combine({
        "core_eq": pd.Series({"AAPL": 0.5}),
        "exp": pd.Series({"SPEC": 0.5}),          # wants 50% -> capped to 5%
    })
    assert combined.get("SPEC", 0) <= 0.05 + 1e-9


# 5. learning-loop reweight
def test_reweight_favours_better_sharpe():
    perf = {"a": {"sharpe": 1.5, "n_days": 60}, "b": {"sharpe": 0.2, "n_days": 60},
            "c": {"sharpe": -0.5, "n_days": 60}}
    w = reweight_sleeves(perf)
    assert w["a"] > w["b"] > w["c"]
    assert abs(sum(w.values()) - 1.0) < 1e-9
    assert w["c"] == 0.0                          # negative Sharpe -> no allocation


# 6. biweekly cash manager
def test_cash_held_until_ev_then_released():
    cm = CashManager(max_idle_days=90)
    cm.deposit(100)
    assert cm.step(ev_ok=False) == 0.0            # held (no EV)
    assert cm.step(ev_ok=True) == 100.0           # released on EV
    # 90-day idle backstop
    cm2 = CashManager(max_idle_days=3)
    cm2.deposit(50)
    for _ in range(3):
        cm2.step(ev_ok=False)
    assert cm2.step(ev_ok=False) == 50.0


# honest source stubs
def test_unavailable_sources_raise_not_silently_faked():
    assert source_available("price_volume")
    assert not source_available("news_reuters_bloomberg_wsj_ft")
    assert SOURCE_STATUS["sec_edgar_fundamentals"] == "shadow_only"
    with pytest.raises(NotImplementedError):
        get_signal("intraday")
    with pytest.raises(NotImplementedError):
        get_signal("reddit_hn_forums")
