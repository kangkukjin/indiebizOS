"""music_core.py — 로컬 음악 라이브러리 코어 (music-player 패키지).

소스 폴더를 등록하면 그 안의 음악 파일을 스캔해 라이브러리(sqlite)로 정리한다.
태그(제목·아티스트·앨범·앨범아트)는 mutagen, 없으면 파일명·폴더명 폴백.
재생은 서버가 하지 않는다 — 보는 표면의 <audio>가 backend/api_music.py 의
/music/stream (Range) 을 직접 문다(라디오 client 모드와 같은 축).

저장 구조 (data/music/):
  sources.json    — 등록된 소스 폴더 목록 (photo scans.json 선례)
  library.db      — 트랙 인덱스 (sqlite WAL, 스캔 산출물 — 폴더가 진실)
  playlists.json  — 플레이리스트 (이름 + 트랙 경로 순서 목록)
  scan_state.json — 백그라운드 스캔 진행 상태 (family-news building 선례)
  covers/         — 앨범아트 캐시 (api_music 이 채움)

api_music.py 와 sys.modules 공유 키("indiebiz_music_core")로 같은 인스턴스를
쓴다(bulletin_core 선례 — 락·경로 검증 공유).
"""

import json
import os
import re
import sqlite3
import threading
import unicodedata
from datetime import datetime
from pathlib import Path
from urllib.parse import quote

_ROOT = Path(__file__).resolve().parents[5]
MUSIC_DIR = _ROOT / "data" / "music"
SOURCES_JSON = MUSIC_DIR / "sources.json"
PLAYLISTS_JSON = MUSIC_DIR / "playlists.json"
DB_PATH = MUSIC_DIR / "library.db"
SCAN_STATE_JSON = MUSIC_DIR / "scan_state.json"
COVERS_DIR = MUSIC_DIR / "covers"

AUDIO_EXTS = {".mp3", ".m4a", ".aac", ".flac", ".ogg", ".oga", ".opus", ".wav", ".aiff", ".aif", ".wma"}

_json_lock = threading.RLock()
_scan_lock = threading.Lock()          # 스캔 스레드 중복 기동 방지 (in-process)

try:
    from mutagen import File as _MutagenFile
except ImportError:                     # 미설치여도 파일명 폴백으로 동작 (PIL EXIF 선례)
    _MutagenFile = None


# ── 공용 유틸 ────────────────────────────────────────────────────────────

def norm_path(p: str) -> str:
    """macOS NFD → NFC 정규화 + 절대경로 (photo_db 선례 — 한글 경로 비교 필수)."""
    return unicodedata.normalize("NFC", os.path.abspath(os.path.expanduser(str(p or ""))))


def _now_iso() -> str:
    return datetime.now().isoformat(timespec="seconds")


def _load_json(path: Path, default):
    with _json_lock:
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            return default


def _save_json(path: Path, data) -> None:
    with _json_lock:
        MUSIC_DIR.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(path.suffix + ".tmp")
        tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        os.replace(tmp, path)


def fmt_duration(sec) -> str:
    try:
        s = int(round(float(sec or 0)))
    except (TypeError, ValueError):
        return ""
    if s <= 0:
        return ""
    if s >= 3600:
        return f"{s // 3600}:{(s % 3600) // 60:02d}:{s % 60:02d}"
    return f"{s // 60}:{s % 60:02d}"


# ── DB ──────────────────────────────────────────────────────────────────

def _conn() -> sqlite3.Connection:
    MUSIC_DIR.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(DB_PATH), timeout=30)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("""
        CREATE TABLE IF NOT EXISTS tracks (
            id INTEGER PRIMARY KEY,
            path TEXT UNIQUE NOT NULL,
            source TEXT NOT NULL,
            filename TEXT, ext TEXT, size INTEGER, mtime REAL,
            title TEXT, artist TEXT, album TEXT, albumartist TEXT,
            genre TEXT, year TEXT, track_no INTEGER, disc_no INTEGER,
            duration REAL, has_cover INTEGER DEFAULT 0,
            added_at TEXT
        )""")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_tracks_artist ON tracks(artist)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_tracks_album ON tracks(album)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_tracks_title ON tracks(title)")
    # 관련곡 그래프 — 곡마다 관련곡 top-K 간선(자기 제외). 스캔 산출물에서 파생(재빌드 가능).
    conn.execute("""
        CREATE TABLE IF NOT EXISTS edges (
            src TEXT NOT NULL, dst TEXT NOT NULL,
            weight REAL, reasons TEXT,
            PRIMARY KEY (src, dst)
        )""")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_edges_src ON edges(src)")
    return conn


# ── 소스 폴더 ────────────────────────────────────────────────────────────

def load_sources() -> list:
    return _load_json(SOURCES_JSON, {"sources": []}).get("sources", [])


def save_sources(sources: list) -> None:
    _save_json(SOURCES_JSON, {"sources": sources})


def add_source(path: str) -> dict:
    p = norm_path(path)
    if not os.path.isdir(p):
        return {"ok": False, "error": f"폴더가 없습니다: {p}"}
    sources = load_sources()
    if any(s["path"] == p for s in sources):
        return {"ok": False, "error": "이미 등록된 폴더입니다."}
    sources.append({"path": p, "added_at": _now_iso()})
    save_sources(sources)
    return {"ok": True, "path": p}


def remove_source(path: str) -> dict:
    p = norm_path(path)
    sources = load_sources()
    kept = [s for s in sources if s["path"] != p]
    if len(kept) == len(sources):
        return {"ok": False, "error": "등록되지 않은 폴더입니다."}
    save_sources(kept)
    with _conn() as conn:
        removed_paths = [r["path"] for r in conn.execute("SELECT path FROM tracks WHERE source = ?", (p,))]
        conn.execute("DELETE FROM tracks WHERE source = ?", (p,))
    if removed_paths:
        _strip_from_playlists(set(removed_paths))
        build_graph()   # 간선도 파생물 — 내려간 곡을 그래프에서 제거
    return {"ok": True, "path": p, "removed": len(removed_paths)}


def path_allowed(path: str) -> bool:
    """스트리밍 화이트리스트 — 등록된 소스 폴더 아래의 실존 파일만 (api_music 이 사용)."""
    p = os.path.realpath(norm_path(path))
    for s in load_sources():
        root = os.path.realpath(s["path"])
        if p == root or p.startswith(root + os.sep):
            return True
    return False


# ── 태그 추출 ────────────────────────────────────────────────────────────

def _looks_cjk(t: str) -> bool:
    return any("가" <= c <= "힣" or "぀" <= c <= "ヿ" or "一" <= c <= "鿿" for c in t)


def _fix_mojibake(s: str) -> str:
    """옛 한국·일본 mp3 ID3 태그 복원 — cp949/cp932/euc-jp 바이트를 latin-1/cp1252 로 읽은
    모지바케(¡¦Ã… 류)를 되돌린다. latin-1 표현 가능한 연속 구간(run) 단위로만 변환을
    시도해, 진짜 CJK(제목 속 神 등)와 섞여 있어도 깨진 구간만 복원. 채택 기준=복원 결과에
    CJK 등장, 또는 구두점-only 깨짐(¡¯→')은 원 구간에 고위문자 연쌍이 있고 복원 후 고위문자가
    사라졌을 때만 — 진짜 라틴 확장문자(Café)는 홀로 있는 고위문자라 무손상."""
    if not s or not any("\x80" <= ch <= "\xff" for ch in s):
        return s

    def _conv(m: "re.Match") -> str:
        seg = m.group(0)
        if not any("\x80" <= ch <= "\xff" for ch in seg):
            return seg
        adjacent_high = any("\x80" <= seg[i] <= "\xff" and "\x80" <= seg[i + 1] <= "\xff"
                            for i in range(len(seg) - 1))
        for back in ("latin-1", "cp1252"):
            try:
                b = seg.encode(back)
            except UnicodeEncodeError:
                continue
            for dec in ("cp949", "cp932", "euc_jp"):
                try:
                    fixed = b.decode(dec)
                except (UnicodeDecodeError, LookupError):
                    continue
                if _looks_cjk(fixed):
                    return fixed
                if adjacent_high and not any("\x80" <= c <= "\xff" for c in fixed):
                    return fixed
        return seg

    return re.sub(r"[\x20-\xff]+", _conv, s)


def _first(tags, key) -> str:
    try:
        v = tags.get(key)
        if isinstance(v, (list, tuple)):
            v = v[0] if v else None
        return _fix_mojibake(str(v).strip()) if v not in (None, "") else ""
    except Exception:
        return ""


def _int_of(s: str):
    m = re.match(r"\s*(\d+)", str(s or ""))
    return int(m.group(1)) if m else None


def extract_cover(path: str):
    """내장 앨범아트 bytes 반환 (없으면 None). ID3 APIC / FLAC pictures / MP4 covr / OGG 그림."""
    if _MutagenFile is None:
        return None
    try:
        audio = _MutagenFile(path)
        if audio is None:
            return None
        # FLAC / OGG-with-pictures
        pics = getattr(audio, "pictures", None)
        if pics:
            return bytes(pics[0].data)
        tags = audio.tags
        if tags is None:
            return None
        # MP3 (ID3 APIC)
        if hasattr(tags, "getall"):
            apics = tags.getall("APIC")
            if apics:
                return bytes(apics[0].data)
        # MP4 covr
        covr = tags.get("covr") if hasattr(tags, "get") else None
        if covr:
            return bytes(covr[0])
        # OGG Vorbis/Opus — base64 metadata_block_picture
        mbp = tags.get("metadata_block_picture") if hasattr(tags, "get") else None
        if mbp:
            import base64
            from mutagen.flac import Picture
            return bytes(Picture(base64.b64decode(mbp[0])).data)
    except Exception:
        pass
    return None


def extract_tags(path: str, source_root: str) -> dict:
    """한 파일의 태그 dict — mutagen 우선, 실패 시 '아티스트 - 제목' 파일명·폴더명 폴백."""
    st = os.stat(path)
    stem = Path(path).stem
    row = {
        "path": path, "source": source_root, "filename": os.path.basename(path),
        "ext": Path(path).suffix.lower().lstrip("."), "size": st.st_size, "mtime": st.st_mtime,
        "title": stem, "artist": "", "album": "", "albumartist": "",
        "genre": "", "year": "", "track_no": None, "disc_no": None,
        "duration": None, "has_cover": 0,
    }
    if _MutagenFile is not None:
        try:
            easy = _MutagenFile(path, easy=True)
            if easy is not None:
                if easy.tags:
                    row["title"] = _first(easy.tags, "title") or stem
                    row["artist"] = _first(easy.tags, "artist")
                    row["album"] = _first(easy.tags, "album")
                    row["albumartist"] = _first(easy.tags, "albumartist")
                    row["genre"] = _first(easy.tags, "genre")
                    row["year"] = (_first(easy.tags, "date") or "")[:4]
                    row["track_no"] = _int_of(_first(easy.tags, "tracknumber"))
                    row["disc_no"] = _int_of(_first(easy.tags, "discnumber"))
                info = getattr(easy, "info", None)
                if info is not None and getattr(info, "length", None):
                    row["duration"] = float(info.length)
            row["has_cover"] = 1 if extract_cover(path) else 0
        except Exception:
            pass
    # 폴백 — 태그 빈칸을 파일명("아티스트 - 제목")·폴더명(앨범)으로 채움
    if not row["artist"] and " - " in stem:
        head, tail = stem.split(" - ", 1)
        row["artist"], row["title"] = head.strip(), (row["title"] if row["title"] != stem else tail.strip())
    if not row["album"]:
        parent = Path(path).parent
        if norm_path(str(parent)) != source_root:
            row["album"] = parent.name
    return row


# ── 스캔 (백그라운드) ────────────────────────────────────────────────────

def scan_state() -> dict:
    return _load_json(SCAN_STATE_JSON, {})


def _set_scan_state(st: dict) -> None:
    _save_json(SCAN_STATE_JSON, {**st, "updated_at": _now_iso()})


def _walk_audio(root: str):
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if not d.startswith(".")]
        for fn in filenames:
            if fn.startswith("."):
                continue
            if Path(fn).suffix.lower() in AUDIO_EXTS:
                yield norm_path(os.path.join(dirpath, fn))


def _scan_source(conn: sqlite3.Connection, root: str, progress: dict) -> None:
    found = set()
    known = {r["path"]: (r["mtime"], r["size"]) for r in
             conn.execute("SELECT path, mtime, size FROM tracks WHERE source = ?", (root,))}
    for p in _walk_audio(root):
        found.add(p)
        progress["seen"] += 1
        try:
            st = os.stat(p)
        except OSError:
            continue
        old = known.get(p)
        if old and abs(old[0] - st.st_mtime) < 1 and old[1] == st.st_size:
            continue  # 변경 없음 — 증분 스킵
        row = extract_tags(p, root)
        conn.execute("""
            INSERT INTO tracks (path, source, filename, ext, size, mtime, title, artist, album,
                                albumartist, genre, year, track_no, disc_no, duration, has_cover, added_at)
            VALUES (:path, :source, :filename, :ext, :size, :mtime, :title, :artist, :album,
                    :albumartist, :genre, :year, :track_no, :disc_no, :duration, :has_cover, :added_at)
            ON CONFLICT(path) DO UPDATE SET
                source=:source, filename=:filename, ext=:ext, size=:size, mtime=:mtime,
                title=:title, artist=:artist, album=:album, albumartist=:albumartist,
                genre=:genre, year=:year, track_no=:track_no, disc_no=:disc_no,
                duration=:duration, has_cover=:has_cover
        """, {**row, "added_at": _now_iso()})
        progress["updated"] += 1
        if progress["updated"] % 50 == 0:
            conn.commit()
            _set_scan_state({"status": "scanning", **progress})
    # 사라진 파일 제거 (폴더가 진실)
    gone = set(known) - found
    if gone:
        conn.executemany("DELETE FROM tracks WHERE path = ?", [(p,) for p in gone])
        _strip_from_playlists(gone)
        progress["removed"] += len(gone)


def _scan_worker(roots: list) -> None:
    progress = {"seen": 0, "updated": 0, "removed": 0, "started_at": _now_iso()}
    try:
        conn = _conn()
        try:
            for root in roots:
                _scan_source(conn, root, progress)
                conn.commit()
        finally:
            conn.close()
        g = build_graph()   # 관련곡 그래프 재빌드 (파생물 — 스캔이 진실을 바꿨으니)
        _set_scan_state({"status": "done", **progress, "graph_edges": g.get("edges", 0),
                         "finished_at": _now_iso()})
    except Exception as e:
        _set_scan_state({"status": "error", **progress, "message": str(e)})
    finally:
        _scan_lock.release()


def start_scan(roots: list = None) -> dict:
    """백그라운드 스캔 기동 (도구 60초 제한 회피 — family-news create 선례). 중복 기동 방지."""
    roots = [norm_path(r) for r in (roots or [s["path"] for s in load_sources()])]
    if not roots:
        return {"ok": False, "error": "등록된 음악 폴더가 없습니다. 먼저 폴더를 등록하세요."}
    if not _scan_lock.acquire(blocking=False):
        return {"ok": False, "error": "이미 스캔이 진행 중입니다.", "scan": scan_state()}
    _set_scan_state({"status": "scanning", "seen": 0, "updated": 0, "removed": 0, "started_at": _now_iso()})
    threading.Thread(target=_scan_worker, args=(roots,), daemon=True).start()
    return {"ok": True, "queued": True, "roots": roots}


def scan_label() -> str:
    st = scan_state()
    status = st.get("status")
    if status == "scanning":
        return f"스캔 중 — {st.get('seen', 0)}개 확인, {st.get('updated', 0)}개 갱신"
    if status == "error":
        return f"스캔 오류: {st.get('message', '')}"
    if status == "done":
        return f"완료 ({st.get('finished_at', '')[:16]}) — {st.get('updated', 0)}개 갱신, {st.get('removed', 0)}개 제거"
    return "아직 스캔한 적 없음"


# ── 질의 ────────────────────────────────────────────────────────────────

def track_row(r) -> dict:
    """DB 행 → 통화 항목 (표시 필드 + 구조 필드 동시 탑재 — photo 선례. table 파이프 직결)."""
    d = dict(r)
    artist = d.get("artist") or ""
    album = d.get("album") or ""
    dur = fmt_duration(d.get("duration"))
    meta = " · ".join(x for x in (artist, album, dur) if x)
    q = quote(d["path"])
    return {
        "title": d.get("title") or d.get("filename") or "",
        "meta": meta,
        "artist": artist, "album": album, "albumartist": d.get("albumartist") or "",
        "genre": d.get("genre") or "", "year": d.get("year") or "",
        "track_no": d.get("track_no"), "duration": d.get("duration"),
        "duration_str": dur, "ext": d.get("ext") or "",
        "path": d["path"], "url": d["path"],
        "stream": f"/music/stream?path={q}",
        "image": f"/music/cover?path={q}",
    }


def query_tracks(q: str = "", artist: str = "", album: str = "", albumartist: str = "",
                 path: str = "", folder: str = "", limit: int = 300) -> list:
    where, args = [], []
    if path:
        where.append("path = ?"); args.append(norm_path(path))
    if folder:
        f = norm_path(folder)
        where.append("(path LIKE ? OR path = ?)"); args += [f + os.sep + "%", f]
    if q:
        where.append("(title LIKE ? OR artist LIKE ? OR album LIKE ? OR filename LIKE ?)")
        args += [f"%{q}%"] * 4
    if artist:
        where.append("artist = ?"); args.append(artist)
    if album:
        where.append("album = ?"); args.append(album)
    if albumartist:
        where.append("COALESCE(NULLIF(albumartist, ''), artist) = ?"); args.append(albumartist)
    sql = "SELECT * FROM tracks"
    if where:
        sql += " WHERE " + " AND ".join(where)
    sql += " ORDER BY album, disc_no, track_no, title LIMIT ?"
    args.append(max(1, min(int(limit or 300), 2000)))
    with _conn() as conn:
        return [track_row(r) for r in conn.execute(sql, args)]


def list_albums() -> list:
    sql = """
        SELECT album, COALESCE(NULLIF(albumartist, ''), artist) AS aartist,
               COUNT(*) AS n, SUM(COALESCE(duration, 0)) AS total_dur,
               MIN(path) AS any_path,
               MIN(CASE WHEN has_cover = 1 THEN path END) AS cover_path
        FROM tracks WHERE album != ''
        GROUP BY album, aartist ORDER BY aartist, album
    """
    rows = []
    with _conn() as conn:
        for r in conn.execute(sql):
            cover = r["cover_path"] or r["any_path"]
            rows.append({
                "title": r["album"], "album": r["album"],
                "artist": r["aartist"] or "", "albumartist": r["aartist"] or "",
                "n": r["n"], "duration_str": fmt_duration(r["total_dur"]),
                "meta": " · ".join(x for x in (r["aartist"], f"{r['n']}곡", fmt_duration(r["total_dur"])) if x),
                "image": f"/music/cover?path={quote(cover)}" if cover else "",
            })
    return rows


def list_artists() -> list:
    sql = """
        SELECT artist, COUNT(*) AS n, COUNT(DISTINCT NULLIF(album, '')) AS n_albums
        FROM tracks WHERE artist != '' GROUP BY artist ORDER BY artist
    """
    with _conn() as conn:
        return [{"title": r["artist"], "artist": r["artist"], "n": r["n"], "n_albums": r["n_albums"],
                 "meta": f"{r['n']}곡 · 앨범 {r['n_albums']}개"}
                for r in conn.execute(sql)]


def stats() -> dict:
    with _conn() as conn:
        tracks = conn.execute("SELECT COUNT(*) FROM tracks").fetchone()[0]
        albums = conn.execute("SELECT COUNT(DISTINCT album || '|' || COALESCE(NULLIF(albumartist,''), artist)) FROM tracks WHERE album != ''").fetchone()[0]
        artists = conn.execute("SELECT COUNT(DISTINCT artist) FROM tracks WHERE artist != ''").fetchone()[0]
        per_source = {r["source"]: r["n"] for r in conn.execute("SELECT source, COUNT(*) AS n FROM tracks GROUP BY source")}
    return {"tracks": tracks, "albums": albums, "artists": artists,
            "playlists": len(load_playlists()), "per_source": per_source}


# ── 폴더 ────────────────────────────────────────────────────────────────

def _rel_folder(dirpath: str) -> str:
    """폴더 표시명 — 소스 루트 기준 상대경로 (루트 자체는 소스 폴더명)."""
    for s in load_sources():
        root = s["path"]
        if dirpath == root:
            return os.path.basename(root) or root
        if dirpath.startswith(root + os.sep):
            return dirpath[len(root) + 1:]
    return dirpath


def list_folders() -> list:
    """곡을 직접 담은 폴더 목록 (폴더 구조=사용자의 의미 단위 — 폴더 단위 재생용)."""
    agg = {}
    with _conn() as conn:
        for r in conn.execute("SELECT path, duration FROM tracks"):
            d = os.path.dirname(r["path"])
            a = agg.setdefault(d, {"n": 0, "dur": 0.0})
            a["n"] += 1
            a["dur"] += r["duration"] or 0
    rows = []
    for d in sorted(agg):
        rel = _rel_folder(d)
        rows.append({
            "title": rel, "name": rel, "path": d,
            "n": agg[d]["n"], "duration_str": fmt_duration(agg[d]["dur"]),
            "meta": f"{agg[d]['n']}곡 · {fmt_duration(agg[d]['dur'])}",
        })
    return rows


# ── 관련곡 그래프 (Obsidian 로컬 그래프의 음악판) ────────────────────────
# 곡마다 관련곡 top-K 간선. 근거=같은 앨범/아티스트/폴더/장르/연대(가중 합산).
# 다양성 제약(같은 앨범·아티스트 쏠림 캡)으로 클러스터 밖 간선을 보장 — 랜덤 워크가
# 앨범 안에 갇히지 않게. 자기 간선 없음. 스캔 후 자동 재빌드(파생물).

GRAPH_TOP_K = 10
_W_ALBUM, _W_ARTIST, _W_FOLDER, _W_GENRE, _W_ERA = 4.0, 3.0, 2.5, 1.5, 1.0
_CAP_ALBUM, _CAP_ARTIST = 3, 5          # top-K 안에서 같은 앨범/아티스트 최대 수
_BIG_BUCKET_SAMPLE = 20                  # 대형 버킷(장르 등)은 곡마다 표본만 연결


def build_graph() -> dict:
    import random as _random
    from collections import defaultdict
    with _conn() as conn:
        tracks = [dict(r) for r in conn.execute(
            "SELECT path, artist, album, albumartist, genre, year FROM tracks")]
        if not tracks:
            conn.execute("DELETE FROM edges")
            return {"tracks": 0, "edges": 0}
        buckets = defaultdict(list)   # (종류, 키) → [path]
        info = {}
        for t in tracks:
            p = t["path"]
            info[p] = t
            aartist = (t["albumartist"] or t["artist"] or "").strip()
            if (t["album"] or "").strip():
                buckets[("album", (t["album"].strip(), aartist))].append(p)
            if (t["artist"] or "").strip():
                buckets[("artist", t["artist"].strip())].append(p)
            buckets[("folder", os.path.dirname(p))].append(p)
            if (t["genre"] or "").strip():
                buckets[("genre", t["genre"].strip().lower())].append(p)
            y = _int_of(t["year"] or "")
            if y:
                buckets[("era", y // 5)].append(p)
        weights = {"album": _W_ALBUM, "artist": _W_ARTIST, "folder": _W_FOLDER,
                   "genre": _W_GENRE, "era": _W_ERA}
        labels = {"album": "같은 앨범", "artist": "같은 아티스트", "folder": "같은 폴더",
                  "genre": "같은 장르", "era": "같은 연대"}
        cand = defaultdict(lambda: defaultdict(lambda: [0.0, set()]))  # src → dst → [score, kinds]
        for (kind, _key), members in buckets.items():
            if len(members) < 2:
                continue
            w = weights[kind]
            for p in members:
                # 대형 버킷은 곡마다 표본만 — O(bucket²) 폭발 방지 (곡 경로 시드=결정론)
                others = [m for m in members if m != p]
                if len(others) > _BIG_BUCKET_SAMPLE:
                    others = _random.Random(hash((p, kind))).sample(others, _BIG_BUCKET_SAMPLE)
                for m in others:
                    c = cand[p][m]
                    c[0] += w
                    c[1].add(kind)
        rows = []
        for src, dsts in cand.items():
            ranked = sorted(dsts.items(), key=lambda kv: (-kv[1][0], kv[0]))
            src_t = info[src]
            src_album = ((src_t["album"] or "").strip(),
                         (src_t["albumartist"] or src_t["artist"] or "").strip())
            n_album = n_artist = 0
            picked = []
            for dst, (score, kinds) in ranked:
                if len(picked) >= GRAPH_TOP_K:
                    break
                dst_t = info[dst]
                same_album = "album" in kinds and src_album[0]
                same_artist = (dst_t["artist"] or "").strip() == (src_t["artist"] or "").strip() and (src_t["artist"] or "").strip()
                if same_album and n_album >= _CAP_ALBUM:
                    continue
                if same_artist and n_artist >= _CAP_ARTIST:
                    continue
                if same_album:
                    n_album += 1
                if same_artist:
                    n_artist += 1
                reasons = ",".join(labels[k] for k in ("album", "artist", "folder", "genre", "era") if k in kinds)
                picked.append((src, dst, score, reasons))
            rows.extend(picked)
        conn.execute("DELETE FROM edges")
        conn.executemany("INSERT OR REPLACE INTO edges (src, dst, weight, reasons) VALUES (?,?,?,?)", rows)
        conn.commit()
        return {"tracks": len(tracks), "edges": len(rows)}


def _ensure_graph() -> None:
    """간선이 비어 있으면(코드 갱신 직후 등) 즉석 빌드 — 곡이 있을 때만."""
    with _conn() as conn:
        n_edges = conn.execute("SELECT COUNT(*) FROM edges").fetchone()[0]
        n_tracks = conn.execute("SELECT COUNT(*) FROM tracks").fetchone()[0]
    if n_edges == 0 and n_tracks > 1:
        build_graph()


def related_of(path: str, limit: int = GRAPH_TOP_K) -> list:
    """곡 하나의 관련곡 (간선 가중치 순, reason 동봉)."""
    p = norm_path(path)
    _ensure_graph()
    with _conn() as conn:
        rows = []
        for e in conn.execute(
                "SELECT e.dst, e.weight, e.reasons FROM edges e WHERE e.src = ? ORDER BY e.weight DESC LIMIT ?",
                (p, max(1, min(int(limit or GRAPH_TOP_K), 50)))):
            t = conn.execute("SELECT * FROM tracks WHERE path = ?", (e["dst"],)).fetchone()
            if t is not None:
                rows.append(dict(track_row(t), reason=e["reasons"], weight=e["weight"]))
    return rows


def walk_playlist(start_path: str = "", q: str = "", length: int = 30) -> list:
    """관련곡 랜덤 워크 — 시작곡에서 관련곡 top-K 중 가중 랜덤으로 다음 곡을 이어감.
    최근 20곡 재방문 금지, 막다른 곳이면 전체에서 랜덤 점프. Obsidian 그래프 산책의 재생판."""
    import random as _random
    from collections import deque
    length = max(2, min(int(length or 30), 100))
    _ensure_graph()
    conn = _conn()
    try:
        def row_of(p):
            r = conn.execute("SELECT * FROM tracks WHERE path = ?", (p,)).fetchone()
            return dict(r) if r is not None else None
        start = None
        if q:
            m = query_tracks(q=q, limit=1)
            start = m[0]["path"] if m else None
        elif start_path:
            start = norm_path(start_path)
            if row_of(start) is None:
                start = None
        if start is None:
            r = conn.execute("SELECT path FROM tracks ORDER BY RANDOM() LIMIT 1").fetchone()
            if r is None:
                return []
            start = r["path"]
        seq, reasons = [start], [""]
        recent = deque(seq, maxlen=20)
        cur = start
        while len(seq) < length:
            nbrs = [(e["dst"], e["weight"], e["reasons"]) for e in
                    conn.execute("SELECT dst, weight, reasons FROM edges WHERE src = ?", (cur,))
                    if e["dst"] not in recent]
            if nbrs:
                total = sum(w for _, w, _ in nbrs)
                pick = _random.uniform(0, total)
                acc = 0.0
                chosen = nbrs[-1]
                for cand_e in nbrs:
                    acc += cand_e[1]
                    if pick <= acc:
                        chosen = cand_e
                        break
                cur, reason = chosen[0], chosen[2]
            else:
                r = conn.execute(
                    "SELECT path FROM tracks WHERE path NOT IN ({}) ORDER BY RANDOM() LIMIT 1".format(
                        ",".join("?" * len(recent))), list(recent)).fetchone()
                if r is None:
                    break
                cur, reason = r["path"], "랜덤 점프"
            seq.append(cur)
            reasons.append(reason)
            recent.append(cur)
        out = []
        for i, p in enumerate(seq):
            r = row_of(p)
            if r is None:
                continue
            item = track_row(r)
            item["step"] = i + 1
            item["reason"] = reasons[i] or "시작곡"
            out.append(item)
        return out
    finally:
        conn.close()


def ego_graph(path: str = "", q: str = "", k: int = GRAPH_TOP_K, ring2: int = 4) -> dict:
    """에고 그래프 — 중심곡 + 1홉(top-k) + 2홉(각 이웃의 top-ring2). 그래프 뷰용."""
    _ensure_graph()
    with _conn() as conn:
        center = None
        if q:
            m = query_tracks(q=q, limit=1)
            center = m[0]["path"] if m else None
        elif path:
            center = norm_path(path)
        if center is None or conn.execute("SELECT 1 FROM tracks WHERE path = ?", (center,)).fetchone() is None:
            r = conn.execute(
                "SELECT src, COUNT(*) c FROM edges GROUP BY src ORDER BY c DESC, src LIMIT 1").fetchone()
            if r is None:
                return {"nodes": [], "edges": [], "center": None}
            center = r["src"]
        nodes, index, edges = [], {}, []

        def add_node(p, ring):
            if p in index:
                return index[p]
            t = conn.execute("SELECT * FROM tracks WHERE path = ?", (p,)).fetchone()
            if t is None:
                return None
            i = len(nodes)
            nodes.append(dict(track_row(t), ring=ring))
            index[p] = i
            return i

        ci = add_node(center, 0)
        ring1 = [e["dst"] for e in conn.execute(
            "SELECT dst FROM edges WHERE src = ? ORDER BY weight DESC LIMIT ?", (center, k))]
        for p1 in ring1:
            i1 = add_node(p1, 1)
            if i1 is not None:
                edges.append([ci, i1])
        for p1 in ring1:
            for e in conn.execute(
                    "SELECT dst FROM edges WHERE src = ? ORDER BY weight DESC LIMIT ?", (p1, ring2)):
                p2 = e["dst"]
                if p2 == center:
                    continue
                i2 = add_node(p2, 2) if p2 not in index else index[p2]
                if i2 is not None:
                    pair = [index[p1], i2]
                    if pair not in edges and [pair[1], pair[0]] not in edges:
                        edges.append(pair)
    return {"nodes": nodes, "edges": edges, "center": center}


# ── 플레이리스트 ─────────────────────────────────────────────────────────

def load_playlists() -> list:
    return _load_json(PLAYLISTS_JSON, {"playlists": []}).get("playlists", [])


def save_playlists(pls: list) -> None:
    _save_json(PLAYLISTS_JSON, {"playlists": pls})


def find_playlist(pls: list, name: str):
    name = (name or "").strip()
    return next((p for p in pls if p["name"] == name), None)


def playlist_tracks(pl: dict) -> list:
    """플레이리스트의 경로 목록 → 트랙 통화 (DB에 없는 경로는 건너뜀 — 폴더가 진실)."""
    if not pl.get("tracks"):
        return []
    with _conn() as conn:
        by_path = {}
        chunk = pl["tracks"]
        for i in range(0, len(chunk), 500):
            part = chunk[i:i + 500]
            marks = ",".join("?" * len(part))
            for r in conn.execute(f"SELECT * FROM tracks WHERE path IN ({marks})", part):
                by_path[r["path"]] = track_row(r)
    return [dict(by_path[p], playlist_name=pl["name"]) for p in pl["tracks"] if p in by_path]


def _strip_from_playlists(paths: set) -> None:
    pls = load_playlists()
    changed = False
    for pl in pls:
        kept = [p for p in pl.get("tracks", []) if p not in paths]
        if len(kept) != len(pl.get("tracks", [])):
            pl["tracks"] = kept
            changed = True
    if changed:
        save_playlists(pls)
