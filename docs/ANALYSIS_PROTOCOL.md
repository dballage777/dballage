# Result Analysis Protocol (apply to every backtest)

Standing protocol: every backtest result is analyzed with this structure. The
job is never to optimize the latest model — it is to learn what the result
teaches us about market behavior, alpha, factor/data quality, robustness, and
deployment readiness. **Evidence from our actual OOS backtests is the final
authority.** Community sources (Reddit/Discord/GitHub/HF/etc.) are idea
generators only — never implement because something is popular.

Favor: statistical significance · out-of-sample · walk-forward · Monte-Carlo ·
stress tests · survivorship controls · leakage prevention · deployment
feasibility. Reject: curve-fitting · hindsight bias · leakage · over-optimization
· social-media hype.

## Required sections (every analysis)
1. Executive summary
2. What improved
3. What degraded
4. Root-cause analysis
5. Comparison vs prior versions (table: IC, long-short Sharpe, strat vs SPY)
6. Which factor families show real alpha (per-factor marginal OOS IC)
7. Which factor families to remove (negative/insignificant marginal IC)
8. Evidence of overfitting (train/OOS gap, fold dispersion, fragility to costs)
9. Evidence of underfitting (flat IC, model too constrained)
10. Survivorship risk assessment
11. Data quality assessment
12. Deployment readiness assessment
13. Top 10 improvements ranked by **expected alpha impact**
14. Top 10 improvements ranked by **risk reduction**
15. Top 10 improvements ranked by **implementation effort**
16. Recommended next experiment
17. Recommended vNext architecture
18. Exact code changes
19. Validation tests required
20. Success metrics required before paper trading

Each recommendation carries: Expected benefit · Expected risk · Confidence
(0–100) · Est. dev time · Supporting evidence (cite the specific metric).

## Final outputs (every analysis)
- **A) Highest-probability path to beat SPY**
- **B) Highest-probability path to survive live trading**
- **C) Highest-probability path to institutional quality**

## What I need pasted to run it
- The full report (or at least §3 IC, §4 vs SPY, §4b long-short, §5 MC/stress,
  §6 feature importance) and the run name/flags.
- For data-quality assessment of a new source: the loader's log lines (e.g. the
  per-quarter insider transaction counts) so I can judge coverage.

Principle: prefer robust, repeatable alpha over impressive backtests. Update the
research direction on evidence. Never lock into prior assumptions.
