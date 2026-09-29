# 상상 훈련 73회차 결과보고서 (2026-09-28) — 문서·표·차트 산출: 조회·집계 결과를 사람이 볼 산출물로

훈련 턴 · **무수정**(가이드 §4-3: 훈련 턴은 라이브 코어를 고치지 않는다). 아래 갭 원장은 [before.json](before.json)과 훈련자가 직접 열어 본 산출물만으로 썼다. 집행 완료 절은 비워 두었다.

## 축 선정

- 축 = 행동 기준 미조합 메뉴의 `table:chart`·`table:document`·`table:spreadsheet`·`table:structure`·`table:rename`·`table:flatten`, `self:sheet`·`self:document`·`self:output`·`self:slide`·`self:deck`. 모두 "교재에는 조합 있음 = 가르쳤으나 안 씀" 부류다. 이것들을 조회·집계 뒤 **마지막 구간**(사람이 볼 산출물)에 놓았다. 도메인은 가계부 월간 보고(72회차 조회의 산출 쪽), 강의 성적표·출석 요약, 가족신문, 부동산 매물 메모, 투자 보고서(캔들·pptx).
- 72회차가 남긴 단서 두 개를 따라갔다. ① groupby·join 결과(Record 봉투)를 산출로 넘길 때의 `.items` 마찰, ② 재무 봉투의 `table`·`blocks`·`points` 중 산출이 어느 칸을 쓰는가. 결과는 그보다 앞에서 막혔다. **판본 2에서는 산출 도구 대부분이 파이프를 아예 받지 못한다**(B73-1). 그래서 `.items`를 붙이든 안 붙이든 `>> [table:chart]`가 거절된다.
- 축 선정 관문 질문("기계로 열거 가능한가"): 조합 자체는 열거할 수 없다. 발견 가운데 두 부류(파이프 자리 누락 B73-1, 선언∖읽기 B73-2)는 열거 가능함이 드러나 읽기 전용 census를 돌렸다([pipe_census.json](pipe_census.json)·[declared_unread_census.json](declared_unread_census.json)). 둘 다 같은 속의 반복이므로 census로 넘기라고 적었다.
- 닫힌 밭(값 표기 격자·날짜 표기·동시성)은 밟지 않았다. 67~72회차 수리 표면(Decimal: 78.5·70.25 성적 → 차트·엑셀 숫자 보존, 결과 참조, 지역 함수)은 산출 경로에서 정상으로 지나갔다.
- 탐침 표면: 모델 경로(`agent_id:"IT73_probe"`·`task_id:"IT73_task"`). 모든 요청이 `edition:2`·`project_id:"컨텐츠"`·`origin:"training"`이다.
- ★사용자 재무 원장은 읽기만(`query`) 했다. 산출은 `outputs/IT73_*`에만 쓰고 탐침 앞뒤로 지웠다. 발신·표시(`others:publish`·`self:output`)와 사용자 강의 저장소에 쓰는 `self:slide create`·`self:deck export`는 check만 했다.
- ★시각 산출물은 전부 직접 열어 판정했다. PNG는 이미지로 보고, PDF는 렌더를 보고, pptx는 python-pptx 되읽기와 LibreOffice PDF 변환으로 봤다. 탐침 PASS는 파일 존재·기계 대조까지일 뿐이며, 육안 판정이 다르면 과제 표에 적었다.

## 지표 스냅샷 (훈련 전)

행동 미조합 140/168 · 파이프 길이 중앙값 3 · 문형 4(조회 26·축적 8·적용 6·조건 2, 시간·발신 0) · 파트너 다양성 중앙값 2. 72회차와 같다. 원본은 [metrics.json](metrics.json). 지표는 몸의 현황이며 훈련 실측은 증류에 담기지 않는다(§6).

## 과제 표

원문·판정식: [probe.py](probe.py) · 응답 전량: [before.json](before.json).
**24과제 중 기계 판정 14통과 · 10실패.** 육안 판정으로 T03을 꼬임으로 추가했다(결함 6부류 · 마찰 5부류). 실행 22 · check만 2(T08·T24). 과제 안 check는 6건(T20 교재 파이프 형태 1, T23 발신·표시·슬라이드·덱 5).

탐색 중 제 문장 잘못은 결함 판정에서 뺐다. 교재에 없는 삼항 `?:`를 썼고, 예약 바인딩 `$i`에 대입했고, groupby 집계에 `mean`을 썼고(정답 `avg`, 오류가 가능 목록을 알려 줌), f-문자열 안에서 따옴표를 이스케이프했고(교재대로 바깥 작은따옴표로 하면 됨 — 문구는 F73-5), flatten 결과의 없는 `total`을 읽었다. 고쳐서 다시 찍었다. T06은 처음에 기계 PASS였지만 PDF를 열어 보니 그림 자리가 깨진 아이콘이었다. 판정식을 "PDF 안 그림의 크기"로 조이고 FAIL로 기록했다.

| # | 상상 의도 | 결과 | 분류 |
| --- | --- | --- | --- |
| T01 | 9월 결제수단별 지출 막대그래프 (교재·코퍼스 4789·4110 형태 `$g.items >> [table:chart]`) | **`PIPE_COLLISION`** — "같은 명시 인자를 함께 주지 마세요" | 결함 B73-1 |
| T02 | 같은 막대를 표형 `table:{columns,rows}`로 | 하나카드 790,027 · 청주페이 321,500 = 원장. 그림: 제목·라벨·값 정상, 한글 정상(x축 제목 없음) | 깨끗 |
| T03 | 최근 석 달 월별 지출·수입 두 선 | 두 시리즈·범례 정상. **x축이 `Jun 28 2026·Jul 12·…·Aug 23` 영어 2주 눈금**이고 9월 점에 라벨 없음 | 꼬임 F73-3 |
| T04 | 가맹점별 금액 막대 — 선언된 `x:"counterparty", y:"amount"` | **29항목·11시리즈**(meta·url·record_id·date…) 쓰레기 막대가 success | 결함 B73-2 |
| T05 | 9월 가계부 월간 보고서 HTML(합계 문장·큰 지출 5건 표·메모 목록) | 합계 1111527원·5행 표·부제 정상. 표 1위가 `입니다.` 545,408, 가맹점 빈 칸 2행 | 깨끗(B72-1·F72-1 노출) |
| T06 | 보고서 PDF에 막대그래프 그림 넣고 되읽기 | 제목·본문·캡션은 있음. **그림 자리가 깨진 아이콘(14×16) + alt 문구**, success | 결함 B73-4 |
| T07 | 차트 두 장을 한 문서에 그림으로 (교재 `as:"images"`에 차트 결과 행 그대로) | "그림 경로를 가진 행이 없습니다"(경로가 `data.path`) · `src_field:"data.path"` 불가 · compute로 `path` 끌어올리면 됨 | 꼬임 F73-1 |
| T08 | 5만원 넘는 9월 지출만 엑셀로 (코퍼스 4790 현재 문법판, check) | 파이프 `PIPE_COLLISION` · `items:` `UNKNOWN_ARGUMENT` | 결함 B73-1(+B72-2 재확인) |
| T09 | 8월·9월 지출을 월별 시트로 (`sheets:{8월:$a.items, 9월:$b.items}`) | **success, 두 시트 모두 1열 — A1 = `"{'title': '더홀릭영통점 …', 'meta': …}"`** | 결함 B73-3 |
| T10 | 강의 성적표 — 총점·등급 계산, 총점 순 엑셀, 되읽기 | 이서연 94.1 A · 정하늘 85.6 B · 김민수 84.2 B · 박지훈 68.15 C, 셀은 숫자(n) | 깨끗 |
| T11 | 성적표에서 B등급만 — 만든 이름(`~workspace/outputs/…`) 그대로 `self:sheet find` | **`…/projects/컨텐츠/~workspace/outputs/IT73_grade.xlsx` 없음**. 절대경로는 [정하늘, 김민수]. 같은 토큰 되읽기: xlsx·html ok, **pdf not_found**, sheet range ok | 결함 B73-6 |
| T12 | 전학생 추가(수식 총점) + 박지훈 출석 정정 (append·update → find) | 5행, 박지훈 출석 13, 최유진 `=B6*0.4+C6*0.6` | 깨끗 |
| T13 | 등급 분포 막대 (groupby → 표형) | A1·B2·C1, 그림 정상(y축 0.5 눈금은 사소) | 깨끗 |
| T14 | 지출 없는 1월 차트 | "입력 0행 — 그릴 내용이 없습니다", 파일 안 만듦 | 깨끗 |
| T15 | 출석 요약 워드 문서(부제 "2026년 2학기 · 16주차 기준") → `self:document inspect` | 제목·본문·표 정상, **부제 문단 없음**(docx 전체에 `학기` 문자열 0) | 결함 B73-5 |
| T16 | 출석 문서 문구를 변경 추적으로 고쳐 새 파일에 → 되읽기 | "면담 대상(결석 3회 이상): 박지훈". 토큰 되읽기: **read_docx 실패**, document inspect ok | 깨끗(B73-6 증거) |
| T17 | 가족신문 10월호 — 기사 카드 3건을 신문 테마 PNG로 | 제호·부제·2열 카드 정상, 한글 정상 | 깨끗 |
| T18 | 부동산 매물 메모 — 영문 키를 한글 열로 rename, 단지별 평균 호가 문서·엑셀 | 표 머리 `단지·전용면적·호가_만원·층`, 가경자이 45,500(2건) · 복대두산위브 47,000. groupby Record에 rename 직결도 됨 | 깨끗 |
| T19 | 강의별 수강생(중첩) 한 줄 한 명으로 펼쳐 엑셀 | 3행, 빈 목록 강의는 0행 | 깨끗 |
| T20 | 강의 메모 → structure → 강의 일지 HTML | 명시형(`title:$s.title, blocks:$s.blocks`)은 사실 보존(25명·10월 10일). 교재 파이프형은 `PIPE_COLLISION`×2 | 꼬임(B73-1) |
| T21 | 삼성전자 1개월 캔들차트 (`data:$h.items`, MA5) | 20봉·MA5·거래량, 한국식 적/청 정상 | 깨끗 |
| T22 | 투자 보고서 pptx(제목·부제·요점·종가 그림) → 슬라이드 되읽기 | 표지에 **부제 없음** · "종가 추이" 제목 슬라이드는 빈 채, 그림은 **다음 무제 슬라이드** | 결함 B73-5 · 마찰 F73-4 |
| T23 | 보고서를 마크다운으로 받고 발행·클립보드·화면·슬라이드·덱으로 (발신·표시·슬라이드 check) | `markdown` 필드 정상, check 5건 모두 `incomplete`·이슈 0 | 깨끗(검수만) |
| T24 | 교재 낱말로 차트 옵션(`series`·`hole`·`trendline`·`ma`, check) | 넷 다 `UNKNOWN_ARGUMENT` + 범용 안내 | 마찰 F73-2 |

명시 인자로 부른 산출과 표 변환은 튼튼했다. 차트 `table`/`data`, 문서 `blocks`/`items`/테마, 엑셀 `headers`/`rows`, `self:sheet`·`self:document` 왕복, rename·flatten·groupby, 0행 정직 거절이 여기 해당한다. 실패는 **산출 도구의 입구 계약**(파이프 자리·선언된 인자·행 모양)과 **emitter 간 불일치**(그림·부제·경로 토큰·영수증 모양)에서 났다.

## 갭의 원장

### B73-1 ★최우선 — `pipe_in: true` 소비자 **15/18**이 판본 2에서 파이프를 못 받는다 (★밭 이관: B56-1·B58-1과 같은 속의 세 번째)

- **요약**: 판본 2의 호환 계약(`ibl_v2_contracts.handler_contract`)은 `pipe_input`을 만들지 않는다. 파이프 자리는 원천 YAML의 명시 `callable_contract`(58회차에 flow 19개로 연결)에서만 온다. 그래서 `pipe_in: true`로 **앞 통화를 읽는다고 선언한** 소비자 중 flow가 아닌 것은 전부 파이프 자리가 없다. `A >> [table:chart]{…}`는 실행 전에 `PIPE_COLLISION`으로 거절된다.
- **최소 재현**(check): `[{a:"x",b:1}] >> [table:chart]{title:"t"}` · `… >> [table:document]{}` · `… >> [table:spreadsheet]{path:"x.xlsx"}` · `"본문" >> [table:structure]{}` · `… >> [self:sheet]{op:"append", path:"x.xlsx"}`
- **실측**: 다섯 모두 `invalid` — `PIPE_COLLISION: 파이프 입력 자리가 없거나 명시 인자와 충돌합니다.`, hint "파이프 입력 자리와 같은 명시 인자를 함께 주지 마세요." 충돌하는 인자가 없으므로 안내가 **원인과 반대 방향**이다(사용자는 인자를 빼 보다가 멈춘다). 같은 문장을 옛 `/ibl/validate`에 넣으면 `valid: True`. (보고서 저장 전 첫 문장을 다시 check로 재현해 같은 진단을 확인했다.)
- **범위(읽기 전용 census)**: [pipe_census.json](pipe_census.json) — `pipe_in: true` 18개 중 파이프 자리 있음 3(`self:read`·`self:script`·`self:write`), **없음 15**: `table:chart`·`table:document`·`table:spreadsheet`·`table:structure`·`self:sheet`·`self:output`·`self:ask`·`self:struct`·`self:copy`·`others:publish`·`others:delegate`·`engines:render`·`engines:image_read`·`limbs:os_open`·`limbs:android`. 코퍼스 3,735문장 중 **140문장**이 이 15개 중 하나로 `>>` 한다(chart 45·document 38·spreadsheet 22·copy 9·android 7·ask 7·struct 5·structure 4·sheet 4·render 3·os_open 1, manual_seed 71). 회상은 이들을 옛 판본으로 표시해 새 문법으로 옮기라고 하는데, 옮기면 반드시 이 거절을 만난다.
- **영향**: 모델의 기본 문법(판본 2)으로는 "조회 → 가공 → **차트/문서/엑셀**"의 마지막 이음매를 쓸 수 없다. 우회는 도구마다 모양이 다르다. 차트는 `table:{columns,rows}`를 each로 손수 짜야 하고, 엑셀은 `headers`+`rows`를 짜야 한다(`items`는 B72-2로 거절). 문서는 `items:`, structure는 `content:`를 쓴다. 72회차 단서였던 `.items` 마찰은 이 거절 뒤에 가려져 있다.
- **뿌리**: B56-1(결합 도구)·B58-1(단항 flow)과 같은 속이다. "선언된 입력을 판본 2 계약이 모른다." 58회차 빌드 관문은 **flow 선언의 입력 자리 누락**만 거부한다. 09-18에 T3(죽은 이음매) 소비자 선언으로 생긴 `pipe_in: true`는 그 관문 밖이다.
- **제안(수리성, ★밭 이관)**: 개별 도구 수리가 아니라 ① `pipe_in: true` 전수(위 15개)에 판본 2 파이프 자리를 선언한다. emitter는 `items`(없으면 추가 선언)·structure는 `content`·sheet는 `items`처럼, 핸들러가 `_prev_result`로 읽던 자리를 명시 입력으로 연결한다. Record 입력은 flow처럼 `input_envelopes: items`로 받는다. ② 빌드 `--check`에 "`pipe_in: true` ⇒ 계약 `pipe_input` 존재" 관문을 넣는다. ③ `PIPE_COLLISION`을 "자리 없음"과 "명시 인자와 충돌"로 갈라, 자리 없음이면 받는 인자 이름(예: `items:`·`table:`)을 안내한다. 가드: 15개 × {List, Record 봉투} 파이프 check·실행, 옛 validate와 판본 2 판정 일치.

### B73-2 선언된 `table:chart` `x`·`y`를 핸들러가 **한 번도 읽지 않는다** — 쓰레기 차트가 성공 (★밭 이관: B72-4와 같은 속의 두 번째)

- **요약**: `visualization/ibl_actions.yaml`은 `params: {x: string, y: string}`을 선언한다(코퍼스 4110이 `x:"${지역열}", y:"${수치열}"`로 가르친다). 하지만 `handler.py`와 렌더러 9개 어디에도 `tool_input.get("x"|"y")`가 없다. 열 선택은 "첫 dict의 키 순서 = 열(첫 열 = 라벨, 나머지 = 시리즈)"뿐이다.
- **최소 재현**: `$t = [self:finance]{op:"query", query_type:"지출", month:"2026-09"}; [table:chart]{chart_type:"bar", title:"가맹점별", data:$t.items, x:"counterparty", y:"amount"}`
- **실측**: `success: true`, "막대 차트 생성 완료 (29개 항목, **11개 시리즈**)". 그림을 열어 보면 범례가 `meta·summary·url·record_id·record_type·kind·date·category·counterparty·amount·source`이고, x 라벨은 `지출 · 2026-09-28` 같은 meta 문자열, 막대는 날짜·ID 등이 뒤섞여 읽을 수 없다. 판본 2 검사·옛 검사 모두 통과한다(선언된 인자이므로).
- **범위(읽기 전용 census, 하한)**: [declared_unread_census.py](declared_unread_census.py)는 선언 params를 패키지 .py의 입력 dict 읽기(`tool_input/input_data/params….get("키")`·`["키"]`·`in`)와 AST로 대조한다. 후보는 9액션 37인자다. `table:chart x·y`(확인), `table:filter value`, `self:finance items`, `sense:company company·corp_name·query·type`, `self:memory keywords`, `self:record`(16인자 — 다른 변수 이름으로 읽을 가능성), `table:join/union/merge table1·table2·a·b`(**오탐 확인**: `pairs` 튜플로 읽음). 단순 문자열 grep은 `x`를 못 잡았다(행 필드 `item.get('x')`가 같은 글자) — AST 대조가 필요한 이유다.
- **뿌리**: B72-4(선언된 `category`를 지출 조회가 무시)와 같은 속이다. "선언 ⊆ 읽기"를 아무 관문도 보지 않는다. B72-2 census(읽기 ⊆ 선언)의 **반대 방향**이다.
- **제안(수리성, ★밭 이관)**: ① `x`·`y`를 실제 열 선택으로 구현한다(`data`/`items` 행에서 라벨 열·값 열 선택, 여러 `y`면 시리즈). 선언을 지우는 것은 코퍼스 4110을 깨므로 택하지 않는다. ② 선언∖읽기 census를 확정해 일괄 처리한다(구현하거나 "무시됨" 신고). ③ 빌드 `--check`의 삼각 검증에 "선언 params ⊆ 핸들러 입력 읽기(AST, 별칭·쌍 별칭 포함)" 변을 넣는다. B72-2의 역방향 변과 한 관문으로 묶는다. 가드: chart x·y × {bar, line, pie} 열 선택, 열 순서와 무관한 결과.

### B73-3 `table:spreadsheet` `rows`·`sheets`에 **레코드 행**을 주면 Python repr 한 칸으로 적고 success

- **요약**: `office_ops.spreadsheet`의 `_fill`은 행이 list/tuple이 아니면 `ws.append([_coerce(r)])`로 **행 전체를 `str(dict)` 한 칸**에 넣는다. 레코드 → 표 투영(`_items_to_table`)은 `items`·`_prev_result` 경로에만 있다. 판본 2는 `items`를 `UNKNOWN_ARGUMENT`로 거절하고(B72-2), 파이프도 거절한다(B73-1). 그래서 판본 2에서 조회 결과를 엑셀로 옮기는 자연스러운 형태 둘은 거절되거나 쓰레기가 된다.
- **최소 재현**: `[table:spreadsheet]{path:"~workspace/outputs/x.xlsx", headers:["이름","점수"], rows:[{이름:"김민수", 점수:84}]}`
- **실측**: `success: true`. 셀은 `[['이름','점수'], ["{'이름': '김민수', '점수': 84}", None]]`. T09(`sheets:{8월:$a.items, 9월:$b.items}`)는 두 시트 모두 1열이고 A1이 `"{'title': '더홀릭영통점 / ( ,2*9*) / / 이용금액 · 6,000원', 'meta': …"`, 응답은 `{"success": true, "sheets": ["8월","9월"]}`.
- **영향**: 월별 시트 가계부·반별 성적 시트처럼 **다중 시트의 유일한 길(`sheets`)**이 레코드를 못 받는다. 산출물이 생기고 성공이라 읽는 쪽은 모른다. "산출물 없이는 성공도 없다(09-03)" 규율의 남은 틈이다. 빈 파일은 막았지만 **모양이 틀린 파일**은 통과한다.
- **제안(수리성, 비파괴)**: `rows`·`sheets[시트]`의 행이 레코드면 단일 시트 `items`와 같은 표 투영(머리 = 관측 열 합집합, `headers`가 주어지면 그 열 순서로 값 선택)을 적용한다. 투영할 수 없는 모양(중첩 등)은 거절하고 받은 모양을 신고한다. 기존에 리스트 행을 주던 문장은 불변이다. 가드: {rows, sheets} × {리스트 행, 레코드 행, 섞임} 셀 대조.

### B73-4 문서 PDF·PNG가 로컬 그림을 **깨진 그림 아이콘**으로 싣고 success

- **요약**: `doc_build`는 pdf·png를 `pg.set_content(doc)`(about:blank 문서)로 렌더한다. `<img src="/Users/…/x.png">` 같은 파일 경로 그림은 about:blank 출처에서 읽히지 않는다. 같은 IR을 docx·pptx emitter는 `_resolve_image_bytes`(파일·data URI·file://)로 **바이트를 넣어** 정상으로 싣는다.
- **최소 재현**: `[table:document]{format:"png", filename:"~workspace/outputs/x", blocks:[{type:"paragraph", text:"그림 아래"}, {type:"image", src:"<차트 PNG 절대경로>", caption:"등급 분포"}]}`
- **실측**: success. PNG를 열어 보면 그림 자리에 **깨진 이미지 아이콘 + alt 문구 "등급 분포"**, 그 아래 캡션만 있다. T06 PDF도 같다. fitz로 본 PDF 안 그림은 `[[14, 16]]` 하나(아이콘)뿐이고, 텍스트에는 캡션이 두 번(alt + figcaption) 나온다.
- **영향**: "차트를 넣은 보고서 PDF"는 산출 축의 대표 과제다(가계부 월간 보고·투자 보고서·강의 자료). 성공 봉투와 페이지 수·그림 수만 보는 검사는 전부 통과하므로 사람만 알아챈다. 문서 선언의 `as:"images"`(도면·사진·차트 N장을 그림으로) 예시도 pdf/png 형식에서는 같은 결과가 된다.
- **제안(수리성)**: pdf/png 렌더 전에 image 블록의 로컬 경로를 data URI로 인라인하거나(docx·pptx와 같은 `_resolve_image_bytes` 재사용), 문서 파일을 임시 경로에 써서 `goto(file://…)`로 연다. 렌더 뒤 그림을 못 실은 블록 수를 신고하고, 0이 아니면 실패 또는 `images_failed`로 알린다. 가드: {html, pdf, png} × {절대경로, ~workspace, data URI} 그림 → 렌더 결과 그림 크기 대조(아이콘 판별).

### B73-5 문서 IR의 `meta`(부제)가 **docx·pptx에서 말없이 사라진다**

- **요약**: `_doc_blocks_to_docx(blocks, title, out_path)`·`_doc_blocks_to_pptx(blocks, title, out_path)`는 `meta`를 받지 않는다. html·typst·markdown emitter는 `meta`를 받아 제목 아래에 싣는다. 선언은 "단일 IR → 다중 emitter", "meta(선택, 제목 아래 부제/발행정보 한 줄)"이다.
- **최소 재현**: `[table:document]{title:"AI 개론 출석 요약", meta:"2026년 2학기 · 16주차 기준", format:"docx", filename:"~workspace/outputs/x", blocks:[{type:"paragraph", text:"본문"}]}` → `[self:document]{op:"inspect", path:…}`
- **실측**: 문단 = `AI 개론 출석 요약` · `본문` …. docx 안 XML 전체에 `학기` 0회. T22 pptx 표지는 제목만 있고 부제 자리표는 비어 있다(python-pptx 되읽기: `['삼성전자 월간 점검', …]`에 "개인 투자 메모" 없음).
- **영향**: 성적표·출석부·보고서의 "학기·기준일·작성 근거" 줄이 형식을 바꾸면 사라진다. 기준일 없는 성적 문서는 오해를 부른다. 성공 봉투는 `blocks: 3`만 말한다.
- **제안(수리성)**: docx는 제목 아래 부제 문단(또는 Subtitle 스타일), pptx는 표지의 부제 자리표에 `meta`를 싣는다. emitter 짝맞춤 시험을 둔다. 같은 IR을 전 형식으로 렌더해 {title, meta, 블록 텍스트} 보존을 대조한다(`when` 생략·cards meta 포함).

### B73-6 `~workspace/…`가 `self:read` pdf·docx와 `self:sheet` find/append/update에서 **펼쳐지지 않는다** (관문 그물 밖)

- **요약**: 경로 펼침 단일 해소점 `expand_body_path`를 거치지 않는 해석기가 남아 있다. `office_ops.read_pdf`·`read_docx`는 `Path(tool_input.get("file_path") or path)`를 그대로 쓰고, `sheet_ops._resolve`는 `Path(raw)`를 `_project_path`에 붙인다. 같은 패키지의 `_get_path`(text·xlsx 읽기), `essentials_ooxml.resolve`(sheet range·document), `ToolContext.resolve_output_path`(emitter)는 펼친다.
- **최소 재현**: `[table:spreadsheet]{path:"~workspace/outputs/g.xlsx", headers:["a"], rows:[[1]]}` 뒤 `[self:sheet]{op:"find", path:"~workspace/outputs/g.xlsx"}`
- **실측**: "파일을 찾을 수 없습니다: /Users/kangkukjin/Desktop/AI/indiebizOS/projects/컨텐츠/~workspace/outputs/IT73_grade.xlsx". 같은 토큰으로 되읽은 결과: `self:read` xlsx ok · html ok · pptx ok · md ok · **pdf not_found** · **docx not_found** · `self:sheet range` ok · `self:document inspect` ok. 절대경로로 부르면 find는 [정하늘, 김민수]로 정상이다.
- **영향**: "방금 만든 파일을 만든 이름 그대로 다시 연다"가 형식·op에 따라 된다·안 된다로 갈린다. 쓰기 도구는 `~workspace`를 권하는데(self:write 교재 "원장과 공유할 파일은 ~workspace/ 접두"), 읽기 쪽 두 형식과 sheet 행 편집이 그 약속을 어긴다. 보고서 PDF를 되읽어 검증하는 흔한 단계(T06)가 이 이름으로는 실패한다.
- **뿌리**: 09-02 관문 `check_body_path_expansion`은 `.expanduser(` 호출만 금지한다. 아예 펼치지 않는 `Path(raw)`·`os.path.join(project_path, raw)` 형태는 그물 밖이다. 관문을 낳은 사건("토큰이 그 자리에서만 조용히 안 먹는다")과 같은 속이다.
- **제안(수리성)**: ① 두 읽기와 `sheet_ops._resolve`를 `expand_body_path`(또는 `ToolContext.resolve_path`)로 옮긴다. ② census: 패키지·IBL 표면에서 경로 인자(`path`·`file_path`·`src`·`dir_path`·`output`)를 `Path(…)`/`os.path.join(project_path, …)`에 **해소점 없이** 넣는 자리를 AST로 전수 조사한다. 관문을 그 형태까지 넓힌다. 가드: `~workspace/` 경로 × 읽기 형식 전부 × sheet op 전부.

### F73-1 차트 영수증의 경로가 `data.path`에 있어 **형제 emitter와 모양이 다르다** — 교재 `as:"images"`가 실패

- T07: `[table:document]{items:[$c1, $c2], as:"images"}` → "2행 중 그림 경로를 가진 행이 없습니다(관습 이름 ['src','path','image','file','url'] …)". `table:chart`는 `{success, data:{path, format, image_tag}, summary}`를 돌려주고, `table:document`·`table:spreadsheet`는 최상위 `path`를 돌려준다. `src_field:"data.path"`는 "src_field 'data.path' 없음"으로 점 경로를 받지 않는다. 우회 `[$c1,$c2] >> [table:compute]{set:($r)=>{path:$r.data.path}}`는 된다. 선언 예시는 `engines:arch_elevation`(최상위 path)이라 차트에서 같은 형태가 깨진다는 것이 드러나지 않았다.
- 제안(수리성): 차트 영수증에 최상위 `path`(와 `file`)를 더한다(`data.path`는 호환 유지). `src_field`·`caption_field`는 공통 필드 경로 해석기(`common/field_path.py`)로 점 경로를 받는다. 가드: chart·document·spreadsheet·arch 영수증 → `as:"images"` 직결.

### F73-2 `table:chart` 교재 낱말이 선언·핸들러에 없다 — 판본 2가 범용 안내로 거절 (F72-2 재확인)

- T24: target_description이 "다중 시리즈는 **series** 배열", "pie: … **hole** 옵션으로 도넛", "scatter: … **trendline** 옵션", "candlestick: … **ma** 옵션"이라고 가르친다. 하지만 선언과 렌더러의 실제 이름은 `series_names`·`donut`·`show_trendline`·`ma_periods`이고 `series`를 읽는 코드는 없다. 판본 2는 넷 다 `UNKNOWN_ARGUMENT`, 안내는 "현재 판본의 서명에 선언된 인자 이름을 사용하세요."뿐이다(최근접 이름 제안 없음 — F72-2와 같은 처방).
- 제안(수리성): 교재 수리는 표면 전수다(§4-3). target_description·tool.json 설명의 낱말을 실제 이름으로 고치거나, 흔한 낱말을 `aliases`로 선언한다(`hole→donut`, `trendline→show_trendline`, `ma→ma_periods`). `series`는 구현이 없으므로 교재에서 빼고 표형 `table`의 다열 = 다중 시리즈를 가르친다. 은퇴 낱말은 `retired_contracts.yaml`에 등록한다.

### F73-3 월 라벨 `"2026-07"`이 날짜축으로 해석돼 **영어 2주 눈금**이 된다

- T03: `table:{columns:["월","지출","수입"], rows:[["2026-07",0,0],["2026-08",696101,0],["2026-09",1111527,42131]]}` 선 그래프를 열어 보면 x축 눈금이 `Jun 28 2026 · Jul 12 · Jul 26 · Aug 9 · Aug 23`이다. 세 점이 각 월 1일에 찍히고 **9월 점에는 라벨이 없다**(가장 가까운 눈금이 Aug 23). 월별 보고 차트를 사람이 잘못 읽게 된다. 범주축으로 강제할 인자가 없고 `spec`(Plotly figure JSON)으로만 우회된다. 캔들·종가 추이(일별)의 영어 월 표기(`Aug 30`·`Sep 6`)도 같은 기본값에서 나온다.
- 제안(수리성): `YYYY-MM` 라벨은 월 범주(또는 `dtick:"M1"`·`tickformat:"%Y-%m"`)로 그리고, 날짜 눈금은 한국어 형식(`%m/%d` 등)을 기본으로 한다. 가드: 월 라벨·일 라벨 차트의 눈금 문자열 대조.

### F73-4 pptx 투영이 그림·표를 **늘 새 무제 슬라이드**로 보낸다 — 제목 슬라이드가 빈 채 남는다

- T22: blocks `heading "종가 추이"` → `image`를 넣으면 python-pptx 되읽기 결과가 `['종가 추이', 그림 0개, '']`, `[None, 그림 1개, '']`이다. LibreOffice 변환으로 봐도 빈 제목 슬라이드 다음에 제목 없는 그림 슬라이드가 온다. `_doc_blocks_to_pptx`의 image·table 가지가 `prs.slides.add_slide(blank)`로 항상 새 슬라이드를 만들기 때문이다. 선언은 "heading = 새 슬라이드, 그 아래 내용 = 글머리표"라 제목 아래 그림을 기대하게 한다.
- 제안(수리성): 직전 heading 슬라이드에 본문이 없으면 그 슬라이드의 본문 영역에 그림·표를 배치한다. 본문이 있을 때만 새 슬라이드를 만들되 heading 제목을 이어 단다.
- (관찰, 미확정) pptx 한글 글꼴이 테마의 `Hang = 맑은 고딕`에만 기대고 run 단위 `ea` 글꼴이 없다. 이 맥의 LibreOffice 변환에서는 **한글이 전부 빠지고** 숫자만 남았다(제목 슬라이드 공백). PowerPoint에서는 확인하지 못했다. 뷰어 의존일 수 있어 결함으로 적지 않는다. 수리 턴이 PowerPoint·Keynote에서 먼저 확인할 것.

### F73-5 (탐색 중 발견) 보간 안 이스케이프 따옴표에 "닫는 }가 없습니다"

- `f"x: ${join(\", \", $w)}"` → `SYNTAX: 보간의 닫는 }가 없습니다.`, hint "표시된 구문 경계를 수정한 뒤 프로그램 전체를 다시 검사하세요." 닫는 `}`는 있다. 원인은 보간 안의 `\"`이다. 교재 규칙(바깥 작은따옴표 `f'x: ${join(", ", $w)}'`)으로 쓰면 된다. 훈련자 잘못이지만 문구가 방향을 주지 않는다.
- 제안(수리성): 보간 안에서 이스케이프된 따옴표를 만나면 "보간 안 문자열은 바깥을 작은따옴표로 감싸세요" 안내를 낸다(70회차 F70-1의 코드별 전용 안내 부류).

### G73-1 (판정 요청) 순수 식에 **조건 값**이 없다 — 등급 매기기가 each+if 세 줄

- T10·T13: 총점 → 등급(A/B/C)은 성적표의 가장 흔한 가공이다. `table:compute`의 `set:($r)=>{…}`는 순수 식만 받고 교재에 조건 식이 없다(`?:`는 SYNTAX). 되는 형태는 `$표 >> [table:each]{ [if: $it.총점 >= 90] { return {**$it, 등급:"A"} } [if: …] {…} return {**$it, 등급:"C"} }`다. 가계부 분류("5만원 이상 = 큰 지출"), 출석 경고, 부동산 "호가 > 실거래 평균" 표시가 모두 같은 우회를 요구한다.
- 새 문법이므로 **언어 개정**이다. 판정 요청에 올린다. 67회차 G67-1(순수 식 원소별 변환 부재)과 함께 판정하면 좋다.

## 재확인 (앞 회차 갭의 증거 추가 — 새 항목 아님)

- **B72-1·F72-1**: T05 월간 보고서 표 1위가 `입니다.` 545,408원이고 가맹점 빈 칸 2행 — 산출물(사람이 읽는 보고서)까지 오염이 그대로 흘러간다.
- **B72-2**: T08 `table:spreadsheet`의 `items:`가 판본 2에서 `UNKNOWN_ARGUMENT`.

## 시드 후보 (실행 검증 통과만 — 자동 등록 안 함)

T02(groupby → each 행 → 차트 `table:{columns,rows}`) · T05(월간 보고서: reduce + sort/take + each 행 → `blocks`) · T10(성적표: compute 총점 → each+if 등급 → sort → `headers`/`rows` 엑셀 → read 되읽기) · T12(`self:sheet` append 수식·update → find) · T13(등급 분포 차트) · T14(0행 차트 정직 거절) · T16(`self:document` inspect → edit 변경 추적 → read) · T17(가족신문 `theme:"newspaper"`) · T18(rename → groupby avg → rename → document·spreadsheet) · T19(flatten keep → spreadsheet) · T20 명시형(structure → `title:$s.title, blocks:$s.blocks`) · T21(캔들 `data:$h.items`). 경로는 `<출력경로>` 자리표로 바꿔 심을 것.

**B73-1 수리 전 주의**: 위 시드는 파이프 없는 명시형이라 지금 유효하다. B73-1 수리 턴이 파이프 형태(`… >> [table:chart]`)를 정본으로 되살리면 코퍼스의 파이프형 140문장이 다시 유효해진다. 그러니 시드는 수리 후에 파이프형과 명시형 중 무엇을 가르칠지 정하고 넣는다. B72-1 수리 전에는 가계부 보고서(T05)를 "정답 수치"와 함께 심지 말 것. T06·T09·T15·T22는 결함 수리 전이라 시드에서 뺀다.

## 판정 요청 (언어 개정·파괴적 변경 2종만)

- **G73-1 — 순수 식의 조건 값(예: 삼항 또는 식 위치의 case)**을 문법에 들일지. 근거: 성적 등급·금액 구간·경고 표시가 모두 each+if 세 줄 우회를 요구한다(T10·T13). 67회차 G67-1과 같은 층(순수 식 표현력)이다.

그 밖의 B73-1~6·F73-1~5는 수리성이다. B73-1의 `PIPE_COLLISION` 분리, B73-2의 x·y 구현(선언 삭제 아님), B73-3의 레코드 행 투영은 모두 지금 거절되거나 쓰레기가 나는 문장을 살리는 쪽이라 기존 문장을 깨뜨리지 않는다.

**다음 수리 턴의 첫 항목(밭 이관)**: ① B73-1 — `pipe_in: true` 소비자 15개 파이프 자리 일괄 연결 + 빌드 관문(B56-1·B58-1에 이은 세 번째). ② B73-2 — 선언∖읽기 AST census 확정 + 삼각 검증에 역방향 변(B72-4에 이은 두 번째, B72-2 census와 한 관문). ③ B73-6 — `check_body_path_expansion`을 "해소점 없는 경로 결합" 형태까지 확장하는 census.

## 위생

- 스크래치: `outputs/IT73_*`와 `projects/컨텐츠/outputs/IT73_*`(탐침 앞뒤 삭제), 탐색용 `IT73_x_*`·`IT73_m_*` 모두 잔존 0. `self:read` pptx가 원본 옆에 만든 `outputs/IT73_t22_images/`(그림 1장)도 삭제했다. LibreOffice 변환 PDF는 세션 스크래치 디렉터리에서 삭제했다.
- 사용자 데이터: `data/finance/finance_records.db` 무변경(mtime 14:04 유지, 거래 63행·최대 id 943·주체 1명). 재무는 query만 했다.
- 발신 0 · 알림 0(알림함 정리 불요) · 클립보드·화면 표시·발행·슬라이드·덱은 check만 · 해마 시딩 0 · 라이브 코어 편집 0. census 두 개는 describe(효과 없음)와 파일 읽기만 한다.
- 건강 원장: 회차 창(21:45~) `action_health`는 **training 339행**이다(self:finance 65·table:chart 56·table:document 45·self:read 31·…·sense:stock 9·table:structure 5). 그 밖의 usage 37행은 agent 채널의 `sense:crawl` 23·`sense:search` 14로, 탐침이 부르지 않은 액션이며 다른 세션의 기록이다.
- AI 실호출: `table:structure` 5회(탐색 1 + 탐침 실행 4회 × T20 1건). 외부 조회 `sense:stock` 9회.
- 백엔드: 회차 내내 `state.json` phase `ACTIVE`, 재기동·FAILED 없음.

## 집행 완료

**1차 — `1b9a4932`(2026-09-29, 72~76회차 일괄 수리)**: B73-1~6·F73-1·F73-2(교재 교정)·F73-3 월 범주축·F73-4 슬라이드
이어 붙임·F73-5 개별 자리. 상세 `docs/IMAGINATION_72_76_REPAIRS.md`. 탐침 재실행 14/24 → 23/24.
밭 이관 ①(파이프 자리 빌드 관문)은 `iblbuild_v2.py` 로 섰고, ②·③은 서지 않았다.

**2차 — 잔여 수리(2026-09-29, 사용자 지시 "삼항 채택하고 남은 73회차 항목까지 수리")**
- **G73-1 언어 개정(사용자 판정: 채택)** — 순수 식의 조건 값 `조건 ? 값1 : 값2`. 조건은 Bool 만, 고르지 않은 가지는
  평가 안 함, 결과 타입 = 두 가지의 합, `or` 층에서 오른쪽 결합, 가지 안 호출은 PURE_EXPRESSION, 줄 머리 `?` 계속.
  파서(`common/expression_parser.py`)·타입 검사(`ibl_v2_compile.py`)만 바꿨다 — 평가기는 옛 판본 호환용
  `conditional` 노드(지연 평가·Bool 강제)를 이미 갖고 있어 그대로 공유. 명세 `ibl.md`·주 교재 `ibl_composition.md` 갱신.
  라이브: 성적 등급 한 줄 `compute{set:($r)=>{등급:$r.총점 >= 90 ? "A" : …}}` 가 A/B/C.
- **B73-2 ② ③ 선언-읽기 관문**(`scripts/iblbuild_declared_reads.py`, build `--check`) — 72회차 액션별 구현-읽기 관문의
  반대 방향. 역방향은 "읽기 전부"를 알아야 성립하므로 입력 dict 의 흐름을 끝까지 본 액션만 판정하고(패키지 밖 함수·
  동적 키·반복·반환으로 새면 판정 불가로 셈), 디스패치 표·형제 모듈 적재(`load_sibling`)·함수 별칭·상수 튜플 반복 키·
  별칭 도우미 상수를 따라간다. **수리 이전 트리(`1b9a4932^`)에 대면 `table:chart x·y`·`self:finance items` 를 잡는다.**
  현재 트리에서 새로 잡은 것: `self:music artist` — 07-28 은퇴한 정확 필터의 선언만 남아 `artist:"아이유"` 가 조용히
  무시되고 전곡이 나왔다 → 은퇴 결정문대로 `query` 별칭. `self:memory keywords` 는 save 가 정책상 본문째 버리고
  `saved:false` 로 정직하게 답하므로 사유를 적어 `DECLARED_UNREAD_ALLOW`. 판정 21 · 판정 불가 42(하한 — 관문 출력에 병기).
- **B73-6 ② 경로 관문 규칙 2**(`check_body_path_expansion.py`) — 입력 경로 키를 해소점 없이 `Path`·`os.path.join`·
  `abspath`·`exists`·`open` 에 넣는 형태. 수리 이전 트리의 `read_pdf`·`read_docx`·`sheet_ops._resolve`·`fill_op` 를 잡는다.
  현재 트리에서 새로 잡은 같은 부류: `engines:render` 4 op 의 `path`(문서→렌더 흐름이 `~workspace` 에서 끊김 — 라이브
  확인), `fill_op` 출력, Gemini/AI 이미지 `output_path`, 사이트 등록 `local_path`(레지스트리엔 해소된 경로 저장),
  폰 클립보드 `image_path`. 수리 자장 저장소 상대 경로 한 곳은 `path-ok` 사유.
- **F73-3 후반** — 날짜 축 기본 눈금을 한국어 표기로(`tool_common.apply_korean_date_ticks`: 간격별 `9/6`·`2026-09`·`2026`,
  렌더러가 형식을 정한 축·월 범주축은 그대로). T21 캔들 `Sep 6` → `9/6` 육안 확인.
- **F73-4** — 그림·표가 들어간 제목 슬라이드의 빈 본문 자리표 제거. pptx 한글 관찰(미확정)은 **결함 아님으로 판정**:
  이 맥의 LibreOffice 는 한글 **평문 txt 조차** 한글 글꼴 없이 렌더(샌드박스 밖에서도 동일), 맥 Quick Look 은 정상.
- 회원 개방 감사: system_essentials(`self:read/fill/script`) 지문과 record-ops 의존 지문(`expression_parser.py`) 재감사 —
  회원 `fill_document` 는 허브가 정한 절대 작업 경로를 넘기므로 펼침이 표면을 바꾸지 않고, 조건 값은 호출 없는 순수 식.
- 남긴 것: T24 는 설계대로 FAIL(교재에서 은퇴한 `series`·`hole`·`trendline`·`ma` 를 판정식이 그대로 씀). `hole` 의 최근접
  제안이 `donut` 이 아닌 것은 문자열 거리의 한계. 가맹점 이름 꼬리(`( ,2*9*) / / 이용금액` 등)는 72회차 F72-1 영역.

검증: 신규 회귀 `backend/test_imagination_round73_residual.py` 27개. build `--check`·경로 관문·파일 크기 통과. 라이브 탐침
23/24(T24 위), 조건 값·`artist`·`~workspace` 렌더 HTTP 확인. 산출 스크래치 정리 완료.
