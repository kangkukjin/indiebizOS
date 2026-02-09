# Study 패키지 가이드

## 논문 검색 도구 선택 가이드

### OpenAlex
- 가장 넓은 커버리지 (2.6억+ 학술 자료)
- 전 분야 지원
- 완전 무료, API 키 불필요
- 일반적인 학술 검색에 가장 추천

### arXiv
- CS, 물리, 수학 분야 프리프린트 전문
- 최신 연구 논문 접근에 최적
- PDF 다운로드 지원 (arxiv_id 필요)

### Semantic Scholar
- AI 기반 학술 검색 엔진
- 인용 분석 및 영향력 지표 제공
- 논문 간 관계 파악에 유용

### Google Scholar
- 가장 넓은 검색 범위
- 한국어 논문 검색 지원
- PDF 직접 다운로드는 미지원

### PubMed
- 의학/생명과학 분야 전문
- PMC ID가 있는 오픈액세스 논문은 무료 PDF 다운로드 가능

---

## PDF 다운로드 워크플로우

### arXiv 논문 다운로드
1. `search_arxiv`로 논문 검색
2. 결과에서 arxiv_id 확인
3. `download_arxiv_pdf`에 arxiv_id 전달하여 다운로드

### PubMed 논문 다운로드
1. `search_pubmed`로 논문 검색
2. 결과에서 PMC ID 확인 (오픈액세스 논문만 해당)
3. `download_pubmed_pdf`에 PMC ID 전달하여 다운로드

---

## 비학술 자료 검색

### Pew Research
- 여론 조사 및 사회 트렌드 데이터
- 미국 및 글로벌 사회 이슈 분석

### The Guardian
- 영문 기사 아카이브 검색
- 다양한 주제의 저널리즘 자료

### World Bank
- 국가별 경제/사회 지표 데이터
- 시계열 데이터 지원
- 주요 지표 코드:
  - `NY.GDP.MKTP.CD` - GDP (경상 달러)
  - `SP.POP.TOTL` - 총 인구
  - `FP.CPI.TOTL.ZG` - 인플레이션율 (소비자 물가)
  - `SL.UEM.TOTL.ZS` - 실업률
  - `NY.GDP.PCAP.CD` - 1인당 GDP

### Google Books
- 도서 정보 검색
- 제목, 저자, 출판 정보 조회

---

## 정렬 옵션

- `relevance` - 관련도순 (기본값, 대부분의 도구)
- `cited` - 피인용순 (OpenAlex)
- `recent` - 최신순 (OpenAlex)
- `newest` - 최신순 (Google Books)
