# 신문/잡지 생성 도구

## 목적

에이전트가 뉴스를 수집하여 신문이나 잡지 형태의 HTML 문서를 만들 수 있게 합니다.
특정 주제에 대한 뉴스를 모아 보기 좋게 편집된 형태로 출력합니다.

## 이 도구가 제공하는 것

- **뉴스 수집**: 키워드로 최신 뉴스 검색
- **신문 생성**: 여러 뉴스를 신문 레이아웃 HTML로
- **잡지 생성**: 단일 주제 심층 분석 잡지 HTML로
- **시각적 결과물**: 바로 열어볼 수 있는 HTML 파일

## 설치 시 필요한 변경사항

### 1. 도구 함수 구현

**generate_newspaper(keywords, options)**
- 여러 키워드로 뉴스 검색
- 신문 레이아웃 HTML 생성
- 섹션별로 기사 배치

**generate_magazine(topic, options)**
- 단일 주제 심층 뉴스 수집
- 잡지 스타일 HTML 생성
- 커버, 목차, 본문 구성

### 2. 도구 정의

```json
{
  "name": "generate_newspaper",
  "description": "키워드로 뉴스를 검색하여 신문 형태 HTML을 생성합니다",
  "input_schema": {
    "type": "object",
    "properties": {
      "keywords": {
        "type": "array",
        "items": {"type": "string"},
        "description": "검색할 키워드 목록"
      },
      "title": {"type": "string", "description": "신문 제목"},
      "max_articles": {"type": "integer", "description": "최대 기사 수"}
    },
    "required": ["keywords"]
  }
}
```

### 3. 뉴스 검색

뉴스를 가져오는 방법이 필요합니다.

선택지:
- **DuckDuckGo News**: 무료, API 키 불필요
- **Google News RSS**: 무료, 제한적
- **News API**: 유료, 풍부한 기능
- **직접 크롤링**: 사이트별 구현 필요

DuckDuckGo 예시:
```bash
pip install duckduckgo-search
```

### 4. HTML 템플릿

보기 좋은 출력물을 위한 템플릿이 필요합니다.

필요한 템플릿:
- 신문 레이아웃 (다단, 헤드라인)
- 잡지 레이아웃 (커버, 페이지)
- 공통 스타일 (폰트, 색상)

Jinja2 같은 템플릿 엔진 사용:
```bash
pip install jinja2
```

### 5. 출력 관리

생성된 파일을 관리해야 합니다.

- outputs 폴더에 저장
- 날짜/시간 기반 파일명
- 자동으로 브라우저에서 열기 (선택)

## 설계 고려사항

### 이미지 처리
- 뉴스 썸네일 포함 여부
- 이미지 다운로드 vs 외부 링크
- 저작권 주의

### AI 요약
- 긴 기사 요약 (선택)
- AI API 비용 고려
- 요약 없이 원문만 사용 가능

### 스타일 커스터마이징
- 사용자 정의 테마
- 로고 추가
- 색상 변경

## 참고 구현

이 폴더의 파일들은 Python + Jinja2 기반 예시입니다.

```
tool_newspaper.py
├── generate_newspaper()
├── generate_magazine()
├── _search_news()
└── NEWSPAPER_TOOLS (도구 정의)

templates/
├── newspaper.html
└── magazine.html
```

### 의존성 (Python 구현)
```bash
pip install duckduckgo-search jinja2
```

이 코드를 그대로 사용하지 말고, 현재 시스템에 맞게 구현하세요.

## 설치 완료 확인

- [ ] 에이전트가 도구를 호출할 수 있음
- [ ] 키워드로 뉴스 검색 가능
- [ ] 신문 HTML 생성 가능
- [ ] 잡지 HTML 생성 가능
- [ ] 생성된 파일을 브라우저에서 열 수 있음
