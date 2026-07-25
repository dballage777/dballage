# Aggressive Shadow Sleeve — HIGH-RISK, paper-only, quarantined

An intentionally aggressive, higher-turnover research sleeve added **additively**
to test — honestly and forward — whether cranking the risk dial actually pays. It
runs *alongside* the 7 paper tests, writes to a **separate** ledger
(`paper/aggressive_shadow_ledger.jsonl`), and **never allocates real capital or
touches V1–V7 or their data.**

> ## Read this first — the honest expectation
> The research is unambiguous: the *literal* "day-trade illiquid micro-caps at max
> size" idea is one of the most reliably money-losing configurations in retail
> trading. Nearly every ingredient — day trading (**~97%** of persistent day
> traders lose money), micro-caps (illiquid, pump-and-dump), meme coins (**97%**
> of 2023–24 meme coins already dead), and full-Kelly sizing (**50%+** drawdowns)
> — independently destroys capital. So this sleeve is **not** that. It is the
> *evidence-backed* version of aggressive, and the most likely honest outcome
> after ~90 days is that it is **more volatile and does not beat the conservative
> baseline** on a risk-adjusted basis. If it wins, we'll have earned that
> knowledge honestly; if it loses, that is also a real, valuable answer.

## What makes it aggressive (and what keeps it from being a lottery)

The three things every blow-up traces back to are kept **off the table**:

| Blow-up cause | How this sleeve avoids it |
|---|---|
| **Illiquidity** | LIQUID mid/large-cap high-beta stocks + top liquid coins only. Illiquid micro-caps / meme coins are **excluded by design**. |
| **Slippage** | SHORT horizon (**5d + 15d** blend) — days-to-weeks, **not intraday**. Our stack has daily data and no low-latency execution; faithful intraday day-trading is infeasible here, so we don't fake it. |
| **Full Kelly** | **HALF Kelly (0.50)**, never full. Full Kelly produces catastrophic drawdowns when the edge is overestimated (it always is, live). |

Everywhere the evidence *permits* aggression, the dial is turned up:

| Knob | Conservative system | Aggressive shadow |
|---|---|---|
| Core signal | low-vol + regime | **cross-sectional momentum** (the effect with real crypto evidence) |
| Horizon | 20–60 days | **5–15 days** |
| Crypto cap | ≤15% | **≤60%** |
| Stocks cap | ≤60% | **≤60%** |
| Per-position | 5–12% | **≤20%** |
| Concentration | top 30% | **top 20%** |
| Sizing | ¼-Kelly | **½-Kelly** |
| Hard stops | −20% DD / −4% day / 3-loss | **−30% DD / −8% day / 3-loss** (looser but REAL) |
| Total invested | — | **capped at 100%** |

## The books

| Book | What it is |
|---|---|
| `aggr_stock_mom` | Liquid high-beta stock momentum (QQQ as the regime benchmark) |
| `aggr_crypto_mom` | Top-liquid-coin momentum (BTC as the regime benchmark) |
| `aggressive_system` | The two combined, total exposure capped at 100% |
| `market_ref` | Passive 100% SPY — the yardstick |

The regime gate still applies: even in aggressive mode, exposure is cut in
bear/crisis regimes and the hard-risk governor forces cash on a breach. Aggressive
means *higher ceilings*, not *no brakes*.

## Run it

```bash
python -m experiments.run_aggressive_shadow            # live (end = today)
python -m experiments.run_aggressive_shadow --quick    # small universes (fast)
```

Runs automatically each day via the daily Action as an additive, failure-tolerant
step, committing `aggressive_shadow_ledger.jsonl`.

## Why same repo (not a new one)

It reuses ~90% of the validated plumbing — the leakage-free backtest harness, the
shadow ledger, the risk governor, the deflated-Sharpe/validation gate, cost
modeling — which an aggressive bot needs *most*. It is quarantined in its own
`v12/aggressive/` module with its own ledger and clear HIGH-RISK labeling, so it
cannot contaminate the honest conservative track record. A **separate repo becomes
right only if** it ever graduates to real capital + real intraday infrastructure
(tick data, low-latency broker) — a genuinely different system then.

## Non-negotiable

SHADOW / paper only. Nothing auto-promotes. This sleeve earns real weight only
after ≥90 days of forward evidence clears the same validation gate as every other
sleeve — and beats, or safely matches, the conservative baseline on risk-adjusted
terms. "It was more exciting but lost to the simple version" is a valid result.
