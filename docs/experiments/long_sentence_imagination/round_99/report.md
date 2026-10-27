# 99회차 보고서 — 긴 실행의 진행 신고가 표면에 정직하게 닿는가 (2026-10-27)

실행 전 계약 [task.md](task.md) · 증거 [evidence.jsonl](evidence.jsonl) · 프로그램 `p1_v0.ibl`(최초)→`p1_v4.ibl`(실행본) · 러너 `runner.py`(POST·폴링·구조화만) ·
시험 프로그램 [subjects/](subjects/) · 최소 재현 [l99_1_2_repro.json](l99_1_2_repro.json) · 독립 AI 요청 [ai_t1_message.txt](ai_t1_message.txt) · 채팅 표면 관측기 [ai_observe.py](ai_observe.py).
**최초 훈련은 보고까지 수행했다. 이후 사용자 요청에 따른 수리·되먹임은 §7, 미커밋 변경의 최종 검증은 §8에 기록한다.**

## 1. 과제와 조건

- **계기(이음새)**: 10-26 `6e312e3c` 가 IBL 액션 단위 진행(`ibl_progress` report_step/beat)을 채팅 표면(진행 수신자→WS `progress`·`conversation_turns.progress`)으로 흘렸다.
  같은 신고가 회수 티켓(`/ibl/recover`)에도 간다. 긴 프로그램(순차·병렬 each, 중간 실패, 재사용 재실행, 긴 단일 단계, 함수 안 each)이 두 표면에서 어떻게 보이는지 한 번도 밟지 않았다(원장 progress 언급 0).
- **형식**: 이음새 입장 회차 — 전체 IBL 1편(탐침 6종 연결·판정·보고·재독) + 기본 변형(같은 프로그램, 입력 병렬=3) + 독립 AI 1회(채팅 세션, **표식 없음**).
- **기준선**: HEAD `c8e1f6ce`, phase ACTIVE, `test_progress_to_chat`·`test_each_progress_visibility` 통과(09:27), 에피소드 최대 5555. 시스템 AI = claude_code/opus.
- **예산**: 09:23:14 시작·10:23:14 상한. 준비·설계 ~12분(코드 열람 포함, §2), 작성·검사 ~3분, 실행 수정 2주기·작성 수정 2주기(§2 표), 기본·변형 실행 각 ~50~66초, 독립 AI 는 §3.3.
- **동시 작업**: 독립 AI 턴(09:49:48~)과 훈련자 v4 기본·변형 실행(09:50~09:53)이 겹쳤다(둘 다 같은 백엔드, 티켓은 별개). 다른 사용자 작업 없음.

## 2. 작성

요구 → 6부품(띄우기·좌표판정·회차판정·결말판정·얼음판정·탐침판정) → 보고·재독. 값 전달·판정·조합은 IBL, 러너는 `/ibl/execute`(ticket) POST 를 스레드로 띄우고 `/ibl/recover` 를 0.15초마다 읽어 running 스냅샷을 구조화(step_prev·row 평탄화)만 한다. 98회차의 "러너본문을 inputs Text 로 `~turn` 에 쓰고 `[self:script]{path}`" 문형을 재사용했다.
**내부 지식 개입**: 설계 단계에서 `supervision_bus`·`chat_streams`·`ibl_v2_runtime`·`common/spill` 을 읽었다(이음새 위치·관측 가능한 표면을 정하기 위한 준비). 가설 H1(병렬 가지 문맥 유실)·H2(note 가 of=0 좌표를 안 적음)는 코드 열람에서 나왔고 task.md 에 실행 전 기록했다. 작성 자체는 교재·describe 범위였다.

| 판 | 변경 | 결과 |
| --- | --- | --- |
| v0 | 최초 전체 초안 | 검사 거절 `NUMBER_REQUIRED` ×4 — 표지 문자열에 숫자 입력(`"…"+$병렬`)을 이어 붙임. **작성 마찰**(문자+숫자 연결은 숫자 연산) |
| v1 | 표지를 `$변형`(Text)으로 | 검사 통과 → 실행 1.6초 `RECORD_REQUIRED`: `get(get($s,"detail",{}),"row")` — 키가 **있고 값이 null** 이면 기본값이 안 쓰여 `get(null,…)`. 진단 frames 가 함수·줄을 정확히 가리킴 |
| v2 | 러너가 row/rows/row_label 평탄화, IBL 은 `get($s,"row")` | 실행 34초 → S5 얼음판정 reduce `UNBOUND $repeat`(repeat 키가 없는 행). 러너 `repeat:0` 초기화 |
| v2' | (러너만) | 실행 39.7초 **완료**. 그러나 ① S1·S3·S6 시험 프로그램이 `parallel:$병렬`(입력) 로 거절 — `STATIC_OPTION`(each 옵션은 컴파일 리터럴, ibl.md 명세) ② dedup 봉투에 `len()` → 키 수 3 을 행 수로 읽음(rows_seen 3 거짓) |
| v3 | dedup `.items`, 시험 프로그램의 parallel 은 요청 조립기가 리터럴로 치환, S6 은 `$병렬` 매개변수 제거 | 완료 52초. S4 재사용 입력(`run_id`)이 null — 러너가 봉투 최상위 `run_id` 를 찾았는데 실제 위치는 `resume.run_id`/`continuation.reuse_args` |
| v4 | 러너 run_id 재귀 탐색, 결말에 봉투 키·reuse 정보 노출 | 기본 54.5초·변형 66.0초 완료(§3) |

검사 수정 1주기(v0→v1), 실행 수정 2주기(v1→v2, v2→v2'), 완료 뒤 판정 보완 2판(v3·v4). 전부 작성자 쪽 원인(시험 프로그램 포함)이며 실행기 결함 아님. 최초 초안·중간 판 전부 보존.

## 3. 실행과 결과

### 3.1 주 과제(v4 기본, 병렬 1) — 54.5초, 모델 0, 검사 통과/실행 종료/달성 별도

| 탐침 | 스냅샷(좌표 있음) | step 단조·최대 | **행 회차 관측** | 결말 | 판정 |
| --- | --- | --- | --- | --- | --- |
| S1 순차 each 6행 | 8(7) · 67폴링 | 단조 · 7 | **0/6 — detail 전무** | success | **미달(회차 없음)** |
| S2 병렬 each 6행(3) | 5(4) · 64 | 단조 · 5 | **0/6** | success | 미달(회차 없음) |
| S3 중간 실패(4행 exit 3) | 6(5) · 40 | 단조 · 5 | **0/6** | success:false · error "Script 종료 코드 3" · `coverage [ok,ok,ok,failed,pending,pending]`·`successful_indices [0,1,2]` | 실패 지점 보존 **달성** / 회차 미달 |
| S4a 읽기 3+잠들기 | 2(1) · 23 | 단조 · 5 | 해당 없음 | success | 달성 |
| S4b reuse 재실행 | 4(3) · 23 | 단조 · 5 | 해당 없음 | success · `reuse.reused_calls 0, candidates 0`, skipped self:read `no_matching_receipt` | **미검증**(§4 L99-3) |
| S5 긴 단일(5초) | 3(2) · 38 | 단조 · 2 | 해당 없음 | success · updated_at 1종/33회 반복 → **얼어 있음(설계대로)** | 달성 |
| S6 함수 안 each 3행 | 1(0)… v4 에서 4(3) · 25 | 단조 · 4 | **0/3** | success | 미달(회차 없음) |

note 에 좌표(action)가 들어간 스냅샷: **0/전부**(S1~S6 모두 `note_has_action false`). note 는 항상 "실행이 아직 돌고 있습니다 — 끝날 때까지 기다리려면…" 일반문.

### 3.2 기본 변형(v4, 입력 병렬=3; S1·S3·S6 의 each 가 parallel 3) — 66.0초

같은 프로그램·같은 판정. 결과 동일: 회차 0/6·0/6·0/3, step 단조, S3 `coverage [ok,ok,ok,failed,ok,pending]`(병렬이라 5행이 끝난 뒤 멈춤 — 부분 결과가 정직하게 남음), S5 얼음 true, note 좌표 0. 견고성 시험으로서 프로그램 수정 0.
H1(병렬 가지에서만 회차 유실)은 **기각** — 순차에서도 유실된다(원인은 §4 L99-1).

### 3.3 독립 AI(채팅 세션 `e81b7de7`, ep5556, 표식 없음) — 09:49:45→09:56:22, **396.7초**, completed

- **비용**: 턴 토큰 2,772,470(캐시 읽기 2,522,650) · 모델 호출 5(라운드 25) · 도구 18(**전부 Bash**, execute_ibl 0, 오류 2) · 첫 도구까지 44.8초(의식·회상) · 자기 보고 "표본 307개·실행 10건".
- **풀이 방식**: 백엔드 소스(`api_ibl.py`·`spill.py`)를 읽어 `/ibl/execute`(ticket, **origin training 명시**, project_id '앱모드')+`/ibl/recover` 0.2초 폴링 관측기 `observe.py` 를 Python 으로 작성·실행. IBL 작성 0 — 과제가 "실행을 관측"하는 것이라 IBL 로 풀 이유가 없었고 훈련자도 같은 선택(러너). 훈련자 trainer/runs/docs 미참조(자기 보고 `not_referenced` + 도구 입력 기록에 해당 경로 0 — 접근 통제 없음).
- **시험 프로그램 거절을 스스로 처리**: S1·S3·S6 원문이 `parallel:$병렬` 로 `STATIC_OPTION`·`UNBOUND` 거절 → 거절 봉투를 `raw/*_orig_*.json` 에 보존하고 parallel 만 1·3 리터럴로 바꾼 사본(`ai_variants/`)으로 실행, 보고에 "사본의 관측" 이라고 명시(**과제 자료 결함 — 작성자 README 가 입력 병렬을 약속했으나 명세는 리터럴**). S4 의 `.content` 오기(`self:read` 는 `.text`)도 발견·보고(lens 0 — 진행 판정 무관).
- **판정(AI)**: (1) step 역행 0/307·of 항상 0·병렬에선 2→5 건너뜀과 "동시에 도는 호출 중 하나만 보임" (2) **행 회차 전무 — 실패**(each 4종 running 표본 전부 detail 없음) (3) 실패 지점 보존 통과(`SCRIPT_EXIT`·소스 위치·coverage·stderr) + "끝난 뒤 회수엔 마지막 좌표가 안 남음" (4) 재사용 **미확인**(reused_calls 0·새 읽기 3, 첫 실행 read_calls 0) (5) S5 updated_at 5.5초 고정 — 얼어 있음 (6) note 좌표 **실패**(코드를 읽고 `of=0` 조건을 원인으로 지목). 훈련자 판정과 **전건 일치**, 추가 발견 2(§4 L99-5·관측).
- **채팅 표면(이 회차의 이음새) 관측**: 관측기가 0.5초마다 읽은 `turn.progress` 는 **396초 내내 null**(progress_trace 0건). 원인 = AI 가 execute_ibl 을 한 번도 안 부르고 Bash 로 HTTP 를 쳤다 — 진행 수신자는 execute_ibl 안쪽(ibl_progress→버스→task_id)만 듣는다. 사람이 본 것은 Bash 카드 18장(도구 한 호출=한 줄, Claude Code 식)뿐. `interim_text` 사건 0(도구 앞 중간 서술 없음 — 프롬프트 미수리로 예상된 미관측). 턴 종료 뒤 `state completed`·progress null.

| 축 | 훈련자(v4, 기본+변형) | 독립 AI(ep5556) |
| --- | --- | --- |
| 달성 | S3·S5 달성, S1·S2·S6 회차 미달, S4 미검증 | 같은 결론(6판정 중 (2)(6) 실패·(4) 미확인) |
| 시간 | 54.5+66.0초(모델 0) | 396.7초(의식 45초 포함) |
| 토큰 | 미측정(작성자) | 2.77M(캐시 2.52M) |
| 풀이 | IBL 1편(판정·보고) + Python 러너(POST·폴링) | Python 관측기 + Python 보고 생성기, IBL 0 |
| 추가 발견 | L99-1 원인(코드 진단)·최소 재현 | L99-5 제출 직후 unknown 창, 결말에 좌표 없음, S4 `.content` 오기 |

## 4. 발견

| ID | 분류 | 내용 | 증거 |
| --- | --- | --- | --- |
| **L99-1 ★★** | 구현 결함(표면 정직성) | **each 행 회차가 회수 티켓 표면에서 전혀 보이지 않는다** — 순차·병렬·함수 안 전부 0/N(기본·변형 합계 8실행, 폴링 ≈360회). 원인(진단): v2 런타임 `_report_action` 이 **행 안 모든 액션 경계**마다 `report_step` 을 부르고, `common.spill.ticket_progress` 가 `rec["progress"] = dict(progress)` 로 **progress 를 통째로 바꿔 beat 이 쓴 detail 을 지운다**. beat→첫 액션 사이 수 ms 만 detail 이 산다. 09-01 수리(②"회차가 없었다")가 v2 액션 경계 신고(10-26)와 만나 라이브에서 되돌아갔다. 채팅 표면은 좌표 신고에 `self.local.row_detail` 을 동봉하므로 영향이 다를 수 있음(§3.3). `test_each_progress_visibility` 는 spill 함수만, `test_progress_to_chat` 는 버스만 검사해 교차점이 없다 | S1~S6 `rows_seen 0`·`any_detail false`, 최소 재현 `l99_1_2_repro.json` `detail_survives_action_report:false` |
| **L99-2 ★** | 구현 결함(진단 공백) | `_progress_note` 가 `prog.get("of")` 가 참일 때만 좌표를 적는다. 10-26 부터 런타임이 `of=0`(미지, 거짓 분모 금지) 을 보내므로 **사람이 읽는 note 에 step/action 이 영원히 없다**. 원시 `progress` 에는 있어 기계 소비자는 보지만, note 만 읽는 소비자(모델)는 "어느 낱말인가"를 못 본다 | 전 스냅샷 `note_has_action false`, 재현 `note_mentions_action_with_of0:false` vs `of:5` 이면 "step 2/5 self:script" |
| L99-3 | 작성 전제 오류·관측 | S4 "재사용 호출이 실행 중으로 보이는가"는 **미검증** — 같은 프로그램 재실행인데 `reused_calls 0, candidates 0`(self:read `no_matching_receipt`). 프로그램에 자원 미상 호출(`self:script`)이 있어 모든 읽기 영수증이 재사용 후보에서 제외되는 기존 계약(봉투 hint 에 명시)을 작성자가 안 읽었다. 재사용 구별 질문은 다음 회차 후보(스크립트 없는 프로그램) | S4b `reuse_info` |
| L99-4 | 작성 마찰(기록) | ① `"문자"+$숫자` 는 숫자 연산(NUMBER_REQUIRED) ② `get(x,k,기본)` 은 키가 있고 값이 null 이면 기본값을 안 준다 → `get(null,…)` 거절 ③ `[table:dedup]` 결과는 `{items,count,success}` 봉투라 `len()` 은 키 수 ④ each `parallel` 은 입력 변수 불가(STATIC_OPTION, 명세대로) ⑤ 성공 봉투의 run_id 는 `resume.run_id`·`continuation.reuse_args` 에만 있고 최상위에 없음 | §2 표 |
| L99-5 | 구현 결함·진단 공백(AI 발견) | 제출 직후 첫 `/ibl/recover` 가 10건 중 8건 `status unknown`("만료 또는 미탑재") — `ticket_begin` 이 실행 스레드에서 늦게 기록돼 0.1~1초 창에서 "못 봤다"가 "없다"로 보인다(B28-1 부류 재발). 훈련자 러너는 0.15초 뒤 첫 폴링이라 같은 창을 밟았지만 running 외 상태를 버려 못 봤다 | AI `other_observations`, raw/*.json 첫 표본 |
| 관측(AI) | — | 결말(done) 봉투에는 마지막 진행 좌표가 남지 않는다 — 실패 위치는 error/coverage 로 보존되므로 결함 아님(기록) | AI 판정 (3) |
| 관측(결함 아님) | — | 중간 실패의 결말은 `coverage`·`successful_indices`·partial 로 실패 지점을 보존(S3 두 변형). 긴 단일 단계의 updated_at 은 얼어 있음(technical.md 명시 "긴 단계는 갱신 없이 실행될 수 있다"). step 은 전 실행 단조 | S3·S5 |

## 5. 개선 방향(공통 능력, **미수리**)

- L99-1: `ticket_progress` 가 기존 `detail` 을 보존하거나(좌표 갱신은 좌표 칸만), `report_step` 이 티켓에도 detail 을 동봉. 어느 쪽이든 "좌표는 소유하고 움직임은 공유한다" 규율 안. 관문 = 실제 `Runtime` + 티켓으로 each 를 돌려 recover 의 `progress.detail.row` 가 보이는 교차 시험.
- L99-2: note 조건을 `step and action`(of 는 있으면 `/of`)으로. 관문 = `_progress_note({"step":2,"of":0,"action":"x"})` 가 action 을 품는가.
- L99-4: 교재에 ①②③⑤ 한 줄씩(②는 `get` 계약 또는 `??`/`has` 안내).

## 6. 비용·낭비 검토와 잔여

- **상한 60분 중 훈련 종료 09:56:22(33분 8초)**: 준비·설계 ~12분, 작성·수정 ~10분, 훈련자 실행 합계 ≈ 7분(검사 4·주 5·변형 3; 실패 2회 36초 포함), 독립 AI 6분 37초(훈련자 v4 와 3분 겹침). 보고·원장 작성은 그 뒤 별도(~15분). 훈련자 모델 호출 0. 작성자(이 세션) 토큰 미측정.
- **필요했던 비용**: 폴링 0.15초(행 0.7초 대비 충분) — 회차 부재가 "폴링이 못 본 것"이 아님을 증명하는 데 필요(S1 67폴링·반복 스냅샷). 최소 재현 2건.
- **줄일 수 있었던 일**: ① 시험 프로그램의 `parallel:$입력`(명세 미독) 로 v2' 한 바퀴(40초)·v3 한 바퀴 ② dedup 봉투 `len()` 오독 ③ run_id 위치 미확인으로 v4 재실행(55+66초) — 셋 다 계약을 미리 `describe`/봉투 한 번 읽었으면 없었음. 확인된 낭비 ①②③.
- **보존할 품질**: 결말·스냅샷 불변식·note 문구를 별도 칸으로 판정, 폴링이 못 본 행과 신고가 안 된 행을 구분, 최초 결과 보존.
- **미검증·잔여**: 재사용 구별(L99-3, 스크립트 없는 프로그램으로) · **채팅 표면에 progress 가 실제로 그려지는 실행은 이번 회차에 없었다**(AI 가 execute_ibl 을 안 씀 — execute_ibl 을 쓰는 턴으로 재관측 필요, 또는 WS 클라이언트) · L99-5 재현(제출 직후 unknown 창) · 수리 전부(사용자 지시로 이번 회차 범위 밖). 다음 회차 후보: L99-1·2 수리 뒤 같은 v4 프로그램 되먹임(회차 N/N·note 좌표), execute_ibl 경로의 채팅 progress.

## 7. 같은 날 수리와 되먹임 (10:30~14:10, 사용자 "보고서를 읽고 수리")

**수리 4건 + 교재 5줄(공통 능력, 새 낱말·op·인자 0)** — 전부 §5 의 방향 그대로.

| 발견 | 수리 | 관문 |
| --- | --- | --- |
| L99-1 | `common/spill.ticket_progress` 통째 교체 → **병합**: 신고 키 갱신, 좌표 신고(step/action)의 detail 은 신고가 품은 것으로(없으면 삭제 — each 밖 좌표에 옛 행이 남으면 거짓), 좌표가 아닌 신고(`resume`·`plan_hash` 손잡이)는 detail 불변·손잡이 보존. `ibl_progress.report_step` 이 버스와 **같은 신고**(detail 포함)를 티켓에도 씀. `ticket_progress/beat/finish` 프로세스 내 `threading.Lock`(병렬 가지의 읽고-고치고-쓰기 유실·늦은 신고의 done 되살림 방지) | 실 `Runtime`×티켓 교차 시험(순차·parallel 2) — 행 안에서 recover 하면 좌표·회차·note 가 함께 있음; `l99_1_2_repro_after.json` `detail_survives_action_report:true`·`detail_cleared_outside_each:true` |
| L99-2 | `_progress_note` 조건 `step and of` → `step or action`, of 는 있을 때만 `/of` | `_progress_note({"step":2,"of":0,"action":"self:script"})` → "step 2 self:script"; of 5 → "step 2/5 self:script" |
| L99-5 | `ticket_begin` 이 표식을 **먼저** 쓰고 gc 는 뒤 · gc 는 프로세스당 60초 1회(`_gc_opportunistic`). 진단: gc 가 14,134 파일 스필 디렉토리를 매 티켓 걷었다(실측 0.131초 cold·0.045초 warm) — ticket_begin 은 async 핸들러 안 동기 호출이라 이 시간이 **이벤트 루프 위**에 얹혀 회수 요청까지 늦췄다 | `test_시작_표식은_청소보다_먼저_쓰고_청소는_드물다`; 라이브 창 측정 §7.2 |
| L99-6(수리 중 발견) | `Journal.announce` 가 run_id 손잡이를 `get_progress_ticket()` 에 썼는데 announce 는 `Runtime._run` 의 claim **보다 먼저**라 그 슬롯은 항상 None — 손잡이가 티켓에 닿은 적이 없었다(끊긴 표면이 running 회수에서 run_id 를 되찾는 통로가 죽은 경로). → 집히기 전 `surface_ticket` 에 쓰고(비어 있으면 바깥 실행 안이라 안 씀), 병합이 보존 | `test_실행_손잡이는_첫_액션_뒤에도_남는다`; repro_after `handle_survives_action_report:true`. ★이 변경은 공유 작업 트리에서 타 세션 커밋 `82e8eb12`(실행 전 티켓 손잡이 게시…)에 실렸고 그 세션이 `test_ibl_migration_completion`·`test_ibl_run_journal` 을 정렬했다 |
| L99-4 | 교재 한 줄씩(원리·경계만): `ibl_composition.md` ①`+`는 Text 양쪽·숫자는 `text()` ②`get` 기본값은 키 부재에만(null 은 `== null` 삼항) ④each 옵션은 컴파일 리터럴, `ibl_composition_tools.md` ③반환 모양은 describe 로·봉투 `len`=키 수 ⑤`run_id` 최상위 없음. `subjects/README.md` 의 거짓 약속(입력 병렬) 정정 | 가이드 예산 33,639/36,000B |
| L99-3 | 수리 없음 — 자원 미상 호출 포함 프로그램의 읽기 영수증 재사용 제외는 계약. 재사용 구별 질문은 스크립트 없는 프로그램으로 다음 회차 | — |

문서: `technical.md` 진행 신고 규약 갱신, 원장 99회차 갭 행 갱신(+L99-6), changelog. 시험: `test_each_progress_visibility.py` +5 → 진행 2파일 26 통과, `test_ibl_migration_completion`·`test_surface_ticket_recovery`·`test_long_completion` 통과.

### 7.1 되먹임 — 같은 `p1_v4.ibl`·같은 조립기, 수리 후 백엔드(세대 `181dbcac…` 이후)

| 탐침 | 수리 전(기본/병렬3) | **수리 후 기본** | **수리 후 병렬3** | 판정 |
| --- | --- | --- | --- | --- |
| S1 순차 each 6행 | 0/6 · 0/6 | **6/6**(max_row 6, 44폴링) | 3/6(parallel 3 → 파도 2) | 달성·달성 |
| S2 병렬 each 6행(3) | 0/6 · 0/6 | 2/6(파도 2) | 3/6 | 달성·달성 |
| S3 중간 실패(4행) | 0/6 · 0/6 | 4/6 · last_row 4 ≤ fail_at · coverage 보존 | 2/6 · coverage `[ok,ok,ok,failed,ok,ok]` · last_row 6(병렬이라 5·6 이 함께 돎 — 설계대로) | 달성·달성 |
| S4a/S4b | 좌표만 | step 5 `self:script` · note 좌표 ○ · reuse 미검증(L99-3) | 같음 | 달성(재사용 구별은 여전히 미검증) |
| S5 긴 단일 | note 좌표 × | note "step 2 self:script" ○ · updated_at 1종/33반복(얼음=설계) | 같음 | 달성 |
| S6 함수 안 each 3행 | 0/3 · 0/3 | **3/3** | 2/3 | 달성·달성 |
| note 에 좌표(action) | 0/전부 | **전 스냅샷 true** | 전 스냅샷 true | 달성 |
| 시간 | 54.5 · 66.0초 | 40.5초 | 40.3초 | 모델 0 |

전 탐침 "달성"(변형 포함, 프로그램·조립기 수정 0). step 단조 전건, 범위 밖 행 0.
**병렬 each 는 파도당 1행만 보인다** — detail 은 한 칸이고 "마지막 쓴 놈이 이긴다"(09-01 규약). parallel 3 이면 세 행이 수 ms 안에 beat·좌표를 쓰고 한 행이 남아 0.7~0.9초 머무르므로 보이는 행 수 ≈ 파도 수(6행/3 = 2). 1..N 범위·rows=N 은 전건이라 "거짓"은 아니나 "동시에 도는 행 집합"은 표면에 없다 — 규약 확장(예: 가지별 detail 목록) 은 다음 회차 후보로 둔다(미결).

### 7.2 L99-5 창 측정(수리 후, 유휴 백엔드)

10회 반복(작은 프로그램, 20ms 폴링, `l99_5_window_after.json`): 티켓이 처음 보인 시각 **중앙 5ms·최대 77ms**, `unknown` 이 먼저 보인 실행 3/10 — 전부 제출과 동시(0~1ms)의 첫 폴링 1회뿐이고 다음 폴링(≈35ms)에서 running. 0.2초 뒤 첫 폴링(AI 관측기 조건)이면 10/10 보임. 수리 전 AI 가 본 8/10·0.1~1초 창은 부하 상황(독립 AI 턴+훈련자 실행 동시, 매 티켓 gc 0.05~0.13초가 이벤트 루프 위)이라 같은 조건을 다시 만들진 않았다 — '제출 직후 unknown' 은 **창을 줄인 것**이지 없앤 것이 아니며(표식은 요청이 핸들러에 닿은 뒤에만 쓸 수 있다), 회수자는 제출 직후의 `unknown` 을 '없다'로 단정하지 않는 규율(B28-1)을 그대로 지켜야 한다.

### 7.3 운영 기록(수리 턴에서 밟은 것)

- 수리 시작 시점(10:20) 백엔드가 이미 **FAILED**(`recovery_unavailable`, 10:10 자기수리 세션 `research_6764e0ee…` 의 red_apply 검증 실패 — 내 변경 전·무관) → 편집을 모아 `restart --wait` 1회(10:40 restarted). 11:05 타 세션의 backend 편집(`ibl_v2_*`·`expression_*`)이 재기동 도중 닿아 `artifact_changed_before_start` → 다시 FAILED; 14:05 `restart --wait` 로 복구, 되먹임 실행. 14:08 타 세션 편집으로 또 자동 재기동(성공).
- **공유 작업 트리**: 타 세션이 내 미커밋 `ibl_run_journal.py` 변경을 자기 커밋 `82e8eb12` 에 실었고, 그 과정에서 깨진 시험을 자기 쪽에서 정렬했다. 내 쪽 커밋은 pathspec 으로만(CLAUDE.md Git 규약 재확인).
- 세션 사용 한도(10:50~14:00)로 다각 검토 워크플로(4 렌즈) 전부 미실행 — 재개 뒤 단일 검토자(읽기 전용)로 대체(결과 §7.4).

### 7.4 독립 검토(읽기 전용 검토자 1)

읽기 전용 검토자(일반 에이전트 1, 47 도구 호출·10분)가 diff·규약·소비자(`mcp_server`·`tool_completion`·`chat_streams`·frontend)·시험 격리(`conftest.isolated_spill_root`)를 읽고 재현 스크립트를 돌렸다. 결과:

| 등급 | 발견 | 조치 |
| --- | --- | --- |
| **중간 — 실결함(재현됨)** | **R99-1** each 가 끝난 직후 **같은 액션**이 0.25초 안에 이어지면 `_report_action` 의 접기(키=액션 이름)가 each 밖 첫 좌표를 삼켜, 병합 규칙의 "좌표 신고에 detail 없으면 삭제"가 발동하지 못해 **옛 행 detail 이 그 액션 내내 남는다**(긴 모델 호출이면 분 단위 거짓). 재현: `[table:each]{items:[1,2]}{[test:a]{n:$it}}; [test:a]{n:9}` → n=9 안에서 recover 가 `each 2/2행(2)`. 내 교차 시험은 접기 간격을 0 으로 패치해 못 봤다 | **수리** — 접기 키를 (액션, 회차) 로: 같은 행 안에서만 접히고 행이 바뀌거나 each 를 벗어나면 즉시 신고(`ibl_v2_runtime._report_action`). 회귀 시험 `test_each_밖_같은_액션은_접히지_않고_옛_행을_지운다`(기본 간격 그대로). `test_같은_액션의_연속_신고는_간격_안에서_접힌다` 는 "같은 행 안에서만 접힘"으로 개정(행마다 같은 액션 2회 → 좌표 3·회차 3). 관련 5파일 78 통과 |
| 낮음(기록) | 프로세스 전역 잠금 하나가 모든 티켓의 파일 I/O 를 직렬화하고, `ticket_finish` 는 이벤트 루프 스레드에서 잠금 아래 봉투 전체를 json.dump 한다 — ms 단위라 결함 아님, 잠금의 유일한 비용. 재진입·교착 없음(잠긴 구간 안에서 spill 재호출 없음) | 기록 |
| 낮음(기록) | `ticket_begin` 은 잠금 밖에서 쓴다 — 신고자보다 항상 먼저라 안전(재-begin 경로 없음) | 기록 |
| 없음 | 옛 모양(통째 교체·of>0 note·매 티켓 gc) 에 의존하는 소비자·시험 없음. gc 전역 상태의 시험 누수 없음(`isolated_spill_root` autouse). 병렬 교차 시험 8/8 재실행 통과 | — |

**접기 키 수리 뒤 라이브 재확인**(백엔드 자동 재기동 세대 `c38f09c6…`, 같은 `p1_v4.ibl` 기본, 38.6초): S1 6/6·S2 2/6·S3 4/6(실패행 4)·S6 3/3, S5 note "step 2 self:script", note 좌표 전 스냅샷 true — 전 탐침 달성(`trainer_repair/p1_report_수리후기본2.json`).


## 8. 미커밋 변경 확인과 최종 검증 (2026-10-27)

사용자의 미커밋 변경 확인·커밋 요청에 따라 정본 main에서 현재 변경을 대조했다.
진행 신고·회수 티켓 수리와 교재·기술 문서·99회차 증거를 함께 반영한다.
이미 커밋된 Runtime 접기 키와 Journal 손잡이 변경은 다시 변경하지 않았다.

- 테스트 선택기: backend 변경 4파일, 구현 모듈 2개 → 전이 시험 743/789파일(94%).
  허브 `ibl_progress`·`spill`로 전수 권고.
- 비system 전수: **10,807 통과, 9 건너뜀**, 종료 0, 844.88초.
- 관련 system: `test_restart_process`, `test_python_libraries`, 이벤트 루프 전수 가드와
  사용자 경로 효과 가드 — **76 통과**, 종료 0, 156.43초.
- UI 번역·카탈로그·경계·상태·X-ray: **37 통과**. frontend `tsc -p tsconfig.app.json` 통과.
- `build_ibl_nodes.py --check` 통과. 증거 JSON/JSONL·Python 구문, 보고서 링크,
  추가 파일의 고신뢰 비밀값 패턴 검사 통과.

위 결과는 이번 커밋 확인에서 새로 실행한 검사다. §7의 라이브 되먹임은 당시 기록이며
이번에 재실행하지 않았다. Cloudflare의 실제 외부 서비스 동작이나 채팅 화면의 라이브
진행 표시를 이번 검사로 검증했다고 주장하지 않는다.

증거 내 개인 홈 절대 경로는 `<REPO>`(저장소 루트)·`<HOME>`(홈)으로 일반화했다.
실행 상태·오류·회차·시간·판정 수치는 바꾸지 않았다. 개인 명사 관문도 확인했다.
