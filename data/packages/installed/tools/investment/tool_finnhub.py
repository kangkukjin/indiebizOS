"""
Finnhub 도구
기업 뉴스 및 실적발표 일정을 조회합니다.

API 문서: https://finnhub.io/docs/api
필요 환경변수: FINNHUB_API_KEY
무료 티어: 분당 60회 제한
"""
import os
import urllib.request
import urllib.parse
import json
from datetime import datetime, timedelta

FINNHUB_API_KEY = os.environ.get("FINNHUB_API_KEY", "")
BASE_URL = "https://finnhub.io/api/v1"


def _check_api_key():
    """API 키 확인"""
    if not FINNHUB_API_KEY:
        return {
            "success": False,
            "error": "FINNHUB_API_KEY 환경변수가 설정되지 않았습니다. https://finnhub.io 에서 무료 API 키를 발급받으세요."
        }
    return None


def _api_request(endpoint: str, params: dict = None):
    """Finnhub API 요청"""
    error = _check_api_key()
    if error:
        return error

    if params is None:
        params = {}
    params["token"] = FINNHUB_API_KEY

    url = f"{BASE_URL}/{endpoint}?" + urllib.parse.urlencode(params)

    try:
        req = urllib.request.Request(url)
        req.add_header("User-Agent", "Mozilla/5.0")

        with urllib.request.urlopen(req, timeout=30) as response:
            data = json.loads(response.read().decode('utf-8'))

        # 에러 응답 확인
        if isinstance(data, dict) and "error" in data:
            return {
                "success": False,
                "error": data["error"]
            }

        return {"success": True, "data": data}

    except urllib.error.HTTPError as e:
        if e.code == 401:
            return {"success": False, "error": "API 키가 유효하지 않습니다."}
        elif e.code == 429:
            return {"success": False, "error": "API 요청 제한을 초과했습니다. (무료 티어: 분당 60회)"}
        return {"success": False, "error": f"HTTP 오류: {e.code}"}
    except Exception as e:
        return {"success": False, "error": f"요청 오류: {str(e)}"}


def get_company_news(symbol: str, start_date: str = None, end_date: str = None):
    """
    기업 관련 뉴스 조회

    Args:
        symbol: 티커 심볼 (미국: AAPL, 한국: 005930.KS)
        start_date: 검색 시작일 (YYYY-MM-DD)
        end_date: 검색 종료일 (YYYY-MM-DD)

    Returns:
        뉴스 목록
    """
    symbol = symbol.upper()

    # 날짜 기본값
    if not end_date:
        end_date = datetime.now().strftime("%Y-%m-%d")
    if not start_date:
        start_date = (datetime.now() - timedelta(days=7)).strftime("%Y-%m-%d")

    params = {
        "symbol": symbol,
        "from": start_date,
        "to": end_date
    }

    result = _api_request("company-news", params)

    if not result.get("success"):
        return result

    data = result["data"]

    if not data:
        return {
            "success": True,
            "data": {
                "symbol": symbol,
                "news": [],
                "count": 0
            },
            "summary": f"{symbol}의 뉴스가 없습니다. ({start_date} ~ {end_date})"
        }

    # 뉴스 정리
    news = []
    for item in data[:20]:  # 최대 20개
        news.append({
            "headline": item.get("headline"),
            "summary": item.get("summary", "")[:300],
            "source": item.get("source"),
            "url": item.get("url"),
            "datetime": datetime.fromtimestamp(item.get("datetime", 0)).strftime("%Y-%m-%d %H:%M") if item.get("datetime") else "",
            "category": item.get("category"),
            "related": item.get("related")
        })

    return {
        "success": True,
        "data": {
            "symbol": symbol,
            "start_date": start_date,
            "end_date": end_date,
            "news": news,
            "count": len(news)
        },
        "summary": f"{symbol}의 뉴스 {len(news)}건 조회 ({start_date} ~ {end_date})"
    }


def get_earnings_calendar(symbol: str = None, start_date: str = None, end_date: str = None):
    """
    실적발표 일정 조회

    Args:
        symbol: 티커 심볼 (선택사항). 없으면 전체 시장
        start_date: 검색 시작일 (YYYY-MM-DD)
        end_date: 검색 종료일 (YYYY-MM-DD)

    Returns:
        실적발표 일정
    """
    # 날짜 기본값
    if not end_date:
        end_date = (datetime.now() + timedelta(days=14)).strftime("%Y-%m-%d")
    if not start_date:
        start_date = datetime.now().strftime("%Y-%m-%d")

    params = {
        "from": start_date,
        "to": end_date
    }

    if symbol:
        params["symbol"] = symbol.upper()

    result = _api_request("calendar/earnings", params)

    if not result.get("success"):
        return result

    data = result["data"]
    earnings = data.get("earningsCalendar", [])

    if not earnings:
        return {
            "success": True,
            "data": {
                "symbol": symbol,
                "earnings": [],
                "count": 0
            },
            "summary": f"실적발표 일정이 없습니다. ({start_date} ~ {end_date})"
        }

    # 특정 종목 필터링
    if symbol:
        earnings = [e for e in earnings if e.get("symbol", "").upper() == symbol.upper()]

    # 일정 정리
    calendar = []
    for item in earnings[:30]:  # 최대 30개
        calendar.append({
            "symbol": item.get("symbol"),
            "date": item.get("date"),
            "hour": item.get("hour"),  # bmo(시장전), amc(시장후), dmh(시간미정)
            "eps_estimate": item.get("epsEstimate"),
            "eps_actual": item.get("epsActual"),
            "revenue_estimate": item.get("revenueEstimate"),
            "revenue_actual": item.get("revenueActual"),
            "quarter": item.get("quarter"),
            "year": item.get("year")
        })

    # 날짜순 정렬
    calendar.sort(key=lambda x: x.get("date", ""))

    return {
        "success": True,
        "data": {
            "symbol": symbol,
            "start_date": start_date,
            "end_date": end_date,
            "earnings": calendar,
            "count": len(calendar)
        },
        "summary": f"실적발표 일정 {len(calendar)}건 ({start_date} ~ {end_date})"
    }


def get_market_news(category: str = "general"):
    """
    시장 뉴스 조회

    Args:
        category: general, forex, crypto, merger

    Returns:
        시장 뉴스 목록
    """
    params = {"category": category}

    result = _api_request("news", params)

    if not result.get("success"):
        return result

    data = result["data"]

    if not data:
        return {
            "success": True,
            "data": {
                "category": category,
                "news": [],
                "count": 0
            },
            "summary": f"{category} 카테고리의 뉴스가 없습니다."
        }

    # 뉴스 정리
    news = []
    for item in data[:20]:
        news.append({
            "headline": item.get("headline"),
            "summary": item.get("summary", "")[:300],
            "source": item.get("source"),
            "url": item.get("url"),
            "datetime": datetime.fromtimestamp(item.get("datetime", 0)).strftime("%Y-%m-%d %H:%M") if item.get("datetime") else "",
            "category": item.get("category")
        })

    return {
        "success": True,
        "data": {
            "category": category,
            "news": news,
            "count": len(news)
        },
        "summary": f"{category} 시장 뉴스 {len(news)}건 조회"
    }


def get_company_profile(symbol: str):
    """
    기업 프로필 조회 (Finnhub)

    Args:
        symbol: 티커 심볼

    Returns:
        기업 기본 정보
    """
    symbol = symbol.upper()
    params = {"symbol": symbol}

    result = _api_request("stock/profile2", params)

    if not result.get("success"):
        return result

    data = result["data"]

    if not data or not data.get("name"):
        return {
            "success": False,
            "error": f"'{symbol}'에 해당하는 기업을 찾을 수 없습니다."
        }

    return {
        "success": True,
        "data": {
            "symbol": data.get("ticker"),
            "name": data.get("name"),
            "country": data.get("country"),
            "currency": data.get("currency"),
            "exchange": data.get("exchange"),
            "industry": data.get("finnhubIndustry"),
            "ipo_date": data.get("ipo"),
            "logo": data.get("logo"),
            "market_cap": data.get("marketCapitalization"),
            "shares_outstanding": data.get("shareOutstanding"),
            "phone": data.get("phone"),
            "website": data.get("weburl")
        },
        "summary": f"{data.get('name')} ({symbol}) - {data.get('finnhubIndustry')}, 시가총액: ${data.get('marketCapitalization', 0):,.0f}M"
    }


def get_recommendation_trends(symbol: str):
    """
    애널리스트 추천 동향 조회

    Args:
        symbol: 티커 심볼

    Returns:
        애널리스트 추천 (매수/보유/매도)
    """
    symbol = symbol.upper()
    params = {"symbol": symbol}

    result = _api_request("stock/recommendation", params)

    if not result.get("success"):
        return result

    data = result["data"]

    if not data:
        return {
            "success": False,
            "error": f"'{symbol}'의 애널리스트 추천 정보가 없습니다."
        }

    # 최근 6개월 데이터
    trends = []
    for item in data[:6]:
        trends.append({
            "period": item.get("period"),
            "strong_buy": item.get("strongBuy"),
            "buy": item.get("buy"),
            "hold": item.get("hold"),
            "sell": item.get("sell"),
            "strong_sell": item.get("strongSell")
        })

    latest = trends[0] if trends else {}
    total = (latest.get("strong_buy", 0) + latest.get("buy", 0) +
             latest.get("hold", 0) + latest.get("sell", 0) + latest.get("strong_sell", 0))

    buy_ratio = ((latest.get("strong_buy", 0) + latest.get("buy", 0)) / total * 100) if total > 0 else 0

    return {
        "success": True,
        "data": {
            "symbol": symbol,
            "trends": trends
        },
        "summary": f"{symbol} 애널리스트 추천 - 매수 {buy_ratio:.0f}% (Strong Buy: {latest.get('strong_buy', 0)}, Buy: {latest.get('buy', 0)}, Hold: {latest.get('hold', 0)}, Sell: {latest.get('sell', 0)})"
    }


def get_price_target(symbol: str):
    """
    애널리스트 목표가 조회

    Args:
        symbol: 티커 심볼

    Returns:
        목표가 정보
    """
    symbol = symbol.upper()
    params = {"symbol": symbol}

    result = _api_request("stock/price-target", params)

    if not result.get("success"):
        return result

    data = result["data"]

    if not data or not data.get("targetHigh"):
        return {
            "success": False,
            "error": f"'{symbol}'의 목표가 정보가 없습니다."
        }

    return {
        "success": True,
        "data": {
            "symbol": symbol,
            "target_high": data.get("targetHigh"),
            "target_low": data.get("targetLow"),
            "target_mean": data.get("targetMean"),
            "target_median": data.get("targetMedian"),
            "last_updated": data.get("lastUpdated")
        },
        "summary": f"{symbol} 목표가 - 평균: ${data.get('targetMean', 'N/A')}, 범위: ${data.get('targetLow', 'N/A')} ~ ${data.get('targetHigh', 'N/A')}"
    }
