"""세계의 지도: 관련 어휘와 구조를 한 번 전달한다. 추가 모델 호출은 없다."""
import json
import re
import time
from contextlib import nullcontext
from html import escape

from knowledge_catalog import load_snapshot, search
from runtime_utils import get_base_path
from world_context import assemble, estimate_tokens

_OPEN = "<method_map>\n세계 지도 · 참고 어휘"
_CLOSE = "\n</method_map>"
_FOLLOWUP = re.compile(r"^(?:그걸|그것|그 방법|그대로|이어서|계속|이걸|이 방법)")
MAX_ITEMS = 4
MAX_CHARS = 600


def load_config(root):
    """다음 턴부터 토글이 적용된다. world_pulse의 장기 캐시와 별개로 읽는다."""
    try:
        config = json.loads((root / "data/world_pulse_config.json").read_text(encoding="utf-8"))
    except FileNotFoundError:
        return {}
    section = config.get("knowledge_catalog", {})
    if not isinstance(section, dict):
        raise ValueError("invalid knowledge_catalog configuration")
    return section


def previous_query(message, history):
    if len(message) > 80 or not _FOLLOWUP.match(message.strip()):
        return ""
    selected, size = [], 0
    for item in reversed(history or []):
        if item.get("role") != "user":
            continue
        content = item.get("content")
        if not isinstance(content, str) or content == message:
            continue
        if size + len(content) > 400:
            break
        selected.append(content)
        size += len(content) + 1
        if len(selected) == 2:
            break
    return "\n".join(reversed(selected))


def render(candidates, max_items=MAX_ITEMS, max_chars=MAX_CHARS):
    lines, ids, omitted = [], [], []
    for entry, _score in candidates:
        line = f"\n- {escape(entry.path[-1])} / {escape(entry.name)}"
        if len(ids) >= max_items:
            omitted.append({"id": entry.id, "reason": "item_budget"})
        elif len(_OPEN + "".join(lines) + line + _CLOSE) > max_chars:
            omitted.append({"id": entry.id, "reason": "char_budget"})
        else:
            lines.append(line)
            ids.append(entry.id)
    return (_OPEN + "".join(lines) + _CLOSE if lines else ""), ids, omitted


def _record(event):
    from episode_logger import record_trajectory_event
    record_trajectory_event("knowledge_catalog.selected", event)


def recall_for_turn(runner, message, history, *, request_type, reflex_hint=None,
                    force_role=None, context_update=False):
    """종전 계약: 스니펫 문자열. 자동 주입 경로는 recall_for_turn_detail(제시 id·이름 포함)을 쓴다."""
    return recall_for_turn_detail(runner, message, history, request_type=request_type, reflex_hint=reflex_hint,
                                  force_role=force_role, context_update=context_update)[0]


def recall_for_turn_detail(runner, message, history, *, request_type, reflex_hint=None,
                           force_role=None, context_update=False):
    """(snippet, event, names) — names = {id: [이름, 별칭…]} 제시된 항목의 결합 키(제시→사용 결합, 2026-09-18)."""
    from supervision_bus import current

    started = time.monotonic()
    event = {"status": "disabled", "mode": "none", "ids": [], "count": 0,
             "chars": 0, "query_kind": "primary", "revision": None}
    names = {}
    def finish(snippet=""):
        event["elapsed_ms"] = round((time.monotonic() - started) * 1000, 3)
        _record(event)
        return snippet, event, names

    # 세계 어휘는 개인 기억이 아니다. 주체·에이전트·실행 역할로 막지 않는다.
    # 모델이 없는 세션 제어만 제외한다. 개인 기억의 권한 관문은 별도로 유지한다.
    if request_type not in {"THINK", "REPAIR", "EXECUTE", "CONTEXT_UPDATE"}:
        event.update(status="excluded")
        return finish()
    root = get_base_path()
    try:
        config = load_config(root)
        if config.get("enabled", True) is False:
            return finish()
        if "enabled" in config and type(config["enabled"]) is not bool:
            raise ValueError("enabled must be a boolean")
        # 과거 실험용 허용 목록은 읽어도 선택에 사용하지 않는다. 이행은 사건으로 드러낸다.
        event["ignored_config"] = [key for key in ("enabled_agents",) if key in config]
        presentation = config.get("mode", "structure")
        if presentation not in {"names", "structure"}:
            raise ValueError("invalid catalog presentation mode")
        structured = presentation == "structure"
        requested = {"items": int(config.get("max_items", MAX_ITEMS)),
                     "chars": int(config.get("max_chars", MAX_CHARS))}
        max_items = max(0, min(MAX_ITEMS, requested["items"]))
        max_chars = max(0, min(MAX_CHARS, requested["chars"]))
        effective = {"items": max_items, "chars": max_chars}
        if structured:
            requested["chars"] = int(config.get("structure_max_chars", 6000))
            requested["tokens"] = int(config.get("max_tokens", 1800))
            max_chars = max(0, min(12000, requested["chars"]))
            max_tokens = max(0, min(6000, requested["tokens"]))
            effective.update(chars=max_chars, tokens=max_tokens)
        event.update(requested_budget=requested, effective_budget=effective,
                     clamped=requested != effective)
    except Exception as exc:
        event.update(status="error", error=type(exc).__name__)
        return finish()
    controller = current()
    # preparation이 일으킨 취소는 fail-soft 경계 밖에서 기존 파이프라인으로 전파한다.
    with controller.preparation("knowledge_catalog") if controller else nullcontext():
        try:
            snapshot = load_snapshot(root)
            candidates, mode = search(root, snapshot, message)
            auxiliary = previous_query(message, history)
            if not candidates and auxiliary:
                candidates, mode = search(root, snapshot, auxiliary)
                candidates = [(e, score * 0.25) for e, score in candidates]
                event["query_kind"] = "context"
            if structured:
                context, snippet = assemble(
                    snapshot, candidates, max_seeds=max_items,
                    max_chars=max_chars, max_tokens=max_tokens,
                    query_kind=event["query_kind"])
                ids = [node["id"] for node in context["nodes"]]
                omitted = context["omitted"]
                event.update(context_digest=context["digest"], edge_ids=[e["id"] for e in context["edges"]],
                             seeds=context["seeds"], token_estimate=estimate_tokens(snippet),
                             token_estimator=context["token_estimator"], presentation="structure")
            else:
                snippet, ids, omitted = render(candidates, max_items, max_chars)
            status = "selected" if ids else "no_match" if not candidates else "budget_empty"
            if not ids and any(o["reason"] == "unreviewed_required_relation" for o in omitted):
                status = "withheld"
            event.update(status=status,
                         mode=mode, revision=snapshot.revision, ids=ids, count=len(ids),
                         chars=len(snippet), omitted=omitted,
                         semantic="unavailable" if config.get("semantic_enabled") else "disabled")
            by_id = {e.id: e for e in snapshot.entries}
            names.update({i: identity_names(by_id[i]) for i in ids if i in by_id})
            return finish(snippet)
        except Exception as exc:
            event.update(status="error", error=type(exc).__name__)
            return finish()


def identity_names(entry):
    """제시→사용 결합에 쓰는 이름 — 그 방법의 고유 이름과 괄호로 병기한 이름만.

    별칭은 질문이 방법에 닿게 하는 검색 열쇠(상황 낱말: 'csv'·'sql'·'선후관계')다. 사용 증거로 다시 쓰면
    과제의 파일 이름이나 요청문에 걸려, 쓰지 않은 방법이 사용으로 남는다(긴문장 L18-5: 입력 `tasks_a.csv` 로
    DuckDB 가 두 턴 연속 used)."""
    import re
    parts = [p.strip() for p in re.split(r"[()（）]", entry.name or "") if p.strip()]
    return list(dict.fromkeys([entry.name, *parts]))


def world_memory_for_turn(message, lexical_snippet=""):
    """종전 계약: 스니펫 문자열. 자동 주입 경로는 world_memory_detail 을 쓴다."""
    return world_memory_detail(message, lexical_snippet)[0]


def world_memory_detail(message, lexical_snippet="", *, budget=None):
    """(snippet, event, names) — names = {id: [이름, 별칭…]} 고른 어휘의 결합 키(제시→사용 결합, 2026-09-18).

    세계의 기억 — 지도(최상위 분야)와 가지 먼저 고른 어휘 3건 (공통 회상 설계 §5.6, 2026-09-17).

    위의 <method_map>(글자 일치 seed + 관계 조각)은 이름을 실제로 말했을 때의 정밀한 길이고, 이 블록은 표현이 달라도
    닿는 의미 채널이다(실측: 새 질문 2/24 → 17/24). 심층기억의 <memory_map>·<recalled_memory> 와 같은 함수
    (tree_recall.recall)를 쓴다. 관련 없음은 기계가 가르지 못하므로 작게 싣고 판단은 받는 AI 가 한다.
    글자 조각에 이미 나온 이름은 뺀다. 인코더 적재·첫 색인은 백그라운드 — 그동안은 지도만 실린다.
    """
    started = time.monotonic()
    event = {"status": "disabled", "mode": "semantic", "ids": [], "branches": [], "chars": 0}
    names = {}
    try:
        root = get_base_path()
        config = load_config(root)
        # 끄는 키는 `world_memory`(기본 켬). 옛 `semantic_enabled` 는 의미 검색이 없던 때의 자리표라 읽지 않는다.
        if config.get("enabled", True) is False or config.get("world_memory", True) is False:
            return "", event, names
        import tree_recall
        from world_recall_store import WorldStore
        store = WorldStore(root)
        r = tree_recall.recall(store, message, **(budget or {}))
        picked = [it for it in r["items"] + r["outside"] if it.label.split(": ", 1)[-1] not in (lexical_snippet or "")]
        parts = ['<world_map note="세계 지도의 최상위 분야 (어휘 수). 아래 분류와 어휘는 '
                 '[self:script]{op:\\"run\\", id:\\"세계지도\\", args:{op:\\"browse\\", path:[\\"<분야>\\"]}} 로 내려가며 본다.">\n'
                 + store.map_text() + "\n</world_map>"]
        by_id = {e.id: e for e in store.snapshot.entries}
        shown_ids = []
        if picked and r["status"] in {"ok", "lexical_only"}:
            context, structured = assemble(
                store.snapshot, [(by_id[it.id], 1.0) for it in picked if it.id in by_id],
                max_seeds=MAX_ITEMS,
                max_chars=max(0, min(12000, int(config.get("structure_max_chars", 6000)))),
                max_tokens=max(0, min(6000, int(config.get("max_tokens", 1800)))),
                query_kind="semantic" if r["status"] == "ok" else "lexical")
            shown_ids = [node["id"] for node in context["nodes"]]
            event.update(seeds=context["seeds"], omitted=context["omitted"],
                         edge_ids=[edge["id"] for edge in context["edges"]],
                         context_digest=context["digest"],
                         token_estimate=estimate_tokens(structured),
                         token_estimator=context["token_estimator"])
            branches = ", ".join("/".join(b) for b in r["branches"])
            if structured:
                parts.append('<world_memory note="이 질문의 방법 후보와 관계. 적합·필수 조건을 확인하고, '
                             '설치·권한·실행 가능성은 describe로 확인한다. 관련 없으면 무시하고 위 지도에서 직접 찾는다.">\n'
                             f"고른 가지: {escape(branches)}\n" + structured + "\n</world_memory>")
        snippet = "\n".join(parts)
        names.update({i: identity_names(by_id[i]) for i in shown_ids})
        event.update(status=r["status"], ids=shown_ids, branches=["/".join(b) for b in r["branches"]],
                     chars=len(snippet), outside_beats_inside=r.get("outside_beats_inside", False),
                     revision=store.snapshot.revision)
        if picked and not shown_ids and event.get("omitted"):
            event["status"] = ("withheld" if any(o["reason"] == "unreviewed_required_relation"
                                               for o in event["omitted"]) else "budget_empty")
        return snippet, event, names
    except Exception as exc:
        event.update(status="error", error=type(exc).__name__)
        return "", event, names
    finally:
        event["elapsed_ms"] = round((time.monotonic() - started) * 1000, 3)
        _record(dict(event, channel="world_memory"))
