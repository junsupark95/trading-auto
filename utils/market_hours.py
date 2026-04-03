"""한국 주식시장 시간 유틸리티"""

from datetime import datetime, time
import pytz

KST = pytz.timezone("Asia/Seoul")

# 한국 공휴일은 별도 관리 필요 (간단 버전)
MARKET_OPEN = time(9, 0)
MARKET_CLOSE = time(15, 30)
PRE_MARKET_START = time(8, 30)


def now_kst() -> datetime:
    return datetime.now(KST)


def is_market_open() -> bool:
    """장 운영 시간 여부"""
    now = now_kst()
    if now.weekday() >= 5:  # 토, 일
        return False
    return MARKET_OPEN <= now.time() <= MARKET_CLOSE


def is_pre_market() -> bool:
    """프리마켓 시간 (08:30~09:00)"""
    now = now_kst()
    if now.weekday() >= 5:
        return False
    return PRE_MARKET_START <= now.time() < MARKET_OPEN


def seconds_until_market_open() -> int:
    """장 시작까지 남은 초"""
    now = now_kst()
    market_open_dt = now.replace(hour=9, minute=0, second=0, microsecond=0)
    if now.time() >= MARKET_OPEN:
        return 0
    return int((market_open_dt - now).total_seconds())


def is_prime_time() -> bool:
    """로스 카메론 핵심 매매 시간 (09:00~10:30)"""
    now = now_kst()
    return time(9, 0) <= now.time() <= time(10, 30)
