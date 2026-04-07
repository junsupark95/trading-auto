"""로스 카메론 모멘텀 데이 트레이딩 전략 엔진"""

from datetime import datetime
from loguru import logger
from config.settings import ross_settings
from strategy.indicators import TechnicalIndicators
import pandas as pd
import pytz

KST = pytz.timezone("Asia/Seoul")


class TradeSignal:
    """트레이딩 신호"""
    BUY = "BUY"
    SELL = "SELL"
    HOLD = "HOLD"

    def __init__(self, action: str, stock_code: str, reason: str,
                 confidence: float = 0.0, entry_price: int = 0,
                 stop_loss: int = 0, take_profit: int = 0):
        self.action = action
        self.stock_code = stock_code
        self.reason = reason
        self.confidence = confidence  # 0.0 ~ 1.0
        self.entry_price = entry_price
        self.stop_loss = stop_loss
        self.take_profit = take_profit
        self.timestamp = datetime.now(KST)

    def to_dict(self) -> dict:
        return {
            "action": self.action,
            "stock_code": self.stock_code,
            "reason": self.reason,
            "confidence": self.confidence,
            "entry_price": self.entry_price,
            "stop_loss": self.stop_loss,
            "take_profit": self.take_profit,
            "timestamp": self.timestamp.isoformat(),
        }


class RossCameronStrategy:
    """로스 카메론 전략 엔진

    핵심 원칙:
    1. 갭업 종목 중 거래량 급증 종목 선별
    2. VWAP 위에서만 롱 진입
    3. 첫 1~2시간(09:00~10:30)에 집중 매매
    4. 2:1 이상 보상/위험 비율 확보
    5. 엄격한 손절라인 (진입가 대비 2%)
    6. 트레일링 스탑으로 수익 보호
    """

    def __init__(self):
        self.settings = ross_settings
        self.indicators = TechnicalIndicators()

    def analyze_entry(self, stock_code: str, stock_name: str,
                      df: pd.DataFrame, current_price: int,
                      price_data: dict = None) -> TradeSignal:
        """매수 진입 분석

        로스 카메론 진입 조건:
        1. VWAP 위
        2. 9EMA 위
        3. 거래량 확인
        4. 적절한 시간대
        5. 캔들 패턴 확인
        """
        if df is None or df.empty or len(df) < 5:
            # 분봉 없을 때 현재가 데이터로 간략 분석 (모의투자 API 500 오류 대비)
            if price_data:
                return self._analyze_entry_no_chart(stock_code, stock_name, current_price, price_data)
            return TradeSignal(TradeSignal.HOLD, stock_code, "데이터 부족")

        # 지표 계산
        df = self.indicators.compute_all(df, self.settings.ma_periods)
        latest = df.iloc[-1]

        reasons = []
        score = 0.0

        # 1) 시간대 확인
        now = datetime.now(KST)
        prime_start = datetime.strptime(self.settings.prime_time_start, "%H:%M").time()
        prime_end = datetime.strptime(self.settings.prime_time_end, "%H:%M").time()
        trading_end = datetime.strptime(self.settings.trading_end, "%H:%M").time()

        if now.time() > trading_end:
            return TradeSignal(TradeSignal.HOLD, stock_code, "매매 시간 종료")

        if prime_start <= now.time() <= prime_end:
            score += 0.15
            reasons.append("핵심 시간대(09:00~10:30)")
        else:
            reasons.append("핵심 시간대 외")

        # 2) VWAP 위 확인
        vwap = latest.get("vwap", 0)
        if vwap > 0 and current_price > vwap:
            score += 0.25
            reasons.append(f"VWAP({vwap:,.0f}) 위")
        elif vwap > 0:
            reasons.append(f"VWAP({vwap:,.0f}) 아래 - 진입 부적합")
            return TradeSignal(TradeSignal.HOLD, stock_code,
                               " | ".join(reasons), confidence=score)

        # 3) 9EMA 위 확인
        ema9 = latest.get("ema_9", 0)
        if ema9 > 0 and current_price > ema9:
            score += 0.2
            reasons.append(f"9EMA({ema9:,.0f}) 위 - 단기 상승세")
        else:
            score -= 0.1
            reasons.append(f"9EMA 아래 - 약세")

        # 4) 20EMA 확인 (추가 확인)
        ema20 = latest.get("ema_20", 0)
        if ema20 > 0 and ema9 > ema20:
            score += 0.1
            reasons.append("9EMA > 20EMA 골든크로스")

        # 5) 캔들 강도
        if len(df) >= 2:
            prev = df.iloc[-2]
            if self.indicators.is_bullish_candle(latest):
                body_ratio = self.indicators.candle_body_ratio(latest)
                if body_ratio > 0.6:
                    score += 0.15
                    reasons.append(f"강한 양봉 (몸통비율: {body_ratio:.0%})")
                else:
                    score += 0.05
                    reasons.append("양봉")

            # 연속 양봉 확인
            if (self.indicators.is_bullish_candle(latest) and
                    self.indicators.is_bullish_candle(prev)):
                score += 0.1
                reasons.append("연속 양봉 모멘텀")

        # 6) 거래량 확인
        rel_vol = self.indicators.relative_volume(df)
        if rel_vol >= self.settings.min_volume_ratio:
            score += 0.15
            reasons.append(f"상대거래량 {rel_vol:.1f}x (기준: {self.settings.min_volume_ratio}x)")
        else:
            score -= 0.1
            reasons.append(f"거래량 부족 ({rel_vol:.1f}x)")

        # 손절/익절 계산 (int 반올림으로 R:R이 2:1 미달하지 않도록 floor/ceil 사용)
        import math
        atr = latest.get("atr", 0)
        if atr > 0:
            stop_loss = math.floor(current_price - (atr * 1.5))   # 낮게 → 위험 확보
            take_profit = math.ceil(current_price + (atr * 3.0))  # 높게 → 보상 확보
        else:
            stop_loss = math.floor(current_price * (1 - self.settings.stop_loss_pct / 100))
            take_profit = math.ceil(current_price * (1 + self.settings.take_profit_pct / 100))

        # 보상/위험 비율 확인
        risk = current_price - stop_loss
        reward = take_profit - current_price
        if risk > 0:
            rr_ratio = reward / risk
            if rr_ratio >= self.settings.reward_risk_ratio:
                score += 0.1
                reasons.append(f"R:R = {rr_ratio:.1f}:1 ✓")
            else:
                score -= 0.1
                reasons.append(f"R:R = {rr_ratio:.1f}:1 (기준 미달)")

        # 최종 판단
        score = max(0.0, min(1.0, score))

        if score >= 0.6:
            action = TradeSignal.BUY
            reasons.insert(0, f"[매수 신호] {stock_name}")
        else:
            action = TradeSignal.HOLD
            reasons.insert(0, f"[관망] {stock_name}")

        return TradeSignal(
            action=action,
            stock_code=stock_code,
            reason=" | ".join(reasons),
            confidence=score,
            entry_price=current_price,
            stop_loss=stop_loss,
            take_profit=take_profit,
        )

    def check_exit(self, stock_code: str, entry_price: int,
                   current_price: int, highest_since_entry: int,
                   minutes_held: int, df: pd.DataFrame = None) -> TradeSignal:
        """청산 조건 확인

        로스 카메론 청산 규칙:
        1. 손절: 진입가 대비 -2%
        2. 익절: 진입가 대비 +4% (또는 목표가 도달)
        3. 트레일링 스탑: 고점 대비 -1.5%
        4. 시간 제한: 최대 60분 보유
        5. VWAP 하향 돌파 시 청산
        """
        reasons = []

        # 1) 손절
        stop_pct = self.settings.stop_loss_pct
        if current_price <= entry_price * (1 - stop_pct / 100):
            loss_pct = (current_price - entry_price) / entry_price * 100
            return TradeSignal(
                TradeSignal.SELL, stock_code,
                f"손절: {loss_pct:+.2f}% (기준: -{stop_pct}%)",
                confidence=1.0,
            )

        # 2) 익절
        profit_pct_val = (current_price - entry_price) / entry_price * 100
        if profit_pct_val >= self.settings.take_profit_pct:
            return TradeSignal(
                TradeSignal.SELL, stock_code,
                f"익절: +{profit_pct_val:.2f}% (목표: +{self.settings.take_profit_pct}%)",
                confidence=0.9,
            )

        # 3) 트레일링 스탑
        if highest_since_entry > entry_price:
            trailing_stop = highest_since_entry * (1 - self.settings.trailing_stop_pct / 100)
            if current_price <= trailing_stop:
                return TradeSignal(
                    TradeSignal.SELL, stock_code,
                    f"트레일링 스탑: 고점 {highest_since_entry:,} → 현재 {current_price:,} "
                    f"(-{self.settings.trailing_stop_pct}%)",
                    confidence=0.85,
                )

        # 4) 시간 제한
        if minutes_held >= self.settings.max_hold_minutes:
            return TradeSignal(
                TradeSignal.SELL, stock_code,
                f"보유 시간 초과: {minutes_held}분 (최대: {self.settings.max_hold_minutes}분)",
                confidence=0.7,
            )

        # 5) VWAP 하향 돌파 확인
        if df is not None and not df.empty:
            df = self.indicators.compute_all(df)
            vwap = df.iloc[-1].get("vwap", 0)
            if vwap > 0 and current_price < vwap and profit_pct_val > 0:
                return TradeSignal(
                    TradeSignal.SELL, stock_code,
                    f"VWAP 하향 돌파 (VWAP: {vwap:,.0f}, 현재: {current_price:,})",
                    confidence=0.75,
                )

        return TradeSignal(TradeSignal.HOLD, stock_code, "보유 유지")

    def _analyze_entry_no_chart(self, stock_code: str, stock_name: str,
                                current_price: int, price_data: dict) -> TradeSignal:
        """분봉 데이터 없을 때 현재가 정보만으로 간략 진입 분석"""
        import math
        reasons = []
        score = 0.0

        # 시간대 확인
        now = datetime.now(KST)
        prime_start = datetime.strptime(self.settings.prime_time_start, "%H:%M").time()
        prime_end = datetime.strptime(self.settings.prime_time_end, "%H:%M").time()
        trading_end = datetime.strptime(self.settings.trading_end, "%H:%M").time()

        if now.time() > trading_end:
            return TradeSignal(TradeSignal.HOLD, stock_code, "매매 시간 종료")

        if prime_start <= now.time() <= prime_end:
            score += 0.2
            reasons.append("핵심 시간대")
        else:
            reasons.append("핵심 시간대 외")

        # 갭업 강도
        change_pct = float(price_data.get("change_pct", 0))
        if change_pct >= self.settings.min_gap_pct * 2:
            score += 0.25
            reasons.append(f"강한 갭업 {change_pct:+.1f}%")
        elif change_pct >= self.settings.min_gap_pct:
            score += 0.15
            reasons.append(f"갭업 {change_pct:+.1f}%")

        # 장중 추세: 현재가 > 시가
        open_price = int(price_data.get("open", 0))
        if open_price > 0 and current_price > open_price:
            score += 0.2
            reasons.append(f"시가({open_price:,}) 위 — 상승 모멘텀")
        elif open_price > 0:
            score -= 0.1
            reasons.append(f"시가({open_price:,}) 아래")

        # 고가 근접 여부 (고가 대비 3% 이내)
        high = int(price_data.get("high", 0))
        if high > 0 and current_price >= high * 0.97:
            score += 0.15
            reasons.append("당일 고가 근접")

        # 손절/익절 (ATR 없으므로 % 기반)
        stop_loss = math.floor(current_price * (1 - self.settings.stop_loss_pct / 100))
        take_profit = math.ceil(current_price * (1 + self.settings.take_profit_pct / 100))

        score = max(0.0, min(1.0, score))
        # 분봉 없이 분석한 경우 BUY 임계값을 0.55로 낮춤
        action = TradeSignal.BUY if score >= 0.55 else TradeSignal.HOLD
        prefix = "[매수 신호·차트미사용]" if action == TradeSignal.BUY else "[관망·차트미사용]"

        return TradeSignal(
            action=action,
            stock_code=stock_code,
            reason=f"{prefix} {stock_name} | " + " | ".join(reasons),
            confidence=score,
            entry_price=current_price,
            stop_loss=stop_loss,
            take_profit=take_profit,
        )

    def get_position_size(self, capital: int, current_price: int,
                          stop_loss: int) -> int:
        """포지션 사이즈 계산 (리스크 기반)

        로스 카메론: 1회 거래 최대 손실을 자본의 1~2%로 제한
        """
        max_risk_per_trade = capital * 0.02  # 자본의 2%
        risk_per_share = current_price - stop_loss

        if risk_per_share <= 0:
            return 0

        qty = int(max_risk_per_trade / risk_per_share)

        # 종목당 최대 투자 비중 확인
        max_amount = capital * (self.settings.reward_risk_ratio / 10)  # ~20%
        max_qty_by_capital = int(max_amount / current_price)

        return min(qty, max_qty_by_capital, 999)  # 최소 안전장치
