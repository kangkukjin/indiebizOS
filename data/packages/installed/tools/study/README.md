# Study

에이전트가 학술 데이터베이스, 여론 조사 기관 및 주요 언론사에서 정보를 검색하고 자료를 수집할 수 있게 합니다.

## 지원 소스

| 소스 | 설명 | 특징 | 자료 형태 |
|------|------|------|-------------|
| **OpenAlex** | 세계 최대 오픈 학술 DB (2.6억+ 논문) | 전 분야, 무료, 제한 없음 | 논문 정보, PDF 링크 |
| **arXiv** | CS, 물리, 수학 등 프리프린트 | 최신 연구, 기술 트렌드 | 모든 논문 PDF 가능 |
| **Semantic Scholar** | AI 기반 학술 검색 | 인용수, 영향력 분석 | 논문 정보, AI 요약 |
| **Google Scholar** | 가장 넓은 커버리지 | 모든 분야, 책/학위논문 | 논문 정보, 링크 |
| **PubMed/PMC** | 의학/생명과학 전문 | 임상연구, 의료 논문 | PMC 논문 PDF 가능 |
| **Pew Research** | 여론 조사 및 사회 트렌드 | 사회 이슈, 인구 통계 | 최신 연구 리포트 |
| **The Guardian** | 글로벌 뉴스 아카이브 | 국제 정세, 언론 시각 | 뉴스 기사 전문 |
| **World Bank** | 글로벌 경제 및 사회 지표 | GDP, 인구, 실업률 등 | 시계열 통계 데이터 |
| **Google Books** | 전 세계 도서 정보 검색 | ISBN, 저자, 출판 정보 | 도서 요약, 메타데이터 |

## 도구 목록

### search_openalex
**세계 최대 오픈 학술 데이터베이스 검색**
- 모든 학문 분야 커버 (자연과학, 공학, 의학, 사회과학, 인문학)
- 완전 무료, API 키 불필요

### search_arxiv
CS, 물리, 수학 등 프리프린트 검색

### download_arxiv_pdf
arXiv 논문 PDF 다운로드

### search_semantic_scholar
AI 기반 학술 검색 (인용수, 영향력 분석 포함)

### search_google_scholar
가장 넓은 범위의 학술 검색

### search_pubmed
의학/생명과학 논문 검색

### download_pubmed_pdf
PubMed Central(PMC) 논문 PDF 다운로드

### fetch_pew_research (NEW)
**Pew Research Center의 최신 연구 및 여론 조사 결과**
- 사회적 이슈, 여론, 인구 통계 분야의 데이터 중심 분석
- 최신 사회 트렌드 및 여론 조사 데이터 확인

### search_guardian (NEW)
**The Guardian 기사 검색 및 아카이브 접근**
- 특정 이슈에 대한 글로벌 언론의 시각 파악
- 섹션, 태그, 날짜별 정교한 검색 지원

### fetch_world_bank_data (NEW)
**국가별 경제 및 사회 지표 데이터 조회**
- GDP, 인구, 인플레이션, 실업률 등 수천 개의 글로벌 지표 제공
- 시계열 데이터(연도별) 분석 및 국가 간 비교에 최적화
- 주요 지표 코드: GDP(`NY.GDP.MKTP.CD`), 인구(`SP.POP.TOTL`), 실업률(`SL.UEM.TOTL.ZS`)

### search_books (NEW)
**Google Books API를 사용한 도서 정보 검색**
- 책을 인용하거나 상세 참고 문헌 정보가 필요할 때 사용
- 제목, 저자, 출판사, 발행일, ISBN, 도서 요약 정보 제공
- 특정 주제에 대한 전문 서적 목록 확인 가능

## 사용 팁

AI에게 "최신 여론 조사 결과 알려줘" 또는 "특정 주제에 대한 논문과 기사 찾아줘"라고 하면 상황에 맞는 소스를 자동 선택합니다.

- **학술 연구**: OpenAlex, arXiv, PubMed
- **사회 트렌드/여론**: Pew Research
- **시사/글로벌 뉴스**: The Guardian
- **경제/통계 지표**: World Bank
- **도서/참고 문헌**: Google Books

## 필요 라이브러리

```bash
pip install arxiv scholarly requests feedparser
```

## 적합한 에이전트
- 연구/학습 에이전트
- 리서치 에이전트
- 기술 분석 에이전트
- 의료/건강 정보 에이전트
- 사회/시사 분석 에이전트
