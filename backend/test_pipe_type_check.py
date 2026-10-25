"""파이프 정적 타입 검사(T1) 관문 — returns 선언의 소비자 (ibl_pipe_types).

P1. 홀로/머리에 선 변환자(통화·items 없음) = 실행 전 정직 거절 (안내 동반).
P2. items 를 직접 실은 머리 변환자 = 통과 (언어 개정 2026-08-28 ③).
P3. 생산자 >> 변환자 = 통과 (정상 파이프).
P4. has_incoming(블록 몸·each 하위) = 통과 — 직전 통화가 들어온다.
P5. `$변수 >>` 머리·병렬 머리·블록 머리 = 검사 밖 (각자 규약 보유).
P6. 미지 액션·사전 불능 = 통과 (보수적 — 검사기가 실행을 죽이면 안 된다).
P7. 통합: execute_pipeline 이 T1 위반을 실행 전에 error_type=binding 으로 거절.
음성 대조(2026-08-29 출하 시 실측): 해마 코퍼스 3,661건 중 거절 3건 — 전부
생산자 없는 미완성 조각(정탐). do 하위 파이프 90건 거절 0.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import boot_paths  # noqa: E402,F401

















# ── T2. 이음매 기아 (2026-08-30) ─────────────────────────────────────────────
# effect >> 변환자 = 실행 전 정직 거절. A 통화는 op·param 조건부까지 해소한다 —
# 액션 단위로만 읽으면 오거절(코퍼스 3,676건 실측 26건: self:script op:run 4 ·
# self:write spill:true 2 등). 음성 대조(출하 시 실측): 사전 정정 후 T2 거절 0.












def _unified(monkeypatch, tmp_path, code):
    import json
    import thread_context
    import system_tools_ibl as unified
    snap = thread_context.snapshot()
    thread_context.clear_all_context()
    try:
        return json.loads(unified._execute_ibl_unified_impl({"code": code,"edition":2}, str(tmp_path)))
    finally:
        thread_context.restore(snap)




def test_current_compiler_rejects_before_execution(monkeypatch, tmp_path):
    import ibl_typecheck
    import ibl_engine
    executed = []
    monkeypatch.setattr(ibl_engine, "execute_ibl", lambda *a, **kw: executed.append(a))
    for code in (
        '[table:take]{n:1}',
        '[self:write]{path:"x",content:[1]}',
        '[limbs:browser]{op:"click",ref:"b1"} >> [table:take]{n:1}',
    ):
        result = _unified(monkeypatch, tmp_path, code)
        assert result.get("success") is False
        assert result.get('issues') or result.get('diagnostic')
    assert executed == [], "검사기가 기권해도 부작용 전 거절해야 한다"






def test_unified_rejects_single_input_union_before_running_searches(monkeypatch, tmp_path):
    import ibl_engine
    executed = []
    monkeypatch.setattr(ibl_engine, 'execute_ibl', lambda *a, **k: executed.append(a))
    code = ('$a = [sense:search]{query:"a"}\n$b = [sense:search]{query:"b"}\n'
            '$a >> [table:union]{with:$b}')
    out = _unified(monkeypatch, tmp_path, code)
    assert not out['success'] and out.get('issues'), out
    assert executed == []




if __name__ == "__main__":
    import pytest
    raise SystemExit(pytest.main([__file__, "-v"]))
