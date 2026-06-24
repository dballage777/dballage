"""Out-of-fold stacking ensemble.

Base models are trained on an inner time-series split; their out-of-fold
predictions feed a simple non-negative meta-learner (Ridge). Using OOF
predictions for the meta-features avoids the base models leaking their training
fit into the meta-learner.
"""
from __future__ import annotations

from typing import List, Tuple

import numpy as np

from ..utils import get_logger
from .zoo import build_model

log = get_logger("stacking")


class StackingEnsemble:
    def __init__(self, base_names: List[str], random_state: int = 42, inner_splits: int = 3):
        self.base_names = base_names
        self.random_state = random_state
        self.inner_splits = inner_splits
        self.base_models_ = []
        self.meta_ = None
        self.used_names_ = []

    def fit(self, X: np.ndarray, y: np.ndarray):
        from sklearn.linear_model import Ridge
        from sklearn.model_selection import TimeSeriesSplit

        n = len(X)
        oof = {}
        tscv = TimeSeriesSplit(n_splits=self.inner_splits)
        for name in self.base_names:
            probe = build_model(name, self.random_state)
            if probe is None:
                continue
            preds = np.full(n, np.nan)
            for tr, va in tscv.split(X):
                m = build_model(name, self.random_state)
                m.fit(X[tr], y[tr])
                preds[va] = m.predict(X[va])
            oof[name] = preds
            self.used_names_.append(name)

        if not self.used_names_:
            raise RuntimeError("No base models available for stacking.")

        meta_X = np.column_stack([oof[n] for n in self.used_names_])
        mask = ~np.isnan(meta_X).any(axis=1)
        self.meta_ = Ridge(alpha=1.0, positive=True)
        self.meta_.fit(meta_X[mask], y[mask])
        # Guard against a degenerate meta-learner (all coefficients ~0 -> the
        # ensemble would emit a constant). Fall back to a simple average so the
        # stack always contributes a usable, non-constant signal.
        self._degenerate = bool(np.allclose(self.meta_.coef_, 0.0))

        # refit base models on the full training set for inference
        self.base_models_ = []
        for name in self.used_names_:
            m = build_model(name, self.random_state)
            m.fit(X, y)
            self.base_models_.append(m)
        return self

    def predict(self, X: np.ndarray) -> np.ndarray:
        base_preds = np.column_stack([m.predict(X) for m in self.base_models_])
        if getattr(self, "_degenerate", False):
            return base_preds.mean(axis=1)
        return self.meta_.predict(base_preds)
