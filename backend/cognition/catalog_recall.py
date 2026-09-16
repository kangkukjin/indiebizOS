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
    from supervision_bus import current

    started = time.monotonic()
    event = {"status": "disabled", "mode": "none", "ids": [], "count": 0,
             "chars": 0, "query_kind": "primary", "revision": None}
    def finish(snippet=""):
        event["elapsed_ms"] = round((time.monotonic() - started) * 1000, 3)
        _record(event)
        return snippet

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
            return finish(snippet)
        except Exception as exc:
            event.update(status="error", error=type(exc).__name__)
            return finish()
