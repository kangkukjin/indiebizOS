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
[self:notebook]{op: "add", name: "보험비교", text: "상담 메모…", title: "B사 상담"}
[self:notebook]{op: "ask", name: "보험비교", query: "치과 보장 제일 나은 곳은?"}
```

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
