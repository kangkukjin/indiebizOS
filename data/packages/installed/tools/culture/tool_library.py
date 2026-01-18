"""
tool_library.py - 국립중앙도서관 서지정보 API 도구
Culture 패키지

공공데이터포털(data.go.kr)에서 제공하는 국립중앙도서관 서지 정보 서비스입니다.
ISBN, 제목, 저자 등으로 도서 정보를 검색할 수 있습니다.

API 키: DATA_GO_KR_API_KEY 환경변수 사용
"""

import os
import requests
from urllib.parse import quote

BASE_URL = "https://apis.data.go.kr/1371029/BookInformationService"


def get_api_key():
    return os.environ.get("DATA_GO_KR_API_KEY", "")


def call_library_api(endpoint, params):
    """국립중앙도서관 API 호출"""
    api_key = get_api_key()
    if not api_key:
        return {
            "error": "DATA_GO_KR_API_KEY 환경변수가 설정되지 않았습니다.",
            "help": "공공데이터포털(data.go.kr)에서 API 키를 발급받으세요."
        }

    params["serviceKey"] = api_key
    url = f"{BASE_URL}/{endpoint}"

    try:
        response = requests.get(url, params=params, timeout=15)

        if response.status_code != 200:
            return {"error": f"API 호출 실패 (상태 코드: {response.status_code})"}

        # JSON 응답 파싱
        try:
            data = response.json()
        except:
            # XML 응답일 수 있음
            return {"error": "응답 파싱 실패", "raw": response.text[:500]}

        # 응답 구조 확인
        if "response" in data:
            resp = data["response"]
            header = resp.get("header", {})

            if header.get("resultCode") != "00":
                return {
                    "error": f"API 오류: {header.get('resultMsg', '알 수 없는 오류')}",
                    "code": header.get("resultCode")
                }

            body = resp.get("body", {})
            items = body.get("items", {})

            # items가 비어있는 경우 처리
            if not items:
                return {"count": 0, "data": [], "message": "검색 결과가 없습니다."}

            # item이 리스트가 아닌 경우 처리
            item_list = items.get("item", [])
            if isinstance(item_list, dict):
                item_list = [item_list]

            return {
                "count": body.get("totalCount", len(item_list)),
                "page": body.get("pageNo", 1),
                "rows": body.get("numOfRows", 10),
                "data": item_list
            }

        return data

    except requests.exceptions.Timeout:
        return {"error": "API 요청 시간 초과"}
    except Exception as e:
        return {"error": f"조회 실패: {str(e)}"}


def search_books(title=None, author=None, publisher=None, isbn=None,
                 subject=None, rows=10, page=1):
    """
    도서 검색

    Args:
        title: 도서 제목 (부분 일치)
        author: 저자명
        publisher: 출판사
        isbn: ISBN (10자리 또는 13자리)
        subject: 주제 분류
        rows: 결과 수 (최대 100)
        page: 페이지 번호

    Returns:
        검색 결과 목록
    """
    params = {
        "numOfRows": min(rows, 100),
        "pageNo": page,
        "resultType": "json"
    }

    # 검색 조건 추가
    if title:
        params["title"] = title
    if author:
        params["author"] = author
    if publisher:
        params["publisher"] = publisher
    if isbn:
        # ISBN에서 하이픈 제거
        params["isbn"] = isbn.replace("-", "")
    if subject:
        params["subject"] = subject

    # 검색 조건이 하나도 없으면 에러
    if not any([title, author, publisher, isbn, subject]):
        return {"error": "검색 조건을 하나 이상 입력해주세요. (title, author, publisher, isbn, subject)"}

    result = call_library_api("searchBookInfo", params)

    if "error" not in result:
        result["search_params"] = {
            "title": title,
            "author": author,
            "publisher": publisher,
            "isbn": isbn,
            "subject": subject
        }
        result["message"] = f"총 {result.get('count', 0)}건의 도서를 찾았습니다."

    return result


def get_book_by_isbn(isbn):
    """
    ISBN으로 도서 상세 정보 조회

    Args:
        isbn: ISBN (10자리 또는 13자리, 하이픈 포함 가능)

    Returns:
        도서 상세 정보
    """
    if not isbn:
        return {"error": "ISBN이 필요합니다."}

    # ISBN 정규화 (하이픈 제거)
    clean_isbn = isbn.replace("-", "").replace(" ", "")

    # ISBN 유효성 검사
    if len(clean_isbn) not in [10, 13]:
        return {"error": f"유효하지 않은 ISBN입니다. 10자리 또는 13자리여야 합니다. (입력: {clean_isbn})"}

    result = search_books(isbn=clean_isbn, rows=1)

    if "error" in result:
        return result

    if result.get("count", 0) == 0:
        return {"error": f"ISBN '{isbn}'에 해당하는 도서를 찾을 수 없습니다."}

    # 첫 번째 결과 반환
    book = result["data"][0] if result["data"] else None
    if book:
        return {"book": book, "message": "도서 정보를 찾았습니다."}

    return {"error": "도서 정보를 찾을 수 없습니다."}


def search_by_title(title, rows=10):
    """
    제목으로 도서 검색 (편의 함수)

    Args:
        title: 도서 제목 (부분 일치)
        rows: 결과 수
    """
    return search_books(title=title, rows=rows)


def search_by_author(author, rows=10):
    """
    저자명으로 도서 검색 (편의 함수)

    Args:
        author: 저자명
        rows: 결과 수
    """
    return search_books(author=author, rows=rows)


def search_by_publisher(publisher, rows=10):
    """
    출판사로 도서 검색 (편의 함수)

    Args:
        publisher: 출판사명
        rows: 결과 수
    """
    return search_books(publisher=publisher, rows=rows)
