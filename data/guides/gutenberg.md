# Project Gutenberg 가이드

저작권이 만료된 7만 6천여 권의 고전 문학·철학·과학 텍스트를 무료로 검색·다운로드한다. Gutendex REST API(`gutendex.com/books`) 기반.

## 액션

```
[sense:gutenberg_books]{query: "검색어", ...옵션}
```

핸들러: `culture` 패키지의 `gutenberg_search`.

## 파라미터

| 파라미터 | 타입 | 설명 |
|---|---|---|
| `query` | string | 도서 제목·저자·키워드 (영문 권장) |
| `topic` | string | 주제 필터 (예: `philosophy`, `children`, `science`) |
| `author_year_start` | int | 저자 출생/사망 연도 시작 (예: 1800) |
| `author_year_end` | int | 저자 출생/사망 연도 끝 (예: 1900) |
| `languages` | string | 언어 코드 쉼표 구분 (기본 `en`, 예: `en,fr`) |

- 한국어 작품은 거의 없음. 동양 고전 원전은 한국고전종합DB(`korean_classics_search`)나 별도 검색으로 보완.
- 모든 파라미터 선택. `query` 없이 `topic`만 줘도 동작.

## 응답 구조

각 결과(`results` 배열, 최대 10개)에 다음 필드:

```
{
  "id": 1342,
  "title": "Pride and Prejudice",
  "authors": ["Austen, Jane"],
  "subjects": ["England -- Fiction", "Love stories"],
  "languages": ["en"],
  "text_url": "https://www.gutenberg.org/files/1342/1342-0.txt",
  "html_url": "https://www.gutenberg.org/files/1342/1342-h/1342-h.htm",
  "download_count": 38421
}
```

전체 응답에는 `count`(총 결과 수), `next`/`previous`(페이지 URL)도 포함.

## 사용 예시

### 1) 제목으로 검색
```
[sense:gutenberg_books]{query: "pride and prejudice"}
```

### 2) 저자 + 언어 한정
```
[sense:gutenberg_books]{query: "shakespeare", languages: "en"}
```

### 3) 주제 + 연도 필터
```
[sense:gutenberg_books]{topic: "philosophy", author_year_start: 1700, author_year_end: 1800}
```

### 4) 원문 다운로드 후 분석 (파이프라인)
```
[sense:gutenberg_books]{query: "moby dick"}
# 결과의 text_url을 받아서:
[sense:web_get]{url: "<text_url>"} >> [self:write]{path: "/tmp/moby.txt", content: "<원문>"}
```
긴 원문은 한 번에 컨텍스트에 넣지 말고 파일로 저장 후 필요한 부분만 `[self:read]`.

## 활용 팁

- **검색어는 영문**: API는 영문 메타데이터 위주. 한글 검색은 거의 안 맞음.
- **다운로드 카운트**: 인기 도서를 먼저 보고 싶다면 결과에서 `download_count` 큰 순으로 정렬.
- **포맷 선택**: `text_url`(plain text, 분석·요약용)과 `html_url`(읽기·인용용) 중 목적에 맞게.
- **API 제한**: 공식 rate limit은 명시 안 됐지만 분당 수십 회 이상 호출 자제.
- **저작권**: Project Gutenberg 도서는 미국 저작권 만료 기준. 국가별 저작권법은 별도 확인.

## 관련 액션

- `sense:korean_classics_search` — 한국고전종합DB (한문 원전)
- `sense:search_books` — 글로벌 도서 일반 검색
- `sense:book` — 한국 도서 (도서관정보나루)
