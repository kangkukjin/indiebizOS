"""
Yahoo Finance & CoinGecko 기반 주식/암호화폐 도구
"""
import os
import sys
import json
import requests
from datetime import datetime

# common 유틸리티 사용
_backend_dir = os.path.join(os.path.dirname(__file__), "..", "..", "..", "..", "backend")
if _backend_dir not in sys.path:
    sys.path.insert(0, os.path.abspath(_backend_dir))

from common.response_formatter import save_large_data, downsample_prices, compact_price_series


def _format_number(num):
    """숫자를 읽기 쉬운 형태로 포맷"""
    if num is None:
        return None
    if num >= 1_000_000_000_000:
        return f"{num/1_000_000_000_000:.2f}T"
    elif num >= 1_000_000_000:
        return f"{num/1_000_000_000:.2f}B"
    elif num >= 1_000_000:
        return f"{num/1_000_000:.2f}M"
    elif num >= 1_000:
        return f"{num/1_000:.2f}K"
    return str(num)


def get_crypto_price(coin_id: str = "bitcoin", days: int = 0, max_points: int = 400) -> dict:
    """
    CoinGecko API를 통해 암호화폐 가격 조회 (무료, API 키 불필요)

    days > 0 이면 market_chart로 일별 시세 이력을 받아 data.prices([{date, close}])에 추가.
    max_points 초과 시 다운샘플.
    """
    symbol_map = {
        "BTC": "bitcoin", "BITCOIN": "bitcoin",
        "ETH": "ethereum", "ETHEREUM": "ethereum",
        "XRP": "ripple", "RIPPLE": "ripple",
        "DOGE": "dogecoin", "DOGECOIN": "dogecoin",
        "ADA": "cardano", "CARDANO": "cardano",
        "SOL": "solana", "SOLANA": "solana",
        "DOT": "polkadot", "POLKADOT": "polkadot",
        "MATIC": "matic-network", "POLYGON": "matic-network",
        "AVAX": "avalanche-2", "AVALANCHE": "avalanche-2",
        "LINK": "chainlink", "CHAINLINK": "chainlink",
        "UNI": "uniswap", "UNISWAP": "uniswap",
        "ATOM": "cosmos", "COSMOS": "cosmos",
        "LTC": "litecoin", "LITECOIN": "litecoin",
        "BCH": "bitcoin-cash",
        "BNB": "binancecoin", "BINANCE": "binancecoin",
        "SHIB": "shiba-inu", "SHIBA": "shiba-inu",
    }

    coin = coin_id.upper().replace("-USD", "").replace("-KRW", "")
    coin_id_resolved = symbol_map.get(coin, coin_id.lower())

    try:
        url = f"https://api.coingecko.com/api/v3/coins/{coin_id_resolved}"
        params = {
            "localization": "false",
            "tickers": "false",
            "market_data": "true",
            "community_data": "false",
            "developer_data": "false"
        }

        response = requests.get(url, params=params, timeout=15)

        if response.status_code == 404:
            return {"success": False, "error": f"'{coin_id}' 암호화폐를 찾을 수 없습니다."}
        elif response.status_code != 200:
            return {"success": False, "error": f"CoinGecko API 오류: {response.status_code}"}

        data = response.json()
        market = data.get("market_data", {})

        current_price_usd = market.get("current_price", {}).get("usd", 0)
        current_price_krw = market.get("current_price", {}).get("krw", 0)
        change_24h = market.get("price_change_percentage_24h", 0)

        direction = "▲" if change_24h and change_24h >= 0 else "▼"

        result = {
            "success": True,
            "data": {
                "symbol": data.get("symbol", "").upper(),
                "name": data.get("name", ""),
                "current_price_usd": current_price_usd,
                "current_price_krw": current_price_krw,
                "change_24h_percent": round(change_24h, 2) if change_24h else 0,
                "market_cap_usd": market.get("market_cap", {}).get("usd"),
                "market_cap_formatted": _format_number(market.get("market_cap", {}).get("usd")),
                "volume_24h_usd": market.get("total_volume", {}).get("usd"),
                "high_24h_usd": market.get("high_24h", {}).get("usd"),
                "low_24h_usd": market.get("low_24h", {}).get("usd"),
                "ath_usd": market.get("ath", {}).get("usd"),
                "rank": data.get("market_cap_rank"),
                "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            },
            "message": f"{data.get('name', '')} ({data.get('symbol', '').upper()}): ${current_price_usd:,.2f} ({current_price_krw:,.0f}원) {direction} {abs(change_24h):.2f}% (24h)"
        }

        # 이력 차트용 일별 시세 (선택)
        if days and days > 0:
            try:
                chart_resp = requests.get(
                    f"https://api.coingecko.com/api/v3/coins/{coin_id_resolved}/market_chart",
                    params={"vs_currency": "usd", "days": days, "interval": "daily"},
                    timeout=15,
                )
                if chart_resp.status_code == 200:
                    raw = chart_resp.json().get("prices", [])
                    pts = [
                        {"date": datetime.fromtimestamp(ts / 1000).strftime("%Y-%m-%d"),
                         "close": round(price, 6)}
                        for ts, price in raw
                    ]
                    if max_points and len(pts) > max_points:
                        step = max(1, len(pts) // max_points)
                        pts = pts[::step]
                    result["data"]["prices"] = pts
            except Exception:
                pass  # 이력 실패해도 현재가는 정상 반환

        return result

    except requests.exceptions.Timeout:
        return {"success": False, "error": "CoinGecko API 요청 시간 초과"}
    except Exception as e:
        return {"success": False, "error": f"암호화폐 정보 조회 실패: {str(e)}"}


def _normalize_symbol(symbol: str) -> str:
    """AI가 자주 틀리는 심볼을 자동 보정

    - 한국 시장 지수명 → yfinance 심볼 (KOSPI → ^KS11)
    - 한국 6자리 종목코드 → .KS 접미사 (005930 → 005930.KS)
    - 이미 올바른 심볼은 그대로 반환
    """
    if not symbol:
        raise ValueError("symbol 파라미터가 필요합니다.")
    s = symbol.strip()

    # 0) 원자재(선물) 한글/영문 별칭 → Yahoo 선물 심볼 (호출자가 GC=F 등을 몰라도 됨)
    _COMMODITY_MAP = {
        "금": "GC=F", "금값": "GC=F", "골드": "GC=F", "gold": "GC=F",
        "은": "SI=F", "은값": "SI=F", "실버": "SI=F", "silver": "SI=F",
        "유가": "CL=F", "원유": "CL=F", "wti": "CL=F", "crude": "CL=F", "oil": "CL=F",
        "브렌트": "BZ=F", "브렌트유": "BZ=F", "brent": "BZ=F",
        "천연가스": "NG=F", "가스": "NG=F", "natgas": "NG=F",
        "구리": "HG=F", "동": "HG=F", "copper": "HG=F",
    }
    commodity = _COMMODITY_MAP.get(s) or _COMMODITY_MAP.get(s.lower())
    if commodity:
        return commodity

    # 1) 시장 지수 별명 → yfinance 심볼
    _INDEX_MAP = {
        "KOSPI": "^KS11", "코스피": "^KS11", "KS11": "^KS11",
        "KOSDAQ": "^KQ11", "코스닥": "^KQ11", "KQ11": "^KQ11",
        "KS200": "^KS200", "KOSPI200": "^KS200",
        "001": "^KS11",   # KRX 내부 코드
        "101": "^KQ11",   # KRX 내부 코드
    }
    mapped = _INDEX_MAP.get(s.upper()) or _INDEX_MAP.get(s)
    if mapped:
        return mapped

    # 2) 한국 종목코드 (6자리 숫자) → .KS 자동 붙이기
    #    이미 .KS/.KQ 있으면 패스, ^로 시작하면 지수이므로 패스
    if s.replace(".", "").isdigit() and len(s) == 6 and not s.startswith("^"):
        return f"{s}.KS"

    return s


def get_stock_price(symbol: str, period: str = "5d", interval: str = "1d", max_points: int = 10) -> dict:
    """
    Yahoo Finance를 통해 주식/ETF/원자재(선물) 가격 조회
    """
    if not symbol:
        return {"success": False, "error": "symbol 파라미터가 필요합니다."}

    # 암호화폐 심볼인 경우 CoinGecko API 사용
    crypto_symbols = ["BTC", "ETH", "XRP", "DOGE", "ADA", "SOL", "DOT", "MATIC", "AVAX",
                      "LINK", "UNI", "ATOM", "LTC", "BCH", "BNB", "SHIB"]
    symbol_upper = symbol.upper().replace("-USD", "").replace("-KRW", "")
    if symbol_upper in crypto_symbols or "-USD" in symbol.upper() or "-KRW" in symbol.upper():
        return get_crypto_price(symbol)

    # 심볼 자동 보정 (KOSPI → ^KS11, 005930 → 005930.KS 등)
    original_symbol = symbol
    symbol = _normalize_symbol(symbol)
    if symbol != original_symbol:
        print(f"[yfinance] 심볼 보정: {original_symbol} → {symbol}")

    try:
        import yfinance as yf
    except ImportError:
        return {"success": False, "error": "yfinance 라이브러리가 설치되지 않았습니다. pip install yfinance 실행 필요"}

    try:
        ticker = yf.Ticker(symbol)
        hist = ticker.history(period=period, interval=interval)

        if hist.empty:
            return {"success": False, "error": f"'{symbol}' 종목을 찾을 수 없거나 데이터가 없습니다."}

        latest = hist.iloc[-1]
        current_price = latest["Close"]
        prev_close = hist.iloc[-2]["Close"] if len(hist) >= 2 else current_price

        if prev_close and prev_close > 0:
            change = current_price - prev_close
            change_percent = (change / prev_close) * 100
        else:
            change = 0
            change_percent = 0

        # 전체 히스토리 데이터 구성
        all_history = []
        for idx, row in hist.iterrows():
            all_history.append({
                "date": idx.strftime("%Y-%m-%d"),
                "open": round(row["Open"], 2),
                "high": round(row["High"], 2),
                "low": round(row["Low"], 2),
                "close": round(row["Close"], 2),
                "volume": int(row["Volume"])
            })

        direction = "▲" if change >= 0 else "▼"
        currency = "KRW" if symbol.endswith((".KS", ".KQ")) else "USD"
        total_days = len(all_history)

        base_data = {
            "symbol": symbol.upper(),
            "current_price": round(current_price, 2),
            "currency": currency,
            "change": round(change, 2),
            "change_percent": round(change_percent, 2),
            "previous_close": round(prev_close, 2),
            "open": round(latest.get("Open", 0), 2),
            "high": round(latest.get("High", 0), 2),
            "low": round(latest.get("Low", 0), 2),
            "volume": int(latest.get("Volume", 0)),
            "period": period,
            "total_days": total_days,
            "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        }

        msg = f"{symbol.upper()}: {round(current_price, 2)} {currency} {direction} {abs(round(change, 2))} ({change_percent:+.2f}%)"

        # prices는 항상 포함(shape 일관). 50일 이하면 전체, 초과면 다운샘플 + 전체는 file_path.
        compact, truncated = compact_price_series(all_history, max_points)
        base_data["prices"] = compact
        base_data["truncated"] = truncated
        if truncated:
            file_path = save_large_data(all_history, "investment", f"yf_prices_{symbol.upper().replace('=', '_')}")
            base_data["file_path"] = file_path     # 전체 데이터 파일 경로 (시각화 data_file용)
            base_data["sample"] = compact          # 하위호환 별칭
            summary = f"{msg}, 기간: {all_history[0]['date']} ~ {all_history[-1]['date']}, 총 {total_days}거래일. 전체 데이터: {file_path}. 차트 생성 시 line_chart 도구에 data_file 파라미터로 이 경로를 전달하세요."
        elif total_days > 20:
            # 충분한 시계열 → 차트 안내
            summary = f"{msg}, 총 {total_days}거래일. 차트 생성 시 line_chart 도구의 data 파라미터에 prices 배열을 전달하세요."
        else:
            # 짧은 현재가 조회(기본 5일) → 현재가 중심 요약 (차트 안내 생략, prices는 최근 맥락일 뿐)
            summary = f"현재가 {round(current_price, 2)} {currency} {direction} {abs(round(change, 2))} ({change_percent:+.2f}%), 전일 {round(prev_close, 2)}. 최근 {total_days}거래일 시세 포함."
        return {"success": True, "data": base_data, "summary": summary}

    except Exception as e:
        return {"success": False, "error": f"주식 정보 조회 실패: {str(e)}"}


def get_stock_info(symbol: str) -> dict:
    """
    Yahoo Finance를 통해 종목 상세 정보 조회
    """
    if not symbol:
        return {"success": False, "error": "symbol 파라미터가 필요합니다."}
    symbol = _normalize_symbol(symbol)

    try:
        import yfinance as yf
    except ImportError:
        return {"success": False, "error": "yfinance 라이브러리가 설치되지 않았습니다."}

    try:
        ticker = yf.Ticker(symbol)
        fast = ticker.fast_info
        hist = ticker.history(period="1y")

        if hist.empty:
            return {"success": False, "error": f"'{symbol}' 종목 정보를 찾을 수 없습니다."}

        latest = hist.iloc[-1]
        year_high = hist["High"].max()
        year_low = hist["Low"].min()

        return {
            "success": True,
            "data": {
                "symbol": symbol.upper(),
                "currency": "KRW" if symbol.endswith((".KS", ".KQ")) else "USD",
                "current_price": round(latest["Close"], 2),
                "market_cap": getattr(fast, 'market_cap', None),
                "market_cap_formatted": _format_number(getattr(fast, 'market_cap', None)),
                "52_week_high": round(year_high, 2),
                "52_week_low": round(year_low, 2),
                "50_day_avg": round(hist.tail(50)["Close"].mean(), 2) if len(hist) >= 50 else None,
                "200_day_avg": round(hist.tail(200)["Close"].mean(), 2) if len(hist) >= 200 else None,
                "volume": int(latest.get("Volume", 0)),
                "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            }
        }

    except Exception as e:
        return {"success": False, "error": f"종목 정보 조회 실패: {str(e)}"}


def _search_kr_stocks(query: str) -> list:
    """한글 회사명 → KRX 종목코드 내부 해소 (yfinance는 영어 검색만 되므로).
    KRX 종목코드 맵(이름→코드)에서 정확 일치 우선, 부분 일치 보조."""
    try:
        from tool_krx import _load_stock_codes
        codes = _load_stock_codes()  # {회사명: 6자리코드}
    except Exception:
        return []
    q = query.strip()
    exact = [(n, c) for n, c in codes.items() if n == q]
    partial = [(n, c) for n, c in codes.items() if q in n and n != q]
    hits = (exact + partial)[:10]
    return [{"symbol": c, "name": n, "exchange": "KRX", "type": "EQUITY"} for n, c in hits]


def search_stock(query: str, search_type: str = "quotes") -> dict:
    """
    Yahoo Finance에서 종목 검색
    """
    # 한글 회사명은 yfinance 검색이 안 되므로 KRX 종목코드 맵으로 먼저 해소
    if search_type == "quotes" and query and any('가' <= ch <= '힣' for ch in query):
        kr = _search_kr_stocks(query)
        if kr:
            return {"success": True, "data": {"query": query, "count": len(kr), "quotes": kr}}

    try:
        import yfinance as yf
    except ImportError:
        return {"success": False, "error": "yfinance 라이브러리가 설치되지 않았습니다."}

    try:
        search = yf.Search(query)

        if search_type == "all":
            return {
                "success": True,
                "data": {
                    "query": query,
                    "quotes": search.quotes[:10] if search.quotes else [],
                    "news": search.news[:5] if search.news else []
                }
            }
        elif search_type == "news":
            return {
                "success": True,
                "data": {
                    "query": query,
                    "count": len(search.news) if search.news else 0,
                    "news": search.news[:10] if search.news else []
                }
            }
        else:
            quotes = []
            for q in (search.quotes or [])[:10]:
                quotes.append({
                    "symbol": q.get("symbol", ""),
                    "name": q.get("shortname") or q.get("longname", ""),
                    "exchange": q.get("exchange", ""),
                    "type": q.get("quoteType", "")
                })
            return {
                "success": True,
                "data": {
                    "query": query,
                    "count": len(quotes),
                    "quotes": quotes
                }
            }

    except Exception as e:
        return {"success": False, "error": f"종목 검색 실패: {str(e)}"}


def get_stock_news(symbol: str) -> dict:
    """
    Yahoo Finance에서 종목 관련 뉴스 조회
    """
    try:
        import yfinance as yf
    except ImportError:
        return {"success": False, "error": "yfinance 라이브러리가 설치되지 않았습니다."}

    try:
        ticker = yf.Ticker(symbol)
        news = ticker.news

        if not news:
            return {"success": True, "data": {"symbol": symbol.upper(), "count": 0, "news": []}}

        news_list = []
        for item in news[:10]:
            # 예전 구조 호환성 (yfinance 하위 버전)
            if "title" in item:
                news_list.append({
                    "title": item.get("title", ""),
                    "publisher": item.get("publisher", ""),
                    "link": item.get("link", ""),
                    "published": datetime.fromtimestamp(item.get("providerPublishTime", 0)).strftime("%Y-%m-%d %H:%M") if item.get("providerPublishTime") else "",
                    "type": item.get("type", "")
                })
            # 새로운 구조 (최신 yfinance 버전)
            elif "content" in item:
                content_dict = item.get("content") or {}
                provider = content_dict.get("provider") or {}
                click_through = content_dict.get("clickThroughUrl") or {}
                news_list.append({
                    "title": content_dict.get("title", ""),
                    "publisher": provider.get("displayName", ""),
                    "link": click_through.get("url", ""),
                    "published": content_dict.get("pubDate", ""),
                    "type": content_dict.get("contentType", "")
                })

        return {
            "success": True,
            "data": {
                "symbol": symbol.upper(),
                "count": len(news_list),
                "news": news_list
            }
        }

    except Exception as e:
        return {"success": False, "error": f"뉴스 조회 실패: {str(e)}"}
