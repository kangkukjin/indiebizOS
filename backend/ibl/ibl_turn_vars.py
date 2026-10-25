"""Turn-scoped authored drafts; execution state belongs to the current journal."""
import hashlib
import json
import os
from typing import Optional


def _task_key() -> Optional[str]:
    try:
        from thread_context import get_current_task_id
        task = get_current_task_id() or ""
    except Exception:
        task = ""
    return hashlib.sha256(task.encode("utf-8", "replace")).hexdigest()[:20] if task else None


def draft_path(key: str) -> str:
    # .json — data/**/*.json 무시 규칙에 들어가 스필 부산물이 작업 트리에 뜨지 않는다(다른 스필 파일과 한 벌)
    from common.spill import spill_dir
    return os.path.join(spill_dir(), f"turn_draft_{key}.json")


def save_draft(code: str) -> bool:
    key = _task_key()
    if not key or not (code or "").strip():
        return False
    with open(draft_path(key), "w", encoding="utf-8") as f:
        json.dump({"code": code}, f, ensure_ascii=False)
    return True


def load_draft() -> str:
    key = _task_key()
    if not key:
        return ""
    try:
        with open(draft_path(key), encoding="utf-8") as f:
            obj = json.load(f)
        return str(obj.get("code") or "") if isinstance(obj, dict) else ""
    except (OSError, ValueError):
        return ""
