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

from ibl_parser import parse, parse_step, IBLSyntaxError  # noqa: E402


def test_d1_mixed_operators_rejected():
    """D1: '[a]{} ?? [b]{} & [c]{}' 는 예전에 b 가 조용히 사라졌다 → 이제 파스 에러."""
    try:
        parse('[sense:web_search]{query: "a"} ?? [sense:crawl]{url: "b"} & [sense:search_gnews]{query: "c"}')
        raise AssertionError("혼용은 IBLSyntaxError 여야 함")
    except IBLSyntaxError as e:
        assert "섞을 수 없습니다" in str(e)
    # 반대 순서도 동일
    try:
        parse('[sense:a1]{} & [sense:a2]{} ?? [sense:a3]{}')
        raise AssertionError("혼용은 IBLSyntaxError 여야 함")
    except IBLSyntaxError:
        pass
    # 순수 병렬·순수 폴백은 그대로 동작 (회귀 없음)
    p = parse('[sense:a1]{} & [sense:a2]{} & [sense:a3]{}')
    assert len(p[0]["branches"]) == 3
    p = parse('[sense:a1]{} ?? [sense:a2]{}')
    assert len(p[0]["_fallback_chain"]) == 2
    print("D1 OK — & / ?? 혼용 명시 거부, 순수 형태 회귀 없음")


def test_d2_leftover_text_rejected():
    """D2: '[a:b]{} [c:d]{}' (>> 누락)는 예전에 c:d 가 침묵 유실 → 이제 에러."""
    try:
        parse('[sense:web_search]{query: "a"} [self:file]{path: "b.md"}')
        raise AssertionError(">> 누락은 IBLSyntaxError 여야 함")
    except IBLSyntaxError as e:
        assert "해석되지 않은" in str(e)
    # 앞쪽 잔여 텍스트도 거부
    try:
        parse('실행해줘 [sense:web_search]{query: "a"}')
        raise AssertionError("앞 잔여 텍스트는 IBLSyntaxError 여야 함")
    except IBLSyntaxError:
        pass
    # @별칭·빈 괄호·인라인 주석은 정상 (기존 관대함 유지)
    s = parse_step('[self:read]{path: "a.md"}@폰2')
    assert s["target_node"] == "폰2"
    assert parse_step('[self:open]()')["action"] == "open"
    assert parse('[sense:web_search]{query: "a"} # 검색')[0]["action"] == "web_search"
    print("D2 OK — 잔여 텍스트 명시 거부, @별칭/주석 회귀 없음")


def test_d3_string_protected_comment_strip():
    """D3: multi-line string 파라미터 안의 '# 헤딩'·빈 줄이 예전엔 삭제됐다 → 보존."""
    code = '''# 진짜 주석은 제거
[self:write]{path: "t.md", content: "제목
# 마크다운 헤딩

## 소제목
본문 don't 포함"}'''
    p = parse(code)
    c = p[0]["params"]["content"]
    assert "# 마크다운 헤딩" in c
    assert "## 소제목" in c
    assert "\n\n" in c            # 문자열 안 빈 줄도 내용
    assert "don't" in c           # 아포스트로피가 문자열 상태를 깨지 않음
    assert p[0]["params"]["path"] == "t.md"
    # 문자열 밖 주석·빈 줄은 여전히 제거
    p2 = parse('# 주석1\n\n[sense:web_search]{query: "a"}\n# 주석2')
    assert len(p2) == 1
    print("D3 OK — 문자열 내부 보호, 밖 주석 제거 유지")


def test_d4_var_binding_parser():
    """D4(파서): $var → 할당 문장의 최종 step 인덱스 {{_step_N_result}}."""
    p = parse('$result = [sense:web_search]{query: "AI"}\n'
              '[others:channel_send]{channel_type: "telegram", body: "$result"}')
    assert p[1]["params"]["body"] == "{{_step_0_result}}"
    # 파이프라인 할당은 마지막 step 을 가리킴
    p = parse('$r = [sense:web_search]{query: "A"} >> [table:take]{n: 3}\n'
              '[others:channel_send]{channel_type: "telegram", body: "$r"}')
    assert p[2]["params"]["body"] == "{{_step_1_result}}"
    print("D4(파서) OK — $var 가 실제 step 인덱스로 치환")


def test_d4_var_binding_engine():
    """D4(엔진): 문서화된 예제가 실제로 앞 문장 결과를 받는다 (예전엔 빈 문자열)."""
    import ibl_engine
    import workflow_engine

    calls = []
    _orig = ibl_engine.execute_ibl

    def _fake_execute(tool_input, project_path, agent_id=None, **kw):
        calls.append(tool_input)
        if tool_input.get("action") == "web_search":
            return "검색결과A"
        return {"success": True, "sent": tool_input.get("params", {}).get("body")}

    ibl_engine.execute_ibl = _fake_execute
    try:
        steps = parse('$result = [sense:web_search]{query: "AI"}\n'
                      '[others:channel_send]{channel_type: "telegram", body: "$result"}')
        out = workflow_engine.execute_pipeline(steps, ".")
    finally:
        ibl_engine.execute_ibl = _orig

    assert out["success"], out
    body = calls[1]["params"]["body"]
    assert body == "검색결과A", f"body={body!r} — 빈 문자열이면 D4 회귀"
    print("D4(엔진) OK — 문장 경계를 넘어 $var 결과 주입")


def test_d5_recursive_acl():
    """D5: 병렬/폴백/if/case 내부의 금지 노드가 ACL 에 걸린다 (예전엔 무검사 통과)."""
    from system_tools_ibl import _collect_step_nodes, _execute_ibl_unified
    import thread_context

    # 수집기 단위 검증
    nodes = set()
    _collect_step_nodes(parse('[sense:a1]{} & [self:read]{path: "x"}'), nodes)
    assert nodes == {"sense", "self"}, nodes
    nodes = set()
    _collect_step_nodes(parse('[sense:a1]{} ?? [limbs:call]{tool: "t"}'), nodes)
    assert nodes == {"sense", "limbs"}, nodes
    nodes = set()
    _collect_step_nodes(parse('[if: sense:kospi < 2400]{\n[self:read]{path: "x"}\n}'), nodes)
    assert "sense" in nodes and "self" in nodes, nodes
    nodes = set()
    _collect_step_nodes(parse('[case: sense:market_status]{\n"상승장": [goal: "매수"]{max_rounds: 2},\ndefault: [goal: "관망"]{max_rounds: 1}\n}'), nodes)
    assert "sense" in nodes, nodes

    # 통합 경로 검증 — sense 만 허용된 에이전트가 병렬 안에 self 를 숨겨도 거부
    thread_context.set_allowed_nodes({"sense"})
    try:
        raw = _execute_ibl_unified(
            {"code": '[sense:web_search]{query: "a"} & [self:read]{path: "/etc/x"}'},
            ".", agent_id="restricted-test")
    finally:
        thread_context.set_allowed_nodes(None)
    obj = json.loads(raw)
    assert obj.get("denied") or obj.get("error"), obj
    assert "self" in raw, raw
    print("D5 OK — 복합 스텝 재귀 ACL (병렬/폴백/if/case)")


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


if __name__ == "__main__":
    print("=== IBL 침묵 실패 수리 회귀 테스트 (D1~D6) ===\n")
    test_d1_mixed_operators_rejected()
    test_d2_leftover_text_rejected()
    test_d3_string_protected_comment_strip()
    test_d4_var_binding_parser()
    test_d4_var_binding_engine()
    test_d5_recursive_acl()
    test_d6_sync_handler_timeout()
    print("\n=== 전부 통과 ===")
