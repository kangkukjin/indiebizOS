"""63회차 수리 회귀 — 첨부 확장 본문이 FTS 질의로 들어가 멈추던 연구 실행, arXiv 불용어, 질문 요약 총수, versions 인자."""
import boot_paths  # noqa: F401
import importlib.util
import json
import pathlib
import time

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[1]


def test_fts_terms_are_bounded_and_deduplicated():
    import notebook_store
    long_query = ("retrieval augmented generation long context " * 20000)  # 약 90만 자
    terms = notebook_store._fts_terms(long_query)
    assert 0 < len(terms) <= notebook_store._FTS_MAX_TERMS
    assert len(set(terms)) == len(terms)
    assert notebook_store._fts_terms("") == []
    assert notebook_store._fts_terms("a b c") == []  # 2자 미만 제외


def test_search_chunks_truncates_long_query_and_reports(tmp_path, monkeypatch):
    import notebook_store
    monkeypatch.setattr(notebook_store, 'get_notebook', lambda name: {'id': 1, 'name': name})
    monkeypatch.setattr(notebook_store, 'semantic_available', lambda: False)
    seen = {}

    def fake_fts(nb_id, query, over, **filters):
        seen['query'] = query
        return []
    monkeypatch.setattr(notebook_store, '_search_semantic', lambda *a, **k: [])
    monkeypatch.setattr(notebook_store, '_search_fts', fake_fts)
    out = notebook_store.search_chunks('nb', 'x' * 100000, alpha=0)
    assert out['success'] and out['query_truncated'] is True
    assert len(seen['query']) == notebook_store._QUERY_MAX_CHARS
    out = notebook_store.search_chunks('nb', '짧은 질문', alpha=0)
    assert out['query_truncated'] is False


def test_research_stream_searches_with_original_message_not_expanded(tmp_path, monkeypatch):
    """첨부 8편을 펼친 본문(수십만 자)이 아니라 사용자 원문이 배경 검색 질의다."""
    import research_runner
    from research_store import ResearchStore
    store = ResearchStore(tmp_path, 'stall-test')
    tid = store.create_thread('첨부 정지 재현')['id']
    run, fresh = store.begin_run(tid, '첨부 보존', 'req-1', [])
    assert fresh
    queries = []
    monkeypatch.setattr(research_runner, '_search', lambda s, q: queries.append(q) or {'items': []})
    monkeypatch.setattr(research_runner, 'attachment_input', lambda s, t, r, m: (m + '\n<attachment>' + ('본문 ' * 50000) + '</attachment>', []))
    received = {}

    def init(runner):
        runner.ai = type('AI', (), {'_provider': None, 'agent_id': ''})()

    def cognitive(runner, message, history, **kwargs):
        received['message'] = message
        yield {'type': 'final', 'content': '끝'}
    monkeypatch.setattr(research_runner.ResearchRunner, '_init_ai', init)
    monkeypatch.setattr(research_runner.ResearchRunner, 'cognitive_stream', cognitive)
    import threading
    events = list(research_runner.stream(store, tid, run, '첨부 보존', threading.Event()))
    assert queries == ['첨부 보존']                      # 검색 질의는 원문
    assert len(received['message']) > 100000              # 모델 입력은 펼친 본문
    assert events[-1]['type'] == 'final'


def test_research_stream_honours_cancel_before_model(tmp_path, monkeypatch):
    import research_runner
    from research_store import ResearchStore
    store = ResearchStore(tmp_path, 'cancel-test')
    tid = store.create_thread('취소')['id']
    run, _ = store.begin_run(tid, '질문', 'req-2', [])
    monkeypatch.setattr(research_runner, '_search', None)
    monkeypatch.setattr(research_runner.ResearchRunner, '_init_ai', lambda runner: setattr(runner, 'ai', type('AI', (), {'_provider': None, 'agent_id': ''})()))
    called = []
    monkeypatch.setattr(research_runner.ResearchRunner, 'cognitive_stream', lambda *a, **k: called.append(1) or iter(()))
    import threading
    cancel = threading.Event(); cancel.set()
    events = list(research_runner.stream(store, tid, run, '질문', cancel))
    assert called == [] and events and events[-1]['type'] == 'error'


def test_question_context_reports_total_counts(tmp_path):
    from research_store import ResearchStore
    from research_questions import ResearchQuestions
    store = ResearchStore(tmp_path, 'count-test')
    tid = store.create_thread('총수')['id']
    q = ResearchQuestions(store, tid)
    q.apply([{'expected_revision': 0, 'text': '질문?', 'gaps': ['a', 'b', 'c', 'd', 'e'], 'next_probes': ['1', '2', '3', '4']}], origin='user', run=None)
    ctx = q.context()
    item = ctx['items'][0]
    assert len(item['gaps']) == 3 and item['gaps_total'] == 5
    assert len(item['next_probes']) == 3 and item['next_probes_total'] == 4


def test_notebook_versions_requires_source_ref(tmp_path, monkeypatch):
    import research_threads as service
    from research_store import ResearchStore
    store = ResearchStore(tmp_path, 'versions-test')
    tid = store.create_thread('판본')['id']
    monkeypatch.setattr(service, 'resolve', lambda ref: ({'project_uid': store.uid}, store))
    with pytest.raises(ValueError, match='source_ref'):
        service.notebook_operation({'op': 'versions', 'project_ref': store.uid, 'thread_ref': tid})


def _study_handler():
    path = ROOT / 'data/packages/installed/tools/study/handler.py'
    spec = importlib.util.spec_from_file_location('study_handler_r63', path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_arxiv_expression_drops_stopwords_and_punctuation():
    mod = _study_handler()
    expr = mod._arxiv_search_expression("Lost in the Middle: How Language Models Use Long Contexts")
    assert 'all:the' not in expr and 'all:in' not in expr and 'all:Middle:' not in expr
    assert expr == 'all:Lost AND all:Middle AND all:Language AND all:Models AND all:Use AND all:Long AND all:Contexts'
    assert mod._arxiv_search_expression('ti:"attention is all you need"') == '(ti:"attention is all you need")'
    assert mod._arxiv_search_expression('"long context" RAG') == 'all:"long context" AND all:RAG'
    assert mod._arxiv_search_expression('the of') == 'all:the AND all:of'   # 전부 불용어면 원문 유지


if __name__ == '__main__':
    import sys
    raise SystemExit(pytest.main([__file__, *sys.argv[1:]]))
