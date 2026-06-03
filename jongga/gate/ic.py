# jongga/gate/ic.py
"""팩터의 1박 갭 IC 게이트(§8.4-1). Spearman IC + BH 보정 + 부호안정성."""
from __future__ import annotations
import numpy as np
import pandas as pd
from scipy import stats


def daily_ic(feature: pd.Series, fwd_return: pd.Series) -> float:
    """단면 Spearman rank IC (한 거래일)."""
    common = feature.dropna().index.intersection(fwd_return.dropna().index)
    if len(common) < 3:
        return np.nan
    rho, _ = stats.spearmanr(feature[common], fwd_return[common])
    return float(rho)


def bh_significant(pvals: dict[str, float], q: float = 0.10) -> set[str]:
    """Benjamini-Hochberg FDR로 유의한 팩터 집합."""
    items = sorted(pvals.items(), key=lambda kv: kv[1])
    m = len(items)
    sig: set[str] = set()
    for i, (name, p) in enumerate(items, start=1):
        if p <= (i / m) * q:
            sig = {n for n, _ in items[:i]}
    return sig


def ic_series_stats(ics: list[float]) -> tuple[float, float]:
    """일별 IC 시계열 → (평균 IC, 양측 p값[H0: 평균=0])."""
    a = np.array([x for x in ics if not np.isnan(x)])
    if len(a) < 2:
        return (float("nan"), 1.0)
    t, p = stats.ttest_1samp(a, 0.0)
    return (float(a.mean()), float(p))
