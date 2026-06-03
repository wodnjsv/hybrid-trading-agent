import pandas as pd
from jongga.universe import build_universe, EXCLUDE_SECT


def test_universe_excludes_sect_then_topk_then_mincap():
    daily = pd.DataFrame({
        "value":     [100, 90, 80, 70, 5],
        "marketcap": [1e11, 1e9, 1e11, 1e11, 1e11],
        "sect":      ["우량기업부", "우량기업부", "관리종목(소속부없음)", "중견기업부", "중견기업부"],
    }, index=["A", "B", "C", "D", "E"])
    # 관리종목 C 제외 → 후보 A,B,D,E. 거래대금 상위3 = A,B,D. B 시총미달 → [A, D].
    uni = build_universe(daily, top_k=3, min_cap=5e10, exclude_sect=EXCLUDE_SECT)
    assert uni == ["A", "D"]
