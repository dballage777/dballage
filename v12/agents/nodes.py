"""Agent node functions.

Each agent is a pure function ``state -> state``. They are deliberately
*deterministic and rule-based* by default (no LLM calls required to run), so the
research loop is reproducible and testable. The hooks where an LLM/LangChain
model would plug in are marked with `# LLM-HOOK`. This keeps the framework
runnable offline while leaving a clean seam for the agentic upgrade.
"""
from __future__ import annotations

from datetime import datetime
from typing import Dict

from ..utils import get_logger
from .state import ResearchState, ResearchMemory, Finding

log = get_logger("agents")


def research_agent(state: ResearchState) -> ResearchState:
    """Proposes hypotheses, conditioned on prior memory."""
    mem = ResearchMemory(state.get("memory_path", "results/research_memory.json"))
    best = mem.best_ic()
    hyps = [
        "Cross-sectional momentum + low-volatility ranks carry the most robust edge.",
        "Relative strength vs sector ETFs adds orthogonal information to absolute momentum.",
        "Breadth/regime features should gate exposure rather than predict returns.",
    ]
    if best:
        hyps.append(f"Prior best IC={best['metrics']['ic_mean']:.4f} ({best['cycle']}); "
                    "extend that feature set rather than restart.")
    # LLM-HOOK: replace with a ResearchAgent LLM that reads forums/papers + memory.
    state["hypotheses"] = hyps
    log.info("ResearchAgent: %d hypotheses (memory=%d findings)", len(hyps), len(mem.findings))
    return state


def feature_agent(state: ResearchState) -> ResearchState:
    """Decides the feature plan for this cycle."""
    cfg = state["config"]
    plan = ["momentum(5..120)", "trend(adx,kama,hull,supertrend,slope,r2)",
            "volume(relvol,obv,cmf,vwap,accel)",
            "volatility(atr,parkinson,yang_zhang,realized,volofvol)",
            "mean_reversion(boll_z,ema_dist,pct_rank)", "breadth(20/50/200,nh/nl)",
            "cross_sectional(mom,vol,rs,liquidity,quality)"]
    # LLM-HOOK: a FeatureAgent could prune/add features based on past importances.
    state["feature_plan"] = plan
    log.info("FeatureAgent: %d feature groups planned.", len(plan))
    return state


def backtest_agent(state: ResearchState) -> ResearchState:
    """Runs the full experiment (the heavy lifting lives in experiments.run)."""
    from experiments.run_experiment import run
    ctx = run(state["config"])
    state["backtest_ctx"] = ctx
    return state


def evaluation_agent(state: ResearchState) -> ResearchState:
    """Turns raw metrics into a pass/fail verdict against the directive's bar."""
    ctx = state["backtest_ctx"]
    strat, spy = ctx["strategy_perf"], ctx["spy_perf"]
    ic = ctx["ic"]["ic_mean"]
    beat_spy = strat["sharpe"] > spy["sharpe"] and ctx["strategy_final"] > ctx["spy_final"]
    robust = ctx["monte_carlo"].get("mc_stability", 0) or 0
    verdict = {
        "beats_spy": bool(beat_spy),
        "ic_mean": ic,
        "signal_ok": bool(abs(ic) >= 0.02),
        "mc_stability": robust,
        "robust": bool(robust and robust >= 1.0),
        "passed": bool(beat_spy and abs(ic) >= 0.02 and robust and robust >= 1.0),
    }
    state["evaluation"] = verdict
    log.info("EvaluationAgent: passed=%s (beat_spy=%s, signal_ok=%s, robust=%s)",
             verdict["passed"], verdict["beats_spy"], verdict["signal_ok"], verdict["robust"])
    return state


def risk_agent(state: ResearchState) -> ResearchState:
    """Independent risk veto layer."""
    ctx = state["backtest_ctx"]
    flags = []
    if ctx["strategy_perf"]["max_drawdown"] < -0.30:
        flags.append("Max drawdown breaches -30% risk limit.")
    if ctx["stress"].get("stress_cost_5bps_sharpe", 0) < 0:
        flags.append("Edge does not survive +5bps cost stress.")
    if ctx["monte_carlo"].get("mc_total_p05", 0) < -0.25:
        flags.append("MC 5th-percentile outcome worse than -25%.")
    state["risk_flags"] = flags
    log.info("RiskAgent: %d flag(s).", len(flags))
    return state


def deployment_agent(state: ResearchState) -> ResearchState:
    """Final gate. Deploy only if evaluation passes AND risk raises no flags."""
    ev = state["evaluation"]
    flags = state.get("risk_flags", [])
    if ev["passed"] and not flags:
        decision = "PROMOTE: eligible for Alpaca paper-trading."
    elif ev["beats_spy"] and not flags:
        decision = "HOLD: beats SPY but signal/robustness below bar — iterate."
    else:
        decision = "REJECT: " + ("; ".join(flags) if flags else "fails evaluation bar.")
    state["deployment_decision"] = decision

    # persist findings to long-term memory
    mem = ResearchMemory(state.get("memory_path", "results/research_memory.json"))
    cycle = state["config"].name
    mem.add(Finding(cycle, "evaluation", decision, {
        "ic_mean": ev["ic_mean"], "sharpe": ctx_sharpe(state),
        "mc_stability": ev.get("mc_stability", float("nan"))}))
    mem.save()
    log.info("DeploymentAgent: %s", decision)
    return state


def ctx_sharpe(state) -> float:
    return float(state["backtest_ctx"]["strategy_perf"]["sharpe"])
