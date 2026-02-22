"""
House Designer v4 - 핸들러 (진입점)
도구 호출을 적절한 모듈로 디스패치
v4: 물량 산출, Undo/Redo, 스냅샷 지원
"""
import json
import os
import sys
import importlib

_pkg_dir = os.path.dirname(os.path.abspath(__file__))


def _load_module(name):
    path = os.path.join(_pkg_dir, f"{name}.py")
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def execute(tool_name: str, params: dict, project_path: str = None) -> str:
    try:
        if tool_name == "create_house_design":
            return _create(params, project_path)
        elif tool_name == "modify_house_design":
            return _modify(params, project_path)
        elif tool_name == "get_house_design":
            return _get(params, project_path)
        elif tool_name == "generate_floor_plan":
            return _floor_plan(params, project_path)
        elif tool_name == "generate_3d_view":
            return _3d_view(params, project_path)
        elif tool_name == "list_house_designs":
            return _list(params, project_path)
        elif tool_name == "generate_quantity_report":
            return _quantity_report(params, project_path)
        elif tool_name == "generate_section_view":
            return _section_view(params, project_path)
        elif tool_name == "generate_elevation_view":
            return _elevation_view(params, project_path)
        elif tool_name == "export_drawing":
            return _export_drawing(params, project_path)
        else:
            return json.dumps({"success": False, "error": f"Unknown tool: {tool_name}"}, ensure_ascii=False)
    except Exception as e:
        return json.dumps({"success": False, "error": str(e)}, ensure_ascii=False)


def _create(params, project_path):
    model = _load_module("design_model")
    design = model.create_design(
        name=params.get("name", "새 설계"),
        site_width=params.get("site_width", 20),
        site_depth=params.get("site_depth", 15),
        floors=params.get("floors", 1),
        floor_height=params.get("floor_height", 2.8),
    )
    path = model.save_design(project_path, design)
    return json.dumps({
        "success": True,
        "design_id": design["id"],
        "name": design["name"],
        "version": design.get("version", "4.0"),
        "floors": len(design["floors"]),
        "site": design["site"],
        "roof": design.get("roof", {}),
        "path": os.path.abspath(path),
        "message": f"설계 '{design['name']}' 생성됨 (ID: {design['id']}, {len(design['floors'])}층, 대지 {design['site']['width']}x{design['site']['depth']}m)",
    }, ensure_ascii=False)


def _modify(params, project_path):
    model = _load_module("design_model")
    history = _load_module("design_history")

    design_id = params.get("design_id")
    if not design_id:
        return json.dumps({"success": False, "error": "design_id가 필요합니다."}, ensure_ascii=False)

    design = model.load_design(project_path, design_id)
    if not design:
        return json.dumps({"success": False, "error": f"설계 '{design_id}'을(를) 찾을 수 없습니다."}, ensure_ascii=False)

    action = params.get("action")
    floor_id = params.get("floor_id", "floor_1")
    element = params.get("element", {})

    # Undo/Redo/스냅샷 전용 action (상태 변경 전 push 불필요)
    history_actions = {
        "undo": lambda: history.undo(design),
        "redo": lambda: history.redo(design),
        "create_snapshot": lambda: history.create_snapshot(design, element.get("name", "")),
        "restore_snapshot": lambda: history.restore_snapshot(design, element.get("name", "")),
        "list_history": lambda: history.list_history(design),
        "compare_snapshots": lambda: history.compare_snapshots(
            design, element.get("name_a", ""), element.get("name_b", "")),
    }

    if action in history_actions:
        result = history_actions[action]()
        if result.get("success") and action in ("undo", "redo", "restore_snapshot"):
            model.save_design(project_path, design)
        return json.dumps(result, ensure_ascii=False)

    # 일반 수정 action
    action_map = {
        # 방 CRUD
        "add_room": lambda: model.add_room(design, floor_id, element),
        "remove_room": lambda: model.remove_room(design, floor_id, element),
        "modify_room": lambda: model.modify_room(design, floor_id, element),
        # 문/창문
        "add_door": lambda: model.add_door(design, floor_id, element),
        "remove_door": lambda: model.remove_door(design, floor_id, element),
        "add_window": lambda: model.add_window(design, floor_id, element),
        "remove_window": lambda: model.remove_window(design, floor_id, element),
        # 가구
        "add_furniture": lambda: model.add_furniture(design, floor_id, element),
        "remove_furniture": lambda: model.remove_furniture(design, floor_id, element),
        "modify_furniture": lambda: model.modify_furniture(design, floor_id, element),
        # 층
        "add_floor": lambda: model.add_floor(design, element),
        "remove_floor": lambda: model.remove_floor(design, element),
        # 벽
        "auto_walls": lambda: model.auto_walls(design, floor_id),
        "add_wall": lambda: _wall_action("add_wall", design, floor_id, element),
        "remove_wall": lambda: _wall_action("remove_wall", design, floor_id, element),
        "move_wall": lambda: _wall_action("move_wall", design, floor_id, element),
        "modify_wall": lambda: _wall_action("modify_wall", design, floor_id, element),
        "split_wall": lambda: _wall_action("split_wall", design, floor_id, element),
        # 구조 요소
        "add_column": lambda: model.add_column(design, floor_id, element),
        "remove_column": lambda: model.remove_column(design, floor_id, element),
        "modify_column": lambda: model.modify_column(design, floor_id, element),
        "add_beam": lambda: model.add_beam(design, floor_id, element),
        "remove_beam": lambda: model.remove_beam(design, floor_id, element),
        # 계단
        "add_stairs": lambda: model.add_stairs(design, floor_id, element),
        "remove_stairs": lambda: model.remove_stairs(design, floor_id, element),
        "modify_stairs": lambda: model.modify_stairs(design, floor_id, element),
        # 설정
        "set_wall_material": lambda: model.set_wall_material(design, floor_id, element),
        "set_roof": lambda: model.set_roof(design, element),
        "set_floor_piloti": lambda: model.set_floor_piloti(design, floor_id, element),
        "set_floor_profile": lambda: model.set_floor_profile(design, floor_id, element),
        "set_facade_defaults": lambda: model.set_facade_defaults(design, element),
        # 치수선
        "add_dimension": lambda: _add_dimension(design, floor_id, element),
        "remove_dimension": lambda: _remove_dimension(design, floor_id, element),
        # 프로젝트 정보
        "set_project_info": lambda: _set_project_info(design, element),
        # 레이어
        "get_layers": lambda: _layer_action("get_layers", design, element),
        "set_layer_visibility": lambda: _layer_action("set_layer_visibility", design, element),
        "set_layer_style": lambda: _layer_action("set_layer_style", design, element),
        "apply_layer_preset": lambda: _layer_action("apply_layer_preset", design, element),
        # === Phase 5 신규 ===
        # 문/창문 확장
        "add_window_batch": lambda: model.add_window_batch(design, floor_id, element),
        "validate_openings": lambda: model.validate_openings(design, floor_id),
        # 축선/구조
        "set_column_grid": lambda: model.set_column_grid(design, element),
        "auto_place_columns_on_grid": lambda: model.auto_place_columns_on_grid(design, floor_id, element),
        "set_load_bearing_wall": lambda: model.set_load_bearing_wall(design, floor_id, element),
        # 방 마감재
        "set_room_finishes": lambda: model.set_room_finishes(design, floor_id, element),
        # 복사/미러/배열
        "copy_room": lambda: model.copy_room(design, floor_id, element),
        "mirror_rooms": lambda: model.mirror_rooms(design, floor_id, element),
        "array_copy": lambda: model.array_copy(design, floor_id, element),
        "copy_floor": lambda: model.copy_floor(design, element),
    }

    if action not in action_map:
        return json.dumps({"success": False, "error": f"알 수 없는 action: {action}"}, ensure_ascii=False)

    # 변경 전 상태 저장 (Undo용)
    history.push_state(design, action)

    result = action_map[action]()

    if result.get("success"):
        model.save_design(project_path, design)

    return json.dumps(result, ensure_ascii=False)


def _get(params, project_path):
    model = _load_module("design_model")
    design_id = params.get("design_id")
    if not design_id:
        return json.dumps({"success": False, "error": "design_id가 필요합니다."}, ensure_ascii=False)

    design = model.load_design(project_path, design_id)
    if not design:
        return json.dumps({"success": False, "error": f"설계 '{design_id}'을(를) 찾을 수 없습니다."}, ensure_ascii=False)

    if params.get("summary", False):
        summary = model.get_design_summary(design, params.get("floor_id"))
        return json.dumps({"success": True, "summary": summary}, ensure_ascii=False)

    floor_id = params.get("floor_id")
    if floor_id:
        floor = model._find_floor(design, floor_id)
        if not floor:
            return json.dumps({"success": False, "error": f"층 '{floor_id}'을(를) 찾을 수 없습니다."}, ensure_ascii=False)
        return json.dumps({"success": True, "floor": floor}, ensure_ascii=False)

    return json.dumps({"success": True, "design": design}, ensure_ascii=False)


def _floor_plan(params, project_path):
    model = _load_module("design_model")
    renderer = _load_module("renderer_2d")

    design_id = params.get("design_id")
    if not design_id:
        return json.dumps({"success": False, "error": "design_id가 필요합니다."}, ensure_ascii=False)

    design = model.load_design(project_path, design_id)
    if not design:
        return json.dumps({"success": False, "error": f"설계 '{design_id}'을(를) 찾을 수 없습니다."}, ensure_ascii=False)

    floor_id = params.get("floor_id", "floor_1")
    output_dir = os.path.join(project_path, "outputs", "house-designs")
    os.makedirs(output_dir, exist_ok=True)
    output_path = os.path.join(output_dir, f"{design_id}_{floor_id}_plan.png")

    result = renderer.render_floor_plan(
        design=design,
        floor_id=floor_id,
        output_path=output_path,
        show_dimensions=params.get("show_dimensions", True),
        show_furniture=params.get("show_furniture", True),
        show_labels=params.get("show_labels", True),
    )

    if result.get("success"):
        abs_path = os.path.abspath(result["path"])
        result["path"] = abs_path
        result["image_tag"] = f"[IMAGE:{abs_path}]"

    return json.dumps(result, ensure_ascii=False)


def _3d_view(params, project_path):
    model = _load_module("design_model")
    renderer = _load_module("renderer_3d")

    design_id = params.get("design_id")
    if not design_id:
        return json.dumps({"success": False, "error": "design_id가 필요합니다."}, ensure_ascii=False)

    design = model.load_design(project_path, design_id)
    if not design:
        return json.dumps({"success": False, "error": f"설계 '{design_id}'을(를) 찾을 수 없습니다."}, ensure_ascii=False)

    output_dir = os.path.join(project_path, "outputs", "house-designs")
    os.makedirs(output_dir, exist_ok=True)
    output_path = os.path.join(output_dir, f"{design_id}_3d.html")

    result = renderer.render_3d_view(
        design=design,
        output_path=output_path,
        show_furniture=params.get("show_furniture", True),
        show_roof=params.get("show_roof", True),
    )

    if result.get("success") and params.get("open_in_browser", True):
        import subprocess
        abs_path = os.path.abspath(result["path"])
        try:
            subprocess.Popen(["open", abs_path])
            result["message"] = f"3D 뷰가 브라우저에서 열렸습니다.\n파일: {abs_path}"
        except Exception:
            result["message"] = f"3D 뷰 생성 완료. 브라우저에서 열기 실패.\n파일: {abs_path}"

    return json.dumps(result, ensure_ascii=False)


def _quantity_report(params, project_path):
    model = _load_module("design_model")
    takeoff = _load_module("quantity_takeoff")

    design_id = params.get("design_id")
    if not design_id:
        return json.dumps({"success": False, "error": "design_id가 필요합니다."}, ensure_ascii=False)

    design = model.load_design(project_path, design_id)
    if not design:
        return json.dumps({"success": False, "error": f"설계 '{design_id}'을(를) 찾을 수 없습니다."}, ensure_ascii=False)

    report_type = params.get("report_type", "full_report")
    floor_id = params.get("floor_id")

    result = takeoff.generate_report(design, report_type, floor_id)
    return json.dumps(result, ensure_ascii=False)


def _add_dimension(design, floor_id, element):
    """사용자 지정 치수선 추가"""
    model = _load_module("design_model")
    floor = model._find_floor(design, floor_id)
    if not floor:
        return {"success": False, "error": f"층 '{floor_id}'을(를) 찾을 수 없습니다."}

    if "dimensions" not in floor:
        floor["dimensions"] = []

    dim_id = f"dim_{len(floor['dimensions']) + 1}"
    dim = {
        "id": dim_id,
        "start": element.get("start", [0, 0]),
        "end": element.get("end", [0, 0]),
        "offset": element.get("offset", 0.5),
        "label": element.get("label", ""),
    }
    floor["dimensions"].append(dim)
    return {"success": True, "dimension_id": dim_id, "message": f"치수선 '{dim_id}' 추가됨"}


def _remove_dimension(design, floor_id, element):
    """사용자 지정 치수선 제거"""
    model = _load_module("design_model")
    floor = model._find_floor(design, floor_id)
    if not floor:
        return {"success": False, "error": f"층 '{floor_id}'을(를) 찾을 수 없습니다."}

    dim_id = element.get("id")
    dims = floor.get("dimensions", [])
    for i, d in enumerate(dims):
        if d["id"] == dim_id:
            dims.pop(i)
            return {"success": True, "message": f"치수선 '{dim_id}' 제거됨"}
    return {"success": False, "error": f"치수선 '{dim_id}'을(를) 찾을 수 없습니다."}


def _section_view(params, project_path):
    model = _load_module("design_model")
    renderer = _load_module("renderer_section")

    design_id = params.get("design_id")
    if not design_id:
        return json.dumps({"success": False, "error": "design_id가 필요합니다."}, ensure_ascii=False)

    design = model.load_design(project_path, design_id)
    if not design:
        return json.dumps({"success": False, "error": f"설계 '{design_id}'을(를) 찾을 수 없습니다."}, ensure_ascii=False)

    cut_start = params.get("cut_start")
    cut_end = params.get("cut_end")
    if not cut_start or not cut_end:
        return json.dumps({"success": False, "error": "cut_start와 cut_end가 필요합니다."}, ensure_ascii=False)

    output_dir = os.path.join(project_path, "outputs", "house-designs")
    os.makedirs(output_dir, exist_ok=True)
    output_path = os.path.join(output_dir, f"{design_id}_section.png")

    result = renderer.render_section_view(
        design=design,
        cut_start=cut_start,
        cut_end=cut_end,
        output_path=output_path,
        view_direction=params.get("view_direction", "right"),
        show_dimensions=params.get("show_dimensions", True),
    )

    if result.get("success"):
        abs_path = os.path.abspath(result["path"])
        result["path"] = abs_path
        result["image_tag"] = f"[IMAGE:{abs_path}]"

    return json.dumps(result, ensure_ascii=False)


def _elevation_view(params, project_path):
    model = _load_module("design_model")
    renderer = _load_module("renderer_elevation")

    design_id = params.get("design_id")
    if not design_id:
        return json.dumps({"success": False, "error": "design_id가 필요합니다."}, ensure_ascii=False)

    design = model.load_design(project_path, design_id)
    if not design:
        return json.dumps({"success": False, "error": f"설계 '{design_id}'을(를) 찾을 수 없습니다."}, ensure_ascii=False)

    direction = params.get("direction", "front")
    output_dir = os.path.join(project_path, "outputs", "house-designs")
    os.makedirs(output_dir, exist_ok=True)
    output_path = os.path.join(output_dir, f"{design_id}_elevation_{direction}.png")

    result = renderer.render_elevation_view(
        design=design,
        direction=direction,
        output_path=output_path,
        show_dimensions=params.get("show_dimensions", True),
    )

    if result.get("success"):
        abs_path = os.path.abspath(result["path"])
        result["path"] = abs_path
        result["image_tag"] = f"[IMAGE:{abs_path}]"

    return json.dumps(result, ensure_ascii=False)


def _set_project_info(design, element):
    """프로젝트 정보 설정"""
    standards = _load_module("drawing_standards")
    return standards.set_project_info(design, element)


def _wall_action(action, design, floor_id, element):
    """벽 시스템 action 디스패치"""
    wall_sys = _load_module("wall_system")
    model = _load_module("design_model")
    _geo = _load_module("geometry_utils")

    common = {
        "_find_floor": model._find_floor,
        "_find_element": model._find_element,
        "_gen_id": model._gen_id,
        "snap": _geo.snap,
    }

    if action == "add_wall":
        return wall_sys.add_wall(design, floor_id, element,
                                 _find_floor=common["_find_floor"],
                                 _gen_id=common["_gen_id"],
                                 snap=common["snap"])
    elif action == "remove_wall":
        return wall_sys.remove_wall(design, floor_id, element,
                                    _find_floor=common["_find_floor"],
                                    _find_element=common["_find_element"])
    elif action == "move_wall":
        return wall_sys.move_wall(design, floor_id, element,
                                  _find_floor=common["_find_floor"],
                                  _find_element=common["_find_element"],
                                  snap=common["snap"])
    elif action == "modify_wall":
        return wall_sys.modify_wall(design, floor_id, element,
                                    _find_floor=common["_find_floor"],
                                    _find_element=common["_find_element"],
                                    snap=common["snap"])
    elif action == "split_wall":
        return wall_sys.split_wall(design, floor_id, element,
                                   _find_floor=common["_find_floor"],
                                   _find_element=common["_find_element"],
                                   _gen_id=common["_gen_id"],
                                   snap=common["snap"])
    return {"success": False, "error": f"알 수 없는 벽 action: {action}"}


def _layer_action(action, design, element):
    """레이어 관리 action 디스패치"""
    layers = _load_module("layer_manager")

    if action == "get_layers":
        return layers.get_layers(design)
    elif action == "set_layer_visibility":
        return layers.set_layer_visibility(design, element)
    elif action == "set_layer_style":
        return layers.set_layer_style(design, element)
    elif action == "apply_layer_preset":
        return layers.apply_preset(design, element.get("preset", "all_on"))
    return {"success": False, "error": f"알 수 없는 레이어 action: {action}"}


def _export_drawing(params, project_path):
    """도면 출력 (PDF/SVG/DXF)"""
    model = _load_module("design_model")
    exporter = _load_module("renderer_export")

    design_id = params.get("design_id")
    if not design_id:
        return json.dumps({"success": False, "error": "design_id가 필요합니다."}, ensure_ascii=False)

    design = model.load_design(project_path, design_id)
    if not design:
        return json.dumps({"success": False, "error": f"설계 '{design_id}'을(를) 찾을 수 없습니다."}, ensure_ascii=False)

    format_type = params.get("format", "pdf")
    output_dir = os.path.join(project_path, "outputs", "house-designs")
    os.makedirs(output_dir, exist_ok=True)

    ext = format_type if format_type != "pdf" else "pdf"
    output_path = os.path.join(output_dir, f"{design_id}_export.{ext}")

    options = {
        "paper_size": params.get("paper_size", "A3"),
        "scale": params.get("scale", "1:100"),
        "include_title_block": params.get("include_title_block", True),
        "include_area_table": params.get("include_area_table", True),
        "floor_ids": params.get("floor_ids"),
        "floor_id": params.get("floor_id", "floor_1"),
        "include_sections": params.get("include_sections", False),
        "section_cuts": params.get("section_cuts", []),
        "include_elevations": params.get("include_elevations", False),
        "elevation_directions": params.get("elevation_directions", ["front"]),
        "drawing_type": params.get("drawing_type", "floor_plan"),
        "direction": params.get("direction", "front"),
        "cut_start": params.get("cut_start"),
        "cut_end": params.get("cut_end"),
    }

    result = exporter.export_drawing(design, output_path, format_type, options)

    if result.get("success"):
        abs_path = os.path.abspath(result["path"])
        result["path"] = abs_path
        result["message"] = f"{format_type.upper()} 출력 완료: {abs_path}"

    return json.dumps(result, ensure_ascii=False)


def _list(params, project_path):
    model = _load_module("design_model")
    designs = model.list_designs(project_path)
    if not designs:
        return json.dumps({"success": True, "designs": [], "message": "저장된 설계가 없습니다."}, ensure_ascii=False)
    return json.dumps({"success": True, "designs": designs, "message": f"{len(designs)}개 설계 발견"}, ensure_ascii=False)
