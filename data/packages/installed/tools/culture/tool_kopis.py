"""
KOPIS API - 공연예술통합전산망 공연 정보 조회 도구

KOPIS(Korea Performing Arts Box Office Information System)는
예술경영지원센터에서 운영하는 공연 정보 통합 시스템입니다.

API 키 발급: https://www.kopis.or.kr/por/cs/openapi/openApiInfo.do
"""

import os
import requests
import xml.etree.ElementTree as ET
import json
from datetime import datetime, timedelta

BASE_URL = "http://www.kopis.or.kr/openApi/restful"

# 지역 코드 매핑 (한글/영문 모두 지원)
REGION_CODES = {
    "서울": "11", "seoul": "11",
    "부산": "26", "busan": "26",
    "대구": "27", "daegu": "27",
    "인천": "28", "incheon": "28",
    "광주": "29", "gwangju": "29",
    "대전": "30", "daejeon": "30",
    "울산": "31", "ulsan": "31",
    "세종": "36", "sejong": "36",
    "경기": "41", "gyeonggi": "41",
    "강원": "42", "gangwon": "42",
    "충북": "43", "chungbuk": "43",
    "충남": "44", "chungnam": "44",
    "전북": "45", "jeonbuk": "45",
    "전남": "46", "jeonnam": "46",
    "경북": "47", "gyeongbuk": "47",
    "경남": "48", "gyeongnam": "48",
    "제주": "50", "jeju": "50",
}

# 장르 코드 매핑
GENRE_CODES = {
    "연극": "AAAA", "theater": "AAAA", "play": "AAAA",
    "뮤지컬": "GGGA", "musical": "GGGA",
    "클래식": "CCCA", "classic": "CCCA", "classical": "CCCA",
    "국악": "CCCC", "korean": "CCCC",
    "대중음악": "CCCD", "pop": "CCCD", "concert": "CCCD",
    "무용": "BBBC", "dance": "BBBC",
    "대중무용": "BBBE", "popular_dance": "BBBE",
    "서커스/마술": "EEEA", "circus": "EEEA", "magic": "EEEA",
    "복합": "EEEB", "complex": "EEEB", "mixed": "EEEB",
}

# 공연 상태 코드
STATUS_CODES = {
    "공연예정": "01", "upcoming": "01",
    "공연중": "02", "ongoing": "02", "running": "02",
    "공연완료": "03", "ended": "03", "completed": "03",
}


def get_api_key():
    return os.environ.get("KOPIS_API_KEY", "")


def _format_date(date_str):
    """날짜 문자열 정규화 (YYYYMMDD 형식으로)"""
    if not date_str:
        return None
    # 이미 올바른 형식
    if len(date_str) == 8 and date_str.isdigit():
        return date_str
    # 다양한 형식 처리
    for fmt in ["%Y-%m-%d", "%Y/%m/%d", "%Y.%m.%d"]:
        try:
            dt = datetime.strptime(date_str, fmt)
            return dt.strftime("%Y%m%d")
        except ValueError:
            continue
    return date_str


def _resolve_region(region):
    """지역명을 코드로 변환"""
    if not region:
        return None
    region_lower = region.lower() if isinstance(region, str) else region
    return REGION_CODES.get(region_lower, REGION_CODES.get(region, region))


def _resolve_genre(genre):
    """장르명을 코드로 변환"""
    if not genre:
        return None
    genre_lower = genre.lower() if isinstance(genre, str) else genre
    return GENRE_CODES.get(genre_lower, GENRE_CODES.get(genre, genre))


def _resolve_status(status):
    """공연상태를 코드로 변환"""
    if not status:
        return None
    status_lower = status.lower() if isinstance(status, str) else status
    return STATUS_CODES.get(status_lower, STATUS_CODES.get(status, status))


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


def call_kopis_api(endpoint, params):
    api_key = get_api_key()
    if not api_key:
        return {
            "error": "KOPIS_API_KEY 환경변수가 설정되지 않았습니다.",
            "help": "https://www.kopis.or.kr/por/cs/openapi/openApiInfo.do 에서 API 키를 발급받으세요."
        }

    params["service"] = api_key
    url = f"{BASE_URL}/{endpoint}"

    try:
        response = requests.get(url, params=params, timeout=15)
        if response.status_code != 200:
            return {"error": f"API 호출 실패 (상태 코드: {response.status_code})"}

        root = ET.fromstring(response.content)

        # 목록형 데이터 (db 태그가 여러개인 경우)
        if endpoint.split("/")[0] in ["pblprfr", "prfsts", "prfplc", "boxoffice", "prffest"]:
            results = []
            for item in root.findall('db'):
                results.append(xml_to_dict(item))
            return {"count": len(results), "data": results}

        # 상세 정보 (태그가 하나인 경우)
        return xml_to_dict(root)

    except ET.ParseError as e:
        return {"error": f"XML 파싱 오류: {str(e)}", "raw": response.text[:200]}
    except requests.exceptions.Timeout:
        return {"error": "KOPIS API 요청 시간 초과"}
    except Exception as e:
        return {"error": f"조회 실패: {str(e)}"}


def get_performances(stdate, eddate, shcate=None, signgucode=None, prfstate="02",
                     keyword=None, rows=10, cpage=1):
    """
    공연 목록 조회

    Args:
        stdate: 시작일 (YYYYMMDD 또는 YYYY-MM-DD)
        eddate: 종료일
        shcate: 장르 (연극, 뮤지컬, musical 등)
        signgucode: 지역 (서울, 부산, seoul 등)
        prfstate: 공연 상태 (공연중, 공연예정, ongoing 등)
        keyword: 공연명 검색어
        rows: 결과 수
        cpage: 페이지 번호
    """
    params = {
        "stdate": _format_date(stdate),
        "eddate": _format_date(eddate),
        "rows": min(rows, 100),
        "cpage": cpage,
    }

    # 상태 코드 변환
    if prfstate:
        params["prfstate"] = _resolve_status(prfstate)

    # 장르 코드 변환
    if shcate:
        params["shcate"] = _resolve_genre(shcate)

    # 지역 코드 변환
    if signgucode:
        params["signgucode"] = _resolve_region(signgucode)

    # 공연명 검색
    if keyword:
        params["shprfnm"] = keyword

    result = call_kopis_api("pblprfr", params)

    # 결과에 검색 파라미터 추가
    if "error" not in result:
        result["search_params"] = {
            "start_date": stdate,
            "end_date": eddate,
            "genre": shcate,
            "region": signgucode,
            "status": prfstate,
            "keyword": keyword
        }
        result["message"] = f"총 {result.get('count', 0)}개의 공연을 찾았습니다."

    return result


def get_performance_detail(performance_id):
    """공연 상세 정보 조회"""
    if not performance_id:
        return {"error": "공연 ID가 필요합니다."}
    return call_kopis_api(f"pblprfr/{performance_id}", {})


def get_box_office(ststype="day", date=None, catecode=None, area=None):
    """
    예매 순위(박스오피스) 조회

    Args:
        ststype: 조회 주기 (day, week, month)
        date: 기준일 (YYYYMMDD), 기본값: 어제
        catecode: 장르 (연극, 뮤지컬 등)
        area: 지역 (서울, 부산 등)
    """
    # 기본값: 어제 (당일 데이터는 없을 수 있음)
    if not date:
        yesterday = datetime.now() - timedelta(days=1)
        date = yesterday.strftime("%Y%m%d")

    params = {
        "ststype": ststype,
        "date": _format_date(date)
    }

    if catecode:
        params["catecode"] = _resolve_genre(catecode)
    if area:
        params["area"] = _resolve_region(area)

    result = call_kopis_api("boxoffice", params)

    if "error" not in result:
        result["query"] = {
            "type": ststype,
            "date": date,
            "genre": catecode,
            "area": area
        }
        result["message"] = f"{date} 기준 박스오피스 {result.get('count', 0)}개 공연"

    return result


def get_facilities(facility_name=None, facility_id=None, signgucode=None, rows=10, cpage=1):
    """
    공연시설(공연장) 조회

    Args:
        facility_name: 시설명 검색어
        facility_id: 시설 ID (상세 조회용)
        signgucode: 지역
        rows: 결과 수
        cpage: 페이지 번호
    """
    if facility_id:
        return call_kopis_api(f"prfplc/{facility_id}", {})

    params = {"rows": min(rows, 100), "cpage": cpage}

    if facility_name:
        params["shprfnmfct"] = facility_name

    if signgucode:
        params["signgucode"] = _resolve_region(signgucode)

    result = call_kopis_api("prfplc", params)

    if "error" not in result:
        result["message"] = f"총 {result.get('count', 0)}개의 공연시설을 찾았습니다."

    return result


def get_festivals(stdate=None, eddate=None, shcate=None, signgucode=None, rows=20, cpage=1):
    """
    축제/페스티벌 목록 조회

    Args:
        stdate: 시작일
        eddate: 종료일
        shcate: 장르
        signgucode: 지역
        rows: 결과 수
        cpage: 페이지 번호
    """
    today = datetime.now()

    if not stdate:
        stdate = today.strftime("%Y%m%d")
    if not eddate:
        eddate = (today + timedelta(days=180)).strftime("%Y%m%d")

    params = {
        "stdate": _format_date(stdate),
        "eddate": _format_date(eddate),
        "rows": min(rows, 100),
        "cpage": cpage,
    }

    if shcate:
        params["shcate"] = _resolve_genre(shcate)
    if signgucode:
        params["signgucode"] = _resolve_region(signgucode)

    result = call_kopis_api("prffest", params)

    if "error" not in result:
        result["message"] = f"총 {result.get('count', 0)}개의 축제를 찾았습니다."

    return result


def get_genre_list():
    """지원하는 장르 목록 반환"""
    return {
        "genres": [
            {"code": "AAAA", "name": "연극", "aliases": ["theater", "play"]},
            {"code": "GGGA", "name": "뮤지컬", "aliases": ["musical"]},
            {"code": "CCCA", "name": "클래식", "aliases": ["classic", "classical"]},
            {"code": "CCCC", "name": "국악", "aliases": ["korean"]},
            {"code": "CCCD", "name": "대중음악", "aliases": ["pop", "concert"]},
            {"code": "BBBC", "name": "무용", "aliases": ["dance"]},
            {"code": "BBBE", "name": "대중무용", "aliases": ["popular_dance"]},
            {"code": "EEEA", "name": "서커스/마술", "aliases": ["circus", "magic"]},
            {"code": "EEEB", "name": "복합", "aliases": ["complex", "mixed"]},
        ],
        "message": "KOPIS API에서 지원하는 장르 목록입니다. 한글명 또는 영문 별칭을 사용할 수 있습니다."
    }


def get_region_list():
    """지원하는 지역 목록 반환"""
    return {
        "regions": [
            {"code": "11", "name": "서울", "aliases": ["seoul"]},
            {"code": "26", "name": "부산", "aliases": ["busan"]},
            {"code": "27", "name": "대구", "aliases": ["daegu"]},
            {"code": "28", "name": "인천", "aliases": ["incheon"]},
            {"code": "29", "name": "광주", "aliases": ["gwangju"]},
            {"code": "30", "name": "대전", "aliases": ["daejeon"]},
            {"code": "31", "name": "울산", "aliases": ["ulsan"]},
            {"code": "36", "name": "세종", "aliases": ["sejong"]},
            {"code": "41", "name": "경기", "aliases": ["gyeonggi"]},
            {"code": "42", "name": "강원", "aliases": ["gangwon"]},
            {"code": "43", "name": "충북", "aliases": ["chungbuk"]},
            {"code": "44", "name": "충남", "aliases": ["chungnam"]},
            {"code": "45", "name": "전북", "aliases": ["jeonbuk"]},
            {"code": "46", "name": "전남", "aliases": ["jeonnam"]},
            {"code": "47", "name": "경북", "aliases": ["gyeongbuk"]},
            {"code": "48", "name": "경남", "aliases": ["gyeongnam"]},
            {"code": "50", "name": "제주", "aliases": ["jeju"]},
        ],
        "message": "KOPIS API에서 지원하는 지역 목록입니다. 한글명 또는 영문 별칭을 사용할 수 있습니다."
    }


def search_by_keyword(keyword, genre=None, region=None, status="공연중", days=90):
    """
    키워드로 공연 검색 (편의 함수)

    Args:
        keyword: 검색어
        genre: 장르
        region: 지역
        status: 공연 상태
        days: 검색 기간 (오늘부터 N일 후까지)
    """
    today = datetime.now()
    stdate = today.strftime("%Y%m%d")
    eddate = (today + timedelta(days=days)).strftime("%Y%m%d")

    return get_performances(
        stdate=stdate,
        eddate=eddate,
        shcate=genre,
        signgucode=region,
        prfstate=status,
        keyword=keyword,
        rows=20
    )
