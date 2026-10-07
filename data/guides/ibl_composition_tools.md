# IBL 조합 — 도구·문서·재개

[IBL 조합 본편](ibl_composition.md)(값·함수·병렬로 짜는 법)에 이어, 도구와 스크립트를 붙이고
문서를 읽고 결과 미리보기를 다루고 중단된 실행을 이어가는 법이다.
문법 전문: `data/common_prompts/fragments/12_ibl_only.md`.

## 도구·스크립트를 붙이는 법

두 출처의 행은 목록이나 `{items:[...]}`를 그대로 인자로 전달한다.

<!-- example:join_time -->
```ibl
#!ibl edition=2
$매물 = [{id:"a",price:300},{id:"b",price:200}]
$관심 = [{id:"a",memo:"역세권"}]
$결합 = [table:join]{left:$매물,right:$관심,on:"id",how:"left",defaults:{memo:"미검토"}}
$날짜 = [self:time]{format:"%Y-%m-%d"}
return {date:$날짜,items:$결합.items}
```

`join`은 정확히 두 출처를, `merge/union`은 두 개 이상의 출처를 받는다.
`($첫 & $둘 & $셋) >> [table:merge]{by:"id"}` 또는 `inputs:[$첫,$둘,$셋]`도 가능하다.
`left/right`와 `inputs`(파이프 포함)를 함께 지정하지 않는다. 결과는 Record이므로 행은 `.items`로
읽는다. 실패한 분기를 건너뛰어 만든 결과는 부분 결과이며 `source_complete:false`를 유지한다.
`self:time`은 Text를 반환하므로 보고서 제목이나 파일 이름에 바로 쓴다.

병렬 결과는 가지 순서의 목록이다. `$r=문서읽기 & 날짜조회`처럼 서로 다른 형태도
고정 인덱스 `$r[0].text`, `$r[1]`로 꺼내 조합할 수 있다. 목록 리터럴·명시 입력·함수 전달·
목록 연결도 고정 위치의 타입을 보존한다. 동적 인덱스나 순서를 모르는 도구 결과는
원소의 공통 타입으로 검사하므로 모든 원소에 없는 필드를 무조건 읽지 않는다.

`join`의 오른쪽 동명 열은 `_2`부터 사용 가능한 접미사로 구별한다. 이름은 입력 전체의
열을 보고 한 번 정하므로 일부 행에서 왼쪽 필드가 없어도 오른쪽 열 이름이 바뀌지 않는다.
inner 결합의 희소 객체에서 없는 필드는 그대로 없고, 표형 입력의 생략된 후행 셀은 null로
채워 오른쪽 값이 왼쪽 열로 밀리지 않게 한다. `items:`로 표 봉투를 단항 변환자에 넘기면
기존 정규화 계약에 따라 객체 목록으로 바뀌므로 이후에는 `.items`를 읽는다.

`join`의 두 입력과 `table:reduce`의 입력은 객체 행이어야 한다. 잘못된 행이 섞이면
0 기반 위치를 알려주며 계산 전에 거절한다. 행을 몰래 버린 합계·결합 결과를 만들지 않는다.
`table:reduce`의 빈 입력은 `init`을 반환한다. 전체 합계는 `reduce($행,0,($합,$r)=>$합+$r.금액)`으로 쓴다.
`groupby`의 키는 필수다(`by:[]` 불가).

`groupby/dedup/rename/flatten/since/reduce/chunk/ai/brief/judge`도 파이프 입력을 받는다.
이 도구들은 기존 Record 반환을 유지한다. 예를 들어 집계 뒤 정렬은 다음처럼 연결한다:

<!-- example:unary_group -->
```ibl
#!ibl edition=2
$합계 = [{분류:"식비",금액:30},{분류:"식비",금액:20}] >> [table:groupby]{by:"분류",agg:{합계:["sum","금액"]}}
$합계.items >> [table:sort]{by:"합계",descending:true}
```

`chunk`는 평문·목록·봉투를 받아 `.items`로 덩이를 낸다. 빈 문자열·목록은 정상 0건,
`by:"chars"`는 평문·`text`·`field` 본문의 공백도 보존한다. items의 누락·빈 행은
생략 수·원래 인덱스와 `PARTIAL_SOURCE`로 신고하며, catch의 `$error.partial`에도 불완전 표지가 남는다.

`flatten`도 모든 중첩 목록이 비어 있으면 정상 0건을 반환한다. 목록이 아닌 행을 생략하면
`rows_dropped`와 `skipped_row_indices`로 원래 위치를 알린다. `field:"refs"`로 items 봉투를
자동 펼치거나 `field:"refs.items"`로 직접 읽어도 원천의 실패·절단 근거는 `row_honesty`에
남으며 `PARTIAL_SOURCE`로 보고한다. 목록 속 업무 행의 상태 필드는 원천 실패로 판정하지 않는다.

조건부 값이 숫자·문자열·Bool 중 하나여도 `f"${값}"`으로 표시한다.
목록과 문자열 중 하나인 값의 정수 인덱스도 각각의 계약으로 검사하며, 레코드의 동적 문자열 키는
실행 시 필드 존재를 확인한다. null·구조를 문자열로 몰래 바꾸거나 없는 키를 빈값으로 숨기지 않는다.

행 수는 반환 계약에 따라 센다. 목록은 `len($목록)`, `items`를 가진 Record는 `len($봉투.items)`다.
`len($봉투)`는 필드 수여서 행이 없어도 양수일 수 있다. 컴파일러의 `RECORD_LENGTH` 경고는
이 차이를 알리며 필드 수 계산을 거절하거나 행 수로 자동 변환하지 않는다.

`$r=[sense:search]{query:"..."}; $r.items >> ...`처럼 반환 계약에 맞게 명시적으로 연결한다.
`[self:script]{id:"등록이름",args:{...}}`는 기존 등록 스크립트도 직접 실행한다.
등록 id는 기존 JSON stdin을 유지하며 JSON stdout 전체가 값이다. `{items:[...],run:...}`이면 `$r.items`와
`$r.run`을 직접 읽는다. 문자열 JSON을 겹겹이 감싸는 workflow 우회는 필요 없다.
실패·부분 결과는 실행 경계에서 전파하고 원천 누락을 목록 길이로 추측하지 않는다.
미등록 계산: inputs→write/edit→`[self:script]{path:"~turn/분석.py",args:$자료}`.
stdout은 진단, 결과 파일은 값이다. 수정·재현·권한은 [Script 계약](script.md).

신규 관용구는 명시 `[def:이름](...){...}` 전체를 검사한 뒤 기존 workflow 저장 창구에
`edition:2,code:...`로 등록한다. 구형 저장 원문 자체를 조사할 때만
`docs/compatibility/ibl_legacy_language.md`를 읽는다. 새 작업을 구형으로 작성하는 지침이 아니다.

결과는 `value`, 상태는 `success/source_complete`, 진단은 `diagnostic/evidence`다.
보여 준 결과가 짧으면 `result_ref.read_args`로 필요한 필드만 읽는다. 상세 조회를 위해 원래 작업을
재실행하지 않는다.

## 중단 뒤 이어가기와 문서 읽기

`result_ref.input_args`를 `inputs`에 넣으면 코드에서 `$입력`으로 쓴다(이름 변경 가능).
일부 값은 `path:["value","rows"]`로 선택한다. 여러 참조는 `{"반":[{"$ref":a},{"$ref":b}]}`처럼
목록·레코드에 둔다. `inputs:{"$ref":...}`는 이름이 없어 거절된다. 실패 실행 전체 대신
성공 가지는 `partial_reads`, 실패 가지의 불완전 자료는 `failed_partial_reads`를 쓴다.
`read_args`·`input_args`로 조회·재사용한다. `input_unavailable`이면 제한을 따른다.
순차 실패의 완료 호출은 `result_ref.completed_calls[].input_args`, 거절된 입력은
`request_inputs.input_args`로 재사용한다. 실패 호출 인자는 `result_ref.failed_calls[].input_args`,
생략된 참조 목록은 `calls_read_args`로 회수한다([Script 예제](script.md)). 마스킹·불완전성은 유지한다.
원문 판단이 필요할 때만 `read_result`로 읽는다. 그 `input_args`는 표시 페이지가 아닌 선택 경로의 전체 값이다.
`read_scope`는 이번 응답의 경로·문자 범위이고 `format:"text"`는 문자열 원문, `"json"`은 구조 값의 JSON이다.
`complete:true`면 하위까지 전달됐으니 재독하지 않는다. `next_read:null`은 중간 offset에서 읽은 끝 페이지일 수도 있다.

실행 응답의 `resume:{run_id}`와 동일 `code`·`inputs`를 다음 execute_ibl 호출에 보낸다.
완료한 도구 호출은 저장된 값으로 복원한다. 반복의 같은 인자도 서로 다른 호출로 기록한다.
코드·입력·도구 구현이 달라지거나 외부 작업의 완료를 확인하지 못하면 재개하지 않는다.
`RESUME_DIVERGED`의 `details.changed/fingerprints`는 변경 차원의 지문이다. 옛 기록은 `dimensions_known:false`다.
취소 후 finally가 외부 정리를 수행한 경우도 새 작업 계획이 필요하다. 확인된 실패를 몰래 재시도하지 않는다.
회원 기록은 사적 세션의 수명을 따르고, 주인 기록은 백엔드 재기동 후에도 남는다.
코드를 고쳤고 이전 읽기를 이어 쓸 의도라면 `continuation.reuse_args`를 요청에 합친다.
쓰기와 계약·인자·의존성이 바뀐 호출은 재사용하지 않는다.
`table:ai/brief/judge` 성공 결과도 입력·설정이 같으면 자동 재사용한다. `reuse.models:false`는 새 판단이다.
쓰기와 겹치는 이전·동시 읽기는 제외한다(자원 미상은 전체).
`per_run:true`(시계)는 새로 읽는다.
최신 자료는 새로 조회한다. `resume`은 실패도 복원한다.

### 읽기·판정·반환을 한 프로그램에서 연결하기

본문 전체가 아니라 다음 결정에 필요한 검사 결과를 반환한다. 도구 오류는 빈 문서로 바꾸지 않는다.
아래 `complete`는 프로그램이 명시한 두 문서의 존재·비어 있지 않음 조건이며 내용의 정확성 검수는 아니다.
저장 성공을 검사할 때도 먼저 저장 결과의 경로로 다시 읽고 요청한 값과 비교한 뒤 완료를 보고한다.

<!-- example:document_completion -->
```ibl
#!ibl edition=2
[def:문서확인]($경로) {
  [try] {
    $문서 = [self:read]{path:$경로}
    return {path:$경로,confirmed:len($문서.text)>0,chars:len($문서.text)}
  } [catch] {
    return {path:$경로,confirmed:false,error:$error.message}
  }
}
$대상 = ["outputs/source-a.txt","outputs/source-b.txt"]
$확인 = $대상 >> [table:each] { [fn:문서확인]{경로:$it} }
$미완료 = $확인 >> [table:filter]{where:($행)=>not $행.confirmed}
return {complete:len($미완료)==0,checked:len($확인),missing:$미완료,checks:$확인}
```

실행 봉투의 `success:true`와 이 프로그램의 `value.complete:false`는 동시에 성립할 수 있다.
앞은 검사 프로그램의 실행, 뒤는 명시 조건의 달성 여부다. 실행 종료·응답 생성만으로 사용자 목표 달성을 주장하지 않는다.

`self:read`는 확장자/`format`에 따라 `.text`·`.blocks`·`.data`를 반환한다.
본문만 필요하면 `format:"text"`의 `.text`만 반환한다. 위치 탐색은 `output_mode:"files_with_matches"`로 좁힌다.
JSON은 `.data`(배열은 `.data.items`), CSV/TSV는 `.data.items`·`.data.table`(문자열 셀), XLSX/XLS는 `.data.table.rows`를 쓴다.
구조화 파일·오피스는 기본 전체 읽기다. XLSX/XLS의 `max_rows`(헤더 포함)와 문서의 `max_blocks`는 생략·0=전체, 양수=선택이다. 원문은 보존하고 표시만 제한하며 큰 값은 `result_ref`로 잇는다.
`.data.sheets`는 시트명이다. 부분 추출을 확인하며, 파일 부재는 `NOT_FOUND`다.
회원 AI도 같은 문법을 사용하며, 회원 기기에서 받은 자료와 정의만 사용한다.

최종 응답을 받기 전에 연결이 끊겼다면 기존 HTTP 티켓 recover의 `progress.resume` 또는
실행 궤적의 `ibl.checkpoint`에서 시작 시 발행한 run_id를 찾는다. 원래 코드를 새 실행으로 다시 보내지 않는다.

계약 조회는 `describe:["fn:이름"]`으로 저장 함수에도 쓴다. 오류를 고치려고 본문을 읽는 경우를 제외하면
입력·반환·효과·미확정 경계부터 확인한다. 파일 편집·grep·웹 검색·크롤링도 현재의 명시 계약을 제공한다.
grep과 search/crawl의 결과는 Record이므로 목록 조합에는 `.items`, 본문에는 계약에 있는 `.text`를 명시한다.

명시 `inputs`의 이름을 인자로 묶으면 성공 프로그램이 함수 후보가 된다. 개인 값은 복사하지 않고 기존 증류 판단 후 등록하며, 새 입력 검증은 실제 호출에서 쌓는다.

## 후보·본문 미리보기와 전체 값

작은 결과는 그대로, 큰 결과는 예산 내 짧은 필드·여러 행을 표시한다. 여러 문자열이 함께
잘릴 때는 온전한 앞쪽 행을 우선한다. 나머지는 미검토이며 원천 누락과는 다르다.
`_preview.changes`는 생략 경로·전체/표시 수·`read_args`를 제공한다. `changes_omitted`가
양수면 진단도 일부이므로 최상위 read_args로 읽는다. 날짜·이름은 필요한 경로만 더 읽는다.
변수·result_ref.input_args는 전체 값을 유지한다. 조건 필터·필드 선택은 전체 값에 적용해 반환한다.

`evidence_summary`는 내부 도구·원천 실패를 상위 실행 성공과 구분한다. 오류의 `result_ref.read_args`는 진단을 먼저 연다. 가이드 재독 대신 변경 확인은 `read_guide`의 `if_hash`, 특정 절만 재확인할 때는 `section`을 쓴다. 본문이 문맥에서 사라졌으면 전문을 다시 읽는다.
문단 위치는 `self:grep`의 `pattern`·`context`로 찾는다.
액션의 인자가 불명확하면 `describe`의 `callable_contract`와 `target_description`을 함께 본다.
legacy-envelope 액션의 구판 전용 설명에는 소스의 `target_description_edition: 1`을 표시해 새 판본 조회에서 제외한다.
실패의 `diagnostic.details`에 사용 예시·허용 값·hint가 있으면 소스 탐색 전에 이를 확인한다.

## 과거의 긴 문장을 현재 문법으로 옮길 때

호출 이력의 원문을 보존하고 입력·반환·실패 정책을 먼저 확인한다. 자동 봉투 추출은 명시
`.items` 접근으로, `each`의 자동 펼침·부모 필드 승계는 `flat_map`과 명시 필드 복사로 바꾼다.
여러 독립 단계의 결과가 필요하면 마지막에 Record로 모아 반환한다.
`on_error:"collect"`가 만든 Result 목록은 `each` 안의 `is_ok/unwrap`으로 다룬다.
외부 도구의 실패는 catch·fallback으로 값을 반환하거나 영수증으로 재개해도
`source_complete:false` 근거로 남는다. 순수 계산 복구와 구분한다.
실제 개정 이전 원문 12개의 변환·검증 사례는
[긴 문장 재현 보고서](../../docs/experiments/legacy_long_replay_2026_09_25/report.md)를 참고한다.

## 설치된 Python 라이브러리

함수·생성자·객체 메서드는 `[self:script]{id:"python_libraries",args:{...}}`로 호출한다. 함수별 등록이 필요 없으며
객체는 같은 최상위 실행 안에서 전달하고 종료 전에 값/파일로 변환한다.
[직접 호출과 오류 복구 예제](python_libraries.md)를 따른다.

`table:judge`의 null은 미결정이다. false·짝 없음으로 바꾸지 말고 확인 목록으로 남긴다([판정 가이드](judgment.md)).

### CSV·경고·재사용 진단

`$행 >> [self:write]{path:$출력,format:"csv"}`는 특수문자를 인용한다. `columns:["이름","금액"]`은 열 선택·순서이며 빈 입력에 필수다. null/결측은 빈 셀, 중첩 값은 사전 변환한다.
집계 제외 건수는 `aggregation_skips`, 중간 도구 경고는 `.items` 투영 뒤에도 `execution_notes`로 확인한다.
`reuse.skipped`는 미복원 이유·위치·변경 지문 차원(옛 기록은 자료 부재)을 보여준다.
