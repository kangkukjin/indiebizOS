# 상상 훈련 75회차 결과보고서 (2026-09-28) — 시간·발신 문형: 예약·트리거·캘린더 실행 이벤트·검침·조건 알림·발신

훈련 턴 · **무수정**(가이드 §4-3: 훈련 턴은 라이브 코어를 고치지 않는다). 아래 갭 원장은 [before.json](before.json)·[baseline.json](baseline.json)과, 셸로 직접 확인한 원장·설정 파일 상태만으로 썼다. 집행 완료 절은 비워 두었다.

## 축 선정

- 축 = 행동 기준에서 **조합 수가 0인 두 문형**(시간·발신)이다. 액션은 `self:schedule`·`self:trigger`·`self:manage_events`·`self:time`·`table:since`·`self:notify_user`·`others:channel_send`·`others:messages`·`others:ask`. 도메인:
  - 매일 아침 AI 팁 보고서, 매주 월요일 청주 전세·실거래 알림
  - 강의 전날 준비물 알림, 가계부 월초/월말 결산, 결혼기념일 전날
  - 주가 임계값 알림, "지난번 이후 새 글만" 검침
  - 가족에게 메일(check), 반복 예약의 일시정지·수정·삭제
  - 말일·윤년·KST 경계
- 축 선정 관문 질문("기계로 열거 가능한가"): 발화 시점 의미(어느 날 도는가, 몇 번 도는가, 취소되는가)는 실행 상태라 AST로 셀 수 없다. 그래서 훈련 축이다. 다만 발견 가운데 둘이 앞 회차와 같은 속이다.
  - 입구 무검증: B54-8 → B75-3
  - 검수↔실행 값 사각: F54-1 → B75-4
  - 둘 다 census로 넘기라고 적었다.
- 닫힌 밭은 밟지 않았다. 날짜 표기(check_datetime)는 보지 않았다. 윤년 `2027-02-29`는 정직 거절만 확인했다. 54회차에서 수리된 칸(발화 프로젝트 문맥·소유자·같은 분 다중 발화·등록 즉시 따라잡기·do→run_pipeline)은 재발견하지 않았다. T16·T17이 그 수리가 살아 있음을 확인했다.
- 탐침 표면: 모델 경로(`agent_id:"IT75_probe"`·`task_id:"IT75_task"`). 모든 요청이 `edition:2`·`project_id:"컨텐츠"`·`origin:"training"`이다.
  - ★**예외 — 발화할 수 있는 등록은 agent_id 없이(표면 기본값)** 보냈다. 셀프 스케줄의 소유 에이전트가 가짜 이름 `IT75_probe`가 되면 발화가 "보이는 실행"(창 열기·LLM 턴)으로 가기 때문이다(`system_ai_plans._execute_schedule` — agent_id가 `system_ai`가 아니면 owner_agent가 된다). 표면 기본값이면 소유 에이전트가 비고, 등록 프로젝트에서 직접 실행된다(54회차 B54-2 수리 경로).
- ★**등록은 원칙적으로 check만** 했다.
  - 등록 계약(저장 레코드·캘린더 거울)을 봐야 하는 과제만 `IT75_` 스크래치로 등록하고, 그 자리에서 지웠다.
  - "그 등록이 언제 도는가"는 **실제 저장 레코드를 발화 판정 함수 `CalendarManagerBase._should_run_task`에 넣는 격리 재현**으로 봤다. 라이브 스케줄러를 거치지 않아 발화 없이 한 달 치 판정을 본다.
  - 발화 실측은 두 건만 했다(T14·T15, 본문 `[self:time]{}`).
- 탐침 전에 알림함·트리거·이력·캘린더·건강 원장·notify_log·시스템 AI 대화·since 원장을 기준선으로 떠 두고, 회차 뒤 대조했다([baseline.json](baseline.json)).

## 지표 스냅샷 (훈련 전)

행동 미조합 140/168 · 파이프 길이 중앙값 3 · 문형 4(조회 26·축적 8·적용 6·조건 2, **시간·발신 0**) · 단발 문형(축적 4·조회 3·시간 1·발신 1) · 파트너 다양성 중앙값 2. 74회차와 같다. 원본은 [metrics.json](metrics.json). 지표는 몸의 현황이며, 훈련 실측은 증류에 담기지 않는다(§6).

## 과제 표

원문·판정식: [probe.py](probe.py) · 응답 전량: [before.json](before.json)(요청·응답 75건) · 기준선과 회차 후 diff: [baseline.json](baseline.json).

**24과제 중 기계 판정 13통과 · 11실패.** 결함 6부류 · 마찰 4부류 · 문법 후보 1 · 어휘 후보 1. 실행 20 · check만 4(T03·T05·T22·T24).

탐색 중 훈련자 문장 잘못은 결함 판정에서 뺐다. T21 첫 시도에서 `[if]` 가지 안 두 문장 사이에 `;`를 빠뜨렸다("문장 사이에는 줄바꿈 또는 ;이 필요합니다" — 오류가 정확히 방향을 줌). 고쳐서 다시 찍었다.

| # | 상상 의도 | 결과 | 분류 |
| --- | --- | --- | --- |
| T01 | 켜진 트리거 중 마지막 실행이 실패한 것만 (list → filter → select) | 1건: `AI시대_보고서출처_뉴스갱신` run_count 302 | 깨끗(F75-2 단서) |
| T02 | 주간 재조사(부동산) 트리거가 몇 번 돌았고 이력에 몇 줄 남았나 | `run_count 4` · `history 1행`. 전역 이력 200행 중 172행을 매시 실패 트리거 하나가 차지(7일 창) | 마찰 F75-1 |
| T03 | 매주 월요일 7시 청주 새 전세만, 있으면 알림 (trigger + since + if, check) | 바깥·안쪽 모두 `incomplete`·이슈 0 — do는 검사되지 않음 | 검수만(B75-4) |
| T04 | 코퍼스 형태 `feed >> since >> notify_user` 트리거 등록 | 안쪽 단독 check = `PIPE_COLLISION`. 트리거 create check = `incomplete`, **등록은 success**. `list`가 `runnable:false`로 사후 적발 | 결함 B75-4(+B73-1) |
| T05 | 강의 전날 20시 준비물(1회 schedule) · 매주 월 20시(cron) | 둘 다 `incomplete` | 검수만 |
| T06 | 강의 날짜마다 전날 계산 | `$d - 1` 산술 거절 · `date_add` 없는 내장 함수 · `split` 우회 `2026-10-5`(0 채움 없음)·**`2026-11-01` → `2026-11-0`** | 불가 G75-1 |
| T07 | 매월 1일 00:30 지난달 가계부 결산 (cron `30 0 1 * *`, 가이드 예시) | 저장 `{repeat:monthly, day:1, date:null}` → 판정 **9-29·9-30·10-01·10-02·10-15·10-31·11-30·2-28 전부 발화** | 결함 B75-1 |
| T08 | 매월 말일 21시 결산 — cron `31`/`L`/`28-31` · date형 10-31 | check는 셋 다 `incomplete`(옛 validate·실행은 `L`·`28-31` 거절). date형 monthly 10-31 → 10-31·12-31만, **11-30·2-28 건너뜀** | 불가 V75-1(+B75-4) |
| T09 | `schedule{repeat:"monthly", time:"09:00"}` | success "반복 스케줄 등록됨 (monthly, 09:00)" · 저장 date·day null → **매일 발화** | 결함 B75-1 |
| T10 | 매주 월 7시 — weekdays 없음 / `["mon"]` / `[0]` | 셋 다 success. 없음·`["mon"]`은 **영원히 안 돎**, `[0]`만 10-05 발화 | 결함 B75-3 |
| T11 | 결혼기념일 전날 매년 9시 — manage_events·schedule(date형) · trigger cron `0 9 12 12 *` | date형 둘은 12-12에 **안 돎**(매년 전부 False). cron형만 12-12 발화 | 결함 B75-3(B75-1 뿌리) |
| T12 | repeat `"매일"`·`"weekday"`·`"once"` | 셋 다 success로 **원문 저장**, 발화 0. 트리거 config `repeat:"매일"`은 check `incomplete`(런타임은 거절) | 결함 B75-3(+B75-4) |
| T13 | 지금 시각·요일·시간대, 윤년 | `2026-09-28 23:01:28` · `%A %Z %z` → `"Monday  "`(시간대 빈칸) · `2027-02-29` 정직 거절 | 깨끗(F75-4) |
| T14 | 40초 뒤 예약 → event_id로 삭제(취소) → 발화하나 (발화 실측) | 삭제 success·이벤트 사라짐. **40초 뒤 그대로 실행**(action_health usage/scheduler 1행, 알림 "예약 실행 완료 — 컨텐츠") | 결함 B75-2 |
| T15 | 2분 뒤 한 번 — 틱이 타이머보다 먼저 오는 분 (발화 실측) | **2회 실행**: 23:06:48(틱, "스케줄 실행 완료 — 컨텐츠/") · 23:06:55(타이머, "예약 실행 완료 — 컨텐츠") | 결함 B75-2 |
| T16 | 아침 알림 끄기 → 켜기 → 9시→10시 → 삭제 (스크래치 트리거) | 캘린더 거울 `enabled` false→true, time 10:00, 이벤트 1개 유지, 삭제 후 0 | 깨끗 |
| T17 | schedule로 건 강의 알림을 manage_events로 21시·새 문장으로 | 저장 time 21:00·run_pipeline·do 판본 2 고정 · 10월 list에서 되읽기 | 깨끗 |
| T18 | 지난번 이후 새 글만, 있을 때만 알림 (판본 2 `$n = … >> since` + `[if: len($n.items) > 0]`) | 1회 기준선(alert false) · 2회 새 1건 · 3회 0건 | 깨끗 |
| T19 | 새 글 알림 단계가 실패하면 다음 검침에 다시 오나 | 실패 뒤 다음 검침 **새 것 0 — 영구 유실**. peek → 실패 → 다음 검침은 1건(우회 성공) | 결함 B75-5 |
| T20 | 매물 0건인 동네 감시 시작 → 첫 매물 | 0행 첫 검침 `seeded:true`(기준선 0행) → 첫 매물 호출이 **또 "첫 검침"**, n 0 | 결함 B75-6 |
| T21 | 삼성전자가 20만원 넘으면 알려줘 (조회 실측 + if 알림) | `"알림"` — 270,000원으로 조건 충족, 알림 제목 파생 정상(회차 유일 실발신 — 삭제) | 깨끗 |
| T22 | 가족신문 새 판 → 엄마에게 메일, 실패하면 나에게 (check) · 가이드 형태 | `?? notify_user` `incomplete`. `channel:"gmail", to:"me"` `incomplete`(핸들러는 `channel` 안 읽음). `search >> channel_send` `PIPE_COLLISION`. `others:ask` `incomplete` | 검수만(F75-3·B73-1) |
| T23 | 안 읽은 메시지가 있는 대화 몇 개 (inbox → filter) | 대화 10 · 미독 2(이름 미수록) | 깨끗 |
| T24 | 점검 끝 자기 알림 | T21이 1건을 썼으므로 check로 강등 — `incomplete` | 검수만 |

조회·되읽기·수정 쪽은 튼튼했다. 트리거 목록·이력 되읽기, disable/enable/update/delete의 캘린더 거울 동기, schedule 예약을 manage_events로 옮기기, 판본 2 since+if 조건 알림, 주가 임계값 알림, 받은편지함 집계가 모두 통과했다. 실패는 네 자리에서 났다.
1. **캘린더 반복 규칙의 쓰는 쪽/읽는 쪽 키 계약**(monthly는 date, yearly는 month/day, 입구마다 다른 키)
2. **지연 예약의 두 실행기**(타이머 + 백업 이벤트)
3. **판본 2 check의 시간 인자 사각**
4. **검침 원장의 커밋 시점**

## 갭의 원장

### B75-1 ★최우선 — 매월 반복이 **매일 발화**하고, date만 준 매년 반복은 **영원히 안 돈다** (반복 규칙의 키 계약이 쓰는 쪽·읽는 쪽에서 어긋남)

- **요약**: 발화 판정 `calendar_manager._should_run_task`는 repeat마다 읽는 키가 다르다.
  - monthly(609~625행): `task.get("date")`의 일자만 본다. date가 비면 **날짜 검사를 건너뛰고 last_run이 오늘이 아닌 한 True**다.
  - yearly(593~607행): `month`·`day`만 본다. 없으면 False다.
  - 쓰는 쪽은 입구마다 다르다.
    - 트리거 cron 매월은 `_cron_to_config`(131행)가 `{"repeat":"monthly","day":N}`를 내고, `_sync_schedule_trigger`가 `event_date=config.get("date")`(None)·`day=N`으로 저장한다(300·303행). 읽는 쪽은 `day`를 모른다.
    - `[self:schedule]{repeat:"monthly", time}`은 반복형이라 date를 채우지 않고 add_event에 month/day도 넘기지 않는다(384~396행).
    - manage_events·schedule의 yearly는 date만 싣는다(가이드 예시도 date형).
  - `normalize_schedule_config`(176행)도 monthly에 date/day를 요구하지 않는다. yearly에만 month/day를 요구한다(226행).
  - (보고서 저장 전 판정 함수의 monthly·yearly 가지를 직접 읽어 확인했다.)
- **최소 재현**(발화 없음 — 저장 레코드를 판정 함수에):
  1. `[self:trigger]{op:"create", name:"x", cron:"30 0 1 * *", do:"[self:time]{}"}` → `[self:manage_events]{op:"list"}`에서 `[IBL] x`의 `date`·`day` 확인 → 그 레코드로 `_should_run_task(task, 2026-10-15 00:31)`
  2. `[self:schedule]{repeat:"monthly", time:"09:00", do:"…"}` 같은 방식
  3. `[self:manage_events]{op:"create", title:"…", date:"2026-12-12", time:"09:00", repeat:"yearly", do:"…"}` → 12-12 09:01 판정
- **실측**:
  - T07 저장: `config={"repeat":"monthly","day":1,"time":"00:30"}` · 거울 이벤트 `{"repeat":"monthly","date":null,"day":1,"time":"00:30"}`
  - T07 판정: `fires_on=['2026-09-29','2026-09-30','2026-10-01','2026-10-02','2026-10-15','2026-10-31','2026-11-30','2027-02-28']` — 표본 8일 전부
  - T09 schedule monthly: 응답 `{"success":true,"message":"반복 스케줄 등록됨 (monthly, 09:00)"}` · 저장 date·day null · 같은 8일 전부 발화
  - T11 yearly date형(manage_events·schedule): `2026-12-12T09:01 False · 2027-12-12T09:01 False`. 같은 뜻의 cron `0 9 12 12 *`만 True
- **영향**:
  - "매월 1일 월간 리포트"·"매월 25일 카드 결제일 알림"·"매월 가계부 결산"을 가이드(trigger.md 표 "매월 1일 00:30 `30 0 1 * *`") 그대로 걸면 **다음 날부터 매일 돈다**. 보고서·위임이면 매일 LLM 비용이고, 알림이면 매일 거짓 알림이다.
  - 매년 기념일 전날 알림을 가이드 예시(date형)로 걸면 조용히 안 돈다.
  - 현재 사용자 원장에 실행형 monthly는 0건이라 피해는 아직 없다. 첫 등록부터 터진다.
- **뿌리**: 반복 규칙을 쓰는 입구 4곳(trigger cron/config·schedule·manage_events·REST)과 읽는 판정 하나 사이에 **반복 규칙의 정본 모양**이 없다. monthly는 date, yearly는 month/day라는 비대칭을 입구마다 다르게 채운다.
- **제안(수리성)**:
  1. 반복 규칙의 정본 모양을 하나로 정한다(monthly=`day`, yearly=`month`+`day`, weekly=`weekdays` 정수, 1회=`date`). `add_event`/`update_event` 한 곳에서 date → day/month/day로 파생·검증한다.
  2. 판정은 정본 키만 읽는다. 옛 레코드는 로드 때 한 번 이행한다(date만 있는 monthly/yearly → day/month).
  3. monthly의 `day` 29~31은 짧은 달에 대한 정책이 필요하다. 조용히 건너뛰지 말고, 정직하게 거절하거나 말일로 접는다. 정책 선택은 V75-1과 함께 적는다.
  - 가드: {trigger cron·config, schedule, manage_events create/update} × {monthly(day 1·15·31, date형), yearly(date형·month/day), weekly} → 한 달·한 해 표본일 판정 대조.

### B75-2 지연 예약이 **두 실행기**로 돈다 — 틱이 먼저 오면 두 번 실행되고, event_id로 지워도 타이머는 발화한다

- **요약**: `_execute_schedule` 지연 모드는 두 가지를 동시에 건다.
  - ①캘린더 백업 이벤트(`repeat:none`, 날짜·**분 단위** `HH:MM`, `run_pipeline`, enabled)(233행)
  - ②`threading.Timer`(303행)
  - 타이머 콜백 `_delayed_run`(258행)은 이벤트를 `enabled=False`로 바꾸려 할 뿐(265행), 이벤트가 이미 돌았는지·지워졌는지·꺼졌는지 확인하지 않고 `execute_scheduled`를 부른다(284행).
  - 스케줄러 틱은 이벤트의 분이 오면 1회성 판정(오늘·last_run 없음)으로 그대로 발화한다.
  - 반환 `event_id`가 유일한 취소 손잡이인데, 타이머 객체에는 닿지 않는다.
- **최소 재현**:
  - 이중: 틱 위상(최근 last_run의 초, 이번엔 48.1s)보다 뒤 초에 끝나도록 `[self:schedule]{seconds:<N>, do:"[self:time]{}"}` → 그 분의 틱과 타이머
  - 취소: `$s = [self:schedule]{seconds:40, do:"[self:time]{}"}` → `[self:manage_events]{op:"delete", event_id:$s.event_id}` → 40초 대기
- **실측**:
  - T15: `secs=175 target=23:06:56 event_time=23:06` → action_health `(23:06:48.70 usage scheduler)`·`(23:06:55.79 usage scheduler)` **2행**, 알림 `스케줄 실행 완료 — 컨텐츠/`(틱 경로)·`예약 실행 완료 — 컨텐츠`(타이머 경로) 2통, 이벤트 `enabled:false, last_run 23:06:48.42`
  - T14: `delete=True event_gone=True` 뒤 `23:03:36.62 usage scheduler` 1행 + 알림 `예약 실행 완료 — 컨텐츠`
  - 54회차 B1(5초 지연)은 틱이 그 몇 초 안에 떨어질 확률이 낮아 이 경로를 보지 못했다.
- **영향**:
  - "10분 뒤 알려줘"·"1시간 뒤 이 파일 저장"은 분 단위 지연이다. 등록한 초가 틱 위상보다 뒤면(대략 절반) **두 번 실행**된다. 알림 2통, 쓰기 2회, 외부 발신이면 2통이다.
  - "그 예약 취소해줘"는 표현할 수 없다. 지우면 목록에서 사라지고 성공이라 말하지만 실행은 그대로다.
  - 가이드("N분 후 실행" 패턴)는 이 형태를 권한다.
- **제안(수리성)**:
  1. 실행기를 하나로 한다(권장: 백업 이벤트를 발화의 정본으로 두고 초 단위 시각을 싣거나, 타이머를 정본으로 두고 백업 이벤트는 재기동 복구 전용 표지로).
  2. 타이머 콜백은 발화 직전 이벤트 존재·enabled·last_run을 잠금 안에서 확인하고 "내가 먼저"를 원자적으로 찍는다(compare-and-set).
  3. 이벤트 삭제·비활성화는 살아 있는 타이머를 취소한다(event_id → Timer 등록부).
  - 가드: {틱 먼저, 타이머 먼저} × {그대로, delete, toggle} → 실행 횟수 1/1/0/0.

### B75-3 schedule·manage_events 입구는 반복 설정을 **검증·정규화하지 않는다** — 영원히 안 도는 예약이 성공으로 등록된다 (★밭 이관: B54-8과 같은 속의 두 번째)

- **요약**: 54회차 B54-8 수리(`normalize_schedule_config` — 요일 이름 → 정수, `once` → `none`, repeat 집합, weekly는 weekdays 필수)는 **트리거 config 경로에만** 붙었다. `[self:schedule]`(`repeat`·`weekdays`를 그대로 `add_event`로)과 `[self:manage_events]` create/update(443·488행)는 받은 값을 저장한다.
- **최소 재현**: `[self:schedule]{repeat:"weekly", time:"07:00", do:"…"}`(weekdays 없음) · `weekdays:["mon"]` · `repeat:"매일"`·`"weekday"`·`"once"` · manage_events yearly date형
- **실측**:
  - T10: 셋 다 `"반복 스케줄 등록됨 (weekly, 07:00)"`. 발화는 `[0]`만 10-05, 없음·`["mon"]`은 표본 4일 전부 False
  - T12: `"반복 스케줄 등록됨 (매일, 09:00)"`·`(weekday…)`·`(once…)` — 저장 repeat 원문, 발화 0
  - T11: yearly date형 발화 0
  - 같은 값을 트리거 config로 주면 런타임은 거절한다(`normalize_schedule_config`).
- **영향**: 사람이 말하는 "매주 월요일"·"매일"·"한 번만"을 모델이 자연스럽게 옮긴 값이 성공 응답과 함께 캘린더에 쌓이고, 그날이 와도 아무 일도 없다. 응답 문구가 원문 repeat를 되풀이해("반복 스케줄 등록됨 (매일, 09:00)") 정상처럼 보인다.
- **제안(수리성, ★밭 이관)**: 개별 입구 수리가 아니다.
  1. 캘린더 쓰기 입구 전수 census(trigger create/update·schedule·manage_events create/update·REST `/scheduler/tasks`·goal 스케줄)를 한다.
  2. 정규화·검증을 `add_event`/`update_event` 한 곳으로 모은다(B75-1의 정본 모양과 한 벌).
  3. 관문: `calendar_events.json`에 쓰는 코드가 이 한 곳을 거치는지 AST로 확인한다.
  - 가드: {schedule, manage_events} × {weekly 없음·이름·정수, 한국어·미지 repeat, once, yearly date형} → 거절 또는 정규화 저장 + 판정 발화.

### B75-4 판본 2 `check:true`가 트리거·스케줄의 **cron·config 값과 do 문장을 보지 않는다** — 등록 런타임도 do를 검사하지 않는다 (★밭 이관: F54-1과 같은 속의 두 번째)

- **요약**:
  - 54회차 F54-1 수리는 옛 검수기 `/ibl/validate`(api_ibl.py 897행 `_check_trigger_schedule_params`)에 "실행기와 같은 파서로 cron·config 미리 판정"을 넣었다. 옛 검수기는 do 문자열도 `[trigger 속]`으로 재귀 검사한다.
  - 교재(`12_ibl_only.md`)가 모델에게 가르치는 판본 2 `check:true`에는 둘 다 없다. `self:trigger`·`self:schedule`·`others:channel_send`·`self:notify_user`는 `open_params:true`라 인자 이름도 안 본다.
  - 등록 런타임 `_create_trigger`는 do를 컴파일하지 않고 저장한다. `list`의 `runnable/problem`(preflight)이 사후에만 적발한다.
- **최소 재현**:
  - `return [self:trigger]{op:"create", name:"x", cron:"30 */2 * * *", do:"[self:time]{}"}`에 `check:true`
  - 같은 문장을 `/ibl/validate`(판본 1)로
  - do에 `… >> [self:notify_user]{…}`
- **실측**:
  - check `incomplete`·이슈 0: `30 */2 * * *`·`* * * * *`·`0 21 L * *`·`0 21 28-31 * *`(T08)·config `repeat:"매일"`(T12)·PIPE_COLLISION이 든 do(T03·T04)·`2026-02-29`(T13)
  - 옛 validate: `"cron/config: 간격형 cron('30 */2 * * *')은 분 0 만 지원합니다…"`·`"cron/config: 일은 숫자여야 합니다: '0 21 L * *'"` — valid:false
  - T04: 판본 2 do 안쪽 단독 check = `PIPE_COLLISION`인데 create는 success. `list` → `runnable:false, problem:"[{'code': 'PIPE_COLLISION', …"`
- **영향**: 모델이 교재대로 check로 확인하고 등록한 정기 작업이 **첫 발화 날 새벽에 처음 실패**한다. 예약 시각엔 사람이 없다. 54회차가 닫았다고 적은 사각이 판본 2 표면에서 다시 열려 있다.
- **제안(수리성, ★밭 이관)**:
  1. 옛 검수기에만 있는 액션별 사전 판정(`_check_trigger_schedule_params`·`[trigger 속]` do 재귀·`_condition_syntax_warning` 등)을 census한다.
  2. 판본 2 check의 액션 계약 확장점(선언 어댑터)으로 연결한다. 파서에 액션 이름을 넣지 않고, 사전의 "값 검사기·문장 인자" 선언으로 붙인다.
  3. `do`·`pipeline`처럼 **문장을 담는 인자**는 선언으로 표시하고, check가 같은 판본으로 재귀 컴파일한다.
  4. 등록 런타임도 같은 검사로 거절한다.
  - 관문: validate-parity를 판본 2 check까지 넓힌다(같은 입력에 옛/새 검수기 판정 대조).

### B75-5 `table:since`가 기준선을 **뒤 단계보다 먼저** 커밋한다 — 알림 단계가 실패하면 그 새 글은 영구히 사라진다

- **요약**: `op_since`는 새 행을 골라 낸 직후 `if not peek:`(134행)에서 모든 행을 seen으로 기록하고 `commit`(153행)한다. 같은 프로그램의 뒤 단계(알림·발신·쓰기)가 실패해도 되돌리지 않는다. 결과적으로 "지난번 이후 새 것 → 알림"은 **최대 한 번(at-most-once)**이고, 실패하면 0번이다.
- **최소 재현**: 기준선 `[{id:"a"}]` 뒤 `$n = [{id:"a"},{id:"b"}] >> [table:since]{key:K}` · `[if: len($n.items) > 0] { <실패하는 단계> }` → 다시 `$n = … >> [table:since]{key:K}; return len($n.items)`
- **실측**(T19):
  - 실패 단계 `[Errno 2] No such file…`로 프로그램 실패 → 다음 검침 `0` — `b`는 다시 안 온다
  - `peek:true`로 고르고 실패 → 다음 일반 검침 `1`(우회 성공)
- **영향**: 코퍼스 검침 문형(3910 `… >> since >> each{notify}`, 3980, 4097 `since` 뒤 `[if]{channel_send}`)은 전부 유실형이다. 트리거로 매일 돌 때 메일 서버 장애·릴레이 거부·권한 오류 하루면 그날의 새 매물·새 글 알림이 조용히 없어진다. 이력에는 실패 1줄만 남고, 다음 날은 "새 것 없음"이다.
- **제안(수리성)**: since의 기준선 갱신을 **프로그램 성공 시 커밋**으로 옮긴다. 실행 단위 보류 원장 → 성공 종료 때 확정, 실패·취소면 폐기. 기존 문장을 깨지 않는다(실패한 날의 새 것을 다음에 다시 보낼 뿐). 그 전까지는 교재에 "peek로 고르고 → 행동 → 같은 행으로 since 확정" 두 단계 관용구를 적는다.
  - 가드: {뒤 단계 성공, 실패, 취소} × {peek 없음, peek → 확정} → 다음 검침의 새 행 수.

### B75-6 0행 첫 검침은 기준선을 남기지 않는다 — 첫 매물·첫 글이 **또 기준선으로 삼켜진다**

- **요약**: `first_run = not seen`(110행) — "첫 검침"을 스트림 원장에 행이 있느냐로 판정한다. 첫 호출이 0행이면 아무것도 기록되지 않아 다음 호출도 "첫 검침"이고, 그 호출의 행이 새 것이 아니라 기준선이 된다(`seeded:true`).
- **최소 재현**: `[] >> [table:since]{key:K, by:"id"}` → `[{id:"m1"}] >> [table:since]{key:K, by:"id"}`
- **실측**(T20):
  - 1회 `{"n":0,"seeded":true,"note":"첫 검침 — 기준선 0행 저장…"}`
  - 2회 `{"n":0,"seeded":true,"note":"첫 검침 — 기준선 1행 저장…"}` — "0행 저장"이라 말하고 실제로는 아무것도 저장하지 않았다
- **영향**: "아직 매물이 없는 동네에 새 매물 나오면 알려줘"·"새로 만든 게시판에 첫 글 오면 알려줘" — 감시가 가장 필요한 순간(0 → 1)에 침묵한다. 15회차 B15-2 판정(첫 검침 = 기준선)의 경계 사례다. 판정 자체를 뒤집지 않고 고칠 수 있다.
- **제안(수리성)**: 스트림 자체의 첫 관측 표지(스트림 행 또는 메타 테이블)를 0행일 때도 남긴다. note 문구는 실제 저장 행 수와 맞춘다.
  - 가드: {0행 → 1행, 0행 → 0행 → 1행, N행 → N+1행}.

### F75-1 트리거 이력이 **전역 200행 하나**를 나눠 쓴다 — 자주 도는 트리거가 드문 트리거의 이력을 밀어낸다

- `trigger_engine.add_history`: `data["history"] = history[-200:]`(372행)
- T02: 이력 원장 200행 중 `[IBL] AI시대_보고서출처_뉴스갱신` 172 · `ai_trend_report_daily` 7, 창 `2026-09-21 08:27 ~ 09-28 22:13`(7일). 주간 재조사 `forage_resurvey_부동산`은 `run_count 4`인데 `history` 1행이다.
- 가이드가 가르치는 `history >> filter{success == false}`는 주간·월간 트리거에서 지난 실패를 거의 볼 수 없다. 매시 트리거 하나가 실패로 돌면 7일 창도 짧아진다.
- 제안(수리성): 트리거별 상한(예: 트리거당 N행 + 전역 상한), 또는 SQLite 원장으로 옮기고 레코드에 `last_error`를 동반한다. 요약 필드(`run_count`)와 이력 행 수가 어긋나면 응답에 `truncated`를 싣는다.

### F75-2 같은 영구 실패가 **매시 경고 알림**을 낸다 — 11일 273통, 억제·요약·백오프 없음

- 실사용 증거(74회차 단서, 읽기만):
  - 트리거 `AI시대_보고서출처_뉴스갱신`(`interval_hours:1`, 프로젝트 홍보)의 이력 172행이 전부 실패다.
  - notify_log의 `스케줄 실행 실패 — 홍보/`는 **273통**(09-15 21:17 ~ 09-28 22:13, 09-17부터 하루 18~24통).
  - 같은 트리거의 성공 알림은 09-17 03:30이 마지막이다.
- 실패 원인(읽기만 — 수리 금지): 워크플로우 2단계 `[self:script]{id:"AI시대뉴스동기화"}` `status` op가 `success: not errors and not issues`를 반환한다(`data/scripts/ai_era_news.py` 278행). `last_prepare.issues`에 과거 보고서 7일치(09-17·18·19·21 "출처 절 누락", 09-23·26·27 "완료 보고서 또는 검증 출처 목록 누락")가 남아 있어 **새 일이 없어도 매번 실패**한다(`candidates 55 · done 55 · pending_count 0`). 과거 보고서가 고쳐지기 전까지 스스로 낫지 않는 실패다.
- 영향: 알림함(deque 100)을 이 경고가 채워 다른 알림을 밀어낸다(하루 24통). 사용자는 같은 경고에 무뎌진다. 알림이 "실패의 시작"을 알리지 못하고 소음이 된다.
- 제안(수리성): 같은 트리거·같은 오류 서명의 연속 실패는 첫 1통 + 요약(예: "N회 연속, 마지막 시각")으로 접는다. 성공으로 돌아오면 회복 1통. 트리거 레코드에 `consecutive_failures`를 싣는다. 자동 비활성화는 하지 않는다(사용자 작업을 끄는 것은 파괴적 — 필요하면 판정).

### F75-3 `trigger.md` 표준 워크플로우가 **읽히지 않는 인자**와 판본 2에서 막히는 파이프를 가르친다 (교재 드리프트)

- 가이드 "1) 매일 정해진 시간에 작업 실행 (가장 흔한 패턴)": `[sense:search]{…} >> [others:channel_send]{channel: 'gmail', to: 'me', subject: '오늘의 AI 뉴스'}`
  - ①`channel_engine.execute_channel_action`은 `params.get("channel_type")`만 읽는다(345행). `channel_send` 선언에는 `channel` 별칭이 없고 `open_params:true`라 check도 침묵한다(T22 `incomplete`). `channel_type`이 비면 `_default_channel_for("me")`가 **nostr 우선**으로 고르므로, "gmail로"라는 말이 조용히 다른 채널이 될 수 있다.
  - ②판본 2에서 `… >> [others:channel_send]`는 `PIPE_COLLISION`이다(T22, B73-1).
  - ③본문(`body`) 없이 제목만 준다.
- 제안(수리성): 가이드 예시를 판본 2 형태(`$r = …` → `channel_type`·`body` 명시)로 고친다. `channel`은 선언 별칭으로 흡수하거나 거절한다. 은퇴 형태(`channel:'gmail'`)는 `data/retired_contracts.yaml`에 등록한다(§4-3 교재 수리는 표면 전수).

### F75-4 `self:time`은 "KST"라고 선언하지만 시간대 표지가 없다

- T13: `format:"%A %Z %z"` → `"Monday  "`(`%Z`·`%z` 빈칸, 순진한 로컬 시각). 요일은 영어다.
- 선언은 "로컬 시스템 시계, KST"다. 몸이 다른 시간대의 기기(여행 중 노트북, 이웃 몸)에서 돌면 KST라는 말이 거짓이 된다. 시각 문자열을 다른 몸·외부 서비스에 넘길 때 기준을 알 수 없다.
- 제안(수리성): 반환에 시간대(오프셋)를 싣거나 선언을 "로컬 시계(시간대 표지 없음)"로 바로잡는다. 요일은 `format`으로 한국어 선택지를 준다(이것은 교재 한 줄로 충분).

### G75-1 (판정 요청) 날짜 산술이 없다 — "전날"·"지난달"·"N일 뒤"를 식으로 못 구한다

- T06:
  - `$d - 1` → "산술에는 관측 가능한 유한 숫자가 필요합니다."
  - `date_add` → "알 수 없는 내장 함수"
  - 문자열 우회 `split($d,"-")` → `2026-10-5`(0 채움 없음)·**`2026-11-01` → `2026-11-0`**(월 경계에서 틀림)
- 공통 값 연산 표(2026-09-27)에 날짜 함수가 없다. "시트의 강의 날짜마다 전날 20시 알림", "매월 1일에 지난달 결산", "마감 3일 전 알림"은 이 축에서 가장 흔한 시간 의도다. 우회는 `[self:script]`밖에 없다.
- 언어 개정이므로 사용자 판정이 필요하다. 후보: 순수 식 `date_add(날짜, 일수)`·`date_diff(a, b)`·`month_end(날짜)`. 날짜 표기 계약(ISO 8601)은 닫힌 밭의 것을 그대로 쓴다.
- 반-어휘-증식 원칙에 따르면 먼저 `[self:script]`로 얼리는 길도 있다. 다만 각 행 식(`compute`·`each` 안)에서 쓰려면 호출이 아니라 순수 함수여야 한다(교재 "그 안의 호출은 먼저 변수에 받는다" — 행마다 스크립트 호출이 된다).

### V75-1 (후보) 말일·공휴일 예약 표현이 없다

- 말일:
  - cron `L`·`28-31`은 거절된다(런타임·옛 검수기 기준. 판본 2 check는 B75-4로 침묵).
  - date형 monthly `10-31`은 `11-30`·`2-28`을 **건너뛴다**(T08).
  - `day:31` cron은 지금은 B75-1로 매일, 수리 뒤엔 짧은 달을 건너뛸 것이다.
  - "매월 말일 결산"은 "매월 1일 새벽에 지난달 결산"으로 우회하는데, 그 "지난달"은 G75-1이 막는다.
- 공휴일: 캘린더 이벤트 유형에 `holiday`(앱 선택지)가 있지만 발화 판정은 다른 이벤트를 보지 않는다. 어휘 전체에 공휴일 데이터가 없다(`ibl_nodes.yaml` 검색 0). "평일 9시, 공휴일 빼고"는 표현할 수 없다.
- 어휘 신설은 훈련이 하지 않는다. 처방 순서는 B75-1 수리 때 `day` 29~31 정책(정직 거절 또는 말일 접기)을 정하고 선언에 쓰는 것, 공휴일은 먼저 사용자 캘린더의 `holiday` 이벤트를 조건으로 읽는 문장(`[self:manage_events]{op:"list"}` → filter)으로 얼려 반복 사용을 본다.

## 재확인 (앞 회차 갭의 증거 추가 — 새 항목 아님)

- **B73-1**:
  - 시간 문형의 대표 꼬리 `… >> [table:since] >> [self:notify_user]{…}`(코퍼스 3980·3873·4016 형태)가 판본 2에서 `PIPE_COLLISION`이다(T04 안쪽 check, 탐색 중 `[{title:"a"}] >> [self:notify_user]`도 같음).
  - `… >> [others:channel_send]{…}`(코퍼스 3712·가이드 워크플로우 1)도 `PIPE_COLLISION`이다(T22).
  - 안내 문구는 여전히 "같은 명시 인자를 함께 주지 마세요"다(충돌 인자 없음). 판본 2 우회(`$n = …; [if: len($n.items) > 0] {…}`)는 T18에서 성공했다.
  - B75-4와 겹쳐, **트리거 do 안의 이 형태는 등록 때 아무도 거절하지 않고 발화 때 매번 죽는다.**

## 시드 후보 (실행 검증 통과만 — 자동 등록 안 함)

- T01(켜진 트리거 중 마지막 실패만: `$t = [self:trigger]{op:"list"}` → `$t.items >> filter{enabled && last_success == false} >> select`)
- T16(트리거 disable → enable → update cron → delete 운영 문형)
- T17(`[self:schedule]{date,time,do}`로 만든 예약을 `[self:manage_events]{op:"update", event_id, time, do}`로 옮기기)
- T18(판본 2 검침 알림: `$n = $rows >> [table:since]{key}` · `[if: len($n.items) > 0] {…} [else] {…}`)
- T21(조회 → 필드 → 임계값 `[if]` → `notify_user`, 가지 안 `;` 구분)
- T23(`[others:messages]{op:"inbox"}` → `get($r,"unread",0) > 0` filter → len)

문장 안 종목·경로·키는 자리표로 바꿔 심을 것.

**빼는 것**:
- T19 peek 두 단계 우회는 동작하지만 B75-5 수리 방향(프로그램 성공 시 커밋)이 정해지기 전에는 관용구로 굳히지 않는다.
- T05(1회 schedule·월요일 cron)·T03·T22·T24는 check만이라 뺀다.
- T07·T09·T10·T11·T12(반복 등록)·T14·T15(지연 예약)·T20은 결함 수리 전이라 뺀다.
- 코퍼스 3910·3980·4097·3712·3873·4016(`>> notify_user`·`>> channel_send` 꼬리)은 판본 2에서 막히는 형태라, B73-1 수리 또는 판본 2 형태 재작성 전까지 **회상 대상에서 재검토**가 필요하다(용례 재검토 관문).

## 판정 요청 (언어 개정·파괴적 변경 2종만)

- **G75-1 — 날짜 산술 순수 함수**(예: `date_add`·`date_diff`·`month_end`)를 공통 값 연산에 들일지. 근거:
  - 시간 문형의 가장 흔한 의도("전날"·"지난달"·"N일 전")를 식으로 말할 수 없다.
  - 문자열 우회는 월 경계에서 틀린다(`2026-11-0`).
  - 행마다 쓰려면 순수 함수여야 한다.
  - 표기 계약은 닫힌 밭(ISO 8601)의 것을 그대로 쓴다.

그 밖의 B75-1~6·F75-1~4는 수리성이다. V75-1은 후보로만 둔다.
- B75-1(반복 규칙 정본 모양)은 지금 매일 잘못 도는 monthly를 바르게 도는 쪽으로, 안 도는 yearly date형을 도는 쪽으로 바꾼다. 기존 사용자 원장의 실행형 monthly·date형 yearly는 0건이다.
- B75-2(단일 실행기)는 이중 실행을 없앤다.
- B75-5(성공 시 커밋)는 실패한 날의 새 것을 다음에 다시 보내는 쪽이다. 어느 것도 기존 문장을 깨뜨리지 않는다.
- F75-2는 자동 비활성화가 아니라 알림 접기라 파괴적 변경이 아니다.

**다음 수리 턴의 첫 항목(밭 이관)**:
1. B75-3 — 캘린더 쓰기 입구 전수 census → `add_event`/`update_event` 한 곳 정규화·검증 + 관문(B54-8에 이은 두 번째). B75-1의 정본 모양 수리와 한 벌로 한다.
2. B75-4 — 옛 `/ibl/validate`에만 있는 액션별 사전 판정(cron·config·do 재귀·조건 구문) census → 판본 2 check 선언 확장점으로 연결 + validate-parity 관문을 판본 2까지(F54-1에 이은 두 번째).

## 위생

- **기준선**: 탐침 전 22:59:53에 떴다([baseline.json](baseline.json) `baseline`). 알림함 2통(홍보 스케줄 실패 경고 2 — 74회차 단서 그대로), 트리거 25, 트리거 이력 200행(마지막 22:13:48), 캘린더 이벤트 54, action_health max id 242399, notify_log 6238, 시스템 AI 대화 max id 4128, since 원장 1스트림 25행(사용자 `F20_3_판정검증_20260822`). 트리거·캘린더 파일 사본은 세션 스크래치에 두었다.
- **스크래치 등록**: 전부 `IT75_` 이름이고, 등록 직후 같은 과제 안에서 지웠다.
  - 트리거 5건(T04·T07·T11·T16, T16은 disable/enable/update 뒤)
  - schedule 이벤트 10건(T09·T10 ×3·T11·T12 ×3·T14·T15·T17)
  - manage_events 이벤트 1건(T11)
- **발화 실측 2건**(T14·T15, 본문 `[self:time]{}` 무해 읽기, 표면 기본값 등록이라 직접 실행)이 남긴 것을 §3-5 네 곳에서 되돌렸다.
  - ①action_health `usage/scheduler` 3행(242460·242465·242466)을 삭제했다.
  - ②트리거 이력: 스크래치 트리거는 발화하지 않았고 지연 예약은 트리거가 아니라 IT75 이력 0행이다. 이력 200행과 마지막 행은 기준선과 같다.
  - ③시스템 AI 대화 새 행 0이다(소유 에이전트 없는 직접 실행).
  - ④알림함 3통(`예약 실행 완료 — 컨텐츠` ×2·`스케줄 실행 완료 — 컨텐츠/`)을 REST DELETE로 지웠고, notify_log의 같은 `usage` 3행(6240~6242)도 지웠다.
- **자기 수신 알림 1건**: T21. 조건 `$p > 200000`이 실제 시세 270,000원으로 충족돼 알림 가지가 탔다. 훈련자는 조건 미충족을 예상했다(예상 착오 — 결과는 올바른 동작). 알림 `삼성전자 270000.0원 — 20만원 돌파`는 알림함에서 지웠다. notify_log 6239는 `source:training`으로 격리돼 있어 남겼다. 이후 T24는 check로 낮췄다. 외부 발신(`others:channel_send`·`others:ask`)은 전부 check다.
- **since 원장**: 스크래치 스트림 `IT75_피드`·`IT75_유실`·`IT75_빈동네` 7행을 지웠다. 사용자 스트림 25행은 무손상이다. 탐색 중 check로만 쓴 `IT75_청주전세`·`IT75_하다`·`IT75_x`는 실행되지 않아 행이 없다.
- **회차 후 diff**(`baseline.json` `after`):
  - 알림·트리거·캘린더 이벤트 추가/삭제 0
  - 트리거·캘린더 파일은 `last_run`·`run_count`를 빼면 기준선 사본과 동일
  - IT75 이력 0 · since IT75 0 · 시스템 AI 대화 새 행 0
- **건강 원장**: 회차 창(22:46~) action_health는 training 60행(agent 43 · app 17 — app은 표면 기본값 등록 호출)이다. usage는 발화 3행을 지운 뒤 9행 남았다(`sense:search`·`sense:crawl`, channel agent, 23:03~23:07). 이 요청들은 이 탐침의 것이 아니라(탐침은 search·crawl을 부르지 않음) 다른 세션·사용자 실행으로 보고 건드리지 않았다.
- **나머지**: 사용자 트리거·이벤트는 읽기만(T01·T02·F75-2 조사). `data/scripts/ai_era_news.py` 읽기만. 해마 시딩 0 · 라이브 코어 편집 0 · 커밋 0. 탐침 75요청 + 탐색 약 15요청.
- **백엔드**: 회차 내내 `state.json` phase `ACTIVE`, 재기동·FAILED 없음.

## 집행 완료

### 1차 — `1b9a4932`(2026-09-29, 72~76회차 묶음 수리)

B75-1~6·F75-1~4 개별 자리를 닫았다(`calendar_rules` 정규화, 지연 예약 단일 실행기, 판본 2 check 의 `value_validator`·`code_params`,
since 성공 시 확정·빈 첫 관측 표지, 트리거별 이력 상한, 같은 실패 하루 요약, 교재·시간대). 보고서 끝 **밭 이관 관문 두 개는 세우지 않았다.**

### 2차 — 재탐침·누출 수리·밭 이관 관문 (2026-09-29 후속)

재탐침(격리 저장소에 실제 입구 함수 → 저장 레코드 → `_should_run_task`, 판본 2 compile, 라이브 check·스크래치 등록)으로
1차 수리 뒤에도 샌 자리를 찾았다. 같은 속의 세 번째가 안 나오도록 판정을 **한 함수**로 모으고 관문으로 묶었다.

| 누출 | 실측 | 뿌리 | 수리 |
| --- | --- | --- | --- |
| L1 트리거 cron 좀비 | `0 9 31 2 *`·`0 9 32 * *`·`0 25 * * *`·`70 9 * * *`·`0 9 1 13 *` → "생성 완료"+warning, 캘린더 이벤트 없음(영원히 안 돎) | cron 경로가 `normalize_schedule_config` 를 비켜 감, 트리거를 먼저 저장하고 동기화 실패를 warning 으로 | cron 결과도 정본 검사 · 동기화 실패 시 트리거 되돌림(오류) |
| L2 시각 없는 실행 예약 | `schedule{repeat:"daily"}`·`manage_events{repeat:"daily", do}`·`interval` 시각 없음 → success, 발화 판정 영원히 False | 정규화가 "실행 이벤트엔 시각 필수"를 몰랐다 | `normalize_schedule_config(executable=)` — action 있는 이벤트는 time 필수 |
| L3 check↔등록 불일치(B75-4 잔여) | `config:{repeat:"매일"}` check 이슈 0 / 등록 거절. schedule·manage_events 는 입구가 인자를 따로 해석 | ①레코드 리터럴이 `constant_value` 에서 미상 ②check 와 등록이 서로 다른 해석 코드 | `constant_value` 레코드 관측 · `calendar_rules.schedule_request`·`calendar_request` 를 **등록 런타임과 check 가 같이 호출** |
| L4 같은 실패 매시 알림(F75-2 잔여) | 수리 뒤에도 `스케줄 실행 실패 — 홍보/` 매시 1~3통(09-29 01~14시) | 실패 원문에 실행마다 새 로그 파일명(uuid)·`duration_ms` → 늘 "다른 실패" | `_failure_signature` — 실행 id·시각·소요 시간 지운 서명으로 비교(실이력 5건 → 서명 1) |
| L5 짧은 달 침묵 건너뜀 | `day:31` 등록이 11-30·2-28 을 건너뛴다는 말 없음 | 보고서 제안 3 미집행 | 등록 응답 `notice`(schedule·manage_events·trigger) |
| L6 입구 밖 쓰기 | `world_pulse` 가 `evt["enabled"]` 직접 + `cm._save_config()`(잠금 밖), REST add/update 의 ValueError → 500 | 쓰기 입구가 하나라는 규칙이 코드에 없었다 | `update_event` 로 · REST 400 · `remove_goal_schedule` 잠금 |
| F75-2 뿌리 | 트리거 `AI시대_보고서출처_뉴스갱신` 이 새 일 없이 매시 실패 | `ai_era_news.py` 가 `## 출처` 한 표기·`_verified_rows_` 한 이름만 인정(실제 `## 출처와 조사 한계`·`_verified_날짜.json`) | 판독을 실제 표기로(사용자 승인: 밀린 출처 뉴스 게시) · 가이드 §3-0 에 검증 원장 파일명 명시 |

**밭 이관 관문** `scripts/iblbuild_schedule_rules.py`(build `--check` 배선):
- 규칙 A(B75-3): 캘린더 이벤트 반복 규칙 키를 쓰는 함수는 `normalized_event` 를 부르는 관리자 입구뿐, 관리자 밖은 이벤트 목록·dict 수정과 `_save_config()` 금지.
  **수리 이전 트리(`1b9a4932^`)에 대 보니 add_event·update_event(원형)·world_pulse 를 잡았다.** 현재 HEAD 에선 world_pulse 2건.
- 규칙 B(B75-4): 어휘가 선언한 `value_validator` 마다 check(`_validator_problem`)와 등록 런타임 입구가 같은 공유 함수를 부르고,
  공유 함수가 읽는 인자 ⊆ check 의 `VALIDATOR_READS`(빠지면 변수 값을 없는 값으로 봐 거짓 빨강). 시각 의존 판정(이미 지난 시각)은 check 에서 뺀다 — 실행 순간의 사실이다.

**G75-1 언어 개정(사용자 채택)**: `date_add(날짜, 일수)`·`date_diff(a, b)`·`month_end(날짜)` — 공통 값 함수 표(`expression_functions.CONTRACTS`) 한 곳 선언,
ISO 8601 만(수선 없음), 날짜 텍스트 산술(`$d - 1`)은 이 함수를 안내하며 거절. ibl.md·교재 표·compact·trigger.md 갱신. 회원 개방 `self:record` 의존 지문 재감사(순수 계산 — 파일·네트워크 없음).
V75-1(말일·공휴일)은 후보로 남긴다 — 말일은 `month_end` 로 날짜를 구해 1회 예약하거나 notice 를 보고 판단한다.

**검증**: 신규 회귀 `backend/test_imagination_round75_followup.py`(누출 재현 — 수리 전 HEAD 에서 14 실패, 수리 후 전부 통과 · 입구×규칙 발화 대조 · check↔등록 19쌍 · 날짜 함수).
관련 회귀 91파일은 HEAD 와 같은 실패 집합(MCP 환경 실패만). 전체 backend 실행의 실패 2건(내장 함수 전수 표에 새 날짜 함수 예시 누락·새 시험 파일 `__main__` 누락)은 둘 다 이 수리의 추가분이 기존 전수 관문에 잡힌 것 — 고친 뒤 재실행 통과. 코퍼스 schedule·trigger·manage_events 127문장 check 판정 불변.
build `--check`·파일 크기·validate-parity·층·동시성·문서 드리프트·폰 번들 통과. 라이브: check 가 `config:{repeat:"매일"}`·`0 9 31 2 *`·시각 없는 반복을 등록과 같은 문구로 거절,
`day:31` 등록 notice, **20초 지연 예약을 지우면 발화 0**(scheduler 채널 건강 행·알림 0). 스크래치 `IT75R_*` 이벤트·since 행 삭제, 캘린더 54건 기준선 그대로.
