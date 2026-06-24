# Run it — getting a real-data result

The code is already on GitHub (branch `claude/gallant-planck-p0wd97`). **Do not
copy-paste it into a notebook cell** — it's a multi-file package and the imports
will break. Instead, *run the repo* somewhere with internet so `yfinance` can
fetch real prices. Two good options.

---

## Option A — GitHub Codespaces (recommended)

Codespaces is in the locked stack, is already authenticated to your private repo
(no tokens), and the devcontainer automates setup.

1. Open the repo on github.com and switch to branch **`claude/gallant-planck-p0wd97`**.
2. Click **Code ▸ Codespaces ▸ Create codespace on this branch**.
3. Wait ~2–3 min. The devcontainer (`.devcontainer/setup.sh`) auto-installs
   dependencies, runs the tests, and fetches real prices via
   `scripts/fetch_data.py`. It prints a **“✅ V12 ready”** checklist when done.
4. In the Codespace terminal:
   ```bash
   python -m experiments.run_experiment
   cat results/v12_baseline_report.md
   ```

---

## Option B — Google Colab

The notebook `notebooks/V12_Colab.ipynb` does clone → install → fetch → run → plot.

1. Open https://colab.research.google.com → **GitHub** tab → search
   `dballage777/dballage` → open `notebooks/V12_Colab.ipynb`.
2. **Runtime ▸ Run all.**

> If the repo is **private**, Colab’s clone step needs a GitHub token. Codespaces
> avoids this entirely — prefer Option A for a private repo.

**Skip Replit** for this project — it fights multi-module Python packages and
dependency installs.

---

## What to check when it finishes

1. **Real data?** The report header must read `data source: **yfinance**`
   (not `synthetic`). If it says synthetic, the network was blocked.
2. **Survivorship bias (§2b)** will show a ⚠️ warning — expected, because the
   default universe is *today’s* large caps. It means: trust the **rank-IC**,
   not the dollar figures, until a point-in-time universe is supplied
   (`config/universe_pit_template.csv`, set `DataConfig.universe_source`).
3. **Send back two things:**
   - **§3** — OOS rank-IC / ICIR (does the signal rank forward returns?)
   - **§4** — performance vs SPY after costs (does it beat the benchmark?)

Those two numbers are the first honest read on whether the features have edge,
and they decide the next move:

| result | next move |
|---|---|
| IC < ~0.02 or loses to SPY | technical-feature ceiling → add fundamentals/alt-data |
| IC positive but fails cost/MC stress | turnover/cost fix (widen rebalance, tighten universe) |
| survives everything | freeze config → wire Alpaca paper-trading to the DeploymentAgent gate |

---

## Optional: a fully honest (survivorship-safe) run

The default universe overstates returns. To remove the bias, build a
point-in-time membership CSV (template at `config/universe_pit_template.csv`,
columns `ticker,start,end`) listing when each name was actually in your universe,
then:

```python
from v12.config import ExperimentConfig
cfg = ExperimentConfig()
cfg.data.universe_source = "config/your_pit_membership.csv"
```

The pipeline masks out non-members so delisted/removed names never contribute a
label. The report’s §2b will then read ✅ survivorship-safe.

---

## Sanity check before trusting anything

```bash
python -m experiments.validate_framework
```

Proves the stack recovers a known signal, does not invent alpha on pure noise,
and aborts on leakage. If this fails, fix it before believing any backtest.
