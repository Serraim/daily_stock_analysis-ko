# 매매 전략 폴더 / Trading Strategies

이 폴더에는 **자연어로 쓴 매매 전략 파일**(YAML 형식)이 들어 있습니다. 시스템이 시작될 때 이 폴더의 `.yaml` 파일을 모두 자동으로 불러옵니다.

사용자와 문서에서는 이 기능을 계속 "전략"이라고 부릅니다. 코드, 설정, API 필드에서는 모두 `skill`이라는 이름을 씁니다. "다시 쓸 수 있는 전략 묶음"이라고 생각하면 됩니다.

## 나만의 전략(Strategy Skill) 만들기

`.yaml` 파일 하나를 만들고 매매 전략을 한국어(또는 어떤 언어든)로 적으면 됩니다. **코드는 한 줄도 쓸 필요가 없습니다.**

### 가장 간단한 템플릿

```yaml
name: my_strategy          # 고유 이름(영문, 밑줄로 연결)
display_name: 나의 전략      # 화면에 보이는 이름
description: 전략 용도를 짧게 설명

instructions: |
  전략 설명...
  판단 기준, 진입 조건, 청산 조건 등을 자연어로 적습니다.
  도구 이름(예: get_daily_history, analyze_trend)을 적어 AI가 어떤 데이터를 쓸지 알려줄 수 있습니다.
```

### 전체 템플릿

```yaml
name: my_strategy
display_name: 나의 전략
description: 이 전략이 맞는 시장 상황을 짧게 설명

# 전략 분류: trend(추세), pattern(패턴), reversal(반전), framework(프레임워크)
category: trend

# 연결된 핵심 매매 원칙 번호(1-7), 선택 사항
core_rules: [1, 2]

# 전략에 필요한 도구 목록, 선택 사항
# 쓸 수 있는 도구: get_daily_history, analyze_trend, get_realtime_quote,
#                 get_sector_rankings, search_stock_news, get_stock_info
required_tools:
  - get_daily_history
  - analyze_trend

# 선택 별칭(/ask 같은 자연어 스킬 선택에 쓰임)
aliases: [나의 매매법, 나의 모델]

# 아래 메타데이터는 기본 동작을 정합니다(선택 사항)
# default_active: 기본으로 켜지는 스킬 묶음에 넣을지
# default_router: 라우터 대체(fallback) 스킬 묶음에 넣을지
# default_priority: 기본 표시/정렬 우선순위, 숫자가 작을수록 앞에 옴
# market_regimes: 이 스킬이 우선 맞춰진 시장 상태 태그
default_active: true
default_router: false
default_priority: 100
market_regimes: [trending_up]

# 전략 상세 설명(자연어, Markdown 지원)
instructions: |
  **나의 전략 이름**

  판단 기준:

  1. **조건 1**:
     - `analyze_trend`로 이동평균선 배열을 확인합니다.
     - 보고 싶은 추세 특징을 적습니다...

  2. **조건 2**:
     - 거래량 조건을 적습니다...

  점수 조정:
  - 조건을 만족할 때 권장하는 sentiment_score 조정
  - `buy_reason`에 전략 이름을 적기
```

### 핵심 매매 원칙 참고

| 번호 | 원칙 |
|------|------|
| 1 | 엄격한 진입: 이격도 < 5%일 때만 진입 고려 |
| 2 | 추세 매매: MA5 > MA10 > MA20 정배열 |
| 3 | 효율 우선: 거래량으로 추세가 진짜인지 확인 |
| 4 | 선호 매수 지점: 이동평균선 지지까지 눌렸을 때 우선 |
| 5 | 위험 점검: 악재 뉴스가 있으면 바로 제외 |
| 6 | 거래량과 가격: 거래량으로 가격 움직임을 검증 |
| 7 | 강한 추세주 예외: 주도주는 기준을 조금 완화 가능 |

## 사용자 전략 폴더

이 폴더(기본 전략) 말고도 환경 변수로 사용자 전략 폴더를 추가로 지정할 수 있습니다:

```env
AGENT_SKILL_DIR=./my_skills
```

시스템은 기본 전략과 사용자 전략을 함께 불러옵니다. 이름이 겹치면 사용자 전략이 기본 전략을 덮어씁니다.

환경 변수 이름은 여전히 `AGENT_SKILL_DIR`입니다. 내부 이름을 통일하면서 정한 설정 이름이며, 의미상으로는 여전히 "사용자 전략 폴더"를 뜻합니다.
