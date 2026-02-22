"""
K-Startup 창업지원 사업공고 조회 모듈
창업진흥원 공공데이터 API 사용 (2024년 신규 API)
"""
import os
import sys
import json

# common 유틸리티 사용
_backend_dir = os.path.join(os.path.dirname(__file__), "..", "..", "..", "..", "backend")
if _backend_dir not in sys.path:
    sys.path.insert(0, os.path.abspath(_backend_dir))

from common.api_client import api_call
from common.auth_manager import check_api_key

# 신규 API 엔드포인트 (2024~)
ENDPOINTS = {
    'announcement': '/B552735/kisedKstartupService01/getAnnouncementInformation01',  # 지원사업 공고
    'business': '/B552735/kisedKstartupService01/getBusinessInformation01',          # 통합공고 지원사업
    'content': '/B552735/kisedKstartupService01/getContentInformation01',            # 콘텐츠 정보
    'statistics': '/B552735/kisedKstartupService01/getStatisticalInformation01',     # 통계보고서
}

def get_tool_definition():
    return {
        "name": "search_kstartup",
        "description": "K-Startup 창업지원 사업공고를 검색합니다. 창업진흥원에서 제공하는 창업지원 사업, 공고 정보를 조회할 수 있습니다.",
        "input_schema": {
            "type": "object",
            "properties": {
                "keyword": {
                    "type": "string",
                    "description": "검색 키워드 (예: 예비창업, 기술창업, 소상공인)"
                },
                "count": {
                    "type": "integer",
                    "default": 10,
                    "minimum": 1,
                    "maximum": 50,
                    "description": "조회할 건수"
                }
            },
            "required": []
        }
    }

def search_kstartup(keyword: str = "", count: int = 10):
    """
    K-Startup 창업지원 사업공고 검색 (신규 API)

    Args:
        keyword: 검색 키워드
        count: 조회 건수

    Returns:
        dict: 조회 결과
    """
    try:
        # API 키 확인
        ok, err = check_api_key("data_go_kr")
        if not ok:
            return {"success": False, "error": err}

        # api_call로 HTTP 요청 (JSON 응답)
        params = {
            'page': '1',
            'perPage': str(count),
            'returnType': 'json'
        }

        result = api_call(
            "data_go_kr",
            ENDPOINTS['announcement'],
            params=params,
            extra_headers={'Accept': 'application/json'},
            timeout=30,
        )

        # api_call이 에러 dict를 반환한 경우
        if isinstance(result, dict) and "error" in result:
            return {"success": False, "error": result["error"]}

        # 문자열 응답인 경우 JSON 파싱
        if isinstance(result, str):
            result = json.loads(result)

        # 신규 API 응답 구조
        items = result.get('data', [])
        total_count = result.get('totalCount', len(items))

        # 키워드 필터링 (API에서 직접 지원하지 않으면 클라이언트에서 필터링)
        if keyword and items:
            items = [item for item in items if keyword in str(item)]

        announcements = []
        for item in items:
            announcement = {
                "사업명": item.get('pblancNm', item.get('pblanc_nm', '')),
                "사업유형": item.get('bizPbancCtgryNm', item.get('biz_pbanc_ctgry_nm', '')),
                "주관기관": item.get('jrsdInsttNm', item.get('jrsd_instt_nm', '')),
                "접수시작일": item.get('reqstBeginDe', item.get('reqst_begin_de', '')),
                "접수마감일": item.get('reqstEndDe', item.get('reqst_end_de', '')),
                "공고상태": item.get('pblancSttusNm', item.get('pbanc_sttus_nm', '')),
                "상세URL": item.get('detailPageUrl', item.get('detail_page_url', '')),
            }
            announcements.append(announcement)

        return {
            "success": True,
            "source": "K-Startup (창업진흥원)",
            "keyword": keyword if keyword else "전체",
            "total_count": total_count,
            "count": len(announcements),
            "data": announcements
        }

    except Exception as e:
        return {
            "success": False,
            "error": str(e)
        }
