"""criteria 품질 계약 회귀 테스트 (2026-08-27, docs/IBL_QUALITY_CONTRACT_HANDOFF.md)

판정자(_call_judge)는 전부 패치 — 실제 원샷 호출 0, 결정론.

    C1. 통과: criteria_verdict=pass 병기 + 핸들러에 criteria 불도달(param 경고 없음)
    C2. 비-AI 액션 미달: 재시도 없이 quality 실패(트레이스백 error_type=quality,
        rejected_result 동봉)
    C3. 파이프 통합: 미달 step 의 quality 트레이스백을 파이프가 승계(pipeline 프레임)
    C4. 판정 불능: 통과 + unjudged 신고 (침묵 없음)
    C5. AI 낱말 재시도: 미달→피드백 얹은 재실행→통과 = pass_after_retry + _criteria_retried
    C6. 재시도도 미달: quality 실패 + quality_retried=true
    C7. 선언 충돌: 액션이 criteria 를 선언하면(image_read op:critic) 엔진이 안 가로챔
    C8. 정직 표지: _criteria_retried 가 markers_of 로 경계를 넘는다

실행: python3 backend/test_ibl_criteria_contract.py
"""
import json
import sys

sys.path.insert(0, __file__.rsplit('/', 1)[0])
import boot_paths  # noqa: F401 — 층 디렉토리 등재

from thread_context import actor_context  # noqa: E402
import ibl_quality as iq  # noqa: E402 — 엔진과 같은 flat 인스턴스를 패치해야 한다
from ibl_engine import execute_ibl  # noqa: E402
from ibl.workflow_engine import execute_pipeline  # noqa: E402
from ibl.ibl_parser import parse as ibl_parse  # noqa: E402
from ibl_honesty import markers_of  # noqa: E402

PASS = FAIL = 0


def check(name, cond, detail=""):
    global PASS, FAIL
    if cond:
        PASS += 1
        print(f"  ok  {name}")
    else:
        FAIL += 1
        print(f"  FAIL {name} — {detail}")


class FakeJudge:
    """스크립트된 판정 응답 — 호출 프롬프트를 기록한다."""

    def __init__(self, *responses):
        self.responses = list(responses)
        self.prompts = []

    def __call__(self, prompt):
        self.prompts.append(prompt)
        return self.responses.pop(0) if self.responses else self.responses_exhausted()

    @staticmethod
    def responses_exhausted():
        raise AssertionError("판정자 호출이 스크립트보다 많다")


J_PASS = '{"pass": true, "reason": "기준 충족"}'


def _run_step(code_step, judge):
    iq._call_judge = judge
    with actor_context(agent_id="test", origin="test"):
        return execute_ibl(code_step, ".", "test")


def _step(node, action, **params):
    return {"_node": node, "action": action, "params": params}


def c1_pass():
    print("C1. 통과 + 핸들러 불도달")
    judge = FakeJudge(J_PASS)
    res = _run_step(_step("table", "take", items=[{"a": 1}], n=1, criteria="행이 1개"), judge)
    obj = json.loads(res) if isinstance(res, str) else res
    check("판정자 1회", len(judge.prompts) == 1, str(len(judge.prompts)))
    check("criteria_verdict=pass", isinstance(obj, dict) and obj.get("criteria_verdict") == "pass",
          str(obj)[:200])
    check("param 경고 없음(핸들러 불도달)", "param_warning" not in (obj or {}), str(obj)[:200])
    check("판정 프롬프트에 기준 포함", "행이 1개" in judge.prompts[0])


def c2_nonai_fail():
    print("C2. 비-AI 액션 미달 → 재시도 없이 quality 실패")
    judge = FakeJudge('{"pass": false, "reason": "행 수가 기준과 다름"}')
    res = _run_step(_step("table", "take", items=[{"a": 1}], n=1, criteria="행이 5개"), judge)
    check("판정자 1회(재시도 없음)", len(judge.prompts) == 1, str(len(judge.prompts)))
    check("quality 실패 봉투", isinstance(res, dict) and res.get("success") is False
          and res.get("criteria_verdict") == "fail", str(res)[:250])
    tb = (res or {}).get("traceback")
    check("error_type=quality", isinstance(tb, dict) and tb.get("error_type") == "quality", str(tb)[:200])
    check("rejected_result 동봉", "rejected_result" in (res or {}), str((res or {}).keys()))
    check("quality_retried=False", res.get("quality_retried") is False)


def c3_pipe():
    print("C3. 파이프가 quality 트레이스백 승계")
    iq._call_judge = FakeJudge('{"pass": false, "reason": "기준 미달"}')
    with actor_context(agent_id="test", origin="test"):
        env = execute_pipeline(ibl_parse(
            '[table:take]{items: [{"a": 1}], n: 1, criteria: "행이 5개"} >> [table:take]{n: 1}'), ".")
    tb = env.get("traceback")
    check("파이프 실패", env.get("success") is False, str(env)[:200])
    check("traceback 승계", isinstance(tb, dict) and tb.get("error_type") == "quality", str(tb)[:250])
    if isinstance(tb, dict):
        f0 = (tb.get("frames") or [{}])[0]
        check("pipeline 프레임(step 1)", f0.get("kind") == "pipeline" and f0.get("step") == 1, str(f0))


def c4_unjudgeable():
    print("C4. 판정 불능 → 통과 + 신고")
    judge = FakeJudge("모호한 산문 응답이라 판정 토큰이 없다")
    res = _run_step(_step("table", "take", items=[{"a": 1}], n=1, criteria="아무거나"), judge)
    obj = json.loads(res) if isinstance(res, str) else res
    check("unjudged 신고", isinstance(obj, dict) and obj.get("criteria_verdict") == "unjudged",
          str(obj)[:250])
    check("note 존재", bool((obj or {}).get("criteria_note")))


def _ai_tool_input():
    return {"_node": "table", "action": "ai",
            "params": {"instruction": "광고 제거", "criteria": "광고 행이 없다"}}


def c5_retry_pass():
    print("C5. AI 낱말 재시도 → 통과")
    ti = _ai_tool_input()
    criteria = ti["params"].pop("criteria")
    judge = FakeJudge('{"pass": false, "reason": "광고 행이 남아 있음"}', J_PASS)
    iq._call_judge = judge
    reruns = []

    def rerun(ti2):
        reruns.append(ti2)
        return json.dumps({"success": True, "items": [{"a": 1}], "rows_in": 2, "rows_out": 1},
                          ensure_ascii=False)

    first = json.dumps({"success": True, "items": [{"a": 1}, {"광고": 1}]}, ensure_ascii=False)
    res = iq.apply_criteria(criteria, first, ti, "table", "ai", ".", "test", rerun)
    obj = json.loads(res) if isinstance(res, str) else res
    check("재실행 1회", len(reruns) == 1, str(len(reruns)))
    check("피드백이 instruction 에 얹힘", reruns and "[품질 재시도]" in
          (reruns[0].get("params") or {}).get("instruction", ""),
          str(reruns[0])[:200] if reruns else "")
    check("pass_after_retry", isinstance(obj, dict) and obj.get("criteria_verdict") == "pass_after_retry",
          str(obj)[:250])
    check("_criteria_retried 표지", obj.get("_criteria_retried") is True)
    check("판정자 2회", len(judge.prompts) == 2, str(len(judge.prompts)))


def c6_retry_fail():
    print("C6. 재시도도 미달 → quality 실패")
    ti = _ai_tool_input()
    criteria = ti["params"].pop("criteria")
    iq._call_judge = FakeJudge('{"pass": false, "reason": "여전히 광고"}',
                               '{"pass": false, "reason": "그대로 광고"}')
    res = iq.apply_criteria(criteria, '{"success": true, "items": []}', ti, "table", "ai",
                            ".", "test", lambda ti2: '{"success": true, "items": []}')
    check("quality 실패", isinstance(res, dict) and res.get("success") is False
          and res.get("criteria_verdict") == "fail", str(res)[:250])
    check("quality_retried=True", res.get("quality_retried") is True)
    check("최종 사유=재판정 사유", "그대로 광고" in (res.get("error") or ""), res.get("error"))


def c7_declared_collision():
    print("C7. 액션 선언 criteria 는 가로채지 않음")
    ti = {"_node": "engines", "action": "image_read",
          "params": {"op": "critic", "path": "/tmp/x.png", "criteria": "제목이 보인다"}}
    got = iq.pop_criteria(ti)
    check("pop 안 함", got is None and ti["params"].get("criteria") == "제목이 보인다",
          f"got={got}, params={ti['params']}")
    ti2 = {"_try": True, "body": [], "params": {"criteria": "x"}}
    check("블록엔 미적용", iq.pop_criteria(ti2) is None and ti2["params"].get("criteria") == "x")


def c8_honesty():
    print("C8. 정직 표지 전파")
    m = markers_of({"success": True, "_criteria_retried": True})
    check("_criteria_retried ∈ markers_of", isinstance(m, dict) and m.get("_criteria_retried") is True,
          str(m))


def c9_distill_exclusion_chain():
    print("C9. 증류 배제 사슬 — quality 실패 봉투는 is_error_result=True")
    from ibl.workflow_engine import is_error_result
    fail = {"success": False, "error": "criteria 미달: x", "criteria_verdict": "fail"}
    check("dict 실패 판정", is_error_result(fail) is True)
    check("JSON 문자열 실패 판정", is_error_result(json.dumps(fail, ensure_ascii=False)) is True)


def c10_quality_of_result():
    print("C10. 증류 셋째 신호 — 재시도-통과 표지 추출")
    from agent_pipeline import _quality_of_result
    # 단독 실행: 마킹된 결과 dict (JSON 문자열)
    single = json.dumps({"success": True, "message": "보고", "criteria_verdict": "pass_after_retry",
                         "criteria_feedback": "수치 누락", "_criteria_retried": True},
                        ensure_ascii=False)
    q, fb = _quality_of_result(single)
    check("단독 결과에서 추출", q == "pass_after_retry" and fb == "수치 누락", f"{q}, {fb}")
    # 파이프 봉투: results[] step 기록(_quality_meta 승격 모양)
    env = json.dumps({"success": True, "results": [
        {"step": 1, "node": "table", "action": "brief",
         "criteria_verdict": "pass_after_retry", "criteria_feedback": "3문장 초과"}],
        "final_result": "보고"}, ensure_ascii=False)
    q2, fb2 = _quality_of_result(env)
    check("파이프 봉투에서 추출", q2 == "pass_after_retry" and fb2 == "3문장 초과", f"{q2}, {fb2}")
    # 표지 없는 성공 — (None, None)
    check("무표지=무신호", _quality_of_result('{"success": true, "items": []}') == (None, None))


def _battery():
    c1_pass()
    c2_nonai_fail()
    c3_pipe()
    c4_unjudgeable()
    c5_retry_pass()
    c6_retry_fail()
    c7_declared_collision()
    c8_honesty()
    c9_distill_exclusion_chain()
    c10_quality_of_result()


def test_criteria_배터리_전건이_pytest_에도_보인다():
    """다리 시험 (단일 러너 규약 test_single_runner R1) — 스크립트형 배터리를 pytest 가
    0건으로 세지 않게, 전 건을 한 test 로 감싼다."""
    _battery()
    assert FAIL == 0, f"{FAIL}건 실패 — python3 backend/test_ibl_criteria_contract.py 로 상세"


if __name__ == "__main__":
    _battery()
    print(f"\n{PASS} ok / {FAIL} fail")
    sys.exit(1 if FAIL else 0)
