import json
import os
import tempfile
import unittest
from pathlib import Path


os.environ.setdefault("KIS_APP_KEY", "test")
os.environ.setdefault("KIS_APP_SECRET", "test")
os.environ.setdefault("KIS_ACCOUNT_NO", "00000000-00")

from ai.trade_executor import ClaudeTradeExecutor
from ai.stock_analyst import AIStockAnalyst
from ai.report_generator import DailyReportGenerator


class _FakeClaudeResponse:
    def __init__(self, text: str):
        self.content = [type("Item", (), {"text": text})()]


class _FakeClaudeMessages:
    def __init__(self, text: str):
        self.text = text
        self.called = False

    def create(self, **kwargs):
        self.called = True
        return _FakeClaudeResponse(self.text)


class _FakeOpenAICompletions:
    def __init__(self, text: str):
        self.text = text
        self.called = False

    def create(self, **kwargs):
        self.called = True
        choice = type("Choice", (), {"message": type("Msg", (), {"content": self.text})()})()
        return type("Resp", (), {"choices": [choice]})()


class _FakeGeminiModel:
    def __init__(self, text: str):
        self.text = text
        self.called = False

    def generate_content(self, prompt: str):
        self.called = True
        return type("Resp", (), {"text": self.text})()


class AICallsTest(unittest.TestCase):
    def test_claude_trade_executor_entry_call(self):
        executor = ClaudeTradeExecutor()
        fake_messages = _FakeClaudeMessages(
            json.dumps(
                {
                    "decision": "BUY",
                    "confidence": 0.83,
                    "reasoning": "조건 충족",
                    "risk_assessment": "낮음",
                    "suggested_qty": 10,
                    "suggested_stop_loss": 9800,
                    "suggested_take_profit": 10600,
                },
                ensure_ascii=False,
            )
        )
        executor.client = type("Client", (), {"messages": fake_messages})()

        result = executor.decide_entry(
            {
                "stock_code": "005930",
                "stock_name": "삼성전자",
                "current_price": 10000,
                "strategy_signal": {"action": "BUY", "confidence": 0.8, "reason": "VWAP 상회"},
            }
        )

        self.assertTrue(fake_messages.called)
        self.assertEqual(result["decision"], "BUY")
        self.assertGreater(result["confidence"], 0)

    def test_stock_analyst_pipeline_calls_gpt_and_gemini(self):
        analyst = AIStockAnalyst()
        gpt_text = json.dumps(
            {
                "selected_stocks": [
                    {"stock_code": "005930", "stock_name": "삼성전자", "score": 85}
                ],
                "market_overview": "양호",
                "trading_plan": "보수적 진입",
            },
            ensure_ascii=False,
        )
        gemini_text = json.dumps(
            {
                "validations": [
                    {
                        "stock_code": "005930",
                        "stock_name": "삼성전자",
                        "approval": True,
                        "risk_level": "LOW",
                        "concerns": "",
                        "suggestion": "",
                    }
                ],
                "overall_risk": "LOW",
            },
            ensure_ascii=False,
        )

        fake_completions = _FakeOpenAICompletions(gpt_text)
        analyst.openai_client = type(
            "OpenAIClient",
            (),
            {"chat": type("Chat", (), {"completions": fake_completions})()},
        )()
        analyst.gemini_model = _FakeGeminiModel(gemini_text)

        result = analyst.analyze_candidates("테스트 스캐너 결과", {"kospi": "+0.8%"})

        self.assertTrue(fake_completions.called)
        self.assertTrue(analyst.gemini_model.called)
        self.assertEqual(len(result["final_picks"]), 1)
        self.assertEqual(result["final_picks"][0]["stock_code"], "005930")

    def test_daily_report_generator_calls_gpt_and_gemini(self):
        generator = DailyReportGenerator()
        gpt_text = json.dumps(
            {
                "title": "일일 리포트",
                "market_summary": "상승장",
                "overall_grade": "A",
            },
            ensure_ascii=False,
        )
        gemini_text = json.dumps(
            {
                "additional_insights": "리스크 관리 우수",
                "missed_risks": "없음",
                "improvement_suggestions": "손절 엄수",
                "sentiment_analysis": "낙관",
            },
            ensure_ascii=False,
        )

        fake_completions = _FakeOpenAICompletions(gpt_text)
        generator.openai_client = type(
            "OpenAIClient",
            (),
            {"chat": type("Chat", (), {"completions": fake_completions})()},
        )()
        generator.gemini_model = _FakeGeminiModel(gemini_text)

        with tempfile.TemporaryDirectory() as tmpdir:
            generator.report_dir = Path(tmpdir)
            report = generator.generate(
                {
                    "date": "2026-04-06",
                    "trades": [],
                    "daily_pnl": 0,
                    "total_trades": 0,
                    "winning_trades": 0,
                }
            )

        self.assertTrue(fake_completions.called)
        self.assertTrue(generator.gemini_model.called)
        self.assertEqual(report["title"], "일일 리포트")
        self.assertIn("gemini_supplement", report)


if __name__ == "__main__":
    unittest.main()
