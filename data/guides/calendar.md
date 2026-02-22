# 캘린더 & 스케줄러 통합 가이드

## 도구 선택 기준

| 상황 | 도구 | 이유 |
|------|------|------|
| 기념일, 생일, 약속 등록 | `manage_events` | 캘린더 이벤트 관리 |
| 지정 시간에 알림/스위치 자동 실행 | `manage_events` (event_action 사용) | 실행 가능 이벤트 |
| 백그라운드 반복 작업 (스위치 실행) | `manage_schedule` | 스케줄러 전용 작업 |

**핵심**: `manage_events`는 캘린더 + 실행 가능 이벤트를 모두 처리합니다. `event_action` 필드가 있으면 자동 실행, 없으면 순수 기록입니다.

---

## manage_events (캘린더 이벤트)

`calendar_events.json`이 유일한 정보 원천(Single Source of Truth)입니다.

### 이벤트 타입
- **anniversary**: 기념일 (repeat: yearly) - "결혼기념일이 5월 15일이야"
- **birthday**: 생일 (repeat: yearly) - "엄마 생일이 9월 25일"
- **appointment**: 약속 (repeat: none) - "다음주 수요일 치과 예약"
- **reminder**: 리마인더 (repeat: 상황에 따라) - "매달 25일 카드 결제일"
- **schedule**: 스케줄 작업 (event_action 필수) - "매일 아침 9시에 알림 보내줘"
- **other**: 기타

### 반복 유형
| repeat | 설명 | 비고 |
|--------|------|------|
| none | 1회성 (기본값) | |
| daily | 매일 | |
| weekly | 매주 | weekdays 배열 (0=월~6=일) |
| monthly | 매달 같은 날 | |
| yearly | 매년 같은 날 | month/day 사용 |
| interval | N시간 간격 | interval_hours 사용 |

### 날짜/시간 형식
- date: YYYY-MM-DD
- time: HH:MM (24시간제)

### 실행 가능 이벤트 (event_action)
- **send_notification**: 알림 전송 (action_params: {title, message})
- **run_switch**: 스위치 실행 (action_params: {switch_id})
- **test**: 테스트 실행

### 호출 예시

```json
// 기념일 등록
{"action": "add", "title": "결혼기념일", "date": "2020-05-15", "type": "anniversary", "repeat": "yearly"}

// 약속 등록
{"action": "add", "title": "치과 예약", "date": "2026-02-15", "time": "14:00", "type": "appointment", "repeat": "none"}

// 생일 등록
{"action": "add", "title": "엄마 생일", "date": "1960-09-25", "type": "birthday", "repeat": "yearly"}

// 매일 알림 스케줄
{"action": "add", "title": "아침 인사", "time": "09:00", "type": "schedule", "repeat": "daily", "event_action": "send_notification", "action_params": {"title": "좋은 아침!", "message": "오늘도 화이팅!"}}

// 스위치 실행 스케줄 (매주 금요일)
{"action": "add", "title": "주간 리포트", "time": "18:00", "type": "schedule", "repeat": "weekly", "weekdays": [4], "event_action": "run_switch", "action_params": {"switch_id": "switch_abc123"}}

// 기념일 하루 전 알림
{"action": "add", "title": "결혼기념일 리마인더", "date": "2020-05-14", "time": "09:00", "type": "schedule", "repeat": "yearly", "month": 5, "day": 14, "event_action": "send_notification", "action_params": {"title": "내일은 결혼기념일!", "message": "준비하세요!"}}

// 목록 조회 / 특정 월 조회
{"action": "list"}
{"action": "list", "year": 2026, "month": 5}

// 수정 / 삭제 / 토글 / 즉시 실행
{"action": "update", "event_id": "evt_xxx", "title": "새 제목"}
{"action": "delete", "event_id": "evt_xxx"}
{"action": "toggle", "event_id": "evt_xxx"}
{"action": "run_now", "event_id": "evt_xxx"}
```

---

## manage_schedule (스케줄러)

백그라운드에서 동작하며 에이전트 없이 자동 실행합니다.

### 반복 유형
| repeat | 필수 파라미터 |
|--------|--------------|
| daily | time |
| weekly | time, weekdays (0=월~6=일) |
| once | time, date (실행 후 자동 비활성화) |
| yearly | time, month, day |
| interval | time (첫 실행), interval_hours |

### 액션 유형
- **send_notification**: action_params: {title, message, type: "info/success/warning"}
- **run_switch**: action_params: {switch_id} — 등록 전 `list_switches`로 확인 필수
- **test**: 테스트용

### 호출 예시

```json
// 기념일 알림
{"action": "add", "name": "결혼기념일 알림", "time": "09:00", "repeat": "yearly", "month": 5, "day": 15, "task_action": "send_notification", "action_params": {"title": "결혼기념일", "message": "특별한 하루 보내세요!", "type": "info"}}

// 매주 월/수/금 스위치 실행
{"action": "add", "name": "주간 뉴스 브리핑", "time": "08:00", "repeat": "weekly", "weekdays": [0, 2, 4], "task_action": "run_switch", "action_params": {"switch_id": "switch_xxx"}}

// 1회성 약속 알림
{"action": "add", "name": "치과 예약", "time": "13:00", "repeat": "once", "date": "2026-02-15", "task_action": "send_notification", "action_params": {"title": "치과 예약", "message": "오후 2시 치과 예약", "type": "warning"}}
```

---

## 주의사항
1. 기념일/생일은 yearly 반복이 기본
2. 약속은 none (1회)이 기본
3. date의 년도는 실제 년도 사용 (생일: 태어난 해, 기념일: 시작된 해)
4. run_switch 등록 전에 `list_switches`로 스위치 ID 확인 필수
5. 사용자가 명시적으로 요청하지 않은 스케줄은 등록하지 마세요
