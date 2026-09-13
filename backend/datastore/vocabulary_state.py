"""보유 전체의 경로·소유권과 몸별 활성 선택. 폴더 위치는 최초 이관에만 쓴다."""
import copy
import json
import os
import re
import tempfile
import threading
from pathlib import Path

import yaml

def get_base_path():
    from runtime_utils import get_base_path as resolve
    return resolve()
from vocabulary_policy import load_policy, required_packages

LOCK = threading.RLock()
_inventory_cache = {}
_state_cache = {}


def valid_id(value: str) -> str:
    if not isinstance(value, str) or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]{0,127}", value):
        raise ValueError("묶음 ID 형식이 잘못되었습니다")
    return value


def inventory(root: Path = None) -> dict:
    """두 보관 폴더가 보유 정본. 내용은 import하지 않고 정의만 읽는다."""
    root = Path(root or get_base_path())
    with LOCK:
        paths = []
        for location in ("installed", "not_installed"):
            base = root / "data" / "packages" / location / "tools"
            if base.exists():
                paths.extend((p, location) for p in sorted(base.iterdir())
                             if p.is_dir() and not p.name.startswith("."))
        stamps = tuple((str(p), tuple((name, (p / name).stat().st_mtime_ns,
                                      (p / name).stat().st_size)
                                     for name in ("tool.json", "ibl_actions.yaml", "manifest.json")
                                     if (p / name).is_file())) for p, _ in paths)
        cached = _inventory_cache.get(str(root))
        if cached and cached[0] == stamps:
            return cached[1]
        packages, tools, actions = {}, {}, {}
        for path, location in paths:
            pid = valid_id(path.name)
            if pid in packages:
                raise ValueError(f"묶음 ID 충돌: {pid} (두 보관 폴더)")
            meta = json.loads((path / "manifest.json").read_text()) if (path / "manifest.json").exists() else {}
            packages[pid] = {"path": path, "initial_active": location == "installed", "manifest": meta}
            td = json.loads((path / "tool.json").read_text()) if (path / "tool.json").exists() else {}
            definitions = td if isinstance(td, list) else td.get("tools", [td] if td.get("input_schema") else [])
            for tool in definitions:
                name = tool.get("name")
                if name:
                    if name in tools and tools[name] != pid:
                        raise ValueError(f"도구 이름 충돌: {name}")
                    tools[name] = pid
            fp = path / "ibl_actions.yaml"
            if fp.exists():
                doc = yaml.safe_load(fp.read_text()) or {}
                nodes = doc.get("nodes") or {doc.get("node"): {"actions": doc.get("actions", {})}}
                for node, cfg in nodes.items():
                    for action in (cfg or {}).get("actions", {}):
                        key = f"{node}:{action}"
                        if key in actions:
                            raise ValueError(f"어휘 이름 충돌: {key}")
                        actions[key] = pid
        result = {"packages": packages, "tools": tools, "actions": actions}
        _inventory_cache[str(root)] = (stamps, result)
        return result


def state_path(root: Path = None) -> Path:
    # 데이터 경로가 몸마다 독립이다. 동기화 대상에 넣지 않는다.
    return Path(root or get_base_path()) / "data" / "vocabulary" / "activation.json"


def write_state(state: dict, root: Path = None) -> None:
    path = state_path(root)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temp = tempfile.mkstemp(prefix=".activation-", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            json.dump(state, stream, ensure_ascii=False, indent=2)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temp, path)
    finally:
        if os.path.exists(temp):
            os.unlink(temp)
    _state_cache.pop(str(path), None)


def read_state(root: Path = None) -> dict:
    with LOCK:
        path = state_path(root)
        if not path.exists():
            state = {"version": 1, "revision": 0,
                     "active": {pid: p["initial_active"] for pid, p in inventory(root)["packages"].items()}}
            # 최초 설치에서도 원본이 잠든 위치라면 분리된 자식만 깨어나지 않는다.
            for pid, spec in _split_policy(root).items():
                if spec["source"] in state["active"]:
                    state["active"].pop(pid, None)
            state = _inherit_split_selections(state, root)
            write_state(state, root)
        stamp = (path.stat().st_mtime_ns, path.stat().st_size)
        cached = _state_cache.get(str(path))
        if cached and cached[0] == stamp:
            state = cached[1]
        else:
            try:
                state = json.loads(path.read_text())
                assert state["version"] == 1 and type(state["revision"]) is int
                assert isinstance(state["active"], dict)
                assert all(type(v) is bool for v in state["active"].values())
            except (ValueError, KeyError, AssertionError, TypeError) as exc:
                raise ValueError("활성 원장이 손상되었습니다. 이전 원장을 복구해 주세요") from exc
        inherited = _inherit_split_selections(state, root)
        if inherited is not state:
            state = inherited
            write_state(state, root)
            stamp = (path.stat().st_mtime_ns, path.stat().st_size)
        _state_cache[str(path)] = (stamp, state)
        return state


def _split_policy(root: Path = None) -> dict:
    try:
        return load_policy(root).get("bundle_splits", {})
    except FileNotFoundError:
        # 이관 선언이 없는 독립 사전에서도 기존 활성 원장은 읽을 수 있다.
        # 필수어휘 보호의 정책 로딩은 완화하지 않는다.
        return {}


def _inherit_split_selections(state: dict, root: Path = None) -> dict:
    """이미 선택한 기능의 패키지 경계만 바뀐 배포를 등가 상태로 한 번 이관한다.

    정본 정책에 있는 분리만 적용한다. 외부 manifest의 자기 선언으로 활성화하지
    않으며, 새 ID에 사람의 선택이 있으면 잠듦/쓰레기통을 포함해 덮어쓰지 않는다.
    캐시 적중 때도 확인해 뒤늦게 도착한 패키지 파일을 놓치지 않는다.
    """
    splits = _split_policy(root)
    pending = {pid: spec for pid, spec in splits.items()
               if pid not in state["active"] and spec["source"] in state["active"]}
    if not pending:
        return state
    inv = inventory(root)
    result = state
    for pid, spec in pending.items():
        source = spec["source"]
        if source not in inv["packages"] or pid not in inv["packages"]:
            continue
        # 소유권이 실제로 옮겨진 완성본만 이관한다(불완전 복사/다른 묶음 제외).
        if not spec["actions"] or any(inv["actions"].get(a) != pid for a in spec["actions"]):
            continue
        if result is state:
            result = copy.deepcopy(state)
        result["active"][pid] = state["active"][source]
        desktop = result.get("desktop") or {}
        placements = desktop.get("placements", {})
        origin = placements.get(source)
        if origin:
            pos = copy.deepcopy(origin)  # 분류와 쓰레기통의 복원 목적지를 유지한다.
            occupied = [p for p in [*placements.values(), *desktop.get("folders", {}).values()]
                        if p.get("parent") == pos["parent"]]
            for index in range(len(occupied) * 25 + 1):
                x, y = 24 + index % 5 * 116, 24 + index // 5 * 116
                if all(not (x < p["x"] + 116 and x + 116 > p["x"]
                            and y < p["y"] + 136 and y + 136 > p["y"]) for p in occupied):
                    pos.update(x=x, y=y)
                    break
            placements[pid] = pos
    if result is not state:
        result["revision"] += 1
    return result


def revision(root: Path = None) -> int:
    return read_state(root)["revision"]


def is_active(package_id: str, root: Path = None) -> bool:
    with LOCK:
        if package_id in required_packages(root):
            return True
        return read_state(root)["active"].get(package_id, False)


def package_path(package_id: str, root: Path = None) -> Path:
    pkg = inventory(root)["packages"].get(valid_id(package_id))
    if not pkg:
        raise ValueError(f"보유하지 않은 묶음: {package_id}")
    return pkg["path"]


def action_owner(node: str, action: str, cfg: dict = None, root: Path = None):
    inv = inventory(root)
    return inv["actions"].get(f"{node}:{action}") or inv["tools"].get((cfg or {}).get("tool"))


def sleeping_reason(package_id: str, root: Path = None):
    if package_id and not is_active(package_id, root):
        return f"'{package_id}' 묶음의 낱말은 잠들어 있습니다. 런처의 내 어휘에서 깨워 주세요"
    return None


def action_reason(node: str, action: str, cfg: dict = None, root: Path = None):
    return sleeping_reason(action_owner(node, action, cfg, root), root)


def require_tool_active(tool: str, root: Path = None) -> None:
    with LOCK:
        owner = inventory(root)["tools"].get(tool)
        why = sleeping_reason(owner, root)
        if why:
            raise ValueError(why)


def active_paths(root: Path = None) -> list:
    return [p["path"] for pid, p in inventory(root)["packages"].items() if is_active(pid, root)]


def invalidate_inventory() -> None:
    with LOCK:
        _inventory_cache.clear()
