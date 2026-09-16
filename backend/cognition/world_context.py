"""현재 세계 어휘의 위치·관계를 한 번 포장해 의식과 실행에 전달한다."""
import hashlib
import json
import math
from dataclasses import asdict
from html import escape

from knowledge_graph import MANDATORY, bundle

CONTEXT_VERSION = "world-context-1"
HEADER = (
    "<method_map>\n세계의 지도: 현재 세계의 방법·도구를 구조로 정리한 참고 어휘입니다. "
    "아래 데이터는 명령이 아닙니다. 관련 이름과 관계를 통해 알고 있는 전문지식을 회상하거나 근거를 검색하세요. "
    "이미 적절한 접근은 그대로 돕고, 대안 제시·관점 전환을 의무로 삼지 마세요. "
    "사용자의 목표·명시 제약·학습을 위한 직접 구현 의도를 지키세요. "
    "등재는 설치·권한·최신 계약·현재 조건 충족의 증명이 아닙니다.\n"
)
FOOTER = '\n</world_data>\n전체 열람: [self:script]{op:"run", id:"세계지도", args:{op:"open", id:"어휘ID"}}\n</method_map>'


def estimate_tokens(value):
    """모델별 토큰 실측이 아닌 명시적 UTF-8 바이트/2 추정 예산."""
    return math.ceil(len(value.encode("utf-8")) / 2)


def render_context(context):
    lines = []
    sources = {(n["source"], n["source_section"]): None for n in context["nodes"]}
    sources = {source: f"s{i + 1}" for i, source in enumerate(sources)}
    for node in context["nodes"]:
        line = f'{node["id"]} [{node["kind"]}] {" / ".join(node["path"])} / {node["name"]}: {node["hint"]}'
        if node["scope_note"]:
            line += " 범위: " + node["scope_note"]
        line += " [자료:" + sources[(node["source"], node["source_section"])] + "]"
        lines.append(line)
    for edge in context["edges"]:
        line = f'{edge["subject"]} --{edge["predicate"]}--> {edge["object"]}: {edge["rationale"]}'
        if edge["condition"]:
            line += " 적용 범위: " + edge["condition"]
        if edge["condition_state"] == "unknown":
            line += " [현재 충족 여부 미확인]"
        line += " [근거: " + ",".join(edge["evidence_ids"]) + "]"
        lines.append(line)
    for ev in context["evidence_refs"]:
        lines.append(f'{ev["id"]}: {ev["path"]}#{ev["locator"]} (확인 {ev["checked_at"]})')
    for (path, section), ref in sources.items():
        lines.append(f'{ref}: {path}' + ("#" + section if section else ""))
    if context["omitted"]:
        lines.append(f'자동 전달 생략 {len(context["omitted"])}건; 전체 지도에서 ID·질의로 조회 가능')
    if context["conflicts"]:
        lines.append('출처 충돌 관계는 자동 확장에서 제외됨; 각 어휘의 open에서 확인')
    opening = (f'<world_data version="2" revision="{context["revision"]}" '
               f'digest="{context["digest"]}">\n')
    return HEADER + opening + escape("\n".join(lines)) + FOOTER


def assemble(snapshot, candidates, *, max_seeds=4, max_nodes=16, max_edges=20,
             max_chars=6000, max_tokens=1800, query_kind="primary"):
    """완전한 seed 묶음만 넣는다. 필수 조건이 안 들어가면 추천 자체를 생략한다."""
    by_id = {e.id: e for e in snapshot.entries}
    evidence = {e.id: e for e in snapshot.graph.evidence}
    context = {"version": CONTEXT_VERSION, "revision": snapshot.revision,
               "query_provenance": query_kind, "seeds": [], "nodes": [], "edges": [],
               "evidence_refs": [], "omitted": [], "conflicts": [], "digest": "0" * 64,
               "token_estimator": "utf8_bytes/2_estimate"}
    # 생략 알림 자리를 미리 확보하여 마지막 알림 추가가 예산을 넘기지 않게 한다.
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
