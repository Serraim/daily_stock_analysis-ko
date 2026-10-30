# Grok Bot Skill 예시

2026-08-11 [Grok Bot](https://x.ai/bot)용 최소 Skill 패키지입니다. DSA에 이미 있는 REST API만 호출하며, 새 API나 환경 변수, MCP 서버를 추가하지 않습니다.

[`SKILL.md`](SKILL.md)를 Bot의 Skills 디렉터리에 복사하고 `DSA_BASE_URL`(예: `http://127.0.0.1:8000`)을 설정하세요. 그 전에 DSA를 `python main.py --serve-only` 또는 Docker로 계속 실행해 두어야 합니다.

전체 범위, DecisionSignal Routine, 인증 제약은 [Grok Bot 연동](../../grok-bot-integration.md)을 참고하세요. openclaw 사용자는 [openclaw Skill](../../openclaw-skill-integration.md)을 보면 되며, 계약(인터페이스)은 같습니다.
