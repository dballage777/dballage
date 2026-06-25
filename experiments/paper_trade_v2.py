"""Variant 2 runner — full GOAL-conditioned STOCK sleeve (shadow paper).

Produces the GOAL-required per-decision output for the latest date using the
*complete* GOAL stock pipeline (full universe, multi-horizon blend, 6-state
regime exposure, fractional Kelly, EV gate, correlation check, graduated
sizing, per-position + asset-class + microcap caps). Logged as a SHADOW sleeve
to the paper ledger — never allocated capital until it passes its gate.

    python -m experiments.paper_trade_v2
    python -m experiments.paper_trade_v2 --end 2026-06-20 --log results/shadow_ledger.jsonl

This is NOT connected to money or to order placement — decision logic only.
"""
from __future__ import annotations

import argparse
import os
import sys
import warnings

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
warnings.filterwarnings("ignore")

from v12.strategies import build_stock_sleeve
from v12.utils import get_logger

log = get_logger("paper_v2")


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--end", default="2026-06-20")
    p.add_argument("--log", default=None,
                   help="shadow-ledger path to append this run (e.g. results/shadow_ledger.jsonl)")
    args = p.parse_args()

    res = build_stock_sleeve(end=args.end, log_path=args.log)

    print(f"\n=== VARIANT 2 — FULL GOAL STOCK SLEEVE (SHADOW) for {res.date:%Y-%m-%d} ===")
    print(f"regime          : {res.regime}  (exposure weight {res.regime_exposure:.2f})")
    print(f"kelly mult      : {res.kelly_mult:.2f}  (25% fractional cap)")
    print(f"governor expo.  : {res.governor_exposure:.2f}  (regime x kelly)")
    print(f"corr overload   : {res.corr_flag}")
    print(f"stock exposure  : {res.stock_exposure*100:.1f}%  (cap 70%)  | rest CASH")
    print("-" * 72)
    print(f"{'ASSET':6} {'ACTION':9} {'EV':>8} {'CONF':>5} {'SIZE':>6}  REASON")
    for d in sorted(res.decisions, key=lambda x: -x.target_weight):
        if d.target_weight == 0 and d.action == "NO TRADE":
            continue
        print(f"{d.asset:6} {d.action:9} {d.ev_score:>8.4f} {d.confidence:>5.0f} "
              f"{d.target_weight*100:>5.1f}%  {d.reasoning}")
    print("-" * 72)
    print(f"{res.n_positions} positions targeted; rest CASH. Sources: {res.sources}.")
    if res.regime_exposure == 0:
        print(f"Regime '{res.regime}' -> exposure 0 -> system holds CASH (capital preservation).")
    if args.log:
        log.info("Logged SHADOW sleeve run to %s", args.log)
    else:
        log.info("Dry decision only. Pass --log results/shadow_ledger.jsonl to record the shadow run.")


if __name__ == "__main__":
    main()
