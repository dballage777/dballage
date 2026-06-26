"""Scoring + reporting: schema and honesty invariants."""
import numpy as np
import pandas as pd

from v12.reporting import score_assets, build_daily_report, top_n, FACTOR_WEIGHTS, FACTOR_STATUS


def _synth_close(n=300, tickers=("AAA", "BBB", "CCC", "DDD")):
    idx = pd.bdate_range("2020-01-01", periods=n)
    rng = np.random.default_rng(0)
    data = {t: 100 * np.exp(np.cumsum(rng.normal(0.0003, 0.01, n))) for t in tickers}
    return pd.DataFrame(data, index=idx)


def test_composite_bounded_and_sorted():
    close = _synth_close()
    vol = close * 0 + 1e6
    s = score_assets(close, vol, model_ev={"AAA": 0.2, "BBB": -0.1})
    assert "composite" in s.columns
    assert (s["composite"] >= 0).all() and (s["composite"] <= 100).all()
    # returned sorted descending by composite
    assert list(s["composite"]) == sorted(s["composite"], reverse=True)


def test_only_live_factors_have_weight():
    # every non-live factor must carry weight 0 (cannot inflate a score)
    for f, w in FACTOR_WEIGHTS.items():
        if FACTOR_STATUS[f] != "live":
            assert w == 0.0, f"{f} is {FACTOR_STATUS[f]} but has weight {w}"
    # live factor weights are positive and sum to 1
    live = [w for f, w in FACTOR_WEIGHTS.items() if FACTOR_STATUS[f] == "live"]
    assert all(w > 0 for w in live)
    assert abs(sum(live) - 1.0) < 1e-9


def test_score_handles_missing_inputs():
    close = _synth_close()
    s = score_assets(close)             # no volume, no ev
    assert len(s) == close.shape[1]
    assert s["composite"].between(0, 100).all()


def test_short_history_is_neutral():
    close = _synth_close(n=10)
    s = score_assets(close)
    assert (s["composite"] == 50.0).all()


class _D:
    def __init__(self, asset, action, ev, risk, conf, reason="r", src="price"):
        self.asset, self.action, self.ev_score = asset, action, ev
        self.risk_status, self.confidence, self.reasoning, self.sources = risk, conf, reason, src


def test_top_n_required_fields():
    close = _synth_close()
    scores = score_assets(close, model_ev={"AAA": 0.3, "BBB": 0.1})
    decs = [_D("AAA", "BUY", 0.3, "LOW", 90), _D("BBB", "NO TRADE", -0.01, "MEDIUM", 40)]
    rows = top_n(scores, decs, targets={"AAA": 0.05}, last_price=close.iloc[-1], n=4)
    req = {"asset", "score", "action", "ev", "risk", "confidence",
           "position_size", "entry_range", "exit_criteria", "reasoning", "sources"}
    assert rows and req.issubset(rows[0].keys())
    # the held name is BUY; ranking is by score desc
    assert [r["score"] for r in rows] == sorted([r["score"] for r in rows], reverse=True)


def test_report_has_mandated_sections():
    close = _synth_close()
    scores = score_assets(close, model_ev={"AAA": 0.3})
    decs = [_D("AAA", "BUY", 0.3, "LOW", 90)]
    md = build_daily_report(
        date=close.index[-1], stock_regime="bull", crypto_regime="bear",
        allocation={"stocks": 0.2, "crypto": 0.1, "cash": 0.7},
        scores=scores, decisions=decs, targets={"AAA": 0.05},
        last_price=close.iloc[-1], crypto_set=set(), live_weight_fraction=0.35)
    for section in ["Market Regime", "Portfolio Allocation", "Top Signals",
                    "Top Risks", "Top 25 Opportunities", "Source coverage"]:
        assert section in md, f"missing section: {section}"
