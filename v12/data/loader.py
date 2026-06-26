"""Price data loading.

Primary source: yfinance (works in Codespaces/Colab/Digital Ocean).
Cache: on-disk parquet/csv keyed by (ticker, start, end) so repeated runs are
fast and reproducible.
Fallback: a regime-switching synthetic generator used only when the network is
unavailable. Synthetic data carries a *known faint* cross-sectional signal so
the validation machinery has something honest to (fail to) find — it must NOT
be interpreted as real alpha.
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Dict, List, Optional

import numpy as np
import pandas as pd

from ..utils import get_logger

log = get_logger("data")


@dataclass
class PriceData:
    """A tidy OHLCV panel.

    Each field is a DataFrame indexed by date, columns = tickers.
    """
    open: pd.DataFrame
    high: pd.DataFrame
    low: pd.DataFrame
    close: pd.DataFrame
    volume: pd.DataFrame
    source: str = "unknown"

    @property
    def tickers(self) -> List[str]:
        return list(self.close.columns)

    @property
    def dates(self) -> pd.DatetimeIndex:
        return self.close.index

    def slice(self, tickers: List[str]) -> "PriceData":
        keep = [t for t in tickers if t in self.close.columns]
        return PriceData(
            self.open[keep], self.high[keep], self.low[keep],
            self.close[keep], self.volume[keep], self.source,
        )


def _cache_path(cache_dir: str, key: str) -> str:
    os.makedirs(cache_dir, exist_ok=True)
    return os.path.join(cache_dir, f"{key}.parquet")


def _download_yf(tickers: List[str], start: str, end: str) -> Optional[Dict[str, pd.DataFrame]]:
    try:
        import yfinance as yf  # noqa
    except Exception:
        log.warning("yfinance not installed; cannot fetch live data.")
        return None
    try:
        raw = yf.download(tickers, start=start, end=end, progress=False,
                          auto_adjust=True, group_by="column", threads=True)
    except Exception as e:  # pragma: no cover - network dependent
        log.warning("yfinance download failed: %s", e)
        return None
    if raw is None or len(raw) == 0:
        return None
    fields = {}
    # yfinance returns a column MultiIndex (field, ticker) when group_by="column"
    for field in ["Open", "High", "Low", "Close", "Volume"]:
        try:
            sub = raw[field]
        except Exception:
            return None
        if isinstance(sub, pd.Series):
            sub = sub.to_frame(tickers[0])
        fields[field.lower()] = sub.dropna(how="all")
    return fields


def _synthetic(tickers: List[str], start: str, end: str, seed: int,
               signal_strength: float = 1.0) -> Dict[str, pd.DataFrame]:
    """Regime-switching GBM with a faint, *causal* cross-sectional signal.

    Construction (so we know exactly what a model *could* learn):
      - A latent market factor with two volatility regimes (calm/stressed).
      - Each name loads on the market factor (beta) + idiosyncratic noise.
      - A small, persistent "quality" tilt: names with higher latent quality
        earn a tiny positive drift premium. This is the only learnable edge,
        and it is intentionally weak (signal-to-noise is realistic).
    """
    rng = np.random.default_rng(seed)
    dates = pd.bdate_range(start=start, end=end)
    n, m = len(dates), len(tickers)

    # Regime process: Markov switch between calm (low vol) and stress (high vol)
    p_stay = np.array([0.985, 0.95])  # calm sticky, stress less so
    regime = np.zeros(n, dtype=int)
    for t in range(1, n):
        stay = rng.random() < p_stay[regime[t - 1]]
        regime[t] = regime[t - 1] if stay else 1 - regime[t - 1]
    mkt_vol = np.where(regime == 0, 0.008, 0.022)
    mkt_drift = np.where(regime == 0, 0.0004, -0.0006)
    mkt_ret = rng.normal(mkt_drift, mkt_vol)

    beta = rng.uniform(0.6, 1.4, size=m)
    quality = rng.normal(0, 1, size=m)              # latent persistent quality
    idio_vol = rng.uniform(0.010, 0.025, size=m)
    quality_premium = 0.00020 * signal_strength      # ~5bp/wk at strength 1.0

    # Base daily returns: market factor + idiosyncratic noise + faint quality drift.
    base = (
        np.outer(mkt_ret, beta)
        + rng.normal(0, 1, size=(n, m)) * idio_vol
        + quality * quality_premium
    )

    # Observable, learnable momentum factor: part of day-t return is proportional
    # to the cross-sectionally z-scored trailing 20-day return *known at t-1*. This
    # is a genuine, point-in-time-predictable signal that the mom_* / csrank_mom
    # features can capture — so the recovery test actually exercises the ML path.
    # It vanishes at signal_strength=0 (pure noise -> no learnable edge).
    mom_coef = 0.0009 * signal_strength
    logp0 = np.log(100.0)
    log_prices = np.empty((n, m))
    cum = np.full(m, logp0)
    for t in range(n):
        r_t = base[t].copy()
        if mom_coef > 0 and t >= 21:
            trailing = log_prices[t - 1] - log_prices[t - 21]
            sd = trailing.std()
            if sd > 0:
                z = (trailing - trailing.mean()) / sd
                r_t = r_t + mom_coef * z          # momentum predictability
        cum = cum + r_t
        log_prices[t] = cum
    close = pd.DataFrame(np.exp(log_prices), index=dates, columns=tickers)

    # Realized daily returns (for volume's activity proxy)
    rets = np.vstack([np.zeros((1, m)), np.diff(log_prices, axis=0)])

    # Build plausible OHLCV around close
    intraday = np.abs(rng.normal(0, 0.006, size=(n, m)))
    high = close * (1 + intraday)
    low = close * (1 - intraday)
    open_ = close.shift(1).fillna(close.iloc[0])
    base_vol = rng.uniform(2e6, 2e7, size=m)
    volume = pd.DataFrame(
        base_vol * (1 + np.abs(rets) * 30) * rng.uniform(0.7, 1.3, size=(n, m)),
        index=dates, columns=tickers,
    ).round()

    return {
        "open": open_, "high": pd.DataFrame(high, index=dates, columns=tickers),
        "low": pd.DataFrame(low, index=dates, columns=tickers),
        "close": close, "volume": volume,
    }


def load_prices(cfg) -> PriceData:
    """Load OHLCV for universe + benchmark + RS refs.

    ``cfg`` is a DataConfig (see v12.config).
    """
    all_tickers = sorted(set(cfg.universe) | {cfg.benchmark} | set(cfg.rs_refs)
                         | set(getattr(cfg, "extra_benchmarks", [])))
    key = f"prices_{hash((tuple(all_tickers), cfg.start, cfg.end, getattr(cfg, 'signal_strength', 1.0), cfg.synthetic_seed)) & 0xFFFFFFFF:x}"
    path = _cache_path(cfg.cache_dir, key)

    if os.path.exists(path):
        log.info("Loading cached prices from %s", path)
        panel = pd.read_parquet(path)
        fields = {f: panel[f].unstack("ticker") for f in
                  ["open", "high", "low", "close", "volume"]}
        return PriceData(**{k: fields[k] for k in
                            ["open", "high", "low", "close", "volume"]}, source="cache")

    fields = _download_yf(all_tickers, cfg.start, cfg.end)
    source = "yfinance"
    if fields is None:
        if not cfg.allow_synthetic:
            raise RuntimeError("Live data unavailable and synthetic disabled.")
        log.warning("Falling back to SYNTHETIC data (pipeline validation only, NOT alpha).")
        fields = _synthetic(all_tickers, cfg.start, cfg.end, cfg.synthetic_seed,
                            getattr(cfg, "signal_strength", 1.0))
        source = "synthetic"

    # align & forward-fill small gaps, drop all-nan rows
    common = None
    for f in fields.values():
        common = f.index if common is None else common.union(f.index)
    fields = {k: v.reindex(common).ffill().dropna(how="all") for k, v in fields.items()}

    data = PriceData(
        open=fields["open"], high=fields["high"], low=fields["low"],
        close=fields["close"], volume=fields["volume"], source=source,
    )

    # persist cache (tidy/long form so it round-trips cleanly)
    try:
        long = pd.concat(
            {f: getattr(data, f).stack() for f in ["open", "high", "low", "close", "volume"]},
            axis=1,
        )
        long.index.names = ["date", "ticker"]
        long.to_parquet(path)
        log.info("Cached prices -> %s (%s)", path, source)
    except Exception as e:  # parquet engine optional
        log.warning("Could not cache prices (%s); continuing.", e)

    return data
