# AI 모멘텀 트레이딩 시스템

한국투자증권 API + 로스 카메론 모멘텀 데이 트레이딩 전략 + 트리플 AI 자동매매 시스템

## 아키텍처

```
┌─────────────────────────────────────────────────────────┐
│                    Main Trading Loop                     │
├───────────┬──────────────┬──────────────┬───────────────┤
│  Scanner  │   Strategy   │  AI Engine   │   Dashboard   │
│ (갭업탐색) │ (Ross Cameron)│ (매매/분석)   │ (실시간 뷰)   │
├───────────┼──────────────┼──────────────┼───────────────┤
│           │              │ Claude Opus  │  Streamlit    │
│  KIS API  │  VWAP/EMA    │ (매매 판단)   │  + Plotly     │
│ (시세/주문) │  ATR/캔들     │ GPT-5.2      │              │
│           │              │ (종목 선정)   │              │
│           │              │ Gemini 3 Pro │              │
│           │              │ (교차 검증)   │              │
└───────────┴──────────────┴──────────────┴───────────────┘
```

## AI 역할 분담

| AI | 역할 | 모델 |
|---|---|---|
| **Claude** | 매수/매도 최종 판단 (추론력 최강) | claude-opus-4-6 |
| **GPT** | 종목 선정 & 일일 리포트 작성 | gpt-5.2-chat-latest |
| **Gemini** | 교차 검증 & 리스크 평가 | gemini-3-pro-preview |

## 로스 카메론 전략 핵심

1. **갭업 종목 선별**: 전일 대비 4%+ 갭업, 거래량 2배+ 급증, 소형주
2. **VWAP 위 진입**: VWAP + 9EMA 위에서만 롱 진입
3. **핵심 시간대 집중**: 09:00~10:30 (첫 1.5시간)
4. **엄격한 리스크 관리**: 손절 -2%, 익절 +4%, 트레일링 스탑 -1.5%
5. **보상/위험 비율**: 최소 2:1

## 설치 & 실행

```bash
# 1. Python 3.11+ 가상환경 생성
python3.11 -m venv .venv
source .venv/bin/activate

# 2. 의존성 설치
pip install -r requirements.txt

# 3. 환경변수 파일 준비 (모의/실전 분리)
cp .env.virtual.example .env.virtual
cp .env.real.example .env.real
# 각 파일에 API 키 입력

# 3-1. 설정 점검 (권장)
python main.py --profile virtual --check-config

# 4. 모의투자 자동 매매 실행
python main.py --profile virtual

# 5. 스캔만 (매매 X)
python main.py --profile virtual --scan-only

# 6. 실전투자 자동 매매 실행
python main.py --profile real

# 7. 실시간 대시보드 (별도 터미널)
streamlit run dashboard/app.py
```

스크립트로 더 간단히 실행:

```bash
# 점검
./scripts/run.sh virtual check

# 모의 스캔 전용
./scripts/run.sh virtual scan

# 모의 자동매매
./scripts/run.sh virtual trade

# 실전 자동매매
./scripts/run.sh real trade

# 대시보드
./scripts/dashboard.sh
```

## 환경 변수

프로파일 파일(`.env.virtual`, `.env.real`)에 아래 키 설정 필요:

- `KIS_APP_KEY` / `KIS_APP_SECRET`: 한국투자증권 API 키
- `KIS_ACCOUNT_NO`: 계좌번호 (형식: 00000000-00)
- `KIS_ENVIRONMENT`: `VIRTUAL` (모의투자) 또는 `REAL` (실전)
- `ANTHROPIC_API_KEY`: Claude API 키
- `OPENAI_API_KEY`: OpenAI API 키
- `GOOGLE_API_KEY`: Google Gemini API 키
- `CLAUDE_MODEL` / `OPENAI_MODEL` / `GEMINI_MODEL`: 각 AI 모델명 (기본값 제공)

직접 파일 지정도 가능:

```bash
python main.py --env-file .env.virtual --scan-only
python main.py --env-file .env.real
python main.py --profile real --check-config
```

## 프로젝트 구조

```
trading-auto/
├── main.py                 # 메인 실행 파일
├── config/
│   └── settings.py         # 전체 설정 (Pydantic)
├── api/
│   ├── kis_auth.py         # KIS 인증 (OAuth)
│   ├── kis_market.py       # 시세 조회
│   ├── kis_order.py        # 주문 (매수/매도)
│   └── kis_websocket.py    # 실시간 WebSocket
├── strategy/
│   ├── scanner.py          # 갭업 종목 스캐너
│   ├── indicators.py       # 기술적 지표 (VWAP, EMA, ATR)
│   └── ross_cameron.py     # 로스 카메론 전략 엔진
├── ai/
│   ├── trade_executor.py   # Claude 매매 판단
│   ├── stock_analyst.py    # GPT+Gemini 종목 분석
│   └── report_generator.py # 일일 리포트 생성
├── core/
│   ├── trading_engine.py   # 핵심 트레이딩 엔진
│   ├── position_manager.py # 포지션 관리
│   └── risk_manager.py     # 리스크 관리
├── dashboard/
│   └── app.py              # Streamlit 실시간 대시보드
├── utils/
│   └── market_hours.py     # 시장 시간 유틸리티
├── reports/daily/          # 일일 리포트 저장
├── logs/                   # 로그 파일
└── tests/                  # 테스트
```

## 주의사항

- **모의투자 먼저**: `KIS_ENVIRONMENT=VIRTUAL`로 충분히 테스트 후 실전 전환
- **API 호출 제한**: 한국투자증권 API는 초당 20건 제한
- **시장 위험**: 자동매매는 항상 손실 위험이 있으므로 소액으로 시작

## 클라이언트에서 AI 호출 실시간 확인하기

대시보드 우측에 **AI 호출 모니터**가 표시됩니다.

- 모듈 상태: `claude_trade`, `gpt_analyst`, `gemini_validator`, `gpt_report`, `gemini_report`
  - 🟢 연결됨: API 키/모델 설정 완료
  - ⚪ 미설정: 키 없음 또는 비활성 상태
- 최근 호출 이벤트 (최신 10건)
  - `START`: 호출 시작
  - `SUCCESS`: 응답 수신
  - `SKIP`: 조건 미충족으로 실행 스킵
  - `ERROR`: 예외 발생
  - (confidence가 있으면 함께 표시)

### 실시간으로 보는 방법

1. 엔진 실행 (`python main.py --profile virtual`)
2. 대시보드 실행 (`streamlit run dashboard/app.py`)
3. 대시보드는 기본 5초 주기로 자동 갱신되므로, 호출 이벤트가 거의 실시간으로 누적됩니다.

> 참고: `logs/dashboard_state.json`은 엔진이 5초 주기로 갱신합니다.  
> 따라서 엔진과 대시보드를 함께 띄워야 이벤트가 보입니다.

## Render 배포 (모바일 접속)

현재 구조는 대시보드가 `logs/dashboard_state.json`을 읽습니다.  
그래서 Render에서는 **트레이딩 엔진 + 대시보드를 같은 컨테이너에서 실행**해야 실시간 값이 보입니다.

### 1) GitHub push
- `Dockerfile`, `render.yaml`, `scripts/start_render.sh`가 포함된 상태로 push

### 2) Render 생성
1. Render 대시보드에서 `New +` -> `Blueprint`
2. GitHub 저장소 선택
3. `render.yaml` 인식 후 서비스 생성

### 3) 환경변수 입력 (Render)
- 필수:
  - `KIS_APP_KEY`
  - `KIS_APP_SECRET`
  - `KIS_ACCOUNT_NO`
  - `KIS_ENVIRONMENT` (`VIRTUAL` 권장)
  - `ANTHROPIC_API_KEY`
  - `OPENAI_API_KEY`
  - `GOOGLE_API_KEY`
- 권장:
  - `DASHBOARD_USER=admin`
  - `DASHBOARD_PASSWORD=<강한비밀번호>`
  - `APP_MODE=fullstack`
  - `TRADING_PROFILE=virtual`

### 4) 핸드폰 접속
- 배포 완료 후 Render URL을 모바일 브라우저에서 열면 됩니다.
- `DASHBOARD_PASSWORD`를 설정했다면 로그인 화면이 먼저 나옵니다.

### 운영 권장
- 초기에는 `KIS_ENVIRONMENT=VIRTUAL`로만 운영
- 실전 전환 시 소액/짧은 시간부터 검증
