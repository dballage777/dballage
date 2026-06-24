"""LangGraph wiring for the research cycle.

Topology:
    research -> feature -> backtest -> evaluation -> risk -> deployment

If ``langgraph`` is installed we build a real ``StateGraph``; otherwise we fall
back to an equivalent sequential executor so the cycle always runs. Either way
the agents share state and append to persistent memory, satisfying the
directive's requirement that agents "share findings" and "improve future
experiments".
"""
from __future__ import annotations

from typing import Callable, Dict

from ..utils import get_logger
from .state import ResearchState
from . import nodes

log = get_logger("agents.graph")

_PIPELINE = [
    ("research", nodes.research_agent),
    ("feature", nodes.feature_agent),
    ("backtest", nodes.backtest_agent),
    ("evaluation", nodes.evaluation_agent),
    ("risk", nodes.risk_agent),
    ("deployment", nodes.deployment_agent),
]


def build_research_graph():
    """Return a compiled LangGraph app, or None if langgraph is unavailable."""
    try:
        from langgraph.graph import StateGraph, END
    except Exception:
        log.warning("langgraph not installed; using sequential fallback executor.")
        return None

    g = StateGraph(ResearchState)
    for name, fn in _PIPELINE:
        g.add_node(name, fn)
    g.set_entry_point(_PIPELINE[0][0])
    for (a, _), (b, _) in zip(_PIPELINE, _PIPELINE[1:]):
        g.add_edge(a, b)
    g.add_edge(_PIPELINE[-1][0], END)
    return g.compile()


def run_research_cycle(config, memory_path: str = "results/research_memory.json") -> ResearchState:
    """Run one full research cycle (real graph if available, else sequential)."""
    state: ResearchState = {"config": config, "memory_path": memory_path}
    app = build_research_graph()
    if app is not None:
        log.info("Running LangGraph research cycle.")
        return app.invoke(state)
    log.info("Running sequential research cycle.")
    for name, fn in _PIPELINE:
        state = fn(state)
    return state
