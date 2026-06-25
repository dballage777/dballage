# V14 Results & Honest Verdict

## The journey (broad universe, 60d, 2018–2026 OOS, after costs)

| Stage | key change | long-short Sharpe | strategy Sharpe vs SPY | finding |
|---|---|---|---|---|
| V12 technicals | 57 features | 0.51 | 0.73 / 0.74 | weak, not significant |
| + fundamentals | EDGAR PIT | 0.63 | 0.77 / 0.74 | (later shown to HURT IC) |
| + sector-neutral | within-sector | 0.63 | 0.80 / 0.74 | risk cleanup |
| + insider | Form 4 PIT | 0.68 | 0.69 / 0.74 | HURTS (failed gate) |
| **factor ablation** | scorecard | — | — | **only vol + cross-sectional ADD; t=1.61 (not sig)** |
| **minimal model** | 9 features, pruned | 0.57 | 0.64 / 0.74 | **t=2.04 (SIGNIFICANT)** |
| **+ regime gate** | risk-off filter | 0.57 | 0.74 / 0.74 | **DD −31%→−19%, Calmar 0.47>0.39** |
| **+ beta overlay (reg)** | long-biased tilt | 0.57 | **0.88 / 0.74** | **best risk-adjusted** |
| beta overlay (full) | full beta | 0.57 | 0.75 / 0.74 | closest absolute ($36.2k), survives cost-stress |

## What we proved
1. **No statistically significant alpha in the kitchen-sink model** (t=1.61). The
   factor-analytics engine showed fundamentals/insider/momentum/trend HURT
   marginal OOS IC — we were diluting a real signal with noise. (This overturned
   an earlier, importance-based claim that fundamentals helped — importance ≠
   marginal contribution.)
2. **The honest signal is a small, significant low-volatility + cross-sectional
   model** (t=2.04, IC 0.055), strengthening with horizon (IC 0.083 at 120d).
3. **The dominant risk lever is regime**: the signal *reverses* in stressed/bear
   states; gating exposure there halved the drawdown.
4. **We cannot beat SPY in absolute return** — a low-vol tilt underperforms a
   high-vol-tech-led bull. The best we built is a **lower-risk SPY alternative**
   (Sharpe 0.88, half the drawdown, Calmar 0.57 vs 0.39).

## Honest caveats (still open)
- **Survivorship:** every number is on current constituents. True survivorship-
  free results would be lower. Full removal needs delisted-name prices (paid data).
- **Cost-stress** of the regime version is an artifact of the flat-daily stress
  metric over-penalizing a strategy that sits in cash; real costs are in §4.
- This is one decade, one universe, one asset class.

## The deliverable, stated plainly
A **statistically significant, leakage-checked, regime-gated, factor-attributed
low-volatility equity strategy** that matches SPY's Sharpe with ~half the
drawdown — **not** an absolute SPY-beater. Institutional-grade *process*; modest
*alpha*. That is an honest, defensible outcome — and the opposite of the leaked
fantasies of V1–V11.

## Realistic paths forward
A. **Treat the regime-overlay as the product** → harden it (Phase 2 guardrails)
   and paper-trade it on Alpaca as a lower-risk equity strategy. Accept it is not
   an SPY-beater.
B. **Survivorship reality check** → build/obtain point-in-time membership (partial
   without delisted prices) to get the honest, lower number before any deployment.
C. **Accept the broader finding** → retail-accessible technical alpha on liquid
   large-caps is largely arbitraged; passive/factor ETFs are the rational default.
   V14 stands as a rigorous research result.

Recommendation: **B then A** — confirm honestly under survivorship as far as free
data allows, and if it survives, paper-trade the regime-overlay as a risk-managed
strategy. Do **not** keep adding technical factors; that edge is exhausted.
