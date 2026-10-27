"""Public runtime budgets and complete text-editing program contracts."""
import boot_paths  # noqa: F401
import importlib.util
import json
import re
import shutil
import unicodedata
from pathlib import Path

import pytest

from ibl_v2_adapters import load_registry
from ibl_v2_compile import compile_program
from ibl_v2_entry import capabilities, handle_request
from ibl_v2_runtime import Budget, Runtime

ROUND = Path(__file__).resolve().parents[1] / 'docs/experiments/long_sentence_imagination/round_39'


def test_parallel_late_receipt_does_not_rewind_progress(monkeypatch):
    """A slower reused branch must not replace the newer branch's coordinate."""
    import threading
    import ibl_progress
    from ibl_v2_adapters import Adapter

    calls = []
    adapter = Adapter({'version': 1, 'params': {'n': 'Number'},
                       'result': 'Number', 'effects': ['read_external']},
                      lambda rt, args: calls.append(args['n']) or args['n'])
    plan = compile_program('[1,2] >> [table:each]{parallel:2} '
                           '{ return [test:read]{n:$it} }', {'test:read': adapter})
    first = Runtime(plan)
    assert first.run()['success']
    receipts = {r['reuse_key']: r for r in first.recordings}
    first_started, second_reused = threading.Event(), threading.Event()
    seen = []

    def report(ticket, step, of, action, detail=None, reused=False):
        seen.append({'step': step, 'detail': detail, 'reused': reused})
        if detail['row'] == 2 and reused:
            second_reused.set()

    class DelayedReuse(Runtime):
        def _timed_invoke(self, node, args, piped):
            if args.value['n'] == 2:
                assert first_started.wait(3)
            return super()._timed_invoke(node, args, piped)

        def _invoke(self, node, args, piped):
            if args.value['n'] == 1:
                first_started.set()
                assert second_reused.wait(3)
            return super()._invoke(node, args, piped)

    monkeypatch.setattr(ibl_progress, 'report_step', report)
    runtime = DelayedReuse(plan, reusable=receipts, reuse_run='previous')
    result = runtime.run()
    assert result['success'] and result['value'] == [1, 2], result
    assert runtime.reused_calls == 2 and sorted(calls) == [1, 2]
    assert [p['step'] for p in seen] == sorted(p['step'] for p in seen), seen
    assert seen[-1]['detail']['row'] == 2 and seen[-1]['reused'], seen


def test_parallel_compute_does_not_claim_another_branch_action_finished(monkeypatch):
    """A compute beat is not proof that another concurrent call has finished."""
    import threading
    import ibl_progress
    from ibl_v2_adapters import Adapter

    active, computing = threading.Event(), threading.Event()
    seen = []

    def read(rt, args):
        active.set()
        assert computing.wait(3)
        return 1

    class OrderedRows(Runtime):
        def each(self, node, env, args, piped):
            assert active.wait(3)
            return super().each(node, env, args, piped)

    def beat(detail):
        seen.append(dict(detail))
        if detail.get('row') == 2:
            computing.set()

    monkeypatch.setattr(ibl_progress, 'beat', beat)
    adapter = Adapter({'version': 1, 'params': {}, 'result': 'Number',
                       'effects': ['read_external']}, read)
    plan = compile_program('[test:read]{} & ([1,2] >> [table:each] { return $it*2 })',
                           {'test:read': adapter})
    assert not plan.issues, plan.report()
    result = OrderedRows(plan).run()
    assert result['success'], result
    assert all(d.get('phase') != 'compute' for d in seen), seen


@pytest.mark.parametrize('count', [0, 25, 2500, 5000, 10000])
def test_saved_pure_each_program_reuses_reads_and_publishes_last_coordinate(tmp_path, monkeypatch, record_property, count):
    """Run the unchanged S7 program, then reuse it with empty/small/full inputs."""
    import ibl_progress
    source = (Path(__file__).resolve().parents[1] /
              'docs/experiments/long_sentence_imagination/round_100/subjects/s7_reuse_pure.ibl').read_text()
    fixture = tmp_path / 'fixture.txt'
    fixture.write_text('progress fixture\n')
    inputs = {'파일': str(fixture), '목록': list(range(1, count + 1))}
    seen = []
    monkeypatch.setattr(ibl_progress, 'report_step',
                        lambda ticket, step, of, action, **kw: seen.append({'step': step, 'action': action, **kw}))
    monkeypatch.setattr(ibl_progress, 'beat', lambda detail: seen.append({'beat': detail}))
    first = handle_request({'edition': 2, 'code': source, 'inputs': inputs}, project_path=str(tmp_path))
    record_property('first_usage', json.dumps(first.get('usage'), ensure_ascii=False))
    assert first['success'], first
    seen.clear()
    second = handle_request({'edition': 2, 'code': source, 'inputs': inputs,
                             'reuse': {'run_id': first['resume']['run_id']}}, project_path=str(tmp_path))
    record_property('reuse_usage', json.dumps(second.get('usage'), ensure_ascii=False))
    assert second['success'] and second['value'] == first['value'], second
    assert second['value']['n'] == count and second['reuse']['reused_calls'] == 3, second
    expected = sum(len(f'{i}-{i*7}-{len(fixture.read_text())}') for i in inputs['목록'])
    assert second['value']['s'] == expected
    rows = [e for e in seen if 'beat' in e]
    if count:
        before = seen[:seen.index(rows[0])]
        assert before[-1]['step'] == 3 and before[-1]['reused'], before
        assert all(e['beat'].get('phase') == 'compute' for e in rows[1:]), rows[:3]


@pytest.mark.parametrize("mode", ["map", "effect"])
def test_caught_validation_partial_has_explicit_json_boundary(tmp_path, mode):
    """L86: a successful assertion is Unit, not a completed device operation."""
    prefix = f'''
#!ibl edition=2
$failure=[try] {{
  [table:each]{{items:[1,0],mode:"{mode}"}} {{
    assert $it>0,"positive required"
  }}
}} [catch] {{ $error }}
'''
    rejected = handle_request(
        {"edition": 2, "code": prefix + "\nreturn json($failure)"},
        project_path=str(tmp_path),
    )
    assert not rejected["success"]
    assert rejected["diagnostic"]["code"] == "NON_JSON_RESULT"
    assert "$.partial[0]" in rejected["error"] and "Unit" in rejected["error"]

    # A report may select serializable metadata while explicitly declaring
    # omitted partial values. Do not silently turn Unit into null or success.
    projected = handle_request({
        "edition": 2,
        "code": prefix.replace("[catch] { $error }", '''[catch] {
  json({code:$error.code,kind:$error.kind,message:$error.message,
    has_partial:$error.has_partial,partial_preserved:false,
    evidence:$error.evidence,details:$error.details})
}''') + "\nreturn $failure",
    }, project_path=str(tmp_path))
    assert projected["success"], projected.get("error")
    report = json.loads(projected["value"])
    assert report["code"] == "ASSERTION_FAILED"
    assert report["kind"] == "partial"
    assert report["message"] == "positive required"
    assert report["has_partial"] and report["partial_preserved"] is False
    assert report["evidence"]
    assert report["details"]["coverage"] == ["ok", "failed"]
    assert report["details"]["successful_indices"] == [0]
    assert report["details"]["errors"]["1"]["code"] == "ASSERTION_FAILED"
    assert not projected["source_complete"]


def test_public_budget_limit_matches_check_and_runtime():
    advertised = capabilities()['v2_budget']
    maximum = advertised['request_max']
    assert maximum == {'steps': 10_000_000, 'rows': 100_000}
    assert Budget.from_request(None).steps == 1_000_000
    for supplied in (None, {}, {'rows': 5000}):
        checked = handle_request({'edition': 2, 'code': 'return 1', 'budget': supplied, 'check': True})
        assert checked['ok'] and checked['budget']['steps'] == advertised['steps'] == 1_000_000
        result = handle_request({'edition': 2, 'code': 'return 1', 'budget': supplied})
        assert result['success'] and result['usage']['limits'] == checked['budget']
    assert advertised['rows'] == 10_000 and advertised['depth'] == 64 and advertised['seconds'] is None
    for steps in (1_000_001, maximum['steps']):
        checked = handle_request({'edition': 2, 'code': 'return 1', 'budget': {'steps': steps}, 'check': True})
        assert checked['ok'] and checked['budget']['steps'] == steps
        result = handle_request({'edition': 2, 'code': 'return 1', 'budget': checked['budget']})
        assert result['success'] and result['usage']['limits']['steps'] == steps
    failed = handle_request({'edition': 2, 'code': 'return 1', 'budget': {'steps': maximum['steps'] + 1}})
    assert not failed.get('executed') and 'BUDGET_ARGUMENT' in str(failed)


@pytest.mark.parametrize('budget,dimension', [({'steps': 2}, 'steps'), ({'rows': 2}, 'rows')])
def test_explicit_small_budget_still_stops_work(budget, dimension):
    result = handle_request({'edition': 2, 'code': '[1,2,3] >> [table:each] { return $it*2 }',
                             'budget': budget})
    assert not result['success'] and result['diagnostic']['code'] == 'BUDGET', result
    exceeded = result['diagnostic']['details']['exceeded'][dimension]
    assert exceeded == {'used': 3, 'limit': 2}


@pytest.mark.system
@pytest.mark.parametrize('variant', ['base', 'big', 'nfd_crlf', 'mixed_nfd', 'bad', 'dry', 'empty'])
def test_complete_document_revision_program(tmp_path, record_property, variant):
    spec = importlib.util.spec_from_file_location('_document_revision_fixture', ROUND / 'harness/prepare.py')
    fixture = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(fixture)
    fixture.OUT = tmp_path / 'fixture'
    fixture.generate()
    source = fixture.OUT / 'source/docs'
    if variant == 'big':
        originals = {p.name: p.read_text() for p in source.glob('*.md')}
        for path in source.glob('*.md'):
            path.unlink()
        for index in range(4):
            for name, body in originals.items():
                # All file targets, including intentionally missing ones, stay
                # within their copy. The independent oracle runs on this input.
                body = re.sub(r'(?<![\w])([a-z_0-9]+\.md)', rf'c{index}_\1', body)
                (source / f'c{index}_{name}').write_text(body)
    fixture.oracle()
    expected = json.loads((fixture.OUT / 'oracle/report.json').read_text())
    expected_bytes = {p.name: p.read_bytes() for p in (fixture.OUT / 'oracle/expected_docs').glob('*.md')}
    docs, out = tmp_path / 'docs', tmp_path / 'out'
    shutil.copytree(source, docs)
    out.mkdir()
    if variant in ('nfd_crlf', 'mixed_nfd'):
        # Input is wholly NFD. Only newly inserted terms/anchor terms are NFC;
        # every untouched character comes from the original decomposed input.
        terms = [s for _, new in fixture.TERMS for s in (new, new.replace(' ', '-'))]
        if variant == 'mixed_nfd':
            terms = [s for pair in fixture.TERMS for s in pair]
        def changed_bytes(body, *, output=False):
            preserved = terms + ([new.replace(' ', '-') for _, new in fixture.TERMS] if output else [])
            pattern = '(' + '|'.join(map(re.escape, preserved)) + ')'
            text = ''.join(part if part in preserved else unicodedata.normalize('NFD', part)
                           for part in re.split(pattern, body.decode()))
            return text.replace('\n', '\r\n').encode()
        for path in docs.glob('*.md'):
            path.write_bytes(changed_bytes(path.read_bytes()) if variant == 'mixed_nfd' else
                             unicodedata.normalize('NFD', path.read_text()).replace('\n', '\r\n').encode())
        expected_bytes = {name: changed_bytes(body, output=True) for name, body in expected_bytes.items()}
    if variant == 'bad':
        (docs / 'guide_07.md').write_bytes(b'\xffinvalid UTF-8')
    if variant == 'empty':
        for path in docs.glob('*.md'):
            path.unlink()
    before = {p.name: (p.read_bytes(), p.stat().st_mtime_ns) for p in docs.glob('*.md')}
    inputs = {'docs': str(docs), 'out': str(out), 'apply': variant != 'dry',
              'terms': [{'old': a, 'new': b} for a, b in fixture.TERMS]}
    code = (ROUND / 'drafts/main_v1.ibl').read_text()
    if variant == 'mixed_nfd':
        original = compile_program(code, load_registry(str(tmp_path)), inputs)
        dry_inputs = {**inputs, 'apply': False}
        observed = Runtime(original, dry_inputs, budget=Budget(steps=3_000_000, rows=100_000)).run()
        assert observed['success'] and observed['value']['anchors_remapped'] == 29
        assert {p.name: (p.read_bytes(), p.stat().st_mtime_ns) for p in docs.glob('*.md')} == before
        code = (ROUND / 'drafts/main_repaired.ibl').read_text()
    plan = compile_program(code, load_registry(str(tmp_path)), inputs)
    assert not plan.issues, plan.issues
    if variant == 'big':
        limited = Runtime(plan, inputs, budget=Budget.from_request({'steps': 1_000_000, 'rows': 100_000})).run()
        assert not limited['success'] and limited['diagnostic']['code'] == 'BUDGET'
        assert {p.name: (p.read_bytes(), p.stat().st_mtime_ns) for p in docs.glob('*.md')} == before
    result = Runtime(plan, inputs, budget=Budget.from_request({'steps': 3_000_000, 'rows': 100_000})).run()
    assert result['success'], result.get('error')
    record_property('usage', json.dumps(result['usage']))
    report = json.loads((out / 'report.json').read_text())
    if variant in ('dry', 'bad', 'empty'):
        assert {p.name: (p.read_bytes(), p.stat().st_mtime_ns) for p in docs.glob('*.md')} == before
        assert report['written'] == []
    if variant == 'bad':
        assert not result['source_complete'] and not report['applied']
        assert [row['file'] for row in report['failed']] == ['guide_07.md']
        return
    if variant == 'empty':
        assert report['files_total'] == 0 and report['files_changed'] == []
        return
    assert report['files_total'] == expected['files_total']
    assert sorted(report['files_changed']) == expected['files_changed']
    assert report['lines_changed_by_file'] == expected['lines_changed_by_file']
    assert report['replacements'] == expected['replacements']
    assert report['anchors_remapped'] == expected['anchors_remapped']
    assert report['broken_not_increased'] and report['reread_ok']
    assert len(report['broken_links']) == len(expected['broken_links'])
    assert len(report['headings_changed']) == len(expected['headings_changed'])
    if variant not in ('nfd_crlf', 'mixed_nfd'):
        assert sorted(report['headings_changed'], key=lambda h: (h['file'], h['old'])) == expected['headings_changed']
        assert sorted(report['broken_links'], key=lambda b: (b['file'], b['line'])) == expected['broken_links']
    if variant == 'dry':
        return
    assert {p.name: p.read_bytes() for p in docs.glob('*.md')} == expected_bytes
    snapshot = {p.name: (p.read_bytes(), p.stat().st_mtime_ns) for p in docs.glob('*.md')}
    again = Runtime(plan, inputs, budget=Budget.from_request({'steps': 3_000_000, 'rows': 100_000})).run()
    assert again['success'], again.get('error')
    report = json.loads((out / 'report.json').read_text())
    assert report['written'] == report['files_changed'] == []
    assert {p.name: (p.read_bytes(), p.stat().st_mtime_ns) for p in docs.glob('*.md')} == snapshot


@pytest.mark.parametrize('effect', ['read_external', 'model'])
@pytest.mark.parametrize('first_target,next_target', [
    ('north', 'south'), ('north', None), (None, 'south'),
    ('north', 'north'), (None, None),
])
def test_reuse_keeps_execution_destination(tmp_path, effect, first_target, next_target):
    """A changed destination must really execute; unchanged work stays reusable."""
    from ibl_v2_adapters import Adapter
    from ibl_run_journal import Journal, reusable_receipts

    calls = []

    def read(runtime, args, target_node=None):
        calls.append(target_node)
        return {'site': target_node or 'local', 'count': {'north': 3, 'south': 8}.get(target_node, 5)}

    registry = {'test:read': Adapter(
        {'version': 1, 'params': {'path': 'Text'}, 'result': 'Record', 'effects': [effect]},
        read, model_identity=(lambda: 'fixed-model') if effect == 'model' else None)}

    def execute(target, **kwargs):
        code = '[def:collect]() { return [test:read]{path:"returns.json"}'
        code += ('@' + target if target else '') + ' }; return [fn:collect]{}'
        plan = compile_program(code, registry)
        assert not plan.issues, plan.issues
        return Runtime(plan, **kwargs).run()

    with Journal(tmp_path, 'first') as journal:
        first = execute(first_target, journal=journal)
        first_id = journal.run_id
    assert first['success'], first
    with Journal(tmp_path, 'second') as journal:
        second = execute(next_target, journal=journal,
                         reusable=reusable_receipts(tmp_path, first_id), reuse_run=first_id)
        second_id = journal.run_id
    assert second['success'], second
    assert second['value'] == {'site': next_target or 'local',
                               'count': {'north': 3, 'south': 8}.get(next_target, 5)}
    changed = first_target != next_target
    assert calls == ([first_target, next_target] if changed else [first_target])
    assert second['reuse']['reused_calls'] == int(not changed)
    if changed:
        assert 'target_node' in second['reuse']['skipped'][0]['candidates'][0]['changed']
    # The new receipt remains useful across another continuation.
    third = execute(next_target, reusable=reusable_receipts(tmp_path, second_id), reuse_run=second_id)
    assert third['success'] and third['value'] == second['value']
    assert third['reuse']['reused_calls'] == 1
    assert len(calls) == (2 if changed else 1)


if __name__ == '__main__':
    import sys
    raise SystemExit(pytest.main([__file__, *sys.argv[1:]]))
