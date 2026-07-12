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
- 통화 = `records[{title, meta, summary, url, image}]` (realty/nanet과 동일 봉투) → `>>` 조합 가능
- `scope: workspace` — 순수 검색이라 project_id 불요

## 2. 소스 선택 기준

| source | 코퍼스 | 강점 | region 의미 |
|--------|--------|------|------------|
| **bunjang**(기본) | 번개장터 전국 | 내부 API=깨끗한 JSON, **매물별 위치 표기** | 위치 substring 후필터(예 "청주") |
| **danggeun** | 당근 동네 직거래 | **동네 스코프**(해당 동+인근 동), 설명 전문·사진 | 동 이름(예 "죽백동") → 지역ID 자동 해소 |
| **joongna** | 중고나라 web | 전국, RSC 파싱(best-effort — 일부 필드 누락 가능) | 미지원 |
| **naver** | 네이버 카페(중고나라 등) | 게시글 단위, API 키 기반 | 미지원 |

**판단 규칙:**
- "우리 동네 / 근처 / 직거래" → **danggeun + region(동 이름)** — 당근의 가치가 '내동네'다.
- 위치가 표기된 전국 매물 → **bunjang**(+region substring). 매물별 위치가 있는 유일한 전국 소스.
- 망라 검색 → 병렬 조합: `[sense:used]{source:"danggeun",…} & [sense:used]{source:"bunjang",…}`

## 3. 당근(danggeun) 내부 동작과 함정 — 2026-07-12 실측

핸들러(`shopping-assistant/tool_used.py` `search_danggeun`)는 2단으로 동작한다:

1. **지역 해소**: `GET www.daangn.com/kr/api/v1/regions/keyword?keyword={region}` → `locations[0].id`
   (죽백동=4796, 시도·시군구·동 depth까지 반환. 키·쿠키 불요, 브라우저 UA만)
2. **검색**: `GET www.daangn.com/kr/buy-sell/?in=x-{id}&search={query}` → HTML 속
   `<script type="application/ld+json">` **ItemList에 전체 결과 통째**(282건도 한 응답,
   페이지네이션 불요 — page 파라미터는 무시됨). Product당 name/description/image/url/price/seller.

**함정(코드가 이미 처리하지만, 직접 만질 때 주의):**
- ★`in=` 슬러그의 한글 이름은 **장식이고 숫자 ID만 유효** — 이름이 틀려도 에러 없이 ID의
  지역이 조용히 나온다(예: `죽백동-1372`는 의정부 녹양동). 반드시 regions/keyword로 해소.
- ★당근 HTML 응답에 charset 헤더가 없어 requests가 ISO-8859-1로 디코딩=한글 모지바케 →
  `_get`이 UTF-8 강제 보정.
- 매물별 동네명은 JSON-LD에 없다(카드 HTML 첫 ~60개에만) — meta엔 해소된 지역명+"인근" 표기.
- 결과 스코프 = 해당 동 + 인근 동(당근 앱의 '내동네'와 유사). GPS 반경 지정은 여전히 앱 전용.
- region 미지정도 작동하지만 지역 스코프가 없는 기본 결과 — 동네 매물엔 region 권장.
- 필터 파라미터는 `in`·`category_id`뿐 — 가격 조건은 records 후필터로.

## 4. 옛 실패 지식 (재-즉석코딩 방지)

- **ddg `site:bunjang.co.kr OR site:daangn.com` 해킹은 은퇴** — 이 액션이 대체. 검색엔진 경유는
  낡은 캐시·매물 아닌 페이지가 섞인다.
- 번개장터/중고나라의 **Playwright SPA 셀렉터는 빈 껍데기**(클라이언트 렌더) — 내부 API/RSC로 대체됨.
- 당근도 옛 진단("web 매물 클라이언트 렌더라 불가")은 **URL이 틀렸던 것** — `/kr/buy-sell/?in=`
  경로는 SSR이다. 위 §3 레시피가 정본.

## 5. 부동산과의 경계

당근 **부동산**(realty.daangn.com)은 다른 코퍼스·다른 함정(동 필터 미적용 SSR)이다 —
부동산 매물은 `[sense:realty]{source: molit/zigbang}` + `real_estate.md` 가이드를 따를 것.
중고 물건 검색만 이 액션이다.
