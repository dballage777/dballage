# Research Log

Structured history so every version builds on the last (never restart).

## V1–V11 summary (pre-framework)

| Version | Strategy | SPY | Sharpe | Verdict / cause |
|---|---|---|---|---|
| V1–V5 | huge | — | — | **Leakage / hindsight bias** — not real |
| V6 | ≈ bench | — | — | Collapsed toward benchmark |
| V7 | — | — | 2.24 (signal) | Corr 0.031, R² −0.044 → **weak features** |
| V8 | $24,140 | $28,976 | — | Lost to SPY |
| V9A | $108,258 | $39,525 | 2.49 | **Implementation artifact / hidden bias** |
| V9B | $12,055 | $10,684 | 2.90 | More realistic |
| V10 | — | — | — | MC mean 71.6%, stability 3.95 — some robustness |
| V10.1 | $1,446 | $1,582 | — | Failed |
| V10.2 | $1,701 | $1,582 | — | Slight improvement |
| V10.3 | $1,777 | $1,582 | — | Incremental |
| V11 | $8,235 | $21,455 | −0.25 | **Institutional validation exposed weakness** |

**Key lesson carried into V12:** the bottleneck is *feature quality* and
*validation integrity*, not model complexity. Several early "wins" were leakage.

## V12 — framework rebuild

**Changes**
- Rebuilt as a modular platform (`data/features/models/portfolio/risk/backtest/
  evaluation/agents/automation`).
- ~50-feature library across momentum / trend / volume / volatility (incl.
  Yang-Zhang, Parkinson) / mean-reversion / breadth / cross-sectional ranks.
- Target = cross-sectionally de-meaned forward return (relative selection, not
  market beta).
- **Purged + embargoed walk-forward** with an executable leakage gate.
- Model zoo (ridge/elasticnet/rf/xgb/lgbm/catboost) + OOF stacking, selected by
  out-of-sample rank-IC.
- Backtest with commission+slippage, DCA contribution model, and overlays
  (cash-regime, vol-targeting). SPY benchmark gets the same contributions.
- Monte-Carlo bootstrap + stress tests; agentic research loop with persistent
  memory.

**First synthetic smoke result** (pipeline validation only — network-restricted
sandbox, *not* real alpha):
- Leakage gate: **passed** (all folds disjoint, purge gap honoured).
- Best model: LightGBM, mean OOS rank-IC ≈ 0.029 (Ridge ≈ 0.00 → the planted
  faint signal is real but weak, as designed).
- MC stability ≈ 0.25 (< 1) and edge did **not** survive +5bps cost stress →
  RiskAgent verdict: **REJECT**. Correct, honest behaviour.

**Framework self-validation** (`experiments/validate_framework.py`, synthetic
ground truth, mean ± std over 3 seeds, 20-name universe)

| planted signal | OOS rank-IC | reading |
|---|---|---|
| none (0×) | −0.015 ± 0.056 | ≈ 0 → **no hallucinated alpha** |
| faint (1×) | +0.002 ± 0.038 | ≈ 0 → faint signal sits at the noise floor (realistic) |
| strong (4×) | **+0.333 ± 0.014** | cleanly recovered, tight variance |

Plus: the leakage gate **fires** on an injected contaminated feature. Together
these establish the antidote to the V1–V9A failures — the stack finds real
signal, does not invent fake signal, and aborts on leakage. Guarded in CI and by
`tests/test_signal_recovery.py`.

> Note: an earlier recovery test planted a *latent* quality drift that mapped to
> features only indirectly and was not recovered. Rather than tune the test to
> pass, the synthetic signal was changed to an **observable momentum factor** so
> the test genuinely exercises the learning path. This is logged as a methodology
> correction, not a silent fix.

## V12 real-data findings (yfinance)

**Run 1 — 25 mega-caps, 5-day horizon:** IC 0.058, long-short Sharpe 1.29. Looked
great — but on a curated winner universe, so suspect.

**Run 2 — broad 54-name universe (incl. laggards), 5-day horizon:** IC collapsed
to 0.008, long-short Sharpe 0.31. **The mega-cap edge did not generalize** — it
was largely universe-selection bias. Gate failed → did not proceed.

**Run 3 — horizon sweep on the broad universe** (hypothesis: the only non-zero
features are slow — mom_120, realized_vol_60, trend_r2 — but the target was 5-day,
a horizon mismatch):

| horizon | IC | long-short Sharpe (after costs) |
|---|---|---|
| 5d | 0.008 | 0.31 |
| 20d | 0.057 | 0.85 |
| 60d | **0.134** | **1.37** |

Clean monotonic dose-response on the *honest* (survivorship-diluted) universe —
the first signal that survives the broad-universe + long-short test.

**Validated recipe:** broad universe, **60-day** horizon, **linear models only**
(elasticnet/ridge — trees went *negative*: lgbm −0.074, xgb −0.056). The signal
is a slow, linear cross-sectional **low-volatility + momentum** factor.

**Caveats (do not over-claim again):**
- Reported **ICIR ≈ 11.5 is inflated** — 60-day labels overlap, so per-date ICs
  are autocorrelated and the ×√252 annualization is invalid. Real annualized
  ICIR ≈ **1.5**. *(Metric needs a horizon-aware fix.)*
- It is **market-neutral**: it will not out-*return* a leveraged bull-market SPY
  and must not be judged on §4. Its metric is the long-short Sharpe (~1.37).
- Still a current-constituents universe; point-in-time membership still owed.

**Next experiments** (auto-proposed by the framework)
1. Feature ablation — keep only top-importance features and re-test.
2. Add fundamentals / alt-data to raise the technical-only IC ceiling.
3. Regime-conditional ensemble weighting.
4. Evaluate IC separately in calm vs stressed regimes.
5. **Live-data rerun** (Codespaces/Colab, 10y, full universe) before any Alpaca
   paper trading.
