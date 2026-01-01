# Web Search 도구

## 목적

AI 에이전트가 웹에서 정보를 검색할 수 있게 합니다.
설치 후 에이전트는 "최신 뉴스 검색해줘", "OOO에 대해 찾아봐" 같은 요청을 처리할 수 있습니다.

## 이 도구가 제공하는 것

- **웹 검색**: 키워드로 웹 검색하여 결과 반환
- **뉴스 검색**: 최신 뉴스 기사 검색
- **무료 API**: API 키 없이 사용 가능 (DuckDuckGo)

## 도구 vs 확장

이것은 **도구(Tool)**입니다. 시스템 확장이 아닙니다.

- 시스템 전체가 아닌 **개별 에이전트**가 사용
- 에이전트의 **allowed_tools**에 추가해야 사용 가능
- AI의 **tool use** 기능으로 호출됨

## 설치 시 필요한 변경사항

### 1. 도구 정의 등록

AI가 이 도구를 호출할 수 있도록 도구 정의를 등록해야 합니다.

도구 정의 예시:
```json
{
  "name": "web_search",
  "description": "웹에서 정보를 검색합니다. 키워드를 입력하면 관련 웹페이지 목록을 반환합니다.",
  "input_schema": {
    "type": "object",
    "properties": {
      "query": {
        "type": "string",
        "description": "검색할 키워드"
      },
      "count": {
        "type": "integer",
        "description": "결과 개수 (기본: 5)",
        "default": 5
      }
    },
    "required": ["query"]
  }
}
```

### 2. 도구 실행 로직

AI가 도구를 호출하면 실제로 검색을 수행하는 로직이 필요합니다.

- tool_use 응답에서 도구 이름과 파라미터 추출
- 검색 API 호출 (DuckDuckGo, Google 등)
- 결과를 AI에게 반환

### 3. 에이전트 설정

에이전트가 이 도구를 사용할 수 있도록 설정해야 합니다.

- 에이전트 설정 UI에서 도구 선택 가능
- allowed_tools 목록에 "web_search" 추가
- 또는 자동 도구 배분 시스템에서 할당

## 참고 구현

이 폴더의 파일들은 Python + DuckDuckGo 구현 예시입니다.

```
tool_ddgs_search.py   - DuckDuckGo 웹 검색
tool_google_news.py   - Google News 검색 (DuckDuckGo 경유)
```

### 핵심 함수
```python
def search_web(query: str, count: int = 5) -> dict:
    """
    웹 검색 수행

    Returns:
        {
            "success": True,
            "results": [
                {"title": "...", "url": "...", "snippet": "..."},
                ...
            ]
        }
    """
```

### 의존성 (Python 구현)
```bash
pip install duckduckgo-search
```

이 코드를 그대로 사용하지 말고, 현재 시스템에 맞게 구현하세요.

## 다른 검색 옵션

DuckDuckGo 외에도 다양한 검색 방법이 있습니다:

### Google Custom Search API
- 더 정확한 결과
- API 키 필요 (유료)
- 일일 할당량 제한

### Bing Search API
- Microsoft Azure 계정 필요
- 유료

### SearXNG
- 오픈소스 메타 검색 엔진
- 자체 호스팅 가능
- 개인정보 보호

시스템 요구사항에 맞는 것을 선택하세요.

## 설치 완료 확인

- [ ] 에이전트 설정에서 web_search 도구 선택 가능
- [ ] 에이전트에게 "OOO 검색해줘" 요청 시 검색 결과 반환
- [ ] 검색 결과에 제목, URL, 설명이 포함됨
