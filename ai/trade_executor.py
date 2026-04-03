"""Claude AI 기반 매매 실행 판단 모듈

Claude Opus를 사용하여 최종 매수/매도 결정을 내립니다.
로스 카메론 전략 신호 + 시장 컨텍스트를 종합 분석합니다.
"""

import json
import anthropic
from loguru import logger
from config.settings import ai_settings


TRADE_SYSTEM_PROMPT = """당신은 로스 카메론(Ross Cameron)의 모멘텀 데이 트레이딩 전략을 기반으로
한국 주식시장에서 매매 결정을 내리는 전문 트레이딩 AI입니다.

## 핵심 원칙
1. **자본 보존 최우선**: 손실을 최소화하고, 확실한 기회에만 진입
2. **2:1 보상/위험 비율**: 최소 보상이 위험의 2배 이상일 때만 진입
3. **VWAP 준수**: VWAP 위에서만 롱 진입
4. **첫 1~2시간 집중**: 09:00~10:30이 최적 매매 시간대
5. **엄격한 손절**: 진입가 대비 -2% 이하에서 무조건 손절
6. **오버트레이딩 금지**: 하루 최대 3~5회 거래

## 판단 기준
- 기술적 지표 (VWAP, EMA, 거래량, 캔들 패턴)
- 시장 전체 분위기
- 갭업 강도와 지속 가능성
- 호가창 수급

## 응답 형식
반드시 아래 JSON 형식으로만 응답하세요:
{
  "decision": "BUY" | "SELL" | "HOLD",
  "confidence": 0.0~1.0,
  "reasoning": "판단 근거 (한국어, 3~5문장)",
  "risk_assessment": "위험 요소 (한국어)",
  "suggested_qty": 0,
  "suggested_stop_loss": 0,
  "suggested_take_profit": 0
}
"""


class ClaudeTradeExecutor:
    """Claude AI를 활용한 매매 실행 판단기"""

    def __init__(self):
        self.client = anthropic.Anthropic(api_key=ai_settings.anthropic_api_key)
        self.model = "claude-opus-4-6"

    def decide_entry(self, context: dict) -> dict:
        """매수 진입 여부 판단

        Args:
            context: {
                "stock_code": 종목코드,
                "stock_name": 종목명,
                "current_price": 현재가,
                "strategy_signal": TradeSignal 결과,
                "chart_summary": 차트 요약,
                "orderbook": 호가 정보,
                "market_condition": 시장 상황,
                "available_capital": 가용 자금,
                "current_positions": 현재 포지션,
                "daily_pnl": 일일 손익,
            }
        """
        prompt = self._build_entry_prompt(context)

        try:
            response = self.client.messages.create(
                model=self.model,
                max_tokens=1024,
                system=TRADE_SYSTEM_PROMPT,
                messages=[{"role": "user", "content": prompt}],
            )
            result = self._parse_response(response.content[0].text)
            logger.info(
                f"Claude 매수 판단: {context['stock_name']} → "
                f"{result['decision']} (신뢰도: {result['confidence']:.0%})"
            )
            return result
        except Exception as e:
            logger.error(f"Claude 매수 판단 실패: {e}")
            return {
                "decision": "HOLD",
                "confidence": 0.0,
                "reasoning": f"AI 판단 오류: {e}",
                "risk_assessment": "판단 불가",
                "suggested_qty": 0,
                "suggested_stop_loss": 0,
                "suggested_take_profit": 0,
            }

    def decide_exit(self, context: dict) -> dict:
        """매도 청산 여부 판단

        Args:
            context: {
                "stock_code": 종목코드,
                "stock_name": 종목명,
                "entry_price": 진입가,
                "current_price": 현재가,
                "qty": 보유 수량,
                "pnl_pct": 수익률,
                "minutes_held": 보유 시간(분),
                "strategy_signal": 전략 신호,
                "chart_summary": 차트 요약,
            }
        """
        prompt = self._build_exit_prompt(context)

        try:
            response = self.client.messages.create(
                model=self.model,
                max_tokens=1024,
                system=TRADE_SYSTEM_PROMPT,
                messages=[{"role": "user", "content": prompt}],
            )
            result = self._parse_response(response.content[0].text)
            logger.info(
                f"Claude 매도 판단: {context['stock_name']} → "
                f"{result['decision']} (신뢰도: {result['confidence']:.0%})"
            )
            return result
        except Exception as e:
            logger.error(f"Claude 매도 판단 실패: {e}")
            return {
                "decision": "HOLD",
                "confidence": 0.0,
                "reasoning": f"AI 판단 오류: {e}",
                "risk_assessment": "판단 불가",
            }

    def _build_entry_prompt(self, ctx: dict) -> str:
        """매수 분석 프롬프트 생성"""
        signal = ctx.get("strategy_signal", {})
        return f"""## 매수 진입 분석 요청

### 종목 정보
- 종목: {ctx.get('stock_name', '?')} ({ctx.get('stock_code', '?')})
- 현재가: {ctx.get('current_price', 0):,}원
- 전략 신호: {signal.get('action', 'N/A')} (신뢰도: {signal.get('confidence', 0):.0%})
- 신호 근거: {signal.get('reason', 'N/A')}

### 차트 분석
{ctx.get('chart_summary', '차트 데이터 없음')}

### 호가 정보
{json.dumps(ctx.get('orderbook', {}), ensure_ascii=False, indent=2)}

### 시장 상황
{ctx.get('market_condition', '정보 없음')}

### 계좌 상태
- 가용 자금: {ctx.get('available_capital', 0):,}원
- 현재 보유 종목 수: {len(ctx.get('current_positions', []))}개
- 오늘 누적 손익: {ctx.get('daily_pnl', 0):,}원

### 제안 손절/익절
- 손절가: {signal.get('stop_loss', 0):,}원
- 익절가: {signal.get('take_profit', 0):,}원

이 종목을 지금 매수해야 할까요? 로스 카메론 전략 기준으로 분석해주세요.
"""

    def _build_exit_prompt(self, ctx: dict) -> str:
        """매도 분석 프롬프트 생성"""
        return f"""## 매도 청산 분석 요청

### 보유 종목 정보
- 종목: {ctx.get('stock_name', '?')} ({ctx.get('stock_code', '?')})
- 진입가: {ctx.get('entry_price', 0):,}원
- 현재가: {ctx.get('current_price', 0):,}원
- 보유 수량: {ctx.get('qty', 0)}주
- 현재 수익률: {ctx.get('pnl_pct', 0):+.2f}%
- 보유 시간: {ctx.get('minutes_held', 0)}분

### 전략 신호
{json.dumps(ctx.get('strategy_signal', {}), ensure_ascii=False, indent=2)}

### 차트 분석
{ctx.get('chart_summary', '차트 데이터 없음')}

이 종목을 지금 매도해야 할까요? 계속 보유해야 할까요?
로스 카메론 전략 기준으로 분석해주세요.
"""

    def _parse_response(self, text: str) -> dict:
        """Claude 응답 파싱"""
        # JSON 블록 추출
        text = text.strip()
        if "```json" in text:
            text = text.split("```json")[1].split("```")[0].strip()
        elif "```" in text:
            text = text.split("```")[1].split("```")[0].strip()

        try:
            return json.loads(text)
        except json.JSONDecodeError:
            # JSON 파싱 실패 시 텍스트에서 핵심 정보 추출 시도
            decision = "HOLD"
            if "BUY" in text.upper():
                decision = "BUY"
            elif "SELL" in text.upper():
                decision = "SELL"
            return {
                "decision": decision,
                "confidence": 0.5,
                "reasoning": text[:500],
                "risk_assessment": "파싱 실패로 보수적 판단",
                "suggested_qty": 0,
                "suggested_stop_loss": 0,
                "suggested_take_profit": 0,
            }
