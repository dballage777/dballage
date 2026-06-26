"""Standings + rollup aggregation from the shadow ledger."""
import pandas as pd

from v12.reporting.standings import standings, period_rollup, render_standings


def _df(rows):
    return pd.DataFrame(rows)


def test_standings_basic():
    rows = [
        {"date": "2026-06-19", "sleeve": "equity_validated", "n_positions": 0,
         "day_return": None, "decisions": []},
        {"date": "2026-06-22", "sleeve": "equity_validated", "n_positions": 2,
         "day_return": 0.01, "decisions": [{"asset": "AAA", "target_weight": 0.05}]},
        {"date": "2026-06-23", "sleeve": "equity_validated", "n_positions": 2,
         "day_return": -0.02, "decisions": [{"asset": "AAA", "target_weight": 0.05}]},
    ]
    st = standings(_df(rows))
    r = st["equity_validated"]
    assert r["n_days"] == 2                       # only the 2 non-null day_returns
    # cum = (1.01)(0.98)-1
    assert abs(r["cum_return"] - ((1.01 * 0.98) - 1)) < 1e-9
    assert abs(r["best_day"] - 0.01) < 1e-9 and abs(r["worst_day"] - (-0.02)) < 1e-9
    assert r["last_exposure"] == 0.05


def test_standings_empty():
    assert standings(_df([])) == {}
    md = render_standings(_df([]))
    assert "No realized returns yet" in md


def test_period_rollup_weekly():
    rows = [
        {"date": "2026-06-22", "sleeve": "s1", "day_return": 0.01, "decisions": []},
        {"date": "2026-06-23", "sleeve": "s1", "day_return": 0.02, "decisions": []},
        {"date": "2026-06-29", "sleeve": "s1", "day_return": -0.01, "decisions": []},
    ]
    w = period_rollup(_df(rows), "W")
    assert not w.empty
    # two distinct ISO weeks
    assert len(w) == 2


def test_render_has_sections_with_data():
    rows = [
        {"date": "2026-06-22", "sleeve": "full_system", "n_positions": 3,
         "day_return": 0.01, "decisions": [{"asset": "X", "target_weight": 0.1}]},
        {"date": "2026-06-23", "sleeve": "full_system", "n_positions": 3,
         "day_return": 0.005, "decisions": [{"asset": "X", "target_weight": 0.1}]},
    ]
    md = render_standings(_df(rows))
    assert "Standings" in md and "Weekly cumulative return" in md
