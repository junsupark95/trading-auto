"""AI 모멘텀 트레이딩 시스템 - 메인 실행 파일

실행 방법:
    python main.py              # 자동 매매 시작
    python main.py --scan-only  # 스캔만 실행 (매매 X)
    python main.py --report     # 일일 리포트만 생성

대시보드 (별도 터미널):
    streamlit run dashboard/app.py
"""

import argparse
import json
import signal
import sys
import time
from datetime import datetime
from pathlib import Path

from loguru import logger
import pytz

from core.trading_engine import TradingEngine
from utils.market_hours import (
    is_market_open,
    is_pre_market,
    is_prime_time,
    seconds_until_market_open,
    now_kst,
)

KST = pytz.timezone("Asia/Seoul")

# ========== 로그 설정 ==========
logger.remove()
logger.add(
    sys.stdout,
    format="<green>{time:HH:mm:ss}</green> | <level>{level: <8}</level> | {message}",
    level="INFO",
)
logger.add(
    "logs/trading_{time:YYYYMMDD}.log",
    rotation="1 day",
    retention="30 days",
    format="{time:YYYY-MM-DD HH:mm:ss} | {level: <8} | {message}",
    level="DEBUG",
)


class TradingApp:
    """메인 트레이딩 애플리케이션"""

    def __init__(self):
        self.engine = TradingEngine()
        self._shutdown = False

    def run(self, scan_only: bool = False):
        """메인 매매 루프"""
        signal.signal(signal.SIGINT, self._signal_handler)
        signal.signal(signal.SIGTERM, self._signal_handler)

        logger.info("=" * 60)
        logger.info("  AI 모멘텀 트레이딩 시스템 v1.0")
        logger.info("  전략: Ross Cameron Momentum Day Trading")
        logger.info("  AI: Claude(매매) + GPT(분석) + Gemini(검증)")
        logger.info("=" * 60)

        self.engine.start()

        if not self.engine.is_running:
            logger.error("엔진 시작 실패")
            return

        try:
            self._main_loop(scan_only)
        except Exception as e:
            logger.exception(f"치명적 오류: {e}")
        finally:
            self._shutdown_sequence()

    def _main_loop(self, scan_only: bool):
        """메인 루프"""
        scan_interval = 300       # 5분마다 스캔
        entry_interval = 30       # 30초마다 진입 검토
        exit_interval = 10        # 10초마다 청산 검토
        dashboard_interval = 5    # 5초마다 대시보드 갱신

        last_scan = 0
        last_entry = 0
        last_exit = 0
        last_dashboard = 0
        market_open_scanned = False

        while not self._shutdown:
            now = time.time()

            # 장 시작 전 대기
            if not is_market_open() and not is_pre_market():
                wait = seconds_until_market_open()
                if wait > 0 and wait < 43200:  # 12시간 이내
                    logger.info(f"장 시작까지 {wait // 60}분 {wait % 60}초 대기...")
                    time.sleep(min(wait, 60))
                    continue
                else:
                    # 장 종료 후 → 일일 리포트 생성 후 종료
                    if self.engine.trade_log:
                        logger.info("장 마감 후 일일 리포트 생성...")
                        self.engine.generate_daily_report()
                    logger.info("장 종료. 내일 다시 시작합니다.")
                    break

            # 프리마켓: 스캔만 실행
            if is_pre_market() and not market_open_scanned:
                logger.info("프리마켓 스캔 시작...")
                self.engine.run_scan_cycle()
                market_open_scanned = True
                self._save_dashboard_state()
                time.sleep(30)
                continue

            # 장중 스캔 (5분 간격)
            if now - last_scan >= scan_interval:
                self.engine.run_scan_cycle()
                last_scan = now

            # 매수 진입 (30초 간격, 핵심 시간대에는 15초)
            current_entry_interval = 15 if is_prime_time() else entry_interval
            if not scan_only and now - last_entry >= current_entry_interval:
                self.engine.run_entry_cycle()
                last_entry = now

            # 매도 청산 (10초 간격)
            if not scan_only and now - last_exit >= exit_interval:
                self.engine.run_exit_cycle()
                last_exit = now

            # 대시보드 갱신 (5초 간격)
            if now - last_dashboard >= dashboard_interval:
                self._save_dashboard_state()
                last_dashboard = now

            time.sleep(1)

    def _save_dashboard_state(self):
        """대시보드용 상태 파일 저장"""
        try:
            state = self.engine.get_dashboard_data()
            state_file = Path("logs/dashboard_state.json")
            with open(state_file, "w", encoding="utf-8") as f:
                json.dump(state, f, ensure_ascii=False, indent=2, default=str)
        except Exception as e:
            logger.debug(f"대시보드 상태 저장 실패: {e}")

    def _signal_handler(self, signum, frame):
        """종료 시그널 핸들러"""
        logger.info(f"종료 시그널 수신 ({signum})")
        self._shutdown = True

    def _shutdown_sequence(self):
        """종료 시퀀스"""
        logger.info("종료 시퀀스 시작...")

        # 미체결 포지션 경고
        if self.engine.position_mgr.open_count > 0:
            logger.warning(
                f"미청산 포지션 {self.engine.position_mgr.open_count}개 있음! "
                "수동 확인 필요."
            )
            for pos in self.engine.position_mgr.positions.values():
                logger.warning(
                    f"  - {pos.stock_name}: {pos.qty}주 "
                    f"(수익률: {pos.pnl_pct:+.2f}%)"
                )

        # 일일 리포트 생성
        if self.engine.trade_log:
            logger.info("일일 리포트 생성 중...")
            try:
                self.engine.generate_daily_report()
            except Exception as e:
                logger.error(f"리포트 생성 실패: {e}")

        self.engine.stop()
        logger.info("시스템 종료 완료")


def run_report_only():
    """리포트만 생성"""
    engine = TradingEngine()
    engine.start()
    report = engine.generate_daily_report()
    print(json.dumps(report, ensure_ascii=False, indent=2, default=str))


def main():
    parser = argparse.ArgumentParser(description="AI 모멘텀 트레이딩 시스템")
    parser.add_argument(
        "--scan-only", action="store_true",
        help="종목 스캔만 실행 (매매 X)",
    )
    parser.add_argument(
        "--report", action="store_true",
        help="일일 리포트만 생성",
    )
    args = parser.parse_args()

    if args.report:
        run_report_only()
    else:
        app = TradingApp()
        app.run(scan_only=args.scan_only)


if __name__ == "__main__":
    main()
