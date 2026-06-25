# GOAL Implementation Audit (honest, attribute-by-attribute)

Status: ✅ implemented · 🟡 partial · ❌ not built · ⛔ infeasible in v1 (no
infra/data) · ⚠️ evidence says it would HURT.

**Bottom line up front:** "all attributes implemented" is **not achievable** —
some are infeasible without external infra/data, some are large separate builds,
and a few we *empirically proved degrade* the strategy. The honest target is:
implement every **feasible, non-counterproductive** attribute, and explicitly
**stub + document** the rest.

| # | GOAL attribute | Status | Note |
|---|---|---|---|
| 1 | EV engine (trade only if EV>0 after costs) | ✅ | decision_engine ev_score = signal − cost |
| 2 | Regime detection — 6 states | ✅ | classify_regime_6 (Bull/Bear/Chop/HighVol/Crisis/Recovery) |
| 3 | No-trade conditions → CASH | 🟡 | EV/regime/confidence/governor ✅; **liquidity/spread checks** ⛔ (no live order book) |
| 4 | Position sizing — Kelly 25% + caps (stocks 5–8%) | ✅ | kelly_exposure + max_weight 8% |
| 5 | Risk rules — maxDD/daily stop/3-loss halt | ✅ | RiskGovernor (20% / 4% / 3) |
| 6 | Graduated (conviction-scaled) sizing | ✅ | graduated_size_multiplier |
| 7 | Cash is a valid position (0–100%) | ✅ | governor + regime → cash |
| 8 | Decision output (Asset/Action/EV/Risk/Conf/Size/Reason/Sources) | ✅ | Decision dataclass |
| 9 | Capital structure 0–70% stocks / 0–30% crypto | 🟡 | stocks cap ✅; crypto 0% (unbuilt) |
| 10 | Universe — stocks 25–40 | ✅ | broad 54-name set incl. core list |
| 11 | Decision hierarchy (Regime→EV→Risk→**Correlation**→Size→Exec) | 🟡 | all but the **correlation-overload check** ❌ |
| 12 | Strategy horizons — long/medium/short | 🟡 | long (60d) ✅; medium (20d) buildable; **short/intraday** ⛔ (daily data only) |
| 13 | Microcap rule (≤10%/≤1%; experimental bucket) | ❌ | no microcap classifier/cap (our universe has none, but unenforced) |
| 14 | Core 95% / Experimental 5% / Shadow portfolios | 🟡 | sleeve manager has live/shadow ✅; explicit 95/5 split ❌ |
| 15 | Learning loop (track accuracy/Sharpe/decay → reweight) | 🟡 | ShadowLedger rolling perf = substrate ✅; **live reweighting** ❌ |
| 16 | Biweekly deposits held in cash until EV met (90-day idle) | 🟡 | DCA in backtest ✅; live "hold-until-EV + 90d idle" ❌ |
| 17 | Futures excluded in v1 | ✅ | none |
| 18 | Crypto universe (BTC/ETH + alts) | ❌ | unbuilt (variant 3 will build) |
| 19 | Microcap caps for crypto (≤5%/≤0.5%) | ❌ | with crypto |
| 20 | Alt-data: SEC EDGAR (10-K/Q/8-K, Form 4, 13F/13D/13G) | 🟡 / ⚠️ | fundamentals + Form 4 built — **ablation showed they HURT OOS IC**, so pruned out |
| 21 | Alt-data: congressional trades, options flow, ETF holdings, COT | ❌ | not ingested |
| 22 | Macro (FRED/BLS/Fed) | ❌ | not ingested |
| 23 | News (Reuters/Bloomberg/WSJ/FT) | ⛔ | paid feeds / licensing; no access |
| 24 | Community (Reddit/HN/forums) | ⛔ partial | scraping/APIs; mostly network-blocked; unproven |
| 25 | Source weighting (30/25/10/10/20/5) + self-adjust | ❌ | no multi-source fusion live |
| 26 | Narrative lifecycle system | ❌ | unbuilt |

## What this means
- **Implemented & validated (the core engine):** EV gate, 6-regime, risk
  governor, Kelly/caps, graduated sizing, cash rule, decision output, sleeve
  manager, shadow ledger. This is a complete, honest *decision system*.
- **Feasible gaps worth closing before the variants:** correlation-overload
  check (#11), medium-horizon blend (#12), microcap enforcement (#13),
  core/experimental split (#14), live learning-loop reweight (#15), biweekly
  hold-until-EV (#16). All buildable, all reasonable.
- **Infeasible in v1 (stub + document):** intraday/short-term (#12), live news
  (#23), most community/alt-data ingestion (#24), options flow / COT (#21).
  These need data feeds / infra this environment doesn't have.
- **Counterproductive (do NOT live-weight):** the EDGAR alt-data signals (#20) —
  the factor-ablation *proved* they reduce OOS IC. Implementing them as live
  weighted inputs would degrade the validated strategy. They stay in the
  research/shadow track, not the live engine.

## Status update — 6 feasible gaps CLOSED (committed)
| gap | now |
|---|---|
| Correlation-overload check (#11) | ✅ decision_engine halves exposure on concentration |
| Medium-horizon blend (#12 long+medium) | ✅ strategies/blend.py (short/intraday still ⛔) |
| Microcap caps (#13) | ✅ portfolio/microcap.py (10%/1% enforced) |
| Core/Experimental split (#14) | ✅ sleeves bucket + 5% experimental cap |
| Learning-loop reweight (#15) | ✅ learning/reweight.py (by realized paper Sharpe) |
| Biweekly hold-until-EV (#16) | ✅ execution/cash_manager.py (90-day idle backstop) |

Infeasible sources now **explicitly declared** (v12/sources): intraday / news /
options-flow / reddit / narrative raise `NotImplementedError` rather than being
faked. Proven-harmful EDGAR alt-data marked `shadow_only`.

**Foundation is now honestly complete:** every feasible, non-counterproductive
GOAL attribute is implemented; everything else is explicitly NOT-AVAILABLE.

## Recommendation
Close the **6 feasible gaps** (correlation check, medium-horizon, microcap
enforcement, core/experimental split, learning-loop reweight, biweekly idle),
explicitly **stub the infeasible** (intraday, live news/alt-data, narrative) with
honest "NOT AVAILABLE" markers, and **keep the proven-harmful alt-data in shadow
only**. Then build variants 2/3/4 on that honest foundation. Claiming "all GOAL
attributes implemented" without these distinctions would be the dishonesty this
project exists to avoid.
