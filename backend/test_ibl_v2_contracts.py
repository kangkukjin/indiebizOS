"""효과 계약은 검사·함수 조합·실행·읽기 재사용에 같은 의미를 준다."""
import json
from pathlib import Path

import boot_paths  # noqa: F401
import pytest
from ibl_v2_entry import handle_request
from model_result_view import describe_actions


ROOT = Path(__file__).resolve().parents[1]


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
def test_full_scheduling_program_and_new_policy_preserve_all_results(tmp_path, monkeypatch):
    import csv
    import runpy
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
