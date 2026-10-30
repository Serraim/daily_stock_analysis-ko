# DingTalk(딩톡) 기업 봇 설정

## DingTalk 봇
DingTalk 봇이 메시지를 받으려면 기업 봇(企业机器人) 기능을 사용해야 합니다.
https://open.dingtalk.com/document/dingstart/configure-the-robot-application

메시지 수신 방식은 `Http模式`(HTTP 모드, 외부에서 접근 가능한 공인 주소 필요)와 `Stream模式`(Stream 모드) 두 가지가 있으며, `Stream模式`을 권장합니다.

앱 생성 절차: https://open.dingtalk.com/document/dingstart/create-application

DingTalk 개발자 콘솔 메뉴 경로: 应用开发(앱 개발) > 企业内部应用(기업 내부 앱) > 钉钉应用(DingTalk 앱) > 创建应用(앱 만들기) > 添加应用能力(앱 기능 추가) > 机器人(봇)

### 봇 추가

![봇 추가 화면](add-dingding-bot.png)

### 봇이 Stream 모드를 쓰도록 설정

![Stream 모드 설정 화면](configbot.png)

### 앱 자격 증명 확인
![앱 자격 증명 화면](appkey.png)

### DingTalk 자격 증명 설정
DingTalk 앱 자격 증명을 설정 파일에 넣습니다.
![환경 설정 예시](envconfig.png)

### 앱 게시
![앱 게시 화면](img.png)

![그룹 화면](group.png)

![그룹에 봇 추가 화면](add-group-bot.png)

### 아래로 스크롤하면 추가한 기업 봇이 보입니다
![추가된 기업 봇](img_1.png)

### 봇 명령 테스트
![봇 명령 테스트 화면](img_3.png)