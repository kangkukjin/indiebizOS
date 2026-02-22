"""
Finnhub 도구
기업 뉴스 및 실적발표 일정을 조회합니다.

API 문서: https://finnhub.io/docs/api
필요 환경변수: FINNHUB_API_KEY
무료 티어: 분당 60회 제한
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
    """Finnhub API 요청 (common.api_client 위임)"""
    result = api_call("finnhub", f"/{endpoint}", params=params or {}, timeout=30)
    # api_call은 에러 시 {"error": "..."} 반환
    if isinstance(result, dict) and "error" in result:
        return {"success": False, "error": result["error"]}
    return {"success": True, "data": result}


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
    for item in data:
        news.append({
            "headline": item.get("headline"),
            "summary": item.get("summary", ""),
            "source": item.get("source"),
            "url": item.get("url"),
            "datetime": datetime.fromtimestamp(item.get("datetime", 0)).strftime("%Y-%m-%d %H:%M") if item.get("datetime") else "",
            "category": item.get("category"),
            "related": item.get("related")
        })

    total_count = len(news)

    # 대량 데이터는 파일로 저장 (20개 초과시)
    if total_count > 20:
        file_path = save_large_data(news, "investment", f"company_news_{symbol}")

        # 최근 5개만 요약으로 반환
        return {
            "success": True,
            "data": {
                "symbol": symbol,
                "start_date": start_date,
                "end_date": end_date,
                "count": total_count,
                "file_path": file_path,
                "sample": news[:5]
            },
            "summary": f"{symbol}의 뉴스 {total_count}건 조회 ({start_date} ~ {end_date}). 전체 데이터: {file_path}"
        }
    else:
        return {
            "success": True,
            "data": {
                "symbol": symbol,
                "start_date": start_date,
                "end_date": end_date,
                "news": news,
                "count": total_count
            },
            "summary": f"{symbol}의 뉴스 {total_count}건 조회 ({start_date} ~ {end_date})"
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
    for item in earnings:
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
    total_count = len(calendar)

    # 대량 데이터는 파일로 저장 (30개 초과시)
    if total_count > 30:
        file_path = save_large_data(calendar, "investment", f"earnings_{symbol or 'market'}")

        return {
            "success": True,
            "data": {
                "symbol": symbol,
                "start_date": start_date,
                "end_date": end_date,
                "count": total_count,
                "file_path": file_path,
                "sample": calendar[:10]
            },
            "summary": f"실적발표 일정 {total_count}건 ({start_date} ~ {end_date}). 전체 데이터: {file_path}"
        }
    else:
        return {
            "success": True,
            "data": {
                "symbol": symbol,
                "start_date": start_date,
                "end_date": end_date,
                "earnings": calendar,
                "count": total_count
            },
            "summary": f"실적발표 일정 {total_count}건 ({start_date} ~ {end_date})"
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
    for item in data:
        news.append({
            "headline": item.get("headline"),
            "summary": item.get("summary", ""),
            "source": item.get("source"),
            "url": item.get("url"),
            "datetime": datetime.fromtimestamp(item.get("datetime", 0)).strftime("%Y-%m-%d %H:%M") if item.get("datetime") else "",
            "category": item.get("category")
        })

    total_count = len(news)

    # 대량 데이터는 파일로 저장 (20개 초과시)
    if total_count > 20:
        file_path = save_large_data(news, "investment", f"market_news_{category}")

        return {
            "success": True,
            "data": {
                "category": category,
                "count": total_count,
                "file_path": file_path,
                "sample": news[:5]
            },
            "summary": f"{category} 시장 뉴스 {total_count}건 조회. 전체 데이터: {file_path}"
        }
    else:
        return {
            "success": True,
            "data": {
                "category": category,
                "news": news,
                "count": total_count
            },
            "summary": f"{category} 시장 뉴스 {total_count}건 조회"
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
