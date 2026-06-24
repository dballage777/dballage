# V12 Architecture

A run is fully described by a single `ExperimentConfig` (see `v12/config.py`),
so any result is reproducible from one object. Data flows:

```
load_prices ─► build_dataset ─► PurgedWalkForward ─► leakage gate
            ─► model comparison (zoo + stacking) ─► OOS predictions
            ─► run_backtest (costs+slippage+DCA, SPY bench)
            ─► metrics · rank-IC · Monte-Carlo · stress ─► report + memory
```

## Modules

### `data/`
`load_prices(DataConfig)` returns a `PriceData` (aligned OHLCV panels).
Source order: on-disk parquet cache → `yfinance` → synthetic fallback. The
synthetic generator is a regime-switching GBM with a *known faint* quality
premium (≈5bp/wk) so validation has an honest, weak signal to find — never to be
read as real alpha. The data source is recorded and surfaced in every report.

### `features/`
Single-name technicals (`technical.py`), relative strength vs benchmarks
(`relative.py`), market breadth (`breadth.py`), and per-date cross-sectional
ranks (`cross_sectional.py`), assembled by `pipeline.py` into a tidy
`(date, ticker)` panel. ~50 features. **All point-in-time.** Target = forward
`h`-day return, cross-sectionally de-meaned (predict *selection*, not beta).

### `validation/`
`PurgedWalkForward` produces expanding-train / rolling-test folds with purge
(drop train rows whose label overlaps the test window) and embargo (gap ≥
horizon). `assert_no_leakage` is an executable gate that aborts on any breach.

### `models/`
`build_model(name)` yields a uniform `fit`/`predict` estimator; heavy libs are
lazy-imported and skipped with a warning if missing. `StackingEnsemble` blends
base learners through an out-of-fold non-negative meta-Ridge (with a degeneracy
guard that falls back to averaging).

### `portfolio/` & `risk/`
Weighting: equal / inverse-vol / risk-parity, capped at `max_weight`. Risk:
vol-targeting scalar, fractional Kelly, CVaR, and a cash-regime overlay that
scales exposure down in weak-breadth / high-vol states.

### `backtest/`
Daily simulation consuming **OOS predictions only**. Selects the top quantile,
weights and de-risks them, charges commission+slippage on turnover, and applies
the DCA schedule. Produces both a time-weighted return series and a
money-weighted equity curve (with a contribution-matched SPY benchmark).

### `evaluation/`
Performance metrics, rank-IC / ICIR (the cleanest read on signal), block-
bootstrap Monte-Carlo (stability = mean/std of total-return distribution),
mechanical stress tests, and a markdown report implementing the directive's
output requirements.

### `agents/`
A LangGraph cycle (`Research → Feature → Backtest → Evaluation → Risk →
Deployment`) sharing one state object and a persistent `ResearchMemory` JSON so
later cycles build on earlier findings. Agents are deterministic/rule-based by
default with clearly marked `# LLM-HOOK` seams; falls back to a sequential
executor when LangGraph isn't installed.

### `automation/`
`run_backtest_cli.py` emits a one-line `V12_SUMMARY={...}` JSON for n8n.
`n8n_workflow.json` schedules nightly runs, stores metrics, compares vs SPY,
alerts on degradation, and triggers a retraining cycle.
