# 새 상품 가격비교 검색 가이드 (`[sense:search_shopping]`)

새 상품의 후보와 표시 가격을 확인한다. 다나와(기본)·에누리 중 원천을 선택한다.
중고 매물은 `[sense:used]`, 외주·프리랜서는 `[sense:freelance]`를 사용한다.

**제품 추천·구매처 비교는 가격비교 두 곳만으로 끝나지 않는다.** 먼저
[구매 지도](web_landmarks.md#한국에서-구매할-제품을-찾을-때)에서 목적에 맞는 채널을 고른다.
제조사·판매처·후기·홈쇼핑·해외 대안은 기존 `search`·`crawl`·`browser`로 확인한다.
이 지도는 검토 후보이며 모든 채널의 의무 순회나 접근 성공 보증이 아니다.

## 원천과 범위

| site | 수집 경로 | 지원 범위 |
|---|---|---|
| `danawa` (기본) | 공개 검색 HTML의 상품 카드 | 기본 정렬, `page=1..100` |
| `enuri` | 공개 검색의 JSON-LD 상품 목록 | 기본 정렬 첫 페이지 (`page=1`) |
| `naver` | 종료 안내 | `source_retired` 오류 |

두 원천 모두 API 키가 필요 없다. HTTP와 표준 라이브러리 파서를 사용하며,
`curl_cffi`가 없는 폰에는 `urllib` 폴백이 있다. 다나와 HTTP 실패 시 PC에서는
Playwright로 같은 조회 범위와 파서를 재시도한다. 기본 진입점이 상품 없는 셸을 반환하면 먼저 같은 첫 페이지를 명시해 한 번 재조회한다. 폰에서 브라우저 폴백이 불가능하면 실패를 보존한다.

- `query`: 상품명·모델명. 필수.
- `limit`: 해당 페이지에서 반환할 개수, 1..40, 기본 5. `display`는 별칭.
- `page`: 다나와 원천의 40개 단위 페이지. `limit=5,page=2`는 전체 6번째 상품부터가 아니다.
- `sort`: `default`만 지원. 원천 기본 순서를 보존한다. 정렬 옵션을 붙인 다나와 URL은 일부 검색어에서 상품 없는 셸을 반환해 지원하지 않는다.
- 에누리의 다른 페이지·정렬은 `unsupported_option` 오류다. 조용히 첫 페이지로 대체하지 않는다.

```ibl
[sense:search_shopping]{query:"밥솥", limit:10}
[sense:search_shopping]{query:"밥솥", site:"danawa", page:2, limit:10}
[sense:search_shopping]{query:"밥솥", site:"enuri", limit:10}
```

두 곳을 확인하려면 기존 병렬 조합을 쓴다. 새 상품과 중고를 섞던 옛 `site=all`은 되살리지 않는다.

```ibl
[sense:search_shopping]{query:"밥솥", site:"danawa", limit:10}
& [sense:search_shopping]{query:"밥솥", site:"enuri", limit:10}
```

두 결과에서 같은 모델은 모델명을 확인해 묶고 출처는 각각 남긴다. 한 원천의 실패를
다른 원천의 성공으로 감추지 않는다. 검색 범위와 실제 확인하지 못한 채널을 보고한다.

## 결과를 읽는 법

통화는 `{items:[...], total, source, query, page, sort, source_url, observed_at}`.
`total`은 **반환 건수**이며 시장 전체 상품 수가 아니다. `page_items`는 파싱된 해당 페이지
상품 수다. `source_url`·UTC `observed_at`은 실제 조회 주소와 관측 시각이다.

각 상품에는 `name`, `price`, `mall`, `link`, `image`, `category`, `site`, `spec`이 있다.
에누리는 스펙 요약을 제공하지 않으며, 원천에 있으면 상품 ID·판매처 수·평점·리뷰 수를 보존한다.
`mall`은 가격비교 서비스 이름이므로 실제 판매처로 오해하지 않는다.

- `price`: 콤마 없는 숫자 문자열. 없거나 0·문의·품절 등 판독할 수 없는 가격은 **null**.
- `currency`: 관측 통화. `price_status`: `observed` 또는 `unknown`.
- `price_basis`: 에누리 집계 최저가는 `aggregate_low`, 그 밖의 표시는 `listed`.
- `shipping_included`: 확인하지 못했으므로 null. 배송 포함으로 추정하지 않는다.
- `rental_hint`: 제목의 렌탈·렌트 단서. false여도 일시불 구매 조건을 보증하지 않는다.

**표시 가격은 구매 총액이 아니다.** 옵션·배송비·쿠폰·회원 조건·렌탈 월 납부액은
판매처 원문에서 확인한다. 가격 미확인은 무료 상품으로 취급하거나 가격순 맨 앞에 놓지 않는다.

## 빈 결과와 실패

- 원천이 명시한 빈 목록만 `empty_reason:no_results`로 반환한다.
- HTTP 오류는 `http_error`, 목록 구조를 확인하지 못하면 `source_changed`다.
- 일부 상품 구조가 깨지면 유효한 상품을 보존하고 `truncations(scope:source)`로 불완전함을 알린다.
- 에누리의 추천 상품은 검색 결과가 아니다. 검색어와 일치하는 ItemList만 읽는다.
- 다나와는 상품 카드 안에서만 가격을 읽어 다음 상품·푸터의 가격을 잘못 붙이지 않는다.

## 종료된 경로

네이버 쇼핑 검색 API는 **2026-07-31 종료**됐다.
[공식 종료 공지](https://developers.naver.com/notice/article/32564)를 기준으로 하며,
남아 있는 옛 API 문서나 키를 근거로 복구를 시도하지 않는다.
네이버 웹 검색·쇼핑 페이지의 접근 가능성은 별도 문제이며 이 액션의 지원 원천에 포함되지 않는다.

옛 `site=used/all`은 2026-08-04 은퇴했다. 중고 스크래퍼를 복구하지 말고
[중고 검색 가이드](used_market.md)의 `[sense:used]`를 쓴다. 기존 직접 호출의 알 수 없는
site 값은 다나와 결과에 안내를 붙이는 호환 경로가 있지만, 새 IBL에서는 명시된 enum을 사용한다.
