"""텔레그램 봇 실시간 알림 모듈"""

import requests
from loguru import logger
from config.settings import telegram_settings


class TelegramNotifier:
    """텔레그램 봇 알림 전송"""

    def __init__(self):
        self.token = telegram_settings.bot_token
        self.chat_id = telegram_settings.chat_id
        self.enabled = bool(self.token and self.chat_id)
        if not self.enabled:
            logger.warning("TELEGRAM_BOT_TOKEN 또는 TELEGRAM_CHAT_ID 미설정: 텔레그램 알림 비활성화")

    def send(self, message: str):
        """메시지 전송"""
        if not self.enabled:
            return
        url = f"https://api.telegram.org/bot{self.token}/sendMessage"
        try:
            resp = requests.post(
                url,
                json={"chat_id": self.chat_id, "text": message, "parse_mode": "HTML"},
                timeout=10,
            )
            if not resp.ok:
                logger.warning(f"텔레그램 전송 실패: {resp.status_code} {resp.text[:200]}")
        except Exception as e:
            logger.warning(f"텔레그램 전송 오류: {e}")

    def notify_engine_start(self, environment: str, max_capital: int, max_loss: int):
        msg = (
            f"🚀 <b>트레이딩 봇 시작</b>\n"
            f"환경: {environment}\n"
            f"일일 투자 한도: {max_capital:,}원\n"
            f"일일 손실 한도: {max_loss:,}원"
        )
        self.send(msg)

    def notify_scan_result(self, selected_stocks: list[dict]):
        if not selected_stocks:
            return
        names = ", ".join(
            s.get("stock_name", s.get("name", s.get("stock_code", "")))
            for s in selected_stocks[:10]
        )
        msg = (
            f"🔍 <b>AI 종목 선정 완료</b>\n"
            f"선정 종목 ({len(selected_stocks)}개): {names}"
        )
        self.send(msg)

    def notify_buy(
        self,
        stock_name: str,
        stock_code: str,
        qty: int,
        entry_price: int,
        stop_loss: int,
        take_profit: int,
        reasoning: str,
    ):
        amount = entry_price * qty
        msg = (
            f"🟢 <b>매수 체결</b>\n"
            f"종목: {stock_name} ({stock_code})\n"
            f"가격: {entry_price:,}원 × {qty}주 = {amount:,}원\n"
            f"손절: {stop_loss:,}원 | 익절: {take_profit:,}원\n"
            f"AI 판단: {reasoning[:200]}"
        )
        self.send(msg)

    def notify_sell(
        self,
        stock_name: str,
        stock_code: str,
        qty: int,
        entry_price: int,
        exit_price: int,
        realized_pnl: int,
        realized_pnl_pct: float,
        reason: str,
    ):
        emoji = "🔴" if realized_pnl < 0 else "💰"
        sign = "+" if realized_pnl >= 0 else ""
        msg = (
            f"{emoji} <b>매도 체결</b>\n"
            f"종목: {stock_name} ({stock_code})\n"
            f"진입: {entry_price:,}원 → 청산: {exit_price:,}원\n"
            f"수량: {qty}주 | 손익: {sign}{realized_pnl:,}원 ({sign}{realized_pnl_pct:.2f}%)\n"
            f"이유: {reason[:200]}"
        )
        self.send(msg)

    def notify_daily_report(
        self,
        date: str,
        total_trades: int,
        winning_trades: int,
        win_rate: float,
        daily_pnl: int,
        grade: str,
    ):
        sign = "+" if daily_pnl >= 0 else ""
        emoji = "📈" if daily_pnl >= 0 else "📉"
        msg = (
            f"{emoji} <b>일일 리포트 ({date})</b>\n"
            f"총 거래: {total_trades}건 | 수익: {winning_trades}건 | 승률: {win_rate:.1f}%\n"
            f"일일 손익: {sign}{daily_pnl:,}원\n"
            f"평가 등급: {grade}"
        )
        self.send(msg)

    def notify_risk_halt(self, reason: str):
        msg = f"⚠️ <b>리스크 제한 - 매매 중단</b>\n사유: {reason}"
        self.send(msg)
