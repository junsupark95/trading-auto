"""한국투자증권 API 인증 모듈"""

import time
import requests
from loguru import logger
from config.settings import kis_settings


class KISAuth:
    """OAuth 토큰 관리 및 API 인증"""

    def __init__(self):
        self.base_url = kis_settings.base_url
        self.app_key = kis_settings.app_key
        self.app_secret = kis_settings.app_secret
        self.access_token: str | None = None
        self.token_expires_at: float = 0

    def get_token(self) -> str:
        """유효한 접근 토큰 반환 (만료 시 자동 갱신)"""
        if self.access_token and time.time() < self.token_expires_at - 60:
            return self.access_token
        return self._issue_token()

    def _issue_token(self) -> str:
        """OAuth 접근 토큰 발급"""
        url = f"{self.base_url}/oauth2/tokenP"
        body = {
            "grant_type": "client_credentials",
            "appkey": self.app_key,
            "appsecret": self.app_secret,
        }
        resp = requests.post(url, json=body, timeout=10)
        resp.raise_for_status()
        data = resp.json()

        self.access_token = data["access_token"]
        # 토큰 유효기간: 약 24시간 (86400초)
        self.token_expires_at = time.time() + data.get("expires_in", 86400)
        logger.info("KIS 접근 토큰 발급 완료")
        return self.access_token

    def get_hashkey(self, body: dict) -> str:
        """주문 등에 필요한 hashkey 발급"""
        url = f"{self.base_url}/uapi/hashkey"
        headers = {
            "Content-Type": "application/json",
            "appKey": self.app_key,
            "appSecret": self.app_secret,
        }
        resp = requests.post(url, json=body, headers=headers, timeout=10)
        resp.raise_for_status()
        return resp.json()["HASH"]

    @property
    def headers(self) -> dict:
        """공통 API 요청 헤더"""
        return {
            "Content-Type": "application/json; charset=utf-8",
            "authorization": f"Bearer {self.get_token()}",
            "appkey": self.app_key,
            "appsecret": self.app_secret,
        }
