# 상상 훈련 77회차 결과보고서 (2026-09-29) — 강의·연구 자료 업무

훈련 턴 · **무수정**(가이드 §4-3). 아래 갭 원장은 [before.json](before.json)·[baseline.json](baseline.json), 그리고 셸로 직접 읽은 패키지 코드·원천 응답만으로 썼다. 집행 완료 절은 비워 두었다.

## 축 선정

- **축**: 행동 기준 미조합 메뉴의 강의·연구 어휘다. 선언과 `describe`로 op·인자·반환을 확인했다.
  - 강의·자료: `self:lecture`·`material`·`notebook`
  - 원천: `sense:researcher`·`book`·`entity`·`devdocs`·`paper`
  - AI 변환: `table:structure`·`judge`
  - 결합: `table:dedup`·`union`·`each`·`document`·`groupby`
- **도메인**: 사용자는 AI 주제 물리학박사·뇌과학 연구자·AI 저서 3권 저자이고 AI 강의를 한다.
  - 이번 주 강의: 「인공지능이 할 수 있는 것, 할 수 없는 것」(88장). 주제는 "LLM 추론의 한계"로 잡았다.
  - 강의 8개·재료 7건, 노트북 3개(AI 동향 65소스·카파시 강의·블로그항법)를 **읽기만** 했다.
- **축 선정 관문 질문**("기계로 열거 가능한가"): 원천마다 인자·응답 코드·칸이 어떻게 다른지는 실제로 불러야 드러난다. 그래서 훈련 축이다. 다만 발견 중 둘은 열거 가능해 census로 넘긴다.
  - F77-1: meta 접기(F76-1의 두 번째)
  - B77-1: source×param 격자
- **닫힌 밭**:
  - 텍스트 동등의 casefold는 값 표기 격자의 정책이므로 다시 갈지 않았다. "대소문자 구분 수단이 없다"는 표현력 갭(G77-1)으로만 적었다.
  - 절단 표지는 재확인으로만 적었다.
- **탐침**: 모델 경로(`agent_id:"IT77_probe"`·`task_id:"IT77_task"`). 모든 요청이 `edition:2`·`project_id:"컨텐츠"`·`origin:"training"`이다.
- **호출 절제**:
  - 외부 API는 읽기 조회만 했다.
  - 고친 문장 재실행(T10 두 번·T16·T17)은 `reuse:{run_id}`로 읽기 영수증을 다시 썼다.
  - 유료 AI는 과제당 1회 이하였다(ask·structure·judge 5행). 발신은 0이다.
- **원천 대조**:
  - T18의 '뇌'·'기억' 적중 2장을 디스크 grep(각 1파일)과 맞췄다.
  - T06 loan_stats 빈 칸은 정보나루 원 XML(`loanInfo/Total` 자식 없음)과 대조했다.
  - B77-3은 Context7 v2 원 응답과 대조했다.
  - B77-2는 청크 원문 오프셋(496자 중 196자 지점)으로 확인했다.

## 지표 스냅샷 (훈련 전)

행동 미조합 140/168 · 파이프 길이 중앙값 3 · 문형 4(조회 26·축적 8·적용 6·조건 2) · 파트너 다양성 중앙값 2. 76회차와 같다. 원본은 [metrics.json](metrics.json)이다. 지표는 몸의 현황이며, 훈련 실측은 증류에 담기지 않는다(§6).

## 과제 표

원문·판정식: [probe.py](probe.py) · 응답 전량: [before.json](before.json)(요청·응답 30건, 격리 raw 9건은 별도) · 기준선과 회차 후 diff: [baseline.json](baseline.json).

**24과제 중 기계 판정 23통과 · 1실패.** 판독으로 T02·T09·T15·T20에 결함·구조 경로를 추가했다. 결함 4부류 · 마찰 3부류 · 문법 갭 1.

탐색 중 훈련자 문장 잘못은 결함 판정에서 뺐다. 거절 안내가 모두 방향을 정확히 줬다.
- groupby 결과(Record)를 `.items` 없이 sort에 넘김(T04, TYPE "레코드 봉투의 행 목록은 .items로")
- f-문자열 안의 큰따옴표(T16, "보간의 닫는 }가 없습니다")
- 내장 함수 인자 안 파이프 `join(…, $x >> each)`(T16, PURE_EXPRESSION)
- 위키데이터에 여러 낱말 질의 → 0건 → `$e.items[0]`(T10 첫 시도, INDEX)
- 필터 낱말 "artificial"(T10 두 번째)

| # | 상상 의도 | 결과 | 분류 |
| --- | --- | --- | --- |
| T01 | 이번 주 주제 최근 논문 5편 → 제목·연도·인용·링크·초록 첫 문장 표 | 5행. 연도는 `split($x.meta," · ")[1]`로만 꺼냄. `sort_by:"cited"`가 관련도를 버려 1·3위가 주제 밖('Negation in English'·'Deliberative Democracy'). 봉투에 total·truncated 없음 | 꼬임(F77-1·B72-3) |
| T02 | arXiv 최신 프리프린트 5편(최근순) | `sort_by:"recent", year_from:2026` → 2026-06-29·2025-09-30·2025-04-30·2025-04-22·**2024-06-19**, 관련도순. 경고 0 | 결함 B77-1 |
| T03 | 서울대 장병탁 교수 최근 국내 논문(동명이인 분리) | find: 서울대 2명(1963년생 lodID 65407 / 생년 없음 351031). nanet 416건 중 15건, meta 문자열 필터로 5편 — 전부 **잡지 인터뷰**(divFlag ARTICLE이 학술논문·기사를 한데 묶음, 원천 한계) | 꼬임(F77-1) |
| T04 | 흔한 이름(김민수) 연구자 소속별 수 + 공저자망 | 10명(limit 30 요청, 표지 없음)·공저자 10 | 깨끗 |
| T05 | 『특이점이 온다』 서지 — 정보나루·nl·구글북스 한 표 | 5·10·10건. nl 행은 저자·출판사·연도가 `meta`("지은이: 레이 커즈와일 ;옮긴이: … · 김영사 · 2025 · 일반도서")에만 있어 병합 표의 출판사·연도가 null. 판본별 ISBN 3종(2007·2016·2025) | 꼬임(F77-1) |
| T06 | 2025년판 ISBN 대출 통계·함께 빌린 책 | co_loan 3권(『마침내 특이점이 시작된다』·『넥서스』…). `loan_stats.total`이 `""` — 원 XML의 `loanInfo/Total`이 빈 요소(원천). 월별은 136·121·124건 | 깨끗 |
| T07 | 내 강의 재료에서 '하네스' 문단 찾기 | 7재료 전수 읽기 → 2문단(「개인들은 하네스 개발이 필요없을까」). 강의 목록 `items`에 **lecture_id가 없어** `.lectures`로 돌았다 | 꼬임(F77-1) |
| T08 | 'AI 동향' 노트북 발췌 5개(LLM 0) | 5행. 위치·점수가 `meta`("¶29 · score 0.7") 문자열 | 깨끗(F77-1 단서) |
| T09 | '카파시 강의' 근거 고정 질문(유료 1) | mode read, 답·인용 4. 답이 따옴표로 인용한 문장이 citations[0].quote에 **없다**(quote=청크 머리 160자) | 결함 B77-2 |
| T10 | '환각' 정의 — 위키데이터(AI·뇌과학 두 뜻)·openalex·구글북스 비교표 | 첫 시도 `contains($x.summary,"AI")`가 **'pAInting by John D. Graham'**(Q23946118)을 골랐다 → `len(split(…,"AI"))>1`로 Q116197048 "confident unjustified claim by an AI" · 뇌과학 Q130741 "perception in the presence of no external stimuli…" | 꼬임(G77-1) |
| T11 | in-context learning 참고문헌 3원천 → 제목 dedup → 마크다운(IT77_) | openalex 5·arxiv 5·semantic **429**(`??` 폴백) → 10행 파일. openalex 제목에 원문 개행("Text-to-Text\n Transformer")이 남음 | 깨끗 |
| T12 | 인용 중복 제거(외부 0) — 대소문자·끝 마침표·DOI 표기 차이 | title 기준 5→4(공백·대소문자는 합치고 끝 마침표는 가름), doi 기준 →3(`arXiv`/`ARXIV` 합침, null 행은 판정 밖), [title,year] 기준 →4(`2017`="2017") | 깨끗 |
| T13 | 4주 강의 계획 주차별 주제에 노트북 발췌 2개씩 연결 | 8행(주차·주제·자료·위치) | 깨끗 |
| T14 | Semantic Scholar 먼저, 막히면 OpenAlex + 실패 이유 | try/catch → openalex 3건 · why `{code:"TOOL", message:"Semantic Scholar API 요청 한도 초과…"}` | 깨끗(F77-2) |
| T15 | transformers pipeline 공식 문서(ID는 resolve에서) | resolve 5행 `title` **전부 ""**, ID는 `meta`에만("/huggingface/transformers"). 첫 시도 `get($first,"id")` → TYPE 거절 → `$first.meta`로 31블록 | 결함 B77-3(+F77-1) |
| T16 | 논문 초록 → 강의 노트 IR(structure 유료 1) → 마크다운 | heading·table·list 4블록, 파일 생성. 표의 제목 "DeepSeek-R1 incentivizes…"가 **"incentives"로 바뀜** | 깨끗(F77-3) |
| T17 | arXiv 5편 중 인지·뇌과학 연결 판정(judge 5행) | false 3 · unknown 2, 행 순서 보존 | 깨끗 |
| T18 | 88장 슬라이드 스펙 JSON에서 '환각'·'뇌'·'기억' 슬라이드, 빈 발표자 노트 수 | '환각' 0(디스크 grep 0 대조) · 30장 "AI 모델과 하네스는 뇌와 신경계를 닮았다"·65장. 스펙 `data`에 `korean_texts` 보존 · 빈 노트 80/88 | 깨끗(B76-2 수리 확인) |
| T19 | '뇌과학 인공지능' 국내 학위논문 — 기본값 vs 5건 명시 | 둘 다 **실패** "[201] 요청에 대한 정상 처리이지만, 결과값이 없습니다"(모집단 37건에 학위논문 0 → 끝 페이지 너머) | 결함 B77-4 |
| T20 | 강의 준비 전 노트북 소스 stale·미색인 점검 + 지도 3줄 | items 기반 stale 0 — items에 `stale`·`status` 칸이 없어 **구조적으로 항상 0**. 원 행 `.sources`로 대조해 0 확인 | 꼬임(F77-1) |
| T21 | "2024~2025년" 문자열 연도 범위(openalex) | `year_from:"2024"` 맞춰 받아 2024·2025만 5건(Friston 등) | 깨끗 |
| T22 | 뇌과학자 김대식 저서 최근순(정보나루) | 30건(rows 30, 표지 없음) → dedup → 8. 동명이인 저서(『K리그 스카우팅리포트』·『위대한 인도』) 섞임(원천 한계) | 깨끗 |
| T23 | 스크래치 IT77 강의 create → 노트북 발췌 메모 material add → list → finally delete | 추가 853B · list 1행 · delete success | 깨끗 |
| T24 | 코퍼스 용례 check — 4013 `'$it.path'`·4005·4759 옛 filter·arXiv download·arxiv year_from | 4013 `incomplete`+**LITERAL_DOLLAR**(F76-4 수리 살아 있음) · 4759 TYPE "Callable가 필요" · download effects `unknown` · arxiv year_from/sort_by/open_access 경고 0 | check(B77-1·B75-4) |

튼튼했던 것:
- 연구자 동명이인 분리, 도서 세 원천 병합, ISBN 상세
- 강의 재료 전수 읽기(each 안 each), 노트북 발췌·주차 연결
- 원천 폴백(429 → openalex), 인용 dedup 규칙, structure→document, judge
- 슬라이드 스펙 JSON, 스크래치 create→add→list→finally delete

실패는 두 자리에서 났다.
1. **원천 변이·원천 응답 코드를 몸이 정직하게 옮기지 못하는 자리**: 인자 침묵 무시, [201] 실패화, API 필드 드리프트, 근거 아닌 인용
2. **구조 칸이 표시 문자열(meta)에만 있는 자리**

## 갭의 원장

### B77-1 `sense:paper`의 원천별 인자 지원이 **침묵 무시**다 — "최신 프리프린트"·"2024년 이후 학위논문"이 조용히 틀린다 (★B76-3 가족 → census)

- **요약**: 행동 선언의 `params`에 `year_from`·`year_to`·`sort_by`·`open_access`·`year`·`type`·`page`가 액션 단위로 올라 있다. 실제로 읽는 원천은 제각각이다(`study/handler.py`).

  | 원천 | 읽는 인자 | 버리는 인자 |
  | --- | --- | --- |
  | openalex(752~755행) | year_from·year_to·open_access·sort_by | year |
  | semantic(416행) | year_from | 나머지 |
  | arXiv(53~62행) | query·limit | 전부(`sortBy:"relevance"` 고정 — 최신순 자체를 말할 수 없음) |
  | nanet(327행) | `year`(정확 일치)·type·page | year_from |
  | pubmed | query·limit | 나머지 |

  `target_description`은 어느 인자가 어느 source에 듣는지 말하지 않는다.
- **최소 재현**: `return [sense:paper]{query:"LLM reasoning limitations", source:"arxiv", sort_by:"recent", year_from:2026, limit:5}`
- **실측**:
  - T02: 결과 날짜 2026-06-29 · 2025-09-30 · 2025-04-30 · 2025-04-22 · **2024-06-19**(관련도순)
  - T24: 같은 문장 + `open_access:true`의 check가 `incomplete`·경고 0, 실행도 경고 없이 success
- **영향**: 강의 준비의 기본 요구("최근 1년", "최신순")가 arXiv·nanet·pubmed에서 조용히 무시된다. 사용자는 걸러진 줄 알고 옛 논문을 받는다. T01의 openalex만 맞게 동작했다.
- **제안(수리성, ★census)**:
  1. 원천 함수가 읽는 `tool_input` 키를 AST로 뽑아 source×param 지원 격자를 만든다(열거 가능).
  2. 선언에 `variants`(source별 허용 인자)를 적고, 지원 안 하는 인자가 오면 판본 2 check·실행이 `ARGUMENT_CONTRACT`로 거절하거나 "이 source는 year_from을 지원하지 않음" 경고를 낸다.
  3. arXiv는 `sortBy=submittedDate`와 `submittedDate:[… TO …]` 질의로 `sort_by:"recent"`·연도 범위를 실제로 구현할 수 있다. nanet은 `year_from`을 후필터에 넣는다.
  - B76-3(naver `deal:"lease"` 흡수 침묵)과 한 가족이다. "원천이 인자를 조용히 다르게 해석"을 격자로 닫는다.
  - 가드: {openalex, arxiv, semantic, pubmed, nanet} × {year_from, year_to, sort_by, open_access, year, type} → 적용·거절·경고 중 하나, 침묵 0.

### B77-2 노트북 `ask`의 `citations[].quote`가 **근거 문장이 아니라 그 위치 청크의 머리 160자**다

- **요약**: `notebook/handler.py`의 `_verify_document_citations`(385~401행)는 답의 `[#소스 loc]`가 실제 청크 위치인지만 확인한다. `quote`는 그 청크의 처음부터 `QUOTE_CHARS=160`자를 자른다. 답이 주장하거나 따옴표로 인용한 문장이 그 160자 안에 있는지는 보지 않는다. 가이드(`notebook.md`)의 "quote는 코드가 원문에서 뽑으므로 인용 환각이 원리적으로 없다"는 **위치**에 대해서만 참이다.
- **최소 재현**: `[self:notebook]{op:"ask", name:"카파시 강의", query:"LLM을 운영체제에 비유한 대목은 무엇이고 어떤 근거를 드는가?"}`
- **실측**(T09):
  - 답: “GPT는 자연어 처리 프로그램을 실행하도록 런타임에 재구성 가능한 범용 컴퓨터” [#67 49:22]
  - `citations[0]` = `{loc:"49:22", quote:"표현력이 풍부하고, GPU 사용 측면에서도 매우 효율적이며…"}`
  - 청크 1974 원문 496자에서 인용 문장은 **196자 지점**이다(quote 경계 160 밖).
  - 나머지 인용 [#67 46:18]·[#67 48:21]의 quote도 청크 머리다.
- **영향**:
  - 인용을 확인하려는 사람이 엉뚱한 문장을 본다.
  - `citations`를 표·참고문헌으로 파이프하면 근거 칸이 근거가 아니다.
  - 답이 인용한 문장이 원문에 **없는** 경우(모델 창작 인용)도 같은 모양으로 통과한다. 이번 표본은 원문에 있었다.
- **제안(수리성)**:
  1. quote는 청크 안에서 인용한 답 문장과 겹침이 가장 큰 창을 결정론으로 고른다. 답에 따옴표 구절이 있으면 그 구절이 청크에 실재하는지 대조해 창의 중심으로 쓴다.
  2. 답의 따옴표 구절이 인용 청크에 없으면 `invalid`로 세어 기존 규칙(무효 인용 → success:false)에 태운다.
  3. 청크 경로(발췌 검색 ask)의 quote 추출도 같은 규칙으로 바꾼다.
  - 가드: 청크 중간·끝에 있는 문장을 인용한 답 fixture → quote가 그 문장을 포함. 원문에 없는 따옴표 구절 → 무효.

### B77-3 `sense:devdocs` resolve 행의 `title`이 **전부 빈 문자열**이다 — Context7 v2의 필드 이름 드리프트를 침묵으로 삼켰다

- **요약**: `context7/handler.py` 81~88행은 라이브러리 이름을 `l.get("name", "")`로 읽는다. 현재 Context7 v2 `/libs/search` 응답은 `{id, title, description, branch, …}`이고 `name`이 없다. 오류 없이 모든 행의 `title`이 `""`가 된다. 라이브러리 ID(`/huggingface/transformers`)는 표시 칸 `meta`에만 있다. `libraries[]` 원 행에는 `id`가 있지만 items에는 없다. (보고서 저장 전 해당 행을 직접 읽어 `"name": l.get("name", "")`·`"title": r.get("name", "")`를 확인했다.)
- **최소 재현**: `return [sense:devdocs]{op:"resolve", library_name:"transformers"}`
- **실측**:
  - T15: 5행 모두 `title:""`, meta `/huggingface/transformers`·`/llmstxt/…`·`/websites/…`
  - 셸 대조: `curl https://context7.com/api/v2/libs/search?libraryName=transformers…` → results[0] 키 `id, title, description, branch, lastUpdateDate, state, totalTokens, totalSnippets, stars, trustScore, benchmarkScore, versions`
  - resolve→search 연결: `get($first,"id")` → null → TYPE 거절. `$first.meta`로 우회해 31블록을 받았다.
- **영향**:
  - 라이브러리 후보를 이름으로 고를 수 없다(동명 5후보가 전부 빈 이름).
  - `_search`의 이름 자동 해소도 `lib_name`이 빈다.
  - 외부 API 드리프트가 "성공"으로 숨는다. 09-13 동봉 codex 설정 키 드리프트와 같은 모양이다.
- **제안(수리성)**:
  1. `title or name`을 읽는다.
  2. items에 `id`(=Context7 ID) 칸을 병기한다(F77-1과 한 스윕).
  3. fixture 건강 검사에 "items 전 행의 `title`이 빈 문자열이면 경보"를 넣어 원천 스키마 드리프트를 잡는다.
  - 가드: v2 응답 fixture → title·id 칸 채워짐.

### B77-4 nanet 통합검색이 원천의 **[201] "결과 없음"을 실패로** 올린다 — 0건은 실패가 되고, 많이 달라고 하면 모은 행까지 버린다

- **요약**: `study/handler.py` `_search_nanet`(317~390행)은 페이지 루프에서 `r0.error`가 있으면(347행) 즉시 `success:false`를 반환한다. LOSI API는 결과가 없는 페이지에 `[201] 요청에 대한 정상 처리이지만, 결과값이 없습니다`를 준다. 그래서 다음 경우가 전부 실패한다.
  1. 0건 질의 — 핸들러 자신의 빈 결과 경로("결과가 없습니다")에 도달하지 못한다.
  2. 요청 건수 > 모집단
  3. `type`·`year` 후필터가 요청 수를 못 채워 끝 페이지를 넘는 경우

  2·3은 이미 모은 행을 버린다.
- **최소 재현**:
  - `return [sense:paper]{source:"nanet", query:"큐비트뇌파양자구름없는말", limit:3}`
  - `return [sense:paper]{source:"nanet", query:"뇌과학 인공지능", limit:40}`(모집단 37)
- **실측**:
  - 0건 질의: `success:false` "[201] … 결과값이 없습니다"
  - 같은 질의 `limit:5`: success 5행 `total:37`
  - `limit:40`: `success:false`·`source_complete:false`·items 없음
  - T19 `type:"학위논문"`(기본·`limit:5` 둘 다): 실패
- **영향**:
  - "이 주제 국내 학위논문 있나?"의 정직한 답 "없다"를 말할 수 없다.
  - `researcher → paper(nanet)` 신원 확인 흐름(가이드 "학위논문=신원의 결정적 닻")이 학위논문이 적은 사람에게서 실패로 끊긴다.
  - `??` 폴백·catch가 "원천 장애"로 오인한다.
- **같은 부류**: molit(`realty_molit_common.py` 90행)은 NODATA를 **1쪽에서만** 흡수한다. 원천별 "결과 없음" 코드 처리가 제각각이다.
- **제안(수리성)**:
  1. [201]은 페이지 끝으로 읽어 루프를 멈추고 모은 행을 돌려준다(0행이면 정직한 빈 결과). 소진했으면 `truncated:false`로 둔다.
  2. 패키지 전수에서 원천 API의 no-data 코드(LOSI 201, data.go.kr `03 NODATA_ERROR`, INFO-200 등)를 census해 "0건 = 성공·빈 목록, 끝 페이지 = 종료"로 통일한다.
  - 가드: nanet {0건, 요청 < 모집단, 요청 > 모집단, 후필터 0/부분} → 성공·행 보존·표지 일치.

### F77-1 ★구조 칸이 `meta` 표시 문자열에만 있다 — 연도순·저자 필터·ID 연결·stale 점검이 문자열 쪼개기가 된다 (★밭 이관: F76-1과 같은 속, 두 번째)

- **자리**:
  - `sense:paper` 5원천: 저자·연도·학술지·인용수·DOI·arXiv ID가 `meta`("Wayne Xin Zhao, … · 2026 · Frontiers of Computer Science · 인용 1,559")에만 있다. 연도순(T01·T02·T03·T19)은 `split($x.meta," · ")[1 또는 -1]`로 꺼냈다. 저자가 없으면 위치가 밀린다. 저자 필터(T03)는 `contains($x.meta, 이름)`이다.
  - `sense:book{source:"nl"}`(`tool_nl.py` 77행): 저자·출판사·연도가 meta에만 있다. 형제 원천(정보나루·google)은 `authors·publisher·publication_year` 칸이 있어 병합 표(T05)에서 nl 행만 null이 된다.
  - `self:lecture{op:"list"}`(`lecture_workspace/handler.py` 138행): items가 title·meta뿐이고 **lecture_id가 없다**. 강의 → 재료 연결(T07)은 옆 키 `.lectures`로 돌았다. 코퍼스 4011~4013은 lecture_id를 손으로 박는다.
  - `sense:devdocs` resolve: ID가 meta에만 있다(B77-3).
  - `self:notebook` search(218·974행): loc·score가 "¶29 · score 0.7" 문자열이다.
  - `self:notebook` sources(182행): `status`·`stale`이 "⚠️modified"·"ready" 문자열에만 있다. T20의 items 기반 stale 필터는 **구조적으로 항상 0**이다(선언은 "결과 items 구조 필드 → table 파이프 직결"). 원 행 `.sources`에서도 `stale` 키는 stale일 때만 생긴다.
- **선례**: `sense:researcher`(study 패키지)는 이미 "식별값을 문자열에만 접으면 select/dedup/join 이 못 쓰므로 열린 통화의 구조 열도 보존한다"며 name·org·birth_year·lodID를 병기한다. 같은 패키지의 paper는 그러지 않는다.
- **규모**: `"meta": " · ".join` 패턴만 **48곳 / 25파일**(shopping 2·real-estate 2·web·system_essentials·study·startup·photo·notebook·music·memory·location·legal·lecture·kosis·investment·health·freelance·entity·contest·portal·books·blog·android 각 1).
- **제안(수리성, ★밭 이관 — 다음 수리 턴 첫 항목)**: 개별 수리가 아니라 census → 일괄 병기 → 탄생 차단 관문이다.
  1. 관문: AST로 `meta` 조립 요소가 같은 dict의 독립 키로도 있는지 검사한다(R7 칸 규약: "표시 칸에 접은 값은 구조 칸에도").
  2. 병기 이름은 F76-1의 격자와 한 스윕으로 정한다. 예: `year`·`authors`·`venue`·`citations`·`doi`·`arxiv_id`, `lecture_id`, `library_id`, `loc`·`score`, `status`·`stale`(항상 존재, 없으면 null).
  - 가드: 생산자별 fixture → 선언된 구조 칸 존재.

### G77-1 대소문자를 구분하는 텍스트 판정 수단이 없다 — 약어(AI·LLM·RL·fMRI) 필터가 조용히 거짓 양성을 낸다

- **요약**: 교재의 `contains`는 "기존 부분일치 정책(NFC·대소문자 정규화)"을 공유하고, `==`·`unique`·`intersection`·`difference`·dedup도 casefold다(값 표기 계약, B46-1). 정책 자체는 닫힌 밭이라 문제 삼지 않는다. 다만 그 결과 **언어 안에 대소문자를 가리는 판정이 하나도 없다.**
- **최소 재현**: `return {c:contains("painting by John D. Graham","AI"), e:"ai"=="AI", i:len(intersection(split("claim by an ai"),["AI"]))}` → `{c:true, e:true, i:1}`
- **실측**(T10): 위키데이터 'hallucination' 7후보에서 `contains($x.summary,"AI")`가 "p**ai**nting by John D. Graham"(Q23946118)을 첫 행으로 골라, AI 뜻 정의 칸에 그림 설명이 들어갔다. success였다.
- **우회**: `len(split($x.summary,"AI")) > 1`(split은 구분함). 단어 경계는 `len(split(" "+$s+" ", " AI ")) > 1`. 둘 다 교재에 없는 관용구다.
- **영향**: 연구·강의 자료 필터의 흔한 요구(약어, 유전자·단백질 기호, 코드 식별자)가 조용히 틀린다.
- **제안(판정성 — 언어 개정)**: 아래 판정 요청 참조.

### F77-2 원천 요청 한도(429)가 일반 `TOOL` 실패와 같은 코드로 온다

- T14: Semantic Scholar 429 → `$error.code:"TOOL"`, 문구만 "요청 한도 초과". OpenAlex 429 경로도 `success:false`+문구다. T11의 `??`는 이를 받아 폴백했다.
- 프로그램이 "잠시 뒤 같은 원천 재시도"와 "원천을 바꿔라"를 구별할 값이 없다(문자열 매칭뿐).
- 제안(수리성): 공통 HTTP 헬퍼(`_polite_get` 등)가 429·Retry-After를 `error_type:"rate_limited"`·`retry_after`로 싣고, 판본 2 FailureView의 kind/code로 올린다. 가드: 429 fixture → code 구별.

### F77-3 `table:structure`가 논문 제목을 바꿔 적는다

- T16 입력 제목 "DeepSeek-R1 **incentivizes** reasoning in LLMs through reinforcement learning" → 산출 표 "DeepSeek-R1 **incentives** reasoning…". 선언은 "지어내기 금지·주어진 내용에서만"이다.
- 참고문헌·강의 노트에서 서지 문자열 변형은 인용 오류다.
- 제안(수리성): structure 결과의 블록 텍스트에 대해, 입력에 있던 고유 문자열(제목·DOI·수치)이 변형된 채 나오면 결정론 대조로 경고를 싣는다. 프롬프트에 "제목·고유명·수치는 원문 그대로"를 넣는다. 가드: 제목 fixture 3건 → 변형 0.

## 재확인 (앞 회차 갭·수리의 증거 — 새 항목 아님)

- **1b9a4932 수리 살아 있음**:
  - B76-2(판본 2 JSON 구조 보존): T18 슬라이드 스펙 `[self:read]` → `$spec.data`에 `layout·title·korean_texts·scene_en·…` 보존
  - F76-4(LITERAL_DOLLAR): T24 코퍼스 4013 `'$it.path'`에 경고
  - 이번 축에서 샌 수리는 없다.
- **B72-3**(표지 없는 절단, 닫힌 밭 — 증거만):
  - openalex(총건수가 message에만)·arXiv·Google Books(`count`=totalItems, truncated 없음) 봉투에 `total`·`truncated`가 없다.
  - 정보나루 저자 검색은 `rows:30` → 정확히 30건, 표지 없다(T22).
  - researcher find는 limit 30 요청에 10명, 표지 없다(원천 상한인지 미확인, T04).
  - nanet만 total·truncations를 싣는다.
- **F76-2**(`UNOBSERVED_FIELD` 거짓 경고): `self:material{op:"list"}`의 `.items`에 "관측된 반환 필드에 없는 이름입니다: items. 관측 필드: material" — 관측이 add op의 봉투만 잡았다. op 변이 축이 없다(`sense:researcher#coauthor`는 있음).
- **B75-4**(판본 2 check의 액션별 사전 판정 부재): 파일을 쓰는 `[sense:paper]{op:"download"}` check effects가 `unknown`이다. B77-1의 무시될 인자도 check가 말하지 않는다.
- **F72-2**(진단 안내 부족): T10 첫 시도 INDEX "인덱스가 범위를 벗어났거나 정수가 아닙니다"의 `details:{}` — 인덱스 값·목록 길이·어느 변수인지 없다(위치만 있음).

## 시드 후보 (실행 검증 통과만 — 자동 등록 안 함)

- T04(researcher find → groupby.items → sort → take, coauthor)
- T06(ISBN detail → usage.co_loan take)
- T08(notebook search → take)
- T11(3원천 paper + `??` 폴백 → union → dedup → document markdown)
- T12(인용 dedup: title·doi·복합 키)
- T13(계획 행 each flat_map → notebook search → compute)
- T14(try/catch 원천 폴백 + `$error.code/message`)
- T17(select → judge 5행)
- T18(lecture load → each spec read → `$spec.data` 필드)
- T21(문자열 연도 범위)
- T23(create → try{add·list} finally{delete})

문장 안 이름·ISBN·노트북·강의 ID는 자리표로 바꿔 심을 것.

**빼는 것**:
- T01·T03·T05·T07·T20: F77-1 수리 전의 meta 쪼개기·`.lectures` 우회
- T10: G77-1 split 우회
- T15: B77-3 우회
- T16: F77-3
- T02·T09·T19: 결함
- T22: 동명이인 섞임
- T24: check만
- 코퍼스 4011~4013(lecture_id 손 박기)·4759(옛 filter dict)는 용례 재검토 대상이다.

## 판정 요청 (언어 개정·파괴적 변경 2종만)

1. **G77-1 — 대소문자를 구분하는 텍스트 판정 수단(언어 개정)**
   - 현재 계약(동등·contains·집합 연산 모두 casefold)은 유지하되, 판정 하나를 더할지 묻는다. 후보는 셋이다.
     - (a) `contains(text, part, exact)` 선택 인자(기본 false — 기존 문장 불변)
     - (b) 대소문자·단어 경계를 가리는 새 내장 함수 하나
     - (c) 수용된 한계로 닫고 교재에 `split` 관용구(`len(split(x,"AI"))>1`)만 적기
   - 근거:
     - 연구·강의 자료 필터의 약어 판정이 조용히 거짓 양성을 낸다(T10: "painting"이 AI로 판정).
     - 우회는 가능하지만 교재에 없어 모델이 스스로 찾기 어렵다.
     - (a)·(b)는 표준 내장 함수 집합의 개정이라 사용자 판정 사항이다.

B77-1~4·F77-1~3은 모두 수리성이다.
- B77-1의 미지원 인자 거절은 사용자 저장 워크플로우에 영향이 있을 수 있어, 수리 턴이 grep으로 확인한 뒤 경고부터 도입하면 비파괴다.
- B77-4는 실패를 빈 결과로 바꾸는 정직화다.

**다음 수리 턴의 첫 항목(밭 이관)**:
1. F77-1(+F76-1) — `meta` 접기 census(48곳/25파일) → 구조 칸 병기 일괄 스윕 → "meta 요소는 구조 칸에도" AST 관문.
2. B77-1(+B76-3) — 원천 함수의 `tool_input` 읽기 키 AST 격자 → 선언 `variants` → 미지원 인자 check 경고·거절.

## 72~77회차 공통 뿌리에 77회차가 더하는 것 (훈련자 관찰)

- 76회차의 뿌리 2(**선언·교재와 실제 동작의 어긋남을 대조하는 관문이 없다**)에 새 차원 둘이 붙었다.
  - **원천 변이별 인자 지원**(B77-1)
  - **외부 원천 스키마 드리프트**(B77-3 — 선언도 코드도 그대로인데 원천이 바뀌어 빈 칸)
  - 후자는 코드 대조로는 못 잡고, fixture 결과의 **값 채움률** 검사만 잡는다.
- 뿌리 3(**통화 칸 규약의 칸·단위가 출처마다 다르다**)은 부동산·투자(76)에서 연구·강의(77)로 번졌다. `meta` 접기가 도메인이 아니라 생산자 관습이라는 증거다. census가 맞는 처방이다.
- 새 부류 하나: **원천의 '결과 없음'·'한도 초과' 응답이 몸의 실패 분류로 정직하게 번역되지 않는다**(B77-4·F77-2). 빈 결과를 실패로, 일시 제한을 일반 실패로 올리면 `??`·catch가 원천 장애와 사실 부재를 구별하지 못한다.

## 위생

- **기준선**: 탐침 전 01:16:51에 떴다([baseline.json](baseline.json)). action_health max id 244181, notify_log 6259, 알림함 1통, since 원장 1스트림 25행.
- **회차 후 diff**(01:35:57):
  - action_health 새 행 **271, 전부 `training`/agent**. 실패 7: semantic 429 ×2 · nanet [201] ×4 · devdocs TYPE ×1.
  - notify_log 새 행 0 · 알림 추가 0 · since 원장 불변.
- **외부 호출 35회**(action_health 기준, 실패 포함): paper 15 · book 7 · entity 5 · devdocs 5 · researcher 3.
  - 셸 원천 대조 2회: Context7 v2 `/libs/search` 1 · 정보나루 `srchDtlList` 원 XML 1. 국회도서관 셸 대조는 키 미로딩으로 호출 0.
  - 유료 AI 3회: notebook ask 1 · table:structure 1 · table:judge 1(5행).
  - 고친 문장 재실행 4건(T10 두 번·T16·T17)은 `reuse`로 읽기 영수증을 재사용했다.
- **스크래치**(전부 삭제 확인):
  - `projects/컨텐츠/outputs/IT77_참고문헌.md`·`IT77_강의노트.md`
  - IT77 강의 `it77seukeuraeci-eijeonteu-boan` — T23의 finally에서 삭제
  - create가 새로 만든 빈 `projects/컨텐츠/outputs/lectures` 폴더
- **사용자 데이터 무손상**: 강의 8·재료 7은 읽기만 했다. 노트북 DB 3개·소스 67 불변. 전역 `outputs/lectures` 불변.
- **나머지**: 발신 0 · 해마 시딩 0 · 라이브 코어 편집 0 · 커밋 0.
- **백엔드**: 회차 내내 `state.json` phase `ACTIVE`(`last_result.outcome: restarted`), 재기동·FAILED 없음.

## 집행 완료

### 1차 — `747d5103`·`2e096a83`(2026-09-29)

B77-2·B77-3·B77-4 와 F77-1 일부(강의 lecture_id·노트북 status/stale/loc/score·Context7 id). B77-1 은 핸들러 안 거절만. 요약은 `docs/IMAGINATION_77_81_REPAIRS_2026_09_29.md`.

### 2차 — 76·77 잔여 재탐침·수리(2026-09-29)

라이브 재탐침: B77-2·B77-3·B77-4 는 살아 있었다(국회도서관 0건 = 성공 빈 목록). 아래가 남아 있었다.

- **B77-1 — 원천별 인자가 check 에 안 보였고, 요구 자체(arXiv 최신순·연도)는 구현이 없었다.** 같은 문장이 check `incomplete`·경고 0 → 실행에서야 거절. 표는 핸들러 안 사본뿐이었다.
  - 수리: 선언 `param_support`(study/ibl_actions.yaml)를 단일 소스로. 판본 2 계약 생성기(`project_param_support`)가 source 조건부 계약의 `forbidden`(새 변이 필드)·`enums` 로 투영해 check 가 거절하고, 핸들러도 같은 표를 읽는다. 모르는 source 도 거절(기본 원천인 척 삼키지 않음).
  - 요구 구현: arXiv `sortBy=submittedDate`·`submittedDate:[…]` 범위, PubMed `pdat` 범위·`pub_date` 정렬·`free full text[sb]`, Semantic `year=lo-hi`·`openAccessPdf`, 국회도서관 연도 범위 후필터, `year`(정확)는 전 원천. 남은 거절은 원천이 못 하는 것뿐(arXiv·PubMed 인용순, Semantic 정렬, nanet 정렬·오픈액세스).
  - 라이브: T02 문장이 2026-09-28 제출 5편(최신순) · `sort_by:"cited"`+arxiv·`open_access`+nanet·`source:"scholar"` 는 check `ARGUMENT_CONTRACT`.
- **F77-1 ★밭 이관 — 표시 칸 접기 관문과 전수 병기.** `scripts/iblbuild_meta_fields.py`(build --check 편입): 기록 행(title 칸)의 meta·summary 가 여러 값을 합성하면 각 조각의 데이터 뿌리(키 경로)가 같은 행의 구조 칸에도 있어야 한다. 펼침(`**it`)은 덮은 것으로 본다. 수리 이전 트리에서 60자리를 적발했고 전부 병기해 0.
  - 논문 5원천: authors(전원)·year(정수, nanet 포함)·journal/venue·citations·doi·arxiv_id·pmid/pmcid·openalex_id·open_access/oa_url · nanet `type`.
  - 도서 nl: authors·publisher·publication_year·form·call_number·location(형제 원천 이름 그대로) · DART 공시·위키데이터 description.
  - 외부 목록(web·쇼핑·중고·부동산 naver/zigbang·숙박·크몽·창업·공모전)과 개인 기록(건강·가계부·가족신문·포털 감사·게시판·공개 창고·폰 알림·스크립트·사진·노트북·강의) — 세 하위 작업이 패키지를 나눠 병기, 표시 문자열·기존 키 불변.
  - 반환 모양 스윕 재관측으로 새 칸이 카탈로그 ⟨열⟩에 올랐다(예 `sense:paper` + authors·year·journal·citations·doi…).
- **F77-2 — 429 = `RATE_LIMITED`.** 공통 봉투 `common.api_client.rate_limited_failure`/`RateLimitedError`(error_type·retry_after·service)를 판본 2 어댑터가 `RATE_LIMITED` 로 올리고 `details.retry_after` 를 싣는다. Semantic·OpenAlex·Google Books·네이버부동산·Windy·api_client 공용 경로. 관문 `scripts/iblbuild_rate_limits.py`: 429 를 알아보는 파일은 공통 봉투를 쓴다(웹 크롤의 봇 차단 분류는 사유와 예외).
- **F77-3 — structure 원문 보존.** 프롬프트에 원문 보존 규칙. 결정론 대조 `_restore_verbatim`: 짧은 출력 문자열(제목·표 칸·목록·heading)이 원문 구간과 낱말 수 같고 1~2 낱말만 가깝게 다르거나 대소문자만 다르면 원문으로 되돌리고 `verbatim_restored` 로 신고. 의역·요약은 건드리지 않는다.
- **G77-1 — 언어 개정(사용자 채택 (a), 2026-09-29).** `contains(text, part, exact)` — 기본 false(기존 문장 불변), true 면 대소문자를 가리는 부분 문자열(NFC 만). ibl.md 내장 함수 표·조합 교재 갱신. 라이브 `contains("painting…","AI",true)=false`.
- 재확인 항목: F76-2(material `.items` 거짓 경고)·F72-2(INDEX details)·B75-4(미지 op)는 76회차 집행 절에 적었다.

### 검증(76·77 공통)

- 신규 회귀 `backend/test_imagination_round76_77_residual.py` 25건 + 77~81 회귀(arXiv 연도 거절 단언을 인용순 거절로 개정) = 50 통과.
- 빌드 `--check` 전 관문 통과(새 관문 둘 포함). 파일 크기·층·맨 문자열 가드 통과. 용례 재검토: sense:paper 55·realty 97·stay 23 건 검토 후 ack(새 거절 조합 사용 0, #4108 교정).
- 지문 재감사: 식 평가기 4파일(self:record 의존 지문)·web·system_essentials(회원 경로 감사 지문) — 변경은 선택 인자·진단 문구·공개 행 칸뿐.
- 일상 종합(`-m "not system"`) 실패 3: 신규 시험의 `__main__` 누락·doc_build 철자 대조 줄의 `vj-ok` 표시 누락(둘 다 이번 변경의 관례 위반, 수정)·교재 예산 초과 시점의 예산 단언(압축 후 통과). 세 파일 재실행 78 통과. 관련 시스템 묶음(어휘 보관·번들) 23 통과. 전수 재실행은 하지 않았다.
- 기존 실패(무관): `test_episode4064_repairs::test_member_combined_call_keeps_member_execution_context` 가 단독 실행에서 "현재 회원 턴에서 해당 계약/결과를 조회할 수 없습니다"(이번 변경 설치 전 원본 트리에서도 같음, 전수 안에서는 통과).
- 라이브: 위 재현 문장 전부. 외부 발신·유료 AI 호출 없음(structure 는 오프라인 시험).
- 운영 함정: 하위 작업 셋이 패키지 .py 를 동시에 고쳐 재기동이 `FAILED(boot_artifact_changed)`(17:37) — 제어자는 `data/packages/installed` 도 감시한다. 편집을 모두 끝낸 뒤 `api.py start` 한 번으로 복구(ACTIVE).
