"""CI 최소 설치에서도 값 코어·실행용 의존성 감사의 경계를 지킨다."""
import subprocess
import sys
from pathlib import Path

import boot_paths  # noqa: F401

ROOT = Path(__file__).resolve().parents[1]


def test_expression_contract_import_without_site_packages():
    # 개발 맥에 requests가 있어도 -S 자식은 stdlib만 보므로 CI의 결손을 재현한다.
    code = '''
import sys
sys.path.insert(0, "backend")
import boot_paths
from ibl_v2_adapters import validate_contract
from common.expression_ir import Fault
from common.value_semantics import numeric_value
assert numeric_value("1.25") is not None
assert "requests" not in sys.modules
assert "common.api_client" not in sys.modules
'''
    result = subprocess.run([sys.executable, '-S', '-c', code], cwd=ROOT,
                            capture_output=True, text=True, timeout=30)
    assert result.returncode == 0, result.stderr


def test_common_http_exports_keep_existing_identity():
    import common
    from common.api_client import api_call, api_call_raw
    assert common.api_call is api_call
    assert common.api_call_raw is api_call_raw
    assert callable(common.clean_html)


def test_runtime_audit_does_not_hide_missing_runtime_imports(tmp_path, monkeypatch):
    monkeypatch.syspath_prepend(str(ROOT / 'scripts'))
    import check_import_coverage as audit

    runtime = tmp_path / 'backend' / 'runtime.py'
    test = runtime.with_name('test_runtime.py')
    support = runtime.with_name('conftest.py')
    runtime.parent.mkdir()
    runtime.write_text('import missing_runtime\n', encoding='utf-8')
    test.write_text('import hypothesis\n', encoding='utf-8')
    support.write_text('import pytest\n', encoding='utf-8')
    monkeypatch.setattr(audit, 'ROOT', tmp_path)
    monkeypatch.setattr(audit, 'SCAN_ROOTS', [runtime.parent])
    monkeypatch.setattr(audit, 'SCAN_FILES', [])
    assert set(audit.collect_imports()) == {'missing_runtime'}
    assert set(audit.collect_imports(include_tests=True)) == {
        'missing_runtime', 'hypothesis', 'pytest'}
    # 같은 개발 라이브러리라도 실행 코드가 읽으면 기본 감사가 반드시 잡는다.
    runtime.write_text('import hypothesis\n', encoding='utf-8')
    assert set(audit.collect_imports()) == {'hypothesis'}


if __name__ == '__main__':
    import pytest
    raise SystemExit(pytest.main([__file__]))
