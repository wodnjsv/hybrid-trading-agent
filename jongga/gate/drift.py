# jongga/gate/drift.py
"""드리프트 민감도(§8.4-3): t-1 선정 vs t-종가 선정."""
from __future__ import annotations


def turnover(basket_t1: list[str], basket_tclose: list[str]) -> float:
    a, b = set(basket_t1), set(basket_tclose)
    union = a | b
    if not union:
        return 0.0
    return 1.0 - len(a & b) / len(union)        # 1 - Jaccard


def return_delta(t1_mean: float, tclose_mean: float) -> float:
    if t1_mean == 0:
        return float("inf") if tclose_mean else 0.0
    return abs(tclose_mean - t1_mean) / abs(t1_mean)
