"""
아파트 전월세 실거래가 조회 모듈 (기간 범위 지원)
국토교통부 공공데이터 API 사용
"""
import urllib.request
import urllib.parse
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
BASE_URL = 'https://apis.data.go.kr/1613000/RTMSDataSvcAptRent/getRTMSDataSvcAptRent'

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
        rents = []

        for item in items:
            deposit = _get_text(item, 'deposit')
            monthly_rent = _get_text(item, 'monthlyRent')
            rent_type = "전세" if monthly_rent == "0" or not monthly_rent else "월세"

            rent = {
                "아파트명": _get_text(item, 'aptNm'),
                "법정동": _get_text(item, 'umdNm'),
                "지번": _get_text(item, 'jibun'),
                "계약유형": rent_type,
                "보증금": deposit,
                "월세": monthly_rent if rent_type == "월세" else "",
                "전용면적": _get_text(item, 'excluUseAr'),
                "층": _get_text(item, 'floor'),
                "건축년도": _get_text(item, 'buildYear'),
                "거래년도": _get_text(item, 'dealYear'),
                "거래월": _get_text(item, 'dealMonth'),
                "거래일": _get_text(item, 'dealDay'),
                "조회년월": year_month,
            }
            rents.append(rent)

        return rents
    except:
        return []

def get_apt_rent(region_code: str, start_month: str, end_month: str = None, count_per_month: int = 30):
    """
    아파트 전월세 실거래가 기간 범위 조회
    """
    key_ok, key_error = check_api_key("molit")
    if not key_ok:
        return {"success": False, "error": key_error}

    if not end_month:
        end_month = start_month

    try:
        months = _get_months_range(start_month, end_month)

        if len(months) > 12:
            return {
                "success": False,
                "error": "최대 12개월까지만 조회 가능합니다."
            }

        all_rents = []
        months_with_data = []

        for month in months:
            rents = _fetch_month_data(region_code, month, count_per_month)
            if rents:
                all_rents.extend(rents)
                months_with_data.append(month)

        # 요약 통계
        if all_rents:
            jeonse_count = sum(1 for r in all_rents if r["계약유형"] == "전세")
            wolse_count = sum(1 for r in all_rents if r["계약유형"] == "월세")

            jeonse_deposits = []
            for r in all_rents:
                if r["계약유형"] == "전세":
                    try:
                        amt = int(r["보증금"].replace(",", "").strip())
                        jeonse_deposits.append(amt)
                    except:
                        pass

            summary = {
                "조회기간": f"{start_month} ~ {end_month}",
                "조회월수": len(months),
                "데이터있는월": len(months_with_data),
                "총거래건수": len(all_rents),
                "전세": jeonse_count,
                "월세": wolse_count,
                "전세_평균보증금": f"{sum(jeonse_deposits) // len(jeonse_deposits):,}만원" if jeonse_deposits else "N/A",
            }
        else:
            summary = {
                "조회기간": f"{start_month} ~ {end_month}",
                "조회월수": len(months),
                "총거래건수": 0
            }

        return {
            "success": True,
            "type": "아파트 전월세 (기간조회)",
            "region_code": region_code,
            "period": f"{start_month} ~ {end_month}",
            "summary": summary,
            "data": all_rents
        }

    except Exception as e:
        return {
            "success": False,
            "error": str(e)
        }

def _get_text(item, tag):
    elem = item.find(tag)
    return elem.text.strip() if elem is not None and elem.text else ""
