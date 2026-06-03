# jongga/selector.py
"""룰 baseline selector(§5.5). 팩터 가중합 − DaysSinceHigh 패널티 → 상위 K."""
from __future__ import annotations
import pandas as pd


def score_and_select(feats: pd.DataFrame, weights: dict[str, float],
                     dsh_penalty: float, k: int) -> list[tuple[str, float]]:
    score = sum(feats[col] * w for col, w in weights.items())
    if dsh_penalty:                    # 패널티 0이면 days_since_high 컬럼 불요
        score = score - dsh_penalty * feats["days_since_high"]
    # conviction = min-max 정규화(0~1)
    lo, hi = score.min(), score.max()
    conv = (score - lo) / (hi - lo) if hi > lo else score * 0.0
    top = conv.sort_values(ascending=False).head(k)
    return [(t, float(c)) for t, c in top.items()]
