# Trade Bot — Full Status Report (2026-11-20)

> **Data source:** every number in this report was produced by
> `python -m experiments.audit_shadow`. The audit downloads real yfinance
> closes at audit time and re-marks every paper (shadow) ledger row against
> them. Raw outputs: [`docs/reports/data/`](data/). The 8-year backtest figures
> in §6 are quoted from `docs/V14_RESULTS.md` and were **not** re-run for this
> report. Paper/shadow only, with zero real capital. Not investment advice.

---

## 1. Bottom line

1. **The paper-test ledger is corrupted by stale prices.** In the main ledger,
   **281 of 871 sleeve-days (32%)** logged a return of exactly 0.00% while the
   positions they held really moved. Across all three ledgers the figure is
   **360 of 1,198 (30%)**. Even the passive SPY benchmark logged 0.00% on 30 days,
   including 18 straight trading days in September.
2. **On real prices, no variant made money.** The "crypto-carried" wins in
   `STANDINGS.md` were mostly an artifact of the stale data:

   | variant | ledger says | real prices say |
   |---|---|---|
   | crypto_full_goal | **+4.63%**, Sharpe 1.20 | **−2.16%**, Sharpe −0.22, max DD −15.9% |
   | full_system | +0.38%, Sharpe 0.14 | **−6.22%**, Sharpe −0.79, max DD −15.9% |
   | full_system_max | +1.55%, Sharpe 0.42 | **−5.04%**, Sharpe −0.64 |

3. **The defensive equity strategy did not defend in paper trading.** From Jul 22
   to Nov 19 (the dates SPY was tracked), `equity_validated` was **more** volatile
   than SPY (18.2% vs 15.1% annualized) and fell further (max drawdown −12.8% vs
   −8.1%). Its −5.31% on Nov 5 (SPY −4.41%) accounts for most of the gap. 84 days
   is too short for a verdict, but it is the opposite of the backtest's claim.
4. **The one encouraging result is the VRP exposure timer** (observe-only,
   S2). On real prices it returned +0.34% (Sharpe 0.15, max DD −4.1%) while SPY
   returned −3.98% (max DD −8.1%) over the same run dates. That matches the project's thesis that the
   edge is in cutting exposure, not picking stocks. It is still only 84 days.
5. **No promotion decision can be made from the current ledger.** The ~90-day
   promotion clock should be treated as **reset** from the day the data bug is
   fixed.

---

## 2. Critical finding: stale-price corruption

### Evidence
Stale sleeve-days per variant (logged 0.00%, real return ≠ 0, book held positions):

| variant | rows | stale | | variant | rows | stale |
|---|---|---|---|---|---|---|
| market_spy | 84 | 30 | | full_system | 104 | 39 |
| equity_validated | 102 | 29 | | full_system_max | 98 | 39 |
| equity_full_goal | 102 | 29 | | full_system_v6 | 97 | 26 |
| crypto_full_goal | 104 | 39 | | metals_full_goal | 96 | 28 |
| bonds_full_goal | 84 | 22 | | aggressive_system | 82 | 27 |
| aggr_stock_mom | 81 | 26 | | **aggr_crypto_mom** | 83 | **0** |
| signal timers (each) | 84 | 28 | | | | |

The crypto sleeve is the clearest case. From Sep 9 to Nov 13 it held a constant
36% crypto book, yet it logged non-zero returns only on Mondays. Every Tuesday
to Friday was 0.00%, while BTC/ETH moved 1–3% on many of those days.

### How we know the re-mark is right
The audit uses the runner's exact attribution rule: the previous row's target
weights × each asset's return between the two row dates. On non-stale days it
reproduces the ledger **exactly**: SPY has 0 mismatches across 54 fresh days,
and `aggr_crypto_mom` has 0 stale and 0 mismatched days out of 83. That sleeve
has its own data path, which is why it was spared.

### Cause (identified in code)
`v12/data/loader.py:196` aligns all tickers on a shared date index and runs
`.ffill()` with **no limit and no freshness check**. When yfinance returns
recent rows for some tickers but not others (rate-limiting: the audit itself
received an HTTP 429 from Yahoo), the missing tickers are silently held at
their last price. That has two effects:

* **Logged P&L is 0.00%** for anything priced from the frozen series.
* **The next day's decisions** (regime, EV, sizing) are computed on frozen
  prices too. The stale days damaged the decisions as well as the scorekeeping.

Nothing in the ledger or the daily report records the data source or how fresh
each ticker's price is, so the failure was invisible.

---

## 3. Corrected standings: same window, real prices

Window **2026-07-22 → 2026-11-19** (84–85 trading days), so every variant is
compared over the same dates as SPY.

| variant | real cum | Sharpe | ann. vol | max DD | days invested | (ledger said) |
|---|---|---|---|---|---|---|
| **vrp_timer** (S2, observe-only) | **+0.34%** | **0.15** | — | **−4.1%** | — | −0.98% |
| metals_full_goal | −0.26% | −0.15 | 4.5% | −3.2% | 95% | +0.51% |
| bonds_full_goal | −0.25% | −1.25 | 0.6% | −0.5% | 92% | −0.19% |
| full_system_v6 | −1.23% | −0.09 | 19.5% | −13.6% | 76% | +3.51% |
| equity_full_goal | −2.84% | −0.50 | 15.0% | −8.1% | 83% | −5.39% |
| full_system / _max | −3.04% | −0.39 | 18.8% | −15.9% | 73% | +3.70% |
| crypto_full_goal | −3.08% | −0.40 | 18.8% | −15.9% | 76% | +3.65% |
| regime_timer (S1) | −3.93% | −0.81 | — | −7.5% | — | −5.39% |
| **market_spy (benchmark)** | **−4.09%** | **−0.76** | 15.1% | −8.1% | 100% | −5.27% |
| equity_validated | −7.08% | −1.12 | 18.2% | −12.8% | 69% | −9.66% |

Aggressive (high-risk) ledger, full span: `aggressive_system` **−18.98%** (max DD
**−30.5%**), `aggr_stock_mom` −15.30%, `aggr_crypto_mom` +0.84% (max DD −14.8%),
against SPY (that ledger's own market reference) −2.88%.

**How to read this:** the market fell about 4% in this window, so a cash-heavy book
"beats SPY" by default. Metals and bonds look best mainly because they barely
took risk. Risk taken is what matters: only the VRP timer cut drawdown roughly
in half while keeping some upside. Every full-goal and aggressive book took
**more** drawdown than SPY.

---

## 4. Strategy-by-strategy read

* **equity_validated** (the product candidate): −7.08% on real prices, worse
  than SPY on return, volatility and drawdown. Excluding Nov 5 it was −1.87% vs
  SPY +0.33%. Its regime gate went to 0% exposure only **after** the Nov 5
  drop. The gate reacts after a crash instead of avoiding it, which is the
  failure mode §4b of the roadmap warns about.
* **crypto_full_goal / full_system**: the reported edge was not real. Its
  real max drawdown (−15.9%) is twice SPY's.
* **full_system_v6** (adds metals): least bad of the full-goal systems
  (−1.23%), because the metals book dampened losses.
* **Aggressive sleeve**: confirms its "HIGH-RISK, quarantined" label. Its loss
  was more than 6× SPY's.
* **VRP timer (S2)**: spent 22 of 85 days risk-off and 22 neutral (average
  exposure 0.72). This is the only component whose paper behaviour matches the
  validated research finding (regime/vol gating reduces drawdown).
* **Regime timer (S1)**: 68 of 85 days risk-on (average exposure 0.92). In
  practice it stayed close to SPY.

---

## 5. Live operations status

* The daily GitHub Action is running (latest commit: shadow run 2026-11-20). It
  is now committing to `claude/gallant-planck-p0wd97`, not `main`.
  `main` last received a shadow run on 2026-07-24.
* Current state (Nov 19 report): stocks regime **high_vol**, crypto **crisis**.
  Allocation 15% stocks / 0% crypto / 85% cash. Most books are flat.
* Source coverage is still **35%** (price/volume only; no news, social or options
  flow).
* Drift monitor: **every** sleeve, including the passive SPY benchmark, carries
  an "edge decay" flag. See the learning-loop report.

---

## 6. Where the research stands (unchanged; not re-run)

From `docs/V14_RESULTS.md`, 8-year walk-forward OOS 2018–2026, after costs:
regime-gated low-vol equity. Sharpe 0.74 vs SPY 0.74 (a tie), max DD −19.0% vs
−33.7%, CAGR 9.0% vs 13.2%. Signal OOS rank-IC 0.055, t = 2.04. Still on a
**current-constituents** (survivorship-biased) universe.

**Roadmap:** still **Phase 0**. Paper trading so far has produced **no evidence
for** the equity strategy's drawdown edge (the opposite in this window). It
also produced none for the crypto sleeve once real prices are used. Phases 1–5
stay gated.

---

## 7. Recommended next steps (in order)

1. **Fix the data bug first.** Otherwise every further day of paper data is
   suspect. Cap forward-fill (e.g. `ffill(limit=1)` for equities), check each
   ticker's last-bar date against the expected session, and **fail the run
   loudly** (or retry with backoff) instead of trading on frozen prices. Stamp
   the data source and a freshness flag on every ledger row.
2. **Restate the standings.** Either re-mark the history with
   `experiments.audit_shadow`, or mark the pre-fix period as invalid and restart
   the 90-day promotion clock.
3. **Fix the learning-loop flaws** listed in the learning-loop report before its
   weights are trusted.
4. **Then resume Phase 0 item B:** the survivorship / point-in-time universe
   check on the long-short spread after costs. Live yfinance works in this
   environment now, so it can run here.
5. **Promote the VRP timer from observe-only to a tracked candidate.** It is
   the cheapest test of the "exposure gate is the edge" thesis. Judge it on
   drawdown versus SPY over the full re-validated window.

---
*Reproduce: `python -m experiments.audit_shadow --out docs/reports/data` (needs
network for yfinance). Paper/shadow only. Not investment advice.*
