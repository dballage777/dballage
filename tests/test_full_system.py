"""Variant 4 — full system: capital-structure + learning-loop invariants."""
import os

import pytest

import v12.data.loader as loader
from v12.strategies import build_full_system, SYSTEM_SLEEVE
from v12.strategies.stock_sleeve import STOCK_POSITION_CAP, STOCK_CLASS_CAP
from v12.strategies.crypto_sleeve import CRYPTO_POSITION_CAP, CRYPTO_CLASS_CAP

STOCKS = ["AAPL", "MSFT", "NVDA", "JPM", "XOM", "JNJ", "PG", "KO"]
CRYPTO = ["BTC-USD", "ETH-USD", "SOL-USD", "XRP-USD", "ADA-USD", "DOGE-USD"]
EPS = 1e-6


@pytest.fixture(scope="module")
def _force_synthetic():
    orig = loader._download_yf
    loader._download_yf = lambda *a, **k: None
    yield
    loader._download_yf = orig


@pytest.fixture(scope="module")
def system(tmp_path_factory, _force_synthetic):
    log_path = str(tmp_path_factory.mktemp("ledger") / "shadow.jsonl")
    res = build_full_system(end="2024-12-31", stock_universe=STOCKS,
                            crypto_universe=CRYPTO, log_path=log_path)
    return res, log_path


def test_capital_structure_caps(system):
    res, _ = system
    assert res.stock_exposure <= STOCK_CLASS_CAP + EPS
    assert res.crypto_exposure <= CRYPTO_CLASS_CAP + EPS
    assert res.total_exposure <= 1.0 + EPS
    assert res.cash >= 0.0
    # cash is the residual and the structure must sum to 1
    assert abs(res.stock_exposure + res.crypto_exposure + res.cash - 1.0) < 1e-6


def test_position_caps_per_book(system):
    res, _ = system
    for a, w in res.combined_targets.items():
        cap = CRYPTO_POSITION_CAP if a.endswith("-USD") else STOCK_POSITION_CAP
        assert w <= cap + EPS, f"{a} {w} exceeds {cap}"


def test_learning_multipliers_bounded(system):
    res, _ = system
    for n, m in res.multipliers.items():
        assert 0.0 <= m <= 1.0


def test_cold_start_no_tilt(system):
    """First run has no realized history -> learning inactive, both mult = 1.0."""
    res, _ = system
    if not res.learning_active:
        assert all(abs(m - 1.0) < EPS for m in res.multipliers.values())


def test_shadow_ledger_logs_system(system):
    res, log_path = system
    assert os.path.exists(log_path)
    import json
    sleeves = {json.loads(l)["sleeve"] for l in open(log_path) if l.strip()}
    assert SYSTEM_SLEEVE in sleeves
    # every logged row must be shadow (never live capital)
    statuses = {json.loads(l)["status"] for l in open(log_path) if l.strip()}
    assert statuses == {"shadow"}
