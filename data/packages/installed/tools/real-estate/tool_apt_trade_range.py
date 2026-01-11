"""
아파트 매매 실거래가 기간 범위 조회 모듈
여러 달을 한 번에 조회하여 API 호출 횟수 감소
"""
import urllib.request
import urllib.parse
import xml.etree.ElementTree as ET
import os
from datetime import datetime

SERVICE_KEY = os.environ.get('MOLIT_API_KEY', '5d93a49043da935280488408c84d900a7c673384b77bb9668ea68f32227ee002')
BASE_URL = 'https://apis.data.go.kr/1613000/RTMSDataSvcAptTrade/getRTMSDataSvcAptTrade'

def get_tool_definition():
    return {
        "name": "apt_trade_range",
        "description": "아파트 매매 실거래가를 기간 범위로 조회합니다. 여러 달을 한번에 조회 가능. [중요] 거래금액 단위는 '만원'입니다. 예: 64,000 = 6억4천만원. 최근 N개월 조회시 이 도구를 사용하세요.",
        "input_schema": {
            "type": "object",
            "properties": {
                "region_code": {
                    "type": "string",
                    "description": "법정동 코드 앞 5자리 (예: 서울 강남구=11680, 서초구=11650)"
                },
                "start_month": {
                    "type": "string",
                    "description": "조회 시작 년월 (YYYYMM 형식, 예: 202311)"
                },
                "end_month": {
                    "type": "string",
                    "description": "조회 종료 년월 (YYYYMM 형식, 예: 202401). 생략시 start_month와 동일"
                },
                "count_per_month": {
                    "type": "integer",
                    "default": 30,
                    "minimum": 1,
                    "maximum": 100,
                    "description": "월별 최대 조회 건수"
                }
            },
            "required": ["region_code", "start_month"]
        }
    }

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
                "아파트명": _get_text(item, 'aptNm'),
                "법정동": _get_text(item, 'umdNm'),
                "거래금액": _get_text(item, 'dealAmount'),
                "전용면적": _get_text(item, 'excluUseAr'),
                "층": _get_text(item, 'floor'),
                "건축년도": _get_text(item, 'buildYear'),
                "거래년도": _get_text(item, 'dealYear'),
                "거래월": _get_text(item, 'dealMonth'),
                "거래일": _get_text(item, 'dealDay'),
                "조회년월": year_month,
            }
            trades.append(trade)

        return trades
    except:
        return []

def get_apt_trade_range(region_code: str, start_month: str, end_month: str = None, count_per_month: int = 30):
    """
    아파트 매매 실거래가 기간 범위 조회
    """
    if not end_month:
        end_month = start_month

    try:
        months = _get_months_range(start_month, end_month)

        if len(months) > 12:
            return {
                "success": False,
                "error": "최대 12개월까지만 조회 가능합니다."
            }

        all_trades = []
        months_with_data = []

        for month in months:
            trades = _fetch_month_data(region_code, month, count_per_month)
            if trades:
                all_trades.extend(trades)
                months_with_data.append(month)

        # 요약 통계
        if all_trades:
            amounts = []
            for t in all_trades:
                try:
                    amt = int(t["거래금액"].replace(",", "").strip())
                    amounts.append(amt)
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
            "type": "아파트 매매 (기간조회)",
            "region_code": region_code,
            "period": f"{start_month} ~ {end_month}",
            "summary": summary,
            "data": all_trades
        }

    except Exception as e:
        return {
            "success": False,
            "error": str(e)
        }

def _get_text(item, tag):
    elem = item.find(tag)
    return elem.text.strip() if elem is not None and elem.text else ""
