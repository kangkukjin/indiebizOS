"""프로그램급 IBL 회귀 배터리 (2026-08-22 — docs/IBL_PROGRAM_GRADE_DESIGN.md M1·M2).

  M1 봉투 다이어트 + 스필 싱크
    E1. 파이프 봉투 results[] 가 step 요약으로 접히고 final_result 는 원형 · 실패 step 오류문 보존
    E2. verbose=True 는 원형 · 멱등 · 비봉투(단일 액션) 무영향
    E3. [self:write]{spill: true} 가 {items:[], ref:{path,kind,count,bytes}} 를 낸다
    E4. 평가자 증거 추출(_unwrap_payload)이 요약 봉투에서 final_result 를 고른다
  M2 술어 확장
    C1. 파서 — 블록 조건식의 $변수는 텍스트 치환 없이 _vars 로, 분기 몸의 $변수는 step 치환
    C2. 엔진 — count($r)·matches·and 조건이 앞 문장 결과로 판정되고 분기 몸이 $r.경로 를 받는다
    C3. 미할당 $변수 = 판정 불능(condition_errors) · else 보류(거짓 단정 금지)
    C4. AI 술어 — [table:brief]{…} == "yes" (message 가 좌변값, "Yes." 정규화)
    C5. case 의 $변수 소스
    C6. 중첩 블록이 바깥 $변수를 계승
    C7. 정적 검수(validate_condition) — 자연어·상수·미할당 경고, 정상식 None
    C8. 옛 문법 회귀 없음 — node:action{…}.field <op> 값 · 연산자 없는 불리언

실행: .venv/bin/python3 -m pytest backend/test_ibl_program_grade.py
"""
import importlib.util
import json
import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import boot_paths  # noqa: F401

import ibl_engine
import ibl_executors as ex
import workflow_engine
from ibl_envelope import diet_envelope
from ibl_predicates import validate_condition

_PKG = Path(__file__).resolve().parent.parent / "data" / "packages" / "installed" / "tools"


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, str(path))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


# ── 공용 가짜 엔진: 잎 액션은 스텁, 블록은 진짜 실행기 ─────────────────────────────
SEARCH = {"success": True, "items": [{"title": "속보: 화재", "price": "3,500"},
                                     {"title": "일반 기사", "price": 50}], "count": 2}


def _fake_factory(calls, brief_answer="Yes."):
    def _fake(tool_input, project_path, agent_id=None, **kw):
        if tool_input.get("_condition"):
            return ex._execute_condition(tool_input, project_path, agent_id)
        if tool_input.get("_case"):
            return ex._execute_case(tool_input, project_path, agent_id)
        calls.append(tool_input)
        act = tool_input.get("action")
        if act == "search":
            return json.dumps(SEARCH, ensure_ascii=False)
        if act == "brief":
            return json.dumps({"success": True, "message": brief_answer, "_ai": True}, ensure_ascii=False)
        if act == "empty":
            return json.dumps({"success": True, "items": []})
        return {"success": True, "did": act, "params": tool_input.get("params", {})}
    return _fake




# ═══ M1 ═══════════════════════════════════════════════════════════════════════
def _envelope():
    big = json.dumps({"items": [{"t": i, "body": "x" * 50} for i in range(30)], "message": "총 30건"})
    return {
        "success": False, "steps_completed": 2, "steps_total": 3,
        "results": [
            {"step": 1, "node": "sense", "action": "search", "result": big, "duration_ms": 5},
            {"step": 2, "node": "table", "action": "brief", "result": json.dumps({"message": "요지 " * 100, "_ai": True}), "duration_ms": 9},
            {"step": 3, "node": "self", "action": "write", "result": json.dumps({"success": False, "error": "content가 필요합니다"}), "duration_ms": 1},
        ],
        "final_result": big,
    }


def test_e1_results_summarized_final_kept():
    env = _envelope()
    out = diet_envelope(env)
    assert out["_results_summarized"] is True and out["final_result"] == env["final_result"]
    s1, s2, s3 = out["results"]
    assert "result" not in s1 and s1["shape"] == "items" and s1["count"] == 30 and s1["columns"] == ["body", "t"]
    assert s1["bytes"] == len(env["results"][0]["result"]) and s1["preview"].startswith('{"t": 0')
    assert s2["shape"] == "message" and s2["preview"].endswith("…") and len(s2["preview"]) <= 170
    assert s3["shape"] == "error" and s3["error"] == "content가 필요합니다", s3
    assert len(json.dumps(out, ensure_ascii=False)) < len(json.dumps(env, ensure_ascii=False)) / 2
    # 실패 step(result 없이 error 만) 은 그대로
    env2 = {"results": [{"step": 1, "error": "변수 치환 실패", "duration_ms": 0}], "final_result": None}
    assert diet_envelope(env2)["results"][0]["error"] == "변수 치환 실패"


def test_e2_verbose_idempotent_noop():
    env = _envelope()
    assert diet_envelope(env, verbose=True) is env
    once = diet_envelope(env)
    assert diet_envelope(once) is once                        # 멱등
    single = {"success": True, "items": [1, 2]}
    assert diet_envelope(single) is single                    # 단일 액션 결과는 봉투가 아님
    assert diet_envelope("평문") == "평문"


def test_e3_write_spill_ref():
    sysess = _load("_t_sysess_pg", _PKG / "system_essentials" / "handler.py")

    # ★스텁 대신 진짜 ToolContext — 쓰기 경로 해소(resolve_output_path)가 컨텍스트 계약의
    # 일부가 됐다(J29-1). 반쪽 스텁은 그 계약을 안 밟아 결함을 가린다.
    from tool_context import ToolContext

    def _Ctx(td):
        return ToolContext(project_path=td, tool_name="write_file", agent_id="test")

    with tempfile.TemporaryDirectory() as td:
        piped = json.dumps({"items": [{"a": 1}, {"a": 2}], "success": True})
        out = json.loads(sysess.execute({"path": os.path.join(td, "s.json"), "spill": True,
                                         "_prev_result": piped}, _Ctx(td)))
        assert out["success"] and out["items"] == [] and out["spilled"] is True, out
        ref = out["ref"]
        assert ref["kind"] == "items" and ref["count"] == 2 and ref["bytes"] > 0
        assert os.path.exists(ref["path"]) and json.load(open(ref["path"]))["items"][1]["a"] == 2
        # spill 없으면 옛 모양(ref 없음) — 현행 유지
        plain = json.loads(sysess.execute({"path": os.path.join(td, "p.json"), "_prev_result": piped}, _Ctx(td)))
        assert "ref" not in plain and "items" not in plain


def test_e4_trace_evidence_prefers_final():
    from cognitive_trace import _unwrap_payload
    out = diet_envelope(_envelope())
    ev = _unwrap_payload(json.dumps(out, ensure_ascii=False))
    assert isinstance(ev, dict) and len(ev["items"]) == 30, type(ev)


# ═══ M2 ═══════════════════════════════════════════════════════════════════════












def test_c7_static_validation():
    assert "자연어" in validate_condition("디스크가 부족하면")
    assert "상수" in validate_condition("1 > 0")
    assert "$r" in validate_condition("count($r) > 0", known_vars=[])
    assert validate_condition("count($r) > 0", known_vars=["r"]) is None
    assert validate_condition('sense:host{op: "status"}.cpu_percent > 80 and not empty($x)', known_vars=["x"]) is None
    assert validate_condition('[table:brief]{instruction: "a and b"} == "yes"') is None




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
    raise SystemExit(_pytest.main([__file__] + _sys.argv[1:]))
