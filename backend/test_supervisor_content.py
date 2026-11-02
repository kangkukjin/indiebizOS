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


if __name__ == '__main__':
    raise SystemExit(pytest.main([__file__, *sys.argv[1:]]))
