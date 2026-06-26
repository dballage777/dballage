# Backtest Summary — What We Validated, and Why It's Trustworthy

> **Read this first:** "success" here does **not** mean "we beat the market." It
> means (1) we built a *trustworthy* test that doesn't lie to us, and (2) we found
> a small, *statistically real* signal that, over the full 8 years, **roughly
> matches the S&P 500's risk-adjusted return with about half the drawdown** — it
> does **not** beat SPY (Sharpe 0.74 vs 0.74, a tie; SPY wins on raw return).
> Honesty is the whole point.
>
> ⚠️ *Correction (real-data reproduction): an earlier version claimed Sharpe 0.88
> "beats SPY risk-adjusted." That figure was the recent ~18-month window mislabeled
> as the full 8 years. The honest full-sample number is **0.74 — a tie**. The
> drawdown reduction is real; the "beats SPY" claim was not.*

---

## In plain English

Imagine you tried to pick stocks for 8 years (2018–2026). Two ways to judge you:
- **Did you make more money than just buying the S&P 500?** → No. SPY made more.
- **Did you make money more *safely* — steadier, with smaller crashes?** → Yes.

Our strategy turned out to be a **"low-volatility" strategy**: it favors calmer,
steadier stocks and **sits in cash when the market turns dangerous**. Over
2018–2026 it earned *less* than the S&P 500 in total, but with **far less risk** —
its worst drop was about **−19%** vs the S&P's **−34%**, and its
return-per-unit-of-risk was **about the same** (Sharpe 0.74 vs 0.74). Think "a
smoother, less scary ride to a *lower* destination," not "a way to get rich
faster" and not "more reward for the risk."

**The bigger success isn't the strategy — it's the *process*.** Eleven earlier
versions looked amazing but were fooling themselves (a bug called "data leakage"
let them peek at the future). This version was built so it *can't* cheat, and it
honestly reports when something doesn't work. That's why we can trust this result.

---

## What the backtest encompassed

| Element | Detail |
|---|---|
| Period | 2015–2026 data; **out-of-sample test 2018–2026 (~8 years)** |
| Universe | 54 liquid US large-cap stocks (incl. laggards, to fight survivorship bias) |
| Validation | **Purged + embargoed walk-forward**, 32 separate test windows |
| Costs | Commission + slippage charged on every trade |
| Stress tests | Monte-Carlo (1,000 bootstraps), cost stress, fat-tail, "drop best days" |
| Leakage controls | Executable tests that abort if any feature can see the future |
| Risk controls | Drawdown kill-switch, daily loss stop, 3-loss freeze, position caps |

---

## The math of "success" (and the honest caveat)

**Final validated strategy (regime-gated low-vol) vs SPY, 2018–2026, after costs:**

| Metric | Strategy | SPY | Winner |
|---|---|---|---|
| Sharpe ratio (return ÷ risk) | 0.74 | 0.74 | **Tie** ➖ |
| Sortino ratio (return ÷ downside risk) | 0.81 | **0.91** | SPY ⚠️ |
| Calmar (return ÷ worst drawdown) | **0.47** | 0.39 | Strategy ✅ |
| Max drawdown (worst peak-to-trough) | **−19.0%** | −33.7% | Strategy ✅ (half!) |
| Annual volatility | **12.7%** | 19.3% | Strategy ✅ |
| **CAGR (raw annual return)** | 9.0% | **13.2%** | **SPY ✅** |
| **Total return** | 99% | **170%** | **SPY ✅** |

**The signal-quality math:** out-of-sample **rank-IC = 0.0554** with a **fold
t-statistic of 2.04** (above 2 = statistically significant). In English: the
model's stock rankings correlate with future returns more than random chance
would allow — a small but *real* edge. The dollar-neutral long-short probe,
however, is a **modest 0.57** Sharpe, and the engine itself flags that selection
skill is weak once survivorship is netted out — so the value is **drawdown
reduction**, not stock-picking.

> What the tie means: Sharpe = (return − cash) ÷ volatility. Strategy 0.74 vs
> SPY 0.74 means you got **the same risk-adjusted return** — but the strategy got
> there with **far smaller crashes** (−19% vs −34%) and lower volatility. So it's
> a *smoother ride to a lower destination*, not better-paid risk overall (SPY's
> Sortino is actually higher).

---

## Why we believe it (the trust checklist)
- ✅ **No data leakage** — executable tests prove no feature sees the future.
- ✅ **Out-of-sample** — judged only on data the model never trained on.
- ✅ **Survives costs** — edge remains after realistic, turnover-aware costs.
- ✅ **Multiple regimes** — tested through the 2020 crash and 2022 bear market.
- ✅ **Honest about limits** — does NOT beat SPY in absolute return; survivorship
  not fully removed (free data can't); one universe / one decade.

---

## One-line takeaway
**We built a trustworthy testing engine and used it to find a modest, real,
risk-reducing equity strategy — a *defensive* alternative to the S&P 500 that
matches its risk-adjusted return with half the drawdown, but does **not** beat it.
The discipline that produced an honest "it ties, with less risk" — and that caught
and corrected an overstated 0.88 → 0.74 — is the actual achievement.**

*(See `docs/assets/backtest_success_chart.png` for the visual, and
`docs/backtest_metrics.csv` to import into Google Sheets.)*
