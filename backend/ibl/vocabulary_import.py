"""단일 파일 등록: 후보 컴파일 → 잠든 보유 등록 → 용례 시딩. 실패하면 해당 변경만 회수."""
import copy
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

from runtime_utils import get_base_path
from vocabulary_archive import unpack, digest
from vocabulary_state import (LOCK, inventory, invalidate_inventory, read_state, write_state)


def _atomic_write(path: Path, content: bytes):
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temp = tempfile.mkstemp(prefix='.iblpack-', dir=path.parent)
    try:
        with os.fdopen(fd, 'wb') as stream:
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temp, path)
    finally:
        if os.path.exists(temp):
            os.unlink(temp)


def _seed_examples(examples: list, source: str) -> int:
    from ibl_usage_db import IBLUsageDB
    db = IBLUsageDB()
    with db._get_connection() as conn:
        previous = {row[0] for row in conn.execute('SELECT ibl_code FROM ibl_examples WHERE source=?', (source,))}
    batch = [{k: ex[k] for k in ('intent', 'ibl_code', 'nodes', 'category', 'difficulty', 'tags') if k in ex}
             for ex in examples if ex['ibl_code'] not in previous]
    for ex in batch:
        ex['source'] = source
    count = db.add_examples_batch(batch, owned_vocabulary=True)
    if count != len(batch):
        raise ValueError('동봉 용례 일부가 시딩 관문에서 거절됐습니다')
    return count


def _undo_seed(source: str):
    from ibl_usage_db import IBLUsageDB
    db = IBLUsageDB()
    with db._get_connection() as conn:
        ids = [row[0] for row in conn.execute('SELECT id FROM ibl_examples WHERE source=?', (source,))]
    db._delete_examples(ids)


def import_package(content: bytes) -> dict:
    manifest, files, examples = unpack(content)
    pid = manifest['id']
    root = Path(get_base_path())
    fingerprint = digest(json.dumps(manifest, sort_keys=True, ensure_ascii=False).encode())
    from vocabulary_policy import required_packages
    if pid in required_packages():
        raise ValueError('외부 파일로 필수 묶음을 교체할 수 없습니다')
    with LOCK:
        state = read_state()
        existing = inventory()['packages'].get(pid)
        if existing:
            if existing['manifest'].get('content_sha256') == fingerprint:
                return {'success': True, 'status': 'already_owned', 'package_id': pid, 'seeded': 0}
            raise ValueError('이미 보유한 ID입니다. 다른 내용/버전을 자동으로 덮어쓰지 않습니다')
        with tempfile.TemporaryDirectory(prefix='iblpack-import-') as work:
            incoming, output = Path(work) / 'incoming', Path(work) / 'catalog'
            incoming.mkdir()
            for name, data in files.items():
                target = incoming / name
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(data)
            manifest['content_sha256'] = fingerprint
            (incoming / 'manifest.json').write_text(json.dumps(manifest, ensure_ascii=False, indent=2))
            script = Path(__file__).resolve().parents[2] / 'scripts/iblbuild_catalog.py'
            proc = subprocess.run([sys.executable, str(script), '--root', str(root),
                                   '--incoming', str(incoming), '--output', str(output)],
                                  capture_output=True, text=True, timeout=120)
            if proc.returncode:
                raise ValueError('어휘 검증 실패: ' + (proc.stderr or proc.stdout)[-4000:])
            dest = root / 'data/packages/not_installed/tools' / pid
            artifacts = {root / 'data' / p.name: p.read_bytes() for p in output.iterdir() if p.name != 'tool.json'}
            saved = {p: p.read_bytes() if p.exists() else None for p in artifacts}
            source = 'iblpack:' + pid + ':' + fingerprint
            seeded = False
            from ibl_routing import invalidate_runtime_caches
            try:
                shutil.copytree(incoming, dest)
                (dest / 'tool.json').write_bytes((output / 'tool.json').read_bytes())
                selection = copy.deepcopy(state)
                selection['active'][pid] = False
                selection['revision'] += 1
                write_state(selection)
                for path, data in artifacts.items():
                    _atomic_write(path, data)
                invalidate_inventory()
                failures = invalidate_runtime_caches()
                if failures:
                    raise RuntimeError('캐시 갱신 실패: ' + ', '.join(failures))
                seeded = True
                count = _seed_examples(examples, source)
            except Exception as original:
                undo_error = None
                if seeded:
                    try:
                        _undo_seed(source)
                    except Exception as exc:
                        undo_error = exc
                if dest.exists():
                    shutil.rmtree(dest)
                for path, data in saved.items():
                    if data is None:
                        path.unlink(missing_ok=True)
                    else:
                        _atomic_write(path, data)
                restored = copy.deepcopy(state)
                restored['revision'] += 2
                write_state(restored)
                invalidate_inventory()
                failures = invalidate_runtime_caches()
                if failures:
                    raise RuntimeError('가져오기를 취소했으나 캐시 복구 실패: ' + ', '.join(failures))
                if undo_error:
                    raise RuntimeError(f'등록은 취소했으나 용례 회수 실패: {undo_error}') from original
                raise
            return {'success': True, 'status': 'sleeping', 'package_id': pid, 'active': False,
                    'seeded': count, 'message': '레고박스에 넣었습니다. 사용할 때 깨워 주세요.'}
