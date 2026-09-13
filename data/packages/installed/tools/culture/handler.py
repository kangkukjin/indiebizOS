"""공연·전시: KOPIS 공연·공연장과 KCISA 문화행사 조회."""
import json
import os
import sys
from common.response_formatter import normalize_api_display as _normalize

CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
if CURRENT_DIR not in sys.path:
    sys.path.insert(0, CURRENT_DIR)


def _norm_date(v) -> str:
    """'2026.08.01' / '20260801' / '2026-08-01' → 'YYYY-MM-DD'. 못 알아보면 빈 문자열.
    ★칸 규약 F1(ibl.md, 2026-08-16 상상훈련): 기간은 start_date/end_date 로 병기 —
    공연(prfpdfrom/prfpdto)과 전시(startDate/endDate)가 같은 개념을 다른 이름으로 내
    union 이 의미 정합을 잃던 것(15건 21열 패딩)의 해소. native 원명은 그대로 둔다(병기)."""
    s = str(v or "").strip().replace(".", "").replace("-", "").replace("/", "")
    if len(s) == 8 and s.isdigit():
        return f"{s[:4]}-{s[4:6]}-{s[6:]}"
    return ""


def _attach_period(items, from_key: str, to_key: str):
    """items 행에 start_date/end_date 칸 병기 (원명 보존·비파괴)."""
    for it in items or []:
        if not isinstance(it, dict):
            continue
        sd = _norm_date(it.get(from_key))
        ed = _norm_date(it.get(to_key))
        if sd and "start_date" not in it:
            it["start_date"] = sd
        if ed and "end_date" not in it:
            it["end_date"] = ed


def _perf_search(ti: dict):
    """[sense:performance]{op:search} — KOPIS 공연 검색."""
    from tool_kopis import get_performances, search_by_keyword
    date_from = ti.get("date_from")
    date_to = ti.get("date_to")
    if bool(date_from) != bool(date_to):
        return {"success": False,
                "error": "date_from과 date_to는 날짜 범위의 양 끝이므로 함께 입력해야 합니다."}
    common = {
        "keyword": ti.get("query") or ti.get("keyword"),  # query 우선(sense 검색 관례), keyword 별칭
        "rows": ti.get("rows", 20),
        "cpage": ti.get("page", 1),  # 스키마가 선언한 page — 종전엔 여기서 조용히 버려졌다
    }
    if date_from:
        result = get_performances(
            stdate=date_from,
            eddate=date_to,
            shcate=ti.get("genre"),
            signgucode=ti.get("region"),
            prfstate=ti.get("status", "공연중"),
            **common,
        )
    else:
        result = search_by_keyword(
            genre=ti.get("genre"),
            region=ti.get("region"),
            status=ti.get("status", "공연중"),
            days=ti.get("days", 90),
            **common,
        )
    # 단일 통화 — native data 목록을 items로 노출.
    if isinstance(result, dict) and isinstance(result.get("data"), list):
        result["items"] = result.pop("data")  # 단일 통화: native dict 직접(records 손실변환 은퇴)
        _attach_period(result["items"], "prfpdfrom", "prfpdto")   # 칸 규약 F1
        # 칸 규약 1(title 병기, F1-title 4회차): prfnm 원명 보존 + title 추가 — 전시(title)와
        # union 후 dedup{by:"title"} 이 서게(4회차 W7 에서 같은 공연이 교차 중복돼도 못 접었다).
        for _it in result["items"]:
            if isinstance(_it, dict) and _it.get("prfnm") and "title" not in _it:
                _it["title"] = _it["prfnm"]
    return result


def _as_items(result, key: str):
    """native 목록 키를 단일 통화 items 로 승격 (search 가 하던 것과 같은 한 줄).

    2026-08-05 감사 ⑤: op 단위 fixture 를 붙이자 `returns: items` 액션인데 venue/
    genres/regions/recommended 만 통화를 안 달고 있던 것이 드러났다 — 액션 fixture 가
    op 하나(search)만 돌던 탓에 몇 달간 아무도 안 봤다.
    """
    if isinstance(result, dict) and isinstance(result.get(key), list):
        result["items"] = result.pop(key)
    return result


def _perf_venue(ti: dict):
    """[sense:performance]{op:venue} — KOPIS 공연장."""
    from tool_kopis import get_facilities
    return _as_items(get_facilities(
        facility_name=ti.get("query") or ti.get("keyword"),  # query 우선, keyword 별칭
        facility_id=ti.get("facility_id"),
        signgucode=ti.get("region"),
        rows=ti.get("rows", 20),
        cpage=ti.get("page", 1),
    ), "data")


def _perf_genres(ti: dict):
    """[sense:performance]{op:genres} — KOPIS 장르 코드."""
    from tool_kopis import get_genre_list
    return _as_items(get_genre_list(), "genres")


def _perf_regions(ti: dict):
    """[sense:performance]{op:regions} — KOPIS 지역 코드."""
    from tool_kopis import get_region_list
    return _as_items(get_region_list(), "regions")

_OP_DISPATCHERS = {"performance_op": {"search": _perf_search, "venue": _perf_venue,
                                       "genres": _perf_genres, "regions": _perf_regions}}
_OP_DEFAULTS = {"performance_op": "search"}


def execute(tool_input: dict, context) -> str:
    """
    Culture 패키지 도구 실행 핸들러 (ToolContext 기반 신규 시그니처).
    """
    tool_name = context.tool_name
    try:
        # === 단일 액션 op 디스패처 (2026-06-03 어휘 정리, 2026-08-05 테이블 디스패치) ===
        if tool_name in _OP_DISPATCHERS:
            op = (tool_input.get("op") or _OP_DEFAULTS[tool_name]).strip()
            fn = _OP_DISPATCHERS[tool_name].get(op)
            if fn is None:
                result = {"success": False,
                          "error": f"알 수 없는 op '{op}'. 사용 가능: {sorted(_OP_DISPATCHERS[tool_name])}"}
            else:
                result = fn(tool_input)

        # === 전시 (KCISA) — [sense:exhibit] ===
        elif tool_name == "kcisa_quick_search":
            from tool_kcisa import quick_search_culture
            result = quick_search_culture(
                keyword=tool_input.get("query") or tool_input.get("keyword"),
                rows=tool_input.get("rows", 10)
            )
            # 레코드 통화 부착(비파괴) — data 전시/행사목록을 records로.
            if isinstance(result, dict) and isinstance(result.get("data"), list):
                result["items"] = result.pop("data")  # 단일 통화: native dict 직접(records 손실변환 은퇴)
                _attach_period(result["items"], "startDate", "endDate")   # 칸 규약 F1 — 공연과 같은 칸

        else:
            return json.dumps({"success": False, "error": f"알 수 없는 도구: {tool_name}"}, ensure_ascii=False)

        return json.dumps(_normalize(result), ensure_ascii=False, indent=2)

    except ImportError as e:
        return json.dumps({"success": False, "error": f"모듈 임포트 오류: {str(e)}"}, ensure_ascii=False)
    except Exception as e:
        return json.dumps({"success": False, "error": f"도구 실행 중 오류 발생: {str(e)}"}, ensure_ascii=False)
