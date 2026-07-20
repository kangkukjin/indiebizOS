"""창고 방언 어댑터 — indiebizOS 가 아닌 표면을 창고 매니페스트 통화로 정규화한다.

설계(2026-07-20, "파일 공유로 인터넷 재발명하기" 1순위 — 폴러 어댑터 층):
- 매니페스트가 우리 형식이어야만 이웃이 될 수 있다면 그건 도로가 아니라 또 하나의 기찻길.
  이미 인터넷에 존재하는 정적 목록들을 그대로 이웃으로 편입한다 — 상대가 아무것도
  설치하지 않아도 이웃이 된다(콜드 스타트 우회: 기존 웹이 창고망의 첫 이웃들).
- 지원 방언: native(indiebizOS /manifest) / autoindex_json(nginx autoindex_format json) /
  autoindex_html(nginx·Apache 디렉토리 목록) / rss(RSS·Atom, HTML 에서 자동발견 포함) /
  nextcloud(공개 공유 /s/<token> → WebDAV) / page(일반 웹페이지의 파일 링크).
- 폴러(warehouse_feed)는 어댑터가 뭘 읽었는지 모른다: 모든 방언이 같은 통화
  {title, files:[{name, mtime, bytes, url}], truncated} 로 정규화된다. AI·토큰 0 유지.
- 감지는 등록·복구 때 한 번(native → URL 모양 → 본문 냄새), 이후엔 poll_status.adapter
  캐시로 직행. 캐시 어댑터가 실패하면 재감지 폴백(상대가 표면을 바꿔도 자가 치유).
- truncated 의미(폴러 계약): 목록이 전체가 아닐 수 있다 → 사라진 파일의 삭제 판정 보류.
  RSS·page(최근 N개 창)와 캡에 걸린 크롤은 truncated=True — 스냅샷이 누적 아카이브가
  되어 검색 색인은 오히려 두터워진다.
- 인지 외골격 원칙: 여기는 순수 기계층. 어떤 창고를 이웃 삼을지는 사용자, 뭘 읽을지는
  읽는 쪽 AI 의 몫 — 어댑터는 방언을 통화로 바꿀 뿐 판단하지 않는다.
"""
import email.utils
import html as html_mod
import json
import re
import xml.etree.ElementTree as ET
from datetime import datetime
from typing import Dict, List, Optional, Tuple
from urllib.parse import quote, unquote, urljoin, urlparse

import requests

_TIMEOUT = 20
_UA = "indiebizOS-warehouse-feed/1.0"
_MAX_REQUESTS = 30            # 창고 하나 폴링당 HTTP 요청 상한 (디렉토리 재귀 포함)
_MAX_FILES = 2000
_MAX_DEPTH = 3                # 루트 아래로 내려가는 최대 깊이
_MAX_BODY = 3 * 1024 * 1024   # HTML/XML 본문 상한 — 그 이상은 목록이 아니라고 본다

ADAPTER_LABELS = {            # 표면(UI)용 짧은 한글 라벨
    "native": "창고",
    "autoindex_json": "색인(JSON)",
    "autoindex_html": "색인",
    "rss": "RSS",
    "nextcloud": "Nextcloud",
    "page": "페이지",
}


def adapter_label(adapter: Optional[str]) -> str:
    kind = (adapter or "native").split("|", 1)[0]
    return ADAPTER_LABELS.get(kind, kind)


def _get(url: str, **kw) -> requests.Response:
    r = requests.get(url, timeout=_TIMEOUT, headers={"User-Agent": _UA}, **kw)
    r.raise_for_status()
    return r


# ── 날짜·크기 정규화 ──────────────────────────────────────────────

def _iso(dt: datetime) -> str:
    if dt.tzinfo is not None:
        dt = dt.astimezone().replace(tzinfo=None)   # DB 는 로컬 naive 문자열 정렬
    return dt.isoformat(timespec="seconds")


def _date_iso(s: Optional[str]) -> str:
    """RFC822(RSS·WebDAV)·ISO(Atom)·목록 표기 등 아무 날짜나 ISO 로 — 실패하면 원문.

    diff 는 문자열 부등 비교라 형식이 흔들려도 동작하지만, 피드 정렬(mtime DESC)을
    위해 최대한 ISO 로 맞춘다."""
    s = (s or "").strip()
    if not s:
        return ""
    try:
        return _iso(email.utils.parsedate_to_datetime(s))
    except Exception:
        pass
    try:
        return _iso(datetime.fromisoformat(s.replace("Z", "+00:00")))
    except Exception:
        pass
    for fmt in ("%d-%b-%Y %H:%M", "%Y-%m-%d %H:%M", "%d-%b-%Y %H:%M:%S"):
        try:
            return _iso(datetime.strptime(s, fmt))
        except Exception:
            continue
    return s


def _human_bytes(s: Optional[str]) -> Optional[int]:
    s = (s or "").strip()
    if not s or s == "-":
        return None
    m = re.fullmatch(r"(\d+(?:\.\d+)?)\s*([KMGTP]?)(?:i?B)?", s, re.I)
    if not m:
        return None
    mult = {"": 1, "K": 1024, "M": 1024 ** 2, "G": 1024 ** 3,
            "T": 1024 ** 4, "P": 1024 ** 5}[m.group(2).upper()]
    return int(float(m.group(1)) * mult)


# ── native: indiebizOS /manifest ─────────────────────────────────

def _native(base: str) -> Dict:
    r = _get(base + "/manifest")
    data = r.json()
    if not isinstance(data, dict) or not isinstance(data.get("files"), list):
        raise ValueError("native 매니페스트 형식이 아님")
    return data


# ── 디렉토리 크롤 공통 골격 (autoindex·nextcloud) ─────────────────

def _crawl(list_dir, file_url) -> Dict:
    """list_dir(rel)->({files},{dirs},title) 를 너비우선으로 돌며 캡 안에서 목록을 모은다.

    rel 은 "" 또는 "sub/"·"sub/inner/" 꼴(사람이 읽는 원문 이름, 인코딩 전).
    루트 요청 실패는 감지 실패로 전파(raise), 하위 실패는 truncated 로만 남긴다."""
    files: List[Dict] = []
    queue: List[Tuple[str, int]] = [("", 0)]
    reqs = 0
    truncated = False
    title = ""
    while queue:
        rel, depth = queue.pop(0)
        if reqs >= _MAX_REQUESTS or len(files) >= _MAX_FILES:
            truncated = True
            break
        reqs += 1
        try:
            fs, ds, t = list_dir(rel)
        except Exception:
            if rel == "":
                raise
            truncated = True
            continue
        if not title and t:
            title = t
        for f in fs:
            if len(files) >= _MAX_FILES:
                truncated = True
                break
            name = rel + f["name"]
            files.append({"name": name, "mtime": f.get("mtime") or "",
                          "bytes": f.get("bytes"), "url": file_url(rel, f["name"])})
        for d in ds:
            if depth + 1 > _MAX_DEPTH:
                truncated = True
                continue
            queue.append((rel + d + "/", depth + 1))
    return {"title": title, "files": files, "truncated": truncated}


# ── autoindex (nginx autoindex_format json) ──────────────────────

def _autoindex_json(base: str) -> Dict:
    def list_dir(rel):
        data = _get(base + "/" + quote(rel)).json()
        if not isinstance(data, list):
            raise ValueError("autoindex JSON 아님")
        fs, ds = [], []
        for e in data:
            if not isinstance(e, dict) or not e.get("name"):
                continue
            if e.get("type") == "directory":
                ds.append(e["name"])
            else:
                fs.append({"name": e["name"], "mtime": _date_iso(e.get("mtime")),
                           "bytes": e.get("size")})
        return fs, ds, ""
    out = _crawl(list_dir, lambda rel, name: base + "/" + quote(rel + name))
    if not out["files"] and out["truncated"] is False:
        # 빈 목록 자체는 유효 — 단 루트가 JSON 리스트였음은 list_dir 이 보장한다
        pass
    return out


# ── autoindex (HTML 디렉토리 목록: nginx·Apache) ─────────────────

_A_RE = re.compile(r'<a\s[^>]*?href\s*=\s*["\']([^"\']+)["\'][^>]*>(.*?)</a>',
                   re.I | re.S)
_TITLE_RE = re.compile(r"<title[^>]*>(.*?)</title>", re.I | re.S)
_LISTING_DATE = re.compile(
    r"(\d{2}-[A-Za-z]{3}-\d{4} \d{2}:\d{2}(?::\d{2})?|\d{4}-\d{2}-\d{2}[ T]\d{2}:\d{2})")
_AFTER_SIZE = re.compile(r"[\s<>a-z=\"/]*?([\d.]+\s*[KMGTP]?i?B?|\d+|-)\s*(?:<|\n|$)", re.I)


def _looks_index(text: str) -> bool:
    head = text[:4096]
    return bool(re.search(r"<title>\s*Index of", head, re.I)) or \
        "Parent Directory" in text or \
        bool(re.search(r"<h1>\s*Index of", text, re.I))


def _page_title(text: str) -> str:
    m = _TITLE_RE.search(text)
    return html_mod.unescape(re.sub(r"\s+", " ", m.group(1))).strip() if m else ""


def _listing_anchors(text: str, page_url: str):
    """디렉토리 목록 페이지의 (한 단계) 항목 앵커들 → (href상대, 뒤따르는 원문 꼬리)."""
    page_path = urlparse(page_url).path
    ms = list(_A_RE.finditer(text))
    for i, m in enumerate(ms):
        href = html_mod.unescape(m.group(1)).strip()
        if href.startswith(("#", "mailto:", "javascript:", "data:")) or "?" in href:
            continue                      # Apache 정렬 링크(?C=N;O=D)·앵커 제외
        if href in ("../", "..", "/", "./"):
            continue
        if href.startswith(("http://", "https://")):
            absu = href
            pu = urlparse(absu)
            if pu.netloc != urlparse(page_url).netloc or not pu.path.startswith(page_path):
                continue
            href = pu.path[len(page_path):]
        elif href.startswith("/"):
            if not href.startswith(page_path):
                continue
            href = href[len(page_path):]
        if not href or "/" in href.rstrip("/"):
            continue                      # 한 단계 항목만 (하위는 재귀가 간다)
        tail = text[m.end(): ms[i + 1].start() if i + 1 < len(ms) else m.end() + 300]
        yield href, tail


def _autoindex_html(base: str) -> Dict:
    def list_dir(rel):
        r = _get(base + "/" + quote(rel))
        text = r.text[:_MAX_BODY]
        if not _looks_index(text):
            raise ValueError("디렉토리 목록 페이지가 아님")
        fs, ds = [], []
        for href, tail in _listing_anchors(text, r.url):
            if href.endswith("/"):
                ds.append(unquote(href[:-1]))
                continue
            mtime, size = "", None
            dm = _LISTING_DATE.search(tail)
            if dm:
                mtime = _date_iso(dm.group(1))
                sm = _AFTER_SIZE.match(tail[dm.end():])
                if sm:
                    size = _human_bytes(sm.group(1))
            fs.append({"name": unquote(href), "mtime": mtime, "bytes": size})
        return fs, ds, _page_title(text)
    return _crawl(list_dir, lambda rel, name: base + "/" + quote(rel + name))


# ── RSS / Atom ───────────────────────────────────────────────────

_BAD_NAME = re.compile(r'[\\/:*?"<>|\x00-\x1f]')


def _ln(el) -> str:
    return el.tag.rsplit("}", 1)[-1].lower() if isinstance(el.tag, str) else ""


def _child_text(el, *names) -> str:
    for ch in el:
        if _ln(ch) in names and (ch.text or "").strip():
            return ch.text.strip()
    return ""


def _rss(url: str) -> Dict:
    return _rss_parse(_get(url).content)


def _rss_parse(content: bytes) -> Dict:
    root = ET.fromstring(content)
    items = [el for el in root.iter() if _ln(el) in ("item", "entry")]
    # 피드 제목 = item 밖의 첫 title (rss: channel>title / atom: feed>title)
    title = ""
    for el in root.iter():
        if _ln(el) in ("item", "entry"):
            break
        if _ln(el) == "title" and (el.text or "").strip():
            title = el.text.strip()
            break
    files: List[Dict] = []
    used: Dict[str, int] = {}
    for it in items:
        link, enc_url, enc_len, date = "", "", None, ""
        for ch in it:
            l = _ln(ch)
            if l == "link":
                href = (ch.get("href") or "").strip()
                if href:
                    if ch.get("rel") in (None, "", "alternate") or not link:
                        link = href
                elif (ch.text or "").strip() and not link:
                    link = ch.text.strip()
            elif l == "enclosure":
                enc_url = (ch.get("url") or "").strip() or enc_url
                enc_len = enc_len or _human_bytes(ch.get("length"))
            elif l in ("pubdate", "published", "updated", "date") and not date:
                date = (ch.text or "").strip()
        furl = enc_url or link
        if not furl:
            continue
        name = _BAD_NAME.sub(" ", _child_text(it, "title")).strip()
        name = re.sub(r"\s+", " ", name)[:120] or unquote(
            urlparse(furl).path.rsplit("/", 1)[-1]) or "글"
        if name in used:                      # 같은 제목 → " (2)" 붙여 경로 충돌 방지
            used[name] += 1
            name = f"{name} ({used[name]})"
        else:
            used[name] = 1
        files.append({"name": name, "mtime": _date_iso(date),
                      "bytes": enc_len, "url": furl})
    if not files:
        raise ValueError("피드에 항목이 없음")
    return {"title": title, "files": files, "truncated": True}


def _discover_feed(text: str, page_url: str) -> str:
    """HTML <link rel=alternate type=rss/atom> 에서 피드 주소 자동발견."""
    for m in re.finditer(r"<link\s[^>]*>", text[:200_000], re.I):
        tag = m.group(0)
        if not re.search(r'rel=["\']?alternate', tag, re.I):
            continue
        if not re.search(r'type=["\']?application/(rss|atom)\+xml', tag, re.I):
            continue
        hm = re.search(r'href\s*=\s*["\']([^"\']+)["\']', tag, re.I)
        if hm:
            return urljoin(page_url, html_mod.unescape(hm.group(1)))
    return ""


# ── Nextcloud 공개 공유 (/s/<token> → WebDAV) ────────────────────

_NC_TOKEN = re.compile(r"/s/([A-Za-z0-9\-_]+)")


def _nextcloud(base: str) -> Dict:
    p = urlparse(base)
    m = _NC_TOKEN.search(p.path)
    if not m:
        raise ValueError("Nextcloud 공유 주소가 아님")
    token = m.group(1)
    origin = f"{p.scheme}://{p.netloc}"
    # 서브패스 설치(/nextcloud/…) 지원: /s/ 앞부분이 설치 루트
    install = p.path[: p.path.find("/s/")]
    dav = f"{origin}{install}/public.php/webdav"
    dav_path = urlparse(dav).path
    share = f"{origin}{p.path[: m.end()]}"

    def list_dir(rel):
        r = requests.request(
            "PROPFIND", dav + "/" + quote(rel), auth=(token, ""),
            headers={"Depth": "1", "User-Agent": _UA}, timeout=_TIMEOUT)
        if r.status_code >= 400:
            r.raise_for_status()
        root = ET.fromstring(r.content)
        fs, ds = [], []
        for resp in (el for el in root.iter() if _ln(el) == "response"):
            href = _child_text(resp, "href")
            rp = unquote(urlparse(href).path)
            if not rp.startswith(dav_path):
                continue
            entry = rp[len(dav_path):].strip("/")
            if entry == rel.strip("/"):
                continue                      # 폴더 자신
            name = entry[len(rel):].strip("/") if rel else entry
            if not name or "/" in name:
                continue
            is_dir = any(_ln(el) == "collection" for el in resp.iter())
            if is_dir:
                ds.append(name)
                continue
            mtime, size = "", None
            for el in resp.iter():
                if _ln(el) == "getlastmodified":
                    mtime = _date_iso(el.text)
                elif _ln(el) == "getcontentlength" and (el.text or "").isdigit():
                    size = int(el.text)
            fs.append({"name": name, "mtime": mtime, "bytes": size})
        return fs, ds, ""

    def file_url(rel, name):
        d = "/" + rel.strip("/") if rel.strip("/") else "/"
        return f"{share}/download?path={quote(d)}&files={quote(name)}"

    out = _crawl(list_dir, file_url)
    out["title"] = out["title"] or f"Nextcloud 공유 ({p.netloc})"
    return out


# ── page: 일반 웹페이지의 파일 링크 ──────────────────────────────

_EXT_RE = re.compile(r"\.([A-Za-z0-9]{1,8})$")
_PAGEY_EXT = {"html", "htm", "php", "asp", "aspx", "jsp"}


def _page(base: str) -> Dict:
    r = _get(base)
    return _page_parse(r.text[:_MAX_BODY], r.url)


def _page_parse(text: str, final_url: str) -> Dict:
    host = urlparse(final_url).netloc
    base_path = urlparse(final_url).path
    base_dir = base_path[: base_path.rfind("/") + 1] if "/" in base_path else "/"
    files: List[Dict] = []
    seen = set()
    for m in _A_RE.finditer(text):
        href = html_mod.unescape(m.group(1)).strip()
        if href.startswith(("#", "mailto:", "javascript:", "data:")):
            continue
        absu = urljoin(final_url, href)
        pu = urlparse(absu)
        if pu.scheme not in ("http", "https") or pu.query or pu.fragment:
            continue
        em = _EXT_RE.search(pu.path)
        if not em:
            continue                          # 확장자 있는 링크만 = "파일" 링크
        if pu.netloc != host and em.group(1).lower() in _PAGEY_EXT:
            continue                          # 딴 사이트의 문서 페이지는 파일이 아니다
        if absu.rstrip("/") == final_url.rstrip("/") or absu in seen:
            continue
        seen.add(absu)
        if pu.netloc == host and pu.path.startswith(base_dir):
            name = unquote(pu.path[len(base_dir):])
        else:
            name = pu.netloc + "/" + unquote(pu.path.rsplit("/", 1)[-1])
        files.append({"name": name, "mtime": "", "bytes": None, "url": absu})
        if len(files) >= _MAX_FILES:
            break
    if not files:
        raise ValueError("페이지에 파일 링크가 없음")
    return {"title": _page_title(text), "files": files, "truncated": True}


# ── 감지·디스패치 ────────────────────────────────────────────────

def _run(adapter: str, base: str) -> Dict:
    kind, _, arg = adapter.partition("|")
    if kind == "native":
        return _native(base)
    if kind == "autoindex_json":
        return _autoindex_json(base)
    if kind == "autoindex_html":
        return _autoindex_html(base)
    if kind == "rss":
        return _rss(arg or base)
    if kind == "nextcloud":
        return _nextcloud(base)
    if kind == "page":
        return _page(base)
    raise ValueError(f"모르는 어댑터: {adapter}")


def fetch_any(base: str, hint: Optional[str] = None) -> Tuple[Dict, str]:
    """주소 하나를 어떤 방언이든 매니페스트 통화로 — 반환 (manifest, adapter).

    hint = poll_status 에 캐시된 어댑터(빠른 길). 실패하면 전체 재감지(자가 치유).
    감지 순서: native → URL 모양(nextcloud) → 본문 냄새(JSON/피드XML/목록HTML/일반페이지).
    """
    if hint:
        try:
            return _run(hint, base), hint
        except Exception:
            pass                              # 표면이 바뀌었나 — 재감지로
    try:
        return _native(base), "native"
    except Exception:
        pass
    if _NC_TOKEN.search(urlparse(base).path):
        try:
            return _nextcloud(base), "nextcloud"
        except Exception:
            pass
    r = _get(base)                            # 여기 실패하면 폴러가 error 로 기록
    ct = (r.headers.get("content-type") or "").lower()
    text = r.text[:_MAX_BODY]
    stripped = text.lstrip()
    if "json" in ct or stripped[:1] in ("[", "{"):
        try:
            data = json.loads(stripped)
            if isinstance(data, dict) and isinstance(data.get("files"), list):
                return data, "native"          # 매니페스트 주소를 직접 등록한 경우
            if isinstance(data, list):
                return _autoindex_json(base), "autoindex_json"
        except Exception:
            pass
    if stripped.startswith("<?xml") or stripped[:100].lstrip().startswith(("<rss", "<feed")) \
            or "xml" in ct.split(";")[0]:
        try:
            return _rss_parse(r.content), "rss"
        except Exception:
            pass
    if _looks_index(text):
        try:
            return _autoindex_html(base), "autoindex_html"
        except Exception:
            pass
    feed = _discover_feed(text, r.url)
    if feed:
        try:
            return _rss(feed), f"rss|{feed}"
        except Exception:
            pass
    return _page_parse(text, r.url), "page"
