"""보고서의 ledger where 0건 사고: 두 표면의 조건 판정과 원장 불변 검증."""
import importlib.util
import json
from pathlib import Path

import pytest
import boot_paths  # noqa: F401

ROOT = Path(__file__).resolve().parents[1]
PKG = ROOT / 'data/packages/installed/tools'


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture
def surfaces(tmp_path, monkeypatch):
    monkeypatch.syspath_prepend(str(PKG / 'data-ops'))
    table = load('ledger_where_table', PKG / 'data-ops/handler.py')
    ledger = load('ledger_where_ops', PKG / 'system_essentials/ledger_ops.py')
    monkeypatch.setattr(ledger, '_ROOT', tmp_path)
    return ledger, table


ROWS = [
    {'id': 1, 'label': 'NEW', 'score': 10, 'date': '2026-09-07'},
    {'id': 2, 'label': ' new ', 'score': '20', 'date': '2026-09-06'},
    {'id': 3, 'label': 'ONGOING', 'score': None, 'date': '2026-08-01'},
]


@pytest.mark.parametrize('where,ids', [
    ({'field': 'label', 'op': 'eq', 'value': 'NEW'}, [1, 2]),
    ({'label': 'NEW'}, [1, 2]),
    ('score >= 15', [2]),
    ('label == NEW and score >= 15 or id == 3', [2, 3]),
    ([{'label': 'NEW'}, {'field': 'score', 'op': 'gte', 'value': 15}], [2]),
    ({'field': 'date', 'op': 'ge', 'value': '2026-09-01'}, [1, 2]),
    ({'field': 'id', 'op': 'not_in', 'value': [1, 3]}, [2]),
    ({'field': 'score', 'op': 'eq', 'value': None}, [3]),
    ({'label': 'ABSENT'}, []),
])
def test_same_rows_and_read_only(surfaces, tmp_path, where, ids):
    ledger, table = surfaces
    p = tmp_path / 'rows.json'
    p.write_text(json.dumps(ROWS))
    before = p.read_bytes()
    got = ledger.op_select({'path': str(p), 'where': where})
    other = table._op_filter({'items': ROWS}, {'where': where})
    assert got['success'] and other.get('success', True)
    assert [r['id'] for r in got['items']] == ids
    assert got['items'] == other['items']
    assert p.read_bytes() == before


@pytest.mark.parametrize('where', [
    {'field': 'label', 'op': 'unknown', 'value': 'NEW'},
    {'field': 'label', 'op': 'matches', 'value': '['},
    'label contains NEW and background',
])
def test_errors_are_not_empty_success(surfaces, tmp_path, where):
    ledger, table = surfaces
    p = tmp_path / 'rows.json'
    p.write_text(json.dumps(ROWS))
    assert ledger.op_select({'path': str(p), 'where': where})['success'] is False
    assert table._op_filter({'items': ROWS}, {'where': where})['success'] is False


def test_nested_paths_projection_limit(surfaces, tmp_path):
    ledger, _ = surfaces
    p = tmp_path / 'rows.json'
    p.write_text(json.dumps({'queue': [
        {'meta': {'label': 'NEW'}, 'values': [10]},
        {'meta': {'label': 'NEW'}, 'values': [20]},
    ]}))
    for where in ({'meta.label': 'NEW'},
                  {'field': 'meta.label', 'op': 'eq', 'value': 'NEW'},
                  'meta.label == NEW'):
        got = ledger.op_select({'path': str(p), 'target': 'queue', 'where': where,
                                'fields': ['values.0'], 'limit': 1})
        assert got['success'] and got['items'] == [{'values.0': 10}]
        assert got['total'] == 2 and got['truncated']


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
