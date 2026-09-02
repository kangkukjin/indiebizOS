"""
Notebook Core — 근거 고정 질의(Grounded Query)의 저장·색인·검색 층
==================================================================
"노트북" = 이름 붙인 소스(문서) 묶음. 소스를 청크로 쪼개 하이브리드 색인
(시맨틱 ko-sroberta + FTS5 BM25)을 만들고, 질의 시 노트북 스코프 안에서
관련 청크를 반환한다. 생성(근거 고정 답변)은 handler.py 몫 — 이 모듈은 LLM 0.

설계 정본: docs/NOTEBOOK_GROUNDED_QUERY_DESIGN.md
엔진 계보: blog/tool_blog_rag.py (KThoughts 하이브리드 검색) 이식·코퍼스-무관 일반화.
★해마 임베딩 모델(ibl_embedding)은 쓰지 않는다 — IBL 코드 연상 특화라 일반 문서 부적합.

Dependencies:
  Required: sqlite3 (stdlib)
  Optional: sentence-transformers + sqlite-vec (시맨틱) — 미설치 시 FTS5만 (graceful)
  Optional: PyMuPDF(fitz) — PDF 소스용. 미설치 시 PDF add가 정직 거부.

이식성: fcntl 등 유닉스 전용 없음(windows 게이트). 동시성=sqlite WAL + 스레드별 연결.
"""

import os
import re
import json
import time
import struct
import hashlib
import logging
import sqlite3
import threading
from runtime_utils import expand_body_path  # 경로 펼침 단일 해소점 (~workspace/·~)
from pathlib import Path
from datetime import datetime
from typing import List, Dict, Tuple, Optional, Any

logger = logging.getLogger(__name__)

_ROOT = Path(__file__).resolve().parents[5]          # indiebizOS 루트 (music_core 선례)
NOTEBOOK_DIR = _ROOT / "data" / "notebook"
DB_PATH = NOTEBOOK_DIR / "notebooks.db"

EMBEDDING_DIM = 768
EMBEDDING_MODEL = "jhgan/ko-sroberta-multitask"       # blog RAG와 동일 (범용 한국어)
BATCH_SIZE = 32
DEFAULT_ALPHA = 0.7                                    # 70% 시맨틱 + 30% BM25

# 청크 규격 (설계 §4-2): 문단 경계 우선, 목표 650자·상한 1100자.
CHUNK_TARGET = 650
CHUNK_HARD_MAX = 1100

# 이 글자 수를 넘는 소스는 색인을 백그라운드로 (도구 60s 타임아웃 방어, family-news 선례)
BACKGROUND_THRESHOLD_CHARS = 150_000

TEXT_EXTS = {".md", ".txt", ".text", ".markdown", ".csv", ".log", ".json", ".yaml", ".yml", ".html", ".htm"}

_write_lock = threading.RLock()        # 쓰기 직렬화 (in-process)
_bg_threads: Dict[int, threading.Thread] = {}   # source_id → 색인 스레드


# =============================================================================
# DB
# =============================================================================

def _connect(with_vec: bool = False) -> sqlite3.Connection:
    NOTEBOOK_DIR.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(DB_PATH), timeout=15.0)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    if with_vec and _check_sqlite_vec():
        import sqlite_vec
        conn.enable_load_extension(True)
        sqlite_vec.load(conn)
        conn.enable_load_extension(False)
    _ensure_schema(conn, with_vec=with_vec and _check_sqlite_vec())
    return conn


def _ensure_schema(conn: sqlite3.Connection, with_vec: bool = False):
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS notebooks(
            id INTEGER PRIMARY KEY,
            name TEXT UNIQUE NOT NULL,
            note TEXT DEFAULT '',
            created_at TEXT,
            updated_at TEXT
        );
        CREATE TABLE IF NOT EXISTS sources(
            id INTEGER PRIMARY KEY,
            notebook_id INTEGER NOT NULL,
            title TEXT NOT NULL,
            kind TEXT NOT NULL,              -- file | text
            path TEXT DEFAULT '',            -- kind=file 원본 경로 (사본 없음, mtime 참조)
            mtime REAL DEFAULT 0,
            char_count INTEGER DEFAULT 0,
            chunk_count INTEGER DEFAULT 0,
            status TEXT DEFAULT 'ready',     -- indexing | ready | error
            error TEXT DEFAULT '',
            added_at TEXT
        );
        CREATE TABLE IF NOT EXISTS chunks(
            id INTEGER PRIMARY KEY,
            notebook_id INTEGER NOT NULL,
            source_id INTEGER NOT NULL,
            seq INTEGER NOT NULL,
            loc TEXT DEFAULT '',             -- p.12 | ¶3 — 인용 해상도
            text TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_chunks_notebook ON chunks(notebook_id);
        CREATE INDEX IF NOT EXISTS idx_chunks_source ON chunks(source_id);
        CREATE TABLE IF NOT EXISTS meta(key TEXT PRIMARY KEY, value TEXT);
    """)
    try:
        conn.execute("CREATE VIRTUAL TABLE IF NOT EXISTS chunks_fts USING fts5(text)")
    except sqlite3.OperationalError:
        pass  # FTS5 없는 빌드 — 시맨틱만으로 동작
    if with_vec:
        conn.execute(
            f"CREATE VIRTUAL TABLE IF NOT EXISTS chunks_vec USING vec0(embedding float[{EMBEDDING_DIM}])"
        )
    conn.commit()


def _now() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


# =============================================================================
# 임베딩 (blog RAG 이식 — lazy load, L2 정규화)
# =============================================================================

_model = None
_model_load_attempted = False
_sqlite_vec_available: Optional[bool] = None


def _check_sqlite_vec() -> bool:
    global _sqlite_vec_available
    if _sqlite_vec_available is None:
        try:
            import sqlite_vec  # noqa: F401
            _sqlite_vec_available = True
        except ImportError:
            _sqlite_vec_available = False
            logger.warning("[notebook] sqlite-vec 미설치 → FTS5 검색만")
    return _sqlite_vec_available


def _load_model() -> bool:
    global _model, _model_load_attempted
    if _model_load_attempted:
        return _model is not None
    _model_load_attempted = True
    try:
        from sentence_transformers import SentenceTransformer
        logger.info(f"[notebook] 임베딩 모델 로딩: {EMBEDDING_MODEL}")
        _model = SentenceTransformer(EMBEDDING_MODEL)
        return True
    except ImportError:
        logger.warning("[notebook] sentence-transformers 미설치 → FTS5 검색만")
        return False
    except Exception as e:
        logger.error(f"[notebook] 모델 로드 실패: {e}")
        return False


def semantic_available() -> bool:
    return _check_sqlite_vec() and _load_model()


def _embed_batch(texts: List[str]) -> List[bytes]:
    if not semantic_available():
        return []
    import numpy as np
    packed = []
    for i in range(0, len(texts), BATCH_SIZE):
        vecs = _model.encode(texts[i:i + BATCH_SIZE], convert_to_numpy=True,
                             show_progress_bar=False).astype("float32")
        norms = np.linalg.norm(vecs, axis=1, keepdims=True)
        norms[norms == 0] = 1
        vecs = vecs / norms
        for v in vecs:
            packed.append(struct.pack(f"{EMBEDDING_DIM}f", *v))
    return packed


def _embed_one(text: str) -> Optional[bytes]:
    out = _embed_batch([text])
    return out[0] if out else None


# =============================================================================
# 추출 (파일 → [(loc, 문단)] 목록)
# =============================================================================

class _BinaryFile(Exception):
    pass


def _read_text_file(path: str) -> str:
    """utf-8 → cp949 → euc-kr → replace 폴백 (self:grep 2층화 선례 — 옛 한글 문서 침묵 탈락 방지).
    ★replace 폴백은 바이너리도 '성공'시키므로 NUL 스니핑이 선행 관문 (실측: /bin/ls 가 141청크로 뚫렸다)."""
    raw = Path(path).read_bytes()
    if b"\x00" in raw[:8192]:
        raise _BinaryFile(path)
    for enc in ("utf-8", "cp949", "euc-kr"):
        try:
            return raw.decode(enc)
        except (UnicodeDecodeError, LookupError):
            continue
    return raw.decode("utf-8", errors="replace")


def _strip_html(text: str) -> str:
    text = re.sub(r"<(script|style)[\s\S]*?</\1>", " ", text, flags=re.I)
    text = re.sub(r"<[^>]+>", " ", text)
    return re.sub(r"[ \t]{2,}", " ", text)


def extract_file(path: str) -> Tuple[List[Tuple[str, str]], str]:
    """파일 → ([(loc, 문단텍스트)...], error). PDF=페이지 단위 loc, 텍스트=문단 번호 loc."""
    ext = Path(path).suffix.lower()
    if ext == ".pdf":
        return _extract_pdf(path)
    if ext in TEXT_EXTS or ext == "":
        try:
            text = _read_text_file(path)
        except _BinaryFile:
            return [], f"바이너리 파일입니다(텍스트 아님): {os.path.basename(path)} — 텍스트/PDF만 받습니다."
        except OSError as e:
            return [], f"파일을 읽을 수 없습니다: {e}"
        if ext in (".html", ".htm"):
            text = _strip_html(text)
        return _paragraphs_with_loc(text), ""
    return [], (f"지원하지 않는 형식입니다: {ext} — 텍스트({', '.join(sorted(TEXT_EXTS))})와 .pdf만 받습니다. "
                f"다른 형식은 본문을 복사해 text 파라미터로 넣어 주세요(리더 모드 우회).")


def _extract_pdf(path: str) -> Tuple[List[Tuple[str, str]], str]:
    try:
        import fitz  # PyMuPDF (system_essentials/office_ops 선례)
    except ImportError:
        return [], "PyMuPDF(fitz) 미설치 — PDF 소스를 쓰려면 .venv에 pymupdf를 설치하세요."
    try:
        doc = fitz.open(path)
    except Exception as e:
        return [], f"PDF를 열 수 없습니다: {e}"
    paras: List[Tuple[str, str]] = []
    total_chars = 0
    try:
        for pno in range(doc.page_count):
            page_text = doc[pno].get_text("text") or ""
            total_chars += len(page_text.strip())
            for block in re.split(r"\n{2,}", page_text):
                block = re.sub(r"\s+", " ", block).strip()
                if len(block) >= 20:
                    paras.append((f"p.{pno + 1}", block))
        page_count = doc.page_count
    finally:
        doc.close()
    # 스캔(이미지) PDF 판정: 페이지당 평균 15자 미만 = 텍스트 층 없음 (설계 §4-1 — OCR 범위 밖.
    # 실측: 30자 임계는 페이지당 한 문장짜리 정상 PDF를 오탐했다)
    if page_count > 0 and total_chars / page_count < 15:
        return [], ("스캔(이미지) PDF로 보입니다(텍스트 층 없음) — 이 어휘는 OCR을 하지 않습니다. "
                    "이런 문서는 NotebookLM 등 OCR 있는 도구를 쓰거나 텍스트 변환 후 넣어 주세요.")
    return paras, ""


def _paragraphs_with_loc(text: str) -> List[Tuple[str, str]]:
    paras = []
    for i, block in enumerate(re.split(r"\n{2,}", text), 1):
        block = block.strip()
        if len(block) >= 15:
            paras.append((f"¶{i}", block))
    return paras


# ── URL 소스 (Phase 2): 웹페이지 본문 · 유튜브 자막 ─────────────────────────

_YT_ID_RE = re.compile(
    r"(?:youtube\.com/(?:watch\?(?:.*&)?v=|shorts/|live/|embed/)|youtu\.be/)([A-Za-z0-9_-]{6,20})")


def _youtube_id(url: str) -> str:
    m = _YT_ID_RE.search(url or "")
    return m.group(1) if m else ""


def is_url(s: str) -> bool:
    return bool(re.match(r"^https?://", (s or "").strip(), re.I))


def _extract_web(url: str) -> Tuple[List[Tuple[str, str]], str, str]:
    """웹페이지 → ([(loc, 문단)], 제목, error). 본문=태그 제거(리더 모드의 결정론 근사)."""
    import requests
    try:
        resp = requests.get(url, timeout=25, headers={
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 Chrome/126 Safari/537.36"})
        resp.raise_for_status()
    except Exception as e:
        return [], "", f"페이지를 가져올 수 없습니다: {e}"
    if resp.encoding in (None, "ISO-8859-1"):
        resp.encoding = resp.apparent_encoding or "utf-8"
    html = resp.text
    m = re.search(r"<title[^>]*>([\s\S]*?)</title>", html, re.I)
    title = re.sub(r"\s+", " ", m.group(1)).strip() if m else ""
    # 블록 태그를 문단 경계로 → 태그 제거
    html = re.sub(r"</(p|div|li|h[1-6]|section|article|tr|blockquote)>", "\n\n", html, flags=re.I)
    html = re.sub(r"<br\s*/?>", "\n", html, flags=re.I)
    text = _strip_html(html)
    text = re.sub(r"&nbsp;", " ", text)
    text = re.sub(r"&amp;", "&", text)
    paras = _paragraphs_with_loc(text)
    if not paras:
        return [], title, ("본문을 추출하지 못했습니다 — 클라이언트 렌더 페이지일 수 있습니다. "
                           "브라우저 리더 모드에서 본문을 복사해 text 파라미터로 넣어 주세요.")
    return paras, title, ""


def _extract_youtube(url: str) -> Tuple[List[Tuple[str, str]], str, str]:
    """유튜브 → 자막을 시간 단위 문단으로 ([(loc "[mm:ss]", 문단)], 영상제목, error).
    yt-dlp 라이브러리 직접 사용(교차 패키지 차용 금지 — youtube 패키지 코드는 안 문다)."""
    try:
        import yt_dlp
    except ImportError:
        return [], "", "yt-dlp 미설치 — 유튜브 소스를 쓰려면 .venv에 yt-dlp를 설치하세요."
    vid = _youtube_id(url)
    target = f"https://www.youtube.com/watch?v={vid}" if vid else url
    opts = {"skip_download": True, "quiet": True, "no_warnings": True,
            "writesubtitles": True, "writeautomaticsub": True}
    try:
        with yt_dlp.YoutubeDL(opts) as ydl:
            info = ydl.extract_info(target, download=False)
    except Exception as e:
        return [], "", f"유튜브 정보를 가져올 수 없습니다: {e}"
    title = (info or {}).get("title") or f"youtube {vid}"
    subs = (info or {}).get("subtitles") or {}
    autos = (info or {}).get("automatic_captions") or {}

    def _pick(tracks: dict) -> Optional[dict]:
        for lang in ("ko", "ko-KR", "en", "en-US", "en-orig"):
            for t in tracks.get(lang, []):
                if t.get("ext") in ("vtt", "srv3", "srv1", "json3"):
                    return t
        for lang in tracks:                     # 아무 언어라도
            for t in tracks[lang]:
                if t.get("ext") == "vtt":
                    return t
        return None

    track = _pick(subs) or _pick(autos)        # 수동 자막 우선, 자동 자막 폴백
    if not track or not track.get("url"):
        return [], title, "이 영상에는 자막(자동 포함)이 없습니다 — 자막 있는 영상만 소스로 넣을 수 있습니다."
    import requests
    try:
        raw = requests.get(track["url"], timeout=25).text
    except Exception as e:
        return [], title, f"자막을 받을 수 없습니다: {e}"
    cues = _parse_vtt(raw) if track.get("ext") == "vtt" or raw.lstrip().startswith("WEBVTT") \
        else _parse_srv(raw)
    if not cues:
        return [], title, "자막 파싱 결과가 비었습니다."
    # 60초 창으로 문단화 — loc=[mm:ss] 창 시작 (인용 해상도)
    paras: List[Tuple[str, str]] = []
    win_start, buf, seen = None, [], set()
    for sec, text in cues:
        if win_start is None:
            win_start = sec
        if sec - win_start >= 60 and buf:
            paras.append((_fmt_ts(win_start), " ".join(buf)))
            win_start, buf, seen = sec, [], set()
        t = text.strip()
        if t and t not in seen:                 # 자동 자막의 롤링 중복 제거
            buf.append(t)
            seen.add(t)
    if buf:
        paras.append((_fmt_ts(win_start or 0), " ".join(buf)))
    return [(loc, p) for loc, p in paras if len(p) >= 15], title, ""


def _fmt_ts(sec: float) -> str:
    s = int(sec)
    return f"[{s // 3600}:{s % 3600 // 60:02d}:{s % 60:02d}]" if s >= 3600 else f"[{s // 60}:{s % 60:02d}]"


_VTT_TS = re.compile(r"(?:(\d+):)?(\d{2}):(\d{2})[.,](\d{3})\s*-->")


def _parse_vtt(raw: str) -> List[Tuple[float, str]]:
    cues, cur = [], None
    for line in raw.splitlines():
        m = _VTT_TS.match(line.strip())
        if m:
            h = int(m.group(1) or 0)
            cur = h * 3600 + int(m.group(2)) * 60 + int(m.group(3))
            continue
        text = re.sub(r"<[^>]+>", "", line).strip()
        if cur is not None and text and "-->" not in text:
            cues.append((float(cur), text))
    return cues


def _parse_srv(raw: str) -> List[Tuple[float, str]]:
    """srv3/json3 최소 파서 — json3의 events[{tStartMs, segs[{utf8}]}]"""
    try:
        data = json.loads(raw)
        cues = []
        for ev in data.get("events", []):
            text = "".join(s.get("utf8", "") for s in ev.get("segs", []) or []).strip()
            if text and text != "\n":
                cues.append((float(ev.get("tStartMs", 0)) / 1000.0, text))
        return cues
    except Exception:
        # srv1/srv3 XML: <text start="12.3">…</text>
        cues = []
        for m in re.finditer(r'<text[^>]*start="([\d.]+)"[^>]*>([\s\S]*?)</text>', raw):
            import html as _html
            text = _html.unescape(re.sub(r"<[^>]+>", "", m.group(2))).strip()
            if text:
                cues.append((float(m.group(1)), text))
        return cues


# =============================================================================
# 청크 (문단 누적, 페이지/loc 경계 보존)
# =============================================================================

_SENT_END = re.compile(r"(?<=[.!?다요까임음됨함])\s+")


def _split_long(text: str) -> List[str]:
    """상한 초과 문단을 문장 경계에서 분할"""
    if len(text) <= CHUNK_HARD_MAX:
        return [text]
    out, buf = [], ""
    for sent in _SENT_END.split(text):
        if buf and len(buf) + len(sent) + 1 > CHUNK_HARD_MAX:
            out.append(buf.strip())
            buf = sent
        else:
            buf = f"{buf} {sent}".strip()
    if buf.strip():
        out.append(buf.strip())
    # 문장 경계가 아예 없는 초장문 방어
    final = []
    for c in out:
        while len(c) > CHUNK_HARD_MAX * 2:
            final.append(c[:CHUNK_HARD_MAX])
            c = c[CHUNK_HARD_MAX:]
        final.append(c)
    return [c for c in final if c.strip()]


def build_chunks(paras: List[Tuple[str, str]]) -> List[Tuple[str, str]]:
    """[(loc, 문단)] → [(loc, 청크)] — 같은 loc 그룹(PDF=페이지) 안에서만 누적."""
    chunks: List[Tuple[str, str]] = []
    cur_loc, buf = None, ""

    def flush():
        nonlocal buf
        if buf.strip():
            for piece in _split_long(buf.strip()):
                chunks.append((cur_loc or "", piece))
        buf = ""

    for loc, para in paras:
        page_boundary = cur_loc is not None and loc != cur_loc and loc.startswith("p.")
        if page_boundary or (buf and len(buf) + len(para) + 1 > CHUNK_TARGET):
            flush()
        if not buf:
            cur_loc = loc
        buf = f"{buf}\n{para}".strip() if buf else para
    flush()
    return chunks


# =============================================================================
# 노트북 CRUD
# =============================================================================

def create_notebook(name: str, note: str = "") -> Dict[str, Any]:
    name = (name or "").strip()
    if not name:
        return {"success": False, "error": "name이 필요합니다 — 노트북 이름."}
    with _write_lock:
        conn = _connect()
        try:
            existing = conn.execute("SELECT id FROM notebooks WHERE name=?", (name,)).fetchone()
            if existing:
                return {"success": False, "error": f"'{name}' 노트북이 이미 있습니다. add로 소스를 추가하세요."}
            conn.execute("INSERT INTO notebooks(name, note, created_at, updated_at) VALUES (?,?,?,?)",
                         (name, (note or "").strip(), _now(), _now()))
            conn.commit()
            return {"success": True, "name": name, "note": note or "",
                    "message": f"노트북 '{name}' 생성. add로 소스(path/text/…)를 넣고 ask로 물어보세요."}
        finally:
            conn.close()


def get_notebook(name: str) -> Optional[Dict[str, Any]]:
    conn = _connect()
    try:
        row = conn.execute("SELECT * FROM notebooks WHERE name=?", ((name or "").strip(),)).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


def list_notebooks() -> List[Dict[str, Any]]:
    conn = _connect()
    try:
        # ★두 LEFT JOIN을 한 쿼리에 두면 소스×청크 팬아웃으로 COUNT가 곱해진다(실측 89×901=80,189)
        rows = conn.execute("""
            SELECT n.*, COUNT(DISTINCT s.id) AS source_count, COUNT(DISTINCT c.id) AS chunk_count
            FROM notebooks n
            LEFT JOIN sources s ON s.notebook_id = n.id
            LEFT JOIN chunks c ON c.notebook_id = n.id
            GROUP BY n.id ORDER BY n.updated_at DESC
        """).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def delete_notebook(name: str) -> Dict[str, Any]:
    nb = get_notebook(name)
    if not nb:
        return {"success": False, "error": f"'{name}' 노트북이 없습니다."}
    with _write_lock:
        conn = _connect(with_vec=True)
        try:
            chunk_ids = [r["id"] for r in conn.execute(
                "SELECT id FROM chunks WHERE notebook_id=?", (nb["id"],)).fetchall()]
            _delete_chunk_index(conn, chunk_ids)
            conn.execute("DELETE FROM chunks WHERE notebook_id=?", (nb["id"],))
            conn.execute("DELETE FROM sources WHERE notebook_id=?", (nb["id"],))
            conn.execute("DELETE FROM notebooks WHERE id=?", (nb["id"],))
            conn.commit()
            return {"success": True, "message": f"노트북 '{name}' 삭제 (소스·색인 포함)."}
        finally:
            conn.close()


def _delete_chunk_index(conn: sqlite3.Connection, chunk_ids: List[int]):
    """FTS·vec 색인에서 청크 제거. ★vec0은 DELETE→INSERT만 (sqlite_vec quirk)"""
    for cid in chunk_ids:
        try:
            conn.execute("DELETE FROM chunks_fts WHERE rowid=?", (cid,))
        except sqlite3.OperationalError:
            pass
        try:
            conn.execute("DELETE FROM chunks_vec WHERE rowid=?", (cid,))
        except sqlite3.OperationalError:
            pass  # vec 테이블 없음(FTS-only 모드)


# =============================================================================
# 소스 add / remove / 목록
# =============================================================================

def add_source(name: str, path: str = "", text: str = "", title: str = "") -> Dict[str, Any]:
    nb = get_notebook(name)
    if not nb:
        return {"success": False, "error": f"'{name}' 노트북이 없습니다. 먼저 op:create."}

    if text and text.strip():
        paras = _paragraphs_with_loc(text)
        if not paras:
            return {"success": False, "error": "text가 너무 짧습니다(문단 없음)."}
        src_title = (title or "").strip() or f"붙여넣기 {datetime.now().strftime('%m/%d %H:%M')}"
        kind, src_path, mtime = "text", "", 0.0
    elif path and str(path).strip() and is_url(str(path)):
        # URL 소스 (Phase 2) — 유튜브=자막(loc=타임스탬프) / 그 외=본문 추출
        src_path = str(path).strip()
        if _youtube_id(src_path):
            paras, auto_title, err = _extract_youtube(src_path)
            kind = "youtube"
        else:
            paras, auto_title, err = _extract_web(src_path)
            kind = "url"
        if err:
            return {"success": False, "error": err}
        src_title = (title or "").strip() or auto_title or src_path
        mtime = 0.0
    elif path and str(path).strip():
        src_path = os.path.abspath(expand_body_path(str(path).strip()))
        if not os.path.isfile(src_path):
            return {"success": False, "error": f"파일이 없습니다: {src_path}"}
        paras, err = extract_file(src_path)
        if err:
            return {"success": False, "error": err}
        if not paras:
            return {"success": False, "error": "추출된 텍스트가 없습니다(빈 문서)."}
        src_title = (title or "").strip() or os.path.basename(src_path)
        kind, mtime = "file", os.path.getmtime(src_path)
    else:
        return {"success": False, "error": "path(파일 경로 또는 URL) 또는 text(붙여넣기) 중 하나가 필요합니다."}

    chunks = build_chunks(paras)
    char_count = sum(len(c) for _, c in chunks)
    if not chunks:
        return {"success": False, "error": "청크를 만들 수 없습니다(내용 부족)."}

    with _write_lock:
        conn = _connect()
        try:
            dup = conn.execute(
                "SELECT id FROM sources WHERE notebook_id=? AND path=? AND path<>''",
                (nb["id"], src_path)).fetchone() if kind != "text" else None
            if dup:
                _remove_source_rows(nb["id"], dup["id"])  # 같은 파일/URL 재추가 = 재색인
            cur = conn.execute(
                "INSERT INTO sources(notebook_id,title,kind,path,mtime,char_count,chunk_count,status,added_at) "
                "VALUES (?,?,?,?,?,?,?,?,?)",
                (nb["id"], src_title, kind, src_path if kind != "text" else "", mtime,
                 char_count, len(chunks), "indexing", _now()))
            source_id = cur.lastrowid
            conn.execute("UPDATE notebooks SET updated_at=? WHERE id=?", (_now(), nb["id"]))
            conn.commit()
        finally:
            conn.close()

    if char_count > BACKGROUND_THRESHOLD_CHARS:
        t = threading.Thread(target=_index_chunks_job, args=(nb["id"], source_id, src_title, chunks),  # cc-ok: 색인 잡 — queued+source_id 로 관측, 사멸 시 재색인 호출로 복구
                             daemon=True, name=f"nb-index-{source_id}")
        _bg_threads[source_id] = t
        t.start()
        return {"success": True, "queued": True, "source_id": source_id, "title": src_title,
                "chunks": len(chunks), "chars": char_count,
                "message": f"'{src_title}' 색인을 백그라운드로 시작했습니다({len(chunks)}청크). op:sources로 상태 확인."}

    _index_chunks_job(nb["id"], source_id, src_title, chunks)
    st = _source_status(source_id)
    if st and st.get("status") == "error":
        return {"success": False, "source_id": source_id, "error": st.get("error", "색인 실패")}
    mode = "하이브리드(시맨틱+FTS)" if semantic_available() else "FTS5(키워드)만 — 시맨틱 의존성 미로드"
    return {"success": True, "source_id": source_id, "title": src_title,
            "chunks": len(chunks), "chars": char_count,
            "message": f"'{src_title}' 색인 완료 ({len(chunks)}청크, {mode})."}


def _source_exists(conn: sqlite3.Connection, source_id: int) -> bool:
    return conn.execute("SELECT 1 FROM sources WHERE id=?", (source_id,)).fetchone() is not None


def _index_chunks_job(notebook_id: int, source_id: int, src_title: str, chunks: List[Tuple[str, str]]):
    """청크 저장 + FTS + 임베딩. 스레드에서도 안전(자기 연결).
    백그라운드 중 소스가 remove/delete 되면 중단·자기 청소 (레이스 가드)."""
    try:
        with _write_lock:
            conn = _connect(with_vec=True)
            try:
                if not _source_exists(conn, source_id):
                    return  # 색인 시작 전에 소스가 지워짐
                chunk_ids = []
                for seq, (loc, ctext) in enumerate(chunks):
                    cur = conn.execute(
                        "INSERT INTO chunks(notebook_id,source_id,seq,loc,text) VALUES (?,?,?,?,?)",
                        (notebook_id, source_id, seq, loc, ctext))
                    chunk_ids.append(cur.lastrowid)
                    try:
                        conn.execute("INSERT INTO chunks_fts(rowid, text) VALUES (?,?)",
                                     (cur.lastrowid, ctext))
                    except sqlite3.OperationalError:
                        pass
                conn.commit()
            finally:
                conn.close()

        # 임베딩은 락 밖에서 (오래 걸림 — 다른 읽기를 막지 않는다)
        embeddings = _embed_batch([f"{src_title} {c}" for _, c in chunks])

        with _write_lock:
            conn = _connect(with_vec=True)
            try:
                if not _source_exists(conn, source_id):
                    # 임베딩 도는 사이 소스가 지워짐 — 방금 넣은 청크·FTS를 되물린다
                    for cid in chunk_ids:
                        try:
                            conn.execute("DELETE FROM chunks_fts WHERE rowid=?", (cid,))
                        except sqlite3.OperationalError:
                            pass
                    conn.execute("DELETE FROM chunks WHERE source_id=?", (source_id,))
                    conn.commit()
                    return
                if embeddings and _check_sqlite_vec():
                    for cid, emb in zip(chunk_ids, embeddings):
                        conn.execute("DELETE FROM chunks_vec WHERE rowid=?", (cid,))
                        conn.execute("INSERT INTO chunks_vec(rowid, embedding) VALUES (?,?)", (cid, emb))
                    conn.execute("INSERT OR REPLACE INTO meta(key,value) VALUES ('embedding_model',?)",
                                 (EMBEDDING_MODEL,))
                conn.execute("UPDATE sources SET status='ready', error='' WHERE id=?", (source_id,))
                conn.commit()
            finally:
                conn.close()
    except Exception as e:
        logger.error(f"[notebook] 색인 실패 source={source_id}: {e}")
        try:
            conn = _connect()
            conn.execute("UPDATE sources SET status='error', error=? WHERE id=?", (str(e), source_id))
            conn.commit()
            conn.close()
        except Exception:
            pass
    finally:
        _bg_threads.pop(source_id, None)


def _source_status(source_id: int) -> Optional[Dict[str, Any]]:
    conn = _connect()
    try:
        row = conn.execute("SELECT * FROM sources WHERE id=?", (source_id,)).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


def _remove_source_rows(notebook_id: int, source_id: int):
    """소스 행+청크+색인 제거 (호출측이 _write_lock 보유)"""
    conn = _connect(with_vec=True)
    try:
        chunk_ids = [r["id"] for r in conn.execute(
            "SELECT id FROM chunks WHERE source_id=?", (source_id,)).fetchall()]
        _delete_chunk_index(conn, chunk_ids)
        conn.execute("DELETE FROM chunks WHERE source_id=?", (source_id,))
        conn.execute("DELETE FROM sources WHERE id=?", (source_id,))
        conn.commit()
    finally:
        conn.close()


def remove_source(name: str, source_id: Any) -> Dict[str, Any]:
    nb = get_notebook(name)
    if not nb:
        return {"success": False, "error": f"'{name}' 노트북이 없습니다."}
    try:
        sid = int(source_id)
    except (TypeError, ValueError):
        return {"success": False, "error": "source_id(정수)가 필요합니다 — op:sources에서 확인."}
    st = _source_status(sid)
    if not st or st["notebook_id"] != nb["id"]:
        return {"success": False, "error": f"소스 {sid}가 '{name}' 노트북에 없습니다."}
    with _write_lock:
        _remove_source_rows(nb["id"], sid)
    return {"success": True, "message": f"소스 '{st['title']}' 제거(청크 {st['chunk_count']}개 포함)."}


def list_sources(name: str) -> Dict[str, Any]:
    nb = get_notebook(name)
    if not nb:
        return {"success": False, "error": f"'{name}' 노트북이 없습니다."}
    conn = _connect()
    try:
        rows = [dict(r) for r in conn.execute(
            "SELECT * FROM sources WHERE notebook_id=? ORDER BY id", (nb["id"],)).fetchall()]
    finally:
        conn.close()
    for r in rows:
        # lazy 부패 노출 (포식 기억 원리) — 삭제·재색인 판단은 호출자 몫
        if r["kind"] == "file" and r["path"]:
            if not os.path.isfile(r["path"]):
                r["stale"] = "missing"
            elif abs(os.path.getmtime(r["path"]) - (r["mtime"] or 0)) > 1:
                r["stale"] = "modified"    # 재색인 = 같은 path로 add 재호출
    return {"success": True, "notebook": nb["name"], "note": nb.get("note", ""),
            "sources": rows, "semantic": semantic_available()}


# =============================================================================
# 검색 (노트북 스코프 하이브리드)
# =============================================================================

def _search_semantic(notebook_id: int, query: str, top_k: int) -> List[Tuple[int, float]]:
    emb = _embed_one(query)
    if emb is None:
        return []
    conn = _connect(with_vec=True)
    try:
        # vec0 MATCH는 전역 이웃 → 오버페치 후 노트북 필터 (설계 §4-2, 파티션 키 버전 의존 회피)
        k = min(1000, max(top_k * 12, 120))  # clamp-ok: 사용자 요청량이 아니라 top_k 에서 파생된 내부 후보 폭(안전 난간)
        try:
            rows = conn.execute(
                "SELECT rowid, distance FROM chunks_vec WHERE embedding MATCH ? AND k=? ORDER BY distance",
                (emb, k)).fetchall()
        except sqlite3.OperationalError:
            return []
        if not rows:
            return []
        ids = [int(r["rowid"]) for r in rows]
        placeholders = ",".join("?" * len(ids))
        mine = {r["id"] for r in conn.execute(
            f"SELECT id FROM chunks WHERE id IN ({placeholders}) AND notebook_id=?",
            ids + [notebook_id]).fetchall()}
        out = []
        for r in rows:
            rid = int(r["rowid"])
            if rid in mine:
                dist = float(r["distance"])
                out.append((rid, max(0.0, 1.0 - (dist * dist / 2.0))))  # L2정규화 → cos 근사
            if len(out) >= top_k:
                break
        return out
    finally:
        conn.close()


def _search_fts(notebook_id: int, query: str, top_k: int) -> List[Tuple[int, float]]:
    conn = _connect()
    try:
        safe = re.sub(r"[^\w\s가-힣]", " ", query)
        tokens = [t for t in safe.split() if len(t) >= 2]
        if not tokens:
            return []
        fts_query = " OR ".join(tokens)
        try:
            rows = conn.execute(f"""
                SELECT c.id, bm25(chunks_fts) AS score
                FROM chunks_fts f JOIN chunks c ON c.id = f.rowid
                WHERE chunks_fts MATCH ? AND c.notebook_id = ?
                ORDER BY score LIMIT ?
            """, (fts_query, notebook_id, top_k)).fetchall()
        except sqlite3.OperationalError:
            return []
        return [(int(r["id"]), -float(r["score"])) for r in rows]  # bm25는 음수(작을수록 관련)
    finally:
        conn.close()


def _combine(sem: List[Tuple[int, float]], fts: List[Tuple[int, float]], alpha: float) -> List[Tuple[int, float]]:
    combined: Dict[int, float] = {}
    max_s = max((s for _, s in sem), default=1.0) or 1.0
    for i, s in sem:
        combined[i] = alpha * (s / max_s)
    max_f = max((s for _, s in fts), default=1.0) or 1.0
    for i, s in fts:
        combined[i] = combined.get(i, 0.0) + (1 - alpha) * (s / max_f)
    return sorted(combined.items(), key=lambda x: x[1], reverse=True)


def search_chunks(name: str, query: str, top_k: int = 8, alpha: float = DEFAULT_ALPHA) -> Dict[str, Any]:
    """노트북 스코프 하이브리드 검색 → 청크 목록 (LLM 0 — search op 및 ask의 재료)"""
    nb = get_notebook(name)
    if not nb:
        return {"success": False, "error": f"'{name}' 노트북이 없습니다.", "results": []}
    query = (query or "").strip()
    if not query:
        return {"success": False, "error": "q(질문/검색어)가 필요합니다.", "results": []}

    over = max(top_k * 2, 12)
    sem = _search_semantic(nb["id"], query, over) if alpha > 0 else []
    fts = _search_fts(nb["id"], query, over)
    if not sem and not fts:
        return {"success": True, "notebook": nb["name"], "results": [],
                "search_type": "hybrid" if semantic_available() else "fts5"}
    if not sem:
        scored, stype = list(fts), "fts5"
    elif not fts:
        scored, stype = list(sem), "semantic"
    else:
        scored, stype = _combine(sem, fts, alpha), "hybrid"

    ids = [i for i, _ in scored[:top_k]]
    placeholders = ",".join("?" * len(ids))
    conn = _connect()
    try:
        rows = {r["id"]: dict(r) for r in conn.execute(f"""
            SELECT c.id, c.loc, c.text, s.title AS source, s.id AS source_id
            FROM chunks c JOIN sources s ON s.id = c.source_id
            WHERE c.id IN ({placeholders})""", ids).fetchall()}
    finally:
        conn.close()

    results = []
    for cid, score in scored[:top_k]:
        r = rows.get(cid)
        if r:
            r["score"] = round(float(score), 4)
            results.append(r)
    return {"success": True, "notebook": nb["name"], "note": nb.get("note", ""),
            "results": results, "search_type": stype}
