"""Warm the price cache once (run where the network is open).

After this succeeds, ``data_cache/`` holds a parquet the experiment reads even in
network-restricted environments — so you can do the heavy live fetch on a
machine with access, commit/copy the cache, and run backtests anywhere.

    python scripts/fetch_data.py                 # default 10y universe
    python scripts/fetch_data.py --start 2010-01-01 --end 2025-01-01
"""
from __future__ import annotations

import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from v12.config import DataConfig
from v12.data import load_prices
from v12.data.universe import resolve_universe
from v12.utils import get_logger

log = get_logger("fetch")


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--start", default="2015-01-01")
    p.add_argument("--end", default="2025-01-01")
    p.add_argument("--universe-source", default="static")
    args = p.parse_args()

    cfg = DataConfig(start=args.start, end=args.end,
                     universe_source=args.universe_source, allow_synthetic=False)
    cfg.universe, meta = resolve_universe(cfg)
    log.info("Fetching %d tickers %s -> %s", len(cfg.universe), args.start, args.end)
    try:
        data = load_prices(cfg)
    except RuntimeError as e:
        log.error("Live fetch failed (%s). Run this where outbound HTTPS to "
                  "Yahoo Finance is allowed (Codespaces/Colab/your laptop).", e)
        sys.exit(1)
    log.info("Cached %d tickers x %d days from source=%s into %s/",
             len(data.tickers), len(data.dates), data.source, cfg.cache_dir)
    if data.source != "yfinance":
        log.warning("Source was '%s', not live yfinance — cache is not real prices.",
                    data.source)


if __name__ == "__main__":
    main()
