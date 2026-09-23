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
