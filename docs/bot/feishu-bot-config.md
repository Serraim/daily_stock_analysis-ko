# Feishu(페이슈) 알림 설정 안내

Feishu(飞书, 페이슈)는 중국 ByteDance가 만든 업무용 메신저입니다. 해외판 이름은 Lark입니다. Feishu 콘솔과 앱 화면은 중국어로 표시되는 경우가 많으므로, 이 문서에서는 화면에서 찾아야 하는 메뉴 이름을 한국어로 옮기고 괄호 안에 원래 중국어 표시를 함께 적었습니다.

이 문서는 흔한 요구 두 가지만 다룹니다.

1. 분석 결과를 Feishu 그룹으로 알림 보내기
2. Feishu 앱 모드, App Bot 직접 알림, 그룹 봇 Webhook 모드를 섞어 쓰지 않기

## 먼저 두 가지 모드를 구분하기

### 모드 1: 그룹 봇 Webhook 알림

이럴 때 씁니다.
- 분석 보고서를 Feishu 그룹으로 보내기만 하면 될 때
- Feishu 메시지 콜백을 처리할 필요가 없을 때
- Stream Bot이 필요 없을 때

이 프로젝트에서 가장 권장하고, 가장 쉽게 적용할 수 있는 Feishu 알림 방식입니다.

설정해야 하는 변수:

```env
FEISHU_WEBHOOK_URL=https://open.feishu.cn/open-apis/bot/v2/hook/your_hook_token
# 필요할 때만 입력
FEISHU_WEBHOOK_SECRET=your_sign_secret
FEISHU_WEBHOOK_KEYWORD=股票日报
```

> `股票日报`(주식 일일 보고)는 예시 키워드입니다. Feishu 봇 보안 설정에 직접 입력한 키워드와 똑같이 적으면 되고, 한국어 등 다른 단어를 써도 됩니다.

### 모드 2: Feishu 앱 / App Bot / Stream Bot / 클라우드 문서

이럴 때 씁니다.
- Feishu App Bot으로 지정한 그룹이나 사용자에게 직접 알림을 보내려 할 때
- Feishu 앱 봇과 대화형 기능을 만들려 할 때
- Stream 모드를 켜려 할 때
- Feishu 클라우드 문서 기능을 쓰려 할 때

관련 변수:

```env
FEISHU_APP_ID=cli_xxx
FEISHU_APP_SECRET=xxx
# App Bot으로 직접 알림을 보낼 때 필수
FEISHU_CHAT_ID=oc_xxx
# 1:1 채팅이면 open_id로 설정, 그룹 채팅은 기본값 chat_id
FEISHU_RECEIVE_ID_TYPE=chat_id
# 이벤트 구독 / Stream Bot을 쓸 때만 켬
FEISHU_STREAM_ENABLED=true
# Lark 해외판은 반드시 lark로 설정, 중국판 Feishu는 feishu 유지
FEISHU_DOMAIN=feishu
```

주의:
- `FEISHU_APP_ID` / `FEISHU_APP_SECRET`만으로는 그룹 Webhook 알림이 켜지지 않습니다.
- 간단한 그룹 알림이라면 `FEISHU_WEBHOOK_URL`을 먼저 설정하십시오.
- Webhook을 쓰지 않을 때 App Bot 직접 알림을 쓰려면 `FEISHU_APP_ID`, `FEISHU_APP_SECRET`, `FEISHU_CHAT_ID`를 모두 설정해야 합니다.
- `FEISHU_STREAM_ENABLED`는 이벤트 구독 / Stream Bot만 뜻하며, 직접 알림 설정이 끝났는지 판단하는 데는 쓰이지 않습니다.
- `FEISHU_DOMAIN=lark`로 설정하면 App Bot 직접 발송, Stream 장기 연결, 메시지 답장이 모두 `open.larksuite.com`을 사용합니다. 중국판 Feishu는 기본값 `feishu`를 씁니다.
- 앱 봇 / Stream Bot을 만드는 경우라면 문서 끝에 남겨 둔 원래 절차 스크린샷을 바로 참고하십시오.
- App Bot 발송 경로는 `requirements.txt`에 이미 있는 `lark-oapi>=1.0.0`을 그대로 씁니다. 표준 설치는 `pip install -r requirements.txt`입니다. [Feishu message create OpenAPI](https://open.feishu.cn/document/server-docs/im-v1/message/create), [lark-oapi PyPI](https://pypi.org/project/lark-oapi/), [SDK repo](https://github.com/larksuite/oapi-sdk-python)를 참고하십시오.

### 파일 발송 모드(FEISHU_SEND_AS_FILE)

켜면 Feishu App Bot이 보고서를 텍스트/카드 메시지 대신 `.md` 파일로 보냅니다.

```bash
FEISHU_SEND_AS_FILE=true
```

- **필요한 앱 권한**: `im:message`(메시지 보내기) + `im:file`(파일 업로드)
- **의존성 버전**: `lark-oapi>=1.0.0`에 `im.v1.file.create` API(파일 업로드 클래스)가 들어 있어야 합니다.
- **Webhook 모드**: Webhook은 파일 업로드를 지원하지 않으므로 파일 내용을 텍스트로 보내는 방식으로 대체됩니다.
- **적용 범위**: `route_type="report"`인 보고서 알림에만 적용됩니다. 경보(알림 규칙), 시스템 알림 등에는 영향이 없습니다.
- **GitHub Actions 예약 실행**: `.github/workflows/00-daily-analysis.yml`에 이미 연결되어 있으므로, 저장소 Settings → Secrets and variables → Actions에서 같은 이름의 변수나 secret을 추가하면 켜집니다.
- **설정 방법**: `.env` 파일, GitHub Actions Secret/Variable, Web/데스크톱 설정 페이지 모두 지원합니다.

## Webhook 알림을 올바르게 설정하는 순서

### 1. Feishu 그룹에서 사용자 지정 봇 만들기

경로는 보통 다음과 같습니다.
- 그룹 채팅
- 그룹 설정(`群设置`)
- 그룹 봇(`群机器人`)
- 봇 추가(`添加机器人`)
- 사용자 지정 봇(`自定义机器人`)

다 만들고 나면 봇이 알려 주는 Webhook URL을 복사합니다.

예시:

```env
FEISHU_WEBHOOK_URL=https://open.feishu.cn/open-apis/bot/v2/hook/xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx
```

### 2. 봇 보안 설정 확인하기

Feishu 그룹 봇에는 흔히 세 가지 보안 제한이 있습니다.

1. 보안 설정 없음
2. "키워드"(`关键词`) 켜기
3. "서명 검증"(`签名校验`) 켜기

봇에 추가 보안 항목을 켰다면 프로젝트 쪽에도 똑같이 설정해야 합니다. 그렇지 않으면 Feishu가 요청을 거부합니다.

#### 키워드를 켠 경우

Feishu에 설정한 키워드와 같은 값을 다음에 적습니다.

```env
FEISHU_WEBHOOK_KEYWORD=股票日报
```

프로젝트가 모든 Feishu 메시지 앞에 이 키워드를 자동으로 붙이므로 보고서 템플릿을 직접 고칠 필요는 없습니다.

#### 서명 검증을 켠 경우

Feishu에 표시된 secret을 다음에 적습니다.

```env
FEISHU_WEBHOOK_SECRET=your_sign_secret
```

프로젝트가 Feishu 요구 사항에 맞춰 모든 메시지에 `timestamp`와 `sign`을 자동으로 붙입니다.

### 3. 실행하고 확인하기

`FEISHU_WEBHOOK_URL`만 설정되어 있으면 알림은 Webhook 채널로 나갑니다.

다음 값도 함께 입력했더라도:

```env
FEISHU_APP_ID=...
FEISHU_APP_SECRET=...
```

Webhook 알림에는 영향이 없습니다. 다만 이 두 값이 `FEISHU_WEBHOOK_URL`을 대신하지는 못합니다.

Webhook을 설정하지 않았다면 App Bot 직접 알림을 쓸 수도 있습니다.

```env
FEISHU_APP_ID=cli_xxx
FEISHU_APP_SECRET=xxx
FEISHU_CHAT_ID=oc_xxx
FEISHU_RECEIVE_ID_TYPE=chat_id
```

이때는 `FEISHU_STREAM_ENABLED`를 켤 필요가 없습니다. 이 값은 이벤트 구독 / Stream Bot에만 쓰입니다.

### 4. Feishu 자동화에서 Webhook 트리거 설정하기

Feishu 자동화(`自动化`) 흐름에서 이 프로젝트가 보내는 카드 메시지를 받아 쓰려면 다음과 같이 설정합니다.

1. Webhook 트리거를 만들 때 **매개변수**(`参数`)에 아래 JSON을 입력합니다(`content`는 필요에 따라 자리표시자를 그대로 두어도 됩니다).

```json
{
  "msg_type": "interactive",
  "card": {
    "config": { "wide_screen_mode": true },
    "elements": [
      {
        "tag": "div",
        "text": {
          "tag": "lark_md",
          "content": "..."
        }
      }
    ],
    "header": {
      "title": {
        "tag": "plain_text",
        "content": "A股智能分析报告"
      }
    }
  }
}
```

> `"A股智能分析报告"`는 카드 제목으로 표시되는 문자열로, 뜻은 "A주 AI 분석 보고서"입니다. 예시이므로 원하는 제목으로 바꿔도 됩니다.

2. **동작/메시지 내용**(`操作/消息内容`) 부분에는 일반 텍스트를 직접 입력하지 마십시오. 더하기(+) 버튼을 눌러 **Webhook 트리거**(`Webhook 触发`)를 고른 뒤 다음 항목에 연결합니다.

`card.elements[0].text.content`

![img_11.png](img_11.png)

## 가장 흔한 실패 원인

### 1. `FEISHU_APP_ID` / `FEISHU_APP_SECRET`만 입력한 경우

증상:
- "Feishu 설정은 끝났다"고 생각했는데
- 실제로는 그룹 알림이 전혀 오지 않습니다.

원인:
- 이 두 변수는 앱 자격 증명일 뿐입니다. 직접 알림에는 `FEISHU_CHAT_ID`가, 그룹 Webhook 알림에는 `FEISHU_WEBHOOK_URL`이 더 필요합니다.

올바른 방법:
- 간단한 그룹 알림: `FEISHU_WEBHOOK_URL`을 추가합니다.
- App Bot 직접 알림: `FEISHU_CHAT_ID`를 추가하고, 앱에 메시지 보내기 권한이 있으며 봇이 대상 그룹에 들어가 있는지 확인합니다.

### 2. Feishu 봇에 키워드를 켰는데 로컬에 `FEISHU_WEBHOOK_KEYWORD`를 설정하지 않은 경우

증상:
- 다른 앱은 메시지를 보낼 수 있는데
- 이 프로젝트만 메시지가 들어가지 않거나, Feishu가 바로 검증 실패를 돌려줍니다.

올바른 방법:
- Feishu 봇 보안 설정의 키워드를 그대로 `FEISHU_WEBHOOK_KEYWORD`에 입력합니다.

### 3. Feishu 봇에 서명 검증을 켰는데 로컬에 `FEISHU_WEBHOOK_SECRET`을 설정하지 않은 경우

증상:
- Webhook URL은 문제없어 보이는데
- Feishu가 서명 관련 오류를 돌려줍니다.

올바른 방법:
- 봇 secret을 `FEISHU_WEBHOOK_SECRET`에 입력합니다.

### 4. 봇이 대상 그룹에 없거나 발언 권한이 없는 경우

확인할 것:
- 봇이 정말 대상 그룹에 추가되어 있는지
- 그룹 관리자가 봇의 메시지 발송을 제한하지 않았는지

### 5. Feishu 쪽에 IP 화이트리스트를 설정한 경우

클라우드 서버, Docker, GitHub Actions에서 실행하면 외부로 나가는 IP가 로컬과 다를 수 있습니다.

확인할 것:
- Feishu 봇에 IP 화이트리스트(`IP 白名单`)가 켜져 있는지
- 현재 실행 환경의 외부 IP가 화이트리스트에 들어 있는지

## 권장하는 최소 설정

### 추가 보안 제한 없음

```env
FEISHU_WEBHOOK_URL=https://open.feishu.cn/open-apis/bot/v2/hook/your_hook_token
```

### 키워드 사용

```env
FEISHU_WEBHOOK_URL=https://open.feishu.cn/open-apis/bot/v2/hook/your_hook_token
FEISHU_WEBHOOK_KEYWORD=股票日报
```

### 서명 검증 사용

```env
FEISHU_WEBHOOK_URL=https://open.feishu.cn/open-apis/bot/v2/hook/your_hook_token
FEISHU_WEBHOOK_SECRET=your_sign_secret
```

### 키워드와 서명을 함께 사용

```env
FEISHU_WEBHOOK_URL=https://open.feishu.cn/open-apis/bot/v2/hook/your_hook_token
FEISHU_WEBHOOK_SECRET=your_sign_secret
FEISHU_WEBHOOK_KEYWORD=股票日报
```

## 권장 점검 순서

1. 먼저 원하는 것이 "그룹 Webhook 알림"인지 "앱 / Stream Bot"인지 확인합니다.
2. 간단한 그룹 알림만 쓴다면 `FEISHU_WEBHOOK_URL`이 설정되어 있는지부터 확인합니다.
3. Webhook 대신 App Bot 직접 알림을 쓴다면 `FEISHU_APP_ID` / `FEISHU_APP_SECRET` / `FEISHU_CHAT_ID` 세 값이 모두 있는지 확인합니다.
4. Feishu 봇 보안 설정으로 돌아가 키워드나 서명이 켜져 있는지 확인합니다.
5. 켜져 있다면 `FEISHU_WEBHOOK_KEYWORD` / `FEISHU_WEBHOOK_SECRET`을 채웁니다.
6. 마지막으로 봇이 그룹에 있는지, 권한이 있는지, IP 화이트리스트에 걸리지 않는지 확인합니다.

## 부록: 앱 / Stream Bot 원래 절차 스크린샷

단순한 그룹 Webhook 알림이 아니라 Feishu 앱, 장기 연결 봇, 클라우드 문서를 계속 설정하려면 아래 원래 스크린샷을 참고하십시오. 스크린샷 속 Feishu 개발자 콘솔은 중국어 화면입니다.

### 1. 앱 만들기

https://open.feishu.cn/document/develop-an-echo-bot/introduction

![img_6.png](img_6.png)

![img_8.png](img_8.png)

### 2. 키 확인하기

![img_7.png](img_7.png)

### 3. 앱 게시하기

![img_5.png](img_5.png)

### 4. Feishu에서 앱 열기

![img_9.png](img_9.png)

### 5. 메시지 주고받기

![img_10.png](img_10.png)
