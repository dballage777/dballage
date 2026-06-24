"""Point-in-time guarantees for insider Form 4 features (V13 #2). No network."""
import os
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from v12.data.insider import parse_form4_xml
from v12.features.insider import build_insider_features

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
