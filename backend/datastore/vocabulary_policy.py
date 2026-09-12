"""필수어휘 보호 선언 — UI·에디션·패키지 관리가 공유하는 데이터 계약."""
from pathlib import Path

import yaml


def load_policy(root: Path = None) -> dict:
    if root is None:
        from runtime_utils import get_base_path
        root = get_base_path()
    path = Path(root) / "data" / "vocabulary_policy.yaml"
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    if (not isinstance(data, dict) or data.get("version") != 1
            or not isinstance(data.get("required_packages"), dict)
            or not isinstance(data.get("standard_nodes"), list)):
        raise ValueError(f"필수어휘 선언이 잘못되었습니다: {path}")
    return data


def required_packages(root: Path = None) -> set:
    return set(load_policy(root)["required_packages"])


def require_optional(package_id: str, root: Path = None) -> None:
    if package_id in required_packages(root):
        raise ValueError(f"'{package_id}'은 필수어휘 묶음이므로 잠재우거나 삭제할 수 없습니다")
