"""
아파트 매매 실거래가 조회 모듈
국토교통부 공공데이터 API 사용
"""
import urllib.request
import urllib.parse
import xml.etree.ElementTree as ET
import os
import sys

# common 유틸리티 사용
_backend_dir = os.path.join(os.path.dirname(__file__), "..", "..", "..", "..", "backend")
if _backend_dir not in sys.path:
    sys.path.insert(0, os.path.abspath(_backend_dir))

from common.auth_manager import get_api_key, check_api_key

# API 설정
SERVICE_KEY = get_api_key('MOLIT_API_KEY') or ''
BASE_URL = 'https://apis.data.go.kr/1613000/RTMSDataSvcAptTrade/getRTMSDataSvcAptTrade'

def get_tool_definition():
    return {
        "name": "apt_trade_price",
        "description": "아파트 매매 실거래가를 조회합니다. 국토교통부 공공데이터 API를 사용합니다.",
        "input_schema": {
            "type": "object",
            "properties": {
                "region_code": {
                    "type": "string",
                    "description": "법정동 코드 앞 5자리 (예: 서울 종로구=11110, 강남구=11680, 서초구=11650)"
                },
                "year_month": {
                    "type": "string",
                    "description": "조회 년월 (YYYYMM 형식, 예: 202401)"
                },
                "count": {
                    "type": "integer",
                    "default": 10,
                    "minimum": 1,
                    "maximum": 100,
                    "description": "조회할 건수"
                }
            },
            "required": ["region_code", "year_month"]
        }
    }

def get_apt_trade(region_code: str, year_month: str, count: int = 10):
    """
    아파트 매매 실거래가 조회

    Args:
        region_code: 법정동 코드 앞 5자리
        year_month: 조회 년월 (YYYYMM)
        count: 조회 건수

    Returns:
        dict: 조회 결과
    """
    key_ok, key_error = check_api_key("molit")
    if not key_ok:
        return {"success": False, "error": key_error}

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
            result_msg = root.find('.//resultMsg')
            return {
                "success": False,
                "error": f"API 오류: {result_msg.text if result_msg is not None else 'Unknown error'}"
            }

        items = root.findall('.//item')
        trades = []

        for item in items:
            trade = {
                "아파트명": _get_text(item, 'aptNm'),
                "법정동": _get_text(item, 'umdNm'),
                "지번": _get_text(item, 'jibun'),
                "거래금액": _get_text(item, 'dealAmount'),
                "전용면적": _get_text(item, 'excluUseAr'),
                "층": _get_text(item, 'floor'),
                "건축년도": _get_text(item, 'buildYear'),
                "거래년도": _get_text(item, 'dealYear'),
                "거래월": _get_text(item, 'dealMonth'),
                "거래일": _get_text(item, 'dealDay'),
                "거래유형": _get_text(item, 'dealingGbn'),
                "매수자": _get_text(item, 'buyerGbn'),
                "매도자": _get_text(item, 'slerGbn'),
                "동": _get_text(item, 'aptDong'),
                "등기일자": _get_text(item, 'rgstDate'),
            }
            trades.append(trade)

        # 요약 통계
        if trades:
            amounts = []
            for t in trades:
                try:
                    amt = int(t["거래금액"].replace(",", "").strip())
                    amounts.append(amt)
                except:
                    pass

            summary = {
                "조회건수": len(trades),
                "평균가": f"{sum(amounts) // len(amounts):,}만원" if amounts else "N/A",
                "최고가": f"{max(amounts):,}만원" if amounts else "N/A",
                "최저가": f"{min(amounts):,}만원" if amounts else "N/A",
            }
        else:
            summary = {"조회건수": 0}

        return {
            "success": True,
            "region_code": region_code,
            "year_month": year_month,
            "summary": summary,
            "data": trades
        }

    except Exception as e:
        return {
            "success": False,
            "error": str(e)
        }

def _get_text(item, tag):
    """XML 요소에서 텍스트 추출"""
    elem = item.find(tag)
    return elem.text.strip() if elem is not None and elem.text else ""
