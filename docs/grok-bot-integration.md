# Grok Bot 연동 안내

이 문서는 [daily_stock_analysis](https://github.com/ZhuLinsen/daily_stock_analysis)(DSA)를 **2026-08-11**에 공개된 [Grok Bot](https://x.ai/bot)(일반 Grok 채팅이 아니라 xAI의 AI 동료(teammate) 제품)과 연결하는 방법을 설명합니다.

API, 환경 변수, provider, 실행 분기를 새로 만들지 않습니다. Grok Bot은 기존 REST / Skill 계약만 씁니다.

## 먼저 두 가지 경로를 구분하세요

| 경로 | 무엇인가 | 설정 방법 | 아닌 것 |
| --- | --- | --- | --- |
| **Grok을 분석 모델로 쓰기** | LiteLLM으로 `xai/*`에 바로 연결해 DSA가 Grok으로 보고서를 씀 | `XAI_API_KEY` + `LITELLM_MODEL=xai/<공식 모델 ID>`. [LLM 설정 가이드](LLM_CONFIG_GUIDE.md) 참고 | Grok Bot 제품이 아님 |
| **Grok Bot을 동료로 쓰기** | 상시 클라우드 컴퓨터, Skills, Routines, MCP/Connectors, computer use를 갖춘 teammate | Bot이 이미 배포된 DSA HTTP API를 호출하거나, 자기 컴퓨터에서 `python main.py`를 실행 | Bot을 `LITELLM_MODEL`로 설정하지 마세요 |

두 경로를 함께 쓸 수도 있습니다. DSA는 `xai/grok-*`로 분석하고, Grok Bot은 그 보고서나 `DecisionSignal`을 읽어 가는 식입니다.

## 권장 연결 순서

1. 먼저 DSA API가 계속 접속 가능하도록 합니다: `python main.py --serve-only` 또는 Docker. GitHub Actions는 예약 실행만 하며 API를 계속 열어 두지 않습니다.
2. Grok Bot에 Skill을 하나 넣습니다([openclaw Skill](openclaw-skill-integration.md)의 `SKILL.md` 예시를 고쳐 쓰거나 [`docs/examples/grok_bot/SKILL.md`](examples/grok_bot/SKILL.md)를 쓰세요).
3. 장중 감시나 아침 브리핑이 필요하면, 전체 분석을 반복해서 돌리지 말고 Bot Routine으로 `DecisionSignal`을 조회하세요.
4. Bot이 HTTP 호출을 안정적으로 할 수 있게 된 다음에만, 같은 엔드포인트들을 MCP Connector에 연결하는 것을 고려하세요. 이 저장소는 **P0 단계에서 MCP server를 제공하지 않습니다**.

## Skill: 개별 종목 분석 실행

openclaw와 같은 주 진입점입니다. Bot / Routine은 **기본으로 `async_mode: true`**를 씁니다.

```http
POST {DSA_BASE_URL}/api/v1/analysis/analyze
Content-Type: application/json

{
  "stock_code": "600519",
  "report_type": "detailed",
  "force_refresh": true,
  "async_mode": true
}
```

- 비동기: 202 + `task_id`를 반환합니다. 그다음 `status: completed`가 될 때까지 `GET /api/v1/analysis/status/{task_id}`를 조회합니다. 완료된 보고서는 `result.report`에 있습니다(`TaskStatus.result`가 `AnalysisResultResponse`입니다). 응답 최상위의 `report`를 읽지 마세요.
- 동기 요청이 시간 초과되었다고 비동기로 다시 요청하지 마세요. 동기 요청이 시간 초과되어도 서버의 `_handle_sync_analysis`는 계속 실행되며 `TaskQueue`에 들어가지 않습니다. 이때 `async_mode: true`로 다시 보내면 큐의 중복 제거를 우회해 LLM 비용과 알림이 중복으로 발생합니다.
- HTTP 제한 시간이 300초 이상이고 사용자가 결과 하나를 기다리는 경우에만 `async_mode: false`를 쓰세요. 동기 응답의 보고서는 최상위 `report`에 있습니다.
- 상태 확인: `GET /api/health`.
- 종목 질문 Agent(`AGENT_MODE=true` 필요): `POST /api/v1/agent/chat`.

결과 읽기 약속(openclaw Skill과 같으며, 같은 뜻의 필드를 따로 만들지 않기 위한 것입니다):

- 자유 텍스트: `report.summary.operation_advice`, `trend_prediction`, `analysis_summary`(비동기는 앞에 `result.`가 붙음)
- 구조화된 행동: 선택 필드 `action` / `action_label`(8가지 상태 `buy|add|hold|reduce|sell|watch|avoid|alert`)
- 예전 기록에 필드가 없으면 `operation_advice`로 대신합니다. 예전 3가지 상태 통계는 여전히 `decision_type`을 기준으로 합니다

Grok Bot Skill 본문은 [`docs/examples/grok_bot/SKILL.md`](examples/grok_bot/SKILL.md)에 있으며, [openclaw Skill](openclaw-skill-integration.md) 예시를 다시 써도 됩니다. 환경 변수는 `DSA_BASE_URL` 하나로 통일합니다.

## Skill: 시장 리뷰

`POST {DSA_BASE_URL}/api/v1/analysis/market-review`는 항상 202 접수 응답 + `task_id`를 반환하며, 리뷰 본문이 아닙니다. 요청 본문에 `send_notification`, `region`을 넣을 수 있습니다.

`status: completed`가 될 때까지 `GET /api/v1/analysis/status/{task_id}`를 조회한 다음, `TaskStatus` 최상위에서 `market_review_report` 또는 `market_review_payload`를 읽으세요(`result.report`에는 없습니다).

## Routine: DecisionSignal 활용

Routine이 매번 분석을 다시 돌리게 하지 마세요. 공개 조회 엔드포인트:

| 용도 | 엔드포인트 |
| --- | --- |
| 특정 종목의 최신 active 신호 | `GET /api/v1/decision-signals/latest/{stock_code}` |
| 페이지 단위 필터링 | `GET /api/v1/decision-signals` |
| 사후 결과 통계 | `GET /api/v1/decision-signals/outcomes/stats` |
| 유용함 / 유용하지 않음 피드백 | `GET/PUT /api/v1/decision-signals/{signal_id}/feedback` |

필드와 생명 주기는 [DecisionSignal 문서](decision-signals.md)를 보세요. `DecisionSignal`은 권고를 기록할 뿐, 주문을 내거나 포트폴리오를 조정하지 않습니다.

Bot에 민감도가 낮은 컨텍스트를 줘야 한다면 [AnalysisContextPack](analysis-context-pack.md)의 공개 overview를 쓰세요. 전체 `context_snapshot`을 Skill 프롬프트에 넣지 마세요.

## MCP / Connector / computer use

- **MCP**: 위 표의 REST를 tool로 감싸기만 하면 됩니다(`analyze_stock`, `get_latest_signal`, `market_review`). 이 저장소는 FastAPI 계약과 두 갈래로 어긋나는 일을 막기 위해 아직 MCP server를 내장하지 않습니다.
- **Connectors**: Grok Bot은 Feishu(페이슈, 중국 업무용 메신저) / 이메일 등에 로그인할 수 있습니다. DSA 자체의 알림 채널은 여전히 `.env`에 있는 webhook을 쓰며, Bot을 거쳐 전달할 필요가 없습니다.
- **Computer use**: Bot의 클라우드 컴퓨터에 저장소를 clone하고 `.env`까지 설정해 둔 경우에만 `python main.py --stocks 600519,AAPL`이나 `python main.py --market-review`를 실행하기에 적합합니다. 인증, 제한 시간, 비동기 작업을 다루기 쉬우므로 기본적으로는 여전히 HTTP를 권장합니다.

## 인증

기본적으로 DSA API는 인증이 필요 없습니다. `ADMIN_AUTH_ENABLED=true`이면 현재는 로그인 후 받은 Cookie만 지원하며 **Bearer Token은 지원하지 않습니다**. Grok Bot이 `Authorization: Bearer`만 보낼 수 있다면, API는 인증 없이 두고 접속 가능한 네트워크 범위를 제한하거나, 리버스 프록시에서 따로 인증하세요. `XAI_API_KEY`를 DSA API 인증 키로 쓰지 마세요.

## 하지 않기로 한 것

- Grok Bot을 LiteLLM managed channel로 등록하지 않습니다.
- `GROK_BOT_*` 환경 변수를 새로 만들지 않습니다.
- `DecisionSignal` / `AnalysisContextPack` schema를 따로 복제하지 않습니다.
- 특정 `grok-*` 모델이 현재 `litellm` 버전 조건에서 반드시 동작한다고 이 문서에서 약속하지 않습니다. 모델은 [xAI 문서](https://docs.x.ai/docs)를 기준으로 하고, `python scripts/check_env.py --llm`으로 직접 확인하세요.

## 최소 확인 항목

1. DSA: `python scripts/check_env.py --config`. xAI 모델을 쓴다면 `python scripts/check_env.py --llm`도 실행합니다.
2. `GET {DSA_BASE_URL}/api/health`가 성공합니다.
3. Bot Skill이 실제 종목 코드 하나(예: `AAPL` 또는 `600519`)에 대해 `operation_advice` 또는 `action`을 받아 옵니다(비동기 경로는 `result.report`에서 읽음).
4. 시장 리뷰가 202 accepted만 받는 것이 아니라 status에서 `market_review_report` 또는 `market_review_payload`를 받아 옵니다.
5. Routine이 분석을 다시 돌리지 않고 `GET /api/v1/decision-signals/latest/{stock_code}`의 JSON을 읽을 수 있습니다.
