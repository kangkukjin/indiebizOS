# manage_events 도구 사용 가이드

## 개요
캘린더 이벤트와 스케줄 작업을 **하나의 도구**로 통합 관리합니다.
`calendar_events.json`이 유일한 정보 원천(Single Source of Truth)입니다.

**핵심 규칙**: `event_action` 필드가 있으면 실행 가능한 스케줄 작업, 없으면 순수 캘린더 이벤트(정보 기록)입니다.

## 이벤트 타입

### anniversary (기념일, repeat: yearly)
- "결혼기념일이 5월 15일이야"
- "우리 만난 날이 3월 20일"

### birthday (생일, repeat: yearly)
- "내 생일은 11월 3일"
- "엄마 생일이 9월 25일"

### appointment (약속, repeat: none)
- "다음주 수요일 치과 예약"
- "2월 15일 오후 3시에 미팅"

### reminder (리마인더, repeat: 상황에 따라)
- "매달 25일 카드 결제일"
- "매주 월요일 팀미팅"

### schedule (스케줄 작업, event_action 필수)
- "매일 아침 9시에 알림 보내줘"
- "매주 월요일에 스위치 실행해줘"

### other (기타)
- 위 분류에 맞지 않는 일정

## 반복 유형
- **none**: 1회성 (기본값)
- **daily**: 매일
- **weekly**: 매주 (weekdays 배열 사용, 0=월 ~ 6=일)
- **monthly**: 매달 같은 날
- **yearly**: 매년 같은 날 (month/day 사용)
- **interval**: N시간 간격 (interval_hours 사용)

## 날짜/시간 형식
- date: YYYY-MM-DD (예: "2026-05-15")
- time: HH:MM (예: "14:00")

## 실행 가능 이벤트 (스케줄 작업)
`event_action` 필드를 지정하면 해당 시간에 자동 실행됩니다:
- **send_notification**: 알림 전송 (action_params: {title, message})
- **run_switch**: 스위치 실행 (action_params: {switch_id})
- **test**: 테스트 실행

## 호출 예시

### 기념일 등록 (순수 캘린더)
```json
{
  "action": "add",
  "title": "결혼기념일",
  "date": "2020-05-15",
  "type": "anniversary",
  "repeat": "yearly",
  "description": "결혼기념일"
}
```

### 약속 등록
```json
{
  "action": "add",
  "title": "치과 예약",
  "date": "2026-02-15",
  "time": "14:00",
  "type": "appointment",
  "repeat": "none",
  "description": "오후 2시 치과 정기검진"
}
```

### 생일 등록
```json
{
  "action": "add",
  "title": "엄마 생일",
  "date": "1960-09-25",
  "type": "birthday",
  "repeat": "yearly"
}
```

### 매월 반복 리마인더
```json
{
  "action": "add",
  "title": "카드 결제일",
  "date": "2026-01-25",
  "type": "reminder",
  "repeat": "monthly",
  "description": "신한카드 결제일"
}
```

### 매일 알림 스케줄 (실행 가능)
```json
{
  "action": "add",
  "title": "아침 인사 알림",
  "time": "09:00",
  "type": "schedule",
  "repeat": "daily",
  "event_action": "send_notification",
  "action_params": {"title": "좋은 아침!", "message": "오늘도 화이팅!"}
}
```

### 스위치 실행 스케줄
```json
{
  "action": "add",
  "title": "주간 리포트",
  "time": "18:00",
  "type": "schedule",
  "repeat": "weekly",
  "weekdays": [4],
  "event_action": "run_switch",
  "action_params": {"switch_id": "switch_abc123"}
}
```

### 기념일 하루 전 알림
사용자가 "결혼기념일 하루 전에 알려줘"라고 하면:
1. 기념일 자체를 기록 (type: anniversary, repeat: yearly)
2. 하루 전 알림을 추가 등록 (type: schedule, event_action: send_notification, yearly 반복)

```json
{
  "action": "add",
  "title": "결혼기념일 리마인더",
  "date": "2020-05-14",
  "time": "09:00",
  "type": "schedule",
  "repeat": "yearly",
  "month": 5,
  "day": 14,
  "event_action": "send_notification",
  "action_params": {"title": "내일은 결혼기념일!", "message": "내일 결혼기념일입니다. 준비하세요!"}
}
```

### 목록 조회
```json
{"action": "list"}
```

### 특정 월 조회
```json
{"action": "list", "year": 2026, "month": 5}
```

### 이벤트 수정
```json
{
  "action": "update",
  "event_id": "evt_abc123def456",
  "title": "결혼기념일 (6주년)"
}
```

### 이벤트 삭제
```json
{"action": "delete", "event_id": "evt_abc123def456"}
```

### 실행 이벤트 토글 (활성화/비활성화)
```json
{"action": "toggle", "event_id": "evt_abc123def456"}
```

### 즉시 실행
```json
{"action": "run_now", "event_id": "evt_abc123def456"}
```

## 주의사항
1. 기념일/생일은 **yearly** 반복이 기본입니다.
2. 약속은 **none** (1회)이 기본입니다.
3. date 필드의 년도는 실제 년도를 사용하세요 (생일: 태어난 해, 기념일: 시작된 해).
4. 실행 가능 이벤트(event_action 있음)는 daily, interval 등에서 date 없이 time만으로 등록 가능합니다.
5. 사용자가 "올해" 약속을 말하면 현재 연도를 사용하세요.
6. 사용자가 날짜를 구체적으로 안 말하면 확인 후 등록하세요.
7. list_switches 도구로 스위치 ID를 먼저 확인한 후 run_switch 스케줄을 등록하세요.
