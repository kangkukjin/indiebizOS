# 상상 훈련 67회차 결과보고서 (2026-09-28) — 2배 훈련·새 공통 값 연산과 Python 호출의 경계

훈련 턴 · **무수정**(가이드 §4-3: 훈련 턴은 라이브 코어를 고치지 않는다). 사용자 요청 "상상훈련을 평상시의 2배로 해서 에러를 찾아줘".

## 축 선정

- 평소 8~12과제 → **24과제**(2배). 24검수·21실행(발신·쓰기·예약 3건은 check만).
- 축 = **09-27 개정으로 새로 들어온 표면**: 공통 값 연산(`9e10bd9f` split·replace·strip·집합·zip·enumerate·any/all·sorted·keys/entries·슬라이싱·`**` 펼침·삼중 따옴표·assert)과 Python 라이브러리 호출(`f0955641` `[self:script]{id:"python_libraries"}`), 줄머리 연산자 이음(`918fc1ee`). 56~66회차 누구도 밟지 않은 밭이다.
- 축 선정 관문 질문("기계로 열거 가능한가"): 새 함수 표면은 열거 가능하지만 **무엇이 결함인지(소수 리터럴·NFD 파일명·numpy 스칼라와의 접점)는 업무 조합에서만 드러났다** — 발견 뒤 census 이관 대상으로 적는다(아래 제안).
- 닫힌 밭(값 표기 격자: `"007"==7`·`"1,000"==1000`은 B46-7 판정)은 탐침에서 재확인만 하고 결함으로 올리지 않았다.
- 도메인 접지: 강의(출석·평점·과제 점수)·부동산(관심 매물·면적)·가족신문(태그·원고)·가계부(분류 합계·구독료)·실제 프로젝트 폴더(`projects/음악`).

## 지표 스냅샷 (훈련 전)

행동 미조합 140/168 · 파이프 길이 중앙값 3 · 문형 4(시간·발신 조합 0) · 파트너 다양성 중앙값 2 · 교재 3,735문장. 원본: [metrics.json](metrics.json). 지표는 몸의 현황이며 훈련 실측은 증류에 안 담긴다(§6).

## 과제 표

원문·기대값: [probe.py](probe.py) · 응답 전량: [before.json](before.json). 모든 요청 `edition:2`·`project_id:"컨텐츠"`·`origin:"training"`.
**45검사 중 37통과 · 8실패**(실패 8 = 결함 7 + 마찰 1).

| # | 상상 의도 | 결과 | 분류 |
| --- | --- | --- | --- |
| T01 | 가족신문 태그 공백 정리·중복 제거 한 줄 | `해외 여행, 강의, 음악` | 깨끗 |
| T02 | 1차시 출석·2차시 결석 학생 (`difference`) | `["나"]` | 깨끗 |
| T03 | 두 차시 모두 출석 (`intersection`) | `["가","다"]` | 깨끗 |
| T04 | 두 사이트 매물 번호 순서 보존 합집합 | `["m1","m2","m3"]` | 깨끗 |
| T05 | 이름·점수 zip → sorted → enumerate 순위 문구 | `["1위 나","2위 다","3위 가"]` | 깨끗 |
| T06 | 강의 평균 평점 3.5를 JSON 문자열로 | **오류 봉투 문자열이 성공 값** | 결함 B67-1 |
| T07 | 학생 평점 4.5 행 목록을 JSON 본문으로 | **오류 봉투 문자열이 성공 값** | 결함 B67-1 |
| T08 | 가계부 분류별 합계 pandas groupby (정수) | 기대값 일치 | 깨끗 |
| T09 | 매물 면적 84.5·59.5 평균 pandas | **`{}` 성공**(면적 열 소실) | 결함 B67-2 |
| T10 | 과제 점수 평균 numpy `result:"value"` | **PY_VALUE_CONVERSION** | 결함 B67-3 |
| T11 | 실제 폴더 `음악` 이름 replace | **`음악` 그대로**(조용한 무변경) | 결함 B67-4 |
| T12 | 폴더명 첫 글자 `$n[0:1]` | **`ᄋ`**(자모 조각) | 결함 B67-4 |
| T13 | 폴더명 글자 수 `len` | **6**(기대 2) | 결함 B67-4 |
| T14 | 가족신문 여러 줄 원고 `f"""…"""` 줄 수 | 3 | 깨끗 |
| T15 | 빈 명단이면 assert로 멈추고 catch 안내 | 기대값 일치 | 깨끗 |
| T16 | 60점 미달을 each collect로 수집 | `[false,true]`·부분 원천 | 깨끗 |
| T17 | 공통 옵션 `{**$기본}`을 take에 재사용 | 기대값 일치 | 깨끗 |
| T18 | 원고 기본 레코드에 상태만 덮어쓰기 | 기대값 일치 | 깨끗 |
| T19 | 주제별 편수 표의 `keys`·요약 문구 | 기대값 일치 | 깨끗 |
| T20 | 줄머리 `>>` 이음 최저가 추천 | 기대값 일치 | 깨끗 |
| T21 | 구독료 19.9 × 3 | `59.699999999999996` | 마찰 F67-1 |
| T22 | 면적 기록 JSON 파일 저장 | 검수 통과 | 검수만 |
| T23 | 결석 안내 메일 | 검수 통과 | 검수만 |
| T24 | 매일 아침 지출 요약 예약 | 검수 통과 | 검수만 |

## 갭의 원장

### B67-1 `json()`이 공개 결과 위반을 **오류 봉투 텍스트로 바꿔 성공 값으로 반환** ★최우선

- **요약**: 소수 리터럴(`1.5`, `3.5`)은 파서가 `Decimal`로 읽는데(`backend/common/expression_parser.py:214`), `json()`은 `json.dumps(public_result(x))`(`backend/common/expression_ops.py:141`)이고 `public_result`는 Decimal을 "JSON으로 표현할 수 없는 값"으로 보고 **`{"success":false,…}` 봉투를 값으로** 돌려준다. `json()`은 그 봉투를 문자열화해 `success:true`로 끝난다. 거짓 성공 부류.
- **최소 재현**: `return json({평균:3.5})`
- **실측**: `value = "{\"success\": false, \"error_code\": \"NON_JSON_RESULT\", \"error\": \"공개 결과 계약 위반: 공개 결과 $.평균의 Decimal 값은 JSON으로 표현할 수 없습니다\"}"`, `success:true`, `source_complete:true`. check도 `valid`.
- **실제 피해 재현**(의도치 않게 실행된 스크래치 쓰기 1건): `$r=[{p:1.5}]; [self:write]{path:"outputs/IT67_x.json",content:json($r)}` → 쓰기 영수증 `success:true`, **파일 내용 = 오류 봉투**. 증거 사본 [evidence_IT67_x.json](evidence_IT67_x.json), 원본은 즉시 삭제.
- **범위**: 연산을 거친 값은 float라 무사(`json({a:1/2})` 정상) — **손대지 않은 소수 리터럴·그것을 담은 레코드**만 걸린다. 교재 예시의 `body:json($r)`·`content:json($r)` 관용 형태가 그대로 해당. 09-23 판본 2 코어(`211fac7e`)부터 잠복(09-27 개정 전에도 같은 코드).
- **제안(수리성)**: ① `json()`은 `public_result`의 위반 봉투를 값으로 삼지 말고 `NON_JSON_RESULT` 실패로 올린다(거짓 성공 차단 — 같은 부류의 다른 호출자도 전수). ② 공개 정규화가 유한 Decimal을 손실 없이 JSON 수로 내보낸다(`value_wire`는 이미 decimal 태그를 가지므로 사람용 JSON은 수 표기로 충분). 가드: 리터럴 소수·중첩 레코드·목록·each 결과·쓰기 본문 경로.

### B67-2 소수 리터럴이 Python에 `Decimal`로 넘어가 pandas/numpy가 **조용히 틀린 결과**

- **요약**: 브리지는 Decimal을 "그대로 보존"한다(가이드 `python_libraries.md`). 그러나 `pandas.DataFrame([{면적:84.5},…])`의 열이 `object` dtype이 되어 `mean(numeric_only=True)`가 그 열을 **제외** → `{}`를 성공으로 반환. `numpy.array([1.5,2.5])`도 `ObjectDType`.
- **최소 재현**: T09 (`{면적:84.5},{면적:59.5}` → mean → to_dict)
- **실측**: `value: {}`, `success:true`, `source_complete:true`. 같은 과제를 정수로 쓰면(T08) 정상.
- **제안(수리성)**: IBL 리터럴의 Decimal은 *정밀도 표기*이지 사용자가 Python `decimal.Decimal` 객체를 요구한 것이 아니다. 브리지 입력 변환 계약을 정하라 — 기본은 float(또는 정수 가능 시 int)로 넘기고, Decimal 객체가 필요하면 `decimal:Decimal` 호출로 명시. B67-1과 같은 뿌리(리터럴 Decimal이 경계 밖으로 새는 곳)의 census: json·Python 브리지·공개 결과·사람용 `value`(현재 `{"$ibl":"decimal","text":"1.5"}` 태그로 보임).

### B67-3 numpy 스칼라를 "손실 없이 표현할 수 없는 객체"로 **거짓 진단**

- **요약**: `data/scripts/python_library/python_bridge_values.py:21-39`의 `value_copy`가 `type(v) is float/int` 정확 비교라 `numpy.float64`(float 하위형)·`numpy.int64`를 거절. 메시지는 무손실 불가라고 하지만 실제로는 무손실이다.
- **최소 재현**: `return [self:script]{id:"python_libraries",args:{op:"call",target:"numpy:mean",args:[[1,2,3]],result:"value"}}`
- **실측**: `PY_VALUE_CONVERSION` "IBL 값으로 손실 없이 표현할 수 없는 객체", partial=`numpy.float64` 참조. `result` 생략 시 ref가 돌아와 `$a+1`이 `NUMBER_REQUIRED`로 실패. 우회 = `receiver:$a,name:"item"` 한 번 더 호출(정상 2.333…).
- **범위**: pandas `Series.sum()`·`df["열"].mean()`·numpy 집계 전반이 스칼라를 numpy 타입으로 돌려준다 — "평균 하나 구하기"마다 호출이 하나 더 필요하다.
- **제안(수리성)**: 유한 numpy 정수/부동 스칼라(`numpy.integer`/`numpy.floating`, `item()`이 무손실인 것)를 기본 값으로 변환. bool·복소수·NaN 거절 규칙은 유지.

### B67-4 NFD 한글(맥 파일명)에서 새 문자열 함수의 **정규화 계약이 둘로 갈림**

- **요약**: `==`·`contains`·`unique`·`intersection`·`dedup`은 NFC로 비교해 NFD `음악`과 NFC `음악`을 같다고 본다. 그런데 `replace`·`strip`·`len`·슬라이싱은 원시 코드포인트로 동작 — 같다고 판정한 문자열에서 replace는 **조용히 아무것도 안 하고**, `len`은 자모 수, 슬라이스는 음절을 쪼갠다.
- **최소 재현**(실제 사용자 데이터): `$d=[self:list]{path:"~workspace/projects"} >> [table:filter]{where:($r)=>contains($r.name,"음악")}; $n=$d[0].name; return {rep:replace($n,"음악","music"), head:$n[0:1], len:len($n), eq:$n=="음악"}`
- **실측**: `{"rep":"음악","head":"ᄋ","len":6,"eq":true}`. 사용자 `projects/` 아래 NFD 이름 **97건**(음악·건축·창업·사진·추천 폴더 자체가 NFD).
- **범위**: `self:list`로 파일명을 읽어 이름 바꾸기·제목 자르기·폭 맞추기를 하는 모든 조합. `strip`/`split` 구분자도 같은 영향 가능.
- **제안(수리성)**: Text 경계(도구 결과→IBL 값, 또는 문자열 함수 입구)에서 NFC 정규화를 한 벌로 — 동등 계약(B46-2 NFC)과 같은 정책을 변환 함수에도. 파일 경로로 되돌려 쓸 때 원 이름이 필요하면 `path` 필드(원문)를 쓰는 규칙을 교재에. 가드: NFD 입력 × {replace, strip, split, len, slice, upper/lower, join, f-string}.

### F67-1 소수 리터럴은 Decimal인데 **첫 산술에서 float로 떨어진다**

- `$단가=19.9; return $단가*3` → `59.699999999999996`, `0.1+0.2==0.3` → `false`, `sum([0.1,0.2])` → `0.30000000000000004`, `round(2.675,2)` → `2.67`. 반면 `text(1.10)`은 `"1.10"`(Decimal 표기 보존).
- 리터럴은 정밀 표기로 들어오지만 연산은 이진 부동소수라 금액 계산에 잡음이 생긴다. B67-1/2와 같은 "Decimal 반쪽 채택" 뿌리. **판정성**: 산술을 Decimal로 유지할지(기존 결과의 수 표기가 바뀜 — 파괴적 변경 가능성) 사용자 판정이 필요하다.

### F67-2 `sorted(목록,"필드")`와 `[table:sort]`의 희소 필드 계약 불일치

- `[{p:3},{id:"x"},{p:1}] >> [table:sort]{by:"p"}` → 결측 행 뒤로(66회차 계약). 같은 자료의 `sorted(…,"p")` → `MISSING_FIELD` 실패. 교재는 sorted에 "비교 불가능한 키는 실패"라고만 적어 결측을 포함하는지 불명. 수리성: 두 정렬 중 하나로 계약을 맞추고 교재에 명시.

### F67-3 `take.n`에 정수값 실수(2.0·`4/2`)를 주면 check는 `valid`, 실행은 `TAKE_COUNT`

- 동등 계약에서는 `2.0==2`인데 take는 거절하고, 검수는 못 잡는다. 수리성: 정수값 실수 수용 또는 검수가 같은 규칙으로 판정.

### G67-1 콜백(순수 식) 안에서 목록 원소별 변환 수단이 없음

- `[table:compute]{set:($r)=>{tags:split($r.t,",") >> [table:each]{strip($it)}}}` → `PURE_EXPRESSION`. 행 안의 태그 목록을 원소별로 정리하려면 compute 밖 each를 겹쳐야 한다. 순수 `map` 계열 내장 함수가 없음. **판정성(언어 개정)**: 새 내장 함수(예: 순수 map) 여부.

## 시드 후보 (실행 검증 통과만 — 자동 등록 안 함)

T01(태그 정리: split→each strip→unique→join) · T02/T03(출석 차집합·교집합) · T05(zip→sorted→enumerate 순위) · T15(assert+catch 안내) · T16(each collect 행별 검증) · T18(기본 레코드 덮어쓰기).

## 판정 요청 (언어 개정·파괴적 변경 2종만)

1. **F67-1** — IBL 산술을 Decimal로 유지할 것인가(금액 정확성 ↑ / 기존 결과 수 표기 변경).
2. **G67-1** — 순수 식 안의 원소별 변환 내장 함수를 추가할 것인가(새 낱말).

B67-1~4·F67-2·F67-3은 수리성 — 다음 수리 턴이 묻지 않고 집행할 몫이다. B67-1·B67-2·F67-1은 같은 뿌리(리터럴 Decimal이 경계에서 새는 자리)이므로 **밭 이관 규약**에 따라 개별 수리보다 "Decimal 경계 census(json·Python 브리지·공개 결과·사람용 value·산술)"를 수리 턴의 첫 항목으로 권한다.

## 위생

- 회차 창(09:50~10:02) `action_health`: 제 요청분은 전부 `training`(dedup·write·groupby·list·script·sqlite). 같은 창의 `usage` 행(scheduler 09:07·agent search·`here`·app dedup 09:51)은 시각·채널상 다른 경로다.
- 스크래치 쓰기 1건(`projects/컨텐츠/outputs/IT67_x.json`)이 탐색 중 check 없이 실행됨 → 내용을 증거로 보존하고 즉시 삭제, 잔존 0 확인. 사용자 데이터 무변경(폴더 목록 읽기만).
- 발신·예약·알림 실측 0. 라이브 코어 편집 0. 해마 시딩 0. 회귀 배터리는 수정이 없어 돌리지 않았다.

## 집행 완료

2026-09-28 정본 수리. 사용자 지시 “필요한 수리를 판단해 진행”에 따라 B67-1~4,
F67-1~3을 수정했다. G67-1은 기존 reduce로 순수 목록 변환이 가능함을 확인해
새 map 내장 함수 대신 실행 가능한 교재 예제를 추가했다.

| 항목 | 적용 결과 |
| --- | --- |
| B67-1 | json()은 엄격 공개 변환의 예외를 실행 실패로 전달한다. 오류 봉투 문자열을 성공 값으로 저장하지 않는다. 소수 목록·레코드·each 결과·실제 임시 파일 본문까지 확인했다. |
| B67-2 | Python 입력의 중첩 Decimal을 십진 표기가 왕복 가능한 유한 float로 전달한다. pandas 면적 평균 72.0, NumPy 소수 집계가 정상이다. Decimal 객체는 decimal:Decimal + result:"ref"로 명시 생성한다. |
| B67-3 | NumPy 정수·유한 실수 스칼라의 item()이 기본 int/float를 반환하면 auto/value에서 값으로 전달한다. bool·복소수·비유한 수·기본 값으로 내보낼 수 없는 고정밀 스칼라는 자동 변환하지 않는다. |
| B67-4 | 문자열 변환·길이·인덱스·슬라이스·보간을 공통 NFC 관점으로 맞췄다. 입력 원문·레코드 키·path는 보존하며 파일 재접근은 원래 path를 사용한다. |
| F67-1 | Decimal 리터럴을 산술·abs·round·min/max/sum에서 유지한다. 19.9×3=59.7, 0.1+0.2==0.3, round(2.675,2)=2.68. 혼합 float는 십진 표기로 변환하고 음수 //·%의 기존 부호 규칙을 유지한다. |
| F67-2 | sorted(list,"field")는 table:sort의 공통 정렬을 사용한다. 일부 결측/null은 뒤로, 전체 필드 부재는 MISSING_FIELD, 빈 목록은 정상이다. 콜백 필드 접근의 오류는 유지한다. |
| F67-3 | take.n은 유한 정수값 Number(2.0·4/2 포함)를 수용한다. 음수·소수 부분이 있는 수는 TAKE_COUNT로 거절한다. |
| G67-1 | compute 순수 콜백 안에서 reduce(split(...),[],($acc,$tag)=>$acc+[strip($tag)])로 변환하는 예제를 교재·실행 검사에 연결했다. |

### Decimal 경계 전수 점검

- 소유 위치는 common/value_semantics.py다. 기존 JSON 도구 인자·공개 결과·json()·Python 입력·사람용 value의 소수 변환이 같은 decimal_json_number를 사용한다.
- 십진 표기가 float 왕복 뒤 달라지는 수(예: 0.10000000000000001)는 숫자로 몰래 반올림하지 않는다. JSON/Python 입력은 명시 실패, 사람용 value는 기존 decimal 태그, value_wire는 원래 Decimal을 보존한다.
- public_result 호출처를 조회했다. 도구/HTTP 최종 경계는 오류 봉투를 반환하는 계약을 유지하고, 사업 데이터 문자열을 만드는 json()만 엄격 예외 모드를 사용한다. {success:false,error:...} 자체가 업무 데이터인 경우에는 정상 직렬화한다.
- 비교·집계·기존 저장 식의 숫자 관측 규칙은 유지한다. 새 산술은 Decimal 입력을 보존하는 공통 관점을 사용한다. Decimal 없는 기존 float 연산까지 임의로 십진 연산으로 바꾸지 않는다.
- Decimal 산술은 기본 28자리 정밀도이며 임의 정밀도의 무한 소수 계산을 보장하지 않는다. NFC도 일반 grapheme 분할 규칙은 아니다.

### 검증

- 원 보고서 재실행: **37/45 → 45/45 통과**. [after.json](after.json). 24과제 중 21실행, 쓰기·발신·예약 3건은 검수만 유지했다.
- 추가 HTTP 검사: **4/4 통과**. [supplemental_after.json](supplemental_after.json).
- 관련 회귀 263건 통과. 실제 JSON 쓰기는 pytest 임시 디렉터리에서 수행했다.
- 회원 공유 기록의 인증·역할·행/필드 접근 경로를 재검토하고 감사 의존 지문을 갱신했다. 회원 기록 회귀 29건 통과.
- 새 예제를 교재 검증 목록에 연결한 뒤 교재 회귀 44건 통과.
- 전체 backend: **7,245 통과·1 건너뜀·6 실패**(700.27초). 실패는 교재 예제 표식 누락 1건, 이전 이진 소수 반올림 기대값 4건, 새 시험의 직접 실행 진입점 누락 1건이다. 모두 보완한 뒤 실패 경로를 포함한 **296건 재검증 통과**(20.37초); XML로 실패 6건 모두 재검증 집합에 포함됨을 대조했다. 전체 재실행은 하지 않았으며 미해결 실패는 없다. [검증 집계](tests.json) · [전체 출력](tests_full.txt) · [재검증 출력](tests_followup.txt).
- 어휘·문서 파생, Android 번들, 층 구조, 은퇴 계약, diff 검사 통과. 제어자를 통한 백엔드 재기동·healthy 확인 및 HTTP 재현 완료.
- 새 어휘·새 내장 함수·해마 시딩·발신·예약 실행 없음. 실제 모델 업무의 전체 시간/토큰 개선률은 측정하지 않았다.
