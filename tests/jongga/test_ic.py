import numpy as np
import pandas as pd
from jongga.gate.ic import daily_ic, bh_significant


def test_daily_ic_perfect_rank_is_one():
    feat = pd.Series([1, 2, 3, 4.0], index=list("ABCD"))
    fwd = pd.Series([10, 20, 30, 40.0], index=list("ABCD"))   # 완전 단조
    assert abs(daily_ic(feat, fwd) - 1.0) < 1e-9

def test_bh_significant_counts_corrected():
    pvals = {"f1": 0.001, "f2": 0.04, "f3": 0.2, "f4": 0.9}
    sig = bh_significant(pvals, q=0.10)
    assert "f1" in sig and "f4" not in sig
