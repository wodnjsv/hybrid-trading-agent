# 실행 가이드 — 수집(Windows) / 개발(Mac)

데이터 수집은 항상 켜둘 수 있는 **Windows** 박스에서, 개발·백테스트는 **Mac**에서.
코드는 git으로 공유하고, **수집한 데이터는 수동으로 복사**한다 (`data/`는 git에 안 올라감).

코드 자체는 크로스플랫폼이라 두 OS에서 동일하게 동작한다. OS별 차이는 venv 경로와 절전 제어뿐.

---

## 공통 1회 셋업 (각 컴퓨터에서)

**Windows**
```bat
python -m venv .venv
.venv\Scripts\pip install -e ".[dev]"
copy secrets.example.yaml secrets.yaml   REM 그리고 키 입력
```

**macOS**
```bash
python3 -m venv .venv
.venv/bin/pip install -e ".[dev]"
cp secrets.example.yaml secrets.yaml      # 그리고 키 입력
```

`secrets.yaml` (양쪽 동일, git 무시됨):
```yaml
app_key: "..."
app_secret: "..."
account_no: "12345678"   # 종합계좌번호 8자리 (수집엔 미사용, Phase 1 대비)
is_paper: false          # 실전 키면 false, 모의 키면 true
```

---

## 데이터 수집 (Windows, 장중 09:00~15:30 KST)

가장 쉬운 방법 — 파일 탐색기에서 **`run-collector.bat` 더블클릭**, 또는:
```bat
.venv\Scripts\manju-collect.exe
```
- 시작하면 `universe: 20 active` 로그가 뜨고, 거래대금 상위 ~20종목의 체결·호가를 `data/`에 녹음한다.
- **절전 자동 방지**: 실행 중에는 Windows 시스템이 잠들지 않도록 코드가 막는다(화면은 꺼져도 됨). 노트북은 전원 연결 권장.
- **중지**: 창에서 **Ctrl+C**. 이때 그날 데이터를 자동으로 **컴팩션**(종목당 1파일로 병합)한다.

> 수집기는 켜져 있는 동안에만 녹음한다. 꺼진 시간 = 영구 데이터 공백(KIS는 과거 호가를 소급 제공하지 않음).

---

## 저장 구조 & 컴팩션

수집 중에는 크래시 안전을 위해 10초마다 작은 shard 파일을 쓴다:
```
data/ticks/2026-06-02/005930-000001.parquet   ← 체결
data/quotes/2026-06-02/005930-000001.parquet  ← 호가
```
정상 종료 시 자동으로, 또는 수동으로 컴팩션하면 종목당 1파일로 병합된다:
```bat
.venv\Scripts\manju-compact.exe                 REM 전체 날짜
.venv\Scripts\manju-compact.exe --date 2026-06-02
```
결과: `data/ticks/2026-06-02/005930.parquet` (shard 삭제, 시간순 정렬). 크래시로 shard가 남았으면 `manju-compact`로 정리 후 복사.

---

## 데이터를 Mac으로 옮기기 (수동)

Windows에서 그날 폴더를 압축해서 옮기는 게 가장 간단하다:
```bat
REM 컴팩션 후 (파일 수가 적어 압축/복사가 빠름)
powershell Compress-Archive -Path data\ticks\2026-06-02,data\quotes\2026-06-02 -DestinationPath 2026-06-02.zip
```
이 `2026-06-02.zip`을 USB/클라우드/공유폴더로 Mac에 복사 후, Mac의 `data/` 아래에 같은 구조로 풀면 된다.

---

## 개발·검증 (Mac)

```bash
.venv/bin/pytest -q                  # 단위 테스트
```
복사해온 데이터 재생(재현) 확인:
```bash
.venv/bin/python - <<'PY'
from manju.replay.feed import ReplayFeed
evs = list(ReplayFeed("data", "2026-06-02").events())
print("events:", len(evs))
PY
```

macOS에서 직접 수집해보고 싶을 때(절전 방지 포함):
```bash
caffeinate -i .venv/bin/manju-collect
```
