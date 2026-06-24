"""Point-in-time fundamental features (value / quality / growth).

Each ticker's filing-date-indexed raw fundamentals are forward-filled onto the
daily price index, so on date t we only ever see the most recent filing with
``filed <= t``. Ratios use the daily price for market cap. Nothing here can see a
number before it was filed — the leakage gate and walk-forward still apply.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

FUNDAMENTAL_COLS = [
    "earnings_yield", "book_to_price", "sales_to_price", "fcf_proxy_yield",
    "roe", "gross_margin", "op_margin", "debt_to_equity",
    "rev_growth_yoy", "ni_growth_yoy",
]


def build_fundamental_features(close: pd.Series, frame: pd.DataFrame,
                               dates: pd.DatetimeIndex) -> pd.DataFrame:
    """Return daily fundamental features for one ticker, indexed by ``dates``.

    ``frame`` is filing-date-indexed (from v12.data.fundamentals). Growth is
    computed on the annual filing series *before* forward-filling, so it reflects
    only information known at each filing date.
    """
    out = pd.DataFrame(index=dates, columns=FUNDAMENTAL_COLS, dtype=float)
    if frame is None or frame.empty:
        return out

    # YoY growth from the (annual) filing series, computed pre-ffill (PIT-safe)
    growth = pd.DataFrame(index=frame.index)
    if "revenue" in frame:
        growth["rev_growth_yoy"] = frame["revenue"].pct_change()
    if "net_income" in frame:
        growth["ni_growth_yoy"] = frame["net_income"].pct_change()

    # forward-fill filings onto the daily calendar (value known from filed date)
    f = frame.reindex(frame.index.union(dates)).ffill().reindex(dates)
    g = growth.reindex(growth.index.union(dates)).ffill().reindex(dates)

    px = close.reindex(dates)
    shares = f["shares"] if "shares" in f else np.nan
    mcap = px * shares

    def safe(num, den):
        den = den.replace(0, np.nan) if isinstance(den, pd.Series) else den
        return num / den

    if "net_income" in f:
        out["earnings_yield"] = safe(f["net_income"], mcap)
        if "shares" in f:
            out["ni_growth_yoy"] = g.get("ni_growth_yoy")
    if "equity" in f:
        out["book_to_price"] = safe(f["equity"], mcap)
        if "net_income" in f:
            out["roe"] = safe(f["net_income"], f["equity"])
    if "revenue" in f:
        out["sales_to_price"] = safe(f["revenue"], mcap)
        out["rev_growth_yoy"] = g.get("rev_growth_yoy")
        if "gross_profit" in f:
            out["gross_margin"] = safe(f["gross_profit"], f["revenue"])
        if "operating_income" in f:
            out["op_margin"] = safe(f["operating_income"], f["revenue"])
            # crude FCF proxy: operating income / market cap (no capex in basic facts)
            out["fcf_proxy_yield"] = safe(f["operating_income"], mcap)
    if "debt" in f and "equity" in f:
        out["debt_to_equity"] = safe(f["debt"], f["equity"])
    elif "liabilities" in f and "equity" in f:
        out["debt_to_equity"] = safe(f["liabilities"], f["equity"])

    return out.replace([np.inf, -np.inf], np.nan).astype(float)
