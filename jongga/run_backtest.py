"""백테스트 오케스트레이션: KRX daily → t-1 팩터 → 룰 baseline → 일별 종가→익일시초 → §8.4 게이트.

누수 차단(핵심 불변식):
  의사결정일 d에 대해
    - universe/factors = d 이전(≤ d-1) 데이터만 (hist_dates = dates[:i])
    - 매수 = close[d], 매도 = open[d+1], overnight 수익 = (open[d+1]-close[d])/close[d]
    - 팩터별 IC = corr( t-1 팩터값(단면), overnight 수익(단면) )

`collect_gate_inputs`는 순수 함수(패널 입력)라 단위 테스트로 누수 불변식을 강제한다.
`main`은 KrxProvider로 패널을 로드해 진단을 출력한다. 사전등록 정식 게이트(walk-forward·홀드아웃·
슬리피지 밴드·드리프트 θ)는 도메인 값 동결 후 Task 16에서 실행한다.
"""
from __future__ import annotations
import logging

import numpy as np
import pandas as pd

from jongga.universe import build_universe, EXCLUDE_SECT
from jongga.factors.chart import spread, alignment, proximity, days_since_high, vol_ratio
from jongga.factors.value import value_rank
from jongga.selector import score_and_select
from jongga.gate.ic import daily_ic, ic_series_stats, bh_significant

logger = logging.getLogger(__name__)

# IC를 평가할 팩터들(supply는 수급 데이터 있을 때만 채워짐 → 없으면 자동 제외)
FACTOR_COLS = ["spread", "alignment", "proximity", "vol_ratio", "value_rank", "supply"]


def _ticker_factors(ch: pd.Series, vh: pd.Series, cfg) -> dict:
    """단일 종목의 t-1까지 종가(ch)·거래량(vh) 시리즈 → 차트 팩터."""
    w = cfg.factors.ma_windows
    return {
        "spread": spread(ch, w[0], w[-1]),
        "alignment": alignment(ch, w),
        "proximity": proximity(ch, cfg.factors.high_window),
        "days_since_high": float(days_since_high(ch, cfg.factors.high_window)),
        "vol_ratio": vol_ratio(ch.tail(cfg.factors.vol_window), vh.tail(cfg.factors.vol_window)),
    }


def collect_gate_inputs(dates, panels, cfg, weights, costs):
    """dates: 정렬된 거래일. panels: {close,open,value,mcap,sect,vol: [date×ticker], mktval: [date]}.
    return: {factor_ics: {f:[일별 ic]}, net_returns: [일별 바스켓 net], baskets_t1: {d:[종목]}}.
    """
    close, open_ = panels["close"], panels["open"]
    value, mcap, sect, vol = panels["value"], panels["mcap"], panels["sect"], panels["vol"]
    supply = panels.get("supply")  # optional: {date×ticker} (외국인+기관)/거래대금 비율 등
    longest = cfg.factors.ma_windows[-1]

    factor_ics: dict[str, list[float]] = {f: [] for f in FACTOR_COLS}
    net_returns: list[float] = []
    baskets: dict[str, list[str]] = {}

    for i in range(1, len(dates) - 1):
        tm1, d, dp1 = dates[i - 1], dates[i], dates[i + 1]
        hist = dates[:i]  # ≤ t-1 (누수 차단)

        daily_tm1 = pd.DataFrame(
            {"value": value.loc[tm1], "marketcap": mcap.loc[tm1], "sect": sect.loc[tm1]}
        ).dropna(subset=["value"])
        uni = build_universe(daily_tm1, cfg.universe.top_k_value,
                             cfg.universe.min_marketcap, EXCLUDE_SECT)
        if len(uni) < 3:
            continue

        rows = {}
        for t in uni:
            sub = pd.DataFrame({"c": close.loc[hist, t], "v": vol.loc[hist, t]}).dropna()
            if len(sub) < longest:
                continue
            rows[t] = _ticker_factors(sub["c"], sub["v"], cfg)
        if len(rows) < 3:
            continue

        feats = pd.DataFrame(rows).T.astype(float)
        feats["value_rank"] = value_rank(value.loc[tm1, feats.index])
        if supply is not None and tm1 in supply.index:
            feats["supply"] = supply.loc[tm1, feats.index]

        # overnight 수익 (매수 close[d], 매도 open[d+1]) — 미래는 d+1 시초까지만
        c_d = close.loc[d, feats.index]
        ret = (open_.loc[dp1, feats.index] - c_d) / c_d

        # 팩터별 1박 갭 IC
        for f in FACTOR_COLS:
            if f in feats.columns and feats[f].notna().sum() >= 3:
                ic = daily_ic(feats[f], ret)
                if not np.isnan(ic):
                    factor_ics[f].append(ic)

        # 룰 baseline 바스켓 (팩터 단면 랭크 가중합) + net 포트폴리오 수익
        norm = pd.DataFrame(index=feats.index)
        for f in weights:
            norm[f] = feats[f].rank(pct=True)
        norm["days_since_high"] = feats["days_since_high"]
        picks = score_and_select(norm, weights, dsh_penalty=0.0, k=cfg.basket_k)
        baskets[d] = [pk for pk, _ in picks]

        cost = costs["sell_tax"] + 2 * costs["fee"] + 2 * costs["slippage"]
        prets = [float(ret.get(t)) - cost for t, _ in picks if not pd.isna(ret.get(t))]
        if prets:
            net_returns.append(float(np.mean(prets)))

    return {"factor_ics": factor_ics, "net_returns": net_returns, "baskets_t1": baskets}


def load_panels(provider, dates: list[str]):
    """달력 후보일들에 대해 KRX daily를 받아(캐시) [date×ticker] 패널로 적재.
    거래일이 아닌 날(빈 응답)은 건너뛴다. 반환: (실제 거래일 정렬 리스트, panels)."""
    acc = {k: {} for k in ["close", "open", "value", "mcap", "sect", "vol"]}
    mktval = {}
    for dt in dates:
        df = provider.daily(dt)
        if df is None or len(df) == 0:
            continue
        acc["close"][dt] = df["close"]
        acc["open"][dt] = df["open"]
        acc["value"][dt] = df["value"]
        acc["mcap"][dt] = df["marketcap"]
        acc["sect"][dt] = df["sect"]
        acc["vol"][dt] = df["volume"]
        mktval[dt] = float(df["value"].sum())
    panels = {
        "close": pd.DataFrame(acc["close"]).T.sort_index(),
        "open": pd.DataFrame(acc["open"]).T.sort_index(),
        "value": pd.DataFrame(acc["value"]).T.sort_index(),
        "mcap": pd.DataFrame(acc["mcap"]).T.sort_index(),
        "sect": pd.DataFrame(acc["sect"]).T.sort_index(),
        "vol": pd.DataFrame(acc["vol"]).T.sort_index(),
        "mktval": pd.Series(mktval).sort_index(),
    }
    return sorted(mktval), panels


def main(start: str | None = None, end: str | None = None, slippage: float = 0.003) -> None:
    """진단 실행: KRX 패널 로드 → collect_gate_inputs → 팩터 평균 IC·BH·net 요약 출력.
    (정식 사전등록 게이트는 도메인 값 동결 후 Task 16.)"""
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    import yaml
    from pathlib import Path
    from jongga.config import Config
    from jongga.data.krx_provider import KrxProvider

    cfg = Config()
    start = start or cfg.start_date
    krx_key = yaml.safe_load(Path("secrets.yaml").read_text(encoding="utf-8"))["krx_api_key"]
    provider = KrxProvider(cfg.data_dir, krx_key)

    cal = [d.strftime("%Y-%m-%d") for d in pd.bdate_range(start, end)]
    logger.info("loading KRX daily for %d candidate business days...", len(cal))
    dates, panels = load_panels(provider, cal)
    logger.info("trading days loaded: %d (%s ~ %s)", len(dates),
                dates[0] if dates else "-", dates[-1] if dates else "-")

    weights = {"spread": 1.0, "alignment": 1.0, "proximity": 1.0,
               "vol_ratio": 1.0, "value_rank": 1.0}
    costs = {"sell_tax": 0.0018, "fee": 0.00014, "slippage": slippage}
    out = collect_gate_inputs(dates, panels, cfg, weights, costs)

    print("\n=== 팩터 1박 갭 IC (진단) ===")
    pvals = {}
    for f, ics in out["factor_ics"].items():
        if len(ics) >= 2:
            mean_ic, p = ic_series_stats(ics)
            pvals[f] = p
            print(f"  {f:12s} n={len(ics):4d}  meanIC={mean_ic:+.4f}  p={p:.3f}")
    if pvals:
        print(f"  BH(q=0.10) 유의 팩터: {sorted(bh_significant(pvals, q=0.10))}")
    net = np.array(out["net_returns"], dtype=float)
    if len(net):
        print(f"\n=== net 바스켓(슬리피지 편도 {slippage:.2%}) ===")
        print(f"  체결일수={len(net)}  평균={net.mean():+.4%}  승률={(net > 0).mean():.2%}")
    print("\n(정식 게이트=walk-forward·홀드아웃·슬리피지 밴드·드리프트 θ는 도메인 값 동결 후 Task 16.)")


if __name__ == "__main__":
    main()
