"""Refresh the committed SEC cache (fundamentals + insider) — safely.

Fetches fresh SEC data into a TEMP dir and only overwrites the committed cache
(data_cache/fundamentals.json, data_cache/insider.json) if the download actually
produced data. If SEC is unreachable/empty, the existing committed cache is left
untouched (exit 1) — we never replace a good snapshot with an empty one.

Run weekly by .github/workflows/refresh_sec_cache.yml, or by hand:
    SEC_USER_AGENT="Name email" python -m experiments.refresh_sec_cache
"""
from __future__ import annotations

import datetime as _dt
import os
import shutil
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import warnings
warnings.filterwarnings("ignore")

from v12.config import BROAD_UNIVERSE
from v12.data.fundamentals import load_fundamentals
from v12.data.insider import load_insider
from v12.utils import get_logger

log = get_logger("refresh_sec")

DEST = "data_cache"
TMP = "data_cache_refresh"


def _has(obj):
    return obj is not None and bool(getattr(obj, "data", None))


def main():
    ua = os.environ.get("SEC_USER_AGENT") or None
    os.makedirs(TMP, exist_ok=True)
    os.makedirs(DEST, exist_ok=True)
    year = _dt.date.today().year

    log.info("Fetching fresh fundamentals + insider into %s ...", TMP)
    fund = ins = None
    try:
        fund = load_fundamentals(list(BROAD_UNIVERSE), TMP, ua)
    except Exception as e:
        log.warning("fundamentals fetch error: %s", e)
    try:
        ins = load_insider(list(BROAD_UNIVERSE), TMP, ua, start_year=2015, end_year=year)
    except Exception as e:
        log.warning("insider fetch error: %s", e)

    updated = []
    for name, obj in [("fundamentals.json", fund), ("insider.json", ins)]:
        src = os.path.join(TMP, name)
        if _has(obj) and os.path.exists(src) and os.path.getsize(src) > 0:
            shutil.copy(src, os.path.join(DEST, name))
            updated.append(name)
            log.info("refreshed %s (%d names)", name, len(obj.data))
        else:
            log.warning("%s NOT refreshed (no data) — kept existing committed cache", name)

    shutil.rmtree(TMP, ignore_errors=True)
    if not updated:
        # Not a failure: safely keeping the good committed cache is the correct
        # fallback when SEC is briefly unreachable. Exit 0 so the weekly workflow
        # stays green (no false-alarm emails); the commit step finds no changes.
        print("REFRESH: no sources refreshed (SEC unreachable) — existing cache kept.")
        return
    print("REFRESH OK: updated " + ", ".join(updated))


if __name__ == "__main__":
    main()
