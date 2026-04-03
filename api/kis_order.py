"""한국투자증권 주문 모듈"""

import requests
from loguru import logger
from config.settings import kis_settings
from api.kis_auth import KISAuth


class KISOrder:
    """매수/매도 주문 및 잔고 조회"""

    def __init__(self, auth: KISAuth):
        self.auth = auth
        self.base_url = kis_settings.base_url
        self.account_no = kis_settings.account_no
        self.is_real = kis_settings.is_real

    @property
    def _account_prefix(self) -> str:
        return self.account_no.split("-")[0]

    @property
    def _account_suffix(self) -> str:
        return self.account_no.split("-")[1]

    def buy_market(self, stock_code: str, qty: int) -> dict:
        """시장가 매수"""
        return self._place_order(
            stock_code=stock_code,
            qty=qty,
            order_type="01",  # 시장가
            price=0,
            side="buy",
        )

    def buy_limit(self, stock_code: str, qty: int, price: int) -> dict:
        """지정가 매수"""
        return self._place_order(
            stock_code=stock_code,
            qty=qty,
            order_type="00",  # 지정가
            price=price,
            side="buy",
        )

    def sell_market(self, stock_code: str, qty: int) -> dict:
        """시장가 매도"""
        return self._place_order(
            stock_code=stock_code,
            qty=qty,
            order_type="01",
            price=0,
            side="sell",
        )

    def sell_limit(self, stock_code: str, qty: int, price: int) -> dict:
        """지정가 매도"""
        return self._place_order(
            stock_code=stock_code,
            qty=qty,
            order_type="00",
            price=price,
            side="sell",
        )

    def _place_order(
        self, stock_code: str, qty: int, order_type: str, price: int, side: str
    ) -> dict:
        """주문 실행"""
        url = f"{self.base_url}/uapi/domestic-stock/v1/trading/order-cash"

        if side == "buy":
            tr_id = "TTTC0802U" if self.is_real else "VTTC0802U"
        else:
            tr_id = "TTTC0801U" if self.is_real else "VTTC0801U"

        body = {
            "CANO": self._account_prefix,
            "ACNT_PRDT_CD": self._account_suffix,
            "PDNO": stock_code,
            "ORD_DVSN": order_type,
            "ORD_QTY": str(qty),
            "ORD_UNPR": str(price),
        }

        hashkey = self.auth.get_hashkey(body)
        headers = {
            **self.auth.headers,
            "tr_id": tr_id,
            "hashkey": hashkey,
        }

        resp = requests.post(url, json=body, headers=headers, timeout=10)
        resp.raise_for_status()
        result = resp.json()

        if result.get("rt_cd") == "0":
            order_no = result.get("output", {}).get("ODNO", "")
            logger.info(
                f"주문 성공: {side.upper()} {stock_code} x{qty} @ {price} (주문번호: {order_no})"
            )
            return {
                "success": True,
                "order_no": order_no,
                "stock_code": stock_code,
                "side": side,
                "qty": qty,
                "price": price,
            }
        else:
            msg = result.get("msg1", "알 수 없는 오류")
            logger.error(f"주문 실패: {side.upper()} {stock_code} - {msg}")
            return {"success": False, "error": msg}

    def get_balance(self) -> list[dict]:
        """보유 잔고 조회"""
        url = f"{self.base_url}/uapi/domestic-stock/v1/trading/inquire-balance"
        tr_id = "TTTC8434R" if self.is_real else "VTTC8434R"
        headers = {
            **self.auth.headers,
            "tr_id": tr_id,
        }
        params = {
            "CANO": self._account_prefix,
            "ACNT_PRDT_CD": self._account_suffix,
            "AFHR_FLPR_YN": "N",
            "OFL_YN": "",
            "INQR_DVSN": "02",
            "UNPR_DVSN": "01",
            "FUND_STTL_ICLD_YN": "N",
            "FNCG_AMT_AUTO_RDPT_YN": "N",
            "PRCS_DVSN": "01",
            "CTX_AREA_FK100": "",
            "CTX_AREA_NK100": "",
        }
        resp = requests.get(url, headers=headers, params=params, timeout=10)
        resp.raise_for_status()
        items = resp.json().get("output1", [])

        positions = []
        for item in items:
            qty = int(item.get("hldg_qty", 0))
            if qty == 0:
                continue
            positions.append({
                "stock_code": item.get("pdno", ""),
                "name": item.get("prdt_name", ""),
                "qty": qty,
                "avg_price": int(float(item.get("pchs_avg_pric", 0))),
                "current_price": int(item.get("prpr", 0)),
                "pnl": int(item.get("evlu_pfls_amt", 0)),
                "pnl_pct": float(item.get("evlu_pfls_rt", 0)),
                "total_value": int(item.get("evlu_amt", 0)),
            })
        return positions

    def get_cash_balance(self) -> int:
        """주문 가능 현금 잔고 조회"""
        url = f"{self.base_url}/uapi/domestic-stock/v1/trading/inquire-psbl-order"
        tr_id = "TTTC8908R" if self.is_real else "VTTC8908R"
        headers = {
            **self.auth.headers,
            "tr_id": tr_id,
        }
        params = {
            "CANO": self._account_prefix,
            "ACNT_PRDT_CD": self._account_suffix,
            "PDNO": "005930",
            "ORD_UNPR": "0",
            "ORD_DVSN": "01",
            "CMA_EVLU_AMT_ICLD_YN": "Y",
            "OVRS_ICLD_YN": "Y",
        }
        resp = requests.get(url, headers=headers, params=params, timeout=10)
        resp.raise_for_status()
        data = resp.json().get("output", {})
        return int(data.get("ord_psbl_cash", 0))
