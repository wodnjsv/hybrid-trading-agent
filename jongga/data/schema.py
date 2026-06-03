# jongga/data/schema.py
"""정규 데이터 스키마. pykrx/KIS가 같은 의미의 수치를 내도록 고정(DF-2)."""
from __future__ import annotations

# 기관 세부 카테고리(참고 보존용 — '기관합계'와 별도로 합 검증 가능)
INSTITUTION_CATEGORIES = ["금융투자", "보험", "투신", "사모", "은행",
                          "기타금융", "연기금", "기타법인"]


def normalize_supply(raw: dict, trade_value: int) -> dict:
    """투자자별 순매수(원) raw → 정규 수급 레코드.

    inst_net/foreign_net = 기관합계/외국인합계 순매수액,
    *_ratio = 순매수액 / 거래대금 (거래대금 0이면 0).
    """
    inst = int(raw.get("기관합계", 0))
    foreign = int(raw.get("외국인합계", 0))
    denom = trade_value if trade_value else 0
    return {
        "inst_net": inst,
        "foreign_net": foreign,
        "inst_net_ratio": (inst / denom) if denom else 0.0,
        "foreign_net_ratio": (foreign / denom) if denom else 0.0,
    }
