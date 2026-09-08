"""조건에 따른 집합 변경과 표본 잘림을 구분하는 회귀. 실제 데이터·외부 API는 쓰지 않는다."""
import importlib.util
import json
from pathlib import Path
import sqlite3

import pytest
import boot_paths  # noqa: F401
from ibl_honesty import scope_violation

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('_population_dataops', ROOT / 'data/packages/installed/tools/data-ops/handler.py')
H = importlib.util.module_from_spec(spec)
spec.loader.exec_module(H)


def envelope(rows, table=False, truncated=False, total=None):
    out = {'success': True, 'total': len(rows) if total is None else total, 'truncated': truncated,
           'summary': {'old': len(rows)}}
    if table:
        keys = list(rows[0]) if rows else ['id', 'verdict']
        out['table'] = {'columns': keys, 'rows': [[r[k] for k in keys] for r in rows]}
    else:
        out.update(items=rows, count=len(rows))
    return out


def size(out):
    if 'items' in out:
        return len(out['items'])
    return len((out.get('table') or out)['rows'])


@pytest.mark.parametrize('table', [False, True])
def test_filter_then_select_is_complete_new_population(table):
    rows = [{'id': i, 'verdict': '관심' if i < 25 else '보류'} for i in range(70)]
    src = envelope(rows, table)
    before = json.dumps(src)
    selected = H._op_filter(src, {'where': 'verdict == 관심'})
    out = H._op_select(selected, {'columns': ['id']})
    assert out['success'] and size(out) == out['total'] == 25
    assert not out.get('truncated') and 'summary' not in out
    assert scope_violation(out) is None
    assert json.dumps(src) == before  # 입력 봉투 비파괴


@pytest.mark.parametrize('table', [False, True])
@pytest.mark.parametrize('op,params,n', [('filter', {'where': 'id > 100'}, 0),
                                       ('dedup', {'by': 'id'}, 2),
                                       ('groupby', {'by': 'id'}, 2)])
@pytest.mark.parametrize('truncated', [False, True])
def test_population_operators_preserve_real_upstream_loss(table, op, params, n, truncated):
    src = envelope([{'id': 1}, {'id': 1}, {'id': 2}], table, truncated, 100 if truncated else 3)
    out = getattr(H, '_op_' + op)(src, params)
    assert out['success'] and size(out) == out['total'] == n, out
    assert bool(out.get('truncated')) == truncated, out
    assert 'summary' not in out


def test_sampling_and_population_order():
    src = envelope([{'id': i} for i in range(10)])
    filtered = H._op_filter(src, {'where': 'id < 5'})
    sampled = H._op_take(filtered, {'n': 2})
    assert sampled['total'] == 5 and sampled['truncated'] and size(sampled) == 2
    sampled_first = H._op_take(src, {'n': 5})
    out = H._op_filter(sampled_first, {'where': 'id < 2'})
    assert out['total'] == 2 and out['truncated'] and size(out) == 2
    # 모든 행이 조건에서 제외돼도 원천 누락은 사라지지 않는다.
    empty = H._op_filter(sampled_first, {'where': 'id > 100'})
    grouped = H._op_groupby(empty, {'by': 'id'})
    assert grouped['total'] == 0 and grouped['truncated']


def test_merge_flatten_and_since_restate_population(monkeypatch, tmp_path):
    a = envelope([{'id': 1}, {'id': 2}])
    out = H._op_merge([a, a], {'by': 'id'})
    assert out['total'] == size(out) == 2 and not out.get('truncated')
    union = H._op_union([a, a], {})
    assert union['total'] == size(union) == 4 and not union.get('truncated')
    flat = H._op_flatten(envelope([{'xs': []}, {'xs': [{'id': 1}]}]), {'field': 'xs'})
    assert flat['total'] == size(flat) == 1 and not flat.get('truncated')
    db = tmp_path / 'since.db'
    def conn():
        c = sqlite3.connect(db)
        c.execute('CREATE TABLE IF NOT EXISTS since_seen (stream TEXT NOT NULL, k TEXT NOT NULL, watched TEXT, first_seen TEXT NOT NULL, last_seen TEXT NOT NULL, PRIMARY KEY(stream,k))')
        return c
    monkeypatch.setattr(H, '_since_conn', conn)
    first = H._op_since(a, {'key': 'test', 'by': 'id'})
    assert first['total'] == size(first) == 0 and not first.get('truncated')


def test_literal_compute_needs_no_dummy_action():
    from tool_context import ToolContext
    out = H.execute({'items': [{'보증금': 9000, '면적': 99}],
                     'set': {'㎡당만원': 'round(보증금 / 면적, 0)'}},
                    ToolContext(str(ROOT), 'data_compute'))
    out = json.loads(out) if isinstance(out, str) else out
    assert out['success'] and out['items'][0]['㎡당만원'] == 91
    assert 'passthrough_rows' not in out


if __name__ == '__main__':
    raise SystemExit(pytest.main([__file__, '-q']))
