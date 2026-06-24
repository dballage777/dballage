"""Point-in-time guarantees for the SEC EDGAR fundamentals path.

A fundamental value must NOT influence any feature before its filing date — the
single most important property of fundamental data (and the classic look-ahead
trap). No network: we feed synthetic companyfacts / frames directly.
"""
import os
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from v12.data.fundamentals import _pit_series, _company_frame
from v12.features.fundamental import build_fundamental_features


def _facts():
    """Minimal companyfacts: revenue filed 2021-02-15 (FY2020) then 2022-02-15."""
    return {"facts": {"us-gaap": {
        "Revenues": {"units": {"USD": [
            {"end": "2020-12-31", "val": 1000, "fp": "FY", "filed": "2021-02-15"},
            {"end": "2021-12-31", "val": 1200, "fp": "FY", "filed": "2022-02-15"},
        ]}},
        "StockholdersEquity": {"units": {"USD": [
            {"end": "2020-12-31", "val": 500, "fp": "FY", "filed": "2021-02-15"},
        ]}},
        "NetIncomeLoss": {"units": {"USD": [
            {"end": "2020-12-31", "val": 100, "fp": "FY", "filed": "2021-02-15"},
        ]}},
    }, "dei": {
        "EntityCommonStockSharesOutstanding": {"units": {"shares": [
            {"end": "2020-12-31", "val": 10, "fp": "FY", "filed": "2021-02-15"},
        ]}},
    }}}


def test_pit_series_indexes_by_filing_date():
    s = _pit_series(_facts(), ["Revenues"], annual_only=True)
    assert list(s.index) == [pd.Timestamp("2021-02-15"), pd.Timestamp("2022-02-15")]
    assert s.iloc[0] == 1000 and s.iloc[1] == 1200


def test_company_frame_has_filed_index():
    frame = _company_frame(_facts())
    assert frame is not None
    assert frame.index.min() == pd.Timestamp("2021-02-15")
    assert "revenue" in frame and "equity" in frame and "shares" in frame


def test_fundamentals_are_point_in_time():
    """Revenue filed 2021-02-15 must not appear in features before that date."""
    frame = _company_frame(_facts())
    dates = pd.bdate_range("2021-01-01", "2021-03-31")
    close = pd.Series(50.0, index=dates)
    feats = build_fundamental_features(close, frame, dates)

    before = feats.loc[dates < "2021-02-15", "sales_to_price"]
    after = feats.loc[dates >= "2021-02-15", "sales_to_price"]
    assert before.isna().all(), "LEAK: fundamentals visible before filing date"
    assert after.notna().any(), "fundamentals never became visible after filing"
    # sanity: sales/price = revenue / (price*shares) = 1000/(50*10) = 2.0
    assert abs(after.dropna().iloc[0] - 2.0) < 1e-9


def test_growth_is_pit_and_needs_two_filings():
    frame = _company_frame(_facts())
    dates = pd.bdate_range("2021-01-01", "2022-03-31")
    close = pd.Series(50.0, index=dates)
    feats = build_fundamental_features(close, frame, dates)
    # YoY revenue growth only knowable after the 2nd filing (2022-02-15)
    g_before = feats.loc[dates < "2022-02-15", "rev_growth_yoy"]
    g_after = feats.loc[dates >= "2022-02-15", "rev_growth_yoy"].dropna()
    assert g_before.isna().all()
    assert abs(g_after.iloc[0] - 0.2) < 1e-9  # 1200/1000 - 1
