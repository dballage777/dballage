# Deploy 24/7 on DigitalOcean (n8n + the shadow engine)

This runs the daily shadow horse-race **continuously, off your laptop**, on a
cheap always-on droplet — the real way to test the original idea forward in paper.

## What "24/7" actually means here (read first)

The box is up 24/7; the **decision cadence is daily**. The validated signal has a
20–60 day horizon — it does not trade tick-by-tick, and pretending to would just
add cost and noise. So the schedule is: **one full recalculation per day** after
the US close, with weekly-ish rebalancing built into the strategy. Crypto markets
run 24/7, but our crypto signal is daily-cadence too. If you later add genuinely
intraday signals (and intraday data), bump the schedule — the architecture
already separates "monitor" (n8n schedule) from "decide" (the engine).

## Cost

- **Basic droplet: $6–12/month** (1–2 GB RAM) is plenty for the daily run.
- n8n is free (self-hosted). Google Sheets / Slack / Telegram are free tiers.
- No market-data cost: `yfinance` is free; Alpaca **paper** is free.

## One-time setup

1. **Create the droplet.** DigitalOcean → Create → Droplet → Ubuntu 24.04,
   $6–12 plan, add your SSH key. Note the IP.

2. **Install Docker.**
   ```bash
   ssh root@YOUR_DROPLET_IP
   curl -fsSL https://get.docker.com | sh
   ```

3. **Clone the repo.**
   ```bash
   git clone https://github.com/dballage777/dballage.git /opt/v12
   cd /opt/v12
   ```

4. **Create `.env`** (never commit it — it's gitignored):
   ```bash
   cat > .env <<'EOF'
   TZ=America/New_York
   N8N_USER=admin
   N8N_PASSWORD=pick-a-strong-password
   N8N_HOST=YOUR_DROPLET_IP
   METRICS_SHEET_ID=your_google_sheet_id        # optional
   # Live PAPER trading only (optional; leave blank for decision-only):
   ALPACA_KEY=
   ALPACA_SECRET=
   SEC_USER_AGENT=YourName your@email
   EOF
   ```

5. **Start the stack.**
   ```bash
   docker compose up -d --build
   ```
   - Engine image builds; n8n comes up on `http://YOUR_DROPLET_IP:5678`
     (basic-auth with the user/password above).

6. **Import the workflow.** In the n8n UI → Workflows → Import from File →
   `automation/n8n_shadow_workflow.json`. Set credentials for Google Sheets /
   Slack if you want storage + alerts. Activate it.

That's it. Every day at 21:30 ET n8n runs the horse-race, appends one NAV row per
sleeve to your sheet, and pings you on any risk event (daily loss > 4% or a crisis
regime). The ledger persists in `./results` across runs.

## Verify it works

```bash
# run one race by hand inside the engine container
docker compose run --rm engine python -m experiments.run_all_shadow --quick
# inspect accumulated performance
docker compose run --rm engine python - <<'PY'
from v12.execution.ledger import ShadowLedger
print(ShadowLedger("results/shadow_ledger.jsonl").load().tail())
PY
```

## Optional: live PAPER orders (still zero real money)

The shadow race is decision-only by default. To also mirror the **validated**
sleeve into an Alpaca **paper** account, add your Alpaca *paper* keys to `.env`
and run:
```bash
docker compose run --rm engine python -m experiments.paper_trade --live-paper
```
The adapter hard-blocks any non-paper endpoint, so this cannot touch real funds.

## Security notes

- Keep `.env` off git (it is gitignored). Rotate any key that has ever been pasted
  into a chat.
- Put n8n behind the basic-auth above at minimum; for a public hostname add a
  reverse proxy + TLS (Caddy/Traefik) — don't expose 5678 unauthenticated.
