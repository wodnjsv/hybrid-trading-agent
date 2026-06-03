from jongga.data.krx_provider import parse_daily


def test_parse_daily_normalizes_strings():
    rows = [{"ISU_CD": "060310", "TDD_OPNPRC": "3210", "TDD_HGPRC": "3300",
             "TDD_LWPRC": "3200", "TDD_CLSPRC": "3300", "ACC_TRDVOL": "100",
             "ACC_TRDVAL": "5774925915", "MKTCAP": "160170918600",
             "LIST_SHRS": "48536642", "SECT_TP_NM": "중견기업부"}]
    df = parse_daily(rows)
    assert df.loc["060310", "close"] == 3300
    assert df.loc["060310", "open"] == 3210
    assert df.loc["060310", "marketcap"] == 160170918600
    assert df.loc["060310", "sect"] == "중견기업부"


def test_parse_daily_empty_returns_empty_frame():
    df = parse_daily([])              # 휴장일/빈 응답
    assert len(df) == 0
    assert "close" in df.columns
