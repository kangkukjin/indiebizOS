"""Google Books 글로벌 도서 검색 — [sense:book]{source: "google"}.

구 study 패키지 [sense:search_books] 를 2026-08-05 어휘 압축 (6)-2b 에서 흡수.
반환 필드는 도서관정보나루(tool_library)와 같은 이름(bookname/authors/…) — 도서 계기가
source 무관하게 그대로 렌더한다. 익명 호출은 IP당 할당량이 작아 429가 잦으므로
.env GOOGLE_BOOKS_API_KEY 가 있으면 사용.
"""
import os
import time

import requests


def search_google_books(query: str, max_results: int = 5, order_by: str = "relevance") -> dict:
    url = "https://www.googleapis.com/books/v1/volumes"
    params = {
        "q": query,
        "maxResults": min(max_results, 40),
        "orderBy": order_by,
        "printType": "books"
    }
    _gbooks_key = os.environ.get("GOOGLE_BOOKS_API_KEY", "").strip()
    if _gbooks_key:
        params["key"] = _gbooks_key

    try:
        # 429(Too Many Requests) 시 짧게 백오프 후 재시도 (최대 3회)
        response = None
        for _attempt in range(3):
            response = requests.get(url, params=params, timeout=15)
            if response.status_code == 429 and _attempt < 2:
                time.sleep(1.5 * (_attempt + 1))
                continue
            break
        response.raise_for_status()
        data = response.json()

        items = data.get("items", [])

        # 구조화 반환 — 도서 계기가 그대로 렌더할 수 있게 도서관정보나루(book)와 같은 필드명.
        books = []
        for item in items:
            info = item.get("volumeInfo", {})
            isbn13 = ""
            for idf in info.get("industryIdentifiers", []):
                if idf.get("type") == "ISBN_13":
                    isbn13 = idf.get("identifier", "")
                    break
            img = info.get("imageLinks") or {}
            image_url = img.get("thumbnail") or img.get("smallThumbnail") or ""
            books.append({
                # F16-4: 제목 칸 title 병기(R7 칸 규약 — bookname 원명 보존)
                "title": info.get("title", ""),
                "bookname": info.get("title", ""),
                "authors": ", ".join(info.get("authors", [])),
                "publisher": info.get("publisher", ""),
                "publication_year": (info.get("publishedDate", "") or "")[:4],
                "isbn13": isbn13,
                "bookImageURL": image_url,
                "description": info.get("description", ""),
                "categories": ", ".join(info.get("categories", [])),
                "page_count": info.get("pageCount"),
                "infoLink": info.get("infoLink", ""),
            })

        return {
            "count": data.get("totalItems", len(books)),
            "items": books,  # 단일 통화: native 도서 dict(bookname/authors/description/image 등 풍부)
            "message": f"'{query}' Google Books 검색 {len(books)}건",
        }

    except Exception as e:
        return {"success": False, "error": f"Google Books API 요청 오류: {str(e)}", "items": []}
