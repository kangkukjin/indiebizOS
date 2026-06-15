# 투자/금융 IBL 사용 가이드

2026-06-03 어휘 정리: 옛 16개 액션(price·kr_company·us_filing…)은 **3개 액션**으로 통합됐다.
- `[sense:stock]{op}` — 주식 시세·거래 데이터
- `[sense:company]{op}` — 기업 펀더멘털 (정보·재무·공시)
- `[sense:crypto]` — 암호화폐 (자산군이 달라 별도)

> 옛 액션명(`price`·`kr_company`·`us_filing` 등)은 2026-06-03 폐지됐다. **위 3개만 사용** — 옛 이름은 "알 수 없는 액션" 에러로 떨어진다.

## 시장 자동판별 (kr/us)
`ticker` 값으로 한국/미국을 **자동 판별**한다 — 별도 지정 불필요.
- **한국**: 6자리 숫자(`005930`), `.KS`/`.KQ` 접미, 한글 회사명(`삼성전자`)
- **미국**: 알파벳 티커(`AAPL`)
- 강제 지정이 필요하면 `market: "kr"` 또는 `market: "us"`.

---

## [sense:stock] — 주식 시세·거래 데이터

| op | 설명 | 소스 | 주요 파라미터 |
|----|------|------|--------------|
| `quote` (기본) | 현재 시세 빠른 조회 | Yahoo | `ticker`, `period`, `interval` |
| `history` | 기간별 주가 이력 | 한국 KRX / 미국 FMP | `ticker`, `start_date`, `end_date`, `max_points` |
| `info` | 종목 메타 (시총·52주·PER·배당) | Yahoo | `ticker` |
| `search` | 회사명으로 심볼 검색 | Yahoo | `query` |
| `investors` | 투자자별 매매동향 (**한국 전용**) | KRX | `ticker`(개별종목) 또는 `market`(STK/KSQ/ALL, 전체시장) |
| `news` | 종목 관련 뉴스 | Finnhub→Yahoo | `ticker`, `start_date`, `end_date` |
| `earnings` | 실적발표 일정 | Finnhub | `ticker`(생략 시 전체시장), `start_date`, `end_date` |

```
[sense:stock]{op: "quote", ticker: "005930"}                 # 삼성전자 현재가 (KRW)
[sense:stock]{op: "quote", ticker: "GC=F", period: "3mo"}    # 금 선물 3개월
[sense:stock]{op: "history", ticker: "AAPL", start_date: "2026-01-01"}
[sense:stock]{op: "info", ticker: "AAPL"}
[sense:stock]{op: "search", query: "삼성"}                    # → 005930 등 후보
[sense:stock]{op: "investors", ticker: "005930"}             # 개별종목 매매동향
[sense:stock]{op: "investors", market: "KSQ"}                # 코스닥 전체시장
[sense:stock]{op: "news", ticker: "TSLA"}
[sense:stock]{op: "earnings"}                                # 향후 2주 전체 실적일정
```

**investors의 `market`** 은 kr/us가 아니라 시장 구분이다: `STK`(코스피, 기본)·`KSQ`(코스닥)·`ALL`(전체). 한국 전용이라 시장 자동판별은 적용 안 됨.

### period / interval (quote 전용)
- period: `1d`, `5d`, `1mo`, `3mo`, `6mo`, `1y`, `2y`, `5y`, `10y`, `ytd`, `max`
- interval: `1m`, `5m`, `15m`, `30m`, `1h`, `1d`, `1wk`, `1mo`

---

## [sense:company] — 기업 펀더멘털

| op | 설명 | 한국(DART) / 미국(FMP·SEC) | 주요 파라미터 |
|----|------|----------------------------|--------------|
| `profile` (기본) | 기업 기본정보 (대표·업종·시총·섹터) | kr_company_info / us_company_profile | `ticker` |
| `financials` | 재무제표 (손익·재무상태·현금흐름) | DART / FMP | 아래 참조 |
| `disclosures` | 공시 검색 | DART / SEC EDGAR | 아래 참조 |

```
[sense:company]{op: "profile", ticker: "삼성전자"}            # 한국 DART 자동
[sense:company]{op: "profile", ticker: "AAPL"}               # 미국 FMP 자동
[sense:company]{op: "financials", ticker: "삼성전자", year: "2024"}
[sense:company]{op: "financials", ticker: "AAPL", statement_type: "income"}
[sense:company]{op: "disclosures", ticker: "삼성전자", pblntf_ty: "A"}
[sense:company]{op: "disclosures", ticker: "AAPL", filing_type: "10-K"}
```

### financials 파라미터
- **한국**: `year`(필수, 예 "2024"), `report_type` — `11011`(연간)·`11012`(반기)·`11013`(1분기)·`11014`(3분기)
- **미국**: `statement_type` — `income`(기본)·`balance`·`cashflow`, `period` — `annual`(기본)·`quarter`, `limit`(기본 5)

### disclosures 파라미터
- **한국(DART) `pblntf_ty`**: `A`(정기·사업보고서)·`B`(주요사항·증자/합병)·`D`(지분·대량보유)·`I`(거래소). `start_date`/`end_date`(YYYYMMDD), `count`(기본 20)
- **미국(SEC) `filing_type`**: `10-K`(연차)·`10-Q`(분기)·`8-K`(수시)·`DEF 14A`(주총). `count`(기본 10)

---

## [sense:crypto] — 암호화폐
```
[sense:crypto]{coin_id: "bitcoin"}     # CoinGecko ID
[sense:crypto]{coin_id: "BTC"}         # 심볼 → 자동 변환
[sense:crypto]{coin_id: "ETH", days: 30, max_points: 400}  # 30일 이력 차트
```
| 심볼 | ID | | 심볼 | ID |
|------|----|----|------|----|
| BTC | bitcoin | | DOGE | dogecoin |
| ETH | ethereum | | SOL | solana |
| XRP | ripple | | ADA | cardano |

반환: USD/KRW 현재가, 24시간 변동률, 시가총액, 거래량, 역대 최고가.

---

## 전형적 워크플로우

**한국 기업 분석**
```
[sense:company]{op: "profile", ticker: "삼성전자"}
  >> [sense:company]{op: "financials", ticker: "삼성전자", year: "2024"}
  >> [sense:stock]{op: "quote", ticker: "005930"}
  >> [sense:company]{op: "disclosures", ticker: "삼성전자"}
```

**미국 기업 분석**
```
[sense:company]{op: "profile", ticker: "AAPL"}
  >> [sense:company]{op: "financials", ticker: "AAPL", statement_type: "income"}
  >> [sense:stock]{op: "quote", ticker: "AAPL"}
  >> [sense:company]{op: "disclosures", ticker: "AAPL", filing_type: "10-K"}
```

**시세 조회 → 차트**
```
[sense:stock]{op: "history", ticker: "AAPL", start_date: "2026-03-01"}
  >> [engines:chart]{title: "AAPL", chart_type: "line"}
```
주가/재무 데이터가 클 때 `file_path`+`sample`이 반환된다. 차트는 `data_file`에 file_path를 넘기거나, `prices` 배열을 `data`로 변환(`[{"x": p["date"], "y": p["close"]}]`)해 넘긴다.

---

## 주요 종목 참조
| 한국 | 코드 | | 미국 | 티커 |
|------|------|---|------|------|
| 삼성전자 | 005930 | | Apple | AAPL |
| SK하이닉스 | 000660 | | Microsoft | MSFT |
| NAVER | 035420 | | NVIDIA | NVDA |
| 카카오 | 035720 | | Tesla | TSLA |
| 현대차 | 005380 | | Amazon | AMZN |

**심볼 형식(Yahoo quote/info)**: 미국 `AAPL`, 한국 `005930.KS`(자동 부착), ETF `SPY`/`QQQ`/`GLD`, 원자재 선물 `GC=F`(금)/`CL=F`(원유), 환율 `USDKRW=X`.
