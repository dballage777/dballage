"""Shadow horse-race runner — runs ALL paper variants once and records them.

This is the engine of the 90-180 day forward paper test. On each (daily) run it:

  1. builds all variants for the latest date:
       v1 equity_validated  — the validated low-vol baseline (control arm)
       v2 equity_full_goal  — stocks + all GOAL conditions
       v3 crypto_full_goal  — crypto + all GOAL conditions
       v4 full_system       — v2 + v3 + learning loop (the full GOAL engine)
       v5 full_system_max   — v4 + all available SEC data (fundamentals [+insider])
       v6 full_system_v6    — v5 + a precious-metals book, revised caps
       vM metals_full_goal  — the standalone precious-metals book (feeds v6)
       v7 bonds_full_goal   — the standalone IG fixed-income book
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
import datetime as _dt
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
from v12.strategies.full_system import SYSTEM_SLEEVE as V4, all_decisions as _alldec
from v12.strategies.metals_sleeve import SLEEVE_NAME as VM
from v12.strategies.bonds_sleeve import build_bonds_sleeve, SLEEVE_NAME as V7
from v12.strategies.full_system_v6 import (build_full_system_v6, all_decisions_v6,
                                           SYSTEM6_SLEEVE as V6)
from v12.config import METALS_UNIVERSE, METALS_BENCHMARK, BONDS_UNIVERSE, BONDS_BENCHMARK
from v12.execution import DecisionEngine

V5 = "full_system_max"        # variant 5: full system + all AVAILABLE SEC data sources
from v12.execution.ledger import ShadowLedger
from v12.risk.governor import governor_exposure_from_returns
from v12.utils import get_logger

log = get_logger("shadow")

SMALL_STOCKS = ["AAPL", "MSFT", "NVDA", "JPM", "XOM", "JNJ", "PG", "KO"]
SMALL_CRYPTO = ["BTC-USD", "ETH-USD", "SOL-USD", "XRP-USD", "ADA-USD", "DOGE-USD"]
SMALL_METALS = ["GLD", "SLV", "PPLT", "PALL"]
SMALL_BONDS = ["AGG", "IEF", "SHY", "LQD"]


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


def _sleeve_return_history(path: str):
    """Per-sleeve ordered list of realized day_returns from the ledger."""
    out = {}
    if not os.path.exists(path):
        return out
    rows = []
    for line in open(path):
        line = line.strip()
        if line:
            rows.append(json.loads(line))
    rows.sort(key=lambda r: r.get("date", ""))
    for r in rows:
        dr = r.get("day_return")
        if dr is not None:
            out.setdefault(r["sleeve"], []).append(float(dr))
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
    p.add_argument("--end", default=None, help="data end date; defaults to today (live)")
    p.add_argument("--log", default="results/shadow_ledger.jsonl")
    p.add_argument("--quick", action="store_true", help="small universes for a fast smoke run")
    p.add_argument("--no-max", action="store_true", help="skip variant 5 (full_system_max)")
    p.add_argument("--no-metals", action="store_true", help="skip variant 6 (full_system_v6)")
    p.add_argument("--no-bonds", action="store_true", help="skip variant 7 (bonds_full_goal)")
    p.add_argument("--with-insider", action="store_true",
                   help="variants 5/6 also pull SEC insider data (heavy; best in Codespace)")
    args = p.parse_args()
    end = args.end or _dt.date.today().isoformat()      # live: advance with the calendar
    want_v5 = not args.no_max
    want_v6 = not args.no_metals
    want_v7 = not args.no_bonds
    v5_insider = args.with_insider or os.environ.get("SHADOW_V5_INSIDER") == "1"

    stocks = SMALL_STOCKS if args.quick else list(BROAD_UNIVERSE)
    crypto = SMALL_CRYPTO if args.quick else list(CRYPTO_UNIVERSE)
    metals = SMALL_METALS if args.quick else list(METALS_UNIVERSE)
    bonds = SMALL_BONDS if args.quick else list(BONDS_UNIVERSE)

    # previous decisions (for realized-return attribution) BEFORE we write new rows
    prev = _prev_rows(args.log)

    # ---- live hard-risk governor: replay each sleeve's realized-return history
    # (drawdown kill-switch / daily-loss stop / 3-consecutive-loss freeze). 0.0 =>
    # circuit-breaker active => that sleeve goes to cash today. ----
    hist = _sleeve_return_history(args.log)
    gov = {name: governor_exposure_from_returns(hist.get(name, []))
           for name in (V1, V2, V3, V4, V5, VM, V6, V7)}

    # build everything; full_system reads prior performance for the learning loop
    # but does NOT write (we do the realized-return logging here)
    sysres = build_full_system(end=end, stock_universe=stocks, crypto_universe=crypto,
                               read_log_path=args.log, log_path=None,
                               stock_gov_mult=gov[V2][0], crypto_gov_mult=gov[V3][0],
                               system_gov_mult=gov[V4][0])
    v1 = build_validated_sleeve(end=end, universe=stocks, log_path=None,
                                risk_gov_mult=gov[V1][0])

    # ---- variant 5: full system + ALL available SEC data (fundamentals [+insider]).
    # reuses variant 4's crypto book (identical) and only rebuilds the stock book
    # with the extra data. Degrades gracefully if SEC data can't be fetched. ----
    v5 = None
    if want_v5:
        v5 = build_full_system(end=end, stock_universe=stocks, crypto_universe=crypto,
                               read_log_path=args.log, log_path=None,
                               system_gov_mult=gov[V5][0],
                               use_fundamentals=True, use_insider=v5_insider,
                               reuse_crypto=sysres.crypto)

    # ---- variant 6: variant 5 + a precious-metals book, under revised caps
    # (stocks <=65% + metals <=15% + crypto <=20%). Reuses v5's SEC stock book and
    # variant 4's crypto book; only the metals book is new. ----
    v6 = None
    if want_v6:
        v6 = build_full_system_v6(
            end=end, stock_universe=stocks, crypto_universe=crypto, metals_universe=metals,
            read_log_path=args.log,
            stock_gov_mult=gov[V2][0], crypto_gov_mult=gov[V3][0],
            metals_gov_mult=gov[VM][0], system_gov_mult=gov[V6][0],
            use_fundamentals=True, use_insider=v5_insider,
            reuse_stock=(v5.stock if v5 is not None else None),
            reuse_crypto=sysres.crypto)

    # ---- variant 7: standalone bonds book (IG fixed income, <=40% class cap).
    # Same GOAL machinery as the metals book; own row + own realized-return track.
    # SHADOW only until it passes the forward test + validation gate. ----
    v7 = None
    if want_v7:
        v7 = build_bonds_sleeve(end=end, universe=bonds, log_path=None,
                                risk_gov_mult=gov[V7][0])

    # price panels for realized-return lookup (cached from the builds above)
    scfg = ExperimentConfig(name="rr_s"); scfg.data.universe = stocks
    scfg.data.start, scfg.data.end = "2015-01-01", end
    ccfg = ExperimentConfig(name="rr_c"); ccfg.data.universe = crypto
    ccfg.data.benchmark = CRYPTO_BENCHMARK; ccfg.data.rs_refs = [CRYPTO_BENCHMARK]
    ccfg.data.start, ccfg.data.end = "2018-01-01", end
    panels = [load_prices(scfg.data).close, load_prices(ccfg.data).close]
    if want_v6:
        mcfg = ExperimentConfig(name="rr_m"); mcfg.data.universe = metals
        mcfg.data.benchmark = METALS_BENCHMARK; mcfg.data.rs_refs = [METALS_BENCHMARK]
        mcfg.data.start, mcfg.data.end = "2010-01-01", end
        panels.append(load_prices(mcfg.data).close)
    if want_v7:
        bcfg = ExperimentConfig(name="rr_b"); bcfg.data.universe = bonds
        bcfg.data.benchmark = BONDS_BENCHMARK; bcfg.data.rs_refs = [BONDS_BENCHMARK]
        bcfg.data.start, bcfg.data.end = "2010-01-01", end
        panels.append(load_prices(bcfg.data).close)
    close = pd.concat(panels, axis=1)
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
    if v5 is not None:
        v5_dec = [d for d in _alldec(v5) if d.asset in v5.combined_targets]
        table.append((V5, v5.date, v5.combined_targets, v5_dec,
                      f"stk:{v5.stock.regime}/cry:{v5.crypto.regime}", v5.total_exposure))
    if v6 is not None:
        # the new metals book (its own row) + the combined variant-6 portfolio
        table.append((VM, v6.metals.date, v6.metals.targets, v6.metals.decisions,
                      v6.metals.regime, sum(v6.metals.targets.values())))
        v6_dec = [d for d in all_decisions_v6(v6) if d.asset in v6.combined_targets]
        table.append((V6, v6.date, v6.combined_targets, v6_dec,
                      f"stk:{v6.stock.regime}/met:{v6.metals.regime}/cry:{v6.crypto.regime}",
                      v6.total_exposure))
    if v7 is not None:
        table.append((V7, v7.date, v7.targets, v7.decisions,
                      v7.regime, sum(v7.targets.values())))

    led = ShadowLedger(args.log)
    summary = {"date": f"{sysres.date:%Y-%m-%d}", "learning_active": sysres.learning_active,
               "sleeves": {}, "logged": 0, "skipped": 0}
    for name, date, targets, decisions, regime, expo in table:
        pdate, ptgt = prev.get(name, (None, {}))
        # Idempotent per scoring date: only log if this decision date is NEWER than
        # the sleeve's last logged date. Re-running the same day (manual + scheduled,
        # or a market-closed day) must not append a duplicate row that pollutes the
        # realized-return series with a spurious 0-return entry.
        is_new = pdate is None or pd.Timestamp(date) > pd.Timestamp(pdate)
        if is_new:
            day_ret = _realized_return(ptgt, pdate, pd.Timestamp(date), close) if pdate else None
            led.log(date=f"{date:%Y-%m-%d}", sleeve=name, status="shadow",
                    decisions=DecisionEngine.to_records(decisions), day_return=day_ret)
            summary["logged"] += 1
        else:
            day_ret = None                       # already have this date — skip, no dup
            summary["skipped"] += 1
        perf = led.rolling_performance(name)
        gov_exp, gov_reason = gov.get(name, (1.0, "ok"))
        summary["sleeves"][name] = {
            "regime": regime, "exposure": round(float(expo), 4),
            "n_positions": int(sum(1 for w in targets.values() if w > 0)),
            "day_return": day_ret, "logged": is_new, "roll_sharpe": perf.get("sharpe"),
            "roll_cum": perf.get("cum_return"), "n_days": perf.get("n_days", 0),
            "risk_governor": ("ACTIVE: " + gov_reason) if gov_exp == 0.0 else "ok",
        }
        if gov_exp == 0.0:
            log.info("%s: hard-risk governor ACTIVE (%s) -> forced to CASH.", name, gov_reason)
    if summary["skipped"]:
        log.info("%d sleeve(s) already logged for their latest date — skipped (idempotent).",
                 summary["skipped"])

    print(f"\n=== SHADOW HORSE-RACE {summary['date']} "
          f"(learning {'ON' if sysres.learning_active else 'cold start'}) ===")
    print(f"{'SLEEVE':18} {'REGIME':22} {'EXPO':>6} {'POS':>4} {'DAYRET':>8} {'SHARPE':>7} {'DAYS':>5}")
    for name, s in summary["sleeves"].items():
        dr = "n/a" if s["day_return"] is None else f"{s['day_return']*100:+.2f}%"
        sh = "n/a" if s["roll_sharpe"] is None or s["roll_sharpe"] != s["roll_sharpe"] else f"{s['roll_sharpe']:.2f}"
        print(f"{name:18} {s['regime'][:22]:22} {s['exposure']*100:5.1f}% {s['n_positions']:>4} "
              f"{dr:>8} {sh:>7} {s['n_days']:>5}")
    print("\nSHADOW_SUMMARY=" + json.dumps(summary, default=float))
    log.info("Logged %d new sleeve row(s) (%d skipped, already current) to %s",
             summary["logged"], summary["skipped"], args.log)


if __name__ == "__main__":
    main()
