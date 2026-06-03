# 종가베팅 Phase 0+1 — 데이터·팩터·룰 baseline 백테스트·게이트 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** pykrx(KRX EOD)로 t-1 안전팩터를 계산해 룰 baseline(종가매수→익일시초매도)을 백테스트하고, §8.4 사전등록 게이트(팩터의 1박 갭 IC·비용 net 엣지·드리프트 민감도)를 자동 판정하는 실행 가능한 하네스를 만든다. 이 하네스가 전략의 make-or-break(#6: 다일 팩터가 1박 갭을 예측하는가)에 답한다.

**Architecture:** 단일 프로세스 Python. `data/`(pykrx 어댑터 + 정규 스키마 + parquet 캐시) 위에 `factors/`(t-1 안전 순수함수)·`universe`·`regime`·`selector`·`sizing`를 얹고, `backtest/`(체결모델 + 엔진)가 일별 종가→익일시초 시뮬을, `gate/`(IC·드리프트·리포트)가 사전등록 합격선 판정을 한다. **모든 선정 입력은 t-1 확정치만 사용**(누수 차단). 백테스트 충격은 EOD proxy 밴드.

**Tech Stack:** Python 3.11, pykrx, pandas, numpy, scipy(통계·BH 보정), pyarrow(parquet), pytest.

**참조 스펙:** `docs/superpowers/specs/2026-06-03-jongga-closebet-agent-design.md` (v4) — §5.2 팩터, §5.5 baseline, §6 sizing, §8.2 체결모델, §8.4 게이트, §8.3 데이터, §11 Phase 0/1, §12.1 사전등록 미정값.

**스코프 경계(이 계획 밖):** KIS 예상체결 TR 어댑터·라이브 충격 캘리브(Phase 3), LLM 재료/Selector(Phase 2), 실행·주문(Phase 3). 이 계획은 pykrx만 사용하며 KIS 의존성 없음.

---

## File Structure

```
jongga/                         # 신규 패키지 (이름 변경 가능)
  __init__.py
  config.py                     # 데이터 경로 + 파라미터(룩백·universe컷 등) 로드
  calendar.py                   # 거래일(영업일) 유틸 — pykrx 기반
  data/
    __init__.py
    schema.py                   # 정규 스키마: DailyBar, SupplyRow(외국인/기관 카테고리 정규화)
    provider.py                 # MarketDataProvider 추상 인터페이스
    pykrx_provider.py           # pykrx 구현 + parquet 캐시
  factors/
    __init__.py
    chart.py                    # MA/Spread/Alignment/Proximity/DaysSinceHigh/VolRatio/NearMA (t-1, 순수)
    flow.py                     # 수급 정규화 팩터(t-1)
    value.py                    # 거래대금 순위 팩터(t-1)
  universe.py                   # t-1 유니버스 구성(거래대금K ∩ 시총하한 ∩ 제외) + PIT
  regime.py                     # 시황등급/배수(t-1 코스닥 거래대금)
  selector.py                   # 룰 baseline selector(팩터 가중합 + DaysSinceHigh 패널티)
  sizing.py                     # 정량가중 sizing + caps(EOD proxy)
  backtest/
    __init__.py
    fill_model.py               # 체결모델: 슬리피지 밴드 + 강제다일(하한가/거래정지) 분기
    metrics.py                  # 승률·평균갭·MDD·회전율·net(수수료+거래세+슬리피지)
    engine.py                   # 일별 종가매수→익일시초매도 시뮬
  gate/
    __init__.py
    ic.py                       # 팩터 1박갭 Spearman IC + BH/Bonferroni 보정 + 부호안정성
    drift.py                    # 드리프트 민감도 θ1(회전)/θ2(수익델타)
    report.py                   # §8.4 게이트 판정 리포트
  run_backtest.py               # 엔트리: walk-forward + 홀드아웃 게이트 실행
tests/jongga/                   # 신규 테스트(기존 manju 테스트와 분리)
  ...
docs/superpowers/prereg/
  2026-06-04-phase1-gate-prereg.md   # Phase 0 사전등록 문서
```

**책임 분리:** `schema`/`factors`/`universe`/`regime`/`selector`/`sizing`/`fill_model`/`metrics`/`ic`/`drift`는 네트워크 없는 순수 로직 → TDD. `pykrx_provider`의 실호출은 통합 검증(실제 출력 대조 후 필드 매핑 확정). `engine`/`run_backtest`는 통합.

**누수 차단 불변식(전 태스크 공통):** 의사결정일 `d`의 선정·수급·universe·regime 입력은 **`d` 이전(t-1 이하)** 데이터만. 매수 체결가 = `d` 종가, 매도 = `d+1` 시초. 이 불변식은 Task 12 엔진에서 단위테스트로 강제한다.

---

## Task 0: 스캐폴드 — 패키지 + 의존성 + config

**Files:**
- Modify: `pyproject.toml`
- Create: `jongga/__init__.py`, `jongga/data/__init__.py`, `jongga/factors/__init__.py`, `jongga/backtest/__init__.py`, `jongga/gate/__init__.py`, `tests/jongga/__init__.py`
- Create: `jongga/config.py`

- [ ] **Step 1: pyproject.toml에 jongga 패키지 + 의존성 추가**

`[tool.setuptools]`의 `packages` 배열에 jongga 패키지들을 추가하고, `[project].dependencies`에 백테스트 의존성을 추가:

```toml
[tool.setuptools]
packages = ["manju", "manju.kis", "manju.collector", "manju.replay",
            "jongga", "jongga.data", "jongga.factors", "jongga.backtest", "jongga.gate"]

[project]
name = "manju"
version = "0.0.0"
requires-python = ">=3.11"
dependencies = [
    "websockets>=12.0",
    "requests>=2.31",
    "pyarrow>=15.0",
    "pyyaml>=6.0",
    "pykrx>=1.0.45",
    "pandas>=2.0",
    "numpy>=1.26",
    "scipy>=1.11",
]
```

- [ ] **Step 2: 패키지 디렉터리 + 빈 `__init__.py` 생성**

Run:
```bash
cd /Users/kimjaewon/Pluto/hybrid-trading-agent && mkdir -p jongga/data jongga/factors jongga/backtest jongga/gate tests/jongga && \
touch jongga/__init__.py jongga/data/__init__.py jongga/factors/__init__.py jongga/backtest/__init__.py jongga/gate/__init__.py tests/jongga/__init__.py
```

- [ ] **Step 3: config.py 작성**

```python
# jongga/config.py
"""백테스트 설정 + 사전등록 파라미터. 값은 §12.1 사전등록 문서와 일치시킨다."""
from __future__ import annotations
from dataclasses import dataclass, field
from pathlib import Path


@dataclass(frozen=True)
class FactorParams:
    ma_windows: tuple[int, ...] = (5, 20, 60, 120)
    high_window: int = 120          # 신고가 룩백 N
    vol_window: int = 20            # VolRatio 윈도우
    near_ma_pct: float = 0.03       # NearMA ±x%


@dataclass(frozen=True)
class UniverseParams:
    top_k_value: int = 100          # 거래대금 상위 K
    min_marketcap: int = 50_000_000_000  # 안전 시총 하한(동전주·상폐 배제 수준; 랭킹은 별도)


@dataclass(frozen=True)
class Config:
    data_dir: Path = Path("data/krx")
    start_date: str = "2018-01-01"
    holdout_start: str = "2025-01-01"   # 홀드아웃 시작(이전=walk-forward, 이후=최종 1회)
    market: str = "KOSDAQ"              # 시황·universe 기준 시장
    factors: FactorParams = field(default_factory=FactorParams)
    universe: UniverseParams = field(default_factory=UniverseParams)
    basket_k: int = 5                  # 최종 바스켓 종목 수
    capital: int = 100_000_000
```

- [ ] **Step 4: 설치 + import 확인**

Run:
```bash
cd /Users/kimjaewon/Pluto/hybrid-trading-agent && .venv/bin/pip install -e ".[dev]" && .venv/bin/python -c "import jongga.config; print('ok')"
```
Expected: 마지막 줄 `ok` (pykrx/pandas/numpy/scipy 설치됨)

- [ ] **Step 5: Commit**

```bash
git add pyproject.toml jongga tests/jongga && git commit -m "chore: scaffold jongga backtest package + deps"
```

---

## Task 1: Phase 0 게이트 사전등록 문서

데이터를 보기 *전에* 합격선·방법을 동결한다(과최적화 방어, §8.4/§12.1). 코드 없음 — 권위 있는 사전등록.

**Files:**
- Create: `docs/superpowers/prereg/2026-06-04-phase1-gate-prereg.md`

- [ ] **Step 1: 사전등록 문서 작성**

아래 내용으로 작성한다. (숫자 중 도메인 판단이 필요한 항목은 `[사용자 확정]`로 표기 — 실행 전 사용자에게 확인.)

```markdown
# Phase 1 게이트 사전등록 (2026-06-04, 데이터 관측 전 동결)

## 검증 프로토콜
- 데이터: pykrx KOSDAQ EOD, 2018-01-01 ~ 현재.
- 분할: walk-forward(확장 윈도우, 매 분기 재평가) + 홀드아웃(2025-01-01 이후, 최종 1회만 본다).
- 탐색은 walk-forward 내부에서만. 홀드아웃은 파라미터 동결 후 단 1회 평가.

## 게이트 1순위 (load-bearing) — 팩터의 1박 갭 IC (룰 baseline 한정)
- 타깃: 종목별 t→t+1 overnight 수익 r = (open_{t+1} − close_t)/close_t.
- 지표: 각 팩터의 Spearman rank IC (단면, 일별) → 시계열 평균 IC와 t-통계.
- 다중검정 보정: Benjamini-Hochberg FDR, q = 0.10. (팩터 ~6개.)
- 합격: 보정 후 유의(q<0.10) 팩터 ≥ m=2개 AND 부호 안정(해당 팩터 IC 부호가 walk-forward 폴드의 ≥75%에서 일치).
- 실패 처리: "룰 baseline 가설 붕괴" → baseline 비활성. 전략 전체 중단 아님(LLM A/B는 §8.5, 본 계획 밖).

## 게이트 2순위 (바닥) — 비용 net 엣지
- net 수익 = gross overnight − 비용. 비용 = 매도 거래세 0.18%(코스닥 0.18%, [사용자 확정: 당해 세율]) + 수수료 0.0140%×2 + 슬리피지 밴드(§8.2).
- 슬리피지 밴드: 보수/낙관 두 값으로 동시 보고. 보수 = 편도 [사용자 확정, 예 0.30%], 낙관 = [예 0.10%].
- 합격: 보수 밴드에서도 net 평균 overnight 수익 > 0 AND net 기준 MDD ≤ [사용자 확정] AND 표본(체결일수) ≥ 250.

## 게이트 3순위 — 드리프트 민감도(잔여 look-ahead)
- t-1 선정 바스켓 vs (참고) t-종가 선정 바스켓 비교.
- θ1 = 1 − Jaccard(두 바스켓) (회전) ≤ 0.30.
- θ2 = |평균 net 수익(t-종가) − 평균 net 수익(t-1)| / |평균 net 수익(t-1)| ≤ 0.20.
- 초과 시: 엣지가 막판 드리프트에 의존하는 아티팩트로 간주(경고).

## 동결 파라미터 (config.py와 일치)
- 팩터 룩백: MA(5,20,60,120), 신고가 120, VolRatio 20, NearMA ±3%.
- Universe: 거래대금 상위 100, 안전 시총 하한 500억.
- 바스켓 K = 5. 팩터 가중치 = 등가중(초기). 시황배수 BULL 1.0/NEUTRAL 0.5/BEAR 0.2.
```

- [ ] **Step 2: Commit**

```bash
git add docs/superpowers/prereg/2026-06-04-phase1-gate-prereg.md && git commit -m "docs: phase1 gate pre-registration (frozen before data)"
```

---

## Task 2: 정규 데이터 스키마 — `data/schema.py`

라이브(KIS)/백테스트(pykrx)가 공유할 정규 레코드. 특히 **수급 카테고리(외국인/기관 세부)를 고정**(DF-2). 순수 — TDD.

**Files:**
- Create: `jongga/data/schema.py`
- Test: `tests/jongga/test_schema.py`

- [ ] **Step 1: 실패하는 테스트 작성**

```python
# tests/jongga/test_schema.py
from jongga.data.schema import normalize_supply, INSTITUTION_CATEGORIES


def test_normalize_supply_aggregates_institution_and_foreign():
    # pykrx 투자자별 순매수(원) 한 종목·하루치 raw dict (컬럼명은 통합검증서 확정)
    raw = {
        "기관합계": 1_000_000_000,
        "외국인합계": 2_000_000_000,
        "개인": -3_000_000_000,
        "연기금": 400_000_000,        # 기관 세부(참고 보존)
    }
    out = normalize_supply(raw, trade_value=10_000_000_000)
    assert out["inst_net"] == 1_000_000_000
    assert out["foreign_net"] == 2_000_000_000
    # 정규화: 순매수 / 거래대금
    assert abs(out["inst_net_ratio"] - 0.1) < 1e-9
    assert abs(out["foreign_net_ratio"] - 0.2) < 1e-9
    # 기관 세부 카테고리 목록이 스키마에 고정돼 있다
    assert "연기금" in INSTITUTION_CATEGORIES


def test_normalize_supply_zero_trade_value_safe():
    out = normalize_supply({"기관합계": 100, "외국인합계": 100}, trade_value=0)
    assert out["inst_net_ratio"] == 0.0
    assert out["foreign_net_ratio"] == 0.0
```

- [ ] **Step 2: 테스트 실패 확인**

Run: `.venv/bin/pytest tests/jongga/test_schema.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'jongga.data.schema'`

- [ ] **Step 3: 최소 구현**

```python
# jongga/data/schema.py
"""정규 데이터 스키마. pykrx/KIS가 같은 의미의 수치를 내도록 고정(DF-2)."""
from __future__ import annotations

# 기관 세부 카테고리(참고 보존용 — '기관합계'와 별도로 합 검증 가능)
INSTITUTION_CATEGORIES = ["금융투자", "보험", "투신", "사모", "은행",
                          "기타금융", "연기금", "기타법인"]


def normalize_supply(raw: dict, trade_value: int) -> dict:
    """투자자별 순매수(원) raw → 정규 수급 레코드.

    inst_net/foreign_net = 기관합계/외국인합계 순매수액,
    *_ratio = 순매수액 / 거래대금 (거래대금 0이면 0).
    """
    inst = int(raw.get("기관합계", 0))
    foreign = int(raw.get("외국인합계", 0))
    denom = trade_value if trade_value else 0
    return {
        "inst_net": inst,
        "foreign_net": foreign,
        "inst_net_ratio": (inst / denom) if denom else 0.0,
        "foreign_net_ratio": (foreign / denom) if denom else 0.0,
    }
```

- [ ] **Step 4: 테스트 통과 확인**

Run: `.venv/bin/pytest tests/jongga/test_schema.py -v`
Expected: PASS (2 passed)

- [ ] **Step 5: Commit**

```bash
git add jongga/data/schema.py tests/jongga/test_schema.py && git commit -m "feat: normalized supply schema (foreign/institution categories)"
```

---

## Task 3: 데이터 프로바이더 — `data/provider.py` + `data/pykrx_provider.py`

EOD 데이터를 정규 형태로 공급 + parquet 캐시. 캐시 로직은 TDD, pykrx 실호출은 통합 검증.

**Files:**
- Create: `jongga/data/provider.py`
- Create: `jongga/data/pykrx_provider.py`
- Test: `tests/jongga/test_provider.py`

- [ ] **Step 1: 인터페이스 작성 (테스트 불필요한 추상)**

```python
# jongga/data/provider.py
"""MarketDataProvider 추상 인터페이스. 백테스트=pykrx / (라이브=KIS, 별도 계획)."""
from __future__ import annotations
from typing import Protocol
import pandas as pd


class MarketDataProvider(Protocol):
    def ohlcv(self, start: str, end: str) -> pd.DataFrame:
        """일봉. MultiIndex (date, ticker), 컬럼: open/high/low/close/volume/value."""
        ...

    def market_cap(self, date: str) -> pd.DataFrame:
        """해당 date 시총. index=ticker, 컬럼: marketcap/shares."""
        ...

    def supply(self, start: str, end: str) -> pd.DataFrame:
        """투자자별 순매수. MultiIndex (date, ticker), 컬럼: inst_net/foreign_net."""
        ...

    def tickers(self, date: str) -> list[str]:
        """해당 date에 상장돼 있던 종목(PIT — 상폐 종목 포함, 생존편향 차단)."""
        ...
```

- [ ] **Step 2: 캐시 로직 실패하는 테스트 작성**

```python
# tests/jongga/test_provider.py
import pandas as pd
from jongga.data.pykrx_provider import cache_path, load_or_fetch


def test_cache_path_layout(tmp_path):
    p = cache_path(tmp_path, "ohlcv", "2026-06-01")
    assert p == tmp_path / "ohlcv" / "2026-06-01.parquet"


def test_load_or_fetch_uses_cache_when_present(tmp_path):
    calls = {"n": 0}
    df = pd.DataFrame({"close": [100, 200]}, index=["A", "B"])

    def fetch():
        calls["n"] += 1
        return df

    p = cache_path(tmp_path, "ohlcv", "2026-06-01")
    out1 = load_or_fetch(p, fetch)      # 첫 호출: fetch + 캐시 기록
    out2 = load_or_fetch(p, fetch)      # 두 번째: 캐시에서
    assert calls["n"] == 1
    assert list(out2["close"]) == [100, 200]
```

- [ ] **Step 3: 테스트 실패 확인**

Run: `.venv/bin/pytest tests/jongga/test_provider.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'jongga.data.pykrx_provider'`

- [ ] **Step 4: 최소 구현 (캐시 + pykrx 호출 골격)**

```python
# jongga/data/pykrx_provider.py
"""pykrx 기반 MarketDataProvider + parquet 캐시.

pykrx 함수 시그니처/컬럼명은 Step 6 통합검증에서 실제 출력으로 확정한다.
캐시 단위: 종류별·날짜별 1파일.
"""
from __future__ import annotations
from pathlib import Path
from typing import Callable
import pandas as pd


def cache_path(data_dir: Path, kind: str, key: str) -> Path:
    return Path(data_dir) / kind / f"{key}.parquet"


def load_or_fetch(path: Path, fetch: Callable[[], pd.DataFrame]) -> pd.DataFrame:
    if path.exists():
        return pd.read_parquet(path)
    df = fetch()
    path.parent.mkdir(parents=True, exist_ok=True)
    df.to_parquet(path)
    return df


class PykrxProvider:
    def __init__(self, data_dir: Path, market: str = "KOSDAQ"):
        self.data_dir = Path(data_dir)
        self.market = market

    def market_cap(self, date: str) -> pd.DataFrame:
        from pykrx import stock
        key = date.replace("-", "")

        def fetch():
            df = stock.get_market_cap(key, market=self.market)
            # 통합검증으로 컬럼명 확정: 한글('시가총액','상장주식수') → 정규화
            return df.rename(columns={"시가총액": "marketcap", "상장주식수": "shares"})

        return load_or_fetch(cache_path(self.data_dir, "market_cap", date), fetch)

    def tickers(self, date: str) -> list[str]:
        from pykrx import stock
        key = date.replace("-", "")
        return stock.get_market_ticker_list(key, market=self.market)
```

> ohlcv·supply 메서드는 Task 3 통합검증 후 동일 패턴으로 채운다(아래 Step 6에서 실제 컬럼 확정).

- [ ] **Step 5: 캐시 단위테스트 통과 확인**

Run: `.venv/bin/pytest tests/jongga/test_provider.py -v`
Expected: PASS (2 passed)

- [ ] **Step 6: 통합 검증 (pykrx 실호출 — 컬럼명·시그니처 확정)**

Run:
```bash
.venv/bin/python - <<'PY'
from pykrx import stock
# 1) 시총·상장주식수 컬럼명
mc = stock.get_market_cap("20260102", market="KOSDAQ")
print("market_cap cols:", list(mc.columns)[:6])
# 2) 일봉 전종목(특정일)
oh = stock.get_market_ohlcv("20260102", market="KOSDAQ")
print("ohlcv cols:", list(oh.columns))
# 3) 투자자별 순매수(종목·기간)
sp = stock.get_market_net_purchases_of_equities("20260102", "20260102", "KOSDAQ", "기관합계")
print("supply head:", sp.head(2).to_dict())
# 4) PIT 종목 목록(상폐 포함 여부 확인 — 과거일자)
tk = stock.get_market_ticker_list("20200102", market="KOSDAQ")
print("tickers 2020:", len(tk))
PY
```
Expected: 각 컬럼명/형태 출력. **출력에 맞춰 `pykrx_provider.py`의 rename 매핑과 `ohlcv()/supply()` 구현을 확정**하고, `normalize_supply`(Task 2)에 실제 컬럼명을 연결. (네트워크 필요 — 실패 시 pykrx 버전/인터넷 확인.)

- [ ] **Step 7: ohlcv()/supply() 구현 완성 + DF-2 골든 테스트**

통합검증 결과로 `ohlcv()`·`supply()`를 완성하고, 수급 정규화가 실제 pykrx 출력에서 동작함을 고정하는 골든 테스트를 `tests/jongga/test_provider.py`에 추가(소량 실데이터 또는 저장한 fixture로). Commit:

```bash
git add jongga/data/provider.py jongga/data/pykrx_provider.py tests/jongga/test_provider.py && git commit -m "feat: pykrx data provider with parquet cache + supply golden test"
```

---

## Task 4: 거래일 캘린더 — `calendar.py`

영업일(거래일) 시퀀스. t-1/t+1 시점 계산의 토대. pykrx 영업일 사용, 순수 부분 TDD.

**Files:**
- Create: `jongga/calendar.py`
- Test: `tests/jongga/test_calendar.py`

- [ ] **Step 1: 실패하는 테스트 작성**

```python
# tests/jongga/test_calendar.py
from jongga.calendar import prev_trading_day, next_trading_day


def test_prev_and_next_trading_day():
    days = ["2026-06-01", "2026-06-02", "2026-06-03"]
    assert prev_trading_day("2026-06-03", days) == "2026-06-02"
    assert next_trading_day("2026-06-02", days) == "2026-06-03"
    assert prev_trading_day("2026-06-01", days) is None
    assert next_trading_day("2026-06-03", days) is None
```

- [ ] **Step 2: 테스트 실패 확인**

Run: `.venv/bin/pytest tests/jongga/test_calendar.py -v`
Expected: FAIL — `ModuleNotFoundError`

- [ ] **Step 3: 최소 구현**

```python
# jongga/calendar.py
"""거래일 유틸. 거래일 리스트는 pykrx ohlcv 인덱스에서 도출(실데이터=실제 영업일)."""
from __future__ import annotations


def prev_trading_day(date: str, trading_days: list[str]) -> str | None:
    i = trading_days.index(date)
    return trading_days[i - 1] if i > 0 else None


def next_trading_day(date: str, trading_days: list[str]) -> str | None:
    i = trading_days.index(date)
    return trading_days[i + 1] if i + 1 < len(trading_days) else None
```

- [ ] **Step 4: 테스트 통과 확인**

Run: `.venv/bin/pytest tests/jongga/test_calendar.py -v`
Expected: PASS (1 passed)

- [ ] **Step 5: Commit**

```bash
git add jongga/calendar.py tests/jongga/test_calendar.py && git commit -m "feat: trading-day calendar helpers"
```

---

## Task 5: 차트 팩터 — `factors/chart.py`

§5.2 차트 팩터를 t-1 종가 시리즈에서 계산하는 순수함수. **누수 가드: 입력은 의사결정일 이전 시리즈만.** TDD 핵심.

**Files:**
- Create: `jongga/factors/chart.py`
- Test: `tests/jongga/test_chart_factors.py`

- [ ] **Step 1: 실패하는 테스트 작성**

```python
# tests/jongga/test_chart_factors.py
import numpy as np
import pandas as pd
from jongga.factors.chart import spread, alignment, proximity, days_since_high, vol_ratio


def test_spread_normalized_by_long_ma():
    prices = pd.Series([10.0] * 4 + [20.0])     # 최근 급등
    s = spread(prices, short=2, long=4)
    assert s > 0                                 # 단기선이 위

def test_alignment_perfect_uptrend_is_one():
    prices = pd.Series(np.arange(1, 200, dtype=float))  # 단조 증가 → 정배열
    assert alignment(prices, (5, 20, 60, 120)) == 1.0

def test_alignment_perfect_downtrend_is_zero():
    prices = pd.Series(np.arange(200, 1, -1, dtype=float))  # 단조 감소 → 역배열
    assert alignment(prices, (5, 20, 60, 120)) == 0.0

def test_proximity_one_at_new_high():
    prices = pd.Series([10, 12, 11, 15.0])       # 마지막이 최고
    assert abs(proximity(prices, n=4) - 1.0) < 1e-9

def test_days_since_high_zero_at_new_high():
    prices = pd.Series([10, 12, 11, 15.0])
    assert days_since_high(prices, n=4) == 0

def test_vol_ratio_up_volume_dominates():
    # 양봉(상승)일 거래량 큼 → >1
    closes = pd.Series([10, 11, 10.5, 12.0])     # +,-,+
    vols = pd.Series([100, 10, 100, 10.0])
    assert vol_ratio(closes, vols) > 1.0
```

- [ ] **Step 2: 테스트 실패 확인**

Run: `.venv/bin/pytest tests/jongga/test_chart_factors.py -v`
Expected: FAIL — `ModuleNotFoundError`

- [ ] **Step 3: 최소 구현**

```python
# jongga/factors/chart.py
"""t-1 안전 차트 팩터(순수). 입력 prices는 의사결정일 *이전*까지의 종가 시리즈."""
from __future__ import annotations
import numpy as np
import pandas as pd


def _ma(prices: pd.Series, w: int) -> float:
    return float(prices.tail(w).mean())


def spread(prices: pd.Series, short: int, long: int) -> float:
    ml = _ma(prices, long)
    return (_ma(prices, short) - ml) / ml if ml else 0.0


def alignment(prices: pd.Series, windows: tuple[int, ...]) -> float:
    mas = [_ma(prices, w) for w in windows]
    pairs = list(zip(mas, mas[1:]))
    ok = sum(1 for a, b in pairs if a > b)        # 단기 > 장기
    return ok / len(pairs)


def proximity(prices: pd.Series, n: int) -> float:
    window = prices.tail(n)
    mx = float(window.max())
    return float(window.iloc[-1]) / mx if mx else 0.0


def days_since_high(prices: pd.Series, n: int) -> int:
    window = prices.tail(n).reset_index(drop=True)
    return int(len(window) - 1 - window.idxmax())


def vol_ratio(closes: pd.Series, vols: pd.Series) -> float:
    diff = closes.diff()
    up = vols[diff > 0].mean()
    down = vols[diff < 0].mean()
    if not down or np.isnan(down):
        return float("inf") if up and not np.isnan(up) else 1.0
    return float(up / down)
```

- [ ] **Step 4: 테스트 통과 확인**

Run: `.venv/bin/pytest tests/jongga/test_chart_factors.py -v`
Expected: PASS (6 passed)

- [ ] **Step 5: Commit**

```bash
git add jongga/factors/chart.py tests/jongga/test_chart_factors.py && git commit -m "feat: t-1 chart factors (spread/alignment/proximity/days-since-high/vol-ratio)"
```

---

## Task 6: 수급·거래대금 팩터 — `factors/flow.py`, `factors/value.py`

§5.2 ①② 팩터. t-1 확정 + 최근 5일 누적 수급, 거래대금 상대순위. 순수 TDD.

**Files:**
- Create: `jongga/factors/flow.py`, `jongga/factors/value.py`
- Test: `tests/jongga/test_flow_value_factors.py`

- [ ] **Step 1: 실패하는 테스트 작성**

```python
# tests/jongga/test_flow_value_factors.py
import pandas as pd
from jongga.factors.flow import supply_factor
from jongga.factors.value import value_rank


def test_supply_factor_5day_cumulative_ratio():
    # 최근 5일 외국인+기관 순매수 누적 / 같은 기간 거래대금 누적
    df = pd.DataFrame({
        "inst_net": [1, 1, 1, 1, 1],
        "foreign_net": [1, 1, 1, 1, 1],
        "value": [10, 10, 10, 10, 10],
    })
    # (5*1 + 5*1) / (5*10) = 10/50 = 0.2
    assert abs(supply_factor(df, lookback=5) - 0.2) < 1e-9


def test_value_rank_is_percentile_0_to_1():
    values = pd.Series({"A": 10, "B": 20, "C": 30, "D": 40})
    r = value_rank(values)
    assert r["D"] == 1.0          # 최고 거래대금 → 1.0
    assert 0.0 <= r["A"] < r["B"] < r["C"] < r["D"]
```

- [ ] **Step 2: 테스트 실패 확인**

Run: `.venv/bin/pytest tests/jongga/test_flow_value_factors.py -v`
Expected: FAIL — `ModuleNotFoundError`

- [ ] **Step 3: 최소 구현**

```python
# jongga/factors/flow.py
"""t-1 수급 팩터(순수)."""
from __future__ import annotations
import pandas as pd


def supply_factor(recent: pd.DataFrame, lookback: int = 5) -> float:
    """최근 lookback일 (외국인+기관) 순매수 누적 / 거래대금 누적."""
    w = recent.tail(lookback)
    net = (w["inst_net"] + w["foreign_net"]).sum()
    denom = w["value"].sum()
    return float(net / denom) if denom else 0.0
```

```python
# jongga/factors/value.py
"""t-1 거래대금 상대순위(0~1, 순수)."""
from __future__ import annotations
import pandas as pd


def value_rank(values: pd.Series) -> pd.Series:
    return values.rank(pct=True)
```

- [ ] **Step 4: 테스트 통과 확인**

Run: `.venv/bin/pytest tests/jongga/test_flow_value_factors.py -v`
Expected: PASS (2 passed)

- [ ] **Step 5: Commit**

```bash
git add jongga/factors/flow.py jongga/factors/value.py tests/jongga/test_flow_value_factors.py && git commit -m "feat: t-1 supply & value-rank factors"
```

---

## Task 7: Universe 구성 — `universe.py`

§5.1 t-1 유니버스: 거래대금 상위 K ∩ 시총하한 ∩ (PIT 상장종목). PIT 멤버십으로 생존편향 차단(BV-6). 순수 TDD + PIT 골든.

**Files:**
- Create: `jongga/universe.py`
- Test: `tests/jongga/test_universe.py`

- [ ] **Step 1: 실패하는 테스트 작성**

```python
# tests/jongga/test_universe.py
import pandas as pd
from jongga.universe import build_universe


def test_universe_top_k_value_and_mincap_and_pit():
    values = pd.Series({"A": 100, "B": 90, "C": 80, "D": 5})   # 거래대금
    caps = pd.Series({"A": 1e11, "B": 1e9, "C": 1e11, "D": 1e11})  # B는 시총 미달
    listed = {"A", "C", "D"}                                    # PIT: B는 상폐(미상장)
    uni = build_universe(values, caps, listed, top_k=3, min_cap=5e10)
    # 거래대금 상위3=A,B,C 중 B(시총미달)·(PIT 미상장)도 탈락 → A,C. D는 top3 밖.
    assert uni == ["A", "C"]
```

- [ ] **Step 2: 테스트 실패 확인**

Run: `.venv/bin/pytest tests/jongga/test_universe.py -v`
Expected: FAIL — `ModuleNotFoundError`

- [ ] **Step 3: 최소 구현**

```python
# jongga/universe.py
"""t-1 유니버스 구성(거래대금 상위 K ∩ 시총하한 ∩ PIT 상장)."""
from __future__ import annotations
import pandas as pd


def build_universe(values: pd.Series, caps: pd.Series, listed: set[str],
                   top_k: int, min_cap: float) -> list[str]:
    ranked = values.sort_values(ascending=False).head(top_k)
    out = [t for t in ranked.index
           if t in listed and float(caps.get(t, 0)) >= min_cap]
    return out
```

- [ ] **Step 4: 테스트 통과 확인**

Run: `.venv/bin/pytest tests/jongga/test_universe.py -v`
Expected: PASS (1 passed)

- [ ] **Step 5: PIT 골든 검증 (생존편향 — 통합)**

Run:
```bash
.venv/bin/python - <<'PY'
from pykrx import stock
# 과거 특정일 상장종목에 '현재 상폐된 종목'이 포함되는지(=PIT 진짜) 확인
old = set(stock.get_market_ticker_list("20190102", market="KOSDAQ"))
now = set(stock.get_market_ticker_list("20260102", market="KOSDAQ"))
print("2019 listed:", len(old), "| 2019-only(이후 상폐 추정):", len(old - now))
PY
```
Expected: `2019-only` > 0 (과거일자에 그 시점 상장종목이 잡혀야 PIT·생존편향 차단 성립). **0이면 pykrx가 PIT를 안 주는 것 → 사전등록 BV-6 한계로 기록하고 대안(상폐목록 별도 수집) 검토.**

- [ ] **Step 6: Commit**

```bash
git add jongga/universe.py tests/jongga/test_universe.py && git commit -m "feat: t-1 PIT universe (top-value, min-cap, listed-membership)"
```

---

## Task 8: 시황등급 — `regime.py`

§6 시황배수. t-1 코스닥 거래대금 → 등급/배수. 순수 TDD.

**Files:**
- Create: `jongga/regime.py`
- Test: `tests/jongga/test_regime.py`

- [ ] **Step 1: 실패하는 테스트 작성**

```python
# tests/jongga/test_regime.py
from jongga.regime import regime_multiplier


def test_regime_thresholds_trillion_won():
    # 코스닥 일거래대금(원). 사전등록: BULL≥12조, BEAR<8조, HALT<5조
    assert regime_multiplier(13e12) == ("BULL", 1.0)
    assert regime_multiplier(10e12) == ("NEUTRAL", 0.5)
    assert regime_multiplier(7e12) == ("BEAR", 0.2)
    assert regime_multiplier(4e12) == ("HALT", 0.0)
```

- [ ] **Step 2: 테스트 실패 확인**

Run: `.venv/bin/pytest tests/jongga/test_regime.py -v`
Expected: FAIL — `ModuleNotFoundError`

- [ ] **Step 3: 최소 구현**

```python
# jongga/regime.py
"""시황등급/비중배수 — t-1 코스닥 거래대금 기준(사전등록 임계치)."""
from __future__ import annotations

BULL, NEUTRAL, BEAR, HALT = 12e12, 8e12, 5e12, 0.0  # 경계(원)


def regime_multiplier(market_value: float) -> tuple[str, float]:
    if market_value >= BULL:
        return ("BULL", 1.0)
    if market_value >= NEUTRAL:
        return ("NEUTRAL", 0.5)
    if market_value >= BEAR:
        return ("BEAR", 0.2)
    return ("HALT", 0.0)
```

- [ ] **Step 4: 테스트 통과 확인**

Run: `.venv/bin/pytest tests/jongga/test_regime.py -v`
Expected: PASS (1 passed)

- [ ] **Step 5: Commit**

```bash
git add jongga/regime.py tests/jongga/test_regime.py && git commit -m "feat: regime multiplier from KOSDAQ trading value"
```

---

## Task 9: 룰 baseline Selector — `selector.py`

§5.5 baseline: 팩터 가중합 상위 K, DaysSinceHigh 패널티(소진 모멘텀 배제), conviction=정규화 팩터점수. 순수 TDD.

**Files:**
- Create: `jongga/selector.py`
- Test: `tests/jongga/test_selector.py`

- [ ] **Step 1: 실패하는 테스트 작성**

```python
# tests/jongga/test_selector.py
import pandas as pd
from jongga.selector import score_and_select


def test_score_select_topk_with_normalized_conviction():
    # 팩터 테이블(이미 0~1 정규화된 팩터들) + days_since_high(패널티)
    feats = pd.DataFrame({
        "spread": [0.9, 0.1, 0.5],
        "supply": [0.8, 0.2, 0.5],
        "days_since_high": [0, 30, 5],   # 작을수록 좋음(패널티)
    }, index=["A", "B", "C"])
    weights = {"spread": 1.0, "supply": 1.0}
    picks = score_and_select(feats, weights, dsh_penalty=0.01, k=2)
    assert [p[0] for p in picks] == ["A", "C"]        # A 최고
    assert 0.0 <= picks[1][1] <= picks[0][1] <= 1.0   # conviction 0~1, 정렬
```

- [ ] **Step 2: 테스트 실패 확인**

Run: `.venv/bin/pytest tests/jongga/test_selector.py -v`
Expected: FAIL — `ModuleNotFoundError`

- [ ] **Step 3: 최소 구현**

```python
# jongga/selector.py
"""룰 baseline selector(§5.5). 팩터 가중합 − DaysSinceHigh 패널티 → 상위 K."""
from __future__ import annotations
import pandas as pd


def score_and_select(feats: pd.DataFrame, weights: dict[str, float],
                     dsh_penalty: float, k: int) -> list[tuple[str, float]]:
    score = sum(feats[col] * w for col, w in weights.items())
    score = score - dsh_penalty * feats["days_since_high"]
    # conviction = min-max 정규화(0~1)
    lo, hi = score.min(), score.max()
    conv = (score - lo) / (hi - lo) if hi > lo else score * 0.0
    top = conv.sort_values(ascending=False).head(k)
    return [(t, float(c)) for t, c in top.items()]
```

- [ ] **Step 4: 테스트 통과 확인**

Run: `.venv/bin/pytest tests/jongga/test_selector.py -v`
Expected: PASS (1 passed)

- [ ] **Step 5: Commit**

```bash
git add jongga/selector.py tests/jongga/test_selector.py && git commit -m "feat: rule baseline selector (factor sum - days-since-high penalty)"
```

---

## Task 10: Sizing — `sizing.py`

§6 정량가중 sizing + caps(EOD proxy). conviction 미사용(#15). 순수 TDD.

**Files:**
- Create: `jongga/sizing.py`
- Test: `tests/jongga/test_sizing.py`

- [ ] **Step 1: 실패하는 테스트 작성**

```python
# tests/jongga/test_sizing.py
from jongga.sizing import size_basket


def test_size_basket_regime_and_caps():
    picks = [("A", 0.9), ("B", 0.1)]          # conviction은 사이징 미사용
    # 자본 1000, BULL 배수 1.0, 등가중 → 각 500, per-symbol cap 400 적용
    out = size_basket(picks, capital=1000, regime_mult=1.0,
                      per_symbol_cap_frac=0.4, value_cap={"A": 1e9, "B": 1e9})
    assert out["A"] == 400 and out["B"] == 400   # cap에 걸려 각 400

def test_size_basket_value_cap_limits_notional():
    picks = [("A", 0.5)]
    out = size_basket(picks, capital=1_000_000, regime_mult=1.0,
                      per_symbol_cap_frac=1.0, value_cap={"A": 300_000})
    assert out["A"] == 300_000                   # 거래대금 proxy cap
```

- [ ] **Step 2: 테스트 실패 확인**

Run: `.venv/bin/pytest tests/jongga/test_sizing.py -v`
Expected: FAIL — `ModuleNotFoundError`

- [ ] **Step 3: 최소 구현**

```python
# jongga/sizing.py
"""정량가중 sizing(#15). conviction 미사용. 등가중 × 시황배수, caps 적용."""
from __future__ import annotations


def size_basket(picks: list[tuple[str, float]], capital: float, regime_mult: float,
                per_symbol_cap_frac: float, value_cap: dict[str, float]) -> dict[str, float]:
    if not picks or regime_mult == 0:
        return {}
    budget = capital * regime_mult
    each = budget / len(picks)                       # 등가중
    cap_abs = capital * per_symbol_cap_frac
    out = {}
    for sym, _conv in picks:
        notional = min(each, cap_abs, value_cap.get(sym, float("inf")))
        out[sym] = notional
    return out
```

- [ ] **Step 4: 테스트 통과 확인**

Run: `.venv/bin/pytest tests/jongga/test_sizing.py -v`
Expected: PASS (2 passed)

- [ ] **Step 5: Commit**

```bash
git add jongga/sizing.py tests/jongga/test_sizing.py && git commit -m "feat: deterministic equal-weight sizing with regime & caps"
```

---

## Task 11: 체결모델 — `backtest/fill_model.py`

§8.2 슬리피지 밴드(매수·매도 대칭) + 강제다일(시초 하한가/거래정지 청산불가) 분기. 순수 TDD.

**Files:**
- Create: `jongga/backtest/fill_model.py`
- Test: `tests/jongga/test_fill_model.py`

- [ ] **Step 1: 실패하는 테스트 작성**

```python
# tests/jongga/test_fill_model.py
from jongga.backtest.fill_model import buy_fill, sell_fill, is_sellable


def test_buy_fill_adds_slippage():
    # 매수는 종가 × (1 + 편도슬리피지)
    assert abs(buy_fill(1000, slippage=0.003) - 1003.0) < 1e-9

def test_sell_fill_subtracts_slippage():
    assert abs(sell_fill(1000, slippage=0.003) - 997.0) < 1e-9

def test_is_sellable_false_when_limit_down_or_halt():
    # 시초가 == 하한가(전일 종가 -30%)면 매도 불가
    assert is_sellable(open_px=700, prev_close=1000, halted=False) is False
    assert is_sellable(open_px=950, prev_close=1000, halted=False) is True
    assert is_sellable(open_px=950, prev_close=1000, halted=True) is False
```

- [ ] **Step 2: 테스트 실패 확인**

Run: `.venv/bin/pytest tests/jongga/test_fill_model.py -v`
Expected: FAIL — `ModuleNotFoundError`

- [ ] **Step 3: 최소 구현**

```python
# jongga/backtest/fill_model.py
"""체결모델: 슬리피지 밴드(대칭) + 강제다일 분기(§8.2)."""
from __future__ import annotations

LIMIT = 0.30   # 가격제한폭 ±30%


def buy_fill(close: float, slippage: float) -> float:
    return close * (1.0 + slippage)


def sell_fill(open_px: float, slippage: float) -> float:
    return open_px * (1.0 - slippage)


def is_sellable(open_px: float, prev_close: float, halted: bool) -> bool:
    if halted:
        return False
    lower_limit = round(prev_close * (1.0 - LIMIT))
    return open_px > lower_limit            # 시초가 하한가면 매도 불가
```

- [ ] **Step 4: 테스트 통과 확인**

Run: `.venv/bin/pytest tests/jongga/test_fill_model.py -v`
Expected: PASS (3 passed)

- [ ] **Step 5: Commit**

```bash
git add jongga/backtest/fill_model.py tests/jongga/test_fill_model.py && git commit -m "feat: fill model with symmetric slippage band + forced-hold branch"
```

---

## Task 12: 메트릭 + 백테스트 엔진 — `backtest/metrics.py`, `backtest/engine.py`

§8.2 일별 종가매수→익일시초매도 시뮬 + net 메트릭. **누수 불변식 강제 테스트 포함.**

**Files:**
- Create: `jongga/backtest/metrics.py`, `jongga/backtest/engine.py`
- Test: `tests/jongga/test_metrics.py`, `tests/jongga/test_engine.py`

- [ ] **Step 1: 메트릭 실패하는 테스트 작성**

```python
# tests/jongga/test_metrics.py
from jongga.backtest.metrics import summarize


def test_summarize_net_and_winrate_and_mdd():
    # 일별 net 수익률(소수)
    rets = [0.02, -0.01, 0.03, -0.04]
    m = summarize(rets)
    assert abs(m["mean"] - 0.0) < 0.011
    assert m["win_rate"] == 0.5
    assert m["n"] == 4
    assert m["mdd"] <= 0.0          # MDD는 음수(낙폭)
```

- [ ] **Step 2: 메트릭 실패 확인**

Run: `.venv/bin/pytest tests/jongga/test_metrics.py -v`
Expected: FAIL — `ModuleNotFoundError`

- [ ] **Step 3: 메트릭 구현**

```python
# jongga/backtest/metrics.py
"""백테스트 net 메트릭."""
from __future__ import annotations
import numpy as np


def summarize(daily_returns: list[float]) -> dict:
    r = np.array(daily_returns, dtype=float)
    if len(r) == 0:
        return {"n": 0, "mean": 0.0, "win_rate": 0.0, "mdd": 0.0}
    equity = np.cumprod(1 + r)
    peak = np.maximum.accumulate(equity)
    mdd = float((equity / peak - 1).min())
    return {
        "n": int(len(r)),
        "mean": float(r.mean()),
        "win_rate": float((r > 0).mean()),
        "mdd": mdd,
    }
```

- [ ] **Step 4: 메트릭 통과 확인**

Run: `.venv/bin/pytest tests/jongga/test_metrics.py -v`
Expected: PASS (1 passed)

- [ ] **Step 5: 엔진 실패하는 테스트 작성 (누수 불변식 + 1박 수익)**

```python
# tests/jongga/test_engine.py
import pandas as pd
from jongga.backtest.engine import run_day


def test_run_day_overnight_return_net_of_costs():
    # 종목 A를 t 종가 1000에 사서 t+1 시초 1100에 판다
    sized = {"A": 100_000}                       # notional
    close_t = {"A": 1000.0}
    open_t1 = {"A": 1100.0}
    prev_close_t = {"A": 1000.0}                 # t-1 종가(하한가 판정용 = t 시초 아님; 여기선 단순화)
    res = run_day(sized, close_t, open_t1, prev_close_for_limit={"A": 1000.0},
                  halted=set(), slippage=0.0, sell_tax=0.0, fee=0.0)
    # gross overnight = (1100-1000)/1000 = +10%
    assert abs(res["A"]["ret"] - 0.10) < 1e-9

def test_run_day_unsellable_marks_forced_hold():
    sized = {"A": 100_000}
    res = run_day(sized, {"A": 1000.0}, {"A": 700.0},
                  prev_close_for_limit={"A": 1000.0}, halted=set(),
                  slippage=0.0, sell_tax=0.0, fee=0.0)
    # 시초 700 == 하한가(1000*0.7) → 매도불가 → forced_hold 플래그
    assert res["A"]["forced_hold"] is True
```

- [ ] **Step 6: 엔진 실패 확인**

Run: `.venv/bin/pytest tests/jongga/test_engine.py -v`
Expected: FAIL — `ModuleNotFoundError`

- [ ] **Step 7: 엔진 최소 구현**

```python
# jongga/backtest/engine.py
"""백테스트 엔진: 하루치 종가매수→익일시초매도 청산(§8.2).

run_day는 한 거래일 d의 바스켓을 d 종가 매수, d+1 시초 매도한 종목별 결과를 낸다.
선정/사이징은 호출 측(run_backtest)이 t-1 입력으로 이미 결정해 넘긴다(누수 차단).
"""
from __future__ import annotations
from jongga.backtest.fill_model import buy_fill, sell_fill, is_sellable


def run_day(sized: dict[str, float], close_t: dict[str, float],
            open_t1: dict[str, float], prev_close_for_limit: dict[str, float],
            halted: set[str], slippage: float, sell_tax: float, fee: float) -> dict:
    out = {}
    for sym, _notional in sized.items():
        buy = buy_fill(close_t[sym], slippage)
        op = open_t1.get(sym)
        if op is None or not is_sellable(op, prev_close_for_limit[sym], sym in halted):
            out[sym] = {"ret": 0.0, "forced_hold": True}
            continue
        sell = sell_fill(op, slippage)
        gross = (sell - buy) / buy
        net = gross - sell_tax - 2 * fee
        out[sym] = {"ret": net, "forced_hold": False}
    return out
```

- [ ] **Step 8: 엔진 통과 확인**

Run: `.venv/bin/pytest tests/jongga/test_engine.py -v`
Expected: PASS (2 passed)

- [ ] **Step 9: Commit**

```bash
git add jongga/backtest/metrics.py jongga/backtest/engine.py tests/jongga/test_metrics.py tests/jongga/test_engine.py && git commit -m "feat: backtest engine (overnight close->open) + net metrics"
```

---

## Task 13: IC 게이트 — `gate/ic.py`

§8.4-1 1순위(load-bearing). 팩터별 close→open Spearman IC + BH 보정 + 부호안정성. 순수 TDD.

**Files:**
- Create: `jongga/gate/ic.py`
- Test: `tests/jongga/test_ic.py`

- [ ] **Step 1: 실패하는 테스트 작성**

```python
# tests/jongga/test_ic.py
import numpy as np
import pandas as pd
from jongga.gate.ic import daily_ic, bh_significant


def test_daily_ic_perfect_rank_is_one():
    feat = pd.Series([1, 2, 3, 4.0], index=list("ABCD"))
    fwd = pd.Series([10, 20, 30, 40.0], index=list("ABCD"))   # 완전 단조
    assert abs(daily_ic(feat, fwd) - 1.0) < 1e-9

def test_bh_significant_counts_corrected():
    # p값 4개 중 BH(q=0.10)로 유의한 개수
    pvals = {"f1": 0.001, "f2": 0.04, "f3": 0.2, "f4": 0.9}
    sig = bh_significant(pvals, q=0.10)
    assert "f1" in sig and "f4" not in sig
```

- [ ] **Step 2: 테스트 실패 확인**

Run: `.venv/bin/pytest tests/jongga/test_ic.py -v`
Expected: FAIL — `ModuleNotFoundError`

- [ ] **Step 3: 최소 구현**

```python
# jongga/gate/ic.py
"""팩터의 1박 갭 IC 게이트(§8.4-1). Spearman IC + BH 보정 + 부호안정성."""
from __future__ import annotations
import numpy as np
import pandas as pd
from scipy import stats


def daily_ic(feature: pd.Series, fwd_return: pd.Series) -> float:
    """단면 Spearman rank IC (한 거래일)."""
    common = feature.dropna().index.intersection(fwd_return.dropna().index)
    if len(common) < 3:
        return np.nan
    rho, _ = stats.spearmanr(feature[common], fwd_return[common])
    return float(rho)


def bh_significant(pvals: dict[str, float], q: float = 0.10) -> set[str]:
    """Benjamini-Hochberg FDR로 유의한 팩터 집합."""
    items = sorted(pvals.items(), key=lambda kv: kv[1])
    m = len(items)
    sig: set[str] = set()
    for i, (name, p) in enumerate(items, start=1):
        if p <= (i / m) * q:
            sig = {n for n, _ in items[:i]}
    return sig


def ic_series_stats(ics: list[float]) -> tuple[float, float]:
    """일별 IC 시계열 → (평균 IC, 양측 p값[H0: 평균=0])."""
    a = np.array([x for x in ics if not np.isnan(x)])
    if len(a) < 2:
        return (float("nan"), 1.0)
    t, p = stats.ttest_1samp(a, 0.0)
    return (float(a.mean()), float(p))
```

- [ ] **Step 4: 테스트 통과 확인**

Run: `.venv/bin/pytest tests/jongga/test_ic.py -v`
Expected: PASS (2 passed)

- [ ] **Step 5: Commit**

```bash
git add jongga/gate/ic.py tests/jongga/test_ic.py && git commit -m "feat: IC gate (spearman IC + BH correction + series stats)"
```

---

## Task 14: 드리프트 민감도 게이트 — `gate/drift.py`

§8.4-3. t-1 선정 vs (참고) t-종가 선정의 회전(θ1)·수익델타(θ2). 순수 TDD.

**Files:**
- Create: `jongga/gate/drift.py`
- Test: `tests/jongga/test_drift.py`

- [ ] **Step 1: 실패하는 테스트 작성**

```python
# tests/jongga/test_drift.py
from jongga.gate.drift import turnover, return_delta


def test_turnover_jaccard_distance():
    # 교집합 {B,C}=2, 합집합 {A,B,C,D}=4 → 회전 = 1 - Jaccard = 1 - 2/4 = 0.5
    assert abs(turnover(["A", "B", "C"], ["B", "C", "D"]) - (1 - 2/4)) < 1e-9

def test_return_delta_relative():
    assert abs(return_delta(t1_mean=0.01, tclose_mean=0.012) - 0.2) < 1e-9
```

- [ ] **Step 2: 테스트 실패 확인**

Run: `.venv/bin/pytest tests/jongga/test_drift.py -v`
Expected: FAIL — `ModuleNotFoundError`

- [ ] **Step 3: 최소 구현**

```python
# jongga/gate/drift.py
"""드리프트 민감도(§8.4-3): t-1 선정 vs t-종가 선정."""
from __future__ import annotations


def turnover(basket_t1: list[str], basket_tclose: list[str]) -> float:
    a, b = set(basket_t1), set(basket_tclose)
    union = a | b
    if not union:
        return 0.0
    return 1.0 - len(a & b) / len(union)        # 1 - Jaccard


def return_delta(t1_mean: float, tclose_mean: float) -> float:
    if t1_mean == 0:
        return float("inf") if tclose_mean else 0.0
    return abs(tclose_mean - t1_mean) / abs(t1_mean)
```

- [ ] **Step 4: 테스트 통과 확인**

Run: `.venv/bin/pytest tests/jongga/test_drift.py -v`
Expected: PASS (2 passed)

- [ ] **Step 5: Commit**

```bash
git add jongga/gate/drift.py tests/jongga/test_drift.py && git commit -m "feat: drift sensitivity gate (turnover + return delta)"
```

---

## Task 15: 게이트 리포트 + 엔트리 — `gate/report.py`, `run_backtest.py`

전 컴포넌트를 묶어 walk-forward로 백테스트하고 §8.4 사전등록 합격선 판정을 출력. 통합.

**Files:**
- Create: `jongga/gate/report.py`
- Create: `jongga/run_backtest.py`
- Test: `tests/jongga/test_report.py`

- [ ] **Step 1: 판정 로직 실패하는 테스트 작성**

```python
# tests/jongga/test_report.py
from jongga.gate.report import verdict


def test_verdict_pass_when_criteria_met():
    v = verdict(
        n_sig_factors=2, sign_stable=True,            # 1순위
        net_mean_conservative=0.004, mdd=-0.15, n=300,  # 2순위
        theta1=0.2, theta2=0.1,                        # 3순위
        thresholds={"m": 2, "mdd_limit": -0.25, "min_n": 250,
                    "theta1_max": 0.30, "theta2_max": 0.20},
    )
    assert v["gate1_pass"] is True
    assert v["gate2_pass"] is True
    assert v["gate3_warn"] is False
    assert v["overall"] == "PASS"


def test_verdict_gate1_fail_is_baseline_collapse():
    v = verdict(n_sig_factors=0, sign_stable=False,
               net_mean_conservative=0.01, mdd=-0.1, n=300,
               theta1=0.1, theta2=0.1,
               thresholds={"m": 2, "mdd_limit": -0.25, "min_n": 250,
                           "theta1_max": 0.30, "theta2_max": 0.20})
    assert v["gate1_pass"] is False
    assert v["overall"] == "BASELINE_COLLAPSE"   # 전략 전체 중단 아님(§8.5/C3)
```

- [ ] **Step 2: 테스트 실패 확인**

Run: `.venv/bin/pytest tests/jongga/test_report.py -v`
Expected: FAIL — `ModuleNotFoundError`

- [ ] **Step 3: 판정 로직 구현**

```python
# jongga/gate/report.py
"""§8.4 사전등록 합격선 판정(C3: 1순위 실패=baseline 붕괴, 전략 전체 중단 아님)."""
from __future__ import annotations


def verdict(n_sig_factors: int, sign_stable: bool,
            net_mean_conservative: float, mdd: float, n: int,
            theta1: float, theta2: float, thresholds: dict) -> dict:
    g1 = (n_sig_factors >= thresholds["m"]) and sign_stable
    g2 = (net_mean_conservative > 0) and (mdd >= thresholds["mdd_limit"]) \
        and (n >= thresholds["min_n"])
    g3_warn = (theta1 > thresholds["theta1_max"]) or (theta2 > thresholds["theta2_max"])
    if not g1:
        overall = "BASELINE_COLLAPSE"        # §8.5/C3: LLM A/B는 별도(이 계획 밖)
    elif g1 and g2:
        overall = "PASS"
    else:
        overall = "FAIL"
    return {"gate1_pass": g1, "gate2_pass": g2, "gate3_warn": g3_warn, "overall": overall}
```

- [ ] **Step 4: 판정 통과 확인**

Run: `.venv/bin/pytest tests/jongga/test_report.py -v`
Expected: PASS (2 passed)

- [ ] **Step 5: run_backtest 엔트리 작성 (통합 — 전 컴포넌트 결선)**

```python
# jongga/run_backtest.py
"""엔트리: pykrx 데이터 → t-1 팩터 → 룰 baseline → 일별 백테스트 → §8.4 게이트.

흐름(누수 차단):
  각 거래일 d에 대해
    - universe/factors/regime/supply = d의 *직전 거래일까지* 데이터로 계산
    - 선정·사이징 = 위 t-1 입력으로
    - 체결 = d 종가 매수, d+1 시초 매도(run_day)
  팩터별 (d의 t-1 팩터값) vs (d→d+1 overnight 수익)으로 일별 IC 수집 → 게이트.
walk-forward: holdout_start 이전만 탐색/평가, 이후는 최종 1회.
"""
from __future__ import annotations
import logging
from jongga.config import Config
from jongga.data.pykrx_provider import PykrxProvider
# ... (factors/universe/regime/selector/sizing/engine/gate import)

logger = logging.getLogger(__name__)


def main() -> None:
    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s %(levelname)s %(message)s")
    cfg = Config()
    provider = PykrxProvider(cfg.data_dir, market=cfg.market)
    # 1) 거래일·일봉·시총·수급 로드(provider, 캐시)
    # 2) for d in trading_days: t-1 입력으로 팩터·universe·선정·사이징 → run_day
    # 3) 팩터별 일별 IC 수집 + net 수익률 시계열
    # 4) gate.ic / gate.drift / gate.report.verdict → 콘솔·파일 출력
    raise NotImplementedError("Step 6 통합검증에서 결선 완성")


if __name__ == "__main__":
    main()
```

- [ ] **Step 6: 통합 검증 (소기간 실행 → 결선 완성 → 게이트 출력)**

`run_backtest.py`의 `main()`을 위 흐름대로 결선하고(Task 2~14 함수 호출), 짧은 기간(예 2024-01-01~2024-06-30)으로 실행:
```bash
cd /Users/kimjaewon/Pluto/hybrid-trading-agent && .venv/bin/python -m jongga.run_backtest
```
Expected: 팩터별 평균 IC·BH 유의 팩터 수·net 평균(보수/낙관 밴드)·MDD·θ1/θ2·**최종 판정(PASS/FAIL/BASELINE_COLLAPSE)**이 출력. (누수 검증: t-1 입력만 쓰는지 코드 리뷰로 확인 — 의사결정일 d의 입력에 d 데이터가 들어가면 버그.)

- [ ] **Step 7: 전체 단위테스트 회귀 + Commit**

Run: `.venv/bin/pytest tests/jongga -q`
Expected: 전부 PASS.
```bash
git add jongga/gate/report.py jongga/run_backtest.py tests/jongga/test_report.py && git commit -m "feat: gate verdict + walk-forward backtest entry"
```

---

## Task 16: 본 실행 — walk-forward + 홀드아웃 게이트 판정

전 기간(2018~) walk-forward로 돌리고, 파라미터 동결 상태에서 홀드아웃(2025~) 1회 평가. 산출물 = 전략 생사 판정.

- [ ] **Step 1: walk-forward 실행 + 결과 기록**

전 기간 실행:
```bash
cd /Users/kimjaewon/Pluto/hybrid-trading-agent && .venv/bin/python -m jongga.run_backtest 2>&1 | tee docs/superpowers/prereg/phase1-walkforward-result.txt
```
Expected: 팩터별 IC·게이트 판정 출력. **사전등록 합격선(Task 1)과 대조.**

- [ ] **Step 2: 홀드아웃 1회 평가 (파라미터 동결 확인 후)**

config 파라미터를 변경하지 않았음을 git diff로 확인한 뒤, 홀드아웃 구간만 평가하도록 실행하고 결과를 기록. (홀드아웃은 단 1회 — 보고 나서 파라미터 재조정 금지.)

- [ ] **Step 3: 판정 문서화 + Commit**

`docs/superpowers/prereg/phase1-verdict.md`에 walk-forward·홀드아웃 게이트 결과, 사전등록 대비 PASS/FAIL/BASELINE_COLLAPSE, 다음 단계 권고(PASS→Phase 2 LLM, BASELINE_COLLAPSE→팩터/가설 재검토 또는 LLM 증분 직행 검토)를 기록:
```bash
git add docs/superpowers/prereg/phase1-walkforward-result.txt docs/superpowers/prereg/phase1-verdict.md && git commit -m "docs: phase1 backtest gate verdict (walk-forward + holdout)"
```

---

## Phase 0+1 완료 기준 (Definition of Done)

- [ ] 전 단위테스트 통과 (`.venv/bin/pytest tests/jongga -q`)
- [ ] pykrx 프로바이더가 일봉·시총·수급·PIT 종목을 정규 스키마로 공급(캐시)
- [ ] 모든 선정 입력이 t-1 확정치만 사용(누수 차단) — 코드 리뷰로 확인
- [ ] 룰 baseline 백테스트가 종가매수→익일시초매도를 비용 net으로 시뮬(슬리피지 밴드·강제다일 분기)
- [ ] §8.4 게이트(IC+BH·net·드리프트)가 사전등록 합격선으로 자동 판정
- [ ] walk-forward + 홀드아웃 1회 결과로 **make-or-break(#6) 판정** 산출·문서화

---

## Self-Review 메모 (작성자 점검)

- **스펙 커버리지:** Phase 0(§8.4 사전등록=Task1, §8.3 정규스키마=Task2·3, PIT=Task7) / Phase 1(데이터=Task3, t-1 팩터=Task5·6, universe=Task7, regime=Task8, baseline=Task9, sizing=Task10, 체결모델=Task11, 엔진=Task12, IC게이트=Task13, 드리프트=Task14, 판정=Task15, 본실행=Task16). 모두 매핑.
- **스코프 경계 준수:** KIS 예상체결 어댑터·라이브 충격 캘리브·LLM·실행은 의도적으로 제외(다음 계획). cap은 EOD proxy(거래대금)로만 — 라이브 분모(§6 ER-N3)는 Phase 3.
- **누수 차단:** 전 태스크가 t-1 입력 원칙. Task12/15에서 코드 리뷰·불변식으로 강제(자동 단위테스트로 완전 보장은 어려워 통합검증 코드리뷰 병행 — 한계 명시).
- **pykrx 불확실성:** 함수 시그니처·컬럼명은 Task3 Step6·Task7 Step5 통합검증에서 실출력으로 확정(추정→검증 경로). PIT/생존편향·관리종목 가용성은 통합검증에서 판명, 미가용 시 사전등록 한계로 기록.
- **YAGNI:** 멀티전략·LLM·라이브 어댑터 미도입. 팩터 가중치=등가중 초기값(탐색은 walk-forward 내부).
- **사전등록 숫자:** 세율·MDD 한도 등 도메인 값은 Task1에서 `[사용자 확정]` 표기 — 본 실행(Task16) 전 사용자 확인 필요.
```
