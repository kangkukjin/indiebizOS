# 프리랜서·외주 서비스 검색 (기술 참조) — [sense:freelance]

> 2026-08-04 신설. 크몽(kmong) 비공식 내부 API 어휘화 (직방 sense:realty·중고 sense:used 의 source 분기 선례).

## 무엇

프리랜서 마켓플레이스에서 **서비스 상품**(로고 제작, 번역, 영상편집…)과 **전문가(사람)** 를 검색.
현재 source=`kmong`(크몽)만. 숨고·위시켓은 후속 source 후보.

| type | 무엇 | 응답 핵심 필드 |
|------|------|----------------|
| `gigs` (기본) | 서비스 상품 | 제목·가격(원)·평점·리뷰수·판매자 닉네임·등급·카테고리·세금계산서 여부 |
| `experts` | 전문가 프로필 | 닉네임·등급(MASTER 등)·자기소개·경력 연차·평균 응답시간(분)·누적 주문수·포트폴리오수·전문분야·스킬·만족도% |

## 사용법

```
[sense:freelance]{query: "로고디자인"}                          # 서비스 검색 (기본, 인기순)
[sense:freelance]{query: "번역", sort: "score"}                 # 연관도순
[sense:freelance]{query: "영상편집", max_price: 100000}         # 10만원 이하 (후필터)
[sense:freelance]{type: "experts", query: "로고디자인"}         # 전문가(사람) 검색
[sense:freelance]{query: "로고", limit: 40} >> [table:sort]{by: "price"} >> [table:take]{n: 5}
```

- **사람을 찾는 질문**("~할 프리랜서/전문가 찾아줘")이면 `type: "experts"`, **얼마에 해주나**("로고 제작 얼마")면 기본 `gigs`.
- sort: `ranking`(인기, 기본) / `score`(연관도). ★서버는 이 둘만 받는다(그 외 400 실측 — 평점순 등은 없음).
- 통화: items[{title, meta, summary, url, image, price}] — table 파이프 가능. experts 는 대표 서비스 `gig_url`/`gig_title` 동봉.

## 내부 구현 레퍼런스 (함정 포함)

### 공통
- ★**HTML 크롤링 불가**: kmong.com 은 Next.js App Router **클라이언트 fetch** 구조 — 첫 HTML(RSC flight 포함)에 검색 데이터가 **없다**(실측). 반드시 내부 API 직접 호출.
- 내부 API `api.kmong.com/gig-app/*` — **인증·키 불요**, 봇 차단 없음. curl_cffi `impersonate="chrome"` + Origin/Referer 헤더(직방 선례).
- `sortType` 은 `RANKING`·`SCORE` **둘만 유효**, REVIEW/RATING/NEWEST 등은 400 (2026-08-04 전수 실측).
- 가격 서버 필터는 미발굴 → `max_price` 는 **후필터**(번개장터 region 후필터 선례).

### type=gigs — GET /gig/v2/gigs/search
- 필수급 파라미터(빠지면 400): `keyword, q(동일값), isPrime/isFastReaction/isCompany/isNowContactable/hasPortfolios=false, includeAggregations, page, perPage, sortType, service=web, rootCategoryId/subCategoryId/thirdCategoryId="null"`(문자열 null).
- `perPage` 최대 40 실측. 응답: `totalItemCount, lastPage, gigs[]` — gigId·title·price·seller{nickname,grade,isAvailableTax}·review{reviewAverage,reviewCount}·category·images[].
- 서비스 URL = `kmong.com/gig/{gigId}` (실측 200).

### type=experts — GET /seller-profile/v2/seller-profiles/search
- 파라미터: `keyword, isFastReaction/isCompany/isResident/hasPortfolios=false, sortType, page, perPage, includeAggregations`.
- 응답: `sellerProfilePage.items[]` — 각 항목 `{seller, gig(대표 서비스), portfolio}`. seller 에 description(자기소개 전문)·satisfactionPoint·averageResponseTimesInMinutes·ordersCount·portfoliosCount·specialties[]·skills[]·careerInfo.totalCareerYear·activityArea·review.
- 프로필 URL = `kmong.com/@{닉네임}` (실측 200). ★`/seller/{userId}`·`/expert/{userId}` 는 404.

### 부속 API (미어휘화, 필요 시 참조)
- 연관 키워드: `GET /search/v1/search?keyword=&keywordsLimit=8`
- 포트폴리오 추천: `GET /gig/v1/gigs/search/recommend/portfolios?keyword=`
- 카테고리 트리: `GET /category/v1/global-navigation-bar`

## 자주 하는 실수
1. **rootCategoryId 등을 빼고 호출** — 400 "요청한 값이 올바르지 않습니다". 문자열 `"null"` 로라도 채워야 한다.
2. **HTML 을 긁어서 파싱 시도** — 데이터가 없다. API 로.
3. **평점순 정렬 요청** — 서버에 없다. 평점 정렬이 필요하면 limit 크게 받아 `[table:sort]{by: ...}` 후처리.
4. 전문가 프로필 URL 을 userId 로 조립 — 404. **닉네임**으로 `@{nickname}`.
5. 비공식 API 라 **스키마 변경 가능** — 실패 시 이 가이드의 파라미터 목록부터 재실측.
