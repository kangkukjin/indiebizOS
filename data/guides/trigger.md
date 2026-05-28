# 트리거·스위치 가이드

`[self:trigger]` · `[self:switch]` 두 단일 액션으로 자동 실행 작업을 등록·관리한다. 둘 다 "조건 충족 시 IBL 파이프라인 실행"이라는 점은 같지만 **트리거는 push (외부 조건)**, **스위치는 pull (사용자 또는 다른 트리거가 호출)** 이다.

`[self:schedule]` (한 번 지연 실행) · `[self:manage_events]` (캘린더 이벤트) · `[self:show_calendar]` (HTML 표시)는 별도 액션. 이 가이드 범위 밖.

---

## 핵심 구분: 트리거 vs 스위치

| | 트리거 | 스위치 |
|---|---|---|
| 실행 시점 | 조건(시간·메시지·웹훅·파일) 충족 시 자동 | 사용자 또는 트리거가 명시적으로 호출 |
| 등록 단위 | 조건 + pipeline 묶음 | 이름이 붙은 pipeline (재사용용) |
| 비유 | 알람·자동응답 | 매크로·단축키 |
| 예 | "매일 8시 뉴스 요약" | "오늘 일정 정리해서 메일" 스위치 |

조합 패턴: 자주 쓰는 작업을 **스위치**로 등록 → 그 스위치를 호출하는 **트리거**를 별도로 등록. 트리거 안에서 직접 IBL pipeline 적어도 되지만, 스위치로 분리하면 수동 실행도 가능해진다.

---

## `[self:trigger]{op}` — 9 op

| op | 필수 | 선택 | 설명 |
|---|---|---|---|
| `list` | (없음) | `type` (필터) | 등록된 모든 트리거 |
| `get` | `trigger_id` | — | 트리거 상세 |
| `create` | `trigger_id` (이름), `pipeline`, `type` | `config`, `enabled` | 새 트리거 |
| `update` | `trigger_id` | `type`/`config`/`pipeline`/`enabled` | 필드 수정 |
| `delete` | `trigger_id` | — | 영구 삭제 |
| `enable` | `trigger_id` | — | 활성화 |
| `disable` | `trigger_id` | — | 비활성화 (조건 충족해도 실행 안 됨) |
| `status` | (없음) | — | 시스템 전체 상태 (폴러·스케줄러·자동응답) |
| `history` | (없음) | `trigger_id`, `limit` | 실행 이력 (성공·실패·결과) |

### `type` 4종

| type | 발화 조건 | config 필드 |
|---|---|---|
| `schedule` | 시간·반복 | `repeat` (daily/weekly/monthly/once), `time` ("HH:MM"), `date`, `weekdays`, `month`, `day`, `interval_hours` |
| `channel` | 외부 메시지 수신 (Gmail·Nostr 등) | `channel` (gmail/nostr), `from`, `keyword`, `subject_contains` 등 — channel_poller 규칙 |
| `webhook` | 외부 HTTP 호출 | (stub) |
| `file` | 파일 변경 감지 | (stub) |

> `webhook` / `file`은 아직 stub 상태(인터페이스만 존재). 실용 발화는 `schedule`·`channel` 두 가지.

---

## `[self:switch]{op}` — 2 op

| op | 필수 | 결과 |
|---|---|---|
| `list` | (없음) | 등록된 모든 스위치 (활성/비활성·타입·이름) |
| `run` | `switch_id` | 즉시 실행 (예약 무시) |

> 스위치 **등록**은 IBL 액션이 아니라 DB(`data/switches.json`) 직접 편집 또는 런처 UI를 통한다. 시스템 AI가 새 스위치를 만들고 싶다면 switches.json을 읽고/편집하면 된다 — [[architecture_ibl_action_criteria]]의 모드 3(IBL 없음, 어드민 영역).

---

## 표준 워크플로우

### 1) 매일 정해진 시간에 작업 실행 (가장 흔한 패턴)

```
[self:trigger]{op:"create", trigger_id:"morning_news",
  type:"schedule",
  config:{repeat:"daily", time:"08:00"},
  pipeline:'[sense:search_news]{query:"AI"} >> [others:channel_send]{channel:"gmail", to:"me", subject:"오늘의 AI 뉴스"}'
}
```

### 2) 평일만, 특정 요일만

```
config:{repeat:"weekly", weekdays:["mon","tue","wed","thu","fri"], time:"09:00"}
config:{repeat:"weekly", weekdays:["sat","sun"], time:"10:00"}
```

### 3) 매월 N일

```
config:{repeat:"monthly", day:1, time:"00:30"}
```

### 4) N시간마다

```
config:{repeat:"daily", interval_hours:6, time:"00:00"}
```

### 5) 한 번만 (특정 날짜)

```
config:{repeat:"once", date:"2026-06-15", time:"14:00"}
```

### 6) 채널 메시지 수신 → 자동 응답

```
[self:trigger]{op:"create", trigger_id:"gmail_alert_keyword",
  type:"channel",
  config:{channel:"gmail", subject_contains:"긴급"},
  pipeline:'[limbs:notify_user]{message:"긴급 메일 도착"}'
}
```

### 7) 스위치를 부르는 트리거

먼저 `switches.json`에 스위치를 등록(또는 런처 UI로). 그 다음:
```
[self:trigger]{op:"create", trigger_id:"morning_routine",
  type:"schedule",
  config:{repeat:"daily", time:"07:30"},
  pipeline:'[engines:run_switch]{switch_id:"daily_briefing"}'
}
```

스위치를 직접 실행할 때:
```
[self:switch]{op:"run", switch_id:"daily_briefing"}
```

---

## 운영 패턴

### 등록 → 확인 → 수정 → 비활성/삭제

```
[self:trigger]{op:"list"}                                       # 등록 상태 점검
[self:trigger]{op:"get", trigger_id:"morning_news"}             # 상세
[self:trigger]{op:"history", trigger_id:"morning_news", limit:10} # 실행 이력·실패 여부
[self:trigger]{op:"disable", trigger_id:"morning_news"}          # 잠시 멈춤
[self:trigger]{op:"enable", trigger_id:"morning_news"}           # 재개
[self:trigger]{op:"update", trigger_id:"morning_news", config:{repeat:"daily", time:"09:00"}}
[self:trigger]{op:"delete", trigger_id:"morning_news"}
```

### 시스템 헬스 점검

```
[self:trigger]{op:"status"}
→ poller(channel) / scheduler(calendar) / auto_response 모듈 상태 한꺼번에
```

`history`가 자주 실패면 pipeline 안의 액션이 깨졌을 가능성. self_check 결과와 교차 점검.

---

## 디자인 원칙

1. **pipeline은 가능한 한 짧게.** 한 트리거가 5단계 이상이면 스위치로 빼고 트리거는 호출만.
2. **이름은 의도가 보이게.** `trg_xyz` 같은 자동 ID보다 `morning_news`, `weekend_summary` 같은 의도형.
3. **schedule trigger는 calendar_manager에 자동 동기화.** 즉 트리거를 만들면 캘린더 이벤트도 생긴다. `show_calendar`로 확인 가능.
4. **channel trigger는 channel_poller 폴러에 등록.** 폴러가 안 돌면 발화 안 함. status로 확인.
5. **테스트는 once 또는 직접 호출로.** 새 트리거 만들고 schedule을 1분 뒤로 잡거나, 같은 pipeline을 `run_pipeline`으로 직접 실행해서 결과부터 검증.

---

## 자주 하는 실수

- **pipeline 없이 create**: 에러. pipeline은 필수.
- **type=schedule인데 time/repeat 누락**: 기본값(`daily`, `09:00`)이 들어가지만 의도와 다를 수 있음.
- **trigger_id 이름 충돌**: create 시 같은 이름이면 새 trigger_id가 자동 발급되어 중복 등록됨. list로 확인 후 등록.
- **disable과 delete 혼동**: 일시 정지는 disable, 영구 제거는 delete.
- **스위치를 IBL로 만들려는 시도**: 스위치 등록은 IBL 액션 없음. switches.json 직접 편집.

## 관련

- [[architecture_ibl_action_criteria]] — 모드 3(IBL 없음, 어드민) — 스위치 등록이 여기 해당
- `data/event_triggers.json` — 트리거 저장 파일 (수동 검토용)
- `data/switches.json` — 스위치 등록 파일
