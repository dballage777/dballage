"""Daily monitoring report + ranked opportunity lists (the spec's OUTPUTS).

Turns the engine's state (regime, allocation, governed decisions) and the 0-100
asset scores into the spec's required artifacts:

  * a daily report (Market Regime, Allocation, Top Signals, Top Risks,
    Top Opportunities)
  * ranked Top-N lists where every recommendation carries the mandated fields:
    Asset, Score, EV, Risk, Confidence, Position Size, Entry Range, Exit Criteria,
    Reasoning, Sources.

BUY/HOLD/SELL come from the governed DecisionEngine; WATCH = high-scoring names
the gates are *not* buying yet (regime/EV/confidence), i.e. the monitoring list.
Entry range and exit criteria are rule-based and explicit (no hidden magic).
"""
from __future__ import annotations

from typing import Dict, List, Optional

import pandas as pd

STOP_PCT = 0.08         # rule-based protective stop used in Exit Criteria


def _action_for(asset: str, decision, composite: float, in_targets: bool) -> str:
    if in_targets:
        return "BUY"
    if decision is not None and decision.action in ("SELL", "REDUCE"):
        return decision.action
    if composite >= 70.0:
        return "WATCH"           # high score but gates not buying -> monitor
    return decision.action if decision is not None else "HOLD"


def top_n(scores: pd.DataFrame, decisions: List, targets: Dict[str, float],
          last_price: Optional[pd.Series] = None, n: int = 25,
          only: Optional[set] = None) -> List[dict]:
    """Top-N ranked recommendations with the full mandated field set."""
    dec_by = {d.asset: d for d in decisions}
    rows: List[dict] = []
    for asset, row in scores.iterrows():
        if only is not None and asset not in only:
            continue
        d = dec_by.get(asset)
        comp = float(row.get("composite", 0.0))
        in_t = targets.get(asset, 0.0) > 0
        action = _action_for(asset, d, comp, in_t)
        px = float(last_price[asset]) if (last_price is not None and asset in last_price) else None
        entry = (f"{px*0.99:.4g}-{px*1.01:.4g}" if px else "n/a")
        rows.append({
            "asset": asset,
            "score": round(comp, 1),
            "action": action,
            "ev": round(float(d.ev_score), 5) if d else None,
            "risk": d.risk_status if d else "n/a",
            "confidence": round(float(d.confidence), 0) if d else None,
            "position_size": round(targets.get(asset, 0.0) * 100, 2),
            "entry_range": entry,
            "exit_criteria": f"stop -{STOP_PCT*100:.0f}% or regime->bear/crisis",
            "reasoning": d.reasoning if d else "scored, not selected by gates",
            "sources": d.sources if d else "price+volatility",
        })
    rows.sort(key=lambda r: -r["score"])
    return rows[:n]


def _fmt_table(rows: List[dict]) -> str:
    if not rows:
        return "_(none)_\n"
    head = ("| Asset | Score | Action | EV | Risk | Conf | Size% | Entry | Exit |\n"
            "|---|---|---|---|---|---|---|---|---|\n")
    body = "".join(
        f"| {r['asset']} | {r['score']} | {r['action']} | "
        f"{r['ev'] if r['ev'] is not None else '-'} | {r['risk']} | "
        f"{r['confidence'] if r['confidence'] is not None else '-'} | {r['position_size']} | "
        f"{r['entry_range']} | {r['exit_criteria']} |\n"
        for r in rows)
    return head + body


def build_daily_report(date, stock_regime: str, crypto_regime: str,
                       allocation: Dict[str, float], scores: pd.DataFrame,
                       decisions: List, targets: Dict[str, float],
                       last_price: Optional[pd.Series] = None,
                       crypto_set: Optional[set] = None,
                       live_weight_fraction: Optional[float] = None) -> str:
    """Render the daily monitoring report as markdown."""
    crypto_set = crypto_set or {a for a in scores.index if str(a).endswith("-USD")}
    stock_set = {a for a in scores.index if a not in crypto_set}

    top_opps = top_n(scores, decisions, targets, last_price, n=25)
    top_signals = sorted([d for d in decisions if d.ev_score is not None],
                         key=lambda d: -d.ev_score)[:10]
    held = [(a, w) for a, w in targets.items() if w > 0]
    top_risks = sorted(held, key=lambda x: -x[1])[:10]

    L = []
    L.append(f"# Daily Monitoring Report — {date:%Y-%m-%d}\n")
    if live_weight_fraction is not None:
        L.append(f"> **Source coverage:** only **{live_weight_fraction*100:.0f}%** of the "
                 f"designed source-weight budget is live today (price/volume). The rest "
                 f"(news/Reddit/Discord/options-flow/etc.) is not ingested — see "
                 f"`docs/MONITORING_SPEC.md`. Scores reflect price/volume signals only.\n")
    L.append("## Market Regime")
    L.append(f"- **Stocks:** {stock_regime}\n- **Crypto (BTC):** {crypto_regime}\n")
    L.append("## Portfolio Allocation")
    L.append(f"- Stocks: **{allocation.get('stocks',0)*100:.1f}%** (cap 70%)")
    L.append(f"- Crypto: **{allocation.get('crypto',0)*100:.1f}%** (cap 30%)")
    L.append(f"- Cash: **{allocation.get('cash',0)*100:.1f}%** (default safe state)\n")

    L.append("## Top Signals (highest EV)")
    L.append(_fmt_table(top_n(scores.loc[[d.asset for d in top_signals]] if top_signals else scores.iloc[:0],
                              decisions, targets, last_price, n=10)))
    L.append("## Top Risks (largest open positions)")
    if top_risks:
        L.append("\n".join(f"- {a}: {w*100:.1f}% of portfolio" for a, w in top_risks) + "\n")
    else:
        L.append("_No open positions — fully in cash._\n")

    L.append("## Top 25 Opportunities (ranked by composite score)")
    L.append(_fmt_table(top_opps))
    L.append("## Top 25 Long-Term / Stock Opportunities")
    L.append(_fmt_table(top_n(scores, decisions, targets, last_price, n=25, only=stock_set)))
    L.append("## Top 25 Crypto Opportunities")
    L.append(_fmt_table(top_n(scores, decisions, targets, last_price, n=25, only=crypto_set)))

    L.append("---\n*Decisions are governed by EV gate, regime exposure, Kelly, "
             "correlation, and position/class caps. WATCH = high score the gates "
             "are not buying yet. Paper/shadow only — not investment advice.*")
    return "\n".join(L)
