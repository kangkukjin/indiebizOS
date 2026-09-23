# IBL 판본 2 — 명시 값·함수·조합

`execute_ibl(code:..., edition:2, inputs:{이름:값})` 또는 파일 첫 줄 `#!ibl edition=2`로 선택한다.
생략하면 기존 판본 1이다. API와 헤더가 다르면 실행 전에 거절한다. 새 판본으로 쓴 코드를 기존 판본에 보내지 않는다.
일반 사용자 기본값과 기존 관용구·워크플로·스케줄은 자동 변경하지 않는다.

## 작성과 검사

```ibl
#!ibl edition=2
[def:가중점수]($목록, $배수=2) {
  $목록 >> [table:each] {
    return {id:$it.id, weighted:$it.score * $배수}
  }
}
$목록 = [{id:"007",score:7},{id:"b",score:5}]
$결과 = $목록 >> [fn:가중점수]{배수:3}
return $결과
```

`check:true`는 같은 컴파일러로 효과 없이 검사한다. 결과는 `valid`(검사한 범위에서 적합),
`invalid`(확정 오류), `incomplete`(미확정 타입의 실행 시 검사 필요), `failed`(검사 기반 오류)다.
`ok`는 업무 품질·모델 정확성·전건 완료를 보장하지 않는다. source_span의 offset/line/column으로 고친다.
함수와 라이브러리의 자유 변수는 오류다. 인자를 명시하며 첫 인자가 파이프 자리다.
파이프 입력과 같은 인자를 동시에 쓰면 null·빈 목록이어도 충돌이다. 재귀는 지원하지 않는다.
같은 범위의 앞으로 나온 함수도 부를 수 있고 지역 함수가 등록 함수보다 우선한다.

## 값·식

변수는 값 그 자체다. 데이터의 `error`, `success`, `items`는 일반 키다.
목록은 0/1/N건 모두 목록이며 `.items` 같은 가상 필드는 없다. 길이는 `len($x)`다.
레코드와 목록은 불변이고 변수만 재바인딩한다. 외부 입력은 `inputs`로 명시하며 이전 턴 변수는 자동 주입하지 않는다.
`files`, `files_from`, 기존 `resume` 봉투는 새 판본에서 거절한다.

일반 문자열은 문자 그대로다. `f"${row.id}: ${1+2}"`만 보간하며 한 번만 해석한다.
보간은 Text·Number·Bool을 받는다. 구조는 `json($x)`, 결측은 `has($r,"key")`와
`get($r,"key",기본값)`을 사용한다. null은 존재하는 값이다. `"007"`을 복사하면 문자열이 유지된다.
산술·동등·순서의 숫자 관측 정책은 기존 `common/value_semantics.py`를 공유한다.

객체·목록·조건·인자·콜백에서 같은 식을 사용한다. `($r) => $r.score * $factor`는 생성 시점의 값을 캡처한다.
콜백과 보간·인자에는 도구 호출을 넣을 수 없다. 먼저 문장으로 실행해 변수에 받는다.
`len`, `has`, `get`, `json`, `number`, `text`, `abs`, `round`, `min`, `max`, `sum`,
`reduce(목록,초깃값,($누적,$행)=>식)`, `is_ok`, `unwrap`, `error_of`, `evidence`가 내장 함수다.

## 반환·분기·반복

`return`은 가장 가까운 프로그램·함수·each 콜백·병렬 가지에서 즉시 반환한다.
if/try는 반환 프레임을 만들지 않는다. finally는 거치며 finally 안 return은 금지다.
명시 return이 없으면 마지막 문장 값이 결과다. 할당·정의·빈 블록은 Unit이며 null과 다르다.

- `[if:Bool 식] { ... } [else] { ... }` — else 생략은 Unit.
- `[case:식] { [when:식] {...} [when:식] {...} [else] {...} }` — 같은 값인 첫 가지.
- `[try] {...} [catch] {...} [finally] {...}` — `$error`는 코드·종류·위치·부분 결과·증거를 가진 FailureView.
- `[repeat:횟수] {...}`, `[repeat:while Bool 식] {...}`, `[repeat:until Bool 식] {...}`.
  i는 0부터 시작한다. while은 회차 전, until은 회차 후 검사한다. repeat의 반환은 Unit이며 현재 프레임 변수를 재바인딩할 수 있다.
- `>>` 성공 값 전달, `&` 가지 순서 목록(자동 펼치기 없음), `??` 잡을 수 있는 실패만 폴백.
  우선순위는 괄호 > `&` > `>>` > `??`다. 빈 목록·빈 문자열·null은 폴백하지 않는다.

`[table:each]{mode:"map"}`가 기본이다. 각 입력당 결과 하나이며 반환 목록은 중첩 목록으로 남는다.
`mode:"flat_map"`은 반드시 List를 반환하고 한 겹만 펼친다. `mode:"effect"`는 Unit을 반환한다.
몸통이 Unit이면 map 결과도 Unit이며 입력 행을 몰래 되돌리지 않는다.
`parallel:1~8`은 출력 순서를 바꾸지 않는다. 중첩 병렬은 작업자 폭증을 피하기 위해 내부를 순차 실행한다.
each는 바깥 값을 읽을 수 있지만 재바인딩하지 못한다. `$it`, `$i`, `$error`는 예약 바인딩이다.

기본 실패 정책은 stop이다. `on_error:"collect"`는 map에서만 가능하며 `List<Result<T>>`를 반환한다.
`is_ok`, `unwrap`, `error_of`로 다루고 Err의 unwrap은 실패한다. `limit`은 없으며 의도한 표본은 앞에서 take/filter한다.
순차 프로그램은 실패 즉시 멈춘다. 계속해야 하는 곳을 try/catch로 명시한다.

## 도구 경계

사전에 `callable_contract`가 있으면 그 값 계약을 사용한다. 나머지 설치·활성 어휘는 기존 실행기를 거치는
호환 어댑터로 호출한다. `edition:2, describe:["sense:search"]`로 실제 계약을 읽는다.
아래는 값 모양을 고정한 네이티브 연결이다:

| 어휘 | 판본 2 입력/결과 |
| --- | --- |
| table:filter | items와 `where:($r)=>Bool` → List<Record> |
| table:select | items와 columns(열 목록 또는 Record 반환 콜백) → List<Record> |
| table:compute | items와 `set:($r)=>Record` → 새 필드를 합친 List<Record> |
| table:sort | items, by(Text), descending(Bool, 선택) → List<Record> |
| table:take | items, n(0 이상 정수) → List |
| self:read | path, offset/limit 선택 → `{text:Text,blocks:List<Record>}`. 첫 어댑터는 **텍스트/Markdown** 고정이다. PDF·Office의 기존 기능은 판본 1을 사용한다. |
| self:write | path, content(Text; 파이프 자리) → 파일 영수증 Record. 기존 쓰기 보호·outputs 경로 규칙 적용. |
| self:list | path, pattern 선택 → List<Record> |
| self:script | id, args(Record; 파이프 자리) → 등록 계약의 값. 명시 ibl-script/2 등록만 허용. |

새 사전 항목은 선언된 어댑터로 확장한다. 파서에 업무 액션 이름을 넣지 않는다.
데이터를 보고 message/items 중에서 고르는 규칙은 새 판본에 없다. 봉투 해제는 사전이 지정한 고정 경로다.
의도한 selection·화면 preview와 원천 누락을 구분한다. 원천 누락은 Fail + partial이며
`$error.partial`을 명시적으로 사용해도 `source_complete:false`는 남는다.
권한 거절·취소·예산 고갈·프로토콜 미지원은 기본 catch/fallback으로 성공 처리하지 않는다.

## 실행 증거와 값 전송

`value`는 사람이 읽는 값, `value_wire:{protocol:"ibl-value/1",data:...}`는 모든 컨테이너를 태그한 손실 없는 값이다.
Unit·Result·Decimal은 일반 JSON 레코드로 위장하지 않는다. 타입을 보존할 소비자는 wire를 읽는다.
`success`와 `source_complete`는 각각 실행 성공과 관측된 원천 완전성이다. 작업 품질의 자동 판정은 아니다.
`evidence($x)`는 값 및 분기 조건의 보수적 의존 DAG를 읽는다. 정확한 행별 출처 추적은 아니다.
`source_map`, node_id, invocation_id로 반복 호출과 원문 위치를 연결한다.
모델 표면은 요약과 result_ref를 받고, 앱/직접 HTTP는 전체 결과를 받는다. 전체 증거와 값은 기존 read_result로 회수한다.

실행 예산은 전체 프로그램에서 공유한다(기본 10만 계산 단계·1만 반복 행·120초·함수 깊이 64).
경계에서 협력적으로 검사하며 이미 실행 중인 외부 프로세스를 즉시 중단했다고 가정하지 않는다.
취소 후 finally 정리는 최대 100단계·1초의 경계 예산이다. 외부 쓰기를 롤백했다고 표시하지 않는다.
실패한 병렬 작업은 신규 제출을 멈추고 이미 시작한 가지의 종료를 확인해 실제 성공 값·원래 인덱스·미처리 상태를 보존한다.

## 저장·도구·호환

검증한 함수를 기존 workflow 원장에 **새 id / edition:2**로 저장한다. 소스는 하나의 `[def:이름](...){...}`다.
관리 호출은 `[self:workflow]{op:"save",edition:2,code:...}` 또는 아래 CLI register다.
실행은 새 판본의 `[fn:이름]{...}`다. `[self:workflow]{op:"run",edition:2,name:...,params:{...}}`도 같은 진입점을 쓴다.
판본 1 id 덮어쓰기는 거절한다. 해마에도 헤더가 있는 명시 `[def:]`를 등록할 수 있다.
같은 이름의 판본 1·2 관용구는 별도 행·서명·실적으로 보존된다. 판본 1 호출은 판본 1을 계속 사용한다.
판본 2의 이름 해소는 지역 정의 → 판본 2 저장 정의 → 기존 함수의 호환 어댑터 순서다. 저장본의 하위 함수를 바꿔도 실행 중 계획의 본문은 바뀌지 않는다.

```bash
.venv/bin/python scripts/ibl_v2.py check docs/examples/ibl_v2/table.ibl
.venv/bin/python scripts/ibl_v2.py run docs/examples/ibl_v2/table.ibl --output /tmp/ibl-run.json
.venv/bin/python scripts/ibl_v2.py replay docs/examples/ibl_v2/table.ibl --record /tmp/ibl-run.json
.venv/bin/python scripts/ibl_v2.py register /path/to/function.ibl
.venv/bin/python scripts/ibl_v2.py inventory
```

replay는 기록된 입력·계획 지문이 같을 때만 외부 결과를 재생한다. 기록이 없으면 외부 호출하지 않고 실패한다.
현재 재생은 디버깅 용도다. 중단된 쓰기의 자동 재개·exactly-once·결과 캐시는 제공하지 않는다.
## 기존 어휘·관용구를 조합하기

호환 어댑터의 반환은 원래 JSON 봉투 전체인 Record다. 자동 `.items` 추출·파이프 인자 추측은 없다.
순수 콜백·Unit·Result·정밀 숫자를 구형 JSON 핸들러로 암묵 변환하지 않는다.

```ibl
#!ibl edition=2
$검색 = [sense:search]{query:"공개 자료",count:5}
$검색.items >> [table:select]{columns:["title","url"]}
```

기존 관용구도 명시 인자로 호출하고 `$결과.items`처럼 반환 봉투를 읽는다.
검사 응답의 `guards[].boundary`는 `legacy-envelope/1` 또는 `legacy-function/1`이고 상태는 `incomplete`다.
선언된 키는 검사하지만 코어의 열린 인자·실제 반환·효과는 기존 실행기에서 확인한다.
검사가 모든 업무 계약을 증명했다는 뜻이 아니다. 권한·회원·도구 보호는 기존 실행기가 집행한다.

## 관용구와 학습 자료 이관

기존 무표기 자료는 판본 1로 보존한다. 새 용례는 헤더로 판본을 명시하고 같은 원장 문에서 새 컴파일러로 검사한다.
회상 카드에도 판본이 나타난다. 판본 2 함수의 실제 호출은 해당 원문의 실적에만 기록한다.
완료된 판본 2 프로그램은 기존 한 번의 증류에서 통째로 선택한다. 부분 실패·검사만 한 코드·외부 inputs가
필요한 코드는 자동 재사용 예제로 만들지 않는다. 서로 다른 프로그램이나 판본을 임의로 연결하지 않는다.
실행 원문은 별도의 관측 코퍼스에 판본과 함께 보존하며 재사용 적합 판정과 구분한다.

```bash
.venv/bin/python scripts/ibl_v2_assets.py inventory
.venv/bin/python scripts/ibl_v2_assets.py seed                     # 검사·예정 건수
.venv/bin/python scripts/ibl_v2_assets.py seed --apply             # 중복 없는 실제 적재
.venv/bin/python scripts/ibl_v2_assets.py seed /path/to/reviewed.json --apply
```

배포 씨앗 정본은 `data/idioms/ibl_v2_seeds.json`이다. `열추려보기`·`정렬해추리기`는 같은 이름의
판본 2 정의가 있으며, 각기 목록 자체를 반환한다. 기존 행의 본문·실적은 덮어쓰지 않는다.
새 별칭의 선언 이름과 `[def:]` 이름은 일치해야 한다. 일반적인 자동 문법 변환은 하지 않는다.
