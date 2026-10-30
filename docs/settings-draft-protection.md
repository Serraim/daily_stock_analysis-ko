# 설정 페이지 초안 보호 / Unsaved settings protection

## 한국어

설정 페이지는 일반 설정, 모델 채널, 스케줄 스위치에서 아직 저장하지 않은 초안을 한곳에서 추적합니다. 잠시 유효하지 않은 채널 이름도 포함됩니다. 설정 분류를 바꿔도 이렇게 편집 중인 내용은 유지됩니다.

- 새로고침, 탭 닫기, 사이트 내부 링크 이동, 브라우저 앞으로/뒤로 가기로 페이지를 떠날 때 저장하지 않은 초안이 있으면 확인 창이 뜹니다
- 떠나기를 취소하면 초안이 유지되고, 버리기를 확인하면 모든 초안을 지운 뒤 원래 가려던 주소로 이동합니다
- 초기화는 일반 설정, 모델 채널, 스케줄의 로컬 변경을 한꺼번에 되돌립니다. 모델 채널은 여전히 별도의 저장 버튼으로 제출합니다
- 모델 저장과 그 뒤의 새로고침이 진행 중이면 초기화, 가져오기, 사이트 내부 이동 확인은 완료될 때까지 기다립니다. 이미 보낸 저장 요청은 페이지를 떠나도 취소되지 않습니다
- 환경 백업을 가져오기 전에 다른 분류에 숨어 있는 초안도 확인합니다. 가져오기 확인을 취소하면 편집 내용이 유지됩니다
- 설정 페이지에서 로그아웃하면 저장하지 않은 설정을 버릴지 먼저 명확히 확인합니다. 취소하면 세션과 초안이 유지되고, 확인하면 로그아웃합니다. 이미 보낸 저장 요청은 로그아웃해도 취소되지 않습니다. 세션이 만료되어 다시 로그인하면 원래 가려던 내부 주소의 query/hash가 그대로 유지됩니다
- 서버가 가져오기를 받아들이면, 그 뒤 새로고침이 실패하거나 모델 채널 설정이 바뀌지 않았더라도 기존 초안을 모두 지웁니다. 가져오기가 실패하면 편집 내용이 유지됩니다. 가져오기와 새로고침이 진행되는 동안에는 편집, 저장, 초기화, 이동 확인을 잠시 멈춰 예전 초안이 가져온 결과를 덮어쓰지 않게 합니다

새로고침/닫기 때 뜨는 브라우저 기본 경고의 문구와 표시 조건은 브라우저가 정하며, 보통 페이지에서 사용자가 이미 뭔가를 조작한 뒤에만 나타납니다. 브라우저를 강제로 종료하는 경우에는 경고 창이 뜬다고 보장할 수 없습니다. 초안은 현재 페이지의 메모리에만 남으며, 자동 저장이나 새로고침 후 복원 기능은 없습니다.

## English

Settings tracks unsaved generic configuration, model-channel edits, and scheduler overrides, including temporarily invalid channel names. Switching categories retains these local drafts.

- Refresh, tab close, in-app links, and browser Back/Forward warn before discarding unsaved edits
- Cancel preserves drafts; confirmed discard clears all draft owners and continues to the original destination
- Reset restores generic fields, model channels, and local scheduler overrides; model channels retain their separate Save button
- While a model save or its subsequent refresh is pending, Reset, Import, and in-app departure confirmation wait for completion; leaving cannot cancel a request already sent
- Backup import also checks drafts hidden in other categories; cancelling its confirmation preserves those edits
- Logout from Settings explicitly confirms discarding unsaved edits before ending the session. Cancel preserves the session and drafts; confirmation logs out without cancelling requests already sent. Session-expiry login redirects preserve the original internal destination's query and fragment
- Once the server accepts an import, all previous drafts are discarded even if the subsequent refresh fails or model-channel configuration is unchanged; a rejected import preserves edits. Editing, saving, resetting, and confirmed departure wait for import and refresh to finish

Native unload wording and display conditions are controlled by the browser and generally require prior user interaction. A forced browser termination cannot guarantee a prompt. Drafts live only in the current page's memory; this feature does not autosave or restore them after a refresh.
