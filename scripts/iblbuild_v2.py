"""Builder seam for the edition 2 contract validator (runtime owns semantics)."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))
import boot_paths  # noqa: E402,F401
from ibl_v2_adapters import validate_contract


def validate_v2_contracts(data):
    issues = []
    for name, node in (data.get("nodes") or {}).items():
        if not isinstance(node, dict):
            continue
        for action, entry in (node.get("actions") or {}).items():
            if isinstance(entry, dict) and "callable_contract" in entry:
                try:
                    validate_contract(entry["callable_contract"])
                except (ValueError, KeyError, TypeError) as exc:
                    issues.append(f"{name}:{action} callable_contract: {exc}")
    return issues


def check_v2_corpus(code, entry, issues, origin, session=None):
    from ibl_edition import source_edition
    try:
        if source_edition(code, entry.get("edition")) != 2:
            return False
        from ibl_v2_learning import check_source
        kwargs = {}
        if session is not None:
            if not session:
                try:
                    from ibl_v2_adapters import load_registry
                    from ibl_v2_store import definitions
                    session.update(registry=load_registry(), library=definitions())
                except Exception as exc:
                    session['error'] = exc
            if 'error' in session:
                raise session['error']
            kwargs = session
        why = check_source(code, bool(entry.get("alias")) or entry.get("category") == "phrase", **kwargs)
        if why:
            issues.append(f"{origin}: 판본 2 용례 검사 — {why}")
    except Exception as exc:
        issues.append(f"{origin}: 판본 2 검사 불가 — {exc}")
    return True
