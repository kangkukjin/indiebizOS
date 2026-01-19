"""
한국 주식 시세 조회 도구
FinanceDataReader 또는 KRX API를 통해 한국 주식 시세를 조회합니다.

의존성: pip install finance-datareader
"""
import os
import urllib.request
import urllib.parse
import json
from datetime import datetime, timedelta
from pathlib import Path

# 종목 코드 캐시
STOCK_CODE_CACHE_PATH = Path(__file__).parent / "stock_code_cache.json"


def _load_stock_codes():
    """종목 코드 목록 로드 (캐시 또는 KRX)"""
    # 캐시 확인
    if STOCK_CODE_CACHE_PATH.exists():
        try:
            with open(STOCK_CODE_CACHE_PATH, 'r', encoding='utf-8') as f:
                cache_data = json.load(f)
                cache_time = datetime.fromisoformat(cache_data.get("cached_at", "2000-01-01"))
                if datetime.now() - cache_time < timedelta(days=1):
                    return cache_data.get("stocks", {})
        except Exception:
            pass

    # KRX에서 종목 목록 가져오기
    try:
        # KOSPI
        kospi_stocks = _fetch_krx_stock_list("STK")
        # KOSDAQ
        kosdaq_stocks = _fetch_krx_stock_list("KSQ")

        stocks = {**kospi_stocks, **kosdaq_stocks}

        # 캐시 저장
        cache_data = {
            "cached_at": datetime.now().isoformat(),
            "stocks": stocks
        }
        with open(STOCK_CODE_CACHE_PATH, 'w', encoding='utf-8') as f:
            json.dump(cache_data, f, ensure_ascii=False, indent=2)

        return stocks

    except Exception as e:
        # 기본 주요 종목 반환
        return {
            "삼성전자": "005930",
            "SK하이닉스": "000660",
            "LG에너지솔루션": "373220",
            "삼성바이오로직스": "207940",
            "현대차": "005380",
            "기아": "000270",
            "셀트리온": "068270",
            "POSCO홀딩스": "005490",
            "KB금융": "105560",
            "신한지주": "055550",
            "NAVER": "035420",
            "카카오": "035720",
            "LG화학": "051910",
            "삼성SDI": "006400",
            "현대모비스": "012330"
        }


def _fetch_krx_stock_list(market: str):
    """KRX에서 종목 목록 조회"""
    url = "http://data.krx.co.kr/comm/bldAttendant/getJsonData.cmd"

    params = {
        "bld": "dbms/MDC/STAT/standard/MDCSTAT01901",
        "mktId": market,
        "share": "1",
        "csvxls_is498No": "false"
    }

    try:
        data = urllib.parse.urlencode(params).encode('utf-8')
        req = urllib.request.Request(url, data=data)
        req.add_header("User-Agent", "Mozilla/5.0")
        req.add_header("Content-Type", "application/x-www-form-urlencoded")

        with urllib.request.urlopen(req, timeout=10) as response:
            result = json.loads(response.read().decode('utf-8'))

        stocks = {}
        for item in result.get("OutBlock_1", []):
            name = item.get("ISU_ABBRV", "")
            code = item.get("ISU_SRT_CD", "")
            if name and code:
                stocks[name] = code

        return stocks

    except Exception:
        return {}


def _find_stock_code(symbol: str):
    """종목명 또는 코드로 종목코드 찾기"""
    # 숫자로만 구성되면 코드로 간주
    if symbol.isdigit():
        return symbol.zfill(6)

    stocks = _load_stock_codes()

    # 정확한 매칭
    if symbol in stocks:
        return stocks[symbol]

    # 부분 매칭
    for name, code in stocks.items():
        if symbol in name or name in symbol:
            return code

    return None


def _fetch_stock_price_fdr(code: str, start_date: str, end_date: str):
    """FinanceDataReader로 주가 조회"""
    try:
        import FinanceDataReader as fdr
        df = fdr.DataReader(code, start_date, end_date)

        if df.empty:
            return None

        prices = []
        for date, row in df.iterrows():
            prices.append({
                "date": date.strftime("%Y-%m-%d"),
                "open": int(row.get("Open", 0)),
                "high": int(row.get("High", 0)),
                "low": int(row.get("Low", 0)),
                "close": int(row.get("Close", 0)),
                "volume": int(row.get("Volume", 0)),
                "change": float(row.get("Change", 0)) if "Change" in row else None
            })

        return prices

    except ImportError:
        return None
    except Exception:
        return None


def _fetch_stock_price_krx(code: str, start_date: str, end_date: str):
    """KRX API로 주가 조회 (대안)"""
    url = "http://data.krx.co.kr/comm/bldAttendant/getJsonData.cmd"

    # 날짜 형식 변환
    start = start_date.replace("-", "")
    end = end_date.replace("-", "")

    params = {
        "bld": "dbms/MDC/STAT/standard/MDCSTAT01701",
        "isuCd": f"KR7{code}000" if len(code) == 6 else code,
        "isuCd2": code,
        "strtDd": start,
        "endDd": end,
        "share": "1",
        "money": "1",
        "csvxls_isNo": "false"
    }

    try:
        data = urllib.parse.urlencode(params).encode('utf-8')
        req = urllib.request.Request(url, data=data)
        req.add_header("User-Agent", "Mozilla/5.0")
        req.add_header("Content-Type", "application/x-www-form-urlencoded")

        with urllib.request.urlopen(req, timeout=15) as response:
            result = json.loads(response.read().decode('utf-8'))

        prices = []
        for item in result.get("output", []):
            prices.append({
                "date": item.get("TRD_DD", "").replace("/", "-"),
                "open": int(item.get("TDD_OPNPRC", "0").replace(",", "")),
                "high": int(item.get("TDD_HGPRC", "0").replace(",", "")),
                "low": int(item.get("TDD_LWPRC", "0").replace(",", "")),
                "close": int(item.get("TDD_CLSPRC", "0").replace(",", "")),
                "volume": int(item.get("ACC_TRDVOL", "0").replace(",", "")),
                "change": float(item.get("FLUC_RT", "0").replace(",", "")) if item.get("FLUC_RT") else None
            })

        return prices

    except Exception:
        return None


def get_stock_price(symbol: str, start_date: str = None, end_date: str = None):
    """
    한국 주식 시세 조회

    Args:
        symbol: 종목코드 (예: 005930) 또는 종목명 (예: 삼성전자)
        start_date: 조회 시작일 (YYYY-MM-DD)
        end_date: 조회 종료일 (YYYY-MM-DD)

    Returns:
        주가 데이터 (시가, 고가, 저가, 종가, 거래량)
    """
    # 종목코드 찾기
    code = _find_stock_code(symbol)
    if not code:
        return {
            "success": False,
            "error": f"'{symbol}'에 해당하는 종목을 찾을 수 없습니다."
        }

    # 날짜 기본값
    if not end_date:
        end_date = datetime.now().strftime("%Y-%m-%d")
    if not start_date:
        start_date = (datetime.now() - timedelta(days=30)).strftime("%Y-%m-%d")

    # FinanceDataReader 시도
    prices = _fetch_stock_price_fdr(code, start_date, end_date)

    # 실패시 KRX API 시도
    if prices is None:
        prices = _fetch_stock_price_krx(code, start_date, end_date)

    if not prices:
        return {
            "success": False,
            "error": f"'{symbol}'의 주가 데이터를 조회할 수 없습니다. FinanceDataReader 라이브러리를 설치해보세요: pip install finance-datareader"
        }

    # 최신 데이터 추출
    latest = prices[-1] if prices else {}

    # 종목명 찾기
    stocks = _load_stock_codes()
    stock_name = symbol
    for name, c in stocks.items():
        if c == code:
            stock_name = name
            break

    return {
        "success": True,
        "data": {
            "symbol": code,
            "name": stock_name,
            "start_date": start_date,
            "end_date": end_date,
            "latest": latest,
            "prices": prices[-30:]  # 최근 30일만
        },
        "summary": f"{stock_name}({code}) 현재가: {latest.get('close', 'N/A'):,}원, 기간: {start_date} ~ {end_date}"
    }


def get_stock_info(symbol: str):
    """
    종목 기본 정보 조회 (현재가, 전일비, 거래량 등)

    Args:
        symbol: 종목코드 또는 종목명

    Returns:
        종목 기본 정보
    """
    code = _find_stock_code(symbol)
    if not code:
        return {
            "success": False,
            "error": f"'{symbol}'에 해당하는 종목을 찾을 수 없습니다."
        }

    # 최근 2일 시세 조회
    end_date = datetime.now().strftime("%Y-%m-%d")
    start_date = (datetime.now() - timedelta(days=7)).strftime("%Y-%m-%d")

    result = get_stock_price(code, start_date, end_date)

    if not result.get("success"):
        return result

    prices = result["data"].get("prices", [])
    if len(prices) < 1:
        return {
            "success": False,
            "error": "시세 데이터가 부족합니다."
        }

    latest = prices[-1]
    prev = prices[-2] if len(prices) > 1 else latest

    change = latest.get("close", 0) - prev.get("close", 0)
    change_pct = (change / prev.get("close", 1)) * 100 if prev.get("close") else 0

    return {
        "success": True,
        "data": {
            "symbol": code,
            "name": result["data"].get("name"),
            "current_price": latest.get("close"),
            "change": change,
            "change_percent": round(change_pct, 2),
            "open": latest.get("open"),
            "high": latest.get("high"),
            "low": latest.get("low"),
            "volume": latest.get("volume"),
            "date": latest.get("date")
        },
        "summary": f"{result['data'].get('name')}({code}): {latest.get('close', 0):,}원 ({'+' if change >= 0 else ''}{change:,}, {'+' if change_pct >= 0 else ''}{change_pct:.2f}%)"
    }
