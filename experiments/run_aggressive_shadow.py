"""HIGH-RISK aggressive shadow runner — quarantined, SHADOW / paper only.

Runs the aggressive momentum books ALONGSIDE the 7 paper tests, writing to a
SEPARATE ledger (`paper/aggressive_shadow_ledger.jsonl`) so it can NEVER touch
V1-V7 or their data. Nothing here allocates real capital.

Books logged each run (+ realized paper return since the previous run):
    aggr_stock_mom    — liquid high-beta stock momentum book
    aggr_crypto_mom   — top-liquid-coin momentum book
    aggressive_system — the two combined (total exposure capped at 100%)
    market_ref        — passive 100% SPY, the yardstick

Aggressive but bounded: the hard-risk governor uses LOOSER stops (-30% drawdown /
-8% daily / 3-loss freeze) than the conservative system, but the stops are REAL.

    python -m experiments.run_aggressive_shadow            # live (end=today)
    python -m experiments.run_aggressive_shadow --quick    # small universes, fast
"""
from __future__ import annotations

import argparse
import datetime as _dt
import json
import os
import sys
import warnings

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
warnings.filterwarnings("ignore")

import pandas as pd

from v12.aggressive import (build_aggressive_system, STOCK_BOOK, CRYPTO_BOOK, SYSTEM_BOOK)
from v12.aggressive.sleeve import (all_decisions, AGGR_STOCK_UNIVERSE, AGGR_CRYPTO_UNIVERSE,
                                   AGGR_STOCK_BENCHMARK, AGGR_CRYPTO_BENCHMARK)
from v12.config import ExperimentConfig
from v12.data import load_prices
from v12.execution import DecisionEngine, Decision
from v12.execution.ledger import ShadowLedger
from v12.risk.governor import governor_exposure_from_returns
from v12.utils import get_logger

log = get_logger("aggressive")

MARKET_REF = "market_ref"
# LOOSER aggressive hard stops (still real)
AGGR_MAX_DD = 0.30
AGGR_DAILY_STOP = 0.08

SMALL_STOCKS = ["NVDA", "AMD", "TSLA", "META", "NFLX", "COIN", "PLTR", "SHOP"]
SMALL_CRYPTO = ["BTC-USD", "ETH-USD", "SOL-USD", "XRP-USD", "ADA-USD", "DOGE-USD"]


def _prev_rows(path: str):
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


def _return_history(path: str):
    out = {}
    if not os.path.exists(path):
        return out
    rows = [json.loads(l) for l in open(path) if l.strip()]
    rows.sort(key=lambda r: r.get("date", ""))
    for r in rows:
        dr = r.get("day_return")
        if dr is not None:
            out.setdefault(r["sleeve"], []).append(float(dr))
    return out


def _realized(prev_targets, prev_date, today, close: pd.DataFrame) -> float:
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
        p0, p1 = s.asof(d0), s.asof(today)
        if p0 and p1 and p0 > 0:
            total += w * (p1 / p0 - 1.0)
    return float(total)


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--end", default=None, help="data end date; defaults to today")
    p.add_argument("--log", default="paper/aggressive_shadow_ledger.jsonl")
    p.add_argument("--quick", action="store_true", help="small universes for a fast smoke run")
    args = p.parse_args()
    end = args.end or _dt.date.today().isoformat()

    stocks = SMALL_STOCKS if args.quick else list(AGGR_STOCK_UNIVERSE)
    crypto = SMALL_CRYPTO if args.quick else list(AGGR_CRYPTO_UNIVERSE)

    prev = _prev_rows(args.log)
    hist = _return_history(args.log)
    gov = {name: governor_exposure_from_returns(
                hist.get(name, []), max_drawdown=AGGR_MAX_DD, daily_loss_stop=AGGR_DAILY_STOP)
           for name in (STOCK_BOOK, CRYPTO_BOOK, SYSTEM_BOOK)}

    sysres = build_aggressive_system(end=end, stock_universe=stocks, crypto_universe=crypto,
                                     stock_gov_mult=gov[STOCK_BOOK][0],
                                     crypto_gov_mult=gov[CRYPTO_BOOK][0])

    # close panels for realized-return lookup (+ SPY for the market reference)
    scfg = ExperimentConfig(name="rr_as")
    scfg.data.universe = list(dict.fromkeys(stocks + [AGGR_STOCK_BENCHMARK, "SPY"]))
    scfg.data.extra_benchmarks = []
    scfg.data.start, scfg.data.end = "2015-01-01", end
    ccfg = ExperimentConfig(name="rr_ac")
    ccfg.data.universe = crypto
    ccfg.data.benchmark = AGGR_CRYPTO_BENCHMARK; ccfg.data.rs_refs = [AGGR_CRYPTO_BENCHMARK]
    ccfg.data.extra_benchmarks = []
    ccfg.data.start, ccfg.data.end = "2018-01-01", end
    close = pd.concat([load_prices(scfg.data).close, load_prices(ccfg.data).close], axis=1)
    close = close.loc[:, ~close.columns.duplicated()]

    date = sysres.date
    sys_dec = [d for d in all_decisions(sysres) if d.asset in sysres.combined_targets]
    table = [
        (STOCK_BOOK, sysres.stock.date, sysres.stock.targets, sysres.stock.decisions,
         sysres.stock.regime, sysres.stock.exposure),
        (CRYPTO_BOOK, sysres.crypto.date, sysres.crypto.targets, sysres.crypto.decisions,
         sysres.crypto.regime, sysres.crypto.exposure),
        (SYSTEM_BOOK, date, sysres.combined_targets, sys_dec,
         f"stk:{sysres.stock.regime}/cry:{sysres.crypto.regime}", sysres.total_exposure),
    ]
    # passive SPY reference row
    if "SPY" in close.columns and not close["SPY"].dropna().empty:
        bd = pd.Timestamp(close["SPY"].dropna().index.max())
        ref_dec = [Decision("SPY", "BUY", 0.0, "LOW", 100.0, 1.0,
                            "passive buy-and-hold market reference", "SPY close")]
        table.append((MARKET_REF, bd, {"SPY": 1.0}, ref_dec, "buy&hold", 1.0))

    led = ShadowLedger(args.log)
    summary = {"date": f"{date:%Y-%m-%d}", "logged": 0, "skipped": 0, "books": {}}
    for name, d, targets, decisions, regime, expo in table:
        pdate, ptgt = prev.get(name, (None, {}))
        is_new = pdate is None or pd.Timestamp(d) > pd.Timestamp(pdate)
        if is_new:
            day_ret = _realized(ptgt, pdate, pd.Timestamp(d), close) if pdate else None
            led.log(date=f"{d:%Y-%m-%d}", sleeve=name, status="shadow",
                    decisions=DecisionEngine.to_records(decisions), day_return=day_ret)
            summary["logged"] += 1
        else:
            day_ret = None
            summary["skipped"] += 1
        perf = led.rolling_performance(name)
        gov_exp, gov_reason = gov.get(name, (1.0, "ok"))
        summary["books"][name] = {
            "regime": regime, "exposure": round(float(expo), 4),
            "n_positions": int(sum(1 for w in targets.values() if w > 0)),
            "day_return": day_ret, "roll_sharpe": perf.get("sharpe"),
            "n_days": perf.get("n_days", 0),
            "risk_governor": ("ACTIVE: " + gov_reason) if gov_exp == 0.0 else "ok"}

    print(f"\n=== AGGRESSIVE SHADOW {summary['date']} (HIGH-RISK, paper only) ===")
    print(f"{'BOOK':18} {'REGIME':22} {'EXPO':>6} {'POS':>4} {'DAYRET':>8} {'SHARPE':>7} {'DAYS':>5}")
    for name, s in summary["books"].items():
        dr = "n/a" if s["day_return"] is None else f"{s['day_return']*100:+.2f}%"
        sh = ("n/a" if s["roll_sharpe"] is None or s["roll_sharpe"] != s["roll_sharpe"]
              else f"{s['roll_sharpe']:.2f}")
        print(f"{name:18} {s['regime'][:22]:22} {s['exposure']*100:5.1f}% {s['n_positions']:>4} "
              f"{dr:>8} {sh:>7} {s['n_days']:>5}")
    print("\nAGGRESSIVE_SUMMARY=" + json.dumps(summary, default=float))
    log.info("Aggressive shadow: logged %d, skipped %d", summary["logged"], summary["skipped"])


if __name__ == "__main__":
    main()
