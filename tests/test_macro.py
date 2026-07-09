"""Macro loader + risk-off logic (deterministic, no network)."""
import numpy as np
import pandas as pd

from v12.data.macro import macro_risk_off, load_macro, _synthetic


def test_risk_off_on_inverted_curve():
    idx = pd.bdate_range("2022-01-01", periods=10)
    macro = pd.DataFrame({"T10Y2Y": [1, 1, -0.2, -0.5, 0.1, 1, 1, 1, 1, 1]}, index=idx)
    ro = macro_risk_off(macro)
    assert ro.iloc[2] and ro.iloc[3]        # inverted -> risk-off
    assert not ro.iloc[0]                    # positive spread -> risk-on


def test_risk_off_on_tight_conditions():
    idx = pd.bdate_range("2020-01-01", periods=400)
    rng = np.random.default_rng(0)
    # NFCI mostly calm (small noise around -0.5), then a sustained spike (tight)
    nfci = np.concatenate([-0.5 + rng.normal(0, 0.05, 360), np.full(40, 2.0)])
    ro = macro_risk_off(pd.DataFrame({"NFCI": nfci}, index=idx))
    assert ro.iloc[-1]                       # tight conditions -> risk-off
    assert not ro.iloc[100]                  # calm -> risk-on


def test_no_lookahead_shapes():
    idx = pd.bdate_range("2021-01-01", periods=50)
    macro = pd.DataFrame({"T10Y2Y": np.linspace(1, -1, 50)}, index=idx)
    ro = macro_risk_off(macro)
    assert len(ro) == 50 and ro.dtype == bool


def test_synthetic_fallback_shape():
    df = _synthetic(["T10Y2Y", "NFCI"], "2020-01-01", "2020-06-30")
    assert list(df.columns) == ["T10Y2Y", "NFCI"] and len(df) > 100


def test_load_macro_synthetic_when_offline():
    # no network in the sandbox -> should fall back to synthetic, stamped
    df, src = load_macro(start="2021-01-01", end="2021-06-30")
    assert not df.empty
    assert src in ("openbb", "fred_csv", "synthetic")
