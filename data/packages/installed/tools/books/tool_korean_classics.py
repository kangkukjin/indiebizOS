"""한국고전종합DB(db.itkc.or.kr) OpenAPI 검색.

2026-09-29(78·79회차 B78-6 형제 점검) 실측: 이 원천의 검색어 인자는 `keyword` 다. 옛 코드가 보내던
`query` 는 원천이 조용히 무시해, 무엇을 물어도 전체 5,538,622건의 같은 첫 문서("가례도감의궤")가
돌아왔다. 원천은 받은 검색어를 헤더 `<field name='keyword'>` 로 되싣는다(이스케이프도 한다) —
보낸 검색어와 되실린 검색어가 다르면 원천이 질의를 읽지 않은 것이므로 결과를 싣지 않고 실패로 돌린다.
"""
import re
import xml.etree.ElementTree as ET

import requests

_SEARCH_URL = "https://db.itkc.or.kr/openapi/search"
_TAG = re.compile(r"<[^>]+>")


def _header_field(root, name):
    node = root.find(f'.//header/field[@name="{name}"]')
    return (node.text or "") if node is not None else ""


def search_korean_classics(query: str, rows: int = 10) -> dict:
    query = str(query or "").strip()
    if not query:
        return {"success": False, "error_type": "input", "error": "query(검색어)가 필요합니다."}
    try:
        response = requests.get(_SEARCH_URL, params={"keyword": query, "rows": rows}, timeout=15)
        if response.status_code != 200:
            return {"success": False, "error": f"HTTP 상태 코드 {response.status_code}"}
        try:
            root = ET.fromstring(response.content)
        except ET.ParseError as e:
            return {"success": False, "error_type": "source_parse",
                    "error": f"한국고전종합DB 응답 XML 이 깨져 읽지 못했습니다(원천 응답 결함): {e}"}

        echoed = " ".join(_header_field(root, "keyword").split())
        if echoed != " ".join(query.split()):
            return {"success": False, "error_type": "source_changed",
                    "error": ("한국고전종합DB가 검색어를 읽지 않았습니다(되실린 검색어 "
                              f"{echoed!r} ≠ 보낸 {query!r}) — 원천 검색 인자 계약이 바뀐 것으로 보입니다.")}

        total_text = _header_field(root, "totalCount")
        total_count = int(total_text) if total_text.isdigit() else 0

        items = []
        for doc in root.findall('.//result/doc'):
            item = {}
            for field in doc.findall('field'):
                name = field.get('name')
                text = field.text or ""
                if name == '서명':
                    item['title'] = text
                elif name == '기사명':
                    item['article'] = text
                elif name == '권차명':
                    item['volume'] = text
                elif name == '저자':
                    item['author'] = text
                elif name == '간행년':
                    item['year'] = text
                elif name == '검색필드':
                    # 원천이 일치 구간을 <em class="hl1"> 로 감싸 보낸다 — 본문 발췌에서 표시 태그를 뺀다.
                    plain = _TAG.sub("", text)
                    item['content_snippet'] = plain[:200] + "..." if len(plain) > 200 else plain
                elif name == '자료ID':
                    item['item_id'] = text
                    item['url'] = f"https://db.itkc.or.kr/dir/item?itemId={text}"
            items.append(item)

        return {"query": query, "total_count": total_count, "results": items}

    except Exception as e:
        return {"success": False, "error": f"한국고전종합DB 검색 중 오류 발생: {str(e)}"}
