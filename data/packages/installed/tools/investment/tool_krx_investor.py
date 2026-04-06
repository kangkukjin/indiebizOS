"""
한국 주식시장 투자자별 매매동향 조회 도구
네이버 금융에서 외국인/기관/개인 순매수 데이터를 조회합니다.

- 개별종목: 네이버 금융 PC 웹 (frgn.naver) HTML 파싱
- 전체시장: 네이버 모바일 API (당일) + PC 웹 파싱 (일별)
"""
import os
import sys
import re
import requests
from datetime import datetime, timedelta
from bs4 import BeautifulSoup

_backend_dir = os.path.join(os.path.dirname(__file__), "..", "..", "..", "..", "backend")
if _backend_dir not in sys.path:
    sys.path.insert(0, os.path.abspath(_backend_dir))

from common.response_formatter import save_large_data

_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
}


def _parse_int(text: str) -> int:
    """콤마/부호가 포함된 문자열을 int로 변환"""
    if not text:
        return 0
    cleaned = text.replace(",", "").replace("+", "").strip()
    try:
        return int(cleaned)
    except (ValueError, TypeError):
        return 0


def _to_millions(val) -> int:
    """원 단위 → 백만원 단위 변환"""
    try:
        return int(val) // 1_000_000
    except (TypeError, ValueError):
        return 0


# ─── 전체시장 투자자별 매매동향 ───


def _fetch_market_naver_mobile(market: str) -> dict | None:
    """네이버 모바일 API로 전체시장 당일 투자자별 매매동향 조회 (단위: 억원)"""
    market_map = {"STK": "KOSPI", "KSQ": "KOSDAQ"}
    index_code = market_map.get(market)
    if not index_code:
        return None

    url = f"https://m.stock.naver.com/api/index/{index_code}/integration?includeContent=investorTrend"
    try:
        resp = requests.get(url, headers=_HEADERS, timeout=10)
        if resp.status_code != 200:
            return None
        data = resp.json()
        info = data.get("dealTrendInfo")
        if not info:
            return None
        return {
            "date": f"{info['bizdate'][:4]}-{info['bizdate'][4:6]}-{info['bizdate'][6:8]}",
            "개인": _parse_int(info.get("personalValue", "0")),
            "외국인": _parse_int(info.get("foreignValue", "0")),
            "기관합계": _parse_int(info.get("institutionalValue", "0")),
        }
    except Exception:
        return None


def _fetch_market_naver_web(market: str, max_pages: int = 5) -> list[dict]:
    """네이버 PC 웹 투자자별 매매동향 일별 데이터 파싱 (단위: 억원)"""
    sosok = {"STK": "01", "KSQ": "02"}.get(market)
    if not sosok:
        return []

    all_data = []
    for page in range(1, max_pages + 1):
        url = f"https://finance.naver.com/sise/investorDealTrendDay.naver?sosok={sosok}&page={page}"
        try:
            resp = requests.get(url, headers=_HEADERS, timeout=10)
            soup = BeautifulSoup(resp.content.decode("euc-kr", errors="replace"), "html.parser")
            table = soup.find("table", {"class": "type_1"})
            if not table:
                break

            found = False
            for row in table.find_all("tr"):
                cells = row.find_all("td")
                if len(cells) < 4:
                    continue
                date_text = cells[0].get_text(strip=True)
                if not re.match(r"\d{4}\.\d{2}\.\d{2}", date_text):
                    continue
                found = True
                all_data.append({
                    "date": date_text.replace(".", "-"),
                    "개인": _parse_int(cells[1].get_text(strip=True)),
                    "외국인": _parse_int(cells[2].get_text(strip=True)),
                    "기관합계": _parse_int(cells[3].get_text(strip=True)),
                })

            if not found:
                break
        except Exception:
            break

    return all_data


def get_market_investor_trading(
    market: str = "STK",
    start_date: str = None,
    end_date: str = None,
):
    """
    전체시장 투자자별 매매동향 (일별 순매수 금액)

    Args:
        market: 시장 구분 - STK(코스피), KSQ(코스닥), ALL(전체)
        start_date: 조회 시작일 (YYYY-MM-DD). 기본: 1개월 전
        end_date: 조회 종료일 (YYYY-MM-DD). 기본: 오늘

    Returns:
        투자자별 일별 순매수 금액 데이터 (단위: 억원)
    """
    if not end_date:
        end_date = datetime.now().strftime("%Y-%m-%d")
    if not start_date:
        start_date = (datetime.now() - timedelta(days=30)).strftime("%Y-%m-%d")

    market_name = {"STK": "코스피", "KSQ": "코스닥", "ALL": "전체"}.get(market, market)

    if market == "ALL":
        # 코스피 + 코스닥 각각 조회 후 합산
        data_stk = _fetch_market_naver_web("STK")
        data_ksq = _fetch_market_naver_web("KSQ")
        if not data_stk and not data_ksq:
            return {"success": False, "error": f"전체 시장 매매동향 데이터가 없습니다. 기간: {start_date} ~ {end_date}"}

        # 날짜별 합산
        by_date = {}
        for d in data_stk + data_ksq:
            key = d["date"]
            if key not in by_date:
                by_date[key] = {"date": key, "개인": 0, "외국인": 0, "기관합계": 0}
            by_date[key]["개인"] += d["개인"]
            by_date[key]["외국인"] += d["외국인"]
            by_date[key]["기관합계"] += d["기관합계"]
        daily_data = sorted(by_date.values(), key=lambda x: x["date"], reverse=True)
    else:
        daily_data = _fetch_market_naver_web(market)

    if not daily_data:
        # 웹 파싱 실패 시 모바일 API로 당일 데이터라도 시도
        today = _fetch_market_naver_mobile(market)
        if today:
            daily_data = [today]
        else:
            return {"success": False, "error": f"{market_name} 시장 매매동향 데이터가 없습니다. 기간: {start_date} ~ {end_date}"}

    # 기간 필터링
    daily_data = [d for d in daily_data if start_date <= d["date"] <= end_date]
    if not daily_data:
        return {"success": False, "error": f"{market_name} 시장 매매동향 데이터가 없습니다. 기간: {start_date} ~ {end_date}"}

    # 날짜 오름차순 정렬
    daily_data.sort(key=lambda x: x["date"])

    # 기간 합계
    foreign_total = sum(d["외국인"] for d in daily_data)
    inst_total = sum(d["기관합계"] for d in daily_data)
    indiv_total = sum(d["개인"] for d in daily_data)
    summary_totals = {"외국인": foreign_total, "기관합계": inst_total, "개인": indiv_total}

    latest = daily_data[-1]
    total_days = len(daily_data)

    result_data = {
        "market": market_name,
        "start_date": start_date,
        "end_date": end_date,
        "total_days": total_days,
        "unit": "억원",
        "latest": latest,
        "period_total": summary_totals,
        "source": "네이버 금융",
    }

    if total_days > 30:
        file_path = save_large_data(daily_data, "investment", f"investor_trading_{market}")
        step = max(1, total_days // 10)
        sample = daily_data[::step]
        if sample[-1] != daily_data[-1]:
            sample.append(daily_data[-1])
        result_data["file_path"] = file_path
        result_data["sample"] = [
            {"date": d["date"], "외국인": d["외국인"], "기관합계": d["기관합계"], "개인": d["개인"]}
            for d in sample
        ]
    else:
        result_data["daily"] = daily_data

    return {
        "success": True,
        "data": result_data,
        "summary": (
            f"[{market_name}] 투자자별 순매수 ({start_date}~{end_date}, {total_days}거래일)\n"
            f"  외국인: {foreign_total:+,}억원 | 기관: {inst_total:+,}억원 | 개인: {indiv_total:+,}억원\n"
            f"  최근({latest['date']}): 외국인 {latest['외국인']:+,}억원"
        ),
    }


# ─── 개별종목 투자자별 매매동향 ───


def _fetch_stock_naver_web(code: str, max_pages: int = 5) -> list[dict]:
    """
    네이버 금융 PC 웹에서 개별종목 외국인/기관 매매동향 파싱
    단위: 순매매 주수 (quantity)
    """
    all_data = []
    for page in range(1, max_pages + 1):
        url = f"https://finance.naver.com/item/frgn.naver?code={code}&page={page}"
        try:
            resp = requests.get(url, headers=_HEADERS, timeout=10)
            soup = BeautifulSoup(resp.content.decode("euc-kr", errors="replace"), "html.parser")
            tables = soup.find_all("table", {"class": "type2"})

            found = False
            for table in tables:
                for row in table.find_all("tr"):
                    cells = row.find_all("td")
                    if len(cells) < 9:
                        continue
                    date_text = cells[0].get_text(strip=True)
                    if not re.match(r"\d{4}\.\d{2}\.\d{2}", date_text):
                        continue
                    found = True

                    close_price = _parse_int(cells[1].get_text(strip=True))
                    change_text = cells[2].get_text(strip=True)
                    # "상승X" / "하락X" 형태에서 숫자 추출
                    change_match = re.search(r"[\d,]+", change_text)
                    change_val = _parse_int(change_match.group()) if change_match else 0
                    if "하락" in change_text:
                        change_val = -change_val

                    pct_text = cells[3].get_text(strip=True)
                    volume = _parse_int(cells[4].get_text(strip=True))
                    organ = _parse_int(cells[5].get_text(strip=True))
                    foreign = _parse_int(cells[6].get_text(strip=True))
                    hold_qty = _parse_int(cells[7].get_text(strip=True))
                    hold_pct = cells[8].get_text(strip=True)

                    all_data.append({
                        "date": date_text.replace(".", "-"),
                        "close": close_price,
                        "change": change_val,
                        "change_pct": pct_text,
                        "volume": volume,
                        "기관": organ,
                        "외국인": foreign,
                        "외국인_보유주수": hold_qty,
                        "외국인_보유율": hold_pct,
                    })

            if not found:
                break
        except Exception:
            break

    return all_data


def get_stock_investor_trading(
    symbol: str,
    start_date: str = None,
    end_date: str = None,
):
    """
    개별종목 투자자별 매매동향 (일별 순매수)

    Args:
        symbol: 종목코드 (예: 005930) 또는 종목명 (예: 삼성전자)
        start_date: 조회 시작일 (YYYY-MM-DD). 기본: 1개월 전
        end_date: 조회 종료일 (YYYY-MM-DD). 기본: 오늘

    Returns:
        해당 종목의 투자자별 일별 순매수 데이터 (단위: 주)
    """
    from tool_krx import _find_stock_code, _load_stock_codes

    code = _find_stock_code(symbol)
    if not code:
        return {"success": False, "error": f"'{symbol}'에 해당하는 종목을 찾을 수 없습니다."}

    if not end_date:
        end_date = datetime.now().strftime("%Y-%m-%d")
    if not start_date:
        start_date = (datetime.now() - timedelta(days=30)).strftime("%Y-%m-%d")

    # 종목명 찾기
    stocks = _load_stock_codes()
    stock_name = symbol
    for name, c in stocks.items():
        if c == code:
            stock_name = name
            break

    # 필요한 페이지 수 추정 (페이지당 약 20거래일)
    days_needed = (datetime.strptime(end_date, "%Y-%m-%d") - datetime.strptime(start_date, "%Y-%m-%d")).days
    max_pages = max(2, (days_needed // 15) + 1)
    max_pages = min(max_pages, 10)

    daily_data = _fetch_stock_naver_web(code, max_pages=max_pages)
    if not daily_data:
        return {"success": False, "error": f"{stock_name}({code}) 매매동향 데이터가 없습니다. 기간: {start_date} ~ {end_date}"}

    # 기간 필터링
    daily_data = [d for d in daily_data if start_date <= d["date"] <= end_date]
    if not daily_data:
        return {"success": False, "error": f"{stock_name}({code}) 매매동향 데이터가 없습니다. 기간: {start_date} ~ {end_date}"}

    # 날짜 오름차순 정렬
    daily_data.sort(key=lambda x: x["date"])

    # 기간 합계
    foreign_total = sum(d["외국인"] for d in daily_data)
    inst_total = sum(d["기관"] for d in daily_data)
    summary_totals = {"외국인": foreign_total, "기관": inst_total}

    latest = daily_data[-1]
    total_days = len(daily_data)

    result_data = {
        "symbol": code,
        "name": stock_name,
        "start_date": start_date,
        "end_date": end_date,
        "total_days": total_days,
        "unit": "주",
        "latest": latest,
        "period_total": summary_totals,
        "source": "네이버 금융",
    }

    if total_days > 30:
        file_path = save_large_data(daily_data, "investment", f"stock_investor_{code}")
        step = max(1, total_days // 10)
        sample = daily_data[::step]
        if sample[-1] != daily_data[-1]:
            sample.append(daily_data[-1])
        result_data["file_path"] = file_path
        result_data["sample"] = [
            {"date": d["date"], "외국인": d["외국인"], "기관": d["기관"], "close": d["close"]}
            for d in sample
        ]
    else:
        result_data["daily"] = daily_data

    return {
        "success": True,
        "data": result_data,
        "summary": (
            f"[{stock_name}({code})] 투자자별 순매수 ({start_date}~{end_date}, {total_days}거래일)\n"
            f"  외국인: {foreign_total:+,}주 | 기관: {inst_total:+,}주\n"
            f"  최근({latest['date']}): 외국인 {latest['외국인']:+,}주 | 종가 {latest['close']:,}원"
        ),
    }
