"""실제 제한 프로세스와 부품 판본·계약 검증. 외부 서비스 호출 없음."""
from pathlib import Path
import json
import os
import socket

import boot_paths  # noqa: F401
import pytest
import component_runtime as c
from coding_process import available

pytestmark = pytest.mark.skipif(not available(), reason='macOS component sandbox')
ROOT = Path(__file__).resolve().parents[1]


def test_real_transform_preserves_contract_and_empty():
    spec = c.registry(ROOT)['web.naver_response']
    source = (ROOT / spec['source']).read_bytes()
    assert c.verify(spec, source)['cases'] == 3
    assert c.run(source, {'response': {'items': []}, 'type': 'news'}) == []
    with pytest.raises(ValueError, match='items'):
        c.run(source, {'response': {'different': []}, 'type': 'news'})


def test_candidate_cannot_read_or_write_host_or_use_environment(tmp_path, monkeypatch):
    secret = tmp_path / 'secret.txt'
    secret.write_text('private fixture')
    monkeypatch.setenv('NAVER_CLIENT_SECRET', 'credential fixture')
    source = ("import os\ndef transform(x):\n"
              "    results=[]\n"
              "    for mode in ('r','w'):\n"
              "        try: open(x,mode); results.append('allowed')\n"
              "        except PermissionError: results.append('denied')\n"
              "    return results+[os.getenv('NAVER_CLIENT_SECRET')]\n").encode()
    assert c.run(source, str(secret)) == ['denied', 'denied', None]
    assert secret.read_text() == 'private fixture'


def test_candidate_cannot_network_or_signal_host():
    with socket.socket() as server:
        server.bind(('127.0.0.1', 0)); server.listen()
        source = b'''import socket,os,signal
def transform(x):
    results=[]
    try: socket.create_connection(('127.0.0.1',x['port']),timeout=.2); results.append('allowed')
    except OSError: results.append('denied')
    try: os.kill(x['pid'],0); results.append('allowed')
    except PermissionError: results.append('denied')
    return results
'''
        assert c.run(source, {'port': server.getsockname()[1], 'pid': os.getpid()}) == ['denied', 'denied']


def test_invalid_contract_and_corrupt_version_rejected(tmp_path):
    spec = c.registry(ROOT)['web.naver_response']
    with pytest.raises(ValueError, match='계약'):
        c.verify(spec, b'def transform(x): return []')
    version = c.store_object(tmp_path, b'def transform(x): return []')
    c.publish(tmp_path, spec, version, receipt={'commit': 'test'})
    assert c.active(tmp_path, spec)['version'] == version
    c.object_path(tmp_path, version).write_text('tampered')
    with pytest.raises(ValueError, match='손상'):
        c.active_source(tmp_path, ROOT, spec)


def test_new_generation_source_supersedes_old_overlay(tmp_path):
    import shutil
    code = tmp_path / 'code'
    original = c.registry(ROOT)['web.naver_response']
    dest = code / original['source']; dest.parent.mkdir(parents=True)
    shutil.copyfile(ROOT / original['source'], dest)
    shutil.copyfile(ROOT / Path(original['source']).parent / 'runtime_components.json',
                    dest.parent / 'runtime_components.json')
    spec = c.registry(code)['web.naver_response']
    version = c.store_object(tmp_path, b'def transform(x): return []')
    c.publish(tmp_path, spec, version, receipt={'commit': 'fixture'})
    live = tmp_path / spec['source']; live.parent.mkdir(parents=True)
    live.write_bytes(c.object_path(tmp_path, version).read_bytes())
    assert c.active_source(tmp_path, code, spec) == b'def transform(x): return []'
    live.write_bytes(dest.read_bytes())
    assert c.active_source(tmp_path, code, spec) == dest.read_bytes()
    live.write_bytes(c.object_path(tmp_path, version).read_bytes())
    dest.write_text('def transform(x): return [x]\n')
    assert c.active_source(tmp_path, code, c.registry(code)['web.naver_response']) == dest.read_bytes()


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__]))
