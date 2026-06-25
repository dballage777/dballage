# System Specification — Autonomous Systematic Multi-Asset Trading Engine

> This is the **design specification** (intended behavior) for the trading system,
> written out explicitly for review/feedback. It describes the *goals*, not the
> current implementation. For what is actually built vs. not, see
> [`GOAL_IMPLEMENTATION_AUDIT.md`](GOAL_IMPLEMENTATION_AUDIT.md).

A statistical decision engine (not a predictor) that allocates capital across
stocks and crypto using probabilistic expected value (EV), regime detection, and
adaptive learning.

**Core objective:** maximize risk-adjusted returns (Sharpe, Sortino) while
minimizing drawdowns, tail risk, overfitting, liquidity failure, regime collapse.
**Primary rule: capital preservation > returns > growth.**

---

## 1. Capital structure (dynamic, not fixed)
- 0–100% **Cash** (default safe state; never required to be fully invested)
- 0–70% **Stocks**
- 0–30% **Crypto**

## 2. Universe
**Stocks:** 25–40 liquid equities/ETFs.
- Core: SPY, QQQ, AAPL, MSFT, NVDA, AMZN, META, TSLA
- Secondary: sector ETFs + mid caps

**Crypto:** 5–12 assets max.
- Core: BTC, ETH · Secondary: large-cap alts only

**Microcap rule (strict, experimental only):**
- Stocks: max 10% allocation, max 1% per position
- Crypto: max 5% allocation, max 0.5% per token

## 3. Strategy structure
- **Long-term (70–80%):** trend following, factor investing, macro-aligned
- **Medium-term (15–25%):** swing trading, momentum cycles, mean reversion
- **Short-term (5–10%):** intraday / volatility, event-driven

## 4. Expected-value (EV) engine
`EV = P(win) × Avg Win − P(loss) × Avg Loss`
**Trade only if EV > 0 after fees, slippage, and risk adjustment.**

## 5. Regime detection
Classify market as one of: **Bull Trend · Bear Trend · Sideways/Chop · High
Volatility · Crisis · Recovery.** Strategy weights adjust dynamically per regime.

## 6. No-trade conditions → DEFAULT = CASH
Do not trade if: EV ≤ 0 · liquidity insufficient · spread too wide · confidence
< 60% · regime conflict · risk budget exhausted · correlation overload.

## 7. Position sizing (risk-capped Kelly)
- Fractional Kelly, **max 25%** of full Kelly
- Hard caps: **Stocks 5–8%** per position · **Crypto 8–12%** per position
- Adjust by volatility regime

## 8. Risk management (hard rules)
- Max portfolio drawdown: **15–25%**
- Daily loss stop: **3–5%**
- **3 consecutive loss days → freeze trading**
- No averaging down unless EV improves

## 9. Cash rule
Cash is a valid position. The system may hold 0–100% cash indefinitely if EV is
insufficient, regimes are unclear, or risk is elevated.

## 10. Biweekly capital (e.g., +$100 biweekly)
New deposits are **not** auto-invested — held in cash until EV thresholds are
met. Max idle period: **90 days**.

## 11. Data sources & initial weighting (self-adjusting)
- Market + Price Data: **30%**
- Filings / Insider (SEC EDGAR 10-K/Q/8-K, Form 4, 13F/13D/13G, congress): **25%**
- Alternative data (Reddit/GitHub/etc.): **20%**
- Macro (FRED/BLS/Fed/COT): **10%**
- News (Reuters/Bloomberg/WSJ/FT): **10%**
- Messaging apps (Discord/Telegram): **5%**

Weights self-adjust based on each source's predictive performance.

## 12. Learning loop
For every signal track: accuracy · Sharpe contribution · drawdown impact · decay
rate. Increase weight if predictive; decrease if noisy.

## 13. Portfolio structure
- **Core (95%):** stable, high-liquidity, long-term strategies
- **Experimental (5%):** microcaps, emerging narratives, high-variance trades
- **Shadow (unlimited paper):** all new ideas tested here first

## 14. Narrative system
Track lifecycle: emergence → acceleration → peak → decline. Avoid crowded
late-stage narratives.

## 15. Futures rule
Not in v1. May be added only after 12+ months successful paper trading, a stable
equity curve, and controlled drawdowns.

## 16. Decision hierarchy
1. Regime detection → 2. EV calculation → 3. Risk validation → 4. Correlation
check → 5. Position sizing (Kelly capped) → 6. Execution decision.

## 17. Required output (every decision)
Asset · Action (BUY / HOLD / SELL / NO TRADE) · EV score · Risk score ·
Confidence · Position size · Reasoning · Data sources used.

---

### Final behavior
Adaptive (not binary) · probabilistic (not absolute) · continuously active (not
stalled) · risk-aware (not overly restrictive). **Objective: maximize
risk-adjusted returns while preserving capital — not minimize activity.**
