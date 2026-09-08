"""실험 오라클 검증. 실제 모델은 호출하지 않고 고정 과제의 양성·음성 대조군을 실행."""
import json
from pathlib import Path
import sys

import pytest
import boot_paths  # noqa: F401

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
from idiom_experiment_worker import run_trial
from idiom_experiment_cases import GOLD
from idiom_experiment_cases import decoded


@pytest.mark.parametrize('case', list(GOLD))
def test_reference_programs_meet_output_contract(case, capsys):
    out = run_trial(GOLD[case], case)
    assert out['quality_ok'], out['verdict']


def test_oracle_rejects_successful_but_discarded_read(capsys):
    catalog = json.loads((ROOT / 'data/idioms/curated.json').read_text())
    entry = next(e for e in catalog['idioms'] if e['name'] == '좁혀서읽기')
    entry['body'] = entry['body'].replace(', collect: true', '')
    code = '[fn:좁혀서읽기]{패턴:"NEEDLE",루트:"notes",파일패턴:"*.txt"}'
    out = run_trial(code, 'snippets', catalog=catalog)
    assert out['result']['success'] and not out['quality_ok']
    assert out['observed']['leaf_calls'].count('self:read') == 3
    repaired = run_trial(code, 'snippets')
    assert repaired['quality_ok']
    rows = decoded(repaired['result']['final_result'])['items']
    assert [row['파일'] for row in rows] == [f'notes/{i:02d}.txt' for i in range(3)]
    assert all(row['줄번호'] == 1 and row['value'].count('context') == 29 for row in rows)


def test_summary_idiom_returns_documented_fields(capsys):
    out = run_trial(GOLD['read_each'], 'read_each')
    rows = decoded(out['result']['final_result'])['items']
    assert rows[0]['message'] == 'SUMMARY: fixture'
    assert rows[0]['title'] == 'first'
    assert rows[1]['title'] == 'broken' and rows[1]['_error']
    assert '요약' not in rows[0]


def test_oracle_rejects_misapplied_idiom(capsys):
    short = '[fn:최신파일읽기]{폴더:"reports",패턴:"*.md"}'
    assert run_trial(short, 'latest')['quality_ok']
    assert not run_trial(short, 'latest_tail')['quality_ok']
    partial = '[fn:좁혀서읽기]{패턴:"NEEDLE",루트:"notes",파일패턴:"*.txt"}'
    assert not run_trial(partial, 'all_hits')['quality_ok']


def test_execution_rejects_live_paths_and_external_tools(capsys):
    assert not run_trial('[self:read]{path:"/etc/hosts"}', 'latest')['quality_ok']
    denied = run_trial('[self:script]{op:"run",id:"anything"}', 'latest')
    assert '허용하지 않는 도구' in denied['verdict']


if __name__ == '__main__':
    raise SystemExit(pytest.main([__file__, *sys.argv[1:]]))
