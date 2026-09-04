# 노트북 — 근거 고정 질의 [self:notebook]

문서 더미(PDF·텍스트)에 이름을 붙여 두고, 물으면 **그 소스 안에서만** 답하며 문장마다 출처 인용을 다는 어휘. NotebookLM의 로컬·파이프라인 판. 설계 정본: `docs/NOTEBOOK_GROUNDED_QUERY_DESIGN.md`

## 언제 쓰나 — 결정 트리

| 상황 | 어휘 |
|---|---|
| 문서 안 **문자열**을 찾는다 ("'위약금'이라는 단어 있나") | `[self:grep]` |
| 문서 더미에 **의미로** 묻는다 ("위약금 조건이 뭐야") | **`[self:notebook]`** |
| 웹에서 **찾아야** 한다 (소스가 손에 없음) | `[sense:search]` 계열 |
| 파일 하나를 통째로 읽는다 | `[self:read]` |

쓸 조건 세 가지(팁 보고서 2026-08-14 팁 1): ①답이 어느 문서에 있는지 이미 안다 ②소스 형식이 제각각(PDF+텍스트 혼재) ③환각이 용납 안 되는 판. 셋 다 아니면 일반 경로가 낫다.

## 워크플로

```
[self:notebook]{op: "create", name: "보험비교", note: "3사 치과보장 비교"}   # note=ask 답변의 렌즈
[self:notebook]{op: "add", name: "보험비교", path: "/…/A사약관.pdf"}
[self:notebook]{op: "add", name: "보험비교", path: "https://youtu.be/<id>"}   # 유튜브=자막, loc=[mm:ss]
[self:notebook]{op: "add", name: "보험비교", url: "https://…"}                # 웹페이지 본문 (url=path 별칭)
[self:notebook]{op: "add", name: "보험비교", text: "상담 메모…", title: "B사 상담"}
[self:notebook]{op: "ask", name: "보험비교", query: "치과 보장 제일 나은 곳은?"}
```

**소스 종류(Phase 2)**: path가 URL이면 자동 분기 — 유튜브 URL=자막(수동 우선·자동 폴백, **자막 없는 영상은 정직 거부**, 60초 창 문단화·loc=타임스탬프) / 그 외 URL=본문 추출(클라이언트 렌더 페이지는 실패 안내 → text 붙여넣기로). 같은 URL 재add=재색인.

**계기(📚 노트북, 앱 표면)**: 질문(노트북 select+질문→답+인용 카드) / 노트북(카드→드릴: 소스 목록·빼기 / **관리 탭**=소스 추가 폼+노트북 삭제[danger·confirm]) / 만들기. `phone_render: false`(pc_only — 원격 브라우저=맥 리모컨으로는 사용 가능).

- **ask**(기본 op): 답 + `citations[{n, source, loc, quote}]` + `not_in_sources`. 인용은 결정론 후검증을 거친다 — quote는 모델이 아니라 코드가 청크 원문에서 뽑으므로 인용 환각이 원리적으로 없다. 무효 인용은 제거되고 `citation_dropped`로 집계.
- **search**: 생성 없이 발췌만(LLM 0) — 싼 경로. items 통화라 `>> [table:take]` 등 파이프 직결.
- **sources**: 소스 목록 + 색인 상태 + **stale**(원본 파일이 변경=`modified`/삭제=`missing`). 재색인 = 같은 path로 add 재호출.
- 같은 path를 다시 add하면 기존 색인을 갈아엎는다(재색인).

## 함정·한계

1. **스캔(이미지) PDF는 정직 거부** — OCR 없음. NotebookLM 등 OCR 있는 도구를 쓰거나 텍스트 변환 후 넣을 것.
2. **소스로 안 붙는 웹페이지**는 본문을 복사해 `text` 파라미터로(리더 모드 우회).
3. **15만자 초과 소스는 백그라운드 색인** — add가 `queued:true`로 즉시 반환, `op:sources`로 상태 확인.
4. **시맨틱 의존성(sentence-transformers·sqlite-vec) 미로드 시 FTS5 키워드 검색으로 강등** — 응답에 명시됨. 의미 질의 품질이 떨어지니 문자열이 겹치는 질문으로 바꿔 물을 것.
5. **임베딩은 ko-sroberta(한국어 특화)** — 영문 문서도 동작하나(FTS 보완) 순수 영문 의미 질의는 품질이 낮을 수 있다. 해마 임베딩 모델과 무관.
6. **runs_on: pc_only** — 폰에서는 `[others:ask]`로 맥에 부탁.
7. 원본은 **경로 참조**(사본 없음) — 파일을 옮기면 stale=missing. 붙여넣기(text)는 DB에 산다.
8. 인코딩: utf-8→cp949→euc-kr 자동 폴백. 바이너리는 NUL 스니핑으로 거부.

## 저장 위치

`data/notebook/notebooks.db` (sqlite WAL — notebooks/sources/chunks + FTS5 + vec0). 백업은 `VACUUM INTO` 규약.

## 상설 노트북 권장 용처 (설계 Phase 3 전 단계의 수동 활용)

- 보고서 원문 정독층(정기보고서가 채택한 원문 재질의) · 피드백 반복 패턴 · 건강검진 연도별 · 계약·보험 서류 비교

## 포식 기억 — 노트북의 지도 (2026-09-03)

노트북을 만들거나 소스를 넣으면 시스템 AI 가 **자동으로 조사**해 `notebook:<이름>` 몸의 포식 기억 문서를 쓴다(어느 소스가 무엇이고 어떤 물음에 답하나, 겹침·용어). 문서 = `[self:forage]{op:"recall", body:"notebook:<이름>", locus:"notebook:<이름>"}` 의 `doc`. 묻기 전에 그 문서를 보면 **어느 소스에 답이 있는지** 알 수 있고, `ask`/`search` 에 `source:"<제목 일부|id>"` 로 좁히면 청크 검색이 그 안에서만 돈다. `ask` 는 이 문서를 발췌 판단의 지도로 자동으로 함께 읽는다(근거는 여전히 발췌만). 질의로 새로 안 것은 `[self:forage]{op:"note", body:"notebook:<이름>", locus:"notebook:<이름>/<소스 제목>", …}` 로 되적는다. 조사 요령은 `folder_survey` 가이드의 '노트북(문서 더미)' 절.

## 실측 기록 (자동 누적)

> 실행 에이전트가 턴 종료 후 덧붙인다.
- 2026-09-03 실측: 포식 기억 자동 조사는 신규 create/add 시점부터 도는 것이라, 그 이전에 만들어진 노트북은 소스가 이미 색인돼 있어도 recall 이 map_count 0 · doc null 로 비어 있다 — 기존 노트북은 수동 첫 조사가 필요하다.

## 문서 단위 (2026-09-04 개정) — 카드가 지도, 답할 때는 골라서 통째로

650자 청크는 **위치 색인**이지 이해의 단위가 아니다. 이해의 단위는 문서(소스)다.

- **카드** `[self:notebook]{op: "card", name}` — 소스마다 AI 가 문서를 한 번 읽고 `> 한 줄`·무엇인가·구조[자리]·핵심 주장·답할 물음을 쓴다. `add` 뒤 자동. 정본은 `data/notebook/cards/<노트북>/<source_id>.md` — 사람이 고치면 지도가 따라온다. 다시 쓰려면 `force: true`.
- **지도** `{op: "map", name}` — 카드 한 줄 목록(모델 호출 0). "무엇이 있나"는 검색이 아니라 이것.
- **질문** `{op: "ask", name, query}` — 사서(경량)가 지도와 검색 힌트(질문의 드문 낱말이 실제로 나오는 문서)를 보고 읽을 문서를 고르고(≤4·본문 합 ≤9만 자), 통째로 읽어 답한다(평가 축). 인용은 `[#소스번호 자리]`. `mode` = read(문서를 읽음) · map(지도만으로 답) · none(주제 없음). 큰 문서는 카드+앞부분으로 강등하고 신고한다. 카드가 없는 노트북은 옛 발췌 검색 경로, `chunks: true` 로 강제 가능.
- **소개** `{op: "digest", name, source}` — 소스 하나를 처음부터 끝까지 읽어 소개(구간 요지 → 소개문).
- **발췌** `{op: "search", name, query}` — 인용문의 정확한 자리를 찾을 때만(LLM 0).
- 비용: ask 한 번에 30~70초·수만 토큰이 든다. 쓸모없는 5천 토큰보다 쓸모 있는 4만 토큰이 싸다는 판정(2026-09-04). 되묻기 대신 지도를 먼저 보라.

