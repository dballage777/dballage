"""Daily monitoring report runner (the spec's DAILY REPORT + OUTPUTS).

Builds the full system for the latest date, scores the whole universe 0-100,
and writes the daily monitoring report (regime, allocation, top signals/risks/
opportunities, ranked Top-N with the mandated fields) to results/reports/.

    python -m experiments.daily_report
    python -m experiments.daily_report --quick --end 2024-06-30

Honest by construction: only price/volume-backed factors contribute; the report
states how much of the designed source diet is actually live.
"""
from __future__ import annotations

import argparse
import datetime as _dt
import os
import sys
import warnings

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
warnings.filterwarnings("ignore")

import pandas as pd

from v12.config import ExperimentConfig, BROAD_UNIVERSE, CRYPTO_UNIVERSE, CRYPTO_BENCHMARK
from v12.data import load_prices
from v12.strategies import build_full_system, all_decisions
from v12.reporting import score_assets, build_daily_report
from v12.sources import live_weight_fraction
from v12.utils import get_logger

log = get_logger("report")

SMALL_STOCKS = ["AAPL", "MSFT", "NVDA", "JPM", "XOM", "JNJ", "PG", "KO"]
SMALL_CRYPTO = ["BTC-USD", "ETH-USD", "SOL-USD", "XRP-USD", "ADA-USD", "DOGE-USD"]


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--end", default=None, help="data end date; defaults to today (live)")
    p.add_argument("--out", default="results/reports")
    p.add_argument("--quick", action="store_true")
    args = p.parse_args()
    end = args.end or _dt.date.today().isoformat()

    stocks = SMALL_STOCKS if args.quick else list(BROAD_UNIVERSE)
    crypto = SMALL_CRYPTO if args.quick else list(CRYPTO_UNIVERSE)

    sysres = build_full_system(end=end, stock_universe=stocks, crypto_universe=crypto)

    # price/volume panels for scoring + entry ranges
    scfg = ExperimentConfig(name="rep_s"); scfg.data.universe = stocks
    scfg.data.start, scfg.data.end = "2015-01-01", end
    ccfg = ExperimentConfig(name="rep_c"); ccfg.data.universe = crypto
    ccfg.data.benchmark = CRYPTO_BENCHMARK; ccfg.data.rs_refs = [CRYPTO_BENCHMARK]
    ccfg.data.start, ccfg.data.end = "2018-01-01", end
    sdata, cdata = load_prices(scfg.data), load_prices(ccfg.data)
    close = pd.concat([sdata.close, cdata.close], axis=1)
    close = close.loc[:, ~close.columns.duplicated()]
    volume = pd.concat([sdata.volume, cdata.volume], axis=1)
    volume = volume.loc[:, ~volume.columns.duplicated()]

    decisions = all_decisions(sysres)
    model_ev = {d.asset: d.ev_score for d in decisions}
    universe = [a for a in (stocks + crypto)]
    scores = score_assets(close[[c for c in universe if c in close.columns]],
                          volume[[c for c in universe if c in volume.columns]],
                          model_ev=model_ev, asof=pd.Timestamp(sysres.date))

    # ffill so weekend/holiday rows (crypto trades, stocks don't) don't blank out
    # stock prices — carry the last actual trading price forward.
    last_price = close.loc[:pd.Timestamp(sysres.date)].ffill().iloc[-1]
    allocation = {"stocks": sysres.stock_exposure, "crypto": sysres.crypto_exposure,
                  "cash": sysres.cash}
    md = build_daily_report(
        date=sysres.date, stock_regime=sysres.stock.regime, crypto_regime=sysres.crypto.regime,
        allocation=allocation, scores=scores, decisions=decisions,
        targets=sysres.combined_targets, last_price=last_price,
        crypto_set=set(crypto), live_weight_fraction=live_weight_fraction())

    os.makedirs(args.out, exist_ok=True)
    path = os.path.join(args.out, f"daily_{sysres.date:%Y-%m-%d}.md")
    with open(path, "w") as f:
        f.write(md)
    print(md[:1500])
    print(f"\n... (truncated) full report -> {path}")
    log.info("Wrote daily report -> %s", path)


if __name__ == "__main__":
    main()
