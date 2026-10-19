# 79회차 — REFLEX 실행 문맥·`#reflex` 태그 이음새 입장 + 보존 궤적 비용 되먹임 + L79-1 수리

2026-10-19. 정본 `/Users/kangkukjin/Desktop/AI/indiebizOS`, 시작 HEAD `6863136c`(개정 가이드 §2·§4-5 커밋 직후), 백엔드 세대 `7c9c630b`(12:42 재기동, `#reflex` 태그 커밋 `ed5c6b8b` 포함).
과제 고정 13:26:55 KST, 훈련 13:27~13:35(훈련자+R1·R2·R3·R6), 수리 13:36~13:41(두 배치, 자동 재기동 2회), 수리 후 검증 13:41~13:46, 보고·회귀는 별도 운영 시간. 60분 상한 안.
**개정 가이드 §2 의 첫 적용 회차**: 새 분야 합성 과제 대신 ① 이음새 입장(REFLEX, 10-19 신설) ② 불변식 탐침 R1~R6 ③ 재호출 없는 보존 궤적 되먹임(4936~4947)으로 구성했다. 독립 AI 실행은 §4-5 ①·③ 조건으로 포함했고, 그 실행 자체가 탐침이다.

## 1. 과제와 조건

[task.md](task.md)에 실행 전 고정. 자료는 78회차 합성 접수 원문 사본 5개(바이트 동일, [해시](evidence/inputs_sha_before.txt)); 이음새가 자료가 아니라 실행 문맥이므로 합성으로 충분하다. oracle: 정상반납 총합 102, north R03 = 5/0, 이름순 목록 5개.
[요청 원문](requests.json) R1(무태그 목록)·R2(`#reflex` 단일 조회)·R3(`#reflex` 세 파일 합산→저장)·R4(`#execute` 영수증 인계)·R5(`#reflex` 최근 4메시지 밖 질문)·R6(`#execute` R2 짝). 전부 `/system-ai/chat` `origin:"training"` `background:true`, `status_url?wait=20` 으로 종료 회수([runs](evidence/runs.json)). 쓰기는 `ai/` 한두 파일, 외부 효과 0.

## 2. 작성 — 훈련자 전체 IBL

[base_v0.ibl](base_v0.ibl): 세 파일 읽기→`split/contains/number` 로 정상반납 수량 추출→합산→저장→재독 assert. 교재의 문자열 내장만 사용, 내부 코드 미열람, 모델 호출 0.
검사 0.33초 `ok:true, issues:[]`(도구 경계 incomplete) → 수정 0회 → 실행 0.598초 `합계 102` 저장·재독 일치. 작성 ~3분. 이 회차에서 훈련자 IBL 은 R3 의 비용 기준선 역할이다(훈련자 토큰 미측정).

## 3. 실행과 결과

### 3-1. 보존 궤적(재호출 0) — 실사용 REFLEX 8회의 사실

`#reflex` 태그 구현(10:47)보다 앞선 02:47~03:18 의 REFLEX 8회(4936~4946)는 **무의식 분류기가 스스로 고른 것**이다. 4946 "…#reflex", 4950 "부동산 보고서를 써줘. #reflex"(10:32, THINK, 입력 201만) 도 태그가 없던 때라 "태그 무시" 가 아니다. **태그는 구현 뒤 실사용 0회** — 이 회차가 첫 실행이다.

| ep | 요청 | route | 실행 호출/도구 | 실행 input | cache_read | cache_create | 시간 |
|---|---|---|---|---:|---:|---:|---:|
| 4945 | 음악을 꺼줘 | REFLEX | 1/1 | 145,828 | 81,348 | 64,476 | 22.9s |
| 4947 | 음악을 꺼줘 #execute | EXECUTE | 1/2 | 440,563 | 426,501 | 14,056 | 28.9s |
| 4938 | 음악을 꺼줘 | REFLEX | 1/3 | 287,298 | 268,463 | 18,827 | 22.4s |
| 4943 | 음악을 꺼줘 #execute | EXECUTE | 6/6 | 293,033 | 271,104 | 0 | 29.4s |
| 4936 | 삼성1 밤편지 틀어줘 | REFLEX | 1/1 | 146,994 | 84,039 | 62,951 | 60.7s(폰 40s) |
| 4946 | 삼성1 인디 음악 #reflex | REFLEX | 1/3 | 311,271 | 283,435 | 27,828 | 187.3s(폰 100s 무응답+56s 대기) |

읽기: 한 도구 왕복마다 ~95~150K 가 다시 들어간다(system 51,496자+tool_schema 13,308자+MCP 어휘). REFLEX 는 그 위에 얹히는 주 세션 이력(~150~300K)을 뺀다. 첫 격리 턴은 cache_create 63~64K(캐시가 식었을 때), 1~2분 안 연속 턴은 19~28K. 느린 폰 응답은 REFLEX 와 무관하게 벽시계를 지배했다.

### 3-2. 이 회차 실행(훈련 → 수리 → 수리 후)

| 실행 | 태그 | route | reflex 사건 | 실행 input / cache_read / cache_create | 호출/도구 | 시간 | 답 |
|---|---|---|---|---:|---|---:|---|
| 훈련자 base_v0 | — | — | — | 모델 0 | — | 0.598s | 102 ✓ |
| R1 ep4965 | 없음 | EXECUTE(분류기) | — | 266,622 / 253,291 / 13,327 | 1/1 | 28.8s | 5개 ✓ |
| R2 ep4966 | #reflex | **EXECUTE** | fallback `missing_conversation_binding` | 288,334 / 277,587 / 10,743 | 1/1 | 11.4s | 5/0 ✓ |
| R3 ep4967 | #reflex | **EXECUTE** | fallback 같은 사유 | 467,757 / 455,356 / 12,395 | 1/3 | 19.5s | 102 ✓ 입력 불변 |
| R6 ep4968 | #execute | EXECUTE | — | 334,757 / 323,925 / 10,828 | 1/1 | 26.3s | 5/0 ✓ |
| — L79-1 수리·재기동 2회 — |
| R2' ep4969 | #reflex | **REFLEX** | reflex_context(4메시지 842자) | **144,297** / 127,813 / 16,480 | 1/1 | 22.2s | 5/0 ✓, `reflex.result` #785 |
| R4' ep4970 | #execute | EXECUTE | `reflex.ack` #786(영수증 인계) | 223,094 / 204,274 / 18,814 | 1/2 | 19.6s | 해시 일치 ✓, 파일 mtime·해시 불변 ✓ |
| R5' ep4971 | #reflex | REFLEX→승격 | reflex_context + fallback `executor_needs_history`, 도구 0 | 157,186(2호출) / 130,516 / 26,666 | 2/0 | 39.8s | "north.txt"(단서 정직) — oracle loans.json ✗ |
| R3' ep4972 | #reflex | **REFLEX** | reflex_context | **293,045** / 274,864 / 18,173 | 1/3(셸 실수 1회 자가 수정) | 38.0s | 102 ✓ 입력 불변 |

태그는 분류 호출을 생략했다(R2·R3·R2'·R3' 에 phase=classify 호출 0; 남은 `oneshot:classify` 행은 capability_guard). R1 의 파일 목록 조회는 분류기가 EXECUTE 로 보냈다(보수적, 결함 아님). R4' 는 R2' 의 격리 턴 결말을 `<separate_execution_history>` 로 받고 ack 를 남겼으며 파일을 다시 쓰지 않았다.

### 3-3. 판정

검사 통과(훈련자 v0)·실행 종료(10/10 succeeded 회수)·과제 달성(R1~R4·R6·R2'·R3'·R4' 정답, R5' 미달)·불변식(R2 기대 미달→수리 뒤 R2' 충족, R4' 충족, R5' 승격 충족·답 미달, R3' 충족)을 따로 둔다.

## 4. 발견

- **L79-1 — 구현 공백(확정, 수리 완료)**: `/system-ai/chat`(원격 런처 자율주행 탭·훈련 리허설)은 대화 세션의 턴을 열지 않아 `conversation_sessions.current()` 가 없고, REFLEX 는 `missing_conversation_binding` 으로 **항상** EXECUTE 로 떨어졌다(명시 `#reflex` 포함). `reflex.result/ack` 영수증·`bind_task` 도 남지 않았다. 데스크톱 채팅 세션 경로(`api_chat_sessions → chat_runs.invoke` 의 `store.begin + scope`)만 소유권이 있었다. 재현 = R2(ep4966) fallback 사건.
- **L79-2 — 비용 상충(기록)**: REFLEX 는 같은 요청의 실행 입력을 절반 안팎으로 줄였지만(R2 288K→R2' 144K, R3 468K→R3' 293K) 벽시계는 늘었다(11.4→22.2s, 19.5→38.0s). 격리 턴은 새 CLI 세션 기동과 cache_create(16~18K, 식은 캐시면 63~64K)를 매번 낸다. 토큰 절감률을 시간 절감으로 쓰지 말 것. 실사용 짝(4945 vs 4947)에서는 시간도 줄었다(22.9 vs 28.9s) — 표본 2쌍, 일반화 안 함.
- **L79-3 — 경로 설계(기록)**: HTTP 경로의 "전체 문맥" 은 `get_history_for_ai(limit=7)` 다. R5' 가 승격한 뒤에도 R1 은 7메시지 밖이어서 보이는 범위(R3 요청문)로 답하고 단서를 붙였다. REFLEX 승격 자체는 계약대로(도구 호출 전 표식). 데스크톱 CLI 세션과 다른 경계이며 가이드 §4-5 에 적을 사실.
- 기록만: 분류기가 파일 목록 조회를 REFLEX 로 보내지 않음(R1) · 독립 AI 셸 실수 1회 자가 수정(R3') · `cognition.route` 의 `reflex:false` 키는 옛 해마 반사 뜻이라 REFLEX 판정과 이름이 겹침(표시 혼동 후보).

## 5. 수리 — L79-1

`backend/datastore/conversation_sessions.py` 에 `owned_turn(path, table, owner, task_id, on_skip)`: 같은 소유자(`system_ai`/`rehearsal`)의 현재(legacy) 세션을 `resolve` 로 찾아 `store.begin` → `scope` → `bind_task`, 성공/실패로 `finish`. 이미 실행 중인 턴이 있으면(동시 요청) None 을 내어 옛 무소유 경로를 보존하고 `conversation.binding_skipped` 사건만 남긴다.
`backend/surface/api_system_ai.py` 는 `_owned_turn(conv_thread, task_id)` 얇은 배선으로 `turn_hold` 와 함께 `_process_turn` 을 감싼다(파일 1,469줄, 1차 배치 1,503줄은 분할). 새 어휘·프롬프트·평가 모델 0. 저장·히스토리가 쓰는 `resolve` 와 같은 세션이라 영수증·대화 행이 한 세션에 모인다.
문서: `docs/MODEL_CONTEXT_POLICY.md` REFLEX 절에 HTTP 경로 소유권 문장, `changelog.log` 한 줄.
회귀 `backend/test_long_sentence_round79_repairs.py` 6건: 바인딩 열림·작업 연결·완료 마감 / REFLEX 적격이 소유 턴 안에서만 / 소유자별 세션 분리+resolve 일치 / 바쁜 세션 → None 무오류 / 실패 → failed 전파 / 배선 존재. `test_reflex_execution.py` 10건·관련 묶음(delegation_tasks·system_ai_ready·user_surface_pipeline·cognitive_consciousness) 통과, 층 가드 통과. 전수 회귀는 §7.
수리 후 실증: R2' REFLEX 경로·영수증 #785, R4' ack #786·파일 불변, R5' 승격 사건, R3' REFLEX 로 다단계 쓰기 정답. 재기동은 제어자 자동(두 배치 사이 ACTIVE 확인).

## 6. 비용·낭비 검토와 잔여

- 필요했던 비용: 보존 궤적 읽기(재호출 0으로 8회 실사용 기준선 확보), 수리 전 4실행(결함 재현·기준선), 수리 후 4실행(계약 네 가지 확인).
- 줄일 수 있었던 일: R6(#execute 짝)은 R2 가 이미 EXECUTE 로 떨어진 뒤라 정보가 겹쳤다(1실행 335K 입력). 1차 배치가 1,500줄 한도를 넘겨 재기동이 한 번 더 들었다(미리 줄 수 계산). 독립 AI 8실행 입력 합 ≈217만(캐시 포함)이 이 회차 모델 비용의 거의 전부 — 탐침 수가 곧 비용이다.
- 보존할 품질: R4' 의 재독·해시 확인, R5' 의 정직한 단서, R3' 의 자가 수정은 낭비가 아니다.
- 미검증: 데스크톱 WS 레거시 채팅(`api_websocket`) 경로의 소유권 유무, 원격 런처 자율주행 탭 실사용에서의 REFLEX 체감, 동시 HTTP 요청 때 `binding_skipped` 실제 발생, REFLEX 격리 턴 기동 지연의 원인(CLI spawn vs 캐시), 폰 실기 REFLEX. 작성자(이 세션) 토큰 미측정.
- 다음 후보: L79-2 격리 턴 기동 지연 측정 → 짧은 요청의 시간 축 개선 / L79-3 HTTP 경로 history 7 과 데스크톱 CLI 세션의 문맥 경계 정렬 판정 / 분류기의 REFLEX 선택 범위(파일 조회 포함 여부) 관측.

## 7. 전수 회귀

backend 비-system 전수(`-m "not system" -n auto --dist loadfile`): **10,836 통과·1 건너뜀·4 실패, 237초**. 실패 4건은 전부 `backend/test_media_browser.py`(Playwright 가짜 미디어 장치의 WebRTC 수신 디코드 `wait_for_function` 30초 시간 초과) — 10-13 미디어 통화 작업의 시험이며 이 회차가 바꾼 대화 세션·HTTP 채팅 경로를 지나지 않는다. 다른 세션의 미커밋 변경이 같은 작업 트리에 있어 깨끗한 트리 대조는 하지 않았다(미검증으로 남김).
직렬 실행(`-x`)에서는 `test_episode3388_repairs.py::test_http_command_without_task_runs_plan_review_final_and_mcp` 가 한 번 실패했으나 단독·병렬 실행에서 통과 — 순서 의존 후보로 기록만 한다. 운영 낭비: 직렬 전수 12분+ 뒤 중단하고 규약대로 병렬 재실행, `-q` 중복으로 합계 줄이 사라져 한 번 더 돌림(총 세 번).
