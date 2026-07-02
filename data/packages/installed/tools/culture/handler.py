"""
Culture 패키지 핸들러 - 공연, 도서, 전시, 고전 등 문화 정보 도구 모음

2026-06-03 culture 어휘 정리: 옛 IBL 액션들을 단일 액션 op 분기로 통합.
- [sense:performance]{op} → performance_op (search/venue/genres/regions, KOPIS)
- [sense:book]{op}        → book_op        (search/recommended/codes, 도서관정보나루)
- [sense:classic]{op}     → classic_op     (western=Gutenberg/korean=한국고전DB)
- [sense:exhibit]         → kcisa_quick_search (KCISA, 유지)
2026-07-03 미소유 도구 감사 후속: tool.json에 없는 kopis_*/library_*/kcisa_* 레거시 분기 제거.
"""
import json
import os
import sys
import html
import re

# 현재 디렉토리를 path에 추가
CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
if CURRENT_DIR not in sys.path:
    sys.path.insert(0, CURRENT_DIR)

_DATE8 = re.compile(r'^\d{8}$')


def _normalize(obj):
    """문화 API 응답 정규화 (서버에서 한 번만): HTML 엔티티(&#39; 등) 디코드 +
    날짜 필드의 YYYYMMDD → YYYY.MM.DD 통일. 호출자(앱/LLM)가 매번 재가공하지 않도록."""
    if isinstance(obj, dict):
        out = {}
        for k, v in obj.items():
            if isinstance(v, str):
                s = html.unescape(v)
                if 'date' in k.lower() and _DATE8.match(s):
                    s = f"{s[:4]}.{s[4:6]}.{s[6:8]}"
                out[k] = s
            else:
                out[k] = _normalize(v)
        return out
    if isinstance(obj, list):
        return [_normalize(x) for x in obj]
    return obj


# ── 단일 액션 op 디스패처 ───────────────────────────────

def _performance_op(ti: dict):
    """[sense:performance]{op} — KOPIS 공연·공연장·필터코드."""
    op = (ti.get("op") or _OP_DEFAULTS["performance_op"]).strip()
    if op == "search":
        from tool_kopis import search_by_keyword
        result = search_by_keyword(
            keyword=ti.get("query") or ti.get("keyword"),  # query 우선(sense 검색 관례), keyword 별칭
            genre=ti.get("genre"),
            region=ti.get("region"),
            status=ti.get("status", "공연중"),
            days=ti.get("days", 90),
        )
        # 단일 통화 — native data 목록을 items로 노출.
        if isinstance(result, dict) and isinstance(result.get("data"), list):
            result["items"] = result.pop("data")  # 단일 통화: native dict 직접(records 손실변환 은퇴)
        return result
    if op == "venue":
        from tool_kopis import get_facilities
        return get_facilities(
            facility_name=ti.get("query") or ti.get("keyword"),  # query 우선, keyword 별칭
            facility_id=ti.get("facility_id"),
            signgucode=ti.get("region"),
            rows=ti.get("rows", 20),
            cpage=ti.get("page", 1),
        )
    if op == "genres":
        from tool_kopis import get_genre_list
        return get_genre_list()
    if op == "regions":
        from tool_kopis import get_region_list
        return get_region_list()
    return {"success": False, "error": f"알 수 없는 op '{op}'. 사용 가능: {sorted(_OP_DISPATCHERS['performance_op'])}"}


def _book_op(ti: dict):
    """[sense:book]{op} — 도서관정보나루 도서·추천·코드."""
    op = (ti.get("op") or _OP_DEFAULTS["book_op"]).strip()
    if op == "search":
        isbn = ti.get("isbn") or ti.get("isbn13")
        title = ti.get("title")
        author = ti.get("author")
        publisher = ti.get("publisher")
        keyword = ti.get("keyword") or ti.get("query")
        detail = ti.get("detail", False)
        rows = ti.get("rows", 10)
        result = None
        if isbn:
            if detail:
                from tool_library import get_book_detail
                return get_book_detail(isbn13=isbn, loan_info=ti.get("loan_info", True))
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
    if op == "recommended":
        from tool_library import get_recommended_books
        return get_recommended_books(isbn13=ti.get("isbn13") or ti.get("isbn"), rec_type=ti.get("rec_type", "mania"))
    if op == "codes":
        ct = (ti.get("code_type") or "kdc").strip().lower()
        if ct == "kdc":
            from tool_library import get_kdc_list
            return get_kdc_list()
        if ct in ("region", "regions"):
            from tool_library import get_region_list
            return get_region_list()
        return {"success": False, "error": f"code_type는 kdc 또는 region이어야 합니다. (받음: {ct})"}
    return {"success": False, "error": f"알 수 없는 op '{op}'. 사용 가능: {sorted(_OP_DISPATCHERS['book_op'])}"}


def _classic_op(ti: dict):
    """[sense:classic]{op} — 고전 원문 (western=Gutenberg, korean=한국고전DB)."""
    op = (ti.get("op") or _OP_DEFAULTS["classic_op"]).strip()
    if op == "western":
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
    if op == "korean":
        from tool_korean_classics import search_korean_classics
        result = search_korean_classics(query=ti.get("query"), rows=ti.get("rows", 10))
        if isinstance(result, dict) and isinstance(result.get("results"), list):
            result["items"] = result.pop("results")  # 단일 통화: native dict 직접(records 손실변환 은퇴)
        return result
    return {"success": False, "error": f"알 수 없는 op '{op}'. 사용 가능: {sorted(_OP_DISPATCHERS['classic_op'])}"}


# 2026-06-03 dispatcher 표준화 — 단일 액션 op 키 메타데이터.
# 값 None — 분기 로직은 위 함수 안에 유지. --check 가 이 dict 키로 src.ops.values 와 정확 비교.
_OP_DISPATCHERS = {
    "performance_op": {"search": None, "venue": None, "genres": None, "regions": None},
    "book_op": {"search": None, "recommended": None, "codes": None},
    "classic_op": {"western": None, "korean": None},
}
_OP_DEFAULTS = {"performance_op": "search", "book_op": "search", "classic_op": "western"}


def execute(tool_input: dict, context) -> str:
    """
    Culture 패키지 도구 실행 핸들러 (ToolContext 기반 신규 시그니처).
    """
    tool_name = context.tool_name
    try:
        # === 단일 액션 op 디스패처 (2026-06-03 어휘 정리) ===
        if tool_name == "performance_op":
            result = _performance_op(tool_input)

        elif tool_name == "book_op":
            result = _book_op(tool_input)

        elif tool_name == "classic_op":
            result = _classic_op(tool_input)

        # === 전시 (KCISA) — [sense:exhibit] ===
        elif tool_name == "kcisa_quick_search":
            from tool_kcisa import quick_search_culture
            result = quick_search_culture(
                keyword=tool_input.get("keyword"),
                rows=tool_input.get("rows", 10)
            )
            # 레코드 통화 부착(비파괴) — data 전시/행사목록을 records로.
            if isinstance(result, dict) and isinstance(result.get("data"), list):
                result["items"] = result.pop("data")  # 단일 통화: native dict 직접(records 손실변환 은퇴)

        else:
            return json.dumps({"error": f"알 수 없는 도구: {tool_name}"}, ensure_ascii=False)

        return json.dumps(_normalize(result), ensure_ascii=False, indent=2)

    except ImportError as e:
        return json.dumps({"error": f"모듈 임포트 오류: {str(e)}"}, ensure_ascii=False)
    except Exception as e:
        return json.dumps({"error": f"도구 실행 중 오류 발생: {str(e)}"}, ensure_ascii=False)
