"""
KOSIS (국가통계포털) Open API 도구
https://kosis.kr/openapi/

주요 기능:
- 통계목록 검색/조회
- 통계자료(데이터) 조회
- 통계설명 조회
- 통합검색
- 주요지표 조회
"""
import requests
import json
from typing import Optional, Dict, Any, List
from datetime import datetime

# KOSIS API 인증키
API_KEY = "NjcyYjY5ODFkMTU2MzU2MDM4YzcwNTA5NDNhMjhlMWE="

# KOSIS API 엔드포인트
BASE_URL = "https://kosis.kr/openapi"
ENDPOINTS = {
    "statistics_list": f"{BASE_URL}/statisticsList.do",
    "statistics_data": f"{BASE_URL}/Param/statisticsParameterData.do",
    "statistics_info": f"{BASE_URL}/statisticsInfo.do",
    "integrated_search": f"{BASE_URL}/search/search.do",
    "indicators": f"{BASE_URL}/indicator/indicator.do"
}

# 서비스뷰 코드 설명
VIEW_CODES = {
    "MT_ZTITLE": "국내통계 주제별",
    "MT_OTITLE": "국내통계 기관별",
    "MT_GTITLE01": "e-지방지표(주제별)",
    "MT_GTITLE02": "e-지방지표(지역별)",
    "MT_CHOSUN_TITLE": "광복이전통계(1908~1943)",
    "MT_HANKUK_TITLE": "대한민국통계연감",
    "MT_STOP_TITLE": "작성중지통계",
    "MT_RTITLE": "국제통계",
    "MT_BUKHAN": "북한통계",
    "MT_TM1_TITLE": "대상별통계",
    "MT_TM2_TITLE": "이슈별통계",
    "MT_ETITLE": "영문 KOSIS"
}


def _make_request(url: str, params: Dict[str, Any]) -> Dict[str, Any]:
    """API 요청 공통 함수"""
    try:
        response = requests.get(url, params=params, timeout=30)
        response.raise_for_status()

        # JSON 응답 파싱
        try:
            data = response.json()
        except json.JSONDecodeError:
            # 일부 API는 JSONP 형식으로 반환할 수 있음
            text = response.text
            if text.startswith("(") and text.endswith(")"):
                text = text[1:-1]
            data = json.loads(text)

        return {
            "success": True,
            "data": data
        }
    except requests.exceptions.Timeout:
        return {"success": False, "error": "요청 시간 초과"}
    except requests.exceptions.RequestException as e:
        return {"success": False, "error": f"API 요청 실패: {str(e)}"}
    except Exception as e:
        return {"success": False, "error": f"오류 발생: {str(e)}"}


def search_statistics(
    keyword: Optional[str] = None,
    vw_cd: str = "MT_ZTITLE",
    parent_list_id: Optional[str] = None
) -> Dict[str, Any]:
    """
    KOSIS 통계목록 검색/조회

    Args:
        keyword: 검색 키워드
        vw_cd: 서비스뷰 코드 (기본: 주제별)
        parent_list_id: 상위 목록 ID

    Returns:
        통계목록 검색 결과
    """
    params = {
        "method": "getList",
        "apiKey": API_KEY,
        "vwCd": vw_cd,
        "format": "json",
        "jsonVD": "Y"
    }

    if keyword:
        params["searchNm"] = keyword

    if parent_list_id:
        params["parentListId"] = parent_list_id

    result = _make_request(ENDPOINTS["statistics_list"], params)

    if result["success"] and result.get("data"):
        data = result["data"]
        # 결과 가공
        if isinstance(data, list):
            items = []
            for item in data:
                items.append({
                    "list_id": item.get("LIST_ID", ""),
                    "list_name": item.get("LIST_NM", ""),
                    "org_id": item.get("ORG_ID", ""),
                    "org_name": item.get("ORG_NM", ""),
                    "tbl_id": item.get("TBL_ID", ""),
                    "tbl_name": item.get("TBL_NM", ""),
                    "stat_id": item.get("STAT_ID", ""),
                    "stat_name": item.get("STAT_NM", ""),
                    "updated": item.get("RECPT_DE", "")
                })
            result["data"] = items
            result["count"] = len(items)
            result["view_code"] = vw_cd
            result["view_name"] = VIEW_CODES.get(vw_cd, vw_cd)

    return result


def get_statistics_data(
    org_id: str,
    tbl_id: str,
    itm_id: str = "ALL",
    obj_l1: str = "ALL",
    obj_l2: str = "ALL",
    obj_l3: str = "ALL",
    prd_se: str = "Y",
    start_prd_de: Optional[str] = None,
    end_prd_de: Optional[str] = None
) -> Dict[str, Any]:
    """
    KOSIS 통계자료(데이터) 조회

    Args:
        org_id: 기관 ID
        tbl_id: 통계표 ID
        itm_id: 항목 ID (기본: ALL)
        obj_l1~l3: 분류 ID (기본: ALL)
        prd_se: 수록주기 (Y/H/Q/M/D)
        start_prd_de: 시작 시점
        end_prd_de: 종료 시점

    Returns:
        통계 데이터
    """
    # 기본 시점 설정 (최근 5년)
    current_year = datetime.now().year
    if not end_prd_de:
        end_prd_de = str(current_year)
    if not start_prd_de:
        start_prd_de = str(current_year - 4)

    params = {
        "method": "getList",
        "apiKey": API_KEY,
        "orgId": org_id,
        "tblId": tbl_id,
        "itmId": itm_id,
        "objL1": obj_l1,
        "prdSe": prd_se,
        "startPrdDe": start_prd_de,
        "endPrdDe": end_prd_de,
        "format": "json",
        "jsonVD": "Y"
    }

    # 분류2, 분류3은 ALL이 아닌 경우에만 추가 (일부 통계표는 분류가 1개만 있음)
    if obj_l2 and obj_l2 != "ALL":
        params["objL2"] = obj_l2
    if obj_l3 and obj_l3 != "ALL":
        params["objL3"] = obj_l3

    result = _make_request(ENDPOINTS["statistics_data"], params)

    if result["success"] and result.get("data"):
        data = result["data"]
        # 에러 응답 체크
        if isinstance(data, dict) and data.get("err"):
            result["success"] = False
            result["error"] = data.get("errMsg", "알 수 없는 오류")
            result["data"] = None
        elif isinstance(data, list):
            items = []
            for item in data:
                items.append({
                    "org_id": item.get("ORG_ID", ""),
                    "tbl_id": item.get("TBL_ID", ""),
                    "tbl_name": item.get("TBL_NM", ""),
                    "item_id": item.get("ITM_ID", ""),
                    "item_name": item.get("ITM_NM", ""),
                    "unit": item.get("UNIT_NM", ""),
                    "c1_id": item.get("C1", ""),
                    "c1_name": item.get("C1_NM", ""),
                    "c1_obj_name": item.get("C1_OBJ_NM", ""),
                    "c2_id": item.get("C2", ""),
                    "c2_name": item.get("C2_NM", ""),
                    "c2_obj_name": item.get("C2_OBJ_NM", ""),
                    "c3_id": item.get("C3", ""),
                    "c3_name": item.get("C3_NM", ""),
                    "period": item.get("PRD_DE", ""),
                    "value": item.get("DT", ""),
                    "updated": item.get("LST_CHN_DE", "")
                })
            result["data"] = items
            result["count"] = len(items)
            result["query"] = {
                "org_id": org_id,
                "tbl_id": tbl_id,
                "period": f"{start_prd_de} ~ {end_prd_de}"
            }

    return result


def get_statistics_info(
    org_id: str,
    tbl_id: str
) -> Dict[str, Any]:
    """
    통계표 상세 정보(메타데이터) 조회

    Args:
        org_id: 기관 ID
        tbl_id: 통계표 ID

    Returns:
        통계표 메타데이터
    """
    params = {
        "method": "getList",
        "apiKey": API_KEY,
        "orgId": org_id,
        "tblId": tbl_id,
        "format": "json",
        "jsonVD": "Y"
    }

    result = _make_request(ENDPOINTS["statistics_info"], params)

    if result["success"] and result.get("data"):
        data = result["data"]
        # 메타데이터 가공
        if isinstance(data, dict):
            result["data"] = {
                "org_id": org_id,
                "org_name": data.get("ORG_NM", ""),
                "tbl_id": tbl_id,
                "tbl_name": data.get("TBL_NM", ""),
                "stat_name": data.get("STAT_NM", ""),
                "period_type": data.get("PRD_SE", ""),
                "start_period": data.get("START_PRD", ""),
                "end_period": data.get("END_PRD", ""),
                "items": data.get("ITM_ID", []),
                "classifications": data.get("OBJ_VAR_ID", [])
            }

    return result


def integrated_search(
    keyword: str,
    count: int = 10
) -> Dict[str, Any]:
    """
    KOSIS 통합검색

    Args:
        keyword: 검색 키워드
        count: 검색 결과 수

    Returns:
        통합검색 결과
    """
    params = {
        "method": "getList",
        "apiKey": API_KEY,
        "searchNm": keyword,
        "resultCount": min(count, 100),
        "format": "json",
        "jsonVD": "Y"
    }

    result = _make_request(ENDPOINTS["integrated_search"], params)

    if result["success"] and result.get("data"):
        data = result["data"]
        if isinstance(data, list):
            items = []
            for item in data:
                items.append({
                    "type": item.get("TYPE", ""),
                    "org_id": item.get("ORG_ID", ""),
                    "org_name": item.get("ORG_NM", ""),
                    "tbl_id": item.get("TBL_ID", ""),
                    "tbl_name": item.get("TBL_NM", ""),
                    "stat_name": item.get("STAT_NM", ""),
                    "description": item.get("CONT", "")
                })
            result["data"] = items
            result["count"] = len(items)
            result["keyword"] = keyword

    return result


def get_indicators(
    indicator_id: Optional[str] = None,
    start_prd_de: Optional[str] = None,
    end_prd_de: Optional[str] = None
) -> Dict[str, Any]:
    """
    KOSIS 주요지표 조회

    Args:
        indicator_id: 지표 ID (없으면 목록 조회)
        start_prd_de: 시작 시점
        end_prd_de: 종료 시점

    Returns:
        주요지표 데이터
    """
    params = {
        "method": "getList",
        "apiKey": API_KEY,
        "format": "json",
        "jsonVD": "Y"
    }

    if indicator_id:
        params["indicatorId"] = indicator_id
        if start_prd_de:
            params["startPrdDe"] = start_prd_de
        if end_prd_de:
            params["endPrdDe"] = end_prd_de

    result = _make_request(ENDPOINTS["indicators"], params)

    if result["success"] and result.get("data"):
        data = result["data"]
        if isinstance(data, list):
            items = []
            for item in data:
                items.append({
                    "indicator_id": item.get("INDICATOR_ID", ""),
                    "indicator_name": item.get("INDICATOR_NM", ""),
                    "org_name": item.get("ORG_NM", ""),
                    "period": item.get("PRD_DE", ""),
                    "value": item.get("DT", ""),
                    "unit": item.get("UNIT_NM", "")
                })
            result["data"] = items
            result["count"] = len(items)

    return result


def get_tool_definitions() -> List[Dict[str, Any]]:
    """도구 정의 반환"""
    return [
        {
            "name": "kosis_search_statistics",
            "description": "KOSIS 통계목록을 검색합니다. 키워드로 관련 통계표를 찾거나, 서비스뷰별로 통계목록을 조회할 수 있습니다.",
            "input_schema": {
                "type": "object",
                "properties": {
                    "keyword": {"type": "string", "description": "검색 키워드"},
                    "vw_cd": {"type": "string", "description": "서비스뷰 코드", "default": "MT_ZTITLE"},
                    "parent_list_id": {"type": "string", "description": "상위 목록 ID"}
                }
            }
        },
        {
            "name": "kosis_get_data",
            "description": "KOSIS에서 특정 통계표의 데이터를 조회합니다.",
            "input_schema": {
                "type": "object",
                "properties": {
                    "org_id": {"type": "string", "description": "통계 기관 ID"},
                    "tbl_id": {"type": "string", "description": "통계표 ID"},
                    "itm_id": {"type": "string", "default": "ALL"},
                    "obj_l1": {"type": "string", "default": "ALL"},
                    "obj_l2": {"type": "string", "default": "ALL"},
                    "obj_l3": {"type": "string", "default": "ALL"},
                    "prd_se": {"type": "string", "default": "Y"},
                    "start_prd_de": {"type": "string"},
                    "end_prd_de": {"type": "string"}
                },
                "required": ["org_id", "tbl_id"]
            }
        },
        {
            "name": "kosis_get_statistics_info",
            "description": "통계표의 상세 설명(메타데이터)을 조회합니다.",
            "input_schema": {
                "type": "object",
                "properties": {
                    "org_id": {"type": "string"},
                    "tbl_id": {"type": "string"}
                },
                "required": ["org_id", "tbl_id"]
            }
        },
        {
            "name": "kosis_integrated_search",
            "description": "KOSIS 통합검색을 수행합니다.",
            "input_schema": {
                "type": "object",
                "properties": {
                    "keyword": {"type": "string"},
                    "count": {"type": "integer", "default": 10}
                },
                "required": ["keyword"]
            }
        },
        {
            "name": "kosis_get_indicators",
            "description": "KOSIS 주요지표를 조회합니다.",
            "input_schema": {
                "type": "object",
                "properties": {
                    "indicator_id": {"type": "string"},
                    "start_prd_de": {"type": "string"},
                    "end_prd_de": {"type": "string"}
                }
            }
        }
    ]
