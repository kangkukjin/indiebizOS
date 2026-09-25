# IBL — 언어와 실행 계약

IBL의 현재 문법은 명시 값·함수·반복·실패를 한 구조로 다룬다.
작성 교재는 [IBL 조합](../guides/ibl_composition.md), 상시 문법은
[실행기 교재](../common_prompts/fragments/12_ibl_only.md)다. 별도의 신판 소개를 읽어 문법을 선택하지 않는다.
모델 도구의 새 코드는 현재 문법을 기본으로 실행한다. 기존 저장 원문·스케줄·직접 HTTP의
호환 기본값은 유지하며, 새 저장 소스에는 `#!ibl edition=2`를 기록해 의미를 고정한다.
실행기 내부의 판본 번호는 저장·호환 메타데이터이며 두 작성 언어를 병렬로 가르치는 기준이 아니다.

## 조합 연산자

<!-- GRAMMAR_OPERATORS:START -->
| 연산자 | 이름 | 의미 |
|--------|------|------|
| `>>` | Sequential | 성공한 값을 선언된 다음 인자에 전달. 빈 목록도 정상 값 |
| `&` | Parallel | 독립 가지를 병렬 실행하고 가지 순서의 목록을 반환. 자동 펼침 없음 |
| `??` | Fallback | 잡을 수 있는 실패만 대체. 0건·빈 문자열·null은 그대로 반환 |
| `;` | Statement (독립 문장) | 독립 문장 경계(줄바꿈과 동일). 실패 즉시 중단, 계속할 곳은 try/catch로 명시 |
<!-- GRAMMAR_OPERATORS:END -->

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
`ok`는 업무 품질·모델 정확성·전건 완료를 보장하지 않는다. 진단의 `location`은 제출 원문 또는
저장 함수 안의 위치이며, `call_path`는 함수 호출 경로다. 기존 `source_span`은 연결 원문의 위치를 유지한다.
`issues`의 확정 오류를 모아 고친 뒤 전체를 재검사하고, `warnings`는 의도에 비춰 검토한다.
`preflight`는 선언된 AI 방문 상한과 미상을 구분한다. `source_hash`는 제출 원문, `plan_hash`는 의존 계획의 지문이다.
검사·실행은 같은 컴파일러를 사용하며 검사 결과를 실행 승인 토큰으로 쓰지 않는다.
검사 대응표·범위: [작성 지원 첫 구현](../../docs/IBL_AUTHORING_SUPPORT_IMPLEMENTATION_2026_09_24.md).
함수와 라이브러리의 자유 변수는 오류다. 인자를 명시하며 첫 인자가 파이프 자리다.
파이프 입력과 같은 인자를 동시에 쓰면 null·빈 목록이어도 충돌이다. 재귀는 지원하지 않는다.
같은 범위의 앞으로 나온 함수도 부를 수 있고 지역 함수가 등록 함수보다 우선한다.

## 값·식

변수는 값 그 자체다. 데이터의 `error`, `success`, `items`는 일반 키다.
목록은 0/1/N건 모두 목록이며 `.items` 같은 가상 필드는 없다. 길이는 `len($x)`다.
레코드와 목록은 불변이고 변수만 재바인딩한다. 외부 입력은 `inputs`로 명시하며 이전 턴 변수는 자동 주입하지 않는다.
큰 본문은 `[self:read]{path:...}`의 `.text`를 전달한다. 일반 외부 값은 `inputs`로 받는다.
`files`, `files_from`는 기존 저장 프로그램의 호환 인자다. 현재 실행은 반환된 `resume:{run_id}`와 동일한 code·inputs로 이어간다.

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
  i는 0부터 시작하며 while 조건과 본문은 현재 회차 번호를 읽는다. until은 본문 실행 후 조건을 검사한다.
  횟수 식은 바깥 범위에서 한 번 평가하고, 중첩 반복이 끝나면 바깥 i를 복원한다. repeat은 Unit이며 현재 프레임에 대입한다.
  until·고정 양수 횟수의 본문에서 모든 진행 경로가 정의한 값은 뒤에서 쓸 수 있다. 0회 가능 경로의 값은 미리 초기화한다.
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

| 어휘 | 입력/결과 |
| --- | --- |
| table:filter | items와 `where:($r)=>Bool` → List<Record> |
| table:select | items와 columns(열 목록 또는 Record 반환 콜백) → List<Record> |
| table:compute | items와 `set:($r)=>Record` → 새 필드를 합친 List<Record> |
| table:sort | items, by(Text), descending(Bool, 선택) → List<Record> |
| table:take | items, n(0 이상 정수) → List |
| table:join | left/right 또는 inputs(파이프 자리), on → items Record. 두 출처의 목록·봉투를 그대로 받는다. |
| table:merge / table:union | left/right 또는 inputs(파이프 자리) → items Record. 두 개 이상 출처·빈 목록·부분 실패를 보존한다. merge의 by는 중복 키다. |
| self:time | format 선택 → Text. JSON처럼 생긴 포맷도 원문 문자열로 반환한다. |
| self:read | path → `{text:Text,blocks:List<Record>,data:Record}`. 확장자로 텍스트/PDF/Office를 해소한다. pages/tables/sheet/max_rows 등은 조회한 계약대로 지정하며 표·시트·이미지·범위 원문은 data에 보존한다. |
| self:write | path, content(Text; 파이프 자리) → 파일 영수증 Record. 기존 쓰기 보호·outputs 경로 규칙 적용. |
| self:list | path, pattern 선택 → List<Record> |
| self:edit | path, new_string, old_string 또는 start_line → 편집 영수증 Record. 줄 번호·별칭·동일 파일 병렬 쓰기를 검사한다. |
| self:grep | pattern, path, output_mode → items/total/truncated Record. content/count/files_with_matches에 따라 행 필드 계약을 해소한다. |
| sense:search | query 또는 queries, source; gnews/hn은 headlines 가능 → items Record. source·curate에 따른 요구 입력·모델 효과를 검사한다. |
| sense:crawl | url, op(content/links/metadata) → 원문 봉투 Record. content는 text/title/url/items가 있으며 원천 누락은 실패와 partial로 보존한다. |
| self:script | id, args(Record; 파이프 자리) → 등록 계약의 값. 기존 등록은 JSON stdin/stdout을 값으로 연결하며, 새 wire 계약도 지원한다. |

계약은 aliases·required_any·requires(인자 동반)·exclusive(동시 입력 금지)·enums·integers·minimum·nonempty와 리터럴 조건 variants를 선언할 수 있다.
검사와 실행은 같은 선언을 소비한다. 동적 선택자는 실행 직전 검사로 남긴다.
`{"$list": {필드: 타입}}`은 구조를 가진 목록 행의 타입 선언이다.
`describe:["fn:이름"]`은 컴파일러가 검사한 저장 함수의 입력·반환·효과·미확정 경계를 본문 없이 돌려준다.

새 사전 항목은 선언된 어댑터로 확장한다. 파서에 업무 액션 이름을 넣지 않는다.
일반 값에 자동 봉투 추출은 없다. 사전의 고정 경로 또는 명시 문서 어댑터가 도구별 결과를 정규화한다.
의도한 selection·화면 preview와 원천 누락을 구분한다. 원천 누락은 Fail + partial이며
`$error.partial`을 명시적으로 사용해도 `source_complete:false`는 남는다.
권한 거절·취소·예산 고갈·프로토콜 미지원은 기본 catch/fallback으로 성공 처리하지 않는다.

## 실행 증거와 값 전송

`value`는 사람이 읽는 값, `value_wire:{protocol:"ibl-value/1",data:...}`는 모든 컨테이너를 태그한 손실 없는 값이다.
Unit·Result·Decimal은 일반 JSON 레코드로 위장하지 않는다. 타입을 보존할 소비자는 wire를 읽는다.
`success`와 `source_complete`는 각각 실행 성공과 관측된 원천 완전성이다. 작업 품질의 자동 판정은 아니다.
`evidence($x)`는 값 및 분기 조건의 보수적 의존 DAG를 읽는다. 정확한 행별 출처 추적은 아니다.
빈 합산·조기 반환·실패 복구·finally와 병렬 실패에서도 실제 평가한 근거를 보존한다.
분기·반복·catch 안에서 대입한 값은 실행 조건의 근거도 유지하며, 병렬 작업자끼리 근거를 섞지 않는다.
`source_map`, node_id, invocation_id로 반복 호출과 원문 위치를 연결한다.
모델 표면은 요약과 result_ref를 받고, 앱/직접 HTTP는 전체 결과를 받는다. 전체 증거와 값은 기존 read_result로 회수한다.

실행 예산은 전체 프로그램에서 공유한다(기본 10만 계산 단계·1만 반복 행·함수 깊이 64).
기본 총시간 제한은 없다. 호출자가 명시한 시간 예산과 개별 도구의 시간 제한은 유지한다.
경계에서 협력적으로 검사하며 이미 실행 중인 외부 프로세스를 즉시 중단했다고 가정하지 않는다.
취소 후 finally 정리는 최대 100단계·1초의 경계 예산이다. 외부 쓰기를 롤백했다고 표시하지 않는다.
실패한 병렬 작업은 신규 제출을 멈추고 이미 시작한 가지의 종료를 확인해 실제 성공 값·원래 인덱스·미처리 상태를 보존한다.

## 관용구와 저장

검사한 `[def:이름]($인자,...){...}`를 `[self:workflow]{op:"save",edition:2,code:...}`로 저장한다.
저장 파일은 `#!ibl edition=2` 헤더를 가진다. 호출은 `[fn:이름]{인자:값}`이다.
기존 관용구도 같은 호출 자리에서 사용한다. 현재 정의가 있으면 먼저 사용하고,
기존 정의만 있으면 어댑터가 그 정의의 실행 의미와 반환 봉투를 보존한다.
기존 반환이 Record이면 필요한 `.items` 등의 필드를 **계약으로 확인해** 다음 부품에 전달한다.
새 관용구를 만들 때는 명시 인자·값 반환으로 작성하며 기존 본문을 그대로 복사하지 않는다.
기존 저장 정의를 고칠 때도 새 정의를 따로 검사한 후 호출자를 전환한다.

`self:script`는 등록된 id와 args를 직접 받는다. 기존 등록 스크립트를 호출하기 위해
workflow로 감쌀 필요가 없다. 기존 스크립트에는 원래 JSON 객체를 stdin으로 주고,
JSON stdout은 객체/목록/스칼라 전체를, 평문 stdout은 완전한 문자열을 반환한다.
실패·부분 원천 표지는 값과 별도로 전파한다. 새 `ibl-script/2` 등록의 명시 타입 계약도 유지한다.
스크립트가 `{items:[...],run:...}`를 반환했다면 `$s.items`, `$s.run`처럼 직접 읽는다.

## 작성 환경과 저장 호환

AI의 execute_ibl 도구는 현재 문법을 기본으로 실행한다. 저장 원문의 `edition`과 헤더는
호환 메타데이터다. 오래된 HTTP 호출·스케줄·저장 프로그램은 그 원래 실행 의미를 유지한다.
API를 직접 사용하는 새 프로그램은 `#!ibl edition=2` 헤더를 넣어 실행 의미를 고정한다.
구문 오류를 이유로 다른 문법으로 재실행하지 않는다. 기존 저장 원문의 분석이 필요하면
`docs/compatibility/ibl_legacy_language.md`를 읽는다. 작성 교재는 이 문서 하나다.

## 언어의 경계 — 표준과 사전 (헌법 조항)

브라우저 / HTML / 사용자의 HTML 파일이 서로 다른 것이듯, **하네스 / IBL 표준 / 개인 사전**은 서로 다른 층이며 섞이지 않는다. 이 구분이 두 이동성을 만든다: 다른 사용자는 같은 IBL 위에 자기 어휘를 가질 수 있고(어휘와 그에 키잉된 축적물 — 해마 코퍼스·임베딩·증류 — 은 사람을 따라감), 하네스(모델·에이전트 러너)는 갈아끼워도 언어와 축적물은 무사하다. (선행 대조군: **SQL** — 방언(사전 차이)이 심한 채로도 명세가 퍼져 이겼다. 표준 코어가 가치의 대부분을 나르면 사전 간극은 치명상이 아니다. 단, 이 명제는 측정 가능해야 한다 — "문법+기능어 코어만으로 가치의 몇 할이 나가는가"를 코퍼스에서 셀 수 있다. 반대 방향의 주의: 퍼지는 것은 *언어*이지 *프로그램*이 아니다 — 개인 사전은 수출되지 않으므로 프로그램 이식성은 목표가 아니고, 몸 사이 간극은 번역이 아니라 부탁(`[others:ask]`, 상호운용)으로 건넌다.)

**IBL 표준** — 모든 IndieBiz 인스턴스가 공유하는 문법·기능어 코어와 개인 사전의 경계:

1. **문법**: 이 문서 앞부분의 값·식·명시 인자 함수·분기·반복·조합 계약이다. 문법 개정은 컴파일러·실행기·검사·주 교재를 함께 갱신한다.
2. **기능어 코어**: `self`·`others`·`table` 중 `always_on: true`로 선언된 어휘다. `STANDARD_CORE_NODES`와 사전 원천이 같은 경계를 나타낸다.
3. **개인 사전**: 내용어는 데이터로 추가·제거한다. 어휘 이름을 파서·엔진의 문법 분기에 넣지 않는다. 어댑터 계약이 값·효과·권한·결과 경계를 선언한다.

기존 도구의 `{items:[...]}`는 그 도구의 반환 계약이다. 언어 전체의 값은 List·Record·Text·Number·Bool·null·Unit·Result이며, 모든 결과를 items 봉투로 강제하지 않는다. 파이프는 선언된 입력 자리에 값을 전달한다. 외부 실행 증거는 값과 함께 보존한다.

이전 문법 개정 이력과 저장 원문의 치환·통화 규칙은 [호환성 명세](../../docs/compatibility/ibl_legacy_system.md)에 보존한다. 새 프로그램의 작성 규칙은 앞의 본문이다.

### 사전은 몸마다 다르다 — 물리 분리와 몸 사이 소통 (부속 조항, 2026-07-22)

한 사람이 여러 몸(맥·폰·낯선 PC)을 쓰면 **사전도 몸마다 다르다**. 배포물은 전체 사전집이지만 **설치된 몸이 갖는 것은 자기 어휘뿐**이다.

- **물리 분리**: 로더가 설치된 패키지의 어휘만 싣고(폰 번들은 빌드 시점에 물리 필터), 카탈로그(`build_environment`)와 해마 회상(`code_is_own`)이 **소유-필터**를 지난다. 원칙은 한 줄 — **남의 어휘를 학습하지 않는다**(미지의 어휘는 남의 것으로 판정).
- **명함(capability card)**: `GET /nodes/card` — 레지스트리에서 파생한 desc-프로젝션(표준 코어 제외, params 미포함, 몸-인식 필터, `dictionary_hash`). 이웃 몸 등록 시 상호 자동 교환·캐시. 프롬프트 냄새는 ~70토큰/몸.
- **부탁(ask)**: `[others:ask]{to, message}` → `POST /nodes/ask`. **상대의 액션 이름을 흉내 내지 않는다** — 자연어로 부탁하면 받는 몸이 *자기 사전*으로 컴파일→실행→통화로 회신하고(1회 자가교정), 자기 어휘 밖이면 정직하게 거절한다. 컴파일러 능력 축은 *해마 유무*(용례 있으면 조종실 경로, 없으면 사전-동봉 경량 모델).
- **`delegate` 와의 구별**: `[others:delegate]`=**인격**(에이전트)에게 일을 맡김 / `[others:ask]`=**몸**에게 능력을 부탁함.
- **특권 배관 금지**: 몸 사이에 전용 RPC·공유 레지스트리 같은 특권 통로를 두지 않는다. 특별함은 배관이 아니라 **이웃 등급**(`body_trust`)이며, 폰-맥도 "최고 레벨 이웃"일 뿐이다.

### 표현 언어의 층위 (부속 조항, 2026-07-03)

IBL(실행 언어) 위에 표현을 맡는 언어가 두 부류 더 있고, 셋은 섞이지 않는다. 판별축은 **파이프를 타는가**:

1. **페이로드 IR** — 파이프 안을 데이터로 흐르는 산출물 기술 언어: 문서 IR(blocks), 슬라이드 IR(slides), 차트 스펙(chart_type·bands·Plotly spec). 각각 특정 액션의 파라미터 계약이며 emitter가 소비해 산출물이 된다. 규율: 표준 외부 언어와 동형인 구간(문서 IR↔Markdown, 차트↔Plotly figure JSON)은 변환자로 왕복 가능하게 유지 — 언제든 표준 쪽으로 접을 수 있는 상태가 목표.
2. **표면 언어(`app:` 뷰 어휘)** — 파이프 밖에서 표면(계기)이 읽는 선언: 뷰 프리미티브·form 필드·뷰-이벤트. 렌더링 언어가 아니라 **통화↔액션 바인딩 언어**다(외부 표준이 존재하지 않는 유일한 층 — 픽셀·문서·차트는 전부 표준어에 위임돼 있다). 표현력 경쟁은 이 언어의 종목이 아니다(그건 escape=React·HTML 표준어의 일). 이 언어의 존재 이유는 {0토큰 표면 · 결정론(주권) · 저술 시점 검증 · 경량 모델 저술 가능}.

**표면 언어의 표준/사전 경계**: 어휘 집합과 해석기 — `build_ibl_nodes.py`의 `APP_VIEW_TYPES`·`APP_FORM_FIELD_TYPES`·`APP_VIEW_EVENTS` 선언 + 렌더러 2곳(`GenericInstrument.tsx`/`api_launcher_web.py`) + `validate_app_blocks` — 은 **표준**(본체 코드, 기본 설치)이다. 패키지는 뷰 단어를 추가할 수 없다(리트머스). `app:` 블록(어휘의 *사용*)은 **사전**(패키지 yaml·`data/instruments/` 데이터)이다.

**뷰 어휘 승격 기준(4)** — 새 뷰 단어는 전부 만족할 때만:
1. 기존 escape(bespoke 컴포넌트) 하나 이상을 은퇴시킨다 — 계기 하나의 미감은 사유가 아님(투기적 승격 금지)
2. 통화(items/blocks)를 소비한다
3. 3표면(데스크탑·원격·폰) 투영이 모두 의미 있다
4. 데이터-패턴/상호작용 계약이다 — **레이아웃·스타일(간격·색·열 배치)을 기술하기 시작하면 거부**. 그건 HTML 재발명의 냄새 = 정지 신호, escape로 보낸다. (UI 원자는 유한한 닫힌 부류라 이 어휘는 점근 수렴해야 정상 — escape 수가 다시 늘면 어휘 부족이 아니라 애초에 어휘로 풀 문제가 아니었는지부터 의심.)

**변경 = 언어 개정**: 뷰 단어의 추가·제거는 렌더러 2곳+검증자+문서 2곳(이 문서 "앱 표면 노출" 절 · `new_action_checklist.md`)을 함께 바꾸는 행위다. **집행**: 빌드의 **뷰-어휘 문서-동기 가드**가 두 문서의 어휘 줄("view 프리미티브 N종: …" / "form 필드 N종: …")을 코드 선언과 대조해 어긋나면 차단.

### 명사의 자리 — 몸의 명사는 코드에, 세계의 명사는 데이터에 (부속 조항, 2026-08-06)

이 시스템이 하드코딩하는 명사는 **몸의 명사**뿐이다 — 6개 노드(감각·자기·손발·타자·생성·표)와 액션 어휘, 즉 *작용의 거처*. **세계의 명사** — 사람·장소·사물·관계, "세계가 이런 곳이다"라는 앎 — 는 어떤 경우에도 코드·표준 쪽으로 넘어오지 않고, 오직 데이터(개인 사전·기억)에 **반증 가능한 퇴적물**로만 존재한다.

- **선행 명사 스키마 금지**: 팔란티어식 Object Type·프라이머리 키·링크 타입 — 세계를 미리 명사로 모델링하고 데이터를 부어 넣는 방향 — 을 만들지 않는다. 스키마 명사는 "구축은 일회성, 조정은 상시"의 유지보수를 낳는다. 조직은 합의를 사기 위해 그 비용을 지불하지만, 주권자가 하나인 개인의 몸은 면제받는다 — **명사가 무료로 틀릴 수 있다는 것**이 이 형태의 해자다.
- **세계상 저장의 원리**: 세 기억이 이미 독립적으로 공유하는 규율을 따른다 — **시스템이 판정하지 않고 증거를 노출한다**(포식기억: `conf`·`freshness`·`provisional`·surface / 심층메모리: 타임스탬프 동반 회상 / 해마: success_rate 표시). 명사·관계가 새로 필요해지면 빈도가 증명했을 때(결정화 사다리 — 용례→관용구→워크플로→가이드; 관용구 = 명시 인자·반환을 가진 재사용 함수, 문법 개정 없이 기억 단위만 더한 층, 정본 `docs/IBL_IDIOM_TIER_HANDOFF.md`) 데이터로만 추가하고, 반드시 반증 가능하게 — 신뢰도·부패 노출·폐기 사유를 달아서.
- **근거**: 지각은 수동 수용이 아니라 능동 구성이다(예측처리). 몸은 고정되고 세계는 유동한다 — 감각 양식은 진화가 고정했고 그 위의 객체는 학습이 임시로 만든다. 이 조항은 "표준과 사전" 경계의 명사판이다: 동사의 문법이 표준이고 내용어가 사전이듯, **명사에서는 몸이 표준이고 세계가 사전이다.**

---

## IBL 설계 철학 — 어휘와 가능성의 공간

> IBL을 개선할 때(액션 추가/삭제/통합, 증류, 패키지 설계) **이 문서를 먼저 읽어라.**
> "어휘를 *얼마나* 만드느냐"가 아니라 "**무엇을 위해, 언제** 만드느냐"가 핵심이다.

## 핵심 명제

**목표는 어휘의 크기가 아니라, 최소 비용으로 *실질적으로 접근 가능해지는 가능성의 공간*을 최대화하는 것이다.**

파이썬 코드로 바닥부터 짜든, IBL 조합으로 처리하든, 새 액션을 만들든 — 유일한 질문은
"이것이 닿을 수 있는 세계를 얼마나 넓히는가, 어떤 비용으로?"이다.

---

## 1. 힘은 어휘 크기가 아니라 *조합*에서 나온다

람다 대수(구성 요소 3개)와 SKI 조합자(2개)는 튜링 완전하다 — 계산 가능한 무엇이든 한다.
**표현력은 어휘의 *크기*에 저장된 적이 없다. *조합*으로 풀려나온다.**

- 잘 고른 소수 프리미티브 + 풍부한 조합 = **생성 문법**(무한). → 언어
- 많은 프리미티브 + 빈약한 조합 = **납작한 룩업 테이블**(크지만 유한). → 사전

IBL의 진짜 엔진은 액션 목록이 아니라 `>>`(순차) `&`(병렬 — 괄호 분기 `(B >> C)` 로 분기별 전처리) `??`(폴백) `;`(독립 문장)
`$변수`(값 바인딩), 명시 인자 함수, `[if:]`/`[case:]`(분기), `[table:each]`(전건 적용)를 조합한다.
연산자의 값 전달·반환 규칙은 앞의 명세와 같다. 목록 전체를 다른 도구에 줄 때는
`[도구]{인자:$목록}`으로 전달하고, 각 행마다 실행할 때는 each를 쓴다. 문자열 보간·자동 봉투 해제로 두 경우를 혼동하지 않는다.

**142 × 조합 × 외부 어휘 = 사실상 무한.** 더 많은 단어 ≠ 더 강한 언어.

> **조합의 병목은 낱말 수가 아니라 문형 수다** (2026-08-15 코퍼스 전수 실측): 파이프 포함 문장
> 7%·평균 길이 2.45·150 중 68개는 한 번도 조합된 적 없음. 미조합의 다수가 `others:`(발신)와
> `self:` 원장·시간·기억이었는데, 원인은 **항목 단위 적용이 없어서**였다 — 목록을 통째로 싱크에
> 넘기는 문장은 말이 안 되니 AI 가 아예 싱크를 못 붙이고 "가져와서 정리해 사람에게" 2단에서
> 멈췄다. `[table:each]` 는 그 한 조각이다. 정본: `docs/HIGHER_ORDER_SENTENCE_DESIGN.md`

## 2. 그러나 파이썬(보편 언어)만으론 부족하다 — 최적점은 *움직인다*

보편성(computability) ≠ 복잡한 일을 위한 힘. 파이썬은 *낮고 보편적인 고도*에 있어,
복잡한 일은 길고 깨지기 쉬운 from-scratch 표현이 된다(중간에 반드시 오류가 난다).
**어휘는 고도(altitude)를 올린다.** 그래서 어휘는 늘려야 하되 — 폭증은 해롭다. 균형이다.

규칙: **요구되는 고도에 맞춰 최소로. 그 요구 고도는 일이 복잡해질수록 올라간다.**
("가능한 한 작게, 그러나 일이 요구하는 것보다 작지는 않게.")

| 실패 모드 | 증상 |
|---|---|
| **과소 어휘**(파이썬만) | 보편적이나 복잡한 게 다 길고 취약 |
| **과잉 어휘**(폭증) | 못 배우고, 납작하고, 조합성·유연성 상실. **언어 안의 도구 폭증** |

**어휘 필요량 = 복잡성의 깊이 × 도메인의 특수성.** indiebizOS는 둘 다 높다(한 사람의 삶을 깊이).
그래서 어휘 생성은 야망에 내재된 일이다 — 일반 하네스가 어휘를 피할 수 있는 건 더 얕게 겨냥하기 때문.

## 3. 액션은 *논리*가 아니라 *접근*을 캡슐화한다 (가장 깊은 이유)

파이썬 추상화는 압축된 논리일 뿐 — 그게 하는 건 날것의 코드도 한다.
하지만 `[sense:realty]{op: "query"}`가 캡슐화하는 건 **국토부 API 키**, CCTV 액션은 **물리적 카메라**다.
**아무리 코딩을 잘해도 갖지 않은 키를, 소유하지 않은 하드웨어를 지능으로 만들어낼 수 없다.**

→ **가능성은 *논리*가 아니라 *접근(access)*으로 열린다.** 접근(키·계정·기기·통합)은 환원 불가능하게 개인적.
- **접근 프리미티브 = 가능성 공간에 *차원을 추가*한다.**
- **조합(코드/IBL 연산자) = 기존 차원 안에서 *움직인다*.**

## 4. 언제 새 액션(단어)을 만드는가 — 판단 기준

> **새 단어를 만들어라 IFF (a) 기존 어휘로 표현이 *비싸거나 불가능*하고, (b) 모양이 *안정적*이라 굳혀도 유연성을 잃지 않을 때.**

| 후보 | (a) 비싼가 | (b) 안정적인가 | 판단 |
|---|---|---|---|
| 접근 프리미티브(키·하드웨어) | ✅ 조합 불가 | ✅ 호출 모양 불변 | **무조건 어휘화** |
| 기존 단어로 간단히 되는 것 | ❌ | — | **만들지 마라** (이미 쌈) |
| 복잡하지만 *계속 변하는* 조합 | ✅ | ❌ | **굳히지 마라** (유연한 조합/코드로) |
| 길고 깨지기 쉬운 *고정* 조합 | ✅ | ✅ | 어휘화 가치 있음(신뢰성 압축) |

**트리거는 *빈도*가 아니다.** 자주 쓰여도 기존 단어로 간단하면 만들지 마라. 빈도는 오해를 부르는 대리변수다.

### 마찰 신호 (실전 감지법)
모델이 내놓은 *해법의 모양*을 보라:
- **짧은 기존-단어 조합** → 만들지 마라(고도가 맞다).
- **길고 깨지기 쉬운 조합 / raw 코드로 떨어짐 / 새 접근이 필요했음** → 후보(기존 어휘가 부족했다는 증거).

## 4.5 일단 만들기로 했다면 — 이름 짓는 법 (명명 헌법)

§4가 *만들지 말지*라면 여기는 *어떻게 부를지*다. 이름이 어휘의 사용성을 좌우한다 — 인간이 읽고 쓸 만큼 단순하면 LLM도 더 잘 쓴다(LLM은 인간 데이터를 학습하니까). 그래서 어휘 정리가 IBL 개선의 핵심이다.

1. **보편성-길이 반비례** (기준은 빈도가 아니라 *보편성*): 보편적 능력은 짧은 단독어(`read`/`search`/`time`) — 흔히 떠올리는 그 의미라서 보편어를 점유할 자격이 있다. 특수 분야 능력은 이름에 "언제 쓰는지"를 담아 자기설명적으로, **길어져도 정상**.
2. **변형은 op로 (굴절)**: 한 능력의 여러 변종은 독립 어휘로 난립시키지 말고 **한 어휘 + op**로. 자연어의 단어 활용/변형과 같다. (kr_price·us_price·price → `[sense:stock]{op}`)
3. **한 단어 = 한 개념 (과통합 경계)**: op는 굴절이지 잡동사니가 아니다. 무관한 능력을 한 이름에 op로 우겨넣으면 (특히 수동 작성을) 오히려 해친다. 도메인이 드러나는 소수의 명료한 액션 + 타이트한 op.
4. **특수보다 보편 우선**: §4의 "기존 단어로 되면 만들지 마라"의 따름정리 — 이미 있는 *특수* 액션도 보편 액션이 *같은 접근*을 제공하면 보편으로 흡수하고 특수를 쳐낸다. (출력이 비슷해도 접근이 다르면 별개.)
5. **land-grab 금지**: 보편어(`price`·`news`)는 보편 동작에만. 분야 액션이 보편어를 점유하면 인간이 못 맞힌다 — 분야가 이름에 드러나야.

> 이름을 바꾸는 정리(rename)는 *방출/교재 표면(meta.yaml·프롬프트·tool.json·운영데이터·코퍼스)을 모두 새 이름으로 옮긴 뒤* 옛 이름 별칭을 **은퇴**시켜 단일 어휘를 유지한다. 영구 별칭은 모순을 쌓는 임시방편이다.

## 4.6 몸-노드는 *열린 계급*, 통화 변환자는 *닫힌 계급* — 그래서 별도 `table` 노드

5개 몸-노드(sense·self·limbs·others·engines)는 **에이전트가 세계와 맺는 관계(작용의 거처)**로 가른다 — 지각/내 자원/세계에 작용/소통/생산. 다섯 모두 *데이터 평면 바깥의 무언가*를 건드린다. 이건 **열린 계급**(내용어)의 분류다: 도메인마다 무한히 자라는 명사들(`sense:price`, `self:photo`…). (선행 대조군: **PowerShell** — 동사는 승인 목록으로 닫았는데 명사를 안 닫아 cmdlet 수천 개로 폭증했다. IBL의 처방은 반대다: 데이터는 공통 값 체계로 조합하고, 열린 계급은 sublinear 성장 규율 + 반-어휘-증식("아니오, `[self:script]` 로 얼려라")로 다스린다. 새 액션마다 물을 질문: 새 동사인가, *명사가 동사 자리에 앉은 것*인가 — HTTP 의 `POST /doAction` 이 후자의 실물이다.)

그런데 **통화 변환자·emitter**(filter·sort·take·select·rename·flatten·dedup·groupby·join·union·merge + chart·spreadsheet·document·structure)는 다르다. 통화→통화 순수·무상태 — 세계의 *어디도* 안 건드리고 통화 평면 *안*에서만 계산하거나 산출물로 방출한다. 이건 **닫힌 계급**(기능어)이다: 고정된 대수, 새 도메인이 생겨도 안 늘어남. 언어로 치면 몸-노드 액션=명사/동사, 변환자=전치사/접속사. 파이프 문법(`>>`·`&`·`??`)과 같은 *계급*이고, 인자를 들어야 해서(`filter where …`) 어휘화됐을 뿐 — **문법에 가깝다**(build script가 이미 "순수 superstructure, IBL 문법, 몸 무관"이라 부른다).

**원리**: 열린 계급을 담으려 만든 분류함(5 도메인)에 닫힌 계급은 구조적으로 안 들어간다. 초기엔 변환자를 engines에 *실용적 셋방*으로 얹어 두고 "이름 이전은 비싸니 `group: transform` 태그로만 계급을 드러내자"고 판단했으나(아래 옛 교훈), **2026-06-30 신규 `table` 노드로 분리**하며 태그-only 방침을 개정했다. 결정적 동기는 **노드 on/off**다: 무거운 engines(미디어 생성)를 꺼도 가벼운 통화 문법은 살아야 하는데, 태그만으론 그 켜고/끔 경계를 못 그린다. 그래서 닫힌 계급이 *자기 노드*를 갖고, engines는 **순수 미디어 생성**만 남았다.

**그래서 어떻게 다루나** — 이제 `table` 노드가 계급의 거처다:
- `table` 노드(17 액션: 변환자 11 + emitter 4 + 고차 each·reduce 2)는 **기능어 코어**로 `always_on: true`다(`self`·`others`와 함께). 어떤 노드 선별에서도 꺼지지 않아 파이프라인이 항상 산다. (헌법: 위 "언어의 경계 — 표준과 사전" 조항)
- 계약을 `--check`가 강제한다(`validate_transform_contract`): `scope: workspace`(무프로젝트 파이프서도 동작) + `runs_on: anywhere`(통화는 몸 무관). 새 변환자가 계약을 빠뜨리면 *침묵-실패 재발* 대신 빌드가 막는다.
- 미래의 통화 연산자(`window`·`pivot`·`flatten`…)도 `table` 노드·같은 계약. 닫힌 계급은 *자기 노드로 드러나되* 5-몸 척추는 *열린 계급 전용*으로 깨끗이 유지된다.

### 원샷 AI 낱말 — 통화 대수의 세 자리 (2026-08-19, ai-ops 패키지)

원샷 AI 호출(개발 관행에서 결정론 배관의 의미론적 이음매를 잇던 그 함수)을 **파이프 시민**으로 승격했다. 낱말 수 = 타입 시그니처 수(자리마다 하나, 의미는 `instruction` 지시문이 나른다):

| 자리 | 낱말 | 형태 |
|---|---|---|
| 입구 | `[self:struct]{file\|text, schema}` | 비정형 → items 구조화 (grounded=원문 발췌 결정론 대조) |
| 중간 | `[table:ai]{instruction}` | items → items 의미 변환 (filter/sort 의 의미론적 형제) |
| 출구 | `[table:brief]{instruction}` | items → 산문 종합 (message=산문 정본 → write 싱크) |

계약: 모델=**기어 실행 축**(경량 `self:ask` 와 별개 — 새 의미 판단은 EXECUTE=본격 논리와 동류) · JSON 검증+재시도 1회+정직 실패 · 행 수 신고(rows_in/out) · `_ai` provenance · 집합 단위 1호출(0행=호출 생략+빈손 성공, 통화 없음=거절) · `ai_call: true` 플래그로 dry-run 고지+포털 대여 기본 거부. 규칙으로 적을 수 있으면 filter/sort 가 먼저다. 상세 = `data/guides/ai_words.md`, 정본 설계 = `docs/ONESHOT_VOCAB_DESIGN.md`.

`table:ai`의 선택 인자 `input_fields`는 모델 입력 열만 좁히며 숨긴 원본은 코드에 보존한다.
`preserve_rows:true`는 색인 전수·중복 검증 후 입력 순서로 병합한다. `fields`는 여전히 출력 투영이다.
`self:script`는 `args:{data:$값}`으로 값을 명시 전달한다. 기존 저장 프로그램의 input_as는 호환 경계에서 보존한다.
원본/표시 사본을 섞거나 `$변수`의 뜻을 바꾸지 않는다. 상세는 `guides/ai_words.md`·`guides/script.md`.
구조 검사는 코드로, 의미 검수는 독립 판단으로 남기는 적용 예는 `docs/IBL_EXECUTION_EVOLUTION_IMPLEMENTATION_2026_09_23.md`.

> 옛 교훈(태그-only 시절): "engines에 이질적인 게 있다"는 관찰은 옳았고, 처음엔 *이름 이전*(화장+코퍼스 비용) 대신 태그·계약·문서로 그 다름을 *드러내는* 것으로 족하다고 봤다. 그러나 노드 on/off 요구가 생기자 태그로는 못 긋는 경계(끄기 단위)가 필요해져 결국 별도 노드로 승격했다 — 분류의 실효는 *기계가 그 구분에 작용할 때* 생긴다는 원리는 그대로다. 여기선 "작용"이 노드 토글이었다.

## 5. *용례 증류*와 *단어 주조*를 혼동하지 마라

| | 무엇 | 사전을 늘리나 | 트리거 |
|---|---|---|---|
| **용례(example) 증류** | 의도 → 어떤 *기존 단어*를 쓰나 | ❌ 안 늘림 | 새 의도여도 OK (조합 유창함을 가르침). 해마가 함 |
| **단어(action) 주조** | 새 명명 액션 생성 | ✅ 늘림 | §4 엄격 기준만 |

→ 빈도/낮은 해마 점수 트리거는 **용례 증류엔 적합, 단어 주조엔 부적합.** 같은 잣대로 보지 마라.

### 새 액션/op는 네 얼굴이 함께 살아야 한다

| 얼굴 | 정본 | AI에게 가르치는 것 |
|---|---|---|
| **몸** | handler 구현 + `_OP_DISPATCHERS` | 실제로 실행되는가 |
| **사전** | `description` + `ops.values` | 카탈로그에서 무엇이 가능한가 |
| **교재** | `ibl_usage.db`의 자연어→IBL 용례 + 재학습용 데이터 | 어떤 표현에서 이 액션/op를 떠올리는가 |
| **관측** | `ibl_param_shapes.json` + fixture 반환 shape | 어떤 인자와 반환 열을 실제로 쓰는가 |

`target_description`과 `tool_json.input_schema`에 인자를 자세히 적어도 그것만으로 에이전트의 IBL 카탈로그에 인자명이 실리는 것은 아니다. 런타임 카탈로그는 `ibl_access.render_action_line()`이 `description`·`ops.values`를 방출하고, `⟨인자: …⟩`는 코퍼스와 실행 로그에서 **관측된 키**만 `ibl_param_sweep.py`가 만든다. 같은 규율로 `⟨동반: …⟩`(그 낱말 뒤에 실제로 이어진 낱말)은 `ibl_partner_sweep.py`가 만든다 — 선언이 아니라 흔적이라 새 액션은 첫 조합이 관측될 때까지 비어 있다. 따라서 새 op의 설명만 추가하면 AI는 존재는 보되 호출 모양을 몰라 범용 크롤·셸로 우회할 수 있다. 첫 등록은 자동 증류를 기다리지 말고 `data/guides/new_action_checklist.md`에 따라 다양한 manual seed를 넣고 실제 연상 프로브를 통과시킨다.

## 6. 가능성을 여는 세 가지 모드 — *큐레이션이 어디 있는가*로 고른다

| 모드 | 무엇 | 언제 |
|---|---|---|
| **A. 어휘화** (IBL 액션) | 명명된 프리미티브 | 좋은 외부 어휘가 *없는* 접근 프리미티브, 또는 취약한 *고정* 조합 압축 |
| **B. 코드** (python-exec/nodejs) | 즉석 로직 | 이미 접근 가능한 차원 안의 *일회성* 신규 로직. 유연하나 누적 안 됨 |
| **C. 접근 + 가이드** (얇은 IBL+가이드) | 액션 1개 + 가이드 파일 | **좋은 외부 어휘가 이미 존재**할 때(Cloudflare API 등) |

**외부 어휘가 있으면 Mode C를 선호하라.** Cloudflare API는 *이미 잘 설계된 어휘*다 — 재어휘화는 중복.
액션 하나(접근) + 가이드(지식) + 모델(추론)로 그 플랫폼의 전부에 닿는다. **어휘는 *소비*하는 것이지 *재생산*하는 게 아니다.**
- Mode C는 가장 확장적: 가능성이 *가이드 쓰는 속도*(싸다)로 자란다, *액션 큐레이션 속도*(비싸다)가 아니라.
- Mode C는 사전을 작게 유지한다(§1의 성질 보존). 외부 API가 진화해도 가이드만 갱신하면 됨(액션은 안 썩음).

### Mode C의 비용(정직하게)
1. **모델이 문서 보고 조합할 만큼 좋아야 함.** 지저분한 API는 얇은 래퍼가 값을 함. (모델이 좋아질수록 C가 A를 잠식 — 좋은 방향.)
2. **세밀한 *통제* 상실.** "X에 뭐든 한다"는 단일 액션은 에이전트별 제약(`allowed_nodes`)이 어렵다. 읽기/배포를 갈라야 하면 좁은 액션이 필요. **어휘화가 때로 사는 건 표현력이 아니라 권한 제어다.**
3. 그래도 *유창함*은 용례로 누적 가능(§5).

## 7. 프롬프트 비용 — 어휘는 *상시 세금*, 가이드는 *주문형*

액션 설명은 *모든 프롬프트*의 시스템 프롬프트에 실린다(`ibl_access.render_action_line`).
Cloudflare 50개를 어휘화하면 50개 설명이 *영원히 매 프롬프트*에 붙는다 — 안 쓰는 대화에도.
가이드는 의식 에이전트가 *필요할 때만* 부른다.
→ **Mode C는 큐레이션 비용뿐 아니라 프롬프트 비용에서도 이긴다.** desc 비용은 [memory.md]·desc 길이 규율 참조.

### 7.5 관용구도 어휘다 — 상시 소개는 곧 세금 (2026-09-07 사용자 판정)

`[fn:이름]` 관용구 가운데 **시스템 프롬프트에 소개되는 것**(`ibl_examples.always_on=1`)은 실질적으로 어휘다: 매 턴 세금을 물고, 모델이 이름으로 부른다. 그러므로 §7·§8이 액션에 요구하는 규율을 그대로 받는다 — **숫자를 마구 늘릴 수 없다.**

- **입력 함수의 제한된 축적**: 명시 inputs로 성공·원천 완료한 현재 IBL은 입력 **이름만** 함수 인자로 묶을 수 있다. 본문 AST·의존성·원 실행 출처를 검증하며 값 대입, 상수 일반화, 효과 추가는 금지한다. 기존 한 번의 반성 호출이 재사용 가치를 판단하고 이름만 제안한다. 자동 상시 소개는 하지 않으며 `always_on=0`, 새 입력의 성공 실적은 0에서 시작한다. 임의 관용구 생성·낱말 자동 작명 경로는 계속 중단한다.
- **등록은 사람이**: 부정기로 에피소드 기억을 살펴 고른다 — `scripts/register_idiom.py`(관문은 자동 경로가 쓰던 그것 그대로: 구문·타입·서명·부를 수 있는가·개인 명사·이름 12자).
- **등록 자격 = 코퍼스에 실릴 만한 것**: 승격은 그 이름을 부르는 용례를 해마 코퍼스에 함께 심는다. 낱말은 문장 안에 있는 모습을 본 적 있어야 실제로 불린다(교재 조합 노출률→실행 조합률 r=0.72).
- **두 층**: `always_on=1` = 소개(어휘) / `always_on=0` = **등록만** — 이름으로 부를 수는 있으나 소개되지 않아 보통은 쓰이지 않는다. 앱 버튼처럼 명시 호출이 있는 자리가 그 층이다.
- **함수 입력 연결**: `[def:이름]($첫인자,$다른인자){...}`의 첫 인자가 파이프 자리다. 명시 인자를 선언하고 전달하며, 본문 자유 변수에서 입력을 추측하지 않는다. 기존 저장 함수는 호환 어댑터가 원래 입력·반환 계약으로 실행한다.

- **호출 교재**: 한 항목 = `[fn:이름]{슬롯: 값} → 반환` + `언제:` + 몸에서 파생한 `골격:`. 수동 선정집은 `입력:`(앞 통화·인자 종류·제약)과 `조합 예:`까지 싣는다. 관용구는 완성 과제를 대신하는 버튼이 아니라 **문장 안에서 다른 낱말·관용구와 이어 쓰는 표현**이다. 앞 통화가 있는 표현은 긴 원문이나 목록을 인자로 다시 복사하지 않는다.
- **선정·등록 입력**: `data/idioms/curated.json` → `scripts/curate_idioms.py`로 몸·서명·실재 어휘·조합 예시를 검사, `--apply --local-encoder`로 명시 반영한다. 실행 정본은 해마 원장/가지 문서이며 자동 덮어쓰지 않는다. 교재는 저장 본문과 일치할 때만 표시한다. 기존 본문 개정은 실행 이력 없는 이름에만 허용하며 SQLite 백업을 남긴다. 호출 용례는 `add_examples_batch`로 심고 전용 등록 출처의 실행 0 placeholder를 회수한다.
- **선정 기준**: 중간 판단 없이 끝나는 반복 구간, 적은 인자, 앞뒤 통화 연결, 명확한 결과·실패 계약. 등록기의 40자 절감 하한은 짧은 표현을 막았으므로 호출이 더 길어지는 경우만 거절한다. 임의 본문 생성 중단·개인 명사·사건 고정값 관문은 유지한다. 입력 함수 추출은 원문의 AST 보존을 별도로 검증한다.
- **내부 AI 호출 0**(2026-09-09 재확인): 상시 관용구 안에 원샷·AI 요약·평가 호출을 숨기지 않는다. 하위 fn·workflow·script·each·criteria까지 확인하며, 확인할 수 없는 동적 코드를 AI 없음으로 인증하지 않는다. 수동 등록 뒤 `/packages/reload`는 관용구 지도와 잎 액션 병기도 즉시 비운다. 추가 선정 3개의 입력·결과·검증은 [비-AI 관용구 확장](../../docs/IBL_IDIOM_EXPANSION_2026_09_09.md)에 기록한다.
- **목록 조회 표현 교체(2026-09-12 사용자 선정)**: `열추려보기{목록,열,개수}`(select→take), `정렬해추리기{목록,기준,내림차순,열,개수}`(sort→take→select)를 상시 소개한다. 최근 조사·쇼핑·여행에서 반복된 조합이며 AI·저장은 없다. 운영 사용 기록이 없던 `원장에누적`·`위치마다읽기`는 명시 호출용으로 내려 소개 수 6개를 유지한다. 원래 변수와 실패·잘림 표지를 보존하고, 개수는 take의 양수/음수/0 규약을 따른다. 정의·호출 용례·강등 사유는 `data/idioms/curated.json`, 결과 계약 검증은 `backend/test_idiom_list_views_2026_09_12.py`에 있다. 모델 선택률·시간 절감은 별도 실측 대상이다.
- **노출 지렛대 넷(2026-09-09, 사용자 지시 "1에서 4까지 전부")** — 09-09 노출 실험(54회)에서 자족형 관용구 둘은 적용 과제 6/6 에서 이름으로 불렸고 앞 통화를 파이프로 받는 위치마다읽기는 1/6 이었다. 그 갈림에서 집행한 규약: ①**자족형 서명** — 앞 통화에 기대는 관용구는 그 통화를 명시 슬롯으로 받는다(`위치마다읽기{위치, 개수, 줄수}`; 서명 개정은 `register_idiom.py --update --resign` 으로만, 옛 서명 용례를 이름으로 짚어 준다) ②**'언제'는 생산자가 아니라 입력 모양** — "grep 결과"가 아니라 "파일·줄번호 열이 있는 목록(grep·JSON·filter 결과)" ③**생산자가 다른 조합 용례** — 선정집 `examples[]` 로 심는다(같은 관문 통과). 회상이 손 조합을 먼저 보여 주면 상시 노출은 진다 ④**어휘 목록 병기** — 관용구는 어휘이므로 부록(`<ibl_idioms>`)만이 아니라 대체하는 **잎 액션 줄 바로 아래** `↳ 관용구 [fn:이름]{슬롯…} → 반환 :: 언제` 한 줄로 선다(어느 낱말 옆인지는 몸의 마지막 잎 액션에서 파생, 코드에 이름 없음). `build_environment(expose_idioms=False)` 가 병기·부록을 함께 끈다(노출 실험의 비노출 조건). 결과·한계 = `docs/IBL_IDIOM_EXPOSURE_LEVERS_2026_09_09.md`.

- **노출 조정(2026-09-21 사용자 선정)**: 최근 72시간에 호출이 없던 `고치고확인하기`·`미처리만고르기`는 등록과 명시 호출을 유지하고 상시 지도·잎 액션 병기에서 제외한다. `직전보고서찾아읽기`는 전역 노출로 올리지 않고 [AI 동향 보고서 가이드](../guides/ai_trend_report.md)에서 소개한다. 파일명 순서·앞 160줄 계약과 추가 열람·첫 작성 처리를 함께 안내한다. 노출 원장은 `data/idioms/curated.json`과 운영 `always_on`을 맞춘다.

## 8. 어휘는 *축적*이 아니라 *가꾸는(garden)* 것이다

- **무절제한 단어 주조 = 언어 안의 도구 폭증.** 어휘는 작업보다 *느리게(sublinear)* 자라야 자산으로 남는다.
- 규율은 *안 만드는 절제*만이 아니라 **조합/op-통합이 단어를 불필요하게 만들면 합치고 쳐내는 리팩토링.**
- **증거: 332 → 199 → 144 → 111(→ 이후 141 → 157 → 162 → 163 → 159[2026-08-05 개념중복 압축 1단계: fs_query·self:agents·run_pipeline·image_critic·output op:file 흡수] → 155[같은 날 2단계: 검색 5액션(ddg/naver/gnews/hn/guardian)→search{source} — web-kr 패키지 은퇴·guardian 은 study→web 이주] → 152[2b+슬라이드 일원화: search_books→book{source:"google"}·engines:slide·slide_shadcn→self:slide{op:create}] → **150**[영상 일원화: engines:html_video·remotion 은퇴→self:deck{op:"video"}]).** op 어휘화 + 사용성 재감사 + 안드로이드 45액션→1액션 통합으로 *더 적은 단어 + 파라미터 분기*가 *더 많은 행동*을 표현했다. 언어가 작아지며 더 강해졌다. 111에서 163으로의 재증가는 폭증이 아니라 §3의 *접근 차원* 추가(비즈니스 도메인·메신저/커뮤니티·통화 변환자·국회도서관 인물/학위논문·공개 표면 가족[포털/공개파일/가족신문/게시판]·숙박/개체해소/중고·몸 부탁·USB 손발·내 음악 등 — 갖지 못한 키·하드웨어·몸·청중을 여는 어휘)다 — 규율은 단어 수의 단조 감소가 아니라 *작업보다 느린(sublinear)* 성장이다. ([architecture_ibl_op_vocabulary], [architecture_ibl_single_action_pattern])

## 9. 왜 이게 indiebizOS에게만 가능한가 (해자)

강력한 *최소* 어휘는 *하나의 작업 분포*에 최적화돼야 한다. 플랫폼 벤더는 못 한다:
- **일반성**이 큐레이션(narrowing)을 금지 — 누구의 150개?
- **개방 세계**(MCP)가 닫힌 문법과 양립 불가 — 안 고르려고 만든 것.
- **멀티테넌트**라 어휘와 짝지을 *단일 누적 기억*이 없음.
- **락인 유인**이 깨끗한 *이식 가능* 언어와 반대.

개인은 *하나의 분포*이기에 자기 어휘를 큐레이션할 수 있다. **IBL은 그들이 만들기를 거절한 게 아니라, 그들의 형태가 못 만들게 막는 것.** ([architecture_avoid_vendor_layer], [architecture_ibl_as_vocabulary])

---

## 개선 시 의사결정 체크리스트

새 기능/도구를 IBL에 넣을지 고민될 때, 순서대로:

1. **좋은 외부 어휘(API/SDK/CLI)가 이미 있나?** → 있으면 **Mode C**(접근 액션 1개 + 가이드). 재어휘화 금지.
2. **기존 IBL 단어 + 조합으로 *짧게* 표현되나?** → 되면 **그냥 조합**(단어 만들지 마라). 자주 쓰면 *용례*로만 증류.
3. **고유 접근(키·하드웨어·계정)을 여나?** → 열면 **Mode A**(어휘화). 차원을 추가하니까.
4. **길고 깨지기 쉬운 고정 조합인가?** → 맞고 *안 변하면* Mode A(신뢰성 압축). *변하면* Mode B/조합(유연성 유지).
5. **일회성 신규 로직인가?** → **Mode B**(코드).
6. 어느 경우든 **유창함은 용례로 누적**(해마)하되 **사전은 최소로.** 조합이 흡수한 단어는 *쳐내라.*

**한 줄 요약: 외부 어휘는 빌리고(C), 기존 단어로 되면 조합하고(B/조합), 고유 접근·취약 고정 조합에만 단어를 만들어라(A) — 그리고 사전은 늘 가꿔라.**

## 액션 카테고리

전 액션(수·노드별 내역은 아래 '핵심 노드 분류' — 빌드 파생)은 프롬프트 가독성을 위해 카테고리로 그룹화된다. 카테고리는 순수 표시 목적이며, 런타임 동작에 영향을 주지 않는다. 에이전트는 항상 구체적 액션명을 직접 사용해야 한다.

| 카테고리 | 의미 | 올바른 사용 예시 |
|---------|------|----------------|
| `search` | 찾기 | `[sense:search]{query: "AI 뉴스"}` |
| `get` | 가져오기 | `[sense:stock]{op: "quote", ticker: "AAPL"}` |
| `list` | 나열하기 | `[self:blog]{op: "posts"}` |
| `create` | 만들기 | `[self:slide]{op: "create", instruction: "발표 핵심을 한 장으로"}` |
| `control` | 조작하기 | `[limbs:screen]{op: "click", x: 100, y: 200}` |
| `fs` | 파일 조작 | `[self:read]{path: "report.pdf"}` |
| `io` | 결과 출력 | `[self:write]{path: "result.md", content: "..."}` |
| `send` | 보내기 | `[others:channel_send]{channel_type: "gmail", to: "user@mail.com", subject: "제목", body: "내용"}` |

프롬프트에서 `<action-categories>` 태그로 표시되며, 각 카테고리에 속한 구체적 액션명이 나열된다. RAG 시스템이 정확한 액션명을 안내하므로, 에이전트는 카테고리명이 아닌 액션명을 직접 써야 한다.

## 액션 group

각 액션은 `group` 필드를 가진다. group은 같은 노드 안에서 액션의 소속/맥락을 나타낸다. 예: limbs 노드의 `music`은 `group: media`이므로 미디어 재생, `browser`는 `group: browser`이므로 Playwright 브라우저 자동화다.

| 노드 | 주요 group | 설명 |
|------|-----------|------|
| limbs | browser, screen, device(android), media, cctv, cloudflare, launcher | 각 제어 대상별 구분 |
| sense | investment, culture, research, location, cctv, web, real_estate, youtube, radio, shopping, world, device(phone) | 정보 소스별 구분 |
| self | photo, blog, memory, health, file, storage, schedule, workflow, event, collect, output, system | 관리 영역별 구분 |
| engines | media_produce, music, chart, web_builder, architecture | 생산물 유형별 구분 |
| others | delegation, channel, business | 소통 유형별 구분 |

## 액션 runs_on (어디서 도는가 — 폰 네이티브)

각 액션은 선택 필드 `runs_on`으로 실행 환경을 선언한다 (미지정=`anywhere`).
- `anywhere`(기본): 이식 가능 로직/HTTP. 단 handler/driver 라우터는 **검증된 폰 패키지**일 때만 폰서 실행.
- `pc_only`: 데스크톱(맥·리눅스·윈도우) 하드웨어·무거운 의존·미검증 패키지(예: `limbs:os_open`/`open_window`=데스크탑 GUI, `self:manage_events`=무거운 api_system_ai 의존). 폰서 직접 실행 못 함 → **허브(데스크톱)에 단건 라우팅**(아래 분산 IBL).
- `phone_only`: 폰 하드웨어 전용 — 현재 `limbs:phone` 하나(알림·진동·토스트·복사·TTS·앱실행 + 문자·전화는 스테이징=작성창/다이얼러를 채워 열고 전송·통화는 사용자 탭). PC에선 graceful 거부(또는 INDIEBIZ_PHONE_URL 설정 시 분산 IBL 로 폰에 포워드).
- **지표어(indexical) 감각** (2026-07-22): `sense:here`(현재위치)·`sense:see`(카메라)·`sense:listen`(마이크)는 phone_only 를 벗었다 — 뜻은 몸 독립이고("지금 나 어디?") *어떻게 답하나*만 몸마다 다르다(폰=GPS/카메라, 데스크톱=`desktop_av` 프로브). 하드웨어가 없으면 거짓말 대신 `no_hardware` 로 정직하게 통화를 돌려준다. `sense:phone`(알림 피드)은 폰이 보내는 입력이라 별개.
- **파일 듣기** (2026-09-10): `[sense:listen]{path}`는 파일 전사, `{path, question}`은 소리 내용 분석, `{path, op:"inspect"}`는 원본 신호 검사다. path 생략 시 기존 마이크 동작. 파일에 마이크는 불필요하며 실행·감독은 같은 구간 분석 증거를 재사용한다. [오디오 듣기 가이드](../guides/audio_listen.md).
<!-- RUNS_ON:START -->
- 현 분포: `anywhere` 119 · `pc_only` 48 · `phone_only` 1. (빌드 파생 — 손 수정 금지)
<!-- RUNS_ON:END -->

**분산 IBL — 액션이 실행 단위(폰↔맥 연합)**: 폰 프로파일에서 엔진(`ibl_engine.execute_ibl`)은 폰서 못 도는 액션을 거부하지 않고 **맥에 단건 위임**(`_forward_to_mac` ↔ 맥→폰 `forward_to_phone` 대칭). 이 chokepoint를 합성 code(`&`/`>>`/`??`)의 각 leaf가 거치므로 **혼합 code도 액션별로 쪼개져** 일부는 폰·일부는 맥서 실행되고 결과가 한 봉투로 결합된다(예: `[sense:weather] & [sense:world_bank]` → weather=폰·world_bank=맥). 맥 도달=`INDIEBIZ_MAC_URL`+`INDIEBIZ_MAC_PASSWORD`(원격 런처 세션), 미설정이면 graceful 에러. **맥→폰 도달(2026-06-17 라이브)**=`INDIEBIZ_PHONE_URL`+`INDIEBIZ_PHONE_TOKEN`: 폰 `phone_api` 미들웨어가 비localhost 요청에 `X-Phone-Token`을 검증(hmac.compare_digest, localhost=WebView 자기접속은 통과), 맥 `forward_to_phone`가 그 토큰을 자동 동봉. 폰 백엔드는 **앱 UI 없이 상주**(`AgentForegroundService`가 `App.ensureBackend()` 기동·START_STICKY·부팅 재기동)하고 **토큰이 있을 때만 `0.0.0.0`(LAN) 바인드**(노출과 인증을 한 묶음 — 토큰 없으면 `127.0.0.1` 전용). 빌린 산출 파일은 `_pull_remote_artifacts`로 양방향 회수(맥←phone_only·폰←mac_only). 보안: 양방향 게이트(맥→폰=토큰/폰→맥=HTTPS 터널+런처 비번), 인터넷 비노출(폰=LAN 한정), caveat=맥→폰 LAN 평문 HTTP(가정 WPA2 저위험·공용 WiFi 금지). 폰=몸(센서·신원·렌더) 자급·머리(연산)는 맥 연합 — 클라이언트-서버 아니라 주권 피어들의 협력(미래 피어=같은 뼈대+허가 층).

계기 가시성은 실행 위치와 **직교**: app 블록은 폰서 기본 노출(실행은 라우팅이 로컬/맥 결정), `app.phone_render: false`만 숨긴다(폰서 못 보여주는 출력=맥 브라우저·네이티브창, 또는 미검증 보류=ytmusic 오디오).

빌드가 `runs_on` + 검증 패키지(`build_ibl_nodes.PHONE_VERIFIED_PACKAGES`)에서 `data/phone_manifest.json`을 파생한다 —
폰 임베드 빌드의 번들 패키지·앱 계기 필터·엔진 라우팅의 단일 진실 소스. PC에선 무영향(전 액션 실행).

---

## 노드 (6-Node 구조 — Phase 25 5-Node 재구조화 + 2026-06-30 table 분리)

### 핵심 노드 분류

<!-- IBL_STATS:START -->
총 **168 액션** — sense 43 · self 52 · limbs 14 · others 17 · engines 19 · table 23
<!-- IBL_STATS:END -->
(위 줄은 빌드가 레지스트리에서 재생성 — 손 수정 금지)

(2026-08-16 **`table:rename`·`table:flatten` 신설** — 관계대수 ρ(rename)와 unnest(flatten). rename 은 *소스가 다른 통화를 join 하기 전에 키를 맞추는* 자리를 메우고, flatten 은 `[table:each]` 가 낸 중첩 결과를 한 판으로 모은다. 둘이 붙어 통화 대수가 닫힌 계급으로 완결 → 142에서 **144**. 이전: 2026-08-15 **연락처를 이웃의 op 로 흡수**: `others:contact` 은퇴 → `[others:neighbor]{op: "contact_add"|"contact_update"|"contact_delete"}`. 근거는 구조다 — contact 에는 **list op 이 없었고**(연락처는 neighbor detail 안에 실려 나온다) 전 op 가 부모 id(neighbor_id) 또는 자식 id(contact_id)를 요구했다 = 대등한 원장이 아니라 **자식 컬렉션**. `self:ledger` 의 item 이 add_image/remove_image 를 자기 op 로 갖는 것과 같은 모양. ★`self:ledger{store:"contact"}` 로 접지 않은 이유: store 축은 *대등한 원장*의 축인데 연락처는 대등하지 않다 — 넣었으면 store 가 거짓말을 시작했을 것이다. ★`others:neighbor` 자체는 유지 — `others`(타자) 노드 축이 실질 정보를 나르므로 `self:ledger` 로 옮기면 "이웃은 나다"가 된다. 코퍼스 0행(이관 없음)·메신저 계기 템플릿 2건 재배선 → 143에서 142. 이전: **지역정보 3형제 은퇴**: `sense:search_local`·`sense:local_query`·`self:local_save` + local-info 패키지 삭제. ★`search_local` 은 중복이자 **이미 죽어 있었다** — `[sense:search]{source:"naver", type:"cafe"}` 가 같은 일을 하고(라이브 대조: 후계 3건 vs 은퇴어 0건, 스크래핑 정지) 계수 19는 "호출됐다"이지 "결과를 냈다"가 아니었다. `local_save` 는 유일한 쓰기 경로인데 계수 0이고 수집 트리거가 없어 원장이 9개월 정지(최신 글 2025-11) → `local_query` 는 얼어붙은 39행을 읽고 있었다. ★부수 수리: 합성 용례 생성기 3종이 `local`(지역)을 **로컬 파일**로 오해해 `[self:local_save]{path:...}` 를 파이프 싱크로 쓰고 있었다(그 액션은 path 를 안 읽는다) → 정본인 `[self:write]` 로 교정(10건). 코퍼스 16행 중 5행은 search naver/cafe 로 이관, 11행은 후계어 없어 삭제. ★`area` 기본값이 `"오송"` 으로 하드코딩돼 있었다 — 세계의 명사가 코드에 박힌 "명사의 자리" 위반의 순수한 형태(패키지와 함께 소멸) → 146에서 143. 이전: **사업 원장 통합**: `self:business`·`business_item`·`business_document`·`work_guideline` → **`[self:ledger]{store, op}`**. 헌법 "명사의 자리" 집행 — 비즈니스·아이템·문서·지침은 *세계의 명사*라 어휘 이름이 아니라 데이터(store 라벨)가 나른다. 조항은 2026-08-06 선포인데 이 어휘들은 06-12 부터 있어 소급된 적이 없었다. ★store 는 Object Type 선언이 아닌 자유 라벨이라 "선행 명사 스키마 금지"와 충돌하지 않는다. ★저장 구조 무변경(사용자 판정): 기존 테이블로 라우팅만, 데이터 이관 0. ★부수 이득: `save`(business·item)와 `update`(document·guideline)가 같은 연산인데 이름만 달랐다 → `save` 통일. store 에 없는 op 는 가능한 op 를 알려주며 명시 거절. 코퍼스 41행 이관 → 149에서 146. 이전: **라디오 재생 제어 흡수**: `[limbs:player_status]`·`[limbs:volume]` 은퇴 → `[limbs:radio]{op:"status"|"volume"}`. 둘 다 desc 는 "음악·라디오"라고 선언하면서 구현은 라디오 모듈 전역만 만졌다(`limbs:explorer` 의 "Finder" 거짓말과 같은 부류 — 그건 이미 은퇴 사유였다). volume 의 "mpv IPC" 도 거짓(구현 docstring 이 "mpv 재시작 방식"). ★`limbs:radio_favorite` 는 **접지 않았다** — 즐겨찾기는 원장 CRUD 라 재생 제어와 `op` 축의 의미가 다르다(섞으면 한 축이 두 개념을 나른다). 코퍼스 11행 이관 시 곡/노래 의도 3행은 라디오가 아니라 `[limbs:music]{op:"queue"}` 로 정직 재배선(거짓 desc 를 보고 쓰인 행들 — 08-15 1차 "파인더→os_open" 선례). ⏳잔여 갭: 로컬 음악 재생 상태는 표면 `<audio>` 가 쥐고 있어 보고할 액션이 없다 → 151에서 149. 이전: 2026-08-15 **고차 문장**: `[table:each]{do, as, limit, on_error}` 신설 — 문장을
값으로 받는 유일한 변환자. 같은 날 M1 로 문장 자리의 이름을 `do` 하나로 통일[trigger.pipeline·
workflow.steps·schedule.pipeline·manage_events.event_action·delegate.steps 를 `do` 별칭으로 흡수 —
핸들러 읽기키는 불변]. 정본 docs/HIGHER_ORDER_SENTENCE_DESIGN.md → 150에서 151. 이전: 2026-08-05 영상 어휘 정리: engines:html_video·engines:remotion 은퇴[영상의 정본 경로=`[self:deck]{op:"video"}` 덱→나레이션 MP4 결정화, 합성 파이프라인은 함수층 잔류·remotion-video 패키지 not_installed] → 152에서 150. 같은 날 슬라이드 어휘 일원화: engines:slide·slide_shadcn→`[self:slide]{op:"create"}`[lecture_id 미지정=스크래치 덱, aesthetic 관통] → 154에서 152. 같은 날 2b: search_books→`book{source:"google"}` 흡수[classic 은 서지↔원문 동음이의로 병합 금지 판정] → 155에서 154. 같은 날 2단계: 검색 5액션[search_ddg/naver/gnews/hn/guardian]→`search{source}` 하나 — web-kr 패키지 은퇴[naver 흡수]·guardian 은 study→web 이주 → 159에서 155. 같은 날 1단계: fs_query→file_find 메타 모드·self:agents→others:agents·run_pipeline→workflow{op:run}·image_critic→image_read{op:critic}·output op:file→write[파이프 싱크 겸용] 흡수 → 163에서 159. 이전: 웹앱 등기부[self:webapp] 추가 → 162에서 163. 이전: 몸 부탁[others:ask]·USB 손발[self:limb·limbs:guestpc]·신문 발행 결정화[engines:newspaper]·내 음악[self:music] 추가 → 157에서 162. 이전: 공개 표면 가족[others: portal/showcase/family_news/bulletin/publish/follow]·숙박/개체해소/중고[sense: stay/entity/used]·공급망 게이트[self:install_lib]·아이콘[engines:icon] → 157. 이전: engines 변환자/emitter 13종을 신규 `table` 노드로 분리(2026-06-30, 노드 5→6). 이전: `self:package` 생애주기 어휘 → 143).

| 노드 | 액션 수 | 설명 | 주요 액션 |
|--------|---------|------|----------|
| `self` | 50 | 개인 도메인: 시스템 관리, 파일(읽기/쓰기/채우기/장부 부분편집), 트리거/스케줄/목표, 메모리·포식기억, **원장(`ledger` 사업·아이템·문서·지침 / `finance` 소비·소유 / `health`)**, 근거 고정 질의(notebook), 등록 스크립트(script), 폰 동기화, 내 음악, USB 손발 발급, 웹앱 등기부, 워크플로우, 패키지·라이브러리 생애주기 | read, write, edit, fill, sheet, file_find, grep, storage, trigger, schedule, workflow, goal, memory, forage, ledger, finance, health, notebook, script, slide, deck, phone_sync, music, limb, webapp, package, install_lib |
| `limbs` | 14 | 장치 제어: UI 조작(브라우저, 데스크톱 화면, 안드로이드 폰) + 폰 네이티브 동작(phone) + 게스트 PC(USB 손발) + 미디어 재생 + 창 열기 | browser, screen, android, phone, guestpc, music, radio, radio_favorite, cctv, launch, os_open, open_window, show_map, cloudflare_api |
| `sense` | 40 | 감각 확장: 외부 정보 수집(연구자·학술·부동산·숙박·중고·프리랜서·개체해소 포함) + 범용 RSS/Atom(feed) + 몸별 지표어 감각(알림·위치·마이크·카메라 — 몸마다 프로브, 없으면 정직하게 no_hardware) | search, feed, stock, company, crawl, realty, stay, used, freelance, entity, weather, researcher, paper, contest, phone, here, listen, see, host, self_check |
| `others` | 17 | 협업·통신·공개 표면: 에이전트 위임 + **이웃 몸에 자연어 부탁(ask)** + 메시지/커뮤니티 + 이웃 CRM(연락처는 `neighbor` 의 op) + 남이 브라우저로 닿는 공개 웹 표면(포털·공개파일·가족신문·게시판·발행·팔로우) | delegate, ask, channel_send, channel_read, messages, feed, board, nostr, follow, auto_response, neighbor, portal, showcase, family_news, bulletin, publish, agents |
| `engines` | 9 | 순수 미디어 생성: 이미지(생성 image_gemini·읽기/평가 image_read[op: read/critic])·아이콘·신문 발행·웹·웹컴포넌트·TTS. 슬라이드는 [self:slide]·동영상은 [self:deck]{op:"video"} 로 일원화(2026-08-05), 통화 변환 문법은 `table` 노드로 분리(2026-06-30). | image_gemini, icon, newspaper, image_read, web, web_site, web_component, tts, render_html |
| `table` | 21 | 표·통화 변환 문법(관계대수·고차 `each`·AI 변환·emitter). engines에서 분리(2026-06-30) — 무거운 engines를 꺼도(노드 on/off) 가벼운 문법은 생존. `each` 만 코어 src(table.yaml)에 사는 이유 = 실행이 `execute_ibl` 재귀라 엔진 층이 필요(패키지가 엔진을 import 하면 층 역전), 나머지는 패키지 fragment가 공급한다. | filter, sort, take, select, dedup, groupby, join, union, merge, **rename**, **flatten**, **each**, ai, brief, chart, spreadsheet, document, structure |

**Phase 25 통합 맥락:**
- source → sense(78): 외부 정보 인식의 "감각 기관" 역할
- system → self(75): 개인 영역 관리의 "자기 중심"
- interface + stream → limbs(96): 장치/미디어 조작의 "손발"
- team + messenger → others(13): 타인/협업의 "다른 개체"
- forge(46) → engines: 복잡한 프로세스를 기동시켜 결과물을 생성하는 "엔진"

**self 주요 액션:**

| 주요 액션 | 설명 | 예시 |
|----------|------|------|
| `notify_user` | 사용자에게 알림 전송 | `[self:notify_user]{message: "작업이 완료되었습니다"}` |
| `output` | 결과를 목적지로 내보냄 (op: gui/clipboard). 파일 저장은 `write`(파이프 싱크 겸용) | `[self:output]{op: "gui", content: "..."}` |
| `goal` (op: list) | 등록된 목표 목록 조회 | `[self:goal]{op: "list", status: "active"}` |
| `goal` (op: status) | 목표 상태/진행도 조회 | `[self:goal]{op: "status", goal_id: "goal_001"}` |
| `goal` (op: kill) | 목표 취소/중단 | `[self:goal]{op: "kill", goal_id: "goal_001"}` |
| `goal` (op: log) | 시도 기록 (전략 에스컬레이션) | `[self:goal]{op: "log", task_id: "T1", approach_category: "api", description: "REST 호출", result: "failure"}` |
| `goal` (op: attempts) | 시도 이력 조회 | `[self:goal]{op: "attempts", task_id: "T1"}` |

**others 주요 액션:**

| 주요 액션 | 설명 | 예시 |
|----------|------|------|
| `delegate` | 동료 에이전트에게 작업 위임 | `[others:delegate]{agent_id: "심장전문", message: "..."}` |
| `delegate` (비동기) | 에이전트에게 작업 위임 (비동기) | `[others:delegate]{agent_id: "투자컨설팅", message: "..."}` |
| `delegate_project` | 다른 프로젝트 에이전트에게 위임 | `[others:delegate]{scope: "cross", project_path: "투자/투자컨설팅", message: "..."}` |
| `channel_send` | 메시지 발송 (gmail/nostr) | `[others:channel_send]{channel_type: "gmail", to: "user@mail.com", subject: "제목", body: "내용"}` |
| `messages` | 메신저 — 대화 목록/스레드 (op 분기) | `[others:messages]{op: "inbox"}` · `[others:messages]{op: "thread", neighbor_id: 3}` |
| `feed` | 커뮤니티 피드 (IndieNet) 조회/게시 | `[others:feed]{op: "read"}` · `[others:feed]{op: "post", content: "..."}` |
| `board` | 커뮤니티 보드 관리 | `[others:board]{op: "list"}` |
| `nostr` | IndieNet/Nostr 계정 (신원·릴레이) | `[others:nostr]{op: "profile"}` · `[others:nostr]{op: "rename", name: "..."}` |
| `neighbor` | 이웃 CRM — 조회/관리 + **연락처**(op: list/detail/save/delete/favorite/merge/contact_add/contact_update/contact_delete) | `[others:neighbor]{op: "list"}` · `[others:neighbor]{op: "detail", name: "김사장"}` · `[others:neighbor]{op: "contact_add", neighbor_id: 3, contact_type: "gmail", contact_value: "a@b.c"}` |
| `auto_response` | 자동응답 토글 (PC 전용) | `[others:auto_response]{op: "status"}` · `[others:auto_response]{op: "start"}` |

### 수족 노드 — limbs (장치 제어 + 미디어 재생)

| 노드 | 액션 수 | 설명 | 주요 액션 |
|--------|---------|------|----------|
| `limbs` | 14 | UI 조작 + 폰 네이티브 동작 + 미디어 재생: 브라우저 자동화, 데스크톱 화면, 안드로이드 폰, phone(진동/알림/TTS), 게스트 PC, 음악, 라디오, CCTV | browser, screen, android, phone, guestpc, music, radio, cctv, launch |

구성: browser(op 26종 통합) + screen(데스크톱 화면) + android(폰 화면 조작) + music/radio(미디어) + cctv + launcher

| 주요 액션 | 설명 | 예시 |
|----------|------|------|
| `browser_navigate` | 웹 페이지 탐색 | `[limbs:browser]{op: "navigate", url: "https://example.com"}` |
| `snapshot` | 브라우저 페이지 스냅샷 | `[limbs:browser]{op: "snapshot"}` |
| `click` | 요소 클릭 | `[limbs:browser]{op: "click", element: "검색 버튼"}` |
| `screen` | 데스크톱 화면 제어 (op: snapshot/click/type) | `[limbs:screen]{op: "snapshot"}` |
| `android` | 안드로이드 폰 화면 조작 (op: snapshot/tap/type/swipe/key/long_press/open_app) — snapshot으로 요소 읽고 ref/좌표로 탭. 집 PC=ADB+uiautomator(USB), 폰 자신=네이티브 AccessibilityService(USB 불필요, 한글은 ACTION_SET_TEXT라 IME 불필요). 핸들러가 INDIEBIZ_PROFILE로 분기 | `[limbs:android]{op: "snapshot"}` → `{op: "tap", query: "전송"}` |
| `play` | 유튜브/라디오 재생 | `[limbs:music]{op: "play", url: "유튜브 링크"}` |
| `radio_play` | 라디오 방송 재생 | `[limbs:radio]{op: "play", station: "KBS Classic FM"}` |
| `download` | 미디어 다운로드 | `[limbs:music]{op: "download", url: "유튜브 링크"}` |

### 감각 노드 — sense (외부 정보 수집 + 내부 데이터 조회)

| 노드 | 액션 수 | 설명 | 주요 액션 |
|--------|---------|------|----------|
| `sense` | 40 | 외부 정보(웹 검색, API): 금융, 문화, 학술(연구자·논문), 법률, 통계, 부동산, 위치, CCTV, 뉴스·영상 + 폰 온디맨드 감각(알림·위치·마이크·카메라) | search, stock, company, crawl, video, realty, weather, world_bank, researcher, paper, phone, here, listen, see |

구성: 외부 정보 수집(웹 API, 크롤링) 중심. 사진/블로그/건강 등 로컬 DB 조회는 self 노드로 이동(`[self:photo]`/`[self:blog]`/`[self:health]`).

| 주요 액션 | 설명 | 예시 |
|----------|------|------|
| `search` | 통합 검색 — source: ddg(기본)/naver(한국어, type 도메인)/gnews(뉴스)/hn(Hacker News)/guardian(가디언) | `[sense:search]{source: "naver", query: "청주 맛집", type: "blog"}` |
| `stock` | 주가·시세 (op 분기) | `[sense:stock]{op: "quote", ticker: "삼성전자"}` |
| `crawl` | 웹 크롤링 | `[sense:crawl]{url: "https://..."}` |
| `company` | 기업 펀더멘털 (op 분기) | `[sense:company]{op: "profile", ticker: "삼성전자"}` |
| `video` | YouTube 동영상·채널 조회 (op 분기). `channel`은 `handle`·`url`·`channel_id` 중 하나를 받음 | `[sense:video]{op: "channel", handle: "@YouTube", limit: 3}` |
| `stay` | 숙박·단기임대 (source 분기 goodchoice/33m2/tourapi) | `[sense:stay]{region: "제주", type: "hotel"}` |
| `world_bank` | 세계은행 지표 (지표명·국가명 자연어 내부해소) | `[sense:world_bank]{indicator: "인구", country: "한국"}` |
| `researcher` | 연구자 검색 (op: find/coauthor) — 국회도서관 국가학술정보(LOSI). 동명이인을 소속·생년으로 분리, 공저자 추적. 인물 찾기 | `[sense:researcher]{op: "find", name: "홍길동"}` |
| `paper` | 학술·학위논문 검색/다운로드 (op: search/download, source 분기 openalex/arxiv/pubmed/semantic + `nanet`=국회도서관 학위논문·국내학술) | `[sense:paper]{op: "search", query: "베이지안", source: "nanet"}` |
| `phone` | 폰 컴패니언 피드 조회 (op: notifications/location/steps) — "지금 폰에 연락 오나"의 정답 소스. 컴패니언 앱이 NIP-17로 보낸 알림·위치·걸음 | `[sense:phone]{op: "notifications"}` |
| `search_photos` | 사진 검색 | `[self:photo]{op: "search", query: "가족"}` |
| `rag_search` | 블로그 RAG 검색 | `[self:memory]{op: "search", query: "AI"}` |
| `save_health` | 건강 기록 저장 | `[self:health]{op: "save", type: "blood_pressure", ...}` |
| `cctv` | CCTV/웹캠 조회 (op 분기, 좌표·playable 보장) | `[sense:cctv]{query: "광화문"}` / `[sense:cctv]{op: "nearby", lat: 37.57, lng: 126.98}` |
| `cctv` (self) | CCTV 캐시 행정 (op 분기) — stats(기본): 전체 소스 현황 / refresh: UTIC 캐시 갱신 | `[self:cctv]` / `[self:cctv]{op: "refresh"}` |

### 엔진 노드 — engines (콘텐츠 생성)

| 노드 | 액션 수 | 설명 | 주요 액션 |
|--------|---------|------|----------|
| `engines` | 9 | 순수 미디어 생성: 이미지 생성·읽기/평가, 아이콘, 신문, 웹, 웹컴포넌트, TTS, HTML 렌더링. 표 변환은 `table`, 슬라이드·영상은 `self`로 분리됨 | image_gemini, image_read, icon, newspaper, web, web_site, web_component, tts, render_html |

특징: 복잡한 프로세스를 기동시켜 결과물을 산출하는 엔진 노드.

---


## 앱 표면 노출 — `app:` 블록 (2026-06-11)

이 절은 앱 표면의 선언·입력 템플릿 계약이다. 아래 저장된 액션 템플릿의 입력 치환은
표면이 담당하며, 현재 IBL 프로그램의 문자열 보간·함수 문법과 구별한다.

액션을 **앱 모드 계기(GUI)**로 노출하려면 src 액션 정의에 선택적 `app:` 블록을 단다. 액션이 자기 입력 폼·IBL 호출 템플릿·결과 표현을 스스로 선언하고, 표면(데스크탑 `GenericInstrument.tsx` / 원격 런처 웹앱)은 이를 해석만 한다 — **app: 블록 1개 = 모든 표면에 동시 등장, 표면별 코드 0줄.**

```yaml
      crypto:
        ...                       # 일반 액션 필드
        app:
          icon: 🪙
          name: 코인              # 계기 표시명 (단독 계기는 icon+name 필수)
          order: 6                # 홈 그리드 정렬
          auto_run: true          # 열자마자 기본값으로 실행
          inputs:                 # text/select(+options_action)/chips/required/default
          - { key: coin, type: text, default: BTC, chips: [BTC, ETH] }
          action: '[sense:crypto]{coin: "$coin"}'   # $key=입력 치환, 빈 입력 파라미터 자동 제거
          view:                   # 프리미티브 목록은 아래 어휘 줄 참조(빌드 가드가 동기 검증)
          # compose: 하단 작성바 — $text=작성, {field}=드릴 데이터. 전송 후 새로고침
          # item_click.tabs: 드릴 상세 탭(대화↔이웃정보 등) — 한 액션 데이터를 탭별 view 로 분할
          # item_click.recursive: 드릴 안의 드릴이 '지금 보고 있는 화면(view 또는 tabs)'을 그대로 재사용(view 와 배타).
          #   깊이를 모르는 트리(폴더 등)를 한 벌 선언으로 탐색 — 손으로 중첩하면 그 깊이에서 막힌다.
          # form/editable_list: $field=입력값, {field}=드릴 데이터 → 저장/추가/삭제 액션 실행 후 새로고침
          - { type: metric, big: '{data.current_price_krw|num}', trend: data.change_24h_percent }
```

- view 프리미티브 15종: metric / kv / kv_list / card_list / image_grid / sparkline / list_action / thread / form / editable_list / map / calendar / group / blocks / media_player — media_player=오디오 플레이어(items의 src 필드=파일 절대경로/URL → HTML5 `<audio>`, 백엔드 `/launcher/file` 서빙 · 원격/폰 파리티), card_list=+item_click 드릴·탭·compose, image_grid=+button 행 버튼(label/action/confirm/refresh — list_action button 과 같은 어휘, 사진 빼기 등), thread=채팅 버블+status+item_button(본문이 match 정규식과 일치하는 항목에만 붙는 선언형 버튼 — label/action/refresh, 캡처 그룹은 `{match1}..{matchN}` 필드로 액션 템플릿에 공급. 계약은 매니페스트 데이터 — 예: 게시판 창고 소개의 창고이웃 등록), form=편집 필드+저장, editable_list=행 CRUD, map=leaflet 지도, calendar=월 그리드, group=파티션 콤비네이터(`by` 키 템플릿으로 items를 나눠 그룹마다 내부 `view:` 재귀 렌더 — table:groupby(집계)와 달리 멤버 유지, 뷰-계층의 groupby), blocks=**문서 IR 렌더**(heading/paragraph/list/table/quote/code/divider/image 블록 배열을 문서로 — `[self:read]{blocks:true}`·`[table:structure]` 출력 직결. 표현 언어 층위 조항의 "정적 표현 원자 공유": 페이로드 IR의 읽기 전용 부분집합이 표면 언어에도 그대로 옴).
- form 필드 11종: text / select / toggle / textarea / images / date / time / datetime / recurrence / folder / files
- ★위 두 어휘 줄은 빌드의 **뷰-어휘 문서-동기 가드**가 코드 선언(`APP_VIEW_TYPES`/`APP_FORM_FIELD_TYPES`)과 자동 대조 — `new_action_checklist.md`의 같은 줄과 함께, 뷰 어휘 변경 시 두 문서를 같이 고쳐야 빌드 통과.
- 표시 템플릿 `{path|filter}` — 필터: round/num/abs/arrow/`opt:앞,뒤`/`trunc:N`. 드릴 응답엔 클릭 행이 `_item`으로 주입.
- 리스트 프리미티브의 `from: "."` = 응답 자체를 1행으로 (단일 객체 응답에 행 버튼 달기 — 예: 신문 생성 결과에 "띄우기").
- **select 입력 2종:** ①정적 `options: [{value,label}]` (IBL 호출 없음 — 시/도·유형 등 고정 목록) ②동적 `options_action`+`options_from` (IBL로 옵션 조회; 응답이 배열이면 option_value/option_label로, 딕셔너리 `{이름:코드}`면 자동 entries 정규화). **종속(cascade):** options_action 안에 `$형제키`를 쓰면 그 형제 select가 바뀔 때 자동 재조회 — 예: 구/군 `options_action: '[sense:realty]{op:"codes", city:"$province"}'` 가 시/도 선택에 따라 갱신. 실거래가 계기가 시연.
- **인터랙티브 지도 — `map` 프리미티브 + `on:` 뷰-이벤트(2026-06-29):** `type: map`은 봉투(`from: map_data`의 center/path/origin/destination)와 마커 리스트(`markers: items`)를 leaflet으로 그린다. `on:` 맵으로 *사용자 조작을 액션으로* 흘린다 — `moveend`(지도 팬/줌 → `$lat/$lng/$radius` 주입해 재조회, 위치 입력박스 대체) / `marker_click`(마커 클릭 → IBL 템플릿 재조회 `$id/$name/$lat/$lng/$url`, **또는** `{stream: true}` = 마커 url 을 HLS 영상 오버레이로 재생, CCTV). 상호작용도 선언이다 — 표면별 코드 0. **★YAML 함정:** `on:`은 따옴표 필수(`'on':`) — 무인용은 YAML 1.1 불리언으로 파싱돼 무시된다(체커가 RED 로 차단).
- **결과-필드 동적 필터 — `filter`:** ①정적 `filter: {items: [{label,value}], key}` = 칩 클릭 시 그 값으로 *재조회*. ②동적 `filter: {from_field: <필드>}` = 결과 items 의 그 필드 distinct 값으로 칩 자동 생성 + **클라이언트 측 거르기(재조회 없음, 같은 결과 내 필터)** — 지도 마커·목록 동시 거름. 상권(category)·검색 결과 분류 등. 둘은 상호배타(체커 강제).
- 탭 계기는 여러 액션이 같은 `instrument:` id + `mode:` 이름 공유 (예: performance+exhibit → 문화공연, search_youtube+music → 유튜브 뮤직). 노드가 달라도 병합된다.
- **리모컨 의미론(2026-06-11 사용자 결정):** 부작용이 집 PC에서 일어나는 계기(라디오·유튜브뮤직 재생, 신문 띄우기)도 원격 노출 OK — `note:`로 "집 PC에서 실행됩니다" 경고만 명확히. 폰-로컬 실행은 폰 네이티브 배포의 일이므로 섞지 말 것.
- `GET /launcher/instruments`가 app: 블록을 모아 계기 매니페스트로 자동 파생 (api_launcher_web._derive_instruments).
- 정합성은 `build_ibl_nodes.py --check`의 `validate_app_blocks`가 정적 차단 (참조 액션 실존·$key↔inputs·view 어휘·계기 그룹).
- app: 블록은 에이전트 프롬프트에 직렬화되지 않는다 (프롬프트 비용 0). 해마 용례·임베딩과도 무관 — 에이전트가 호출하는 어휘가 아니라 표면이 읽는 선언이다.
- 전체 어휘 명세: `docs/REMOTE_APP_GENERIC_RENDERER_PLAN.md`.

---

## IBL 건강 유지·확인 시스템

IBL은 단순하다 — 액션 한 항목 = **세 얼굴(src 정의 ↔ tool.json 스키마 ↔ handler 구현)이 일치**하고, 자기 `returns:` 역할의 통화 계약을 지키는 것. 그래서 건강도 단순하게 — **어휘를 쓸 때 만들고, 커밋 때 강제하고, 하루 한 번 회귀 그물로 확인.** 폴링 sweep도, AI 턴도 없다(전부 AI 0). (2026-06-27 단순화)

### 용례는 계약에 기대어 있다 — 재검토 관문 (2026-09-18)

실행기억의 용례는 "이 의도엔 이 문장"이라는 주장이고 그 주장은 액션의 **행동**에 기댄다. 행동이 바뀌면 용례는 구문·인자·타입·어휘 생존이 전부 초록인 채 거짓이 된다 — 09-17 전수 정독의 H 부류 27건(`[self:memory]{op:"save"}` 가 저장을 그만둔 뒤에도 "기억해둬"에 회상되던 15건, 결제 알림 전용이 된 `sense:phone` 의 카톡·문자 용례)이 그랬고, 그 변화는 전부 사전의 계약 필드에 드러나 있었다.

- 원장 `data/ibl_example_review.json` 이 액션마다 **계약 필드의 지문**을 든다(description·target_description·implementation·returns·returns_variants·target_key·params·aliases·ops·side_effect·runs_on·router·tool). 예산·표시용 필드는 계약이 아니다.
- `build_ibl_nodes.py --check`(= pre-commit)가 지금의 지문과 대조해, 달라진 액션이 있으면 **바뀐 필드와 그 액션을 쓰는 로컬 용례 수**를 말하고 실패한다.
- 절차: `python3 scripts/iblbuild_example_review.py --show node:action` 으로 용례를 읽는다 → 거짓이 된 것을 고치거나 지운다(`add_examples_batch`·판정표) → `--ack node:action` 으로 원장을 올려 **원장도 같이 스테이지**한다. 빌드는 원장을 쓰지 않는다 — 읽었다는 서명은 읽은 쪽이 남긴다.
- 못 잡는 것: 사전은 그대로인데 핸들러만 바뀐 변화. 그 자리는 "어휘 변경 시 문서 표면 갱신 의무"(`new_action_checklist.md`)가 막는다.

### 건강의 두 종류

| 종류 | 무엇 | 언제 변하나 |
|------|------|------------|
| **구조 건강 (정적)** | 세 얼굴 정합 + `returns:` enum + fixture 완전성 | **어휘를 쓸 때만** (편집 안 하면 안 깨짐) |
| **행동 건강 (실행)** | 좋은 파라미터 하나로 실행 시 유효한 통화를 내는가 | 외부 의존(API·키·네트워크) — 실사용 시 드러남 |

### 검사는 두 군데에서만 돈다

1. **커밋 시 `scripts/build_ibl_nodes.py --check`** (pre-commit 훅, AI 0, 즉각) — 어휘가 변하는 유일한 순간을 막는다:
   - 삼각 정합: `src.tool` ↔ tool.json name, `src.ops` ↔ op.enum/default ↔ handler `_OP_DISPATCHERS`(AST)
   - `returns:` 필수·enum(`items|transform|scalar|effect`)·transform 정합
   - **fixture 완전성**: `returns: items|scalar` 액션은 `data/ibl_fixtures.json`에 fixture 또는 exempt(사유 명시) 필수 → **신규 액션이 검사망을 못 빠져나가고, 삭제 시 고아 fixture도 잡힌다.**

2. **하루 1회 `scripts/ibl_health_check.py`** (`run_daily_health_check`, AI 0, 수 분) — 그 정적·행동·흐름 검사를 회귀 그물로 한 번 더:
   - **§1A 정적**: `--check` 호출
   - **§1B 통화(fixture)**: `data/ibl_fixtures.json`의 "올바른 파라미터 예 하나"를 라이브 실행 → items 통화 유효성 단언 (GREEN/YELLOW/RED)
   - **§1C 골든 파이프**: 고정 파이프 몇 개를 돌려 `>>` 흐름 단언
   - RED면 알림 한 통(notification). GREEN이면 끝. self_checks 테이블에 기록 → x-ray 노출.

위 둘은 *구조·행동*을 본다(AI 0). 그러나 `description:` 산문은 자유 자연어라 동작이 바뀌어도(예: 통화 records/table→items) 설명이 조용히 stale해진다(좀비 어휘). 그 빈틈은 세 번째 검사가 메운다:

3. **주 1회 `backend/cognition/ibl_description_audit.py`** (`run_maintenance_bundle` 합류, 카덴스 게이트) — `--check`의 *의미* 판:
   - **결정적 교차참조**(AI 0): 설명이 가리키는 `[node:action]`이 실재하는지. 끊긴 참조(개명·삭제된 액션을 가리킴)를 LLM 없이 잡는다.
   - **의미 드리프트**(경량 LLM, role=background): 도구의 기존 봉투 계약 앵커(`_VOCAB_ANCHOR`, 언어 전체의 값 타입과는 별개)에 비춰 각 설명이 ①옛 통화 어휘 ②returns/op와 모순 을 쓰는지 플래그. *교차참조 존재 검사는 LLM에 안 맡긴다*(결정적 검사가 더 정확). 경량 모델이라 오탐 꼬리가 있어 — 구조 `--check`가 커밋을 *막는다*면 이건 self_checks에 *깃발만 꽂고*, 판단·수정은 사람.

### fixture — 행동 건강의 단일 진실 소스

`data/ibl_fixtures.json`이 액션별 **"올바른 파라미터 예 하나"**를 담는다. "좋은 입력 하나로 제대로 돌면 정상"이라는 원리 — AI가 파라미터를 추론할 필요가 없다(사람이 한 번 큐레이션). `--check`가 완전성을 강제하므로 어휘 생성·삭제 시 fixture 한 줄이 *권고가 아니라 게이트*다.
- **effect**(부작용)는 정기 실행 불가 → fixture 면제, 구조검사만.
- **transform**은 골든 파이프(§1C)로 흐름 검증.

### 라이프사이클 (어휘를 만들·고치·지울 때)

가이드가 절차를 나르고, `--check`가 빠질 수 없는 부분을 강제한다:
- **생성**: `data/guides/new_action_checklist.md` — 0.5단계(역할·통화 계약) + 2.5단계(fixture 한 줄 추가).
- **가르치기**: 같은 체크리스트의 해마 단계 — `.venv`에서 `_load_model_sync()` 후 `add_examples_batch` 단일 경로로 자연어 변형·op·인자·조합 용례를 넣고, 재학습용 데이터에도 남긴다. 이어 `scripts/ibl_param_sweep.py`로 관측 인자 표면을 갱신하고 실제 연상 검색을 확인한다. **빌드 통과는 실행 가능성, 연상 프로브는 사용 가능성**을 각각 증명한다.
- **라이브 반영**: `build_ibl_nodes.py`가 중앙 레지스트리·tool.json·문서 마커를 파생한다. `/packages/reload`는 `handler.py`만 교체하므로 `tool_*.py`·서브모듈 변경은 백엔드 재기동까지 해야 한다.
- **삭제**: `data/guides/action_removal.md` — src·tool.json·handler·**fixture** 줄 + 해마·건강기록 정리.
- 절차서·처리 플레이북: `docs/IBL_MAINTENANCE_MANUAL.md`.

### 수동 점검

- 조종실의 **🩺 건강 확인** 버튼 → `POST /world-pulse/ibl-health-check`(동기) → §1A/§1B/§1C 결과 표시.
- 또는 직접: `python scripts/ibl_health_check.py` (단독 실행, 외부 인프라 비의존 — 레지스트리 + `/ibl/execute`만).
- IBL 액션으로도: `[*:self_check]` = `run_daily_health_check`.

---


## 이전 실행 의미의 기록

구형 변수 치환·자동 통화 추출·실패 뒤 계속 실행·함수 자유 슬롯의 기록은
[저장 프로그램 참고](../../docs/compatibility/ibl_legacy_system.md)에 보존한다.
그 문법은 이미 저장된 원문을 해석할 때만 사용한다. 새 작성 교재와 모델 프롬프트에는 주입하지 않는다.


## 실행 중단과 재개

현재 IBL은 외부 호출 전후 영수증을 디스크에 보존한다. 반환된 `resume:{run_id}`를
동일한 `code`, `inputs`와 함께 보내면 완료한 호출의 값·실패·근거를 재사용하고 미실행 부분을 진행한다.
같은 인자의 반복 호출도 함수·반복·병렬 위치로 구분한다. 확인된 실패의 재개는 그 실패를 다시 보여주며,
실패한 읽기를 새로 시도하려면 별도 프로그램을 명시적으로 작성한다.
소스·입력·연결된 정의·도구 구현·주체·프로젝트·권한이 바뀌면 재개를 거절한다.
영수증 없이 실행 시작만 남은 외부 작업은 `EFFECT_UNCERTAIN`이며 자동 재실행하지 않는다.
취소 후 finally가 외부 정리를 시작한 실행도 재개를 거절한다. 외부 효과의 exactly-once 보장은 아니다.
기존 결과를 복원하는 계산도 실행 예산 안에서 진행하므로 무한 계산·행 상한 우회 수단은 아니다.
회원의 실행 기록은 기존 사적 세션 저장소에만 두며 세션 삭제·서버 재기동 시 기존 개인정보 수명대로 폐기한다.
주인 실행 기록은 백엔드 재기동을 넘는다. 상세 결과 열람은 read_result를 사용한다.
재개 지문에는 실제 참조한 함수·하위 함수·도구 계약을 포함한다. 미사용 관용구 추가는 재개를 막지 않는다.
고정된 script id는 등록 정보와 Python의 로컬 import 폐포를 추적하며, 동적 선택·동적 로딩·셸/Node는
스크립트 사전 전체를 보수적으로 묶는다. 도구 패키지 내부는 하위 모듈을 포함한 패키지 구현 경계를 유지한다.
효과가 미확정인 과거 함수의 호환 실행은 참조 함수 폐포와 함께 기존 해석기·도구·스크립트 실행 영역을 보수적으로 고정한다.

`POST /ibl/recover {run_id, project_id 또는 project_path}`는 같은 주체·프로젝트의 실행 상태,
생성·갱신·종료 시각과 마지막 영수증 위치를 조회한다. `running/completed/interrupted/uncertain/blocked`를
구분하며 `resumable`은 재개 자격 후보일 뿐 실제 소스·권한 검사 통과를 대신하지 않는다.
원래 ticket 조회 방식도 유지한다. 없는 핸들과 정리된 핸들은 `unavailable`, 재개 불가로 응답한다.

기존 일일 유지보수에서 **완료한 기록만** 30일 보존 후 정리한다. 주체·프로젝트 저장소별 512 MiB를
넘으면 완료 기록 중 오래된 것부터 정리하며, 실행 중·잠긴 기록·중단·결과 불명·정리 차단 기록은 남긴다.
보호 기록만으로 용량을 넘으면 초과 사실을 보고하고 강제 삭제하지 않는다. 오래된 상태 미표기 기록도
완료로 추정하지 않는다. 영수증에는 전체 값을 저장하며 정리를 위해 결과를 자르지 않는다.
빈 잠금 파일은 경쟁 실행의 잠금 분리를 막기 위해 유지한다. 회원 기록에는 이 보존 연장을 적용하지 않는다.

회원 AI도 현재 문법·inputs·check를 쓴다. 회원이 동봉한 새 함수와 과거 함수만 연결하며 주인 사전을 읽지 않는다.
원격 스크립트는 인증된 `/ibl/capabilities`와 `ibl-script-call/1` 계약을 확인한 뒤 원문 값을 전송한다.
회원 PC는 도우미가 광고하는 `ibl-script/2`를 확인한다. 이전 기기는 실행 전 업데이트 요구를 반환한다.
새 wire의 background, 회원 args_file, 직접 연결 불가 기기의 푸시 큐 전달은 현재 지원 범위에 포함되지 않는다.

최종 응답을 받기 전에 연결이 끊겼다면 기존 HTTP 티켓 recover의 `progress.resume` 또는
실행 궤적의 `ibl.checkpoint`에서 시작 시 발행한 run_id를 찾는다. 원래 코드를 새 실행으로 다시 보내지 않는다.
