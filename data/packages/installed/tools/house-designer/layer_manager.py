"""
House Designer v4 - 레이어 관리 시스템
요소 타입별 가시성/스타일을 제어하여 도면 출력을 커스터마이즈
"""

# ============================================================
# 기본 레이어 정의
# ============================================================

DEFAULT_LAYERS = {
    "walls": {
        "name": "벽",
        "visible": True,
        "color": None,       # None = 기본값 사용
        "lineweight": None,  # None = 기본값 사용
        "opacity": 1.0,
    },
    "doors": {
        "name": "문",
        "visible": True,
        "color": None,
        "lineweight": None,
        "opacity": 1.0,
    },
    "windows": {
        "name": "창문",
        "visible": True,
        "color": None,
        "lineweight": None,
        "opacity": 1.0,
    },
    "furniture": {
        "name": "가구",
        "visible": True,
        "color": None,
        "lineweight": None,
        "opacity": 1.0,
    },
    "dimensions": {
        "name": "치수",
        "visible": True,
        "color": None,
        "lineweight": None,
        "opacity": 1.0,
    },
    "labels": {
        "name": "라벨",
        "visible": True,
        "color": None,
        "lineweight": None,
        "opacity": 1.0,
    },
    "structure": {
        "name": "구조 (기둥/보)",
        "visible": True,
        "color": None,
        "lineweight": None,
        "opacity": 1.0,
    },
    "stairs": {
        "name": "계단",
        "visible": True,
        "color": None,
        "lineweight": None,
        "opacity": 1.0,
    },
    "grid": {
        "name": "그리드",
        "visible": True,
        "color": "#CCCCCC",
        "lineweight": 0.3,
        "opacity": 0.08,
    },
    "rooms": {
        "name": "방 (배경색)",
        "visible": True,
        "color": None,
        "lineweight": None,
        "opacity": 0.5,
    },
}


# ============================================================
# 레이어 초기화/조회
# ============================================================

def init_layers(design):
    """설계에 레이어 기본값 초기화 (없으면 생성)"""
    if "layers" not in design:
        import copy
        design["layers"] = copy.deepcopy(DEFAULT_LAYERS)
    return design["layers"]


def get_layers(design):
    """현재 레이어 설정 반환"""
    layers = design.get("layers")
    if not layers:
        layers = init_layers(design)

    result = {}
    for layer_id, layer in layers.items():
        result[layer_id] = {
            "name": layer.get("name", layer_id),
            "visible": layer.get("visible", True),
            "color": layer.get("color"),
            "lineweight": layer.get("lineweight"),
            "opacity": layer.get("opacity", 1.0),
        }
    return {
        "success": True,
        "layers": result,
        "message": f"{len(result)}개 레이어",
    }


# ============================================================
# 레이어 가시성 설정
# ============================================================

def set_layer_visibility(design, element):
    """레이어 가시성 설정.
    element:
        layer_id: str - 단일 레이어 ID
        layer_ids: [str] - 여러 레이어 ID
        visible: bool
    """
    layers = design.get("layers")
    if not layers:
        layers = init_layers(design)

    layer_ids = element.get("layer_ids", [])
    if element.get("layer_id"):
        layer_ids = [element["layer_id"]]

    if not layer_ids:
        return {"success": False, "error": "layer_id 또는 layer_ids가 필요합니다."}

    visible = element.get("visible", True)
    changed = []
    not_found = []

    for lid in layer_ids:
        if lid in layers:
            layers[lid]["visible"] = visible
            changed.append(lid)
        else:
            not_found.append(lid)

    if not changed:
        return {"success": False, "error": f"레이어를 찾을 수 없습니다: {', '.join(not_found)}"}

    state = "표시" if visible else "숨김"
    msg = f"{len(changed)}개 레이어 {state}: {', '.join(changed)}"
    if not_found:
        msg += f" | 없는 레이어: {', '.join(not_found)}"

    return {"success": True, "message": msg}


# ============================================================
# 레이어 스타일 설정
# ============================================================

def set_layer_style(design, element):
    """레이어 스타일 설정.
    element:
        layer_id: str
        color: str (hex 색상)
        lineweight: float
        opacity: float (0.0~1.0)
    """
    layers = design.get("layers")
    if not layers:
        layers = init_layers(design)

    layer_id = element.get("layer_id")
    if not layer_id:
        return {"success": False, "error": "layer_id가 필요합니다."}

    if layer_id not in layers:
        return {"success": False, "error": f"레이어 '{layer_id}'을(를) 찾을 수 없습니다."}

    layer = layers[layer_id]
    changes = []

    if "color" in element:
        layer["color"] = element["color"]
        changes.append(f"색상={element['color']}")

    if "lineweight" in element:
        layer["lineweight"] = element["lineweight"]
        changes.append(f"선두께={element['lineweight']}")

    if "opacity" in element:
        opacity = max(0.0, min(1.0, element["opacity"]))
        layer["opacity"] = opacity
        changes.append(f"투명도={opacity}")

    if not changes:
        return {"success": False, "error": "변경할 스타일 속성이 없습니다."}

    return {
        "success": True,
        "message": f"레이어 '{layer_id}' 스타일 변경: {', '.join(changes)}",
    }


# ============================================================
# 레이어 필터링 (렌더링용)
# ============================================================

def is_layer_visible(design, layer_id):
    """특정 레이어가 보이는지 확인"""
    layers = design.get("layers")
    if not layers:
        return True  # 레이어 미설정 시 모두 표시
    layer = layers.get(layer_id)
    if not layer:
        return True  # 알 수 없는 레이어는 표시
    return layer.get("visible", True)


def get_layer_style(design, layer_id):
    """특정 레이어의 스타일 반환. 레이어 미설정 시 None 반환."""
    layers = design.get("layers")
    if not layers:
        return None
    layer = layers.get(layer_id)
    if not layer:
        return None
    return {
        "color": layer.get("color"),
        "lineweight": layer.get("lineweight"),
        "opacity": layer.get("opacity", 1.0),
    }


def filter_elements_by_layers(design, floor):
    """레이어 가시성에 따라 렌더링할 요소만 필터링.
    Returns dict with keys: rooms, walls, doors, windows, furniture,
                            columns, beams, stairs, show_dimensions,
                            show_labels, show_grid
    """
    result = {
        "rooms": floor.get("rooms", []) if is_layer_visible(design, "rooms") else [],
        "walls": floor.get("walls", []) if is_layer_visible(design, "walls") else [],
        "doors": floor.get("doors", []) if is_layer_visible(design, "doors") else [],
        "windows": floor.get("windows", []) if is_layer_visible(design, "windows") else [],
        "furniture": floor.get("furniture", []) if is_layer_visible(design, "furniture") else [],
        "columns": floor.get("columns", []) if is_layer_visible(design, "structure") else [],
        "beams": floor.get("beams", []) if is_layer_visible(design, "structure") else [],
        "stairs": floor.get("stairs", []) if is_layer_visible(design, "stairs") else [],
        "show_dimensions": is_layer_visible(design, "dimensions"),
        "show_labels": is_layer_visible(design, "labels"),
        "show_grid": is_layer_visible(design, "grid"),
    }
    return result


# ============================================================
# 프리셋
# ============================================================

def apply_preset(design, preset_name):
    """미리 정의된 레이어 프리셋 적용.
    presets:
        all_on - 모든 레이어 표시
        structure_only - 벽+기둥+보만 표시
        presentation - 가구+라벨+방, 치수/그리드 숨김
        dimensions_only - 벽+치수만 표시
    """
    layers = design.get("layers")
    if not layers:
        layers = init_layers(design)

    presets = {
        "all_on": {lid: True for lid in layers},
        "structure_only": {
            "walls": True, "structure": True, "grid": True,
            "doors": False, "windows": False, "furniture": False,
            "dimensions": False, "labels": False, "stairs": True, "rooms": False,
        },
        "presentation": {
            "walls": True, "doors": True, "windows": True, "furniture": True,
            "labels": True, "rooms": True, "stairs": True, "structure": True,
            "dimensions": False, "grid": False,
        },
        "dimensions_only": {
            "walls": True, "dimensions": True, "labels": True,
            "doors": False, "windows": False, "furniture": False,
            "structure": False, "stairs": False, "grid": True, "rooms": False,
        },
    }

    preset = presets.get(preset_name)
    if not preset:
        return {
            "success": False,
            "error": f"알 수 없는 프리셋: {preset_name}. 사용 가능: {list(presets.keys())}",
        }

    for lid, visible in preset.items():
        if lid in layers:
            layers[lid]["visible"] = visible

    return {
        "success": True,
        "message": f"레이어 프리셋 '{preset_name}' 적용됨",
    }
