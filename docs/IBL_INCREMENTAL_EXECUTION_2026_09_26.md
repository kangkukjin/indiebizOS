# IBL 증분 실행 — 파이썬에서는 되는데 IBL에서는 안 되던 셋 (2026-09-26)

상태: 적용·시험 통과. 교재(ibl_composition.md) 6단계·상시 프롬프트·정본 ibl.md·MCP 표면 갱신.
계기: [작업 분해 설계](IBL_TASK_DECOMPOSITION_DESIGN_2026_09_26.md)가 "도구 반환이나 맥락 전달의 한계가 실제로 확인되면
계약을 개선한다"고 미뤄 둔 그 확인이 에피소드 4078(read_result 본문 219,441자, 관용구가 대상 4개 중 3개만 읽음)이었다.
교재를 고치기 전에 실행기가 먼저 그 일을 할 수 있어야 교재가 정직해진다는 판정(사용자, 09-26).

## 1. 무엇이 안 됐나 — 파이썬 개발 루프와의 대조

| 파이썬에서 되는 것 | IBL 실물(09-26 이전) | 뿌리 |
| --- | --- | --- |
| REPL 이 수집 결과를 변수에 들고, 정규화 함수만 고쳐 다시 부른다 | 함수 하나를 고치면 프로그램 전체가 새 실행 — 부작용 있는 수집까지 재실행 | 영수증 요청 지문에 프로그램 지문이 섞임(`ibl_v2_runtime.invoke` request.plan), 재개는 소스·입력 완전 일치만 |
| 이전 결과를 값으로 넘긴다(변수·pickle) | inputs 는 리터럴만 — 모델이 본문을 복사하거나 파일로 읽어 재파싱 | `ibl_v2_entry` inputs 가 참조를 모름. 결과 참조는 읽는 쪽(read_result)에만 |
| 타입 스텁이 없는 필드 접근을 잡는다 | 판본 2 검사기는 통화 종류만 알고 항목 필드는 모름 → `select` 필드 추측이 `incomplete` 로 통과 | 관측 열(`data/ibl_return_shapes.json`)과 경고 규칙이 옛 검사기(판본 1)에만 있고 09-23 이행 때 새 컴파일러가 이어받지 않음 |

이미 파이썬 수준이라 손대지 않은 것: 트레이스백(경계 프레임·원형 오류·입력 요약), `check:true` 의 location/call_path,
감독자 수리 상한(`max_repairs`=1), 단언(분기·return 으로 표현). 일부러 안 고친 것: Jupyter 식 세션 변수 — 명시 입력 원칙으로
배제된 것이며 아래 ①②가 숨은 상태 없이 같은 효용을 준다.

## 2. 집행 — 어휘·op·문법 증가 0, 실행 의미 개정 3

### ① `reuse:{run_id}` — 고친 프로그램의 영수증 재사용
- 재사용 키 = digest{action, args, 도구 구현 지문}. **프로그램 지문 없음.** 영수증에 `action`·`reuse_key` 를 함께 적는다(옛 영수증은 후보 아님).
- 후보 = 이 문맥(주체·프로젝트 저널 루트)의 지난 실행이 남긴 **성공** 영수증(`ibl_run_journal.reusable_receipts`). 진행 중(잠금)이면 `REUSE_BUSY`, 없으면 `REUSE_NOT_FOUND`.
- 실행기는 `effects == ["read_external"]` 인 호출에서만 꺼내 쓴다. 쓰기·모델·미상 효과·바뀐 인자는 실행. 권한 확인(`authorize`)은 재사용에도 걸린다.
- 재사용한 호출은 **새 실행의 저널에도 완결 영수증**으로 남는다 — 그 실행을 다시 resume/reuse 할 수 있다(사슬).
- 증거: `receipt_reused{source: reuse|journal|replay, run_id}` 사건, 봉투 `reuse:{run_id, reused_calls, candidates}`.
- `resume` 과 함께 쓰면 `REUSE_ARGUMENT`. 같은 프로그램=resume, 고친 프로그램=reuse.
- 표면: execute_ibl 스키마(tool_loader)·HTTP(api_ibl.IBLRequest)·MCP(mcp_server, 루트라 다음 MCP 기동에 반영)·회원 화이트리스트(member_runner).

### ② inputs 값 자리의 `{"$ref": result_ref.id, "path": [...]}`
- 인지 층(`model_result_view.resolve_input_refs`)이 실행 전에 푼다 — 증거 저장소는 턴 문맥의 것이라 실행기(ibl 층)에 두지 않는다. `system_tools_ibl` 가 판본 2 진입 직전에 호출.
- path 생략 = 판본 2 `value_wire`(손실 없는 값) → 옛 봉투 `final_result` → 본문 전체. 경로 규칙은 read_result 와 같은 `_walk` 한 벌.
- 전송 절단 봉투의 스필 참조(`{"ref": {"path"}, "_spilled": true}`)도 푼다.
- 봉투에 `inputs_resolved[{name, id, path, chars}]`, 궤적 사건 `context.input_ref_resolved`. 실패는 실행 전 거절 봉투.
- 여전히 **명시 입력**이다 — 이름·출처를 적은 것만 들어온다. 이전 턴 변수의 자동 주입이 아니다.

### ③ 관측 반환 필드 → 판본 2 컴파일러 경고 `UNOBSERVED_FIELD`
- 해소 규칙을 `ibl_typecheck.catalog_entry` 한 벌로 뽑아(node:action · #op · @param=값 · columns_from · fixture op · default op, `more` 기권) 판본 1 `_catalog_cols` 와 판본 2 `ibl_v2_adapters.observed_result` 가 같이 쓴다.
- 타입: `Type(observed=True)` 인 **열린** Record. ⟨열⟩(items)은 봉투 `items` 원소/List 원소에, ⟨키⟩(scalar)는 봉투 최상위에. `legacy-envelope` 어댑터에만 — 표 변환자의 열은 입력이 정한다.
- 관측 밖 접근 = `compiler.warn` → `preflight.warnings`(check 보고서 `warnings`, 실행 봉투 `precheck_warnings`). 오류 아님, 상태 불변. `has/get` 은 경고 없음.
- 관측은 계약 지문에 들어가지 않는다 — 스윕 갱신이 진행 중 실행의 재개 지문을 바꾸지 않는다.
- `describe` 응답에 `observed_returns`(액션·#op·@변이 전부) — 카탈로그 줄이 아니라 조회 응답에만(상시 토큰 예산).

## 3. 검증
- 새 시험 `backend/test_ibl_v2_incremental_2026_09_26.py`: 고친 프로그램의 읽기 재사용·쓰기/바뀐 인자 재실행·저널 사슬(resume)·구현 지문 불일치·실패 영수증 제외·BUSY/NOT_FOUND/ARGUMENT·inputs 참조(value_wire/final_result/path/스필/오류)·관측 경고(items·scalar·more 기권·has/get·실행 봉투)·catalog_entry 규칙.
- 기존: test_ibl_v2_core·run_lifecycle·historical_replay·current_surfaces·callable_contracts·container_calls·migration_completion·client_agent_contract·composition_teaching·ibl_typecheck·imagination_round55·param_shapes·v2_assets 통과.

## 4. 남은 것 (설계 문서와의 연결)
- 교재 확장은 이제 정직하게 쓸 수 있다: 스파이크(작은 입력 실행) → 함수 하나 수리 → `reuse` 로 재실행 → 최종 프로그램. 용례는 해마에 심고 회상 통로를 지정한다(`data/guides/new_action_checklist.md`).
- 관측 데이터의 신선도는 기존 `ibl_shape_sweep.py`(fixture·`--from-health`) 카덴스 그대로. 영수증에 `action` 이 남으므로 저널 기반 관측 스윕도 가능하나 지금은 만들지 않는다.
- 재사용을 `model` 효과까지 넓힐지는 판정 사항 — 비결정 호출을 되돌려 쓰는 것이라 기본은 아니다.
