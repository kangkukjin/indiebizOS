"""
House Designer v4 - 복사/미러/배열 변환
방, 가구, 층의 복사 및 미러/배열 복사 기능
"""
import copy


def copy_room(design, floor_id, element, *, _find_floor, _find_element, _gen_id, snap):
    """방 복사. element: {id, offset_x?, offset_y?, new_name?}"""
    floor = _find_floor(design, floor_id)
    if not floor:
        return {"success": False, "error": f"층 '{floor_id}'을(를) 찾을 수 없습니다."}

    room_id = element.get("id")
    _, room = _find_element(floor["rooms"], room_id)
    if not room:
        return {"success": False, "error": f"방 '{room_id}'을(를) 찾을 수 없습니다."}

    dx = element.get("offset_x", 0)
    dy = element.get("offset_y", 0)

    new_room = copy.deepcopy(room)
    new_room["id"] = _gen_id("room")
    new_room["name"] = element.get("new_name", f"{room['name']} (사본)")

    if "vertices" in new_room and new_room["vertices"]:
        new_room["vertices"] = [[snap(v[0] + dx), snap(v[1] + dy)]
                                for v in new_room["vertices"]]
    else:
        new_room["x"] = snap(new_room.get("x", 0) + dx)
        new_room["y"] = snap(new_room.get("y", 0) + dy)

    floor["rooms"].append(new_room)
    return {
        "success": True,
        "room_id": new_room["id"],
        "message": f"방 '{room['name']}' -> '{new_room['name']}' 복사됨 (오프셋: {dx}, {dy})",
    }


def mirror_rooms(design, floor_id, element, *, _find_floor, _find_element, _gen_id, snap):
    """방 미러 복사. element: {ids: [], axis: 'x'|'y', axis_value: float}"""
    floor = _find_floor(design, floor_id)
    if not floor:
        return {"success": False, "error": f"층 '{floor_id}'을(를) 찾을 수 없습니다."}

    room_ids = element.get("ids", [])
    axis = element.get("axis", "x")
    axis_val = element.get("axis_value", 0)

    if not room_ids:
        return {"success": False, "error": "미러할 방 ID 목록(ids)이 필요합니다."}

    mirrored = []
    for rid in room_ids:
        _, room = _find_element(floor["rooms"], rid)
        if not room:
            continue

        new_room = copy.deepcopy(room)
        new_room["id"] = _gen_id("room")
        new_room["name"] = f"{room['name']} (미러)"

        if "vertices" in new_room and new_room["vertices"]:
            new_verts = []
            for v in new_room["vertices"]:
                if axis == "x":
                    new_verts.append([snap(2 * axis_val - v[0]), snap(v[1])])
                else:
                    new_verts.append([snap(v[0]), snap(2 * axis_val - v[1])])
            # 미러 시 정점 순서 반전 (방향 유지)
            new_room["vertices"] = list(reversed(new_verts))
        else:
            if axis == "x":
                new_room["x"] = snap(2 * axis_val - new_room.get("x", 0) - new_room.get("width", 0))
            else:
                new_room["y"] = snap(2 * axis_val - new_room.get("y", 0) - new_room.get("depth", 0))

        floor["rooms"].append(new_room)
        mirrored.append(new_room["id"])

    if not mirrored:
        return {"success": False, "error": "미러할 방을 찾을 수 없습니다."}

    return {
        "success": True,
        "room_ids": mirrored,
        "message": f"{len(mirrored)}개 방 미러 복사됨 ({axis}={axis_val} 기준)",
    }


def array_copy(design, floor_id, element, *, _find_floor, _find_element, _gen_id, snap):
    """방 배열 복사. element: {id, count_x?, count_y?, spacing_x?, spacing_y?}"""
    floor = _find_floor(design, floor_id)
    if not floor:
        return {"success": False, "error": f"층 '{floor_id}'을(를) 찾을 수 없습니다."}

    room_id = element.get("id")
    _, room = _find_element(floor["rooms"], room_id)
    if not room:
        return {"success": False, "error": f"방 '{room_id}'을(를) 찾을 수 없습니다."}

    count_x = element.get("count_x", 1)
    count_y = element.get("count_y", 1)
    spacing_x = element.get("spacing_x", 0)
    spacing_y = element.get("spacing_y", 0)

    if count_x < 1 or count_y < 1:
        return {"success": False, "error": "count_x, count_y는 1 이상이어야 합니다."}

    # 방 크기 기반 기본 간격
    if spacing_x == 0:
        spacing_x = room.get("width", 4)
    if spacing_y == 0:
        spacing_y = room.get("depth", 4)

    created = []
    for ix in range(count_x):
        for iy in range(count_y):
            if ix == 0 and iy == 0:
                continue  # 원본 건너뜀

            dx = ix * spacing_x
            dy = iy * spacing_y

            new_room = copy.deepcopy(room)
            new_room["id"] = _gen_id("room")
            new_room["name"] = f"{room['name']} ({ix+1},{iy+1})"

            if "vertices" in new_room and new_room["vertices"]:
                new_room["vertices"] = [[snap(v[0] + dx), snap(v[1] + dy)]
                                        for v in new_room["vertices"]]
            else:
                new_room["x"] = snap(new_room.get("x", 0) + dx)
                new_room["y"] = snap(new_room.get("y", 0) + dy)

            floor["rooms"].append(new_room)
            created.append(new_room["id"])

    return {
        "success": True,
        "room_ids": created,
        "message": f"배열 복사: {len(created)}개 방 생성 ({count_x}x{count_y}, 간격 {spacing_x}x{spacing_y}m)",
    }


def copy_floor(design, element, *, _find_floor, _gen_id):
    """층 복사. element: {source_floor_id, target_floor_id?, new_name?}"""
    source_id = element.get("source_floor_id")
    source = _find_floor(design, source_id)
    if not source:
        return {"success": False, "error": f"원본 층 '{source_id}'을(를) 찾을 수 없습니다."}

    target_id = element.get("target_floor_id")
    if target_id:
        target = _find_floor(design, target_id)
        if not target:
            return {"success": False, "error": f"대상 층 '{target_id}'을(를) 찾을 수 없습니다."}
    else:
        # 새 층 생성
        existing_levels = [f["level"] for f in design["floors"]]
        new_level = max(existing_levels) + 1 if existing_levels else 0
        target = {
            "id": f"floor_{new_level + 1}",
            "name": element.get("new_name", f"{new_level + 1}층"),
            "level": new_level,
            "height": source.get("height", 2.8),
            "elevation": 0,
            "is_piloti": False,
            "piloti_height": 3.5,
            "profile": {"offset_x": 0.0, "offset_y": 0.0},
            "rooms": [], "walls": [], "doors": [], "windows": [],
            "furniture": [], "columns": [], "beams": [], "stairs": [],
        }
        # elevation 계산
        for f in design["floors"]:
            if f["level"] < new_level:
                target["elevation"] = max(target["elevation"],
                                          f["elevation"] + f["height"])
        design["floors"].append(target)
        design["floors"].sort(key=lambda f: f["level"])
        target_id = target["id"]

    # ID 매핑 (원본 ID -> 새 ID)
    id_map = {}

    # 방 복사
    for room in source.get("rooms", []):
        new = copy.deepcopy(room)
        new_id = _gen_id("room")
        id_map[room["id"]] = new_id
        new["id"] = new_id
        target["rooms"].append(new)

    # 벽 복사
    for wall in source.get("walls", []):
        new = copy.deepcopy(wall)
        new_id = _gen_id("wall")
        id_map[wall["id"]] = new_id
        new["id"] = new_id
        target["walls"].append(new)

    # 문 복사 (wall_id 매핑)
    for door in source.get("doors", []):
        new = copy.deepcopy(door)
        new["id"] = _gen_id("door")
        old_wall = door.get("wall_id", "")
        new["wall_id"] = id_map.get(old_wall, old_wall)
        target["doors"].append(new)

    # 창문 복사 (wall_id 매핑)
    for win in source.get("windows", []):
        new = copy.deepcopy(win)
        new["id"] = _gen_id("win")
        old_wall = win.get("wall_id", "")
        new["wall_id"] = id_map.get(old_wall, old_wall)
        target["windows"].append(new)

    # 기둥 복사
    for col in source.get("columns", []):
        new = copy.deepcopy(col)
        new["id"] = _gen_id("col")
        target["columns"].append(new)

    # 보 복사
    for beam in source.get("beams", []):
        new = copy.deepcopy(beam)
        new["id"] = _gen_id("beam")
        target["beams"].append(new)

    # 가구 복사 (room_id 매핑)
    for furn in source.get("furniture", []):
        new = copy.deepcopy(furn)
        new["id"] = _gen_id("furn")
        old_room = furn.get("room_id", "")
        if old_room:
            new["room_id"] = id_map.get(old_room, old_room)
        target["furniture"].append(new)

    total = (len(target["rooms"]) + len(target["walls"]) +
             len(target["doors"]) + len(target["windows"]) +
             len(target["columns"]) + len(target["beams"]) +
             len(target["furniture"]))
    return {
        "success": True,
        "floor_id": target_id,
        "message": f"'{source['name']}' -> '{target['name']}' 복사 완료 ({total}개 요소)",
    }
