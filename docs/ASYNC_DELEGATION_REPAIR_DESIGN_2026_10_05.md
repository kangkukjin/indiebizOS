# 비동기 실행과 조건부 위임 수리 설계

상태: **구현 반영(2026-10-05).** 아래 '결정' 절은 구현과 일치하며, 검토 과정에서 제외한 항목은 '제외한 것'에 남겼다.
작성일: 2026-10-05. 조사 기준: 정본 main `3b07ff7e`와 17회차 실행 기록. 검토: 설계 검토 2회(Fable·Codex), 범위 축소 뒤 구현.
독자: 수리 구현자와 설계 검토자. 목적 정본은 [IBL 진화 목적](IBL_EVOLUTION_PURPOSE.md)이다.
회귀: `backend/test_delegation_tasks.py`. 공통 모듈: `backend/cognition/delegation_tasks.py`.

직접 수행을 기본으로 유지하면서, 독립된 작업의 분업이 품질이나 완료 시간에 도움이 될 때
위임할 수 있도록 한다. 그 전제로 작업 접수부터 결과 회수까지의 계약과 훈련 격리를 먼저
고치고, 그 위에서 "사용자가 요청하지 않으면 절대 위임하지 마세요"를 조건부 허용으로 바꿨다.
새 위임 횟수나 병렬 작업 수는 성과가 아니다. 결과 품질, 사용자가 기다린 시간, 부모와 자식의
전체 모델 비용으로 판단한다.

## 문제와 사용자 의도

사용자가 초기 개발 때 자동 위임을 제한한 이유는 AI가 스스로 처리할 수 있는 일까지 다른
에이전트에게 떠넘겼기 때문이다. 이 문제를 다시 만들지 않아야 한다. 동시에 독립적인 조사나
검증을 맡기고 원래 실행자가 다른 필수 작업을 진행하는 분업은 열어 둘 필요가 있다.

옛 문구는 위임의 이득 대신 사용자가 위임을 명시했는지를 기준으로 삼아, 짧은 작업을
떠넘기는 행위와 유효한 병렬 분업을 함께 막았다. 문구 단순 삭제나 모든 복잡한 과제의 자동
위임은 채택하지 않았다.

## 조사에서 확인한 사실

| 확인한 사실 | 근거 | 수리 |
| --- | --- | --- |
| 시스템 AI에 사용자 요청 없는 위임을 금지하는 문구가 주입된다. | `fragments/10_system_ai_delegation.md`, `prompt_builder.build_system_ai_prompt` | 조건부 정책 문안으로 교체(아래) |
| background 응답은 접수 문구이며 작업 ID를 돌려주지 않는다. 런처는 이전 메시지 번호보다 새로운 답을 찾아 회수한다. | `api_system_ai.ChatResponse`, `launcher_app_autopilot.apPollAssistant` | 작업 선발급·접수증(`task_id`·`status_url`)·작업 조회 GET·런처는 그 작업의 종료로 판정 |
| background 워커의 예외는 `traceback.print_exc` 로만 사라진다. | `api_system_ai.chat.background` 분기 | 예외를 작업 `failed`(원인=`result`)와 assistant 메시지로 남김 |
| 타 프로젝트 위임은 mode 분기보다 먼저 비동기 위임기로 들어가 `cross + sync` 도 접수 응답만 반환했다. | `routing_system._delegate_unified` | cross 도 접수 뒤 같은 task 를 기다림 |
| 같은 프로젝트의 sync 는 임시 AIAgent 를 만들어 async(상주 러너)와 실행기가 둘이었다. | `routing_system._agent_ask_sync` | 은퇴. sync = 같은 접수 경로 + 같은 task 대기 |
| 훈련 출처가 타 프로젝트 위임 메시지에 전달되지 않는다. 순환 위임 방지가 없다. | `system_ai_tools._execute_call_project_agent` 의 `msg_dict`, 위임 코드 네 곳 | 봉투(origin·조상 사슬) 전파, 조상 사슬 소속으로 순환 거절 |
| 기존 task 결과는 500자로 잘려 저장된다. | 두 저장소의 `complete_task` | 전문 저장. 표시용 발췌는 소비자가 자른다 |
| 자식 응답을 받을 때마다 카운터를 빼고 목록에 붙여 중복 통지에 취약하다. | `decrement_pending_and_update_context` | `record_child_response` — child_task_id 별 한 번 |
| 17회차 변형 실행 중 훈련자가 다른 작업을 계속한 것은 셸 작업의 겹침이며 위임 사용 증거가 아니다. | `world_pulse.db` ep4334·4336 | 절감으로 세지 않음 |

코딩 앱(`api_coding`, 10-02)에는 이미 task·runs·events(`sequence/after/next` 커서)·cancel 계약이 있다.
첫 설계안은 이를 빠뜨리고 별도 `revision/after_revision` 을 제안했다 — 검토에서 바로잡아 **상태 투영의 결과
모양과 경로 형태는 코딩 앱을 따르되 저장소와 업무 구조는 섞지 않는다.** 이벤트 API 에는 제한 대기가 없으므로
작업 조회 GET 에 서버 상한이 있는 `wait` 만 더했다.

## 결정 (구현과 일치)

### 접수증과 상태 투영
HTTP background 와 `[others:delegate]` 는 같은 모양의 접수증을 돌려준다.
```json
{"success": true, "accepted": true, "task_ref": {"owner": "fixture", "task_id": "task_…"},
 "run_id": "run_…", "state": "queued", "status_url": "/projects/fixture/agents/agent_x/tasks/task_…"}
```
owner 는 `system`(시스템 AI 저장소) 또는 프로젝트 id(프로젝트 저장소). 조회는 실행을 만들지 않는 GET
`/system-ai/tasks/{id}` · `/projects/{p}/agents/{a}/tasks/{id}` 이며 `?wait=`(초, 상한 30)으로 종료까지
제한 대기한다. 경로의 agent 는 저장된 `delegated_to` 와 대조한다. 투영 상태는
`queued/running/waiting_children/succeeded/failed/cancelled`, 수리 대기 상태(`waiting_user` 등)는 원문 보존.
`result` 는 종료 상태에서만 전문(실패면 `error`). 완료 상태와 업무 달성 판정은 분리한다.
기존 `response`·`timestamp`·`provider`·`model` 은 유지한다(구버전 클라이언트).

### 접수 순서
1. 호출자·대상·입력을 검증한다(순환 사슬 포함).
2. 실행 전에 task 행과 부모 연결·mode 를 영속 저장한다(HTTP background 도 선발급).
3. 동기는 같은 task 를 기다리고, 비동기는 같은 task 의 접수증을 돌려준다.
4. 부모는 자식 응답을 child_task_id 별 한 번만 반영한다. 통지는 신호이고 상태의 정본은 저장소다.

### 동기 위임
접수 뒤 `delegation_tasks.await_child` 가 자식 task 의 종료를 기다린다(기본 상한 600초, 모듈 값).
끝나면 `called_agent` 플래그를 접수 전 값으로 되돌려 결과를 손에 든 부모 턴이 "위임 중"으로 열려
있지 않게 한다. 시간이 끝나면 실패·취소로 바꾸지 않고 현재 상태와 같은 task 를 돌려준다.
접수 때 부모 원장의 위임 항목에 `mode:"sync"` 가 기록되고 보고기는 그 자식을 부모 러너에 통지하지
않는다(대기자가 회수). 시간 초과 정산 `settle_sync_delegation` 은 보고기의 판정과 같은 배타 트랜잭션에서
"응답이 이미 있으면 그것을 쓰고, 없으면 mode 를 async 로 바꿔 이후 보고가 평소대로 전달되게" 한다 —
응답이 두 번 쓰이거나 사라지는 창이 없다.

same 의 sync 도 async 와 같은 접수 경로(상주 러너)를 쓴다. 대상 에이전트가 실행 중이어야 하는 점은
async 와 같다(옛 임시 실행기는 멈춘 에이전트에게도 닿았다 — 받아들인 변경). 옛 sync 가 풀던
`프로젝트/에이전트` 표기는 cross 접수로 보내 도달 범위를 유지한다. 작업 문맥이 없는 호출은 부모 없는
자식 행(`requester_channel:"pipeline"`)을 만들어 기다릴 task 를 항상 남긴다.

### 봉투와 순환 차단
부모가 자식에게 넣는 메시지에 `origin`(서버가 실행 문맥에서 정함, 모델이 바꾸지 못함)과 `chain`(조상
행위자 식별자 목록)이 실린다. 수신 루프(에이전트·시스템 AI 러너)는 `delegation_tasks.received` 로
처리 동안 두 칸을 세우고 끝나면 복원한다 — 에피소드 시작보다 먼저여서 `training` 이 위임을 지나도
자식의 에피소드·대화(`rehearsal` 스레드)·CLI 세션(`@rehearsal`)이 실사용과 갈린다. 재위임은 대상이
사슬에 있으면(자기 자신 포함) 접수를 거절한다(`error_type:"delegation_cycle"`). 깊이 숫자 설정은 두지 않는다.

### 실패 전파
자식 처리 중 예외는 자기 task 를 `failed` 로 닫고 부모에게 `failed:true` 응답으로 보고한다. 병렬 통합
보고에 "(실패)" 표식이 붙는다. 이미 닫힌 task 의 재보고는 생략한다.

### 미지원 조합
`scope=cross/system` 의 `mode=workflow` 는 구현된 적이 없다. 실행은 `error_type:"capability"` 로,
사전은 cross/system variant 의 `enums.mode:[async, sync]` 로 거절한다. 교재와 enum 은 같은 커밋.

### 조건부 위임 정책 (교체한 프롬프트 문안의 요지)
> 기본은 직접 수행. 단순하거나 짧은 작업은 떠넘기지 않는다. 독립된 하위 작업에 충분한 분량이 있고
> 전문성·독립 검증·동시 진행의 이점이 위임과 결과 통합 비용보다 클 때 위임할 수 있다. 자신이 할 수 있다는
> 이유만으로 유효한 분업을 금지하지 않는다. 입력·산출물·완료 조건과 남은 일을 분명히 하고, 위임할 때만
> 짧은 근거를 남긴다. 접수 응답은 완료가 아니다. 결과 확인·통합·완료는 원래 실행자의 책임. 사용자가
> 지정하면 그 의도를 따르고, 위임으로 권한·범위를 넓히지 않는다.

판단은 기존 실행자의 계획 안에서 한다. 별도 위임 판정 모델·사유 작성 의무·자식 수 상한은 없다.
정본: `data/common_prompts/fragments/10_system_ai_delegation.md`, `data/guides/delegation_system_ai.md`,
`data/guides/delegation_agent.md`.

### 런처 소비자
`launcher_app_autopilot`·`launcher_lite` 는 접수증의 `status_url` 로 **그 작업**의 종료를 판정한다(`wait=20`).
본문은 작업의 `result` 전문, 이미지는 같은 본문의 어시스턴트 메시지에서 찾는다. `status_url` 이 없거나
상태 투영이 아닌 응답(구버전 서버)에만 메시지 번호 폴링으로 폴백하며, 그때는 동시 작업을 식별하지 못한다.

## 제외한 것 (검토에서 범위를 좁힌 항목)

- `[others:delegate]` 에 `op=status/wait` 추가 — op 신설은 어휘 증식이다. 기존 `mode=sync`·비동기 보고·HTTP
  조회로 충족된다. 기존 경로로 안 되는 구체적 요구가 드러날 때 별도 검토.
- 동시 자식 수 상한(2개) — 근거 없는 설정. 동시성은 기존 실행 풀·수명 관리의 몫(현재 `max_workers` 상한 없음을
  확인했고 이번에 바꾸지 않았다). 재위임 깊이 숫자 대신 사슬 소속 판정.
- 멱등 접수 키·예산 예약 체계·협력 취소·재기동 뒤 `interrupted` 정리 — 이번에 보장할 동작에 필수가 아니다.
  범위 기준은 "사고가 났는가"가 아니라 "이번에 보장할 동작에 필수인가"다(background 예외 기록은 그래서 포함).
- 두 task 저장소의 통합 — 공통 투영으로 차이를 흡수. 새 작업 DB 없음.

## 검증

- `backend/test_delegation_tasks.py`: cross sync 가 같은 task 를 기다려 전문을 돌려줌(500자 초과) · cross async
  접수증 · 시간 초과 시 작업 유지와 async 정산 · same sync 가 async 접수 경로 공유(`_agent_ask_sync` 부재) ·
  작업 문맥 없는 sync · cross/system workflow 거절(실행·사전) · 순환·자기 위임 거절 · 봉투 적용과 복원 ·
  child 별 1회 반영(두 저장소) · 전문 보존과 상태 투영 · background 접수증과 실패 기록(비밀 마스킹) ·
  background 성공의 `succeeded` 조회 · 에이전트 작업 조회의 소유자 대조.
- 갱신: `test_scheduled_delegation`(접수증 모양), `test_remote_agent_images`(접수증·작업 조회 경로),
  `test_long_sentence_remaining_repairs`(선발급 리허설 채널).
- IBL 빌드 정합(`build_ibl_nodes.py --check`)·backend 층 가드 통과. 종합 회귀 수치는 changelog.log.

성능(직접 수행 대비 조건부 위임의 시간·토큰)은 측정하지 않았다. 기능이 돌아간다는 사실로 빨라졌다고
말하지 않는다. 비교는 같은 과제·모델·조건으로 따로 하며, 부모와 모든 자식의 사용량을 call ID 로 합산한다.
