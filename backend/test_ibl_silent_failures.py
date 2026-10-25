"""IBL 문법 층 침묵 실패 수리 회귀 테스트 (2026-08-05 감사 D1~D6)

각 결함의 재현 케이스를 남긴다 — 수리 전엔 조용히 잘못되던 것들이
이제 명시 에러 또는 올바른 동작이 됨을 검증.

    D1. & / ?? 혼용 시 액션 침묵 소실           → 명시 파스 에러
    D2. >> 누락 오타가 한 스텝으로 침묵 흡수     → 잔여 텍스트 에러
    D3. 문자열 내부 # 줄(마크다운 헤딩) 삭제     → 문자열 보호
    D4. $var 바인딩이 빈 문자열로 뭉개짐         → {{_step_N_result}} 실구현
    D5. 복합 스텝(&/??/goal/if/case) ACL 무검사  → 재귀 노드 수집
    D6. 동기 handler.execute 무제한 행           → 스레드 오프로드 타임아웃

실행: python3 backend/test_ibl_silent_failures.py
"""
import json
import sys
import time

sys.path.insert(0, __file__.rsplit('/', 1)[0])
import boot_paths  # noqa: F401 — 층 디렉토리 등재 (물리 이동 2026-08-05)













def test_d5_recursive_acl(tmp_path, monkeypatch):
    import ibl_engine
    import thread_context
    from ibl_v2_entry import handle_request
    routed=[]
    monkeypatch.setattr(ibl_engine, '_route_handler', lambda *a,**k:routed.append(a))
    prior=thread_context.snapshot()
    try:
        thread_context.set_allowed_nodes({'sense'})
        for code in ('[self:read]{path:"forbidden"}',
                     '[def:f](){return [self:read]{path:"forbidden"}}\n[fn:f]{}',
                     '[table:each]{items:[1]}{[self:read]{path:"forbidden"}}'):
            out=handle_request({'code':code,'edition':2},str(tmp_path),agent_id='restricted-test')
            assert not out['success'],out
        assert routed==[]
    finally:
        thread_context.restore(prior)



def test_d6_sync_handler_timeout():
    """D6: 동기 핸들러가 행 걸려도 타임아웃으로 명확한 에러 (예전엔 무제한 행)."""
    from ibl_routing import _run_sync_with_timeout, _SyncHandlerTimeout
    import thread_context

    # 정상 반환
    assert _run_sync_with_timeout(lambda a, b: a + b, (1, 2), 5, "t") == 3

    # 예외는 원형 재전파
    def _boom(_i, _c):
        raise ValueError("원 예외")
    try:
        _run_sync_with_timeout(_boom, (None, None), 5, "t")
        raise AssertionError("ValueError 재전파돼야 함")
    except ValueError as e:
        assert "원 예외" in str(e)

    # thread_context(threading.local) 승계
    thread_context.set_allowed_nodes({"sense"})
    try:
        seen = _run_sync_with_timeout(
            lambda _i, _c: thread_context.get_allowed_nodes(), (None, None), 5, "t")
        assert seen == {"sense"}, seen
    finally:
        thread_context.set_allowed_nodes(None)

    # 행 걸린 핸들러 → 타임아웃
    t0 = time.time()
    try:
        _run_sync_with_timeout(lambda _i, _c: time.sleep(30), (None, None), 0.5, "hang-tool")
        raise AssertionError("_SyncHandlerTimeout 이어야 함")
    except _SyncHandlerTimeout as e:
        assert "hang-tool" in str(e)
    assert time.time() - t0 < 5, "타임아웃이 제때 발동해야 함"
    print("D6 OK — 동기 핸들러 타임아웃·컨텍스트 승계·예외 재전파")


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
