"""
House Designer v4 - 요소 CRUD 모듈
문, 창문, 가구, 기둥, 보 추가/제거/수정
v4.1: 좌표 기반 배치, 열림 방향, 연속 배치, 겹침 검증
"""
import math


# --- 문 CRUD ---

def add_door(design, floor_id, element, *, _find_floor, _gen_id):
    floor = _find_floor(design, floor_id)
    if not floor:
        return {"success": False, "error": f"층 '{floor_id}'을(를) 찾을 수 없습니다."}

    wall_id = element.get("wall_id")

    # v4.1: 좌표 기반 배치 — 가장 가까운 벽에 자동 스냅
    if not wall_id and element.get("x") is not None and element.get("y") is not None:
        snap_result = _snap_to_nearest_wall(floor, element["x"], element["y"])
        if not snap_result:
            return {"success": False, "error": "좌표 근처에 벽을 찾을 수 없습니다."}
        wall_id = snap_result["wall_id"]
        element["position"] = snap_result["position"]

    door = {
        "id": element.get("id", _gen_id("door")),
        "wall_id": wall_id,
        "position": element.get("position", 0),
        "width": element.get("width", 0.9),
        "type": element.get("type", "single"),
        "swing": element.get("swing", "in"),  # v4.1: 열림 방향
    }

    # v4.1: 개구부 겹침 검증
    overlap = _check_opening_overlap(floor, door["wall_id"], door["position"],
                                     door["width"])
    warning = None
    if overlap:
        warning = f"기존 개구부와 겹칩니다: {overlap}"

    floor["doors"].append(door)
    msg = f"문 추가됨 (벽 {door['wall_id']}, 위치 {door['position']}m, 열림: {door['swing']})"
    if warning:
        msg += f" [경고: {warning}]"
    return {"success": True, "message": msg, "door_id": door["id"],
            "warnings": [warning] if warning else []}


def remove_door(design, floor_id, element, *, _find_floor, _find_element):
    floor = _find_floor(design, floor_id)
    if not floor:
        return {"success": False, "error": f"층 '{floor_id}'을(를) 찾을 수 없습니다."}
    idx, _ = _find_element(floor["doors"], element.get("id"))
    if idx < 0:
        return {"success": False, "error": f"문 '{element.get('id')}'을(를) 찾을 수 없습니다."}
    floor["doors"].pop(idx)
    return {"success": True, "message": "문 제거됨"}


# --- 창문 CRUD ---

def add_window(design, floor_id, element, *, _find_floor, _gen_id):
    floor = _find_floor(design, floor_id)
    if not floor:
        return {"success": False, "error": f"층 '{floor_id}'을(를) 찾을 수 없습니다."}

    wall_id = element.get("wall_id")

    # v4.1: 좌표 기반 배치
    if not wall_id and element.get("x") is not None and element.get("y") is not None:
        snap_result = _snap_to_nearest_wall(floor, element["x"], element["y"])
        if not snap_result:
            return {"success": False, "error": "좌표 근처에 벽을 찾을 수 없습니다."}
        wall_id = snap_result["wall_id"]
        element["position"] = snap_result["position"]

    window = {
        "id": element.get("id", _gen_id("win")),
        "wall_id": wall_id,
        "position": element.get("position", 0),
        "width": element.get("width", 1.5),
        "height": element.get("height", 1.2),
        "sill_height": element.get("sill_height", 0.9),
    }

    # v4.1: 개구부 겹침 검증
    overlap = _check_opening_overlap(floor, window["wall_id"], window["position"],
                                     window["width"])
    warning = None
    if overlap:
        warning = f"기존 개구부와 겹칩니다: {overlap}"

    floor["windows"].append(window)
    msg = f"창문 추가됨 (벽 {window['wall_id']}, 폭 {window['width']}m)"
    if warning:
        msg += f" [경고: {warning}]"
    return {"success": True, "message": msg, "window_id": window["id"],
            "warnings": [warning] if warning else []}


def add_window_batch(design, floor_id, element, *, _find_floor, _gen_id):
    """v4.1: 창문 연속 배치. element: {wall_id, count, width?, height?, spacing?, start_position?}"""
    floor = _find_floor(design, floor_id)
    if not floor:
        return {"success": False, "error": f"층 '{floor_id}'을(를) 찾을 수 없습니다."}

    wall_id = element.get("wall_id")
    count = element.get("count", 3)
    width = element.get("width", 1.5)
    height = element.get("height", 1.2)
    sill_height = element.get("sill_height", 0.9)
    spacing = element.get("spacing", 0.5)  # 창문 사이 간격
    start_pos = element.get("start_position")

    # 벽 길이 계산
    wall = None
    for w in floor.get("walls", []):
        if w["id"] == wall_id:
            wall = w
            break
    if not wall:
        return {"success": False, "error": f"벽 '{wall_id}'을(를) 찾을 수 없습니다."}

    sx, sy = wall["start"]
    ex, ey = wall["end"]
    wall_len = math.hypot(ex - sx, ey - sy)

    # 시작 위치 자동 계산 (벽 중앙 정렬)
    total_w = count * width + (count - 1) * spacing
    if start_pos is None:
        start_pos = (wall_len - total_w) / 2 + width / 2

    if start_pos < width / 2:
        start_pos = width / 2

    created = []
    warnings = []
    for i in range(count):
        pos = start_pos + i * (width + spacing)
        if pos + width / 2 > wall_len:
            warnings.append(f"창문 {i+1}이 벽 범위를 초과합니다 (위치 {pos:.1f}m > 벽 길이 {wall_len:.1f}m)")
            break
        win = {
            "id": _gen_id("win"),
            "wall_id": wall_id,
            "position": round(pos, 3),
            "width": width,
            "height": height,
            "sill_height": sill_height,
        }
        floor["windows"].append(win)
        created.append(win["id"])

    msg = f"{len(created)}개 창문 연속 배치 (벽 {wall_id}, 폭 {width}m, 간격 {spacing}m)"
    if warnings:
        msg += " | " + "; ".join(warnings)
    return {"success": True, "window_ids": created, "message": msg, "warnings": warnings}


def remove_window(design, floor_id, element, *, _find_floor, _find_element):
    floor = _find_floor(design, floor_id)
    if not floor:
        return {"success": False, "error": f"층 '{floor_id}'을(를) 찾을 수 없습니다."}
    idx, _ = _find_element(floor["windows"], element.get("id"))
    if idx < 0:
        return {"success": False, "error": f"창문 '{element.get('id')}'을(를) 찾을 수 없습니다."}
    floor["windows"].pop(idx)
    return {"success": True, "message": "창문 제거됨"}


# --- 가구 CRUD ---

def add_furniture(design, floor_id, element, *, _find_floor, _gen_id, _check_furniture_in_room,
                  snap, FURNITURE_DEFAULTS):
    floor = _find_floor(design, floor_id)
    if not floor:
        return {"success": False, "error": f"층 '{floor_id}'을(를) 찾을 수 없습니다."}
    ftype = element.get("type", "other")
    defaults = FURNITURE_DEFAULTS.get(ftype, {})
    furn = {
        "id": element.get("id", _gen_id("furn")),
        "name": element.get("name", defaults.get("name", ftype)),
        "type": ftype,
        "room_id": element.get("room_id"),
        "x": snap(element.get("x", 0)),
        "y": snap(element.get("y", 0)),
        "width": element.get("width", defaults.get("width", 1.0)),
        "depth": element.get("depth", defaults.get("depth", 1.0)),
        "height": element.get("height", defaults.get("height", 0.6)),
        "rotation": element.get("rotation", 0),
    }

    warning = _check_furniture_in_room(floor, furn)
    floor["furniture"].append(furn)

    warnings = [warning] if warning else []
    msg = f"가구 '{furn['name']}' 추가됨"
    if warning:
        msg += f" [경고: {warning}]"
    return {"success": True, "message": msg, "furniture_id": furn["id"], "warnings": warnings}


def remove_furniture(design, floor_id, element, *, _find_floor, _find_element):
    floor = _find_floor(design, floor_id)
    if not floor:
        return {"success": False, "error": f"층 '{floor_id}'을(를) 찾을 수 없습니다."}
    idx, _ = _find_element(floor["furniture"], element.get("id"))
    if idx < 0:
        return {"success": False, "error": f"가구 '{element.get('id')}'을(를) 찾을 수 없습니다."}
    removed = floor["furniture"].pop(idx)
    return {"success": True, "message": f"가구 '{removed['name']}' 제거됨"}


def modify_furniture(design, floor_id, element, *, _find_floor, _find_element,
                     _check_furniture_in_room, snap):
    floor = _find_floor(design, floor_id)
    if not floor:
        return {"success": False, "error": f"층 '{floor_id}'을(를) 찾을 수 없습니다."}
    furn_id = element.get("id")
    idx, furn = _find_element(floor["furniture"], furn_id)
    if idx < 0:
        return {"success": False, "error": f"가구 '{furn_id}'을(를) 찾을 수 없습니다."}
    for key in ["name", "type", "room_id", "x", "y", "width", "depth", "height", "rotation"]:
        if key in element:
            furn[key] = snap(element[key]) if key in ("x", "y") else element[key]

    warning = _check_furniture_in_room(floor, furn)
    msg = f"가구 '{furn['name']}' 수정됨"
    if warning:
        msg += f" [경고: {warning}]"
    return {"success": True, "message": msg}


# --- 기둥 CRUD ---

def add_column(design, floor_id, element, *, _find_floor, _gen_id, snap):
    floor = _find_floor(design, floor_id)
    if not floor:
        return {"success": False, "error": f"층 '{floor_id}'을(를) 찾을 수 없습니다."}
    if "columns" not in floor:
        floor["columns"] = []

    col = {
        "id": element.get("id", _gen_id("col")),
        "x": snap(element.get("x", 0)),
        "y": snap(element.get("y", 0)),
        "width": element.get("width", 0.4),
        "depth": element.get("depth", 0.4),
        "shape": element.get("shape", "rect"),
    }
    floor["columns"].append(col)
    shape_label = "원형" if col["shape"] == "round" else "사각"
    return {
        "success": True,
        "message": f"{shape_label} 기둥 추가됨 ({col['x']}, {col['y']})",
        "column_id": col["id"],
    }


def remove_column(design, floor_id, element, *, _find_floor, _find_element):
    floor = _find_floor(design, floor_id)
    if not floor:
        return {"success": False, "error": f"층 '{floor_id}'을(를) 찾을 수 없습니다."}
    cols = floor.get("columns", [])
    idx, _ = _find_element(cols, element.get("id"))
    if idx < 0:
        return {"success": False, "error": f"기둥 '{element.get('id')}'을(를) 찾을 수 없습니다."}
    cols.pop(idx)
    return {"success": True, "message": "기둥 제거됨"}


def modify_column(design, floor_id, element, *, _find_floor, _find_element, snap):
    floor = _find_floor(design, floor_id)
    if not floor:
        return {"success": False, "error": f"층 '{floor_id}'을(를) 찾을 수 없습니다."}
    cols = floor.get("columns", [])
    idx, col = _find_element(cols, element.get("id"))
    if idx < 0:
        return {"success": False, "error": f"기둥 '{element.get('id')}'을(를) 찾을 수 없습니다."}
    for key in ["x", "y", "width", "depth", "shape"]:
        if key in element:
            col[key] = snap(element[key]) if key in ("x", "y") else element[key]
    return {"success": True, "message": f"기둥 '{col['id']}' 수정됨"}


# --- 보 CRUD ---

def add_beam(design, floor_id, element, *, _find_floor, _gen_id, snap):
    floor = _find_floor(design, floor_id)
    if not floor:
        return {"success": False, "error": f"층 '{floor_id}'을(를) 찾을 수 없습니다."}
    if "beams" not in floor:
        floor["beams"] = []

    beam = {
        "id": element.get("id", _gen_id("beam")),
        "start": [snap(element.get("start", [0, 0])[0]), snap(element.get("start", [0, 0])[1])],
        "end": [snap(element.get("end", [1, 0])[0]), snap(element.get("end", [1, 0])[1])],
        "width": element.get("width", 0.3),
        "depth": element.get("depth", 0.5),
    }
    floor["beams"].append(beam)
    length = ((beam["end"][0] - beam["start"][0])**2 + (beam["end"][1] - beam["start"][1])**2)**0.5
    return {
        "success": True,
        "message": f"보 추가됨 ({length:.1f}m)",
        "beam_id": beam["id"],
    }


def remove_beam(design, floor_id, element, *, _find_floor, _find_element):
    floor = _find_floor(design, floor_id)
    if not floor:
        return {"success": False, "error": f"층 '{floor_id}'을(를) 찾을 수 없습니다."}
    beams = floor.get("beams", [])
    idx, _ = _find_element(beams, element.get("id"))
    if idx < 0:
        return {"success": False, "error": f"보 '{element.get('id')}'을(를) 찾을 수 없습니다."}
    beams.pop(idx)
    return {"success": True, "message": "보 제거됨"}


def validate_openings(design, floor_id, element, *, _find_floor):
    """v4.1: 개구부 겹침 검증. 모든 문/창문의 겹침 검사"""
    floor = _find_floor(design, floor_id)
    if not floor:
        return {"success": False, "error": f"층 '{floor_id}'을(를) 찾을 수 없습니다."}

    issues = []
    walls = floor.get("walls", [])

    for wall in walls:
        wid = wall["id"]
        openings = []
        for d in floor.get("doors", []):
            if d.get("wall_id") == wid:
                pos = d.get("position", 0)
                hw = d.get("width", 0.9) / 2
                openings.append({"id": d["id"], "type": "문", "start": pos - hw, "end": pos + hw})
        for w in floor.get("windows", []):
            if w.get("wall_id") == wid:
                pos = w.get("position", 0)
                hw = w.get("width", 1.5) / 2
                openings.append({"id": w["id"], "type": "창문", "start": pos - hw, "end": pos + hw})

        openings.sort(key=lambda o: o["start"])
        for i in range(len(openings) - 1):
            if openings[i]["end"] > openings[i+1]["start"] + 0.01:
                issues.append(
                    f"벽 {wid}: {openings[i]['type']} {openings[i]['id']}와 "
                    f"{openings[i+1]['type']} {openings[i+1]['id']} 겹침"
                )

    if issues:
        return {"success": True, "valid": False, "issues": issues,
                "message": f"{len(issues)}개 겹침 발견"}
    return {"success": True, "valid": True, "issues": [],
            "message": "모든 개구부 정상"}


# --- v4.1: 내부 헬퍼 ---

def _snap_to_nearest_wall(floor, x, y, max_dist=1.0):
    """좌표에서 가장 가까운 벽과 해당 위치를 찾음"""
    best = None
    best_dist = max_dist

    for wall in floor.get("walls", []):
        sx, sy = wall["start"]
        ex, ey = wall["end"]
        wlen = math.hypot(ex - sx, ey - sy)
        if wlen < 0.01:
            continue

        # 점-선분 최단 거리 계산
        dx, dy = ex - sx, ey - sy
        t = max(0, min(1, ((x - sx) * dx + (y - sy) * dy) / (wlen * wlen)))
        proj_x = sx + t * dx
        proj_y = sy + t * dy
        dist = math.hypot(x - proj_x, y - proj_y)

        if dist < best_dist:
            best_dist = dist
            best = {"wall_id": wall["id"], "position": round(t * wlen, 3)}

    return best


def _check_opening_overlap(floor, wall_id, position, width):
    """해당 벽에서 개구부 겹침 확인"""
    half_w = width / 2
    new_start = position - half_w
    new_end = position + half_w

    for d in floor.get("doors", []):
        if d.get("wall_id") == wall_id:
            pos = d.get("position", 0)
            hw = d.get("width", 0.9) / 2
            if new_start < pos + hw - 0.01 and new_end > pos - hw + 0.01:
                return d["id"]

    for w in floor.get("windows", []):
        if w.get("wall_id") == wall_id:
            pos = w.get("position", 0)
            hw = w.get("width", 1.5) / 2
            if new_start < pos + hw - 0.01 and new_end > pos - hw + 0.01:
                return w["id"]

    return None
