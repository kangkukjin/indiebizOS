# manage_schedule 도구 사용 가이드

## 개요
사용자의 일정, 기념일, 반복 작업을 스케줄러에 등록하고 관리하는 도구입니다.
스케줄러는 백그라운드에서 동작하며, 에이전트 없이 지정된 시간에 자동으로 작업을 실행합니다.

**아키텍처**: `scheduler.py`는 하위 호환 래퍼이며, 모든 실제 로직은 `CalendarManager`(`calendar_manager.py`)에서 처리됩니다. 데이터 저장소는 `data/calendar_events.json`(Single Source of Truth)입니다.

## 핵심 규칙

### 1. 사용자 의도 파악
사용자가 일정이나 알림을 언급하면 적절한 스케줄 등록을 제안하세요:
- "내일 3시에 회의가 있어" → none 타입(1회), 알림 등록 제안
- "매주 월요일마다 보고서 만들어줘" → weekly 타입, 스위치 실행 등록 제안
- "결혼기념일이 5월 15일이야" → yearly 타입, 알림 등록
- "매일 아침 8시에 뉴스 정리해줘" → daily 타입, 스위치 실행 등록 제안
- "매월 1일에 월간 리포트 생성해줘" → monthly 타입, 스위치 실행 등록 제안

### 2. 반복 유형 (repeat)

| repeat | 설명 | 필수 파라미터 |
|--------|------|--------------|
| `daily` | 매일 지정 시간 | time |
| `weekly` | 매주 지정 요일+시간 | time, weekdays |
| `monthly` | 매월 지정일+시간 | time, date (일자 추출) |
| `yearly` | 매년 지정 월/일+시간 (기념일) | time, month, day |
| `none` | 1회 실행 후 자동 비활성화 | time, date |
| `interval` | N시간 간격 반복 | time (첫 실행), interval_hours |

**주의**: 1회성 스케줄의 repeat 값은 `"none"`입니다 (`"once"`가 아님).

### 3. 요일 코드 (weekdays)
weekly 타입에서 사용합니다. 리스트로 여러 요일 지정 가능:
- 0 = 월요일
- 1 = 화요일
- 2 = 수요일
- 3 = 목요일
- 4 = 금요일
- 5 = 토요일
- 6 = 일요일

예: 월/수/금 → `[0, 2, 4]`

### 4. 이벤트 타입 (event_type)

CalendarManager는 실행 가능한 스케줄뿐 아니라 순수 캘린더 이벤트도 관리합니다:

| event_type | 설명 |
|------------|------|
| `anniversary` | 기념일 |
| `birthday` | 생일 |
| `appointment` | 약속 |
| `reminder` | 리마인더 |
| `schedule` | 스케줄 작업 (실행 목적) |
| `other` | 기타 |

- `action` 필드가 있으면 실행 가능한 이벤트 (스케줄러가 자동 실행)
- `action`이 null이면 순수 캘린더 이벤트 (정보 기록만)

### 5. 액션 유형 (action)

#### run_pipeline - IBL 코드 직접 실행 (가장 유연)
IBL 코드를 직접 실행합니다. 음악 재생, 웹 검색, 파일 저장 등 모든 IBL 액션을 예약 실행할 수 있습니다.

action_params:
```json
{
  "pipeline": "[limbs:play]{query: '아이유 밤편지'}"
}
```

파이프라인 연산자도 지원:
```json
{
  "pipeline": "[sense:search_ddg]{query: 'AI 뉴스'} >> [self:file]{path: 'news.md'}"
}
```

#### run_switch - 스위치 실행
등록된 스위치를 자동으로 실행합니다. 정기 보고서, 데이터 수집 등에 적합합니다.

action_params:
```json
{
  "switch_id": "스위치_ID"
}
```

**중요**: run_switch를 등록하기 전에 반드시 `list_switches` 도구로 사용 가능한 스위치 목록을 확인하세요.

#### send_notification - 알림 전송
사용자에게 알림을 보냅니다. 기념일, 약속, 리마인더에 적합합니다.

action_params:
```json
{
  "title": "알림 제목",
  "message": "알림 내용",
  "type": "info"  // info, success, warning 중 선택
}
```

#### run_workflow - 워크플로우 실행
저장된 워크플로우를 실행합니다.

action_params:
```json
{
  "workflow_id": "워크플로우_ID"
}
```

#### run_goal - 목표 반복 실행 (Phase 26)
Goal의 every/schedule 설정에 의해 트리거됩니다. CalendarManager가 주기에 맞춰 goal의 다음 라운드를 실행합니다.

action_params:
```json
{
  "goal_id": "목표_ID"
}
```

- 종료된 목표(achieved, expired, limit_reached, cancelled)는 자동 스킵 및 비활성화
- `add_goal_schedule()` 메서드로 Goal의 every_frequency/schedule_at을 캘린더 이벤트로 자동 등록
- `remove_goal_schedule()` 메서드로 Goal 관련 스케줄 이벤트 일괄 제거

#### test - 테스트
개발/테스트 용도. action_params 불필요.

## 사용 예시

### 기념일 등록
```json
{
  "action": "add",
  "name": "결혼기념일 알림",
  "description": "결혼기념일을 축하합니다!",
  "time": "09:00",
  "repeat": "yearly",
  "month": 5,
  "day": 15,
  "task_action": "send_notification",
  "action_params": {
    "title": "결혼기념일",
    "message": "오늘은 결혼기념일입니다! 특별한 하루 보내세요.",
    "type": "info"
  }
}
```

### 매주 월/수/금 스위치 실행
```json
{
  "action": "add",
  "name": "주간 뉴스 브리핑",
  "description": "매주 월/수/금 아침에 뉴스를 정리합니다",
  "time": "08:00",
  "repeat": "weekly",
  "weekdays": [0, 2, 4],
  "task_action": "run_switch",
  "action_params": {
    "switch_id": "switch_xxx"
  }
}
```

### 1회성 약속 알림
```json
{
  "action": "add",
  "name": "치과 예약 알림",
  "description": "오후 2시 치과 예약",
  "time": "13:00",
  "repeat": "none",
  "date": "2026-02-15",
  "task_action": "send_notification",
  "action_params": {
    "title": "치과 예약",
    "message": "오늘 오후 2시에 치과 예약이 있습니다.",
    "type": "warning"
  }
}
```

### 매일 반복
```json
{
  "action": "add",
  "name": "일일 보고서",
  "description": "매일 저녁 업무 보고서 생성",
  "time": "18:00",
  "repeat": "daily",
  "task_action": "run_switch",
  "action_params": {
    "switch_id": "switch_xxx"
  }
}
```

### 매월 반복
```json
{
  "action": "add",
  "name": "월간 리포트",
  "description": "매월 1일 월간 리포트 생성",
  "time": "09:00",
  "repeat": "monthly",
  "date": "2026-01-01",
  "task_action": "run_switch",
  "action_params": {
    "switch_id": "switch_xxx"
  }
}
```

monthly 타입은 date 필드의 day 값을 매월 반복일로 사용합니다. 위 예시에서 date가 `2026-01-01`이면 매월 1일에 실행됩니다.

### 간격 반복
```json
{
  "action": "add",
  "name": "서버 상태 체크",
  "description": "3시간마다 서버 상태 확인",
  "time": "00:00",
  "repeat": "interval",
  "interval_hours": 3,
  "task_action": "run_switch",
  "action_params": {
    "switch_id": "switch_xxx"
  }
}
```

## 작업 흐름

1. 사용자가 일정/반복 작업을 요청
2. 필요시 `list_switches` 도구로 사용 가능한 스위치 확인
3. `manage_schedule` 도구의 `list` 액션으로 기존 스케줄 확인
4. `add` 액션으로 새 스케줄 등록
5. 등록 결과를 사용자에게 안내

## 주의사항
- 시간은 반드시 HH:MM 형식 (24시간제)
- date는 YYYY-MM-DD 형식
- none 타입은 실행 후 자동 비활성화됨
- run_switch 등록 전에 해당 스위치가 존재하는지 확인 필수
- 사용자가 명시적으로 요청하지 않은 스케줄은 등록하지 마세요
- 스케줄 삭제/수정 시에는 먼저 list로 task_id를 확인하세요

## "N분 후에 실행" 패턴

**manage_events의 `run_now`는 예약 시간을 무시하고 즉시 실행합니다.** 시간 지연 실행이 목적이면 `run_now`를 호출하면 안 됩니다.

올바른 워크플로우:
1. `[self:time]`으로 현재 시각 확인
2. 현재 시각 + N분 계산
3. `manage_events` `add`로 미래 시각에 `repeat: "none"` 이벤트 등록
4. 사용자에게 "HH:MM에 실행 예약했습니다" 안내
5. **여기서 끝.** 스케줄러가 지정 시각에 자동 실행함.

일회성 작업에 새 스위치를 만들지 마세요. `switches.json`을 직접 읽거나 쓰지 마세요.

---

## API 레퍼런스

모든 API는 `/scheduler` 프리픽스를 사용합니다. 내부적으로 CalendarManager에 위임됩니다.

### 스케줄러 제어

| 메서드 | 경로 | 설명 |
|--------|------|------|
| GET | `/scheduler/status` | 스케줄러 상태 (running, task_count, available_actions) |
| POST | `/scheduler/start` | 스케줄러 시작 |
| POST | `/scheduler/stop` | 스케줄러 중지 |
| GET | `/scheduler/actions` | 사용 가능한 액션 목록 |

### 작업(Task) 관리

| 메서드 | 경로 | 설명 |
|--------|------|------|
| GET | `/scheduler/tasks` | 실행 가능한 작업 목록 (action이 있는 이벤트만) |
| POST | `/scheduler/tasks` | 작업 추가 |
| PUT | `/scheduler/tasks/{task_id}` | 작업 수정 |
| DELETE | `/scheduler/tasks/{task_id}` | 작업 삭제 |
| POST | `/scheduler/tasks/{task_id}/toggle` | 작업 활성화/비활성화 토글 |
| POST | `/scheduler/tasks/{task_id}/run` | 작업 즉시 실행 |

### 캘린더 API

| 메서드 | 경로 | 설명 |
|--------|------|------|
| GET | `/scheduler/calendar/events` | 캘린더 이벤트 전체 목록 (year, month 필터 가능) |
| GET | `/scheduler/calendar/events/by-agent` | 특정 에이전트의 스케줄 조회 (project_id, agent_id 파라미터) |
| GET | `/scheduler/calendar/view` | 캘린더 HTML 생성 후 브라우저에서 열기 (year, month 파라미터) |

### Goal 관리 API (Phase 26)

| 메서드 | 경로 | 설명 |
|--------|------|------|
| GET | `/scheduler/goals` | Goal 목록 조회 (status, project_id 필터) |
| GET | `/scheduler/goals/{goal_id}` | Goal 상세 조회 (rounds, progress 포함) |
| POST | `/scheduler/goals/approve` | Goal 승인 및 활성화 (project_id, goal_id 필요) |
| POST | `/scheduler/goals/{goal_id}/kill` | Goal 중단 (project_id 파라미터) |

---

## 에이전트 소유 스케줄 (Phase 27)

모든 스케줄 이벤트에는 소유자(owner)가 있습니다. 스케줄은 중앙 큐가 아니라 **에이전트에게 속합니다**.

### 소유자 필드

| 필드 | 설명 | 예시 |
|------|------|------|
| `owner_project_id` | 소유 프로젝트 ID | `"투자"`, `"__system_ai__"` |
| `owner_agent_id` | 소유 에이전트 ID | `"researcher"`, `"system_ai"` |

### 에이전트별 스케줄 조회

```
GET /scheduler/calendar/events/by-agent?project_id=투자&agent_id=researcher
```

### 크로스 위임

다른 에이전트의 스케줄로 등록하여 시간 기반으로 일을 맡김:

```
[self:schedule]{at: "09:00",
  target_project_id: "투자", target_agent_id: "analyst",
  pipeline: "[sense:search_ddg]{query: '오늘 뉴스'}"}
```

- `target_project_id`/`target_agent_id` 지정 시 해당 에이전트가 owner
- 미지정 시 호출한 에이전트 자신이 owner (셀프 스케줄)

---

## 멀티에이전트 작업계획서

작업계획서는 자연어로 작성하고, 기존 위임 도구(`[others:delegate]`, `[others:delegate_project]`)를 순차/병렬로 조합하여 실행합니다.

작성 방법은 가이드 파일 참조: `work_plan_writing.md` (guide_db.json에서 "작업계획서"로 검색)

---

*마지막 업데이트: 2026-03-27*
