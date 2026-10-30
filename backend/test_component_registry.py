"""순수 부품 교체와 권한 코드 감사의 서로 다른 판본 경계."""
import json
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
from threading import Event

import boot_paths  # noqa: F401
import component_registry as c
import pytest


def fixture_package(root):
    pkg = root / 'data/packages/installed/tools/example'
    pkg.mkdir(parents=True)
    (pkg / 'handler.py').write_text('# privileged host\n')
    source = pkg / 'example_response.py'
    source.write_text('def transform(x): return x\n')
    spec = {'id': 'example.response', 'protocol': 'pure-json/1',
            'source': source.relative_to(root).as_posix(), 'fixtures': []}
    (pkg / 'runtime_components.json').write_text(json.dumps([spec]))
    return pkg, source


def test_isolated_bytes_do_not_invalidate_privileged_audit(tmp_path):
    pkg, source = fixture_package(tmp_path)
    original = c.handler_fingerprint(pkg)
    source.write_text('def transform(x): return [x]\n')
    assert c.handler_fingerprint(pkg) == original
    manifest = pkg / 'runtime_components.json'
    manifest.write_text(manifest.read_text() + '\n')
    assert c.handler_fingerprint(pkg) != original
    next_version = c.handler_fingerprint(pkg)
    (pkg / 'handler.py').write_text('# changed privileged host\n')
    assert c.handler_fingerprint(pkg) != next_version


@pytest.mark.parametrize('source', ['data/packages/installed/tools/example/handler.py',
                                    'data/packages/installed/tools/other/tool.py',
                                    'data/packages/installed/tools/example/../tool.py'])
def test_registration_cannot_exclude_host_or_another_package(tmp_path, source):
    pkg, _ = fixture_package(tmp_path)
    (pkg / 'runtime_components.json').write_text(json.dumps([
        {'protocol': 'pure-json/1', 'source': source}]))
    with pytest.raises(ValueError):
        c.handler_fingerprint(pkg)


def test_inflight_snapshot_and_independent_task_survive_publication(tmp_path):
    pkg, source = fixture_package(tmp_path)
    spec = c.registry(tmp_path)['example.response']
    before = source.read_bytes()
    selected, release = Event(), Event()

    def in_flight():
        snapshot = c.active_source(tmp_path, tmp_path, spec)
        selected.set()
        assert release.wait(5)
        return snapshot

    with ThreadPoolExecutor(max_workers=2) as pool:
        running = pool.submit(in_flight)
        assert selected.wait(5)
        after = b'def transform(x): return [x]\n'
        version = c.store_object(tmp_path, after)
        c.publish(tmp_path, spec, version, receipt={'commit': 'fixture'})
        source.write_bytes(after)
        assert pool.submit(lambda: 2 + 3).result(timeout=5) == 5
        assert c.active_source(tmp_path, tmp_path, spec) == after
        release.set()
        assert running.result(timeout=5) == before


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__]))
