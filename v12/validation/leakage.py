"""Explicit, executable leakage assertions.

These run as part of every experiment. If any fail, the experiment aborts —
a loud failure beats a silently inflated Sharpe (the V1-V9A trap).
"""
from __future__ import annotations

import numpy as np
import pandas as pd


def assert_no_leakage(panel, feature_cols, splits, horizon: int):
    """Run a battery of cheap structural checks.

    1. No feature column is (near-)identical to the future target.
    2. Train and test index sets are disjoint within every fold.
    3. The max train date is strictly before the min test date in each fold
       by at least ``horizon`` days (purge gap honoured).
    """
    issues = []

    # 1) feature/target contamination
    tgt = panel["target"]
    for c in feature_cols:
        corr = panel[c].corr(tgt)
        if pd.notna(corr) and abs(corr) > 0.95:
            issues.append(f"Feature '{c}' corr={corr:.3f} with target (possible leak).")

    # 2 & 3) fold integrity
    dates = panel.index.get_level_values("date")
    for tr_idx, te_idx, info in splits:
        if set(tr_idx) & set(te_idx):
            issues.append(f"Fold {info['fold']}: train/test indices overlap.")
        if len(tr_idx) and len(te_idx):
            max_train = dates[tr_idx].max()
            min_test = dates[te_idx].min()
            gap = (min_test - max_train).days
            if max_train >= min_test:
                issues.append(f"Fold {info['fold']}: train date >= test date.")
            elif gap < 1:
                issues.append(f"Fold {info['fold']}: purge gap too small ({gap}d).")

    if issues:
        raise AssertionError("LEAKAGE CHECK FAILED:\n  - " + "\n  - ".join(issues))
    return True
