"""평가자 도구 trace 직렬화 회귀 테스트

목적: 37개 도구 호출이 평가자 입력에서 절단되어도 **호출 이름·순서는 끝까지 보존**되는지 검증.
2026-05-28 홍보 프로젝트 홈페이지 작업에서 마지막 5개만 노출되어 첫 호출
[engines:web_site] list가 평가자에 안 보였던 회귀 방지.

실행: cd backend && python3 test_evaluator_trace.py
"""

import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from agent_cognitive import serialize_tool_trace, _brief_input, _normalize_tool_entry


def _make_homepage_workflow_fixture():
    """2026-05-28 사례 재현: 첫 호출은 engines:web_site list, 이후 Read/Edit/Write로 컴포넌트 수정,
    마지막은 next build 성공."""
    calls = []
    # 1: 가이드 워크플로우의 첫 단계 — 사이트 목록 조회
    calls.append({
        "name": "execute_ibl",
        "input": {"node": "engines", "action": "web_site", "op": "list"},
        "result": '[{"id":"indiebizOS-home","path":"/Users/.../indiebizOS-homepage"},{"id":"site2"}]',
        "is_error": False,
    })
    # 2~5: 파일 읽기
    for i in range(4):
        calls.append({
            "name": "Read",
            "input": {"file_path": f"/Users/kangkukjin/Desktop/AI/HomePages/indiebizOS-home/components/section-{i}.tsx"},
            "result": "(파일 내용 200줄)",
            "is_error": False,
        })
    # 6~30: Edit 작업
    for i in range(25):
        calls.append({
            "name": "Edit",
            "input": {
                "file_path": f"/Users/kangkukjin/Desktop/AI/HomePages/indiebizOS-home/components/indie-hero.tsx",
                "old_string": f"...{i}...",
                "new_string": f"...{i} updated...",
            },
            "result": "Edit completed.",
            "is_error": False,
        })
    # 31: 신규 컴포넌트 생성 (이게 created_files에 잡혀야 함)
    calls.append({
        "name": "Write",
        "input": {
            "file_path": "/tmp/test_harness_vs_frameworks_section.tsx",
            "content": "export function HarnessSection() { return <div>test</div>; }",
        },
        "result": "File created.",
        "is_error": False,
    })
    # 32~36: 후속 Edit
    for i in range(5):
        calls.append({
            "name": "Edit",
            "input": {"file_path": f"/path/to/another-{i}.tsx"},
            "result": "Edit completed.",
            "is_error": False,
        })
    # 37: 빌드 명령
    calls.append({
        "name": "run_command",
        "input": {"command": "cd /Users/.../indiebizOS-home && npx next build"},
        "result": "Compiled successfully.",
        "is_error": False,
    })
    return calls


def test_sequence_preserved_when_many_calls():
    """37개 호출 → 직렬화 trace에 첫 호출(engines:web_site list)과 마지막 호출(run_command)이
    모두 포함되어야 한다."""
    calls = _make_homepage_workflow_fixture()
    assert len(calls) == 37, f"fixture 호출 수: {len(calls)}"

    trace = serialize_tool_trace(calls)
    print(f"\n--- 직렬화 trace 길이: {len(trace)}자 ---")
    print(trace[:1500])
    print("..." if len(trace) > 1500 else "")

    # 핵심 검증 1: 총 호출 수가 헤더에 노출
    assert "총 37회" in trace, f"총 호출 수 헤더 누락: {trace[:200]}"

    # 핵심 검증 2: 첫 호출(가이드 워크플로우 시작점)이 trace에 보존됨
    assert "[1]" in trace, "[1] 인덱스 누락"
    assert "execute_ibl" in trace, "첫 호출의 도구 이름(execute_ibl)이 trace에 없음"
    assert "engines" in trace and "web_site" in trace and "op=list" in trace, \
        f"첫 호출의 핵심 input(node=engines action=web_site op=list)이 trace에 없음:\n{trace[:500]}"

    # 핵심 검증 3: 마지막 호출(run_command)도 보존됨
    assert "[37]" in trace, f"[37] 인덱스 누락: trace 끝부분=\n{trace[-500:]}"
    assert "run_command" in trace, "마지막 호출 이름(run_command)이 trace에 없음"
    assert "next build" in trace, "마지막 호출의 핵심 input(next build)이 trace에 없음"

    print("✓ 시퀀스 보존 검증 통과")


def test_all_call_headers_visible():
    """가운데 일부 결과 본문은 생략되더라도, 모든 호출의 **헤더 라인**은 trace에 보여야 한다."""
    calls = _make_homepage_workflow_fixture()
    trace = serialize_tool_trace(calls)

    # 1~37번 인덱스가 모두 보여야 함 (헤더가 살아있어야 함)
    for i in range(1, 38):
        marker = f"[{i}]"
        assert marker in trace, f"호출 {marker}의 헤더가 trace에서 사라짐 (시퀀스 손실)"

    print(f"✓ 1~37번 호출 헤더 모두 trace에 존재")


def test_backward_compat_with_string_list():
    """legacy: tool_results가 문자열 리스트인 경우도 작동해야 함."""
    legacy = [f"결과 {i}" for i in range(10)]
    trace = serialize_tool_trace(legacy)
    assert "총 10회" in trace
    assert "[1]" in trace and "[10]" in trace
    assert "(이름미상)" in trace, "이름 불명 마커가 표시되어야 함"
    print("✓ 문자열 리스트(legacy) backward-compat 통과")


def test_empty_input():
    """빈 입력은 빈 문자열을 반환해야 함."""
    assert serialize_tool_trace([]) == ""
    assert serialize_tool_trace(None) == ""
    print("✓ 빈 입력 처리 통과")


def test_brief_input_priority_keys():
    """input 요약에서 식별성 높은 키(node/action/op/command/file_path)가 우선 노출."""
    # IBL 호출
    s = _brief_input({"node": "engines", "action": "web_site", "op": "list", "params": {"x": "y"}})
    assert "node=engines" in s and "action=web_site" in s and "op=list" in s
    # Bash
    s2 = _brief_input({"command": "ls -la", "description": "디렉터리 목록"})
    assert "command=" in s2 and "ls -la" in s2
    # Write
    s3 = _brief_input({"file_path": "/tmp/foo.tsx", "content": "x" * 1000})
    assert "file_path=" in s3 and "/tmp/foo.tsx" in s3
    print("✓ input 요약 우선순위 키 노출 통과")


def test_created_files_from_tool_calls():
    """_collect_created_files가 tool_calls에서 Write 호출의 file_path를 직접 수집하는지 검증.
    Write 결과로 생성된 파일이 응답 텍스트에 안 보여도 created_files로 잡혀야 한다."""
    import tempfile

    # 실제 임시 파일 생성 — _collect_created_files는 os.path.isfile 체크함
    with tempfile.NamedTemporaryFile(mode='w', suffix='.tsx', delete=False) as f:
        f.write("export function Test() { return null; }")
        tmp_path = f.name

    try:
        tool_calls = [
            {"name": "Write", "input": {"file_path": tmp_path}, "result": "File created."},
        ]
        # 더미 AgentCognitiveMixin 인스턴스 만들기 어려우니 메서드 자체를 추출해 검증
        # — _collect_created_files는 self에 의존 안 함 (response, tool_calls만 사용)
        from agent_cognitive import AgentCognitiveMixin

        class _Dummy(AgentCognitiveMixin):
            pass

        dummy = _Dummy()
        # 응답 텍스트는 파일을 언급하지 않음 — tool_calls 기반 수집이 동작해야 함
        result = dummy._collect_created_files(
            response="홈페이지를 업데이트했습니다.",
            tool_calls=tool_calls,
        )
        assert tmp_path in result or os.path.basename(tmp_path) in result, \
            f"Write 도구의 file_path를 created_files에서 수집 못 함:\n{result[:300]}"
        print(f"✓ Write 호출에서 file_path 직접 수집 통과")
    finally:
        try:
            os.unlink(tmp_path)
        except Exception:
            pass


def test_ibl_self_write_file_path():
    """IBL execute_ibl([self:write]) 같은 케이스: input.params.path에서 경로 추출."""
    import tempfile
    from agent_cognitive import AgentCognitiveMixin

    with tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False) as f:
        f.write("hello")
        tmp_path = f.name

    try:
        tool_calls = [{
            "name": "execute_ibl",
            "input": {"node": "self", "action": "write", "params": {"path": tmp_path, "content": "hello"}},
            "result": "ok",
        }]

        class _Dummy(AgentCognitiveMixin):
            pass

        result = _Dummy()._collect_created_files(response="", tool_calls=tool_calls)
        assert tmp_path in result or os.path.basename(tmp_path) in result, \
            f"[self:write]의 params.path를 수집 못 함:\n{result[:300]}"
        print("✓ IBL [self:write] params.path 수집 통과")
    finally:
        try:
            os.unlink(tmp_path)
        except Exception:
            pass


def test_error_tag():
    """is_error=True인 호출은 [ERROR] 태그가 붙어야 함."""
    calls = [
        {"name": "Read", "input": {"file_path": "/nope"}, "result": "Not found", "is_error": True},
        {"name": "Read", "input": {"file_path": "/ok"}, "result": "OK", "is_error": False},
    ]
    trace = serialize_tool_trace(calls)
    # 첫 호출만 [ERROR]
    err_count = trace.count("[ERROR]")
    assert err_count == 1, f"[ERROR] 태그가 정확히 1개여야 함, 실제 {err_count}개:\n{trace}"
    print("✓ [ERROR] 태그 통과")


if __name__ == "__main__":
    print("=== 평가자 도구 trace 직렬화 회귀 테스트 ===\n")
    test_empty_input()
    test_brief_input_priority_keys()
    test_backward_compat_with_string_list()
    test_sequence_preserved_when_many_calls()
    test_all_call_headers_visible()
    test_created_files_from_tool_calls()
    test_ibl_self_write_file_path()
    test_error_tag()
    print("\n=== 전체 통과 ===")
