"""어휘 선택의 유일한 변경 경로. HTTP·IBL·조종실 모두 같은 계약을 사용한다."""
import copy
import importlib.util
import json

from packaging.specifiers import SpecifierSet
from packaging.version import Version

from vocabulary_policy import require_optional
from vocabulary_state import LOCK, inventory, is_active, package_path, read_state, write_state

# IBL 파라미터로 위조할 수 없는 프로세스 내부 권한. surface의 사용자 요청 검사만 전달한다.
HUMAN_AUTHORITY = object()


def check_ready(package_id: str) -> list:
    pkg = inventory()["packages"].get(package_id)
    if not pkg:
        return [f"보유하지 않은 묶음: {package_id}"]
    path, manifest = pkg["path"], pkg["manifest"]
    issues = []
    if not (path / "handler.py").exists():
        issues.append("handler.py가 없습니다")
    # import하지 않고 명시된 요구사항만 검사한다.
    for module in manifest.get("requires_modules", []):
        if not isinstance(module, str) or "." in module or importlib.util.find_spec(module) is None:
            issues.append(f"라이브러리 준비 필요: {module}")
    import os
    for key in manifest.get("requires_env", []):
        if not os.environ.get(key):
            issues.append(f"연결 설정 필요: {key}")
    dependencies = manifest.get("dependencies", {}) if manifest.get("format") == "iblpack" else {}
    if not isinstance(dependencies, dict):
        return issues + ["dependencies는 묶음 ID와 버전 조건의 객체여야 합니다"]
    for dep, spec in dependencies.items():
        target = inventory()["packages"].get(dep)
        if dep == package_id or not target or not is_active(dep):
            issues.append(f"의존 묶음을 먼저 준비하고 깨워 주세요: {dep}")
            continue
        td_path = target["path"] / "tool.json"
        td = json.loads(td_path.read_text()) if td_path.exists() else {}
        version = target["manifest"].get("version") or (td.get("version", "0") if isinstance(td, dict) else "0")
        if spec and Version(version) not in SpecifierSet(spec):
            issues.append(f"의존 묶음 버전 불일치: {dep} {spec}")
    return issues


def set_package_active(package_id: str, active: bool, *, authority=None, profile: str = None) -> dict:
    """보유 파일·기억을 보존하고 선택만 바꾼다. 이미 진행 중인 호출은 취소하지 않는다.

    profile='member' 면 주인 선택은 두고 **회원 프로파일의 허용**만 바꾼다(주인 활성 ∩ 회원 허용).
    주인이 잠재운 묶음은 회원에게 열 수 없다. 같은 사람 권한(HUMAN_AUTHORITY)·같은 revision 축."""
    if authority is not HUMAN_AUTHORITY:
        return {"success": False, "status": "human_required", "package_id": package_id,
                "message": "어휘 선택은 사람이 합니다. 런처의 내 어휘에서 변경해 주세요."}
    if type(active) is not bool:
        raise ValueError("active는 참/거짓이어야 합니다")
    if profile and profile != "owner":
        with LOCK:
            package_path(package_id)
            if active and not is_active(package_id):
                raise ValueError(f"'{package_id}' 은(는) 주인 선택에서 잠들어 있어 {profile} 프로파일에 열 수 없습니다")
            before = read_state()
            after = copy.deepcopy(before)
            prof = after.setdefault("profiles", {}).setdefault(profile, {}).setdefault("active", {})
            if prof.get(package_id, False) == active:
                return {"success": True, "status": "active" if active else "sleeping", "package_id": package_id,
                        "profile": profile, "active": active, "changed": False}
            prof[package_id] = active
            after["revision"] += 1
            write_state(after)
            from ibl_routing import invalidate_runtime_caches
            failures = invalidate_runtime_caches()
            if failures:
                raise RuntimeError("캐시 갱신 실패: " + ", ".join(failures))
            return {"success": True, "status": "active" if active else "sleeping", "package_id": package_id,
                    "profile": profile, "active": active, "changed": True, "revision": after["revision"]}
    with LOCK:
        package_path(package_id)
        if not active:
            require_optional(package_id)
        if is_active(package_id) == active:
            return {"success": True, "status": "active" if active else "sleeping",
                    "package_id": package_id, "active": active, "changed": False}
        if active:
            issues = check_ready(package_id)
            if issues:
                raise ValueError("; ".join(issues))
        else:
            dependents = [pid for pid, cfg in inventory()["packages"].items()
                          if is_active(pid) and cfg["manifest"].get("format") == "iblpack"
                          and package_id in cfg["manifest"].get("dependencies", {})]
            if dependents:
                raise ValueError("먼저 잠재울 의존 묶음: " + ", ".join(dependents))
        from ibl_routing import invalidate_runtime_caches
        before = read_state()
        after = copy.deepcopy(before)
        after["active"][package_id] = active
        after["revision"] += 1
        write_state(after)
        try:
            failures = invalidate_runtime_caches()
            if failures:
                raise RuntimeError("캐시 갱신 실패: " + ", ".join(failures))
        except Exception:
            # 새 revision을 유지해 이미 만들어진 회상 캐시도 재사용하지 않는다.
            restored = copy.deepcopy(before)
            restored["revision"] = after["revision"] + 1
            write_state(restored)
            failures = invalidate_runtime_caches()
            if failures:
                raise RuntimeError("원장은 복구했으나 캐시 복구 실패: " + ", ".join(failures))
            raise
        return {"success": True, "status": "active" if active else "sleeping",
                "package_id": package_id, "active": active, "changed": True,
                "revision": after["revision"], "message": "깨웠습니다" if active else "잠재웠습니다"}
