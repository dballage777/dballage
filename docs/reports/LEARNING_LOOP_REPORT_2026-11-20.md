# Trade Bot — Learning Loop Report (2026-11-20)

> **Data source:** produced by `python -m experiments.audit_shadow`. It replays
> the learning loop from the committed ledgers twice: once on the **logged**
> returns (what the loop actually saw) and once on returns **re-marked against
> real yfinance closes** (what it should have seen). Raw outputs:
> [`data/learning_replay.csv`](data/learning_replay.csv),
> [`data/drift_history.csv`](data/drift_history.csv),
> [`data/summary.json`](data/summary.json). Paper/shadow only. Not investment advice.

The system has three learning loops. Their status:

| loop | what it does | status this period |
|---|---|---|
| **1. Sleeve reweighting** (`v12/learning/reweight.py`) | shifts `full_system` capital toward the sleeve with the better realized paper Sharpe | **Active, but it learned from corrupted data and has a design flaw** |
| **2. Drift / decay monitor** (S6, `v12/monitoring/drift.py`) | flags sleeves whose edge is decaying or changing | **Running; flags everything, including the benchmark; drives nothing** |
| **3. Research cycle + version log** (LangGraph agents, `docs/RESEARCH_LOG.md`) | proposes, tests and grades new ideas; remembers every attempt | **Not run in automation; agent memory does not persist** |

---

## Loop 1: Sleeve reweighting

### What it actually did
* It switched on **2026-06-28** and from **2026-07-23** onward it set the stock
  sleeve's exposure multiplier to **0** on **84 of 105 runs**. Crypto stayed
  at 1.0 throughout.
* As a result, `full_system` logged **the same return as `crypto_full_goal`** on
  **83 of 104 days**. For four months the "full system" was effectively the
  crypto sleeve alone.
* The input it trusted: a 63-day crypto Sharpe of **~2.8–3.7**, against a stock
  Sharpe of **−1 to −4**.

### What it would have done on real prices
* The crypto Sharpe it relied on was inflated by stale days (§2 of the full
  report). On real prices the crypto Sharpe fell steadily, from ~3.9 in
  September to **0.13 by Nov 13 and −0.08 by Nov 16**.
* On real prices the stock sleeve would have been partly re-admitted on 14
  runs in late September and October, with multipliers up to 0.63 on Oct 30.
  The logged loop never re-admitted it.
* The two versions disagree on the multipliers on **11 runs**, and the gap
  widened over time. **Bad data turned into bad learning:** the loop confidently
  concentrated into the sleeve whose apparent edge was mostly missing prices.

### Design flaw: when everything loses, it goes back to full risk
`reweight_sleeves` clips negative Sharpes to 0. If **every** sleeve's Sharpe is
≤ 0, the total is 0 and it falls back to **equal weights**. `full_system` then
turns those weights into multipliers of **1.0 for every sleeve**. On real prices
this happened from **2026-11-16** (stock Sharpe −1.44, crypto −0.08). The loop's
answer to "everything is losing" was "restore full exposure to everything." The
docstring says the opposite ("a sleeve with … non-positive Sharpe gets near-zero
weight (it must earn allocation)").

### Other weaknesses
* **No noise floor.** A 63-day paper Sharpe has a standard error of about ±2.
  Differences of this size are mostly noise, yet the loop moves 100% of the
  tilt on them.
* **No data-quality input.** The loop cannot tell a 0.00% caused by a frozen
  price from a real flat day.
* **Single-sleeve concentration.** Multiplier = weight / max weight, so a
  single lucky sleeve takes everything.

---

## Loop 2: Drift / decay monitor (S6)

* It has run on 85 days since 2026-07-22, reading the main ledger read-only.
* **Latest state: all 9 sleeves are flagged "edge decay"** (lower confidence
  bound of Sharpe ≤ 0), and 7 of 9 also carry a Page-Hinkley change-point flag.
  That includes **`market_spy`, the passive benchmark** (flagged since Aug 19).
* When a monitor flags the benchmark it is not separating good sleeves from bad
  ones. With under 100 noisy days, almost no sleeve can show a lower bound
  above 0. The monitor's statistics are honest, but at this sample size it
  carries no information.
* Its inputs are the same stale-corrupted returns.
* It is **observe-only**: no flag changes any allocation. That is the right
  setting until it can tell sleeves apart.

## The exposure timers (S1 / S2)

Both are part of this loop's toolkit. They are also observe-only. Re-marked on
real SPY prices:

| timer | real cum | Sharpe | max DD | time risk-off / neutral | avg exposure |
|---|---|---|---|---|---|
| **vrp_timer** (S2) | **+0.34%** | 0.15 | **−4.1%** | 22 / 22 of 85 days | 0.72 |
| regime_timer (S1) | −3.93% | −0.81 | −7.5% | 1 / 16 of 85 days | 0.92 |
| SPY (reference) | −3.98% | −0.73 | −8.1% | — | 1.00 |

**What it learned:** the VRP timer is the only component whose paper behaviour
supports the validated research finding: the edge is in **exposure gating**,
not stock picking. The composite regime timer barely left risk-on, so it added
nothing in this window.

---

## Loop 3: Research cycle + version learning

* **The agentic research cycle** (`run_research_cycle`) is not scheduled in CI
  or the daily Action. Its memory file (`results/research_memory.json`) is
  under the git-ignored `results/` folder, so no memory exists in the repo.
  As things stand, this loop has **not** accumulated anything since it was last
  run by hand. Its agent hooks are still rule-based (`# LLM-HOOK`).
* **The version log** (`docs/RESEARCH_LOG.md`) is current through V14: technical
  alpha on liquid large-caps is exhausted, the regime gate is the dominant lever,
  and the survivorship (point-in-time) check is still owed. This period adds two
  entries, now recorded in the log (2026-11-20):
  1. **The paper data pipeline silently froze prices on about 30% of days.** Every
     paper "win" so far must be re-validated on clean data.
  2. **Paper trading has not confirmed the equity drawdown edge.** The VRP
     exposure timer is the only component consistent with it.

---

## What the loops learned this period (honest summary)

1. **The reweighting loop learned the wrong thing**, confidently, because its
   inputs were corrupted. It also has a fallback bug that adds risk when
   everything is losing.
2. **The drift monitor learned nothing usable yet.** The sample is too small,
   so it flags everything.
3. **The real lesson came from auditing the loops, not from the loops
   themselves:** data integrity must be checked before performance is trusted.
   This is the V1–V11 lesson again, now in the live pipeline instead of the
   backtest.

## Recommended fixes (before the loop's weights are trusted)

1. **Data freshness gate** (prerequisite for all loops): limit forward-fill,
   check each ticker's last-bar date, and fail or retry instead of logging
   0.00%. Record source and freshness on every ledger row.
2. **Fix the all-negative fallback**: if no sleeve has a positive Sharpe, every
   multiplier should go to a low floor (or cash), **not** 1.0. Add a unit test
   for it.
3. **Add a noise floor**: tilt only when the Sharpe gap exceeds its standard
   error, and shrink toward equal weight otherwise. Cap any one sleeve's share.
4. **Exclude rows flagged stale** from `rolling_performance`.
5. **Drift monitor**: judge each sleeve **relative to the benchmark** (the
   Sharpe difference vs SPY), not on absolute Sharpe, so a falling market does
   not flag everything.
6. **Research loop**: either schedule it with memory committed under a tracked
   path, or record in the docs that it is a manual tool.

---
*Reproduce: `python -m experiments.audit_shadow --out docs/reports/data`.
Paper/shadow only. Not investment advice.*
