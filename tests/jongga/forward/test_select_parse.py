from jongga.forward.select import parse_selection, SELECTION_SCHEMA


def test_parse_selection_valid():
    raw = {"picks": [
        {"ticker": "005930", "catalyst_summary": "HBM 공급 확대", "catalyst_timestamp": "2026-06-05T13:10",
         "theme": "반도체", "conviction": 0.8, "rationale": "…"},
    ], "regime_read": "강세"}
    picks = parse_selection(raw, candidate_tickers={"005930", "000660"})
    assert len(picks) == 1 and picks[0]["ticker"] == "005930"
    assert 0 <= picks[0]["conviction"] <= 1


def test_parse_selection_pass_is_empty():
    assert parse_selection({"picks": [], "regime_read": "약세-패스"}, {"005930"}) == []


def test_parse_selection_drops_offlist_ticker():
    raw = {"picks": [{"ticker": "111111", "catalyst_summary": "x", "catalyst_timestamp": "t",
                      "theme": "t", "conviction": 0.5, "rationale": "r"}], "regime_read": "-"}
    assert parse_selection(raw, candidate_tickers={"005930"}) == []
