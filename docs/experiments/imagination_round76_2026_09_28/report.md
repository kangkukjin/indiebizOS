# 상상 훈련 76회차 결과보고서 (2026-09-28) — 외부 조회 조합: 부동산·투자

훈련 턴 · **무수정**(가이드 §4-3: 훈련 턴은 라이브 코어를 고치지 않는다). 아래 갭 원장은 [before.json](before.json)·[baseline.json](baseline.json)과, 셸로 직접 읽은 패키지 코드만으로 썼다. 집행 완료 절은 비워 두었다.

## 축 선정

- 축 = 행동 기준 미조합 메뉴의 **외부 조회 어휘**다.
  - 조회: `sense:realty`·`stock`·`crypto`·`company`·`kosis`·`world_bank`·`weather`·`commercial`·`legal`·`http`
  - 결합: `table:join`·`merge`·`union`·`rename`·`compute`·`groupby`·`judge`
  - 도메인(부동산·투자 프로젝트):
    - 청주 흥덕구(오송, 43113) 아파트 실거래·전세가율·단지별 전월 대비, 호가 vs 실거래, 빌라 전세
    - 관심 종목 수익률, DART EPS와 PER, 환율·금·코인
    - KOSIS 인구, 세계은행 GDP, 날씨 조건, 상권, 법령·판례, 등기
    - 외부 조회 실패 폴백·부분 실패·빈 달
- 축 선정 관문 질문("기계로 열거 가능한가"): 외부 원천의 모양(단위·필드·절단)이 조합에서 어떻게 부딪히는지는 원천을 실제로 불러야 드러난다. 그래서 훈련 축이다. 다만 발견 가운데 하나가 앞 회차와 같은 속이다.
  - numpy 스칼라 경계: B67-3 → B76-1
  - census로 넘기라고 적었다.
- 닫힌 밭은 밟지 않았다.
  - 값 표기: `270000.0원`은 산출물 품질로만 봤다(T09, `round`로 해결).
  - 절단 표지: 표지 **누락**은 B72-3 재확인으로만 적었다. B76-4는 표지가 있으나 **거짓**인 새 형태다.
- 탐침 표면: 모델 경로(`agent_id:"IT76_probe"`·`task_id:"IT76_task"`). 모든 요청이 `edition:2`·`project_id:"컨텐츠"`·`origin:"training"`이다.
- 외부 API는 읽기 조회만 했다. 과제마다 한 프로그램 안에서 변수로 재사용했고, 고친 문장 재실행 5건은 `reuse:{run_id}`로 읽기 영수증을 다시 썼다. 유료 `table:judge`는 1회(5행)만 불렀다. 발신은 0이다.
- 숫자는 원천끼리 대조했다.
  - 삼성전자 quote 270,000원 = 판본 1 info 270,000원
  - BTC 원화 113,457,457 ≈ 83,475 USD × 1,358.9(차 0.02%)
  - KOSIS 8월 매매 275건 + 9월 181건 = T01 두 달 456건
  - PER 270,000 ÷ EPS 6,605 = 40.9

## 지표 스냅샷 (훈련 전)

행동 미조합 140/168 · 파이프 길이 중앙값 3 · 문형 4(조회 26·축적 8·적용 6·조건 2) · 파트너 다양성 중앙값 2. 75회차와 같다. 원본은 [metrics.json](metrics.json)이다. 지표는 몸의 현황이며, 훈련 실측은 증류에 담기지 않는다(§6).

## 과제 표

원문·판정식: [probe.py](probe.py) · 응답 전량: [before.json](before.json)(요청·응답 32건, 탐색 raw 약 14건은 별도) · 기준선과 회차 후 diff: [baseline.json](baseline.json).

**24과제 중 기계 판정 21통과 · 3실패.** 판독으로 T11·T15에 결함 경로를 추가했다(과제는 우회로 달성). 결함 5부류 · 마찰 4부류 · 어휘 후보 1.

탐색 중 훈련자 문장 잘못은 결함 판정에서 뺐다. 거절 안내가 모두 방향을 정확히 줬다.
- 최상위 `$i`(예약 바인딩)
- 내장 함수 인자 안 파이프 `len($x >> filter)`(T03·T07·T09·T21, PURE_EXPRESSION)
- 숫자로 시작하는 필드 `$x.9월`(T04)
- `㎡`가 든 키(T08)
- 조인에 파이프+`right`(T06, 설명문대로 `left`/`right`로)
- 람다·객체 안 `[if]`(T12·T21)
- 전세가율의 단일 키 조인(T03 첫 시도)

| # | 상상 의도 | 결과 | 분류 |
| --- | --- | --- | --- |
| T01 | 오송(흥덕구) 아파트 두 달 매매 → 단지별 평균·건수 → 3건 이상 비싼 순 5 | 456행 · `truncated:false` · 110단지 · 1위 신영지웰시티1차 평균 12.0억(6건) | 깨끗 |
| T02 | 전월세 중 전세만 단지별 평균 보증금 | 606행 → 전세 282 → 86단지. `계약유형` 필드에 거짓 경고 | 깨끗(F76-2) |
| T03 | 단지별 전세가율(국평 59~85㎡) 높은 순 | 첫 시도(키 `아파트명`) **'효성' 328.6%** → 복합 키(`아파트명`+`법정동`)+평형 띠로 51단지·80% 이상 19. 1위 효성아파트(비하동) 101.8%. 단위(원 vs 만원 문자열)는 손으로 맞춤 | 꼬임(F76-1·F76-3) |
| T04 | 단지별 8월 대비 9월 변화율 | 58단지 · 상승 28 · 1위 형석(992) +61.1%(소표본) | 깨끗 |
| T05 | 거래 없는 달(2026-12)·없는 단지 | `n 0 · total 0 · truncated false`, groupby·join·compute 0행 정직 | 깨끗 |
| T06 | 네이버 호가 vs 실거래 갭% — 전 평형판·국평판 | 전 평형판: 6단지 매칭(동아라이크텐 +6.1%, 파라곤센트럴시티 +1.8%). 국평판은 **meta 문자열을 `split` 세 번** 쪼개 면적을 꺼내 5단지(호반베르디움 −8.9%) | 꼬임(F76-1) |
| T07 | 오송 전세 매물 — 코퍼스 `deal:"lease"` vs 교재 `deal:"rent", lease:"전세"` | lease형 30건 중 **월세 15**, 메시지 "전세/월세", `무시된_파라미터` 없음. 교재형 30건 전부 전세 | 결함 B76-3 |
| T08 | 오송 빌라 전세(직방) ㎡당 보증금 | 1건 196.3만원/㎡(원천이 희소) | 깨끗 |
| T09 | 관심 종목 셋 수익률 표 + 요약 한 줄 | 삼성 +28.57% · 하이닉스 −2.17% · NAVER −14.65%, 합계 +353,500원. 보간 `270000.0원` → `round`로 `270000원` | 깨끗 |
| T10 | 종목 하나가 오타·없는 코드 — 되는 것만 + 실패 이유 | `each{on_error:"collect"}` → flat_map 분리(안내대로): ok 1 · bad 2(`TOOL` "'ZZZZ99' 종목을 찾을 수 없거나…") | 깨끗 |
| T11 | 삼성전자 DART 2025 + 현재가 → PER | 시총 경로 `stock info` **`VALUE_PROTOCOL float64`**. EPS 경로: financials 스필 JSON을 `self:read`로 못 읽음(문단 텍스트) → `self:ledger select`로 EPS 6,605·순이익 45.2조 → PER 40.9 | 꼬임(B76-1·B76-2) |
| T12 | 환율·금·BTC 한 표, 원화 환산 | BTC 행 `current_price` 113,457,457(원화)에 `currency` 칸 없음 → **원화 154,177,338,317**(1,359배) | 결함 B76-5 |
| T13 | BTC 30일 변화율·최고·최저 | 31점 · +6.53% · 최고 86,596.74 · 최저 75,590.24(이력은 `data.prices`) | 깨끗(F76-1 단서) |
| T14 | 흥덕구 월별 인구(KOSIS) + 월별 매매 건수 | 검색 → 메타(`codes`에서 흥덕구 43113) → 데이터 → join: 202608 인구 294,300 · 매매 275. 첫 시도 `on:"period"`(kosis.md 예시)는 "실제 필드: 기간…"으로 정직 거절 | 꼬임(F76-2·F76-3) |
| T15 | 세계은행 GDP + 삼성전자 연평균 종가 — join 설명문 예문 그대로·전량·표본 | 예문 그대로 PARTIAL_SOURCE · `max_points:1500` **PARTIAL_SOURCE**(`limit 1500 retained 1223 scope source`) · `max_points:100` 성공(selection 103행) → 2021~2025 결합 | 결함 B76-4(+F76-3) |
| T16 | 청주 사흘 예보에 5mm 이상 비 → 임장 연기 | 0/0/0.1mm → "임장 OK" | 깨끗 |
| T17 | 오송역 1km 상권 업종 상위 5 | 914점포 · 한식 191 · 부동산 서비스 131 · 기타 간이 69 | 깨끗 |
| T18 | 주택임대차보호법·전세보증금 판례 3건 | 법(2026-01-02)·시행령(2026-07-01) · 판례 날짜 역순 3 | 깨끗 |
| T19 | 등기부(근저당) — 없는 op `registry` | check `incomplete`·이슈 0 → 실행 **success 825행 "아파트 매매 (기간조회)"**, `param_warning`은 봉투 안에만 | 결함(B75-4 재확인) |
| T20 | 네이버가 못 찾으면 직방, 둘 다 안 되면 이유 | `??` 두 가지 모두 실패 → 직방 원인 문구로 정직 실패 · molit try/catch `TOOL` + "district_codes로 목록을…"(은퇴 이름) | 깨끗(F76-3 단서) |
| T21 | 국토부 API·네이버 상태 보고 경로 고르기 | data.go.kr 405(HEAD 미지원) · 네이버 200 → molit | 깨끗 |
| T22 | 매물 설명 급매 판정(judge 5행) | 5행 전부 `false/decided` | 깨끗 |
| T23 | 복대동 빌라 전세 네이버+직방 한 표(단위 맞춤) | 네이버 빌라 전세 0(그 동의 3건은 모두 월세 — 원천 현실) · 직방 5 → merge 5. 단위(원 vs 만원)를 손으로 맞춤. 첫 시도 오송읍은 표본 0/1이라 동을 바꿨다 | 꼬임(F76-1) |
| T24 | 코퍼스 4097·4112 형태 check | `count($m)` → BUILTIN(안내에 `len` 없음) · `'$m.items.0.title'` → `incomplete`·경고 0 · `>> [if]{파이프}` → PIPE_TARGET | check(F76-4·F72-2) |

실거래 표 연산(groupby·복합 키 join·compute), 월별 비교, 빈 달 0행, 부분 실패 collect, 폴백·try/catch, KOSIS 3단계, 세계은행 결합, 날씨 조건, 상권, 법령, judge는 튼튼했다. 실패는 두 자리에서 났다.
1. **판본 2 값 경계가 도구 봉투를 온전히 받지 못하는 자리**: numpy 스칼라, JSON 파일, 거짓 절단 표지
2. **통화 칸 규약의 단위·필드 누락**: 원화 단위 없는 canonical 가격, 출처마다 다른 가격 칸

## 갭의 원장

### B76-1 ★최우선 — `[sense:stock]{op:"info"}`가 판본 2에서 **항상 실패**한다 (★밭 이관: B67-3과 같은 속의 두 번째)

- **요약**:
  - `tool_yfinance.get_stock_info`(550~596행)는 `round(latest["Close"], 2)`·`round(year_high, 2)`·`round(hist.tail(50)["Close"].mean(), 2)` 등 **pandas가 낸 numpy.float64**를 봉투에 싣는다.
  - 판본 1은 이를 JSON으로 직렬화해 문제가 없다(float 하위형).
  - 판본 2의 값 경계 `common/expression_ir.pack`(127행)은 `type(value) is float` 정확 비교라 `VALUE_PROTOCOL "전송할 수 없는 값: float64"`로 거절한다.
- **최소 재현**: `return [sense:stock]{op:"info", ticker:"AAPL"}`(`"005930"`도 같음)
- **실측**:
  - 판본 2: 둘 다 `success:false`, `diagnostic.code:"VALUE_PROTOCOL"`, `source_complete:false`. (보고서 저장 전 AAPL로 다시 재현해 `VALUE_PROTOCOL 전송할 수 없는 값: float64`를 확인했다.)
  - 같은 호출을 판본 1(`edition` 없이)로: `success:true`, `current_price:270000.0 · market_cap:1772972038620000.0 · 52_week_high:374087.45…`
  - T11 시총 경로가 여기서 죽었다.
- **영향**: 시총·52주 고저·50/200일 이평·PER 계산을 모델의 기본 문법으로 못 한다. T11은 DART EPS로 우회했다. 다른 yfinance 경로(`round()`를 쓰는 곳)도 같은 위험이 있다.
- **뿌리**: 67회차 B67-3("numpy 스칼라 거짓 진단")은 파이썬 브리지 `python_bridge_values.value_copy`(22~27행에 numpy `.item()` 분기 추가) **한 자리**만 고쳤다. 같은 정확 타입 비교가 판본 2의 호환 봉투 경계에 남아 있다.
- **제안(수리성, ★밭 이관)**: 개별 수리가 아니다.
  1. 판본 2 값 경계 전수(`pack`·호환 봉투 어댑터·`value_wire` 직렬화·브리지)에서 `type(x) is float/int` 정확 비교를 census한다.
  2. 유한 `numpy.integer/floating`(→`.item()`)·`Decimal` 정규화를 **한 함수**로 모은다.
  3. 관문: 값 경계 모듈의 정확 타입 비교 AST 검사를 넣는다.
  - bool·복소수·NaN 거절 규칙은 유지한다.
  - 가드: {info KR, info US, quote US(yfinance 경로)} × 판본 2 → success, 판본 1과 값 일치.

### B76-2 판본 2 `self:read`가 JSON 파일을 **문단 텍스트로만** 준다 — 도구 스필과 원장 누적 관용구가 값으로 이어지지 않는다

- **요약**:
  - 판본 2 네이티브 `self:read`는 `.json`을 `{text, blocks:[{type:"paragraph",text}], data:{items:[문단 블록], message:원문, count:1}}`로 준다. `format:"json"`을 줘도 같다.
  - 판본 1은 같은 파일의 최상위 필드를 파싱해 돌려준다(`balance_sheet`·`income_statement`…).
  - 교재 내장 함수에는 JSON 파싱이 없다(`json()`은 문자열화).
- **최소 재현**(격리, 스크래치 `outputs/IT76_env.json` = `{"items":[{"a":1}],"count":1}`): `$e = [self:read]{path:"…/IT76_env.json"}; return $e.data`
- **실측**:
  - 격리: `{"items":[{"type":"paragraph","text":"{\"items\":[{\"a\":1}],\"count\":1}"}],…}`. 맨 배열 파일(`[{"a":1},{"a":2}]`)도 같다.
  - T11: `financials`가 스스로 스필한 `file_path`를 읽으면 `data.items[0]` 키가 `type·text`뿐이다. `$doc.data.income_statement` → "필드가 없습니다".
  - 같은 파일을 판본 1로 읽으면 필드가 나온다.
- **영향**:
  - 도구가 "크면 `file_path`+`sample`"로 넘기는 전량(`company financials` 111계정, `stock history`·코인 이력의 전체 데이터 — 투자 가이드가 "전체는 file_path")을 판본 2에서 값으로 못 잇는다.
  - `self:write` 선언이 가르치는 원장 누적 관용구(`$본 = [self:read]{path}` → `$본.items & (새 조회 >> …) >> union >> dedup >> write`)가 판본 2에서 성립하지 않는다.
  - `$본.data.items`는 **문단 블록을 행처럼 내므로** union·dedup에 넣으면 조용한 쓰레기가 된다.
- **우회**: `[self:ledger]{op:"select", path, target:"income_statement"}`는 된다(T11).
- **제안(수리성)**:
  1. 판본 2 `self:read`가 `.json`(과 `format:"json"`)을 파싱해 `data`에 구조를 보존한다. `{items,count}` 봉투면 `data.items`=그 목록, 그 밖의 객체는 `data`=객체, 맨 배열은 `data.items`로 한다. `text`는 원문을 유지한다.
  2. 교재 `self:read` 행에 JSON 해소를 적는다.
  - 가드: {맨 배열, `{items}` 봉투, 임의 객체, 도구 스필 파일} × 판본 1/2 → 같은 구조.

### B76-3 네이버 `deal:"lease"`가 **조용히 전세+월세**가 된다 — 코퍼스 4건이 그렇게 가르치고, 핸들러 주석은 흡수한다고 적는다

- **요약**:
  - `tool_naver._trade_types`(149~163행) 주석은 "모델이 전세/월세를 deal에 넣는 경향이 있어(예 deal="lease"/"전세"), lease가 비면 deal 값을 흡수"라고 적는다.
  - 그러나 코드는 `("전세","jeonse","월세","wolse","monthly")`만 흡수한다. `"lease"`는 마지막 분기 `B1:B2`(전세/월세)로 떨어진다.
  - 판본 2 check·실행 어디서도 경고가 없다(`무시된_파라미터` null).
  - molit은 같은 미지 deal을 "잘못된 조합… deal=rent|trade"로 **정직 거절**한다 — 비대칭.
- **최소 재현**: `[sense:realty]{source:"naver", region:"청주 오송읍", type:"apt", deal:"lease", limit:30}` → meta의 `전세 `/`월세 ` 개수
- **실측**(T07):
  - lease형: `n 30 · 전세 15 · 월세 15`, 메시지 "apt 전세/월세 — 30건"
  - 교재형 `deal:"rent", lease:"전세"`: `n 30 · 전세 30 · 월세 0`
- **영향**:
  - 코퍼스 3812("청주 새 전세 매물 3건만")·4097("새 전세 매물 있으면 보내줘")·4116·4129("전세 워크플로우")의 의도는 모두 전세다. 이 형태로 감시하면 월세 매물이 전세 알림으로 온다.
  - 행에 거래유형 칸이 없어(F76-1) 뒤에서 가를 수도 없다. 월세 행의 `price`는 보증금이라 평균 보증금이 크게 낮아진다.
  - 사용자 저장 워크플로우·트리거에는 이 형태가 0건이다(grep 확인). 수리는 비파괴다.
- **제안(수리성)**:
  1. deal 허용값(`trade|rent` + 흡수 낱말)을 선언에 적는다. 미지 값은 molit처럼 정직 거절하고 `lease:"전세"|"월세"`를 안내한다.
  2. 주석을 코드와 맞춘다.
  3. 코퍼스 4건은 용례 재검토 관문으로 보낸다.
  - 가드: {naver, zigbang} × {`lease`, `전세`, `jeonse`, 미지 값} → 흡수 또는 거절, 메시지·결과 유형 일치.

### B76-4 `stock history`는 **전량을 요청하면 실패하고 표본을 요청해야 성공**한다 — 거짓 절단 표지

- **요약**:
  - `common/response_formatter.compact_price_series`(137~146행)는 50행을 넘으면 **다운샘플 결과와 무관하게** `truncated=True`를 낸다. `max_points ≥ 행 수`면 `downsample_prices`의 step이 1이라 전량인데도 그렇다.
  - `investment/handler._attach_price_table`(283~291행)은 이를 `bounded_selection(requested, requested, len(prices), True)`로 넘긴다. `retained(1223) < limit(1500)`이라 `scope:"source"`가 된다.
  - 판본 2는 `PARTIAL_SOURCE` 실패로 올린다.
  - 기본값(max_points 10, 요청 없음)도 `source`라 실패한다.
- **최소 재현**: `return [sense:stock]{op:"history", ticker:"005930", period:"5y", max_points:1500}` · 같은 문장 `max_points:100` · `max_points` 생략
- **실측**(T15):
  - 1500 → `PARTIAL_SOURCE`, `truncations:[{scope:"source", reason:"max_points", limit:1500, retained:1223}]`, `total 1223`, `truncated true`
  - 100 → success, `[{scope:"selection", limit:100, retained:103}]`
  - 생략 → `PARTIAL_SOURCE`(1223일 → 12점)
- **영향**:
  - "5년 주가 전부로 연평균"처럼 전량을 원하면 실패하고, 덜 달라고 해야 성공한다. 역설이다.
  - 교재 예문이 판본 2에서 모두 죽는다: 투자 가이드 "시세 조회 → 차트"(`history` 기본값), `table:join` 설명문의 `[sense:stock]{op: history} & [sense:world_bank]{…} >> [table:join]{on:"연도"}`.
  - 코인 이력(`max_points` 기본 400)은 별도 경로라 이번엔 통과했다.
- **닫힌 밭과의 관계**: 절단 표지 밭은 68회차 수리(절단 생산자 34파일·59곳 분류 + 관문 C)로 닫혔다. 이 항목은 표지 **누락**이 아니라 **거짓 표지**(전량인데 `truncated:true`)다. 관문 C가 표지의 존재만 보고 내용을 대조하지 않는다는 증거로 적는다. 밭을 다시 갈 필요는 없다.
- **제안(수리성)**:
  1. `compact_price_series`는 실제로 행을 버렸을 때만 `truncated`를 낸다(`len(compact) < total`).
  2. `bounded_selection`은 요청 ≥ 모집단이면 절단이 아니다.
  3. 관문 C에 불변식을 더한다: `truncated ⇒ retained < total`, `retained == len(items)`.
  - 가드: `max_points` {생략, < 총, = 총, > 총} × {KR, US, 지수} → 성공/selection/source 판정.

### B76-5 `sense:crypto`의 canonical `current_price`는 **원화인데 통화 칸이 없다** — 주식 시세와 합치면 원화 환산이 1,359배 틀린다

- **요약**:
  - `investment/handler`의 스냅샷 병기(448~467행, "F1-스냅샷 canonical 병기 2026-08-16")는 `current_price`가 비면 `current_price_krw or current_price_usd`를 넣는다.
  - 그런데 `currency` 칸을 싣지 않는다.
  - 형제 `sense:stock` quote 행은 `currency`(USD·KRW)를 싣는다. 같은 `current_price` 칸이 출처에 따라 단위가 다르고, 그 단위를 말하는 칸이 한쪽에만 있다.
- **최소 재현**: `$u = [table:union]{inputs:[[sense:stock]{op:"quote", ticker:"GC=F"}, [sense:crypto]{coin:"BTC"}]}` → 행별 `get($r,"currency","USD")`로 원화 환산
- **실측**(T12):
  - BTC 행 `current_price 113457457`, `has($btc.items[0],"currency") = false`
  - `current_price_usd 83475` · `current_price_krw 113457457`
  - "통화 없으면 USD"로 환산 → **154,177,338,317원**(실제 1.13억, 1,359배). 금(GC=F) 행은 `currency:"USD"`로 정상(4,170.2 USD → 5,666,885원).
- **영향**: "환율·금·코인 한 표"·"포트폴리오 원화 평가"처럼 자산군을 합치는 순간 조용히 틀린다. 병기의 목적(union 행을 온전하게)이 단위에서 새고 있다.
- **제안(수리성)**:
  1. canonical 가격을 병기할 때 `currency`를 함께 병기한다(krw면 `"KRW"`, usd 폴백이면 `"USD"`).
  2. `scripts/currency_items_sweep.py`에 "가격 canonical 칸 ⇒ 단위 칸 동반" 검사를 더한다. F76-1과 한 스윕이다.
  - 가드: {stock KR, stock US, 원자재, 환율, crypto} union → 행마다 `currency` 존재.

### F76-1 통화 칸 규약의 병기가 **도구마다 반쪽**이다 — 단위·필드를 손으로 맞춰야 조합이 된다

- **molit**:
  - `price`(원 정수) 병기(R7 칸 규약 2)는 `tool_apt_trade_range`·`tool_apt_trade` **둘뿐**이다.
  - 전월세 3도구(`보증금`="18,000" 만원 콤마 문자열)와 단독·연립 매매에는 없다.
  - T03 전세가율은 `전세평균만원 * 10000 / 매매평균원`을 손으로 적었다. `real_estate.md` §7 레시피는 단위를 말하지 않는다.
- **naver**:
  - 행 칸이 `title·name·meta·summary·url·image·lat·lng·price(·rent)`뿐이다. **전용면적·층·거래유형은 meta 텍스트에만** 있고, `_trade`는 밑줄 접두라 출력에서 빠진다(`tool_naver._article_to_item`).
  - 평형 맞춤 호가 비교(T06 국평판)는 `number(replace(split(split($x.meta," · ")[1],"/")[1],"㎡",""))`였다.
  - 전세/월세가 섞인 결과(B76-3·기본 `deal:"rent"`)를 행 칸으로 가를 수 없다. zigbang은 09-09 수리로 `area_m2·floor·salesType`을 보존했다.
- **단위 불일치**: zigbang `deposit`(만원) · naver `price`(원) · molit 매매 `price`(원) · molit 전세 `보증금`(만원 문자열). T23 병합에서 손으로 맞췄다.
- **이력 위치**: 코인 이력은 `data.prices`(items는 스냅샷 1행)이고 주식 이력은 `items`다.
- **제안(수리성)**: `currency_items_sweep`을 "가격·면적·거래유형 canonical 칸 + 단위" 격자로 확장한다(realty 3소스 × 매매/전월세 × apt/house/villa, crypto 이력). molit 전 도구 `price`, 전월세 `deposit_won`(가칭)·`rent_won`, naver `area_m2`·`floor`·`deal_type`을 병기한다(원명 보존). 이름 확정은 R7 칸 규약 명문화(ibl.md)를 따른다.

### F76-2 `UNOBSERVED_FIELD`가 **정상 필드에 거짓 경고**를 낸다 — 관측 반환의 변이 축이 source만 있다

- 68회차에 들어온 관측 필드 경고는 `data/ibl_return_shapes.json`의 변이 키(`node:action[#op][@param=값]`)를 쓴다. `sense:realty`는 `@source=naver`·`@source=zigbang`만 선언돼 있다(`shape_variants:`).
- 그래서 molit **`deal:"rent"`** 행의 `계약유형`·`보증금`·`월세`는 매 조회마다 경고가 난다(T02·T03·T14: "관측된 반환 필드에 없는 이름입니다: 계약유형. 관측 필드: 아파트명, …, price").
- `sense:kosis`의 `info:true` 결과 `codes`도 같다(검색 모드의 열만 관측).
- 영향: 교재가 "경고면 describe로 실제 필드를 확인하라"고 가르치므로, 거짓 경고는 확인 비용과 경고 불신을 함께 만든다.
- 제안(수리성): 변이 선언을 원천 모양 축 전부로 넓힌다(realty `deal=rent`·`type=house/villa`, kosis `info=true`·`tbl_id` 데이터 모드, company op별). 그리고 호출 인자에 선언되지 않은 변이 축 값이 있으면 경고를 "미관측 변이"로 낮춘다. 가드: 변이별 fixture로 경고 0.

### F76-3 외부 조회 표면의 교재 드리프트 — 예문이 판본 2에서 돌지 않는다

- `table:join` 설명문(`data-ops/ibl_actions.yaml` 541행) 예문 `[sense:stock]{op: history} & [sense:world_bank]{…} >> [table:join]{on:"연도"}`
  - 주가 이력에는 `연도`가 없다(`date`).
  - B76-4로 기본 호출부터 실패한다(T15).
- `kosis.md` 99행 `>> [table:chart]{…x:"period"…}` — 실제 열은 `기간`이다(T14 첫 시도의 join이 "실제 필드: 기간…"으로 거절).
- `realty.md` 107행 워크플로우 5 `>> [table:chart]{x:"month", y:"price"}` — molit에 `month` 없음(`거래월`·`조회년월`), 파이프는 B73-1, `x`·`y`는 B73-2.
- `investment.md` 122행 "시세 조회 → 차트" — B76-4·B73-1.
- `real_estate.md` 157~162행 전세가율 레시피는 매매·전세 평균을 나누라고만 한다. **단지 정체성(`아파트명`만으로는 동명 단지가 섞임)·평형·단위**가 없다.
  - T03 첫 시도가 레시피대로 조인해 '효성' **328.6%**를 냈다.
  - 격리: 매매 '효성'=복대동 37.48㎡ 7,000만원, 전세 '효성'=가경동 99.98㎡ 23,000만원.
- 런타임 문구 `tool_region_codes.py` 576행 "district_codes로 목록을 확인할 수 있습니다" — 2026-06-03에 은퇴한 이름이다(현행 `[sense:realty]{op:"codes"}`). `data/retired_contracts.yaml`에 없다.
- B76-3의 `_trade_types` 주석.
- 제안(수리성): 예문을 판본 2 형태로 고치고 실행 가능한지 확인한다. 전세가율 레시피에 `[아파트명, 법정동]` 복합 키·평형 띠·단위를 명시한다. `district_codes`는 은퇴 계약으로 등록한다(§4-3 교재 수리는 표면 전수).

### F76-4 옛 판본 문자열 치환(`"$m.value"`·`'$m.items.0.title'`)이 판본 2에서 **문자 그대로**인데 check가 말하지 않는다

- T24: `return {body:'$m.items.0.title'}` → `incomplete`, warnings 0. 판본 2는 f-문자열만 보간하므로 이 값은 글자 그대로의 `$m.items.0.title`이다.
- 옛 판본 용례 중 일반 문자열 안에 `$이름.필드`가 든 것이 **123문장**이다(부동산·투자·코인 16 — 4097 `'$m.items.0.title'`, 4108 `"최고가 $m.value 만원"`, 4166 `"$요약.message"` 등).
- 회상은 이들을 옛 판본으로 표시해 새 문법으로 옮기라고 한다. 따옴표만 유지해 옮기면 알림·메일 본문이 **변수 이름 그대로** 나가고, 성공으로 끝난다.
- 제안(수리성): 판본 2 check가 일반 문자열 리터럴 안의 `$식별자(.필드)+` 모양에 경고한다("보간은 f\"${…}\" — 문자 그대로 의도면 무시"). 용례 재검토 관문에 이 모양을 추가한다.

### V76-1 (후보) 등기부(권리관계) 조회 수단이 없다

- `real_estate.md` §7은 "근저당 + 선순위 보증금 합계가 건물가의 70~80% 초과 시 위험"을 판단 기준으로 가르친다. 그러나 어휘 전체에 등기 조회가 없다(T19). 인터넷등기소는 로그인·유료다.
- 어휘 신설은 훈련이 하지 않는다. 사용자가 발급한 등기부 PDF를 `self:read`로 읽는 문장으로 먼저 얼려 반복 사용을 본다.

## 재확인 (앞 회차 갭의 증거 추가 — 새 항목 아님)

- **B75-4**(판본 2 check의 액션별 사전 판정 부재, 밭 이관):
  - 미선언 op `[sense:realty]{op:"registry"}`를 옛 `/ibl/validate`는 typecheck 오류로 잡는다("선언된 op 가 아닙니다… 사용 가능: ['codes','query']").
  - 판본 2 check는 `incomplete`·이슈 0이다.
  - 실행은 핸들러 `handler.execute`의 `_OP_DISPATCHERS[...].get(_op, _op_query)` 폴백(232~235행)으로 **실거래 825행 success**였고, `param_warning`은 봉투 안에만 있다(T19).
  - census 항목에 "op 선언 대조"와 "미지 op 폴백 디스패처"를 더한다.
- **B72-3**(표지 없는 절단): naver 기본 `limit` 30(최대 3페이지)은 `isMoreData`를 버리고 `truncated`·`total`이 없다. T06·T07이 정확히 30건으로 찼는데 더 있는지 알 수 없다(가이드 §9는 "재고를 절반 이하로 과소평가"라 경고).
- **B73-1**: `realty.md` 워크플로우 5·`investment.md` "시세 조회 → 차트"가 `>> [table:chart]` 형태다.
- **F72-2**: `count($m)` → BUILTIN "알 수 없는 내장 함수: count"인데 안내가 `len`을 말하지 않는다. `$x.9월` → SYNTAX "이름이 필요합니다"인데 안내가 `get($x,"9월")`을 말하지 않는다(T24·T04).
- **G73-1**: T12 원화 환산("KRW면 그대로, 아니면 환율 곱")이 순수 식 조건 값 부재로 each+if 네 줄이 됐다.

## 시드 후보 (실행 검증 통과만 — 자동 등록 안 함)

- T01(molit 매매 → groupby 단지 → filter 건수 → sort → take)
- T02(전월세 → filter 전세 → groupby 평균 보증금)
- T04(월별 filter → 지역 함수 → join → compute 변화율, 숫자로 시작하는 열은 `get`)
- T05(빈 달의 0행 흐름)
- T09(each quote → compute 수익률, 보간은 `round`)
- T10(`each{on_error:"collect"}` → flat_map로 성공·실패 분리)
- T13(코인 `data.prices` → 변화율·max/min)
- T14(KOSIS 검색 → `info` codes → 데이터 → join)
- T16(날씨 filter → `[if]` 판정)
- T17(상권 groupby → sort count → take)
- T18(법령·판례 take/sort/select)
- T21(http 두 개 → union → select → 경로 선택)
- T22(judge 5행)

문장 안 지역 코드·종목·단지는 자리표로 바꿔 심을 것.

**빼는 것**:
- T03·T06·T23: F76-1 수리(가격·면적 병기) 전의 손 단위 맞춤·meta 쪼개기
- T11: B76-1·B76-2 우회
- T15: B76-4 표본 우회
- T07·T12·T19: 결함
- T24: check만
- 코퍼스 3812·4097·4116·4129(`deal:"lease"`), 4097·4112(`count`), 일반 문자열 `$변수.필드` 123문장은 **용례 재검토** 대상이다(B76-3·F76-4).

## 판정 요청 (언어 개정·파괴적 변경 2종만)

없음. B76-1~5·F76-1~4는 모두 수리성이다.
- B76-3의 미지 deal 거절은 사용자 저장 워크플로우·트리거 0건이라 파괴적이지 않다. 코퍼스는 용례 재검토로 처리한다.
- F76-4는 경고 추가라 언어 개정이 아니다.
- V76-1은 후보로만 둔다.

**다음 수리 턴의 첫 항목(밭 이관)**:
1. B76-1 — 판본 2 값 경계 전수에서 정확 타입 비교 census → 유한 numpy·Decimal 정규화 한 함수 + AST 관문(B67-3에 이은 두 번째).
2. B76-5·F76-1 — `currency_items_sweep`을 가격·면적·거래유형·단위 격자로 확장해 한 스윕으로 병기한다.

## 72~76회차를 가로지르는 공통 뿌리 (훈련자 관찰)

1. **판본 2 경계가 옛 도구의 행동을 한 차원씩 놓친다.** 매 회차 새 차원이 하나씩 나왔다 — B72-2(선언 밖 인자 거절) · B73-1(pipe_in 파이프 자리) · B74-5(평문 실패가 ADAPTER_SHAPE) · B75-4(옛 검수기의 사전 판정 부재) · B76-1(numpy 스칼라) · B76-2(JSON 구조 소실) · F76-4(문자열 치환 침묵). 각각 따로 수리하면 다음 차원이 또 나온다. 실제 fixture·코퍼스 봉투를 **판본 1/판본 2 양쪽에 재생해 대조하는 차분 관문**(parity census) 하나가 이 속 전체를 닫을 자리로 보인다.
2. **선언·교재와 실제 동작의 어긋남을 대조하는 관문이 없다.** 선언∖읽기(B72-4·B73-2), 읽기∖선언(B72-2), 변이 선언(F76-2), 교재 예문(F75-3·F76-3), 주석(B76-3).
3. **통화 칸 규약의 단위·필드가 출처마다 다르다.** F72-4·B76-5·F76-1. `currency_items_sweep`이 칸 존재만 보고 단위는 보지 않는다.

## 위생

- **기준선**: 탐침 전 23:23:34에 떴다([baseline.json](baseline.json)). action_health max id 242475, notify_log 6243, 알림함 3통, since 원장 1스트림 25행.
- **회차 후 diff**:
  - action_health 새 행 **134, 전부 `training`/agent**(usage 0)
  - notify_log 새 행 0 · 알림 추가 0 · since 원장 불변(IT76 행 0 — T24는 check만)
- **외부 호출 77회**(action_health 기준, 실패 포함): realty 29 · stock 24 · kosis 5 · company 5 · world_bank 4 · crypto 3 · legal 2 · http 2 · weather 1 · commercial 1 · judge 1(Jev, 5행). 고친 문장 재실행 5건은 `reuse`로 읽기 영수증을 재사용했다. (보고서 저장 시 B76-1 재현용 `stock info` 1회 추가.)
- **도구 스필**: `financials`·`history`가 호출마다 `outputs/investment/`에 새 파일을 쓴다. 이 회차가 만든 11파일(`financial_00126380_20260928_2326~2333` 5개, `kr_prices_005930_20260928_2333~2335` 6개)을 삭제했다. 09:34·09:37의 같은 이름 파일은 다른 실행의 것이라 두었다.
- **격리 스크래치**: `outputs/IT76_list.json`·`outputs/IT76_env.json`(B76-2 격리)은 셸로 만들고 바로 지웠다.
- **나머지**: 발신 0(`notify_user`·`channel_send` 미사용) · 사용자 원장·트리거·캘린더는 읽기만 · 해마 시딩 0 · 라이브 코어 편집 0 · 커밋 0.
- **백엔드**: 회차 내내 `state.json` phase `ACTIVE`(`last_result.outcome: restarted`), 재기동·FAILED 없음.

## 집행 완료

### 1차 — `1b9a4932`(2026-09-29)

B76-1~5·F76-1~4 개별 자리. 요약은 `docs/IMAGINATION_72_76_REPAIRS.md` 76회차 절.

### 2차 — 76·77 잔여 재탐침·수리(2026-09-29)

보고서 재현 문장을 라이브로 다시 대 보았다. B76-1(numpy)·B76-2(JSON 읽기)·B76-3(lease)·B76-5(통화 칸)·F76-1(molit·naver 칸)·F76-3(교재)·F76-4(LITERAL_DOLLAR)는 살아 있었다. 아래가 샜다.

- **B75-4 재확인(T19) — 미지 op 이 여전히 실거래 성공이었다.** `[sense:realty]{op:"registry"}` 가 check `incomplete`·이슈 0, 실행 842행 success.
  - 뿌리: 손으로 쓴 `callable_contract` 는 `ops` 선언의 투영(op 허용값·기본값·op별 효과)을 받지 못했다. 유도 계약만 받았다. 같은 처지가 `self:script`.
  - 수리: `ibl_v2_contracts.project_ops` 한 벌을 유도·선언 계약이 함께 쓴다(`declared_contract`). realty 핸들러의 `.get(op, _op_query)` 폴백을 거절로 바꿨다.
  - 관문: 빌드가 `_OP_DISPATCHERS[…].get(op, 폴백)` 을 금지한다(`iblbuild_validators._dispatcher_fallbacks`). 선언 계약의 `enums.op` 가 `ops.values` 와 어긋나면 신고한다(`iblbuild_v2`).
  - 라이브: check `ARGUMENT_CONTRACT "op: 허용 값 ['query','codes']"`, 실행도 같은 거절.
- **B76-4 잔여 — 전량 요청 봉투에 `total` 이 없었다.** `max_points:1500` 성공 봉투에서 `$h.total` 이 MISSING_FIELD. 절단일 때만 모집단을 실었다. 봉투 모양이 절단 여부로 바뀌지 않게 `total` 을 상시 싣는다(라이브 `{n:1223, t:1223, tr:false}`).
- **F76-2 재확인 — 관측 좌표 축이 손 선언(realty)에만 있었다.** `[sense:book]{source:"nl"}` 의 `meta` 에 거짓 UNOBSERVED_FIELD(정보나루 fixture 열로 판정). `self:material{op:"list"}` 의 `.items` 경고는 op 를 모르는 실사용 관측(add 봉투)을 빌려준 탓.
  - 수리: `ibl_typecheck.shape_axes` 가 좌표 축을 기존 선언에서 유도한다(shape_axes · shape_variants 라벨 · param_support 축 · 스키마 enum 2값 이상). 좌표가 다른 호출은 미상으로 기권한다. op 있는 액션에는 실사용 관측을 빌려주지 않는다. book 에 `shape_axes: {source: null}` 을 선언했다.
  - 라이브: 원천 변이는 경고 0, 기본 원천의 진짜 오타(`nosuchcol`)는 여전히 경고.
- **F72-2 재확인(T04·T24).** `count` → "비슷한 내장 함수: len, …"(다른 언어 관용 이름 표 + 철자 근접, 컴파일·실행 한 문장). `$x.9월` → "목록 위치는 $값[0], 숫자로 시작하거나 기호가 든 필드는 get(…) 또는 $값[\"필드\"]". INDEX 진단 details 에 index·length·variable.
- **직방 매매 `price`(F76-1 형제, 수리 중 발견).** 매매 매물의 `price` 가 보증금으로 채워졌다(표시는 매매가 우선이라 둘이 어긋남). 매매는 매매가, 임대는 보증금.
- **용례 #4108 교정.** 직방 `price`(원)를 만원 30000 과 비교해 3억 경고가 항상 켜지던 교재. 300000000 으로 고치고 벡터를 재색인했다(백업·영수증 `data/_backups/2026-09-29_imagination76_77_corpus/`, git 밖).
- 밭 이관 2 — 가격·면적·거래유형 격자는 77회차 F77-1 표시 칸 접기 관문(`scripts/iblbuild_meta_fields.py`)이 전 패키지에서 집행한다(77회차 보고서 집행 절).

검증은 77회차 보고서 집행 절과 같다.
