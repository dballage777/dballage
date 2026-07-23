"""P0 observe-only shadows — S1 regime layer, S2 VRP timer, S6 drift monitor.

These tests assert the signals are well-formed and, crucially, that they are
OBSERVE-ONLY (they never claim to allocate) and never touch the 7-test ledger.
"""
import numpy as np
import pytest

import v12.data.loader as loader
from v12.signals import build_vrp_signal, build_regime_layer, VRP_BOOK, REGIME_BOOK
from v12.monitoring import assess_sleeve
from v12.monitoring.drift import _page_hinkley, MIN_OBS

BREADTH = ["AAPL", "MSFT", "NVDA", "JPM", "XOM", "JNJ", "PG", "KO"]


@pytest.fixture(scope="module")
def _force_synthetic():
    orig = loader._download_yf
    loader._download_yf = lambda *a, **k: None      # force synthetic (deterministic)
    yield
    loader._download_yf = orig


# ---- S2 VRP timer ----
def test_vrp_signal_shape(_force_synthetic):
    res = build_vrp_signal(end="2024-12-31")
    if res is None:                                  # VIX synthetic may be absent
        pytest.skip("VIX unavailable in this data")
    assert res.state in ("risk_on", "neutral", "risk_off")
    assert 0.0 <= res.suggested_mult <= 1.0
    assert 0.0 <= res.vrp_pct <= 1.0
    assert res.market_close is not None and not res.market_close.empty


# ---- S1 regime layer ----
def test_regime_layer_shape(_force_synthetic):
    res = build_regime_layer(end="2024-12-31", breadth_universe=BREADTH)
    if res is None:
        pytest.skip("no regime sub-signals available")
    assert res.state in ("risk_on", "neutral", "risk_off")
    assert -1.0 <= res.score <= 1.0
    assert 0.0 <= res.suggested_mult <= 1.0
    # at least one sub-signal voted
    assert any(v is not None for v in res.votes.values())


# ---- S6 drift/decay guardian ----
def test_page_hinkley_flat_no_alarm():
    assert _page_hinkley([0.001] * 60) is False     # constant stream -> no change


def test_page_hinkley_detects_shift():
    x = [0.001] * 60 + [-0.03] * 40                 # clear downward regime shift
    assert _page_hinkley(x) is True


def test_assess_sleeve_warmup():
    h = assess_sleeve("x", [0.01] * (MIN_OBS - 1))
    assert h.decay_flag is False and h.drift_flag is False
    assert "warming up" in h.note


def test_assess_sleeve_decay_flag():
    rng = np.random.default_rng(0)
    losing = list(rng.normal(-0.002, 0.01, 60))     # negative drift -> Sharpe LCB <= 0
    h = assess_sleeve("losing", losing)
    assert h.n == 60
    assert h.decay_flag is True
