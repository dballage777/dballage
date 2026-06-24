"""Central configuration.

All experiment knobs live here as plain dataclasses so a run is fully described
by a single ``ExperimentConfig`` object (reproducibility).
"""
from __future__ import annotations

from dataclasses import dataclass, field, asdict
from typing import List
import json


# --- Universes ---------------------------------------------------------------
# A compact, liquid US-equity universe + the sector ETFs used for relative
# strength. Kept small on purpose: more names != more alpha, and a tight,
# liquid universe keeps transaction-cost assumptions honest.
DEFAULT_UNIVERSE: List[str] = [
    "AAPL", "MSFT", "NVDA", "AMZN", "GOOGL", "META", "TSLA", "AVGO",
    "JPM", "V", "UNH", "XOM", "JNJ", "WMT", "PG", "HD", "MA", "COST",
    "BAC", "KO", "PEP", "CSCO", "MRK", "ABBV", "CVX",
]
BENCHMARK = "SPY"
RELATIVE_STRENGTH_REFS: List[str] = ["SPY", "QQQ", "XLK", "XLF", "XLY", "XLI"]


@dataclass
class DataConfig:
    universe: List[str] = field(default_factory=lambda: list(DEFAULT_UNIVERSE))
    benchmark: str = BENCHMARK
    rs_refs: List[str] = field(default_factory=lambda: list(RELATIVE_STRENGTH_REFS))
    start: str = "2015-01-01"
    end: str = "2025-01-01"
    cache_dir: str = "data_cache"
    # "static" (current constituents — survivorship biased) or a path to a
    # point-in-time membership CSV (columns: ticker,start,end). See data/universe.py.
    universe_source: str = "static"
    # When True, falls back to a synthetic generator if a live download fails
    # (e.g. restricted network). Synthetic data is for *pipeline validation only*.
    allow_synthetic: bool = True
    synthetic_seed: int = 7


@dataclass
class FeatureConfig:
    momentum_windows: List[int] = field(default_factory=lambda: [5, 10, 20, 40, 60, 120])
    vol_windows: List[int] = field(default_factory=lambda: [10, 20, 60])
    breadth_mas: List[int] = field(default_factory=lambda: [20, 50, 200])
    # Forward return horizon (trading days) used to build the target. The label
    # for day t is the return from close[t] -> close[t+horizon]; features at t
    # must use *only* information up to and including t.
    target_horizon: int = 5
    winsorize_pct: float = 0.01  # cross-sectional winsorisation on features


@dataclass
class ModelConfig:
    # Which models from the zoo to compare. Stacking is layered on top.
    candidates: List[str] = field(default_factory=lambda: ["ridge", "elasticnet", "rf", "lgbm", "xgb"])
    use_stacking: bool = True
    random_state: int = 42


@dataclass
class ValidationConfig:
    n_splits: int = 6           # walk-forward folds
    train_min_days: int = 504   # ~2y minimum train window
    test_days: int = 63         # ~1 quarter OOS per fold
    embargo_days: int = 5       # >= target_horizon to prevent label leakage
    purge: bool = True


@dataclass
class BacktestConfig:
    top_quantile: float = 0.30        # long the top 30% by predicted score
    rebalance_days: int = 5           # rebalance cadence (trading days)
    commission_bps: float = 1.0       # per-side commission
    slippage_bps: float = 5.0         # per-side slippage assumption
    initial_capital: float = 500.0
    dca_amount: float = 100.0         # contribution per interval
    dca_interval_days: int = 10       # ~ every 2 weeks of trading days
    dca_mode: str = "dca"             # "none" | "dca" | "variable"
    vol_target_annual: float = 0.15   # annualised vol target (None disables)
    weighting: str = "inverse_vol"    # "equal" | "inverse_vol" | "risk_parity"
    max_weight: float = 0.20          # position cap


@dataclass
class ExperimentConfig:
    name: str = "v12_baseline"
    data: DataConfig = field(default_factory=DataConfig)
    features: FeatureConfig = field(default_factory=FeatureConfig)
    models: ModelConfig = field(default_factory=ModelConfig)
    validation: ValidationConfig = field(default_factory=ValidationConfig)
    backtest: BacktestConfig = field(default_factory=BacktestConfig)
    output_dir: str = "results"

    def to_json(self) -> str:
        return json.dumps(asdict(self), indent=2)

    def __post_init__(self):
        # Safety invariant: embargo must cover the label horizon, otherwise the
        # test fold can "see" prices that overlap the training labels.
        if self.validation.embargo_days < self.features.target_horizon:
            self.validation.embargo_days = self.features.target_horizon
