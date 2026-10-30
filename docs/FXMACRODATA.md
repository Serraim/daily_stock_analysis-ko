# FXMacroData 거시경제 데이터 도구

주식 분석 Agent와 채팅 Agent의 도구 목록에 FXMacroData가 연결되어 있습니다. USD 데이터 카탈로그, 최근 90일 지표 이력, 발표 일정은 키, 계정, 신용카드 없이 무료로 사용할 수 있습니다.

선택 사항인 유료 인증 데이터가 필요하면 애플리케이션을 실행하는 환경에 `FXMACRODATA_API_KEY`를 설정합니다. GitHub Actions로 예약 분석을 돌리는 경우에는 저장소 Secret `FXMACRODATA_API_KEY`로 저장하면 `00-daily-analysis.yml`이 이 값을 분석 단계의 환경 변수로 넘겨 줍니다. 키는 도구 인자, 모델 컨텍스트, 응답 어디에도 들어가지 않습니다. Agent 모드를 켜면 `fxmacrodata_data_catalogue`(`currency=USD`), `fxmacrodata_indicator_history`(`currency=USD, indicator=policy_rate`), `fxmacrodata_release_calendar`를 조회할 수 있습니다.

멀티 Agent 모드에서는 정보(Intel) Agent의 기본 도구 허용 목록이 고정된 클라이언트 v0.1.0 스냅샷의 작업 72개를 모두 제공하고, 리스크 Agent와 포트폴리오 Agent는 발표, 거시경제, 시장 간 리스크와 관련된 작업만 제공합니다. 각 전문 Agent의 기존 도구 접근 제한은 그대로 적용됩니다. Codex App Server 채팅 백엔드는 제거되었으며, FXMacroData는 기본 채팅 백엔드와 리포트 Agent를 통해 계속 사용합니다.

이 연동은 공개 API의 원본 데이터, 발표 시각, 출처, 추정 시각 표시를 그대로 유지합니다. `records`는 화면 표시용으로 덧붙인 보조 뷰입니다. 시장 컨센서스, 공식 전망, FXMacroData가 생성한 예측은 서로 구분해서 다룹니다. 데이터를 가져올 수 없으면 상태를 명확히 반환하며, 임의로 만든 데이터를 채워 넣지 않습니다.

고정 클라이언트 v0.1.0 내장 스냅샷에 들어 있는 REST 작업 23개와 MCP 도구 49개의 작업 표, 매개변수, 설치 및 테스트 방법은 [영문 가이드](FXMACRODATA_EN.md)를 참고하십시오. 두 문서는 같은 기능을 설명하며, 전체 작업 이름은 영어 그대로 둡니다.

[FXMacroData](https://fxmacrodata.com/?utm_source=github&utm_medium=referral&utm_campaign=open_source_integrations&utm_content=daily_stock_analysis_readme) · [API 문서](https://fxmacrodata.com/documentation/reference?utm_source=github&utm_medium=referral&utm_campaign=open_source_integrations&utm_content=daily_stock_analysis_docs)
