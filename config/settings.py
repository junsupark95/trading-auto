"""전체 시스템 설정"""

from pydantic_settings import BaseSettings
from pydantic import Field


class KISSettings(BaseSettings):
    """한국투자증권 API 설정"""
    app_key: str = Field(alias="KIS_APP_KEY")
    app_secret: str = Field(alias="KIS_APP_SECRET")
    account_no: str = Field(alias="KIS_ACCOUNT_NO")
    environment: str = Field(default="VIRTUAL", alias="KIS_ENVIRONMENT")

    @property
    def is_real(self) -> bool:
        return self.environment == "REAL"

    @property
    def base_url(self) -> str:
        if self.is_real:
            return "https://openapi.koreainvestment.com:9443"
        return "https://openapivts.koreainvestment.com:29443"

    @property
    def ws_url(self) -> str:
        if self.is_real:
            return "ws://ops.koreainvestment.com:21000"
        return "ws://ops.koreainvestment.com:31000"

    model_config = {"env_file": ".env", "extra": "ignore"}


class TradingSettings(BaseSettings):
    """트레이딩 파라미터 설정"""
    max_daily_capital: int = Field(default=1_000_000, alias="MAX_DAILY_CAPITAL")
    max_daily_loss: int = Field(default=200_000, alias="MAX_DAILY_LOSS")
    max_position_pct: int = Field(default=20, alias="MAX_POSITION_PCT")
    max_positions: int = Field(default=5, alias="MAX_POSITIONS")
    order_cooldown_sec: int = Field(default=10, alias="ORDER_COOLDOWN_SEC")
    max_slippage_pct: float = Field(default=0.5, alias="MAX_SLIPPAGE_PCT")

    model_config = {"env_file": ".env", "extra": "ignore"}


class AISettings(BaseSettings):
    """AI API 설정"""
    anthropic_api_key: str = Field(default="", alias="ANTHROPIC_API_KEY")
    openai_api_key: str = Field(default="", alias="OPENAI_API_KEY")
    google_api_key: str = Field(default="", alias="GOOGLE_API_KEY")
    claude_model: str = Field(default="claude-opus-4-6", alias="CLAUDE_MODEL")
    openai_model: str = Field(default="gpt-5.2-chat-latest", alias="OPENAI_MODEL")
    gemini_model: str = Field(default="gemini-3-pro-preview", alias="GEMINI_MODEL")

    model_config = {"env_file": ".env", "extra": "ignore"}


class TelegramSettings(BaseSettings):
    """텔레그램 알림 설정"""
    bot_token: str = Field(default="", alias="TELEGRAM_BOT_TOKEN")
    chat_id: str = Field(default="", alias="TELEGRAM_CHAT_ID")

    model_config = {"env_file": ".env", "extra": "ignore"}


class RossCameronSettings(BaseSettings):
    """로스 카메론 전략 파라미터"""
    # 갭업 스캐너 조건
    min_gap_pct: float = 4.0          # 최소 갭업 비율 (%)
    min_volume_ratio: float = 2.0     # 최소 상대 거래량 배수
    min_price: int = 2_000            # 최소 주가 (원) - 한국시장 기준
    max_price: int = 50_000           # 최대 주가 (원) - 한국시장 기준
    max_market_cap: int = 500_000_000_000  # 최대 시가총액 5000억원

    # 진입 조건
    vwap_entry: bool = True           # VWAP 위에서만 진입
    use_moving_avg: bool = True       # 이동평균선 확인
    ma_periods: list[int] = [9, 20]   # 이동평균 기간

    # 리스크 관리
    reward_risk_ratio: float = 2.0    # 최소 보상/위험 비율
    stop_loss_pct: float = 2.0        # 손절 비율 (%)
    take_profit_pct: float = 4.0      # 익절 비율 (%)
    max_hold_minutes: int = 60        # 최대 보유 시간 (분)
    trailing_stop_pct: float = 1.5    # 트레일링 스탑 (%)

    # 시간 필터
    trading_start: str = "09:00"      # 매매 시작 시간
    trading_end: str = "15:00"        # 매매 종료 시간
    prime_time_start: str = "09:00"   # 핵심 시간대 시작
    prime_time_end: str = "10:30"     # 핵심 시간대 종료 (로스 카메론: 첫 1~2시간 집중)

    model_config = {"env_file": ".env", "extra": "ignore"}


# 싱글턴 인스턴스
kis_settings = KISSettings()
trading_settings = TradingSettings()
ai_settings = AISettings()
telegram_settings = TelegramSettings()
ross_settings = RossCameronSettings()
