"""[self:workflow]{op:"run", params} 침묵 유실 수리 회귀 테스트 (2026-08-17 B8)

desc("run — … + params 옵션(문장 안 $변수에 주입)")가 선언만 하고 구현이 없어,
호출자 params 가 조용히 무시되고 워크플로우가 고정값으로 돌아 거짓 정상을 냈다.

    W1. 저장본 run + params → 문장 안 미할당 $변수에 실제 주입
    W2. 통짜 참조("$n")는 원시 타입 보존, 문자열 임베드는 str/JSON
    W3. 대응 $변수 없는 params 키 → 정직 경고(params_warning)
    W4. 예약 이름($it/$items/each as) → 주입 금지 + 경고, each 의 $it 는 보존
    W5. 즉석 실행(do/steps·pipeline) + params — 저장본과 동일 지원
    W6. 문장 안 할당($x = …)이 호출자 params 보다 항상 이긴다(파스 후 주입)
    W7. params 비객체(JSON 아님) → 침묵 무시 대신 정직 거절 / JSON 문자열은 관용 수용
    W8. params 없으면 기존 동작 그대로(무회귀 — 리터럴 $변수 보존, 새 필드 없음)

실행: python3 backend/test_workflow_params.py
"""
import sys

sys.path.insert(0, __file__.rsplit('/', 1)[0])
import boot_paths  # noqa: F401 — 층 디렉토리 등재

import ibl_engine  # noqa: E402
import workflow_engine  # noqa: E402
from workflow_engine import execute_workflow_action  # noqa: E402


class _FakeEngine:
    """ibl_engine.execute_ibl 을 가로채 tool_input 을 기록하고 성공 응답."""

    def __init__(self):
        self.calls = []
        self._orig = None

    def __enter__(self):
        self._orig = ibl_engine.execute_ibl

        def _fake(tool_input, project_path, agent_id=None, **kw):
            self.calls.append(tool_input)
            return {"success": True, "echo": tool_input.get("params", {})}

        ibl_engine.execute_ibl = _fake
        return self

    def __exit__(self, *a):
        ibl_engine.execute_ibl = self._orig


def _save_tmp_workflow(wf_id, data):
    data = dict(data)
    data["id"] = wf_id
    workflow_engine.save_workflow(data)
    return wf_id


def _cleanup(wf_id):
    workflow_engine.delete_workflow(wf_id)


def test_w1_saved_run_injects_params():
    wf_id = _save_tmp_workflow("_t_params_w1", {
        "name": "_t_params_w1",
        "steps": ['[sense:web_search]{query: "$city 맛집"}'],
    })
    try:
        with _FakeEngine() as eng:
            out = execute_workflow_action("workflow", {
                "op": "run", "workflow_id": wf_id, "params": {"city": "청주"},
            }, ".")
        assert out.get("success"), out
        q = eng.calls[0]["params"]["query"]
        assert q == "청주 맛집", f"query={q!r} — '$city 맛집' 그대로면 B8 회귀"
        assert out.get("params_injected") == ["city"], out.get("params_injected")
        assert "params_warning" not in out, out
    finally:
        _cleanup(wf_id)
    print("W1 OK — 저장본 run 이 params 를 $변수에 주입")


def test_w2_type_preservation():
    wf_id = _save_tmp_workflow("_t_params_w2", {
        "name": "_t_params_w2",
        "steps": ['[table:take]{n: "$count", note: "상한 $count 건"}'],
    })
    try:
        with _FakeEngine() as eng:
            out = execute_workflow_action("workflow", {
                "op": "run", "workflow_id": wf_id, "params": {"count": 5},
            }, ".")
        assert out.get("success"), out
        p = eng.calls[0]["params"]
        assert p["n"] == 5 and isinstance(p["n"], int), f"통짜 참조 타입 소실: {p['n']!r}"
        assert p["note"] == "상한 5 건", p["note"]
    finally:
        _cleanup(wf_id)
    print("W2 OK — 통짜 참조 원시 타입 보존 + 문자열 임베드")


def test_w3_unmatched_param_warns():
    wf_id = _save_tmp_workflow("_t_params_w3", {
        "name": "_t_params_w3",
        "steps": ['[sense:web_search]{query: "$city 맛집"}'],
    })
    try:
        with _FakeEngine():
            out = execute_workflow_action("workflow", {
                "op": "run", "workflow_id": wf_id,
                "params": {"city": "청주", "없는변수": 1},
            }, ".")
        assert out.get("success"), out
        warn = out.get("params_warning", "")
        assert "없는변수" in warn, f"미대응 키 침묵 통과: {out}"
        assert out.get("params_injected") == ["city"], out
    finally:
        _cleanup(wf_id)
    print("W3 OK — 대응 $변수 없는 params 키는 정직 경고")


def test_w4_reserved_names_protected():
    wf_id = _save_tmp_workflow("_t_params_w4", {
        "name": "_t_params_w4",
        "steps": ['[table:each]{do: "[self:notify_user]{message: \'$it.title\'}", as: "it"}'],
    })
    try:
        with _FakeEngine() as eng:
            out = execute_workflow_action("workflow", {
                "op": "run", "workflow_id": wf_id, "params": {"it": "덮어쓰기시도"},
            }, ".")
        assert out.get("success"), out
        do = eng.calls[0]["params"]["do"]
        assert "$it.title" in do, f"$it 이 params 에 침식됨: {do!r}"
        assert "예약 이름" in out.get("params_warning", ""), out
    finally:
        _cleanup(wf_id)
    print("W4 OK — $it/예약 이름 주입 금지 + 경고, each 문장 보존")


def test_w5_inline_run_injects_params():
    with _FakeEngine() as eng:
        out = execute_workflow_action("workflow", {
            "op": "run",
            "steps": ['[sense:weather]{city: "$도시"}'],
            "params": {"도시": "오송"},
        }, ".")
    assert out.get("success"), out
    assert eng.calls[0]["params"]["city"] == "오송", eng.calls[0]
    # run_pipeline 내부 진입점도 동일
    with _FakeEngine() as eng2:
        out2 = execute_workflow_action("run_pipeline", {
            "pipeline": '[sense:weather]{city: "$도시"}',
            "params": {"도시": "청주"},
        }, ".")
    assert out2.get("success"), out2
    assert eng2.calls[0]["params"]["city"] == "청주", eng2.calls[0]
    print("W5 OK — 즉석 실행(steps·pipeline)도 params 주입 일관")


def test_w6_assignment_wins_over_params():
    wf_id = _save_tmp_workflow("_t_params_w6", {
        "name": "_t_params_w6",
        "pipeline": ('$r = [sense:web_search]{query: "AI"}\n'
                     '[others:channel_send]{body: "$r"}'),
    })
    try:
        with _FakeEngine() as eng:
            out = execute_workflow_action("workflow", {
                "op": "run", "workflow_id": wf_id, "params": {"r": "클로버"},
            }, ".")
        assert out.get("success"), out
        body = eng.calls[1]["params"]["body"]
        # 파서가 $r 을 {{_step_0_result}} 로 이미 치환 → step 결과가 주입돼야 함
        assert "클로버" not in str(body), f"호출자 params 가 step 바인딩을 침식: {body!r}"
        warn = out.get("params_warning", "")
        assert "'r'" in warn or '"r"' in warn or "[‘r’]" in warn or "['r']" in warn, \
            f"할당 변수와 겹친 키 침묵 통과: {out}"
    finally:
        _cleanup(wf_id)
    print("W6 OK — 문장 안 할당이 params 보다 이김(+미대응 경고)")


def test_w7_bad_params_rejected():
    with _FakeEngine():
        out = execute_workflow_action("workflow", {
            "op": "run", "steps": ['[sense:weather]{}'], "params": [1, 2],
        }, ".")
    assert "error" in out and "객체" in out["error"], f"비객체 params 침묵 통과: {out}"
    # JSON 문자열은 관용 수용
    with _FakeEngine() as eng:
        out2 = execute_workflow_action("workflow", {
            "op": "run", "steps": ['[sense:weather]{city: "$c"}'],
            "params": '{"c": "서울"}',
        }, ".")
    assert out2.get("success"), out2
    assert eng.calls[0]["params"]["city"] == "서울", eng.calls[0]
    print("W7 OK — 비객체 params 정직 거절 / JSON 문자열 관용 수용")


def test_w8_no_params_no_regression():
    wf_id = _save_tmp_workflow("_t_params_w8", {
        "name": "_t_params_w8",
        "steps": ['[sense:web_search]{query: "$city 맛집"}'],
    })
    try:
        with _FakeEngine() as eng:
            out = execute_workflow_action("workflow", {
                "op": "run", "workflow_id": wf_id,
            }, ".")
        assert out.get("success"), out
        assert eng.calls[0]["params"]["query"] == "$city 맛집", eng.calls[0]
        assert "params_injected" not in out and "params_warning" not in out, out
    finally:
        _cleanup(wf_id)
    print("W8 OK — params 없으면 기존 동작 그대로(무회귀)")


if __name__ == "__main__":
    print("=== workflow run params 주입 회귀 테스트 (W1~W8) ===\n")
    test_w1_saved_run_injects_params()
    test_w2_type_preservation()
    test_w3_unmatched_param_warns()
    test_w4_reserved_names_protected()
    test_w5_inline_run_injects_params()
    test_w6_assignment_wins_over_params()
    test_w7_bad_params_rejected()
    test_w8_no_params_no_regression()
    print("\n=== 전부 통과 ===")
