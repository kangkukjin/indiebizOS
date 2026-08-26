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
    # CD 통이미지(.ape/.flac + .cue) 지원 — 곡 하나가 '큰 파일의 한 구간'일 수 있다.
    # media_path=실제 파일(비면 path 자신), start=구간 시작(초). 옛 DB 도 여기서 따라온다.
    for col, ddl in (("media_path", "TEXT"), ("start", "REAL")):
        try:
            conn.execute(f"ALTER TABLE tracks ADD COLUMN {col} {ddl}")
        except sqlite3.OperationalError:
            pass                                    # 이미 있음
    conn.execute("CREATE INDEX IF NOT EXISTS idx_tracks_artist ON tracks(artist)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_tracks_album ON tracks(album)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_tracks_title ON tracks(title)")
    # 2026-07-28 관련곡 그래프 은퇴 — 파생 캐시라 그냥 버린다(원본 파일 무손상).
    # 스키마에서 뺀 채로 두면 옛 설치본에 40,000행짜리 유령 테이블이 남으므로 여기서 떨군다.
    conn.execute("DROP TABLE IF EXISTS edges")
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


# ── CUE 시트 (CD 통이미지) ──────────────────────────────────────────────
# 무손실 립은 흔히 "CD 한 장 = 큰 파일 하나(.ape/.flac) + .cue" 로 온다. cue 에 트랙 제목·
# 연주자·시작시각이 들어 있으므로, 그걸 읽어 **곡 단위로** 색인한다(파일은 하나여도 곡은 여럿).
# 재생은 api_music 이 그 구간만 잘라 변환해 흘린다. cue 가 가리키는 파일 자체는 따로 색인하지
# 않는다(중복 방지).

_CUE_EXTS = {".cue"}


def _decode_text(raw: bytes) -> str:
    """cue 인코딩 추정 — utf-8 → cp949(한글이 나올 때만) → cp1252/latin-1."""
    for enc in ("utf-8-sig", "utf-8"):
        try:
            return raw.decode(enc)
        except UnicodeDecodeError:
            pass
    try:
        t = raw.decode("cp949")
        if _looks_cjk(t):
            return t
    except UnicodeDecodeError:
        pass
    for enc in ("cp1252", "latin-1"):
        try:
            return raw.decode(enc)
        except UnicodeDecodeError:
            continue
    return raw.decode("utf-8", "replace")


def _cue_time(s: str) -> float:
    """MM:SS:FF(프레임 75/초) → 초."""
    parts = (s or "").strip().split(":")
    try:
        mm, ss, ff = (int(parts[0]), int(parts[1]), int(parts[2]) if len(parts) > 2 else 0)
    except (ValueError, IndexError):
        return 0.0
    return mm * 60 + ss + ff / 75.0


def _unquote(s: str) -> str:
    s = (s or "").strip()
    return s[1:-1] if len(s) >= 2 and s[0] == '"' and s[-1] == '"' else s


def parse_cue(cue_path: str):
    """cue 한 장 → {album, albumartist, genre, year, tracks:[{no,title,artist,media,start}]}.

    FILE 이 여러 번 나오는 cue(트랙마다 파일)도 지원 — 트랙은 직전 FILE 에 속한다.
    가리키는 파일이 실제로 없으면 None(깨진 cue 는 조용히 건너뛴다).
    """
    try:
        txt = _decode_text(Path(cue_path).read_bytes())
    except OSError:
        return None
    base = os.path.dirname(cue_path)
    album = albumartist = genre = year = ""
    cur_media = ""
    tracks: list = []
    cur = None
    for raw_line in txt.splitlines():
        line = raw_line.strip()
        up = line.upper()
        if up.startswith("REM GENRE "):
            genre = _unquote(line[10:])
        elif up.startswith("REM DATE "):
            year = _unquote(line[9:])[:4]
        elif up.startswith("FILE "):
            name = _unquote(line[5:].rsplit(" ", 1)[0])
            cand = norm_path(os.path.join(base, name))
            cur_media = cand if os.path.isfile(cand) else ""
        elif up.startswith("TRACK "):
            if cur:
                tracks.append(cur)
            bits = line.split()
            no = int(bits[1]) if len(bits) > 1 and bits[1].isdigit() else len(tracks) + 1
            cur = {"no": no, "title": "", "artist": "", "media": cur_media, "start": 0.0}
        elif up.startswith("TITLE "):
            if cur:
                cur["title"] = _unquote(line[6:])
            else:
                album = _unquote(line[6:])          # 트랙 앞의 TITLE = 앨범명
        elif up.startswith("PERFORMER "):
            if cur:
                cur["artist"] = _unquote(line[10:])
            else:
                albumartist = _unquote(line[10:])
        elif up.startswith("INDEX 01 ") and cur:
            cur["start"] = _cue_time(line[9:])
    if cur:
        tracks.append(cur)
    tracks = [t for t in tracks if t["media"]]
    if not tracks:
        return None
    return {"album": album, "albumartist": albumartist, "genre": genre,
            "year": year, "tracks": tracks}


def cue_rows(cue_path: str, source_root: str) -> list:
    """cue → tracks 테이블 행 목록. path 는 '<미디어>#<트랙번호>' 합성 키(폴더는 그대로)."""
    cue = parse_cue(cue_path)
    if not cue:
        return []
    # 미디어별 총 길이 — 마지막 트랙 길이 계산용
    lengths: dict = {}
    for t in cue["tracks"]:
        if t["media"] not in lengths:
            try:
                mf = _MutagenFile(t["media"]) if _MutagenFile else None
                lengths[t["media"]] = float(mf.info.length) if mf and mf.info else 0.0
            except Exception:
                lengths[t["media"]] = 0.0
    rows = []
    for i, t in enumerate(cue["tracks"]):
        nxt = cue["tracks"][i + 1] if i + 1 < len(cue["tracks"]) else None
        if nxt and nxt["media"] == t["media"]:
            dur = max(0.0, nxt["start"] - t["start"])
        else:
            dur = max(0.0, lengths.get(t["media"], 0.0) - t["start"])
        try:
            st = os.stat(t["media"])
            size, mtime = st.st_size, st.st_mtime
        except OSError:
            continue
        rows.append({
            "path": f"{t['media']}#{t['no']:02d}",
            "media_path": t["media"], "start": round(t["start"], 3),
            "source": source_root, "filename": os.path.basename(t["media"]),
            "ext": Path(t["media"]).suffix.lower().lstrip("."),
            "size": size, "mtime": mtime,
            "title": t["title"] or f"Track {t['no']:02d}",
            "artist": t["artist"] or cue["albumartist"],
            "album": cue["album"], "albumartist": cue["albumartist"],
            "genre": cue["genre"], "year": cue["year"],
            "track_no": t["no"], "disc_no": None,
            "duration": round(dur, 3), "has_cover": 0,
        })
    return rows


def _walk_audio(root: str):
    """색인할 오디오 파일 + cue 시트. cue 가 가리키는 미디어 파일은 제외(곡은 cue 가 낸다)."""
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if not d.startswith(".")]
        cues = [f for f in filenames if not f.startswith(".") and Path(f).suffix.lower() in _CUE_EXTS]
        claimed = set()
        for c in cues:
            cue_path = norm_path(os.path.join(dirpath, c))
            parsed = parse_cue(cue_path)
            if parsed:
                claimed.update(t["media"] for t in parsed["tracks"])
                yield cue_path
        for fn in filenames:
            if fn.startswith("."):
                continue
            p = norm_path(os.path.join(dirpath, fn))
            if Path(fn).suffix.lower() in AUDIO_EXTS and p not in claimed:
                yield p


def _scan_source(conn: sqlite3.Connection, root: str, progress: dict) -> None:
    found = set()
    known = {r["path"]: (r["mtime"], r["size"]) for r in
             conn.execute("SELECT path, mtime, size FROM tracks WHERE source = ?", (root,))}

    def _upsert(row: dict) -> None:
        conn.execute("""
            INSERT INTO tracks (path, source, filename, ext, size, mtime, title, artist, album,
                                albumartist, genre, year, track_no, disc_no, duration, has_cover,
                                media_path, start, added_at)
            VALUES (:path, :source, :filename, :ext, :size, :mtime, :title, :artist, :album,
                    :albumartist, :genre, :year, :track_no, :disc_no, :duration, :has_cover,
                    :media_path, :start, :added_at)
            ON CONFLICT(path) DO UPDATE SET
                source=:source, filename=:filename, ext=:ext, size=:size, mtime=:mtime,
                title=:title, artist=:artist, album=:album, albumartist=:albumartist,
                genre=:genre, year=:year, track_no=:track_no, disc_no=:disc_no,
                duration=:duration, has_cover=:has_cover, media_path=:media_path, start=:start
        """, {"media_path": None, "start": None, **row, "added_at": _now_iso()})

    for p in _walk_audio(root):
        # cue 한 장은 곡 여러 개를 낸다 — 파일 하나:행 하나 규칙의 유일한 예외.
        if Path(p).suffix.lower() in _CUE_EXTS:
            progress["seen"] += 1
            try:
                cue_st = os.stat(p)
            except OSError:
                continue
            rows = cue_rows(p, root)
            for row in rows:
                found.add(row["path"])
                old = known.get(row["path"])
                # cue 나 미디어 중 하나라도 바뀌면 그 앨범을 다시 읽는다.
                if old and abs(old[0] - max(row["mtime"], cue_st.st_mtime)) < 1 and old[1] == row["size"]:
                    continue
                row = {**row, "mtime": max(row["mtime"], cue_st.st_mtime)}
                _upsert(row)
                progress["updated"] += 1
            if rows and progress["updated"] % 50 < len(rows):
                conn.commit()
                _set_scan_state({"status": "scanning", **progress})
            continue

        found.add(p)
        progress["seen"] += 1
        try:
            st = os.stat(p)
        except OSError:
            continue
        old = known.get(p)
        if old and abs(old[0] - st.st_mtime) < 1 and old[1] == st.st_size:
            continue  # 변경 없음 — 증분 스킵
        _upsert(extract_tags(p, root))     # 일반 파일 — media_path/start 는 비운다(자기 자신)
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
        _set_scan_state({"status": "done", **progress, "finished_at": _now_iso()})
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
    threading.Thread(target=_scan_worker, args=(roots,), daemon=True).start()  # cc-ok: 멱등 스캔 잡 — 사멸 시 다음 스캔 호출이 재실행
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


def query_tracks(q: str = "", path: str = "", folder: str = "", limit: int = 300) -> list:
    """곡 질의 — q(부분검색) · folder(폴더 단위) · path(단일 곡).

    artist/album/albumartist 정확 필터는 2026-07-28 은퇴 — 앨범·아티스트 목록 뷰의
    드릴다운 전용이었고 그 축이 사라졌다. 아티스트·앨범명 검색은 q 가 그대로 덮는다.
    """
    where, args = [], []
    if path:
        where.append("path = ?"); args.append(norm_path(path))
    if folder:
        f = norm_path(folder)
        where.append("(path LIKE ? OR path = ?)"); args += [f + os.sep + "%", f]
    if q:
        where.append("(title LIKE ? OR artist LIKE ? OR album LIKE ? OR filename LIKE ?)")
        args += [f"%{q}%"] * 4
    sql = "SELECT * FROM tracks"
    if where:
        sql += " WHERE " + " AND ".join(where)
    sql += " ORDER BY album, disc_no, track_no, title LIMIT ?"
    args.append(max(1, min(int(limit or 300), 2000)))  # clamp-ok: SQL LIMIT 안전 난간 2000 — 요청량이 아니라 폭주 방지
    with _conn() as conn:
        return [track_row(r) for r in conn.execute(sql, args)]


def stats() -> dict:
    """라이브러리 요약 — 곡·폴더·플레이리스트. 앨범/아티스트 집계는 2026-07-28 은퇴
    (앨범·아티스트 축을 지운 자리에 폴더 수가 들어왔다 — 폴더가 이 앱의 뼈대)."""
    with _conn() as conn:
        tracks = conn.execute("SELECT COUNT(*) FROM tracks").fetchone()[0]
        per_source = {r["source"]: r["n"] for r in conn.execute("SELECT source, COUNT(*) AS n FROM tracks GROUP BY source")}
    return {"tracks": tracks, "folders": count_folders(),
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


def _track_dirs() -> dict:
    """곡을 **직접** 담은 폴더 → {n, dur}. 트리 집계의 원재료."""
    agg = {}
    with _conn() as conn:
        for r in conn.execute("SELECT path, duration FROM tracks"):
            d = os.path.dirname(r["path"])
            a = agg.setdefault(d, {"n": 0, "dur": 0.0})
            a["n"] += 1
            a["dur"] += r["duration"] or 0
    return agg


def count_folders() -> int:
    """곡을 담은 폴더 수 (보관함 통계용)."""
    return len(_track_dirs())


def direct_tracks(folder: str, limit: int = 500) -> list:
    """그 폴더에 **직접** 든 곡만 (하위 폴더 제외) — 파인더의 '이 폴더 안 파일'.

    query_tracks(folder=…) 는 하위까지 훑으므로 여기선 부모 디렉토리가 정확히 일치하는
    것만 고른다. 폴더 안 순서는 디스크 번호·트랙 번호(앨범 순서), 없으면 파일명.
    """
    f = norm_path(folder)
    if not f:
        return []
    with _conn() as conn:
        rows = conn.execute(
            "SELECT * FROM tracks WHERE path LIKE ? AND path NOT LIKE ? "
            "ORDER BY disc_no, track_no, filename LIMIT ?",
            (f + os.sep + "%", f + os.sep + "%" + os.sep + "%", max(1, int(limit))),
        ).fetchall()
    return [track_row(r) for r in rows]


def browse_folders(parent: str = "") -> dict:
    """파인더식 한 단계 탐색 — parent 의 **바로 아래** 폴더만 돌려준다.

    옛 list_folders 는 곡을 담은 폴더를 전부(275개) 평평하게 늘어놓아, 많아지면
    찾아 들어갈 수가 없었다. 트리는 한 단계씩 — 각 행에 그 폴더 **아래 전체**(하위 폴더 포함)
    곡 수를 실어, 들어가기 전에 규모를 보고 고를 수 있게 한다.

    - parent 없음 → 등록된 소스 폴더(루트)
    - parent 있음 → 그 폴더의 직속 하위 폴더 + 맨 앞에 '⬆️ 상위 폴더' 행
      (상위 행의 path 가 비면 루트로 돌아간다 — 같은 액션 하나로 오르내린다)

    곡이 하나도 없는 가지는 아예 내지 않는다(빈 폴더를 헤매지 않게).
    """
    agg = _track_dirs()
    roots = [s["path"] for s in load_sources()]
    p = norm_path(parent) if parent else ""

    def subtree(d: str):
        """d 아래(자기 포함) 전체 곡 수·길이."""
        n = dur = 0
        pre = d + os.sep
        for k, v in agg.items():
            if k == d or k.startswith(pre):
                n += v["n"]; dur += v["dur"]
        return n, dur

    def row(d: str, label: str) -> dict:
        n, dur = subtree(d)
        pre = d + os.sep
        subs = {k[len(pre):].split(os.sep)[0] for k in agg if k.startswith(pre)}
        bits = [f"{n}곡"]
        if subs:
            bits.append(f"하위 {len(subs)}폴더")
        if fmt_duration(dur):
            bits.append(fmt_duration(dur))
        return {"title": label, "name": label, "path": d, "kind": "folder",
                "n": n, "sub": len(subs), "duration_str": fmt_duration(dur),
                "meta": " · ".join(bits)}

    if not p:
        items = [row(r, os.path.basename(r) or r) for r in roots if subtree(r)[0]]
        return {"folder": "", "parent": "", "items": sorted(items, key=lambda x: x["title"]),
                "n_tracks": sum(v["n"] for v in agg.values())}

    pre = p + os.sep
    kids = sorted({k[len(pre):].split(os.sep)[0] for k in agg if k.startswith(pre)})
    items = [row(os.path.join(p, k), k) for k in kids]

    # 상위로 — 소스 루트에서 오르면 최상위(빈 path)로 돌아간다.
    up = "" if p in roots else os.path.dirname(p)
    items.insert(0, {"title": "⬆️ 상위 폴더", "name": "⬆️ 상위 폴더", "path": up,
                     "kind": "up", "n": 0, "sub": 0, "meta": _rel_folder(up) if up else "최상위"})
    n, _ = subtree(p)
    return {"folder": p, "parent": up, "items": items, "n_tracks": n}


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
