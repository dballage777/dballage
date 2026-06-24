"""Thin CLI wrapper for automation (n8n / cron / CI).

Emits a single-line JSON summary on stdout so n8n's "Execute Command" node can
parse the result, compare versions, and trigger alerts/retraining.

    python automation/run_backtest_cli.py --name nightly --dca dca
"""
from __future__ import annotations

import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from v12.config import ExperimentConfig
from experiments.run_experiment import run


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--name", default="nightly")
    p.add_argument("--dca", choices=["none", "dca", "variable"], default="dca")
    p.add_argument("--quick", action="store_true")
    args = p.parse_args()

    cfg = ExperimentConfig(name=args.name)
    cfg.backtest.dca_mode = args.dca
    if args.quick:
        cfg.data.start, cfg.data.end = "2019-01-01", "2024-01-01"
        cfg.validation.n_splits = 3
        cfg.validation.train_min_days = 252
        cfg.models.candidates = ["ridge", "lgbm"]

    ctx = run(cfg)
    summary = {
        "name": cfg.name,
        "data_source": ctx["data_source"],
        "ic_mean": ctx["ic"]["ic_mean"],
        "strategy_sharpe": ctx["strategy_perf"]["sharpe"],
        "spy_sharpe": ctx["spy_perf"]["sharpe"],
        "strategy_final": ctx["strategy_final"],
        "spy_final": ctx["spy_final"],
        "mc_stability": ctx["monte_carlo"]["mc_stability"],
        "beat_spy": ctx["strategy_perf"]["sharpe"] > ctx["spy_perf"]["sharpe"]
        and ctx["strategy_final"] > ctx["spy_final"],
    }
    # machine-readable line for n8n to parse (prefixed for easy extraction)
    print("V12_SUMMARY=" + json.dumps(summary, default=float))


if __name__ == "__main__":
    main()
