"""Point-in-time insider transactions from SEC EDGAR (free, no API key).

Form 4 reports insider open-market purchases (code ``P``) and sales (``S``). We
index every transaction by its **filing date** (when it became public), so the
backtest only ever sees insider activity after the market did. Cluster *buying*
in particular is a documented, orthogonal signal.

Source: SEC's **bulk quarterly insider-transaction datasets** (one zip per
quarter with all transactions in TSV tables) — ~48 downloads for a decade, vs
the ~100k individual-filing fetches the naive approach would need. Each quarter
is cached so re-runs are instant. Network-restricted sandboxes fail gracefully
and the pipeline skips insider data.
"""
from __future__ import annotations

import io
import json
import os
import xml.etree.ElementTree as ET
import zipfile
from dataclasses import dataclass
from datetime import datetime
from typing import Dict, List, Optional

import pandas as pd

from ..utils import get_logger

log = get_logger("insider")

# Bulk Form 345 datasets, one zip per quarter (tab-separated tables inside).
_DATASET_URL = "https://www.sec.gov/files/structureddata/data/insider-transactions-data-sets/{y}q{q}_form345.zip"


@dataclass
class Insider:
    data: Dict[str, pd.DataFrame]  # ticker -> filing-date-indexed [signed_value, is_purchase]
    source: str = "edgar"


def parse_form4_xml(xml_text: str) -> List[dict]:
    """Parse non-derivative open-market transactions from a single Form 4 doc.

    Kept for unit tests / fallback. Returns dicts for codes P and S only.
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


def _download(url: str, ua: str) -> Optional[bytes]:
    headers = {"User-Agent": ua, "Accept-Encoding": "gzip, deflate"}
    try:
        import requests
        r = requests.get(url, headers=headers, timeout=120)
        return r.content if r.status_code == 200 else None
    except Exception:
        try:
            import urllib.request
            req = urllib.request.Request(url, headers=headers)
            with urllib.request.urlopen(req, timeout=120) as resp:
                return resp.read()
        except Exception:
            return None


def _parse_date(s: pd.Series) -> pd.Series:
    d = pd.to_datetime(s, format="%d-%b-%Y", errors="coerce")  # e.g. 15-FEB-2021
    if d.isna().mean() > 0.5:
        d = pd.to_datetime(s, errors="coerce")                 # fallback ISO etc.
    return d


def _quarter_rows(zbytes: bytes, tickers_upper: set) -> List[tuple]:
    """Return [(ticker, filing_date, signed_value, is_purchase)] for our tickers."""
    rows: List[tuple] = []
    try:
        zf = zipfile.ZipFile(io.BytesIO(zbytes))
    except Exception:
        return rows

    def _read(name):
        for n in zf.namelist():
            if n.upper().endswith(name):
                return pd.read_csv(zf.open(n), sep="\t", dtype=str, low_memory=False)
        return None

    sub = _read("SUBMISSION.TSV")
    nd = _read("NONDERIV_TRANS.TSV")
    if sub is None or nd is None:
        return rows
    sub.columns = [c.upper() for c in sub.columns]
    nd.columns = [c.upper() for c in nd.columns]
    if "ISSUERTRADINGSYMBOL" not in sub or "ACCESSION_NUMBER" not in sub:
        return rows

    sub["SYM"] = sub["ISSUERTRADINGSYMBOL"].astype(str).str.upper().str.strip()
    keep = sub[sub["SYM"].isin(tickers_upper)][["ACCESSION_NUMBER", "FILING_DATE", "SYM"]].copy()
    if keep.empty:
        return rows
    keep["FILING_DATE"] = _parse_date(keep["FILING_DATE"])

    nd = nd[nd["TRANS_CODE"].isin(["P", "S"])]
    merged = nd.merge(keep, on="ACCESSION_NUMBER", how="inner")
    for _, r in merged.iterrows():
        try:
            shares = float(r.get("TRANS_SHARES") or 0)
            price = float(r.get("TRANS_PRICEPERSHARE") or 0)
        except (ValueError, TypeError):
            continue
        if pd.isna(r["FILING_DATE"]):
            continue
        val = shares * price
        is_p = 1 if r["TRANS_CODE"] == "P" else 0
        rows.append((r["SYM"], r["FILING_DATE"], val if is_p else -val, is_p))
    return rows


def load_insider(tickers: List[str], cache_dir: str = "data_cache",
                 user_agent: Optional[str] = None,
                 start_year: int = 2014, end_year: Optional[int] = None) -> Optional[Insider]:
    ua = user_agent or os.environ.get("SEC_USER_AGENT", "v12-research contact@example.com")
    end_year = end_year or datetime.utcnow().year
    cache = os.path.join(cache_dir, "insider.json")
    if os.path.exists(cache):
        log.info("Loading cached insider data from %s", cache)
        blob = json.load(open(cache))

        def _read(v):
            df = pd.read_json(v, orient="split")
            df["filed"] = pd.to_datetime(df["filed"])
            return df.set_index("filed").sort_index()

        return Insider({t: _read(v) for t, v in blob.items()}, "cache")

    tickers_upper = {t.upper() for t in tickers}
    qdir = os.path.join(cache_dir, "insider_q")
    os.makedirs(qdir, exist_ok=True)

    all_rows: List[tuple] = []
    n_ok = 0
    quarters = [(y, q) for y in range(start_year, end_year + 1) for q in range(1, 5)]
    for y, q in quarters:
        qcache = os.path.join(qdir, f"{y}q{q}.json")
        if os.path.exists(qcache):  # resume: skip done quarters
            rows = [tuple(r) for r in json.load(open(qcache))]
            all_rows.extend(rows); n_ok += 1
            continue
        zb = _download(_DATASET_URL.format(y=y, q=q), ua)
        if zb is None:
            log.info("Insider %dQ%d: dataset unavailable (skipped).", y, q)
            continue
        rows = _quarter_rows(zb, tickers_upper)
        json.dump([[r[0], r[1].isoformat(), r[2], r[3]] for r in rows], open(qcache, "w"))
        all_rows.extend([(r[0], r[1], r[2], r[3]) for r in rows])
        n_ok += 1
        log.info("Insider %dQ%d: %d open-market transactions for our universe.", y, q, len(rows))

    if n_ok == 0 or not all_rows:
        log.warning("Insider datasets unavailable; pipeline runs without insider data.")
        return None

    df = pd.DataFrame(all_rows, columns=["ticker", "filed", "signed_value", "is_purchase"])
    df["filed"] = pd.to_datetime(df["filed"])
    data: Dict[str, pd.DataFrame] = {}
    for t, g in df.groupby("ticker"):
        data[t] = g.drop(columns="ticker").set_index("filed").sort_index()

    try:
        json.dump({t: g.reset_index().to_json(orient="split", date_format="iso")
                   for t, g in data.items()}, open(cache, "w"))
        log.info("Cached insider data for %d tickers (%d quarters) -> %s",
                 len(data), n_ok, cache)
    except Exception as e:
        log.warning("Could not cache insider data (%s)", e)
    return Insider(data, "edgar")
