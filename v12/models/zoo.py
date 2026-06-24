"""Unified model zoo.

Every model exposes the same sklearn-style ``fit``/``predict`` interface so the
walk-forward engine is model-agnostic. Heavy libraries (xgboost, lightgbm,
catboost) are imported lazily and skipped with a warning if unavailable — the
framework still runs on the sklearn-only baseline.
"""
from __future__ import annotations

from typing import Callable, Dict

from ..utils import get_logger

log = get_logger("models")

AVAILABLE_MODELS = ["ridge", "elasticnet", "rf", "xgb", "lgbm", "catboost"]


def _ridge(rs):
    from sklearn.linear_model import Ridge
    from sklearn.pipeline import Pipeline
    from sklearn.preprocessing import StandardScaler
    return Pipeline([("scale", StandardScaler()), ("m", Ridge(alpha=10.0))])


def _elasticnet(rs):
    from sklearn.linear_model import ElasticNet
    from sklearn.pipeline import Pipeline
    from sklearn.preprocessing import StandardScaler
    return Pipeline([("scale", StandardScaler()),
                     ("m", ElasticNet(alpha=0.001, l1_ratio=0.5, max_iter=5000))])


def _rf(rs):
    from sklearn.ensemble import RandomForestRegressor
    return RandomForestRegressor(n_estimators=300, max_depth=6, min_samples_leaf=50,
                                 n_jobs=-1, random_state=rs)


def _xgb(rs):
    import xgboost as xgb
    return xgb.XGBRegressor(n_estimators=400, max_depth=4, learning_rate=0.03,
                            subsample=0.8, colsample_bytree=0.8, min_child_weight=20,
                            reg_lambda=2.0, n_jobs=-1, random_state=rs)


def _lgbm(rs):
    import lightgbm as lgb
    return lgb.LGBMRegressor(n_estimators=500, num_leaves=31, learning_rate=0.02,
                             subsample=0.8, colsample_bytree=0.8, min_child_samples=50,
                             reg_lambda=2.0, n_jobs=-1, random_state=rs, verbose=-1)


def _catboost(rs):
    from catboost import CatBoostRegressor
    return CatBoostRegressor(iterations=400, depth=4, learning_rate=0.03,
                             l2_leaf_reg=3.0, random_state=rs, verbose=False)


_FACTORIES: Dict[str, Callable] = {
    "ridge": _ridge, "elasticnet": _elasticnet, "rf": _rf,
    "xgb": _xgb, "lgbm": _lgbm, "catboost": _catboost,
}


def build_model(name: str, random_state: int = 42):
    """Return a fresh estimator, or None if its library is unavailable."""
    if name not in _FACTORIES:
        raise ValueError(f"Unknown model '{name}'. Options: {list(_FACTORIES)}")
    try:
        return _FACTORIES[name](random_state)
    except Exception as e:
        log.warning("Model '%s' unavailable (%s); skipping.", name, e)
        return None
