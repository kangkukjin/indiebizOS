# 웹 크롤링 도구

## 목적

에이전트가 웹페이지 내용을 읽을 수 있게 합니다.
URL을 주면 해당 페이지의 텍스트 내용을 추출하여 에이전트가 분석하거나 참조할 수 있습니다.

## 이 도구가 제공하는 것

- **페이지 읽기**: URL에서 텍스트 내용 추출
- **HTML → 텍스트 변환**: 깔끔한 마크다운/텍스트로 변환
- **메타데이터 추출**: 제목, 설명 등

## 설치 시 필요한 변경사항

### 1. 도구 함수 구현

웹페이지를 가져와 텍스트로 변환하는 함수가 필요합니다.

**crawl_website(url, options)**
- HTTP 요청으로 페이지 가져오기
- HTML 파싱
- 본문 텍스트 추출
- 마크다운 또는 플레인 텍스트 반환

### 2. 도구 정의

```json
{
  "name": "crawl_website",
  "description": "웹페이지 URL의 내용을 텍스트로 가져옵니다",
  "input_schema": {
    "type": "object",
    "properties": {
      "url": {"type": "string", "description": "크롤링할 URL"},
      "include_links": {"type": "boolean", "description": "링크 포함 여부"}
    },
    "required": ["url"]
  }
}
```

### 3. HTML 처리

페이지에서 유용한 텍스트만 추출해야 합니다.

추출할 것:
- 제목 (title, h1)
- 본문 텍스트 (article, main, body)
- 목록과 표

제거할 것:
- 스크립트, 스타일
- 네비게이션, 푸터
- 광고 영역

### 4. 에이전트 연동

- 도구 정의를 에이전트에 제공
- tool_use 응답 처리
- 결과를 AI에게 전달

## 설계 고려사항

### 요청 제한
- 동일 사이트 연속 요청 시 딜레이
- robots.txt 존중 (선택)
- 타임아웃 설정

### 인코딩
- 다양한 문자 인코딩 처리
- UTF-8이 아닌 페이지 대응

### 동적 페이지
- JavaScript 렌더링이 필요한 페이지는 별도 처리 필요
- 필요시 browser-automation 도구와 연계

### 크기 제한
- 너무 긴 페이지는 요약 또는 잘라내기
- AI 컨텍스트 한도 고려

## 참고 구현

이 폴더의 `tool_crawl.py`는 Python + requests + BeautifulSoup 기반 예시입니다.

```
tool_crawl.py
├── crawl_website()
├── _extract_content()
└── CRAWL_TOOLS (도구 정의)
```

### 의존성 (Python 구현)
```bash
pip install requests beautifulsoup4 html2text
```

이 코드를 그대로 사용하지 말고, 현재 시스템에 맞게 구현하세요.

## 설치 완료 확인

- [ ] 에이전트가 도구를 호출할 수 있음
- [ ] URL에서 텍스트 추출 가능
- [ ] HTML이 깔끔하게 변환됨
- [ ] 한글 페이지도 정상 처리됨
