# Monitoring & Intelligence Spec — Institutional Vision vs. Honest Status

> ⚠️ **Read this like `ORIGINAL_GOALS.md`.** Below is the full *institutional-grade
> autonomous research, monitoring, ranking, and allocation* spec as requested.
> Each item is tagged with its **honest status**, because a system that *claims* to
> monitor Reddit/Discord/news in real time while actually ingesting only price data
> would be lying to you. The discipline of this project is to never do that.

**Status legend:** ✅ built · 🟡 buildable (needs an API key/connector, no paid feed) ·
🔴 needs paid/real-time/authenticated infra · ⛔ tested, showed no out-of-sample edge.

---

## END PRODUCT — item by item

| # | Capability | Status |
|---|---|---|
| 1 | Continuously monitor sources | 🟡 scheduler is built (n8n daily); only price/volume is a live source |
| 2 | Extract signals/sentiment/trends/anomalies | ✅ price/volume signals · 🔴 sentiment/social |
| 3 | Probabilistic EV scoring | ✅ `DecisionEngine` EV gate + 0-100 `score_assets` |
| 4 | Dynamic regime allocation | ✅ 6-regime exposure + capital structure (variant 4) |
| 5 | BUY/HOLD/SELL/WATCH decisions | ✅ `build_daily_report` (WATCH = high score, gates not buying) |
| 6 | Paper-trading portfolio | ✅ shadow ledger + Alpaca **paper** adapter |
| 7 | Daily/weekly/monthly/quarterly reports | ✅ daily report built · 🟡 weekly+ are aggregations to add |
| 8 | Learn from prior signal effectiveness | ✅ learning loop (`reweight_sleeves`) on realized paper Sharpe |
| 9 | Rank by risk-adjusted expected return | ✅ Top-N ranked outputs |
| 10 | Capital preservation first | ✅ cash default, crisis→0%, hard-risk governor |

## Source weighting model (your weights) vs. what is live

| Category | Target weight | Live now? |
|---|---|---|
| Traditional market data | 35% | ✅ **live** |
| SEC filings / earnings / insider | 20% | ⛔ fundamentals+insider (ablation: no edge) · 🟡 13F/congress |
| Reddit | 10% | 🔴 needs API + infra |
| GitHub | 10% | 🟡 connector buildable (REST API) |
| Macro / economic | 10% | 🟡 FRED/BLS/CFTC connectors buildable |
| News | 5% | 🔴 paid APIs |
| Crypto-native (TVL/dev/fees) | 5% | 🟡 DefiLlama/Token Terminal connectors buildable |
| Discord / Telegram | 5% | 🔴 needs bot infra + auth |

**Live source-weight fraction today: ≈35%** (price/volume). The engine reports this
number on every daily report so the gap is never hidden. This is encoded in
`v12/sources` (`SOURCE_REGISTRY`, `live_weight_fraction()`).

## Monitoring frequency (intended) vs. reality

The spec asks for real-time prices, 1-min news, 5-min filings, etc. **Reality:** the
validated signal has a **20–60 day horizon**, so the engine recomputes **daily** and
rebalances weekly — higher frequency would add cost and noise without edge *for this
signal*. The intended cadences are recorded per source in `SOURCE_REGISTRY`; faster
loops switch on only when a signal that needs them is built and validated.

## Asset scoring model (0–100)

Built in `v12/reporting/scoring.py`. The 12 spec factors are all **declared**, but
only data-backed, edge-positive factors **contribute** (the rest carry weight 0):

| Factor | Weight | Status |
|---|---|---|
| Expected value (model) | 0.30 | ✅ live |
| Trend strength | 0.20 | ✅ live |
| Momentum | 0.20 | ✅ live |
| Low volatility | 0.15 | ✅ live |
| Liquidity | 0.15 | ✅ live |
| Fundamental quality | 0.0 | ⛔ ablation: no OOS edge |
| Sentiment | 0.0 | 🔴 no real-time feed |
| Insider activity | 0.0 | ⛔ ablation: no OOS edge |
| Institutional (13F) | 0.0 | 🟡 connector to build |
| Macro alignment | 0.0 | 🟡 FRED connector |
| Developer activity | 0.0 | 🟡 GitHub connector |
| Community conviction | 0.0 | 🔴 no Reddit/Discord feed |

## Outputs (Top-N lists)

Built: Top Opportunities, Top Long-Term/Stock, Top Crypto (each ranked, with the
mandated fields). Hidden-Gems / Emerging-Trends / Most-Over/Undervalued / Highest-
Conviction require the social + fundamental feeds above, so they are deferred until
those sources are real — not faked.

## Final decision framework

Every recommendation carries the mandated fields — **Asset · Score · EV · Risk ·
Confidence · Position Size · Entry Range · Exit Criteria · Reasoning · Sources** —
in `build_daily_report` / `top_n`. Entry range and exit criteria are explicit
rule-based values (entry ±1% band; exit = −8% stop or regime→bear/crisis), not
hidden heuristics. "Never recommend solely because popular" is enforced structurally:
popularity/social factors carry **zero weight** until a validated feed exists.

---

## The evidence gate (built — run this before paying for anything)

Every candidate source must clear `experiments/validate_source.py` first: it runs
the same purged/embargoed walk-forward and a **paired per-fold IC significance
test** of baseline vs baseline+candidate. PASS only if the source improves OOS IC,
significantly, across folds — exit code 2 on FAIL so n8n/CI can block on it.

```bash
python -m experiments.validate_source --source fundamentals --broad --horizon 60 \
    --sector-neutral --folds 34          # (this one FAILS — as the ablation showed)
python -m experiments.validate_source --family momentum --broad --horizon 60
```

A source that cannot beat this gate gets **zero weight — no exceptions, including
paid feeds.** That is the rule that stops you paying for data that adds nothing.

## What to build next (in honest priority order)

1. **Weekly/monthly/quarterly report aggregations** (pure aggregation of the daily
   ledger — fully feasible, no new data). *Highest value, lowest risk.*
2. **GitHub + crypto-native connectors** (free REST APIs) — turns two 🟡 buckets
   live; *then validate they add OOS edge before weighting them.*
3. **FRED macro connector** (free API key) — regime context.
4. Social/news (Reddit/Discord/Telegram/news) — only if you want to fund the infra;
   and only deployed after the same leakage-free validation every other signal got.

*Reminder: this document is the expanded vision plus its honest status — not a claim
that all of it is live. See `GOAL_IMPLEMENTATION_AUDIT.md` for the engine audit.*
