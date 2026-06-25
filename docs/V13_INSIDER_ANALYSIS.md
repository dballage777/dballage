# Institutional Analysis — `v13_insider` (2018–2026 OOS)

Evidence base: our own OOS backtests. Community sources are idea generators only.

## Version comparison (broad universe, 60d, ~8y honest OOS)

| Run | IC | LS Sharpe | LS maxDD | Strat Sharpe vs SPY | +5bps cost-stress | $ vs SPY |
|---|---|---|---|---|---|---|
| oos2018 (technicals) | 0.048 | 0.51 | — | 0.73 / 0.74 | — | lose |
| fund_v1 (+fundamentals) | 0.040 | 0.63 | −14.3% | 0.77 / 0.74 | +0.022 | $36.8k / $37.2k |
| v13_sn (+sector-neutral) | 0.041 | 0.63 | −10.0% | **0.80** / 0.74 | **+0.045** | $36.2k / $37.2k |
| **v13_insider (+insider)** | **0.039** | **0.68** | **−8.4%** | **0.69** / 0.74 | **−0.042** | **$33.6k** / $37.2k |

## 1. Executive summary
Insider Form 4 data is now integrated with good coverage. Its effect is
**marginal and mixed**: the long-short spread Sharpe rose 0.63→0.68 and its
drawdown improved, BUT aggregate IC fell, the (deployable) long-only Sharpe fell
0.80→0.69 (now below SPY), the +5bps cost-stress went **negative (−0.042)**, and
no insider feature appears in the top-15 importances. **By our gate (must improve
the spread AND survive cost-stress), insider FAILS the cost-stress half.** Net:
not a clear win; likely re-shuffling near the noise floor, not robust new alpha.
Deployment remains NOT ready.

## 2. What improved
- Long-short Sharpe 0.63→0.68; long-short maxDD −10.0%→−8.4% (cleaner spread).
- Insider data pipeline: 45 quarters, ~900–2,900 tx/qtr, 54/54 coverage, fast & cached.

## 3. What degraded
- Aggregate IC 0.041→0.039. Long-only Sharpe 0.80→0.69 (drops below SPY 0.74).
- **+5bps cost-stress Sharpe +0.045→−0.042 (now negative)** — the edge no longer
  survives realistic costs. This is the headline regression.
- Money-weighted result $36.2k→$33.6k (further behind SPY).

## 4. Root-cause analysis
Insider purchases, even with good raw coverage, are **sparse per name-date** and
their cross-sectional rank is mostly neutral (0). The model barely weights them
(absent from top-15). The small long-short gain coincides with a long-only loss
and higher turnover (0.81→0.84) → consistent with insider features **reshuffling
the extremes** rather than adding broad, robust ranking skill. The negative
cost-stress is driven by that extra turnover against a razor-thin edge.

## 5. Comparison vs prior versions
The trajectory is flat-to-noisy: LS Sharpe 0.51→0.63→0.63→0.68, IC ~0.04–0.05,
and the strategy has **never** beaten SPY's absolute return on the honest 8y
window. Fundamentals delivered the only durable, attributable lift (value/quality
features persist in top importances). Sector-neutral cleaned risk. Insider is
inconclusive-to-negative.

## 6. Factor families showing real alpha (evidence)
- **Value / Quality (fundamentals):** YES — `f_earnings_yield`, `f_roe`,
  `f_book_to_price` consistently top-15. Modest but real.
- **Low-vol / momentum / relative-strength (technicals):** YES — `atr_pct`,
  `rs_SPY/rs_QQQ/rs_XLK`, `mom_120`, `realized_vol_*` dominate. The workhorses.
- **Insider:** NOT demonstrated — absent from importances, fails cost-stress.

## 7. Factor families to remove / gate
- **Insider:** turn OFF by default pending the ablation engine's marginal-IC +
  significance verdict. Don't ship a factor that worsens cost-stress.
- **Redundant technicals:** ~57 features with heavy collinearity (many vol/mom
  variants) — prune via redundancy analysis; smaller sets generalize better.

## 8. Evidence of overfitting
- Tree models went **negative** earlier (anti-predictive) → noise-fitting.
- Aggregate metrics swing materially when one factor is added (strat Sharpe
  0.80→0.69) → we are operating near the noise floor; small changes move outcomes.
- ic_std 0.21 ≫ ic_mean 0.039 → low signal-to-noise per period.

## 9. Evidence of underfitting
- Minimal. Linear models are appropriate (trees did worse). Flat IC reflects a
  genuinely **weak signal**, not an under-powered model. More capacity hurt.

## 10. Survivorship risk assessment
HIGH and unaddressed. Static current-constituents universe (warning stamped).
The long-short partially cancels it, but absolute (§4) numbers are inflated; true
edge is lower. **Point-in-time membership is the biggest open validity gap.**

## 11. Data quality assessment
- Prices: good (yfinance, 2,882 days). Fundamentals: good (54/54 EDGAR, PIT).
- Insider: good coverage (45 quarters), PIT by filing date. 2026Q2–Q4 absent
  (future) — fine, OOS ends 2026-03.
- Gaps: delisted-name prices (survivorship), PIT analyst estimates (not attempted).

## 12. Deployment readiness
NOT READY. Fails three blockers: (a) does not beat SPY (absolute), (b) edge does
not survive +5bps costs, (c) survivorship not removed. Paper trading would be
premature.

## 13. Top 10 by expected ALPHA impact
| # | Improvement | Exp. benefit | Risk | Conf | Dev | Evidence |
|---|---|---|---|---|---|---|
| 1 | Factor-analytics/ablation engine (measure marginal IC + significance) | Direction clarity; prune dead factors | Low | 80 | 1–2d | metrics swing per factor; can't attribute now |
| 2 | Earnings surprise / PEAD factor | +0.005–0.015 IC | Med | 55 | 2–3d | robust anomaly; orthogonal |
| 3 | Short-interest factor | +0.003–0.010 IC | Med | 55 | 2d | short-leg predictive (lit) |
| 4 | Feature pruning/redundancy | +Sharpe via less noise | Low | 60 | 1d | 57 collinear features |
| 5 | Beta-overlay mode (to chase absolute SPY) | path to beat SPY | High | 35 | 2d | market-neutral can't out-return bull SPY |
| 6 | 13F institutional Δ ownership | +0.003–0.010 IC | Med | 45 | 2–3d | crowding/smart-money |
| 7 | Regime-conditioned exposure | +Sharpe via DD control | Med | 40 | 2–3d | overfit risk |
| 8 | Horizon ensemble (20+60d blend) | small IC stability | Med | 45 | 1d | dose-response earlier |
| 9 | Analyst revisions (only w/ PIT data) | +0.005–0.015 IC | High (leakage) | 30 | 3d+ | strongest factor but PIT-risky |
| 10 | Cross-sectional standardization tweaks | marginal | Low | 35 | 0.5d | minor |

## 14. Top 10 by RISK reduction
| # | Improvement | Benefit | Conf | Dev |
|---|---|---|---|---|
| 1 | Reduce turnover (slower rebalance for 60d signal) | restore cost-stress survival | 75 | 0.5d |
| 2 | Point-in-time universe (survivorship removal) | honest numbers | 70 | 2–3d |
| 3 | Overlap-corrected ICIR/significance | stop over-reading signal | 85 | 0.5d |
| 4 | Max-DD kill-switch / daily cutoff (Phase 2) | tail control | 70 | 1–2d |
| 5 | Position caps already 8% / Kelly 25% | sizing discipline | done | — |
| 6 | Factor gating enforced (no cost-stress-negative factor) | prevents bad ships | 80 | 0.5d |
| 7 | Cost-model realism (per-name spread/slippage) | honest costs | 60 | 1d |
| 8 | Correlation-cluster exposure cap | hidden-bet control | 55 | 1d |
| 9 | Walk-forward stability report (per-fold) | catch fragility | 65 | 1d |
| 10 | Monte-Carlo block tuning | robustness honesty | 50 | 0.5d |

## 15. Top 10 by IMPLEMENTATION effort (easiest first)
1. Overlap-corrected ICIR (0.5d). 2. Slower rebalance / turnover cut (0.5d).
3. Enforce factor gating (0.5d). 4. Feature pruning (1d). 5. Per-fold stability
report (1d). 6. Cost-model realism (1d). 7. Factor-analytics engine (1–2d).
8. Short interest (2d). 9. PEAD (2–3d). 10. Beta-overlay mode (2d).

## 16. Recommended next experiment
**Build the factor-analytics/ablation engine and run it on the current factor
set** (technical / fundamental / insider). Produce per-family marginal OOS IC +
overlap-corrected significance + decay + redundancy. This converts "aggregate
metrics wiggle" into a hard per-factor verdict — and will formally decide insider
in/out. Pair with a turnover-reduction test to restore cost-stress survival.

## 17. Recommended vNext architecture
V14 as planned: orthogonal sector-neutral PIT factor blocks + **factor-analytics/
gating engine first**, two portfolio modes (market-neutral + beta overlay),
survivorship-free universe, overlap-corrected significance. Keep linear models;
no model tuning until a factor family clears the bar.

## 18. Exact code changes (next increment)
- `v12/evaluation/factor_analytics.py`: rolling/yearly/regime IC, marginal-IC
  (leave-one-out), decay/half-life, correlation+redundancy, overlap-corrected
  significance; new report sections.
- `evaluation/metrics.py`: `information_coefficient` gains `horizon` arg → deflate
  ICIR by effective sample (≈ N/horizon).
- `config.py`: `use_insider` default stays False (gated out until proven).
- `backtest`: expose `rebalance_days` sweep; test 60/90d to cut turnover.

## 19. Validation tests required
- Unit: overlap-corrected ICIR matches a known synthetic case.
- Unit: marginal-IC engine returns 0 for a pure-noise injected factor.
- Existing PIT/leakage tests stay green; add per-factor PIT test as factors land.

## 20. Success metrics required before paper trading
1. Long-short Sharpe ≥ ~1.0 OOS **after** costs, on a **survivorship-free** universe.
2. Edge survives +5bps cost-stress with **positive** Sharpe.
3. Overlap-corrected IC significance (t-stat) meaningfully > 2.
4. Stable across folds/years (no single-period dependence) and MC stability ≥ 1.
5. For absolute SPY-beating: beta-overlay net return > SPY after costs OOS.
Current run meets **none** of these. Honest gap remains wide.

---

## A) Highest-probability path to BEAT SPY (absolute)
Low base rate (~25–35%). Best shot: **beta-overlay mode** — hold core market beta
and tilt by the validated factor composite (value/quality/low-vol/momentum),
sized by vol-target + Kelly, de-risked by a regime kill-switch. Market-neutral
alone (Sharpe ~0.6–0.7) will not out-return a bull-market SPY. Honest caveat:
even this likely only wins risk-adjusted, not always absolute.

## B) Highest-probability path to SURVIVE live trading
**Cut costs/turnover and add hard risk guardrails.** The current edge is
cost-fragile (negative cost-stress). Slow the rebalance, prune turnover, enforce
max-DD kill-switch + daily loss cutoff + position/correlation caps, paper-trade
tiny first. Survival is about not blowing up on a thin edge, not maximizing it.

## C) Highest-probability path to INSTITUTIONAL quality
**Measurement + survivorship + significance.** Build the factor-analytics/ablation
engine, remove survivorship via point-in-time membership, fix overlap-corrected
significance, and report per-factor attribution every run. Institutional quality
is defined by *honest measurement and risk control*, which we can fully achieve
even if the alpha stays modest — and which we're closer to than to beating SPY.
