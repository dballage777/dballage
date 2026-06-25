"""Biweekly-deposit cash manager (GOAL: hold deposits in cash until EV met).

New deposits are NOT auto-invested. They sit in a cash buffer and are released
to the engine only when an EV-positive opportunity exists — or, as a backstop,
after ``max_idle_days`` (default 90) to avoid cash sitting forever.
"""
from __future__ import annotations


class CashManager:
    def __init__(self, max_idle_days: int = 90):
        self.max_idle_days = max_idle_days
        self.buffer = 0.0
        self.idle_days = 0

    def deposit(self, amount: float) -> None:
        self.buffer += max(amount, 0.0)

    def step(self, ev_ok: bool) -> float:
        """Advance one day; return cash released for deployment (0 if held)."""
        if self.buffer <= 0:
            self.idle_days = 0
            return 0.0
        if ev_ok or self.idle_days >= self.max_idle_days:
            released = self.buffer
            self.buffer = 0.0
            self.idle_days = 0
            return released
        self.idle_days += 1
        return 0.0
