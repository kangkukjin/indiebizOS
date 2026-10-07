"""Chunk source parity, boundary preservation, and bounded packing work."""
import boot_paths  # noqa: F401
import cProfile
import importlib.util
import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(scope='module')
def chunk():
    path = ROOT / 'data/packages/installed/tools/data-ops/chunk_ops.py'
    spec = importlib.util.spec_from_file_location('chunk_contract', path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module._op_chunk


@pytest.mark.parametrize('text', ['', ' \t\n  ', 'a b\n'])
@pytest.mark.parametrize('entry', ['explicit', 'record', 'field'])
def test_source_forms_keep_empty_and_whitespace(chunk, text, entry):
    params = {'size': 4, 'overlap': 1, 'by': 'chars'}
    expected = chunk(text, params)
    if entry == 'explicit':
        actual = chunk('MUST NOT USE FALLBACK', {**params, 'text': text})
    elif entry == 'record':
        actual = chunk({'text': text}, params)
    else:
        actual = chunk({'body': text, 'items': [{'text': 'MUST NOT USE ROWS'}]},
                       {**params, 'field': 'body'})
    assert actual['success'], actual
    assert actual['items'] == expected['items']
    assert actual['source_chars'] == len(text)


def test_rows_still_precede_envelope_message_and_report_missing_text(chunk):
    result = chunk({'message': 'not content', 'items': [{'text': 'a'}, {'text': ''}, {}]},
                   {'by': 'chars', 'size': 8})
    assert result['by'] == 'rows'
    assert result['items'][0]['text'] == 'a'
    assert result['skipped_row_indices'] == [1, 2]
    assert not chunk({'other': 1}, {'field': 'missing'})['success']


@pytest.mark.parametrize('by,separator', [('line', '\n'), ('paragraph', '\n\n')])
def test_many_small_segments_pack_without_rejoining_prefixes(chunk, by, separator):
    parts = ['ab'] * 6000
    text = separator.join(parts)
    profile = cProfile.Profile()
    profile.enable()
    result = chunk(text, {'by': by, 'size': 20000})
    profile.disable()
    assert separator.join(item['text'] for item in result['items']) == text
    assert all(item['chars'] <= 20000 for item in result['items'])
    # Deterministic work bound; avoid wall-clock thresholds on shared machines.
    # chunk_ops 자신이 부른 join 만 센다 — 전체 join 수는 같은 스레드에서 그사이 돈 바깥 코드(긴 xdist 워커의
    # 가비지 종료자 등)까지 세어 1묶음에 3회로 보인 적이 있다(2026-10-07 전수 1건, 단독 재실행은 통과).
    own = chunk.__code__.co_filename
    joins = sum(sub.callcount for entry in profile.getstats()
                if not isinstance(entry.code, str) and entry.code.co_filename == own
                for sub in (entry.calls or [])
                if isinstance(sub.code, str) and "'join' of 'str'" in sub.code)
    assert 1 <= joins <= len(result['items']) + 1, joins


@pytest.mark.parametrize('by,separator', [('line', '\n'), ('paragraph', '\n\n')])
def test_buffer_length_resets_after_overlong_segment(chunk, by, separator):
    text = separator.join(['a', 'abcdefghijk', 'b', 'cc', 'd'])
    result = chunk(text, {'by': by, 'size': 6})
    assert [(row['text'], row['start']) for row in result['items']] == (
        [('a', 0), ('abcdef', 1), ('ghijk', 1), ('b\ncc\nd', 2)] if by == 'line' else
        [('a', 0), ('abcdef', 1), ('ghijk', 1), ('b\n\ncc', 2), ('d', 4)])


@pytest.mark.parametrize('record', [False, True])
def test_full_document_index_with_empty_sources(tmp_path, record):
    from ibl_v2_adapters import load_registry
    from ibl_v2_compile import compile_program
    from ibl_v2_runtime import Runtime
    from thread_context import actor_context
    fixture = ROOT / 'docs/experiments/long_sentence_imagination/round_21'
    source = fixture / 'drafts' / ('index_record_v0.ibl' if record else 'index_v0.ibl')
    documents = [{'id': 'A', 'text': '  가나다\n' * 120}, {'id': 'E', 'text': ''},
                 {'id': 'W', 'text': ' \t\n  '}]
    inputs = {'prepared': {'documents': documents, 'queries': ['가나다', '없는말']},
              'size': 512, 'overlap': 64, 'out': str(tmp_path / 'index')}
    plan = compile_program(source.read_text(), load_registry(str(ROOT)), inputs)
    assert not plan.issues, plan.issues
    with actor_context(origin='training'):
        result = Runtime(plan, inputs).run()
    assert result['success'], result.get('diagnostic')
    assert result['value']['report']['verified']
    assert result['value']['index_verified'] and result['value']['report_verified']
    index = json.loads((tmp_path / 'index/index.json').read_text())
    for doc in documents:
        chunks = [row for row in index['chunks'] if row['doc_id'] == doc['id']]
        assert ''.join(row['text'][64 if i else 0:] for i, row in enumerate(chunks)) == doc['text']


if __name__ == '__main__':
    import sys
    raise SystemExit(pytest.main([__file__, *sys.argv[1:]]))
