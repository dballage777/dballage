"""Static sector map for the universe (GICS-style buckets).

Used for sector neutralization: ranking signals and de-meaning the target
*within* sector removes sector bets, so the model is rewarded for picking the
best name in a sector rather than for tilting toward whatever sector ran. This
usually lifts IC modestly and the long-short Sharpe more (cleaner, lower-vol
spread). Unknown tickers fall into "Other".
"""
from __future__ import annotations

from typing import Dict

SECTOR_MAP: Dict[str, str] = {
    # Information Technology
    "AAPL": "Tech", "MSFT": "Tech", "NVDA": "Tech", "AVGO": "Tech", "ORCL": "Tech",
    "CSCO": "Tech", "INTC": "Tech", "IBM": "Tech", "ADBE": "Tech", "CRM": "Tech",
    "QCOM": "Tech", "TXN": "Tech", "AMD": "Tech",
    # Communication Services
    "GOOGL": "Comm", "META": "Comm", "NFLX": "Comm", "DIS": "Comm", "CMCSA": "Comm",
    "VZ": "Comm", "T": "Comm",
    # Consumer Discretionary
    "AMZN": "ConsDisc", "TSLA": "ConsDisc", "HD": "ConsDisc", "NKE": "ConsDisc",
    "MCD": "ConsDisc", "F": "ConsDisc", "GM": "ConsDisc",
    # Financials
    "JPM": "Fin", "BAC": "Fin", "WFC": "Fin", "GS": "Fin", "V": "Fin", "MA": "Fin",
    "AXP": "Fin",
    # Health Care
    "UNH": "Health", "JNJ": "Health", "PFE": "Health", "MRK": "Health",
    "ABBV": "Health", "LLY": "Health", "BMY": "Health", "CVS": "Health",
    # Consumer Staples
    "WMT": "Staples", "PG": "Staples", "KO": "Staples", "PEP": "Staples", "COST": "Staples",
    # Energy
    "XOM": "Energy", "CVX": "Energy",
    # Industrials
    "CAT": "Indust", "BA": "Indust", "GE": "Indust", "MMM": "Indust", "HON": "Indust",
}


def get_sector(ticker: str) -> str:
    return SECTOR_MAP.get(ticker, "Other")
