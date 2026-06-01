# manju/kis/constants.py
"""KIS TR ID 및 실시간 필드 레이아웃.

PRICE_COLUMNS는 open-trading-api(koreainvestment/open-trading-api)의
websocket.py에서 검증된 H0STCNT0 체결 필드 순서.
"""

TRADE_TR = "H0STCNT0"   # 실시간 체결가
QUOTE_TR = "H0STASP0"   # 실시간 호가

# REST: 거래량/거래대금 순위
VOLUME_RANK_TR = "FHPST01710000"
VOLUME_RANK_PATH = "/uapi/domestic-stock/v1/quotations/volume-rank"

# 인증
TOKEN_PATH = "/oauth2/tokenP"
APPROVAL_PATH = "/oauth2/Approval"

# H0STCNT0 체결 필드 순서 (^ 구분)
PRICE_COLUMNS = [
    "MKSC_SHRN_ISCD", "STCK_CNTG_HOUR", "STCK_PRPR", "PRDY_VRSS_SIGN",
    "PRDY_VRSS", "PRDY_CTRT", "WGHN_AVRG_STCK_PRC", "STCK_OPRC",
    "STCK_HGPR", "STCK_LWPR", "ASKP1", "BIDP1", "CNTG_VOL", "ACML_VOL",
    "ACML_TR_PBMN", "SELN_CNTG_CSNU", "SHNU_CNTG_CSNU", "NTBY_CNTG_CSNU",
    "CTTR", "SELN_CNTG_SMTN", "SHNU_CNTG_SMTN", "CCLD_DVSN", "SHNU_RATE",
    "PRDY_VOL_VRSS_ACML_VOL_RATE", "OPRC_HOUR", "OPRC_VRSS_PRPR_SIGN",
    "OPRC_VRSS_PRPR", "HGPR_HOUR", "HGPR_VRSS_PRPR_SIGN", "HGPR_VRSS_PRPR",
    "LWPR_HOUR", "LWPR_VRSS_PRPR_SIGN", "LWPR_VRSS_PRPR", "BSOP_DATE",
    "NEW_MKOP_CLS_CODE", "TRHT_YN", "ASKP_RSQN1", "BIDP_RSQN1",
    "TOTAL_ASKP_RSQN", "TOTAL_BIDP_RSQN", "VOL_TNRT",
    "PRDY_SMNS_HOUR_ACML_VOL", "PRDY_SMNS_HOUR_ACML_VOL_RATE",
    "HOUR_CLS_CODE", "MRKT_TRTM_CLS_CODE", "VI_STND_PRC",
]

# H0STASP0 호가 선두 필드 인덱스 (^ 구분). 선두 45필드만 확정 사용, 나머지는 raw 보관.
# 0:종목 1:영업시간 2:시간구분 | 3~12:매도호가1~10 13~22:매수호가1~10
# 23~32:매도잔량1~10 33~42:매수잔량1~10 | 43:총매도잔량 44:총매수잔량
QUOTE_IDX = {
    "symbol": 0, "hour": 1,
    "ask": slice(3, 13), "bid": slice(13, 23),
    "ask_qty": slice(23, 33), "bid_qty": slice(33, 43),
    "total_ask_qty": 43, "total_bid_qty": 44,
}
