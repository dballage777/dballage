# V14 Research Plan — Factor Alpha Discovery (not model tuning)

## Thesis

V12→V13 established: leakage controls work, and technicals + basic fundamentals
produce a **real but weak** signal (long-short Sharpe ~0.63; strategy Sharpe 0.80
vs SPY 0.74 risk-adjusted, but still loses SPY's absolute return). The bottleneck
is **factor quality and data quality, not model complexity** — the gradient-boosted
models were *anti*-predictive; linear is sufficient.

## The central question

> **Does any factor family produce statistically significant, out-of-sample,
> survivorship-aware alpha after costs?**

The goal is NOT to maximize a backtest. It is to get an honest **yes/no per factor
family**, with significance that accounts for overlapping labels. A rigorous "no"
is a successful result.

## Approach: measurement before accumulation

Build the **factor-analytics engine first**, then add factors one at a time, each
gated by the engine. We do not add a factor we cannot individually measure.

Analytics the engine must produce (per factor and per factor family):
- Rolling 252-day IC and IC-by-year.
- IC by market regime.
- Factor decay curve + alpha half-life (how fast the edge dies by horizon/lag).
- Factor contribution ranking (marginal IC over the existing set).
- Factor correlation matrix + redundancy analysis.
- **Overlap-corrected significance** (the 60-day labels overlap; naive ICIR is
  inflated — deflate by the effective independent sample, ~N/horizon).

## Factor families under test (priority order)
1. Insider transactions (Form 4) — built (V13 #2), free + PIT.
2. Short interest (FINRA) — free-ish, ~PIT, short-side signal.
3. Earnings surprise / PEAD — partial PIT from actuals + price reaction.
4. Institutional ownership (13F / 13D / 13G) — EDGAR, quarterly + 45-day lag.
5. Analyst estimate revisions — ONLY if a point-in-time source is secured
   (otherwise a look-ahead trap; skip).
6. Regime classification — a conditioning layer, not an alpha source.

## Success criteria
- A factor is **admitted** only if its marginal OOS rolling IC is positive,
  statistically meaningful after overlap correction, and survives the +5bps cost
  stress.
- Deliverable is an honest **factor scorecard**, not a hero number. Expected
  outcome (priors from V13 review): most factors marginal; 1–2 may add a real
  +0.02–0.10 Sharpe; combined market-neutral Sharpe plausibly ~0.8–1.0. Beating
  SPY in absolute return remains a separate, ~25–35% stretch via a beta overlay.

## Invariants (carried from V12/V13, non-negotiable)
Purged + embargoed walk-forward; executable leakage tests; Monte-Carlo +
stress; survivorship-bias warning on every report; vectorbt / Alpaca / LangGraph
/ n8n compatibility preserved.
