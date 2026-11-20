"""Shadow-ledger integrity audit + learning-loop reconstruction.

Two questions, both answered from code (no hand-typed numbers):

1. INTEGRITY — is each logged ``day_return`` what the book actually earned?
   Every sleeve-day is RE-MARKED against freshly downloaded closes, using the
   exact attribution rule the runner uses (previous row's target weights x
   asset return between the two row dates; cash earns 0). A logged return of
   exactly 0.0 while the held book really moved is flagged STALE.

2. LEARNING LOOP — what did the loop actually decide each day?
   Replays ``full_system``'s stock/crypto exposure multipliers from the ledger
   history available BEFORE each run (same ``reweight_sleeves`` + 63-day
   rolling Sharpe), on both the logged and the re-marked returns.

    python -m experiments.audit_shadow                      # writes results/audit/*
    python -m experiments.audit_shadow --out docs/reports/data

Needs live yfinance. Paper/shadow data only; not investment advice.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import warnings

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
warnings.filterwarnings("ignore")

import numpy as np
import pandas as pd

from v12.learning.reweight import reweight_sleeves, MIN_DAYS

STOCK, CRYPTO = "equity_full_goal", "crypto_full_goal"
WINDOW = 63           # ShadowLedger.rolling_performance default
EPS = 1e-6            # |return| below this counts as "zero"


# ----------------------------------------------------------------------------- io
def load_rows(path: str) -> list[dict]:
    rows = [json.loads(l) for l in open(path) if l.strip()]
    rows.sort(key=lambda r: r["date"])
    return rows


def targets(row: dict) -> dict:
    return {d["asset"]: float(d.get("target_weight", 0.0)) for d in row.get("decisions", [])
            if "asset" in d and float(d.get("target_weight", 0.0) or 0.0) > 0}


def download_closes(tickers, start, end) -> pd.DataFrame:
    import yfinance as yf
    df = yf.download(sorted(tickers), start=start, end=end, progress=False,
                     auto_adjust=True, threads=True)["Close"]
    if isinstance(df, pd.Series):
        df = df.to_frame(sorted(tickers)[0])
    return df


def _ret(close: pd.DataFrame, tgt: dict, d0: str, d1: str):
    """Runner's rule: sum_w w*(P(d1)/P(d0)-1) using last close at/before each date."""
    t0, t1 = pd.Timestamp(d0), pd.Timestamp(d1)
    total, missing = 0.0, []
    for a, w in tgt.items():
        if a not in close.columns:
            missing.append(a)
            continue
        s = close[a].dropna()
        p0, p1 = s.asof(t0), s.asof(t1)
        if not (p0 == p0 and p1 == p1) or p0 <= 0:
            missing.append(a)
            continue
        total += w * (p1 / p0 - 1.0)
    return float(total), missing


# ---------------------------------------------------------------------- metrics
def stats(r: pd.Series) -> dict:
    r = r.dropna().astype(float)
    if r.empty:
        return {"n_days": 0}
    nav = (1 + r).cumprod()
    sd = r.std()
    return {
        "n_days": int(len(r)),
        "cum_return": float(nav.iloc[-1] - 1),
        "ann_vol": float(sd * np.sqrt(252)) if sd > 0 else 0.0,
        "sharpe": float(r.mean() / sd * np.sqrt(252)) if sd > 0 else float("nan"),
        "max_drawdown": float((nav / nav.cummax() - 1).min()),
        "best_day": float(r.max()),
        "worst_day": float(r.min()),
        "invested_days_pct": float((r.abs() > EPS).mean()),
    }


# ------------------------------------------------------------------- integrity
def remark(rows: list[dict], close: pd.DataFrame) -> pd.DataFrame:
    by = {}
    for r in rows:
        by.setdefault(r["sleeve"], []).append(r)
    out = []
    for sleeve, rs in by.items():
        for prev, cur in zip(rs, rs[1:]):
            logged = cur.get("day_return")
            if logged is None:
                continue
            tgt = targets(prev)
            true, missing = _ret(close, tgt, prev["date"], cur["date"])
            out.append({"date": cur["date"], "sleeve": sleeve, "prev_date": prev["date"],
                        "held_weight": sum(tgt.values()), "logged": float(logged),
                        "remarked": true, "missing": ",".join(missing)})
    df = pd.DataFrame(out)
    df["diff"] = df["logged"] - df["remarked"]
    df["stale"] = (df["logged"].abs() < EPS) & (df["remarked"].abs() > EPS)
    df["mismatch"] = (df["diff"].abs() > 1e-4) & ~df["stale"]
    return df


# --------------------------------------------------------------- learning loop
def replay_learning(rows: list[dict], returns: pd.DataFrame, col: str) -> pd.DataFrame:
    """For each full_system run date D, rebuild the multipliers from returns
    logged strictly before D (what the runner could see)."""
    run_dates = sorted({r["date"] for r in rows if r["sleeve"] == "full_system"})
    out = []
    for d in run_dates:
        perf = {}
        for n in (STOCK, CRYPTO):
            s = returns[(returns["sleeve"] == n) & (returns["date"] < d)][col].tail(WINDOW)
            sd = s.std() if len(s) > 1 else float("nan")
            perf[n] = {"n_days": int(len(s)),
                       "sharpe": float(s.mean() / sd * np.sqrt(252)) if sd and sd > 0 else float("nan")}
        has = any(p["n_days"] >= 1 and p["sharpe"] == p["sharpe"] for p in perf.values())
        w = reweight_sleeves(perf)
        if not w or not has:
            mult, active = {STOCK: 1.0, CRYPTO: 1.0}, False
        else:
            top = max(w.values()) or 1.0
            mult, active = {n: min(w[n] / top, 1.0) for n in (STOCK, CRYPTO)}, True
        out.append({"date": d, "active": active,
                    "stock_n": perf[STOCK]["n_days"], "stock_sharpe": perf[STOCK]["sharpe"],
                    "crypto_n": perf[CRYPTO]["n_days"], "crypto_sharpe": perf[CRYPTO]["sharpe"],
                    "stock_mult": mult[STOCK], "crypto_mult": mult[CRYPTO]})
    return pd.DataFrame(out)


def drift_history(path: str) -> pd.DataFrame:
    out = []
    for r in load_rows(path):
        if r["sleeve"] != "drift_monitor":
            continue
        for d in r["decisions"]:
            out.append({"date": r["date"], **{k: d.get(k) for k in
                        ("sleeve", "n", "roll_sharpe", "sharpe_lcb", "decay_flag", "drift_flag", "note")}})
    return pd.DataFrame(out)


def timer_history(path: str) -> pd.DataFrame:
    out = []
    for r in load_rows(path):
        if r["sleeve"] in ("vrp_timer", "regime_timer", "market_ref"):
            m = next((d.get("suggested_mult") for d in r["decisions"] if "suggested_mult" in d), None)
            st = next((d.get("state") for d in r["decisions"] if "state" in d), None)
            out.append({"date": r["date"], "sleeve": r["sleeve"], "day_return": r.get("day_return"),
                        "mult": m, "state": st})
    return pd.DataFrame(out)


# ------------------------------------------------------------------------ main
def main():
    p = argparse.ArgumentParser()
    p.add_argument("--main", default="paper/shadow_ledger.jsonl")
    p.add_argument("--signal", default="paper/signal_shadow_ledger.jsonl")
    p.add_argument("--aggr", default="paper/aggressive_shadow_ledger.jsonl")
    p.add_argument("--out", default="results/audit")
    a = p.parse_args()
    os.makedirs(a.out, exist_ok=True)

    ledgers = {"main": load_rows(a.main), "aggressive": load_rows(a.aggr)}
    tickers = {"SPY"}
    for rows in ledgers.values():
        for r in rows:
            tickers |= set(targets(r))
    start = min(r["date"] for rs in ledgers.values() for r in rs)
    end = (pd.Timestamp(max(r["date"] for rs in ledgers.values() for r in rs))
           + pd.Timedelta(days=3)).strftime("%Y-%m-%d")
    close = download_closes(tickers, (pd.Timestamp(start) - pd.Timedelta(days=10)).strftime("%Y-%m-%d"), end)
    print(f"[data] yfinance closes: {close.shape[1]} tickers, {close.index.min():%Y-%m-%d}..{close.index.max():%Y-%m-%d}")

    summary = {"data_source": "yfinance (re-mark, downloaded at audit time)",
               "ledger_span": [start, max(r["date"] for r in ledgers["main"])], "ledgers": {}}
    for name, rows in ledgers.items():
        rm = remark(rows, close)
        rm.to_csv(f"{a.out}/remark_{name}.csv", index=False)
        per = {}
        for s, g in rm.groupby("sleeve"):
            per[s] = {"logged": stats(g.set_index("date")["logged"]),
                      "remarked": stats(g.set_index("date")["remarked"]),
                      "stale_days": int(g["stale"].sum()),
                      "mismatch_days": int(g["mismatch"].sum()),
                      "rows": int(len(g)),
                      "stale_dates": g.loc[g["stale"], "date"].tolist()}
        summary["ledgers"][name] = per

    # common-window comparison vs the REAL SPY over the benchmark's span
    rm_main = pd.read_csv(f"{a.out}/remark_main.csv")
    spy_dates = rm_main[rm_main["sleeve"] == "market_spy"]["date"]
    w0, w1 = spy_dates.min(), spy_dates.max()
    common = {}
    for s, g in rm_main.groupby("sleeve"):
        g = g[(g["date"] >= w0) & (g["date"] <= w1)].set_index("date")
        common[s] = {"logged": stats(g["logged"]), "remarked": stats(g["remarked"])}
    spy = close["SPY"].dropna()
    spy = spy[(spy.index >= pd.Timestamp(w0) - pd.Timedelta(days=5)) & (spy.index <= pd.Timestamp(w1))]
    summary["common_window"] = {"start": w0, "end": w1, "sleeves": common,
                                "spy_true_daily": stats(spy.pct_change().loc[w0:])}

    # learning loop replay on logged vs re-marked returns
    ret_long = rm_main[["date", "sleeve", "logged", "remarked"]]
    ll_logged = replay_learning(ledgers["main"], ret_long, "logged")
    ll_true = replay_learning(ledgers["main"], ret_long, "remarked")
    ll = ll_logged.merge(ll_true, on="date", suffixes=("_logged", "_remarked"))
    ll.to_csv(f"{a.out}/learning_replay.csv", index=False)

    # does full_system's logged return equal crypto's (i.e. stock leg zeroed)?
    pv = rm_main.pivot_table(index="date", columns="sleeve", values="logged")
    both = pv[["full_system", CRYPTO]].dropna()
    summary["learning"] = {
        "runs": int(len(ll)),
        "first_active": ll.loc[ll["active_logged"], "date"].min() if ll["active_logged"].any() else None,
        "days_stock_mult_zero_logged": int((ll["stock_mult_logged"] < 1e-9).sum()),
        "days_stock_mult_zero_remarked": int((ll["stock_mult_remarked"] < 1e-9).sum()),
        "days_crypto_mult_zero_logged": int((ll["crypto_mult_logged"] < 1e-9).sum()),
        "days_crypto_mult_zero_remarked": int((ll["crypto_mult_remarked"] < 1e-9).sum()),
        "multiplier_disagree_days": int(((ll["stock_mult_logged"] - ll["stock_mult_remarked"]).abs()
                                         + (ll["crypto_mult_logged"] - ll["crypto_mult_remarked"]).abs()
                                         > 0.05).sum()),
        "full_eq_crypto_days": int(((both["full_system"] - both[CRYPTO]).abs() < 1e-9).sum()),
        "full_vs_crypto_days": int(len(both)),
        "last": ll.iloc[-1].to_dict(),
    }

    dh = drift_history(a.signal)
    dh.to_csv(f"{a.out}/drift_history.csv", index=False)
    th = timer_history(a.signal)
    th.to_csv(f"{a.out}/timer_history.csv", index=False)
    # timers: re-mark as previous suggested_mult x real SPY return over the gap
    spy_px = close["SPY"].dropna()
    timers = {}
    for s, g in th.groupby("sleeve"):
        g = g.sort_values("date").reset_index(drop=True)
        rr = []
        for i in range(1, len(g)):
            m = 1.0 if s == "market_ref" else float(g.loc[i - 1, "mult"])
            p0 = spy_px.asof(pd.Timestamp(g.loc[i - 1, "date"]))
            p1 = spy_px.asof(pd.Timestamp(g.loc[i, "date"]))
            rr.append((g.loc[i, "date"], m * (p1 / p0 - 1.0), g.loc[i, "day_return"]))
        df = pd.DataFrame(rr, columns=["date", "remarked", "logged"]).set_index("date")
        timers[s] = {"logged": stats(df["logged"].fillna(0.0)), "remarked": stats(df["remarked"]),
                     "stale_days": int(((df["logged"].fillna(0).abs() < EPS)
                                        & (df["remarked"].abs() > EPS)).sum()),
                     "mean_mult": float(g["mult"].mean()),
                     "states": g["state"].value_counts().to_dict()}
    summary["timers"] = timers
    last = dh[dh["date"] == dh["date"].max()]
    summary["drift_last"] = last.drop(columns="date").to_dict("records")

    with open(f"{a.out}/summary.json", "w") as f:
        json.dump(summary, f, indent=2, default=str)
    print(f"[ok] wrote {a.out}/summary.json")


if __name__ == "__main__":
    main()
