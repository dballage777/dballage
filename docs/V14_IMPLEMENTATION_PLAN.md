# V14 Implementation Plan — incremental, analytics-first

Build the measurement instrument first, then add factors one at a time, running
full validation after each. Nothing ships without per-factor evidence.

## Step 1 — Factor-analytics engine (the instrument)  ← do first

New module `v12/evaluation/factor_analytics.py` + report sections. Computes, for
every feature/factor and factor family:

- **Rolling 252-day IC** (and IC by calendar year).
- **IC by market regime** (uses the Step-4 regime labels; until then, by vol
  tercile as a proxy).
- **Factor decay curve**: IC vs forward horizon (5/10/20/40/60/120d) → **alpha
  half-life** estimate.
- **Factor contribution ranking**: marginal OOS IC of each factor over the rest
  (leave-one-in / leave-one-out).
- **Factor correlation matrix** + **redundancy analysis** (cluster |corr|>0.7).
- **Overlap-corrected significance**: deflate ICIR / t-stat by the effective
  independent sample (≈ N_obs / horizon) — fixes the inflated ICIR.

New report sections (append to `evaluation/report.py`):
Factor IC by year · Factor IC by regime · Rolling 252d IC · Factor decay curves
· Factor contribution ranking · Factor correlation matrix · Feature redundancy ·
Alpha half-life.

Validation: re-run the honest harness; the report now carries the scorecard.

## Step 2 — Short interest factor
`v12/data/short_interest.py` (FINRA) + `v12/features/short_interest.py`
(relative SI level + Δ). PIT by publication date. Gate via Step 1.

## Step 3 — Earnings surprise / PEAD
`v12/features/earnings.py`: SUE proxy from EDGAR actuals + announcement-window
price reaction; drift feature. PIT by announcement date. Gate via Step 1.

## Step 4 — Regime classification
`v12/regime.py`: one validated classifier (trend strength, realized vol,
breadth, cross-correlation) → regime label used for IC-by-regime and exposure
modulation. No hand-tuned allocation buckets.

## Step 5 — 13F / 13D / 13G institutional ownership
Extend the EDGAR client; quarterly, lagged to filing date. Gate via Step 1.

## Step 6 — Analyst revisions (only if PIT source secured)

## Step 7 — Factor ablation engine
`experiments/ablation.py`: systematically drop factor families and report the
OOS-IC / Sharpe delta, producing the final factor scorecard.

## Invariants to preserve at every step
- Purged + embargoed walk-forward; executable leakage tests (add a PIT test for
  each new data source — as done for fundamentals & insider).
- Monte-Carlo + stress + survivorship warning on every report.
- vectorbt-compatible returns; Alpaca deployment path (DeploymentAgent gate);
  LangGraph agent compatibility; n8n CLI summary unchanged.
- Each new factor is a separate commit with its own PIT test, gated on marginal
  OOS evidence before it becomes a default.

## Definition of done for V14
An honest **factor scorecard**: for each family, marginal OOS IC, overlap-
corrected significance, decay/half-life, redundancy, and cost-stress survival —
answering "does this family add statistically meaningful alpha?" Models are not
re-tuned until at least one family clears the bar.
