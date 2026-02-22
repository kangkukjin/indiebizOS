# Investment Tools 사용 가이드

## 한국 기업 분석 워크플로우

### 기본 흐름
```
kr_company_info → kr_financial_statements → kr_stock_price → kr_disclosures
   (기업 개황)      (재무제표)                (주가 조회)       (공시 검색)
```

### 1단계: 기업 정보 조회
```python
# 회사명으로 조회
kr_company_info(corp_name='삼성전자')

# DART 코드로 조회
kr_company_info(corp_code='00126380')
```

### 2단계: 재무제표 조회
```python
# 연간 재무제표
kr_financial_statements(corp_name='삼성전자', year='2024')

# 반기/분기 재무제표
kr_financial_statements(corp_name='삼성전자', year='2024', report_type='11012')
```

**report_type 코드:**
| 코드 | 보고서 유형 |
|------|------------|
| `11011` | 연간 (사업보고서) |
| `11012` | 반기 |
| `11013` | 1분기 |
| `11014` | 3분기 |

### 3단계: 주가 조회
```python
# 종목코드 또는 종목명 사용 가능
kr_stock_price(symbol='005930')
kr_stock_price(symbol='삼성전자')

# 기간 지정
kr_stock_price(symbol='005930', start_date='2024-01-01', end_date='2024-12-31')
```

### 4단계: 공시 검색
```python
# 최근 공시
kr_disclosures(corp_name='삼성전자', count=10)

# 정기공시만
kr_disclosures(corp_name='삼성전자', pblntf_ty='A')
```

**DART 공시유형 (pblntf_ty):**
| 코드 | 유형 | 내용 |
|------|------|------|
| `A` | 정기공시 | 사업보고서 |
| `B` | 주요사항보고 | 유상증자, 합병 |
| `D` | 지분공시 | 대량보유 |
| `I` | 거래소공시 | 거래소 관련 |

---

## 미국 기업 분석 워크플로우

### 기본 흐름
```
us_company_profile → us_financial_statements → us_stock_price → us_sec_filings
   (기업 프로필)        (재무제표)                (주가 조회)      (SEC 공시)
```

### 1단계: 기업 프로필
```python
us_company_profile(symbol='AAPL')
```

### 2단계: 재무제표
```python
# 손익계산서 (기본)
us_financial_statements(symbol='AAPL', statement_type='income', limit=5)

# 재무상태표
us_financial_statements(symbol='AAPL', statement_type='balance')

# 현금흐름표
us_financial_statements(symbol='AAPL', statement_type='cashflow')

# 분기 데이터
us_financial_statements(symbol='AAPL', statement_type='income', period='quarter')
```

**statement_type 옵션:**
| 유형 | 설명 | 주요 항목 |
|------|------|----------|
| `income` | 손익계산서 | 매출, 영업이익, 순이익, EPS |
| `balance` | 재무상태표 | 자산, 부채, 자본, 현금 |
| `cashflow` | 현금흐름표 | 영업/투자/재무 현금흐름, FCF |

### 3단계: 주가 조회
```python
us_stock_price(symbol='AAPL')
us_stock_price(symbol='AAPL', start_date='2024-01-01')
```

### 4단계: SEC 공시
```python
# 연차보고서
us_sec_filings(symbol='AAPL', filing_type='10-K')

# 전체 공시
us_sec_filings(symbol='AAPL', count=10)
```

**SEC 공시 유형 (filing_type):**
| 유형 | 설명 | 내용 |
|------|------|------|
| `10-K` | 연차보고서 | 사업개요, 리스크, MD&A |
| `10-Q` | 분기보고서 | 분기 재무상태 |
| `8-K` | 수시보고 | 중요 이벤트 (인수, 경영진 변경 등) |
| `DEF 14A` | 주주총회 자료 | 의결권 행사, 경영진 보상 |

---

## Yahoo Finance 도구 (yf_*) 사용법

### 심볼 형식

| 자산 종류 | 심볼 형식 | 예시 |
|----------|----------|------|
| 미국 주식 | 티커 그대로 | `AAPL`, `TSLA`, `MSFT`, `GOOGL` |
| 한국 주식 | 종목코드.KS | `005930.KS` (삼성전자), `000660.KS` (SK하이닉스) |
| ETF | 티커 그대로 | `SPY`, `QQQ`, `VOO`, `GLD`(금), `SLV`(은) |
| 원자재 선물 | 코드=F | `GC=F`(금), `SI=F`(은), `CL=F`(원유), `NG=F`(천연가스) |
| 환율 | 통화쌍=X | `USDKRW=X`, `EURUSD=X`, `USDJPY=X` |

### yf_stock_price 사용법
```python
# 기본 조회 (최근 5일)
yf_stock_price(symbol='AAPL')

# 기간 지정
yf_stock_price(symbol='AAPL', period='3mo')
yf_stock_price(symbol='005930.KS', period='1y')

# 데이터 간격 지정
yf_stock_price(symbol='AAPL', period='1d', interval='5m')  # 당일 5분봉
```

**period 옵션:** `1d`, `5d`, `1mo`, `3mo`, `6mo`, `1y`, `2y`, `5y`, `10y`, `ytd`, `max`

**interval 옵션:** `1m`, `5m`, `15m`, `30m`, `1h`, `1d`, `1wk`, `1mo`

### yf_search_stock - 심볼을 모를 때
```python
yf_search_stock(query='Apple')      # → AAPL 찾기
yf_search_stock(query='삼성')       # → 005930.KS 찾기
```

---

## 대량 데이터 활용법

50거래일(재무제표 30항목) 초과 시 `file_path`와 `sample`이 반환됩니다.

### file_path 반환 시 처리 방법
```python
import json

# 주가 데이터 읽기
with open(file_path) as f:
    prices = json.load(f)
# prices = [{"date": "2023-01-25", "open": 62000, "high": 63500, "low": 61800, "close": 62600, "volume": 12345678}, ...]

# 재무제표 데이터 읽기
with open(file_path) as f:
    data = json.load(f)
# data['balance_sheet'], data['income_statement'], data['cash_flow']

# 뉴스 데이터 읽기
with open(file_path) as f:
    news = json.load(f)
# news = [{"headline": "...", "summary": "...", "url": "...", "datetime": "..."}, ...]
```

### 차트 생성 워크플로우
```
1. yf_stock_price(symbol='AAPL', period='3mo')
   → 결과에서 file_path 또는 prices 획득

2-A. file_path가 있는 경우:
   line_chart(data_file=file_path, ...)

2-B. prices 배열이 있는 경우:
   data = [{"x": p["date"], "y": p["close"]} for p in prices]
   line_chart(data=data, ...)
```

---

## 암호화폐 조회

### crypto_price 사용법
```python
# CoinGecko ID 또는 심볼 모두 사용 가능 (자동 변환)
crypto_price(coin_id='bitcoin')     # CoinGecko ID
crypto_price(coin_id='BTC')         # 심볼 → 자동 변환
crypto_price(coin_id='ethereum')
crypto_price(coin_id='ETH')
```

**주요 지원 코인:**
| 심볼 | CoinGecko ID | 이름 |
|------|-------------|------|
| BTC | bitcoin | 비트코인 |
| ETH | ethereum | 이더리움 |
| XRP | ripple | 리플 |
| DOGE | dogecoin | 도지코인 |
| SOL | solana | 솔라나 |
| ADA | cardano | 카르다노 |

**반환 정보:** USD/KRW 현재가, 24시간 변동률, 시가총액, 거래량, 역대 최고가

**참고:** yf_stock_price에 암호화폐 심볼 입력 시 자동으로 CoinGecko API로 전환됩니다.

---

## 뉴스 및 실적 일정

### company_news 사용법
```python
# 미국 기업 뉴스
company_news(symbol='AAPL')

# 한국 기업 뉴스
company_news(symbol='005930.KS')

# 기간 지정
company_news(symbol='NVDA', start_date='2024-01-01', end_date='2024-03-31')
```

### earnings_calendar 사용법
```python
# 향후 2주 전체 실적 발표 일정
earnings_calendar()

# 특정 기업만
earnings_calendar(symbol='AAPL')
```

**발표 시간 코드:**
| 코드 | 의미 |
|------|------|
| `bmo` | Before Market Open (장전) |
| `amc` | After Market Close (장후) |
| `dmh` | During Market Hours (장중) |

---

## 주요 종목코드 참조

### 한국
| 종목 | 코드 |
|------|------|
| 삼성전자 | 005930 |
| SK하이닉스 | 000660 |
| NAVER | 035420 |
| 카카오 | 035720 |
| 현대차 | 005380 |

### 미국
| 종목 | 티커 |
|------|------|
| Apple | AAPL |
| Microsoft | MSFT |
| Google | GOOGL |
| Amazon | AMZN |
| NVIDIA | NVDA |
| Meta | META |
| Tesla | TSLA |
