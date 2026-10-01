# 상상훈련 76~81회차 회귀 재검 결과 (2026-09-29 22:1x~22:3x, 읽기 전용)

- 백엔드: /health healthy, restart_control phase ACTIVE. 재기동·표식 조작 없음.
- 모든 실행: `#!ibl edition=2`, edition 2, `project_id:"컨텐츠"`, `origin:"training"`, agent_id/task_id `REGRESS_7681`.
  (판본 1 대조 1건만 edition 생략.) 요청/러너: `scratchpad/regress/tmp/r7681/`.
- 부수 효과 확인: 새 기억 DB(`memory_REGRESS_7681.db`) 생성 없음, `data/portal_state.json` mtime 불변,
  action_health·trajectory_event 의 이번 행은 전부 `source=training`(궤적 200행).
  TTS 1건은 산출 경로를 scratchpad(`tmp/r7681/narr/r81.mp3`)로 지정해 그곳에만 생성됨.
- 단위: 갭(원장 항목) 기준. 한 갭에 여러 문장을 돌린 경우 가장 강한 판정으로 센다.

## 1. 회차별 요약

| 회차 | 재검 갭 | 정상 | 문법변화(정상) | 여전히 오류 | 검수만/못 함 |
|---|---|---|---|---|---|
| 76 (외부 조회: 부동산·투자) | 11 | 10 | 0 | 1 (B76-4 잔여) | 0 (V76-1 후보 제외) |
| 77 (강의·연구 자료) | 8 | 5 | 2 (book `limit`→`rows`, structure `text/intent`→`content/instruction`) | 2 (B77-1 새 형태, F77-1 nl 연도 칸) | 1 (F77-2 429는 재현 불가) |
| 78 (기억·건강·포식) | 13 | 11 | 0 | 0 | 2 (F78-4 지표 스크립트, F78-5 ledger 쓰기) |
| 79 (공연·전시·중고·맛집·숙박) | 12 | 11 | 0 | 1 (B79-2 check 단계 미검출, 경미) | 0 (V79-1 후보 제외) |
| 80 (소통·공개면) | 13 | 13 | 0 | 0 | 발신 계열은 check만 (V80-1 후보 제외) |
| 81 (미디어·사진·음악·강의) | 11 | 10 | 0 | 1 (B81-3 잔여) | 2 (B73-4 렌더 산출, B81-2 폰 경로) |

## 2. 여전히 오류

### R76-B4 — 76회차 B76-4 `stock history` 기본값(max_points 생략)이 판본 2에서 실패, 교재 예문이 죽음
- 원래 증상: 전량/기본 요청이 거짓 절단 표지로 `PARTIAL_SOURCE` 실패. 표본을 요청해야 성공.
- 현재: 전량 요청(`max_points:1500`)은 수리됨(`{n:1223,t:1223,tr:false}`), `max_points:100` 은 selection 성공.
  그러나 **max_points 생략 + 10행 초과 기간**은 여전히 실패한다. 교재 `data/guides/investment.md` 33행 예문이 그대로 실패.
  같은 액션을 `start_date`·`period` 없이 부르면 20행 success라 기본값 동작도 들쭉날쭉하다.
```
$h = [sense:stock]{op: "history", ticker: "AAPL", start_date: "2026-01-01"}
return {n:len($h.items), t:get($h,"total",null), trs:get($h,"truncations",null)}
```
(동일: `ticker:"005930", start_date:"2026-01-01"`, `ticker:"005930", period:"5y"`)
- validate: 통과(check incomplete 급). execute: `PARTIAL_SOURCE` "도구의 원천 결과가 불완전합니다. 절단 사유 `max_points`(상한 10). `max_points` 를 명시하면 그만큼의 선택으로 받고, 전부가 필요하면 값을 올리세요." (partial total_days 185/181/1223)
- 분류: 원 결함 재현(부분) — 수리 때 안내 문구만 붙고, 기본값 10의 다운샘플을 원천 절단(source scope)으로 올리는 뿌리는 남음. 교재 예문(`investment.md` 33행) 드리프트도 함께.
- 비고: 보고서 원문 "생략 → PARTIAL_SOURCE(1223일 → 12점)"과 같은 모양. 2차 수리 절은 전량 요청과 `total` 상시 게재만 적었다.

### R77-B1n — 77회차 B77-1 수리의 새 형태: arXiv `sort_by:"recent"` 가 여러 낱말 질의에서 관련 없는 논문을 준다
- 원래 증상: arXiv가 sort_by·연도를 조용히 무시.
- 현재: 최신순·연도는 구현됨. 그러나 `search_query = "all:{query}"` 에 낱말을 이어 붙이기만 해서, 관련도순일 때는 가려지던 OR 성격 매칭이 최신순에서는 그대로 드러난다(study/handler.py 63행).
```
$p = [sense:paper]{query:"LLM reasoning limitations", source:"arxiv", sort_by:"recent", limit:8}
return $p.items >> [table:select]{columns:["title"]}
```
- validate 통과, execute success. 결과 8편 중 LLM 관련 2~3편. 나머지 예: "From Density to Mass: … Dark Matter Environment Around Black Holes", "Retrieving Biblical Intertextual References in Karen Blixen's…", "Can Fingers of God be Resummed?".
  같은 질의를 관련도순(`year_from:2026`만)으로 하면 5편 모두 LLM 추론 논문.
- 분류: 새 형태의 오류(침묵 오답 — 성공으로 보임). 77회차 T02 문장(`sort_by:"recent", year_from:2026`)도 같은 결과(Dark Matter 논문이 1위).
- 비고: 2차 수리 라이브 기록은 "T02 문장이 2026-09-28 제출 5편(최신순)"만 확인했고 주제 관련성은 보지 않았다.

### R77-F1 — 77회차 F77-1 병기 칸의 값이 규약 밖: 도서 nl `publication_year` 가 연도가 아닌 날짜 문자열
```
$b = [sense:book]{source:"nl", query:"하네스", rows:2}
return $b.items >> [table:select]{columns:["title","authors","publisher","publication_year"]}
```
- execute success: 1행 `publication_year:"2012"`, 2행 `publication_year:"20120208"`, `publisher:"서울 : 하다, 20120208"`(발행지·연월일이 출판사 칸에 섞임).
- 분류: 새 형태의 오류(경미) — 구조 칸은 생겼지만 같은 원천 안에서도 형식이 갈려 연도순 정렬·연도 필터가 틀린다. 형제 원천(정보나루) `publication_year` 형식과도 대조 필요.

### R79-B2c — 79회차 B79-2 원천 값 영역: 실행은 정직 거절이지만 check 는 여전히 못 본다 (경미)
```
return [sense:performance]{date_from:"2026-10-03", date_to:"2026-10-04", region:"청주"}
```
- check: `incomplete`, 이슈·경고 0. execute: `TOOL` "알 수 없는 지역: 청주. 허용 지역: 서울, … 제주 … 시·군·구 이름(예 수원·전주)은 KOPIS 지역 코드가 아닙니다 …"(`details.error_type:"invalid_value"`).
  `genre:"어린이극"` 도 check 통과, 실행에서 거절. 형제: `[sense:used]{source:"danggeun", query:"자전거"}`(region 없음)도 check 통과, 실행에서 `missing_param` 거절.
- 분류: 새 형태의 오류(경미) — 원 결함(침묵 0건 성공)은 닫힘. 81 잔여 수리의 "도구 스키마 enum 을 판본 2 계약에 전달"(tts engine·photo kind 는 check 에서 `ARGUMENT_CONTRACT`)이 코드표 값(지역·장르)·조건부 필수(당근 region)에는 닿지 않아, check 가 사전 판정하지 못하고 실패 코드도 `ARGUMENT_CONTRACT` 가 아닌 `TOOL`.

### R81-B3 — 81회차 B81-3 `self:photo` 의 '사진'이 여전히 워크스페이스 이미지 자산을 포함
```
[try] { $p = [self:photo]{kind:"photo", limit:100}; $r = $p.items } [catch] { $r = $error.partial.items }
$ws = $r >> [table:filter]{where:($x)=> contains($x.path, "/Desktop/AI/")}
return $ws >> [table:select]{columns:["path","origin","camera"]}
```
- execute: 기본 호출 자체는 `PARTIAL_SOURCE`(candidate_limit — 수리 문서가 정직한 원천 상한으로 명시). partial 100행 중 indiebizOS 경로 10행, `/Desktop/AI/` 전체 20행 이상:
  `indiebizOS/backend/assets/{finder,launcher}/icon-*.png`, `indiebizOS/projects/study/images/msg_*.png`, `HomePages/*/public/*.jpg|webp`, `HomePages/…/scripts/_backup/*.png` — 모두 `origin:"unknown"`, camera 빈칸.
- 분류: 원 결함 재현(부분) — 제외 목록이 `outputs/`·`data/`·`projects/*/outputs/` 뿐이라 코드 자산·프로젝트 이미지·홈페이지 소스가 기본 '사진' 최신 목록을 채운다.
- 비고: 81 잔여 수리 문서가 "홈의 모든 그림을 촬영 사진으로 분류하는 기능은 아니다"로 한계를 명시한 항목. 기본 사진 질의가 항상 PARTIAL_SOURCE 실패인 점(76~81 B78-1 속)도 수리 문서상 의도된 정직 실패지만, 결과적으로 `[self:photo]{}` 기본형은 판본 2에서 계속 실패한다.

## 3. 문법 변화로 정상 처리된 항목

- `[sense:book]{source:"nl", query:…, limit:2}` → `rows:2` (UNKNOWN_ARGUMENT limit; 사용 가능 인자에 rows) — 이후 정상.
- `[table:structure]{text:…, intent:…}` → `{content:…, instruction:…}` — F77-3 제목 원문 보존 정상("incentivizes" 유지).
- (훈련자 표현 오류 교정, 문법 변화 아님) `get($list, 0, null)` → `$list[0]`, `$i` 바인딩(읽기 전용) → 다른 이름, 판본 1 문장 앞 `return` 제거.

## 4. 정상 확인 (요지)

- 76: B76-1 info KR/US success(numpy 해소) · B76-2 JSON 봉투/맨 배열/객체 구조 보존 · B76-3 `deal:"lease"` 는 전세 30/30으로 흡수(`deal_type` 칸) · B76-5 BTC 행 `currency:"KRW"` · F76-1 molit 전월세 `deposit_won/rent_won/deal_type/area_m2`, 연립 월세·단독 매매 `price` 병기, naver `area_m2/floor/deal_type` · F76-2 molit rent·kosis info 거짓 경고 0 · F76-3 교재 문구 교정·`district_codes` 은퇴 등록 · F76-4 LITERAL_DOLLAR 경고 · B75-4 미지 op check `ARGUMENT_CONTRACT` · F72-2 `count`→len 제안, `$x.9월`→get 안내.
- 77: B77-1 arXiv 인용순·nanet open_access·미지 source check 거절, PubMed/nanet 연도 범위 · B77-2 quote 가 인용 문장 포함 청크 · B77-3 Context7 title/id · B77-4 nanet 0건/40건/학위논문 0건 정직 성공 · F77-1 논문 authors/year/journal/citations/doi/arxiv_id, lecture_id/slide_count, notebook status/stale · G77-1 `contains(…, true)`.
- 78: B78-1 recent_chats success·selection 표지 · B78-2 새 agent 기억 DB 미생성, 오타 person 조회 persons 불변(코드 경로 `create=False`) · B78-3 "AI 블로그" 5건 · B78-4 없는 노트북 `locus_exists:false` · B78-5 `book:하네스: …`·`book:하네스` locus map_count 1·2 · B78-6 `R&D 전략`·`<하네스>` 각 3건 · B78-7 궤적 source=training · B78-8 빈 query 실패가 action_health success=0 · F78-1 오타 폴더 `locus_exists:false, own_count:0, doc_is_ancestor:true` · F78-2 recent_chats `days/query`·publish `dry_run`·feed `preview` check 거절 · F78-3 health 평탄 키 통과, forage `layer` 거절.
- 79: B79-1 주말 기본 9건(공연예정 5 포함) · B79-2 실행 거절 문구·hint · B79-3 당근 로더 복구 + 0건 `empty_notes` 정직 · B79-4 번개장터 `scanned 200·unlocated 129·scan_limit` 정직 실패 · B79-5 네이버 전국 행 0, distance 정수, blog_count null 허용 · B79-6 1박 평균 필터·nights/price_total/price_per_night, 필터 0건 source 절단 없음 · B79-7 전시 lat/lng float · B79-8 판본 1 `descending:true` 내림차순, 판본 2 `desc` 별칭 · F79-1 title_key/place_key · F79-2 공모전 hint · F79-3 `round(x,0)`·`3/3` 인덱스, INDEX details(index/length/variable) · 날씨 `days:20` → 16일 + clamped/requested/applied.
- 80: B80-1 이웃 list/detail 인증 칸 0(값은 불러오지 않고 has() 만) · B80-2 `unreplied`·`created_at` · B80-3 최신순 + created_at · B80-4 `source:local_snapshot, as_of:null, stale:true` · F80-1 `state` 병기, nullable not 조건은 row_index 포함 BOOL_REQUIRED · F80-2 절대 URL·post_id · F80-3 detail items=글·board 칸 · B75-4 feed read/board delete effects read/write 구분 · delegate `mode:"sinc"`·`agent/msg` 오타 check 거절 · B72-2 inbox search check 통과 · portal 읽기 mtime 불변·없는 포털 정직 오류 · 블로그 없는 폴더 정직 거절.
- 81: B81-1 TTS 판본 2 success + `path`·duration, 명시 폴더 보존(B81-4) · B81-2 `taken_at` +09:00·현지 month·origin · B81-4 render `~workspace`/상대 경로가 프로젝트 outputs 로 해소 · B81-5 critic `passed/score/tier` 최상위 · F81-1 lecture list lecture_id, load 관측 경고 0 · F81-2 blog 설명의 새 관용구(`$b.path` → self:read) 실행 성공, render→each critic check 통과 · F81-3 year 정수/null + year_raw · F81-4 즐겨찾기 station_id/broadcaster, korean 목록 stream_url 4/12 · photo kind "사진"·tts engine 오타 check 거절 · photo lat/lng 관측 경고 0 · `engines:web_site` list items.

## 5. 재검 못 한 항목과 이유

- F77-2 (429 → RATE_LIMITED): 원천 한도를 일부러 유발할 수 없어 재현 불가.
- F78-4 (조합 지표 도달 가능 셈): 지표 스크립트 실행은 범위 밖(코드/문서상 self_can_run 적용 기록만 확인).
- F78-5 (ledger 쓰기가 쓰기 원장에): 쓰기 op — 부작용.
- B73-4 재확인(렌더 깨진 로컬 이미지 prescreen), B81-5 비전 경로: 렌더 산출 파일 생성·유료 비전 호출이 필요해 생략(critic 은 prescreen 경로만 확인).
- B81-2 폰 `_mediastore_query` 경로: 폰 몸 필요.
- 발신·쓰기 계열(publish·feed post·delegate·board delete·health save)은 check 만.
- V76-1·V79-1·V80-1·V81-1: 어휘 후보(결함 아님) — 대상 외.

## 6. 참고 관찰 (수집 대상 아님)

- F78-1/B78-4: 없는 장소에서 `locus_exists:false` 인데 `root_missing:false` 로 남는다. 두 칸의 의미 차이(문서 뿌리 vs 장소)가 봉투만으로는 모호 — 교재 확인 권장.
- F80-1: `alive` nullable 로 `not $r.alive` 가 check 는 통과하고 실행에서 BOOL_REQUIRED(row_index 17). 교재에 `alive == false` 가 명시돼 설계대로.
- 78회차 판정 요청 1(고아·갈린 포식 기억 처분)·80회차 판정 요청(옛 영수증)은 사용자 판정 대기 그대로 — 회상은 두 book 몸을 여전히 따로 보여준다(`book:하네스: AI 시대의 새로운 몸` / `book:하네스`).
