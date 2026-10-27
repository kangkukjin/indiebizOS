# 100회차 보고서 — 큰 변경 뒤 재진입: 99회차 "진행→표면" 훈련 재실행 + 보존 프로그램 검사 회귀 (2026-10-28)

## 1. 과제와 조건
사용자 지시 "앞의 훈련을 다시 해줘. 시스템이 많이 바뀌어서". 계기와 완료 조건은 [task.md](task.md). 시작 00:35·상한 01:35, 훈련 종료 01:03(28분, 보고·회수 별도). 형식 = 회귀 재진입(가이드 §2 ②) + 99 경계 질문 셋(a 병렬 each 동시 행 집합 · b execute_ibl 경로 채팅 progress · c 스크립트 없는 재사용 S7).
시험 대상 = 99회차 subjects 6편 **변경 0** + `s7_reuse_pure.ibl` 신설(읽기 3 + 순수 each 2500행, 스크립트 없음). 훈련자 프로그램 `p1_v0.ibl` = 99 `p1_v4.ibl` 그대로(검사 issues 0) → `p1_v1`(S7 두 실행·판정 추가) → `p1_v2`(재사용 수 키 보정 `reuse.reused_calls`·S7/S1 스냅샷 원문 보존 — 판정 보완만). 러너 99 판 그대로. 모델 호출 0.

## 2. 운영 환경 — 이 회차의 측정을 가른 두 조건
- **타 세션의 동시 편집·시험**: 00:33~00:50 타 세션이 backend(`spill.py`·`restart_controller.py`·`execution_trace*` 등 14파일)를 저장할 때마다 개발 세대 교체가 걸려 백엔드가 **5분에 3회 재기동**(controller.log 00:33·00:36·00:38 세대 인계), 00:44·00:49 에도 DRAINING/STOPPING. 매 실행 앞뒤에 `gate.py`(ACTIVE·healthy 확인+세대 digest 기록, `evidence.jsonl`)를 두었다. 00:49 병렬3 1차 실행은 **drain 중 새 접수 거절**("재기동을 위해 새 작업 접수를 잠시 중단했습니다")로 S5~S7 미실행 → 01:01 재실행.
- **CPU 부하**: 00:50~00:59 타 세션 pytest(python 11 프로세스 ×80%, load 19.5). 이 창의 시간 수치는 전부 부하 혼입(아래 §3.4). 01:00 이후 load 3.7 에서 재측정.
- 백엔드 세대: 00:47~00:49 `ea6f9559…`, 01:01~ `78a9cc24…`(모두 타 세션 편집으로 바뀐 개발 세대 — 실행된 코드 = 저장소 HEAD `357336f6` + 타 세션 미커밋 변경).

## 3. 실행과 결과

### 3.1 P0 보존 프로그램 검사 회귀 스윕(`sweep_check.py`, 69편, 실행 0, 세대 `ab8018a6…`)
| 결과 | 편수 | 내용 |
| --- | --- | --- |
| ok | 8 | 입력 없는 프로그램(86 unit_error·89~91 functions) |
| UNBOUND 만 | 46 | 입력 부재만 — 새 계약 층에서 거절 0 |
| 그 외 코드 | 15 | TYPE 12·FUNCTION 7·SYNTAX 3·READONLY 2·BUILTIN 1·PURE_EXPRESSION 1·PARAMETERS 1 |

15편 분류: **(iii) 당시에도 깨져 있던 초안·중간판 11편**(88/94/95 v0 SYNTAX, 85 recover_v0·98 p1_v0 READONLY, 85 v1·88 v1·96 v0 TYPE, 85 v3 BUILTIN parse_json, 97 v0 PARAMETERS) · **분할 프로그램 1편**(89 main_v0 의 함수가 functions.ibl 에 있음, FUNCTION 7) · **(i) 의도된 엄격화 1편(4판 전부)** = 84 base_v0~v3 `TYPE: List<Record>|Text 가 필요하지만 Null|Text` — `$question=get($req,"ask_user","")` 를 `self:write content` 에 넣는 자리. `get` 기본값은 키 부재에만 적용되므로 값이 null 일 수 있다는 분석은 옳다(99 교재 ② 와 같은 뿌리). 10-20 에는 실행 성공한 최종판이 지금 검사에서 거절되는 **작성 마찰**이지 회귀는 아니다(null 삼항으로 고치면 통과). 회귀 0.
한계: 입력 없이 검사했으므로 입력이 있을 때만 드러나는 타입 문제는 못 본다(99 p1_v4 는 입력 포함 검사 issues 0 으로 별도 확인).

### 3.2 P1 재실행 — 99 되먹임(10-27 14:15) 대비
| 탐침 | 99 수리후(기본/병렬3) | **100 v2 기본(01:01)** | **100 v2 병렬3** | 판정 |
| --- | --- | --- | --- | --- |
| S1 순차 each 6행 | 6/6 · 3/6 | **6/6**, step 단조, note 전 true, 9.3초 | **거절**(PARALLEL_RESOURCE_CONFLICT) | 달성 / **변경됨** |
| S2 병렬 each 6행(3) | 2/6 · 3/6 | **거절** | **거절** | **변경됨** |
| S3 중간 실패(4행) | 4/6 · 2/6 | 4/6, last_row 4 ≤ fail_at, coverage `[ok,ok,ok,failed,pending,pending]`, success:false | **거절** | 달성 / 변경됨 |
| S4a/S4b 스크립트 포함 재사용 | reused 미검증 | `reuse.reused_calls 0`·`skipped no_matching_receipt`(계약 L99-3 그대로), step 5·note ○ | 같음 | 달성(재사용 제외는 계약) |
| S5 긴 단일 | 얼음·note ○ | updated_at 1종/35반복, note "step 2 self:script" | 같음 | 달성 |
| S6 함수 안 each 3행 | 3/3 · 2/3 | **3/3** | **거절** | 달성 / 변경됨 |
| S7a 순수 each 2500행(신설) | — | success, **회차 보임 11/2500 표본**(H3 참), 좌표 `step 1 self:read` 가 each 내내, 마지막 `step 4 table:reduce` | 같음(max_step 1 — reduce 표본 미관측) | 달성·**L100-3** |
| S7b 재사용 재실행 | — | `reuse.reused_calls 3`(**재사용 성립**, L99-3 대조군), 진행은 S7a 와 **같은 모양**(step 1 self:read · each N/2500) — 재사용된 읽기가 "진행 중"으로 보임 | 같음 | 달성·**L100-3** |
| 시간(모델 0) | 40.5 / 40.3초(8 launch) | 46.8초(10 launch) | 29.1초(병렬 4편 즉시 거절) | §3.4 |

v1(00:48, 부하 중) 기본은 같은 판정·같은 거절(S2)이며 S1 14.6초 등 시간만 다르다(`trainer/p1_report_기본.json`). 1차 병렬3(00:49)은 S5~S7 drain 거절로 미검증 → v2 재실행이 정본.

### 3.3 독립 AI 1회 — `POST /system-ai/chat` `origin:"training"` background (ep5559)
00:50:36~00:57:47 **431초**, 도구 27(Bash 25·Write 1·execute_ibl 1), 모델 usage(billable) 실행 입력 3,836,294(캐시 읽기 3,658,587·생성 177,651)·출력 26,006, 의식 162,674/2,923, 평가 1회 22.7초. 방법 = 자체 Python 표본기(`ai_out/sampler.py`, HTTP execute+recover 0.1초 폴링 463표본) — "MCP execute_ibl 은 결말까지 돌려주지 않는 동기 호출이라 실행 중 표본은 HTTP 로만"이라고 스스로 적음. execute_ibl 1회는 결과 JSON 재독(0.58초, `self:read`).
판정(`ai_out/report.json`): step 역행 0/463 · 행 1..N 범위 · S3 실패 지점 보존 · S5 얼음 · note 좌표 ○ — 훈련자와 **전건 일치**. 추가 관측도 일치: "parallel:3 each 는 실행 단계에서 PARALLEL_RESOURCE_CONFLICT 거절(check 는 통과)" · "S7 의 step 은 each 2500행 동안 증가하지 않음, 좌표가 step 1 로 남음" · "S1 행당 4.4초(부하)". 미확인으로 남긴 것: 재사용의 '새 읽기 호출 0' 카운터(**봉투 `reuse.reused_calls` 를 못 찾음** — 훈련자도 v1 에서 `receipt_reused` 를 찾다 같은 자리에서 미끄러짐, L100-4).
**채팅 표면(b)**: 이 턴은 `_owned_turn("rehearsal")` 로 `conversation_turns` 에 턴을 열고(`legacy-…` 세션), DB 폴링 관측기(`ai_observe_db.py`, 0.5초 ×433초)가 그 턴의 `progress` 칸을 읽었다 — **전 구간 빈 문자열**(전이 0). 같은 시각 `trajectory_event` 에는 `supervision.progress`(step 1 self:read) 1건이 있다 → 버스 신고는 났으나 **HTTP 턴에는 진행 수신자가 없다**(진행 수신자 `make_progress_sink` 는 WS `chat_streams` 에만 설치, L100-5). 사건은 `handoff.tool_start/result` 27쌍만 기록.

### 3.4 시간 — 회귀인가 부하인가
| 측정 | 부하 중(00:52, load 19) | 부하 뒤(01:02, load 3.7) | 99 참고 |
| --- | --- | --- | --- |
| 순수 `return 1+1` | 0.55~0.78초 | **0.28~0.34초** | — |
| `self:read` 1회 / 3회 | 0.6 / 0.65초 | **0.32 / 0.39초** | S4a(읽기3+잠들기2.5) 3.31초 |
| `self:script` 잠들기 0 | 1.7~9.0초 | **1.0~1.2초** | — |
| S1(스크립트 6×0.7초) | 14.6초 | 9.3초 | 6.9초 |
| S4a | 5.1초 | 3.8초 | 3.3초 |

읽기 3회 ≈ 읽기 1회이므로 **액션당 고정 비용의 회귀는 없다**. 스크립트 호출당 약 0.3~0.4초(S4a 기준 +0.5초)가 99 보다 더 걸리는 것은 관측되나, 측정 시각 load 가 아직 3.7 이고 세대가 다르므로 **미확정**(다음 유휴 창에서 같은 프로그램으로 재측정 과제).

## 4. 발견
| 번호 | 분류 | 내용 | 근거 |
| --- | --- | --- | --- |
| **L100-1 ★★** | 언어 정책(10-27 설계) + 안내 공백 | 병렬 가지(each parallel>1·`&`)에 **효과 미상 호출**(`[self:script]{path}` 등)이 있으면 `admit()` 이 PARALLEL_RESOURCE_CONFLICT 로 거절 — 99 되먹임에서 돌던 S1/S2/S3/S6 병렬판이 전부 안 돈다. 설계 문서(NEXT_DESIGN_AUDIT §11 "불투명 스크립트 병렬 예시는 명시 순서로 이행", A4)가 택한 **의도된 정책**이며 등록 스크립트의 `effects` 선언(script.md)이 통로다. 다만 ① `check:true` 는 **아무 말 없이 통과**하고 실행에서만 거절(A1) ② 메시지 "순서를 명시하세요"에 수단이 없음 ③ `conflicts(strict=)` 인자가 본문에서 쓰이지 않아 A4 의 "strict opt-in" 서술과 코드가 어긋남 ④ 99 subjects README 가 병렬을 약속 | A1·A2·A6·S1~S6 병렬 거절, `ibl_v2_access.admit` |
| **L100-2 ★** | 구현 공백 | 가지별 **다른** 파일에 쓰는 병렬 each 가 항목이 **숫자**면 거절(`f"…${$it}"`·`text($it)` 모두) — 글자 항목은 통과(B1·B4·E2). 원인: `infer(int)` 가 리터럴 없는 Number 를 돌려주고(`ibl_v2_types.infer`), `text()`·f-string 이 Number 리터럴을 Text 리터럴로 옮기지 않아 admit 의 가지별 자원이 미해소. 설계 "독립 자원의 병렬성은 보존한다" 위반 | B2·E3 vs B1·E2 |
| **L100-3 ★** | 표면 정직성 | 순수 each(또는 재사용된 읽기 뒤 계산) 동안 좌표가 **마지막 액션**(`step 1 self:read`)으로 남아 note 가 "self:read 진행 중"이라 말한다 — 읽기는 끝났거나(S7a) 아예 재사용돼 실행되지 않았다(S7b). 또 같은 액션 3연속 신고가 0.25초 접기에 삼켜져 step 이 1 에 머묾(실제 3). 재사용 호출은 좌표에 표시가 없다 | S7a/S7b 스냅샷 13·11(v2) |
| L100-4 | 교재 손잡이 | 재사용 수는 봉투 `reuse.reused_calls`(+`skipped`) 인데 ibl.md 는 `receipt_reused` 증거만 말한다 → 훈련자 v1·독립 AI 둘 다 못 찾음 | S7b 봉투·AI unverified ② |
| **L100-5 ★** | 이음새 미배선 | `/system-ai/chat`(HTTP·훈련 표식 경로) 턴은 conversation_turns 에 열리지만 진행 수신자가 없어 `progress` 가 영원히 빈 칸 — 10-26 이음새는 WS 경로만 | ai_observe 전이 0 vs supervision.progress 1 |
| L100-6 | 운영 | 타 세션 편집→개발 세대 교체가 훈련 중 실행에 "접수 중단" 거절을 넣었다(1차 병렬3 S5~S7). 거절 자체는 정직(거짓 성공 0) | runs/p1_v1_병렬3 |
| L100-7 | 작성 마찰 | 평문 `"w_{$it}.txt"` 는 보간이 아니라 글자(보간은 `f"${…}"` 만) — 전 행이 같은 파일에 써 PARALLEL_WRITE_CONFLICT 가 **옳게** 났다. 그러나 평문 안 `{$이름}` 에는 경고가 없다(`LITERAL_DOLLAR` 는 `$a.b` 만) | C1·D1~D4(내 오기) |
| — | 비용 | 스크립트 호출당 +0.3~0.4초(미확정, §3.4) | 미확정 |

철회: 보간 거짓 충돌(C1/D1) — 내 문법 오기. 84 TYPE — 엄격화(§3.1).

## 5. 개선 방향(공통 능력)
L100-2 리터럴 전달(int → `text()`/f-string) · L100-3 접힌 좌표를 beat 앞에서 흘려 보내고, 액션 없는 each 는 "계산 중", 재사용 호출은 "(재사용)" 표시 · L100-1 ①② 검사 단계 경고 + 메시지에 수단 · L100-5 HTTP 턴에도 같은 진행 수신자 · L100-4/7 교재·경고 한 줄. **L100-1 정책 자체(불투명 스크립트 병렬 금지)는 언어 개정 사항 — 사용자 판정 필요**(수리 턴은 정책을 바꾸지 않고 ①②③④만 다룬다).

## 6. 비용·낭비 검토
훈련자: 작성 v0→v2 약 10분(S7 추가·키 보정), 실행 6회(검사 1·v1 2·v2 2·보정 2)+탐침 30여 회(2~10초), 모델 0. 독립 AI 431초·입력 3.8M(캐시 95%). 운영: 재기동 대기 누적 약 4분, 1차 병렬3 재실행 1회. **낭비 후보**: 내 보간 문법 오기로 탐침 8회 — 교재가 `f"${}"` 를 한 줄로만 말해 찾기 어려웠다(L100-7 경고가 있었으면 첫 검사에서 잡힘). 필요했던 비용: 부하 전후 2중 측정(시간 회귀 오판을 막음).

## 7. 수리와 되먹임 (01:08~01:30, 사용자 "발견된 개선점들을 수리해줘")

**수리 5건 + 교재·명세 4줄(공통 능력, 새 낱말·op·인자 0). L100-1 의 정책 자체(불투명 스크립트의 병렬 금지)는 바꾸지 않았다 — 언어 개정 사항이라 사용자 판정으로 남긴다.**

| 발견 | 수리 | 관문 |
| --- | --- | --- |
| L100-2 | `ibl_v2_access.runtime_type` 가 정수를 리터럴 Number 로(admit 의 가지별 자원 재료) · `ibl_v2_analysis.builtin_type('text')` 가 글자·정수 리터럴을 Text 리터럴로 전달 · `ibl_v2_compile` f-string 보간의 정수 리터럴 부분을 글자로 | `test_ibl_v2_access` +3(`f"k${$it}"`·`"k"+text($it)` 병렬 3가지 동시 성공, 같은 자원이면 여전히 거절) · 라이브 F1·F2 `[1,2,3] >> each{parallel:3}` 쓰기 성공 |
| L100-1 ①② | 컴파일 `each`(parallel>1)·`&` 가지에 효과 미상(`unknown`) 호출이 있으면 경고 `PARALLEL_RESOURCE_UNKNOWN`(HINTS 포함) · `admit` 거절 메시지에 수단(순차·글자 자원·효과 선언 등록 스크립트) | `test_unknown_effect_in_parallel_is_warned_at_check_time`(each·`&`·순차 무경고·실행 거절 메시지) · 라이브 F4(S2 check 경고)·F5(메시지) |
| L100-3 | `Runtime._report_action` 이 접힌 좌표를 보류(`_progress_pending`) → 액션 없는 each 의 beat 앞에서 `_flush_pending_coordinate` · each 둘째 행부터 beat detail `phase:"compute"` · 영수증 재사용 분기에서 `_report_reused`(좌표 `reused:true`) · `ibl_progress.report_step(reused=)` 는 참/거짓을 늘 실음(병합 잔류 방지) · `spill.ticket_beat` 는 phase 를 그 beat 의 것으로 · `_progress_note` "step N action(재사용) 뒤 · each i/N행 계산 중" · `chat_streams` 표면 계약에 `reused` | `test_each_progress_visibility` +3(기본 접기 간격 그대로: 읽기 3연속 뒤 순수 each → 첫 beat 에 step 3·둘째 행부터 compute·note; note 렌더; beat phase 비잔류) · 라이브 §7.1 |
| L100-5 | `conversation_sessions.progress_sink(binding)`/`clear_progress` — WS 수신자와 같은 규율(좌표 기억·beat 0.2초 접기)로 `conversation_turns.progress` 를 직접 갱신 · `api_system_ai._process_turn` 이 `_owned_turn` 안에서 `register_progress_sink(task_id, …)`, finally 에서 해제·비움 | `test_progress_to_chat` +2(현재값·접기·비움 / 버스 등록→report_step 수신) · 라이브 §7.2 |
| L100-7 | 평문 문자열의 `{$이름}`·`${…}` 에 경고 `LITERAL_BRACE` | `test_plain_string_brace_is_warned` · 라이브 F6 |
| L100-4 | `ibl_composition_tools.md` 한 줄(재사용 수는 봉투 `reuse.reused_calls`·`skipped`) | — |
| 문서 | `ibl.md` 병렬 자원 정책 한 줄(정수 항목 자원 정체·효과 미상 거절·검사 경고) · `ibl_composition.md` each 절 한 줄(순차/등록 스크립트·가지별 글자 경로·평문 중괄호) · `technical.md` 진행 신고 규약 · subjects README 정정 · changelog | 가이드 예산 34,475/36,000B · `check_file_size`·`build_ibl_nodes --check`·`check_backend_layers` 통과 |

시험: 관련 16파일(`test_progress_to_chat`·`test_ibl_v2_access`·`test_each_progress_visibility`·`test_spill`·`test_api_system_ai`·`test_conversation_sessions`·`test_ibl_v2_{compile_rows,preflight,requirements,completion,call_analysis}`·`test_ibl_honesty`·`test_surface_ticket_recovery`·`test_ibl_migration_completion`·`test_long_completion`·`test_ibl_run_journal`) 종료 0, 실패 0(점 집계 413 통과 — addopts -q 와 겹친 -qq 로 요약 줄 생략). 비system 전수는 미실행(타 세션이 같은 작업 트리에서 pytest 를 돌리는 중 — 기록만).

### 7.1 되먹임 — 같은 `p1_v2.ibl` 기본, 수리 후 세대 `73259f49…`(01:28, 40.8초, 모델 0)
S1 6/6 · S3 4/6(last_row 4) · S4a/b · S5 · S6 3/3 전부 수리 전과 같음. **S7a**: 첫 beat 부터 `step 3 self:read 뒤 · each 67/2500행 계산 중`(수리 전 `step 1 self:read · … 진행 중`), 둘째 행부터 전 스냅샷 compute. **S7b**: `step 3 self:read(재사용) 뒤 · each 330/2500행 계산 중`, `reuse.reused_calls 3`. S2 는 정책대로 거절(새 메시지). 판정 전 탐침 달성(S2 제외 — 정책).

### 7.2 L100-5 라이브 — 표식 있는 HTTP 턴의 채팅 progress
`POST /system-ai/chat` `origin:"training"` background 로 4행 each(스크립트 1.5초) 프로그램을 execute_ibl 로 실행하게 함(task_sysai_2d231b99, ep5560, 18.8초, 도구 1). DB 관측기(0.5초): 턴 `6cdd456f…` 의 `progress` 가 **step 2→5 self:script · row 1..4/4**(reused:false) 로 4번 바뀌고 턴 종료와 함께 비워짐(null). 수리 전(ep5559, 433초) 전이 0 → 수리 후 전이 4. `ai/ai_sink_observe.json`.

### 7.3 남긴 것
- **L100-1 정책 판정(사용자)**: 불투명 `[self:script]{path}` 의 병렬 실행 금지를 유지할지. 유지하면 99 subjects S2·병렬 변형은 영구 "정책 거절"이고, 병렬이 필요한 스크립트는 효과 선언 등록 스크립트로 옮겨야 한다(script.md). 또 `ibl_v2_access.conflicts(strict=)` 인자는 본문에서 쓰이지 않아 A4 문서의 "strict opt-in" 서술과 코드가 어긋난다(코드 소유 세션이 활동 중이라 손대지 않음).
- 시간: 스크립트 호출당 +0.3~0.4초 미확정(유휴 창 재측정 과제). 수리 후 기본 40.8초(수리 전 46.8초, 부하 차이 범위).
- 운영: 송신기 종료 키 오류(`status` 대신 `state`) → ai_run.json 32MB 를 요약으로 교체(`ai/ai_run.json` sender_note). 타 세션 동시 편집 중 재기동 5분 3회 — `gate.py` 관문 없이는 실행 사이에 세대가 바뀐다.
- 미커밋(사용자 미지시): backend 9파일·시험 3파일·교재/명세/기술문서/changelog·원장·round_100 폴더. 커밋은 pathspec 으로만 — 작업 트리에 타 세션의 `spill.py _root`·`restart_*`·`execution_trace*` 변경이 함께 있다.

## 8. 수리 재감사와 추가 수리 (2026-10-28)

대상은 정본 main의 `bb4959d5`다. §7.3의 미커밋·정책 판정 메모는 당시 상태이며,
이번 감사는 불투명 파일 스크립트의 병렬 거절 정책을 유지한다. §7의 순차 수리와 HTTP 배선은
유효하지만, 병렬 진행과 실제 채팅 표시까지 수리가 끝났다고 볼 수는 없었다.

### 재현과 수정

- **L100-3 후속: 늦은 재사용 신고의 역행.** 실제 Runtime의 병렬 읽기 두 개를 먼저 실행하고
  영수증으로 다시 실행했다. 첫 가지의 영수증 회수를 늦추면 좌표가 `1→2→2→1`로 역행했다.
  번호 할당·접힌 좌표·신고 발행을 한 잠금으로 순서화하고, 이전 호출의 재사용 신고는 최신
  좌표를 덮거나 최신 보류 좌표를 지우지 않게 했다. 실행 자체는 잠그지 않는다.
- **L100-3 후속: 다른 가지의 액션이 실행 중인데 끝난 것으로 표시.** 읽기 한 개와 순수 each를
  병렬로 실행하면 읽기가 아직 대기 중인데 `phase:compute`가 나왔다. 실행 중인 호출을
  추적해, 다른 가지의 호출이 남아 있으면 마지막 액션이 끝났다는 표시를 내지 않는다.
- **L100-3 후속: 채팅 표시 누락.** React의 WS 수신·세션 복원에서 `reused`를 버렸고,
  도구 카드가 `phase=compute`를 내부 키 그대로 표시했다. 두 진입점의 값을 보존하고
  카드에 `재사용`·`계산 중`을 표시한다. 실제 React 컴포넌트 렌더 검사로 확인한다.
- **L100-5 후속: 수신자 중복과 종료 경계.** HTTP/WS의 좌표 기억·beat 접기·발행을
  `supervision_bus.ProgressSink`로 통합했다. 발행 순서를 보존하고 해제 시 진행 중 발행을
  마친 뒤 닫아, 이미 잡혀 있던 늦은 콜백이 진행을 되살리지 못한다. 턴 마감도 progress를
  비운다. HTTP 라우트의 성공·실패 양쪽에서 진행 수신과 해제를 검증한다(모델은 대역).
- **L100-1 정리.** 효력 없는 `conflicts(strict=)` 인자를 제거했다. 기본·composition 모드
  모두 미선언 쓰기를 거절한다는 검사를 유지한다. 설계 A4는 §11 수리 전 관측임을 명시했다.
  불투명 스크립트를 순수하다고 바꾸거나 자동 순차화하는 우회는 추가하지 않았다.

### 실행 검증 범위

수리 전 회귀 2건이 실패하는 것을 확인했고, 수정 후 같은 재현을 통과했다.
원본 `subjects/s7_reuse_pure.ibl`은 변경 없이 실제 읽기·저널·재사용 경로에서
0·25·2,500행으로 실행했다. 결과를 독립 기대값과 대조하고 재사용 읽기 3회,
each 앞 최신 좌표와 재사용 표식을 확인했다. 등록 스크립트의 대안도 임시 등록 원장과
실제 Python 프로세스로 6행/parallel:3을 실행해 결과 순서와 동시 진입을 확인했다.
실제 사용자 등록 원장은 변경하지 않았다.

상설 회귀 위치는 `test_ibl_v2_runtime`(역행·병렬 계산·S7), `test_ibl_v2_access`
(기본 거절·등록 스크립트), `test_progress_to_chat`(발행·마감·React 렌더),
`test_api_system_ai`(HTTP 성공·실패 배선)다.

처음에는 로컬 8765 백엔드가 응답하지 않았으나 05:00에 ACTIVE·healthy를 확인했다.
활성 세대의 변경한 backend 5파일이 작업 트리와 바이트 단위로 같음을 대조하고,
원본 `p1_v2.ibl`과 HTTP 관측기를 변경 없이 재실행했다. 기본(2,500행) 41.62초,
병렬 변형(1,000행) 22.53초, 예산 경계 변형(5,000행) 25.94초로 모두 종료했다.
기본의 S2, 병렬 변형의 S1/S2/S3/S6은 현행 정책대로 거절되고, 나머지는 기존 조건을
충족했다. 5,000행의 S7a/S7b는 기본 steps 예산 100,000을 초과해 정직하게 실패했으며
성공으로 세지 않았다. 세 실행 모두 관측 좌표 역행 0, 모든 하위 티켓 done, 읽기 재사용
3회와 `step 3 self:read(재사용) 뒤 … 계산 중`을 확인했다. 원본 관측기의 옛 판정 문자열
(정책 거절을 회차 미달로 표시)은 보존하고, 현행 계약 판정을 별도로 대조했다.
원자료는 `outputs/l100_audit/`, 검증 요약은 [audit.json](audit.json)에 보존한다.
실제 모델의 독립 AI 되먹임과 Electron 실창 표시는 재실행하지 않았다. HTTP 모델 대역·
React 렌더와 실제 IBL HTTP 실행을 구분하며, 이번 시간 수치를 성능 개선으로 주장하지 않는다.


### 최종 관문

- 변경 관련 검사 105개 통과, 관련 시스템 검사 56개 통과, 검사 대역 보완 후 관련 두 파일 23개 통과(각 종료 0).
- 비system 전수: 10,967개 통과·9개 건너뜀, 실패·오류 0(종료 0).
- TypeScript(`tsc -p tsconfig.app.json`), 어휘 파생물 검사, backend 층 검사, 파일 크기 검사 통과. Android 몸 번들 재생성 후 정합 확인.
- 중간 전수의 두 실패는 검사 전제 문제였다. 등록 스크립트 시험은 남은 작업까지 세 개씩 동시에 시작한다고 가정해, 정상적인 꼬리 순차 실행에서 barrier가 깨졌다. 첫 세 작업의 겹침만 요구하도록 고쳤다. 기존 수리 정책 시험은 앞선 task origin을 이어받아 설정 없는 runner 대역으로 미완료 보존에 진입했다. 사용자 문맥·runner 설정을 명시하고 blocked 보존도 검증했다. 제품의 실행·수리 정책은 바꾸지 않았다.
- 첫 전수는 샌드박스의 브라우저·소켓·프로세스 접근 제한 아래 132 실패·34 오류였고, 같은 검사를 제한 밖에서 재실행한 위 결과로 판정했다. 첫 시스템 검사 56개는 항목 자체가 통과했으나 감사 중 문서·시험 추가를 저장소 변경 감시가 감지해 종료 1이었다. 변경을 멈춘 재실행은 56개·종료 0이다.


## 9. 기본 예산 후속 수리 (2026-10-28)

사용자 요청: 기본 예산을 합리적으로 올리고 5,000행이 예산 지정 없이 완주하는지 확인.
§8의 예산 거절은 차단 동작의 확인이며 기본값의 적절성을 입증하지 못했다.
원본 S7의 5,000행을 기본 예산으로 실행하는 회귀를 추가해 수리 전
`BUDGET steps 100001/100000` 실패를 재현한 뒤, 단계 기본값을 **10만 → 100만**으로 올렸다.

기준은 기본 반복량 1만 행에서 행당 여러 식을 계산할 여유를 주는 것이다.
이 프로그램은 5,000행 170,067단계, 1만 행 340,067단계를 썼다. 새 기본값은 각각
약 5.9배·2.9배의 여유가 있다. 이 프로그램에 맞춘 행 수 분기나 특례는 없으며,
단계 계수 방식·기본 반복 행 1만·깊이 64·요청 최대 1,000만 단계/10만 행은 유지한다.
명시적 작은 steps/rows는 여전히 초과 즉시 실패한다.

`capabilities().v2_budget`와 모델 도구 설명은 Budget의 실제 기본값·최대값을 읽는다.
도구 설명에 남아 있던 최대 100만 오류도 고쳤다(실제 최대는 1,000만).
전체/압축 프롬프트·IBL 명세·조합 교재의 기본값도 함께 맞췄다.

원본 `subjects/s7_reuse_pure.ibl`을 수정하지 않고 실제 읽기·저널·재사용 경로에서
0·25·2,500·5,000·10,000행을 검증했다. 모든 요청에서 budget은 생략했으며,
독립 합산 기대값·행 수·재사용 읽기 3회·진행 좌표를 확인했다.
HTTP 실행도 5,000행 최초 3.80초/재사용 3.74초, 1만 행 6.47초로 완주했다.
5,000행 결과 `n:5000,s:62308`, 1만 행 `n:10000,s:127309`는 Python으로 독립 대조했다.
활성 세대의 변경 backend 3파일이 작업 트리와 같음을 확인했다.
원자료 `outputs/l100_budget/`, 요약 [budget_audit.json](budget_audit.json).

관련 런타임·교재 검사 114개 통과. 추가한 작은 예산 검사에서 오류 문자열과 구조화 진단의
자리를 잘못 짚은 부분을 고쳤고, 압축 프롬프트는 기존 4,200자 예산 안으로 문장을 줄였다.

첫 전수는 10,970 통과·9 건너뜀·1 실패였다. 유일한 실패는 6회차 원본 정규화 검사가 기본 예산에서 실패해야 한다고 가정한 자리였다. 현재 기본값에서 성공하는 것이 요청한 변화이므로, 명시적 10만 단계에서는 실패·30만 단계에서는 2,698행 및 금액 합계가 일치·기본 설정도 같은 결과로 완주하는 검사로 보완했다. 제한 검사를 제거하지 않았다.

두 번째 전수는 10,983 통과·9 건너뜀·1 실패였다. 검사 중 다른 세션이 추가한 `test_long_sentence_verify_coords.py`에 직접 실행 진입점이 아직 없어 `test_single_runner`가 거절했다. 이후 그 세션의 `2c51a4aa` 커밋에 진입점이 포함됐고, 두 관련 파일 18개는 재검사에서 통과했다. 예산 구현은 이 과정에서 변경하지 않았다.

최종 검증: 비system 전수 10,985개 통과·9개 건너뜀, 관련 시스템 56개 통과. 개별 시험의 실패·오류는 0이나 전수 명령은 동시 편집 감지로 종료 1이다(관련·시스템 검사 종료 0). 어휘·교재 파생 정합 검사와 Android 몸 번들 재생성, 파일 크기 검사도 통과했다.
