"""Point-in-time insider transactions from SEC EDGAR Form 4 (free, no API key).

Form 4 reports insider open-market purchases (code ``P``) and sales (``S``). We
index every transaction by the **filing date** (when it became public), so the
backtest only ever sees insider activity after the market did. Cluster *buying*
in particular is a documented, orthogonal signal (insiders act on information not
yet in price or financials).

Heavy: a decade of Form 4s is thousands of filings. Results are cached per run.
Network-restricted sandboxes fail gracefully and the pipeline skips insider data.
"""
from __future__ import annotations

import json
import os
import time
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from typing import Dict, List, Optional

import pandas as pd

from ..utils import get_logger
from .fundamentals import _http_get_json, _ticker_cik_map

log = get_logger("insider")

_SUBMISSIONS_URL = "https://data.sec.gov/submissions/CIK{cik:010d}.json"
_ARCHIVE = "https://www.sec.gov/Archives/edgar/data/{cik}/{acc}/{doc}"


@dataclass
class Insider:
    data: Dict[str, pd.DataFrame]  # ticker -> filing-date-indexed [signed_value, is_purchase]
    source: str = "edgar"


def parse_form4_xml(xml_text: str) -> List[dict]:
    """Parse non-derivative open-market transactions from a Form 4 document.

    Returns dicts: {code, shares, price, signed_value, is_purchase}. Only codes
    P (purchase) and S (sale) — the open-market, information-bearing trades.
    """
    out: List[dict] = []
    try:
        root = ET.fromstring(xml_text)
    except Exception:
        return out
    for tx in root.iter("nonDerivativeTransaction"):
        code_el = tx.find("./transactionCoding/transactionCode")
        code = (code_el.text or "").strip() if code_el is not None else ""
        if code not in ("P", "S"):
            continue
        sh = tx.find("./transactionAmounts/transactionShares/value")
        pr = tx.find("./transactionAmounts/transactionPricePerShare/value")
        try:
            shares = float(sh.text) if sh is not None and sh.text else 0.0
            price = float(pr.text) if pr is not None and pr.text else 0.0
        except ValueError:
            continue
        value = shares * price
        out.append({"code": code, "shares": shares, "price": price,
                    "signed_value": value if code == "P" else -value,
                    "is_purchase": 1 if code == "P" else 0})
    return out


def _form4_refs(cik: int, ua: str) -> List[tuple]:
    """Return [(filing_date, accession, primary_document)] for all Form 4s."""
    sub = _http_get_json(_SUBMISSIONS_URL.format(cik=cik), ua)
    if not sub:
        return []
    refs: List[tuple] = []

    def _collect(recent):
        forms = recent.get("form", [])
        for i, f in enumerate(forms):
            if f == "4":
                refs.append((recent["filingDate"][i], recent["accessionNumber"][i],
                             recent["primaryDocument"][i]))

    _collect(sub.get("filings", {}).get("recent", {}))
    for extra in sub.get("filings", {}).get("files", []):  # older history shards
        more = _http_get_json(f"https://data.sec.gov/submissions/{extra['name']}", ua)
        if more:
            _collect(more)
        time.sleep(0.1)
    return refs


def load_insider(tickers: List[str], cache_dir: str = "data_cache",
                 user_agent: Optional[str] = None) -> Optional[Insider]:
    ua = user_agent or os.environ.get("SEC_USER_AGENT", "v12-research contact@example.com")
    cache = os.path.join(cache_dir, "insider.json")
    if os.path.exists(cache):
        log.info("Loading cached insider data from %s", cache)
        blob = json.load(open(cache))

        def _read(v):
            df = pd.read_json(v, orient="split")
            df["filed"] = pd.to_datetime(df["filed"])
            return df.set_index("filed").sort_index()

        return Insider({t: _read(v) for t, v in blob.items()}, "cache")

    cik_map = _ticker_cik_map(cache_dir, ua)
    if not cik_map:
        log.warning("No ticker->CIK map (network?). Skipping insider data.")
        return None

    # Incremental, resumable cache: progress is saved per ticker so a long fetch
    # (or a Ctrl+C) is never wasted — re-running picks up where it left off.
    progress = os.path.join(cache_dir, "insider_progress.json")
    blob: Dict[str, str] = json.load(open(progress)) if os.path.exists(progress) else {}
    data: Dict[str, pd.DataFrame] = {}
    for t, v in blob.items():
        df = pd.read_json(v, orient="split")
        df["filed"] = pd.to_datetime(df["filed"])
        data[t] = df.set_index("filed").sort_index()

    todo = [t for t in tickers if t not in blob]
    log.info("Insider fetch: %d cached, %d to fetch (resumable).", len(blob), len(todo))
    for t in todo:
        cik = cik_map.get(t.upper())
        rows = []
        if cik is not None:
            for filed, acc, doc in _form4_refs(cik, ua):
                url = _ARCHIVE.format(cik=cik, acc=acc.replace("-", ""), doc=doc)
                xml = _http_text(url, ua)
                if xml:
                    for tx in parse_form4_xml(xml):
                        rows.append((filed, tx["signed_value"], tx["is_purchase"]))
                time.sleep(0.12)  # be polite to SEC
        df = pd.DataFrame(rows, columns=["filed", "signed_value", "is_purchase"])
        if rows:
            df["filed"] = pd.to_datetime(df["filed"])
            data[t] = df.set_index("filed").sort_index()
        # persist progress after each ticker (even empties, so we don't refetch)
        blob[t] = df.to_json(orient="split", date_format="iso")
        json.dump(blob, open(progress, "w"))
        log.info("Insider %s: %d open-market transactions (%d/%d done)",
                 t, len(rows), len(blob), len(tickers))

    if not data:
        log.warning("Insider data unavailable; pipeline runs without it.")
        return None
    try:
        json.dump({t: df.reset_index().to_json(orient="split", date_format="iso")
                   for t, df in data.items()}, open(cache, "w"))
        log.info("Cached insider data for %d tickers -> %s", len(data), cache)
    except Exception as e:
        log.warning("Could not cache insider data (%s)", e)
    return Insider(data, "edgar")


def _http_text(url: str, ua: str) -> Optional[str]:
    headers = {"User-Agent": ua}
    try:
        import requests
        r = requests.get(url, headers=headers, timeout=30)
        return r.text if r.status_code == 200 else None
    except Exception:
        try:
            import urllib.request
            req = urllib.request.Request(url, headers=headers)
            with urllib.request.urlopen(req, timeout=30) as resp:
                return resp.read().decode(errors="ignore")
        except Exception:
            return None
