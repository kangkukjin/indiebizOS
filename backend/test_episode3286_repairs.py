"""ep3286: 원천 절단의 each/fn 경계·복구 안내·평가/학습 전달 회귀."""
import json
import sys
from pathlib import Path

import boot_paths  # noqa: F401
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
from idiom_experiment_worker import load, run_trial
from idiom_experiment_cases import decoded
from ibl_honesty import truncation_evidence
from test_distill_source_recovery_2026_09_09 import _arm

URL = 'https://fixture.test/a'
CUT = {'scope': 'source', 'source': URL, 'unit': 'characters',
       'retained': 10000, 'total': 23218,
       'retry': {'url': URL, 'max_length': 23218}}


def source(truncated=True):
    out = {'success': True, 'items': [{'text': '원문'}], 'truncated': truncated}
    if truncated:
        out['truncations'] = [CUT]
    return out


def run(code, payload=None):
    trial = run_trial(code, 'dedup', source_results={URL: payload or source()})
    assert trial['result']['success'], trial
    assert trial['observed']['brief'] == 0
    return trial['result'], decoded(trial['result']['final_result'])


@pytest.mark.parametrize('parallel', [1, 2])
@pytest.mark.parametrize('named', [False, True])
@pytest.mark.parametrize('truncated', [False, True])
def test_each_and_idiom_preserve_source_warning_without_false_row_failure(parallel, named, truncated):
    if named:
        # 원장 정의를 같은 실행기에서 쓰되 병렬 조건만 대역 교재로 바꾼다.
        catalog = json.loads((ROOT / 'data/idioms/curated.json').read_text())
        entry = next(e for e in catalog['idioms'] if e['name'] == '주소마다읽기')
        entry['body'] = entry['body'].replace('collect: true', f'collect: true, parallel: {parallel}')
        code = '$목록=[{url:"' + URL + '"},{url:"https://fixture.test/c"}]; [fn:주소마다읽기]{목록:$목록,개수:2}'
        result = run_trial(code, 'dedup', catalog=catalog,
                           source_results={URL: source(truncated)})['result']
        final = decoded(result['final_result'])
    else:
        code = ('$목록=[{url:"' + URL + '"},{url:"https://fixture.test/c"}]; '
                '$목록 >> [table:each]{keep:["url"],parallel:' + str(parallel)
                + '} { [sense:crawl]{url:"$it.url"} }')
        result, final = run(code, source(truncated))
    assert result['success'] and final['error_count'] == 0 and final['ok_count'] == 2
    assert len(final['items']) == 2 and final['items'][0]['url'] == URL
    assert bool(result.get('truncated')) is truncated
    if truncated:
        row = final['row_honesty'][0]
        assert row['row'] == 1 and row['label'] == URL
        assert row['markers']['truncations'] == [CUT]
        assert truncation_evidence(result)['truncations'] == [CUT]
    else:
        assert not final.get('row_honesty')


def test_nested_partial_failure_counts_keep_their_units():
    payload = {'success': True, 'items': [{'text': '부분 결과'}],
               'error_count': 2, 'errors': [{'url': 'b', '_error': '실패'}]}
    _, final = run('$목록=[{url:"' + URL + '"}]; [fn:주소마다읽기]{목록:$목록,개수:1}', payload)
    assert final['error_count'] == 0 and final['ok_count'] == 1
    assert final['row_honesty'][0]['markers']['error_count'] == 2


def test_empty_each_preserves_incomplete_input():
    payload = source()
    payload['items'] = []
    _, final = run('[sense:crawl]{url:"' + URL + '"} >> [table:each] { [sense:crawl]{url:"$it.url"} }', payload)
    assert final['items'] == [] and final['rows_processed'] == 0
    assert final['truncated'] and final['row_honesty'][0]['scope'] == 'input'


def test_projection_and_summarized_intermediate_result_keep_evidence():
    from ibl_envelope import diet_envelope
    code = ('$목록=[{url:"' + URL + '"}]; '
            '$자료=[fn:주소마다읽기]{목록:$목록,개수:1} >> [table:select]{columns:["text","url"]}; '
            '[table:take]{items:[{done:true}],n:1}')
    result, final = run(code)
    assert final['items'] == [{'done': True}]
    compact = diet_envelope(result)
    assert truncation_evidence(compact)['truncations'] == [CUT]


def test_crawl_preserves_complete_source_with_small_display_budget(monkeypatch, tmp_path):
    from common import spill
    monkeypatch.setattr(spill, "_root", lambda: str(tmp_path))
    crawler = load('_ep3286_crawler', ROOT / 'data/packages/installed/tools/web/tool_webcrawl.py')
    calls = []
    def fetch(url, max_length):
        calls.append(max_length)
        text, length, truncated = crawler._truncate('a' * 23218, max_length)
        return dict(success=True, url=url, text=text, length=length, truncated=truncated)
    monkeypatch.setattr(crawler, '_crawl_website_impl', fetch)
    first = crawler.crawl_website(URL)
    full = crawler.crawl_website(URL, max_length=23218)
    assert calls == [None] and full['cache']['hit']
    assert len(first['text']) == len(full['text']) == 23218
    assert not first.get('truncated') and not first.get('truncations')
    assert json.loads(Path(first['source_ref']['path']).read_text())['text'] == full['text']


def test_sample_and_preview_do_not_become_source_truncation():
    from types import SimpleNamespace
    dataops = load('_ep3286_dataops', ROOT / 'data/packages/installed/tools/data-ops/handler.py')
    selected = dataops.execute({'_prev_result': {'items': [{'x': 1}, {'x': 2}], 'total': 2}, 'n': 1},
                               SimpleNamespace(tool_name='data_take'))
    assert truncation_evidence(selected)['truncations'] == [
        {'scope': 'selection', 'unit': 'rows', 'retained': 1, 'total': 2}]
    assert truncation_evidence({'_preview': {'shown': 8}, 'items': [{'truncated': True}]}) == {'preview': True}
    assert truncation_evidence({'truncated': True}) == {'truncations': [{'scope': 'unknown'}]}


def test_mcp_evidence_and_evaluator_header_survive_excerpt_budget():
    from cognitive_trace import serialize_tool_trace
    envelope = {'success': True, 'final_result': json.dumps(source()), 'results': []}
    blocks = [{'type': 'text', 'text': json.dumps(envelope)}]
    assert truncation_evidence(blocks)['truncations'] == [CUT]
    trace = serialize_tool_trace([{'name': 'execute_ibl', 'result': json.dumps(envelope)}], total_budget=1)
    assert '[절단 증거 1건: source;' in trace


def test_parallel_provenance_survives_spilled_branch_payload():
    envelope = {'success': True, 'results': [], 'final_result': {'items': []},
                'branches_honesty': [{'step': 1, 'branches': [
                    {'branch': 2, 'markers': {'truncated': True, 'truncations': [CUT]}}]}]}
    assert truncation_evidence(envelope)['truncations'] == [CUT]


def test_unresolved_source_never_reaches_distiller_or_training(monkeypatch, tmp_path):
    rag, stored, asked, runs = _arm(monkeypatch, tmp_path, [])
    code = '[sense:crawl]{url:"' + URL + '"} >> [table:take]{n:60}'
    call = {'tool_name': 'execute_ibl', 'input': {'code': code}, 'success': True,
            'evidence': {'truncations': [CUT]}}
    assert not rag.distill_experience('전체 조사', [call], 0.0)
    assert not stored and not asked and not runs


def test_repaired_call_is_learned_instead_of_earlier_cut(monkeypatch, tmp_path):
    old = '[sense:crawl]{url:"' + URL + '"}'
    fixed = '[sense:crawl]{url:"' + URL + '",max_length:23218}'
    rag, stored, asked, _ = _arm(monkeypatch, tmp_path,
                                [{'intent': '문서 수집', 'code': fixed, 'topic': '시험'}])
    calls = [dict(tool_name='execute_ibl', input={'code': old}, success=True, result=source()),
             dict(tool_name='execute_ibl', input={'code': fixed}, success=True, result=source(False))]
    assert rag.distill_experience('문서 수집', calls, 0.0)
    assert stored[0]['ibl_code'] == fixed
    assert old not in asked[0]['prompt']


@pytest.mark.parametrize('evidence', [{'preview': True}, {'truncations': [{'scope': 'selection'}]},
                                     {'truncations': [{'scope': 'unknown'}]}])
def test_preview_and_sample_remain_learnable_with_scope(monkeypatch, tmp_path, evidence):
    code = '[table:take]{items:[{x:1},{x:2}],n:1}'
    rag, stored, asked, _ = _arm(monkeypatch, tmp_path,
                                [{'intent': '앞 한 행 표본', 'code': code, 'topic': '시험'}])
    call = dict(tool_name='execute_ibl', input={'code': code}, success=True, evidence=evidence)
    assert rag.distill_experience('앞 한 행', [call], 0.0) and stored
    if 'truncations' in evidence:
        assert '전량 수집·완전한 조사의 성공 용례로 일반화하지 말고' in asked[0]['prompt']


if __name__ == '__main__':
    raise SystemExit(pytest.main([__file__] + sys.argv[1:]))
