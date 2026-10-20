"""효과 계약은 검사·함수 조합·실행·읽기 재사용에 같은 의미를 준다."""
import json
import hashlib
import os
from pathlib import Path

import boot_paths  # noqa: F401
import pytest
from ibl_v2_entry import handle_request
from model_result_view import describe_actions
from test_ibl_v2_assets import memory  # noqa: F401 — 격리한 관용구 DB


ROOT = Path(__file__).resolve().parents[1]


@pytest.mark.parametrize('action', ['list', 'file_find', 'grep'])
@pytest.mark.parametrize('change', ['add', 'delete', 'content', 'empty'])
def test_file_discovery_reuse_observes_current_sources(tmp_path, action, change):
    folder = tmp_path / 'sources'
    folder.mkdir()
    a, b = folder / 'a.txt', folder / 'b.txt'
    a.write_text('10')
    b.write_text('20')
    args = 'path:$folder,pattern:"*.txt",hash:true'
    if action == 'grep':
        args = 'path:$folder,pattern:"[0-9]+",regex:true,file_pattern:"*.txt"'
    code = f'return [self:{action}]{{{args}}}'
    request = {'edition': 2, 'code': code, 'inputs': {'folder': str(folder)}}
    first = handle_request(request, str(tmp_path))
    assert first['success'], first
    if change == 'add':
        (folder / 'c.txt').write_text('30')
    elif change == 'delete':
        b.unlink()
    elif change == 'empty':
        a.unlink()
        b.unlink()
    else:
        stamp = a.stat()
        a.write_text('90')
        os.utime(a, ns=(stamp.st_atime_ns, stamp.st_mtime_ns))
    # A new run must discover the current population, even without any writes.
    again = handle_request({**request, 'reuse': first['resume']}, str(tmp_path))
    assert again['success'], again
    rows = again['value'] if action == 'list' else again['value']['items']
    expected = {str(p): p.read_text() for p in folder.glob('*.txt')}
    if action == 'grep':
        assert {str(tmp_path / r['파일']): r['내용'] for r in rows} == expected
    else:
        assert {r['path']: r['sha256'] for r in rows} == {
            path: hashlib.sha256(text.encode()).hexdigest()
            for path, text in expected.items()
        }
    assert again['reuse']['reused_calls'] == 0
    # Resume is historical replay of the same run, not a new observation.
    resumed = handle_request({**request, 'resume': first['resume']}, str(tmp_path))
    assert resumed['success'] and resumed['value'] == first['value'], resumed


def test_discovery_refresh_keeps_unchanged_file_reads_reusable(tmp_path):
    source = tmp_path / 'sources'
    source.mkdir()
    (source / 'a.txt').write_text('10')
    (source / 'b.txt').write_text('20')
    code = '''$files=[self:list]{path:$folder,pattern:"*.txt",hash:true}
$rows=$files >> [table:each] {
  $doc=[self:read]{path:$it.path}
  return {value:number($doc.text),sha256:$it.sha256}
}
return {rows:$rows,total:sum(map($rows,($r)=>$r.value))}'''
    request = {'edition': 2, 'code': code, 'inputs': {'folder': str(source)}}
    first = handle_request(request, str(tmp_path))
    assert first['success'] and first['value']['total'] == 30, first
    same = handle_request({**request, 'reuse': first['resume']}, str(tmp_path))
    assert same['success'] and same['value'] == first['value'], same
    (source / 'c.txt').write_text('30')
    changed = handle_request({**request, 'reuse': same['resume']}, str(tmp_path))
    assert changed['success'] and changed['value']['total'] == 60, changed
    assert same['reuse']['reused_calls'] == 2
    assert changed['reuse']['reused_calls'] == 2


def test_groupby_declared_pure_and_composes_inside_lambda():
    described = describe_actions(['table:groupby'], {'table'}, edition=2)
    assert described['actions'][0]['definition']['callable_contract']['effects'] == ['pure']
    code = (ROOT / 'docs/experiments/long_sentence_imagination/round_17/repro/groupby_in_lambda.ibl').read_text()
    checked = handle_request({'edition': 2, 'code': code, 'check': True})
    assert not checked['issues'], checked
    result = handle_request({'edition': 2, 'code': code})
    assert result['success'] and result['value'] == [1], result


def test_groupby_does_not_invalidate_reused_reads(tmp_path):
    for name in ('a', 'b'):
        (tmp_path / f'{name}.json').write_text(json.dumps([{'k': name}, {'k': name}]))
    code = '''$a=[self:read]{path:"a.json",format:"json"}
$b=[self:read]{path:"b.json",format:"json"}
$g=$a >> [table:groupby]{by:"k",agg:{n:["count"]}}
return {a:$g,b:$b}'''
    first = handle_request({'edition': 2, 'code': code}, str(tmp_path))
    assert first['success'], first
    again = handle_request({'edition': 2, 'code': code + '\n# reuse',
                            'reuse': {'run_id': first['resume']['run_id']}}, str(tmp_path))
    assert again['success'] and again['value'] == first['value'], again
    assert again['reuse']['reused_calls'] == 2, again


def test_groupby_invalid_aggregation_still_fails():
    result = handle_request({'edition': 2, 'code': '''[def:f]($rows){
$g=$rows >> [table:groupby]{by:"k",agg:{n:["invalid","v"]}}
return $g.items}
return map([{k:"a",v:2}],($r)=>[fn:f]{rows:[$r]})'''})
    assert not result['success'] and result['executed'], result


@pytest.mark.system
def test_full_scheduling_program_and_new_policy_preserve_all_results(tmp_path, monkeypatch, memory):
    import csv
    import runpy
    seeds = json.loads((ROOT / 'data/idioms/ibl_v2_seeds.json').read_text())
    seed = next(item for item in seeds if item.get('alias') == '정렬해추리기')
    assert memory.add_examples_batch([seed]) == 1
    fixture = ROOT / 'docs/experiments/long_sentence_imagination/round_17'
    generated = tmp_path / 'generated.json'
    monkeypatch.setenv('INDIEBIZ_SCRIPT_RESULT', str(generated))
    source = runpy.run_path(str(fixture / 'harness/generate.py'))
    data = json.loads(generated.read_text())
    folder = tmp_path / 'inputs'
    folder.mkdir()
    for name, rows in [('bookings_a.csv', data['a']), ('maintenance.csv', data['maintenance'])]:
        with (folder / name).open('w', newline='') as stream:
            writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
            writer.writeheader()
            writer.writerows(rows)
    for name, rows in [('bookings_b.json', data['b']), ('rooms.json', data['rooms'])]:
        (folder / name).write_text(json.dumps({'items': rows}))
    budget = {'steps': 1000000, 'rows': 100000}
    first = handle_request({'edition': 2, 'code': (fixture / 'drafts/p1_executed.ibl').read_text(),
                            'inputs': {'root': str(folder)}, 'budget': budget}, str(tmp_path))
    assert first['success'], first.get('error')
    def ordered(rows):
        return sorted(rows, key=lambda row: json.dumps(row, ensure_ascii=False, sort_keys=True))
    for buffer in (0, 15, 45):
        out = tmp_path / f'out{buffer}'
        result = handle_request({'edition': 2, 'code': (fixture / 'drafts/p2_executed.ibl').read_text(),
                                 'inputs': {'prepared': first['value'], 'buffer': buffer, 'out': str(out)},
                                 'budget': budget}, str(tmp_path))
        assert result['success'], result.get('error')
        assert result['value']['verified'] is True
        actual = json.loads((out / 'result.json').read_text())
        for key, expected in source['expected'](buffer).items():
            if isinstance(expected, list) and key != 'top10':
                assert ordered(actual[key]) == ordered(expected), (buffer, key)
            else:
                assert actual[key] == expected, (buffer, key)
        assert all(not (event.get('action') == 'self:read' and
                       str(folder) in json.dumps(event.get('targets', {}))) for event in result['evidence'])



if __name__ == "__main__":
    import sys
    raise SystemExit(pytest.main([__file__] + sys.argv[1:]))


@pytest.mark.parametrize('code,expected', [
    ('[self:notebook]{op:"versions",project_ref:"p",thread_ref:"t"}', 'source_ref'),
    ('[self:notebook]{op:"read",project_ref:"p",thread_ref:"t"}', 'version_ref'),
    ('[self:project]{op:"thread_update",questions:[],notes:"memo"}', 'questions'),
    ('[self:project]{op:"thread_update",questions:[],title:"title"}', 'questions'),
    ('[self:project]{op:"thread_update",questions:[],mode:"research"}', 'questions'),
])
def test_research_op_preconditions_reject_before_any_execution(code, expected):
    from ibl_v2_adapters import load_registry
    from ibl_v2_compile import compile_program
    from ibl_v2_runtime import Runtime
    plan = compile_program('[self:read]{path:"must-not-open"};' + code, load_registry())
    assert plan.issues and expected in str(plan.issues), plan.issues
    assert Runtime(plan).run()['executed'] is False


@pytest.mark.parametrize('code', [
    '[self:notebook]{op:"versions",project_ref:"p",source_ref:"s"}',
    '[self:notebook]{op:"read",project_ref:"p",version_ref:"v"}',
    '[self:project]{op:"thread_update",questions:[]}',
    '[self:project]{op:"thread_update",notes:"memo",title:"title"}',
])
def test_research_op_preconditions_accept_separate_valid_requests(code):
    from ibl_v2_adapters import load_registry
    from ibl_v2_compile import compile_program
    plan = compile_program(code, load_registry())
    assert not plan.issues, plan.issues
