"""Feature pipeline: PriceData -> tidy (date, ticker) feature panel + target.

Leakage controls baked in:
  * Every feature is point-in-time (rolling windows, no forward shift).
  * The target is a *forward* return (close[t]->close[t+h]) and is the ONLY
    column that looks ahead. It is cross-sectionally de-meaned so the model
    learns relative selection, not market beta.
  * Rows whose target window extends past the data end are dropped.
"""
from __future__ import annotations

from typing import List

import numpy as np
import pandas as pd

from ..data import PriceData
from ..utils import get_logger
from . import technical as T
from . import relative as R
from .breadth import compute_breadth
from .cross_sectional import cross_sectional_rank, winsorize_cross_section

log = get_logger("features")


class FeaturePipeline:
    def __init__(self, cfg, data_cfg):
        self.cfg = cfg
        self.data_cfg = data_cfg

    # ---- single-name feature block ----
    def _name_features(self, o, h, l, c, v) -> pd.DataFrame:
        f = {}
        for w in self.cfg.momentum_windows:
            f[f"mom_{w}"] = T.log_momentum(c, w)
        f["adx"] = T.adx(h, l, c)
        f["kama_dist"] = T.kama(c)
        f["hull_dist"] = T.hull_ma(c)
        f["supertrend"] = T.supertrend_signal(h, l, c)
        slope, r2 = T.trend_slope_r2(c, 40)
        f["trend_slope"], f["trend_r2"] = slope, r2
        f["rel_volume"] = T.relative_volume(v)
        f["obv_z"] = T.obv(c, v)
        f["cmf"] = T.cmf(h, l, c, v)
        f["vwap_dist"] = T.vwap_distance(h, l, c, v)
        f["vol_accel"] = T.volume_acceleration(v)
        for w in self.cfg.vol_windows:
            f[f"realized_vol_{w}"] = T.realized_vol(c, w)
        f["atr_pct"] = T.atr_pct(h, l, c)
        f["parkinson_vol"] = T.parkinson_vol(h, l)
        f["yang_zhang_vol"] = T.yang_zhang_vol(o, h, l, c)
        f["vol_of_vol"] = T.vol_of_vol(c)
        f["boll_z"] = T.bollinger_z(c)
        f["ema_dist"] = T.ema_distance(c)
        f["pct_rank_60"] = T.percentile_rank(c, 60)
        f["rsi"] = T.rsi(c)
        return pd.DataFrame(f)

    def build(self, data: PriceData):
        cfg, dcfg = self.cfg, self.data_cfg
        names = [t for t in dcfg.universe if t in data.close.columns]
        log.info("Building features for %d names...", len(names))

        # --- per-name technical + relative-strength features ---
        per_name = {}
        for t in names:
            o, h, l, c, v = (data.open[t], data.high[t], data.low[t],
                             data.close[t], data.volume[t])
            df = self._name_features(o, h, l, c, v)
            for ref in dcfg.rs_refs:
                if ref in data.close.columns:
                    df[f"rs_{ref}"] = R.relative_strength(c, data.close[ref], 60)
            df[f"beta_{dcfg.benchmark}"] = R.rolling_beta(c, data.close[dcfg.benchmark], 60)
            per_name[t] = df

        # --- market breadth (broadcast to all names) ---
        breadth = compute_breadth(data.close[names], self.cfg.breadth_mas)

        # --- cross-sectional ranks of a few base signals ---
        base_for_rank = {
            "csrank_mom": pd.DataFrame({t: per_name[t]["mom_20"] for t in names}),
            "csrank_vol": pd.DataFrame({t: per_name[t]["realized_vol_20"] for t in names}),
            "csrank_rs": pd.DataFrame({t: per_name[t][f"rs_{dcfg.benchmark}"] for t in names}),
            "csrank_liquidity": data.volume[names] * data.close[names],
            "csrank_quality": pd.DataFrame(
                {t: -per_name[t]["realized_vol_60"].fillna(0) + per_name[t]["trend_r2"].fillna(0)
                 for t in names}),
        }
        cs_ranks = {k: cross_sectional_rank(v) for k, v in base_for_rank.items()}

        # --- target: forward h-day return, cross-sectionally de-meaned ---
        h = self.cfg.target_horizon
        fwd = data.close[names].shift(-h) / data.close[names] - 1.0
        # Point-in-time universe masking (survivorship-bias control): names that
        # were not members on a given date contribute no label and are dropped.
        from ..data.universe import membership_mask
        mask = membership_mask(dcfg, data.close.index, names)
        if mask is not None:
            mask = mask.reindex(index=data.close.index, columns=names).fillna(False)
            fwd = fwd.where(mask)
            log.info("Applied point-in-time membership mask (survivorship-safe).")
        target = fwd.sub(fwd.mean(axis=1), axis=0)  # market-neutral label

        # --- assemble long panel ---
        frames = []
        for t in names:
            df = per_name[t].copy()
            for col in breadth.columns:
                df[col] = breadth[col]
            for k in cs_ranks:
                df[k] = cs_ranks[k][t]
            df["target"] = target[t]
            df["ticker"] = t
            frames.append(df)
        panel = pd.concat(frames)
        panel = panel.set_index("ticker", append=True).reorder_levels([0, 1])
        panel.index.names = ["date", "ticker"]

        feature_cols = [c for c in panel.columns if c != "target"]

        # cross-sectional winsorisation per date (robustness, no leakage)
        for col in feature_cols:
            wide = panel[col].unstack("ticker")
            wide = winsorize_cross_section(wide, self.cfg.winsorize_pct)
            panel[col] = wide.stack(future_stack=True).reorder_levels([0, 1])

        before = len(panel)
        panel = panel.replace([np.inf, -np.inf], np.nan).dropna()
        log.info("Feature panel: %d rows (dropped %d warmup/NaN), %d features.",
                 len(panel), before - len(panel), len(feature_cols))
        return panel, feature_cols


def build_dataset(data: PriceData, feature_cfg, data_cfg):
    return FeaturePipeline(feature_cfg, data_cfg).build(data)
