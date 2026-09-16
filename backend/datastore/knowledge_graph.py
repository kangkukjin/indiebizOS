"""세계 어휘의 검토된 관계. 세계의 명사·사례는 데이터에만 둔다."""
from dataclasses import dataclass
from datetime import date
import hashlib
import re
from pathlib import Path
from urllib.parse import urlparse

GRAPH_VERSION = "structure-1"
KINDS = {"term", "concept", "problem", "method", "tool", "resource", "criterion", "condition"}
RELATIONS = {
    "broader", "related", "implements", "addresses", "requires", "applicable_when",
    "unsuitable_when", "alternative_to", "complements", "uses_source", "evaluated_by",
}
SYMMETRIC = {"related", "alternative_to", "complements"}
STATUSES = {"proposed", "verified", "disputed", "retired"}
MANDATORY = {"requires", "applicable_when", "unsuitable_when", "evaluated_by"}


def text(value, limit=500):
    if not isinstance(value, str) or not value.strip() or len(value) > limit or "\n" in value:
        raise ValueError("invalid graph text")
    return value.strip()


def identifier(value):
    value = text(value, 80)
    if not re.fullmatch(r"[a-z0-9_.-]+", value):
        raise ValueError("invalid graph identifier")
    return value


def local_path(root, value):
    value = text(value, 300)
    path = (Path(root) / value).resolve()
    if Path(value).is_absolute() or not path.is_relative_to(Path(root).resolve()) or not path.is_file():
        raise ValueError("graph source must exist within repository")
    return value


@dataclass(frozen=True)
class Evidence:
    id: str
    path: str
    locator: str
    claim: str
    checked_at: str
    url: str = ""
    content_hash: str = ""
    current: bool = True


@dataclass(frozen=True)
class Edge:
    id: str
    subject: str
    predicate: str
    object: str
    rationale: str
    evidence_ids: tuple
    status: str
    condition: str = ""


@dataclass(frozen=True)
class Graph:
    edges: tuple = ()
    evidence: tuple = ()


def parse_graph(root, documents, entries):
    """ID/종류/방향/근거/직접 계층을 검증. 역간선을 정본에 중복 저장하지 않는다."""
    nodes = {e.id: e for e in entries}
    evidence, edges, seen, relations = {}, [], set(), set()
    for doc in documents:
        for row in doc.get("evidence", []):
            eid = identifier(row["id"])
            if eid in evidence:
                raise ValueError("duplicate evidence")
            checked = str(row["checked_at"])
            date.fromisoformat(checked)
            url = row.get("url", "")
            if url and (urlparse(url).scheme not in {"https", "http"} or not urlparse(url).netloc):
                raise ValueError("invalid evidence URL")
            path = local_path(root, row["path"])
            expected_hash = row["content_hash"]
            if not re.fullmatch(r"[0-9a-f]{64}", expected_hash):
                raise ValueError("invalid evidence content hash")
            current = hashlib.sha256((Path(root) / path).read_bytes()).hexdigest() == expected_hash
            evidence[eid] = Evidence(eid, path, text(row["locator"]), text(row["claim"]),
                                     checked, url, expected_hash, current)
    for doc in documents:
        for row in doc.get("edges", []):
            eid, s, p, o = (identifier(row[k]) for k in ("id", "subject", "predicate", "object"))
            if eid in seen or s not in nodes or o not in nodes or s == o or p not in RELATIONS:
                raise ValueError("invalid graph reference, predicate or duplicate ID")
            key = (min(s, o), p, max(s, o)) if p in SYMMETRIC else (s, p, o)
            if key in relations:
                raise ValueError("duplicate relation (including symmetric inverse)")
            refs = row["evidence_ids"]
            if not isinstance(refs, list) or not refs or any(r not in evidence for r in refs):
                raise ValueError("edge evidence unresolved")
            status = row.get("status", "proposed")
            if status not in STATUSES:
                raise ValueError("invalid edge status")
            if status == "verified" and any(not evidence[r].current for r in refs):
                status = "stale"
            sk, ok = nodes[s].kind, nodes[o].kind
            types = {
                "implements": ({"tool"}, {"method"}),
                "addresses": ({"method"}, {"problem"}),
                "requires": ({"method", "tool"}, {"condition", "resource"}),
                "applicable_when": ({"method", "tool"}, {"condition"}),
                "unsuitable_when": ({"method", "tool"}, {"condition"}),
                "uses_source": ({"method", "problem"}, {"resource"}),
                "evaluated_by": ({"method", "problem"}, {"criterion"}),
                "alternative_to": ({"method", "tool"}, {"method", "tool"}),
                "complements": ({"method", "tool"}, {"method", "tool"}),
            }
            if p in types and (sk not in types[p][0] or ok not in types[p][1]):
                raise ValueError("relation kind/direction mismatch")
            if p == "broader" and (sk != ok or sk not in {"concept", "problem", "method"}):
                raise ValueError("broader must generalize concepts of the same kind")
            condition = row.get("condition", "")
            if condition:
                condition = text(condition)
            if p in {"alternative_to", "complements"} and not condition:
                raise ValueError("alternative/complement needs explicit scope condition")
            edges.append(Edge(eid, s, p, o, text(row["rationale"]), tuple(refs), status, condition))
            seen.add(eid)
            relations.add(key)
    parents = {}
    for edge in edges:
        if edge.predicate == "broader":
            parents.setdefault(edge.subject, []).append(edge.object)
    closures = {}
    def ancestors(nid, stack):
        if nid in stack:
            raise ValueError("hierarchy cycle")
        if nid not in closures:
            found = set()
            for parent in parents.get(nid, []):
                found.add(parent)
                found.update(ancestors(parent, stack | {nid}))
            closures[nid] = found
        return closures[nid]
    for nid in nodes:
        ancestors(nid, set())
    for edge in edges:
        if edge.predicate == "related" and (edge.object in closures[edge.subject]
                                             or edge.subject in closures[edge.object]):
            raise ValueError("related conflicts with hierarchy")
    return Graph(tuple(sorted(edges, key=lambda e: e.id)), tuple(evidence.values()))


def bundle(graph, seed, max_hops=2):
    """문제↔방법↔도구를 양방향 조회하고 말단 방법의 조건까지 동봉한다."""
    chosen, nodes, frontier = {}, {seed}, {seed}
    usable = [e for e in graph.edges if e.status == "verified"]
    for depth in range(max_hops):
        following, connected = set(), set()
        for edge in usable:
            if edge.subject not in frontier and edge.object not in frontier:
                continue
            # 일반 연관·대안은 seed의 직접 연결만. 조건에서 다른 방법으로 번지지 않는다.
            if edge.predicate in {"related", "alternative_to", "complements"} and depth:
                continue
            if depth and edge.predicate in MANDATORY | {"uses_source"} and edge.subject not in frontier:
                continue
            chosen[edge.id] = edge
            connected.update((edge.subject, edge.object))
            if edge.predicate not in SYMMETRIC:
                following.update((edge.subject, edge.object))
        frontier = following - nodes
        nodes.update(connected)
    # 경계에서 찾은 방법/도구의 필수 조건을 예산 때문에 침묵 절단하지 않는다.
    for edge in usable:
        if edge.subject in nodes and edge.predicate in MANDATORY:
            chosen[edge.id] = edge
    nodes.update(n for e in chosen.values() for n in (e.subject, e.object))
    for _ in range(3):
        parents = [e for e in usable if e.subject in nodes and e.predicate == "broader"]
        for edge in parents:
            chosen[edge.id] = edge
            nodes.add(edge.object)
    return nodes, tuple(chosen.values())
