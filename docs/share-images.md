# 공유 이미지 템플릿과 데이터 채우기

공유 이미지는 개별 종목 분석과 시장 리뷰를 SNS에 올리기 좋은 너비 1080px의 세로로 긴 이미지로 바꿔 줍니다. 개별 종목과 시장 전체는 서로 다른 정보 구조를 쓰지만, DSA 브랜드, 저장소 표시 `ZhuLinsen/daily_stock_analysis`, 위험 고지는 함께 씁니다. GitHub 영역에는 QR 코드를 넣지 않습니다. Web과 데스크톱 앱의 공유 이미지는 기본적으로 저장소에 들어 있는 샤오훙수(小红书, 중국 SNS) QR 코드와 닉네임 `@霸天土小豆`를 보여 주며, 배포 설정에서 QR 코드와 계정 정보를 바꿀 수 있습니다.

## 실행 중 데이터가 채워지는 방식

기존 알림 흐름에서는 이미지 데이터를 손으로 조립할 필요가 없습니다.

```text
개별 종목 AnalysisResult
  -> AnalysisResult.to_dict() 구조화 JSON + 형식이 고정된 Markdown
  -> share_image가 JSON을 먼저 읽고, 없으면 Markdown으로 대체
  -> 개별 종목 결정 카드 HTML
  -> wkhtmltoimage / markdown-to-file / Playwright로 PNG 출력

시장 MarketOverview + market_light + LLM 리뷰
  -> MarketAnalyzer가 market_review_payload + 형식이 고정된 Markdown 생성
  -> share_image가 payload를 먼저 읽고, 없으면 Markdown으로 대체
  -> 시장 리뷰 카드 HTML
  -> wkhtmltoimage / markdown-to-file / Playwright로 PNG 출력
```

`MARKDOWN_TO_IMAGE_CHANNELS`, `MD2IMG_ENGINE`, `MARKDOWN_TO_IMAGE_MAX_CHARS`는 지금처럼 어떤 알림 채널을 이미지로 바꿀지, 어떤 엔진을 쓸지, 입력 최대 길이를 얼마로 할지 정합니다. 변환에 실패하면 여전히 텍스트 알림으로 대신 보냅니다.

공유 이미지를 만들려면 실행 환경에 해당 언어의 글꼴이 있어야 합니다. 공식 Docker 이미지에는 Noto CJK 글꼴이 이미 들어 있습니다. Debian/Ubuntu에서 소스 코드로 배포하면서 기본 `wkhtmltoimage` 엔진을 쓴다면 `wkhtmltopdf fonts-noto-cjk`를 설치해야 합니다. 변환 도구만 설치하고 CJK 글꼴이 없으면 PNG에서 중국어나 한국어가 사라지고 숫자, 영어, 테두리만 남을 수 있습니다.
`fonts-noto-cjk`는 Debian 글꼴 패키지 이름일 뿐이며, 일본어 보고서를 새로 지원한다는 뜻이 아닙니다. 보고서 출력은 여전히 `REPORT_LANGUAGE=zh|en|ko`만 지원합니다. 일본 주식 개별 종목과 일본 시장 리뷰에 나오는 일본어 원래 이름은 공통 Noto CJK 대체 글꼴로 표시됩니다. 화면 언어는 선택한 보고서 언어를 따르며, `7203.T`나 `region=jp`를 보고 지원하지 않는 `ja` 출력으로 바뀌지 않습니다.

샤오훙수 브랜드에는 다음 선택 설정을 씁니다. 모두 비워 두면 저장소에 들어 있는 QR 코드와 닉네임 `@霸天土小豆`를 보여 줍니다. 사용자 지정 값을 하나라도 설정하면 그 사용자 지정 브랜드 정보만 씁니다. 사용자 계정과 기본 QR 코드가 섞이지 않게 하기 위해서입니다.

```dotenv
SHARE_IMAGE_XIAOHONGSHU_URL=https://example.com/my-xiaohongshu
SHARE_IMAGE_XIAOHONGSHU_HANDLE=@我的账号
SHARE_IMAGE_XIAOHONGSHU_QR_PATH=assets/my-xiaohongshu-qr.png
```

(`@我的账号`는 "내 계정"이라는 뜻의 예시 값입니다. 실제 닉네임으로 바꿔 넣으세요.)

QR 코드 경로는 절대 경로나 프로젝트 루트 기준 상대 경로를 쓸 수 있습니다. 묶음 실행 파일로 만든 데스크톱 백엔드는 PyInstaller 리소스 폴더에서도 상대 경로를 찾습니다. 계정 URL은 `http://`나 `https://`만 받습니다. QR 코드는 이미지로 바꿀 때 Data URI로 내장해 그리므로 실행 중 네트워크가 필요 없습니다. `SHARE_IMAGE_XIAOHONGSHU_QR_PATH`를 설정하지 않으면 소스 코드와 데스크톱 패키지에 함께 들어 있는 `src/assets/share_image/xiaohongshu_qr.jpg`를 씁니다. 그래서 Web PNG와 데스크톱 Electron PNG 모두 QR 코드가 남습니다. QR 코드 아래에는 `小红书@霸天土小豆`처럼 샤오훙수 닉네임이 항상 표시됩니다. 예전 설정의 숫자 ID는 공유 이미지에 쓰이지 않습니다.

## Web에서 한 번에 공유하기

브라우저 버전의 과거 개별 종목 보고서, 시장 리뷰, 전체 보고서 서랍 오른쪽 위에는 "공유" 버튼이 있습니다. 보고서를 불러올 때는 이미지를 만들지 않습니다. 사용자가 "공유"를 눌러야 `GET /api/v1/history/{record_id}/share-image`를 호출해 PNG를 새로 만들거나 캐시된 것을 읽습니다. 파일 공유를 지원하는 브라우저에서는 이미지가 준비되면 "다시 눌러 공유"라는 안내가 나오고, 두 번째 클릭에서 시스템 공유 창을 바로 엽니다. 비동기로 이미지를 만드는 동안 브라우저의 사용자 조작 상태가 풀리는 문제를 피하기 위해서입니다. 다른 브라우저는 처음 생성이 끝나면 PNG를 바로 내려받습니다. 시스템 공유 창을 여는 데 실패하면, 사용자가 직접 취소한 경우를 빼고 이미 만들어진 PNG를 자동으로 내려받습니다.

Electron 데스크톱 앱에도 "공유" 버튼이 있지만, `wkhtmltoimage`, `markdown-to-file`, Playwright를 따로 함께 배포할 필요가 없습니다. 사용자가 누르면 데스크톱 preload가 제한된 IPC를 통해 메인 프로세스에게 로컬 `GET /api/v1/history/{record_id}/share-image-html`을 열게 합니다. 그리고 Electron에 들어 있는 숨겨진 Chromium 창으로 페이지 전체 높이를 캡처해 PNG로 만든 뒤, 브라우저와 같은 방식으로 내려받습니다. IPC는 양의 정수 기록 ID만 받습니다. 메인 프로세스는 현재 데스크톱 창이 이번 실행 때 정해진 백엔드 origin(명시적으로 설정한 내부망 `WEBUI_HOST` 포함)에만 요청하도록 허용합니다. HTML 응답은 CSP로 스크립트, 외부 리소스, 네트워크 로딩을 막습니다.

Web에서 직접 만드는 이미지는 `MARKDOWN_TO_IMAGE_CHANNELS`의 영향을 받지 않지만, 서버에 사용 가능한 `MD2IMG_ENGINE`이 설정되어 있어야 합니다. 데스크톱 앱에서 직접 만드는 이미지는 Electron을 쓰므로 `MD2IMG_ENGINE`을 읽지 않습니다. Web에서 Playwright를 쓴다면 먼저 다음을 실행하세요.

```bash
cd apps/dsa-web
npm ci
npx playwright install chromium
```

구조화 데이터는 이름, 행동, 점수, 가격, 시장 폭(상승·하락 종목 수), 업종 같은 필드를 정확하게 채우는 데 씁니다. Markdown은 예전 호출과의 호환, 그리고 계획·위험 같은 텍스트 부분을 맡습니다. 일부 과거 JSON은 실제로 들어 있는 필드만 덮어쓰며, Markdown에 이미 있는 시세, 기술 지표 참고, 실행 가격대를 지우지 않습니다. 템플릿은 점수를 보고 행동을 스스로 추론하지 않으며, 가격이나 지표를 지어내지도 않습니다. 필드가 `N/A`, `-`, 빈 값이거나 해당 모듈이 없으면 관련 카드는 자동으로 숨겨집니다.

## 개별 종목 카드 필드 대응

| 이미지 영역 | 프로젝트 필드 / 생성 출처 | 채우는 규칙 |
| --- | --- | --- |
| 종목 이름, 코드 | `AnalysisResult.name`, `AnalysisResult.code` | 구조화 필드를 바로 읽고, Markdown 제목은 대체용으로만 씁니다 |
| 행동, 점수, 추세 | `action_label` / `operation_advice`, `sentiment_score`, `trend_prediction`, `confidence_level` | 최종 보정된 결과를 씁니다. 점수 범위는 0–100이며 결론의 신뢰도를 함께 표시합니다 |
| 핵심 결론 | `dashboard.core_conclusion.one_sentence` | 없으면 숨깁니다 |
| 시장 스냅샷 | `market_snapshot` | 현재가/종가, 등락률, 거래량 비율, 회전율을 있는 필드만 보여 줍니다. 데이터 출처는 아래쪽 고지에 들어갑니다 |
| 실행 계획 | `dashboard.battle_plan.sniper_points` | 이상적/확인 매수, 손절, 첫 목표 가격만 보여 줍니다. 복잡한 발동 조건은 전체 보고서에 남깁니다 |
| 기술 지표 참고 | `dashboard.data_perspective` | 이동평균선 상태, 추세 점수, MA5 이격도, 지지선과 저항선을 보여 줍니다. 구조화된 거래량 비율/회전율이 이미 스냅샷에 있으면 긴 거래량 설명은 반복하지 않습니다. 구조화된 거래량 데이터가 없는 예전 기록은 Markdown 내용을 그대로 둡니다 |
| 다음 관찰 포인트 | `dashboard.phase_decision` | 행동 시점, 다음 점검 시각, 관찰 조건을 최대 두 개 보여 줍니다 |
| 호재와 위험 | `dashboard.intelligence` | `positive_catalysts`와 `risk_alerts`를 각각 최대 2개의 짧은 요약으로 보여 줍니다 |
| 보유 여부별 조언 | `core_conclusion.position_advice` | 미보유와 보유만 구분합니다. 비중, 진입, 위험 관리에 관한 긴 글은 전체 보고서에 남깁니다 |

템플릿은 프로젝트가 지금 지원하는 중국어, 영어, 한국어 보고서 라벨을 지원합니다. 포스터 항목, 지표 라벨, 아래쪽 고지는 보고서 언어를 따릅니다. "결정 대시보드"에 종목이 하나뿐이면 자동으로 개별 종목 카드를 씁니다. 여러 종목이 들어 있으면 여러 종목용 보고서 배치를 유지해, 첫 번째 종목을 보고서 전체로 잘못 다루지 않습니다. `强烈买入`(적극 매수), `Strong Buy` 같은 복합 행동은 행동 라벨 전체를 그대로 둡니다.

## 시장 카드 필드 대응

| 이미지 영역 | 프로젝트 필드 / 생성 출처 | 채우는 규칙 |
| --- | --- | --- |
| 날짜, 시장 범위 | `MarketOverview.date`, 리뷰 대상 지역 | A주/미국/홍콩/일본/한국 시장 리뷰 제목을 만듭니다. 여러 시장 보고서는 구간별로 `market_review_payload.markets`와 맞춥니다 |
| 시장 신호 | `market_light.score`, `temperature_label`, `label`, `guidance` | 정해진 규칙으로 계산한 시장 신호등 결과를 쓰며, 템플릿이 다시 점수를 매기지 않습니다 |
| 지수 흐름 | `MarketOverview.indices`, `color_scheme` | 주요 지수를 최대 4개까지 최신 값과 등락률로 보여 줍니다. 구조화 payload는 생성 당시의 `green_up` / `red_up` 색상 의미를 저장해 둡니다 |
| 시장 폭 | `up_count`, `down_count`, `limit_up_count`, `limit_down_count`, `total_amount` | 데이터 소스가 지원하고 보고서에 구조화 데이터가 있을 때만 보여 줍니다 (`limit_up`/`limit_down`은 상한가·하한가 종목 수입니다) |
| 신호 세부 항목 | `market_light.dimensions` | `available != false`인 확정 점수만 보여 줍니다. 지원하지 않는 항목의 자리 채움 점수 50을 실제 데이터처럼 다루지 않습니다 |
| 강세·약세 업종 | `sectors.top`, `sectors.bottom` | 상승 선두와 하락 선두를 각각 상위 3개씩 보여 줍니다. 업종 순위가 없는 시장에서는 자동으로 숨깁니다 |
| 자금 흐름 관찰 | 리뷰의 "자금과 심리" 부분 | 상승·하락 종목 비율, 거래대금 증가, 자금 성향을 뽑아냅니다. 거래대금이나 뉴스에서 추측한 내용을 순유입처럼 꾸미지 않습니다 |
| 주요 관찰 대상 | 리뷰 "내일 매매 계획"의 관심/회피 방향 | 업종이나 테마를 각각 최대 2개 보여 줍니다. 현재 payload에는 `leader_stocks`가 없으므로 주요 종목을 지어내지 않습니다 |
| 내일 전략 | 리뷰 "내일 매매 계획" 부분 | 결론, 비중 범위, 무효화 조건을 보여 주며 주요 관찰 대상과 겹치지 않게 합니다 |
| 위험 안내 | 리뷰 "위험 안내" 부분 | 최대 2개까지 보여 주며 중복된 면책 문구는 걸러 냅니다 |

## 직접 채우기 또는 로컬 미리보기

템플릿은 여전히 프로젝트가 만든 Markdown을 받습니다. 새 흐름에서는 `AnalysisResult.to_dict()`나 `market_review_payload`를 추가로 넘깁니다. 호환용 대체 경로만 디버깅할 때는 최소한의 개별 종목 보고서를 준비하면 됩니다.

아래 예시는 프로그램이 읽어 들이는 중국어 보고서 형식 그대로입니다(마오타이(贵州茅台, 600519) 예시). 제목과 표 라벨(`核心结论` 핵심 결론, `作战计划` 매매 계획, `理想买入点` 이상적 매수 가격, `止损位` 손절 가격, `目标位` 목표 가격 등)을 바꾸지 말고 그대로 쓰세요.

```markdown
## 🟢 贵州茅台 (600519)

> 2026-07-31 15:00 | 评分: **72** | 看多

### 📌 核心结论

**买入**: 趋势偏强，等待回踩支撑后分批执行。

| 持仓情况 | 操作建议 |
| --- | --- |
| 空仓者 | 等待回踩确认，不追高。 |
| 持仓者 | 继续持有，跌破止损位退出。 |

### 🎯 作战计划

| 点位类型 | 价格 |
| --- | --- |
| 理想买入点 | 1420-1450 |
| 次优买入点 | 1380-1400 |
| 止损位 | 1350 |
| 目标位 | 1580 |
```

HTML 미리보기 만들기:

```python
from pathlib import Path
from src.share_image import ShareImageBranding, build_share_image_html

markdown_text = Path("reports/example.md").read_text(encoding="utf-8")
branding = ShareImageBranding(
    xiaohongshu_url="https://example.com/my-xiaohongshu",
    xiaohongshu_handle="@我的账号",
    xiaohongshu_qr_path="assets/my-xiaohongshu-qr.png",
)
html = build_share_image_html(markdown_text, branding=branding)
Path("share-preview.html").write_text(html, encoding="utf-8")
```

실제 실행 데이터로 미리 보려면 구조화 결과를 넘깁니다.

```python
html = build_share_image_html(
    markdown_text,
    structured_payload=analysis_result.to_dict(),
)
```

실제 알림을 PNG로 바꿀 때는 여전히 다음을 호출합니다.

```python
from src.md2img import markdown_to_image

png_bytes = markdown_to_image(
    markdown_text,
    structured_payload=analysis_result.to_dict(),
)
```

시장 보고서는 `MarketAnalyzer`가 만드는 "시장 신호, 지수 구조, 업종 주도 흐름, 뉴스 촉매, 내일 매매 계획, 위험 안내" 부분을 그대로 쓰는 것이 좋습니다. 외부에서 필드 이름을 따로 만들면 템플릿이 해당 필드가 없는 것으로 처리합니다.

## 디자인과 내용의 경계

- 상승·하락 색상은 구조화 payload에 저장된 `color_scheme`을 먼저 씁니다. 예전 기록은 최종 보고서의 색상 표시에서 되살립니다. 템플릿은 시장 지역에 따라 상승·하락 색을 고정해 두지 않습니다(중국 시장은 빨간색이 상승, 초록색이 하락인 경우가 많습니다).
- 공유 이미지의 매수, 손절, 목표는 한눈에 보이는 가격이나 "안정될 때까지 대기" 정도만 남깁니다. 전체 조건은 항상 원래 보고서에 남아 있습니다.
- 실제 가격 데이터가 없으면 가짜 캔들 차트를 그리지 않습니다. 위쪽에는 데이터와 상관없는 브랜드 장식 효과만 둡니다.
- 샤오훙수 URL, 닉네임, QR 코드 경로는 실행 설정으로 덮어쓸 수 있습니다. QR 코드 아래에는 닉네임만 표시하고 숫자 ID는 표시하지 않습니다. 모두 비워 두면 내장 닉네임 `@霸天土小豆`와 저장소에 들어 있는 QR 코드를 씁니다. GitHub에는 저장소 표시 `ZhuLinsen/daily_stock_analysis`를 항상 보여 주며 QR 코드는 만들지 않습니다.
- 시장 보고서에서 핵심 모듈을 제대로 뽑아냈다면 전체 Markdown을 다시 붙이지 않습니다. 추가 상세 내용은 원래 보고서에 남기고, 공유 이미지에는 구조화된 요약만 보여 줍니다.
- 이미지 아래쪽에는 "AI가 생성한 내용이며 연구·교류용일 뿐, 투자 권유가 아닙니다"라는 안내가 항상 들어갑니다(보고서 언어에 맞게 표시됩니다).
