# ORIGINAL GOALS — Aspirational Design Spec (NOT current state)

> ⚠️ **READ THIS FIRST.** This document is the **original, aspirational design
> target** for the trading system — the goals *as first specified*. It is **NOT a
> description of what is currently built.** Many items below are aspirational, not
> yet implemented, infeasible with available data/infrastructure, or were later
> found by testing to be counterproductive.
>
> For the honest status of what is actually implemented vs. not, see
> `GOAL_IMPLEMENTATION_AUDIT.md`. For what the built system actually achieved, see
> `BACKTEST_SUMMARY.md`.
>
> **Purpose of this doc:** to gather outside opinions on the *original vision*.

---

## System concept
An autonomous quantitative **statistical decision engine** (not a predictor) that
allocates capital across **stocks and crypto** using probabilistic expected value
(EV), regime detection, and adaptive learning.

**Core objective:** maximize risk-adjusted returns (Sharpe, Sortino) while
minimizing drawdowns, tail risk, overfitting, liquidity failure, regime collapse.
**Primary rule: capital preservation > returns > growth.**

## Capital structure (dynamic)
- 0–100% **Cash** (default safe state; never required to be fully invested)
- 0–70% **Stocks**
- 0–30% **Crypto**

## Universe
- **Stocks:** 25–40 liquid equities/ETFs. Core: SPY, QQQ, AAPL, MSFT, NVDA, AMZN,
  META, TSLA. Secondary: sector ETFs + mid caps.
- **Crypto:** 5–12 assets. Core: BTC, ETH. Secondary: large-cap alts only.
- **Microcap rule (strict, experimental only):** Stocks max 10% / 1% per position;
  Crypto max 5% / 0.5% per token.

## Strategy structure
- **Long-term (70–80%):** trend following, factor investing, macro-aligned
- **Medium-term (15–25%):** swing trading, momentum cycles, mean reversion
- **Short-term (5–10%):** intraday / volatility, event-driven

## Expected-value (EV) engine
`EV = P(win) × Avg Win − P(loss) × Avg Loss`.
Trade only if **EV > 0 after fees, slippage, and risk adjustment**.

## Regime detection
Bull Trend · Bear Trend · Sideways/Chop · High Volatility · Crisis · Recovery.
Strategy weights adjust dynamically per regime.

## No-trade conditions → DEFAULT = CASH
EV ≤ 0 · insufficient liquidity · spread too wide · confidence < 60% · regime
conflict · risk budget exhausted · correlation overload.

## Position sizing (risk-capped Kelly)
Fractional Kelly, **max 25%**. Hard caps: **Stocks 5–8%**, **Crypto 8–12%** per
position. Adjust by volatility regime.

## Risk management (hard rules)
Max portfolio drawdown **15–25%** · daily loss stop **3–5%** · **3 consecutive
loss days → freeze trading** · no averaging down unless EV improves.

## Cash rule
Cash is a valid position; may hold 0–100% cash indefinitely if EV insufficient,
regimes unclear, or risk elevated.

## Biweekly capital (e.g., +$100 biweekly)
Deposits are NOT auto-invested — held in cash until EV thresholds met. Max idle:
**90 days**.

## Data sources & initial weighting (self-adjusting)
- Market + Price Data: **30%**
- Filings / Insider (SEC EDGAR 10-K/Q/8-K, Form 4, 13F/13D/13G, congress): **25%**
- Alternative data (Reddit/GitHub/etc.): **20%**
- Macro (FRED/BLS/Fed, CFTC COT): **10%**
- News (Reuters/Bloomberg/WSJ/FT): **10%**
- Messaging apps (Discord/Telegram): **5%**

Weights self-adjust based on predictive performance.

## Learning loop
Per signal track: accuracy · Sharpe contribution · drawdown impact · decay rate.
Increase weight if predictive; decrease if noisy.

## Portfolio structure
- **Core (95%):** stable, high-liquidity, long-term
- **Experimental (5%):** microcaps, emerging narratives, high-variance
- **Shadow (unlimited paper):** all new ideas tested here first

## Narrative system
Track lifecycle: emergence → acceleration → peak → decline. Avoid crowded
late-stage narratives.

## Futures rule
Not in v1. Allowed only after 12+ months successful paper trading, a stable
equity curve, and controlled drawdowns.

## Decision hierarchy
1. Regime detection → 2. EV calculation → 3. Risk validation → 4. Correlation
check → 5. Position sizing (Kelly capped) → 6. Execution decision.

## Required output (every decision)
Asset · Action (BUY / HOLD / SELL / NO TRADE) · EV score · Risk score ·
Confidence · Position size · Reasoning · Data sources used.

---

### Final intended behavior
Adaptive (not binary) · probabilistic (not absolute) · continuously active (not
stalled) · risk-aware (not overly restrictive). **Maximize risk-adjusted returns
while preserving capital — not minimize activity.**

---

*Reminder: the above is the ORIGINAL VISION for feedback. It is not a claim about
what currently exists. See GOAL_IMPLEMENTATION_AUDIT.md for actual status.*
