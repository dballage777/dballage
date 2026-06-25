"""Variant 3 — full GOAL crypto sleeve: governance-invariant tests.

Mirror of test_stock_sleeve but for crypto-specific caps (30% class, 12%
position) and rules (BTC regime benchmark, no sector-neutral).
"""
import os

import pytest

import v12.data.loader as loader
from v12.strategies import build_crypto_sleeve
from v12.strategies.crypto_sleeve import (
    SLEEVE_NAME, CRYPTO_POSITION_CAP, CRYPTO_CLASS_CAP, REGIME6_EXPOSURE,
)

# small crypto set keeps the test fast; "-USD" tickers route through synthetic
SMALL = ["BTC-USD", "ETH-USD", "SOL-USD", "XRP-USD", "ADA-USD", "DOGE-USD"]
EPS = 1e-6


@pytest.fixture(scope="module")
def _force_synthetic():
    orig = loader._download_yf
    loader._download_yf = lambda *a, **k: None
    yield
    loader._download_yf = orig


@pytest.fixture(scope="module")
def sleeve(tmp_path_factory, _force_synthetic):
    log_path = str(tmp_path_factory.mktemp("ledger") / "shadow.jsonl")
    return build_crypto_sleeve(end="2024-12-31", universe=SMALL, log_path=log_path), log_path


def test_position_cap(sleeve):
    res, _ = sleeve
    for asset, w in res.targets.items():
        assert w <= CRYPTO_POSITION_CAP + EPS, f"{asset} {w} exceeds crypto position cap"


def test_class_cap(sleeve):
    res, _ = sleeve
    assert res.crypto_exposure <= CRYPTO_CLASS_CAP + EPS


def test_exposures_bounded(sleeve):
    res, _ = sleeve
    assert 0.0 <= res.regime_exposure <= 1.0
    assert 0.0 <= res.kelly_mult <= 1.0
    assert 0.0 <= res.governor_exposure <= 1.0


def test_regime_valid(sleeve):
    res, _ = sleeve
    assert res.regime in REGIME6_EXPOSURE


def test_required_output_schema(sleeve):
    res, _ = sleeve
    assert res.decisions
    allowed = {"BUY", "HOLD", "SELL", "NO TRADE", "REDUCE"}
    for d in res.decisions:
        assert d.asset
        assert d.action in allowed
        assert d.risk_status in {"LOW", "MEDIUM", "HIGH"}
        assert 0.0 <= d.confidence <= 100.0
        assert d.target_weight >= 0.0
        assert d.reasoning and d.sources


def test_crisis_regime_forces_cash(sleeve):
    res, _ = sleeve
    if res.regime_exposure == 0.0:
        assert res.crypto_exposure == 0.0


def test_shadow_ledger_written(sleeve):
    res, log_path = sleeve
    assert os.path.exists(log_path)
    import json
    rows = [l for l in open(log_path) if l.strip()]
    assert rows
    rec = json.loads(rows[-1])
    assert rec["sleeve"] == SLEEVE_NAME
    assert rec["status"] == "shadow"
