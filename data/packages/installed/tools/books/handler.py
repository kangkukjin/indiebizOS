"""책·고전: 도서 조회·대출 통계·추천과 고전 원문 탐색."""
import json
import os
import sys
from common.response_formatter import normalize_api_display as _normalize

CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
if CURRENT_DIR not in sys.path:
    sys.path.insert(0, CURRENT_DIR)


def _as_items(result, key: str):
    """native 목록 키를 단일 통화 items 로 승격 (search 가 하던 것과 같은 한 줄).

    2026-08-05 감사 ⑤: op 단위 fixture 를 붙이자 `returns: items` 액션인데 venue/
    genres/regions/recommended 만 통화를 안 달고 있던 것이 드러났다 — 액션 fixture 가
    op 하나(search)만 돌던 탓에 몇 달간 아무도 안 봤다.
    """
    if isinstance(result, dict) and isinstance(result.get(key), list):
        result["items"] = result.pop(key)
    return result


def _book_search(ti: dict):
    """[sense:book]{op:search} — 도서 검색 (정보나루 기본, source=nl 국립중앙도서관)."""
    isbn = ti.get("isbn") or ti.get("isbn13")
    title = ti.get("title")
    author = ti.get("author")
    publisher = ti.get("publisher")
    keyword = ti.get("query") or ti.get("keyword")
    detail = ti.get("detail", False)
    rows = ti.get("rows", 10)
    # source=nl → 국립중앙도서관 납본 소장 검색 (정보나루=공공도서관 대출 렌즈와 코퍼스가 다름
    # — 도서관들이 안 산 신간·소부수 출판은 나루엔 없어도 납본으로 여기엔 있다)
    source = str(ti.get("source") or "").strip().lower()
    # source=google → Google Books 글로벌 도서 (구 sense:search_books 흡수, 2026-08-05).
    # search op 전용 — popular/trending 등 대출 통계 op 는 정보나루 코퍼스에만 있다.
    if source in ("google", "gbooks", "구글"):
        from tool_gbooks import search_google_books
        kw = keyword or " ".join(x for x in [title, author, publisher] if x) or (isbn or "")
        return search_google_books(query=kw, max_results=ti.get("max_results") or rows,
                                   order_by=ti.get("order_by", "relevance"))
    if source in ("nl", "national", "국립", "국립중앙도서관"):
        from tool_nl import search_nl
        kw = keyword or " ".join(x for x in [title, author, publisher] if x) or (isbn or "")
        return search_nl(keyword=kw, category=ti.get("category", "도서"),
                         page=ti.get("page", 1), page_size=rows)
    result = None
    if isbn:
        if detail:
            # 드릴 풍부화(2026-08-04): 상세+이용분석+소장도서관을 한 응답에 —
            # 앱 드릴 tabs 는 단일 액션 결과를 탭별로 슬라이스한다(렌더러 계약).
            from tool_library import (get_book_detail, get_usage_analysis,
                                      search_libraries_by_book, get_region_code)
            out = get_book_detail(isbn13=isbn, loan_info=ti.get("loan_info", True))
            if not (isinstance(out, dict) and "error" in out):
                ua = get_usage_analysis(isbn)
                if isinstance(ua, dict) and "error" not in ua:
                    out["usage"] = ua
                # ★libSrchByBook 은 region 필수(regionCodeErr 실측) — 이름("충북")도 코드로 정규화
                region = get_region_code(str(ti.get("region") or "").strip())
                if region:
                    libs = search_libraries_by_book(isbn13=isbn, region=region, page_size=30)
                    if isinstance(libs, dict) and "error" not in libs:
                        out["libraries"] = libs.get("data") or []
                        out["libraries_total"] = libs.get("count")
                        if not out["libraries"]:
                            # ★실측(2026-08-04): libSrchByBook 은 실시간 연계 참여관만 반환 —
                            # 같은 책이 서울 293·세종 50인데 경기·충북 0 (지역별 편차 큼)
                            out["libraries_note"] = "이 지역에서 조회되는 소장 도서관이 없습니다 — 정보나루 실시간 연계 도서관만 잡혀 지역별 편차가 큽니다."
                if "libraries" not in out:
                    out["libraries"] = []
                    out["libraries_note"] = "지역을 선택하고 다시 열면 그 지역 소장 도서관이 표시됩니다 (정보나루 API 는 지역 필수)."
            return out
        from tool_library import get_book_by_isbn
        result = get_book_by_isbn(isbn=isbn)
    elif title or author or publisher:
        from tool_library import search_books
        result = search_books(title=title, author=author, publisher=publisher, page_size=rows)
    elif keyword:
        from tool_library import quick_search
        result = quick_search(keyword=keyword, rows=rows)
    else:
        return {"success": False, "error": "title/author/keyword/isbn 중 하나가 필요합니다."}
    # 레코드 통화 부착(비파괴) — data 목록이 있으면 records로. 앱은 data, >> 파이프는 records.
    if isinstance(result, dict) and isinstance(result.get("data"), list):
        result["items"] = result.pop("data")  # 단일 통화: native dict 직접(records 손실변환 은퇴)
    return result


def _book_popular(ti: dict):
    """[sense:book]{op:popular} — 인기 대출 도서 (loanItemSrch). 2026-08-04 노출."""
    from tool_library import get_popular_books, get_region_code
    g = ti.get("gender")
    if isinstance(g, str):
        gs = g.strip()
        g = int(gs) if gs.isdigit() else {"남": 0, "남성": 0, "여": 1, "여성": 1}.get(gs)
    fa, ta = ti.get("from_age"), ti.get("to_age")
    age = str(ti.get("age") or "").strip()
    if age and not fa:
        try:
            a = int(age.rstrip("대"))
            fa, ta = a, a + 9
        except ValueError:
            pass
    result = get_popular_books(
        start_date=ti.get("start_date"), end_date=ti.get("end_date"),
        gender=g if g in (0, 1) else None,
        from_age=fa, to_age=ta,
        region=get_region_code(str(ti.get("region") or "").strip()) or None,
        kdc=ti.get("kdc"), page=ti.get("page", 1),
        page_size=ti.get("rows", 20))
    if isinstance(result, dict) and isinstance(result.get("data"), list):
        result["items"] = result.pop("data")  # 단일 통화 items (search 와 동형)
    # ★실측(2026-08-04): region 집계는 일부 지역만 실림(서울·부산 5000 vs 경기·충북·대전 0)
    # — libSrchByBook 과 같은 지역 커버리지 공백 부류. 빈 결과를 버그로 오독하지 않게 안내.
    if (isinstance(result, dict)
            and not result.get("items") and str(ti.get("region") or "").strip()):
        result["message"] = ("이 지역 집계가 비어 있습니다 — 정보나루 지역 필터는 "
                             "일부 지역(서울·부산 등)만 집계됩니다. '전국'으로 조회해 보세요.")
    return result


def _book_trending(ti: dict):
    """[sense:book]{op:trending} — 급상승 대출 도서 (hotTrend). 2026-08-04 노출."""
    from tool_library import get_trending_books
    result = get_trending_books(base_date=ti.get("base_date") or ti.get("date"))
    if isinstance(result, dict) and isinstance(result.get("data"), list):
        result["items"] = result.pop("data")  # 단일 통화 items (search 와 동형)
    return result


def _book_recommended(ti: dict):
    """[sense:book]{op:recommended} — ISBN 기반 추천 도서."""
    from tool_library import get_recommended_books
    return _as_items(get_recommended_books(
        isbn13=ti.get("isbn13") or ti.get("isbn"),
        rec_type=ti.get("rec_type", "mania")), "data")


def _book_codes(ti: dict):
    """[sense:book]{op:codes} — KDC/지역 코드 목록."""
    ct = (ti.get("code_type") or "kdc").strip().lower()
    if ct == "kdc":
        from tool_library import get_kdc_list
        return get_kdc_list()
    if ct in ("region", "regions"):
        from tool_library import get_region_list
        return get_region_list()
    return {"success": False, "error": f"code_type는 kdc 또는 region이어야 합니다. (받음: {ct})"}


def _classic_western(ti: dict):
    """[sense:classic]{op:western} — Gutenberg 서양 고전."""
    from tool_gutenberg import search_gutenberg
    result = search_gutenberg(
        query=ti.get("query"),
        author_year_start=ti.get("author_year_start"),
        author_year_end=ti.get("author_year_end"),
        topic=ti.get("topic"),
        languages=ti.get("languages", "en"),
    )
    # 레코드 통화 부착(비파괴) — results 고전목록을 records로.
    if isinstance(result, dict) and isinstance(result.get("results"), list):
        result["items"] = result.pop("results")  # 단일 통화: native dict 직접(records 손실변환 은퇴)
    return result


def _classic_korean(ti: dict):
    """[sense:classic]{op:korean} — 한국고전종합DB."""
    from tool_korean_classics import search_korean_classics
    result = search_korean_classics(query=ti.get("query"), rows=ti.get("rows", 10))
    if isinstance(result, dict) and isinstance(result.get("results"), list):
        result["items"] = result.pop("results")  # 단일 통화: native dict 직접(records 손실변환 은퇴)
    return result

_OP_DISPATCHERS = {
    "book_op": {"search": _book_search, "popular": _book_popular, "trending": _book_trending,
                "recommended": _book_recommended, "codes": _book_codes},
    "classic_op": {"western": _classic_western, "korean": _classic_korean},
}
_OP_DEFAULTS = {"book_op": "search", "classic_op": "western"}


def execute(tool_input: dict, context) -> str:
    """
    책·고전 패키지 도구 실행 핸들러 (ToolContext 기반 신규 시그니처).
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

        else:
            return json.dumps({"success": False, "error": f"알 수 없는 도구: {tool_name}"}, ensure_ascii=False)

        return json.dumps(_normalize(result), ensure_ascii=False, indent=2)

    except ImportError as e:
        return json.dumps({"success": False, "error": f"모듈 임포트 오류: {str(e)}"}, ensure_ascii=False)
    except Exception as e:
        return json.dumps({"success": False, "error": f"도구 실행 중 오류 발생: {str(e)}"}, ensure_ascii=False)
