"""A check shares metadata; later checks and invocations observe fresh assets."""
import boot_paths  # noqa: F401
from dataclasses import replace
from pathlib import Path

import pytest

import ibl_dependencies as dependencies
from ibl_v2_adapters import Adapter
from ibl_v2_compile import compile_program
from ibl_v2_runtime import Runtime


@pytest.fixture
def scripts(tmp_path, monkeypatch):
    import python_environment_lock
    import runtime_utils
    import thread_context

    root = tmp_path / "data/scripts"
    root.mkdir(parents=True)
    (root / "registry.yaml").write_text(
        "one:\n  file: one.py\n  interpreter: python\n"
        "two:\n  file: two.py\n  interpreter: python\n"
    )
    (root / "one.py").write_text("result = 1\n")
    (root / "two.py").write_text("result = 2\n")
    state = {"environment": "before", "fingerprints": 0, "executed": 0}

    def fingerprint(path):
        assert Path(path) == root
        state["fingerprints"] += 1
        return state["environment"]

    monkeypatch.setattr(runtime_utils, "get_base_path", lambda: tmp_path)
    monkeypatch.setattr(thread_context, "get_repair_workspace", lambda **kw: None)
    monkeypatch.setattr(python_environment_lock, "fingerprint", fingerprint)

    def run(rt, args):
        state["executed"] += 1
        return 1

    registry = {"fixture:script": Adapter(
        {"version": 1, "params": {"id": "Text"}, "result": "Number",
         "effects": ["read_external"]}, run, dependency=dependencies.script_dependency)}
    source = (
        '$a=[fixture:script]{id:"one"}\n'
        '$b=[fixture:script]{id:"two"}\n'
        'return [fixture:script]{id:"one"}'
    )
    return root, registry, source, state


def test_check_reads_environment_once_but_each_invocation_rechecks(scripts, monkeypatch):
    _, registry, source, state = scripts
    reads = []
    load = dependencies.yaml.safe_load

    def read_registry(text):
        reads.append(text)
        return load(text)

    monkeypatch.setattr(dependencies.yaml, "safe_load", read_registry)
    plan = compile_program(source, registry)
    assert not plan.issues
    assert state["fingerprints"] == 1
    assert len(reads) == 1
    result = Runtime(plan).run()
    assert result["success"] and result["value"] == 1, result
    assert state["executed"] == 3
    assert state["fingerprints"] == 4
    assert len(reads) == 4


@pytest.mark.parametrize("change", ["source", "registry", "environment", "new_import"])
def test_next_check_and_old_plan_detect_changes(scripts, change):
    root, registry, source, state = scripts
    if change == "new_import":
        (root / "one.py").write_text("import sibling\nresult = 1\n")
    before = compile_program(source, registry)
    if change == "source":
        (root / "one.py").write_text("result = 3\n")
    elif change == "registry":
        path = root / "registry.yaml"
        path.write_text(path.read_text().replace("file: one.py", "file: two.py"))
    elif change == "environment":
        state["environment"] = "after"
    else:
        (root / "sibling.py").write_text("value = 1\n")
    after = compile_program(source, registry)
    assert before.dependencies["calls"] != after.dependencies["calls"]
    result = Runtime(before).run()
    assert not result["success"]
    assert result["diagnostic"]["code"] == "DEFINITION_CHANGED", result
    assert state["executed"] == 0


def test_failed_check_does_not_leave_dependency_cache(scripts):
    _, registry, source, state = scripts
    original = registry["fixture:script"].dependency

    def broken(args):
        original(args)
        raise RuntimeError("metadata unavailable")

    registry["fixture:script"] = replace(registry["fixture:script"], dependency=broken)
    with pytest.raises(RuntimeError, match="metadata unavailable"):
        compile_program(source, registry)
    state["environment"] = "after"
    assert dependencies.script_snapshot({"id": "one"})["environment"] == "after"
    assert state["fingerprints"] == 2


def test_specialization_observes_registry_change_between_checks(scripts):
    import json

    root, registry, _, _ = scripts
    entry = {
        "file": "one.py", "interpreter": "python",
        "callable_contract": {
            "version": 1, "params": {}, "required": [],
            "result": "Number", "effects": ["pure"],
            "adapter": {"protocol": "registered-json/1"},
        },
    }
    path = root / "registry.yaml"
    path.write_text(json.dumps({"one": entry}))
    registry["fixture:script"] = replace(
        registry["fixture:script"], specialize=dependencies.script_contract)
    source = 'return [fixture:script]{id:"one"} + 1'
    before = compile_program(source, registry)
    assert not before.issues
    entry["callable_contract"]["result"] = "Record"
    path.write_text(json.dumps({"one": entry}))
    after = compile_program(source, registry)
    assert any(issue["code"] == "ARITHMETIC" for issue in after.issues)


def test_call_sites_do_not_share_mutable_snapshot_evidence(scripts):
    _, registry, source, _ = scripts
    plan = compile_program(source, registry)
    snapshots = list(plan.dependencies["calls"].values())
    assert snapshots[0] == snapshots[2]
    snapshots[0]["files"].clear()
    assert snapshots[2]["files"]


def test_register_then_first_run_binds_new_definition_at_invocation(scripts):
    import json
    root, registry, _, state = scripts
    original = registry["fixture:script"]
    def run(rt, args):
        if args.get("op") == "register":
            entries = dependencies.yaml.safe_load((root / "registry.yaml").read_text())
            entries[args["id"]] = {"file": "one.py", "interpreter": "python"}
            (root / "registry.yaml").write_text(json.dumps(entries))
            return 0
        assert rt.local.invocation_dependency["scope"] == "script-closure"
        state["executed"] += 1
        return 1
    registry["fixture:script"] = replace(original, run=run,
        contract={"version": 1, "params": {"id": "Text", "op": "Text"},
                  "required": ["id"], "result": "Number", "effects": ["write_external"]},
        invocation_dependency=dependencies.script_invocation_snapshot)
    plan = compile_program('$r=[fixture:script]{op:"register",id:"new"}\n'
                           'return [fixture:script]{id:"new"}', registry)
    assert not plan.issues, plan.issues
    result = Runtime(plan).run()
    assert result["success"] and result["value"] == 1, result
    assert state["executed"] == 1
    assert plan.dependencies["calls"][list(plan.dependencies["calls"])[-1]]["binding"] == "invocation"


def test_unbound_dependency_requires_invocation_provider(scripts):
    _, registry, _, state = scripts
    plan = compile_program('[fixture:script]{id:"not_yet_registered"}', registry)
    result = Runtime(plan).run()
    assert result["diagnostic"]["code"] == "DEPENDENCY_CONTRACT"
    assert state["executed"] == 0


def test_public_script_register_then_run_uses_real_runner(scripts, monkeypatch):
    import runtime_utils
    from ibl_v2_adapters import load_registry
    from system_tools import load_tool_handler
    root, _, _, _ = scripts
    monkeypatch.setattr(runtime_utils, "get_base_path", lambda: Path(__file__).resolve().parents[1])
    snapshot = dependencies.script_snapshot
    monkeypatch.setattr(dependencies, "script_snapshot", lambda args, **kw: snapshot(args, root, **kw))
    handler = load_tool_handler("script_op")
    ops = handler._load_sibling("script_ops")
    monkeypatch.setattr(ops, "_SCRIPT_DIR", root)
    monkeypatch.setattr(ops, "_REGISTRY", root / "registry.yaml")
    monkeypatch.setitem(handler._SIBLING_MODS, "script_ops", ops)
    script = root / "fresh.py"
    script.write_text('import json,sys; print(json.dumps({"answer":json.load(sys.stdin)["n"]*2}))')
    registry = load_registry(str(root.parent.parent))
    source = ('[self:script]{op:"register",id:"fresh",path:$path}\n'
              'return [self:script]{id:"fresh",args:{n:7}}')
    plan = compile_program(source, registry, {"path": str(script)})
    assert not plan.issues, plan.report()
    result = Runtime(plan, {"path": str(script)}).run()
    assert result["success"] and result["value"] == {"answer": 14}, result
    assert dependencies.yaml.safe_load((root / "registry.yaml").read_text())["fresh"]["file"] == "fresh.py"


@pytest.mark.parametrize("changed", [False, True])
def test_dynamic_script_reuse_checks_invocation_assets(scripts, tmp_path, changed):
    from ibl_run_journal import Journal, reusable_receipts
    root, registry, _, state = scripts
    registry["fixture:script"] = replace(registry["fixture:script"],
        invocation_dependency=dependencies.script_invocation_snapshot)
    inputs = {"name": "one"}
    plan = compile_program('return [fixture:script]{id:$name}', registry, inputs)
    assert not plan.issues, plan.report()
    assert next(iter(plan.dependencies["calls"].values()))["binding"] == "invocation"
    with Journal(tmp_path / "journal", "first") as journal:
        first = Runtime(plan, inputs, journal=journal).run()
        run_id = journal.run_id
    assert first["success"], first
    if changed:
        (root / "one.py").write_text("result = 3\n")
    result = Runtime(plan, inputs, reusable=reusable_receipts(tmp_path / "journal", run_id),
                     reuse_run=run_id).run()
    assert result["success"], result
    assert state["executed"] == (2 if changed else 1)
    assert result["reuse"]["reused_calls"] == int(not changed)


if __name__ == "__main__":
    import sys
    raise SystemExit(pytest.main([__file__] + sys.argv[1:]))
