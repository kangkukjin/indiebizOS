# 산출물 척추(A~G) 빌드아웃 핸드오프

> 작성: 2026-06-15. 한 세션에서 산출물 생산 척추의 **새 골격**(G·sense:host·데이터 통화·B 구조화·C 공유 IR)을
> 전부 세우고 종단 검증함. 이 문서는 그 상태와 **남은 본진(producer 이관)**을 신선한 세션이 이어받기 위한 지도.
> G 루프의 세부는 별도 문서 `docs/G_LOOP_CLOSURE_HANDOFF.md` 참조.

---

## ★ 남은 일 (2026-06-15 기준, 다음 세션 START HERE)
조합 밀도 본진·소소 잔여·로컬 점검 전부 완료. 남은 건:

1. ✅ **해마 모델 재학습 완료(로컬 MPS, 2026-06-15)** — `cloud_training/ibl_embedding_trainer_cloud.py` batch16/seq64/10ep, M4 Pro(OOM 없음). best=epoch4 **code-Top5 93.4% / desc-Top5 93.3%**(코퍼스 2527, base 42.9%→93.4%). 현 프로덕션(92.8/94.5)과 동등. 새 모델 `data/models/ibl_embedding/` 교체+rebuild_index(2527)+백엔드 touch reload 완료. 백업=`data/models/ibl_embedding.bak.20260615_135146`. **⚠️후속(부분미해소)**: docx-쓰기("워드로"→여전히 read{docx} #1, structure>>document #2)·PPT(→delegate)·book검색 등 **타깃 모호성 충돌 잔존** — 쓰기경로 코퍼스가 적어(각 3~6건) 빈도 많은 옛 경로에 밀림. 해소=write-path 용례 대폭 추가(재균형)+재학습. cloud_training/make_bundle→trainer 그대로 재실행하면 됨.
2. **별도 트랙 — 폰-자아 후속** (`PHONE_SELF_FOLLOWUPS_HANDOFF.md`): 의료기록 삭제op·channel트리거·받아쓰기 등. 산출물 척추와 무관.
3. **선택(품질 한 단계 더)**: ①**승격 UX/하향진화** — 만족 워크플로우 동결→앱(아키텍처 미구현 빈자리, [[principle_crystallize_workflow]]) ②"더 나은 결과물" 확산(newspaper식 dedup/중요도/G검증을 다른 목록형에) ③G 루프를 document/chart 산출에 옵션 연결.
4. ✅ **자잘 정리 완료(2026-06-15, 커밋 30cf003 척추전체+818591e self-check)**:
   - ✅ **self-check 활성 프로젝트 컨텍스트** — `world_pulse_health.run_self_check`가 `params.project_id="앱모드"`(앱/수동 런처와 동일 시스템 프로젝트) 주입. 라이브 전수 재점검: **path-error 125→0**, 남은 실패 2건뿐(kosis 404=업스트림 기존·company 'TEST'=테스트파라미터 아티팩트, 실 버그 0). false-positive를 깨끗한 신호로 전환.
   - ✅ **web markdown dead code** — web/handler.py에 `markdown_to_html` 없음(이미 정리됨), `generate_section`은 뉴스 수집 함수로 live. backend `gen_newspaper.py`/`generate_newspaper.py`는 CLAUDE.md 문서화된 독립 스크립트라 보존(범위 밖).
   - ✅ **health query 반환형** — `self:health` query는 app/instrument 소비처 0(에이전트 전용), 반환 JSON의 `text` 키에 사람용 텍스트 보존 → 앱 영향 없음 확인.
   - stock quote/world는 의도적 통화 제외(원칙상) — 무변경.

---

## 0. 개념 틀 (왜 이걸 했나)

IBL을 **산출물 생산의 척추 A~G**로 본다:
- **A 획득**(sense:* 41) · **B 구조화**(콘텐츠→IR) · **C 공유 IR**(포맷 중립 문서 모델) ·
  **D 배치 / E 스타일**(producer 내부) · **F 렌더/emit**(IR→바이트) · **G 비평**(render→보고→판단→수정)
- 관통 명제(사용자): **"언어는 명사(파이프를 흐르는 데이터 모양)에 산다."** 동사(액션)는 싸고, 조합성은
  공유 명사(통화·IR)에서 나온다. → engines가 저마다 다른 입력을 받으면 "언어 의상을 입은 스위치 더미".
- 또 하나의 헌법(사용자): **아티팩트 종류별로 IR 하나 + emitter 다수.** "모든 걸 한 IR로 뭉개기"가 아니다
  (슬라이드=슬라이드 IR, 문서=문서 IR). ← producer 이관 시 가장 중요한 분별.

세션 직전 진단: A·F는 강했고, B·C·G·통화·맥 자기몸(sense:host)이 비어 있었다. 이번에 그 칸들을 채움.

---

## 1. 이번 세션 완료 (전부 라이브 검증, 액션 122→127)

### G 비평 루프 ✅ (세부: G_LOOP_CLOSURE_HANDOFF.md)
- 플래그십 일러스트 슬라이드 inner loop: `media_producer/slide_image.py` `_critique`·`_gen_with_critique`
  (합성 전 원시 일러스트 자평→교정 재생성 기본2R→최고점채택, fail-open).
- **보편 백스톱**(평가자가 픽셀을 봄): `consciousness_agent.lightweight_ai_call(images=)` +
  `agent_cognitive._collect_visual_artifacts` + `_evaluate_achievement(visual_artifacts=)` 멀티모달화 +
  `evaluator_prompt.md` 지침. **추가형·기본값보존·fail-safe.**
- critic 일반화: `engines:image_critic` `preset`(slide_illustration 기본/general). verdict `{passed,score,issues,notes}` 공유통화.

### sense:host — 맥 자기수용감각 ✅
- `[sense:host]{op: status(기본)/apps/resources}` — 기계를 화면이 아니라 직접 내성. `pc-manager/handler.py`
  `_host_op`/`_host_status`/`_host_apps`/`_host_resources` (psutil + lsappinfo 전면앱 + runtime_utils.detect_body 몸이름,
  권한 프롬프트 無, mac_only). tool.json `host_op`, sense.yaml device 그룹.
- 해마 17용례(distilled). 직접 기계상태 표현 연상 양호, 모호한 진단표현은 sense:self_check와 충돌(차기 재학습 몫).

### 데이터 통화 (table currency) ✅ — "언어는 명사에 산다"의 실천
- **통화 정의**: `table = {columns:[x, s1, s2...], rows:[[x,v1,v2...],...]}` (첫 열=x/범주, 나머지=시리즈).
- **소비자 2**: `engines:chart`(visualization/handler.py `_table_to_chart_data`) · `engines:spreadsheet`
  (system_essentials/handler.py, table→headers/rows).
- **생산자 2**: `sense:world_bank`(study/handler.py `_fetch_world_bank_data` — JSON {success,indicator,country,table,summary},
  연도 오름차순) · `sense:stock` op:history(investment/handler.py `_attach_price_table` — 날짜·종가, krx·fmp 공통).
- **`>>` 자동 파이프**: chart·spreadsheet가 `_prev_result`의 table 자동 수용(`_extract_table_from_prev`).
  → `[sense:world_bank]{...} >> [engines:chart]{title,chart_type}` 무reshape 동작(라이브 검증).

### B 구조화 원자 ✅
- `[engines:structure]{content, instruction}` — 경량 LLM 편집자가 콘텐츠→문서 IR blocks.
  `media_producer/handler.py` `structure_document` + `_STRUCTURE_PROMPT`. `>>` 시 이전 텍스트를 content로 수용.

### C 공유 IR (문서) ✅
- **문서 IR**: `{title?, blocks:[{type,...}]}`. 블록 타입 = heading/paragraph/list/image/**table**/quote/code/divider.
  ★table 블록 = 데이터 통화 `{columns,rows}` 그대로 재사용(IR↔통화 한 이음매서 만남).
- **emitter 3종(하나의 IR → 다수)**: `[engines:document]{blocks, title?, format: html(기본)/pdf/png, filename?}`.
  `media_producer/handler.py` `render_document` + `_doc_blocks_to_html`. pdf·png는 동일 HTML을 Playwright로
  (page.pdf A4 / full_page screenshot). `_prev_result.blocks/title` 자동 수용 → `structure >> document` 파이프.
- 검증: 8블록 전타입 HTML ✓ · 동일 IR→html/pdf/png 3포맷 ✓ · `structure >> document` ✓.

### 종단 파이프 (IBL 한 줄로 전체 척추)
- 문서: `[sense:crawl]{url} >> [engines:structure]{instruction} >> [engines:document]{format:pdf}`
- 데이터: `[sense:world_bank]{...} >> [engines:chart]{...}` / `>> [engines:spreadsheet]{path}`
- 교차: 데이터 통화 table이 document의 table 블록으로도 흐름.

---

## 2. 남은 본진 (다음 세션 — 우선순위)

### ✅ newspaper 이관 완료 (2026-06-15) — producer 이관 1호
정찰 결과 producer 이관 표면은 **newspaper 하나**였음(데이터=table 통화·문서=document IR 이미 표준화, 슬라이드/영상/이미지/웹은 정당히 다른 종류). 사용자 결정="새 형식 테스트, 나빠지면 원인 찾아 고친다". 실행:
- **newspaper = 렌더러 → 문서 IR 생산자**로 환생(`web/handler.py generate_newspaper`): 뉴스 수집 → `{title, meta, theme:"newspaper", blocks}` 반환(키워드별 heading + **cards 블록**). ★LLM structure 단계 의도적 배제 — 뉴스는 이미 구조화돼 있어 LLM 끼면 기사누락·링크소실·비결정. 결정적 매핑.
- **문서 IR 강화**: `cards` 블록(링크 카드 그리드 — 뉴스/검색결과/북마크 공용) + `theme`(default/newspaper) + `meta`(부제) + `list` 항목 링크 + heading 앵커. 5 emitter(html/pdf/png/docx/pptx) 전부 cards 처리, docx는 클릭 하이퍼링크(`_add_hyperlink`).
- **앱 배선**: app: 블록 `[engines:newspaper]{} >> [engines:document]{theme:newspaper}` 합성. 렌더러 2곳(GenericInstrument.tsx·api_launcher_web.py) `ibl()`가 합성 응답의 `final_result`(마지막 단계)를 펼쳐 `from:'.'`/`{file}` 해소(모든 합성 앱 액션에 일반 적용). 데스크탑 bespoke `NewspaperInstrument.tsx`도 합성+final_result 파싱으로.
- **검증**: 라이브 합성 파이프 html/png/docx ✓(7기사→docx 7 하이퍼링크), PNG 시각=제호+발행정보+목차(앵커링크)+2단 카드그리드(옛 룩 보존). **회귀 1건(목차 손실) 발견→복구**(list 링크+앵커). 옛 `markdown_to_html`/`generate_section` 마크다운 경로는 dead code(다른 호출처 0 — 안전 후속 정리). 해마 3용례+distilled 419. 액션 127 유지(cards/theme는 document 파라미터).

### ✅ 더 나은 신문 (발견→검증) — "할 수 있다"를 넘어 "실제로 더 낫다" 첫 증명 (2026-06-15)
사용자 반성 압박: "이관이 파리티(옛 룩 보존)지 개선이 아니지 않나? 결과물이 더 나아져야 더 좋은 IBL." 맞음. 그래서 newspaper를 *실제로 더 낫게*:
- **결정적(0토큰) 품질 향상**을 생산자에 박음(`web/handler.py`): ①**중복 제거**(`_dedup_rank` — 근접 제목 묶기, 28수집→7고유) ②**중요도순 정렬**(coverage=같은 사건 보도 매체 수 신호, 많을수록 위) ③**요약 잡음 제거**(`_clean_summary` — 구글뉴스 'title-source' 반복은 버림) ④**제목 꼬리 제거**(' - 출처'는 meta와 중복) ⑤coverage>1이면 "N개 매체 보도" 메타.
- **G로 검증**(발견 단계 G 사용): `[engines:image_critic]{preset:general}`가 렌더된 PNG를 직접 보고 **10/10 통과**("섹션 균형·출처/날짜/링크 명확·가독성 뛰어남, 의도 완벽 충족", issues 0).
- **승격은 자동**: 개선이 생산자 내부 로직이라(파이프라인 모양 변경 아님), 앱의 기존 `newspaper >> document{theme:newspaper}` 워크플로우가 그대로 더 나은 신문을 생산. 별도 저장 불필요.

**★개념 정립(사용자와): 토큰 긴장의 해소.** "생각" 2종 — (A)레시피(어떻게 잘 만드나: 중복제거·균형·레이아웃)=한 번 알아내 **결정화하면 0토큰 영구** / (B)내용(오늘 기사 요약)=새 입력이라 **불가피하게 매 실행**(단 "신문을 다시 생각"이 아니라 "새 뉴스 읽기"). 이번 개선은 전부 (A)라 0토큰. **워크플로우 저장 모델**(사용자): 만족스러운 결과 나오면 그 워크플로우를 동결해 앱이 씀, 사용자가 "개선" 명령할 때까지. = 트릴레마 결정화(자율주행→앱)·하향진화. G는 발견 단계 + 가끔 면역순찰만, steady-state 워크플로우엔 없음. **(B) 옵션(LLM 한 줄 요약)은 미구현 — 넣을지는 저장 시점 1회 선택**(매번 묻지 않음).

### ✅ A-1/A-2/A-3 완료 (2026-06-15) — "A를 순서대로, 4번(재학습)은 제외"
- **A-1 슬라이드 IR 명문화 + emitter 정리**: `slide_shadcn`의 slides[]를 *명시적 슬라이드 IR 계약*으로 문서화(문서 IR과 별개 명시). `format`(png 기본/pdf/pptx) 추가 — `_bundle_slides`(shadcn_slides.py): ★슬라이드 layout=디자인된 HTML이라 pdf=슬라이드당 1페이지·pptx=슬라이드당 풀블리드 이미지로 **렌더 보존**(네이티브 도형 재구성=디자인 파괴 함정 회피). 검증: pdf 2페이지·pptx 2슬라이드(1280×720 정비율).
- **A-2 추가 emitter**: ①문서 IR → **typst PDF**(`_doc_blocks_to_typst`+`format:typst`, 한글=Apple SD Gothic Neo, 책 품질 조판 — 산문/보고서 최적, theme/cards 무시). 시각검증=중앙제목·양끝맞춤·표·인용·페이지번호 ✓. ②**heatmap 통화 매핑**(`_table_to_chart_data`에 heatmap 분기 — 표=행렬). 시각검증 ✓. candlestick OHLCV는 stock 통화 확장 필요한 niche라 보류.
- **A-3 kosis 데이터 통화 생산자**: `_to_table_currency`(tool_kosis_api.py) — KOSIS long-format(기간×분류×값)을 피벗(period=x, 지표·분류조합=시리즈). get_statistics_data·get_indicators 결과에 `table` 부착. 검증: 실 KOSIS(101/DT_1B040A3) 3462행→4년×814열(★다차원=넓은 통화, 차트엔 itm_id/obj_l1로 좁히라 명문화). ⚠️KOSIS search/indicator 엔드포인트는 기존 404(데이터 엔드포인트는 정상).
- 해마 6용례 + distilled 425. 액션 127 유지(전부 파라미터/format 추가).

### ▶ 진행중: 조합 밀도 끌어올리기 — 레코드 통화 (2026-06-15~)
**사용자 비전 정립**: 좋은 IBL = 스위치 더미가 아니라 *조합으로 증식하는 언어*. 측정자 = **조합 밀도**(액션 개수 아님 — 통화를 읽고/쓰는 액션 비율). 1차 감사 결과 *정보* 액션의 ~20%만 통화를 말함(~80% bespoke). 최대 레버 = **검색·목록형 sense를 통화로**.
**설계 원칙(사용자 co-정립)**: *능력은 새 **명사**에서 오고(명사는 N×M을 곱한다), 복잡성 부채는 명사마다 붙는 **필드/옵션**에서 온다(쌓이기만). → 명사엔 관대, 필드엔 인색(기존 필드에 접어 넣기).* 정렬=변환이지 표현 아님(IR 밖).
**레코드 통화(신설 명사)**: `items: [{title, meta?, summary?, url?, image?}]` 최상위 비파괴 필드(kosis `table`처럼). 단일 목록형 액션의 자연 명사.
- **소비**: `document`가 `>>`로 items→cards 블록 / `spreadsheet`가 items→table 투영(★생산자는 items 하나만, 투영은 소비자에서 — 명사 안 늘림). chart는 제외(제목 차트=무의미, "의미 있는 곳에만").
- **IR 개선(능력↑)**: cards 블록에 `image` 추가 → book이 표지 시각 카탈로그(table 불가). 카드=`{title,meta,summary,url,image}` 5필드 동결.
- **변형 비용 3등급**(파일럿으로 확인): ①dict 이미 있음=trivial(book·restaurant) ②우리가 string-format=un-format 리팩터(paper/arxiv: {message,items}) ③raw API JSON passthrough=파싱 필요(legal — 연기).
- **완료(4패키지)**: culture(book — 표지 카탈로그✓), study(paper/arxiv — 나머지 3소스 남음), location(restaurant), web(search_news·search_ddg·search_naver). book>>document(표지)·book>>spreadsheet(11행)·restaurant·paper·news·ddg·naver >> document 전부 라이브✓. 비파괴.
- **★개명**: 통화 필드 `items`→**`records`**(items는 naver·shopping·kosis 등 과적 — 명명헌법). 카드 *블록* 내부 키는 `items` 유지(레이어 분리: 생산자=records 명사 / 렌더=cards.items).
- **★★엔진 버그 발견·수정**: `postprocess:compress`(경량LLM이 결과를 텍스트 다이제스트로 humanize, 에이전트 컨텍스트 절약용)가 **`>>` 중간 단계에도 적용돼 구조화 통화(records/table)를 죽이고 있었음** → search_ddg/news/naver가 통화를 못 흘림. 수정=`workflow_engine` 순차 루프에서 *마지막 아닌 step에 `_raw` 주입*(compress 건너뜀, 구조 보존). 압축은 에이전트가 보는 최종/단일 출력에만(검증: 단일 search_ddg 여전히 압축 텍스트). **8개 compress 액션(search_guardian·search_shopping·travel·devdocs·crawl 포함) 전부 파이프 구조 보존으로 언락** — records 매퍼만 추가하면 흐름. 백엔드 코어 편집=자동 reload.
- **★대량 전환 완료(2026-06-15, 병렬 서브에이전트 5)**: study(paper 전 4소스·search_guardian·search_books·pew_research) · culture(classic·exhibit·performance, book기존) · youtube(search_youtube) · shopping(search_shopping) · real-estate(realty+apt/house변형·commercial) · startup · context7(devdocs resolve) · location(travel·search_local→실은 local-info 패키지). **records 생산 파일 26개.** 키 불필요(classic·pew·youtube)는 라이브 `>> document` ✓, 키 필요분은 직접 import/읽기 검증(매핑 정확). 전부 비파괴(records만 ADD).
- **건너뜀(이유)**: crawl·devdocs:search(비정형 텍스트) · travel:flight(깊은 중첩, name 없음) · legal(raw API JSON passthrough — 파싱 필요).
- **★2차 대량 전환 완료(2026-06-15, 병렬 4)**: 수치형→table(weather 7일 예보·health measurements), self 목록→records(photo[썸네일 image]·blog·memory), others→records(messages inbox/thread·neighbor), legal→records(raw 법제처 JSON 파싱, 10 target law/prec/admrul…, try/except 폴백으로 회귀0). 라이브✓: weather>>chart(기온추이)·neighbor>>document(이웃5)·messages>>document(대화6). legal은 합성검증(라이브는 등록 OC키/IP 필요). **누적: records 생산 34파일 + table 9파일.**
- **★3차 배치 완료(2026-06-15, 병렬3+직접1)**: ①**self:read = IR 입력 측 폐곡선**(xlsx→table·docx→문서IR blocks) — `read(데이터.xlsx)>>chart`·`read(보고서.docx)>>document{pdf}`(포맷변환) 라이브✓. IR이 *내보내기만*에서 *받아들이기*까지 양방향. ②file목록(list/grep/file_find→table). ③feed/board→records(channel_engine). ④company→table(지표·값, investment). ⑤recent_chats→records(sqlite_driver `_memory_recent`) 라이브✓. (fs_query는 pc-manager라 범위밖·후속)
- **비추천만 남김(의도적 스킵)**: stock quote(단일값)·world(이질 스냅샷·내부 self-state). 원칙(명사는 곱하고 필드는 쌓인다)상 통화 부적합.
- **★조합 밀도 본진 완료.** 검색·도서·공연·전시·논문·뉴스·쇼핑·부동산·창업·여행·영상·문서검색·사진·블로그·메모·메시지·이웃·법령·피드/게시판·대화로그 + 날씨·건강·기업 시계열/표 + **read로 기존 오피스 문서 IR 흡수**까지 전부 통화화. 정보 어휘 대부분이 `>> document`(html/pdf/png/docx/typst)·`>> chart`·`>> spreadsheet`로 흐름.

### ★ 다음 producer 후보 (선택) — 설계 판단이 핵심 (기계작업 아님)
engines의 문서류 producer가 저마다 다른 입력을 받는 "스위치 더미" 해소. **단, 종류별 IR 분별이 먼저.**
- **분류 먼저**: 각 producer가 어떤 *아티팩트 종류*인가?
  - 문서류(텍스트 중심) → **문서 IR로 수렴 가능**: `engines:newspaper`(키워드→뉴스→HTML), 보고서류.
    → newspaper를 "수집 → structure(문서 IR) → document(html)" 로 재구성 검토. 단 newspaper는 현재 리치
    신문 레이아웃(다단)이라 문서 IR이 *표현력 손실*일 수 있음 — 신문 전용 레이아웃을 유지할지, 문서 IR+신문 테마로
    갈지 **사용자와 설계 합의 후**.
  - 슬라이드류(시각 레이아웃) → **별도 슬라이드 IR 유지**(slide_shadcn의 slides 스펙이 이미 그 IR). 문서 IR로
    뭉개지 말 것. 여기서 할 일은 슬라이드 IR을 *명시적 계약으로 문서화*하고 emitter(png/pdf/pptx)를 정리하는 것.
  - 웹류(`engines:web`) → 별개(프로젝트 생성). 손대지 말 것.
- **교훈 재확인**: "아티팩트 종류별 IR 1 + emitter 다수." 이관 = 각 종류의 IR을 *식별·명문화*하고 producer를 그
  IR 소비로 정리하는 것이지, 단일 IR 강요가 아니다.

### 2순위: 추가 emitter (additive, 저위험)
- ✅ **docx/pptx 완료(2026-06-15)**: 문서 IR → `_doc_blocks_to_docx`(python-docx)·`_doc_blocks_to_pptx`(python-pptx).
  `render_document` format에 docx/pptx 합류(fail-open=HTML 폴백). 공용 `_resolve_image_bytes`(로컬/data URI/http).
  **★pptx = 문서 IR을 슬라이드로 *투영***(heading L≤2=새 슬라이드, 표·구분선 뒤 첫 heading도 슬라이드 제목, 내용=글머리표) —
  슬라이드 IR이 아니라 문서 IR 정본을 emit. 시각 레이아웃 슬라이드는 engines:slide(슬라이드 IR). 종단 검증:
  전 블록타입 docx(13문단+표)·pptx(6슬라이드), 라이브 `/ibl/execute` docx·pptx, `structure >> document{docx}` 파이프.
  해마 용례 6(docx3/pptx3) + ibl_distilled 410→416. ⚠️ recall은 "워드로"가 기존 `self:read{docx}`와 충돌 —
  재학습 배치(4순위) 몫. **남은**: typst/pdf(출판 스킬 자산 재사용).
- 데이터 통화 추가 소비자: `engines:chart`의 candlestick(stock OHLCV 통화 확장 — 현재 통화는 종가만), heatmap.

### 3순위: 데이터 통화 추가 생산자
- `sense:kosis` — ⚠️ 다차원(기간×분류×값)이라 단순 table 매핑 비자명. `kosis/handler.py` → `kosis_api` 내부
  출력 구조 먼저 확인 후 매핑(잘못 매핑하면 깨짐). 단순 시계열 소스(crypto 등)는 패턴 복붙.

### ✅ 소소 잔여 + 재학습 + 점검 완료 (2026-06-15)
- **소소 잔여**: crawl→문서IR blocks(텍스트 문단화, `_text_to_blocks`)·read(pdf)→blocks(+`read_pdf`가 `path` 별칭 수용 버그수정)·devdocs:search→blocks·fs_query→table·**stock history>>chart{candlestick}**(★table 통화 안 부풀리고 chart가 `_prev_result`서 OHLC 리스트 제네릭 추출 `_extract_ohlc_from_prev` — open/high/low/close 보유 리스트 인식, 필드 무증가). 라이브✓ crawl>>document{pdf}·read(pdf)>>document·candlestick.
- **재학습 배치**: (a)로컬 `rebuild_index` 완료(전 코퍼스 2527건 현재 모델 재색인, 7.1초 — 세션 추가 용례 전부 검색 반영). (b)GPU 모델 재학습=`cloud_training/ibl_train_bundle.zip` 최신 코퍼스(2527)로 번들 준비 완료 — Modal CLI 없음+로컬 OOM 이력이라 Colab 노트북/Modal로 사용자 실행(→apply_model→rebuild_index). docx↔read{docx} 모호성은 이 모델 재학습 몫.
- **점검**: build --check ✓ · 편집 액션 단독 스모크(book·neighbor·recent_chats·weather) 전부 비파괴(원래 키+통화) ✓ · World Pulse self-check 정적정합성 통과 + **실제 에러 0**(실패 52건 전부 self-check의 프로젝트컨텍스트 환경한계, 내 변경 무관). 백엔드 healthy.

### 4순위: 마감/강건성
- 완전 recall: 임베딩 재학습 배치(`cloud_training/`, "마지막의 마지막"). 이번에 추가한 용례들(sense:host 17 +
  structure/document 11)이 거기 흡수되면 모호 표현 충돌 해소.
- structure 모델 티어: 현재 경량(gemini flash-lite). 문서 품질 민감하면 midtier로 올리는 튜닝 knob.
- document에 G 연결: document{format:png} → image_critic(preset:general)로 자가 비평 루프(옵션).

---

## 3. 운영 노트 (함정 — 다음 세션 필독)
- **패키지 handler.py 편집 → `POST /packages/reload` 필요.** slide_image.py 등 동적 로드 모듈은 불필요(매 호출 fresh).
  **백엔드 코어 모듈**(agent_cognitive.py·consciousness_agent.py) 편집은 백엔드 자동 reload/재시작에 의존.
- **src yaml 편집 → `python3 scripts/build_ibl_nodes.py` 후 `--check`** (삼각 정합성 src↔tool.json↔handler).
  새 op 액션은 handler `_OP_DISPATCHERS` 키까지 AST 일치해야 통과.
- **`/ibl/execute` 테스트엔 `project_id` 필수**(thread context 없을 때). 합성 `>>`는 **각 leaf마다** project_id 필요.
  액션이 연속 3회 실패하면 **서킷브레이커**가 ~수십초 차단(테스트 실패가 누적되니 주의 — 직접 핸들러 호출로 우회 검증 가능).
- **해마 용례 추가**: `IBLUsageDB().add_examples_batch([{intent,ibl_code,nodes,category,source}])` (자동 색인,
  full rebuild 불필요) + `data/training/ibl_distilled.json`에도 append. composite는 category='composite'.
- **system_ai_config apiKey = Gemini 키(AIza)** (provider 라벨은 claude_code) — 미디어 생성/critique이 이 키 사용.
- 새 액션 체크리스트: src yaml + handler + tool.json + build --check + 해마 용례 + (선택 app: 블록). 이번 3개 액션
  (sense:host·structure·document) 다 거침.

---

## 4. 한 줄 요약
척추의 **새 골격**(B 구조화·C 문서IR+3emitter·데이터통화 양끝+파이프·G 비평·sense:host)을 세우고 종단 검증했다.
남은 건 **기존 producer 이관**인데, 이는 단일 IR 강요가 아니라 *아티팩트 종류별 IR을 식별·명문화*하는 설계 판단이라
신선한 세션 + 사용자 합의가 낫다. 그 외는 additive(docx/pptx emitter, kosis 생산자, 재학습 배치).
