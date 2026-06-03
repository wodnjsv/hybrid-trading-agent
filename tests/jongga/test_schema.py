# tests/jongga/test_schema.py
from jongga.data.schema import normalize_supply, INSTITUTION_CATEGORIES


def test_normalize_supply_aggregates_institution_and_foreign():
    # 투자자별 순매수(원) 한 종목·하루치 raw dict
    raw = {
        "기관합계": 1_000_000_000,
        "외국인합계": 2_000_000_000,
        "개인": -3_000_000_000,
        "연기금": 400_000_000,        # 기관 세부(참고 보존)
    }
    out = normalize_supply(raw, trade_value=10_000_000_000)
    assert out["inst_net"] == 1_000_000_000
    assert out["foreign_net"] == 2_000_000_000
    # 정규화: 순매수 / 거래대금
    assert abs(out["inst_net_ratio"] - 0.1) < 1e-9
    assert abs(out["foreign_net_ratio"] - 0.2) < 1e-9
    # 기관 세부 카테고리 목록이 스키마에 고정돼 있다
    assert "연기금" in INSTITUTION_CATEGORIES


def test_normalize_supply_zero_trade_value_safe():
    out = normalize_supply({"기관합계": 100, "외국인합계": 100}, trade_value=0)
    assert out["inst_net_ratio"] == 0.0
    assert out["foreign_net_ratio"] == 0.0
