"""
House Designer v4 - 면적표/물량 산출 모듈
면적 일람표, 건폐율/용적률, 벽체/창호/바닥 물량 산출
"""
import os
import importlib.util

_pkg_dir = os.path.dirname(os.path.abspath(__file__))


def _load_module(name):
    path = os.path.join(_pkg_dir, f"{name}.py")
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


_geo = _load_module("geometry_utils")
room_area = _geo.room_area
room_vertices = _geo.room_vertices


# --- 면적 일람표 ---

def generate_area_schedule(design, floor_id=None):
    """층별 방 면적표 생성.
    Returns: {floors: [{floor_id, floor_name, rooms: [{name, type, area}], subtotal}], grand_total}
    """
    result_floors = []
    grand_total = 0.0

    target_floors = design["floors"]
    if floor_id:
        target_floors = [f for f in design["floors"] if f["id"] == floor_id]
        if not target_floors:
            return {"success": False, "error": f"층 '{floor_id}'을(를) 찾을 수 없습니다."}

    for floor in target_floors:
        rooms_data = []
        subtotal = 0.0
        for room in floor.get("rooms", []):
            area = room_area(room)
            rooms_data.append({
                "id": room["id"],
                "name": room.get("name", ""),
                "type": room.get("type", "other"),
                "area": round(area, 2),
            })
            subtotal += area

        result_floors.append({
            "floor_id": floor["id"],
            "floor_name": floor.get("name", ""),
            "rooms": rooms_data,
            "subtotal": round(subtotal, 2),
        })
        grand_total += subtotal

    return {
        "success": True,
        "floors": result_floors,
        "grand_total": round(grand_total, 2),
    }


def _format_area_schedule_text(schedule):
    """면적표를 텍스트로 포맷팅"""
    lines = ["=" * 60]
    lines.append("면적표 (Area Schedule)")
    lines.append("=" * 60)
    lines.append(f"{'실명':<15} {'타입':<12} {'면적(m²)':>10}")
    lines.append("-" * 40)

    for fl in schedule["floors"]:
        lines.append(f"\n--- {fl['floor_name']} ---")
        for room in fl["rooms"]:
            lines.append(f"  {room['name']:<13} {room['type']:<12} {room['area']:>8.2f}")
        lines.append(f"  {'소계':<13} {'':12} {fl['subtotal']:>8.2f}")

    lines.append("-" * 40)
    lines.append(f"  {'총 면적':<13} {'':12} {schedule['grand_total']:>8.2f}")
    lines.append("=" * 60)
    return "\n".join(lines)


# --- 건폐율/용적률 ---

def calculate_coverage_ratio(design):
    """건폐율 계산: 1층 바닥면적 / 대지면적 x 100"""
    site = design.get("site", {})
    site_area = site.get("width", 1) * site.get("depth", 1)
    if site_area <= 0:
        return {"success": False, "error": "대지 면적이 0입니다."}

    # 1층(level=0) 바닥 면적
    ground_floor = None
    for f in design["floors"]:
        if f.get("level", 0) == 0:
            ground_floor = f
            break
    if not ground_floor:
        ground_floor = design["floors"][0] if design["floors"] else None

    if not ground_floor or not ground_floor.get("rooms"):
        return {"success": True, "coverage_ratio": 0.0, "building_area": 0.0,
                "site_area": round(site_area, 2)}

    building_area = sum(room_area(r) for r in ground_floor["rooms"])
    ratio = (building_area / site_area) * 100

    return {
        "success": True,
        "coverage_ratio": round(ratio, 2),
        "building_area": round(building_area, 2),
        "site_area": round(site_area, 2),
        "message": f"건폐율: {ratio:.2f}% (건축면적 {building_area:.2f}m² / 대지면적 {site_area:.2f}m²)",
    }


def calculate_floor_area_ratio(design):
    """용적률 계산: 연면적 / 대지면적 x 100"""
    site = design.get("site", {})
    site_area = site.get("width", 1) * site.get("depth", 1)
    if site_area <= 0:
        return {"success": False, "error": "대지 면적이 0입니다."}

    total_floor_area = 0.0
    for floor in design["floors"]:
        for room in floor.get("rooms", []):
            total_floor_area += room_area(room)

    ratio = (total_floor_area / site_area) * 100

    return {
        "success": True,
        "floor_area_ratio": round(ratio, 2),
        "total_floor_area": round(total_floor_area, 2),
        "site_area": round(site_area, 2),
        "message": f"용적률: {ratio:.2f}% (연면적 {total_floor_area:.2f}m² / 대지면적 {site_area:.2f}m²)",
    }


# --- 벽체 물량 ---

def generate_wall_schedule(design, floor_id=None):
    """벽 타입별 총 길이(m), 총 면적(m²) 산출"""
    target_floors = design["floors"]
    if floor_id:
        target_floors = [f for f in design["floors"] if f["id"] == floor_id]

    wall_stats = {}  # key: (type, material) -> {length, area, count}

    for floor in target_floors:
        floor_height = floor.get("height", 2.8)
        for wall in floor.get("walls", []):
            wtype = wall.get("type", "unknown")
            material = wall.get("material", "none")
            key = (wtype, material)

            sx, sy = wall["start"]
            ex, ey = wall["end"]
            length = ((ex - sx)**2 + (ey - sy)**2)**0.5
            area = length * floor_height
            thickness = wall.get("thickness", 0.2)

            if key not in wall_stats:
                wall_stats[key] = {"type": wtype, "material": material,
                                   "total_length": 0, "total_area": 0,
                                   "thickness": thickness, "count": 0}
            wall_stats[key]["total_length"] += length
            wall_stats[key]["total_area"] += area
            wall_stats[key]["count"] += 1

    result = []
    for key, stats in sorted(wall_stats.items()):
        result.append({
            "type": stats["type"],
            "material": stats["material"],
            "thickness": stats["thickness"],
            "count": stats["count"],
            "total_length": round(stats["total_length"], 2),
            "total_area": round(stats["total_area"], 2),
        })

    return {"success": True, "walls": result}


# --- 창호 일람표 ---

def generate_door_schedule(design):
    """문 타입별 수량, 규격 정리"""
    door_groups = {}  # key: (type, width) -> count

    for floor in design["floors"]:
        for door in floor.get("doors", []):
            dtype = door.get("type", "single")
            width = door.get("width", 0.9)
            key = (dtype, width)
            if key not in door_groups:
                door_groups[key] = {"type": dtype, "width": width,
                                    "count": 0, "ids": []}
            door_groups[key]["count"] += 1
            door_groups[key]["ids"].append(door["id"])

    result = sorted(door_groups.values(), key=lambda x: (x["type"], x["width"]))
    return {"success": True, "doors": result, "total": sum(d["count"] for d in result)}


def generate_window_schedule(design):
    """창문 타입별 수량, 규격(폭x높이) 정리"""
    win_groups = {}  # key: (width, height, sill_height) -> count

    for floor in design["floors"]:
        for win in floor.get("windows", []):
            width = win.get("width", 1.5)
            height = win.get("height", 1.2)
            sill = win.get("sill_height", 0.9)
            key = (width, height, sill)
            if key not in win_groups:
                win_groups[key] = {"width": width, "height": height,
                                   "sill_height": sill, "count": 0, "ids": []}
            win_groups[key]["count"] += 1
            win_groups[key]["ids"].append(win["id"])

    result = sorted(win_groups.values(), key=lambda x: (x["width"], x["height"]))
    return {"success": True, "windows": result, "total": sum(w["count"] for w in result)}


# --- 바닥 면적표 ---

def generate_flooring_quantities(design, floor_id=None):
    """타입별 바닥재 소요량 (방 타입 기반)"""
    target_floors = design["floors"]
    if floor_id:
        target_floors = [f for f in design["floors"] if f["id"] == floor_id]

    flooring = {}  # key: room_type -> total_area

    for floor in target_floors:
        for room in floor.get("rooms", []):
            rtype = room.get("type", "other")
            # floor_material 필드가 있으면 사용, 없으면 방 타입으로 추정
            material = room.get("floor_material", _default_flooring(rtype))
            area = room_area(room)
            if material not in flooring:
                flooring[material] = {"material": material, "total_area": 0, "rooms": []}
            flooring[material]["total_area"] += area
            flooring[material]["rooms"].append({
                "name": room.get("name", ""),
                "area": round(area, 2),
            })

    result = []
    for mat, data in sorted(flooring.items()):
        result.append({
            "material": data["material"],
            "total_area": round(data["total_area"], 2),
            "room_count": len(data["rooms"]),
        })

    return {"success": True, "flooring": result}


def _default_flooring(room_type):
    """방 타입에서 기본 바닥재 추정"""
    mapping = {
        "bathroom": "타일", "kitchen": "타일", "laundry": "타일",
        "entrance": "타일", "balcony": "타일",
        "living": "마루", "bedroom": "마루", "dining": "마루",
        "office": "마루", "closet": "마루", "storage": "마루",
        "hallway": "마루",
        "garage": "콘크리트", "stairs": "콘크리트",
    }
    return mapping.get(room_type, "마루")


# --- 종합 보고서 ---

def generate_full_report(design):
    """면적표 + 건폐율/용적률 + 벽체/창호/바닥 물량 종합 보고서"""
    lines = []
    lines.append(f"{'=' * 60}")
    lines.append(f"건축 물량 산출서 - {design.get('name', '무제')}")
    lines.append(f"설계 ID: {design.get('id', '')}")
    lines.append(f"대지: {design['site']['width']}m x {design['site']['depth']}m")
    lines.append(f"{'=' * 60}")

    # 1. 면적표
    schedule = generate_area_schedule(design)
    if schedule.get("success"):
        lines.append(_format_area_schedule_text(schedule))

    # 2. 건폐율/용적률
    lines.append("")
    coverage = calculate_coverage_ratio(design)
    if coverage.get("success"):
        lines.append(f"건폐율: {coverage['coverage_ratio']:.2f}%")
        lines.append(f"  건축면적: {coverage['building_area']:.2f}m²")

    far = calculate_floor_area_ratio(design)
    if far.get("success"):
        lines.append(f"용적률: {far['floor_area_ratio']:.2f}%")
        lines.append(f"  연면적: {far['total_floor_area']:.2f}m²")
        lines.append(f"  대지면적: {far['site_area']:.2f}m²")

    # 3. 벽체 물량
    lines.append(f"\n{'=' * 60}")
    lines.append("벽체 물량표")
    lines.append(f"{'=' * 60}")
    wall_sch = generate_wall_schedule(design)
    if wall_sch.get("success"):
        lines.append(f"{'타입':<10} {'재질':<10} {'두께(m)':>8} {'수량':>5} {'길이(m)':>10} {'면적(m²)':>10}")
        lines.append("-" * 55)
        for w in wall_sch["walls"]:
            lines.append(f"  {w['type']:<8} {w['material']:<10} {w['thickness']:>6.2f} {w['count']:>5} {w['total_length']:>8.2f} {w['total_area']:>10.2f}")

    # 4. 문 일람표
    lines.append(f"\n{'=' * 60}")
    lines.append("문 일람표")
    lines.append(f"{'=' * 60}")
    door_sch = generate_door_schedule(design)
    if door_sch.get("success"):
        lines.append(f"{'타입':<12} {'폭(m)':>8} {'수량':>5}")
        lines.append("-" * 28)
        for d in door_sch["doors"]:
            lines.append(f"  {d['type']:<10} {d['width']:>6.2f} {d['count']:>5}")
        lines.append(f"  총 문 수량: {door_sch['total']}개")

    # 5. 창문 일람표
    lines.append(f"\n{'=' * 60}")
    lines.append("창호 일람표")
    lines.append(f"{'=' * 60}")
    win_sch = generate_window_schedule(design)
    if win_sch.get("success"):
        lines.append(f"{'규격(WxH)':>12} {'하단높이(m)':>10} {'수량':>5}")
        lines.append("-" * 30)
        for w in win_sch["windows"]:
            lines.append(f"  {w['width']:.1f}x{w['height']:.1f}m   {w['sill_height']:>8.2f} {w['count']:>5}")
        lines.append(f"  총 창문 수량: {win_sch['total']}개")

    # 6. 바닥재 물량
    lines.append(f"\n{'=' * 60}")
    lines.append("바닥재 물량표")
    lines.append(f"{'=' * 60}")
    flooring = generate_flooring_quantities(design)
    if flooring.get("success"):
        lines.append(f"{'바닥재':<12} {'면적(m²)':>10} {'실 수':>5}")
        lines.append("-" * 30)
        for fl in flooring["flooring"]:
            lines.append(f"  {fl['material']:<10} {fl['total_area']:>8.2f} {fl['room_count']:>5}")

    lines.append(f"\n{'=' * 60}")
    return "\n".join(lines)


# --- 진입점 ---

def generate_report(design, report_type="full_report", floor_id=None):
    """보고서 생성 진입점"""
    handlers = {
        "area_schedule": lambda: generate_area_schedule(design, floor_id),
        "coverage_ratio": lambda: calculate_coverage_ratio(design),
        "floor_area_ratio": lambda: calculate_floor_area_ratio(design),
        "wall_schedule": lambda: generate_wall_schedule(design, floor_id),
        "door_schedule": lambda: generate_door_schedule(design),
        "window_schedule": lambda: generate_window_schedule(design),
        "flooring": lambda: generate_flooring_quantities(design, floor_id),
        "full_report": lambda: {"success": True, "report": generate_full_report(design)},
    }

    handler = handlers.get(report_type)
    if not handler:
        return {"success": False, "error": f"알 수 없는 보고서 타입: {report_type}. 사용 가능: {list(handlers.keys())}"}

    return handler()
