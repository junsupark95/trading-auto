"""일일 분석 리포트 생성 모듈

GPT가 리포트 작성, Gemini가 보완 의견 추가
"""

import json
from datetime import datetime
from pathlib import Path
from loguru import logger
from config.settings import ai_settings
import openai
import google.generativeai as genai
import pytz

KST = pytz.timezone("Asia/Seoul")

REPORT_PROMPT = """당신은 전문 트레이딩 리포트 작성자입니다.
오늘의 매매 결과를 분석하여 상세한 일일 리포트를 작성해주세요.

## 리포트 포함 항목
1. **시장 개요**: 오늘 시장 전반적인 흐름
2. **종목 선정 결과**: 선정된 종목과 이유
3. **매매 실행 결과**: 각 거래의 진입/청산 가격, 수익률
4. **수익/손실 분석**: 총 손익, 승률, 평균 수익/손실
5. **전략 평가**: 로스 카메론 전략의 오늘 적용 결과
6. **교훈 및 개선점**: 내일 적용할 개선 사항
7. **내일 전망**: 주목해야 할 섹터/이벤트

반드시 한국어로 작성하세요.
응답 형식: JSON
{
  "title": "리포트 제목",
  "market_summary": "시장 개요",
  "stock_selection": "종목 선정 분석",
  "trade_results": "매매 결과 상세",
  "pnl_analysis": "손익 분석",
  "strategy_review": "전략 평가",
  "lessons": "교훈 및 개선점",
  "tomorrow_outlook": "내일 전망",
  "overall_grade": "A/B/C/D/F"
}
"""


class DailyReportGenerator:
    """일일 트레이딩 리포트 생성기"""

    def __init__(self):
        self.openai_client = openai.OpenAI(api_key=ai_settings.openai_api_key)
        genai.configure(api_key=ai_settings.google_api_key)
        self.gemini_model = genai.GenerativeModel("gemini-2.0-flash")
        self.report_dir = Path("reports/daily")
        self.report_dir.mkdir(parents=True, exist_ok=True)

    def generate(self, trading_data: dict) -> dict:
        """일일 리포트 생성

        Args:
            trading_data: {
                "date": "2024-01-15",
                "market_condition": "시장 상황",
                "candidates": [종목 후보 리스트],
                "trades": [실행된 거래 리스트],
                "positions": [보유 포지션],
                "daily_pnl": 일일 손익,
                "total_trades": 총 거래 수,
                "winning_trades": 수익 거래 수,
            }
        """
        # GPT 리포트 작성
        gpt_report = self._gpt_write_report(trading_data)

        # Gemini 보완 의견
        gemini_supplement = self._gemini_supplement(gpt_report, trading_data)

        # 통합
        final_report = {
            **gpt_report,
            "gemini_supplement": gemini_supplement,
            "generated_at": datetime.now(KST).isoformat(),
        }

        # 파일 저장
        self._save_report(final_report, trading_data.get("date", "unknown"))

        logger.info(f"일일 리포트 생성 완료: {trading_data.get('date')}")
        return final_report

    def _gpt_write_report(self, trading_data: dict) -> dict:
        """GPT 리포트 작성"""
        user_prompt = f"""## 오늘의 트레이딩 데이터
{json.dumps(trading_data, ensure_ascii=False, indent=2, default=str)}

위 데이터를 기반으로 상세한 일일 트레이딩 리포트를 작성해주세요.
"""
        try:
            response = self.openai_client.chat.completions.create(
                model="gpt-4o",
                messages=[
                    {"role": "system", "content": REPORT_PROMPT},
                    {"role": "user", "content": user_prompt},
                ],
                max_tokens=3000,
                temperature=0.4,
            )
            text = response.choices[0].message.content
            return self._parse_json(text)
        except Exception as e:
            logger.error(f"GPT 리포트 생성 실패: {e}")
            return {"title": "리포트 생성 실패", "error": str(e)}

    def _gemini_supplement(self, gpt_report: dict,
                           trading_data: dict) -> dict:
        """Gemini 보완 의견"""
        prompt = f"""다음은 GPT가 작성한 일일 트레이딩 리포트입니다.
보완할 점, 놓친 리스크, 추가 인사이트를 제공해주세요.

## GPT 리포트
{json.dumps(gpt_report, ensure_ascii=False, indent=2, default=str)}

## 원본 데이터
{json.dumps(trading_data, ensure_ascii=False, indent=2, default=str)}

JSON 형식으로 응답해주세요:
{{
  "additional_insights": "추가 인사이트",
  "missed_risks": "놓친 위험 요소",
  "improvement_suggestions": "전략 개선 제안",
  "sentiment_analysis": "시장 심리 분석"
}}
"""
        try:
            response = self.gemini_model.generate_content(prompt)
            return self._parse_json(response.text)
        except Exception as e:
            logger.error(f"Gemini 보완 실패: {e}")
            return {"error": str(e)}

    def _save_report(self, report: dict, date: str):
        """리포트 파일 저장"""
        filepath = self.report_dir / f"report_{date}.json"
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(report, f, ensure_ascii=False, indent=2, default=str)
        logger.info(f"리포트 저장: {filepath}")

    def _parse_json(self, text: str) -> dict:
        """JSON 추출"""
        text = text.strip()
        if "```json" in text:
            text = text.split("```json")[1].split("```")[0].strip()
        elif "```" in text:
            text = text.split("```")[1].split("```")[0].strip()
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            return {"raw_text": text[:2000]}
