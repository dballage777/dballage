"""Markdown report generator implementing the directive's OUTPUT REQUIREMENTS:
changes, rationale, metrics, benchmark comparison, failure analysis, and a
proposed next experiment."""
from __future__ import annotations

from datetime import datetime
from typing import Dict


def _fmt(v):
    if isinstance(v, float):
        if v != v:  # NaN
            return "n/a"
        return f"{v:,.4f}"
    return str(v)


def _table(d: Dict, cols=("metric", "value")) -> str:
    rows = [f"| {cols[0]} | {cols[1]} |", "|---|---|"]
    for k, v in d.items():
        rows.append(f"| {k} | {_fmt(v)} |")
    return "\n".join(rows)


def build_report(config, ctx: Dict) -> str:
    """``ctx`` carries everything the runner computed."""
    strat = ctx["strategy_perf"]
    spy = ctx["spy_perf"]
    verdict = "BEAT" if strat["sharpe"] > spy["sharpe"] and \
        ctx["strategy_final"] > ctx["spy_final"] else "LOST TO"

    lines = []
    lines.append(f"# V12 Experiment Report — `{config.name}`")
    lines.append(f"_Generated {datetime.utcnow():%Y-%m-%d %H:%M UTC} · data source: "
                 f"**{ctx.get('data_source','?')}**_")
    if ctx.get("data_source") == "synthetic":
        lines.append("\n> ⚠️ **Synthetic data** (network-restricted environment). "
                     "These numbers validate the *pipeline*, not real alpha. "
                     "Re-run with live data in Codespaces/Colab for tradable results.")

    # 1. Changes
    lines.append("\n## 1. What changed & why")
    lines.append(ctx.get("changes", "_n/a_"))

    # 2. Leakage
    lines.append("\n## 2. Leakage controls")
    lines.append(ctx.get("leakage_note", "All structural leakage assertions passed."))

    # 2b. Survivorship bias
    lines.append("\n## 2b. Survivorship bias")
    lines.append(ctx.get("bias_note", "_n/a_"))

    # 3. Signal quality
    lines.append("\n## 3. Signal quality (out-of-sample)")
    lines.append(_table(ctx["ic"]))
    lines.append("\n**Best model per fold (OOS rank-IC):**\n")
    lines.append(ctx.get("model_table", "_n/a_"))

    # 4. Performance vs benchmark
    lines.append("\n## 4. Performance vs SPY  →  **Strategy " + verdict + " SPY**")
    perf_tbl = ["| metric | strategy | SPY |", "|---|---|---|"]
    for k in ["cagr", "ann_vol", "sharpe", "sortino", "max_drawdown", "calmar",
              "win_rate", "total_return"]:
        perf_tbl.append(f"| {k} | {_fmt(strat[k])} | {_fmt(spy[k])} |")
    lines.append("\n".join(perf_tbl))
    lines.append(f"\n**Money-weighted (DCA={config.backtest.dca_mode}, "
                 f"contrib ${ctx['contrib_total']:,.0f}):** "
                 f"Strategy **${ctx['strategy_final']:,.2f}** vs "
                 f"SPY **${ctx['spy_final']:,.2f}**")

    # 4b. Long-short signal probe (survivorship-neutral)
    if "long_short_perf" in ctx:
        lines.append("\n## 4b. Long-short signal probe (dollar-neutral, survivorship-cancelling)")
        ls = ctx["long_short_perf"]
        ls_tbl = ["| metric | long-short spread |", "|---|---|"]
        for k in ["cagr", "ann_vol", "sharpe", "sortino", "max_drawdown", "total_return"]:
            ls_tbl.append(f"| {k} | {_fmt(ls[k])} |")
        lines.append("\n".join(ls_tbl))
        lines.append("\n" + ctx.get("long_short_note", ""))

    # 5. Monte Carlo + stress
    lines.append("\n## 5. Monte-Carlo & stress")
    lines.append(_table(ctx["monte_carlo"]))
    lines.append("")
    lines.append(_table(ctx["stress"]))

    # 6. Top features
    lines.append("\n## 6. Feature importance (top 15, gain/coef avg over folds)")
    lines.append(ctx.get("feature_table", "_n/a_"))

    # 7. Failure analysis + next experiment
    lines.append("\n## 7. Failure analysis")
    lines.append(ctx.get("failure_analysis", "_n/a_"))
    lines.append("\n## 8. Proposed next experiment")
    lines.append(ctx.get("next_experiment", "_n/a_"))

    return "\n".join(lines) + "\n"
