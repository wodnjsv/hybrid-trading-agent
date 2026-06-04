"""익일 정산: 미정산 행 + d+1 일봉(+d+2 종가) → exit·net밴드·settled."""
from __future__ import annotations
import pandas as pd
from jongga.forward.cost import overnight_net, SLIP_BANDS
from jongga.forward.paperbook import PaperBook


def settle_day(pb: PaperBook, run_date: str, d1: pd.DataFrame, d2: pd.DataFrame) -> int:
    """run_date의 미정산 포지션을 d1(익일 OHLC)·d2(d+2 종가)로 정산. 정산 건수 반환."""
    settled = 0
    for row in pb.open_positions(run_date):
        t = row["ticker"]
        if t not in d1.index or pd.isna(d1.loc[t, "open"]):
            continue
        exit_open = float(d1.loc[t, "open"])
        nets = {s: overnight_net(row["entry_close"], exit_open, s) for s in SLIP_BANDS}
        c2 = float(d2.loc[t, "close"]) if (d2 is not None and t in d2.index) else None
        pb.settle(row["id"], exit_open, float(d1.loc[t, "high"]), float(d1.loc[t, "low"]),
                  float(d1.loc[t, "close"]), c2, nets)
        settled += 1
    return settled
