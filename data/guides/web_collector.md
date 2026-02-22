# Web Collector 사용 가이드

## 개요

웹사이트에서 정보를 수집하고 DB에 축적하는 프레임워크.
**사이트별 가이드**가 핵심 — 어디서 뭘 어떻게 찾고, 찾은 데이터를 어떻게 저장할지 정의.

실제 브라우저 탐색은 **browser-action 도구**가 담당하고,
web-collector는 **가이드 제공 + DB 저장/조회**만 담당한다.

## 핵심 원칙

1. **DB 먼저, 탐색은 나중에**: 사용자가 질문하면 wc_query로 DB부터 확인. 데이터가 있으면 탐색하지 않음
2. **가이드 먼저 읽기**: browser-action으로 사이트를 탐색하기 전에 반드시 wc_sites(action="info")로 가이드를 확인
3. **찾으면 바로 저장**: browser-action으로 데이터를 수집했으면 wc_save로 즉시 DB에 저장
4. **가이드는 한 번 만들면 재사용**: 사이트 가이드를 등록해두면 다음부터는 가이드만 참조하면 됨

## 도구 3개

### wc_sites — 사이트 가이드 관리
| action | 설명 | 필요 파라미터 |
|--------|------|--------------|
| list | 등록된 사이트 목록 | - |
| info | 사이트 가이드 상세 (검색 방법, 필드 정의, 해석법) | site_id |
| register | 새 사이트 가이드 등록 (guide_code 없으면 템플릿 반환) | guide_code |

### wc_save — 수집 데이터 DB 저장
| 파라미터 | 설명 |
|---------|------|
| site_id | 사이트 ID (필수) |
| items | 저장할 데이터 목록 (필수, list[dict]) |

### wc_query — DB 조회
| action | 설명 | 필요 파라미터 |
|--------|------|--------------|
| search | FTS5 전문 검색 | query, (site_id) |
| stats | 수집 통계 | (site_id) |
| recent | 최근 수집 항목 | (site_id), limit |
| detail | 항목 상세 | item_id |
| delete | 항목 삭제 | item_id |

## 워크플로우

### 패턴 1: 등록된 사이트에서 정보 수집

```
사용자: "법원경매에서 충북 아파트 경매 있어?"

1. wc_sites(action="list")
   → "courtauction" 사이트가 있는지 확인

2. wc_query(action="search", query="충북 아파트", site_id="courtauction")
   → DB에 데이터가 있으면 그걸로 응답 (탐색 안 함)

3. DB에 없거나 최신 데이터 필요하면:
   a) wc_sites(action="info", site_id="courtauction")
      → 가이드 읽기: 검색 방법, 필드 구조, 해석법
   b) 가이드에 따라 browser-action 도구로 사이트 탐색:
      - browser_navigate("https://www.courtauction.go.kr")
      - browser_snapshot() → 검색 입력란 찾기
      - browser_type(ref="...", text="충북 아파트")
      - browser_click(ref="...(검색 버튼)")
      - browser_get_content() → 결과 텍스트 추출
   c) 추출한 데이터를 가이드의 fields 정의에 맞게 구조화
   d) wc_save(site_id="courtauction", items=[{...}, {...}])
      → DB에 저장 (key_field 기준 중복 자동 제거)

4. 가이드의 해석법에 따라 사용자에게 결과 보고
```

### 패턴 2: 새 사이트 등록

```
사용자: "온비드에서 공매 물건 찾아줘"

1. wc_sites(action="list") → "onbid" 사이트 없음

2. 사용자에게 알림:
   "온비드 가이드가 아직 없습니다. 사이트를 분석해서 등록할까요?"

3. 승인 받으면:
   a) browser-action으로 사이트 구조 탐색
      - 검색 폼, 결과 목록 구조, 필드 파악
   b) wc_sites(action="register") → 템플릿 확인
   c) SITE_CONFIG 작성 (id, name, url, key_field, fields, guide)
   d) wc_sites(action="register", guide_code=코드)
   e) 바로 browser-action으로 검색 실행 + wc_save
```

### 패턴 3: 축적된 데이터 분석

```
사용자: "지난달 대비 오송 경매 건수가 늘었어?"

1. wc_query(action="stats", site_id="courtauction")
   → 수집 이력 확인

2. wc_query(action="search", query="오송", site_id="courtauction")
   → 축적된 데이터에서 시기별 분석

3. 필요하면 browser-action으로 최신 데이터 추가 수집 → wc_save

4. DB 데이터만으로 추세 분석
```

## 사이트 가이드 작성법

### 가이드란
특정 웹사이트를 위한 작은 Python 파일. SITE_CONFIG dict 하나만 있으면 됨.
코드(함수)는 없고, 설정과 텍스트 가이드만 포함.

### SITE_CONFIG 구조

```python
SITE_CONFIG = {
    "id": "site_id",           # 파일명과 동일
    "name": "사이트 이름",      # 사용자에게 보여줄 이름
    "url": "https://...",       # 시작 URL
    "description": "설명",
    "key_field": "case_no",     # 중복 제거 기준 필드 (매우 중요!)
    "fields": {                 # 수집할 데이터 필드 정의
        "case_no": {"type": "text", "label": "사건번호"},
        "location": {"type": "text", "label": "소재지"},
        "price": {"type": "text", "label": "가격"},
    },
    "search_params": {          # 검색 시 사용자가 지정할 수 있는 파라미터
        "region": {"type": "text", "label": "지역"},
    },
    "guide": """
    여기에 AI가 참조할 모든 지침을 작성.
    검색 방법, 결과 추출법, 저장 규칙, 해석법 등.
    """
}
```

### key_field가 중요한 이유
- DB에서 같은 항목을 식별하는 기준
- 예: 경매라면 "사건번호", 상품이라면 "상품코드", 게시글이라면 "URL"
- 이 필드가 같으면 기존 데이터를 업데이트 (새로 추가하지 않음)
- wc_save 시 모든 항목에 반드시 포함되어야 함

### guide 필드 작성 요령

가이드는 AI 에이전트가 browser-action으로 사이트를 탐색할 때의 "매뉴얼"이다.
다음 내용을 포함:

1. **검색 방법**: 단계별 탐색 지침 (어디를 클릭, 뭘 입력, 어디서 결과 확인)
2. **결과 추출**: 결과 페이지 구조 (테이블 열 순서, 카드 구조 등)
3. **데이터 저장**: key_field 규칙, 필드 정규화 (가격 포맷, 날짜 포맷 등)
4. **데이터 해석**: 핵심 지표, 상태 코드 의미, 유효기간
5. **참고사항**: 사이트 특이사항 (팝업, iframe, 로딩 지연 등)

## DB 저장 규칙 (wc_save)

### 필드 정규화 원칙
- **가격**: 숫자만 남기기 (쉼표, "원", "만원" 등 제거)
- **날짜**: YYYY-MM-DD 또는 YYYY.MM.DD 통일
- **key_field**: 공백 제거, 빈 값 불가
- **텍스트**: 앞뒤 공백 제거

### 중복 처리
- site_id + key_field 값이 같으면 기존 데이터를 업데이트
- 새 데이터의 필드가 기존 데이터와 병합됨 (새 값이 우선)
- 빈 문자열("")은 기존 값을 덮어쓰지 않음

### items 예시
```json
[
  {
    "case_no": "2025타경12345",
    "location": "충북 청주시 흥덕구 오송읍",
    "usage": "아파트",
    "appraisal_price": "350000000",
    "minimum_price": "224000000",
    "auction_date": "2025.03.15",
    "status": "진행중"
  }
]
```
