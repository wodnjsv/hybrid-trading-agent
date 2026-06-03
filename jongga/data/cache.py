"""parquet 캐시 유틸(종류별·날짜별 1파일)."""
from __future__ import annotations
from pathlib import Path
from typing import Callable
import pandas as pd


def cache_path(data_dir, kind: str, key: str) -> Path:
    return Path(data_dir) / kind / f"{key}.parquet"


def load_or_fetch(path: Path, fetch: Callable[[], pd.DataFrame]) -> pd.DataFrame:
    if path.exists():
        return pd.read_parquet(path)
    df = fetch()
    if len(df):                        # 빈 결과(휴장/일시적 오류)는 캐시하지 않음
        path.parent.mkdir(parents=True, exist_ok=True)
        df.to_parquet(path)
    return df
