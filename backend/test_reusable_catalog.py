"""Discover by task intent, then distinguish invocation from mention."""
import boot_paths  # noqa: F401
from reusable_catalog import ranked
from associative_recall import _used_capabilities
import pytest


@pytest.mark.parametrize('name', ['압축', '시험', 'zip', 'R', '表'])
@pytest.mark.parametrize('prefix', ['', 'script:', 'fn:'])
def test_exact_names_are_discoverable_regardless_of_length(name, prefix):
    exact = {'id': prefix + name, 'description': 'opaque'}
    related = {'id': 'related', 'description': name + ' helper'}
    assert ranked(' ' + name.swapcase() + ' ', [related, exact], limit=1) == [exact]
    assert ranked(prefix + name, [exact]) == [exact]


def test_two_character_intent_matches_description_without_one_character_noise():
    entry = {'id': 'opaque', 'description': '파일 압축과 시험 결과'}
    assert ranked('압축', [entry]) == [entry]
    assert ranked('시험', [entry]) == [entry]
    assert ranked('압', [entry]) == []
    assert ranked('없는기능', [entry]) == []
    assert ranked('', [entry]) == []


def test_task_without_component_name_finds_contract_and_unrelated_task_does_not():
    entry = {'id': 'script:opaque7', 'description': 'sensor statistics and missing rows validation',
             'contract': {'params': {'rows': 'List<Record>'}, 'result': 'Record'}}
    assert ranked('check missing sensor rows', [entry]) == [entry]
    assert ranked('translate a poem', [entry]) == []


def test_partial_words_and_one_shared_word_do_not_recommend_unrelated_parts():
    narration = {'id': 'script:narration', 'description': '나레이션 파일의 음량 정렬'}
    device = {'id': 'fn:device', 'description': '본체 음량 제어'}
    assert ranked('본체 음량 낮춰', [narration, device]) == [device]
    assert ranked('파일', [{'id': 'script:compiler', 'description': '컴파일 결과 확인'}]) == []
    assert ranked('세계지도는 폴더형태로 구조화되어 있나?', [narration, device]) == []


def test_explicit_component_name_in_sentence_and_korean_particles_remain_searchable():
    entry = {'id': 'script:압축', 'description': 'opaque'}
    assert ranked('압축을 사용해서 이 작업을 진행해줘', [entry]) == [entry]
    semantic = {'id': 'fn:opaque', 'description': '센서 행 누락 검사'}
    assert ranked('센서의 행 누락을 검사해줘', [semantic]) == [semantic]


def test_long_incidental_description_does_not_outrank_focused_component():
    focused = {'id': 'fn:focused', 'description': 'sensor missing rows validation'}
    verbose = {'id': 'script:verbose', 'description':
               'sensor missing rows validation ' + ' '.join(f'option{i}' for i in range(100))}
    assert ranked('sensor missing rows validation', [verbose, focused], limit=1) == [focused]


def test_candidates_exclude_only_actually_exposed_functions_before_limit(tmp_path, monkeypatch):
    import yaml
    import principal, runtime_utils, thread_context, workflow_store, ibl_v2_store, ibl_access
    from ibl_v2_ir import digest
    from reusable_catalog import candidates
    monkeypatch.setattr(principal, 'is_owner', lambda: True)
    monkeypatch.setattr(runtime_utils, 'get_base_path', lambda: tmp_path)
    monkeypatch.setattr(thread_context, 'get_repair_workspace', lambda: None)
    monkeypatch.setattr(thread_context, 'get_allowed_nodes', lambda: None)
    monkeypatch.setattr(workflow_store, '_get_workflows_path', lambda: tmp_path)
    monkeypatch.setattr(ibl_v2_store, 'installed_definitions', lambda: {})
    monkeypatch.setattr(ibl_access, 'exposed_idiom_names', lambda allowed: {'압축'})
    scripts = tmp_path / 'data/scripts'
    scripts.mkdir(parents=True)
    (scripts / 'zip.py').write_text('')
    (scripts / 'registry.yaml').write_text(yaml.safe_dump({
        '압축': {'file': 'zip.py', 'description': '압축'}}))
    for name in ('압축', '예산밖함수'):
        code = f'[def:{name}](){{return 1}}'
        (tmp_path / (name + '.yaml')).write_text(yaml.safe_dump({
            'edition': 2, 'name': name, 'description': '압축', 'code': code,
            'source_hash': digest(code), 'capability_contract': {'result': 'Number'}}))
    assert {row['id'] for row in candidates('압축', limit=2)} == {'script:압축', 'fn:예산밖함수'}


def test_mentions_and_unsuccessful_calls_do_not_count_as_use():
    ids = ['script:opaque7']
    mentioned = _used_capabilities(ids, {}, {'response': 'opaque7', 'tool_calls': []})
    assert mentioned['used'] == []
    invoked = _used_capabilities(ids, {}, {'tool_calls': [{'result': {'capability_usage': [
        {'id': ids[0], 'success': True}]}}]})
    assert invoked['used'] == ids and invoked['quality_contribution'] == 'not_inferred'


def test_local_function_shadow_is_not_counted_as_stored_capability():
    from ibl_v2_compile import compile_program
    from ibl_v2_runtime import Runtime
    out = Runtime(compile_program('[def:opaque]($n){return $n*2}\n[fn:opaque]{n:3}', {})).run()
    assert out['success'] and not out.get('capability_usage')


def test_stored_function_retains_derived_contract_and_dependencies(tmp_path, monkeypatch):
    import yaml
    import ibl_v2_store, ibl_v2_adapters, workflow_store
    monkeypatch.setattr(workflow_store, '_get_workflows_path', lambda: tmp_path)
    monkeypatch.setattr(ibl_v2_store, 'definitions', lambda: {})
    monkeypatch.setattr(ibl_v2_adapters, 'load_registry', lambda *a: {})
    out = ibl_v2_store.action('save', {'code': '[def:opaque]($n){return $n*2}', 'description': 'sensor calibration'}, str(tmp_path))
    assert out['success'], out
    saved = yaml.safe_load((tmp_path / (out['workflow_id'] + '.yaml')).read_text())
    assert saved['capability_contract']['name'] == 'opaque'
    assert saved['source_hash'] and saved['dependencies'] and saved['plan_hash']


if __name__ == "__main__":
    import pytest
    raise SystemExit(pytest.main([__file__]))
