"""KRX OpenAPI(코스닥 일별매매정보) 프로바이더. 인증=AUTH_KEY 헤더(프로브 확정)."""
from __future__ import annotations
import json
import urllib.parse
import urllib.request
from pathlib import Path
import pandas as pd
from jongga.data.cache import cache_path, load_or_fetch

BASE = "https://data-dbg.krx.co.kr/svc/apis/sto/ksq_bydd_trd"
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


def _fetch(date: str, api_key: str) -> list[dict]:
    url = BASE + "?" + urllib.parse.urlencode({"basDd": date})
    req = urllib.request.Request(url, headers={"AUTH_KEY": api_key})
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read().decode("utf-8")).get("OutBlock_1", [])


class KrxProvider:
    def __init__(self, data_dir, api_key: str):
        self.data_dir = Path(data_dir)
        self.api_key = api_key

    def daily(self, date: str) -> pd.DataFrame:
        key = date.replace("-", "")
        return load_or_fetch(cache_path(self.data_dir, "daily", date),
                             lambda: parse_daily(_fetch(key, self.api_key)))
