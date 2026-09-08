"""ep3176 실제 실패의 축소 재현과 대입·회상·파일 통화 불변식."""
import json
import sys
from pathlib import Path

import boot_paths  # noqa: F401
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from ibl_boundary_probe import probe
from ibl_boundary_cases import literal as q
from idiom_experiment_worker import load
from test_names_first_recall_2026_09_05 import env, _add  # noqa: F401


@pytest.mark.parametrize('rows', [[], [{'v': 0}], [{'v': False}], [{'v': None}],
                                  [{'v': '007'}], [{'v': '$items'}], [{'v': "'한글\n"}]])
@pytest.mark.parametrize('sink', ['$q >> [table:take]{n:10}',
                                  '$q.items >> [table:take]{n:10}',
                                  '[table:take]{items:$q,n:10}',
                                  '[table:take]{items:${q.value},n:10}',
                                  '$qq=$q\n$qq >> [table:take]{n:10}'])
def test_assignment_alias_preserves_collection_across_consumers(rows, sink):
    code = '$r=[table:take]{items:' + q(rows) + ',n:10}\n$q=$r.items\n' + sink
    result = probe(dict(id='alias', code=code, expected=rows, error=False, contains=None))
    assert result['ok'], result


@pytest.mark.parametrize('value', [{'value': [1, 2]}, {'message': '원문'}, {'items': [3]}, {'field': False}])
def test_path_assignment_preserves_object_keys(value):
    code = '$r=[table:take]{items:[{data:' + q(value) + '}],n:1}\n$q=$r.items.0.data\n$qq=$q\n[table:take]{items:[{v:${qq.value}}],n:1}'
    # value라는 실제 데이터 키가 있으면 그 키를 읽는다. 그 밖에는 이전 .value 메타 접근도 유지.
    expected = value['value'] if 'value' in value else value
    result = probe(dict(id='object', code=code, expected=[{'v': expected}], error=False, contains=None))
    assert result['ok'], result


def test_user_object_value_is_not_an_assignment_envelope():
    from common.currency import value_result_payload
    obj = {'value': [1], 'assigned': 'user', 'success': True}
    assert value_result_payload(obj) == (False, obj)


@pytest.mark.parametrize('condition', ['$q.flag == true', 'count($q.items) == 1'])
def test_assignment_paths_are_identical_in_conditions(condition):
    code = ('$r=[table:take]{items:[{data:{flag:true,items:[1]}}],n:1}\n'
            '$q=$r.items.0.data\n[if:' + condition + ']{[table:take]{items:[{ok:true}],n:1}}')
    result = probe(dict(id='condition', code=code, expected=[{'ok': True}], error=False, contains=None))
    assert result['ok'], result


def test_recall_exposes_parent_functions_as_currency_without_bodies(env):
    tree, db = env
    child = '보고서/부동산 발굴'
    _add(db, '지역별 기록', '[self:time]{}', child)
    pid = _add(db, '최신 보고서 읽기', '$return=[self:read]{path:$파일}', '보고서', category='phrase', alias='공통읽기', ok=2)
    _add(db, '관계없는 함수', '[self:time]{}', '오디오', category='phrase', alias='관계없음')
    out = tree.recall(child, db)
    entry = next(r for r in out['items'] if r['id'] == pid)
    assert entry['topic'] == '보고서' and entry['success_rate'] == 1.0
    assert entry['call'].startswith('[fn:공통읽기]') and '[self:read]' not in entry['ibl_code']
    assert out['count'] == 2 and out['inherited_function_count'] == 1
    assert '상위 가지 보고서' in out['text'] and '관계없음' not in out['text']
    assert '[self:read]' in tree.recall(child, db, expand='공통읽기')['text']
    assert all('success_rate' in r for r in out['items'])
    dataops = load('_ep3176_dataops', Path(__file__).parents[1] / 'data/packages/installed/tools/data-ops/handler.py')
    from types import SimpleNamespace
    result = dataops.execute({'items': out['items'], 'columns': ['alias', 'intent', 'signature', 'returns', 'success_rate', 'bypass_count']}, SimpleNamespace(tool_name='data_select'))
    assert result['success'], result


def test_empty_recall_does_not_promise_automatic_naming(env):
    tree, db = env
    _add(db, '기록', '[self:time]{}', '기록')
    text = tree.recall('기록', db)['text']
    assert '자동 작명은 중단' in text
    assert '증류가 이름을 붙인다' not in text


@pytest.mark.parametrize('name', ['note.txt', '한글.json', 'subdir'])
def test_list_and_find_share_file_fields(tmp_path, name):
    from tool_context import ToolContext
    root = Path(__file__).parents[1]
    fs = load('_ep3176_fs', root / 'data/packages/installed/tools/system_essentials/handler.py')
    p = tmp_path / name
    p.mkdir() if name == 'subdir' else p.write_text('value')
    outputs = [json.loads(fs.execute({'path': str(tmp_path), 'pattern': name}, ToolContext(str(tmp_path), tool)))
               for tool in ['list_directory', 'glob_files']]
    fields = ['name', 'path', 'size', 'mtime', 'dir', 'is_dir']
    assert {k: outputs[0]['items'][0][k] for k in fields} == {k: outputs[1]['items'][0][k] for k in fields}
    dataops = load('_ep3176_list_projection', root / 'data/packages/installed/tools/data-ops/handler.py')
    from types import SimpleNamespace
    result = dataops.execute({'_prev_result': outputs[0], 'columns': ['name']}, SimpleNamespace(tool_name='data_select'))
    assert result['success'] and result['items'] == [{'name': name}]


@pytest.mark.parametrize('sequence', [13, 27, 36])
def test_actual_episode_failure_sentence_unchanged(sequence, env, tmp_path, monkeypatch):
    import hashlib
    import ibl_engine
    import workflow_engine
    import episode_logger
    from ibl_parser import parse_with_vars
    from tool_context import ToolContext
    tree, db = env
    _add(db, '지역 기록', '[self:time]{}', '보고서/부동산 발굴')
    _add(db, '공통 함수', '$return=[self:read]{path:$파일}', '보고서', alias='공통읽기', category='phrase')
    memory = tree.recall('보고서/부동산 발굴', db)
    fixtures = json.loads((Path(__file__).parents[1] / 'docs/experiments/episode3176_failures.json').read_text())
    fixture = next(f for f in fixtures['fixtures'] if f['event_seq'] == sequence)
    assert hashlib.sha256(fixture['code'].encode()).hexdigest() == fixture['code_sha256']
    queue = [dict(slug='a', name='A', unit='a', tier=1, visits=0, last_visited='', verdict='보류'),
             dict(slug='b', name='B', unit='b', tier=1, visits=1, last_visited='2026-09-07', verdict='관심')]
    (tmp_path / 'region.json').write_text('{}')
    root = Path(__file__).parents[1]
    dataops = load('_ep3176_actual_dataops', root / 'data/packages/installed/tools/data-ops/handler.py')
    fs = load('_ep3176_actual_fs', root / 'data/packages/installed/tools/system_essentials/handler.py')
    original = ibl_engine._execute_ibl_impl

    def leaf(step, project, agent_id=None):
        node, action = step.get('_node'), step.get('action')
        params = dict(step.get('params') or {})
        if node == 'table':
            return dataops.execute(params, ToolContext(project, 'data_' + action))
        if node == 'self' and action == 'memory':
            return memory
        if node == 'self' and action == 'read':
            path = params.get('path', '')
            if path == 'rotation-fixture.json':
                return {'queue': queue, 'explore_first': True}
            if path == 'cfg-fixture.json':
                return {'items': [{'config': 'fixture'}]}
            assert path.endswith(('_thesis.md', 'housing_report_2026-09-08_서산시.md'))
            return 'fixture report'
        if node == 'self' and action == 'list':
            return fs.execute({**params, 'path': str(tmp_path)}, ToolContext(project, 'list_directory'))
        if node == 'sense' and action == 'realty':
            assert params['op'] == 'codes'
            return {'items': [{'지역': '당진'}, {'지역': '서산'}, {'지역': '서울'}]}
        assert any(step.get(k) for k in ['_assign', '_var_emit']), step
        return original(step, project, agent_id)

    monkeypatch.setattr(ibl_engine, '_execute_ibl_impl', leaf)
    monkeypatch.setattr(ibl_engine, 'execute_ibl', leaf)
    monkeypatch.setattr(episode_logger, 'record_trajectory_event', lambda *a, **k: None)
    prefix = '$rot=[self:read]{path:"rotation-fixture.json"}\n$cfg=[self:read]{path:"cfg-fixture.json"}\n'
    steps, _ = parse_with_vars(prefix + fixture['code'])
    result = workflow_engine.execute_pipeline(steps, str(tmp_path))
    assert result['success'], result
    from ibl_boundary_cases import payload
    final = payload(result)
    if sequence == 27:
        assert [r['slug'] for r in final if 'slug' in r] == ['a', 'b']
    if sequence == 36:
        assert final == [{'지역': '당진'}, {'지역': '서산'}]


if __name__ == '__main__':
    raise SystemExit(pytest.main([__file__, *sys.argv[1:]]))
