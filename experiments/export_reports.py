"""Export the shadow horse-race to CSV + PDF (Sheets-friendly + emailable).

    python -m experiments.export_reports --log paper/shadow_ledger.jsonl --out paper/reports

Writes:
  paper/reports/standings.csv       per-variant scoreboard (one row per variant)
  paper/reports/daily_returns.csv   long time-series: date,sleeve,day_return,n_positions
  paper/reports/shadow_report.pdf   one-page PDF (scoreboard + latest allocation)

CSV imports straight into Google Sheets/Excel; the PDF is the emailable summary.
"""
from __future__ import annotations

import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pandas as pd

from v12.execution.ledger import ShadowLedger
from v12.reporting.standings import standings, SLEEVE_ORDER


def _write_csvs(df: pd.DataFrame, st: dict, out: str):
    rows = [{"variant": k, **{kk: vv for kk, vv in v.items()}} for k, v in st.items()]
    order = {n: i for i, n in enumerate(SLEEVE_ORDER)}
    rows.sort(key=lambda r: order.get(r["variant"], 99))
    sc_path = os.path.join(out, "standings.csv")
    pd.DataFrame(rows).to_csv(sc_path, index=False)

    dr_path = os.path.join(out, "daily_returns.csv")
    if not df.empty and "day_return" in df:
        ts = df[df["day_return"].notna()][["date", "sleeve", "day_return", "n_positions"]]
        ts.sort_values(["date", "sleeve"]).to_csv(dr_path, index=False)
    else:
        pd.DataFrame(columns=["date", "sleeve", "day_return", "n_positions"]).to_csv(dr_path, index=False)
    return sc_path, dr_path


def _write_pdf(df: pd.DataFrame, st: dict, out: str):
    try:
        from fpdf import FPDF
        from fpdf.enums import XPos, YPos
    except Exception:
        return None
    pdf = FPDF()
    pdf.set_auto_page_break(auto=True, margin=15)
    pdf.add_page()
    W = pdf.epw

    def line(txt, h=5):
        pdf.multi_cell(W, h, str(txt), new_x=XPos.LMARGIN, new_y=YPos.NEXT)

    last_date = str(pd.to_datetime(df["date"]).max().date()) if not df.empty else "n/a"
    pdf.set_font("Helvetica", "B", 15); line("Shadow Horse-Race Report")
    pdf.set_font("Helvetica", "", 10)
    line(f"As of {last_date}  -  paper/shadow only, zero real capital")
    n = max((v["n_days"] for v in st.values()), default=0)
    line(f"Realized paper performance across {n} trading day(s). "
         f"Sharpe is meaningful ~20 days; promotion gate ~90.")
    pdf.ln(2)

    pdf.set_font("Helvetica", "B", 11); line("Scoreboard")
    pdf.set_font("Courier", "", 9)
    line(f"{'variant':18}{'days':>5}{'cum ret':>10}{'Sharpe':>8}{'win%':>7}{'expo':>7}")
    order = {nme: i for i, nme in enumerate(SLEEVE_ORDER)}
    for name in sorted(st, key=lambda x: order.get(x, 99)):
        r = st[name]
        cr = f"{r['cum_return']*100:+.2f}%"
        sh = "n/a" if r["sharpe"] != r["sharpe"] else f"{r['sharpe']:.2f}"
        wr = "n/a" if r["win_rate"] != r["win_rate"] else f"{r['win_rate']*100:.0f}%"
        line(f"{name:18}{r['n_days']:>5}{cr:>10}{sh:>8}{wr:>7}{r['last_exposure']*100:>6.0f}%")
    pdf.ln(2)
    pdf.set_font("Helvetica", "I", 8)
    line("The question: does any GOAL variant out-Sharpe equity_validated? "
         "Full detail in paper/reports/daily_*.md and STANDINGS.md.")

    path = os.path.join(out, "shadow_report.pdf")
    pdf.output(path)
    return path


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--log", default="paper/shadow_ledger.jsonl")
    p.add_argument("--out", default="paper/reports")
    args = p.parse_args()

    os.makedirs(args.out, exist_ok=True)
    df = ShadowLedger(args.log).load()
    st = standings(df)
    sc, dr = _write_csvs(df, st, args.out)
    pdf = _write_pdf(df, st, args.out)
    print(f"CSV  -> {sc}\nCSV  -> {dr}")
    print(f"PDF  -> {pdf}" if pdf else "PDF  -> skipped (fpdf2 not installed)")


if __name__ == "__main__":
    main()
