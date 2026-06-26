"""Shadow horse-race: realized-return attribution + multi-sleeve logging."""
import pandas as pd

from experiments.run_all_shadow import _realized_return, _prev_rows


def test_realized_return_weighted():
    idx = pd.to_datetime(["2024-01-01", "2024-02-01", "2024-03-01"])
    close = pd.DataFrame({"AAA": [100, 110, 120], "BBB": [50, 45, 40]}, index=idx)
    # hold 50% AAA (+10%) and 25% BBB (-10%) from Jan 1 -> Feb 1
    r = _realized_return({"AAA": 0.5, "BBB": 0.25}, "2024-01-01",
                         pd.Timestamp("2024-02-01"), close)
    assert abs(r - (0.5 * 0.10 + 0.25 * -0.10)) < 1e-9


def test_realized_return_empty_or_future():
    idx = pd.to_datetime(["2024-01-01", "2024-02-01"])
    close = pd.DataFrame({"AAA": [100, 110]}, index=idx)
    assert _realized_return({}, "2024-01-01", pd.Timestamp("2024-02-01"), close) == 0.0
    # prev date not before today -> 0
    assert _realized_return({"AAA": 1.0}, "2024-02-01", pd.Timestamp("2024-02-01"), close) == 0.0


def test_realized_return_ignores_unknown_assets():
    idx = pd.to_datetime(["2024-01-01", "2024-02-01"])
    close = pd.DataFrame({"AAA": [100, 110]}, index=idx)
    # ZZZ not in price frame -> ignored; only AAA contributes
    r = _realized_return({"AAA": 0.5, "ZZZ": 0.5}, "2024-01-01",
                         pd.Timestamp("2024-02-01"), close)
    assert abs(r - 0.05) < 1e-9


def test_prev_rows_missing_file(tmp_path):
    assert _prev_rows(str(tmp_path / "nope.jsonl")) == {}


def test_prev_rows_parses_targets(tmp_path):
    import json
    p = tmp_path / "led.jsonl"
    rows = [
        {"date": "2024-01-01", "sleeve": "s1",
         "decisions": [{"asset": "AAA", "target_weight": 0.05},
                       {"asset": "BBB", "target_weight": 0.0}]},
        {"date": "2024-01-02", "sleeve": "s1",
         "decisions": [{"asset": "CCC", "target_weight": 0.03}]},
    ]
    p.write_text("\n".join(json.dumps(r) for r in rows) + "\n")
    prev = _prev_rows(str(p))
    # latest row per sleeve wins; only positive-weight targets kept
    assert prev["s1"][0] == "2024-01-02"
    assert prev["s1"][1] == {"CCC": 0.03}
