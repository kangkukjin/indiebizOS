"""프로그램급 IBL 회귀 배터리 2 (2026-08-22 — 설계 M3·M4·M5).

  M3 오류 처리
    T1. [try]{실패} [catch]{$error.summary 치환} → catch 결과 + _caught 메타
    T2. try 성공 → catch 안 돎, finally 는 돎(결과 불변)
    T3. try·catch 모두 실패 → 두 오류 동봉(덮어쓰기 금지)
    T4. [on_error: skip] — 실패 step 건너뛰고 직전 통화로 계속 + skipped_steps 신고
    T5. [on_error: null] — 빈 items 로 계속
    T6. A ?? (B >> C) 괄호 파이프 가지
  M4 반복
    R1. [repeat: 3, collect: true] — $i 치환·회차 items 이어붙임
    R2. until 이 몸통 할당 $st 를 읽는다(3회차에 done)
    R3. until 미충족 max 도달 → halted:"max"(성공·통화 냄)
    R4. while 바깥 $변수 · 몸통 실패 → success False
    R5. [table:each]{collect: true}
  M5 누적·스필·재개
    D1. [table:reduce] 합·문자열·없는 열·허용 밖 구문
    S1. 자동 스필 — 임계 초과 통화가 참조로 흐르고 $items 바인딩·data-ops _get_items 가 투명하게 읽는다
    S2. 실패 봉투 resume → 그 step 부터 재개(앞 단 재실행 0)
    S3. 스필 GC(24h)

실행: .venv/bin/python3 -m pytest -q backend/test_ibl_program_grade_m3m5.py
"""
import importlib.util
import json
import os
import sys
import time
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))
import boot_paths  # noqa: F401

import ibl_engine
import ibl_executors as ex
import ibl_control_blocks as cb
import workflow_engine
from ibl_parser import parse
from common import spill as spill_mod

_PKG = Path(__file__).resolve().parent.parent / "data" / "packages" / "installed" / "tools"


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, str(path))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


ROWS = {"success": True, "items": [{"title": "a", "n": 1}, {"title": "b", "n": 2}, {"title": "c", "n": 3}]}


def _fake_factory(calls, state):
    def _fake(tool_input, project_path, agent_id=None, **kw):
        for key, fn in (("_condition", ex._execute_condition), ("_case", ex._execute_case),
                        ("_try", cb._execute_try), ("_repeat", cb._execute_repeat)):
            if tool_input.get(key):
                return fn(tool_input, project_path, agent_id)
        calls.append(tool_input)
        act = tool_input.get("action")
        p = tool_input.get("params", {}) or {}
        if act == "rows":
            return json.dumps(ROWS)
        if act == "bad":
            return json.dumps({"success": False, "error": "고장: " + str(p.get("why", "x"))})
        if act == "boom":
            raise RuntimeError("예외 발생")
        if act == "status":
            state["calls"] = state.get("calls", 0) + 1
            return json.dumps({"success": True, "status": "done" if state["calls"] >= 3 else "running", "n": state["calls"]})
        if act == "each":
            return ex._execute_table_each(dict(p), project_path, agent_id=agent_id)
        if act == "reduce":
            return cb._execute_table_reduce(dict(p), project_path, agent_id=agent_id)
        if act == "big":
            return json.dumps({"items": [{"i": i, "pad": "x" * 100} for i in range(50)]})
        if act == "take":
            prev = p.get("_prev_result")
            obj, err = spill_mod.resolve_ref_str(prev)
            if err:
                return json.dumps({"success": False, "error": err})
            if isinstance(obj, str):
                obj = json.loads(obj) if obj.strip()[:1] in "{[" else {}
            items = obj.get("items") if isinstance(obj, dict) else []
            return json.dumps({"items": items[: int(p.get("n", 1))]})
        return {"success": True, "did": act, "params": {k: v for k, v in p.items() if not k.startswith("_")},
                "prev": p.get("_prev_result")}
    return _fake


def _run(code, calls=None, state=None, context=None):
    calls = calls if calls is not None else []
    state = state if state is not None else {}
    orig = ibl_engine.execute_ibl
    ibl_engine.execute_ibl = _fake_factory(calls, state)
    try:
        return workflow_engine.execute_pipeline(parse(code), ".", context=context)
    finally:
        ibl_engine.execute_ibl = orig


def _final(out):
    f = out.get("final_result")
    return json.loads(f) if isinstance(f, str) and f.strip()[:1] in "{[" else f


@pytest.fixture
def tmp_spill(tmp_path, monkeypatch):
    monkeypatch.setattr(spill_mod, "_root", lambda: str(tmp_path / "spill"))
    return tmp_path / "spill"


# ═══ M3 ═══
def test_t1_try_catch_error_binding():
    calls = []
    out = _run('[try]{[sense:bad]{why: "크롤 실패"}} [catch]{[self:notify]{message: "대체: $error.summary"}}', calls)
    assert out["success"], out
    acts = [c["action"] for c in calls]
    assert acts == ["bad", "notify"]
    assert calls[1]["params"]["message"] == "대체: 고장: 크롤 실패"
    fr = _final(out)
    assert fr["_caught"]["summary"] == "고장: 크롤 실패" and fr["did"] == "notify"


def test_t2_try_success_finally_runs():
    calls = []
    out = _run('[try]{[sense:rows]{}} [catch]{[self:no]{}} [finally]{[self:cleanup]{}}', calls)
    assert out["success"] and [c["action"] for c in calls] == ["rows", "cleanup"]
    assert _final(out)["items"][0]["title"] == "a"          # finally 는 결과를 바꾸지 않는다


def test_t3_try_and_catch_both_fail():
    calls = []
    out = _run('[try]{[sense:bad]{why: "1차"}} [catch]{[sense:bad]{why: "2차"}}', calls)
    assert out["success"] is False
    fr = _final(out)
    assert fr["try_error"]["summary"] == "고장: 1차" and fr["catch_error"]["summary"] == "고장: 2차"
    # 예외도 실패로
    out = _run('[try]{[sense:boom]{}} [catch]{[self:ok]{}}', [])
    assert out["success"] and _final(out)["_caught"]["error"].startswith("RuntimeError")


def test_t4_on_error_skip():
    calls = []
    out = _run('[on_error: skip] [sense:rows]{} >> [sense:bad]{} >> [self:sink]{}', calls)
    assert out["success"] and out["skipped_steps"] == [2] and "건너뛰었" in out["warning"], out
    assert out["results"][1]["skipped"] == "skip"
    prev = json.loads(calls[2]["params"]["_prev_result"])
    assert len(prev["items"]) == 3                           # 직전(step1) 통화가 step3 에
    # 기본(stop)은 현행 그대로
    out = _run('[sense:rows]{} >> [sense:bad]{} >> [self:sink]{}', [])
    assert out["success"] is False and out["steps_completed"] == 1


def test_t5_on_error_null():
    calls = []
    out = _run('[on_error: null] [sense:bad]{} >> [self:sink]{}', calls)
    assert out["success"] and out["skipped_steps"] == [1]
    assert json.loads(calls[1]["params"]["_prev_result"]) == {"items": []}


def test_t6_fallback_paren_branch():
    calls = []
    out = _run('[sense:bad]{} ?? ([sense:rows]{} >> [sense:take]{n: 2})', calls)
    assert out["success"], out
    assert [c["action"] for c in calls] == ["bad", "rows", "take"]
    fr = _final(out)
    assert len(fr["items"]) == 2 and fr["_fallback_used"] == 2


# ═══ M4 ═══
def test_r1_repeat_count_collect():
    calls = []
    out = _run('[repeat: 3, collect: true]{[sense:rows]{page: "$i"} >> [sense:take]{n: 1}}', calls)
    assert out["success"], out
    pages = [c["params"].get("page") for c in calls if c["action"] == "rows"]
    assert pages == ["0", "1", "2"]
    fr = _final(out)
    assert fr["iterations"] == 3 and fr["count"] == 3 and "halted" not in fr


def test_r2_repeat_until_body_var():
    calls, state = [], {}
    out = _run('[repeat: until $st.status == "done", max: 10]{$st = [self:status]{}}', calls, state)
    assert out["success"], out
    fr = _final(out)
    assert fr["iterations"] == 3 and "halted" not in fr and fr["last"]["status"] == "done"


def test_r3_repeat_until_max_halt():
    calls, state = [], {"calls": -100}
    out = _run('[repeat: until $st.status == "done", max: 2]{$st = [self:status]{}}', calls, state)
    assert out["success"], out
    fr = _final(out)
    assert fr["halted"] == "max" and fr["iterations"] == 2 and "max=2" in fr["note"]


def test_r4_repeat_while_outer_var_and_body_failure():
    calls = []
    out = _run('$q = [sense:rows]{}\n[repeat: while count($q) > 0, max: 3]{[self:work]{}}', calls)
    fr = _final(out)
    assert fr["iterations"] == 3 and fr["halted"] == "max"
    out = _run('$q = [sense:rows]{}\n[repeat: while count($q) > 5, max: 3]{[self:work]{}}', calls)
    assert _final(out)["iterations"] == 0
    out = _run('[repeat: 3]{[sense:bad]{}}', [])
    assert out["success"] is False and _final(out)["halted"] == "error" and _final(out)["iterations"] == 1
    # every 상한·판정 불능
    out = _run('[repeat: until $nope == 1, max: 3]{[self:work]{}}', [])
    assert out["success"] is False and _final(out)["halted"] == "condition_error"


def test_r5_each_collect():
    calls = []
    out = _run('[sense:rows]{} >> [table:each]{collect: true, do: "[self:echo]{t: \'$it.title\'}"}', calls)
    assert out["success"], out
    fr = _final(out)
    assert fr["rows_processed"] == 3 and fr["count"] == 3, fr
    assert [r["params"]["t"] for r in fr["items"]] == ["a", "b", "c"]      # 회차 결과가 행 감싸기 없이 평탄


# ═══ M5 ═══
def test_d1_reduce():
    r = cb._execute_table_reduce({"items": ROWS["items"], "init": 0, "step": "acc + n", "as": "합"}, ".")
    assert r["success"] and r["value"] == 6 and r["items"] == [{"합": 6}] and r["message"] == "6"
    r = cb._execute_table_reduce({"items": ROWS["items"], "init": "", "step": 'acc + title + ","'}, ".")
    assert r["value"] == "a,b,c,"
    r = cb._execute_table_reduce({"items": ROWS["items"], "step": "max(acc, n) if i > 0 else n"}, ".")
    assert r["value"] == 3
    r = cb._execute_table_reduce({"items": ROWS["items"], "step": "acc + 없는열"}, ".")
    assert r["success"] is False and "없는열" in r["error"]
    r = cb._execute_table_reduce({"items": ROWS["items"], "step": "__import__('os')"}, ".")
    assert r["success"] is False and "식 오류" in r["error"]
    # 파이프 안에서
    out = _run('[sense:rows]{} >> [table:reduce]{init: 0, step: "acc + n"}', [])
    assert _final(out)["value"] == 6


def test_s1_auto_spill_transparent(tmp_spill, monkeypatch):
    monkeypatch.setattr(spill_mod, "AUTO_SPILL_THRESHOLD", 500)
    calls = []
    out = _run('[sense:big]{} >> [sense:take]{n: 2} >> [self:show]{markers: "$items"}', calls)
    assert out["success"], out
    assert out["results"][0]["spilled"]["kind"] == "items" and out["results"][0]["spilled"]["count"] == 50
    ref_env = json.loads(calls[1]["params"]["_prev_result"])
    assert ref_env["items"] == [] and ref_env["_spilled"] is True
    assert os.path.isfile(ref_env["ref"]["path"])
    assert len(calls[2]["params"]["markers"]) == 2          # $items 바인딩이 참조 너머를 읽음(step2 결과는 작아 스필 안 됨)
    # 마지막 step 결과는 스필하지 않는다 (final_result 원형)
    out = _run('[sense:big]{}', [])
    assert "spilled" not in json.dumps(out)
    # data-ops 변환자 _get_items 투명 해소
    dataops = _load("_t_dataops_pg", _PKG / "data-ops" / "handler.py")
    env = spill_mod.spill_write(json.dumps(ROWS), tag="t")
    recs, _ = dataops._get_items(env)
    assert recs and recs[0]["title"] == "a"


def test_s2_resume(tmp_spill):
    from system_tools_ibl import _execute_ibl_unified
    calls, state = [], {}
    orig = ibl_engine.execute_ibl
    ibl_engine.execute_ibl = _fake_factory(calls, state)
    try:
        code = '[sense:rows]{} >> [sense:take]{n: 2} >> [sense:bad]{} >> [self:sink]{}'
        out = json.loads(_execute_ibl_unified({"code": code}, ".", agent_id="t"))
        assert out["success"] is False and out["resume"]["from_step"] == 3, out
        ref = out["resume"]["prev_ref"]
        assert os.path.isfile(ref["path"]) and ref["count"] == 2
        # 재개: step 3 부터, 앞 단 재실행 없음 — 여기선 step3 을 다시 실패시키지 않도록 code 를 고친 상황을 흉내
        calls.clear()
        fixed = '[sense:rows]{} >> [sense:take]{n: 2} >> [self:fixed]{} >> [self:sink]{}'
        out2 = json.loads(_execute_ibl_unified({"code": fixed, "resume": {"from_step": 3, "prev_ref": ref}}, ".", agent_id="t"))
        assert out2["success"] and out2["resumed_from"] == 3, out2
        assert [c["action"] for c in calls] == ["fixed", "sink"]
        assert len(json.loads(calls[0]["params"]["_prev_result"])["items"]) == 2
        assert [r["step"] for r in out2["results"]] == [3, 4]
        # 앞 단 $변수 참조가 남아 있으면 거절
        bad = '$r = [sense:rows]{}\n[sense:take]{n: 2} >> [sense:x]{} >> [self:sink]{m: "$r.items.0.title"}'
        out3 = json.loads(_execute_ibl_unified({"code": bad, "resume": {"from_step": 3, "prev_ref": ref}}, ".", agent_id="t"))
        assert "resume 불가" in out3["error"]
    finally:
        ibl_engine.execute_ibl = orig


def test_s3_spill_gc(tmp_spill):
    env = spill_mod.spill_write("x" * 10, tag="old")
    old = env["ref"]["path"]
    os.utime(old, (time.time() - 25 * 3600, time.time() - 25 * 3600))
    fresh = spill_mod.spill_write("y", tag="new")["ref"]["path"]
    assert not os.path.exists(old) and os.path.exists(fresh)
    body, err = spill_mod.read_ref(env["ref"])
    assert body is None and "24h" in err
