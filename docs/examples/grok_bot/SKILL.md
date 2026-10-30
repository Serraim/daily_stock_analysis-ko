---
name: daily-stock-analysis
description: daily_stock_analysis API를 호출해 주식을 분석합니다. 사용자가 「마오타이 분석해줘」「analyze AAPL」「600519 좀 봐줘」라고 하거나 시장 복기를 원할 때 사용합니다. 가능하면 종목 코드를 씁니다.
---

# daily_stock_analysis

이 Skill은 Grok Bot(2026-08-11 AI teammate)용입니다. 이미 배포된 DSA를 HTTP로 호출하며, Bot을 LiteLLM provider로 설정하지 마세요.

환경 변수 `DSA_BASE_URL`(DSA API 루트 주소, 끝에 슬래시 없음)이 필요합니다.

## 언제 쓰나요

- 종목 하나 또는 여러 종목 분석
- 특정 종목의 최신 DecisionSignal 조회(아침 브리핑 / 장중 모니터링 Routine)
- 시장 복기

## 작업 흐름

1. 종목 코드 추출: A주(중국 본토 주식)는 6자리(`600519`), 홍콩 주식은 `hk00700`, 미국 주식은 `AAPL`, 대만 주식은 `.TW` / `.TWO`. 한국 주식은 `005930.KS`처럼 `.KS`(코스피) / `.KQ`(코스닥)를 붙입니다. 종목 이름만 있으면 먼저 사용자에게 코드를 알려 달라고 하거나, 잘 알려진 대응 관계를 씁니다(구이저우마오타이 → `600519`).
2. 전체 분석이 필요하면 `{DSA_BASE_URL}/api/v1/analysis/analyze`에 POST합니다. **Routine이거나 Bot의 HTTP 타임아웃을 넘길 것 같은 분석은 처음부터 비동기로** 보내세요. 동기로 보냈다가 비동기로 다시 보내면 안 됩니다. 동기 요청이 타임아웃되어도 서버의 `_handle_sync_analysis`는 계속 실행되며 `TaskQueue`에 들어가지 않습니다. 이때 `async_mode: true`로 다시 보내면 큐의 중복 제거를 건너뛰어 요금과 알림이 중복됩니다.

```json
{
  "stock_code": "<code>",
  "report_type": "detailed",
  "force_refresh": true,
  "async_mode": true
}
```

202와 `task_id`가 돌아오면 `status: completed`가 될 때까지 `GET {DSA_BASE_URL}/api/v1/analysis/status/{task_id}`를 폴링합니다. 완성된 리포트는 `result.report`에 있으며, 응답 최상위의 `report`를 읽으면 안 됩니다.

`async_mode: false`는 Bot HTTP 타임아웃이 300초 이상이고 사용자가 한 번의 동기 결과를 기다리는 경우에만 씁니다. 동기 요청이 타임아웃되면 비동기로 다시 실행하지 마세요. 먼저 그 종목에 진행 중인 작업이 있는지(409 / status) 확인하거나 최신 DecisionSignal을 읽습니다.

3. 분석을 다시 돌리지 않고 최신 의견만 필요하면: `GET {DSA_BASE_URL}/api/v1/decision-signals/latest/{stock_code}`.
4. 시장 복기: `POST {DSA_BASE_URL}/api/v1/analysis/market-review`는 항상 202와 `task_id`를 돌려주며, 복기 본문을 돌려주지 않습니다. 같은 status API를 폴링하고, 완료되면 최상위의 `market_review_report` 또는 `market_review_payload`를 읽습니다(`result.report`에는 없습니다).
5. 상태 확인이 실패하면 먼저 `GET {DSA_BASE_URL}/api/health`를 호출합니다.

## 결과 보여 주기

- 동기 분석: `report.summary.operation_advice`, `trend_prediction`, `analysis_summary`
- 비동기 분석: `result.report.summary.operation_advice`, `result.report.summary.trend_prediction`, `result.report.summary.analysis_summary`
- 구조화된 행동: `action` / `action_label`(`buy|add|hold|reduce|sell|watch|avoid|alert`). 비동기일 때는 `result.report.summary`에 있습니다
- 계획: 동기는 `report.strategy.ideal_buy` / `stop_loss` / `take_profit`, 비동기는 `result.report.strategy.*`
- 시장 복기: `market_review_report`(텍스트) 또는 `market_review_payload`(구조화)
- 필드가 없으면 `operation_advice`로 대신합니다. 예전 3단계 통계는 여전히 `decision_type`을 봅니다
- DecisionSignal은 의견만 보여 주며, 주문을 넣거나 포지션을 바꾸지 않습니다

## 오류

| 상태 | 처리 |
| --- | --- |
| 연결 실패 | DSA가 실행 중인지, `DSA_BASE_URL`이 맞는지 확인 |
| 400 | `stock_code` 확인 |
| 409 | 해당 종목을 이미 분석 중입니다. 기존 `existing_task_id`의 status를 조회하고, 분석을 새로 시작하지 마세요 |
| 500 | DSA 로그 확인. `LITELLM_MODEL`과 그에 맞는 Key(선택 사항인 `XAI_API_KEY` 포함) 확인 |

`ADMIN_AUTH_ENABLED=true`이면 현재 API는 Cookie만 인정하고 Bearer는 인정하지 않습니다. `XAI_API_KEY`를 DSA API 키로 쓰지 마세요.
