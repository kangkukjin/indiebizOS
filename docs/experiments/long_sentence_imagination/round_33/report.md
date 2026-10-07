# 긴문장 33회차 — 다단계 BOM 전개와 재사용 신선도 수리

정본 `/Users/kangkukjin/Desktop/AI/indiebizOS`에서 훈련 후 수리. 시작 HEAD `4f9cfcb23af812a6379694a54fed0c9a09682b34`.
시작 2026-10-07 17:07:38 KST, 훈련 상한 60분. 모든 작업 종료 확인·훈련 종료 17:17:19, 이후 수리·검증은 별도다.

## 과제와 조건

[사전 과제](task.md), [자연어 원문](request.txt), [순환 변형](variant_request.txt).
새 축은 **깊이를 모르는 트리의 전개**다. 명세는 "재귀는 지원하지 않는다"고 못 박았으므로 깊이 5의 구성 트리(제품 10·반제품 60·
구매품 200, 구성 209행, 주문 20건)를 `[repeat:while]` + `table:join`(anti=말단, inner=전개) 한 층씩 전개로 썼다. 주문별 경로를 보존해
순환을 값으로 멈추고, 구매품별 총소요량을 집계해 재고와 대사한다. 변형 A는 순환 1개·정의 없는 부품 2개·구성 없는 반제품 1개를 주입한
자료(같은 프로그램·다른 입력), 변형 B는 주문 O007 수량 2배(변경 용이성, `reuse`). 합성 자료·독립 oracle(Python 재귀 DFS)은
`harness/prepare.py`, 산출물 대조는 `harness/verify.py`다. AI에는 `source/` 사본 경로만 줬다.

## 작성

공개 교재·명세·`describe`(join·groupby·each·write)만 보고 썼다. 초안은 모두 보존했다.

| 버전 | 결과·수정 이유 |
| --- | --- |
| [v0](drafts/main_v0.ibl) | `{**$acc,[$r.product]:$r.depth}`(값으로 정한 키)가 SYNTAX "이름이 필요합니다." — 위치만 있고 지원하지 않는 모양·대안 없음. L33-1 |
| [v1](drafts/main_v1.ibl) | depth_by_product 를 `{product,depth}` 행 목록으로. 검사 통과. 첫 실행은 HTTP body 에 `project_id` 가 없어 첫 읽기에서 거절(검사는 침묵) — L33-3. 문맥 보충 뒤 기본·순환·변경 변형 전건 달성 |
| [수리 후](drafts/main_repaired.ibl) | 새 변형의 재고 중복 행(R200 2행)이 1:N 조인으로 소요 행을 복제한 것을 발견(L33-4, 훈련자 작성 공백) → `dedup`+행수 집계로 "재고 중복" 판정 |

수정 주기 1(v0→v1)과 요청 문맥 보충 1. 회차 시작→최초 관측 회수 약 4분. 내부 소스는 실행 뒤 원인 진단에서만 열었다.

## 실행·품질

| 실행 | 검사 / 실행 / 달성 | 시간 | 근거 |
| --- | --- | ---: | --- |
| 훈련자 v0 | 거절 / 미실행 / 미달 | 검사 0.28초 | 값으로 정한 레코드 키 |
| 훈련자 v1 기본(문맥 없음) | 허용 / 실패 / 미달 | 1.00초 | 읽기 4건 전부 "활성 프로젝트 경로를 확보할 수 없어" |
| 훈련자 v1 기본 | 허용 / 정상 / **달성** | HTTP 2.85초 | 68행·주문 20·깊이 5·events 209, 재고 미상 3 null |
| 훈련자 v1 순환 변형 | 같은 문장 / 정상 / **달성** | HTTP 2.96초 | 순환 8건+유효 경로, 54행, 정의 없음 2·구성 없음 1, 반복 종료 |
| 훈련자 v1 변경 변형(별도 폴더, reuse) | 같은 문장 / 정상 / 달성 | 1.53초 | 읽기 5건 재사용 0(경로가 달라 정당) |
| 훈련자 v1 제자리 수정 + reuse | 같은 문장 / 정상 / **오답** | 1.77초 | 바뀐 orders.json 을 옛 영수증으로 읽어 O007=102(정답 204), 재독 검증 통과 — L33-2 |
| 독립 AI ep4395 (기본) | 자연어 / 정상 / 달성(해석 차이 2) | 217.7초 | 소요 68행 전건 일치. status 라벨 "정상", leaf_rows 를 말단 부품 목록으로 해석 |
| 독립 AI ep4396 (순환) | 자연어 후속 / 정상 / 달성(해석 차이) | 109.8초 | 주문·순환 경로·소요 전건 일치, 상태를 "정의 없음 + 재고 미상"처럼 겹쳐 표기, 순환 제품 깊이 null |

독립 AI 모델 claude_code/opus. `task_sysai_90c5652e`·`task_sysai_36608105` 모두 succeeded 를 회수한 뒤 수리했다. AI 는 IBL 로 파일을 읽고 쓰되
계산은 자체 Python(`mrp_explode.py`)이며 IBL 독립 작성 성공으로 세지 않는다. 기본에 검사 거절 3회(check_rejections), 자동 압축 0, 회상 제시·사용 각 1.
`leaf_rows`·정상 라벨은 요청문이 정의하지 않은 칸이라 과제 설계의 모호성으로 적는다.

| AI 실행 | 입력(캐시 포함) | 출력 | cache_read | cache_create | 도구 | execute_ibl |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| ep4395 | 1,992,161 | 20,699 | 1,717,358 | 269,873 | 13 | 12 |
| ep4396 | 2,077,348 | 11,485 | 1,920,032 | 152,482 | 7 | 5 |

`accounting=billable_usage` 만 합산, 훈련자 작성 비용 미포함. [계측](evidence/ai_metrics.json) · [종료 확인](evidence/training_end.json) · [실행 요약](evidence/runs.json).

## 발견·수리

| 갭 | 분류·원인 | 조치 |
| --- | --- | --- |
| L33-1 | 문법 공백+진단 — 값으로 정한 레코드 키 `{[$k]:v}` 는 문법에 없는데 오류가 "이름이 필요합니다"뿐 | 파서가 지원하지 않는 모양과 대안(`{key,value}` 행 목록·keys/values/entries)을 말한다. 문법 추가는 언어 개정이라 사용자 판정으로 남김 |
| L33-2 | **구현 결함(정직성)** — `reuse` 가 같은 경로의 파일을 수정 뒤에도 옛 영수증으로 읽어 결과가 조용히 틀림. 재독 검증은 같은 오답끼리 일치 | 읽기 영수증에 읽기 직전 파일 지문(수정 시각 ns·크기) `resource_state` 를 싣고, 빌릴 때 다르면 `resource_changed`(바뀐 경로 명시), 지문 없는 옛 영수증은 `freshness_unknown` 으로 새로 읽는다. 파일 아닌 원천은 종전과 같다 |
| L33-3 | 낭비(검사 침묵) — 프로젝트 문맥 없는 HTTP 요청은 검사 통과 뒤 첫 읽기에서 거절(32회차에도 밟음) | 검사가 사용 액션의 scope·효과와 요청 문맥을 대조해 `PROJECT_CONTEXT` 경고(액션 목록·hint). 거절은 아님 — 문장 인자 project_id 가 그 step 에만 적용되므로 |
| L33-4 | 훈련자 작성 공백 — 재고 중복 행을 1:N 조인으로 복제(join 설명의 ★경고를 놓침) | 프로그램에 `dedup`+행수 집계로 "재고 중복" 판정 추가, oracle 도 같은 정책. 시스템 수리 아님 |

관측(수리 없음): 반복 안 행 구성 1,190행에 29.5K 단계(행당 ≈2×필드+7, [탐침](evidence/runs.json) 밖 실측) — 주문 40건이면 기본 단계 예산을 넘는다.
`table:join` 호출당 고정 비용 ≈12ms(10행·400행 거의 같음). 독립 AI 의 `leaf_rows` 해석 차이는 요청문 책임.

수리 코드: `backend/ibl/ibl_run_journal.py`(resource_state) · `ibl_v2_runtime.py`(지문 저장·대조·skip 사유) · `ibl_v2_compile.py`(preflight.actions) ·
`ibl_v2_analysis.py`+`ibl_v2_entry.py`(PROJECT_CONTEXT) · `common/expression_parser.py`(키 안내). 교재: ibl_composition(_tools)·ibl.md·12_ibl_only.
회귀시험 [test_imagination_round33_repairs.py](../../../../backend/test_imagination_round33_repairs.py) 6건.
파서는 `record-ops`(회원 기록 앱)가 `path_audited.dependencies` 로 지문을 고정한 공유 의존이라, 첫 전수에서 어휘 검증 5건이 '의존 구현 지문 불일치'로 실패했다.
안내 메시지만 추가된 변경임을 확인하고 지문을 재감사(10-07 주석)한 뒤 `build_ibl_nodes.py` 로 파생본(ibl_nodes.yaml·member_manifest.json)을 재생성했다.

## 수리 후 검증

[post_validation.json](evidence/post_validation.json). 재기동(제어자, 손 표식 없음) 뒤 라이브 HTTP 로:
- 원래 v1 기본·순환·변경 변형 전건 일치(1.5~1.6초, 전수 회귀 병행 없음).
- 제자리 수정 + reuse(`inplace2`): 읽기 5건 중 3건 재사용, orders.json 은 `resource_changed`(경로 명시), 재독 겹침 1건 `overlapping_write`, O007=204 전건 일치.
- 문맥 없는 검사 → `PROJECT_CONTEXT`(self:read·self:write), 문맥 있는 검사 → 경고 없음. v0 검사 → 새 안내 문구.
- 새 변형(주문 역순·O003 수량 0·R001 재고 행 삭제·R200 중복 재고)을 실행 전 고정([조건](evidence/new_variant_conditions.json)): v1 은 R200 복제로 1검사 실패 → 수리본은 기본·순환·새 변형 전건 일치, R200 "재고 중복"·R001 "재고 미상".
- 입력 8파일 바이트 불변([대조](evidence/source_integrity.json)).

## 낭비와 한계

- 필요한 비용: 순환·정의 없음·구성 없음·재고 미상·재고 중복을 값으로 드러내는 분기와 oracle 전건 대조. 정직 표시를 줄여 얻은 절감은 없다.
- 제거한 낭비: 검사 통과 뒤 실행 거절(문맥) 왕복, 오답을 성공으로 보고하던 재사용. 두 번째는 시간이 아니라 결과 품질의 문제다.
- 작성 낭비: 값으로 정한 키 시도 1회, 재고 중복 미고려 — 훈련자 비용이며 시스템 성과에 합산하지 않는다.
- 독립 AI 는 두 턴 모두 Python 계산이었다. 수리 후 독립 AI 재실행은 하지 않았고 토큰·시간 개선량은 미측정.
- `resume`(같은 프로그램의 계속)은 설계상 옛 영수증을 그대로 복원한다 — 이번 수리 범위 밖. 웹·모델 원천의 신선도는 종전대로 작성자 책임.
- 계산 단계 예산(행당 ≈2×필드)은 관측으로 남긴다. 함수 깊이 64 는 반복 전개로 쓰지 않아 닿지 않았다.

## 최종 검증·반영 범위

- 관련 20파일(재사용·검사·파서·긴문장 수리 회귀) 전부 통과, 신규 6건 통과.
- 첫 backend 전수(sandbox 밖, `-n 6`): 9,216+ 시험 중 실패 5 — 전부 `record-ops` 의 파서 의존 지문 불일치(어휘 검증 거절). 지문 재감사·파생 재생성 뒤 5건 통과.
- 파생 재생성이 재기동 도중에 닿아 제어자가 `FAILED(artifact_changed_before_start)` 로 내려갔고, 문서화된 복구(`backend/api.py start`)로 ACTIVE 복귀. 복귀 뒤 라이브 기본 전건 일치·문맥 없는 검사 경고 확인.
- 최종 전수: **9,367 시험·실패 1**(`test_chunk_ops` 작은 조각 묶기 — 단독 재실행 2/2 통과, 병렬 부하의 시간 조건으로 추정, 이 회차 변경과 무관). 종료 1.
- 같은 시각 다른 세션의 미커밋 편집(`routing_system.py`·`ibl_routing.py`·`ibl_typecheck.py`·새 `test_routing_system.py`)이 작업 트리에 있었고 전수에 포함됐다. 이 커밋에는 넣지 않는다.
- `build_ibl_nodes.py --check` 정합, 층 가드·파일 크기 예산 통과. frontend 미변경·미실행.

훈련 종료 이후 수리·검증·보고서 벽시계는 약 25분(17:17~17:42). [검증 영수증](evidence/post_validation.json).
