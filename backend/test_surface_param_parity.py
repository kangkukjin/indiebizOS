"""표면 파라미터 일치 상설 관문 — 도구 스키마 ⊆ 모든 실행 표면 (B23-1 부류의 탄생 차단).

23회차(2026-08-22)가 resume/files/verbose 가 REST·MCP 에서 조용히 탈락하던 부류를
스윕했지만, 재발 방지는 IBLRequest 의 **주석 의무**("함께 늘릴 것")뿐이었다 —
주석으로만 있던 불변식은 반드시 샌다(공개노출↔인증 관문과 같은 교훈). 이 시험이
그 의무를 기계화한다: tool_loader 의 execute_ibl 스키마에 파라미터를 넣으면
REST(IBLRequest)·MCP(execute_ibl 시그니처)도 같이 늘려야 커밋이 통과한다.

표면 고유 확장(project_id/project_path 등)은 허용 — 불변식은 포함(⊆)이지 동일이 아니다.
"""

import ast
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent


def _schema_params():
    from ibl.tool_loader import build_execute_ibl_tool
    tool = build_execute_ibl_tool()
    assert tool, "execute_ibl 도구 스키마 생성 실패 (ibl_nodes.yaml)"
    return set(tool["input_schema"]["properties"].keys())


def _rest_fields():
    """backend/surface/api_ibl.py IBLRequest 의 필드 — 정적(AST)으로 읽는다."""
    tree = ast.parse((ROOT / "backend/surface/api_ibl.py").read_text())
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef) and node.name == "IBLRequest":
            return {stmt.target.id for stmt in node.body
                    if isinstance(stmt, ast.AnnAssign) and isinstance(stmt.target, ast.Name)}
    raise AssertionError("IBLRequest 를 찾지 못했습니다 — api_ibl.py 이사 시 이 시험도 이사")


def _mcp_args():
    """mcp_server.py execute_ibl 시그니처 인자 — 정적(AST)으로 읽는다."""
    tree = ast.parse((ROOT / "mcp_server.py").read_text())
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) \
                and node.name == "execute_ibl":
            args = node.args
            names = {a.arg for a in [*args.posonlyargs, *args.args, *args.kwonlyargs]}
            return names - {"self", "ctx", "context"}
    raise AssertionError("mcp_server.execute_ibl 을 찾지 못했습니다")


def test_schema_params_reach_every_surface():
    """스키마의 모든 파라미터가 REST·MCP 표면에 실존한다 — 침묵 탈락 부류 차단."""
    schema = _schema_params()
    rest, mcp = _rest_fields(), _mcp_args()
    assert schema, "빈 스키마"
    missing_rest = schema - rest
    missing_mcp = schema - mcp
    assert not missing_rest, (
        f"도구 스키마 파라미터 {sorted(missing_rest)} 이(가) REST IBLRequest 에 없습니다 — "
        "body 로 보낸 값이 pydantic 에서 조용히 탈락합니다(B23-1 부류). api_ibl.py 에 필드를 늘리세요.")
    assert not missing_mcp, (
        f"도구 스키마 파라미터 {sorted(missing_mcp)} 이(가) MCP execute_ibl 시그니처에 없습니다 — "
        "mcp_server.py 시그니처와 payload 패스스루를 늘리세요.")


def test_code_is_required_everywhere():
    assert "code" in _schema_params()
    assert "code" in _rest_fields()
    assert "code" in _mcp_args()


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__]))
