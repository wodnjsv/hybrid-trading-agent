# tests/test_auth.py
import manju.kis.auth as auth
from manju.config import Config

CFG = Config(app_key="AK", app_secret="AS", account_no="12345678", is_paper=False)


class _Resp:
    def __init__(self, payload): self._p = payload
    def raise_for_status(self): pass
    def json(self): return self._p


def test_issue_token_posts_correct_payload(monkeypatch):
    captured = {}
    def fake_post(url, json=None, timeout=None):
        captured["url"] = url; captured["json"] = json
        return _Resp({"access_token": "TOK", "expires_in": 86400})
    monkeypatch.setattr(auth.requests, "post", fake_post)

    tok = auth.issue_access_token(CFG)
    assert tok == "TOK"
    assert captured["url"] == "https://openapi.koreainvestment.com:9443/oauth2/tokenP"
    assert captured["json"] == {
        "grant_type": "client_credentials", "appkey": "AK", "appsecret": "AS"}


def test_issue_approval_uses_secretkey_field(monkeypatch):
    captured = {}
    def fake_post(url, json=None, timeout=None):
        captured["json"] = json
        return _Resp({"approval_key": "APPR"})
    monkeypatch.setattr(auth.requests, "post", fake_post)

    key = auth.issue_approval_key(CFG)
    assert key == "APPR"
    # Approval 엔드포인트는 appsecret이 아니라 secretkey 필드 사용
    assert captured["json"]["secretkey"] == "AS"
    assert "appsecret" not in captured["json"]
