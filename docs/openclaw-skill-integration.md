# openclaw Skill 연동 가이드

이 문서는 [openclaw](https://github.com/openclaw/openclaw) Skill로 daily_stock_analysis의 REST API를 호출해, openclaw 대화 안에서 주식 분석을 실행하는 방법을 설명합니다.

## 개요

- **연동 방식**: openclaw Skill이 HTTP로 daily_stock_analysis(DSA) REST API를 호출합니다
- **사용 상황**: DSA API 서비스를 이미 배포해 두었고, openclaw 대화에서 분석을 실행하고 싶을 때(예: "마오타이 분석해 줘", "analyze AAPL")
- **같은 방식을 쓰는 다른 도구**: 2026-08-11에 공개된 [Grok Bot](https://x.ai/bot)(Skills / Routines / MCP / computer use)도 같은 REST 계약을 씁니다. 별도의 API를 새로 만들지 마세요. [Grok Bot 연동](grok-bot-integration.md)을 참고하세요.

## 사전 조건

1. **daily_stock_analysis가 실행 중이어야 합니다**: `python main.py --serve-only`를 실행하거나 Docker로 배포해 API가 계속 켜져 있도록 하세요
2. **openclaw가 HTTP 호출을 할 수 있어야 합니다**: 예를 들어 `system.run`으로 curl을 실행하거나, 내장 HTTP 도구(api-tester 등)를 씁니다
3. **참고**: GitHub Actions는 예약 실행만 하며 API를 계속 열어 두지 않습니다. DSA는 로컬이나 Docker에서 실행해야 합니다

## 핵심 API 참고

| 엔드포인트 | 메서드 | 용도 |
|------|------|------|
| `/api/v1/analysis/analyze` | POST | 분석 실행(주 진입점) |
| `/api/v1/analysis/status/{task_id}` | GET | 비동기 작업 상태 |
| `/api/v1/agent/chat` | POST | Agent 전략 종목 질문(`AGENT_MODE=true` 필요) |
| `/api/health` | GET | 상태 확인 |

### 분석 실행 요청 본문

```json
{
  "stock_code": "600519",
  "report_type": "detailed",
  "force_refresh": true,
  "async_mode": false
}
```

- `stock_code`: 종목 코드(필수)
- `report_type`: `simple` | `detailed` | `brief`
- `force_refresh`: 불리언 값. 캐시를 무시하고 새로 가져올지 여부
- `async_mode`: 불리언 값. `false`면 결과를 바로 돌려주고, `true`면 202 + `task_id`를 돌려주므로 상태를 반복 조회해야 합니다

**주의**: `force_refresh`, `async_mode`는 문자열이 아니라 불리언 타입입니다.

### 응답 예시(동기 모드)

아래 값(`贵州茅台` 구이저우 마오타이, `持有` 보유, `看多` 상승 전망)은 보고서 언어가 중국어일 때의 예시입니다. 보고서 언어를 한국어로 설정하면 해당 텍스트가 한국어로 나옵니다.

```json
{
  "query_id": "abc123def456",
  "stock_code": "600519",
  "stock_name": "贵州茅台",
  "report": {
    "summary": {
      "analysis_summary": "...",
      "operation_advice": "持有",
      "action": "hold",
      "action_label": "持有",
      "trend_prediction": "看多",
      "sentiment_score": 75
    },
    "strategy": {
      "ideal_buy": "1850",
      "stop_loss": "1780",
      "take_profit": "1950"
    }
  },
  "created_at": "2026-03-13T10:00:00"
}
```

## 중요한 제한과 참고 사항

- **종목 코드만 지원합니다**: API는 종목 이름(예: "마오타이")을 받지 않습니다. Skill 쪽에서 코드로 바꾸거나 사용자에게 코드(예: 600519, AAPL)를 알려 달라고 안내해야 합니다
- **동기 모드 소요 시간**: `async_mode: false`일 때 분석 한 번에 약 2–5분이 걸립니다. openclaw나 HTTP 클라이언트의 제한 시간을 충분히 길게 잡으세요
- **비동기 모드**: `async_mode: true`는 202 + `task_id`를 돌려줍니다. `status: completed`가 될 때까지 `GET /api/v1/analysis/status/{task_id}`를 반복 조회하세요

## 종목 코드 형식

| 종류 | 형식 | 예시 |
|------|------|------|
| A주(중국 본토) | 6자리 숫자 | `600519`, `000001`, `300750` |
| 베이징증권거래소 | 8/4/92로 시작하는 6자리. `BJ` 접두사나 `.BJ` 접미사 지원 | `920748`, `BJ920493`, `920493.BJ` |
| 홍콩 주식 | hk + 5자리 숫자 | `hk00700`, `hk09988` |
| 미국 주식 | 영문 1-5자(.X 접미사 선택) | `AAPL`, `TSLA`, `BRK.B` |
| 미국 지수 | SPX/DJI/IXIC 등 | `SPX`, `DJI`, `NASDAQ`, `VIX` |

## 설정 방법

`~/.openclaw/openclaw.json`에 설정합니다.

```json
{
  "skills": {
    "entries": {
      "daily-stock-analysis": {
        "enabled": true,
        "env": {
          "DSA_BASE_URL": "http://localhost:8000"
        }
      }
    }
  }
}
```

- 로컬 배포: `http://localhost:8000` 또는 `http://127.0.0.1:8000`
- 원격 배포: 실제 URL로 바꾸세요
- **권장**: `DSA_BASE_URL` 끝에 `/`를 붙이지 마세요

## 오류 응답 형식

| 상태 코드 | error 필드 | 설명 |
|--------|-------------|------|
| 400 | `validation_error` | 파라미터 오류(예: stock_code 누락) |
| 409 | `duplicate_task` | 해당 종목을 이미 분석 중이라 중복 요청을 거부함 |
| 500 | `internal_error` / `analysis_failed` | 분석 중 오류 발생 |

## SKILL.md 전체 예시

아래 내용을 `~/.openclaw/skills/daily-stock-analysis/SKILL.md`에 저장하세요.

```markdown
---
name: daily-stock-analysis
description: daily_stock_analysis API를 호출해 주식을 분석합니다. 사용자가 "마오타이 분석해 줘", "analyze AAPL", "600519 좀 봐 줘"처럼 요청할 때 사용합니다. 종목 코드만 지원하며 종목 이름은 지원하지 않습니다.
metadata:
  {"openclaw": {"requires": {"env": ["DSA_BASE_URL"]}, "primaryEnv": "DSA_BASE_URL"}}
---

## 사용 조건

사용자가 특정 종목 분석을 요청하면(예: "마오타이 분석해 줘", "analyze AAPL", "600519 좀 봐 줘") 이 Skill을 사용합니다.

## 작업 순서

1. **종목 코드 추출**: 사용자 메시지에서 종목 코드(예: 600519, AAPL, hk00700)를 찾습니다. 사용자가 종목 이름(예: "마오타이")만 말했다면 종목 코드를 알려 달라고 안내하거나, 잘 알려진 대응 관계(마오타이→600519)를 씁니다.
2. **API 호출**: `{DSA_BASE_URL}/api/v1/analysis/analyze`로 POST 요청을 보냅니다. 요청 본문:
   ```json
   {"stock_code": "<추출한 코드>", "report_type": "detailed", "force_refresh": true, "async_mode": false, "skills": ["bull_trend"]}
   ```
   > `skills`는 선택 사항인 전략 ID 배열입니다. 예전 필드 `strategies`도 호환을 위해 남아 있지만 `skills`를 쓰는 것이 좋습니다.
3. **응답 대기**: 동기 모드에서는 분석에 약 2–5분이 걸립니다. HTTP 클라이언트 제한 시간을 충분히 잡으세요(300초 이상 권장).
4. **결과 해석**: 응답의 `report.summary`에서 `operation_advice`, `trend_prediction`, `analysis_summary`를, `report.strategy`에서 `ideal_buy`, `stop_loss`, `take_profit`을 꺼내 간단히 정리해 보여 줍니다. 외부 연동은 자유 텍스트인 `operation_advice`만 계속 읽어도 됩니다. 구조화해서 보여 주고 싶다면 선택 필드 `action` / `action_label`(8가지 상태: `buy|add|hold|reduce|sell|watch|avoid|alert`)을 먼저 읽으세요. 예전 기록에 필드가 없으면 `operation_advice` 텍스트로 대신 보여 줄 수 있지만, 이것이 안정적인 API action과 같은 것은 아닙니다. 예전 3가지 상태 통계 기준은 여전히 `decision_type`입니다.
5. **오류 처리**:
   - 연결 실패: DSA가 실행 중인지, DSA_BASE_URL이 올바른지 확인하라고 안내합니다
   - 400: stock_code 형식을 확인합니다
   - 409: 해당 종목을 이미 분석 중이므로 잠시 뒤 다시 시도하거나 작업 상태를 조회합니다
   - 500: DSA 로그를 확인하라고 안내합니다

## 종목 코드 형식

- A주: 6자리 숫자(600519, 000001)
- 베이징증권거래소: 8/4/92로 시작하는 6자리, BJ 접두사나 .BJ 접미사 지원(920748, BJ920493, 920493.BJ)
- 홍콩 주식: hk + 5자리 숫자(hk00700)
- 미국 주식: 영문 1–5자(AAPL, TSLA, BRK.B)
- 미국 지수: SPX, DJI, IXIC 등
```

## Agent 전략 종목 질문(선택)

daily_stock_analysis에서 `AGENT_MODE=true`를 켜 두었다면 Agent 전략 종목 질문 엔드포인트를 호출할 수 있습니다. 여러 번 주고받는 대화와 다양한 전략(찬론(缠论, 중국식 차트 분석 이론), 이동평균선 골든크로스 등)을 지원합니다.

```bash
# {DSA_BASE_URL}을 실제로 설정한 API 주소(예: http://localhost:8000)로 바꾸세요
curl -X POST {DSA_BASE_URL}/api/v1/agent/chat \
  -H 'Content-Type: application/json' \
  -d '{"message": "用缠论分析 600519", "session_id": "optional-session-id"}'
```

(`用缠论分析 600519`는 "찬론으로 600519를 분석해 줘"라는 뜻의 예시 질문입니다. 한국어로 질문해도 됩니다. Windows PowerShell에서는 작은따옴표 대신 `curl.exe`와 큰따옴표 이스케이프가 필요할 수 있습니다.)

응답에는 `content`(분석 결론)와 `session_id`(이어지는 대화에 사용)가 들어 있습니다.

## 문제 해결

| 증상 | 가능한 원인 | 해결 방법 |
|------|----------|----------|
| 연결 실패 | DSA 미실행, 포트 오류, 방화벽 | `python main.py --serve-only`가 실행 중인지 확인하고 `DSA_BASE_URL`을 점검하세요 |
| 400 오류 | stock_code 형식 오류 또는 누락 | 코드 형식(위 표 참고)을 확인하고 요청 본문에 `stock_code`가 있는지 확인하세요 |
| 500 오류 | AI 설정, 데이터 소스, 네트워크 문제 | DSA 로그를 보고 `LITELLM_MODEL`과 해당 Key(예: `GEMINI_API_KEY` / `XAI_API_KEY`)가 설정되어 있는지 확인하세요 |
| Agent 400 | Agent 모드가 꺼져 있음 | DSA의 `.env`에 `AGENT_MODE=true`를 설정하세요 |
| 분석 시간 초과 | 동기 모드 대기 시간이 너무 김 | HTTP 클라이언트 제한 시간을 늘리거나 `async_mode: true`로 바꿔 상태를 반복 조회하세요 |

## 인증 안내

기본적으로 DSA API는 인증이 필요 없습니다. `.env`에서 `ADMIN_AUTH_ENABLED=true`를 켰다면 Skill이 호출할 때 로그인 후 받은 Cookie를 함께 보내야 합니다. 구체적인 방법은 openclaw HTTP 도구의 기능에 따라 다릅니다(현재 API는 Cookie 인증만 지원하며 Bearer Token은 지원하지 않습니다).
