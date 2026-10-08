"""Round 68: durable reuse, lifecycle, diagnostics and producer selection scopes."""
import ast
import importlib.util
import json
from pathlib import Path
import sqlite3

import boot_paths  # noqa: F401
import pytest
from filelock import FileLock

from common.currency import bounded_selection
from ibl_run_journal import (Journal, inspect_run, reusable_receipts,
                             migrate_completed_runs, validate_resume)
from ibl_v2_adapters import Adapter, Adapted, load_registry
from ibl_v2_analysis import syntax_report, HINTS
from ibl_v2_compile import compile_program
from ibl_v2_ir import Fault, pack
from ibl_v2_runtime import Runtime
from test_ibl_general_capabilities import adapter, boundary  # noqa: F401

ROOT = Path(__file__).resolve().parents[1]
TOOLS = ROOT / 'data/packages/installed/tools'


def module(relative):
    spec = importlib.util.spec_from_file_location('round68_' + Path(relative).stem, TOOLS / relative)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.mark.parametrize('order,expected', [
    ('read_write', 0), ('write_read', 1), ('overlap_read_first', 0), ('overlap_write_first', 0)])
def test_source_mutation_order_and_overlap(tmp_path, order, expected):
    with Journal(tmp_path, 'one') as j:
        def begin_read():
            j.begin('r', 'r', reusable=True, state_change=False)
        def finish_read():
            j.finish('r', {'value': pack(1), 'reuse_key': 'read'})
        def begin_write():
            j.begin('w', 'w', state_change=True)
        def finish_write():
            j.finish('w', {'value': pack(2), 'reuse_key': 'write'})
        ops = {'read_write': [begin_read, finish_read, begin_write, finish_write],
               'write_read': [begin_write, finish_write, begin_read, finish_read],
               'overlap_read_first': [begin_read, begin_write, finish_write, finish_read],
               'overlap_write_first': [begin_write, begin_read, finish_write, finish_read]}
        for op in ops[order]:
            op()
        summary = {'read_calls': expected, 'state_change_possible': True}
        if expected == 0:
            summary.update(read_exclusions=[{'reason': 'unknown_write_resources',
                'write_call_id': 'w', 'excluded_calls': 1}], read_exclusions_total=1)
        assert j.reuse_summary() == summary
        j.complete({'success': True, 'source_complete': True})
    assert len(reusable_receipts(tmp_path, j.run_id)) == expected


def test_append_reuse_keeps_prior_write_and_safe_post_write_reads(tmp_path):
    data = ['A']
    reg = {'t:read': adapter(lambda *_: ''.join(data), result='Text'),
           't:write': Adapter({'version': 1, 'params': {'text': 'Text'}, 'result': 'Null',
                               'effects': ['write_external']}, lambda rt, a: data.__setitem__(slice(None), [a['text']]))}
    def code(tail):
        return f'$x=[t:read]{{}}; [t:write]{{text:$x+"{tail}"}}; return [t:read]{{}}'
    with Journal(tmp_path, 'first') as j:
        first = Runtime(compile_program(code('B'), reg), journal=j).run()
    assert first['success'], first
    assert first['continuation']['state_change_possible'] and first['continuation']['read_calls'] == 1
    second = Runtime(compile_program(code('C'), reg), reusable=reusable_receipts(tmp_path, j.run_id), reuse_run=j.run_id).run()
    assert second['success'] and second['value'] == 'ABC', second


def test_clock_per_run_is_fresh_for_reuse_but_stable_on_resume(tmp_path):
    ticks = []
    reg = {'t:time': adapter(lambda *_: ticks.append(1) or len(ticks), per_run=True)}
    plan = compile_program('return [t:time]{}', reg)
    with Journal(tmp_path, 'same') as j:
        first = Runtime(plan, journal=j).run()
    candidates = reusable_receipts(tmp_path, j.run_id)
    assert not candidates and 'continuation' not in first
    assert Runtime(plan, reusable=candidates).run()['value'] == 2
    with Journal(tmp_path, 'same', {'run_id': j.run_id}) as resumed:
        assert Runtime(plan, journal=resumed).run()['value'] == 1
    assert len(ticks) == 2


@pytest.mark.parametrize('source', [
    '$x=[t:read]{} ?? 9; return $x',
    '$x=0; [try] { $x=[t:read]{} } [catch] { $x=9 }; return $x',
    'return [t:partial]{}'])
def test_normal_return_has_independent_completion_axes(tmp_path, source):
    def fail(*_):
        raise Fault('TOOL', 'failed')
    reg = {'t:read': adapter(fail),
           't:partial': adapter(lambda *_: Adapted(9, {'incomplete': True}))}
    with Journal(tmp_path, 'run') as j:
        result = Runtime(compile_program(source, reg), journal=j).run()
    assert result['success'], result
    state = inspect_run(tmp_path, j.run_id)
    assert state['status'] == 'completed' and state['source_complete'] is False


def test_migration_is_backed_up_idempotent_and_excludes_uncertain_and_failed(tmp_path):
    runs = tmp_path / 'runs'
    ids = []
    for i in range(4):
        with Journal(runs, str(i)) as j:
            j.begin('r', 'r')
            if i != 1:
                j.finish('r', {'value': pack(1)})
            j.complete({'success': False})
        ids.append(j.run_id)
        with sqlite3.connect(runs / (j.run_id + '.sqlite')) as db:
            db.execute("UPDATE lifecycle SET status='interrupted', reason=?, ended=1", ('real failure' if i == 2 else None,))
            if i == 3:
                db.execute("UPDATE meta SET blocked='cleanup'")
    assert migrate_completed_runs(runs)['candidates'] == 1
    assert inspect_run(runs, ids[0])['status'] == 'interrupted'
    backup = tmp_path / 'backup'
    assert migrate_completed_runs(runs, backup_dir=backup)['updated'] == 1
    assert inspect_run(runs, ids[0])['status'] == 'completed'
    with sqlite3.connect(backup / (ids[0] + '.sqlite')) as db:
        assert db.execute('SELECT status FROM lifecycle').fetchone()[0] == 'interrupted'
    assert migrate_completed_runs(runs, backup_dir=backup)['updated'] == 0
    assert all(inspect_run(runs, run_id)['status'] != 'completed' for run_id in ids[1:])


def test_check_validates_handles_without_mutating_journal(boundary, tmp_path):
    from ibl_v2_entry import handle_request
    req = {'edition': 2, 'code': 'return 1'}
    result = handle_request(req, str(tmp_path))
    run_id = result['resume']['run_id']
    path = tmp_path / 'runs' / (run_id + '.sqlite')
    before = path.read_bytes()
    for handle in ('resume', 'reuse'):
        checked = handle_request({**req, 'check': True, handle: {'run_id': run_id}}, str(tmp_path))
        assert checked['ok'], checked
        missing = handle_request({**req, 'check': True, handle: {'run_id': '0' * 32}}, str(tmp_path))
        assert missing['diagnostic']['code'] == handle.upper() + '_NOT_FOUND'
        malformed = handle_request({**req, 'check': True, handle: {'bad': run_id}}, str(tmp_path))
        assert malformed['diagnostic']['code'] == handle.upper() + '_ARGUMENT'
    changed = handle_request({**req, 'code': 'return 2', 'check': True, 'resume': {'run_id': run_id}}, str(tmp_path))
    assert changed['diagnostic']['code'] == 'RESUME_CHANGED'
    assert path.read_bytes() == before
    with FileLock(str(path) + '.lock'):
        with pytest.raises(Fault, match='진행 중'):
            validate_resume(path.parent, {'run_id': run_id}, 'wrong')


def test_all_literal_fault_codes_have_nonsyntax_fallback_and_unknown_future_codes():
    codes = set()
    for path in (ROOT / 'backend').rglob('*.py'):
        if path.name.startswith('test_'):
            continue
        for node in ast.walk(ast.parse(path.read_text())):
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == 'Fault':
                if node.args and isinstance(node.args[0], ast.Constant) and isinstance(node.args[0].value, str):
                    codes.add(node.args[0].value)
    assert len(codes) > 70
    for code in codes | {'FUTURE_PROTOCOL_CODE'}:
        if code == 'SYNTAX':
            continue
        for kind in ('compile', 'permission', 'protocol'):
            assert syntax_report(Fault(code, 'test', kind=kind), '')['diagnostic']['hint'] != HINTS['SYNTAX']


@pytest.fixture(scope='module')
def actual_registry():
    return load_registry(str(ROOT / 'projects/컨텐츠'), None)


@pytest.mark.parametrize('expression', [
    '[table:filter]{where:($r)=>$r.nmae=="a"}',
    '[table:sort]{by:"nmae"}', '[table:select]{columns:["nmae"]}',
    '[table:dedup]{by:"nmae"}',
    '[table:take]{n:1} >> [table:each]{return $it.nmae}',
    '[table:filter]{where:($r)=>$r.name=="a"} >> [table:each]{return $it.nmae}',
    '[table:sort]{by:"name"} >> [table:each]{return $it.nmae}',
    # dedup retains its legacy Record envelope.
    '[table:compute]{set:($r)=>{tag:$r.nmae}}',
])
def test_observed_fields_across_row_transformers(actual_registry, expression):
    plan = compile_program('$d=[self:list]{path:"."}; return $d >> ' + expression, actual_registry)
    assert not plan.issues, plan.report()
    warnings = [w for w in plan.preflight['warnings'] if w['code'] == 'UNOBSERVED_FIELD']
    assert len(warnings) == 1 and warnings[0]['facts']['field'] == 'nmae', plan.report()


@pytest.mark.parametrize('requested,boundary,retained,scope', [
    (3, 3, 3, 'selection'), (None, 3, 3, 'source'), (4, 3, 3, 'source'),
    (3, 3, 2, 'source'), (True, 1, 1, 'source'), ('3', 3, 3, 'source'),
    (3.5, 3, 3, 'source')])
def test_selection_requires_exact_explicit_fulfilled_boundary(requested, boundary, retained, scope):
    assert bounded_selection(requested, boundary, retained, True)['truncations'][0]['scope'] == scope
    assert bounded_selection(requested, boundary, retained, False) == {}


def test_sqlite_limit_and_blob_are_json_safe(tmp_path):
    sql = module('system_essentials/sqlite_ops.py')
    path = tmp_path / 'source.db'
    with sqlite3.connect(path) as db:
        db.execute('create table sample(n, b, empty, text, real)')
        db.executemany('insert into sample values(?, ?, ?, ?, ?)', [(i, b'\0\xff', None, '한글', 1.25) for i in range(220)])
    args = {'path': str(path), 'query': 'select * from sample'}
    explicit = sql.op_query({**args, 'limit': 3})
    assert explicit['success'] and len(explicit['items']) == 3
    assert explicit['truncations'][0]['scope'] == 'selection'
    assert sql.op_query(args)['truncations'][0]['scope'] == 'source'
    first = json.loads(json.dumps(explicit))['items'][0]
    assert first == {'n': 0, 'b': {'$blob': {'bytes': 2, 'hex': '00ff'}}, 'empty': None, 'text': '한글', 'real': 1.25}
    assert explicit['markers']['blob_columns'] == ['b']
    assert not sql.op_query({**args, 'query': 'delete from sample'})['success']


def test_dedup_preserves_observations_in_legacy_items(actual_registry):
    plan = compile_program('$d=[self:list]{path:"."}; $x=$d >> [table:dedup]{by:"name"}; '
                           'return $x.items >> [table:each]{return $it.nmae}', actual_registry)
    assert not plan.issues, plan.report()
    assert [w['facts']['field'] for w in plan.preflight['warnings'] if w['code'] == 'UNOBSERVED_FIELD'] == ['nmae']


def test_literal_sort_keys_keep_runtime_sparse_field_validation(actual_registry):
    plan = compile_program('return [{obj:{name:"a"},xs:[{n:1}]}] >> [table:sort]{by:"obj.name"}', actual_registry)
    assert not plan.issues, plan.report()
    assert not plan.preflight['warnings']


def test_new_producer_requires_own_classification():
    spec = importlib.util.spec_from_file_location('round68_guard', ROOT / 'scripts/check_honesty_propagation.py')
    guard = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(guard)
    source = 'out={"truncated":True}  # truncation-scope: source — safety cap\nout["truncated"]=True\n'
    assert guard.unclassified_truncations(source) == [2]
    assert guard.unclassified_truncations('out.update(truncated=True)') == [1]
    assert guard.unclassified_truncations('truncated=True\nx=out.get("truncated")') == []


def test_freelance_explicit_limit_and_unfilled_filter(monkeypatch):
    mod = module('freelance-services/tool_freelance.py')
    monkeypatch.setattr(mod, '_get_json', lambda *a: {'totalItemCount': 100, 'gigs': [
        {'gigId': 1, 'title': 'A', 'price': 100}, {'gigId': 2, 'title': 'B', 'price': 200}]})
    selected = mod._search_gigs('q', 2, 'ranking', None, requested=2)
    assert selected['truncations'][0]['scope'] == 'selection'
    default = mod._search_gigs('q', 2, 'ranking', None)
    assert default['truncations'][0]['scope'] == 'source'
    short = mod._search_gigs('q', 4, 'ranking', 150, requested=4)
    assert short['truncations'][0]['scope'] == 'source'


def test_month_source_errors_cannot_be_mistaken_for_selection(monkeypatch):
    mod = module('real-estate/realty_molit_common.py')
    good = '<response><resultCode>000</resultCode><totalCount>9</totalCount><items><item><n>1</n></item></items></response>'
    monkeypatch.setattr(mod, '_get', lambda *_: good)
    selected = mod.fetch_month_paged('https://example.invalid/', '', 'x', '202601', 1, lambda *_: {'n': 1})
    assert selected['truncations'][0]['scope'] == 'selection'
    def failed(*_):
        raise ValueError('broken response')
    monkeypatch.setattr(mod, '_get', failed)
    partial = mod.fetch_month_paged('https://example.invalid/', '', 'x', '202601', 1, lambda *_: {})
    assert partial['error'] and partial['truncations'][0]['scope'] == 'source'


def test_price_history_selection_uses_raw_author_argument():
    mod = module('investment/handler.py')
    def result():
        return {'success': True, 'data': {'prices': [{'date': str(i), 'close': i} for i in range(5)],
                                         'truncated': True, 'total_days': 200}}
    assert mod._attach_price_table(result(), {'max_points': 5})['truncations'][0]['scope'] == 'selection'
    assert mod._attach_price_table(result())['truncations'][0]['scope'] == 'source'
    assert mod._attach_price_table(result(), {'max_points': 10})['truncations'][0]['scope'] == 'source'


if __name__ == '__main__':
    raise SystemExit(pytest.main([__file__]))
