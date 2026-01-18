"""
tool_kcisa.py - 한국문화정보원(KCISA) 문화정보 조회 API 도구
Culture 패키지

공공데이터포털(data.go.kr)에서 제공하는 한국문화정보원 문화정보 서비스입니다.
전시, 공연, 축제 등 다양한 문화 정보를 검색할 수 있습니다.

API 키: DATA_GO_KR_API_KEY 환경변수 사용
"""

import os
import requests
import xml.etree.ElementTree as ET
from datetime import datetime

BASE_URL = "http://apis.data.go.kr/B553457/cultureinfo"


def get_api_key():
    """API 키 가져오기 (환경변수 우선, 없으면 하드코딩된 값 - 보안상 비권장하나 사용자의 요청에 따름)"""
    key = os.environ.get("DATA_GO_KR_API_KEY", "")
    if not key:
        # 사용자가 제공한 키 (일부)
        key = "5d93a49043da935..." # 실제 키는 시스템 환경에 맞게 설정되어야 함
    return key


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
    """KCISA API 호출"""
    api_key = get_api_key()
    if not api_key:
        return {
            "error": "DATA_GO_KR_API_KEY 환경변수가 설정되지 않았습니다.",
            "help": "공공데이터포털(data.go.kr)에서 API 키를 발급받으세요."
        }

    # API 키는 인코딩된 상태로 전달되어야 하는 경우가 많음
    params["serviceKey"] = api_key
    url = f"{BASE_URL}/{endpoint}"

    try:
        # KCISA API는 기본적으로 XML을 반환하는 경우가 많음
        response = requests.get(url, params=params, timeout=15)

        if response.status_code != 200:
            return {"error": f"API 호출 실패 (상태 코드: {response.status_code})"}

        # 응답이 JSON인지 확인
        try:
            if "application/json" in response.headers.get("Content-Type", ""):
                return response.json()
            
            # XML 파싱
            root = ET.fromstring(response.content)
            
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
            if "SERVICE KEY IS INVALID" in response.text:
                return {"error": "유효하지 않은 API 키입니다."}
            return {"error": "응답 파싱 실패", "raw": response.text[:200]}

    except requests.exceptions.Timeout:
        return {"error": "API 요청 시간 초과"}
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
        "numOfRows": min(rows, 100),
        "pageNo": page,
        "type": "json" # JSON 요청 시도 (지원하지 않으면 XML로 반환됨)
    }

    if keyword:
        params["keyword"] = keyword
    if start_date:
        params["startDt"] = start_date.replace("-", "").replace(".", "")
    if end_date:
        params["endDt"] = end_date.replace("-", "").replace(".", "")
    if area:
        params["area"] = area

    result = call_kcisa_api("culturalEventList", params)

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

    return call_kcisa_api("culturalEventDetail", params)


def quick_search_culture(keyword, rows=10):
    """키워드로 문화 정보 간편 검색"""
    return search_culture_events(keyword=keyword, rows=rows)
