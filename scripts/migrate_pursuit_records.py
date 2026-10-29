#!/usr/bin/env python3
"""은퇴 과제의 수리 완료 의도를 기존 수리 기준으로 옮긴다. 기본은 읽기 전용 점검."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))
import boot_paths  # noqa: E402,F401
import argparse
import copy
import hashlib
import json

from restart_protocol import atomic_json
from supervisor_handoff import criteria_contract

FIELDS = {"scope", "title", "goal_criteria", "pursuit_id", "pursuit_reason", "detach_pursuit"}


def convert_record(row, fallback=None, *, review=False):
    """저장된 기준만 옮긴다. 과거 전체 목표를 추측으로 새 합격 조건으로 만들지 않는다."""
    result = copy.deepcopy(row)
    request = result.get("done_request") or ((result.get("packet") or {}).get("context") or {}).get("completion_request") or {}
    previous = result.get("pursuit") or result.get("original_pursuit") or {}
    if review:
        context = result.setdefault("packet", {}).setdefault("context", {})
        contract = copy.deepcopy(context.get("criteria_contract") or fallback)
    else:
        contract = copy.deepcopy(result.get("criteria_contract") or fallback)
    if not contract:
        contract = criteria_contract(result.get("goal", ""), result.get("framing") or {})
    if not isinstance(contract, dict) or not isinstance(contract.get("criteria"), list) or not contract["criteria"]:
        raise ValueError("보존된 수리 완료 기준을 확인할 수 없습니다")
    goal = request.get("goal_criteria")
    if goal and not any(c.get("text") == goal for c in contract["criteria"]):
        # Prior evaluator added precisely this completion request to the criteria.
        ids = {c.get("id") for c in contract["criteria"]}
        ident = "G1"
        while ident in ids:
            ident += "_saved"
        contract["criteria"].append({"id": ident, "text": goal, "source": "saved_completion_request"})
    if previous.get("goal_criteria"):
        # Old framing context survives, but is not silently promoted into a new criterion.
        contract.setdefault("previous_overall_goal", previous["goal_criteria"])
    if review:
        context["criteria_contract"] = contract
        context.pop("completion_request", None)
    else:
        result["criteria_contract"] = contract
        if request:
            result["completion_review_required"] = True
    for name in ("pursuit", "original_pursuit", "done_request"):
        result.pop(name, None)
    if isinstance(result.get("framing"), dict):
        result["framing"] = {k: v for k, v in result["framing"].items() if k not in FIELDS}
    return result


def _read(path):
    return json.loads(path.read_text()) if path.is_file() else {}


def prepare(root):
    root = Path(root).resolve()
    changes, errors = {}, []
    for path in sorted((root / "data/system_ai_state/repair_continuations").glob("*.json")):
        row = _read(path)
        if not (row.get("pursuit") or row.get("original_pursuit") or row.get("done_request") or (row.get("framing") or {}).get("pursuit_id")):
            continue
        task = row.get("staging_task_id") or row.get("task_id", "")
        if not task or Path(task).name != task:
            errors.append({"file": str(path.relative_to(root)), "reason": "invalid task identity"})
            continue
        session = _read(root / "data/system_ai_state/repair_sessions" / (task + ".json"))
        fallback = (session.get("readiness") or {}).get("criteria")
        review_path = Path(row["review_path"]).resolve() if row.get("review_path") else None
        try:
            saved = {}
            if review_path:
                if not review_path.is_relative_to(root / "data/spill/supervision") or review_path.name != "repair_review.json":
                    raise ValueError("검수 체크포인트 경로를 확인해야 합니다")
                saved = _read(review_path)
                fallback = ((saved.get("packet") or {}).get("context") or {}).get("criteria_contract") or fallback
            converted = convert_record(row, fallback)
            changes[path] = (path.read_bytes(), converted)
            if saved:
                review_row = convert_record(saved, converted["criteria_contract"], review=True)
                changes[review_path] = (review_path.read_bytes(), review_row)
        except ValueError as exc:
            # Terminal history is never scheduled; leave its original bytes intact if its old schema is incomplete.
            errors.append({"file": str(path.relative_to(root)), "status": row.get("status"), "reason": str(exc)})
    return changes, errors


def apply(root, changes, backup):
    root, backup = Path(root).resolve(), Path(backup).resolve()
    if not backup.is_relative_to(root / "data/_backups"):
        raise ValueError("백업은 data/_backups 안에 저장해야 합니다")
    # Validate every input before writing any record; runtime must be quiescent during conversion.
    for path, (original, _) in changes.items():
        if path.read_bytes() != original:
            raise ValueError("점검 이후 수리 기록이 바뀌었습니다")
    manifest = []
    for path, (original, converted) in changes.items():
        relative = path.relative_to(root)
        target = backup / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        if target.exists() and target.read_bytes() != original:
            raise ValueError("다른 원문 백업을 덮어쓸 수 없습니다")
        target.write_bytes(original)
        manifest.append({"path": str(relative), "before": hashlib.sha256(original).hexdigest()})
    for path, (original, converted) in changes.items():
        if path.read_bytes() != original:
            raise ValueError("점검 이후 수리 기록이 바뀌었습니다. 백업과 manifest를 확인하세요")
        atomic_json(path, converted)
    for item in manifest:
        item["after"] = hashlib.sha256((root / item["path"]).read_bytes()).hexdigest()
    atomic_json(backup / "manifest.json", manifest)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    changes, errors = prepare(args.root)
    blocking = [e for e in errors if e.get("status") not in {"completed", "cancelled", "continued"}]
    print(json.dumps({"files": len(changes), "unresolved": errors, "applied": False}, ensure_ascii=False))
    if args.apply:
        if blocking:
            raise SystemExit("미완료 수리의 기준을 확인한 뒤 적용하세요")
        apply(args.root, changes, args.root / "data/_backups/2026-10-29_pursuit_removal/records")
        print(json.dumps({"applied_files": len(changes)}))


if __name__ == "__main__":
    main()
