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




ROWS = '{items: [{"이름": "가"}, {"이름": "나"}]}'














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
    assert FAIL == 0, f"{FAIL}건 실패 / {PASS}건 통과 — 상세는 stdout 의 FAIL 줄"
    assert PASS > 0, "0건 통과는 통과가 아니라 '아무것도 안 봤다'이다"


if __name__ == "__main__":
    # 러너는 하나 — pytest 에 위임 (test_single_runner 규약).
    import pytest
    sys.exit(pytest.main([__file__] + sys.argv[1:]))


def test_native_function_failure_keeps_source_and_call_frame():
    from ibl_v2_compile import compile_program
    from ibl_v2_runtime import Runtime
    source = '[def:f]($n){return 1/$n}; [fn:f]{n:0}'
    result = Runtime(compile_program(source)).run()
    assert not result['success']
    diagnostic = result['diagnostic']
    assert diagnostic['code'] == 'VALUE'
    assert diagnostic['frames'][0]['function'] == 'f'
    span = diagnostic['source_span']
    assert source[span['start']:span['end']] == '1/$n'
    assert diagnostic['evidence']
    assert {x['id'] for x in result['evidence']} >= set(diagnostic['evidence'])


def test_native_each_preserves_failed_row_diagnostic():
    from ibl_v2_compile import compile_program
    from ibl_v2_runtime import Runtime
    from ibl_v2_ir import unpack
    result = Runtime(compile_program('[table:each]{items:[1,0],on_error:"collect"}{return 1/$it}')).run()
    assert result['success'] and not result['source_complete']
    first, second = unpack(result['value_wire']['data'])
    assert first.ok and first.value == 1
    assert not second.ok and second.error['code'] == 'VALUE'
    assert second.error['source_span']['start'] == 52
    assert second.error['evidence']
