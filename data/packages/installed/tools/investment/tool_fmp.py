"""
Financial Modeling Prep (FMP) 도구
미국 기업의 주가, 재무제표, 기업 프로필을 조회합니다.

API 문서: https://site.financialmodelingprep.com/developer/docs
필요 환경변수: FMP_API_KEY
무료 티어: 일 250회 제한

2026-02: /v3/ 레거시 → /stable/ 신규 API로 마이그레이션
"""
import os
import sys
import json
from datetime import datetime, timedelta

# common 유틸리티 사용
_backend_dir = os.path.join(os.path.dirname(__file__), "..", "..", "..", "..", "backend")
if _backend_dir not in sys.path:
    sys.path.insert(0, os.path.abspath(_backend_dir))

from common.api_client import api_call
from common.response_formatter import save_large_data


def _api_request(endpoint: str, params: dict = None):
    """FMP API 요청 (/stable/ 엔드포인트 사용)

    2026-02: /v3/ 레거시 폐기 → /stable/ 신규 API 사용
    base_url을 직접 지정하여 /api/ 접두사 우회
    """
    result = api_call(
        "fmp", f"/{endpoint}",
        params=params or {},
        timeout=30,
        base_url="https://financialmodelingprep.com/stable"
    )
    if isinstance(result, dict) and "error" in result:
        return {"success": False, "error": result["error"]}
    if isinstance(result, dict) and "Error Message" in result:
        return {"success": False, "error": result["Error Message"]}
    return {"success": True, "data": result}


def get_company_profile(symbol: str):
    """
    미국 기업 프로필 조회

    Args:
        symbol: 티커 심볼 (예: AAPL, MSFT)

    Returns:
        기업 기본 정보 (업종, 시가총액, CEO, 사업설명 등)
    """
    symbol = symbol.upper()
    # /stable/profile?symbol=PLTR
    result = _api_request("profile", {"symbol": symbol})

    if not result.get("success"):
        return result

    data = result["data"]
    if not data or len(data) == 0:
        return {
            "success": False,
            "error": f"'{symbol}'에 해당하는 기업을 찾을 수 없습니다."
        }

    company = data[0]

    return {
        "success": True,
        "data": {
            "symbol": company.get("symbol"),
            "company_name": company.get("companyName"),
            "price": company.get("price"),
            "market_cap": company.get("marketCap"),
            "beta": company.get("beta"),
            "volume_avg": company.get("averageVolume"),
            "last_dividend": company.get("lastDividend"),
            "range_52week": company.get("range"),
            "change": company.get("change"),
            "change_percent": company.get("changePercentage"),
            "currency": company.get("currency"),
            "exchange": company.get("exchange"),
            "industry": company.get("industry"),
            "sector": company.get("sector"),
            "country": company.get("country"),
            "employees": company.get("fullTimeEmployees"),
            "ceo": company.get("ceo"),
            "website": company.get("website"),
            "description": company.get("description"),
            "ipo_date": company.get("ipoDate"),
            "is_etf": company.get("isEtf"),
            "is_actively_trading": company.get("isActivelyTrading")
        },
        "summary": f"{company.get('companyName')} ({symbol}) - {company.get('sector')}/{company.get('industry')}, 시가총액: ${company.get('marketCap', 0):,.0f}"
    }


def get_financial_statements(symbol: str, statement_type: str = "income",
                              period: str = "annual", limit: int = 5):
    """
    미국 기업 재무제표 조회

    Args:
        symbol: 티커 심볼
        statement_type: income(손익계산서), balance(재무상태표), cashflow(현금흐름표)
        period: annual(연간), quarter(분기)
        limit: 조회할 기간 수

    Returns:
        재무제표 데이터
    """
    symbol = symbol.upper()

    # /stable/ 엔드포인트
    endpoint_map = {
        "income": "income-statement",
        "balance": "balance-sheet-statement",
        "cashflow": "cash-flow-statement"
    }

    endpoint = endpoint_map.get(statement_type, "income-statement")

    params = {"symbol": symbol, "limit": limit}
    if period == "quarter":
        params["period"] = "quarter"

    result = _api_request(endpoint, params)

    if not result.get("success"):
        return result

    data = result["data"]
    if not data:
        return {
            "success": False,
            "error": f"'{symbol}'의 재무제표를 찾을 수 없습니다."
        }

    # 주요 항목 추출
    statements = []
    for item in data:
        if statement_type == "income":
            statement = {
                "date": item.get("date"),
                "period": item.get("period"),
                "revenue": item.get("revenue"),
                "cost_of_revenue": item.get("costOfRevenue"),
                "gross_profit": item.get("grossProfit"),
                "operating_expenses": item.get("operatingExpenses"),
                "operating_income": item.get("operatingIncome"),
                "net_income": item.get("netIncome"),
                "eps": item.get("eps"),
                "eps_diluted": item.get("epsdiluted"),
                "ebitda": item.get("ebitda"),
                "gross_margin": item.get("grossProfitRatio"),
                "operating_margin": item.get("operatingIncomeRatio"),
                "net_margin": item.get("netIncomeRatio")
            }
        elif statement_type == "balance":
            statement = {
                "date": item.get("date"),
                "period": item.get("period"),
                "total_assets": item.get("totalAssets"),
                "total_current_assets": item.get("totalCurrentAssets"),
                "cash_and_equivalents": item.get("cashAndCashEquivalents"),
                "total_liabilities": item.get("totalLiabilities"),
                "total_current_liabilities": item.get("totalCurrentLiabilities"),
                "long_term_debt": item.get("longTermDebt"),
                "total_debt": item.get("totalDebt"),
                "total_equity": item.get("totalStockholdersEquity"),
                "retained_earnings": item.get("retainedEarnings")
            }
        else:  # cashflow
            statement = {
                "date": item.get("date"),
                "period": item.get("period"),
                "operating_cash_flow": item.get("operatingCashFlow"),
                "investing_cash_flow": item.get("netCashUsedForInvestingActivites"),
                "financing_cash_flow": item.get("netCashUsedProvidedByFinancingActivities"),
                "free_cash_flow": item.get("freeCashFlow"),
                "capital_expenditure": item.get("capitalExpenditure"),
                "dividends_paid": item.get("dividendsPaid"),
                "stock_repurchase": item.get("commonStockRepurchased")
            }

        statements.append(statement)

    statement_names = {
        "income": "손익계산서",
        "balance": "재무상태표",
        "cashflow": "현금흐름표"
    }

    return {
        "success": True,
        "data": {
            "symbol": symbol,
            "statement_type": statement_type,
            "period": period,
            "statements": statements
        },
        "summary": f"{symbol}의 {statement_names.get(statement_type)} ({period}) - {len(statements)}개 기간 조회"
    }


def get_stock_price(symbol: str, start_date: str = None, end_date: str = None):
    """
    미국 주식 시세 조회

    Args:
        symbol: 티커 심볼
        start_date: 조회 시작일 (YYYY-MM-DD)
        end_date: 조회 종료일 (YYYY-MM-DD)

    Returns:
        주가 데이터
    """
    symbol = symbol.upper()

    # 날짜 기본값
    if not end_date:
        end_date = datetime.now().strftime("%Y-%m-%d")
    if not start_date:
        start_date = (datetime.now() - timedelta(days=30)).strftime("%Y-%m-%d")

    # /stable/historical-price-eod/full?symbol=PLTR&from=...&to=...
    params = {
        "symbol": symbol,
        "from": start_date,
        "to": end_date
    }

    result = _api_request("historical-price-eod/full", params)

    if not result.get("success"):
        return result

    data = result["data"]
    # 신규 API: 배열 직접 반환 (historical 래핑 없음)
    if not data:
        return {
            "success": False,
            "error": f"'{symbol}'의 주가 데이터를 찾을 수 없습니다."
        }

    # 데이터 정리 (최신 순 → 오래된 순)
    prices = []
    for item in reversed(data):
        prices.append({
            "date": item.get("date"),
            "open": item.get("open"),
            "high": item.get("high"),
            "low": item.get("low"),
            "close": item.get("close"),
            "volume": item.get("volume"),
            "change": item.get("change"),
            "change_percent": item.get("changePercent"),
            "vwap": item.get("vwap")
        })

    latest = prices[-1] if prices else {}
    total_days = len(prices)

    # 대량 데이터는 파일로 저장 (50개 초과시)
    if total_days > 50:
        file_path = save_large_data(prices, "investment", f"us_prices_{symbol}")

        # 요약용 샘플 (10개 포인트만)
        step = max(1, total_days // 10)
        sample_prices = prices[::step]
        if sample_prices[-1] != prices[-1]:
            sample_prices.append(prices[-1])
        sample_compact = [{"date": p["date"], "close": p["close"]} for p in sample_prices]

        return {
            "success": True,
            "data": {
                "symbol": symbol,
                "start_date": start_date,
                "end_date": end_date,
                "total_days": total_days,
                "latest": latest,
                "file_path": file_path,
                "sample": sample_compact
            },
            "summary": f"{symbol} 현재가: ${latest.get('close', 'N/A')}, 변동: {latest.get('change_percent', 0):.2f}%, 기간: {start_date} ~ {end_date}, 총 {total_days}거래일. 전체 데이터: {file_path}"
        }
    else:
        compact_prices = [{"date": p["date"], "close": p["close"]} for p in prices]

        return {
            "success": True,
            "data": {
                "symbol": symbol,
                "start_date": start_date,
                "end_date": end_date,
                "total_days": total_days,
                "latest": latest,
                "prices": compact_prices
            },
            "summary": f"{symbol} 현재가: ${latest.get('close', 'N/A')}, 변동: {latest.get('change_percent', 0):.2f}%"
        }


def get_stock_quote(symbol: str):
    """
    미국 주식 실시간 시세 조회

    Args:
        symbol: 티커 심볼

    Returns:
        실시간 시세
    """
    symbol = symbol.upper()
    # /stable/profile이 가격 정보 포함
    result = _api_request("profile", {"symbol": symbol})

    if not result.get("success"):
        return result

    data = result["data"]
    if not data or len(data) == 0:
        return {
            "success": False,
            "error": f"'{symbol}'의 시세를 찾을 수 없습니다."
        }

    quote = data[0]

    return {
        "success": True,
        "data": {
            "symbol": quote.get("symbol"),
            "name": quote.get("companyName"),
            "price": quote.get("price"),
            "change": quote.get("change"),
            "change_percent": quote.get("changePercentage"),
            "market_cap": quote.get("marketCap"),
            "volume": quote.get("volume"),
            "avg_volume": quote.get("averageVolume"),
            "beta": quote.get("beta"),
            "range_52week": quote.get("range"),
            "last_dividend": quote.get("lastDividend"),
            "exchange": quote.get("exchange"),
            "currency": quote.get("currency")
        },
        "summary": f"{quote.get('companyName')} ({symbol}): ${quote.get('price')} ({'+' if quote.get('change', 0) >= 0 else ''}{quote.get('change')}, {'+' if quote.get('changePercentage', 0) >= 0 else ''}{quote.get('changePercentage'):.2f}%)"
    }


def get_key_metrics(symbol: str, period: str = "annual", limit: int = 5):
    """
    주요 재무 비율 조회

    Args:
        symbol: 티커 심볼
        period: annual(연간), quarter(분기)
        limit: 조회할 기간 수

    Returns:
        주요 재무 비율 (ROE, ROA, PER, PBR 등)
    """
    symbol = symbol.upper()

    params = {"symbol": symbol, "limit": limit}
    if period == "quarter":
        params["period"] = "quarter"

    result = _api_request("key-metrics", params)

    if not result.get("success"):
        return result

    data = result["data"]
    if not data:
        return {
            "success": False,
            "error": f"'{symbol}'의 재무 비율을 찾을 수 없습니다."
        }

    metrics = []
    for item in data:
        metrics.append({
            "date": item.get("date"),
            "period": item.get("period"),
            "revenue_per_share": item.get("revenuePerShare"),
            "eps": item.get("netIncomePerShare"),
            "book_value_per_share": item.get("bookValuePerShare"),
            "pe_ratio": item.get("peRatio"),
            "pb_ratio": item.get("pbRatio"),
            "ps_ratio": item.get("priceToSalesRatio"),
            "ev_to_ebitda": item.get("enterpriseValueOverEBITDA"),
            "roe": item.get("roe"),
            "roa": item.get("returnOnTangibleAssets"),
            "debt_to_equity": item.get("debtToEquity"),
            "current_ratio": item.get("currentRatio"),
            "dividend_yield": item.get("dividendYield"),
            "payout_ratio": item.get("payoutRatio"),
            "free_cash_flow_per_share": item.get("freeCashFlowPerShare")
        })

    latest = metrics[0] if metrics else {}

    return {
        "success": True,
        "data": {
            "symbol": symbol,
            "period": period,
            "metrics": metrics
        },
        "summary": f"{symbol} 주요지표 - PER: {latest.get('pe_ratio', 'N/A')}, PBR: {latest.get('pb_ratio', 'N/A')}, ROE: {latest.get('roe', 'N/A')}"
    }


def search_company(query: str):
    """
    기업/종목 검색

    Args:
        query: 검색어 (기업명)

    Returns:
        검색 결과 목록
    """
    result = _api_request("search-name", {"query": query})

    if not result.get("success"):
        return result

    data = result["data"]
    if not data:
        return {
            "success": False,
            "error": f"'{query}' 검색 결과가 없습니다."
        }

    results = []
    for item in data[:10]:
        results.append({
            "symbol": item.get("symbol"),
            "name": item.get("name"),
            "currency": item.get("currency"),
            "exchange": item.get("exchangeFullName") or item.get("exchange")
        })

    return {
        "success": True,
        "data": results,
        "summary": f"'{query}' 검색 결과 {len(results)}건"
    }
