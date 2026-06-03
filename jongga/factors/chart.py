# jongga/factors/chart.py
"""t-1 안전 차트 팩터(순수). 입력 prices는 의사결정일 *이전*까지의 종가 시리즈."""
from __future__ import annotations
import numpy as np
import pandas as pd


def _ma(prices: pd.Series, w: int) -> float:
    return float(prices.tail(w).mean())


def spread(prices: pd.Series, short: int, long: int) -> float:
    ml = _ma(prices, long)
    return (_ma(prices, short) - ml) / ml if ml else 0.0


def alignment(prices: pd.Series, windows: tuple[int, ...]) -> float:
    mas = [_ma(prices, w) for w in windows]
    pairs = list(zip(mas, mas[1:]))
    ok = sum(1 for a, b in pairs if a > b)        # 단기 > 장기
    return ok / len(pairs)


def proximity(prices: pd.Series, n: int) -> float:
    window = prices.tail(n)
    mx = float(window.max())
    return float(window.iloc[-1]) / mx if mx else 0.0


def days_since_high(prices: pd.Series, n: int) -> int:
    window = prices.tail(n).reset_index(drop=True)
    return int(len(window) - 1 - window.idxmax())


def vol_ratio(closes: pd.Series, vols: pd.Series) -> float:
    diff = closes.diff()
    up = vols[diff > 0].mean()
    down = vols[diff < 0].mean()
    if not down or np.isnan(down):
        return float("inf") if up and not np.isnan(up) else 1.0
    return float(up / down)
