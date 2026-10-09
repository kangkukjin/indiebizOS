# 43회차 — 홍보 한 바퀴: 고객 목소리 → 브리프 → 앵글별 소재 → 발행 직전 묶음 → 캠페인 원장 → 반응으로 좁히기

정본 `/Users/kangkukjin/Desktop/AI/indiebizOS` main `e6b3a90c`(+ 미커밋 `data/guides/marketing.md` 2행 보강)에서 훈련했다.
시스템 코드·설정·어휘 수리와 관용구 등록은 하지 않았다. 사전 조사 정본은 [홍보 어휘 조사](../../../PROMOTION_VOCAB_SURVEY_2026_10_09.md).

## 1. 판정과 산출물

| 실행 | 검사 | 실제 실행 | 요구 달성 | 시간 |
|---|---|---|---|---:|
| 훈련자 기본 v0 | issues 0·경고 0(최초 초안) | 정상, 4,608단계, AI 3회·이미지 3·카드 3·네이버 3 | **달성** — 결정론 검수 14/14, 분류 oracle 일치 123/123 | HTTP 80.091초 |
| 훈련자 변형 react v0→v1 | v0 경고 `BIND_RETURNS` 2(작성 오류) → v1 issues 0 | 정상, 9,977단계, `source_complete:false`(self:ledger upsert 실패를 catch 로 폴백) | **달성** — 검수 11/11(집계·KPI·결측·노출0·미측정·원장 status·리포트 절) | 12.229초 |
| 독립 AI 기본 | 검사 거절 1(groupby `n` 집계 표기 — hint 로 교정)·자작 관문 1·SCRIPT_PATH 1·read_result 오용 1 | 정상 ep4498, 도구 29(execute_ibl 24·Bash 5), 실행 실패 6(위 4 + 내부 2), 압축 0 | **달성** — 느슨 검수 11/11([verify_agent](evidence/verify_agent_base.json)), 거친 축 일치 123/123(6축을 3축으로 합치면 49/37/25·제외 12), `total_estimate` 9칸 조회 | 턴 695.881초 |
| 독립 AI 변형 | 자작 관문 1 | 정상 ep4499, 도구 15(execute_ibl 12·Bash 3), 압축 0 | **달성** — 소재별 합계·총 문의 109·KPI 달성·좁히기 A2·결측일·노출 0·미측정 2 전부 리포트에 명시, 원장 status 3행 proposal_* · 평가 경로는 UNKNOWN(L43-3) | 턴 263.554초 |

- [사전 과제](task.md) · [최초 초안 main_v0](drafts/main_v0.ibl)(수정 없이 실행) · [변형 v0](drafts/react_v0.ibl) → [v1](drafts/react_v1.ibl)
- 훈련자 증거: [기본 검사](evidence/trainer_base_main_v0_check.json) · [기본 실행](evidence/trainer_base_main_v0.json) · [기본 검수](evidence/trainer_base_qa.json) · [변형 실행](evidence/trainer_react_react_v1.json) · [변형 검수](evidence/trainer_react_qa.json) · [모델 사용량](evidence/trainer_model_usage.json)
- 탐침: [naver total 단건/배치](evidence/probe_naver_total_single.json) · [self:write json 모양](evidence/probe_write_json_shape.json) · [self:ledger 출처별](evidence/probe_ledger_origin.json)
- 산출물(훈련자, 로컬 `outputs/long_sentence_imagination/2026-10-09_43회차/trainer/out/`): brief.md·brief.json·research/3·assets/6 PNG·bundle/3·campaign_ledger.json·performance.md·performance.json. 브리프·카드 1장·원장은 [artifacts/trainer](artifacts/trainer/)에 사본.
- 발행·게시·발송 액션 호출 0(검사 `actions` 목록으로 확인). `table:since` 기준선 1건(`LSI43_후기감시`, 네이버 블로그 10행)은 내부 검침 상태에 남는다.

## 2. 과제·환경·작성

가상 동네 수리교실(42회차 소재 재사용)의 홍보를 조사→브리프→소재→발행 직전 묶음→원장까지 한 프로그램으로, 2주 뒤 반응 자료로 좁히기 제안·원장 갱신·감시 등록을 두 번째 프로그램으로 썼다.
자료는 전부 합성(`harness/prepare.py`, seed 43): 고객 목소리 123행(time 49·confidence 37·cost_waste 25·noise 12, 경계 표본 3 = 쉼표·따옴표·줄바꿈), 경쟁사 안내문 2, 자사 JSON, 검색어 3, 반응 83행(결측일 1·노출 0 행 1·미측정 채널 2). 정답은 입력 폴더 밖 `_oracle/`.
실제 외부 읽기는 네이버 검색뿐(실패 허용·미확인 표기). 외부 공개·발송·예약 없음 — 발행 직전 묶음까지가 시스템의 일(마케팅 가이드 핵심규칙 2).

기본 경로 HTTP `/ibl/execute`, `project_id:"수동모드"`, `origin:"training"`, 예산 100만 단계. AI 호출은 `table:ai` 3(분류·경쟁사 추출·소재 문안) + `engines:image_gemini` 3 + 변형 `table:brief` 1. 내부 모델 ClaudeCode/opus.

**분해(기본)**: 순수 보조 5(`글`·`금지어검사`·`축건수`·`대표인용`·`검색근거`·`옛원장`) → 읽기 → 분류(AI, preserve_rows) → groupby 건수 → 순위·상위 3 → 대표 인용(원문 그대로) → 경쟁사 추출(AI) → 검색어 근거(try/catch) → 소재 문안(AI 1회, 3행) → 소재마다 이미지·카드뉴스·금지어 검수(결정론 `contains`) → 브리프 md/json → 묶음 3파일 → `[fn:원장에누적]` → 파일 실존 확인 → 요약.
**분해(변형)**: 수치화 → 일별 CTR(노출 0=null) → 결측일(쌍×날짜 차집합) → 소재별·채널별 groupby → KPI → 원장 결합·상태 규칙 → 제안 산문(brief, 표만 근거) → 리포트 → `self:ledger upsert` 시도/폴백 → `sense:search >> table:since` 감시.

**작성 조건**: 훈련 가이드·조합 교재 2편·문법 전문·`describe` 18개 액션·관용구 계약(`원장에누적`·`묶어순위내기`·`미처리만고르기`)만 사용. 내부 코드 열람 0. 수정 주기: 기본 0회, 변형 1회(`$x = [try]{ return … }` — 블록 값은 마지막 문장. 검사가 `BIND_RETURNS` 로 줄·힌트까지 정확히 짚음, 29회차 수리의 효과).
작성 시간: 자료 생성기 약 6분, 기본 초안 약 8분, 변형 초안 약 4분(병렬로 기본 실행 대기 중 작성).

## 3. 검수와 독립 AI 비교

결정론 [verify.py](harness/verify.py): 분류 라벨 oracle 일치율, 원문 보존(123행 text 동일), 대표 인용 원문 일치·축 일치, 경쟁사 가격·형식 키워드, RTB verified 만, 금지어 검수 재계산 일치, PNG 6장 유효·정사각, 묶음 3파일, `published:false`, 후킹에 브랜드명 없음; 변형은 소재별 합계·CTR·KPI·좁히기=A2·결측일·노출0·미측정 2·원장 status·리포트 절.
카드뉴스 3장과 이미지 2장은 눈으로 확인했다(후킹→해결→그림→CTA 순, 1:1 그림은 브랜드 초록·크림, 글자 없음).
훈련자 기본 검수 14/14, 변형 11/11 통과. 분류는 oracle 과 123/123 일치(AI 비결정성은 이번 실행에서 0건이었다 — 다른 실행에서 보장되지 않는다).

### 독립 AI (ep4498 기본 · ep4499 변형)

같은 자연어([요청문](evidence/request_base.txt)·[변형](evidence/request_variant.txt))를 `/system-ai/chat` training background 로 보냈다. 훈련자 초안·정답·분해 방법은 넘기지 않았다.

| 관측 축 | 독립 AI 기본·변형에서 확인한 행동 |
|---|---|
| 풀이 | **`table:ai` 0회.** 고객 목소리 분류를 자료를 읽은 뒤 키워드 규칙 Python(`scripts/classify_reviews.py`, 6축 P1~P6)으로 풀고 `self:script` 로 실행(첫 호출은 SCRIPT_PATH 로 거절 → Bash 로 직접 실행). 카드뉴스도 자기 HTML 틀(`card.html`)→`engines:render` PNG 1080×1080, `engines:image_read` 로 자가 채점(A2 1차 불합격→레이아웃 수정→재검). IBL 은 읽기·검색·groupby 교차검산·렌더·이미지 읽기에 24회. 단일 전체 IBL 작성은 아니며 IBL 풀이 성공으로 세지 않는다. |
| 분할·재사용 | 변형은 자기 ledger·copy.json 을 읽어 반응과 결합, 새 Python 2개(`performance_calc.py`·`build_performance.py`)로 집계. `table:groupby` 교차검산 1회. 앞 턴 result_ref 재사용은 관측되지 않음(`reuse` 0). |
| 방법 발견 | 회상 제시 1(해마 2339·2341, script 3) 사용 0 — 홍보 용례가 해마에 없다는 사전 조사 그대로. `describe` 1회. **네이버 단건 호출로 `total_estimate` 를 스스로 찾아** 9칸 건수를 채움(훈련자는 배치 경로에서 못 찾음, L43-1). 변형에서는 네이버가 구절 검색을 적용하지 않음을 실험 2회로 확인하고 제목·요약 필터를 단 감시로 바꿈. |
| 완료 판정 | 123=111+12 검산, 인용 원문 대조, 파일 재독, 금지어 결정론 대조, 카드 자가 채점(1차 불합격 교정). 변형에서 결측·노출 0·미측정을 모두 명시하고 "제안만" 을 지킴. **평가 경로는 변형 턴에서 UNKNOWN** — 기준 C1~C4 가 직전 턴 과제의 것이어서 "현재 요청과 맞지 않는다" 고 평가기가 스스로 적음(L43-3). |
| 축적 | source=training 리허설. 증류·등록 없음. 감시 스트림 3개(`가상동네수리교실_naver_blog`·`_exact`·`_named`)가 `data/table_since.db` 에 남음 — 폐기 어휘 없음(L43-4). |
| 비용 | 기본 695.9초·입력 5.68M(cache_read 5.32M)·출력 66.6K, 변형 263.6초·입력 3.99M·출력 25.4K. 압축 0. 자작 관문 2회(두 턴 모두 Python 150줄+를 먼저 쓰고 세상 도구 확인을 안 해 걸림). |

**두 실행 대조.** 훈련자: 전체 IBL 1편(기본) + 1편(변형), AI 호출 4(분류·추출·문안·제안), 80.1초 + 12.2초, 모델 입력 30.6K. 독립 AI: 11.6분 + 4.4분, 입력 9.67M. 결과는 둘 다 oracle 과 일치(분류는 훈련자 AI 분류 123/123, 독립 AI 키워드 규칙 123/123 거친 축 기준). 품질 차이: 독립 AI 카드뉴스(1080×1080 전용 틀, 하단 정보 띠)가 훈련자 카드(`table:document` png — A4 문서 모양)보다 소재로서 낫다. 훈련자 브리프의 검색어 표는 정보량 0(L43-1), 독립 AI 는 변별력 있는 표. 둘 다 발행·발송 0.
훈련자 실행의 갭이 독립 AI 에서도 밟혔는가: L43-1 은 밟히지 않음(단건 경로를 실험으로 찾음) → 계약·안내 문제. L43-2 는 밟히지 않음(자기 JSON 모양을 Python 으로 직접 다룸 — 어휘 두 반쪽을 번갈아 쓰지 않았기 때문). L43-3·4 는 독립 AI 쪽에서만 관측.

## 4. 발견과 공통 개선 방향

### L43-1 — 검색 건수 비교의 유일한 근거 `total_estimate` 가 권장 배치 경로에서 사라지고 계약에도 없다

**분류: 계약 공백(도구)·발견 마찰.** 가이드가 "검색어가 여럿이면 한 호출에 — `queries:[…]`" 를 ★로 권장하고 `sections` 에 "검색어별 건수" 가 온다고 하지만, 그 건수는 **반환 행수(limit 상한)** 다. 훈련자는 세 유형 모두 `count:10` 을 받아 변별력 0 인 표를 브리프에 실었다(정직하게 "간접 추정" 으로 적었으나 쓸모 없음).
단건 `query` 봉투에는 네이버 전체 결과 추정 `total_estimate`(예 59,515) 가 있다 — [탐침](evidence/probe_naver_total_single.json): 단건 keys `[success,type,total_estimate,items,source]`, 배치 keys `[success,source,queries,count,_display,sections,items]`. `describe` 의 `observed_returns` 와 `target_description` 어디에도 `total_estimate` 가 없다. 독립 AI 는 단건 호출을 실험해 이 필드를 찾아 썼다(§3).
개선 후보: ① 배치 `sections` 에 `total_estimate` 동반 ② 계약 설명·관측 반환에 필드 명시 ③ 훈련 전 보강한 `marketing.md` 검색어 행의 "sections 건수 비교" 를 "`total_estimate` 비교(단건)" 로 정정. 어휘 신설 아님.

### L43-2 — JSON 원장의 파일 모양이 쓰는 길에 따라 뒤집히고, `self:ledger` 오류가 원인을 말하지 않는다

**분류: 계약 불일치(도구 간)·진단 안내 공백.** `[fn:원장에누적]`(관용구 어댑터 경로의 `self:write format:"json"`)은 **맨 배열** `[{…}]` 을 쓰고, 같은 행 목록을 직접 `>> [self:write]{format:"json"}` 하면 **봉투** `{items:[…],count}` 를 쓴다 — [탐침](evidence/probe_write_json_shape.json). `self:write` 설명("통화 보존 — items/count")은 봉투를 암시한다.
`self:ledger` 는 맨 배열 루트 또는 `target` 으로 가리킨 배열만 받는다. 훈련자는 봉투를 가정해 `target:"items"` 로 upsert 했고 `target의 부모가 객체가 아닙니다` 로 거절 → catch 폴백(`self:write`) 이 원장을 봉투로 **다시 써서 모양이 바뀜**(기본 뒤 맨 배열 → 변형 뒤 봉투). 루트가 배열인 파일에 `target` 없이 select/upsert 하면 정상([탐침](evidence/probe_ledger_origin.json) tiny·fresh_ext_modified ok). 봉투 파일에 `target` 없이 부르면 `select target 은 JSON 배열이어야 합니다` 만 나오고 details 가 `{}` 라 "루트가 객체이니 target 을 주라" 는 안내가 없다.
개선 후보: ① `self:write format:"json"` 의 모양 규칙을 한 가지로(또는 설명에 두 경우 명시) ② `self:ledger` 가 루트 모양을 보고 `{items:[…]}` 봉투는 자동으로 items 를 쓰거나, 오류 details 에 루트 타입·제안 target 을 싣기. 두 "원장" 반쪽(`원장에누적`·`self:ledger`)이 같은 파일을 번갈아 다룰 때 필요한 공통 계약이다.

### L43-3 — 후속 요청의 평가가 직전 턴의 기준으로 돌아 UNKNOWN 으로 끝난다

**분류: 관측·축적 공백(평가 경로).** 독립 AI 변형 턴(ep4499)의 응답 꼬리: `[평가 검수 미승인] 평가 응답에 달성 여부 판정이 없습니다: UNKNOWN — criteria C1(축별 건수·대표 인용)·C2(검색어 건수)·C3(소재·이미지)·C4(bundle)는 직전 과제의 기준이며 현재 요청과 맞지 않습니다 … C5(원장 3행)만 현재 과제와 관련`([status](evidence/ai_variant_status.json)). 즉 같은 대화의 후속 요청("조건이 바뀌었어 …")에 대해 평가기가 앞 턴에서 세운 기준을 상속해 현재 산출물(성과 리포트·KPI 판정·null CTR·결측 명시·감시 등록)을 평가하지 못했다. 평가기는 그 불일치를 정직하게 적었으나 달성 판정은 비었다.
개선 후보: 후속 요청마다 기준을 새로 세우거나(요청 문장이 바뀌면 C 재도출), 상속한 기준에 "현재 요청 적합성" 검사를 앞세워 맞지 않으면 재도출. 가이드 §4-5 "완료 판정 — 평가 경로가 돌았는가" 의 관측 항목.

### L43-4 — 같은 프로그램의 잡힌 실패가 `table:since` 기준선 저장을 조용히 취소하는데 응답은 "저장" 이라고 말한다

**분류: 구현 결함(실행 커밋·정직 보고 불일치).** 훈련자 변형 v1 은 `self:ledger` 거절을 `[try]/[catch]` 로 받아 폴백했고(`source_complete:false`), 그 뒤 `[sense:search] >> [table:since]{key:"LSI43_후기감시"}` 가 `"첫 검침 — 기준선 10행 저장"` 을 반환했다. 그러나 `data/table_since.db` 에 그 스트림이 없다. 최소 재현([단독](evidence/probe_since_alone.json) vs [잡힌 실패 뒤](evidence/probe_since_aftercatch.json)): 단독은 `LSI43_probe_alone` 5행이 영속, 잡힌 실패 뒤는 같은 note 를 내고도 `LSI43_probe_aftercatch` 가 DB 에 없다.
원인(진단 열람): `since_ops.py` 는 기준선 쓰기를 실행 커밋 scope 의 지연 action 으로 넘기고, `execution_commit.committed_program` 은 `success and source_complete` 일 때만 `scope.commit()` 을 부른다. 부분 원천 실행에서 상태 쓰기를 미루는 정책 자체는 방어적이지만, (1) 도구 반환 note 는 커밋 전에 "저장" 을 단정하고 (2) 미커밋 사실이 응답 어디에도 없다 — 트리거·감시 설계자는 기준선이 섰다고 믿게 된다. 또 독립 AI 가 남긴 폐기 스트림 2개처럼 **검침 스트림을 지우는 어휘·op 가 없다**(AI 도 "시스템의 감시 상태 기록에는 남아 있습니다" 라고 적음).
개선 후보: 커밋 보류 시 결과에 `state_committed:false`(또는 note 를 "기준선 저장 보류 — 실행이 부분 원천이라 커밋되지 않음") 로 바꾸기; 응답 봉투에 지연 action 의 커밋 여부 신고; 스트림 폐기는 새 낱말보다 `since` 의 `op` 도 어휘 증식이므로 기존 `self:ledger`/파일 수준 처리 가능성부터 판정. 발견만, 수리 없음.

## 5. 비용·낭비·한계

| 실행 | 모델 요청 | 입력 | 출력 | cache_read | cache_create | 벽시계 |
|---|---:|---:|---:|---:|---:|---:|
| 훈련자 기본 v0 (table:ai 3) | 3 | 25,090 | 5,031 | 1,632 | 23,452 | 80.1초 (이미지 29.8초·AI 44.6초·카드 4.0초·검색 0.7초) |
| 훈련자 변형 v1 (table:brief 1) | 1 | 5,492 | 1,068 | 544 | 4,946 | 12.2초 (brief 11.3초) |
| 독립 AI 기본 ep4498 (전체 계측) | 역할별 합 | 5,681,138 | 66,585 | 5,318,986 | 359,423 | 695.9초 (도구 48.2초·평가 모델 8.5초) |
| 독립 AI 변형 ep4499 (전체 계측) | 역할별 합 | 3,990,116 | 25,404 | 3,824,550 | 152,864 | 263.6초 |

훈련자 수치는 실행 봉투 `usage.model` 의 billable 합(call_id 중복 제거). `engines:image_gemini` 3회의 과금·토큰은 봉투에 없어 미측정. 훈련자(Codex) 자신의 작성·검수 토큰도 미측정.

- 필요한 비용: 123행 분류(AI 1회), 경쟁사 추출, 소재 문안 생성, 이미지 3, 카드 3, 결정론 검수와 원문 보존 대조, 반응 집계·리포트.
- 줄일 수 있었던 일: 검색어 근거 3호출은 limit 에 묶여 정보량 0(L43-1) — 단건 `total_estimate` 로 바꾸면 같은 3호출로 의미 있는 표. 변형의 `table:brief` 입력에 집계 기간을 넣지 않아 산문이 "기간이 없어 KPI 판단 불가" 라고 썼다(결정론 절은 이미 달성으로 판정) — 작성자가 items 에 기간을 넣으면 재호출 없이 해결, 모순 문장도 사라진다. 변형의 upsert 실패→폴백 재저장은 전체 원장을 다시 쓴 중복 쓰기(L43-2).
- 합성 자료의 cost_waste 대표 인용 2건이 같은 문장(접미 변형) — 자료 생성기의 템플릿 수 부족, 시스템 문제 아님.
- 회차 사전 기록 12:23 KST → 변형 검수 종료 12:35 (훈련자 작성·실행·검수·탐침 약 12분, 자료 준비 6분 포함 18분). 독립 AI 대기·회수는 별도(§3). 60분 상한 안.

미검증: 카피·이미지의 홍보 품질(사람 판단), 다른 AI 실행에서의 분류 비결정성, 실제 공개면 발행·측정(의도적으로 제외), `table:since` 두 번째 호출의 새 행 흐름, 네이버 외 소스의 건수 필드.

## 6. 종료와 재현

접수 작업 2개(`task_sysai_dd650b8e` 기본, 변형 task id 는 [receipt](evidence/ai_variant_receipt.json))는 `state:succeeded` 로 회수했다([기본 status](evidence/ai_base_status.json)·[변형 status](evidence/ai_variant_status.json)). 훈련자 실행 2건은 동기 완료. 탐침 7건은 전부 종료.
남은 것: `data/table_since.db` 에 독립 AI 스트림 3개와 탐침 스트림 `LSI43_probe_alone` 1개가 남음(폐기 어휘 없음 — 사용자 결정 시 sqlite 로 삭제). `outputs/…/_probe/` 탐침 파일은 로컬. 모델 교체·설정 변경 없음.
새 코드·어휘·설정 적용이나 예약은 없다. 훈련 전 보강한 `marketing.md` 2행 가운데 검색어 행은 L43-1 에 따라 정정이 필요하다(훈련 종료 뒤 문서 1행 정정 — 커밋에 포함).

재현: `harness/prepare.py` 로 입력·oracle 생성 → `harness/run.py base --draft main_v0.ibl --check` → 같은 명령에서 `--check` 제거 → `_staging/reactions` 를 `trainer/input/reactions` 로 복사 → `run.py react --draft react_v1.ibl` → `harness/verify.py <out> <input> <_oracle> qa.json [--react]`. 독립 AI 는 `harness/ai_chain.py base evidence/request_base.txt`, 변형은 `ai_chain.py variant evidence/request_variant.txt`(반응 자료를 `agent/input/reactions` 로 복사한 뒤). 이미지 바이트·AI 문안은 결정론 정답이 아니다.


## 7. 후속 수리 (2026-10-09)

사용자 수리 요청에 따라 정본 main의 `de6e9ba2`에서 진행했다. 기존 기본·변형 작업의
보존 status가 모두 `succeeded`/`completed`임을 확인한 뒤 구현을 수정했다.
최초 실행·산출물·발견 문장은 보존한다.

| 발견 | 공통 소유자와 변경 | 검증 |
|---|---|---|
| L43-1 | web 배치 병합이 원천 `total_estimate`를 각 sections에 보존한다. count는 반환 행수, 추정치 0과 미제공은 구별한다. 어휘와 마케팅 교재에 단건/배치 위치·기간 필터 이전 전체 검색 추정이라는 한계를 명시 | 제한된 반환 1행/추정59515, 추정0, 미제공, 부분 검색 실패의 병합 시험 |
| L43-2 | ledger의 루트 모양 불일치가 root_type·target·hint를 반환하고 IBL 오류 상세까지 보존된다. 배열/봉투의 target을 명시하게 하며 오류 시 파일을 바꾸지 않는다. 쓰기 교재에 두 저장 형식을 구별 | select/append/upsert × 배열/봉투 오류6건, 파일 바이트 불변·올바른 target으로 재실행 |
| L43-3 | framing_inheritance의 경량 패치 입력·허용 필드에 구조화 criteria를 포함. 후속 요청은 현재 criteria와 achievement_criteria를 함께 명시해야 계승되며, 누락·빈 기준은 재요청 후 일반 의식 규정으로 돌아간다. 정기 실행의 변경 없는 기준은 유지 | 변경 기준이 최종 평가 계약에 도달하고 user_quote·fallback을 보존하는 시험, 불완전 패치 거절·정기 실행 보존 |
| L43-4 | since는 프로그램 실행 중 저장 대기라고 반환하고, 실행 소유자가 최종 state_commit에 committed/not_committed/partial/failed/pending과 확정 수를 신고한다. 잡힌 도구 실패의 source_complete:false에서는 기존처럼 기준선을 올리지 않는다 | 정상·잡힌 실패·실패 종료·peek·중첩 실행·부분 저장 실패, 실제 임시 SQLite와 후속 새 행 비교 |

**L43-2 최초 원인 설명 정정.** 판본2 `원장에누적`은 어댑터가 format을 잃은 것이 아니다.
정본 `data/idioms/legacy_port_seeds.json`의 함수가 애초에
`[self:write]{content:json($합.items)}`로 배열 원문을 쓴다. format:"json"을 명시한
직접 목록 쓰기는 `{items,count}` 봉투를 저장한다. 기존 관용구 파일 모양을 바꾸거나
명시 target을 자동 교정하지 않고, 실제 계약을 가이드와 진단에서 드러냈다.

**전체 프로그램 재생의 범위.** 원래 main_v0와 react_v1을 처음부터 실행하되 모델·검색의
보존 영수증을 공급하고, 미디어 생성은 보관된 정사각 PNG로 대체했다. 현재 날짜는 훈련일로
고정했다. 로컬 파일 읽기·쓰기·표 계산·관용구 본문은 실제 구현, ledger는 실제 구현과 공통
인자 변환, since는 실제 구현과 임시 SQLite를 사용했다. 원래 변형의 target 오류·폴백·
미확정을 그대로 재현한다. 새 변형은 반응 입력 행을 역순으로 바꾸고 배열 원장의 target을
생략하여, 배열 형식 보존·원장 갱신·기준선 확정을 검증한다. 기본14·변형11 검수 조건을
각각 대조한다. 회귀의 집은 `backend/test_execution_commit.py`의 전체 프로그램 시험이다.

보존 결과 재생은 실시간 네이버 조회·새 이미지 생성·독립 AI의 작성 행동 검증이 아니다.
새 검색 추정치는 별도 생산자 배치 시험으로 확인했으며, 이전 검색 영수증에 값을 지어넣지 않았다.
전체 토큰/시간 절감이나 새 모델의 의미 판단 품질 향상은 측정하지 않았다.
원래 출력·입력·운영 검침 스트림은 수정·삭제하지 않았다. 스트림 폐기는 기존 DB 관리 범위이며
새 어휘·예약·자동 삭제를 추가하지 않았다.

### 최종 검증

- 직접 관련 39검사 통과(전체 프로그램 재생2 포함). 각 기본14·변형11 검수 조건이 두 재생에서 모두 일치했다.
- 영향 선택기: 변경7파일 → 전이 시험564/612(92%), execution_commit·ibl_v2_adapters·ibl_v2_runtime 허브로 전수 권고.
- 최종 backend non-system: **9,555 통과·1 건너뜀·실패0**, 121.22초.
- 추가 관련 묶음(Python 라이브러리·어휘 배포/분리·기존 긴문장 전체 재생·이번 검침 시험): **86 통과**, 49.54초. 위 직접 검사와 겹치는 항목이 있어 두 수를 고유 검사 수로 합산하지 않는다.
- 회원 경로/권한 포함 관련36검사, 용례 검토 관문4검사, 어휘 --check·층·은퇴 계약·Android 매니페스트 재생성·diff 공백 검사 통과. frontend는 변경하지 않았고 TypeScript 검사는 실행하지 않았다.
- 용례: ledger14·write95·search211·since38의 호출 표면을 검토했다. 새 반환 메타와 진단을 추가했으며 기존 호출 인자·행 반환·저장 형식은 유지한다. 실제 배열 관용구 #4889와 봉투 저장 예제 #4453의 차이를 교재에 명시했다.
- 최초 샌드박스 전수는 로컬 소켓·브라우저·자식 프로세스 제한 및 용례 재검토 미완료로 실패했다. 용례 원장을 갱신하고 승인된 권한으로 전수를 다시 실행한 결과가 위 최종 수치다.
- 활성 백엔드 ACTIVE·코드 지문 일치 확인. 실제 HTTP 검증에서 배열 root_type/hint 전달·target 교정 upsert·배열 형식 보존, since peek 미저장을 확인했다. 별도 실제 네이버 배치 조회2건은 각각 count=1, total_estimate=59515/105635였다. [활성 확인 증거](evidence/repair_live.json). 최초 확인 요청은 판본2 선언 누락으로 실행 전 거절됐고 선언을 보충한 요청만 성공 검증으로 셌다.

새 독립 AI 턴의 기준 작성/판정 정확도와 전체 시간·토큰 개선은 미측정이다. 미디어 대역을 쓴 재생으로 새 이미지의 시각 품질을 보증하지 않는다.
