# Paper Testing — the 90–180 Day Shadow Horse-Race

This is how we **truly test the original idea** without risking a dollar: run all
five variants forward, every day, side by side, and let *honest realized paper
performance* — not a re-optimized backtest — decide which (if any) earns
promotion to live paper trading.

## The five horses

| Sleeve | What it is |
|---|---|
| `equity_validated` | The validated low-vol baseline (variant 1) — the **control arm** |
| `equity_full_goal` | Stocks + all GOAL conditions (variant 2) |
| `crypto_full_goal` | Crypto + all GOAL conditions (variant 3) |
| `full_system` | Variant 2 + 3 + learning loop (variant 4) — the full GOAL engine |
| `full_system_max` | Variant 4 **+ every available SEC data source** (fundamentals [+insider]) — variant 5, the maximal-data arm |

The whole point of the race: does the heavier GOAL machinery (6-regime exposure,
multi-horizon blend, Kelly, crypto, learning loop) actually **beat the simple
validated baseline** in honest forward paper? If it doesn't, we keep the simpler
thing. That is the discipline.

**Variant 5 caveat (honesty):** it adds the SEC data sources our *backtest ablation
showed HURT* out-of-sample — included at the user's request to test that finding
*forward* too. It uses every data source that has real ingestion code (price/volume
+ fundamentals + insider); the ~100 community/news sources in the GOAL spec have no
feeds and are **not** ingested (each decision's `sources` field records exactly what
was used, and flags anything UNAVAILABLE). Variant 5 degrades gracefully to
price/volume when SEC data can't be fetched. Insider is heavy (bulk quarterly
downloads) so it is **off by default** in the daily Action; enable it with
`--with-insider` (or `SHADOW_V5_INSIDER=1`) when running in Codespaces.

## Run it

```bash
# one run (records all four variants to the ledger; computes realized
# paper return for each since its previous run)
python -m experiments.run_all_shadow --log results/shadow_ledger.jsonl

# fast smoke (small universes)
python -m experiments.run_all_shadow --quick
```

Each run appends one **shadow** row per sleeve to `results/shadow_ledger.jsonl`:
the day's governed decisions (full GOAL output per asset) plus the **realized
return** of the weights it was holding. Over time the ledger becomes a real,
forward, survivorship-free track record per sleeve.

## What accumulates (the learning loop)

- After ~**20 trading days** each sleeve has enough history for a rolling Sharpe.
- The `full_system` sleeve then **activates its learning loop**: it reads each
  book's realized Sharpe and tilts exposure toward the better book (`reweight_sleeves`).
- Before that, learning is **cold-start** (no tilt) — it must *earn* an opinion.

## The promotion gate (shadow → live paper)

A sleeve graduates from shadow to live paper **only** when, over ≥90 trading days:

1. **Positive realized Sharpe** (rolling, after costs) — and **≥ the baseline's**.
2. **Max daily loss respected** — no day worse than the −4% stop would have allowed.
3. **Regime behavior correct** — went to cash in crisis/bear (capital preservation).
4. **No single-name or class-cap breach** in any logged decision.
5. **Beats, or safely matches, `equity_validated`** on risk-adjusted terms.

If nothing clears the gate, the honest outcome is: **stay in paper, or deploy only
the validated baseline.** "It didn't beat the simple version" is a valid, valuable
result — it is exactly what eleven leakage-driven prior versions failed to admit.

## Reading the ledger

```bash
python - <<'PY'
from v12.execution.ledger import ShadowLedger
led = ShadowLedger("results/shadow_ledger.jsonl")
for s in ["equity_validated","equity_full_goal","crypto_full_goal","full_system"]:
    print(s, led.rolling_performance(s))
PY
```

## Honest limits

- **Cadence is daily**, not tick-by-tick. The validated signal has a 20–60 day
  horizon; daily decision + weekly-ish rebalance is the right frequency. "Real-time
  monitoring" of news/Reddit/Discord is **not** implemented (see the source audit).
- **Paper only.** No real capital. Live *paper* orders (Alpaca paper) are opt-in.
- Synthetic data in a sandboxed network validates the **pipeline**, not alpha —
  run on a host with real `yfinance`/Alpaca access (see `DEPLOY_DIGITALOCEAN.md`).
