"""리스크 관리 모듈"""

from loguru import logger
from config.settings import trading_settings
from core.position_manager import PositionManager


class RiskManager:
    """일일 리스크 관리

    로스 카메론 원칙:
    - 일일 최대 손실 도달 시 매매 중단
    - 연속 손실 시 포지션 축소
    - 종목당 최대 투자 비중 제한
    """

    def __init__(self, position_manager: PositionManager):
        self.pm = position_manager
        self.settings = trading_settings
        self.daily_loss_limit_hit = False
        self.consecutive_losses = 0

    def can_open_position(self, stock_code: str, amount: int) -> tuple[bool, str]:
        """신규 포지션 오픈 가능 여부 확인"""
        # 1) 일일 최대 손실 확인
        if self.pm.realized_pnl <= -self.settings.max_daily_loss:
            self.daily_loss_limit_hit = True
            return False, f"일일 최대 손실 한도 도달 ({self.pm.realized_pnl:,}원)"

        # 2) 최대 동시 보유 종목 수 확인
        if self.pm.open_count >= self.settings.max_positions:
            return False, f"최대 보유 종목 수 초과 ({self.pm.open_count}/{self.settings.max_positions})"

        # 3) 이미 보유 중인 종목인지 확인
        if self.pm.has_position(stock_code):
            return False, f"이미 보유 중: {stock_code}"

        # 4) 종목당 투자 비중 확인
        max_amount = self.settings.max_daily_capital * (self.settings.max_position_pct / 100)
        if amount > max_amount:
            return False, f"종목당 투자 한도 초과: {amount:,}원 > {max_amount:,}원"

        # 5) 일일 총 투자 한도 확인
        total_invested = sum(p.total_value for p in self.pm.positions.values())
        if total_invested + amount > self.settings.max_daily_capital:
            return False, f"일일 투자 한도 초과"

        # 6) 연속 손실 시 경고
        if self.consecutive_losses >= 3:
            logger.warning(f"연속 {self.consecutive_losses}회 손실 - 신중한 진입 필요")

        return True, "진입 가능"

    def update_on_trade_close(self, pnl: int):
        """거래 종료 시 리스크 파라미터 업데이트"""
        if pnl < 0:
            self.consecutive_losses += 1
            logger.warning(f"손실 거래 (연속 {self.consecutive_losses}회)")
        else:
            self.consecutive_losses = 0
            logger.info("수익 거래 - 연속 손실 카운터 리셋")

    def get_adjusted_position_size(self, base_qty: int) -> int:
        """연속 손실 시 포지션 사이즈 축소"""
        if self.consecutive_losses >= 3:
            adjusted = max(1, int(base_qty * 0.5))
            logger.info(f"포지션 축소: {base_qty} → {adjusted} (연속 {self.consecutive_losses}회 손실)")
            return adjusted
        elif self.consecutive_losses >= 2:
            adjusted = max(1, int(base_qty * 0.75))
            logger.info(f"포지션 축소: {base_qty} → {adjusted} (연속 {self.consecutive_losses}회 손실)")
            return adjusted
        return base_qty

    def is_trading_allowed(self) -> tuple[bool, str]:
        """매매 가능 여부"""
        if self.daily_loss_limit_hit:
            return False, "일일 최대 손실 한도 도달 - 오늘 매매 중단"
        return True, "매매 가능"

    def get_status(self) -> dict:
        return {
            "daily_loss_limit_hit": self.daily_loss_limit_hit,
            "consecutive_losses": self.consecutive_losses,
            "realized_pnl": self.pm.realized_pnl,
            "max_daily_capital": self.settings.max_daily_capital,
            "max_daily_loss": self.settings.max_daily_loss,
            "remaining_loss_budget": self.settings.max_daily_loss + self.pm.realized_pnl,
            "open_positions": self.pm.open_count,
            "max_positions": self.settings.max_positions,
        }
