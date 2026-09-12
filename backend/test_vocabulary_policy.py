"""필수 보호가 UI 표시와 무관하게 관리 경로에서도 적용되는지 검증."""
import pytest

from package_manager import PackageManager
from vocabulary_policy import load_policy, required_packages


def test_required_packages_cannot_be_removed():
    manager = PackageManager()
    for package in required_packages():
        for method in (manager.uninstall_package, manager.remove_package):
            with pytest.raises(ValueError, match="필수어휘"):
                method(package)


def test_standard_nodes_match_declarations():
    from ibl_access import load_nodes_raw
    nodes = load_nodes_raw()["nodes"]
    assert set(load_policy()["standard_nodes"]) == {
        n for n, cfg in nodes.items() if cfg.get("always_on")
    }


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__]))
