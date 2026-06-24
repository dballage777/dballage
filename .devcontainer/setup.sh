#!/usr/bin/env bash
# Codespaces post-create: install deps and verify the framework runs.
set -euo pipefail

echo "==> Installing V12 dependencies..."
pip install --upgrade pip
pip install -r requirements.txt

echo "==> Running leakage & feature tests..."
python -m pytest tests/ -q

echo "==> Warming the price cache (real yfinance data; Codespaces has network)..."
python scripts/fetch_data.py || echo "WARN: live fetch failed; experiments will use synthetic fallback."

cat <<'EOF'

✅ V12 ready.

Next:
  python -m experiments.run_experiment          # full real-data baseline
  cat results/v12_baseline_report.md            # check 'data source: yfinance'

Honest baseline checklist (see docs/REAL_DATA_RUN.md):
  - report stamped data source = yfinance
  - section 2b: survivorship bias status
  - judge on OOS rank-IC + post-cost SPY comparison, not raw $.
EOF
