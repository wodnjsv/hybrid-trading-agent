from datetime import datetime
import pyarrow.parquet as pq
from manju.collector.recorder import Recorder
from manju.collector.compact import compact_date
from manju.replay.feed import ReplayFeed
from manju.models import Trade, OrderBook


def _trade(sym, sec):
    ts = datetime(2026, 6, 1, 9, 0, sec)
    return Trade(symbol=sym, market_ts=ts, recv_ts=ts, price=70000, change_rate=1.0,
                 volume=1, cum_volume=1, cum_value=1, strength=100.0, ccld_dvsn="1",
                 ask1=70100, bid1=70000, ask1_qty=1, bid1_qty=1,
                 total_ask_qty=1, total_bid_qty=1, vi_std_price=0, raw="r")


def _quote(sym, sec):
    ts = datetime(2026, 6, 1, 9, 0, sec)
    return OrderBook(symbol=sym, market_ts=ts, recv_ts=ts,
                     asks=[1]*10, bids=[1]*10, ask_qtys=[1]*10, bid_qtys=[1]*10,
                     total_ask_qty=10, total_bid_qty=10, raw="r")


def test_compact_merges_shards_into_one_file_per_symbol(tmp_path):
    rec = Recorder(tmp_path)
    rec.record(_trade("005930", 3)); rec.flush()              # shard 1
    rec.record(_trade("005930", 1)); rec.record(_trade("000660", 2)); rec.flush()  # shard 2
    rec.record(_quote("005930", 2)); rec.flush()              # quote shard

    tdir = tmp_path / "ticks" / "2026-06-01"
    assert len(list(tdir.glob("005930-*.parquet"))) == 2      # compact 전: shard 2개

    n = compact_date(tmp_path, "2026-06-01")
    assert n == 3   # 005930(ticks) + 000660(ticks) + 005930(quotes)

    assert (tdir / "005930.parquet").exists()
    assert (tdir / "000660.parquet").exists()
    assert list(tdir.glob("005930-*.parquet")) == []          # shard 삭제됨

    rows = pq.read_table(tdir / "005930.parquet").to_pylist()
    assert len(rows) == 2                                      # row 보존
    mt = [r["market_ts"] for r in rows]
    assert mt == sorted(mt)                                    # 시간순 정렬


def test_compact_is_idempotent(tmp_path):
    rec = Recorder(tmp_path)
    rec.record(_trade("005930", 1)); rec.flush()
    compact_date(tmp_path, "2026-06-01")
    compact_date(tmp_path, "2026-06-01")                       # 재실행해도 안전
    rows = pq.read_table(tmp_path / "ticks" / "2026-06-01" / "005930.parquet").to_pylist()
    assert len(rows) == 1


def test_replay_reads_compacted_output(tmp_path):
    rec = Recorder(tmp_path)
    rec.record(_trade("005930", 2)); rec.record(_quote("005930", 1)); rec.flush()
    compact_date(tmp_path, "2026-06-01")
    evs = list(ReplayFeed(tmp_path, "2026-06-01").events())
    assert [e.market_ts.second for e in evs] == [1, 2]
    assert isinstance(evs[0], OrderBook) and isinstance(evs[1], Trade)
