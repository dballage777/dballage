# Paper / Shadow Forward Test

This directory holds the **live forward paper test** output, committed daily by
`.github/workflows/daily_shadow.yml` (or `scripts/daily_shadow.sh`):

- `shadow_ledger.jsonl` — append-only per-sleeve decisions + realized paper returns
- `reports/daily_*.md` — the daily monitoring report

It accumulates over a 90-180 day window; the promotion gate is in
`docs/PAPER_TESTING.md`. Decision-only, zero real capital.
