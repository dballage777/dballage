"""Performance & signal-quality metrics."""
from __future__ import annotations

from typing import Dict

import numpy as np
import pandas as pd

TRADING_DAYS = 252


def cagr(returns: pd.Series) -> float:
    if len(returns) == 0:
        return 0.0
    total = (1 + returns).prod()
    years = len(returns) / TRADING_DAYS
    return float(total ** (1 / years) - 1) if years > 0 and total > 0 else float("nan")


def ann_vol(returns: pd.Series) -> float:
    return float(returns.std() * np.sqrt(TRADING_DAYS))


def sharpe(returns: pd.Series, rf: float = 0.0) -> float:
    excess = returns - rf / TRADING_DAYS
    sd = excess.std()
    return float(excess.mean() / sd * np.sqrt(TRADING_DAYS)) if sd > 0 else float("nan")


def sortino(returns: pd.Series, rf: float = 0.0) -> float:
    excess = returns - rf / TRADING_DAYS
    downside = excess[excess < 0].std()
    return float(excess.mean() / downside * np.sqrt(TRADING_DAYS)) if downside > 0 else float("nan")


def max_drawdown(returns: pd.Series) -> float:
    nav = (1 + returns).cumprod()
    peak = nav.cummax()
    return float((nav / peak - 1).min())


def calmar(returns: pd.Series) -> float:
    mdd = max_drawdown(returns)
    c = cagr(returns)
    return float(c / abs(mdd)) if mdd < 0 else float("nan")


def win_rate(returns: pd.Series) -> float:
    nz = returns[returns != 0]
    return float((nz > 0).mean()) if len(nz) else float("nan")


def information_coefficient(predictions: pd.Series, target: pd.Series) -> Dict[str, float]:
    """Rank IC (Spearman) per date, then summarised — the cleanest read on
    whether the signal actually ranks future returns."""
    df = pd.DataFrame({"pred": predictions, "y": target}).dropna()
    if df.empty:
        return {"ic_mean": float("nan"), "ic_std": float("nan"), "icir": float("nan")}
    by_date = df.groupby(level="date")
    ics = by_date.apply(lambda g: g["pred"].corr(g["y"], method="spearman"))
    ics = ics.dropna()
    mean, std = float(ics.mean()), float(ics.std())
    return {"ic_mean": mean, "ic_std": std,
            "icir": float(mean / std * np.sqrt(TRADING_DAYS)) if std > 0 else float("nan")}


def performance_summary(returns: pd.Series, name: str = "strategy") -> Dict[str, float]:
    return {
        "name": name,
        "cagr": cagr(returns),
        "ann_vol": ann_vol(returns),
        "sharpe": sharpe(returns),
        "sortino": sortino(returns),
        "max_drawdown": max_drawdown(returns),
        "calmar": calmar(returns),
        "win_rate": win_rate(returns),
        "total_return": float((1 + returns).prod() - 1),
    }
