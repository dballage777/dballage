"""Monte-Carlo & stress testing.

Block bootstrap preserves short-horizon autocorrelation (so we don't flatter
Sharpe by destroying volatility clustering). Stress tests apply mechanical
shocks to the realised return stream.
"""
from __future__ import annotations

from typing import Dict

import numpy as np
import pandas as pd

from .metrics import sharpe, max_drawdown, cagr


def monte_carlo_bootstrap(returns: pd.Series, n_sims: int = 1000,
                          block: int = 10, seed: int = 0) -> Dict[str, float]:
    rng = np.random.default_rng(seed)
    r = returns.dropna().values
    n = len(r)
    if n < block * 2:
        return {"mc_sharpe_mean": float("nan"), "mc_sharpe_std": float("nan"),
                "mc_total_mean": float("nan"), "mc_total_p05": float("nan"),
                "mc_stability": float("nan")}
    n_blocks = int(np.ceil(n / block))
    sharpes, totals = [], []
    for _ in range(n_sims):
        starts = rng.integers(0, n - block, size=n_blocks)
        sample = np.concatenate([r[s:s + block] for s in starts])[:n]
        s = pd.Series(sample)
        sd = s.std()
        sharpes.append(s.mean() / sd * np.sqrt(252) if sd > 0 else 0.0)
        totals.append((1 + s).prod() - 1)
    sharpes, totals = np.array(sharpes), np.array(totals)
    mean_t, std_t = totals.mean(), totals.std()
    return {
        "mc_sharpe_mean": float(sharpes.mean()),
        "mc_sharpe_std": float(sharpes.std()),
        "mc_total_mean": float(mean_t),
        "mc_total_p05": float(np.percentile(totals, 5)),
        "mc_total_p95": float(np.percentile(totals, 95)),
        # stability = signal-to-noise of the total-return distribution
        "mc_stability": float(mean_t / std_t) if std_t > 0 else float("nan"),
    }


def stress_tests(returns: pd.Series) -> Dict[str, float]:
    """Mechanical robustness shocks."""
    out = {}
    # 1) extra 5bps/day cost drag
    out["stress_cost_5bps_sharpe"] = sharpe(returns - 0.0005)
    # 2) worst 1% days doubled (fat-tail shock)
    r = returns.copy()
    thr = r.quantile(0.01)
    r2 = r.copy()
    r2[r2 <= thr] *= 2
    out["stress_fattail_maxdd"] = max_drawdown(r2)
    # 3) drop best 5% of days (luck removal)
    r3 = returns[returns < returns.quantile(0.95)]
    out["stress_no_luck_cagr"] = cagr(r3)
    return out
