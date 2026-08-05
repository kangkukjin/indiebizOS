"""국립중앙도서관 소장자료 검색 — nl.go.kr 통합검색 크롤 ([sense:book]{source: "nl"})

★2026-08-04 실측 계약:
- 공식 오픈API는 키 신청이 필요하지만, 통합검색 HTML은 봇차단 없이 맨 requests로 200.
- 각 결과 항목에 data-refWorks 속성으로 구조화 JSON이 실림(T1 제목/A1 저자/PB 출판사/
  YR 연도/SN ISBN13/FD 자료형태 — quote_plus 인코딩) → 태그 파싱 대신 이 블롭이 정본.
- 청구기호·자료이용(자료실)은 블롭 밖 HTML에만 있어 항목 chunk 안에서 regex로 짝지음.
- 의미: 납본 전수 코퍼스 — 공공도서관(정보나루)이 구입하지 않은 신간·소부수 출판도
  존재를 단언할 수 있다(정보나루=대출 렌즈, 여기=국가 서지 렌즈).
"""
import re
import json
import html as _html
import urllib.parse

import requests

_BASE = "https://www.nl.go.kr/NL/contents/search.do"
_HEADERS = {"User-Agent": "Mozilla/5.0"}


def _deplus(s: str) -> str:
    """refWorks 블롭 값 정리 — unquote_plus 후 남는 HTML 엔티티 해제."""
    return _html.unescape((s or "").strip())


def search_nl(keyword, category="도서", page=1, page_size=20):
    """국립중앙도서관 통합검색. category=도서(기본)/학위논문/기사 등, 빈 값=전체."""
    if not keyword:
        return {"success": False, "error": "검색어(keyword)가 필요합니다.", "items": []}
    params = {
        "pageNum": max(1, int(page or 1)),
        "pageSize": min(max(1, int(page_size or 20)), 50),
        "srchTarget": "total",
        "kwd": keyword,
    }
    if category:
        params["category"] = category
    try:
        r = requests.get(_BASE, params=params, headers=_HEADERS, timeout=25)
        r.raise_for_status()
    except requests.RequestException as e:
        return {"success": False, "error": f"국립중앙도서관 검색 실패: {e}", "items": []}
    h = r.text

    # 총건수는 "총 <em>N</em>건"처럼 태그가 끼므로 숫자 뒤 태그 허용
    m_total = re.search(r"검색\s*결과\s*총[^0-9]*([\d,]+)[^0-9]{0,20}건", h)
    total = int(m_total.group(1).replace(",", "")) if m_total else None

    # 항목 경계 = data-refWorks 위치 — 청구기호·자료실을 같은 chunk 안에서만 찾아 어긋남 방지
    starts = [m.start() for m in re.finditer(r"data-refWorks='", h)]
    items = []
    for i, pos in enumerate(starts):
        end = starts[i + 1] if i + 1 < len(starts) else len(h)
        chunk = h[pos:end]
        m_blob = re.match(r"data-refWorks='([^']+)'", chunk)
        if not m_blob:
            continue
        try:
            d = json.loads(urllib.parse.unquote_plus(m_blob.group(1)))
        except ValueError:
            continue
        title = _deplus(d.get("T1") or d.get("TI") or "")
        if not title:
            continue
        author = _deplus(d.get("A1") or "")
        publisher = _deplus(d.get("PB") or "")
        year = _deplus(d.get("YR") or "")
        form = _deplus(d.get("FD") or "")
        isbn = _deplus(d.get("SN") or "")
        m_call = re.search(r"청구기호\s*:\s*([^<]+)", chunk)
        m_room = re.search(r'data-layer="info_img_pop"[^>]*>\s*([^<]+)', chunk)
        callno = m_call.group(1).strip() if m_call else ""
        room = m_room.group(1).strip() if m_room else ""
        rec = {
            "title": title,
            "meta": " · ".join(x for x in [author, publisher, year, form] if x),
            "summary": " · ".join(x for x in [
                (f"청구기호 {callno}" if callno else ""), room] if x),
            "url": _BASE + "?" + urllib.parse.urlencode({"kwd": title, "srchTarget": "total"}),
        }
        if isbn:
            rec["isbn13"] = isbn
        items.append(rec)

    if not items:
        return {"items": [],
                "message": f"'{keyword}'에 대한 국립중앙도서관 소장 자료가 없습니다"
                           + (f" (category={category})." if category else ".")}
    head = f"국립중앙도서관 '{keyword}' — {len(items)}건"
    if isinstance(total, int):
        head += f" (전체 {total:,}건)"
    lines = [head]
    for it in items:
        lines.append(f"- {it['title']}" + (f" [{it['meta']}]" if it['meta'] else "")
                     + (f" — {it['summary']}" if it['summary'] else ""))
    return {"success": True, "message": "\n".join(lines),
            "items": items, "count": len(items), "total": total}
