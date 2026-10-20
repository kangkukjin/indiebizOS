# 87회차 — 세 조작면 드라이버(Android 폰·Windows PC·Chrome)를 한 프로그램으로: 쓰기·원복·실패 모양

설계 정본: [LONG_SENTENCE_DRIVER_TRIAD_DESIGN_2026_10_20.md](../../../LONG_SENTENCE_DRIVER_TRIAD_DESIGN_2026_10_20.md). 형식 = 가이드 §2 이음새 입장 회차 + 탐침 묶음 + 독립 AI 1회.

## 과제(설계 §3 원문을 그대로, AI 에도 같은 글)

"집 안 기기들로 저녁 영상 시청 준비가 되는지 점검하고 준비해 줘. 거실 TV 에 붙은 Windows PC(tv1)는 화면·전원·사용자 입회·실행 앱·네트워크 상태를 읽고,
60초 동안 잠들지 않게 잡았다가 풀어 주고, 클립보드에 오늘 볼 링크 `https://example.org/tonight` 를 넣었다가 원래 내용으로 되돌려 줘. 메모장을 최소화로
띄웠다가 닫아 줘. 안방 스피커 폰(삼성0)은 미디어 음량을 절반으로 낮췄다가 끝나면 원래대로 복원하고, 밝기 설정을 읽어 둬. 거실 스피커 폰(예나폰)은
화면을 켜고 지금 화면을 읽은 다음 설정 앱을 열어 화면을 읽고, 뒤로 가서 홈으로 돌아온 뒤 화면을 꺼 줘. 내 휴대폰(삼성1)은 상태만 읽고 아무것도 바꾸지 마.
이 맥의 Chrome 에는 같은 링크를 배경 탭으로 열되 내가 보는 탭은 그대로 두고, 그 탭으로 갔다가 원래 탭으로 돌아온 뒤 그 탭만 닫아 줘.
같은 점검을 맥26 에도 보내되 거기서는 클립보드 왕복만 해.
기기마다 시작 상태와 끝 상태가 같은지 확인하고, 어느 동작이 실패·미확인이어도 나머지는 계속하고, 성공·실패·미확인을 구분한 JSON 보고서 하나로 남겨 줘.
실제로 소리가 났는지·사람이 보고 있는지·페이지가 다 떴는지는 확인한 것과 구분해 줘. 안 되는 기기는 건너뛰고 이유를 적어."

## 실행 전 조건 실측 (2026-10-20 23:50~23:54 KST)

- 백엔드 phase ACTIVE(outcome restarted), HEAD `8e5e853a`, Windows·Chrome 드라이버 작업은 **미커밋** 상태(dirty 40여 파일).
- `[self:limb]{op:"list"}` 연결: tv1 `guestpc-70e163471313`·맥26 `guestpc-9dc41d53987d`·삼성0 `guestpc-fc7b12fba936`·예나폰 `guestpc-f0fa1e3465a0`·삼성1 `guestpc-4e51c614b25b`. 맥12 미연결.
- tv1: 앞 창 `about:blank - Chrome`(Netflix 아님), idle 203,511초, 클립보드 길이 0(원복 = 빈 글 Clear). 설계대로 lock·sleep·wifi·shortcut 은 제외.
- **맥26**: 명부 `connected:true` 인데 `PC조회묶음` 이 "선택 PC가 연결·활성·shell 준비 상태가 아닙니다"(stage target) — 헬퍼 capabilities 에 `runtimes` 없음. 설계 §2 의 "원격 맥 OS 드라이버 첫 실측" 은 이 거절 경로 관측으로 바뀐다(발견 후보, 진단은 실행 뒤).
- 삼성0: `hardware_control:1`, SM-A366N Android 16, 화면 켜짐·잠금 없음, music 음량 3/15. `ui_snapshot` → `UI_DRIVER_UPDATE_REQUIRED`(APK 가 ui_contract:1 아님). 예나폰·삼성1: `hardware_control:0`(구형 APK), 화면 꺼짐·잠김.
  → 설계 §2 의 분기대로 **UI 가지는 거절 경로 관측**이 된다. 대상은 예나폰(설계) 대신 삼성0(화면 켜짐·잠금 없음·계약 1)로 바꿔 "APK 판본" 하나만 원인으로 남긴다. 예나폰은 읽기만. APK 설치는 회차 밖.
- 본체 Chrome 창 1·탭 14·현재 탭 5. 사용자는 다른 창에서 작업 중(Chrome 가지는 배경 동작만).
- 예산: 23:50 시작, **00:50 KST 상한**(준비 포함 60분). 독립 AI 1회는 상한 밖 별도 계시.

## 입력·격리

- 실기 쓰기(원복 짝): tv1 keep_awake 60→allow_sleep · clipboard_write(링크)→clipboard_write(원문) · launch notepad→quit / 삼성0 volume_half→volume_restore / 본체 Chrome open(배경)→switch→switch(복귀)→close(탭 id) / 맥26 clipboard 왕복(거절 예상).
- 쓰기 없음: 삼성1·예나폰(status·volume_status 만). 외부 발송·공개·예약 0.
- 보고서: `outputs/…/trainer/base_v0.json`(raw 포함, git 밖). git 에는 프로그램·task·판정만. 클립보드 원문은 길이만.
- 완료 조건: 가지 7(tv1·맥26·삼성0 음량·삼성0 UI·삼성1·예나폰·Chrome), 쓰기 행 바로 뒤 재조회 행, 원복 대조 3값(same/changed/unverified)에서 changed 0, JSON 저장·재독 일치, 미검증 항목 명시(소리·입회·페이지 로드·Windows 화면 잠듦).
