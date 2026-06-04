from jongga.forward.paperbook import PaperBook


def test_record_and_query_open(tmp_path):
    pb = PaperBook(tmp_path / "pb.db")
    row = dict(run_date="2026-06-05", market="KOSPI", ticker="005930", source="llm",
               k_t=2, catalyst_summary="HBM 공급", catalyst_timestamp="2026-06-05T14:50",
               theme="반도체", conviction=0.8, rationale="…", websearch_snapshot="{}",
               entry_close=80000.0, ret_d=0.03, close_pos=0.9, close_strength=0.02,
               trade_value=1e12, vol20=0.02)
    pb.record(row)
    pb.record({**row, "ticker": "000660", "source": "baseline"})
    opens = pb.open_positions("2026-06-05")
    assert len(opens) == 2
    assert {o["ticker"] for o in opens} == {"005930", "000660"}
    assert all(o["settled"] == 0 for o in opens)


def test_open_positions_excludes_settled(tmp_path):
    pb = PaperBook(tmp_path / "pb.db")
    row = dict(run_date="2026-06-05", market="KOSPI", ticker="005930", source="llm",
               k_t=1, catalyst_summary="", catalyst_timestamp="", theme="", conviction=0.5,
               rationale="", websearch_snapshot="{}", entry_close=80000.0, ret_d=0.0,
               close_pos=0.5, close_strength=0.0, trade_value=1e12, vol20=0.01)
    rid = pb.record(row)
    pb.settle(rid, exit_open=81000, exit_high=82000, exit_low=80000,
              exit_close1=81500, exit_close2=82000, nets={0.0: 0.01, 0.0005: 0.009, 0.001: 0.008})
    assert pb.open_positions("2026-06-05") == []
