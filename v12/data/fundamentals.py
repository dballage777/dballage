"""Point-in-time fundamentals from SEC EDGAR (free, no API key).

EDGAR's ``companyfacts`` endpoint returns every XBRL financial concept with both
the reporting period (``end``) and the **filing date** (``filed``) — the date the
number became public. We index everything by ``filed`` so a value can never be
used before the market could have known it. This is the difference between honest
fundamentals and the look-ahead bias that inflated V1-V9A.

Network note: SEC requires a descriptive User-Agent. Set ``SEC_USER_AGENT``
(e.g. "yourname you@email.com"). In a network-restricted sandbox the fetch fails
gracefully and the pipeline simply runs without fundamentals.
"""
from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass
from typing import Dict, List, Optional

import pandas as pd

from ..utils import get_logger

log = get_logger("fundamentals")

_TICKERS_URL = "https://www.sec.gov/files/company_tickers.json"
_FACTS_URL = "https://data.sec.gov/api/xbrl/companyfacts/CIK{cik:010d}.json"

# XBRL concepts we use (us-gaap namespace unless noted). Levels are point-in-time
# stock values; flows are annual (fp=FY) to avoid mixing quarterly/annual.
_LEVEL_CONCEPTS = {
    "equity": ["StockholdersEquity", "StockholdersEquityIncludingPortionAttributableToNoncontrollingInterest"],
    "assets": ["Assets"],
    "liabilities": ["Liabilities"],
    "debt": ["LongTermDebtNoncurrent", "LongTermDebt"],
}
_FLOW_CONCEPTS = {
    "net_income": ["NetIncomeLoss"],
    "revenue": ["Revenues", "RevenueFromContractWithCustomerExcludingAssessedTax", "SalesRevenueNet"],
    "gross_profit": ["GrossProfit"],
    "operating_income": ["OperatingIncomeLoss"],
}
_SHARES_CONCEPTS = ["EntityCommonStockSharesOutstanding", "CommonStockSharesOutstanding",
                    "WeightedAverageNumberOfSharesOutstandingBasic"]


@dataclass
class Fundamentals:
    """Point-in-time fundamental series per ticker.

    ``data[ticker]`` is a DataFrame indexed by *filing date* with one column per
    derived raw quantity (equity, revenue, net_income, shares, ...).
    """
    data: Dict[str, pd.DataFrame]
    source: str = "edgar"

    @property
    def tickers(self) -> List[str]:
        return list(self.data.keys())


def _http_get_json(url: str, ua: str) -> Optional[dict]:
    headers = {"User-Agent": ua, "Accept-Encoding": "gzip, deflate"}
    try:
        import requests
        r = requests.get(url, headers=headers, timeout=30)
        if r.status_code != 200:
            log.warning("GET %s -> %s", url, r.status_code)
            return None
        return r.json()
    except Exception:
        pass
    try:
        import urllib.request
        req = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(req, timeout=30) as resp:
            return json.loads(resp.read().decode())
    except Exception as e:  # network-restricted sandbox lands here
        log.warning("Fundamentals fetch failed for %s (%s)", url, e)
        return None


def _ticker_cik_map(cache_dir: str, ua: str) -> Dict[str, int]:
    path = os.path.join(cache_dir, "sec_ticker_cik.json")
    if os.path.exists(path):
        with open(path) as f:
            return {k: int(v) for k, v in json.load(f).items()}
    raw = _http_get_json(_TICKERS_URL, ua)
    if not raw:
        return {}
    mapping = {row["ticker"].upper(): int(row["cik_str"]) for row in raw.values()}
    os.makedirs(cache_dir, exist_ok=True)
    with open(path, "w") as f:
        json.dump(mapping, f)
    return mapping


def _pit_series(facts: dict, concepts: List[str], annual_only: bool) -> Optional[pd.Series]:
    """Build a filing-date-indexed series for the first available concept.

    Dedupe by keeping the latest-filed value per filing date; sorted ascending.
    """
    gaap = facts.get("facts", {}).get("us-gaap", {})
    dei = facts.get("facts", {}).get("dei", {})
    for c in concepts:
        node = gaap.get(c) or dei.get(c)
        if not node:
            continue
        units = node.get("units", {})
        # pick the most populated unit (USD, shares, USD/shares)
        unit_key = max(units, key=lambda k: len(units[k])) if units else None
        if not unit_key:
            continue
        rows = []
        for r in units[unit_key]:
            if "filed" not in r or "val" not in r:
                continue
            if annual_only and r.get("fp") != "FY":
                continue
            rows.append((r["filed"], r["end"], r["val"]))
        if not rows:
            continue
        df = pd.DataFrame(rows, columns=["filed", "end", "val"])
        df["filed"] = pd.to_datetime(df["filed"])
        # latest reported value per filing date
        df = df.sort_values(["filed", "end"]).drop_duplicates("filed", keep="last")
        return df.set_index("filed")["val"].sort_index()
    return None


def _company_frame(facts: dict) -> Optional[pd.DataFrame]:
    cols = {}
    for name, concepts in _LEVEL_CONCEPTS.items():
        s = _pit_series(facts, concepts, annual_only=False)
        if s is not None:
            cols[name] = s
    for name, concepts in _FLOW_CONCEPTS.items():
        s = _pit_series(facts, concepts, annual_only=True)
        if s is not None:
            cols[name] = s
    shares = _pit_series(facts, _SHARES_CONCEPTS, annual_only=False)
    if shares is not None:
        cols["shares"] = shares
    if not cols:
        return None
    # union of all filing dates, forward-filled (each value known from its filed date)
    frame = pd.DataFrame(cols).sort_index()
    return frame[~frame.index.duplicated(keep="last")]


def load_fundamentals(tickers: List[str], cache_dir: str = "data_cache",
                      user_agent: Optional[str] = None) -> Optional[Fundamentals]:
    ua = user_agent or os.environ.get("SEC_USER_AGENT", "v12-research contact@example.com")
    os.makedirs(cache_dir, exist_ok=True)
    cache = os.path.join(cache_dir, "fundamentals.json")
    if os.path.exists(cache):
        log.info("Loading cached fundamentals from %s", cache)
        blob = json.load(open(cache))
        data = {t: pd.read_json(v, orient="split") for t, v in blob.items()}
        return Fundamentals(data=data, source="cache")

    cik_map = _ticker_cik_map(cache_dir, ua)
    if not cik_map:
        log.warning("No ticker->CIK map (network?). Skipping fundamentals.")
        return None

    data: Dict[str, pd.DataFrame] = {}
    for t in tickers:
        cik = cik_map.get(t.upper())
        if cik is None:
            continue
        facts = _http_get_json(_FACTS_URL.format(cik=cik), ua)
        if not facts:
            continue
        frame = _company_frame(facts)
        if frame is not None and len(frame):
            data[t] = frame
        time.sleep(0.12)  # be polite to SEC (<10 req/s)

    if not data:
        log.warning("Fundamentals unavailable for all tickers; pipeline runs without them.")
        return None
    try:
        blob = {t: df.to_json(orient="split", date_format="iso") for t, df in data.items()}
        json.dump(blob, open(cache, "w"))
        log.info("Cached fundamentals for %d tickers -> %s", len(data), cache)
    except Exception as e:
        log.warning("Could not cache fundamentals (%s)", e)
    return Fundamentals(data=data, source="edgar")
