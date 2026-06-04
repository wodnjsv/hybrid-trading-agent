import pandas as pd
from jongga.forward.paperbook import PaperBook
from jongga.forward.settle import settle_day


def test_settle_day_fills_exit_and_nets(tmp_path):
    pb = PaperBook(tmp_path / "pb.db")
    base = dict(market="KOSPI", source="llm", k_t=1, catalyst_summary="", catalyst_timestamp="",
                theme="", conviction=0.5, rationale="", websearch_snapshot="{}",
                ret_d=0.0, close_pos=0.5, close_strength=0.0, trade_value=1e12, vol20=0.01)
    pb.record({**base, "run_date": "2026-06-05", "ticker": "005930", "entry_close": 1000.0})
    d1 = pd.DataFrame({"open": [1100.0], "high": [1150.0], "low": [1090.0], "close": [1120.0]},
                      index=["005930"])
    d2 = pd.DataFrame({"close": [1130.0]}, index=["005930"])
    n = settle_day(pb, "2026-06-05", d1, d2)
    assert n == 1
    row = pb.all_settled()[0]
    assert row["exit_open"] == 1100.0 and row["exit_close2"] == 1130.0
    from jongga.forward.cost import overnight_net
    assert abs(row["net_s0"] - overnight_net(1000.0, 1100.0, 0.0)) < 1e-9


def test_settle_skips_missing_ticker(tmp_path):
    pb = PaperBook(tmp_path / "pb.db")
    pb.record(dict(run_date="2026-06-05", market="KOSPI", ticker="999999", source="llm", k_t=1,
                   catalyst_summary="", catalyst_timestamp="", theme="", conviction=0.5,
                   rationale="", websearch_snapshot="{}", entry_close=1000.0, ret_d=0.0,
                   close_pos=0.5, close_strength=0.0, trade_value=1e12, vol20=0.01))
    d1 = pd.DataFrame({"open": [1100.0], "high": [1150.0], "low": [1090.0], "close": [1120.0]},
                      index=["005930"])
    assert settle_day(pb, "2026-06-05", d1, d1) == 0
    assert pb.open_positions("2026-06-05")
