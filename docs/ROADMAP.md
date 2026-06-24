# V12 Roadmap — when each piece gets built

**Core principle:** every phase is gated on *evidence*, not a date. We build a
capability only once its prerequisite is proven, because writing risk rules,
regime engines, and execution logic on top of an unvalidated signal is precisely
how V1–V11 produced inflated, fake results. If a gate fails, we do **not**
proceed — we go back and fix the signal.

Legend: 🔒 blocked by a gate · 🟡 partial today · ✅ done

---

## Phase 0 — Validate the core signal  *(WE ARE HERE)*

**Goal:** prove the cross-sectional stock signal is *real selection skill*, not
survivorship beta or luck.

- [x] Real-data baseline (yfinance): IC 0.058, beats SPY on a biased universe.
- [ ] **Long-short §4b verdict** — is the spread positive after costs? *(pending your run)*
- [ ] Confirm on a **broader / point-in-time universe** (survivorship-safe).
- [ ] Check return concentration (the "drop best 5% of days" fragility).

**GATE to proceed:** long-short Sharpe clearly positive after costs **and** the
edge survives a less-biased universe. *If this fails → back to feature research,
not forward to risk/regime/execution.*

---

## Phase 1 — Risk sizing  🔒(needs Phase 0 pass)

Cheap, defensible, low overfitting surface. ~1 session.

- [ ] Wire **Kelly fraction** (already defined) into sizing, capped at **25%** of full Kelly.
- [ ] Tighten **position caps**: 5–8% stocks (today: flat 20%).
- [x] **Vol targeting** for stocks (10–15%) — already live.

---

## Phase 2 — Backtestable risk guardrails  🔒(needs Phase 1)

Portfolio-level hard constraints, implemented as **testable overlays** with
honest before/after metrics. ~1–2 sessions.

- [ ] Max-drawdown **kill-switch** (15–25%, de-risk to cash when breached).
- [ ] **Daily loss cutoff** (3–5%).
- [ ] **Consecutive-loss-day halt** (stop after 3).
- [ ] **Correlation-cluster exposure cap** (no hidden overexposure).

> Note: each threshold is a free parameter. We'll choose them on a validation
> window and stress-test them, not hand-pick to flatter the backtest.

---

## Phase 3 — Regime layer  🔒(needs a validated, robust signal)

The 4-regime spec (Trending Up / Down / Chop / Crisis) and regime→strategy
allocation. ~2–3 sessions. Built carefully to avoid a parameter explosion:

- [ ] A **regime classifier** (trend strength, vol compression/expansion,
      correlation spikes, breadth) — validated to improve OOS, not assumed.
- [ ] Regime used first as an **exposure modulator** of the existing strategy.
- [ ] Only then add **multiple sub-strategies** (trend-follow / mean-revert) and
      the regime allocation buckets — each must earn its place on OOS data.

> Today: only a continuous risk-on/off cash overlay exists. The 70/20/10-style
> allocation numbers are placeholders until validated.

---

## Phase 4 — Execution layer (Alpaca paper)  🔒(needs Phases 1–2 + paper-eligibility)

This is where the **entry/exit rules**, **per-trade EV gate**, and **decision
hierarchy** actually live — they require a real order loop, which is stubbed
today. ~2–3 sessions.

- [ ] Alpaca paper adapter wired to the **DeploymentAgent** gate.
- [ ] Decision hierarchy: regime → strategy → EV>0 after costs → Kelly size →
      risk-constraint validation → execution approval.
- [ ] Entry gates (EV, liquidity, risk budget, non-redundant) and exit rules
      (EV-flip, regime change, stop-loss, vol spike).
- [ ] Live monitoring + degradation alerts (n8n).

---

## Phase 5 — Crypto  🔒(needs the stock system live)

Parallel asset-class expansion. ~2 sessions.

- [ ] Crypto data (BTC-USD/ETH-USD via yfinance, or ccxt).
- [ ] Crypto vol targets (25–40%) and position caps (8–12%).
- [ ] Portfolio split (stocks ~70% / crypto ~30%) — as a *tested* allocation.

---

## What this means for "when"

- **Phases 1–2** can happen fast — within a session or two **once Phase 0
  passes.**
- **Phases 3–5** are multi-session builds, each behind its own gate.
- **If Phase 0 fails** (signal is survivorship beta), none of this gets built
  yet — we return to feature/alpha research. That's the system working, not a
  setback.

The single thing standing between us and Phase 1 right now is the **§4b
long-short number.**
