"""방법의 지도: 불변 정본 스냅샷과 명시적으로 빌드하는 로컬 FTS 색인.

세계의 명사는 YAML만 소유한다. 질문 경로에서는 모델 적재·색인 재생성을 하지 않는다.
색인이 없거나 낡으면 같은 스냅샷의 작은 어휘 검색으로 내려간다.
"""
import hashlib
import json
import os
import re
import sqlite3
import tempfile
import unicodedata
from contextlib import closing
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from knowledge_graph import GRAPH_VERSION, KINDS, Graph, local_path, parse_graph

SEARCH_VERSION = "lexical-5-browse-" + GRAPH_VERSION
CATALOG_PATH = "data/knowledge_catalog/world.yaml"
INDEX_PATH = "data/knowledge_catalog_index/world.sqlite3"
# 분야 어휘가 아닌 문법 조사. 앞 음절을 자르지 않고 질의의 어미만 허용한다.
_PARTICLES = re.compile(r"^(?:은|는|이|가|을|를|의|에|에서|에게|로|으로|와|과|도|만|랑|이라도|처럼|보다|부터|까지|하고|이나|나|에는|으로는|에서는|들을|들이|들은|들)?$")
_WORDS = re.compile(r"[^\W_]+", re.UNICODE)


def normalize(text):
    return unicodedata.normalize("NFKC", text).casefold()


def terms(text):
    return tuple(t for t in _WORDS.findall(normalize(text)) if len(t) > 1)


@lru_cache(maxsize=4096)
def _phrase_pattern(phrase):
    parts = []
    for word in phrase.split():
        # 한글 음절 사이의 띄어쓰기만 허용: 근무표 ↔ 근무 표.
        chars = []
        for i, char in enumerate(word):
            chars.append(re.escape(char))
            if i + 1 < len(word) and re.fullmatch(r"[가-힣]{2}", word[i:i + 2]):
                chars.append(r"\s*")
        parts.append("".join(chars))
    return re.compile(r"\s*".join(parts))


def mentions(phrase, query):
    """영어 단어 내부 오탐을 막고 한글의 띄어쓰기·조사 차이만 허용한다."""
    phrase = normalize(phrase).strip()
    if not phrase:
        return False
    return _mentions_normalized(phrase, normalize(query))


def _mentions_normalized(phrase, query):
    for match in _phrase_pattern(phrase).finditer(query):
        before = query[:match.start()]
        after = query[match.end():]
        if before and before[-1].isalnum():
            continue
        tail = re.match(r"[^\W_]+", after)
        if tail and not _PARTICLES.fullmatch(tail[0]):
            continue
        return True
    return False


@dataclass(frozen=True)
class Entry:
    id: str
    path: tuple
    name: str
    hint: str
    aliases: tuple
    source: str
    kind: str = "term"
    scope_note: str = ""
    source_section: str = ""


@dataclass(frozen=True)
class Snapshot:
    revision: str
    entries: tuple
    graph: Graph = Graph()
    files: tuple = ()


def _text(value, limit):
    if not isinstance(value, str) or not value.strip() or len(value) > limit or "\n" in value:
        raise ValueError("catalog text must be a nonempty bounded single line")
    return value.strip()


@lru_cache(maxsize=8)
def _parse(root, raw, fragments=(), evidence_hashes=()):
    import yaml
    doc = yaml.safe_load(raw)
    if not isinstance(doc, dict) or doc.get("version") not in {1, 2} or not isinstance(doc.get("entries"), list):
        raise ValueError("unsupported catalog schema")
    documents = [doc] + [yaml.safe_load(content) for _, content in fragments]
    if any(not isinstance(d, dict) or not isinstance(d.get("entries", []), list) for d in documents):
        raise ValueError("invalid catalog fragment")
    entries, seen = [], set()
    for row in [row for d in documents for row in d.get("entries", [])]:
        eid = _text(row["id"], 80)
        if eid in seen or not re.fullmatch(r"[a-z0-9_.-]+", eid):
            raise ValueError("invalid or duplicate catalog id")
        seen.add(eid)
        path, aliases = row["path"], row.get("aliases", [])
        if not isinstance(path, list) or not 1 <= len(path) <= 5 or not isinstance(aliases, list):
            raise ValueError("invalid catalog path or aliases")
        source = _text(row["source"]["path"], 300)
        resolved = (Path(root) / source).resolve()
        if Path(source).is_absolute() or not resolved.is_relative_to(Path(root)) or not resolved.is_file():
            raise ValueError("catalog source must exist within repository")
        kind = row.get("kind", "term")
        if kind not in KINDS:
            raise ValueError("invalid catalog kind")
        scope = _text(row["scope_note"], 300) if row.get("scope_note") else ""
        section = _text(row["source"]["section"], 120) if row["source"].get("section") else ""
        entries.append(Entry(eid, tuple(_text(p, 40) for p in path),
                             _text(row["name"], 60), _text(row["hint"], 100),
                             tuple(_text(a, 60) for a in aliases), source, kind, scope, section))
    graph = parse_graph(root, documents, entries)
    digest = hashlib.sha256(SEARCH_VERSION.encode() + raw)
    for name, content in fragments:
        digest.update(name.encode() + b"\0" + content)
    digest.update(json.dumps(evidence_hashes).encode())
    return Snapshot(digest.hexdigest(), tuple(entries), graph, tuple(name for name, _ in fragments))


def load_snapshot(root):
    import yaml
    root = Path(root).resolve()
    raw = (root / CATALOG_PATH).read_bytes()
    doc = yaml.safe_load(raw)
    if not isinstance(doc, dict):
        raise ValueError("invalid catalog")
    files = doc.get("fragments", [])
    if not isinstance(files, list) or len(files) != len(set(files)):
        raise ValueError("invalid catalog fragments")
    if files and doc.get("version") != 2:
        raise ValueError("fragments require version 2")
    fragments = tuple((local_path(root, f), (root / f).read_bytes()) for f in files)
    documents = [doc] + [yaml.safe_load(content) for _, content in fragments]
    sources = {local_path(root, e["path"]) for d in documents for e in d.get("evidence", [])}
    hashes = tuple((p, hashlib.sha256((root / p).read_bytes()).hexdigest()) for p in sorted(sources))
    return _parse(str(root), raw, fragments, hashes)


def source_hashes(root, snapshot):
    return {s: hashlib.sha256((Path(root) / s).read_bytes()).hexdigest()
            for s in sorted({e.source for e in snapshot.entries} | {e.path for e in snapshot.graph.evidence})}


def build_index(root):
    root = Path(root)
    snapshot = load_snapshot(root)
    if any(not e.current for e in snapshot.graph.evidence):
        raise ValueError("catalog evidence changed; review before rebuilding")
    destination = root / INDEX_PATH
    destination.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=".catalog-", dir=destination.parent)
    os.close(fd)
    try:
        with closing(sqlite3.connect(temporary, timeout=10)) as db, db:
            db.execute("CREATE TABLE metadata (key TEXT PRIMARY KEY, value TEXT NOT NULL)")
            db.executemany("INSERT INTO metadata VALUES (?, ?)", [
                ("revision", snapshot.revision), ("search_version", SEARCH_VERSION),
                ("sources", json.dumps(source_hashes(root, snapshot), sort_keys=True)),
            ])
            db.execute("CREATE VIRTUAL TABLE catalog USING fts5(id UNINDEXED, name, aliases, hint, path)")
            db.executemany("INSERT INTO catalog VALUES (?, ?, ?, ?, ?)",
                           [(e.id, e.name, " ".join(e.aliases), e.hint, " ".join(e.path))
                            for e in snapshot.entries])
            db.execute("CREATE TABLE edges (id TEXT PRIMARY KEY, subject TEXT, predicate TEXT, object TEXT, record TEXT)")
            db.execute("CREATE INDEX edge_subject ON edges(subject)")
            db.execute("CREATE INDEX edge_object ON edges(object)")
            db.executemany("INSERT INTO edges VALUES (?, ?, ?, ?, ?)", _edge_rows(snapshot))
        os.replace(temporary, destination)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)
    return snapshot


def _connect(root):
    return sqlite3.connect((Path(root) / INDEX_PATH).resolve().as_uri() + "?mode=ro", uri=True, timeout=0.02)


def check_index(root):
    snapshot = load_snapshot(root)
    with closing(_connect(root)) as db:
        metadata = dict(db.execute("SELECT key, value FROM metadata"))
        if metadata.get("revision") != snapshot.revision:
            raise ValueError("catalog index stale; rebuild")
        if json.loads(metadata["sources"]) != source_hashes(root, snapshot):
            raise ValueError("catalog source changed; review entries and rebuild")
        rows = db.execute("SELECT id, name, aliases, hint, path FROM catalog ORDER BY id").fetchall()
        expected = sorted((e.id, e.name, " ".join(e.aliases), e.hint, " ".join(e.path)) for e in snapshot.entries)
        if rows != expected:
            raise ValueError("catalog index content differs from snapshot")
        if db.execute("SELECT * FROM edges ORDER BY id").fetchall() != sorted(_edge_rows(snapshot)):
            raise ValueError("catalog edge index differs from snapshot")
        if db.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
            raise ValueError("catalog index integrity check failed")
    return snapshot


def _edge_rows(snapshot):
    from dataclasses import asdict
    return [(e.id, e.subject, e.predicate, e.object, json.dumps(asdict(e), sort_keys=True))
            for e in snapshot.graph.edges]


def search(root, snapshot, query):
    """(후보, 모드). FTS 순위는 동점 처리만 맡고 실제 어휘 근거가 문턱을 소유한다."""
    # 첨부 전문이 긴 질문에도 검색 시간이 커지지 않도록 앞·뒤에서 단서만 읽는다.
    query = normalize(query if len(query) <= 8000 else query[:4000] + "\n" + query[-4000:])
    ranks, mode = {}, "lexical_fallback"
    try:
        with closing(_connect(root)) as db:
            revision = db.execute("SELECT value FROM metadata WHERE key='revision'").fetchone()
            if revision and revision[0] == snapshot.revision:
                # FTS 문법은 사용자 입력과 분리한다. 긴 요청도 최대 64 검색어.
                words = tuple(dict.fromkeys(terms(query)))[:64]
                if words:
                    expression = " OR ".join('"' + w + '"*' for w in words)
                    rows = db.execute("SELECT id FROM catalog WHERE catalog MATCH ? ORDER BY bm25(catalog)",
                                      (expression,)).fetchall()
                    ranks = {r[0]: i for i, r in enumerate(rows)}
                mode = "lexical_fts"
    except (sqlite3.Error, OSError):
        pass
    scored = []
    for entry in snapshot.entries:
        name = _mentions_normalized(normalize(entry.name), query)
        aliases = sum(_mentions_normalized(normalize(a), query) for a in entry.aliases)
        hits = sum(_mentions_normalized(t, query) for t in set(terms(entry.hint + " " + entry.scope_note)))
        path_hits = sum(_mentions_normalized(t, query) for t in set(terms(" ".join(entry.path))))
        # 일반 단어 하나(자료·변환·처리 등)만으로 연관 있다고 가장하지 않는다.
        if not name and not aliases and hits < 2:
            continue
        score = 20 * name + 6 * min(aliases, 3) + min(hits, 6) + min(path_hits, 2) * 0.25
        scored.append((entry, score))
    scored.sort(key=lambda pair: (-pair[1], ranks.get(pair[0].id, 9999), pair[0].id))
    # 이름·별칭처럼 강한 단서가 있으면 일반 설명 단어만 맞는 후보로 채우지 않는다.
    # 분류명은 순위에만 보태며 설명의 같은 단어를 이중 계산해 문턱을 넘기지 않는다.
    if scored and scored[0][1] >= 6:
        scored = [pair for pair in scored if pair[1] >= 6]
    if not scored:
        # 분야 이름만 물으면 그 분류의 입구를 연다. 문장 중 일반 주제어는 확장하지 않는다.
        category = query.strip()
        scored = [(entry, 1) for entry in snapshot.entries
                  if any(normalize(part) == category for part in entry.path)]
        if scored:
            mode = "category_exact"
            scored.sort(key=lambda pair: (pair[0].path, pair[0].name, pair[0].id))
    return scored, mode


def _browse_rows(snapshot, path):
    """편집 분류의 한 단계를 열람. 분류를 의미론적 broader 관계로 주장하지 않는다."""
    from dataclasses import asdict
    categories, leaves = {}, []
    prefix = tuple(path)
    for entry in snapshot.entries:
        if entry.path[:len(prefix)] != prefix:
            continue
        if len(entry.path) == len(prefix):
            leaves.append(dict(asdict(entry), item_type="entry"))
        else:
            child = entry.path[:len(prefix) + 1]
            categories[child] = categories.get(child, 0) + 1
    rows = [dict(item_type="category", name=p[-1], path=list(p), entry_count=count,
                 browse=dict(op="browse", path=list(p), revision=snapshot.revision))
            for p, count in sorted(categories.items())]
    return rows + sorted(leaves, key=lambda row: (row["name"], row["id"]))


def lookup(root, *, op="search", query="", id="", offset=0, limit=10, revision="", path=None):
    """등록 스크립트의 읽기 전용 전체 지도 조회. snapshot이 다르면 페이지를 섞지 않는다."""
    from dataclasses import asdict
    snapshot = load_snapshot(root)
    if revision and revision != snapshot.revision:
        return {"items": [], "status": "stale_revision", "revision": snapshot.revision,
                "truncated": False, "omitted": 0}
    if op not in {"search", "open", "neighbors", "ancestors", "browse"}:
        raise ValueError("op must be search/open/neighbors/ancestors/browse")
    if not isinstance(query, str) or not isinstance(id, str):
        raise ValueError("query and id must be strings")
    if type(offset) is not int or type(limit) is not int or offset < 0 or not 1 <= limit <= 50:
        raise ValueError("offset >= 0 and limit 1..50 required")
    if path is None:
        path = []
    if not isinstance(path, list) or len(path) > 5:
        raise ValueError("path must be a list of up to 5 category names")
    path = [_text(part, 40) for part in path]
    if path and op != "browse":
        raise ValueError("path is only supported for browse")
    if op == "browse" and (query or id):
        raise ValueError("browse uses path, not query or id")
    nodes = {e.id: e for e in snapshot.entries}
    mode = "snapshot"
    if op == "browse":
        rows = _browse_rows(snapshot, path)
    elif op == "search":
        if query.strip():
            found, mode = search(root, snapshot, query)
            rows = [dict(asdict(e), score=score) for e, score in found]
        else:
            rows = [asdict(e) for e in snapshot.entries]
    elif id not in nodes:
        return {"items": [], "status": "not_found", "revision": snapshot.revision,
                "truncated": False, "omitted": 0}
    elif op == "open":
        edges = [asdict(e) for e in snapshot.graph.edges if id in {e.subject, e.object}]
        refs = {r for e in edges for r in e["evidence_ids"]}
        rows = [dict(asdict(nodes[id]), edges=edges,
                     evidence=[asdict(e) for e in snapshot.graph.evidence if e.id in refs])]
    elif op == "neighbors":
        rows = [dict(asdict(nodes[e.object if e.subject == id else e.subject]), edge=asdict(e))
                for e in snapshot.graph.edges if id in {e.subject, e.object}]
    else:
        rows, frontier, seen = [], [(id, [id])], {id}
        while frontier:
            current, path = frontier.pop(0)
            for edge in snapshot.graph.edges:
                if edge.subject != current or edge.predicate != "broader" or edge.status != "verified":
                    continue
                rows.append(dict(asdict(nodes[edge.object]), depth=len(path),
                                 via=path + [edge.object], edge=asdict(edge)))
                if edge.object not in seen:
                    seen.add(edge.object)
                    frontier.append((edge.object, path + [edge.object]))
    page = rows[offset:offset + limit]
    remaining = max(0, len(rows) - offset - len(page))
    next_args = dict(op=op, query=query, id=id, offset=offset + len(page), limit=limit,
                     revision=snapshot.revision) if remaining else None
    if next_args is not None and op == "browse":
        next_args["path"] = path
    return {"items": page, "status": "partial" if remaining else "ok" if rows else "no_match",
            "revision": snapshot.revision, "retrieval_mode": mode, "total": len(rows),
            "truncated": bool(remaining), "omitted": remaining, "next": next_args,
            "browse": dict(op="browse", path=[], revision=snapshot.revision)}
