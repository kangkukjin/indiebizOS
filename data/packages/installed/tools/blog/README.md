# 블로그 도구

## 목적

에이전트가 네이버 블로그를 검색하고 분석할 수 있게 합니다.
특정 주제에 대한 블로그 글을 찾고, 내용을 읽고, 인사이트를 추출합니다.

## 이 도구가 제공하는 것

- **블로그 검색**: 키워드로 네이버 블로그 검색
- **내용 읽기**: 블로그 포스트 본문 추출
- **인사이트 보고서**: AI로 블로그 분석 리포트 생성

## 설치 시 필요한 변경사항

### 1. 도구 함수 구현

**search_blog(keyword, count)**
- 네이버 블로그 검색
- 검색 결과 목록 반환 (제목, URL, 요약)

**get_post_content(url)**
- 블로그 포스트 URL에서 본문 추출
- 텍스트와 이미지 URL 반환

**blog_insight_report(keyword, ai_config)**
- 키워드로 블로그 검색
- 상위 글들을 분석
- AI로 인사이트 보고서 생성

### 2. 도구 정의

```json
{
  "name": "search_blog",
  "description": "네이버 블로그에서 키워드를 검색합니다",
  "input_schema": {
    "type": "object",
    "properties": {
      "keyword": {"type": "string", "description": "검색 키워드"},
      "count": {"type": "integer", "description": "검색 결과 수 (기본: 10)"}
    },
    "required": ["keyword"]
  }
}
```

### 3. 네이버 블로그 크롤링

네이버 블로그는 특수한 구조를 가지고 있습니다.

- iframe 안에 콘텐츠가 있음
- 모바일 버전이 크롤링하기 쉬움
- JavaScript 렌더링이 필요할 수 있음

크롤링 전략:
1. 모바일 URL로 변환 (m.blog.naver.com)
2. 또는 postView URL 직접 접근
3. 본문 영역 파싱

### 4. AI 분석

인사이트 보고서 생성 시 AI가 필요합니다.

- 에이전트의 AI 설정 활용
- 또는 별도 AI 설정 전달
- 프롬프트 설계 필요

## 설계 고려사항

### 네이버 API
- 네이버 검색 API를 사용하면 더 안정적
- API 키가 필요함
- 또는 웹 크롤링으로 대체

### 접근 제한
- 과도한 요청 시 차단될 수 있음
- 딜레이 추가
- User-Agent 설정

### 콘텐츠 권한
- 블로그 내용 저작권 주의
- 분석/참조 목적으로만 사용

## 참고 구현

이 폴더의 `tool_blog.py`는 Python + BeautifulSoup 기반 예시입니다.

```
tool_blog.py
├── search_blog()
├── get_post_content()
├── blog_insight_report()
└── BLOG_TOOLS (도구 정의)
```

### 의존성 (Python 구현)
```bash
pip install requests beautifulsoup4
```

이 코드를 그대로 사용하지 말고, 현재 시스템에 맞게 구현하세요.

## 설치 완료 확인

- [ ] 에이전트가 도구를 호출할 수 있음
- [ ] 키워드로 블로그 검색 가능
- [ ] 블로그 포스트 내용 읽기 가능
- [ ] AI 인사이트 보고서 생성 가능
