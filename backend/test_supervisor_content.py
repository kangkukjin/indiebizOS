"""실제 셸·스크립트 반환 파일을 본문 검수에 연결하는 계약."""
import hashlib
import json
import subprocess
import sys

import pytest
import boot_paths  # noqa: F401
from final_evaluator import prepare, snapshot_error, invoke
from supervisor_content import discover
from test_conscious_supervisor import supervisor  # noqa: F401


def receipt(path):
    return {"path": str(path), "bytes": path.stat().st_size,
            "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}


def test_native_file_change_reaches_first_review_and_recovery(supervisor, tmp_path, monkeypatch):
    from providers.codex import CodexProvider
    from evaluation_input import evidence_references, recover
    from test_evaluation_input import provider

    report = tmp_path / '최종 보고서.md'
    report.write_text('## 판단\n실제 보고서 본문과 미확인 범위\n', encoding='utf-8')
    source = tmp_path / 'source.json'
    source.write_text(json.dumps({'text': '수집 원문\n' * 40000}))
    supervisor.run_tool('shell', {}, lambda: json.dumps(receipt(source)))
    native = CodexProvider(api_key='', model='fake', system_prompt='', tools=[])
    native._reset_turn_state()
    # Codex의 짧은 편집은 item.started 없이 완료 사건만 도착한다.
    events = native._translate_stream_event({'type': 'item.completed', 'item': {
        'id': 'patch-1', 'type': 'file_change', 'status': 'completed',
        'changes': [{'path': report.name, 'kind': 'add'}],
    }}, '', 0)
    for event, _ in events:
        if event['type'] == 'tool_start':
            call = supervisor._start(event['name'], event['input'])
        elif event['type'] == 'tool_result':
            supervisor._finish(call, event['result'], error=event['is_error'])
    supervisor.store.put_response(f'[상세 보고서]({report})')
    packet = prepare(supervisor)
    rows = {a['subject']: a for a in packet['attachments']}
    assert rows[str(report)]['text'] == report.read_text()
    assert rows[str(report)]['role'] == 'submission'
    assert rows[str(source)]['role'] == 'support'
    ref = next(r for r in evidence_references(packet)
               if r['evidence_id'] == rows[str(report)]['source_ref'])
    assert ref['recoverable'] and ref['total'] == len(report.read_text())
    recovered = recover(supervisor, [{'criterion_id': 'C1', 'evidence_id': ref['evidence_id'],
                                     'revision': ref['revision'], 'start': 0, 'end': ref['total']}])
    assert recovered[0]['text'] == report.read_text()
    observed = []

    def evaluate(prompt, **kwargs):
        text = prompt.prepare_request(provider(request_limits={'chars': 200000}))
        observed.append(text)
        assert report.read_text() in text
        return 'ACHIEVED'

    monkeypatch.setattr('consciousness_agent.system_ai_call', evaluate)
    assert json.loads(invoke(supervisor))['status'] == 'APPROVED'
    assert len(observed) == 1
    assert snapshot_error(supervisor) is None
    report.write_text('평가 후 변경')
    assert snapshot_error(supervisor)


@pytest.mark.parametrize('status,kind,declined,expected', [
    ('completed', 'add', False, True),
    ('completed', 'update', False, True),
    ('completed', 'delete', False, False),
    ('in_progress', 'add', False, False),
    ('failed', 'add', False, False),
    ('interrupted', 'update', False, False),
    ('completed', 'add', True, False),
])
def test_native_change_receipts_require_completed_writes(
        supervisor, tmp_path, status, kind, declined, expected):
    from providers.codex import CodexProvider
    path = tmp_path / 'existing.md'
    path.write_text('이전 파일이 존재해도 실패·삭제를 산출물로 바꾸지 않는다')
    item = {'type': 'file_change', 'status': status, 'declined': declined,
            'changes': [{'path': str(path), 'kind': kind}]}
    result, error = CodexProvider._tool_result(item)
    found = discover(supervisor, f'[링크]({path})', [{
        'name': 'apply_patch', 'input': {'changes': item['changes']},
        'result': result, 'is_error': error}])
    assert bool(found) is expected


def test_native_multi_file_edit_preserves_receipts_without_promoting_deleted_files(supervisor, tmp_path):
    from providers.codex import CodexProvider
    paths = [tmp_path / name for name in ('new.md', 'updated.md', 'removed.md')]
    for path in paths:
        path.write_text(path.name)
    item = {'type': 'file_change', 'status': 'completed', 'changes': [
        {'path': str(path), 'kind': kind}
        for path, kind in zip(paths, ('add', 'update', 'delete'))]}
    result, error = CodexProvider._tool_result(item)
    assert json.loads(result)['changes'] == item['changes']
    found = discover(supervisor, '', [{'name': 'apply_patch', 'result': result, 'is_error': error}])
    assert {a['path'] for a in found} == {str(p) for p in paths[:2]}


@pytest.mark.parametrize('envelope', [
    lambda p: {'artifacts': [{'output_path': str(p)}]},
    lambda p: {'artifact': receipt(p)},
    lambda p: {'output_file': str(p)},
])
def test_declared_outputs_do_not_require_a_tool_name_allowlist(supervisor, tmp_path, envelope):
    path = tmp_path / 'result.md'
    path.write_text('공통 출력 본문')
    result = envelope(path)
    calls = [{'name': 'another_provider_edit', 'result': result}]
    assert discover(supervisor, '', calls)[0]['path'] == str(path)
    for denial in ({'success': False}, {'executed': False}, {'not_executed': True}, {'exit_code': 1}):
        calls[0]['result'] = {**result, **denial}
        assert not discover(supervisor, '', calls)


def test_shell_written_report_reaches_first_model_input(supervisor, tmp_path, monkeypatch):
    path = tmp_path / '새 보고서.md'
    body = '## 결과\n수집 사실과 미확인 범위를 구분한 최종 본문\n'
    script = ('import pathlib,json,sys\n'
              'p=pathlib.Path(sys.argv[1]); p.write_text(sys.argv[2], encoding="utf-8")\n'
              'print(json.dumps({"path":str(p),"bytes":p.stat().st_size}))')
    result = subprocess.run([sys.executable, '-c', script, str(path), body],
                            capture_output=True, text=True, check=True)
    key = supervisor._start('shell', {'command': 'python script.py'})
    supervisor._finish(key, result.stdout)
    # 사용자에게는 공개 링크만 반환해 로컬 경로 정규식으로 발견할 수 없다.
    supervisor.store.put_response('[보고서](https://example.test/f?path=report.html)')
    packet = prepare(supervisor)
    assert [a['path'] for a in supervisor.content_artifacts] == [str(path)]
    assert body in packet['files']
    attachment = next(a for a in packet['attachments'] if a['subject'] == str(path))
    assert attachment['role'] == 'submission'
    assert attachment['text'] == body
    assert attachment['revision'] == attachment['source_ref']
    assert snapshot_error(supervisor) is None
    prompts = []

    def evaluate(prompt, **kwargs):
        prompts.append(prompt)
        assert body in prompt and str(path) in prompt
        return 'UNKNOWN\nUNKNOWN_REASON: evidence\n출처 의미 대조는 별도 확인 필요'

    monkeypatch.setattr('consciousness_agent.system_ai_call', evaluate)
    assert json.loads(invoke(supervisor))['status'] == 'UNKNOWN'
    assert len(prompts) == 1  # 파일 존재만으로 완료 승인하지 않는다.
    path.write_text('검수 후 바뀐 판본', encoding='utf-8')
    assert snapshot_error(supervisor)


def test_script_publication_uses_full_receipt_not_source_or_short_preview(supervisor, tmp_path):
    html = tmp_path / '오늘의 보고서.html'
    source = tmp_path / '입력.md'
    html.write_text('<h1>발행 본문</h1><p>실제 내용</p>', encoding='utf-8')
    source.write_text('입력 자료는 출력 영수증이 아니다', encoding='utf-8')
    raw = supervisor.store.evidence({
        'success': True, 'value': {'success': True, 'published': True,
            'source': str(source), 'items': [receipt(html)],
            'public_url': 'https://example.test/report.html'},
        'evidence': [{'kind': 'invoke', 'action': 'self:script', 'targets': {'id': 'render'}}]})
    key = supervisor._start('execute_ibl', {'code': '[self:script]{id:"render"}'})
    supervisor._finish(key, json.dumps({'edition': 2, 'executed': True, 'success': True,
                                       'value': {'published': True}, 'result_ref': raw}))
    supervisor.store.put_response('발행 완료: https://example.test/report.html')
    packet = prepare(supervisor)
    assert html.read_text() in packet['files']
    assert source.read_text() not in packet['files']
    assert set(supervisor._evaluation_snapshot['files']) == {str(html)}


@pytest.mark.parametrize('name,envelope', [
    ('shell', lambda value: json.dumps(value)),
    ('Bash', lambda value: {'stdout': json.dumps(value), 'exit_code': 0}),
    ('run_script', lambda value: value),
    ('functions.exec_command', lambda value: {'output': json.dumps(value), 'exit_code': 0}),
    ('exec_command', lambda value: {'output': json.dumps(value), 'exit_code': 0}),
])
def test_execution_receipts_preserve_spaces_and_deduplicate(supervisor, tmp_path, name, envelope):
    path = tmp_path / '공백 있는 결과.txt'
    path.write_text('끝까지 보존된 내용', encoding='utf-8')
    calls = [{'name': name, 'input': {}, 'result': envelope({'items': [
        receipt(path), {**receipt(path), 'path': path.name}]})}]
    found = discover(supervisor, '', calls)
    assert len(found) == 1 and found[0]['path'] == str(path)


@pytest.mark.parametrize('call', [
    {'name': 'self:read'}, {'name': 'search'},
    {'name': 'execute_ibl', 'runtime_calls': [{'action': 'self:read'}]},
    {'name': 'shell', 'is_error': True},
    {'name': 'shell', 'success': False},
])
def test_read_search_and_failed_calls_do_not_declare_artifacts(supervisor, tmp_path, call):
    path = tmp_path / '원문.txt'
    path.write_text('이미 존재한 원문', encoding='utf-8')
    assert not discover(supervisor, '', [{**call, 'input': {}, 'result': receipt(path)}])


@pytest.mark.parametrize('wrap', [
    lambda r: {'success': False, 'value': r},
    lambda r: {'executed': False, 'value': r},
    lambda r: {'not_executed': True, 'value': r},
    lambda r: {'exit_code': 1, 'stdout': json.dumps(r)},
    lambda r: {'source': r, 'input': r, 'data': r},
    lambda r: 'a log mentioning ' + json.dumps(r),
])
def test_unexecuted_or_unstructured_paths_are_not_outputs(supervisor, tmp_path, wrap):
    path = tmp_path / '기존.txt'
    path.write_text('이전 결과', encoding='utf-8')
    call = {'name': 'shell', 'input': {'command': str(path)}, 'result': wrap(receipt(path))}
    assert not discover(supervisor, '', [call])


def test_staged_publication_keeps_current_draft_and_excludes_old_public_file(supervisor, tmp_path, monkeypatch):
    from test_supervision_delivery import prepare as stage
    public, _, _ = stage(supervisor, tmp_path, monkeypatch)
    manifest = supervisor.delivery.manifest()
    row = manifest['artifacts'][0]
    calls = [{'name': 'run_script', 'input': {}, 'result': {'items': [
        {'path': str(public), 'bytes': 10}, {'path': row['staged'], 'bytes': 20}]}}]
    supervisor.store.put_response('검수 대기')
    packet = prepare(supervisor, calls)
    assert str(public) not in supervisor._evaluation_snapshot['files']
    assert row['staged'] in supervisor._evaluation_snapshot['files']
    assert any(a['subject'] == row['staged'] for a in packet['attachments'])


@pytest.mark.parametrize('selection', ['receipt', 'response'])
def test_explicit_submission_separates_collected_outputs_without_losing_snapshots(
        supervisor, tmp_path, selection):
    report = tmp_path / 'report.md'
    ledger = tmp_path / 'evidence.md'
    source = tmp_path / 'source.json'
    untouched = tmp_path / 'read-only.md'
    for path in (report, ledger, source, untouched):
        path.write_text('실제 파일 ' + path.name)
    outputs = [receipt(path) for path in (source, report, ledger)]
    if selection == 'receipt':
        outputs[1]['role'] = 'submission'
    response = f'[근거]({ledger}) [읽은 자료]({untouched})'
    if selection == 'response':
        response += f' [결과]({report})'
    supervisor.store.put_response(response)
    packet = prepare(supervisor, [{'name': 'shell', 'result': {'artifacts': outputs}}])
    roles = {a['subject']: a['role'] for a in packet['attachments']}
    assert roles[str(report)] == roles[str(ledger)] == 'submission'
    assert roles[str(source)] == 'support'
    assert str(untouched) not in roles
    assert set(supervisor._evaluation_snapshot['files']) == {str(report), str(ledger), str(source)}
    source.write_text('검수 중 바뀐 수집 자료')
    assert snapshot_error(supervisor)  # selection never weakens mutation detection


def test_first_review_keeps_report_and_ledger_with_large_matching_sources(supervisor, tmp_path, monkeypatch):
    from evaluation_input import SUPPORT_PREVIEW_CHARS
    from test_evaluation_input import provider
    report = tmp_path / 'final.md'
    ledger = tmp_path / 'evidence.md'
    report.write_text('보고서 본문\n' * 4000 + '결론 끝')
    ledger.write_text('근거 원장\n' * 1000 + '미확인 끝')
    calls = []
    for i in range(12):
        source = tmp_path / f'source-{i}.json'
        source.write_text(json.dumps({'text': '검증 성공 주장과 반례\n' * 10000}))
        calls.append({'name': 'shell', 'result': receipt(source)})
        supervisor.run_tool('read', {}, lambda: '검증 성공 주장과 반례\n' * 10000)
    calls.append({'name': 'shell', 'result': {'artifacts': [
        {**receipt(report), 'role': 'submission'}, {**receipt(ledger), 'role': 'supporting_evidence'}]}})
    supervisor.store.put_response(f'[보고서]({report})')
    packet = prepare(supervisor, calls)
    observed = []

    def evaluate(prompt, **kwargs):
        text = prompt.prepare_request(provider(request_limits={'chars': 250000}))
        observed.append(prompt.metrics)
        assert report.read_text() in text and ledger.read_text() in text
        supporting = [r for r in prompt.metrics['sections'] if r['role'] not in {'submission', 'recovered', 'citation'}]
        assert sum(r['shown_chars'] for r in supporting) <= SUPPORT_PREVIEW_CHARS
        assert any(r['completeness'] != 'complete' for r in supporting)
        assert len(text) < 200000
        return 'ACHIEVED'

    monkeypatch.setattr('consciousness_agent.system_ai_call', evaluate)
    assert json.loads(invoke(supervisor))['status'] == 'APPROVED'
    assert len(observed) == 1
    assert len(packet['context']['evidence_index']) == 12


def test_unsupervised_collection_uses_same_submission_roles(supervisor, tmp_path):
    from final_evaluator import Evaluator
    report, source = tmp_path / 'result.md', tmp_path / 'collected.txt'
    report.write_text('제출 본문')
    source.write_text('수집 원문')
    evaluator = Evaluator()
    evaluator.project_path = str(tmp_path)
    attachments, snapshots = [], {}
    evaluator._collect_created_files('', [{'name': 'shell', 'result': {'artifacts': [
        {**receipt(report), 'role': 'submission'}, receipt(source)]}}],
        attachments=attachments, snapshots=snapshots, evidence_store=supervisor.store)
    assert {r['subject']: r['role'] for r in attachments} == {
        str(report): 'submission', str(source): 'support'}
    assert set(snapshots) == {str(report), str(source)}


@pytest.mark.parametrize('role', [None, [], {}])
def test_unknown_receipt_role_does_not_break_output_collection(supervisor, tmp_path, role):
    path = tmp_path / 'result.txt'
    path.write_text('관측된 출력')
    found = discover(supervisor, '', [{'name': 'shell', 'result': {**receipt(path), 'role': role}}])
    assert found[0]['path'] == str(path)
    assert found[0]['role'] == 'submission'  # no explicit selection: retain existing fallback


if __name__ == '__main__':
    raise SystemExit(pytest.main([__file__, *sys.argv[1:]]))
