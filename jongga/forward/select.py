"""GPT-5.4 웹검색 재료 선별: 프롬프트·structured 스키마 + 응답 파싱·검증(순수). (실호출은 후속 태스크.)"""
from __future__ import annotations

SELECTION_SCHEMA = {
    "type": "object",
    "properties": {
        "regime_read": {"type": "string"},
        "picks": {"type": "array", "items": {
            "type": "object",
            "properties": {
                "ticker": {"type": "string"},
                "catalyst_summary": {"type": "string"},
                "catalyst_timestamp": {"type": "string"},
                "theme": {"type": "string"},
                "conviction": {"type": "number"},
                "rationale": {"type": "string"},
            },
            "required": ["ticker", "catalyst_summary", "catalyst_timestamp",
                         "theme", "conviction", "rationale"],
        }},
    },
    "required": ["regime_read", "picks"],
}

SYSTEM_PROMPT = (
    "너는 한국 주식 종가베팅 트레이더다. 주어진 후보(정량 컨텍스트 포함) 중, "
    "그날 15:20(종가 동시호가) 이전에 공개된 재료/뉴스/테마가 강한 종목만 0~K개 고른다. "
    "재료가 약하면 빈 배열로 패스한다. 각 픽에 재료 발표시각(catalyst_timestamp, ≤15:20)을 반드시 단다. "
    "15:20 이후(장 마감 후) 공시·뉴스는 사용 금지."
)


def parse_selection(raw: dict, candidate_tickers: set[str]) -> list[dict]:
    """응답 dict → 검증된 픽 리스트. 후보 밖 종목·필드 누락은 제외. 패스=[]."""
    out = []
    for p in raw.get("picks", []):
        if not isinstance(p, dict) or p.get("ticker") not in candidate_tickers:
            continue
        if not all(k in p for k in ("catalyst_summary", "catalyst_timestamp", "theme",
                                    "conviction", "rationale")):
            continue
        c = max(0.0, min(1.0, float(p["conviction"])))
        out.append({**p, "conviction": c})
    return out
