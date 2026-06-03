from jongga.gate.drift import turnover, return_delta


def test_turnover_jaccard_distance():
    # 교집합 {B,C}=2, 합집합 {A,B,C,D}=4 → 회전 = 1 - 2/4 = 0.5
    assert abs(turnover(["A", "B", "C"], ["B", "C", "D"]) - (1 - 2/4)) < 1e-9

def test_return_delta_relative():
    assert abs(return_delta(t1_mean=0.01, tclose_mean=0.012) - 0.2) < 1e-9
