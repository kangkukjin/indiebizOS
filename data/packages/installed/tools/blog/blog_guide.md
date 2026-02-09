# Blog 도구 가이드

## 주의사항

이 도구는 **개인 블로그 'K의 생각' 전용**이다. 일반적인 웹 검색은 `ddgs_search` (web 패키지)를 사용할 것.

---

## 도구 선택 가이드

| 목적 | 도구 | 설명 |
|------|------|------|
| RAG 검색 | `search_blog_rag` | 의미 기반 검색 (시맨틱) |
| 전문 조회 (RAG) | `get_post_content_rag` | RAG 시스템을 통한 글 전문 조회 |
| 전문 조회 (단순) | `blog_get_post` | 단순 ID 기반 글 조회 |
| 글 목록 | `blog_get_posts` | 카테고리 필터링, 요약 옵션 |
| DB 업데이트 | `blog_check_new_posts` | RSS를 통해 DB에 새 글 반영 |
| 통계 | `blog_stats` | 블로그 통계 |
| 인사이트 (최신 10개) | `kinsight` | 최신 글 10개 기반 인사이트 분석 |
| 인사이트 (개수 지정) | `kinsight2` | 개수 지정 가능한 인사이트 분석 |

---

## get_post_content_rag vs blog_get_post

| 항목 | get_post_content_rag | blog_get_post |
|------|---------------------|---------------|
| 조회 방식 | RAG 시스템을 통해 조회 | 단순 ID 기반 조회 |
| 사용 시점 | search_blog_rag 결과에서 상세 읽기 | ID를 이미 알고 있을 때 |
| 추천 | 일반적인 워크플로우에서 권장 | 빠른 직접 조회가 필요할 때 |

---

## kinsight vs kinsight2

| 항목 | kinsight | kinsight2 |
|------|----------|-----------|
| 분석 대상 | 최신 10개 글 (고정) | 개수 지정 가능 |
| 사용 시점 | 빠르게 최근 인사이트 확인 | 특정 개수의 글을 분석하고 싶을 때 |

---

## 기본 워크플로우

### 블로그 글 검색 및 읽기

```
1. search_blog_rag("검색 키워드")
   - 의미 기반으로 관련 글 검색
   - 결과에서 글 ID, 제목, 관련도 확인

2. get_post_content_rag(글 ID)
   - 검색된 글의 전문 조회
   - RAG 시스템을 통한 상세 내용 확인
```

### 카테고리별 글 탐색

```
1. blog_get_posts(category="카테고리명")
   - 특정 카테고리의 글 목록 조회
   - 요약 옵션으로 간략한 내용 확인

2. blog_get_post(글 ID) 또는 get_post_content_rag(글 ID)
   - 원하는 글의 전문 조회
```

### 블로그 인사이트 분석

```
- kinsight: 최신 10개 글의 인사이트를 빠르게 확인
- kinsight2(count=20): 최신 20개 등 원하는 개수만큼 분석
```

### 새 글 반영

```
blog_check_new_posts
- RSS 피드를 확인하여 새 글을 DB에 반영
- 검색 전에 최신 상태로 업데이트할 때 사용
```
