# 상품·중고

[sense:search_shopping]으로 새 상품 가격을 비교하고 [sense:used]로 중고 매물을 찾습니다.

예: `[sense:search_shopping]{query: "노트북"}`

외주 검색 [sense:freelance]는 freelance-services 묶음에서 선택합니다.

다나와 검색은 공개 검색 진입점의 기본 정렬을 사용하며, 기본값은 첫 페이지입니다. `page`로 페이지를 선택하고 `limit`만큼 반환합니다. 반환 `total`은 받은 항목 수이며 시장 전체 상품 수가 아닙니다. 정상 0건과 요청 실패·페이지 구조 미확인은 구분합니다.

다나와의 새 페이지는 검색어·페이지 번호가 일치하는 공개 `productList` 상태를 읽습니다.
광고·추천 목록은 섞지 않고, 검색 건수가 있는데 상품 목록이 비어 있는 응답은 확인 실패로
처리합니다. 구형 상품 카드도 지원하며 HTTP·브라우저 경로가 같은 파서를 사용합니다.
브라우저에 완성된 검색 상태가 있으면 옛 HTML 선택자를 기다리지 않습니다.
에누리는 검색어가 일치하는 JSON-LD 목록의 공식 `price.enuri.com/catalog/…`와
`www.enuri.com/detail.jsp?modelno=…` 상품 주소를 지원합니다.
