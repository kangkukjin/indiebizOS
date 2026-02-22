"""
House Designer v4 - 벽 시스템 고도화
커스텀 벽 (두께 지정), 곡선 벽, 이중벽, 수동 벽 편집
"""
import math
import os
import importlib.util

_pkg_dir = os.path.dirname(os.path.abspath(__file__))


def _load(name):
    path = os.path.join(_pkg_dir, f"{name}.py")
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


# ============================================================
# 커스텀 벽 추가
# ============================================================

def add_wall(design, floor_id, element, *, _find_floor, _gen_id, snap):
    """수동으로 벽을 추가합니다.
    element:
        start: [x, y]
        end: [x, y]
        thickness: float (기본 0.2)
        type: "exterior" | "interior" (기본 "exterior")
        material: str (기본 None -> 파사드 기본값)
        color: str
        wall_type: "custom" | "curved" | "double" (기본 "custom")
        is_load_bearing: bool (기본 False)
        -- 곡선 벽용 --
        curve: {center: [x,y], radius: float, start_angle: float, end_angle: float}
        -- 이중벽용 --
        insulation: {thickness: float, material: str}
    """
    floor = _find_floor(design, floor_id)
    if not floor:
        return {"success": False, "error": f"층 '{floor_id}'을(를) 찾을 수 없습니다."}

    start = element.get("start")
    end = element.get("end")
    wall_type_mode = element.get("wall_type", "custom")

    if wall_type_mode == "curved":
        return _add_curved_wall(floor, element, _gen_id=_gen_id, snap=snap, design=design)
    elif wall_type_mode == "double":
        return _add_double_wall(floor, element, _gen_id=_gen_id, snap=snap, design=design)

    if not start or not end:
        return {"success": False, "error": "start와 end 좌표가 필요합니다."}

    thickness = element.get("thickness", 0.2)
    if thickness < 0.05:
        return {"success": False, "error": "벽 두께는 최소 0.05m입니다."}
    if thickness > 1.0:
        return {"success": False, "error": "벽 두께는 최대 1.0m입니다."}

    wall_kind = element.get("type", "exterior")
    wall_id = _gen_id("wall")

    wall = {
        "id": wall_id,
        "start": [snap(start[0]), snap(start[1])],
        "end": [snap(end[0]), snap(end[1])],
        "thickness": thickness,
        "type": wall_kind,
        "wall_type": "custom",
        "is_load_bearing": element.get("is_load_bearing", False),
    }

    # 재질
    material = element.get("material")
    if material:
        wall["material"] = material
    elif wall_kind == "exterior":
        facade = design.get("facade_defaults", {})
        wall["material"] = facade.get("material", "concrete")
        wall["color"] = facade.get("color", "#E0DDD0")

    if element.get("color"):
        wall["color"] = element["color"]

    floor["walls"].append(wall)

    length = math.hypot(end[0] - start[0], end[1] - start[1])
    return {
        "success": True,
        "wall_id": wall_id,
        "message": f"벽 '{wall_id}' 추가됨 (길이: {length:.2f}m, 두께: {thickness}m, {wall_kind})",
    }


def _add_curved_wall(floor, element, *, _gen_id, snap, design):
    """곡선(원호) 벽 추가"""
    curve = element.get("curve")
    if not curve:
        return {"success": False, "error": "곡선 벽에는 curve 데이터가 필요합니다."}

    center = curve.get("center")
    radius = curve.get("radius")
    start_angle = curve.get("start_angle", 0)
    end_angle = curve.get("end_angle", 90)

    if not center or radius is None:
        return {"success": False, "error": "curve에 center와 radius가 필요합니다."}
    if radius < 0.5:
        return {"success": False, "error": "곡선 벽 반지름은 최소 0.5m입니다."}

    thickness = element.get("thickness", 0.2)
    wall_kind = element.get("type", "exterior")
    wall_id = _gen_id("wall")

    # 원호의 시작/끝 점 계산
    sa_rad = math.radians(start_angle)
    ea_rad = math.radians(end_angle)
    sx = snap(center[0] + radius * math.cos(sa_rad))
    sy = snap(center[1] + radius * math.sin(sa_rad))
    ex = snap(center[0] + radius * math.cos(ea_rad))
    ey = snap(center[1] + radius * math.sin(ea_rad))

    wall = {
        "id": wall_id,
        "start": [sx, sy],
        "end": [ex, ey],
        "thickness": thickness,
        "type": wall_kind,
        "wall_type": "curved",
        "is_load_bearing": element.get("is_load_bearing", False),
        "curve": {
            "center": [snap(center[0]), snap(center[1])],
            "radius": radius,
            "start_angle": start_angle,
            "end_angle": end_angle,
        },
    }

    material = element.get("material")
    if material:
        wall["material"] = material
    elif wall_kind == "exterior":
        facade = design.get("facade_defaults", {})
        wall["material"] = facade.get("material", "concrete")
        wall["color"] = facade.get("color", "#E0DDD0")

    if element.get("color"):
        wall["color"] = element["color"]

    floor["walls"].append(wall)

    arc_len = radius * abs(ea_rad - sa_rad)
    return {
        "success": True,
        "wall_id": wall_id,
        "message": f"곡선 벽 '{wall_id}' 추가됨 (호 길이: {arc_len:.2f}m, 반지름: {radius}m)",
    }


def _add_double_wall(floor, element, *, _gen_id, snap, design):
    """이중벽 추가 (외장재 + 단열재 + 내장재)"""
    start = element.get("start")
    end = element.get("end")
    if not start or not end:
        return {"success": False, "error": "start와 end 좌표가 필요합니다."}

    thickness = element.get("thickness", 0.2)
    insulation = element.get("insulation", {"thickness": 0.05, "material": "insulation"})
    wall_kind = element.get("type", "exterior")
    wall_id = _gen_id("wall")

    total_thickness = thickness + insulation.get("thickness", 0.05) + 0.1  # 외벽 + 단열 + 내벽

    wall = {
        "id": wall_id,
        "start": [snap(start[0]), snap(start[1])],
        "end": [snap(end[0]), snap(end[1])],
        "thickness": total_thickness,
        "type": wall_kind,
        "wall_type": "double",
        "is_load_bearing": element.get("is_load_bearing", True),
        "insulation": {
            "thickness": insulation.get("thickness", 0.05),
            "material": insulation.get("material", "insulation"),
        },
        "outer_thickness": thickness,
        "inner_thickness": 0.1,
    }

    material = element.get("material")
    if material:
        wall["material"] = material
    elif wall_kind == "exterior":
        facade = design.get("facade_defaults", {})
        wall["material"] = facade.get("material", "concrete")
        wall["color"] = facade.get("color", "#E0DDD0")

    if element.get("color"):
        wall["color"] = element["color"]

    floor["walls"].append(wall)

    length = math.hypot(end[0] - start[0], end[1] - start[1])
    return {
        "success": True,
        "wall_id": wall_id,
        "message": f"이중벽 '{wall_id}' 추가됨 (길이: {length:.2f}m, 총 두께: {total_thickness:.2f}m)",
    }


# ============================================================
# 벽 제거
# ============================================================

def remove_wall(design, floor_id, element, *, _find_floor, _find_element):
    """벽 제거. 연결된 문/창문도 경고."""
    floor = _find_floor(design, floor_id)
    if not floor:
        return {"success": False, "error": f"층 '{floor_id}'을(를) 찾을 수 없습니다."}

    wall_id = element.get("id")
    if not wall_id:
        return {"success": False, "error": "제거할 벽의 id가 필요합니다."}

    idx, wall = _find_element(floor["walls"], wall_id)
    if idx < 0:
        return {"success": False, "error": f"벽 '{wall_id}'을(를) 찾을 수 없습니다."}

    # 연결된 문/창문 확인
    orphan_doors = [d["id"] for d in floor.get("doors", []) if d.get("wall_id") == wall_id]
    orphan_windows = [w["id"] for w in floor.get("windows", []) if w.get("wall_id") == wall_id]

    floor["walls"].pop(idx)

    msg = f"벽 '{wall_id}' 제거됨"
    if orphan_doors:
        msg += f" | 경고: 연결 끊긴 문 {len(orphan_doors)}개 ({', '.join(orphan_doors)})"
    if orphan_windows:
        msg += f" | 경고: 연결 끊긴 창문 {len(orphan_windows)}개 ({', '.join(orphan_windows)})"

    return {"success": True, "message": msg}


# ============================================================
# 벽 이동
# ============================================================

def move_wall(design, floor_id, element, *, _find_floor, _find_element, snap):
    """벽 이동 (start/end 좌표 변경)"""
    floor = _find_floor(design, floor_id)
    if not floor:
        return {"success": False, "error": f"층 '{floor_id}'을(를) 찾을 수 없습니다."}

    wall_id = element.get("id")
    idx, wall = _find_element(floor["walls"], wall_id)
    if idx < 0:
        return {"success": False, "error": f"벽 '{wall_id}'을(를) 찾을 수 없습니다."}

    new_start = element.get("start")
    new_end = element.get("end")
    dx = element.get("dx", 0)
    dy = element.get("dy", 0)

    if new_start:
        wall["start"] = [snap(new_start[0]), snap(new_start[1])]
    elif dx or dy:
        wall["start"] = [snap(wall["start"][0] + dx), snap(wall["start"][1] + dy)]

    if new_end:
        wall["end"] = [snap(new_end[0]), snap(new_end[1])]
    elif dx or dy:
        wall["end"] = [snap(wall["end"][0] + dx), snap(wall["end"][1] + dy)]

    length = math.hypot(wall["end"][0] - wall["start"][0],
                        wall["end"][1] - wall["start"][1])
    return {
        "success": True,
        "message": f"벽 '{wall_id}' 이동됨 (새 길이: {length:.2f}m)",
    }


# ============================================================
# 벽 수정
# ============================================================

def modify_wall(design, floor_id, element, *, _find_floor, _find_element, snap):
    """벽 속성 수정 (두께, 재질, 타입, 내력벽 여부 등)"""
    floor = _find_floor(design, floor_id)
    if not floor:
        return {"success": False, "error": f"층 '{floor_id}'을(를) 찾을 수 없습니다."}

    wall_id = element.get("id")
    idx, wall = _find_element(floor["walls"], wall_id)
    if idx < 0:
        return {"success": False, "error": f"벽 '{wall_id}'을(를) 찾을 수 없습니다."}

    changes = []

    if "thickness" in element:
        t = element["thickness"]
        if t < 0.05 or t > 1.0:
            return {"success": False, "error": "벽 두께는 0.05~1.0m 범위입니다."}
        wall["thickness"] = t
        changes.append(f"두께={t}m")

    if "type" in element:
        wall["type"] = element["type"]
        changes.append(f"타입={element['type']}")

    if "material" in element:
        wall["material"] = element["material"]
        changes.append(f"재질={element['material']}")

    if "color" in element:
        wall["color"] = element["color"]
        changes.append(f"색상={element['color']}")

    if "is_load_bearing" in element:
        wall["is_load_bearing"] = element["is_load_bearing"]
        changes.append(f"내력벽={'예' if element['is_load_bearing'] else '아니오'}")

    if "start" in element:
        wall["start"] = [snap(element["start"][0]), snap(element["start"][1])]
        changes.append("시작점 변경")

    if "end" in element:
        wall["end"] = [snap(element["end"][0]), snap(element["end"][1])]
        changes.append("끝점 변경")

    if "insulation" in element:
        wall["insulation"] = element["insulation"]
        changes.append(f"단열재={element['insulation'].get('material', '')}")

    if not changes:
        return {"success": False, "error": "수정할 속성이 지정되지 않았습니다."}

    return {
        "success": True,
        "message": f"벽 '{wall_id}' 수정됨: {', '.join(changes)}",
    }


# ============================================================
# 벽 분할
# ============================================================

def split_wall(design, floor_id, element, *, _find_floor, _find_element, _gen_id, snap):
    """벽을 지정 위치에서 두 개로 분할"""
    floor = _find_floor(design, floor_id)
    if not floor:
        return {"success": False, "error": f"층 '{floor_id}'을(를) 찾을 수 없습니다."}

    wall_id = element.get("id")
    idx, wall = _find_element(floor["walls"], wall_id)
    if idx < 0:
        return {"success": False, "error": f"벽 '{wall_id}'을(를) 찾을 수 없습니다."}

    # 분할 위치: position (0~1 비율) 또는 point [x, y]
    position = element.get("position", 0.5)
    split_point = element.get("point")

    sx, sy = wall["start"]
    ex, ey = wall["end"]

    if split_point:
        mx, my = snap(split_point[0]), snap(split_point[1])
    else:
        mx = snap(sx + (ex - sx) * position)
        my = snap(sy + (ey - sy) * position)

    # 첫 번째 벽 (원래 벽 수정)
    wall["end"] = [mx, my]

    # 두 번째 벽 (새로 생성)
    wall2_id = _gen_id("wall")
    wall2 = {
        "id": wall2_id,
        "start": [mx, my],
        "end": [snap(ex), snap(ey)],
        "thickness": wall.get("thickness", 0.2),
        "type": wall.get("type", "exterior"),
        "wall_type": wall.get("wall_type", "auto"),
        "is_load_bearing": wall.get("is_load_bearing", False),
    }
    if wall.get("material"):
        wall2["material"] = wall["material"]
    if wall.get("color"):
        wall2["color"] = wall["color"]

    floor["walls"].insert(idx + 1, wall2)

    return {
        "success": True,
        "wall_ids": [wall_id, wall2_id],
        "split_point": [mx, my],
        "message": f"벽 '{wall_id}'이 [{mx}, {my}]에서 분할됨 → '{wall_id}' + '{wall2_id}'",
    }


# ============================================================
# 원호 벽 기하학 헬퍼
# ============================================================

def arc_points(center, radius, start_angle, end_angle, num_segments=16):
    """원호를 따르는 점 목록 생성"""
    cx, cy = center
    sa = math.radians(start_angle)
    ea = math.radians(end_angle)
    points = []
    for i in range(num_segments + 1):
        t = sa + (ea - sa) * i / num_segments
        x = cx + radius * math.cos(t)
        y = cy + radius * math.sin(t)
        points.append((round(x, 4), round(y, 4)))
    return points


def arc_wall_polygon(center, radius, thickness, start_angle, end_angle, num_segments=16):
    """원호 벽의 외곽 다각형 생성 (내측+외측 원호)"""
    cx, cy = center
    half_t = thickness / 2
    r_outer = radius + half_t
    r_inner = radius - half_t

    outer_pts = arc_points(center, r_outer, start_angle, end_angle, num_segments)
    inner_pts = arc_points(center, r_inner, start_angle, end_angle, num_segments)
    inner_pts.reverse()

    return outer_pts + inner_pts
