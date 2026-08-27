"""IBL 트레이스백 회귀 테스트 (2026-08-27, docs/IBL_TRACEBACK_HANDOFF.md)

실패한 문장이 "어디서(frames)·왜(error/py_tail)·무슨 입력으로(input)" 죽었는지를
구조화된 traceback 하나로 나르는 경계 규약의 재현 케이스.

    T1. 파이프 중간 step 실패 → frames[0]=pipeline(step·node·action) + input 요약
    T2. each 행별 실패 → errors[i]._traceback 에 each 프레임 (경계 규약에 예외 없음)
    T3. 동일 오류 반복 → 무거운 상세는 첫 행에만, 이후 detail_at 참조(침묵 접기 금지)
    T4. each 전량 실패가 파이프를 죽일 때 → pipeline→each 프레임 사슬 승계
    T5. 문법 오류 → error_type=syntax
    T6. 병렬 가지 실패 → branches_failed[i].traceback 에 parallel 프레임
    T7. try 블록(catch 없음) 실패 → block 프레임
    U1~U3. ibl_traceback 단위: py_tail_of / nested 승계 / fold_heavy

실행: python3 backend/test_ibl_traceback.py
"""
import json
import sys

sys.path.insert(0, __file__.rsplit('/', 1)[0])
import boot_paths  # noqa: F401 — 층 디렉토리 등재

from thread_context import actor_context  # noqa: E402
from ibl.workflow_engine import execute_pipeline  # noqa: E402
from ibl.ibl_parser import parse as ibl_parse  # noqa: E402
from ibl.ibl_traceback import build_tb, push_frame, tb_of, py_tail_of, fold_heavy  # noqa: E402

PASS = FAIL = 0


def check(name, cond, detail=""):
    global PASS, FAIL
    if cond:
        PASS += 1
        print(f"  ok  {name}")
    else:
        FAIL += 1
        print(f"  FAIL {name} — {detail}")


def run(code):
    with actor_context(agent_id="test", origin="test"):
        return execute_pipeline(ibl_parse(code), ".")


ROWS = '{items: [{"이름": "가"}, {"이름": "나"}]}'


def t1_pipeline_frame():
    print("T1. 파이프 중간 step 실패")
    env = run('[table:take]{items: [{"a": 1}], n: 1} >> [table:select]{columns: ["없는열"]}')
    tb = env.get("traceback")
    check("실패 봉투에 traceback", isinstance(tb, dict), json.dumps(env, ensure_ascii=False)[:300])
    if not isinstance(tb, dict):
        return
    f0 = (tb.get("frames") or [{}])[0]
    check("frames[0]=pipeline step 2", f0.get("kind") == "pipeline" and f0.get("step") == 2, str(f0))
    check("node:action 위치", f0.get("node") == "table" and f0.get("action") == "select", str(f0))
    check("error_type 존재", tb.get("error_type") in ("tool_error", "exception"), str(tb.get("error_type")))
    check("입력 통화 요약(input)", isinstance(tb.get("input"), dict) and "shape" in tb["input"],
          str(tb.get("input")))
    # 실패 step 기록에도 남는다(다이어트 생존 경로)
    recs = [r for r in env.get("results", []) if isinstance(r, dict) and r.get("traceback")]
    check("results[] 실패 step 기록에도 traceback", bool(recs))


def t2_each_rows():
    print("T2/T3. each 행별 실패 + 무거운 상세 접기")
    env = run(f'[table:take]{{items: {ROWS[8:-1]}, n: 2}} >> '
              f'[table:each]{{do: "[table:select]{{columns: [\\"없는열\\"]}}"}}')
    # each 는 부분/전량 실패 봉투를 낸다 — 여기선 전량 실패
    final = env.get("final_result")
    obj = json.loads(final) if isinstance(final, str) else final
    errs = (obj or {}).get("errors") if isinstance(obj, dict) else None
    if not errs:  # 봉투 위치가 최상위일 수도(성공 파이프면 final 이 each 봉투)
        errs = env.get("errors")
    check("errors[] 존재", isinstance(errs, list) and len(errs) == 2,
          json.dumps(env, ensure_ascii=False)[:400])
    if not (isinstance(errs, list) and errs):
        return
    tb0 = errs[0].get("_traceback")
    check("행1 _traceback", isinstance(tb0, dict), str(errs[0])[:200])
    if isinstance(tb0, dict):
        kinds = [f.get("kind") for f in tb0.get("frames", [])]
        check("each 프레임 존재", "each" in kinds, str(kinds))
        e_frame = next((f for f in tb0["frames"] if f.get("kind") == "each"), {})
        check("each item/of", e_frame.get("item") == 1 and e_frame.get("of") == 2, str(e_frame))
        check("do 안 pipeline 프레임 승계", "pipeline" in kinds, str(kinds))
    tb1 = (errs[1] or {}).get("_traceback")
    check("행2 동일 오류 detail_at=1", isinstance(tb1, dict) and tb1.get("detail_at") == 1,
          str(tb1)[:200])


def t4_each_kills_pipe():
    print("T4. each 전량 실패 → 파이프 트레이스백 사슬")
    env = run(f'[table:take]{{items: {ROWS[8:-1]}, n: 2}} >> '
              f'[table:each]{{do: "[table:select]{{columns: [\\"없는열\\"]}}"}} >> [table:take]{{n: 1}}')
    tb = env.get("traceback")
    check("success=False", env.get("success") is False, str(env.get("success")))
    check("traceback 존재", isinstance(tb, dict), json.dumps(env, ensure_ascii=False)[:300])
    if isinstance(tb, dict):
        kinds = [f.get("kind") for f in tb.get("frames", [])]
        check("pipeline→each 사슬", kinds[:2] == ["pipeline", "each"], str(kinds))


def t5_syntax():
    print("T5. 문법 오류")
    with actor_context(agent_id="test", origin="test"):
        env = execute_pipeline(["[[[망가진"], ".")
    tb = env.get("traceback")
    check("syntax traceback", isinstance(tb, dict) and tb.get("error_type") == "syntax", str(tb)[:200])


def t6_parallel():
    print("T6. 병렬 가지 실패")
    env = run('[table:select]{columns: ["x"]} & [table:take]{items: [{"a": 1}], n: 1}')
    bf = None
    for r in env.get("results", []):
        if isinstance(r, dict) and r.get("branches_failed"):
            bf = r["branches_failed"]
    bf = bf or env.get("branches_failed")
    if isinstance(bf, list) and bf and isinstance(bf[0], dict) and "failed" in bf[0]:
        bf = bf[0]["failed"]  # _seq 승격 모양
    check("branches_failed 존재", isinstance(bf, list) and bf, json.dumps(env, ensure_ascii=False)[:400])
    if isinstance(bf, list) and bf:
        btb = bf[0].get("traceback")
        check("가지 traceback", isinstance(btb, dict), str(bf[0])[:200])
        if isinstance(btb, dict):
            kinds = [f.get("kind") for f in btb.get("frames", [])]
            check("parallel 프레임", "parallel" in kinds, str(kinds))


def t7_try_block():
    print("T7. try 블록(catch 없음) 실패")
    env = run('[try]{[table:select]{columns: ["없는열"], items: [{"a": 1}]}} '
              '[finally]{[table:take]{items: [{"a": 1}], n: 1}}')
    tb = env.get("traceback")
    if not isinstance(tb, dict):  # 블록 결과가 final 에만 실렸을 수도
        final = env.get("final_result")
        obj = json.loads(final) if isinstance(final, str) else final
        tb = (obj or {}).get("traceback") if isinstance(obj, dict) else None
    check("traceback 존재", isinstance(tb, dict), json.dumps(env, ensure_ascii=False)[:400])
    if isinstance(tb, dict):
        kinds = [f.get("kind") for f in tb.get("frames", [])]
        check("block 프레임", "block" in kinds, str(kinds))


def u_units():
    print("U1~U3. 단위")
    try:
        raise ValueError("보기")
    except ValueError as e:
        tail = py_tail_of(e)
    check("py_tail 꼬리+오류문", tail and tail[-1].startswith("ValueError") and ":" in tail[0], str(tail))

    inner = build_tb("안쪽 오류", "exception", py_tail=["x.py:1 in f", "E: x"])
    outer = build_tb("바깥 문구", nested=inner,
                     frame={"kind": "pipeline", "step": 3, "of": 5})
    check("nested 승계 — error 안쪽 유지", outer["error"] == "안쪽 오류", outer["error"])
    check("nested 승계 — 프레임 앞붙임", outer["frames"][0]["step"] == 3, str(outer["frames"]))
    check("원본 불변", inner["frames"] == [], str(inner["frames"]))

    seen = {}
    a = build_tb("같은 오류", "exception", py_tail=["t"])
    b = build_tb("같은 오류", "exception", py_tail=["t"])
    check("fold 첫 발생=원형", fold_heavy(a, seen, 1) is False and "py_tail" in a, str(a))
    check("fold 반복=참조", fold_heavy(b, seen, 2) is True and b.get("detail_at") == 1
          and "py_tail" not in b, str(b))

    check("tb_of 는 사본", (lambda r: (lambda t: t is not r["traceback"])(tb_of(r)))(
        {"traceback": build_tb("e")}))


def test_트레이스백_배터리_전건이_pytest_에도_보인다():
    """다리 시험 (2026-08-27, 단일 러너 규약 test_single_runner R1) — 이 배터리는
    스크립트형(check/PASS/FAIL)이라 pytest 가 0건을 수집했고, CI 초록이 이 파일을
    조용히 지나치고 있었다(27·28회차 거짓 초록과 같은 부류). 전 케이스를 한 시험으로
    노출한다 — 실패 상세는 check() 가 stdout 에 이미 찍는다."""
    global PASS, FAIL
    PASS = FAIL = 0
    u_units()
    t1_pipeline_frame()
    t2_each_rows()
    t4_each_kills_pipe()
    t5_syntax()
    t6_parallel()
    t7_try_block()
    assert FAIL == 0, f"{FAIL}건 실패 / {PASS}건 통과 — 상세는 stdout 의 FAIL 줄"
    assert PASS > 0, "0건 통과는 통과가 아니라 '아무것도 안 봤다'이다"


if __name__ == "__main__":
    # 러너는 하나 — pytest 에 위임 (test_single_runner 규약).
    import pytest
    sys.exit(pytest.main([__file__] + sys.argv[1:]))
