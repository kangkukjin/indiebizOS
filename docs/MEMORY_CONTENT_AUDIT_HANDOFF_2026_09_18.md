# 기억 재고 감사 — 핸드오프 (2026-09-17 밤 ~ 09-18 새벽)

> 한 세션에서 "기억의 *회상 메커니즘*이 아니라 *내용물과 구조*"를 점검·정리했다. 컨텍스트가 차서 여기서 끊는다.
> 짝 문서(회상 설계): `docs/TREE_MEMORY_RECALL_COMMON_DESIGN_2026_09_17.md`.
> §4 "실행기억의 문법 감사" 는 이어받은 세션에서 집행 완료. **다음 = §3 의 5번(세계의 기억 재건)** — 2·3·4번 집행 완료.

## 0. 사용자 질문의 흐름
1. 심층기억·실행기억·세계의 기억의 *재고 품질*을 점검하라 → 셋 다 재고가 문제였다.
2. 심층기억 입구 관문 집행 → 기존 재고 정리 → 가지 사전 채우기 (완료)
3. "실행기억은 초기에 AI 가 생성한 게 많고 그 뒤 IBL 이 많이 바뀌었다 — 처음부터 자세히 봐야" → 전수 정독·집행 (완료)
4. **"어휘도 어휘지만 문법도 문제 아니냐. 그때는 공통 통화도 없었을걸?"** → 집행 완료(§4)

## 1. 끝난 것

### 1-1. 심층기억 입구 관문 (backend, 미커밋·라이브 반영)
- ★정정: 작업일지·`[보충]` 오병합은 09-12 증류기 개편(`562c4598`·`cf4ac0d9`)이 이미 막았다. 내가 읽은 쓰레기는 그 이전 재고였다.
- 남아 있던 입구 결함 둘을 막음:
  - **발화자 축** `utterance_author`(owner/agent/schedule/member) — 모든 `cognitive_stream`·`process_system_ai_message` 호출이 명시(fail-closed), `owner` 만 심층 증류. 배선 = `agent_pipeline` → `_after_response_async(write_deep=)` → 증류 큐 payload. 예약 주입은 `calendar_actions` 가 WS dict 에 `schedule` 표식. 실측 뿌리 = 시스템 AI 위임문의 하네스 안내가 건축 에이전트의 `사용자선호` 로 저장(#7, ep3832).
  - **지시 대상 관문** `memory_evidence.unresolved_reference`(첫 단위의 의존 머리 · 단독 단위 속 지시 관형사) + 추출 프롬프트에 "가리키는 앞 단위를 source_ids 에 함께". 실저장 42건 재생 → 16건 거절. 거절은 `memory.distill.rejected` 궤적 사건.
- 회귀 = `backend/test_deep_memory_entrance_2026_09_17.py`(진입점 전수 AST 관문 포함). 문서 = `data/system_docs/memory.md` §5.
- 미검증: 새 추출 프롬프트의 라이브 거동(실 DB 쓰기라 시험 안 함).

### 1-2. 심층기억 재고 정리 (적용 완료 — 사용자가 직접 실행)
- 22 DB 981건 전수 판정 → **479건 삭제**(시스템 AI 300→87), `[보충]` 오병합 13건 머리만, 고아 DB(`투자/memory_None.db`)의 투자 철학 2건을 본 DB 로 이주.
- 백업·판정표 = `data/_backups/2026-09-17_deep_memory_cleanup/`(`cleanup.py` 가 곧 판정 기록, 복원 = DB 복사).
- ★실삭제 명령은 세션 분류기가 막았다 → 백업·dry-run 까지 하고 명령을 사용자에게 건넸다. (실행기억 집행은 막히지 않았다.)

### 1-3. 가지 사전 채우기 (적용 완료)
- 15 DB·산 가지 114개 전부에 `> 요약`(정리 뒤 내용 기준)·`찾는 말:`(주인이 할 법한 일상 표현)·`함께 볼 가지:`. 단독 가지 7건 합침, 빈 가지 32개 문서·고아 DB 10개를 백업 폴더로.
- 스크립트 = 같은 백업 폴더 `fill_branch_dictionary.py`(사전 표가 곧 기록, 재실행 안전).
- ★잠복 결함 수리(패키지 파일, 미커밋): `memory_tree.ensure_column` 이 `node` 만 보장해 `source_ref` 없는 옛 DB(법률·출판사×2·행정)에서 가지 열기·문서 재렌더가 `no such column` 으로 죽던 것 → 두 칸 다 보장.
- 연기 시험 가지 @1 12/12 — 내가 쓴 질문이라 낙관. 진짜 판정은 실사용 `data/recall_index/outside_hits.jsonl`.

### 1-4. 실행기억 전수 정독 (적용 완료 — DB·training JSON 은 git 밖)
- 3,879행(코드 2,368종)을 머리 액션별로 정독 → **삭제 292 · 코드/의도 교체 87** → 3,587행. training JSON 도 같은 쌍으로(`ibl_distilled.json` −190, `balanced_20260516` −69·교체 53). 새 코드는 파서·타입·인자 검사 통과 후 적용·재임베딩.
- 범위: engines·limbs·others·table·fn·self 전부, sense 는 비-수동시드 전부. sense 의 수동 시드 전용 묶음은 직접 읽지 않고 발견 부류의 기계 훑기로 대체.
- 백업·판정표 = `data/_backups/2026-09-17_hippocampus_review/` (`verdicts.py` = id 별 사유, `apply_verdicts.py`, `manifest.json` = 변경 전후).
- 부류(★ = 검사기가 원리적으로 못 잡음):
  - ★**H 행동이 바뀐 어휘** 27 — `[self:memory]{op:"save"}` 는 09-12 부터 무동작인데 용례 15건이 "기억해둬"에 회상 / `sense:phone` = 결제 앱 포획 알림만 / `sense:world` = 시스템 자기 상태 없음 / 네이버 책 검색 은퇴.
  - **E 틀린 인자**(헐거운 검사기 통과) — kr 재무 `corp_code:"005930"`+`report_type:"income"`, us 재무 `type`(읽는 키는 `statement_type`), `channel_send{message}`(→`body`), telegram·slack 없는 채널.
  - **C 직시어 상수** — "근처·내 주변·이 동네·우산 챙겨야 돼?" → 서울/강남/종로 상수 → `[sense:here]` 로 교체.
  - **A 오대응** — 사이트 북마크→라디오 즐겨찾기 9, 연락처→메시지 검색 5 등.
  - **B/F 일회성·개인** ~175 — 증류된 수리·조사 주행(개인 절대경로·10KB 본문·의료·여행). **삭제의 2/3 = 증류가 일반화를 못 하는 것이 최대 오염원.**
- 벡터 없는 행 23건은 이전부터(09-09 기록과 동일). 라이브 백엔드 검색 캐시는 재기동 때 비워짐.

## 2. 세계의 기억 — 점검만(미집행)
1,265항목 중 1,099(87%)가 09-17 하루 AI 편집 초안(파일당 정확히 100, "not individually source-verified"). 별칭 영어뿐 1,056(83%) → 글자 채널 2/24 의 원인. 2단 가지 167 중 단독 79·≤2건 103. 관계가 닿는 항목 279(22%). tool 26·resource 2. 가지 사전 `gist`·`see_also` 0/167.
처방 방향: 사용자의 실제 질문 원장에서 자라게 + 한국어 일상 별칭 + 단독 가지 합치기·`함께 볼 가지` + 이 몸에서 실행 가능한 도구·자료원 보강.

## 3. 남은 일 (우선순위 순)
1. ~~§4 실행기억 문법 감사~~ ✅ 09-18 집행(§4). 조합 용례 보강도 집행(§4 ④-집행). 근접 중복도 집행(§4 ⑤). 실행기억 다듬기 완료 — 재학습은 사용자 지시 대기
2. ~~증류 입구 관문~~ ✅ 09-18 집행(미커밋) — `ibl_idiom.example_entrance_reason`(개인 명사·홈 경로를 의도·코드 양쪽 + 본문 1,000자 상한)을 `ibl_usage_rag` 저장 직전에. 지운 증류 191건 재생 92건 거절·남은 53건 오탐 0. **남은 절반(의도↔코드 오대응·일회성 질의)은 기계 관문 밖** — 반성기 프롬프트의 일. 회귀 `backend/test_distill_entrance_gate_2026_09_18.py`, 문서 memory.md.
3. ~~검사기 조이기~~ ✅ 09-18 집행 — ①`ibl_param_vocab.allowed_param_keys` 의 허용 키 = **그 액션의 선언**(input_schema·aliases·target_key). 패키지 전체 읽기키는 스키마 없는 도구의 폴백으로만. 조이기 전 실측: 코퍼스 3,635행 중 1행·실사용 2,463 step 중 3종만 새로 걸림(빌드의 param 선언 완전성 관문이 코퍼스를 이미 선언에 묶어 둔 덕 — "대량 빨강" 우려는 기우였다). 가려져 있던 선언 구멍 3건 보충: `self:read.sheet`·`limbs:browser.submit`(읽는데 미선언)·`sense:researcher` 의 `query` 별칭. `[self:script]{name}` 은 진짜 적발. ②없는 op 값 — `/ibl/validate` 표면에만 붙어 있던 검사를 `unknown_op_message` 로 옮겨 `check_params` 가 한 벌로 맡는다(증류·시딩·관용구 등록·실행 경고가 같이 본다). 조인 뒤 코퍼스·training JSON 빨강 0, 실사용 1,823 코드에서 6종(전부 진짜 오타). 회귀 `backend/test_param_check_action_scope_2026_09_18.py`. 남은 조각 둘도 같은 날 집행: ③`ibl_typecheck._type_action` 이 없는 op 을 **error** 로 낸다(같은 `unknown_op_message`) ④**T3 죽은 이음매 경고** — `ibl_pipe_types.dead_seam_warnings` + 소비자 17개에 `pipe_in: true` 선언(사전 데이터, 액션 이름은 검사기에 없다). 처음엔 '언어 표면 변경이라 판정 대상'이라 미뤘으나 문법이 아니라 사전 선언+정적 규칙(T1·T2 와 같은 부류)이라 집행. 거절이 아니라 경고인 이유 = `>>` 의 성공 의존은 정당. 실측: 코퍼스 경고 0 · 실사용 1,823 코드에서 알려진 죽은 이음매 1건만(오탐 0). 부패 방지 = `_prev_result` 를 읽는 패키지에 소비자 선언이 없으면 실패하는 시험. 회귀 `backend/test_dead_seam_and_op_check_2026_09_18.py`, 문서 ibl.md §통화와 변환자.
4. ~~행동이 바뀐 어휘를 잡는 관문~~ ✅ 09-18 집행 — `scripts/iblbuild_example_review.py` + 원장 `data/ibl_example_review.json`(액션 166개의 계약 필드 지문). `build --check`(pre-commit)가 지문과 대조해 계약이 바뀐 액션마다 **바뀐 필드·로컬 용례 수**를 말하고 실패 → `--show` 로 읽고 고친 뒤 `--ack`(원장도 스테이지). 근거: 09-12 memory save 무동작화는 git 에서 target_description·ops.returns·ops.side_effect·ops.values·fixture 변화로 그대로 보였다 — 읽는 절차가 없었을 뿐. 기준선은 이번 세션의 전수 정독 뒤 상태. 못 잡는 것 = 사전은 그대로인데 핸들러만 바뀐 변화(문서 갱신 의무의 자리). 회귀 `backend/test_example_review_gate_2026_09_18.py`, 문서 ibl.md §건강·hippocampus_retraining.md §7.
5. 세계의 기억 재건(§2).
6. 커밋 — 이번 세션의 backend 13파일+회귀·`memory.md`·`memory_tree.py` 가 **다른 세션의 미커밋 회상 작업과 같은 파일에 섞여 있다**(`agent_pipeline.py`·`agent_communication.py`·`api_system_ai.py` 등). 사용자 지시 대기. pathspec 으로도 파일 단위로는 못 가른다 — 같이 커밋하거나 `git add -p`.
7. ⚠곁가지(미수리·미재현, 사용자 판정 요청해 둠): 예약 주입문이 채팅 핸들러를 타며 `set_task_origin("user")` 를 받는다 → 예약 턴이 RED 수리 그랜트 자격을 얻을 수 있음. 헌법("스케줄러 = 미세팅 = fail-closed")과 어긋남. 이번에 넣은 `schedule` 표식을 그 자리에서 읽으면 닫힌다(`services/chat_streams.py` 의 `_so("user")`·`_set_origin("user")` 3곳).

## 4. ✅ 실행기억의 문법 감사 (09-18 이어받은 세션에서 집행 완료)

도구·판정·백업 = `data/_backups/2026-09-18_hippocampus_grammar/` — `seams.py`(이음매 전수 추출기, 읽기 전용·재실행 안전) · `verdicts_I1.py`/`I1b`/`I2`/`I2b`/`I2c`(부류별 판정, I2 계열은 `*_frozen.json` 이 확정본) · `manifest_*.json`(변경 전후) · `ibl_usage.db`·training JSON(집행 전 백업). 집행 = 09-17 `apply_verdicts.py` 재사용(부류마다 새 판정 파일). 결과 3,587 → **3,586행, 교체 132·삭제 1**, 전 행 재검 구문 0·인자 경고 0.

**① 죽은 이음매(I1) — 교체 38·삭제 1.** 이음매 883개(572행) 중 B 가 변환자 아님·명시 참조(`$items` 등) 없음·`_prev_result` 를 읽는 소비자 아님 = 101개. 그중 **B 가 자기 입력도 없이 서 있는 것**만 죽은 이음매다(기계 판별식: 비소비자 B 의 인자가 `op`·`title` 뿐).
- `[sense:here] >> [sense:restaurant]{}`·`>> [sense:weather]{}` 9행 — **실행 실측 실패**("query 필요"/"city 또는 lat/lon 필요"). ★전 세션이 C 부류 교체로 심은 것(30여 건이 아니라 9건 — 나머지는 이미 `$위치` 꼴이었다). → `$위치 = [sense:here]` + `x/y`·`lat/lon` 명시(실측 통과).
- **`… >> [table:brief] >> [self:notify_user]{}` 14행** — 최대 부류. notify_user 는 앞 결과를 읽은 적이 없다(`git log -S` 로 확인) → 제목도 본문도 없는 빈 알림. 08월 상상훈련 수동 시드·workflow/trigger `do:` 몸에 퍼져 있었다. → `$요약 = … >> [table:brief]{…}` 다음 줄 `[self:notify_user]{message: "$요약.message"}`(실측: 블록 안 재할당·`$요약.message` 경로 통과). `channel_send{channel_type}`(to·body 없음) 1행도 같은 처방.
- `search_youtube >> [limbs:music]{play|add}` 6 → `query` 가 곧 검색어. `take{n:1} >> [limbs:cctv|radio|radio_favorite]` 5 · `file_find >> [self:fill|delete]{}` 2 → `[table:each] { …'$it.필드'… }`(필드명 실측: cctv `url`, radio `stream_url`/`station_id`, file_find `path`). 의존 없는 순차 2 → `;`.
- **죽은 게 아닌 것**(처음 가설 정정): `build >> deploy >> check`·UI 자동화(`snapshot >> tap >> type`)·`body diff >> commit` — 통화는 안 넘지만 **"성공했을 때만 다음"** 이 실제 의존이다. ibl.md 의 `>>` 정의 그대로라 정당. `;` 로 바꾸면 빌드 실패 뒤 배포가 돈다.
- 추출기 주의: `_parallel.branches`·`_fallback_chain` 은 형제 가지다 — 순서열로 걸으면 `A & B` 가 이음매로 오계수된다(1차 1,011 → 정정 883).

**② 옛 표기(I2) — 교체 93.** `pipeline:` → `do:` 39행(전부 balanced 코호트, 몸 안 `\"` 이스케이프 → 홑따옴표. 08월 M1 "문장 자리 이름 통일" 이전 양식) · 문자열 속 `[자리표]`/`{자리표}` → `<자리표>` 33행(어휘·params 괄호와 같은 글자. #4475 는 API 경로 템플릿이라 제외) · `"..."`·`/abs/path/img.png` → 이름 있는 `<자리표>` 21행.
- 손대지 않은 것: `where` 문자열식 31행(구조형 51행과 공존 — ibl.md 가 은퇴를 선언한 적 없다) · `| where:` 단축 0행 · `{{_prev_result}}`·`$prev` 0행 · 이름 있는 함수(idiom/manual_registry)의 `[table:each]{do: "…"}` 4행(그중 #4543 은 `do: "${상세}"` — 몸이 인자라 블록으로 못 쓴다. 관용구는 개정 원장이 있는 별도 경로).

**③ 필드 경로 — 결함 아님.** `sense:stock{…}.current_price`·`.data.current_price`·`.items.0.current_price` 셋 다 같은 값(256000.0)으로 풀린다(실측). 추출기가 봉투를 내려가 찾는다.

**④ 조합 부재 — 진단만(미집행).** 단발률: balanced_20260516 **93%**(변환자 0%·블록 0%) · synthetic 89% · manual_seed 65% · 기타 58% · **distilled(실사용 증류) 22%**(`>>` 57%·변환자 41%·`$변수` 35%). 5월 시드는 문법이 틀린 게 아니라 **문법이 없다** — 실사용은 78%가 조합인데 행 수의 47%를 차지하는 코호트가 단발만 가르친다. 처방은 삭제가 아니라 조합 용례 보강(같은 의도의 현행 관용 짝)이고 재학습과 묶인 별도 작업.

**④-집행 (09-18, 사용자 지시 "일단 용례를 보강해줘, 재학습은 다듬기가 끝나면") — 조합 용례 73건 시딩.** 3,586 → **3,659행**, 벡터 누락 0, `ibl_distilled.json` +73(682). `source: manual_seed`·`tags: compose_2026_09_18`.
- 고른 법: 생산자(returns items) 76종마다 단발/조합 용례 수를 세어 **단발 ≥8·조합 ≤2** 인 28종을 표적으로(paper 48:1, business 42:1, weather 34:2, neighbor 33:2, company 30:1, manage_events 28:2, finance 25:2 …).
- 쓴 법: 각 생산자의 어휘 fixture 를 실행해 **실제 행 필드**를 받아(`producer_probe.json`) 그 필드로만 썼다. 꼴은 filter(구조형 where)·sort·take·select·groupby(agg)·compute·since·merge/union·brief·chart·document·spreadsheet·each·`$변수`+알림.
- 검증: `verify_seeds.py` = 구문·인자·타입·입구 관문 + **실행**(부작용·AI 단계 앞까지 잘라서). 73/73 통과, 0행 13건은 정상 선별(비 오는 날 없음 등). 실측이 잡은 제 오류 3건: `used` 행에 `source` 열 없음 · "네이버" 동명 기업 13곳 · "NAVER" 는 미국 티커로 해소.
- 회상 연기 시험: "이번 달 어디에 돈 많이 썼어"·"논문 찾아서 표로"·"근처 약국 지도로" 에 조합 꼴이 Top-3 에 오른다. **"다가오는 일정" 은 아직 단발 3건이 Top-3 를 독점** — balanced 코호트의 같은 코드 중복이 자리를 먹는다(다음 다듬기 표적: 근접 중복 단발).
- ★실측 부작용 정리: `[table:since]` 시드 실행이 `data/table_since.db` 에 기준선 4종(46행)을 만들어 지웠다. since 를 실측할 땐 `peek: true` 로.
- 도구·백업 = 같은 폴더 `compose_seeds.py`·`verify_seeds.py`·`verify_compose_seeds.json`·`ibl_usage.before_compose.db`·`ibl_distilled.before_compose.json`.

**④-부수 수리 — 검사기 오탐 뿌리 둘 (미커밋).** 시드 검증에서 타입 경고 12건이 떴는데 11건이 오탐이었다.
- **열 관측이 10열에서 잘렸다**: `scripts/ibl_shape_sweep.py` 의 `MAX_KEYS = 10` 은 표시용 절단인데(표시 상한은 `ibl_access` 렌더러가 `[:8]` 로 따로 가진다) 정적 검사기가 그 잘린 목록을 전체로 읽어 11번째 이후 열(`place.distance`·`book.loan_count`·`performance.start_date`·`realty.price`)을 "없는 열"로 경고했다. 170개 관측 중 37개가 정확히 10열이었다. → 상한 40 + 넘으면 `more` 표기, `ibl_typecheck._catalog_cols` 는 `more` 관측을 미상으로 기권. 재스윕 결과 최대 23열·`more` 0건.
- **가계부는 열이 op 이 아니라 `query_type` 으로 갈린다**(summary=가게별 집계 / 지출·수입·거래=거래 행) → `finance-record/ibl_actions.yaml` 에 `shape_variants` 3종 선언. 이를 막던 빌드 관문(`_check_shape_variants` 의 "부작용 액션 금지")은 액션 통째의 플래그만 봤다 — **변이 코드가 부르는 op** 을 `ibl_ops.op_side_effect` 로 해소하게 고침(파괴적 op 을 부르는 변이는 여전히 거절, 회귀 추가).
- 회귀: `test_shape_variant_axis`·`test_ibl_typecheck`·`test_pipe_type_check` 등 8파일 106건 통과, `build --check` ✓.

**⑤ 근접 중복 단발 (09-18 집행) — 코퍼스가 아니라 회상을 고쳤다.** 이름 없는 3,614행 = 코드 2,148종. 같은 코드를 나눠 가진 행이 1,876(410군)인데 **의도까지 같은 진짜 중복은 24행뿐**이고 나머지는 설계된 바꿔 말하기(코드 하나에 의도 5개 묶음이 182군, 5월 balanced 코호트). 바꿔 말하기는 의미 검색의 입구이자 재학습 재료라 지우지 않는다.
- 병은 회상에 있었다: 같은 코드를 접는 단계가 없어 300질의 실측 **Top-5 슬롯의 26%(393/1500)가 같은 코드**, 15질의는 다섯 칸 전부가 한 코드. → 모든 해마 검색이 지나는 한 자리 `ibl_usage_rag._search_active` 에 `_distinct_codes`(최고 점수 행이 코드를 대표). 빈 칸은 그 함수의 기존 넓히기 고리가 채운다. 재측정 낭비 0·5칸 미달 0. 소비자(표시·반사 top-1·이름 채널)는 반복을 신호로 쓰지 않음을 확인. 회귀 `backend/test_recall_distinct_codes_2026_09_18.py`.
- 진짜 중복 24행(balanced 18·manual_seed 6)은 실행 이력 있는 행·오래된 행을 남기고 삭제, training JSON 은 쌍당 한 행으로(balanced 1,892→1,873). ★09-17 `apply_verdicts.py` 는 (의도, 코드) 쌍을 JSON 에서 **전부** 지우므로 "한 행 남기기"에 쓰면 안 된다 — `manifest_exact_dups.json`.
- 부수: 진짜처럼 보이는 가짜 ID 71행(`trigger_001`·`lec_001`·`task_001`·`goal_001`) → `<트리거 ID>` 등, "근처"에 좌표 상수 1행 → `$위치`. `example.com` 은 공인 예시 도메인이라 무변경. 의도가 좌표를 직접 준 꼴("이 좌표", "— 36.5, 127.5")의 상수는 맞다.
- 최종: **3,635행** · 구문 오류 0 · 인자 경고 0 · 벡터 없는 행 23(이전부터). **실행기억 다듬기는 여기까지 — 재학습 가능 상태.**

**남긴 구멍 → 09-18 T3 로 닫음(§3-3 참조)**: "비소비자 B 가 입력 없이 이음매 뒤에 선다"를 실행 전에 잡는 규칙이 없다. 정적 규칙으로 올리려면 ①어느 비변환자가 앞 통화를 읽는지가 사전에 없다(지금은 핸들러 코드의 `_prev_result` 판독으로만 안다 — write·chart·document·brief·spreadsheet·copy·sheet·read·ask·delegate·os_open·publish·render 등) ②"필수 인자"도 사전에 없다(`target_key` 는 다수가 `op`). 둘을 `flow:` 선언으로 올리면 T3 규칙이 된다 — 언어 표면 변경이라 판정 대상. 그 전까지는 `seams.py` 가 코퍼스 쪽 관문(재학습 전 실행).

## 5. 이 세션의 교훈
- 재고를 읽고 입구를 처방하기 전에 **입구 코드의 최근 커밋부터** 볼 것(09-12 개편을 모르고 이미 고쳐진 것을 처방했다).
- "검사 통과 = 깨끗" 이 아니다. 검사기가 무엇을 *안 보는지*부터 확인(허용 키 범위·없는 op·비변환자 이음매·행동 변화).
- 눈으로 읽어야 잡히는 부류가 있다(A·C·H). 표본 200행에서 부류를 세우고 전수로 간 순서가 맞았다.
- backend 편집은 한 스크립트로 모아 한 번에(13파일 1회 재기동, FAILED 없음).
- 고친 코드도 실행해 봐야 한다 — 파서·타입·인자 검사를 다 통과한 교체분(`[sense:here] >> [sense:restaurant]{}`)이 실행에서 죽었다. 검사 통과는 "받아 준다"지 "돈다"가 아니다.
- `>>` 의 의존은 둘이다(통화·성공). 통화가 안 넘는다고 죽은 이음매가 아니다 — 가설을 세울 때 ibl.md 의 연산자 정의부터.
