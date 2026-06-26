"""Variant 4 runner — the FULL SYSTEM (stocks + crypto + learning loop), shadow.

Combines the variant-2 stock sleeve and variant-3 crypto sleeve under the GOAL
capital structure (stocks <= 70% + crypto <= 30%, remainder CASH), applies the
learning loop (reweight by realized paper Sharpe), and prints one unified
decision report. SHADOW only — logged and tracked, never allocated capital.

    python -m experiments.paper_trade_v4
    python -m experiments.paper_trade_v4 --end 2026-06-20 --log results/shadow_ledger.jsonl
"""
from __future__ import annotations

import argparse
import os
import sys
import warnings

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
warnings.filterwarnings("ignore")

from v12.strategies import build_full_system, all_decisions
from v12.utils import get_logger

log = get_logger("paper_v4")


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--end", default="2026-06-20")
    p.add_argument("--log", default=None,
                   help="shadow-ledger path to append this run (e.g. results/shadow_ledger.jsonl)")
    args = p.parse_args()

    res = build_full_system(end=args.end, log_path=args.log)

    print(f"\n=== VARIANT 4 — FULL SYSTEM (SHADOW) for {res.date:%Y-%m-%d} ===")
    print(f"stock book   : regime {res.stock.regime:9} expo {res.stock.governor_exposure:.2f}")
    print(f"crypto book  : regime {res.crypto.regime:9} expo {res.crypto.governor_exposure:.2f} (BTC)")
    lw = res.learn_weights
    print(f"learning loop: {'ACTIVE' if res.learning_active else 'cold start (no tilt)'}  "
          f"weights stocks={lw.get('equity_full_goal', 0):.2f} crypto={lw.get('crypto_full_goal', 0):.2f}  "
          f"-> mult stocks={res.multipliers['equity_full_goal']:.2f} crypto={res.multipliers['crypto_full_goal']:.2f}")
    print("-" * 74)
    print(f"CAPITAL STRUCTURE:  stocks {res.stock_exposure*100:5.1f}% (cap 70%) | "
          f"crypto {res.crypto_exposure*100:5.1f}% (cap 30%) | CASH {res.cash*100:5.1f}%")
    print("-" * 74)
    print(f"{'ASSET':10} {'ACTION':9} {'EV':>8} {'CONF':>5} {'SIZE':>6}  REASON")
    rows = [(a, w) for a, w in res.combined_targets.items()]
    decs = {d.asset: d for d in all_decisions(res)}
    for a, w in sorted(rows, key=lambda x: -x[1]):
        d = decs.get(a)
        if d is None:
            continue
        print(f"{a:10} {d.action:9} {d.ev_score:>8.4f} {d.confidence:>5.0f} "
              f"{w*100:>5.1f}%  {d.reasoning}")
    print("-" * 74)
    n = len(res.combined_targets)
    print(f"{n} positions targeted ({sum(not k.endswith('-USD') for k in res.combined_targets)} stocks, "
          f"{sum(k.endswith('-USD') for k in res.combined_targets)} crypto); rest CASH.")
    if args.log:
        log.info("Logged SHADOW full-system run to %s", args.log)
    else:
        log.info("Dry decision only. Pass --log results/shadow_ledger.jsonl to record the shadow run.")


if __name__ == "__main__":
    main()
