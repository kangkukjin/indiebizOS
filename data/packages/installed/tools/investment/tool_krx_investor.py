"""
한국 주식시장 투자자별 매매동향 조회 도구
pykrx를 통해 외국인/기관/개인 순매수 데이터를 조회합니다.

의존성: pip install pykrx
"""
import os
import sys
import json
from datetime import datetime, timedelta

_backend_dir = os.path.join(os.path.dirname(__file__), "..", "..", "..", "..", "backend")
if _backend_dir not in sys.path:
    sys.path.insert(0, os.path.abspath(_backend_dir))

from common.response_formatter import save_large_data


def _to_millions(val) -> int:
    """원 단위 → 백만원 단위 변환"""
    try:
        return int(val) // 1_000_000
    except (TypeError, ValueError):
        return 0


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
        투자자별 일별 순매수 금액 데이터
    """
    try:
        from pykrx import stock
    except ImportError:
        return {"success": False, "error": "pykrx 라이브러리가 필요합니다: pip install pykrx"}

    if not end_date:
        end_date = datetime.now().strftime("%Y-%m-%d")
    if not start_date:
        start_date = (datetime.now() - timedelta(days=30)).strftime("%Y-%m-%d")

    # pykrx는 YYYYMMDD 형식 사용
    start_str = start_date.replace("-", "")
    end_str = end_date.replace("-", "")

    # 시장명 매핑 (pykrx는 KOSPI/KOSDAQ 사용)
    market_map = {"STK": "KOSPI", "KSQ": "KOSDAQ", "ALL": "ALL"}
    pykrx_market = market_map.get(market, market)
    market_name = {"STK": "코스피", "KSQ": "코스닥", "ALL": "전체"}.get(market, market)

    try:
        if pykrx_market == "ALL":
            # pykrx에는 ALL이 없으므로 KOSPI + KOSDAQ 합산
            df_kospi = stock.get_market_trading_value_by_date(start_str, end_str, "KOSPI")
            df_kosdaq = stock.get_market_trading_value_by_date(start_str, end_str, "KOSDAQ")
            if df_kospi.empty and df_kosdaq.empty:
                return {"success": False, "error": f"전체 시장 매매동향 데이터가 없습니다. 기간: {start_date} ~ {end_date}"}
            # 공통 인덱스로 합산
            common_idx = df_kospi.index.intersection(df_kosdaq.index)
            df = df_kospi.loc[common_idx] + df_kosdaq.loc[common_idx]
        else:
            df = stock.get_market_trading_value_by_date(start_str, end_str, pykrx_market)

        if df.empty:
            return {"success": False, "error": f"{market_name} 시장 매매동향 데이터가 없습니다. 기간: {start_date} ~ {end_date}"}

        # DataFrame → dict 변환
        # 컬럼: 기관합계, 기타법인, 개인, 외국인합계, 전체
        daily_data = []
        for date_idx, row in df.iterrows():
            d = {"date": date_idx.strftime("%Y-%m-%d")}
            for col in df.columns:
                label = col.replace("합계", "") if col == "외국인합계" else col
                if label == "외국인":
                    d["외국인"] = _to_millions(row[col])
                elif label == "전체":
                    continue  # 항상 0이므로 생략
                else:
                    d[col] = _to_millions(row[col])
            daily_data.append(d)

        # 기간 합계
        investor_cols = ["기관합계", "기타법인", "개인"]
        summary_totals = {}
        for col in investor_cols:
            if col in df.columns:
                summary_totals[col] = _to_millions(df[col].sum())
        if "외국인합계" in df.columns:
            summary_totals["외국인"] = _to_millions(df["외국인합계"].sum())

        foreign_total = summary_totals.get("외국인", 0)
        inst_total = summary_totals.get("기관합계", 0)
        indiv_total = summary_totals.get("개인", 0)

        latest = daily_data[-1] if daily_data else {}
        total_days = len(daily_data)

        # 대량 데이터는 파일로 저장
        if total_days > 30:
            file_path = save_large_data(daily_data, "investment", f"investor_trading_{market}")
            step = max(1, total_days // 10)
            sample = daily_data[::step]
            if sample[-1] != daily_data[-1]:
                sample.append(daily_data[-1])
            sample_compact = [
                {"date": d["date"], "외국인": d.get("외국인", 0), "기관합계": d.get("기관합계", 0), "개인": d.get("개인", 0)}
                for d in sample
            ]

            return {
                "success": True,
                "data": {
                    "market": market_name,
                    "start_date": start_date,
                    "end_date": end_date,
                    "total_days": total_days,
                    "unit": "백만원",
                    "latest": latest,
                    "period_total": summary_totals,
                    "file_path": file_path,
                    "sample": sample_compact,
                },
                "summary": (
                    f"[{market_name}] 투자자별 순매수 ({start_date}~{end_date}, {total_days}거래일)\n"
                    f"  외국인: {foreign_total:+,}백만원 | 기관: {inst_total:+,}백만원 | 개인: {indiv_total:+,}백만원\n"
                    f"  최근({latest.get('date', '')}): 외국인 {latest.get('외국인', 0):+,}백만원\n"
                    f"  전체 데이터: {file_path}"
                ),
            }
        else:
            return {
                "success": True,
                "data": {
                    "market": market_name,
                    "start_date": start_date,
                    "end_date": end_date,
                    "total_days": total_days,
                    "unit": "백만원",
                    "latest": latest,
                    "period_total": summary_totals,
                    "daily": daily_data,
                },
                "summary": (
                    f"[{market_name}] 투자자별 순매수 ({start_date}~{end_date}, {total_days}거래일)\n"
                    f"  외국인: {foreign_total:+,}백만원 | 기관: {inst_total:+,}백만원 | 개인: {indiv_total:+,}백만원\n"
                    f"  최근({latest.get('date', '')}): 외국인 {latest.get('외국인', 0):+,}백만원"
                ),
            }

    except Exception as e:
        return {"success": False, "error": f"투자자별 매매동향 조회 실패: {str(e)}"}


def get_stock_investor_trading(
    symbol: str,
    start_date: str = None,
    end_date: str = None,
):
    """
    개별종목 투자자별 매매동향 (일별 순매수 금액)

    Args:
        symbol: 종목코드 (예: 005930) 또는 종목명 (예: 삼성전자)
        start_date: 조회 시작일 (YYYY-MM-DD). 기본: 1개월 전
        end_date: 조회 종료일 (YYYY-MM-DD). 기본: 오늘

    Returns:
        해당 종목의 투자자별 일별 순매수 금액 데이터
    """
    try:
        from pykrx import stock
    except ImportError:
        return {"success": False, "error": "pykrx 라이브러리가 필요합니다: pip install pykrx"}

    # 종목코드 찾기 (tool_krx의 함수 재사용)
    from tool_krx import _find_stock_code, _load_stock_codes

    code = _find_stock_code(symbol)
    if not code:
        return {"success": False, "error": f"'{symbol}'에 해당하는 종목을 찾을 수 없습니다."}

    if not end_date:
        end_date = datetime.now().strftime("%Y-%m-%d")
    if not start_date:
        start_date = (datetime.now() - timedelta(days=30)).strftime("%Y-%m-%d")

    start_str = start_date.replace("-", "")
    end_str = end_date.replace("-", "")

    # 종목명 찾기
    stocks = _load_stock_codes()
    stock_name = symbol
    for name, c in stocks.items():
        if c == code:
            stock_name = name
            break

    try:
        df = stock.get_market_trading_value_by_date(start_str, end_str, code)

        if df.empty:
            return {"success": False, "error": f"{stock_name}({code}) 매매동향 데이터가 없습니다. 기간: {start_date} ~ {end_date}"}

        # DataFrame → dict 변환
        daily_data = []
        for date_idx, row in df.iterrows():
            d = {"date": date_idx.strftime("%Y-%m-%d")}
            for col in df.columns:
                if col == "외국인합계":
                    d["외국인"] = _to_millions(row[col])
                elif col == "전체":
                    continue
                else:
                    d[col] = _to_millions(row[col])
            daily_data.append(d)

        # 기간 합계
        summary_totals = {}
        for col in df.columns:
            if col == "전체":
                continue
            label = "외국인" if col == "외국인합계" else col
            summary_totals[label] = _to_millions(df[col].sum())

        foreign_total = summary_totals.get("외국인", 0)
        inst_total = summary_totals.get("기관합계", 0)
        indiv_total = summary_totals.get("개인", 0)

        latest = daily_data[-1] if daily_data else {}
        total_days = len(daily_data)

        if total_days > 30:
            file_path = save_large_data(daily_data, "investment", f"stock_investor_{code}")
            step = max(1, total_days // 10)
            sample = daily_data[::step]
            if sample[-1] != daily_data[-1]:
                sample.append(daily_data[-1])
            sample_compact = [
                {"date": d["date"], "외국인": d.get("외국인", 0), "기관합계": d.get("기관합계", 0), "개인": d.get("개인", 0)}
                for d in sample
            ]

            return {
                "success": True,
                "data": {
                    "symbol": code,
                    "name": stock_name,
                    "start_date": start_date,
                    "end_date": end_date,
                    "total_days": total_days,
                    "unit": "백만원",
                    "latest": latest,
                    "period_total": summary_totals,
                    "file_path": file_path,
                    "sample": sample_compact,
                },
                "summary": (
                    f"[{stock_name}({code})] 투자자별 순매수 ({start_date}~{end_date}, {total_days}거래일)\n"
                    f"  외국인: {foreign_total:+,}백만원 | 기관: {inst_total:+,}백만원 | 개인: {indiv_total:+,}백만원\n"
                    f"  최근({latest.get('date', '')}): 외국인 {latest.get('외국인', 0):+,}백만원\n"
                    f"  전체 데이터: {file_path}"
                ),
            }
        else:
            return {
                "success": True,
                "data": {
                    "symbol": code,
                    "name": stock_name,
                    "start_date": start_date,
                    "end_date": end_date,
                    "total_days": total_days,
                    "unit": "백만원",
                    "latest": latest,
                    "period_total": summary_totals,
                    "daily": daily_data,
                },
                "summary": (
                    f"[{stock_name}({code})] 투자자별 순매수 ({start_date}~{end_date}, {total_days}거래일)\n"
                    f"  외국인: {foreign_total:+,}백만원 | 기관: {inst_total:+,}백만원 | 개인: {indiv_total:+,}백만원\n"
                    f"  최근({latest.get('date', '')}): 외국인 {latest.get('외국인', 0):+,}백만원"
                ),
            }

    except Exception as e:
        return {"success": False, "error": f"{stock_name}({code}) 투자자별 매매동향 조회 실패: {str(e)}"}
