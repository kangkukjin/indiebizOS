"""단순한 보고서 흐름의 실제 IBL 실행·저장·재개. 외부 AI/YouTube만 고정 응답으로 대체한다."""
import copy
import importlib.util
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))
import boot_paths  # noqa: E402,F401
import pytest

spec = importlib.util.spec_from_file_location("tips_helper", ROOT / "data/scripts/ai_tips_report.py")
helper = importlib.util.module_from_spec(spec)
spec.loader.exec_module(helper)
BODY = (ROOT / "data/idioms/ai_tips_report.ibl").read_text()
IDS = ("aaaaaaaaaaa", "bbbbbbbbbbb")
QUOTES = ("Before changing files, save a checkpoint and review the diff.",
          "Retry only the failed step; do not repeat a successful payment.")
TITLES = ("수정 전 체크포인트와 차이를 확인한다", "실패 단계만 재시도한다")


def fixture_ai(item):
    source = item["input"]
    kind = source["kind"]
    if kind == "queries":
        return {"queries": ["한국어 팁", "AI tutorial"]}
    if kind == "select":
        return {"selected": [v["video_id"] for v in source["videos"]]}
    if kind == "extract":
        n = IDS.index(source["video"]["video_id"])
        return {"tips": [{"tip": TITLES[n], "how": QUOTES[n], "caveat": "직접 재현하지 않음"}]}
    if kind == "compose":
        return {"summary": "안전하게 복구하는 방법", "tips": [
            {**t, "implication": "복구 작업에서 적용 여부를 선택한다"} for t in source["tips"]],
            "next_topic": "문서"}
    raise AssertionError(kind)


@pytest.fixture
def execute(tmp_path, monkeypatch):
    import ibl_engine
    import ibl_v2_store
    import ibl_v2_compat
    import ibl_v2_learning
    import ibl_run_journal
    from ibl_v2_entry import handle_request
    from common import spill
    monkeypatch.setattr(ibl_v2_store, 'definitions', lambda: {'AI팁보고서쓰기': BODY})
    monkeypatch.setattr(ibl_v2_compat, 'legacy_functions', lambda: {})
    monkeypatch.setattr(ibl_v2_learning, 'record_functions', lambda *a: None)
    monkeypatch.setattr(ibl_run_journal, 'journal_root', lambda *a: tmp_path / 'journal')
    monkeypatch.setattr(helper.delivery, 'ROOT', tmp_path)
    monkeypatch.setattr(helper.delivery.renderer, '_ROOT', tmp_path)
    calls, stages = [], {}
    model_calls, ai_inputs = [], []
    transcripts, ai_hooks = {}, []
    metadata_overrides, metadata_responses = {}, {}
    search_calls, search_responses = [], {}
    corrupt = {}
    monkeypatch.setattr(spill, "_root", lambda: str(tmp_path / "spill"))
    original = ibl_engine._execute_ibl_impl
    def leaf(ti, project, agent_id=None):
        # Test doubles must retain the real dispatcher depth guard.
        if (ti.get("_depth") or 0) > ibl_engine.MAX_NEST_DEPTH:
            return original(ti, project, agent_id)
        node, act = ti.get("_node"), ti.get("action")
        p = dict(ti.get("params") or {})
        if node == "self" and act == "script":
            args = p["args"]
            assert p["_ibl_edition"] == 2
            stage = args["op"]
            if stage in corrupt:
                args = corrupt[stage](copy.deepcopy(args))
            stages[stage] = copy.deepcopy(args)
            try:
                out = helper.run(args)
            except Exception as exc:
                out = {"success": False, "error": str(exc)}
            return out if out.get("success") is False else {"success": True, "value": out}
        if node == "sense" and act == "search_youtube":
            query = p["query"]
            search_calls.append(query)
            override = search_responses.get(query)
            if override is not None:
                return override(search_calls.count(query)) if callable(override) else copy.deepcopy(override)
            return {"success": True, "items": [{"video_id": vid} for vid in IDS]}
        if node == "sense" and act == "video":
            vid = p["video_id"]
            calls.append((p["op"], vid))
            if p["op"] == "info":
                if vid in metadata_responses:
                    return copy.deepcopy(metadata_responses[vid])
                return {"success": True, "items": [{"video_id": vid, "title": "Fixture " + vid,
                        "uploader": "Fixture Channel", "duration": 240, "upload_date": "2026-09-01", **metadata_overrides.get(vid, {})}]}
            if vid in transcripts:
                return copy.deepcopy(transcripts[vid])
            return {"success": True, "items": [{"start": 0.0, "duration": 8.0,
                                               "text": QUOTES[IDS.index(vid)]}]}
        if node == "table" and act == "ai":
            source = p.get("_prev_result") if "_prev_result" in p else p.get("items")
            inputs = helper.rows(source)
            ai_inputs.extend(copy.deepcopy(inputs))
            if inputs:
                model_calls.append(("ai", len(inputs)))
            for hook in ai_hooks:
                override = hook(inputs)
                if override is not None:
                    return override
            return {"success": True, "items": [{**r, "result": fixture_ai(r)} for r in inputs],
                    "rows_in": len(inputs), "rows_out": len(inputs)}
        return original(ti, project, agent_id)
    monkeypatch.setattr(ibl_engine, "_execute_ibl_impl", leaf)
    monkeypatch.setattr(ibl_engine, "execute_ibl", leaf)
    def run(mode="draft", named=True, topic="복구", config_override=None):
        config = {"root": str(tmp_path / "reports"), "date": "2026-09-24", "topic": topic,
                  "mode": mode, "run_id": "test", "share_root": str(tmp_path / "공유창고/0/AI 팁들")}
        if config_override is not None:
            config = config_override
        code = "[fn:AI팁보고서쓰기]{설정:$config}"
        return handle_request({'edition': 2, 'code': code, 'inputs': {'config': config}}, str(tmp_path))
    run.stages, run.calls, run.corrupt = stages, calls, corrupt
    run.root = tmp_path / "reports"
    run.model_calls, run.ai_inputs = model_calls, ai_inputs
    run.transcripts, run.ai_hooks = transcripts, ai_hooks
    run.metadata_overrides, run.metadata_responses = metadata_overrides, metadata_responses
    run.search_calls, run.search_responses = search_calls, search_responses
    return run


def final(result):
    assert result["success"], str(result.get("error") or result.get("traceback") or result)[-3000:]
    return result["value"]

def test_named_commit_and_resume_do_not_repeat_work(execute):
    out = final(execute('commit'))
    assert out['status'] == 'completed' and out['new_tips'] == 2
    report = Path(out['report']).read_text()
    assert all('watch?v=' + vid in report for vid in IDS)
    tips = helper.load_json(execute.root / 'db/tips.json')
    assert len(tips) == 2 and all('_quote' not in t for t in tips)
    assert len(execute.model_calls) == 5
    counts = (len(execute.calls), len(execute.model_calls), len(execute.search_calls))
    assert final(execute('commit')) == out
    assert counts == (len(execute.calls), len(execute.model_calls), len(execute.search_calls))


def test_draft_does_not_write_ledgers(execute):
    out = final(execute())
    assert out['status'] == 'draft' and Path(out['report']).is_file()
    assert not (execute.root / 'db/tips.json').exists()
    assert not (execute.root / '_covered_videos.json').exists()


def test_one_failed_search_uses_other_results(execute):
    execute.search_responses['한국어 팁'] = {'success': False, 'error': 'timeout'}
    out = final(execute())
    assert '검색 일부 실패' in Path(out['report']).read_text()
    assert len(execute.search_calls) == 2


def test_all_empty_searches_do_not_invent_report(execute):
    execute.search_responses.update({q: {'success': True, 'items': []} for q in ('한국어 팁', 'AI tutorial')})
    assert not execute('commit')['success']
    assert not (execute.root / 'db/tips.json').exists()


@pytest.mark.parametrize('date', ['2020-01-01', '2026-10-01', 'unknown'])
def test_nonrecent_or_unknown_dates_are_excluded(execute, date):
    execute.metadata_overrides[IDS[0]] = {'upload_date': date}
    out = final(execute())
    assert out['new_tips'] == 1
    assert ('transcript', IDS[0]) not in execute.calls


def test_covered_video_is_skipped_before_metadata(execute):
    helper.atomic(execute.root / '_covered_videos.json', {'covered': [{'id': IDS[0], 'verdict': 'no_tips'}]})
    assert final(execute())['new_tips'] == 1
    assert ('info', IDS[0]) not in execute.calls


def test_missing_transcript_does_not_cover_failed_video(execute):
    execute.transcripts[IDS[0]] = {'success': False, 'error': 'no captions'}
    out = final(execute('commit'))
    assert out['new_tips'] == 1 and '자막을 읽지 못한 영상' in Path(out['report']).read_text()
    assert [v['id'] for v in helper.load_json(execute.root / '_covered_videos.json')['covered']] == [IDS[1]]


def test_no_transcripts_stops_without_writes(execute):
    execute.transcripts.update({vid: {'success': False, 'error': 'no captions'} for vid in IDS})
    assert not execute('commit')['success']
    assert not (execute.root / 'db/tips.json').exists()


def test_plain_transcript_needs_no_timestamps(execute):
    execute.transcripts[IDS[0]] = {'success': True, 'transcript': QUOTES[0]}
    assert final(execute())['new_tips'] == 2


def test_long_transcript_tail_is_read_once_in_order(execute):
    text = 'A' * (helper.CHUNK_CHARS * 2 + 20) + 'TAIL_METHOD'
    execute.transcripts[IDS[0]] = {'success': True, 'transcript': text}
    final(execute())
    inputs = [r['input'] for r in execute.ai_inputs if r['input']['kind'] == 'extract'
              and r['input']['video']['video_id'] == IDS[0]]
    assert sorted(r['part'] for r in inputs) == [1, 2, 3]
    assert 'TAIL_METHOD' in next(r for r in inputs if r['part'] == 3)['transcript']
    assert len(execute.model_calls) == 7


def test_failed_extraction_keeps_other_tips_and_can_revisit_video(execute):
    execute.ai_hooks.append(lambda inputs: {'success': False, 'error': 'timeout'} if inputs and
        inputs[0]['input']['kind'] == 'extract' and inputs[0]['video_id'] == IDS[0] else None)
    out = final(execute('commit'))
    assert out['new_tips'] == 1 and '팁 추출에 실패한 자막 구간' in Path(out['report']).read_text()
    covered = helper.load_json(execute.root / '_covered_videos.json')['covered']
    assert IDS[0] not in {v['id'] for v in covered}


def test_no_extracted_tips_stops_without_writes(execute):
    execute.ai_hooks.append(lambda inputs: {'success': True, 'items': [
        {**r, 'result': {'tips': []}} for r in inputs]} if inputs and inputs[0]['input']['kind'] == 'extract' else None)
    assert not execute('commit')['success']
    assert not (execute.root / 'db/tips.json').exists()


def test_failed_compose_resumes_without_search_or_extraction(execute):
    execute.ai_hooks.append(lambda inputs: {'success': False, 'error': 'timeout'} if inputs and
        inputs[0]['input']['kind'] == 'compose' else None)
    assert not execute('commit')['success']
    before = (len(execute.calls), len(execute.search_calls), len(execute.model_calls))
    execute.ai_hooks.clear()
    assert final(execute('commit'))['new_tips'] == 2
    assert (len(execute.calls), len(execute.search_calls)) == before[:2]
    assert len(execute.model_calls) == before[2] + 1


def test_fabricated_source_id_is_rejected(execute):
    def corrupt(args):
        args['data']['items'][0]['result']['tips'][0]['id'] = 'invented'
        return args
    execute.corrupt['finish'] = corrupt
    assert not execute('commit')['success']
    assert not (execute.root / 'db/tips.json').exists()


def test_concurrent_ledger_change_is_not_overwritten(execute):
    def corrupt(args):
        helper.atomic(execute.root / 'db/tips.json', [{'tip': 'other work'}])
        return args
    execute.corrupt['finish'] = corrupt
    assert not execute('commit')['success']
    assert helper.load_json(execute.root / 'db/tips.json') == [{'tip': 'other work'}]


def test_interrupted_storage_recovers_without_model_calls(execute, monkeypatch):
    atomic = helper.io.atomic
    crashed = []
    def interrupt(path, value, **kwargs):
        if path == execute.root / 'db/tips.json' and not crashed:
            crashed.append(True)
            raise OSError('simulated disk interruption')
        return atomic(path, value, **kwargs)
    monkeypatch.setattr(helper.io, 'atomic', interrupt)
    assert not execute('commit')['success']
    assert helper.load_json(execute.root / '_report_transaction.json').get('done') is not True
    count = len(execute.model_calls)
    out = final(execute('commit'))
    assert out['new_tips'] == 2 and len(execute.model_calls) == count
    assert len(helper.load_json(execute.root / 'db/tips.json')) == 2
    assert helper.load_json(execute.root / '_report_transaction.json')['done']


def test_old_run_is_preserved_and_rejected(execute):
    path = execute.root / '_runs/test/state.json'
    helper.atomic(path, {'version': 3, 'sentinel': 'keep'})
    assert not execute()['success']
    assert helper.load_json(path) == {'version': 3, 'sentinel': 'keep'}

@pytest.mark.parametrize('format', ['file', 'spill'])
def test_externalized_transcript_reads_full_body(execute, tmp_path, format):
    path = tmp_path / 'captions.json'
    helper.atomic(path, {'items': [{'text': QUOTES[0]}]})
    execute.transcripts[IDS[0]] = ({'success': True, 'items': [], 'saved_to_file': True,
        'file_path': str(path)} if format == 'file' else {'success': True, 'items': [],
        '_spilled': True, 'ref': {'path': str(path), 'kind': 'items'}})
    assert final(execute())['new_tips'] == 2
    requests = [r['input'] for r in execute.ai_inputs if r['input']['kind'] == 'extract']
    assert any(r['transcript'] == QUOTES[0] for r in requests)


def test_incomplete_transcript_is_not_silently_used(execute):
    execute.transcripts[IDS[0]] = {'success': True, 'items': [{'text': QUOTES[0]}], 'partial': True}
    out = final(execute('commit'))
    assert out['new_tips'] == 1 and '자막을 읽지 못한 영상' in Path(out['report']).read_text()


def test_existing_report_is_not_overwritten(execute):
    path = execute.root / 'ai_tips_report_2026-09-24_복구.md'
    helper.atomic(path, 'earlier report', text=True)
    assert not execute('commit')['success']
    assert path.read_text() == 'earlier report'
    assert not (execute.root / 'db/tips.json').exists()


def test_named_result_has_native_optional_config_contract():
    from ibl_v2_parser import parse
    from ibl_v2_learning import check_source
    assert check_source(BODY, function_body=True) is None
    definition = parse(BODY).data['statements'][0]
    assert list(definition.data['params']) == ['설정']
    assert definition.data['params']['설정'] is not None


def test_used_video_is_covered_even_when_one_chunk_failed(execute):
    execute.transcripts[IDS[0]] = {'success': True, 'transcript': 'A' * (helper.CHUNK_CHARS + 100)}
    execute.ai_hooks.append(lambda inputs: {'success': False, 'error': 'timeout'} if inputs and
        inputs[0].get('job_id') == IDS[0] + '-2' else None)
    out = final(execute('commit'))
    assert out['new_tips'] == 2 and out['videos'] == 2
    assert '팁 추출에 실패한 자막 구간 1개' in Path(out['report']).read_text()


def test_private_implication_stays_on_one_removable_line(execute):
    def corrupt(args):
        args['data']['items'][0]['result']['tips'][0]['implication'] = '개인 환경\n내부 적용 구상'
        return args
    execute.corrupt['finish'] = corrupt
    report = Path(final(execute())['report']).read_text()
    assert '개인 환경 내부 적용 구상' in report
    assert '\n내부 적용 구상' not in report


def test_handled_missing_video_returns_compact_success_at_real_v2_boundary(execute):
    execute.metadata_responses[IDS[0]] = {'success': False, 'error': 'This video is not available'}
    result = execute('commit')
    out = final(result)
    # 2026-09-25 언어 개정(91448265): catch로 처리한 외부 실패도 실행 봉투의
    # `source_complete:false` 근거로 남는다. 관용구는 완료(completed)로 값을 돌려주되
    # 빠진 영상을 limitations에 적고, 봉투는 원천 불완전을 감추지 않는다.
    assert result['success'] and out['status'] == 'completed'
    assert result['source_complete'] is False
    assert any('영상 정보를 확인하지 못해 제외' in str(x) for x in out['limitations'])
    assert out['new_tips'] == 1 and out['published']
    assert Path(out['shared_report']).is_file()
    assert '결과' not in out and 'results' not in out and 'final_result' not in out
    assert len(json.dumps(out, ensure_ascii=False)) < 2500
    from model_result_view import project_v2_result
    assert len(json.dumps(project_v2_result(result), ensure_ascii=False).encode()) < 6000
    assert '원천 결과가 불완전' not in json.dumps(result, ensure_ascii=False)
    assert 'This video is not available' not in Path(out['report']).read_text()
    assert any(e['kind'] == 'recovered' for e in result['evidence'])


def test_reader_context_reaches_queries_selection_and_extraction(execute):
    final(execute())
    for kind in ['queries', 'select', 'extract', 'compose']:
        inputs = [r['input'] for r in execute.ai_inputs if r['input']['kind'] == kind]
        assert inputs and all('AI 도구' in r['reader_context'] for r in inputs)


def test_shared_report_has_all_tips_and_no_private_context(execute):
    def private(args):
        result = args['data']['items'][0]['result']
        result['summary'] = 'PRIVATE_READER_CONTEXT 라는 독자 환경에 대한 요약'
        for tip in result['tips']:
            tip['implication'] = '편집자 해석: PRIVATE_READER_CONTEXT 적용 의견'
        return args
    execute.corrupt['finish'] = private
    out = final(execute('commit'))
    html = Path(out['shared_report']).read_text()
    assert 'PRIVATE_READER_CONTEXT' not in html and '우리 시스템 함의' not in html
    assert html.count('<h3>') == 2 and html.count('https://www.youtube.com/watch?v=') == 4
    assert '(편집자 해석): 편집자 해석:' not in Path(out['report']).read_text()


def test_default_call_needs_no_outside_preparation_and_reuses_same_run(execute, monkeypatch):
    import datetime
    from types import SimpleNamespace
    class Today:
        @staticmethod
        def today():
            return datetime.date(2026, 9, 24)
    monkeypatch.setattr(helper.delivery, 'dt', SimpleNamespace(date=Today))
    # Empty settings means ordinary report creation, including warehouse delivery.
    out = final(execute(config_override={}))
    assert out['status'] == 'completed' and out['topic'] == '코딩'
    assert Path(out['report']).is_file() and Path(out['shared_report']).is_file()
    before = (len(execute.calls), len(execute.model_calls))
    assert final(execute(config_override={})) == out
    assert before == (len(execute.calls), len(execute.model_calls))


def test_share_failure_resumes_only_delivery(execute, monkeypatch):
    render = helper.delivery.renderer.render
    def unavailable(args):
        raise OSError('shared disk unavailable')
    monkeypatch.setattr(helper.delivery.renderer, 'render', unavailable)
    assert not execute('commit')['success']
    assert len(helper.load_json(execute.root / 'db/tips.json')) == 2
    before = (len(execute.calls), len(execute.model_calls))
    monkeypatch.setattr(helper.delivery.renderer, 'render', render)
    out = final(execute('commit'))
    assert out['status'] == 'completed' and Path(out['shared_report']).exists()
    assert before == (len(execute.calls), len(execute.model_calls))
    assert len(helper.load_json(execute.root / 'db/tips.json')) == 2


def test_review_queue_gets_html_and_published_flag_remains_honest(execute, tmp_path, monkeypatch):
    from supervision_delivery import STAGING_ENV, DeliveryQueue
    queue = DeliveryQueue(tmp_path / 'review', tmp_path / '공유창고', lambda *a, **k: None)
    monkeypatch.setenv(STAGING_ENV, str(queue.directory))
    out = final(execute('commit'))
    assert out['status'] == 'publication_pending' and not out['published']
    assert not Path(out['shared_report']).exists() and Path(out['shared_preview']).exists()
    manifest = queue.manifest()
    queue.deliver(manifest['hash'])
    before = len(execute.model_calls)
    published = final(execute('commit'))
    assert published['published'] and published['status'] == 'completed'
    assert len(execute.model_calls) == before


def test_existing_different_shared_report_is_not_overwritten(execute, tmp_path):
    shared = tmp_path / '공유창고/0/AI 팁들/AI 팁 보고서 2026-09-24 복구.html'
    helper.atomic(shared, 'another report', text=True)
    assert not execute('commit')['success']
    assert shared.read_text() == 'another report'


def test_default_topic_uses_previous_issue_and_ignores_same_day(execute):
    root = helper.delivery.ROOT / 'outputs/ai_tips_reports'
    helper.atomic(root / '_covered_videos.json', {'covered': [], 'recent_topics': [
        {'date': '2026-09-23', 'topic': '코딩'}, {'date': '2026-09-24', 'topic': '문서'}]})
    helper.atomic(root / 'ai_tips_report_2026-09-23_코딩.md', '## 다음 주제 후보\n\n평가\n', text=True)
    helper.atomic(root / 'ai_tips_report_2026-09-24_문서.md', '## 다음 주제 후보\n\n다른 주제\n', text=True)
    config = helper.delivery.settings({'date': '2026-09-24'})
    assert config['topic'] == '평가' and config['run_id'] == '2026-09-24-auto-v5'
