"""Registered value contracts remain usable across script/function/table boundaries."""
import boot_paths  # noqa: F401
import copy
import importlib.util
from pathlib import Path

import pytest
import yaml

from ibl_callable_contract import checked_values
from ibl_dependencies import script_contract
from ibl_v2_adapters import Adapter, load_registry
from ibl_v2_compile import compile_program
from ibl_v2_runtime import Runtime
from ibl_v2_types import guard
from test_function_support import current_source

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def script():
    spec = importlib.util.spec_from_file_location('judgment_idioms_test', ROOT / 'data/scripts/judgment_idioms.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def contract():
    return yaml.safe_load((ROOT / 'data/scripts/registry.yaml').read_text())['판정관용구']['callable_contract']


@pytest.fixture
def registry(tmp_path, script):
    registry = load_registry(str(tmp_path))
    # Run the real deterministic script in process; no external API, subprocess,
    # registration or production workflow journal is involved.
    registry['self:script'] = Adapter(
        registry['self:script'].contract,
        lambda rt, args: script.run(args['args']), specialize=script_contract)
    return registry


@pytest.mark.parametrize('rows', [[], [{'url': 'https://example.test', 'text': 'needle'}]])
@pytest.mark.parametrize('consumer', [
    '[table:select]{columns:["text"]}', '[table:filter]{where:($r)=>true}',
    '[table:sort]{by:"text"}', '[table:take]{n:3}',
    '[table:each]{return $it}',
])
def test_named_function_result_composes_without_field_extraction(registry, rows, consumer):
    code = ('return [fn:본문에서찾기]{목록:$source,패턴:"needle",문맥:0,개수:6} >> ' + consumer)
    inputs = {'source': {'items': rows}}
    definitions = {'본문에서찾기': current_source('본문에서찾기')}
    plan = compile_program(code, registry, inputs, definitions)
    assert not plan.issues, plan.report()
    out = Runtime(plan, inputs).run()
    expected = [{'text': r['text']} for r in rows] if 'select' in consumer else rows
    assert out['success'] and out['value'] == expected, out


@pytest.mark.parametrize('partial', [False, True])
def test_original_crawl_function_projection_path(registry, partial):
    from ibl_v2_adapters import Adapted, decode_envelope
    value = {'text': 'needle', 'title': 'source', 'url': 'https://example.test',
             'items': [{'text': 'needle', 'url': 'https://example.test'}]}
    contract = registry['sense:crawl'].contract
    def crawl(*_):
        raw = copy.deepcopy(value)
        if partial:
            raw['truncated'] = True
        return Adapted(*decode_envelope(raw, contract['adapter']))
    registry['sense:crawl'] = Adapter(contract, crawl)
    code = ('$c=[try]{[sense:crawl]{url:"https://example.test"}}[catch]{$error.partial}\n'
            'return ($c >> [fn:본문에서찾기]{패턴:"needle",문맥:0,개수:6})'
            ' >> [table:select]{columns:["text"]}')
    plan = compile_program(code, registry, definitions={'본문에서찾기': current_source('본문에서찾기')})
    assert not plan.issues, plan.report()
    out = Runtime(plan).run()
    assert out['success'] and out['value'] == [{'text': 'needle'}], out
    assert out['source_complete'] is (not partial), out


def test_every_operation_returns_its_declared_value(script, contract):
    source = {'items': [{'url': 'https://example.test', 'text': 'needle', 'title': 'title'}]}
    samples = [
        {'op': 'urls', 'source': source},
        {'op': 'urls', 'source': source, 'limit': 0},
        {'op': 'prepare', 'mode': 'body', 'source': source, 'question': 'needle', 'limit': 2},
        {'op': 'match', 'source': source, 'pattern': 'needle', 'limit': 2},
        {'op': 'match', 'source': source, 'pattern': 'missing', 'limit': 2},
        {'op': 'collect', 'results': [{'ok': True, 'value': source}]},
        {'op': 'collect', 'results': [{'ok': False, 'error': {'message': 'source unavailable'}}]},
    ]
    prepared = script.run(samples[2])
    selection = {'op': 'select', 'prepared': prepared['plan'], 'mode': 'body', 'limit': 2,
                 'judged': {'items': [{'rid': 0, 'judgment_result_status': 'decided',
                                      'judgment_result_value': True}]}}
    samples.append(selection)
    samples.append({'op': 'finish', 'selection': script.run(selection)['selection'], 'result': source})
    for args in samples:
        selected, values = checked_values(contract, args)
        actual = script.run(values)
        assert guard(actual, selected['result'], args['op']) == actual
        assert isinstance(actual['items'], list)


def test_match_discards_stale_full_text_and_preserves_selection_receipts(script):
    source = {'text': '원문 전체 ' * 30000, 'length': 180000, 'truncated': True,
              'items': [{'text': 'needle', 'url': 'https://one', 'paragraph_index': 27},
                        {'text': 'other', 'url': 'https://one', 'paragraph_index': 28},
                        {'url': 'https://two', '_error': '403'}],
              'research_materials': [{'version_ref': 'original'}],
              'source_ref': {'path': '/preserved/full.txt'}}
    out = script.run({'op': 'match', 'source': source, 'pattern': 'needle', 'limit': 1})
    assert 'text' not in out
    assert out['items'] == [source['items'][0], source['items'][2]]
    assert out['research_materials'] == source['research_materials']
    assert out['source_ref'] == source['source_ref'] and out['truncated']
    assert source['text'].startswith('원문 전체')


@pytest.mark.parametrize('op', ['urls', 'prepare', 'select', 'finish', 'match', 'collect'])
def test_missing_operation_inputs_rejected_before_script(registry, op):
    code = 'return [self:script]{id:"판정관용구",args:{op:"' + op + '"}}'
    plan = compile_program(code, registry)
    assert plan.issues, plan.report()
    assert not Runtime(plan).run()['executed']


@pytest.mark.parametrize('args', [
    '{op:"match",source:[],pattern:"x",limit:-1}',
    '{op:"match",source:[],pattern:"x",limit:1.5}',
    '{op:"prepare",source:[],mode:"invalid",question:"x",limit:1}',
    '{op:"prepare",source:[],mode:"body",question:"",limit:1}',
])
def test_known_invalid_options_rejected_before_script(registry, args):
    plan = compile_program('return [self:script]{id:"판정관용구",args:' + args + '}', registry)
    assert plan.issues, plan.report()
    assert not Runtime(plan).run()['executed']


if __name__ == '__main__':
    import sys
    raise SystemExit(pytest.main([__file__, *sys.argv[1:]]))
