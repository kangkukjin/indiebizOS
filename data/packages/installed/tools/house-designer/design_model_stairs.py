"""
House Designer v4 - 계단 CRUD 모듈
계단 추가/제거/수정 및 검증 (직선, L자, U턴, 나선형, Winder)
"""
import math

# 계단 기본값
STAIR_DEFAULTS = {
    "width": 1.0,
    "num_treads": 15,
    "tread_depth": 0.28,
    "landing_depth": 1.0,
}

# 나선형 계단 기본값
SPIRAL_DEFAULTS = {
    "radius": 1.5,           # 외부 반지름
    "inner_radius": 0.15,    # 중심 기둥 반지름
    "num_treads": 12,
    "total_angle": 360,      # 총 회전각도 (도)
    "rotation": "cw",        # 회전 방향 (cw/ccw)
}

# Winder 계단 기본값
WINDER_DEFAULTS = {
    "width": 1.0,
    "num_treads": 15,
    "tread_depth": 0.28,
    "winder_count": 3,       # 회전부 디딤판 수 (2~4)
    "turn_angle": 90,        # 회전 각도 (90 또는 180)
}


def add_stairs(design, floor_id, element, *, _find_floor, _gen_id, snap):
    """계단 추가. element: {name, type, start, direction, width, num_treads, ...}"""
    floor = _find_floor(design, floor_id)
    if not floor:
        return {"success": False, "error": f"층 '{floor_id}'을(를) 찾을 수 없습니다."}
    if "stairs" not in floor:
        floor["stairs"] = []

    stair_type = element.get("type", "straight")
    valid_types = ["straight", "l_shape", "u_turn", "spiral", "winder"]
    if stair_type not in valid_types:
        return {"success": False, "error": f"계단 타입은 {valid_types} 중 하나여야 합니다."}

    # 나선형 계단은 별도 처리
    if stair_type == "spiral":
        return _add_spiral_stairs(floor, element, _gen_id=_gen_id, snap=snap)

    # Winder 계단은 별도 처리
    if stair_type == "winder":
        return _add_winder_stairs(floor, element, _gen_id=_gen_id, snap=snap)

    width = element.get("width", STAIR_DEFAULTS["width"])
    if width < 0.8:
        return {"success": False, "error": f"계단 폭({width}m)은 최소 0.8m이어야 합니다."}

    num_treads = element.get("num_treads", STAIR_DEFAULTS["num_treads"])
    if num_treads < 3:
        return {"success": False, "error": f"디딤판 수({num_treads})는 최소 3개여야 합니다."}

    tread_depth = element.get("tread_depth", STAIR_DEFAULTS["tread_depth"])
    if tread_depth < 0.22:
        return {"success": False, "error": f"디딤판 깊이({tread_depth}m)는 최소 0.22m이어야 합니다."}

    riser_height = element.get("riser_height")
    if riser_height is None:
        floor_height = floor.get("height", 2.8)
        riser_height = round(floor_height / num_treads, 4)

    start = element.get("start", [0, 0])
    direction = element.get("direction", 0)

    stair = {
        "id": element.get("id", _gen_id("stair")),
        "name": element.get("name", "계단"),
        "type": stair_type,
        "start": [snap(start[0]), snap(start[1])],
        "direction": direction,
        "width": snap(width),
        "num_treads": num_treads,
        "tread_depth": snap(tread_depth),
        "riser_height": round(riser_height, 4),
        "landing_depth": snap(element.get("landing_depth", STAIR_DEFAULTS["landing_depth"])),
        "turn_direction": element.get("turn_direction", "right"),
        "handrail": element.get("handrail", "both"),
        "connects_to": element.get("connects_to", ""),
    }

    floor["stairs"].append(stair)

    total_rise = round(riser_height * num_treads, 2)
    total_run = round(tread_depth * num_treads, 2)
    msg = f"계단 '{stair['name']}' 추가됨 ({stair_type}, {num_treads}단, 폭 {width}m, 총 높이 {total_rise}m, 총 길이 {total_run}m)"
    return {"success": True, "message": msg, "stair_id": stair["id"]}


def remove_stairs(design, floor_id, element, *, _find_floor, _find_element):
    """계단 제거"""
    floor = _find_floor(design, floor_id)
    if not floor:
        return {"success": False, "error": f"층 '{floor_id}'을(를) 찾을 수 없습니다."}
    stairs = floor.get("stairs", [])
    idx, _ = _find_element(stairs, element.get("id"))
    if idx < 0:
        return {"success": False, "error": f"계단 '{element.get('id')}'을(를) 찾을 수 없습니다."}
    removed = stairs.pop(idx)
    return {"success": True, "message": f"계단 '{removed.get('name', '')}' 제거됨"}


def modify_stairs(design, floor_id, element, *, _find_floor, _find_element, snap):
    """계단 수정"""
    floor = _find_floor(design, floor_id)
    if not floor:
        return {"success": False, "error": f"층 '{floor_id}'을(를) 찾을 수 없습니다."}
    stairs = floor.get("stairs", [])
    idx, stair = _find_element(stairs, element.get("id"))
    if idx < 0:
        return {"success": False, "error": f"계단 '{element.get('id')}'을(를) 찾을 수 없습니다."}

    if "type" in element:
        valid_types = ["straight", "l_shape", "u_turn", "spiral", "winder"]
        if element["type"] not in valid_types:
            return {"success": False, "error": f"계단 타입은 {valid_types} 중 하나여야 합니다."}

    if "width" in element and element["width"] < 0.8:
        return {"success": False, "error": f"계단 폭({element['width']}m)은 최소 0.8m이어야 합니다."}

    if "num_treads" in element and element["num_treads"] < 3:
        return {"success": False, "error": f"디딤판 수({element['num_treads']})는 최소 3개여야 합니다."}

    if "tread_depth" in element and element["tread_depth"] < 0.22:
        return {"success": False, "error": f"디딤판 깊이({element['tread_depth']}m)는 최소 0.22m이어야 합니다."}

    snap_keys = {"width", "tread_depth", "landing_depth", "radius", "inner_radius"}
    round_keys = {"riser_height"}
    all_keys = ["name", "type", "direction", "width", "num_treads", "tread_depth",
                "riser_height", "landing_depth", "turn_direction", "handrail", "connects_to",
                "radius", "inner_radius", "total_angle", "rotation",
                "winder_count", "turn_angle"]
    for key in all_keys:
        if key in element:
            if key in snap_keys:
                stair[key] = snap(element[key])
            elif key in round_keys:
                stair[key] = round(element[key], 4)
            else:
                stair[key] = element[key]

    if "start" in element:
        stair["start"] = [snap(element["start"][0]), snap(element["start"][1])]
    if "center" in element:
        stair["center"] = [snap(element["center"][0]), snap(element["center"][1])]

    if "num_treads" in element and "riser_height" not in element:
        floor_height = floor.get("height", 2.8)
        stair["riser_height"] = round(floor_height / stair["num_treads"], 4)

    return {"success": True, "message": f"계단 '{stair['name']}' 수정됨"}


# ============================================================
# 나선형(Spiral) 계단
# ============================================================

def _add_spiral_stairs(floor, element, *, _gen_id, snap):
    """나선형 계단 추가. element: {center, radius, inner_radius, num_treads, total_angle, rotation, ...}"""
    center = element.get("center", element.get("start", [0, 0]))
    radius = element.get("radius", SPIRAL_DEFAULTS["radius"])
    inner_radius = element.get("inner_radius", SPIRAL_DEFAULTS["inner_radius"])
    num_treads = element.get("num_treads", SPIRAL_DEFAULTS["num_treads"])
    total_angle = element.get("total_angle", SPIRAL_DEFAULTS["total_angle"])
    rotation = element.get("rotation", SPIRAL_DEFAULTS["rotation"])

    if radius < 0.8:
        return {"success": False, "error": f"나선형 계단 반지름({radius}m)은 최소 0.8m이어야 합니다."}
    if inner_radius >= radius:
        return {"success": False, "error": "중심 기둥 반지름은 외부 반지름보다 작아야 합니다."}
    if num_treads < 4:
        return {"success": False, "error": f"나선형 계단 디딤판 수({num_treads})는 최소 4개여야 합니다."}
    if total_angle < 90 or total_angle > 720:
        return {"success": False, "error": f"총 회전각도({total_angle}°)는 90°~720° 범위여야 합니다."}

    # 챌판 높이 자동 계산
    riser_height = element.get("riser_height")
    if riser_height is None:
        floor_height = floor.get("height", 2.8)
        riser_height = round(floor_height / num_treads, 4)

    # 최소 디딤판 폭 검증 (내측)
    angle_per_tread = math.radians(total_angle / num_treads)
    inner_tread_width = inner_radius * angle_per_tread
    if inner_tread_width < 0.05:
        pass  # 중심부는 좁아도 허용 (기둥에 가까움)
    outer_tread_width = radius * angle_per_tread
    if outer_tread_width < 0.22:
        return {"success": False, "error": f"외측 디딤판 폭({outer_tread_width:.2f}m)이 너무 좁습니다. 반지름을 늘리거나 디딤판 수를 줄이세요."}

    stair = {
        "id": element.get("id", _gen_id("stair")),
        "name": element.get("name", "나선형 계단"),
        "type": "spiral",
        "center": [snap(center[0]), snap(center[1])],
        "start": [snap(center[0]), snap(center[1])],  # 호환용
        "direction": element.get("direction", 0),
        "radius": snap(radius),
        "inner_radius": snap(inner_radius),
        "num_treads": num_treads,
        "total_angle": total_angle,
        "rotation": rotation,
        "riser_height": round(riser_height, 4),
        "handrail": element.get("handrail", "outer"),
        "connects_to": element.get("connects_to", ""),
    }

    floor["stairs"].append(stair)

    total_rise = round(riser_height * num_treads, 2)
    msg = (f"나선형 계단 '{stair['name']}' 추가됨 "
           f"(반지름 {radius}m, {num_treads}단, {total_angle}° {rotation}, 총 높이 {total_rise}m)")
    return {"success": True, "message": msg, "stair_id": stair["id"]}


# ============================================================
# Winder(부채꼴) 계단
# ============================================================

def _add_winder_stairs(floor, element, *, _gen_id, snap):
    """Winder 계단 추가. 랜딩 없이 부채꼴 디딤판으로 방향 전환.
    element: {start, direction, width, num_treads, winder_count, turn_angle, turn_direction, ...}
    """
    width = element.get("width", WINDER_DEFAULTS["width"])
    if width < 0.8:
        return {"success": False, "error": f"계단 폭({width}m)은 최소 0.8m이어야 합니다."}

    num_treads = element.get("num_treads", WINDER_DEFAULTS["num_treads"])
    if num_treads < 5:
        return {"success": False, "error": f"Winder 계단 디딤판 수({num_treads})는 최소 5개여야 합니다."}

    winder_count = element.get("winder_count", WINDER_DEFAULTS["winder_count"])
    if winder_count < 2 or winder_count > 4:
        return {"success": False, "error": f"Winder 디딤판 수({winder_count})는 2~4개여야 합니다."}

    turn_angle = element.get("turn_angle", WINDER_DEFAULTS["turn_angle"])
    if turn_angle not in (90, 180):
        return {"success": False, "error": "Winder 회전 각도는 90° 또는 180°만 지원합니다."}

    tread_depth = element.get("tread_depth", WINDER_DEFAULTS["tread_depth"])
    if tread_depth < 0.22:
        return {"success": False, "error": f"디딤판 깊이({tread_depth}m)는 최소 0.22m이어야 합니다."}

    # 챌판 높이 자동 계산
    riser_height = element.get("riser_height")
    if riser_height is None:
        floor_height = floor.get("height", 2.8)
        riser_height = round(floor_height / num_treads, 4)

    start = element.get("start", [0, 0])
    direction = element.get("direction", 0)

    # 직선부 디딤판 수 계산 (winder 전후 균등 분배)
    straight_treads = num_treads - winder_count
    treads_before = straight_treads // 2
    treads_after = straight_treads - treads_before

    stair = {
        "id": element.get("id", _gen_id("stair")),
        "name": element.get("name", "Winder 계단"),
        "type": "winder",
        "start": [snap(start[0]), snap(start[1])],
        "direction": direction,
        "width": snap(width),
        "num_treads": num_treads,
        "tread_depth": snap(tread_depth),
        "riser_height": round(riser_height, 4),
        "winder_count": winder_count,
        "turn_angle": turn_angle,
        "turn_direction": element.get("turn_direction", "right"),
        "treads_before": treads_before,
        "treads_after": treads_after,
        "handrail": element.get("handrail", "both"),
        "connects_to": element.get("connects_to", ""),
    }

    floor["stairs"].append(stair)

    total_rise = round(riser_height * num_treads, 2)
    total_run = round(tread_depth * straight_treads, 2)
    msg = (f"Winder 계단 '{stair['name']}' 추가됨 "
           f"({num_treads}단, Winder {winder_count}단, {turn_angle}° 회전, 총 높이 {total_rise}m)")
    return {"success": True, "message": msg, "stair_id": stair["id"]}
