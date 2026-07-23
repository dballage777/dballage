# Concurrent Shadow Signals — S1 / S2 / S6 (observe-only)

These are the first three **P0** cross-market research shadows from
[`CROSS_MARKET_RESEARCH`](#) — added **additively**. They run *alongside* the
existing 7 paper tests, write to a **separate** ledger
(`paper/signal_shadow_ledger.jsonl`), and **never allocate capital or modify
V1–V7**. Every output is a recorded *suggestion* or *alarm*, not an action.

> Why these three first: the research (see the report) is blunt that for this
> project *more signals have hurt more often than helped* — fundamentals,
> insider, and macro-regime all failed our validation gate. So the highest-value
> first move is the **guardian that catches decay (S6)**, plus the two additions
> with the strongest independent published support and lowest leakage risk
> (**S2 VRP**, **S1 regime**), aimed at *exposure timing* — our actual edge —
> not stock-picking, where we are weak.

## The three shadows

| Book | What it is | Output | Data |
|---|---|---|---|
| `vrp_timer` (S2) | Variance-risk-premium equity timer. VRP = implied vol (VIX) − realized vol; elevated VRP has historically predicted higher forward equity returns. | Suggested equity exposure multiplier (1.0 / 0.6 / 0.3) | VIX + SPY (free) |
| `regime_timer` (S1) | Composite cross-market regime state: VIX term structure, HYG/LQD credit trend, breadth (% above 200-DMA), stock-bond correlation. Transparent rules (not a black-box HMM yet). | Suggested exposure multiplier from a −1…+1 vote score | SPY/AGG/HYG/LQD/VIX + breadth |
| `market_ref` | Passive 100% SPY. The yardstick both timers are judged against. | — | SPY |
| `drift_monitor` (S6) | The **safeguard**. Reads the *main* 7-test ledger READ-ONLY and raises **decay** (rolling Sharpe lower-bound ≤ 0) and **drift** (Page-Hinkley change-point) alarms per sleeve. Flags for review — demotes nothing. | Per-sleeve health record | main ledger |

## How the timers are scored (honestly)

Each timer logs a suggested exposure multiplier. On the **next** run, the realized
market return over the gap is attributed at the **previous** suggestion's
multiplier. Over time the ledger answers one question directly: **did timing beat
staying fully invested (`market_ref`)?** — on realized, forward, survivorship-free
returns, after the fact, with no re-optimization.

## Run it

```bash
python -m experiments.run_shadow_signals            # live (end = today)
python -m experiments.run_shadow_signals --quick    # small breadth universe (fast)
```

It runs automatically each day via the `Daily Shadow Paper Test` Action, as an
additive step after the main horse-race, and commits `signal_shadow_ledger.jsonl`.

## Honest limits

- **Observe-only.** These change **nothing** about live/paper allocation. They are
  research instruments accumulating forward evidence.
- **Daily cadence**, 20–60 day horizon — the fast tick-level lead/lag effects in
  the literature are *not* tradable with daily data, so we do not chase them.
- **Page-Hinkley is a simplified detector** (dependency-free), not full ADWIN. It
  flags candidates for human review.
- **Synthetic fallback** in a sandbox (no network) is stamped and for pipeline
  validation only; real VIX/SPY/credit data come from the Action / a Codespace.
- **Nothing auto-promotes.** A shadow becomes a "challenger" only after ≥90 days
  of forward evidence clears the same validation gate as every sleeve.
