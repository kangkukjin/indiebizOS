"""
House Designer v4 - 방 CRUD 모듈
방 추가/제거/수정, 겹침 검사, 가구 위치 검증, 마감재 설정
"""

# 마감재 기본값 (방 타입별)
FINISH_DEFAULTS = {
    "bedroom": {"floor_material": "wood", "wall_finish": "paint", "ceiling_finish": "paint", "ceiling_height": 2.4},
    "living_room": {"floor_material": "wood", "wall_finish": "paint", "ceiling_finish": "paint", "ceiling_height": 2.4},
    "kitchen": {"floor_material": "tile", "wall_finish": "tile", "ceiling_finish": "paint", "ceiling_height": 2.4},
    "bathroom": {"floor_material": "tile", "wall_finish": "tile", "ceiling_finish": "paint", "ceiling_height": 2.3},
    "balcony": {"floor_material": "tile", "wall_finish": "paint", "ceiling_finish": "paint", "ceiling_height": 2.4},
    "hallway": {"floor_material": "wood", "wall_finish": "paint", "ceiling_finish": "paint", "ceiling_height": 2.4},
    "storage": {"floor_material": "concrete", "wall_finish": "paint", "ceiling_finish": "paint", "ceiling_height": 2.4},
    "other": {"floor_material": "concrete", "wall_finish": "paint", "ceiling_finish": "paint", "ceiling_height": 2.4},
}


def add_room(design, floor_id, element, *, _find_floor, _gen_id, _validate_vertices,
             _validate_dimensions, _check_room_overlap, snap, room_area, ROOM_TYPE_COLORS):
    floor = _find_floor(design, floor_id)
    if not floor:
        return {"success": False, "error": f"층 '{floor_id}'을(를) 찾을 수 없습니다."}

    vertices = element.get("vertices")
    if vertices:
        vert_errors = _validate_vertices(vertices)
        if vert_errors:
            return {"success": False, "error": "; ".join(vert_errors)}
        room = {
            "id": element.get("id", _gen_id("room")),
            "name": element.get("name", "방"),
            "type": element.get("type", "other"),
            "vertices": [[snap(v[0]), snap(v[1])] for v in vertices],
            "color": element.get("color", ROOM_TYPE_COLORS.get(element.get("type", "other"), "#E0E0E0")),
        }
        area = room_area(room)
        size_desc = f"{area:.1f}m²"
    else:
        width = element.get("width", 4)
        depth = element.get("depth", 4)
        dim_errors = _validate_dimensions(width, depth, "방")
        if dim_errors:
            return {"success": False, "error": "; ".join(dim_errors)}
        room = {
            "id": element.get("id", _gen_id("room")),
            "name": element.get("name", "방"),
            "type": element.get("type", "other"),
            "x": snap(element.get("x", 0)),
            "y": snap(element.get("y", 0)),
            "width": snap(width),
            "depth": snap(depth),
            "color": element.get("color", ROOM_TYPE_COLORS.get(element.get("type", "other"), "#E0E0E0")),
        }
        size_desc = f"{room['width']}x{room['depth']}m"

    # 마감재 설정 (v4)
    _apply_finishes(room, element)

    # 발코니 타입이면 기본 난간 자동 추가
    if room.get("type") == "balcony" and "railing" not in room:
        room["railing"] = element.get("railing", {"height": 1.1, "type": "metal"})
    elif "railing" in element:
        room["railing"] = element["railing"]

    warnings = _check_room_overlap(floor, room)
    floor["rooms"].append(room)

    msg = f"방 '{room['name']}' ({size_desc}) 추가됨"
    if warnings:
        msg += f" [경고: {'; '.join(warnings)}]"
    return {"success": True, "message": msg, "room_id": room["id"], "warnings": warnings}


def remove_room(design, floor_id, element, *, _find_floor, _find_element):
    floor = _find_floor(design, floor_id)
    if not floor:
        return {"success": False, "error": f"층 '{floor_id}'을(를) 찾을 수 없습니다."}
    room_id = element.get("id")
    idx, _ = _find_element(floor["rooms"], room_id)
    if idx < 0:
        return {"success": False, "error": f"방 '{room_id}'을(를) 찾을 수 없습니다."}
    removed = floor["rooms"].pop(idx)
    floor["furniture"] = [f for f in floor["furniture"] if f.get("room_id") != room_id]
    return {"success": True, "message": f"방 '{removed['name']}' 제거됨"}


def modify_room(design, floor_id, element, *, _find_floor, _find_element,
                _validate_vertices, _validate_dimensions, _check_room_overlap,
                snap, ROOM_TYPE_COLORS):
    floor = _find_floor(design, floor_id)
    if not floor:
        return {"success": False, "error": f"층 '{floor_id}'을(를) 찾을 수 없습니다."}
    room_id = element.get("id")
    idx, room = _find_element(floor["rooms"], room_id)
    if idx < 0:
        return {"success": False, "error": f"방 '{room_id}'을(를) 찾을 수 없습니다."}

    if "vertices" in element:
        vert_errors = _validate_vertices(element["vertices"])
        if vert_errors:
            return {"success": False, "error": "; ".join(vert_errors)}
        room["vertices"] = [[snap(v[0]), snap(v[1])] for v in element["vertices"]]
        for key in ("x", "y", "width", "depth"):
            room.pop(key, None)

    if "width" in element or "depth" in element:
        w = element.get("width", room.get("width", 4))
        d = element.get("depth", room.get("depth", 4))
        dim_errors = _validate_dimensions(w, d, "방")
        if dim_errors:
            return {"success": False, "error": "; ".join(dim_errors)}

    for key in ["name", "type", "x", "y", "width", "depth", "color"]:
        if key in element:
            room[key] = snap(element[key]) if key in ("x", "y", "width", "depth") else element[key]
    if "type" in element and "color" not in element:
        room["color"] = ROOM_TYPE_COLORS.get(element["type"], room.get("color", "#E0E0E0"))

    # 마감재 수정 (v4)
    _apply_finishes(room, element, update=True)

    if "railing" in element:
        if element["railing"] is None:
            room.pop("railing", None)
        else:
            railing = room.get("railing", {})
            railing.update(element["railing"])
            room["railing"] = railing
    if element.get("type") == "balcony" and "railing" not in room:
        room["railing"] = {"height": 1.1, "type": "metal"}

    warnings = _check_room_overlap(floor, room, exclude_id=room_id)
    msg = f"방 '{room['name']}' 수정됨"
    if warnings:
        msg += f" [경고: {'; '.join(warnings)}]"
    return {"success": True, "message": msg}


# ============================================================
# 마감재 헬퍼
# ============================================================

def _apply_finishes(room, element, update=False):
    """방에 마감재 필드 적용.
    update=False: 신규 생성 시 (기본값 적용)
    update=True: 수정 시 (명시된 필드만 업데이트)
    """
    finish_keys = ["floor_material", "wall_finish", "ceiling_finish", "ceiling_height"]

    if update:
        # 수정 시: 명시된 필드만 업데이트
        for key in finish_keys:
            if key in element:
                room[key] = element[key]
    else:
        # 신규 시: element에 명시 안 된 필드는 타입 기본값 적용
        room_type = room.get("type", "other")
        defaults = FINISH_DEFAULTS.get(room_type, FINISH_DEFAULTS["other"])
        for key in finish_keys:
            room[key] = element.get(key, defaults.get(key))


def set_room_finishes(design, floor_id, element, *, _find_floor, _find_element):
    """방 마감재 일괄 설정. element: {id 또는 room_ids, floor_material?, wall_finish?, ceiling_finish?, ceiling_height?}"""
    floor = _find_floor(design, floor_id)
    if not floor:
        return {"success": False, "error": f"층 '{floor_id}'을(를) 찾을 수 없습니다."}

    room_ids = element.get("room_ids", [])
    if element.get("id"):
        room_ids = [element["id"]]

    # room_ids가 비어있으면 전체 방에 적용
    if not room_ids:
        room_ids = [r["id"] for r in floor["rooms"]]

    finish_keys = ["floor_material", "wall_finish", "ceiling_finish", "ceiling_height"]
    updates = {k: element[k] for k in finish_keys if k in element}
    if not updates:
        return {"success": False, "error": "설정할 마감재 속성이 없습니다 (floor_material, wall_finish, ceiling_finish, ceiling_height)"}

    count = 0
    for room in floor["rooms"]:
        if room["id"] in room_ids:
            for k, v in updates.items():
                room[k] = v
            count += 1

    if count == 0:
        return {"success": False, "error": "대상 방을 찾을 수 없습니다."}

    desc = ", ".join(f"{k}={v}" for k, v in updates.items())
    return {"success": True, "message": f"{count}개 방에 마감재 설정됨: {desc}"}
