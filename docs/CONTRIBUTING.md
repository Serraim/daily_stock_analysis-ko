# 기여 가이드

이 프로젝트에 관심을 가져 주셔서 감사합니다. 어떤 형태의 기여든 환영합니다.

## 🐛 버그 신고

1. 먼저 [Issues](https://github.com/ZhuLinsen/daily_stock_analysis/issues)를 검색해 이미 신고된 문제가 아닌지 확인하세요
2. Bug Report 템플릿으로 새 Issue를 만드세요
3. 재현 방법과 실행 환경 정보를 자세히 적어 주세요

## 💡 기능 제안

1. 먼저 Issues를 검색해 이미 나온 제안이 아닌지 확인하세요
2. Feature Request 템플릿으로 새 Issue를 만드세요
3. 어떤 상황에서 쓰려는지, 어떤 기능을 기대하는지 자세히 적어 주세요

## 🔧 코드 제출

### 개발 환경

```bash
# 저장소 복제
git clone https://github.com/ZhuLinsen/daily_stock_analysis.git
cd daily_stock_analysis

# 가상 환경 만들기
python -m venv venv
source venv/bin/activate  # Linux/Mac
# venv\Scripts\activate   # Windows

# 의존성 설치
pip install -r requirements.txt

# 환경 변수 설정 (Windows 명령 프롬프트에서는 copy .env.example .env)
cp .env.example .env
```

### 제출 순서

1. 이 저장소를 Fork합니다
2. 기능 브랜치를 만듭니다: `git checkout -b feature/your-feature`
3. 변경 사항을 커밋합니다: `git commit -m 'feat: add some feature'`
4. 브랜치를 push합니다: `git push origin feature/your-feature`
5. Pull Request를 만듭니다

### 커밋 규칙

[Conventional Commits](https://www.conventionalcommits.org/) 규칙을 따릅니다.

```
feat: 새 기능
fix: 버그 수정
docs: 문서 수정
style: 코드 형식 (동작에는 영향 없음)
refactor: 리팩터링
perf: 성능 개선
test: 테스트 관련
chore: 빌드/도구 관련
```

예시:
```
feat: DingTalk 봇 지원 추가
fix: 429 요청 제한 재시도 로직 수정
docs: README 배포 안내 업데이트
```

### 코드 규칙

- Python 코드는 PEP 8을 따릅니다
- 함수와 클래스에는 docstring을 붙입니다
- 중요한 로직에는 주석을 답니다
- 새 기능을 추가하면 관련 문서도 고칩니다

### CI 자동 검사

PR을 올리면 CI가 다음 검사를 자동으로 실행합니다.

일반 `docs/**`, 관리 규칙과 무관한 Markdown, `LICENSE`만 고친 경우에는 가벼운 변경 감지, 관리 규칙 검사, 결과 요약만 실행하고 백엔드 테스트 shard 3개, Docker, Web, 데스크톱 패키징은 건너뜁니다. 오프라인 테스트가 직접 읽는 계약 문서, 정적 API 명세, Markdown fixture를 고치면 여전히 백엔드 테스트가 실행됩니다. `AGENTS.md`, `.github/instructions/**`, `.claude/skills/**` 같은 관리 규칙 파일은 계속 `ai-governance`가 검사하며, 설정, 의존성, 워크플로처럼 실행에 영향을 주는 텍스트 파일은 해당하는 전체 검사를 실행합니다.

| 검사 항목 | 설명 | 반드시 통과 |
|--------|------|:--------:|
| backend-gate | `scripts/ci_gate.sh`(py_compile + flake8 심각한 오류 + 로컬 핵심 스크립트 + offline pytest) | ✅ |
| docker-build | Docker 이미지 빌드와 핵심 모듈 import smoke 테스트 | ✅ |
| web-gate | 프론트엔드를 고쳤을 때 `npm run lint` + `npm run build` 실행 | ✅(실행될 때) |
| pr-review | PR 자동 실행은 멈춰 두었고, 관리자가 `workflow_dispatch`로 PR 번호를 지정해 직접 실행할 때만 동작. GitHub API로 PR 메타데이터와 diff를 읽으며, fork PR 코드를 체크아웃하거나 실행하지 않음 | ❌(보조 항목) |
| network-smoke | 예약/수동으로 `pytest -m network` + `scripts/test.sh quick` 실행(통과하지 않아도 막지 않음) | ❌(관찰 항목) |

**로컬에서 검사 실행하기:**

```bash
# backend gate (권장)
pip install -r requirements.txt
pip install flake8 pytest
./scripts/ci_gate.sh

# 프론트엔드 gate (apps/dsa-web을 고친 경우)
cd apps/dsa-web
npm ci
npm run lint
npm run build
```

`./scripts/ci_gate.sh`는 bash 스크립트입니다. Windows에서는 Git Bash나 WSL에서 실행하세요.

## 📋 우선 기여 분야

프로젝트의 현재 핵심 기능과 주요 진입점은 [README](../README.md)를 참고하세요.

- 🔔 새 알림 채널(DingTalk, Feishu, Telegram)
- 🤖 새 AI 모델 지원(GPT-4, Claude)
- 📊 새 데이터 소스 연결
- 🐛 버그 수정과 성능 개선
- 📖 문서 보완과 번역

## ❓ 문의

궁금한 점이 있으면 언제든지:
- Issue를 만들어 논의해 주세요
- 기존 Issue와 Discussion을 확인해 주세요

기여해 주셔서 다시 한번 감사합니다! 🎉
