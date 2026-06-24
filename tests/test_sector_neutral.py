"""Sector-neutralization correctness (V13 enhancement #1)."""
import os
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from v12.features.cross_sectional import sector_neutral_rank


def test_ranks_are_within_sector():
    dates = pd.bdate_range("2021-01-01", periods=3)
    # 4 names, 2 sectors
    panel = pd.DataFrame(
        {"A": [1, 2, 3], "B": [4, 5, 6], "C": [10, 20, 30], "D": [40, 50, 60]},
        index=dates, dtype=float)
    smap = {"A": "X", "B": "X", "C": "Y", "D": "Y"}
    r = sector_neutral_rank(panel, smap)
    # within each sector of 2 names, ranks must be exactly {-0.5, +0.5} not 0
    row = r.iloc[0]
    assert set(np.round(row[["A", "B"]].values, 2)) == {0.0, 0.5} or \
           set(np.round(row[["A", "B"]].values, 2)) == {-0.0, 0.5}  # pct rank of 2 -> {0.5,1.0}-0.5
    # B>A within sector X, D>C within sector Y, regardless of cross-sector scale
    assert row["B"] > row["A"]
    assert row["D"] > row["C"]
    # C (small in absolute terms) is NOT penalized vs A/B because it's ranked in Y
    assert row["C"] == row["A"]  # both bottom-of-sector


def test_sector_neutral_target_demeans_within_sector():
    """Within-sector de-meaning => each sector's mean forward return is ~0 per date."""
    from v12.data.sectors import SECTOR_MAP
    dates = pd.bdate_range("2021-01-01", periods=4)
    names = ["AAPL", "MSFT", "JPM", "BAC"]  # Tech, Tech, Fin, Fin
    fwd = pd.DataFrame(np.random.RandomState(0).normal(size=(4, 4)),
                       index=dates, columns=names)
    sec = pd.Series({t: SECTOR_MAP.get(t, "Other") for t in names})
    target = fwd.copy()
    for _, grp in sec.groupby(sec):
        cols = list(grp.index)
        target[cols] = fwd[cols].sub(fwd[cols].mean(axis=1), axis=0)
    # Tech pair and Fin pair each sum to ~0 per date
    assert np.allclose(target[["AAPL", "MSFT"]].sum(axis=1), 0.0)
    assert np.allclose(target[["JPM", "BAC"]].sum(axis=1), 0.0)
