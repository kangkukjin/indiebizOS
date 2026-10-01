# 상상훈련 18~25회차 회귀 재검 결과 (2026-09-29 22:17~22:25 KST, 읽기 전용)

백엔드: `/health` healthy, 재검 내내 응답. 모든 execute 는 `project_id:"컨텐츠", origin:"training"`
(action_health 에 `source=training` 으로 적재됨을 확인). 요청·응답 원본: `scratchpad/regress/tmp/r18/*.json`.
부작용 문장: workflow save(B22-1)는 validate와 오프라인 `call_signature()` 호출로만 검사함. F18-2·B21-1 의 write/copy 는 경로를 `tmp/r18/` 로 바꿔서 실행함.
notify/goal/since 기준선 기록은 실행하지 않음.

## 1. 회차별 요약

| 회차 | 재검한 표현 | 정상 | 문법변화(정상) | 여전히 오류 | 검수만/재검 불가 |
|---|---|---|---|---|---|
| 18 | 9 (F18-1·F18-2·V18-1·V18-2·B18-1·F18-3·T1·T2·F15-1) | 9 | 0 | 0 | 0 |
| 19 | 7 (B19-1 a~d·B19-2 a·b·F19-1) | 7 | 0 | 0 | 0 (F19-2 는 기록 항목) |
| 20 | 8 (F20-1·F20-1 재작성·F20-2 ×2·F20-3·B20-1 v/x·F20-4·T9) | 8 | 0 | 0 | 1 (F20-5 알림 제목 — notify 부작용) |
| 21 | 4 (B21-1 ×2·V21-2·F21-1·T7) | 3 | 1 (V21-1: render_html 은퇴) | 0 | 0 |
| 22 | 6 (B22-1·F22-1·F22-2·F22-3·F22-4·T12) | 6 | 0 | 0 | 0 (B22-1 save/run 은 검수와 오프라인 시그니처 계산으로만 확인) |
| 23 | 5 (B23-1 resume REST·F23-1·F23-2·U8·U12) | 4 | 1 (F23-1 교재 재편) | 0 | 0 |
| 24 | 5 (W1·W2·W3·W4·W7) | 5 | 0 | 0 | 0 |
| 25 | 5 (Y2·B25-1(b)·Y11/F25-1·Y9/F25-2·Y6) | 5 | 0 | 0 | 0 |

## 2. 여전히 오류

**없음.** 18~25회차 원장의 결함(B)·마찰(F)·어휘(V)는 모두 지금은 증상이 없거나, 정직하게 거절·신고된다.

## 참고 관찰 (오류로 수집하지 않음 — 판단 참고용)

- **O-1 (B20-1 관련)**: 유령 op `[self:finance]{op:"summary"}` 를 `/ibl/validate` 에 넣으면 최상위는 여전히 `valid: true` 다. 다만 같은 응답에
  `param_warning` 과 `typecheck.ok:false`(severity `error`, "선언된 op 가 아닙니다 … 사용 가능: delete·ingest·query·save·sync")가 함께 실리고,
  `/ibl/execute` 는 실행 전 통화 검사에서 거절한다. 원래 결함(검수가 조용히 통과시킴)은 해소됐다. `valid` 가 문법 판정만 뜻하는 설계로 보인다.
- **O-2 (20회차 T9)**: `[self:forage]{op:"recall"} & [sense:paper]{…} >> [table:union]{}` 는 예전엔 정직하게 거절됐는데 지금은 성공한다.
  recall 봉투 전체가 "효과 봉투라 1행씩 실었습니다" note 와 함께 **1행**으로 합쳐진다(recall 은 `returns: scalar` 인 읽기 액션인데 "부수효과 결과"로 불림).
  반면 순수 스칼라 가지(`[self:time]`)는 지금도 union 이 거절한다. 커밋 `84265b8d`(언어 개정) 이후의 설계로 보여 오류로 올리지 않는다.
- **O-3 (F23-1)**: 블록 문장(`[try]…[catch]`)의 최상위 `results` 는 여전히 검색 원문 배열이다(파이프의 step 요약 `results[]` 와 키가 같음).
  판별 규칙을 적은 교재 구절은 `5b9f0498`(IBL 주 교재 통일)에서 빠졌고, 판별은 지금 `backend/cognition/model_result_view.py` 가 맡는다. 블록 봉투에는 `_caught`·`_untransformed` 가 붙어 있다.

## 3. 문법 변화·수리로 정상 처리된 항목

- F18-1 columns 침묵 절단 → `ibl_envelope._clamp_names` 가 `columns_truncated/total` 을 신고함. compute 파생 열 `평당가만원` 정상 산출.
- F18-2 write 가 `_untransformed` 무시 → 저장 파일에 WorldPulse 0건, 봉투에 `excluded_untransformed: ["existing_schedules"]` 로 신고.
- V18-1 `[self:workflow]{op:"list"} >> take` → items 병기(`_mirrored:["workflows"]`) 로 통과.
- V18-2 self_check 원장 분리 → `[sense:self_check]{op:"results", source:"usage"}` 로 workflow 실패 근거에 닿음.
- B18-1 시험 실패가 usage 원장을 오염 → action_health 에 `source=test` 가 분리돼 있고, `_t_rec*` 의 usage 행은 0건.
- F18-3 prompt_hidden 이 미조합 메뉴에 섞임 → `vocab_composition_metrics.py` 가 `self_can_run` 정본으로 제외함.
- B19-1 문자열 where 의 `matches`/`contains` 침묵 0건 → 둘 다 '자이' 단지를 정상으로 거름(96행). 모르는 op(`foobar`)는 지원 목록과 함께 정직하게 거절.
- B19-2 `[table:reduce]{items:"$r.items"}`·`[table:brief]{items:"$r.items"}` 거절 → 둘 다 통과(842건 / 단지명 3개).
- F19-1 case 매칭 미신고 → `matched:"0~50", matched_value:30.4`.
- F20-1 realty 열 source 구분 → 카탈로그 ⟨열 | source=naver⟩ 병기 코드(`ibl_access.py`)와 `shape_variants` 가 있음. 옛 열 이름은 사용 가능 필드 목록과 함께 정직하게 거절되고,
  `deposit_won`/`area_m2` 로 고쳐 쓰면 통과함(`deal:"rent", lease:"전세"`).
- F20-2 `sense:host{op:"status"}.disk_percent` 조건 좌변 해소 실패 → `matched_value: 5.2` 로 해소됨.
- F20-3 since 첫 검침 0행 >> brief 오류 → brief 가 "입력 0행 — AI 호출 생략" 으로 성공. 최상위 warning 이 peek 0행 사유를 신고함.
- B20-1 유령 op summary → execute 는 실행 전 거절, validate 는 param_warning 과 typecheck error 를 냄(O-1 참고).
  코퍼스 finance 용례는 `op:"query", query_type:"summary"` 뿐.
- F20-4 거절 문구에 sync 누락 → 지금 문구의 사용 가능 목록에 sync 포함.
- B21-1 핸들러 오류 문자열이 성공 봉투에 실림 → `render_html` 은 은퇴했음. 같은 부류로 `[self:time] >> [self:copy]{src:…}`(dest 누락)를 돌리니 `success:false`·`error_type: tool_error`·resume 발급.
- V21-1 `[engines:render_html]` 통화 미소비 → 액션 은퇴("노드 'engines'에 'render_html' 액션이 없습니다"). 후속 어휘는 `[engines:render]`(파일 투영). **문법 변화**로 분류.
- V21-2 `[self:cctv]{op:"stats"} >> take` → items 병기(`_mirrored:["sources"]`), 2행.
- F21-1 가이드 curl 에 project_id 없음 → `data/guides/imagination_training.md:85-90` 에 반영됨.
- B22-1 `$return = $r` 가 인자로 오인 → `workflow_contract.call_signature()` 결과: `$r/$return`→[], while `$n`→[], repeat `$i`→[], `$topic`→['topic']. save 는 validate 만 함(valid).
- F22-1 groupby shape effect → items 동봉. F22-2 groupby 가 상류 total 을 승계 → `total:14`(자기 행수)이고 상류 절단은 `truncations` 로 따로 신고.
- F22-3 since peek 함정 → 어휘 설명에 "peek(true=기준선 안 올리고 미리보기)"가 있고, 실행 시 warning 이 "peek — 기준선 저장 안 함" 을 신고.
- F22-4 spill 문서 → write 설명이 투명 해소 쪽으로 정정됨. 실행 step note 도 "변환자·each·$items·write 는 투명하게 읽음" 으로 나옴.
- B23-1 REST 가 resume 을 침묵 무시 → 1단이 죽는 URL + resume 으로 `success:true, steps 2/2, resumed_from:2`.
- F23-1 블록 results 키 충돌(교재) → 교재가 재편되며 해당 구절이 빠짐. **문법 변화/교재 재편**으로 분류(O-3).
- F23-2 halted 가 최상위에서 안 보임 → `halted_steps:[{step:2, halted:"max", iterations:3}]` 과 warning 이 최상위에 실림.
- B24-1 병렬 실패 미신고 → W1 `branches_failed` 와 부분 warning / W2 `success:false`("병렬 전 가지 실패 2/2") / W3 merge 후 최상위 `branches_failed` 와 warning.
- F24-1 괄호 분기 실패 시 2차 증상만 보임 → W4 는 지금 `branches_failed` 와 `branches_skipped` 표지를 달고 부분 성공으로 끝남.
- B25-1 소스참조 `.items.0.max_temp` 판정 불능 → if 는 `matched_value 25.0`, case 는 `matched "20~30"`.
- F25-1 교재의 유령 `page` → 교재·가이드에서 `page: "$i"` 0건. Y11 원문은 `param_warning`(미인식 page, 비슷한 키 page_size)으로 정직하게 신고됨.
- F25-2 `_raw` 교재 문장 → 교재·가이드에서 `_raw` 문단 0건. `_raw:true` 를 붙인 문장도 정상 실행됨.
- 기타 실행 확인(성공 문장 무회귀): 18T1 평당가 정렬 · 18T2 `$합.value` 비중 compute(0.14/0.11/0.31) · 21T7 거래금액(쉼표 문자열) reduce · 22T12 case disk_percent · 23 U8 폴백 · U12 판정 불능 시 else 보류 · 25Y6 블록-인-파이프.

## 4. 재검 못 한 항목과 이유

- F20-5 `[self:notify_user]{message:}` 만 줄 때 알림 제목이 빈칸 — 알림 발송은 부작용이라 실행 안 함(22회차 보고서가 이미 정상 제목 관찰을 적어 둠).
- B22-1 저장 후 run 왕복 — workflow 등록은 부작용이라 save 는 validate 만 함. 시그니처는 라이브 코드의 `call_signature()` 를 읽기 전용 import 로 계산함.
- 24회차 W9(show_map)·W12(goal 등록)·21회차 T5/T11·18회차 T8/T13 — 원래도 오류가 없었고 부작용 문장이라 제외.
- since 기준선을 기록하는 문장(25회차 Y12 등) — since DB 쓰기를 피하려고 peek 형태로만 확인함.
