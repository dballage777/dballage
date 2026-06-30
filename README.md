# V12 — Quantitative Research Platform

A modular research framework for discovering, validating, and deploying trading
signals that must beat a passive **SPY** benchmark **after** transaction costs,
slippage, walk-forward validation, out-of-sample testing, Monte-Carlo stress,
and regime shifts.

> **Design philosophy (learned from V1–V11):** feature quality > model
> complexity; never trust a backtest that hasn't survived purged, embargoed
> validation; optimise for robustness, not profit. See
> [`docs/RESEARCH_LOG.md`](docs/RESEARCH_LOG.md).

---

## ⚠️ Honesty notice (read this first)

This repository contains a **runnable research framework**, not a finished
money-printer. Two things are deliberately true:

1. **No fabricated metrics.** Every number in a report is produced by running
   the code. Nothing is hand-edited.
2. **Data source matters.** In a network-restricted environment (e.g. this CI
   sandbox) the data layer falls back to a **synthetic** generator with a
   *known, faint* signal. Synthetic results validate the **pipeline**, not real
   alpha — every report is stamped with its data source. Run in
   Codespaces/Colab (which have network access) to get results on real prices
   via `yfinance`.

The first synthetic smoke run, for example, was correctly **REJECTED** by the
risk agent ("edge does not survive +5bps cost stress") — which is exactly the
discipline this platform exists to enforce.

---

## Results (real data, out-of-sample 2018–2026, after costs)

![Strategy vs SPY](docs/assets/backtest_success_chart.png)

The validated strategy is a **regime-gated low-volatility equity strategy**. On
the full 8-year out-of-sample window it **roughly matches SPY's risk-adjusted
return with far smaller drawdowns** — it does **not** beat SPY:

| Metric | Strategy | SPY | |
|---|---|---|---|
| Sharpe | 0.74 | 0.74 | ➖ **tie** (not a beat) |
| Sortino | 0.81 | **0.91** | ⚠️ SPY better |
| Calmar | **0.47** | 0.39 | ✅ |
| Max drawdown | **−19.0%** | −33.7% | ✅ half the crash |
| Annual volatility | **12.7%** | 19.3% | ✅ |
| **CAGR (raw return)** | 9.0% | **13.2%** | ⚠️ **SPY wins** |
| Total return | 99% | **170%** | ⚠️ SPY wins |

Signal quality: out-of-sample rank-IC **0.0554**, fold **t-stat 2.04** (>2 =
statistically significant), across 32 walk-forward folds (2018–2026), leakage-
checked, cost- and Monte-Carlo-stressed. The dollar-neutral long-short probe is a
**modest 0.57** Sharpe — some real selection skill, weak once survivorship nets out.

> **Honest verdict:** a **lower-risk, lower-drawdown *defensive* alternative** to
> the S&P 500 — about the same risk-adjusted return with roughly **half the
> crash** — **not** a way to beat it. The signal is real and statistically
> significant; the *edge* is mostly drawdown reduction (the regime gate), not
> stock-picking alpha.
>
> ⚠️ *An earlier version of this table reported Sharpe 0.88 — that was the recent
> ~18-month window mislabeled as the full 8 years. The honest full-sample number
> is 0.74 (a tie with SPY). Corrected on real-data reproduction.*

📄 Full write-up: [`docs/BACKTEST_SUMMARY.md`](docs/BACKTEST_SUMMARY.md) (plain-English + technical) ·
📊 [`docs/backtest_metrics.csv`](docs/backtest_metrics.csv) (Google-Sheets-ready) ·
📋 design spec: [`docs/SYSTEM_SPEC.md`](docs/SYSTEM_SPEC.md) ·
🔎 what's built vs not: [`docs/GOAL_IMPLEMENTATION_AUDIT.md`](docs/GOAL_IMPLEMENTATION_AUDIT.md)

---

## Quickstart

```bash
pip install -r requirements.txt          # core works with just numpy/pandas/scikit-learn

# Fast smoke test (short window, 2 models)
python -m experiments.run_experiment --quick

# Full experiment (10y, full universe, model zoo + stacking)
python -m experiments.run_experiment

# Contribution model: none | dca | variable
python -m experiments.run_experiment --dca dca

# Full agentic research cycle (Research -> ... -> Deployment)
python -m experiments.run_research_cycle

# Tests (leakage + feature correctness + signal recovery)
python -m pytest tests/ -q

# Framework self-validation: proves the stack recovers real signal,
# does NOT invent fake signal, and aborts on leakage
python -m experiments.validate_framework
```

### Framework self-validation (why you can trust a result here)

Before trusting any backtest, `experiments/validate_framework.py` checks three
properties on synthetic data with a *known* ground truth (averaged over seeds):

| planted signal | OOS rank-IC | meaning |
|---|---|---|
| none | ≈ 0 (−0.01) | no hallucinated alpha |
| faint | ≈ 0 (+0.00) | faint signal genuinely at the noise floor |
| strong | **+0.33** | real signal is cleanly recovered |

…and an injected leaked feature makes the validation gate **abort**. This is the
structural antidote to the V1–V9A "fake alpha" failures. It runs in CI on every
push.

Outputs land in `results/`: a markdown report, a metrics JSON, and an equity CSV.

### Google Colab / GitHub Codespaces

**👉 Step-by-step guide: [`docs/RUN_IT.md`](docs/RUN_IT.md)** (which environment, what to click, what to check).

```python
!git clone <this-repo> && cd dballage
!pip install -r requirements.txt
!python -m experiments.run_experiment        # real yfinance data when network is open
```

---

## Architecture

```
v12/
├── data/          yfinance loader + on-disk cache + synthetic fallback
├── features/      momentum · trend · volume · volatility · mean-reversion ·
│                  breadth · cross-sectional ranks   (all point-in-time)
├── models/        unified zoo (ridge, elasticnet, rf, xgb, lgbm, catboost) + stacking
├── validation/    purged & embargoed walk-forward + executable leakage assertions
├── portfolio/     equal / inverse-vol / risk-parity weighting (capped)
├── risk/          vol-targeting · Kelly · CVaR · cash-regime overlay
├── backtest/      daily engine w/ costs+slippage + DCA contribution model + SPY bench
├── evaluation/    metrics · rank-IC · Monte-Carlo bootstrap · stress tests · report
├── agents/        LangGraph cycle: Research→Feature→Backtest→Eval→Risk→Deploy + memory
└── utils/
experiments/       run_experiment.py · run_research_cycle.py
automation/        n8n workflow + CLI wrapper for nightly runs/alerts/retraining
tests/             leakage & feature point-in-time guarantees
```

See [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) for module-by-module detail.

---

## How leakage is prevented (the V1–V9A failure mode)

1. **Point-in-time features.** Every feature uses only rolling/expanding windows
   of past+current data. `tests/test_features.py` asserts that perturbing a
   *future* price never changes a *past* feature.
2. **Forward-only target.** The label is the cross-sectionally de-meaned forward
   `h`-day return — the only column that looks ahead.
3. **Purged + embargoed walk-forward.** Training rows whose label window overlaps
   the test fold are dropped (purge); a buffer ≥ `h` separates folds (embargo).
4. **Executable leakage gate.** `assert_no_leakage` aborts the run if any fold
   overlaps, any purge gap is too small, or any feature has `|corr|>0.95` with
   the target.

---

## Contribution (DCA) model

Initial capital **$500**, **+$100 every ~2 weeks**. Supported modes: `none`,
`dca`, and `variable` (buy-the-dip tilt). Time-weighted returns (Sharpe/DD) are
computed *without* contributions; the headline "Strategy $X vs SPY $Y" uses a
money-weighted account where **SPY gets the identical contribution schedule**.

---

## Roadmap

- [ ] Live `yfinance` runs + cached real-data baselines committed as references.
- [ ] Fundamentals / alt-data features (raise the technical-only IC ceiling).
- [ ] Alpaca paper-trading adapter wired to the DeploymentAgent gate.
- [ ] Replace rule-based agent hooks (`# LLM-HOOK`) with LLM-driven research.
- [x] vectorbt cross-check of the in-house backtest engine (`experiments/vectorbt_crosscheck.py`).
