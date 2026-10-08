# 긴문장 상상훈련 28회차 — 사람 승인이 낀 영구 삭제 + 프로젝트 에이전트 위임의 접수증·취소

정본 main `051e8f82`(+27회차 미커밋 수리 27파일) 위에서 훈련했다. 훈련 단계는 사용자 지시대로 발견만 했고(§1~5), 뒤이은 판정으로 **L28-1·4·5 세 건을 수리**했다(§6). 당시 L28-2·3은 승인 설계 판정 대기였으나, 이후 `4fbde9b0`에서 핵심 재개 계약을 구현했다(§7). L28-6의 후속 부분 수리도 같은 설계 기록에 있다.
27회차가 남긴 미검증 축 둘(사람 승인 작업·프로젝트 에이전트 위임+취소)을 한 요청에 묶었다. 시작 10:53:23, 훈련 실행 종료 11:00:04(약 7분), 상한 60분.

## 1. 과제와 조건
[사전 과제](task.md) · [독립 요청](request.txt). "발표 뒤 정리": (가) 홍보/홈페이지 에이전트에 가이드 요약 위임 → 15초 대기 → 안 끝나면 취소 시도·실제 상태 보고
(나) 준비 단계에서 만든 임시 스위치 2개 **영구 삭제**(`requires.human_confirm`) — 사람 승인 왕복 (다) 보고서 저장·재독.
준비(과제 밖): `prep_switches.ibl` 로 스위치 `99acb150`·`044e43f9` 생성, 에이전트 시작(`prep_start_agent.ibl`). 사람 통로 `/ibl/approve` 는 훈련자가 '그 자리의 사람' 역할([approve.py](harness/approve.py), 발급 기록 [approvals.jsonl](evidence/approvals.jsonl)).
환경: 시스템 AI·모든 프로젝트 에이전트의 실행 모델이 claude_code/opus 인데 백엔드가 CLI 를 못 찾는다(§3 L28-5) — 위임받은 턴은 1~4초 만에 "AI가 초기화되지 않았습니다"로 끝난다.
훈련자는 `task_receipts.md`·`body_lifecycle.md`·`ibl.md`(요구 권한 절)·describe 로 작성했고, 구현(`system_tools_delegate.py`·`action_requires.py`)은 실패 원인 진단 때만 읽었다.

## 2. 작성과 실행
| 시도 | 프로그램 | 검사 / 실행 / 과제 | 새 위임 | 승인 | 비고 |
| --- | --- | --- | ---: | ---: | --- |
| 0 | [start_v0](drafts/start_v0.ibl) 1회 | 통과(승인 필요 예고 없음) / **실패** / 미달성 | 0 | 0 | "에이전트 '홈페이지'가 실행 중이 아닙니다" — 위임의 전제조건(에이전트 start)이 낱말 설명에 없다 |
| 1 | start_v0 (에이전트 시작 뒤) | 통과 / 실패 / 미달성 | 1 | 0 | 위임 접수 → `wait` 가 즉시 `unknown`(L28-1) → 삭제 1번째가 `approval_required{challenge 38b5…}` |
| 2 | start_v0 + 승인 토큰 재전송 | — / 실패 / 미달성 | 1 | 1 | **같은 프로그램이 처음부터 다시 돈다**: 위임 2번째 시작, A 삭제됨, B 삭제는 같은 challenge 로 다시 거절(토큰 1회성, L28-2) |
| 3 | start_v0 + 승인 토큰 재전송 | — / 실패 / 미달성 | 1 | 1 | 위임 3번째 시작, A 삭제가 "스위치 없음"으로 실패 → B 에 영영 닿지 못함(막다른 길) |
| 4 | 분할: [v1_delegate](drafts/start_v1_delegate.ibl) → [delete_one](drafts/delete_one_v1.ibl)(B, 거절→승인→재전송) → [report_v1](drafts/report_v1.ibl) | 통과 / 정상 / **달성(상태는 정직)** | 1 | 1 | 가 = 오류(unknown, 접수증 보존), 삭제 2건, 남은 스위치 0, 재독 일치. 과제가 요구한 "위임 1회"는 전체로 보면 4회 |
| 변형 | delete_one(없는 id `deadbeef`) | — / 실패 / 정직 | 0 | 1 | 승인을 먼저 요구하고 승인 뒤 "스위치 없음" — 사람의 승인 1회 낭비(L28-4) |
| 변형 | [v1_delegate_system](drafts/start_v1_delegate_system.ibl)(scope system) | 통과 / 정상 / 정직 | 1(시스템) | 0 | 3.3초 만에 `failed`·사유 전달(27회차 L27-6 수리 동작 확인). 취소 시도 전에 끝남 |
| 탐침 | [probe_sync_delegate](drafts/probe_sync_delegate.ibl)(mode sync) | — / 실패 / — | 큐 1 | 0 | "동기 위임의 자식 작업이 만들어지지 않았습니다 — child_task_id 가 없습니다" — **sync 는 정직하게 거절하고 async 만 죽은 접수증을 준다**. 메시지는 큐에 들어간 뒤 에이전트를 멈춰 잔류 |

[독립 대조](evidence/trainer_validation.json) 9검사 중 7 통과 — 빠진 둘은 발견 그 자체다(승인 4회 vs 보고 3회는 변형의 1회가 보고 뒤라서, 위임 4회 vs 요구 1회는 재전송 중복). [최종 보고서](../../../../outputs/long_sentence_imagination/2026-10-07_28회차/trainer/report_1.json).
훈련 뒤 되돌림: 스위치 저장소 빈 목록(준비 전과 같음), 에이전트 stop. 시스템 작업 `task_sysai_4868e0a3`(failed) 1행은 남아 있다.

### 시스템 AI 독립 실행
**실행하지 못했다.** 시스템 AI 설정이 claude_code/opus 이고 백엔드가 CLI 를 못 찾아 모든 턴이 "AI가 초기화되지 않았습니다"로 끝난다([증거](evidence/ai_blocked.json), 27회차 10:11:31 부터). 설정은 건드리지 않았다.

## 3. 발견
- **L28-1 구현 결함(접수증 계약 위반) — 같은 프로젝트 비동기 위임의 접수증이 가리키는 작업이 없다.** `[others:delegate]{agent_id, message}`(mode async) 가
  `task_ref: {kind: delegation, task_id: "LSI28", owner: "홍보"}, child_task_id: null` 을 돌려줬다 — **호출자의 task_id** 다. `[self:task]{op: status|wait}` 는 "작업 LSI28 을(를) 홍보 저장소에서 찾지 못했습니다"(unknown), `status_url` 은 404.
  에이전트는 실제로 돌았다(홈페이지 에피소드 4회). 원인(`system_tools_delegate.execute_call_agent`): 현재 task_id 가 있으면 `_create_child_task(parent)` 를 부르는데 부모 행이 DB 에 없으면 `None` 을 돌려주고, 호출자는 `new_task_id or current_task_id` 로 **부모 id 를 접수증에 싣는다**.
  영향: `/ibl/execute` 에 임의 task_id 를 주는 모든 호출자(앱 표면·훈련·외부 표면) — 작업 문맥이 아예 없을 때만 standalone 행을 만든다. `mode: sync` 는 같은 자리에서 "child_task_id 가 없습니다"로 정직하게 거절한다 — async 만 죽은 접수증이다. **"같은 일을 두 번 시작하지 마"를 접수증으로 지킬 수 없다.**
- **L28-2 구현 결함(값 계약·완료 불가) — 한 프로그램에 사람 승인 호출이 둘이면 끝낼 수 없다.** 토큰은 (주체·액션·op·요청 지문) challenge 에 1회 소비. 같은 프로그램 안의 두 `delete` 는 challenge 가 같고 토큰은 하나라
  1번째만 통과, 2번째는 **같은 challenge** 로 다시 거절. 표면이 다시 승인·재전송하면 1번째가 "스위치 없음"으로 실패해 2번째에 영영 닿지 못한다(시도 2·3). `[table:each]` 로 n 개를 지우는 자연스러운 프로그램이 n ≥ 2 에서 막다른 길.
- **L28-3 낭비(관문 자리·예고 부재) — 승인 전 부작용이 재전송마다 반복된다.** 관문은 실행 중 잎에서 걸린다. 승인 뒤 "같은 요청을 다시 보내라"는 규칙은 **프로그램 전체 재실행**이라 앞선 위임이 재전송마다 다시 시작됐다(요구 1회 → 4회, 승인 4회 → 최소 2회).
  `check: true` 는 `human_confirm` 선언을 보고도 예고하지 않는다(`ok: true, issues: []`) — 저자가 실행 전에 프로그램을 승인 단위로 나눌 근거가 없다. 가이드(`body_lifecycle.md`)는 "자율 턴에서는 휴지통으로 끝내라"만 말하고, 주인이 명시한 영구 삭제의 승인 왕복 절차(승인 단위로 프로그램을 나눈다·부작용 뒤에 두지 않는다)는 어디에도 없다.
- **L28-4 낭비(관문 순서) — 없는 대상의 영구 삭제도 사람의 승인을 먼저 요구한다.** `deadbeef` 삭제: approval_required → 승인 → "스위치 없음". 존재 검증이 관문 뒤에 있어 사람의 승인 1회가 헛돈다.
- **L28-5 환경 결함(탐색 경로) — 데스크톱 앱 동봉 Claude CLI 를 못 찾는다.** `find_claude_binary` 는 `claude-code/<ver>/claude.app/Contents/MacOS/claude` 를 보는데 실제 배치는 `claude-code/<ver>/<해시>/claude.app/…`(2.1.288·2.1.289 둘 다). PATH 에도 없어 `None` → 시스템 AI·프로젝트 에이전트 전부 "AI가 초기화되지 않았습니다". 독립 실행 불가의 뿌리.
- **L28-6 발견·학습(작은 것들)**: ① `others:delegate` 설명에 "대상 에이전트가 실행 중이어야 한다"가 없다(첫 시도 실패). ② `[others:agents]{op:"info", project_id, agent_id}` 는 "찾을 수 없습니다"인데 같은 인자의 start/stop 은 동작 — op 간 식별자 해소 불일치. start 의 result_type 이 `items: List<Record 관측 project·id·name>` 로 거짓. ③ 판본 1 파싱 실패("파싱 실패: return {a: $a.switch.id …}")에 위치·힌트가 없다(판본 2 헤더가 없다는 안내도 없음).
- 미검증: 살아 있는 위임의 `cancel`(미지원 거절 경로) — 모델이 즉시 죽어 밟지 못했다. 시스템 AI 독립 실행 없음.

## 4. 비용·낭비 검토
- **필요했던 비용**: 위임 1·스위치당 승인 1(=2)·보고서 저장·재독.
- **실제**: 위임 4(+시스템 1, 큐 잔류 1), 승인 4, 훈련자 요청 24(준비·탐침 포함). 초과분의 원인은 전부 §3 — 재전송=전체 재실행(L28-3), 토큰 1회성(L28-2), 관문이 존재 검증보다 앞(L28-4). 작성자 선택은 없다(최초 초안이 가장 자연스러운 모양이고 검사가 경고하지 않았다).
- **보존된 품질**: 거절은 전부 정직했다(승인 필요·스위치 없음·unknown·failed 사유). 취소되지 않은 일을 취소됐다고 쓴 곳 없음.
- 수리 후보(사용자 판정): L28-1 부모 행이 없으면 standalone 행(코드 1분기) · L28-2 토큰을 challenge 당 n 회 또는 프로그램 단위 승인 · L28-3 check 가 human_confirm 호출을 예고 + 가이드 한 절 · L28-4 존재 검증을 관문 앞으로(또는 핸들러가 먼저 존재를 확인) · L28-5 번들 탐색을 한 단계 더(rglob).

## 6. 수리(사용자 판정 뒤, 11:2x) 와 검증
훈련 작업·에피소드 종료와 스위치·에이전트 되돌림을 확인한 뒤 적용했다. [증거](evidence/post_repair_validation.json).
- **L28-5** `providers/claude_code.find_claude_binary`: 번들 배치를 `<ver>/claude.app` 과 `<ver>/<빌드 해시>/claude.app` 둘 다, 최신 판부터 본다(Windows 도 같은 두 모양).
  라이브: 재기동 뒤 "시스템 AI: 초기화 완료 (binary=…/2.1.289/ee67e3f1ea60/…)", 에이전트도 초기화 완료 — 위임받은 턴이 실제 요약 781자를 돌려줬다(20.1초).
- **L28-1** `system_tools_delegate._send_to_running_agent`: 호출 문맥의 task_id 에 부모 행이 없으면 부모 없는 자식 행(`pipeline` 채널)을 만들고 접수증·메시지·`child_task_id` 가 전부 그 행을 가리킨다.
  행을 못 만들면 접수하지 않는다(없는 작업의 접수증을 주지 않는다). 라이브: 같은 요청이 `task_aa95dff4` 를 받아 `status` = running, 15초 `wait` = 시간 초과 값, 자동 보고가 행을 `completed` 로 닫음.
- **L28-4** `requires.exists: "모듈:함수"`(action_requires — 사람에게 묻기 전 대상 존재 확인, 원 인자 전달, 함수 없으면 fail-closed) + `launcher_ops.switch_exists/project_exists` + `self:switch`·`self:project` delete 선언 + ibl.md·body_lifecycle.md 한 줄.
  단위 시험 통과. **파생 빌드 보류**: 다른 세션의 미추적 `data/instruments/spreadsheet.yaml` 이 빌드 검증을 막아 `ibl_nodes.yaml` 이 갱신되지 않았다 — 그 파일이 검증을 통과한 뒤 `python3 scripts/build_ibl_nodes.py` 를 한 번 돌려야 라이브에 닿는다. 그때까지 회귀 `test_switch_delete_of_missing_switch_does_not_ask_for_approval` 은 실패한다(의도된 실패 — 파생물 미갱신 신고).
- 회귀 6건 추가: `test_imagination_round28_repairs.py`(번들 탐색 2모양·최신 우선 / exists 관문 / validate 모양 / 라이브 없는 스위치), `test_delegation_tasks.py`(고아 task_id 의 자기 행 / 행 못 만들면 거절). 전수 회귀 결과는 아래 줄.
- 전수 회귀: 요약 줄 없음(진행 문자 집계: 실패 5). 실패 5건은 전부 다른 세션의 미추적 `data/instruments/spreadsheet.yaml` 검증 실패가 원인이다 — `test_vocabulary_archive.py` 3·`test_vocabulary_bundle_split.py` 1(어휘 가져오기가 같은 검증을 부른다, 이 세션 변경과 무관·단독 재실행도 같은 오류)과 위의 라이브 L28-4 시험 1. 그 파일이 검증을 통과하면 빌드 뒤 다시 돌릴 것.


## 7. 후속 승인 설계·구현 상태 (원장 정정 2026-10-09)

정본 `4fbde9b0`의 [1단계 구현 기록](../../../IBL_COMPOSITION_REPAIR_PLAN_2026_10_07.md)에 따라
L28-2·3의 승인 설계는 판정 대기가 아니다. 호출 위치·반복 순번·해석된 인자와 실행 신원에
1회 승인을 결속하고, 승인 대기는 `suspended`로 보존한다. 같은 `resume`으로 이어가면
이미 완료한 외부 효과는 영수증으로 복원한다. 전역 토큰 소비 횟수를 늘리는 안을 채택하지 않았다.

`backend/test_ibl_run_journal.py::test_two_approvals_preserve_completed_effects_and_retransmission`은
위임1회→A 승인→B 승인→완료·재전송에서 위임·A·B가 각각 한 번만 실행됨을 확인한다.
순차/병렬 반복·만료·다른 실행의 토큰·효과 불명 등의 인수 근거와 검증 수치는 위 기록을 따른다.
원래 훈련의 재전송 실패 증거는 보존한다. 이 문서의 옛 “판정 대기”는 당시 상태다.

완료 범위는 승인 재개·중복 효과 방지와 승인 화면/명세 연결이다. L28-3에 함께 기록된
`check`의 승인 사전 예고는 별도 잔여로 남긴다. 외부 서비스의 보편적 exactly-once 보증도 아니다.
