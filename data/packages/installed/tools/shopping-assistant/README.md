# 상품·중고

[sense:search_shopping]으로 새 상품 가격을 비교하고 [sense:used]로 중고 매물을 찾습니다.

예: `[sense:search_shopping]{query: "노트북"}`

외주 검색 [sense:freelance]는 freelance-services 묶음에서 선택합니다.

다나와 검색은 공개 검색 진입점의 기본 정렬을 사용하며, 기본값은 첫 페이지입니다. `page`로 페이지를 선택하고 `limit`만큼 반환합니다. 반환 `total`은 받은 항목 수이며 시장 전체 상품 수가 아닙니다. 정상 0건과 요청 실패·페이지 구조 미확인은 구분합니다.
