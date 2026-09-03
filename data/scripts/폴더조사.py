"""폴더 조사 — 지명된 폴더를 예산 안에서 관측해 골격·아이템 목록·조사 원장을 남긴다.

정본 설계: docs/FOLDER_SURVEY_HANDOFF.md (2026-09-03).
이 스크립트는 **관측만** 한다 — 축·겹침·예외·죽은 가지 같은 *판단*은 AI 가 report.md 를 읽고
`[self:forage]{op:"note"}` 로 적는다(forager=AI). 조사 = 예산 안의 투영: 상위 축척은 자식 폴더마다
한 줄(골격), 아이템 축척은 파일마다 속성(items.json). 예산과 실사용은 조사 원장(survey 표)에 남아
"이 폴더는 아직 거칠다"를 다음 AI 가 안다.

args(stdin JSON):
  op: survey(기본) | items | status | dictionary
  survey: path(필수) · depth(골격 보고 깊이, 기본 2) · items(auto|true|false — 아이템 목록까지)
          · parse(auto|media|plain) · body(생략=자동: /Volumes/<라벨>→disk:<라벨>, 그 외 몸 profile)
          · budget{dirs(기본 4000), files(기본 20000), items(기본 5000), sample(자식당 예시 이름 수, 기본 6)}
  items:  path(조사한 폴더 또는 그 하위) · q(제목·이름 부분일치) · where{필드:값} · limit(기본 50)
  status: body(선택) → 조사 원장 + 신선도
stdout: {"items":[...], ...} 통화.
"""
import json
import os
import re
import sys
import time
import unicodedata
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))
import boot_paths  # noqa: E402  층 디렉토리 sys.path
boot_paths.install()
import forage_memory  # noqa: E402
from runtime_utils import detect_body, expand_body_path  # noqa: E402

ARTIFACT_ROOT = ROOT / "data" / "forage_surveys"
NOISE_DIRS = frozenset(("node_modules", "__pycache__", ".git", ".venv", "venv", ".cache",
                        "$RECYCLE.BIN", "System Volume Information", ".Spotlight-V100",
                        ".fseventsd", ".Trashes", ".TemporaryItems"))
EXT_KIND = {
    **{e: "video" for e in (".mp4", ".mkv", ".avi", ".mov", ".m4v", ".webm", ".wmv", ".flv", ".ts", ".mpg", ".mpeg")},
    **{e: "audio" for e in (".mp3", ".m4a", ".flac", ".wav", ".aac", ".ogg", ".wma")},
    **{e: "image" for e in (".jpg", ".jpeg", ".png", ".heic", ".heif", ".gif", ".tiff", ".webp", ".bmp", ".raw", ".cr2", ".nef")},
    **{e: "subtitle" for e in (".srt", ".smi", ".ass", ".ssa", ".sub", ".idx", ".vtt")},
    **{e: "doc" for e in (".pdf", ".doc", ".docx", ".hwp", ".hwpx", ".ppt", ".pptx", ".xls", ".xlsx", ".txt", ".md", ".rtf", ".epub", ".pages", ".key", ".numbers")},
    **{e: "archive" for e in (".zip", ".rar", ".7z", ".tar", ".gz", ".dmg", ".iso")},
    **{e: "code" for e in (".py", ".js", ".ts", ".tsx", ".html", ".css", ".json", ".yaml", ".yml", ".sh", ".c", ".cpp", ".java", ".ipynb")},
    ".nfo": "meta", ".torrent": "meta", ".url": "meta", ".DS_Store": "meta",
}
YEAR_RE = re.compile(r"(?<!\d)((?:19|20)\d{2})(?!\d)")
PART_RE = re.compile(r"(?i)\b(?:cd|part|disc|disk)\s*[\-_.]?\s*(\d{1,2})\b|\((\d)\)$")
QUALITY_TOKENS = {"720p", "1080p", "2160p", "4k", "480p", "x264", "x265", "h264", "h265", "hevc",
                  "bluray", "brrip", "bdrip", "dvdrip", "webrip", "web-dl", "webdl", "hdrip", "hdtv",
                  "xvid", "divx", "ac3", "aac", "dts", "aac2", "5.1", "hd", "uhd", "remux", "proper",
                  "repack", "extended", "unrated", "dc", "ntsc", "pal", "kor", "eng", "sub", "dub"}
HANGUL_RE = re.compile(r"[가-힣]")
LATIN_RE = re.compile(r"[A-Za-z]")


def _kind(name: str) -> str:
    return EXT_KIND.get(os.path.splitext(name)[1].lower(), "other")


def _auto_body(path: str) -> str:
    m = re.match(r"^/Volumes/([^/]+)", path)
    if m:
        return f"disk:{m.group(1)}"
    return detect_body().get("profile") or "pc"


def _slug(path: str) -> str:
    s = re.sub(r"[^\w가-힣]+", "_", path.strip("/")).strip("_")
    return s[-80:] or "root"


# ---------------------------------------------------------------- 걷기(예산 안)
def walk(root: str, budget: dict):
    """예산 안 os.walk. 반환: dirs{relpath: {files:[names], subdirs:[names], mtime}} , truncated."""
    dirs, n_files, truncated = {}, 0, False
    for cur, subdirs, files in os.walk(root):
        # ★NFC 정규화 — APFS 는 한글 이름을 NFD(자모 분해)로 돌려줘 [가-힣] 이 한 글자도 안 맞는다(실측)
        subdirs[:] = sorted(unicodedata.normalize("NFC", d) for d in subdirs
                            if d not in NOISE_DIRS and not d.startswith("."))
        files = [unicodedata.normalize("NFC", f) for f in files if not f.startswith(".")]
        rel = unicodedata.normalize("NFC", os.path.relpath(cur, root))
        rel = "" if rel == "." else rel
        try:
            mt = os.stat(cur).st_mtime
        except OSError:
            mt = 0.0
        dirs[rel] = {"files": sorted(files), "subdirs": list(subdirs), "mtime": mt}
        n_files += len(files)
        if len(dirs) >= budget["dirs"] or n_files >= budget["files"]:
            truncated = True
            subdirs[:] = []
            break
    return dirs, n_files, truncated


def _subtree(dirs: dict, rel: str):
    """rel 아래(자기 포함) 디렉토리 항목들."""
    pre = rel + os.sep if rel else ""
    return {k: v for k, v in dirs.items() if k == rel or (k.startswith(pre) if rel else True)}


def _pick_samples(names, k):
    if len(names) <= k:
        return list(names)
    step = max(1, len(names) // k)
    return [names[i] for i in range(0, len(names), step)][:k]


def summarize_node(root: str, dirs: dict, rel: str, sample_k: int) -> dict:
    sub = _subtree(dirs, rel)
    files = [(d, f) for d, v in sub.items() for f in v["files"]]
    kinds = Counter(_kind(f) for _, f in files)
    names = [f for _, f in files if _kind(f) not in ("meta", "subtitle")]  # 명명 힌트는 주 파일 기준
    years = [int(m.group(1)) for f in names for m in [YEAR_RE.search(f)] if m]
    mtimes = [v["mtime"] for v in sub.values() if v["mtime"]]
    n_sub = sum(len(v["subdirs"]) for v in sub.values())
    # 명명 힌트(싼 L1 추론)
    n = max(1, len(names))
    hints = {
        "year_in_name": round(sum(1 for f in names if YEAR_RE.search(f)) / n, 2),
        "bracket_tag": round(sum(1 for f in names if "[" in f or "(" in f) / n, 2),
        "hangul": round(sum(1 for f in names if HANGUL_RE.search(f)) / n, 2),
        "latin": round(sum(1 for f in names if LATIN_RE.search(f)) / n, 2),
        "multipart": sum(1 for f in names if PART_RE.search(os.path.splitext(f)[0])),
    }
    # 아이템 폴더 비율: 직계 자식 폴더 중 '주 파일 1개(+부속)' 꼴
    own = dirs.get(rel, {"subdirs": []})
    item_folders = 0
    for c in own["subdirs"]:
        crel = os.path.join(rel, c) if rel else c
        cf = dirs.get(crel, {}).get("files", [])
        mains = [f for f in cf if _kind(f) in ("video", "audio", "doc", "image", "archive", "other")]
        # 잎 폴더(하위 없음)에 주 파일 소수 = 아이템 하나(영화·시리즈·앨범) — 구조가 아니라 내용
        if 1 <= len(mains) <= 8 and not dirs.get(crel, {}).get("subdirs"):
            item_folders += 1
    return {
        "name": os.path.basename(rel) if rel else os.path.basename(root.rstrip(os.sep)),
        "rel": rel,
        "files": len(files), "subdirs": n_sub, "direct_subdirs": len(own["subdirs"]),
        "item_folder_ratio": round(item_folders / max(1, len(own["subdirs"])), 2) if own["subdirs"] else 0.0,
        "kinds": dict(kinds.most_common()),
        "years_in_names": [min(years), max(years)] if years else None,
        "mtime_span": [time.strftime("%Y-%m", time.localtime(min(mtimes))),
                       time.strftime("%Y-%m", time.localtime(max(mtimes)))] if mtimes else None,
        "naming": hints,
        "sample_dirs": _pick_samples(own["subdirs"], sample_k),
        "sample_files": _pick_samples([f for f in own["files"] if _kind(f) != "meta"], sample_k),
    }


# ---------------------------------------------------------------- 아이템 파싱
RELEASE_TAG_RE = re.compile(r"^(?:(?i:cd|part|disc|disk)\d{0,2}|[A-Z0-9]{2,6}|\S*\d\S*[A-Za-z]\S*|\S*[A-Za-z]\S*\d\S*|\S+-[A-Z0-9]{2,12})$")


def _clean_title(s: str, before_year: bool = False) -> str:
    """파일명 → 제목 후보. 괄호 태그·연도·화질/코덱·릴리스 그룹(대문자 약어·숫자섞임·-GROUP)을 걷어낸다.
    before_year=True 면 첫 연도 앞까지만(릴 이름은 '제목.연도.태그들' 순이 관례)."""
    s = re.sub(r"[\[\(][^\]\)]*[\]\)]", " ", s)          # 괄호 태그 제거
    s = s.replace(".", " ").replace("_", " ")
    toks = s.split()
    if before_year:
        for i, t in enumerate(toks):
            if YEAR_RE.fullmatch(t):
                toks = toks[:i]; break
    out = []
    for t in toks:
        if YEAR_RE.fullmatch(t) or t.lower().strip("-") in QUALITY_TOKENS:
            continue
        if HANGUL_RE.search(t):
            out.append(t); continue
        if RELEASE_TAG_RE.match(t) and not (t.isalpha() and t[0].isupper() and t[1:].islower()):
            continue  # 릴리스 태그(WAF·AC3·x264·1CH·-KTH). 보통 영단어(Blood·The)는 남긴다
        out.append(t)
    return re.sub(r"\s+", " ", " ".join(out)).strip(" -")


def parse_media(root: str, dirs: dict, rel_dir: str, fname: str) -> dict:
    stem, ext = os.path.splitext(fname)
    folder_files = dirs[rel_dir]["files"]
    parent = os.path.basename(rel_dir) if rel_dir else ""
    top = rel_dir.split(os.sep)[0] if rel_dir else ""
    # 아이템 폴더(주 파일 1~2개)면 폴더 이름이 한글 제목의 1순위
    mains = [f for f in folder_files if _kind(f) == "video"]
    item_folder = rel_dir and 1 <= len(mains) <= 2 and not dirs[rel_dir]["subdirs"]
    tags = re.findall(r"[\[\(]([^\]\)]+)[\]\)]", stem + " " + (parent if item_folder else ""))
    year = None
    for src in (stem, parent):
        m = YEAR_RE.search(src)
        if m:
            year = int(m.group(1)); break
    part = None
    pm = PART_RE.search(stem)
    if pm:
        part = int(pm.group(1) or pm.group(2))
    ko_src = parent if (item_folder and HANGUL_RE.search(parent)) else stem
    ko = " ".join(t for t in _clean_title(ko_src).split() if HANGUL_RE.search(t) or not LATIN_RE.search(t))
    en = " ".join(t for t in _clean_title(stem, before_year=True).split() if LATIN_RE.search(t) and not HANGUL_RE.search(t))
    if not en:  # 연도 앞에 영어가 없으면(한글 제목 뒤 원제) 전체에서 다시
        en = " ".join(t for t in _clean_title(stem).split() if LATIN_RE.search(t) and not HANGUL_RE.search(t))
    subs = [f for f in folder_files if _kind(f) == "subtitle" and os.path.splitext(f)[0].lower().startswith(stem.lower()[:8])]
    subs = subs or [f for f in folder_files if _kind(f) == "subtitle"]
    full = os.path.join(root, rel_dir, fname)
    try:
        st = os.stat(full); size_mb = round(st.st_size / 1048576); mtime = time.strftime("%Y-%m-%d", time.localtime(st.st_mtime))
    except OSError:
        size_mb, mtime = None, None
    return {"title": ko or en or stem, "title_ko": ko or None, "title_en": en or None, "year": year,
            "category": top, "folder": rel_dir, "file": fname, "ext": ext.lower().lstrip("."),
            "part": part, "tags": tags[:6], "has_subtitle": bool(subs), "size_mb": size_mb,
            "mtime": mtime, "path": full}


def parse_plain(root: str, dirs: dict, rel_dir: str, fname: str) -> dict:
    stem, ext = os.path.splitext(fname)
    full = os.path.join(root, rel_dir, fname)
    try:
        st = os.stat(full); size_mb = round(st.st_size / 1048576, 1); mtime = time.strftime("%Y-%m-%d", time.localtime(st.st_mtime))
    except OSError:
        size_mb, mtime = None, None
    m = YEAR_RE.search(stem)
    return {"title": stem, "year": int(m.group(1)) if m else None, "kind": _kind(fname),
            "category": rel_dir.split(os.sep)[0] if rel_dir else "", "folder": rel_dir, "file": fname,
            "ext": ext.lower().lstrip("."), "size_mb": size_mb, "mtime": mtime, "path": full}


# ---------------------------------------------------------------- 보고서
def render_report(root: str, body: str, nodes: list, n_files: int, n_dirs: int, spent: dict,
                  truncated: bool, items_n: int, parse: str) -> str:
    L = [f"# 폴더 조사 보고 — {root}", "",
         f"몸 {body} · 디렉토리 {n_dirs} · 파일 {n_files} · 아이템 목록 {items_n}({parse}) · "
         f"소요 {spent.get('seconds')}s" + (" · ★예산 초과로 잘림" if truncated else ""), "",
         "이 보고는 관측이다. 판단(분할의 축·겹치는 축·명명 관습·예외·죽은 가지·기질·주제어)은 AI 가 읽고 "
         "`[self:forage]{op:\"note\"}` 로 적는다.", ""]
    rootn = nodes[0]
    L += [f"## 루트: 직계 하위 {rootn['direct_subdirs']} · 종류 {rootn['kinds']} · 이름 연도 {rootn['years_in_names']} · 명명 {rootn['naming']}", ""]
    L += ["## 자식 폴더 (골격)", "", "| 폴더 | 파일 | 하위 | 아이템폴더비 | 종류 | 이름연도 | 수정시각 | 예시 |", "|---|---|---|---|---|---|---|---|"]
    for nd in nodes[1:]:
        ex = "; ".join((nd["sample_dirs"] or nd["sample_files"])[:4])
        L.append(f"| {nd['rel']} | {nd['files']} | {nd['subdirs']} | {nd['item_folder_ratio']} | "
                 f"{', '.join(f'{k}{v}' for k, v in list(nd['kinds'].items())[:3])} | "
                 f"{'~'.join(map(str, nd['years_in_names'])) if nd['years_in_names'] else ''} | "
                 f"{'~'.join(nd['mtime_span']) if nd['mtime_span'] else ''} | {ex} |")
    return "\n".join(L) + "\n"


# ---------------------------------------------------------------- op
def op_survey(a: dict) -> dict:
    path = a.get("path")
    if not path:
        return {"success": False, "error": "path 가 필요합니다"}
    root = os.path.abspath(expand_body_path(str(path)))
    if not os.path.isdir(root):
        return {"success": False, "error": f"폴더가 없거나 마운트되지 않았습니다: {root}"}
    depth = int(a.get("depth") or 2)
    budget = {"dirs": 4000, "files": 20000, "items": 5000, "sample": 6}
    budget.update({k: int(v) for k, v in (a.get("budget") or {}).items() if k in budget})
    body = a.get("body") or _auto_body(root)
    t0 = time.time()
    dirs, n_files, truncated = walk(root, budget)
    # 골격: 루트 + depth 까지의 노드
    rels = sorted(r for r in dirs if r and r.count(os.sep) < depth)
    nodes = [summarize_node(root, dirs, "", budget["sample"])]
    item_parents = set()
    for r in rels:
        parent = os.path.dirname(r)
        if parent in item_parents:
            continue  # 부모가 '아이템 폴더 모음'이면 자식은 구조가 아니라 아이템 — 골격에 안 올린다
        nd = summarize_node(root, dirs, r, budget["sample"])
        nodes.append(nd)
        if nd["item_folder_ratio"] >= 0.6:
            item_parents.add(r)
    # 아이템 축척 결정
    kinds_total = Counter()
    for v in dirs.values():
        kinds_total.update(_kind(f) for f in v["files"])
    want_items = a.get("items", "auto")
    if isinstance(want_items, str):  # 계기(select)는 문자열로 보낸다 — "false" 가 참이 되던 함정
        want_items = {"auto": "auto", "true": True, "false": False}.get(want_items.strip().lower(), "auto")
    do_items = (n_files <= budget["items"]) if want_items == "auto" else bool(want_items)
    parse = a.get("parse", "auto")
    if parse == "auto":
        parse = "media" if (kinds_total.get("video", 0) + kinds_total.get("audio", 0)) >= 0.3 * max(1, n_files - kinds_total.get("subtitle", 0) - kinds_total.get("meta", 0)) else "plain"
    items = []
    if do_items:
        for rel, v in dirs.items():
            for f in v["files"]:
                k = _kind(f)
                if k in ("meta", "subtitle"):
                    continue
                if parse == "media" and k not in ("video", "audio"):
                    continue
                items.append(parse_media(root, dirs, rel, f) if parse == "media" else parse_plain(root, dirs, rel, f))
                if len(items) >= budget["items"]:
                    truncated = True; break
            if len(items) >= budget["items"]:
                break
        items.sort(key=lambda x: (x.get("category") or "", x.get("title") or ""))
    spent = {"dirs": len(dirs), "files": n_files, "items": len(items), "seconds": round(time.time() - t0, 1)}
    art = ARTIFACT_ROOT / _slug(root)
    art.mkdir(parents=True, exist_ok=True)
    (art / "skeleton.json").write_text(json.dumps({"root": root, "body": body, "depth": depth, "nodes": nodes,
                                                   "kinds_total": dict(kinds_total), "truncated": truncated,
                                                   "surveyed_at": time.strftime("%Y-%m-%dT%H:%M:%S")}, ensure_ascii=False, indent=1), encoding="utf-8")
    if do_items:
        (art / "items.json").write_text(json.dumps(items, ensure_ascii=False, indent=0), encoding="utf-8")
    report = render_report(root, body, nodes, n_files, len(dirs), spent, truncated, len(items), parse if do_items else "없음")
    (art / "report.md").write_text(report, encoding="utf-8")
    led = forage_memory.record_survey(body=body, locus=root, depth=depth, budget=budget, spent=spent,
                                      item_resolution=do_items, artifact_dir=str(art), truncated=truncated)
    return {"success": True, "survey_id": led.get("id"), "body": body, "locus": root, "spent": spent,
            "truncated": truncated, "item_resolution": do_items, "parse": parse if do_items else None,
            "artifact_dir": str(art), "report": report[:12000],
            "items": [{"title": nd["rel"] or "(루트)", "files": nd["files"], "subdirs": nd["subdirs"],
                       "kinds": nd["kinds"], "years": nd["years_in_names"], "samples": (nd["sample_dirs"] or nd["sample_files"])[:4]}
                      for nd in nodes]}


def op_items(a: dict) -> dict:
    path = a.get("path")
    if not path:
        return {"success": False, "error": "path 가 필요합니다(조사한 폴더 또는 그 하위)"}
    p = os.path.abspath(expand_body_path(str(path)))
    sv = forage_memory.survey_covering(p)
    if not sv or not sv.get("item_resolution"):
        return {"success": False, "error": f"이 경로를 아이템 축척으로 조사한 원장이 없습니다: {p} — op:survey 먼저", "items": []}
    ipath = Path(sv["artifact_dir"]) / "items.json"
    if not ipath.exists():
        return {"success": False, "error": f"items.json 없음: {ipath}", "items": []}
    items = json.loads(ipath.read_text(encoding="utf-8"))
    if p != sv["locus"]:
        items = [it for it in items if it["path"].startswith(p + os.sep) or it["path"] == p]
    q = str(a.get("q") or "").strip().lower()
    if q:
        items = [it for it in items if any(q in str(it.get(k) or "").lower() for k in ("title", "title_ko", "title_en", "file", "folder", "tags"))]
    for k, v in (a.get("where") or {}).items():
        if isinstance(v, bool) or v is None or isinstance(v, (int, float)):
            items = [it for it in items if it.get(k) == v]
        else:
            vs = str(v).lower()
            items = [it for it in items if vs in str(it.get(k) or "").lower()]
    limit = int(a.get("limit") or 50)
    return {"success": True, "survey_locus": sv["locus"], "surveyed_at": sv["surveyed_at"],
            "freshness": sv["freshness"], "total": len(items), "items": items[:limit]}


def op_dictionary(a: dict) -> dict:
    """사전(dictionary.md) 읽기 — 계기의 편집 폼용. 쓰기는 [self:write]{path:"{dictionary}"} 로(있는 동사)."""
    path = a.get("path")
    if not path:
        return {"success": False, "error": "path 가 필요합니다"}
    p = os.path.abspath(expand_body_path(str(path)))
    sv = forage_memory.survey_covering(p)
    if not sv:
        return {"success": False, "error": f"조사 원장에 없는 폴더입니다: {p} — op:survey 먼저"}
    art = Path(sv["artifact_dir"] or "")
    dpath, rpath = art / "dictionary.md", art / "report.md"
    content = dpath.read_text(encoding="utf-8") if dpath.exists() else ""
    if not content:
        content = (f"# 폴더 조사 사전 — {sv['locus']}\n\n(AI 판단 요청 전이거나 아직 비어 있습니다. "
                   f"report.md 를 읽고 축·겹침·예외·죽은 가지·기질·주제어를 적으세요.)\n")
    # items 통화를 실어야 스크립트 실행기가 나머지 키(content·dictionary…)도 결과에 합친다(script_ops 승격 규칙)
    return {"success": True, "locus": sv["locus"], "dictionary": str(dpath), "report": str(rpath),
            "exists": dpath.exists(), "content": content, "surveyed_at": sv["surveyed_at"],
            "freshness": sv["freshness"] or "fresh",
            "items": [{"title": sv["locus"], "meta": f"{sv['surveyed_at']} · 사전 {'있음' if dpath.exists() else '없음'} · {sv['freshness'] or 'fresh'}",
                       "dictionary": str(dpath), "report": str(rpath)}]}


def op_status(a: dict) -> dict:
    rows = forage_memory.list_surveys(body=a.get("body"))
    items = []
    for r in rows:
        art = r.get("artifact_dir") or ""
        sp = r.get("spent") or {}
        items.append({"title": r["locus"], "body": r["body"], "surveyed_at": r["surveyed_at"],
                      "depth": r["depth"], "item_resolution": bool(r["item_resolution"]),
                      "spent": sp, "freshness": r["freshness"] or "fresh", "truncated": bool(r["truncated"]),
                      # 계기(앱)가 드릴로 여는 산출물 경로 — 없으면 빈 문자열
                      "artifact_dir": art,
                      "report": os.path.join(art, "report.md") if art else "",
                      "dictionary": os.path.join(art, "dictionary.md") if art else "",
                      "meta": f"{r['surveyed_at']} · 깊이 {r['depth']} · {'아이템 ' + str(sp.get('items', 0)) + '편' if r['item_resolution'] else '골격만'} · {r['freshness'] or 'fresh'}"})
    return {"success": True, "items": items}


def main():
    try:
        args = json.loads(sys.stdin.read() or "{}")
    except Exception as e:
        print(json.dumps({"success": False, "error": f"args JSON 파싱 실패: {e}"}, ensure_ascii=False)); return
    op = (args.get("op") or "survey").strip()
    fn = {"survey": op_survey, "items": op_items, "status": op_status, "dictionary": op_dictionary}.get(op)
    if not fn:
        print(json.dumps({"success": False, "error": f"op 는 survey|items|status|dictionary (받음: {op})"}, ensure_ascii=False)); return
    print(json.dumps(fn(args), ensure_ascii=False))


if __name__ == "__main__":
    main()
