"""노출 실험에서 발견한 실제 저장·교재 누락·불필요한 수리의 회귀."""

import json
import sqlite3
import sys
from pathlib import Path

import pytest
import boot_paths  # noqa: F401

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from idiom_exposure_cases import GOLD, judge, setup, returned_body
from idiom_exposure_worker import run

EVIDENCE = ROOT / "docs/experiments/idiom_exposure_2026_09_09"
REGISTRY = json.loads((EVIDENCE / "registry.json").read_text())
CALL = '[fn:최신범위읽기]{폴더:"drafts",패턴:"*.md",시작줄:11,줄수:12}'
QUEUE = (
    '[self:read]{path:"queue.json"} '
    ">> [table:filter]{where:\"state == 'open' and priority >= 3\"} "
    '>> [table:sort]{by:"id"} '
    '>> [self:write]{path:"outputs/pending.json",format:"json"}'
)


def execute(code, case="embedded_latest", seed=2026090901):
    return run(dict(code=code, case_id=case, seed=seed, registry=REGISTRY))


@pytest.mark.parametrize(
    "program",
    [
        CALL + ' >> [self:write]{path:"outputs/excerpt.txt"}',
        "$part = "
        + CALL
        + '\n$part >> [self:write]{path:"outputs/excerpt.txt"}',
        "$part = "
        + CALL
        + '\n[self:write]{path:"outputs/excerpt.txt",content:"$part"}',
        "$part = "
        + CALL
        + '\n[self:write]{path:"outputs/excerpt.txt",content:$part.text}',
        "$part = "
        + CALL
        + '\n[self:write]{path:"outputs/excerpt.txt",content:$part.final_result}',
        "[def: 감싸기]{$return = " + CALL + "}\n"
        '[fn:감싸기]{} >> [self:write]{path:"outputs/excerpt.txt"}',
    ],
)
def test_named_scalar_reaches_actual_file_without_execution_record(program):
    out = execute(program + "\n" + QUEUE)
    assert out["runtime_ok"], out["verdict"]
    assert out["quality_ok"], out["verdict"]
    text = out["artifacts"]["outputs/excerpt.txt"]
    assert len(text.splitlines()) == 13  # 읽기 범위 헤더 + 본문 12줄
    assert '"results"' not in text and '"fn"' not in text
    assert out["observed"]["fn_calls"]  # 펼친 정답으로 우회하지 않았다
    fn_steps = [r for r in out["result"]["results"] if r.get("node") == "fn"]
    assert fn_steps and json.loads(fn_steps[0]["result"])["fn_source"]


@pytest.mark.parametrize(
    "value",
    [
        "본문\n",
        "",
        {"items": []},
        {"items": [{"id": 1}]},
        [1, 2],
        {"success": True, "path": "saved"},
    ],
)
def test_return_projection_keeps_values_and_does_not_mutate_diagnostics(value):
    from common.currency import fn_result_payload
    from workflow_binding import _to_prev_currency

    env = dict(
        success=True,
        _fn_result=True,
        final_result=value,
        results=[{"step": 1}],
    )
    before = json.dumps(env)
    assert fn_result_payload(env) == (True, value)
    actual = _to_prev_currency(env)
    assert (actual if isinstance(value, str) else json.loads(actual)) == value
    assert json.dumps(env) == before
    failed = dict(env, success=False, error="실패", traceback={"frames": []})
    assert fn_result_payload(failed) == (False, failed)
    business = dict(
        fn="업무 필드", fn_source="idiom", final_result=value, success=True
    )
    assert fn_result_payload(business) == (False, business)


def test_saved_workflow_called_as_function_uses_same_value_gate(monkeypatch):
    import workflow_engine
    from ibl_control_blocks import _execute_fn
    from workflow_binding import _to_prev_currency

    monkeypatch.setattr(
        workflow_engine, "get_workflow", lambda name: {"name": name}
    )
    monkeypatch.setattr(
        workflow_engine,
        "execute_workflow",
        lambda *a, **k: {
            "success": True,
            "final_result": "저장 함수 본문",
            "results": [{"step": 1}],
        },
    )
    out = _execute_fn({"action": "저장된함수", "params": {}}, ".", "test")
    assert _to_prev_currency(out) == "저장 함수 본문"
    assert out["fn_source"] == "workflow" and out["results"]


def test_current_block_body_keeps_teaching_in_actual_introduction(
    tmp_path, monkeypatch
):
    import ibl_access
    import runtime_utils

    catalog = json.loads((ROOT / "data/idioms/curated.json").read_text())
    lesson = next(e for e in catalog["idioms"] if e["name"] == "위치마다읽기")
    # 불변식은 교재 몸 == **운영 원장의 현재 몸**(다르면 소개기가 교재를 버린다). v1 스냅샷은 09-09 서명 개정
    # (파이프형→자족형, 지렛대 1) 이전의 몸이라 비교 대상이 아니다 — 운영 원장을 읽기 전용으로 본다.
    live = ROOT / "data/ibl_usage.db"
    if not live.exists():
        pytest.skip("운영 원장 없음")
    with sqlite3.connect(f"file:{live}?mode=ro", uri=True) as con:
        con.row_factory = sqlite3.Row
        row = dict(con.execute(
            "SELECT intent, ibl_code, alias, returns, signature FROM ibl_examples "
            "WHERE alias='위치마다읽기' AND always_on=1").fetchone())
    assert (
        lesson["body"] == row["ibl_code"]
    )  # 운영 몸을 옛 교재로 되돌리지 않는다
    (tmp_path / "data/idioms").mkdir(parents=True)
    (tmp_path / "data/idioms/curated.json").write_text(json.dumps(catalog))
    with sqlite3.connect(tmp_path / "data/ibl_usage.db") as con:
        con.execute(
            "CREATE TABLE ibl_examples (intent,ibl_code,success_count,fail_count,"
            "topic,alias,returns,signature,always_on,created_at)"
        )
        con.execute(
            "INSERT INTO ibl_examples VALUES (?,?,?,?,?,?,?,?,?,?)",
            (
                row["intent"],
                row["ibl_code"],
                1,
                0,
                "찾기",
                row["alias"],
                row["returns"],
                row["signature"],
                1,
                "2026-09-09",
            ),
        )
    monkeypatch.setattr(runtime_utils, "get_base_path", lambda: tmp_path)
    monkeypatch.setattr(
        ibl_access, "_idioms_cache", {"text": None, "t": 0, "key": None}
    )
    block = ibl_access.idioms_map(None)
    assert lesson["inputs"] in block and lesson["example"] in block


def test_correct_artifact_with_incidental_error_does_not_require_repair():
    out = execute(
        GOLD["direct_ledger"] + '\n[self:mkdir]{path:"outputs"}',
        "direct_ledger",
    )
    assert out["quality_ok"]
    assert not out["runtime_ok"] and out["result"]["error"]


def test_trial_stops_at_correct_result_even_if_runtime_has_warning(
    tmp_path, monkeypatch
):
    import idiom_exposure_study as study

    calls = []

    def model(*args):
        calls.append(args)
        return {"result": '{"code":"test"}', "wall_ms": 1}

    monkeypatch.setattr(study, "call_model", model)
    monkeypatch.setattr(
        study,
        "execute",
        lambda *a: {
            "quality_ok": True,
            "runtime_ok": False,
            "verdict": "품질 기준 통과",
            "result": {"success": False, "error": "부수 오류"},
        },
    )
    record = study.trial(
        tmp_path,
        {"cases": study.CASES, "max_repairs": 1},
        {
            "case": "direct_ledger",
            "repeat": 0,
            "arm": "exposed",
            "seed": 1,
        },
    )
    assert len(calls) == len(record["attempts"]) == 1


def test_equivalent_body_is_accepted_but_trace_and_wrong_body_are_rejected(
    tmp_path,
):
    setup(tmp_path, 7)
    initial = {
        str(p.relative_to(tmp_path)): p.read_bytes()
        for p in tmp_path.rglob("*")
        if p.is_file()
    }
    body = "\n".join(
        initial["drafts/report_2026-08-27.md"].decode().splitlines()[10:22]
    )

    def verdict(payload):
        return judge(
            "counter_latest",
            {"success": True, "final_result": payload},
            tmp_path,
            {},
            initial,
        )[0]

    assert verdict({"items": [{"file": "a.md", "content": body}]})
    assert verdict(
        {"_value_result": True, "value": {"items": [{"본문": body}]}}
    )
    assert not verdict({"items": [{"content": body + "\n원치 않은 줄"}]})
    assert not verdict({"results": [{"content": body}], "message": "완료"})
    assert not verdict({"items": [{"content": "다른 문서"}]})
    assert returned_body({"items": []}) == []


def test_korean_error_field_is_a_valid_location_failure():
    examples = json.loads(
        (EVIDENCE / "oracle_difference_examples.json").read_text()
    )
    example = next(
        e for e in examples if e["id"] == "direct_context_1_exposed"
    )
    out = execute(example["code"], "direct_context")
    assert out["quality_ok"], out["verdict"]


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, *sys.argv[1:]]))
