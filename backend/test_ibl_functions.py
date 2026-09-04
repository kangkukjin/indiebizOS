"""함수 문법 [def: 이름]{…} / [fn:이름]{인자} 회귀 (언어 개정 2026-09-05, 사용자 판정).

  F1  파서: 정의 블록은 몸(step 리스트)·시그니처(미할당 $이름)·todo 를 낸다. 중복·예약어·할당 좌변은 정직 오류.
  F2  앞당김: 호출이 정의보다 앞에 와도 `_fn_ref`(정의 표 참조) 가 붙는다. 정의 없는 이름은 붙지 않는다(원장 폴백 자리).
  F3  실행: 인자 주입·닫힌 스코프·`$return`·마지막 통화, 앞 통화(>>)가 몸의 첫 문장에 흐른다.
  F4  정직: 인자 누락·todo·깊이 상한(재귀)·정의도 원장도 없음 — 전부 이유가 있는 실패. 원장에 있으면 워크플로 폴백.
  F5  검증기: [fn:이름] 은 어휘가 아니다 — 소유 필터·액션 실존·param 검사·runnable 이 거절하지 않는다.
실행: .venv/bin/python -m pytest backend/test_ibl_functions.py -q
"""
import json
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import boot_paths  # noqa: E402,F401
import ibl_engine  # noqa: E402
import ibl_executors as ex  # noqa: E402
import ibl_control_blocks as cb  # noqa: E402
import workflow_engine  # noqa: E402
from ibl_parser import parse, IBLSyntaxError  # noqa: E402

ROWS = {"items": [{"a": 1}, {"a": 2}, {"a": 3}]}


def _fake_factory(calls):
    def _fake(tool_input, project_path, agent_id=None, **kw):
        if tool_input.get("_def"):
            return ibl_engine.execute_ibl.__wrapped__(tool_input, project_path, agent_id) if hasattr(ibl_engine.execute_ibl, "__wrapped__") else \
                {"success": True, "defined": tool_input["name"]}
        if tool_input.get("_node") == "fn":
            return cb._execute_fn(tool_input, project_path, agent_id)
        for key, fn in (("_condition", ex._execute_condition), ("_case", ex._execute_case),
                        ("_try", cb._execute_try), ("_repeat", cb._execute_repeat), ("_assign", cb._execute_assign)):
            if tool_input.get(key):
                return fn(tool_input, project_path, agent_id)
        calls.append(tool_input)
        act = tool_input.get("action")
        p = tool_input.get("params", {}) or {}
        if act == "rows":
            return json.dumps(ROWS)
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


def _step_env(out, idx):
    """독립 문장은 각자 결과를 갖는다 — idx 번째 step 의 결과 봉투(JSON 이면 파싱)."""
    r = out["results"][idx].get("result")
    return json.loads(r) if isinstance(r, str) and r.strip()[:1] in "{[" else r


def _fn_error(out):
    for r in out.get("results") or []:
        env = json.loads(r["result"]) if isinstance(r.get("result"), str) and r["result"].strip()[:1] in "{[" else r.get("result")
        if isinstance(env, dict) and env.get("fn") is not None and not env.get("success", True):
            return env["error"]
    return out.get("error")


# ---------------------------------------------------------------- F1 파서
def test_f1_def_block_parses_signature_and_todo():
    st = parse('[def: 두배]{\n$x = $n * 2\n$return = $x\n}')
    assert len(st) == 1 and st[0]["_def"] and st[0]["name"] == "두배" and st[0]["signature"] == ["n"]
    assert isinstance(st[0]["body"], list) and st[0]["todo"] is False
    st = parse('[def: 나중]{todo}')
    assert st[0]["todo"] is True and st[0]["body"] is None and st[0]["signature"] == []
    for bad in ('[def: a]{[x:y]}\n[def: a]{[x:y]}', '[def: if]{[x:y]}', '$v = [def: a]{[x:y]}', '[def: a]{}'):
        with pytest.raises(IBLSyntaxError):
            parse(bad)


# ---------------------------------------------------------------- F2 앞당김
def test_f2_forward_reference_binds_and_unknown_stays_unbound():
    st = parse('[fn:모으기]{q: "a"}\n[fn:없음]{}\n[def: 모으기]{[x:rows]{q: "$q"} >> [x:take]{n: 2}}')
    assert st[0].get("_def")                                                # 정의는 앞으로 끌려 올라온다
    call, unknown = st[1], st[2]
    assert call["_node"] == "fn" and call["_fn_ref"]["name"] == "모으기" and call["_fn_ref"]["params"] == ["q"]
    assert "_fn_ref" not in unknown and "body" not in call["_fn_ref"]      # 몸통은 step 에 없다(정의 표 참조)


# ---------------------------------------------------------------- F3 실행
def test_f3_call_with_params_return_and_flowing_currency():
    calls = []
    out = _run('$r = [fn:앞둘]{k: 2}\n[def: 앞둘]{[x:rows]{} >> [x:take]{n: "$k"}}', calls)
    assert out["success"], out.get("error")
    assert out["results"][0]["node"] == "?" and _step_env(out, 0)["defined"] == "앞둘"   # 정의가 앞으로 끌려 올라왔다
    fn_env = _step_env(out, 1)
    assert fn_env["fn"] == "앞둘" and fn_env["fn_source"] == "def" and fn_env["params_injected"] == ["k"]
    assert "params_warning" not in fn_env                                  # 배관 키(_raw)는 인자로 새지 않는다
    assert [r["a"] for r in fn_env["items"]] == [1, 2]                    # 인자 k=2 가 몸의 $k 에 들어갔다
    assert [c["action"] for c in calls] == ["rows", "take"]
    assert _final(out)["fn"] == "앞둘"                                     # 마지막 문장의 통화가 정의 신고에 가려지지 않는다
    # 앞 통화가 몸의 첫 문장으로 흐른다 + $return 규약
    calls.clear()
    out = _run('[x:rows]{} >> [fn:둘]{}\n[def: 둘]{$t = [x:take]{n: 2}\n$return = $t}', calls)
    assert out["success"], out.get("error")
    fn_env = _step_env(out, len(out["results"]) - 1)
    assert fn_env["returned"] == "$return" and [r["a"] for r in fn_env["items"]] == [1, 2]
    assert calls[-1]["action"] == "take" and json.loads(calls[-1]["params"]["_prev_result"])["items"] == ROWS["items"]


def test_f3_real_engine_assign_only_body():
    # 실제 실행기 경로: [def:] 는 정의 신고, 몸이 식 할당뿐인 함수는 도구 없이 돈다
    st = parse('[def: 두배]{$x = $n * 2\n$return = $x}\n$r = [fn:두배]{n: 21}')
    d = ibl_engine.execute_ibl(st[0], ".", None)
    assert d["success"] and d["defined"] == "두배" and d["signature"] == ["n"]
    r = ibl_engine.execute_ibl(st[1], ".", None)
    assert r["success"] and r["returned"] == "$return"
    assert str(r["final_result"]).strip() in ("42", "42.0")                # $return 의 값 그대로


# ---------------------------------------------------------------- F4 정직
def test_f4_honest_failures_and_workflow_fallback(monkeypatch):
    out = _run('[fn:두배]{}\n[def: 두배]{$x = $n * 2\n$return = $x}')
    assert not out["success"] and "인자 누락" in _fn_error(out) and "$n" in _fn_error(out)
    out = _run('[fn:나중]{}\n[def: 나중]{todo}')
    assert not out["success"] and "todo" in _fn_error(out)
    out = _run('[fn:무한]{}\n[def: 무한]{[fn:무한]{}}')
    assert not out["success"] and "깊이 상한" in json.dumps(out, ensure_ascii=False)
    out = _run('[fn:없는이름]{}')
    assert not out["success"] and "정의가 없고" in _fn_error(out)
    monkeypatch.setattr(workflow_engine, "get_workflow", lambda wid: {"name": wid} if wid == "저장된것" else None)
    monkeypatch.setattr(workflow_engine, "execute_workflow", lambda wid, pp, params=None, **kw: {"success": True, "workflow_id": wid, "got": params})
    out = _run('[fn:저장된것]{city: "수원"}')
    fn_env = _step_env(out, 0)
    assert fn_env["fn_source"] == "workflow" and fn_env["got"] == {"city": "수원"}


# ---------------------------------------------------------------- F5 검증기
def test_f5_validators_treat_fn_as_call_not_vocab():
    from ibl_registry import foreign_actions
    from ibl_param_vocab import check_code_params
    import ibl_usage_rag as rag
    code = '[fn:요약]{q: "x"} >> [table:take]{n: 1}\n[def: 요약]{[sense:search]{query: "$q"} >> [table:take]{n: 3}}'
    assert "fn:요약" not in foreign_actions(code)
    assert rag._validate_ibl_actions('[fn:summarize]{q: "x"} >> [table:take]{n: 1}') is True
    assert check_code_params(code) == []
    chk = workflow_engine.check_runnable if hasattr(workflow_engine, "check_runnable") else None
    if chk:
        assert chk(code)["runnable"] is True


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))


# ---------------------------------------------------------------- F6 관용구 = 이름 붙은 함수 (2026-09-05)
def test_f6_fn_resolves_named_idiom_after_def_and_workflow(monkeypatch):
    import ibl_usage_db as mod
    calls = []
    monkeypatch.setattr(workflow_engine, "get_workflow", lambda wid: None)
    monkeypatch.setattr(mod.IBLUsageDB, "_instance", None)
    monkeypatch.setattr(mod.IBLUsageDB, "__init__", lambda self, *a, **k: None)
    monkeypatch.setattr(mod.IBLUsageDB, "find_phrase_by_alias",
                        lambda self, name: {"id": 1, "intent": "앞 둘 뽑기", "alias": name,
                                            "ibl_code": '[x:rows]{q: "${질의}"} >> [x:take]{n: 2}', "topic": "개발"} if name == "앞둘뽑기" else None)
    monkeypatch.setattr(mod.IBLUsageDB, "phrase_aliases", lambda self, limit=12: ["앞둘뽑기"])
    used = []
    monkeypatch.setattr(mod.IBLUsageDB, "update_success_by_code", lambda self, code, ok, **kw: used.append((code, ok)) or True)
    out = _run('[fn:앞둘뽑기]{질의: "a"}', calls)
    fn_env = _step_env(out, 0)
    assert fn_env["success"] and fn_env["fn_source"] == "idiom" and fn_env["params_required"] == ["질의"]
    assert calls[0]["params"]["q"] == "a"                                 # ${슬롯} 이 시그니처 — 인자가 들어갔다
    assert used and used[0][1] is True                                     # 이름으로 부른 관용구는 쓰인 것(귀속)
    out = _run('[fn:앞둘뽑기]{}')
    assert "인자 누락" in _fn_error(out)
    out = _run('[fn:없는것]{}')
    assert "관용구 이름: 앞둘뽑기" in _fn_error(out)


def test_f6_idiom_name_sanitize_and_unique():
    from ibl_idiom import sanitize_fn_name, unique_fn_name
    assert sanitize_fn_name("뉴스 모아 쓰기!", "x") == "뉴스모아쓰기"
    assert sanitize_fn_name("", "뉴스 모아 선별하고 절 본문 쓰기") == "뉴스모아선별하고절본문쓰"
    assert sanitize_fn_name("if", "의도") == "의도" and sanitize_fn_name("123", "") .startswith("관용구")

    class DB:
        def find_phrase_by_alias(self, n):
            return {"ibl_code": "A"} if n == "이름" else ({"ibl_code": "B"} if n == "이름2" else None)
    assert unique_fn_name("이름", DB(), "A") == "이름"          # 같은 골격이면 같은 이름
    assert unique_fn_name("이름", DB(), "C") == "이름3"         # 다른 골격이 이름·이름2 를 차지하면 이름3
