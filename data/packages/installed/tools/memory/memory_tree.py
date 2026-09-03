"""
memory_tree.py — 심층 기억의 **주제 트리 문서**(정본) + 목차(지도)

2026-09-03 사용자 판정: "심층기억을 평면으로 보관하지 말고 폴더 구조로 정리하면 블로그와 같다.
기억이 발생할 때마다 어디에 넣을지 판단하는 것도 AI 가 할 일."

원리
- 평면 표(memories) 위에 **주제 노드**(`node` 컬럼, `가족/어머니` 꼴의 경로)를 얹는다. 종류
  (사용자선호·의사결정…)는 축이 아니라 줄마다 붙는 표식으로 내려간다.
- 노드마다 문서 하나: `<DB 옆>/memory_tree_<자아>/<노드 경로>/memory.md`. 문서가 정본, DB 는 색인
  (포식 기억 forage_doc 와 같은 배치). 문서 = 표식 + 제목 + `> 한 줄 요약`(목차에 실린다) + AI 산문
  + `## 기억` 기계 절(한 줄 = 기억 하나) + `## 갱신 기록`.
- **지도(목차)는 작아서 항상 올린다**, 가지의 내용은 AI 가 `[self:memory]{op:"recall", node}` 로 연다.
  (벡터 Top-3 자동 주입 폐지 — 단서는 질문이 아니라 지도에서 온다.)
- **어디에 넣을지는 AI 가 정한다**: 증류기가 지도를 보고 node 를 적는다(기존 노드 우선, 새 주제면 새 경로).
  이 모듈은 분류기를 두지 않는다 — 파일 위치·문서 렌더·문서→색인 동기화(사람이 고친 줄)만 한다.
"""
import os
import re
import sqlite3
from datetime import datetime
from typing import Any, Callable, Dict, List, Optional, Tuple

DOC_NAME = "memory.md"
SECTION = "## 기억"
LEDGER = "## 갱신 기록"
MARKER_RE = re.compile(r'<!--\s*memory-node\s+agent="([^"]*)"\s+node="([^"]*)"\s*-->')
LINE_RE = re.compile(r'^- \[([^\]]*)\]\s+(.*?)\s*‹#(\d+)[^›]*›\s*$')      # 색인된 줄(#id 보유)
NEW_LINE_RE = re.compile(r'^- \[([^\]]*)\]\s+(.+?)\s*(?:‹[^›]*›)?\s*$')   # 사람이 새로 적은 줄(#id 없음)
SECTION_NOTE = ("<!-- 기계가 읽는 절: 한 줄 = 기억 하나 `- [분류] 내용 ‹#id · 날짜 · kw: …›`. "
                "줄을 고치면 색인이 따라오고(recall 이 문서 시각을 본다), 줄을 지우면 색인에서도 지워지며, "
                "#id 없이 `- [분류] 내용` 을 적으면 새 기억이 된다. 다른 절(요약·산문)은 자유롭게 쓴다. -->")
GIST_PLACEHOLDER = "(한 줄 요약 — 이 가지에 무엇이 있나. AI 가 채운다; 목차에 실린다)"
MAX_DEPTH = 4


# ─────────────────────────── 위치 ───────────────────────────

def tree_dir(db_path: str) -> str:
    """DB 옆의 트리 폴더: memory_<자아>.db → memory_tree_<자아>/"""
    d, base = os.path.split(os.path.abspath(db_path))
    stem = os.path.splitext(base)[0]
    who = stem[len("memory_"):] if stem.startswith("memory_") else stem
    return os.path.join(d, f"memory_tree_{who or 'default'}")


def agent_label(db_path: str) -> str:
    stem = os.path.splitext(os.path.basename(db_path))[0]
    return stem[len("memory_"):] if stem.startswith("memory_") else stem


def norm_node(node: Optional[str]) -> str:
    """'가족 / 어머니 /' → '가족/어머니'. 빈 값 = 뿌리. 상위 이동(..)·너무 깊은 경로는 잘라낸다."""
    parts = []
    for seg in str(node or "").replace("\\", "/").split("/"):
        seg = re.sub(r"\s+", " ", seg).strip().strip(".")
        if seg:
            parts.append(seg)
    return "/".join(parts[:MAX_DEPTH])


def node_dir(db_path: str, node: str) -> str:
    n = norm_node(node)
    return os.path.join(tree_dir(db_path), *n.split("/")) if n else tree_dir(db_path)


def doc_path(db_path: str, node: str) -> str:
    return os.path.join(node_dir(db_path, node), DOC_NAME)


def parent_of(node: str) -> Optional[str]:
    n = norm_node(node)
    if not n:
        return None
    return n.rsplit("/", 1)[0] if "/" in n else ""


# ─────────────────────────── 색인(DB) ───────────────────────────

def _conn(db_path: str) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path, timeout=10)
    conn.row_factory = sqlite3.Row
    return conn


def ensure_column(db_path: str) -> None:
    """memories.node 컬럼 보장(옛 DB 이전). memory_db 스키마 보장에서도 부른다."""
    conn = sqlite3.connect(db_path, timeout=10)
    try:
        try:
            conn.execute("SELECT node FROM memories LIMIT 1")
        except sqlite3.OperationalError:
            try:
                conn.execute("ALTER TABLE memories ADD COLUMN node TEXT DEFAULT ''")
                conn.commit()
            except sqlite3.OperationalError:
                pass   # memories 표 자체가 없는 빈 DB — 첫 save 가 만든다
    finally:
        conn.close()


def rows_of(db_path: str, node: str) -> List[Dict[str, Any]]:
    """이 노드에 **직접** 속한 행(하위 노드의 행은 각자 문서에)."""
    ensure_column(db_path)
    conn = _conn(db_path)
    try:
        rows = conn.execute(
            "SELECT id, category, keywords, content, created_at, used_at, node FROM memories "
            "WHERE COALESCE(node,'') = ? ORDER BY created_at, id", (norm_node(node),)).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def node_counts(db_path: str) -> Dict[str, int]:
    ensure_column(db_path)
    conn = _conn(db_path)
    try:
        rows = conn.execute("SELECT COALESCE(node,'') AS n, COUNT(*) AS c FROM memories GROUP BY n").fetchall()
        return {norm_node(r["n"]): r["c"] for r in rows}
    except sqlite3.OperationalError:
        return {}
    finally:
        conn.close()


def all_nodes(db_path: str) -> List[str]:
    """DB 에 행이 있는 노드 ∪ 디스크에 문서가 있는 노드(행 0개여도 AI 가 만든 가지) ∪ 그 조상들."""
    nodes = set(node_counts(db_path).keys())
    root = tree_dir(db_path)
    if os.path.isdir(root):
        for cur, _dirs, files in os.walk(root):
            if DOC_NAME in files:
                rel = os.path.relpath(cur, root)
                nodes.add("" if rel == "." else norm_node(rel.replace(os.sep, "/")))
    for n in list(nodes):
        p = parent_of(n)
        while p is not None:
            nodes.add(p)
            p = parent_of(p)
    nodes.add("")
    return sorted(nodes, key=lambda s: (s.count("/"), s))


def children_of(db_path: str, node: str) -> List[str]:
    n = norm_node(node)
    out = []
    for m in all_nodes(db_path):
        if m and parent_of(m) == n:
            out.append(m)
    return out


def unfiled(db_path: str) -> List[Dict[str, Any]]:
    """아직 노드가 없는 행(뿌리에 놓인 것) — 옛 평면 기억, 또는 증류가 node 를 못 적은 것."""
    return rows_of(db_path, "")


# ─────────────────────────── 문서 렌더 ───────────────────────────

def _one_line(text: str) -> str:
    return re.sub(r"\s*\n+\s*", " ", (text or "").strip())


def _norm_content(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "")).strip()


def render_line(r: Dict[str, Any]) -> str:
    date = (r.get("created_at") or "")[:10]
    meta = [f"#{r['id']}", date]
    kw = (r.get("keywords") or "").strip()
    if kw:
        meta.append(f"kw: {kw[:80]}")
    return f"- [{r.get('category') or '기타'}] {_one_line(r.get('content'))} ‹{' · '.join(m for m in meta if m)}›"


def render_section(rows: List[Dict[str, Any]]) -> str:
    body = [SECTION, SECTION_NOTE]
    body.extend(render_line(r) for r in rows)
    return "\n".join(body) + "\n"


def _split_section(text: str) -> Tuple[str, str, str]:
    """(앞, 절, 뒤) — 절이 없으면 절='' 이고 뒤는 '## 갱신 기록' 부터."""
    m = re.search(r"(?m)^## 기억\s*$", text)
    if m:
        start = m.start()
        nxt = re.search(r"(?m)^## ", text[m.end():])
        end = m.end() + nxt.start() if nxt else len(text)
        return text[:start], text[start:end], text[end:]
    lm = re.search(r"(?m)^## 갱신 기록\s*$", text)
    if lm:
        return text[:lm.start()], "", text[lm.start():]
    return text, "", ""


def _replace_section(text: str, section: str) -> str:
    head, _old, tail = _split_section(text)
    if head and not head.endswith("\n\n"):
        head = head.rstrip("\n") + "\n\n"
    if tail and not tail.startswith("\n"):
        section = section + "\n"
    return head + section + tail


def _marker(agent: str, node: str) -> str:
    return f'<!-- memory-node agent="{agent}" node="{norm_node(node)}" -->'


def _read_marker(path: str) -> Optional[Tuple[str, str]]:
    try:
        with open(path, encoding="utf-8") as f:
            head = f.read(1500)
    except OSError:
        return None
    m = MARKER_RE.search(head)
    return (m.group(1), norm_node(m.group(2))) if m else None


def gist_of(path: str) -> str:
    """표식 뒤 첫 `> ` 줄 = 목차에 실리는 한 줄 요약."""
    try:
        with open(path, encoding="utf-8") as f:
            text = f.read(3000)
    except OSError:
        return ""
    m = re.search(r"(?m)^>\s*(.+?)\s*$", text)
    g = m.group(1).strip() if m else ""
    return "" if g.startswith("(한 줄 요약") else g


def _stamp_key(node: str) -> str:
    return f"tree_stamp:{norm_node(node)}"


def _stamp(db_path: str, node: str, path: str) -> None:
    import memory_db
    try:
        memory_db.set_meta(db_path, _stamp_key(node), str(os.path.getmtime(path)))
    except Exception:
        pass


def refresh_node(db_path: str, node: str, agent: Optional[str] = None) -> str:
    """DB → 문서(`## 기억` 절만 다시 그린다; 요약·산문·갱신 기록은 보존). 문서가 없으면 껍데기 생성."""
    node = norm_node(node)
    agent = agent or agent_label(db_path)
    path = doc_path(db_path, node)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    if os.path.exists(path):
        text = open(path, encoding="utf-8").read()
        if not MARKER_RE.search(text[:1500]):
            text = _marker(agent, node) + "\n" + text
    else:
        title = node or "(뿌리)"
        text = (f"{_marker(agent, node)}\n# 기억 — {title}\n> {GIST_PLACEHOLDER}\n\n"
                f"{LEDGER}\n- {datetime.now().strftime('%Y-%m-%d')} 가지 생성\n")
    text = _replace_section(text, render_section(rows_of(db_path, node)))
    with open(path, "w", encoding="utf-8") as f:
        f.write(text)
    _stamp(db_path, node, path)
    return path


def refresh_all(db_path: str) -> List[str]:
    return [refresh_node(db_path, n) for n in all_nodes(db_path)]


# ─────────────────────────── 문서 → 색인 (사람이 고친 줄) ───────────────────────────

def parse_section(text: str) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    """(색인된 줄[{id,category,content}], 새 줄[{category,content}])"""
    _h, sec, _t = _split_section(text)
    known, fresh = [], []
    for line in sec.splitlines():
        if not line.startswith("- ["):
            continue
        m = LINE_RE.match(line)
        if m:
            known.append({"category": m.group(1).strip(), "content": m.group(2).strip(), "id": int(m.group(3))})
            continue
        m = NEW_LINE_RE.match(line)
        if m and m.group(2).strip():
            fresh.append({"category": m.group(1).strip(), "content": m.group(2).strip()})
    return known, fresh


def sync_node(db_path: str, node: str) -> Dict[str, Any]:
    """문서가 마지막 렌더보다 새로우면 절을 읽어 색인에 반영: 고친 줄=UPDATE · 지운 줄=DELETE · 새 줄=INSERT.
    반영 뒤 다시 그려(새 줄에 #id 부여) 도장을 찍는다."""
    import memory_db
    node = norm_node(node)
    path = doc_path(db_path, node)
    if not os.path.exists(path):
        return {"synced": False, "reason": "no_doc"}
    try:
        mtime = os.path.getmtime(path)
        stamp = float(memory_db.get_meta(db_path, _stamp_key(node)) or 0)
    except Exception:
        mtime, stamp = 1.0, 0.0
    if mtime <= stamp + 1e-6:
        return {"synced": False, "reason": "fresh"}
    text = open(path, encoding="utf-8").read()
    known, fresh = parse_section(text)
    existing = {r["id"]: r for r in rows_of(db_path, node)}
    updated = deleted = inserted = 0
    rejected: List[str] = []
    conn = sqlite3.connect(db_path, timeout=10)
    try:
        now = datetime.now().isoformat()
        seen = set()
        for k in known:
            r = existing.get(k["id"])
            if r is None:
                fresh.append({"category": k["category"], "content": k["content"]})   # 색인에 없는 id → 새 기억으로
                continue
            seen.add(k["id"])
            cat = memory_db.normalize_category(k["category"])
            if _norm_content(k["content"]) != _norm_content(r["content"]) or cat != (r.get("category") or ""):
                conn.execute("UPDATE memories SET content=?, category=?, used_at=? WHERE id=?",
                             (memory_db.mask_secrets(k["content"]), cat, now, k["id"]))
                updated += 1
                memory_db._index_one(db_path, k["id"], k["content"], r.get("keywords") or "", cat)
        for mid in set(existing) - seen:
            conn.execute("DELETE FROM memories WHERE id=?", (mid,))
            deleted += 1
            memory_db._delete_vec(db_path, mid)
        for f in fresh:
            try:
                memory_db._reject_body_noun(f["content"])
            except Exception as e:
                rejected.append(f"{f['content'][:40]} — {e}")
                continue
            cat = memory_db.normalize_category(f["category"])
            cur = conn.execute(
                "INSERT INTO memories (category, keywords, content, created_at, source_ref, node) VALUES (?,?,?,?,?,?)",
                (cat, "", memory_db.mask_secrets(f["content"]), now, '{"utterance": "문서에서 직접 적음"}', node))
            inserted += 1
            memory_db._index_one(db_path, cur.lastrowid, f["content"], "", cat)
        conn.commit()
    finally:
        conn.close()
    refresh_node(db_path, node)
    out = {"synced": True, "updated": updated, "deleted": deleted, "inserted": inserted}
    if rejected:
        out["rejected"] = rejected
    return out


def sync_all(db_path: str) -> Dict[str, int]:
    """모든 노드 문서의 시각을 대조(싸다) — 고쳐진 문서만 색인에 반영."""
    n = 0
    for node in all_nodes(db_path):
        if sync_node(db_path, node).get("synced"):
            n += 1
    return {"synced_docs": n}


# ─────────────────────────── 지도(목차) · 회상 · 이동 ───────────────────────────

def map_lines(db_path: str) -> List[Dict[str, Any]]:
    counts = node_counts(db_path)
    out = []
    for n in all_nodes(db_path):
        p = doc_path(db_path, n)
        out.append({"node": n, "count": counts.get(n, 0), "gist": gist_of(p) if os.path.exists(p) else "",
                    "doc": p if os.path.exists(p) else None})
    return out


def map_text(db_path: str) -> str:
    """항상 올리는 목차 — 한 노드 한 줄 `- 노드 (n) — 요약`. 비어 있으면 빈 문자열."""
    lines = []
    for row in map_lines(db_path):
        if row["node"] == "" and row["count"] == 0:
            continue
        label = row["node"] or "(뿌리 — 아직 가지가 없는 기억)"
        s = f"- {label} ({row['count']})"
        if row["gist"]:
            s += f" — {row['gist']}"
        lines.append(s)
    return "\n".join(lines)


def recall(db_path: str, node: str) -> Dict[str, Any]:
    """한 가지를 연다: 문서 전문 + 그 노드의 행 + 하위 노드 목록. 문서가 고쳐졌으면 먼저 색인에 반영."""
    node = norm_node(node)
    sync_node(db_path, node)
    path = doc_path(db_path, node)
    if not os.path.exists(path) and node not in all_nodes(db_path):
        return {"success": False, "node": node, "error": f"없는 가지: '{node}' — 지도(목차)의 이름을 쓰거나 save 에 node 를 붙여 새 가지를 만든다.",
                "nodes": [m["node"] for m in map_lines(db_path) if m["node"]]}
    if not os.path.exists(path):
        refresh_node(db_path, node)
    rows = rows_of(db_path, node)
    counts = node_counts(db_path)
    return {"success": True, "node": node, "doc": path, "text": open(path, encoding="utf-8").read(),
            "items": rows, "count": len(rows),
            "children": [{"node": c, "count": counts.get(c, 0), "gist": gist_of(doc_path(db_path, c))} for c in children_of(db_path, node)],
            "parent": parent_of(node)}


def move(db_path: str, memory_id: int, node: str) -> Dict[str, Any]:
    ensure_column(db_path)
    node = norm_node(node)
    conn = _conn(db_path)
    try:
        row = conn.execute("SELECT COALESCE(node,'') AS node FROM memories WHERE id=?", (memory_id,)).fetchone()
        if not row:
            return {"success": False, "error": f"memory_id {memory_id} 없음"}
        old = norm_node(row["node"])
        conn.execute("UPDATE memories SET node=? WHERE id=?", (node, memory_id))
        conn.commit()
    finally:
        conn.close()
    refresh_node(db_path, old)
    refresh_node(db_path, node)
    return {"success": True, "memory_id": memory_id, "from": old, "to": node}


# ─────────────────────────── 미배치 행 배치(AI 몫 — 판단은 모델, 여기는 왕복만) ───────────────────────────

FILE_PROMPT = """아래는 한 자아의 기억 지도(주제 가지)와, 아직 가지가 없는 기억들이다.
각 기억을 **가장 알맞은 가지**에 넣어라. 규칙:
- 기존 가지를 우선한다. 정말 새 주제면 새 경로를 만들어도 된다(`상위/하위` 꼴, 최대 3단, 한국어 명사).
- 종류(선호·결정·날짜)는 가지가 아니다 — 가지는 **무엇에 관한 기억인가**(사람·장소·일·물건·주제)로 나눈다.
- 한두 건짜리 가지를 만들지 마라 — 여럿이 모일 주제만 새 가지, 아니면 가장 가까운 기존 가지에 둔다.
- 확신이 없으면 상위 가지에 둔다. 판단 불가면 빈 문자열.

[기억 지도]
{map}

[배치할 기억]
{rows}

JSON 객체로만 응답: {{"<id>": "<가지 경로>", ...}}"""


def file_unfiled(db_path: str, ai_call: Callable[[str, str], Optional[str]], batch: int = 30,
                 extra_map: str = "") -> Dict[str, Any]:
    """node 가 빈 행을 모델에게 배치시킨다. ai_call(prompt, system_prompt) -> str(JSON).
    extra_map: 아직 문서가 없는 설계 가지(사람/AI 가 미리 그린 트리)를 지도에 덧붙일 때."""
    import json
    rows = unfiled(db_path)
    filed, skipped, new_nodes = 0, 0, set()
    known = set(all_nodes(db_path))
    for i in range(0, len(rows), batch):
        chunk = rows[i:i + batch]
        m = map_text(db_path)
        if extra_map:
            m = (m + "\n" + extra_map).strip()
        listing = "\n".join(f"{r['id']}: [{r.get('category') or '기타'}] {_one_line(r['content'])[:300]}" for r in chunk)
        resp = ai_call(FILE_PROMPT.format(map=m or "(아직 가지 없음)", rows=listing),
                       "기억 배치기. JSON 객체로만 응답.")
        try:
            from runtime_utils import parse_first_json
            verdict = parse_first_json(resp or "") or {}
        except Exception:
            try:
                verdict = json.loads(resp or "{}")
            except Exception:
                verdict = {}
        if not isinstance(verdict, dict):
            verdict = {}
        conn = sqlite3.connect(db_path, timeout=10)
        try:
            for r in chunk:
                node = norm_node(verdict.get(str(r["id"])) or verdict.get(r["id"]) or "")
                if not node:
                    skipped += 1
                    continue
                conn.execute("UPDATE memories SET node=? WHERE id=?", (node, r["id"]))
                filed += 1
                if node not in known:
                    new_nodes.add(node); known.add(node)
            conn.commit()
        finally:
            conn.close()
    refresh_all(db_path)
    return {"total": len(rows), "filed": filed, "skipped": skipped, "new_nodes": sorted(new_nodes)}
