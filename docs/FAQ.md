# ❓ 자주 묻는 질문 (FAQ)

이 문서는 사용하면서 자주 겪는 문제와 해결 방법을 모은 것입니다.

---

## 📊 데이터 관련

### Q1: 미국 주식 코드(AMD, AAPL 등)를 분석하면 가격이 이상하게 나와요

**증상**: 미국 주식 코드를 입력했는데 가격이 분명히 틀리거나(예: AMD가 7.33위안으로 표시), A주(중국 본토 주식)로 잘못 인식됩니다.

**원인**: 초기 버전의 코드 매칭 로직이 중국 A주 규칙을 먼저 시도해 코드가 충돌했습니다.

**해결 방법**:
1. v2.3.0에서 고쳐졌으며, 이제 미국 주식 코드를 자동으로 인식합니다
2. 그래도 문제가 있으면 `.env`에 다음을 설정하세요.
   ```bash
   YFINANCE_PRIORITY=0
   ```
   그러면 미국 주식 데이터는 Yahoo Finance 데이터 소스를 우선 씁니다

> 📌 관련 Issue: [#153](https://github.com/ZhuLinsen/daily_stock_analysis/issues/153)

---

### Q2: 리포트의 "量比"(거래량 비율) 필드가 비어 있거나 N/A로 나와요

**증상**: 분석 리포트에 거래량 비율 데이터가 없어, AI가 거래량 증감을 판단하기 어렵습니다.

**원인**: 기본 실시간 시세 소스 가운데 일부(예: Sina API)는 거래량 비율 필드를 제공하지 않습니다.

**해결 방법**:
1. v2.3.0에서 고쳐졌으며, 이제 Tencent API에서 거래량 비율을 읽어 옵니다
2. 실시간 시세 소스 우선순위를 다음처럼 설정하는 것을 권장합니다.
   ```bash
   REALTIME_SOURCE_PRIORITY=tencent,akshare_sina,efinance,akshare_em
   ```
3. 시스템에는 5일 평균 거래량 계산이 대체 로직으로 들어 있습니다

> 📌 관련 Issue: [#155](https://github.com/ZhuLinsen/daily_stock_analysis/issues/155)

---

### Q3: Tushare 데이터 수집이 실패하고 Token이 틀렸다고 나와요

**증상**: 로그에 `Tushare 获取数据失败: 您的token不对，请确认`(Tushare 데이터 수집 실패: token이 올바르지 않으니 확인하세요)가 나옵니다.

**해결 방법**:
1. **Tushare 계정이 없다면**: `TUSHARE_TOKEN`을 설정할 필요가 없습니다. 시스템이 무료 데이터 소스(AkShare, Efinance)를 자동으로 씁니다
2. **Tushare 계정이 있다면**: Token이 맞는지 [Tushare Pro](https://tushare.pro/weborder/#/login?reg=834638 ) 개인 센터에서 확인하세요
3. 이 프로젝트의 핵심 기능은 모두 Tushare 없이도 정상적으로 동작합니다

---

### Q4: 데이터 수집이 요청 제한에 걸리거나 빈 값이 돌아와요

**증상**: 로그에 `熔断器触发`(차단기 작동)가 나오거나 데이터가 `None`으로 돌아오며, `RemoteDisconnected`, `push2his.eastmoney.com` 연결 끊김 등이 나타납니다.

**원인**: 무료 데이터 소스(둥팡차이푸(East Money), Sina 등)에는 크롤링 방지 장치가 있어, 짧은 시간에 요청이 많으면 제한에 걸립니다.

**해결 방법**:
1. 시스템에는 여러 데이터 소스 자동 전환과 차단기 보호가 들어 있습니다
2. 관심 종목 수를 줄이거나 요청 간격을 늘립니다
3. 분석을 너무 자주 직접 실행하지 않습니다
4. 둥팡차이푸 API가 자주 실패하면 `ENABLE_EASTMONEY_PATCH=true`로 둥팡차이푸 패치를 켤 수 있습니다(NID 토큰과 무작위 User-Agent를 넣어 제한에 걸릴 확률을 낮춤)
5. `MAX_WORKERS=1`로 바꿔 순서대로 가져오면 둥팡차이푸에 대한 동시 요청 부담이 줄어듭니다

---

## ⚙️ 설정 관련

### Q5: GitHub Actions 실행이 실패하고 환경 변수를 찾을 수 없다고 나와요

**증상**: Actions 로그에 `GEMINI_API_KEY`나 `STOCK_LIST`가 정의되지 않았다고 나옵니다.

**원인**: GitHub는 `Secrets`(암호화)와 `Variables`(일반 변수)를 구분하므로, 잘못된 곳에 넣으면 읽지 못합니다.

**해결 방법**:
1. 저장소의 `Settings` → `Secrets and variables` → `Actions`로 들어갑니다
2. **Secrets**(`New repository secret` 클릭): 민감한 정보를 넣습니다
   - `GEMINI_API_KEY`
   - `OPENAI_API_KEY`
   - `TELEGRAM_BOT_TOKEN`
   - 각종 Webhook URL
3. **Variables**(`Variables` 탭 클릭): 민감하지 않은 설정을 넣습니다
   - `STOCK_LIST`
   - `GEMINI_MODEL`
   - `REPORT_TYPE`

> 호환 안내: 일일 분석 workflow는 `STOCK_LIST`라는 이름의 Environment에도 연결되어 있어서, 실수로 `STOCK_LIST`를 그 Environment variables에 넣어도 읽힙니다. 그래도 권장 위치는 Repository variables입니다. 일일 작업이 사람의 승인을 기다리게 하려는 것이 아니라면, 이 Environment에 required reviewers, wait timer, 배포 브랜치 제한을 설정하지 마세요.

---

### Q6: .env 파일을 고쳤는데 설정이 적용되지 않아요

**해결 방법**:
1. `.env` 파일이 프로젝트 루트 디렉터리에 있는지 확인합니다
2. **Docker 배포 / WebUI 시스템 설정**:
   - `--env-file .env` / Compose `env_file`은 호스트의 `.env`를 시작 시 환경 변수로 컨테이너에 넣을 뿐, 컨테이너 안의 `/app/.env`를 자동으로 만들거나 되쓰지 않습니다
   - WebUI 설정 페이지는 현재 사용 중인 `.env` 파일에 일부 키가 없으면 시작 시 주입된 같은 이름의 환경 변수를 대신 보여 줍니다. 하지만 "`.env` 내보내기"는 여전히 현재 사용 중인 설정 파일의 내용만 내보냅니다
   - WebUI에서 저장한 `STOCK_LIST`, `SCHEDULE_ENABLED`, `SCHEDULE_TIME`, `SCHEDULE_TIMES`, `SCHEDULE_RUN_IMMEDIATELY`, `RUN_IMMEDIATELY`는 컨테이너 안의 `.env`에 다시 기록됩니다
   - WebUI에서 저장하면 현재 프로세스의 설정을 다시 불러옵니다. 실행 중인 읽기 경로는 방금 기록된 `.env`를 바로 씁니다. 예를 들어 예약 실행은 저장된 `STOCK_LIST`를 계속 새로 읽습니다
   - 컨테이너 시작 명령에 같은 이름의 환경 변수를 넘겼다면(`--env-file .env`, `docker run -e ...`, Compose `environment:` 등), 다음에 다시 시작할 때 시작 환경 변수가 우선할 수 있습니다. WebUI에서 저장한 값을 쓰려면 같은 이름의 override를 함께 고치거나 지우세요
   - WebUI에서 저장한 설정을 계속 유지하려면 `ENV_FILE`을 `/app/data/runtime.env`처럼 쓰기 가능한 데이터 볼륨의 파일로 지정하세요. 호스트의 `.env` 파일 하나를 `/app/.env`에 마운트하지 마세요
   - `SCHEDULE_ENABLED`, `SCHEDULE_TIME`, `SCHEDULE_TIMES`를 저장하면 WebUI/API/Desktop처럼 오래 실행되는 프로세스가 새 설정에 따라 runtime scheduler를 켜고 끄거나 다시 만듭니다. `--serve-only`나 Desktop 프로세스를 다시 시작하면 켜져 있던 daily jobs를 복구하지만, 시작할 때 바로 분석을 실행하지는 않습니다
   - `SCHEDULE_RUN_IMMEDIATELY`와 `RUN_IMMEDIATELY`는 여전히 시작 시점/일회성 실행 설정이므로, 저장해도 바로 분석이 한 번 실행되지는 않습니다
   - `SCHEDULE_STARTUP_DEDUP`는 순수 CLI 예약 모드에서 시작 즉시 실행할 때 같은 날 중복을 막는 설정입니다(그날 이미 전체 분석이 성공했으면 시작 시 보충 실행을 건너뜀. 자세한 내용은 `docs/full-guide.md` 설정 표 참고). 이것도 시작 시점 설정입니다
3. **Docker에서 `.env`를 직접 고쳤다면**: 고친 뒤 컨테이너를 다시 시작하는 것을 권장합니다
   ```bash
   docker-compose down && docker-compose up -d
   ```
4. **GitHub Actions**: `.env` 파일은 적용되지 않으므로 반드시 Secrets/Variables에 설정해야 합니다
5. `.env` 파일이 여러 개(`.env.local` 등) 있어서 서로 덮어쓰고 있지 않은지 확인합니다

---

### Q7: Gemini/OpenAI API에 프록시로 접속하려면 어떻게 하나요?

**해결 방법**:

`.env`에 다음을 설정합니다.
```bash
USE_PROXY=true
PROXY_HOST=127.0.0.1
PROXY_PORT=10809
```

> ⚠️ 주의: 프록시 설정은 로컬 실행에만 적용됩니다. GitHub Actions 환경에서는 프록시를 설정할 필요가 없습니다.

---

### LLM 설정 자주 묻는 질문

> 자세한 설명은 [LLM 설정 가이드](LLM_CONFIG_GUIDE.md)를 보세요.

**Q: GEMINI_API_KEY와 LLM_CHANNELS를 둘 다 설정했는데 왜 채널만 쓰나요?**

시스템은 우선순위에 따라 한 가지만 씁니다: 고급 모델 라우팅 YAML(`LITELLM_CONFIG`) > `LLM_CHANNELS` > legacy keys. 단, YAML은 파일을 정상적으로 해석할 수 있고 유효한 `model_list`가 나올 때만 적용됩니다. YAML 경로가 잘못되었거나 내용이 비어 있으면 자동으로 `LLM_CHANNELS`나 legacy keys로 넘어갑니다. 어느 한 단계가 실제로 적용되면, 그보다 우선순위가 낮은 설정은 해석에 쓰이지 않습니다.

**Q: check_env가 "未配置可用 AI 模型"(쓸 수 있는 AI 모델이 설정되지 않음)이라고 출력해요**

먼저 서비스 제공자 하나를 골라 해당 API Key를 넣으세요. 기본 모델을 고정하려면 `LITELLM_MODEL=provider/model`을 추가하고, 여러 모델을 바꿔 쓰려면 `LLM_CHANNELS`나 고급 모델 라우팅 YAML을 설정합니다. `python scripts/check_env.py --config`로 설정을 검증하고, `python scripts/check_env.py --llm`으로 실제 API를 호출해 테스트합니다.

**Q: 여러 모델(AIHubmix + DeepSeek + Gemini 등)을 함께 쓰려면 어떻게 하나요?**

채널 모드를 씁니다. `LLM_CHANNELS=aihubmix,deepseek,gemini`로 설정하고, 채널마다 `LLM_{NAME}_BASE_URL`, `LLM_{NAME}_API_KEY`, `LLM_{NAME}_MODELS`를 설정합니다. 웹 설정 페이지 → AI 모델 → AI 모델 연결에서 화면으로 설정할 수도 있습니다.

**Q: 종목 질문(问股)/Agent에서 쓸 수 있는 LLM이 없다고 나오는데, 저는 예전 `GEMINI_*` / `OPENAI_*` / `ANTHROPIC_*` 설정만 있어요**

먼저 `LITELLM_CONFIG`나 `LLM_CHANNELS`를 켜 두었는지 확인하세요. 켜져 있다면 위 단계 설정이 legacy keys를 덮어씁니다. 두 단계 모두 켜지 않았고 `AGENT_LITELLM_MODEL`이 비어 있다면, 종목 질문 Agent는 legacy provider 모델을 자동으로 이어받습니다. `GEMINI_MODEL`, `OPENAI_MODEL`, `ANTHROPIC_MODEL`이 각각 해당 provider 접두사가 붙은 LiteLLM 모델 이름으로 대응됩니다. 이번 수정은 예전 설정을 몰래 옮기거나 지우지 않으며, "실제로 무엇이 빠졌는지"를 프런트엔드에 그대로 돌려줘서 key가 없는지, 모델 이름이 없는지, 위 단계 설정에 덮였는지 판단할 수 있게 합니다. 전체 호환 의미는 [LLM 설정 가이드](LLM_CONFIG_GUIDE.md)의 "问股 Agent / LiteLLM 配置兼容说明"(종목 질문 Agent / LiteLLM 설정 호환 안내)을 보세요.

---

## 📱 알림 관련

### Q8: 봇 알림이 실패하고 메시지가 너무 길다고 나와요

**증상**: 분석은 성공했는데 알림을 받지 못하고, 로그에 400 오류나 `Message too long`이 나옵니다.

**원인**: 플랫폼마다 메시지 길이 제한이 다릅니다.
- WeCom(기업용 위챗): 4KB
- Feishu(페이슈): 20KB
- DingTalk(딩톡): 20KB

**해결 방법**:
1. **자동 분할**: 최신 버전은 긴 메시지를 자동으로 나눠 보냅니다
2. **종목별 알림 모드**: `SINGLE_STOCK_NOTIFY=true`로 설정하면 종목 하나를 분석할 때마다 바로 알림을 보냅니다
3. **간단한 리포트**: `REPORT_TYPE=simple`로 간단한 형식을 씁니다
4. **로컬 리포트만 저장**: 알림 채널을 하나도 설정하지 않아도 `SINGLE_STOCK_NOTIFY=true`이면 종목별 리포트를 `reports/report_YYYYMMDD_<종목 코드>.md`에 저장합니다

---

### Q8.1: 분석은 끝났는데 `reports/`에 리포트 파일이 없어요

**흔한 원인**:
1. `STOCK_LIST`가 비어 있고, 이번 실행에서 시장 복기도 켜지 않았습니다
2. 종목 목록은 있지만 개별 종목 분석이 모두 실패해 성공한 결과가 없습니다
3. 개별 종목 결과는 만들어졌지만 `reports/`에 쓰다가 실패했습니다(디렉터리 권한이나 마운트 문제 등)

**현재 동작**:
1. CLI로 분석을 시작하면 위 상황마다 실패 원인을 분명히 기록합니다
2. `--serve`가 아닌 단독 실행 모드는 0이 아닌 종료 코드를 돌려줘, workflow가 "리포트 없음"을 성공으로 잘못 판단하지 않게 합니다
3. 종목별 알림 모드인데 알림을 설정하지 않았다면, 문제 확인용으로 로컬 Markdown 리포트는 계속 저장합니다

### Q9: Telegram 알림이 오지 않아요

**해결 방법**:
1. `TELEGRAM_BOT_TOKEN`과 `TELEGRAM_CHAT_ID`를 모두 설정했는지 확인합니다
2. Chat ID 얻는 방법:
   - Bot에게 아무 메시지나 보냅니다
   - `https://api.telegram.org/bot<TOKEN>/getUpdates`에 접속합니다
   - 돌아온 JSON에서 `chat.id`를 찾습니다
3. (그룹 대화라면) Bot이 대상 그룹에 추가되어 있는지 확인합니다
4. 로컬에서 실행한다면 Telegram API에 접속할 수 있어야 합니다(프록시가 필요할 수 있음)

---

### Q10: WeCom(기업용 위챗)에서 Markdown 형식이 제대로 안 보여요

**해결 방법**:
1. WeCom은 Markdown 지원이 제한적이므로 다음 설정을 시도해 보세요.
   ```bash
   WECHAT_MSG_TYPE=text
   ```
2. 그러면 일반 텍스트 형식으로 메시지를 보냅니다

---

## 🤖 AI 모델 관련

### Q11: Gemini API가 429 오류(요청 과다)를 돌려줘요

**증상**: 로그에 `Resource has been exhausted`나 `429 Too Many Requests`가 나옵니다.

**해결 방법**:
1. Gemini 무료 버전에는 속도 제한이 있습니다(약 15 RPM)
2. 동시에 분석하는 종목 수를 줄입니다
3. 요청 지연을 늘립니다.
   ```bash
   GEMINI_REQUEST_DELAY=5
   ANALYSIS_DELAY=10
   ```
4. 또는 OpenAI 호환 API를 대안으로 씁니다

---

### Q12: DeepSeek 같은 중국 모델은 어떻게 쓰나요?

**설정 방법**:

```bash
# GEMINI_API_KEY는 설정하지 않아도 됩니다
OPENAI_API_KEY=sk-xxxxxxxx
OPENAI_BASE_URL=https://api.deepseek.com
OPENAI_MODEL=deepseek-v4-flash
# deepseek-chat / deepseek-reasoner도 여전히 쓸 수 있지만, 공식적으로 2026/07/24 이후 지원 중단 예정입니다
```

지원하는 모델 서비스:
- DeepSeek: `https://api.deepseek.com`
- 통이첸원(Qwen): `https://dashscope.aliyuncs.com/compatible-mode/v1`
- Moonshot: `https://api.moonshot.cn/v1`

---

### Q12b: Ollama 로컬 모델은 어떻게 쓰나요?

**설정 방법**: `OLLAMA_API_BASE` + `LITELLM_MODEL`을 쓰거나, 채널 모드(`LLM_CHANNELS=ollama` + `LLM_OLLAMA_BASE_URL` + `LLM_OLLAMA_MODELS`)를 씁니다.

**주의할 점**: `OPENAI_BASE_URL`로 Ollama를 설정하지 마세요. 그러면 시스템이 URL을 잘못 이어 붙입니다(404, `api/generate/api/show` 등). 자세한 내용은 [LLM 설정 가이드](LLM_CONFIG_GUIDE.md)의 예시 4와 채널 예시를 보세요.

---

### Q12c: 실행 중 `OllamaException / APIConnectionError`(All LLM models failed)가 나와요

**증상**: 로그에 `litellm.APIConnectionError: OllamaException`이나 `Analysis failed: All LLM models failed (tried 1 model(s))`가 나옵니다.

다음 5가지를 차례로 확인하세요.

1. **Ollama 서비스가 실행 중인지**
   ```bash
   # 프로세스 확인
   pgrep -a ollama
   # 출력이 없으면 먼저 실행
   ollama serve
   ```
   서비스가 수신 중인지 확인합니다: `curl http://localhost:11434`를 실행하면 `Ollama is running`이 나와야 합니다. (Windows에서는 Ollama 앱이 실행 중인지 작업 표시줄에서 확인하고, PowerShell에서 `curl.exe http://localhost:11434`로 확인할 수 있습니다.)

2. **`OLLAMA_API_BASE`를 제대로 설정했는지**
   - ✅ 올바름: `OLLAMA_API_BASE=http://localhost:11434`
   - ❌ 잘못됨: Ollama 주소를 `OPENAI_BASE_URL`에 넣으면 URL 경로가 잘못 이어집니다(예: `…/api/generate/api/show`).

3. **모델 이름에 `ollama/` 접두사를 붙였는지**
   - ✅ 올바름: `LITELLM_MODEL=ollama/qwen3:8b`
   - ❌ 잘못됨: `LITELLM_MODEL=qwen3:8b`(접두사가 없으면 litellm이 Ollama로 라우팅하지 못함)

4. **모델을 로컬에 내려받았는지**
   ```bash
   ollama list          # 가지고 있는 모델 확인
   ollama pull qwen3:8b # 없으면 먼저 내려받기
   ```

5. **원격 배포 / Docker일 때의 네트워크와 방화벽**
   - Ollama와 프로그램이 같은 컴퓨터에 있지 않다면 `OLLAMA_API_BASE`를 실제 IP로 바꿔야 합니다. 예: `http://192.168.1.100:11434`.
   - 방화벽에서 11434 포트를 열었는지, Ollama가 올바른 주소로 시작했는지(`OLLAMA_HOST=0.0.0.0:11434`) 확인합니다.

> 전체 설정 예시는 [LLM 설정 가이드 → 예시 4(Ollama)](LLM_CONFIG_GUIDE.md#示例-4使用-ollama-本地模型)를 보세요.

---

## 🐳 Docker 관련

### Q13: Docker 컨테이너가 시작하자마자 종료돼요

**해결 방법**:
1. 컨테이너 로그를 확인합니다.
   ```bash
   docker logs <container_id>
   ```
2. 흔한 원인:
   - 환경 변수를 제대로 설정하지 않음
   - `.env` 파일 형식 오류(불필요한 공백 등)
   - 의존성 패키지 버전 충돌

---

### Q14: Docker에서 API 서비스에 접속할 수 없어요

**해결 방법**:
1. 시작 명령에 `--host 0.0.0.0`이 들어 있는지 확인합니다(127.0.0.1이면 안 됨)
2. 포트 매핑이 맞는지 확인합니다.
   ```yaml
   ports:
     - "8000:8000"
   ```

---

### Q14.1: Docker에서 네트워크/DNS 해석이 실패해요(api.tushare.pro, searchapi.eastmoney.com 등을 찾지 못함)

**증상**: 로그에 `Temporary failure in name resolution`이나 `NameResolutionError`가 나오고, 주식 데이터 API와 LLM API 모두 접속하지 못합니다.

**원인**: 사용자 정의 bridge 네트워크에서는 컨테이너가 Docker 내장 DNS를 쓰는데, 보조 라우터나 특수한 네트워크 환경에서는 해석에 실패할 수 있습니다.

**해결 방법**(위에서부터 차례로 시도):

1. **DNS를 명시적으로 설정**: `docker/docker-compose.yml`의 `x-common` 아래에 다음을 추가합니다.
   ```yaml
   dns:
     - 223.5.5.5
     - 119.29.29.29
     - 8.8.8.8
   ```
   그런 다음 `docker-compose down`과 `docker-compose up -d --force-recreate`를 실행해 컨테이너를 다시 만듭니다. (예시의 `223.5.5.5`, `119.29.29.29`는 중국 공개 DNS이므로, 한국에서는 `8.8.8.8`, `1.1.1.1` 같은 DNS를 써도 됩니다.)

2. **host 네트워크 모드로 바꾸기**: 위 방법으로도 안 되면 `server` 서비스 아래에 `network_mode: host`를 추가하고 `ports` 매핑을 지웁니다. host 모드에서는 `ports`가 적용되지 않으며, **포트는 `command`의 `--port`로 정합니다**. 호스트의 기본 포트가 이미 쓰이고 있다면 다른 포트로 바꿀 수 있습니다(예: `.env`에 `API_PORT=8080`을 설정하고 `http://localhost:8080`으로 접속).

> 📌 관련 Issue: [#372](https://github.com/ZhuLinsen/daily_stock_analysis/issues/372)

---

### Q14.2: Docker로 설치했을 때 소프트웨어 버전은 어느 파일에 적혀 있나요?

**결론**: Docker 사용자에게 **가장 확실한 버전은 Python 소스 파일의 상수가 아니라, 실제로 쓰고 있는 이미지 tag**입니다.

**이유**:
1. 저장소의 Docker 배포는 `.github/workflows/docker-publish.yml`이 실행하며, `v*.*.*` 형식의 Git tag(예: `v3.12.0`)를 push할 때만 해당 배포 이미지가 만들어집니다.
2. 즉 Docker 이미지 버전은 근본적으로 **GitHub Release / Git tag**를 따르며, `main.py`, `server.py` 같은 백엔드 소스에 고정되어 있지 않습니다.
3. `apps/dsa-web/package.json`의 `version`은 현재 자리 표시 값 `0.0.0`입니다. WebUI의 "버전 정보" 카드는 정적 리소스가 다시 빌드되었는지 확인하는 데 알맞으며, Docker 배포 버전으로 보면 안 됩니다.
4. 데스크톱 앱 버전은 따로 관리하며 `apps/dsa-desktop/package.json`의 `version` 필드에 있습니다. 이는 Electron 데스크톱 앱 버전일 뿐 Docker 이미지 버전이 아닙니다.

**현재 Docker 버전 확인 방법**:
1. **먼저 배포 명령이나 Compose 파일의 이미지 tag를 봅니다**: 예를 들어 `ghcr.io/zhulinsen/daily_stock_analysis:v3.12.0`이라면 `v3.12.0`이 현재 배포 버전입니다.
2. **`latest`를 받았다면**: 당시의 `docker pull` / `docker-compose.yml` / 배포 스크립트를 다시 보거나, [GitHub Releases](https://github.com/ZhuLinsen/daily_stock_analysis/releases)와 대조해 해당 배포 기록을 확인하세요.
3. **프런트엔드가 새 빌드로 바뀌었는지만 확인하려면**: WebUI의 "시스템 설정" 페이지에서 `构建标识`(빌드 식별자) / `构建时间`(빌드 시각)을 보세요. 정적 리소스가 새로 고쳐졌는지 확인하는 데는 도움이 되지만 Docker 이미지 배포 버전과 같지는 않습니다.

**권장**: 불필요한 업데이트를 피하려면 배포할 때 가능한 한 명확한 버전 tag(예: `v3.12.0`)를 고정해서 쓰고, `latest`에 오래 의존하지 마세요.

---

## 🖥️ 데스크톱 앱 관련

### Q15: macOS에서 "앱이 손상되었습니다"라고 나오거나 데스크톱 앱이 열리지 않아요

**원인**: 현재 macOS DMG는 아직 Apple Developer 인증서로 서명하고 공증하지 않았습니다. 브라우저로 내려받으면 macOS Gatekeeper가 앱에 quarantine(다운로드 격리) 속성을 붙여 실행을 막을 수 있습니다.

**해결 방법**:

1. 프로젝트의 [GitHub Releases](https://github.com/ZhuLinsen/daily_stock_analysis/releases)에서만 첨부 파일을 내려받고, 설치 파일의 아키텍처가 Mac과 맞는지 확인하세요. 제3자가 다시 올렸거나 출처를 알 수 없는 앱에 대해서는 Gatekeeper를 우회하지 마세요.
2. `Daily Stock Analysis`를 "응용 프로그램"으로 끌어 놓고, 먼저 "시스템 설정 → 개인정보 보호 및 보안"에서 "그래도 열기"를 시도합니다.
3. 그래도 실행되지 않고 파일이 프로젝트 공식 Release에서 온 것이 확실하다면, 터미널에서 이 앱에 대해서만 quarantine 속성을 지우고 실행할 수 있습니다.

   ```bash
   xattr -dr com.apple.quarantine "/Applications/Daily Stock Analysis.app"
   open "/Applications/Daily Stock Analysis.app"
   ```

앱이 `/Applications`에 없다면 실제 `.app` 경로로 바꾸세요. `/Applications` 디렉터리 전체에 `xattr`를 실행하지 마세요. 이 명령은 믿을 수 있는 unsigned 앱을 임시로 허용할 뿐, 서명이나 공증을 대신하지 않습니다. 전체 문제 해결 안내는 [데스크톱 앱 패키징과 배포](desktop-package.md#macos-提示应用已损坏无法打开)를 보세요.

> 📌 관련 Issue: [#2113](https://github.com/ZhuLinsen/daily_stock_analysis/issues/2113)

---

## 🔧 기타

### Q16: 개별 종목 분석 없이 시장 복기만 실행하려면?

**방법**:
```bash
# 로컬 실행
python main.py --market-only

# GitHub Actions
# 직접 실행할 때 mode: market-only 선택
```

---

### Q17: 분석 결과의 매수/관망/매도 개수 통계가 맞지 않아요

**원인**: 초기 버전은 정규식 매칭으로 통계를 내서 실제 의견과 다를 수 있었습니다.

**해결 방법**: 최신 버전에서 고쳐졌습니다. 이제 AI 모델이 정확한 통계를 위해 `decision_type` 필드를 직접 출력합니다.

---

### Q18: 주말에 GitHub Actions를 직접 실행했는데 왜 "비거래일이라 건너뜀"이라고 나오나요?

**증상**: `TRADING_DAY_CHECK_ENABLED`를 설정했거나 직접 실행하고 싶은데, 로그에 "今日所有相关市场均为非交易日，跳过执行"(오늘은 관련된 모든 시장이 비거래일이라 실행을 건너뜀)이 나옵니다.

**해결 방법**:
1. `Actions → 每日股票分析 → Run workflow`를 엽니다(`每日股票分析`는 "일일 주식 분석" workflow 이름입니다)
2. 직접 실행할 때 `force_run`을 `true`로 둡니다(이번 한 번만 강제 실행)
3. 거래일 확인을 계속 끄고 싶다면 `Settings → Secrets and variables → Actions`에서 다음을 설정합니다.
   ```bash
   TRADING_DAY_CHECK_ENABLED=false
   ```

**규칙 정리**:
- `TRADING_DAY_CHECK_ENABLED=true`이고 `force_run=false`: 비거래일에는 건너뜀(기본값)
- `force_run=true`: 이번에는 비거래일이어도 실행
- `TRADING_DAY_CHECK_ENABLED=false`: 예약 실행과 직접 실행 모두 거래일 확인을 하지 않음

---

## 💬 그래도 해결되지 않나요?

위 내용으로 해결되지 않았다면 다음을 이용해 주세요.
1. [전체 설정 가이드](full-guide.md) 보기
2. [GitHub Issue](https://github.com/ZhuLinsen/daily_stock_analysis/issues) 검색 또는 제출
3. [변경 이력](CHANGELOG.md)에서 최근 수정 사항 확인

---

*마지막 업데이트: 2026-08-03*
