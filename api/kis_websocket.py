from __future__ import annotations

"""한국투자증권 실시간 WebSocket 모듈"""

import json
import asyncio
from collections.abc import Callable
from loguru import logger
from config.settings import kis_settings

try:
    import websockets
except ImportError:
    websockets = None


class KISWebSocket:
    """실시간 체결가/호가 WebSocket 스트리밍"""

    def __init__(self, auth):
        self.auth = auth
        self.ws_url = kis_settings.ws_url
        self.subscriptions: dict[str, list[Callable]] = {}
        self._ws = None
        self._running = False
        self._approval_key: str | None = None

    def _get_approval_key(self) -> str:
        """WebSocket 접속키 발급"""
        if self._approval_key:
            return self._approval_key
        import requests
        url = f"{kis_settings.base_url}/oauth2/Approval"
        body = {
            "grant_type": "client_credentials",
            "appkey": kis_settings.app_key,
            "secretkey": kis_settings.app_secret,
        }
        resp = requests.post(url, json=body, timeout=10)
        resp.raise_for_status()
        self._approval_key = resp.json()["approval_key"]
        return self._approval_key

    def subscribe_price(self, stock_code: str, callback: Callable):
        """실시간 체결가 구독"""
        key = f"H0STCNT0|{stock_code}"
        if key not in self.subscriptions:
            self.subscriptions[key] = []
        self.subscriptions[key].append(callback)

    def subscribe_orderbook(self, stock_code: str, callback: Callable):
        """실시간 호가 구독"""
        key = f"H0STASP0|{stock_code}"
        if key not in self.subscriptions:
            self.subscriptions[key] = []
        self.subscriptions[key].append(callback)

    async def connect(self):
        """WebSocket 연결 및 수신 루프"""
        if websockets is None:
            logger.error("websockets 패키지가 설치되지 않았습니다")
            return

        approval_key = self._get_approval_key()
        self._running = True

        async with websockets.connect(self.ws_url, ping_interval=30) as ws:
            self._ws = ws
            logger.info("KIS WebSocket 연결 완료")

            # 구독 등록
            for key in self.subscriptions:
                tr_id, tr_key = key.split("|")
                sub_msg = json.dumps({
                    "header": {
                        "approval_key": approval_key,
                        "custtype": "P",
                        "tr_type": "1",
                        "content-type": "utf-8",
                    },
                    "body": {
                        "input": {
                            "tr_id": tr_id,
                            "tr_key": tr_key,
                        }
                    }
                })
                await ws.send(sub_msg)
                logger.info(f"실시간 구독: {tr_id} {tr_key}")

            # 수신 루프
            while self._running:
                try:
                    raw = await asyncio.wait_for(ws.recv(), timeout=60)
                    self._handle_message(raw)
                except asyncio.TimeoutError:
                    continue
                except websockets.ConnectionClosed:
                    logger.warning("WebSocket 연결 종료")
                    break

    def _handle_message(self, raw: str):
        """수신 메시지 파싱 및 콜백 호출"""
        # 실시간 데이터는 '|' 로 구분된 텍스트 형식
        if raw.startswith("{"):
            # JSON 응답 (구독 확인 등)
            return

        parts = raw.split("|")
        if len(parts) < 4:
            return

        tr_id = parts[1]
        data_cnt = int(parts[2])
        data_str = parts[3]

        if tr_id == "H0STCNT0":
            # 실시간 체결
            fields = data_str.split("^")
            if len(fields) >= 15:
                tick = {
                    "stock_code": fields[0],
                    "time": fields[1],
                    "price": int(fields[2]),
                    "change": int(fields[4]),
                    "change_pct": float(fields[5]),
                    "volume": int(fields[12]),
                    "acc_volume": int(fields[13]),
                }
                key = f"H0STCNT0|{tick['stock_code']}"
                for cb in self.subscriptions.get(key, []):
                    cb(tick)

    async def disconnect(self):
        """WebSocket 연결 종료"""
        self._running = False
        if self._ws:
            await self._ws.close()
            logger.info("KIS WebSocket 연결 해제")
