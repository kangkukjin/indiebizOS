"""forage_doc.py — 포식 기억의 정본은 문서다 (2026-09-03 사용자 판정: "단언은 그 폴더의 포식 기억 문서에 있어야").

위치(폴더·공간)마다 마크다운 문서 하나(`data/forage_surveys/<slug>.md`, 저장소 밖·개인정보).
문서의 `## 단언` 절이 단언의 정본이고, `forage_map`(DB)은 그 절의 **색인**이다 — 회상은 색인을 읽고,
쓰기는 어느 쪽으로 들어오든 둘을 같게 만든다:
  - DB 로 들어오는 쓰기(note/forget/정리 패스)   → 절을 다시 그린다(refresh_doc_for)
  - 문서로 들어오는 쓰기(판·편집기·AI)           → 절을 읽어 색인을 맞춘다(sync_doc_to_db; recall 이 mtime 으로 게을러도 잡는다)
저장 구조 = **폴더 트리를 비춘 트리**(2026-09-03 사용자 판정 "그런 구조로"): `data/forage_surveys/<몸>/<경로 그대로>/memory.md`.
  mac/Users/u/Desktop/memory.md · mac/Users/u/Desktop/AI/memory.md(있으면 "AI 는 따로 조사됨") · disk_X/Volumes/X/영화/memory.md
  · code_repo/memory.md(경로 아닌 몸은 몸 폴더 하나) · mac/memory.md(경로 없는 locus 들).
  위계가 곧 저장 구조라 문서 찾기 = 경로를 그대로 옮기기, 조상 = 부모 디렉토리 올라가기, 하위 문서 = 아래 걷기(표식 스캔 없음).
  새 문서가 생기는 자리: 처음엔 상위 세 단(~/Desktop 급) · 영토 앵커(territory)를 찍은 폴더는 자기 노드에 문서를 갖는다(조사된 뿌리).
절의 표기는 최소: `- [종류] 표식 한 줄 ‹메타›` — 판단은 AI·주인 것, 여기는 표기만.
"""
from __future__ import annotations

import json
import os
import re
import time
from typing import Any, Dict, List, Optional, Tuple

import forage_memory as FM

DOC_DIR = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "data", "forage_surveys"))
SECTION = "## 단언"
MARKER_RE = re.compile(r"<!--\s*forage-doc\s+body=\"([^\"]*)\"\s+root=\"([^\"]*)\"(?:\s+dir_id=\"[^\"]*\")?\s*-->")
LINE_RE = re.compile(r"^- \[(identity|convention|dead_branch|substrate)\]\s*([⚑↓≈?]*)\s*(.*?)\s*(?:‹(.*?)›)?\s*$")
SECTION_NOTE = ("<!-- 기계가 읽는 절: 한 줄 = 단언 하나. `- [종류]` 뒤 표식 ⚑영토 ↓하위에도 적용 ≈의미적 ?의심 · "
                "끝의 ‹확신 · 시각 · 출처 · prune: 이유›는 메타. 줄을 고치면 색인이 따라온다(recall 이 문서 시각을 본다). -->")


# ----------------------------------------------------------------- 위치 → 문서
def _is_path(locus: str) -> bool:
    return bool(locus) and (locus.startswith("/") or locus.startswith("~"))


def _norm(locus: str) -> str:
    loc = (locus or "").rstrip("/")
    return loc[:-2] if loc.endswith("/*") else loc


def _path_body(body: str) -> bool:
    """디스크 몸(mac·disk:*·phone*)만 경로로 문서를 나눈다. 코드·웹·책은 locus 가 경로 모양이어도 몸마다 문서 하나."""
    return body == "mac" or body.startswith(("disk:", "phone", "windows", "linux"))


def doc_root_for(body: str, locus: str) -> str:
    """문서 단위의 뿌리. 디스크 몸의 경로 locus 는 상위 세 단(그보다 짧으면 그 경로), 그 밖은 몸 이름."""
    loc = _norm(os.path.expanduser(locus or ""))
    if not (_path_body(body) and _is_path(loc)):
        return body
    parts = [p for p in loc.split("/") if p]
    return "/" + "/".join(parts[:3]) if parts else "/"


def _covers(body: str, root: str, locus: str) -> bool:
    """문서(body, root)가 locus 를 덮나.
    ★디스크 몸의 '경로 아닌 뿌리'(예: root=mac — 경로 없는 locus 들의 문서)는 경로 locus 를 덮지 않는다.
      이 구분이 없던 2026-09-03 사고: 시험이 mac.md 를 덮어쓰자 동기화가 그 문서를 정본으로 믿고 맥 단언 100여 건을 지웠다."""
    r = _norm(root); loc = _norm(os.path.expanduser(locus or ""))
    if _path_body(body):
        if _is_path(r):
            return loc == r or loc.startswith(r + "/")
        return not _is_path(loc)
    return True  # 코드·웹·책: 몸 하나 = 문서 하나


def slug(s: str) -> str:
    s = s.strip().lstrip("/")
    s = re.sub(r"[\\/]+", "_", s)
    return re.sub(r'[<>:"|?*\x00-\x1f]', "_", s) or "root"


DOC_NAME = "memory.md"


def node_dir(body: str, root: str) -> str:
    """이 (몸, 뿌리)의 문서가 사는 디렉토리 — 트리를 비춘다."""
    base = os.path.join(DOC_DIR, slug(body))
    r = _norm(os.path.expanduser(root or ""))
    if _path_body(body) and _is_path(r):
        return os.path.join(base, *[p for p in r.split("/") if p])
    return base


def doc_path_at(body: str, root: str) -> str:
    return os.path.join(node_dir(body, root), DOC_NAME)


def _marker_line(body: str, root: str) -> str:
    return f'<!-- forage-doc body="{body}" root="{root}" -->'


def _read_marker(path: str) -> Optional[Tuple[str, str]]:
    try:
        with open(path, encoding="utf-8") as f:
            head = f.read(2000)
    except OSError:
        return None
    m = MARKER_RE.search(head)
    return (m.group(1), m.group(2)) if m else None


def _scan_docs() -> List[Tuple[str, str, str]]:
    """[(path, body, root)] — 트리 전체의 memory.md(표식이 몸·뿌리의 진실, 경로는 색인)."""
    out = []
    if not os.path.isdir(DOC_DIR):
        return out
    for cur, dirs, files in os.walk(DOC_DIR):
        dirs[:] = sorted(d for d in dirs if d != GONE_DIR)
        if DOC_NAME in files:
            p = os.path.join(cur, DOC_NAME)
            mk = _read_marker(p)
            if mk:
                out.append((p, mk[0], mk[1]))
    return out


def _ancestor_chain(body: str, locus: str) -> List[str]:
    """locus 자기 노드부터 위로 올라가며 존재하는 문서 경로들(가까운 것부터). 경로 아닌 몸은 몸 문서 하나."""
    loc = _norm(os.path.expanduser(locus or ""))
    found = []
    if _path_body(body) and _is_path(loc):
        parts = [p for p in loc.split("/") if p]
        for k in range(len(parts), 0, -1):
            cand = doc_path_at(body, "/" + "/".join(parts[:k]))
            if os.path.exists(cand):
                found.append(cand)
    else:
        cand = doc_path_at(body, body)
        if os.path.exists(cand):
            found.append(cand)
    return found


def docs_below(body: str, root: str) -> List[str]:
    """root 노드 아래(자기 제외)의 문서 경로들 — '하위 폴더가 더 자세한 기억을 가진다'가 디렉토리에서 바로 드러난다."""
    base = node_dir(body, root)
    out = []
    if not os.path.isdir(base):
        return out
    for cur, dirs, files in os.walk(base):
        dirs[:] = sorted(d for d in dirs if d != GONE_DIR)
        if cur != base and DOC_NAME in files:
            out.append(os.path.join(cur, DOC_NAME))
    return out


def root_of_doc(path: str) -> str:
    """문서 경로 → 뿌리(표식 우선, 없으면 경로에서)."""
    mk = _read_marker(path)
    if mk:
        return mk[1]
    rel = os.path.relpath(os.path.dirname(path), DOC_DIR).split(os.sep)
    return "/" + "/".join(rel[1:]) if len(rel) > 1 else rel[0]


def doc_path_for(body: str, locus: str, *, create_default: bool = True) -> Optional[str]:
    """locus 를 덮는 가장 가까운 기존 문서(자기 노드 → 조상) → 없으면 기본 뿌리(상위 세 단)의 문서 경로(아직 없을 수 있음)."""
    chain = _ancestor_chain(body, locus)
    if chain:
        return chain[0]
    if not create_default:
        return None
    return doc_path_at(body, doc_root_for(body, locus))


def existing_doc_for_root(body: str, root: str) -> Optional[str]:
    p = doc_path_at(body, root)
    return p if os.path.exists(p) else None


def default_doc_path(body: str, root: str) -> str:
    return doc_path_at(body, root)


# ----------------------------------------------------------------- 렌더 / 파싱
def _meta_text(r: Dict[str, Any]) -> str:
    parts = [f"{float(r.get('confidence') or 0):.2f}", str(r.get("last_seen") or "")[:10]]
    src = ""
    try:
        prov = json.loads(r.get("provenance") or "{}")
        srcs = prov.get("sources") or prov.get("observed") or []
        if isinstance(srcs, list) and srcs:
            src = str(srcs[0])[:40]
        elif prov.get("query"):
            src = "query:" + str(prov["query"])[:30]
    except (ValueError, TypeError):
        pass
    if src:
        parts.append(src)
    if r.get("prune_reason"):
        parts.append("prune: " + str(r["prune_reason"])[:60])
    return " · ".join(p for p in parts if p)


def _claim_key(claim: str) -> str:
    """비교용 문장 정규화 — 렌더가 줄바꿈·‹›를 바꾸므로 양쪽을 같은 모양으로."""
    return re.sub(r"\s+", " ", str(claim or "")).replace("‹", "<").replace("›", ">").strip()


def render_line(r: Dict[str, Any]) -> str:
    flags = ("⚑" if r.get("territory") else "") + ("↓" if r.get("generalizes") else "") \
        + ("≈" if r.get("prior_class") == "semantic" else "") + ("?" if r.get("surface_flag") else "")
    claim = str(r.get("claim") or "").replace("\n", " ").replace("‹", "<").replace("›", ">")
    return f"- [{r['kind']}] {flags + ' ' if flags else ''}{claim} ‹{_meta_text(r)}›"


def render_section(rows: List[Dict[str, Any]]) -> str:
    by: Dict[str, List[Dict[str, Any]]] = {}
    for r in rows:
        by.setdefault(_norm(r["locus"]), []).append(r)
    lines = [SECTION, SECTION_NOTE, ""]
    for loc in sorted(by, key=lambda x: (x.count("/"), x)):
        lines.append(f"### {loc}")
        for r in sorted(by[loc], key=lambda x: (0 if x.get("territory") else 1, x["kind"], x["claim"])):
            lines.append(render_line(r))
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def parse_section(text: str) -> List[Dict[str, Any]]:
    """`## 단언` 절 → [{locus, kind, claim, territory, generalizes, prior_class, surface_flag, confidence, prune_reason}]"""
    if SECTION not in text:
        return []
    body = text.split(SECTION, 1)[1]
    m = re.search(r"^## ", body, re.M)
    body = body[:m.start()] if m else body
    out, locus = [], None
    for raw in body.splitlines():
        line = raw.rstrip()
        if line.startswith("### "):
            locus = line[4:].strip()
            continue
        mm = LINE_RE.match(line)
        if not mm or not locus:
            continue
        kind, flags, claim, meta = mm.group(1), mm.group(2) or "", mm.group(3).strip(), mm.group(4) or ""
        if not claim:
            continue
        conf, prune = None, None
        for part in [p.strip() for p in meta.split("·")]:
            if re.fullmatch(r"[01](?:\.\d+)?", part):
                conf = float(part)
            elif part.startswith("prune:"):
                prune = part[6:].strip()
        out.append({"locus": locus, "kind": kind, "claim": claim,
                    "territory": "⚑" in flags, "generalizes": "↓" in flags,
                    "prior_class": "semantic" if "≈" in flags else "structural",
                    "surface_flag": "?" in flags, "confidence": conf, "prune_reason": prune})
    return out


def _replace_section(text: str, section: str) -> str:
    if SECTION in text:
        i = text.index(SECTION)
        rest = text[i + len(SECTION):]
        m = re.search(r"^## ", rest, re.M)
        tail = rest[m.start():] if m else ""
        return text[:i] + section + ("\n" + tail if tail else "")
    # 갱신 기록 앞에 끼워 넣는다(있으면), 없으면 끝에
    if "## 갱신 기록" in text:
        i = text.index("## 갱신 기록")
        return text[:i] + section + "\n" + text[i:]
    return text.rstrip() + "\n\n" + section


def _stamp_key(path: str) -> str:
    return "docsync:" + path


def _stamp(path: str) -> None:
    try:
        FM.set_meta(_stamp_key(path), str(os.path.getmtime(path)))
    except OSError:
        pass


# ----------------------------------------------------------------- DB → 문서
def rows_for_doc(body: str, root: str) -> List[Dict[str, Any]]:
    """이 문서가 담을 행 — 같은 몸에서 더 구체적인 다른 문서가 덮는 행은 뺀다(상위 문서는 골격, 상세는 하위 문서)."""
    r = _norm(root)
    conn = FM._connect()
    try:
        rows = [dict(x) for x in conn.execute("SELECT * FROM forage_map WHERE body=?", (body,)).fetchall()]
    finally:
        conn.close()
    if not _path_body(body):
        return rows
    if not _is_path(r):
        return [x for x in rows if not _is_path(_norm(os.path.expanduser(x["locus"])))]   # 경로 없는 locus 들만
    deeper = [_norm(root_of_doc(p)) for p in docs_below(body, r)]
    out = []
    for x in rows:
        loc = _norm(os.path.expanduser(x["locus"]))
        if not (loc == r or loc.startswith(r + "/")):
            continue
        if any(loc == d or loc.startswith(d + "/") for d in deeper):
            continue
        out.append(x)
    return out


def refresh_doc_for(body: str, locus: str, *, own_node: bool = False) -> Optional[str]:
    """DB(색인)가 바뀐 뒤 그 위치를 덮는 문서의 `## 단언` 절을 다시 그린다. 문서가 없으면 최소 머리로 만든다.
    own_node=True(영토 앵커): 이 locus 자기 노드에 문서를 만들고, 그 행들을 잃는 조상 문서도 다시 그린다."""
    loc = _norm(os.path.expanduser(locus or ""))
    if own_node and _path_body(body) and _is_path(loc):
        path = doc_path_at(body, loc)
        chain_before = _ancestor_chain(body, loc)
        out = refresh_doc(path, body, loc)
        for anc in chain_before:
            if anc != path:
                refresh_doc(anc, body, root_of_doc(anc))
                break
        return out
    path = doc_path_for(body, locus)
    if not path:
        return None
    root = root_of_doc(path) if os.path.exists(path) else doc_root_for(body, locus)
    return refresh_doc(path, body, root)


def refresh_doc(path: str, body: str, root: str) -> Optional[str]:
    rows = rows_for_doc(body, root)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    if os.path.exists(path):
        text = open(path, encoding="utf-8").read()
        if not MARKER_RE.search(text[:2000]):
            text = _marker_line(body, root) + "\n" + text
    else:
        title = root if _is_path(root) else body
        text = (_marker_line(body, root) + f'\n# 포식 기억 — {title}\n\n'
                f"| 머리 | |\n|---|---|\n| 조사 일시 | (아직 조사 안 함 — 단언은 대화·포식에서 쌓인 것) |\n"
                f"| 예산 (어디까지 봤나) | — |\n| 거칠기 | — |\n| 상위 문서 | — |\n| 하위 문서 | — |\n\n"
                f"## 갱신 기록\n")
    text = _replace_section(text, render_section(rows))
    with open(path, "w", encoding="utf-8") as f:
        f.write(text)
    _stamp(path)
    return path


def refresh_all_docs() -> List[str]:
    """정리 패스 뒤 등 — 표식 있는 문서 전부 다시 그린다."""
    out = []
    for p, b, r in _scan_docs():
        try:
            if refresh_doc_for(b, r):
                out.append(p)
        except Exception:
            continue
    return out


# ----------------------------------------------------------------- 문서 → DB
def sync_doc_to_db(path: str) -> Dict[str, Any]:
    """문서의 `## 단언` 절을 색인에 맞춘다: 같은 (locus, kind, claim) 은 유지(출처 보존), 새 줄은 삽입, 절에 없는 행은 삭제."""
    if not os.path.exists(path):
        return {"success": False, "error": f"문서 없음: {path}"}
    text = open(path, encoding="utf-8").read()
    m = MARKER_RE.search(text[:2000])
    if not m:
        return {"success": False, "error": "forage-doc 표식이 없는 문서"}
    body, root = m.group(1), m.group(2)
    parsed = parse_section(text)
    # 더 구체적인 하위 문서가 덮는 위치의 줄은 이 문서 소관이 아니다(옛 렌더의 잔재) — 건너뛰고, 다음 재렌더가 절에서 걷어낸다
    deeper = [_norm(root_of_doc(d)) for d in docs_below(body, root)] if (_path_body(body) and _is_path(_norm(root))) else []
    if deeper:
        parsed = [q for q in parsed
                  if not any(_norm(os.path.expanduser(q["locus"])) == d or _norm(os.path.expanduser(q["locus"])).startswith(d + "/") for d in deeper)]
    existing = rows_for_doc(body, root)
    ex_by = {(_norm(os.path.expanduser(r["locus"])), r["kind"], _claim_key(r["claim"])): r for r in existing}
    seen = {(_norm(os.path.expanduser(p["locus"])), p["kind"], _claim_key(p["claim"])) for p in parsed}
    inserted, updated = 0, 0
    conn = FM._connect()
    try:
        now = FM._now()
        # 삭제를 먼저 — 같은 (locus, kind) 의 옛 줄이 남아 있으면 새 줄 삽입이 유일 키에 걸린다
        deleted = 0
        for key, r in ex_by.items():
            if key not in seen:
                conn.execute("DELETE FROM forage_map WHERE id=?", (r["id"],))
                deleted += 1
        for p in parsed:
            key = (_norm(os.path.expanduser(p["locus"])), p["kind"], _claim_key(p["claim"]))
            r = ex_by.get(key)
            if r:
                conn.execute("UPDATE forage_map SET territory=?, generalizes=?, prior_class=?, surface_flag=?, "
                             "confidence=COALESCE(?, confidence), prune_reason=? WHERE id=?",
                             (1 if p["territory"] else 0, 1 if p["generalizes"] else 0, p["prior_class"],
                              1 if p["surface_flag"] else 0, p["confidence"], p["prune_reason"], r["id"]))
                updated += 1
            else:
                conn.execute("INSERT INTO forage_map (body, locus, kind, claim, prior_class, confidence, provenance, "
                             "prune_reason, generalizes, last_seen, locus_mtime, surface_flag, territory) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
                             (body, key[0], p["kind"], FM.mask_secrets(p["claim"]), p["prior_class"], p["confidence"] or 0.9,
                              json.dumps({"sources": ["doc"], "formed_at": now, "observed": [f"문서 편집: {os.path.basename(path)}"]}, ensure_ascii=False),
                              p["prune_reason"], 1 if p["generalizes"] else 0, now, FM._locus_mtime(key[0]),
                              1 if p["surface_flag"] else 0, 1 if p["territory"] else 0))
                inserted += 1
        conn.commit()
    finally:
        conn.close()
    _stamp(path)
    return {"success": True, "path": path, "body": body, "root": root,
            "inserted": inserted, "updated": updated, "deleted": deleted, "lines": len(parsed)}


def _covering_docs(locus: str, body: Optional[str]) -> List[str]:
    """locus 를 덮는 문서들(자기 노드+조상). 몸을 모르면: 경로 locus 는 디스크 몸들의 사슬, 아니면 모든 몸 문서."""
    loc = _norm(os.path.expanduser(locus or ""))
    bodies = [body] if body else sorted({b for _p, b, _r in _scan_docs()})
    out: List[str] = []
    for b in bodies:
        if not body and _is_path(loc) and not _path_body(b):
            continue
        out.extend(_ancestor_chain(b, loc))
    return out


def lazy_sync(locus: str, body: Optional[str] = None) -> List[Dict[str, Any]]:
    """locus 를 덮는 문서가 색인보다 새로우면(사람·AI 가 문서를 고쳤으면) 색인을 맞춘다. 회상 앞에서 부른다 — stat 한 번."""
    out = []
    for p in _covering_docs(locus, body):
        try:
            mtime = os.path.getmtime(p)
        except OSError:
            continue
        stamp = FM.get_meta(_stamp_key(p))
        if stamp is None or float(stamp) + 1e-6 < mtime:   # 우리 쓰기는 정확히 그 mtime 으로 도장 찍는다 — 그 뒤의 편집만 잡는다
            out.append(sync_doc_to_db(p))
    return out


def sync_for_locus(locus: str, body: Optional[str] = None) -> Dict[str, Any]:
    """어휘 `[self:forage]{op:"sync", locus}` — 그 위치를 덮는 문서(들)를 색인에 맞춘다(시각 무관, 강제)."""
    done = [sync_doc_to_db(p) for p in _covering_docs(locus, body)]
    if not done:
        return {"success": False, "error": f"이 위치를 덮는 포식 기억 문서가 없습니다: {locus}"}
    return {"success": True, "synced": done}


# ----------------------------------------------------------------- 이관
def _prose_len(text: str) -> int:
    """`## 단언` 절과 표식을 뺀 본문 길이 — '누가 더 많이 썼나'의 잣대."""
    t = MARKER_RE.sub("", text)
    if SECTION in t:
        i = t.index(SECTION); rest = t[i + len(SECTION):]
        m = re.search(r"^## ", rest, re.M)
        t = t[:i] + (rest[m.start():] if m else "")
    return len(t.strip())


def migrate_layout() -> Dict[str, Any]:
    """옛 평평한 문서(`<slug>.md`, 표식 있음)를 트리 자리(`<몸>/<경로>/memory.md`)로 옮긴다. 멱등."""
    moved = []
    if not os.path.isdir(DOC_DIR):
        return {"success": True, "moved": moved}
    for name in sorted(os.listdir(DOC_DIR)):
        p = os.path.join(DOC_DIR, name)
        if not (name.endswith(".md") and os.path.isfile(p)):
            continue
        mk = _read_marker(p)
        if not mk:
            continue
        dst = doc_path_at(mk[0], mk[1])
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        if os.path.exists(dst):
            # 트리 자리에 이미 문서가 있어도 옛 평평한 문서가 이긴다 — 그건 사람·AI 가 쓴 것이고, 트리 것은 그 사이 기계가 만든 껍데기다
            os.replace(dst, dst + ".tree.bak")
        os.replace(p, dst)
        try:
            refresh_doc(dst, mk[0], mk[1])   # 절은 색인에서 다시 그린다
        except Exception:
            pass
        moved.append({"from": name, "to": os.path.relpath(dst, DOC_DIR)})
    if moved:
        refresh_all_docs()   # 전부 옮긴 뒤에 그려야 상위 절이 하위 문서 소관의 행을 뺀다
    return {"success": True, "moved": moved}


def migrate_all() -> Dict[str, Any]:
    """DB 의 모든 단언을 위치별 문서로 — 문서가 이미 있으면(AI 가 쓴 것) 표식과 `## 단언` 절만 더한다.
    영토 앵커(territory=1)가 있는 경로 locus 는 자기 노드에 문서를 갖는다(조사된 뿌리)."""
    conn = FM._connect()
    try:
        rows = [dict(x) for x in conn.execute("SELECT body, locus FROM forage_map").fetchall()]
    finally:
        conn.close()
    migrate_layout()
    groups: Dict[Tuple[str, str], int] = {}
    conn = FM._connect()
    try:
        terr = [dict(x) for x in conn.execute("SELECT body, locus FROM forage_map WHERE territory=1").fetchall()]
    finally:
        conn.close()
    for t in terr:  # 영토 앵커 = 자기 노드 문서
        loc = _norm(os.path.expanduser(t["locus"]))
        if _path_body(t["body"]) and _is_path(loc):
            groups[(t["body"], loc)] = groups.get((t["body"], loc), 0)
    for r in rows:
        key = (r["body"], doc_root_for(r["body"], r["locus"]))
        groups[key] = groups.get(key, 0) + 1
    written = []
    # 구체적(긴) 뿌리부터 만들어야 상위 문서의 절이 하위 문서가 덮는 행을 뺀다 — 끝에 전부 한 번 더 그린다
    for (body, root), n in sorted(groups.items(), key=lambda kv: (kv[0][0], -len(kv[0][1]))):
        p = refresh_doc(existing_doc_for_root(body, root) or default_doc_path(body, root), body, root)
        if p:
            written.append({"doc": os.path.basename(p), "body": body, "root": root, "rows": n})
    refresh_all_docs()
    return {"success": True, "docs": len(written), "written": written}


# ----------------------------------------------------------------- 대조(reconcile) — 실제 트리 ↔ 기억 트리
# 2026-09-03 사용자 판정: "폴더가 위치를 바꾸면 그냥 포식 기억을 포기하자 — 다시 얻는 게 이사를 찾는 것만큼 힘들지 않다. _gone 은 일주일마다 지워."
# 그래서 관측은 존재 여부 하나뿐: 폴더가 없어졌으면 그 노드(와 그 밑)의 문서를 `_gone/` 으로 접고 부모 문서에 한 줄, 단언은 '폴더 사라짐' 표식.
# 내용물만 바뀐 흔한 경우는 낡음 표식만 — 아무것도 지우지 않는다. 옮긴 폴더는 새 자리에서 다시 조사한다.
GONE_DIR = "_gone"
_RECONCILE_MIN_INTERVAL = 3600
GONE_PURGE_DAYS = 7


def _mounted(path: str) -> bool:
    """볼륨이 안 꽂힌 것은 '사라짐'이 아니다."""
    m = re.match(r"^(/Volumes/[^/]+)", path)
    return os.path.isdir(m.group(1)) if m else True


def _append_record(doc_path: str, line: str) -> None:
    """문서 `## 갱신 기록` 에 한 줄(없으면 절을 만든다)."""
    if not os.path.exists(doc_path):
        return
    text = open(doc_path, encoding="utf-8").read()
    if "## 갱신 기록" not in text:
        text = text.rstrip() + "\n\n## 갱신 기록\n"
    text = text.rstrip("\n") + "\n" + line + "\n"
    open(doc_path, "w", encoding="utf-8").write(text)
    _stamp(doc_path)


def _parent_doc(body: str, root: str) -> Optional[str]:
    r = _norm(root)
    parent = os.path.dirname(r)
    return (_ancestor_chain(body, parent) or [None])[0] if parent and parent != r else None


def tombstone_node(body: str, root: str) -> Dict[str, Any]:
    """사라진 폴더: 노드 문서(와 그 밑 전부)를 `_gone/` 으로 접고 부모 문서에 한 줄. 단언은 지우지 않고 '폴더 사라짐' 표식."""
    r = _norm(root)
    today = FM._now()[:10]
    conn = FM._connect()
    try:
        conn.execute("UPDATE forage_map SET surface_flag=1, prune_reason=COALESCE(prune_reason, ?) WHERE body=? AND (locus=? OR locus LIKE ?)",
                     (f"폴더 사라짐 {today}", body, r, r + "/%"))
        conn.commit()
    finally:
        conn.close()
    src = node_dir(body, r)
    gone = os.path.join(DOC_DIR, slug(body), GONE_DIR, *[p for p in r.split("/") if p])
    if os.path.isdir(src):
        if os.path.exists(gone):
            os.renames(src, gone + f".{today}.bak")
        else:
            os.renames(src, gone)
    parent = _parent_doc(body, r)
    if parent:
        _append_record(parent, f"- {today} `{os.path.basename(r)}` 사라짐 — 기억은 `{os.path.relpath(gone, DOC_DIR)}` 에 접어 둠(일주일 뒤 삭제). 옮긴 것이면 새 자리에서 다시 조사")
        refresh_doc(parent, body, root_of_doc(parent))
    return {"success": True, "root": r, "action": "gone", "archived": os.path.relpath(gone, DOC_DIR)}


def reconcile(body: Optional[str] = None, locus: Optional[str] = None, *, apply: bool = True) -> Dict[str, Any]:
    """실제 트리 ↔ 기억 트리 대조. 문서 노드(디스크 몸·경로 뿌리)마다 존재를 보고, 없으면 `_gone/` 으로 접는다."""
    loc = _norm(os.path.expanduser(locus)) if locus else None
    nodes = [(p, b, _norm(r)) for p, b, r in _scan_docs() if _path_body(b) and _is_path(_norm(r))]
    if body:
        nodes = [x for x in nodes if x[1] == body]
    if loc:
        nodes = [x for x in nodes if x[2] == loc or x[2].startswith(loc + "/") or loc.startswith(x[2] + "/")]
    nodes.sort(key=lambda x: x[2].count("/"))   # 얕은 것부터 — 조상이 사라졌으면 그 밑은 통째로 접힌다
    report = {"checked": 0, "unmounted": [], "missing": [], "gone": []}
    handled: List[str] = []
    for p, b, r in nodes:
        if any(r == h or r.startswith(h + "/") for h in handled):
            continue
        if not _mounted(r):
            report["unmounted"].append(r); continue
        report["checked"] += 1
        if os.path.isdir(os.path.expanduser(r)):
            continue
        report["missing"].append(r)
        if apply:
            report["gone"].append(tombstone_node(b, r)); handled.append(r)
    return {"success": True, **report}


def reconcile_lazy(locus: str, body: Optional[str] = None) -> Optional[Dict[str, Any]]:
    """회상 앞에서 — 이 위치를 덮는 문서 뿌리가 실제로 없을 때만(그리고 한 시간에 한 번만) 그 가지를 대조한다. 비용=stat 하나."""
    for p in _covering_docs(locus, body):
        mk = _read_marker(p)
        if not mk or not (_path_body(mk[0]) and _is_path(_norm(mk[1]))):
            continue
        r = _norm(mk[1])
        if os.path.isdir(os.path.expanduser(r)) or not _mounted(r):
            continue
        key = "reconcile:" + p
        last = FM.get_meta(key)
        now = time.time()
        if last and now - float(last) < _RECONCILE_MIN_INTERVAL:
            continue
        FM.set_meta(key, str(now))
        return reconcile(mk[0], r)
    return None


def purge_gone(days: int = GONE_PURGE_DAYS) -> Dict[str, Any]:
    """`_gone/` 아래 접힌 기억 중 days 일 지난 것을 지운다 — 주간 정리 패스가 부른다(사용자 판정: 일주일마다)."""
    import shutil
    cutoff = time.time() - days * 86400
    removed = []
    if not os.path.isdir(DOC_DIR):
        return {"success": True, "removed": removed}
    for body_dir in os.listdir(DOC_DIR):
        gone = os.path.join(DOC_DIR, body_dir, GONE_DIR)
        if not os.path.isdir(gone):
            continue
        targets = []
        for cur, _dirs, files in os.walk(gone):
            if DOC_NAME in files:
                try:
                    if os.path.getmtime(os.path.join(cur, DOC_NAME)) < cutoff:
                        targets.append(cur)
                except OSError:
                    pass
        for cur in sorted(targets, key=len):   # 얕은 것부터 — 밑은 함께 지워진다
            if os.path.isdir(cur):
                shutil.rmtree(cur, ignore_errors=True); removed.append(os.path.relpath(cur, DOC_DIR))
        for cur, _dirs, _files in os.walk(gone, topdown=False):   # 빈 껍데기 정리
            if cur != gone and os.path.isdir(cur) and not os.listdir(cur):
                os.rmdir(cur)
    return {"success": True, "removed": removed}
