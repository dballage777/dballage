"""V12 — Quantitative Research Platform.

A modular, leakage-aware research framework for discovering, validating, and
deploying trading signals that must beat a passive SPY benchmark *after* costs,
slippage, walk-forward validation, out-of-sample testing and Monte-Carlo stress.

Design principles (learned from V1-V11):
    1. Feature quality > model complexity.
    2. No data leakage, ever. Validation is purged & embargoed.
    3. Never optimise for profit alone — optimise for robustness.
    4. Every result must be reproducible from code, never hand-edited.
"""

__version__ = "12.0.0"
