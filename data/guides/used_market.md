# 중고 매물 검색 가이드 — [sense:used]{source}

> 2026-07-12 결정화·실측 기준. 자주 하는 중고물건 검색을 즉석 코드(ddg `site:` 해킹) 대신
> 단일 어휘로. 소스마다 액션이 아니라 **한 액션 + source 파라미터**(직방 `sense:realty{source}` 선례).

## 1. 기본 사용법

```
[sense:used]{source: "bunjang", query: "맥미니 m4 pro"}
[sense:used]{source: "danggeun", query: "아이폰 15", region: "죽백동"}
[sense:used]{source: "joongna", query: "소니 카메라"}
[sense:used]{source: "naver", query: "닌텐도 스위치"}
```

- **query**(필수) 검색어 · **limit** 개수(기본 15) · **region** 지역 필터(source별 의미 다름 — §3)
- 통화 = `items[{title, meta, summary, url, image, price, …}]` → `>>` 조합 가능. 수치·지역은 구조 칸(price·location/region·sold)으로 읽는다
- `scope: workspace` — 순수 검색이라 project_id 불요

## 2. 소스 선택 기준

| source | 코퍼스 | 강점 | region 의미 |
|--------|--------|------|------------|
| **bunjang**(기본) | 번개장터 전국 | 내부 API=깨끗한 JSON, 매물별 위치 표기(일부만) | 위치 substring **후필터 표본**(예 "청주") — §2-1 |
| **danggeun** | 당근 동네 직거래 | **동네 스코프**(해당 동+인근 동), 설명·사진·매물 동 | 동 이름(예 "죽백동", **필수**) → 지역ID 자동 해소 |
| **joongna** | 중고나라 web | 전국, RSC 파싱(best-effort — 일부 필드 누락 가능) | 미지원 |
| **naver** | 네이버 카페(중고나라 등) | 게시글 단위, API 키 기반 | 미지원 |

**판단 규칙:**
- "우리 동네 / 근처 / 직거래" → **danggeun + region(동 이름)** — 당근의 가치가 '내동네'다.
- 위치가 표기된 전국 매물 → **bunjang**(+region substring). 매물별 위치가 있는 유일한 전국 소스.
- 망라 검색 → 병렬 조합: `[sense:used]{source:"danggeun",…} & [sense:used]{source:"bunjang",…}`

### 2-1. 번개장터 region 은 표본이다 (2026-09-29, 79회차 B79-4)

번개장터 API 에는 지역 이름 인자가 없다. region 을 주면 **전국 최신순을 40행씩 최대 5쪽(200행)** 훑어
위치 칸에 그 문자열이 든 매물만 남긴다. 위치 미표기 매물(표본의 대다수)은 판정할 수 없어 빠진다.
봉투가 해석을 말한다 — `scanned`(훑은 행)·`unlocated`(위치 미표기로 뺀 행)·상한에 닿아 limit 을 못 채우면
`truncations:[{scope:"source", reason:"scan_limit"}]`. 그래서 0건은 "그 지역 매물 없음"이 아니라
"최신 200행 표본에 없음"이다 — 동네 매물 질문은 danggeun 으로 가라.

## 3. 당근(danggeun) 내부 동작과 함정 — 2026-07-12 실측

핸들러(`shopping-assistant/tool_used.py` `search_danggeun`)는 2단으로 동작한다:

1. **지역 해소**: `GET www.daangn.com/kr/api/v1/regions/keyword?keyword={region}` → `locations[0].id`
   (시도·시군구·동 depth까지 반환. 키·쿠키 불요, 브라우저 UA만)
2. **검색**(2026-09-29 재실측으로 교체): 옛 `/kr/buy-sell/?in=x-{id}&search=` 는 301 로
   `/kr/search/buy-sell/?in=x-{id}&q=` 에 가고 JSON-LD 가 없어졌다. 새 페이지는 Remix 앱이라
   SSR HTML 의 `window.__remixContext` 에도 목록 칸(buySellArticles)이 있지만 **비어 오고** 브라우저가
   같은 로더를 JSON 으로 다시 부른다. 핸들러는 그 로더를 직접 읽는다:
   `GET …/kr/search/buy-sell/?in=x-{id}&q={query}&_data=routes/kr.search.buy-sell._index`
   → `buySellArticles[{title, content, price, thumbnail, status, createdAt, region{name}, href}]`
   (한 응답에 전체, 수백 건). 행의 `region` 이 **매물의 실제 동**이고 `search_region` 이 검색 동네다.

**함정(코드가 이미 처리하지만, 직접 만질 때 주의):**
- ★`in=` 슬러그의 한글 이름은 **장식이고 숫자 ID만 유효** — 이름이 틀려도 에러 없이 ID의
  지역이 조용히 나온다(예: `죽백동-1372`는 의정부 녹양동). 반드시 regions/keyword로 해소.
- ★당근 HTML 응답에 charset 헤더가 없어 requests가 ISO-8859-1로 디코딩=한글 모지바케 →
  `_get`이 UTF-8 강제 보정.
- ★구조를 못 찾으면(로더 JSON 에 buySellArticles 없음) `error_type:"source_changed"` 실패다 — 0건이 아니다.
- ★같은 요청이 한 번은 283건, 몇 분 뒤 0건(광고도 0, 응답 지연 3초대)을 준 실측이 있다 — 당근 검색 서버가
  느리면 빈 목록으로 떨어진다. 핸들러는 0건이면 한 번 다시 묻고, 그래도 0건이면 성공 0건에 `empty_notes`
  (미확인)를 싣는다. 이 0건으로 "매물 없음"을 단정하지 말 것.
- 결과 스코프 = 해당 동 + 인근 동(당근 앱의 '내동네'와 유사). GPS 반경 지정은 여전히 앱 전용.
- **region 필수** — 지역 없는 요청은 당근이 접속 IP 로 동네를 추정해 조용히 스코프한다(실측). 고르지 않은
  동네의 결과를 전체처럼 줄 수 없어 거절한다.
- 필터 파라미터는 `in`·`category_id`뿐 — 가격 조건은 items 후필터로.

## 4. 옛 실패 지식 (재-즉석코딩 방지)

- **ddg `site:bunjang.co.kr OR site:daangn.com` 해킹은 은퇴** — 이 액션이 대체. 검색엔진 경유는
  낡은 캐시·매물 아닌 페이지가 섞인다.
- 번개장터/중고나라의 **Playwright SPA 셀렉터는 빈 껍데기**(클라이언트 렌더) — 내부 API/RSC로 대체됨.
- 당근은 2026-07 SSR JSON-LD 경로가 2026-09 에 사라졌다 — 페이지 구조는 또 바뀐다. 구조 미발견은
  `source_changed` 로 드러나고, 주간 정직성 스윕이 `shape_variants` 의 source=danggeun 줄을 돌려 0행을 경보(불변식 G)한다.
  위 §3 레시피가 정본.

## 5. 부동산과의 경계

당근 **부동산**(realty.daangn.com)은 다른 코퍼스·다른 함정(동 필터 미적용 SSR)이다 —
부동산 매물은 `[sense:realty]{source: molit/zigbang}` + `real_estate.md` 가이드를 따를 것.
중고 물건 검색만 이 액션이다.
