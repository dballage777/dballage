"""Shared research state + persistent memory.

The agents communicate through a single ``ResearchState`` dict that flows along
the graph, and accumulate long-term findings in ``ResearchMemory`` (a JSON file
on disk). This is how the system "learns from every backtest iteration": each
cycle reads prior findings and appends new ones, so later experiments are
conditioned on earlier ones rather than starting over.
"""
from __future__ import annotations

import json
import os
from dataclasses import dataclass, field, asdict
from datetime import datetime
from typing import Any, Dict, List, Optional, TypedDict


class ResearchState(TypedDict, total=False):
    """Mutable state passed between agent nodes within one research cycle."""
    config: Any                 # ExperimentConfig
    hypotheses: List[str]       # ResearchAgent output
    feature_plan: List[str]     # FeatureAgent output
    backtest_ctx: Dict          # BacktestAgent output (the run() context)
    evaluation: Dict            # EvaluationAgent verdict
    risk_flags: List[str]       # RiskAgent output
    deployment_decision: str    # DeploymentAgent output
    findings: List[str]         # accumulated notes this cycle
    memory_path: str


@dataclass
class Finding:
    cycle: str
    agent: str
    note: str
    metrics: Dict[str, float] = field(default_factory=dict)
    ts: str = field(default_factory=lambda: datetime.utcnow().isoformat())


class ResearchMemory:
    """Append-only JSON store of cross-experiment findings."""

    def __init__(self, path: str = "results/research_memory.json"):
        self.path = path
        self.findings: List[Dict] = []
        if os.path.exists(path):
            try:
                with open(path) as f:
                    self.findings = json.load(f)
            except Exception:
                self.findings = []

    def add(self, finding: Finding):
        self.findings.append(asdict(finding))

    def recent(self, n: int = 10) -> List[Dict]:
        return self.findings[-n:]

    def best_ic(self) -> Optional[Dict]:
        scored = [f for f in self.findings if "ic_mean" in f.get("metrics", {})]
        return max(scored, key=lambda f: f["metrics"]["ic_mean"]) if scored else None

    def save(self):
        os.makedirs(os.path.dirname(self.path) or ".", exist_ok=True)
        with open(self.path, "w") as f:
            json.dump(self.findings, f, indent=2, default=float)
