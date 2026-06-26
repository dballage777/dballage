#!/usr/bin/env bash
# One-command daily forward paper run (for manual use, a droplet, or cron).
#
#   ./scripts/daily_shadow.sh
#
# Runs all four variants, records realized paper returns to the ledger, and
# writes the daily report. Decision-only; no real money. For a true 24/7 setup
# prefer the GitHub Action (.github/workflows/daily_shadow.yml) or the n8n stack
# (docs/DEPLOY_DIGITALOCEAN.md).
#
# cron example (weekdays 17:05 local, after US close):
#   5 17 * * 1-5  cd /path/to/dballage && ./scripts/daily_shadow.sh >> paper/cron.log 2>&1
set -euo pipefail
cd "$(dirname "$0")/.."

mkdir -p paper/reports
python -m experiments.run_all_shadow --log paper/shadow_ledger.jsonl
python -m experiments.daily_report --out paper/reports

echo "Done. Ledger: paper/shadow_ledger.jsonl  |  Reports: paper/reports/"
