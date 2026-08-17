# 폰 알림 참조 가이드

사용자의 스마트폰(컴패니언 앱)이 받은 알림이 indiebizOS 에 저장되어 있다.
카카오톡·문자·앱 알림 등. 사용자가 **폰/알림/카톡/메시지/연락** 관련해 물으면 이걸 참조한다.

## 읽는 법 (run_command)

```bash
curl -s "http://localhost:8765/phone/notifications?limit=20"
```

반환: `{"notifications": [{pkg, title, body, posted_at, sender}, ...], "count": N}`
- `pkg`: 앱 패키지 (예 `com.kakao.talk`=카톡, `com.android.shell`=테스트)
- `title`/`body`: 알림 제목/본문
- `posted_at`: 폰에서 알림이 뜬 시각 (Unix)
- 최신순 정렬.

특정 앱만: `?pkg=com.kakao.talk`. 즉시 새로 받아오려면 `POST /phone/notifications/poll`.

## 위치 / 걸음수 (자기상태 신호)

```bash
curl -s "http://localhost:8765/phone/locations?limit=20"   # 위치(30분 간격 기록)
curl -s "http://localhost:8765/phone/steps?limit=14"        # 일별 걸음수(1일 1회)
```

- 위치: `{lat, lng, accuracy(m), captured_at}` 최신순. "지금 어디야?"→가장 최근 좌표. 좌표→지명은 location 도구로 역지오코딩.
- 걸음: `{date, steps, cumulative}` 날짜순. "어제 몇 보 걸었어?"→해당 date의 steps. (당일 값은 다음날 보고됨 — 1일 1회 설계.)
- 심박·수면은 폰에 데이터가 없어 **수집 안 함**.

## 대화 활용

- "카톡 뭐 왔어?" → kakao.talk 항목을 사람이 읽기 좋게 요약.
- "오늘 알림 정리해줘" → posted_at 으로 추리고 앱별 묶어 정리.
- 알림은 **한방향 센서 피드**다 — 여기서 답장 전송 등은 (아직) 못 한다. 읽어서 알려주는 용도.

## 한계

- 폴러가 ~60초마다 릴레이서 가져와 저장한다. 막 온 알림은 약간 지연될 수 있음 → 필요시 poll 먼저.
- 저장된 것만 보인다(앱 설치·알림접근 허용 이후). 그 전 알림은 없다.
