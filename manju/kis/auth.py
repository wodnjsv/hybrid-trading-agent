# manju/kis/auth.py
"""KIS OAuth: access_token(REST), approval_key(WebSocket) 발급."""
from __future__ import annotations
import requests
from manju.config import Config
from manju.kis.constants import TOKEN_PATH, APPROVAL_PATH


def issue_access_token(cfg: Config) -> str:
    r = requests.post(
        cfg.base_url + TOKEN_PATH,
        json={"grant_type": "client_credentials",
              "appkey": cfg.app_key, "appsecret": cfg.app_secret},
        timeout=10,
    )
    r.raise_for_status()
    return r.json()["access_token"]


def issue_approval_key(cfg: Config) -> str:
    # 주의: Approval 엔드포인트는 'secretkey' 필드명을 사용 (tokenP의 appsecret과 다름)
    r = requests.post(
        cfg.base_url + APPROVAL_PATH,
        json={"grant_type": "client_credentials",
              "appkey": cfg.app_key, "secretkey": cfg.app_secret},
        timeout=10,
    )
    r.raise_for_status()
    return r.json()["approval_key"]
