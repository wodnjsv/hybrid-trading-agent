import numpy as np
import pandas as pd
from jongga.factors.chart import spread, alignment, proximity, days_since_high, vol_ratio


def test_spread_normalized_by_long_ma():
    prices = pd.Series([10.0] * 4 + [20.0])     # 최근 급등
    s = spread(prices, short=2, long=4)
    assert s > 0                                 # 단기선이 위

def test_alignment_perfect_uptrend_is_one():
    prices = pd.Series(np.arange(1, 200, dtype=float))  # 단조 증가 → 정배열
    assert alignment(prices, (5, 20, 60, 120)) == 1.0

def test_alignment_perfect_downtrend_is_zero():
    prices = pd.Series(np.arange(200, 1, -1, dtype=float))  # 단조 감소 → 역배열
    assert alignment(prices, (5, 20, 60, 120)) == 0.0

def test_proximity_one_at_new_high():
    prices = pd.Series([10, 12, 11, 15.0])       # 마지막이 최고
    assert abs(proximity(prices, n=4) - 1.0) < 1e-9

def test_days_since_high_zero_at_new_high():
    prices = pd.Series([10, 12, 11, 15.0])
    assert days_since_high(prices, n=4) == 0

def test_vol_ratio_up_volume_dominates():
    closes = pd.Series([10, 11, 10.5, 12.0])     # +,-,+
    vols = pd.Series([10, 100, 10, 100.0])        # up-days(idx 1,3) vol=100, down-day(idx 2) vol=10
    assert vol_ratio(closes, vols) > 1.0
