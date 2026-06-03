# jongga/universe.py
"""t-1 유니버스: (소속부 제외) → 거래대금 상위 K → 시총하한.
입력 daily = KRX 일별매매정보(index=ticker가 곧 PIT 멤버십, 상폐 포함)."""
from __future__ import annotations
import pandas as pd

EXCLUDE_SECT = ("관리종목(소속부없음)", "투자주의환기종목(소속부없음)",
                "SPAC(소속부없음)", "외국기업(소속부없음)")


def build_universe(daily: pd.DataFrame, top_k: int, min_cap: float,
                   exclude_sect: tuple[str, ...]) -> list[str]:
    eligible = daily[~daily["sect"].isin(exclude_sect)]
    ranked = eligible.sort_values("value", ascending=False).head(top_k)
    return [t for t in ranked.index if float(ranked.loc[t, "marketcap"]) >= min_cap]
