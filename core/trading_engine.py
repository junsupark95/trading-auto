"""핵심 트레이딩 엔진

모든 모듈을 통합하여 자동 매매 루프를 실행합니다.
1. 스캐너로 갭업 종목 탐색
2. AI(GPT+Gemini)로 종목 선정
3. 전략 엔진이 진입/청산 신호 생성
4. AI(Claude)가 최종 매매 결정
5. KIS API로 주문 실행
"""

import json
import time
from datetime import datetime
from pathlib import Path
from loguru import logger
import pytz

from config.settings import trading_settings, ross_settings
from api.kis_auth import KISAuth
from api.kis_market import KISMarket
from api.kis_order import KISOrder
from strategy.scanner import GapUpScanner
from strategy.ross_cameron import RossCameronStrategy
from strategy.indicators import TechnicalIndicators
from core.position_manager import PositionManager
from core.risk_manager import RiskManager
from ai.trade_executor import ClaudeTradeExecutor
from ai.stock_analyst import AIStockAnalyst
from ai.report_generator import DailyReportGenerator

KST = pytz.timezone("Asia/Seoul")


class TradingEngine:
    """메인 트레이딩 엔진"""

    def __init__(self):
        # API
        self.auth = KISAuth()
        self.market = KISMarket(self.auth)
        self.order = KISOrder(self.auth)

        # 전략
        self.scanner = GapUpScanner(self.market)
        self.strategy = RossCameronStrategy()

        # 포지션 & 리스크
        self.position_mgr = PositionManager()
        self.risk_mgr = RiskManager(self.position_mgr)

        # AI
        self.claude = ClaudeTradeExecutor()
        self.analyst = AIStockAnalyst()
        self.reporter = DailyReportGenerator()

        # 상태
        self.candidates: list[dict] = []
        self.selected_stocks: list[dict] = []
        self.trade_log: list[dict] = []
        self.is_running = False
        self.last_scan_time: datetime | None = None

        # 로그 디렉토리
        Path("logs").mkdir(exist_ok=True)

    def start(self):
        """트레이딩 엔진 시작"""
        logger.info("=" * 60)
        logger.info("트레이딩 엔진 시작")
        logger.info(f"환경: {'실전' if self.auth.base_url.find('vts') == -1 else '모의투자'}")
        logger.info(f"일일 투자 한도: {trading_settings.max_daily_capital:,}원")
        logger.info(f"일일 손실 한도: {trading_settings.max_daily_loss:,}원")
        logger.info("=" * 60)

        self.is_running = True
        self._authenticate()

    def stop(self):
        """엔진 종료"""
        self.is_running = False
        logger.info("트레이딩 엔진 종료")

    def _authenticate(self):
        """API 인증"""
        try:
            self.auth.get_token()
            logger.info("KIS API 인증 성공")
        except Exception as e:
            logger.error(f"KIS API 인증 실패: {e}")
            self.is_running = False

    # ========== 매매 사이클 ==========

    def run_scan_cycle(self) -> list[dict]:
        """종목 스캔 사이클"""
        logger.info("--- 종목 스캔 시작 ---")

        # 1) 갭업 스캐너 실행
        self.candidates = self.scanner.scan()
        scanner_summary = self.scanner.get_scanner_summary(self.candidates)

        if not self.candidates:
            logger.info("갭업 후보 종목 없음")
            return []

        # 2) AI 종목 분석 (GPT + Gemini)
        try:
            analysis = self.analyst.analyze_candidates(scanner_summary)
            self.selected_stocks = analysis.get("final_picks", [])
            logger.info(
                f"AI 종목 선정: {len(self.selected_stocks)}개 "
                f"(시장 개요: {analysis.get('market_overview', '')[:100]})"
            )
        except Exception as e:
            logger.error(f"AI 종목 분석 실패: {e}")
            # AI 실패 시 스캐너 상위 5개를 그대로 사용
            self.selected_stocks = [
                {"stock_code": c["stock_code"], "stock_name": c.get("name", "")}
                for c in self.candidates[:5]
            ]

        self.last_scan_time = datetime.now(KST)
        return self.selected_stocks

    def run_entry_cycle(self):
        """매수 진입 사이클"""
        allowed, reason = self.risk_mgr.is_trading_allowed()
        if not allowed:
            logger.warning(f"매매 불가: {reason}")
            return

        for stock in self.selected_stocks:
            code = stock.get("stock_code", "")
            name = stock.get("stock_name", stock.get("name", ""))

            if not code or self.position_mgr.has_position(code):
                continue

            try:
                self._evaluate_and_enter(code, name)
            except Exception as e:
                logger.error(f"진입 분석 오류 ({name}): {e}")

            time.sleep(0.5)  # API 호출 간격

    def _evaluate_and_enter(self, stock_code: str, stock_name: str):
        """개별 종목 진입 평가 및 실행"""
        # 1) 현재가 조회
        price_data = self.market.get_current_price(stock_code)
        current_price = price_data["price"]
        if current_price == 0:
            return

        # 2) 분봉 데이터 조회
        df = self.market.get_minute_chart(stock_code)

        # 3) 전략 엔진 분석
        signal = self.strategy.analyze_entry(
            stock_code, stock_name, df, current_price
        )

        if signal.action != "BUY":
            logger.debug(f"전략 관망: {stock_name} - {signal.reason}")
            return

        # 4) 호가 조회
        orderbook = self.market.get_orderbook(stock_code)

        # 5) Claude AI 최종 판단
        cash = self.order.get_cash_balance()
        context = {
            "stock_code": stock_code,
            "stock_name": stock_name,
            "current_price": current_price,
            "strategy_signal": signal.to_dict(),
            "chart_summary": self._build_chart_summary(df, price_data),
            "orderbook": orderbook,
            "market_condition": "",
            "available_capital": cash,
            "current_positions": [
                p.to_dict() for p in self.position_mgr.positions.values()
            ],
            "daily_pnl": self.position_mgr.realized_pnl,
        }

        ai_decision = self.claude.decide_entry(context)

        if ai_decision.get("decision") != "BUY":
            logger.info(
                f"Claude 관망: {stock_name} - {ai_decision.get('reasoning', '')[:100]}"
            )
            return

        if ai_decision.get("confidence", 0) < 0.6:
            logger.info(f"Claude 신뢰도 부족: {stock_name} ({ai_decision.get('confidence', 0):.0%})")
            return

        # 6) 포지션 사이즈 계산
        qty = self.strategy.get_position_size(
            capital=min(cash, trading_settings.max_daily_capital),
            current_price=current_price,
            stop_loss=signal.stop_loss,
        )
        qty = self.risk_mgr.get_adjusted_position_size(qty)

        if qty <= 0:
            return

        # 7) 리스크 체크
        amount = current_price * qty
        can_open, msg = self.risk_mgr.can_open_position(stock_code, amount)
        if not can_open:
            logger.warning(f"리스크 제한: {stock_name} - {msg}")
            return

        # 8) 주문 실행
        result = self.order.buy_market(stock_code, qty)

        if result.get("success"):
            pos = self.position_mgr.open_position(
                stock_code=stock_code,
                stock_name=stock_name,
                qty=qty,
                entry_price=current_price,
                stop_loss=ai_decision.get("suggested_stop_loss", signal.stop_loss),
                take_profit=ai_decision.get("suggested_take_profit", signal.take_profit),
                order_no=result.get("order_no", ""),
                ai_reasoning=ai_decision.get("reasoning", ""),
            )
            self._log_trade("BUY", pos.to_dict(), ai_decision)
        else:
            logger.error(f"매수 실패: {stock_name} - {result.get('error')}")

    def run_exit_cycle(self):
        """매도 청산 사이클"""
        for stock_code, pos in list(self.position_mgr.positions.items()):
            try:
                self._evaluate_and_exit(pos)
            except Exception as e:
                logger.error(f"청산 분석 오류 ({pos.stock_name}): {e}")
            time.sleep(0.3)

    def _evaluate_and_exit(self, pos):
        """개별 포지션 청산 평가 및 실행"""
        # 1) 현재가 업데이트
        price_data = self.market.get_current_price(pos.stock_code)
        current_price = price_data["price"]
        pos.update_price(current_price)

        # 2) 분봉 데이터
        df = self.market.get_minute_chart(pos.stock_code)

        # 3) 전략 청산 신호
        signal = self.strategy.check_exit(
            stock_code=pos.stock_code,
            entry_price=pos.entry_price,
            current_price=current_price,
            highest_since_entry=pos.highest_price,
            minutes_held=pos.minutes_held,
            df=df,
        )

        # 손절/익절/트레일링 스탑은 AI 판단 없이 즉시 실행
        if signal.action == "SELL" and signal.confidence >= 0.85:
            self._execute_exit(pos, current_price, signal.reason)
            return

        # 그 외 상황에서는 Claude 판단
        if signal.action == "SELL" or pos.minutes_held > ross_settings.max_hold_minutes * 0.7:
            context = {
                "stock_code": pos.stock_code,
                "stock_name": pos.stock_name,
                "entry_price": pos.entry_price,
                "current_price": current_price,
                "qty": pos.qty,
                "pnl_pct": pos.pnl_pct,
                "minutes_held": pos.minutes_held,
                "strategy_signal": signal.to_dict(),
                "chart_summary": self._build_chart_summary(df, price_data),
            }

            ai_decision = self.claude.decide_exit(context)

            if ai_decision.get("decision") == "SELL" and ai_decision.get("confidence", 0) >= 0.6:
                reason = f"Claude 판단: {ai_decision.get('reasoning', '')[:100]}"
                self._execute_exit(pos, current_price, reason)

    def _execute_exit(self, pos, price: int, reason: str):
        """매도 실행"""
        result = self.order.sell_market(pos.stock_code, pos.qty)
        if result.get("success"):
            trade = self.position_mgr.close_position(pos.stock_code, price, reason)
            if trade:
                self.risk_mgr.update_on_trade_close(trade["realized_pnl"])
                self._log_trade("SELL", trade, {"reasoning": reason})
        else:
            logger.error(f"매도 실패: {pos.stock_name} - {result.get('error')}")

    # ========== 일일 리포트 ==========

    def generate_daily_report(self) -> dict:
        """일일 리포트 생성"""
        today = datetime.now(KST).strftime("%Y-%m-%d")
        summary = self.position_mgr.get_summary()

        trading_data = {
            "date": today,
            "candidates": self.candidates[:10],
            "selected_stocks": self.selected_stocks,
            "trades": self.trade_log,
            "positions": summary["open_positions"],
            "daily_pnl": summary["realized_pnl"],
            "total_trades": summary["total_trades"],
            "winning_trades": summary["winning_trades"],
            "win_rate": summary["win_rate"],
            "risk_status": self.risk_mgr.get_status(),
        }

        return self.reporter.generate(trading_data)

    # ========== 유틸리티 ==========

    def _build_chart_summary(self, df, price_data: dict) -> str:
        """차트 데이터 텍스트 요약 (AI 프롬프트용)"""
        if df is None or df.empty:
            return "차트 데이터 없음"

        df = TechnicalIndicators.compute_all(df)
        latest = df.iloc[-1]

        lines = [
            f"현재가: {price_data.get('price', 0):,}원",
            f"등락률: {price_data.get('change_pct', 0):+.2f}%",
            f"거래량: {price_data.get('volume', 0):,}",
            f"고가: {price_data.get('high', 0):,} / 저가: {price_data.get('low', 0):,}",
            f"시가: {price_data.get('open', 0):,}",
            f"VWAP: {latest.get('vwap', 0):,.0f}",
            f"9EMA: {latest.get('ema_9', 0):,.0f}",
            f"20EMA: {latest.get('ema_20', 0):,.0f}",
            f"ATR: {latest.get('atr', 0):,.0f}",
        ]
        return " | ".join(lines)

    def _log_trade(self, side: str, trade_data: dict, ai_data: dict):
        """거래 로그 기록"""
        log_entry = {
            "timestamp": datetime.now(KST).isoformat(),
            "side": side,
            "trade": trade_data,
            "ai_decision": ai_data,
        }
        self.trade_log.append(log_entry)

        # 파일 로그
        log_file = Path("logs") / f"trades_{datetime.now(KST).strftime('%Y%m%d')}.json"
        try:
            existing = []
            if log_file.exists():
                with open(log_file, encoding="utf-8") as f:
                    existing = json.load(f)
            existing.append(log_entry)
            with open(log_file, "w", encoding="utf-8") as f:
                json.dump(existing, f, ensure_ascii=False, indent=2, default=str)
        except Exception as e:
            logger.error(f"거래 로그 저장 실패: {e}")

    def get_dashboard_data(self) -> dict:
        """대시보드용 실시간 데이터"""
        return {
            "is_running": self.is_running,
            "timestamp": datetime.now(KST).isoformat(),
            "positions": self.position_mgr.get_summary(),
            "risk": self.risk_mgr.get_status(),
            "candidates": self.candidates[:10],
            "selected_stocks": self.selected_stocks,
            "trade_log": self.trade_log[-20:],
            "last_scan_time": self.last_scan_time.isoformat() if self.last_scan_time else None,
        }
