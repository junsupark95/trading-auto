"""한국투자증권 시세 조회 모듈"""

import pandas as pd
import requests
from loguru import logger
from config.settings import kis_settings
from api.kis_auth import KISAuth


class KISMarket:
    """시세 조회, 종목 정보, 호가 등"""

    def __init__(self, auth: KISAuth):
        self.auth = auth
        self.base_url = kis_settings.base_url

    def get_current_price(self, stock_code: str) -> dict:
        """현재가 조회"""
        url = f"{self.base_url}/uapi/domestic-stock/v1/quotations/inquire-price"
        headers = {
            **self.auth.headers,
            "tr_id": "FHKST01010100",
        }
        params = {
            "FID_COND_MRKT_DIV_CODE": "J",
            "FID_INPUT_ISCD": stock_code,
        }
        resp = requests.get(url, headers=headers, params=params, timeout=10)
        resp.raise_for_status()
        data = resp.json().get("output", {})
        return {
            "stock_code": stock_code,
            "name": data.get("hts_kor_isnm", ""),
            "price": int(data.get("stck_prpr", 0)),
            "change_pct": float(data.get("prdy_ctrt", 0)),
            "volume": int(data.get("acml_vol", 0)),
            "trade_amount": int(data.get("acml_tr_pbmn", 0)),
            "high": int(data.get("stck_hgpr", 0)),
            "low": int(data.get("stck_lwpr", 0)),
            "open": int(data.get("stck_oprc", 0)),
            "prev_close": int(data.get("stck_sdpr", 0)),
            "market_cap": int(data.get("hts_avls", 0)) * 100_000_000,
        }

    def get_minute_chart(self, stock_code: str, period: str = "1") -> pd.DataFrame:
        """분봉 데이터 조회 (1분, 3분, 5분, 10분, 15분, 30분, 60분)"""
        from datetime import datetime as _dt
        import pytz as _pytz
        _kst = _pytz.timezone("Asia/Seoul")
        current_time = _dt.now(_kst).strftime("%H%M%S")

        url = f"{self.base_url}/uapi/domestic-stock/v1/quotations/inquire-time-itemchartprice"
        headers = {
            **self.auth.headers,
            "tr_id": "FHKST03010200",
        }
        params = {
            "FID_ETC_CLS_CODE": "",
            "FID_COND_MRKT_DIV_CODE": "J",
            "FID_INPUT_ISCD": stock_code,
            "FID_INPUT_HOUR_1": current_time,  # 현재 시각 기준 이전 데이터 조회 (하드코딩 시 미래 시간 문제)
            "FID_PW_DATA_INCU_YN": "Y",
        }
        resp = requests.get(url, headers=headers, params=params, timeout=10)
        resp.raise_for_status()
        items = resp.json().get("output2", [])

        if not items:
            return pd.DataFrame()

        df = pd.DataFrame(items)
        df = df.rename(columns={
            "stck_cntg_hour": "time",
            "stck_prpr": "close",
            "stck_oprc": "open",
            "stck_hgpr": "high",
            "stck_lwpr": "low",
            "cntg_vol": "volume",
        })
        for col in ["close", "open", "high", "low", "volume"]:
            if col in df.columns:
                df[col] = pd.to_numeric(df[col], errors="coerce")
        return df[["time", "open", "high", "low", "close", "volume"]].sort_values("time")

    def get_volume_rank(self, market: str = "J") -> list[dict]:
        """거래량 급증 종목 조회 (갭업 스캐닝용)"""
        url = f"{self.base_url}/uapi/domestic-stock/v1/quotations/volume-rank"
        headers = {
            **self.auth.headers,
            "tr_id": "FHPST01710000",
        }
        params = {
            "FID_COND_MRKT_DIV_CODE": market,
            "FID_COND_SCR_DIV_CODE": "20171",
            "FID_INPUT_ISCD": "0000",
            "FID_DIV_CLS_CODE": "0",
            "FID_BLNG_CLS_CODE": "0",
            "FID_TRGT_CLS_CODE": "111111111",
            "FID_TRGT_EXLS_CLS_CODE": "000000",
            "FID_INPUT_PRICE_1": "",
            "FID_INPUT_PRICE_2": "",
            "FID_VOL_CNT": "",
            "FID_INPUT_DATE_1": "",
        }
        resp = requests.get(url, headers=headers, params=params, timeout=10)
        resp.raise_for_status()
        items = resp.json().get("output", [])

        results = []
        for item in items:
            results.append({
                "stock_code": item.get("mksc_shrn_iscd", ""),
                "name": item.get("hts_kor_isnm", ""),
                "price": int(item.get("stck_prpr", 0)),
                "change_pct": float(item.get("prdy_ctrt", 0)),
                "volume": int(item.get("acml_vol", 0)),
                "volume_ratio": float(item.get("vol_inrt", 0)),
                "market_cap": int(item.get("hts_avls", 0)) * 100_000_000,
            })
        return results

    def get_orderbook(self, stock_code: str) -> dict:
        """호가 조회"""
        url = f"{self.base_url}/uapi/domestic-stock/v1/quotations/inquire-asking-price-exp-ccn"
        headers = {
            **self.auth.headers,
            "tr_id": "FHKST01010200",
        }
        params = {
            "FID_COND_MRKT_DIV_CODE": "J",
            "FID_INPUT_ISCD": stock_code,
        }
        resp = requests.get(url, headers=headers, params=params, timeout=10)
        resp.raise_for_status()
        data = resp.json().get("output1", {})

        asks = []
        bids = []
        for i in range(1, 11):
            asks.append({
                "price": int(data.get(f"askp{i}", 0)),
                "volume": int(data.get(f"askp_rsqn{i}", 0)),
            })
            bids.append({
                "price": int(data.get(f"bidp{i}", 0)),
                "volume": int(data.get(f"bidp_rsqn{i}", 0)),
            })
        return {"asks": asks, "bids": bids}

    def get_fluctuation_rank(self) -> list[dict]:
        """등락률 상위 종목 (프리마켓 갭업 스캐닝)"""
        url = f"{self.base_url}/uapi/domestic-stock/v1/ranking/fluctuation"
        headers = {
            **self.auth.headers,
            "tr_id": "FHPST01700000",
        }
        params = {
            "fid_cond_mrkt_div_code": "J",
            "fid_cond_scr_div_code": "20170",
            "fid_input_iscd": "0000",
            "fid_rank_sort_cls_code": "0",
            "fid_input_cnt_1": "0",
            "fid_prc_cls_code": "1",
            "fid_input_price_1": "",
            "fid_input_price_2": "",
            "fid_vol_cnt": "",
            "fid_trgt_cls_code": "0",
            "fid_trgt_exls_cls_code": "0",
            "fid_div_cls_code": "0",
            "fid_rsfl_rate1": "",
            "fid_rsfl_rate2": "",
        }
        resp = requests.get(url, headers=headers, params=params, timeout=10)
        resp.raise_for_status()
        items = resp.json().get("output", [])

        results = []
        for item in items:
            results.append({
                "stock_code": item.get("stck_shrn_iscd", ""),
                "name": item.get("hts_kor_isnm", ""),
                "price": int(item.get("stck_prpr", 0)),
                "change_pct": float(item.get("prdy_ctrt", 0)),
                "volume": int(item.get("acml_vol", 0)),
            })
        return results
