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

from common.response_formatter import save_large_data


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


def get_crypto_price(coin_id: str = "bitcoin") -> dict:
    """
    CoinGecko API를 통해 암호화폐 가격 조회 (무료, API 키 불필요)
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

        return {
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

    except requests.exceptions.Timeout:
        return {"success": False, "error": "CoinGecko API 요청 시간 초과"}
    except Exception as e:
        return {"success": False, "error": f"암호화폐 정보 조회 실패: {str(e)}"}


def get_stock_price(symbol: str, period: str = "5d", interval: str = "1d") -> dict:
    """
    Yahoo Finance를 통해 주식/ETF 가격 조회
    """
    # 암호화폐 심볼인 경우 CoinGecko API 사용
    crypto_symbols = ["BTC", "ETH", "XRP", "DOGE", "ADA", "SOL", "DOT", "MATIC", "AVAX",
                      "LINK", "UNI", "ATOM", "LTC", "BCH", "BNB", "SHIB"]
    symbol_upper = symbol.upper().replace("-USD", "").replace("-KRW", "")
    if symbol_upper in crypto_symbols or "-USD" in symbol.upper() or "-KRW" in symbol.upper():
        return get_crypto_price(symbol)

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

        # 50개 초과 시 파일로 저장 + 샘플 제공
        if total_days > 50:
            file_path = save_large_data(all_history, "investment", f"yf_prices_{symbol.upper().replace('=', '_')}")

            # 시각화용 샘플 (10개 포인트)
            step = max(1, total_days // 10)
            sample = all_history[::step]
            if sample[-1] != all_history[-1]:
                sample.append(all_history[-1])
            sample_compact = [{"date": p["date"], "close": p["close"]} for p in sample]

            base_data["file_path"] = file_path
            base_data["sample"] = sample_compact

            return {
                "success": True,
                "data": base_data,
                "summary": f"{msg}, 기간: {all_history[0]['date']} ~ {all_history[-1]['date']}, 총 {total_days}거래일. 전체 데이터: {file_path}. 차트 생성 시 line_chart 도구에 data_file 파라미터로 이 경로를 전달하세요."
            }
        else:
            # 50개 이하: 직접 prices 배열 반환
            compact_prices = [{"date": p["date"], "close": p["close"]} for p in all_history]
            base_data["prices"] = compact_prices

            return {
                "success": True,
                "data": base_data,
                "summary": f"{msg}, 총 {total_days}거래일. 차트 생성 시 line_chart 도구의 data 파라미터에 prices 배열을 전달하세요."
            }

    except Exception as e:
        return {"success": False, "error": f"주식 정보 조회 실패: {str(e)}"}


def get_stock_info(symbol: str) -> dict:
    """
    Yahoo Finance를 통해 종목 상세 정보 조회
    """
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


def search_stock(query: str, search_type: str = "quotes") -> dict:
    """
    Yahoo Finance에서 종목 검색
    """
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
            news_list.append({
                "title": item.get("title", ""),
                "publisher": item.get("publisher", ""),
                "link": item.get("link", ""),
                "published": datetime.fromtimestamp(item.get("providerPublishTime", 0)).strftime("%Y-%m-%d %H:%M") if item.get("providerPublishTime") else "",
                "type": item.get("type", "")
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
