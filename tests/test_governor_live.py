"""Live hard-risk governor: replay over a return history -> today's exposure."""
from v12.risk.governor import governor_exposure_from_returns as gov


def test_empty_history_allows_trading():
    exp, reason = gov([])
    assert exp == 1.0 and reason == "ok"


def test_calm_history_allows_trading():
    exp, _ = gov([0.001, -0.002, 0.003, 0.001, -0.001])
    assert exp == 1.0


def test_daily_loss_stop_triggers_cash():
    # a day worse than -4% -> cooldown -> cash today
    exp, reason = gov([0.0, -0.05])
    assert exp == 0.0
    assert "loss" in reason


def test_three_consecutive_losses_freeze():
    exp, reason = gov([-0.01, -0.01, -0.01])
    assert exp == 0.0
    assert "loss" in reason or "consecutive" in reason


def test_max_drawdown_kill_switch():
    # cumulative drawdown beyond -20% -> kill to cash
    exp, reason = gov([-0.08, -0.08, -0.08])      # ~ -22% compounded
    assert exp == 0.0
    assert "drawdown" in reason or "loss" in reason


def test_recovers_after_drawdown():
    # deep drawdown then a strong recovery above the -10% re-enter band
    rets = [-0.08, -0.08, -0.08] + [0.06] * 8
    exp, _ = gov(rets)
    assert exp == 1.0


def test_nans_skipped():
    exp, _ = gov([0.01, None, float("nan"), 0.01])
    assert exp == 1.0
