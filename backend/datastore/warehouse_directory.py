"""
warehouse_directory — 창고이웃 *후보*를 장르별로 둘러보는 층.

이웃찾기(#IndieNet 소개 노트)가 "나를 알린 사람"을 보는 수신면이라면, 여기는
**아직 아무 관계도 없는 창고**를 장르로 훑는 면이다. 방언 어댑터가 생긴 뒤로
세상에는 이미 창고가 아주 많다(색인·RSS·Neocities·페이지) — 다만 그걸 볼
방법이 없었다. 이 모듈이 그 목록을 만든다.

후보 출처는 둘뿐이고, 둘 다 *데이터*다(코드에 사이트 이름을 박지 않는다):

  ① live: `neocities:<tag>`  — Neocities 의 공개 태그 브라우즈를 요청 1회로 파싱.
     169만 사이트가 태그로 색인돼 있고 인증이 없다. 한 페이지 HTML 안에
     사이트 주소·제목·조회수·**썸네일**이 다 들어 있어 사이트당 추가 요청이 0.
  ② seed: 사람이 적어둔 목록 — `data/warehouse_directory.json` 의 seeds.
     기본값은 실측으로 살아있음을 확인한 공개 자료 창고들이고, 사용자가
     자유롭게 고치는 파일이다(설정이지 코드가 아니다).

여기서 나온 후보는 `/warehouse-feed/neighbors/add` 로 그대로 넘어간다 —
등록 경로는 이웃찾기와 완전히 같다(신규 배관 0).

★크롤러가 아니다: 사용자가 장르를 열 때만 1회 요청하고, 결과를 6시간 캐시한다.
"""
from __future__ import annotations

import json
import re
import time
from html import unescape
from pathlib import Path
from common.value_semantics import values_equal
from typing import Dict, List, Optional
from urllib.parse import urljoin

import requests

DATA_DIR = Path(__file__).parent.parent.parent / "data"
CATALOG_PATH = DATA_DIR / "warehouse_directory.json"
CACHE_PATH = DATA_DIR / "warehouse_directory_cache.json"

_TIMEOUT = 20
# Neocities 브라우즈는 브라우저 UA 를 안 주면 응답이 달라질 수 있다(실측: 기본 UA 도
# 200 이지만, 공개 페이지를 사람이 보는 것과 같은 모양으로 받기 위해 명시).
_UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
       "(KHTML, like Gecko) Chrome/124.0 Safari/537.36")
_CACHE_TTL = 6 * 3600          # 장르 한 칸당 재요청 간격
_NEO_BROWSE = "https://neocities.org/browse"

# ── 기본 카탈로그 ────────────────────────────────────────────────
# neocities 태그는 실측으로 결과가 나오는 것만 넣는다. seeds 는 조사에서 직접
# 접속해 살아있음을 확인한 공개 창고들(2026-07 기준) — 사용자가 지우고 자기
# 목록으로 바꿔도 되는 출발점이다.
_DEFAULT_CATALOG: Dict = {
    "genres": [
        {"key": "personal", "label": "개인 홈페이지", "icon": "🏠",
         "hint": "자기 이야기를 스스로 짓는 사람들 — 옛 개인 홈페이지의 직계",
         "neocities_tag": "personal"},
        {"key": "art", "label": "예술·그림", "icon": "🎨",
         "hint": "그림·일러스트·창작물을 쌓아두는 창고",
         "neocities_tag": "art"},
        {"key": "writing", "label": "글·일기", "icon": "✍️",
         "hint": "블로그·일기·에세이. RSS 주소를 직접 등록해도 창고가 됩니다",
         "neocities_tag": "blog"},
        {"key": "music", "label": "음악", "icon": "🎵",
         "hint": "음악을 모으거나 만드는 창고",
         "neocities_tag": "music"},
        {"key": "game", "label": "게임", "icon": "🕹️",
         "hint": "게임 자료·팬사이트·직접 만든 게임",
         "neocities_tag": "videogames"},
        {"key": "photo", "label": "사진", "icon": "📷",
         "hint": "사진 아카이브",
         "neocities_tag": "photography"},
        {"key": "tech", "label": "기술·코드", "icon": "💻",
         "hint": "프로그래밍·자작 도구",
         "neocities_tag": "programming"},
        {"key": "archive", "label": "자료·아카이브", "icon": "📚",
         "hint": "옛 FTP 자료실의 현대판 — 디렉토리 색인을 그대로 읽어옵니다. "
                 "★미러의 '루트'는 대개 안내 페이지라 창고가 못 됩니다. 실제 색인 폴더를 가리키세요",
         "seeds": [
             {"name": "카카오 미러 · ubuntu", "url": "https://mirror.kakao.com/ubuntu/",
              "desc": "국내 최대 오픈소스 미러 (카카오 운영)"},
             {"name": "KAIST 거울 · 한글자료", "url": "http://ftp.kaist.ac.kr/hangul/",
              "desc": "학부 동아리 SPARCS 가 운영하는 72TiB 미러의 한글 자료 구획"},
             {"name": "mirror.siwoo.org", "url": "https://mirror.siwoo.org/archlinux/",
              "desc": "개인이 운영하는 20TB 미러 (광주, ROKFOSS 참여)"},
             {"name": "distly", "url": "https://mirror.distly.kr/archlinux/",
              "desc": "비영리 개인 미러 · Arch Linux 공식 Tier 2 (전남·광주)"},
             {"name": "GNU 아카이브", "url": "https://ftp.gnu.org/gnu/",
              "desc": "GNU 프로젝트 원본 배포처 — 지금도 FTP 포트가 열려 있는 몇 안 되는 곳"},
             {"name": "ibiblio", "url": "https://ibiblio.org/pub/",
              "desc": "1992년 SunSITE 이래의 공개 서고 — 개인이 기증한 컬렉션이 산다"},
             {"name": "FUNET", "url": "https://ftp.funet.fi/pub/",
              "desc": "핀란드 학술망 아카이브 — 리눅스가 처음 올라갔던 곳"},
         ]},
    ]
}


def _load_json(path: Path, default):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default


def _catalog() -> Dict:
    """카탈로그를 읽는다. 없으면 기본값을 파일로 굳혀 사용자가 고칠 수 있게 한다."""
    if not CATALOG_PATH.exists():
        try:
            DATA_DIR.mkdir(parents=True, exist_ok=True)
            CATALOG_PATH.write_text(
                json.dumps(_DEFAULT_CATALOG, ensure_ascii=False, indent=2),
                encoding="utf-8")
        except Exception:
            pass
        return _DEFAULT_CATALOG
    cat = _load_json(CATALOG_PATH, None)
    if not isinstance(cat, dict) or not isinstance(cat.get("genres"), list):
        return _DEFAULT_CATALOG
    return cat


def list_genres() -> List[Dict]:
    """장르 칩 목록. 각 칸이 어디서 오는지(live/seed)를 표면이 알 수 있게 표시."""
    out = []
    for g in _catalog().get("genres", []):
        if not isinstance(g, dict) or not g.get("key"):
            continue
        out.append({
            "key": g["key"],
            "label": g.get("label") or g["key"],
            "icon": g.get("icon") or "📦",
            "hint": g.get("hint") or "",
            "live": bool(g.get("neocities_tag")),
            "seed_count": len(g.get("seeds") or []),
        })
    return out


def _genre(key: str) -> Optional[Dict]:
    for g in _catalog().get("genres", []):
        if isinstance(g, dict) and g.get("key") == key:
            return g
    return None


# ── Neocities 태그 브라우즈 파싱 ─────────────────────────────────
# 한 사이트 = <li id="username_<이름>"> … </li> 블록. 그 안에:
#   <a href="<사이트 주소>" class="neo-Screen-Shot" title="<제목>">   ← 커스텀 도메인도 여기 그대로
#   background:url(/site_screenshots/…webp)                          ← 썸네일
#   <div class="site-stats…"> … <i class="fa fa-eye"></i> … 58,817,401  ← 조회수
# 사이트당 추가 요청이 0이라는 게 이 파싱의 요점(/api/info 를 100번 부르지 않는다).
_LI = re.compile(r'<li\s+id="username_([A-Za-z0-9][A-Za-z0-9\-_]*)"(.*?)</li>', re.S | re.I)
_HREF = re.compile(r'<a\s+href="(https?://[^"]+)"\s*\n?\s*class="neo-Screen-Shot"', re.I)
_TITLE = re.compile(r'class="neo-Screen-Shot"\s*\n?\s*title="([^"]*)"', re.I)
_SHOT = re.compile(r'background:\s*url\(([^)]+)\)', re.I)
_VIEWS = re.compile(r'fa-eye.*?</span>\s*([\d,]+)', re.S | re.I)
_TAGS = re.compile(r'href="/browse\?tag=([A-Za-z0-9]+)"', re.I)


def _neocities_tag(tag: str, limit: int) -> List[Dict]:
    r = requests.get(_NEO_BROWSE, params={"tag": tag, "sort_by": "views"},
                     headers={"User-Agent": _UA}, timeout=_TIMEOUT)
    r.raise_for_status()
    items: List[Dict] = []
    for name, block in _LI.findall(r.text):
        mh = _HREF.search(block)
        url = mh.group(1) if mh else f"https://{name}.neocities.org"
        mt = _TITLE.search(block)
        title = unescape(mt.group(1)).strip() if mt else name
        ms = _SHOT.search(block)
        thumb = urljoin("https://neocities.org/", ms.group(1).strip("'\" ")) if ms else ""
        mv = _VIEWS.search(block)
        views = int(mv.group(1).replace(",", "")) if mv else None
        tags = [t for t in _TAGS.findall(block) if not values_equal(t, tag)][:4]
        items.append({
            "name": name,
            "url": url.rstrip("/"),
            "title": title or name,
            "desc": (", ".join(tags) if tags else ""),
            "thumb": thumb,
            "views": views,
            "source": "neocities",
            # 등록할 때 그대로 넘길 어댑터 힌트. 커스텀 도메인(ita.toys 등)은 호스트로
            # 자동 감지가 안 돼 'page' 로 떨어지는데, 브라우즈에서 이미 사이트명을
            # 알고 왔으므로 여기서 정체를 박아 보낸다.
            "adapter": f"neocities|{name}",
        })
        if len(items) >= limit:
            break
    return items


# ── 캐시 ────────────────────────────────────────────────────────

def _cache_get(key: str) -> Optional[Dict]:
    c = _load_json(CACHE_PATH, {})
    e = c.get(key) if isinstance(c, dict) else None
    if isinstance(e, dict) and (time.time() - float(e.get("at") or 0)) < _CACHE_TTL:
        return e
    return None


def _cache_put(key: str, items: List[Dict]) -> None:
    c = _load_json(CACHE_PATH, {})
    if not isinstance(c, dict):
        c = {}
    c[key] = {"at": time.time(), "items": items}
    try:
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        CACHE_PATH.write_text(json.dumps(c, ensure_ascii=False), encoding="utf-8")
    except Exception:
        pass


def candidates(key: str, limit: int = 60, refresh: bool = False) -> Dict:
    """한 장르의 후보 창고 목록. seeds 가 위, live 가 아래(사람이 고른 것 먼저).

    live 요청이 실패해도 seeds 는 그대로 돌려준다 — 남의 사이트가 죽었다고
    이 화면이 통째로 비면 안 된다. 실패는 note 로만 알린다.
    """
    g = _genre(key)
    if not g:
        return {"items": [], "error": "그런 장르가 없어요"}

    items: List[Dict] = []
    for s in (g.get("seeds") or []):
        if not isinstance(s, dict) or not s.get("url"):
            continue
        items.append({
            "name": s.get("name") or s["url"],
            "url": str(s["url"]).rstrip("/"),
            "title": s.get("name") or "",
            "desc": s.get("desc") or "",
            "thumb": "", "views": None, "source": "seed",
        })

    note = ""
    cached_at = None
    tag = g.get("neocities_tag")
    if tag:
        room = max(0, limit - len(items))
        hit = None if refresh else _cache_get(key)
        if hit:
            items += (hit.get("items") or [])[:room]
            cached_at = hit.get("at")
        elif room:
            try:
                live = _neocities_tag(str(tag), room)
                _cache_put(key, live)
                items += live
                cached_at = time.time()
            except Exception as e:
                stale = _load_json(CACHE_PATH, {}).get(key) if CACHE_PATH.exists() else None
                if isinstance(stale, dict) and stale.get("items"):
                    items += (stale["items"] or [])[:room]   # 묵은 거라도 보여준다
                    cached_at = stale.get("at")
                    note = f"Neocities 목록을 새로 못 받아 예전 것을 보여드려요 ({e})"
                else:
                    note = f"Neocities 목록을 못 받았어요 ({e})"
    return {"items": items[:limit], "note": note, "cached_at": cached_at}
