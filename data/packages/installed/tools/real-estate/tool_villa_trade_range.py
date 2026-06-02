"""
연립다세대 매매 실거래가 기간 범위 조회 모듈
국토교통부 RTMSDataSvcRHTrade API (연립/다세대)
여러 달을 한 번에 조회하여 API 호출 횟수 감소
"""
import urllib.request
import urllib.parse
import urllib.error
import xml.etree.ElementTree as ET
import os
import sys
from datetime import datetime

# common 유틸리티 사용
_backend_dir = os.path.join(os.path.dirname(__file__), "..", "..", "..", "..", "backend")
if _backend_dir not in sys.path:
    sys.path.insert(0, os.path.abspath(_backend_dir))

from common.auth_manager import get_api_key, check_api_key

SERVICE_KEY = get_api_key('MOLIT_API_KEY') or ''
BASE_URL = 'https://apis.data.go.kr/1613000/RTMSDataSvcRHTrade/getRTMSDataSvcRHTrade'


def _get_months_range(start_month: str, end_month: str) -> list:
    """시작월부터 종료월까지의 월 목록 생성"""
    months = []
    start = datetime.strptime(start_month, "%Y%m")
    end = datetime.strptime(end_month, "%Y%m")

    current = start
    while current <= end:
        months.append(current.strftime("%Y%m"))
        if current.month == 12:
            current = current.replace(year=current.year + 1, month=1)
        else:
            current = current.replace(month=current.month + 1)

    return months


def _fetch_month_data(region_code: str, year_month: str, count: int) -> list:
    """한 달 데이터 조회"""
    try:
        params = {
            'serviceKey': SERVICE_KEY,
            'LAWD_CD': region_code,
            'DEAL_YMD': year_month,
            'numOfRows': str(count)
        }

        url = BASE_URL + '?' + urllib.parse.urlencode(params)
        req = urllib.request.Request(url)

        with urllib.request.urlopen(req, timeout=30) as response:
            data = response.read().decode('utf-8')

        root = ET.fromstring(data)
        result_code = root.find('.//resultCode')

        if result_code is None or result_code.text != '000':
            return []

        items = root.findall('.//item')
        trades = []

        for item in items:
            trade = {
                "건물명": _get_text(item, 'mhouseNm'),
                "법정동": _get_text(item, 'umdNm'),
                "지번": _get_text(item, 'jibun'),
                "거래금액": _get_text(item, 'dealAmount'),
                "전용면적": _get_text(item, 'excluUseAr'),
                "대지권면적": _get_text(item, 'landAr'),
                "층": _get_text(item, 'floor'),
                "건축년도": _get_text(item, 'buildYear'),
                "거래년도": _get_text(item, 'dealYear'),
                "거래월": _get_text(item, 'dealMonth'),
                "거래일": _get_text(item, 'dealDay'),
                "거래유형": _get_text(item, 'dealingGbn'),
                "조회년월": year_month,
            }
            trades.append(trade)

        return trades
    except urllib.error.HTTPError as e:
        if e.code in (401, 403):
            raise  # 인증/미승인 — 상위에서 친절히 안내
        return []
    except:
        return []


def get_villa_trade_range(region_code: str, start_month: str, end_month: str = None, count_per_month: int = 30):
    """연립다세대 매매 실거래가 기간 범위 조회"""
    key_ok, key_error = check_api_key("molit")
    if not key_ok:
        return {"success": False, "error": key_error}

    if not end_month:
        end_month = start_month

    try:
        months = _get_months_range(start_month, end_month)

        if len(months) > 12:
            return {"success": False, "error": "최대 12개월까지만 조회 가능합니다."}

        all_trades = []
        months_with_data = []

        for month in months:
            trades = _fetch_month_data(region_code, month, count_per_month)
            if trades:
                all_trades.extend(trades)
                months_with_data.append(month)

        if all_trades:
            amounts = []
            for t in all_trades:
                try:
                    amounts.append(int(t["거래금액"].replace(",", "").strip()))
                except:
                    pass

            summary = {
                "조회기간": f"{start_month} ~ {end_month}",
                "조회월수": len(months),
                "데이터있는월": len(months_with_data),
                "총거래건수": len(all_trades),
                "평균가": f"{sum(amounts) // len(amounts):,}만원" if amounts else "N/A",
                "최고가": f"{max(amounts):,}만원" if amounts else "N/A",
                "최저가": f"{min(amounts):,}만원" if amounts else "N/A",
            }
        else:
            summary = {
                "조회기간": f"{start_month} ~ {end_month}",
                "조회월수": len(months),
                "총거래건수": 0
            }

        return {
            "success": True,
            "type": "연립다세대 매매 (기간조회)",
            "region_code": region_code,
            "period": f"{start_month} ~ {end_month}",
            "summary": summary,
            "data": all_trades
        }

    except urllib.error.HTTPError as e:
        if e.code in (401, 403):
            return {"success": False, "error": "연립다세대 실거래가 API 권한이 없습니다(403). data.go.kr에서 '국토교통부_연립다세대 매매 실거래가 자료'를 동일 키로 활용신청하면 바로 됩니다."}
        return {"success": False, "error": f"HTTP {e.code}: {e.reason}"}
    except Exception as e:
        return {"success": False, "error": str(e)}


def _get_text(item, tag):
    elem = item.find(tag)
    return elem.text.strip() if elem is not None and elem.text else ""
