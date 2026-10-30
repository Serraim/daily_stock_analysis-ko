# AnalysisContextPack: P0 현황 조사, P1/P2 계약, P3 Runtime Consumption, P4 가시성, P5 데이터 품질, #1386 P6 연동, #1389 P6 마이그레이션·롤백

이 페이지는 Issue #1389 주제 문서입니다. 현재 DSA 분석 컨텍스트(분석에 쓰이는 입력 데이터 묶음)의 실제 출처, 소비 경로, 필드 상태 경계와 함께 `AnalysisContextPack`의 내부 계약, builder, 런타임 소비, 민감도가 낮은 정보의 가시성, 데이터 품질 점수, 경보/보유 종목/이력/백테스트 연동, 마이그레이션과 롤백 경계를 기록합니다. P0는 현황 조사와 계약 경계를 맡습니다. P1은 내부 schema/envelope, block catalog, 타입 규약, 마스킹 직렬화만 추가합니다. P2는 pipeline이 이미 가진 artifacts로 pack을 조립하기만 합니다. P3는 민감도가 낮은 요약을 일반 분석과 Agent 첫 Prompt에만 연결합니다. P4는 민감도가 낮은 overview를 이력 상세, 동기 분석 응답, completed task status, Web 리포트 페이지에만 연결합니다. P5는 같은 `PACK_VERSION = "1.0"` 안에서 데이터 품질 점수, `fetch_failed` 상태, Prompt 데이터 한계, overview의 저민감 표시를 보완합니다. #1386 P6는 같은 공개 overview를 재사용해 경보, 보유 종목, 이력, 백테스트, 알림을 연동하고, 보유 종목 수동 분석 때 선택적인 보조 `portfolio` block을 추가합니다. #1389 P6는 문서, 설정 가시성, 마이그레이션, 롤백 안내만 보완하며, pack runtime, pack feature flag, DB migration, schema 버전은 추가하지 않습니다.

## 용어와 경계
<!-- 계약 키(tests): ## 术语与边界 -->

현재 저장소에는 context / snapshot이라는 이름의 데이터 면이 여러 개 있습니다. P0는 먼저 이 용어들을 구분해, 기존 런타임 구조를 앞으로 만들 pack으로 잘못 적지 않게 해야 합니다.

| 용어 | 현재 의미 | 현재 주요 사용처 | P0 경계 |
| --- | --- | --- | --- |
| `storage.get_analysis_context()` | `src/storage.py`에서 데이터베이스의 최근 이틀 OHLCV로 만드는 기술적 분석용 간단 컨텍스트이며, `today`, `yesterday`, `volume_change_ratio`, `price_change_ratio`, `ma_status` 등을 포함합니다. 현재 구현은 `target_date`를 받지만 실제로는 여전히 최신 이틀 데이터를 가져옵니다. | 일반 분석 주 경로, Agent 도구 `get_analysis_context` | 기존 기술적 분석 입력 출처로 기록하며, 앞으로 만들 pack과 바로 같은 것으로 보지 않습니다. |
| `enhanced_context` | 일반 분석에서 `src/core/pipeline.py`가 DB 간단 컨텍스트, 실시간 시세, 매물대(chip), 추세, 펀더멘털, 언어 정보를 바탕으로 보강한 prompt 컨텍스트입니다. | `src/analyzer.py` prompt 렌더링, `_build_context_snapshot()` | 현재 prompt 입력 면으로 기록합니다. P0는 필드 이름이나 구조를 바꾸지 않습니다. |
| `analysis_history.context_snapshot` | 분석이 끝난 뒤 이력 테이블에 저장하는 스냅샷입니다. 일반 분석은 보통 `enhanced_context`, `news_content`, `realtime_quote_raw`, `chip_distribution_raw`를 포함하고, Agent 경로는 `initial_context`를 저장합니다. | 이력 상세, 동기 analysis/status 응답, 백테스트, 일부 펀더멘털 fallback 표시 | 저장된 소비 면으로 기록합니다. `context_snapshot.enhanced_context.date` 호환을 반드시 유지해야 합니다. |
| Agent executor message context | `AgentExecutor._build_user_message()`가 첫 사용자 메시지에 넣는 컨텍스트로, `AGENT_ARCH=single` 경로에 해당합니다. 현재 종목 코드, 리포트 유형, 출력 언어, `realtime_quote`, `chip_distribution`, `news_context`를 포함합니다. | 단일 Agent 첫 LLM 메시지 | 현재 첫 메시지에서 보이는 필드를 기록합니다. P0는 runtime 주입을 보완하지 않습니다. |
| Agent orchestrator `AgentContext` | `AgentOrchestrator._build_context()`가 쓰는 멀티 Agent 공유 컨텍스트로, `AGENT_ARCH=multi` 경로에 해당합니다. `realtime_quote`, `daily_history`, `chip_distribution`, `trend_result`, `news_context`를 미리 넣을 수 있습니다. | Technical / Intel / Risk / Decision 멀티 Agent 경로 | orchestrator 내부 공유 데이터 면으로 기록합니다. `fundamental_context`는 미리 넣지 않으며, `trend_result`가 있는지는 caller가 넘겼는지에 달려 있습니다. |

## P0 범위와 비목표
<!-- 계약 키(tests): ## P0 范围与非目标 | P1 已新增 `AnalysisContextPack` 内部 schema | 不新增 builder | 不接入 runtime | 不公开完整 pack | 不 pack 化 `market_review` | P5 已在同一 1.0 umbrella 内追加该状态 -->

P0의 목표는 이후 P1/P2/P3가 실제 저장소 경계를 바탕으로 `AnalysisContextPack`을 설계할 수 있게 하는 것이며, 런타임을 미리 고치는 것이 아닙니다.

- P0는 일반 분석, Agent, 경보, 보유 종목, 백테스트, 이력, 알림 일곱 경로의 컨텍스트를 조사합니다.
- P0는 필드 품질 상태 용어를 고정합니다. P1에서 `AnalysisContextPack` 내부 schema가 추가되었지만, 여전히 builder를 추가하지 않고, runtime에 연결하지 않으며, 완전한 pack을 공개하지 않습니다.
- P0는 builder, 설정 항목, 데이터베이스 필드를 추가하지 않으며, API, 리포트, 이력, 알림 payload도 바꾸지 않습니다.
- P0는 runtime에 연결하지 않으며, `src/`의 분석, Agent, 경보, 보유 종목, 백테스트, 알림 로직을 바꾸지 않습니다.
- P0는 `market_review`, `market_light`, 시장 신호등 주제 스냅샷을 pack으로 만들지 않습니다. 이것들은 이력 스냅샷 안의 다른 `report_kind` / 주제별 소비 경계로만 기록합니다.
- P0 당시에는 `fetch_failed`를 필드 품질 상태 용어에 넣지 않았습니다. P5에서 같은 1.0 umbrella 안에 이 상태를 추가해 "지원하지 않음"과 "이번 수집 실패"를 분명히 구분합니다.
- P0는 README에 구현 세부를 늘려 쓰지 않습니다. 이 페이지는 주제 문서이며 `docs/INDEX.md` / `docs/INDEX_EN.md`의 목록에서 찾을 수 있습니다.

## P1 내부 계약
<!-- 계약 키(tests): ## P1 内部契约 | 不填充运行时数据 | 不新增 fetcher | 不改变 Prompt | 不写入 history/task/report metadata | 不把完整 pack 暴露到 API、Web、Bot、Desktop 或通知 | 不重复新增 `identity` block | `AnalysisContextPack.created_at` 使用 `datetime` | `model_dump(mode="json")` 输出 ISO 8601 | 构造时校验 | `block.status` 表示整块可用性 | `item.status` 表示字段级质量 | 不实现 `item.status` 到 `block.status` 的自动聚合推导 | 不扫描普通字符串值 | 不做 URL 正则脱敏 -->

P1은 `src/schemas/analysis_context_pack.py`를 추가하며, 내부 schema/envelope만 정의해 P2 builder와 P3 runtime이 같은 구조를 재사용할 수 있게 합니다. P1은 런타임 데이터를 채우지 않고, fetcher를 추가하지 않으며, Prompt를 바꾸지 않고, history/task/report metadata에 쓰지 않으며, 완전한 pack을 API, Web, Bot, Desktop, 알림에 노출하지 않습니다.

P1 schema 구성:

- `PACK_VERSION = "1.0"`이며, `AnalysisContextPack.pack_version`으로 계약 버전을 표시합니다.
- `ContextFieldStatus`: P1 첫 버전은 `available`, `missing`, `not_supported`, `fallback`, `stale`, `estimated`, `partial`만 허용합니다. P5에서 `fetch_failed`가 추가되었으며, 필드나 데이터 블록의 이번 수집이 명확히 실패했다는 뜻일 뿐 분석 전체가 실패했다는 뜻은 아닙니다.
- `AnalysisSubject`: 최상위 식별 슬롯이며 `code`, `stock_name`, `market`만 포함합니다. `exchange`, `currency`, `industry`는 이후 확장으로 남겨 둡니다. P2 builder는 P1 schema를 늘리지 않으며, `identity` block을 중복으로 추가하지도 않습니다.
- `AnalysisContextItem`: 필드 단위 입력 항목이며 `status`, `value`, `source`, `timestamp`, `fallback_from`, `missing_reason`, `warnings`, `metadata`를 포함합니다.
- `AnalysisContextBlock`: 데이터 블록 단위 묶음이며 `status`, `items`, `source`, `timestamp`, `warnings`, `metadata`를 포함합니다. `items`는 `Dict[str, AnalysisContextItem]`입니다.
- `DataQuality`: P1은 `warnings`와 `metadata` 컨테이너만 둡니다. P5에서 `overall_score`, `level`, `block_scores`, `limitations`가 추가되었으며, 여전히 민감도가 낮은 정보만 담고 raw payload는 담지 않습니다.
- `AnalysisContextPack`: 최상위 envelope이며 `pack_version`, `subject`, `phase`, `blocks`, `data_quality`, `metadata`, `created_at`을 포함합니다.

시간 필드 규약:

- `AnalysisContextPack.created_at`은 `datetime`을 쓰며, `model_dump(mode="json")`이 ISO 8601 문자열로 출력합니다.
- `AnalysisContextItem.timestamp`와 `AnalysisContextBlock.timestamp`는 `Optional[str]`을 쓰며, ISO 8601 datetime 문자열을 약속합니다. P1 schema는 생성 시점에 이 형식을 검증하며, date-only(날짜만 있는 값), 자연어 시간, 슬래시로 구분한 날짜는 거부합니다. P2 builder는 기존 artifact의 타임스탬프를 재사용할 때 강제로 다시 변환하지 않습니다.

상태 의미:

- `block.status`는 블록 전체의 사용 가능 여부를 나타냅니다.
- `item.status`는 필드 단위 품질을 나타냅니다.
- P1은 `item.status`에서 `block.status`를 자동으로 집계해 추론하는 기능을 구현하지 않습니다.

P1 Block Catalog:

| block key | P1 의미 | P1 경계 |
| --- | --- | --- |
| `quote` | 실시간 시세와 호가 관련 입력 | 표현할 위치만 정의하며 데이터를 가져오거나 채우지 않습니다. |
| `daily_bars` | 완전한 일봉 구간과 가장 최근 완전한 일봉 날짜 | P1은 partial bar를 판단하지 않습니다. |
| `technical` | 기술 지표, 가격·거래량 구조, 패턴 | P1은 지표를 만들지 않습니다. |
| `fundamentals` | 밸류에이션, 성장, 수익성, 재무제표, 주주 환원 | P1은 펀더멘털 fetcher를 추가하지 않습니다. |
| `news` | 뉴스, 공시, 여론, 촉매 이벤트 입력 | P1은 뉴스 검색을 바꾸지 않습니다. |
| `portfolio` | 보유 여부, 계좌 요약, 원가, 수량, 비중, stale 요약 | P1은 거래 내역, 현금 내역, 계좌 전체 개인정보를 넣지 않습니다. |
| `chip` / `capital_flow` | 매물대 분포, 자금 흐름, 주력 자금 동향 | 이후 확장 키이며, P1은 계약상 표현만 허용합니다. |
| `events` / `market_context` | 리스크 이벤트, 시장 폭(breadth), 지수, 업종, 테마 환경 | 이후 확장 키이며, `market_review` / `market_light`를 첫 버전 개별 종목 pack으로 쓰지 않습니다. |

`phase` 필드는 #1386 `MarketPhaseContext.to_dict()`의 결과만 받으며 `Dict[str, Any]`를 유지합니다. phase enum이나 phase 하위 모델을 새로 정의하지 않습니다.

마스킹 경계:

- `AnalysisContextPack.to_safe_dict()`는 먼저 `model_dump(mode="json")`을 실행한 뒤 `redact_sensitive_mapping()`을 호출합니다.
- `redact_sensitive_mapping()`은 dict/list에 대해 키 이름 기준으로 재귀 마스킹만 합니다. `api_key`, `access_token`, `refresh_token`, `authorization_header`, `webhook_url`, `password`, `cookie`, `secret`, `token`, `sendkey`, `license_key` 같은 민감한 키나 구문이 걸리면 값을 `[REDACTED]`로 바꿉니다.
- P1은 일반 문자열 값을 검사하지 않고, URL 정규식 마스킹도 하지 않으며, `data_api`나 단독 `api` / `key`를 민감 항목으로 보지 않습니다. 이 계약이 범용 secrets 엔진으로 커지지 않게 하기 위해서입니다.

## P2 Builder 계약
<!-- 계약 키(tests): ## P2 Builder 契约 | pipeline 已 fetch | `code`、`stock_name`、`market` | 不改变 Prompt | 不写入 history/task/report metadata | builder 只映射上游 artifact，不做质量评分 | `is_partial_bar`、`is_estimated`、`estimated_fields` | `daily_bars` 不承载 partial/estimated -->

P2는 `AnalysisContextBuilder`를 추가하지만, 첫 버전은 assembler(조립기) 역할만 합니다. 일반 분석 pipeline이 이미 가져온 artifacts로 내부 `AnalysisContextPack`을 조립합니다. Issue 인수 항목의 "기존 데이터 소스 재사용"은 이번 범위에서 pipeline이 이미 fetch한 `realtime_quote`, `base_context`, `enhanced_context`, `trend_result`, `chip_data`, `fundamental_context`, `news_context` 등의 artifacts를 재사용한다는 뜻으로 해석합니다. builder 자체는 zero-fetch이며, DB, fetcher, SearchService, Agent 도구, 개별 provider를 호출하지 않습니다.

P2 입력 계약은 `PipelineAnalysisArtifacts`를 씁니다: `code`, `stock_name`, `market`, `phase`, `base_context`, `enhanced_context`, `realtime_quote`, `trend_result`, `chip_data`, `fundamental_context`, `news_context`, `news_result_count`, `metadata`. 개별 종목 `build()`와 일괄 `build_batch()`가 같은 구조를 재사용하므로, P3 runtime 연결 때 시그니처를 다시 바꿀 필요가 없습니다.

P2 block 조립 경계:

- `subject`는 여전히 `code`, `stock_name`, `market` 세 필드만 쓰며 `AnalysisSubject`를 늘리지 않습니다.
- `phase`는 전달받은 `MarketPhaseContext.to_dict()` 결과만 받으며, `enhanced_context`에서 거꾸로 추론하지 않습니다.
- `quote`는 `realtime_quote`로 조립합니다. 없으면 `missing`입니다. `source=fallback`이거나 `fallback_from`이 명시되어 있으면 `fallback`으로 매핑하되, `source`에는 실제로 성공한 출처를 남깁니다. `fallback_from`은 artifact/metadata가 명시적으로 줄 때만 채우며, 그렇지 않으면 안정적인 warning code만 기록하고 provider 체인을 꾸며 내지 않습니다.
- `quote`는 #1386 P3의 `fetched_at`, `provider_timestamp`, `is_stale`, `stale_seconds`, `fallback_from`을 그대로 전달합니다. 상태 우선순위는 `STALE > FALLBACK > AVAILABLE`로 고정합니다. `is_stale=True`, `price_stale`, `quote_stale`, `quote_stale_seconds` 같은 명시적 marker는 `stale`로 표시합니다. `stale_seconds`가 있고 `is_stale=False`이면 메타데이터일 뿐이며, 그것만으로 stale을 추론하지 않습니다. builder는 상위 artifact를 매핑할 뿐 품질 점수를 매기지 않습니다.
- `daily_bars`는 완전한 일봉 구간만 표현하며, `base_context.today`, `base_context.yesterday`, `base_context.date`, `base_context.data_missing`을 우선 읽습니다. date-only 값은 `value`나 `metadata`에 넣고 `timestamp`에는 쓰지 않습니다.
- `enhanced_context.today`의 `is_partial_bar`, `is_estimated`, `estimated_fields`는 우선 `technical`로 들어갑니다. 이 값이 없으면 `enhanced_context.today.data_source`가 `realtime:*`인 경우를 보는 예전 heuristic도 계속 지원합니다. partial/estimated(장중 미완성/추정) 정보는 `technical`에만 들어가며 `daily_bars`는 partial/estimated를 담지 않습니다. warning은 `intraday_realtime_overlay`를 씁니다.
- `technical`은 `trend_result.to_dict()`를 우선 재사용하며, trend artifact가 없으면 `missing`입니다.
- `chip`은 `chip_data.to_dict()`를 재사용합니다. chip artifact가 없으면 기본적으로 `missing`이며, 입력 metadata/artifact가 not_supported를 명시할 때만 `not_supported`로 표시합니다.
- `fundamentals`는 `fundamental_context` 매개변수만 읽습니다. `ok`는 `available`, `not_supported`는 `not_supported`, `partial`은 `partial`로 매핑하고, P5 이후 `failed`는 `fetch_failed` + 안정적인 reason code `fundamental_pipeline_failed`로 매핑합니다. `errors[]` 원문은 쓰지 않습니다.
- `news`는 공백이 아닌 문자열이면 `available`, 공백이거나 없으면 `missing`입니다. `news_result_count`는 pack metadata에 씁니다.

P2는 `portfolio`, `events`, `market_context`를 조립하지 않으며, `capital_flow`를 별도 block으로 나누지도 않습니다. 첫 버전은 이것을 fundamentals의 coverage/source chain metadata 안에만 남겨 둡니다. P2 당시에는 Prompt도 바꾸지 않았고, 일반 분석이나 Agent runtime이 pack을 소비하게 하지도 않았으며, history/task/report metadata에 쓰지 않았고, 완전한 pack을 API/Web/Bot/Desktop/알림에 노출하지도 않았습니다. P5는 기존 builder 위에 저민감 점수, `fetch_failed` 세분화, Prompt 한계 안내만 추가하며 fetcher는 추가하지 않습니다.

## P3 Runtime Consumption (런타임 소비)
<!-- 계약 키(tests): 低敏 `analysis_context_pack_summary` -->
<!-- 계약 키(tests): `StockAnalysisPipeline` 是 summary 的唯一生产者 | 基础信息 -> #1386 `market_phase_context` 渲染区块 -> `analysis_context_pack_summary` | `news.content`、`trend_result`、`chip`、`fundamental_context` 等原始 payload | 禁止写入 `ctx.data` | `news` block 为 `missing` 是当前 P3 的预期状态 | Agent 工具级 pack cache 复用 | P4 在此基础上新增低敏 overview | P5 继续复用 summary 消费路径 -->

P3는 P2 `AnalysisContextBuilder` 다음 단계에서 런타임 소비를 연결하지만, 소비 범위는 민감도가 낮은 `analysis_context_pack_summary`로 제한합니다. `StockAnalysisPipeline`이 summary의 유일한 생산자입니다. 일반 분석 경로와 Agent 경로 안에서 `PipelineAnalysisArtifacts` -> `AnalysisContextBuilder.build()` -> `format_analysis_context_pack_prompt_section()`을 완료하며, 하위의 analyzer, single-agent, multi-agent는 summary 문자열만 받습니다. 완전한 pack을 스스로 만들지 않고, `AnalysisContextPack.to_safe_dict()`의 block item 원본 값도 읽지 않습니다.

일반 분석 Prompt의 순서는 기본 정보 -> #1386 `market_phase_context` 렌더링 블록 -> `analysis_context_pack_summary` -> 기술적 분석, 실시간 시세, 뉴스 등 기존 블록으로 고정합니다. `analysis_context_pack_summary`에는 subject, `pack_version`, block `status` / `source` / `warnings` / `missing_reason`, `metadata.news_result_count`, `data_quality.warnings`, P5의 저민감 데이터 한계만 들어가며, `news.content`, `trend_result`, `chip`, `fundamental_context` 같은 원본 payload를 출력하면 안 됩니다.

Agent 경로도 summary만 전달합니다. `AgentExecutor._build_user_message()`는 market phase 부분 다음, pre-fetched JSON 앞에 summary를 넣습니다. `AgentOrchestrator._build_context()`는 summary를 `ctx.meta["analysis_context_pack_summary"]`에만 넣으며, `ctx.data`에 쓰는 것은 금지됩니다. `BaseAgent._build_messages()`는 market phase user message 다음, `_inject_cached_data()` 앞에 summary를 넣습니다. Agent 경로는 `_ensure_agent_history()` 사전 조회 뒤 `storage.get_analysis_context()`를 한 번 읽어 `daily_bars`의 저민감 상태 출처로 씁니다. 읽기가 실패하거나 쓸 수 있는 컨텍스트가 없을 때만 `daily_bars_missing`으로 표시하며, 이 읽기는 fail-open이고 일봉 원본 payload를 Agent runtime context에 쓰지 않습니다. Agent 첫 단계는 일반 분석의 뉴스 검색을 재사용하지 않으므로, `news` block이 `missing`인 것은 현재 P3에서 예상된 상태입니다.

P3 당시에는 완전한 pack을 저장하지 않았고, API/Web/Bot/Desktop 필드를 추가하지 않았으며, 리포트 JSON schema를 바꾸지 않았고, summary를 `analysis_history.context_snapshot`, task status, report metadata에 쓰지 않았습니다. history snapshot과 diagnostic snapshot에서는 `market_phase_context`, `analysis_context_pack`, `analysis_context_pack_summary` 같은 runtime prompt 키를 제거합니다. P4는 이를 바탕으로 저민감 overview를 추가하며, 가시성은 이력 상세, 동기 분석 응답, completed task status, Web 리포트 페이지로 한정됩니다. P5는 summary 소비 경로를 계속 재사용하며 LLM 출력 JSON schema를 바꾸지 않습니다. Agent 도구 단위의 pack cache 재사용은 아직 이후 과제입니다.

## #1381 Daily Market Context

#1381은 AnalysisContextPack과 별도로 작은 일일 시장 환경 요약 경로를 추가해, `market_review` / `market_light`를 곧바로 pack으로 만들지 않게 합니다. `DAILY_MARKET_CONTEXT_ENABLED`는 기본으로 켜져 있습니다. `MARKET_REVIEW_ENABLED=true`이고 `DAILY_MARKET_CONTEXT_ENABLED=true`이면 `StockAnalysisPipeline`은 개별 종목의 시장(`cn` / `hk` / `us`)에 맞춰 당일 시장 컨텍스트를 불러옵니다. `analysis_history(code=MARKET, report_type=market_review)`에서 같은 날, 같은 시장 기록을 우선 재사용하고, 같은 날 기록이 없을 때만 `run_market_review(..., return_structured=True, send_notification=False)`를 호출해 이번 컨텍스트를 만듭니다. 프로세스 내 cache로 같은 Pipeline에서 중복 생성을 막고, CLI/예약 실행의 동시 실행 경로에서는 market review lock으로 생성을 직렬화합니다. `DAILY_MARKET_CONTEXT_ENABLED=false`는 개별 종목 분석의 저민감 요약 주입과 보수적 가드레일만 끄며, 시장 리뷰 자체는 끄지 않습니다.

**배경(Background):** `#1381`은 개별 종목 분석에서 당일 시장 컨텍스트를 재사용하고 대체 동작을 제어하는 데 초점을 둡니다. 기존 장중 단계, 일일 리포트, 상태 모델 구조는 바꾸지 않습니다. 이 단락은 `docs/CHANGELOG.md` [Unreleased]의 #1381 항목과 일치하며, 이번 변경 설명의 범위를 정리하는 기준으로 쓸 수 있습니다.
**범위(Scope, 이번 구현 범위):** `#1381`은 백엔드 runtime의 시장 컨텍스트 주입, 당일/대상 거래일 재사용 제어, 보수적 가드레일만 다룹니다. 별도 API, Web 단계 결과 별도 표시, 4단계 일일 리포트의 구조화 저장, 새 일일 리포트 상태 테이블은 포함하지 않습니다. 주요 진입점은 `main.py`(스케줄링과 `--no-market-review`), `src/core/pipeline.py`, `src/core/market_review.py`, `src/services/daily_market_context.py`, `src/analyzer.py`, `src/analysis_context_pack_overview.py`, `src/agent/executor.py`, `src/agent/orchestrator.py`, `src/agent/agents/base_agent.py`, `src/daily_market_context_guardrail.py`입니다. Web 쪽은 `DAILY_MARKET_CONTEXT_ENABLED` 설정 항목의 문구/도움말만 맞추며, 단계 결과 표시는 추가하지 않습니다.
**인수 완료 경계:** 이 PR은 `#1381`의 runtime 연결과 가드레일 하위 목표에만 해당합니다. 별도 API, Web 단계 표시, 4단계 일일 리포트 저장, 일일 리포트 상태 테이블이 이후 변경에서 반영되고 검증되기 전에는 Issue #1381을 완전히 인수 통과로 표시하면 안 됩니다.
**인수 기준(Acceptance Criteria):** 이번에는 runtime과 설정 진입점 기준으로만 인수하며, PR 과정의 API/Web UI 별도 단계 표시 인수는 포함하지 않습니다. 현재 인수 경로는 `tests/test_main_schedule_mode.py`, `tests/test_pipeline_daily_market_context.py`, `tests/test_daily_market_context.py`, `tests/test_daily_market_context_guardrail.py`, `tests/test_agent_executor.py`, `tests/test_config_env_compat.py`, `tests/test_config_registry.py`, `apps/dsa-web/tests/system_config_i18n.test.ts`로 제한합니다. 중점 확인 항목은 다음과 같습니다: `--no-market-review`가 시장 리뷰 생성을 막는지, `DAILY_MARKET_CONTEXT_ENABLED=false`가 개별 종목 컨텍스트 주입은 끄되 시장 리뷰는 유지하는지, 한 번의 schedule이 같은 `target_date`를 재사용하는지, 여러 시장 컨텍스트 로드(`cn,us`), `daily_market_context`가 같은 분석 주 경로에서 한 번만 주입되는지, 일반 분석과 Agent 경로가 가드레일을 적용하면서 원본 `market_review_payload`를 노출하지 않는지.
**호환성/위험(Compatibility/Risk):** `#1381`은 `provider/model/base_url`, 기본 모델, 설정 정리/되채우기/마이그레이션 의미를 바꾸지 않으며, 데이터베이스나 런타임 설정 테이블 변경도 추가하지 않습니다. `main.py::_bootstrap_environment`, `src/core/pipeline.py`, `src/analyzer.py`, `src/agent/executor.py`, `src/agent/orchestrator.py`, `src/agent/agents/base_agent.py`, `src/services/daily_market_context.py`, `src/daily_market_context_guardrail.py`는 기존 읽기 경로에서 LLM과 시장 리뷰 컨텍스트를 소비할 뿐이며, `SystemConfig` 저장이나 되쓰기 분기를 추가하지 않습니다. 공식 호환 근거는 `LiteLLM OpenAI-compatible`과 `OpenAI Chat Completion`을 그대로 따릅니다(아래 "호환성 근거와 확인 경계" 참고). 롤백은 일반적인 릴리스 롤백(관련 커밋 되돌리기)으로 하며, 필요하면 재시작과 함께 `env_file` / `--env-file` / 프로세스 단위의 같은 이름 환경 변수 덮어쓰기를 정리해 사용자의 기존 저장 설정을 복원합니다.
**호환성 근거와 확인 경계:** 이번 변경은 기존 LLM 설정 경로로 설정을 읽기만 하며, `.env` 쓰기 분기나 설정 마이그레이션/정리/되쓰기 진입점을 추가하지 않습니다. 공식 근거는 `LiteLLM OpenAI-compatible` <https://docs.litellm.ai/docs/providers/openai_compatible>, `OpenAI Chat Completion` <https://platform.openai.com/docs/api-reference/chat/create>를 따르며, 버전 제약은 `requirements.txt`(`litellm`, `openai`)의 현재 범위를 봅니다. 추적 가능한 코드 경로: `main.py::_bootstrap_environment`, `src/analyzer.py::_init_litellm`, `src/agent/agents/base_agent.py::_get_analyzer_config`(읽기 전용), `src/agent/executor.py`, `src/agent/orchestrator.py`, `src/core/pipeline.py`, `src/services/daily_market_context.py`, `src/daily_market_context_guardrail.py`. 회귀 확인 지점은 `tests/test_config_env_compat.py`, `tests/test_config_registry.py`, `tests/test_system_config_service.py`, `tests/test_system_config_api.py`, `tests/test_llm_channel_config.py`, `tests/test_market_review_runtime.py`입니다.

일반 분석과 Agent 분석은 저민감 필드만 받습니다: `daily_market_context`(region, trade_date, summary, risk_tags, source, 선택 항목 position_cap)와 `daily_market_context_summary` Prompt 부분입니다. 전체 `market_review_payload`, 원본 뉴스, 키, 알림 설정은 넘기지 않습니다. 일반 분석 Prompt는 시장 단계 부분 다음, 기술적 데이터 앞에 시장 요약을 넣고, 단일 Agent와 멀티 Agent 경로는 market phase 다음, pre-fetched 데이터 앞에 같은 요약을 넣습니다. Agent 자유 대화는 호출 측이 이미 `daily_market_context` / `daily_market_context_summary`를 준 경우에만 주입하며, 대화할 때마다 시장 리뷰를 자동으로 실행하지 않습니다.

결과 후처리에는 보수적인 시장 환경 가드레일이 추가됩니다. 요약이나 태그에 `high_risk`, `market_cooling`, `conservative`, `low_position_cap`이 있고 보수적/고위험 맥락이면, 모델이 낸 `buy` 결정("즉시 매수/추격 매수/공격적 비중 확대" 같은 매수 계열 제안 포함)은 관망 또는 소량 진입 후 확인 대기로 완화되고, 높은 확신도는 중간으로 낮아집니다. 이 가드레일은 해당 회차의 `AnalysisResult`와 dashboard 안의 저민감 한계 설명만 바꾸며, 데이터베이스 테이블이나 API 필드를 추가하지 않습니다. 롤백은 #1381 관련 서비스, Prompt 주입, guardrail 코드를 되돌리면 되며, 기존 시장 리뷰 이력 기록은 호환됩니다.

## P4 이력 기록, 작업 상태, Web 가시성
<!-- 계약 키(tests): 折叠头部展示可用数、缺失数、非零的其他状态计数和触发来源 -->
<!-- 계약 키(tests): ## P4 历史记录、任务状态与 Web 可见性 | 专用 renderer | 同步 `POST /api/v1/analysis/analyze` | overview 依赖已持久化的 `analysis_history.context_snapshot` | 不持久化整份 `analysis_history.context_snapshot` | 位置在策略点位和资讯之后、运行诊断之前 | 默认折叠 | 非零的其他状态计数 | 不覆盖 pending/processing TaskPanel | 不改通知摘要 | 质量分/等级 | `fetch_failed` 状态 -->

P4는 P3에서 만든 `AnalysisContextPack`을 공개용 저민감 `analysis_context_pack_overview`로 투영합니다. 이 overview는 전용 renderer가 만들며, 공개 API가 `AnalysisContextPack.to_safe_dict()`나 완전한 pack dump를 바로 반환하는 것은 허용하지 않습니다. renderer는 허용 목록의 필드만 출력합니다: `pack_version`, `created_at`, `subject.code` / `stock_name` / `market`, 데이터 블록 `key` / `label` / `status` / `source` / `warnings` / `missing_reasons`, block status별 개수 `counts`, 최상위 `data_quality.warnings`, `metadata.trigger_source` / `metadata.news_result_count`. P5는 같은 overview에 저민감 `data_quality` 객체를 추가하며, 최상위 `warnings`를 중복하지 않습니다.

overview는 `blocks.*.items`, `items.value`, `news.content`, `trend_result`, `chip`, `fundamental_context` 원본 payload를 출력하지 않으며, `api_key`, `token`, `cookie`, `webhook_url`, `password`, `secret`, `authorization`, `sendkey`, `license_key` 같은 민감한 키나 값도 출력하지 않습니다.

P4의 저장 면은 `analysis_history.context_snapshot` 최상위에 `analysis_context_pack_overview`를 쓰는 것뿐입니다. 런타임 prompt 필드는 계속 `enhanced_context`와 history snapshot에서 제거됩니다: `market_phase_context`, `analysis_context_pack`, `analysis_context_pack_summary`는 공개 이력 상세나 작업 상태에 들어가지 않습니다. `SAVE_CONTEXT_SNAPSHOT=false`이면 `analysis_history.context_snapshot` 전체를 저장하지 않으므로 overview, `market_phase_summary`, `enhanced_context`, raw snapshot 필드도 저장되지 않습니다. 예전 기록이나 overview가 없는 기록은 빈 필드를 반환하며 이력 상세 읽기에는 영향이 없습니다.

공개 overview block에는 `timestamp`, `provider_timestamp`, `fetched_at`을 추가할 수 있습니다. 해석 가능한 ISO 8601 datetime만 그대로 전달하며 시간대와 원래 값을 유지합니다. 임의의 item에서 block 전체의 시각을 추측하지 않으며, 다른 metadata는 노출하지 않습니다. `timestamp`는 수집 시각일 수 있으므로 관측 시각이나 데이터가 최신이라는 증거로 쓸 수 없습니다. `provider_timestamp`와 `fetched_at`은 각각 출처의 관측 시각과 수집 시각을 담습니다. 예전 overview에 이 필드가 없어도 읽을 수 있습니다.

공개 API 필드는 `report.details.analysis_context_pack_overview`로 고정되며, Web은 깊은 camelCase 변환 뒤 `analysisContextPackOverview`를 읽습니다. 연결 지점은 다음과 같습니다.

- `GET /api/v1/history/{record_id}` 이력 상세.
- 동기 `POST /api/v1/analysis/analyze`가 반환하는 `AnalysisResultResponse.report.details`. 다만 overview는 이미 저장된 `analysis_history.context_snapshot`에 의존하므로, `SAVE_CONTEXT_SNAPSHOT=false`이면 새 기록에서 overview 반환을 보장하지 않습니다.
- completed `GET /api/v1/analysis/status/{task_id}`. 메모리 큐 enrichment와 DB completed fallback을 모두 포함합니다.

API가 Web에 돌려주는 `details.context_snapshot`은 `sanitize_context_snapshot_for_api()`를 거치며 최상위 `analysis_context_pack_overview`가 제거됩니다. raw snapshot 패널에서 중복 표시되거나 완전한 컨텍스트로 내보내지는 것을 막기 위해서입니다. overview는 `extract_analysis_context_pack_overview()`로만 따로 꺼냅니다. Agent 경로와 일반 분석 경로는 같은 형태의 overview를 쓰며, Agent에 뉴스 개수가 없으면 `metadata.news_result_count`는 비어 있을 수 있습니다.

P4 Web 표시는 리포트 상세 페이지에서만 `AnalysisContextSummary`를 렌더링하며, 위치는 전략 가격대와 뉴스 섹션 다음, 실행 진단 앞입니다. 이 영역은 기본적으로 접혀 있으며, 접힌 머리글에는 사용 가능 개수, 누락 개수, 0이 아닌 기타 상태 개수, 트리거 출처를 보여 줍니다. 펼치면 각 데이터 블록의 상태, 출처, 경고, 설명만 보여 줍니다. 출처가 비어 있으면 "입력 출처 기록 없음"이라고 표시합니다. 설명 줄은 알려진 누락 원인을 원인, 이번 분석에 미치는 영향, 간단한 처리 방법으로 풀어 쓰고 괄호 안에 진단 코드를 남깁니다. 알 수 없는 원인은 block 상태에 따라 일반적인 안내를 보여 줍니다. `fallback`, `stale`, `estimated`, `partial`처럼 누락 원인이 없는 저하 상태도 같은 설명 줄에서 설명하며, 처리/범위/근거 필드를 새로 만들지는 않습니다. 리포트 페이지의 관련 뉴스는 별도 API로 불러오므로, 그 유무를 overview의 `metadata.news_result_count`로 추측할 수 없습니다. 뉴스 영역은 자신이 리포트 페이지의 보충 뉴스라는 점만 밝히고, 입력 데이터 블록은 뉴스가 이번 LLM 분석에 들어갔는지만 밝혀 두 데이터 범위를 같은 결과로 섞지 않습니다. 펼친 영역에는 상태 개수와 뉴스 결과 수가 계속 표시됩니다. P5 이후에는 접힌 머리글에 품질 점수/등급도 표시하고, 펼치면 `limitations`와 `fetch_failed` 상태를 보여 줍니다. overview가 없으면 자리 표시도 렌더링하지 않습니다. #1386 P4b에서 Web은 같은 리포트 상세 페이지에 `report.meta.market_phase_summary` 단계 라벨을 보여 주며, 이 저민감 데이터 품질 요약을 계속 재사용합니다. 완전한 pack, Prompt summary, raw payload, snapshot 내부 필드의 공개 범위는 넓히지 않습니다. P4/P5는 pending/processing TaskPanel의 AnalysisContextPack 데이터 품질 요약이나 SSE 진행 중 overview 가시성을 다루지 않으며, 알림 요약, Bot/Desktop 전용 표시, `market_review` overview도 바꾸지 않습니다.

## P5 데이터 품질 점수와 Prompt 데이터 한계
<!-- 계약 키(tests): ## P5 数据质量评分与 Prompt 数据限制 | `confidence_level` 不得为 `高` / `High` | 不替代 P5 的 confidence/safety 规则 | 不新增 fetcher | 不改变 LLM 输出 JSON schema -->

P5는 `PACK_VERSION`을 올리지 않고, fetcher와 설정 항목을 추가하지 않으며, 이력 마이그레이션도 하지 않는다는 전제에서 세 가지를 보완합니다. 내부 저민감 데이터 품질 점수, 모델에 관계없이 쓰는 Prompt 데이터 한계 블록, 기존 `analysis_context_pack_overview`의 저민감 가시성 확장입니다. #1389 P5는 여전히 LLM 출력 JSON schema를 바꾸지 않으며, 후처리로 결과를 강제로 고쳐 쓰지도 않습니다. #1386 P5는 여기의 저민감 입력 품질을 사용해 리포트 `dashboard.phase_decision`에 장중 행동 필드와 품질 가드레일 결과를 출력합니다.

상태 계약에 `fetch_failed`가 추가되며, "현재 필드나 데이터 블록의 이번 수집이 명확히 실패함"을 뜻합니다. 첫 버전은 기존 artifact가 명확히 실패했을 때만 씁니다. 예: `fundamental_context.status == "failed"`. 빈 뉴스, 검색 미설정, 실시간 quote artifact 없음, chip 누락은 기존 `missing` / `not_supported` 의미를 유지하여, 켜지 않은 기능을 수집 실패로 잘못 보고하지 않게 합니다. `fetch_failed`는 분석 전체가 실패했다는 뜻이 아닙니다.

`DataQuality`에는 다음 저민감 필드가 추가되며, 기존 `warnings` / `metadata`는 유지됩니다.

- `overall_score: Optional[int]`: 0-100 총점.
- `level: Optional["good"|"usable"|"limited"|"poor"]`: `>=85 good`, `>=70 usable`, `>=55 limited`, 그 밖에는 `poor`.
- `block_scores: Dict[str, int]`: 고정된 여섯 블록의 상태 점수.
- `limitations: List[str]`: 최대 5개의 안정적인 한계 설명이며, `block: status` 형식을 씁니다.

점수는 고정된 여섯 블록만 계산하며, 보조 블록이 없다고 다시 정규화하지 않습니다. 앞으로 block이 추가되어도 총점에 자동으로 영향을 주지 않습니다. 가중치는 `quote=25`, `daily_bars=25`, `technical=25`, `news=10`, `fundamentals=10`, `chip=5`로 고정하고, 상태 점수는 `available=100`, `partial=75`, `estimated=75`, `not_supported=70`, `fallback=65`, `stale=50`, `missing=35`, `fetch_failed=25`로 고정합니다. 총점 공식은 `round(sum(block_score * weight) / 100)`입니다.

`limitations`는 핵심 블록 `quote` / `daily_bars` / `technical`의 `stale`, `fallback`, `missing`, `fetch_failed`, `partial`, `estimated`를 먼저 나열하고, 그다음 보조 블록 `news` / `fundamentals` / `chip`의 `fetch_failed`, `fallback`, `stale`을 나열합니다. 보조 블록이 단순히 없는 경우는 한계 목록에 넣지 않습니다. 뉴스 누락, 검색 미설정, 지원하지 않는 기능을 호재나 악재로 해석하지 않게 하기 위해서입니다.

Prompt 데이터 한계는 `format_analysis_context_pack_prompt_section()` 안에서만 렌더링되며 pack summary 바로 뒤에 붙습니다. 그래서 일반 분석, single Agent, multi-agent가 같은 소비 경로를 재사용합니다. 중국어 출력에서는 제목이 `数据限制`(데이터 한계)이고, 영어 출력에서는 `Data Limitations`입니다. 실제 score가 있을 때만 점수 줄을 출력합니다. `quote`, `daily_bars`, `technical` 중 하나라도 degraded 상태이면, Prompt는 최종 JSON의 `confidence_level`이 `高`(높음) / `High`가 되어서는 안 된다고 명시합니다. Prompt는 계속 status/source/warnings/missing_reason/저민감 점수만 쓰며, raw payload, 뉴스 본문, 추세 원본 값, secret, token, webhook은 출력하지 않습니다.

> `数据限制`와 `高`는 프로그램이 Prompt와 결과에서 실제로 쓰는 문자열이라 원문 그대로 둡니다.

#1386 P2-full은 P5 score/limitations 다음, confidence/safety 앞에 최소한의 `phase × degraded data` 교차 제약을 추가합니다. `AnalysisContextPack.phase`가 올바른 `MarketPhaseContext`에서 왔고 `quote`, `daily_bars`, `technical` 중 degraded 상태가 있으면, Prompt는 현재 단계에서 데이터 품질이 장중 판단, 개장 계획, 보수적 분석을 어떻게 제한하는지만 보충합니다. 이것은 P5의 confidence/safety 규칙을 대신하지 않으며, `market_phase_context`의 phase 전용 문구를 반복하지도 않습니다. `pack.phase`가 없거나, dict가 아니거나, 잘못된 phase를 담고 있으면 fail-open으로 처리하고 P5의 일반 데이터 한계만 남깁니다.

overview는 기존 공개 면만 확장합니다. `analysis_context_pack_overview.data_quality` 허용 목록에는 `overall_score`, `level`, `block_scores`, `limitations`가 있으며, `warnings`를 중복 공개하지 않습니다. `render_analysis_context_pack_overview()`와 `extract_analysis_context_pack_overview()` / persisted sanitizer는 모두 이 객체를 정리합니다. 예전 overview에 `data_quality`가 없어도 정상적으로 읽힙니다. `details.context_snapshot`은 계속 최상위 `analysis_context_pack_overview`를 제거하며, 완전한 pack을 공개하지 않습니다.

## P6 경보, 보유 종목, 이력, 백테스트 연동

#1386 P6는 pack 버전을 새로 만들지 않으며, 완전한 pack을 더 많은 공개 면에 노출하지도 않습니다. P4/P5에서 정의한 `analysis_context_pack_overview`와 #1386에서 정의한 `market_phase_summary`만 재사용합니다.

- 경보 발동 기록은 여전히 기존 `alert_triggers.diagnostics` 텍스트 필드에 씁니다. diagnostics를 JSON으로 만들 수 있으면 worker가 `analysis_visibility.analysis_context_pack_overview`를 합쳐 넣으며, 출처는 evaluator가 이미 가진 overview 또는 최근 30일 이력 snapshot만 허용합니다. 예전 일반 텍스트 diagnostics는 덮어쓰지 않으며, API 파생 필드는 비어 있고 source는 `legacy_text`입니다.
- 보유 종목 수동 분석은 API에서 저민감 `portfolio_context`를 만들어 pipeline에 넘깁니다. builder는 pack에 선택 항목인 `portfolio` block을 추가합니다. 이 block은 계좌 ID/이름, symbol, market, currency, quantity, 평균 단가, 총 원가, 평가 손익, price source/provider/date/stale/available, cost method만 포함하며, 거래 내역, 현금 내역, 뉴스 본문, Prompt, 키, webhook은 포함하지 않습니다.
- `portfolio` block은 보조 블록이며 `metadata={"auxiliary": true, "quality_weighted": false}`입니다. P5의 고정 여섯 블록 `quote`, `daily_bars`, `technical`, `news`, `fundamentals`, `chip`의 가중치, 총점, limitations 기준을 바꾸지 않습니다.
- `portfolio_context`는 작업 실행 내부에서만 전달됩니다. `TaskInfo.to_dict()`, 작업 목록, SSE `task_created/task_started/task_completed/task_failed/task_progress` payload에는 이 객체가 노출되지 않습니다.
- 이력 목록, 개별 종목 이력, StockBar, 백테스트 결과는 `context_snapshot` 최상위의 공개 `market_phase_summary`만 읽습니다. 예전 기록, `SAVE_CONTEXT_SNAPSHOT=false`, 해석 실패는 `null` / `unknown`을 반환하며 실패로 처리하지 않습니다.
- 백테스트 phase 필터는 공개 summary만으로 bucket을 나눕니다. `premarket`은 premarket 그대로, `intraday|lunch_break|closing_auction`은 intraday로, `postmarket`은 postmarket 그대로, `non_trading|missing|invalid`는 unknown으로 묶습니다. phase 필터가 있으면 repository가 먼저 SQL 조건으로 결과와 snapshot을 한꺼번에 읽고, 서비스 계층에서 bucket을 나눈 뒤 페이지를 나누고 통계를 냅니다. API 계층에서 페이지를 나눈 뒤 임시로 걸러 내는 일을 피하기 위해서입니다.
- 알림 요약은 `market_phase_summary`와 `analysis_context_pack_overview.data_quality`만 사용하며, 단계, trigger source, partial-bar warning, 품질 등급, 앞의 두 개 limitations를 출력합니다. raw pack, `analysis_context_pack_summary` Prompt 문자열, 뉴스 본문, 민감한 보유 종목 세부 정보는 출력하지 않습니다.

<a id="p6-文档迁移与回滚"></a>
## P6 문서, 마이그레이션, 롤백
<!-- 계약 키(tests): ## P6 文档、迁移与回滚 | 四个数据面 | 内部完整 pack | 摘要可见性矩阵 | 不持久化整份 `analysis_history.context_snapshot` | 本次历史已持久化 `analysis_history.context_snapshot` | 不影响当次 `AnalysisContextPack` 构建 | 不影响内存中的 `result.diagnostic_context_snapshot` | 当前不存在 | 运行时 pack 总开关 | 发布或代码回滚 | 完整 webhook URL | 邮箱密码 -->

P6는 P1-P5의 런타임 동작을 바꾸지 않고, 이미 반영된 계약, 가시성, 설정, 마이그레이션, 롤백 경계를 안정적인 문서로 정리합니다. pack을 켜고 끄는 feature flag를 추가하지 않고, `PACK_VERSION = "1.0"`을 올리지 않으며, API 매개변수를 추가하지 않고, 리포트 JSON schema를 바꾸지 않으며, 데이터베이스 마이그레이션도 하지 않습니다.

다음 네 가지 데이터 면은 반드시 구분해서 이해해야 합니다.

| 데이터 면 | 위치 | 가시성 | P6 경계 |
| --- | --- | --- | --- |
| 내부 완전한 pack | `AnalysisContextPack` / `AnalysisContextBuilder` 산출물 | 내부 런타임에서만 사용 | 공개 API가 아니며 이력에 쓰지 않고, 외부에 안정적인 wire contract를 약속하지 않습니다. |
| LLM 저민감 요약 | `analysis_context_pack_summary` | 일반 분석, single Agent, multi-agent Prompt | subject, pack version, block status/source/warnings/missing reason, 뉴스 결과 수, 데이터 한계만 포함합니다. `items.value`, 뉴스 본문, 추세/매물대/펀더멘털 raw payload, secret, token, webhook은 포함하지 않습니다. |
| 공개 저민감 overview | `report.details.analysis_context_pack_overview` | 이력 상세, 동기 분석 응답, completed task status, Web 리포트 페이지 | 허용 목록 필드와 `data_quality` 저민감 점수만 출력합니다. 완전한 pack, Prompt summary, raw payload는 출력하지 않습니다. |
| 이력 컨텍스트 스냅샷 | `analysis_history.context_snapshot` | 저장 후 이력/API/Web/진단에서 읽음 | `details.context_snapshot`은 `sanitize_context_snapshot_for_api()`를 거쳐 `analysis_context_pack_overview`와 `market_phase_summary`가 제거됩니다. raw 패널이 안정적인 요약을 중복 공개하지 않게 하기 위해서입니다. |

요약 가시성 매트릭스:

| 소비 면 | 노출 내용 | 노출하지 않는 내용 |
| --- | --- | --- |
| LLM Prompt | `analysis_context_pack_summary` 저민감 상태 요약과 데이터 한계 | 완전한 pack, `items.value`, 뉴스 본문, 추세/매물대/펀더멘털 raw payload, secret/token/webhook |
| `GET /api/v1/history/{record_id}` | `report.details.analysis_context_pack_overview` | 완전한 pack, Prompt summary, raw `analysis_context_pack_overview` duplicate |
| 동기 `POST /api/v1/analysis/analyze` | `report.details.analysis_context_pack_overview`. 단, 이번 이력에 `analysis_history.context_snapshot`이 이미 저장되어 있어야 함 | 완전한 pack, Prompt summary |
| completed `GET /api/v1/analysis/status/{task_id}` | `status.result.report.details.analysis_context_pack_overview` | 완전한 pack, Prompt summary |
| Web 리포트 페이지 | 기본 접힘 상태의 `AnalysisContextSummary`. block 상태, 출처, 경고, 영향/권장 조치/진단 코드가 담긴 설명, 품질 점수와 한계를 표시 | 완전한 pack, raw payload, Prompt summary, 리포트 페이지가 따로 불러온 뉴스 결과 상태 |
| raw `details.context_snapshot` | 정리된 이력 스냅샷 | 최상위 `analysis_context_pack_overview`, `market_phase_summary` |
| 알림, Bot, Desktop 전용 표시 | P6에서 전용 표시를 추가하지 않음 | 완전한 pack, Prompt summary, raw payload |

필드 품질 상태 전체 목록은 `available`, `missing`, `not_supported`, `fallback`, `stale`, `estimated`, `partial`, `fetch_failed`로 유지합니다. 이 상태들은 입력 데이터 품질을 설명할 뿐이며, 분석 작업, 경보, 백테스트, 알림 전달 자체의 성공이나 실패를 뜻하지 않습니다.

마스킹 경계:

- 완전한 `AnalysisContextPack`은 공개 API, Web, 알림, Bot, Desktop 전용 표시에 들어가지 않습니다.
- `AnalysisContextPack.to_safe_dict()`는 내부 안전 직렬화 helper로만 씁니다. 공개 overview는 반드시 `render_analysis_context_pack_overview()`로 투영해야 합니다.
- `analysis_context_pack_summary`와 overview는 모두 `items.value`, 뉴스 본문, `trend_result`, `chip`, `fundamental_context` 원본 payload, API key, token, cookie, 전체 webhook URL, 이메일 비밀번호, secret, authorization, sendkey, license key를 출력하면 안 됩니다.
- 저장된 overview를 다시 읽을 때는 반드시 `extract_analysis_context_pack_overview()` / persisted sanitizer를 거쳐야 합니다. API 투명성 패널은 계속 `sanitize_context_snapshot_for_api()`로 최상위 안정 요약을 제거해야 합니다.

마이그레이션 경계:

- P6는 DB migration을 하지 않습니다. 예전 이력 기록에 `analysis_context_pack_overview`나 `data_quality`가 없으면 빈 필드를 반환하며, 리포트는 정상적으로 읽힙니다.
- `SAVE_CONTEXT_SNAPSHOT=true`가 기본 동작이며, `analysis_history.context_snapshot`을 이력 투명성과 진단 출처로 계속 저장합니다.
- `SAVE_CONTEXT_SNAPSHOT=false` 또는 CLI `--no-context-snapshot`을 쓰면 `analysis_history.context_snapshot` 전체 저장을 멈춥니다. 즉, 새 이력에는 `enhanced_context`, `market_phase_summary`, `analysis_context_pack_overview`, `diagnostics`, `realtime_quote_raw`, 기타 raw snapshot 필드를 포함한 `analysis_history.context_snapshot` 전체가 저장되지 않습니다.
- 저장을 꺼도 해당 회차의 `AnalysisContextPack` 생성과 `analysis_context_pack_summary`의 Prompt 주입에는 영향이 없으며, 메모리 안의 `result.diagnostic_context_snapshot`에도 영향이 없습니다.

롤백 방법:

| 수단 | 효과 | 할 수 없는 일 |
| --- | --- | --- |
| P3-P5 관련 변경의 릴리스 또는 코드 롤백 | pack prompt summary, overview, 데이터 품질 연결을 제거 | - |
| `SAVE_CONTEXT_SNAPSHOT=false` 또는 `--no-context-snapshot` | 새 이력 `context_snapshot` 저장을 멈춰, 새 이력에서 overview / phase summary / raw snapshot을 더 이상 공개하지 않음 | 해당 회차의 pack 생성이나 LLM Prompt 안의 저민감 summary는 끌 수 없음 |
| 런타임 pack 전체 스위치 | 현재 존재하지 않음 | 환경 변수 하나로 P3-P5 pack 연결을 끌 수 없음. 코드 롤백이나 이후 별도 설계가 필요 |

## 필드 품질 상태
<!-- 계약 키(tests): ## 字段质量状态 | P0 先固定七词 | P5 在同一 1.0 umbrella 内追加 `fetch_failed` -->

앞으로 만들 pack의 필드 품질 상태는 P0에서 먼저 일곱 단어로 고정했고, P5가 같은 1.0 umbrella 안에서 `fetch_failed`를 추가했습니다. 이 상태들은 필드나 데이터 블록의 품질을 설명하며, 업무 흐름의 성공 여부를 설명하지 않습니다.

| 상태 | 의미 | 예시 경계 |
| --- | --- | --- |
| `available` | 필드가 있고 출처와 타임스탬프를 설명할 수 있으며, 현재 경로에서 정상적으로 쓸 수 있습니다. | 실시간 시세가 가격과 출처를 반환함. 과거 K선 구간이 계산에 충분함. |
| `missing` | 현재 경로에 필요한 필드인데 실제로 가져오지 못했거나 비어 있습니다. | DB에 최근 일봉이 없어 일반 분석이 `data_missing` 결과로 들어감. |
| `not_supported` | 현재 시장, 데이터 소스, 경로가 이 필드를 지원하지 않으며, 오류로 잘못 보고하면 안 됩니다. | 일부 시장에는 매물대 분포나 자금 흐름이 없음. |
| `fallback` | 우선 출처를 쓸 수 없어 대체 출처나 예전 경로를 사용했습니다. | 보유 종목 가격이 실시간 시세에서 과거 종가로 fallback됨. |
| `stale` | 필드는 있지만 최신성이 부족합니다. | 보유 종목 평가의 `price_stale` / `fx_stale`. |
| `estimated` | 추정값이므로 완전한 사실로 다루면 안 됩니다. | 장중에 실시간 가격으로 오늘 봉을 보충해 만든 기술적 추정. |
| `partial` | 데이터 블록의 일부만 쓸 수 있고 일부는 없습니다. | 시장 신호등 `data_quality=partial` 또는 도구가 `partial_cache`를 반환. |
| `fetch_failed` | 현재 경로가 수집을 시도한 것이 확인되었지만 이번 수집은 실패했습니다. | `fundamental_context.status == "failed"`를 펀더멘털 block 수집 실패로 매핑. |

## 기존 상태 매핑
<!-- 계약 키(tests): ## 现有状态映射 | 不映射 -->

현재 저장소에는 이미 상태 용어가 많습니다. P0는 매핑할지(또는 매핑하지 않을지)만 정해, 이후 업무 결과 상태가 필드 품질 enum에 섞이지 않게 합니다.

| 기존 용어 또는 필드 | 현재 위치 | 권장 관계 | 설명 |
| --- | --- | --- | --- |
| `data_missing` | 일반 분석에서 과거 데이터가 없는 결과 | `missing`으로 매핑 가능 | 핵심 입력이 없다는 뜻이며 업무 성공 상태가 아닙니다. |
| `cache_hit` / `partial_cache` | Agent 과거 데이터 도구 | `partial_cache`는 `partial`로 매핑 가능 | `cache_hit`는 출처/캐시 메타데이터이며 품질 상태가 아닙니다. |
| `source` / `data_source` / `realtime_source` | 데이터 소스, 경보, 컨텍스트 스냅샷 | 매핑하지 않음 | 출처 메타데이터이므로 필드 품질 상태와 나란히 저장해야 합니다. |
| `price_source=missing` | 보유 종목 스냅샷 | `missing`으로 매핑 가능 | 평가 가격을 쓸 수 없다는 뜻입니다. |
| `price_stale` / `fx_stale` | 보유 종목 스냅샷 | `stale`로 매핑 가능 | 원래 필드는 업무 메타데이터로 유지합니다. |
| `triggered` / `skipped` / `degraded` / `failed` | 경보 평가와 기록 | 매핑하지 않음 | 규칙 평가나 기록 결과이며, 필드 단위 품질 상태가 아닙니다. |
| `insufficient_data` / `completed` / `error` | 백테스트 서비스 | 매핑하지 않음 | 백테스트 실행 상태입니다. pack 요약에서 발생 원인을 설명할 수는 있습니다. |
| `sent` / `no_channel` / `partial_failed` / `all_failed` | 알림 발송 | 매핑하지 않음 | 알림 전달 결과이며, 이것으로 분석 입력 품질을 거꾸로 추론할 수 없습니다. |
| `data_quality=ok/partial/unavailable` | 시장 신호등 | `partial`은 매핑 가능, `unavailable`은 필드 상황에 따라 `missing` 또는 `not_supported`로 매핑 | P0는 시장 신호등을 첫 버전 개별 종목 pack에 넣지 않습니다. |
| `fetch_failed` | 데이터 품질 세분화 | P5에서 `fetch_failed`로 매핑 | 기존 artifact가 명확히 실패했을 때만 쓰며, 분석 전체 실패를 뜻하지 않습니다. |

## 일곱 경로 현황
<!-- 계약 키(tests): ## 七路径盘点 | 不显式注入 `fundamental_context` 或 `trend_result` | 不预注入 `fundamental_context` -->

### 일반 분석
<!-- 계약 키(tests): ### 普通分析 -->

일반 분석의 주 경로는 `src/core/pipeline.py`에서 입력을 조립합니다. 먼저 `storage.get_analysis_context()`를 읽고, 사용 가능 여부에 따라 실시간 시세, 매물대, 추세 분석, 뉴스, 펀더멘털, 리포트 언어를 보충한 뒤 `src/analyzer.py`에 넘겨 prompt를 렌더링합니다. 현재 중복은 주로 실시간 필드가 `enhanced_context.realtime`, `realtime_quote_raw`, 리포트 meta에 동시에 있다는 점입니다. 이름도 `source`, `data_source`, `realtime_source` 등 출처 필드가 여러 가지입니다.

첫 버전 pack은 일반 분석 경로에서 개별 종목의 핵심 식별 정보, 시세, 일봉, 기술적 분석, 뉴스, 펀더멘털, 데이터 품질 요약을 뽑아낼 수 있습니다. P0는 `_enhance_context()`, `_build_context_snapshot()`, analyzer prompt를 바꾸지 않습니다.

### Agent

Agent에는 따로 기록해야 하는 데이터 면이 세 층 있습니다. `src/core/pipeline.py`의 Agent 경로는 `initial_context`를 만들며, 여기에는 `fundamental_context`가 항상 들어가고, 가능하면 `trend_result`도 들어갑니다. 이것이 최종적으로 Agent 경로의 `context_snapshot`으로 저장됩니다. `AgentExecutor._build_user_message()`는 `AGENT_ARCH=single`에만 적용되며, 첫 메시지에는 `realtime_quote`, `chip_distribution`, `news_context` 등 이미 가져온 컨텍스트만 명시적으로 넣고, `fundamental_context`나 `trend_result`는 명시적으로 넣지 않습니다. `AgentOrchestrator._build_context()`는 `AGENT_ARCH=multi`에 적용되며 `realtime_quote`, `daily_history`, `chip_distribution`, `trend_result`, `news_context`를 미리 넣을 수 있습니다. `AgentContext`에 들어간 이 필드들은 pre-fetched data로 각 stage agent 메시지에 주입됩니다. 하지만 orchestrator는 `fundamental_context`를 미리 넣지 않습니다. `trend_result`는 항상 있는 것이 아니라 caller가 넘겼는지에 달려 있습니다.

Agent 도구는 `get_realtime_quote`, `get_daily_history`, `get_chip_distribution`, `get_analysis_context`, `get_stock_info` 같은 도구를 따로 호출하기도 하므로, 일반 분석이 미리 가져온 데이터와 요청이 겹치기 쉽습니다. 현재 pack 생성은 Agent 이력 사전 조회 뒤 `storage.get_analysis_context()`의 일봉 사용 가능 상태만 재사용하며, 도구 단위의 완전한 pack cache를 재사용하거나 노출하지 않습니다. 더 깊은 데이터 품질 점수와 도구 캐시 재사용 여부는 P5에서 다시 정합니다.

### 경보
<!-- 계약 키(tests): ### 告警 -->

경보 경로는 `src/services/alert_worker.py`에서 규칙을 평가하고, 발동 이력을 기록하고, 알림을 보냅니다. 필드 의미는 [실시간 경보 센터](alerts.md)를 참고하십시오. `triggered`, `skipped`, `degraded`, `failed` 같은 경보 상태는 규칙 평가나 기록 상태이므로 필드 품질 enum에 바로 넣으면 안 됩니다.

첫 버전 pack은 경보 규칙 평가를 입력 데이터 블록으로 다루지 않습니다. 경보는 이후 pack의 필드 품질 요약만 사용합니다. 예를 들어 핵심 시세가 fallback인지, stale인지, partial인지 같은 정보입니다.

### 보유 종목
<!-- 계약 키(tests): ### 持仓 -->

보유 종목 스냅샷은 `src/services/portfolio_service.py`에서 계좌, 포지션, 원가, 가격, 환율, 리스크 입력을 모으며, API 출력 구조는 `api/v1/schemas/portfolio.py`에 있습니다. 현재 `price_source`, `price_provider`, `price_date`, `price_stale`, `price_available`, `fx_stale` 등의 필드가 있습니다.

첫 버전 pack은 "보유 여부, 계좌 요약, 원가, 수량, 비중, 평가 손익, 가격/환율 stale 요약"을 기록할 수 있지만, 거래 내역, 현금 내역, 기업 행위(corporate action), 계좌 전체 개인정보는 넣지 않습니다.

### 백테스트
<!-- 계약 키(tests): ### 回测 -->

백테스트 서비스는 `src/services/backtest_service.py`와 `src/repositories/backtest_repo.py`에서 과거 분석 기록과 일봉 데이터를 사용합니다. 기존 `parse_analysis_date_from_snapshot()`은 `analysis_history.context_snapshot.enhanced_context.date`로 분석 날짜를 해석합니다.

P0는 `enhanced_context.date`를 호환 경계로 표시해야 합니다. 이후 pack에서 더 명확한 날짜 필드를 추가할 수는 있지만, 마이그레이션 없이 현재 이력 스냅샷의 날짜 위치를 삭제하거나 이름을 바꾸면 안 됩니다.

### 이력
<!-- 계약 키(tests): ### 历史 -->

이력 상세는 `src/services/history_service.py`, `api/v1/endpoints/history.py`, `api/v1/schemas/history.py`에서 `raw_result`, `news_content`, `context_snapshot` 등의 필드를 반환합니다. 동기 analysis/status 응답도 `api/v1/endpoints/analysis.py`에서 `context_snapshot.enhanced_context`, `realtime_quote_raw`, 펀더멘털 fallback을 읽습니다.

P0는 이력 소비 면만 기록합니다. 완전한 pack은 기본적으로 이력 상세나 공개 API에 공개하면 안 됩니다. 이후 P4에서 보여 줄 필요가 있다면 요약, 출처, 저하 설명을 우선 노출해야 합니다.

### 알림
<!-- 계약 키(tests): ### 通知 -->

알림 경로는 `src/notification.py`에서 `AnalysisResult`, dashboard, market snapshot, data_sources 등의 출력을 사용하며, `sent`, `no_channel`, `partial_failed`, `all_failed` 같은 전달 상태를 기록합니다. 채널 설정과 경계는 [알림 기능 기준선](notifications.md)을 참고하십시오.

알림은 사실 데이터 계층이 아니므로, 전달 실패를 입력 품질 실패로 잘못 기록하면 안 됩니다. 이후 필요한 경우에만 pack 요약을 사용해야 합니다. 예: "실시간 시세 저하", "펀더멘털 누락", "뉴스 출처 부족".

## 소스 코드 기준점
<!-- 계약 키(tests): ## 源码锚点 -->

| 영역 | 기준점 |
| --- | --- |
| 일반 분석 | `src/core/pipeline.py`, `src/storage.py`, `src/analyzer.py` |
| Agent | `src/agent/orchestrator.py`, `src/agent/executor.py`, `src/agent/tools/data_tools.py` |
| 경보 | `src/services/alert_worker.py`, `docs/alerts.md` |
| 보유 종목 | `src/services/portfolio_service.py`, `api/v1/schemas/portfolio.py` |
| 백테스트 | `src/services/backtest_service.py`, `src/repositories/backtest_repo.py` |
| 이력 | `src/services/history_service.py`, `api/v1/endpoints/history.py`, `api/v1/endpoints/analysis.py`, `api/v1/schemas/history.py` |
| 알림 | `src/notification.py`, `docs/notifications.md` |

## 호환성과 보안 경계
<!-- 계약 키(tests): ## 兼容与安全边界 | 完整 pack 不默认公开 | 完整 webhook URL | 邮箱密码 -->

- `analysis_history.context_snapshot.enhanced_context.date`는 현재 백테스트 날짜 해석의 호환 지점이며, P1/P2는 마이그레이션 없이 이를 깨뜨리면 안 됩니다.
- 완전한 pack은 기본적으로 이력, API, Web, 알림에 공개하지 않습니다. P4/P5는 `analysis_context_pack_overview` 저민감 요약, 출처, fallback, stale, missing reason, block status count, `data_quality` 저민감 점수만 공개합니다.
- pack, 로그, 이력 스냅샷, API 응답에는 API key, token, cookie, 전체 webhook URL, 이메일 비밀번호, 비공개 환경 변수, 기타 키를 기록하면 안 됩니다.
- `source`, `timestamp`, `fallback`, `stale`, `partial` 같은 품질 메타데이터는 입력의 한계를 설명하는 데만 쓰며, 분석을 막는 데 쓰지 않습니다. 기존 핵심 경로가 원래 fail-fast인 경우만 예외입니다.
- #1386의 장전 / 장중 phase 인식은 이후 `phase` / `data_quality` 필드의 중요한 배경입니다. P0는 관계만 기록하며 runtime에는 연결하지 않습니다.
