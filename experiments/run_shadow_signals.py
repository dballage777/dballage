"""Concurrent SHADOW-SIGNAL runner — the three P0 observe-only shadows (S1/S2/S6).

Runs ALONGSIDE the existing 7-paper-test horse-race, writing to a SEPARATE ledger
(`paper/signal_shadow_ledger.jsonl`) so it can never touch V1-V7 or their data.
Nothing here allocates capital; every output is a recorded suggestion or alarm.

  S2 vrp_timer     — variance-risk-premium equity exposure timer
  S1 regime_timer  — composite cross-market regime exposure timer
  (market_ref)     — passive 100% SPY, the yardstick both timers are judged against
  S6 drift_monitor — reads the MAIN ledger READ-ONLY, raises decay/drift alarms

Each timer logs a suggested exposure multiplier; on the next run the realized
market return over the gap is attributed at the PREVIOUS suggestion's multiplier,
so over time the ledger honestly answers: did timing beat staying fully invested?

    python -m experiments.run_shadow_signals            # live (end=today)
    python -m experiments.run_shadow_signals --quick    # small breadth universe
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

from v12.signals import build_vrp_signal, build_regime_layer, VRP_BOOK, REGIME_BOOK
from v12.monitoring import scan_ledger
from v12.execution.ledger import ShadowLedger
from v12.utils import get_logger

log = get_logger("shadow_signals")

MARKET_REF = "market_ref"
DRIFT_BOOK = "drift_monitor"
SMALL_BREADTH = ["AAPL", "MSFT", "NVDA", "JPM", "XOM", "JNJ", "PG", "KO"]


def _prev(path: str):
    """Last logged (date, suggested_mult) per book."""
    out = {}
    if not os.path.exists(path):
        return out
    for line in open(path):
        line = line.strip()
        if not line:
            continue
        r = json.loads(line)
        decs = r.get("decisions", [])
        mult = None
        for d in decs:
            if "suggested_mult" in d:
                mult = float(d["suggested_mult"])
                break
        out[r["sleeve"]] = (r["date"], mult)
    return out


def _gap_return(close: pd.Series, prev_date, today) -> float:
    if close is None or prev_date is None:
        return 0.0
    s = close.dropna()
    try:
        d0 = pd.to_datetime(prev_date)
    except Exception:
        return 0.0
    if d0 >= today:
        return 0.0
    p0, p1 = s.asof(d0), s.asof(today)
    if p0 and p1 and p0 > 0:
        return float(p1 / p0 - 1.0)
    return 0.0


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--end", default=None, help="data end date; defaults to today")
    p.add_argument("--log", default="paper/signal_shadow_ledger.jsonl")
    p.add_argument("--main-log", default="paper/shadow_ledger.jsonl",
                   help="the existing 7-test ledger (read-only, for the drift monitor)")
    p.add_argument("--quick", action="store_true", help="small breadth universe")
    args = p.parse_args()
    end = args.end or _dt.date.today().isoformat()

    prev = _prev(args.log)
    led = ShadowLedger(args.log)

    vrp = build_vrp_signal(end=end)
    breadth_u = SMALL_BREADTH if args.quick else None
    regime = build_regime_layer(end=end, breadth_universe=breadth_u)

    # a shared market series for realized attribution (prefer whichever loaded)
    market = (vrp.market_close if vrp is not None else
              (regime.market_close if regime is not None else None))
    ref_date = None
    if vrp is not None:
        ref_date = vrp.date
    elif regime is not None:
        ref_date = regime.date

    summary = {"date": None, "logged": 0, "skipped": 0, "signals": {}}

    # ---- timers + passive market reference ----
    books = []
    if ref_date is not None and market is not None:
        books.append((MARKET_REF, ref_date, 1.0,
                      [{"asset": "SPY", "suggested_mult": 1.0, "state": "buy&hold",
                        "reasoning": "passive 100% SPY reference",
                        "sources": "SPY close"}]))
    if vrp is not None:
        books.append((VRP_BOOK, vrp.date, vrp.suggested_mult, [vrp.as_record()]))
    if regime is not None:
        books.append((REGIME_BOOK, regime.date, regime.suggested_mult, [regime.as_record()]))

    for name, date, _mult, decisions in books:
        summary["date"] = f"{date:%Y-%m-%d}"
        pdate, pmult = prev.get(name, (None, None))
        is_new = pdate is None or pd.Timestamp(date) > pd.Timestamp(pdate)
        if is_new:
            gap = _gap_return(market, pdate, pd.Timestamp(date)) if pdate else None
            day_ret = (float((pmult if pmult is not None else 1.0) * gap)
                       if gap is not None else None)
            led.log(date=f"{date:%Y-%m-%d}", sleeve=name, status="shadow",
                    decisions=decisions, day_return=day_ret)
            summary["logged"] += 1
        else:
            day_ret = None
            summary["skipped"] += 1
        perf = led.rolling_performance(name)
        summary["signals"][name] = {
            "suggested_mult": decisions[0].get("suggested_mult"),
            "state": decisions[0].get("state"), "day_return": day_ret,
            "roll_sharpe": perf.get("sharpe"), "n_days": perf.get("n_days", 0)}

    # ---- S6 drift/decay guardian: read the MAIN ledger read-only ----
    health = scan_ledger(args.main_log)
    alarms = [h for h in health if h.decay_flag or h.drift_flag]
    if ref_date is not None:
        # log one monitor snapshot per run (idempotent by date)
        pdate, _ = prev.get(DRIFT_BOOK, (None, None))
        if pdate is None or pd.Timestamp(ref_date) > pd.Timestamp(pdate):
            led.log(date=f"{ref_date:%Y-%m-%d}", sleeve=DRIFT_BOOK, status="monitor",
                    decisions=[h.as_record() for h in health], day_return=None)
    summary["drift"] = {"assessed": len(health), "alarms": len(alarms),
                        "flagged": [h.sleeve for h in alarms]}

    # ---- report ----
    print(f"\n=== SHADOW SIGNALS {summary['date']} (observe-only) ===")
    for name, s in summary["signals"].items():
        dr = "n/a" if s["day_return"] is None else f"{s['day_return']*100:+.2f}%"
        sh = ("n/a" if s["roll_sharpe"] is None or s["roll_sharpe"] != s["roll_sharpe"]
              else f"{s['roll_sharpe']:.2f}")
        print(f"  {name:14} mult={str(s['suggested_mult']):>4} "
              f"state={str(s['state']):<9} dayret={dr:>8} sharpe={sh:>6} n={s['n_days']}")
    print(f"  {DRIFT_BOOK:14} assessed={summary['drift']['assessed']} "
          f"alarms={summary['drift']['alarms']} {summary['drift']['flagged']}")
    print("\nSIGNAL_SUMMARY=" + json.dumps(summary, default=float))
    log.info("Signal shadows: logged %d, skipped %d; drift alarms=%d",
             summary["logged"], summary["skipped"], summary["drift"]["alarms"])


if __name__ == "__main__":
    main()
