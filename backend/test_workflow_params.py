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
    W8. 저장본 인자 누락 → 정직 거절 (2026-08-22 승격 — 아래 참조)

2026-08-22 시그니처·재귀 가드 (M-sig / M-rec):
    W8 은 원래 "params 없으면 리터럴 $변수 보존"을 무회귀로 못박고 있었다. 그 동작이
    바로 결함이었다 — 인자 없이 부른 저장본이 "$city 맛집" 을 그대로 검색어로 삼고도
    success 로 완주했다(스코프 문제가 아니라 시그니처 부재의 증상). 저장본에는 save 라는
    "선언하는 순간"이 있으므로 정직 거절로 승격한다. 무인자 워크플로우의 무회귀는 유지.

    W9.  params_default — 기본값이 인자를 채우고, 호출자 params 가 기본값을 이긴다
    W10. 자기 순환 워크플로우 → 정직 거절 (실경로: 가짜 엔진 없이 engine 왕복)
    W11. 상호 순환 A→B→A → 정직 거절
    W12. 워크플로우 중첩 깊이 상한(MAX_WORKFLOW_DEPTH)
    W13. 즉석 실행의 미채움 자유 변수 → 경고(거절 아님 — 선언하는 순간이 없다)
    W14. save 가 시그니처를 계산·저장·보고하고 list 가 노출
    W15. 스케줄러 run_workflow 액션이 action_params.params 를 엔진에 통과 (2026-08-22)
    W16. 몸통이 스스로 할당한 변수는 시그니처가 아니다 — 시그니처 = 사용 − 할당 (B22-1)

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
        "steps": ['[sense:search]{query: "$city 맛집"}'],
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
        "steps": ['[sense:search]{query: "$city 맛집"}'],
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
        "pipeline": ('$r = [sense:search]{query: "AI"}\n'
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


def test_w8_missing_arg_rejected():
    """인자를 요구하는 저장본을 인자 없이 부르면 정직 거절 (2026-08-22 승격)."""
    wf_id = _save_tmp_workflow("_t_params_w8", {
        "name": "_t_params_w8",
        "steps": ['[sense:search]{query: "$city 맛집"}'],
    })
    try:
        with _FakeEngine() as eng:
            out = execute_workflow_action("workflow", {
                "op": "run", "workflow_id": wf_id,
            }, ".")
        assert not out.get("success"), f"인자 누락이 success 로 완주: {out}"
        assert out.get("params_missing") == ["city"], out
        assert out.get("params_required") == ["city"], out
        assert "$city" in out.get("error", ""), out
        assert not eng.calls, f"거절해 놓고 몸통을 실행함: {eng.calls}"
    finally:
        _cleanup(wf_id)

    # 무인자 워크플로우는 무회귀 — params 없이 그대로 돌고 새 필드도 붙지 않는다.
    wf2 = _save_tmp_workflow("_t_params_w8b", {
        "name": "_t_params_w8b",
        "steps": ['[sense:search]{query: "고정 검색어"}'],
    })
    try:
        with _FakeEngine() as eng:
            out2 = execute_workflow_action("workflow", {
                "op": "run", "workflow_id": wf2,
            }, ".")
        assert out2.get("success"), out2
        assert eng.calls[0]["params"]["query"] == "고정 검색어", eng.calls[0]
        assert "params_injected" not in out2 and "params_warning" not in out2, out2
        assert "params_required" not in out2, out2
    finally:
        _cleanup(wf2)
    print("W8 OK — 인자 누락 정직 거절 / 무인자 워크플로우 무회귀")


# === 2026-08-22 시그니처 (M-sig) ===

def test_w9_params_default():
    wf_id = _save_tmp_workflow("_t_params_w9", {
        "name": "_t_params_w9",
        "steps": ['[sense:search]{query: "$city 맛집", note: "$n 건"}'],
        "params_default": {"city": "청주", "n": 5},
    })
    try:
        # 기본값만으로 실행된다 — 거절 없음
        with _FakeEngine() as eng:
            out = execute_workflow_action("workflow", {
                "op": "run", "workflow_id": wf_id,
            }, ".")
        assert out.get("success"), out
        assert eng.calls[0]["params"]["query"] == "청주 맛집", eng.calls[0]

        # 호출자 params 가 기본값을 이긴다
        with _FakeEngine() as eng2:
            out2 = execute_workflow_action("workflow", {
                "op": "run", "workflow_id": wf_id, "params": {"city": "오송"},
            }, ".")
        assert out2.get("success"), out2
        assert eng2.calls[0]["params"]["query"] == "오송 맛집", eng2.calls[0]
    finally:
        _cleanup(wf_id)
    print("W9 OK — params_default 가 인자를 채우고 호출자가 이김")


def test_w14_signature_saved_and_listed():
    out = execute_workflow_action("workflow", {
        "op": "save", "workflow_id": "_t_params_w14", "name": "_t_params_w14",
        "do": '[sense:search]{query: "$city 맛집"} >> [table:take]{n: "$count"}',
    }, ".")
    try:
        assert out.get("success"), out
        assert out.get("params_required") == ["city", "count"], out
        assert "$city" in out.get("message", ""), out["message"]

        wf = execute_workflow_action("workflow", {"op": "get", "workflow_id": "_t_params_w14"}, ".")
        assert wf.get("params_required") == ["city", "count"], wf

        listed = execute_workflow_action("workflow", {"op": "list"}, ".")["workflows"]
        row = next(w for w in listed if w["id"] == "_t_params_w14")
        assert row.get("params_required") == ["city", "count"], row
    finally:
        _cleanup("_t_params_w14")

    # ★한글 접미 함정 (2026-08-22 발견): 파서(_VAR_REF_PATTERN=\$(\w+))·주입기·시그니처가
    # 모두 \w 경계라 `$n건` 은 변수 `n` + 글자 `건` 이 아니라 **변수 `n건`** 이다.
    # 셋이 일관되므로 오동작은 아니지만, 한글에서는 조사·단위가 이름에 먹힌다.
    # 시그니처가 save 시점에 그걸 드러내는 것이 유일한 방어선이라 회귀로 못박는다.
    out2 = execute_workflow_action("workflow", {
        "op": "save", "workflow_id": "_t_params_w14b", "name": "_t_params_w14b",
        "do": '[table:take]{n: "$n건"}',
    }, ".")
    try:
        assert out2.get("params_required") == ["n건"], \
            f"한글 접미 경계가 파서와 어긋남: {out2.get('params_required')}"
    finally:
        _cleanup("_t_params_w14b")
    print("W14 OK — save 가 시그니처를 계산·저장·보고 / list 노출 / 한글 접미 경계 일관")


def test_w13_inline_unfilled_warns_not_rejects():
    """즉석 실행은 '선언하는 순간'이 없다 — 거절 대신 정직 경고."""
    with _FakeEngine() as eng:
        out = execute_workflow_action("workflow", {
            "op": "run", "steps": ['[sense:search]{query: "$city 맛집"}'],
        }, ".")
    assert out.get("success"), out
    assert eng.calls[0]["params"]["query"] == "$city 맛집", eng.calls[0]
    assert "$city" in out.get("params_warning", ""), \
        f"미채움 자유 변수가 침묵 통과: {out}"
    print("W13 OK — 즉석 실행의 미채움 자유 변수는 경고(거절 아님)")


# === 2026-08-22 재귀·순환 가드 (M-rec) ===
# 여기부터는 _FakeEngine 을 쓰지 않는다 — 스택이 step → execute_ibl → params → 다음
# workflow run 으로 이어지는지가 검증 대상이라, 실제 엔진 왕복이 아니면 의미가 없다.

def test_w10_self_cycle_rejected():
    wf_id = _save_tmp_workflow("_t_rec_self", {
        "name": "_t_rec_self",
        "steps": ['[self:workflow]{op: "run", workflow_id: "_t_rec_self"}'],
    })
    try:
        out = execute_workflow_action("workflow", {"op": "run", "workflow_id": wf_id}, ".")
        assert not out.get("success"), f"자기 순환이 완주: {out}"
        assert "순환" in str(out.get("error", "")), out
        assert f"{wf_id} → {wf_id}" in str(out.get("error", "")), out
    finally:
        _cleanup(wf_id)
    print("W10 OK — 자기 순환 워크플로우 정직 거절(경로 표시)")


def test_w11_mutual_cycle_rejected():
    a = _save_tmp_workflow("_t_rec_a", {
        "name": "_t_rec_a",
        "steps": ['[self:workflow]{op: "run", workflow_id: "_t_rec_b"}'],
    })
    b = _save_tmp_workflow("_t_rec_b", {
        "name": "_t_rec_b",
        "steps": ['[self:workflow]{op: "run", workflow_id: "_t_rec_a"}'],
    })
    try:
        out = execute_workflow_action("workflow", {"op": "run", "workflow_id": a}, ".")
        assert not out.get("success"), f"상호 순환이 완주: {out}"
        err = str(out.get("error", ""))
        assert "순환" in err and "_t_rec_a → _t_rec_b → _t_rec_a" in err, err
    finally:
        _cleanup(a)
        _cleanup(b)
    print("W11 OK — 상호 순환(A→B→A) 정직 거절")


def test_w12_depth_cap():
    # 단위: 스택이 상한에 닿으면 순환이 아니어도 거절
    stack = [f"w{i}" for i in range(workflow_engine.MAX_WORKFLOW_DEPTH)]
    pushed, err = workflow_engine._wf_push(stack, "w_last")
    assert pushed is None and "중첩 깊이 상한" in err, (pushed, err)

    # 실경로: 순환 없는 사슬 w0→w1→…→wN 이 상한에서 끊긴다
    n = workflow_engine.MAX_WORKFLOW_DEPTH + 2
    ids = [f"_t_rec_chain{i}" for i in range(n)]
    for i, wid in enumerate(ids):
        body = (f'[self:workflow]{{op: "run", workflow_id: "{ids[i + 1]}"}}'
                if i + 1 < n else '[self:time]{}')
        _save_tmp_workflow(wid, {"name": wid, "steps": [body]})
    try:
        out = execute_workflow_action("workflow", {"op": "run", "workflow_id": ids[0]}, ".")
        assert not out.get("success"), f"상한을 넘은 사슬이 완주: {out}"
        assert "중첩 깊이 상한" in str(out.get("error", "")), out
    finally:
        for wid in ids:
            _cleanup(wid)
    print(f"W12 OK — 워크플로우 중첩 깊이 상한({workflow_engine.MAX_WORKFLOW_DEPTH})")


# === 스케줄 표면 — 저장된 인자를 실행 시점까지 나르는가 (2026-08-22) ===
# 시그니처 도입 뒤, 스케줄러의 run_workflow 액션이 workflow_id 만 읽고 params 를 버려
# "인자를 요구하는 워크플로우는 스케줄에 걸면 실행 시점에 반드시 실패" 하는 구멍이 있었다.


class _FakeScheduler:
    """CalendarActionsMixin._action_run_workflow 만 떼어 쓰는 최소 숙주(_log 만 요구)."""

    def __init__(self):
        import calendar_actions
        self.logs = []
        self._run = calendar_actions.CalendarActionsMixin._action_run_workflow

    def _log(self, msg):
        self.logs.append(str(msg))

    def run(self, action_params):
        return self._run(self, {"title": "_t_sched", "action_params": action_params})


def test_w15_scheduler_passes_params():
    wf_id = _save_tmp_workflow("_t_params_w15", {
        "name": "_t_params_w15",
        "steps": ['[sense:search]{query: "$city 맛집"}'],
    })
    sched = _FakeScheduler()
    try:
        # (a) 인자 없이 스케줄 실행 → 엔진의 정직 거절이 그대로 보고된다
        with _FakeEngine():
            out = sched.run({"workflow_id": wf_id})
        assert not out.get("success"), f"인자 누락인데 완주: {out}"
        assert "인자 누락" in str(out.get("error", "")), out

        # (b) action_params.params 를 실으면 실제 주입까지 도달
        with _FakeEngine() as eng:
            out = sched.run({"workflow_id": wf_id, "params": {"city": "청주"}})
        assert out.get("success"), out
        q = eng.calls[0]["params"]["query"]
        assert q == "청주 맛집", f"query={q!r} — 스케줄이 params 를 버리면 회귀"
        assert out.get("params_injected") == ["city"], out

        # (c) 모델이 JSON 문자열로 저장해도 엔진과 같은 규칙으로 수용
        with _FakeEngine() as eng:
            out = sched.run({"workflow_id": wf_id, "params": '{"city": "부산"}'})
        assert out.get("success"), out
        assert eng.calls[0]["params"]["query"] == "부산 맛집", eng.calls[0]

        # (d) 객체가 아닌 params → 침묵 무시 대신 정직 거절
        with _FakeEngine():
            out = sched.run({"workflow_id": wf_id, "params": "청주"})
        assert not out.get("success") and "객체여야" in str(out.get("error", "")), out
    finally:
        _cleanup(wf_id)

    # (e) params_default 만 있는 저장본은 스케줄에서 인자 없이도 돈다 (엔진이 처리)
    wf2 = _save_tmp_workflow("_t_params_w15b", {
        "name": "_t_params_w15b",
        "steps": ['[sense:search]{query: "$city 맛집"}'],
        "params_default": {"city": "서울"},
    })
    try:
        with _FakeEngine() as eng:
            out = sched.run({"workflow_id": wf2})
        assert out.get("success"), out
        assert eng.calls[0]["params"]["query"] == "서울 맛집", eng.calls[0]
    finally:
        _cleanup(wf2)
    print("W15 OK — 스케줄러 run_workflow 가 params 를 엔진까지 통과")


def test_w16_body_bound_vars_not_signature():
    """W16 (B22-1, 22회차 상상훈련) — 몸통이 스스로 할당한 변수는 시그니처가 아니다.

    시그니처는 '사용' 이 아니라 '사용 − 할당' 이다. 파서 치환기는 param 값 자리만 치환하고
    식 할당의 우변·repeat 조건에 남은 $이름은 리터럴로 남긴다. 그걸 자유 변수로 세면
    교재 M6 의 `do: '…$return = …'` 저장본이 저장은 되고 실행은 거절된다.
    아래 표가 오탐 경계다 — 진짜 자유 변수(W8)는 차집합 뒤에도 그대로 걸려야 한다.
    """
    from workflow_contract import _free_vars, _normalize_steps_for_injection

    cases = [
        ('$r = [self:time]\n$return = $r', [], '식 할당 우변'),
        ('$a = [self:time]\n[table:brief]{items: "$a", instruction: "한 줄"}', [], 'param 값 자리'),
        ('$n = 0\n[repeat: while $n < 3, max: 5]{$n = $n + 1\n[self:time]}', [], 'repeat 조건'),
        ('[repeat: 3, collect: true]{[sense:search]{query: "AI", page: "$i"}}', [], '회차 변수 $i'),
        ('[sense:search]{query: "$topic"}', ['topic'], '진짜 자유 변수 — W8 무회귀'),
        ('[sense:search]{query: "$topic"}\n$r = [self:time]\n$return = $r', ['topic'], '혼합'),
    ]
    for body, want, label in cases:
        steps, err = _normalize_steps_for_injection(body)
        assert not err, (label, err)
        got = _free_vars(steps)
        assert got == want, f'{label}: 시그니처 {got} (기대 {want}) — {body!r}'

    wf = _save_tmp_workflow('_t_params_w16', {
        'name': '_t_params_w16',
        'do': '$r = [self:time]\n$return = $r',
    })
    try:
        with _FakeEngine():
            out = execute_workflow_action('workflow', {'op': 'run', 'workflow_id': wf}, '.')
        assert out.get('success'), f'몸통이 할당한 변수를 인자로 요구했다: {out}'
        assert 'params_missing' not in out, out
    finally:
        _cleanup(wf)
    print('W16 OK — 몸통이 할당한 변수는 시그니처가 아니다(식 할당 우변·repeat·$i)')


if __name__ == "__main__":
    print("=== workflow params·시그니처·재귀 가드 회귀 테스트 (W1~W15) ===\n")
    test_w1_saved_run_injects_params()
    test_w2_type_preservation()
    test_w3_unmatched_param_warns()
    test_w4_reserved_names_protected()
    test_w5_inline_run_injects_params()
    test_w6_assignment_wins_over_params()
    test_w7_bad_params_rejected()
    test_w8_missing_arg_rejected()
    test_w9_params_default()
    test_w13_inline_unfilled_warns_not_rejects()
    test_w14_signature_saved_and_listed()
    test_w15_scheduler_passes_params()
    test_w16_body_bound_vars_not_signature()
    print("\n--- 재귀·순환 가드 (실경로) ---")
    test_w10_self_cycle_rejected()
    test_w11_mutual_cycle_rejected()
    test_w12_depth_cap()
    print("\n=== 전부 통과 ===")
