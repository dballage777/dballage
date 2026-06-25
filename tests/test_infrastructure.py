"""Multi-sleeve manager + shadow ledger (parallel paper horse-race substrate)."""
import os
import sys
import tempfile

import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from v12.portfolio.sleeves import Sleeve, SleeveManager
from v12.execution.ledger import ShadowLedger


def test_shadow_sleeves_excluded_from_live_portfolio():
    m = SleeveManager()
    m.register(Sleeve("equity_lowvol", status="live", allocation=1.0))
    m.register(Sleeve("crypto_full", asset_class="crypto", status="shadow"))
    combined = m.combine({
        "equity_lowvol": pd.Series({"AAPL": 0.05, "MSFT": 0.03}),
        "crypto_full": pd.Series({"BTC": 0.20}),
    })
    assert "BTC" not in combined.index          # shadow not in live portfolio
    assert "AAPL" in combined.index


def test_asset_class_cap_enforced():
    m = SleeveManager()
    s = Sleeve("eq", status="live", allocation=1.0, max_class_weight=0.70)
    m.register(s)
    # sleeve wants 100% exposure -> capped at 70%
    combined = m.combine({"eq": pd.Series({f"T{i}": 0.10 for i in range(10)})})
    assert combined.sum() <= 0.70 + 1e-9


def test_promote_shadow_to_live():
    m = SleeveManager()
    m.register(Sleeve("crypto", asset_class="crypto", status="shadow"))
    assert not m.live_sleeves()
    m.promote("crypto")
    assert m.live_sleeves()[0].name == "crypto"


def test_ledger_logs_and_tracks_performance():
    with tempfile.TemporaryDirectory() as d:
        led = ShadowLedger(os.path.join(d, "ledger.jsonl"))
        decisions = [{"asset": "AAPL", "action": "BUY", "target_weight": 0.05}]
        for i, r in enumerate([0.01, -0.005, 0.02]):
            led.log(f"2026-01-0{i+1}", "equity_lowvol", "shadow", decisions, day_return=r)
        perf = led.rolling_performance("equity_lowvol")
        assert perf["n_days"] == 3
        assert abs(perf["cum_return"] - ((1.01 * 0.995 * 1.02) - 1)) < 1e-9
        assert perf["win_rate"] > 0
