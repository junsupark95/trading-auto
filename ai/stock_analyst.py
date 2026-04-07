"""GPT + Gemini 기반 종목 선정 & 분석 모듈

GPT-4가 1차 종목 선정 및 분석을 수행하고,
Gemini가 교차 검증 및 보완 의견을 제시합니다.
"""

import json
import openai
import anthropic
from google import genai as google_genai
from loguru import logger
from config.settings import ai_settings


GPT_ANALYST_PROMPT = """당신은 한국 주식시장 전문 데이트레이딩 애널리스트입니다.
로스 카메론(Ross Cameron)의 모멘텀 전략을 기반으로 종목을 분석합니다.

## 분석 기준
1. 갭업 강도와 원인 (뉴스, 공시, 테마)
2. 거래량 폭증 여부 (평소 대비)
3. 차트 패턴 (지지/저항, 캔들 패턴)
4. 시가총액과 유동주식수 (소형주 선호)
5. 당일 모멘텀 지속 가능성

## 응답 형식 (JSON)
{
  "selected_stocks": [
    {
      "stock_code": "종목코드",
      "stock_name": "종목명",
      "score": 0~100,
      "reason": "선정 이유 (3~5문장)",
      "entry_strategy": "진입 전략",
      "risk_factors": "위험 요소",
      "target_return": "목표 수익률"
    }
  ],
  "market_overview": "오늘 시장 전반 분석 (3~5문장)",
  "trading_plan": "오늘의 매매 전략 요약"
}
"""

GEMINI_VALIDATOR_PROMPT = """당신은 한국 주식시장 리스크 관리 전문가입니다.
GPT가 선정한 종목에 대해 교차 검증을 수행합니다.

## 검증 기준
1. 과열 여부 (급등 후 급락 위험)
2. 펀더멘탈 리스크 (재무 악화, 관리종목 등)
3. 수급 분석 (외국인/기관 동향)
4. 테마/섹터 모멘텀 지속 가능성
5. 기술적 과매수/과매도

## 응답 형식 (JSON)
{
  "validations": [
    {
      "stock_code": "종목코드",
      "stock_name": "종목명",
      "approval": true/false,
      "risk_level": "LOW/MEDIUM/HIGH/VERY_HIGH",
      "concerns": "우려 사항",
      "suggestion": "수정 제안"
    }
  ],
  "overall_risk": "전체 리스크 평가",
  "additional_recommendations": "추가 권고사항"
}
"""


class AIStockAnalyst:
    """GPT + Gemini 듀얼 AI 종목 분석"""

    def __init__(self):
        self.openai_client = None
        if ai_settings.openai_api_key:
            self.openai_client = openai.OpenAI(api_key=ai_settings.openai_api_key)
        else:
            logger.warning("OPENAI_API_KEY 미설정: GPT 종목 분석 비활성화")

        # 새 google-genai SDK 사용 (google-generativeai 대체)
        self.gemini_client = None
        if ai_settings.google_api_key:
            self.gemini_client = google_genai.Client(api_key=ai_settings.google_api_key)
        else:
            logger.warning("GOOGLE_API_KEY 미설정: Gemini 비활성화")

        self.claude_client = None
        if ai_settings.anthropic_api_key:
            self.claude_client = anthropic.Anthropic(api_key=ai_settings.anthropic_api_key)

        self.openai_model = ai_settings.openai_model
        self.gemini_model_name = ai_settings.gemini_model

    def analyze_candidates(self, scanner_summary: str,
                           market_data: dict = None) -> dict:
        """종목 분석 파이프라인: Gemini(무료) 1차 → Gemini 교차 검증"""
        # Step 1: 1차 분석 (Gemini 우선 → GPT → Claude 순)
        primary_result = self._primary_analyze(scanner_summary, market_data)

        # Step 2: Gemini 교차 검증
        gemini_result = self._gemini_validate(primary_result, scanner_summary)

        # Step 3: 결과 통합
        combined = self._combine_results(primary_result, gemini_result)

        logger.info(
            f"AI 종목 분석 완료: "
            f"{len(combined.get('final_picks', []))}개 최종 선정"
        )
        return combined

    def _primary_analyze(self, scanner_summary: str, market_data: dict = None) -> dict:
        """1차 종목 분석: Gemini(무료) → GPT → Claude 순서로 시도"""
        # 1순위: Gemini (무료)
        try:
            return self._gemini_primary_analyze(scanner_summary, market_data)
        except Exception as e:
            logger.warning(f"Gemini 1차 분석 실패: {e} → GPT로 대체")

        # 2순위: GPT
        try:
            if self.openai_client is None:
                raise RuntimeError("OPENAI_API_KEY 미설정")
            user_prompt = f"""## 오늘의 갭업 스캐너 결과
{scanner_summary}

## 추가 시장 데이터
{json.dumps(market_data or {}, ensure_ascii=False, indent=2)}

위 종목들을 로스 카메론 전략 기준으로 분석하고,
매매 가치가 높은 상위 종목을 선정해주세요.
"""
            response = self.openai_client.chat.completions.create(
                model=self.openai_model,
                messages=[
                    {"role": "system", "content": GPT_ANALYST_PROMPT},
                    {"role": "user", "content": user_prompt},
                ],
                max_tokens=2048,
                temperature=0.3,
            )
            text = response.choices[0].message.content
            result = self._parse_json(text)
            logger.info(f"GPT 분석 완료: {len(result.get('selected_stocks', []))}개 종목 선정")
            return result
        except Exception as e:
            logger.warning(f"GPT 분석 실패: {e} → Claude로 대체")

        # 3순위: Claude
        return self._claude_analyze(scanner_summary, market_data)

    def _gemini_call(self, prompt: str) -> str:
        """새 google-genai SDK로 Gemini 호출 (공통 헬퍼)"""
        if self.gemini_client is None:
            raise RuntimeError("GOOGLE_API_KEY 미설정")
        response = self.gemini_client.models.generate_content(
            model=self.gemini_model_name,
            contents=prompt,
        )
        return response.text

    def _gemini_primary_analyze(self, scanner_summary: str, market_data: dict = None) -> dict:
        """Gemini를 사용한 1차 종목 분석 (GPT_ANALYST_PROMPT와 동일 출력 형식)"""
        prompt = f"""{GPT_ANALYST_PROMPT}

## 오늘의 갭업 스캐너 결과
{scanner_summary}

## 추가 시장 데이터
{json.dumps(market_data or {}, ensure_ascii=False, indent=2)}

위 종목들을 로스 카메론 전략 기준으로 분석하고, 매매 가치가 높은 상위 종목을 선정해주세요.
반드시 JSON 형식으로만 응답하세요. 마크다운 없이 순수 JSON만 출력하세요.
"""
        text = self._gemini_call(prompt)
        result = self._parse_json(text)
        if not result.get("selected_stocks"):
            raise ValueError("Gemini 분석 결과 비어있음")
        logger.info(f"Gemini 1차 분석 완료: {len(result.get('selected_stocks', []))}개 종목 선정")
        return result

    def _gemini_validate(self, gpt_result: dict, scanner_summary: str) -> dict:
        """Gemini 교차 검증"""
        prompt = f"""{GEMINI_VALIDATOR_PROMPT}

## GPT가 선정한 종목
{json.dumps(gpt_result.get('selected_stocks', []), ensure_ascii=False, indent=2)}

## 원본 스캐너 데이터
{scanner_summary}

위 종목들에 대해 교차 검증을 수행해주세요.
"""
        try:
            text = self._gemini_call(prompt)
            result = self._parse_json(text)
            logger.info("Gemini 교차 검증 완료")
            return result
        except Exception as e:
            logger.warning(f"Gemini 검증 실패: {e} → 검증 생략(전종목 승인)")
            return {"validations": [], "overall_risk": "Gemini 검증 생략"}

    def _claude_analyze(self, scanner_summary: str, market_data: dict = None) -> dict:
        """Claude를 GPT 대체로 사용하는 종목 분석"""
        if self.claude_client is None:
            return {"selected_stocks": [], "market_overview": "Claude API 키 미설정"}
        prompt = f"""아래 갭업 스캐너 결과를 분석하여 매매 가치 높은 상위 종목을 선정하세요.

{scanner_summary}

다음 JSON 형식으로만 응답하세요. 설명이나 마크다운 없이 순수 JSON만:
{{
  "selected_stocks": [
    {{
      "stock_code": "종목코드",
      "stock_name": "종목명",
      "score": 0,
      "reason": "선정 이유",
      "entry_strategy": "진입 전략",
      "risk_factors": "위험 요소",
      "target_return": "목표 수익률"
    }}
  ],
  "market_overview": "시장 개요",
  "trading_plan": "매매 전략"
}}"""
        try:
            response = self.claude_client.messages.create(
                model=ai_settings.claude_model,
                max_tokens=2048,
                messages=[{"role": "user", "content": prompt}],
            )
            text = response.content[0].text.strip()
            result = self._parse_json(text)
            picks = result.get("selected_stocks", [])
            logger.info(f"Claude 분석 완료: {len(picks)}개 종목 선정")
            return result
        except Exception as e:
            logger.error(f"Claude 분석 실패: {e}")
            return {"selected_stocks": [], "market_overview": f"분석 실패: {e}"}

    def _combine_results(self, gpt_result: dict, gemini_result: dict) -> dict:
        """GPT + Gemini 결과 통합"""
        final_picks = []
        validations = {
            v["stock_code"]: v
            for v in gemini_result.get("validations", [])
        }

        for stock in gpt_result.get("selected_stocks", []):
            code = stock.get("stock_code", "")
            validation = validations.get(code, {})

            # Gemini가 승인하고 리스크가 VERY_HIGH가 아닌 종목만
            is_approved = validation.get("approval", True)
            risk_level = validation.get("risk_level", "MEDIUM")

            if is_approved and risk_level != "VERY_HIGH":
                stock["gemini_validation"] = validation
                stock["final_risk"] = risk_level
                final_picks.append(stock)

        # 교차검증 결과가 과도하게 보수적이거나 파싱 실패한 경우 GPT 상위 종목으로 폴백
        if not final_picks:
            for stock in gpt_result.get("selected_stocks", [])[:5]:
                stock["final_risk"] = "MEDIUM"
                final_picks.append(stock)

        # 점수순 정렬
        final_picks.sort(key=lambda x: x.get("score", 0), reverse=True)

        return {
            "final_picks": final_picks,
            "gpt_analysis": gpt_result,
            "gemini_validation": gemini_result,
            "market_overview": gpt_result.get("market_overview", ""),
            "overall_risk": gemini_result.get("overall_risk", ""),
            "trading_plan": gpt_result.get("trading_plan", ""),
        }

    def _parse_json(self, text: str) -> dict:
        """AI 응답에서 JSON 추출"""
        text = text.strip()
        if "```json" in text:
            text = text.split("```json")[1].split("```")[0].strip()
        elif "```" in text:
            text = text.split("```")[1].split("```")[0].strip()

        try:
            return json.loads(text)
        except json.JSONDecodeError:
            logger.warning("JSON 파싱 실패, 빈 결과 반환")
            return {}
