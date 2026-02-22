"""
api_transforms_legacy.py - 레거시 Python 응답 변환 함수

api_registry.yaml의 `transform:` 키워드용 하드코딩된 변환 함수들.
이제 모든 도구가 `response:` 블록(api_transforms.py)으로 전환되어
이 파일의 함수들은 사용되지 않습니다.

하위 호환을 위해 보존하며, 향후 제거 예정입니다.

사용법 (더 이상 호출되지 않음):
    from api_transforms_legacy import register_legacy_transforms
    register_legacy_transforms(transform_registry)
"""

from datetime import datetime
from typing import Any, Dict, List


# === 레거시 변환 함수들 ===

def _transform_naver_shopping(data: Any, tool_input: dict) -> dict:
    """네이버 쇼핑 응답 변환 (레거시)"""
    if isinstance(data, dict) and "error" in data:
        return data
    from common.html_utils import clean_html
    raw_items = data.get("items", [])
    items = []
    for item in raw_items:
        items.append({
            "name": clean_html(item.get("title", "")),
            "price": item.get("lprice", "0"),
            "mall": item.get("mallName", "네이버"),
            "link": item.get("link", ""),
            "image": item.get("image", ""),
            "category": f"{item.get('category1', '')} > {item.get('category2', '')}",
            "site": "naver"
        })
    return {"total": data.get("total", 0), "items": items}


def _transform_kakao_restaurants(data: Any, tool_input: dict) -> dict:
    """카카오 맛집 검색 응답 변환 (레거시)"""
    if isinstance(data, dict) and "error" in data:
        return data
    documents = data.get("documents", [])
    restaurants = []
    for doc in documents:
        restaurants.append({
            "name": doc.get("place_name", ""),
            "category": doc.get("category_name", ""),
            "address": doc.get("road_address_name") or doc.get("address_name", ""),
            "phone": doc.get("phone", ""),
            "url": doc.get("place_url", ""),
            "distance": doc.get("distance", ""),
            "x": doc.get("x", ""),
            "y": doc.get("y", ""),
        })
    query = tool_input.get("query", "")
    return {
        "total": data.get("meta", {}).get("total_count", 0),
        "restaurants": restaurants,
        "message": f"'{query}' 검색 결과 {len(restaurants)}개의 맛집을 찾았습니다."
    }


def _transform_ninjas_data(data: Any, tool_input: dict) -> dict:
    """API Ninjas 응답 변환 (레거시)"""
    endpoint = tool_input.get("endpoint", "")
    if isinstance(data, list):
        return {"endpoint": endpoint, "count": len(data), "results": data}
    return {"endpoint": endpoint, "result": data}


def _transform_kosis_list(data: Any, tool_input: dict) -> dict:
    """KOSIS 통계목록 응답 변환 (레거시)"""
    if isinstance(data, dict) and "error" in data:
        return data
    if isinstance(data, list):
        return {"success": True, "count": len(data), "data": data}
    return {"success": True, "data": data}


def _transform_kstartup(data: Any, tool_input: dict) -> dict:
    """K-Startup 공고 응답 변환 (레거시)"""
    if isinstance(data, dict) and "error" in data:
        return data
    items = data.get("data", [])
    if isinstance(items, list):
        return {"success": True, "count": len(items), "items": items}
    return {"success": True, "data": data}


def _transform_fmp_profile(data: Any, tool_input: dict) -> dict:
    """FMP 기업 프로필 응답 변환 (레거시)"""
    if isinstance(data, dict) and "error" in data:
        return data
    if isinstance(data, list) and len(data) > 0:
        c = data[0]
        return {
            "success": True,
            "data": {
                "symbol": c.get("symbol"),
                "company_name": c.get("companyName"),
                "price": c.get("price"),
                "market_cap": c.get("mktCap"),
                "beta": c.get("beta"),
                "volume_avg": c.get("volAvg"),
                "last_dividend": c.get("lastDiv"),
                "range_52week": c.get("range"),
                "changes": c.get("changes"),
                "currency": c.get("currency"),
                "exchange": c.get("exchangeShortName"),
                "industry": c.get("industry"),
                "sector": c.get("sector"),
                "country": c.get("country"),
                "employees": c.get("fullTimeEmployees"),
                "ceo": c.get("ceo"),
                "website": c.get("website"),
                "description": c.get("description"),
                "ipo_date": c.get("ipoDate"),
            }
        }
    return {"success": False, "error": "기업 정보를 찾을 수 없습니다."}


def _transform_finnhub_news(data: Any, tool_input: dict) -> dict:
    """Finnhub 뉴스 응답 변환 (레거시)"""
    if isinstance(data, dict) and "error" in data:
        return data
    if not isinstance(data, list):
        return {"success": True, "count": 0, "data": []}
    items = []
    for item in data[:20]:
        dt = item.get("datetime", 0)
        try:
            dt_str = datetime.fromtimestamp(dt).strftime("%Y-%m-%d %H:%M")
        except (ValueError, OSError):
            dt_str = ""
        items.append({
            "headline": item.get("headline"),
            "summary": item.get("summary", ""),
            "source": item.get("source"),
            "url": item.get("url"),
            "datetime": dt_str,
            "category": item.get("category"),
            "related": item.get("related"),
        })
    return {"success": True, "count": len(items), "data": items}


def _transform_finnhub_earnings(data: Any, tool_input: dict) -> dict:
    """Finnhub 실적 캘린더 응답 변환 (레거시)"""
    if isinstance(data, dict) and "error" in data:
        return data
    earnings = []
    if isinstance(data, dict):
        earnings = data.get("earningsCalendar", [])
    if not earnings:
        return {"success": True, "count": 0, "data": []}
    items = []
    for item in sorted(earnings, key=lambda x: x.get("date", ""))[:30]:
        items.append({
            "symbol": item.get("symbol"),
            "date": item.get("date"),
            "hour": item.get("hour"),
            "eps_estimate": item.get("epsEstimate"),
            "eps_actual": item.get("epsActual"),
            "revenue_estimate": item.get("revenueEstimate"),
            "revenue_actual": item.get("revenueActual"),
            "quarter": item.get("quarter"),
            "year": item.get("year"),
        })
    return {"success": True, "count": len(items), "data": items}


def _transform_kopis_list(data: Any, tool_input: dict) -> dict:
    """KOPIS XML 목록 응답 변환 (레거시)"""
    if isinstance(data, dict) and "error" in data:
        return data
    items = _extract_xml_items(data, "db")
    return {"success": True, "count": len(items), "data": items}


def _transform_kopis_detail(data: Any, tool_input: dict) -> dict:
    """KOPIS XML 단일 상세 응답 변환 (레거시)"""
    if isinstance(data, dict) and "error" in data:
        return data
    items = _extract_xml_items(data, "db")
    if items:
        return {"success": True, "data": items[0]}
    return {"success": True, "data": data}


def _transform_library_docs(data: Any, tool_input: dict) -> dict:
    """도서관 XML 응답 변환 - doc (레거시)"""
    if isinstance(data, dict) and "error" in data:
        return data
    items = _extract_xml_items(data, "doc")
    return {"success": True, "count": len(items), "data": items}


def _transform_library_libs(data: Any, tool_input: dict) -> dict:
    """도서관 XML 응답 변환 - lib (레거시)"""
    if isinstance(data, dict) and "error" in data:
        return data
    items = _extract_xml_items(data, "lib")
    return {"success": True, "count": len(items), "data": items}


def _transform_kcisa_detail(data: Any, tool_input: dict) -> dict:
    """KCISA 상세 응답 변환 (레거시)"""
    if isinstance(data, dict) and "error" in data:
        return data
    items = _extract_xml_items(data, "item")
    if items:
        return {"success": True, "data": items[0]}
    return {"success": True, "data": data}


def _transform_kcisa_events(data: Any, tool_input: dict) -> dict:
    """KCISA 문화행사 목록 응답 변환 (레거시)"""
    if isinstance(data, dict) and "error" in data:
        return data
    items = _extract_xml_items(data, "item")
    return {"success": True, "count": len(items), "data": items}


# === XML 공통 헬퍼 ===

def _extract_xml_items(data: Any, tag_name: str) -> list:
    """XML 파싱 결과에서 특정 태그의 항목들을 추출"""
    if not isinstance(data, dict):
        return []
    if tag_name in data:
        val = data[tag_name]
        return val if isinstance(val, list) else [val]
    for key in ("body", "response", "dbs", "items", "result"):
        if key in data:
            sub = data[key]
            if isinstance(sub, dict):
                found = _extract_xml_items(sub, tag_name)
                if found:
                    return found
    return []


# === 레거시 등록 함수 ===

def register_legacy_transforms(registry: dict):
    """레거시 변환 함수들을 레지스트리에 등록 (하위 호환용)"""
    registry["naver_shopping"] = _transform_naver_shopping
    registry["kakao_restaurants"] = _transform_kakao_restaurants
    registry["ninjas_data"] = _transform_ninjas_data
    registry["kosis_list"] = _transform_kosis_list
    registry["kosis_data"] = _transform_kosis_list
    registry["kosis_info"] = _transform_kosis_list
    registry["kosis_search"] = _transform_kosis_list
    registry["kosis_indicators"] = _transform_kosis_list
    registry["kstartup"] = _transform_kstartup
    registry["fmp_profile"] = _transform_fmp_profile
    registry["finnhub_news"] = _transform_finnhub_news
    registry["finnhub_earnings"] = _transform_finnhub_earnings
    registry["kopis_list"] = _transform_kopis_list
    registry["kopis_detail"] = _transform_kopis_detail
    registry["library_docs"] = _transform_library_docs
    registry["library_libs"] = _transform_library_libs
    registry["kcisa_detail"] = _transform_kcisa_detail
    registry["kcisa_events"] = _transform_kcisa_events
