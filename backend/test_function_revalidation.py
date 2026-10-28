"""The existing catalog grows reusable, bodyless abilities without executing tools."""
import boot_paths  # noqa: F401
import copy
import json

import pytest

from test_ibl_v2_semantic import abilities, save_layers, query  # noqa: F401
from ibl_v2_compile import Compiler, compile_program
from ibl_v2_runtime import Runtime
from ibl_v2_ir import Fault
from function_library import register, definitions, reference_library
from function_revalidation import revalidate


def save(name, body, **kwargs):
    return register(name, '#!ibl edition=2\n' + body, edition=2, **kwargs)


def legacy(monkeypatch):
    from ibl_v2_semantic import Unsupported
    def absent(*args):
        raise Unsupported('legacy certificate unavailable')
    monkeypatch.setattr('ibl_v2_semantic_store.derive', absent)


def test_recertification_is_atomic_idempotent_and_preserves_exact_revisions(abilities, monkeypatch):
    import function_store
    reg, calls, _ = abilities
    with monkeypatch.context() as old:
        legacy(old)
        save_layers()
    before = function_store.snapshot()
    root = function_store.storage_root()
    old_files = {p: p.read_bytes() for p in root.rglob('*') if p.is_file()}
    audited = revalidate()
    assert {v['status'] for v in audited['functions'].values()} == {'ready'}
    assert not audited['executed'] and not audited['applied'] and calls == []
    assert old_files == {p: p.read_bytes() for p in root.rglob('*') if p.is_file()}
    applied = revalidate(apply=True)
    assert applied['applied'] and calls == []
    after = function_store.snapshot()
    assert after['generation'] == before['generation'] + 1
    for fid, row in before['records'].items():
        assert after['records'][fid]['source'] == row['source']
        assert function_store.revision(fid, row['revision'])['source'] == row['source']
    library = definitions()
    assert set(library.interfaces) == {'normalizer', 'gather', 'decide', 'recheck'}, library.interface_limits
    for interface in library.interfaces.values():
        for name, dep in interface['dependencies'].items():
            assert dep['function_ref'] == library.references[name]
    generation = after['generation']
    assert not revalidate(apply=True)['applied']
    assert function_store.snapshot()['generation'] == generation
    with monkeypatch.context() as blocked:
        blocked.setattr(Compiler, '_function', lambda *a, **kw: pytest.fail('lower body analysis'))
        checked = compile_program(query(), reg, definitions=library.interfaces_only())
    assert not checked.issues
    checked.definitions = library
    assert Runtime(checked).run()['success']
    assert calls == [('read', 'catalog'), ('script', 'normalize')]


def test_transitive_invalidation_and_revalidation_keep_pinned_history(abilities):
    reg, calls, _ = abilities
    old = save('leaf', '[def:leaf]($x){return $x+1}')
    save('middle', '[def:middle]($x){return [fn:leaf]{x:$x}}')
    save('upper', '[def:upper]($x){return {v:[fn:middle]{x:$x}}}')
    checked = compile_program('[fn:upper]{x:1}', reg, definitions=definitions())
    save('leaf', '[def:leaf]($x){return $x+2}', expected_revision=old['revision'])
    assert set(definitions().interfaces) == {'leaf'}
    assert set(definitions().interface_limits) == {'middle', 'upper'}
    assert Runtime(checked).run()['value'] == {'v': 2}
    pinned = reference_library(checked.dependencies['function_refs'])
    assert set(pinned.interfaces) == {'leaf', 'middle', 'upper'}
    assert revalidate(apply=True)['applied']
    library = definitions()
    assert set(library.interfaces) == {'leaf', 'middle', 'upper'}
    assert Runtime(compile_program('[fn:upper]{x:1}', reg, definitions=library)).run()['value'] == {'v': 3}
    assert calls == []


def test_changed_primitive_contract_requires_revalidation(abilities):
    reg, calls, _ = abilities
    save('read', '[def:read]($source){return [probe:read]{source:$source}}')
    save('outer', '[def:outer]($source){return [fn:read]{source:$source}}')
    reg['probe:read'].contract['result']['extra'] = 'Text'
    with pytest.raises(Fault) as invalid:
        compile_program('[fn:outer]{source:"x"}', reg, definitions=definitions().interfaces_only())
    assert invalid.value.code == 'SEMANTIC_INTERFACE_REQUIRED'
    from ibl_v2_store import describe
    stale = describe('outer')
    assert not stale.get('error') and 'revalidation required' in stale['semantic_limit']
    result = revalidate(apply=True)
    assert result['applied'] and calls == []
    checked = compile_program('[fn:outer]{source:"x"}.extra', reg, definitions=definitions().interfaces_only())
    assert not checked.issues and str(checked.result_type) == 'Text'


def test_catalog_race_rejects_whole_recertification(abilities, monkeypatch):
    import function_store
    with monkeypatch.context() as old:
        legacy(old)
        save('leaf', '[def:leaf](){return 7}')
    publish = function_store.publish
    # Install the unrelated mutation with the original publisher, then attempt
    # the already audited generation. No certificate from the stale audit wins.
    def race(changes, **kwargs):
        with monkeypatch.context() as context:
            context.setattr(function_store, 'publish', publish)
            save('concurrent', '[def:concurrent](){return 8}')
        return publish(changes, **kwargs)
    monkeypatch.setattr(function_store, 'publish', race)
    with pytest.raises(ValueError, match='원장이 변경'):
        revalidate(apply=True)
    assert 'leaf' not in definitions().interfaces


def test_binding_uses_checked_metadata_without_second_compilation(abilities, monkeypatch):
    reg, calls, _ = abilities
    from dataclasses import replace
    reg['probe:python'] = replace(reg['probe:python'],
        dependency=lambda args: {'revision': 1, 'id': args.get('id')})
    save_layers()
    plan = compile_program(query(), reg, definitions=definitions())
    original = copy.deepcopy(plan.report())
    with monkeypatch.context() as blocked:
        blocked.setattr(Compiler, '_function', lambda *a, **kw: pytest.fail('body judgment'))
        with monkeypatch.context() as lowering:
            lowering.setattr('ibl_v2_compile.compile_program', lambda *a, **kw: pytest.fail('second compilation'))
            runtime = Runtime(plan)
        assert runtime.plan.issues == plan.issues and runtime.plan.result_type == plan.result_type
        assert runtime.plan.effects == plan.effects and runtime.plan.fingerprint == plan.fingerprint
        result = runtime.run()
    assert result['success'], result
    assert plan.report() == original
    assert calls == [('read', 'catalog'), ('script', 'normalize')]


@pytest.mark.parametrize('body,expected', [
    ('assert $ok,"required",{why:"no"};return $rows[1:3]', [2, 3]),
    ('return [try]{assert false,"no";99}[catch]{7}[finally]{}', 7),
    ('assert true,1/0;return $rows[:]', [1, 2, 3, 4]),
])
def test_assert_slice_survive_recertification_and_bodyless_composition(abilities, monkeypatch, body, expected):
    reg, calls, _ = abilities
    source = '[def:part]($ok,$rows){' + body + '}'
    with monkeypatch.context() as old:
        legacy(old)
        save('part', source)
    assert revalidate(apply=True)['applied']
    save('promoted', '[def:promoted]($ok,$rows){return [fn:part]{ok:$ok,rows:$rows}}')
    library = definitions()
    code = '[fn:promoted]{ok:true,rows:[1,2,3,4]}'
    with monkeypatch.context() as blocked:
        blocked.setattr(Compiler, '_function', lambda *a, **kw: pytest.fail('body judgment'))
        plan = compile_program(code, reg, definitions=library.interfaces_only())
    assert not plan.issues, plan.report()
    plan.definitions = library
    result = Runtime(plan).run()
    assert result['success'] and result['value'] == expected, result
    assert calls == []


def test_discover_describe_apply_save_and_rediscover_same_interface(abilities, tmp_path, monkeypatch):
    from reusable_catalog import candidates, discovery_payload
    from ibl_v2_store import describe, Library
    from ibl_v2_ir import digest
    reg, calls, _ = abilities
    monkeypatch.setattr('principal.is_owner', lambda: True)
    monkeypatch.setattr('runtime_utils.get_base_path', lambda: tmp_path)
    monkeypatch.setattr('thread_context.get_repair_workspace', lambda **kw: None)
    monkeypatch.setattr('thread_context.get_allowed_nodes', lambda **kw: None)
    monkeypatch.setattr('ibl_access.exposed_idiom_names', lambda *a: set())
    save('prepare', '[def:prepare]($rows){assert len($rows)>0,"empty";return $rows[0:2]}',
         description='센서 행 선택 검증')
    original = Library.__getitem__
    def no_body(lib, name):
        if name in lib.interfaces:
            pytest.fail('discovery/authoring read lower body')
        return original(lib, name)
    with monkeypatch.context() as blocked:
        blocked.setattr(Library, '__getitem__', no_body)
        found = candidates('센서 행 선택 검증')
        card = discovery_payload(found)['candidates'][0]
        detail = describe('prepare')
        assert card['contract'] == detail['application_view']
        assert card['contract']['relation_hash'] == digest(detail['semantic_interface'])
        assert 'terms' not in json.dumps(card['contract'])
        assert 'contract' not in card['details_omitted']
        application = card['contract']['apply']
        plan = compile_program(application['code'], reg, inputs={'rows': [{'v': 1}, {'v': 2}]},
                               definitions=definitions().interfaces_only())
        assert not plan.issues and 'v' in str(plan.result_type)
        save('report', '[def:report]($rows){return {chosen:[fn:prepare]{rows:$rows}}}',
             description='센서 선택 보고')
        again = candidates('센서 선택 보고')[0]
        assert again['id'] == 'fn:report'
        assert again['contract']['protocol'] == card['contract']['protocol']
    assert calls == []


def test_pure_provider_after_write_can_change_inside_saved_implementation(abilities, tmp_path):
    from ibl_v2_adapters import Adapter
    from ibl_v2_entry import handle_request
    reg, calls, _ = abilities
    reg['probe:compute'] = Adapter({'version': 1, 'params': {'n': 'Number'}, 'result': 'Number',
                                  'effects': ['pure']}, lambda rt, a: a['n'] + 1)
    source = ('[def:step]($n){[probe:publish]{items:[]};$r=[probe:compute]{n:1};'
              'return {computed:$r,ratio:1/$n}}')
    old = save('step', source)
    request = {'edition': 2, 'code': '[fn:step]{n:$n}', 'inputs': {'n': 0}}
    first = handle_request(request, str(tmp_path))
    assert not first['success'] and calls == [('publish', [])]
    save('step', source.replace('n:1', 'n:2').replace('1/$n', '1/($n+1)'),
         expected_revision=old['revision'])
    plan = compile_program(request['code'], reg, inputs=request['inputs'], definitions=definitions())
    update = {**request, 'function_refs': plan.dependencies['function_refs'], 'repair': first['resume']}
    checked = handle_request({**update, 'check': True}, str(tmp_path))
    assert checked.get('ok'), checked
    update['repair']['plan_hash'] = checked['repair']['plan_hash']
    repaired = handle_request(update, str(tmp_path))
    assert repaired['success'] and repaired['value'] == {'computed': 3, 'ratio': 1}, repaired
    assert calls == [('publish', [])]


def test_unsupported_closure_stays_explicit_while_other_records_migrate(abilities, monkeypatch):
    import function_store
    with monkeypatch.context() as old:
        legacy(old)
        ref = save('annotated', '[def:annotated]($x:"Number"){return $x}')
        save('wrapper', '[def:wrapper]($x){return [fn:annotated]{x:$x}}')
        save('simple', '[def:simple](){return 7}')
    report = revalidate(apply=True)
    assert report['functions']['annotated']['status'] == 'source-required'
    assert report['functions']['wrapper']['status'] == 'source-required'
    assert report['functions']['simple']['status'] == 'certified'
    assert function_store.resolve('annotated')['revision'] == ref['revision']
    assert set(definitions().interfaces) == {'simple'}


@pytest.mark.parametrize('args,issue', [('rows:[1,2],step:0', 'SLICE_BOUND'),
                                      ('rows:7,step:1', 'TYPE')])
def test_slice_interface_rejects_new_invalid_inputs(abilities, args, issue):
    reg, calls, _ = abilities
    save('slice_rows', '[def:slice_rows]($rows,$step){return $rows[::$step]}')
    plan = compile_program('[fn:slice_rows]{' + args + '}', reg, definitions=definitions().interfaces_only())
    assert any(row['code'] == issue for row in plan.issues), plan.report()
    assert calls == []


def test_semantic_edition_cache_invalidates_on_file_change(tmp_path, monkeypatch):
    from pathlib import Path
    import ibl_v2_semantic as semantic
    original = semantic.edition()
    # Isolate the semantic sources so no repository edit occurs during pytest.
    root = Path(semantic.__file__).parent
    for path in root.glob('ibl_v2_*.py'):
        (tmp_path / path.name).write_bytes(path.read_bytes())
    monkeypatch.setattr(semantic, '__file__', str(tmp_path / 'ibl_v2_semantic.py'))
    assert semantic.edition() == original
    hits = semantic._edition.cache_info().hits
    assert semantic.edition() == original
    assert semantic._edition.cache_info().hits > hits
    source = tmp_path / 'ibl_v2_binding.py'
    source.write_text(source.read_text() + '\n# changed implementation edition\n')
    assert semantic.edition() != original


@pytest.mark.parametrize('expression', ['[probe:asset]{id:$id}', '$reader{id:$id}'])
def test_binding_retains_dynamic_assets_for_direct_and_indirect_calls(abilities, expression):
    from ibl_v2_adapters import Adapter
    reg, calls, _ = abilities
    reg['probe:asset'] = Adapter({'version': 1, 'params': {'id': 'Text'}, 'result': 'Text',
        'effects': ['read_external']}, lambda rt, a: calls.append(a['id']) or a['id'],
        dependency=lambda args: None if args.get('id') == 'a' else
            {'selected': args.get('id'), 'revision': 1, 'symbol': {'opaque': True}})
    save('asset', '[def:asset]($id){$reader=&[probe:asset];return ' + expression + '}')
    plan = compile_program('return [[fn:asset]{id:"a"},[fn:asset]{id:"b"},[fn:asset]{id:"a"}]',
                           reg, definitions=definitions())
    assert not plan.issues and calls == []
    result = Runtime(plan).run()
    assert result['success'] and result['value'] == ['a', 'b', 'a'], result
    assert calls == ['a', 'b', 'a']


if __name__ == '__main__':
    raise SystemExit(pytest.main([__file__]))
