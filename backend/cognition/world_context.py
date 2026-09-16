"""현재 세계 어휘의 위치·관계를 한 번 포장해 의식과 실행에 전달한다."""
import hashlib
import json
import math
from dataclasses import asdict
from html import escape

from knowledge_graph import MANDATORY, bundle

CONTEXT_VERSION = "world-context-4-vocabulary"
HEADER = "<method_map>\n세계 지도 · 참고 어휘\n<world_data>\n"
FOOTER = "\n</world_data>\n</method_map>"
_RELATION_LABELS = {
    "broader": "상위", "related": "연관", "implements": "구현",
    "addresses": "용도", "requires": "필요", "applicable_when": "적합조건",
    "unsuitable_when": "부적합조건", "alternative_to": "대안",
    "complements": "보완", "uses_source": "자료원", "evaluated_by": "평가기준",
}


def estimate_tokens(value):
    """모델별 토큰 실측이 아닌 명시적 UTF-8 바이트/2 추정 예산."""
    return math.ceil(len(value.encode("utf-8")) / 2)


def render_context(context):
    """이름과 관계만 건넨다. 설명·검증 정보는 검색/상세 조회/내부 원장이 소유한다."""
    nodes = {node["id"]: node for node in context["nodes"]}
    names = [node["name"] for node in nodes.values()]
    labels = {nid: (node["name"] if names.count(node["name"]) == 1
                    else " / ".join((*node["path"], node["name"])))
              for nid, node in nodes.items()}
    # 동명이면서 분류까지 같은 경우에도 서로 다른 어휘를 합치지 않는다.
    duplicates = {label for label in labels.values() if list(labels.values()).count(label) > 1}
    labels = {nid: label + (f" [{nid}]" if label in duplicates else "")
              for nid, label in labels.items()}
    grouped, connected = {}, set()
    for edge in context["edges"]:
        subject, target = edge["subject"], edge["object"]
        value = _RELATION_LABELS[edge["predicate"]] + "=" + labels[target]
        if edge["condition"]:
            value += " (" + edge["condition"] + ")"
        grouped.setdefault(subject, []).append(value)
        connected.update((subject, target))
    lines = [labels[nid] + ": " + "; ".join(values) for nid, values in grouped.items()]
    for nid, node in nodes.items():
        if nid not in connected:
            lines.append(labels[nid] if labels[nid] != node["name"]
                         else " / ".join((*node["path"], node["name"])))
        if node["scope_note"]:
            lines.append(labels[nid] + " (" + node["scope_note"] + ")")
    if context["conflicts"]:
        lines.append("관계 충돌 있음")
    return HEADER + escape("\n".join(lines)) + FOOTER


def assemble(snapshot, candidates, *, max_seeds=4, max_nodes=16, max_edges=20,
             max_chars=6000, max_tokens=1800, query_kind="primary"):
    """완전한 seed 묶음만 넣는다. 필수 조건이 안 들어가면 추천 자체를 생략한다."""
    by_id = {e.id: e for e in snapshot.entries}
    evidence = {e.id: e for e in snapshot.graph.evidence}
    context = {"version": CONTEXT_VERSION, "revision": snapshot.revision,
               "query_provenance": query_kind, "seeds": [], "nodes": [], "edges": [],
               "evidence_refs": [], "omitted": [], "conflicts": [], "digest": "0" * 64,
               "token_estimator": "utf8_bytes/2_estimate"}
    # 충돌 표지 자리를 확보한다. 생략 상세는 내부 원장에만 남긴다.
    reserve = 100
    for entry, score in candidates:
        reason = "seed_budget" if len(context["seeds"]) >= max_seeds else ""
        node_ids, edges = bundle(snapshot.graph, entry.id)
        blocked = [e for e in snapshot.graph.edges if e.subject in node_ids
                   and e.predicate in MANDATORY and e.status != "verified"]
        if blocked:
            reason = "unreviewed_required_relation"
        new_nodes = {n["id"]: n for n in context["nodes"]}
        for nid in sorted(node_ids, key=lambda n: (n != entry.id, n)):
            new_nodes[nid] = asdict(by_id[nid])
        new_edges = {e["id"]: e for e in context["edges"]}
        for edge in edges:
            new_edges[edge.id] = dict(asdict(edge), condition_state=(
                "unknown" if edge.condition or edge.predicate in MANDATORY else "not_applicable"))
        refs = {eid for e in new_edges.values() for eid in e["evidence_ids"]}
        trial = dict(context, nodes=list(new_nodes.values()), edges=list(new_edges.values()),
                     evidence_refs=[asdict(evidence[eid]) for eid in sorted(refs)],
                     seeds=context["seeds"] + [{"id": entry.id, "score": score, "reason": "lexical"}])
        snippet = render_context(trial)
        if len(new_nodes) > max_nodes or len(new_edges) > max_edges:
            reason = reason or "structure_budget"
        elif len(snippet) + reserve > max_chars or estimate_tokens(snippet) + reserve > max_tokens:
            reason = reason or "context_budget"
        if reason:
            context["omitted"].append({"id": entry.id, "reason": reason})
        else:
            context = trial
    included = {n["id"] for n in context["nodes"]}
    context["conflicts"] = [asdict(e) for e in snapshot.graph.edges
                            if e.status == "disputed" and {e.subject, e.object} & included]
    # 충돌을 가진 일반 관계는 자동 확장에 쓰지 않는다. 자세한 주장은 open에서 열람한다.
    canonical = json.dumps(context, ensure_ascii=False, sort_keys=True)
    context["digest"] = hashlib.sha256(canonical.encode()).hexdigest()
    snippet = render_context(context) if context["nodes"] else ""
    return context, snippet
