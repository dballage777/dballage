# V14 Alpha Factor Catalog

Each factor: definition, data source, point-in-time feasibility, expected
**marginal** rank-IC (incremental over the current technical+fundamental set),
and key risks. Estimates carry wide error bars (see V13_RESEARCH_REVIEW.md).

| Factor family | Definition | Source | Free + PIT? | Marginal IC (est.) | Status |
|---|---|---|---|---|---|
| **Insider Form 4** | trailing cluster buying; net-buy direction | EDGAR Form 4 | ✅ | +0.002–0.008 | built (V13 #2) |
| **Short interest** | relative short interest level + change | FINRA bi-monthly | 🟡 ~PIT | +0.003–0.010 | planned |
| **Earnings surprise / PEAD** | SUE / post-announcement drift | actuals (free) + price | 🟡 partial | +0.005–0.015 | planned |
| **13F institutional** | Δ aggregate institutional ownership | EDGAR 13F (q, +45d lag) | ✅ slow | +0.003–0.010 | planned |
| **13D / 13G activist** | new >5% / activist stakes | EDGAR 13D/13G | ✅ | episodic | planned |
| **Form 3 / 5** | new-insider onboarding / annual true-up | EDGAR | ✅ | low (context) | optional |
| **Analyst revisions** | Δ consensus EPS estimates | external (FMP/Finnhub) | ❌ PIT-risky | +0.005–0.015 | gated on PIT data |
| **Value/Quality/Growth** | E/P, B/P, ROE, margins, leverage, growth | EDGAR companyfacts | ✅ | (in book) | built (V13 fund) |
| **Regime** | trend/vol/breadth/correlation state | derived | ✅ | ~0 (conditioning) | planned |

## Detailed notes

### Insider Form 4 (built)
Open-market purchases (code P) signal quality; cluster buying is the strongest
form. Sparse → episodic contribution; value is orthogonality, not magnitude.

### Short interest
Short sellers anticipate bad news months ahead (well documented). Mostly a
**short-leg** signal → helps the long-short more than long-only. FINRA settlement
data is bi-monthly; treat the publication date as the PIT date.

### Earnings surprise / PEAD
One of the most robust anomalies. Standardized unexpected earnings (SUE) and the
drift after announcement. Actuals + announcement dates are free/PIT; consensus
estimates are the external piece — a surprise proxy can be built from actuals +
the price reaction window without paid estimates.

### 13F / 13D / 13G
13F shows institutional holdings quarterly with a 45-day filing lag → slow,
crowding/smart-money signal, must be lagged to its filing date. 13D/13G flag new
>5% and activist positions → episodic catalysts.

### Analyst revisions (gated)
Highest standalone alpha on the list, but free APIs rarely provide point-in-time
estimate *history*; using current estimates on past dates is look-ahead. Build
ONLY with a verified PIT source, else skip — a leaked factor is worse than none.

### Regime (conditioning, not alpha)
Used to modulate exposure / condition factor weights, not to predict returns.
Every regime boundary is a free parameter → build one validated layer, not hand-
tuned buckets.

## Build gate (applies to every factor)
Admit only if marginal OOS rolling IC is positive, meaningful after overlap
correction, AND it survives the +5bps cost stress. The factor-analytics engine
(V14 step 1) produces the evidence; nothing ships on a hunch.
