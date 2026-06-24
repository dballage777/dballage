"""V12 end-to-end experiment runner.

Pipeline:  data -> features -> purged walk-forward -> model comparison
        -> OOS predictions -> backtest (costs+DCA) -> evaluation -> report.

Run:
    python -m experiments.run_experiment                 # default config
    python -m experiments.run_experiment --quick         # fast smoke test
    python -m experiments.run_experiment --dca none      # contribution mode

Designed to run unchanged in GitHub Codespaces and Google Colab. In a
network-restricted environment it transparently falls back to synthetic data
(clearly labelled in the report).
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import warnings

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
warnings.filterwarnings("ignore")

from v12.config import ExperimentConfig
from v12.data import load_prices
from v12.features import build_dataset
from v12.validation import PurgedWalkForward, assert_no_leakage
from v12.models import build_model, StackingEnsemble
from v12.backtest import run_backtest, run_long_short
from v12.evaluation import (performance_summary, information_coefficient,
                            monte_carlo_bootstrap, stress_tests, build_report)
from v12.utils import get_logger

log = get_logger("run")


def _walk_forward_predict(panel, feature_cols, folds, model_name, cfg_models):
    """Return (oos_predictions Series, per-fold IC list, importances dict)."""
    X_all = panel[feature_cols]
    y_all = panel["target"]
    oos = pd.Series(index=panel.index, dtype=float)
    fold_ics, importances = [], np.zeros(len(feature_cols))
    n_imp = 0

    for tr_idx, te_idx, info in folds:
        Xtr, ytr = X_all.iloc[tr_idx].values, y_all.iloc[tr_idx].values
        Xte = X_all.iloc[te_idx].values
        if model_name == "stack":
            # exclude RandomForest from the stack base: it is the runtime
            # bottleneck on small machines and is retrained many times here.
            stack_base = [m for m in cfg_models.candidates if m != "rf"]
            model = StackingEnsemble(stack_base, cfg_models.random_state)
        else:
            model = build_model(model_name, cfg_models.random_state)
        if model is None:
            return None, [], {}
        model.fit(Xtr, ytr)
        preds = model.predict(Xte)
        oos.iloc[te_idx] = preds

        # per-fold rank-IC
        te_panel = panel.iloc[te_idx]
        ic = information_coefficient(
            pd.Series(preds, index=te_panel.index), te_panel["target"])
        fold_ics.append(ic["ic_mean"])

        imp = _extract_importance(model, len(feature_cols))
        if imp is not None:
            importances += imp
            n_imp += 1

    imp_dict = {}
    if n_imp:
        importances /= n_imp
        imp_dict = dict(sorted(zip(feature_cols, importances),
                               key=lambda kv: -abs(kv[1])))
    return oos.dropna(), fold_ics, imp_dict


def _extract_importance(model, n_features):
    est = model
    if hasattr(model, "steps"):
        est = model.steps[-1][1]
    if hasattr(est, "feature_importances_"):
        return np.asarray(est.feature_importances_, dtype=float)
    if hasattr(est, "coef_"):
        return np.abs(np.asarray(est.coef_, dtype=float)).ravel()[:n_features]
    return None


def run(config: ExperimentConfig) -> dict:
    os.makedirs(config.output_dir, exist_ok=True)
    log.info("=== V12 experiment '%s' ===", config.name)

    # 0. Universe + survivorship-bias status
    from v12.data.universe import resolve_universe
    universe, universe_meta = resolve_universe(config.data)
    config.data.universe = universe

    # 1. Data
    data = load_prices(config.data)
    log.info("Loaded %d tickers x %d days (source=%s)",
             len(data.tickers), len(data.dates), data.source)

    # 2. Features
    panel, feature_cols = build_dataset(data, config.features, config.data)
    if len(panel) < 1000:
        log.warning("Very small panel (%d rows) — results will be noisy.", len(panel))

    # 3. Splits + leakage gate
    wf = PurgedWalkForward(
        n_splits=config.validation.n_splits,
        train_min_days=config.validation.train_min_days,
        test_days=config.validation.test_days,
        embargo_days=config.validation.embargo_days,
        horizon=config.features.target_horizon,
        purge=config.validation.purge,
    )
    folds = list(wf.split(panel))
    if not folds:
        raise RuntimeError("No walk-forward folds — widen date range or lower train_min_days.")
    assert_no_leakage(panel, feature_cols, iter(folds), config.features.target_horizon)
    log.info("Leakage checks passed. %d folds.", len(folds))

    # 4. Model comparison (each candidate + stacking)
    candidates = list(config.models.candidates)
    if config.models.use_stacking:
        candidates = candidates + ["stack"]
    results = {}
    for name in candidates:
        oos, fold_ics, imp = _walk_forward_predict(panel, feature_cols, folds, name, config.models)
        if oos is None or len(oos) == 0:
            log.warning("Model '%s' produced no predictions; skipped.", name)
            continue
        mean_ic = float(np.nanmean(fold_ics)) if fold_ics else float("nan")
        results[name] = {"oos": oos, "fold_ics": fold_ics, "mean_ic": mean_ic, "imp": imp}
        log.info("Model %-10s mean OOS rank-IC = %.4f", name, mean_ic)

    if not results:
        raise RuntimeError("No models available. Install xgboost/lightgbm or use sklearn baseline.")
    best = max(results, key=lambda k: (results[k]["mean_ic"]
                                       if results[k]["mean_ic"] == results[k]["mean_ic"] else -9))
    log.info("Best model: %s (IC=%.4f)", best, results[best]["mean_ic"])

    # 5. Backtest with best OOS predictions
    from v12.features.breadth import compute_breadth
    breadth = compute_breadth(data.close[[t for t in config.data.universe
                                          if t in data.close.columns]], config.features.breadth_mas)
    bt = run_backtest(results[best]["oos"], data.close, data.close[config.data.benchmark],
                      config.backtest, breadth=breadth)

    # 5b. Long-short (dollar-neutral) signal probe — nets out survivorship beta
    ls_ret = run_long_short(results[best]["oos"], data.close, config.backtest)
    ls_perf = performance_summary(ls_ret, "long_short")

    # 6. Evaluation
    strat_perf = performance_summary(bt.strategy_returns, "strategy")
    spy_perf = performance_summary(bt.spy_returns, "SPY")
    ic_full = information_coefficient(results[best]["oos"], panel["target"])
    mc = monte_carlo_bootstrap(bt.strategy_returns)
    stress = stress_tests(bt.strategy_returns)

    # 7. Report context
    model_table = "| model | mean OOS rank-IC | folds |\n|---|---|---|\n" + "\n".join(
        f"| {k} | {v['mean_ic']:.4f} | {len(v['fold_ics'])} |"
        for k, v in sorted(results.items(), key=lambda kv: -kv[1]['mean_ic']))
    top_imp = list(results[best]["imp"].items())[:15]
    feature_table = "| feature | importance |\n|---|---|\n" + "\n".join(
        f"| {f} | {imp:.5f} |" for f, imp in top_imp)

    beat = strat_perf["sharpe"] > spy_perf["sharpe"] and bt.strategy_equity.iloc[-1] > bt.spy_equity.iloc[-1]
    failure = _failure_analysis(strat_perf, spy_perf, ic_full, mc, beat, ls_perf,
                                universe_meta["survivorship_safe"])
    nxt = _next_experiment(results, ic_full, beat)

    bias_note = ("✅ " if universe_meta["survivorship_safe"] else "⚠️ ") + universe_meta["note"]

    ls_sharpe = ls_perf["sharpe"]
    if ls_sharpe == ls_sharpe and ls_sharpe >= 0.7 and ls_perf["total_return"] > 0:
        ls_note = ("✅ Long-short spread is **positive after costs** (Sharpe "
                   f"{ls_sharpe:.2f}). Because survivorship lifts long & short legs alike "
                   "and cancels in the spread, this is evidence of genuine cross-sectional "
                   "selection skill — not just owning past winners.")
    elif ls_sharpe == ls_sharpe and ls_sharpe >= 0.3:
        ls_note = (f"➖ Long-short spread is **modest** (Sharpe {ls_sharpe:.2f}). Some real "
                   "selection skill may exist but it is weak once survivorship is netted out.")
    else:
        ls_note = (f"⚠️ Long-short spread is **flat/negative** (Sharpe {ls_sharpe:.2f}). The "
                   "long-only outperformance is most likely **survivorship beta**, not "
                   "selection skill. Do not trust the §4 SPY win.")

    ctx = {
        "data_source": data.source,
        "universe_meta": universe_meta,
        "bias_note": bias_note,
        "changes": _changes_block(config, best),
        "leakage_note": (f"Purged walk-forward with embargo={config.validation.embargo_days}d "
                         f">= horizon={config.features.target_horizon}d. "
                         f"All {len(folds)} folds passed disjointness + purge-gap assertions; "
                         f"no feature exceeds |corr|>0.95 with the forward target."),
        "ic": ic_full,
        "model_table": model_table,
        "strategy_perf": strat_perf,
        "spy_perf": spy_perf,
        "long_short_perf": ls_perf,
        "long_short_note": ls_note,
        "strategy_final": float(bt.strategy_equity.iloc[-1]),
        "spy_final": float(bt.spy_equity.iloc[-1]),
        "contrib_total": bt.contributions_total,
        "monte_carlo": mc,
        "stress": stress,
        "feature_table": feature_table,
        "failure_analysis": failure,
        "next_experiment": nxt,
    }
    report = build_report(config, ctx)

    # 8. Persist
    rpath = os.path.join(config.output_dir, f"{config.name}_report.md")
    with open(rpath, "w") as f:
        f.write(report)
    metrics_path = os.path.join(config.output_dir, f"{config.name}_metrics.json")
    with open(metrics_path, "w") as f:
        json.dump({"best_model": best, "strategy": strat_perf, "spy": spy_perf,
                   "long_short": ls_perf, "ic": ic_full, "monte_carlo": mc, "stress": stress,
                   "strategy_final": ctx["strategy_final"], "spy_final": ctx["spy_final"],
                   "data_source": data.source, "survivorship_safe": universe_meta["survivorship_safe"],
                   "model_ic": {k: v["mean_ic"] for k, v in results.items()}},
                  f, indent=2, default=float)
    bt.strategy_equity.to_frame("strategy").assign(spy=bt.spy_equity).to_csv(
        os.path.join(config.output_dir, f"{config.name}_equity.csv"))

    log.info("Report  -> %s", rpath)
    log.info("Metrics -> %s", metrics_path)
    print("\n" + report)
    return ctx


def _changes_block(config, best):
    return (f"- Rebuilt from scratch as a modular framework (data/features/models/"
            f"portfolio/risk/backtest/evaluation/agents/automation).\n"
            f"- Massively expanded the **feature library** (momentum, trend, volume, "
            f"volatility incl. Yang-Zhang/Parkinson, mean-reversion, breadth, "
            f"cross-sectional ranks) — the V11 lesson was *feature quality*, not model complexity.\n"
            f"- Target is the **cross-sectionally de-meaned** forward {config.features.target_horizon}d "
            f"return (predict relative selection, not market beta).\n"
            f"- Validation upgraded to **purged + embargoed walk-forward** with executable "
            f"leakage assertions (directly addresses the V1-V9A inflated-Sharpe failures).\n"
            f"- Compared {len(config.models.candidates)} models"
            f"{' + stacking' if config.models.use_stacking else ''}; selected **{best}** by OOS rank-IC.")


def _failure_analysis(strat, spy, ic, mc, beat, ls=None, survivorship_safe=True):
    pts = []
    if ls is not None and not survivorship_safe:
        lss = ls["sharpe"]
        if not (lss == lss and lss >= 0.7):
            pts.append(f"- **Survivorship suspicion**: long-short spread Sharpe {lss:.2f} is "
                       "weak/negative on a survivorship-biased universe — the §4 SPY win is "
                       "likely market/survivorship beta, not selection skill. Re-test on a "
                       "point-in-time or broader universe before believing it.")
    if ic["ic_mean"] != ic["ic_mean"] or abs(ic["ic_mean"]) < 0.02:
        pts.append(f"- **Weak signal**: OOS rank-IC={ic['ic_mean']:.4f} (|IC|<0.02 ≈ noise). "
                   "The features still don't rank forward returns well enough.")
    if not beat:
        pts.append(f"- **Lost to SPY**: strategy Sharpe {strat['sharpe']:.2f} vs SPY {spy['sharpe']:.2f}. "
                   "Selection edge does not survive costs + de-meaning.")
    if mc["mc_stability"] == mc["mc_stability"] and mc["mc_stability"] < 1.0:
        pts.append(f"- **Low MC stability** ({mc['mc_stability']:.2f}<1): outcome distribution is "
                   "dominated by noise; the result is not dependable.")
    if strat["max_drawdown"] < -0.30:
        pts.append(f"- **Deep drawdown** ({strat['max_drawdown']:.1%}): risk overlays need tightening.")
    if not pts:
        pts.append("- No critical failures flagged on this run; proceed to richer validation "
                   "(more folds, live data, additional regimes) before trusting it.")
    return "\n".join(pts)


def _next_experiment(results, ic, beat):
    ranked = sorted(results.items(), key=lambda kv: -kv[1]["mean_ic"])
    second = ranked[1][0] if len(ranked) > 1 else ranked[0][0]
    return ("1. **Feature ablation**: drop bottom-quartile features by importance and re-test — "
            "smaller, higher-quality feature sets usually generalise better.\n"
            "2. **Add fundamentals/alt-data** (earnings surprise, analyst revisions, short interest) — "
            "pure technicals have a low IC ceiling.\n"
            f"3. **Ensemble tuning**: blend best + '{second}' with regime-conditional weights.\n"
            "4. **Regime split**: evaluate IC separately in calm vs stressed regimes; route capital accordingly.\n"
            "5. **Live-data rerun** in Codespaces/Colab (10y, full universe) before any paper trading on Alpaca.")


def parse_args():
    p = argparse.ArgumentParser()
    p.add_argument("--quick", action="store_true", help="fast smoke test (short window, fewer folds)")
    p.add_argument("--dca", choices=["none", "dca", "variable"], default=None)
    p.add_argument("--name", default=None)
    p.add_argument("--no-stack", action="store_true", help="skip the stacking ensemble (faster)")
    p.add_argument("--models", default=None,
                   help="comma-separated model subset, e.g. 'elasticnet,lgbm'")
    return p.parse_args()


def main():
    args = parse_args()
    cfg = ExperimentConfig()
    if args.quick:
        cfg.data.start = "2019-01-01"
        cfg.data.end = "2024-01-01"
        cfg.validation.n_splits = 3
        cfg.validation.train_min_days = 252
        cfg.models.candidates = ["ridge", "lgbm"]
        cfg.name = "v12_quick"
    if args.models:
        cfg.models.candidates = [m.strip() for m in args.models.split(",") if m.strip()]
    if args.no_stack:
        cfg.models.use_stacking = False
    if args.dca:
        cfg.backtest.dca_mode = args.dca
    if args.name:
        cfg.name = args.name
    run(cfg)


if __name__ == "__main__":
    main()
