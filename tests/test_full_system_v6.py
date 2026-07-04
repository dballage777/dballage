"""Variant 6 — metals sleeve + full_system_v6 revised-caps invariants."""
import pytest

import v12.data.loader as loader
from v12.strategies import build_full_system_v6, build_metals_sleeve
from v12.strategies.metals_sleeve import METALS_CLASS_CAP, METALS_POSITION_CAP
from v12.strategies.full_system_v6 import STOCK_CAP_V6, METALS_CAP_V6, CRYPTO_CAP_V6

STOCKS = ["AAPL", "MSFT", "NVDA", "JPM", "XOM", "JNJ", "PG", "KO"]
CRYPTO = ["BTC-USD", "ETH-USD", "SOL-USD", "XRP-USD", "ADA-USD", "DOGE-USD"]
METALS = ["GLD", "SLV", "PPLT", "PALL"]
EPS = 1e-6


@pytest.fixture(scope="module")
def _force_synthetic():
    orig = loader._download_yf
    loader._download_yf = lambda *a, **k: None
    yield
    loader._download_yf = orig


@pytest.fixture(scope="module")
def metals(_force_synthetic):
    return build_metals_sleeve(end="2024-12-31", universe=METALS)


@pytest.fixture(scope="module")
def v6(_force_synthetic):
    return build_full_system_v6(end="2024-12-31", stock_universe=STOCKS,
                                crypto_universe=CRYPTO, metals_universe=METALS)


def test_metals_position_cap(metals):
    for a, w in metals.targets.items():
        assert w <= METALS_POSITION_CAP + EPS


def test_metals_class_cap(metals):
    assert metals.metals_exposure <= METALS_CLASS_CAP + EPS


def test_v6_revised_caps(v6):
    assert v6.stock_exposure <= STOCK_CAP_V6 + EPS
    assert v6.metals_exposure <= METALS_CAP_V6 + EPS
    assert v6.crypto_exposure <= CRYPTO_CAP_V6 + EPS
    assert v6.total_exposure <= 1.0 + EPS
    # capital structure sums to 1 with cash as the residual
    assert abs(v6.stock_exposure + v6.metals_exposure + v6.crypto_exposure + v6.cash - 1.0) < 1e-6


def test_v6_has_three_books(v6):
    assert v6.stock is not None and v6.crypto is not None and v6.metals is not None
    # metals assets are correctly attributed (not counted as stocks)
    for a in v6.combined_targets:
        if a in v6.metals_set:
            assert not a.endswith("-USD")


def test_v6_cold_start_no_tilt(v6):
    if not v6.learning_active:
        assert all(abs(m - 1.0) < EPS for m in v6.multipliers.values())
