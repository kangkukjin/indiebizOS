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

        # 게이트웨이 강등: data.go.kr 의 이 MSS 서비스(1421000/mssBizService*)가
        # 2026-06 현재 폐기되어 404("API not found")·500("Unexpected errors")를 돌려준다.
        # api_call 은 404 를 에러 dict 로, 500 은 raw 평문(비-XML)으로 주므로 둘 다 잡아
        # 명확한 안내로 강등한다 (ET 파싱 크래시·cryptic 404 방지). 복구하려면 사용자가
        # data.go.kr 에서 현행 중기부 사업공고 API(데이터셋 15113297 등)를 활용신청 후
        # 엔드포인트를 갱신해야 함. 그때까지는 K-Startup(source:kstartup)으로 충분.
        _UNAVAIL = {
            "success": False,
            "available": False,
            "error": "중기부(MSS) 사업공고 API 미가용 — data.go.kr 엔드포인트 폐기 추정(활용신청 필요). 정부 창업·지원사업은 source:kstartup(K-Startup) 사용 권장.",
        }
        if isinstance(response_text, dict) and "error" in response_text:
            return _UNAVAIL
        txt = response_text if isinstance(response_text, str) else response_text.decode("utf-8", "ignore")
        if not txt.lstrip().startswith("<"):
            return _UNAVAIL

        root = ET.fromstring(txt.encode("utf-8"))
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
