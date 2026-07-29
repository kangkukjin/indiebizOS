"""창고 방언 어댑터 — indiebizOS 가 아닌 표면을 창고 매니페스트 통화로 정규화한다.

설계(2026-07-20, "파일 공유로 인터넷 재발명하기" 1순위 — 폴러 어댑터 층):
- 매니페스트가 우리 형식이어야만 이웃이 될 수 있다면 그건 도로가 아니라 또 하나의 기찻길.
  이미 인터넷에 존재하는 정적 목록들을 그대로 이웃으로 편입한다 — 상대가 아무것도
  설치하지 않아도 이웃이 된다(콜드 스타트 우회: 기존 웹이 창고망의 첫 이웃들).
- 지원 방언: native(indiebizOS /manifest) / autoindex_json(nginx autoindex_format json) /
  autoindex_html(nginx·Apache 디렉토리 목록) / rss(RSS·Atom, HTML 에서 자동발견 포함) /
  nextcloud(공개 공유 /s/<token> → WebDAV) / neocities(공개 프로필 업데이트 이벤트) /
  page(일반 웹페이지의 파일 링크).
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
    "neocities": "Neocities",
    "page": "페이지",
}


def adapter_label(adapter: Optional[str]) -> str:
    kind = (adapter or "native").split("|", 1)[0]
    return ADAPTER_LABELS.get(kind, kind)


def _get(url: str, **kw) -> requests.Response:
    r = requests.get(url, timeout=_TIMEOUT, headers={"User-Agent": _UA}, **kw)
    r.raise_for_status()
    if r.encoding and "charset" not in (r.headers.get("content-type") or "").lower():
        # 헤더에 charset 이 없으면 requests 는 text/* 를 ISO-8859-1 로 읽는다 →
        # <meta charset> 을 먼저 존중한다. 안 그러면 제목·파일명이 모지바케가 되고
        # (실측: 'â\x96· ESPY.WORLD') euc-kr 한글 페이지는 통째로 깨진다.
        m = re.search(rb'charset\s*=\s*["\']?([A-Za-z0-9_\-]+)', r.content[:4096], re.I)
        r.encoding = (m.group(1).decode("ascii", "ignore") if m
                      else r.apparent_encoding) or r.encoding
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

def _native(base: str, cookies: Optional[Dict] = None) -> Dict:
    # cookies = 회원 세션(pk) — 창고 주인이 나를 승급했으면 매니페스트가 내 레벨로 열린다.
    # 로그인은 native 창고만의 개념이라 다른 방언은 쿠키를 받지 않는다.
    r = _get(base + "/manifest", cookies=cookies)
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
    """HTML <link rel=alternate type=rss/atom> 에서 피드 주소 자동발견.

    스캔 창 3MB — 옛 200KB 는 유튜브 채널(HTML 1.4MB, rss link 태그가 ~700KB 지점)
    같은 거대 페이지에서 실존 태그를 놓쳤다(2026-07-28 실측). 정규식은 link 태그만
    훑으므로 MB 단위 텍스트도 ms 급."""
    for m in re.finditer(r"<link\s[^>]*>", text[:3_000_000], re.I):
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


# ── Neocities (공개 프로필 업데이트 이벤트 + 사이트 루트 링크) ───

# Neocities 는 남의 사이트 파일 목록 API 를 열지 않는다(/api/list 는 그 사이트 자신의
# 키 필요, 폴더 요청은 404 — 실측 2026-07-29). 대신 공개된 두 창이 있다:
#   ① /api/info?sitename= (무인증) — 커스텀 도메인·최종수정·태그
#   ② /site/<이름> 프로필의 "updated their site" 이벤트 — 갱신된 파일의 실제 URL + 시각
# ②가 곧 그 사이트의 변경 피드다(RSS 와 같은 성질: 최근 창 → truncated=True).
# 여기에 사이트 루트의 링크를 얹어 첫 폴링부터 사이트의 페이지들이 색인되게 한다.
# mtime 은 이벤트에서만 온다 — 루트 링크에 사이트 last_updated 를 찍으면 사이트가
# 한 번 갱신될 때마다 전 파일이 changed 로 요동친다.

_NEO_HOST = re.compile(r"^([A-Za-z0-9][A-Za-z0-9\-]*)\.neocities\.org$", re.I)
_NEO_PROFILE = re.compile(r"^/site/([A-Za-z0-9][A-Za-z0-9\-_]*)/?$", re.I)
_NEO_BADGE = re.compile(r"neocities\.org/site/([A-Za-z0-9][A-Za-z0-9\-_]*)", re.I)
_NEO_SELF = re.compile(r"\b([A-Za-z0-9][A-Za-z0-9\-]*)\.neocities\.org", re.I)
_NEO_ITEM = re.compile(r'<div\s+class="news-item\s+([a-z_]+)"', re.I)
_NEO_TS = re.compile(r'data-timestamp="(\d+)"')
_NEO_FILES = re.compile(r'class="files"(.*?)(?:class="actions"|\Z)', re.I | re.S)
_NEO_HREF = re.compile(r'href\s*=\s*["\']([^"\']+)["\']', re.I)
_NEO_API = "https://neocities.org/api/info"
_NEO_SITE = "https://neocities.org/site/"
_NEO_BADGE_TRIES = 3          # 배지가 여럿인 페이지에서 확인 API 남발 방지


def _neo_norm_host(h: str) -> str:
    h = (h or "").lower().split(":")[0]
    return h[4:] if h.startswith("www.") else h


def _neo_info(name: str) -> Dict:
    """공개 사이트 정보 — 없는 사이트면 400 이라 예외로 걸러진다."""
    data = _get(f"{_NEO_API}?sitename={quote(name)}").json()
    if not isinstance(data, dict) or data.get("result") != "success":
        raise ValueError(f"Neocities 사이트가 아님: {name}")
    return data.get("info") or {}


def _neo_base(name: str, info: Dict) -> str:
    """그 사이트의 정식 주소 — 커스텀 도메인을 쓰면 프로필의 파일 링크도 그쪽이다."""
    domain = (info.get("domain") or "").strip()
    return f"https://{domain}" if domain else f"https://{name}.neocities.org"


def _neo_name(url: str, site_base: str) -> str:
    """파일 URL → 사이트 루트 기준 경로. 루트·디렉토리는 index.html 로 접는다."""
    if not url.startswith(site_base):
        return ""
    rel = unquote(url[len(site_base):].split("?")[0].split("#")[0]).lstrip("/")
    if not rel or rel.endswith("/"):
        rel += "index.html"
    return rel


def _neo_events(name: str, site_base: str) -> List[Dict]:
    """프로필의 update 이벤트 → 파일들. 페이지가 최신순이라 첫 등장이 최신 mtime."""
    text = _get(_NEO_SITE + quote(name)).text[:_MAX_BODY]
    marks = list(_NEO_ITEM.finditer(text))
    out: List[Dict] = []
    for i, m in enumerate(marks):
        if m.group(1).lower() != "update":
            continue                          # comment·follow 는 파일 변화가 아니다
        end = marks[i + 1].start() if i + 1 < len(marks) else len(text)
        chunk = text[m.end():end]
        tm = _NEO_TS.search(chunk)
        mtime = _iso(datetime.fromtimestamp(int(tm.group(1)))) if tm else ""
        fb = _NEO_FILES.search(chunk)
        if not fb:
            continue
        for hm in _NEO_HREF.finditer(fb.group(1)):
            url = urljoin(site_base + "/", html_mod.unescape(hm.group(1)).strip())
            fname = _neo_name(url, site_base)
            if fname:
                out.append({"name": fname, "mtime": mtime, "bytes": None, "url": url})
    return out


def _neocities(name: str) -> Dict:
    info = _neo_info(name)
    site_base = _neo_base(name, info)
    files: Dict[str, Dict] = {}
    try:
        for f in _neo_events(name, site_base):
            files.setdefault(f["name"], f)    # 최신 이벤트 우선
    except Exception:
        pass                                  # 프로필이 막혀도 사이트 링크로 창고는 선다
    title = ""
    try:
        r = _get(site_base + "/")
        text = r.text[:_MAX_BODY]
        title = _page_title(text)
        try:
            for f in _page_parse(text, r.url)["files"]:
                if f["url"].startswith(site_base):
                    files.setdefault(f["name"], f)   # 이벤트가 있으면 그 mtime 을 지킨다
        except Exception:
            pass                              # 링크 없는 한 장짜리 사이트도 정상
    except Exception:
        pass                                  # 사이트가 잠깐 죽어도 이벤트 목록은 산다
    return {"title": title or f"{name} (Neocities)",
            "files": list(files.values()), "truncated": True}


def _neo_sitename(base: str) -> str:
    """등록 주소가 Neocities 사이트를 가리키면 사이트 이름 — 아니면 ""."""
    p = urlparse(base)
    host = _neo_norm_host(p.netloc)
    path = p.path or "/"
    if host == "neocities.org":
        m = _NEO_PROFILE.match(path)          # 프로필 주소를 그대로 등록한 경우
        return m.group(1) if m else ""
    if path.strip("/") == "":                 # 루트만 — 깊은 주소는 사용자 의도를 존중
        m = _NEO_HOST.match(p.netloc.split(":")[0])
        if m and m.group(1).lower() != "www":
            return m.group(1)
    return ""


def _neo_candidates(text: str, host: str) -> List[str]:
    """커스텀 도메인 페이지에서 사이트 이름 후보 — 문서 순서대로, 중복 제거.

    ① 도메인 첫 라벨(plasticdino.net → plasticdino) — 대개 사이트 이름과 같다.
    ② 본문의 neocities.org/site/<이름> 배지.
    ③ 본문의 <이름>.neocities.org 자기참조 — 커스텀 도메인을 써도 서브도메인은 남아
       있어 사이트가 자기 파일을 그 주소로 부르는 일이 흔하다(실측 plasticdino).
    ②③ 에는 웹링·친구 배지로 남의 이름이 잔뜩 섞이므로, 채택은 반드시 API 대조로."""
    out: List[str] = []
    seen = set()

    def add(c):
        c = (c or "").strip().lower()
        if c and c != "www" and c not in seen:
            seen.add(c)
            out.append(c)

    add(host.split(".")[0])
    body = text[:_MAX_BODY]
    for m in _NEO_BADGE.finditer(body):
        add(m.group(1))
    for m in _NEO_SELF.finditer(body):
        add(m.group(1))
    return out[:_NEO_BADGE_TRIES]


def _neo_from_page(text: str, page_url: str) -> str:
    """커스텀 도메인 사이트 — 후보를 API 로 대조해 확인(추측만으로 채택하지 않는다)."""
    host = _neo_norm_host(urlparse(page_url).netloc)
    for cand in _neo_candidates(text, host):
        try:
            info = _neo_info(cand)
        except Exception:
            continue
        if _neo_norm_host(info.get("domain") or "") == host:
            return cand                       # 그 사이트가 이 도메인을 자기 것이라 선언
    return ""


# ── 감지·디스패치 ────────────────────────────────────────────────

def _run(adapter: str, base: str, cookies: Optional[Dict] = None) -> Dict:
    kind, _, arg = adapter.partition("|")
    if kind == "native":
        return _native(base, cookies=cookies)
    if kind == "autoindex_json":
        return _autoindex_json(base)
    if kind == "autoindex_html":
        return _autoindex_html(base)
    if kind == "rss":
        return _rss(arg or base)
    if kind == "nextcloud":
        return _nextcloud(base)
    if kind == "neocities":
        return _neocities(arg or _neo_sitename(base))
    if kind == "page":
        return _page(base)
    raise ValueError(f"모르는 어댑터: {adapter}")


def fetch_any(base: str, hint: Optional[str] = None,
              cookies: Optional[Dict] = None) -> Tuple[Dict, str]:
    """주소 하나를 어떤 방언이든 매니페스트 통화로 — 반환 (manifest, adapter).

    hint = poll_status 에 캐시된 어댑터(빠른 길). 실패하면 전체 재감지(자가 치유).
    감지 순서: native → URL 모양(nextcloud) → 본문 냄새(JSON/피드XML/목록HTML/일반페이지).
    cookies = native 회원 세션(pk). 본문 냄새 감지 경로는 익명으로 두어도 된다 —
    다음 폴링부터 hint=native 로 쿠키가 실린다.
    """
    if hint:
        try:
            return _run(hint, base, cookies=cookies), hint
        except Exception:
            pass                              # 표면이 바뀌었나 — 재감지로
    try:
        return _native(base, cookies=cookies), "native"
    except Exception:
        pass
    if _NC_TOKEN.search(urlparse(base).path):
        try:
            return _nextcloud(base), "nextcloud"
        except Exception:
            pass
    neo = _neo_sitename(base)
    if neo:
        try:
            return _neocities(neo), f"neocities|{neo}"
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
    # 커스텀 도메인 Neocities — 주인이 피드를 선언했으면 그쪽이 먼저다(위에서 잡힌다).
    neo = _neo_from_page(text, r.url)
    if neo:
        try:
            return _neocities(neo), f"neocities|{neo}"
        except Exception:
            pass
    return _page_parse(text, r.url), "page"
