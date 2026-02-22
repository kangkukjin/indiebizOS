"""
House Designer v2 - 재질 정의 및 매핑
벽, 지붕, 바닥 등에 사용되는 재질 데이터
"""

# 벽 재질 정의
MATERIALS = {
    "brick": {
        "color": "#B85C38",
        "color_2d": "#C4704A",
        "label": "벽돌",
        "opacity": 1.0,
        "texture_type": "brick",
    },
    "concrete": {
        "color": "#C0BEB5",
        "color_2d": "#B0AEA5",
        "label": "콘크리트",
        "opacity": 1.0,
        "texture_type": "concrete",
    },
    "wood": {
        "color": "#DEB887",
        "color_2d": "#C8A873",
        "label": "목재",
        "opacity": 1.0,
        "texture_type": "wood",
    },
    "glass": {
        "color": "#A8D8EA",
        "color_2d": "#90C0D2",
        "label": "유리",
        "opacity": 0.4,
        "texture_type": "glass",
    },
    "stone": {
        "color": "#A0A0A0",
        "color_2d": "#909090",
        "label": "석재",
        "opacity": 1.0,
        "texture_type": "stone",
    },
    "stucco": {
        "color": "#F5F0E8",
        "color_2d": "#E5E0D8",
        "label": "스터코",
        "opacity": 1.0,
        "texture_type": "stucco",
    },
    "metal": {
        "color": "#888888",
        "color_2d": "#787878",
        "label": "금속",
        "opacity": 1.0,
        "texture_type": "metal",
    },
    "tile": {
        "color": "#E8D5B7",
        "color_2d": "#D8C5A7",
        "label": "타일",
        "opacity": 1.0,
        "texture_type": "tile",
    },
}

# 지붕 재질 정의
ROOF_MATERIALS = {
    "shingle": {
        "color": "#5D4E37",
        "label": "아스팔트 싱글",
    },
    "tile": {
        "color": "#B85C38",
        "label": "기와",
    },
    "metal": {
        "color": "#707070",
        "label": "금속",
    },
    "glass": {
        "color": "#A8D8EA",
        "label": "유리",
        "opacity": 0.4,
    },
    "slate": {
        "color": "#4A4A4A",
        "label": "슬레이트",
    },
}

# 2D 해칭 스타일 (matplotlib hatch 패턴)
HATCH_PATTERNS = {
    "brick": "//",
    "concrete": "",
    "wood": "||",
    "glass": "",
    "stone": "xx",
    "stucco": "..",
    "metal": "--",
    "tile": "++",
}

# 난간 재질 정의 (발코니용)
RAILING_MATERIALS = {
    "metal": {"color": "#555555", "label": "금속 난간", "opacity": 1.0},
    "glass": {"color": "#A8D8EA", "label": "유리 난간", "opacity": 0.3},
    "wood": {"color": "#8B6914", "label": "목재 난간", "opacity": 1.0},
}

# 기둥/보 재질 기본값
STRUCTURAL_DEFAULTS = {
    "column": {
        "material": "concrete",
        "color": "#A0A0A0",
    },
    "beam": {
        "material": "concrete",
        "color": "#B0B0B0",
    },
}


def get_material(name):
    """재질 이름으로 정의 조회. 없으면 기본 concrete."""
    return MATERIALS.get(name, MATERIALS["concrete"])


def get_roof_material(name):
    """지붕 재질 조회."""
    return ROOF_MATERIALS.get(name, ROOF_MATERIALS["shingle"])


def get_2d_hatch(name):
    """2D 해칭 패턴 반환."""
    return HATCH_PATTERNS.get(name, "")


def get_2d_color(name):
    """2D 렌더링용 색상 반환."""
    mat = MATERIALS.get(name, MATERIALS["concrete"])
    return mat.get("color_2d", mat["color"])


def get_materials_json():
    """3D 렌더러용 재질 JSON 데이터 생성."""
    return {
        "materials": MATERIALS,
        "roof_materials": ROOF_MATERIALS,
        "structural": STRUCTURAL_DEFAULTS,
        "railing_materials": RAILING_MATERIALS,
    }


def list_materials():
    """사용 가능한 재질 목록."""
    return [
        {"name": k, "label": v["label"]}
        for k, v in MATERIALS.items()
    ]


def list_roof_materials():
    """사용 가능한 지붕 재질 목록."""
    return [
        {"name": k, "label": v["label"]}
        for k, v in ROOF_MATERIALS.items()
    ]
