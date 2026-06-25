"""Event-driven (daily) backtest engine.

Consumes out-of-sample predictions only (the runner never feeds in-sample
scores). Each rebalance it:
  1. selects the top-quantile names by predicted score,
  2. weights them (portfolio scheme + max-weight cap),
  3. scales gross exposure by the cash-regime and vol-target overlays,
  4. charges commission + slippage on turnover.

Two views are produced:
  * Time-weighted return series (contributions removed) -> Sharpe/DD/etc.
  * Money-weighted equity curve (with the DCA contribution schedule) ->
    the headline "Strategy $X vs SPY $Y" comparison, apples-to-apples because
    SPY is simulated with the *same* contribution schedule.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

import numpy as np
import pandas as pd

from ..portfolio import compute_weights
from ..risk import vol_target_scalar, cash_regime_scalar, kelly_exposure
from ..utils import get_logger
from .costs import turnover_cost

log = get_logger("backtest")


@dataclass
class BacktestResult:
    strategy_returns: pd.Series              # time-weighted daily returns (net)
    strategy_nav: pd.Series                  # cumprod of the above (starts 1.0)
    strategy_equity: pd.Series               # money-weighted account incl. DCA
    spy_returns: pd.Series
    spy_nav: pd.Series
    spy_equity: pd.Series
    weights_history: pd.DataFrame
    contributions_total: float
    avg_turnover: float
    meta: dict = field(default_factory=dict)


def _contribution_dates(dates, cfg):
    if cfg.dca_mode == "none":
        return {}
    sched = {}
    for i, d in enumerate(dates):
        if i > 0 and i % cfg.dca_interval_days == 0:
            amt = cfg.dca_amount
            if cfg.dca_mode == "variable":
                # variable DCA: lean in harder after drawdowns (handled in loop)
                amt = cfg.dca_amount  # base; scaled dynamically below
            sched[d] = amt
    return sched


def run_backtest(predictions: pd.Series, close: pd.DataFrame, benchmark: pd.Series,
                 cfg, breadth: Optional[pd.DataFrame] = None) -> BacktestResult:
    pred_dates = predictions.index.get_level_values("date").unique().sort_values()
    daily_ret = close.pct_change()
    bench_ret = benchmark.pct_change()

    dates = [d for d in pred_dates if d in daily_ret.index]
    rebal_dates = set(dates[::cfg.rebalance_days])
    contrib_sched = _contribution_dates(dates, cfg)

    # Point-in-time regime labels for the optional risk-off exposure gate
    regime_on = None
    if getattr(cfg, "regime_filter", False):
        from ..regime import classify_regime
        regime_on = classify_regime(benchmark)["risk_on"]

    cur_w = pd.Series(dtype=float)            # current target weights (assets)
    weights_hist = {}
    tw_returns, turnovers = [], []

    # money-weighted accounts
    strat_value = cfg.initial_capital
    spy_value = cfg.initial_capital
    spy_units = strat_value / benchmark.loc[dates[0]] if dates else 0.0
    strat_equity, spy_equity = {}, {}
    contrib_total = 0.0

    tw_series = []  # (date, net daily return)
    recent_port_rets = []

    for i, d in enumerate(dates):
        # ---- daily P&L from yesterday's weights ----
        if i > 0 and len(cur_w) > 0:
            r = daily_ret.loc[d, cur_w.index].fillna(0.0)
            gross_ret = float((cur_w * r).sum())
        else:
            gross_ret = 0.0
        cost_today = 0.0

        # ---- rebalance ----
        if d in rebal_dates:
            today_scores = predictions.loc[d] if d in predictions.index.get_level_values("date") else None
            if today_scores is not None and len(today_scores) > 0:
                scores = today_scores.dropna().sort_values(ascending=False)
                k = max(int(np.ceil(len(scores) * cfg.top_quantile)), 1)
                picks = scores.index[:k].tolist()

                lookback = daily_ret.loc[:d].tail(60)[picks].dropna(how="all", axis=1)
                picks = [p for p in picks if p in lookback.columns]
                if picks:
                    w_new = compute_weights(cfg.weighting, lookback[picks].dropna(), cfg.max_weight)

                    # ---- exposure overlays ----
                    exposure = 1.0
                    if breadth is not None and d in breadth.index:
                        b200 = breadth.loc[d].get("breadth_pct_above_200", 0.5)
                        mvol = bench_ret.loc[:d].tail(20).std() * np.sqrt(252)
                        exposure *= cash_regime_scalar(float(b200), float(mvol))
                    if cfg.vol_target_annual and len(recent_port_rets) > 20:
                        exposure *= vol_target_scalar(
                            pd.Series(recent_port_rets), cfg.vol_target_annual)
                    if getattr(cfg, "use_kelly", False) and len(recent_port_rets) > 20:
                        exposure *= kelly_exposure(
                            pd.Series(recent_port_rets), cfg.kelly_fraction_cap)
                    if regime_on is not None and d in regime_on.index and regime_on.loc[d] < 0.5:
                        exposure *= cfg.regime_off_exposure  # risk-off: cut exposure
                    w_new = w_new * exposure

                    # ---- turnover & cost ----
                    all_idx = cur_w.index.union(w_new.index)
                    turn = float((w_new.reindex(all_idx).fillna(0)
                                  - cur_w.reindex(all_idx).fillna(0)).abs().sum())
                    cost_today = turnover_cost(turn, cfg.commission_bps, cfg.slippage_bps)
                    turnovers.append(turn)
                    cur_w = w_new

        net_ret = gross_ret - cost_today
        tw_series.append((d, net_ret))
        recent_port_rets.append(net_ret)
        if len(recent_port_rets) > 60:
            recent_port_rets.pop(0)
        weights_hist[d] = cur_w.copy()

        # ---- money-weighted accounts (with DCA) ----
        strat_value *= (1 + net_ret)
        spy_r = float(bench_ret.loc[d]) if d in bench_ret.index and i > 0 else 0.0
        spy_value *= (1 + spy_r)
        if d in contrib_sched:
            amt = contrib_sched[d]
            if cfg.dca_mode == "variable":
                # buy-the-dip tilt: up to 2x base when 20d strat return < -5%
                recent = np.prod([1 + x for x in recent_port_rets[-20:]]) - 1
                amt *= float(np.clip(1.0 - 5 * recent, 0.5, 2.0))
            strat_value += amt
            spy_value += amt
            contrib_total += amt
        strat_equity[d] = strat_value
        spy_equity[d] = spy_value

    idx = [d for d, _ in tw_series]
    strat_ret = pd.Series([r for _, r in tw_series], index=idx)
    spy_ret = bench_ret.reindex(idx).fillna(0.0)
    spy_ret.iloc[0] = 0.0

    result = BacktestResult(
        strategy_returns=strat_ret,
        strategy_nav=(1 + strat_ret).cumprod(),
        strategy_equity=pd.Series(strat_equity),
        spy_returns=spy_ret,
        spy_nav=(1 + spy_ret).cumprod(),
        spy_equity=pd.Series(spy_equity),
        weights_history=pd.DataFrame(weights_hist).T.fillna(0.0),
        contributions_total=contrib_total,
        avg_turnover=float(np.mean(turnovers)) if turnovers else 0.0,
        meta={"n_days": len(idx), "n_rebalances": len(turnovers),
              "dca_mode": cfg.dca_mode},
    )
    log.info("Backtest: %d days, %d rebalances, avg turnover %.2f, contrib $%.0f",
             len(idx), len(turnovers), result.avg_turnover, contrib_total)
    return result


def run_long_short(predictions: pd.Series, close: pd.DataFrame, cfg) -> pd.Series:
    """Dollar-neutral long-short spread return (research diagnostic).

    Each rebalance: long the top quantile, short the bottom quantile, equal
    weight within each leg, scaled to gross exposure 1.0 (long +0.5 / short
    -0.5, net 0). Net of the same commission+slippage on turnover.

    Why this matters: survivorship bias lifts essentially every name in a
    current-constituents universe, so it largely *cancels* in the long-short
    spread. A spread that is solidly positive after costs is evidence of real
    cross-sectional selection skill rather than just owning past winners. (It
    is a signal-quality probe, not necessarily a deployable strategy — shorting
    has its own borrow/availability constraints.)
    """
    daily_ret = close.pct_change()
    pred_dates = predictions.index.get_level_values("date").unique().sort_values()
    dates = [d for d in pred_dates if d in daily_ret.index]
    rebal = set(dates[::cfg.rebalance_days])
    pred_date_level = predictions.index.get_level_values("date")

    cur_w = pd.Series(dtype=float)
    out = []
    for i, d in enumerate(dates):
        gross = 0.0
        if i > 0 and len(cur_w) > 0:
            r = daily_ret.loc[d, cur_w.index].fillna(0.0)
            gross = float((cur_w * r).sum())
        cost = 0.0
        if d in rebal and d in pred_date_level:
            scores = predictions.loc[d].dropna().sort_values(ascending=False)
            if len(scores) >= 4:
                k = max(int(np.ceil(len(scores) * cfg.top_quantile)), 1)
                longs, shorts = scores.index[:k], scores.index[-k:]
                w_new = pd.concat([pd.Series(0.5 / len(longs), index=longs),
                                   pd.Series(-0.5 / len(shorts), index=shorts)])
                idx = cur_w.index.union(w_new.index)
                turn = float((w_new.reindex(idx).fillna(0)
                              - cur_w.reindex(idx).fillna(0)).abs().sum())
                cost = turnover_cost(turn, cfg.commission_bps, cfg.slippage_bps)
                cur_w = w_new
        out.append((d, gross - cost))

    idx = [d for d, _ in out]
    return pd.Series([r for _, r in out], index=idx)
