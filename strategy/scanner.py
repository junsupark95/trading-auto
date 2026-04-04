"""갭업 종목 스캐너 - 로스 카메론 전략의 종목 선별"""

from loguru import logger
from config.settings import ross_settings
from api.kis_market import KISMarket


class GapUpScanner:
    """프리마켓/장초반 갭업 종목 스캐닝

    로스 카메론 기준:
    - 갭업 비율이 일정 수준 이상
    - 상대 거래량이 평소 대비 급증
    - 소형~중형주 (시가총액 필터)
    - 적정 가격대
    """

    def __init__(self, market: KISMarket):
        self.market = market
        self.settings = ross_settings

    def scan(self) -> list[dict]:
        """갭업 후보 종목 스캔 후 필터링"""
        candidates = []

        # 1) 등락률 상위 종목 가져오기
        try:
            fluctuation = self.market.get_fluctuation_rank()
        except Exception as e:
            logger.warning(f"등락률 조회 실패: {e}")
            fluctuation = []

        # 2) 거래량 급증 종목 가져오기
        try:
            volume_rank = self.market.get_volume_rank()
        except Exception as e:
            logger.warning(f"거래량 조회 실패: {e}")
            volume_rank = []

        # 두 리스트 병합 (중복 제거)
        seen = set()
        all_stocks = []
        for stock in fluctuation + volume_rank:
            code = stock.get("stock_code", "")
            if code and code not in seen:
                seen.add(code)
                all_stocks.append(stock)

        # 3) 필터링
        for stock in all_stocks:
            if self._passes_filter(stock):
                # 추가 상세 정보 조회
                try:
                    detail = self.market.get_current_price(stock["stock_code"])
                    stock.update(detail)
                except Exception:
                    pass
                candidates.append(stock)

        # 갭업 비율 높은 순으로 정렬
        candidates.sort(key=lambda x: x.get("change_pct", 0), reverse=True)

        logger.info(f"갭업 스캐너: {len(all_stocks)}개 중 {len(candidates)}개 후보 선별")
        return candidates[:20]  # 상위 20개

    def _passes_filter(self, stock: dict) -> bool:
        """로스 카메론 종목 필터 조건"""
        price = stock.get("price", 0)
        change_pct = stock.get("change_pct", 0)
        volume_ratio = stock.get("volume_ratio", 0)
        market_cap = stock.get("market_cap", 0)

        # 갭업 비율 최소 조건
        if change_pct < self.settings.min_gap_pct:
            return False

        # 가격대 필터
        if price < self.settings.min_price or price > self.settings.max_price:
            return False

        # 시가총액 필터 (0이면 정보 없음 → 통과)
        if market_cap > 0 and market_cap > self.settings.max_market_cap:
            return False

        # 거래량 배수 (정보 있는 경우에만)
        if volume_ratio > 0 and volume_ratio < self.settings.min_volume_ratio:
            return False

        return True

    def get_scanner_summary(self, candidates: list[dict]) -> str:
        """AI 분석용 스캐너 결과 요약 텍스트 생성"""
        if not candidates:
            return "현재 갭업 조건을 충족하는 종목이 없습니다."

        lines = ["=== 갭업 스캐너 결과 ===\n"]
        for i, c in enumerate(candidates, 1):
            lines.append(
                f"{i}. {c.get('name', '?')} ({c.get('stock_code', '?')})\n"
                f"   현재가: {c.get('price', 0):,}원 | "
                f"등락률: {c.get('change_pct', 0):+.2f}% | "
                f"거래량: {c.get('volume', 0):,} | "
                f"거래량배수: {c.get('volume_ratio', 0):.1f}x | "
                f"시가총액: {c.get('market_cap', 0) / 100_000_000:,.0f}억원"
            )
        return "\n".join(lines)
