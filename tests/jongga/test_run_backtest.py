"""백테스트 오케스트레이션 핵심 — 누수 차단 불변식 검증.

핵심: 의사결정일 d의 팩터/universe는 d-1까지만, 매수=close[d], 매도=open[d+1].
미래값(close[d], open/close[d+2..])을 바꿔도 day d 이전 결정·산출이 흔들리면 누수 버그.
"""
import numpy as np
import pandas as pd
from jongga.config import Config
from jongga.run_backtest import collect_gate_inputs


def _panel(values: dict, dates, tickers):
    return pd.DataFrame(values, index=dates, columns=tickers)


def _synthetic(cfg, close_overrides=None):
    # 6 거래일, 6 종목(모두 우량기업부·시총 충분·거래대금 충분)
    dates = [f"2024-01-0{i}" for i in range(1, 7)]
    tickers = [f"T{i}" for i in range(6)]
    rng = np.arange(1, 7).reshape(-1, 1)
    base = 1000 + rng * np.arange(6) * 10.0      # date×ticker, 종목마다 다른 추세
    close = _panel(base.copy(), dates, tickers)
    if close_overrides:
        for (dt, tk), v in close_overrides.items():
            close.loc[dt, tk] = v
    open_ = close * 1.001                          # 시초 = 종가의 +0.1% (단순)
    value = _panel(np.full((6, 6), 1e10), dates, tickers)
    mcap = _panel(np.full((6, 6), 1e11), dates, tickers)
    sect = _panel(np.full((6, 6), "우량기업부", dtype=object), dates, tickers)
    vol = _panel(np.full((6, 6), 1000.0), dates, tickers)
    mktval = pd.Series(value.sum(axis=1), index=dates)
    return dates, dict(close=close, open=open_, value=value, mcap=mcap,
                       sect=sect, vol=vol, mktval=mktval)


WEIGHTS = {"spread": 1.0, "value_rank": 1.0}
COSTS = {"sell_tax": 0.0, "fee": 0.0, "slippage": 0.0}


def test_collect_produces_ics_and_net_returns():
    cfg = Config()
    cfg = Config(  # 작은 룩백으로 합성 6일에서도 팩터 계산 가능
        factors=type(cfg.factors)(ma_windows=(2, 3), high_window=3, vol_window=2),
        universe=type(cfg.universe)(top_k_value=10, min_marketcap=1),
        basket_k=3,
    )
    dates, p = _synthetic(cfg)
    out = collect_gate_inputs(dates, p, cfg, WEIGHTS, COSTS)
    assert "spread" in out["factor_ics"]
    assert len(out["net_returns"]) >= 1          # 최소 한 거래일 체결
    # 매수=close[d], 매도=open[d+1]=close[d+1]*1.001 인 합성이므로 overnight 수익이 계산됨


def test_no_lookahead_future_close_does_not_change_day_d():
    cfg = Config(
        factors=type(Config().factors)(ma_windows=(2, 3), high_window=3, vol_window=2),
        universe=type(Config().universe)(top_k_value=10, min_marketcap=1),
        basket_k=3,
    )
    dates, p = _synthetic(cfg)
    base_out = collect_gate_inputs(dates, p, cfg, WEIGHTS, COSTS)

    # 마지막 날(미래) 종가를 크게 바꿔도 그 이전 거래일들의 net_returns는 불변이어야 한다.
    dates2, p2 = _synthetic(cfg, close_overrides={("2024-01-06", "T3"): 999999.0})
    fut_out = collect_gate_inputs(dates2, p2, cfg, WEIGHTS, COSTS)

    # day d=2024-01-04(매수)·매도 01-05 까지는 01-06 종가와 무관 → 앞부분 net_returns 동일
    n = min(len(base_out["net_returns"]), len(fut_out["net_returns"]))
    # 01-06이 매도일(d+1)인 거래일 d=01-05만 영향. 그 이전 거래일들은 동일.
    assert base_out["net_returns"][:n - 1] == fut_out["net_returns"][:n - 1]
