"""배포 전 AI API 연결 상태 점검 스크립트

실행:
    python scripts/check_api.py

각 API에 최소한의 요청을 보내 응답 여부를 확인합니다.
실패한 항목은 빨간색으로 표시됩니다.
"""

import os
import sys
from pathlib import Path

# 프로젝트 루트를 sys.path에 추가
sys.path.insert(0, str(Path(__file__).parent.parent))

from dotenv import load_dotenv
load_dotenv(override=False)

OK   = "\033[92m✔\033[0m"
FAIL = "\033[91m✘\033[0m"
SKIP = "\033[93m-\033[0m"

results = {}


def check_gemini():
    key = os.getenv("GOOGLE_API_KEY", "")
    if not key:
        print(f"  {SKIP} Gemini: GOOGLE_API_KEY 미설정 — 건너뜀")
        results["gemini"] = "skip"
        return
    try:
        import google.generativeai as genai
        genai.configure(api_key=key)
        model = genai.GenerativeModel("gemini-1.5-flash")
        resp = model.generate_content("한국어로 '연결 확인'이라고만 답하세요.")
        text = resp.text.strip()
        print(f"  {OK} Gemini 1.5 Flash: 응답 OK → '{text[:40]}'")
        results["gemini"] = "ok"
    except Exception as e:
        print(f"  {FAIL} Gemini: 오류 → {e}")
        results["gemini"] = "fail"


def check_claude():
    key = os.getenv("ANTHROPIC_API_KEY", "")
    if not key:
        print(f"  {SKIP} Claude: ANTHROPIC_API_KEY 미설정 — 건너뜀")
        results["claude"] = "skip"
        return
    try:
        import anthropic
        client = anthropic.Anthropic(api_key=key)
        resp = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=20,
            messages=[{"role": "user", "content": "한국어로 '연결 확인'이라고만 답하세요."}],
        )
        text = resp.content[0].text.strip()
        print(f"  {OK} Claude Haiku: 응답 OK → '{text[:40]}'")
        results["claude"] = "ok"
    except Exception as e:
        print(f"  {FAIL} Claude: 오류 → {e}")
        results["claude"] = "fail"


def check_openai():
    key = os.getenv("OPENAI_API_KEY", "")
    if not key:
        print(f"  {SKIP} OpenAI: OPENAI_API_KEY 미설정 — 건너뜀")
        results["openai"] = "skip"
        return
    try:
        import openai
        client = openai.OpenAI(api_key=key)
        resp = client.chat.completions.create(
            model="gpt-4o-mini",
            max_tokens=20,
            messages=[{"role": "user", "content": "한국어로 '연결 확인'이라고만 답하세요."}],
        )
        text = resp.choices[0].message.content.strip()
        print(f"  {OK} GPT-4o-mini: 응답 OK → '{text[:40]}'")
        results["openai"] = "ok"
    except Exception as e:
        print(f"  {FAIL} OpenAI: 오류 → {e}")
        results["openai"] = "fail"


if __name__ == "__main__":
    print("=" * 50)
    print("  AI API 연결 점검")
    print("=" * 50)

    check_gemini()
    check_claude()
    check_openai()

    print("=" * 50)
    ok_count  = sum(1 for v in results.values() if v == "ok")
    fail_count = sum(1 for v in results.values() if v == "fail")
    skip_count = sum(1 for v in results.values() if v == "skip")
    print(f"  결과: 성공 {ok_count}  실패 {fail_count}  건너뜀 {skip_count}")

    # 트레이딩 가능 여부 판단
    if results.get("gemini") == "ok":
        print(f"\n  {OK} Gemini OK → 종목 분석 정상 작동 예정")
    else:
        print(f"\n  {FAIL} Gemini 실패 → 종목 분석 폴백(GPT→Claude) 사용")

    if results.get("claude") == "ok":
        print(f"  {OK} Claude OK → 매매 판단 AI 정상 작동 예정")
    else:
        print(f"  {SKIP} Claude 미사용 → 전략 신호 폴백으로 매매 판단")

    print("=" * 50)

    # Gemini가 fail이면 경고 후 비정상 종료
    if fail_count > 0 and results.get("gemini") == "fail":
        print("\n  ⚠ 핵심 무료 API(Gemini) 실패. 배포 전 GOOGLE_API_KEY 확인 필요.")
        sys.exit(1)
    sys.exit(0)
