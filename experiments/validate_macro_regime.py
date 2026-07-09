"""Gate: does macro data improve the regime timing? (variant-7 pre-check)

Before building a whole forward variant 7 (v6 + OpenBB macro), test the core
claim cheaply: does a macro 'risk-off' overlay (inverted yield curve / tight
financial conditions) improve the risk-adjusted timing of being in vs out of the
market, over the price-only regime gate?

Compares, on the benchmark (SPY):
  A. buy & hold
  B. price-only 2-state regime gate (our current approach)
  C. price regime + macro overlay (cash if EITHER says risk-off)

PASS (build variant 7) if C beats B on risk-adjusted terms — higher Sharpe, or
meaningfully smaller drawdown without hurting Sharpe. Otherwise macro doesn't
earn a forward variant. Exit 0 = PASS, 2 = FAIL.

    python -m experiments.validate_macro_regime --start 2015-01-01 --end 2026-06-20

Needs network (OpenBB or FRED) for a REAL verdict; falls back to synthetic macro
(clearly stamped) for pipeline validation only.
"""
from __future__ import annotations

import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import warnings
warnings.filterwarnings("ignore")

import pandas as pd

from v12.config import ExperimentConfig
from v12.data import load_prices
from v12.data.macro import load_macro, macro_risk_off
from v12.regime import classify_regime
from v12.evaluation import performance_summary
from v12.utils import get_logger

log = get_logger("macro_gate")


def _gated_returns(spy_ret, exposure):
    """Apply yesterday's exposure to today's return (no look-ahead)."""
    return (spy_ret * exposure.shift(1).fillna(0.0)).dropna()


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--start", default="2015-01-01")
    p.add_argument("--end", default="2026-06-20")
    p.add_argument("--min-sharpe-gain", type=float, default=0.05)
    p.add_argument("--min-dd-gain", type=float, default=0.02)
    args = p.parse_args()

    cfg = ExperimentConfig(name="macro_gate")
    cfg.data.start, cfg.data.end = args.start, args.end
    data = load_prices(cfg.data)
    spy = data.close[cfg.data.benchmark].dropna()
    spy_ret = spy.pct_change()

    macro, msrc = load_macro(start=args.start, end=args.end)
    log.info("Macro source: %s", msrc)
    risk_off = macro_risk_off(macro).reindex(spy.index).ffill().fillna(False)

    price_on = classify_regime(spy)["risk_on"].reindex(spy.index).fillna(0.0)
    macro_on = (price_on.astype(bool) & (~risk_off.astype(bool))).astype(float)

    bh = performance_summary(spy_ret.dropna(), "buy_hold")
    price = performance_summary(_gated_returns(spy_ret, price_on), "price_regime")
    macroP = performance_summary(_gated_returns(spy_ret, macro_on), "macro_regime")

    def row(nm, m):
        return f"{nm:16}{m['sharpe']:>8.3f}{m['max_drawdown']*100:>10.1f}%{m['cagr']*100:>9.1f}%"
    print(f"\n=== MACRO-REGIME GATE  (macro source: {msrc}) ===")
    print(f"{'strategy':16}{'Sharpe':>8}{'maxDD':>11}{'CAGR':>9}")
    print(row("buy_hold", bh)); print(row("price_regime", price)); print(row("macro_regime", macroP))

    sharpe_gain = macroP["sharpe"] - price["sharpe"]
    dd_gain = macroP["max_drawdown"] - price["max_drawdown"]        # less negative = better
    helps = (sharpe_gain >= args.min_sharpe_gain) or \
            (dd_gain >= args.min_dd_gain and sharpe_gain >= -0.01)
    print(f"\nmacro vs price-only:  Sharpe {sharpe_gain:+.3f} | drawdown {dd_gain*100:+.1f}pts")
    verdict = "PASS - build variant 7" if helps else "FAIL - macro does not earn a forward variant"
    if msrc == "synthetic":
        verdict += "  (SYNTHETIC macro - wiring check only; rerun with network for the real verdict)"
    print("\n" + "=" * 60 + f"\nMACRO GATE: {verdict}\n" + "=" * 60)
    sys.exit(0 if helps else 2)


if __name__ == "__main__":
    main()
