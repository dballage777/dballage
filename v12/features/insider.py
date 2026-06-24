"""Point-in-time insider (Form 4) features.

From filing-date-indexed open-market transactions we build trailing-window
signals — all using only filings public as of date t:

  * insider_buy_count_90d   — # of open-market purchases in the last 90d
                              (cluster buying; size-agnostic).
  * insider_net_buy_norm    — net $ bought vs sold over 90d, self-normalized by
                              trailing-365d gross activity -> [-1, 1] (direction).

Sparse by nature (most names, most days = no filings), so these contribute
episodically and are valuable mainly because they're orthogonal to price and
fundamentals.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

INSIDER_COLS = ["insider_buy_count_90d", "insider_net_buy_norm"]


def build_insider_features(frame: pd.DataFrame, dates: pd.DatetimeIndex) -> pd.DataFrame:
    out = pd.DataFrame(index=dates, columns=INSIDER_COLS, dtype=float)
    if frame is None or frame.empty:
        return out.fillna(0.0)  # no insider data => neutral

    # daily flows (events are dated by filing date; sum same-day events)
    signed = frame["signed_value"].groupby(level=0).sum().reindex(dates).fillna(0.0)
    purchases = frame["is_purchase"].groupby(level=0).sum().reindex(dates).fillna(0.0)

    buy_count_90 = purchases.rolling(90, min_periods=1).sum()
    net_90 = signed.rolling(90, min_periods=1).sum()
    gross_365 = signed.abs().rolling(365, min_periods=1).sum()

    out["insider_buy_count_90d"] = buy_count_90
    out["insider_net_buy_norm"] = net_90 / (gross_365 + 1.0)
    return out.replace([np.inf, -np.inf], np.nan).fillna(0.0)
