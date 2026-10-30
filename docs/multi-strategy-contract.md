# 다중 전략 투자 제안 계약: Baseline 의미, Phase 1 수렴, Phase 2/3/4 범위

이 페이지는 Issue #1964 "다중 전략 투자 제안"의 주제 문서입니다. 두 개 이상의 전략·스킬(skill) 의견이 시스템 안에서 어떻게 **의미상 하나로 수렴하는지 그 경계**를 기록합니다. 대상은 유효한 근거 집합, 유효하지 않은 의견의 격리, 진영 나누기, 합의 수준, 여러 출력 화면 간 일관성입니다. Baseline은 계약 범위와 현재 상태 점검을 맡습니다. Phase 1은 Baseline 계약 안에서만 유효 근거 집합 분류, `strategy_synthesis`의 결정적(deterministic) 합성, DecisionAgent prompt 수렴, 네 가지 renderer의 일관성, E2E 반례 검증을 완성합니다. Phase 1.5는 Phase 1 계약 위에 통제된 협동 추론 v0(mediator_v0)을 추가합니다. 충돌 의제, 전략별 응답, softened(완화) 수정, 신뢰도 할인 사유만 기록합니다. Phase 1.6은 주입 가능한 LLM mediator v1(llm_mediator_v1)을 추가합니다. schema상 유효한 구조화 수정만 허용하며, 응답이 없거나 비정상이거나 범위를 벗어나면 v0으로 되돌립니다. Phase 1.7은 주입 가능한 strategy self-review v2(self_review_v2)를 추가합니다. 충돌에 참여한 전략만 고정된 schema로 자기 검토를 하며, 참여자 중 하나라도 범위를 벗어나면 그 회차 전체를 baseline으로 되돌립니다. Phase 1.8은 수정 투영 v3(revision_projection)을 추가합니다. softened 수정을 반영했을 때의 종합 신호, 신뢰도, 충돌 상태를 미리 보여 줄 뿐, 권위 있는 `final_signal`을 덮어쓰지 않습니다. Phase 1.9는 설정 가능한 다회차 협동 추론 v4(multi_round_v4)를 추가합니다. `max_rounds`만큼 구조화 수정을 이어 가며 `round_history`를 남기고, 어느 회차든 범위를 벗어나면 직전 회차의 검증된 결과로 돌아갑니다. Phase 2는 Phase 1/1.5/1.6/1.7/1.8/1.9 계약 아래에서 2~4개 전략의 동시 실행 스케줄링과 단계별 스케줄링만 추가합니다. Phase 3은 Phase 2 위에 프런트엔드의 다국어 전체 표시만 보완합니다. Phase 4는 같은 `CONTRACT_VERSION = "1.0"` 안에서 실제 Skill Outcome(스킬 결과) 기반 가중치 피드백 루프만 보완합니다. Baseline의 모든 제약은 이후 모든 Phase에 영구히 적용됩니다. 어떤 Phase N도 Baseline에서 고정한 경계를 조용히 낮출 수 없습니다.

## Skill opinion 표본 범위 (Issue #1904 P2 PR1)

`AgentRuntimeFacts.skill_opinions`는 개별 SkillAgent의 민감도가 낮은 필드만 투영합니다. 대상은 `skill_id`, canonical `signal`, `confidence`, 의견 시각입니다. `skill_consensus` / `strategy_consensus`, DecisionAgent, 기본 Agent, Invalid Opinion은 이 집합에 들어갈 수 없습니다. 한 번의 실행에서 같은 `skill_id`의 유효 의견이 여러 개 나오면 마지막 것만 남깁니다. SkillAgent는 처음 파싱할 때 숫자가 아니거나, 유한하지 않거나, `[0, 1]` 범위를 벗어난 confidence를 반드시 거부해야 합니다. AgentOpinion은 RuntimeFacts의 방어적 검증을 위해 입력 유효성 표시를 보존하며, 잘못된 입력을 clamp(범위 안으로 강제 조정)한 뒤 유효 표본으로 계속 쓰는 것은 금지합니다.

분석 기록이 저장되면 Pipeline은 best-effort 방식으로 `skill_opinion_samples` sidecar에 씁니다. 부모 기록의 존재 확인과 표본 삽입은 같은 SQLite 원자적 쓰기 트랜잭션 안에서 이뤄져야 합니다. 기록 삭제도 같은 쓰기 트랜잭션과 locked retry를 재사용합니다. 삽입과 삭제 중 무엇이 먼저 실행되든 고아 표본이 남으면 안 됩니다. 멱등 키는 `(analysis_history_id, skill_id, sample_schema_version)`이며, 다시 실행해도 처음 저장한 불변 표본을 덮어쓰면 안 됩니다. 쓰기 실패는 민감도가 낮은 오류 유형만 기록하며, 리포트, 기록 저장, DecisionSignal 주 흐름을 실패시키면 안 됩니다.

현재 `sample_schema_version=skill-opinion-sample-v1`입니다. `skill_version`과 `horizon`은 빈 값 호환용 자리로만 남겨 둡니다. 현재 Skill 정의와 SkillAgent 출력에는 믿을 만한 버전·기간 계약이 없으므로, 이 단계에서 LLM `raw_data`로부터 추측하거나 지어내면 안 됩니다. PR1은 outcome을 만들지 않고, skill 성과 통계를 제공하지 않으며, `get_skill_summary()`를 구현하지 않고, `AgentMemory` / `SkillAggregator` 가중치도 바꾸지 않습니다.

## Skill Opinion Outcome 범위 (Issue #1904 P2)

`skill_opinion_outcomes`는 불변인 `skill_opinion_sample` 하나가 특정 `horizon`(평가 기간), 특정 `engine_version`에서 얻은 독립적인 사후 결과를 나타냅니다. 고유 키는 `(skill_opinion_sample_id, horizon, engine_version)`입니다. 초기 horizon은 `1d`, `3d`, `5d`, `10d`만 허용합니다. 실행마다 지정하는 `limit`는 처리 대기 중인 `sample × horizon` outcome key 수를 제한하며, sample 수가 아닙니다. 명시적으로 빈 horizons, 공백뿐인 skill/stock 필터, 범위를 벗어난 limit는 fail closed(안전하게 거부)해야 하며, 전체 실행으로 바뀌면 안 됩니다.

각 outcome은 해당 sample 자신의 canonical `signal`만 사용합니다. 최종 Agent decision, `skill_consensus`, 다른 skill의 signal은 읽으면 안 됩니다. `strong_buy` / `buy`는 상승(bullish) 기준으로, `strong_sell` / `sell`은 하락(bearish) 기준으로 평가합니다. 방향 기준 수익률이 0보다 엄격히 클 때만 `hit`이고, 수익률 0은 `miss`입니다. `hold`는 가격 구간이 완전히 갖춰진 뒤 `observational`로 저장하며, 방향 적중 여부를 만들지 않습니다.

과거 분석 날짜는 `enhanced_context.date`에서 가져오고, 없을 때만 기록 생성 날짜로 대신합니다. Backtest(백테스트)와 Outcome은 종목 식별 해석, 지원되는 예전 시장 스냅샷 재구성, 권위 있는 시작 session(거래 세션) 판정을 공유합니다. 시장이 일치하고 유효한 `market_phase_summary.effective_daily_bar_date`를 우선 사용합니다. 이 필드가 없으면 phase와 거래일 달력으로 시작점을 증명할 수 있을 때만 추론하고, 그렇지 않으면 fail closed하며 임의의 더 이른 로컬 일봉을 고르면 안 됩니다. Outcome은 판정을 통과한 `expected_start_date`만 받습니다. Backtest는 기존 기록과의 호환을 위해, session이 아닌 `effective_daily_bar_date`에 해당하는 정확한 로컬 bar가 이미 있으면 명시적인 `backtest_start_date`로 읽기 전용 재생을 할 수 있습니다. 이 fallback은 권위 있는 Outcome 표본이 아니며, 잘못된 날짜 refill을 일으키지 않고, Skill Outcome 통계나 가중치 보정에도 들어가지 않습니다. 공유 구간 resolver는 지정한 시작점 중 완전한 구간을 우선하며, 시작 bar와 이후(forward) bar는 반드시 같은 저장 code 형태에서 와야 하고 여러 후보를 이어 붙이면 안 됩니다.

Outcome의 경우, 권위 있는 시작 session은 정해졌지만 해당 시작 bar가 아직 기록되지 않았거나 이후 로컬 일봉이 부족하면 재시도 가능한 `pending`으로 저장합니다. 후보 key는 마지막 시도 시각(outcome이 없으면 sample 생성 시각) 기준으로 공정하게 스케줄링합니다. 재시도할 때마다 `pending.updated_at`을 갱신해 대기열 맨 뒤로 보내므로, 계속 새로 생기는 누락 key가 오래된 재시도를 굶기지 않고, 재시도가 새 표본을 거꾸로 막지도 않습니다. 손상됐거나 분석 날짜보다 늦은 `effective_daily_bar_date`, 종목 시장과 스냅샷 시장의 충돌, 믿을 만한 phase와 거래일 달력으로 시작점을 증명할 수 없는 경우처럼 영구적으로 무효인 메타데이터는 최종 상태 `unable`로 저장합니다. 이것을 `missing_start_bar`로 꾸며 계속 재시도하면 안 됩니다. 같은 engine version에서는 `pending`만 갱신할 수 있고, `evaluated`, `observational`, `unable`은 덮어쓸 수 없습니다. 규칙이 바뀌면 engine version을 올려야 합니다. 기록 삭제는 같은 쓰기 트랜잭션 안에서 outcome → sample → history 순으로 명시적으로 정리하며, SQLite 외래 키 설정에 의존하면 안 됩니다.

Outcome 핵심 단계(#2116)는 이미 병합된 #2073을 바탕으로 Outcome evaluator, repository, service 핵심만 제공했습니다. 당시에는 성과 통계, 표본 충분성, 순위, 가중치 조정이 포함되지 않았습니다. 그 뒤의 읽기 전용 통계 단계는 다음 절에서 따로 정의합니다. 그 단계에서도 관리자 API, Schema, OpenAPI, 주 Pipeline 자동 실행을 추가하지 않으며, 런타임 가중치도 조정하지 않습니다. 이후 운영용 진입점이 필요하면 실제 호출자와 권한 계약을 근거로 따로 검토해야 합니다.

### Skill Opinion Outcome 성과 통계

Outcome 통계는 읽기 전용 데이터 영역이며 `skill_id + horizon + engine_version` 기준으로 bucket(묶음)을 독립적으로 나눕니다. 어떤 bucket도 같은 skill의 다른 horizon, 다른 skill, 다른 engine version, 전체 표본을 빌려 지표를 열 수 없습니다. 현재 고정 기준은 `evaluated >= 30`입니다. 개별 skill opinion 자신의 signal로 생긴 `hit` / `miss`만 evaluated에 들어갑니다. `pending`, `observational`, `unable`은 개수만 유지하며 표본 충분성에는 넣지 않습니다.

표본이 부족하면 bucket의 `sample_status`는 `observational`이 됩니다. 개수는 계속 반환하지만 `hit_rate_pct`, `miss_rate_pct`, `avg_directional_return_pct`, `unable_rate_pct`는 모두 `null`이며, 순위를 내거나 가중치를 추론하면 안 됩니다. 표본이 충분하면 hit/miss rate는 `hit + miss`를 분모로 하고, 평균 방향 수익률은 evaluated 행만 사용합니다. unable rate는 최종 상태 기록 `evaluated + observational + unable`을 분모로 하며, 일시적인 `pending`이 영구 실패 비율을 희석하면 안 됩니다.

읽기 전용 통계 단계(PR #2119) 자체는 `BacktestService.get_skill_summary()`, `AgentMemory`, `SkillAggregator`를 수정하지 않고, API, Pipeline 자동 실행, Web 표시도 추가하지 않습니다. 이 페이지 뒷부분의 Phase 4가 이 통계 계약 위에서 보수적인 런타임 가중치를 별도로 연결합니다. 현재 조합 구현도 이미 저장된 Outcome을 읽기만 하며, evaluator를 자동으로 실행하지 않습니다.

## 용어와 범위

현재 저장소에는 opinion / signal / consensus / synthesis라는 이름의 데이터 영역이 여러 개 있습니다. 기존 런타임 구조를 미래 phase로 잘못 적지 않도록 Baseline에서 먼저 뜻을 구분해야 합니다.

| 용어 | 현재 의미 | 현재 주요 사용처 | Baseline 범위 |
| --- | --- | --- | --- |
| `AgentOpinion` | `src/agent/protocols.py`에 있는, 모든 Agent(SkillAgent, TechnicalAgent, IntelAgent, RiskAgent, DecisionAgent 포함)가 만드는 의견 데이터 클래스입니다. `agent_name` / `signal` / `confidence` / `reasoning` / `key_levels` / `raw_data`를 담습니다. | Orchestrator, Aggregator, DecisionAgent, Disagreement, Renderer | 원본 의견을 담는 그릇으로 기록합니다. Baseline은 필드를 추가하지 않으며, `AgentOpinion`을 두 종류로 나누지도 않습니다. |
| `StrategyOpinion` | `src/agent/protocols.py`에 있는 내부 정규화 보기입니다. `skill_id` / `signal` / `original_signal` / `invalid_signal`을 담으며 Aggregator/Synthesizer 내부에서만 씁니다. | `SkillAggregator`, `ConflictDetector`, `StrategySynthesizer` | 내부 계산용 정규화 보기로 기록합니다. `ctx.opinions`, 공개 payload, DecisionAgent prompt에는 들어가지 않습니다. |
| Signal / Canonical Signal | 매매 신호의 정규화 라벨입니다. Canonical 값은 `strong_buy` / `buy` / `hold` / `sell` / `strong_sell` 다섯 개의 소문자 문자열뿐입니다. | 전체 경로 | 이후 모든 계산이 받을 수 있는 유일한 입력 형식으로 기록합니다. 대문자 별칭, `"strong buy"`, Signal 열거형 원래 값은 모두 먼저 `normalize_strategy_signal()`로 canonical 값으로 바꾼 뒤 계산에 참여해야 합니다. |
| Valid Opinion / Invalid Opinion | `is_valid_strategy_signal(signal) == True`이고 `invalid_signal=True`로 표시되지 않은 의견이 Valid(유효)이며, 나머지는 Invalid(무효)입니다. | Orchestrator 분류, Aggregator, DecisionAgent | 계약 수준의 유효·무효 판정으로 기록합니다. Baseline은 판정 함수와 의미만 정의하고, 분류가 일어날 위치는 미리 정하지 않습니다. |
| Evidence Chain | DecisionAgent prompt와 `strategy_synthesis` 수치 계산에 들어가는 **유효 의견 집합**입니다. | DecisionAgent, Aggregator | 의사결정 입력으로 기록합니다. Baseline은 Evidence Chain(근거 체인)이 Valid Opinion으로만 이뤄지며, Invalid는 섞일 수 없다고 정합니다. |
| Diagnostics | 무효 의견을 모아 두는 진단 공간입니다. 로그, 디버깅, 사용자에게 보이는 "그 밖에 N개 전략 해석 실패" 개수에만 씁니다. | Renderer 표시, 로그 | 진단 영역으로 기록합니다. Baseline은 Invalid가 반드시 Diagnostics로 가야 하며, 조용히 `hold`로 바뀌어 Evidence Chain에 섞이면 안 된다고 정합니다. |
| `strategy_synthesis` | `dashboard.strategy_synthesis` 최상위 payload입니다. `final_signal` / `consensus_level` / `conflict_severity` / `supporting_skills` / `opposing_skills` / `summary_params`를 담습니다. | Markdown, WeChat, Notification, History 네 가지 renderer | 공개용 저민감 payload로 기록합니다. Baseline은 이 payload가 **유일한 권위 있는 합성 출처**이며, LLM dashboard가 거꾸로 덮어쓸 수 없다고 정합니다. |
| `disagreement_summary` | `ctx.meta["agent_disagreement_summary"]`이며, `build_agent_disagreement_summary()`가 만드는 저민감 Agent 간 의견 차이 요약입니다. | DecisionAgent prompt, 로그 | 의사결정 경로의 힌트로 기록합니다. Baseline은 Valid Opinion으로만 bucket을 만들며, Invalid는 `bullish_agents` / `bearish_agents` / `neutral_agents`에 들어갈 수 없다고 정합니다. |
| Consensus Level | `strategy_synthesis.consensus_level`이며 값은 `high` / `medium` / `low` / `insufficient`입니다. | Renderer 표시, Aggregator 내부 판정 | 합의 수준 열거형으로 기록합니다. Baseline은 valid가 1개 이하이거나 `sum(confidence) == 0`이면 `insufficient`로 강제하며, `high`를 내면 안 된다고 정합니다. |

## Baseline 범위와 비목표

Baseline의 목표는 Phase 1/2/3/4가 모두 같은 의미 계약을 바탕으로 런타임 변경을 설계하게 하는 것입니다. PR마다 "유효 의견", "합의", "지지 측"을 새로 정의하지 않게 하려는 것입니다.

- Baseline은 SkillAgent → Orchestrator → Aggregator → Synthesizer → DecisionAgent → Disagreement → Renderer의 일곱 사용처에 걸친 의미 수렴 경계를 다룹니다.
- Baseline은 Canonical Signal 열거형, Valid/Invalid 판정 함수, Evidence Chain / Diagnostics 분리 원칙, 동적 이분 진영 의미, 합의 기준 단계, `strategy_synthesis` payload schema, 불변 조건 목록, 반례 매트릭스를 고정합니다. Phase 1은 이 경계를 처음으로 코드로 구현한 것입니다.
- Baseline은 동시 실행 스케줄링, 프런트엔드 다국어 전체 표시, 가중치 백테스트 피드백을 도입하지 않습니다. 이것들은 Phase 2/3/4에 남겨 둡니다.
- Baseline은 기존 `AgentOpinion` 필드를 바꾸지 않고, 데이터베이스 필드를 추가하지 않으며, API 반환 구조를 바꾸지 않고(`strategy_synthesis`는 이전 PR에서 이미 추가됨), 설정 항목도 추가하지 않습니다.
- Baseline은 계약을 범용 opinion registry로 확장하지 않습니다. `AgentOpinion` 구조는 기존 코드가 관리하며, 이 계약은 그것을 **의미상 어떻게 처리하는지**만 규정합니다.

## Baseline 내부 계약

### Canonical Signal과 Valid 판정 (Canonical Signal 与 Valid 判定)

Canonical Signal은 Baseline이 허용하는 **유일한 점수·가중·그룹 입력 형식**입니다. 정규화 진입점은 `src/agent/protocols.py`의 두 함수입니다.

- `normalize_strategy_signal(signal)`은 `(canonical, invalid, original)` 세 값을 반환합니다. `Signal` 열거형, 대소문자 문자열, `"strong buy"` / `"strong-buy"` 별칭을 받아 canonical 집합으로 통일합니다. 매핑할 수 없으면 `invalid=True`이고 `canonical`은 `default`(기본값 `"hold"`)로 떨어지지만, **반드시** `invalid=True`와 함께 하위로 전달해야 하며 단독으로 쓰면 안 됩니다.
- `is_valid_strategy_signal(signal)`은 Baseline 전체 경로에서 유효성 판정의 **단일 기준**입니다. 어떤 모듈이든 "이 opinion이 Evidence Chain에 들어갈 자격이 있는지" 판단할 때는 반드시 이 함수를 호출해야 합니다.

Baseline은 `_STRATEGY_SIGNAL_ALIASES` 외에 두 번째 canonical 매핑표를 두는 것을 금지합니다. ConflictDetector와 Synthesizer 내부의 `strategy_signal_score(canonical)`은 canonical 값만 받으며, `op.original_signal`이나 대소문자 변형으로 표를 조회하는 것은 금지합니다.

### Evidence Chain과 Diagnostics 분리 (Evidence Chain 与 Diagnostics 分离)

Baseline은 다음과 같이 정합니다.

- **Evidence Chain은 Valid Opinion 집합이며, 그것뿐입니다.** DecisionAgent prompt, `strategy_synthesis` 수치 계산, `disagreement_summary` bucket 생성은 모두 같은 Evidence Chain에서 읽어야 합니다.
- **Invalid Opinion은 반드시 Diagnostics로 갑니다**(`ctx.meta["invalid_opinions"]` 또는 동등한 필드). 로그, 진단, 사용자에게 보이는 "그 밖에 N개 전략 해석 실패" 개수에만 씁니다.
- 두 집합은 **서로 겹치지 않고 합치면 전체를 이룹니다**. 하나의 opinion은 Evidence Chain 아니면 Diagnostics 중 한 곳에만 있어야 하며, 두 곳에 동시에 있거나 어디에도 없으면 안 됩니다.
- Invalid Opinion은 조용히 `hold`로 바뀌거나, `confidence` 원래 값을 유지한 채, 이름 없이 `bullish_agents` / `bearish_agents` / `neutral_agents` bucket에 섞여 들어가면 **안 됩니다**.

Diagnostics 구조:

```python
ctx.meta["invalid_opinions"] = [
    {
        "agent_name": str,          # 원래 agent_name
        "raw_signal": str | None,   # 원래 signal 문자열 그대로(정규화 전)
        "confidence": float,        # 원래 confidence, 진단용일 뿐 어떤 계산에도 쓰지 않음
        "reason": str,              # "missing_signal" | "unrecognized_signal" | "invalid_flag"
    },
    ...
]
```

Baseline은 이 구조만 정하며, 분류가 일어나는 **코드 위치**는 정하지 않습니다. Phase 1에서 분류를 Orchestrator에 둡니다.

### 동적 이분 진영 (Supporting / Opposing) (动态二分阵营)

최종 신호 `final_signal`과 canonical score `final_score = strategy_signal_score(final_signal)`이 주어지면, 각 Valid Opinion `op`에 대해 `op_score = strategy_signal_score(op.signal)`를 계산합니다.

- **`final_signal == "hold"`(즉 `final_score == 3.0`)일 때**:
  - `op_score == 3.0` → `supporting_skills`
  - `op_score != 3.0` → `opposing_skills`(이견과 의견 차이로 모아 둡니다. 관망·이견 의견이 조용히 버려지지 않게 해서, 표시할 때 이견의 배경이 사라지지 않도록 합니다)

- **`final_signal`이 방향성 신호(`strong_buy` / `buy` / `sell` / `strong_sell`)일 때**:
  - 같은 방향(둘 다 상승 또는 둘 다 하락)이고 `abs(op_score - final_score) ≤ 1.0` → `supporting_skills`
  - 반대 방향이고 `abs(op_score - final_score) ≥ 2.0` → `opposing_skills`
  - 나머지(`abs(diff) < 2.0`이고 같은 방향이 아님) → `opposing_skills`(이견에 합쳐서, 세 번째 진영 `neutral_skills`가 생기지 않게 합니다)

Baseline은 **`neutral_skills`가 payload의 정식 필드가 아님**을 분명히 합니다. 모든 Valid Opinion은 `supporting_skills`와 `opposing_skills` 중 **정확히 하나**에 들어가야 하며, 분류 결과의 총 개수는 `summary_params.opinion_count`와 같아야 합니다.

### 합의 수준 기준 (共识度门槛)

Baseline은 valid 표본 수에 따라 단계적으로 합의 수준을 판정합니다.

| valid 개수 | consensus_level | 설명 |
| --- | --- | --- |
| 0 | `insufficient` | 종합할 근거가 없습니다. final_signal은 `hold`로 강제되고 `confidence=0.0`입니다 |
| 1 | `insufficient` | 표본 하나는 "합의"가 아닙니다. final과 완전히 같더라도 `high`를 내면 안 됩니다 |
| ≥ 2, `sum(confidence) == 0` | `insufficient` | 유효 근거의 신뢰도가 0이라 합의를 세울 수 없습니다 |
| ≥ 2, `sum(confidence) > 0` | aligned_ratio 판정으로 이동 | 아래 표 참고 |

Aligned Ratio(같은 방향 비율) 판정(valid ≥ 2이고 `sum(confidence) > 0`):

| 조건 | consensus_level |
| --- | --- |
| `conflict_severity == "high"` | `low` |
| `aligned_ratio ≥ 2/3`이고 `conflict_count == 0`(`conflict_severity == "none"`과 같음) | `high` |
| `conflict_severity == "medium"`이고 `aligned_ratio < 0.5` | `low` |
| 나머지 | `medium` |

여기서 `aligned = final_signal과 같은 방향이고 score 차이가 1.0 이하인 valid 개수`, `aligned_ratio = aligned / len(valid)`입니다.

Baseline은 `sum(...) or 1.0` 같은 대체값으로 가중치 0을 분모 1처럼 가리는 것을 금지합니다. 가중치 0은 반드시 명시적으로 `insufficient` 분기로 보내고, `final_signal`은 `hold`로 되돌려야 합니다.

### `strategy_synthesis` Payload Schema

```json
{
  "final_signal": "hold",                 // canonical signal
  "weighted_score": 3.0,                  // 소수 넷째 자리까지 유지
  "confidence": 0.72,                     // 할인 후 신뢰도
  "original_confidence": 0.80,            // 할인 전 가중 신뢰도
  "conflict_count": 0,
  "conflict_severity": "none",            // none | low | medium | high
  "conflicts": [ /* ConflictDetector가 출력한 dict 목록 */ ],
  "supporting_skills": [ /* opinion item */ ],
  "opposing_skills":   [ /* opinion item */ ],
  "consensus_level": "high",              // high | medium | low | insufficient
  "summary_key": "strategy_synthesis.no_conflicts",   // 동적 i18n 요약 키 이름, 합의·충돌 상태에 따라 정해짐
  "summary_params": {
    "opinion_count": 2,                   // valid 표본 수(Evidence Chain 크기)
    "total_opinion_count": 4,             // valid + invalid(분류 전 원래 입력 총수)
    "invalid_opinion_count": 2,           // Diagnostics 길이
    "final_signal": "hold",
    "consensus_level": "high",
    "conflict_severity": "none",
    "conflict_count": 0
  },
  "deliberation": {                       // 선택 항목. 실질적 충돌(material conflicts)이 있을 때만 생성
    "status": "completed",
    "mode": "multi_round_v4",
    "rounds": 2,
    "agenda": [ /* conflict agenda item */ ],
    "responses": [ /* 의제별 참여자 응답 */ ],
    "summary": {
      "resolution_status": "partially_resolved",
      "resolved_conflict_count": 0,
      "unresolved_conflict_count": 1,
      "minority_view_preserved": true,
      "confidence_adjustment": -0.06,
      "confidence_adjustment_reason_key": "deliberation.confidence.high_partially_resolved"
    },
    "round_history": [
      {
        "round": 1,
        "source_mode": "mediator_v0",
        "status": "baseline",
        "changed_response_count": 2,
        "confidence_adjustment": -0.06
      },
      {
        "round": 2,
        "source_mode": "multi_round_v4",
        "status": "accepted",
        "changed_response_count": 1,
        "confidence_adjustment": -0.09
      }
    ]
  },
  "revision_projection": {                // 선택 항목. deliberation이 있을 때만 만드는 미리보기
    "status": "computed",
    "mode": "preview_only",
    "source_mode": "mediator_v0",
    "projected_signal": "hold",
    "projected_weighted_score": 3.0,
    "projected_confidence": 0.6696,
    "projected_original_confidence": 0.72,
    "projected_conflict_count": 1,
    "projected_conflict_severity": "medium",
    "projected_consensus_level": "low",
    "changed_skill_count": 2,
    "changed_skills": ["trend_v1", "theme_v1"],
    "final_signal_overridden": false
  }
}
```

Opinion Item 구조(`supporting_skills` / `opposing_skills`의 각 원소):

```json
{
  "skill_id": "trend_v1",
  "agent_name": "skill_trend_v1",
  "signal": "hold",              // canonical
  "confidence": 0.80,            // 소수 넷째 자리까지 유지
  "reasoning": "...",
  "score_adjustment": 0,
  "conditions_met": []
}
```

Baseline은 `strategy_synthesis`가 **SkillAggregator의 결정적 알고리즘이 만든 유일한 권위 있는 합성 결과**임을 분명히 합니다. Orchestrator의 `_collect_strategy_synthesis()`는 `ctx.get_data("skill_consensus")`의 synthesis를 우선 사용해야 하며, SkillAggregator가 결과를 만들지 못했을 때만 `ctx.opinions`의 `skill_consensus` opinion으로 대체할 수 있습니다. **LLM이 반환한 dashboard는 `dashboard.strategy_synthesis`를 덮어쓰거나 수정할 수 없습니다.** `normalize_dashboard_payload`는 LLM 출력을 받을 때 LLM 쪽 `strategy_synthesis` 필드를 제거해, LLM 환각이 권위 있는 합성 결과를 오염시키지 않게 해야 합니다.

### Strategy Deliberation v0 (Phase 1.5)

`strategy_synthesis.deliberation`은 선택적인 협동 추론 블록이며, 중간 이상 강도의 충돌이나 명확한 핵심 충돌 유형이 있을 때만 만듭니다. v0은 결정적인 `mediator_v0`을 쓰며, LLM을 호출하지 않고, 전략끼리 자유롭게 대화하게 하지 않으며, 원래 opinion을 수정하지 않고, `final_signal`도 다시 계산하지 않습니다. 하는 일은 충돌을 감사 가능한 의제로 바꾸고, 전략별 응답, 가벼운 수정, 종합 신뢰도 할인 사유를 기록하는 것입니다.

발생 조건:

- `len(valid_opinions) >= 2`
- 그리고 `severity in {"medium", "high"}`인 conflict가 있거나, conflict type이 `directional_opposition` / `high_confidence_dissent`에 속함

v0 revision은 다음만 허용합니다.

- `unchanged`: 원래 의견을 유지합니다.
- `softened`: confidence만 낮추거나, `strong_buy -> buy`, `strong_sell -> sell`로 바꿉니다. `buy` / `sell` / `hold`는 뒤집지 않고 confidence만 낮출 수 있습니다.

v0이 명확히 금지하는 것:

- `reversed`: 의견을 뒤집으면 안 됩니다.
- `final_signal`을 다시 계산하는 것.
- 다회차 토론, 동시 실행 스케줄링, 프런트엔드 표시, 새 설정 항목을 도입하는 것.

`deliberation.summary.confidence_adjustment`는 `StrategySynthesizer`가 원래 conflict severity에 따라 할인한 뒤에 추가로 적용하는 보수적 할인일 뿐입니다. 높은 충돌이 일부 해소되면 기본 약 `-0.06`, 해소되지 않으면 약 `-0.08`입니다. 중간 충돌이 일부 해소되면 기본 약 `-0.04`, 해소되지 않으면 약 `-0.05`입니다. 이 필드는 반드시 payload에 남겨, 나중에 renderer나 Web UI가 "왜 신뢰도가 더 낮아졌는지" 보여 줄 수 있게 해야 합니다.

### LLM Mediator v1 (Phase 1.6)

`llm_mediator_v1`은 `StrategyDeliberation`의 주입 가능한 강화 모드이며 기본 런타임 동작이 아닙니다. 호출자는 `StrategySynthesizer(deliberation_mediator=...)`에 `LLMDeliberationMediator`를 주입할 수 있습니다. 이것은 먼저 v0 baseline agenda를 만든 다음, 민감도가 낮은 구조화된 opinions/conflicts/baseline payload를 LLM callable에 보냅니다. LLM은 같은 schema의 JSON 객체만 반환할 수 있습니다. 텍스트, 잘못된 JSON, 필드 누락, ID 변경, 범위를 벗어난 revision을 반환하면 무조건 v0으로 되돌려야 합니다.

v1 schema 검사:

- `agenda`는 v0의 `agenda_id` 집합을 유지해야 합니다. 참여자를 추가, 삭제, 교체하면 안 됩니다.
- `responses`는 v0의 `(agenda_id, skill_id)` 집합을 모두 포함해야 합니다. 참여하지 않은 전략을 추가하면 안 됩니다.
- `revision`은 `unchanged` / `softened`만 허용하며, `reversed`는 계속 금지합니다.
- v0 baseline에서 이미 `softened`인 response는 계속 `softened`여야 하며, original signal로 되돌리면 안 되고, `revised_confidence`가 baseline의 검증된 값보다 높아지면 안 됩니다.
- v0 baseline이 `unchanged`인 response는 그대로 두거나 원래 규칙에 따라 `softened`로 바꿀 수 있습니다. signal을 뒤집거나 confidence를 높이면 안 됩니다.
- `summary.confidence_adjustment`는 v0 baseline보다 낙관적이면 안 되며, 1회 추가 할인 하한은 `-0.10`입니다. LLM이 결정적 할인을 취소하지 못하게 하기 위해서입니다.

v1 출력이 검사를 통과하면 `deliberation.mode="llm_mediator_v1"`이고, 그렇지 않으면 `mediator_v0` 출력을 유지합니다. v1도 전략 agent의 자기 검토를 호출하지 않고, 다회차 토론을 하지 않으며, `final_signal`을 다시 계산하지 않고, 설정 항목을 추가하지 않습니다.

### Strategy Self-Review v2 (Phase 1.7)

`self_review_v2`는 `StrategyDeliberation`의 주입 가능한 자기 검토 모드이며 기본 런타임 동작이 아닙니다. 호출자는 `StrategySynthesizer(deliberation_mediator=...)`에 `StrategySelfReviewMediator`를 주입할 수 있습니다. 이것은 먼저 baseline deliberation(`mediator_v0` 또는 검사를 통과한 `llm_mediator_v1`)을 얻은 뒤, 각 baseline response의 `(agenda_id, skill_id)`마다 자기 검토 callable을 호출합니다. 나중에는 실제로 충돌에 참여한 strategy agent가 이 callable을 실행할 수 있습니다. 현재 계약은 입력·출력과 성능 저하 시 대체 동작만 정합니다.

v2 self-review 검사:

- 각 baseline response는 자기 자신의 response JSON만, 정확히 하나 반환해야 합니다. 다른 전략의 응답을 수정하면 안 됩니다.
- 반환된 `agenda_id` / `skill_id`는 baseline response와 완전히 같아야 합니다.
- `revision`은 여전히 `unchanged` / `softened`만 허용하며, `reversed`는 계속 금지합니다.
- baseline이 이미 `softened`이면 `unchanged`로 되돌리거나, original signal을 복원하거나, baseline `revised_confidence`를 높이면 안 됩니다.
- baseline이 `unchanged`이면 그대로 두거나 원래 규칙에 따라 `softened`로 바꿀 수 있습니다. signal을 뒤집거나 confidence를 높이면 안 됩니다.
- v2가 검사를 통과한 responses로 summary를 다시 계산할 때, 최종 `confidence_adjustment`는 입력 baseline보다 낙관적이면 안 됩니다.
- 참여자 중 하나라도 응답이 없거나, 잘못된 JSON, ID 변경, 권한 밖 수정, `reversed` 시도가 있으면 그 회차의 self-review 전체를 baseline deliberation으로 되돌립니다. 일부만 유효한 자기 검토를 섞어 쓰는 것은 금지합니다.

v2 출력이 검사를 통과하면 `deliberation.mode="self_review_v2"`입니다. v2도 한 회차만 하며, 동시 실행 스케줄링을 추가하지 않고, `final_signal`을 다시 계산하지 않으며, 원래 opinion을 바꾸지 않고, 설정 항목을 추가하지 않습니다.

### Revision Projection v3 (Phase 1.8)

`strategy_synthesis.revision_projection`은 선택적인 미리보기 블록이며, `deliberation`이 있을 때만 `StrategySynthesizer`가 계산합니다. v0/v1/v2 schema 검사를 이미 통과한 `responses`를 읽어, `revision="softened"`인 응답을 임시 `StrategyOpinion` 사본에 적용한 다음, confidence 가중 score로 새 종합 결과를 미리 봅니다.

v3 출력 범위:

- `revision_projection.mode`는 `preview_only`로 고정합니다.
- `source_mode`는 투영의 출처를 기록합니다: `mediator_v0` / `llm_mediator_v1` / `self_review_v2`.
- `projected_signal` / `projected_weighted_score` / `projected_confidence`는 softened 수정을 반영했을 때의 미리보기 결과만 설명합니다.
- `projected_conflict_count` / `projected_conflict_severity` / `projected_consensus_level`은 임시 수정 사본으로 다시 검출한 값이며, 원래 conflicts를 고쳐 쓰지 않습니다.
- `changed_skill_count` / `changed_skills`는 실제로 softened된 전략만 셉니다.
- `final_signal_overridden`은 반드시 `false`로 고정해, v3가 권위 있는 최종 신호를 덮어쓰지 않음을 분명히 합니다.

v3가 명확히 금지하는 것:

- `projected_signal`을 최상위 `final_signal`에 다시 쓰는 것.
- `projected_weighted_score`를 최상위 `weighted_score`에 다시 쓰는 것.
- `projected_confidence`를 최상위 `confidence`에 다시 쓰는 것.
- `deliberation`이 없는 상황에서 빈 projection을 출력하는 것.
- v0/v1/v2 검사를 거치지 않은 자유 텍스트, 뒤집힌 신호, 새로 추가된 전략 응답을 받아들이는 것.

v3는 투영 진입점에서 `original_signal`, 허용된 softened signal, `revised_confidence` 상한을 다시 확인합니다. 호출자가 내장 mediator 검사를 거치지 않은 사용자 정의 결과를 주입하더라도, 더 공격적인 response를 임시 opinion 사본에 적용하지 않습니다.

### Configurable Multi-Round Deliberation v4 (Phase 1.9)

`multi_round_v4`는 `StrategyDeliberation`의 주입 가능한 다회차 강화 모드이며 기본 런타임 동작이 아닙니다. 호출자는 `StrategySynthesizer(deliberation_mediator=...)`에 `MultiRoundDeliberationMediator`를 주입하고, 생성자 인자로 다음을 설정할 수 있습니다.

- `fallback`: 첫 회차 baseline mediator입니다. `mediator_v0`, `llm_mediator_v1`, `self_review_v2` 중 하나입니다.
- `max_rounds`: 전체 회차 상한이며 범위는 `1–4`입니다. `1`이면 fallback baseline만 유지하는 것과 같습니다.
- `stop_when_stable`: 어떤 회차에서 response 변화가 전혀 없을 때 일찍 멈출지 여부이며, 기본값은 켜짐입니다.
- `round_completion(round_index, messages)`: 다음 회차의 구조화 수정 callable이며, 같은 schema의 JSON만 반환할 수 있습니다.

v4 회차 검사:

- 매 회차는 직전 회차의 `agenda_id` 집합과 `(agenda_id, skill_id)` response 집합을 유지해야 합니다. 참여자를 추가, 삭제, 교체하면 안 됩니다.
- `revision`은 여전히 `unchanged` / `softened`만 허용하며, `reversed`는 계속 금지합니다.
- 직전 회차에서 이미 `softened`인 response는 `unchanged`로 돌아갈 수 없습니다.
- 직전 회차에서 이미 `softened`인 response는 `revised_signal`을 바꿀 수 없고, `revised_confidence`를 높일 수도 없습니다.
- 직전 회차에서 `unchanged`인 response는 계속 `unchanged`로 두거나, 원래 규칙에 따라 `softened`로 바꿀 수 있습니다.
- `summary.confidence_adjustment`는 양수가 될 수 없고, 직전 회차보다 낙관적이어서도 안 됩니다. 회차당 하한은 여전히 v1 검사에 따라 `-0.10`으로 제한합니다.
- 어느 회차에서든 잘못된 JSON, ID 변경, 범위를 벗어난 revision, softened 취소, confidence 상승이 있으면 이후 회차를 멈추고 직전 회차의 검증된 결과를 반환합니다. 2회차에서 바로 실패하면 fallback baseline을 유지합니다.

v4 출력:

- 추가 수정을 적어도 한 회차 받아들였으면 `deliberation.mode="multi_round_v4"`입니다.
- `deliberation.rounds`는 실제로 받아들인 전체 회차 수를 기록합니다.
- `deliberation.round_history`는 baseline과 받아들인 각 회차의 `round`, `source_mode`, `status`, `changed_response_count`, `confidence_adjustment`를 기록합니다.
- v4도 최상위 `final_signal`을 다시 계산하지 않고, 원래 opinion을 바꾸지 않으며, 최상위 `weighted_score`나 `confidence`를 직접 덮어쓰지 않습니다. 최상위 confidence는 최종 `deliberation.summary.confidence_adjustment`만 읽어 보수적으로 할인합니다.

### 핵심 불변 조건

Baseline의 의미 경계는 아홉 개의 불변 조건으로 정리됩니다. 모든 Phase N 구현은 이 아홉 가지를 동시에 만족해야 하며, 하나라도 어기면 계약 위반으로 봅니다.

| ID | 불변 조건 | 상황 | 기대 결과 |
| --- | --- | --- | --- |
| I-1 | Evidence Chain 배타성 | 어떤 모듈이든 Evidence Chain을 읽을 때 | 집합 안의 모든 항목이 `is_valid_strategy_signal == True`여야 하며, Invalid는 나올 수 없습니다 |
| I-2 | 조용한 변환 금지 | signal이 없거나 인식할 수 없을 때 | Diagnostics로 보내며, `hold`로 바꿔 Evidence Chain에 섞거나 bucket을 만들면 안 됩니다 |
| I-3 | 근거 0 → insufficient | 유효 신호가 있지만 `sum(confidences) == 0`이거나, valid 개수 = 0 | `final_signal="hold"`, `weighted_confidence=0.0`, `consensus_level="insufficient"`. `strong_sell`이나 어떤 방향성 신호도 내면 안 됩니다 |
| I-4 | 표본 하나 → insufficient | valid opinion이 정확히 1개 | final과 완전히 같더라도 `consensus_level="insufficient"` |
| I-5 | Hold-final 일관성 | `final_signal == "hold"`이고 hold인 valid opinion이 2개 이상 | 모든 hold opinion은 `supporting_skills`에 들어가야 합니다. consensus_level과 supporting_skills 개수의 관계가 서로 맞아야 합니다(`high`이면 supporting이 2/3 이상) |
| I-6 | Payload와 renderer의 의미 일치 | `dashboard.strategy_synthesis` 값 | 네 가지 renderer(Markdown / WeChat / Notification / History)의 실제 텍스트가 payload와 완전히 일치해야 하며, "합의 수준: 높음 + 지지 전략: 없음" 같은 모순된 조합이 나오면 안 됩니다 |
| I-7 | Canonical 우선 점수 계산 | Aggregator / ConflictDetector / Synthesizer 내부의 점수 계산, 가중, 충돌 판정, 그룹 나누기 | 반드시 `normalize_strategy_signal()`이 반환한 canonical 소문자 값을 써야 합니다. 대문자 `"BUY"`, 별칭 등 원래 문자열로 `strategy_signal_score`를 바로 조회하면 안 됩니다 |
| I-8 | 다국어 빈 자리 표시 | `supporting_skills` / `opposing_skills`가 비었을 때의 표시 | 반드시 `report_language`에 따라 `labels.none_label`을 조회해야 합니다. 코드나 템플릿에 중국어 `"无"` / 영어 `"None"` / 한국어 `"없음"` 문자열을 직접 쓰면 안 됩니다 |
| I-9 | Deliberation의 단조 보수성 | v1/v2/v4가 직전 단계의 검증된 baseline을 수정하고, v3가 projection을 적용할 때 | 기존 `softened`를 취소하거나, original signal을 복원하거나, baseline revised confidence나 baseline confidence adjustment를 높이면 안 됩니다. 범위를 벗어난 결과는 직전 단계로 되돌립니다 |

## Phase 1 의미 수렴 (이 PR의 전달 범위)

Phase 1은 Baseline 계약을 처음으로 코드로 구현한 것입니다. Phase 1은 **새 계약 조항을 추가하지 않고**, Baseline이 이미 고정한 경계를 구체적인 코드에 반영할 뿐입니다. 대상은 Orchestrator 분류, Aggregator/Synthesizer 계산 수렴, DecisionAgent prompt 수렴, Disagreement 수렴, 네 가지 renderer 일관성, E2E 반례 검증입니다.

Phase 1이 다루는 진입점:

- `src/agent/protocols.py`: 단일 기준인 `is_valid_strategy_signal()`을 추가하고, `normalize_strategy_signal()`은 invalid 상태 비트를 유지합니다.
- `src/agent/skills/engine.py`: `StrategyEngine.process()`가 `partition_only()`로 유일한 권위 있는 분류를 마친 뒤, `process_partition()`이 집계와 합성을 진행합니다. Valid는 Evidence Chain에 남고, Invalid는 Diagnostics에 기록됩니다.
- `src/agent/orchestrator.py`: DecisionAgent 실행 전에 `_run_strategy_engine(ctx)`를 호출합니다. timeout / budget-skip으로 일찍 끝나는 경로는 `_apply_partition_fallback(ctx)`를 호출해 분류만 하고 합성은 하지 않아, Invalid가 근거 체인으로 되돌아오지 않게 합니다.
- `src/agent/skills/aggregator.py`: `StrategyEngine`이 `valid_skill_opinions`를 `SkillAggregator.calculate()`에 넘깁니다. 수학 계산은 valid opinion만 사용하며, `valid_weight_sum == 0`이면 명시적으로 `insufficient` 분기로 갑니다.
- `src/agent/skills/synthesis.py`: `ConflictDetector` / `StrategySynthesizer`는 canonical signal로 계산합니다. `_group_opinions()`는 §"동적 이분 진영"(动态二分阵营)대로, `_consensus_level()`은 §"합의 수준 기준"(共识度门槛)대로 구현합니다. `summary_params`에 `invalid_opinion_count` / `total_opinion_count`를 보완합니다.
- `src/agent/agents/decision_agent.py`: `build_user_message()`는 `ctx.opinions`를 바로 사용하며 두 번 거르지 않습니다. prompt에 `ctx.meta["invalid_opinions"]` 개수를 그대로 보여 줍니다.
- `src/agent/disagreement.py`: `build_agent_disagreement_summary()`는 `ctx.opinions`를 바로 사용합니다(StrategyEngine이 이미 분류했고 Orchestrator가 다시 기록했기 때문). Invalid는 `bullish_agents` / `bearish_agents` / `neutral_agents` 세 bucket 어디에도 나오지 않습니다.
- `src/services/report_renderer.py`, `templates/report_markdown.j2`, `templates/report_wechat.j2`, `src/notification.py`, `src/services/history_service.py`: `strategy_synthesis.supporting_skills` / `opposing_skills` / `consensus_level` / `summary_params.invalid_opinion_count`를 읽습니다. 빈 목록은 `labels.none_label`로 출력하고, 더 이상 `neutral_skills`를 사용하지 않습니다.
- `src/report_language.py`: `labels.none_label`을 zh/en/ko 세 언어 모두에서 갖춥니다. 합의 수준과 진단 개수 문구도 갖춥니다.
- `tests/test_multi_agent.py`: E2E-A..G 반례 매트릭스를 추가합니다. SkillAgent 입력 → StrategyEngine 분류·집계 → DecisionAgent prompt → dashboard payload → renderer 실제 텍스트까지 전체 경로를 검증합니다.

Phase 1은 `AgentOpinion` 필드, API 반환 구조, 데이터베이스 schema를 바꾸지 않고, 설정 항목을 추가하지 않으며, 기존 skill의 실행 방식도 바꾸지 않습니다.

## Phase 2 동시 실행 스케줄링

Phase 2는 Phase 1/1.5/1.6/1.7/1.8/1.9 계약 아래에서 2~4개 전략의 동시 실행 스케줄링과 단계별 스케줄링만 추가합니다.

- `src/agent/skills/scheduler.py::AgentSkillScheduler`는 thread pool로 specialist skill agent들을 동시에 실행합니다. 각 skill은 `AgentContext` 사본으로 실행되며, 별도의 `copy_context()`로 주 파이프라인이 고정해 둔 target date 같은 `ContextVar` 상태를 worker에 전달합니다. 주 스레드는 라우팅 순서대로 구조화된 opinion을 합치므로, 여러 skill이 공유 `ctx.opinions`에 동시에 쓰지 않습니다.
- specialist 최종 진입점은 최대 4개 전략을 고릅니다. `AGENT_SKILL_CONCURRENCY`는 동시에 실행되는 worker 수를 정하며 기본값은 `3`, 범위는 `1–4`입니다. 기본값에서는 4번째 전략이 다음 동시 실행 묶음(wave)으로 넘어가며, 라우팅 단계에서 조용히 버려지지 않습니다.
- `AGENT_SKILL_AGENT_TIMEOUT_S`는 계속 skill 하나의 독립 시간 제한 상한입니다. Pipeline 전체 예산이 켜져 있으면 `_run_stage_agent()`는 여전히 Pipeline 남은 예산과 skill 독립 상한 중 작은 값을 씁니다.
- skill 하나가 시간 초과되거나 예외가 나면 Diagnostics 경로(`reason="skill_timeout"` / `"skill_error"`)로 가서 `ctx.meta["invalid_opinions"]`에 들어가며, 다른 skill과 주 흐름을 막지 않습니다.
- Phase 2는 Baseline의 Evidence Chain / Diagnostics 분리 원칙, 진영 의미, 합의 기준, `strategy_synthesis` payload schema를 바꾸지 않습니다.
- Phase 2는 renderer 표시 로직을 바꾸지 않습니다. scheduler의 timeout/error/no-opinion과 signal 검증 실패는 모두 StrategyEngine의 권위 있는 Diagnostics로 모이며, `invalid_opinion_count` / `total_opinion_count`가 이렇게 실패한 skill까지 포함합니다.
- `ctx.meta["skill_scheduler"]`는 런타임 진단용일 뿐입니다. 스케줄링 모드, 동시 실행 수, skill별 timeout, 스케줄된 수, 완료 수, invalid 수를 기록하며, 종합 점수 계산에 참여하면 안 됩니다.

## Phase 3 프런트엔드 다국어 전체 표시 (이 PR에서는 하지 않음)

Phase 3은 Phase 2 위에 프런트엔드(`apps/dsa-web/`, `apps/dsa-desktop/`)의 `strategy_synthesis` 다국어 전체 표시만 보완합니다.

- Web 리포트 상세 페이지에 `final_signal` / `consensus_level` / `supporting_skills` / `opposing_skills` / `conflicts` / `invalid_opinion_count`를 표시합니다.
- 데스크톱 앱은 Web 표시 로직을 재사용합니다.
- 다국어 라벨 표는 `src/report_language.py`에 이미 있는 zh/en/ko 세 언어를 재사용합니다. 프런트엔드는 투영만 하며 새로 정의하지 않습니다.
- Phase 3은 Baseline 계약을 바꾸지 않고, payload 필드나 API 엔드포인트를 추가하지 않습니다.

## Phase 4 Skill Outcome 가중치 피드백 루프

Phase 4는 같은 `CONTRACT_VERSION = "1.0"` 안에서, 실제로 출처를 추적할 수 있는
개별 Skill Outcome만으로 런타임 상대 가중치를 조정합니다. 가중치 통계는 계속
`skill_id + horizon + engine_version` 기준으로 엄격히 bucket을 나눕니다. 각 horizon은
독립적으로 `evaluated >= 30`을 만족해야 하며, horizon, skill, engine version을 넘나들며
표본을 이어 붙여 가중치를 열면 안 됩니다.

충분한 bucket 하나는 대칭 `Beta(15, 15)` 사전 분포로 적중률을 수축(shrinkage)합니다.

```text
n = hit + miss
posterior_hit_rate = (hit + 15) / (n + 30)
direction_score = 2 * posterior_hit_rate - 1
unable_rate = unable / (evaluated + observational + unable)
bucket_score = clamp(direction_score - 0.25 * unable_rate, -1, 1)
evidence_strength = n / (n + 30)
```

`pending`은 unable rate 분모에 들어가지 않으며, `observational` / `unable`로
evaluated 기준을 채울 수 없습니다. 현재 opinion에는 믿을 만한 horizon이 없으므로,
각자 기준을 이미 만족한 bucket들에 대해서만 근거 강도로 가중한 모델 평균을 냅니다.

```text
combined_score =
    sum(bucket_score * evidence_strength)
    / sum(evidence_strength)
performance_factor = exp(ln(1.2) * combined_score)
effective_weight = opinion.confidence * performance_factor
```

`performance_factor`는 곱셈 기준으로 대칭인 구간 `[1 / 1.2, 1.2]`로 제한됩니다.
충분한 bucket이 없거나, 통계 읽기가 실패하거나, bucket이 손상됐거나, 수치가 유한하지
않거나, `AGENT_SKILL_AUTOWEIGHT=false`이면 반드시 중립 인자 `1.0`을 반환해야 합니다.
가중치 계산이 실패해도 분석을 중단하면 안 됩니다. 런타임은 더 이상 `BacktestService`의
전체 또는 출처를 추적할 수 없는 summary를 Skill 성과인 것처럼 쓰지 않습니다. 이 단계는
이미 저장된 Outcome을 읽기만 하며, evaluator를 위한 Pipeline, API, 예약 실행 진입점을
추가하지 않습니다.

`avg_directional_return_pct`는 현재 읽기 전용 설명 지표일 뿐이며 가중치에 참여하지
않습니다. 평균만 있고 분산이나 표준오차가 없는 상태에서 공식에 바로 넣으면 가짜
정밀도가 생깁니다. 나중에 수익률을 쓰려면 먼저 버전이 매겨진 위험 조정 수익률 계약을
세워야 합니다.

Phase 4는 Baseline의 canonical signal / valid 판정 / 합의 기준 / 진영 의미를 바꾸지 않습니다.
가중치 변화는 `weighted_score`와 `confidence`에만 영향을 주고, `consensus_level`
판정 경로에는 영향을 주지 않습니다. `AGENT_ARCH=single`은 `SkillAggregator`를 거치지 않으므로 호환성이 유지됩니다.

## 사용처 점검

Baseline의 일곱 사용처는 반드시 아래 표대로 역할을 나눠야 하며, 서로의 내부 데이터를 넘나들며 사용하면 안 됩니다.

### SkillAgent

각 skill은 `src/agent/skills/skill_agent.py`를 통해 `AgentOpinion`을 만듭니다. Baseline은 skill이 어떤 signal 문자열이든(대문자, 별칭, `Signal` 열거형 포함) 출력하는 것을 허용하며, 데이터 부족으로 `signal=None`이나 필드 누락을 내는 것도 허용합니다. 이런 경우는 하위 분류 단계가 처리하며, skill 스스로 걸러 내지 않습니다.

### StrategyEngine / Orchestrator (분류와 연결)

Phase 1에서는 DecisionAgent 실행 전에 Orchestrator가 `_run_strategy_engine(ctx)`를 호출합니다.

- `StrategyEngine.partition_only()`는 `agent_name`이 `is_skill_agent_name()`에 해당하는 모든 의견을 순회하며, `normalize_strategy_signal()`로 canonical signal을 유지합니다.
- Invalid는 Evidence Chain에서 빼서 `StrategyResult.invalid_records`에 기록하고, Orchestrator가 이것을 다시 `ctx.meta["invalid_opinions"]`에 넣습니다.
- `StrategyEngine.process_partition()`은 `valid_skill_opinions`만 Aggregator/Synthesizer에 넘깁니다. 만들어진 consensus opinion과 `skill_consensus`는 `_run_strategy_engine()`이 한 번에 context에 기록합니다.
- 전체 engine 실행 전에 timeout / budget-skip이 일어나면 `_apply_partition_fallback()`이 `partition_only()`를 재사용해 분류와 Diagnostics 기록만 하고 consensus는 만들지 않습니다.

Baseline은 `StrategyEngine.partition_only()`가 **유일한 권위 있는 분류 구현**이라고 정합니다. Aggregator / DecisionAgent / Disagreement는 더 이상 각자 Valid/Invalid 규칙을 정의하지 않고, engine이 수렴시킨 Evidence Chain을 바로 사용합니다. Orchestrator에 남아 있는 예전 wrapper는 기존 내부 호출·테스트와의 호환용일 뿐이며, 정상 런타임 경로에 속하지 않습니다.

### SkillAggregator

정상 런타임에서는 `StrategyEngine`이 `SkillAggregator.calculate(valid_skill_opinions)`를 호출합니다. Aggregator는 입력을 내부 `StrategyOpinion`으로 바꾸고, 수학 계산은 valid opinion만 사용하며, `strategy_signal_score` 조회에는 엄격히 canonical signal만 씁니다. 호환용 진입점이 분류되지 않은 입력을 받더라도 Invalid가 가중치 계산에 참여하면 안 됩니다. 다음 세 가지 상태는 명시적으로 `insufficient` 분기로 갑니다.

- `len(valid) == 0`: `final_signal="hold"`, `confidence=0.0`.
- `len(valid) == 1`: 해당 opinion의 canonical signal로 `final_signal`을 내지만, `consensus_level="insufficient"`.
- `len(valid) ≥ 2`이고 `sum(confidence) == 0`: `final_signal="hold"`, `confidence=0.0`.

만들어진 `strategy_synthesis`는 `StrategyEngine`이 `StrategyResult.skill_consensus_data`에 담고, Orchestrator가 `ctx.set_data("skill_consensus", {...})`로 붙입니다. `_collect_strategy_synthesis()`는 여기서 읽어 dashboard의 권위 있는 합성 출처로 씁니다.

### DecisionAgent

`build_user_message()`는 `ctx.opinions`에서 의견을 읽어 prompt에 씁니다. Orchestrator의 분류가 `ctx.opinions`에 Valid만 있음을 이미 보장하므로, DecisionAgent는 **더 이상** 두 번 거르지 않습니다. Prompt의 "그 밖에 N개 전략 해석 실패" 표시는 `ctx.meta["invalid_opinions"]` 길이를 바로 읽습니다.

DecisionAgent가 출력한 dashboard JSON은 `dashboard.strategy_synthesis`를 덮어쓸 수 없습니다. LLM 반환값에 이 필드가 있으면 `normalize_dashboard_payload()`가 반드시 제거하고, Aggregator 쪽의 권위 있는 합성 결과를 유지해야 합니다.

### 의견 불일치 (Disagreement)

`build_agent_disagreement_summary()`는 `ctx.opinions`로만 `bullish_agents` / `bearish_agents` / `neutral_agents` 세 bucket을 만듭니다. `ctx.opinions`에는 이미 Valid만 있으므로 Invalid는 세 bucket 어디에도 나오지 않으며, `_normalize_signal()`에 의해 조용히 `hold`로 대체되지도 않습니다.

`ctx.meta["invalid_opinions"]` 길이는 `disagreement_summary.diagnostics.invalid_count`로 따로 DecisionAgent prompt에 노출되며, LLM이 `data_limitations` 문구를 만들 때 참고합니다.

### Renderer (네 가지)

모든 renderer는 `dashboard.strategy_synthesis`를 읽어 다음을 표시합니다.

- `final_signal` / `consensus_level` / `conflict_severity` / `conflict_count`.
- `supporting_skills` / `opposing_skills`(더 이상 `neutral_skills`를 사용하지 않음).
- `summary_params.invalid_opinion_count` → 언어별로 "그 밖에 N개 전략 무효·해석 실패"를 표시.

빈 목록 자리 표시는 반드시 `labels.none_label`(`report_language`에 따라 조회)로 출력합니다. 네 가지 renderer가 표시하는 최종 텍스트는 payload와 완전히 일치해야 하며, "합의 수준: 높음 + 지지 전략: 없음" 같은 내부 모순이 나오면 안 됩니다.

과거 기록과 외부 호출자는 계약이 적용되기 전의 느슨한 형태를 그대로 가지고 있을 수 있습니다. 네 가지 renderer는 먼저 `normalize_strategy_synthesis_payload()`로 dict가 아닌 최상위 값을 없는 것으로 보고, 전략·충돌 목록에서 dict가 아닌 항목을 걸러 내야 합니다. `strategy_invalid_opinion_count()`는 진단 개수를 한 곳에서 읽으며, 순수한 10진 양의 정수 문자열만 좁게 변환하고 그 밖의 잘못된 값은 0으로 낮춥니다. History, Notification, 템플릿에 따로 손으로 쓴 읽기 로직을 두는 것은 금지합니다.

### Diagnostics

`ctx.meta["invalid_opinions"]`는 다음 세 가지 용도로만 사용할 수 있습니다.

- 로그: `agent_name` / `raw_signal` / `reason`을 기록해 문제 해결에 씁니다.
- DecisionAgent prompt: "그 밖에 N개 전략 해석 실패" 개수의 출처로 씁니다.
- Renderer: `summary_params.invalid_opinion_count`의 출처로 씁니다.

Diagnostics의 `confidence`를 어떤 가중 계산에도 쓰면 안 되며, `raw_signal`을 `ctx.opinions`에 다시 넣는 것도 금지합니다.

## 반례 매트릭스

Phase 1은 다음 E2E 반례 검증을 반드시 제공해야 합니다. 여기서 E2E는 SkillAgent 입력에서 시작해 Orchestrator 분류 → SkillAggregator → DecisionAgent prompt → 최종 dashboard payload → 네 가지 renderer의 실제 텍스트 출력까지 통과하는 것을 뜻합니다. 일부만 보는 단위 테스트로 E2E를 대신하는 것은 금지합니다.

| 번호 | 입력 | 확인 항목 | 다루는 불변 조건 |
| --- | --- | --- | --- |
| E2E-A | valid `buy/0.8` 1개 + invalid `moon/0.9` 2개 | ① DecisionAgent prompt에 `moon` 문자열, invalid `agent_name`, `0.9` 맥락이 없음 ② `ctx.meta["invalid_opinions"]` 길이 = 2 ③ `strategy_synthesis.summary_params.opinion_count == 1`, `invalid_opinion_count == 2` ④ `consensus_level == "insufficient"` ⑤ 네 가지 renderer 출력 텍스트에 언어별로 "그 밖에 2개 전략 무효·해석 실패"가 포함됨 ⑥ `disagreement_summary.bullish_agents` / `neutral_agents` / `bearish_agents` 어디에도 moon이 바뀐 hold/0.9가 나오지 않음 | I-1, I-2, I-4 |
| E2E-B | valid `hold/0.0` 2개 | `final_signal="hold"`, `weighted_confidence=0.0`, `consensus_level="insufficient"`, `strong_sell`은 **절대** 나오지 않음. 모든 renderer가 언어별로 "근거 부족(관망)"을 표시 | I-3 |
| E2E-C | valid `buy/0.0` 1개 + valid `hold/0.0` 1개 | 가중치 0이 섞인 상황: `final="hold"`, `confidence=0.0`, `consensus="insufficient"`, `strong_sell` 없음 | I-3 |
| E2E-D | valid `hold/0.8` 2개 | ① `final_signal="hold"`, `consensus_level="high"` ② `supporting_skills` 길이 = 2, `opposing_skills` 길이 = 0 ③ 네 가지 renderer의 실제 텍스트에 "높은 합의"와 두 skill 이름이 함께 있으며, "지지 전략: 없음"과 "합의 수준: 높음"이 함께 나오는 조합이 없음 | I-5, I-6 |
| E2E-E | valid `buy/0.8` 1개 + invalid 9개 | `consensus_level="insufficient"`(high가 나오면 **안 됨**). 네 가지 renderer가 "유효 전략 1개 기준 판단(그 밖에 9개 전략 무효·해석 실패)"를 표시 | I-4, I-6 |
| E2E-F | valid opinion 2개, 그중 하나가 `signal="BUY"`(대문자) | Aggregator가 `weighted_score`를 계산할 때 canonical `buy`로 점수(4.0)를 조회하며, 대문자 때문에 조회에 실패해 0이 되면 **안 됨**. `strategy_synthesis.final_signal`은 canonical 소문자로 출력 | I-7 |
| E2E-G | 빈 `supporting_skills` + `report_language="en"` | 네 가지 renderer 출력에 중국어 `"无"`가 나오지 않고 `"None"`(또는 해당 언어의 `labels.none_label`)이 나옴 | I-8 |

(표의 따옴표 안 문구는 renderer가 실제로 출력하는 다국어 문구의 의미를 옮긴 것입니다. 실제 문자열은 `src/report_language.py`의 언어별 라벨을 따릅니다.)

## 소스 코드 위치

| 영역 | 위치 |
| --- | --- |
| Signal 정규화와 Valid 판정 | `src/agent/protocols.py::normalize_strategy_signal`, `is_valid_strategy_signal`, `strategy_signal_score` |
| StrategyEngine 분류와 합성 진입점 | `src/agent/skills/engine.py::StrategyEngine.partition_only`, `process`, `process_partition` |
| Orchestrator 연결과 조기 종료 분류 | `src/agent/orchestrator.py::_run_strategy_engine`, `_apply_partition_fallback` |
| SkillAggregator | `src/agent/skills/aggregator.py::SkillAggregator.calculate`, `aggregate`(호환용 진입점) |
| ConflictDetector / StrategySynthesizer | `src/agent/skills/synthesis.py::ConflictDetector`, `StrategySynthesizer` |
| DecisionAgent prompt | `src/agent/agents/decision_agent.py::build_user_message` |
| Disagreement | `src/agent/disagreement.py::build_agent_disagreement_summary` |
| Dashboard 합성 연결 | `src/agent/orchestrator.py::_collect_strategy_synthesis` |
| Renderer · Markdown | `src/services/report_renderer.py::render`, `templates/report_markdown.j2` |
| Renderer · WeChat | `templates/report_wechat.j2` |
| Renderer · Notification | `src/notification.py`(전략 종합 행 렌더링) |
| Renderer · History | `src/services/history_service.py`(기록 상세의 전략 종합 블록) |
| 다국어와 느슨한 payload 방어 | `src/report_language.py::_REPORT_LABELS`, `normalize_strategy_synthesis_payload`, `strategy_invalid_opinion_count`, `localize_strategy_synthesis_summary`, `labels.none_label` |
| E2E 반례 매트릭스 | `tests/test_multi_agent.py::TestP1SemanticConvergence`, `TestStrategyEngineE2E` |

## 호환성과 롤백

### 폐기된 동작 (Phase 1 적용 후)

| 예전 동작 | 계약 적용 후 |
| --- | --- |
| `normalize_strategy_signal`이 알 수 없는 신호에 조용히 `default="hold"`를 반환해 근거 체인에 섞음 | 알 수 없는 신호는 반드시 Diagnostics로 가며, `ctx.opinions`에 나올 수 없음 |
| Aggregator가 `sum(...) or 1.0`으로 가중치 0을 가림 | `valid_weight_sum == 0`을 명시적으로 판정해 `insufficient` 분기로 가고, `final_signal="hold"` |
| Renderer가 빈 진영에 `"无"`를 하드코딩해 표시 | `labels.none_label`을 언어별로 조회 |
| DecisionAgent가 prompt 단계에서 invalid를 직접 거름 | 분류는 Orchestrator가 마치고, DecisionAgent는 `ctx.opinions`를 바로 사용 |
| `strategy_synthesis`가 `neutral_skills`를 출력 | 계약 적용 후 이 필드는 없으며, renderer도 더 이상 사용하지 않음 |
| LLM dashboard가 `strategy_synthesis`를 덮어씀 | 권위 있는 합성 결과는 Aggregator에서 오며, LLM 쪽 필드는 `normalize_dashboard_payload`가 제거 |

### 새로 추가된 필드

- `ctx.meta["invalid_opinions"]`: Diagnostics 보관 위치(구조는 "Evidence Chain과 Diagnostics 분리" 참고).
- `strategy_synthesis.summary_params.invalid_opinion_count`: Diagnostics 길이.
- `strategy_synthesis.summary_params.total_opinion_count`: valid + invalid의 원래 총수.

### 롤백 방법

| 방법 | 효과 | 할 수 없는 것 |
| --- | --- | --- |
| Phase 1 관련 커밋을 버전 되돌리기 | Orchestrator 분류, Aggregator/Synthesizer 수렴, renderer 일관성 변경을 제거 | 불변 조건 일부만 되돌릴 수는 없습니다. 계약은 전체가 함께 수렴합니다 |
| 계약 문서만 남기고 코드를 되돌리기 | Baseline 문서는 남기고 예전 동작으로 돌아감 | 문서로서의 의미만 있고 런타임 이점은 없습니다. 권장하지 않습니다 |
| Phase 2/3/4를 각각 되돌리기 | 각 Phase의 런타임 변경을 독립적으로 되돌림 | Baseline은 되돌릴 수 없습니다. 어떤 Phase든 항상 Baseline 여덟 가지 불변 조건을 만족해야 합니다 |

Baseline은 설정 항목을 추가하지 않으므로 환경 변수 수준의 롤백 스위치가 없습니다. 이는 의도한 선택입니다. 계약 경계는 코드에서 항상 적용돼야 하며, 환경 변수로 낮출 수 없어야 합니다.
