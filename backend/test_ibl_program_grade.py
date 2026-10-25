"""파일 스필은 원문과 행 수를 보존한다. 언어 검수는 현행 컴파일러가 맡는다."""
import importlib.util
import json
import os
import sys
import tempfile
from pathlib import Path
import boot_paths  # noqa: F401
import pytest
_PKG = Path(__file__).resolve().parent.parent / "data/packages/installed/tools"


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, str(path))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_e3_write_spill_ref():
    sysess = _load("_t_sysess_pg", _PKG / "system_essentials" / "handler.py")

    # ★스텁 대신 진짜 ToolContext — 쓰기 경로 해소(resolve_output_path)가 컨텍스트 계약의
    # 일부가 됐다(J29-1). 반쪽 스텁은 그 계약을 안 밟아 결함을 가린다.
    from tool_context import ToolContext

    def _Ctx(td):
        return ToolContext(project_path=td, tool_name="write_file", agent_id="test")

    with tempfile.TemporaryDirectory() as td:
        piped = json.dumps({"items": [{"a": 1}, {"a": 2}], "success": True})
        out = json.loads(sysess.execute({"path": os.path.join(td, "s.json"), "spill": True,
                                         "_prev_result": piped}, _Ctx(td)))
        assert out["success"] and out["items"] == [] and out["spilled"] is True, out
        ref = out["ref"]
        assert ref["kind"] == "items" and ref["count"] == 2 and ref["bytes"] > 0
        assert os.path.exists(ref["path"]) and json.load(open(ref["path"]))["items"][1]["a"] == 2
        # spill 없으면 옛 모양(ref 없음) — 현행 유지
        plain = json.loads(sysess.execute({"path": os.path.join(td, "p.json"), "_prev_result": piped}, _Ctx(td)))
        assert "ref" not in plain and "items" not in plain


def test_condition_validation_uses_current_compiler():
    from ibl_v2_compile import compile_program
    plan = compile_program('[if: len($rows)>0]{return $rows} [else]{return []}', {}, inputs={'rows': []})
    assert not plan.issues
    invalid = compile_program('[if: len($missing)>0]{return $missing}', {})
    assert invalid.issues


if __name__ == '__main__':
    raise SystemExit(pytest.main([__file__, *sys.argv[1:]]))
