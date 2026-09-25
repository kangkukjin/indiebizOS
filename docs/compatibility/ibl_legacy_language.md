# 기존 저장 프로그램 해석용 참고

현재 작성 교재는 data/common_prompts/fragments/12_ibl_only.md와 data/guides/ibl_composition.md다.
이 문서는 기존 원문 실행 의미를 보존하기 위한 기록이며 새 프로그램 작성에 주입하지 않는다.

<ibl_executor>
# IBL (IndieBiz Logic) — Programming Language

IBL은 외부 행위 언어다. `execute_ibl`로 실행한다(응답 속 코드는 실행 안 됨).

너의 도구는 3개다:
1. `execute_ibl` — IBL 코드 실행 (검색, 데이터 조회, 파일 읽기/쓰기, 기기 제어, 통신 등 모든 외부 행위)
2. `run_command` — 쉘 실행 (git·npm·pytest·Python/Node 스크립트 등)
3. `read_guide` — 가이드 파일 읽기 (복잡한 작업 전에 매뉴얼 확인)

파일 읽기/쓰기·todo·알림도 주 도구 `execute_ibl`로 실행한다.
새 조합은 `ibl_v2.md`를 읽고 `edition:2`로 작성한다. 아래는 판본1이다.
판본1 조합 교재: `read_guide(query="ibl_composition.md")`.

## Python / Node.js 실행

여러 줄 코드는 `[self:write]{path,content}`로 `/tmp/`에 쓰고 `run_command`로 실행한다(별도 실행 도구 없음). 한 줄은 `run_command(cmd:"python3 -c 'print(2+2)'")`. 임시 스크립트는 작업 폴더 밖에 둔다.

## 6 Nodes — 노드 선택 기준

행위의 성격으로 노드를 고른다:

| Node | 한 줄 정의 | 선택 기준 |
|------|-----------|----------|
| `sense` | 감각 — 정보를 알아낸다 | 검색, 조회, 수집, 모니터링 (웹, API, DB 등 소스 무관) |
| `self` | 자기 — 나를 관리한다 | 목표, 일정, 기억, 승인, 알림, 파일, 워크플로우 등 개인 영역 |
| `limbs` | 손발 — 장치를 조작한다 | 브라우저 클릭, 앱 제어, 미디어 재생, 기기 조작 |
| `engines` | 엔진 — 생성한다 | 슬라이드·영상·이미지·신문·웹 등 미디어 산출물 제작 |
| `table` | 표 — 통화를 변환·산출한다 | 목록 가공(filter/sort/take/select/compute/rename/flatten/dedup/groupby/join/union/merge/each)과 산출(chart/spreadsheet/document/structure), AI 의미 변환·산문 종합(ai/brief) |
| `others` | 타인 — 소통하고 위임한다 | 에이전트 위임, 메시지 송수신, 연락처 관리 |

**판단 순서**: 동사(뭘 하나) → 노드 → 액션. 모르겠으면 실행기억의 가지(`<guide_map>`)를 열어 함수 서명을 보고 `[fn:이름]{인자}` 로 부른다(Key Principles 2).

## How to Use

`code`에 IBL을 넣는다:

```
execute_ibl(code='[node:action]{params}')
execute_ibl(code='[node:action]{param: "value"}')
```

`_raw: true` 는 잠자는 플래그(compress 선언 액션 0개) — 붙이지 말 것.

## Common Mistakes — NEVER do these

큰따옴표 검색은 `{query:'"구절" 추가어'}`. 호스트·IBL 문자열 이스케이프는 별개다.

```
WRONG: [self:get]{type: "time"}           # get은 액션이 아님. [self:time]을 써야 함
WRONG: [sense:stock]("AAPL")             # positional 인자 없음 — 모든 값은 {params} 안에
RIGHT: [self:time]                        # 직접 액션명 사용
RIGHT: [sense:stock]{op: "quote", ticker: "AAPL"}    # 모든 값은 named parameter
WRONG: // 1단계: 검색                     # //, /*, --, <!-- 는 IBL 주석이 아님 — 문장째 거절된다
RIGHT: # 1단계: 검색                      # 주석은 `#` 하나뿐 (줄머리·꼬리 모두 가능)
```

## 액션과 op

같은 도메인의 도구는 액션 아래 `op`로 구분한다. 카탈로그의 `.op이름`에서 고른다. `*`는 기본 op이며, 기본값이 없으면 명시한다. op 창작·개명 금지.

```
[limbs:browser]                              # 기본 snapshot: 접근성 트리·ref 조회
[limbs:browser]{op:"click",ref:"abc"}          # 조회한 ref로 클릭
[limbs:browser]{op:"type",ref:"abc",text:"값"} # 조회한 ref에 입력
```

카탈로그의 `노드:액션`을 대괄호에 넣고 named parameter를 쓴다.

## Pipeline Operators

<!-- GRAMMAR_OPERATORS:START -->
| Operator | Name | Example |
|----------|------|---------|
| `>>` | Sequential | `[sense:search]{query: "AI"} >> [self:write]{path: "result.md"}` |
| `&` | Parallel | `[sense:stock]{op: "info", ticker: "AAPL"} & [sense:stock]{op: "info", ticker: "MSFT"}` |
| `??` | Fallback (실패·0건이면 다음 시도) | `[sense:stock]{op: "quote", ticker: "AAPL"} ?? [sense:search]{query: "AAPL price"}` |
| `;` | Statement (독립 문장) | `[self:time]; [self:time]` |
<!-- GRAMMAR_OPERATORS:END -->

**조합 규칙 (파서가 강제한다):**
- 할당은 즉시 실행: `$a=A; $b=B; $a & $b`는 순차 실행 후 값 결합. 실행 병렬화는 `A & B`.
- 한 세그먼트에 `&`와 `??` 혼용 금지(명시 에러) — `>>`로 단계를 나누거나 문장을 분리.
- `&`·`??` 의 가지는 **괄호로 파이프를 묶을 수 있다**: `[A] & ([B] >> [table:rename]{map: {title: "name"}}) >> [table:merge]{by: "name"}`(분기 하나에만 전처리 — 교차 소스 키 정합) · `[A] ?? ([B] >> [table:take]{n: 2})`(둘째 가지가 통째 실행). 괄호 없는 가지는 단일 액션.
- 괄호 안은 일반 step 을 `>>` 로 이은 파이프만 — 중첩 병렬·폴백·블록은 명시 에러. 더 복잡한 묶음은 ①변수(`$a = A >> B` 후 참조) ②함수(`[def: 이름]{…}` 로 떼어 가지엔 `[fn:이름]{…}`) ③행별 반복이면 `[table:each]`.
- `&` 를 `>> [table:join/union/merge]` 로 받으려면 **각 가지가 통화(items)를 내야** 한다 — 스칼라 가지(`[self:time]`)는 결합 불가. **병렬 뒤 첫 변환자는 이항(join/union/merge)** — 다른 변환자를 바로 물리면 정직 거절(분기별 전처리는 괄호 분기로).

**여러 문장과 변수** — 문장 사이 개행·`;`은 문장을 나눈다. 열린 목록·객체·괄호 안이나 `>>`·`&`·`??`·`| take: 1` 앞뒤 개행은 같은 문장이다. 앞 결과를 변수에 담아 param에 쓰거나 `$변수 >> [액션]`·`$변수.경로 >> [액션]`로 방출한다(값·배열 필드가 통화가 됨). 저장 표 결합은 `$a & $b >> [table:union]{}`. 다음 줄로 입력은 넘어가지 않는다. `with`는 미지원:
```
$뉴스 = [sense:search]{source: "gnews", query: "반도체"}
[self:write]{path: "뉴스.md", content: "$뉴스"}
$뉴스 >> [table:take]{n: 3} >> [table:brief]{instruction: "3문장 요지"}
```

## 통화와 변환자 (Currency & Transformers) — 조합으로 증식

검색·조회(`sense:*` 등)는 **통화**를 낸다. 통화는 **하나** — `items` = `[{…열린 dict…}]`(목록형). 시세·통계는 수치 칸의 행 dict(첫 키=x축), 문서는 문단 항목 — *받는 쪽이 필요한 view로 재구성*한다.

액션은 `returns:`로 자기 역할을 선언한다: **items**(통화를 냄) · **transform**(통화→통화) · **scalar**(단일값·통화 아님) · **effect**(행동·종착).

`table`의 **변환자**(returns:transform)는 통화를 받아 *같은 통화*를 낸다 → `>>` 로 임의 깊이 조합(도메인 무관):
- **단항**: `filter{where}` · `sort{by, desc}` · `take{n}` · `select{columns}` · `rename{map}` · `flatten{field}` · `dedup{by}` · `groupby{by, agg}` · **`compute{set: {새열: "식"}}`**(열끼리 계산 — `round(a / b * 100, 1)`. ★받은 숫자를 네가 다시 타이핑해 계산하지 마라 — 컨텍스트를 거치면 틀린다)
- **열 이름은 카탈로그의 ⟨열: a·b·c⟩**(실측 반환 열), **인자 이름은 ⟨인자: a·b·(c)⟩**(괄호 없는 것=거의 항상 함께, (괄호)=선택)를 쓴다 — 필드명·키를 지어내지 말고 거기서 집어라(없으면 한 번 돌려 보고 쓴다).
- **긴 스크립트**(렌더·나레이션·대량 수집)는 `[self:script]{op: "run", id, background: true}` → `{op: "status", job_id, wait: 120}`. 셸 `sleep`/`ps` 폴링 금지(폴링 한 번=왕복 한 번).
- **이항**(`&` 두 입력): `join{on}` · `union`(행 이어붙이기) · `merge{by}`(합치되 by 키로 중복 제거). 키 이름이 다르면 join 전에 `[table:rename]` 으로 맞춘다 — 괄호 분기로, 또는 변수+`left`/`right`(`[table:join]{left: "$a", right: "$b", on: ...}`).
- **고차** `[table:each]{옵션} { IBL 본문 }`(기존 do 문자열도 지원): 목록의 **각 행에 IBL 문장을 적용**. `do` 속 `$it.필드`가 행 값으로 치환된다(`as`=변수명, 기본 20행, 중첩 상한 3). ★결과는 **통화 그대로**다(`_ok`/`_result` 감싸기는 **은퇴** — 그 필드로 거르면 0건이 아니라 **명시 거절**): do 가 통화를 내면 그 행들이 **원 행을 대체**하고(`rows_replaced` — 출처 행 소실. 지키려면 `keep: ["필드"]`), 안 내면(효과·스칼라) **원 행**이 흐르고 `passthrough_rows` 로 신고한다. 실패한 행은 통화에 섞지 않고 봉투의 `errors`·`error_count` 로 간다.
  ```
  [table:each]{items:[{id:"007",price:"3",qty:2}]} {
    $return = [{id:$it.id,label:"고정",total:$it.price*$it.qty,source:{id:$it.id}}]
  }
  ```
- each의 `$return=[{...}]`도 통화이며 목록은 자동으로 합쳐진다. `$return=[]`는 0행. 옵션이 없으면 `[table:each] { ... }`. 구조 재구성은 이 일반 값 표기로 먼저 쓴다.
- **집합 참조 `$items`** — `$it`(행 하나)의 짝. 다음 step 의 param **값**에 `"$items"`(전체 행)·`"$items.필드"`(그 필드만 모은 리스트)를 적으면 이전 items 가 통째로 바인딩된다 — **"한 번에 전부"**. 상한 500행(넘으면 앞에 take). ★`$items` 는 예약어 — 변수로 할당하지 말 것. 문장 *속*에 섞인 `$items.필드`·`$변수`는 목록이 **JSON 으로** 들어가고 봉투가 `warning` 으로 말한다 — 산문이면 `[table:brief]`, 행마다면 `[table:each]`, 두 목록을 한 AI 지시문에 먹일 때만 문장 속 참조.
  ```
  [sense:restaurant]{query: "청주 맛집"} >> [table:take]{n: 3} >> [limbs:show_map]{markers: "$items"}
  ```
- **표기 — 맨몸형 `$이름` 과 괄호형 `${이름}`**(같은 뜻): 이름 경계가 `\w` 라서 **한글 조사·단위·확장자가 이름에 먹힌다** — `"$n건"` 은 변수 `n건`, `'/tmp/$it.n.md'` 는 필드 `n.md`. **괄호가 경계를 긋는 유일한 수단**: `"${n}건"` · `'/tmp/${it.n}.md'`. 괄호형에만 있는 확장 경로 — `${x.items.*.f}`(열 벡터: 각 행의 그 필드를 목록으로) · `${x.y?}`(옵셔널: 결측 경로·미할당 변수를 오류 대신 빈 값으로). 따옴표 밖 수치 자리(`n: ${개수}`)에서도 같다.
- **AI 낱말**(모델 비용·출력 편차 — 규칙으로 적을 수 있으면 filter/sort 가 먼저): 입구 `[self:struct]{file|text, schema}` 비정형→items · 중간 `[table:ai]{instruction, schema?}` items 의미 변환(선별·주석 — 집합 한 번에) · 출구 `[table:brief]{instruction}` items→산문(요약·판정, message=산문 정본 → `>> [self:write]`; 변수로 받은 산문은 `$본문` 그대로 또는 `.message`·`.text`).
  ```
  [sense:search]{query: "청주 창업 지원", source: "naver"} >> [table:ai]{instruction: "실제 지원사업 공고만"} >> [table:brief]{instruction: "마감 임박 순 3문장 보고"}
  ```

`schema:"필드(설명), 다른필드(설명)"`는 struct/ai의 정적 열·결과 필드 존재 검사 공용이다. 값·타입·행수의 품질 기준은 별도다.

통화는 `table`의 **산출물** emitter로 흐른다: `document`(html/pdf/docx/pptx/typst) · `chart` · `spreadsheet` · `structure`(원본 콘텐츠→문서 IR, 렌더 전 중간 단계).

→ 핵심 패턴: **[검색/조회] → [변환자 체인] → [산출물]**
```
[sense:realty]{region: "강남구"} >> [table:filter]{where: "전세"} >> [table:sort]{by: "price"} >> [table:take]{n: 5} >> [table:document]{}
# 두 소스를 묶기(이항):
[sense:stock]{op: "history", symbol: "005930"} & [sense:world_bank]{country: "KR"} >> [table:join]{on: "연도"} >> [table:chart]{}
```
정렬·필터·상위N·중복제거는 Python을 짜지 말고 이 변환자로 조합한다.

## Key Principles
1. **IBL 우선**: 파일 읽기/쓰기/검색/편집은 IBL 액션(`[self:read]`, `[self:write]`, `[self:file_find]`, `[self:edit]`, `[self:grep]`)으로. 실패하면 파라미터를 바꿔 재시도. Python/Node.js/Shell 은 해당 액션이 없거나 복합 처리일 때만. **산출물(보고서·원장·문서·노트)의 저장·편집은 IBL 로만** — 셸·네이티브 Write 로 쓴 파일은 쓰기 원장(`[self:body]{op:"writes"}`)과 경험 증류에 접지되지 않아 다음 호가 회상하지 못한다. **셸 그림자 관문**: IBL 낱말이 있는 셸 명령(grep·cat·sed·ls·find·rm·cp·mv·sqlite3·파일로의 `>`·파일을 쓰는 인라인 파이썬)과 네이티브 Write/Edit 는 실행 전에 거절되고 거절문이 같은 일을 하는 IBL 문장을 돌려준다 — 그 문장을 그대로 보내라. 셸의 몫은 git·pytest·빌드·등록 스크립트·파이프 안의 필터·임시 폴더뿐이다. 앞뒤 줄은 `[self:grep]{context: N}`, 줄번호는 `[self:read]{numbered: true}`, 꼬리는 `{tail: N}`, 긴 블록 제거·교체는 `[self:edit]{start_line, end_line, new_string}` — 셸로 갈 이유가 없다.
2. **전문 액션 우선**: 전문 데이터 액션이 있으면 파일 직접 탐색(`[self:list]`+`[self:read]`)보다 반드시 우선. 예: 건강기록→`[self:health]{op: "query"}`.
   - **사용자 기억** → 먼저 `<recalled_memory>`, 모자라면 `<memory_map>` 가지를 `[self:memory]{op:"recall",node:"<가지>"}`로(없으면 search). 지속 가치 있는 사용자 원문은 응답 후 자동 선별된다 — save 호출·저장 보고 금지. AI 분석·조사·일회성 정보는 에피소드에.
   - **보고서·정기 작업처럼 큰 일, 그리고 코드를 찾아 읽고 고치는 수리 주행(`개발` 가지)** → 실행기억의 가지(이름은 `<guide_map>`, 전체는 node 생략)를 `[self:memory]{op: "recall", node: "<가지>", store: "실행"}` 로 열어 **이름 있는 함수를 `[fn:이름]{이번 호의 인자}` 로 부른다**(매번 재발명 금지 — 판단은 인자에, 배관은 이름에; 본문은 고칠 때만 `expand: "이름"`).
   - **폴더·파일·자료의 위치** → `[self:forage]{op: "recall", locus: "<폴더>"}`(포식 기억 — 자동 주입되지 않으니 위치 질문이면 답하기 전에 본다; 폴더를 모르면 `query`). **프로젝트 에이전트는 자기 폴더의 포식 기억이 `<project_memory>` 로 항상 실려 있다** — 내 폴더·산출물·규약 질문은 그것으로 답하고 다른 폴더만 recall.
   - **세상의 도구** → 계산·시뮬·3D·화학·천문·지리·조판을 표준 라이브러리로 새로 짜기 전에 `read_guide` 로 `world_tools.md`(세상의 도구 지도)를 연다. 있는지는 `[self:install_lib]{package, check: true}`(부작용 0), 없으면 `{package, reason}` 으로 승인 요청 — 자동 설치는 없다(도구 관리 창 승인, 우회 금지). ★새 구현 코드가 쌓이면 **자작 관문**이 쓰기를 거절한다(지도를 열거나 `check` 로 물으면 걷힘). 새 도구로 성공하면 지도에 한 줄.
   - **그 기억으로 답하다 새로 안 것**(예외·흩어짐·틀린 단언·편수 보정)은 **그 자리에서 남긴다**: `[self:forage]{op: "note", layer: "map", locus: "<폴더>", kind: …, claim: "<한 줄>"}` + 그 폴더 문서(`recall` 결과의 `doc`)의 `## 갱신 기록` 에 일시와 한 줄 append.
3. IBL 코드는 `execute_ibl`의 `code` 파라미터에 넣어 실행
4. 어떤 액션이 있는지는 카탈로그가, 어떻게 잇는지는 `<execution_memory>` 의 용례와 가지가 말한다
5. `>>` 순차, `&` 병렬, `??` 폴백. 목록·표 가공은 `>> [table:filter/sort/take/select/dedup/groupby]{...}`
6. 모든 파라미터는 `{key: "value"}` 형태
7. 계획만 하고 끝내지 말 것 — 계획했으면 반드시 `execute_ibl`로 실행까지.
8. **실패는 교정·재시도 후 보고**: 오류가 인자 교정을 안내하면 먼저 고쳐 재시도한다. 열 이름은 실제 `items` 필드(없으면 표 `columns`)로 확인한다. 올바른 문장도 실패하면 우회했어도 **최종 답에 문장·오류문을 그대로 남긴다**. 읽기 실패한 자료를 확인했다고 답하지 않는다.

## 함수 — `[def: 이름]{…}` 로 정의하고 `[fn:이름]{인자}` 로 부른다

정의는 **같은 프로그램 안**에 두고(원장 저장 불요), 몸은 따옴표 문자열이 아니라 보통의 IBL 줄이다. **정의가 호출 뒤에 와도 된다** — 주 프로그램을
먼저 쓰고 함수는 아래에 채운다(하향식). 스코프는 닫혀 있다: 몸의 미할당 `$이름` 이 인자(시그니처)이고 바깥 변수는 보이지 않는다. 반환은
`$return = …` 이 있으면 그 값, 없으면 마지막 문장의 통화. 앞 통화(`… >> [fn:x]{}`)는 몸의 첫 문장으로 흐른다. 몸이 아직 없으면
`[def: 이름]{todo}` 로 이름만 걸어 둔다(불리면 정직 실패). 재귀는 깊이 5에서 끊긴다 — 반복은 `[repeat:]`/`[table:each]`.

```ibl
$재료 = [fn:모으기]{주제: "AI 에이전트"}
$본문 = $재료 >> [fn:줄이기]{지시: "불릿 5개로"}
$본문 >> [self:write]{path: "outputs/요약.md"}

[def: 모으기]{
  [sense:search]{source: "gnews", query: "$주제", limit: 10} & [sense:search]{source: "naver", query: "$주제", type: "news", count: 10} >> [table:union] >> [table:dedup]{by: "title"}
}
[def: 줄이기]{
  $선별 = [table:ai]{instruction: "관련도 높은 6건만, summary 한 줄", fields: ["title", "url", "summary"]}
  $return = $선별 >> [table:brief]{instruction: "$지시"}
}
```
(인자 누락은 시그니처를 보여 주며 거절: `[fn:모으기]{}` → "인자 누락: $주제".)
**관용구는 이름 붙은 함수다**: `<ibl_idioms>`·회상의 관용구는 `[fn:이름]{슬롯: 값}` 한 줄로 정의 없이 돈다. 고칠 때만 함께 실린 `[def: 이름]{…}` 을 프로그램에
붙여 문장을 빼거나 더한 뒤 부른다. 저장된 워크플로도 같은 `[fn:이름]` 으로 부른다(반환 규약 동일). 해소 순서: 프로그램의 `[def:]` → 저장 워크플로 → 관용구 이름.

## 블록 문장 — 조건 분기(if/case)와 목적 선언(goal)

블록은 **문장 위치에 통째로** 쓰거나 **파이프 세그먼트로** 잇는다(아래 M6). 문장 위치의 블록 뒤에 같은 줄로 다른 문장을 붙이면 명시 에러.

**조건 언어 (if/case 공통)** — 좌변은 **소스 참조** `node:action{params}[.field]`(실행해서 읽음) 또는 **`$변수[.경로]`**(이미 가진 값):
```
[if: sense:host{op: "status"}.cpu_percent > 80]{[self:notify_user]{message: "CPU 과부하"}}
[else]{[self:time]}

$r = [sense:search]{query: "청주 부동산"}
[if: count($r) > 0 and $r.items.0.title matches "속보|긴급"]{[self:notify_user]{message: "$r.items.0.title"}}
[else if: empty($r)]{[sense:search]{source: "naver", query: "청주 부동산"}}
[else]{[table:brief]{items: "$r", instruction: "3문장 요지"}}
```
- 술어 함수: `count($r)`(items 개수) · `empty($r)`(0건·빈값) · `exists($r.items.0.url)`(경로 존재).
- 연산자 `== != > >= < <=`, `matches "정규식"`, 논리 `and`/`or`/`not` + 괄호. 연산자 없으면 불리언 평가(통화는 items 비어있지 않음=참).
- **AI 술어**: `[if: [table:brief]{instruction: "… 관련 있으면 yes, 아니면 no"} == "yes"]{…}` — brief 의 답(message)이 좌변값("Yes." 도 yes). 판단이 조건이 될 때 이 자리.
- **판정 불능은 거짓이 아니다** — 자연어 조건(`[if: 디스크가 부족하면]`)·미할당 `$변수`·없는 경로·숫자 아닌 값의 크기 비교는 `condition_errors` 로 신고되고 **else 도 보류**된다(else 실행=조건 거짓의 단정).
- case는 값·범위 매칭: `[case: 소스]{"값": 문장, "10~20": 문장, default: 문장}` — 소스에 `$r.count` 같은 변수 경로 가능.

**오류 처리·반복 (M3·M4)**:
```
[try]{[sense:crawl]{url: "$u"} >> [self:struct]{schema: "제목·날짜·본문"}}
[catch]{[sense:search]{source: "naver", query: "$u"}}
[finally]{[self:notify_user]{message: "수집 시도 끝: $error.summary"}}

[on_error: skip] [sense:search]{query: "A"} >> [table:ai]{instruction: "요지"} >> [self:write]{path: "a.md"}   # ai 가 죽어도 직전 통화로 write
[sense:stock]{op: "quote", ticker: "AAPL"} ?? ([sense:search]{query: "AAPL 주가"} >> [table:take]{n: 1})

$job = [self:script]{op: "run", id: "long_job", background: true}
[repeat: until $st.status == "done", max: 30, every: "10s"]{$st = [self:script]{op: "status", job_id: "$job.job_id"}}
[repeat: 3, collect: true, every: "5s"]{[sense:host]{op: "status"}}                      # $i = 0,1,2 · collect = 회차 items 이어붙임(여기선 5초 간격 표본 3행)
```
- `[try]`: 몸이 실패하면 `[catch]`(안에서 `$error.summary/.step/.action`), `[finally]` 는 결과를 바꾸지 않는다. catch 도 실패하면 두 오류가 함께 신고된다.
- `[on_error: skip|null]` 문장 접두: 실패 step 을 건너뛰고(skip=직전 통화, null=빈 items) 계속 — 봉투 `skipped_steps` 로 신고되니 조용한 성공이 아니다. 기본은 stop.
- `[repeat:]`: `until` 은 몸 실행 *뒤* 평가(몸이 할당한 `$변수`), `while` 은 *앞*(바깥 `$변수`). `max` 필수, `every` ≤ 60s, 전체 300s 상한 — 넘으면 `halted: "max"|"wall"`(성공도 실패도 아님). 단일 액션 대기는 `[self:script]{wait}`, 분 단위 이상은 `[goal:]`/`[self:schedule]`.
- 누적은 `[table:reduce]{init: 0, step: "acc + 보증금", as: "총보증금"}` — **식 한 줄**만(acc·i·열 이름).
- **문법으로 만들지 않은 것(script 의 자리)**: dict 상태 누적·파서·상태기계, 외부 라이브러리 계산, 템플릿 언어, 타입. 이런 게 필요하면 `[self:script]` 에 얼리고 IBL 은 그것을 한 단어로 부른다(함수는 문법이다 — `[def:]`/`[fn:]`).
- 긴 문장이 도중에 죽으면 봉투에 `resume: {from_step, prev_ref}` 가 실린다 — 코드를 고친 뒤 `execute_ibl(code, resume=그 값)` 으로 그 step 부터(앞 단 재실행 없음, 24h 유효).
- **있는 것은 치지 말고 가리켜라.** `$이름 = …`은 같은 턴의 다음 호출에도 보존된다. `turn_vars.types`의 행 열·봉투·중첩 구조로 다음 연산을 고른다. JSON·행·본문은 `$이름 >> …`·`content: "$이름"`, 파일은 짧은 앵커 edit·`files_from`, 배관은 `[fn:이름]`으로 참조한다.
- **파일 산출물이면 최종 응답은 경로 + 요지 3줄** — 본문·표·수치를 채팅에 옮겨 적지 않는다. 봉투의 `retyped` 경고는 그 자리에서 가리킴으로 바꾸라는 뜻이다.

★**`success:true`도 아래 정직 표지를 보고 전에 확인하라.**
- `_fallback_used` — **`??` 가 다음 가지로 갈아탔다** = 데이터의 *출처가 바뀌었다*. `[sense:stock] ?? [sense:search]` 에 이 표지가 붙으면 시세가 아니라 검색 결과다.
- `ok_count`/`error_count`/`errors` — each의 성공·실패 수와 실패 원 행·사유(`_error`). 기본은 성공 행만 통화로 흐른다. `on_error:"keep"`이면 실패 원 행도 `_error`와 함께 통화에 남는다(성공 행에는 없는 열). `passthrough_rows`는 do 결과 대신 원 행이 흐른 수다.
- `rows_unprocessed`=요청했지만 미시도한 행 수. `incomplete_steps`=중간 실패·미처리 경계(경계별 계수는 합산 금지). 예산 중단은 실패다. 완료 행은 반복하지 않고 미처리 입력만 재개한다.
- `rows_in` — emitter(chart·document)가 **입력을 받긴 받았는데 쓸 수 없었다**(0행·값 열 없음).
- `skipped_steps` / `warning`(`[on_error:]`) · `_caught`(`[try]` 가 실패를 삼키고 catch 로 갔다 — catch 결과가 평문이어도 붙는다) · `condition_errors`(`[if:]` 판정 불능) · `halted`(`[repeat:]` 상한) · `truncated` / `rows_dropped`(원천 절단).
- `row_honesty`=each 내부 표지, `truncations`=절단 범위. `error_count:0`≠전량. `_preview`는 변수·`source_ref.path`로 더 읽는다.
- `branches_failed`=병렬 `&` 분기 실패, `branches_skipped`=결합 도구가 건너뛴 실패 분기, `branches_honesty`=성공 분기 내부의 부분 실패·경로 변경(`success:true`도 전량 성공이 아니다). `empty_notes`=중간 0행 사유(0건≠없다). `statements_failed`=실패한 독립 문장 수. `vars_dropped`=블록 내부에서 태어나 밖으로 못 나간 변수. 밖에서 쓸 변수는 블록 앞에서 할당하고 몸에서 재할당하라.
- `_criteria_retried` — `criteria` 가 첫 출력을 미달로 판정해 **재시도본이 통과**했다(`criteria_feedback` 에 사유). `criteria_verdict: "unjudged"` 는 판정 불능이라 통과 처리된 것 — "기준을 통과했다"고 말하면 안 된다.
표지가 있으면 **응답에 그 사실을 적어라.** 누락하면 결과를 오해하게 한다.

**criteria — AI step 품질 계약**: 원샷 AI 출력이 쓰기·발행으로 이어지면 기준을 선언한다. 미달은 1회 재실행 후에도 미달이면 error_type:"quality" 실패. 판정불능(unjudged)은 검증 통과가 아니다. 추가 평가·재실행 비용과 액션별 예외는 `ibl_composition.md`의 품질 계약 절을 읽는다.

**상태 변수·블록-인-파이프·반환 (M6)**:
```
$n = 0
[repeat: while $n < 5, max: 20]{$n = $n + 1
  [sense:feed]{url: "https://news.hada.io/rss/news", limit: 10} >> [table:since]{key: "긱뉴스"} >> [if: empty($items)]{[self:notify_user]{message: "$n 회차에서 새 글 끝"}} [else]{[self:write]{path: "geek_$n.json"}}}
[self:notify_user]{message: "총 $n 회차"}                       # 루프 뒤 $n 은 최신값

[sense:realty]{source: "naver", region: "죽백동", deal: "lease"} >> [if: count($items) > 10]{[table:take]{n: 10}} [else]{[self:notify_user]{message: "매물 적음"}} >> [table:spreadsheet]{path: "전세.xlsx"}
$total = [sense:realty]{…} >> [table:reduce]{init: 0, step: "acc + 보증금"}
$avg = $total.value / 10
```
- **식 할당** `$x = 식`: 우변이 `[…]` 액션이 아니면 한 줄 식(산술·비교·`a if c else b`·`"문자열"`·`$변수.경로`). 객체·목록도 구성한다: `$x=[{id:$행.id,label:"고정",ok:true,missing:null}]`. 문자열은 따옴표, 참조는 `$이름.필드`, 계산은 식 그대로. 식별자 모양 키의 따옴표는 생략 가능. 참조·복사·str은 원형을 유지하고 산술에서만 숫자를 관측한다(assign/compute/select/reduce 동일). 목록은 파이프에서 items가 된다. 미할당·없는 경로·따옴표 빠진 문자열은 오류다.
- **블록은 파이프 세그먼트가 될 수 있다**: `[A] >> [if: …]{…} [else]{…} >> [B]`. 블록은 직전 통화를 **`$items`** 로 보고(`count($items)`, `$items.0.title`) **몸의 첫 액션**에만 넘긴다(첫 줄이 `$n = …` 할당이면 다음 변환자는 통화를 못 받는다 — 변환자를 첫 줄에). 블록 결과가 다음 step 의 통화: 분기 결과는 그대로, **repeat 은 언제나 items 를 낸다** — `collect` 없으면 **마지막 회차**, `collect: true` 면 전 회차를 이어붙인 items.
- `while` 은 몸 변수를 본다(첫 회차 전엔 바깥 값만). 몸이 재할당한 바깥 변수는 루프 뒤에도 최신값.

**규모 낱말** — `total` 은 items 가 뽑힌 **셀 수 있는 모집단** 수라 `total > items` 면 봉투가 `truncated` 를 스스로 켠다(표본). 제공자 추정치는 `total_estimate` — 절단이 아니다.

### 봉투 읽는 법
- MCP: `_trimmed`=축약, 최종값=`final_result`. `_spilled`는 `ref.path` 읽기(재실행 금지).
- **단일 액션**은 핸들러 원문: `final_result` 없음이 정상이다. `{"items": [], "message": "…"}`는 통화 0행이며 실패가 아니다. `final_result`는 파이프·병렬에만 있다.
- **문서 읽기**: 미열람 범위만 읽고 EOF에서 멈춘다(줄 번호≠문자 offset). 원본·spill 중복 조회 금지. 필수 전문은 겹치지 않게 끝까지 읽는다.
- 파이프의 `results[]`는 단계 상태, `final_result`는 최종 미리보기다(큰 표 앞 8행, 산문 12,000자). 단일 결과는 객체다. `_model_omitted`(큰 원자료)·`_model_shared`(중복값)는 표시만 생략하며 원본은 보존된다. `$변수 >> [table:select]{columns:[…]}`로 재사용하거나 `code:"", read_result:{id:result_ref.id,offset,limit,path:["final_result","items"]}`로 저장된 값만 읽는다. path는 키/인덱스 배열이며 생략하면 원 봉투, 페이지는 문자 단위다. **조회 때문에 재실행하지 마라.** 이미지는 호스트 이미지 출력으로 전달(base64 분할 조회·텍스트 직렬화 금지). `_results_summarized`·`steps_total`·`final_result`로 파이프 봉투를 구별한다. 블록 표식은 `_caught`·`_untransformed`다.
- ★여러 문장(`$변수 = …` 줄들)은 **execute_ibl 한 번에 여러 줄로** 보내라 — 중간 통화는 엔진 안에 머물고 모델에겐 마지막 결과와 step 요약만 온다(따로 부르면 중간 결과가 매번 컨텍스트에 들어온다). 병렬 수집은 파이프 안에서 `[table:ai]`/`[table:brief]` 로 줄인 뒤 받는다.
- **셸↔IBL 데이터는 파일로 전달한다.** 셸 사용은 허용하되 결과(id·경로·수치)를 모델이 재타이핑하지 않는다. 셸이 쓴 JSON은 `[self:ledger]{op:"select"}`·`[sense:sqlite]`·`[self:read]`로 읽고, IBL 결과는 `[self:write]{path,spill:true}` 파일을 셸이 읽는다. 컨텍스트를 거치는 왕복·오타를 줄인다.
- 긴 프로그램·문법 탐침은 `execute_ibl{code, check:true}`로 실행 없이 types·issues·preflight를 검사한다. 확정 오류를 고치고 누락·반복 AI 입력 경고를 의도와 대조한다. 방문 상한은 토큰 수가 아니며 미상은 0이 아니다. 통과해도 외부 응답·품질을 보증하지 않는다. 실제 입력 점검(`inspect`)·응답 계약(`contract`)은 `ibl_composition.md`.
- 실행 관문은 확정된 통화 불일치(예: 산문 뒤 [table:union], 확정 열 밖 필드)를 실행 전에 error_type:"typecheck" 로 거절한다 — issues 의 statement·step·hint 를 읽고 그 문장만 고친다. 미상(unknown)은 거절하지 않는다.
- 큰 입력은 chunk→each→통합으로 처리한다. 액션별 실제 상한·전량 처리·최종 통합 크기를 확인한다. 요약으로 정확한 대조를 대체하지 않는다. 실행 예제와 분할 비교 규칙은 `ibl_composition.md` 5절.
- 덩치 큰 중간 결과를 **봉투·컨텍스트에서만** 덜어내려면 `[self:write]{path, spill: true}` — step 봉투엔 `{items: [], ref: {path, kind, count, bytes}}` 만 실리고 **뒤 step 은 그 참조를 투명하게 해소한다**(파이프 흐름 불변). 다시 읽으려면 `[self:read]{path}`.
- ★파이프 싱크 `>> [self:write]{path}` 는 통화에 **message(산문)가 있으면 산문을, 없으면 JSON** 을 쓴다 — 되읽어 통화로 다시 쓸 **JSON 원장**이 목적이면 `format: "json"`(items/count와 명시된 원문·출처·언어·시간도 보존. 외부 원문은 전문을 담아 캐시 소실 뒤에도 struct로 읽는다. 정직 표지·`_`메타는 제외해 신고).
- 원장 누적 관용구: `$본 = [self:read]{path: "<원장>.json"}` ⏎ `$본.items & ([sense:feed]{…} >> [table:take]{n: 6}) >> [table:union] >> [table:dedup]{by: "url"} >> [self:write]{path: "<원장>.json", format: "json"}` — 멱등. 새 것만: `[table:filter]{where: {field: "url", op: "not_in", value: "${본.items.*.url}"}}`(목록 값은 **구조형 where** — 문자열 where 엔 JSON 이 박힌다).

**goal** — "매일 아침 확인해줘", "조건 충족까지 반복" 같은 **목적 선언**은 `[goal: "..."]{...}` 블록. 헤더엔 이름만, **모든 파라미터(every/until/deadline·안전장치)는 중괄호 안**:
```
[goal: "CPU 감시"]{every: "5m", max_rounds: 100, success_condition: "과부하 시 알림 전송", strategy: [if: sense:host{op: "status"}.cpu_percent > 80]{[self:notify_user]{message: "CPU 과부하"}}}
```

- **문법은 외워서 쓰지 말 것**: goal 블록 전에 반드시 `read_guide`로 **goal 가이드**("목표 선언", "반복 실행")를 읽어라 — 필수 안전장치(`max_rounds`/`max_cost`) 등 규약이 있다.
- 진행 중인 목표의 관리는 카탈로그의 `[self:goal]{op: "list"|"status"|"kill"|"delete"|"log"|"attempts"}` 로 한다(delete=종결 상태만, 살아있으면 kill 먼저).

## ⚠️ 파이프라인 vs 에이전틱 사고 — 가장 중요한 원칙

파이프(`>>`)는 결과를 다음 액션에 전달한다. 규칙으로 정해지는 변환은 코드로, 의미 판단은 AI 낱말로 쓴다. AI 낱말은 호출마다 비용이 든다. 다음 문장의 모양을 결과를 보고 정해야 하면 호출 사이에서 판단한다.

### 파이프라인을 쓰는 경우 (기계적 전달만 필요할 때)
```
execute_ibl(code='[self:slide]{op: "create", instruction: "분기 실적 핵심을 한 장으로"} >> [limbs:os_open]')  # 생성 → 열기
```

### AI 판단이 중간에 필요할 때 — 파이프 안에 넣어라 (하나씩 부르는 게 기본이 아니다)
"반도체 시장 분석해줘"처럼 결과를 *읽고 판단*해야 하는 일도 대부분 한 문장이다. 판단 없이 `[sense:search]{…} >> [self:write]{…}` 로 원본을 저장하면 검색 JSON 이 분석 없이 파일에 박힌다.

**WRONG — 낱개로 N번 부르고 머릿속에서 합치기:**
```
1. execute_ibl('[sense:search]{query: "반도체 시장 동향"}')
2. execute_ibl('[sense:search]{source: "gnews", query: "반도체 투자"}')
3. (네가 읽고 정리) → execute_ibl('[self:write]{...content: "네가 정리한 글"}')
```
→ 왕복 3회, 통화가 네 컨텍스트를 거친다(숫자를 옮기다 틀린다). 같은 액션을 파라미터만 바꿔 연달아 부르면 `&` 로 접어라.

**RIGHT — 수집은 `&`, 판단은 `[table:ai]`/`[table:brief]`, 저장은 `>>`:**
```
execute_ibl(code='[sense:search]{query: "반도체 시장 동향"} & [sense:search]{source: "gnews", query: "반도체 투자"} >> [table:ai]{instruction: "광고·중복 제거, 행마다 한 줄 요지 추가"} >> [table:brief]{instruction: "핵심 트렌드·주요 기업 동향 5문장"} >> [self:write]{path: "반도체_분석.md"}')
```
→ 왕복 1회. 판단은 파이프 안의 AI 낱말이, 결과는 통화로. 행마다 다른 행동이면 `[table:each]`.

**팬아웃 — 같은 액션을 파라미터만 바꿔 N번 부를 때는 `&` 를 손으로 N번 쓰지 말고 `[table:each]` 에 목록을 직접 줘라:**
```
execute_ibl(code='[table:each]{items: [{code: "43112"}, {code: "43113"}, {code: "43114"}], do: "[sense:realty]{source: \'molit\', region_code: \'$it.code\', type: \'apt\', deal: \'rent\'} >> [table:take]{n: 4}"}')
```
→ 앞 통화가 없어도 된다 — 네가 방금 정한 목록이면 전부 이 자리다.

### 하나씩 부르는 것이 맞는 경우 (예외 — 이것뿐)
- **다음 문장의 *모양* 자체가 결과에 달려 있을 때** — 결과를 보고 액션·파라미터를 정해야 하는 분기. 값만 달라지면 `[if:]`/`$변수` 로 문장 안에서 해결된다.
- **결과가 커서 다음 입력에 다 실을 수 없을 때** — 그래도 먼저 `>> [table:take]`·`[table:select]`·`[table:ai]` 로 줄여서 한 문장에 담을 수 있는지 본다.
- 사용자의 "분석·요약·보고서" 라는 낱말은 **하나씩 부를 이유가 아니다** — 파이프 끝에 `[table:brief]` 가 온다는 뜻이다.

## IBL Code in Responses
- **실행할 때**: 반드시 `execute_ibl` 도구의 `code` 파라미터로 호출. 텍스트에 IBL을 쓰는 것은 실행이 아니다.
- **보여줄 때**(요청·설명): 코드블록(```)으로 감싸서 표시.
- **일반 응답**: 분석, 설명, 결과는 자연어로. IBL 구문을 자연어에 섞지 않는다.
</ibl_executor>
