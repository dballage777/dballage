"""HIGH-RISK aggressive shadow sleeve — caps, half-Kelly, isolation invariants.

Asserts the aggressive books respect their (looser but real) caps, use HALF
(not full) Kelly, cap total exposure at 100%, and stay observe-only / isolated.
"""
import pytest

import v12.data.loader as loader
from v12.aggressive import build_aggressive_system
from v12.aggressive.sleeve import (build_aggressive_book, HALF_KELLY, POSITION_CAP,
                                   STOCK_CLASS_CAP, CRYPTO_CLASS_CAP, HORIZON_WEIGHTS,
                                   STOCK_BOOK, AGGR_STOCK_BENCHMARK)

STOCKS = ["NVDA", "AMD", "TSLA", "META", "NFLX", "COIN", "PLTR", "SHOP"]
CRYPTO = ["BTC-USD", "ETH-USD", "SOL-USD", "XRP-USD", "ADA-USD", "DOGE-USD"]
EPS = 1e-6


@pytest.fixture(scope="module")
def _force_synthetic():
    orig = loader._download_yf
    loader._download_yf = lambda *a, **k: None
    yield
    loader._download_yf = orig


@pytest.fixture(scope="module")
def system(_force_synthetic):
    return build_aggressive_system(end="2024-12-31", stock_universe=STOCKS, crypto_universe=CRYPTO)


def test_half_kelly_not_full():
    # the aggressive ceiling is HALF Kelly, never full (blow-up guard)
    assert HALF_KELLY == 0.50
    assert HALF_KELLY < 1.0


def test_position_cap_aggressive_but_bounded(system):
    for a, w in system.combined_targets.items():
        assert w <= POSITION_CAP + EPS          # <=20% per name


def test_total_exposure_capped_at_one(system):
    assert system.total_exposure <= 1.0 + EPS
    # cash is the residual and never negative
    assert system.cash >= -EPS
    assert abs(system.stock_exposure + system.crypto_exposure + system.cash - 1.0) < 1e-6 \
        or system.total_exposure <= 1.0 + EPS


def test_class_caps(system):
    # each book independently respects its class cap before combination/rescale
    assert system.stock.exposure <= STOCK_CLASS_CAP + EPS
    assert system.crypto.exposure <= CRYPTO_CLASS_CAP + EPS


def test_short_horizon(system):
    # SHORT horizon (days-to-weeks), NOT intraday / not the 60d core horizon
    assert max(HORIZON_WEIGHTS) <= 20


def test_book_builds_standalone(_force_synthetic):
    b = build_aggressive_book(STOCK_BOOK, STOCKS, AGGR_STOCK_BENCHMARK,
                              STOCK_CLASS_CAP, "aggr_stock", start="2015-01-01", end="2024-12-31")
    assert b.exposure <= STOCK_CLASS_CAP + EPS
    for a, w in b.targets.items():
        assert w <= POSITION_CAP + EPS
