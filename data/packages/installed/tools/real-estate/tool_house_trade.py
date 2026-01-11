"""
단독/다가구 매매 실거래가 조회 모듈
국토교통부 공공데이터 API 사용
"""
import urllib.request
import urllib.parse
import xml.etree.ElementTree as ET
import os

SERVICE_KEY = os.environ.get('MOLIT_API_KEY', '5d93a49043da935280488408c84d900a7c673384b77bb9668ea68f32227ee002')
BASE_URL = 'https://apis.data.go.kr/1613000/RTMSDataSvcSHTrade/getRTMSDataSvcSHTrade'

def get_tool_definition():
    return {
        "name": "house_trade_price",
        "description": "단독/다가구 주택 매매 실거래가를 조회합니다. 국토교통부 공공데이터 API를 사용합니다.",
        "input_schema": {
            "type": "object",
            "properties": {
                "region_code": {
                    "type": "string",
                    "description": "법정동 코드 앞 5자리 (예: 서울 종로구=11110, 강남구=11680)"
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

def get_house_trade(region_code: str, year_month: str, count: int = 10):
    """
    단독/다가구 매매 실거래가 조회
    """
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
                "주택유형": _get_text(item, 'houseType'),
                "법정동": _get_text(item, 'umdNm'),
                "지번": _get_text(item, 'jibun'),
                "거래금액": _get_text(item, 'dealAmount'),
                "대지면적": _get_text(item, 'plottageAr'),
                "연면적": _get_text(item, 'totFlrAr'),
                "건축년도": _get_text(item, 'buildYear'),
                "거래년도": _get_text(item, 'dealYear'),
                "거래월": _get_text(item, 'dealMonth'),
                "거래일": _get_text(item, 'dealDay'),
                "거래유형": _get_text(item, 'dealingGbn'),
                "매수자": _get_text(item, 'buyerGbn'),
                "매도자": _get_text(item, 'slerGbn'),
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
            "type": "단독/다가구 매매",
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
    elem = item.find(tag)
    return elem.text.strip() if elem is not None and elem.text else ""
