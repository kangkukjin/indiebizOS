"""
단독/다가구 매매 실거래가 기간 범위 조회 모듈
여러 달을 병렬 조회 · 페이징으로 그 달 전부 · 잘림은 truncated 로 신고
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
# 403 문구의 정본 — 데이터셋 이름·신청 링크를 여기서 손으로 적지 않는다.
from common.datagokr_catalog import permission_error
from common.pkg_utils import load_sibling
_molit = load_sibling(__file__, "realty_molit_common")  # 페이징·잘림 신고·월 병렬 공용

SERVICE_KEY = get_api_key('MOLIT_API_KEY') or ''
BASE_URL = 'https://apis.data.go.kr/1613000/RTMSDataSvcSHTrade/getRTMSDataSvcSHTrade'

def get_tool_definition():
    return {
        "name": "house_trade_range",
        "description": "단독/다가구 주택 매매 실거래가를 기간 범위로 조회합니다. 여러 달을 한번에 조회 가능. [중요] 거래금액 단위는 '만원'입니다. 예: 64,000 = 6억4천만원, 5,360 = 5,360만원. 최근 N개월 조회시 이 도구를 사용하세요.",
        "input_schema": {
            "type": "object",
            "properties": {
                "region_code": {
                    "type": "string",
                    "description": "법정동 코드 앞 5자리 (예: 서울 종로구=11110, 충북 청주시흥덕구=43113)"
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
                    "minimum": 1,
                    "description": "월별 반환 상한. 생략하면 그 달 전부(페이징). 잘리면 truncated 로 신고"
                }
            },
            "required": ["region_code", "start_month"]
        }
    }

def _parse_item(item, year_month: str) -> dict:
    """XML item 한 건 → dict (필드 사전은 이 도구 고유)"""
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
        "조회년월": year_month,
    }
    return trade


def _fetch_month_data(region_code: str, year_month: str, count) -> list:
    """한 달 데이터 조회 (호환용 — 페이징은 공용 모듈이 한다)"""
    return _molit.fetch_month_paged(BASE_URL, SERVICE_KEY, region_code, year_month, count, _parse_item)["rows"]

def get_house_trade_range(region_code: str, start_month: str, end_month: str = None, count_per_month=None):
    """
    단독/다가구 매매 실거래가 기간 범위 조회
    """
    key_ok, key_error = check_api_key("molit")
    if not key_ok:
        return {"success": False, "error": key_error}

    if not end_month:
        end_month = start_month

    try:
        months = _molit.get_months_range(start_month, end_month)

        if len(months) > 12:
            return {
                "success": False,
                "error": "최대 12개월까지만 조회 가능합니다."
            }

        all_trades, months_with_data, total, truncated, errors = _molit.fetch_range(
            BASE_URL, SERVICE_KEY, region_code, months, count_per_month, _parse_item)

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
                "전체건수": total,
                "잘림": truncated,
                "평균가": f"{sum(amounts) // len(amounts):,}만원" if amounts else "N/A",
                "최고가": f"{max(amounts):,}만원" if amounts else "N/A",
                "최저가": f"{min(amounts):,}만원" if amounts else "N/A",
            }
        else:
            summary = {
                "조회기간": f"{start_month} ~ {end_month}",
                "조회월수": len(months),
                "총거래건수": 0,
                "전체건수": total,
                "잘림": truncated
            }

        return {
            "success": True,
            "type": "단독/다가구 매매 (기간조회)",
            "region_code": region_code,
            "period": f"{start_month} ~ {end_month}",
            "total": total,
            "truncated": truncated,
            "errors": errors,  # {YYYYMM: 사유} — 비면 전 월 완전. 타임아웃 달은 0건이 아니라 불완전
            "summary": summary,
            "data": all_trades
        }

    except urllib.error.HTTPError as e:
        if e.code in (401, 403):
            return {"success": False, "error": permission_error(BASE_URL, e.code)}
        return {"success": False, "error": f"HTTP {e.code}: {e.reason}"}
    except Exception as e:
        return {
            "success": False,
            "error": str(e)
        }

_get_text = _molit.get_text
