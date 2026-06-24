"""Run one full agentic research cycle (ResearchAgent ... DeploymentAgent).

    python -m experiments.run_research_cycle
    python -m experiments.run_research_cycle --quick
"""
from __future__ import annotations

import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from v12.config import ExperimentConfig
from v12.agents import run_research_cycle


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--quick", action="store_true")
    p.add_argument("--name", default="v12_cycle")
    args = p.parse_args()

    cfg = ExperimentConfig(name=args.name)
    if args.quick:
        cfg.data.start, cfg.data.end = "2019-01-01", "2024-01-01"
        cfg.validation.n_splits = 3
        cfg.validation.train_min_days = 252
        cfg.models.candidates = ["ridge", "lgbm"]

    state = run_research_cycle(cfg)
    print("\n" + "=" * 60)
    print("HYPOTHESES:")
    for h in state.get("hypotheses", []):
        print("  -", h)
    print("\nEVALUATION:", state.get("evaluation"))
    print("RISK FLAGS:", state.get("risk_flags"))
    print("DECISION:", state.get("deployment_decision"))
    print("=" * 60)


if __name__ == "__main__":
    main()
