"""Original full photo workflow on an isolated hub and native resident helper.

No connection to the real 맥12, no OS service installation, no model calls.
"""
import boot_paths  # noqa: F401
import json
import platform
import socket
import subprocess
import threading
import time
from pathlib import Path

import pytest
from fastapi import FastAPI
import uvicorn

from test_guestpc_resident_idioms import pc  # noqa: F401
from test_resident_pcs import registry  # noqa: F401

ROOT = Path(__file__).resolve().parents[1]
ROUND = ROOT / 'docs/experiments/long_sentence_imagination/round_49'


@pytest.fixture
def native_pc(pc):
    import api_resident_pcs
    if platform.system() != 'Darwin':
        pytest.skip('original photo program uses macOS sips')
    arch = 'arm64' if platform.machine() == 'arm64' else 'amd64'
    binary = ROOT / f'helper/dist/indiebiz-helper-mac-{arch}'
    sock = socket.socket()
    sock.bind(('127.0.0.1', 0))
    port = sock.getsockname()[1]
    app = FastAPI()
    app.include_router(api_resident_pcs.router)
    server = uvicorn.Server(uvicorn.Config(app, log_level='error'))
    thread = threading.Thread(target=server.run, kwargs={'sockets': [sock]}, daemon=True)
    thread.start()
    worker = pc.path / 'worker'
    worker.mkdir()
    # The isolated registry and native helper share one installation identity.
    import limb_keys
    installation = limb_keys.get_by_device(pc.rec['device_id'])['registration']['installation_id']
    cfg = {'mode': 'resident', 'base': f'http://127.0.0.1:{port}', 'key': pc.rec['key'],
           'installation_id': installation, 'generation': pc.rec['registration']['generation'],
           'data_dir': str(worker), 'alias': '시험PC'}
    (worker / 'indiebiz-helper.json').write_text(json.dumps(cfg))
    proc = None
    try:
        for _ in range(100):
            if server.started:
                break
            time.sleep(.02)
        assert server.started
        proc = subprocess.Popen([str(binary)], cwd=worker, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
        pc.real_local_tools = True
        from ibl_v2_runtime import Budget
        pc.runtime_options = {'budget': Budget(steps=1000000, rows=100000)}
        yield pc
    finally:
        if proc and proc.poll() is None:
            proc.terminate()
            proc.wait(timeout=10)
        server.should_exit = True
        thread.join(timeout=30)
        assert not thread.is_alive()


@pytest.mark.system
@pytest.mark.parametrize('draft,variant,count', [('remote_v3.ibl', 'base', 8),
    ('remote_repaired.ibl', 'broken', 8), ('remote_repaired.ibl', 'large', 108)])
def test_full_photo_workflow_and_resubmission(native_pc, draft, variant, count):
    from PIL import Image
    pc = native_pc
    src, out = pc.path / 'input', pc.path / 'out'
    photos = src / 'photos'
    photos.mkdir(parents=True)
    out.mkdir()
    for i in range(count):
        Image.new('RGB', (128, 96), (i % 256, 45, 90)).save(photos / f'한글 사진 ({i}).png')
    (photos / '빈 파일.png').write_bytes(b'')
    if variant == 'broken':
        (photos / '깨진 사진.png').write_bytes(b'not a png')
    remote = pc.path / 'remote' / variant
    job = {'pc': '시험PC', 'remote_dir': str(remote), 'long_side': 80, 'quality': 80,
           'bundle': '한글 결과', 'skip': {'min_bytes': 1, 'name_prefix': ''},
           'pace_ms': 0, 'format': 'jpeg'}
    (src / 'job.json').write_text(json.dumps(job, ensure_ascii=False))
    code = (ROUND / 'drafts' / draft).read_text()
    result = pc(code, src=str(src), out=str(out))
    assert result['collected'] and result['originals_match'] and result['isolation'], result
    assert result['converted'] == count and result['runs'] == 1 and result['skipped'] == 1
    assert len(result['failed']) == (1 if variant == 'broken' else 0)
    assert not remote.exists() and result['connected'] and result['folder_absent']
    report = json.loads((out / 'result.json').read_text())
    assert report['collect']['zip']['names_missing'] == []
    if draft == 'remote_repaired.ibl':
        assert all(t['seconds'] is not None for t in report['history'])
    # Real saved ZIP bytes and names, independently opened with archive's reader.
    import importlib.util
    spec = importlib.util.spec_from_file_location('round49_archive', ROOT / 'data/scripts/압축.py')
    archive = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(archive)
    restored = pc.path / 'restored'
    unpacked = archive.op_unpack({'path': str(out / '한글 결과.zip'), 'out_dir': str(restored)})
    assert unpacked['count'] == count
    for row in unpacked['items']:
        with Image.open(row['out']) as image:
            assert max(image.size) <= 80 and image.format == 'JPEG'
    before = len(pc.history())
    pc.runtime_options['budget'] = __import__('ibl_v2_runtime').Budget(steps=1000000, rows=100000)
    again = pc(code, src=str(src), out=str(out))
    # info/list are reads without request IDs; all shell/transfer effects must be reused.
    new_tasks = pc.history()[:len(pc.history())-before]
    assert all(t['summary']['op'] in {'info', 'list'} for t in new_tasks)
    assert again['runs'] == 1 and again['collected']


if __name__ == '__main__':
    raise SystemExit(pytest.main([__file__]))
