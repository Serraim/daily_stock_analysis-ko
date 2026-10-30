# 에이전트 스트림 진행 이벤트

이 문서는 다음 기능이 사용하는 진행 이벤트(progress event) 계약을 정리합니다.

- `POST /api/v1/agent/chat/stream`
- Web 종목 질문(Ask) 채팅의 진행 상황 표시
- 단일 에이전트 `run_agent_loop`
- 다중 에이전트 `AgentOrchestrator`

이 엔드포인트는 여전히 Server-Sent Events(`text/event-stream`)로 스트리밍합니다. 각 SSE 페이로드는 최상위에 `type` 필드가 있는 JSON 객체입니다.

## 호환성 범위

이번 이벤트 변경은 기존 내용에 추가만 합니다. 기존 클라이언트는 예전 최상위 필드를 그대로 사용할 수 있습니다.

- `type`
- `step`
- `tool`
- `display_name`
- `success`
- `duration`
- `message`
- `content`

새 클라이언트는 다음 필드도 추가로 읽을 수 있습니다.

- `stage`
- `status`
- `elapsed`
- `timeout`
- `remaining`
- `minimum`
- `reason`
- `meta`

알 수 없는 이벤트 유형은 무시하거나 일반적인 대체 표시로 보여 줘야 합니다.
`done`과 `error`는 기존의 완료 의미를 그대로 유지합니다.

## 이벤트 유형

| 유형 | 생성 주체 | 의미 | 주요 필드 |
| --- | --- | --- | --- |
| `accepted` | SSE 엔드포인트 | 컨텍스트 준비와 사용자 턴·상태 트랜잭션이 성공했습니다. 아직 실행은 시작하지 않았습니다. | `backend`, `request_id`, `session_id`, `active_stock_context`, `session_state_version`, `session_generation`, `session_state` |
| `stage_start` | 단일 에이전트 루프, 다중 에이전트 오케스트레이터 | 에이전트 또는 파이프라인 단계가 시작됐습니다. | `stage`, `message` |
| `stage_done` | 단일 에이전트 루프, 다중 에이전트 오케스트레이터 | 에이전트 또는 파이프라인 단계가 끝났습니다. | `stage`, `status`, `duration` |
| `thinking` | 단일 에이전트 루프 | 에이전트가 다음 행동을 결정하는 중입니다. | `step`, `message` |
| `tool_start` | 단일 에이전트 루프 | 도구 호출이 시작됐습니다. | `step`, `tool`, `display_name` |
| `tool_done` | 단일 에이전트 루프 | 도구 호출이 끝났거나 실패했습니다. | `step`, `tool`, `success`, `duration`, `display_name` |
| `generating` | 단일 에이전트 루프 | 최종 답변을 생성하는 중입니다. | `step`, `message` |
| `pipeline_timeout` | 다중 에이전트 오케스트레이터 | 단계 또는 파이프라인의 시간 예산이 다 돼서 오케스트레이터가 멈췄습니다. | `stage`, `elapsed`, `timeout` |
| `pipeline_budget_skipped` | 다중 에이전트 오케스트레이터 | 남은 예산이 의미 있는 작업을 하기에 너무 적어서, 다음 단계를 시작하기 전에 오케스트레이터가 멈췄습니다. | `stage`, `elapsed`, `timeout`, `remaining`, `minimum`, `reason`, `message` |
| `done` | SSE 엔드포인트 | 요청이 완료됐습니다. | `success`, `content`, `error`, `total_steps`, `session_id` |
| `error` | SSE 엔드포인트 | 정상 완료 전에 요청이 실패했습니다. `accepted` 이전에 준비 단계에서 거부된 경우도 포함합니다. | `message`, `error_code`, `request_id`, `session_id` |

## 등록된 종목명과 그 안에 포함된 언급

채팅 대상을 준비할 때, 종목 목록에서 검증된 전체 종목명은 하나의 단어 단위로 취급합니다. 그 이름 안에 완전히 들어 있는 더 짧은 별칭이나 티커처럼 보이는 조각은 또 다른 대상을 만들지 않습니다. 예를 들어 `长电科技(600584.SH)`는 `600584`를 선택하지만, 단독으로 쓴 `长电`은 여전히 `600900`(长江电力)을 선택합니다. (`长电科技`, `长江电力`, 뒤에 나오는 `中芯国际`는 사용자가 입력하는 중국 상장사 이름이며 프로그램이 그대로 인식하므로 원문대로 둡니다.)
이 규칙은 스트리밍 채팅과 비스트리밍 채팅 모두에 적용됩니다. 두 방식이 같은 대상 결정 코드를 쓰기 때문입니다. 종목명 바깥에 따로 쓴 언급과 코드는 평소 검사를 그대로 거칩니다. `长电科技(600900.SH)`는 여전히 확인 질문이 필요하고, `中芯国际`처럼 여러 종목이 공유하는 이름은 여전히 모호하지 않은 코드가 필요합니다.
이 변경은 응답 필드, SSE 이벤트 유형, 리포트 서식을 추가하지 않습니다.

## 수락과 세션 상태

엔드포인트는 먼저 기존 접근 권한과 백엔드 기능 범위를 확인합니다. 분석 컨텍스트는 수락(acceptance) 쓰기 트랜잭션 밖에서 준비한 다음, 사용자 메시지, 명시적인 Skill 선택, 주요 논의 대상을 한 번에 커밋합니다. 커밋이 성공해야만 `accepted`를 보냅니다. 분석 진행 이벤트와 `done`은 그보다 먼저 올 수 없습니다. 다만 준비 단계에서 끝나는 `error`는 그 전에 올 수 있습니다.

`accepted`, `GET /api/v1/agent/chat/sessions/{session_id}`, 그리고 지원되는 비스트리밍 `POST /api/v1/agent/chat` 응답은 다음 상태 필드를 공유합니다.

```json
{
  "active_stock_context": {
    "stock_code": "sh000001",
    "stock_name": "上证指数",
    "canonical_id": "sh000001",
    "asset_type": "index"
  },
  "session_state_version": 3,
  "session_generation": "opaque-server-assigned-instance",
  "session_state": {"selected_skill_ids": []}
}
```

(`"上证指数"`는 상하이종합지수의 중국어 이름이며, 서버가 돌려주는 실제 값이라 그대로 둡니다.)

- `active_stock_context`는 `null`일 수 있고, `stock_name`도 `null`일 수 있습니다. 숫자 코드만 남기지 말고 `canonical_id`와 `asset_type`을 함께 보존해야 합니다. 비교 질문에서는 여러 도구 대상을 허용하면서도 주요 대상은 바꾸지 않거나 null로 둘 수 있습니다.
- `session_generation`은 세션 인스턴스를 식별할 뿐, 권한을 뜻하지 않습니다. 삭제된 세션 ID가 다시 만들어지면 값이 바뀝니다. 이 값을 아는 클라이언트는 다음 Chat 요청에 함께 보낼 수 있으며, 오래된 인스턴스는 거부됩니다.
- 버전은 수락된 턴마다 증가하며, 같은 generation 안에서만 비교할 수 있습니다. 상세 조회의 버전 0은 예전 기록을 보수적으로 보여 주는 것이지, 새로 수락된 턴이 아닙니다. 정말로 비어 있는 상세는 generation이 null일 수 있습니다.
- `session_state.selected_skill_ids`는 저장된 사용자 선택입니다. null은 지정하지 않음, `[]`는 내장 기본값 선택, 비어 있지 않은 목록은 이름을 지정한 Skill 선택을 뜻합니다. 설정에서 정해진 실제 기본값은 사용자 선택으로 기록하지 않습니다.
- 확인 출처(provenance)와 provider 추적 정보는 공개하지 않습니다. 비스트리밍 상태는 나중의 상세 조회가 아니라 해당 턴의 수락 시점 스냅샷에서 가져옵니다.
- 클라이언트는 일부가 빠졌거나 형식이 잘못된 상태 필드를 거부해야 합니다. 대상·버전·generation 세 필드가 모두 없으면 버전 0이 아니라 예전 API라는 뜻입니다.

상세 조회는 비즈니스 상태를 고치거나 증가시키지 않습니다. 예전 코드의 쓰기 때문에 수락된 대상의 출처를 믿을 수 없게 되면, 상세 조회는 이전에 수락된 대상과 같은 generation·버전으로 null을 반환할 수 있습니다. 같은 버전이라면 유효한 현재 상세가 늦게 도착한 accepted 응답보다 우선합니다. 버전을 비교하기 전에 응답 소유권, 로컬 인스턴스 연결, generation을 먼저 확인해야 하며, 오래된 상세가 더 새로운 연결 인스턴스를 대체할 수 없습니다.

준비·커밋 충돌이 나면 `accepted`, `done`, 도구 진행 이벤트, 메시지·Skill·종목의 부분 업데이트 없이 `error_code=session_state_conflict`를 보냅니다. 비스트리밍 API는 `error`/`message` JSON 페이로드와 함께 HTTP 409를 반환합니다. 클라이언트는 작성 중인 내용을 보존하고, 자동으로 다시 보내지 말고 사용자가 명시적으로 새로고침·재시도하도록 해야 합니다. 고정된 확인 질문은 일반적으로 수락된 사용자 턴이며, 분석 준비나 모델 호출 없이 `done`(`total_steps=0`)이 뒤따릅니다.

커밋 이후의 실패, 시간 초과, 중지, 연결 끊김은 수락된 상태를 되돌리지 않습니다. 종료 시점의 쓰기는 수락된 세션·메시지 인스턴스를 확인하므로, 늦게 도착한 답변이 삭제된 세션을 다시 만들거나 같은 이름의 새 세션을 오염시킬 수 없습니다. 이 계약은 더 이상 쓰지 않는 `codex_app_server` 값을 준비·수락 전에(확인 질문 포함) HTTP 400 `backend_removed`로 거부합니다. 이때 `accepted`나 상태 변경은 일어나지 않습니다. Codex 전용 취소 엔드포인트는 제거됐습니다(API 전용 모드에서는 404, 프런트엔드 자산이 설치된 경우에는 기존 SPA GET catch-all이 알 수 없는 POST에 405 반환). 클라이언트 측 중단과 세션 소유권 확인은 그대로 남아 있습니다. 이 제거는 과거 Gate 0B 결과를 바꾸지 않습니다.

## Web 동작

Web 채팅 UI는 기존 thinking/tool/generating 이벤트에 더해 `stage_start`, `stage_done`, `pipeline_timeout`, `pipeline_budget_skipped`도 인식합니다.
나중에 추가된 백엔드 이벤트를 인식하지 못하면, UI는 그 이벤트를 메시지 진행 기록에 남기고 빈 진행 행 대신 일반적인 대체 표시를 보여 줍니다.

## 런타임과 Provider 범위

이 이벤트 계약은 모델 라우팅이나 런타임 설정을 바꾸지 않습니다.
다음 항목은 수정하지 않습니다.

- provider 선택
- 모델 이름
- Base URL 처리
- LiteLLM 라우트 해석
- API 키 또는 자격 증명 로딩
- 설정 정리 또는 마이그레이션 동작

Provider/모델/Base URL 동작은 기존 LLM 설정 문서와 런타임 코드가 계속 결정합니다. 테스트에 쓰인 provider/모델 문자열은 모두 mock 식별자일 뿐입니다.

## 검증

이 계약을 바꿀 때 권장하는 확인 명령입니다.

```bash
python -m pytest tests/test_agent_stream_events.py tests/test_agent_sse_cleanup.py tests/test_agent_chat_api.py tests/test_agent_active_stock_integration.py
```

```bash
cd apps/dsa-web
npm test -- src/stores/__tests__/agentChatStore.test.ts src/pages/__tests__/ChatPage.test.tsx
```

해당 테스트로 다음을 확인해야 합니다.

- 이벤트 헬퍼 출력이 예전 필드를 보존하고 설정되지 않은 필드는 빼는지
- 단계 메타데이터가 보존되는지
- `run_agent_loop`가 짝을 이루는 `stage_start` / `stage_done` 이벤트와 `thinking`, `generating`을 보내는지
- 오케스트레이터의 시간 초과 이벤트가 예산 부족 건너뜀 이벤트와 구분되는지
- SSE 정리 동작이 바뀌지 않았는지
- Web 채팅 상태와 Chat 페이지 렌더링 테스트가 여전히 통과하는지

<a id="rollback"></a>
## 롤백

이 이벤트 계약 변경을 롤백하려면 다음을 도입한 커밋을 revert합니다.

- `src/agent/stream_events.py`
- `src/agent/runner.py`의 이벤트 헬퍼 연결
- `src/agent/orchestrator.py`의 단계 이벤트 연결
- Web `ProgressStep`과 Chat 페이지 렌더링 변경

이 변경은 추가만 했고 `done` / `error`의 의미를 바꾸지 않았으므로, 기존 클라이언트는 마이그레이션 없이 새 단계 이벤트를 무시해도 됩니다.

세션 상태 확장을 롤백할 때는, 대응하는 백엔드·Web 코드를 되돌리기 전에 먼저 새 백엔드를 중지합니다. 추가된 nullable 컬럼과 데이터베이스 수준의 버전 기본값은 그대로 둡니다. 컬럼을 삭제하거나 데이터베이스를 다시 만들지 마십시오. 예전 백엔드와 새 백엔드가 동시에 쓰기를 하도록 실행하지 마십시오. 롤백 중 예전 코드로 기록된 사용자 쓰기는 다시 업그레이드한 뒤 재확인이 필요합니다. 보존된 메시지와 Skill 선택은 계속 사용할 수 있습니다. 플랫폼 업그레이드 수락 여부는 이 통신 계약과 별개입니다.
