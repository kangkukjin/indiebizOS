"""선언 반환 계약 ↔ 실측 대조(자가점검 §1B-2) — 31ea17f0 의 손 발견을 기계가 다시 찾는가.

31ea17f0 이전의 수집관용구 계약은 result: Record(칸 없음)였다. 실제로는 {items, count}를 돌려주고,
그 Record 가 본문에서찾기의 반환형이 되어 행 자리에서 정상 조합이 거절됐다. 아래 OLD_CONTRACT 는
당시 판정관용구의 계약이다. 현재 수집관용구에 적용하여 같은 일반 오류를 재현한다.
"""
import boot_paths  # noqa: F401
import copy
import json
import subprocess
from pathlib import Path

import pytest
import yaml

import ibl_dependencies
from ibl_contract_drift import collect, compare, describe, healthy, summarize
from ibl_v2_adapters import load_registry
from ibl_v2_compile import compile_program
from ibl_v2_runtime import Runtime
from ibl_v2_types import declared
from test_function_support import current_source

ROOT = Path(__file__).resolve().parents[1]
OLD_CONTRACT = {
    "version": 1, "adapter": {"protocol": "registered-json/1"}, "effects": ["pure"],
    "params": {"op": "Text", "mode": "Text", "source": "Unknown", "origin": "Unknown", "question": "Text",
               "limit": "Number", "context": "Number", "prepared": "Record", "judged": "Record",
               "selection": "Record", "result": "Record", "results": "List<Record>", "keep": "List<Text>",
               "pattern": "Text"},
    "required": ["op"], "enums": {"op": ["urls", "prepare", "select", "finish", "match", "collect"]},
    "result": "Record",
}


def _scripts():
    return yaml.safe_load((ROOT / "data/scripts/registry.yaml").read_text())


def _samples():
    return json.loads((ROOT / "data/ibl_contract_samples.json").read_text())


def _sample_count():
    samples = _samples()
    return sum(len(cases) for group in ("scripts", "idioms")
               for cases in samples[group].values())


def _collect(scripts, run=None):
    registry = load_registry(str(ROOT))
    # 운영 점검은 compile_current(현행 관용구 원장)를 쓴다. 사본에는 원장이 없으므로 같은 저장 정의를 넣는다.
    definitions = {"본문에서찾기": current_source("본문에서찾기")}
    return collect(_samples(), scripts, lambda code: compile_program(code, registry, definitions=definitions),
                   run or (lambda plan: Runtime(plan).run()))


@pytest.fixture
def old_contract(monkeypatch):
    """검사기와 실행 경계가 읽는 등록부를 31ea17f0 이전 계약으로 바꾼다(파일은 그대로)."""
    scripts = _scripts()
    scripts["수집관용구"] = {**scripts["수집관용구"], "callable_contract": copy.deepcopy(OLD_CONTRACT)}
    monkeypatch.setattr(ibl_dependencies, "_script_registry", lambda path: scripts)
    return scripts


def test_pre_31ea17f0_contract_is_detected_as_under_declared(old_contract):
    rows = {r["target"]: r for r in _collect(old_contract)}
    judged = {k: v for k, v in rows.items() if k.startswith("script:수집관용구")}
    assert len(judged) == 3, rows
    for target, row in judged.items():
        assert row["verdict"] == "under_declared" and row["paths"] == ["$"], (target, row)
        assert row["declared"] == "Record" and "items: List<" in row["actual"], row
    # 관용구는 스크립트 계약을 물려받는다 — 사용자가 부딪힌 자리도 같은 판정으로 잡힌다.
    assert rows["fn:본문에서찾기"]["verdict"] == "under_declared", rows["fn:본문에서찾기"]
    summary = summarize(list(rows.values()))
    assert not healthy(summary) and len(summary["drift"]) == 4
    assert "어긋남 4" in describe(summary) and "under_declared" in describe(summary)


def test_current_contracts_compare_without_alarm():
    rows = _collect(_scripts())
    compared = [r for r in rows if r["verdict"] not in ("not_comparable", "no_sample")]
    required = {
        "script:수집관용구#urls", "script:수집관용구#match",
        "script:수집관용구#collect", "fn:본문에서찾기"}
    assert required <= {r["target"] for r in compared}
    assert len(compared) == _sample_count()  # every installed pure sample was run
    assert not any(r["verdict"] == "no_sample" for r in rows)
    assert all(r["verdict"] == "ok" for r in compared), compared
    summary = summarize(rows)
    assert healthy(summary) and summary["compared"] == _sample_count() and summary["drift"] == []


def test_side_effect_and_external_scripts_are_never_run_but_counted():
    scripts = _scripts()
    executed = []

    def run(plan):
        executed.append(str(plan.effects))
        return Runtime(plan).run()

    rows = _collect(scripts, run)
    contracted = {sid: e["callable_contract"] for sid, e in scripts.items()
                  if isinstance(e, dict) and e.get("callable_contract")}
    impure = {sid for sid, c in contracted.items() if set(c.get("effects") or ["unknown"]) != {"pure"}}
    skipped = {r["target"]: r["reason"] for r in rows if r["verdict"] == "not_comparable"}
    assert set(skipped) == {f"script:{sid}" for sid in impure} and len(impure) >= 10
    assert "script:의약품허가조회" in skipped and "read_external" in skipped["script:의약품허가조회"]
    assert all(e == "{'pure'}" for e in executed) and len(executed) == _sample_count()
    message = describe(summarize(rows))
    assert f"대조 불가 {len(impure)}" in message and "실행하지 않음" in message


def test_pure_script_without_sample_is_reported_not_silently_green():
    scripts = _scripts()
    rows = collect({"scripts": {}, "idioms": {}}, scripts, lambda code: pytest.fail(code),
                   lambda plan: pytest.fail("run"))
    gap = [r for r in rows if r["verdict"] == "no_sample"]
    pure = {f"script:{sid}" for sid, entry in scripts.items()
            if (contract := entry.get("callable_contract"))
            and set(contract.get("effects") or ["unknown"]) == {"pure"}}
    assert "script:수집관용구" in pure
    assert {r["target"] for r in gap} == pure and len(gap) == len(pure)
    summary = summarize(rows)
    assert summary["compared"] == 0 and not healthy(summary)


@pytest.mark.parametrize("spec,value,verdict,paths", [
    ({"items": "List<Record>", "count": "Number"}, {"items": []}, "over_declared", ["$.count"]),
    ({"plan": {"source": {"items": "List<Record>"}}}, {"plan": {"source": {}}}, "over_declared", ["$.plan.source.items"]),
    ("List<Record>", {"a": 1}, "type_mismatch", []),
    ({"count": "Number"}, {"count": "3"}, "type_mismatch", []),
    ({"plan": "Record"}, {"plan": {"items": [{"a": 1}]}}, "under_declared", ["$.plan"]),
    ("Unknown", {"items": [{"a": 1}]}, "ok", []),
    ({"items": "List<Record>"}, {"items": [], "extra": [1]}, "ok", []),
])
def test_compare_uses_checker_type_rules(spec, value, verdict, paths):
    row = compare(declared(spec), value)
    assert row["verdict"] == verdict and row["paths"] == paths, row


class _Done:
    def __init__(self, stdout):
        self.stdout, self.stderr, self.returncode = stdout, "", 0


@pytest.mark.parametrize("broken", [True, False])
def test_drift_reaches_ledger_and_results_projection(monkeypatch, tmp_path, broken, request):
    import pulse_db
    import world_pulse_health as health
    from routing_system import _cap_self_check_results
    if broken:
        request.getfixturevalue("old_contract")
    summary = summarize(_collect(ibl_dependencies._script_registry(None) if broken else _scripts()))
    marker = {"static_ok": True, "currency": {"green": 1, "yellow": 0, "red": 0, "reds": []},
              "golden_pipes": {"passed": 1, "total": 1, "fails": []}, "operators": {"passed": 1, "total": 1},
              "contract_drift": summary}
    monkeypatch.setattr(subprocess, "run", lambda *a, **k: _Done(
        "@@HEALTH_JSON@@ " + json.dumps(marker, ensure_ascii=False) + "\n"
        if str(a[0][1]).endswith("ibl_health_check.py") else ""))
    row = {ev["action"]: ev for ev in health.run_ibl_health_check()}["contract_drift"]
    assert row["success"] is (not broken)
    assert ("어긋남 4" in row["error_message"]) is broken and "대조 불가" in row["error_message"]

    monkeypatch.setattr(pulse_db, "CONSCIOUSNESS_DB_PATH", tmp_path / "world_pulse.db")
    health.save_self_check(row)
    items = _cap_self_check_results({"limit": 5})["items"]
    found = [i for i in items if i["title"] == "__ibl_health__:contract_drift"]
    assert len(found) == 1 and found[0]["success"] is (not broken)
    assert found[0]["quality"] == ("contract_drift" if broken else "ok")
    assert f"대조 {_sample_count()}" in found[0]["error"]


def test_health_script_section_runs_and_reports(monkeypatch):
    monkeypatch.syspath_prepend(str(ROOT / "scripts"))
    monkeypatch.chdir(ROOT)
    import importlib
    module = importlib.import_module("ibl_health_check")
    out = module.run_contract_drift()
    # 사본에는 관용구 원장이 없어 fn 표본은 check_failed 로 보고된다 — 숨지 않고 오류로 센다.
    assert "error" not in out, out
    verdicts = {r["target"]: r["verdict"] for r in out["rows"]}
    assert verdicts["script:수집관용구#match"] == "ok"
    assert verdicts["fn:본문에서찾기"] in ("ok", "check_failed")
    assert module._drift_line(out).startswith("대조 ")


if __name__ == "__main__":
    import sys
    raise SystemExit(pytest.main([__file__, *sys.argv[1:]]))
