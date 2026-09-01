"""
Yahoo Finance & CoinGecko 기반 주식/암호화폐 도구
"""
import os
import re
import sys
import json
import requests
from datetime import datetime, timedelta, timezone

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


def _yahoo_chart(symbol: str, period: str = "5d", interval: str = "1d",
                 meta_sink: dict = None) -> list:
    """Yahoo Finance chart API 직접 호출(requests) → 일별 바 리스트.

    yfinance 라이브러리는 Yahoo 봇차단에 막히고(최신판은 curl_cffi 네이티브 의존),
    이 v8/finance/chart 엔드포인트는 브라우저 UA 헤더면 열려 있다 — 폰(Chaquopy)·데스크탑 공통.
    반환: [{date, open, high, low, close, volume}] (close 결측 바 제외).

    meta_sink(dict)를 주면 응답의 meta 블록을 담아준다 — currency/instrumentType 등
    *권위 있는* 메타데이터가 여기 있다(심볼 접미사 추측 금지)."""
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{symbol}"
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
    r = requests.get(url, params={"range": period, "interval": interval},
                     headers=headers, timeout=15)
    res = ((r.json().get("chart") or {}).get("result")) or []
    if not res:
        return []
    res0 = res[0]
    if meta_sink is not None and isinstance(res0.get("meta"), dict):
        meta_sink.update(res0["meta"])
    ts = res0.get("timestamp") or []
    q = ((res0.get("indicators") or {}).get("quote") or [{}])[0]
    o, h, l, c, v = (q.get(k) or [] for k in ("open", "high", "low", "close", "volume"))
    bars = []
    dropped = []          # close 결측 바 = '거래일인데 값이 없는 구멍'. 조용히 버리면 전일종가가 한 장 밀린다.
    for i, t in enumerate(ts):
        cl = c[i] if i < len(c) else None
        if cl is None:
            dropped.append(datetime.fromtimestamp(t, timezone.utc).strftime("%Y-%m-%d"))
            continue
        bars.append({
            "date": datetime.fromtimestamp(t, timezone.utc).strftime("%Y-%m-%d"),
            "open": round(o[i], 2) if i < len(o) and o[i] is not None else round(cl, 2),
            "high": round(h[i], 2) if i < len(h) and h[i] is not None else round(cl, 2),
            "low": round(l[i], 2) if i < len(l) and l[i] is not None else round(cl, 2),
            "close": round(cl, 2),
            "volume": int(v[i]) if i < len(v) and v[i] is not None else 0,
        })
    if meta_sink is not None:
        meta_sink["_dropped_dates"] = dropped
    return bars


# 거래소 접미사 → 표시통화 (meta.currency 를 못 얻었을 때만 쓰는 폴백).
_SUFFIX_CCY = {
    ".KS": "KRW", ".KQ": "KRW", ".T": "JPY", ".HK": "HKD", ".SS": "CNY",
    ".SZ": "CNY", ".L": "GBP", ".DE": "EUR", ".PA": "EUR", ".AS": "EUR",
    ".MI": "EUR", ".SW": "CHF", ".TO": "CAD", ".AX": "AUD", ".NS": "INR",
    ".BO": "INR", ".TW": "TWD", ".SI": "SGD", ".SA": "BRL",
}


def _resolve_currency(symbol: str, meta: dict = None) -> str:
    """이 시세의 표시통화. Yahoo meta.currency 가 **권위** — 있으면 그대로 쓴다.

    옛 코드는 `".KS/.KQ 면 KRW 아니면 USD"` 이진 추측이라 환율쌍(JPYKRW=X→KRW)과
    비미국 거래소(7203.T→JPY)를 전부 USD 로 잘못 라벨했다(에피소드 881에서 발견).
    meta 를 못 얻은 경우에만 접미사·환율쌍 규칙으로 폴백한다.
    """
    ccy = (meta or {}).get("currency")
    if isinstance(ccy, str) and ccy.strip():
        return ccy.strip().upper()

    s = (symbol or "").upper()
    # 환율쌍: "JPYKRW=X"=원/엔 → 표시통화는 뒤(quote) 통화. "KRW=X"=USD/KRW → KRW.
    if s.endswith("=X"):
        base = s[:-2]
        if len(base) == 6:
            return base[3:]
        if len(base) == 3:
            return base
        return "USD"
    for suf, c in _SUFFIX_CCY.items():
        if s.endswith(suf):
            return c
    return "USD"


# ── 네이버 실시간 오버레이 (2026-08-01) ──────────────────────────────
# Yahoo의 KRX 시세는 ~20분 지연 → 한국 종목/지수의 *현재가 스냅샷*만 네이버 폴링
# API(delayTime=0, 무키)로 덮는다. 차트용 일봉 시계열은 Yahoo 유지. 실패 시 조용히
# None → Yahoo 값 그대로(자연 폴백, kospi-board Worker와 같은 설계).
_NAVER_POLL = "https://polling.finance.naver.com/api/realtime/domestic/"
_NAVER_INDEX = {"^KS11": "index/KOSPI", "^KQ11": "index/KOSDAQ"}


def _naver_num(v):
    """숫자|콤마 문자열 관용 파서 — *Raw 필드가 호출 경로에 따라 숫자/문자열로 오는 것 실측."""
    if isinstance(v, (int, float)):
        return float(v)
    if isinstance(v, str):
        try:
            return float(v.replace(",", ""))
        except ValueError:
            return None
    return None


def _naver_realtime(symbol: str):
    """한국 종목(6자리.KS/.KQ)·코스피/코스닥 지수의 네이버 실시간 스냅샷. 비대상/실패=None."""
    s = (symbol or "").upper()
    path = _NAVER_INDEX.get(s)
    if path is None:
        m = re.match(r"^(\d{6})\.(KS|KQ)$", s)
        if not m:
            return None
        path = f"stock/{m.group(1)}"
    try:
        r = requests.get(_NAVER_POLL + path,
                         headers={"User-Agent": "Mozilla/5.0", "Accept": "application/json"},
                         timeout=5)
        if r.status_code != 200:
            return None
        d = (r.json().get("datas") or [{}])[0]
        price = _naver_num(d.get("closePriceRaw")) or _naver_num(d.get("closePrice"))
        change = _naver_num(d.get("compareToPreviousClosePriceRaw"))
        if change is None:
            change = _naver_num(d.get("compareToPreviousClosePrice"))  # 하락=음수 직접 옴(실측)
        if price is None or change is None:
            return None
        return {
            "price": price,
            "change": change,
            "change_percent": _naver_num(d.get("fluctuationsRatioRaw")) or _naver_num(d.get("fluctuationsRatio")),
            "open": _naver_num(d.get("openPriceRaw")) or _naver_num(d.get("openPrice")),
            "high": _naver_num(d.get("highPriceRaw")) or _naver_num(d.get("highPrice")),
            "low": _naver_num(d.get("lowPriceRaw")) or _naver_num(d.get("lowPrice")),
            "volume": _naver_num(d.get("accumulatedTradingVolumeRaw")),
            "quote_time": d.get("localTradedAt"),
            "market_status": d.get("marketStatus"),
        }
    except Exception:
        return None


# ── 한국 지수 일봉: 네이버 (2026-09-01) ────────────────────────────
# 지수(^KS11·^KQ11)는 quote 도 history 도 같은 Yahoo chart 를 쓰는데, Yahoo 가 한국
# 거래일을 close=null 로 통째 빠뜨린다(실측: 8/28·8/31 둘 다 null → 시계열이 8/27 에서
# 멈추고 quote 만 네이버로 앞서 나갔다). 종목은 KRX/FMP 라는 대조 소스가 있어 핸들러가
# 보정하지만 지수엔 없었다 — 그래서 일봉 자체를 네이버(무키, 같은 KRX 원천)로 바꾼다.
_NAVER_SISE = "https://api.finance.naver.com/siseJson.naver"
_NAVER_INDEX_DAILY = {"^KS11": "KOSPI", "^KQ11": "KOSDAQ", "^KS200": "KPI200"}
_PERIOD_DAYS = {"1d": 5, "5d": 10, "1mo": 31, "3mo": 93, "6mo": 186,
                "1y": 366, "2y": 731, "5y": 1827, "10y": 3653, "ytd": 366, "max": 3653}


def _naver_index_daily(symbol: str, period: str = "5d") -> list:
    """한국 지수의 일봉 시계열(네이버). 비대상·실패=[] → 호출자가 Yahoo 로 폴백.

    응답은 JSON 이 아니라 파이썬 리터럴에 가까운 텍스트(작은따옴표 헤더)라 눈으로 파싱한다.
    반환 모양은 _yahoo_chart 와 동일 — [{date, open, high, low, close, volume}] 오름차순.
    """
    code = _NAVER_INDEX_DAILY.get((symbol or "").upper())
    if not code:
        return []
    days = _PERIOD_DAYS.get(str(period or "5d").lower(), 31)
    end = datetime.now()
    start = end - timedelta(days=days)
    try:
        r = requests.get(_NAVER_SISE, params={
            "symbol": code, "requestType": 1, "timeframe": "day",
            "startTime": start.strftime("%Y%m%d"), "endTime": end.strftime("%Y%m%d"),
        }, headers={"User-Agent": "Mozilla/5.0", "Referer": "https://finance.naver.com/"}, timeout=10)
        if r.status_code != 200:
            return []
        bars = []
        for m in re.finditer(r'\["(\d{8})",\s*([\d.]+),\s*([\d.]+),\s*([\d.]+),\s*([\d.]+),\s*(\d+)', r.text):
            d, o, h, l, c, v = m.groups()
            bars.append({
                "date": f"{d[:4]}-{d[4:6]}-{d[6:]}",
                "open": round(float(o), 2), "high": round(float(h), 2),
                "low": round(float(l), 2), "close": round(float(c), 2),
                "volume": int(v),
            })
        return bars
    except Exception:
        return []


def get_stock_price(symbol: str, period: str = "5d", interval: str = "1d", max_points: int = 10) -> dict:
    """
    Yahoo Finance를 통해 주식/ETF/원자재(선물) 가격 조회
    (한국 종목·지수의 현재가 스냅샷은 네이버 실시간이 덮는다 — _naver_realtime)
    (한국 지수의 일봉은 네이버 — Yahoo 가 거래일을 통째 빠뜨린다, _naver_index_daily)
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
        # yfinance 라이브러리(봇차단) 대신 Yahoo chart API 직접(requests) — 폰·데스크탑 공통.
        chart_meta: dict = {}
        series_source = None
        all_history = []
        if str(interval or "1d").lower() in ("1d", "1day", "d"):
            # 한국 지수는 네이버 일봉이 먼저 (Yahoo 는 거래일을 통째 빠뜨린다)
            all_history = _naver_index_daily(symbol, period)
            if all_history:
                series_source = "naver_daily"
                chart_meta["currency"] = "KRW"
        if not all_history:
            all_history = _yahoo_chart(symbol, period, interval, meta_sink=chart_meta)
        if not all_history:
            return {"success": False, "error": f"'{symbol}' 종목을 찾을 수 없거나 데이터가 없습니다."}

        latest = all_history[-1]
        as_of = latest["date"]                       # 이 시세가 말하는 거래일 = history 마지막 행의 날짜
        current_price = latest["close"]
        prev_row = all_history[-2] if len(all_history) >= 2 else None
        prev_close = prev_row["close"] if prev_row else current_price
        prev_close_date = prev_row["date"] if prev_row else None
        snap_open, snap_high, snap_low, snap_volume = latest["open"], latest["high"], latest["low"], latest["volume"]

        if prev_close and prev_close > 0:
            change = current_price - prev_close
            change_percent = (change / prev_close) * 100
        else:
            change = 0
            change_percent = 0

        # ★한국 종목·지수: 현재가 스냅샷을 네이버 실시간으로 덮음(Yahoo KRX ~20분 지연).
        #   시계열(prices)은 Yahoo 일봉 유지 — 차트 계약 불변. 실패 시 Yahoo 값 그대로.
        #   ★거래일 정합(2026-09-01): 스냅샷이 *어느 장*의 것인지(quote_time 날짜)를 일봉의
        #   마지막 행(as_of)과 먼저 대조한다. 장전·휴장에는 네이버가 '아직 시작 안 한 오늘'
        #   기준 등락(=0)을 주는데 가격은 전 장 종가라, 옛 역산(prev_close = price - change)은
        #   전일종가를 그 장 종가 자신으로 만들어 history 의 마지막 행과 어긋났다.
        realtime = _naver_realtime(symbol)
        quote_lag = None                             # 일봉과 스냅샷이 다른 장을 가리킬 때의 정직 표지
        if realtime:
            rt_day = (realtime["quote_time"] or "")[:10] or datetime.now().strftime("%Y-%m-%d")
            if rt_day == as_of:
                # ① 같은 장 — 현재가만 실시간으로 덮고, 전일종가는 일봉 직전 행에 고정한다.
                current_price = realtime["price"]
                if prev_close and prev_close > 0:
                    change = current_price - prev_close
                    change_percent = (change / prev_close) * 100
                else:
                    change = realtime["change"]
                    change_percent = realtime["change_percent"] or 0
                naver_prev = realtime["price"] - realtime["change"]
                if prev_close and abs(naver_prev - prev_close) > max(abs(prev_close) * 0.005, 0.01):
                    # 네이버가 보는 전일종가 ≠ 일봉 직전 행 = 일봉에 구멍/지연. 정합은 일봉 쪽에
                    # 맞추되(quote 와 history 가 같은 자), 불일치 자체를 숨기지 않는다.
                    quote_lag = {"reason": "prev_close_disagreement",
                                 "naver_implied_prev_close": round(naver_prev, 2),
                                 "series_prev_close": round(prev_close, 2),
                                 "series_prev_date": prev_close_date}
                snap_open = realtime["open"] if realtime["open"] is not None else snap_open
                snap_high = realtime["high"] if realtime["high"] is not None else snap_high
                snap_low = realtime["low"] if realtime["low"] is not None else snap_low
                snap_volume = realtime["volume"] if realtime["volume"] is not None else snap_volume
            elif realtime["change"]:
                # ② 네이버가 일봉에 아직 없는 장을 이미 갖고 있다(일봉 지연) — 그 장으로 옮기되
                #    history 가 한 장 뒤처져 있음을 표지로 남긴다.
                as_of = rt_day
                current_price = realtime["price"]
                change = realtime["change"]
                prev_close_date = None               # 네이버의 전 장 = 일봉에 없는 장일 수 있다(추측 금지)
                prev_close = current_price - change
                change_percent = realtime["change_percent"] if realtime["change_percent"] is not None \
                    else ((change / prev_close) * 100 if prev_close else 0)
                quote_lag = {"reason": "series_behind_quote", "series_last_date": latest["date"]}
                snap_open = realtime["open"] if realtime["open"] is not None else snap_open
                snap_high = realtime["high"] if realtime["high"] is not None else snap_high
                snap_low = realtime["low"] if realtime["low"] is not None else snap_low
                snap_volume = realtime["volume"] if realtime["volume"] is not None else snap_volume
            # ③ 다른 날짜 + 등락 0 = 아직 시작 안 한 장(장전·휴장). 스냅샷에 새 장 정보가 없으니
            #    일봉의 마지막 완결 장(as_of)을 그대로 쓴다 — quote 와 history 가 같은 날을 가리킨다.

        # 일봉 구멍: as_of 와 전일종가로 쓴 행 *사이*에 결측 거래일이 있으면, 전일종가는
        # 진짜 직전 장이 아니다(옛 증상: 8/28 결측 → 8/27 기준 계산 → 부호 반전).
        series_gap = [d for d in (chart_meta.get("_dropped_dates") or [])
                      if (prev_close_date or "") < d < as_of]
        direction = "▲" if change >= 0 else "▼"
        currency = _resolve_currency(symbol, chart_meta)
        total_days = len(all_history)

        base_data = {
            "symbol": symbol.upper(),
            "current_price": round(current_price, 2),
            "currency": currency,
            "change": round(change, 2),
            "change_percent": round(change_percent, 2),
            "previous_close": round(prev_close, 2),
            "as_of": as_of,                          # 이 시세가 말하는 거래일 (history 마지막 행과 대조 가능)
            "previous_close_date": prev_close_date,
            "open": snap_open,
            "high": snap_high,
            "low": snap_low,
            "volume": snap_volume,
            "period": period,
            "total_days": total_days,
            "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        }
        if series_source:
            base_data["series_source"] = series_source   # 일봉이 어느 소스인지 (기본=yahoo_chart)
        if realtime:
            base_data["source"] = "naver_realtime"      # 한국 시세=실시간(delayTime 0)
            if realtime["quote_time"]:
                base_data["quote_time"] = realtime["quote_time"]
            if realtime["market_status"]:
                base_data["market_status"] = realtime["market_status"]
        if quote_lag:
            base_data["quote_lag"] = quote_lag       # 일봉과 스냅샷의 거래일/전일종가 불일치 신고
        if series_gap:
            base_data["series_gap"] = series_gap     # 전일종가와 as_of 사이의 결측 거래일(핸들러가 정합 보정)

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
            summary = f"[{as_of} 기준] 현재가 {round(current_price, 2)} {currency} {direction} {abs(round(change, 2))} ({change_percent:+.2f}%), 전일({prev_close_date or '?'}) {round(prev_close, 2)}. 최근 {total_days}거래일 시세 포함."
        if realtime:
            summary += " (네이버 실시간)"
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

        # fast_info.currency 가 권위(yfinance 가 Yahoo meta 를 그대로 노출) — 없으면 폴백.
        fast_ccy = None
        try:
            fast_ccy = getattr(fast, "currency", None)
        except Exception:
            fast_ccy = None

        return {
            "success": True,
            "data": {
                "symbol": symbol.upper(),
                "currency": _resolve_currency(symbol, {"currency": fast_ccy} if fast_ccy else None),
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
        # yf.Search(봇차단) 대신 Yahoo search API 직접(requests) — 폰·데스크탑 공통.
        url = "https://query1.finance.yahoo.com/v1/finance/search"
        headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
        j = requests.get(url, params={"q": query, "quotesCount": 10, "newsCount": 5},
                         headers=headers, timeout=12).json()
        raw_quotes = j.get("quotes") or []
        raw_news = j.get("news") or []

        if search_type == "all":
            return {"success": True, "data": {"query": query, "quotes": raw_quotes[:10], "news": raw_news[:5]}}
        elif search_type == "news":
            return {"success": True, "data": {"query": query, "count": len(raw_news), "news": raw_news[:10]}}
        else:
            quotes = []
            for q in raw_quotes[:10]:
                if not q.get("symbol"):
                    continue
                quotes.append({
                    "symbol": q.get("symbol", ""),
                    "name": q.get("shortname") or q.get("longname", ""),
                    "exchange": q.get("exchange", ""),
                    "type": q.get("quoteType", "")
                })
            return {"success": True, "data": {"query": query, "count": len(quotes), "quotes": quotes}}

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
