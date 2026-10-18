"""실제 읽기·목록 생산자와 IBL 영수증/증류 연결."""
import json
from types import SimpleNamespace

import boot_paths  # noqa: F401
import pytest
from test_forage_evidence import env, row  # noqa: F401
from test_ibl_general_capabilities import boundary  # noqa: F401
from test_structured_file_read import reader  # noqa: F401
from test_repair_workspace_completion import module
import source_observation as so
import forage_evidence as fe
from distill_memory_adapters import prepare_forage, apply_forage


@pytest.mark.parametrize('ending', ['\n', '\r', '\r\n'])
def test_partial_actual_read_and_selector_roundtrip(env, ending):
    handler = module('handler')
    path = env / 'data.txt'; path.write_bytes(('header' + ending + 'unit=1000' + ending + 'tail').encode())
    result = handler.execute({'path': str(path), 'offset': 1, 'limit': 1},
                             SimpleNamespace(tool_name='read_file', project_path=str(env), agent_id='owner'))
    evidence = so.from_result(result)
    assert len(evidence) == 1
    e = evidence[0]
    assert e['scope']['selector'] == {'start': 1, 'end': 2} and not e['scope']['complete']
    assert fe.Checker('content').check(e)['state'] == 'unchanged'
    path.write_bytes(('other' + ending + 'unit=1000' + ending + 'tail').encode())
    assert fe.Checker('content').check(e)['state'] == 'unchanged'
    path.write_bytes(('other' + ending + 'unit=1' + ending + 'tail').encode())
    assert fe.Checker('content').check(e)['state'] == 'changed'


def test_listing_provider_attests_only_requested_names(env):
    handler = module('handler'); (env / 'a.csv').touch(); (env / 'b.txt').touch()
    result = handler.execute({'path': str(env), 'pattern': '*.csv'},
                             SimpleNamespace(tool_name='list_directory', project_path=str(env), agent_id='owner'))
    e = so.from_result(result)[0]
    assert e['scope']['pattern'] == '*.csv' and e['scope']['depth'] == 1
    assert fe.Checker('content').check(e)['state'] == 'unchanged'
    (env / 'new.csv').touch()
    assert fe.Checker('content').check(e)['state'] == 'changed'


def test_real_ibl_read_distill_nongeneralized_meaning_and_recall(env, reader):
    import forage_memory as fm
    p = env / 'orders.csv'; p.write_text('customer,amount_thousand\na,3\n')
    raw, out = reader('return [self:read]{path:"orders.csv"}')
    assert out['success']
    evidence = so.from_result(out)
    assert evidence, out.get('evidence')
    job = {'principal': 'owner', 'body_id': so.identity()[1], 'job_key': 'read-job',
           'recorded_at': so.now(), 'write_deep': False,
           'tool_calls': [{'success': True, 'result': out, 'input': {'code': 'read'}}]}
    section = prepare_forage(job)
    assert section['eligible'] and section['observations'][0]['source_evidence']
    c = dict(body='mac', locus=str(p), kind='convention', claim='금액은 천 원 단위, 고객 번호로 연결',
             prior_class='semantic', generalizes=False, observation_ids=[1], relation='NEW')
    result = apply_forage(job, section, c, 'read-candidate')
    assert result['status'] == 'saved'
    recalled = fm.recall(locus=str(p), evidence_check='content')['map'][0]
    assert recalled['evidence_status']['state'] == 'unchanged' and not recalled['generalizes']
    assert recalled['evidence_doc']
    # Job-backed direct note uses the same resolver, not model hashes.
    import distill_ledger as ledger
    ledger.create(job); ledger.update(job['job_key'], prepared={'sections': {'forage': section}})
    other = fm.note_map(body='mac', locus=str(p), kind='identity', claim='주문 항목', provenance={
        'observation_refs': [{'job_key': job['job_key'], 'observation_id': 1}]})
    assert other['success']
    forged = fm.note_map(body='mac', locus=str(p), kind='identity', claim='위조', provenance={
        'observation_refs': [{'job_key': job['job_key'], 'observation_id': 999}]})
    assert not forged['success']


def test_read_during_mutation_is_unstable(env, monkeypatch):
    handler = module('handler'); p = env / 'x'; p.write_text('original')
    original = so.file_state; count = 0
    def state(path):
        nonlocal count
        count += 1
        if count == 2:
            p.write_text('changed')
        return original(path)
    monkeypatch.setattr(so, 'file_state', state)
    result = handler.execute({'path': str(p)}, SimpleNamespace(tool_name='read_file', project_path=str(env), agent_id='owner'))
    assert so.from_result(result)[0]['stable'] is False


def test_plain_json_looking_file_is_not_rewritten(env):
    handler = module('handler'); p = env / 'x.json'; p.write_text('{"source_observation_ref":"business-data"}')
    result = handler.execute({'path': str(p)}, SimpleNamespace(tool_name='read_file', project_path=str(env), agent_id='owner'))
    assert result == p.read_text()
    assert so.from_result(result)[0]['source']['address'] == str(p)


def test_partial_header_does_not_reread_whole_large_file(env):
    handler = module('handler'); p = env / 'large.txt'
    p.write_bytes(b'unit=1000\n' + b'x' * (fe.CHECK_LIMITS['bytes'] + 1))
    result = handler.execute({'path': str(p), 'offset': 0, 'limit': 1},
                             SimpleNamespace(tool_name='read_file', project_path=str(env), agent_id='owner'))
    e = so.from_result(result)[0]
    checker = fe.Checker('content')
    assert checker.check(e)['state'] == 'unchanged'
    assert checker.bytes < 65536


def test_ambiguous_plaintext_is_not_attested_to_wrong_source(env):
    handler = module('handler')
    for name in ('a.txt', 'b.txt'):
        p = env / name; p.write_text('same content')
        handler.execute({'path': str(p)}, SimpleNamespace(tool_name='read_file', project_path=str(env), agent_id='owner'))
    assert so.from_result('same content') == []


if __name__ == '__main__':
    import sys
    raise SystemExit(pytest.main([__file__] + sys.argv[1:]))
