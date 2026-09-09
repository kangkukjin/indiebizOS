"""Execute one generated program in a fresh fixture using the current IBL engine."""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
import boot_paths  # noqa: E402,F401

import contextlib
import io
import json
import tempfile
import time
from unittest.mock import patch
from idiom_experiment_worker import load
from idiom_exposure_cases import setup, judge


def run(req):
    import ibl_engine, ibl_usage_db, workflow_engine, ibl_typecheck, episode_logger, write_ledger
    import oneshot_facade, consciousness_agent
    from common import spill
    from ibl_parser import parse_with_vars
    from ibl_control_blocks import _execute_fn
    from ibl_executors import _execute_table_each
    from tool_context import ToolContext
    from thread_context import actor_context

    entries = {e["alias"]: e for e in req["registry"]}
    dataops = load(
        "_exposure_dataops",
        ROOT / "data/packages/installed/tools/data-ops/handler.py",
    )
    fs = load(
        "_exposure_fs",
        ROOT / "data/packages/installed/tools/system_essentials/handler.py",
    )
    ledger = load(
        "_exposure_ledger",
        ROOT / "data/packages/installed/tools/system_essentials/ledger_ops.py",
    )
    observed = {"leaf_calls": [], "fn_calls": []}

    class DB:
        def find_phrase_by_alias(self, name):
            return entries.get(name)

        def update_success_by_code(self, *a, **k):
            pass

        def phrase_aliases(self, *a, **k):
            return list(entries)

    def forbidden_ai(*a, **k):
        raise ValueError("Only deterministic fixture actions are permitted")

    with tempfile.TemporaryDirectory(
        prefix="ibl_exposure_"
    ) as tmp, contextlib.ExitStack() as stack:
        root = Path(tmp).resolve()
        setup(root, req["seed"])
        initial = {
            str(p.relative_to(root)): p.read_bytes()
            for p in root.rglob("*")
            if p.is_file()
        }

        def path_of(raw):
            p = Path(str(raw))
            p = (p if p.is_absolute() else root / p).resolve()
            if not p.is_relative_to(root):
                raise ValueError("Path outside isolated fixture")
            return p

        stack.enter_context(patch.object(ibl_usage_db, "IBLUsageDB", DB))
        stack.enter_context(
            patch.object(workflow_engine, "get_workflow", lambda name: None)
        )
        stack.enter_context(
            patch.object(
                ibl_typecheck,
                "FN_CODE_SOURCES",
                [lambda name: entries.get(name, {}).get("ibl_code")],
            )
        )
        stack.enter_context(
            patch.object(spill, "_root", lambda: str(root / "_spill"))
        )
        stack.enter_context(
            patch.object(write_ledger, "_LEDGER_PATH", root / "_writes.jsonl")
        )
        stack.enter_context(
            patch.object(
                episode_logger, "record_trajectory_event", lambda *a, **k: None
            )
        )
        stack.enter_context(
            patch.object(oneshot_facade, "execution_oneshot", forbidden_ai)
        )
        stack.enter_context(
            patch.object(consciousness_agent, "oneshot_ai_call", forbidden_ai)
        )
        stack.enter_context(patch.object(ledger, "_target_path", path_of))
        original = ibl_engine._execute_ibl_impl
        public_execute = ibl_engine.execute_ibl

        def leaf(ti, project, agent_id=None):
            n, a = ti.get("_node"), ti.get("action")
            p = dict(ti.get("params") or {})
            if p.get("criteria"):
                return {
                    "success": False,
                    "error": "AI criteria are not available in this deterministic experiment",
                }
            if n == "fn":
                observed["fn_calls"].append(a)
                return _execute_fn(ti, project, agent_id)
            if ti.get("_def") or any(
                ti.get(k)
                for k in [
                    "_condition",
                    "_case",
                    "_try",
                    "_repeat",
                    "_var_emit",
                    "_assign",
                    "_parallel",
                    "_fallback",
                ]
            ):
                return original(ti, project, agent_id)
            observed["leaf_calls"].append(f"{n}:{a}")
            if n == "table" and a == "each":
                p["_depth"] = ti.get("_depth", 0)
                return _execute_table_each(p, project, agent_id=agent_id)
            if n == "table" and "data_" + str(a) in dataops._DISPATCH:
                return dataops.execute(p, ToolContext(project, "data_" + a))
            mapped = {
                "read": "read_op",
                "file_find": "glob_files",
                "grep": "grep_files",
                "edit": "edit_file",
                "write": "write_file",
                "list": "list_directory",
            }
            if n == "self" and (a in mapped or a == "ledger"):
                try:
                    for key in (
                        "path",
                        "root_path",
                        "file_path",
                        "directory",
                        "items_file",
                        "files_from",
                        "source",
                        "destination",
                    ):
                        if isinstance(p.get(key), str):
                            path_of(p[key])
                    if a == "ledger":
                        func = getattr(
                            ledger, "op_" + str(p.get("op", "select")), None
                        )
                        return (
                            func(p)
                            if func
                            else {
                                "success": False,
                                "error": "Unknown ledger operation",
                            }
                        )
                    return fs.execute(
                        p,
                        ToolContext(
                            project, mapped[a], agent_id="exposure-fixture"
                        ),
                    )
                except ValueError as exc:
                    return {"success": False, "error": str(exc)}
            return {
                "success": False,
                "error": f"Unavailable fixture action {n}:{a}",
            }

        def public(ti, project, agent_id=None):
            if (ti.get("params") or {}).get("criteria"):
                return {
                    "success": False,
                    "error": "AI criteria are not available in this deterministic experiment",
                }
            return public_execute(ti, project, agent_id)

        stack.enter_context(
            patch.object(ibl_engine, "_execute_ibl_impl", leaf)
        )
        stack.enter_context(patch.object(ibl_engine, "execute_ibl", public))
        started = time.perf_counter()
        checked = {}
        try:
            steps, variables = parse_with_vars(req["code"])
            checked = ibl_typecheck.typecheck(steps, variables)
            if checked.get("abstained"):
                raise ValueError(
                    "Type checker abstained: " + checked["abstained"]
                )
            if not checked["ok"]:
                result = {
                    "success": False,
                    "error": json.dumps(checked["issues"], ensure_ascii=False),
                }
            else:
                with actor_context(agent_id="exposure-fixture", origin="test"):
                    result = workflow_engine.execute_pipeline(steps, str(root))
            try:
                ok, verdict = judge(
                    req["case_id"], result, root, observed, initial
                )
            except (
                OSError,
                ValueError,
                TypeError,
                KeyError,
                AttributeError,
            ) as exc:
                ok, verdict = (
                    False,
                    f"Expected artifact missing or invalid: {type(exc).__name__}: {exc}",
                )
        except Exception as exc:
            result = {
                "success": False,
                "error": f"{type(exc).__name__}: {exc}",
            }
            ok = False
            verdict = result["error"]
        artifacts = {
            str(p.relative_to(root)): p.read_text()
            for p in (root / "outputs").rglob("*")
            if p.is_file()
        }
        return {
            "quality_ok": bool(ok),
            "verdict": verdict,
            "result": result,
            "observed": observed,
            "runtime_ms": round((time.perf_counter() - started) * 1000, 3),
            "typecheck": checked,
            "artifacts": artifacts,
        }


if __name__ == "__main__":
    req = json.loads(sys.stdin.read())
    with contextlib.redirect_stdout(io.StringIO()):
        out = run(req)
    print(json.dumps(out, ensure_ascii=False))
