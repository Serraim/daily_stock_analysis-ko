# Discord 봇 설정

## Discord 봇
Discord 봇이 메시지를 받으려면 Discord Developer Portal에서 봇 애플리케이션을 만들어야 합니다.
https://discord.com/developers/applications

Discord 봇은 두 가지 메시지 발송 방식을 지원합니다.
1. **Webhook 모드**: 설정이 간단하고 권한이 적어, 메시지만 보내면 되는 경우에 맞습니다
2. **Bot API 모드**: 권한이 많고 명령을 받을 수 있으며, Bot Token과 채널 ID를 설정해야 합니다

## Discord 봇 만들기

### 1. Discord Developer Portal에 로그인
https://discord.com/developers/applications 에 접속해 Discord 계정으로 로그인합니다.

### 2. 애플리케이션 만들기
"New Application" 버튼을 누르고 애플리케이션 이름(예: 주식 분석 봇)을 입력한 뒤 "Create"를 누릅니다.

### 3. 봇 설정
왼쪽 메뉴에서 "Bot"을 누르고 "Add Bot" 버튼을 눌러 추가를 확인합니다.

### 4. Bot Token 받기
Bot 페이지에서 "Reset Token" 버튼을 누르고 생성된 Token을 복사합니다(이것이 `DISCORD_BOT_TOKEN`입니다).

### 5. 권한 설정
Bot 페이지의 "Privileged Gateway Intents" 항목에서 다음을 켭니다.
- Presence Intent
- Server Members Intent
- Message Content Intent

### 6. 서버에 추가
1. 왼쪽 메뉴에서 "OAuth2" > "URL Generator"를 누릅니다
2. "Scopes"에서 다음을 고릅니다.
   - `bot`
   - `applications.commands`
3. "Bot Permissions"에서 다음을 고릅니다.
   - Send Messages
   - Embed Links
   - Attach Files
   - Read Message History
   - Use Slash Commands
4. 생성된 URL을 복사해 브라우저에서 열고, 봇을 추가할 서버를 고릅니다

### 7. 채널 ID 받기
1. Discord 클라이언트에서 개발자 모드를 켭니다: 설정 > 고급 > 개발자 모드
2. 봇이 메시지를 보낼 채널을 마우스 오른쪽 버튼으로 누르고 "Copy ID"(ID 복사하기)를 고릅니다(이것이 `DISCORD_MAIN_CHANNEL_ID`입니다)

## 환경 변수 설정

다음 설정을 `.env` 파일에 추가합니다.

```env
# Discord 봇 설정
DISCORD_BOT_TOKEN=your-discord-bot-token
DISCORD_MAIN_CHANNEL_ID=your-channel-id
DISCORD_WEBHOOK_URL=your-webhook-url (선택)
DISCORD_INTERACTIONS_PUBLIC_KEY=your-public-key (들어오는 Interaction/Webhook 콜백을 받을 때만 필요)
DISCORD_BOT_STATUS=A股智能分析 | /help
```

`DISCORD_BOT_STATUS`는 봇 상태 문구이며, 예시의 `A股智能分析`(A주 AI 분석)은 원하는 문구로 바꿔도 됩니다.

Discord Interaction / Webhook 수신 콜백을 설정했다면, 반드시 Discord Developer Portal의 `General Information -> Public Key`에서 공개 키를 복사해 `DISCORD_INTERACTIONS_PUBLIC_KEY`에 넣으세요. 시스템은 이 공개 키로 들어오는 모든 요청의 Ed25519 서명을 검증하며, 검증에 실패한 요청은 바로 거부합니다.

## Webhook 모드 설정(선택)

Bot Token 없이 Webhook 모드로만 메시지를 보내려면 다음처럼 설정합니다.

1. 채널을 마우스 오른쪽 버튼으로 누르고 "채널 편집"을 고릅니다
2. "연동" > "웹후크" > "새 웹후크"를 누릅니다
3. Webhook 이름과 아바타를 설정합니다
4. Webhook URL을 복사합니다(이것이 `DISCORD_WEBHOOK_URL`입니다)

## 지원하는 명령

Discord 봇은 다음 Slash 명령을 지원합니다.

1. `/analyze <target> [full_report]` - 지정한 종목, 등록된 지수, 종목 이름을 분석합니다
   - `target`: 분석 대상. 종목 코드(예: `600519`), 등록된 지수(예: `sh000016`, `930955.CSI`, `上证50`), 종목 이름(예: `贵州茅台`)을 쓸 수 있습니다. 지수 이름과 종목 이름은 프로그램이 인식하는 중국어 이름 그대로 입력합니다
   - `full_report`: 선택. 전체 리포트(시장 분석 포함)를 만들지 여부

2. `/market_review` - 시장 복기 리포트를 받습니다

3. `/help` - 도움말을 봅니다

> 범위: `/analyze`는 등록된 지수와 종목 이름 입력을 지원합니다(종목 이름은 기존 이름 해석기를 거쳐 legacy code로 제출됩니다). `/ask`와 `/batch`는 아직 지수 입력을 지원하지 않습니다.

## 봇 테스트

1. 봇이 서버에 제대로 추가되었는지 확인합니다
2. 채널에 `/help`를 입력하면 봇이 도움말을 보여 줍니다
3. `/analyze 600519`를 입력해 종목 분석 기능을 테스트합니다(등록된 지수 `/analyze sh000016`, 종목 이름 `/analyze 贵州茅台`도 됩니다)
4. `/market_review`를 입력해 시장 복기 기능을 테스트합니다

## 주의 사항

1. 봇에 채널에서 메시지를 보내고 Slash 명령을 쓸 권한이 충분한지 확인하세요
2. 보안을 위해 Bot Token을 주기적으로 갱신하세요
3. Bot Token을 누구와도 공유하지 마세요
4. 봇이 응답하지 않으면 다음을 확인하세요.
   - Bot Token이 맞는지
   - 채널 ID가 맞는지
   - 봇이 온라인인지
   - 봇에 메시지 발송 권한이 있는지

## 문제 해결

- **봇이 명령에 응답하지 않음**: Bot Token과 채널 ID가 맞는지, 봇이 서버에 추가되었는지 확인하세요
- **Slash 명령이 보이지 않음**: 잠시 기다리거나(Discord가 명령을 동기화하는 데 시간이 걸립니다) 봇을 다시 추가하세요
- **메시지 발송 실패**: 채널 권한을 확인하고, 봇에 메시지 발송 권한이 있는지 확인하세요

## 관련 링크

- [Discord Developer Portal](https://discord.com/developers/applications)
- [Discord Bot Documentation](https://discordpy.readthedocs.io/en/stable/)
- [Discord Slash Commands](https://discord.com/developers/docs/interactions/application-commands)
