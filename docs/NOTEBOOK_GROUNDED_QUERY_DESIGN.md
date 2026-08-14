# [self:notebook] — 근거 고정 질의(Grounded Query) 설계

> 작성 2026-08-14 · 상태: **Phase 1+2 구현 완료 (2026-08-14, 액션 154)** — Phase 3(인지 통합)은 미착수
>
> **Phase 2 구현 기록 (2026-08-14, 같은 날)**: ①📚 노트북 계기 3탭(질문/노트북/만들기) — `app:` 블록 선언만으로 전 표면 등장(React 신규 0), ask 답변은 handler가 `blocks` IR(문단+인용 heading)을 동봉해 기존 blocks 뷰가 렌더. 실브라우저 전 루프 검증(만들기 폼→드릴 소스 추가 폼에 PEP20 URL→소스 목록 ready→질문 탭 select+ask→답변·[1] 인용 카드 ¶16 렌더, 계기 네트워크 전부 200 · 콘솔 에러 1건은 페이지 로드 시 PWA sw 페치=기존 현상). ②소스 확장: path가 URL이면 자동 분기 — 유튜브=yt-dlp 자막(수동 우선·자동 폴백, 없으면 정직 거부, 60초 창 문단화·loc=[mm:ss] 타임스탬프) / 웹=본문 추출(제목 자동, 클라이언트 렌더 페이지=실패 안내). `url`/`file`=path 별칭. 라이브 14/14 — 실영상(Jeff Su 20분) 자막 21청크, ask가 [19:24] 타임스탬프 인용으로 해당 대목 적중(영어 자막↔한국어 질문 교차), PEP20 웹 4청크 ask 적중, 같은 URL 재add=재색인. ★notebook_core는 서브모듈이라 /packages/reload 밖 — backend touch 재기동(keeper 일시정지 규약 준수).
> 발단: 유튜브 AI 팁 보고서 2026-08-14 자료조사호 — "근거 고정 층과 종합·산출 층을 나누고 배관으로 이어라"(팁 16), "내 문서 더미에 근거 고정 질의를 하는 어휘가 우리 시스템에 얇다"(팁 16 함의).
>
> **Phase 1 구현 기록 (2026-08-14)**: `data/packages/installed/tools/notebook/` (notebook_core.py 색인·인제스트 / handler.py op 8종·ask 생성·인용 후검증). 검증=build --check 전 가드 + 인프로세스 26/26 + 라이브 /ibl/execute 종단 13/13(실보고서 md 31청크+실PDF 52청크, 인용이 실제 원문 대목 적중, not_in_sources 정직, 영문 PDF 교차 언어 ask 적중, search→[table:take] 파이프) + 해마 12용례(대조 시드 포함 — "노트북 배터리"→sense:host 0.812 유지, notebook ask 0.688 직행) + guide notebook.md. **구현 중 실측 봉합 3건**: ①인코딩 replace 폴백이 바이너리를 통과시킴(/bin/ls→141청크) → NUL 스니핑 선행 관문 ②스캔 PDF 판정 30자/페이지가 짧은 정상 PDF 오탐 → 15자로 하향 ③백그라운드 색인 중 소스 remove/delete 레이스 → 존재 가드+자기 청소. **열린 질문 1(영어 성능) 1차 실측**: 영문 논문 PDF에 한국어 질문("bash가 무엇의 약자?")이 정확 답변+인용 — FTS 보완이 작동, 순수 영문 의미 질의는 계속 관찰.

## 0. 한 줄 요약

사용자가 가진 **문서 더미(소스 묶음)에 이름을 붙여 두고, 자연어로 물으면 그 소스 안에서만 답하며 문장마다 출처를 다는** 어휘. NotebookLM의 로컬·파이프라인 판. 부품의 7할(하이브리드 색인·인제스트)은 이미 시스템 안에 있고, 새로 짓는 것은 "노트북 = 이름 붙인 소스 묶음" 층과 "근거 고정 생성 + 인용" 층 둘이다.

## 1. 판별 — 왜 새 단어인가

`ibl_design_philosophy.md` 기준(새 단어 IFF **(a) 기존 어휘로 비싸거나 불가 + (b) 모양이 안정적**)으로:

- **(a) 기존 어휘로 불가**: `[self:read]`+`[self:grep]` 조합은 *키워드* 접근이다. "치과 보장이 제일 나은 곳은?"은 문서에 '치과 보장'이라는 문자열이 없어도 답해야 하는 *의미* 질의라 grep으로 원리적으로 안 된다. 영속 시맨틱 색인 + 제약 생성은 조합으로 표현하면 길고 취약한 raw 코드로 떨어진다 — 전형적 승격 신호.
- **(b) 모양 안정**: NotebookLM이 제품으로 검증한 형태(소스 묶음 → 근거 고정 질의 → 인용 달린 답)를 그대로 따른다. op 공간이 이미 수렴돼 있다.
- **4기준**: 조합성(ask 결과가 통화라 `>> [table:*]` 직결) + 빈도(상설 노트북의 반복 질의) 둘 충족.
- **반-어휘-증식 점검**: "기본 답=스크립트 등록"이 안 되는 경우다 — 영속 색인 + 임베딩 모델 + 생성 계약이 한 몸인 *능력* 단위지, 코드 조합이 아니다.
- **[self:memory]와 별개인 이유**: memory 패키지는 *내 기억·노트*(내가 쓴 것)의 관리다. notebook은 *남이 쓴 문서 더미의 심문*(넣고 묻는 것)이다. 한 단어=한 개념 원칙상 분리가 맞다.

### 명명 결정과 동음이의 위험

`notebook`을 1안으로 한다(NotebookLM 연상 = 사용자 발화와 일치, "묶음+질의" 개념이 한 단어에 담김). **위험**: 한국어 "노트북"=랩탑. "노트북 배터리 어때" 류가 이 액션으로 오라우팅될 수 있다 → 해마 시드에 **대조 용례**를 반드시 동봉한다("노트북 배터리/느려"→`[sense:host]`, "보험 자료 노트북에 넣어"→`[self:notebook]`). 8/5 코퍼스 교정(애매 intent 문맥화 30건)의 선례 그대로. 2안은 `corpus`(동음이의 없음, 대신 사용자 발화와 거리).

## 2. 포지셔닝 — NotebookLM과의 역할 분담

경쟁이 아니라 분업이다(팁 16의 논리를 우리 안에 재적용):

| | NotebookLM (손으로) | [self:notebook] (우리 어휘) |
|---|---|---|
| 적합 | 일회성·크고 지저분한 코퍼스(수백p 스캔 자료) | **작고·민감하고·반복 질의되는 코퍼스** |
| 인제스트 품질 | OCR·표·영상까지 구글 인프라 | 텍스트·PDF·자막 수준 (스캔 PDF는 한계 명시) |
| 자동화 | 공식 API 없음(커뮤니티 CLI/MCP=취약) | **스케줄러·보고서 사슬에 직결** |
| 산출 | 도구 안에 갇힘 | **통화(items) → table 파이프** |
| 프라이버시 | 구글 업로드 | 로컬 sqlite |

목표 용처(수요 실재 근거): ①정기보고서 3편의 원문 정독 층 ②피드백 반복 패턴 추출(팁 12) ③상설 노트북 — 건강검진·회의록·재무+세법(팁 15) ④보험·계약서류 비교(팁 1의 세 조건이 참인 전형) ⑤"책들 서재" 2.2만 파일(7월 forage 실측에서 grep 하강으로 고생한 자리).

## 3. 어휘 설계

단일 액션 + op 디스패치(`_OP_DISPATCHERS` 표준 패턴). 노드=`self`(내 자료), group=`notebook`.

```
[self:notebook]{op:"create", name:"보험비교", note:"3사 치과보장 비교용"}
[self:notebook]{op:"add",    name:"보험비교", path:"~/Downloads/A사.pdf"}
[self:notebook]{op:"add",    name:"보험비교", url:"https://..."}          # 웹페이지
[self:notebook]{op:"add",    name:"보험비교", youtube:"<video_id>"}       # 자막
[self:notebook]{op:"add",    name:"보험비교", text:"...", title:"메모"}   # 붙여넣기(리더 모드 우회, 팁 5)
[self:notebook]{op:"ask",    name:"보험비교", q:"치과 보장이 제일 나은 곳은?"}
[self:notebook]{op:"search", name:"보험비교", q:"임플란트"}               # 생성 없이 발췌만(싼 경로)
[self:notebook]{op:"sources", name:"보험비교"}                            # 소스 목록·상태
[self:notebook]{op:"remove", name:"보험비교", source_id:3}
[self:notebook]{op:"list"}                                                # 노트북 전체
[self:notebook]{op:"delete", name:"보험비교"}
```

- **op 어휘화**: src yaml `ops: {default: "ask", values: [...]}` — 의식 에이전트가 op 차원까지 추천.
- `runs_on: pc_only` — sentence-transformers·sqlite-vec가 폰 번들에 없다. 폰은 `[others:ask]`로 맥에 부탁(명함 경로).
- 기본 op는 `ask`(가장 빈번할 동사).

### 통화 계약

```json
{
  "answer": "A사가 치과 보장 한도가 가장 높다[1]. 다만 임플란트는 B사만 포함한다[2].",
  "citations": [
    {"n": 1, "source": "A사.pdf", "loc": "p.12", "quote": "치과 치료 연 300만원 한도"},
    {"n": 2, "source": "B사_약관.pdf", "loc": "p.34", "quote": "임플란트 1개당 ..."}
  ],
  "items": [ /* citations를 행으로 편 것 — table 파이프용 */ ],
  "not_in_sources": false
}
```

- `items`=citations의 행 투영 → `>> [table:filter]` 등 직결 (통화=items 원칙).
- `not_in_sources: true` = "소스에 없다"의 정직 반환(모름 허용 — 8/12 환각 억제 3종). 침묵 빈답 금지(파이프 침묵 실패 시리즈의 계약 그대로).
- `search` op는 `{items:[{source, loc, quote, score}]}`만 — LLM 0, 발췌 확인·파이프용 싼 경로.

## 4. 아키텍처 — 3층

```
인제스트(add)        색인(자동)                생성(ask)
경로/URL/자막/텍스트 → 추출 → 청크 → 임베딩+FTS5 → 검색(하이브리드) → 경량AI 제약 생성 → 인용 검증 → 통화
```

### 4-1. 인제스트 (재사용이 원칙)

| 소스 | 추출기 | 비고 |
|---|---|---|
| .md/.txt | 직접 읽기 | 인코딩 utf-8→cp949 폴백 (`self:grep` 2층화 선례) |
| PDF | `[self:read]` 계열 추출기 재사용 (+`tables:true` 표) | **스캔(이미지) PDF는 미지원 명시** — 거부 메시지에 한계를 적는다 |
| 웹페이지 | web 패키지 크롤러 | 본문 추출 후 텍스트로 |
| 유튜브 | youtube 패키지 자막 추출 | AI 팁 보고서와 같은 재료 |
| 붙여넣기 | text 파라미터 | 리더 모드 우회 경로(팁 5) |

- **원본은 참조가 기본**(경로+mtime 저장), 사본은 만들지 않는다. 회상 시 mtime 비교로 stale 노출(포식 기억의 lazy 부패무효화 원리) — 재색인은 `add` 재호출로 명시적으로.
- 인제스트가 클 수 있으므로(수백 페이지) **add는 백그라운드 기본**(즉시 queued 반환 + 상태는 `sources` op — family-news/신문 발행 선례, 도구 60s 타임아웃 방어). 소스 1~2개 소량은 동기 완료.

### 4-2. 색인 — blog RAG 엔진 이식

`blog/tool_blog_rag.py`가 정확히 이 기계다: **jhgan/ko-sroberta-multitask(768차원) + sqlite-vec + FTS5 BM25 하이브리드, 미설치 시 FTS5 폴백**. blog 자신이 KThoughtsSystemV2에서 "핵심 알고리즘 이식, 외부 의존성 없이 독립 동작"으로 왔듯, **새 패키지로 이식(코퍼스-무관하게 일반화)하고 blog은 무손상으로 둔다.**

- 교차 패키지 importlib 차용은 금지(8/5 검색 통합 때 소멸시킨 패턴). 이식=중복이지만 하우스 패턴이고, 나중에 셋째 사용자가 나타나면 backend/datastore 공유 모듈로 승격을 그때 검토.
- 저장: `data/notebooks.db` 단일 sqlite — `notebooks / sources / chunks / chunks_vec(vec0) / chunks_fts(FTS5)`. vec0 갱신은 DELETE→INSERT(sqlite_vec quirk).
- 청크: 문단 경계 우선, 400~800자 목표 + 겹침 1문장. 청크마다 `(source_id, loc)` — loc은 PDF=페이지, 자막=타임스탬프, 텍스트=문단 번호. **인용의 해상도가 loc에서 결정된다.**
- **임베딩 모델: 해마 것(`ibl_embedding`)을 쓰지 않는다** — IBL 코드 연상에 파인튜닝된 모델이라 일반 문서에 부적합. ko-sroberta로 시작. ⚠️ 열린 질문: 영어 문서 성능(ko 특화 모델) — 영어 코퍼스가 실제로 자주 들어오면 다국어 모델(예: paraphrase-multilingual) 교체 검토. DB에 `embedding_model` 기록해 교체 시 재색인 판정.

### 4-3. 근거 고정 생성 (ask)

1. 하이브리드 검색으로 상위 K청크(기본 12, 토큰 예산 상한) 수집.
2. **경량 AI** 1회 호출, 제약 프롬프트:
   - "아래 발췌들**만** 근거로 답하라. 일반 지식으로 보충 금지."
   - "모든 주장 문장에 [n] 인용을 달라. n은 발췌 번호."
   - "발췌에 답이 없으면 지어내지 말고 not_in_sources를 참으로."
   - 노트북 `note`(생성 시 적은 목적)를 시스템 컨텍스트로 동봉 — 팁 7(노트북 단위 커스텀 지시)의 구현.
3. **인용 후검증(결정론)**: 답의 [n]들이 실제 전달한 발췌 번호인지, quote가 해당 청크에 실재하는지 확인 — 불일치 인용은 제거하고 `citation_dropped` 카운트를 정직 반환. (생성층의 환각을 코드층이 잡는 이중 방어.)
- 모델 티어: 기본 경량(제약된 과제라 충분). 어려운 종합 질의는 호출자가 에이전트 층에서 재종합하면 된다 — 층 분리(팁 16) 원칙상 notebook은 근거 고정 층만 담당.

## 5. 계기 (app: 블록)

📚 노트북 계기, 3탭 — `app:` 블록 선언으로 전 표면 자동 등장:

1. **질문**: 노트북 select(`options_action: list`) + q 입력 → ask → 답 + 인용 목록(card_list, 인용 클릭=원문 위치)
2. **노트북**: card_list(이름·소스 수·최근 질의) → 드릴 = 소스 editable_list(추가·제거·재색인)
3. **만들기**: form(name, note)

`phone_render: false`(pc_only 실행이라 폰 네이티브 숨김, 원격 런처=맥 리모컨으로 사용 가능).

## 6. 함정 체크리스트 (기존 부채에서)

- [ ] **windows 이식성**: 위험지대가 바로 data/packages/ — fcntl 금지, 원자쓰기는 limb_keys 식 무-flock 패턴. 이식성 게이트(pre-commit) 통과 확인.
- [ ] **package-submodule-reload-gap**: tool_*.py 서브모듈은 /packages/reload 밖 — 수정 후 backend touch 재기동.
- [ ] **1500줄 규칙**: handler.py(op 디스패치) / tool_notebook_index.py(색인 엔진) / tool_notebook_ingest.py(추출) / tool_notebook_ask.py(생성·검증) 선분할.
- [ ] **해마 시딩**: .venv 파이썬 필수(시스템 python3=sqlite_vec 없음), `add_examples_batch`(source='manual_seed') 후 `_load_model_sync()`→`_index_batch` 재색인(벡터 조용히 안 붙는 함정). **대조 시드 동봉**(§1 노트북=랩탑 동음이의).
- [ ] **코퍼스 param 가드**: build --check가 시드 용례의 파라미터를 검증하므로 tool_input.get은 리터럴로.
- [ ] **어휘 변경 7표면**: checklist + 가이드 `notebook.md` 신설 + guide_db 등록 + self.yaml guides/tags + ibl.md 어휘 줄 + 재학습 대기열 합류.
- [ ] **백업 규약**: 실험 중 DB 백업은 `data/_backups/YYYY-MM-DD_notebook/`.

## 7. 검증 계획

1. `scripts/build_ibl_nodes.py --check` 전 가드(삼각 정합 · 액션 152→153).
2. 인프로세스: 청크 경계·인코딩(cp949 실파일)·vec0 갱신·인용 후검증(가짜 인용 제거)·not_in_sources 정직 반환·FTS 폴백(모델 미로드).
3. 라이브 종단: 실제 PDF 2~3개로 create→add(백그라운드 완주)→ask(인용이 실제 원문 대목인지 육안)→search→remove→delete 원상복구.
4. 파이프: `[self:notebook]{op:"search"} >> [table:take]{n:3}` 통화 흐름.
5. 실브라우저: 계기 3탭 렌더·질문→인용 표시·콘솔 무에러.
6. 해마 연상 검증: "보험 자료 넣고 물어봐"→notebook 직행, "노트북 배터리"→sense:host 유지.

## 8. 단계

- **Phase 1 (MVP)**: 어휘 + 색인 + ask/search + 통화 계약. 계기 없음. 실사용 1건(보험 또는 보고서 원문)으로 품질 실측.
- **Phase 2**: 계기 3탭 + 백그라운드 인제스트 상태 + 유튜브/웹 소스.
- **Phase 3 (인지 통합)**: 상설 노트북을 0단계 회상의 냄새(scent)로 노출 — "이 주제로 물을 수 있는 노트북이 있다"(포식 기억 owner 상시 노출 원리). 보고서 사슬 통합: 정기보고서가 채택 원문을 자기 노트북에 적재 → 다음 호가 ask로 재질의(팁 4 "채택한 것은 원문까지" + 팁 8 "승격"의 구현). 피드백 노트북(팁 12).

## 9. 열린 질문

1. 임베딩 모델의 영어 문서 성능 (ko-sroberta 특화) — Phase 1 실측 후 결정.
2. 스캔 PDF: OCR을 붙일 것인가, "NotebookLM에 손으로"로 남길 것인가 — §2 분업표대로 후자가 기본.
3. Google Docs류 살아있는 문서 동기화(팁 5-③) — mtime 참조 방식이라 로컬 파일은 자연 해결, 클라우드 문서는 범위 밖.
4. `search` op와 `[self:grep]`의 경계 서술 — 가이드에 "문자열=grep / 의미=notebook" 결정 트리 명시.
