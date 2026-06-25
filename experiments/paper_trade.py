"""Paper-trading decision runner (the shadow-portfolio entrypoint).

Produces the GOAL-required per-decision output for the *current* date using the
validated low-vol strategy, governed by regime + EV + risk rules + graduated
sizing. PAPER ONLY: dry-run by default; pass --live-paper (with Alpaca PAPER
keys in env) to actually place paper orders.

    python -m experiments.paper_trade                 # dry-run decision report
    ALPACA_KEY=.. ALPACA_SECRET=.. python -m experiments.paper_trade --live-paper

This is NOT connected to real money — the adapter hard-blocks non-paper endpoints.
"""
from __future__ import annotations

import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import warnings
warnings.filterwarnings("ignore")

from v12.config import ExperimentConfig, BROAD_UNIVERSE
from v12.data import load_prices
from v12.features import build_dataset
from v12.evaluation.factor_analytics import select_features
from v12.models import build_model
from v12.regime import classify_regime
from v12.execution import DecisionEngine
from v12.utils import get_logger

log = get_logger("paper")


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--live-paper", action="store_true", help="place orders on Alpaca PAPER account")
    p.add_argument("--equity", type=float, default=500.0, help="paper account notional for sizing")
    p.add_argument("--end", default="2026-06-20")
    args = p.parse_args()

    cfg = ExperimentConfig(name="paper")
    cfg.data.universe = list(BROAD_UNIVERSE)
    cfg.data.start, cfg.data.end = "2015-01-01", args.end
    cfg.features.target_horizon = 60
    cfg.features.sector_neutral = True
    cfg.__post_init__()

    data = load_prices(cfg.data)
    panel, feats = build_dataset(data, cfg.features, cfg.data)
    feats = select_features(panel, feats, ["volatility", "cross_sectional"], prune_corr=0.9)
    panel = panel[feats + ["target"]]

    # train on all labelled history, score the most recent date
    labelled = panel.dropna(subset=["target"])
    model = build_model("elasticnet", cfg.models.random_state)
    model.fit(labelled[feats].values, labelled["target"].values)

    last_date = panel.index.get_level_values("date").max()
    today = panel.xs(last_date, level="date")
    import pandas as pd
    scores = pd.Series(model.predict(today[feats].values), index=today.index)

    reg = classify_regime(data.close[cfg.data.benchmark])
    risk_on = bool(reg["risk_on"].reindex([last_date]).fillna(0).iloc[0])

    eng = DecisionEngine(max_weight=cfg.backtest.max_weight,
                         top_quantile=cfg.backtest.top_quantile)
    # governor_exposure=1.0 for a cold snapshot; the live loop maintains it from NAV
    decisions = eng.decide(scores, regime_risk_on=risk_on, governor_exposure=1.0)

    print(f"\n=== PAPER DECISIONS for {last_date:%Y-%m-%d} "
          f"(regime risk_on={risk_on}) ===")
    print(f"{'ASSET':6} {'ACTION':9} {'EV':>8} {'CONF':>5} {'SIZE':>6}  REASON")
    actives = [d for d in decisions if d.target_weight > 0 or d.action not in ("NO TRADE",)]
    for d in sorted(decisions, key=lambda x: -x.target_weight):
        if d.target_weight == 0 and d.action == "NO TRADE":
            continue
        print(f"{d.asset:6} {d.action:9} {d.ev_score:>8.4f} {d.confidence:>5.0f} "
              f"{d.target_weight*100:>5.1f}%  {d.reasoning}")
    n_buys = sum(d.target_weight > 0 for d in decisions)
    print(f"\n{n_buys} positions targeted; rest CASH. Sources: price+volatility (validated).")
    if not risk_on:
        print("Regime risk-off -> system holds CASH (capital preservation).")

    targets = {d.asset: d.target_weight for d in decisions if d.target_weight > 0}
    if args.live_paper:
        from v12.execution.alpaca_adapter import AlpacaPaperAdapter
        adapter = AlpacaPaperAdapter(api_key=os.environ.get("ALPACA_KEY"),
                                     secret_key=os.environ.get("ALPACA_SECRET"),
                                     dry_run=False)
        eq = adapter.account_equity() or args.equity
        recs = adapter.submit_target_weights(targets, eq)
        log.info("Submitted %d paper targets (equity $%.2f).", len(recs), eq)
    else:
        log.info("Dry-run only. Re-run with --live-paper + Alpaca PAPER keys to execute.")


if __name__ == "__main__":
    main()
