# 숙박·단기임대 검색 (기술 참조) — [sense:stay]

> 2026-07-13 신설. 국내 숙박의 3층 구조를 source 하나로 통합 (realty의 molit/zigbang/naver 3분업 선례).

## 소스 3분업

| source | 무엇 | 가격 | 강점 |
|--------|------|------|------|
| `goodchoice` (기본) | 여기어때 실시간 예약 재고 | 날짜별 할인가 | 호텔·모텔·펜션·게스트하우스, 평점·리뷰수 |
| `33m2` | 삼삼엠투 한 달 살기 | 주간요금(usingFee) | 단기임대 전문, 주단위 계약, 서버측 가격필터 |
| `tourapi` | 관광공사 공식 숙박 디렉토리 | **없음** | 권위 목록·연락처·한옥 등 등록업소 전수 |

**해외 호텔은 `[sense:travel]{op: "hotel"}`** (Amadeus) — stay는 국내 전용.

## 사용법

```
[sense:stay]{region: "제주"}                                          # 여기어때 호텔 (기본)
[sense:stay]{region: "제주", checkin: "2026-08-10", checkout: "2026-08-11", personal: 4}
[sense:stay]{region: "강남", type: "motel", max_price: 80000}         # 1박 8만원 이하 모텔
[sense:stay]{source: "33m2", region: "평택", max_week_fee: 300000}    # 주 30만 이하 한달살기
[sense:stay]{source: "tourapi", region: "경주 한옥"}                   # 공식 디렉토리 키워드검색
[sense:stay]{source: "tourapi", region: "제주"}                        # 광역명이면 지역 전체목록
```

- type (goodchoice 전용): `hotel`(기본)/`motel`/`pension`/`camping`/`guesthouse`
- 통화: items[{title, meta, summary, url, image, lat, lng, price|week_fee}] + map_data — `>> [table:sort]{by: "price"}` 등 파이프 가능

## 내부 구현 레퍼런스 (함정 포함)

### goodchoice = yeogi.com (여기어때)
- ★**레거시 goodchoice.kr URL 금지**: `goodchoice.kr/product/search/{cat}` 은 yeogi.com 으로 리다이렉트되며 **keyword 를 떨어뜨리고 '서울'로 고정**한다(실측). 반드시 `https://www.yeogi.com/domestic-accommodations` 직접 호출.
- 파라미터: `searchType=KEYWORD, keyword, category, checkIn, checkOut, personal, page`. 날짜별 요금·페이지네이션(paginationInfo.totalCount) 서버 반영 실측 확인.
- 카테고리 코드(1~12 전수 실측): 1=모텔 / 2=호텔·리조트 / 3=펜션 / 5=캠핑·글램핑 / 6=게스트하우스. ★**4와 7 이상은 서버가 무시하고 "전체" 반환** — 잘못 매핑하면 타입 필터가 조용히 풀린다(첫 구현이 게하=7로 이 함정에 걸렸음).
- 데이터: `__NEXT_DATA__` SSR 임베드 → `props.pageProps.domesticList.body.items[]`. 가격은 `room.stay.price.discountTotalPrice || discountPrice`, 정가 `strikePrice`.
- TLS 지문 봇탐지 대비 curl_cffi `impersonate="chrome"` (naver부동산 선례).
- 상세 URL: `yeogi.com/domestic-accommodations/{meta.id}`.

### 33m2 (삼삼엠투)
- `GET https://api.33m2.co.kr/v1/rooms` — **키·인증 불요** 공개 JSON. ★`page`는 **1부터**(0이면 VLD_001).
- 파라미터: `keyword, size, page, sortBy=POPULAR, minUsingFee/maxUsingFee(원, 서버필터), startDate/endDate, propertyTypes`.
- 응답: `data.rooms.content[]` — rid·roomName·usingFee(주간)·mgmtFee·pyeongSize·lat/lng·longtermDiscountPer·isSuperHost.
- 전체 건수는 별도 `GET /v1/rooms/count` → `data.roomCount`.
- 상세 URL: `33m2.co.kr/room/detail/{rid}` (★`/room/{rid}`는 404). 이미지 CDN: `d1pviohoskiraj.cloudfront.net/{picMain}`.

### tourapi (한국관광공사 TourAPI 4.0)
- `DATA_GO_KR_API_KEY` 사용 (공공데이터포털 활용신청 완료 2026-07-13).
- 광역명(서울/부산/제주 등 17개)이면 `areaBasedList2?areaCode=`, 그 외 키워드는 `searchKeyword2?keyword=`. 둘 다 `contentTypeId=32`(숙박).
- ★키워드 검색은 **업소명 매칭**이라 좁다("경주 한옥"=1건). 지역 전수는 광역명으로.
- 가격·예약가능 여부 없음 — 디렉토리 역할만. 가격이 필요하면 goodchoice 로.
- ★상세 링크: visitkorea `ms_detail.do?cotid=`의 cotid는 **별도 GUID 체계**라 TourAPI contentid로 조립 불가(200이 오지만 빈 페이지) → 업소명 **검색 링크**(`search_list.do?keyword=`)로 안내.

## 자주 하는 실수
1. **국내인데 `[sense:travel]{op:"hotel"}`** — Amadeus test 는 국내 커버리지가 없다시피 함(부산 5건). 국내는 stay.
2. **33m2 page=0** — 1부터 시작.
3. **goodchoice.kr 도메인으로 호출** — keyword 가 무시되고 서울 결과가 온다. yeogi.com 직접.
4. **tourapi 로 가격 질문에 답** — 가격 없음. 가격은 goodchoice/33m2.
5. 여기어때 날짜 미지정 시 **오늘 1박** 기준가가 온다 — 사용자가 날짜를 말했으면 반드시 checkin/checkout 전달.
6. **매진 숙소는 price가 없다**(soldOut "다른 날짜 확인") — 목록엔 "매진" 표기로 포함되지만, max_price 지정 시엔 제외된다.
7. 여기어때에 **초단기 다발 호출은 일시 실패** 가능(스로틀 추정) — 서킷브레이커가 8초 차단 후 자동 회복. 재시도로 해결.
