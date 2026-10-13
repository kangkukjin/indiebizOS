# 긴문장 상상훈련 63회차 — 연구 질문을 실원문 근거로 이어가고 종결하기 (+ 56회차 되먹임)

설계 [LONG_SENTENCE_ROUND63_DESIGN_2026_10_13.md](../../../LONG_SENTENCE_ROUND63_DESIGN_2026_10_13.md) · 과제 [task.md](task.md) · 원장 [LONG_SENTENCE_IMAGINATION_LEDGER.md](../../../LONG_SENTENCE_IMAGINATION_LEDGER.md).
훈련 2026-10-13 13:06~13:45 KST(상한 60분 중 39분), 정본 main `a9fd00ce`, 백엔드 세대 `5f1e74dd`. 다른 세션의 미커밋 24파일(guest-helper 계열)은 이번 이음새와 무관하며 훈련 중 재기동 0. 수리는 훈련 종료·모든 작업 종료 확인 뒤 별도.

## 1. 과제와 조건

개정 가이드 §2·§3·§6 의 첫 적용. 계기 = 10-13 `b3d26f00` 연구 질문·근거 이음새(새 낱말 0, 긴문장 사용 0회). 실자료 = 공개 arXiv 논문 8편 + 늦게 도착하는 1편(`task.md` 표, 해시 `evidence/pdf_index.json`). 연구 프로젝트 하나에 훈련자·시스템 AI·미끼 대화 셋. 공개 판정 계약은 task.md 와 같다. 되먹임 블록으로 56회차 요청문을 글자 그대로 시스템 AI 에 재실행했다.

## 2. 작성

훈련자 프로그램 셋(`programs/`): 보존·기록 `record`, 기억 없는 재개 `resume`, 늦은 논문 반영 `change`. 공통 부품 = 보존(sources 로 기존 판본 재사용→add→read), 근거(`위치||인용` 셀을 `{version_ref,extraction_revision,locator,quote}` 로, `contains(text,quote,true)` 사전 검사), 탐침([try] 로 거부를 값으로 보존), 조건탐침(효과 있는 호출을 [if:] 안에 넣는 함수).

| 판 | 검사 | 이유 |
| --- | --- | --- |
| v0 (3편) | 거절 1 | f-문자열 안 이스케이프 따옴표 — 훈련자 습관 **여섯 번째 재발**(53회차 다섯 번째) |
| v1 | record TYPE 1 + PURE_EXPRESSION 2, resume 1, change 3 | `get(맵, 숫자키)`; 효과 있는 `[fn:]` 을 삼항 가지에 둠(L10 규칙) — 조건탐침·반영저장 함수로 [if:] 안으로 |
| v2 | 통과(incomplete) | 실행: record v2 는 `table:ai` 입력 96,308자 > 60,000 상한으로 실패(아래 L63-3) |
| v3 | 통과 | 읽기 본문을 앞 3,500자로 투영, 기존 자료 재사용, `contains` exact |

작성 자료는 교재·연구 질문 가이드·계약 문서·`ibl.md`(if 문법) 와 62회차 프로그램. 내부 구현은 `read`/`validate_reference`/`notebook_operation` 을 열람했다(훈련자 기본 조건 밖, 보고).

## 3. 실행과 결과

### 훈련자 (`evidence/trainer_runs.json`)

| 실행 | 결과 | 경과 | 모델 |
| --- | --- | --- | --- |
| record v2 기본 | 실패 — table:ai 입력 상한(8편×12,000자) | 5.2초 | 0 |
| record v3 기본 | **성공** 8/8 보존(전부 기존 판본 재사용·전부 12,000자에서 잘림 신고)·질문 3·탐침 7/7 거부·중복 생성 수용(duplicate_candidates 안내)·철회 수용·종결 시도 0·재독 일치·인용 불일치 0 | 61.4초 | 2회(입력 22,662/출력 7,095) |
| resume 기본 | **성공** 입력 두 값만으로 4건 회수(이력 포함), 종결 가능 0(남은 확인 3~4건) — 정직 | 0.5초 | 0 |
| change 변형 | **성공** 논문 9 보존·q1 갱신(판본 1→2)·q2 **충돌→최신 재읽기→판본 3 재저장**·q3 **판본 1 불변**·철회된 중복 질문도 재개(훈련자 결함) | 23.7초 | 1회 |

운영자 개입: change 가 도는 동안 q2 를 사용자 자격으로 answered 종결(판본 2, objections 3건) → 프로그램의 옛 expected_revision 저장이 충돌 → 재읽기 뒤 판본 3, 내용 변경으로 자동 재개(`evidence/question_history.json`: rev1 open → rev2 resolved/user → rev3 open). 판본 사슬 지문 연결 확인.

심은 조건 10개 중 9개 기대대로(거부 7·충돌 복구·재개·무관 판본 불변). "다른 대화 자료 거부" 는 첫 미끼(논문 1)가 훈련자 대화에도 있어 같은 version_ref 였으므로 미끼를 논문 9 로 바꿔 거부를 확인했다 — **version_ref 는 내용 지문이고 대화 귀속은 captures 가 정한다**(관측, 올바른 동작).

### 관찰 C — 연구 실행 자체 (`evidence/observation_c_result.json`)

훈련자 대화에 `thread_send` 로 "기록만으로 종결 가능한 질문 판정" 요청. 연구 실행의 주 모델이 요약 목록(7,500자)만 받고도 공개 도구로 전체 기록을 읽고, 4건 모두 종결 불가로 판정, q2 에 종결을 막는 사유 2건을 gaps 로 추가(판본 4, origin agent), 반박·기존 gaps 보존. 모델이 "요약에는 3건으로 보였는데 원문은 4건" 이라며 요약 절단을 스스로 발견 → L63-5.

### 시스템 AI (`evidence/agent_runs.json`, `evidence/agent_*.md`)

| 턴 | 에피소드 | 경과 | 모델 호출 | 도구 | 결과 |
| --- | --- | --- | --- | --- | --- |
| 기본 | 4670 | 931.2초 | 8 | execute_ibl 35(거절 4) | 보존 8/8(첨부 thread_send)·질문 3·인용 23건 전건 원문 일치·**Q1 종결**(objections 4)·재독 일치·표 저장. 전부 IBL, Bash 0 |
| 재개 | 4673 | 61.5초 | 5 | execute_ibl 2 | 두 값만으로 회수, 종결 0(정직), 거부 0 |
| 변경 | 4674 | 461.7초 | 8 | execute_ibl 9(거절 2) | **보존 실패** — 첫 턴의 연구 실행이 멈춰 있어 첨부 거절, thread_cancel 도 `cancel_requested` 에서 안 끝남. 질문 판본 전부 불변(정직). notebook add 우회는 하지 않음 |

입력 토큰 합계 기본 7,141,655(캐시 읽기 6,749,572 포함 범위 별도)/출력 43,028, 재개 1,001,227/6,413, 변경 4,308,902/17,126. 훈련자 자신의 토큰은 미측정.

AI 가 관측해 보고한 것: `notebook versions` 가 보존 직후 빈 목록(→ L63-6, source_ref 없이 호출), `read_guide` 가 research_project.md 를 못 찾음(→ L63-7), 연구 실행 정지(→ L63-1).

### 되먹임 — 56회차 수리 뒤 독립 AI 재실행 (`evidence/feedback56_evidence.json`)

| | 기준선 10-11(수리 전) | 10-13(수리 후) |
| --- | --- | --- |
| 기본 | ep4604 146.8초·수집 IBL·비교 Python·**RESULT_MISSING**(L56-5) | ep4668 173.1초·execute_ibl 8·Bash 0·RESULT_MISSING 0·검사 거절 2(보간 따옴표·check) |
| 변형 | ep4605 56.5초·재검색 0·반환 오류 재발 | ep4669 63.2초·execute_ibl 2·오류 0·재검색 0 |

L56-5 가이드 수리(반환 파일 복구 안내)는 효력이 있었다: 같은 오류 재발 0, 경로가 전부 IBL 로 바뀜. 시간은 늘었고(표본 1회, 당일 매물 다름) 절감률은 주장하지 않는다. 산출물 구조(원응답 보존·실패 구분·요약 Markdown) 동일.

## 4. 발견

| ID | 원인 분류 | 관측 | 상태 |
| --- | --- | --- | --- |
| **L63-1** ★★ | 구현 결함(연구 실행 정지) | 첨부 8편으로 보낸 연구 실행이 `run.started` 뒤 영원히 running. 재현: 시스템 AI 와 무관하게 `/ibl/execute` 의 thread_send+첨부 8편으로도 정지. 오프라인 재현에서 `attachment_input` 이 첨부 본문을 펼친 **429,244자 메시지**를 `_context` → `ResearchLibrary.search` → `_search_fts` 에 질의로 넘겨 FTS5 MATCH(수천 항 OR)가 멈춤(6만 자 질의 60초+). 결과: 대화 `active_run` 영구 점유, 다음 첨부 거절, `thread_cancel` 무효(취소 검사가 모델 루프 안에만 있음), **재기동 drain 이 두 리스에 막힘** | 수리 |
| L63-2 | 구현 결함(원천) | arXiv 검색이 제목 9건 전부 0건 success — `all:term AND …` 에 불용어·구두점 낱말이 들어가면 0건(API 직접 확인: 불용어 포함 0 / 제거 20) | 수리 |
| L63-3 | 진단 안내(경미) | table:ai 입력 상한 거절의 `message` 에 크기·한도 없음(details 에는 있음, 같은 핸들러의 다른 자리는 메시지에 포함) | 수리 |
| L63-4 | 값 계약(경미) | `notebook read` 는 12,000자 고정 페이지라 호출자가 범위를 줄일 수 없고, table:ai 상한(60,000자)과 만나 8편×12,000 이 거절 — 훈련자는 슬라이스로 우회 | 남김(설계 판정) |
| L63-5 | 안내 공백(경미) | 질문 요약 목록이 gaps·next_probes 를 앞 3건으로 접되 총수를 안 적어 연구 모델이 "3건" 으로 오인 | 수리 |
| L63-6 | 값 계약(경미) | `notebook versions` 를 source_ref 없이 부르면 빈 목록 success | 수리 |
| L63-7 | 발견 공백(경미) | research_project.md·research_questions.md 가 guide_db 미등록 → read_guide 0건(빌드도 고아 경고) | 수리 |

훈련자 결함(시스템 아님): 세미콜론 구분으로 gaps 를 쪼개 "(Bai et al., 2024a; Jin…)" 이 두 조각; 철회(withdrawn) 질문도 변경 반영 대상에 넣어 재개; f-문자열 따옴표 6회째; 효과 있는 함수를 삼항에 둠. 평가 명세 결함: 설계는 기본 실행에서 종결이 생긴다고 가정했으나 훈련자 모델은 셋 다 종결 불가로 판정 — 운영자 종결로 변형 조건을 만들었고 그 사실을 적었다.

## 5. 개선 방향과 수리

훈련 종료(13:45, live_turns [] 확인) 뒤 적용. 새 낱말·op·인자 0.

- **L63-1**: `research_runner.stream` 이 배경 검색 질의를 첨부 확장 전 사용자 원문으로 보내고, 모델 입력만 펼친 본문을 쓴다. 모델 시작 전에 취소 요청을 존중. 뿌리 자리도 묶음: `notebook_store._fts_terms` 가 FTS 질의 항을 중복 제거·48항 상한, `search_chunks` 가 질의를 4,000자로 자르고 `query_truncated` 를 돌려준다.
- **L63-2**: `study/handler._arxiv_search_expression` — 불용어·구두점 제거, 질의 문법·따옴표 구절은 보존, 전부 불용어면 원문 유지.
- **L63-3**: ai-ops 상한 메시지에 `(N자 > 한도)` 명시.
- **L63-5**: 요약 항목에 `gaps_total`·`next_probes_total`; 계약 문서 §5·연구 질문 가이드 문구.
- **L63-6**: versions 에 source_ref 없으면 거절.
- **L63-7**: guide_db.json 에 두 가이드 등록(데이터).

회귀 `backend/test_round63_research_attachment_stall.py` 7건(FTS 항 상한·질의 절단 신고·원문 질의·시작 전 취소·요약 총수·versions 인자·arXiv 식). 수리 후 검증은 §7.

## 6. 비용·낭비·잔여

필요했던 비용: 논문 선정·보존(실서비스 읽기), 프로그램 작성 3판, 독립 AI 3턴(약 24분), 관찰 C, 되먹임 2턴(약 4분). 줄일 수 있었던 것: table:ai 에 12,000자×8 을 그대로 넣은 첫 실행(5초·모델 0 이라 비용 작음), arXiv 제목 검색 3회(0건·OpenAlex 로 우회). 훈련자 토큰 미측정. 시스템 AI 기본 턴 15.5분 중 약 14분은 멈춘 연구 실행을 기다린 시간이다 — L63-1 의 비용.

잔여: L63-4 설계 판정(읽기 페이지 크기 인자 노출 여부 — 새 인자이므로 사용자 판정). 멈춘 두 연구 실행은 재기동이 끝낸다(상태는 §7). 수리 후 독립 AI 재실행(첨부 8편 보존→질문→변경)은 이번에 하지 않았다 — 다음 회차의 되먹임 블록 후보. 토큰 절감률 미주장.

## 7. 수리 후 검증

**적용 순서.** 훈련 종료(13:45)·세 실행자와 관찰 C·되먹임 작업 전부 종료 확인(`evidence/training_ended_health.json`, live_turns []) 뒤 13:50~13:52 에 수리 파일을 모아 썼다. 파일 변경 감지로 제어자가 DRAINING 에 들어갔으나 **멈춘 연구 실행 2개(research-chat 리스)가 drain 을 막아 14:02 에 deferred**, 접수 폐쇄 상태가 됐다 — L63-1 의 2차 효과. 문서 규약대로 `backend/api.py restart --wait --force` 를 보냈고(14:06), 제어자가 그 요청의 drain 마감(14:22)에 force 정지 → 새 세대 `56fbd127` ACTIVE(14:22:46), 중단 소유자 2건 기록(`effect_unknown` true). 손 표식·포트 소탕 없음. 재기동 뒤 멈췄던 두 실행은 `cancelled`·`interrupted` 로 닫히고 세 대화의 `active_run` 이 비었다.

| 검증 | 결과 |
| --- | --- |
| L63-1 재현 재실행: 새 대화에 첨부 8편 thread_send | 14:23:29 접수 → 모델 호출(system 69,383자·message 438,184자) → **2분 안에 완료**, 보존 8·응답 본문 있음(`evidence/post_repair_attach_send.json`) |
| L63-1 독립 AI 변경 턴 재실행 (ep4677, 318.3초, execute_ibl 23·거절 7) | 논문 9 보존 성공(판본 `1ef1b433…`), **Q2·Q3 갱신(rev1→2, 열림 유지)·Q1 유지**, 충돌 없음, 재독으로 Q1 지문 불변 확인, change.md 에 이전 거절 기록 보존. 어느 질문에 닿는지는 모델 판단(훈련자 모델은 q1·q2, AI 는 Q2·Q3 — 설계 기대 q1·q2 는 평가 명세였지 정답이 아님) |
| L63-2 arXiv | 질의가 `all:Lost AND all:Middle…` 로 생성됨은 라이브 응답 URL 로 확인, 결과 수는 export.arxiv.org **429/타임아웃**으로 라이브 재확인 못 함 — 수리 전 API 직접 실측(불용어 포함 0건 → 제거 20건)과 단위 시험으로 확인 |
| L63-6 versions | source_ref 없이 호출 → "versions 에는 source_ref 가 필요합니다" 거부 |
| L63-7 read_guide | `research_project.md` 검색이 `research_project` 가이드를 찾음 |
| 회귀 | 새 시험 7 + 관련 모듈 8(연구 runner/threads/questions/library/store·notebook grounding/memory·ai-ops) 전건 통과. 선택기(`select_tests.py`)는 변경 파일에 대해 추가 시험 0 |
| 빌드 | `build_ibl_nodes.py --check` 통과(문서 파생 재기입 architecture.md·technical.md, 가이드 고아 0) |

미검증: backend 전수·frontend(변경 없음), 수리 뒤 훈련자 프로그램 재실행(변경 없는 경로), arXiv 라이브 결과 수(외부 429). 토큰 절감률은 주장하지 않는다.
