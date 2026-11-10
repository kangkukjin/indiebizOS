"""헬퍼 단독 설치 기준(R0) — 대상 PC 에 IndieBizOS·Python·Node 가 없어도 기본 원격 기능이 동작한다.

설계: docs/REMOTE_EXECUTION_CONTINUITY_REPAIR_DESIGN_2026_11_11.md §5·§12 '헬퍼 단독'.
실제 빌드된 헬퍼 바이너리를 **OS 기본 경로와 빈 홈만 있는 환경**에서 띄우고, 격리된 허브(임의 포트)로
등록 연결·셸·info·파일 왕복·전송·작업 조회·취소를 확인한다. 개발 PC 의 가상환경·저장소·Homebrew 가
PATH/HOME 으로 새어 들어와 통과시키는 일이 없게 하는 것이 이 시험의 목적이다.
"""
import boot_paths  # noqa: F401
import importlib.util
import json
import socket
import subprocess
import threading
import time
from pathlib import Path

import pytest
from fastapi import FastAPI

import api_resident_pcs
import device_registry
import limb_keys
import resident_pcs as pcs
import resident_store
from test_resident_pcs import helper_only_env, native_helper_binary

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def standalone(tmp_path, monkeypatch):
    import uvicorn
    binary = native_helper_binary()
    monkeypatch.setenv('INDIEBIZ_RUNTIME_STATE_DIR', str(tmp_path))
    monkeypatch.setattr(limb_keys, '_store_path', lambda: tmp_path / 'keys.json')
    monkeypatch.setattr(limb_keys, '_cache', None)
    monkeypatch.setattr(device_registry, 'register', lambda *a, **k: None)
    rec = limb_keys.resident_enroll(limb_keys.resident_invite('헬퍼만-PC')['key'], 'c' * 32)
    app = FastAPI()
    app.include_router(api_resident_pcs.router)
    sock = socket.socket()
    sock.bind(('127.0.0.1', 0))
    port = sock.getsockname()[1]
    server = uvicorn.Server(uvicorn.Config(app, log_level='error'))
    thread = threading.Thread(target=server.run, kwargs={'sockets': [sock]}, daemon=True)
    thread.start()
    worker, home = tmp_path / 'helper-data', tmp_path / 'home'
    worker.mkdir()
    (worker / 'indiebiz-helper.json').write_text(json.dumps({
        'mode': 'resident', 'base': f'http://127.0.0.1:{port}', 'key': rec['key'], 'installation_id': 'c' * 32,
        'generation': rec['registration']['generation'], 'data_dir': str(worker), 'alias': '헬퍼만-PC'}))
    for _ in range(100):
        if server.started:
            break
        time.sleep(0.02)
    proc = subprocess.Popen([str(binary)], cwd=worker, env=helper_only_env(home),
                            stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)

    def wait(job, timeout=20):
        end = time.time() + timeout
        while time.time() < end:
            row = resident_store.history(job=job['job_id'])['tasks'][0]
            if row['result'] is not None or row['state'] in {'cancelled', 'failed', 'unknown'}:
                return row
            time.sleep(0.05)
        raise AssertionError(('timed out', resident_store.history(job=job['job_id'])))

    def run(command, request_id):
        return wait(pcs.submit(rec['device_id'], command, request_id))
    try:
        yield type('Standalone', (), dict(rec=rec, run=staticmethod(run), wait=staticmethod(wait), home=home,
                                          worker=worker, port=port, tmp=tmp_path))
    finally:
        if proc.poll() is None:
            proc.terminate()
            proc.wait(timeout=5)
        server.should_exit = True
        thread.join(timeout=30)


@pytest.mark.system
def test_helper_alone_keeps_shell_files_transfer_status_and_cancel(standalone):
    s = standalone
    # 셸: OS 가 주는 셸과 명령만 쓴다. 작업이 본 환경이 곧 헬퍼가 받은 환경이다(개발 PATH·HOME 이 새지 않았다).
    shell = s.run({'op': 'shell', 'cmd': 'printf helper-only', 'timeout': 10}, 'shell-1')
    assert shell['state'] == 'succeeded' and shell['result']['output'] == 'helper-only', shell
    seen = s.run({'op': 'shell', 'cmd': 'printf "%s|%s" "$PATH" "$HOME"', 'timeout': 10}, 'env-1')
    assert seen['result']['output'] == '/usr/bin:/bin|' + str(s.home), seen

    # info: 등록 능력과 도구 관측. 이 환경에서 찾은 도구는 OS 기본 경로의 것뿐이다.
    info = s.run({'op': 'info'}, 'info-1')['result']
    assert info['path'] == '/usr/bin:/bin' and info['home'] == str(s.home)
    assert info['resident']['shell'] is True and info['resident']['transfer'] is True
    assert not any(marker in json.dumps(info, ensure_ascii=False) for marker in ('.venv', 'indiebizOS/backend', ':8765'))
    capabilities = limb_keys.get_by_device(s.rec['device_id'])['registration']['capabilities']
    assert isinstance(capabilities['media_components']['missing'], list)   # 선택 구성요소는 신고일 뿐 관문이 아니다
    assert not {'python', 'runtimes'} & set(capabilities)                   # 기본 계약에 런타임 요구가 없다

    # 파일 왕복: write → read → list.
    target = s.home / 'notes' / 'round trip.txt'
    wrote = s.run({'op': 'write', 'path': str(target), 'content': '가나다 abc\n'}, 'write-1')
    assert wrote['state'] == 'succeeded' and target.read_text(encoding='utf-8') == '가나다 abc\n'
    assert s.run({'op': 'read', 'path': str(target)}, 'read-1')['result']['content'] == '가나다 abc\n'
    listed = s.run({'op': 'list', 'path': str(target.parent)}, 'list-1')['result']
    assert [row['name'] for row in listed['files']] == ['round trip.txt']

    # 바이너리 전송: 중앙 → PC → 중앙, 내용 일치.
    payload = bytes(range(256)) * 400
    source = s.tmp / 'source.bin'
    source.write_bytes(payload)
    sent = pcs.transfer_local(s.rec['device_id'], {'action': 'send', 'local_path': str(source),
                                                   'path': str(s.home / 'received.bin'), 'request_id': 'send-1'})
    assert s.wait(sent)['state'] == 'succeeded' and (s.home / 'received.bin').read_bytes() == payload
    back = pcs.transfer_local(s.rec['device_id'], {'action': 'receive', 'path': str(s.home / 'received.bin'),
                                                   'request_id': 'receive-1'})
    assert s.wait(back)['state'] == 'succeeded'
    pcs.transfer_local(s.rec['device_id'], {'action': 'collect', 'local_path': str(s.tmp / 'collected.bin'),
                                            'transfer_id': back['transfer_id']})
    assert (s.tmp / 'collected.bin').read_bytes() == payload

    # 작업 조회: 같은 요청 ID 는 같은 작업을 돌려주고(새 효과 없음), 접수증 어댑터가 세대·수신 시점을 낸다.
    again = pcs.submit(s.rec['device_id'], {'op': 'shell', 'cmd': 'printf helper-only', 'timeout': 10}, 'shell-1')
    assert again['relation'] == 'reused' and again['job_id'] == shell['id']
    spec = importlib.util.spec_from_file_location('standalone_guest', ROOT / 'data/packages/installed/tools/guest-helper/handler.py')
    handler = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(handler)
    view = handler.task_status(again['task_ref'])
    assert view['state'] == 'succeeded' and view['generation'] == s.rec['registration']['generation']
    assert view['result_received_at'] and view['result']['output'] == 'helper-only'

    # 취소: 실행 중인 명령을 같은 작업 참조로 멈추고, 그 명령은 끝까지 가지 못한다.
    marker = s.home / 'finished'
    long = pcs.submit(s.rec['device_id'], {'op': 'shell', 'cmd': f'sleep 6; echo done > "{marker}"', 'timeout': 30}, 'long-1')
    deadline = time.time() + 10
    while resident_store.history(job=long['job_id'])['tasks'][0]['state'] != 'running':
        assert time.time() < deadline
        time.sleep(0.05)
    assert handler.task_status_cancel(long['task_ref'])['state'] in {'cancel_requested', 'cancelled'}
    stopped = s.wait(long)
    assert stopped['state'] == 'cancelled', stopped
    time.sleep(0.5)
    assert not marker.exists()
    # 기본 기능은 그 뒤에도 그대로다.
    assert s.run({'op': 'shell', 'cmd': 'printf still-ok', 'timeout': 10}, 'shell-2')['result']['output'] == 'still-ok'


@pytest.mark.system
def test_missing_program_fails_that_command_only(standalone):
    """사용자가 요청한 프로그램의 의존성은 그 프로그램의 것이다 — 없으면 그 명령만 실패하고 헬퍼는 계속 동작한다."""
    s = standalone
    missing = s.run({'op': 'shell', 'cmd': 'definitely-not-installed-runtime --version', 'timeout': 10}, 'missing-1')
    assert missing['state'] == 'failed' and missing['result']['exit'] != 0
    assert s.run({'op': 'shell', 'cmd': 'printf base-ok', 'timeout': 10}, 'base-1')['result']['output'] == 'base-ok'
    assert s.run({'op': 'info'}, 'info-2')['state'] == 'succeeded'
