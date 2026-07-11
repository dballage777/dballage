"""Data-source registry — honest accounting of GOAL / monitoring data sources.

Rather than fake unavailable feeds, the engine declares each source's true
status, its target weight, and its intended monitoring frequency. ``get_signal``
for an unavailable/infeasible source raises explicitly — nothing is silently
stubbed as if it were real.

Status values:
  live              - used by the validated engine (price/volatility)
  shadow_only       - implemented but ablation showed it HURTS -> research only
  not_implemented   - buildable; needs an API key / connector but no paid feed
  infeasible        - needs paid/real-time/authenticated infra this lacks
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Dict

# --- backward-compatible flat status map ------------------------------------
SOURCE_STATUS: Dict[str, str] = {
    "price_volume": "live",
    "sec_edgar_fundamentals": "shadow_only",   # ablation: reduces OOS IC
    "sec_form4_insider": "shadow_only",         # ablation: reduces OOS IC
    "sec_13f": "not_implemented",
    "congress_trades": "not_implemented",
    "macro_fred": "shadow_only",   # gate-tested (macro-regime overlay): HURT Sharpe on real FRED data
    "etf_holdings": "not_implemented",
    "cftc_cot": "not_implemented",
    "options_flow": "infeasible",
    "news_reuters_bloomberg_wsj_ft": "infeasible",
    "reddit_hn_forums": "infeasible",
    "narrative_lifecycle": "not_implemented",
    "intraday": "infeasible",
}

_USABLE = {"live"}


@dataclass
class SourceSpec:
    category: str
    weight: float        # target category weight from the monitoring spec
    frequency: str       # intended monitoring cadence
    status: str          # feasibility (see module docstring)


# --- monitoring spec: category weights + cadence + honest feasibility --------
# Weights are the user's institutional spec (sum = 1.00). They are TARGETS; a
# source only contributes if its status is 'live'. Everything else is recorded
# so the gap between vision and reality is explicit and reviewable, never hidden.
SOURCE_REGISTRY: Dict[str, SourceSpec] = {
    # Traditional market data — 35% (the only fully live bucket today)
    "price_volume":        SourceSpec("market_data", 0.35, "daily (signal horizon 20-60d)", "live"),
    # SEC filings / earnings / insider — 20%
    "sec_edgar_fundamentals": SourceSpec("filings", 0.10, "every 5 min (intended)", "shadow_only"),
    "sec_form4_insider":      SourceSpec("filings", 0.05, "every 10 min (intended)", "shadow_only"),
    "sec_13f":                SourceSpec("filings", 0.03, "quarterly", "not_implemented"),
    "congress_trades":        SourceSpec("filings", 0.02, "daily", "not_implemented"),
    # Reddit — 10%
    "reddit_hn_forums":    SourceSpec("reddit", 0.10, "every 15 min (intended)", "infeasible"),
    # GitHub — 10%
    "github_dev_activity": SourceSpec("github", 0.10, "every 15 min (intended)", "not_implemented"),
    # Macro / economic — 10%
    "macro_fred":          SourceSpec("macro", 0.06, "hourly", "shadow_only"),   # macro-regime gate FAILED
    "cftc_cot":            SourceSpec("macro", 0.02, "weekly", "not_implemented"),
    "treasury_bls":        SourceSpec("macro", 0.02, "daily", "not_implemented"),
    # News — 5%
    "news_apis":           SourceSpec("news", 0.05, "every 1 min (intended)", "infeasible"),
    # Crypto-native — 5%
    "crypto_onchain_tvl":  SourceSpec("crypto_native", 0.05, "hourly (intended)", "not_implemented"),
    # Discord / Telegram — 5%
    "discord_telegram":    SourceSpec("messaging", 0.05, "every 15 min (intended)", "infeasible"),
}

# category target weights (for the self-adjusting weighting model)
CATEGORY_WEIGHTS: Dict[str, float] = {
    "market_data": 0.35, "filings": 0.20, "reddit": 0.10, "github": 0.10,
    "macro": 0.10, "news": 0.05, "crypto_native": 0.05, "messaging": 0.05,
}


def live_weight_fraction() -> float:
    """Fraction of the intended source-weight budget that is actually live.

    A blunt honesty metric: how much of the designed information diet the engine
    truly ingests today. (Currently ~price/volume only.)"""
    return round(sum(s.weight for s in SOURCE_REGISTRY.values() if s.status == "live"), 4)


def source_available(name: str) -> bool:
    return SOURCE_STATUS.get(name, SOURCE_REGISTRY.get(name, SourceSpec("", 0, "", "x")).status) in _USABLE


def get_signal(name: str):
    status = SOURCE_STATUS.get(name) or (SOURCE_REGISTRY[name].status if name in SOURCE_REGISTRY else "unknown")
    if status not in _USABLE:
        raise NotImplementedError(
            f"data source '{name}' is NOT AVAILABLE (status={status}). "
            "It is not wired into the live engine; see docs/MONITORING_SPEC.md.")
    raise NotImplementedError(f"'{name}' is live but has no standalone signal accessor.")
