"""
아파트 전월세 실거래가 조회 모듈 (기간 범위 지원)
국토교통부 공공데이터 API 사용
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
BASE_URL = 'https://apis.data.go.kr/1613000/RTMSDataSvcAptRent/getRTMSDataSvcAptRent'

def _parse_item(item, year_month: str) -> dict:
    """XML item 한 건 → dict (필드 사전은 이 도구 고유)"""
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
    return rent


def _fetch_month_data(region_code: str, year_month: str, count) -> list:
    """한 달 데이터 조회 (호환용 — 페이징은 공용 모듈이 한다)"""
    return _molit.fetch_month_paged(BASE_URL, SERVICE_KEY, region_code, year_month, count, _parse_item)["rows"]

def get_apt_rent(region_code: str, start_month: str, end_month: str = None, count_per_month=None):
    """
    아파트 전월세 실거래가 기간 범위 조회
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

        all_rents, months_with_data, total, truncated, errors = _molit.fetch_range(
            BASE_URL, SERVICE_KEY, region_code, months, count_per_month, _parse_item)

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
                "전체건수": total,
                "잘림": truncated,
                "전세": jeonse_count,
                "월세": wolse_count,
                "전세_평균보증금": f"{sum(jeonse_deposits) // len(jeonse_deposits):,}만원" if jeonse_deposits else "N/A",
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
            "type": "아파트 전월세 (기간조회)",
            "region_code": region_code,
            "period": f"{start_month} ~ {end_month}",
            "total": total,
            "truncated": truncated,
            "errors": errors,  # {YYYYMM: 사유} — 비면 전 월 완전. 타임아웃 달은 0건이 아니라 불완전
            "summary": summary,
            "data": all_rents
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
