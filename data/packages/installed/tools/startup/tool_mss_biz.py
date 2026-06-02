"""
중소벤처기업부 사업공고 조회 모듈
공공데이터 API 사용
"""
import os
import sys
import xml.etree.ElementTree as ET

# common 유틸리티 사용
_backend_dir = os.path.join(os.path.dirname(__file__), "..", "..", "..", "..", "backend")
if _backend_dir not in sys.path:
    sys.path.insert(0, os.path.abspath(_backend_dir))

from common.api_client import api_call
from common.auth_manager import check_api_key

def get_tool_definition():
    return {
        "name": "search_mss_biz",
        "description": "중소벤처기업부 사업공고를 검색합니다. 정부 중소기업 지원사업 공고 목록을 조회할 수 있습니다.",
        "input_schema": {
            "type": "object",
            "properties": {
                "keyword": {
                    "type": "string",
                    "description": "검색 키워드 (예: 창업, R&D, 수출)"
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

def search_mss_biz(keyword: str = "", count: int = 10):
    """
    중소벤처기업부 사업공고 검색

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

        # api_call로 HTTP 요청 (XML 응답이므로 raw_response=True)
        params = {
            'numOfRows': str(count),
            'pageNo': '1'
        }

        response_text = api_call(
            "data_go_kr",
            "/1421000/mssBizService_v2/getMssBizList",
            params=params,
            timeout=30,
            raw_response=True,
        )

        # api_call이 에러 dict를 반환한 경우
        if isinstance(response_text, dict) and "error" in response_text:
            return {"success": False, "error": response_text["error"]}

        root = ET.fromstring(response_text.encode("utf-8") if isinstance(response_text, str) else response_text)
        result_code = root.find('.//resultCode')

        if result_code is None or result_code.text != '000':
            result_msg = root.find('.//resultMsg')
            return {
                "success": False,
                "error": f"API 오류: {result_msg.text if result_msg is not None else 'Unknown error'}"
            }

        items = root.findall('.//item')
        announcements = []

        for item in items:
            title = _get_text(item, 'pblancNm')

            # 키워드 필터링
            if keyword and keyword not in title:
                continue

            announcement = {
                "사업명": title,
                "공고일": _get_text(item, 'pblancDe'),
                "접수시작일": _get_text(item, 'reqstBeginDe'),
                "접수마감일": _get_text(item, 'reqstEndDe'),
                "담당부서": _get_text(item, 'jrsdInsttNm'),
                "담당자": _get_text(item, 'chargerNm'),
                "연락처": _get_text(item, 'chargerCttpc'),
                "상세URL": _get_text(item, 'detailUrl'),
            }
            announcements.append(announcement)

        total_count = root.find('.//totalCount')

        return {
            "success": True,
            "source": "중소벤처기업부",
            "keyword": keyword if keyword else "전체",
            "total_count": total_count.text if total_count is not None else len(announcements),
            "filtered_count": len(announcements),
            "data": announcements
        }

    except Exception as e:
        return {
            "success": False,
            "error": str(e)
        }

def _get_text(item, tag):
    elem = item.find(tag)
    return elem.text.strip() if elem is not None and elem.text else ""
