"""프로젝트 도구의 items 선언은 이름이 있는 Record 행을 반환한다."""
import sys
from types import SimpleNamespace

import boot_paths  # noqa: F401
import pytest
import launcher_ops


def test_templates_keep_record_currency_and_creation_name(monkeypatch):
    names = ['기본', '연구']
    monkeypatch.setattr(launcher_ops, '_pm', lambda: SimpleNamespace(list_templates=lambda: names))
    result = launcher_ops.project_op({'op': 'templates'})
    assert result['success'] is True
    assert result['items'] == [{'name': name} for name in names]
    assert names == ['기본', '연구']


if __name__ == '__main__':
    raise SystemExit(pytest.main([__file__, *sys.argv[1:]]))
