"""현행 조건의 필드·빈 값 관측과 since 첫 검침 계약."""
import importlib.util
import sqlite3
import sys
import tempfile
from pathlib import Path
import boot_paths  # noqa: F401
import pytest
from ibl_v2_compile import compile_program
from ibl_v2_runtime import Runtime


def test_since_seeded_flag(monkeypatch):
    """P1: 첫 검침 seeded:true, 2회차 미표기."""
    spec = importlib.util.spec_from_file_location(
        "dataops_handler",
        Path(__file__).resolve().parents[1]
        / "data/packages/installed/tools/data-ops/handler.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)

    td = tempfile.mkdtemp()
    db = str(Path(td) / "since.db")

    def fake_conn():
        conn = sqlite3.connect(db, timeout=10)
        conn.execute(
            "CREATE TABLE IF NOT EXISTS since_seen ("
            " stream TEXT NOT NULL, k TEXT NOT NULL, watched TEXT,"
            " first_seen TEXT NOT NULL, last_seen TEXT NOT NULL,"
            " PRIMARY KEY (stream, k))")
        return conn

    monkeypatch.setattr(mod, "_since_conn", fake_conn)
    prev = {"items": [{"url": "http://a", "title": "A"}]}
    r1 = mod._op_since(prev, {"key": "테스트스트림"})
    assert r1.get("seeded") is True and r1["items"] == [], r1
    r2 = mod._op_since(prev, {"key": "테스트스트림"})
    assert "seeded" not in r2, r2


@pytest.mark.parametrize('expression, expected', [
    ('$data.items[0].max_temp', 30.3), ('$data.current.temp', 24.7),
    ('$data.items[1].battery', None),
])
def test_direct_and_bound_current_field_paths_agree(expression, expected):
    data = {'items': [{'max_temp': 30.3}, {'battery': None}], 'current': {'temp': 24.7}}
    for code in ('return ' + expression, '$copy = $data; return ' + expression.replace('$data.', '$copy.')):
        result = Runtime(compile_program(code, {}, inputs={'data': data}), {'data': data}).run()
        assert result['success'] is True and result['value'] == expected


@pytest.mark.parametrize('expression', ['$data.items[9].max_temp', '$data.current.missing', '$data.missing'])
def test_missing_field_does_not_choose_false_branch(expression):
    code = '[if: ' + expression + ' == null]{return "false branch"} [else]{return "other"}'
    data = {'items': [], 'current': {}}
    result = Runtime(compile_program(code, {}, inputs={'data': data}), {'data': data}).run()
    assert result['success'] is False and (result.get('diagnostic') or result.get('issues'))


if __name__ == '__main__':
    raise SystemExit(pytest.main([__file__, *sys.argv[1:]]))
