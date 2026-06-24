"""Universe resolution with survivorship-bias controls.

The default universe is a list of *today's* large caps. That is textbook
**survivorship bias**: it silently excludes names that were liquid in the past
but later crashed, merged, or delisted (e.g. it would have omitted the losers of
the 2000 and 2008 cohorts). A backtest on such a universe overstates returns.

This module makes that bias explicit and offers a real fix: a point-in-time
(PIT) membership file. Provide a CSV with columns ``ticker,start,end`` (one row
per membership window; blank ``end`` = still a member). ``membership_mask`` then
yields a date x ticker boolean of who was actually in the universe each day, and
the feature pipeline NaNs out non-members so they never contribute a label.
"""
from __future__ import annotations

import os
from typing import List, Optional, Tuple

import pandas as pd

from ..utils import get_logger

log = get_logger("universe")


def resolve_universe(data_cfg) -> Tuple[List[str], dict]:
    """Return (tickers, meta). ``meta`` records bias status for the report."""
    src = getattr(data_cfg, "universe_source", "static")
    if src and src != "static" and os.path.exists(src):
        df = pd.read_csv(src, comment="#")
        tickers = sorted(df["ticker"].astype(str).unique().tolist())
        meta = {"universe_source": src, "survivorship_safe": True,
                "n_members": len(tickers),
                "note": "Point-in-time membership file supplied; survivorship bias controlled."}
        log.info("Universe from PIT file %s: %d names.", src, len(tickers))
        return tickers, meta

    tickers = list(data_cfg.universe)
    meta = {"universe_source": "static", "survivorship_safe": False,
            "n_members": len(tickers),
            "note": ("STATIC universe of current large caps — SURVIVORSHIP BIASED. "
                     "Results overstate returns; supply a point-in-time membership "
                     "CSV (data_cfg.universe_source) for honest long-horizon tests.")}
    log.warning("SURVIVORSHIP BIAS: static current-constituents universe in use. %s",
                meta["note"])
    return tickers, meta


def membership_mask(data_cfg, dates: pd.DatetimeIndex,
                    tickers: List[str]) -> Optional[pd.DataFrame]:
    """Date x ticker boolean of PIT membership, or None for a static universe."""
    src = getattr(data_cfg, "universe_source", "static")
    if not src or src == "static" or not os.path.exists(src):
        return None
    df = pd.read_csv(src, comment="#", parse_dates=["start", "end"])
    mask = pd.DataFrame(False, index=dates, columns=tickers)
    for _, row in df.iterrows():
        t = str(row["ticker"])
        if t not in mask.columns:
            continue
        start = row["start"] if pd.notna(row["start"]) else dates[0]
        end = row["end"] if pd.notna(row["end"]) else dates[-1]
        mask.loc[(mask.index >= start) & (mask.index <= end), t] = True
    return mask
