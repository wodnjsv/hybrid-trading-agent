# manju/collector/recorder.py
"""Trade/OrderBook → parquet 녹음 (date/symbol 파티셔닝, flush마다 새 파일)."""
from __future__ import annotations
from collections import defaultdict
from pathlib import Path
import pyarrow as pa
import pyarrow.parquet as pq
from manju.models import Trade, OrderBook


class Recorder:
    def __init__(self, data_dir: Path):
        self.data_dir = Path(data_dir)
        self._seq = 0
        # (kind, date, symbol) -> list[dict rows]
        self._buf: dict[tuple, list[dict]] = defaultdict(list)
        self.dates_written: set[str] = set()   # 종료 시 컴팩션 대상 날짜

    def record(self, event) -> None:
        kind = "ticks" if isinstance(event, Trade) else "quotes"
        date = event.market_ts.strftime("%Y-%m-%d")
        self._buf[(kind, date, event.symbol)].append(event.to_row())
        self.dates_written.add(date)

    def flush(self) -> None:
        if not self._buf:
            return
        self._seq += 1
        for (kind, date, symbol), rows in self._buf.items():
            out_dir = self.data_dir / kind / date
            out_dir.mkdir(parents=True, exist_ok=True)
            table = pa.Table.from_pylist(rows)
            pq.write_table(table, out_dir / f"{symbol}-{self._seq:06d}.parquet")
        self._buf.clear()
