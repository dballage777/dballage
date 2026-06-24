# Running the honest real-data baseline

The framework runs anywhere, but **trustworthy** numbers require (a) real prices
and (b) survivorship-bias control. This is the one experiment to run before
adding any features or models.

## Fastest path — Google Colab
Open `notebooks/V12_Colab.ipynb`, set `REPO_URL`, Run all. It clones, installs,
fetches real prices, runs the full experiment, and renders the report + equity
curve.

## GitHub Codespaces
The devcontainer installs deps, runs tests, and warms the cache automatically.
Then:
```bash
python -m experiments.run_experiment        # full real-data baseline
cat results/v12_baseline_report.md
```

## One-time fetch, run anywhere
On a networked machine:
```bash
python scripts/fetch_data.py --start 2015-01-01 --end 2025-01-01
```
This writes `data_cache/*.parquet`. Copy that cache to a restricted box and the
experiment will read real prices from it (no network needed at run time).

## Reading the result honestly

1. **Data source** — the report header must say `data source: yfinance`. If it
   says `synthetic`, the network was blocked and the numbers are pipeline-only.
2. **Survivorship bias (§2b)** — with the default `static` universe the report
   prints a ⚠️ warning: results overstate returns because today's large caps
   exclude past losers/delistings. To remove the bias, build a point-in-time
   membership CSV (template: `config/universe_pit_template.csv`) and set
   `DataConfig.universe_source` to it; the pipeline then masks non-members.
3. **Judge the signal, not the dollars** — look first at **OOS rank-IC / ICIR**
   (§3) and the **post-cost SPY comparison** (§4). A static-universe dollar win
   that vanishes once you add PIT membership or costs is the classic V1–V11 trap.
4. **Robustness gates (§5)** — Monte-Carlo stability ≥ 1 and survival of the
   +5bps cost stress are minimum bars before considering Alpaca paper trading.

## Decision tree after the baseline
- IC < ~0.02 or loses to SPY → technical-feature ceiling → add fundamentals/alt-data.
- IC positive but fails cost/MC stress → turnover/costs problem → widen rebalance, tighten universe.
- Survives everything → freeze config → wire Alpaca paper-trading to the DeploymentAgent gate.
