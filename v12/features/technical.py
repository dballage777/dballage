"""Single-name technical features.

Every function takes plain price/volume Series (indexed by date) and returns a
Series aligned to the same index. **All features are strictly point-in-time**:
they use only rolling/expanding windows of past and current data, never a
forward shift. This is the first line of defence against leakage.
"""
from __future__ import annotations

import numpy as np
import pandas as pd


# --- helpers ----------------------------------------------------------------
def _wma(s: pd.Series, n: int) -> pd.Series:
    w = np.arange(1, n + 1)
    return s.rolling(n).apply(lambda x: np.dot(x, w) / w.sum(), raw=True)


def true_range(high, low, close) -> pd.Series:
    prev_close = close.shift(1)
    tr = pd.concat([(high - low), (high - prev_close).abs(), (low - prev_close).abs()], axis=1)
    return tr.max(axis=1)


# --- momentum ---------------------------------------------------------------
def momentum(close: pd.Series, window: int) -> pd.Series:
    """Total return over the trailing ``window`` days."""
    return close.pct_change(window)


def log_momentum(close: pd.Series, window: int) -> pd.Series:
    return np.log(close).diff(window)


# --- trend ------------------------------------------------------------------
def adx(high, low, close, n: int = 14) -> pd.Series:
    """Average Directional Index (Wilder)."""
    up = high.diff()
    down = -low.diff()
    plus_dm = np.where((up > down) & (up > 0), up, 0.0)
    minus_dm = np.where((down > up) & (down > 0), down, 0.0)
    tr = true_range(high, low, close)
    atr = tr.ewm(alpha=1 / n, adjust=False).mean()
    plus_di = 100 * pd.Series(plus_dm, index=close.index).ewm(alpha=1 / n, adjust=False).mean() / atr
    minus_di = 100 * pd.Series(minus_dm, index=close.index).ewm(alpha=1 / n, adjust=False).mean() / atr
    dx = 100 * (plus_di - minus_di).abs() / (plus_di + minus_di).replace(0, np.nan)
    return dx.ewm(alpha=1 / n, adjust=False).mean()


def kama(close: pd.Series, er_window: int = 10, fast: int = 2, slow: int = 30) -> pd.Series:
    """Kaufman Adaptive Moving Average -> distance of price from KAMA."""
    change = close.diff(er_window).abs()
    volatility = close.diff().abs().rolling(er_window).sum()
    er = (change / volatility.replace(0, np.nan)).fillna(0)
    sc = (er * (2 / (fast + 1) - 2 / (slow + 1)) + 2 / (slow + 1)) ** 2
    out = pd.Series(index=close.index, dtype=float)
    prev = close.iloc[0]
    for i, (px, s) in enumerate(zip(close.values, sc.values)):
        prev = prev + (0 if np.isnan(s) else s) * (px - prev)
        out.iloc[i] = prev
    return (close - out) / out  # relative distance


def hull_ma(close: pd.Series, n: int = 20) -> pd.Series:
    """Hull MA -> relative distance of price from HMA."""
    half = max(int(n / 2), 1)
    sqrt_n = max(int(np.sqrt(n)), 1)
    hma = _wma(2 * _wma(close, half) - _wma(close, n), sqrt_n)
    return (close - hma) / hma


def supertrend_signal(high, low, close, n: int = 10, mult: float = 3.0) -> pd.Series:
    """SuperTrend direction in {-1, +1} (uptrend / downtrend)."""
    atr = true_range(high, low, close).ewm(alpha=1 / n, adjust=False).mean()
    hl2 = (high + low) / 2
    upper = hl2 + mult * atr
    lower = hl2 - mult * atr
    direction = pd.Series(1, index=close.index)
    for i in range(1, len(close)):
        if close.iloc[i] > upper.iloc[i - 1]:
            direction.iloc[i] = 1
        elif close.iloc[i] < lower.iloc[i - 1]:
            direction.iloc[i] = -1
        else:
            direction.iloc[i] = direction.iloc[i - 1]
    return direction


def trend_slope_r2(close: pd.Series, n: int = 40):
    """Rolling OLS of log-price vs time -> (annualised slope, R²)."""
    logp = np.log(close)
    x = np.arange(n)
    x_mean = x.mean()
    sxx = ((x - x_mean) ** 2).sum()

    def _slope(y):
        y_mean = y.mean()
        sxy = ((x - x_mean) * (y - y_mean)).sum()
        return sxy / sxx

    def _r2(y):
        y_mean = y.mean()
        sxy = ((x - x_mean) * (y - y_mean)).sum()
        ss_tot = ((y - y_mean) ** 2).sum()
        if ss_tot == 0:
            return 0.0
        ss_res = ss_tot - sxy ** 2 / sxx
        return 1 - ss_res / ss_tot

    slope = logp.rolling(n).apply(_slope, raw=True) * 252
    r2 = logp.rolling(n).apply(_r2, raw=True)
    return slope, r2


# --- volume -----------------------------------------------------------------
def relative_volume(volume: pd.Series, n: int = 20) -> pd.Series:
    return volume / volume.rolling(n).mean()


def obv(close: pd.Series, volume: pd.Series) -> pd.Series:
    """On-Balance Volume -> z-scored to be comparable across names."""
    sign = np.sign(close.diff()).fillna(0)
    raw = (sign * volume).cumsum()
    return (raw - raw.rolling(60).mean()) / raw.rolling(60).std()


def cmf(high, low, close, volume, n: int = 20) -> pd.Series:
    """Chaikin Money Flow."""
    mfm = ((close - low) - (high - close)) / (high - low).replace(0, np.nan)
    mfv = mfm * volume
    return mfv.rolling(n).sum() / volume.rolling(n).sum()


def vwap_distance(high, low, close, volume, n: int = 20) -> pd.Series:
    tp = (high + low + close) / 3
    vwap = (tp * volume).rolling(n).sum() / volume.rolling(n).sum()
    return (close - vwap) / vwap


def volume_acceleration(volume: pd.Series, n: int = 10) -> pd.Series:
    rv = volume.rolling(n).mean()
    return rv.pct_change(n)


# --- volatility -------------------------------------------------------------
def atr_pct(high, low, close, n: int = 14) -> pd.Series:
    return true_range(high, low, close).ewm(alpha=1 / n, adjust=False).mean() / close


def realized_vol(close: pd.Series, n: int = 20) -> pd.Series:
    return close.pct_change().rolling(n).std() * np.sqrt(252)


def vol_of_vol(close: pd.Series, n: int = 20) -> pd.Series:
    rv = close.pct_change().rolling(n).std()
    return rv.rolling(n).std() * np.sqrt(252)


def parkinson_vol(high, low, n: int = 20) -> pd.Series:
    hl = np.log(high / low) ** 2
    return np.sqrt(hl.rolling(n).mean() / (4 * np.log(2)) * 252)


def yang_zhang_vol(open_, high, low, close, n: int = 20) -> pd.Series:
    """Yang-Zhang volatility (drift-independent, handles overnight gaps)."""
    log_ho = np.log(high / open_)
    log_lo = np.log(low / open_)
    log_co = np.log(close / open_)
    log_oc = np.log(open_ / close.shift(1))
    log_cc = np.log(close / close.shift(1))
    k = 0.34 / (1.34 + (n + 1) / (n - 1))
    rs = (log_ho * (log_ho - log_co) + log_lo * (log_lo - log_co)).rolling(n).mean()
    overnight = log_oc.rolling(n).var()
    openclose = log_cc.rolling(n).var()
    return np.sqrt((overnight + k * openclose + (1 - k) * rs) * 252)


# --- mean reversion ---------------------------------------------------------
def bollinger_z(close: pd.Series, n: int = 20) -> pd.Series:
    m = close.rolling(n).mean()
    s = close.rolling(n).std()
    return (close - m) / s


def ema_distance(close: pd.Series, n: int = 20) -> pd.Series:
    ema = close.ewm(span=n, adjust=False).mean()
    return (close - ema) / ema


def percentile_rank(close: pd.Series, n: int = 60) -> pd.Series:
    return close.rolling(n).apply(lambda x: (x < x[-1]).mean(), raw=True)


def rsi(close: pd.Series, n: int = 14) -> pd.Series:
    delta = close.diff()
    gain = delta.clip(lower=0).ewm(alpha=1 / n, adjust=False).mean()
    loss = (-delta.clip(upper=0)).ewm(alpha=1 / n, adjust=False).mean()
    rs = gain / loss.replace(0, np.nan)
    return 100 - 100 / (1 + rs)
