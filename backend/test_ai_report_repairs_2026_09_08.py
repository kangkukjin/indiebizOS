"""AI 동향보고서 현장 신호: 원장 오염, 괄호 변수 분기, 산문 수집 회귀."""
import importlib.util
import json
from pathlib import Path

import pytest
import boot_paths  # noqa: F401
from ibl_typecheck import typecheck_code

ROOT = Path(__file__).resolve().parents[1]
PROGRAM = '''
$기술 = [table:compute]{items:[{id:1},{id:2},{id:3}],set:{x:1}};
$사례 = [table:compute]{items:[{id:4}],set:{x:2}};
($기술 >> [table:take]{n:-2}) & $사례 >> [table:union]
'''










@pytest.fixture
def ledger(tmp_path, monkeypatch):
    spec = importlib.util.spec_from_file_location('report_ledger_probe', ROOT / 'data/packages/installed/tools/system_essentials/ledger_ops.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    monkeypatch.setattr(module, '_ROOT', tmp_path)
    return module


@pytest.mark.parametrize('bad', ['{date:"2026-09-07",tags:["a"]}', 1, False, ['a']])
def test_ledger_rejects_nonobject_input_atomically(ledger, tmp_path, bad):
    path = tmp_path / 'ledger.json'
    path.write_text('[{"date":"2026-09-08","tags":["정상"]}]')
    before = path.read_bytes()
    result = ledger.op_append({'path': str(path), 'items': [{'date': 'new'}, bad]})
    assert not result['success'] and '객체' in result['error']
    assert path.read_bytes() == before
    path2 = tmp_path / 'new.json'
    assert not ledger.op_append({'path': str(path2), 'item': bad})['success']
    assert not path2.exists()


def test_ledger_reports_corrupt_rows_even_when_filter_would_hide_them(ledger, tmp_path):
    path = tmp_path / 'ledger.json'
    path.write_text('[{"date":"2026-09-08"},"broken"]')
    before = path.read_bytes()
    for call in (ledger.op_select, ledger.op_append):
        out = call({'path': str(path), 'where': {'date': '2026-09-08'}, 'item': {'date': 'new'}})
        assert not out['success'] and '첫 위치 2' in out['error']
        assert path.read_bytes() == before




if __name__ == '__main__':
    raise SystemExit(pytest.main([__file__, '-q']))
