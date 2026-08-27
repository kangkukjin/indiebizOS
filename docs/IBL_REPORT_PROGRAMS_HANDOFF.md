# 핸드오프 — 세 일간 보고서를 IBL 완성 프로그램으로 (품질 반복 인상)

> 2026-08-28 작성. 사용자 지시(원문 취지): **"부동산뿐 아니라 AI 팁·AI 동향 보고서도 IBL
> 문장으로 만들되, 품질을 높이는 것을 여러 번 시도하라. 그 과정에서 지금 우리가 했듯이
> IBL 을 고칠 부분을 찾게 될 것이다."**
>
> 상위 판정(2026-08-27, 이 작업의 헌법): **"초안이라는 개념을 좋아하지 않는다. 파이썬이면
> 몇백 줄도 짜는데 IBL 로 좋은 보고서를 쓸 수 있어야지. 그게 IBL 의 한계 때문에 안 된다면
> IBL 을 고치고."** — 목표는 "초안"이 아니라 **가이드 품질 기준을 충족하는 완성 산출물**이다.

## 0. 지금 어디까지 왔나 (2026-08-28 아침 기준)

- **부동산**: 완성 프로그램 증명 완료 — 순회 커서 선출 → molit 12건 → 철학 평가(fields)
  → 뉴스 가지 → 가격 지형 분석·총평(brief 2편) → blocks 혼합 문서(산문+표+카드) → 원장
  갱신(self:edit, 사본 실증). 개정 문법으로 **11/11 완주 75초**. 실행 기록·산출물 경로는
  `docs/VOCAB_COMPOSABILITY_HANDOFF.md` "초안 은퇴" 절.
- **AI 팁**: 증류 코어 증명 — `each{후보} do: "[sense:video]{op:'transcript'} >>
  [self:struct]{schema:…, grounded: true}"` 가 2만 자대 자막에서 grounded 통과 42행
  (팁·단계·도구·_quote·출처). **완성 프로그램은 미조립** — 원장 dedup 은 됐고, 남은 것:
  주제 선정, 팁 절제(3~7건), 보고서 산문(머리글·시도 후보), 원장/DB 갱신 단계.
- **AI 동향**: 가장 멀다. 원장($기준선) 주입·섹션 분류·문서화는 되나, **섹션 고사**(검색
  재료 부족 — 쿼리 1개는 가이드의 "섹션별 3회+" 미달)와 **델타 서사**(직전 보고서 대비
  "무엇이 새로운가" — 이 보고서의 영혼)가 프로그램에 없다. `queries`(배치 팬아웃)·
  `headlines`·`curate`, `$직전 = [self:read]{최신 보고서}` 주입이 미개척 재료.

## 1. 이번 아크가 IBL 에 이미 고친 것 (다 쓸 수 있다)

| 개정 | 내용 | 커밋 |
|---|---|---|
| 치환 의미론 | 통짜 `.path` 참조 = **원형**(list/dict/스칼라). bare `$var`=v4 추출·문장 속=문자열화 불변 | `09af296c` |
| 파이프 머리 | `$변수 >> [액션]` / `$변수.path >> [액션]` — 통화 방출(_var_emit) | `09af296c` |
| items 개방 | 단항 변환자 전부+render_document 가 `items`(array) 공개 — 리터럴·원형 씨앗 | `09af296c` |
| 문자열 식 | compute/식 언어에 split/replace/strip/upper/lower/contains/join | `09af296c` |
| blocks 변수 | document blocks 에 `$x.message`·`$x.columns`·`$x.rows`·`$x.items` 주입(B52) | `2dc1c1d9` |
| struct 본문 | transcript 봉투·외부화 파일(saved_to_file) 따라가기+타임스탬프 정규화 | `935470cf` |
| 표면 티켓 | 120초 넘는 실행도 `execute_ibl{recover:"티켓"}` 로 결과 회수(F51-1) | `c6c43332` |
| 품질 계약 | leaf 액션에 `criteria:` 선언 → 판정자 심사·재시도 1회·`error_type:"quality"` | `f675498d`~ |
| 트레이스백 | 실패 봉투에 frames·error_type·input·py_tail — 조립 디버깅의 눈 | `f14c86e2` |

조립 규약(실측): 씨앗은 리터럴이면 아무 변환자나 `items` 로 직접 / 변수는 `items:"$x"`
주입 또는 파이프 머리 / 섹션 보장=섹션별 `$변수` 가지(합친 뒤 분류하면 AI 가 버릴 때
섹션이 빈다) / 표의 열은 `table:ai` 의 `fields` 로 계약 / 산문은 brief 로 분리해 blocks
paragraph 에(표에 행으로 섞지 말 것) / **정직 표지(rows_in·rows_dropped·branches_honesty·
passthrough_rows)를 읽고 어느 가지가 왜 비었는지 판단**할 것.

## 2. 다음 세션이 할 일 — 품질 반복 인상 루프

보고서마다 (팁 → 동향 순 권장, 부동산은 다듬기):

1. **가이드를 먼저 정독** — 품질 기준의 정본은 각 가이드다(`youtube_ai_tips_report.md`
   §1 증류 헌법 / `ai_trend_report.md` §3 델타 서술·§2-4 신뢰도·§2-5 신선도 /
   `housing_report.md` §1 주거 철학·§1-5/1-6 평가표). 프로그램의 채점표가 이것이다.
2. **완성 프로그램 조립 → 실행** (`/ibl/execute` + ticket, 긴 실행은 recover 폴링).
3. **산출물을 가이드 기준으로 채점** — 실제 최근호(outputs/ 폴더)와 나란히 놓고 비교하면
   갭이 구체화된다.
4. **갭을 분해**: (a) 일처리(지시문·파라미터·조합 선택) → 문장 수정 후 재실행.
   (b) IBL 결함/공백 → 수리성(결함·비대칭·이음매 누락)은 **묻지 말고 근본 집행**(가드
   시험+은퇴 등록 포함), 문법(표준) 개정은 사용자 판정 요청. 이번 아크의 선례: 판정
   후보를 명확한 목록으로 모아 제시하면 사용자가 일괄 판정해 준다.
5. **반복** — 품질이 가이드 기준에 닿을 때까지. 회차마다 실험 원장
   (`docs/VOCAB_COMPOSABILITY_HANDOFF.md`)에 결과·수리·교훈을 한 항목으로 남긴다.

**완료 기준**: 세 보고서 각각, 가이드 기준을 충족하는 완성 산출물을 내는 프로그램이
검증됨. **스케줄(정기보고) 편입 여부는 별도 사용자 판정** — 프로그램이 준비됐다는 보고까지가
이 작업의 끝이다.

## 3. 보고서별 예상 과제 (이번 아크의 정찰)

- **팁**: 주제 선정(covered 원장의 recent_topics 로테이션), 팁 절제(42행→3~7건 선별 =
  ai 한 칸), 과장 보정(hype 필드가 struct 에서 누락되곤 함 — schema 표현 개선 또는 후속
  ai), 보고서 형태(가이드 §5), `_covered_videos.json`·`db/tips.json` upsert(원형 유지 —
  json 병합을 문장으로 어떻게? `[self:script]` json원장 또는 edit. **막히면 IBL 수리 후보**).
- **동향**: 검색 재료 확충(`queries` 팬아웃·`headlines`·영어 검색 — 가이드 최소 횟수 충족),
  델타 서사(`$직전` = 최신 보고서 읽기 → ai 지시에 주입해 NEW/CHANGED 구분 — 파일명이
  날짜 사전순이라 `[self:file_find] >> sort >> take{1}` 로 최신 호를 문장 안에서 찾을 수
  있는지가 첫 실험), 조건부 작성 게이트(§3-0 — `[if:]` 로 "중대 변화 없음" 분기),
  `_coverage_ledger.json` 롤링 갱신.
- **부동산**: 지역 분석 축(§3-1 — 첫 방문 풀 분석 vs 재방문 델타 분기), 평가표 5축 정식
  적용, 호가 소스 병행(molit 은 2달 지연), `db/regions/<슬러그>.json` upsert, HTML 렌더
  (blocks → format:"html")와 공유창고 등재 규약(§0).

## 4. 주의 (이번 아크의 사용자 교정·함정 — 어기면 다시 교정받는다)

- ★**가이드에 구체 IBL 문장을 적지 말 것** (2026-08-27 사용자 교정): 가이드는 원리·경계·
  "매번 직접 조합하라"만. 좋은 문장의 정착 통로는 해마(증류)다. 프로그램 원문은 실험
  원장(docs)이나 워크플로우 등록(`[self:workflow]`) 쪽이 자리 — 등록 여부도 품질이 선 뒤에.
- ★실험 중 **실제 원장·DB 를 건드리지 말 것** — 상태 쓰기는 사본(/tmp)으로 실증하고,
  실 갱신은 프로그램이 "준비 완료" 판정을 받은 뒤의 일. 산출물도 outputs/ 정본 폴더가
  아니라 스크래치에(정본 폴더는 정기보고 앱·아카이브 규약이 읽는다).
- ★라이브 backend/ 에 스크래치 .py 를 만들 땐 감시 밖 이름(`test_*.py`·`_이름.py`)만.
- ★120초 넘는 실행은 표면이 끊겨도 정상 — ticket 을 싣고 recover 로 회수(F51-1 규약).
- ★zsh 로 봉투 JSON 을 다룰 때 `echo "$JSON"` 금지(백슬래시 훼손) — printf/파일로.
- ★어휘·문법을 고치면: 가드 시험 신설, 옛 계약은 `data/retired_contracts.yaml` 등록,
  `python3 scripts/build_ibl_nodes.py` 재생성(+android 번들), ibl.md 언어의 경계 갱신,
  36회차류 옛 계약 시험 개정. 이번 아크에서 몸의 관문들(값 판정·은퇴·단일 러너)이 개정
  작업 자체의 결함을 세 번 적발했다 — 관문이 물면 관문이 옳다고 먼저 가정할 것.
- 커밋은 pathspec 으로(동시 세션=공유 인덱스), main 직접.

## 5. 핵심 파일 지도

- 실험 원장(이력·교훈 전부): `docs/VOCAB_COMPOSABILITY_HANDOFF.md` 뒤쪽 2026-08-27 절들
- 가이드 3종: `data/guides/{youtube_ai_tips_report, ai_trend_report, housing_report}.md`
- 언어 가드: `backend/test_language_revision_var_semantics.py`(V1~V8) ·
  `test_pipe_currency_failures.py`(P1~P31) · `test_struct_body_seam.py`(S1~S4) ·
  `test_surface_ticket_recovery.py`(T1~T8)
- 치환·파서·엔진: `backend/ibl/{workflow_binding, ibl_parser, ibl_engine}.py` ·
  식 언어: `backend/common/safe_expr.py` · 통화 게이트: `backend/common/currency.py`
- 실제 최근호(품질 비교 대상): `outputs/{ai_tips_reports, ai_trend_reports, housing_reports}/`
