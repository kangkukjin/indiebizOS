"""ep3286: 원천 절단의 each/fn 경계·복구 안내·평가/학습 전달 회귀."""
import json
import re
import sys
from pathlib import Path

import boot_paths  # noqa: F401
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
from test_report_repair_contracts_2026_09_08 import load
from ibl_honesty import truncation_evidence
from test_distill_source_recovery_2026_09_09 import _arm, completed_call

URL = 'https://fixture.test/a'
CUT = {'scope': 'source', 'source': URL, 'unit': 'characters',
       'retained': 10000, 'total': 23218,
       'retry': {'url': URL, 'max_length': 23218}}


def source(truncated=True):
    out = {'success': True, 'items': [{'text': '원문'}], 'truncated': truncated}
    if truncated:
        out['truncations'] = [CUT]
    return out












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
    from ibl_v2_adapters import Adapter, load_registry, decode_envelope
    from ibl_v2_compile import compile_program
    from ibl_v2_runtime import Runtime
    registry = load_registry(str(ROOT))
    contract = registry['sense:crawl'].contract
    registry['sense:crawl'] = Adapter(contract, lambda rt, args: decode_envelope(source(), contract['adapter']))
    envelope = Runtime(compile_program('[sense:crawl]{url:"https://fixture.test/a"}', registry)).run()
    assert envelope['success'] is False and envelope['diagnostic']['code'] == 'PARTIAL_SOURCE'
    blocks = [{'type': 'text', 'text': json.dumps(envelope)}]
    assert truncation_evidence(blocks)['truncations'] == [CUT]
    trace = serialize_tool_trace([{'name': 'execute_ibl', 'result': json.dumps(envelope)}], total_budget=1)
    assert '[절단 증거 1건: source;' in trace



def test_business_truncation_fields_do_not_become_execution_evidence():
    assert truncation_evidence({'edition': 2, 'success': True, 'value': source()}) == {}


def test_parallel_provenance_survives_spilled_branch_payload():
    envelope = {'success': True, 'items': [],
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
    old = '#!ibl edition=2\n[sense:crawl]{url:"' + URL + '"}'
    fixed = '#!ibl edition=2\n[sense:crawl]{url:"' + URL + '",max_length:23218}'
    rag, stored, asked, _ = _arm(monkeypatch, tmp_path,
                                [{'intent': '문서 수집', 'source_ids': [1], 'topic': '시험'}])
    calls = [completed_call(old), completed_call(fixed)]
    calls[0]['result'].update(source())
    calls[0]['result']['source_complete'] = False
    calls[1]['result'].update(source(False))

    assert rag.distill_experience('문서 수집', calls, 0.0)
    assert stored[0]['ibl_code'] == fixed
    assert old not in asked[0]['prompt']


@pytest.mark.parametrize('evidence', [{'preview': True}, {'truncations': [{'scope': 'selection'}]},
                                     {'truncations': [{'scope': 'unknown'}]}])
def test_preview_and_sample_remain_learnable_with_scope(monkeypatch, tmp_path, evidence):
    code = '#!ibl edition=2\n[table:take]{items:[{x:1},{x:2}],n:1}'
    rag, stored, asked, _ = _arm(monkeypatch, tmp_path,
                                [{'intent': '앞 한 행 표본', 'source_ids': [1], 'topic': '시험'}])
    call = completed_call(code)
    call['evidence'] = evidence
    assert rag.distill_experience('앞 한 행', [call], 0.0) and stored
    if 'truncations' in evidence:
        assert '전량 수집·완전한 조사의 성공 용례로 일반화하지 말고' in asked[0]['prompt']


if __name__ == '__main__':
    raise SystemExit(pytest.main([__file__] + sys.argv[1:]))
