# Data sources & the orthogonal-alpha plan

After the 8-year honest test showed **no robust edge in daily technical/price
features** on liquid large-caps (see RESEARCH_LOG.md), the only credible path to
a real edge is **orthogonal information** the price chart doesn't contain. This
file records the research-grounded plan.

## What the evidence says (June 2026 web research)

- Factors that survive out-of-sample: **value, momentum, quality, low-volatility.**
- **Combining fundamental + quant signals raises the information ratio ~50%**
  (risk-parity combo IR ≈ 0.34 over 2008–2025) — fundamentals are *orthogonal*
  to our momentum/low-vol technicals, which is exactly what we need.
- Reality check: even done well, these edges are **modest** (IR ~0.3). Realistic
  target is lifting our market-neutral Sharpe from ~0.5 toward ~0.8–1.0 — a real
  improvement, not a moonshot. Anyone promising more is selling overfit.

## The leakage trap (non-negotiable)

Fundamentals must be **point-in-time**: a figure may only be used *after its
actual public filing date*. Naive sources (yfinance `.info`, most "current"
snapshots) stamp today's restated financials onto past dates → look-ahead bias,
the exact V1–V9A failure. We will not use any fundamental value before it was
filed.

## Chosen source: SEC EDGAR `companyfacts` (free, no key, point-in-time)

`https://data.sec.gov/api/xbrl/companyfacts/CIK{cik}.json` returns every XBRL
financial concept with both the period (`end`) and the **filing date (`filed`)**.
We index features by `filed` date, so the backtest only ever sees a number after
the market did. No API key, fully PIT-correct.

Backup options (need a free API key, easier but verify PIT): Financial Modeling
Prep, Finnhub, Alpha Vantage.

## Planned fundamental feature set (PIT, cross-sectional)

- **Value:** earnings yield (E/P), book/price, sales/price, FCF yield.
- **Quality:** ROE, gross & operating margin, accruals, debt/equity.
- **Growth/revisions:** YoY revenue & EPS growth; (later) analyst EPS revisions.
- All cross-sectionally ranked per date (like the existing `csrank_*` features)
  and merged into the panel by `filed` date with forward-fill until the next
  filing.

## Build plan

1. `v12/data/fundamentals.py` — EDGAR client + ticker→CIK map + PIT assembly.
2. `v12/features/fundamental.py` — the value/quality/growth features above.
3. Wire into `FeaturePipeline` alongside technicals (same leakage gate, same
   purged walk-forward).
4. Re-test on the **honest harness**: broad universe, 60d horizon, 2018–present
   OOS, long-short probe. Compare IC/long-short Sharpe with vs without
   fundamentals. Ship only if it clears the bar net of costs.

## Sources
- Robeco, *Seizing quant & fundamental alpha* (2025)
- CFA Institute, *When the Equity Premium Fades, Alpha Shines* (2025)
- PIMCO, *The Alpha Equation: Myths and Realities* (2024)
- SEC EDGAR XBRL frames/companyfacts API
- Free fundamental APIs: FMP, EODHD, Finnhub, Alpha Vantage
