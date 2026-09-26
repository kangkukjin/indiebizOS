"""판본 2 증분 실행(2026-09-26): 고친 프로그램의 읽기 영수증 재사용 · inputs 참조 · 관측 반환 필드 경고.

파이썬 REPL 이 값을 들고 함수 하나만 고쳐 다시 부르는 일을 IBL 이 숨은 상태 없이 하게 하는 세 계약이다.
정본: docs/IBL_INCREMENTAL_EXECUTION_2026_09_26.md
"""
import json
import boot_paths  # noqa: F401
import pytest
from ibl_v2_ir import Fault, pack, unpack
from ibl_v2_compile import compile_program
from ibl_v2_runtime import Runtime
from ibl_v2_adapters import Adapter
from ibl_run_journal import Journal, reusable_receipts, inspect_run


def adapter(fn, params=None, result="Unknown", effects=None, implementation="impl-1"):
    return Adapter({"version": 1, "params": params or {}, "result": result,
                    "effects": effects or ["read_external"], "implementation_fingerprint": implementation}, fn)


def registry(calls, implementation="impl-1"):
    return {"t:read": adapter(lambda rt, a: calls.append(("read", a["n"])) or {"n": a["n"], "rows": [a["n"]]},
                              {"n": "Number"}, "Record", implementation=implementation),
            "t:write": adapter(lambda rt, a: calls.append(("write", a["n"])) or {"ok": True},
                               {"n": "Number"}, "Record", ["write_external"])}


def test_edited_program_reuses_read_receipts_and_reruns_writes_and_changed_args(tmp_path):
    calls = []
    first = compile_program("$a = [t:read]{n:1}\n$w = [t:write]{n:1}\nreturn $a", registry(calls))
    with Journal(tmp_path, "first") as journal:
        run_id = journal.run_id
        out = Runtime(first, journal=journal).run()
    assert out["success"] and calls == [("read", 1), ("write", 1)]
    reusable = reusable_receipts(tmp_path, run_id)
    assert len(reusable) == 2 and all(r["action"] in ("t:read", "t:write") for r in reusable.values())

    edited = compile_program("$a = [t:read]{n:1}\n$w = [t:write]{n:1}\n$b = [t:read]{n:2}\nreturn {a:$a, b:$b}",
                             registry(calls))
    calls.clear()
    with Journal(tmp_path, "second") as journal:
        second_id = journal.run_id
        out = Runtime(edited, journal=journal, reusable=reusable, reuse_run=run_id).run()
    assert out["success"]
    assert calls == [("write", 1), ("read", 2)]  # 읽기 n:1 은 재사용, 쓰기·새 인자는 실행
    assert out["reuse"] == {"run_id": run_id, "reused_calls": 1, "candidates": 2}
    reused = [e for e in out["evidence"] if e["kind"] == "receipt_reused"]
    assert len(reused) == 1 and reused[0]["source"] == "reuse" and reused[0]["run_id"] == run_id
    assert unpack(out["value_wire"]["data"]) == {"a": {"n": 1, "rows": [1]}, "b": {"n": 2, "rows": [2]}}
    # 재사용한 호출도 새 실행의 저널에 완료 영수증으로 남는다 — 그 실행을 다시 resume 할 수 있다
    state = inspect_run(tmp_path, second_id)
    assert state["calls"] == 3 and state["uncertain_calls"] == 0 and state["status"] == "completed"
    calls.clear()
    with Journal(tmp_path, "second", resume={"run_id": second_id}) as journal:
        again = Runtime(edited, journal=journal).run()
    assert again["success"] and calls == []
    assert all(e["source"] == "journal" for e in again["evidence"] if e["kind"] == "receipt_reused")


def test_changed_implementation_failed_receipts_and_missing_runs_are_not_reused(tmp_path):
    calls = []
    plan = compile_program("return [t:read]{n:1}", registry(calls))
    with Journal(tmp_path, "a") as journal:
        run_id = journal.run_id
        Runtime(plan, journal=journal).run()
    changed = compile_program("return [t:read]{n:1}", registry(calls, implementation="impl-2"))
    calls.clear()
    out = Runtime(changed, reusable=reusable_receipts(tmp_path, run_id), reuse_run=run_id).run()
    assert out["success"] and calls == [("read", 1)] and out["reuse"]["reused_calls"] == 0

    failing = {"t:read": adapter(lambda rt, a: (_ for _ in ()).throw(Fault("TOOL", "down")), {"n": "Number"}, "Record")}
    failed_plan = compile_program("return [t:read]{n:7}", failing)
    with Journal(tmp_path, "f") as journal:
        failed_id = journal.run_id
        assert not Runtime(failed_plan, journal=journal).run()["success"]
    assert reusable_receipts(tmp_path, failed_id) == {}  # 실패 영수증은 후보가 아니다

    with pytest.raises(Fault) as missing:
        reusable_receipts(tmp_path, "f" * 32)
    assert missing.value.code == "REUSE_NOT_FOUND"
    with pytest.raises(Fault) as bad:
        reusable_receipts(tmp_path, "nope")
    assert bad.value.code == "REUSE_ARGUMENT"
    with Journal(tmp_path, "busy") as journal:
        with pytest.raises(Fault) as busy:
            reusable_receipts(tmp_path, journal.run_id)
        assert busy.value.code == "REUSE_BUSY"


def test_unknown_effect_vocabulary_reuses_by_side_effect_rule(tmp_path):
    """legacy 어휘(effects unknown)는 ibl_ops 부작용 규칙으로 op 단위 판정 — 읽기 op 재사용, 쓰기 op 재실행."""
    from ibl_ops import op_side_effect, resolve_op
    calls = []
    action_def = {"ops": {"values": {"list": "목록", "save": "저장"}, "side_effect": {"list": False, "save": True}, "default": "list"}}
    def reusable(args, ac=action_def):
        return not op_side_effect(ac, resolve_op(ac, args))
    contract = {"version": 1, "params": {"op": "Text", "n": "Number"}, "result": "Record", "effects": ["unknown"],
                "compatibility": "legacy-envelope/1", "adapter": {"protocol": "legacy-envelope", "value_path": ""},
                "implementation_fingerprint": "impl-1"}
    reg = {"t:legacy": Adapter(contract, lambda rt, a: calls.append((a["op"], a["n"])) or {"op": a["op"]}, None, None, reusable)}
    first = compile_program('$a = [t:legacy]{op:"list", n:1}\n$b = [t:legacy]{op:"save", n:1}\nreturn $a', reg)
    with Journal(tmp_path, "one") as journal:
        run_id = journal.run_id
        assert Runtime(first, journal=journal).run()["success"]
    calls.clear()
    edited = compile_program('$a = [t:legacy]{op:"list", n:1}\n$b = [t:legacy]{op:"save", n:1}\nreturn {a:$a, x:1}', reg)
    out = Runtime(edited, reusable=reusable_receipts(tmp_path, run_id), reuse_run=run_id).run()
    assert out["success"] and calls == [("save", 1)] and out["reuse"]["reused_calls"] == 1


def test_entry_rejects_bad_reuse_shape_and_reuse_with_resume():
    from ibl_v2_entry import handle_request
    bad = handle_request({"code": "#!ibl edition=2\nreturn 1", "reuse": {"run": "x"}})
    assert bad["ok"] is False and "REUSE_ARGUMENT" in json.dumps(bad)
    both = handle_request({"code": "#!ibl edition=2\nreturn 1", "reuse": {"run_id": "a" * 32}, "resume": {"run_id": "b" * 32}})
    assert both["ok"] is False and "REUSE_ARGUMENT" in json.dumps(both)


def test_input_refs_resolve_stored_values_without_copying(tmp_path, monkeypatch):
    import model_result_view as view
    from supervision_store import TurnStore
    store = TurnStore(tmp_path / "ev")
    monkeypatch.setattr(view, "evidence_store", lambda: store)
    rows = {"rows": [{"id": 1}, {"id": 2}]}
    v2 = store.evidence(json.dumps({"edition": 2, "value": rows, "value_wire": {"protocol": "ibl-value/1", "data": pack(rows)}}))
    legacy = store.evidence(json.dumps({"final_result": {"items": [{"a": 1}]}}))
    resolved, notes = view.resolve_input_refs({
        "x": {"$ref": v2["id"]}, "y": {"$ref": legacy["id"]},
        "z": {"$ref": v2["id"], "path": ["value", "rows", 1]}, "plain": 3})
    assert resolved == {"x": rows, "y": {"items": [{"a": 1}]}, "z": {"id": 2}, "plain": 3}
    assert [n["name"] for n in notes] == ["x", "y", "z"]
    assert notes[0]["path"] == ["value_wire"] and notes[1]["path"] == ["final_result"] and notes[2]["path"] == ["value", "rows", 1]
    # 참조가 없으면 손대지 않는다
    assert view.resolve_input_refs({"plain": {"k": 1}}) == ({"plain": {"k": 1}}, [])
    with pytest.raises(ValueError):
        view.resolve_input_refs({"x": {"$ref": v2["id"], "extra": 1}})
    with pytest.raises(ValueError):
        view.resolve_input_refs({"x": {"$ref": v2["id"], "path": ["nope"]}})
    with pytest.raises(ValueError):
        view.resolve_input_refs({"x": {"$ref": "bad-id"}})
    # 스필 참조 봉투도 푼다
    spill = tmp_path / "spill.json"
    spill.write_text(json.dumps({"items": [{"q": 1}]}), encoding="utf-8")
    resolved, notes = view.resolve_input_refs({"s": {"items": [], "ref": {"path": str(spill)}, "_spilled": True}})
    assert resolved == {"s": {"items": [{"q": 1}]}} and notes[0]["ref"] == str(spill)


def _legacy(name):
    # 실제 봉투에는 관측 밖 필드(pth)도 있다 — 경고는 컴파일 시 흔적과의 불일치일 뿐 실행을 막지 않는다
    body = {"path": "p", "bytes": 1, "pth": "x", "items": [{"title": "t", "url": "u"}], "count": 1}
    return Adapter({"version": 1, "params": {}, "result": "Record", "effects": ["unknown"],
                    "compatibility": "legacy-envelope/1",
                    "adapter": {"protocol": "legacy-envelope", "value_path": ""}}, lambda rt, a: dict(body))


def test_observed_return_fields_warn_outside_observation_but_never_reject(monkeypatch):
    import ibl_access
    import ibl_typecheck
    shapes = {"t:list": {"kind": "items", "keys": ["title", "url"]},
              "t:more": {"kind": "items", "keys": ["a"], "more": 3},
              "t:one": {"kind": "scalar", "keys": ["path", "bytes"]}}
    monkeypatch.setattr(ibl_access, "_return_shapes", lambda: shapes)
    monkeypatch.setattr(ibl_typecheck, "_action_def", lambda node, action: {})
    reg = {k: _legacy(k) for k in ("t:list", "t:more", "t:one")}

    plan = compile_program("$r = [t:list]{}\n$k = $r.count\nreturn $r.items >> [table:each]{ return {t:$it.title, u:$it.titel} }", reg)
    assert not plan.issues
    warns = [w for w in plan.preflight["warnings"] if w["code"] == "UNOBSERVED_FIELD"]
    assert [w["facts"]["field"] for w in warns] == ["titel"] and warns[0]["facts"]["observed"] == ["title", "url"]
    assert warns[0]["severity"] == "warning" and "location" in warns[0] and warns[0]["hint"]
    report = plan.report()
    assert report["ok"] and report["status"] in ("valid", "incomplete") and warns[0] in report["warnings"]
    assert "Record⟨관측: title·url⟩" in str(compile_program("$r = [t:list]{}\nreturn $r.items", reg).result_type)

    quiet = compile_program("$r = [t:more]{}\nreturn $r.items >> [table:each]{ return $it.zzz }", reg)
    assert not [w for w in quiet.preflight["warnings"] if w["code"] == "UNOBSERVED_FIELD"]  # 잘린 관측은 기권
    scalar = compile_program("$r = [t:one]{}\nreturn {p:$r.path, q:$r.pth}", reg)
    assert [w["facts"]["field"] for w in scalar.preflight["warnings"] if w["code"] == "UNOBSERVED_FIELD"] == ["pth"]
    safe = compile_program("$r = [t:one]{}\nreturn get($r, \"pth\", null)", reg)
    assert not [w for w in safe.preflight["warnings"] if w["code"] == "UNOBSERVED_FIELD"]
    # 실행 봉투에도 실린다(precheck_warnings) — 경고는 실행을 막지 않는다
    out = Runtime(scalar).run()
    assert out["success"] and [w["code"] for w in out["precheck_warnings"]] == ["UNOBSERVED_FIELD"]


def test_declared_items_contract_still_gets_observed_row_fields(monkeypatch):
    """실제 어휘(sense:search 등)는 result 를 {items: List<Record>} 로 선언한다 — 그 행 원소에도 관측 필드가 붙어야 한다."""
    import ibl_access
    import ibl_typecheck
    monkeypatch.setattr(ibl_access, "_return_shapes", lambda: {"t:decl": {"kind": "items", "keys": ["title", "url"]}})
    monkeypatch.setattr(ibl_typecheck, "_action_def", lambda node, action: {})
    declared = Adapter({"version": 1, "params": {"query": "Text"}, "result": {"items": "List<Record>", "count": "Number"},
                        "effects": ["read_external"], "adapter": {"protocol": "legacy-envelope", "value_path": ""}},
                       lambda rt, a: {"items": [{"title": "t", "url": "u", "titel": "x"}], "count": 1})  # 실제 값엔 관측 밖 필드도 있을 수 있다
    reg = {"t:decl": declared}
    plan = compile_program("$r = [t:decl]{query:\"x\"}\nreturn {n:$r.count, rows:$r.items >> [table:each] { return {a:$it.title, b:$it.titel} }}", reg)
    warns = [w for w in plan.preflight["warnings"] if w["code"] == "UNOBSERVED_FIELD"]
    assert [w["facts"]["field"] for w in warns] == ["titel"]
    assert not plan.issues and Runtime(plan).run()["success"]
    # 선언이 행 모양을 이미 말하면 관측을 덮지 않는다
    rowed = Adapter({**declared.contract, "result": {"items": {"$list": {"title": "Text"}}}}, declared.run)
    plan2 = compile_program("$r = [t:decl]{query:\"x\"}\nreturn $r.items >> [table:each] { return $it.titel }", {"t:decl": rowed})
    assert not [w for w in plan2.preflight["warnings"] if w["code"] == "UNOBSERVED_FIELD"]


def test_catalog_entry_is_the_single_resolution_rule(monkeypatch):
    import ibl_access
    import ibl_typecheck
    shapes = {"t:x": {"kind": "items", "keys": ["a"]}, "t:x#list": {"kind": "items", "keys": ["b"]},
              "t:x@source=z": {"kind": "items", "keys": ["c"]}, "t:s": {"kind": "scalar", "keys": ["k"]}}
    monkeypatch.setattr(ibl_access, "_return_shapes", lambda: shapes)
    monkeypatch.setattr(ibl_typecheck, "_action_def", lambda node, action: {})
    assert ibl_typecheck.catalog_entry("t", "x", {})["keys"] == ["a"]
    assert ibl_typecheck.catalog_entry("t", "x", {"op": "list"})["keys"] == ["b"]
    assert ibl_typecheck.catalog_entry("t", "x", {"source": "z"})["keys"] == ["c"]
    assert ibl_typecheck.catalog_entry("t", "x", {"op": "$dyn"})["keys"] == ["a"]
    assert ibl_typecheck.catalog_entry("t", "s", {}) is None  # 판본 1 검사기는 ⟨키⟩를 열로 쓰지 않는다
    assert ibl_typecheck.catalog_entry("t", "s", {}, kinds=("scalar",))["keys"] == ["k"]
    assert ibl_typecheck._catalog_cols("t", "x", {"op": "list"}) == ["b"]


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__]))
