# V13 Institutional Research Review — Pre-Build Alpha Assessment

**Mandate:** estimate the expected alpha contribution of six proposed
enhancements, then design a V13 architecture aimed at beating SPY in a fully
out-of-sample, walk-forward, survivorship-bias-free framework. No code until this
review is approved.

## 0. Where we stand (the honest baseline)

| Config (broad universe, 60d, 2018–2026 OOS, after costs) | rank-IC | long-short Sharpe |
|---|---|---|
| Technicals only | 0.048 | 0.51 |
| + PIT fundamentals (`fund_v1`) | 0.040 | 0.63 |

Fundamentals improved the *tradeable* spread (0.51→0.63) and drawdown, with
`f_roe`, `f_earnings_yield`, `f_debt_to_equity` ranking among top features — but
the book is market-neutral and still trails SPY's **absolute** return.

**Calibration anchor (from the literature):** for US equities, a single factor
with a monthly rank-IC of **0.05–0.06 is "very strong"**; most real factors run
**0.02–0.03**. Our *combined* IC of ~0.04 is already a respectable multi-factor
number. This sets the scale: nobody is adding a 0.10-IC silver bullet. Gains come
in increments of **0.005–0.015 marginal IC** per orthogonal factor, and they
**diminish** because factors correlate.

## 1. Two different goals — name the bar

- **(A) Market-neutral alpha book** (what we have): long-short, low SPY beta.
  Judged on long-short Sharpe. Beating SPY here means *risk-adjusted*. Realistic
  and ~50–60% achievable to reach Sharpe ~0.8–1.0.
- **(B) Beat SPY in absolute return, after costs, OOS, survivorship-free** (your
  stated mandate). This is **much harder.** A 0.8-Sharpe market-neutral book does
  **not** out-return a bull-market SPY. To beat SPY absolute you must run
  long-biased (market beta + an alpha tilt), which reintroduces beta and means
  you mostly win by *timing/sizing* beta — a different, harder game. Honest
  probability of clearing bar (B) with retail-accessible data: **~25–35%.**

V13 must be explicit about which bar it targets. Recommendation: build the
**market-neutral alpha engine first** (measurable, gateable), then add a
**beta-overlay mode** to pursue absolute outperformance — and report both.

## 2. Per-enhancement alpha review

Estimates are **marginal** (incremental over our current technical+fundamental
book), after correlation, with wide error bars. "Sharpe lift" is to the
market-neutral long-short book.

| # | Enhancement | Standalone rank-IC (lit) | **Marginal IC (est.)** | **Sharpe lift (est.)** | Free + point-in-time? | Confidence |
|---|---|---|---|---|---|---|
| 1 | **Sector-relative ranking / neutralization** | n/a (de-noiser) | +0.003 – 0.008 | +0.05 – 0.15 | ✅ derived (GICS/ETF map) | Med-High |
| 2 | **Analyst estimate revisions** | 0.03 – 0.06 | +0.005 – 0.015 | +0.05 – 0.20 | ❌ external data; PIT-risky | Med (alpha) / Low (data) |
| 3 | **Earnings revisions / PEAD** | 0.03 – 0.05 | +0.005 – 0.015 | +0.05 – 0.20 | 🟡 dates free, estimates external | Med |
| 4 | **Short interest** | 0.02 – 0.04 | +0.003 – 0.010 | +0.03 – 0.12 | 🟡 FINRA bi-monthly, ~PIT | Med |
| 5 | **Insider ownership / Form 4** | 0.02 – 0.03 (sparse) | +0.002 – 0.008 | +0.02 – 0.10 | ✅ EDGAR (pipe built) | Med-Low (sparse) |
| 6 | **Regime-specific models** | ~0 (not a signal) | ~0 | +0.05 – 0.25 (drawdown control) | ✅ derived | Low (overfit risk) |

### Notes per factor
1. **Sector-relative** is the highest-ROI/lowest-risk item: it's not new alpha,
   it *removes sector bets* from every existing factor, which usually lifts IC a
   little and Sharpe more (cleaner, lower-vol spread). Cheap, free, low overfit.
2. **Analyst revisions** is the strongest *alpha* on the list (well-documented),
   **but** the data is the problem: free tiers (FMP/Finnhub) rarely give true
   point-in-time estimate history → high look-ahead risk. Without PIT estimates
   this factor is a leakage trap. Treat as "high value, gated on PIT data."
3. **Earnings revisions / PEAD** is robust academically. Earnings *dates* and
   actuals are free/PIT; consensus *estimates* are the external piece. A
   surprise/drift factor from actuals + price reaction is partially buildable PIT.
4. **Short interest**: short sellers anticipate bad news months ahead (literature
   is clear). FINRA settlement-date short interest is bi-monthly and reasonably
   PIT. Mostly a **short-leg** signal; helps the long-short more than long-only.
5. **Insider Form 4**: cluster *buying* signals quality, especially in adverse
   situations; sparse (most names, most days = no signal) so its average IC is
   small but **uncorrelated** — value is diversification, not magnitude. Free via
   the EDGAR pipe already built.
6. **Regime models**: not an alpha source — a *conditioning/sizing* layer. Helps
   Sharpe and drawdown by de-risking in hostile regimes, **but** every regime
   definition is a free parameter → real overfit risk. Build as a single
   validated exposure modulator, not 4 hand-tuned buckets.

### Combined expectation (NOT additive)
Factors correlate; costs and signal decay erode the sum. Realistic combined
outcome if **3–4 of these survive OOS gating**:
- Market-neutral long-short Sharpe: **~0.6 → ~0.9–1.1** (base case ~0.9).
- Combined rank-IC: **~0.04 → ~0.05–0.07**.
- Beating SPY **absolute**: only plausible via the beta-overlay mode, and even
  then it's coin-flip-to-unlikely (~25–35%). **Set expectations accordingly.**

## 3. Survivorship-bias removal (the hard requirement)

True removal needs two things:
1. **Point-in-time index membership** — who was actually in the universe each
   day. Buildable from historical S&P 500 constituent-change data → a membership
   CSV → our existing `membership_mask` (already implemented). Free-ish.
2. **Delisted-security prices** — the names that dropped out. **This is the gap:**
   yfinance does not carry most delisted tickers, so the short/loser leg is
   under-represented. Honest limitation; partial mitigations: a broad pre-listed
   universe, or a paid PIT dataset later. We will **state this limitation in every
   report** rather than pretend it's solved.

## 4. V13 Architecture

```
v13/
  universe/      PIT membership (constituent-change CSV) + delisting handling
  factors/       orthogonal factor BLOCKS, each: PIT, cross-sectionally ranked,
                 SECTOR-NEUTRALIZED:
                   - technical (carry over from V12)
                   - value/quality/growth (EDGAR fundamentals, built)
                   - earnings/PEAD            (gated on data)
                   - analyst revisions        (gated on PIT data)
                   - short interest           (FINRA)
                   - insider Form 4           (EDGAR)
  gating/        admit a factor ONLY if marginal OOS rank-IC > threshold AND it
                 survives the +5bps cost stress (kills the factor-zoo overfit)
  model/         linear composite (best so far) vs IC-weighted blend — compared
  regime/        ONE validated exposure modulator (not hand-tuned buckets)
  portfolio/     two modes:
                   (A) market-neutral long-short  -> risk-adjusted vs SPY
                   (B) beta + alpha-tilt overlay   -> absolute vs SPY
  eval/          purged/embargoed walk-forward (have it), full 2018-present OOS,
                 PER-FOLD and PER-FACTOR IC tracking, horizon-aware ICIR (fix the
                 inflated metric), survivorship caveat stamped on every report
```

### Principles (carried from V12, non-negotiable)
- Every factor point-in-time; leakage gate + tests required before inclusion.
- **Factor gating** prevents the factor zoo: no factor ships without positive
  marginal OOS IC after costs. This is the antidote to "throw 30 signals at it."
- Report **both** market-neutral and absolute results, with honest caveats.
- Regime/risk layers (Kelly, caps, DD kill-switch) added only after the alpha
  validates — per ROADMAP.

## 5. Recommended build order (by ROI / risk / cost)

1. **Sector neutralization** (free, low-risk, lifts everything) — do first.
2. **Insider Form 4** (free, PIT, pipe built) — your stated priority, cheap.
3. **Short interest** (FINRA, ~PIT) — adds an orthogonal short-side signal.
4. **PEAD / earnings surprise** from free actuals + price reaction (partial PIT).
5. **Survivorship-free universe** (PIT membership CSV) — run as the honesty check.
6. **Analyst revisions** — ONLY if a point-in-time estimate source is secured;
   otherwise it's a leakage trap, skip it.
7. **Regime modulator** — last, single validated layer.

Each step re-tested on the honest harness; **ship only what clears the gate.**

## 6. Bottom line

- These enhancements are **worth building** and should push the market-neutral
  book from ~0.6 toward ~0.9–1.1 Sharpe — a real, professional-grade result.
- **Beating SPY in absolute return** remains a stretch goal (~25–35%) that
  depends on the beta-overlay mode and favorable conditions. We will pursue it
  but not promise it.
- The single biggest risk is **overfitting via a factor zoo**; the **gating**
  layer is the architectural answer and must not be bypassed.
