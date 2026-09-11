# 실행 기록의 통합 조회 설계와 원장 물리 통합 판단

상태: **L0→L1→L2 구현·검증 완료**. 설계 기준: 정본 main `777430f9`, 2026-09-11. 구현·검증 기록은 11~14절.
관련: [단순화 수리 기록](SYSTEM_SIMPLIFICATION_PLAN.md), [재기동 제어 설계](RESTART_COORDINATION_DESIGN_2026_09_11.md).

## 1. 결정

**여섯 저장소를 하나의 이벤트 DB로 합치는 일은 현재 필요하지 않다. 작업 하나의 기록을 한 번에 연결해서 읽고, 누락·충돌을 드러내는 일은 필요하다.**

물리 통합을 해도 프로세스·스레드·HTTP 경계의 신원 전달은 사라지지 않는다. 기록 장소가 같다고 기록 시점, 실패 의미, 원문 수명, 현재 상태의 권위가 같아지지도 않는다. 지금은 기존 trajectory를 사건 조회의 중심으로 삼고, 각 원장의 근거와 상태를 함께 반환하는 읽기 서비스를 만든다.

새 통합 이벤트 저장소, 전 원장 이중 쓰기, 전체 event sourcing, 오래된 원장의 일괄 삭제는 이 설계의 범위에 포함하지 않는다.

## 2. 실제 소유권

| 저장소/코드 | 소유하는 것 | 보존할 계약 |
|---|---|---|
| [episode_logger.py](../backend/base/episode_logger.py)의 episode_log/episode_summary | 대화 실행의 개설·종료, 로그와 요약 | 종료 행·요약·테스트 분류·정리 수명. 원문 전체나 현재 실행 여부의 유일한 정답은 아님 |
| 같은 파일 trajectory_event | run별 순번을 가진 작고 마스킹된 사건 | 관측 실패는 본 실행을 깨지 않음. 큰 본문은 손잡이로 기록 |
| [write_ledger.py](../backend/base/write_ledger.py) | 쓰기 관문을 통과한 부작용 관측 | 본 쓰기 뒤 best-effort, 회전·심장박동 압축·관문 밖 쓰기의 부분성 |
| [supervision_store.py](../backend/datastore/supervision_store.py)의 TurnStore | 증거 원문, 응답 블록, 읽은 범위, 패치/채택 지문, events/cost | 검수·공개할 바이트의 무결성과 실제 읽기 범위. 이 디렉터리를 일반 로그로 취급하지 않음 |
| [pursuit_ledger.py](../backend/datastore/pursuit_ledger.py) | 장기 과제 상태·version/CAS·사건·각 작업 연결 | 자아별 접근, 상태와 사건의 로컬 트랜잭션, version 충돌 |
| [conversation_db.py](../backend/datastore/conversation_db.py) 및 task 저장 경로 | 프로젝트 대화, 위임·대기·완료 상태, 미전달 메시지 | 소비자가 쓰는 현재 상태와 복구 계약. 조회 때 임의로 재구성해 덮지 않음 |
| [model_call_context.py](../backend/base/model_call_context.py) | 호출 신원·부모 호출·관측 종류와 문맥 승계 | 논리 호출과 provider round 구분, 비용 원천을 중복 합산하지 않음 |

이미 `write_ledger.log_write`는 trajectory의 run/event_seq/episode를 JSONL에 실을 수 있다. `conscious_supervisor.log`는 작업대 사건을 trajectory에도 손잡이와 함께 보낸다. tasks에는 run_id/parent_run_id가 있고 pursuit_turn에는 task_id/episode_id가 있다. 따라서 연결을 처음부터 발명할 필요가 없다.

다만 `episode_logger.get_trajectory`는 조회 실패도 `[]`로 돌려준다. 새 서비스는 이 호환 함수의 빈 결과만으로 관측 성공을 판정하지 말고, 실패를 구별하는 읽기 계약을 실제 저장소 소유자에 추가해야 한다.

## 3. 제공할 기능

한 작업에 대해 다음 질문을 한 응답에서 설명한다.

1. 어떤 요청/과제에서 시작했으며 부모·자식 작업은 무엇인가?
2. 현재 DB 상태, 실행 프로세스의 관측, 마지막 사건은 각각 무엇인가?
3. 어떤 모델 호출과 도구·쓰기·검수가 있었는가?
4. 어떤 원문/공개 대기물/대화 결과에 연결되는가?
5. 무엇이 미관측·누락·충돌·잘림·권한 제한 상태인가?

첫 버전은 read-only 서비스 함수로 제공한다(제안: `services/execution_trace.py`). 원본 읽기 어댑터는 각 기존 저장소 소유자에 둔다. UI/HTTP는 서비스에 의존하고, datastore/base가 surface 라우터를 import하지 않는다. 새 backend 모듈은 층 검사에 등록한다.

기존 주행기록/과제 상세 화면을 소비자로 사용한다. 먼저 기존 API·IBL 조회 동사의 확장이 가능한지 확인하며 새 IBL 낱말을 기본 해법으로 추가하지 않는다. 필요한 HTTP 주소는 기존 라우트와 인증 계약을 조사한 후 정한다. 이 문서의 함수/필드 이름은 제안이며 이미 존재하는 API가 아니다.

## 4. 신원과 원문 참조

### 4.1 식별 규칙

- 질의는 검증된 owner/project 범위와 task_id 또는 run_id/episode_id로 한다. 같은 표시 이름·타임스탬프·본문 유사도를 조인 키로 쓰지 않는다.
- 현재 `trajectory_run_id(task_id)`의 계산과 기존 식별자는 유지한다. 새 조회 서비스에서 다른 hash 규칙을 만들지 않는다. 작업 키의 owner/저장소 범위도 함께 검증하며 task_id가 모든 프로젝트에서 절대 유일하다고 가정하지 않는다.
- parent_run_id, parent_task_id, pursuit_id는 명시된 연결만 채택한다. 여러 후보이면 `ambiguous`로 반환한다. 누락된 owner/run을 이웃 기록에서 자동 추정해 원본에 쓰지 않는다.
- 식별 관계의 근거를 `explicit / deterministic_legacy / missing / ambiguous`로 표현한다. 현재 함수로 재계산하는 옛 run 연결도 derived임을 밝힌다.
- 향후 재기동 generation이 생기면 추가 메타로 연결한다. 지금 세대 없는 과거 기록을 같은 가상 세대로 꾸며 쓰지 않는다.

### 4.2 출처별 사건 식별자

조회 항목은 `source`, `source_record_id`, `source_ref`, `identity`, `kind`, `observed_at`, `summary`, `links`, `diagnostics`를 가진다. source_ref는 서버가 해소하는 불투명 손잡이이며 사용자 입력 경로를 그대로 읽지 않는다.

- trajectory: DB 범위 + run_id + event_seq. 같은 run의 순서만 확정 순서로 해석한다.
- 작업대 사건: 저장소 ID + 해당 파일 세대 + seq. in-memory sequence가 재시작 뒤에도 전역 유일하다고 가정하지 않는다.
- pursuit: 원본 원장 범위 + pursuit_id + 기존 event ID/key 또는 turn의 복합 키.
- 대화/태스크: DB 범위 + 테이블 종류 + 실제 행 ID/키.
- 옛 write JSONL: 지속 ID가 없으면 파일 세대/offset/hash로 **그 조회 스냅샷 안의 위치**를 표시한다. 이것을 영구 전역 ID라고 선언하지 않는다. 회전/교체되면 커서를 무효화하고 다시 읽는다. 같은 내용의 두 번 쓰기를 하나로 지우지 않는다.

trajectory와 write JSONL의 명시적 run/event_seq가 같으면 한 사건의 두 관측으로 묶되 두 출처를 남긴다. 작업대와 trajectory의 대응 역시 명시된 store/seq 연결만 사용한다. 연결 키 없는 비슷한 사건은 별도로 표시한다. 사건 중복 표시 제거와 실제 반복 실행의 제거를 혼동하지 않는다.

## 5. 응답 계약

제안 형태:

```json
{
  "identity": {"task_id": "...", "run_id": "...", "owner": "..."},
  "state": {"task": "running", "runtime": "unknown", "assessment": "unconfirmed"},
  "events": [],
  "links": {"parents": [], "children": [], "pursuits": [], "evidence": [], "messages": []},
  "usage": {"measured": {}, "complete": false, "unattributed_records": 0},
  "sources": [
    {"source": "trajectory", "status": "ok", "observed_at": "...", "high_water": "..."},
    {"source": "supervision", "status": "unavailable", "reason": "..."}
  ],
  "partial": true,
  "next_cursor": null
}
```

허용 출처 상태: `ok / empty / missing / unavailable / malformed / partial / forbidden`. `empty`는 지정 범위를 정상 조회해 0건인 경우뿐이다. `forbidden`은 원장의 존재 자체를 노출하지 않도록 권한 정책이 허용하는 수준으로 축약한다.

- 전체 응답 실패와 일부 출처 실패를 구분한다. 일부 읽기에 실패해도 다른 근거를 보여주며 `partial`을 세운다. 실제 실행의 성공/실패 판정과 조회의 partial은 다른 필드다.
- 진행 프로세스를 못 찾았다는 사실을 task 실패/완료로 자동 변경하지 않는다. DB 완료와 runtime 진행이 충돌하면 둘 다 표시하고 진단을 반환한다. 자동 수리/DB 갱신은 별도 작업이다.
- 서로 다른 저장소의 타임스탬프를 전역 인과 순서로 보장하지 않는다. UTC 정규화가 가능한 시각만 정규화하고, 옛 지역 시각/시각 누락은 불명으로 남긴다. 부모/자식·run 순번의 근거를 우선한다.
- 원문은 개요 응답에 넣지 않고 필요한 페이지를 명시적으로 읽는다. 읽기 권한·경로 경계·크기 제한을 원본 소유자와 동일하게 적용한다. 조회 서비스는 검수 coverage를 채우거나 미승인 바이트를 공개하지 않는다.
- 원문이 삭제됐거나 회전 범위를 벗어나면 `missing`/`partial`로 표시한다. “이 사건 없음”이나 빈 성공 결과로 바꾸지 않는다.

## 6. 비용 집계

`model.usage`의 `accounting=billable_usage`만 기본 측정 원천으로 쓴다. 각 원본 usage 사건을 한 번만 합산하고 동일 call의 여러 provider round는 유지한다. **call_id 하나로 모든 usage 행을 접으면 실제 여러 호출을 잃는다.**

`model.input`은 입력 모양, `model.call_finished`는 호출 경계, `model.response_snapshot`은 응답의 누적 관측이다. 이것들을 usage에 더하지 않는다. 작업대 cost.json과 supervisor model.finished도 같은 사용량의 별도 요약일 수 있으므로 더하지 않는다.

누적 snapshot은 별도 분석에서 run/provider/role/response_id별 필드 최댓값으로 읽을 수 있지만 청구 합계와 구분한다. usage_partial·원천 출처 누락·옛 신원 부재를 그대로 보고한다. 부모/자식 호출 연결 자체를 중복 청구의 증거로 삼지 않는다. 통화 비용 환산은 가격/시점이 명시된 기존 소유자를 쓸 수 있을 때만 제공하고, 없으면 측정 토큰까지만 표시한다.

## 7. 일관성·비용·복구

첫 버전은 요청 시 조회한다. 새 상주 수집기나 영속 색인 DB를 먼저 만들지 않는다.

1. 관련 저장소 위치는 프로젝트/자아 메타데이터와 허용된 경로 해소기로 찾는다. 요청마다 전체 디스크의 SQLite/JSONL을 훑지 않는다. 생성자에 스키마 생성·정리 부작용이 있으면 조회에서 인스턴스화하지 않는다.
2. SQLite는 소유자별 읽기 트랜잭션/high-water, JSONL은 열어 둔 파일의 정체성과 최초 읽기 상한을 고정한다. 서로 다른 저장소 전체의 원자적 스냅샷이라고 주장하지 않는다.
3. 응답의 페이지 커서에 질의 범위·출처별 high-water/위치·버전을 묶고 검증한다. 조회 중 생긴 사건은 다음 새 스냅샷에서 보인다. 회전/교체/삭제 시 조용히 건너뛰지 않고 커서 만료와 부분성을 반환한다.
4. 출처별 읽기량·지연 예산, 최대 페이지/본문 크기를 둔다. 예산 소진은 partial과 다음 커서다. 현재 규모를 읽기 전용으로 측정한 뒤 실제 한도를 정하고 시험에서 강제한다.
5. 재조회는 사용자 task/version·공개 상태를 변경하지 않는다. 서비스/캐시를 꺼도 원본의 실행·검수·복구가 계속된다.
6. 이후 실제 조회 병목이 입증되면 재생성 가능한 색인을 검토한다. 원본 삭제를 색인 도입과 묶지 않는다. 색인에는 버전·watermark·출처별 오류가 있어야 하며 원본 재생으로 검증할 수 있어야 한다.

## 8. 물리 통합이 필요해질 수 있는 경우

다음 근거가 나온 경우에만 별도 ADR로 다시 결정한다.

- 실제로 함께 성공해야 하는 두 **권위 있는 상태 변경**이 분리 트랜잭션 때문에 불일치하고, 보상/로컬 outbox/기존 단일 소유자 개선으로 해결할 수 없다.
- 통합 조회 후에도 측정된 쓰기·조회 병목이나 복구 실패가 물리 분산에서 생긴다고 확인된다.
- 옮길 데이터의 소유권·권한·보관 기간·원문 무결성·복구 순서가 호환되고, 구 reader가 모두 이전 가능하다.

그때도 문제를 일으키는 저장소 쌍부터 검토한다. 관측 실패를 허용하는 write_ledger를 본 쓰기와 강결합하거나 TurnStore의 원문/CAS를 4KB 사건으로 대체하는 것은 허용하지 않는다. 과거 로그만으로 모든 현재 상태를 재생할 수 있다고 가정하지 않는다.

별도 이전 계획에는 손실 없는 export와 checksum, 레코드/참조 대응표, 스키마 버전, 복제 데이터에서의 shadow 조회 비교, 읽기 전환, 실패 시 되돌리기, 각 원본 보존 기간이 필요하다. 라이브 SQLite 백업은 backup/VACUUM INTO를 쓰고 임의 파일 복사를 금지한다. 자동 이중 쓰기부터 켜는 접근은 새로운 불일치 가능성이 있으므로 원자성/재시도 정책부터 설계한다.

## 9. 구현 묶음과 시험

| 순서 | 변경 | 완료 기준 |
|---|---|---|
| L0 | 출처/reader/신원 계약 지도와 합성 누락·충돌 fixture | 현재 공통 키와 실패/보관 경계가 코드에 근거해 설명됨 |
| L1 | 오류를 구별하는 원본 reader + read-only 조합 서비스 | 한 task의 사건·상태·원문 연결을 반환, 정상 빈 값과 실패 분리 |
| L2 | 기존 상세 화면/조회 입구에 연결, 원문 페이지 조회 | 권한·부분성·비용 표시·페이지 재조회 일관성 검증 |
| L3 | 필요성이 측정된 경우만 캐시/색인 | 원본에서 재생성 가능, 원본 권위와 삭제 수명 유지 |

필수 회귀: 같은 agent의 동시 두 task, 다른 project의 같은 task 문자열, MCP 재진입, 부모/자식 호출, WS 타임아웃 뒤 늦은 완료, usage snapshot 중복, 같은 call의 여러 실제 usage, JSONL 회전/잘린 마지막 행, DB 잠금·부재, 증거 파일 부재, 잘못된 참조, 권한 없는 경로, task 상태와 runtime 충돌, 페이지 도중 새 사건 삽입. 오류 후에도 원본 DB/파일이 바뀌지 않았음을 확인한다.

기존 `test_trajectory_spine`, `test_write_ledger`, `test_pursuit_ledger`, 모델 호출/원문 보존/동시 실행 관련 시험과 전체 backend 검사를 실행한다. 프런트 변경 시 TypeScript·빌드·주행기록 화면을 검증한다. 실사용 DB는 읽기 전용 표본으로만 검증하고 외부 송신은 하지 않는다.

## 10. 다른 세션에 넘길 요청

> 정본 `/Users/kangkukjin/Desktop/AI/indiebizOS`의 AGENTS.md와 이 문서를 읽고 L0→L1→L2 순서로 구현하라. 원장을 물리적으로 합치거나 새 이벤트 DB를 만들지 말고, 기존 trajectory와 출처별 원장을 한 작업 기준으로 연결하는 읽기 서비스를 만들어라. 실패/빈 값/부분성/권한/비용 중복을 구분하고 원문·검수·CAS·복구 계약을 보존하라. 실제 코드의 최신 소비처를 재확인하고, 새 브랜치/clone 없이 정본 main에 검토 가능한 묶음별로 커밋하라. 이 문서에 검증과 남은 조건을 기록하라.

## 11. L0 — 확인된 reader·신원 지도 (2026-09-11)

- `episode_logger._get_db`는 mkdir/WAL 설정, `get_trajectory`는 오류→[]이므로 새 읽기 경로에서 호출하지 않는다. `episode_log.owner`는 **프로세스 신원**이며 자아 ID가 아니다. `agent`도 표시 이름이다. episode에는 project 컬럼이 없다.
- `trajectory_run_id(task)`는 task 문자열만 해시한다. 프로젝트별 같은 문자열은 같은 run이다. episode가 있는 사건은 episode FK로 분리하고, episode 없는 옛 사건은 자아/프로젝트를 증명하지 못하면 `ambiguous`로 남긴다. 이를 고치기 위한 기존 행 UPDATE는 없다.
- 프로젝트 DB는 `projects/projects.json`에 등록된 경로의 `conversations.db`, 시스템 자아 DB는 `INDIEBIZ_USERDATA` 또는 data의 `system_ai_memory.db`이다. `ConversationDB`/`PursuitLedger` 생성자는 스키마를 쓰므로 조회에서 만들지 않는다. `pursuit_turn.episode_id`와 `pursuit.agent_key`가 episode→저장소/자아의 명시적 연결이다. project task 입력은 검증한 등록 범위에서만 읽는다.
- tasks의 `delegated_to`는 표시 이름이다. 이를 자아 ID로 바꾸지 않는다. 프로젝트 messages 및 시스템 conversations에는 task FK가 없으므로 시간·이름으로 메시지를 붙이지 않는다. tasks.result와 pursuit_turn.response는 실제 task 키로 참조 가능하다. 미전달 플래그를 변경하지 않는다.
- `ConsciousSupervisor.log`의 trajectory `data.store`+`data.seq`는 작업대 연결이다. store 경로는 허용 루트 바로 아래 turn ID로 재검증한다. TurnStore seq는 파일 내에서도 재시작 시 중복 가능하므로 파일 세대/offset도 보존하고 대응 후보가 여럿이면 합치지 않는다. evidence 조회는 coverage를 기록하지 않는다. 응답 원문은 검수 승인 지문과 현재 manifest가 맞는 버전만 제공한다.
- `write_ledger`의 두 세대만 읽는다. run/event_seq+episode가 맞으면 두 관측의 참조를 연결한다. 옛 agent/task만 있는 행은 범위를 증명하지 못하면 내보내지 않는다. 관문 밖 쓰기·heartbeat 압축·회전 전 기록 부재를 부분성으로 명시한다.
- `model.usage`의 `accounting=billable_usage`만 토큰을 합산한다. 동일 call의 여러 행은 별개다. snapshot·boundary·cost.json은 합산하지 않는다.
- `EpisodeJournal.tsx`의 기존 상세 펼치기를 소비처로 사용한다. 기존 `/world-pulse/episodes/{id}/trajectory`는 호환을 유지하고 같은 주행 아래 통합 조회/원문 페이지를 추가한다. 기존 전역 `remote_access_guard`의 로컬 또는 원격 런처 세션 계약을 따르며 공개 경로에는 추가하지 않는다. 새 IBL 낱말은 없다.
- 읽기 전용 실측: trajectory 77,990행/20,136 run, 최대 run 872행, data 최대 4,105자. 쓰기 JSONL 5,792,300바이트(회전 파일 없음). 등록 프로젝트 24개. supervision 62개, 사건 파일 중앙값 1,832/최대 202,464바이트. 본문·키·메시지는 표본 출력하지 않았다.
- 합성 입력: `backend/fixtures/execution_trace_cases.json`. 여러 provider round+부모/자식 비용 정답은 input=350/output=35이며 누적 snapshot/호출 종료를 더하면 시험이 실패해야 한다. 실패·누락·충돌·페이지/권한 불변식도 이 fixture를 바탕으로 시험한다.

## 12. L1 — 구현 및 검증

- 읽기 서비스: `backend/services/execution_trace.py`, 등록 범위 해소: `execution_trace_scope.py`. 기존 소유자의 strict reader를 사용한다. episode reader는 1500줄 규칙 때문에 `base/episode_trace_reader.py`로 분리하고 `episode_logger`에서 재수출했다. 공통 읽기 원시 연산은 `base/trace_read.py`다. 기존 호환 reader와 writer/CAS/복구 동작은 유지했다.
- SQLite `mode=ro`/`query_only`/읽기 트랜잭션, 100ms 잠금 대기와 SQL 350ms 예산을 적용한다. 페이지는 출처당 1~100행(기본 50). append 원장은 rowid 상한/범위 count/파일 신원으로 보존 범위 변화를 감지한다. JSONL은 최초 파일 신원·상한·앞뒤 지문을 고정하고 요청당 출처별 1MiB를 스캔한다. 64KiB 초과 행은 나머지를 새 사건으로 파싱하지 않는다.
- 등록 프로젝트는 최대 64개/메타데이터 256KiB, 신원 후보 200개, 명시 작업대 32개/연결 사건 2000개로 제한한다. 이 한도 초과는 부분성을 반환한다. 전 디스크 탐색·상주 수집·새 DB·캐시/색인은 없다.
- HMAC 커서는 질의/접근 범위/원장별 상한·위치를 묶는다. 유효기간 15분, 서비스 프로세스가 바뀌면 만료한다. 작업 상태/과제 version 변경, 원장 회전·삭제·보존 범위 변경은 새 스냅샷을 요구한다. 커서 없는 재조회가 새 사건을 본다. 모든 DB가 동시에 관측됐다는 원자성은 주장하지 않는다.
- 개요에는 원문/도구 excerpt를 복제하지 않는다. 증거·episode log·task result·pursuit input/response는 서버 발행 참조의 별도 페이지다. 일반 원문 1M자/증거 4MiB 상한, 응답 페이지 12000자. 증거 내용 주소와 응답의 승인·현재 manifest 지문을 확인하며 coverage/patch/adopt/publish는 실행하지 않는다.
- 직접 task/run 질의는 등록 project+owner 범위를 요구한다. 과제 episode FK가 없으면 scoped task 상태만 보여주며 전역 run을 추정 조인하지 않는다. messages에 task FK가 없는 현재 스키마는 `missing/no_task_foreign_key`로 드러낸다.
- 같은 페이지의 trajectory/write 명시 연결은 observations로 묶고 두 원본 ID를 남긴다. 페이지를 넘는 대응은 observation_of 참조로 남긴다. 작업대 반복 seq는 파일 위치별로 보존하고 ambiguous로 표시한다. 여러 실제 usage는 모두 합산하며 `complete=false`는 best-effort 기록만으로 전체 청구의 완전성을 증명할 수 없다는 뜻이다. `recorded_events_complete`는 기록된 청구 사건의 페이지 읽기 완료만 뜻한다.
- L1 합성 회귀 **14개 통과**: 비용 정답/반복 쓰기/같은 task 다른 프로젝트/같은 자아 다른 task/잠금·빈 결과·부재·손상/회전·삭제/증거 접근·해시·검수/CAS/늦은 완료·상태 충돌/페이지 중 삽입/원본 무변경/본문 변경 커서 만료/예산 진행. 기존 trajectory/write/pursuit/task binding/concurrency/delivery 시험 **65개 통과**. 층 검사 통과, Android 번들 재생성 완료.
- 실사용 최근 episode 읽기 표본: **42ms**, 명시 자아 범위 해소 성공, 104개 개요 사건, 다음 커서 있음. 원래 4KB에서 잘린 작업대 trajectory 데이터는 `malformed_store_link`로 표시됐고 실제 원장을 손대지 않았다. 전체 backend 회귀는 L2 완료 후 결과를 아래에 기록한다.


## 13. L2 — 주행기록·원문 페이지 연결

- 조종실 → 주행기록 → 요청 행 펼치기에서 통합 기록을 조회한다. 사건·현재 DB 상태·별도 runtime 관측·에피소드 종료 기록·측정 토큰·부모/자식/과제 version·출처 상태를 표시한다. 원문은 명시적으로 열며 도구/검수 증거는 접을 수 있는 목록이다. 기존 분석 버튼과 `/trajectory` 응답은 유지한다.
- HTTP: GET/POST `/world-pulse/episodes/{id}/trace`, POST 같은 경로의 `/document`. task/run은 POST `/world-pulse/execution-trace`에 project/owner/task_id 또는 run_id를 지정하고 원문은 `/world-pulse/execution-trace/document`로 읽는다. POST는 읽기 요청만 수행하며 긴 커서를 URL에 싣지 않는다. 부작용은 없다. 모든 진입점은 기존 로컬/원격 런처 인증을 적용하고 공개 경로에 등록하지 않았다.
- `missing`→404, `forbidden`→403, 인증 미확인→401/503, 읽기 실패→503, 형식 오류→422. 일부 출처 실패는 200 응답 안의 출처 상태/partial로 보인다. 만료된 커서는 새 스냅샷 조회를 요구한다. 프런트는 늦게 도착한 이전 요청/원문 응답을 무시하며 재조회 시 이전 페이지 누계를 초기화한다.
- best-effort인 비용의 전체 완전성을 주장하지 않는다. 기록된 청구 사건의 페이지 누계만 표시하고 snapshot/boundary/supervisor cost 중복은 제외한다. 공개 대기 사건은 manifest 지문·산출물 수·알림 수만 요약하며 초안 본문/알림 내용은 개요에 싣지 않는다.
- 인증/입력 경계 포함 합성 시험 **19개 통과**. runtime observer 오류가 다른 출처 조회를 막지 않음, malformed 메타데이터/원문 지문 오류 뒤 원본 무변경, 공개 대기물 무노출/무송신까지 포함한다. 저장소 단일 시험 러너 규약과 사설 값 판정 관문도 통과한다.
- 실제 localhost 화면에서 최근 주행의 **104→204 사건 페이지 누적**, **12,000→24,000자 원문 페이지**, 새로 조회 시 원문 폐쇄와 104건 첫 페이지 복귀를 확인했다. 출처별 부분성과 비용 표시, 접는 증거 목록을 시각 검증했다. 원격 통신·분석 AI·알림 발송은 실행하지 않았다. 초기 앱 연결 재시도 중 기존 기어/스위치 로더의 네트워크 오류가 있었고 이후 로드됐으며, 통합 기록 컴포넌트의 렌더 오류는 관측되지 않았다.
- TypeScript(`npx tsc -p tsconfig.app.json`), 변경한 두 컴포넌트 ESLint, `npm run build` 통과. 기존 큰 JS chunk 경고는 남아 있으며 이 변경의 오류가 아니다.
- 전체 backend 첫 실행의 실패 2건(새 시험의 `__main__` 누락, SQLite 오류 문구의 사설 소문자 비교)을 수정했다. 재실행은 **3,876 passed / 1 skipped / 116 warnings**(249.75초). 최종 보강 후 전체 결과는 아래에 추가한다.

남는 경계: 메시지 FK 없는 과거 대화, 범위를 증명하지 못하는 episode 없는 옛 run/write, 이미 정리된 원문은 복원하지 않는다. 이는 명시적 missing/ambiguous/partial이다. SQLite 사건 원장은 기존 append-only 계약, JSONL은 기존 append/회전 계약에 의존한다. 한도 초과 신원 후보/작업대/원문은 partial로 반환하며 한도를 우회해 전체 디스크를 스캔하지 않는다. 원장 물리 통합·새 이벤트 DB·L3 캐시/색인은 도입하지 않았다.


## 14. 최종 검증 결과 (2026-09-11)

정본 `/Users/kangkukjin/Desktop/AI/indiebizOS` main 반영:

| 묶음 | 확인한 커밋 | 결과 |
|---|---|---|
| L0 | `e24e4ab4` | 소유권·신원·실패 지도, 합성 fixture |
| L1 | `ed59d00b` | strict reader·조합 서비스·인증된 조회 API |
| L2 | `b927e2d7` | 주행기록 상세·원문 페이지·보강 회귀 |

- 최종 코드 전체 backend: `.venv/bin/python3 -m pytest backend/ -q -o addopts=''` → **3,878 passed / 1 skipped / 116 warnings**, **248.76초**, 종료코드 0. 추가한 통합/HTTP 시험 19개를 포함한다. 기존 trajectory/write/pursuit, 모델·원문 보존(`test_conscious_supervisor`, `test_model_provider_memory`, `test_supervision_delivery`), 동시 실행·MCP(`test_parallel_context_inherit`, `test_parallel_branch_budget`, `test_mcp_boundary`)도 이 전체 실행에서 통과했다.
- 1개 skip은 `test_narration_injection.py:17`의 기존 로컬 전용 스크립트가 pytest 수집 시 명시적으로 건너뛰는 계약이다. 이번 구현의 시험 누락/실패가 아니다. 기존 Pydantic 및 의존 라이브러리 deprecation 경고 116개는 유지된다.
- 최종 프런트: TypeScript, 변경 컴포넌트 ESLint **경고 0/오류 0**, `npm run build` **성공**(Vite 2.59초). 기존 bundle chunk 크기 경고만 남는다. 브라우저에서 주행기록 펼치기·사건 다음 페이지·원문 두 페이지·재조회를 실검증했다.
- 최신 실사용 주행의 **전체 12페이지 / 785개 관측**, **총 189.4ms / 최대 페이지 40.1ms**. 최종 측정 비용이 같은 episode의 원본 SQL `model.usage/accounting=billable_usage` 합계와 모든 토큰 필드에서 일치했다. 이 표본 검증은 개요만 읽었고 원문을 출력하거나 외부로 송신하지 않았다. 관측 중복은 원본 위치별로 남고 청구량에 더해지지 않는다.
- `build_ibl_nodes.py`/Android 몸 번들을 재생성했고, 커밋 관문의 파생물·층·1500줄·모듈 그림자·이벤트 루프·동시성·단일 시험 러너·값 의미론 검사가 전부 통과했다. `git diff --check`도 통과했다.
- 기존 IBL `[self:body]{op:"trajectory"}`의 `items/total/truncated` 및 앞뒤 사건 추출 계약을 확인했다(`system_essentials/body_ops.py:324`). 이 호환 표면을 유지하고, scope·cursor·원문 권한을 받는 새 읽기 계약은 같은 주행기록의 HTTP 하위 경로로 제공한다. 새 IBL 낱말/파라미터를 추가하지 않았다.
- 복제본·새 브랜치를 만들지 않았고 원장 스키마/물리 저장 구조를 바꾸지 않았다. 기존 다른 작업의 `docs/SYSTEM_REFLECTION_2026_09_11.md` 미추적 파일은 건드리지 않았다.
