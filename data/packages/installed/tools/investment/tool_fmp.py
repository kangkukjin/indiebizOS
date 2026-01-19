"""
Financial Modeling Prep (FMP) 도구
미국 기업의 주가, 재무제표, 기업 프로필을 조회합니다.

API 문서: https://site.financialmodelingprep.com/developer/docs
필요 환경변수: FMP_API_KEY
무료 티어: 일 250회 제한
"""
import os
import urllib.request
import urllib.parse
import json
from datetime import datetime, timedelta

FMP_API_KEY = os.environ.get("FMP_API_KEY", "")
BASE_URL = "https://financialmodelingprep.com/api/v3"


def _check_api_key():
    """API 키 확인"""
    if not FMP_API_KEY:
        return {
            "success": False,
            "error": "FMP_API_KEY 환경변수가 설정되지 않았습니다. https://site.financialmodelingprep.com 에서 무료 API 키를 발급받으세요."
        }
    return None


def _api_request(endpoint: str, params: dict = None):
    """FMP API 요청"""
    error = _check_api_key()
    if error:
        return error

    if params is None:
        params = {}
    params["apikey"] = FMP_API_KEY

    url = f"{BASE_URL}/{endpoint}?" + urllib.parse.urlencode(params)

    try:
        req = urllib.request.Request(url)
        req.add_header("User-Agent", "Mozilla/5.0")

        with urllib.request.urlopen(req, timeout=30) as response:
            data = json.loads(response.read().decode('utf-8'))

        # 에러 응답 확인
        if isinstance(data, dict) and "Error Message" in data:
            return {
                "success": False,
                "error": data["Error Message"]
            }

        return {"success": True, "data": data}

    except urllib.error.HTTPError as e:
        if e.code == 401:
            return {"success": False, "error": "API 키가 유효하지 않습니다."}
        elif e.code == 403:
            return {"success": False, "error": "API 사용 제한을 초과했습니다. (무료 티어: 일 250회)"}
        return {"success": False, "error": f"HTTP 오류: {e.code}"}
    except Exception as e:
        return {"success": False, "error": f"요청 오류: {str(e)}"}


def get_company_profile(symbol: str):
    """
    미국 기업 프로필 조회

    Args:
        symbol: 티커 심볼 (예: AAPL, MSFT)

    Returns:
        기업 기본 정보 (업종, 시가총액, CEO, 사업설명 등)
    """
    symbol = symbol.upper()
    result = _api_request(f"profile/{symbol}")

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
            "market_cap": company.get("mktCap"),
            "beta": company.get("beta"),
            "volume_avg": company.get("volAvg"),
            "last_dividend": company.get("lastDiv"),
            "range_52week": company.get("range"),
            "changes": company.get("changes"),
            "currency": company.get("currency"),
            "exchange": company.get("exchangeShortName"),
            "industry": company.get("industry"),
            "sector": company.get("sector"),
            "country": company.get("country"),
            "employees": company.get("fullTimeEmployees"),
            "ceo": company.get("ceo"),
            "phone": company.get("phone"),
            "address": company.get("address"),
            "city": company.get("city"),
            "state": company.get("state"),
            "website": company.get("website"),
            "description": company.get("description"),
            "ipo_date": company.get("ipoDate"),
            "is_etf": company.get("isEtf"),
            "is_actively_trading": company.get("isActivelyTrading")
        },
        "summary": f"{company.get('companyName')} ({symbol}) - {company.get('sector')}/{company.get('industry')}, 시가총액: ${company.get('mktCap', 0):,.0f}"
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

    # 엔드포인트 결정
    endpoint_map = {
        "income": "income-statement",
        "balance": "balance-sheet-statement",
        "cashflow": "cash-flow-statement"
    }

    endpoint = endpoint_map.get(statement_type, "income-statement")

    params = {"limit": limit}
    if period == "quarter":
        params["period"] = "quarter"

    result = _api_request(f"{endpoint}/{symbol}", params)

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

    params = {
        "from": start_date,
        "to": end_date
    }

    result = _api_request(f"historical-price-full/{symbol}", params)

    if not result.get("success"):
        return result

    data = result["data"]
    if not data or "historical" not in data:
        return {
            "success": False,
            "error": f"'{symbol}'의 주가 데이터를 찾을 수 없습니다."
        }

    historical = data.get("historical", [])

    # 데이터 정리 (최신 순 → 오래된 순)
    prices = []
    for item in reversed(historical):
        prices.append({
            "date": item.get("date"),
            "open": item.get("open"),
            "high": item.get("high"),
            "low": item.get("low"),
            "close": item.get("close"),
            "adj_close": item.get("adjClose"),
            "volume": item.get("volume"),
            "change": item.get("change"),
            "change_percent": item.get("changePercent")
        })

    latest = prices[-1] if prices else {}

    return {
        "success": True,
        "data": {
            "symbol": symbol,
            "start_date": start_date,
            "end_date": end_date,
            "latest": latest,
            "prices": prices[-30:]  # 최근 30일
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
    result = _api_request(f"quote/{symbol}")

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
            "name": quote.get("name"),
            "price": quote.get("price"),
            "change": quote.get("change"),
            "change_percent": quote.get("changesPercentage"),
            "day_low": quote.get("dayLow"),
            "day_high": quote.get("dayHigh"),
            "year_low": quote.get("yearLow"),
            "year_high": quote.get("yearHigh"),
            "market_cap": quote.get("marketCap"),
            "volume": quote.get("volume"),
            "avg_volume": quote.get("avgVolume"),
            "open": quote.get("open"),
            "previous_close": quote.get("previousClose"),
            "eps": quote.get("eps"),
            "pe": quote.get("pe"),
            "earnings_announcement": quote.get("earningsAnnouncement"),
            "shares_outstanding": quote.get("sharesOutstanding"),
            "timestamp": quote.get("timestamp")
        },
        "summary": f"{quote.get('name')} ({symbol}): ${quote.get('price')} ({'+' if quote.get('change', 0) >= 0 else ''}{quote.get('change')}, {'+' if quote.get('changesPercentage', 0) >= 0 else ''}{quote.get('changesPercentage'):.2f}%)"
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

    params = {"limit": limit}
    if period == "quarter":
        params["period"] = "quarter"

    result = _api_request(f"key-metrics/{symbol}", params)

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
