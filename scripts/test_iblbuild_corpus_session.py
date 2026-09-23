"""Corpus growth must not multiply registry loads or hide per-source errors."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from iblbuild_v2 import check_v2_corpus


def test_session_reuses_registry_but_checks_every_source(monkeypatch):
    import ibl_v2_adapters
    import ibl_v2_store
    calls = []
    monkeypatch.setattr(ibl_v2_adapters, 'load_registry', lambda: calls.append('registry') or {})
    monkeypatch.setattr(ibl_v2_store, 'definitions', lambda: calls.append('library') or {})
    session, issues = {}, []
    for source in ('return 1', 'return $missing', 'return [2,3]'):
        assert check_v2_corpus('#!ibl edition=2\n'+source, {}, issues, 'fixture', session)
    assert calls == ['registry', 'library'] and len(issues) == 1
    check_v2_corpus('#!ibl edition=2\nreturn 4', {}, [], 'another pass', {})
    assert calls == ['registry', 'library', 'registry', 'library']


def test_broken_registry_is_reported_for_each_row_without_reloading(monkeypatch):
    import ibl_v2_adapters
    calls = []
    def broken():
        calls.append(1)
        raise OSError('fixture unavailable')
    monkeypatch.setattr(ibl_v2_adapters, 'load_registry', broken)
    session, issues = {}, []
    for i in range(3):
        check_v2_corpus('#!ibl edition=2\nreturn 1', {}, issues, f'row{i}', session)
    assert len(calls) == 1 and len(issues) == 3
