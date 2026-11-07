"""Final result collection is independent of how a file was created."""
import json
import pytest
import boot_paths  # noqa: F401
from final_evaluator import prepare, snapshot_error, invoke
from supervisor_content import discover, result_paths
from test_conscious_supervisor import supervisor  # noqa: F401


@pytest.mark.parametrize('producer', ['shell', 'Write', 'apply_patch', 'unknown', None])
def test_final_report_reaches_model_without_producer_receipt(supervisor, tmp_path, monkeypatch, producer):
    report, source = tmp_path / '최종 보고서.md', tmp_path / 'source.json'
    source.write_text('검수에서 다시 조사하지 않는 원문' * 100000)
    body = '# 결과\r\n조건부 결론🙂\r\n[근거](source.json)\n한계: 일반화 미확인'
    report.write_bytes(body.encode())
    calls = ([{'name': producer, 'input': {'path': str(report)},
               'result': json.dumps({'report': str(report), 'characters': len(body)})}]
             if producer else [])
    supervisor.store.put_response(f'[보고서](<{report}>)')
    monkeypatch.setattr(supervisor.store, 'tool_index', lambda *a, **k: pytest.fail('execution trail read'))
    monkeypatch.setattr('research_context.citation_review', lambda *a, **k: pytest.fail('citation audit'))
    packet = prepare(supervisor, calls)
    assert [a['subject'] for a in packet['attachments']] == [str(report)]
    assert packet['attachments'][0]['text'] == body
    assert source.read_text() not in packet['files']
    assert snapshot_error(supervisor) is None
    seen = []
    def model(prompt, **kwargs):
        seen.append(prompt)
        assert body in prompt and '검수에서 다시 조사하지 않는 원문' not in prompt
        return 'UNKNOWN\n일반화 여부는 최종 결과에 미확인으로 명시되어 있습니다.'
    monkeypatch.setattr('consciousness_agent.system_ai_call', model)
    assert json.loads(invoke(supervisor))['status'] == 'UNKNOWN'
    assert len(seen) == 1
    report.write_text('검수 도중 다른 판본')
    assert snapshot_error(supervisor)


def test_files_without_final_reference_are_not_collected(supervisor, tmp_path):
    path = tmp_path / 'working.md'
    path.write_text('작업 중 임시 파일')
    assert discover(supervisor, '최종 답변은 이 문장입니다.', [
        {'name': 'Write', 'input': {'path': str(path)}, 'result': 'saved'}]) == []


def test_missing_final_report_is_reported_not_reconstructed_from_command(supervisor, tmp_path):
    path = tmp_path / 'missing.md'
    supervisor.store.put_response(f'[보고서]({path})')
    packet = prepare(supervisor, [{'name': 'shell', 'input': {'command': 'cat > report.md'},
                                   'result': '상상한 본문'}])
    assert packet['context']['artifact_errors'][0]['path'] == str(path)
    assert '최종 제출물을 읽지 못했습니다' in packet['files']
    assert '상상한 본문' not in packet['files']


def test_paths_preserve_unicode_spaces_and_project_boundary(supervisor, tmp_path):
    from urllib.parse import quote
    path = tmp_path / '한글 공백.py'
    path.write_text('print("final")')
    outside = tmp_path.parent / 'outside.md'
    outside.write_text('프로젝트 밖')
    response = f'[코드]({quote(str(path))}#L1) [중복](<{path}>) [외부]({outside})'
    found = discover(supervisor, response)
    assert len(found) == 1 and found[0]['path'] == str(path)
    link = tmp_path / 'escape.md'
    link.symlink_to(outside)
    assert discover(supervisor, '[링크](escape.md)') == []


def test_staged_publication_uses_current_draft(supervisor, tmp_path, monkeypatch):
    from test_supervision_delivery import prepare as stage
    target, artifact, _ = stage(supervisor, tmp_path, monkeypatch)
    supervisor.store.put_response(f'[최종 결과]({target})')
    packet = prepare(supervisor)
    assert 'new reviewed bytes' in packet['files'] and '14 tips' in packet['files']
    assert str(target) not in supervisor._evaluation_snapshot['files']
    assert artifact['staged'] in supervisor._evaluation_snapshot['files']


def test_collection_masks_secrets_but_checks_original_bytes(supervisor, tmp_path):
    secret = 'sk-' + 'Ab3' * 12
    path = tmp_path / 'report.md'
    path.write_text('최종 결과: ' + secret)
    supervisor.store.put_response(f'[결과]({path})')
    packet = prepare(supervisor)
    assert secret not in packet['files'] and '****' in packet['files']
    assert snapshot_error(supervisor) is None


def test_output_receipts_remain_available_to_visual_consumer(supervisor, tmp_path):
    from providers.codex import CodexProvider
    path = tmp_path / 'image.svg'
    path.write_text('<svg/>')
    result, error = CodexProvider._tool_result({'type': 'file_change', 'status': 'completed',
                                             'changes': [{'path': str(path), 'kind': 'add'}]})
    assert result_paths(supervisor, {'name': 'apply_patch', 'result': result, 'is_error': error}) == [str(path)]
