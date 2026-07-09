"""Macro-data loader for the macro-regime experiment (variant-7 candidate).

Fetches a few classic macro regime indicators. Source priority, honest and
graceful:
  1. OpenBB (if installed)  — obb.economy.fred_series(...)
  2. FRED CSV (no API key)  — fred.stlouisfed.org/graph/fredgraph.csv?id=...
  3. synthetic fallback     — clearly marked; for pipeline validation only

Indicators (the macro thesis for regime detection):
  T10Y2Y  10y-2y Treasury spread  (inverted = recession risk)
  NFCI    Chicago Fed National Financial Conditions Index (higher = tighter/stress)

Returns (DataFrame[date x series], source_str). Nothing is ever presented as
real when it is synthetic — the source is stamped so the experiment can say so.
"""
from __future__ import annotations

import io
import os
from typing import List, Optional, Tuple

import numpy as np
import pandas as pd

from ..utils import get_logger

log = get_logger("macro")

DEFAULT_SERIES = ["T10Y2Y", "NFCI"]


def _via_openbb(series: List[str], start: str, end: str) -> Optional[pd.DataFrame]:
    try:
        from openbb import obb  # heavy, optional
    except Exception:
        return None
    try:
        cols = {}
        for sid in series:
            df = obb.economy.fred_series(symbol=sid, start_date=start, end_date=end).to_df()
            col = "value" if "value" in df.columns else df.columns[-1]
            cols[sid] = df[col]
        out = pd.DataFrame(cols)
        out.index = pd.to_datetime(out.index)
        return out.dropna(how="all")
    except Exception as e:
        log.warning("OpenBB macro fetch failed: %s", e)
        return None


def _via_fred_csv(series: List[str], start: str, end: str) -> Optional[pd.DataFrame]:
    """FRED's public CSV endpoint needs no API key."""
    import urllib.request
    cols = {}
    for sid in series:
        url = (f"https://fred.stlouisfed.org/graph/fredgraph.csv?id={sid}"
               f"&cosd={start}&coed={end}")
        try:
            with urllib.request.urlopen(url, timeout=30) as r:
                raw = r.read().decode("utf-8")
            df = pd.read_csv(io.StringIO(raw))
            df.columns = ["date", sid]
            df["date"] = pd.to_datetime(df["date"])
            df[sid] = pd.to_numeric(df[sid], errors="coerce")
            cols[sid] = df.set_index("date")[sid]
        except Exception as e:
            log.warning("FRED CSV fetch failed for %s: %s", sid, e)
            return None
    return pd.DataFrame(cols).dropna(how="all") if cols else None


def _synthetic(series: List[str], start: str, end: str, seed: int = 7) -> pd.DataFrame:
    idx = pd.bdate_range(start, end)
    rng = np.random.default_rng(seed)
    cols = {}
    for i, sid in enumerate(series):
        # mean-reverting-ish walk around 0 (like a spread / conditions index)
        x = np.cumsum(rng.normal(0, 0.05, len(idx)))
        x = x - pd.Series(x).rolling(200, min_periods=1).mean().values
        cols[sid] = x
    return pd.DataFrame(cols, index=idx)


def load_macro(series: Optional[List[str]] = None, start: str = "2015-01-01",
               end: str = "2026-06-20", allow_synthetic: bool = True
               ) -> Tuple[pd.DataFrame, str]:
    series = series or list(DEFAULT_SERIES)
    df = _via_openbb(series, start, end)
    if df is not None and not df.empty:
        return df, "openbb"
    df = _via_fred_csv(series, start, end)
    if df is not None and not df.empty:
        return df, "fred_csv"
    if not allow_synthetic:
        raise RuntimeError("macro data unavailable and synthetic disabled")
    log.warning("Falling back to SYNTHETIC macro data (pipeline validation only, NOT real).")
    return _synthetic(series, start, end), "synthetic"


def macro_risk_off(macro: pd.DataFrame) -> pd.Series:
    """Point-in-time macro 'risk-off' flag (True = defensive), from state up to t.

    Risk-off when the yield curve is inverted (T10Y2Y < 0) OR financial
    conditions are tight (NFCI > 0). NFCI is constructed to be zero-centered, so
    a positive reading means tighter-than-average conditions (stress) — an
    absolute threshold, not a rolling percentile (a percentile would flag a fixed
    fraction of days even in calm regimes). Both are point-in-time levels.
    """
    flags = pd.Series(False, index=macro.index)
    if "T10Y2Y" in macro:
        flags = flags | (macro["T10Y2Y"] < 0)
    if "NFCI" in macro:
        flags = flags | (macro["NFCI"] > 0.0)
    return flags.fillna(False)
