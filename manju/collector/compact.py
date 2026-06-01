"""일일 컴팩션: 하루치 shard parquet들을 종목당 단일 파일로 병합.

수집기는 크래시 안전을 위해 flush마다 작은 shard 파일(`{symbol}-{seq}.parquet`)을 쓴다.
이 모듈은 하루치 shard를 종목당 1파일(`{symbol}.parquet`)로 병합해 수동 복사·재생을
쉽게 한다. 정상 종료 시 runner가 자동 호출하며, 크래시 후엔 `manju-compact`로 수동 실행한다.
"""
from __future__ import annotations
import os
from collections import defaultdict
from pathlib import Path
import pyarrow as pa
import pyarrow.parquet as pq

_KINDS = ("ticks", "quotes")


def compact_date(data_dir, date: str) -> int:
    """date(YYYY-MM-DD)의 shard들을 종목당 단일 `{symbol}.parquet`으로 병합한다.

    병합 대상 shard는 삭제. market_ts(동률 시 recv_ts) 기준 시간순 정렬.
    이미 병합된 단일 파일만 있으면 그대로 다시 써서 idempotent하다.
    반환: 병합한 (kind, symbol) 수.
    """
    data_dir = Path(data_dir)
    count = 0
    for kind in _KINDS:
        d = data_dir / kind / date
        if not d.exists():
            continue
        groups: dict[str, list[Path]] = defaultdict(list)
        for f in d.glob("*.parquet"):
            symbol = f.stem.split("-")[0]
            groups[symbol].append(f)
        for symbol, files in groups.items():
            target = d / f"{symbol}.parquet"
            merged = pa.concat_tables([pq.read_table(f) for f in files])
            merged = merged.sort_by([("market_ts", "ascending"), ("recv_ts", "ascending")])
            tmp = d / f"{symbol}.parquet.tmp"
            pq.write_table(merged, tmp)
            for f in files:
                if f != target:
                    f.unlink()
            os.replace(tmp, target)
            count += 1
    return count


def _all_dates(data_dir: Path) -> list[str]:
    dates: set[str] = set()
    for kind in _KINDS:
        kd = data_dir / kind
        if kd.exists():
            dates.update(p.name for p in kd.iterdir() if p.is_dir())
    return sorted(dates)


def main() -> None:
    import argparse
    p = argparse.ArgumentParser(description="일일 parquet shard 컴팩션")
    p.add_argument("--data-dir", default="data")
    p.add_argument("--date", default=None, help="YYYY-MM-DD (미지정 시 전체 날짜)")
    a = p.parse_args()
    data_dir = Path(a.data_dir)
    dates = [a.date] if a.date else _all_dates(data_dir)
    for d in dates:
        n = compact_date(data_dir, d)
        print(f"{d}: {n} symbol-file(s) compacted")


if __name__ == "__main__":
    main()
