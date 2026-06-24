"""Purged & embargoed walk-forward splitting.

This is the centrepiece of the anti-leakage design (the failure mode that
inflated V1-V9A). For a label horizon ``h`` and an embargo ``e``:

    train window  | purge gap (h) | embargo (e) | test window
    --------------|---------------|-------------|-------------
    learn here    | DROP labels   | DROP rows   | evaluate here

  * Purge: training samples whose forward-looking label overlaps the test
    window are removed (their label "sees" test-period prices).
  * Embargo: a buffer after the test window is excluded from the *next* train
    fold so serially-correlated features can't bleed across the boundary.

Splits are done on unique dates, then expanded to all (date, ticker) rows so the
panel stays balanced and no single date straddles train/test.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Iterator, Tuple, List

import numpy as np
import pandas as pd


@dataclass
class PurgedWalkForward:
    n_splits: int
    train_min_days: int
    test_days: int
    embargo_days: int
    horizon: int
    purge: bool = True

    def split(self, panel: pd.DataFrame) -> Iterator[Tuple[np.ndarray, np.ndarray, dict]]:
        dates = panel.index.get_level_values("date").unique().sort_values()
        n = len(dates)
        date_to_pos = {d: i for i, d in enumerate(dates)}
        pos = panel.index.get_level_values("date").map(date_to_pos).to_numpy()

        # expanding-train, rolling-test folds laid out from the end backwards
        last_test_end = n
        folds = []
        for _ in range(self.n_splits):
            test_end = last_test_end
            test_start = test_end - self.test_days
            train_end = test_start - self.embargo_days - self.horizon
            if train_end < self.train_min_days:
                break
            folds.append((0, train_end, test_start, test_end))
            last_test_end = test_start  # walk backwards, non-overlapping tests
        folds = folds[::-1]  # chronological order

        for k, (tr0, tr1, te0, te1) in enumerate(folds):
            train_mask = (pos >= tr0) & (pos < tr1)
            test_mask = (pos >= te0) & (pos < te1)
            if self.purge:
                # remove train rows whose label window reaches into [te0, te1)
                label_end = pos + self.horizon
                overlap = (label_end >= te0) & (pos < te0)
                train_mask &= ~overlap
            info = {
                "fold": k,
                "train_dates": (dates[tr0], dates[max(tr1 - 1, 0)]),
                "test_dates": (dates[te0], dates[min(te1 - 1, n - 1)]),
                "n_train": int(train_mask.sum()),
                "n_test": int(test_mask.sum()),
            }
            yield np.where(train_mask)[0], np.where(test_mask)[0], info
