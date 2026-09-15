"""페이지의 링크·메타정보를 원문 근거와 함께 추출한다. 모델 호출·날짜 추정 없음."""
import json
from datetime import datetime
from urllib.parse import urljoin, urlsplit

from bs4 import BeautifulSoup


def http_url(value, base):
    """HTML base와 상대 주소를 해소하되 실행·메일 주소는 수집하지 않는다."""
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        url = urljoin(base, value.strip())
        parts = urlsplit(url)
        return url if parts.scheme in {"http", "https"} and parts.netloc else None
    except ValueError:
        return None


def extract(html, url):
    soup = BeautifulSoup(html, "html.parser")
    title = soup.title.get_text(" ", strip=True) if soup.title else ""
    base_tag = soup.find("base", href=True)
    base = http_url(base_tag["href"], url) if base_tag else url
    base = base or url
    links, metadata = [], []

    def add(field, raw, source, *, entity=None):
        if raw is None or isinstance(raw, (dict, list)):
            return
        raw = str(raw).strip()
        if not raw:
            return
        value = raw
        if field == "canonical_url":
            value = http_url(raw, base)
            if value is None:
                return
        row = {"field": field, "value": value, "raw": raw, "source": source,
               "source_url": url, "url": url, "title": title}
        if entity is not None:
            row["entity"] = entity
        if field in {"published_at", "modified_at", "date"}:
            # ISO 날짜/시각만 정규화한다. timezone·날짜가 없으면 만들어내지 않는다.
            try:
                parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
                row["normalized"] = parsed.date().isoformat() if len(raw) == 10 else parsed.isoformat()
            except ValueError:
                row["normalized"] = None
        metadata.append(row)

    add("title", title, "title")
    for i, a in enumerate(soup.find_all("a", href=True), 1):
        href = a.get("href")
        target = http_url(href, base)
        if target:
            links.append({"text": a.get_text(" ", strip=True), "url": target,
                          "href": href, "source_url": url, "title": title,
                          "rel": a.get("rel", []), "link_index": i})
    for i, link in enumerate(soup.find_all("link", href=True), 1):
        if "canonical" in [s.lower() for s in link.get("rel", [])]:
            add("canonical_url", link["href"], f"link[{i}][rel=canonical]@href")
    fields = {
        "og:title": "title", "twitter:title": "title", "og:url": "canonical_url",
        "author": "author", "article:author": "author", "citation_author": "author",
        "article:published_time": "published_at", "datepublished": "published_at",
        "citation_publication_date": "published_at", "pubdate": "published_at",
        "article:modified_time": "modified_at", "datemodified": "modified_at",
        "date": "date", "dc.date": "date", "dc.date.issued": "published_at",
    }
    for i, tag in enumerate(soup.find_all("meta"), 1):
        name = tag.get("property") or tag.get("name") or tag.get("itemprop") or ""
        field = fields.get(name.lower())
        if field:
            add(field, tag.get("content"), f"meta[{i}][{name}]@content")
    for i, tag in enumerate(soup.find_all("time"), 1):
        field = fields.get(str(tag.get("itemprop", "")).lower(), "date")
        add(field, tag.get("datetime") or tag.get_text(" ", strip=True), f"time[{i}]")

    errors = []
    for i, tag in enumerate(soup.find_all("script", type="application/ld+json"), 1):
        try:
            data = json.loads(tag.string or tag.get_text())
        except (ValueError, TypeError) as exc:
            errors.append({"source_url": url, "source": f"jsonld[{i}]", "error": str(exc)})
            continue
        pending = [(data, f"jsonld[{i}]")]
        while pending:
            obj, path = pending.pop()
            if isinstance(obj, list):
                pending.extend((v, f"{path}[{j}]") for j, v in reversed(list(enumerate(obj))))
            elif isinstance(obj, dict):
                entity = {k: obj[k] for k in ("@type", "@id") if k in obj}
                for key, field in (("headline", "title"), ("datePublished", "published_at"),
                                   ("dateModified", "modified_at")):
                    add(field, obj.get(key), f"{path}.{key}", entity=entity)
                authors = obj.get("author", [])
                for author in authors if isinstance(authors, list) else [authors]:
                    add("author", author.get("name") if isinstance(author, dict) else author,
                        f"{path}.author", entity=entity)
                for key, value in reversed(list(obj.items())):
                    if isinstance(value, (dict, list)):
                        pending.append((value, f"{path}.{key}"))
    return {"links": links, "metadata": metadata, "errors": errors}


def combine(parts, errors=()):
    return {"links": [r for p in parts for r in p["links"]],
            "metadata": [r for p in parts for r in p["metadata"]],
            "errors": [r for p in parts for r in p.get("errors", [])] + list(errors)}


def project(result, op):
    """같은 불변 수집 스냅샷에서 요청한 보기를 선택한다."""
    out = dict(result)
    structure = out.pop("_page_structure", None)
    out.pop("_structure_only", None)
    if not out.get("success") or op == "content":
        return out
    if structure is None:
        return {"success": False, "items": [], "url": out.get("url"),
                "reason": "structure_unavailable",
                "error": "이 수집 결과는 HTML 구조를 제공하지 않습니다(PDF 등). 본문은 op:content로 읽으세요.",
                "source_ref": out.get("source_ref")}
    out.pop("text", None)
    out.pop("length", None)
    out["op"] = op
    out["items"] = structure[op]
    out["count"] = len(out["items"])
    if structure.get("errors"):
        out["structure_errors"] = structure["errors"]
        out["partial"] = True
    return out
