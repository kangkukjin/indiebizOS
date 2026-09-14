"""회원 작업 공간: 실제 실행 관문, NDJSON 표면, 사적 경로와 공통 앱 격리."""
import boot_paths
import json
import re
import shutil
import subprocess
import threading
from types import SimpleNamespace

import pytest
import principal as P
import member_runtime as MR

@pytest.fixture(autouse=True)
def principal_context():
    token = P.set_transport(P.OWNER)
    yield
    P.reset_transport(token)


def test_command_is_sent_only_to_connected_local_task(tmp_path, monkeypatch):
    from member_runner import MemberRunner
    import member_bridge
    sent = []
    monkeypatch.setattr(member_bridge, 'request', lambda command, **kw: sent.append(command) or {'success': True})
    runner = MemberRunner.__new__(MemberRunner)
    with P.narrow(P.member('member-a', 4, 'device-a')), MR.turn_scope(tmp_path, 'device-a', 'hub-task', threading.Event(), {}):
        MR.current().update(local_task_id='local-task', shell_available=True)
        assert json.loads(runner._member_tool('run_command', {'command': 'echo local', 'timeout': 2}))['success']
        MR.current()['shell_available'] = False
        assert json.loads(runner._member_tool('run_command', {'command': 'echo denied'}))['error_type'] == 'permission'
    assert sent == [{'op': 'shell', 'cmd': 'echo local', 'timeout': 2}]


def test_foreign_spill_cannot_read_owner_or_symlink(tmp_path):
    from common.spill import read_ref
    owner = tmp_path / 'owner-secret.txt'
    owner.write_text('PRIVATE OWNER')
    private = tmp_path / 'member'
    private.mkdir()
    with P.narrow(P.member('a', 4, 'd')), MR.turn_scope(private, 'd', 'task', threading.Event(), {}):
        from common.spill import spill_dir
        from pathlib import Path
        spill = Path(spill_dir())
        (spill / 'link').symlink_to(owner)
        for path in [owner, spill / 'link']:
            body, error = read_ref({'path': str(path)})
            assert body is None and error
        (spill / 'mine').write_text('LOCAL')
        assert read_ref({'path': str(spill / 'mine')}) == ('LOCAL', None)


def test_new_routes_use_member_auth_without_owner_login():
    from api_launcher_web import is_public_remote_path
    for path in ['/m/run', '/m/apps', '/m/bootstrap']:
        assert is_public_remote_path('POST', path)
        assert not is_public_remote_path('DELETE', path)


def test_member_stream_carries_local_task_and_events(monkeypatch):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    import api_member
    from member_session import MemberSessionManager
    seen = []
    def turn(*args, **kw):
        seen.append((P.current(), kw['local_task_id'], kw['code']))
        kw['on_event']({'type': 'text', 'content': 'local progress'})
        return {'success': True, 'response': 'done'}
    monkeypatch.setattr(api_member, '_member_of', lambda key: (({'device_id': 'd'}, 'a', 4), None) if key == 'test-key' else (None, {'success': False, 'error': 'invalid'}))
    monkeypatch.setattr(MemberSessionManager, 'instance', lambda: SimpleNamespace(turn=turn, close=lambda *args: None))
    app = FastAPI(); app.include_router(api_member.router)
    with TestClient(app) as client:
        out = client.post('/m/run', json={'key': 'test-key', 'task_id': 'local-1', 'message': 'test'} )
        rows = [json.loads(line) for line in out.text.splitlines()]
        assert [r['type'] for r in rows] == ['event', 'result']
        assert rows[-1]['result']['success']
        assert client.post('/m/run', json={'key': 'wrong', 'task_id': 'local-1', 'message': 'test'}).json()['success'] is False
    assert seen[0][0] == P.member('a', 4, 'd')
    assert seen[0][1:] == ('local-1', None)


def test_catalogue_removes_closed_modes_and_never_loads_owner_apps(monkeypatch, tmp_path):
    import member_apps
    import api_launcher_web
    import runtime_utils
    monkeypatch.setattr(runtime_utils, 'get_base_path', lambda: str(tmp_path))
    monkeypatch.setattr(member_apps, 'load_nodes_installed', lambda: {'nodes': {'self': {'actions': {'read': {'app': {'instrument': 'files'}}}}}})
    monkeypatch.setattr(member_apps, 'visible', lambda *args: True)
    def derive(include_standalone):
        assert include_standalone is False
        return {'instruments': [{'id':'files', 'modes':[{'name':'read','action':'[self:read]{path:"$path"}'},{'name':'owner','action':'[self:config]{}'}]}]}
    monkeypatch.setattr(api_launcher_web, '_derive_instruments', derive)
    out = member_apps.catalogue()
    assert [m['name'] for m in out['instruments'][0]['modes']] == ['read']


def test_app_frame_scripts_parse_and_have_no_local_credentials():
    from member_app_frame import frame_html
    html = frame_html()
    assert "connect-src 'none'" in html
    assert 'X-Member-Token' not in html and 'MemberBridge.request' not in html
    if not shutil.which('node'):
        pytest.skip('node required')
    for script in re.findall(r'<script[^>]*>(.*?)</script>', html, re.S):
        subprocess.run(['node','--check'],input=script,text=True,capture_output=True,check=True)


def test_app_executes_real_ibl_without_model_initialization(tmp_path, monkeypatch):
    from member_session import MemberSessionManager, MemberSession
    import member_session, member_bridge, member_profile
    monkeypatch.setattr(member_session, '_base', lambda: tmp_path)
    monkeypatch.setattr(member_bridge, 'connected', lambda device: True)
    monkeypatch.setattr(member_profile, '_package_open', lambda *args, **kw: True)
    monkeypatch.setattr(MemberSession, '_ensure_runner', lambda self: pytest.fail('앱에서 모델 초기화'))
    sent = []
    def exchange(command, **kw):
        sent.append(command)
        if command['op'] == 'memory_recall':
            return {'success': True, 'history': [], 'workspace': '/member/workspace'}
        if command['op'] == 'memory_save':
            return {'success': True, 'saved': True}
        return {'success': True, 'files': [{'name': 'local.txt'}]}
    monkeypatch.setattr(member_bridge, 'request', exchange)
    out = MemberSessionManager(tmp_path).turn('a','d',4,'member','앱 실행',local_task_id='local-task',code='[self:list]{path:"."}')
    assert out['success'], out
    assert out['memory_saved'] and out['app_result']
    assert any(c == {'op': 'list', 'path': '.'} for c in sent)


def test_bootstrap_validates_key_and_returns_local_member_bundle(tmp_path, monkeypatch):
    from fastapi import HTTPException
    import api_member, runtime_utils, io, zipfile
    binary = tmp_path / 'helper/dist/indiebiz-helper-linux'
    binary.parent.mkdir(parents=True)
    binary.write_bytes(b'synthetic binary')
    monkeypatch.setattr(runtime_utils, 'get_base_path', lambda: str(tmp_path))
    monkeypatch.setattr(api_member, '_member_of', lambda key: (({'alias': 'test'}, 'a', 4), None) if key == 'synthetic-key' else (None, {'error': 'invalid'}))
    req = api_member.MemberBootstrap(key='synthetic-key',platform='linux',base='https://hub.example')
    response = api_member.member_bootstrap(req)
    with zipfile.ZipFile(io.BytesIO(response.body)) as archive:
        config = json.loads(archive.read('indiebiz-helper.json'))
        assert config['mode'] == 'member' and config['key'] == 'synthetic-key'
        assert archive.read(binary.name) == b'synthetic binary'
        assert archive.getinfo(binary.name).external_attr >> 16 & 0o111
    req.key = 'invalid'
    with pytest.raises(HTTPException):
        api_member.member_bootstrap(req)


if __name__ == '__main__':
    raise SystemExit(pytest.main([__file__, '-q']))
