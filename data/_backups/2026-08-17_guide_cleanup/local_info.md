# Local Info - 지역 정보 검색 및 DB 관리 가이드

## 개요

동네 가게/상점 정보를 검색하고 개인 DB에 축적하는 도구.
검색할 때마다 가게 이름이 언급된 게시글을 기록하여, **언급 빈도** 자체가 데이터가 됩니다.
많이 언급되는 가게 = 사람들이 많이 가는 가게.

## 핵심 원칙

1. **판단하지 말고 기록만**: 좋은 가게/나쁜 가게를 AI가 판단하지 않음. 빈도가 곧 데이터.
2. **가게는 한 번, 언급은 매번**: 가게 기본정보는 한 번 등록, 게시글은 발견할 때마다 mention으로 쌓음
3. **중복 자동 처리**: 같은 가게, 같은 게시글은 자동 인식하여 중복 저장 안 됨
4. **점진적 축적**: 사용할수록 빈도 데이터가 풍부해짐

## 워크플로우

### 기본 패턴: 검색 → 가게 등록 → 언급 기록

```
1. 사용자: "오송에 괜찮은 미용실 있어?"

2. DB 먼저 확인:
   local_db_query(query="미용실", area="오송")
   → DB에 가게가 있으면 언급 횟수와 함께 제공

3. 추가 검색:
   local_search(query="미용실 추천", site="naver_cafe")
   local_search(query="오송 미용실", site="naver_map")

4. 검색 결과 처리:
   a) 가게 이름이 보이면 → local_db_save(mode="store") 로 등록
   b) 그 게시글을 → local_db_save(mode="mention") 로 기록
      - source_url을 반드시 포함 (다음에 같은 글 나오면 중복 방지)

5. 사용자에게 결과 제공 (언급 많은 순으로)
```

### 실제 예시

```
이번주 "오송 미용실 추천" 검색:
  카페 글 1: "OO미용실 강추" (url: /post/111)
    → store: OO미용실 등록
    → mention: /post/111 기록
  카페 글 2: "XX헤어 다녀왔어요" (url: /post/222)
    → store: XX헤어 등록
    → mention: /post/222 기록
  카페 글 3: "미용실 어디 좋아요?" (url: /post/333)
    → 특정 가게 이름 없음 → 저장 안 함
  지도 결과: OO미용실 (주소, 전화)
    → store: OO미용실 업데이트 (주소/전화 추가)

다음주 같은 검색:
  카페 글 1: "OO미용실 강추" (같은 url) → mention 중복 → 무시
  카페 글 4: "OO미용실 또 감" (url: /post/555) → mention 추가 (새 글)
  카페 글 5: "AA뷰티 오픈" (url: /post/666) → 새 가게 + mention

결과: OO미용실 (언급 2회) > XX헤어 (1회) = AA뷰티 (1회)
```

### 저장 기준

**store로 등록:**
- 게시글에서 구체적인 가게 이름이 나온 경우
- 지도 검색에서 나온 가게

**mention으로 기록:**
- 특정 가게 이름이 언급된 모든 게시글 (추천이든 불만이든 상관없이)
- source_url 필수 (중복 방지 핵심)

**저장 안 함:**
- 가게 이름이 전혀 없는 일반 질문글

## 중복 방지

### 가게(store) 3단계
1. 이름 + 주소 정확히 일치
2. 이름 + 지역(area) 일치
3. 이름 정규화 비교 ("오송 헤어" = "오송헤어")

### 언급(mention)
1. 같은 가게 + 같은 source_url → 저장 안 함
2. 같은 가게 + 같은 제목 → 저장 안 함
3. 둘 다 안 걸리면 → 새 언급 생성

## 도구별 상세

### local_search
| 파라미터 | 설명 | 기본값 |
|---------|------|--------|
| query | 검색 키워드 | (필수) |
| site | naver_cafe / naver_map | naver_cafe |
| cafe_id | 카페 ID | osong1 |
| display | 결과 수 | 5 (최대 10) |

### local_db_query
| action | 설명 |
|--------|------|
| search | FTS5 전문 검색 (mention_count 포함) |
| stats | 통계 + 가장 많이 언급된 가게 TOP 5 |
| recent | 최근 추가/수정 |
| detail | 가게 상세 + 전체 언급 목록 |

### local_db_save
| mode | 핵심 파라미터 |
|------|--------------|
| store | name(필수), category, address, phone |
| mention | store_id(필수), title, source_url |
| delete | store_id |

## 알려진 제약사항

- 네이버 카페 검색은 Playwright 필요
- 네이버 지도 API는 NAVER_CLIENT_ID/SECRET 환경변수 필요
- 카페 검색 결과는 제목+미리보기만 (본문 전체가 아님)
- 비로그인 검색이므로 비공개 게시글 접근 불가
