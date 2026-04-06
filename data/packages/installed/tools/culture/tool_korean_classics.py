
import requests
import xml.etree.ElementTree as ET
import urllib.parse

def search_korean_classics(query: str, rows: int = 10) -> dict:
    url = f"https://db.itkc.or.kr/openapi/search?query={urllib.parse.quote(query)}&rows={rows}"
    try:
        response = requests.get(url, timeout=15)
        if response.status_code != 200:
            return {"error": f"HTTP 상태 코드 {response.status_code}"}
            
        root = ET.fromstring(response.content)
        
        total_count_node = root.find('.//header/field[@name="totalCount"]')
        total_count = int(total_count_node.text) if total_count_node is not None and total_count_node.text else 0
        
        result_docs = root.findall('.//result/doc')
        if not result_docs:
            return {"query": query, "total_count": total_count, "results": []}
            
        items = []
        for doc in result_docs:
            item = {}
            for field in doc.findall('field'):
                name = field.get('name')
                text = field.text or ""
                
                if name == '서명':
                    item['title'] = text
                elif name == '저자':
                    item['author'] = text
                elif name == '간행년':
                    item['year'] = text
                elif name == '검색필드':
                    item['content_snippet'] = text[:200] + "..." if len(text) > 200 else text
                elif name == '자료ID':
                    item['item_id'] = text
                    item['url'] = f"https://db.itkc.or.kr/dir/item?itemId={text}"
            items.append(item)
            
        return {
            "query": query,
            "total_count": total_count,
            "results": items
        }
        
    except Exception as e:
        return {"error": f"한국고전종합DB 검색 중 오류 발생: {str(e)}"}
