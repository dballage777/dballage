"""Hard risk-control governor (capital-preservation layer).

Path-dependent kill-switches the GOAL spec requires but the engine lacked. Each
is point-in-time: today's allowed exposure is decided from state through
*yesterday* only, so there is no look-ahead.

Canonical values (resolving spec-gap C1 — single numbers, not ranges):
  max_drawdown   = 20%   -> kill to cash; re-enter when DD recovers above -10%
  daily_loss_stop=  4%   -> cash cooldown after any day worse than -4%
  consec_losses  =  3    -> freeze after 3 consecutive losing days
  cooldown_days  =  5    -> length of the post-trigger cash cooldown
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass
class RiskGovernor:
    max_drawdown: float = 0.20
    daily_loss_stop: float = 0.04
    max_consec_losses: int = 3
    cooldown_days: int = 5
    reenter_drawdown: float = 0.10

    def __post_init__(self):
        self.nav = 1.0
        self.peak = 1.0
        self.consec = 0
        self.cooldown = 0
        self.killed = False
        self.last_reason = ""

    def exposure(self) -> float:
        """Exposure allowed TODAY, based only on state through yesterday."""
        if self.killed:
            self.last_reason = "max-drawdown kill-switch"
            return 0.0
        if self.cooldown > 0:
            self.last_reason = "loss-stop / consecutive-loss freeze"
            return 0.0
        self.last_reason = ""
        return 1.0

    def update(self, day_return: float) -> None:
        """Advance state with the realized (already-exposure-applied) return."""
        self.nav *= (1.0 + day_return)
        self.peak = max(self.peak, self.nav)
        dd = self.nav / self.peak - 1.0

        if dd <= -self.max_drawdown:
            self.killed = True
        elif self.killed and dd >= -self.reenter_drawdown:
            self.killed = False  # recovered enough to re-enter

        if day_return <= -self.daily_loss_stop:
            self.cooldown = self.cooldown_days
        elif self.cooldown > 0:
            self.cooldown -= 1

        if day_return < 0:
            self.consec += 1
        else:
            self.consec = 0
        if self.consec >= self.max_consec_losses:
            self.cooldown = max(self.cooldown, self.cooldown_days)


def governor_exposure_from_returns(returns, max_drawdown: float = 0.20,
                                   daily_loss_stop: float = 0.04,
                                   max_consec_losses: int = 3,
                                   cooldown_days: int = 5,
                                   reenter_drawdown: float = 0.10):
    """Replay the hard-risk governor over a sleeve's realized-return history and
    return ``(exposure_today, reason)``.

    ``exposure_today`` is 1.0 (trade allowed) or 0.0 (cash) based only on returns
    through *yesterday* — no look-ahead. This is how the live decision path gets
    the GOAL drawdown kill-switch / daily-loss stop / consecutive-loss freeze that
    was previously only in the backtest."""
    g = RiskGovernor(max_drawdown, daily_loss_stop, max_consec_losses,
                     cooldown_days, reenter_drawdown)
    for r in returns:
        if r is None or r != r:          # skip None / NaN
            continue
        g.update(float(r))
    exp = g.exposure()
    return exp, (g.last_reason or "ok")
