# IBL 조합 — 값·함수로 큰 작업 만들기

이 문서는 현재 IBL의 주 작성 교재다. 도구마다 AI가 다음 호출을 다시 작성하기보다,
정할 수 있는 데이터 흐름을 하나의 프로그램으로 표현한다. 필요한 내용 판단·검수는 유지한다.
문법 전문은 `data/common_prompts/fragments/12_ibl_only.md`다. 별도 신판 교재를 찾아 선택하지 않는다.

## 작성 순서

1. 입력·반환·출처·완료 조건을 정한다. 실제 액션 계약은 `execute_ibl(code="",describe=["node:action"])`으로 조회한다.
2. 변수는 값이다. 목록은 `.items/.count`로 감싸지 않고 그대로 전달하며 길이는 `len`으로 구한다.
   Record를 반환하는 도구에만 계약에 맞게 `.items/.text` 등을 사용한다.
3. 독립 실행은 `A & B`, 값 전달은 `A >> B`, 여러 곳에서 쓸 값은 `$이름=A`다.
   `$a=A; $b=B; $a & $b`는 A·B를 먼저 순차 실행한다. `&`는 자동으로 목록을 펼치지 않는다.
4. 함수는 `[def:이름]($인자,$선택=기본값){...}`로 정의하고 `[fn:이름]{인자:값}`으로 부른다.
   첫 인자가 파이프 자리다. 모든 외부 의존은 인자로 받는다. `return`은 즉시 반환한다.
5. 빈값·실패·입력 규모·재개를 설계한 뒤 `check:true`로 검사하고 같은 프로그램을 실행한다.
   확정 오류는 `source_span`으로 고친다. `incomplete`는 실행 중 검사할 타입·도구 경계가 있다는 뜻이다.

모델 도구는 현재 문법이 기본이다. 아래 저장 가능한 예제의 `#!ibl edition=2`는 실행 의미를
고정하는 파일 헤더다. HTTP·CLI·저장 원장에서도 같은 의미로 실행한다. 외부 데이터는 `inputs`로
명시하며 앞 호출의 변수를 자동 상속하지 않는다. 문자열은 그대로이고 `f"${값}"`만 보간한다.

## 1. 순수 계산을 한 흐름으로

<!-- example:pipeline -->
```ibl
#!ibl edition=2
$접수 = [{id:"a",score:3},{id:"b",score:7},{id:"c",score:5}]
$접수 >> [table:filter]{where:($행)=>$행.score >= 5} >> [table:sort]{by:"score",descending:true} >> [table:select]{columns:["id","score"]}
```

결과는 `[{id:"b",score:7},{id:"c",score:5}]`다. 반환 목록은 `value`에서 읽는다.
조건을 문자열이나 `{field,op,value}`로 다시 해석하지 않는다. 콜백도 일반 식과 같은 규칙이다.

## 2. 함수·관용구·병렬을 함께 조합하기

<!-- example:compose -->
```ibl
#!ibl edition=2
[def:통과점수]($목록,$최소,$배수) {
  $통과 = $목록 >> [table:filter]{where:($행)=>$행.score >= $최소}
  $상위 = [fn:정렬해추리기]{목록:$통과,기준:"score",내림차순:true,열:["id","score"],개수:2}
  $상위 >> [table:each] { return {id:$it.id,score:$it.score,weighted:$it.score * $배수} }
}
$출처별 = [table:take]{items:[{id:"a",score:3},{id:"b",score:7}],n:2} & [table:take]{items:[{id:"c",score:5}],n:1}
$합 = $출처별 >> [table:each]{mode:"flat_map"} { return $it }
[fn:통과점수]{목록:$합,최소:5,배수:2}
```

결과는 b(7,14), c(5,10)다. 최소를 99로 바꾸면 빈 목록이다. 이 예제의 `정렬해추리기`는
현재 명시 인자·목록 반환으로 등록된 관용구다. 필요한 관용구의 이름과 반환 계약만 읽고 호출한다.
수정할 때 해당 정의만 펼친다. 본문을 매번 재작성하거나 같은 이름의 지역 함수에서 자신을 호출하지 않는다.

기존 등록 함수도 같은 `[fn:이름]` 자리에서 해소된다. 기존 함수가 반환하는 봉투는 그대로이므로
모양을 확인해 값을 선택한다. 새 정의는 명시 인자·값 반환으로 작성한다.

## 3. 빈값과 실패는 별개

<!-- example:empty -->
```ibl
#!ibl edition=2
$후보 = []
[if:len($후보)==0] { return [{status:"대상 없음"}] }
[else] { $후보 >> [table:select]{columns:["id"]} }
```

빈 목록·빈 문자열·null은 정상 값이다. `??`는 잡을 수 있는 실패만 대체한다.

<!-- example:catch -->
```ibl
#!ibl edition=2
[try] { [sense:crawl]{url:"https://example.org/bad"} }
[catch] { return {status:"원문 확인 실패",reason:$error.message} }
```

실패를 빈 목록으로 바꾸어 조회 성공으로 보고하지 않는다. 원천 부분 실패·권한·취소·예산·프로토콜의
경계는 문법 전문을 따른다. 조건은 Bool이어야 하며 판정할 수 없는 값을 false로 추측하지 않는다.

## 4. 실패한 항목만 재시도하기

<!-- example:retry -->
```ibl
#!ibl edition=2
$주소 = [{id:"a",url:"https://example.org/one"},{id:"b",url:"https://example.org/bad"}]
$첫읽기 = $주소 >> [table:each]{parallel:2,on_error:"collect"} {
  $문서 = [sense:crawl]{url:$it.url}
  return {id:$it.id,text:$문서.text}
}
$주소 >> [table:each] {
  [if:is_ok($첫읽기[$i])] { return unwrap($첫읽기[$i]) }
  [else] {
    [try] {
      $문서 = [sense:crawl]{url:$it.url}
      return {id:$it.id,text:$문서.text}
    } [catch] { return {id:$it.id,error:$error.message} }
  }
}
```

첫 성공은 다시 읽지 않는다. 실패 항목만 한 번 더 읽고 끝까지 실패한 ID와 이유를 반환한다.
`on_error:"collect"`는 각 입력의 성공/실패를 `Result`로 보존한다. 성공값은 `unwrap`, 실패는
`error_of`로 읽는다. 복구해도 앞선 실패의 증거는 지우지 않는다. 외부 쓰기·누적·결제에는
이 패턴을 무조건 적용하지 말고 해당 동작의 멱등 키·저장 영수증부터 확인한다.

## 5. 전건 처리와 명시적인 펼침

<!-- example:chunk -->
```ibl
#!ibl edition=2
$덩이 = [[{index:0,text:"가나"},{index:1,text:"다라"}],[{index:2,text:"마바"}]]
$덩이 >> [table:each]{mode:"flat_map",parallel:2} {
  $it >> [table:each] { return {index:$it.index,text:$it.text,chars:len($it.text)} }
} >> [table:sort]{by:"index"}
```

기본 each는 모든 입력당 결과 하나를 내므로 목록을 반환하면 중첩 목록이 된다.
`flat_map`은 반환 목록을 한 겹만 펼친다. 임의 `limit`으로 전건 처리 요구를 줄이지 않는다.
샘플이 목적일 때만 앞에서 take/filter한다. 원문 분할은 원문 위치·순서·모든 조각을 보존하며,
AI 호출의 입력 한도와 마지막 통합의 크기도 계산한다. 작업이 크면 저장 영수증을 기준으로
단계를 이어 가고 이미 성공한 쓰기·수집을 재실행하지 않는다.

## 도구·스크립트를 붙이는 법

`$r=[sense:search]{query:"..."}; $r.items >> ...`처럼 반환 계약에 맞게 명시적으로 연결한다.
`[self:script]{id:"등록이름",args:{...}}`는 기존 등록 스크립트도 직접 실행한다.
기존 JSON stdin을 유지하며 JSON stdout 전체가 값이다. `{items:[...],run:...}`이면 `$r.items`와
`$r.run`을 직접 읽는다. 문자열 JSON을 겹겹이 감싸는 workflow 우회는 필요 없다.
실패·부분 결과는 실행 경계에서 전파하고 원천 누락을 목록 길이로 추측하지 않는다.

신규 관용구는 명시 `[def:이름](...){...}` 전체를 검사한 뒤 기존 workflow 저장 창구에
`edition:2,code:...`로 등록한다. 구형 저장 원문 자체를 조사할 때만
`docs/compatibility/ibl_legacy_language.md`를 읽는다. 새 작업을 구형으로 작성하는 지침이 아니다.

결과는 `value`, 상태는 `success/source_complete`, 진단은 `diagnostic/evidence`다.
보여 준 결과가 짧으면 `result_ref.read_args`로 필요한 필드만 읽는다. 상세 조회를 위해 원래 작업을
재실행하지 않는다. 기능 시험의 외부 응답은 고정하며 실제 웹·AI 품질을 통과했다고 주장하지 않는다.


## 중단 뒤 이어가기와 문서 읽기

실행 응답의 `resume:{run_id}`와 동일 `code`·`inputs`를 다음 execute_ibl 호출에 보낸다.
완료한 도구 호출은 저장된 값으로 복원한다. 반복의 같은 인자도 서로 다른 호출로 기록한다.
코드·입력·도구 구현이 달라지거나 외부 작업의 완료를 확인하지 못하면 재개하지 않는다.
취소 후 finally가 외부 정리를 수행한 경우도 새 작업 계획이 필요하다. 확인된 실패를 몰래 재시도하지 않는다.
회원 기록은 사적 세션의 수명을 따르고, 주인 기록은 백엔드 재기동 후에도 남는다.

`self:read`는 확장자로 텍스트·PDF·Office를 구분하며 `.text`, `.blocks`, `.data`를 반환한다.
PDF의 `pages`·`tables`, XLSX의 `sheet`·`max_rows`를 현재 문법에서 지정한다.
표와 시트 등 형식별 결과는 `.data.table`, `.data.sheets`처럼 읽고 부분 추출 표지도 확인한다.
회원 AI도 같은 문법을 사용하며, 회원 기기에서 받은 자료와 정의만 사용한다.

최종 응답을 받기 전에 연결이 끊겼다면 기존 HTTP 티켓 recover의 `progress.resume` 또는
실행 궤적의 `ibl.checkpoint`에서 시작 시 발행한 run_id를 찾는다. 원래 코드를 새 실행으로 다시 보내지 않는다.


계약 조회는 `describe:["fn:이름"]`으로 저장 함수에도 사용할 수 있다. 오류를 고치려고 본문을 읽는 경우를 제외하면
입력·반환·효과·미확정 경계부터 확인한다. 파일 편집·grep·웹 검색·크롤링도 현재의 명시 계약을 제공한다.
grep과 search/crawl의 결과는 Record이므로 목록 조합에는 `.items`, 본문에는 계약에 있는 `.text`를 명시한다.

명시 `inputs`를 사용하는 성공 프로그램은 입력 이름을 인자로 묶어 재사용 함수 후보가 될 수 있습니다. 개인 입력값을 본문에 복사하지 않으며, 기존 증류의 가치 판단을 통과한 경우에만 등록합니다. 새 입력에 대한 검증 실적은 이후 실제 호출에서 쌓입니다.
