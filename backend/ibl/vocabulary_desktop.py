"""단어묶음의 몸별 데스크톱. 폴더 분류와 활성 선택은 같은 원장에 보존한다."""
import copy
import math
import uuid
from collections import Counter

import yaml

from vocabulary_state import (LOCK, action_owner, get_base_path, inventory, is_active,
                              package_path, read_state, write_state)
from vocabulary_policy import required_packages
from vocabulary_lifecycle import HUMAN_AUTHORITY, set_package_active

ROOT = "desktop"
STORE = "store"
CORE = "required"
TRASH = "trash"
SPECIAL = {STORE: "단어묶음 저장고", CORE: "필수 단어묶음", TRASH: "쓰레기통"}
GROUPS = {"sense": "자료 찾기", "engines": "콘텐츠 만들기", "limbs": "기기와 도구",
          "self": "생활과 기록", "others": "생활과 기록", "table": "콘텐츠 만들기"}
ACTION_GROUPS = {"device": "기기와 도구", "file": "기기와 도구",
                 "research": "자료 찾기", "ai": "콘텐츠 만들기", "transform": "콘텐츠 만들기"}


def _fragment(pid):
    path = package_path(pid) / "ibl_actions.yaml"
    doc = yaml.safe_load(path.read_text()) if path.exists() else {}
    return (doc or {}).get("nodes") or {(doc or {}).get("node"): {"actions": (doc or {}).get("actions", {})}}


def package_words(pid):
    """잠든 묶음도 정의는 볼 수 있다. 실행 카탈로그 필터를 우회해 핸들러를 로드하지 않는다."""
    package_path(pid)
    nodes = _fragment(pid)
    words = {f"{node}:{name}": cfg for node, meta in nodes.items()
             for name, cfg in (meta or {}).get("actions", {}).items()}
    path = get_base_path() / "data" / "ibl_nodes.yaml"
    if path.exists():
        for node, meta in (yaml.safe_load(path.read_text()) or {}).get("nodes", {}).items():
            for name, cfg in meta.get("actions", {}).items():
                owner = action_owner(node, name, cfg)
                if owner == pid or (owner is None and pid == "ibl-core"):
                    words.setdefault(f"{node}:{name}", cfg)
    return [{"name": f"[{name}]", "description": cfg.get("description", ""),
             "example": cfg.get("fixture") if isinstance(cfg.get("fixture"), str) else ""}
            for name, cfg in sorted(words.items())]


def _position(index):
    return {"x": 24 + index % 5 * 116, "y": 24 + index // 5 * 116}


def _slot(desktop, parent):
    used = {(p["x"], p["y"]) for p in [*desktop["placements"].values(), *desktop["folders"].values()]
            if p["parent"] == parent}
    index = 0
    while tuple(_position(index).values()) in used:
        index += 1
    return _position(index)


def _normal(desktop, parent):
    return parent == ROOT or (parent in desktop["folders"] and parent not in SPECIAL)


def get_desktop():
    with LOCK:
        state = copy.deepcopy(read_state())
        desktop = copy.deepcopy(state.get("desktop"))
        initial = desktop is None
        if initial:
            desktop = {"folders": {}, "placements": {}}
            for i, (fid, name) in enumerate(SPECIAL.items()):
                desktop["folders"][fid] = {"name": name, "parent": ROOT, **_position(i)}
            for i, name in enumerate(dict.fromkeys(GROUPS.values())):
                desktop["folders"][f"group-{i}"] = {"name": name, "parent": ROOT, **_position(i + 3)}
        required = required_packages()
        for pid in inventory()["packages"]:
            pos = desktop["placements"].get(pid)
            if not pos:
                parent = ROOT
                if initial and pid not in required and is_active(pid):
                    nodes = _fragment(pid)
                    roles = Counter(ACTION_GROUPS[cfg["group"]] for meta in nodes.values()
                                    for cfg in (meta or {}).get("actions", {}).values()
                                    if cfg.get("group") in ACTION_GROUPS)
                    counts = Counter({node: len((cfg or {}).get("actions", {})) for node, cfg in nodes.items()})
                    group = roles.most_common(1)[0][0] if roles else (GROUPS.get(counts.most_common(1)[0][0]) if counts else None)
                    parent = next((fid for fid, folder in desktop["folders"].items() if folder["name"] == group), ROOT)
                pos = {"parent": parent, **_slot(desktop, parent)}
            parent = pos["parent"]
            if pid in required:
                parent = CORE
            elif not is_active(pid):
                parent = TRASH if parent == TRASH else STORE
            elif not _normal(desktop, parent):
                parent = ROOT
            if parent != pos["parent"]:
                pos = {"parent": parent, **_slot(desktop, parent)}
            desktop["placements"][pid] = pos
        desktop["placements"] = {pid: pos for pid, pos in desktop["placements"].items() if pid in inventory()["packages"]}
        if desktop != state.get("desktop"):
            state["desktop"] = desktop
            write_state(state)
        return copy.deepcopy(desktop)


def _coordinates(x, y):
    if any(type(v) not in (int, float) or not math.isfinite(v) or v < 0 or v > 100000 for v in (x, y)):
        raise ValueError("아이콘 위치가 올바르지 않습니다")
    return {"x": round(x), "y": round(y)}


def _arrange_nearby(desktop, parent, columns):
    """현재 배치를 가까운 격자로 맞춘다. 고정 영역과 먼저 자리 잡은 아이콘은 피한다."""
    entries = [(key, entry) for key, entry in
               {**desktop["folders"], **desktop["placements"]}.items()
               if entry["parent"] == parent]
    # 버튼 영역(이름 포함): 폭 112, 보통 높이 최대 112, 큰 저장고는 최대 136.
    occupied = [(entry["x"], entry["y"], 112, 136 if key == STORE else 112)
                for key, entry in entries if key in SPECIAL]

    def nearest(entry):
        col = min(columns - 1, max(0, math.floor((entry["x"] - 24) / 116 + 0.5)))
        row = max(0, math.floor((entry["y"] - 24) / 116 + 0.5))
        return 24 + col * 116, 24 + row * 116

    def distance(point, entry):
        return (point[0] - entry["x"]) ** 2 + (point[1] - entry["y"]) ** 2

    # 이미 격자에 있는 아이콘의 자리를 먼저 보존한다. ID는 동률일 때만 쓴다.
    movable = sorted(((key, entry) for key, entry in entries if key not in SPECIAL),
                     key=lambda pair: (distance(nearest(pair[1]), pair[1]),
                                       pair[1]["y"], pair[1]["x"], pair[0]))
    for _, entry in movable:
        row = (nearest(entry)[1] - 24) // 116
        radius = len(entries) + 2  # 모든 이웃이 차 있어도 빈 행까지 탐색한다.
        candidates = ((24 + col * 116, 24 + r * 116)
                      for r in range(max(0, row - radius), min((100000 - 24) // 116, row + radius) + 1)
                      for col in range(columns))
        free = (point for point in candidates if not any(
            point[0] < x + w + 4 and point[0] + 116 > x
            and point[1] < y + h + 4 and point[1] + 116 > y
            for x, y, w, h in occupied))
        x, y = min(free, key=lambda point: (distance(point, entry), point[1], point[0]))
        entry.update(x=x, y=y)
        occupied.append((x, y, 112, 112))


def edit_desktop(op, *, item=None, parent=ROOT, name=None, x=24, y=24, columns=5, authority=None):
    if authority is not HUMAN_AUTHORITY:
        raise ValueError("어휘 배치는 내 어휘 화면에서 변경해 주세요")
    with LOCK:
        desktop = get_desktop()
        folders, placements = desktop["folders"], desktop["placements"]
        position = _coordinates(x, y)
        previous_active = None
        if op == "create_folder":
            if not _normal(desktop, parent):
                raise ValueError("일반 폴더나 바탕에 폴더를 만들어 주세요")
            if not isinstance(name, str) or not name.strip() or len(name) > 80:
                raise ValueError("폴더 이름은 1~80자로 적어 주세요")
            folders["folder-" + uuid.uuid4().hex] = {"name": name.strip(), "parent": parent, **position}
        elif op in ("rename", "remove_folder"):
            if item not in folders or item in SPECIAL:
                raise ValueError("특수 폴더는 이름을 바꾸거나 삭제할 수 없습니다")
            if op == "rename":
                if not isinstance(name, str) or not name.strip() or len(name) > 80:
                    raise ValueError("폴더 이름은 1~80자로 적어 주세요")
                folders[item]["name"] = name.strip()
            else:
                destination = folders[item]["parent"]
                for entry in [*placements.values(), *folders.values()]:
                    if entry["parent"] == item:
                        entry.update(parent=destination, **_slot(desktop, destination))
                del folders[item]
        elif op == "arrange":
            if parent != ROOT and parent not in folders:
                raise ValueError("폴더가 없습니다")
            if type(columns) is not int or not 1 <= columns <= 30:
                raise ValueError("정렬 열 수가 올바르지 않습니다")
            _arrange_nearby(desktop, parent, columns)
        elif op in ("move", "restore"):
            if item in (CORE, STORE):
                raise ValueError("고정 폴더는 이동할 수 없습니다")
            if item == TRASH and (op != "move" or parent != ROOT):
                raise ValueError("쓰레기통은 바탕 안에서만 옮길 수 있습니다")
            if item in folders:
                if op == "restore" or not _normal(desktop, parent):
                    raise ValueError("일반 폴더는 바탕이나 일반 폴더로 옮겨 주세요")
                ancestor = parent
                while ancestor != ROOT:
                    if ancestor == item:
                        raise ValueError("폴더를 자기 안으로 옮길 수 없습니다")
                    ancestor = folders[ancestor]["parent"]
                folders[item].update(parent=parent, **position)
            elif item in placements:
                old = placements[item]
                if op == "restore":
                    if old["parent"] != TRASH:
                        raise ValueError("쓰레기통에 있는 묶음만 복원할 수 있습니다")
                    restore = old.get("restore", {"parent": STORE})
                    parent = restore["parent"]
                    if parent not in (ROOT, STORE) and not _normal(desktop, parent):
                        parent = ROOT
                    position = _slot(desktop, parent)
                required = item in required_packages()
                if required and parent != CORE:
                    raise ValueError("필수 단어묶음은 잠재우거나 삭제할 수 없습니다")
                if not required and parent == CORE:
                    raise ValueError("필수 단어묶음 폴더는 필수 묶음 전용입니다")
                if parent not in (ROOT, STORE, TRASH, CORE) and parent not in folders:
                    raise ValueError("옮길 폴더가 없습니다")
                previous_active = is_active(item)
                desired = parent not in (STORE, TRASH)
                if desired != previous_active:
                    result = set_package_active(item, desired, authority=authority)
                    if not result["success"]:
                        raise ValueError(result["message"])
                placement = {"parent": parent, **position}
                if parent == TRASH:
                    placement["restore"] = old.get("restore", {"parent": old["parent"]})
                placements[item] = placement
            else:
                raise ValueError("아이콘이 없습니다")
        else:
            raise ValueError("지원하지 않는 데스크톱 작업입니다")
        try:
            state = copy.deepcopy(read_state())
            state["desktop"] = desktop
            write_state(state)
        except Exception:
            if previous_active is not None and is_active(item) != previous_active:
                set_package_active(item, previous_active, authority=authority)
            raise
        return get_desktop()
