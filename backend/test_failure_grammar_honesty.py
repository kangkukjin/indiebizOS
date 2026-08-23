"""실패 문법의 정직성 회귀 — 30회차 (2026-08-23)

30회차 축 = **실패 문법(8) × 실패 원인(12) = 96칸**. 코퍼스 3,582문장 중 오류 경로를
밟는 문장이 **28건(0.78%)** 뿐이라, 언어의 '고장 나는 쪽 절반'은 거의 시험된 적이 없었다.

재현하는 결함(전부 실측):
  B30-1 **`[try]{[A] & [B]}` 가 엉뚱한 문구로 죽는다.**
     파서는 병렬을 `{"_parallel": [...]}` 한 step 으로 내는데, `execute_ibl` 의 블록
     디스패치 목록(`_goal`/`_condition`/`_case`/`_try`/`_repeat`/`_assign`)에 `_parallel`
     만 빠져 있었다. 블록 몸은 `_run_body` 가 dict 를 `execute_ibl` 로 곧장 넘기므로
     아래 `action` 검사까지 떨어져 이렇게 죽었다:
         _caught = {"error": "action 파라미터가 필요합니다.", "node": null, "action": null}
     ★봉투가 스스로 "무엇이 죽었는지 모른다"고 자백한다(node·action 이 null).
     ★같은 부류를 코드가 이미 이름 붙여 알고 있었다 — system_tools_ibl.py 의
       "전 표면 블록 실행 봉쇄 부류" 주석. 최상위 경로는 고쳤고 블록 몸은 안 고쳤다.
     대조: `??` 는 같은 한계를 **검수 시점에 정확히** 거절한다("& 와 ?? 를 섞을 수 없습니다").
     같은 한계를 두 문법이 다르게 말하면 안 된다.

  B30-2 **서킷 브레이커가 블록 문장을 전부 빈 키 하나로 뭉쳤다.**
     `_fail_key = f"{agent}:{_node}:{_action}"` 인데 블록 문장은 node·action 이 비어
     모든 블록이 `agent::` **한 바구니**에 들어갔다. 서로 무관한 블록 셋이 실패하면
     *모든* 블록 문장이 90초 차단됐고 메시지는 `[:] 액션이 연속 3회 실패…` 라며 아무
     이름도 대지 못했다. 실측: 한 훈련 회차에 빈 키 차단 **36회**.
     ★게다가 판정이 **두 벌**이었다(체크 지점·갱신 지점이 각자 키를 조립) — 그래서 같은
       실수가 두 곳에 있었다. 수리는 `_breaker_key()` 한 벌로 모았다.

  B30-3 **리허설의 의도된 실패가 사용자의 실제 호출을 차단할 수 있었다.**
     훈련은 갭을 찾으려고 `ZZZZINVALID` 를 일부러 밟는데, 그 실패가 차단기를 열면
     그 90초 동안 사용자의 진짜 `[sense:stock]` 호출까지 막힌다. E28-3('리허설은 삶이
     아니다')이 건강 원장에 내린 판정과 같은 규율을 차단기에도 적용 — **지우지 않고
     키 공간을 분리**한다(훈련 안에서의 폭주 방어는 그대로 산다).

실행: .venv/bin/python -m pytest backend/test_failure_grammar_honesty.py -q
"""
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import boot_paths  # noqa: F401


# ── B30-2 / B30-3: 차단기 판정은 한 벌 ────────────────────────────────

def _parse(code):
    from ibl_parser import parse
    return parse(code)


def test_R1_블록_문장은_차단기_대상이_아니다():
    """빈 키 `agent::` 바구니가 다시 생기지 않는다."""
    import system_tools_ibl as sti
    for code in ('[repeat: 2, every: "1s"]{[self:time]}',
                 '[try]{[self:time]}\n[catch]{[self:time]}',
                 '[if: 1 > 0]{[self:time]}\n[else]{[self:time]}',
                 '[sense:weather]{city: "수원"} & [sense:weather]{city: "평택"}'):
        key = sti._breaker_key(_parse(code), "agent1")
        assert key is None, f"블록/병렬이 차단기 키를 얻었다: {code!r} → {key!r}"


def test_R2_진짜_단일_액션만_키를_얻는다():
    import system_tools_ibl as sti
    key = sti._breaker_key(_parse('[sense:stock]{op: "quote", ticker: "005930"}'), "agent1")
    assert key and key.endswith("sense:stock")
    assert "::" not in key, f"빈 마디가 있다: {key!r}"


def test_R3_리허설은_자기_키_공간을_쓴다(monkeypatch):
    """훈련의 의도된 실패가 사용자의 실제 호출을 차단하지 않는다."""
    import system_tools_ibl as sti
    import thread_context
    code = '[sense:stock]{op: "quote", ticker: "005930"}'
    live = sti._breaker_key(_parse(code), "agent1")
    monkeypatch.setattr(thread_context, "in_rehearsal", lambda: True)
    rehearsal = sti._breaker_key(_parse(code), "agent1")
    assert rehearsal != live, "리허설과 실사용이 같은 차단기 칸을 쓴다"
    assert "training" in rehearsal


def test_R4_판정은_한_벌이다():
    """체크 지점·갱신 지점이 각자 키를 조립하던 중복이 되살아나지 않는다."""
    src = open(os.path.join(os.path.dirname(os.path.abspath(__file__)),
                            "cognition", "system_tools_ibl.py"), encoding="utf-8").read()
    assert src.count("_breaker_key(") >= 3, "두 호출 지점 + 정의가 모두 있어야 한다"
    # 손으로 조립한 옛 키 문자열이 남아 있으면 판정이 다시 두 벌이 된다
    assert "f\"{agent_id or 'default'}:{_node}:{_action}\"" not in src
    assert "f\"{agent_id or 'default'}:{_n}:{_a}\"" not in src


# ── B30-1: 블록 몸의 병렬 ────────────────────────────────────────────

def test_R5_engine_이_parallel_을_디스패치한다():
    """블록 몸의 `[A] & [B]` 가 'action 파라미터가 필요합니다' 로 죽지 않는다."""
    src = open(os.path.join(os.path.dirname(os.path.abspath(__file__)),
                            "ibl", "ibl_engine.py"), encoding="utf-8").read()
    i_par = src.find('tool_input.get("_parallel")')
    i_act = src.find('action = tool_input.get("action")')
    assert i_par != -1, "_parallel 디스패치가 없다"
    assert i_par < i_act, "_parallel 분기가 action 검사보다 뒤에 있으면 여전히 오진한다"


def test_R6_try_몸의_병렬이_실제로_흐른다(monkeypatch):
    """의미론을 복제하지 않고 소유자(파이프 실행기)에게 위임했는지 — 실호출로 확인."""
    import ibl_engine
    calls = []

    def _fake_pipeline(steps, project_path=".", context=None, agent_id=None):
        calls.append(steps)
        return {"success": True, "final_result": '{"items": [{"a": 1}], "count": 1}'}

    import workflow_engine
    monkeypatch.setattr(workflow_engine, "execute_pipeline", _fake_pipeline)
    out = ibl_engine.execute_ibl({"_parallel": [{"_node": "sense", "action": "weather"},
                                                {"_node": "sense", "action": "weather"}]}, ".")
    assert calls, "파이프 실행기에 위임하지 않았다(의미론을 복제했을 가능성)"
    assert isinstance(out, dict) and out.get("count") == 1
    assert "action 파라미터가 필요합니다" not in str(out)


# ── F30-1: 정직 표지가 교재에서 가르쳐지는가 ──────────────────────────

def test_R7_봉투_정직_표지가_교재에_있다():
    """몸이 표지를 달아도 읽는 법을 안 가르치면 아무도 안 본다.

    30회차 실측: `_fallback_used`·`ok_count`/`error_count`·`rows_in` 은 몸이 실제로
    싣는데 공통 프롬프트·어휘 src 어디에도 **0회** 언급이었다. 특히 `_fallback_used` 는
    데이터의 *출처가 바뀌었다*는 표지라, 못 읽으면 검색 결과를 시세라고 보고하게 된다.
    """
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    frag = os.path.join(root, "data", "common_prompts", "fragments", "12_ibl_only.md")
    src = open(frag, encoding="utf-8").read()
    for marker in ("_fallback_used", "ok_count", "error_count", "rows_in",
                   "skipped_steps", "_caught", "condition_errors", "halted"):
        assert marker in src, f"교재가 정직 표지 '{marker}' 를 가르치지 않는다"


def test_R8_fallback_표지가_교재뿐_아니라_실물로도_나온다(monkeypatch):
    """F35-1(35회차): R7 은 **교재에 적혀 있는지**만 봤고 '몸이 실제로 싣는다'는
    30회차의 가정을 검증하지 않았다. 실측하니 안 실었다 —

        [sense:stock]{op:"quote", ticker:"ZZZZINVALID"} ?? [self:time]
        → final_result '2026-08-23 21:05:31' · 최상위/final_result/results[0] 어디에도
          `_fallback_used` 없음

    옛 배선은 표지를 *결과 안*에 넣어서 dict 나 '{' 로 시작하는 JSON 문자열에만 붙었다.
    **평문 스칼라**라는 세 번째 모양에서 조용히 사라졌고, 읽는 쪽은 표지가 없으니
    '폴백 안 씀'으로 단정한다(34회차의 이 저장소 자신이 그렇게 읽었다).
    가르치는 자리와 신고하는 자리는 **둘 다** 지켜져야 한다."""
    import ibl_engine, workflow_engine
    from ibl_parser import parse

    def _fake(tool_input, project_path, agent_id=None, **kw):
        if tool_input.get("action") == "bad":
            return {"success": False, "error": "없는 종목"}
        return "2026-08-23 21:05:31"          # ★평문 스칼라 — 옛 배선이 놓치던 모양

    orig = ibl_engine.execute_ibl
    ibl_engine.execute_ibl = _fake
    try:
        out = workflow_engine.execute_pipeline(parse('[sense:bad]{} ?? [self:time]'), ".")
    finally:
        ibl_engine.execute_ibl = orig

    assert out.get("success"), out
    assert "_fallback_used" in out, f"갈아탄 사실이 최상위 봉투에 없다: {sorted(out.keys())}"
    fb = out["_fallback_used"]
    assert fb and fb[0]["attempt"] == 2, fb
    assert "sense:bad" in fb[0]["skipped"], fb          # 무엇을 버렸는지도 말한다
    assert "출처" in (out.get("warning") or ""), out.get("warning")

    # ★첫 가지가 그냥 성공하면 표지가 붙지 않아야 한다(거짓 경보 금지)
    def _ok(tool_input, project_path, agent_id=None, **kw):
        return "2026-08-23 21:05:31"
    ibl_engine.execute_ibl = _ok
    try:
        out2 = workflow_engine.execute_pipeline(parse('[self:time]{} ?? [sense:bad]{}'), ".")
    finally:
        ibl_engine.execute_ibl = orig
    assert "_fallback_used" not in out2, out2


if __name__ == "__main__":                      # 러너는 하나 — pytest (2026-08-23)
    import sys as _sys
    try:
        import pytest as _pytest
    except ImportError:
        raise SystemExit("pytest 가 없습니다 — .venv/bin/python -m pytest 로 실행하세요")
    raise SystemExit(_pytest.main([__file__, "-q"] + _sys.argv[1:]))
