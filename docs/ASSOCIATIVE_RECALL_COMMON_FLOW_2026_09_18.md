# 연상 회상의 공통 흐름 — 설계·집행 핸드오프 (2026-09-18)

> 사용자 판정(2026-09-18): **「네 기억을 최소한의 공통 기반 위에 놓고, 차이는 의미상 필요하거나 성능으로 입증된 것만 유지한다.」**
> 같은 원리로 작동하는 부분은 구현까지 공유하고, 공통 기반으로 옮긴 책임은 기존 코드에서 없앤다(양쪽에 남기면 통합이 아니다).
> 성능 판단은 두 단계 — ① 동작을 바꾸지 않는 구조 통합(이 문서의 집행분), ② 검색·정책의 통합·개선 실험(별도, 기억별로 잰다).

## 1. 무엇이 문제였나

09-17 의 공통 회상(`tree_recall`)으로 심층·세계·포식(장소 찾기)은 **검색 함수**를 이미 공유했다. 그러나 「어떤 상황에서 어느 기억을 찾고,
무엇을 전달하며, 결과를 어떻게 되먹일지」는 여전히 여러 곳에 나뉘어 있었다. 실측:

| 조립 지점 | 종전 | 결함 |
|---|---|---|
| `agent_pipeline.cognitive_stream` | 러너 `_build_execution_memory` 튜플 + 과제 원장 + 세계 지도 2블록을 손으로 덧붙임 | 순서·조립 규칙이 이 함수 안에만 있다 |
| `agent_communication` (에이전트 간 위임) | 같은 두 단계를 손으로 다시 씀 | 글자 채널(`method_map`)은 빠짐 |
| `api_system_ai.recall_preview` (조종실 검증창) | 1상만 부름 | **세계 지도·세계의 기억을 통째로 못 받았다** — "실제 주입물과 동일"이라던 표면이 거짓 |
| `switch_runner` (스위치 실행) | 해마만 직접 호출 | 관문이 찾아낸 네 번째 지점 |

새 기억 하나에 네 곳을 고쳐야 하고, 하나를 빠뜨리면 조용히 갈라진다. 되먹임도 셋(해마 사용 결과·가지 밖 적중·장소 흔적)이 각자였다.

## 2. 경계 — 공통으로 관리할 것 / 기억별로 남길 것

| 공통(`backend/cognition/associative_recall.py`) | 기억별(각 공급원이 부르는 저장소) |
|---|---|
| 요청의 주체·채널·권한과 회상 시점(1상/2상) | 자동 회상인지, 명시적으로 열 때만인지(정책 표의 값) |
| 후보의 식별자·출처·상태·분량 (`Block`) | 후보가 실행 절차인지·사용자 사실인지·장소인지·지식의 단서인지 |
| 전달 분량과 최종 문맥 조립 (`Recall.text()`) | 검색기(해마=전용 인코더·sqlite-vec+FTS5, 트리 기억=`tree_recall`)·순위·실행 가능성 검사 |
| 제시 기록 (`recall.presented` 사건) | 무엇을 성공으로 보고 어떻게 학습·정리하는지(해마 `record_recall_outcome`, 가지 밖 적중 원장, 장소 흔적) |

**점수를 섞지 않는다.** 해마 점수는 반사 분기의 값이고 세계기억 순위는 단서 고르기의 값이다. 공통 흐름은 이를 `ReflexSignal`(이름 붙은 출력)로만 드러내며
합산·정렬하지 않는다. 지금 필요한 차이만 표현한다 — "다른 기억도 반사에 기여"하도록 미리 넓히지 않는다.

**되먹임은 형식만 공통.** 사건 `recall.presented` 가 턴마다 「채널·request_type·반사 신호·공급원별 {status, ids, chars, ms}」를 남긴다.
해석과 갱신 규칙은 기억별로 둔다(원장 파일을 물리적으로 합치지 않는다). 사용 여부의 결합 키: 해마=용례 id·코드(`build_execution_memory_detail`),
심층=항목 id·가지, 세계=이름·별칭 — 결합 자체는 §8(2단계 ①).

## 3. 계약

```python
recall = runner._associate(message, history=…, channel="pipeline", action_hint=…, deep=True)   # 1상: 분류 전
recall.reflex.score / recall.reflex.code          # 반사 분기가 읽는 이름 붙은 출력
recall.attach("pursuit", block)                   # 두 상 사이에 파이프라인이 끼우는 블록(과제 원장·문맥 갱신 표식)
recall.route(request_type, reflex_hint=…, force_role=…, context_update=…)   # 2상: 분류 뒤(세계 지도 글자 채널이 request_type 을 본다)
recall.text()                                     # 주입 문자열 — route 전엔 RuntimeError
recall.presented()                                # 제시 기록(사건에도 남는다)
```

- 두 상인 이유: 반사 신호는 분류 *전에* 필요하고, 세계 지도의 글자 채널은 분류 *뒤*(request_type)에 도는 종전 정책을 보존해야 한다. 시점이 둘이어도 정하는 책임은 한 곳이다.
- `Source` 표(`SOURCES`): 이름·태그·상·personal(주체 관문)·needs(요청 필드)·auto. 포식 기억은 `auto=False` 로 실려 "어휘가 입구"(09-03 판정)가 데이터로 보존된다.
- `CHANNELS` 표: 채널별로 어느 공급원이 도는가. 값은 **종전 동작을 그대로 옮긴 것**: `agent_message` 는 `method_map` 제외, `switch` 는 해마만. 바꾸는 일은 2단계 실험이다.
- 러너 훅 `CognitiveRecallMixin._associate` 는 위임만 한다. 회원 러너는 `stub(...)` 로 덮어써 주인 기억(1상)을 돌지 않는다(2상 세계는 개인 기억이 아니라 돈다).
- 실패 격리: 한 공급원의 예외는 그 블록만 `status=error` 로 남기고 다른 기억을 막지 않는다(종전엔 1상 전체가 빈손이 됐다 — 동작 불변의 유일한 예외이며 개선 방향).

## 4. 옮긴 것 / 남긴 것 (함수 단위)

| 종전 | 지금 |
|---|---|
| `cognitive_recall._build_execution_memory` (주체 관문·순서·조립·요약 로그) | `associative_recall.begin/_run_phase/route/text` — **삭제** |
| `_memory_map_scent`·`_recalled_memory_scent`·`_guide_map_scent`·`_limb_presence_scent`·`_pending_repair_scent`·`_decision_scent`·`_deep_memory_db`·`_note_outside_hit` | 모듈 함수 `_memory_map`·`_recalled_memory`·`_guide_map`·`_connected_limbs`·`_pending_repair`·`_decision_ledger`·`deep_memory_db`·`note_outside_hit` — 믹스인에서 **삭제** |
| `agent_pipeline` 의 과제 원장·문맥 갱신·세계 지도 덧붙이기 | `recall.attach` + `recall.route` — 문자열 덧붙임 **삭제**; `pursuit_bind.prepare()` 는 블록만 돌려준다 |
| `agent_communication` 의 손 조립 | `_associate(...).route(None).text()` |
| `api_system_ai.recall_preview` 1상만 | `_associate(..., channel="preview").route("THINK")` + `presented` 노출 |
| `switch_runner` 해마 직접 호출 | `begin(holder, command, channel="switch").route("EXECUTE")` |
| `prompt_composition._recall_bundle` 러너/해마 이중 경로 | `begin(runner_or_None, …, channel="sample")` 한 경로 |
| **남긴 것**: `ibl_usage_rag.build_execution_memory(_from_hint)`(검색·별칭·관용구·구현 조회·액션 검증), `catalog_recall.recall_for_turn/world_memory_for_turn`, `tree_recall`, `decision_ledger.scent_xml`, `red_report.pending_scent`, `hippo_tree.guide_map_text` | 공급원 함수가 부르기만 한다 — 이 안을 건드리면 재학습·검색 경로가 흔들린다 |

## 5. 증명

- **고정물** `scripts/recall_golden.py`(git 밖 `data/recall_index/golden/before.json`, 심층기억 본문 포함): 14 입력(실행·심층·세계·포식 단서·후속·수리 단서·긴 문서·잡담)에 대해
  손대기 전에 녹화 → 통합 뒤 `check` — **14/14 블록 본문·순서·반사 신호 동일**(재현성: 수정 전 두 번 녹화도 동일). 지연·글자 수는 보고만.
- **관문** `scripts/check_recall_assembly.py`(pre-commit + CI `recall-assembly`): A) 공급원 진입 함수는 `associative_recall`(과 정의 모듈) 밖에서 호출 금지, `tree_recall.recall` 은 `associative_recall`·`catalog_recall` 만.
  B) `_associate`/`begin` 을 연 함수는 같은 함수에서 `.route` 로 닫는다. 첫 실행이 `switch_runner` 의 네 번째 조립 지점을 찾아냈다(사람 grep 은 셋만 봤다).
- **은퇴 등록** `data/retired_contracts.yaml` `recall_assembly_per_call_site` — 옛 이름 7개가 어느 표면에도 남지 못한다.
- 조종실 검증창 실측(통합 후): `method_map`·`world_map` 이 처음으로 실린다(종전 `present=False`).

## 6. 완료 기준(사용자·Codex 합의)과 판정

| 기준 | 판정 |
|---|---|
| 새 기억을 붙일 때 파이프라인 여러 곳을 고치지 않아도 되는가 | ✅ `SOURCES` 한 줄 + 공급원 함수 하나. 네 호출 지점은 표를 모른다 |
| 어떤 기억이 왜 제시되고 어떻게 쓰였는지 한 경로로 추적되는가 | ✅ 제시 `recall.presented` + 사용 `recall.used` 두 사건(§8, 2단계 ① 집행) |
| 같은 입력에 후보·순서·주입·반사 판단 유지 | ✅ 고정물 14/14 |
| 지연·토큰 불변 | ✅ 글자 수 동일, ms 는 잡음 범위 |

## 7. 2단계(별도 실험, 기억별로 잰다)

1. ✅ 사용 결합 — §8 (2026-09-18 집행).
2. 채널 정책 실험: `agent_message` 에 글자 채널, `switch` 에 심층·가이드 — 각각 켜고 기억별 지표로 판정.
3. 검색기 통합 실험: 해마 전용 인코더는 유지(세계 어휘 13/24 대 20/24 실측). 후보 수(`n_branches/k_in/k_out`, `DEFAULT_K`, `MAX_ITEMS`)의 정책 표 이전은 효용 실험과 함께.
4. 가지 문서 기질 공통화(hippo_tree·forage_doc·memory_tree 의 표식·절·동기화·갱신 기록): 절 나누기는 공유하기 쉽지만 동기화엔 기억별 식별·삭제·검증 규칙이 있다 — 여기서 다시 판단.

기억별 품질 고정물: 해마 T5, 심층 정답 40건(`evaluate_tree_recall.py`), 세계 질문 24(설계 부록 A), 포식 장소 찾기 @1. 합산 평균은 보지 않는다.

## 8. 제시→사용 결합 (2단계 ①, 2026-09-18 집행)

**원칙**: 형식은 공통, 해석은 기억별, 점수는 안 고친다. 세 되먹임(해마 사용 결과·가지 밖 적중·장소 흔적)의 뜻이 다르므로 한 값으로 접지 않는다.

| 층 | 무엇 |
|---|---|
| 결합 키 | 공급원이 `Block.join` 으로 제시 항목의 결합 키를 낸다 — 해마 `{items:[{id, code, kind, alias}]}`(`build_execution_memory_detail`), 심층 `{paths:{id: 가지}, db}`, 세계 두 채널 `{names:{id:[이름, 별칭…]}}`(`recall_for_turn_detail`/`world_memory_detail`). 옛 튜플·문자열 판은 래퍼로 남는다 |
| 전달 | `Recall.usage_payload()` → 파이프라인이 `_after_response_async(presented=…)` 로 값으로 넘김(증류 큐 payload) — 사건엔 id·건수만(4KB 절단 안전) |
| 해석기 (`USAGE` 표) | 해마 `executed`: 제시 용례의 `[node:action]` 쌍이 이 턴의 execute_ibl 에 등장(`record_recall_outcome` 과 같은 규칙), 관용구는 `[fn:이름]`. 세계 `mentioned`: 이름·별칭(2자 이상)이 응답·코드에 등장 — 약한 증거(모델이 이미 알던 이름일 수 있다). 심층 `expanded`: `[self:memory]{op:"recall", node|expand:"#id"}` 가 제시 가지·id 를 열었다 / `confirmed`: 증류가 SAME/UPDATE 로 다시 만나 `used_at` 을 올렸다(전후 대조). 자동 회상은 사용이 아니다(used_at 계약 유지) |
| 기록 | `_after_response` 5단계에서 `record_usage` → 사건 `recall.used` `{blocks:[{source, presented, used, evidence}]}` 하나 |
| 읽기 | `scripts/recall_usage_report.py` — 기억별 제시 턴·결합 턴·항목 사용률·증거 분포, 자주 제시되나 안 쓰인 항목. 합산 평균 없음 |

**갱신 규칙은 그대로**: 해마 success_rate 는 `record_recall_outcome`(top-1·≥0.85), 심층 `used_at` 은 증류·명시 조회, 세계는 없음. 결합은 관측이지 학습이 아니다 — 학습 규칙을 바꾸는 일은 이 보고서를 근거로 기억별로 판정한다.

**해마 해석의 알려진 거칠기**: 같은 `[node:action]` 을 공유하는 용례 둘이 제시되면 둘 다 `executed` 로 센다(실측: `[self:workflow]{op:"run"}` 두 용례). 용례 단위의 정밀 귀속은 인자까지 대조해야 하며, 그것이 해마의 규칙 개정이므로 여기서 하지 않았다.

증명: `backend/test_recall_usage_join_2026_09_18.py`(해석기 3종·사건 형식·payload/사건 분리·used_at 스냅샷·상세 판=튜플 판), 고정물 `recall_golden.py check` 14/14 동일(주입 XML 불변), 실데이터 smoke(근무표 질의: 해마 2/2 executed·세계 글자 1/5 mentioned·심층 0/3).
