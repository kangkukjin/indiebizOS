# IBL 조합 — 값·함수로 큰 작업 만들기

정해진 흐름은 프로그램으로 표현하고 판단·검수는 유지한다.
문법 전문: `data/common_prompts/fragments/12_ibl_only.md`.
도구 결합·문서 읽기·결과 미리보기·중단 뒤 이어가기: `read_guide(query="ibl_composition_tools.md")`.

## 부품의 형태와 완료 의미

어휘·등록 스크립트·관용구·드라이버는 현재 계약으로 발견하고 조합한다. 형태 전환은 사용자가
결정하며 빈도로 자동 전환하지 않는다. 계약이 소개에 이미 있으면 같은 설명을 다시 조회하지 않는다.
`contract_known:false`나 생략된 상세는 완료 보장이 아니므로 필요한 정보만 inspect로 확인한다.

실행 성공과 업무 완료를 구분한다. PC·Android 제어 함수는 실패도 정상 값으로 반환할 수 있으므로
`status`·`verified`·검증 범위를 확인한다. pending·unknown은 원 영수증으로 조회하고 변경을
재전송하지 않는다. Safari·Chrome 스크립트의 실패는 catch로 전달된다. 함수를 감싸서 오류를
값으로 바꿀 때는 `$error.details.error_code`·failure·recovery와 원 `$error`를 보존한다.
PC·Android 반환의 `failure.cause`는 원 오류, `failure.recovery`는 구조화된 복구 지시다.
검증 스크립트의 명시 `operation_outcome`은 실행 봉투의 작업 판정이며 업무 값 속 동명 필드를
자동 판정하지 않는다. 선언 판정이 없으면 성공으로 추정하지 않는다. 구체 형식은 `script.md`를 따른다.

## 작성 순서

복잡한 새 일의 기본은 **사용자 요구 → 분해 이유 → 함수별 계약 → 구현 → 최상위 조합**이다.
지역 함수·관용구를 조합하고 반복할 정의만 저장한다. 장문 설명·단계별 모델 호출은 필요 없다.

1. 입력·반환·출처·완료 조건을 정한다. 실제 액션 계약은 `execute_ibl(code="",describe=["node:action"])`으로 조회한다(한 번에 1~6개). `describe`와 코드를 함께 주면 조회 성공 후 한 번 실행하고 `descriptions`를 덧붙인다. `check:true`는 검사만, `read_result`는 단독 조회다.
2. 변수는 값이다. 목록은 `.items/.count`로 감싸지 않고 그대로 전달하며 길이는 `len`으로 구한다.
   Record를 반환하는 도구에만 계약에 맞게 `.items/.text` 등을 사용한다.
3. 독립 실행은 `A & B`, 값 전달은 `A >> B`, 여러 곳에서 쓸 값은 `$이름=A`다. `&`·`>>`·`??`로 시작하는 줄은 앞 식의 계속이다. 산술 연산자는 앞줄 끝에 둔다(`$합=1 +` 다음 줄 `2`). 줄 첫 산술은 SYNTAX다.
   `&`가 `>>`보다 먼저 묶인다. 독립된 파이프 두 개는 `(A >> B) & (C >> D)`, 병렬 결과를 한 곳에 넘길 때는 `(A & B) >> C`로 쓴다. `A >> B & C >> D`는 전자의 뜻이 아니다.
   후속 E가 A와 D만 소비한다면 `((A & D) >> E) & B & C`처럼 필요한 결과끼리 합류한다. 모든 분기를 먼저 모으는 `(A & B & C & D) >> E`는 불필요한 대기를 만든다. 단, 공유 자원·동시 실행 한도·일관성 때문에 필요한 대기는 유지한다. 겹침 기록을 만들기 위한 인위적 시작 장벽은 두지 않는다.
   `$a=A; $b=B; $a & $b`는 A·B를 먼저 순차 실행한다. `&`는 자동으로 목록을 펼치지 않는다.
4. 함수는 `[def:이름]($인자,$선택=기본값){...}`로 정의하고 `[fn:이름]{인자:값}`으로 부른다.
   의미 있는 하위 작업마다 입력·반환·실패·외부 효과를 정하고 구현한 뒤, 마지막에 전체 흐름을 조합한다.
   첫 인자가 파이프 자리다. 모든 외부 의존은 인자로 받는다. `return`은 즉시 반환한다. 저장·등록 없이 실행된다.
5. 빈값·실패·입력 규모·재개를 설계한 뒤 `check:true`로 검사하고, 통과하면 `execute_args` 그대로 실행한다(원문·`inputs`·`budget` 보존 — 적은 인자만 전체 교체).
   오류는 `issues`를 모아 `location`(원문·정의 속 위치), `call_path`, `expected/actual`, `hint`로 고친 뒤 전체를 재검사한다. `revise_args`가 있으면 `code_edits`로 조각만 고친다. 참조가 원래 inputs·budget·edition과 읽기 재사용을 복원한다. 검사만 하려면 check:true, 새 조회는 reuse:null을 명시한다.
   `warnings`의 반복 AI 입력은 의도를 확인한다. `incomplete`는 실행 중 검사할 타입·도구 경계가 있다는 뜻이다.
   `PROJECT_CONTEXT` 경고는 요청에 프로젝트 문맥이 없어 파일 액션이 첫 호출에서 거절된다는 사전경고다 — HTTP `/ibl/execute`는 body에 `project_id`를 넣는다.
   명시한 프로젝트 ID가 해소되지 않으면 다른 프로젝트로 폴백하지 않는다. HTTP는 `PROJECT_NOT_FOUND`로 실행 전에 거절하므로 ID를 바로잡는다.
   `UNOBSERVED_FIELD`는 관측된 반환 필드 밖의 이름이다 — `describe`의 `observed_returns`나 작은 실행으로 실제 필드를 본 뒤 쓴다.
6. 읽기 후 실패의 `revise_args`는 기존 읽기를 자동으로 이어 쓴다. 참조 없이 원문을 수정할 때는 응답 `continuation.reuse_args`의 키를 요청 최상위에 합쳐(`reuse:{run_id:…}`) 같은 읽기·성공 모델 결과를 재사용한다(조건: `ibl_composition_tools.md` 「중단 뒤 이어가기」).
   단계별 입력 연결은 [분할 예제](long_sentence_imagination.md#비싼-추출-결과를-반환한-뒤-계산표현을-바꾸기)를 따른다.
   `$ref`는 출처·불완전성을 보존하며 `evidence($입력)`으로 확인한다.

`check:true`의 `functions`와 `describe:["fn:이름"]`은 컴파일러가 계산한 함수 계약을 제공한다.
입력·필수 인자·반환에 더해 첫 파이프 인자(`pipe_input`), 기본값 식(`default_expressions`),
전이적으로 호출하는 도구(`actions`)와 가능한 효과(`effects`)를 확인할 수 있다. 기본값 식은
설명용 원문이며 데이터 값으로 자동 변환하지 않는다. 함수 내부의 실패 위치는 실행 진단의
`call_path`로 확인한다. 회상과 정의 펼침은 같은 호출 줄·관측 반환 표시를 사용하고 저장된
적용 조건을 함께 보여준다. 업무의 완료 조건은 프로그램에 명시하며 계약 조회가 대신 판정하지 않는다.

관용구 반환: 목록은 그대로, Record는 계약의 필드로 읽는다.
실행 상태는 `success`·`diagnostic`, 업무 값은 `value`, 손실 없는 값은 `value_wire`에 있다.
값 조회·재전달은 `result_ref.read_args`·`input_args`를 사용한다. 함수 실패 위치는
진단의 `call_path`에서 확인한다. 표시 사본을 원문으로 취급하거나 원문 조회 때문에 도구를 재실행하지 않는다.

모델 도구는 현재 문법이 기본이다. 아래 저장 가능한 예제의 `#!ibl edition=2`는 실행 의미를
고정하는 파일 헤더다. HTTP·CLI·저장 원장에서도 같은 의미로 실행한다. 원시 HTTP는 헤더 또는 요청 `edition:2`로 원문 형식을 명시한다.
`describe` 단독 조회는 다음 실행의 판본을 바꾸지 않는다. 설명·실행을 함께 요청하면 같은 판본을 쓴다. 외부 데이터는 `inputs`로
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
`+`는 양쪽이 모두 Text일 때만 이어 붙이기다. 숫자를 문자열에 이으려면 `text()`로 명시한다 — 문자+숫자는 숫자 연산으로 검사돼 `NUMBER_REQUIRED`다(2026-10-27 실측).
조건·`?:`·and/or·람다 본문·기본값은 순수 식 자리다. 순수 계약의 도구·함수·파이프를
직접 조합한다. 외부 읽기·쓰기·모델·미확정 효과는 이 자리에서 거절하며 객체로 감싸도
숨길 수 없다. 제어 블록은 앞 문장이나 함수 본문에 둔다.

람다 안에서도 `$행 >> [table:take]{n:2}` 같은 순수 변환을 쓴다. `reduce`는 누적 계산에 쓴다. 술어 함수는 `[def:큰가]($n){return ($r)=>$r.n > $n}`처럼 람다를 반환하고
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
레코드·목록·함수 반환의 Callable도 `$ops.f(-2)`, `$ops[0](-2)`, `[fn:선택]{}(-2)`로
직접 호출한다. 입력·반환 계약은 전달 뒤에도 보존한다. `-2 >> abs()`는 `abs(-2)`,
`값 >> $f(다른값)`은 `$f(값,다른값)`이며 명명 도구 인자는 선언된 파이프 자리를 쓴다.
조건 값의 가지 안 파이프는 괄호로 묶는다. 호출 계약 미상은 `incomplete`로 보고한다.
함수 값 자체는 JSON 저장·외부 반환 대상이 아니므로 실행 결과를 저장한다.

콜백은 본문이 사용하는 바깥 변수만 생성 시점의 값으로 보관한다. 중첩 콜백의 변수도
같은 규칙을 따르며, 나중에 바깥 변수를 재대입해도 이미 만든 콜백의 값은 바뀌지 않는다.
`each`의 `on_error:"collect"`로 얻은 성공 결과 안에 함수가 있어도 실행 내부에서
`unwrap`으로 꺼내 다시 사용할 수 있다. 함수가 들어 있는 결과 목록 자체를 JSON이나
외부 결과로 전송하지 않고, 함수를 적용해 얻은 일반 값을 반환한다.

`each`의 `parallel`·`mode`·`on_error`는 컴파일 시점 리터럴이다(`STATIC_OPTION`). 입력 변수로 바꿀 수 없으므로, 폭을 바꿔 돌리려면 요청을 조립하는 단계에서 리터럴을 치환한다(2026-10-27 실측).
병렬 each 안의 효과 미상 호출(`[self:script]{path}` 등)은 실행에서 거절된다(검사 경고 `PARALLEL_RESOURCE_UNKNOWN`) — 순차로 돌리거나 효과를 선언한 등록 스크립트([Script 계약](script.md))를 쓴다. 가지별 다른 파일에 쓰는 병렬은 경로가 글자로 정해져야 한다(`"a_"+$it`·`f"a_${$it}"`, 정수 항목도 됨). 평문 `"a_{$it}"`는 보간이 아니라 글자다(`LITERAL_BRACE` 경고, 2026-10-28).

## 3. 빈값과 실패는 별개

<!-- example:empty -->
```ibl
#!ibl edition=2
$후보 = []
[if:len($후보)==0] { return [{status:"대상 없음"}] }
[else] { $후보 >> [table:select]{columns:["id"]} }
```

빈 목록·빈 문자열·null은 정상 값이다. `??`는 잡을 수 있는 실패만 대체한다.
`get($레코드,"키",기본)`의 기본값은 키 부재에만 쓰인다 — 키가 있고 값이 null이면 null이 돌아오고, 그 값을 다음 `get`에 넣으면 `RECORD_REQUIRED`로 거절된다. null 가능 값은 `== null` 삼항으로 가른다(2026-10-27 실측).

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

오류 전체에 `json($error)`를 적용하면 `partial`의 Unit·함수 때문에 보고서 작성도 실패할 수 있다.
JSON 보고용 필드는 **catch 안에서** 선택한다(try 성공값과 오류의 합타입을 바깥에서 투영하지 않는다).
부분값 생략은 명시하고, 원형 오류도 필요하면 아래처럼 별도 값으로 반환해 실행 응답의
`value_wire`·결과 참조로 보존한다. Unit을 null이나 성공값으로 바꾸지 않는다.

<!-- example:catch_json_report -->
```ibl
#!ibl edition=2
[try] { [1,0] >> [table:each] { assert $it>0,"positive required" } }
[catch] {
  $report={code:$error.code,kind:$error.kind,message:$error.message,
    has_partial:$error.has_partial,partial_preserved:false,evidence:$error.evidence}
  return {report_json:json($report),original_error:$error}
}
```

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
`mode:"flat_map"`은 반환 목록을 한 겹만 펼친다(each의 방식이며 식 함수 `flat_map()`은 없다 — 순수식에서는 `reduce($행,[],($모음,$r)=>$모음 + $r.목록)`). 임의 `limit`으로 전건 처리 요구를 줄이지 않는다.
샘플이 목적일 때만 앞에서 take/filter한다. 원문 분할은 원문 위치·순서·모든 조각을 보존하며,
AI 호출의 입력 한도와 마지막 통합의 크기도 계산한다. 작업이 크면 저장 영수증을 기준으로
단계를 이어 가고 이미 성공한 쓰기·수집을 재실행하지 않는다.
공유 예산은 기본 100만 단계·1만 반복 행·깊이 64다. steps는 평가한 식·문장·내장 작업량이다.
람다 변환은 행당 여러 단계를 쓴다. 요청 `budget:{steps:3000000,rows:20000}`로 조정한다(최대 1,000만·10만; 기본 100만·1만).
`check`는 인자만 검증한다. `usage`는 합계, 예산 20%↑면 `steps_by_line`, 10초↑면 `tool_ms_by_line`(줄별 도구 시간 `ms`=호출 합, 병렬로 겹쳤으면 `wall_ms`=실제 기다린 시간) 3줄(전문=`read_result` `["usage"]`).
BUDGET의 소진 차원·사용량·한도를 보고
도구 필터나 여러 실행으로 나눈다. `number(value)` 해석 실패는 잡을 수 있는 오류다. `number(value, null)`처럼 실패값을 명시하면 순수 map/filter 식에서도 안전하게 변환한다. null은 0이 아니며 집계 전에 분리한다. fallback 인자도 먼저 평가하므로 인자 계산 오류를 숨기지 않는다.

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
문자열 비교·탐색·길이·슬라이싱 위치는 NFC 기준이며 반환은 원문 조각을 보존한다.
replace가 일치하지 않거나 split→join을 되돌리면 NFD 원문이 그대로 남는다.
치환문·연결·보간도 입력 표기를 유지한다. 결합 구간 내부를 가르면 경계 조각만 NFC로 반환한다.
contains($본문,"\r")는 실제 CR 유무를 검사하며 빈 검색어는 참이다.
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
값으로 정한 키는 `from_entries(map($행,($r)=>[$r.key,$r.value]))`로 레코드를 만든다(`{[$k]:…}` 문법은 없음). 입력은 두 원소 쌍의 목록·Text 키만 허용하고 빈 목록은 `{}`, 중복 키는 실패다. 키 원문·순서를 보존하며 선택 키는 `has/get`으로 조회한다. 내부 조회용 색인이나 JSON·API 본문에 쓸 수 있고, 행 처리는 `{key:$k,value:…}` 목록으로 이어간다.
assert는 작성한 조건을 실제 결과에 대해 검사하며 조건 자체의 충분성은 별도 판단이다.
메시지와 상세 값은 실패 때만 평가한다. 큰 본문은 삼중 따옴표로 쓰되,
이미 있는 본문은 파일/결과 참조로 연결하고 다시 생성하지 않는다.

## 문자열 동등성과 레코드 조회 키를 구별하기

문자열 `==`와 `unique`는 NFC/NFD를 같은 값으로 보지만, 레코드의
`get/has/[]`·`from_entries`·`**`는 **원문 키**를 보존하고 그대로 조회한다.
`"부산" == "부산"`이어도 `get({부산:1},"부산",0)`은 0이다.
`==`·`unique`는 대소문자·공백·숫자 표기도 관측 동등성으로 합칠 수 있다.
`groupby`의 그룹 키, `join/dedup`의 관계 키는 각 액션 계약을 확인한다.
업무 이름을 그대로 레코드 색인으로 쓰면 집계는 맞아도 근거 목록이 갈라질 수 있다.

업무에서 NFC/NFD만 합쳐야 한다면 원문별 별칭을 공통 번호로 연결하고,
양쪽 자료의 집계·조인·근거 색인에 같은 번호를 사용한다. 표시 이름과 파일 path는 원문을 남긴다.
아래 지역 함수는 같은 실행 안의 대응표다. 빈 입력은 빈 대응표이며,
대소문자·공백·문자열 숫자 코드는 서로 다르다. 번호는 입력 순서에 따르므로 실행 사이의 영속 ID로 쓰지 않는다.

<!-- example:record_key_aliases -->
```ibl
#!ibl edition=2
[def:같은표기]($a,$b) { return len($a)==len($b) and contains($a,$b,true) }
[def:키색인]($names) {
  $spellings=keys(reduce($names,{},($acc,$name)=>{**$acc,**from_entries([[$name,true]])}))
  $names=reduce($spellings,[],($acc,$name)=>any(map($acc,($key)=>[fn:같은표기]{a:$key,b:$name})) ? $acc : $acc+[$name])
  $indexed=enumerate($names)
  return {names:$names,aliases:from_entries(map($spellings,($name)=>[$name,filter($indexed,($pair)=>[fn:같은표기]{a:$pair[1],b:$name})[0][0]]))}
}
$색인=[fn:키색인]{names:["부산","부산","A","a"]}
return {names:$색인.names,aliases:$색인.aliases}
```

`같은표기`는 NFC 길이와 대소문자를 구별하는 부분 일치를 함께 검사하여 NFC/NFD만 합친다.
두 부산 표기는 번호 0, A와 a는 각각 1과 2다. 입력 전체에서 한 번 대응표를 만들고
행 처리에서는 `get($색인.aliases,$원문)`으로 조회한다. 등록하지 않은 원문을 0으로 대체하지 않는다.
복합 번호를 레코드 키로 쓸 때는 `json([$sku_key,$warehouse_key])`처럼 경계를 보존한다.
이 예제의 대응표 작성은 고유 표기×고유 이름을 비교하므로 고유 이름이 많은 자료는
실행 예산·시간을 확인한다. 각 행마다 전체 전표를 다시 검색하는 방법으로 바꾸지 않는다.

## 평면 기록의 내용 동일성과 정확한 ID로 묶기

같은 실행·과금 ID의 중복과 충돌을 가를 때 먼저 업무의 동일성 기준을 정한다.
`json(레코드)`의 문자열만 비교하면 필드 순서가 다른 같은 기록도 충돌이 된다.
반대로 `unique`·관계 키의 동등성은 원문 대소문자·숫자 표기를 합칠 수 있으므로
정확한 ID나 원문 내용의 동일성을 대신하지 않는다.

아래 비교는 **값이 문자열·숫자·불리언·null인 평면 레코드**용이다. 필드 순서는 무시하고,
필드 이름·문자열 원문·타입·부재와 null은 구분한다. JSON 스칼라 표현을 레코드 키로 조회하므로
문자열 동등 비교의 정규화를 적용하지 않는다. 중첩 객체의 일반 정규화 함수로 쓰지 않는다.

<!-- example:flat_record_identity -->
```ibl
#!ibl edition=2
[def:평면기록같음]($a,$b) {
  return len(keys($a))==len(keys($b)) and reduce(keys($a),true,($same,$key)=>$same and has($b,$key) and has(from_entries([[json($a[$key]),true]]),json($b[$key])))
}
return [fn:평면기록같음]{a:{id:"A",tokens:3},b:{tokens:3,id:"A"}}
```

정확한 문자열 ID로 반복 조회할 때는 레코드의 원문 키 계약으로 한 번 묶는다.
아래 예제는 `A`와 `a`를 분리하고, 같은 ID의 행은 버리지 않고 입력 순서대로 모두 보존한다.
필요한 집계·충돌 판정을 각 묶음에서 수행하면 항목마다 전체 목록을 다시 필터하지 않아도 된다.
레코드는 불변이므로 누적도 복사 비용이 있다. 큰 입력에서 단계·시간을 측정하며 무조건 빠르다고 단정하지 않는다.

<!-- example:exact_key_groups -->
```ibl
#!ibl edition=2
[def:원문ID로묶기]($rows) {
  $index={}
  [repeat:len($rows)] {
    $row=$rows[$i];$key=$row.id
    $index={**$index,**from_entries([[$key,get($index,$key,[])+[$row]]])}
  }
  return $index
}
return [fn:원문ID로묶기]{rows:[{id:"A",n:1},{id:"a",n:2},{id:"A",n:3}]}
```

## 그룹마다 가장 좋은 후보 하나를 고르기

각 대상의 `each` 안에서 후보 전체를 다시 `filter`하면 대상 수×후보 수만큼 훑는다.
비교 규칙이 같다면 전체를 한 번 정렬하고 `dedup`의 첫 행 유지 계약으로 그룹별 대표를 고른다.
아래는 비용→날짜→ID의 순서를 보존한다. 동률 기준을 모두 적어 입력 순서에 기대지 않는다.

<!-- example:group_best -->
```ibl
#!ibl edition=2
$후보=[{group:"a",cost:20,days:2,id:"x"},{group:"a",cost:10,days:3,id:"y"},{group:"b",cost:10,days:1,id:"z"}]
$대표=$후보 >> [table:sort]{by:["cost","days","id"]} >> [table:dedup]{by:"group"}
$색인=from_entries(map($대표.items,($r)=>[$r.group,$r]))
return map(["a","b","c"],($key)=>{group:$key,choice:get($색인,$key,null)})
```

`c`처럼 후보가 없는 대상도 원래 대상 목록에서 복원한다. `dedup`은 키의 공백·대소문자를
정규화하므로 원문을 구별해야 하는 식별자는 그 동등성 계약부터 확인한다. 입력의 선택 필드는
`get($행,"price",null)`처럼 명시적으로 읽고 누락을 분류한다. 파일 재독 일치는 원자료와의
독립 대조를 대신하지 않는다. 조건 변경에는 같은 원자료의 `reuse:{run_id:...}` 읽기 영수증을
사용할 수 있으며, 재사용·변경 감지 내역을 확인한다.

## 근거 발췌와 짧은 산출물

문서를 발췌해 판단 모델에 넘길 때는 줄 번호뿐 아니라 절 제목과 생략 범위도 보존한다.
키워드 주변 몇 줄에 제목이 없다고 원문에 절이 없다고 판단할 수는 없다. 판정에 필요한
문맥이 빠졌으면 그 범위만 보완하며, 기본값·기능 유무·구현·실기 검증을 같은 주장으로 합치지 않는다.
짧은 산출물을 요청받았다면 핵심 결론·근거·미확인을 유지하면서 설명 중복을 줄인다.
변형의 원본 보존은 기존 파일과 참조를 유지하는 것이며, 요청하지 않은 원본 전문을 다시 생성하지 않는다.
