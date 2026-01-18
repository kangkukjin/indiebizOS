# Culture & Arts 패키지

공연, 전시, 영화 등 문화 예술 정보를 조회하는 도구 패키지입니다.

## 현재 지원하는 API

### KOPIS (공연예술통합전산망)
- 연극, 뮤지컬, 클래식, 국악, 콘서트 등 공연 정보
- 예매 순위(박스오피스)
- 공연장 정보
- 축제/페스티벌 정보

## API 키 설정

### KOPIS API 키 발급
1. [KOPIS Open API 페이지](https://www.kopis.or.kr/por/cs/openapi/openApiInfo.do) 접속
2. 회원가입 후 API 키 신청
3. 환경변수 설정:
   ```bash
   export KOPIS_API_KEY="발급받은_API_키"
   ```

## 도구 목록

### kopis_quick_search
공연을 키워드로 빠르게 검색합니다.

```python
# 위키드 뮤지컬 검색
kopis_quick_search(keyword="위키드", genre="뮤지컬")

# 서울 지역 공연중인 연극
kopis_quick_search(genre="연극", region="서울", status="공연중")

# 앞으로 3개월간 예정된 콘서트
kopis_quick_search(genre="대중음악", status="공연예정", days=90)
```

### kopis_search_performances
기간을 지정하여 공연 목록을 상세 검색합니다.

```python
# 2024년 1월 서울 뮤지컬 검색
kopis_search_performances(
    stdate="20240101",
    eddate="20240131",
    genre="뮤지컬",
    region="서울"
)
```

### kopis_get_performance
공연 상세 정보를 조회합니다.

```python
# 공연 ID로 상세 정보 조회
kopis_get_performance(performance_id="PF123456")
```

### kopis_box_office
예매 순위(박스오피스)를 조회합니다.

```python
# 오늘의 전체 박스오피스
kopis_box_office(period="day")

# 이번 주 뮤지컬 순위
kopis_box_office(period="week", genre="뮤지컬")

# 특정 날짜 서울 지역 순위
kopis_box_office(date="20240115", region="서울")
```

### kopis_search_facilities
공연장 정보를 검색합니다.

```python
# 예술의전당 검색
kopis_search_facilities(keyword="예술의전당")

# 서울 지역 공연장 목록
kopis_search_facilities(region="서울")
```

### kopis_search_festivals
축제/페스티벌을 검색합니다.

```python
# 다가오는 음악 축제
kopis_search_festivals(genre="대중음악")

# 서울 지역 축제
kopis_search_festivals(region="서울")
```

## 지원하는 장르

| 한글명 | 영문 별칭 | 코드 |
|--------|-----------|------|
| 연극 | theater, play | AAAA |
| 뮤지컬 | musical | GGGA |
| 클래식 | classic, classical | CCCA |
| 국악 | korean | CCCC |
| 대중음악 | pop, concert | CCCD |
| 무용 | dance | BBBC |
| 대중무용 | popular_dance | BBBE |
| 서커스/마술 | circus, magic | EEEA |
| 복합 | complex, mixed | EEEB |

## 지원하는 지역

| 한글명 | 영문 별칭 | 코드 |
|--------|-----------|------|
| 서울 | seoul | 11 |
| 부산 | busan | 26 |
| 대구 | daegu | 27 |
| 인천 | incheon | 28 |
| 광주 | gwangju | 29 |
| 대전 | daejeon | 30 |
| 울산 | ulsan | 31 |
| 세종 | sejong | 36 |
| 경기 | gyeonggi | 41 |
| 강원 | gangwon | 42 |
| 충북 | chungbuk | 43 |
| 충남 | chungnam | 44 |
| 전북 | jeonbuk | 45 |
| 전남 | jeonnam | 46 |
| 경북 | gyeongbuk | 47 |
| 경남 | gyeongnam | 48 |
| 제주 | jeju | 50 |

## 공연 상태

| 한글명 | 영문 별칭 | 코드 |
|--------|-----------|------|
| 공연예정 | upcoming | 01 |
| 공연중 | ongoing, running | 02 |
| 공연완료 | ended, completed | 03 |

## 향후 추가 예정

- **영화 정보**: 영화진흥위원회(KOFIC) API
- **도서 정보**: 국립중앙도서관 API, 알라딘 API
- **전시 정보**: 문화포털 전시 API
- **공연 리뷰/평점**: 인터파크, 예스24 등

## 참고 자료

- [KOPIS 공연예술통합전산망](https://www.kopis.or.kr/)
- [KOPIS Open API 안내](https://kopis.or.kr/por/cs/openapi/openApiInfo.do)
- [KOPIS API GitHub 라이브러리](https://github.com/jinwooYoon/kopisapi)
