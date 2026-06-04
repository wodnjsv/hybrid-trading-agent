"""forward CLI: eve(종가 선별·기록) / morn(익일 정산) / report_cmd(A/B 리포트)."""
from __future__ import annotations
import json
import logging
import sys
from pathlib import Path

import pandas as pd
import yaml

from jongga.config import Config
from jongga.data.krx_provider import KrxProvider
from jongga.data.pykrx_supply import PykrxSupply
from jongga.forward.paperbook import PaperBook
from jongga.forward.report import paired_by_day
from jongga.forward.screen import entry_covariates
from jongga.forward.select import select_with_gpt, parse_selection
from jongga.forward.settle import settle_day
from jongga.run_backtest import load_panels
from jongga.universe import build_universe, EXCLUDE_SECT

DB = Path("data/forward/paperbook.db")
SHORTLIST_N = 30
K_DEFAULT = 3

_name_cache: dict[str, str] = {}


def _secrets() -> dict:
    return yaml.safe_load(Path("secrets.yaml").read_text(encoding="utf-8"))


def _ticker_name(code: str) -> str:
    if code in _name_cache:
        return _name_cache[code]
    try:
        from pykrx import stock
        name = stock.get_market_ticker_name(code)
    except Exception:
        name = code
    _name_cache[code] = name
    return name


def eve(argv=None) -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    log = logging.getLogger(__name__)

    if argv is None:
        argv = sys.argv[1:]
    explicit_date = argv[0] if argv else None

    secrets = _secrets()
    krx_key = secrets["krx_api_key"]
    cfg = Config()

    DB.parent.mkdir(parents=True, exist_ok=True)
    pb = PaperBook(DB)

    for market in ("KOSPI", "KOSDAQ"):
        log.info("=== %s: 패널 로드 시작 ===", market)

        # ~150 거래일이 되려면 달력 약 220일
        if explicit_date:
            anchor = pd.Timestamp(explicit_date)
        else:
            anchor = pd.Timestamp.today().normalize()
        cal_start = anchor - pd.Timedelta(days=220)
        cal = [d.strftime("%Y-%m-%d") for d in pd.bdate_range(cal_start, anchor)]

        provider = KrxProvider(cfg.data_dir, krx_key, market)
        supply_prov = PykrxSupply(cfg.data_dir, market)
        dates, panels = load_panels(provider, cal, supply_prov)

        if len(dates) < 2:
            log.warning("%s: 거래일 부족 (%d일), 스킵", market, len(dates))
            continue

        # 요청일 결정: 명시 날짜가 dates에 있으면 사용, 없으면 마지막 거래일
        if explicit_date and explicit_date in dates:
            d = explicit_date
        else:
            d = dates[-1]
        d_idx = dates.index(d)
        if d_idx == 0:
            log.warning("%s: d=%s 가 첫 번째 거래일이라 t-1 없음, 스킵", market, d)
            continue
        tm1 = dates[d_idx - 1]

        close = panels["close"]
        open_ = panels["open"]
        high = panels["high"]
        low = panels["low"]
        value = panels["value"]
        mcap = panels["mcap"]
        sect = panels["sect"]
        inst = panels.get("inst_net")
        foreign = panels.get("foreign_net")

        # 후보 풀
        daily = pd.DataFrame({
            "value": value.loc[d],
            "marketcap": mcap.loc[d],
            "sect": sect.loc[d],
        }).dropna(subset=["value"])
        cand_tickers = build_universe(daily, SHORTLIST_N, cfg.universe.min_marketcap, EXCLUDE_SECT)

        candidates: list[dict] = []
        for s in cand_tickers:
            if s not in close.columns:
                continue
            ch = close.loc[:d, s].dropna()
            if len(ch) < 25:
                continue
            px = float(close.loc[d, s])
            pxm1 = float(close.loc[tm1, s]) if s in close.columns else None
            if pxm1 is None or pxm1 == 0:
                continue
            ret_d = (px - pxm1) / pxm1
            ma20 = float(ch.tail(20).mean())

            # 수급 필터
            sup_ok = False
            if inst is not None and foreign is not None:
                if s in inst.columns and s in foreign.columns:
                    iv = inst.loc[tm1, s] if tm1 in inst.index else None
                    fv = foreign.loc[tm1, s] if tm1 in foreign.index else None
                    sup_ok = (iv is not None and fv is not None
                               and not pd.isna(iv) and not pd.isna(fv)
                               and float(iv) > 0 and float(fv) > 0)

            if not (sup_ok and px > ma20 and 0 < ret_d < 0.10):
                continue

            cov = entry_covariates(
                ch,
                float(open_.loc[d, s]) if s in open_.columns else px,
                float(high.loc[d, s]) if s in high.columns else px,
                float(low.loc[d, s]) if s in low.columns else px,
                float(value.loc[d, s]) if s in value.columns else 0.0,
            )
            candidates.append({
                "ticker": s,
                "name": _ticker_name(s),
                "market": market,
                "entry_close": px,
                "supply_note": "외/기 순매수",
                **cov,
            })

        log.info("%s d=%s: 후보 %d종목", market, d, len(candidates))
        if not candidates:
            log.warning("%s: 후보 없음, 스킵", market)
            continue

        # LLM 선별
        raw = select_with_gpt(candidates, secrets["openai_api_key"])
        picks = parse_selection(raw, {c["ticker"] for c in candidates})
        k_t = len(picks)
        log.info("%s: LLM 픽 %d종목 %s", market, k_t,
                 [p["ticker"] for p in picks])

        ticker_to_cand = {c["ticker"]: c for c in candidates}
        websearch_snap = json.dumps(raw, ensure_ascii=False)

        # LLM 행 기록
        for p in picks:
            c = ticker_to_cand[p["ticker"]]
            pb.record({
                "run_date": d,
                "market": market,
                "ticker": p["ticker"],
                "source": "llm",
                "k_t": k_t,
                "catalyst_summary": p["catalyst_summary"],
                "catalyst_timestamp": p["catalyst_timestamp"],
                "theme": p["theme"],
                "conviction": float(p["conviction"]),
                "rationale": p["rationale"],
                "websearch_snapshot": websearch_snap,
                "entry_close": c["entry_close"],
                "ret_d": c["ret_d"],
                "close_pos": c["close_pos"],
                "close_strength": c["close_strength"],
                "trade_value": c["trade_value"],
                "vol20": c["vol20"],
            })

        # baseline 행 기록
        k_base = k_t if k_t > 0 else K_DEFAULT
        baseline = sorted(candidates, key=lambda c: -c["trade_value"])[:k_base]
        log.info("%s: baseline %d종목 %s", market, len(baseline),
                 [b["ticker"] for b in baseline])
        for b in baseline:
            pb.record({
                "run_date": d,
                "market": market,
                "ticker": b["ticker"],
                "source": "baseline",
                "k_t": k_t,
                "catalyst_summary": "",
                "catalyst_timestamp": "",
                "theme": "",
                "conviction": 0.0,
                "rationale": "",
                "websearch_snapshot": "",
                "entry_close": b["entry_close"],
                "ret_d": b["ret_d"],
                "close_pos": b["close_pos"],
                "close_strength": b["close_strength"],
                "trade_value": b["trade_value"],
                "vol20": b["vol20"],
            })

    log.info("eve 완료")


def morn(argv=None) -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    log = logging.getLogger(__name__)

    if not DB.exists():
        log.warning("paperbook.db 없음, 정산 대상 없음")
        return

    pb = PaperBook(DB)
    secrets = _secrets()
    krx_key = secrets["krx_api_key"]
    cfg = Config()

    # 미정산 run_date 목록
    cur = pb.conn.execute("SELECT DISTINCT run_date, market FROM paper WHERE settled=0")
    open_days = [(r["run_date"], r["market"]) for r in cur.fetchall()]

    if not open_days:
        log.info("정산 대상 없음")
        return

    # run_date별·market별로 그룹화
    from collections import defaultdict
    by_date: dict[str, set[str]] = defaultdict(set)
    for rd, mkt in open_days:
        by_date[rd].add(mkt)

    total_settled = 0
    for run_date in sorted(by_date):
        for market in sorted(by_date[run_date]):
            log.info("정산 시도: run_date=%s market=%s", run_date, market)
            provider = KrxProvider(cfg.data_dir, krx_key, market)

            # run_date 이후 달력일 탐색 → 첫 두 거래일(d+1, d+2) 찾기
            rd_ts = pd.Timestamp(run_date)
            # 넉넉히 30 캘린더일 뒤까지 후보 생성
            search_cal = [d.strftime("%Y-%m-%d")
                          for d in pd.bdate_range(rd_ts + pd.Timedelta(days=1),
                                                  rd_ts + pd.Timedelta(days=30))]
            trading_after: list[str] = []
            for dt in search_cal:
                df = provider.daily(dt)
                if df is not None and len(df) > 0:
                    trading_after.append(dt)
                if len(trading_after) >= 2:
                    break

            if len(trading_after) < 1:
                log.warning("%s %s: d+1 거래일 없음, 스킵", run_date, market)
                continue

            d1_raw = provider.daily(trading_after[0])
            d1_df = d1_raw[["open", "high", "low", "close"]]

            d2_df = None
            if len(trading_after) >= 2:
                d2_raw = provider.daily(trading_after[1])
                d2_df = d2_raw[["close"]]

            n = settle_day(pb, run_date, d1_df, d2_df)
            log.info("정산 완료: %s %s → %d건", run_date, market, n)
            total_settled += n

    log.info("morn 완료: 총 정산 %d건", total_settled)


def report_cmd(argv=None) -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

    if not DB.exists():
        print("paperbook.db 없음")
        return

    pb = PaperBook(DB)
    rows = pb.all_settled()
    if not rows:
        print("정산된 행 없음")
        return

    for market in ("KOSPI", "KOSDAQ"):
        mrows = [r for r in rows if r["market"] == market]
        if not mrows:
            continue
        for band in ("net_s0", "net_s05", "net_s10"):
            res = paired_by_day(mrows, band)
            print(
                f"[{market}][{band}] n_days={res['n_days']} "
                f"mean_diff={res['mean_diff']:.4%} "
                f"llm_mean={res['llm_mean']:.4%} "
                f"p_rel={res['p_rel']:.3f}"
            )
