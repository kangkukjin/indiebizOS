"""프로그램급 IBL 회귀 배터리 3 (2026-08-22 — M6: 긴 프로그램이 멈추던 자리 4곳).

  A1. 식 할당 `$n = 0` / `$n = $n + 1` / `$s = $r.count * 2` — 뒤 문장 치환·조건에서 value 로
  A2. 식 할당 오류 — 미할당 변수·허용 밖 구문·따옴표 빠진 문자열 = 정직 에러
  W1. [repeat: while $n < 3]{$n = $n + 1 …} — while 이 몸 변수를 보고, 루프 뒤 바깥 $n 이 최신값
  W2. 몸 안 중첩 [if:] 가 바깥·몸 변수를 계승(인덱스 충돌 없음)
  P1. 파이프 속 [if:] — 직전 통화를 `$items` 로 보고 분기 몸에 넘기며 결과가 다음 step 통화
  P2. 파이프 속 [repeat:]·[try] — `[repeat …]{…} >> [table:dedup]` 모양이 한 문장
  F1. `$return = …` — workflow run 반환값이 마지막 문장이 아니라 $return 의 결과
  F2. $return 없으면 옛 규약(마지막 문장 items 승격) 불변

실행: .venv/bin/python3 -m pytest -q backend/test_ibl_program_grade_m6.py
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import boot_paths  # noqa: F401

import ibl_engine
import ibl_executors as ex
import ibl_control_blocks as cb
import workflow_engine
from ibl_parser import parse

ROWS = {"success": True, "items": [{"title": "a", "n": 1}, {"title": "b", "n": 2}, {"title": "a", "n": 3}], "count": 3}


def _fake_factory(calls):
    def _fake(tool_input, project_path, agent_id=None, **kw):
        for key, fn in (("_condition", ex._execute_condition), ("_case", ex._execute_case),
                        ("_try", cb._execute_try), ("_repeat", cb._execute_repeat), ("_assign", cb._execute_assign)):
            if tool_input.get(key):
                return fn(tool_input, project_path, agent_id)
        calls.append(tool_input)
        act = tool_input.get("action")
        p = tool_input.get("params", {}) or {}
        if act == "rows":
            return json.dumps(ROWS)
        if act == "bad":
            return json.dumps({"success": False, "error": "고장"})
        if act == "dedup":
            prev = json.loads(p["_prev_result"])
            seen, out = set(), []
            for r in prev["items"]:
                if r["title"] not in seen:
                    seen.add(r["title"]); out.append(r)
            return json.dumps({"items": out})
        if act == "take":
            prev = json.loads(p["_prev_result"])
            return json.dumps({"items": prev["items"][: int(p.get("n", 1))]})
        return {"success": True, "did": act, "params": {k: v for k, v in p.items() if not k.startswith("_")},
                "prev": p.get("_prev_result")}
    return _fake


def _run(code, calls=None):
    calls = calls if calls is not None else []
    orig = ibl_engine.execute_ibl
    ibl_engine.execute_ibl = _fake_factory(calls)
    try:
        return workflow_engine.execute_pipeline(parse(code), ".")
    finally:
        ibl_engine.execute_ibl = orig


def _final(out):
    f = out.get("final_result")
    return json.loads(f) if isinstance(f, str) and f.strip()[:1] in "{[" else f


def test_a1_expression_assignment():
    calls = []
    out = _run('$n = 0\n$n = $n + 1\n$r = [sense:rows]{}\n$s = $r.count * 2 + $n\n'
               '[self:echo]{n: "$n", s: "$s"}\n[if: $s == 7 and $n < 2]{[self:yes]{}} [else]{[self:no]{}}', calls)
    assert out["success"], out
    echo = next(c for c in calls if c["action"] == "echo")
    assert {k: v for k, v in echo["params"].items() if not k.startswith("_")} == {"n": "1", "s": "7"}, echo
    assert [c["action"] for c in calls][-1] == "yes"
    # 문자열 식·조건식 삼항
    out = _run('$a = "x"\n$b = $a + "y"\n$c = 10 if $b == "xy" else 0\n[self:echo]{b: "$b", c: "$c"}', calls)
    assert {k: v for k, v in calls[-1]["params"].items() if not k.startswith("_")} == {"b": "xy", "c": "10"}


def test_a2_assignment_errors():
    out = _run('$n = $zz + 1\n[self:echo]{}', [])
    assert out["success"] is False and "$zz" in json.dumps(out, ensure_ascii=False)
    out = _run('$n = __import__("os")\n[self:echo]{}', [])
    assert out["success"] is False
    out = _run('$n = hello\n[self:echo]{}', [])
    assert out["success"] is False and "따옴표" in json.dumps(out, ensure_ascii=False)


def test_w1_while_sees_body_vars_and_writes_back():
    calls = []
    out = _run('$n = 0\n[repeat: while $n < 3, max: 10]{$n = $n + 1\n[self:work]{k: "$n"}}\n[self:done]{n: "$n"}', calls)
    assert out["success"], out
    ks = [c["params"]["k"] for c in calls if c["action"] == "work"]
    assert ks == ["1", "2", "3"], ks
    assert calls[-1]["action"] == "done" and calls[-1]["params"]["n"] == "3"      # 루프 뒤 바깥 $n 최신값
    rep = json.loads(out["results"][1]["result"])
    assert rep["iterations"] == 3 and "halted" not in rep


def test_w2_nested_if_inside_repeat():
    calls = []
    out = _run('$n = 0\n[repeat: 4]{$n = $n + 1\n[if: $n == 2 or $i == 3]{[self:hit]{n: "$n", i: "$i"}} [else]{[self:miss]{}}}', calls)
    assert out["success"], out
    hits = [c["params"] for c in calls if c["action"] == "hit"]
    assert hits == [{"n": "2", "i": "1"}, {"n": "4", "i": "3"}], hits


def test_p1_block_in_pipe_condition():
    calls = []
    out = _run('[sense:rows]{} >> [if: count($items) > 2 and $items.0.title == "a"]{[sense:take]{n: 1}} [else]{[self:no]{}} >> [self:sink]{}', calls)
    assert out["success"], out
    assert [c["action"] for c in calls] == ["rows", "take", "sink"]
    assert json.loads(calls[1]["params"]["_prev_result"])["count"] == 3          # 분기 몸이 직전 통화를 받는다
    sink_prev = json.loads(calls[2]["params"]["_prev_result"])
    assert len(sink_prev["items"]) == 1
    # 빈 입력 → else
    calls.clear()
    out = _run('[sense:rows]{} >> [sense:take]{n: 0} >> [if: empty($items)]{[self:empty]{}} [else]{[self:no]{}}', calls)
    assert [c["action"] for c in calls][-1] == "empty"


def test_p2_repeat_and_try_in_pipe():
    calls = []
    out = _run('[repeat: 2, collect: true]{[sense:rows]{}} >> [sense:dedup]{} >> [self:sink]{}', calls)
    assert out["success"], out
    assert len(json.loads(calls[-1]["params"]["_prev_result"])["items"]) == 2     # 6행 → dedup 2
    calls.clear()
    out = _run('[sense:rows]{} >> [try]{[sense:bad]{}} [catch]{[sense:take]{n: 2}} >> [self:sink]{}', calls)
    assert out["success"] and len(json.loads(calls[-1]["params"]["_prev_result"])["items"]) == 2


def test_f1_return_convention(monkeypatch):
    calls = []
    orig = ibl_engine.execute_ibl
    ibl_engine.execute_ibl = _fake_factory(calls)
    try:
        out = workflow_engine._run_inline({"pipeline": '$return = [sense:rows]{} >> [sense:take]{n: 2}\n[self:notify]{}'}, ".")
        assert out["success"] and out["returned"] == "$return" and out["count"] == 2, out
        assert [c["action"] for c in calls] == ["rows", "take", "notify"]
    finally:
        ibl_engine.execute_ibl = orig


def test_f2_no_return_keeps_last_statement():
    calls = []
    orig = ibl_engine.execute_ibl
    ibl_engine.execute_ibl = _fake_factory(calls)
    try:
        out = workflow_engine._run_inline({"pipeline": '[sense:rows]{} >> [sense:take]{n: 1}'}, ".")
        assert out["success"] and "returned" not in out and out["count"] == 1
    finally:
        ibl_engine.execute_ibl = orig


if __name__ == "__main__":                      # 러너는 하나 — pytest (2026-08-23)
    # ★두 번째 러너를 두지 않는다. 손으로 적은 러너는 반드시 드리프트한다 — 새 시험 함수를
    # 러너에 안 적으면 직접 실행이 **그 시험만 조용히 건너뛰고 종료코드 0** 을 낸다.
    # 실측(2026-08-23): 배터리 44개·시험 303건 중 **147건**이 직접 실행에서 한 번도 안 돌았고,
    # 27·28회차 상상훈련이 그 초록을 "전부 통과"로 보고서에 적었다(거짓 초록).
    # 위임하면 직접 실행도 살고(순찰·손버릇) 수집은 pytest 가 하므로 드리프트가 불가능하다.
    import sys as _sys
    try:
        import pytest as _pytest
    except ImportError:
        raise SystemExit("pytest 가 없습니다 — .venv/bin/python -m pytest 로 실행하세요")
    raise SystemExit(_pytest.main([__file__, "-q"] + _sys.argv[1:]))
