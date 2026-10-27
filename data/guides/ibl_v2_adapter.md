# IBL 사전 어댑터 작성


## 선언과 검증

어휘를 새로 늘리지 않고 원천 YAML의 `callable_contract`에 version/params/required/pipe_input/result/effects/adapter를 선언한다.
빌더와 런타임은 같은 validator를 사용한다. callable_contract는 현재 IBL이 소비한다. 기존 returns/flow는 저장 원문 호환 실행을 위해 유지한다.
두 판본의 입력 의미가 달라지는 경우 하나를 다른 하나로 자동 파생하지 않는다(예: where 문자열과 순수 Callable).
도구 성공·실패·원천 절단을 선언된 외부 봉투에서만 해석하고 사용자 value/items 안의 동명 키는 건드리지 않는다.
JSON 봉투를 선언한 도구는 실패도 `success:false,error,error_type`으로 반환한다. 예외를 평문으로 바꾸면 어댑터가 실제 실패를 형식 오류로 오진한다. `error_type`·`errno`는 TOOL 진단의 details로 보존하고 permission은 폴백으로 삼키지 않는다. 본문 속 `Error:` 문자열은 오류로 추측하지 않는다.
0/1/N건, Unit, 실제 파일/프로세스, 부분 실패·권한·취소·재생 및 기존 호출 회귀를 시험한다.
지원 범위와 예제는 주 교재 ibl_composition.md와 문법 전문에 함께 갱신하며, 추가 계약은 build_ibl_nodes.py로 파생한다.

실행 계약과 연결된 범위는 [주 IBL 교재](ibl_composition.md)를 함께 읽는다.

기존 저장 관용구를 연결할 때는 기존 본문의 파이프 입력 자리 판정도 계약에 보존한다.
첫 파이프의 맨몸 자유 변수만 `pipe_input`이 되며, 인자 순서로 추측하지 않는다.
명시 인자와 파이프가 같은 자리에 들어가면 실행 전에 거부한다.

여러 출처를 결합하는 도구는 `flow.input_bundle_param`을 `callable_contract.pipe_input`에
연결하고, 묶음과 개별 입력을 두 스키마(`params`, `callable_contract.params`)에 모두 선언한다.
`required_any`는 대안, `requires`는 함께 필요한 인자, `exclusive`는 동시에 줄 수 없는 인자를
선언한다. 검사와 실행 모두 파이프로 주입되는 입력까지 포함해 판정한다.
빌드는 pair/same-kind flow의 입력 연결과 컨테이너 타입 누락을 거부한다.

파이프 입력은 자연스러운 주 입력이 있는 액션에만 선언한다. `self:grep`은 `pattern`,
`self:mkdir`는 `path`다. 전자는 명시 계약의 `pipe_input`, 후자는 기존 `pipe_text`를 사용하며
레지스트리·describe·검사·실행은 해소된 같은 계약을 읽는다. 설정만 받는 조회(`self:time.format`)는
입력 자료의 흐름이 아니며, `self:move`의 source/destination과 op마다 입력이 달라지는 도구는
임의로 첫 인자를 택하지 않는다. 목록을 Text로 몰래 바꾸지 않는다.
명시 인자와 파이프의 0/1/N건·빈값·타입 오류·부분 실패 근거를 같은 경계에서 검사한다.

순수 계약의 도구는 조건·람다·기본값과 파이프에서도 호출할 수 있다. pure는 실패 불가를 뜻하지
않으며 권한·예산·취소·실행 근거를 우회하지 않는다. 값 전용 표현 호스트는 계속 도구를 실행하지 않는다.

단항 `flow.accepts: items/prose` 계열도 명시 `pipe_input`을 선언한다. 기존 봉투 어댑터의
`adapter.input_envelopes: [items]`는 그 입력 슬롯의 Record 또는 JSON Record가 원천 상태를
담은 봉투임을 선언한다. 목록 자체와 목록 안 업무 필드는 상태로 해석하지 않는다.
변환 중 잎 도구가 입력을 행 목록으로 바꾸더라도 어댑터가 원래 입력의 실패·원천 누락을
반환값과 함께 보존한다. 의도한 선택(`scope: selection`)은 불완전 원천과 구별한다.
반환은 기존 Record를 유지한다. `result`에 `items: List<Record>`를 선언하면 주요 행 연산은
봉투를 직접 받으며, 목록과 봉투가 갈리는 분기도 같은 규칙으로 해석한다.
필드 없는 `Record` 선언은 행 목록을 보장하지 않는다. 실제 출력에 맞게 반환 계약을 보강하고,
유도 계약의 정적 검사는 어휘의 통화 선언(`ops.returns` 우선, 없으면 액션 `returns`)이 items인 호출을
`items` 봉투로 해소한다(실행 반환 검사는 그대로). 스칼라 관측이 있으면 관측이 이긴다. 그래서 op별
통화가 액션 기본과 다르면 `ops.returns`에 정직하게 적는다 — 상속된 거짓 items는 `.items` 없는 조합을 통과시킨다.
행이 아닌 값이 섞인 분기는 명시적으로 처리한다. 내부 프로토콜 이름을 바꿀 필요는 없다.
빌드는 단항 입력 자리와 봉투 근거 연결이 빠진 선언도 거부한다.

정상 반환이 평문인 기존 잎 도구는 **성공이 확정된 반환 지점**에서 `ibl_edition.text_result`로
현재 판본의 실행 봉투를 만든다. 기존 판본은 원래 문자열을 유지한다. JSON처럼 생긴 본문이나
`Error:`로 시작하는 업무 텍스트를 상태로 해석하지 않도록 JSON 판정보다 먼저 감싼다.
실패 반환에 이 함수를 쓰거나 공통 어댑터에서 모든 문자열을 성공으로 받아서는 안 된다.
결합에서 건너뛴 분기는 공통 정직 표지 `branches_skipped`와 완료 증거로 보존한다.

JSON 도구 경계의 Decimal은 십진 표기가 JSON 숫자 왕복 후 동일할 때만 숫자로 투영한다.
일반 좌표는 그대로 전달하며 고정밀 값의 손실·비유한 수·큰 정수·Unit/Result는 거절한다.
필요한 명시 문자열화는 text()로 한다. 투영은 사본이고 IBL 값·지문은 원래 타입을 유지한다.
표시 예산으로 고른 브라우저 요소와 요청 limit을 충족한 검색 표본은 scope:selection을
선언한다. 실제 수집 누락/실패는 source 또는 실패로 보존하며 selection으로 덮지 않는다.

모델 표시의 `_preview.scope:display`는 실행·원천 완전성을 바꾸지 않는다. 원문 값과
타입 전송은 저장소에 유지하고, 표시에서 잘린 목록·필드·문자열은 경로별 read_args로
읽는다. 생산자의 content_selection은 HTML 본문 영역 선택이며 문서 전체 검토의 증명이 아니다.

원천별 제한은 `variants.when`과 `minimum`/`maximum`/`integers`/`integer_values`/`nonempty`로 선언한다. 리터럴·목록·같은 순차 블록에서 확정된 바인딩과 유계 수치 산술은 실행 전에, 동적 값은 호출 직전에 같은 계약으로 검사한다. 예: source=zigbang의 limit 최대 50. 상한 초과를 조용히 자르지 않는다.

등록 Script의 `ibl-script-session/1`은 실행 소유 워커에 네이티브 값을 전달하며 JSON 도구 인자 투영을 거치지 않는다.
ForeignRef는 공통 타입/wire이고 공급자가 실행 소유권을 검사한다. stateful 어댑터의 영수증은
새 실행에 재생하지 않는다. 세션 스크립트는 제한 없는 주인의 로컬 코드 실행 권한을 별도 검사한다.

새 `truncated` 생산 위치에는 `truncation-scope: 분류 — 사유`를 적는다(정직 표지 관문 C). 명시 상한·실효 상한·충족 건수는 `common.currency.bounded_selection`로 판정한다. 기본·안전 상한·미충족·수집 오류는 selection으로 덮지 않는다. 시계나 파일 목록·검색처럼 매 실행 다시 관측해야 하는 읽기 계약은 `per_run:true`로 새 실행의 재사용에서 제외한다. 같은 실행의 resume은 기록을 복원한다. 명시 계약은 그 안에, 유도 계약은 액션 루트에 `per_run`을 선언한다. 기존 검색 결과만으로 새 항목·이전 불일치 항목의 변화까지 검증할 수 없다.

읽기·쓰기 범위를 알면 `read_resources`·`write_resources: {file: 인자}`로 선언한다.
명시 `callable_contract`는 그 안에, 기존 봉투에서 계약을 유도하는 액션은 액션 루트에 둔다.
별칭은 액션 `aliases` 한 곳에 선언하며 자원 판정 전 정규 인자로 해소된다.
파일의 대체 출력 이름까지 포함해야 하면 `{file: {param: output, fallback: path, parent: true}}`로
출력 인자(없으면 원본)의 부모 디렉터리를 보수적으로 선언한다. 외부 조회의 복합 키는
`{legal: [query, id, target, page, limit, search_scope]}`처럼 선언 인자 목록을 쓴다.
인자 이름과 값 함께 해시하므로 같은 텍스트의 query와 id, 서로 다른 페이지를 구분한다.
컴파일러와 실행 원장이 같은 선언 해소 함수를 쓰며, 선언 값 미상은 재사용 가능으로 추정하지 않는다.
예: `table:chart`의 `write_resources: {file: output_path}`. 확장자 없는 출력 경로도
PNG/HTML 형식으로 그 경로 자체에 저장하므로 실제 쓰기 범위와 선언이 일치한다.
경로 생략·bare 파일명 등 실제 해소를 보장하지 못하는 경우는 보수적으로 전체 충돌을 유지한다.
`continuation.read_exclusions`는 쓰기 때문에 재사용 후보에서 빠진 호출을 원인 쓰기별로
묶어 최대 20건 표시한다(`read_exclusions_total`은 원인 그룹 전체 수).
각 항목은 `reason`(`unknown_write_resources`/`overlapping_write`), `write_call_id`,
`action`, `location`, `excluded_calls`를 담는다. 저장된 원장에도 남아 같은 실행 재개 후 유지된다.

`integers`는 정수 표현만, `integer_values`는 1.0처럼 정수로 정확히 관측되는 값도 허용한다. 인자 타입 검사는 별도로 유지한다. 분기·반복·함수 경계에서는 상수 바인딩을 추측하지 않고 실행 시 검사한다.

부분 성공을 제공하는 기존 봉투는 `adapter.partial_value_path`로 실패 시 보존할 값 경로를 선언한다. 빈 경로는 전체 봉투다. 실패는 성공으로 바뀌지 않으며 오류의 `partial`에 보존하고 원장·catch에도 전달한다. 권한·접수 대기·프로토콜 실패에는 적용하지 않는다. `sense:search`는 성공한 items·실패한 errors·sections를 함께 보존하므로 실패 검색어만 재시도할 수 있다.


## 자동 병렬 실행 선언

callable_contract의 `execution: {concurrency: reentrant}`는 동일 구현의 동시 호출을
허용하는 선언이다. 기본은 serial이며 효과가 pure/read_external인 경우에만 API 도구
묶음의 자동 병렬 후보가 된다. 선언 전에 서로 다른 입력·이미지·오류·공유 자원의 혼입을
회귀로 확인한다. 작성자의 선언만으로 검증을 대신하지 않는다. affinity는 자원 공유를
나타내지만 현재 자동 실행기는 순차로 처리한다. 명시적 IBL `&`의 기존 의미는 바꾸지 않는다.
중첩 프로그램은 실행할 검사 계획의 효과를 검사하며, 미상·동적 코드·재개는 자동 병렬에서
순차 장벽이다. 단독 호출에는 병렬 판정을 위한 추가 컴파일을 하지 않는다.

## 실측 기록 (자동 누적)

> 실행 에이전트가 턴 종료 후 덧붙인다.
- 2026-10-27 실측: handler_contract로 유도한 계약은 수리 전에는 어휘의 `returns: items`·`ops.returns` 선언을 읽지 않고 반환을 필드 없는 Record로 두었다. 이 때문에 행 목록 판정은 관측 기록 `data/ibl_return_shapes.json`에만 의존했다.
- 2026-10-27 실측: `data/ibl_return_shapes.json`은 git에서 추적하지 않는 실행 관측 기록이고 fixture가 있는 op만 담는다. 그래서 사본이나 새 설치에서는 미관측 op의 행 연산(예: `sense:book→take`, `sense:weather→filter`)이 거절된다. 수리 전 사본에서 재현해 확인했다.


## 실행 내부 부품 참조

선언된 어휘는 `&[node:action]`으로 참조하고 `$op{이름:값}`으로 적용한다.
직접 호출과 같은 정규화·조건부 계약·receiver·실행 관문을 사용한다. 참조 생성은
도구 실행·승인 발급이 아니며, 권한은 `authorize`와 기존 잎 라우팅이 호출마다 확인한다.
분석은 전달된 Callable의 잠재 효과와 실제 호출 효과를 구분한다. 값 콜백은 pure를 요구한다.
명명 함수와 람다는 같은 컴파일 내부 분석 요약을 공유하고, 간접 호출도 현재 호출 위치·
반복 경로에 독립 영수증을 갖는다. 대상/캡처 신원은 요청 지문에 포함된다.
Callable은 실행 내부 값이다. 외부 Script·JSON·HTTP 인자로 넘기는 우회 직렬화를 만들지 않는다.

부품 구성 예제는 [부품 조합 가이드](ibl_component_composition.md)를 따른다.
