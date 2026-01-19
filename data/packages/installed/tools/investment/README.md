# Investment Tools

한국/미국 기업의 주가, 재무제표, 공시정보, 뉴스를 조회하는 투자 분석 도구 패키지입니다.

## 기능

### 한국 기업 (DART OpenAPI + KRX)
- `kr_company_info` - 기업 개황 (대표자, 업종, 주소, 설립일 등)
- `kr_financial_statements` - 재무제표 (재무상태표, 손익계산서, 현금흐름표)
- `kr_disclosures` - 공시 목록 검색 (유상증자, M&A, 임원변동 등)
- `kr_stock_price` - 주가 조회 (현재가, 과거 시세)

### 미국 기업 (SEC EDGAR + FMP)
- `us_company_profile` - 기업 프로필 (업종, 시가총액, CEO, 사업설명)
- `us_financial_statements` - 재무제표 (손익, 재무상태, 현금흐름)
- `us_sec_filings` - SEC 공시 검색 (10-K, 10-Q, 8-K 등)
- `us_stock_price` - 주가 조회

### 공통 (Finnhub)
- `company_news` - 기업별 최신 뉴스
- `earnings_calendar` - 실적발표 일정

## API 키 설정

`.env` 파일에 다음 환경변수를 추가하세요:

```bash
# 한국 공시 (필수)
DART_API_KEY=your_dart_api_key
# https://opendart.fss.or.kr 에서 무료 발급

# 미국 주가/재무 (필수)
FMP_API_KEY=your_fmp_api_key
# https://site.financialmodelingprep.com 에서 무료 발급 (일 250회)

# 뉴스/실적 (선택)
FINNHUB_API_KEY=your_finnhub_api_key
# https://finnhub.io 에서 무료 발급 (분당 60회)
```

## 데이터 소스

| 소스 | 용도 | 인증 | 제한 |
|------|------|------|------|
| **DART OpenAPI** | 한국 공시, 재무제표 | API 키 (무료) | 일 10,000회 |
| **KRX** | 한국 주가 | 불필요 | - |
| **SEC EDGAR** | 미국 공시 | 불필요 | - |
| **Financial Modeling Prep** | 미국 주가, 재무제표, 기업정보 | API 키 (무료) | 일 250회 |
| **Finnhub** | 뉴스, 실적발표 | API 키 (무료) | 분당 60회 |

## 의존성 설치

```bash
pip install finance-datareader
```

> FinanceDataReader가 없어도 KRX API로 대체 동작합니다.

## 사용 예시

### 한국 기업 조회
```python
# 삼성전자 기업 정보
kr_company_info(corp_name="삼성전자")

# 삼성전자 2024년 재무제표
kr_financial_statements(corp_name="삼성전자", year="2024")

# 삼성전자 최근 공시
kr_disclosures(corp_name="삼성전자", count=10)

# 삼성전자 주가
kr_stock_price(symbol="005930")
```

### 미국 기업 조회
```python
# Apple 기업 프로필
us_company_profile(symbol="AAPL")

# Apple 손익계산서 (최근 5년)
us_financial_statements(symbol="AAPL", statement_type="income")

# Apple SEC 공시 (10-K만)
us_sec_filings(symbol="AAPL", filing_type="10-K")

# Apple 주가
us_stock_price(symbol="AAPL")
```

### 뉴스 및 실적
```python
# NVIDIA 관련 뉴스
company_news(symbol="NVDA")

# 향후 2주 실적발표 일정
earnings_calendar()
```

## 파일 구조

```
investment/
├── tool.json           # 도구 정의 (10개 도구)
├── handler.py          # 진입점
├── tool_dart.py        # DART OpenAPI (한국 공시)
├── tool_krx.py         # KRX/FinanceDataReader (한국 주가)
├── tool_sec_edgar.py   # SEC EDGAR (미국 공시)
├── tool_fmp.py         # Financial Modeling Prep (미국 주가/재무)
├── tool_finnhub.py     # Finnhub (뉴스/실적)
├── requirements.txt
└── README.md
```

## 캐시

패키지는 API 호출을 줄이기 위해 일부 데이터를 캐시합니다:
- `corp_code_cache.json` - DART 기업코드 (7일)
- `stock_code_cache.json` - KRX 종목코드 (1일)
- `cik_cache.json` - SEC CIK 코드 (영구)

## 버전

- 1.0.0 (2025-01-19): 최초 릴리스
