"""Deferred observation receipts reflect database state across program boundaries."""
import sqlite3
from pathlib import Path

import boot_paths  # noqa: F401
import pytest
from common.pkg_utils import load_sibling
from execution_commit import CommitScope, bind_scope, committed_program
from ibl_v2_adapters import Adapter, load_registry
from ibl_v2_compile import compile_program
from ibl_v2_runtime import Runtime

PKG = Path(__file__).resolve().parents[1] / 'data/packages/installed/tools/data-ops/handler.py'
SINCE = load_sibling(str(PKG), 'since_ops')
SEMANTICS = load_sibling(str(PKG), 'dataops_value_semantics')


@pytest.fixture
def observation(tmp_path):
    def connect():
        conn = sqlite3.connect(tmp_path / 'since.db')
        conn.execute('CREATE TABLE IF NOT EXISTS since_seen (stream TEXT, k TEXT, watched TEXT, first_seen TEXT, last_seen TEXT, PRIMARY KEY(stream,k))')
        return conn
    def since(rows, peek=False, by="id"):
        return SINCE.op_since({'items': rows}, {'key': 'test', 'by': by, 'peek': peek},
            lambda x: (x['items'], x), lambda env, items, **kw: {'items': items},
            lambda *a: {'error': a}, lambda *a: {'error': a}, SEMANTICS, connect)
    return since, connect


@pytest.mark.parametrize('failure', ['', '[try] { [self:read]{path:"missing"} } [catch] { 0 }',
                                  'assert false, "uncaught"'])
def test_runtime_commit_receipt_matches_persisted_baseline(observation, failure):
    since, connect = observation
    registry = load_registry()
    from ibl_v2_ir import Fault
    def missing(rt, args):
        raise Fault('TOOL', 'missing')
    registry['self:read'] = Adapter(registry['self:read'].contract, missing)
    registry['table:since'] = Adapter(registry['table:since'].contract, lambda rt, args: since(args['items']))
    code = '$s=[table:since]{items:[{id:1}],key:"test",by:"id"}\n' + failure + '\nreturn $s'
    plan = compile_program(code, registry, {})
    assert not plan.issues, plan.report()
    result = Runtime(plan, {}).run()
    committed = not failure
    assert result['state_commit']['status'] == ('committed' if committed else 'not_committed')
    with connect() as conn:
        assert conn.execute('SELECT count(*) FROM since_seen').fetchone()[0] == int(committed)
    if result['success']:
        assert result['value']['state_committed'] is None
        assert '저장 대기' in result['value']['note']
    next_value = since([{'id': 1}, {'id': 2}])
    assert next_value['state_committed'] is True
    assert [r['id'] for r in next_value['items']] == ([2] if committed else [])


def test_direct_peek_and_nested_commit_owner(observation):
    since, connect = observation
    assert since([], peek=True)['state_committed'] is False
    @committed_program
    def inner():
        return {'success': True, 'value': since([{'id': 1}])}
    @committed_program
    def outer():
        nested = inner()
        assert nested['state_commit']['status'] == 'pending'
        return {'success': True, 'source_complete': False, 'nested': nested}
    out = outer()
    assert out['state_commit']['status'] == 'not_committed'
    with connect() as conn:
        assert conn.execute('SELECT count(*) FROM since_seen').fetchone()[0] == 0


def test_commit_failure_reports_partial_without_reapplying_completed_actions():
    scope = CommitScope()
    calls = []
    scope.actions['a'] = lambda: calls.append('a')
    def failed():
        raise OSError('disk full')
    scope.actions['b'] = failed
    with pytest.raises(OSError):
        scope.commit()
    result = {'success': False}
    scope.report(result)
    assert result['state_commit']['status'] == 'failed'
    assert result['state_commit']['committed'] == 1
    assert result['state_commit']['reason'] == 'commit_failed'
    scope.actions['b'] = lambda: calls.append('b')
    scope.commit()
    assert calls == ['a', 'b']


@pytest.mark.system
@pytest.mark.parametrize('corrected', [False, True])
def test_complete_marketing_program_preserves_ledger_and_reports_commit(tmp_path, monkeypatch, observation, corrected):
    """Whole original programs; recorded model/search/media outputs, real local I/O and state."""
    import copy
    import csv
    import importlib.util
    import json
    import shutil
    from collections import defaultdict, deque
    from ibl_v2_ir import unpack
    from ibl_v2_adapters import decode_envelope
    from ibl_v2_compat import plain_arguments

    root = Path(__file__).resolve().parents[1]
    report = root / 'docs/experiments/long_sentence_imagination/round_43'
    def module(name):
        spec = importlib.util.spec_from_file_location('lsi43_' + name, report / 'harness' / (name + '.py'))
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        return mod
    prepare, verify = module('prepare'), module('verify')
    source, out, oracle = tmp_path / 'input', tmp_path / 'out', tmp_path / 'oracle'
    rows, labels = prepare.write_inputs(source)
    reactions = prepare.make_reactions(tmp_path / 'staging')
    prepare.oracle(rows, labels, reactions, oracle)
    out.mkdir()
    library = {r['alias']: r['ibl_code'] for r in json.loads(
        (root / 'data/idioms/legacy_port_seeds.json').read_text()) if r['alias']}
    ledger = load_sibling(str(root / 'data/packages/installed/tools/system_essentials/handler.py'), 'ledger_ops')
    monkeypatch.setattr(ledger, '_ROOT', tmp_path)
    since, connect = observation
    for stage, filename in [('base', 'main_v0'), ('react', 'react_v1')]:
        if stage == 'react':
            shutil.copytree(tmp_path / 'staging/reactions', source / 'reactions')
            if corrected:
                path = source / 'reactions/reactions.csv'
                with path.open(newline='') as f:
                    reader = csv.DictReader(f)
                    fields, data = reader.fieldnames, list(reader)
                with path.open('w', newline='') as f:
                    writer = csv.DictWriter(f, fieldnames=fields)
                    writer.writeheader(); writer.writerows(reversed(data))
        records = json.loads((report / 'evidence' / f'trainer_{stage}_{filename}.json').read_text())['response']['recordings']
        fixture = defaultdict(deque)
        for receipt in records:
            if 'value' in receipt:
                fixture[receipt['action']].append(unpack(receipt['value']))
        registry = load_registry(str(tmp_path))
        registry['self:time'] = Adapter(registry['self:time'].contract, lambda rt, args: '2026-10-09')
        for key in ['table:ai', 'table:brief', 'sense:search', 'engines:image_gemini', 'table:document']:
            def replay(rt, args, action=key):
                value = copy.deepcopy(fixture[action].popleft())
                if action in ['engines:image_gemini', 'table:document']:
                    target = Path(args['output_path'] if action == 'engines:image_gemini' else args['filename'] + '.png')
                    target.parent.mkdir(parents=True, exist_ok=True)
                    # Existing PNG fixture stands in for media generation; visual quality is not tested here.
                    shutil.copyfile(report / 'artifacts/agent/A2_card.png', target)
                    value['path'] = str(target)
                return value
            registry[key] = Adapter(registry[key].contract, replay)
        registry['table:since'] = Adapter(registry['table:since'].contract, lambda rt, args: since(args['items']['items'] if isinstance(args['items'], dict) else args['items'], by='url'))
        registry['self:ledger'] = Adapter(registry['self:ledger'].contract,
            lambda rt, args: decode_envelope(getattr(ledger, 'op_' + args['op'])(plain_arguments(args)), {})[0])
        code = (report / 'drafts' / (filename + '.ibl')).read_text()
        if corrected and stage == 'react':
            code = code.replace('target:"items",key:"asset_id"', 'key:"asset_id"')
        inputs = {'src': str(source), 'out': str(out)}
        plan = compile_program(code, registry, inputs, library)
        assert not plan.issues, plan.report()
        from ibl_v2_runtime import Budget
        result = Runtime(plan, inputs, budget=Budget(steps=1_000_000, rows=100_000)).run()
        assert result['success'], result
        checks, _ = getattr(verify, 'verify_' + stage)(out, source, oracle)
        assert all(checks.values()), checks
        if stage == 'react':
            assert result['source_complete'] is corrected, result['value']['ledger_update']
            assert result['state_commit']['status'] == ('committed' if corrected else 'not_committed')
            saved = json.loads((out / 'campaign_ledger.json').read_text())
            assert isinstance(saved, list if corrected else dict)
            with connect() as conn:
                count = conn.execute('SELECT count(*) FROM since_seen').fetchone()[0]
                assert (count > 0) is corrected


if __name__ == "__main__":
    import sys
    import pytest
    raise SystemExit(pytest.main([__file__, *sys.argv[1:]]))
