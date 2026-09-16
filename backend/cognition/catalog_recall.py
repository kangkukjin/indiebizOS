"""방법의 지도: 이번 일에 쓸 도구·방법의 이름을 한 번 고른다. 추가 모델 호출은 없다."""
import json
import re
import time
from contextlib import nullcontext
from html import escape

from knowledge_catalog import load_snapshot, search
from runtime_utils import get_base_path

_OPEN = ("<method_map>\n방법의 지도: 이번 일에 쓸 수 있는 도구·방법의 이름입니다. 적합한 것만 활용하세요. "
         "도구의 설치·사용 가능 여부는 별도 확인이 필요합니다.")
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
        line = f"\n- {escape(entry.path[-1])} / {escape(entry.name)} — {escape(entry.hint)}"
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
    import principal
    from supervision_bus import current
    from thread_context import get_current_registry_key

    started = time.monotonic()
    event = {"status": "disabled", "mode": "none", "ids": [], "count": 0,
             "chars": 0, "query_kind": "primary", "revision": None}
    def finish(snippet=""):
        event["elapsed_ms"] = round((time.monotonic() - started) * 1000, 3)
        _record(event)
        return snippet

    if (not principal.is_owner() or context_update or reflex_hint or force_role
            or request_type not in {"THINK", "REPAIR", "EXECUTE"}):
        event.update(status="excluded")
        return finish()
    root = get_base_path()
    try:
        config = load_config(root)
        if config.get("enabled") is not True:
            return finish()
        agents = config.get("enabled_agents")
        if agents is not None and (not isinstance(agents, list) or not all(isinstance(a, str) for a in agents)):
            raise ValueError("enabled_agents must be a list")
        registry = getattr(runner, "registry_key", None) or get_current_registry_key()
        if agents is not None and registry not in agents:
            event.update(status="agent_disabled")
            return finish()
        requested = {"items": int(config.get("max_items", MAX_ITEMS)),
                     "chars": int(config.get("max_chars", MAX_CHARS))}
        max_items = max(0, min(MAX_ITEMS, requested["items"]))
        max_chars = max(0, min(MAX_CHARS, requested["chars"]))
        effective = {"items": max_items, "chars": max_chars}
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
            snippet, ids, omitted = render(candidates, max_items, max_chars)
            event.update(status="selected" if ids else "no_match" if not candidates else "budget_empty",
                         mode=mode, revision=snapshot.revision, ids=ids, count=len(ids),
                         chars=len(snippet), omitted=omitted,
                         semantic="unavailable" if config.get("semantic_enabled") else "disabled")
            return finish(snippet)
        except Exception as exc:
            event.update(status="error", error=type(exc).__name__)
            return finish()
