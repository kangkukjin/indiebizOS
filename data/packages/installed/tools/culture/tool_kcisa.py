"""
tool_kcisa.py - 한국문화정보원(KCISA) 문화정보 조회 API 도구
Culture 패키지

공공데이터포털(data.go.kr)에서 제공하는 한국문화정보원 문화정보 서비스입니다.
전시, 공연, 축제 등 다양한 문화 정보를 검색할 수 있습니다.

API 문서: https://www.data.go.kr/data/15138937/openapi.do

API 키: DATA_GO_KR_API_KEY 환경변수 사용

엔드포인트:
- /period2: 기간별 검색
- /area2: 지역별 검색
- /realm2: 분야별 검색
- /detail2: 상세정보
- /livelihood2: 문화캘린더
"""

import os
import sys
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta

# common 유틸리티 사용
_backend_dir = os.path.join(os.path.dirname(__file__), "..", "..", "..", "..", "backend")
if _backend_dir not in sys.path:
    sys.path.insert(0, os.path.abspath(_backend_dir))

from common.api_client import api_call
from common.auth_manager import check_api_key


def xml_to_dict(element):
    """XML 엘리먼트를 재귀적으로 딕셔너리로 변환"""
    ret = {}
    for child in element:
        if len(child) > 0:
            value = xml_to_dict(child)
        else:
            value = child.text

        if child.tag in ret:
            if not isinstance(ret[child.tag], list):
                ret[child.tag] = [ret[child.tag]]
            ret[child.tag].append(value)
        else:
            ret[child.tag] = value
    return ret


def call_kcisa_api(endpoint, params):
    """KCISA API 호출 (common api_call 사용)"""
    # API 키 확인
    ok, err = check_api_key("data_go_kr")
    if not ok:
        return {
            "error": err,
            "help": "공공데이터포털(data.go.kr)에서 API 키를 발급받으세요."
        }

    # api_call로 HTTP 요청 (XML 응답이므로 raw_response=True)
    # data_go_kr 기본 URL은 https://apis.data.go.kr, KCISA 경로는 /B553457/cultureinfo/{endpoint}
    response_text = api_call(
        "data_go_kr",
        f"/B553457/cultureinfo/{endpoint}",
        params=params,
        timeout=15,
        raw_response=True,
    )

    # api_call이 에러 dict를 반환한 경우
    if isinstance(response_text, dict) and "error" in response_text:
        return response_text

    try:
        # 응답이 JSON인지 확인
        if response_text.strip().startswith("{"):
            import json
            return json.loads(response_text)

        # XML 파싱
        root = ET.fromstring(response_text.encode("utf-8") if isinstance(response_text, str) else response_text)

        # 에러 체크
        header = root.find("header")
        if header is not None:
            result_code = header.findtext("resultCode")
            if result_code != "00":
                return {
                    "error": f"API 오류: {header.findtext('resultMsg')}",
                    "code": result_code
                }

        body = root.find("body")
        if body is not None:
            items_node = body.find("items")
            total_count = int(body.findtext("totalCount", "0"))
            page_no = int(body.findtext("pageNo", "1"))
            num_of_rows = int(body.findtext("numOfRows", "10"))

            items = []
            if items_node is not None:
                for item in items_node.findall("item"):
                    items.append(xml_to_dict(item))

            return {
                "count": total_count,
                "page": page_no,
                "rows": num_of_rows,
                "data": items
            }

        return xml_to_dict(root)

    except ET.ParseError:
        # 가끔 에러 메시지가 평문으로 올 때가 있음
        if "SERVICE KEY IS INVALID" in response_text:
            return {"error": "유효하지 않은 API 키입니다."}
        return {"error": "응답 파싱 실패", "raw": response_text[:200]}
    except Exception as e:
        return {"error": f"조회 실패: {str(e)}"}


def search_culture_events(keyword=None, start_date=None, end_date=None, area=None, rows=10, page=1):
    """
    문화 행사(전시, 공연, 축제 등) 검색

    Args:
        keyword: 검색어
        start_date: 시작일 (YYYYMMDD)
        end_date: 종료일 (YYYYMMDD)
        area: 지역 (서울, 부산 등)
        rows: 결과 수
        page: 페이지 번호
    """
    params = {
        "numOfrows": min(rows, 100),  # API 스펙에 맞게 수정
        "PageNo": page  # API 스펙에 맞게 수정
    }

    # 기간 파라미터 (period2 엔드포인트)
    if start_date:
        params["from"] = start_date.replace("-", "").replace(".", "")
    if end_date:
        params["to"] = end_date.replace("-", "").replace(".", "")

    # 기본 기간 설정 (오늘부터 3개월)
    if not start_date and not end_date:
        today = datetime.now()
        params["from"] = today.strftime("%Y%m%d")
        params["to"] = (today + timedelta(days=90)).strftime("%Y%m%d")

    if keyword:
        params["keyword"] = keyword

    # 지역 파라미터
    if area:
        params["sido"] = area

    # period2 엔드포인트 사용 (기간별 검색)
    result = call_kcisa_api("period2", params)

    if "error" not in result:
        result["search_params"] = {
            "keyword": keyword,
            "start_date": start_date,
            "end_date": end_date,
            "area": area
        }
        result["message"] = f"총 {result.get('count', 0)}건의 문화 정보를 찾았습니다."

    return result


def get_culture_event_detail(seq):
    """
    문화 행사 상세 정보 조회

    Args:
        seq: 행사 일련번호 (UCI 또는 ID)
    """
    if not seq:
        return {"error": "행사 일련번호(seq)가 필요합니다."}

    params = {
        "seq": seq,
        "type": "json"
    }

    return call_kcisa_api("detail2", params)


def quick_search_culture(keyword, rows=10):
    """키워드로 문화 정보 간편 검색"""
    return search_culture_events(keyword=keyword, rows=rows)
