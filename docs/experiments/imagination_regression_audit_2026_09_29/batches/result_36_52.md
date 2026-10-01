# 회귀 재검 — 상상훈련 36~52회차 (2026-09-29, 읽기 전용)

백엔드: `/health` healthy. 저장소 파일 편집 없음. 쓰기 문장은 전부 경로를 `scratchpad/regress/tmp/r36/it49/` 로 돌려 실행(문서·xlsx·json). 외부 발신·등록 없음.
드라이버·원자료: `scratchpad/regress/tmp/r36/` (batch.py·fin.py·p48.py·p49.py, p48_out.json·p49_out.json).

## 1. 회차별 요약 (재검 표현 수 / 정상 / 문법변화(정상) / 여전히 오류 / 검수만)

| 회차 | 재검 | 정상 | 문법변화 | 여전히 오류 | 검수만 | 비고 |
|---|---|---|---|---|---|---|
| 36 | 4 (B36-1·B36-2·F36-1·F36-2 최소 재현) | 4 | 0 | 0 | 0 | F36-1: filter 가 이제 inline items 수용(거절 자체 소멸). F36-2: `$return = []` 이제 통과 |
| 37 | 3 (`>`·`>=`·`!=` 결측) | 3 | 0 | 0 | 0 | G37-1 판정(결측은 ne 에서도 제외) 반영됨 |
| 38 | 5 (0 vs "0" join/dedup, null 키 직접/변수, 빈 문자열 키) | 5 | 0 | 0 | 0 | |
| 39 | 3 (avg 결측, count(field), 무관측 sum) | 3 | 0 | 0 | 0 | avg=10+aggregation_skips, count=1, sum=null |
| 40 | 2 (bool/0 그룹, list 그룹 키) | 2 | 0 | 0 | 0 | |
| 41 | 1 (사전 순서 join) | 1 | 0 | 0 | 0 | |
| 42 | 1 (사전 순서 eq) | 1 | 0 | 0 | 0 | |
| 43 | 2 (백분율 filter·sort) | 2 | 0 | 0 | 0 | |
| 44 (보고서 없음, 핸드오프 §7) | 4 (2^53 filter·sort, nan 집계·le) | 4 | 0 | 0 | 0 | `"nan"` le 5 → 정직 거절(판정 불능=오류, 45회차 계약) |
| 45 (보고서 없음) | 3 (혼합 타입 gt, 공백 날짜 sort·filter) | 3 | 0 | 0 | 0 | 혼합 타입은 필터 전체 정직 거절 |
| 46 | 9 (startswith casefold, NFD eq·contains, null contains, list repr, list 멤버십, in bool, join "1,000"/1000, dedup 1/1.0/"02"/2) | 9 | 0 | 0 | 0 | B46-6(api_transforms 응답 필터)은 IBL 문장으로 직접 겨냥 못 함 — §4 |
| 47 | 3 (researcher select·coauthor dedup, flatten 뒤 each) | 3 | 0 | 0 | 0 | flatten 설명·오류문 모두 교정 확인 |
| 48 | 46 칸 전수(_probe48 코드) + F48-6 보강 2 | 44 | 3 (교재 드리프트 F48-3/4/5) | **1** (F48-6) | 0 | B48-1(`_caught`)·B48-2(`branches_honesty`)·F48-7(B2 passthrough 최상위·H2 truncated 최상위) 수리 확인 |
| 49 | 48 칸 전수(_probe49, /tmp/it49 → scratchpad) + 최소 재현 3 | 51 | 0 | 0 | 0 | 실패 칸(M1/M3/M4.C8, M4.C1/C2/C5/C6/C7)은 원 보고서가 '내 셀 오류·정직 거절'로 분류한 것 그대로 정직 거절. M5 6칸·M3.C5·M2.C8(validate) 는 이제 통과 |
| 50 (보고서 없음) | 5 (B50-1 page1/2, B50-2 if·try 스칼라, 안 탄 분기) + 파생 2 | 5 | 0 | **1** (새 형태 — 사전검사 거짓 경고) | 0 | |
| 51 (보고서 없음) | 6 (B51-1 brief·document·spreadsheet, B51-2 0행, B51-3 덮어쓰기 신고, B51-4 brief rows_in) | 6 | 0 | 0 | 0 | brief 는 현재 instruction 필수 — 붙여서 재실행 |
| 52 (보고서 없음) | 5 (B52 blocks `$변수` 주입 2형, 판정후보 ①`$변수 >>` 머리 ②고전 변환자 리터럴 ③compute split) + 파생 3 | 5 | 0 | **1** (새 형태 — document 블록 침묵 누락) | 0 | ①②③ 모두 이제 동작 |

## 2. 여전히 오류

### R48-F6 — `[table:chart]` 가 쓸 수 없는 입력을 받았을 때 오류문이 원인을 틀리게 말하고 `rows_in` 이 없음
- 원 회차: 48회차 F48-6 (`rows_in` 이 emitter 실패 경로에서 조건부로만 붙음 + chart 문구가 "사용자가 data 를 안 줌"으로 오도). 49회차 후속이 "census 결과 chart 는 이미 고쳐져 있었다"며 닫았으나, 실측으로는 재현.
- 실행 문장 1 (원 G2 칸):
```
[self:time] >> [table:chart]{chart_type: "line"}
```
- validate: `valid:true`. execute: `success:false`, `"Step 2 에러: 데이터가 비어있습니다. data 또는 data_file을 제공하세요."` — `rows_in` 없음(traceback `input.shape:"text"` 만 단서).
- 실행 문장 2 (0행 대조, 경로는 scratchpad):
```
[sense:host]{op: "apps", limit: 3} >> [table:filter]{where: "pid == -999"} >> [table:chart]{chart_type: "bar", x: "name", y: "cpu_percent", path: "<scratch>/c0.png"}
```
- execute: `"차트 x/y 열을 입력 행에서 찾을 수 없습니다: ['name', 'cpu_percent']"` — 열은 있고 행이 0인 것인데 열 부재로 말함. 형제 emitter 는 같은 사건에 `rows_in: 0` + "입력 0행 — …"(document·spreadsheet 실측 확인).
- 분류: 원 결함 재현 (정직 문구·형제 불일치). 실패 자체는 나므로 거짓 성공은 아님.
- 비고: 48회차 "미집행·잔여" → 49회차 후속에서 "수리됨(chart 는 이미 고쳐져 있었다)"로 닫힘 — 닫힘 판정이 틀렸을 가능성.

### R50-N1 — 사전검사(precheck)가 모든 분기에서 할당된 변수를 "분기 몸 안에서만 태어난 변수"로 거짓 경고
- 원 회차: 50회차 B50-2 / 49회차 V49-1(블록 몸 할당 되쓰기) 파생 확인 중 발견.
- 실행 문장:
```
[if: 1 == 1]{$k = 1}[else]{$k = 2}
[table:take]{items: [{v: "$k"}], n: 1}
```
```
[try]{$k = [self:time]} [catch]{$k = "x"}
[table:take]{items: [{v: "$k"}], n: 1}
```
- validate: `valid:true`. execute: `success:true`(값 정상 전달) + `precheck_warnings: "$k 은(는) 분기 몸 안에서만 태어난 변수입니다 — 그 분기에 들어가지 않으면 값이 없어 실행에서 '아직 값을 기록하지 않았습니다' 로 죽습니다."`
- if/else 양쪽, try/catch 양쪽이 모두 할당하므로 "들어가지 않는 분기"가 없다 → 경고가 거짓. (한쪽만 할당하는 `[if: 1 == 2]{$z = 7}` 은 실제로 실행에서 미할당 거절 — 그 경우 경고는 옳다.)
- 분류: 새 형태의 오류 (경미 — 거짓 경보. 실행 결과는 옳음).

### R52-N1 — `[table:document]` 가 렌더할 수 없는 블록을 조용히 버리고 "N블록을 렌더했습니다" 성공
- 원 회차: 52회차 B52(blocks 구조 필드 `$변수` 주입) 재검 중 발견. B52 자체(`columns: "$cols"` 문자열 되읽기)는 정상.
- 실행 문장(경로는 scratchpad):
```
[table:document]{format: "markdown", title: "N1", path: "<scratch>/n1.md", blocks: [{type: "table", items: [{a: 1, b: 2}]}]}
[table:document]{format: "markdown", title: "N2", path: "<scratch>/n2.md", blocks: [{type: "table"}]}
[table:document]{format: "markdown", title: "N3", path: "<scratch>/n3.md", blocks: [{type: "cards", items: [{이름: "A", 가격: 100}]}]}
$표 = [table:take]{items: [{이름: "A", 가격: 100}], n: 1}
[table:document]{format: "markdown", title: "P31b", path: "<scratch>/b52b.md", blocks: [{type: "table", items: "$표.items"}]}
```
- validate: 전부 `valid:true`, param_warning 없음. execute: 전부 `success:true`, `"문서 1블록을 마크다운으로 렌더했습니다."` — 실제 markdown 은 `# N1\n`(표 없음) / `# N2\n` / `# N3\n\n-\n`(빈 카드) / `# P31b\n`.
- table 블록 계약은 `columns`/`rows` 라 `items` 는 모델 쪽 오용이지만, 내용이 통째로 사라지는데 성공·블록 수 신고로 끝나는 침묵 누락이다(cards 는 title/url 없는 행을 "-" 로).
- 분류: 새 형태의 오류 (침묵 성공/내용 소실).

## 3. 문법 변화로 정상 처리된 항목
- F48-3 (교재가 `branches_failed`·`empty_notes`·`statements_failed` 를 안 가르침) — `12_ibl_only.md` 가 판본 교체로 전면 재작성되어 옛 "정직 표지를 읽어라" 절 자체가 없음(해당 키 0회 언급). 구 교재 기준 갭이라 재검 대상 소멸. 몸 쪽 표지는 여전히 봉투에 실림(B7 `branches_honesty`+warning 확인).
- F48-4 (`[repeat: N]{…} >> 변환자` 가 "거절된다"는 교재 문구) — 교재 문구 소멸, 동작은 items(마지막 회차)로 통과(49회차 후속이 구현을 정본으로 판정).
- F48-5 (`_ok` 필터 "0건" 문구) — 교재 문구 소멸, 실행은 `'_ok' 필드가 어느 행에도 없습니다` 명시 거절(더 정직한 쪽).
- (문법 변화 아님, 참고) F36-1: `[table:filter]{items:[…]}` 는 이제 직접 수용되어 validate·execute 가 일치.

## 4. 재검 못 한 항목·한계
- B46-6 (api_transforms 응답 필터 `contains`·TypeError 누출): 응답 필터 표면은 패키지 선언 `response` 변환 경로라 IBL 한 문장으로 입력값을 고정해 겨냥할 수 없음 — 같은 한 벌(`text_match`)을 쓰는 where 표면(B46-1/3/4/5)은 정상 확인.
- 48회차 원 드라이버(_probe48.py)·49회차(_probe49.py) 자체는 결과 json 을 저장소에 덮어쓰므로 실행하지 않고, 결과 json 의 `code` 를 읽어 동일 문장을 별도 드라이버로 재실행함(49회차 `/tmp/it49` 경로는 scratchpad 로 치환).
- 51회차 F51-1(MCP 표면 타임아웃·티켓 회수)은 MCP 표면 경유 장시간 실행이 필요해 재검하지 않음(백엔드 직행 실행은 전부 정상 완주).
- 52회차 "13문장 완성 부동산 보고서" 전체 프로그램은 원장 쓰기(`[self:edit]`)·외부 다수 호출 포함이라 재실행하지 않음 — 그 안에서 적발된 B52 만 최소 재현으로 재검.
- 외부 원천(researcher·performance·stock) 호출은 모두 응답 정상 — 외부 원천 범주 해당 없음.
