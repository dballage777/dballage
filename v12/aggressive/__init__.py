"""HIGH-RISK aggressive research sleeve — quarantined, SHADOW / paper only.

This package is deliberately isolated from the validated system (v12.strategies).
It hosts an intentionally aggressive, higher-turnover momentum book used to test —
honestly and forward — whether cranking the risk dial actually pays. It NEVER
allocates real capital, NEVER touches the 7 paper tests or their ledger, and is
gated behind the same >=90-day validation bar as everything else.

Design is evidence-bounded (see docs/AGGRESSIVE_SHADOW.md): the research is blunt
that day-trading illiquid micro-caps at full size is a near-certain loser, so this
keeps the three things every blow-up traces back to OFF the table —
  * illiquidity  -> LIQUID mid/large-cap stocks + top liquid coins only,
  * slippage     -> short-horizon (days-to-weeks), NOT intraday,
  * full Kelly   -> HALF Kelly, never full —
while pushing caps, concentration, and stops as aggressive as the evidence allows.
"""
from .sleeve import (build_aggressive_book, build_aggressive_system,
                     AggressiveBookResult, AggressiveSystemResult,
                     STOCK_BOOK, CRYPTO_BOOK, SYSTEM_BOOK)

__all__ = ["build_aggressive_book", "build_aggressive_system",
           "AggressiveBookResult", "AggressiveSystemResult",
           "STOCK_BOOK", "CRYPTO_BOOK", "SYSTEM_BOOK"]
