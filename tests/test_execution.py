"""Decision engine governance + graduated sizing, and the paper-only guard."""
import os
import sys

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from v12.execution import DecisionEngine
from v12.execution.alpaca_adapter import AlpacaPaperAdapter


def _scores(n=10, seed=0):
    rng = np.random.default_rng(seed)
    return pd.Series(rng.normal(0.01, 0.02, n), index=[f"T{i}" for i in range(n)])


def test_governor_kill_forces_derisk():
    eng = DecisionEngine()
    d = eng.decide(_scores(), regime_risk_on=True, governor_exposure=0.0)
    assert all(x.target_weight == 0.0 for x in d)        # all cash
    assert all(x.action in ("NO TRADE", "SELL") for x in d)
    assert all(x.risk_status == "HIGH" for x in d)


def test_regime_risk_off_goes_to_cash():
    eng = DecisionEngine()
    d = eng.decide(_scores(), regime_risk_on=False, governor_exposure=1.0)
    assert all(x.target_weight == 0.0 for x in d)


def test_negative_ev_is_no_trade():
    eng = DecisionEngine(cost=0.05)  # cost above all signals -> EV<=0 everywhere
    d = eng.decide(_scores(), regime_risk_on=True, governor_exposure=1.0)
    assert all(x.ev_score <= 0 for x in d)
    assert all(x.action in ("NO TRADE", "SELL") for x in d)


def test_graduated_targets_and_caps():
    eng = DecisionEngine(max_weight=0.08, top_quantile=0.3)
    d = eng.decide(_scores(seed=1), regime_risk_on=True, governor_exposure=1.0)
    tgt = {x.asset: x.target_weight for x in d}
    assert all(0.0 <= w <= 0.08 + 1e-9 for w in tgt.values())   # capped
    assert any(w > 0 for w in tgt.values())                      # some BUYs
    # only a subset is held (top-quantile), not everything
    assert sum(w > 0 for w in tgt.values()) <= max(1, int(np.ceil(10 * 0.3)))


def test_required_output_fields_present():
    eng = DecisionEngine()
    d = eng.decide(_scores(), regime_risk_on=True, governor_exposure=1.0)[0]
    for f in ("asset", "action", "ev_score", "risk_status", "confidence",
              "target_weight", "reasoning", "sources"):
        assert hasattr(d, f)


def test_adapter_refuses_real_money_endpoint():
    with pytest.raises(ValueError):
        AlpacaPaperAdapter(base_url="https://api.alpaca.markets")  # live endpoint


def test_adapter_dry_run_logs_no_orders():
    a = AlpacaPaperAdapter(dry_run=True)
    recs = a.submit_target_weights({"AAPL": 0.05, "MSFT": 0.03}, equity=10000)
    assert all(r["mode"] == "DRY_RUN" for r in recs)
    assert recs[0]["notional"] == 500.0
