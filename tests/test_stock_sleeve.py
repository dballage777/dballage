"""Variant 2 — full GOAL stock sleeve: structural / invariant tests.

These don't assert alpha (synthetic data has none worth trusting); they assert
that every GOAL governance invariant holds on the assembled pipeline:
per-position cap, asset-class cap, valid regime, bounded exposures, and the
GOAL-required per-decision output schema.
"""
import os

import pandas as pd
import pytest

import v12.data.loader as loader
from v12.strategies import build_stock_sleeve, SLEEVE_NAME
from v12.strategies.stock_sleeve import (
    STOCK_POSITION_CAP, STOCK_CLASS_CAP, REGIME6_EXPOSURE,
)

SMALL = ["AAPL", "MSFT", "NVDA", "JPM", "XOM", "JNJ", "PG", "KO"]
EPS = 1e-6


@pytest.fixture(scope="module")
def sleeve(tmp_path_factory, _force_synthetic):
    log_path = str(tmp_path_factory.mktemp("ledger") / "shadow.jsonl")
    return build_stock_sleeve(end="2024-12-31", universe=SMALL, log_path=log_path), log_path


@pytest.fixture(scope="module")
def _force_synthetic():
    """Force the synthetic data path so the test is offline + deterministic."""
    orig = loader._download_yf
    loader._download_yf = lambda *a, **k: None
    yield
    loader._download_yf = orig


def test_position_cap(sleeve):
    res, _ = sleeve
    for asset, w in res.targets.items():
        assert w <= STOCK_POSITION_CAP + EPS, f"{asset} {w} exceeds position cap"


def test_class_cap(sleeve):
    res, _ = sleeve
    assert res.stock_exposure <= STOCK_CLASS_CAP + EPS


def test_exposures_bounded(sleeve):
    res, _ = sleeve
    assert 0.0 <= res.regime_exposure <= 1.0
    assert 0.0 <= res.kelly_mult <= 1.0
    assert 0.0 <= res.governor_exposure <= 1.0


def test_regime_valid(sleeve):
    res, _ = sleeve
    assert res.regime in REGIME6_EXPOSURE


def test_required_output_schema(sleeve):
    """GOAL: every decision must carry the full required output."""
    res, _ = sleeve
    assert res.decisions, "expected at least one decision"
    allowed = {"BUY", "HOLD", "SELL", "NO TRADE", "REDUCE"}
    for d in res.decisions:
        assert d.asset
        assert d.action in allowed
        assert isinstance(d.ev_score, float)
        assert d.risk_status in {"LOW", "MEDIUM", "HIGH"}
        assert 0.0 <= d.confidence <= 100.0
        assert d.target_weight >= 0.0
        assert d.reasoning and d.sources


def test_crisis_regime_forces_cash(sleeve):
    """If the regime weight is 0 (crisis), exposure must collapse to cash."""
    res, _ = sleeve
    if res.regime_exposure == 0.0:
        assert res.stock_exposure == 0.0


def test_shadow_ledger_written(sleeve):
    res, log_path = sleeve
    assert os.path.exists(log_path)
    rows = [l for l in open(log_path) if l.strip()]
    assert rows, "shadow ledger should have at least one row"
    import json
    rec = json.loads(rows[-1])
    assert rec["sleeve"] == SLEEVE_NAME
    assert rec["status"] == "shadow"     # never live capital
