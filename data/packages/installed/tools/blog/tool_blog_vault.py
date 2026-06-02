"""
Blog Vault - Obsidian vault를 블로그 글의 진실 소스(canonical store)로 관리.

설계 (A안: vault = canonical):
- 본인 블로그 글의 원본은 ~/Documents/iRepublic-Vault 의 markdown 파일.
- SQLite DB(blog_insight.db)는 vault에서 재생성되는 검색 인덱스(FTS5 + 벡터) 캐시.
- 새 글/요약이 생기면 .md를 먼저 갱신(canonical)하고 DB에 반영.
- rebuild_db_from_vault()로 언제든 vault만으로 DB 전체 복구 가능.

.md 포맷:
- frontmatter: 모든 메타데이터를 JSON 인코딩 값으로 저장 → 무손실 왕복 보장.
  post_id, title, category, pub_date, url, (keywords), (summary)
- body: 순수 텍스트 본문.
"""

import os
import re
import json
import sqlite3
from typing import Dict, List, Any, Optional, Iterator

# vault 위치 — 환경변수로 덮어쓸 수 있음
VAULT_DIR = os.environ.get(
    "IREPUBLIC_VAULT_DIR",
    os.path.expanduser("~/Documents/iRepublic-Vault"),
)

BLOG_URL = "https://irepublic.tistory.com"

# frontmatter에 담는 메타 키 (순서 고정)
_FRONTMATTER_KEYS = ["post_id", "title", "category", "pub_date", "url", "keywords", "summary"]
_FM_FENCE = "---"
# 분류 없는 글의 폴더
_UNCATEGORIZED = "_분류없음"


# =============================================================================
# 파일시스템 경로
# =============================================================================

def _sanitize_segment(seg: str) -> str:
    """폴더/파일명 한 조각 정리. 슬래시는 호출 측에서 이미 분리됨."""
    seg = seg.strip()
    # 파일시스템에서 문제되는 문자만 치환 (한글/공백/쉼표는 그대로 둠)
    seg = re.sub(r'[\\:*?"<>|]', "_", seg)
    return seg or _UNCATEGORIZED


def category_to_relpath(category: Optional[str]) -> str:
    """'주제별 글모음/세상보기' → ' 주제별 글모음/세상보기' 폴더 경로."""
    if not category or not category.strip():
        return _UNCATEGORIZED
    parts = [_sanitize_segment(p) for p in category.split("/") if p.strip()]
    return os.path.join(*parts) if parts else _UNCATEGORIZED


_MAX_TITLE_LEN = 80


def _safe_title(title: str) -> str:
    """제목을 파일명 안전 문자열로. 위험문자 치환 + 공백 정리 + 길이 제한."""
    title = (title or "").strip()
    # 파일시스템/크로스플랫폼 위험문자 + 위키링크 방해문자(# ^ [ ]) 치환
    title = re.sub(r'[/\\:*?"<>|#^\[\]\r\n\t]', " ", title)
    title = re.sub(r"\s+", " ", title).strip(" .")  # 앞뒤 공백/마침표 제거
    if len(title) > _MAX_TITLE_LEN:
        title = title[:_MAX_TITLE_LEN].rstrip()
    return title or "untitled"


def _date_prefix(pub_date: Optional[str]) -> str:
    """'2026-05-23 15:39:09' → '2026-05-23 '. 날짜 없으면 빈 문자열."""
    if not pub_date:
        return ""
    m = re.match(r"(\d{4}-\d{2}-\d{2})", str(pub_date))
    return f"{m.group(1)} " if m else ""


def filename_for(post: Dict[str, Any]) -> str:
    """post dict → 사람이 읽는 파일명 '{날짜} {제목}.md' (충돌 미해결)."""
    return f"{_date_prefix(post.get('pub_date'))}{_safe_title(post.get('title'))}.md"


def post_dir(category: Optional[str]) -> str:
    """글이 들어갈 폴더 절대경로."""
    return os.path.join(VAULT_DIR, category_to_relpath(category))


def post_md_path(post: Dict[str, Any]) -> str:
    """글 하나의 .md 절대경로. 같은 폴더에 다른 글이 같은 이름이면 post_id 꼬리 추가."""
    directory = post_dir(post.get("category"))
    base = filename_for(post)
    path = os.path.join(directory, base)
    post_id = str(post.get("post_id", ""))
    # 충돌: 이미 존재하고 그 파일의 post_id가 다르면 post_id를 붙여 구분
    if os.path.exists(path):
        try:
            with open(path, "r", encoding="utf-8") as f:
                other = parse_post_md(f.read())
            if other and str(other.get("post_id")) != post_id:
                stem = base[:-3]  # .md 제거
                path = os.path.join(directory, f"{stem} ({post_id}).md")
        except Exception:
            stem = base[:-3]
            path = os.path.join(directory, f"{stem} ({post_id}).md")
    return path


# =============================================================================
# frontmatter 직렬화 / 역직렬화 (JSON 값 → 무손실)
# =============================================================================

def _dump_frontmatter(meta: Dict[str, Any]) -> str:
    lines = [_FM_FENCE]
    for key in _FRONTMATTER_KEYS:
        val = meta.get(key)
        if val is None or val == "":
            continue
        lines.append(f"{key}: {json.dumps(val, ensure_ascii=False)}")
    lines.append(_FM_FENCE)
    return "\n".join(lines)


# 의미 연결(관련 글) 섹션 구분자 — 본문과 분리해 content 순수성 보존.
# HTML 주석이라 Obsidian 표시에는 안 보이고, 그 아래 [[링크]]는 그래프에 정상 반영됨.
_RELATED_MARKER = "<!-- related-links -->"
_RELATED_HEADING = "## 관련 글"


def render_post_md(post: Dict[str, Any]) -> str:
    """post dict → .md 텍스트 전체. related(관련 글 stem 리스트)가 있으면 하단에 추가."""
    post_id = str(post.get("post_id", ""))
    meta = {
        "post_id": post_id,
        "title": post.get("title") or "",
        "category": post.get("category") or "",
        "pub_date": post.get("pub_date") or "",
        "url": f"{BLOG_URL}/{post_id}",
        "keywords": post.get("keywords") or "",
        "summary": post.get("summary") or "",
    }
    fm = _dump_frontmatter(meta)
    title = post.get("title") or ""
    content = post.get("content") or ""
    out = f"{fm}\n\n# {title}\n\n{content}\n"
    related = post.get("related") or []
    if related:
        links = "\n".join(f"- [[{stem}]]" for stem in related)
        out += f"\n{_RELATED_MARKER}\n{_RELATED_HEADING}\n{links}\n"
    return out


def parse_post_md(text: str) -> Optional[Dict[str, Any]]:
    """.md 텍스트 → post dict. frontmatter + 본문 복원."""
    if not text.startswith(_FM_FENCE):
        return None
    # 첫 fence 이후 두 번째 fence까지가 frontmatter
    rest = text[len(_FM_FENCE):]
    end = rest.find("\n" + _FM_FENCE)
    if end == -1:
        return None
    fm_block = rest[:end].strip("\n")
    body = rest[end + 1 + len(_FM_FENCE):]

    meta: Dict[str, Any] = {}
    for line in fm_block.split("\n"):
        if not line.strip() or ":" not in line:
            continue
        key, _, raw = line.partition(":")
        key = key.strip()
        raw = raw.strip()
        try:
            meta[key] = json.loads(raw)
        except (ValueError, json.JSONDecodeError):
            meta[key] = raw.strip('"')

    # 관련 글 섹션 분리 (있으면) — content에 섞이지 않도록 먼저 떼어냄
    related: List[str] = []
    if _RELATED_MARKER in body:
        body, related_part = body.split(_RELATED_MARKER, 1)
        related = re.findall(r"\[\[([^\]]+)\]\]", related_part)

    # 본문: 맨 앞의 "# 제목\n\n" 헤더를 제거하고 순수 content 복원
    body = body.lstrip("\n")
    title = meta.get("title", "")
    header = f"# {title}\n\n"
    if body.startswith(header):
        body = body[len(header):]
    elif body.startswith("# "):
        # 제목이 약간 달라도 첫 헤더 라인 제거
        nl = body.find("\n\n")
        if nl != -1:
            body = body[nl + 2:]
    content = body.rstrip("\n")

    if not meta.get("post_id"):
        return None
    return {
        "post_id": str(meta["post_id"]),
        "title": meta.get("title", ""),
        "category": meta.get("category", ""),
        "pub_date": meta.get("pub_date", ""),
        "content": content,
        "summary": meta.get("summary", ""),
        "keywords": meta.get("keywords", ""),
        "related": related,
    }


# =============================================================================
# 쓰기 (canonical 갱신)
# =============================================================================

def write_post_md(post: Dict[str, Any]) -> str:
    """글 하나를 vault에 기록(생성/덮어쓰기). 절대경로 반환.
    파일명은 '{날짜} {제목}.md'. 같은 글이 다른 이름으로 이미 있으면 옮김."""
    existing = find_post_md(str(post.get("post_id", "")))
    path = post_md_path(post)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(render_post_md(post))
    # 같은 post_id의 옛 파일이 다른 경로에 있으면 정리(제목/카테고리 변경 대비)
    if existing and os.path.abspath(existing) != os.path.abspath(path):
        try:
            os.remove(existing)
        except Exception:
            pass
    return path


def update_post_summary_md(post_id: str, summary: str, keywords: str = "") -> Optional[str]:
    """기존 .md의 요약/키워드만 갱신. 글 위치를 찾아 frontmatter만 다시 씀."""
    existing = find_post_md(post_id)
    if not existing:
        return None
    with open(existing, "r", encoding="utf-8") as f:
        post = parse_post_md(f.read())
    if not post:
        return None
    post["summary"] = summary
    post["keywords"] = keywords
    with open(existing, "w", encoding="utf-8") as f:
        f.write(render_post_md(post))
    return existing


def find_post_md(post_id: str) -> Optional[str]:
    """post_id로 .md 파일 경로 탐색. 파일명이 제목 기반이라 frontmatter를 본다."""
    post_id = str(post_id)
    if not os.path.isdir(VAULT_DIR):
        return None
    needle = f'post_id: "{post_id}"'
    for root, _dirs, files in os.walk(VAULT_DIR):
        if ".obsidian" in root:
            continue
        for name in files:
            if not name.endswith(".md"):
                continue
            path = os.path.join(root, name)
            try:
                # frontmatter만 보면 충분 — 앞부분만 읽음
                with open(path, "r", encoding="utf-8") as f:
                    head = f.read(1024)
            except Exception:
                continue
            if needle in head:
                return path
    return None


# =============================================================================
# 읽기 (vault 순회)
# =============================================================================

def iter_vault_posts() -> Iterator[Dict[str, Any]]:
    """vault의 모든 .md를 파싱해 post dict로 순회."""
    if not os.path.isdir(VAULT_DIR):
        return
    for root, _dirs, files in os.walk(VAULT_DIR):
        if ".obsidian" in root:
            continue
        for name in files:
            if not name.endswith(".md"):
                continue
            try:
                with open(os.path.join(root, name), "r", encoding="utf-8") as f:
                    post = parse_post_md(f.read())
                if post:
                    yield post
            except Exception:
                continue


def rename_existing_to_titles() -> Dict[str, Any]:
    """일회성: vault의 기존 .md 파일명을 '{날짜} {제목}.md' 규칙으로 일괄 변경.
    내용은 그대로, 파일명만 바꾼다. frontmatter의 post_id가 정체성이라 안전."""
    # 먼저 (현재경로, post) 수집 후 순차 리네임 (walk 중 변경 회피)
    entries = []
    for root, _dirs, files in os.walk(VAULT_DIR):
        if ".obsidian" in root:
            continue
        for name in files:
            if not name.endswith(".md"):
                continue
            path = os.path.join(root, name)
            try:
                with open(path, "r", encoding="utf-8") as f:
                    post = parse_post_md(f.read())
            except Exception:
                post = None
            if post and post.get("post_id"):
                entries.append((path, post))

    renamed = 0
    unchanged = 0
    errors = []
    for cur, post in entries:
        try:
            target = post_md_path(post)  # 충돌 시 post_id 꼬리 자동 부여
            if os.path.abspath(cur) == os.path.abspath(target):
                unchanged += 1
                continue
            os.makedirs(os.path.dirname(target), exist_ok=True)
            os.rename(cur, target)
            renamed += 1
        except Exception as e:
            errors.append(f"{post.get('post_id')}: {e}")

    return {
        "success": True,
        "vault_dir": VAULT_DIR,
        "renamed": renamed,
        "unchanged": unchanged,
        "errors": errors[:20],
        "error_count": len(errors),
    }


def _vault_index() -> Dict[str, str]:
    """vault 1회 순회 → {post_id: 파일 절대경로}."""
    idx: Dict[str, str] = {}
    if not os.path.isdir(VAULT_DIR):
        return idx
    for root, _dirs, files in os.walk(VAULT_DIR):
        if ".obsidian" in root:
            continue
        for name in files:
            if not name.endswith(".md"):
                continue
            path = os.path.join(root, name)
            try:
                with open(path, "r", encoding="utf-8") as f:
                    head = f.read(1024)
            except Exception:
                continue
            m = re.search(r'post_id:\s*"([^"]+)"', head)
            if m:
                idx[m.group(1)] = path
    return idx


def build_semantic_links(k: int = 6, min_sim: float = 0.55) -> Dict[str, Any]:
    """해마 임베딩으로 각 글의 의미적 이웃 top-k를 계산해 '## 관련 글' [[링크]]를
    .md 하단에 기록. Obsidian 그래프가 의미 기반으로 연결된다.
    본문 없는(임베딩 없는) 짧은 글은 대상에서 제외된다."""
    import numpy as np
    import sqlite_vec

    # 1) 임베딩 로드 (posts.id → vector)
    conn = _db()
    conn.enable_load_extension(True)
    sqlite_vec.load(conn)
    rows = conn.execute("SELECT rowid, embedding FROM posts_vec").fetchall()
    if not rows:
        conn.close()
        return {"success": False, "error": "임베딩 없음 — 먼저 인덱싱 필요"}
    ids = [r[0] for r in rows]
    mat = np.vstack([np.frombuffer(r[1], dtype=np.float32) for r in rows])
    # 정규화 보장 (혹시 모를 비정규 대비)
    norms = np.linalg.norm(mat, axis=1, keepdims=True)
    norms[norms == 0] = 1.0
    mat = mat / norms

    # 2) posts.id → post_id, post_id → 파일 stem 매핑
    id_to_pid = {row[0]: str(row[1]) for row in
                 conn.execute("SELECT id, post_id FROM posts").fetchall()}
    conn.close()
    pid_to_path = _vault_index()

    n = len(ids)
    kk = min(k + 1, n)  # 자기 자신 포함 → +1
    linked = 0
    skipped_no_file = 0
    errors = []

    # 3) 행 단위로 유사도 계산 (메모리 절약: 청크)
    CHUNK = 512
    for start in range(0, n, CHUNK):
        block = mat[start:start + CHUNK]          # (b, 768)
        sims = block @ mat.T                       # (b, n) 코사인
        # 각 행 top-kk (자기 포함)
        part = np.argpartition(-sims, kk - 1, axis=1)[:, :kk]
        for bi in range(block.shape[0]):
            gi = start + bi                        # 전체 인덱스
            src_pid = id_to_pid.get(ids[gi])
            src_path = pid_to_path.get(src_pid) if src_pid else None
            if not src_path:
                skipped_no_file += 1
                continue
            # 이웃 정렬 (자기 제외, 임계값 이상)
            cand = part[bi]
            cand = cand[np.argsort(-sims[bi, cand])]
            neighbor_stems = []
            for ci in cand:
                if ci == gi:
                    continue
                if float(sims[bi, ci]) < min_sim:
                    continue
                npid = id_to_pid.get(ids[ci])
                npath = pid_to_path.get(npid) if npid else None
                if not npath:
                    continue
                neighbor_stems.append(os.path.basename(npath)[:-3])  # .md 제거
                if len(neighbor_stems) >= k:
                    break
            # 4) 파일 갱신 (content/summary 보존, related만 교체)
            try:
                with open(src_path, "r", encoding="utf-8") as f:
                    post = parse_post_md(f.read())
                if not post:
                    continue
                post["related"] = neighbor_stems
                with open(src_path, "w", encoding="utf-8") as f:
                    f.write(render_post_md(post))
                if neighbor_stems:
                    linked += 1
            except Exception as e:
                errors.append(f"{src_pid}: {e}")

    return {
        "success": True,
        "vault_dir": VAULT_DIR,
        "embedded_posts": n,
        "linked": linked,
        "k": k,
        "min_sim": min_sim,
        "skipped_no_file": skipped_no_file,
        "errors": errors[:20],
        "error_count": len(errors),
    }


def vault_stats() -> Dict[str, Any]:
    """vault 현황."""
    total = 0
    with_summary = 0
    for p in iter_vault_posts():
        total += 1
        if p.get("summary"):
            with_summary += 1
    return {
        "vault_dir": VAULT_DIR,
        "exists": os.path.isdir(VAULT_DIR),
        "total_posts": total,
        "with_summary": with_summary,
    }


# =============================================================================
# DB <-> vault 브리지
# =============================================================================

_DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")
_DB_PATH = os.path.join(_DATA_DIR, "blog_insight.db")


def _db() -> sqlite3.Connection:
    conn = sqlite3.connect(_DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def export_all() -> Dict[str, Any]:
    """일회성: DB의 모든 글(+요약)을 vault .md로 내보냄. 기존 .md는 덮어씀."""
    if not os.path.exists(_DB_PATH):
        return {"success": False, "error": f"DB 없음: {_DB_PATH}"}
    conn = _db()
    rows = conn.execute(
        """
        SELECT p.post_id, p.title, p.category, p.pub_date, p.content,
               s.summary, s.keywords
        FROM posts p LEFT JOIN summaries s ON p.post_id = s.post_id
        ORDER BY p.pub_date
        """
    ).fetchall()
    conn.close()

    written = 0
    with_summary = 0
    errors = []
    for row in rows:
        try:
            post = {
                "post_id": row["post_id"],
                "title": row["title"],
                "category": row["category"],
                "pub_date": row["pub_date"],
                "content": row["content"],
                "summary": row["summary"] or "",
                "keywords": row["keywords"] or "",
            }
            write_post_md(post)
            written += 1
            if post["summary"]:
                with_summary += 1
        except Exception as e:
            errors.append(f"{row['post_id']}: {e}")

    return {
        "success": True,
        "vault_dir": VAULT_DIR,
        "exported": written,
        "with_summary": with_summary,
        "errors": errors[:20],
        "error_count": len(errors),
    }


def rebuild_db_from_vault(reindex: bool = True) -> Dict[str, Any]:
    """복구용: vault .md만으로 DB(posts/summaries)를 전면 재구축.
    reindex=True면 FTS5 재구축 + 벡터 임베딩 재생성까지 수행."""
    posts = list(iter_vault_posts())
    if not posts:
        return {"success": False, "error": f"vault에 글 없음: {VAULT_DIR}"}

    conn = _db()
    try:
        # posts 삭제 → FTS delete 트리거가 동작. summaries도 비움.
        conn.execute("DELETE FROM posts")
        conn.execute("DELETE FROM summaries")
        conn.commit()

        ins_posts = 0
        ins_summaries = 0
        for p in posts:
            content = p.get("content") or ""
            conn.execute(
                """INSERT OR IGNORE INTO posts (post_id, title, category, pub_date, content, char_count)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (p["post_id"], p.get("title", ""), p.get("category", ""),
                 p.get("pub_date") or None, content, len(content)),
            )
            ins_posts += 1
            if p.get("summary"):
                conn.execute(
                    "INSERT OR REPLACE INTO summaries (post_id, summary, keywords) VALUES (?, ?, ?)",
                    (p["post_id"], p["summary"], p.get("keywords", "")),
                )
                ins_summaries += 1
        conn.commit()
        # FTS5 안전 재구축
        try:
            conn.execute("INSERT INTO posts_fts(posts_fts) VALUES('rebuild')")
            conn.commit()
        except Exception:
            pass
    finally:
        conn.close()

    result = {
        "success": True,
        "vault_dir": VAULT_DIR,
        "posts": ins_posts,
        "summaries": ins_summaries,
    }

    # 벡터 인덱스 재생성 (모델 로드 필요 — 무거움)
    if reindex:
        try:
            from tool_blog_rag import BlogHybridSearch
            engine = BlogHybridSearch()
            rb = engine.rebuild_index()
            result["vector_reindex"] = rb
        except Exception as e:
            result["vector_reindex"] = {"success": False, "error": str(e)}

    return result
