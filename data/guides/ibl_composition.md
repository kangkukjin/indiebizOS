# IBL 조합 — 값·함수로 큰 작업 만들기

정해진 흐름은 프로그램으로 표현하고 판단·검수는 유지한다.
문법 전문: `data/common_prompts/fragments/12_ibl_only.md`.
도구 결합·문서 읽기·결과 미리보기·중단 뒤 이어가기: `read_guide(query="ibl_composition_tools.md")`.

## 작성 순서

복잡한 새 일의 기본은 **사용자 요구 → 분해 이유 → 함수별 계약 → 구현 → 최상위 조합**이다.
지역 함수·관용구를 조합하고 반복할 정의만 저장한다. 장문 설명·단계별 모델 호출은 필요 없다.

1. 입력·반환·출처·완료 조건을 정한다. 실제 액션 계약은 `execute_ibl(code="",describe=["node:action"])`으로 조회한다(한 번에 1~6개). `describe`와 코드를 함께 주면 조회 성공 후 한 번 실행하고 `descriptions`를 덧붙인다. `check:true`는 검사만, `read_result`는 단독 조회다.
2. 변수는 값이다. 목록은 `.items/.count`로 감싸지 않고 그대로 전달하며 길이는 `len`으로 구한다.
   Record를 반환하는 도구에만 계약에 맞게 `.items/.text` 등을 사용한다.
3. 독립 실행은 `A & B`, 값 전달은 `A >> B`, 여러 곳에서 쓸 값은 `$이름=A`다. `&`·`>>`·`??`로 시작하는 줄은 앞 식의 계속이다. 산술 연산자는 앞줄 끝에 둔다(`$합=1 +` 다음 줄 `2`). 줄 첫 산술은 SYNTAX다.
   `&`가 `>>`보다 먼저 묶인다. 독립된 파이프 두 개는 `(A >> B) & (C >> D)`, 병렬 결과를 한 곳에 넘길 때는 `(A & B) >> C`로 쓴다. `A >> B & C >> D`는 전자의 뜻이 아니다.
   `$a=A; $b=B; $a & $b`는 A·B를 먼저 순차 실행한다. `&`는 자동으로 목록을 펼치지 않는다.
4. 함수는 `[def:이름]($인자,$선택=기본값){...}`로 정의하고 `[fn:이름]{인자:값}`으로 부른다.
   의미 있는 하위 작업마다 입력·반환·실패·외부 효과를 정하고 구현한 뒤, 마지막에 전체 흐름을 조합한다.
   첫 인자가 파이프 자리다. 모든 외부 의존은 인자로 받는다. `return`은 즉시 반환한다. 저장·등록 없이 실행된다.
5. 빈값·실패·입력 규모·재개를 설계한 뒤 `check:true`로 검사하고, 통과하면 `execute_args` 그대로 실행한다(원문·`inputs`·`budget` 보존 — 적은 인자만 전체 교체).
   오류는 `issues`를 모아 `location`(원문·정의 속 위치), `call_path`, `expected/actual`, `hint`로 고친 뒤 전체를 재검사한다. 긴 원문은 `revise_args`의 `code_edits`로 조각만 고친다.
   `warnings`의 반복 AI 입력은 의도를 확인한다. `incomplete`는 실행 중 검사할 타입·도구 경계가 있다는 뜻이다.
   `PROJECT_CONTEXT` 경고는 요청에 프로젝트 문맥이 없어 파일 액션이 첫 호출에서 거절된다는 사전경고다 — HTTP `/ibl/execute`는 body에 `project_id`를 넣는다.
   명시한 프로젝트 ID가 해소되지 않으면 다른 프로젝트로 폴백하지 않는다. HTTP는 `PROJECT_NOT_FOUND`로 실행 전에 거절하므로 ID를 바로잡는다.
   `UNOBSERVED_FIELD`는 관측된 반환 필드 밖의 이름이다 — `describe`의 `observed_returns`나 작은 실행으로 실제 필드를 본 뒤 쓴다.
6. 수정 실행은 `continuation.reuse_args`로 같은 읽기·성공 모델 결과를 재사용한다(조건: `ibl_composition_tools.md` 「중단 뒤 이어가기」).
   단계별 입력 연결은 [분할 예제](long_sentence_imagination.md#비싼-추출-결과를-반환한-뒤-계산표현을-바꾸기)를 따른다.
   `$ref`는 출처·불완전성을 보존하며 `evidence($입력)`으로 확인한다.

`check:true`의 `functions`와 `describe:["fn:이름"]`은 컴파일러가 계산한 함수 계약을 제공한다.
입력·필수 인자·반환에 더해 첫 파이프 인자(`pipe_input`), 기본값 식(`default_expressions`),
전이적으로 호출하는 도구(`actions`)와 가능한 효과(`effects`)를 확인할 수 있다. 기본값 식은
설명용 원문이며 데이터 값으로 자동 변환하지 않는다. 함수 내부의 실패 위치는 실행 진단의
`call_path`로 확인한다. 회상과 정의 펼침은 같은 호출 줄·관측 반환 표시를 사용하고 저장된
적용 조건을 함께 보여준다. 업무의 완료 조건은 프로그램에 명시하며 계약 조회가 대신 판정하지 않는다.

관용구 반환: 목록은 그대로, Record는 계약의 필드로 읽는다.
`final_result`·`results` 실행 봉투는 값과 분리한다. 값 조회·재전달은 `result_ref.read_args`·`input_args`,
중간 진단은 `evidence($값).events`의 `attachments.execution_ref.read_args`를 쓴다(재실행 없음).
`failure_origin`의 `input_shape`는 입력 필드 불일치(책임 미확정), `unknown`은 원인 미확정,
`definition`은 확인된 정의 구문 오류다. 입력/미확정 실패는 실행 실패로 남기되 정의 실패 점수에서 제외한다.

모델 도구는 현재 문법이 기본이다. 아래 저장 가능한 예제의 `#!ibl edition=2`는 실행 의미를
고정하는 파일 헤더다. HTTP·CLI·저장 원장에서도 같은 의미로 실행한다. 외부 데이터는 `inputs`로
명시하며 앞 호출의 변수를 자동 상속하지 않는다. 문자열은 그대로이고 `f"${값}"`만 보간한다.
문자열 안의 줄바꿈은 `\n` 또는 삼중 따옴표로 작성한다. 긴 본문은 코드에 다시 적기보다
`inputs:{본문:"…"}`에 값으로 전달해 `$본문`을 쓰거나 기존 파일·결과 참조로 연결한다.
`STRING_LITERAL`은 이 작성 경계를 안내한다. `VALUE_PROTOCOL`이 최소 프로그램에서도 반복되면
문법을 바꾸거나 구판으로 전환하지 말고 실행 기반 오류로 보고한다.

## 처음 보는 작업을 지역 함수로 분해하기

**사용자 요구**: 두 구매안의 품목별 금액과 합계를 계산하고, 각 안이 예산 안에 드는지 알려 달라.
수량·단가·예산은 같은 통화의 0 이상 숫자로 제공됐다고 가정한다. 실제 가격 수집·통화 변환은 별도 계약이 필요하다.

**분해 이유**: 품목 계산·내역 생성·예산 판정의 입력과 결과가 달라 분리한다. 계산 규칙은 공유한다.
한 번만 쓰더라도 복잡한 책임은 함수로 나누되, 단순 호출마다 감싸지는 않는다.

**함수별 계약**:

| 지역 함수 | 입력 | 반환 | 실패·효과 |
| --- | --- | --- | --- |
| 금액계산 | id·수량·단가를 가진 행 | id·금액 | 필수 필드·타입 오류 전파, 외부 효과 없음 |
| 내역작성 | 품목 행 목록 | 순서를 보존한 금액 행 목록 | 항목 실패 시 중단, 빈 입력은 빈 목록 |
| 예산검토 | 품목 행 목록·예산 | 내역·합계·예산이내 | 하위 실패 전파, 빈 내역의 합계는 0 |

**구현과 최상위 조합**: 세 지역 정의와 호출을 하나의 프로그램으로 보낸다.
마지막 호출에서 `예산검토 → 내역작성 → 금액계산`을 실행한다.

<!-- example:local_decomposition -->
```ibl
#!ibl edition=2
[def:금액계산]($행) {
  return {id:$행.id,금액:$행.수량 * $행.단가}
}
[def:내역작성]($목록) {
  $목록 >> [table:each] { [fn:금액계산]{행:$it} }
}
[def:예산검토]($목록,$예산) {
  $내역 = [fn:내역작성]{목록:$목록}
  $합계 = reduce($내역,0,($합,$행)=>$합 + $행.금액)
  return {내역:$내역,합계:$합계,예산이내:$합계 <= $예산}
}
return {
  첫안:[fn:예산검토]{목록:[{id:"a",수량:2,단가:30},{id:"b",수량:1,단가:50}],예산:100},
  둘째안:[fn:예산검토]{목록:[{id:"c",수량:1,단가:80}],예산:100}
}
```

첫안은 합계 110·예산이내 false, 둘째안은 80·true다. 실제 외부 입력은 `inputs`로 받고
지역 함수에 명시적으로 전달한다. 다음 실행은 이전 실행의 지역 정의·변수를 자동 상속하지 않는다.
같은 프로그램에서 저장 없이 반복 호출한다.

도구를 쓰는 작업도 이 구조를 따른다. 수집·변환·판단·산출 중 필요한 책임을 함수로 나누고,
도구 반환 계약을 확인해 연결한다. 독립적인 수집은 `&`, 입력별 처리는 `each`, 새로운 의미 판단은
필요한 AI 호출로 표현한다. 외부 효과·실패·부분 원천은 함수로 감싸도 사라지지 않는다.
탐색 결과에 따라 계획 자체가 바뀌어야 하면 그 경계에서 결과를 확인하고 나머지를 구성한다.
아직 모르는 도구·자료·판단을 지어내어 한 프로그램을 완성하지 않는다.

## 1. 순수 계산을 한 흐름으로

<!-- example:pipeline -->
```ibl
#!ibl edition=2
$접수 = [{id:"a",score:3},{id:"b",score:7},{id:"c",score:5}]
$접수 >> [table:filter]{where:($행)=>$행.score >= 5} >> [table:sort]{by:"score",descending:true} >> [table:select]{columns:["id","score"]}
```

결과는 `[{id:"b",score:7},{id:"c",score:5}]`다.
조건을 문자열이나 `{field,op,value}`로 다시 해석하지 않는다. 콜백도 일반 식과 같은 규칙이다.

`sort`의 기준 필드가 비어 있지 않은 입력의 모든 행에 없으면 `MISSING_FIELD`로 실패한다.
열 이름을 바꾼 뒤에는 정렬 기준도 새 이름으로 지정한다. 일부 행의 필드 부재·null은
기존 규칙대로 뒤에 놓으며, 빈 목록은 정상 빈 목록으로 유지한다. 기준이 없는 자료를
원래 순서대로 돌려주어 후속 `take`가 잘못된 추천을 만들지 않는다.

**객체 필드·배열 원소·호출 인자에 함수·도구 호출과 조합을 넣을 수 있다.**
작성 순서대로 값을 완성하며, 중첩 인자를 먼저 계산한 뒤 바깥 함수를 실행한다.
자동 병렬은 없고 `&`로 명시한다. 실패하면 뒤의 값은 실행하지 않으며 완료된 쓰기를 롤백하지 않는다.
같은 실행의 `resume`은 완료 영수증을 재사용하고, 완료 불명 호출은 재실행하지 않는다.

<!-- example:container_record -->
```ibl
#!ibl edition=2
$목록 = [{url:"https://example.org/board"},{url:"https://example.org/news"}]
return {apps:($목록 >> [table:filter]{where:($행)=>$행.url == "https://example.org/board"})}
```

위 예제는 URL 일치 검사다. 부분 검색은 `contains(문자열,부분문자열)`(세 번째 인자 true면
대소문자 구분), `in`은 목록 원소 검사다.
연산·내장 함수 인자·보간도 값 자리라 호출·`>>`를 그대로 쓴다: `sum($행 >> [table:each]{return $it.n})`.
조건·`?:`·and/or·람다 본문·기본값은 순수 식 자리다. 객체로 감싸도 호출을 숨길 수 없으며
먼저 변수에 받는다. 제어 블록은 앞 문장이나 함수 본문에 둔다. 호출 규칙은 위치와 무관하다.

람다 안의 목록 변환은 §10의 `reduce` 예제를 쓴다. 효과 없는 `[fn:이름]`은 람다·조건에서도
부를 수 있다. 술어 함수는 `[def:큰가]($n){return ($r)=>$r.n > $n}`처럼 람다를 반환하고
`$술어=[fn:큰가]{n:2}`를 먼저 실행한 뒤 `where:$술어`로 넘긴다.

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

내장 함수도 함수 값으로 전달할 수 있다. 직접 호출과 같은 인자 수·오류·실행 예산 검사를 거친다.

<!-- example:builtin_callable -->
```ibl
#!ibl edition=2
[def:보정]($점수,$함수=abs) { return $함수($점수) }
$결과 = [-7,3] >> [table:each] { [fn:보정]{점수:$it} }
return $결과
```

결과는 `[7,3]`이다. 한 원소 목록도 `[abs]`, `[true]`, `[null]`처럼 쓴다.
레코드·목록에서 꺼낸 함수는 `$f=$ops[0]`처럼 변수에 받은 뒤 `$f(...)`로 호출한다.
함수 값 자체는 JSON 저장·외부 반환 대상이 아니므로 실행 결과를 저장한다.

콜백은 본문이 사용하는 바깥 변수만 생성 시점의 값으로 보관한다. 중첩 콜백의 변수도
같은 규칙을 따르며, 나중에 바깥 변수를 재대입해도 이미 만든 콜백의 값은 바뀌지 않는다.
`each`의 `on_error:"collect"`로 얻은 성공 결과 안에 함수가 있어도 실행 내부에서
`unwrap`으로 꺼내 다시 사용할 수 있다. 함수가 들어 있는 결과 목록 자체를 JSON이나
외부 결과로 전송하지 않고, 함수를 적용해 얻은 일반 값을 반환한다.

## 3. 빈값과 실패는 별개

<!-- example:empty -->
```ibl
#!ibl edition=2
$후보 = []
[if:len($후보)==0] { return [{status:"대상 없음"}] }
[else] { $후보 >> [table:select]{columns:["id"]} }
```

빈 목록·빈 문자열·null은 정상 값이다. `??`는 잡을 수 있는 실패만 대체한다.

선택 파일은 목록에서 존재를 확인한 뒤 읽는다. 필수 파일에는 이 분기를 쓰지 않는다.
아래 결과는 `found`로 부재와 빈 파일을 구별한다. 목록·읽기의 실패는 그대로 전파한다.

<!-- example:optional_file -->
```ibl
#!ibl edition=2
$파일 = [self:list]{path:"outputs",pattern:"optional.json"}
[if:len($파일)==0] { return {found:false,text:""} }
[else] { $문서=[self:read]{path:$파일[0].path}; return {found:true,text:$문서.text} }
```

<!-- example:catch -->
```ibl
#!ibl edition=2
[try] { [sense:crawl]{url:"https://example.org/bad"} }
[catch] { return {status:"원문 확인 실패",reason:$error.message} }
```

원천 요청 한도는 `$error.code`=`RATE_LIMITED`(대기 초 `$error.details.retry_after`).
catch/finally는 실패 직전의 변수 값을 읽는다(try 안 재대입도 롤백하지 않음). 실패 전에 대입됐는지
불확실한 새 변수는 복구 코드에서 쓰지 말고 try 전에 초기화한다. 모든 경로가 return한 뒤의 문장은 반환형에 섞이지 않는다.

실패를 빈 목록 성공으로 보고하지 않는다. 부분 실패·권한·취소·예산·프로토콜 경계는 문법 전문을 따른다.
조건은 Bool이며 판정할 수 없는 값을 false로 추측하지 않는다.

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
공유 예산은 기본 10만 단계·1만 반복 행·깊이 64다. steps는 평가한 식·문장·내장 작업량이다.
람다 변환은 행당 여러 단계를 쓴다. 요청 `budget:{steps:300000,rows:20000}`로 조정한다(최대 100만·10만).
`check`는 인자만 검증한다. `usage`는 합계, 예산 20%↑면 `steps_by_line`, 10초↑면 `tool_ms_by_line`(줄별 도구 시간 `ms`=호출 합, 병렬로 겹쳤으면 `wall_ms`=실제 기다린 시간) 3줄(전문=`read_result` `["usage"]`).
BUDGET의 소진 차원·사용량·한도를 보고
도구 필터나 여러 실행으로 나눈다. `number()` 해석 실패는 null이 아니라 잡을 수 있는 오류다.

## 반복으로 목록 누적하기

반복으로 제목을 모을 때도 `+`는 목록 연결이며, 숫자 계산으로 바뀌지 않는다.
while의 `$i`는 지금 실행할 회차의 0 기반 번호다. until은 본문에서 만든 값을 조건에서 읽을 수 있다.
횟수 식은 반복 진입 전에 평가하고, 안쪽 반복을 마치면 바깥 `$i`가 복원된다.

<!-- example:loop_accumulate -->
```ibl
#!ibl edition=2
$제목 = ["기초", "실습", "심화", "보충"]
$목차 = []
[repeat:while $i < 3] { $목차 = $목차 + [$제목[$i]] }
return $목차
```

결과는 `["기초","실습","심화"]`다. 0회 실행될 수 있는 while·동적 횟수 반복은 결과 변수를
위처럼 먼저 초기화한다. until 또는 고정 양수 횟수 반복에서 모든 진행 경로가 정의한 변수는
반복 뒤에서도 사용할 수 있다. 콜백·함수 인자는 별도 범위이고 each는 바깥 변수를 재바인딩하지 않는다.

## 10. 값 가공과 완료 조건을 한 프로그램으로

이미 얻은 값의 분리·정렬·제외·합성에는 식 함수를 쓴다. 레코드의 열/키 관계 연산은
기존 table 어휘를 사용한다. 값 의미와 근거는 공유한다.
아래는 새 항목 제외·정렬·인자 재사용·명시 검증을 묶은 분야 중립 예제다.

<!-- example:value_revision -->
```ibl
#!ibl edition=2
[def:제외하고정렬]($후보,$처리됨) {
  return sorted(difference($후보,$처리됨))
}
$기본 = {후보:split("c a b a"),처리됨:["b"]}
$결과 = [fn:제외하고정렬]{**$기본}
assert len($결과)==2, "처리 결과 수가 다릅니다", {actual:len($결과),expected:2}
return {목록:$결과,앞쪽:$결과[:1],표시:join(", ",$결과)}
```

`split/replace/strip/upper/lower/contains`는 Text를 받는다. `join(구분자,문자열목록)`으로 합친다.
`unique/union/intersection/difference`는 순서 보존 목록 연산이며 집합 타입을 만들지 않는다.
`zip/enumerate`의 각 행도 목록이다. `any/all`은 Bool 목록을 받으며,
`sorted($행,"점수",true)` 또는 `sorted($행,($r)=>$r.점수)`로 키를 지정한다.
필드 이름 정렬은 `table:sort`와 같다(결측/null 행은 마지막, 전 행에 필드가 없으면 실패).
콜백의 누락 필드 접근은 오류다.
문자열 변환·길이·슬라이싱은 NFC를 사용해 맥의 NFD 한글도 음절 단위로 다룬다.
파일 접근에는 목록이 반환한 원래 `path`를 사용한다.

`map`은 변환, `filter`는 Bool 필터다. 콜백은 순수식이며 공통 예산을 쓴다.
`groupby`를 호출하는 순수 지역 함수도 콜백 안에서 쓸 수 있다.
`groupby.agg` 자체는 콜백을 받지 않는다. `{합계:["sum","금액"]}`처럼
count/sum/avg/min/max 집계 명세를 전달한다. JSON 도구 인자 안에 함수를 넣으면
`ARGUMENT_CONTRACT`의 `details.path`가 지원하지 않는 콜백 위치를 가리킨다.
<!-- example:pure_list_transform -->
```ibl
[{t:" 강의 , 음악 "}] >> [table:compute]{set:($r)=>{
  tags:map(filter(split($r.t,","),($tag)=>len(strip($tag))>0),($tag)=>strip($tag)),
  amount:format_number(1234.5,",.2f")
}}
```
조건에 따른 값은 `조건 ? 값1 : 값2`다(조건은 Bool, 고르지 않은 가지는 실행 안 함):
`등급:$r.점수 >= 90 ? "A" : $r.점수 >= 80 ? "B" : "C"`.
소수 리터럴은 산술에서도 십진수로 유지된다. `19.9*3`은 59.7이며
`json([{면적:72.5}])`는 실제 숫자가 담긴 JSON을 만든다.
떨어지지 않는 몫은 실수 근사값이다(자릿수는 `round`). 긴 정확 소수는 JSON 숫자가
못 돼 오류다(`text()`).
`table:filter`는 레코드 행, `filter`는 문자열·숫자·목록도 받는다.
`format_number`는 f/%·선택 쉼표·소수 0~28자리이며 중간값은 짝수 반올림이다.
`keys/values/entries`로 레코드를 열거한다. `**` 펼침은 뒤 필드 우선이고 중복 명시 키는 오류다.
값으로 정한 키로 레코드를 만드는 문법(`{[$k]:…}`)은 없다 — `{key:$k,value:…}` 행 목록으로 두고 `groupby`·`sorted`로 다룬다.
assert는 작성한 조건을 실제 결과에 대해 검사하며 조건 자체의 충분성은 별도 판단이다.
메시지와 상세 값은 실패 때만 평가한다. 큰 본문은 삼중 따옴표로 쓰되,
이미 있는 본문은 파일/결과 참조로 연결하고 다시 생성하지 않는다.
