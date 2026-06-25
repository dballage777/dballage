"""Point-in-time guarantees for insider Form 4 features (V13 #2). No network."""
import os
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import io
import zipfile

from v12.data.insider import parse_form4_xml, _quarter_rows
from v12.features.insider import build_insider_features


def test_bulk_quarter_parser_filters_universe_and_codes():
    """_quarter_rows joins SUBMISSION+NONDERIV_TRANS, keeps only our tickers & P/S."""
    submission = (
        "ACCESSION_NUMBER\tFILING_DATE\tISSUERTRADINGSYMBOL\n"
        "0001-AAPL\t15-FEB-2021\tAAPL\n"
        "0002-XYZ\t16-FEB-2021\tXYZ\n"   # not in our universe -> dropped
    )
    nonderiv = (
        "ACCESSION_NUMBER\tTRANS_CODE\tTRANS_SHARES\tTRANS_PRICEPERSHARE\n"
        "0001-AAPL\tP\t1000\t50\n"       # purchase, kept
        "0001-AAPL\tS\t200\t50\n"        # sale, kept
        "0001-AAPL\tA\t999\t50\n"        # award, dropped
        "0002-XYZ\tP\t5\t10\n"           # wrong ticker, dropped
    )
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("SUBMISSION.tsv", submission)
        z.writestr("NONDERIV_TRANS.tsv", nonderiv)
    rows = _quarter_rows(buf.getvalue(), {"AAPL"})
    assert len(rows) == 2  # only AAPL P and S
    by_purchase = {r[3]: r for r in rows}
    assert by_purchase[1][2] == 50000   # P signed +
    assert by_purchase[0][2] == -10000  # S signed -
    assert all(r[0] == "AAPL" for r in rows)

_FORM4 = """<?xml version="1.0"?>
<ownershipDocument>
  <nonDerivativeTable>
    <nonDerivativeTransaction>
      <transactionCoding><transactionCode>P</transactionCode></transactionCoding>
      <transactionAmounts>
        <transactionShares><value>1000</value></transactionShares>
        <transactionPricePerShare><value>50</value></transactionPricePerShare>
      </transactionAmounts>
    </nonDerivativeTransaction>
    <nonDerivativeTransaction>
      <transactionCoding><transactionCode>S</transactionCode></transactionCoding>
      <transactionAmounts>
        <transactionShares><value>200</value></transactionShares>
        <transactionPricePerShare><value>50</value></transactionPricePerShare>
      </transactionAmounts>
    </nonDerivativeTransaction>
    <nonDerivativeTransaction>
      <transactionCoding><transactionCode>A</transactionCode></transactionCoding>
      <transactionAmounts>
        <transactionShares><value>9999</value></transactionShares>
        <transactionPricePerShare><value>50</value></transactionPricePerShare>
      </transactionAmounts>
    </nonDerivativeTransaction>
  </nonDerivativeTable>
</ownershipDocument>"""


def test_parse_form4_only_open_market():
    txs = parse_form4_xml(_FORM4)
    assert len(txs) == 2  # P and S; the 'A' (award) is ignored
    p = [t for t in txs if t["code"] == "P"][0]
    assert p["signed_value"] == 50000 and p["is_purchase"] == 1
    s = [t for t in txs if t["code"] == "S"][0]
    assert s["signed_value"] == -10000 and s["is_purchase"] == 0


def test_insider_features_are_point_in_time():
    """A purchase filed 2021-06-15 must not show up before that date."""
    frame = pd.DataFrame(
        {"signed_value": [50000.0], "is_purchase": [1]},
        index=pd.DatetimeIndex(["2021-06-15"], name="filed"))
    dates = pd.bdate_range("2021-05-01", "2021-07-31")
    feats = build_insider_features(frame, dates)

    before = feats.loc[dates < "2021-06-15", "insider_buy_count_90d"]
    after = feats.loc[dates >= "2021-06-15", "insider_buy_count_90d"]
    assert (before == 0).all(), "LEAK: insider buy visible before filing date"
    assert (after >= 1).all(), "insider buy never registered after filing"
    # net-buy direction is positive after a pure purchase
    assert feats.loc[dates >= "2021-06-15", "insider_net_buy_norm"].iloc[-1] > 0


def test_missing_insider_is_neutral():
    dates = pd.bdate_range("2021-01-01", periods=10)
    feats = build_insider_features(None, dates)
    assert (feats == 0.0).all().all()
