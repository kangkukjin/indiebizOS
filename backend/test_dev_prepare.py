"""개발준비의 실제 사본 신원, 변경 감지 및 실패 입력 계약."""
import boot_paths  # noqa: F401
import hashlib
import importlib.util
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location('dev_prepare_under_test', ROOT / 'data/scripts/dev_prepare.py')
prepare = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(prepare)


def test_prepare_observes_actual_candidate_and_existing_owners():
    path = 'data/scripts/dev_prepare.py'
    result = prepare.prepare({'files': [path]})
    assert Path(prepare.__file__).resolve() == ROOT / path
    assert result['identity']['workspace'] == str(ROOT)
    assert result['identity']['files'][path]['sha256'] == hashlib.sha256((ROOT / path).read_bytes()).hexdigest()
    assert result['items'][0]['owner'] == prepare.describe(path)
    assert result['tests']['owner'] == 'scripts/select_tests.py'
    assert result['tests']['pytest_args']
    assert result['stable']
    assert any('SOURCE_ROOTS' in row['reason'] for row in result['unknown'])
    assert not result['source_complete']


@pytest.mark.parametrize('files', [None, [], ['../outside.py'], ['/tmp/outside.py'], [42]])
def test_invalid_files_are_rejected(files):
    with pytest.raises((ValueError, TypeError)):
        prepare.prepare({'files': files})


def test_missing_file_and_changed_prior_identity_are_not_current_evidence(tmp_path):
    previous = {'workspace': str(tmp_path), 'head': {'value': 'old'},
                'files': {'missing.py': {'sha256': 'old', 'state': 'read'}}}
    result = prepare.prepare({'files': ['missing.py'], 'previous': previous}, root=tmp_path)
    assert result['items'][0]['state'] == 'unread'
    assert result['unknown'] and not result['source_complete']
    assert result['previous_comparison']['files_changed'] == ['missing.py']
    assert result['previous_comparison']['head_changed']


def test_outside_symlink_is_rejected(tmp_path):
    workspace = tmp_path / 'workspace'
    workspace.mkdir()
    outside = tmp_path / 'outside.py'
    outside.write_text('VALUE = 1\n')
    (workspace / 'linked.py').symlink_to(outside)
    with pytest.raises(ValueError, match='사본 밖'):
        prepare.prepare({'files': ['linked.py']}, root=workspace)


if __name__ == '__main__':
    raise SystemExit(pytest.main([__file__, *sys.argv[1:]]))
