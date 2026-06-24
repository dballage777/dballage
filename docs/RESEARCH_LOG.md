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

**Next experiments** (auto-proposed by the framework)
1. Feature ablation — keep only top-importance features and re-test.
2. Add fundamentals / alt-data to raise the technical-only IC ceiling.
3. Regime-conditional ensemble weighting.
4. Evaluate IC separately in calm vs stressed regimes.
5. **Live-data rerun** (Codespaces/Colab, 10y, full universe) before any Alpaca
   paper trading.
