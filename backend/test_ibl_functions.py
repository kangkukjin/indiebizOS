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
import workflow_store  # 시험 대역도 저장소 소유자에 설치한다.
import ibl_engine  # noqa: E402
import ibl_executors as ex  # noqa: E402
import ibl_control_blocks as cb  # noqa: E402
import workflow_engine  # noqa: E402

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


# ---------------------------------------------------------------- F2 앞당김


# ---------------------------------------------------------------- F3 실행




# ---------------------------------------------------------------- F4 정직


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
