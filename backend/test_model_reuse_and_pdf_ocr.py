"""Incremental model work and local page OCR at the public value boundaries."""
import boot_paths  # noqa: F401
import importlib.util
import json
from pathlib import Path
from dataclasses import replace
import shutil
import subprocess
from types import SimpleNamespace

import pytest

from ibl_v2_adapters import Adapter, load_registry
from ibl_v2_compile import compile_program
from ibl_v2_runtime import Runtime
from ibl_run_journal import Journal, reusable_receipts, model_reuse_identity
from ibl_v2_ir import Fault

ROOT = Path(__file__).resolve().parents[1]
PACKAGE = ROOT / 'data/packages/installed/tools/system_essentials'


def execute(source, registry, inputs=None, **kwargs):
    plan = compile_program(source, registry, inputs)
    assert not plan.issues, plan.issues
    return Runtime(plan, inputs, **kwargs).run()


def model_registry(calls, settings, *, fail=False, per_run=False):
    def call(rt, args):
        from model_call_context import record_captured_usage
        calls.append(dict(args))
        record_captured_usage({'input': 50, 'output': 10}, 1, 'fixture')
        if fail:
            raise Fault('TOOL', 'failed model')
        return {'answer': args['text']}
    contract = {'version': 1, 'params': {'text': 'Text'}, 'result': 'Record',
                'effects': ['model'], 'per_run': per_run, 'model_reuse': {'role': 'execution'}}
    return {'t:model': Adapter(contract, call, model_identity=lambda: settings[0]),
            't:write': Adapter({'version': 1, 'params': {}, 'result': 'Number',
                                'effects': ['write_external']}, lambda rt, a: 1)}


@pytest.mark.parametrize('change', ['render', 'input', 'settings', 'contract', 'fresh', 'per_run', 'opaque'])
def test_model_receipt_reuse_conditions(tmp_path, change):
    calls, settings = [], ['model-a']
    reg = model_registry(calls, settings, per_run=change == 'per_run')
    if change == 'opaque':
        reg['t:model'] = replace(reg['t:model'], model_identity=None)
    code = '$r=[t:model]{text:$text};[t:write]{};return $r'
    with Journal(tmp_path, 'first') as journal:
        first = execute(code, reg, {'text': 'source'}, journal=journal)
        rid = journal.run_id
    assert first['success']
    if change == 'settings':
        settings[0] = 'model-b'
    if change == 'contract':
        reg['t:model'] = replace(reg['t:model'], contract={**reg['t:model'].contract,
                                                         'implementation_fingerprint': 'new'})
    second = execute(code + '.answer', reg, {'text': 'changed' if change == 'input' else 'source'},
                     reusable=reusable_receipts(tmp_path, rid), reuse_run=rid,
                     reuse_models=change != 'fresh')
    assert second['success'], second
    if change == 'render':
        assert len(calls) == 1 and second['reuse']['model_calls'] == 1
        assert 'model' not in second['usage']
        evidence = next(e for e in second['evidence'] if 'original_model_usage' in e)
        assert evidence['original_model_usage'][0]['input'] == 50
        assert first['continuation']['model_calls'] == 1
        assert first['continuation']['read_calls'] == 0
    else:
        assert len(calls) == 2 and second['reuse']['reused_calls'] == 0
        assert second['usage']['model']['requests'] == 1


def test_failed_model_and_configuration_changed_during_call_are_not_candidates(tmp_path):
    calls, settings = [], ['a']
    for name, failing in [('failure', True), ('changing', False)]:
        reg = model_registry(calls, settings, fail=failing)
        original = reg['t:model'].run
        if not failing:
            def changing(rt, args):
                value = original(rt, args)
                settings[0] = 'b'
                return value
            reg['t:model'] = replace(reg['t:model'], run=changing)
        with Journal(tmp_path / name, name) as journal:
            result = execute('[t:model]{text:"source"}', reg, journal=journal)
            rid = journal.run_id
        assert not reusable_receipts(tmp_path / name, rid)
        assert 'reuse_args' not in result.get('continuation', {})


def test_reused_model_can_resume_reuse_and_replay_without_rebilling(tmp_path):
    calls, settings = [], ['a']
    reg = model_registry(calls, settings)
    code = 'return [t:model]{text:"source"}'
    with Journal(tmp_path, 'first') as journal:
        execute(code, reg, journal=journal)
        rid = journal.run_id
    edited = code + '.answer'
    with Journal(tmp_path, 'second') as journal:
        result = execute(edited, reg, journal=journal, reusable=reusable_receipts(tmp_path, rid), reuse_run=rid)
        second_id = journal.run_id
    with Journal(tmp_path, 'second', {'run_id': second_id}) as journal:
        resumed = execute(edited, reg, journal=journal)
    replayed = execute(edited, reg, replay=True, recordings=result['recordings'])
    third = execute(edited, reg, reusable=reusable_receipts(tmp_path, second_id), reuse_run=second_id)
    assert len(calls) == 1
    assert all(r['success'] and r['value'] == 'source' and 'model' not in r['usage']
               for r in (result, resumed, replayed, third))
    denied = replace(reg['t:model'], authorize=lambda: (_ for _ in ()).throw(Fault('DENIED', 'denied')))
    result = execute(edited, {'t:model': denied}, reusable=reusable_receipts(tmp_path, rid), reuse_run=rid)
    assert not result['success'] and len(calls) == 1


def test_resolved_model_settings_change_reuse_identity_without_exposing_secrets(monkeypatch):
    import model_resolver
    config = {'provider': 'fixture', 'model': 'a', 'api_key': 'secret-never-persist'}
    quality = {'provider': 'fixture', 'model': 'quality-a'}
    monkeypatch.setattr(model_resolver, 'resolve',
                        lambda role: dict(quality if role == 'evaluate' else config))
    monkeypatch.setattr(model_resolver, 'resolve_compat_model', lambda _: None)
    first = model_reuse_identity({'role': 'execution'})
    config['model'] = 'b'
    assert model_reuse_identity({'role': 'execution'}) != first
    second = model_reuse_identity({'role': 'execution'})
    quality['model'] = 'quality-b'
    assert model_reuse_identity({'role': 'execution'}) != second
    assert len(first) == 64 and 'secret' not in first


def test_duplicate_model_samples_are_not_collapsed(tmp_path):
    calls, settings = [], ['a']
    reg = model_registry(calls, settings)
    code = 'return [t:model]{text:"same"}'
    with Journal(tmp_path, 'first') as journal:
        execute(code, reg, journal=journal)
        rid = journal.run_id
    doubled = '[t:model]{text:"same"};' + code
    result = execute(doubled, reg, reusable=reusable_receipts(tmp_path, rid), reuse_run=rid)
    assert result['success'] and len(calls) == 2 and result['reuse']['model_calls'] == 1
    with Journal(tmp_path, 'duplicates') as journal:
        result = execute(doubled, reg, journal=journal)
        rid = journal.run_id
    assert not reusable_receipts(tmp_path, rid)
    assert 'reuse_args' not in result.get('continuation', {})


def test_public_reuse_models_option(monkeypatch, tmp_path):
    import ibl_v2_adapters, ibl_run_journal
    from ibl_v2_entry import handle_request
    calls, settings = [], ['a']
    monkeypatch.setattr(ibl_v2_adapters, 'load_registry', lambda *a: model_registry(calls, settings))
    monkeypatch.setattr(ibl_run_journal, 'journal_root', lambda _: tmp_path)
    request = {'code': '#!ibl edition=2\nreturn [t:model]{text:"source"}'}
    first = handle_request(request)
    rid = first['resume']['run_id']
    changed = {**request, 'code': request['code'] + '.answer'}
    reused = handle_request({**changed, 'reuse': {'run_id': rid}})
    fresh = handle_request({**changed, 'reuse': {'run_id': rid, 'models': False}})
    assert reused['reuse']['model_calls'] == 1 and fresh['reuse']['reused_calls'] == 0
    assert len(calls) == 2
    bad = handle_request({**changed, 'reuse': {'run_id': rid, 'models': 'false'}})
    assert not bad.get('success') and len(calls) == 2


def module(name):
    spec = importlib.util.spec_from_file_location(name, PACKAGE / (name + '.py'))
    result = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(result)
    return result


@pytest.fixture(scope='module')
def registry():
    return load_registry(str(ROOT))


def scanned_pdf(path):
    import fitz
    with fitz.open() as source, fitz.open() as target:
        page = source.new_page(width=500, height=300)
        page.insert_text((30, 60), 'Receipt R11', fontsize=22)
        page.insert_text((30, 100), '2026-09-30', fontsize=22)
        page.insert_text((30, 140), 'TOTAL 24,500', fontsize=22)
        pix = page.get_pixmap(matrix=fitz.Matrix(2, 2))
        target.new_page(width=500, height=300).insert_image(page.rect, stream=pix.tobytes('png'))
        target.new_page().insert_text((30, 50), 'native second page')
        target.save(path)


def test_real_ocr_reads_selected_scanned_page_with_provenance(registry, tmp_path):
    if not shutil.which('tesseract'):
        pytest.skip('local Tesseract integration requires installed engine')
    path = tmp_path / 'scan.pdf'
    scanned_pdf(path)
    result = execute('return [self:read]{path:$p,pages:"1"}', registry, {'p': str(path)})
    assert result['success'] and result['source_complete'], result
    doc = result['value']
    assert all(text in doc['text'] for text in ('R11', '2026-09-30', '24,500'))
    assert 'native second' not in doc['text']
    assert doc['blocks'][0]['source'] == 'ocr'
    assert doc['data']['ocr_pages'][0]['status'] == 'recognized'
    assert doc['data']['no_text_pages'] == []
    off = execute('[try]{return [self:read]{path:$p,ocr:false}}[catch]{return $error}',
                  registry, {'p': str(path)})
    assert off['success'] and not off['source_complete']
    assert off['value']['code'] == 'PARTIAL_SOURCE'
    assert 'native second' in off['value']['partial']['text']


def test_original_korean_scan_keeps_amount_lines(registry):
    if not shutil.which('tesseract'):
        pytest.skip('local Tesseract integration requires installed engine')
    path = ROOT / 'docs/experiments/long_sentence_imagination/round_5/input/receipts/R11.pdf'
    result = execute('[try]{return [self:read]{path:$p}}[catch]{return $error.partial}',
                     registry, {'p': str(path)})
    assert result['success'], result
    text = ''.join(result['value']['text'].split())
    assert '2026-09-15' in text and '합계' in text and '15,000' in text
    assert result['value']['data']['ocr_pages'][0]['engine'] == 'tesseract'


def test_native_page_does_not_invoke_ocr(registry, tmp_path, monkeypatch):
    path = tmp_path / 'scan.pdf'
    scanned_pdf(path)
    monkeypatch.setattr(shutil, 'which', lambda *_: pytest.fail('native page invoked OCR'))
    result = execute('return [self:read]{path:$p,pages:"2"}', registry, {'p': str(path)})
    assert result['success'] and result['value']['data']['ocr_pages'] == []


@pytest.mark.parametrize('failure', ['unavailable', 'timeout', 'empty', 'low_confidence', 'exit'])
def test_ocr_failure_keeps_partial_document(registry, tmp_path, monkeypatch, failure):
    path = tmp_path / 'scan.pdf'
    scanned_pdf(path)
    monkeypatch.setattr(shutil, 'which', lambda _: None if failure == 'unavailable' else '/fixture/tesseract')
    def process(argv, **kw):
        assert kw.get('shell', False) is False
        if '--list-langs' in argv:
            return SimpleNamespace(stdout=b'eng\nkor\n')
        assert kw['input'].startswith(b'\x89PNG')
        if failure == 'timeout':
            raise subprocess.TimeoutExpired(argv, 45)
        if failure == 'exit':
            raise subprocess.CalledProcessError(1, argv)
        header = 'level\tblock_num\tpar_num\tline_num\tconf\ttext\n'
        word = '5\t1\t1\t1\t20\tuncertain\n' if failure == 'low_confidence' else ''
        return SimpleNamespace(stdout=(header + word).encode())
    monkeypatch.setattr(subprocess, 'run', process)
    result = execute('[try]{return [self:read]{path:$p}}[catch]{return $error}', registry, {'p': str(path)})
    assert result['success'] and not result['source_complete']
    partial = result['value']['partial']
    assert 'native second' in partial['text']
    assert partial['data']['incomplete_pages'] == [1]
    if failure == 'low_confidence':
        assert 'uncertain' in partial['text']
        assert partial['data']['ocr_pages'][0]['confidence_min'] == 20


if __name__ == '__main__':
    raise SystemExit(pytest.main([__file__]))
