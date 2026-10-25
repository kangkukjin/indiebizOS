"""Episode 3942: 검사만 초록이던 잘못된 필터를 실행 파서로 거절한다."""
import importlib.util
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent))
import boot_paths  # noqa: E402,F401
from ibl_typecheck import typecheck_code  # noqa: E402


@pytest.fixture(scope="module")
def handler():
    path = Path(__file__).resolve().parents[1] / "data/packages/installed/tools/data-ops/handler.py"
    spec = importlib.util.spec_from_file_location("_filter_precheck_handler", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def code_for(where, key="where"):
    return ('[table:filter]{items:[{title:"모닝 브리프",price:3}], '
            + key + ':' + json.dumps(where, ensure_ascii=False) + '}')














@pytest.mark.parametrize("check_only", [True, False])
def test_unified_rejects_episode_expression_before_any_search(monkeypatch, tmp_path, check_only):
    import ibl_engine
    import system_tools_ibl as unified
    import thread_context

    calls = []
    monkeypatch.setattr(ibl_engine, "execute_ibl", lambda *a, **kw: calls.append(a))
    snapshot = thread_context.snapshot()
    thread_context.clear_all_context()
    try:
        code = ('[sense:search]{query:"한국 증시"} >> '
                '[table:filter]{where:"title ~= \'모닝 브리프|자사주 매입|30조 배당\'"}')
        result = json.loads(unified._execute_ibl_unified_impl(
            {"code": code, "edition":2, "check": check_only}, str(tmp_path)))
        assert (result.get("ok") is False or result.get("success") is False), result
        assert result.get('issues') or result.get('diagnostic')
        assert calls == []
    finally:
        thread_context.restore(snapshot)


if __name__ == "__main__":
    sys.exit(pytest.main([__file__] + sys.argv[1:]))
