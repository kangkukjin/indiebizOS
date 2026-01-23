"""
Culture 패키지 핸들러 - 공연, 도서, 전시 등 문화 정보 도구 모음
"""
import json
import os
import sys

# 현재 디렉토리를 path에 추가
CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
if CURRENT_DIR not in sys.path:
    sys.path.insert(0, CURRENT_DIR)


def execute(tool_name: str, tool_input: dict, project_path: str = ".") -> str:
    """
    Culture 패키지 도구 실행 핸들러
    """
    try:
        # KOPIS 공연 정보 도구들
        if tool_name == "kopis_search_performances":
            from tool_kopis import get_performances
            result = get_performances(
                stdate=tool_input.get("stdate"),
                eddate=tool_input.get("eddate"),
                shcate=tool_input.get("genre"),
                signgucode=tool_input.get("region"),
                prfstate=tool_input.get("status", "공연중"),
                keyword=tool_input.get("keyword"),
                rows=tool_input.get("rows", 20),
                cpage=tool_input.get("page", 1)
            )

        elif tool_name == "kopis_get_performance":
            from tool_kopis import get_performance_detail
            result = get_performance_detail(
                performance_id=tool_input.get("performance_id")
            )

        elif tool_name == "kopis_box_office":
            from tool_kopis import get_box_office
            result = get_box_office(
                ststype=tool_input.get("period", "day"),
                date=tool_input.get("date"),
                catecode=tool_input.get("genre"),
                area=tool_input.get("region")
            )

        elif tool_name == "kopis_search_facilities":
            from tool_kopis import get_facilities
            result = get_facilities(
                facility_name=tool_input.get("keyword"),
                facility_id=tool_input.get("facility_id"),
                signgucode=tool_input.get("region"),
                rows=tool_input.get("rows", 20),
                cpage=tool_input.get("page", 1)
            )

        elif tool_name == "kopis_search_festivals":
            from tool_kopis import get_festivals
            result = get_festivals(
                stdate=tool_input.get("stdate"),
                eddate=tool_input.get("eddate"),
                shcate=tool_input.get("genre"),
                signgucode=tool_input.get("region"),
                rows=tool_input.get("rows", 20),
                cpage=tool_input.get("page", 1)
            )

        elif tool_name == "kopis_quick_search":
            from tool_kopis import search_by_keyword
            result = search_by_keyword(
                keyword=tool_input.get("keyword"),
                genre=tool_input.get("genre"),
                region=tool_input.get("region"),
                status=tool_input.get("status", "공연중"),
                days=tool_input.get("days", 90)
            )

        elif tool_name == "kopis_get_genres":
            from tool_kopis import get_genre_list
            result = get_genre_list()

        elif tool_name == "kopis_get_regions":
            from tool_kopis import get_region_list
            result = get_region_list()

        # 도서관 정보나루 도서 검색 도구들
        elif tool_name == "library_search_books":
            from tool_library import search_books
            result = search_books(
                keyword=tool_input.get("keyword"),
                page=tool_input.get("page", 1),
                page_size=tool_input.get("rows", 10)
            )

        elif tool_name == "library_get_book_detail":
            from tool_library import get_book_detail
            result = get_book_detail(
                isbn13=tool_input.get("isbn13"),
                loan_info=tool_input.get("loan_info", True)
            )

        elif tool_name == "library_get_popular_books":
            from tool_library import get_popular_books
            result = get_popular_books(
                start_date=tool_input.get("start_date"),
                end_date=tool_input.get("end_date"),
                gender=tool_input.get("gender"),
                from_age=tool_input.get("from_age"),
                to_age=tool_input.get("to_age"),
                region=tool_input.get("region"),
                kdc=tool_input.get("kdc"),
                page=tool_input.get("page", 1),
                page_size=tool_input.get("rows", 10)
            )

        elif tool_name == "library_get_trending_books":
            from tool_library import get_trending_books
            result = get_trending_books(
                base_date=tool_input.get("base_date")
            )

        elif tool_name == "library_get_recommended_books":
            from tool_library import get_recommended_books
            result = get_recommended_books(
                isbn13=tool_input.get("isbn13"),
                rec_type=tool_input.get("rec_type", "mania")
            )

        elif tool_name == "library_search_libraries":
            from tool_library import search_libraries
            result = search_libraries(
                name=tool_input.get("name"),
                region=tool_input.get("region"),
                page=tool_input.get("page", 1),
                page_size=tool_input.get("rows", 10)
            )

        elif tool_name == "library_search_by_book":
            from tool_library import search_libraries_by_book
            result = search_libraries_by_book(
                isbn13=tool_input.get("isbn13"),
                region=tool_input.get("region"),
                page=tool_input.get("page", 1),
                page_size=tool_input.get("rows", 10)
            )

        elif tool_name == "library_quick_search":
            from tool_library import quick_search
            result = quick_search(
                keyword=tool_input.get("keyword"),
                rows=tool_input.get("rows", 10)
            )

        elif tool_name == "library_get_book_by_isbn":
            from tool_library import get_book_by_isbn
            result = get_book_by_isbn(
                isbn=tool_input.get("isbn")
            )

        elif tool_name == "library_get_regions":
            from tool_library import get_region_list
            result = get_region_list()

        elif tool_name == "library_get_kdc":
            from tool_library import get_kdc_list
            result = get_kdc_list()

        # KCISA 문화정보 도구들
        elif tool_name == "kcisa_search_culture":
            from tool_kcisa import search_culture_events
            result = search_culture_events(
                keyword=tool_input.get("keyword"),
                start_date=tool_input.get("start_date"),
                end_date=tool_input.get("end_date"),
                area=tool_input.get("area"),
                rows=tool_input.get("rows", 10),
                page=tool_input.get("page", 1)
            )

        elif tool_name == "kcisa_get_event_detail":
            from tool_kcisa import get_culture_event_detail
            result = get_culture_event_detail(
                seq=tool_input.get("seq")
            )

        elif tool_name == "kcisa_quick_search":
            from tool_kcisa import quick_search_culture
            result = quick_search_culture(
                keyword=tool_input.get("keyword"),
                rows=tool_input.get("rows", 10)
            )

        # 레거시 호환 (기존 tool_name 지원)
        elif tool_name == "get_performances":
            from tool_kopis import get_performances
            result = get_performances(
                stdate=tool_input.get("stdate"),
                eddate=tool_input.get("eddate"),
                shcate=tool_input.get("shcate"),
                signgucode=tool_input.get("signgucode"),
                prfstate=tool_input.get("prfstate", "02"),
                rows=tool_input.get("rows", 10),
                cpage=tool_input.get("cpage", 1)
            )

        elif tool_name == "get_performance_detail":
            from tool_kopis import get_performance_detail
            result = get_performance_detail(
                performance_id=tool_input.get("performance_id")
            )

        elif tool_name == "get_box_office":
            from tool_kopis import get_box_office
            result = get_box_office(
                ststype=tool_input.get("ststype", "week"),
                date=tool_input.get("date"),
                catecode=tool_input.get("catecode"),
                area=tool_input.get("area")
            )

        elif tool_name == "get_facilities":
            from tool_kopis import get_facilities
            result = get_facilities(
                facility_name=tool_input.get("facility_name"),
                facility_id=tool_input.get("facility_id")
            )

        else:
            return json.dumps({"error": f"알 수 없는 도구: {tool_name}"}, ensure_ascii=False)

        return json.dumps(result, ensure_ascii=False, indent=2)

    except ImportError as e:
        return json.dumps({"error": f"모듈 임포트 오류: {str(e)}"}, ensure_ascii=False)
    except Exception as e:
        return json.dumps({"error": f"도구 실행 중 오류 발생: {str(e)}"}, ensure_ascii=False)
