"""Horse-race standings + weekly/monthly rollups from the shadow ledger.

Reads the append-only paper ledger and produces:
  * current standings per sleeve (days, cumulative return, Sharpe, best/worst day,
    win rate, latest exposure) — the scoreboard;
  * weekly and monthly cumulative-return rollups per sleeve — the digestible
    history for the 90-180 day test.

Pure aggregation of realized paper returns already in the ledger — no model runs,
no new data. Safe to call as often as you like.
"""
from __future__ import annotations

from typing import Dict

import numpy as np
import pandas as pd

# canonical display order (variant 1 -> 7)
SLEEVE_ORDER = ["equity_validated", "equity_full_goal", "crypto_full_goal",
                "full_system", "full_system_max", "metals_full_goal", "full_system_v6",
                "bonds_full_goal"]


def _realized(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty or "day_return" not in df:
        return df.iloc[0:0]
    s = df[df["day_return"].notna()].copy()
    s["day_return"] = s["day_return"].astype(float)
    s["date"] = pd.to_datetime(s["date"])
    return s


def standings(df: pd.DataFrame) -> Dict[str, dict]:
    """Per-sleeve scoreboard from the full ledger."""
    out: Dict[str, dict] = {}
    if df.empty:
        return out
    for sleeve, g in df.groupby("sleeve"):
        g = g.sort_values("date")
        rr = g["day_return"].dropna().astype(float)
        last = g.iloc[-1]
        decs = last.get("decisions")
        expo = (sum(float(d.get("target_weight", 0)) for d in decs)
                if isinstance(decs, list) else float("nan"))
        sd = rr.std()
        out[sleeve] = {
            "n_days": int(len(rr)),
            "cum_return": float((1 + rr).prod() - 1) if len(rr) else 0.0,
            "sharpe": float(rr.mean() / sd * np.sqrt(252)) if len(rr) > 1 and sd > 0 else float("nan"),
            "best_day": float(rr.max()) if len(rr) else float("nan"),
            "worst_day": float(rr.min()) if len(rr) else float("nan"),
            "win_rate": float((rr > 0).mean()) if len(rr) else float("nan"),
            "last_date": str(pd.to_datetime(last["date"]).date()),
            "last_exposure": float(expo),
            "last_positions": int(last.get("n_positions", 0) or 0),
        }
    return out


def period_rollup(df: pd.DataFrame, freq: str) -> pd.DataFrame:
    """Cumulative return per (period, sleeve). freq 'W' weekly, 'M' monthly."""
    s = _realized(df)
    if s.empty:
        return pd.DataFrame()
    s = s.assign(period=s["date"].dt.to_period(freq))
    g = s.groupby(["period", "sleeve"])["day_return"].apply(lambda x: (1 + x).prod() - 1)
    return g.unstack("sleeve")


def _ordered(cols):
    known = [c for c in SLEEVE_ORDER if c in cols]
    return known + [c for c in cols if c not in known]


def _pct(v):
    return "n/a" if v != v else f"{v*100:+.2f}%"


def _num(v):
    return "n/a" if v != v else f"{v:.2f}"


def render_standings(df: pd.DataFrame) -> str:
    st = standings(df)
    L = ["# Shadow Horse-Race Standings", ""]
    if not st:
        return "\n".join(L + ["_No realized returns yet — needs ≥2 runs on different "
                              "trading days. Check back after the test has run a few days._\n"])
    n = max((s["n_days"] for s in st.values()), default=0)
    L.append(f"_Realized paper performance across {n} trading day(s). "
             f"Sharpe needs ~20 days to be meaningful; promotion gate ~90._\n")
    L.append("| variant | days | cum return | Sharpe | best | worst | win% | last expo |")
    L.append("|---|---|---|---|---|---|---|---|")
    for s in _ordered(list(st.keys())):
        r = st[s]
        L.append(f"| {s} | {r['n_days']} | {_pct(r['cum_return'])} | {_num(r['sharpe'])} | "
                 f"{_pct(r['best_day'])} | {_pct(r['worst_day'])} | "
                 f"{_pct(r['win_rate']) if r['win_rate']==r['win_rate'] else 'n/a'} | "
                 f"{r['last_exposure']*100:.0f}% |")

    for freq, title in [("W", "Weekly"), ("M", "Monthly")]:
        roll = period_rollup(df, freq)
        if roll.empty:
            continue
        cols = _ordered(list(roll.columns))
        L.append(f"\n## {title} cumulative return")
        L.append("| period | " + " | ".join(cols) + " |")
        L.append("|" + "---|" * (len(cols) + 1))
        for period, row in roll.iterrows():
            L.append(f"| {period} | " + " | ".join(_pct(row.get(c, float('nan'))) for c in cols) + " |")

    L.append("\n_Shadow/paper only — realized returns of logged decisions, zero real "
             "capital. The question: does any GOAL variant out-Sharpe `equity_validated`?_")
    return "\n".join(L) + "\n"
