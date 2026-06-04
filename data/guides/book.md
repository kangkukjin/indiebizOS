# 한국 도서 검색 가이드

`[sense:book]{op}` 으로 도서관정보나루(국립중앙도서관 공식 통계 API) 도서를 조회한다 (2026-06-03 op 분기로 통합).

| op | 설명 | 주요 파라미터 |
|----|------|--------------|
| `search` (기본) | 도서 검색·조회 (필드분기·ISBN·대출통계) | title/author/publisher/keyword/isbn/detail |
| `recommended` | 추천도서 (마니아·다독자 패턴) | isbn13, rec_type(mania 기본/reader) |
| `codes` | 분류 코드 목록 | code_type(kdc 또는 region) |

다른 도서 액션과 구분:
- **이 액션(book)**: 한국 출판 도서 (메타 + 대출 통계 + 추천)
- `sense:search_books` — 글로벌 도서 (Google Books, 영어권·원서)
- `sense:classic`{op:"western"} — 서양 고전 원문 (Project Gutenberg)
- `sense:classic`{op:"korean"} — 한국 고전 원문 (한국고전종합DB)

---

## op=search 입력 모드 (기본, op 생략 가능)

필드/ISBN으로 분기:

| 모드 | 호출 | 결과 |
|---|---|---|
| **필드 검색** | `title:"하네스"` / `author:"…"` / `publisher:"…"` | 해당 필드 매칭 도서 목록 |
| **광역 검색** | `keyword:"하네스"` | 제목+저자+출판사 통합 검색 |
| **ISBN 기본 조회** | `isbn:"9788936434267"` | 단일 도서 메타데이터 |
| **ISBN 상세 + 대출통계** | `isbn:"9788936434267", detail:true` | 메타 + 대출 추이·연령대·성별 통계 |

제목만 안다면 `title`로 좁혀라(정확도↑). 기본값: `detail:false`.

## op=recommended / op=codes
```
[sense:book]{op:"recommended", isbn13:"9788936434267"}       # 마니아 추천 (rec_type:"reader"면 다독자)
[sense:book]{op:"codes", code_type:"kdc"}                     # KDC 주제분류 코드
[sense:book]{op:"codes", code_type:"region"}                  # 도서관 지역 코드
```

---

## 파라미터

| 키 | 필수 | 설명 |
|---|---|---|
| `keyword` | (둘 중 하나) | 제목·저자·출판사 검색어 (자연어 가능) |
| `isbn` | (둘 중 하나) | ISBN13 (10자리도 일부 지원). 하이픈은 안 넣음 |
| `detail` | (옵션) | ISBN 조회 시 true면 대출 통계 포함 |
| `rows` | (옵션, 기본 10) | keyword 검색 시 반환 건수 |

`keyword`와 `isbn`이 같이 들어오면 **isbn 우선**.

---

## 표준 워크플로우

### 1) 자연어로 책 찾기
```
[sense:book]{keyword:"하네스 노동"}
→ 후보 목록에서 ISBN 확보
```

### 2) ISBN 알 때 기본 조회
```
[sense:book]{isbn:"9788936434267"}
→ 단일 도서 메타 (제목·저자·출판사·발행연도·분류 등)
```

### 3) 대출 통계 포함 상세 조회
```
[sense:book]{isbn:"9788936434267", detail:true}
→ 메타 + 대출 추이(월별) + 연령대 분포 + 성별 분포
```

### 4) 키워드로 찾고 → 상세 깊게 보기 (2단계)
```
[sense:book]{keyword:"하네스 노동", rows:5}
→ ISBN 추출
[sense:book]{isbn:"...", detail:true}
```

### 5) 분야별 다량 탐색
```
[sense:book]{keyword:"인공지능 윤리", rows:30}
```

---

## 활용 패턴

### 강의/출판용 참고문헌 모으기
강의/책 작업 중 인용·참고문헌 필요 시 자연어 키워드로 후보를 모아 ISBN을 확보. 그 후 도서관·온라인 서점에서 직접 확인.

### 시장 반응 추정 (대출 통계)
신간이라면 발행 후 6~12개월 대출 통계로 대중 반응을 가늠. detail 모드의 월별 추이가 핵심.

### 한국 vs 해외 도서 구분
영어권 도서는 이 액션으로 안 잡힌다. 글로벌 검색은 `sense:search_books`(있으면)나 외부 채널.

---

## 자주 하는 실수

- **ISBN 하이픈**: `978-89-364-3426-7` 같이 하이픈 포함은 일부 케이스에서 실패. 숫자만 권장.
- **detail은 ISBN 모드에서만**: keyword 검색에 detail:true 줘도 무시됨. ISBN 확보 후 호출.
- **rows 큰 값**: 100 이상은 API 측 제한이나 응답 느림. 20~30 적정.
- **도서관정보나루는 한국 책 위주**: 외국 책 검색은 매칭 거의 없음.

## 관련

- `sense:classic`{op:"western"} — Project Gutenberg 영문 고전 원문
- `culture` 패키지 한국고전종합DB — 한문 고전
- `sense:search_books` (있다면) — 글로벌 도서 일반 검색
