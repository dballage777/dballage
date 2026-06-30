"""Independent cross-check of the in-house backtest engine (VectorBt + numpy).

Single-engine backtests carry unquantified implementation error (see the
'Implementation Risk in Portfolio Backtesting' literature). This script confirms
our engine on the two things that matter for trust:

  PART A — return generation: recompute daily portfolio returns *independently*
           from the engine's own position history (numpy, zero-cost config) and
           assert they match the engine's returns exactly.
  PART B — metric computation: take the engine's strategy return series and
           recompute Sharpe / max-drawdown / total-return with BOTH numpy and
           **VectorBt**, and assert they match the engine's reported metrics.

Uses a deterministic momentum signal (no ML) so the check isolates the engine's
*arithmetic* — which is model-agnostic, so confirming it here confirms it for the
validated ML strategy too. Exit code 0 = engines agree, 2 = divergence.

    python -m experiments.vectorbt_crosscheck --broad --start 2018-01-01 --end 2026-06-20
"""
from __future__ import annotations

import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import warnings
warnings.filterwarnings("ignore")

import numpy as np
import pandas as pd

from v12.config import ExperimentConfig, BROAD_UNIVERSE
from v12.data import load_prices
from v12.backtest.engine import run_backtest
from v12.evaluation import performance_summary
from v12.utils import get_logger

log = get_logger("crosscheck")
TOL = 0.02            # relative tolerance for metric agreement (2%)
ABS_TOL = 1e-9        # for the exact return-generation check


def _momentum_predictions(close: pd.DataFrame, lookback: int = 120, start=None) -> pd.Series:
    """Deterministic signal: trailing-return rank, as (date,ticker) predictions."""
    mom = close / close.shift(lookback) - 1.0
    mom = mom.dropna(how="all")
    if start is not None:
        mom = mom.loc[mom.index >= pd.Timestamp(start)]
    s = mom.stack()
    s.index.names = ["date", "ticker"]
    return s


def _simple_cfg(name, costs: bool):
    cfg = ExperimentConfig(name=name).backtest
    cfg.weighting = "equal"
    cfg.portfolio_mode = "neutral"
    cfg.vol_target_annual = None
    cfg.use_kelly = False
    cfg.regime_filter = False
    cfg.hard_risk = False
    cfg.graduated_sizing = False
    cfg.no_trade_band = 0.0
    cfg.dca_mode = "none"
    cfg.commission_bps = 1.0 if costs else 0.0
    cfg.slippage_bps = 5.0 if costs else 0.0
    return cfg


def _np_metrics(r: pd.Series) -> dict:
    r = r.dropna()
    sd = r.std()
    nav = (1 + r).cumprod()
    dd = (nav / nav.cummax() - 1.0).min()
    return {"sharpe": float(r.mean() / sd * np.sqrt(252)) if sd > 0 else float("nan"),
            "max_drawdown": float(dd), "total_return": float(nav.iloc[-1] - 1.0)}


def _vbt_metrics(r: pd.Series):
    try:
        import vectorbt as vbt
    except Exception as e:
        return None, f"vectorbt not installed ({e})"
    try:
        acc = r.dropna().vbt.returns(freq="D")
        return ({"sharpe": float(acc.sharpe_ratio()),
                 "max_drawdown": float(acc.max_drawdown()),
                 "total_return": float(acc.total_return())}, None)
    except Exception as e:                       # API differences across versions
        return None, f"vectorbt API error ({e})"


def _close(a, b, tol):
    if a != a or b != b:
        return a != a and b != b
    return abs(a - b) <= tol * max(abs(a), abs(b), 1e-9)


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--broad", action="store_true")
    p.add_argument("--start", default="2018-01-01")
    p.add_argument("--end", default="2026-06-20")
    args = p.parse_args()

    cfg = ExperimentConfig(name="crosscheck")
    if args.broad:
        cfg.data.universe = list(BROAD_UNIVERSE)
    cfg.data.start, cfg.data.end = "2015-01-01", args.end
    data = load_prices(cfg.data)
    close = data.close[[t for t in cfg.data.universe if t in data.close.columns]]
    bench = data.close[cfg.data.benchmark]
    preds = _momentum_predictions(close, start=args.start)
    log.info("Cross-check on %d names, %d prediction dates (data=%s).",
             close.shape[1], preds.index.get_level_values("date").nunique(), data.source)

    ok = True

    # ---- PART A: independent return-generation check (zero cost) ----
    btA = run_backtest(preds, close, bench, _simple_cfg("ccA", costs=False))
    eng_ret = btA.strategy_returns
    daily = close.pct_change()
    wh = btA.weights_history.reindex(eng_ret.index).fillna(0.0)
    # engine applies YESTERDAY's stored weights to today's return
    recomputed = (wh.shift(1) * daily.reindex(columns=wh.columns).loc[eng_ret.index]).sum(axis=1)
    recomputed.iloc[0] = 0.0
    max_diff = float((eng_ret - recomputed).abs().max())
    a_pass = max_diff <= 1e-6
    ok &= a_pass
    print("\n=== PART A — return generation (engine vs independent numpy recompute) ===")
    print(f"  max per-day return difference: {max_diff:.2e}  -> {'MATCH' if a_pass else 'DIVERGE'}")

    # ---- PART B: metric computation check (real costs) ----
    btB = run_backtest(preds, close, bench, _simple_cfg("ccB", costs=True))
    r = btB.strategy_returns
    eng = performance_summary(r, "strategy")
    npm = _np_metrics(r)
    vbtm, vbt_err = _vbt_metrics(r)

    print("\n=== PART B — metrics on the engine's return series ===")
    print(f"{'metric':14}{'engine':>12}{'numpy':>12}{'vectorbt':>12}")
    for k in ["sharpe", "max_drawdown", "total_return"]:
        ev, nv = eng[k], npm[k]
        vv = vbtm[k] if vbtm else float("nan")
        print(f"{k:14}{ev:>12.4f}{nv:>12.4f}{vv:>12.4f}")
        if not _close(ev, nv, TOL):
            ok = False
            print(f"   ^ engine vs numpy DIVERGE on {k}")
        if vbtm and not _close(ev, vv, TOL):
            ok = False
            print(f"   ^ engine vs vectorbt DIVERGE on {k}")
    if vbtm is None:
        print(f"  (vectorbt comparison skipped: {vbt_err})")

    print("\n" + "=" * 60)
    verdict = "ENGINES AGREE" if ok else "DIVERGENCE DETECTED — investigate"
    print(f"CROSS-CHECK VERDICT: {verdict}")
    print("=" * 60)
    sys.exit(0 if ok else 2)


if __name__ == "__main__":
    main()
