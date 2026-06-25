"""Data-source availability registry — honest accounting of GOAL data sources.

Rather than fake unavailable feeds, the engine declares each source's true
status. ``get_signal`` for an unavailable/infeasible source raises explicitly —
nothing is silently stubbed as if it were real.

Status values:
  live              - used by the validated engine (price/volatility)
  shadow_only       - implemented but ablation showed it HURTS -> research only
  not_implemented   - buildable but not yet built
  infeasible        - needs infra/data this environment lacks
"""
from __future__ import annotations

from typing import Dict

SOURCE_STATUS: Dict[str, str] = {
    "price_volume": "live",
    "sec_edgar_fundamentals": "shadow_only",   # ablation: reduces OOS IC
    "sec_form4_insider": "shadow_only",         # ablation: reduces OOS IC
    "sec_13f": "not_implemented",
    "congress_trades": "not_implemented",
    "macro_fred": "not_implemented",
    "etf_holdings": "not_implemented",
    "cftc_cot": "not_implemented",
    "options_flow": "infeasible",
    "news_reuters_bloomberg_wsj_ft": "infeasible",
    "reddit_hn_forums": "infeasible",
    "narrative_lifecycle": "not_implemented",
    "intraday": "infeasible",
}

_USABLE = {"live"}


def source_available(name: str) -> bool:
    return SOURCE_STATUS.get(name) in _USABLE


def get_signal(name: str):
    status = SOURCE_STATUS.get(name, "unknown")
    if status not in _USABLE:
        raise NotImplementedError(
            f"data source '{name}' is NOT AVAILABLE (status={status}). "
            "It is not wired into the live engine; see docs/GOAL_IMPLEMENTATION_AUDIT.md.")
    raise NotImplementedError(f"'{name}' is live but has no standalone signal accessor.")
