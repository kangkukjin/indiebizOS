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


def test_public_budget_limit_matches_check_and_runtime():
    maximum = capabilities()['v2_budget']['request_max']
    assert maximum == {'steps': 10_000_000, 'rows': 100_000}
    assert Budget.from_request(None).steps == 100_000
    for steps in (1_000_001, maximum['steps']):
        checked = handle_request({'edition': 2, 'code': 'return 1', 'budget': {'steps': steps}, 'check': True})
        assert checked['ok'] and checked['budget']['steps'] == steps
        result = handle_request({'edition': 2, 'code': 'return 1', 'budget': checked['budget']})
        assert result['success'] and result['usage']['limits']['steps'] == steps
    failed = handle_request({'edition': 2, 'code': 'return 1', 'budget': {'steps': maximum['steps'] + 1}})
    assert not failed.get('executed') and 'BUDGET_ARGUMENT' in str(failed)


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


if __name__ == '__main__':
    import sys
    raise SystemExit(pytest.main([__file__, *sys.argv[1:]]))
