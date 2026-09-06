"""
House Designer v3 - 3D HTML 렌더러
Three.js 템플릿에 설계 데이터와 JS 모듈을 주입하여 독립 실행형 HTML 생성
v3: JS 모듈 분리 (텍스처, 건물요소, 가구, 지붕) → 인라인 삽입
"""
import json
import os
import importlib.util

# geometry_utils 임포트
_pkg_dir = os.path.dirname(os.path.abspath(__file__))
_gu_path = os.path.join(_pkg_dir, "geometry_utils.py")
_spec = importlib.util.spec_from_file_location("geometry_utils", _gu_path)
_gu = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_gu)
room_area = _gu.room_area

# materials 임포트
_mat_path = os.path.join(_pkg_dir, "materials.py")
_mat_spec = importlib.util.spec_from_file_location("materials", _mat_path)
_mat_mod = importlib.util.module_from_spec(_mat_spec)
_mat_spec.loader.exec_module(_mat_mod)
get_materials_json = _mat_mod.get_materials_json

# JS 모듈 파일 매핑 (플레이스홀더 → 파일명)
_JS_MODULES = {
    "{{INLINE_3D_TEXTURES}}": "3d_textures.js",
    "{{INLINE_3D_BUILDING}}": "3d_building.js",
    "{{INLINE_3D_FURNITURE}}": "3d_furniture.js",
    "{{INLINE_3D_ROOF}}": "3d_roof.js",
}


def _load_js_modules(template_dir):
    """JS 모듈 파일들을 읽어 {플레이스홀더: 내용} 딕셔너리로 반환."""
    modules = {}
    for placeholder, filename in _JS_MODULES.items():
        filepath = os.path.join(template_dir, filename)
        if os.path.exists(filepath):
            with open(filepath, "r", encoding="utf-8") as f:
                modules[placeholder] = f.read()
        else:
            modules[placeholder] = f"// WARNING: {filename} not found"
    return modules


def render_3d_view(design, output_path, show_furniture=True, show_roof=True):
    template_dir = os.path.join(_pkg_dir, "templates")
    template_path = os.path.join(template_dir, "3d_viewer.html")

    if not os.path.exists(template_path):
        return {"success": False, "error": "3D 뷰어 템플릿을 찾을 수 없습니다."}

    with open(template_path, "r", encoding="utf-8") as f:
        html = f.read()

    # JS 모듈 인라인 삽입
    js_modules = _load_js_modules(template_dir)
    for placeholder, content in js_modules.items():
        html = html.replace(placeholder, content)

    # 통계 계산 (다각형 방 면적 포함)
    total_rooms = sum(len(fl.get("rooms", [])) for fl in design.get("floors", []))
    total_area = 0
    for fl in design.get("floors", []):
        for r in fl.get("rooms", []):
            total_area += room_area(r)

    total_columns = sum(len(fl.get("columns", [])) for fl in design.get("floors", []))
    total_beams = sum(len(fl.get("beams", [])) for fl in design.get("floors", []))

    # 재질 데이터
    materials_json = json.dumps(get_materials_json(), ensure_ascii=False)

    # 지붕 설정
    roof_config = json.dumps(design.get("roof", {
        "type": "hip", "height": 2.0, "direction": "x", "overhang": 0.3
    }), ensure_ascii=False)

    # 외벽 기본 재질
    facade_defaults = json.dumps(design.get("facade_defaults", {
        "material": "concrete", "color": "#E0DDD0"
    }), ensure_ascii=False)

    # 플레이스홀더 치환
    html = html.replace("{{DESIGN_NAME}}", _escape_html(design.get("name", "House")))
    html = html.replace("{{DESIGN_JSON}}", json.dumps(design, ensure_ascii=False))
    html = html.replace("{{MATERIALS_JSON}}", materials_json)
    html = html.replace("{{ROOF_CONFIG}}", roof_config)
    html = html.replace("{{FACADE_DEFAULTS}}", facade_defaults)
    html = html.replace("{{FLOOR_COUNT}}", str(len(design.get("floors", []))))
    html = html.replace("{{ROOM_COUNT}}", str(total_rooms))
    html = html.replace("{{TOTAL_AREA}}", f"{total_area:.1f}")
    html = html.replace("{{SHOW_FURNITURE}}", "true" if show_furniture else "false")
    html = html.replace("{{SHOW_ROOF}}", "true" if show_roof else "false")

    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(html)

    msg_parts = [f"{total_rooms}개 방", f"{total_area:.1f}m\u00b2"]
    if total_columns:
        msg_parts.append(f"기둥 {total_columns}개")
    if total_beams:
        msg_parts.append(f"보 {total_beams}개")

    return {
        "success": True,
        "path": os.path.abspath(output_path),
        "format": "html",
        "message": f"3D 뷰 생성 완료 ({', '.join(msg_parts)})",
    }


def _escape_html(text):
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;")
