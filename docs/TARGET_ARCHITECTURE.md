# Target Architecture (full vision) — captured & gated

This file records the **complete intended system** (multi-asset autonomous
trading engine + research-source ingestion) so the vision is preserved. It is a
**target**, not a build order. Each block is gated in `ROADMAP.md`: we build it
only once the prerequisite evidence exists. Building it all now — on a signal
that is real-but-modest and not yet validated out-of-sample — would recreate the
V1–V11 failure (lots of hand-tuned parameters, an impressive-looking backtest,
and no idea what actually works).

> Current status of the underlying signal (see RESEARCH_LOG.md): one slow (60-day)
> linear cross-sectional factor, long-short Sharpe ~1.37, **true** ICIR ~1.5, on a
> still-survivorship-biased universe, OOS now extended to ~2018–present. Promising,
> unproven. Overall project rating ~5/10; "tradeable alpha" 3/10.

---

## A. Asset allocation & universe  🔒 Phase 5 (crypto) / partially Phase 0 (stocks)

- 70% stocks/ETFs, 30% crypto.
- Stocks: 25–40 names, core 10–15 (SPY/QQQ/AAPL/MSFT/NVDA/AMZN/META/TSLA), secondary rotation.
- Crypto: 5–12 assets, core BTC/ETH, top-liquidity only.

**Status:** stocks ≈ built (broad 54-name universe). Crypto = 0%, not built.
**Gate:** crypto only after the stock signal is validated and a paper-execution
loop exists. The 70/30 split is a *deployment* parameter — meaningless until
there is a validated thing to deploy.

## B. Strategy-horizon allocation  🔒 Phases 0 & 3

- 70–80% long-term (trend/factor/mean-reversion/DCA)
- 15–25% medium-term swing (3–21d)
- 5–15% short-term / intraday (scalping, vol breakout)

**Status:** one single-horizon strategy exists. We have evidence the **long/slow**
horizon (60d) is where our signal lives.
**Reality check on intraday:** the engine uses **daily** bars. Scalping / intraday
momentum is **not possible** without intraday data, a low-latency execution path,
and microstructure-aware costs — that's a different system. It stays out of scope
until (and unless) there's a reason to build intraday infrastructure.

## C. Asset scoring engine (0–100)  ⚠️ design conflict

Proposed: score each asset daily on Trend(25) + Volume(15) + Volatility(15) +
Momentum/News(20) + MeanRevDistance(25); allocate by score buckets (≥80 full,
65–79 medium, 50–64 small, <50 none).

**Honest issue:** this hand-weighted 0–100 scheme is a *less rigorous version of
what the ML model already does* — it ranks assets by a blend of the same factors.
Replacing a walk-forward-validated, leakage-checked model with arbitrary fixed
weights (why 25 for trend, 20 for news?) would be a **step backward** and a fresh
overfitting surface. If we want interpretable scores, we derive them *from* the
validated model, not from guessed weights. The score→position-size mapping
(buckets) is reasonable and can be adopted once sizing is validated (Phase 1).

## D. Portfolio weighting & concentration  🔒 Phase 1

- Top 5 positions 40–50% of stock capital; next 10 30–40%; rotation 10–20%.
- Crypto: BTC 40–50%, ETH 25–35%, alts 15–35%.

**Status:** inverse-vol / risk-parity weighting with an 8% cap exists. Tiered
concentration not built. **Gate:** after the signal is validated (concentration
amplifies whatever edge — or error — exists).

## E. Risk rules  🔒 Phase 1–2 (mostly backtestable now)

- Max single stock 5–8% (✅ cap now 8%), crypto 10–12%.
- Max portfolio drawdown 15–25%; daily loss cutoff 3–5%; stop after 3 losing days.
- Reduce exposure in high-vol regimes (🟡 partial via cash overlay + vol target).

**Status:** position cap + vol-target + cash overlay live; DD kill-switch / daily
cutoff / consecutive-loss halt = Phase 2 (backtestable overlays). Each threshold
is a free parameter — chosen on a validation window, not hand-tuned to flatter
the backtest.

## F. Regime detection & rebalancing  🔒 Phase 3

- 4 regimes (trend up/down, chop, crisis) → strategy reweighting.
- Rebalance stocks ~30d, crypto 14–30d, emergency if vol > 2× baseline.

**Status:** only a continuous risk-on/off cash overlay exists. The 4-regime
classifier + regime allocation buckets are unbuilt and must be *shown to improve
OOS* before being trusted.

## G. Decision logic / execution (buy/sell/hold, EV gate)  🔒 Phase 4

Per-trade EV>0, trend-alignment, liquidity, risk-capacity gates; sell on score<50
/ reversal / DD>8–12% / regime shift. **Status:** none built; requires the live
Alpaca order loop (stubbed today). This is where these rules actually run.

## H. Research-source ingestion (the 40 sources)  🔒 separate project, Phase 4+

Reddit (r/algotrading, r/quant, …), Quantocracy, SSRN, arXiv q-fin, GitHub
trending, HN, Seeking Alpha, crypto/web3 (ethresear.ch, Messari, DeFiLlama),
Discord/Telegram, etc.

**Status:** not built. This is a **RAG / news-ingestion subsystem** for the
`ResearchAgent` (the `# LLM-HOOK` in `v12/agents/nodes.py`) — it informs *what to
research*, it does **not** backtest or generate the trading signal. It's a
distinct effort, much of it gated behind APIs/scraping that this environment's
network policy blocks. It belongs *after* there's a validated strategy worth
feeding ideas to. Useful eventually; irrelevant to whether the current signal is
real.

---

## Why the gating is non-negotiable

Every percentage above (70/30, 75/20/5, 40–50% BTC, score thresholds 80/65/50,
DD 15–25%, …) is a **free parameter**. The spec has ~30+ of them. Fit 30 knobs to
one decade of data on an unproven signal and you get a backtest that looks
incredible and predicts nothing — which is *exactly* what V1–V9A did. We earn each
layer with out-of-sample evidence, in the ROADMAP order. That discipline is the
only thing separating V12 from the eleven versions that failed.
