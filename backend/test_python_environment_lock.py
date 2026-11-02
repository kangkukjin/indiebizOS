"""Environment identity stays fresh while metadata is decoded only once."""
import hashlib
import importlib.metadata
import json
import sys

import boot_paths  # noqa: F401
import pytest

import python_environment_lock as environment


@pytest.fixture
def installation(tmp_path, monkeypatch):
    base = tmp_path / 'example-1.0.dist-info'
    base.mkdir()
    (base / 'METADATA').write_text('Metadata-Version: 2.1\nName: example\nVersion: 1.0\n\nDescription\n')
    (base / 'RECORD').write_text('example.py,,\n')
    source = tmp_path / 'source'
    source.mkdir()
    (source / 'script.py').write_text('value = 1\n')
    reads = []

    class Distribution(importlib.metadata.PathDistribution):
        def read_text(self, filename):
            reads.append(filename)
            return super().read_text(filename)

    monkeypatch.setattr(environment.metadata, 'distributions', lambda: [Distribution(base)])
    return base, source, reads


def test_fingerprint_keeps_existing_digest_and_reads_metadata_once(installation):
    base, source, reads = installation
    expected = hashlib.sha256(sys.version.encode())
    expected.update(b'example=1.0')
    for name in ('METADATA', 'RECORD'):
        path = base / name
        stat = path.stat()
        expected.update(f'{path}:{stat.st_size}:{stat.st_mtime_ns}'.encode())
    metadata_digest = expected.hexdigest()
    expected.update((source / 'script.py').read_bytes())
    assert environment.fingerprint(source, details=True) == {
        'combined': expected.hexdigest(), 'environment': metadata_digest}
    assert reads.count('METADATA') == 1


@pytest.mark.parametrize('change', ['metadata', 'record', 'editable', 'source', 'removed'])
def test_later_fingerprint_observes_environment_and_source_changes(installation, change):
    base, source, _ = installation
    editable = source.parent / 'editable'
    editable.mkdir()
    module = editable / 'module.py'
    module.write_text('value = 1\n')
    (base / 'direct_url.json').write_text(json.dumps({
        'url': editable.as_uri(), 'dir_info': {'editable': True}}))
    before = environment.fingerprint(source, details=True)
    if change == 'metadata':
        (base / 'METADATA').write_text('Name: example\nVersion: 2.0\n')
    elif change == 'record':
        (base / 'RECORD').write_text('new.py,,\nexample.py,,\n')
    elif change == 'editable':
        module.write_text('value = 2\n')
    elif change == 'removed':
        (base / 'RECORD').unlink()
    else:
        (source / 'script.py').write_text('value = 2\n')
    after = environment.fingerprint(source, details=True)
    assert before['combined'] != after['combined']
    assert (before['environment'] == after['environment']) == (change == 'source')


def test_aliases_and_duplicate_search_paths_do_not_change_installation(installation, monkeypatch):
    base, source, _ = installation
    alias = base.parent / 'alias.dist-info'
    alias.symlink_to(base, target_is_directory=True)
    dist = importlib.metadata.PathDistribution
    monkeypatch.setattr(environment.metadata, 'distributions', lambda: [dist(base)])
    before = environment.fingerprint(source)
    monkeypatch.setattr(environment.metadata, 'distributions', lambda: [dist(alias), dist(base)])
    assert environment.fingerprint(source) == before


def test_explicit_search_paths_survive_different_caller_environment(tmp_path, monkeypatch):
    folder = tmp_path / 'libs'
    dist = folder / 'example-1.dist-info'
    dist.mkdir(parents=True)
    (dist / 'METADATA').write_text('Name: example\nVersion: 1\n')
    before = environment.fingerprint(tmp_path, search_paths=[str(folder)])
    monkeypatch.setattr(sys, 'path', [])
    assert environment.fingerprint(tmp_path, search_paths=[str(folder)]) == before
    (dist / 'METADATA').write_text('Name: example\nVersion: 2\n')
    assert environment.fingerprint(tmp_path, search_paths=[str(folder)]) != before


def test_program_environment_tracks_transitive_installs_not_unrelated_packages(tmp_path):
    def install(name, version, requires=''):
        root = tmp_path / (name + '.dist-info')
        root.mkdir(exist_ok=True)
        (root / 'METADATA').write_text(f'Name: {name}\nVersion: {version}\n' + requires)
        (root / 'top_level.txt').write_text(name)
    install('feature', '1', 'Requires-Dist: shared>=1\n')
    install('shared', '1')
    install('unrelated', '1')
    fingerprint = lambda: environment.fingerprint(tmp_path, search_paths=[str(tmp_path)], modules=['feature'])
    before = fingerprint()
    install('unrelated', '2')
    assert fingerprint() == before
    install('shared', '2')
    assert fingerprint() != before

if __name__ == '__main__':
    raise SystemExit(pytest.main([__file__]))
