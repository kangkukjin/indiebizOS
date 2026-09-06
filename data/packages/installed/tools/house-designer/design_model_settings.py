"""
House Designer v4 - 설정/벽/요약 모듈
벽 자동생성, 재질/지붕/필로티/프로파일/파사드 설정, 축선 시스템, 설계 요약
"""
import math


def auto_walls(design, floor_id, *, _find_floor, edge_key, room_to_edges, snap, DEFAULT_FACADE):
    """방 경계에서 벽을 자동 생성. 다각형/직사각형 통합."""
    floor = _find_floor(design, floor_id)
    if not floor:
        return {"success": False, "error": f"층 '{floor_id}'을(를) 찾을 수 없습니다."}
    if not floor["rooms"]:
        return {"success": False, "error": "방이 없어서 벽을 생성할 수 없습니다."}

    old_walls = {w["id"]: w for w in floor.get("walls", [])}

    walls = []
    wall_counter = 0
    EXT_THICK = 0.2
    INT_THICK = 0.12

    edge_set = {}
    for room in floor["rooms"]:
        edges = room_to_edges(room)
        for start, end in edges:
            key = edge_key(start, end)
            if key not in edge_set:
                edge_set[key] = 0
            edge_set[key] += 1

    new_wall_by_edge = {}
    for (start, end), count in edge_set.items():
        is_interior = count > 1
        wall_counter += 1
        wall_id = f"wall_{wall_counter}"
        wall = {
            "id": wall_id,
            "start": list(start),
            "end": list(end),
            "thickness": INT_THICK if is_interior else EXT_THICK,
            "type": "interior" if is_interior else "exterior",
        }
        if not is_interior:
            facade = design.get("facade_defaults", DEFAULT_FACADE)
            wall["material"] = facade.get("material", "concrete")
            wall["color"] = facade.get("color", "#E0DDD0")
        walls.append(wall)
        new_wall_by_edge[(start, end)] = wall_id

    # 기존 벽 -> 새 벽 ID 매핑
    old_to_new = {}
    for old_id, old_wall in old_walls.items():
        old_key = edge_key(old_wall["start"], old_wall["end"])
        if old_key in new_wall_by_edge:
            old_to_new[old_id] = new_wall_by_edge[old_key]

    # 문/창문 wall_id 마이그레이션
    migrated_doors = 0
    orphaned_doors = []
    for door in floor.get("doors", []):
        old_wid = door.get("wall_id")
        if old_wid in old_to_new:
            door["wall_id"] = old_to_new[old_wid]
            migrated_doors += 1
        elif old_wid not in {w["id"] for w in walls}:
            orphaned_doors.append(door["id"])

    migrated_windows = 0
    orphaned_windows = []
    for win in floor.get("windows", []):
        old_wid = win.get("wall_id")
        if old_wid in old_to_new:
            win["wall_id"] = old_to_new[old_wid]
            migrated_windows += 1
        elif old_wid not in {w["id"] for w in walls}:
            orphaned_windows.append(win["id"])

    floor["walls"] = walls

    ext_count = sum(1 for w in walls if w["type"] == "exterior")
    int_count = sum(1 for w in walls if w["type"] == "interior")
    msg = f"{len(walls)}개 벽 자동 생성됨 (외벽: {ext_count}, 내벽: {int_count})"
    if migrated_doors or migrated_windows:
        msg += f" | 마이그레이션: 문 {migrated_doors}개, 창문 {migrated_windows}개"
    if orphaned_doors:
        msg += f" | 경고: 연결이 끊긴 문 {len(orphaned_doors)}개 ({', '.join(orphaned_doors)})"
    if orphaned_windows:
        msg += f" | 경고: 연결이 끊긴 창문 {len(orphaned_windows)}개 ({', '.join(orphaned_windows)})"

    return {"success": True, "message": msg, "wall_ids": [w["id"] for w in walls]}


def set_wall_material(design, floor_id, element, *, _find_floor):
    """벽의 재질 설정"""
    floor = _find_floor(design, floor_id)
    if not floor:
        return {"success": False, "error": f"층 '{floor_id}'을(를) 찾을 수 없습니다."}

    wall_ids = element.get("wall_ids", [])
    if element.get("wall_id"):
        wall_ids = [element["wall_id"]]
    if not wall_ids:
        wall_type = element.get("wall_type", "exterior")
        wall_ids = [w["id"] for w in floor["walls"] if w.get("type") == wall_type]

    material = element.get("material", "concrete")
    color = element.get("color")
    count = 0
    for wall in floor["walls"]:
        if wall["id"] in wall_ids:
            wall["material"] = material
            if color:
                wall["color"] = color
            count += 1

    if count == 0:
        return {"success": False, "error": "대상 벽을 찾을 수 없습니다."}
    return {"success": True, "message": f"{count}개 벽에 '{material}' 재질 적용됨"}


def set_roof(design, element, *, DEFAULT_ROOF):
    """지붕 설정"""
    roof = design.get("roof", dict(DEFAULT_ROOF))
    valid_types = ["hip", "gable", "flat", "mansard", "gable_glass"]
    new_type = element.get("type")
    if new_type and new_type not in valid_types:
        return {"success": False, "error": f"지붕 타입은 {valid_types} 중 하나여야 합니다."}

    for key in ["type", "height", "direction", "overhang", "glass_triangle"]:
        if key in element:
            roof[key] = element[key]

    design["roof"] = roof
    return {"success": True, "message": f"지붕 설정됨: {roof['type']} (높이 {roof.get('height', 2.0)}m)"}


def set_floor_piloti(design, floor_id, element, *, _find_floor):
    """층을 필로티로 설정"""
    floor = _find_floor(design, floor_id)
    if not floor:
        return {"success": False, "error": f"층 '{floor_id}'을(를) 찾을 수 없습니다."}

    is_piloti = element.get("is_piloti", True)
    floor["is_piloti"] = is_piloti
    if "piloti_height" in element:
        floor["piloti_height"] = element["piloti_height"]
    if is_piloti and "height" in element:
        floor["height"] = element["height"]

    if is_piloti:
        return {"success": True, "message": f"'{floor['name']}' 필로티 설정됨 (높이 {floor.get('piloti_height', 3.5)}m)"}
    else:
        return {"success": True, "message": f"'{floor['name']}' 필로티 해제됨"}


def set_floor_profile(design, floor_id, element, *, _find_floor, snap):
    """층별 오프셋/프로파일 설정"""
    floor = _find_floor(design, floor_id)
    if not floor:
        return {"success": False, "error": f"층 '{floor_id}'을(를) 찾을 수 없습니다."}

    profile = floor.get("profile", {"offset_x": 0.0, "offset_y": 0.0})
    if "offset_x" in element:
        profile["offset_x"] = snap(element["offset_x"])
    if "offset_y" in element:
        profile["offset_y"] = snap(element["offset_y"])
    floor["profile"] = profile

    return {
        "success": True,
        "message": f"'{floor['name']}' 프로파일: offset ({profile['offset_x']}, {profile['offset_y']})m",
    }


def set_facade_defaults(design, element, *, DEFAULT_FACADE):
    """기본 외벽 재질 설정"""
    facade = design.get("facade_defaults", dict(DEFAULT_FACADE))
    if "material" in element:
        facade["material"] = element["material"]
    if "color" in element:
        facade["color"] = element["color"]
    design["facade_defaults"] = facade
    return {"success": True, "message": f"기본 외벽 재질: {facade['material']}"}


def get_design_summary(design, floor_id=None, *, _find_floor, room_area):
    """설계 요약 텍스트 생성"""
    lines = [f"설계: {design['name']} (ID: {design['id']}, v{design.get('version', '1.0')})"]
    lines.append(f"대지: {design['site']['width']}x{design['site']['depth']}m")
    lines.append(f"총 {len(design['floors'])}층")

    roof = design.get("roof", {})
    if roof:
        lines.append(f"지붕: {roof.get('type', 'hip')} (높이 {roof.get('height', 2.0)}m)")

    facade = design.get("facade_defaults", {})
    if facade.get("material"):
        lines.append(f"기본 외벽: {facade['material']}")

    lines.append("")

    target_floors = design["floors"]
    if floor_id:
        f = _find_floor(design, floor_id)
        if f:
            target_floors = [f]

    for floor in target_floors:
        piloti_tag = " [필로티]" if floor.get("is_piloti") else ""
        profile = floor.get("profile", {})
        profile_tag = ""
        if profile.get("offset_x") or profile.get("offset_y"):
            profile_tag = f" [오프셋: {profile.get('offset_x', 0)}, {profile.get('offset_y', 0)}m]"
        lines.append(f"=== {floor['name']} (높이: {floor['height']}m){piloti_tag}{profile_tag} ===")

        if floor["rooms"]:
            for room in floor["rooms"]:
                area = room_area(room)
                if "vertices" in room:
                    lines.append(f"  - {room['name']} ({room['type']}, ID: {room['id']}): 다각형 {len(room['vertices'])}꼭짓점 = {area:.1f}m²")
                else:
                    lines.append(f"  - {room['name']} ({room['type']}, ID: {room['id']}): {room['width']}x{room['depth']}m = {area:.1f}m²")
        else:
            lines.append("  (방 없음)")

        if floor["walls"]:
            ext = sum(1 for w in floor["walls"] if w["type"] == "exterior")
            intr = sum(1 for w in floor["walls"] if w["type"] == "interior")
            materials_used = set(w.get("material", "none") for w in floor["walls"] if w.get("material"))
            mat_str = f", 재질: {', '.join(materials_used)}" if materials_used else ""
            lines.append(f"  벽: 외벽 {ext}개, 내벽 {intr}개{mat_str}")
            for w in floor["walls"]:
                length = round(((w["end"][0]-w["start"][0])**2 + (w["end"][1]-w["start"][1])**2)**0.5, 2)
                mat_label = f", {w.get('material', '')}" if w.get("material") else ""
                lines.append(f"    {w['id']}: {w['start']}->{w['end']} ({length}m, {w['type']}{mat_label})")

        lines.append(f"  문: {len(floor['doors'])}개, 창문: {len(floor['windows'])}개")

        stairs = floor.get("stairs", [])
        if stairs:
            for st in stairs:
                lines.append(f"  계단: {st.get('name', '계단')} ({st.get('type', 'straight')}, {st.get('num_treads', 0)}단, ID: {st['id']})")

        cols = floor.get("columns", [])
        beams = floor.get("beams", [])
        if cols or beams:
            lines.append(f"  구조: 기둥 {len(cols)}개, 보 {len(beams)}개")

        if floor["furniture"]:
            lines.append(f"  가구: {', '.join(f['name'] for f in floor['furniture'])}")

        total_area = sum(room_area(r) for r in floor["rooms"])
        lines.append(f"  총 면적: {total_area:.1f}m²")
        lines.append("")

    return "\n".join(lines)


# ============================================================
# 축선(Grid Line) 시스템
# ============================================================

def set_column_grid(design, element, *, snap):
    """축선 그리드 설정.
    element: {
        x_axes: [{"label": "X1", "value": 0}, {"label": "X2", "value": 6}, ...],
        y_axes: [{"label": "Y1", "value": 0}, {"label": "Y2", "value": 4}, ...],
        origin: [x, y]  # 축선 원점 (기본 [0, 0])
    }
    간편 형식:
        x_spacings: [6, 6, 4]  → X1=0, X2=6, X3=12, X4=16
        y_spacings: [4, 4]     → Y1=0, Y2=4, Y3=8
    """
    grid = design.get("column_grid", {"x_axes": [], "y_axes": [], "origin": [0, 0]})

    if "origin" in element:
        grid["origin"] = [snap(element["origin"][0]), snap(element["origin"][1])]

    # 간편 형식 (spacing 배열)
    if "x_spacings" in element:
        spacings = element["x_spacings"]
        axes = []
        pos = 0.0
        for i, sp in enumerate(spacings):
            if i == 0:
                axes.append({"label": f"X{i+1}", "value": snap(pos)})
            pos += sp
            axes.append({"label": f"X{i+2}", "value": snap(pos)})
        if not spacings:
            axes.append({"label": "X1", "value": 0.0})
        grid["x_axes"] = axes

    if "y_spacings" in element:
        spacings = element["y_spacings"]
        axes = []
        pos = 0.0
        for i, sp in enumerate(spacings):
            if i == 0:
                axes.append({"label": f"Y{i+1}", "value": snap(pos)})
            pos += sp
            axes.append({"label": f"Y{i+2}", "value": snap(pos)})
        if not spacings:
            axes.append({"label": "Y1", "value": 0.0})
        grid["y_axes"] = axes

    # 상세 형식 (직접 축선 지정)
    if "x_axes" in element:
        grid["x_axes"] = [{"label": a["label"], "value": snap(a["value"])}
                          for a in element["x_axes"]]
    if "y_axes" in element:
        grid["y_axes"] = [{"label": a["label"], "value": snap(a["value"])}
                          for a in element["y_axes"]]

    design["column_grid"] = grid

    x_count = len(grid["x_axes"])
    y_count = len(grid["y_axes"])
    msg = f"축선 그리드 설정됨: X축 {x_count}개, Y축 {y_count}개"
    if x_count and y_count:
        msg += f" (교차점 {x_count * y_count}개)"
    return {"success": True, "message": msg, "grid": grid}


def auto_place_columns_on_grid(design, floor_id, element, *, _find_floor, _gen_id, snap):
    """축선 교차점에 기둥 자동 배치.
    element: {size?: [w, d], shape?: 'square'|'circle', material?: str, exclude_intersections?: [[xi, yj], ...]}
    """
    floor = _find_floor(design, floor_id)
    if not floor:
        return {"success": False, "error": f"층 '{floor_id}'을(를) 찾을 수 없습니다."}

    grid = design.get("column_grid")
    if not grid or not grid.get("x_axes") or not grid.get("y_axes"):
        return {"success": False, "error": "축선 그리드가 설정되지 않았습니다. set_column_grid를 먼저 실행하세요."}

    origin = grid.get("origin", [0, 0])
    ox, oy = origin[0], origin[1]
    col_size = element.get("size", [0.4, 0.4])
    col_shape = element.get("shape", "square")
    col_material = element.get("material", "concrete")
    exclude = set()
    for exc in element.get("exclude_intersections", []):
        exclude.add((str(exc[0]), str(exc[1])))

    if "columns" not in floor:
        floor["columns"] = []

    # 기존 기둥 위치 추적 (중복 방지)
    existing_positions = set()
    for col in floor["columns"]:
        pos = col.get("position", [0, 0])
        existing_positions.add((round(pos[0], 3), round(pos[1], 3)))

    created = []
    for xa in grid["x_axes"]:
        for ya in grid["y_axes"]:
            if (xa["label"], ya["label"]) in exclude:
                continue

            px = snap(ox + xa["value"])
            py = snap(oy + ya["value"])

            if (round(px, 3), round(py, 3)) in existing_positions:
                continue

            col = {
                "id": _gen_id("col"),
                "position": [px, py],
                "size": [snap(col_size[0]), snap(col_size[1])],
                "shape": col_shape,
                "material": col_material,
                "grid_label": f"{xa['label']}-{ya['label']}",
            }
            floor["columns"].append(col)
            created.append(col["id"])

    if not created:
        return {"success": True, "message": "새로 배치할 기둥이 없습니다 (모든 교차점에 이미 기둥 존재)"}

    return {
        "success": True,
        "column_ids": created,
        "message": f"축선 교차점에 {len(created)}개 기둥 자동 배치됨 ({col_shape}, {col_size[0]}x{col_size[1]}m, {col_material})",
    }


def set_load_bearing_wall(design, floor_id, element, *, _find_floor):
    """벽의 내력벽 여부 설정.
    element: {wall_ids: [], is_load_bearing: true/false}
    """
    floor = _find_floor(design, floor_id)
    if not floor:
        return {"success": False, "error": f"층 '{floor_id}'을(를) 찾을 수 없습니다."}

    wall_ids = element.get("wall_ids", [])
    if element.get("wall_id"):
        wall_ids = [element["wall_id"]]
    is_lb = element.get("is_load_bearing", True)

    count = 0
    for wall in floor.get("walls", []):
        if wall["id"] in wall_ids:
            wall["is_load_bearing"] = is_lb
            count += 1

    if count == 0:
        return {"success": False, "error": "대상 벽을 찾을 수 없습니다."}
    status = "내력벽" if is_lb else "비내력벽"
    return {"success": True, "message": f"{count}개 벽을 {status}으로 설정됨"}
