"""Long-program report 3: typed rows, reuse, bounded diagnostics and paid boundaries."""
import boot_paths  # noqa: F401
import json
from pathlib import Path

import pytest

from ibl_v2_adapters import Adapter, load_registry
from ibl_v2_compile import compile_program
from ibl_v2_ir import Fault
from ibl_v2_runtime import Budget, Runtime
from ibl_run_journal import Journal, reusable_receipts

ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / 'docs/experiments/long_sentence_imagination/round_3'


@pytest.fixture(scope='module')
def registry(tmp_path_factory):
    import ibl_usage_db as db_module
    import workflow_store
    root = tmp_path_factory.mktemp('round3')
    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(db_module, 'DB_PATH', str(root / 'usage.db'))
        patch.setattr(db_module.IBLUsageDB, '_instance', None)
        patch.setattr(db_module.IBLUsageDB, '_index_batch', lambda *a, **k: None)
        patch.setattr(db_module.IBLUsageDB, '_index_single', lambda *a, **k: None)
        patch.setattr(db_module, '_tree_refresh', lambda *a, **k: None)
        patch.setattr(workflow_store, '_get_workflows_path', lambda: root / 'workflows')
        entry = next(e for e in json.loads((ROOT / 'data/idioms/curated.json').read_text())['idioms']
                     if e['name'] == '본문에서찾기')
        db_module.IBLUsageDB().add_examples_batch([{
            'intent': entry['when'], 'ibl_code': entry['body'], 'alias': entry['name'],
            'category': 'phrase', 'nodes': 'table'}])
        yield load_registry(str(ROOT))


def execute(code, registry, inputs=None, **kwargs):
    plan = compile_program(code, registry, inputs)
    assert not plan.issues, [(i['code'], i['message']) for i in plan.issues]
    return Runtime(plan, inputs, **kwargs).run()


@pytest.mark.parametrize('index', range(1, 13))
def test_schema_reproductions(registry, index):
    code = (FIXTURE / f'repro/ai_schema_input_fields_{index}.ibl').read_text()
    assert not compile_program(code, registry, {'ok': True}).issues


def test_empty_branch_is_not_unknown_row(registry):
    from ibl_v2_types import infer, join
    assert join(infer([]), infer([{'a': 1}])).item == infer({'a': 1})
    assert join(infer([{'a': 1}]), infer([])).item == infer({'a': 1})
    code = '[def:f]($ok){[if:$ok]{return [{a:1}]};return []};'
    code += '$r=[fn:f]{ok:$ok} >> [table:ai]{schema:"x(値),y(値)",instruction:"x"};'
    assert not compile_program(code + 'return $r.items[0].a', registry, {'ok': True}).issues
    assert compile_program(code + 'return $r.items[0].typo', registry, {'ok': True}).issues


@pytest.mark.parametrize('bad,expected', [(True, ['x']), (False, [])])
def test_has_filter_proves_presence(registry, bad, expected):
    result = execute((FIXTURE / 'repro/has_narrow.ibl').read_text(), registry, {'bad': bad})
    assert result['success'] and result['value'] == expected


def test_has_does_not_refine_sibling_or_assert_nonnull(registry):
    code = '$rows=[{a:null},{b:2}];'
    assert compile_program(code + 'return $rows[1].a', registry).issues
    result = execute(code + '$rows >> [table:filter]{where:($r)=>has($r,"a")} '
                     '>> [table:each]{return $it.a}', registry)
    assert result['success'] and result['value'] == [None]
    assert compile_program('return has({a:1},"a") ? 1 : {b:2}.a', registry).issues


def test_multiline_lambda_and_metadata_warning(registry):
    result = execute((FIXTURE / 'repro/multiline_lambda.ibl').read_text(), registry)
    assert result['value'] == 6
    code = (FIXTURE / 'repro/ai_input_fields_warning.ibl').read_text()
    assert not compile_program(code, registry).preflight['warnings']
    repeated = '$all=[{id:1},{id:2}];[1,2] >> [table:each]{'
    repeated += '$all >> [table:ai]{instruction:"x",input_fields:["id"]}}'
    assert compile_program(repeated, registry).preflight['warnings'][0]['facts']['argument'] == 'items'


@pytest.mark.parametrize('dimension,kwargs', [('rows', {'rows': 0}), ('steps', {'steps': 0}),
                                             ('depth', {'depth': 0}), ('seconds', {'seconds': -1})])
def test_budget_reports_exhausted_dimension(dimension, kwargs):
    with pytest.raises(Fault) as raised:
        Budget(**kwargs).tick(row=True, depth=1)
    exc = raised.value
    assert not exc.catchable
    assert exc.details['exceeded'][dimension]['used'] > exc.details['exceeded'][dimension]['limit']
    assert '전건' in exc.details['hint']


def test_number_diagnostic_and_recovery(registry):
    result = execute('return number($v)', registry, {'v': '5,000~6,000'})
    assert not result['success']
    assert result['diagnostic']['details']['input_preview'] == repr('5,000~6,000')
    result = execute('[try]{return number($v)}[catch]{return null}', registry, {'v': '5,000~6,000'})
    assert result['success'] and result['value'] is None


def test_legacy_filter_contract_and_reuse(registry, tmp_path, monkeypatch):
    import ibl_v2_compat
    # Preserve the body semantics and expose selected values with separate evidence.
    spec = registry['fn:본문에서찾기']
    assert spec.contract['effects'] == ['pure']
    assert spec.contract['params']['패턴'] == 'Text'
    rows = [{'text': f'hit {i}', 'url': 'https://example.test', 'paragraph_index': i} for i in range(3)]
    out = execute('[fn:본문에서찾기]{목록:$rows,패턴:"hit",문맥:0,개수:1}', registry, {'rows': rows})
    assert out['success'], out
    assert out['value']['items'] == rows[:1]
    assert out['value']['match_info']['total_matches'] == 3
    assert out['value']['match_info']['omitted_matches'] == 2
    assert 'final_result' not in out['value']
    assert any((event.get('attachments') or {}).get('execution_ref') for event in out['evidence'])
    calls = []
    local = {**registry, 't:read': Adapter({'version': 1, 'params': {}, 'result': 'List<Record>',
             'effects': ['read_external']}, lambda rt, args: calls.append(1) or rows)}
    code = '$r=[t:read]{};return $r >> [fn:본문에서찾기]{패턴:"hit",문맥:0,개수:1}'
    with Journal(tmp_path, 'pure') as journal:
        result = execute(code, local, journal=journal)
        run_id = journal.run_id
    assert result['continuation']['read_calls'] == 1
    changed = execute(code.replace('개수:1', '개수:2'), local,
                      reusable=reusable_receipts(tmp_path, run_id), reuse_run=run_id)
    assert changed['reuse']['reused_calls'] == 1 and calls == [1]
    assert changed['value']['items'] == rows[:2]
    from ibl_parser import parse_function_body
    body = '$return=$목록 >> [table:filter]{where:{field:"text",op:"matches",value:$패턴},context:{}}'
    steps = parse_function_body(body)
    assert not ibl_v2_compat.forwarding_contract(None, [], None)
    bare = parse_function_body(body.replace(',context:{}', ''))
    assert not ibl_v2_compat.forwarding_contract(bare, ['목록', '패턴'], '목록')
    assert ibl_v2_compat.forwarding_contract(steps, ['목록', '패턴'], '목록')['effects'] == ['pure']
    for extra in [{'_node': 'self', 'action': 'write', 'params': {}}, {'criteria': 'check'}]:
        assert not ibl_v2_compat.forwarding_contract(steps + [extra], ['목록', '패턴'], '목록')
    steps[1]['criteria'] = 'extra model'
    assert not ibl_v2_compat.forwarding_contract(steps, ['목록', '패턴'], '목록')


def test_model_missing_duplicate_invalid_diagnostics(registry, monkeypatch):
    import oneshot_facade
    from model_result_view import read_result
    output = [{'_i': 0, 'x': 'a'}, {'_i': 0, 'x': 'b'}, {'_i': 7, 'x': 'c'}]
    monkeypatch.setattr(oneshot_facade, 'oneshot_json', lambda *a: (output, None))
    result = execute('[{a:1},{a:2}] >> [table:ai]{instruction:"x",schema:"x(text)",preserve_rows:true}', registry)
    assert not result['success']
    details = result['diagnostic']['details']
    assert details['missing_indices'] == [1] and details['duplicate_indices'] == [0]
    assert details['invalid_indices'] == [{'row': 2, 'index': 7}]
    saved = read_result(details['model_output_ref']['read_args'])
    assert json.loads(saved['text']) == output


def test_crawl_http_diagnostics(registry, monkeypatch):
    from common.pkg_utils import load_sibling
    c = load_sibling(ROOT / 'data/packages/installed/tools/web/handler.py', 'tool_webcrawl')
    monkeypatch.setattr(c, '_crawl_static', lambda url, *a, **kw: {
        'success': False, 'url': url, 'resolved_url': url, 'http_status': 404,
        'reason': 'http_error', 'error': 'HTTP 404', 'method': 'fixture'})
    monkeypatch.setattr(c, '_get_browser_session', lambda: None)
    monkeypatch.setattr(c, '_get_chrome_driver', lambda: None)
    monkeypatch.setattr(c, '_resolve_google_news', lambda url: None)
    from ibl_v2_adapters import decode_envelope
    raw = c._crawl_website_impl("https://fixture.test/missing-round3", None)
    with pytest.raises(Fault) as raised:
        decode_envelope(raw, {"protocol": "legacy-envelope", "value_path": ""})
    assert raised.value.code == 'NOT_FOUND'
    assert raised.value.details['http_status'] == 404
    assert raised.value.details['url'].endswith('/missing-round3')


def test_expensive_stage_reference_survives_downstream_edit(tmp_path, monkeypatch):
    from supervision_store import TurnStore
    import model_result_view as view
    calls = []
    reg = {'t:model': Adapter({'version': 1, 'params': {}, 'result': 'List<Record>',
            'effects': ['model']}, lambda rt, args: calls.append(1) or [{'value': '5,000~6,000'}])}
    first = execute('return [t:model]{}', reg)
    assert first['success']
    store = TurnStore(tmp_path)
    monkeypatch.setattr(view, 'evidence_store', lambda: store)
    ref = store.evidence(first)
    inputs, _ = view.resolve_input_refs({'rows': {'$ref': ref['id']}})
    failed = execute('$rows >> [table:each]{return number($it.value)}', {}, inputs)
    assert not failed['success']
    repaired = execute('$rows >> [table:each]{[try]{return number($it.value)}[catch]{return null}}', {}, inputs)
    assert repaired['success'] and repaired['value'] == [None] and calls == [1]


@pytest.mark.system  # 2026-10-04: 전체 재생·전수 스캔은 system 묶음(docs/REGRESSION_TESTING.md 표)
@pytest.mark.parametrize('variant', [False, True])
def test_full_report_and_six_source_reuse(registry, tmp_path, monkeypatch, variant):
    import oneshot_facade
    from dataclasses import replace
    requests, crawls = [], []

    def model(prompt, system):
        rows = json.loads(prompt.split('[items]\n', 1)[1].split('\n\n[지시]', 1)[0])
        requests.append(rows)
        if '주장(목록' in system:
            return ([{'_i': row['_i'], '주장': [{'값': '8,848.86', '단위': 'm',
                     '대상': '검증 수치', '측정': '2020'}], '논쟁': 'Amazon과 길이 논쟁'}
                     for row in rows], None)
        return ([{'_i': row['_i'], '판정': '일치', '해설': '주어진 근거의 일치'} for row in rows], None)

    monkeypatch.setattr(oneshot_facade, 'oneshot_json', model)

    def crawl(rt, args):
        crawls.append(args['url'])
        return {'url': args['url'], 'title': 'fixture', 'text': 'fixture',
                'items': [{'url': args['url'], 'paragraph_index': 1,
                           'text': f"8,848.86 m, 2020. length 길이 Amazon 아마존 {args['url']}"}]}

    # Preserve read effects, but use deterministic web/model fixtures. No live calls.
    reg = {**registry, 'sense:crawl': replace(registry['sense:crawl'], run=crawl)}
    inputs = json.loads((FIXTURE / 'inputs_main_v5.json').read_text())['inputs']
    inputs['출력'] = str(tmp_path / 'report.md')
    code = (FIXTURE / 'drafts/v8b.ibl').read_text()
    # Remove the report's static-check workarounds at the affected field boundaries.
    code = code.replace('get($p,"paragraph_index",null)', '$p.paragraph_index')
    code = code.replace('get($p,"text","")', '$p.text')
    code = code.replace('get($it,"paragraph_index",null)', '$it.paragraph_index')
    with Journal(tmp_path / 'runs', 'main') as journal:
        first = execute(code, reg, inputs, journal=journal)
        run_id = journal.run_id
    assert first['success'] and first['value']['저장일치'], first
    assert first['value']['버림수'] == 0
    assert len(crawls) == 6 and len(requests) == 7
    assert 'Amazon' in Path(inputs['출력']).read_text()
    other = (FIXTURE / 'drafts/varB_v1.ibl').read_text() if variant else code
    second = execute(other, reg, {**inputs, '출력': str(tmp_path / 'changed.md')},
                     reusable=reusable_receipts(tmp_path / 'runs', run_id), reuse_run=run_id)
    assert second['success'] and second['value']['저장일치'], second
    assert second['reuse']['reused_calls'] == 13 and len(crawls) == 6
    assert second['reuse']['model_calls'] == 7
    assert len(requests) == 7  # Formatting/quiz changes preserve all seven model results.
    assert 'model' not in second['usage']


def test_repaired_stages_keep_model_work_out_of_render_repairs(registry, tmp_path, monkeypatch):
    from dataclasses import replace
    from supervision_store import TurnStore
    import model_result_view as view
    import oneshot_facade
    requests = []
    def model(prompt, system):
        rows = json.loads(prompt.split('[items]\n', 1)[1].split('\n\n[지시]', 1)[0])
        requests.append(rows)
        if '주장(목록' in system:
            return ([{'_i': r['_i'], '주장': [{'값': '8,848.86', '단위': 'm',
                     '대상': '검증 수치', '측정': None}], '논쟁': None} for r in rows], None)
        return ([{'_i': r['_i'], '판정': '일치', '해설': '입력 근거'} for r in rows], None)
    monkeypatch.setattr(oneshot_facade, 'oneshot_json', model)
    reg = {**registry, 'sense:crawl': replace(registry['sense:crawl'], run=lambda rt, args: {
        'url': args['url'], 'title': 'fixture', 'text': 'fixture', 'items': [
            {'url': args['url'], 'paragraph_index': i, 'text': '8,848.86 length 길이 Amazon'}
            for i in range(3)]})}
    inputs = json.loads((FIXTURE / 'inputs_main_v5.json').read_text())['inputs']
    inputs.update(문단상한=1, 출력=str(tmp_path / 'report.md'))
    store = TurnStore(tmp_path / 'evidence')
    monkeypatch.setattr(view, 'evidence_store', lambda: store)
    def source(stage):
        return (FIXTURE / f'drafts/repaired_{stage}.ibl').read_text()
    def referenced(result):
        ref = store.evidence(result)
        values, _ = view.resolve_input_refs({'자료': {'$ref': ref['id']}})
        return {**inputs, **values}
    collected = execute(source('collect'), reg, inputs)
    assert collected['success'] and len(requests) == 6
    assert all(r['적중'] == 3 and r['사용'] == 1 for r in collected['value']['읽음'])
    material = referenced(collected)
    failed = execute('return number($v)', reg, {**material, 'v': 'invalid'})
    assert not failed['success'] and len(requests) == 6
    analyzed = execute(source('analyze'), reg, material)
    assert analyzed['success'] and len(requests) == 7, analyzed
    for output in ['first.md', 'changed.md']:
        rendered = execute(source('render'), reg, {**referenced(analyzed), '출력': str(tmp_path / output)})
        assert rendered['success'] and rendered['value']['저장일치'], rendered
        assert '적중 3 중 1만 사용' in (tmp_path / output).read_text()
    assert len(requests) == 7


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__]))
