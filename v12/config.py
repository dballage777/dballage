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

# Broader, sector-diversified universe for robustness testing. Deliberately
# includes long-term laggards (INTC, PFE, VZ, T, CVS, F, GM, MMM, BA, GE...) so
# the short leg of the long-short probe has genuine losers — a stronger test of
# selection skill and a partial dilution of survivorship bias (still current
# constituents; true point-in-time membership remains the gold standard).
BROAD_UNIVERSE: List[str] = [
    "AAPL", "MSFT", "NVDA", "AMZN", "GOOGL", "META", "TSLA", "AVGO", "ORCL",
    "CSCO", "INTC", "IBM", "ADBE", "CRM", "QCOM", "TXN", "AMD", "NFLX", "DIS",
    "CMCSA", "VZ", "T", "JPM", "BAC", "WFC", "GS", "V", "MA", "AXP", "UNH",
    "JNJ", "PFE", "MRK", "ABBV", "LLY", "BMY", "CVS", "WMT", "HD", "PG", "KO",
    "PEP", "COST", "NKE", "MCD", "XOM", "CVX", "CAT", "BA", "GE", "MMM", "HON",
    "F", "GM",
]


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
    # Scales the faint planted cross-sectional signal in synthetic data.
    # 0.0 = pure noise (no learnable edge); 1.0 = realistic-faint (default).
    # Used by the framework-validation harness to test signal recovery.
    signal_strength: float = 1.0
    # SEC EDGAR requires a descriptive User-Agent ("name email"); else env SEC_USER_AGENT.
    sec_user_agent: str = ""


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
    # Add point-in-time SEC EDGAR fundamentals (value/quality/growth) as
    # cross-sectionally ranked features. Off by default (needs network).
    use_fundamentals: bool = False
    # Sector-neutralize: rank signals and de-mean the target WITHIN sector,
    # removing sector bets (V13 enhancement #1).
    sector_neutral: bool = False
    # Add point-in-time insider Form 4 features (cluster buying) (V13 #2).
    use_insider: bool = False


@dataclass
class ModelConfig:
    # Which models from the zoo to compare. Stacking is layered on top.
    # RandomForest is intentionally NOT a default: on small (e.g. 2-core
    # Codespace) machines it dominated runtime (~18 min/run) while badly
    # trailing the linear/boosted models on real data. It stays available in
    # the zoo (add "rf" here to include it). Linear + boosting is the default.
    candidates: List[str] = field(default_factory=lambda: ["ridge", "elasticnet", "lgbm", "xgb"])
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
    max_weight: float = 0.08          # single-position cap (Phase 1: 5-8% for stocks)
    use_kelly: bool = True            # Phase 1: fractional-Kelly risk budget
    kelly_fraction_cap: float = 0.25  # deploy at most 25% of full Kelly
    # Regime filter: cut exposure when the market is not "risk_on" (bear or
    # stressed-vol) — the regimes where the scorecard showed the signal reverses.
    regime_filter: bool = False
    regime_off_exposure: float = 0.20  # exposure multiplier when risk-off


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
