"""네이버 응답의 순수 변환. 인증·요청·호스트 상태를 소유하지 않는다."""
import re
from html import unescape


def clean_html(text):
    if not text:
        return ""
    return re.sub(r'\s+', ' ', unescape(re.sub(r'<[^>]+>', '', text))).strip()


def _item_date_iso(it: dict) -> dict:
    """news pub_date(RFC 2822)·blog post_date(YYYYMMDD) → {"date": ISO8601} · 불능이면 {}.

    gnews·hn 의 date 필드와 같은 계약 — 모르는 날짜는 싣지 않는다(미주장).
    """
    pub = it.get("pub_date", "")
    if pub:
        try:
            from email.utils import parsedate_to_datetime
            return {"date": parsedate_to_datetime(pub).isoformat()}
        except Exception:
            return {}
    post = it.get("post_date", "")
    if post and len(post) == 8 and post.isdigit():
        return {"date": f"{post[:4]}-{post[4:6]}-{post[6:]}"}
    return {}


def _format_item(item: dict, type_: str) -> dict:
    """도메인별 응답 item을 통일된 형식으로 변환"""
    base = {
        "title": clean_html(item.get("title", "")),
        "link": item.get("link", ""),
        "snippet": clean_html(item.get("description", "")),
        "site": "naver",
        "type": type_,
    }

    # 도메인별 추가 메타데이터
    if type_ == "news":
        base["pub_date"] = item.get("pubDate", "")
        base["original_link"] = item.get("originallink", "")
    elif type_ == "blog":
        base["blogger"] = item.get("bloggername", "")
        base["blogger_link"] = item.get("bloggerlink", "")
        base["post_date"] = item.get("postdate", "")
    elif type_ == "cafe":
        base["cafe_name"] = item.get("cafename", "")
        base["cafe_url"] = item.get("cafeurl", "")
    elif type_ == "encyc":
        base["thumbnail"] = item.get("thumbnail", "")

    return base


def transform(value):
    data, kind = value['response'], value['type']
    if not isinstance(data, dict) or not isinstance(data.get('items'), list):
        raise ValueError('응답 items 목록을 찾지 못했습니다')
    out = []
    for item in data['items']:
        if not isinstance(item, dict):
            raise ValueError('응답 항목은 객체여야 합니다')
        if not all(key in item for key in ('title', 'link')):
            raise ValueError('응답 항목의 title/link 필드가 없습니다')
        it = _format_item(item, kind)
        out.append({'title': it.get('title', ''), 'meta': '',
                    'summary': it.get('snippet', ''), 'url': it.get('link', ''),
                    **_item_date_iso(it)})
    return out
