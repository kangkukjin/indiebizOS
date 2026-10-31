"""Observation facts distinguish recoverable artifacts, unknown sizes and user files."""
import boot_paths  # noqa: F401
import importlib.util
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('remote_observe', ROOT / 'scripts/remote_observe.py')
observer = importlib.util.module_from_spec(spec)
spec.loader.exec_module(observer)


def test_bounded_scan_reports_lower_bound_and_never_mutates(tmp_path):
    for n in range(10):
        (tmp_path / str(n)).write_bytes(b'x' * 100)
    result = observer.path_facts(tmp_path, max_entries=4)
    assert not result['complete'] and result['size_kind'] == 'observed_lower_bound'
    assert result['bytes'] < 1000
    assert len(list(tmp_path.iterdir())) == 10
    exact = observer.path_facts(tmp_path)
    assert exact['complete'] and exact['bytes'] == 1000
    assert exact['volume']['free_bytes'] > 0


def test_missing_and_linked_paths_are_not_zero_size_cleanup_evidence(tmp_path):
    missing = observer.path_facts(tmp_path / 'missing')
    assert not missing['exists'] and missing['bytes'] is None
    (tmp_path / 'outside').write_bytes(b'keep')
    (tmp_path / 'link').symlink_to(tmp_path / 'outside')
    result = observer.path_facts(tmp_path / 'link')
    assert not result['complete'] and result['errors'][0]['reason'] == 'link_not_followed'
    assert (tmp_path / 'outside').read_bytes() == b'keep'


def test_provenance_is_evidence_not_delete_advice_and_stale_receipt_is_explicit(tmp_path):
    archive = tmp_path / 'archive.zip'
    archive.write_bytes(b'cached')
    receipt = archive.with_name(archive.name + '.artifact.json')
    receipt.write_text(json.dumps({'bytes': archive.stat().st_size, 'mtime_ns': archive.stat().st_mtime_ns,
                                   'source_url': 'https://example.invalid/archive.zip', 'kind': 'download_archive'}))
    result = observer.path_facts(archive)
    assert result['provenance']['matches_size_mtime']
    archive.write_bytes(b'authored changes')
    assert not observer.path_facts(archive)['provenance']['matches_size_mtime']
    user_file = tmp_path / 'personal.db'
    user_file.write_bytes(b'personal')
    assert 'provenance' not in observer.path_facts(user_file)
    assert 'delete' not in result


def test_unavailable_process_library_and_malformed_receipt_preserve_other_facts(tmp_path, monkeypatch):
    import sys
    monkeypatch.setitem(sys.modules, 'psutil', None)
    archive = tmp_path / 'cache.zip'
    archive.write_bytes(b'cache')
    archive.with_name('cache.zip.artifact.json').write_text('[]')
    result = observer.observe(tmp_path, [archive])
    assert result['paths'][0]['bytes'] == 5
    assert 'error' in result['paths'][0]['provenance']
    assert result['processes']['unobserved_processes'] is None
    assert 'error' in result['processes']


if __name__ == '__main__':
    import pytest
    raise SystemExit(pytest.main([__file__]))
