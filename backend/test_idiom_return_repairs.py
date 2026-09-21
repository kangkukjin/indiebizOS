"""관용구 반환형 감사 회귀. 라이브 원장·외부 작업 대신 격리된 실제 실행기를 쓴다."""
import json
import sys
from pathlib import Path

import pytest
import boot_paths  # noqa: F401

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
CATALOG = json.loads((ROOT / 'data/idioms/curated.json').read_text())
ENTRIES = {e['name']: e for e in CATALOG['idioms']}
WAIT_BODY = ('$job = [self:script]{op:"run",id:"${작업}",background:true}; '
             '[repeat: until $st.status == "done", max:30, every:"10s"]{'
             '$st = [self:script]{op:"status",job_id:"$job.job_id"}}; $return = $st')


@pytest.mark.parametrize('name', ['본문에서찾기', '미처리만고르기'])
def test_unknown_inputs_have_items_returns(name):
    from ibl_typecheck import return_type_of
    assert return_type_of(ENTRIES[name]['body']) == 'items⟨열 미상⟩'


@pytest.mark.parametrize('action,params', [
    ('filter', '{where:{id:1}}'), ('dedup', '{by:"id"}'),
    ('sort', '{by:"id"}'), ('since', '{key:"fixture",by:"id",peek:true}'),
])
def test_row_transform_declares_items_for_unknown_input(action, params):
    from ibl_typecheck import return_type_of
    assert return_type_of(f'$return = $목록 >> [table:{action}]' + params).startswith('items⟨')


def test_assignment_preserves_reference_and_loop_binding_types():
    from ibl_typecheck import return_type_of, typecheck_code
    assert return_type_of('$rows = [{id:1}]; $return = $rows') == 'items⟨id⟩'
    assert return_type_of('$return = $목록') == '?'
    assert return_type_of(WAIT_BODY).startswith('items⟨')
    result = typecheck_code('[repeat: while false, max:1]{$rows = [{id:1}]}; $copy = $rows')
    assert result['types'][-1] == '$copy: items⟨id⟩'
    assert any('분기 몸 안에서만 태어난' in i['message'] for i in result['issues'])
    # 첫 회차에만 맞는 타입을 뒤 회차에도 가정하지 않는다.
    assert return_type_of('$a = [{id:1}]; [repeat:2]{$b=$a; $a=1}; $return=$b') == '?'


def test_left_columns_do_not_override_items_emission():
    from ibl_typecheck import return_type_of
    assert return_type_of('$return = $a & $b >> [table:join]{on:"id",how:"anti"}') == 'items⟨열 미상⟩'


def test_cold_api_check_registers_sources_and_cached_contracts(monkeypatch):
    import api_ibl
    import ibl_idiom
    import ibl_typecheck
    monkeypatch.setattr(ibl_typecheck, 'FN_CODE_SOURCES', [])
    monkeypatch.setattr(ibl_typecheck, '_FN_CACHE', {})
    monkeypatch.setattr(ibl_idiom, '_workflow_code_by_name', lambda name: None)
    monkeypatch.setattr(ibl_idiom, '_phrase_code_by_alias', lambda name: '$return = [{id:1}]')
    for _ in range(2):
        result = api_ibl._typecheck_of('[fn:검수시험]{}')
        assert result['fn_returns'] == {'검수시험':'items⟨id⟩'}
        assert result['types'] == ['(1) items⟨id⟩']
    assert len(ibl_typecheck.FN_CODE_SOURCES) == 2


@pytest.mark.parametrize('body', [
    '$return = [sense:search]{query:$질의} >> [table:brief]{instruction:"요약"} >> [table:take]{n:1}',
    '$rows = [{id:1}]; $return = $rows >> [table:select]{columns:["missing"]}',
    '[self:write]{path:$경로,content:"x"} >> [table:filter]{where:{id:1}}',
    '[self:read]{path:$경로}; [table:take]{n:1}',
])
def test_def_and_external_function_cannot_hide_definite_errors(body, monkeypatch):
    import ibl_typecheck
    from register_idiom import _gates
    defined = ibl_typecheck.typecheck_code('[def:오류재현]{' + body + '}')
    assert not defined['ok'], defined
    assert any(i['severity'] == 'error' and 'fn.body' in i['at'] for i in defined['issues'])
    info, why = _gates('오류재현', '잘못된 함수 본문의 등록 거절을 확인할 때', body)
    assert info is None and '타입 오류' in why
    monkeypatch.setattr(ibl_typecheck, 'FN_CODE_SOURCES', [lambda name: body])
    monkeypatch.setattr(ibl_typecheck, '_FN_CACHE', {})
    for _ in range(2):
        result = ibl_typecheck.typecheck_code('[fn:오류재현]{질의:"x",경로:"fixture"}')
        assert not result['ok'], result
    assert not ibl_typecheck._FN_CACHE  # 두 번째 호출이 캐시 때문에 거짓 통과하면 안 된다.


def test_function_incoming_currency_and_unknown_arguments_remain_valid():
    from ibl_typecheck import typecheck_code
    for body in ('$return = [table:take]{n:$개수}',
                 '$return = $목록 >> [table:select]{columns:["title"]}',
                 '$return = [self:read]{path:$경로} >> [table:take]{n:1}'):
        result = typecheck_code('[def:정상호출]{' + body + '}')
        assert result['ok'] and not result.get('abstained'), result


@pytest.mark.parametrize('location', ['body', 'example', 'extra'])
def test_catalog_rejects_invalid_params_in_body_and_every_example(location):
    from curate_idioms import validate_catalog
    entry = json.loads(json.dumps(CATALOG['idioms'][0]))
    bad = '[self:read]{path:"fixture.txt",zzzz_unknown_test_key:1}'
    if location == 'extra':
        entry['examples'] = [{'code': entry['example'] + '; ' + bad}]
    else:
        entry[location] += '; ' + bad
    with pytest.raises(ValueError, match='존재하지 않는'):
        validate_catalog({'idioms': [entry]})


def test_conditional_includes_skipped_input_but_not_with_else():
    from ibl_typecheck import return_type_of
    head = '$rows = [{id:1}]; $return = $rows >> '
    branch = '[if:not empty($items)]{[self:read]{path:"x.txt"}}'
    assert return_type_of(head + branch) == '?'
    assert return_type_of(head + branch + ' [else]{[self:read]{path:"y.txt"}}') == 'scalar'
    assert return_type_of(head + '[if:true]{[table:take]{n:1}}') == 'items⟨id⟩'


@pytest.mark.parametrize('name', ['최신파일읽기', '최신범위읽기', '직전보고서찾아읽기'])
@pytest.mark.parametrize('pattern', ['*.md', '*.rst'])
def test_file_reader_present_and_missing_candidates(name, pattern):
    from ibl_typecheck import return_type_of
    from idiom_experiment_worker import run_trial
    from idiom_value_cases import final_value
    args = {'폴더': 'reports', '패턴': pattern}
    if name == '최신범위읽기':
        args.update(시작줄=1, 줄수=2)
    trial = run_trial(f'[fn:{name}]' + json.dumps(args, ensure_ascii=False), 'dedup')
    result = trial['result']
    assert result['success'], result
    value = final_value(result)
    if pattern == '*.rst':
        assert value['items'] == [], value
        assert 'self:read' not in trial['observed']['leaf_calls']
    else:
        marker = 'OLD_REPORT' if name == '직전보고서찾아읽기' else 'NEW_REPORT'
        assert isinstance(value, str) and marker in value
    assert return_type_of(ENTRIES[name]['body']) == '?'


@pytest.mark.parametrize('name,args,expected', [
    ('본문에서찾기', {'목록': [{'text':'NEEDLE', 'url':'a'}, {'text':'noise', 'url':'b'}],
                  '패턴':'NEEDLE', '문맥':0, '개수':1}, [{'text':'NEEDLE', 'url':'a'}]),
    ('미처리만고르기', {'후보':[{'id':1}, {'id':2}], '처리됨':[{'id':1}], '키':'id'}, [{'id':2}]),
])
def test_row_idioms_runtime_matches_contract(name, args, expected):
    from idiom_experiment_worker import run_trial
    from idiom_value_cases import final_value
    result = run_trial(f'[fn:{name}]' + json.dumps(args, ensure_ascii=False), 'dedup')['result']
    assert result['success'], result
    assert final_value(result)['items'] == expected


def test_wait_reference_runtime_is_items(tmp_path, monkeypatch):
    import ibl_engine
    import episode_logger
    from ibl_parser import parse
    from workflow_engine import execute_pipeline
    from idiom_value_cases import final_value
    original = ibl_engine._execute_ibl_impl
    calls = []

    def leaf(ti, project, agent_id=None):
        if ti.get('_node') == 'self' and ti.get('action') == 'script':
            op = ti['params']['op']
            calls.append(op)
            if op == 'run':
                return {'success':True, 'job_id':'fixture', 'status':'running'}
            return {'success':True, 'job_id':'fixture', 'status':'done',
                    'items':[{'job_id':'fixture', 'status':'done'}]}
        return original(ti, project, agent_id)

    monkeypatch.setattr(ibl_engine, '_execute_ibl_impl', leaf)
    monkeypatch.setattr(ibl_engine, 'execute_ibl', leaf)
    monkeypatch.setattr(episode_logger, 'record_trajectory_event', lambda *a, **kw: None)
    result = execute_pipeline(parse('[def: 확인대기]{' + WAIT_BODY + '}; [fn:확인대기]{작업:"fixture"}'), str(tmp_path))
    assert result['success'], result
    value = final_value(result)
    assert value == [{'job_id':'fixture', 'status':'done'}]
    assert calls == ['run', 'status']


def test_metadata_refresh_legacy_name_preserves_registration(tmp_path, monkeypatch):
    import ibl_usage_db
    from register_idiom import _gates, refresh_idiom_metadata
    from test_judgment_idiom_registration import Registry
    monkeypatch.setattr(ibl_usage_db, '_tree_refresh', lambda *a, **kw: None)
    db = Registry(tmp_path / 'registry.db')
    name = '나레이션스크립트띄우고대기하기'
    code = '[self:script]{op:"status",job_id:"fixture"}'
    with db._get_connection() as con:
        con.execute('CREATE TABLE ibl_examples(id INTEGER PRIMARY KEY, alias, intent, ibl_code, '
                    'returns, signature, topic, always_on, success_count, fail_count)')
        con.execute('INSERT INTO ibl_examples VALUES(1,?,?,?,?,?,?,?,?,?)',
                    (name, '과거 등록', code, '?', '[]', '개발', 0, 7, 2))
    assert _gates(name, '과거 등록', code)[1]  # 신규 승격 정책은 계속 유지한다.
    before = db.find_phrase_by_alias(name)
    assert refresh_idiom_metadata(db, name)
    after = db.find_phrase_by_alias(name)
    assert after['returns'].startswith('items⟨')
    assert {k:v for k,v in before.items() if k not in ('returns','signature')} == {
        k:v for k,v in after.items() if k not in ('returns','signature')}
    assert not refresh_idiom_metadata(db, name)
    with db._get_connection() as con:
        con.execute('UPDATE ibl_examples SET ibl_code=?', ('[self:missing_action]{}',))
    with pytest.raises(ValueError, match='계약 갱신 거절'):
        refresh_idiom_metadata(db, name)


if __name__ == '__main__':
    raise SystemExit(pytest.main([__file__, *sys.argv[1:]]))
