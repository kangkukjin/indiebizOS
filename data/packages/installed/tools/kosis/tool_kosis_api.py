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
import os
import sys
import json
import re
from typing import Optional, Dict, Any, List
from datetime import datetime

# common 유틸리티 사용
_backend_dir = os.path.join(os.path.dirname(__file__), "..", "..", "..", "..", "backend")
if _backend_dir not in sys.path:
    sys.path.insert(0, os.path.abspath(_backend_dir))

from common.api_client import api_call
from common.auth_manager import check_api_key

# 인증은 common.auth_manager의 KOSIS_API_KEY 설정을 사용한다.

# KOSIS API 엔드포인트 (api_client의 BASE_URL: "https://kosis.kr/openapi")
ENDPOINTS = {
    "statistics_list": "/statisticsList.do",
    "statistics_data": "/Param/statisticsParameterData.do",
    "statistics_info": "/statisticsInfo.do",
    "integrated_search": "/statisticsSearch.do",  # 구 /search/search.do 폐지(404) → 통합검색 엔드포인트 이전(2026-06-17 확인)
    "indicators": "/indicator/indicator.do",
    # 통계표 메타(표 이름·항목·분류 차원·수록 주기) — statisticsInfo.do 는 KOSIS 에 없는 자원(전 표 404,
    # 2026-09-15 실측). 메타의 정본은 statisticsData.do?method=getMeta&type=TBL|ITM|PRD 다.
    "statistics_meta": "/statisticsData.do",
}

def _to_table_currency(items: list) -> Optional[dict]:
    """KOSIS long-format(기간×분류×값) → 표준 table 통화로 피벗.
    period=x축(첫 열), (지표명 + 분류 c1/c2/c3)=각 시리즈 열. value=셀.
    → [sense:kosis]{...} >> [table:chart/spreadsheet] / [table:document](table 블록) 무reshape.
    다차원이라 시리즈 조합이 많을 수 있음(데이터 본연의 폭)."""
    if not items:
        return None

    def series_label(it):
        name = it.get("item_name") or it.get("indicator_name") or "값"
        parts = [name] + [it.get(k, "") for k in ("c1_name", "c2_name", "c3_name")]
        label = " · ".join(p for p in parts if p)
        unit = it.get("unit")
        return f"{label} ({unit})" if unit else label

    periods, series, cell = [], [], {}
    for it in items:
        p = str(it.get("period", ""))
        if not p:
            continue
        s = series_label(it)
        if p not in periods:
            periods.append(p)
        if s not in series:
            series.append(s)
        v = it.get("value", "")
        try:
            v = float(v)
        except (ValueError, TypeError):
            pass
        cell[(p, s)] = v

    if not periods or not series:
        return None
    periods.sort()
    columns = ["기간"] + series
    rows = [[p] + [cell.get((p, s)) for s in series] for p in periods]
    return {"columns": columns, "rows": rows}


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


def _make_request(endpoint_key: str, params: Dict[str, Any]) -> Dict[str, Any]:
    """API 요청 공통 함수 - common.api_client 사용"""
    try:
        key_ok, key_error = check_api_key("kosis")
        if not key_ok:
            return {"success": False, "error": key_error}
        endpoint = ENDPOINTS.get(endpoint_key, endpoint_key)
        result = api_call("kosis", endpoint, params=params, timeout=30)

        # api_call은 에러 시 {"error": "..."} 반환, 성공 시 파싱된 JSON 반환
        if isinstance(result, dict) and "error" in result:
            return {"success": False, "error": result["error"]}

        # 문자열 응답인 경우 (JSONP 등) 추가 파싱 시도
        if isinstance(result, str):
            text = result
            if text.startswith("(") and text.endswith(")"):
                text = text[1:-1]
            result = json.loads(text)

        if isinstance(result, dict) and (result.get("err") or result.get("error")):
            failure = {"success": False, "error": result.get("errMsg") or result.get("error") or "KOSIS 오류",
                       "error_code": result.get("err")}
            if endpoint_key == "statistics_data" and "objl" in str(failure["error"]).lower():
                failure["classification_request"] = {k: params[k] for k in ("objL1", "objL2", "objL3") if k in params}
                failure["hint"] = "통계표의 분류 차원과 코드를 확인하세요. 미지정 차원은 생략되고 명시한 ALL은 유지됩니다."
                failure["error"] += " " + failure["hint"]
            return failure
        if endpoint_key != "statistics_info" and (
                not isinstance(result, list) or any(not isinstance(row, dict) for row in result)):
            return {"success": False, "error": "KOSIS 응답이 레코드 배열이 아닙니다."}
        return {"success": True, "data": result,
                **({"items": [], "count": 0} if result == [] else {})}
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
        "vwCd": vw_cd,
        "format": "json",
        "jsonVD": "Y"
    }

    if keyword:
        params["searchNm"] = keyword

    if parent_list_id:
        params["parentListId"] = parent_list_id

    result = _make_request("statistics_list", params)

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
            # 단일 통화 items(records-관습 카드 shape) — 통계표 목록 >> 파이프. 실제 수치는 get_statistics_data(table).
            result["items"] = [{
                **it,
                "title": it.get("tbl_name") or it.get("stat_name") or it.get("list_name") or "",
                "meta": " · ".join(x for x in [it.get("org_name"), it.get("tbl_id")] if x),
                "summary": it.get("stat_name", "") if it.get("stat_name") != it.get("tbl_name") else "",
                "url": "",
            } for it in items]

    return result


def _obj_level_params(obj_l1, obj_l2, obj_l3, obj_levels):
    """objL1..objLN 요청 인자 — 명시한 값만 싣는다(없는 차원은 생략, 명시한 ALL 은 유지)."""
    levels = {1: obj_l1}
    if obj_l2:
        levels[2] = obj_l2
    if obj_l3:
        levels[3] = obj_l3
    for n, v in (obj_levels or {}).items():
        try:
            n = int(n)
        except (TypeError, ValueError):
            continue
        if v and 1 <= n <= 8:
            levels[n] = v
    return {f"objL{n}": v for n, v in sorted(levels.items()) if v}


def _dimension_ids_from_meta(meta: Dict[str, Any]) -> List[str]:
    """표 메타의 분류 차원(objL 순서) ID 목록 — 항목(ITEM)은 차원이 아니다."""
    return [c["obj_id"] for c in (meta.get("classifications") or []) if c.get("obj_id")]


def get_statistics_data(
    org_id: str,
    tbl_id: str,
    itm_id: str = "ALL",
    obj_l1: str = "ALL",
    obj_l2: Optional[str] = None,
    obj_l3: Optional[str] = None,
    prd_se: str = "Y",
    start_prd_de: Optional[str] = None,
    end_prd_de: Optional[str] = None,
    obj_levels: Optional[Dict[int, str]] = None,
) -> Dict[str, Any]:
    """
    KOSIS 통계자료(데이터) 조회

    Args:
        org_id: 기관 ID
        tbl_id: 통계표 ID
        itm_id: 항목 ID (기본: ALL)
        obj_l1: 분류1 ID (기본 ALL)
        obj_l2~l3: 추가 분류 ID (기본 생략, 명시한 ALL은 전체 분류로 전달)
        prd_se: 수록주기 (Y/H/Q/M/D)
        start_prd_de: 시작 시점
        end_prd_de: 종료 시점
        obj_levels: {4: "ALL", ...} — 분류4 이상(KOSIS 는 objL8 까지)

    분류 차원 자동 보충(2026-09-15): 요청이 표의 차원 수보다 적으면 KOSIS 는
    "필수요청변수값이 누락되었습니다. (objL)" 를 낸다. 차원 수는 표 메타(getMeta ITM)가
    정본이라, 그 오류를 받으면 메타에서 차원을 읽어 미지정 차원을 ALL 로 채우고 **한 번**
    다시 묻는다(호출자가 표마다 차원 수를 외울 필요가 없다 — 세계의 명사는 데이터에서).
    보충한 차원은 응답 `classification_filled` 로 정직하게 신고한다.

    Returns:
        통계 데이터
    """
    # 기본 시점 설정 (최근 5년)
    current_year = datetime.now().year
    if not end_prd_de:
        end_prd_de = str(current_year)
    if not start_prd_de:
        start_prd_de = str(current_year - 4)

    base_params = {
        "method": "getList",
        "orgId": org_id,
        "tblId": tbl_id,
        "itmId": itm_id,
        "prdSe": prd_se,
        "startPrdDe": start_prd_de,
        "endPrdDe": end_prd_de,
        "format": "json",
        "jsonVD": "Y"
    }
    requested = _obj_level_params(obj_l1, obj_l2, obj_l3, obj_levels)
    result = _make_request("statistics_data", {**base_params, **requested})

    filled = None
    if not result.get("success") and "objl" in str(result.get("error", "")).lower():
        # 차원 수 부족 — 메타의 차원 목록으로 빈 자리를 ALL 로 채워 한 번 재시도.
        meta = get_table_meta(org_id, tbl_id)
        dims = _dimension_ids_from_meta(meta.get("data") or {}) if meta.get("success") else []
        if dims and len(dims) > len(requested):
            merged = dict(requested)
            for n in range(1, len(dims) + 1):
                merged.setdefault(f"objL{n}", "ALL")
            retry = _make_request("statistics_data", {**base_params, **merged})
            if retry.get("success"):
                result = retry
                filled = {k: "ALL" for k in merged if k not in requested}
                requested = merged
            else:
                retry["classification_request"] = merged
                retry["dimensions"] = [{"obj_id": c["obj_id"], "name": c.get("name"), "level": c.get("level")}
                                       for c in (meta["data"].get("classifications") or [])]
                return retry
        elif meta.get("success"):
            result["dimensions"] = [{"obj_id": c["obj_id"], "name": c.get("name"), "level": c.get("level")}
                                    for c in (meta["data"].get("classifications") or [])]

    if result["success"] and result.get("data"):
        data = result["data"]
        # 에러 응답 체크
        if isinstance(data, dict) and data.get("err"):
            result["success"] = False
            result["error"] = data.get("errMsg", "알 수 없는 오류")
            result["data"] = None
            result["error_code"] = data["err"]
            if "objl" in str(result["error"]).lower():
                result["classification_request"] = requested
                result["hint"] = ("분류 코드를 바꾸기 전에 통계표의 차원과 코드를 확인하세요(info: true). "
                                  "같은 요청을 반복하지 마세요.")
                result["error"] += " " + result["hint"]
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
            # 단일 통화 items(행 dict) — 기간×시리즈 피벗을 행 dict로(소비자가 table 재구성). raw long-format은 data에 잔류.
            _tbl = _to_table_currency(items)
            result["items"] = ([dict(zip(_tbl["columns"], r)) for r in _tbl["rows"]]
                               if _tbl and _tbl.get("rows") else items)
            result["query"] = {
                "org_id": org_id,
                "tbl_id": tbl_id,
                "period": f"{start_prd_de} ~ {end_prd_de}",
                "classification": requested,
            }
            if filled:
                result["classification_filled"] = filled
                result["note"] = ("표의 분류 차원이 요청보다 많아 미지정 차원을 ALL 로 보충했습니다: "
                                  + ", ".join(sorted(filled)) + ". 좁히려면 info: true 로 코드를 확인하세요.")

    return result


def get_table_meta(org_id: str, tbl_id: str) -> Dict[str, Any]:
    """통계표 메타 — 표 이름(TBL)·항목과 분류 차원·코드(ITM)·수록 주기(PRD) 세 조회의 합성.

    data = {org_id, tbl_id, tbl_name, tbl_name_eng, periods:[{prd_se,start,end}],
            items:[{id,name,unit}], classifications:[{obj_id,name,level,codes:[{id,name}]}]}
    classifications 의 순서가 곧 objL1..objLN 이다(OBJ_ID_SN).
    """
    common = {"method": "getMeta", "orgId": org_id, "tblId": tbl_id, "format": "json", "jsonVD": "Y"}
    tbl = _make_request("statistics_meta", {**common, "type": "TBL"})
    if not tbl.get("success"):
        return tbl
    itm = _make_request("statistics_meta", {**common, "type": "ITM"})
    if not itm.get("success"):
        return itm
    prd = _make_request("statistics_meta", {**common, "type": "PRD"})

    head = (tbl.get("data") or [{}])[0] if isinstance(tbl.get("data"), list) else {}
    items, dims = [], {}
    for row in itm.get("data") or []:
        obj_id = row.get("OBJ_ID", "")
        if obj_id == "ITEM":
            items.append({"id": row.get("ITM_ID", ""), "name": row.get("ITM_NM", ""),
                          "unit": row.get("UNIT_NM", "")})
            continue
        d = dims.setdefault(obj_id, {"obj_id": obj_id, "name": row.get("OBJ_NM", ""),
                                     "order": row.get("OBJ_ID_SN") or "", "codes": []})
        d["codes"].append({"id": row.get("ITM_ID", ""), "name": row.get("ITM_NM", "")})

    def _sn(d):
        try:
            return int(d["order"])
        except (TypeError, ValueError):
            return 10 ** 6
    classifications = sorted(dims.values(), key=_sn)
    for i, c in enumerate(classifications, 1):
        c["level"] = f"objL{i}"
        c["n_codes"] = len(c["codes"])
        c.pop("order", None)

    periods = [{"prd_se": r.get("PRD_SE", ""), "start": r.get("STRT_PRD_DE", ""), "end": r.get("END_PRD_DE", "")}
               for r in (prd.get("data") or []) if isinstance(r, dict)] if prd.get("success") else []
    return {"success": True, "data": {
        "org_id": org_id, "tbl_id": tbl_id,
        "tbl_name": head.get("TBL_NM", ""), "tbl_name_eng": head.get("TBL_NM_ENG", ""),
        "periods": periods, "items": items, "classifications": classifications,
    }}


def get_statistics_info(
    org_id: str,
    tbl_id: str
) -> Dict[str, Any]:
    """
    통계표 상세 정보(메타데이터) 조회 — 항목·분류 차원(코드 포함)·수록 주기.

    ★2026-09-15: 종전 엔드포인트 statisticsInfo.do 는 KOSIS 에 존재하지 않아 모든 표에서
    404 였다(action_health 실측 — info: true 호출 전량 실패). 정본 메타는
    statisticsData.do?method=getMeta 라 get_table_meta 의 합성으로 대체.

    Returns:
        data = 표 메타(get_table_meta), items = 차원 한 줄씩(level·obj_id·name·n_codes·codes)
        + 항목(level "ITEM") 한 줄 — 데이터 조회의 obj_lN / itm_id 자리에 무엇을 줄지 이 표로 안다.
    """
    result = get_table_meta(org_id, tbl_id)
    if not result.get("success"):
        return result
    meta = result["data"]
    rows = [{"level": c["level"], "obj_id": c["obj_id"], "name": c["name"],
             "n_codes": c["n_codes"], "codes": c["codes"],
             "title": f"{c['level']} · {c['name']}", "summary": ", ".join(x["name"] for x in c["codes"][:8])
             + (" …" if len(c["codes"]) > 8 else "")}
            for c in meta["classifications"]]
    rows.append({"level": "ITEM", "obj_id": "ITEM", "name": "항목", "n_codes": len(meta["items"]),
                 "codes": [{"id": i["id"], "name": i["name"]} for i in meta["items"]],
                 "title": "ITEM · 항목",
                 "summary": ", ".join(f"{i['name']}({i['unit']})" if i.get("unit") else i["name"]
                                      for i in meta["items"][:8]) + (" …" if len(meta["items"]) > 8 else "")})
    result["items"] = rows
    result["count"] = len(rows)
    dims_txt = (": " + " × ".join(c["name"] for c in meta["classifications"])) if meta["classifications"] else ""
    prd_txt = ("/".join(p["prd_se"] for p in meta["periods"]) or "미상") if meta["periods"] else "미상"
    result["message"] = (f"{meta['tbl_name']} — 분류 차원 {len(meta['classifications'])}개{dims_txt}, "
                         f"항목 {len(meta['items'])}개, 주기 {prd_txt}")
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
    if type(count) is bool or not re.fullmatch(r"\d+", str(count).strip()):
        return {"success": False, "error": "limit은 0 이상의 정수여야 합니다."}
    count = int(count)
    if count == 0:
        return {"success": True, "items": [], "data": [], "count": 0}
    params = {
        "method": "getList",
        "searchNm": keyword,
        "resultCount": min(count, 100),  # clamp-ok: KOSIS API 스펙 상한(resultCount 100)
        "format": "json",
        "jsonVD": "Y"
    }

    result = _make_request("integrated_search", params)

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
            # 단일 통화 items(records-관습 카드 shape) — 통합검색 결과 목록 >> 파이프.
            result["items"] = [{
                **it,
                "title": it.get("tbl_name") or it.get("stat_name") or "",
                "meta": " · ".join(x for x in [it.get("org_name"), it.get("tbl_id"), it.get("type")] if x),
                "summary": it.get("description", ""),
                "url": "",
            } for it in items]

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
        "format": "json",
        "jsonVD": "Y"
    }

    if indicator_id:
        params["indicatorId"] = indicator_id
        if start_prd_de:
            params["startPrdDe"] = start_prd_de
        if end_prd_de:
            params["endPrdDe"] = end_prd_de

    result = _make_request("indicators", params)

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
            # 단일 통화 items(행 dict) — 기간×시리즈 피벗을 행 dict로(소비자가 table 재구성). raw long-format은 data에 잔류.
            _tbl = _to_table_currency(items)
            result["items"] = ([dict(zip(_tbl["columns"], r)) for r in _tbl["rows"]]
                               if _tbl and _tbl.get("rows") else items)

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
                    "obj_l2": {"type": "string", "description": "미지정 시 생략, ALL 명시 시 분류2 전체"},
                    "obj_l3": {"type": "string", "description": "미지정 시 생략, ALL 명시 시 분류3 전체"},
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
