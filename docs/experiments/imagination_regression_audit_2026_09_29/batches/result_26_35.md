# 상상훈련 26~35회차 회귀 재검 결과 (2026-09-29, 읽기 전용)

- 백엔드: `/health` healthy, restart_control phase=ACTIVE (시작·종료 모두). 저장소 파일 편집 0.
- 실행: `/ibl/validate` + `/ibl/execute` (body `project_id:"컨텐츠"`, `origin:"training"`). 헤더 없는 HTTP 호출 = 구 판본(legacy) 의미. 의심 항목은 `#!ibl edition=2` 헤더(현재 문법)로 다시 돌려 대조함.
- 파일 쓰기가 필요한 문장(write/chart/document)은 경로를 `scratchpad/regress/tmp/` 로 바꿈.
- 주의(정직 고지): R33-B33-2 재검 중 `[self:workflow]{op:"run", do:"$n = $n + 1"}` 를 1회 실행함(validate 에서 safety=write 로 표시됨). 즉석 do 실행이고 step 1 에서 실패했으며 등록 op 는 아님. 그 뒤로 workflow 문장은 validate 만 함.

## 1. 회차별 요약

| 회차 | 재검 | 정상 | 문법변화(정상) | 여전히 오류 | 검수만(부작용) | 비고 |
|---|---|---|---|---|---|---|
| 26 | 7 | 4 | 1 | 0 | 2 | B26-3 output gui, F26-2 nostr 는 검수만 |
| 27 | 6 | 6 | 0 | 0 | 0 | |
| 28 | 3 | 2 | 1 | 0 | 0 | |
| 29 | 7 | 4 | 0 | **1** | 2 | B29-1① 회귀 |
| 30 | 5 | 2 | 2 | 0 | 0 | B30-3 은 재검 못 함. B30-1 은 구 판본 HTTP 경로에 잔여 결함 있음(§3 참조) |
| 31 | 4 | 3 | 0 | 0 | 1 | G31-1 판정 집행(치환+경고) 확인 |
| 32 | 3 | 3 | 0 | 0 | 0 | G32-1 은 여전히 정직 거절(판정 대기) |
| 33 | 6 | 5 | 0 | **1** | 0 | B33-2 판단 불가 |
| 34 | 2 | 2 | 0 | 0 | 0 | B34-1(핸드오프 기재분) |
| 35 | 10 | 10 | 0 | 0 | 0 | B35-1/B35-2 는 `ab831882` 로 처리됨. 관찰 2건 |

## 2. 여전히 오류

### R29-B29-1a — 29회차 B29-1①: 1열 통화 → `[table:chart]` 가 **거짓 성공**(빈 차트)
- 원래 증상: 1열 통화가 오면 chart 가 "데이터가 비어있습니다. data 또는 data_file을 제공하세요"라는 엉뚱한 문구로 실패. 29회차에 "입력 N행이 왔지만 값 열이 없습니다 — 최소 2열이 필요" 라는 정직한 거절로 고쳤음.
- 이번 문장(원문. 경로만 tmp 로 바꿈):
```
[sense:realty]{source: "molit", region: "죽백동", type: "apt", deal: "trade"} >> [table:take]{n: 3} >> [table:reduce]{init: 0, step: "acc + price", as: "총거래액"} >> [table:chart]{chart_type: "bar", path: ".../regress/tmp/c1.png"}
```
  대조 문장(외부 원천 무관):
```
[sense:weather]{city: "수원"} >> [table:select]{columns: ["max_temp"]} >> [table:chart]{chart_type: "bar", path: ".../regress/tmp/c3.png"}
#!ibl edition=2
$w = [sense:weather]{city: "수원"}
$w.items >> [table:select]{columns: ["max_temp"]} >> [table:chart]{chart_type: "bar", path: ".../regress/tmp/c4.png"}
```
- validate: valid, 경고 없음.
- execute: `success: true`, `"막대 차트 생성 완료 (1개 항목, 1개 시리즈)"` / `"(3개 항목, 1개 시리즈)"`. 실제 PNG(c1·c3·c4)를 열어 보면 **막대가 하나도 없는 빈 축**뿐임(x축=값, y축 -1~4). 두 판본 모두 같음.
- 분류: **원 결함 재현(회귀, 증상은 더 나빠짐)**. 29회차 전에는 틀린 문구로라도 실패했는데, 지금은 거짓 성공을 냄.
- 비고(뿌리 추정, 읽기만 함): `data/packages/installed/tools/visualization/handler.py` `_table_to_chart_data()` 에서 bar 이고 `len(cols)==2` 일 때만 라벨/값 갈래로 감. 1열이면 else(line/scatter) 갈래로 떨어져 `vcols=["y"]` 가짜 시리즈를 만들고, data 가 비어 있지 않게 돼서 `_diagnose_no_data()`(139행의 "값 열이 없습니다" 거절)까지 도달하지 못하는 것으로 보임. 0행 경우는 여전히 정상 거절함.

### R33-B33-2 — 33회차 B33-2: `do:` 안의 `$n = $n + 1`(판단 불가)
- 원래 증상: 바깥에 `$n` 이 있으면 파서가 do 문자열의 할당 좌변까지 치환해서 `0 = 0 + 1` 파싱 실패. 보고서는 "바깥에 `$n` 이 없으면 멀쩡히 돈다"고 적었음.
- 이번 문장:
```
$n = 0
[self:webapp]{op: "list"} >> [table:take]{n: 2} >> [table:each]{do: "$n = $n + 1"}
```
  (바깥 `$n` 없는 판, `[self:workflow]{op:"run", do:"$n = $n + 1"}` 판도 같이 돌림)
- validate: valid.
- execute: `each: 2건 전부 실패 — 첫 오류: Step 1 에러: $n = $n + 1: 식 오류 변수 $n 이(가) 앞에서 할당되지 않았습니다.` 바깥 `$n` 이 있든 없든, each 든 workflow run 이든 같음.
- 분류: **판단 불가.** 원래 결함(좌변 치환 → 파싱 붕괴)은 사라졌고 지금 거절은 정직함. 다만 "바깥 `$n` 없으면 돈다"는 보고서 서술은 더 이상 맞지 않음. do 안에서 바깥 변수를 누적하는 패턴은 어느 경우에도 표현이 안 됨. 바깥 변수 읽기 자체는 됨(`$q` 를 do 안 `'$q'` 로 쓰면 정상). 이게 each 스코프 설계인지 결함인지는 사용자 판단이 필요함. repeat 몸 안의 `$n = $n + 1` 은 정상(최종 `$n`=3).

## 3. 문법 변화로 정상 처리된 항목

- V26-1 `[self:folder_note]{op:"get"} >> [table:take]` → op 가 `detail` 로 개명됨. `{op:"detail"}` 은 이제 `items` 통화를 내고 take 가 정상 동작함(옛 `get` 은 typecheck 가 "사용 가능: detail, set" 으로 정직하게 거절).
- F28-1 `each{do:[self:grep]} >> [table:flatten]{field:"_result"}` → each 가 이제 do 통화를 직접 흘려서 `_result` 감싸기가 은퇴함. flatten 이 "이미 평탄합니다 — flatten 없이 바로 이으세요"라고 정확히 안내함. flatten 을 빼면 정상.
- B30-1 `[try]{[A] & [B]}[catch]{[C]}` → 현재 문법(`#!ibl edition=2`)에서는 병렬 가지 하나가 실패하면 catch 가 실행되고 값이 정상으로 옴. 전 가지가 실패한 경우는 구 판본에서도 `_caught` 로 정상.
  ★**구 판본 잔여 결함(수집은 하지 않았지만 기록함)**: 헤더 없는 HTTP(저장 프로그램·스케줄이 쓰는 경로)에서 `[try]{[sense:stock]{op:"quote",ticker:"ZZZZINVALID"} & [sense:weather]{city:"수원"}}[catch]{…}` 를 돌리면 봉투가 `{"result": "[{'success': False, ...}, '{...json...}']"}` 로 옴. 이건 **파이썬 repr 문자열**이라 `json.loads` 가 실패함. `success`·`branches_failed`·`warning` 도 없음. 같은 병렬을 최상위에서 돌리면 `branches_failed`+`warning` 이 붙음. 즉 블록 경계에서 부분 실패 표지가 사라지고 있음(B27-4 계열). 전 가지가 성공해도 같은 repr 모양임.
- G30-1 `[A] & [B] ?? [C]` → 구 판본은 여전히 검수에서 "섞을 수 없습니다"로 정직하게 거절함. 현재 문법은 우선순위(괄호 > & > >> > ??)를 정의해서 실행되고 폴백도 정상.
- F27-1 (문장 자리 블록 결과가 `{result:"<JSON 문자열>"}` 로 싸이는 것) → 구 판본에는 그대로 남아 있음(보고서 판정도 "마찰·고치지 않음"). 현재 문법은 `value` 봉투를 줌.

## 4. 정상 확인 항목(간략)

B26-1(take/filter/dedup 뒤 truncated 참, sort 무변) · B26-2(groupby 후 summary 제거) · B27-1(select 봉투 items) · B27-2(spill 참조 → groupby 정상) · B27-3(each 안 `$it.영역 matches '…'` 조건 판정, ok 3/3) · B27-4(repeat+on_error 에서 `skipped_steps`+note) · F27-2(validate 가 미인식 param 경고) · B28-1(0행에서 rename/sort/select/groupby/dedup/compute/flatten 전부 성공 0행) · B29-1 0행 chart·document(정직 거절 + rows_in) · F29-1/J29-1(chart·document 가 준 path 를 지킴) · B30-2(블록 4회 실패 뒤에도 다른 블록 문장 정상) · B31-1(`$items.title`→ticker 정직 거절 + 집합 참조 안내) · B31-2/G31-1(문장 속 `$items` → JSON 치환 + `list_in_text` 경고) · F31-1(미인식 키 + 선언 키 안내) · B32-1(`rows_replaced` 신고) · G32-1(do 첫 자리 변환자 → 실행 전 정직 거절, 판정 대기 그대로) · B33-1(case count/empty($items) 정상) · F33-1(collect 없는 repeat >> take 정직 거절) · G33-1(`>> [on_error:]` 검수 거절 + 사유) · B34-1(ticker/city 에 목록 → 정직 거절) · F35-1(`?? [self:time]` 평문 스칼라에도 최상위 `_fallback_used`+warning) · B35-1(`ticker: 005930` 앞자리 0 보존 → 005930.KS, `city: 123` → "123" 무손실 변환, 핸드오프 1157행 판정대로) · B35-2(`n: 3.7`·`headlines:"yes"` 정직 거절, 병렬 가지에서는 branches_failed) · V4/V7 정직 거절.

관찰(수집 안 함):
- 35회차 `[sense:weather]{city: 123}`(=`city:"123"`) → 성공이지만 `resolved: "123, 라말라, … 요르단강 서안 지구"` 로 지오코딩됨. 타입 관문은 정상이고 `resolved` 필드로 드러나긴 하지만, 의미 없는 도시명을 조용히 해외 지명으로 해석함.
- 35회차 V8 `[sense:world_bank]{country:"KR"}`(required `indicator` 누락) → validate 는 통과, execute 는 "지표 'None'(국가: KR)에 대한 데이터를 찾을 수 없습니다". 거절은 되지만 누락된 required 이름을 대지 않고 `None` 이 샘. 원 보고서도 "정직거절"로 분류했으므로 회귀는 아님.
- 30회차 F30-1: 주 교재 `12_ibl_only.md`(edition 2 로 재작성, `5b9f0498`)에는 정직 표지 이름(`_fallback_used`·`rows_in`·`ok_count` 등)이 0회 나옴. 표지 교육은 `docs/compatibility/ibl_legacy_language.md` 로 옮겨졌고 `test_R7` 도 그 파일을 봄. 몸은 표지를 실제로 싣는 것을 확인함.
- 26회차 F26-1 `self:body` 단독 봉투에 `count` 가 없는 것은 여전함(보고서 "고치지 않음" 그대로).

## 5. 재검 못 한 항목

- B26-3 `[self:output]{op:"gui"}` — UI 출력 부작용이라 validate·check 만 함(ok). `_sink_content` 계약은 코드에 있음(`backend/ibl/ibl_exec_output.py:15,59,190`).
- F26-2 `others:nostr` — others:* 외부 노드라 실행하지 않음.
- B29-3 병렬 타임아웃(`table:ai` + 90초) — AI 호출 비용과 90초 대기 때문에 validate 만 함(valid).
- 29회차 `[table:since]` empty_notes — `table_since.db` 에 기준선을 쓰는 문장이라 실행하지 않음(다른 0행 파이프에서 `empty_notes` 키가 승격되는 것은 확인).
- B30-3 리허설/실사용 차단기 키 분리 — 실사용(origin≠training) 실패를 만들어야 해서 건강 원장을 오염시키므로 하지 않음.
- F31-2 `[limbs:show_map]` — limbs 출력이라 validate 만 함(valid).
- F32-1·F33-1 교재 문구 — 주 교재가 edition 2 로 전면 재작성돼서 옛 줄 단위 대조가 의미 없음.
- 35회차 P6(`[self:workflow]{op:"run"}`) 여섯 칸 — 위 고지 1회 외에는 실행하지 않음.
