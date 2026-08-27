---
title: IBL (IndieBiz Logic)
scope: IBL 명세, 6-Node 구조(액션 수=본문 '핵심 노드 분류' 빌드 파생), 파서/엔진/라우팅, 조합 문법(파이프·병렬·폴백·블록·고차 문장)
owner_code: ibl_engine.py, ibl_parser.py, ibl_access.py, ibl_routing.py
source_of_truth: data/ibl_nodes_src/{meta,sense,self,limbs,others,engines,table}.yaml
build_tool: scripts/build_ibl_nodes.py
last_updated: 2026-08-25
see_also: [memory.md, packages.md, technical.md]
---

# IBL (IndieBiz Logic)

> indiebizOS의 정보 흐름 추상화 언어

## IBL이 하는 일

IBL은 에이전트가 정보를 가져오고, 가공하고, 전달하는 과정을 하나의 패턴으로 표현한다.

```
[node:action]{params}
```

- **node**: 어디서 (sense, self, limbs, others, engines, table)
- **action**: 무엇을 (search, get, create, ...)
- **params**: 매개변수 ({query: "AI 뉴스", limit: 10, ...})

API든 크롤링이든 안드로이드든 DB든, 에이전트는 같은 문법으로 요청한다. 프로토콜의 차이는 드라이버가 감춘다.

> **주의**: 이전 `(target)` 문법은 더 이상 권장되지 않습니다. 이제 모든 매개변수(target 포함)는 `{}` 안에 키-값 형태로 전달합니다.

```
IBL 표현 계층:     [node:action]{params}
                         |
드라이버 계층:     http | websocket | adb | cdp | sqlite | file_io
                         |
물리 계층:         인터넷 | USB | 로컬디스크 | 프로세스간 통신
```

---

## 언어의 경계 — 표준과 사전 (헌법 조항)

브라우저 / HTML / 사용자의 HTML 파일이 서로 다른 것이듯, **하네스 / IBL 표준 / 개인 사전**은 서로 다른 층이며 섞이지 않는다. 이 구분이 두 이동성을 만든다: 다른 사용자는 같은 IBL 위에 자기 어휘를 가질 수 있고(어휘와 그에 키잉된 축적물 — 해마 코퍼스·임베딩·증류 — 은 사람을 따라감), 하네스(모델·에이전트 러너)는 갈아끼워도 언어와 축적물은 무사하다. (선행 대조군: **SQL** — 방언(사전 차이)이 심한 채로도 명세가 퍼져 이겼다. 표준 코어가 가치의 대부분을 나르면 사전 간극은 치명상이 아니다. 단, 이 명제는 측정 가능해야 한다 — "문법+기능어 코어만으로 가치의 몇 할이 나가는가"를 코퍼스에서 셀 수 있다. 반대 방향의 주의: 퍼지는 것은 *언어*이지 *프로그램*이 아니다 — 개인 사전은 수출되지 않으므로 프로그램 이식성은 목표가 아니고, 몸 사이 간극은 번역이 아니라 부탁(`[others:ask]`, 상호운용)으로 건넌다.)

**IBL 표준** — 모든 IndieBiz 인스턴스가 공유하는 언어. 두 부분:
1. **문법**: `[node:action]{params}` 패턴, 연산자(`>>` 순차, `&` 병렬, `??` 폴백, `;` 독립 문장), **병렬 괄호 분기**(`A & (B >> C) >> [table:merge]` — 분기 하나에만 전처리 파이프, 2026-08-19 개정·괄호 안=일반 step 파이프만), `$변수`(맨몸 `$이름` = 괄호 `${이름}`, 2026-08-22 — 경계가 `\w` 라 한글 조사·단위가 이름에 먹히는 것을 괄호로 끊는다)·`$file:N`, if/case/goal 블록, 파이프 설탕(`| where:` 등 → `[table:*]` desugar), **조건 언어**(2026-08-22 개정, `ibl_predicates.py`: 좌변 = `node:action{…}[.경로]` 소스 참조 | `$변수[.경로]`(앞 문장 결과, 실행 없음) | `count()`/`empty()`/`exists()` | `[table:brief]{…}` AI 술어(message 가 값) · 연산자 `== != > >= < <= matches`(정규식) · `and`/`or`/`not`·괄호 · 판정 불능≠거짓), **봉투 다이어트**(에이전트 경계의 `results[]`=step 요약·`final_result`=원형, `verbose:true` 로 원형 — 하네스 이음매 `execute_ibl` 하나의 응답 모양이라 언어 밖) · `[self:write]{spill:true}` 스필 싱크(뒤 step 엔 `{items:[], ref}` 참조만). **제어 블록**(2026-08-22 M3·M4): `[try]{…} [catch]{…} [finally]{…}`(catch 안 `$error`), `[on_error: stop|skip|null]` 문장 접두(`>>` 실패 규약 — 기본 stop, skip/null 은 건너뛴 step 을 봉투에 신고), `??` 가지의 괄호 파이프 `A ?? (B >> C)`, `[repeat: N | until 조건 | while 조건, max(필수), every(≤60s), collect, as]{…}`(문장 안 결정론 반복 — 벽시계 300s 상한 신고, 더 길면 goal/schedule). 기능어 `[table:reduce]{init, step, as}`(식 한 줄 fold). **자동 스필**(이음매 통화 200K자 초과 → `data/spill/` 참조, 소비자 투명 해소, 24h 캐시 GC)·**재개**(실패 봉투 `resume:{from_step, prev_ref}` → `execute_ibl(code, resume)`)·**트레이스백**(2026-08-27: 모든 실패 봉투에 `traceback: {frames(바깥→안쪽 경로 — pipeline·each·block·parallel·fallback·workflow), error(원형), error_type(tool_error|exception|syntax|binding|quality†), input(실패 지점 입력 통화 요약), py_tail(예외 꼬리)}` — each 행·병렬 가지 같은 부분 실패에도 예외 없이 붙는 경계 규약(동일 오류 반복은 상세를 첫 발생에만 원형, 이후 `detail_at` 참조), 다이어트 밖. †quality 는 품질 계약이 쓴다. 정본 = `docs/IBL_TRACEBACK_HANDOFF.md`)·**criteria 품질 계약**(2026-08-27 언어 개정: `criteria` 는 `project_id`·`scope` 와 같은 런타임 메타 param — leaf 액션에 선언하면 실행 직후 판정자(모델 수준=**기어 평가 축** role:evaluate — GoalEval 평가자와 같은 축, 절약·균형=경량·최대=고급)가 심사, 미달 시 사유를 instruction 에 얹어 **재시도 1회**(ai_call+instruction 선언 액션만), 그래도 미달이면 `error_type:"quality"` 실패로 그 step 이 트레이스백에 찍힌다(`rejected_result` 동봉). 판정 불능=통과+`unjudged` 신고, 재시도 통과=`_criteria_retried` 정직 표지. ★액션이 criteria 를 자기 param 으로 선언하면(image_read op:critic) 그 액션의 것 — 엔진이 가로채지 않는다. 블록에는 비적용(goal 은 자기 판정 보유). 정본 = `docs/IBL_QUALITY_CONTRACT_HANDOFF.md`) 은 엔진 규약. **M6(2026-08-22)**: 식 할당 `$n = 0` / `$n = $n + 1` / `$s = $r.count * 2`(한 줄 식, `common/safe_expr` — 우변이 액션이 아니면 식), 블록을 파이프 세그먼트로(`[A] >> [if: count($items) > 0]{…} >> [B]`, `[repeat:…]{…} >> [table:dedup]` — 블록은 직전 통화를 `$items` 로 보고 몸에 넘기며 결과가 다음 통화), `while` 이 몸 변수를 봄(회차마다 현재 값으로 몸 치환·루프 뒤 바깥 `$n` 최신값), `$return = …` 반환 규약(`[self:workflow]` run). ★블록 몸의 `$변수`는 파서가 아니라 **실행기가 실행 직전 값으로 치환**한다(안쪽 파이프 인덱스와 바깥 인덱스 충돌 방지). **예약어**(블록 키워드 — 어휘 이름으로 쓸 수 없음): `if else case goal repeat try catch finally on_error` + 변수 `$items $it $i $error $return`. 파서(`ibl_parser.py`)는 이름-무검증 — 모르는 어휘도 문법적으로 파싱한다. 개정 로드맵·집행 기록 = `docs/IBL_PROGRAM_GRADE_DESIGN.md`.
2. **기능어 코어**: `self` / `others` / `table` — 노드 yaml의 `always_on: true` 플래그가 단일 소스. 언어학의 기능어(조사·전치사)처럼 닫힌 부류라 모든 화자가 공유하며, 특히 table(통화 변환 문법)은 파이프라인 생존에 필수라 어떤 노드 선별에서도 꺼지지 않는다. table 의 17 액션 중 **`each`·`reduce` 만 코어 src(`data/ibl_nodes_src/table.yaml`)에 산다** — each 는 데이터가 아니라 *문장*을 인자로 받는 고차 어휘라 실행이 `execute_ibl` 재귀이고, reduce(2026-08-22 M5)는 한 줄 식 fold 로 조건·반복과 함께 상태를 넘기는 제어 구조의 일부라 엔진 층에 구현이 있어야 하기 때문이다(패키지가 엔진을 import 하면 층 역전). 나머지 15(변환자 11·emitter 4)는 data-ops 패키지 fragment.

**개인 사전** — 그 외 모든 내용어(sense·limbs·engines의 액션들). 정의(`ibl_nodes_src/`·패키지 `ibl_actions.yaml`)·구현(패키지 핸들러)·파라미터 별칭(`aliases:`)·프롬프트 설명까지 전부 데이터가 소유한다.

**규칙**:
- 내용어의 추가·개명·제거는 **사전 편집**이다 — yaml+핸들러만 바뀌고 파서·엔진 코드는 무수정이 불변식. 어휘 이름이 backend 코드에 박히면 경계 위반.
- 표준(문법·기능어 코어)을 바꾸는 것은 **언어 개정**이다 — 파서·desugar·always_on 플래그·이 조항·빌드의 `STANDARD_CORE_NODES` 선언을 함께, 의식적으로 바꾼다. 선언 없이 바꾸면 표준-코어 가드가 빌드를 멈춘다.
- 하네스 쪽 이음매는 `execute_ibl` 단 하나 — 하네스 기능(분류·의식·평가·회상)은 언어에 스며들지 않는다.

**집행**: 두 겹이다.
- *어휘 층* — `build_ibl_nodes.py --check`의 **표준-코어 가드**(always_on 집합 = `STANDARD_CORE_NODES` 선언 일치, 파서 desugar 타깃이 표준 코어의 실존 액션인지).
- *코드 층* (2026-08-24 추가) — `check_backend_layers.py`의 **순수 코어 폐포 가드**: 문법·통화 계약(`ibl_parser`·`ibl_envelope`·`ibl_predicates`·`ibl_ops`·`api_transforms`)의 전이 폐포가 **ibl 층 + `backend/common/` 밖으로 나가지 않는다**. 직접이든 전이든 숙주(DB·에이전트·HTTP·설정)에 닿으면 실패한다 — "표준은 몸을 몰라야 한다"를 선언이 아니라 매 빌드의 사실로 만든다. 파일 목록이 아니라 뿌리에서 뻗는 폐포라, 1500줄 규칙으로 파서가 또 쪼개져도 새 파일이 자동으로 검사에 들어온다. ★`ibl_control_blocks`·`ibl_exec_each`는 뿌리가 아니다(층-밖 의존은 0이지만 엔진·워크플로를 끌어와 실제로는 엔진 한복판이다).

둘 다 pre-commit 훅과 self-check 12h 순찰에 합류.

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
- **세계상 저장의 원리**: 세 기억이 이미 독립적으로 공유하는 규율을 따른다 — **시스템이 판정하지 않고 증거를 노출한다**(포식기억: `conf`·`freshness`·`provisional`·surface / 심층메모리: 타임스탬프 동반 회상 / 해마: success_rate 표시). 명사·관계가 새로 필요해지면 빈도가 증명했을 때(결정화 사다리) 데이터로만 추가하고, 반드시 반증 가능하게 — 신뢰도·부패 노출·폐기 사유를 달아서.
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
`$변수`(바인딩) `$items`(집합 참조 — 아래) `[if:]`/`[case:]`(분기) **`[table:each]`(적용 — 문장을 값으로 받는 고차 변환자)**
+ 접근 + 가이드다.

> **병렬 괄호 분기** (2026-08-19 상상훈련 13회차 G13-1 판정·문법 개정): `[A] & ([B] >> [table:rename]{map: {title: "name"}}) >> [table:merge]{by: "name"}` — 병렬 분기 하나에만 전처리 파이프를 붙인다. 대표 용례=교차 소스 칸 정합(다나와 `name` vs 번개장터 `title`). 괄호 안은 일반 step 을 `>>` 로 이은 파이프만(중첩 병렬·폴백·블록=명시 에러). **`??` 의 가지도 같은 괄호를 받는다** — 2026-08-22 21회차 F21-1 정정: 옛 문구는 '단일 액션만'이라 적었으나 구현은 처음부터 지원했다(실측 `[sense:stock]{op:"quote", ticker:"ZZZZ…"} ?? ([sense:search]{…} >> [table:take]{n:2})` → attempt 2 가 `node:"pipe", action:"(2단)", status:"ok"`, `_fallback_used: 2`). 병렬 뒤 첫 변환자는 이항(join/union/merge)이어야 하며 다른 변환자를 바로 물리면 검수가 경고하고 실행이 정직하게 거절한다(F13-2).

> **`$items` 집합 참조** (2026-08-16 상상훈련 G1-③ 판정): `$it`(each, 행 하나)의 짝.
> 파이프 다음 step 의 param **값**에 `"$items"`(전체 행) 또는 `"$items.필드"`(그 필드만 모은
> 리스트)를 적으면 이전 결과의 items 가 **실행 시점에 값으로** 바인딩된다 — 텍스트 치환이
> 아니다(데이터가 문장 텍스트를 통과하면 이스케이프·페이로드가 깨진다, shell-IBL 은퇴 사유).
> "행마다 하나씩"(each)과 "한 번에 전부"($items)는 다른 문형이다: 맛집 3곳을 each 로 돌리면
> 지도 3장, `[limbs:show_map]{markers: "$items"}` 면 마커 3개 달린 지도 1장. 상한 500행
> (초과=침묵 절단 대신 take 안내 거절). 행동 액션이 **핸들러 수정 없이** 파이프 하류에 서는
> 규약 — verb 마다 `_prev_result` 소비를 붙이면 비대칭(F6 부류)이 재생산되므로 언어에 한 번.
> ★`$items` 는 예약 — 변수 이름으로 할당하지 말 것(할당하면 파서의 $var 치환이 우선한다).
> **문장 *속* 목록 참조** (2026-08-23 31회차 G31-1 판정·언어 개정): `"오늘 매물: $items.title"` 처럼
> 참조가 글자 사이에 섞이면 **JSON 으로 치환되고 봉투가 그 사실을 말한다**(`list_in_text` +
> `warning`). `$변수` 도 같은 규칙 — 예약어 특수 취급 없음, 파이프 step·블록 몸·저장 워크플로우
> params 세 자리가 같은 표식. 산문 한 줄이 의도면 `[table:brief]`, 행마다면 `[table:each]{do:"…$it.필드…"}`,
> 두 목록을 한 AI 지시문에 먹이는 게 의도면 경고를 무시한다(파이프는 하나만 나르므로 이 길은
> 닫을 수 없다). 통짜 참조(`content: "$곡"`)와 스칼라 경로(`$곡.0.title`)는 조용하다 — 의도된 전달.
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

5개 몸-노드(sense·self·limbs·others·engines)는 **에이전트가 세계와 맺는 관계(작용의 거처)**로 가른다 — 지각/내 자원/세계에 작용/소통/생산. 다섯 모두 *데이터 평면 바깥의 무언가*를 건드린다. 이건 **열린 계급**(내용어)의 분류다: 도메인마다 무한히 자라는 명사들(`sense:price`, `self:photo`…). (선행 대조군: **PowerShell** — 동사는 승인 목록으로 닫았는데 명사를 안 닫아 cmdlet 수천 개로 폭증했다. IBL의 처방은 반대다: 명사는 통화 하나로 닫고, 열린 계급은 sublinear 성장 규율 + 반-어휘-증식("아니오, `[self:script]` 로 얼려라")로 다스린다. 새 액션마다 물을 질문: 새 동사인가, *명사가 동사 자리에 앉은 것*인가 — HTTP 의 `POST /doAction` 이 후자의 실물이다.)

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

`target_description`과 `tool_json.input_schema`에 인자를 자세히 적어도 그것만으로 에이전트의 IBL 카탈로그에 인자명이 실리는 것은 아니다. 런타임 카탈로그는 `ibl_access._emit_action_line()`이 `description`·`ops.values`를 방출하고, `⟨인자: …⟩`는 코퍼스와 실행 로그에서 **관측된 키**만 `ibl_param_sweep.py`가 만든다. 따라서 새 op의 설명만 추가하면 AI는 존재는 보되 호출 모양을 몰라 범용 크롤·셸로 우회할 수 있다. 첫 등록은 자동 증류를 기다리지 말고 `data/guides/new_action_checklist.md`에 따라 다양한 manual seed를 넣고 실제 연상 프로브를 통과시킨다.

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

액션 설명은 *모든 프롬프트*의 시스템 프롬프트에 실린다(`ibl_access._emit_action_line`).
Cloudflare 50개를 어휘화하면 50개 설명이 *영원히 매 프롬프트*에 붙는다 — 안 쓰는 대화에도.
가이드는 의식 에이전트가 *필요할 때만* 부른다.
→ **Mode C는 큐레이션 비용뿐 아니라 프롬프트 비용에서도 이긴다.** desc 비용은 [memory.md]·desc 길이 규율 참조.

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

각 액션은 `group` 필드를 가진다. group은 같은 노드 안에서 액션의 소속/맥락을 나타낸다. 예: limbs 노드의 `music`은 `group: media`이므로 미디어 재생, `browser`는 `group: browser`이므로 Playwright 브라우저 자동화다. discover에서 group명으로 검색할 수 있다.

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
<!-- RUNS_ON:START -->
- 현 분포: `anywhere` 114 · `pc_only` 36 · `phone_only` 1. (빌드 파생 — 손 수정 금지)
<!-- RUNS_ON:END -->

**분산 IBL — 액션이 실행 단위(폰↔맥 연합)**: 폰 프로파일에서 엔진(`ibl_engine.execute_ibl`)은 폰서 못 도는 액션을 거부하지 않고 **맥에 단건 위임**(`_forward_to_mac` ↔ 맥→폰 `forward_to_phone` 대칭). 이 chokepoint를 합성 code(`&`/`>>`/`??`)의 각 leaf가 거치므로 **혼합 code도 액션별로 쪼개져** 일부는 폰·일부는 맥서 실행되고 결과가 한 봉투로 결합된다(예: `[sense:weather] & [sense:world_bank]` → weather=폰·world_bank=맥). 맥 도달=`INDIEBIZ_MAC_URL`+`INDIEBIZ_MAC_PASSWORD`(원격 런처 세션), 미설정이면 graceful 에러. **맥→폰 도달(2026-06-17 라이브)**=`INDIEBIZ_PHONE_URL`+`INDIEBIZ_PHONE_TOKEN`: 폰 `phone_api` 미들웨어가 비localhost 요청에 `X-Phone-Token`을 검증(hmac.compare_digest, localhost=WebView 자기접속은 통과), 맥 `forward_to_phone`가 그 토큰을 자동 동봉. 폰 백엔드는 **앱 UI 없이 상주**(`AgentForegroundService`가 `App.ensureBackend()` 기동·START_STICKY·부팅 재기동)하고 **토큰이 있을 때만 `0.0.0.0`(LAN) 바인드**(노출과 인증을 한 묶음 — 토큰 없으면 `127.0.0.1` 전용). 빌린 산출 파일은 `_pull_remote_artifacts`로 양방향 회수(맥←phone_only·폰←mac_only). 보안: 양방향 게이트(맥→폰=토큰/폰→맥=HTTPS 터널+런처 비번), 인터넷 비노출(폰=LAN 한정), caveat=맥→폰 LAN 평문 HTTP(가정 WPA2 저위험·공용 WiFi 금지). 폰=몸(센서·신원·렌더) 자급·머리(연산)는 맥 연합 — 클라이언트-서버 아니라 주권 피어들의 협력(미래 피어=같은 뼈대+허가 층).

계기 가시성은 실행 위치와 **직교**: app 블록은 폰서 기본 노출(실행은 라우팅이 로컬/맥 결정), `app.phone_render: false`만 숨긴다(폰서 못 보여주는 출력=맥 브라우저·네이티브창, 또는 미검증 보류=ytmusic 오디오).

빌드가 `runs_on` + 검증 패키지(`build_ibl_nodes.PHONE_VERIFIED_PACKAGES`)에서 `data/phone_manifest.json`을 파생한다 —
폰 임베드 빌드의 번들 패키지·앱 계기 필터·엔진 라우팅의 단일 진실 소스. PC에선 무영향(전 액션 실행).

---

## 노드 (6-Node 구조 — Phase 25 5-Node 재구조화 + 2026-06-30 table 분리)

### 핵심 노드 분류

<!-- IBL_STATS:START -->
총 **151 액션** — sense 40 · self 50 · limbs 14 · others 17 · engines 9 · table 21
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

## 파이프라인

IBL 액션을 연산자로 연결하면 파이프라인이 된다.

| 연산자 | 이름 | 의미 |
|--------|------|------|
| `>>` | Sequential | 순차 실행, 이전 결과를 다음에 전달. 앞 단계가 **성공했을 때만** 다음으로 (에러 전파 방지) |
| `&` | Parallel | 동시 실행, 결과를 합침 |
| `??` | Fallback | 실패 **또는 빈 결과(0건 — items:[]·total:0)** 시 대체 실행. `>>` 는 고장만 멈춤(0건은 정상 흐름) — 두 연산자의 술어가 다르다(2026-08-08 ⑯) |
| `;` | Statement (독립 문장) | **되든 안 되든 다음.** 한 줄 안의 줄바꿈 — 개행으로 나눈 문장과 완전히 같다. 앞 문장이 실패해도 뒤 문장을 실행하고, 결과(`_prev_result`)는 경계를 넘지 않는다. 실패는 숨기지 않는다(`success:false` + `statements_failed`) |

**`>>` 와 `;` 의 차이** — `>>` 는 ①다음에 ②결과를 넘기고 ③성공했을 때만, 셋을 한 기호에 묶는다. 의존이 *없는* 순차("지우고 → 만든다", "정리하고 → 발행한다")는 `;` 다. 이게 없으면 도구마다 `missing_ok` 같은 파라미터를 새로 만들게 된다(문법 결함을 어휘로 때우는 것 = 어휘 오염).

**`&` 와 `??` 는 한 세그먼트에서 섞을 수 없다**(2026-08-05) — 두 연산자 사이 우선순위가 정의돼 있지 않아 파스 에러로 거부된다. 섞어야 하면 `>>` 로 단계를 나누거나 문장(`;`/줄바꿈)을 분리할 것. (예: `[a]{} ?? [b]{} & [c]{}` ✗ → `[a]{} ?? [b]{}` 와 `[c]{}` 를 문장 분리 ✓)

**`[table:filter]` 결측 비교 규약**(2026-08-25): 비교 필드가 없거나 값이 `null`인 행은 `!=`/`ne`와 `< <= > >=`(워드 별칭 포함)에서도 **불일치**다. 모르는 값을 “다르다”거나 더 크고 작다고 단정하지 않는다. 필드 부재와 `null`을 포함한 결측 행을 찾을 때는 구조형 `{field:"필드", op:"eq", value:null}`을 쓴다.

**`[table:join]` 관계 키 규약**(2026-08-25): items/table 어느 통화든 `null`·필드 부재·빈 문자열·공백뿐인 문자열은 **키 없음**으로 보아 조인에서 제외한다. 숫자 `0`과 불리언 `False`는 실존 키이며 문자열화한 `"0"`·`"false"`와 같은 정규화 키로 비교한다. 직접 병렬과 변수 `left/right`는 같은 입력 모양·결과 의미를 보존한다.

```
[self:delete]{path: "낡은판.html"} ; [self:read]{path: "새것.md"} >> [table:document]{format: "html"}
```
→ 삭제가 실패해도(파일이 원래 없어도) 뒤 문장은 그대로 돈다. 뒤 문장 *안*에서는 `>>` 규칙 그대로 — read 가 실패하면 document 는 안 돈다.
| `\| op:` | Pipe (통화 변환 단축) | `\| where:/sort:/take:/select:/dedup:` — 목록·표 결과를 거르고·정렬·추리는 단항 변환자 단축. 각각 `>> [table:filter/sort/take/select/dedup]{...}` 로 풀림 (ibl_parser desugar) |

**감각 피드백**: 파이프라인 실행 결과에는 모든 중간 단계의 결과가 누적되어 AI에게 전달된다. `_action_count` 필드로 파이프라인 내 총 액션 수가 반환되어, AI가 실행 규모를 파악할 수 있다.

```
# 순차: 검색 → 저장 (검색 실패 시 저장 단계는 실행되지 않음)
[sense:search]{query: "AI 뉴스"} >> [self:write]{path: "news.md"}

# 병렬: 두 검색 동시 실행
[sense:search]{query: "AI"} & [sense:search]{query: "부동산"}

# Fallback: 첫째 실패 시 둘째 시도
[sense:stock]{op: "quote", ticker: "AAPL"} ?? [sense:stock]{op: "info", ticker: "AAPL"}

# 혼합
[sense:search]{query: "AI"} & [sense:search]{query: "부동산"} >> [self:write]{path: "briefing.md"}
```

### 통화와 변환자 (Currency & Transformers)

조합성의 핵심은 **공유 통화(명사)**다. 통화는 단 하나 — **`items`** = `[{…열린 dict…}]`. (2026-06-27 단일 통화 이행 완료: 옛 records/table/document 전부 items로 흡수.) (선행 대조군: **Unix 파이프** — 통화를 바이트/줄로 정한 탓에 도구마다 자기 파서를 길렀다(awk·cut·sed = 통화 부재의 세금). 교훈은 한 층 아래에도 적용된다: item *안쪽* 칸 이름이 액션마다 제각각이면 같은 병이 통화 내부에서 재발한다 — 최소 칸 규약·발명률 감사가 그 함정 위에 서 있다.)
- 가장 흔한 관습은 카드 `{title, meta, summary, url, image?}`(검색·매물·뉴스) — 단 `title`조차 보장 아닌 **열린 항목**.
- 같은 items가 통계/시세는 **수치 칸을 담은 행 dict**(첫 키=x축)로, 문서는 **문단 항목**(type·text)으로 흐른다 — *받는 쪽(소비자)이 필요한 view로 재구성*한다.
- 액션은 `returns:` 로 자기 역할을 선언한다: **items**(생성=통화 냄) · **transform**(변환=통화→통화) · **scalar**(단일값·통화 아님) · **effect**(행동·종착).

**최소 칸 규약 (2026-08-16, 상상훈련 F1 — 병기 원칙)**: 열린 항목이되, 파이프가 실제로 무는 칸은 관습을 지킨다.
1. **제목 칸 = `title`** — native 이름 칸(`name` 등)을 가진 생산자도 `title`을 병기한다(제거 아님·추가). 계열마다 제목 칸이 다르면 교차 `each`/`join`이 매번 필드명 실측을 요구한다(실측: restaurant `name` vs 상거래 `title`).
2. **파이프가 물 수 있는 값(가격·평점·수량·날짜)은 표시 문자열(meta)에만 접지 말고 수치 칸을 병기한다** — `price`(원 단위 정수)·`rating`(수치)처럼. 가격이 `meta: "80만원 · 지역"`에만 있으면 sort/filter/비교가 원리적으로 막힌다(실측: bunjang·kmong 평점).
3. **날짜 칸 = `date`(단일 시점) / `start_date`·`end_date`(기간)** — 값은 정렬 가능한 `YYYY-MM-DD` 문자열, native 원명(`prfpdfrom`·`startDate`·`시행일자`)은 그대로 두고 *병기*한다. 시간은 도메인이 달라도 뜻이 같은 몸의 축이라 표준 칸이 정당하다 (2026-08-16 상상훈련 3회차 F1: legal 시행일이 meta 에 접혀 정렬 불가·공연/전시 union 이 같은 개념을 다른 이름으로 나름).
4. **위치 칸 = `lat`·`lng`(수치)** — 좌표를 가진 생산자는 이 이름으로 병기한다(zigbang·restaurant 선례). 시간과 같은 몸의 축. 행동 액션(show_map 등)이 파이프 하류에서 물 수 있는 유일한 좌표 규약.
5. ★**기관·지역 같은 세계의 명사 칸은 규약에 넣지 않는다** (판정 2026-08-16) — 발행기관·소관부처·회신기관은 다른 명사이고, 표준 칸에 밀어 넣으면 "명사의 자리"(세계의 명사=데이터) 위반. 필요하면 사용자가 rename 으로 그때그때 맞춘다.
6. 표시용 문자열(meta)은 자유 — 규약은 *수치·날짜·좌표의 병기*이지 표시의 통제가 아니다. 카드 4칸만 내는 생산자(수치 없는 뉴스 등)는 해당 없음.

`engines`의 **변환자**(returns:transform)는 통화를 받아 *같은 통화*를 내므로(closure) `>>`로 임의 깊이 조합된다(도메인 무관):
- **단항**(앞 결과 1개): `filter{where}` · `sort{by, desc}` · `take{n}` · `select{columns}` · `dedup{by}` · `groupby{by, agg}` — 단항은 `|` 단축 문법 지원
- **이항**(`&` 두 입력): `join{on}` · `union` · `merge`

통화는 산출물 emitter로 흐른다: `document`(html/pdf/docx/pptx/typst) · `chart` · `spreadsheet`. 패턴: **[검색/조회] → [변환자 체인] → [산출물]**. 명제="언어는 명사에 산다" — 명사(통화)가 coverage를, 변환자가 depth를 곱한다. (data-ops 패키지, 2026-06-15)

```
[sense:realty]{region: "강남구"} | where: "전세" | sort: price | take: 5 >> [table:document]{}
[sense:stock]{op: "history", symbol: "005930"} & [sense:world_bank]{country: "KR"} >> [table:join]{on: "연도"} >> [table:chart]{}
```

---

## IBL 건강 유지·확인 시스템

IBL은 단순하다 — 액션 한 항목 = **세 얼굴(src 정의 ↔ tool.json 스키마 ↔ handler 구현)이 일치**하고, 자기 `returns:` 역할의 통화 계약을 지키는 것. 그래서 건강도 단순하게 — **어휘를 쓸 때 만들고, 커밋 때 강제하고, 하루 한 번 회귀 그물로 확인.** 폴링 sweep도, AI 턴도 없다(전부 AI 0). (2026-06-27 단순화)

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
   - **의미 드리프트**(경량 LLM, role=background): 정본 어휘 앵커(`_VOCAB_ANCHOR` — 통화는 items 하나 등)에 비춰 각 설명이 ①옛 통화 어휘 ②returns/op와 모순 을 쓰는지 플래그. *교차참조 존재 검사는 LLM에 안 맡긴다*(결정적 검사가 더 정확). 경량 모델이라 오탐 꼬리가 있어 — 구조 `--check`가 커밋을 *막는다*면 이건 self_checks에 *깃발만 꽂고*, 판단·수정은 사람.

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

- 수동 모드 런처의 **🩺 건강 확인** 버튼 → `POST /world-pulse/ibl-health-check`(동기) → §1A/§1B/§1C 결과 표시.
- 또는 직접: `python scripts/ibl_health_check.py` (단독 실행, 외부 인프라 비의존 — 레지스트리 + `/ibl/execute`만).
- IBL 액션으로도: `[*:self_check]` = `run_daily_health_check`.

---

## 변수 바인딩 ($variable)

IBL 코드 내에서 액션의 실행 결과를 변수에 저장하고 이후 단계에서 참조할 수 있다.

**문법**: `$변수명 = [node:action]{params}`

```
# 검색 결과를 변수에 저장
$result = [sense:search]{query: "AI 뉴스"}

# 변수를 다음 액션에서 참조
[self:write]{path: "news.md", content: $result}
```

- `$변수명 = 액션` 형태로 할당
- `$변수명` 또는 `$변수명.필드.경로`로 이전 결과를 참조
- 파이프라인(`>>`) 없이도 중간 결과를 명시적으로 전달 가능
- 변수명 경계는 정규식 `\w` — 영문·숫자·밑줄 **그리고 한글**(유니코드 낱말 문자)

### 괄호 표기 `${변수명}` (2026-08-22)

`$변수명` 과 `${변수명}` 은 **같은 뜻**이다. 경로도 괄호 안에 넣는다 — `${r.file}`.

괄호가 필요한 이유는 경계다. 이름 경계가 `\w` 라서 한국어에서는 조사·단위가 이름에 먹힌다:

```
"$n건"      → 변수 `n건` (변수 n 뒤의 글자 '건'이 아니다)
"${n}건"    → 변수 `n` + 글자 '건'
```

영어는 공백이 경계를 대신 그어 주지만 한국어는 아니라서, 괄호가 경계를 사람이 직접 긋는
유일한 수단이다. 맨몸 표기의 경계는 **바꾸지 않았다** — 옛 문장이 뜻을 바꾸면 안 되므로,
괄호는 더하는 표기이지 고치는 표기가 아니다.

표기의 단일 진실은 `backend/common/ibl_vars.py` 다(발견 `find_names`, 치환 `sub_ref`/`sub_refs`,
통짜 판정 `is_sole_ref`). 파서·주입기·시그니처·each 행 참조·조건/식 바인딩·`$items` 예약어가
모두 이 모듈을 통해 같은 표기를 읽는다 — `$` 를 직접 정규식으로 훑는 코드를 새로 만들면
"파서는 아는데 시그니처는 모르는 변수" 가 생긴다(2026-08-22 이전에 실제로 층마다
`\w+` 와 `[^\W\d]\w*` 로 방언이 갈려 있었다).

---

## $file:N 파라미터 (파일 참조)

코드 파일이나 긴 텍스트를 IBL 파라미터로 직접 넣으면 이스케이프 문제가 발생한다. `$file:N` 메커니즘은 이를 해결한다.

**원리**: `execute_ibl`의 `files` 파라미터로 코드/긴 텍스트를 별도 전달하고, IBL 코드 내에서 `$file:0`, `$file:1` 등의 플레이스홀더로 참조한다. IBL 파서가 `$file:N`을 만나면 `files[N]`의 실제 내용으로 치환한다.

```
# execute_ibl 호출 시
{
  "ibl_code": "[self:write]{path: \"script.py\", content: $file:0}",
  "files": ["print('hello world')\nfor i in range(10):\n    print(i)"]
}
```

- `$file:0` → files 배열의 첫 번째 항목으로 치환
- `$file:1` → files 배열의 두 번째 항목으로 치환
- 이스케이프 문제 없이 코드, JSON, 마크다운 등 모든 텍스트를 안전하게 전달 가능

---

## 워크플로우 — 이름 붙은 함수 (2026-08-22 개정)

자주 쓰는 문장을 YAML로 저장해두면 한 줄로 실행할 수 있다.

```yaml
# data/workflows/news_briefing.yaml
name: "뉴스 브리핑"
pipeline: '[sense:search]{query: "AI 뉴스"} & [sense:search]{query: "부동산 뉴스"}'
```

실행: `[self:workflow]{op: "run", name: "news_briefing"}`

steps 형식도 지원:

```yaml
name: "주가 확인"
steps:
  - node: sense
    action: price
    target: "삼성전자"
```

### 함수의 다섯 부품

워크플로우는 "이름 붙은 문장"에서 **함수**로 한 칸 옮겨졌다. 다섯 부품 중 넷은 이미 있었고(이름·인자·반환값·스코프), 2026-08-22에 시그니처와 재귀 안전이 채워졌다.

| 부품 | 모양 |
|------|------|
| 이름 | `name` 또는 `workflow_id` (`do` 를 직접 주면 저장 없는 즉석 실행) |
| 인자 | 몸통에 남은 **미할당 `$이름`** = 자유 변수. `save` 가 `params_required` 로 계산·저장, `list`/`get` 이 노출 |
| 기본값 | 저장본의 `params_default: {이름: 값}` — 호출자 `params` 가 이긴다 |
| 반환값 | 몸통 마지막 문장의 통화. `$return = …` 이 있으면 그 결과(마지막이 effect 여도 됨) |
| 스코프 | `execute_pipeline` 의 `step_results` 가 run 마다 새로 나는 지역 dict — 호출 경계가 닫혀 있다. 블록(`_nest`)은 바깥 변수를 계승하지만 워크플로우 경계는 불투명 |

```ibl
[self:workflow]{op: "save", name: "맛집", do: "[sense:search]{query: \"${city} 맛집\"} >> [table:take]{n: 5}"}
→ params_required: ["city"]

[self:workflow]{op: "run", name: "맛집", params: {"city": "수원"}} >> [table:brief]{}
```

- **누락은 정직 거절**: 저장본 `run` 은 인자가 비면 실패한다(`params_missing` + 시그니처를 응답에 동봉). 저장이라는 *선언 시점*이 있기 때문이다. 즉석 `run`(`do` 직접)은 선언 시점이 없어 `params_warning` 만 붙인다.
- **한글 조사·단위 함정**: 변수 이름 경계가 `\w` 라 `"$n건"` 은 변수 `n건` 으로 읽힌다 → 괄호형 `"${n}건"` 으로 끊는다.
- **재귀·순환 가드**(`backend/ibl/workflow_contract.py`): 같은 id 재진입은 경로를 보여주며 즉시 거절(직접·상호 모두), 중첩 깊이 상한은 5. 반복은 `[repeat:]` / `[table:each]` 로 쓴다. ★중첩 실행 깊이(`MAX_NEST_DEPTH`)는 몸통에서 0으로 재시작한다 — "긴 절차는 워크플로우에 저장해 id 로 부르라"는 탈출구 안내를 지키려면 그래야 하고, 그래서 워크플로우 호출 자체를 세는 별도 스택(`_wf_stack`)이 있다.
- **합성**: `run` 은 몸통 마지막 문장의 items 를 통화로 내므로 `[self:workflow]{op:"run", …} >> [table:*]` 로 이어 쓸 수 있다(effect 로 끝나는 몸통이면 통화 없음).

---

## 액션 스코프 (Phase 30)

액션마다 데이터 경계가 다르다. 모든 액션이 특정 프로젝트의 폴더에서 작동하는 건 아니고, 인스턴스 전체에 걸친 워크스페이스에서 작동하거나 indiebizOS 자체를 다루는 액션도 있다. `data/ibl_nodes_src/<node>.yaml`에 `scope`를 명시.

| scope | 의미 | base path | 용도 예시 |
|-------|------|-----------|----------|
| `project` (기본) | 특정 프로젝트의 데이터 | 활성 프로젝트 폴더 | `self:read`, `self:write` — 프로젝트 폴더 안 파일 |
| `workspace` | 인스턴스 전체에 걸친 데이터 | `get_base_path()` (indiebizOS 루트 / userData) | `self:lecture_list`, `self:lecture_open` — `outputs/lectures/` |
| `system` | indiebizOS 자체 작업 | `get_base_path()` | 설정·패키지 관리 등 (향후 권한 모델 분리 예정) |

**선언 위치** — `ibl_nodes_src/<node>.yaml`에 두 곳에 쓸 수 있음:
- **노드 레벨** (전체 액션 기본값): 해당 노드 dict 안에 `scope: workspace`
- **액션 레벨** (개별 오버라이드): 해당 액션 dict 안에 `scope:`

```yaml
self:
  scope: workspace        # 이 노드의 모든 액션 기본값
  actions:
    lecture_list: { router: handler, tool: lecture_list, ... }
    lecture_create: { router: handler, tool: lecture_create, ... }
    special_action:
      router: handler
      tool: special
      scope: project      # 이 액션만 오버라이드
```

**라우팅 동작** — `_route_handler`(`backend/ibl/ibl_routing.py`)가 scope를 보고:
- `project`: `resolve_project_path` 4단 폴백 (인자 → thread_context → params.project_path → params.project_id). 모두 실패하면 에러.
- `workspace`/`system`: `get_base_path()`를 ToolContext에 주입. project_path/project_id 무시 — 의도적 격리.

**왜 필요한가** — 강의 만들기 워크스페이스 같은 패키지는 `outputs/lectures/` 같은 공유 폴더에 데이터를 두는데, 라우팅이 이를 모르고 모든 액션에 프로젝트 컨텍스트를 강요하면 AI가 "프로젝트 하나 골라서 컨텍스트 끌어오기" 같은 부자연스러운 우회를 한다. scope 선언으로 이 마찰을 제거.

---

## 앱 표면 노출 — `app:` 블록 (2026-06-11)

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
          action: '[sense:crypto]{coin_id: "$coin"}'   # $key=입력 치환, 빈 입력 파라미터 자동 제거
          view:                   # 프리미티브 목록은 아래 어휘 줄 참조(빌드 가드가 동기 검증)
          # compose: 하단 작성바 — $text=작성, {field}=드릴 데이터. 전송 후 새로고침
          # item_click.tabs: 드릴 상세 탭(대화↔이웃정보 등) — 한 액션 데이터를 탭별 view 로 분할
          # item_click.recursive: 드릴 안의 드릴이 '지금 보고 있는 화면(view 또는 tabs)'을 그대로 재사용(view 와 배타).
          #   깊이를 모르는 트리(폴더 등)를 한 벌 선언으로 탐색 — 손으로 중첩하면 그 깊이에서 막힌다.
          # form/editable_list: $field=입력값, {field}=드릴 데이터 → 저장/추가/삭제 액션 실행 후 새로고침
          - { type: metric, big: '{data.current_price_krw|num}', trend: data.change_24h_percent }
```

- view 프리미티브 15종: metric / kv / kv_list / card_list / image_grid / sparkline / list_action / thread / form / editable_list / map / calendar / group / blocks / media_player — media_player=오디오 플레이어(items의 src 필드=파일 절대경로/URL → HTML5 `<audio>`, 백엔드 `/launcher/file` 서빙 · 원격/폰 파리티), card_list=+item_click 드릴·탭·compose, image_grid=+button 행 버튼(label/action/confirm/refresh — list_action button 과 같은 어휘, 사진 빼기 등), thread=채팅 버블+status, form=편집 필드+저장, editable_list=행 CRUD, map=leaflet 지도, calendar=월 그리드, group=파티션 콤비네이터(`by` 키 템플릿으로 items를 나눠 그룹마다 내부 `view:` 재귀 렌더 — table:groupby(집계)와 달리 멤버 유지, 뷰-계층의 groupby), blocks=**문서 IR 렌더**(heading/paragraph/list/table/quote/code/divider/image 블록 배열을 문서로 — `[self:read]{blocks:true}`·`[table:structure]` 출력 직결. 표현 언어 층위 조항의 "정적 표현 원자 공유": 페이로드 IR의 읽기 전용 부분집합이 표면 언어에도 그대로 옴).
- form 필드 10종: text / select / toggle / textarea / images / date / time / datetime / recurrence / folder
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

## 노드 타입

노드들은 노드 타입으로 그룹화되어 상위 레벨에서 접근할 수 있다.

| 노드 | 타입 | 하위 소스 | 사용법 |
|------|------|----------|--------|
| `ibl_info` | info | (레거시 — sense로 통합됨) | `ibl_info(source="finance", ...)` → `[sense:stock]{op: "search"}` |
| `ibl_store` | store | (레거시 — sense로 통합됨) | `ibl_store(store="health", ...)` → `[self:health]{op: "save"}` |
| `ibl_exec` | exec | python, node, shell | `ibl_exec(action="python", target="print(1+1)")` |

---

## 해석 순서

에이전트가 `[sense:search]{query: "AI"}`을 호출하면:

1. **액션 매칭**: `sense.actions.web_search`가 있는가? → 있으면 실행
2. **에러**: 없으면 사용 가능한 액션 목록 반환

---

## 핵심 파일

| 파일 | 역할 |
|------|------|
| `data/ibl_nodes_src/` | **IBL 액션 단일 진실 소스** — 노드별 yaml (sense/self/limbs/others/engines/table + meta) |
| `data/ibl_nodes.yaml` | **빌드 산출물** — 직접 편집 금지. `scripts/build_ibl_nodes.py`로 생성 |
| `scripts/build_ibl_nodes.py` | 빌드 + 삼각 검증 (`--check`로 src↔tool.json↔handler.py `_OP_DISPATCHERS` AST 정확 비교 + **fixture 완전성** 강제) |
| `scripts/git-hooks/pre-commit` | 정합성 게이트 (commit 시점에 `--check` 자동 호출) |
| `scripts/ibl_health_check.py` | **건강 점검 단일 소스** — §1A 정적 + §1B fixture 통화 + §1C 골든 파이프 (AI 0) |
| `data/ibl_fixtures.json` | **행동 건강 fixture 단일 소스** — 액션별 올바른 파라미터 예 하나 (+ exempt) |
| `backend/cognition/world_pulse_health.py` | `run_daily_health_check`(하루 1회·RED면 알림) · `run_ibl_health_check`(스크립트 실행·파싱) |
| `data/api_registry.yaml` | API 도구 정의 (node 필드로 자동 병합) |
| `backend/ibl/ibl_engine.py` | IBL 실행 엔진, 동사 해석, 라우팅, 자동 발견 |
| `backend/ibl/api_engine.py` | API 레지스트리 실행 엔진, transform 후처리 |
| `backend/ibl/ibl_parser.py` | IBL 문법 파서 (`>>`, `&`, `??`) |
| `backend/ibl/ibl_access.py` | 에이전트별 노드 접근 제어, 환경 프롬프트(`_emit_action_line` — op 자식 노출) |
| `backend/ibl/workflow_engine.py` | 파이프라인 실행, 워크플로우 관리 |
| `backend/ibl/trigger_engine.py` | 이벤트/트리거 기반 실행 엔진 |
| `data/workflows/` | 저장된 워크플로우 YAML |
| `backend/cognition/goal_evaluator.py` | Goal 조건 평가, 비용 산출 (Phase 26) |

---

## op 어휘 단일화 (2026-05-28)

단일 액션 + op 분기 패턴(예: `[limbs:browser]{op: "click", mode: "double", ref: "..."}`)에서 op 값들을 src yaml에 어휘로 선언:

```yaml
click:
  description: 브라우저 요소 클릭 (op 분기). single/double/right.
  target_key: op
  router: handler
  tool: browser_click_op
  ops:                          # 신규 (2026-05-28)
    default: single
    values:
      single: 좌클릭 (기본)
      double: 더블클릭 — 표 셀 편집·파일 열기
      right: 우클릭 — 컨텍스트 메뉴
```

**규약**:
- `target_key: op` 인 모든 액션에 `ops` 블록 의무 (라우터 무관 — handler/system/workflow_engine/trigger_engine 모두).
- `ops.values` 키들은 시스템 프롬프트에 `<op>` 자식 요소로 노출되어 실행 에이전트가 정확한 op를 선택.
- 24개 op 액션(limbs 13 + self 11) 마이그레이션 완료.

**삼각 검증** (`build_ibl_nodes.py --check`):
1. **등록**: src.tool ↔ tool.json.name (어제 dispatcher audit의 16건 누락 패턴 재발 방지)
2. **op enum**: src.ops.values 키 ↔ tool.json input_schema.properties.op.enum (exact set)
3. **default**: src.ops.default ↔ tool.json input_schema.properties.op.default
4. **handler**: src.ops.values 키 ↔ handler.py 모듈 레벨 `_OP_DISPATCHERS[tool_name]` dict 키 (AST 파싱, exact set)

### op 축 — 통화·부작용을 op 단위로 (2026-08-05, 언어 개정)

`returns:`/`side_effect:` 는 **액션** 단위인데, 실제로 통화와 부작용을 가르는 건 **op** 다.
`self:business_item` 하나에 `list`(items)와 `delete`(effect)가 같이 살아, 전 패키지가
"정직하게 전부 items 로 래핑" 아니면 "items 라 선언하고 대다수 op 는 effect 반환" 중
하나를 택해 왔다. `side_effect: true` 도 액션 통째에 걸려 **읽기 op 가 쓰기 액션 안에
갇혔다**(자동 건강검진 fixture 82개 중 32개가 그 이유로 실행조차 안 됐다).

`ops` 블록에 **형제 맵 둘**을 둔다 (둘 다 선택, 선언한 op 만 적으면 된다):

```yaml
  ops:
    default: list
    returns:            # op 별 통화. 선언 없는 op 는 액션 returns 를 상속.
      delete: effect
    side_effect:        # op 별 부작용. 해소 규칙은 아래.
      list: false
      detail: false
    fixture:            # op 별 '올바른 파라미터 예 하나' — 읽기 op 전용
      list: '[self:ledger]{op: "list", store: "item"}'
    exempt:             # 자동 실행 불가한 읽기 op — 사유
      detail: item_id 필요(list 결과의 id) — 고정 fixture 부적합
    values:             # {op: 설명 문자열} — 모양 고정(프롬프트 카탈로그가 읽는 유일한 맵)
      list: 아이템 목록
      detail: 아이템 상세 (item_id 필수)
      delete: 아이템 삭제 (item_id 필수)
```

**부작용 해소 규칙 — 조이는 건 자동, 푸는 건 명시** (`backend/ibl/ibl_ops.py` 단일 소스):
1. `ops.side_effect[op]` 가 bool 이면 그것
2. 액션이 `side_effect:` 를 선언했으면 그것 — **끈적하다**. op 가 `false` 를 직접 말하기
   전엔 안 풀린다(카메라·마이크처럼 "통화는 읽기, 행위는 셔터"인 액션을 지키는 자리)
3. 없으면 해소된 op returns 가 effect 인지로 파생

즉 items 액션 안의 op 가 `returns: effect` 를 선언하면 **자동으로** 위험 판정되고(마찰 0),
안전 판정은 사람이 op 이름을 대고 `false` 라고 적어야만 난다. `returns: effect` +
`side_effect: false` 동시 선언은 모순이라 빌드가 거부한다.

**행위 검증 — `fixture`/`exempt` 형제 맵** (2026-08-05 감사 ⑤): 액션 레벨 `fixture:` 는
액션당 **op 하나**만 증명한다. `[self:music]` 의 fixture 가 `sources` 를 돌 때
`library`·`track`·`folders`·`playlists`·`playlist` 는 한 번도 실행되지 않았다(읽기 op
133개 중 fixture 가 닿는 것이 37개였다). 그래서 op 별 예제를 형제 맵으로 단다.

빌드가 **완전성을 강제**한다 — 읽기(side_effect=false)이면서 통화가 items|scalar 인 op 은
`ops.fixture` 또는 `ops.exempt`(사유), 또는 액션 레벨 `fixture:`/`exempt:` 로 반드시 덮인다.
**쓰기 op 에는 fixture 를 달 수 없다**(무인 건강검진이 매일 그 부작용을 실행하게 된다).
파생물 `data/ibl_fixtures.json` 의 op 항목 키는 `node:action#op`.

★"읽기라고 선언했는데 통화는 액션의 `effect` 상속"도 모순으로 막는다 — 그 상태의 op 은
실행 대상 밖으로 분류돼 행위 검증에서 조용히 빠진다(`limbs:browser`·`limbs:guestpc` 등
21개가 그랬다). 읽기 op 은 자기 통화를 직접 말해야 한다.

**소비자**: 조종실 dry-run 라벨(`api_ibl._safety`) · 건강검진 read-only 게이트와 통화 판정
(`ibl_health_check`) · 부작용 지도(`ibl_safety.build_op_safety_map`).

**함정**: `values` 를 `{op: {desc, returns}}` 중첩형으로 바꾸지 **말 것**. `values` 는 8곳이
`{op: str}` 로 읽고 그 중 하나가 모든 에이전트 턴의 프롬프트 카탈로그다 — 모양을 바꾸면
놓친 소비자 하나가 조용히 `[object Object]` 를 뿜는다. 형제 맵은 순수 가산이라 못 깬다.
키 드리프트(유령 op)는 빌드 가드가 막는다.

**dispatcher 표준** (handler.py 측 규약):
```python
_OP_DISPATCHERS = {
    tool_name: {op: handler_or_None, ...},
    ...
}
_OP_DEFAULTS = {tool_name: default_op, ...}  # 기본값 있을 때만
```
op 분기 패키지 모두 이 패턴 채택(수·목록은 packages.md — 빌드 파생).

**이중 게이트**:
- `pre-commit` 훅: commit 시점, 정적 검증
- `world_pulse_health.run_daily_health_check()`: **하루 1회** 건강 점검 — `scripts/ibl_health_check.py` 를 subprocess 로 돌려 §1A 정적 정합성·§1B fixture 통화·§1C 골든 파이프 결과를 `self_checks` 테이블에 기록(정적분 식별자 `__static__:ibl_consistency`). AI 0

---

## 목적/시간/조건 (Phase 26: Goal/Time/Condition)

### Goal Block — 목적 선언

에이전트에게 "왜"를 알려주는 상위 레이어. 목적이 있으면 에이전트가 스스로 달성 여부를 판단하고 반복한다.

```
[goal: "에어컨 최적 구매"]{
  success_condition: "가격/성능/배송 비교 완료",
  resources: ["shopping-assistant", "web"],
  max_rounds: 20,
  max_cost: 1000,
  by: "오늘 저녁",
  report_to: "사용자"
}
```

**필수 안전장치**: 모든 Goal에 `max_rounds` 또는 `max_cost` 중 하나 이상 필수.

**시간 표현**:

| 표현 | 의미 | 예시 |
|------|------|------|
| `deadline` | 최종 기한 | `deadline: "2026-12-31"` |
| `until` | 조건 달성까지 | `until: "매수결정"` |
| `within` | 기한 내 완료 | `within: "2h"` |
| `by` | 특정 시점까지 보고 | `by: "오늘 저녁"` |
| `every` | 반복 실행 주기 | `every: "매일 08:00"` |
| `schedule` | 일회성 예약 실행 | `schedule: "2026-04-01 09:00"` |

**Goal 상태**: `pending` → `active` → `achieved` / `expired` / `limit_reached` / `cancelled`

**종료 우선순위**: `until` 충족 > `deadline` 도달 > `max_rounds`/`max_cost` 도달

### 조건문 (if/else if/else) — 상황에 따른 분기

```
[if: sense:kospi < 2400]{
  [goal: "방어적 포트폴리오 재편"]{deadline: "즉시", max_rounds: 10}
} [else]{
  [goal: "성장주 모니터링 유지"]{every: "매일 09:00", max_rounds: 30}
}
```

`else if`로 다중 조건 분기도 가능하다:

```
[if: sense:kospi < 2400]{
  [goal: "방어적 포트폴리오 재편"]{deadline: "즉시", max_rounds: 10}
} [else if: sense:kospi < 2600]{
  [goal: "중립 포지션 유지"]{every: "매일 09:00", max_rounds: 20}
} [else]{
  [goal: "공격적 매수 검토"]{max_rounds: 15}
}
```

### 케이스문 (case) — 다중 분기

```
[case: sense:market_status]{
  "상승장": [goal: "공격적 매수"]{max_rounds: 20},
  "하락장": [goal: "손절 점검"]{max_rounds: 10},
  "> 20%": [goal: "즉시 구매"]{max_rounds: 5},
  "10~20%": [goal: "추가 비교"]{max_rounds: 15},
  default: [goal: "관망"]{max_rounds: 5}
}
```

범위 표현식: `> N`, `>= N`, `< N`, `<= N`, `== N`, `N~M` 지원.

### Goal 프로세스 관리

```
[self:goal]{op: "list", status: "active"}       # 진행 중인 목표 조회
[self:goal]{op: "status", goal_id: "goal_001"}   # 특정 목표 상태 조회
[self:goal]{op: "kill", goal_id: "goal_001"}     # 목표 중단
```

### 통합 예시

```
[goal: "청주 투자 적기 판단"]{
  every: "매일 08:00",
  deadline: "2026-09-30",
  until: "매수 결정",
  max_rounds: 200,
  max_cost: 50000,
  strategy: [case: sense:interest_rate]{
    "하락": [sense:realty]{op: "query", region: "청주", depth: "deep"},
    "상승": [goal: "관망"]{max_rounds: 1},
    default: [sense:realty]{op: "query", region: "청주", depth: "shallow"}
  }
}
```
### 전략 에스컬레이션 & 라운드 메모리 (Phase 26b)

에이전트가 동일 유형의 시도를 반복하는 문제를 방지하는 메커니즘.

**전략 전환 규칙** (`<strategy_rules>`로 시스템 프롬프트에 주입):
1. 매 시도 후 `[self:goal]{op: "log"}`로 접근 범주, 결과, 교훈을 기록
2. 동일 `approach_category`가 3회 연속 실패 시 범주 포기, 다른 접근으로 전환
3. 모든 범주 소진 시 사용자에게 보고
4. 새 시도 전 `[self:goal]{op: "attempts"}`로 이전 이력 확인

**라운드 메모리** (`attempt_log` 테이블):
- `task_id`: 같은 작업의 시도를 묶는 키
- `approach_category`: 접근 범주 (예: "cv2_import", "pillow_fallback")
- `result`: "success" / "failure"
- `lesson`: 교훈
- 시스템 프롬프트의 `<attempt_history>` 섹션으로 동적 주입, 포기된 범주는 `<exhausted_categories>`로 명시

**구현 파일**: `conversation_db.py` (attempt_log 테이블), `ibl_nodes.yaml` (log_attempt, get_attempts), `ibl_engine.py` (핸들러), `ibl_access.py` (규칙/이력 주입)

---

| `backend/datastore/ibl_usage_db.py` | IBL 용례 사전 DB + 시맨틱 검색(FTS5 폴백) |
| `backend/cognition/ibl_usage_rag.py` | 용례 RAG 참조 모듈 |
| `data/ibl_usage.db` | 용례 사전 + 실행 로그 DB |

---

## 용례 RAG 참조 시스템

에이전트가 IBL 코드를 생성할 때, 유사한 과거 성공 사례를 자동으로 참조한다.

사용자 메시지가 들어오면 용례 사전에서 검색해 유사 용례를 XML 형태로 프롬프트에 주입한다. 현재 기본은 시맨틱 100%(`DEFAULT_ALPHA=1.0`)이며, 임베딩 모델이 준비되지 않은 짧은 구간에만 FTS5/BM25가 폴백한다. AI는 이 참조를 기계적으로 복사하지 않고 현재 상황에 맞게 변형한다.

```xml
<ibl_references note="아래는 유사한 과거 용례입니다. code의 IBL 코드를 참고하되, 반드시 execute_ibl 도구의 code 파라미터로 실행하세요. 절대 텍스트 응답에 IBL 코드를 포함하지 마세요. 분석/판단/정리가 필요한 작업은 파이프라인(>>)으로 엮지 말고 액션을 하나씩 호출하면서 중간에 생각하세요.">
  <ref intent="아파트 매매 실거래가" code='[sense:realty]{op: "query", region_code: "지역코드"}' score="0.88"/>
</ibl_references>
```

성공한 도구 실행 로그는 자동으로 용례 사전에 승격되어, 시스템이 사용할수록 참조 품질이 향상된다.

→ 상세 문서: [memory.md](memory.md) (연상기억 심층 — 해마·용례 RAG)

---

## 액션 라우팅 이원화 (Phase 18)

IBL 액션은 라우터 타입에 따라 여러 경로로 실행된다. 현재 9종의 라우터가 존재한다:

| 라우터 | 설명 |
|--------|------|
| `handler` | 패키지의 handler.py로 라우팅 (복잡한 후처리) |
| `api_engine` | api_registry.yaml 기반 API 호출 + transform 후처리 |
| `system` | 시스템 내장 액션 (ask_user, approve 등) |
| `trigger_engine` | 이벤트/트리거 기반 실행 |
| `workflow_engine` | 워크플로우/파이프라인 실행 |
| `channel_engine` | 채널 추상화 (메시지 송수신) |
| `driver` | 드라이버 기반 프로토콜 직접 접근 |
| `stub` | 미구현 예약 액션 (Phase 표시) |

주요 두 가지 경로:

### 1. api_engine 라우팅 (자동 발견)
`api_registry.yaml`에 `node` 필드가 있는 도구는 로드 시 자동으로 해당 노드의 액션으로 병합된다. `ibl_nodes.yaml`에 별도 등록이 필요 없다.

```yaml
# api_registry.yaml — node 필드만 추가하면 끝
kosis_search_statistics:
  service: kosis
  endpoint: /statisticsList.do
  transform: kosis_list
  node: sense                  # ← Phase 25: statistics → sense
  action_name: search_statistics
  description: "통계표 목록 검색"
  target_key: keyword
```

이 방식은 API 호출 + transform 후처리로 완결되는 도구에 적합하다. 현재 api_engine 라우팅 액션들이 이 방식을 사용한다.

### 2. handler 라우팅 (수동 등록)
복잡한 후처리(캐싱, 코드 매핑, 다단계 API 호출 등)가 필요한 도구는 `ibl_nodes.yaml`에 수동 등록하고 `handler.py`가 처리한다.

```yaml
# ibl_nodes.yaml — handler 패키지의 handler.py로 라우팅
performance:
  router: handler
  tool: kopis_quick_search
  target_key: keyword
```

### 자동 병합 메커니즘
`ibl_engine.py`의 `_merge_api_registry_actions()`가 `_load_nodes()` 시점에 호출되어, `api_registry.yaml`의 node 바인딩된 도구를 `ibl_nodes.yaml`의 actions dict에 in-place로 병합한다. YAML 앵커(`&id005` 등)가 가리키는 동일 dict 객체를 직접 변경하므로 nodes 섹션에도 자동 반영된다.

---

## 시스템 AI IBL 통합 (Phase 17→25)

Phase 17에서 시스템 AI도 프로젝트 에이전트와 동일한 `execute_ibl` 단일 도구 구조로 통합되었습니다.
Phase 19-22에서 점진적으로 노드를 통합했으며, Phase 25에서 최종 5개 노드 구조로 재구조화되었습니다: self(75), limbs(96), sense(78), others(13), engines(46). 총 308개 액션.

**차이점은 접근 범위뿐:**
- 프로젝트 에이전트: `allowed_nodes`에 지정된 노드만 접근 가능
- 시스템 AI: 모든 노드 접근 가능 + 프로젝트 간 위임(`[others:delegate]{scope: "cross"}`)

**항상 허용되는 인프라 노드 (노드 yaml `always_on: true` 플래그, 단일 소스):**
`self`, `others`, `table` — 모든 에이전트에 자동 제공. self는 개인 도메인 관리, others는 협업/통신 전담, table은 통화 변환 문법 계층(파이프 생존 보장).

**시스템 AI 전용 others 액션:**
| 액션 | 설명 |
|------|------|
| `list_projects` | 모든 프로젝트/에이전트 목록 조회 |
| `delegate_project` | 다른 프로젝트의 에이전트에게 작업 위임 |

**시스템 AI 전용 self 액션:**
| 액션 | 설명 |
|------|------|
| `manage_events` | 이벤트/스케줄 통합 관리 |
| `list_switches` | 등록된 스위치 목록 조회 |

---

### IBL 진화 요약

IBL은 Phase 0(원시 도구 호출)에서 시작하여, 드라이버 기반 프로토콜 추상화(Phase 5-10), 노드 통합(Phase 17-25), verb 시스템 도입과 폐지(Phase 22-24), Goal/Time/Condition(Phase 26)을 거쳐 5-Node 체계로 발전했고, 이후 op 어휘화·사용성 재감사·어휘 정리·메신저/비즈니스 IBL화·neighbor 통합·폰 온디맨드 감각 삼각·통화 대수(engines 변환자→2026-06-30 table 노드 분리로 6-Node)·포식 기억(self:forage/residual)·국가학술정보(sense:researcher/paper)·능력 자기완결화(self:package)·공개 표면 가족(others: portal/showcase/family_news/bulletin)·몸 부탁(others:ask)·USB 손발(self:limb·limbs:guestpc)·신문 발행 결정화(engines:newspaper)·내 음악(self:music)·웹앱 등기부(self:webapp)·개념중복 압축 1·2·2b·슬라이드/영상 일원화(2026-08-05 — 검색 search{source}·도서 book{source:google}·슬라이드 self:slide·동영상 deck{op:video})로 현재 150 액션이 됐다. 핵심 설계 철학은 "AI가 작성하는 언어"이며, 문법 복잡도보다 표현력을 우선한다.

*Phase 20: filesystem→orchestrator, webdev+design→creator, photo+blog+memory+health→librarian 통합.*
*Phase 21: finance+culture+study+legal+statistics+commerce+location+web(search/crawl/news)→informant 통합.*
*Phase 22: youtube+radio→stream, browser+android+desktop→interface, informant+librarian→source, orchestrator→system, creator→forge. 6개 노드, 321 액션.*
*Phase 23: system에서 위임 관련 7개 액션을 team 노드로 분리. 7개 노드(system, team, interface, source, forge, stream, messenger).*
*Phase 24: verb 시스템 제거. 런타임 verb→action 해석 삭제. 프롬프트 가독성을 위해 category 태그로 대체 (순수 표시용).*
*Phase 25: 5-Node 최종 구조 재설계. source→sense(외부 정보), system→self(개인 도메인), interface+stream→limbs(신체/장치), team+messenger→others(협업/통신), forge→engines(엔진/창작). 총 308 액션.*
*Phase 26: self 노드에 log_attempt, get_attempts (전략 에스컬레이션/라운드 메모리). sense 노드에 cctv_refresh, cctv_stats (UTIC 실시간 API).*
*최근 변경(2026-08-25): 새 액션/op의 네 얼굴(몸·사전·교재·관측)과 시딩→param sweep→연상 프로브 생명주기를 명문화하고 현행 줄-카탈로그·시맨틱 검색 경로를 정정. 이력 정본=git log·changelog.log(`[self:body]` 회상).*
