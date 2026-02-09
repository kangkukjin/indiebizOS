# Web 패키지 가이드

## 도구 선택 가이드

### ddgs_search
- 웹 검색 (DuckDuckGo 기반)
- 일반적인 정보 검색에 사용

### crawl_website
- 특정 URL의 페이지 내용 읽기
- 정적 HTML만 처리 가능 (JavaScript 렌더링 불가)
- `max_length` 기본값 10000
- 로그인이 필요한 페이지는 접근 불가

### google_news_search
- 뉴스 검색 전용
- API 키 불필요
- 최신 뉴스 기사 검색에 최적

### generate_newspaper
- 키워드 기반 신문 형태 콘텐츠 생성
- AI 토큰을 소비하지 않음
- 여러 키워드를 동시에 처리 가능

### launch_sites
- 즐겨찾기 사이트 관리 및 열기
- action 종류:
  - `open_ui` - 즐겨찾기 관리 UI 열기
  - `open_all` - 모든 즐겨찾기 사이트 한번에 열기
  - `list` - 등록된 사이트 목록 조회
  - `add` - 새 사이트 추가
  - `remove` - 사이트 제거

---

## 다른 패키지와의 관계

### 음식점/맛집 검색
- web 패키지가 아닌 `location-services` 패키지의 `search_restaurants` 사용

### 동적 페이지 / 로그인 필요 페이지
- `crawl_website`로 처리 불가
- `browser-action` 패키지 사용 (Playwright 기반 브라우저 자동화)

---

## 일반적인 워크플로우

1. `ddgs_search`로 관련 페이지 검색
2. 검색 결과에서 원하는 URL 확인
3. `crawl_website`로 해당 URL의 상세 내용 가져오기

---

## crawl_website 제한사항

- 정적 HTML만 처리 가능
- JavaScript로 동적 렌더링되는 콘텐츠는 가져올 수 없음
- 로그인이 필요한 페이지 접근 불가
- `max_length` 기본값 10000 (초과분은 잘림)
