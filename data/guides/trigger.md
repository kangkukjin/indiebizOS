# 트리거·스위치 가이드

`[self:trigger]` · `[self:switch]` 두 단일 액션으로 자동 실행 작업을 등록·관리한다. 둘 다 "조건 충족 시 IBL 문장 실행"이라는 점은 같지만 **트리거는 push (외부 조건)**, **스위치는 pull (사용자 또는 다른 트리거가 호출)** 이다.

`[self:schedule]` (지연·1회·반복 예약) · `[self:manage_events]` (캘린더 이벤트, `do` 로 실행 이벤트)는 별도 액션 — 규약은 `scheduler_guide.md`. 세 어휘의 공통 규칙은 아래 "발화 규칙" 절.

---

## 핵심 구분: 트리거 vs 스위치

| | 트리거 | 스위치 |
|---|---|---|
| 실행 시점 | 조건(시간·메시지·웹훅·파일) 충족 시 자동 | 사용자 또는 트리거가 명시적으로 호출 |
| 등록 단위 | 조건 + do(문장) 묶음 | 이름이 붙은 문장 (재사용용) |
| 비유 | 알람·자동응답 | 매크로·단축키 |
| 예 | "매일 8시 뉴스 요약" | "오늘 일정 정리해서 메일" 스위치 |

조합 패턴: 자주 쓰는 작업을 **워크플로우**(`[self:workflow]{op:"save"}`)나 스위치로 등록 → 그것을 부르는 **트리거**를 별도로 등록. 트리거 안에서 직접 문장을 적어도 되지만, 분리하면 수동 실행도 가능해진다.

---

## `[self:trigger]{op}` — 9 op

| op | 필수 | 선택 | 설명 |
|---|---|---|---|
| `list` | (없음) | `type` (필터) | 등록된 모든 트리거 — items 통화(`>> [table:filter]` 가능), `runnable`/`problem` 동반 |
| `detail` | `id` | — | 트리거 상세(저장된 do 원문 포함) |
| `create` | `name`, `do` | `cron` 또는 `config`, `enabled`, `type` | 새 트리거 |
| `update` | `id` | `cron`/`config`/`do`/`enabled`/`name` | 필드 수정 (캘린더 이벤트도 따라온다) |
| `delete` | `id` | — | 영구 삭제 (캘린더 이벤트도 삭제) |
| `enable` / `disable` | `id` | — | 켜기 / 끄기 (조건 충족해도 실행 안 됨) |
| `status` | (없음) | — | 시스템 전체 상태 (폴러·스케줄러·자동응답) |
| `history` | (없음) | `id`, `limit` | 실행 이력 — 행마다 `time`·`success`·`error`·`count`·`result_summary` |

### 시각 지정 — cron 이 정본

| 뜻 | cron | 해소 |
|---|---|---|
| 매일 09:00 | `0 9 * * *` | daily 09:00 |
| 평일 09:00 | `0 9 * * 1-5` (또는 `mon-fri`) | weekly 월~금 |
| 월·수·금 18:30 | `30 18 * * 1,3,5` | weekly |
| 토·일 10:00 | `0 10 * * 6,0` (cron 요일 0=일) | weekly |
| 매월 1일 00:30 | `30 0 1 * *` | monthly |
| 매년 6월 15일 09:00 | `0 9 15 6 *` | yearly |
| 2시간마다 | `0 */2 * * *` | interval 2h — **분은 0 만**(`30 */2` 는 거절: 간격 반복엔 분 자리가 없다) |
| 매시 정각 | `0 * * * *` | interval 1h |

지원하지 않는 것(정직 거절): 매분 `* * * * *`·`*/N` 분(→ `[self:schedule]{seconds|minutes}`), 일+요일 동시 지정.

`config` 를 직접 쓸 수도 있다 — 입구가 정규화·검증한다: `repeat` ∈ `daily/weekly/monthly/yearly/none/interval`(`once` 는 `none` 으로), `weekdays` 는 `0=월..6=일`(`mon..sun` 도 됨), 1회는 `none` + `date`, `interval` 은 `interval_hours` 필수, `time` 은 `HH:MM`. 검수(dry-run)도 같은 파서로 cron/config 를 먼저 판정한다.

### `type` 4종

| type | 발화 조건 | 지정 |
|---|---|---|
| `schedule` | 시간·반복 | `cron` 또는 `config` |
| `channel` | 외부 메시지 수신 (Gmail·Nostr 등) | `config:{channel, from, keyword, subject_contains …}` — channel_poller 규칙 |
| `webhook` | 외부 HTTP 호출 | (stub) |
| `file` | 파일 변경 감지 | (stub) |

> `webhook` / `file`은 아직 stub 상태(인터페이스만 존재). 실용 발화는 `schedule`·`channel` 두 가지.

---

## 발화 규칙 (trigger · schedule · manage_events 공통 — 2026-09-02 54회차)

1. **등록한 프로젝트에서 돈다.** 트리거·스케줄·실행 이벤트는 등록 시 프로젝트를 싣고, 발화가 그 프로젝트 경로에서 실행된다 — `do` 안에 `project_id` 를 손으로 쓸 필요가 없다. (시스템 AI 가 자기 자리에서 등록한 것은 시스템 AI 의 것.)
2. **`do` 속 `$변수`는 등록 시점 값으로 굳는다.** `$q = [sense:stock]{…}` 뒤에 `do:"[self:write]{content:'$q.items.0.current_price'}"` 를 등록하면 저장본은 `content:'253000.0'` 이다. 발화 시점의 값이 필요하면 **조회를 do 안에** 넣어라.
3. **반복형은 오늘 예정 시각이 지났으면 내일부터.** "매일 9시"를 15시에 등록하면 15시에 돌지 않고 내일 9시에 처음 돈다. 따라잡기는 등록 전의 결번(그 분에 몸이 죽어 있던 날)에만. 1회 예약(`[self:schedule]{at}`)의 지난 시각은 등록 거절.
4. **결과는 알림함으로.** 발화 성공·실패 모두 알림(`스케줄 실행 완료/실패`, `예약 실행 완료/실패`)이 온다. 소유 **에이전트**가 있는 스케줄은 창을 열어 채팅에서 "보이는 실행"으로 돈다.
5. **이력은 통화다.** `[self:trigger]{op:"history", id} >> [table:filter]{where:"success == false"} >> [table:select]{columns:["time","error"]}`. 트리거 레코드의 `run_count`·`last_run`·`last_success` 도 발화마다 갱신된다.
6. **같은 분에 여러 건이 due 여도 전부 돈다.**
7. 인용은 안쪽으로 갈수록 `"` → `'` → `\"` (3중까지 실측 무손상): `do: "[sense:feed]{url: '…'} >> [table:each]{do: '[self:write]{path: \"…\", content: \"$it.title\"}'}"`.

---

## `[self:switch]{op}` — 2 op

| op | 필수 | 결과 |
|---|---|---|
| `list` | (없음) | 등록된 모든 스위치 (활성/비활성·타입·이름) |
| `run` | `switch_id` | 즉시 실행 (예약 무시) |

> 스위치 **등록**은 IBL 액션이 아니라 DB(`data/switches.json`) 직접 편집 또는 런처 UI를 통한다 — [[architecture_ibl_action_criteria]]의 모드 3(IBL 없음, 어드민 영역).

---

## 표준 워크플로우

### 1) 매일 정해진 시간에 작업 실행 (가장 흔한 패턴)

```
[self:trigger]{op:"create", name:"morning_news", cron:"0 8 * * *",
  do:"[sense:search]{source: 'gnews', query: 'AI'} >> [others:channel_send]{channel: 'gmail', to: 'me', subject: '오늘의 AI 뉴스'}"}
```

### 2) 평일만, 특정 요일만

```
cron:"0 9 * * 1-5"        # 평일 09:00
cron:"0 10 * * 6,0"       # 토·일 10:00
```

### 3) 매월 N일 / 매년

```
cron:"30 0 1 * *"         # 매월 1일 00:30
cron:"0 9 15 6 *"         # 매년 6월 15일 09:00
```

### 4) N시간마다

```
cron:"0 */6 * * *"        # 6시간마다 (분은 0 만)
```

### 5) 한 번만 (특정 날짜) — 트리거 대신 `[self:schedule]`

```
[self:schedule]{date:"2026-06-15", time:"14:00", do:"…"}     # 지난 시각이면 거절
[self:schedule]{minutes:10, do:"…"}                           # 잠깐 뒤
```

### 6) 채널 메시지 수신 → 자동 응답

```
[self:trigger]{op:"create", name:"gmail_alert_keyword", type:"channel",
  config:{channel:"gmail", subject_contains:"긴급"},
  do:"[self:notify_user]{message: '긴급 메일 도착'}"}
```

### 7) 워크플로우·스위치를 부르는 트리거

```
[self:workflow]{op:"save", name:"아침브리핑", do:"…"}
[self:trigger]{op:"create", name:"morning_routine", cron:"30 7 * * *", do:"[self:workflow]{op: 'run', name: '아침브리핑'}"}
[self:trigger]{op:"create", name:"switch_call", cron:"30 7 * * *", do:"[self:switch]{op: 'run', switch_id: 'daily_briefing'}"}
```

---

## 운영 패턴

### 등록 → 확인 → 수정 → 비활성/삭제

```
$t = [self:trigger]{op:"create", name:"morning_news", cron:"0 8 * * *", do:"…"}
[self:trigger]{op:"detail", id:"$t.trigger.id"}                 # 저장된 do 원문 확인
[self:trigger]{op:"list"} >> [table:filter]{where:"enabled == true"} >> [table:select]{columns:["name","last_run","run_count"]}
[self:trigger]{op:"history", id:"$t.trigger.id", limit:10} >> [table:filter]{where:"success == false"}
[self:trigger]{op:"update", id:"$t.trigger.id", cron:"0 9 * * *"}
[self:trigger]{op:"disable", id:"$t.trigger.id"} · {op:"enable"} · {op:"delete"}
```

### 시스템 헬스 점검

```
[self:trigger]{op:"status"}
→ poller(channel) / scheduler(calendar) / auto_response 모듈 상태 한꺼번에
```

`history`가 자주 실패면 do 안의 액션이 깨졌을 가능성 — `list` 의 `runnable:false`/`problem`(어휘 은퇴 pre-flight)과 교차 점검.

---

## 디자인 원칙

1. **do 는 가능한 한 짧게.** 한 트리거가 5단계 이상이면 워크플로우로 빼고 트리거는 호출만.
2. **이름은 의도가 보이게.** `trg_xyz` 같은 자동 ID보다 `morning_news`, `weekend_summary` 같은 의도형.
3. **schedule trigger는 calendar_manager에 자동 동기화.** 트리거를 만들면 캘린더 이벤트(`[IBL] 이름`)도 생기고 update/enable/disable/delete 가 따라온다. `[self:manage_events]{op:"list"}`로 확인 가능.
4. **channel trigger는 channel_poller 폴러에 등록.** 폴러가 안 돌면 발화 안 함. status로 확인.
5. **테스트는 `[self:schedule]{seconds}` 나 직접 호출로.** 같은 문장을 먼저 직접 실행해 결과부터 검증하고, 잠깐 뒤 발화는 `seconds`/`minutes` 지연으로.

---

## 자주 하는 실수

- **do 없이 create**: 에러. do 는 필수.
- **옛 `config` 형태(1회를 once 로, 요일을 이름으로)**: 입구가 정규화하지만, cron 이 더 짧고 검수도 본다.
- **분 단위 반복을 트리거로**: 거절. `[self:schedule]{seconds|minutes}` 또는 `[repeat: …, every]`.
- **이름 충돌**: create 시 같은 이름이면 새 id 가 발급되어 중복 등록됨. list로 확인 후 등록.
- **disable과 delete 혼동**: 일시 정지는 disable, 영구 제거는 delete.
- **스위치를 IBL로 만들려는 시도**: 스위치 등록은 IBL 액션 없음. switches.json 직접 편집.

## 관련

- [[architecture_ibl_action_criteria]] — 모드 3(IBL 없음, 어드민) — 스위치 등록이 여기 해당
- `scheduler_guide.md` — 캘린더/스케줄 규약(repeat 표·요일 코드·첫 발화 규칙)
