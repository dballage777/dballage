"""Print + write the shadow horse-race standings and weekly/monthly rollups.

    python -m experiments.standings                       # reads paper/shadow_ledger.jsonl
    python -m experiments.standings --log results/shadow_ledger.jsonl

Pure aggregation of the ledger — run it any time to see the scoreboard. Writes
paper/reports/STANDINGS.md (always the latest), which the daily Action commits.
"""
from __future__ import annotations

import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from v12.execution.ledger import ShadowLedger
from v12.reporting.standings import render_standings


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--log", default="paper/shadow_ledger.jsonl")
    p.add_argument("--out", default="paper/reports")
    args = p.parse_args()

    df = ShadowLedger(args.log).load()
    md = render_standings(df)
    print(md)

    os.makedirs(args.out, exist_ok=True)
    path = os.path.join(args.out, "STANDINGS.md")
    with open(path, "w") as f:
        f.write(md)
    print(f"-> {path}")


if __name__ == "__main__":
    main()
