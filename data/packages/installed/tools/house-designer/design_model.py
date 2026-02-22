"""
House Designer v4 - 데이터 모델 (Facade)
설계 JSON의 생성, 로드, 저장, 수정, 검증
v4: 모듈 분할 + 면적표/물량산출 + Undo/Redo
서브모듈: design_model_rooms, design_model_elements, design_model_stairs, design_model_settings, design_transforms
"""
import json
import os
import uuid
import importlib.util
from datetime import datetime

# geometry_utils에서 공용 함수 임포트
_pkg_dir = os.path.dirname(os.path.abspath(__file__))

def _load_submodule(name):
    path = os.path.join(_pkg_dir, f"{name}.py")
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod

try:
    from geometry_utils import (
        snap, edge_key, EPS,
        room_vertices, room_to_edges, room_area, room_centroid, room_bbox,
        rooms_overlap, furniture_in_room, polygon_area, polygon_centroid,
    )
except ImportError:
    _gu = _load_submodule("geometry_utils")
    snap = _gu.snap
    edge_key = _gu.edge_key
    EPS = _gu.EPS
    room_vertices = _gu.room_vertices
    room_to_edges = _gu.room_to_edges
    room_area = _gu.room_area
    room_centroid = _gu.room_centroid
    room_bbox = _gu.room_bbox
    rooms_overlap = _gu.rooms_overlap
    furniture_in_room = _gu.furniture_in_room
    polygon_area = _gu.polygon_area
    polygon_centroid = _gu.polygon_centroid

# 하위 호환
_snap = snap
_edge_key = edge_key
_EPS = EPS

# 서브모듈 로드
_mod_rooms = _load_submodule("design_model_rooms")
_mod_elements = _load_submodule("design_model_elements")
_mod_stairs = _load_submodule("design_model_stairs")
_mod_settings = _load_submodule("design_model_settings")
_mod_transforms = _load_submodule("design_transforms")

# --- 상수 ---

ROOM_TYPE_COLORS = {
    "living": "#E8D5B7", "bedroom": "#D5E8D5", "kitchen": "#B7D5E8",
    "bathroom": "#D5B7E8", "dining": "#E8E0B7", "garage": "#D0D0D0",
    "hallway": "#F0F0E0", "closet": "#E0D8D0", "office": "#D0D8E8",
    "laundry": "#C8D8E0", "balcony": "#D8E8D0", "entrance": "#E0E0D0",
    "stairs": "#C0C0C0", "storage": "#D8D0C8", "other": "#E0E0E0",
}

FURNITURE_DEFAULTS = {
    "sofa": {"width": 2.4, "depth": 0.9, "height": 0.75, "name": "소파"},
    "bed_single": {"width": 1.0, "depth": 2.0, "height": 0.5, "name": "싱글 침대"},
    "bed_double": {"width": 1.6, "depth": 2.0, "height": 0.5, "name": "더블 침대"},
    "bed_queen": {"width": 1.5, "depth": 2.0, "height": 0.5, "name": "퀸 침대"},
    "bed_king": {"width": 1.8, "depth": 2.0, "height": 0.5, "name": "킹 침대"},
    "dining_table": {"width": 1.4, "depth": 0.9, "height": 0.75, "name": "식탁"},
    "desk": {"width": 1.2, "depth": 0.6, "height": 0.75, "name": "책상"},
    "wardrobe": {"width": 1.8, "depth": 0.6, "height": 2.0, "name": "옷장"},
    "bookshelf": {"width": 1.0, "depth": 0.3, "height": 1.8, "name": "책장"},
    "tv_stand": {"width": 1.5, "depth": 0.4, "height": 0.5, "name": "TV 스탠드"},
    "toilet": {"width": 0.4, "depth": 0.7, "height": 0.4, "name": "변기"},
    "bathtub": {"width": 0.8, "depth": 1.7, "height": 0.55, "name": "욕조"},
    "shower": {"width": 0.9, "depth": 0.9, "height": 2.1, "name": "샤워부스"},
    "sink": {"width": 0.6, "depth": 0.5, "height": 0.85, "name": "세면대"},
    "kitchen_sink": {"width": 0.8, "depth": 0.6, "height": 0.85, "name": "싱크대"},
    "stove": {"width": 0.6, "depth": 0.6, "height": 0.85, "name": "가스레인지"},
    "refrigerator": {"width": 0.8, "depth": 0.7, "height": 1.8, "name": "냉장고"},
    "washing_machine": {"width": 0.6, "depth": 0.6, "height": 0.85, "name": "세탁기"},
    "chair": {"width": 0.5, "depth": 0.5, "height": 0.45, "name": "의자"},
    "coffee_table": {"width": 1.0, "depth": 0.6, "height": 0.4, "name": "커피 테이블"},
}

DEFAULT_ROOF = {"type": "hip", "height": 2.0, "direction": "x", "overhang": 0.3, "glass_triangle": False}
DEFAULT_FACADE = {"material": "concrete", "color": "#E0DDD0"}
STAIR_DEFAULTS = _mod_stairs.STAIR_DEFAULTS
SPIRAL_DEFAULTS = _mod_stairs.SPIRAL_DEFAULTS
WINDER_DEFAULTS = _mod_stairs.WINDER_DEFAULTS
FINISH_DEFAULTS = _mod_rooms.FINISH_DEFAULTS


# --- 유틸리티 ---

def _gen_id(prefix):
    return f"{prefix}_{uuid.uuid4().hex[:8]}"


def _designs_dir(project_path):
    d = os.path.join(project_path, "outputs", "house-designs")
    os.makedirs(d, exist_ok=True)
    return d


def _design_path(project_path, design_id):
    return os.path.join(_designs_dir(project_path), f"{design_id}.json")


# --- I/O ---

def load_design(project_path, design_id):
    path = _design_path(project_path, design_id)
    if not os.path.exists(path):
        return None
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def save_design(project_path, design):
    # _history의 undo/redo 스택은 저장하지 않음 (세션 전용)
    save_data = dict(design)
    history = save_data.get("_history")
    if history:
        # 명명 스냅샷만 저장
        save_data["_history"] = {"snapshots": history.get("snapshots", {})}
    save_data["updated_at"] = datetime.now().isoformat()
    path = _design_path(project_path, save_data["id"])
    with open(path, "w", encoding="utf-8") as f:
        json.dump(save_data, f, ensure_ascii=False, indent=2)
    design["updated_at"] = save_data["updated_at"]
    return path


# --- 설계 생성 ---

def create_design(name, site_width=20, site_depth=15, floors=1, floor_height=2.8):
    design_id = f"design_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    now = datetime.now().isoformat()
    design = {
        "id": design_id,
        "name": name,
        "version": "4.0",
        "created_at": now,
        "updated_at": now,
        "units": "meters",
        "site": {"width": site_width, "depth": site_depth},
        "roof": dict(DEFAULT_ROOF),
        "facade_defaults": dict(DEFAULT_FACADE),
        "floors": [],
    }
    for i in range(floors):
        floor = _create_floor(i, floor_height)
        design["floors"].append(floor)
    return design


def _create_floor(level, height=2.8):
    return {
        "id": f"floor_{level + 1}",
        "name": f"{level + 1}층",
        "level": level,
        "height": height,
        "elevation": level * height,
        "is_piloti": False,
        "piloti_height": 3.5,
        "profile": {"offset_x": 0.0, "offset_y": 0.0},
        "rooms": [], "walls": [], "doors": [], "windows": [],
        "furniture": [], "columns": [], "beams": [], "stairs": [],
    }


def _find_floor(design, floor_id):
    for f in design["floors"]:
        if f["id"] == floor_id:
            return f
    return None


def _find_element(lst, element_id):
    for i, el in enumerate(lst):
        if el.get("id") == element_id:
            return i, el
    return -1, None


# --- 검증 ---

def _validate_dimensions(width, depth, label="요소"):
    errors = []
    if width is not None and width <= 0:
        errors.append(f"{label}의 width({width})는 양수여야 합니다.")
    if depth is not None and depth <= 0:
        errors.append(f"{label}의 depth({depth})는 양수여야 합니다.")
    return errors


def _validate_vertices(vertices):
    if not vertices or len(vertices) < 3:
        return ["다각형은 최소 3개의 꼭짓점이 필요합니다."]
    errors = []
    for i, v in enumerate(vertices):
        if not isinstance(v, (list, tuple)) or len(v) != 2:
            errors.append(f"꼭짓점 {i}: [x, y] 형식이어야 합니다.")
    area = polygon_area(vertices)
    if area < 0.01:
        errors.append("다각형 면적이 너무 작습니다 (퇴화 다각형).")
    return errors


def _check_room_overlap(floor, new_room, exclude_id=None):
    warnings = []
    for room in floor["rooms"]:
        if exclude_id and room["id"] == exclude_id:
            continue
        if rooms_overlap(new_room, room):
            warnings.append(f"방 '{new_room.get('name', '')}'이(가) '{room['name']}'과(와) 겹칩니다.")
    return warnings


def _check_furniture_in_room(floor, furn):
    room_id = furn.get("room_id")
    if not room_id:
        return None
    _, room = _find_element(floor["rooms"], room_id)
    if not room:
        return f"room_id '{room_id}'에 해당하는 방이 없습니다."
    if not furniture_in_room(furn, room):
        return f"가구 '{furn.get('name', '')}'이(가) 방 '{room['name']}' 경계를 벗어납니다."
    return None


# --- 공용 kwargs 빌더 ---

def _room_kwargs():
    return dict(_find_floor=_find_floor, _gen_id=_gen_id,
                _validate_vertices=_validate_vertices, _validate_dimensions=_validate_dimensions,
                _check_room_overlap=_check_room_overlap, snap=snap, room_area=room_area,
                ROOM_TYPE_COLORS=ROOM_TYPE_COLORS)

def _room_modify_kwargs():
    return dict(_find_floor=_find_floor, _find_element=_find_element,
                _validate_vertices=_validate_vertices, _validate_dimensions=_validate_dimensions,
                _check_room_overlap=_check_room_overlap, snap=snap, ROOM_TYPE_COLORS=ROOM_TYPE_COLORS)

def _find_kwargs():
    return dict(_find_floor=_find_floor, _find_element=_find_element)

def _gen_kwargs():
    return dict(_find_floor=_find_floor, _gen_id=_gen_id)

def _snap_kwargs():
    return dict(_find_floor=_find_floor, _gen_id=_gen_id, snap=snap)


# --- 방 CRUD (위임) ---

def add_room(design, floor_id, element):
    return _mod_rooms.add_room(design, floor_id, element, **_room_kwargs())

def remove_room(design, floor_id, element):
    return _mod_rooms.remove_room(design, floor_id, element, **_find_kwargs())

def modify_room(design, floor_id, element):
    return _mod_rooms.modify_room(design, floor_id, element, **_room_modify_kwargs())


# --- 문/창문/가구/기둥/보 CRUD (위임) ---

def add_door(design, floor_id, element):
    return _mod_elements.add_door(design, floor_id, element, **_gen_kwargs())

def remove_door(design, floor_id, element):
    return _mod_elements.remove_door(design, floor_id, element, **_find_kwargs())

def add_window(design, floor_id, element):
    return _mod_elements.add_window(design, floor_id, element, **_gen_kwargs())

def remove_window(design, floor_id, element):
    return _mod_elements.remove_window(design, floor_id, element, **_find_kwargs())

def add_furniture(design, floor_id, element):
    return _mod_elements.add_furniture(design, floor_id, element,
                                       _find_floor=_find_floor, _gen_id=_gen_id,
                                       _check_furniture_in_room=_check_furniture_in_room,
                                       snap=snap, FURNITURE_DEFAULTS=FURNITURE_DEFAULTS)

def remove_furniture(design, floor_id, element):
    return _mod_elements.remove_furniture(design, floor_id, element, **_find_kwargs())

def modify_furniture(design, floor_id, element):
    return _mod_elements.modify_furniture(design, floor_id, element,
                                          _find_floor=_find_floor, _find_element=_find_element,
                                          _check_furniture_in_room=_check_furniture_in_room, snap=snap)

def add_column(design, floor_id, element):
    return _mod_elements.add_column(design, floor_id, element, **_snap_kwargs())

def remove_column(design, floor_id, element):
    return _mod_elements.remove_column(design, floor_id, element, **_find_kwargs())

def modify_column(design, floor_id, element):
    return _mod_elements.modify_column(design, floor_id, element,
                                        _find_floor=_find_floor, _find_element=_find_element, snap=snap)

def add_beam(design, floor_id, element):
    return _mod_elements.add_beam(design, floor_id, element, **_snap_kwargs())

def remove_beam(design, floor_id, element):
    return _mod_elements.remove_beam(design, floor_id, element, **_find_kwargs())


# --- 층 CRUD ---

def add_floor(design, element):
    existing_levels = [f["level"] for f in design["floors"]]
    new_level = max(existing_levels) + 1 if existing_levels else 0
    height = element.get("height", 2.8)
    elevation = 0
    for f in design["floors"]:
        if f["level"] < new_level:
            elevation = max(elevation, f["elevation"] + f["height"])

    floor = _create_floor(new_level, height)
    floor["elevation"] = elevation
    if "id" in element:
        floor["id"] = element["id"]
    if "name" in element:
        floor["name"] = element["name"]

    design["floors"].append(floor)
    design["floors"].sort(key=lambda f: f["level"])
    return {"success": True, "message": f"'{floor['name']}' 추가됨 (높이 {elevation}m)", "floor_id": floor["id"]}


def remove_floor(design, element):
    floor_id = element.get("id")
    idx, _ = _find_element(design["floors"], floor_id)
    if idx < 0:
        return {"success": False, "error": f"층 '{floor_id}'을(를) 찾을 수 없습니다."}
    if len(design["floors"]) <= 1:
        return {"success": False, "error": "최소 1개의 층이 필요합니다."}
    removed = design["floors"].pop(idx)
    return {"success": True, "message": f"'{removed['name']}' 제거됨"}


# --- 계단 CRUD (위임) ---

def add_stairs(design, floor_id, element):
    return _mod_stairs.add_stairs(design, floor_id, element,
                                  _find_floor=_find_floor, _gen_id=_gen_id, snap=snap)

def remove_stairs(design, floor_id, element):
    return _mod_stairs.remove_stairs(design, floor_id, element, **_find_kwargs())

def modify_stairs(design, floor_id, element):
    return _mod_stairs.modify_stairs(design, floor_id, element,
                                     _find_floor=_find_floor, _find_element=_find_element, snap=snap)


# --- 설정 (위임) ---

def auto_walls(design, floor_id):
    return _mod_settings.auto_walls(design, floor_id,
                                     _find_floor=_find_floor, edge_key=edge_key,
                                     room_to_edges=room_to_edges, snap=snap,
                                     DEFAULT_FACADE=DEFAULT_FACADE)

def set_wall_material(design, floor_id, element):
    return _mod_settings.set_wall_material(design, floor_id, element, _find_floor=_find_floor)

def set_roof(design, element):
    return _mod_settings.set_roof(design, element, DEFAULT_ROOF=DEFAULT_ROOF)

def set_floor_piloti(design, floor_id, element):
    return _mod_settings.set_floor_piloti(design, floor_id, element, _find_floor=_find_floor)

def set_floor_profile(design, floor_id, element):
    return _mod_settings.set_floor_profile(design, floor_id, element, _find_floor=_find_floor, snap=snap)

def set_facade_defaults(design, element):
    return _mod_settings.set_facade_defaults(design, element, DEFAULT_FACADE=DEFAULT_FACADE)


# --- 축선/구조 (위임) ---

def set_column_grid(design, element):
    return _mod_settings.set_column_grid(design, element, snap=snap)

def auto_place_columns_on_grid(design, floor_id, element):
    return _mod_settings.auto_place_columns_on_grid(design, floor_id, element,
                                                     _find_floor=_find_floor, _gen_id=_gen_id, snap=snap)

def set_load_bearing_wall(design, floor_id, element):
    return _mod_settings.set_load_bearing_wall(design, floor_id, element, _find_floor=_find_floor)


# --- 문/창문 확장 (위임) ---

def add_window_batch(design, floor_id, element):
    return _mod_elements.add_window_batch(design, floor_id, element, **_gen_kwargs())

def validate_openings(design, floor_id):
    return _mod_elements.validate_openings(design, floor_id, _find_floor=_find_floor)


# --- 방 마감재 (위임) ---

def set_room_finishes(design, floor_id, element):
    return _mod_rooms.set_room_finishes(design, floor_id, element, **_find_kwargs())


# --- 복사/미러/배열 (위임) ---

def _transform_kwargs():
    return dict(_find_floor=_find_floor, _find_element=_find_element, _gen_id=_gen_id, snap=snap)

def copy_room(design, floor_id, element):
    return _mod_transforms.copy_room(design, floor_id, element, **_transform_kwargs())

def mirror_rooms(design, floor_id, element):
    return _mod_transforms.mirror_rooms(design, floor_id, element, **_transform_kwargs())

def array_copy(design, floor_id, element):
    return _mod_transforms.array_copy(design, floor_id, element, **_transform_kwargs())

def copy_floor(design, element):
    return _mod_transforms.copy_floor(design, element, _find_floor=_find_floor, _gen_id=_gen_id)


# --- 요약/목록 ---

def get_design_summary(design, floor_id=None):
    return _mod_settings.get_design_summary(design, floor_id,
                                             _find_floor=_find_floor, room_area=room_area)


def list_designs(project_path):
    designs_dir = _designs_dir(project_path)
    results = []
    for fname in sorted(os.listdir(designs_dir)):
        if fname.endswith(".json"):
            path = os.path.join(designs_dir, fname)
            try:
                with open(path, "r", encoding="utf-8") as f:
                    d = json.load(f)
                total_rooms = sum(len(fl["rooms"]) for fl in d.get("floors", []))
                results.append({
                    "id": d["id"], "name": d["name"],
                    "version": d.get("version", "1.0"),
                    "floors": len(d.get("floors", [])),
                    "rooms": total_rooms,
                    "created_at": d.get("created_at", ""),
                    "updated_at": d.get("updated_at", ""),
                })
            except Exception:
                pass
    return results
