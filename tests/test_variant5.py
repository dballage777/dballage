"""Variant 5 (full_system_max): honest degradation of SEC data sources.

Offline (no SEC access), variant 5 must NOT claim to use fundamentals/insider —
it must record them as UNAVAILABLE and fall back to price/volume. Nothing faked.
"""
import pytest

import v12.data.loader as loader
from v12.strategies.stock_sleeve import build_stock_sleeve

SMALL = ["AAPL", "MSFT", "NVDA", "JPM", "XOM", "JNJ"]


@pytest.fixture(scope="module")
def _offline():
    orig = loader._download_yf
    loader._download_yf = lambda *a, **k: None      # force synthetic prices, no network
    yield
    loader._download_yf = orig


def test_fundamentals_unavailable_is_honest(_offline):
    r = build_stock_sleeve(end="2024-06-30", universe=SMALL, use_fundamentals=True)
    # offline: must be flagged UNAVAILABLE, never silently claimed as used
    assert "UNAVAILABLE" in r.sources and "fundamentals" in r.sources
    assert "+fundamentals" not in r.sources
    # still produces a valid decision set (degrades to price/volume)
    assert r.decisions
    assert all(0.0 <= w <= 0.08 + 1e-9 for w in r.targets.values())


def test_default_sleeve_has_no_sec_claim(_offline):
    r = build_stock_sleeve(end="2024-06-30", universe=SMALL)   # variants 2/4 path
    assert "fundamentals" not in r.sources and "insider" not in r.sources
