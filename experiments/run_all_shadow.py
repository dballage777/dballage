"""Shadow horse-race runner — runs ALL paper variants once and records them.

This is the engine of the 90-180 day forward paper test. On each (daily) run it:

  1. builds all four variants for the latest date:
       v1 equity_validated  — the validated low-vol baseline (control arm)
       v2 equity_full_goal  — stocks + all GOAL conditions
       v3 crypto_full_goal  — crypto + all GOAL conditions
       v4 full_system       — v2 + v3 + learning loop (the full GOAL engine)
  2. computes each sleeve's REALIZED paper return since its previous decision
     (weights held x actual asset returns over the gap) — closing the loop so the
     ledger accumulates honest, forward, survivorship-free performance per sleeve;
  3. appends one SHADOW row per sleeve to the ledger (never live capital);
  4. emits a single machine-readable `SHADOW_SUMMARY=` JSON line for n8n.

    python -m experiments.run_all_shadow --log results/shadow_ledger.jsonl
    python -m experiments.run_all_shadow --quick           # small universes, fast

Designed to be invoked daily by n8n/cron on an always-on host (see
docs/DEPLOY_DIGITALOCEAN.md). Decision logic only — no order placement.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import warnings

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
warnings.filterwarnings("ignore")

import pandas as pd

from v12.config import ExperimentConfig, BROAD_UNIVERSE, CRYPTO_UNIVERSE, CRYPTO_BENCHMARK
from v12.data import load_prices
from v12.strategies import build_full_system, build_validated_sleeve, all_decisions
from v12.strategies.validated_sleeve import SLEEVE_NAME as V1
from v12.strategies.stock_sleeve import SLEEVE_NAME as V2
from v12.strategies.crypto_sleeve import SLEEVE_NAME as V3
from v12.strategies.full_system import SYSTEM_SLEEVE as V4
from v12.execution import DecisionEngine
from v12.execution.ledger import ShadowLedger
from v12.utils import get_logger

log = get_logger("shadow")

SMALL_STOCKS = ["AAPL", "MSFT", "NVDA", "JPM", "XOM", "JNJ", "PG", "KO"]
SMALL_CRYPTO = ["BTC-USD", "ETH-USD", "SOL-USD", "XRP-USD", "ADA-USD", "DOGE-USD"]


def _prev_rows(path: str):
    """Last logged row per sleeve -> (date, {asset: target_weight})."""
    out = {}
    if not os.path.exists(path):
        return out
    for line in open(path):
        line = line.strip()
        if not line:
            continue
        r = json.loads(line)
        tgt = {d["asset"]: d.get("target_weight", 0.0) for d in r.get("decisions", [])
               if d.get("target_weight", 0.0) > 0}
        out[r["sleeve"]] = (r["date"], tgt)
    return out


def _realized_return(prev_targets, prev_date, today, close: pd.DataFrame) -> float:
    """Weighted realized return of yesterday's book over the gap (cash earns 0)."""
    if not prev_targets:
        return 0.0
    try:
        d0 = pd.to_datetime(prev_date)
    except Exception:
        return 0.0
    if d0 >= today:
        return 0.0
    total = 0.0
    for a, w in prev_targets.items():
        if a not in close.columns:
            continue
        s = close[a].dropna()
        if s.empty:
            continue
        p0 = s.asof(d0)
        p1 = s.asof(today)
        if p0 and p1 and p0 > 0:
            total += w * (p1 / p0 - 1.0)
    return float(total)


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--end", default="2026-06-20")
    p.add_argument("--log", default="results/shadow_ledger.jsonl")
    p.add_argument("--quick", action="store_true", help="small universes for a fast smoke run")
    args = p.parse_args()

    stocks = SMALL_STOCKS if args.quick else list(BROAD_UNIVERSE)
    crypto = SMALL_CRYPTO if args.quick else list(CRYPTO_UNIVERSE)

    # previous decisions (for realized-return attribution) BEFORE we write new rows
    prev = _prev_rows(args.log)

    # build everything; full_system reads prior performance for the learning loop
    # but does NOT write (we do the realized-return logging here)
    sysres = build_full_system(end=args.end, stock_universe=stocks, crypto_universe=crypto,
                               read_log_path=args.log, log_path=None)
    v1 = build_validated_sleeve(end=args.end, universe=stocks, log_path=None)

    # price panels for realized-return lookup (cached from the builds above)
    scfg = ExperimentConfig(name="rr_s"); scfg.data.universe = stocks
    scfg.data.start, scfg.data.end = "2015-01-01", args.end
    ccfg = ExperimentConfig(name="rr_c"); ccfg.data.universe = crypto
    ccfg.data.benchmark = CRYPTO_BENCHMARK; ccfg.data.rs_refs = [CRYPTO_BENCHMARK]
    ccfg.data.start, ccfg.data.end = "2018-01-01", args.end
    close = pd.concat([load_prices(scfg.data).close, load_prices(ccfg.data).close], axis=1)
    close = close.loc[:, ~close.columns.duplicated()]

    # uniform sleeve table: (name, date, targets, decisions, regime, exposure)
    v4_dec = [d for d in all_decisions(sysres) if d.asset in sysres.combined_targets]
    table = [
        (V1, v1.date, v1.targets, v1.decisions, v1.regime, sum(v1.targets.values())),
        (V2, sysres.stock.date, sysres.stock.targets, sysres.stock.decisions,
         sysres.stock.regime, sum(sysres.stock.targets.values())),
        (V3, sysres.crypto.date, sysres.crypto.targets, sysres.crypto.decisions,
         sysres.crypto.regime, sum(sysres.crypto.targets.values())),
        (V4, sysres.date, sysres.combined_targets, v4_dec,
         f"stk:{sysres.stock.regime}/cry:{sysres.crypto.regime}", sysres.total_exposure),
    ]

    led = ShadowLedger(args.log)
    summary = {"date": f"{sysres.date:%Y-%m-%d}", "learning_active": sysres.learning_active,
               "sleeves": {}}
    for name, date, targets, decisions, regime, expo in table:
        pdate, ptgt = prev.get(name, (None, {}))
        day_ret = _realized_return(ptgt, pdate, pd.Timestamp(date), close) if pdate else None
        led.log(date=f"{date:%Y-%m-%d}", sleeve=name, status="shadow",
                decisions=DecisionEngine.to_records(decisions), day_return=day_ret)
        perf = led.rolling_performance(name)
        summary["sleeves"][name] = {
            "regime": regime, "exposure": round(float(expo), 4),
            "n_positions": int(sum(1 for w in targets.values() if w > 0)),
            "day_return": day_ret, "roll_sharpe": perf.get("sharpe"),
            "roll_cum": perf.get("cum_return"), "n_days": perf.get("n_days", 0),
        }

    print(f"\n=== SHADOW HORSE-RACE {summary['date']} "
          f"(learning {'ON' if sysres.learning_active else 'cold start'}) ===")
    print(f"{'SLEEVE':18} {'REGIME':22} {'EXPO':>6} {'POS':>4} {'DAYRET':>8} {'SHARPE':>7} {'DAYS':>5}")
    for name, s in summary["sleeves"].items():
        dr = "n/a" if s["day_return"] is None else f"{s['day_return']*100:+.2f}%"
        sh = "n/a" if s["roll_sharpe"] is None or s["roll_sharpe"] != s["roll_sharpe"] else f"{s['roll_sharpe']:.2f}"
        print(f"{name:18} {s['regime'][:22]:22} {s['exposure']*100:5.1f}% {s['n_positions']:>4} "
              f"{dr:>8} {sh:>7} {s['n_days']:>5}")
    print("\nSHADOW_SUMMARY=" + json.dumps(summary, default=float))
    log.info("Logged %d shadow sleeves to %s", len(table), args.log)


if __name__ == "__main__":
    main()
