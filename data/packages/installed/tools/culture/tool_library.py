"""
tool_library.py - 도서관 정보나루 API 도서검색 도구
Culture 패키지

도서관 정보나루(data4library.kr) Open API
- 전국 공공도서관의 장서, 대출 정보 제공
- 도서 검색, 인기대출도서, 도서 상세정보 등

API 엔드포인트:
- /api/srchBooks: 도서 검색
- /api/srchDtlList: 도서 상세조회
- /api/loanItemSrch: 인기대출도서 조회
- /api/libSrch: 도서관 검색
- /api/libSrchByBook: 도서 소장 도서관 검색
- /api/hotTrend: 대출 급상승 도서
- /api/recommandList: 추천도서 (마니아/다독자)

API 키: DATA4LIBRARY_API_KEY 환경변수 사용
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


def parse_xml_response(xml_text):
    """XML 응답을 파싱하여 딕셔너리로 변환"""
    # JSON 응답인 경우 처리
    if xml_text.strip().startswith('{'):
        try:
            import json
            data = json.loads(xml_text)
            # JSON 에러 응답 처리
            if "response" in data and "error" in data["response"]:
                return {
                    "error": f"API 오류: {data['response']['error']}",
                    "help": "도서관 정보나루에서 API 활성화 상태를 확인하세요. (https://www.data4library.kr)"
                }
            return data
        except json.JSONDecodeError:
            pass

    try:
        root = ET.fromstring(xml_text)

        # 에러 체크
        err_code = root.find('.//errCode')
        err_msg = root.find('.//errMsg')

        if err_code is not None and err_code.text:
            return {
                "error": f"API 오류: {err_msg.text if err_msg is not None else '알 수 없는 오류'}",
                "code": err_code.text
            }

        return root
    except ET.ParseError as e:
        return {"error": f"XML 파싱 실패: {str(e)}", "raw": xml_text[:500]}


def call_library_api(endpoint, params):
    """
    도서관 정보나루 API 호출 (common api_call 사용)

    Args:
        endpoint: API 엔드포인트 (예: srchBooks)
        params: 요청 파라미터

    Returns:
        API 응답 데이터 (XML Element 또는 에러 딕셔너리)
    """
    # API 키 확인
    ok, err = check_api_key("data4library")
    if not ok:
        return {
            "error": err,
            "help": "DATA4LIBRARY_API_KEY 환경변수를 설정하거나 도서관 정보나루에서 API 키를 발급받으세요."
        }

    # api_call로 HTTP 요청 (XML 응답이므로 raw_response=True)
    response_text = api_call(
        "data4library",
        f"/{endpoint}",
        params=params,
        extra_headers={
            "Accept": "application/xml",
            "User-Agent": "IndieBizOS/1.0"
        },
        timeout=30,
        raw_response=True,
    )

    # api_call이 에러 dict를 반환한 경우
    if isinstance(response_text, dict) and "error" in response_text:
        return response_text

    return parse_xml_response(response_text)


def extract_books_from_xml(root, item_tag="doc"):
    """XML에서 도서 목록 추출"""
    books = []

    for item in root.findall(f'.//{item_tag}'):
        book = {}
        for child in item:
            if child.text:
                book[child.tag] = child.text.strip()
        if book:
            books.append(book)

    return books


def extract_libs_from_xml(root):
    """XML에서 도서관 목록 추출"""
    libs = []

    for lib in root.findall('.//lib'):
        lib_info = {}
        for child in lib:
            if child.text:
                lib_info[child.tag] = child.text.strip()
        if lib_info:
            libs.append(lib_info)

    return libs


# ==================== 도서 검색 API ====================

def search_books(keyword, page=1, page_size=10):
    """
    도서 검색 (키워드 기반)

    도서관 정보나루의 이용분석 대상 도서를 검색합니다.

    Args:
        keyword: 검색 키워드 (제목, 저자, 출판사 등)
        page: 페이지 번호 (기본값: 1)
        page_size: 한 페이지당 결과 수 (기본값: 10, 최대: 100)

    Returns:
        검색 결과 목록
    """
    if not keyword:
        return {"error": "검색 키워드를 입력해주세요."}

    params = {
        "keyword": keyword,
        "pageNo": page,
        "pageSize": min(page_size, 100)
    }

    result = call_library_api("srchBooks", params)

    if isinstance(result, dict) and "error" in result:
        return result

    # XML 파싱
    books = extract_books_from_xml(result, "doc")

    # 총 결과 수 추출
    num_found = result.find('.//numFound')
    total = int(num_found.text) if num_found is not None and num_found.text else len(books)

    return {
        "count": total,
        "page": page,
        "pageSize": page_size,
        "data": books,
        "message": f"'{keyword}' 검색 결과: 총 {total}건"
    }


def get_book_detail(isbn13, loan_info=True):
    """
    도서 상세 정보 조회

    ISBN13으로 도서의 상세 정보를 조회합니다.

    Args:
        isbn13: ISBN 13자리
        loan_info: 대출 정보 포함 여부 (기본값: True)

    Returns:
        도서 상세 정보 (책소개, 대출 통계 등)
    """
    if not isbn13:
        return {"error": "ISBN을 입력해주세요."}

    # ISBN 정규화 (하이픈 제거)
    clean_isbn = isbn13.replace("-", "").replace(" ", "")

    if len(clean_isbn) != 13:
        return {
            "error": "ISBN 13자리를 입력해주세요.",
            "input": isbn13,
            "help": "ISBN-13 형식 (예: 9788937460494)"
        }

    params = {
        "isbn13": clean_isbn,
        "loaninfoYN": "Y" if loan_info else "N"
    }

    result = call_library_api("srchDtlList", params)

    if isinstance(result, dict) and "error" in result:
        return result

    # 도서 정보 추출
    detail = result.find('.//detail')
    if detail is None:
        return {
            "error": f"ISBN '{isbn13}'에 해당하는 도서를 찾을 수 없습니다.",
            "suggestion": "ISBN을 확인하거나 키워드로 검색해보세요."
        }

    book_info = {}
    for child in detail:
        if child.text:
            book_info[child.tag] = child.text.strip()

    # 대출 정보 추출
    if loan_info:
        loan_data = {
            "by_region": [],
            "by_age": []
        }

        # 지역별 대출
        for loan in result.findall('.//loanInfo'):
            loan_entry = {}
            for child in loan:
                if child.text:
                    loan_entry[child.tag] = child.text.strip()
            if loan_entry:
                loan_data["by_region"].append(loan_entry)

        # 연령별 대출
        for age_loan in result.findall('.//loanInfoByAge'):
            age_entry = {}
            for child in age_loan:
                if child.text:
                    age_entry[child.tag] = child.text.strip()
            if age_entry:
                loan_data["by_age"].append(age_entry)

        book_info["loan_stats"] = loan_data

    return {
        "book": book_info,
        "message": "도서 상세 정보를 조회했습니다."
    }


# ==================== 인기대출도서 API ====================

def get_popular_books(start_date=None, end_date=None, gender=None,
                     from_age=None, to_age=None, region=None,
                     kdc=None, page=1, page_size=10):
    """
    인기대출도서 조회

    기간, 성별, 연령대, 지역, 주제분류별 인기 대출 도서를 조회합니다.

    Args:
        start_date: 시작일 (YYYY-MM-DD, 기본: 7일 전)
        end_date: 종료일 (YYYY-MM-DD, 기본: 어제)
        gender: 성별 (0: 남성, 1: 여성)
        from_age: 시작 연령 (예: 20)
        to_age: 종료 연령 (예: 29)
        region: 지역코드 (예: 11=서울)
        kdc: KDC 분류코드 (예: 8=문학)
        page: 페이지 번호
        page_size: 결과 수

    Returns:
        인기대출도서 목록
    """
    # 기본 날짜 설정
    if not end_date:
        end_date = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")
    if not start_date:
        start_date = (datetime.now() - timedelta(days=7)).strftime("%Y-%m-%d")

    params = {
        "startDt": start_date,
        "endDt": end_date,
        "pageNo": page,
        "pageSize": min(page_size, 100)
    }

    # 선택 파라미터 추가
    if gender is not None:
        params["gender"] = gender
    if from_age is not None:
        params["from_age"] = from_age
    if to_age is not None:
        params["to_age"] = to_age
    if region:
        params["region"] = region
    if kdc:
        params["kdc"] = kdc

    result = call_library_api("loanItemSrch", params)

    if isinstance(result, dict) and "error" in result:
        return result

    # 도서 목록 추출
    books = extract_books_from_xml(result, "doc")

    # 총 결과 수
    num_found = result.find('.//numFound')
    total = int(num_found.text) if num_found is not None and num_found.text else len(books)

    # 필터 정보
    filters = {}
    if gender is not None:
        filters["gender"] = "남성" if gender == 0 else "여성"
    if from_age and to_age:
        filters["age_range"] = f"{from_age}~{to_age}세"
    if region:
        filters["region"] = region
    if kdc:
        filters["kdc"] = kdc

    return {
        "count": total,
        "page": page,
        "pageSize": page_size,
        "period": f"{start_date} ~ {end_date}",
        "filters": filters if filters else None,
        "data": books,
        "message": f"인기대출도서 {total}건 조회"
    }


def get_trending_books(base_date=None):
    """
    대출 급상승 도서 조회

    최근 대출이 급상승한 도서를 조회합니다.

    Args:
        base_date: 기준일 (YYYY-MM-DD, 기본: 어제)

    Returns:
        대출 급상승 도서 목록
    """
    if not base_date:
        base_date = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")

    params = {
        "searchDt": base_date
    }

    result = call_library_api("hotTrend", params)

    if isinstance(result, dict) and "error" in result:
        return result

    # 도서 목록 추출
    books = extract_books_from_xml(result, "doc")

    return {
        "base_date": base_date,
        "count": len(books),
        "data": books,
        "message": f"{base_date} 기준 대출 급상승 도서 {len(books)}건"
    }


# ==================== 추천도서 API ====================

def get_recommended_books(isbn13, rec_type="mania"):
    """
    추천도서 조회

    특정 도서와 관련된 추천도서를 조회합니다.

    Args:
        isbn13: 기준 도서의 ISBN13
        rec_type: 추천 유형 (mania: 마니아 추천, reader: 다독자 추천)

    Returns:
        추천도서 목록
    """
    if not isbn13:
        return {"error": "기준 도서의 ISBN을 입력해주세요."}

    clean_isbn = isbn13.replace("-", "").replace(" ", "")

    params = {
        "isbn13": clean_isbn,
        "type": rec_type
    }

    result = call_library_api("recommandList", params)

    if isinstance(result, dict) and "error" in result:
        return result

    # 도서 목록 추출
    books = extract_books_from_xml(result, "doc")

    rec_type_name = "마니아" if rec_type == "mania" else "다독자"

    return {
        "base_isbn": isbn13,
        "rec_type": rec_type_name,
        "count": len(books),
        "data": books,
        "message": f"'{rec_type_name}' 추천도서 {len(books)}건"
    }


# ==================== 도서관 검색 API ====================

def search_libraries(name=None, region=None, page=1, page_size=10):
    """
    도서관 검색

    전국 공공도서관 정보를 검색합니다.

    Args:
        name: 도서관명 (부분 일치)
        region: 지역코드 (예: 11=서울, 26=부산)
        page: 페이지 번호
        page_size: 결과 수

    Returns:
        도서관 목록
    """
    params = {
        "pageNo": page,
        "pageSize": min(page_size, 100)
    }

    if name:
        params["libName"] = name
    if region:
        params["region"] = region

    result = call_library_api("libSrch", params)

    if isinstance(result, dict) and "error" in result:
        return result

    # 도서관 목록 추출
    libs = extract_libs_from_xml(result)

    # 총 결과 수
    num_found = result.find('.//numFound')
    total = int(num_found.text) if num_found is not None and num_found.text else len(libs)

    return {
        "count": total,
        "page": page,
        "pageSize": page_size,
        "data": libs,
        "message": f"도서관 {total}건 검색됨"
    }


def search_libraries_by_book(isbn13, region=None, page=1, page_size=10):
    """
    도서 소장 도서관 검색

    특정 도서를 소장하고 있는 도서관을 검색합니다.

    Args:
        isbn13: 도서의 ISBN13
        region: 지역코드 (선택)
        page: 페이지 번호
        page_size: 결과 수

    Returns:
        소장 도서관 목록
    """
    if not isbn13:
        return {"error": "ISBN을 입력해주세요."}

    clean_isbn = isbn13.replace("-", "").replace(" ", "")

    params = {
        "isbn": clean_isbn,
        "pageNo": page,
        "pageSize": min(page_size, 100)
    }

    if region:
        params["region"] = region

    result = call_library_api("libSrchByBook", params)

    if isinstance(result, dict) and "error" in result:
        return result

    # 도서관 목록 추출
    libs = extract_libs_from_xml(result)

    # 총 결과 수
    num_found = result.find('.//numFound')
    total = int(num_found.text) if num_found is not None and num_found.text else len(libs)

    return {
        "isbn": isbn13,
        "count": total,
        "page": page,
        "pageSize": page_size,
        "data": libs,
        "message": f"'{isbn13}' 소장 도서관 {total}건"
    }


# ==================== 편의 함수 ====================

def quick_search(keyword, rows=10):
    """
    빠른 도서 검색 (편의 함수)

    키워드로 도서를 빠르게 검색합니다.

    Args:
        keyword: 검색 키워드
        rows: 결과 수
    """
    return search_books(keyword=keyword, page_size=rows)


def get_book_by_isbn(isbn):
    """
    ISBN으로 도서 조회 (편의 함수)

    ISBN으로 도서 상세 정보를 조회합니다.

    Args:
        isbn: ISBN (10자리 또는 13자리)
    """
    # 10자리 ISBN을 13자리로 변환
    clean_isbn = isbn.replace("-", "").replace(" ", "")

    if len(clean_isbn) == 10:
        # ISBN-10 → ISBN-13 변환
        isbn13 = "978" + clean_isbn[:-1]
        # 체크섬 계산
        total = 0
        for i, digit in enumerate(isbn13):
            weight = 1 if i % 2 == 0 else 3
            total += int(digit) * weight
        check = (10 - (total % 10)) % 10
        isbn13 += str(check)
        clean_isbn = isbn13

    return get_book_detail(isbn13=clean_isbn, loan_info=True)


# ==================== 지역코드 참조 ====================

REGION_CODES = {
    "서울": "11", "부산": "26", "대구": "27", "인천": "28",
    "광주": "29", "대전": "30", "울산": "31", "세종": "36",
    "경기": "41", "강원": "42", "충북": "43", "충남": "44",
    "전북": "45", "전남": "46", "경북": "47", "경남": "48",
    "제주": "50"
}


def get_region_code(region_name):
    """지역명을 지역코드로 변환"""
    if region_name in REGION_CODES:
        return REGION_CODES[region_name]
    # 이미 코드인 경우
    if region_name in REGION_CODES.values():
        return region_name
    return None


def get_region_list():
    """지역코드 목록 반환"""
    return {
        "regions": REGION_CODES,
        "message": "지역코드 목록입니다. 지역명 또는 코드를 사용할 수 있습니다."
    }


# ==================== KDC 분류코드 참조 ====================

KDC_CODES = {
    "총류": "0", "철학": "1", "종교": "2", "사회과학": "3",
    "자연과학": "4", "기술과학": "5", "예술": "6", "언어": "7",
    "문학": "8", "역사": "9"
}


def get_kdc_list():
    """KDC 분류코드 목록 반환"""
    return {
        "kdc_codes": KDC_CODES,
        "message": "KDC 주제분류코드 목록입니다."
    }
