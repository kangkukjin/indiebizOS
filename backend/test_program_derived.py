"""Generated definitions keep their owner without opening prose/core writes."""
from pathlib import Path
from types import SimpleNamespace

import boot_paths  # noqa: F401
import pytest
from test_repair_workspace_completion import module


@pytest.fixture
def case(tmp_path, monkeypatch):
    repo = tmp_path / 'repo'
    wt = repo / 'candidate'
    wt.mkdir(parents=True)
    candidate, derived = module('repair_candidate'), module('program_derived')
    docs = {'files': ['data/ibl_nodes.yaml'], 'documents': [['README.md', '<!-- X -->', '<!-- Y -->']]}
    monkeypatch.setattr(derived, 'contract', lambda: docs)
    calls = []
    def checked(*args, **kwargs):
        calls.append(args)
        return SimpleNamespace(returncode=0, stdout='', stderr='')
    monkeypatch.setattr('repair_process.run', checked)
    session = {'worktree': 'candidate', 'baseline': {}}
    return repo, wt, candidate, derived, session, calls


def test_owner_check_admits_exact_compiled_definition_and_rejects_later_tamper(case):
    repo, wt, candidate, derived, session, calls = case
    path = wt / 'data/ibl_nodes.yaml'
    path.parent.mkdir()
    path.write_text('nodes: {}')
    current = {'data/ibl_nodes.yaml': candidate.fingerprint(path)}
    derived.accept(candidate, repo, session, current, list(current))
    assert len(calls) == 1
    assert session['derived_files'] == current
    path.write_text('nodes: changed')
    assert candidate.fingerprint(path) != session['derived_files']['data/ibl_nodes.yaml']


def test_document_marker_changes_do_not_authorize_prose_changes(case):
    repo, wt, candidate, derived, session, calls = case
    before = 'instruction\n<!-- X -->old<!-- Y -->\n'
    (repo / 'README.md').write_text(before)
    session['baseline']['README.md'] = candidate.fingerprint(repo / 'README.md')
    (wt / 'README.md').write_text(before.replace('old', 'new'))
    current = {'README.md': candidate.fingerprint(wt / 'README.md')}
    derived.accept(candidate, repo, session, current, list(current))
    assert len(calls) == 1
    session.pop('derived_files')
    (wt / 'README.md').write_text(before.replace('instruction', 'weakened instruction'))
    with pytest.raises(PermissionError, match='마커 밖'):
        derived.accept(candidate, repo, session, {'README.md': candidate.fingerprint(wt / 'README.md')}, ['README.md'])
    assert len(calls) == 1


@pytest.mark.parametrize('relative', ['scripts/iblbuild_derive.py',
                                      'backend/base/program_boundary.py',
                                      'backend/base/repair_process_bridge.py'])
def test_core_and_builder_changes_are_rejected_before_candidate_execution(case, relative):
    repo, wt, candidate, derived, session, calls = case
    path = wt / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text('raise RuntimeError("must not execute")\n')
    current = {relative: candidate.fingerprint(path)}
    with pytest.raises(PermissionError):
        derived.accept(candidate, repo, session, current, [relative])
    assert not calls


if __name__ == '__main__':
    raise SystemExit(pytest.main([__file__]))
