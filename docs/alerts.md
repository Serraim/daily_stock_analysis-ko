# 실시간 경보 센터

이 문서는 Issue #1202 경보 센터의 실행 기준선, 데이터 계약, 단계별 구현 범위, 호환 경계를 정리합니다.

> 용어 안내: 이 문서에서 "경보(알림 규칙)"는 조건이 맞을 때 알림을 보내는 규칙을 말하고, "알림"은 Feishu(페이슈), DingTalk(딩톡), 위챗 워크 같은 채널로 실제 메시지를 보내는 일을 말합니다.

## 현재 기준선

현재 런타임 경보는 `src/services/alert_worker.py`의 백그라운드 worker가 일괄 스케줄링하며, 실제 규칙 평가는 `src/services/alert_service.py`와 `src/agent/events.py`에 있는 EventMonitor 규칙 모델을 재사용합니다.

- 설정 진입점: `AGENT_EVENT_MONITOR_ENABLED`, `AGENT_EVENT_MONITOR_INTERVAL_MINUTES`, `AGENT_EVENT_ALERT_RULES_JSON`.
- 실행 진입점: `main.py`가 schedule 모드에서 `agent_event_monitor` 백그라운드 작업을 등록합니다. 백그라운드 worker는 매 회차마다 저장된 active rules(활성 규칙)를 읽고, legacy `AGENT_EVENT_ALERT_RULES_JSON`도 계속 지원합니다.
- 알림 전달: 경보가 발동하면 `NotificationService.send(..., route_type="alert")`를 재사용하며, 알림 게이트웨이의 alert 라우팅 설정을 그대로 따릅니다.
- Web/System 설정 검증: `src/services/system_config_service.py`가 `AGENT_EVENT_ALERT_RULES_JSON`의 JSON 형식과 규칙 의미를 검증합니다.

현재 runtime은 세 가지 규칙을 지원합니다.

| `alert_type` | 방향 필드 | 임계값 필드 | 현재 의미 |
| --- | --- | --- | --- |
| `price_cross` | `direction`: `above` / `below` | `price` | 실시간 가격이 지정 가격을 상향 또는 하향 돌파 |
| `price_change_percent` | `direction`: `up` / `down` | `change_pct` | 실시간 등락률이 지정 비율에 도달 |
| `volume_spike` | - | `multiplier` | 최신 거래량이 최근 20일 평균 거래량의 지정 배수를 초과 |

`sentiment_shift`, `risk_flag`, `custom` 등은 향후 확장을 위한 자리 표시일 뿐이며, 현재 런타임은 이 유형들을 실행 가능한 규칙으로 받지 않습니다.

## Legacy 설정 호환

규칙 목록은 이제 읽기 전용 `rule_sources`를 함께 반환합니다. `legacy_configured`는 검증을 통과한 환경 변수 규칙 항목 수이고, `legacy_effective`는 백그라운드 worker의 기존 로직대로 활성 데이터베이스 규칙과 중복을 제거한 뒤 남은 환경 변수 규칙 수입니다. 이 값은 필터를 적용하지 않은 설정 로드 결과를 설명할 뿐이며, 폴링이 시작되었다는 뜻은 아닙니다. 중복된 환경 변수 항목은 앞의 값에는 여러 번 세어질 수 있지만 뒤의 값에는 한 번만 세어집니다. 유효하지 않은 항목은 worker의 건너뛰기 규칙을 그대로 따릅니다.

출처 통계는 백그라운드 규칙 우선순위, 데이터베이스와 펼친 대상 수의 상한, 중복 제거 의미를 그대로 유지합니다. 보유 종목 대상은 읽기 전용 원장 재생(replay)으로 얻으며, 실시간 시세를 조회하지 않고 보유 종목 캐시, 배치, 일별 스냅샷도 다시 쓰지 않습니다. 같은 목록 요청 안에서는 대상 범위와 계좌가 같은 규칙끼리 펼친 결과를 재사용해 재생을 반복하지 않습니다. 펼치기에 실패해도 한 번만 시도하며, 각 규칙은 각자의 실패 정보와 개수 자리 표시를 유지합니다. 캐시는 요청을 넘어 공유되지 않으므로 새 요청은 최신 보유 종목을 다시 읽고 이전 실패도 다시 시도합니다. 목록 필터, 페이지 이동, 모니터링 스위치는 이 경계를 바꾸지 않습니다. 백그라운드 폴링과 규칙 시험 실행은 여전히 기존 시세 및 스냅샷 로드 방식을 사용합니다.

Web은 유효한 환경 변수 규칙을 발견하면, 데이터베이스 목록이 비어 있거나 환경 변수 규칙이 모두 같은 조건의 활성 데이터베이스 규칙에 가려져 있더라도 항상 출처 안내를 표시합니다. 페이지에서 삭제하거나 비활성화하면 데이터베이스만 바뀌고 환경 변수 규칙은 바뀌지 않습니다. 따라서 데이터베이스 규칙을 비활성화하거나 삭제하면 같은 조건의 환경 변수 규칙이 다시 폴링 대상이 될 수 있습니다. 환경 변수 규칙을 멈추려면 실제 배포 설정에서 `AGENT_EVENT_ALERT_RULES_JSON`을 수정한 뒤 설정을 다시 불러오십시오. 이번 변경은 설정을 자동으로 옮기지 않으며, 실행, 쿨다운, 알림 의미도 바꾸지 않습니다.

시각 회귀 테스트: `apps/dsa-web`에서 `npx playwright test --config playwright.fixture.config.ts`를 실행합니다(백엔드나 로그인 암호가 필요 없음). 통제된 API 응답으로 데이터베이스 목록이 비어 있을 때의 데스크톱/좁은 화면 안내를 확인하고 `test-results/fixtures/**/alerts-sources-*.png`를 생성합니다. 이 테스트는 UI만 검증하며, 백엔드의 실제 설정 로드 회귀 테스트를 대신하지 않습니다. 이 주제 문서에는 영문판이 없습니다.

`AGENT_EVENT_ALERT_RULES_JSON`은 legacy 런타임 규칙 출처로 계속 유지되며, 사용자가 이미 설정한 `.env` / Web 설정을 자동으로 옮기거나, 삭제하거나, 덮어쓰거나, 고쳐 쓰지 않습니다.

- 빈 문자열이나 빈 배열은 legacy 규칙이 설정되지 않았다는 뜻입니다. 이 경우에도 schedule 모드는 백그라운드 worker를 등록하므로, 나중에 API로 만든 저장 규칙(active rules)은 재시작 없이 평가됩니다.
- Web/System 설정을 저장할 때는 엄격하게 검증합니다. JSON 형식 오류, 필드 누락, 잘못된 방향, 잘못된 임계값, unsupported rule type은 모두 설정 오류로 반환해야 합니다.
- 런타임에 불러올 때는 잘못된 규칙 한 개를 건너뛸 수 있으며, 나머지 유효한 규칙은 계속 동작합니다. 규칙 하나 때문에 schedule 프로세스 전체가 멈추지 않게 하기 위해서입니다.
- 현재 worker는 프로세스 내부 fingerprint로 조건이 계속 충족될 때 같은 알림이 반복 발송되지 않게 합니다. 이것은 경보 센터의 쿨다운 모델이 아니며, 프로세스 간이나 재시작 후에는 쿨다운 상태가 유지되지 않습니다.

## 데이터 계약
<!-- 계약 키(tests): 完整 webhook URL / 邮箱密码 -->

아래 계약은 이후 P1+ 단계의 API, worker, Web, 저장소 구현을 맞추기 위한 것입니다. P0는 필드와 의미 경계만 정의하며, 이 저장 엔터티들이 이미 존재한다는 뜻은 아닙니다.

### `alert_rule`

관리할 수 있는 경보 규칙입니다.

| 필드 | 설명 |
| --- | --- |
| `id` | 규칙 ID. legacy JSON 규칙은 P0에서 저장된 ID가 없음 |
| `name` | 사용자가 읽을 수 있는 이름. 지정하지 않으면 규칙 유형과 대상으로 생성 가능 |
| `target_scope` | 대상 범위. 예: single symbol, watchlist(관심 종목), portfolio(보유 종목), market |
| `target` | 대상 종목 또는 대상 참조. 예: 종목 코드, watchlist ID, portfolio ID |
| `alert_type` | 규칙 유형. P1 초기에는 `price_cross`, `price_change_percent`, `volume_spike`만 허용 |
| `parameters` | 규칙 매개변수. 예: `direction`, `price`, `change_pct`, `multiplier` |
| `severity` | 경보 등급. 예: info, warning, critical |
| `enabled` | 사용 여부 |
| `cooldown_policy` | 쿨다운 정책. P0는 필드만 정의하고, 실행 의미는 P4에서 구현 |
| `notification_policy` | 알림 정책. 기본적으로 `NotificationService`의 alert 라우팅을 재사용 |
| `source` | 생성 출처. 예: legacy_env, web, api, import |
| `created_at` / `updated_at` | 생성 시각과 수정 시각 |

### `alert_trigger`

실제로 발생했거나 기록할 수 있는 규칙 발동 한 건입니다.

| 필드 | 설명 |
| --- | --- |
| `id` | 발동 기록 ID |
| `rule_id` | 해당 규칙 ID. legacy env 규칙은 임시 참조를 기록할 수 있음 |
| `target` | 실제 발동 대상 |
| `observed_value` | 관측값. 예: 현재가, 등락률, 거래량 배수 |
| `threshold` | 발동 임계값 |
| `reason` | 사람이 읽을 수 있는 발동 이유 |
| `data_source` | 데이터 소스 또는 provider |
| `data_timestamp` | 데이터 시각. 없으면 현재 시각으로 꾸며 넣으면 안 됨 |
| `triggered_at` | 발동 시각 |
| `status` | 발동 상태. 예: triggered, skipped, degraded, failed |
| `diagnostics` | 마스킹한 진단 정보 |

### `alert_notification`

발동 한 건에 대한 알림 발송 시도입니다.

| 필드 | 설명 |
| --- | --- |
| `id` | 알림 시도 ID |
| `trigger_id` | 해당 발동 기록 ID |
| `channel` | 알림 채널 |
| `attempt` | 몇 번째 시도인지 |
| `success` | 성공 여부 |
| `error_code` | 구조화된 오류 코드 |
| `retryable` | 재시도 권장 여부 |
| `latency_ms` | 소요 시간 |
| `diagnostics` | 마스킹한 발송 진단. token, 전체 webhook URL, 이메일 비밀번호, bot secret을 포함하면 안 됨 |
| `created_at` | 시도 시각 |

### `alert_cooldown`

규칙 또는 대상 단위의 쿨다운 상태입니다.

| 필드 | 설명 |
| --- | --- |
| `rule_id` | 해당 규칙 ID |
| `target` | 쿨다운 대상 |
| `severity` | 선택 항목인 등급 차원 |
| `last_triggered_at` | 최근 발동 시각 |
| `cooldown_until` | 쿨다운 종료 시각 |
| `reason` | 쿨다운 이유 |
| `state` | 현재 상태. 예: active, expired |
| `updated_at` | 수정 시각 |

## 저장 방식 검토
<!-- 계약 키(tests): ## 存储方案评估 | 幂等初始化 | 回滚说明 -->

현재 저장소에는 이미 SQLite 저장 계층과 repository/service 계층 구분이 있습니다.

- `src/storage.py`는 SQLite 연결, SQLAlchemy ORM 모델, `DatabaseManager`를 관리합니다.
- `src/repositories/`에는 데이터 접근 계층이 있습니다. 예: `PortfolioRepository`.
- `src/services/`에는 비즈니스 서비스 계층이 있습니다. 예: `PortfolioService`, `PortfolioRiskService`.
- 기본 데이터베이스 경로는 기존 설정을 따르며, 보통 `data/stock_analysis.db`입니다.

P1/P2에서 경보 저장 기능을 구현할 때는 위 패턴을 우선 재사용하는 것을 권장합니다. storage 계층에서 alert ORM 모델을 정의하고, repository 계층에서 CRUD와 조회를 감싸며, service 계층에서 규칙 검증, 평가 상태, 알림 결과, 쿨다운 의미를 처리합니다. P0는 테이블을 새로 만들지 않고 기존 데이터베이스도 바꾸지 않습니다.

이후 PR에서 schema 변경이 필요하면 다음을 함께 제시해야 합니다.

- 멱등 초기화: 여러 번 시작하거나 초기화를 반복 실행해도 기존 데이터가 손상되면 안 됩니다.
- 하위 호환: 경보 센터를 설정하지 않았을 때 일일 분석, 종목 질문(Ask), 알림, 시장 리뷰, 보유 종목 기능에 영향을 주지 않아야 합니다.
- 롤백 안내: 최소 롤백 방법으로 최소한 PR revert를 포함해야 하며, 새 테이블이나 인덱스를 만들었다면 데이터를 보존하는지, 수동으로 어떻게 정리하는지 설명해야 합니다.
- 데이터 마이그레이션 경계: 사용자가 명시적으로 가져오기를 실행하지 않는 한 `AGENT_EVENT_ALERT_RULES_JSON`을 자동으로 옮기거나, 삭제하거나, 덮어쓰면 안 됩니다.

## P1 Alert API MVP
<!-- 계약 키(tests): 脱敏 | 保留字段 | 不执行冷却或自定义通知语义 | 不新增 Web 告警中心页面 | 不让 schedule worker 加载持久化 active rules | 不实现真实 `alert_trigger` / `alert_notification` 写入 | 不实现 `alert_cooldown` 执行语义 | 不实现 MACD、KDJ、CCI、RSI | 不自动迁移、删除、覆盖或改写 legacy 配置 -->

P1은 백엔드 Alert API와 schema를 추가해 경보 센터의 최소 API 계약을 고정합니다. Web 페이지나 백그라운드 worker와는 아직 연결하지 않습니다.

- 새 API 파일: `api/v1/endpoints/alerts.py`.
- 새 schema 파일: `api/v1/schemas/alerts.py`.
- API 범위:
  - `GET /api/v1/alerts/rules`
  - `POST /api/v1/alerts/rules`
  - `GET /api/v1/alerts/rules/{rule_id}`
  - `PATCH /api/v1/alerts/rules/{rule_id}`
  - `DELETE /api/v1/alerts/rules/{rule_id}`
  - `POST /api/v1/alerts/rules/{rule_id}/enable`
  - `POST /api/v1/alerts/rules/{rule_id}/disable`
  - `POST /api/v1/alerts/rules/{rule_id}/test`
  - `GET /api/v1/alerts/triggers`
  - `GET /api/v1/alerts/notifications`
- 첫 버전 규칙은 여전히 `price_cross`, `price_change_percent`, `volume_spike`만 지원합니다. `sentiment_shift`, `risk_flag`, `custom` 등 향후 유형은 구조화된 unsupported 오류를 반환합니다.
- `test` 엔드포인트는 일회성 dry-run(시험 실행) 평가만 수행하며, 알림을 보내지 않고 실제 발동 기록이나 알림 attempt도 쓰지 않습니다.
- `cooldown_policy` / `notification_policy`는 P1에서 예약 필드일 뿐입니다. API는 이 불투명(opaque) 설정을 저장하고 돌려줄 수 있지만, 쿨다운이나 사용자 정의 알림 의미는 실행하지 않습니다.
- API 응답은 반드시 마스킹해야 하며, token, 전체 webhook URL, 이메일 비밀번호, cookie, bot secret을 그대로 돌려주지 않습니다.
- `AGENT_EVENT_ALERT_RULES_JSON`은 계속 legacy 설정 진입점으로 남습니다. P1은 legacy 설정을 자동으로 옮기거나, 삭제하거나, 덮어쓰거나, 고쳐 쓰지 않습니다.

P1에서 하지 않는 일:

- Web 경보 센터 페이지, 라우트, 사이드바 메뉴를 추가하지 않습니다.
- schedule worker가 저장된 active rules를 불러오게 하지 않으며, 저장 규칙과 legacy JSON의 병합/중복 제거도 구현하지 않습니다.
- 실제 `alert_trigger` / `alert_notification` 쓰기를 구현하지 않습니다. P1은 조회 API와 테이블 구조만 제공합니다.
- `alert_cooldown` 실행 의미를 구현하지 않습니다.
- MACD, KDJ, CCI, RSI, 보유 종목 리스크, Market Light 경보 규칙을 구현하지 않습니다.

## P2 경보 평가 Worker
<!-- 계약 키(tests): ## P2 告警评估 Worker | 持久化 active rules | `triggered`、`skipped`、`degraded`、`failed` | 不写 `alert_notifications` | 不执行 `cooldown_policy` -->

P2는 schedule 런타임을 "시작할 때 legacy `EventMonitor`를 한 번 만드는 방식"에서 "백그라운드 worker가 매 회차마다 저장된 active rules와 legacy JSON 규칙을 평가하는 방식"으로 바꿉니다.

- `AGENT_EVENT_MONITOR_ENABLED`는 계속 전체 스위치이며, 백그라운드 작업 이름은 `agent_event_monitor`로 유지됩니다.
- worker는 매 회차마다 DB에서 `enabled=true`인 `alert_rules`를 읽고 `AGENT_EVENT_ALERT_RULES_JSON`도 다시 해석합니다. API로 새로 만든 규칙은 schedule 프로세스를 재시작하지 않아도 됩니다.
- DB 규칙과 legacy 규칙은 `target_scope + target + alert_type + canonical(parameters)` 기준으로 중복을 제거하며, 충돌하면 DB 규칙이 우선합니다. legacy 설정은 자동으로 옮기거나, 삭제하거나, 고쳐 쓰지 않습니다.
- 규칙은 하나씩 따로 평가합니다. 한 규칙이 실패하면 그 규칙에 `failed` 평가 상태만 기록하고, 같은 회차의 다른 규칙이나 주 분석 흐름에는 영향을 주지 않습니다.
- P2에서 `alert_triggers`는 최소한의 평가 이력을 기록하는 데 씁니다: `triggered`, `skipped`, `degraded`, `failed`. 정상적인 `not_triggered`는 기록하지 않아 폴링 때문에 테이블이 불어나지 않게 합니다.
- 실시간 시세 누락, 필드 누락, 평가할 수 없는 상황은 `skipped`로 기록합니다. 일봉 데이터를 쓸 수 없거나 구조가 불완전하면 `degraded`로 기록합니다. 진단 정보는 마스킹됩니다.
- 발동 후에는 여전히 `NotificationService.send(..., route_type="alert")`를 호출합니다. 프로세스 내부 fingerprint는 조건이 계속 충족될 때 반복 발송을 막을 뿐이며, `cooldown_policy`를 실행하지는 않습니다.

P2에서 하지 않는 일:

- Web 경보 센터 페이지, 라우트, 사이드바 메뉴를 추가하지 않습니다.
- `alert_notifications`에 쓰지 않으며, 채널별 알림 attempt도 기록하지 않습니다.
- `alert_cooldown`, `cooldown_policy`, `notification_policy`의 실행 의미를 구현하지 않습니다.
- MACD, KDJ, CCI, RSI, 보유 종목 리스크, Market Light 경보 규칙을 구현하지 않습니다.

## P3 Web 경보 센터 MVP

P3는 WebUI에 `/alerts` 경보 센터 진입점을 추가해, 사용자가 legacy JSON을 직접 편집하지 않고도 현재 세 가지 런타임 규칙을 관리할 수 있게 합니다.

- 사이드바에 "경보" 메뉴가 생기며, 페이지는 규칙 목록, 페이지 나누기, 사용 여부 필터, 규칙 유형 필터를 지원합니다.
- 규칙 생성 폼은 `single_symbol` 대상 범위와 현재 실행 가능한 세 가지 규칙만 지원합니다.
  - `price_cross`: `direction`은 `above` / `below`이며 `price`를 입력합니다.
  - `price_change_percent`: `direction`은 `up` / `down`이며 `change_pct`를 입력합니다.
  - `volume_spike`: `multiplier`를 입력합니다.
- 규칙 작업으로 사용, 사용 중지, 삭제, 일회성 dry-run 테스트를 지원합니다.
- 규칙을 생성, 사용, 사용 중지, 삭제하는 도중에 필터나 페이지를 바꾸면, 작업이 끝난 뒤 목록 새로 고침은 현재 필터 조건을 사용합니다. 생성에 성공하면 여전히 현재 필터의 첫 페이지로 돌아갑니다.
- dry-run 테스트는 `AlertRuleTestResponse`에 선언된 필드만 보여 줍니다: 규칙 ID, 상태, 발동 여부, 관측값, 메시지. `threshold`, `data_source`, `data_timestamp` 같은 확장 진단 필드는 백엔드 schema가 명시적으로 노출한 뒤에 표시합니다.
- 발동 이력은 P2 worker가 기록한 `triggered`, `skipped`, `degraded`, `failed` 기록을 보여 줍니다. 정상적인 `not_triggered`는 여전히 이력에 기록되지 않습니다.
- 알림 시도 영역은 기존 `GET /api/v1/alerts/notifications`만 조회합니다. P2 런타임은 채널별 알림 attempt를 기록하지 않으므로 지금은 보통 "알림 시도 기록 없음" 빈 상태가 표시되며, 발동 상태를 알림 전달 결과로 추측하지 않습니다.
- Web 페이지는 `AGENT_EVENT_ALERT_RULES_JSON` 편집 기능을 제공하지 않으며, legacy 설정을 자동으로 옮기거나, 삭제하거나, 고쳐 쓰지 않습니다.

P3에서 하지 않는 일:

- 백엔드 API, schema, storage, worker 동작을 추가하거나 바꾸지 않습니다.
- 규칙 편집, target/source 고급 필터, watchlist/portfolio 대상, 기술 지표 규칙, Market Light 연동을 구현하지 않습니다.
- `cooldown_policy` / `notification_policy`를 실행하지 않으며, `alert_notifications`에 쓰지 않습니다.

## P4 알림 결과와 저장형 쿨다운
<!-- 계약 키(tests): ## P4 通知结果与持久化冷却 | 同一数据点去重 | `data_timestamp` 缺失时不做去重 | DB 持久化规则正常路径使用 `alert_cooldowns` | 读取持久化冷却状态失败 | legacy `AGENT_EVENT_ALERT_RULES_JSON` 规则继续使用 worker 进程内 fingerprint | 不会写入或延长 `alert_cooldowns` -->

P4는 실제 경보 발동에 문제 해결이 가능한 알림 결과를 남기고, Alert API로 만든 저장 규칙에 재시작 후에도 유지되는 업무용 쿨다운 상태를 부여합니다.

- DB 저장 규칙의 `triggered` 이력은 `rule_id + target + data_source + data_timestamp` 기준으로 같은 데이터 지점의 중복을 제거합니다. 같은 발동 이벤트는 가장 이른 `alert_triggers` 한 건만 남기고, 폴링이 반복해서 맞더라도 기존 발동 기록을 재사용합니다. `data_timestamp`가 없으면 같은 출처임을 증명할 수 없는 데이터 지점을 잘못 합치지 않도록 중복 제거를 하지 않습니다. 이후 쿨다운이나 알림 소음 억제로 발송이 막히더라도, 해당 알림 시도나 synthetic(가상) 억제 상태는 `alert_notifications`에 기록됩니다.
- `alert_notifications`는 실제 채널별 알림 attempt를 기록하며, `channel`, `success`, `error_code`, `retryable`, `latency_ms`, 마스킹된 `diagnostics`를 포함합니다.
- 실제 채널 발송이 아닌 상태는 synthetic channel로 기록합니다.
  - `__cooldown__`: 경보 업무 쿨다운으로 억제됨, `error_code="cooldown_active"`.
  - `__cooldown_read_failed__`: 저장된 쿨다운 상태를 읽지 못해 worker 프로세스 내부의 임시 대체 수단으로 억제됨, `error_code="cooldown_read_failed"`.
  - `__noise_suppressed__`: 알림 인프라의 소음 억제로 막힘, `error_code="noise_suppressed"`.
  - `__no_channel__`: alert 라우팅에 맞는 사용 가능한 알림 채널이 없음.
  - `__dispatch__`: 알림 발송 단계의 fallback 또는 예외.
- 쿨다운 계층:
  - DB 저장 규칙의 정상 경로는 `alert_cooldowns`를 경보 업무 쿨다운으로 사용하며, 더 이상 worker 프로세스 내부 fingerprint로 판단하지 않습니다. 저장된 쿨다운 상태를 읽지 못했을 때만, DB 이상 기간에 같은 규칙이 매 회차 반복 발송되지 않도록 임시로 프로세스 내부 fingerprint를 사용합니다.
  - legacy `AGENT_EVENT_ALERT_RULES_JSON` 규칙은 계속 worker 프로세스 내부 fingerprint를 사용하며 `alert_cooldowns`에 쓰지 않습니다.
  - `notification_noise.py`는 여전히 알림 인프라 계층의 전역 안전망입니다. 이것은 경보 업무 쿨다운이 아니며, 여기서 억제되더라도 `alert_cooldowns`를 쓰거나 연장하지 않습니다.
- DB 규칙의 `cooldown_policy.cooldown_seconds`는 0 이상의 정수로 정규화됩니다. 값이 없으면 기본 24시간 업무 쿨다운을 쓰고, `0`이면 DB 업무 쿨다운을 끕니다.
- `GET /api/v1/alerts/rules`는 읽기 전용 `last_triggered_at` / `cooldown_until` / `cooldown_active` 요약을 반환합니다. `cooldown_active`는 백엔드가 같은 쿨다운 시간 의미로 계산하며, Web은 브라우저에서 시간대 정보 없는(naive) ISO 문자열을 해석해 상태를 추측하지 않습니다.
- Web 경보 센터는 쿨다운 상태와 알림 결과를 읽기 전용으로 보여 줄 뿐이며, cooldown policy 편집 폼은 제공하지 않습니다.

P4에서 하지 않는 일:

- 기술 지표, 보유 종목, 관심 종목, portfolio, watchlist, Market Light 경보 규칙을 추가하지 않습니다.
- 대상(target) 단위로 여러 규칙을 묶는 쿨다운은 구현하지 않습니다. 대상 단위 병합은 보유 종목/시장 연동 단계로 미룹니다.
- 알림 채널 게이트웨이를 다시 작성하지 않습니다. `NotificationService.send()`는 계속 불리언 반환과 호환되며, 구조화된 결과는 새로 추가한 호환 인터페이스로 제공합니다.
- legacy `AGENT_EVENT_ALERT_RULES_JSON`을 자동으로 옮기거나, 삭제하거나, 고쳐 쓰지 않습니다.

## P5 기술 지표 규칙
<!-- 계약 키(tests): ## P5 技术指标规则 | 最近两根已收盘日线 | 服务器本地时区启发式 | 日期不可判定都会保守丢弃 | legacy JSON 路径 | 不扩展 `src/agent/events.py` | 不支持 MACD 柱体放大/收缩 | 不支持 KDJ 超买/超卖区规则 | 不支持 MA 与 MA 双均线交叉 | 不支持分钟线 | revert P5 PR | skip unsupported `alert_type` -->

P5는 기존 Alert API, Web 경보 센터, `src/services/alert_worker.py` 평가 경로에 일봉 기술 지표 규칙을 추가합니다. 규칙은 여전히 `alert_rules`에 저장되며, 발동, 성능 저하, 실패, 알림 결과, 저장형 쿨다운은 P2-P4의 `alert_triggers`, `alert_notifications`, `alert_cooldowns` 의미를 그대로 재사용합니다.

P5가 지원하는 `alert_type`과 `parameters`:

| alert_type | parameters | 발동 의미 |
| --- | --- | --- |
| `ma_price_cross` | `direction=above|below`, `window` 기본값 `20`, 정수 `[2,250]` | 종가(close)가 MA(window)를 경계에서 상향/하향 돌파 |
| `rsi_threshold` | `direction=above|below`, `period` 기본값 `12`, 정수 `[2,250]`, `threshold` 필수이며 `0..100` | RSI가 임계값을 경계에서 상향/하향 돌파 |
| `macd_cross` | `direction=bullish_cross|bearish_cross`, `fast_period=12`, `slow_period=26`, `signal_period=9`, 모두 `[2,250]`이며 `fast_period < slow_period` | DIF/DEA의 경계 골든크로스/데드크로스 |
| `kdj_cross` | `direction=bullish_cross|bearish_cross`, `period=9`, `k_period=3`, `d_period=3`, 모두 `[2,250]` | K/D의 경계 골든크로스/데드크로스 |
| `cci_threshold` | `direction=above|below`, `period` 기본값 `14`, 정수 `[2,250]`, `threshold` 필수이며 유한한 숫자 | CCI가 임계값을 경계에서 상향/하향 돌파 |

평가 규칙:

- 첫 버전은 모두 일봉 close를 사용하며, 분봉은 다루지 않습니다.
- 경계 발동은 마감된 최근 일봉 두 개만 비교합니다. 경계를 넘은 것이 아니라 현재 수준이 이미 임계값을 만족하는 상태라면 `not_triggered`를 반환합니다. 규칙을 만든 첫날 과거 상태를 새 발동으로 잘못 보고하지 않기 위해서입니다.
- 경계 발동에는 직전 봉이 임계값이나 0축과 정확히 같은 경우도 포함됩니다. `above` / `bullish_cross`는 `prev <= threshold < current`, `below` / `bearish_cross`는 `prev >= threshold > current`를 사용합니다.
- 장중 미완성 봉(partial bar)은 서버 로컬 시간대 기준의 추정 규칙만 사용합니다. 현재 로컬 시간이 16:00 이전이면, 마지막 행의 날짜가 로컬 기준 오늘이거나 날짜를 판단할 수 없을 때 모두 보수적으로 버립니다. A주, 홍콩 주식, 미국 주식의 시장 시간대나 거래일 달력은 구분하지 않습니다. Issue #1386 P0의 시장 단계(장전/장중/장후) 기준선은 아직 기술 지표 규칙에 연결하지 않으며, 경보용 partial bar의 정밀 판정은 이후 단계로 미룹니다.
- `src/services/alert_indicators.py`가 직접 OHLCV를 정규화하고 MA, RSI, MACD, KDJ, CCI를 계산합니다. fetcher가 미리 계산한 MA5/MA10/MA20에 의존하지 않습니다.
- RSI는 Wilder's EMA / SMMA를 사용합니다: `avg_gain = gain.ewm(alpha=1/period, adjust=False).mean()`, `avg_loss`도 같은 방식이며, rolling SMA는 쓰지 않습니다.
- MACD는 `EMA(fast_period) - EMA(slow_period)`로 DIF를 구하고, DEA는 DIF의 `EMA(signal_period)`입니다. 골든크로스/데드크로스는 DIF-DEA가 0을 경계에서 넘는지 비교합니다.
- KDJ는 최근 `period`일의 최고가/최저가로 RSV를 계산하고, `alpha=1/k_period`, `alpha=1/d_period`인 EMA로 K/D를 구합니다. 골든크로스/데드크로스는 K-D가 0을 경계에서 넘는지 비교합니다.
- CCI는 대표 가격 `(high + low + close) / 3`을 쓰며, `period`일 평균과 평균 절대 편차로 `(TP - MA(TP)) / (0.015 * mean_deviation)`을 계산합니다.
- `compute_required_bars(alert_type, params)`는 필요한 최소 유효 closed bars 수를 정의합니다: MA=`window+1`, RSI=`period+1`, MACD=`slow_period+signal_period+1`, KDJ=`period+k_period+d_period+1`, CCI=`period+1`.
- 가져올 일수는 `requested_days = min(max(required_bars * 3, required_bars + 30), 365)`입니다. API는 `required_bars > 365`가 되는 기간 조합을 거부하여 표본이 영원히 부족한 규칙이 만들어지지 않게 합니다. 같은 worker 회차 안에서는 `(stock_code, requested_days)` 단위로 일봉 데이터를 캐시하고, 회차가 끝나면 해제합니다.
- 데이터 누락, 열 누락, 유효 표본이 `required_bars`보다 적으면 `degraded`로 기록합니다. 데이터 소스 예외는 `volume_spike`와 같은 의미로 `evaluation_error` / `failed`를 반환하며 알림을 보내지 않습니다.

호환 경계:

- `AGENT_EVENT_ALERT_RULES_JSON`은 여전히 legacy JSON 경로이며 `price_cross`, `price_change_percent`, `volume_spike` 세 가지만 지원합니다. P5 기술 지표 규칙은 Alert API / Web에서만 만들 수 있습니다.
- `src/agent/events.py`의 legacy `AlertType`이나 `_RUNTIME_SUPPORTED_ALERT_TYPES`는 확장하지 않습니다.
- P5 생성/수정 시 매개변수 오류는 기존 Alert API 오류 계약을 따릅니다: HTTP 400 + `validation_error`. unsupported 유형은 HTTP 400 + `unsupported_alert_type`을 반환합니다.
- Web 경보 센터는 기존 생성 폼, 목록 표시, 유형 필터, dry-run 테스트만 확장하며 규칙 편집기는 추가하지 않습니다. dry-run 테스트는 발동 이력을 쓰지 않고, API 응답도 여전히 `triggered` / `not_triggered` / `evaluation_error` 세 가지 상태를 씁니다. worker가 기록한 `degraded` 상태는 발동 이력에서 확인합니다.
- P5 PR을 revert하면 데이터베이스에 이미 만든 기술 지표 규칙 기록은 남습니다. 이전 코드는 worker 로드 단계에서 unsupported `alert_type`을 skip하므로, legacy 세 가지 규칙은 계속 실행됩니다. 정리가 필요하면 관리자가 확인한 뒤 해당 `alert_rules` 기록을 수동으로 삭제해야 합니다.

P5에서 하지 않는 일:

- MACD 막대(histogram) 확대/축소는 지원하지 않습니다.
- KDJ 과매수/과매도 구간 규칙은 지원하지 않습니다.
- MA와 MA의 이동평균선 교차(두 이동평균선 교차)는 지원하지 않습니다.
- 분봉, 시장 달력 기반 정밀 판정, 여러 시장 시간대의 정밀 partial bar 판정은 지원하지 않습니다.
- legacy `AGENT_EVENT_ALERT_RULES_JSON`의 기술 지표 규칙은 지원하지 않습니다.
- DSL, 규칙 엔진, 새 데이터베이스 테이블, 분석 리포트 pipeline 안의 기술 지표 규칙 엔진은 도입하지 않습니다.

## P6 보유 종목과 관심 종목 연동
<!-- 계약 키(tests): ### 持仓 -->
<!-- 계약 키(tests): ## P6 持仓与自选股联动 | P6 scope/type 矩阵 | 父规则摘要 | legacy `AGENT_EVENT_ALERT_RULES_JSON` 不支持 watchlist、portfolio | sector 级集中度 | P6 PR -->

P6는 기존 Alert API, Web 경보 센터, `src/services/alert_worker.py` 평가 경로에 `watchlist`, `portfolio_holdings`, `portfolio_account` 세 가지 대상 범위를 추가합니다. 규칙은 여전히 `alert_rules`에 저장되며, 발동, 성능 저하, 실패, 알림 결과, 저장형 쿨다운은 P2-P4의 `alert_triggers`, `alert_notifications`, `alert_cooldowns` 의미를 그대로 재사용합니다. 테이블이나 마이그레이션은 추가하지 않습니다.

### P6 scope/type 매트릭스

| `target_scope` | `target` | 허용되는 `alert_type` | 평가 방식 |
| --- | --- | --- | --- |
| `single_symbol` | 종목 코드 | P1 가격/거래량 규칙 3종 + P5 기술 지표 | 규칙 하나, 종목 하나 |
| `watchlist` | `default` | P1 가격/거래량 규칙 3종 + P5 기술 지표 | 매 회차마다 현재 `STOCK_LIST`를 새로 읽어 종목 코드별로 펼침 |
| `portfolio_holdings` | `all` 또는 active account ID | P1 가격/거래량 규칙 3종 + P5 기술 지표 | 보유 종목 snapshot에서 수량이 0이 아닌 종목을 symbol로 펼치고 symbol 기준으로 중복 제거 |
| `portfolio_account` | `all` 또는 active account ID | `portfolio_stop_loss`, `portfolio_concentration`, `portfolio_drawdown`, `portfolio_price_stale` | 계좌 단위 리스크 평가이며 개별 종목으로 펼치지 않음 |

규칙을 생성/수정할 때 `watchlist` / `portfolio_holdings`는 상위 `target`을 종목 코드로 검증하지 않습니다. `portfolio_account`는 가격/거래량/기술 지표 유형을 허용하지 않습니다. `portfolio_holdings`와 `portfolio_account`는 `target=<id>`일 때 계좌가 존재하고 active인지 검증하며, 없으면 HTTP 400 + `validation_error`를 반환합니다. legacy `AGENT_EVENT_ALERT_RULES_JSON`은 watchlist, portfolio, 기술 지표 확장을 지원하지 않으며, 계속 `single_symbol`의 `price_cross`, `price_change_percent`, `volume_spike`만 지원합니다.

### Target Identity Contract (대상 식별 계약)

P6는 화면에 보여 줄 대상과 저장할 대상을 분리합니다.

| 상황 | `effective_target` | `display_target` |
| --- | --- | --- |
| `single_symbol` | `<symbol>` | `<symbol>` |
| `watchlist`를 펼친 하위 대상 | `<symbol>` | `自选股 - <symbol>` (화면 표시 문자열, "관심 종목 - <symbol>") |
| `portfolio_holdings`를 펼친 하위 대상 | `<symbol>` | `持仓 - <symbol>` (화면 표시 문자열, "보유 종목 - <symbol>") |
| `portfolio_account target=all` | `account:all` | `全部账户` (화면 표시 문자열, "전체 계좌") |
| `portfolio_account target=<id>` | `account:<id>` | `账户 <id>` (화면 표시 문자열, "계좌 <id>") |

> 위 표의 `display_target` 값은 프로그램이 실제로 만들어 내는 문자열이라 원문 그대로 두었습니다.

- `alert_triggers.target`, `alert_cooldowns.target`, P4의 `rule_id + target + data_source + data_timestamp` 중복 제거는 모두 `effective_target`을 사용합니다.
- `RuntimeAlertRule.key`는 펼친 하위 대상에 `{parent_key}|{effective_target}`를 사용합니다. DB 쿨다운 읽기가 실패했을 때 프로세스 내부 fallback이 같은 상위 규칙 아래의 서로 다른 하위 대상을 서로 억제하지 않게 하기 위해서입니다.
- `display_target`은 `alert_triggers.target`에 쓰지 않으며, 알림 제목, dry-run `target_results`, Web 표시에만 씁니다.
- P6는 규칙을 넘나드는 같은 종목 알림 병합을 하지 않습니다. 같은 종목이 watchlist 하위 규칙과 별도 `single_symbol` 규칙에 동시에 걸리면, 규칙마다 따로 기록하고 따로 알립니다.

### Dry-run 집계

- `POST /api/v1/alerts/rules/{rule_id}/test`는 여러 대상을 가진 규칙에 대해 집계 필드를 반환합니다: `evaluated_count`, `triggered_count`, `degraded_count`, `skipped_count`, `target_results`.
- 펼친 대상의 soft cap(권장 상한)은 100입니다. dry-run에서 soft cap을 넘는 대상은 `degraded` 집계 결과로 기록하고 로그를 남깁니다. worker 런타임은 펼친 대상 중 앞의 100개만 평가하고 warning을 남기며, 초과분 자체에 대해서는 `alert_triggers` 이력을 쓰지 않습니다.
- dry-run은 동시 실행 수를 제한해 평가하며, 대상 하나당 10초, 전체 평가 30초 제한이 있습니다. 끝나지 않은 대상은 `skipped`로 기록합니다.
- 어느 대상이라도 triggered이면 최상위 `status=triggered`입니다. 발동은 없지만 성공한 평가, skipped, degraded가 있으면 최상위 `status=not_triggered`입니다. 펼칠 수 없거나 전부 실패했을 때만 `evaluation_error`를 반환합니다.
- 빈 watchlist / 빈 holdings: dry-run은 `not_triggered`를 반환하고 `target_results`에 `record_status=skipped`를 담습니다. worker는 `skipped` 이력을 기록합니다.
- `degraded_count`는 펼친 전체 평가 결과 중 `record_status=degraded`인 항목 수입니다. `target_results`는 앞의 20개만 보여 주며, triggered를 먼저, 그다음 degraded/failed, 그다음 target 순으로 정렬합니다.

### 보유 종목 리스크 규칙

| `alert_type` | 매개변수 | 관측값 | 발동 의미 |
| --- | --- | --- | --- |
| `portfolio_stop_loss` | `mode=near|breach`, 기본값 `near` | 영향받는 종목 중 최대 `loss_pct` | `near`는 `stop_loss.near_alert`를 사용하고, `breach`는 `is_triggered=true`인 items만 셉니다. 계좌당 회차마다 trigger는 최대 한 건 |
| `portfolio_concentration` | - | `concentration.top_weight_pct` | `top_weight_pct >= portfolio_risk_concentration_alert_pct` |
| `portfolio_drawdown` | - | `drawdown.max_drawdown_pct` | `PortfolioRiskService`의 `drawdown.alert`를 재사용. `current_drawdown_pct`는 diagnostics에 기록 |
| `portfolio_price_stale` | - | 가격이 오래되었거나(stale) 없는 보유 종목 수 | position 중 하나라도 `price_stale=true` 또는 `price_available=false` |

portfolio diagnostics에는 반드시 `account_id`(또는 `all`), `currency`, `as_of`, `price_stale`, `fx_stale`, `data_available`, `top_affected_symbols`가 들어 있어야 합니다. `portfolio_stop_loss`, `portfolio_concentration`, `portfolio_drawdown`은 `PortfolioRiskService.get_risk_report()`를 재사용하고, `portfolio_price_stale`은 `PortfolioService.get_portfolio_snapshot()`의 position price metadata를 재사용합니다.

### Web과 cooldown 요약

- Web 생성 폼에 대상 범위 선택이 추가됩니다. `watchlist` / `portfolio_holdings`는 가격/거래량/P5 기술 지표 유형만, `portfolio_account`는 portfolio 리스크 유형 네 가지만 보여 줍니다.
- `portfolio_holdings` / `portfolio_account`에서 계좌 목록을 불러오지 못하면, 폼은 `all` 옵션을 남겨 두고 오류를 표시합니다.
- 규칙 목록의 `cooldown_active`는 `single_symbol`과 `portfolio_account`에 대해서는 정확합니다. `watchlist` / `portfolio_holdings`는 상위 규칙 요약일 뿐 각 하위 대상의 쿨다운 상태를 나타내지 않으며, 하위 대상의 쿨다운은 발동 이력과 `effective_target`을 기준으로 봅니다.
- dry-run UI는 집계 개수와 최대 20개의 `target_results` 상세를 보여 줍니다.

P6에서 하지 않는 일:

- P7 Market Light는 하지 않습니다.
- 실적 발표일 전, 배당/권리락일 전 알림은 하지 않습니다. 이런 규칙은 안정적인 날짜 계약이 생긴 뒤 별도 follow-up으로 진행합니다.
- sector(업종) 단위 집중도 경보는 하지 않습니다. P6 집중도는 symbol 단위 `top_weight_pct`를 사용합니다.
- 규칙을 넘나드는 같은 종목 알림 병합, 분봉, 여러 시장 시간대의 정밀 판정, legacy JSON 확장은 하지 않습니다.

## 시장 단계 인식과 공개 요약 연동 (Refs #1386 P6)

이 절은 #1386 P6의 경보 가시성 연동을 설명하며, 위의 "P6 보유 종목과 관심 종목 연동"과는 다른 내용입니다. 이 연동은 경보 테이블을 추가하지 않고, migration도 하지 않으며, 가벼운 LLM 분석을 자동으로 실행하지도 않습니다. 발동 당시 공개할 수 있는 phase/pack 요약만 기존 발동 이력에 기록합니다.

- `AlertTriggerItem`은 `diagnostics` 문자열을 그대로 두고, 파생 필드 `market_phase_summary`, `analysis_context_pack_overview`, `analysis_visibility_source`를 추가합니다.
- 실제 `status=triggered`인 worker 기록은 JSON diagnostics에 형제 키 `analysis_visibility`를 합쳐 넣으며, 여기에는 `market_phase_summary`, `analysis_context_pack_overview`, `source`가 들어갑니다. 예전 일반 텍스트 diagnostics는 원문을 유지하고, API 파생 필드는 `null`, source는 `legacy_text`를 반환합니다.
- `analysis_visibility_source` 값은 `alert_trigger_market_context`, `analysis_history_snapshot`, `evaluator_snapshot`, `legacy_text`, `null` 중 하나입니다.
- symbol 대상은 `get_market_for_stock(normalize_stock_code(effective_target))`로 발동 시점의 phase를 만듭니다. `target_scope=market`은 `normalize_market_region(target)`을 바로 쓰며, `cn|hk|us|jp|kr`를 종목 코드로 추정하지 않습니다. 계좌 단위처럼 시장을 하나로 특정할 수 없으면 summary가 `unknown`이 될 수 있습니다.
- `analysis_context_pack_overview`는 evaluator가 이미 가지고 있는 overview 또는 최근 30일 안의 이력 snapshot에서만 가져옵니다. 최근 이력 조회는 이력 서비스의 코드 변형 후보를 재사용하며, best-effort 방식과 배치 안 단기 캐시로 실행합니다. 없거나 해석에 실패하면 `null`을 반환하며, pack을 꾸며 내지 않습니다.
- 경보 알림은 공개 요약만 출력합니다: 단계 라벨, trigger source, partial-bar warning, 데이터 품질 등급, 앞의 두 개 limitations. 알림에는 raw context pack, Prompt, 뉴스 본문, 전체 diagnostics JSON, webhook URL, token, 민감한 보유 종목 세부 정보가 들어가면 안 됩니다.
- Web 경보 이력은 phase 배지, 데이터 품질 등급, limitations 빈 상태를 보여 줍니다. 예전 발동 기록에 공개 요약이 없어도 목록 읽기에는 영향이 없습니다.
- #1390 P6는 여기서 더 나아가 `DecisionSignal`을 재사용합니다. 종목 단위의 실제 발동은 같은 종목의 최신 active 신호를 우선 연결하고, 민감도가 낮은 `decision_signal_summary`를 diagnostics에 기록합니다. active 신호가 없을 때만 최소한의 `source_type=alert/action=alert` 신호를 만듭니다. `trace_id=alert-rule-<hash>`는 같은 출처의 재시도를 best-effort로 멱등 처리하는 데만 쓰며, active 신호를 덮어쓰지 않습니다. 새로 만든 경보 신호에는 `market_phase`를 쓰지 않아, 같은 규칙이 단계가 바뀔 때마다 중복 생성되지 않게 합니다. `market`, `portfolio_account`, overflow, 또는 구체적인 종목으로 해석할 수 없는 발동은 개별 종목 신호를 만들지 않습니다.

DecisionSignal 필드, 마스킹, 마이그레이션, 롤백 경계는 [DecisionSignal 결정 신호 문서](decision-signals.md)를 참고하십시오.

<!-- 계약 키(tests): #1386 P7 的用户边界：告警联动只解释触发时已经可公开的阶段和数据质量摘要，不会自动发起轻量 LLM 盘中分析，也不会新增告警表、规则类型、环境变量或 migration。需要阶段化分析时，仍应通过分析 API / Web 手动分析入口触发；告警通知只保留阶段标签、trigger source、partial-bar warning、数据质量等级和前两条 limitations。 -->
#1386 P7의 사용자 경계: 경보 연동은 발동 당시 이미 공개할 수 있는 단계와 데이터 품질 요약만 설명하며, 가벼운 LLM 장중 분석을 자동으로 실행하지 않습니다. 경보 테이블, 규칙 유형, 환경 변수, migration도 추가하지 않습니다. 단계별 분석이 필요하면 여전히 분석 API / Web 수동 분석 메뉴로 실행해야 합니다. 경보 알림에는 단계 라벨, trigger source, partial-bar warning, 데이터 품질 등급, 앞의 두 개 limitations만 남습니다.

<!-- 계약 키(tests): 回滚本联动 -->
이 연동을 롤백하려면 worker/API/Web 변경만 revert하면 됩니다. 이미 기록된 `diagnostics.analysis_visibility`는 일반 JSON diagnostics로 남으며, 이전 코드는 이 형제 키를 읽지 않습니다.

## P7 시장 신호등 구조화 경보
<!-- 계약 키(tests): ## P7 大盘红绿灯结构化告警 | 双向约束 | 最大 `snapshot.trade_date` | 旧交易日 backfill | legacy `AGENT_EVENT_ALERT_RULES_JSON` 不支持 market 规则 | revert P7 PR -->

P7은 기존 Alert API, Web 경보 센터, `src/services/alert_worker.py`에 `target_scope=market`을 추가합니다. 구조화된 `MarketLightSnapshot`을 사용하며, Markdown을 해석하지 않고, legacy `AGENT_EVENT_ALERT_RULES_JSON`을 확장하지 않으며, 테이블도 추가하지 않습니다. 시장 리뷰 이력은 여전히 `analysis_history(code=MARKET, report_type=market_review)` 한 건으로 기록됩니다. 여러 시장을 리뷰할 때는 `context_snapshot.market_light_snapshots`에 이번에 실제로 리뷰한 스냅샷을 region별 map으로 저장합니다.

> 시장 신호등(Market Light)은 시장 전체 분위기를 빨강/노랑/초록 세 단계로 요약한 지표입니다.

### P7 scope/type 매트릭스

| `target_scope` | `target` | 허용되는 `alert_type` | 매개변수 | 발동 의미 |
| --- | --- | --- | --- | --- |
| `market` | `cn` / `hk` / `us` / `jp` / `kr` | `market_light_status` | `statuses=["red","yellow"]`, `red/yellow`만 허용, 기본값 `["red","yellow"]` | 현재 `MarketLightSnapshot.status`가 목록에 포함되면 발동 |
| `market` | `cn` / `hk` / `us` / `jp` / `kr` | `market_light_score_drop` | `min_drop > 0` | `prev.score - current.score >= min_drop`이고 `prev.trade_date < current.trade_date` |

scope/type 검증은 양방향 제약입니다. `target_scope=market`은 Market Light 규칙 두 가지만 쓸 수 있고, `market_light_*` 규칙도 `target_scope=market`만 쓸 수 있습니다. `target`은 `strip().lower()`를 거친 뒤 `cn|hk|us|jp|kr`로 엄격히 제한되며, 잘못된 target은 HTTP 400 + `validation_error`를 반환합니다.

### `MarketLightSnapshot` 계약

구조화 스냅샷 필드는 `region`, `trade_date`, `status`, `score`, `label`, `temperature_label`, `reasons`, `guidance`, `dimensions`, `data_quality`입니다. 첫 버전의 `trade_date`는 항상 `MarketOverview.date`를 사용하며, P7은 provider 시세의 as-of 시각을 해석하지 않습니다.

`dimensions`는 canonical scorer(표준 채점기) 하나만 출처로 사용합니다. `build_market_light_snapshot()`, 시장 리뷰 주입 블록, 경보 service는 점수 계산을 따로 구현하지 않습니다. `_build_market_temperature()`는 thin wrapper일 뿐입니다. 신호등 `status` 임계값은 `60/40`, temperature label 임계값은 `70/55/40`으로 유지합니다.

| dimension | `available=true` 조건 | fallback score |
| --- | --- | --- |
| `breadth` | `has_market_stats && (up_count + down_count) > 0` | `50` |
| `index` | `indices`가 비어 있지 않고 최소 하나의 `change_pct != None` | `50` |
| `limit` | `has_market_stats && (limit_up_count + limit_down_count) > 0` | `50` |

> `limit` 차원은 상·하한가(중국 A주는 보통 하루 ±10%) 종목 수를 바탕으로 합니다.

`data_quality=unavailable`은 `index.available=false`를 뜻하며, 두 market 규칙 모두 `skipped`를 반환하고 알림을 보내지 않습니다. `partial`은 적어도 한 차원이 fallback이라는 뜻이고, `ok`는 세 차원이 모두 available이라는 뜻입니다. `market_light_status`는 `ok/partial`에서 발동할 수 있으며, `partial`로 발동하면 diagnostics에 반드시 `missing_dimensions`가 있어야 합니다. `market_light_score_drop`은 canonical 종합 점수를 바로 비교합니다. 어느 한쪽이 `partial`이어도 비교는 할 수 있지만, diagnostics에 반드시 `partial_comparison=true`와 `missing_dimensions`가 있어야 합니다.

### 기준선, 거래일, 중복 제거

- 시장 리뷰를 저장할 때는 리포트 생성에 쓴 것과 같은 `MarketOverview`로 `MarketLightSnapshot`을 만들어야 하며, 저장 단계에서 시세를 다시 가져오면 안 됩니다.
- `load_previous_snapshot(region, before_trade_date)`는 `analysis_history(code=MARKET, report_type=market_review)`를 훑으며 `context_snapshot.market_light_snapshots[region]`이 없는 legacy 기록은 건너뜁니다. 먼저 `before_trade_date`보다 작은 가장 큰 `snapshot.trade_date`를 고르고, 같은 `trade_date` 안에서는 `created_at DESC, id DESC` 순으로 가장 최신의 유효한 스냅샷을 가져옵니다. 나중에 들어온 과거 거래일 backfill이 올바른 기준선을 덮어쓰지 않습니다.
- 대상 `trade_date`에 손상된 스냅샷만 있으면 `market_light_score_drop`은 `degraded`를 반환하며, 더 오래된 거래일로 자동으로 물러나 best-effort 비교를 하지 않습니다.
- 첫 버전의 `market_light_score_drop`은 거래일 사이 비교만 합니다. 직전 거래일 기준선이 없거나 같은 날 기준선만 있으면 `skipped`, 조회/해석 예외는 `degraded`를 반환합니다.
- worker는 `target_scope=market`에 대해 region별 거래일 확인을 하며, `TRADING_DAY_CHECK_ENABLED` / `config.trading_day_check_enabled`를 따릅니다. 확인을 끄면 평가를 허용하고, 확인을 켠 상태에서 해당 region이 휴장일이면 `skipped`를 반환하며 현재 스냅샷을 가져오지 않습니다.
- 발동 이력에는 `target=<region>`, `observed_value=<score>`, `data_source=market_light`, `data_timestamp=<trade_date 00:00:00>`를 기록하며, P4의 `rule_id + target + data_source + data_timestamp` 중복 제거를 계속 재사용합니다.

### Web과 롤백 경계

- Web 경보 센터에 `market` scope, region 선택, market 규칙 두 가지의 매개변수 입력, 유형 필터, region 표시, 매개변수 표시가 추가됩니다. API의 snake_case 매핑은 `statuses`와 `min_drop`을 사용합니다.
- legacy `AGENT_EVENT_ALERT_RULES_JSON`은 market 규칙을 지원하지 않습니다. 새 설정 항목이 없으므로 P7은 `.env.example`을 수정하지 않습니다.
- P7은 지수 하락률, 업종 이상 움직임, 상·하한가 구조 악화, 분봉, 여러 시장 시간대의 정밀한 시세 as-of 해석을 다루지 않으며, DSL/규칙 엔진도 추가하지 않습니다.

## P8 사용자 설정과 배포 경계
<!-- 계약 키(tests): ## P8 用户配置与部署边界 | Alert API / Web 告警中心持久化规则 | 只兼容 `single_symbol` | P5 技术指标、P6 watchlist/portfolio 或 P7 market light | 保留 `data/` 数据库卷 | 一次性分析 workflow | 不运行 `--schedule` 后台 alert worker | 没有映射 `AGENT_EVENT_*` | Desktop 不新增原生告警管理界面 | `triggered`、`skipped`、`degraded`、`failed` | 回滚 P8 只需 revert 文档、配置说明和 Web 文案改动 -->

P8은 규칙 유형, API, 테이블 구조, worker 동작을 추가하지 않습니다. P0-P7에서 이미 병합된 기능을 사용자와 배포 담당자를 위한 설정 안내로 정리합니다. 경보 worker는 schedule 모드에서만 등록되며, 핵심 스위치는 여전히 `AGENT_EVENT_MONITOR_ENABLED`, 폴링 간격은 여전히 `AGENT_EVENT_MONITOR_INTERVAL_MINUTES`입니다. 알림 채널은 계속 alert 라우팅을 따르며, 자세한 내용은 [알림 설정](notifications.md)의 `NOTIFICATION_ALERT_CHANNELS`와 `route_type=alert`를 참고하십시오.

### 로컬 설정

로컬에서 `python main.py --schedule`, `python main.py --serve --schedule` 또는 같은 역할의 내장 예약 실행 모드로 실행할 때 `AGENT_EVENT_MONITOR_ENABLED=true`를 설정하면 백그라운드 경보 worker가 시작됩니다. `AGENT_EVENT_MONITOR_INTERVAL_MINUTES`로 폴링 간격을 조절합니다.

규칙 출처는 두 가지입니다.

- Alert API / Web 경보 센터의 저장 규칙: 권장 진입점입니다. `single_symbol`, `watchlist`, `portfolio_holdings`, `portfolio_account`, `market`을 지원하며 실시간 가격, 등락률, 거래량, 일봉 기술 지표, 보유 종목 리스크, 시장 신호등 규칙을 다룹니다.
- legacy `AGENT_EVENT_ALERT_RULES_JSON`: `single_symbol`의 `price_cross`, `price_change_percent`, `volume_spike` 세 가지 기본 규칙만 호환합니다. P5 기술 지표, P6 watchlist/portfolio, P7 market light는 지원하지 않습니다. 시스템은 legacy JSON을 자동으로 옮기거나, 삭제하거나, 고쳐 쓰지 않습니다.

### Docker

저장소의 `docker/Dockerfile` 기본 명령은 `python main.py --schedule`이므로, 컨테이너에서 `AGENT_EVENT_MONITOR_ENABLED=true`만 설정하면 schedule 모드에서 경보 worker가 켜집니다. Web/API 저장 규칙은 애플리케이션 데이터베이스에 의존합니다. Docker로 배포할 때는 `data/` 데이터베이스 볼륨을 반드시 유지해야 컨테이너를 다시 만들어도 규칙, 발동 이력, 알림 시도, 쿨다운 상태가 사라지지 않습니다. legacy JSON은 여전히 환경 변수로 주입하며, Docker 전용 설정 체계가 아닙니다.

### GitHub Actions

저장소에 들어 있는 `.github/workflows/00-daily-analysis.yml`은 한 번 실행하고 끝나는 분석 workflow입니다. 실제로는 `python main.py`, `python main.py --market-review`, `python main.py --no-market-review`를 호출하며, `--schedule` 백그라운드 alert worker는 실행하지 않고 `AGENT_EVENT_*` 변수도 연결하지 않습니다. repository Secrets / Variables에 `AGENT_EVENT_MONITOR_ENABLED`나 `AGENT_EVENT_ALERT_RULES_JSON`만 추가해서는 기본 Actions가 경보를 계속 폴링하지 않습니다.

GitHub Actions에서 경보 폴링이 필요하면, 이후 별도 PR에서 schedule 시작 방식, 환경 변수 연결, 규칙 출처, 저장 데이터베이스 전략을 명확히 정해야 합니다. P8은 기존 workflow를 바꾸지 않습니다.

### Web과 Desktop

Web 경보 센터 `/alerts`는 저장 규칙의 주 진입점입니다. 규칙을 만들고, 켜고 끄고, 삭제할 수 있으며, 일회성 dry-run 테스트를 실행하고, 발동 이력, 알림 시도, 읽기 전용 쿨다운 상태를 볼 수 있습니다. 여러 대상을 가진 규칙의 목록 쿨다운 상태는 상위 규칙 요약이며, 하위 대상의 쿨다운 여부는 발동 이력의 `target` / `effective_target`을 기준으로 봅니다.

Desktop에는 별도의 네이티브 경보 관리 화면을 추가하지 않습니다. 데스크톱 사용자는 내장 또는 외부 WebUI의 `/alerts` 페이지를 그대로 사용합니다. Desktop을 롤백할 때 따로 정리할 상태는 없습니다.

### 상태, 알림, 롤백

worker는 `triggered`, `skipped`, `degraded`, `failed`를 `alert_triggers`에 평가 이력으로 기록하며, 정상적으로 발동하지 않은 경우는 기록하지 않습니다. `skipped`는 이번 회차에 평가할 조건이 없었다는 뜻입니다(예: market 휴장일, 직전 거래일 기준선 없음). `degraded`는 데이터 소스, 보유 종목 스냅샷, 이력 스냅샷, 해석 과정에 이상이 있어 결과를 알림 발동에 쓸 수 없다는 뜻입니다.

실제로 발동하면 `alert_notifications`와 `alert_cooldowns`에 기록합니다. DB 저장 규칙은 `rule_id + target + data_source + data_timestamp` 기준으로 같은 데이터 지점을 best-effort로 중복 제거합니다. legacy JSON 규칙은 계속 프로세스 내부 fingerprint만 쓰며, 저장형 쿨다운을 기록하지 않습니다.

P8을 롤백하려면 문서, 설정 안내, Web 문구 변경만 revert하면 됩니다. 데이터베이스 마이그레이션이나 사용자 데이터 정리는 없습니다. 이전 Phase를 롤백할 때 이미 만든 저장 규칙은 자동으로 삭제되지 않으며, 아래 Phase별 롤백 안내에 따라 처리합니다.

## Phase 경계

- P0: 이 문서, 계약, 저장 방식 검토, 호환 테스트.
- P1: Alert API MVP. 첫 버전은 기존 runtime 규칙 세 가지만 다룹니다.
- P2: 경보 평가 worker와 runtime 통합. 저장된 active rules와 legacy JSON이 함께 동작합니다.
- P3: Web 경보 센터 MVP.
- P4: 발동 이력, 알림 결과, 쿨다운 상태.
- P5: 기술 지표 규칙.
- P6: 보유 종목과 관심 종목 연동.
- P7: 시장 신호등과 시장 연동.
- P8: 문서, 마이그레이션, 마무리.

## P0에서 하지 않는 일
<!-- 계약 키(tests): ## P0 不做 | P0 阶段不新增 `api/v1/schemas/alerts.py` | P0 阶段不新增 Web 告警中心页面 | P0 阶段不新增数据库表 | P0 阶段不实现触发历史 | P0 阶段不自动迁移、删除或覆盖 `AGENT_EVENT_ALERT_RULES_JSON` | P0 阶段不重写 `NotificationService` -->

- P0 단계에서는 `api/v1/schemas/alerts.py`나 Alert API를 추가하지 않습니다.
- P0 단계에서는 Web 경보 센터 페이지, 라우트, 사이드바 메뉴를 추가하지 않습니다.
- P0 단계에서는 데이터베이스 테이블, repository, migration을 추가하지 않습니다.
- P0 단계에서는 발동 이력, 알림 결과, 쿨다운 상태 쓰기를 구현하지 않습니다.
- P0 단계에서는 `AGENT_EVENT_ALERT_RULES_JSON`을 자동으로 옮기거나, 삭제하거나, 덮어쓰지 않습니다.
- P0 단계에서는 MACD, KDJ, CCI, RSI, 보유 종목 리스크, Market Light 경보 규칙을 구현하지 않습니다.
- P0 단계에서는 `NotificationService`나 알림 라우팅 구조를 다시 작성하지 않습니다.

## 롤백
<!-- 계약 키(tests): P1 新增 Alert API 代码 | `alert_rules` / `alert_triggers` / `alert_notifications` SQLite 表 | SQLite 表与数据不会自动删除 | 手动删除相关表 | 最小回滚方式是 revert P4 PR | revert P7 PR | P6 PR -->

- P0는 문서와 테스트 정리입니다. P0만 롤백한다면 해당 PR을 revert하면 되며, 따로 처리할 데이터베이스, 설정, 사용자 데이터 마이그레이션은 없습니다.
- P1은 Alert API 코드와 `alert_rules` / `alert_triggers` / `alert_notifications` SQLite 테이블을 추가합니다. 최소 롤백 방법은 P1 PR revert입니다. revert하면 API, service, repository, schema, ORM 정의는 사라지지만, 이미 `Base.metadata.create_all()`로 만들어진 SQLite 테이블과 데이터는 자동으로 삭제되지 않습니다. 정리가 필요하면 관리자가 이력 데이터가 더 이상 필요 없는지 확인한 뒤 해당 테이블을 수동으로 삭제해야 합니다.
- P3는 Web과 문서 변경입니다. 최소 롤백 방법은 P3 PR revert이며, 기존 규칙, 발동 이력, legacy JSON 설정은 삭제되지 않습니다.
- P4는 `alert_cooldowns` SQLite 테이블을 추가하고 `alert_notifications`에 쓰기 시작합니다. 최소 롤백 방법은 P4 PR revert입니다. 이미 만들어진 `alert_cooldowns`, `alert_triggers`, `alert_notifications` 데이터는 자동으로 삭제되지 않습니다. 정리가 필요하면 관리자가 확인한 뒤 해당 테이블이나 기록을 수동으로 삭제해야 합니다.
- P5는 Alert API/Web에서 지원하는 기술 지표 규칙을 추가합니다. 최소 롤백 방법은 P5 PR revert입니다. 이미 만든 P5 `alert_rules` 기록은 자동으로 삭제되지 않으며, 이전 코드는 worker 로드 단계에서 unsupported `alert_type`을 skip하므로 legacy 세 가지 규칙 실행에는 영향이 없습니다. 정리가 필요하면 관리자가 확인한 뒤 해당 규칙 기록을 수동으로 삭제해야 합니다.
- P6는 Alert API/Web에서 지원하는 watchlist, portfolio holdings, portfolio account 규칙을 추가합니다. 최소 롤백 방법은 P6 PR revert이며, 새 테이블이나 마이그레이션은 없고 이미 만든 P6 `alert_rules`는 남습니다. 롤백 전에 `single_symbol`이 아닌 P6 규칙을 disable/delete하는 것을 권장합니다. 그렇지 않으면 이전 worker가 `watchlist` / `portfolio_holdings`의 상위 `target`을 종목 코드로 평가해 failed/skipped 잡음을 만들 수 있으며, portfolio 전용 `alert_type`은 worker 로드 단계에서 skip됩니다.
- P7은 Alert API/Web에서 지원하는 `market` 규칙과 시장 리뷰의 `market_light_snapshots` 이력 스냅샷을 추가합니다. 최소 롤백 방법은 P7 PR revert이며, 새 테이블이나 마이그레이션은 없고 이미 만든 P7 `alert_rules`는 남습니다. 롤백 전에 `target_scope=market` 규칙을 disable/delete하는 것을 권장합니다. 이전 worker는 unsupported `market_light_*` 유형을 skip하거나, scope/type을 인식하지 못해 설정 잡음을 만들 수 있습니다.

### 페이지 출처 안내의 시각 검증

`cd apps/dsa-web && npx playwright install chromium && npx playwright test --config playwright.fixture.config.ts`를 실행합니다. 실제 경보 페이지와 API를 가로채는 fixture를 사용하므로 백엔드나 로그인 암호가 필요 없습니다. 데이터베이스가 비어 있어도 유효한 환경 변수 설정 2건, 중복 제거 후 규칙 1건, 사용 중지 경계가 표시되는지 확인합니다. 1440px 데스크톱과 390px 좁은 화면을 모두 다루며, 가로 넘침이 없어야 합니다. 스크린샷은 `apps/dsa-web/test-results/fixtures/`에 저장되고, web-gate가 `web-ui-evidence-<head SHA>` artifact로 업로드하며 저장소에는 넣지 않습니다.
