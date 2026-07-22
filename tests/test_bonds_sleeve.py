"""Variant 7 — standalone bonds sleeve invariants (caps, structure)."""
import pytest

import v12.data.loader as loader
from v12.strategies import build_bonds_sleeve
from v12.strategies.bonds_sleeve import BONDS_CLASS_CAP, BONDS_POSITION_CAP

BONDS = ["AGG", "IEF", "SHY", "LQD"]
EPS = 1e-6


@pytest.fixture(scope="module")
def _force_synthetic():
    orig = loader._download_yf
    loader._download_yf = lambda *a, **k: None
    yield
    loader._download_yf = orig


@pytest.fixture(scope="module")
def bonds(_force_synthetic):
    return build_bonds_sleeve(end="2024-12-31", universe=BONDS)


def test_bonds_position_cap(bonds):
    for a, w in bonds.targets.items():
        assert w <= BONDS_POSITION_CAP + EPS


def test_bonds_class_cap(bonds):
    assert bonds.bonds_exposure <= BONDS_CLASS_CAP + EPS


def test_bonds_exposure_within_book(bonds):
    # a standalone book: total exposure is bounded and cash is the residual
    assert 0.0 - EPS <= bonds.bonds_exposure <= 1.0 + EPS
    assert bonds.n_positions == sum(1 for w in bonds.targets.values() if w > 0)


def test_bonds_decisions_present(bonds):
    # decision list exists and every held position carries a positive weight
    assert isinstance(bonds.decisions, list)
    for a, w in bonds.targets.items():
        assert w > 0
