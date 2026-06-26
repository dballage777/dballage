# Shadow paper-trading engine — always-on host image (DigitalOcean droplet).
# Builds a minimal image that can run the daily shadow horse-race. n8n runs as a
# separate container (see docker-compose.yml) and invokes this one on a schedule.
FROM python:3.11-slim

WORKDIR /opt/v12

# Core scientific stack only (no heavy optional deps) keeps the image small and
# the daily run fast. Add xgboost/lightgbm to requirements if you want the zoo.
RUN apt-get update && apt-get install -y --no-install-recommends \
        build-essential git \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt ./
RUN pip install --no-cache-dir \
        numpy pandas scipy scikit-learn pyarrow yfinance alpaca-py

COPY . .

# Persist the ledger + price cache across runs via a mounted volume.
ENV PYTHONUNBUFFERED=1
VOLUME ["/opt/v12/results", "/opt/v12/data_cache"]

# Default: one shadow horse-race run, appending to the persisted ledger.
CMD ["python", "-m", "experiments.run_all_shadow", "--log", "results/shadow_ledger.jsonl"]
