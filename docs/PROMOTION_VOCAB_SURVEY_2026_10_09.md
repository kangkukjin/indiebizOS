# 홍보 주제 긴문장 훈련 사전 조사 — 어휘·도구 보유/공백 (2026-10-09)

> 목적: 다음 긴문장 상상훈련을 "홍보" 주제로 하기 전에, 시스템이 홍보 일에 필요한 어휘·도구를
> 가졌는지와, 없는 것 중 쓸모 있을 것을 가린다. 조사만 — 코드·어휘·설정 변경 없음.
> 주의: 42회차는 이미 "동영상 제작(4장면 홍보영상)"으로 끝났다(`0136fffb`). 홍보 회차는 **43**이다.

## 0. 결론 요지

- **만들기(조사→브리프→소재)는 어휘가 거의 다 있다.** 검색(네이버 blog/cafe/kin/news·gnews·ddg)·크롤·이미지 생성·슬라이드·영상·문서 렌더·산문 종합·자기 산출물 지각까지 한 바퀴가 IBL 로 닫힌다.
- **내보내기(유통)는 내 공개면·IndieNet 안으로만 닫힌다.** Nostr 장문/피드, 쇼케이스(Cloudflare)/포털/게시판/공유창고, 이메일(주소록 수신자), Vercel 배포. 외부 SNS·블로그 플랫폼(인스타·X·스레드·틱톡·네이버 블로그·티스토리·유튜브 업로드·카카오채널) 발행 어휘는 **0** — 유일 경로는 `[limbs:browser]` 조작.
- **재기(성과 측정)는 사실상 없다.** 공개면 방문·조회 집계 없음, 플랫폼 애널리틱스 어휘 없음. `marketing.md` 가 말하는 "앵글 넓게→반응으로 좁히기" 의 반쪽(반응)을 시스템이 못 본다.
- **해마 용례에 홍보가 0건**(1,203건 중 홍보·마케팅·카피·소재·카드뉴스 각 0). 가이드 `marketing.md` 는 있고 라우팅 키워드도 등록돼 있으나, 시스템 AI 가 회상할 홍보 문장이 없다.
- 공백 중 쓸모 순위(아래 §3): ① 성과 측정 ② 검색어·트렌드 근거 ③ 캠페인 원장(조합으로 해결) ④ 카드뉴스/세로 규격(조합으로 해결) ⑤ 외부 SNS 발행(어휘 신설 반대).

## 1. 조사 방법

- 어휘 전수: `data/ibl_nodes.yaml`(sense 43·self 59·limbs 14·others 20·engines 19·table 23 = 178 액션)의 설명·op 값·파라미터.
- 패키지 47(보유)+4(잠듦: nodejs·publishing(책 출판)·python-exec·remotion-video).
- 가이드 92편 중 `marketing.md`·`web_builder.md`·`blog.md`·`business.md`·`delegation_system_ai.md`, 관용구 `data/idioms/curated.json` 19개, 해마 색인 `ibl_hippo_index.json` 1,203건 키워드 집계.
- 런처 '홍보' 프로젝트(에이전트 2: 스토리텔러·홈페이지, 트리거 2: `AI시대_보고서출처_뉴스갱신`·`forage_resurvey_홍보`)와 42회차 기록.

## 2. 홍보 일의 단계별 보유 어휘

| 단계 | 보유 어휘 | 비고 |
|---|---|---|
| ① 조사(3C) | `[sense:search]{source:"naver", type: webkr/news/blog/cafe/kin/encyc, days, queries 배치}` · gnews/ddg/hn · `[sense:crawl]`(content/links/metadata, include_images) · `[sense:feed]`(경쟁사 RSS) · `[sense:search_youtube]`·`[sense:video]{op:channel/transcript}` · `[sense:commercial]`(상권 점포)·`[sense:place]`·`[sense:restaurant]`(블로그 후기 수) · `[sense:kosis]`·`[sense:world_bank]` · `[table:since]`(새 언급 감시) | 고객 목소리(후기·카페·지식인)와 경쟁사 메시지 수집은 충분. **검색량·트렌드 근거 없음**(§3-②) |
| ② 브리프·카피 | `[table:brief]`(산문 종합) · `[table:ai]`(의미 변환) · `[table:judge]` · `[self:ask]`(경량 모델 원샷) · `[self:struct]`(비정형→schema) · 자사 원천 `[self:business]{store: business/item/document}` · 내 글 `[self:blog]{op:search}` · `[self:notebook]`(근거 고정) | 브리프 양식은 `marketing.md` §1 표. 저장은 `[self:write]`/`[self:ledger]` |
| ③ 소재 제작 | `[engines:image_gemini]`(aspect_ratio 1:1 기본·9:16 가능, image_size, style_preset, input_image 편집) · `[self:slide]`(aesthetic 4종, overlay_text 결정론 글자, note=나레이션) · `[self:deck]{op:export pdf/pptx/images, op:video captions}`(1280×720 기본) · `[engines:tts]` · `[table:document]`(html/pdf/png/docx/pptx) · `[engines:web]{op:create template:"landing", features:["seo"]}`·`{op:check}` Lighthouse SEO · `[engines:render]`·`[engines:image_read]{critic}`(자기 검수) · `[engines:newspaper]` · (잠듦)`[engines:remotion]` | 42회차가 영상 경로를 이미 실증(`슬라이드틀적용` 재사용). **슬라이드 캔버스는 16:9 고정**(§3-④) |
| ④ 발행·유통 | `[others:publish]`(Nostr NIP-23 장문, slug 재발행) · `[others:feed]{op:post, hashtag}` · `[self:business]{store:document, op:publish}`(공개 프로필 Nostr) · `[others:showcase]`(폴더→바스켓 /s/ 공개, Cloudflare) · `[others:portal]`(/h/, 레벨별 진열) · `[others:bulletin]`(/b/ 익명 게시판) · `[self:warehouse]`(레벨 0~4) · `[others:channel_send]{channel_type: email/nostr}`(수신자 1명·주소록 해소만) · `[engines:web]{op:deploy}`(Vercel) · `[limbs:cloudflare_api]` · `[limbs:browser]`·`[limbs:os_open]` · `[self:webapp]{op:list/status}` | 전부 "내 공개면 + IndieNet + 이메일". **외부 플랫폼 발행 0**(§3-⑤). 집단 발송은 `[table:each]`×이웃 명부로 조합 가능 |
| ⑤ 측정·반복 | `[self:webapp]{op:status}`(생존만) · `[others:portal]{op:audit}`(누가·언제·무엇) · `[sense:video]{op:channel}`(내 채널 공개 지표) · `[self:blog]{op:stats}`(글 수 분포) · `[table:since]` · `[self:trigger]`/`[self:schedule]`/`[self:workflow]`(정기) · `[self:ledger]`(JSON 원장) · `[others:delegate]` | **도달·조회·전환 집계 없음**(§3-①). 게시판·쇼케이스엔 audit 도 없음 |

가이드 `marketing.md` §5 실행 경로 표의 어휘는 전부 실재하며 이름도 맞다. 다만 표에 ①의 검색어 근거와 ⑤의 측정 행이 없다.

## 3. 없는 것과 쓸모 판단

### ① 성과 측정(도달·조회·방문) — 쓸모 **높음**, 가장 큰 공백
- 상태: 공개면(쇼케이스·게시판·포털·공유창고)에 방문·조회 집계 어휘 없음(포털만 audit). Cloudflare Web Analytics·YouTube Analytics·네이버 애널리틱스·Search Console 어휘 0. `self:webapp status` 는 살아 있는지만 본다.
- 왜 중요: `marketing.md` 의 핵심 절차(앵글 넓게 → 반응 오는 앵글로 좁히기, 성과 리포트 = 팩트→KPI 대비→소재별→제안)가 반응 입력 없이는 성립하지 않는다. "홍보능력 = 품질 × 유통 × 꾸준함" 에서 유통의 피드백 고리가 끊겨 있다.
- 기본 답(반-어휘-증식): Cloudflare GraphQL Analytics 는 `[limbs:cloudflare_api]` 로 이미 호출 가능 → `[self:script]` 로 얼린다. 공개면 서빙 층의 접근 로그 집계는 몸의 명사(코드)이지만 **op 신설도 어휘 증식**이므로 훈련 뒤 실측으로 필요가 입증될 때 판정 요청.
- 훈련에서의 처리: 반응 데이터는 **합성 CSV**(소재별 노출·클릭·문의)로 주입해 "좁히기" 논리를 시험한다.

### ② 검색어·트렌드 근거 — 쓸모 **중상**
- 상태: 네이버 데이터랩·구글 트렌드·연관검색어·자동완성 소스 0. 브리프 항목 "고객이 검색하는 말" 의 반증 가능한 근거가 없다.
- 대체: `[sense:search]{source:"naver", type:"blog"|"cafe"|"kin", queries:[...]}` 의 `sections` 건수 비교로 간접 추정(세계의 명사=데이터 원칙에 맞음).
- 후보: 데이터랩 검색어 트렌드 API 는 `sense:search` 의 `source` 값 추가(데이터 축 확장) 로 들어갈 수 있다 — 새 낱말 아님. 사용자 판정 사항.

### ③ 캠페인·소재 원장 — 쓸모 **중상**, 새 낱말 0 으로 해결
- 상태: 소재·앵글·채널·발행일·반응을 한 줄로 묶는 원장 없음.
- 답: `[self:ledger]` + 관용구 `원장에누적`·`미처리만고르기` 조합. 훈련 축으로 적합(40회차 "원장" 계열 재사용).

### ④ 소재 규격(카드뉴스 1:1·쇼츠 9:16) — 쓸모 **중**, 조합으로 해결
- 상태: `self:slide` 캔버스 16:9 고정(pptx 12192000 EMU), deck video 1280×720 기본(width/height 내부 옵션은 어휘 노출 미확인).
- 답: `[engines:image_gemini]{aspect_ratio:"1:1"|"9:16"}` + `[table:document]{format:"png"}`(HTML 카드) 로 카드뉴스 가능. 세로 영상은 42회차 영상 경로에 width/height 노출 여부 확인이 선행.

### ⑤ 외부 SNS·블로그 플랫폼 발행 — 쓸모는 높으나 **어휘 신설 반대**
- 상태: 0. 유일 경로 `[limbs:browser]`(DOM ref 조작).
- 이유: 공개 발행물은 사용자가 직접 쓴 것(피드백 정본), 플랫폼 토큰·약관 의존, 세계의 명사. 가이드 §핵심규칙 2 도 "AI 는 초안까지" 로 못박는다.
- 훈련 경계: "발행 직전 묶음(초안·미리보기·대기)" 까지가 시스템의 일. 외부 발행은 사용자 손.

### ⑥ 기타(쓸모 낮음·미확인)
- 집단 발송(뉴스레터): `channel_send` 수신자 1명 → `[table:each]` 로 가능. 발송 전 사람 승인 설계 유지.
- UTM·단축 URL·QR: 어휘 없음. 문자열 함수·`table:compute` 로 UTM 은 조합 가능.
- 보도자료·소개문 양식: `[self:fill]`(DOCX 템플릿) 로 가능.
- 런처 '홍보' 프로젝트의 매시 트리거 실패(75회차 273통)는 현 상태 미확인(`/triggers` 응답 빈값) — 훈련은 상상행동 격리 원칙대로 **가상 사업체 합성** 으로 간다.

### ⑦ 해마·가이드
- 해마 용례 1,203건 중 홍보·마케팅·카피·소재·카드뉴스·SNS·보도자료·뉴스레터 **0**, 블로그 38·포털 12·신문 8·발행 7·게시판 5·쇼케이스 5·publish 3·image_gemini 1·slide/deck 0. 시스템 AI 독립 실행은 가이드 라우팅(`marketing` 키워드 14개 등록)에만 기댄다.
- 훈련의 자연스런 산출 = 홍보 용례 시딩(`add_examples_batch` 단일 경로, `_load_model_sync` 선행).

## 4. 43회차 과제 설계 재료(제안, 사용자 결정)

- 주 과제: 가상 동네 사업체(42회차 '수리교실' 자료 재사용 가능)의 **홍보 한 바퀴** — 3C 조사(네이버 blog/cafe/kin 배치 + 경쟁사 2곳 crawl) → 브리프(`table:brief`·`self:struct`, 파일 저장) → 앵글 3 × 소재(이미지 1:1·카드뉴스 png·30초 영상 재사용) → 발행 직전 묶음(쇼케이스 바스켓 또는 게시판 + NIP-23 초안) → 캠페인 원장(`self:ledger`).
- 변형: 합성 반응 CSV 투입 → 소재별 성과 표 → 앵글 좁히기 제안(팩트/제안 분리) → `table:since` 로 새 후기 감시 등록. 두 번째 변형: 경쟁사 메시지와 동일 소구 감지(판정 `table:judge`).
- 독립 AI 실행: 같은 자연어로 시스템 AI 에 맡겨 가이드 라우팅·해마 0건 상태의 수행을 대조(§4-5).
- 측정 공백(§3-①)은 과제 안에서 "측정 불가를 정직하게 보고" 하는 조건으로 둔다.
