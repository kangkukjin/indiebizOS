"""페이지의 링크·메타정보를 원문 근거와 함께 추출한다. 모델 호출·날짜 추정 없음."""
import json
import re
from collections import Counter
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
    from common.pkg_utils import load_sibling
    body = load_sibling(__file__, "webcrawl_body").selection(html)
    return {"links": links, "metadata": metadata, "errors": errors,
            "content_selections": [{**body, "url": url}],
            "documents": [{"html": html, "url": url}]}


def _pdf_date(raw):
    """PDF 정보 사전의 D:YYYYMMDDHHmmSS+HH'mm' 을 ISO 로. 못 읽으면 None — 만들어내지 않는다."""
    m = re.match(r"D:(\d{4})(\d{2})(\d{2})(\d{2})?(\d{2})?(\d{2})?([+\-Z])?(\d{2})?'?(\d{2})?", str(raw or ""))
    if not m:
        return None
    y, mo, d, h, mi, s, sign, oh, om = m.groups()
    try:
        stamp = datetime(int(y), int(mo), int(d), int(h or 0), int(mi or 0), int(s or 0)).isoformat()
    except ValueError:
        return None
    if sign in ("+", "-") and oh:
        return f"{stamp}{sign}{oh}:{om or '00'}"
    return stamp + "+00:00" if sign == "Z" else stamp


def first_page_heading(page):
    """첫 쪽에서 본문(최빈 글꼴 크기)보다 확연히 큰 최대 글꼴 줄 묶음. 없으면 None — 추정하지 않는다.

    HTML 의 <h1> 에 해당하는 관측이다. 글꼴이 한 크기뿐인 문서(편지·원장)는 제목을 내지 않는다.
    """
    lines = []
    for block in page.get_text("dict").get("blocks", []):
        for line in block.get("lines", []):
            spans = line.get("spans") or []
            text = "".join(str(s.get("text", "")) for s in spans).strip()
            if text and spans:
                lines.append((max(round(float(s.get("size", 0)), 1) for s in spans), text))
    if len(lines) < 2:
        return None
    body = Counter(size for size, _ in lines).most_common(1)[0][0]
    top = max(size for size, _ in lines)
    if top < body * 1.15:
        return None
    text = " ".join([t for size, t in lines if size == top][:6])
    return {"text": text, "size": top} if 3 <= len(text) <= 300 else None


def extract_pdf(path, url, info=None):
    """PDF 의 메타정보·링크를 HTML 과 같은 관측 행으로 낸다. 파일명은 제목으로 내지 않는다.

    제목 관측은 두 가지를 각각 근거를 달아 낸다: 내장 정보(pdf.info.title — "Microsoft Word - 문서1"
    같은 값이 흔하다)와 첫 쪽의 최대 글꼴 줄(pdf.page[1].largest_font). 우선순위는 읽는 쪽이 정한다.
    2026-10-04: EADV 보도자료 PDF 는 내장 제목이 비어 crawl 이 파일명을 제목으로 냈고, 뉴스 작업은
    구조 없음으로 32회 연속 실패했다.
    """
    import fitz
    info = info or {}
    links, metadata, errors = [], [], []
    heading = None
    doc = None
    try:
        doc = fitz.open(path)
        if doc.page_count:
            heading = first_page_heading(doc[0])
    except Exception as exc:
        errors.append({"source_url": url, "source": "pdf", "error": str(exc)})
    title = str(info.get("title") or "").strip() or (heading or {}).get("text", "")

    def add(field, raw, source, normalized=None):
        raw = "" if raw is None else str(raw).strip()
        if not raw:
            return
        row = {"field": field, "value": raw, "raw": raw, "source": source,
               "source_url": url, "url": url, "title": title}
        if field in {"published_at", "modified_at", "date"}:
            row["normalized"] = normalized
        metadata.append(row)

    if heading:
        add("title", heading["text"], f"pdf.page[1].largest_font({heading['size']:g}pt)")
    add("title", info.get("title"), "pdf.info.title")
    add("author", info.get("author"), "pdf.info.author")
    add("date", info.get("creationDate"), "pdf.info.creationDate", _pdf_date(info.get("creationDate")))
    add("modified_at", info.get("modDate"), "pdf.info.modDate", _pdf_date(info.get("modDate")))
    if doc is not None:
        try:
            for pno, page in enumerate(doc, 1):
                for link in page.get_links():
                    href = link.get("uri")
                    target = http_url(href, url)
                    if not target:
                        continue
                    rect = link.get("from")
                    text = page.get_textbox(rect).strip() if rect is not None else ""
                    links.append({"text": " ".join(text.split()), "url": target, "href": href,
                                  "source_url": url, "title": title, "rel": [],
                                  "link_index": len(links) + 1, "page": pno})
        except Exception as exc:
            errors.append({"source_url": url, "source": "pdf.links", "error": str(exc)})
        finally:
            doc.close()
    return {"links": links, "metadata": metadata, "errors": errors,
            "content_selections": [], "documents": [], "title": title}


def combine(parts, errors=()):
    return {"content_selections": [r for p in parts for r in p.get("content_selections", [])],
            "documents": [r for p in parts for r in p.get("documents", [])],
            "links": [r for p in parts for r in p["links"]],
            "metadata": [r for p in parts for r in p["metadata"]],
            "errors": [r for p in parts for r in p.get("errors", [])] + list(errors)}


def project(result, op):
    """같은 불변 수집 스냅샷에서 요청한 보기를 선택한다."""
    out = dict(result)
    structure = out.pop("_page_structure", None)
    selections = out.pop("_content_selection", None)
    out.pop("_structure_only", None)
    if not out.get("success") or op == "content":
        if selections is not None:
            out["content_selection"] = selections
        elif structure and structure.get("content_selections"):
            out["content_selection"] = structure["content_selections"]
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
