# Live Deployment Playbook (planning — nothing live yet)

> **Status: NOT LIVE, by design.** The system is paper-only. This document is the
> pre-flight plan for *if and when* the paper test earns a live deployment. Read
> it end-to-end before a single real dollar is involved. Nothing here is enabled
> automatically — going live is a deliberate, human-gated act.

---

## 0. The gate — do NOT go live until ALL of these are true
Live trading is unlocked only after the forward paper test clears the promotion
gate in [`PAPER_TESTING.md`](PAPER_TESTING.md):

- [ ] ≥ **90 trading days** of honest forward paper results.
- [ ] The candidate variant has a **positive realized Sharpe after costs**.
- [ ] It **beats `equity_validated`** (the simple baseline) — or you deploy the
      baseline instead.
- [ ] It **beats USMV/SPLV** (the cheap ETF alternative) on risk-adjusted terms.
- [ ] The **risk governor behaved correctly** (went to cash in drawdowns; no day
      breached the loss stop).
- [ ] You have decided a **maximum real capital at risk** you can afford to lose.

If any box is unchecked, stay in paper. "It didn't clear the gate" is a valid,
money-saving outcome.

---

## 1. Architecture — Alpaca is the broker, not the host
```
[ always-on host ]  --daily-->  [ decision engine ]  --orders-->  [ Alpaca API ]
   (droplet/VM)                    (this repo)                     (execution)
```
Alpaca **executes** orders; it does not run your code. You need an always-on
**host** that fires the daily decision and submits orders to Alpaca's API.

**Cadence reality:** the strategy is daily (20–60 day horizon, ~weekly
rebalance). The host is always-on; the bot **acts once per day** (compute after
the US close; Alpaca queues orders for the next open). Equities are market-hours;
Alpaca crypto is 24/7 but the crypto signal is daily too. You do **not** need a
tick-by-tick bot.

---

## 2. Recommended host: a DigitalOcean droplet
We already built the deployment scaffolding — see
[`DEPLOY_DIGITALOCEAN.md`](DEPLOY_DIGITALOCEAN.md) (`Dockerfile`,
`docker-compose.yml`, the n8n workflow). For live, the same droplet runs a daily
job (cron **or** n8n) that calls the decision engine and the live adapter.

Alternatives (all fine): AWS Lambda + EventBridge (serverless cron),
Render/Railway/Fly.io (managed cron). **GitHub Actions is great for paper but not
recommended as the sole live executor** — its cron can lag 5–30+ min and it isn't
built for real-money execution. Keep it as paper/redundant, not primary.

---

## 3. Engineering that MUST be built before live (honest gaps)
The current `AlpacaPaperAdapter` is a **paper stub**, not a production executor.
Going live is **not** "flip the URL" — these must be built and tested first:

1. **A gated live adapter.** Today the adapter *hard-refuses* any non-paper
   endpoint (a deliberate safety). Live needs a separate `AlpacaLiveAdapter`
   behind an explicit `--i-understand-this-is-real-money` style flag + config,
   never a silent default.
2. **A real order manager (not just BUY).** The paper stub only submits BUY
   notionals. Live must: read current positions, compute **deltas** vs targets,
   **SELL/REDUCE** overweight names, respect the no-trade band, and reconcile
   partial fills. Rebalancing, not just buying.
3. **Asset-class handling.** Equities (market-hours, fractional shares) vs Alpaca
   **crypto** (24/7, different symbols/precision) need separate order paths.
4. **Market-hours / order-type logic.** Decide MOC/limit/notional and
   time-in-force; handle halts, PDT rules, and settlement.
5. **State reconciliation.** On each run, trust Alpaca's *actual* positions/cash
   as truth, not the shadow ledger.

Until these exist and are paper-tested, live is not ready — regardless of the gate.

---

## 4. Pre-flight safety checklist
- [ ] **Risk governor live** — drawdown kill-switch / daily-loss stop / 3-loss
      freeze (already built) wired into the live path and tested.
- [ ] **Position + class caps enforced** (stocks 8%, crypto 12%, class 70/30).
- [ ] **Hard max-capital cap** set in config; start with **tiny** real money.
- [ ] **Manual kill-switch** — a one-command "flatten everything to cash".
- [ ] **Monitoring + alerts** — daily fill report + immediate alert on any error,
      governor trip, or unexpected position (Slack/Telegram/email).
- [ ] **Alpaca account secured** — 2FA on, keys in secrets (never committed),
      least-privilege.
- [ ] **Dry-run in live account first** — run the live adapter in `dry_run=True`
      against the *live* account for a week; confirm it *would* have placed
      correct orders before letting it send.

---

## 5. Go-live steps (when the gate is passed)
1. Fund an Alpaca **live** account with your predetermined *small* amount.
2. Build + paper-test the order manager and `AlpacaLiveAdapter` (Section 3).
3. Deploy to the droplet; store live keys as secrets; set the max-capital cap.
4. Run **live-account dry-run** for ~1 week; verify intended orders daily.
5. Flip to real orders for **one variant only** (the gate winner) at **minimum
   size**; keep the others in shadow.
6. Watch daily. Scale capital **only** as it keeps proving itself — never all at
   once (quarter-Kelly discipline).

---

## 6. Kill / rollback
- **Flatten now:** one command that cancels open orders and market-sells to cash.
- **Pause:** disable the daily job (droplet cron off / n8n workflow deactivated).
- **Governor auto-halt:** the drawdown/loss circuit-breakers already force cash —
  verify they page you when they trip.
- Keep the **paper shadow running in parallel** so you always have a live-vs-paper
  divergence check.

---

## 7. Honest caveats
- Beating the paper results live is **not** guaranteed — slippage, fills, and
  spreads are real. Expect live to be *worse* than paper; size for that.
- The strategy's validated edge is **defensive** (lower drawdown, ~matches SPY),
  not a money-printer. Live deployment is about capturing that risk profile, not
  getting rich.
- Real money changes behavior. The point of full automation is to remove the
  human override that kills most retail systems — trust the governor, don't
  discretionarily intervene.

*Nothing in this repo trades real money today. This is the plan for later.*
