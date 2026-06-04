"""KRX OpenAPI 일별매매정보 프로바이더(KOSDAQ/KOSPI). 인증=AUTH_KEY 헤더(프로브 확정).

KOSPI(유가증권)·KOSDAQ 응답 필드는 동일(Spec 5·6) → parse_daily 공용."""
from __future__ import annotations
import json
import urllib.parse
import urllib.request
from pathlib import Path
import pandas as pd
from jongga.data.cache import cache_path, load_or_fetch

ENDPOINTS = {
    "KOSDAQ": "https://data-dbg.krx.co.kr/svc/apis/sto/ksq_bydd_trd",
    "KOSPI": "https://data-dbg.krx.co.kr/svc/apis/sto/stk_bydd_trd",
}
BASE = ENDPOINTS["KOSDAQ"]   # 하위호환(기본 KOSDAQ)
_FIELDS = {"ISU_CD": "ticker", "TDD_OPNPRC": "open", "TDD_HGPRC": "high",
           "TDD_LWPRC": "low", "TDD_CLSPRC": "close", "ACC_TRDVOL": "volume",
           "ACC_TRDVAL": "value", "MKTCAP": "marketcap", "LIST_SHRS": "shares",
           "SECT_TP_NM": "sect"}
_NUM = ["open", "high", "low", "close", "volume", "value", "marketcap", "shares"]


def parse_daily(rows: list[dict]) -> pd.DataFrame:
    if not rows:                       # 휴장일/일시적 빈 응답 → 빈 프레임(호출측이 skip)
        return pd.DataFrame(columns=[c for c in _FIELDS.values() if c != "ticker"])
    df = pd.DataFrame(rows)[list(_FIELDS)].rename(columns=_FIELDS)
    for c in _NUM:
        df[c] = pd.to_numeric(df[c].astype(str).str.replace(",", ""), errors="coerce")
    return df.set_index("ticker")


def _fetch(date: str, api_key: str, url: str = BASE) -> list[dict]:
    full = url + "?" + urllib.parse.urlencode({"basDd": date})
    req = urllib.request.Request(full, headers={"AUTH_KEY": api_key})
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read().decode("utf-8")).get("OutBlock_1", [])


class KrxProvider:
    def __init__(self, data_dir, api_key: str, market: str = "KOSDAQ"):
        self.data_dir = Path(data_dir)
        self.api_key = api_key
        self.market = market
        self.url = ENDPOINTS[market]

    def daily(self, date: str) -> pd.DataFrame:
        key = date.replace("-", "")
        kind = "daily" if self.market == "KOSDAQ" else f"daily_{self.market}"
        return load_or_fetch(cache_path(self.data_dir, kind, date),
                             lambda: parse_daily(_fetch(key, self.api_key, self.url)))
