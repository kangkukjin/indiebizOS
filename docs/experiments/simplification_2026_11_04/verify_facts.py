"""Research-only probes: extract current functions; replace all operational dependencies.

No application imports, network calls, package activation or source edits.
Run from the canonical repository root with Python's standard library.
"""
import ast
import copy
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import threading
import types
from typing import Any, Optional

ROOT = Path(__file__).resolve().parents[3]


def extracted(relative, names, namespace):
    path = ROOT / relative
    tree = ast.parse(path.read_text())
    selected = [node for node in tree.body
                if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
                and node.name in names]
    assert len(selected) == len(names)
    exec(compile(ast.Module(body=selected, type_ignores=[]), str(path), "exec"), namespace)


def activation(profile):
    state = {"version": 1, "revision": 10, "active": {"pkg": True},
             "profiles": {"member": {"active": {"pkg": True}}}}
    writes, resets = [], []
    authority = object()

    def write(value):
        state.clear()
        state.update(copy.deepcopy(value))
        writes.append(copy.deepcopy(state))

    def reset():
        resets.append(len(resets) + 1)
        return ["synthetic cache failure"] if len(resets) == 1 else []

    namespace = dict(copy=copy, HUMAN_AUTHORITY=authority,
                     LOCK=threading.RLock(), package_path=lambda _: Path("/synthetic/pkg"),
                     is_active=lambda _: state["active"]["pkg"],
                     read_state=lambda: copy.deepcopy(state), write_state=write,
                     require_optional=lambda _: None, check_ready=lambda _: [],
                     inventory=lambda: {"packages": {}})
    extracted("backend/ibl/vocabulary_lifecycle.py", {"set_package_active"}, namespace)
    stub = types.ModuleType("ibl_routing")
    stub.invalidate_runtime_caches = reset
    previous = sys.modules.get("ibl_routing")
    sys.modules["ibl_routing"] = stub
    try:
        try:
            namespace["set_package_active"]("pkg", False, authority=authority, profile=profile)
        except RuntimeError as error:
            outcome = str(error)
        after_failure = copy.deepcopy(state)
        reset_count = len(resets)
        repeated = namespace["set_package_active"]("pkg", False, authority=authority, profile=profile)
        return {"profile": profile, "error": outcome, "state_after_failure": after_failure,
                "cache_reset_calls_before_retry": reset_count, "retry": repeated,
                "cache_reset_calls_after_retry": len(resets), "writes": writes}
    finally:
        if previous is None:
            sys.modules.pop("ibl_routing", None)
        else:
            sys.modules["ibl_routing"] = previous


def loader_fast_path():
    """Isolate the ownership-map refresh bypass, not a full deployed hot-reload test."""
    calls = []
    old = types.SimpleNamespace(package="old_package")
    namespace = dict(Optional=Optional, Any=Any,
                     _tool_handlers_cache={"tool": old},
                     _package_handlers_cache={"old_package": old},
                     _tool_to_package_map={"tool": "old_package"},
                     require_tool_active=lambda _: calls.append("current owner new_package is active"),
                     _invalidate_stale_handler=lambda _: False,
                     build_tool_package_map=lambda: calls.append("refresh mapping"))
    extracted("backend/ibl/tool_loader.py", {"load_tool_handler"}, namespace)
    returned = namespace["load_tool_handler"]("tool")
    return {"returned_package": returned.package, "calls": calls,
            "scope": "Current function's cached branch with synthetic ownership change; no live package modified."}


def member_implicit_default():
    state = {"version": 1, "revision": 10, "active": {"pkg": True}}
    writes, resets = [], []
    authority = object()
    namespace = dict(copy=copy, Path=Path, MEMBER_PROFILE="member", HUMAN_AUTHORITY=authority,
                     LOCK=threading.RLock(), package_path=lambda _: Path("/synthetic/pkg"),
                     is_active=lambda _: state["active"]["pkg"],
                     read_state=lambda *args: copy.deepcopy(state),
                     write_state=lambda value: writes.append(value),
                     require_optional=lambda _: None, check_ready=lambda _: [],
                     inventory=lambda: {"packages": {}})
    extracted("backend/ibl/vocabulary_lifecycle.py", {"set_package_active"}, namespace)
    extracted("backend/datastore/vocabulary_state.py", {"profile_active_map"}, namespace)
    before = namespace["profile_active_map"]("member")["pkg"]
    result = namespace["set_package_active"]("pkg", False, authority=authority, profile="member")
    after = namespace["profile_active_map"]("member")["pkg"]
    return {"before_member_active": before, "reported_result": result,
            "after_member_active": after, "writes": writes}


if __name__ == "__main__":
    paths = ["backend/ibl/vocabulary_lifecycle.py", "backend/ibl/tool_loader.py",
             "backend/surface/api_ibl.py", "mcp_server.py", "backend/base/program_runtime.py",
             "backend/datastore/vocabulary_state.py", "backend/test_surface_param_parity.py"]
    result = {"head": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip(),
              "source_sha256": {p: hashlib.sha256((ROOT / p).read_bytes()).hexdigest() for p in paths},
              "activation": [activation("owner"), activation("member")],
              "member_implicit_default": member_implicit_default(),
              "loader_fast_path": loader_fast_path(),
              "limitations": "Extracted real function bodies with in-memory stubs. Not full integration, pytest, real filesystem atomicity or concurrency validation."}
    print(json.dumps(result, ensure_ascii=False, indent=2))
