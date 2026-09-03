"""forage_doc.py — 포식 기억의 정본은 문서다 (2026-09-03 사용자 판정: "단언은 그 폴더의 포식 기억 문서에 있어야").

위치(폴더·공간)마다 마크다운 문서 하나(`data/forage_surveys/<slug>.md`, 저장소 밖·개인정보).
문서의 `## 단언` 절이 단언의 정본이고, `forage_map`(DB)은 그 절의 **색인**이다 — 회상은 색인을 읽고,
쓰기는 어느 쪽으로 들어오든 둘을 같게 만든다:
  - DB 로 들어오는 쓰기(note/forget/정리 패스)   → 절을 다시 그린다(refresh_doc_for)
  - 문서로 들어오는 쓰기(판·편집기·AI)           → 절을 읽어 색인을 맞춘다(sync_doc_to_db; recall 이 mtime 으로 게을러도 잡는다)
문서 단위: 경로 locus 는 상위 세 단(예: ~/Desktop, /Volumes/X/Y)마다 하나, 경로 아닌 locus(웹·코드·책)는 몸(body)마다 하나.
절의 표기는 최소: `- [종류] 표식 한 줄 ‹메타›` — 판단은 AI·주인 것, 여기는 표기만.
"""
from __future__ import annotations

import json
import os
import re
from typing import Any, Dict, List, Optional, Tuple

import forage_memory as FM

DOC_DIR = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "data", "forage_surveys"))
SECTION = "## 단언"
MARKER_RE = re.compile(r"<!--\s*forage-doc\s+body=\"([^\"]*)\"\s+root=\"([^\"]*)\"\s*-->")
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


def _scan_docs() -> List[Tuple[str, str, str]]:
    """[(path, body, root)] — 표식이 있는 문서만."""
    out = []
    if not os.path.isdir(DOC_DIR):
        return out
    for name in sorted(os.listdir(DOC_DIR)):
        if not name.endswith(".md"):
            continue
        p = os.path.join(DOC_DIR, name)
        try:
            with open(p, encoding="utf-8") as f:
                head = f.read(2000)
        except OSError:
            continue
        m = MARKER_RE.search(head)
        if m:
            out.append((p, m.group(1), m.group(2)))
    return out


def doc_path_for(body: str, locus: str, *, create_default: bool = True) -> Optional[str]:
    """locus 를 덮는 가장 구체적인 기존 문서 → 없으면 기본 뿌리의 문서 경로(파일은 아직 없을 수 있음)."""
    best = None
    for p, b, root in _scan_docs():
        if b != body or not _covers(body, root, locus):
            continue
        if best is None or len(_norm(root)) > len(_norm(best[1])):
            best = (p, root)
    if best:
        return best[0]
    root = doc_root_for(body, locus)
    legacy = _legacy_doc_path(body, root)
    if legacy:
        return legacy
    if not create_default:
        return None
    return default_doc_path(body, root)


def _legacy_doc_path(body: str, root: str) -> Optional[str]:
    """표식 없이 AI·사람이 지은 문서 인수 — 경로 슬러그 이름(예: Volumes_Expansion_영화.md)이 있으면 그 문서(표식은 다음 렌더 때 붙는다)."""
    if not (_path_body(body) and _is_path(root)):
        return None
    cand = os.path.join(DOC_DIR, slug(root) + ".md")
    if os.path.exists(cand):
        try:
            head = open(cand, encoding="utf-8").read(2000)
        except OSError:
            return None
        m = MARKER_RE.search(head)
        if not m or (m.group(1) == body and _norm(m.group(2)) == _norm(root)):
            return cand
    return None


def existing_doc_for_root(body: str, root: str) -> Optional[str]:
    """정확히 이 (body, root) 의 문서 — 표식 일치 또는 옛 이름."""
    for p, b, r in _scan_docs():
        if b == body and _norm(r) == _norm(root):
            return p
    return _legacy_doc_path(body, root)


def default_doc_path(body: str, root: str) -> str:
    """기본 파일명: 맥은 경로 슬러그, 다른 디스크 몸은 `몸__경로`(같은 경로 뿌리가 몸마다 충돌하지 않게), 그 밖은 몸 이름.
    기존 문서는 이름이 아니라 머리의 표식(body·root)으로 찾는다 — AI 가 지은 이름(예: Volumes_Expansion_영화.md)도 그대로 산다."""
    if _path_body(body) and _is_path(root):
        return os.path.join(DOC_DIR, (slug(root) if body == "mac" else slug(body) + "__" + slug(root)) + ".md")
    return os.path.join(DOC_DIR, slug(body) + ".md")


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
    deeper = [_norm(rt) for _p, b, rt in _scan_docs() if b == body and _norm(rt) != r and _norm(rt).startswith(r + "/")]
    out = []
    for x in rows:
        loc = _norm(os.path.expanduser(x["locus"]))
        if not (loc == r or loc.startswith(r + "/")):
            continue
        if any(loc == d or loc.startswith(d + "/") for d in deeper):
            continue
        out.append(x)
    return out


def refresh_doc_for(body: str, locus: str) -> Optional[str]:
    """DB(색인)가 바뀐 뒤 그 위치를 덮는 문서의 `## 단언` 절을 다시 그린다. 문서가 없으면 최소 머리로 만든다."""
    path = doc_path_for(body, locus)
    if not path:
        return None
    root = None
    for p, b, r in _scan_docs():
        if p == path:
            root = r
    if root is None:
        root = doc_root_for(body, locus)
    return refresh_doc(path, body, root)


def refresh_doc(path: str, body: str, root: str) -> Optional[str]:
    rows = rows_for_doc(body, root)
    os.makedirs(DOC_DIR, exist_ok=True)
    if os.path.exists(path):
        text = open(path, encoding="utf-8").read()
        if not MARKER_RE.search(text[:2000]):
            text = f'<!-- forage-doc body="{body}" root="{root}" -->\n' + text
    else:
        title = root if _is_path(root) else body
        text = (f'<!-- forage-doc body="{body}" root="{root}" -->\n# 포식 기억 — {title}\n\n'
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


def lazy_sync(locus: str, body: Optional[str] = None) -> List[Dict[str, Any]]:
    """locus 를 덮는 문서가 색인보다 새로우면(사람·AI 가 문서를 고쳤으면) 색인을 맞춘다. 회상 앞에서 부른다 — stat 한 번."""
    out = []
    for p, b, root in _scan_docs():
        if body and b != body:
            continue
        if not body and _is_path(_norm(os.path.expanduser(locus or ""))) and not _path_body(b):
            continue  # 경로 질의에 웹·코드·책 문서는 무관(몸을 모르면 디스크 몸만)
        if not _covers(b, root, locus):
            continue
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
    done = []
    for p, b, root in _scan_docs():
        if body and b != body:
            continue
        if not body and _is_path(_norm(os.path.expanduser(locus or ""))) and not _path_body(b):
            continue
        if _covers(b, root, locus):
            done.append(sync_doc_to_db(p))
    if not done:
        return {"success": False, "error": f"이 위치를 덮는 포식 기억 문서가 없습니다: {locus}"}
    return {"success": True, "synced": done}


# ----------------------------------------------------------------- 이관
def migrate_all() -> Dict[str, Any]:
    """DB 의 모든 단언을 위치별 문서로 — 문서가 이미 있으면(AI 가 쓴 것) 표식과 `## 단언` 절만 더한다."""
    conn = FM._connect()
    try:
        rows = [dict(x) for x in conn.execute("SELECT body, locus FROM forage_map").fetchall()]
    finally:
        conn.close()
    groups: Dict[Tuple[str, str], int] = {}
    for r in rows:
        groups[(r["body"], doc_root_for(r["body"], r["locus"]))] = groups.get((r["body"], doc_root_for(r["body"], r["locus"])), 0) + 1
    written = []
    # 구체적(긴) 뿌리부터 만들어야 상위 문서의 절이 하위 문서가 덮는 행을 뺀다 — 끝에 전부 한 번 더 그린다
    for (body, root), n in sorted(groups.items(), key=lambda kv: (kv[0][0], -len(kv[0][1]))):
        p = refresh_doc(existing_doc_for_root(body, root) or default_doc_path(body, root), body, root)
        if p:
            written.append({"doc": os.path.basename(p), "body": body, "root": root, "rows": n})
    refresh_all_docs()
    return {"success": True, "docs": len(written), "written": written}
