"""
House Designer v4 - 도면 출력 모듈
PDF, SVG, DXF 형식 출력 지원
제목란, 면적표, 축척 반영, 다중 도면(평면도+단면도+입면도) 결합
"""
import os
import importlib.util
import json
import math

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.backends.backend_pdf import PdfPages

_pkg_dir = os.path.dirname(os.path.abspath(__file__))


def _load(name):
    path = os.path.join(_pkg_dir, f"{name}.py")
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


# ============================================================
# PDF 출력
# ============================================================

def export_pdf(design, output_path, options=None):
    """다중 페이지 PDF 출력.
    options:
        paper_size: "A3" | "A4" (기본 A3)
        scale: "1:50" | "1:100" | "1:200" (기본 1:100)
        include_title_block: bool (기본 True)
        include_area_table: bool (기본 True)
        floor_ids: [str] (기본 전체 층)
        include_sections: bool (기본 False)
        section_cuts: [[cut_start, cut_end], ...]
        include_elevations: bool (기본 False)
        elevation_directions: ["front", "rear", "left", "right"]
    """
    if options is None:
        options = {}

    paper_size = options.get("paper_size", "A3")
    scale = options.get("scale", "1:100")
    include_title = options.get("include_title_block", True)
    include_area = options.get("include_area_table", True)
    floor_ids = options.get("floor_ids")
    include_sections = options.get("include_sections", False)
    section_cuts = options.get("section_cuts", [])
    include_elevations = options.get("include_elevations", False)
    elevation_dirs = options.get("elevation_directions", ["front"])

    renderer_2d = _load("renderer_2d")
    standards = _load("drawing_standards")

    # 용지 크기 (inch)
    paper = standards.PAPER_SIZES.get(paper_size, standards.PAPER_SIZES["A3"])
    fig_w = paper["width_mm"] / 25.4
    fig_h = paper["height_mm"] / 25.4

    floors = design.get("floors", [])
    if floor_ids:
        floors = [f for f in floors if f["id"] in floor_ids]

    pages_generated = 0

    with PdfPages(output_path) as pdf:
        # 1) 층별 평면도
        for floor in floors:
            fig, ax = plt.subplots(1, 1, figsize=(fig_w, fig_h))
            fig.patch.set_facecolor("white")

            # 평면도 렌더링 (기존 렌더러 활용하되 fig/ax 직접 전달)
            _render_floor_plan_on_ax(ax, design, floor, scale, standards)

            drawing_num = standards.auto_number_drawing(design, "floor_plan")
            drawing_name = f"평면도 - {floor.get('name', floor['id'])}"

            if include_title:
                standards.draw_title_block(
                    ax, fig, design,
                    drawing_name=drawing_name,
                    drawing_number=drawing_num,
                    scale=scale,
                    paper_size=paper_size,
                )

            if include_area:
                standards.draw_area_table(ax, design, floor_id=floor["id"])

            ax.set_aspect("equal")
            plt.tight_layout()
            pdf.savefig(fig, dpi=150)
            plt.close(fig)
            pages_generated += 1

        # 2) 단면도
        if include_sections and section_cuts:
            renderer_sec = _load("renderer_section")
            for i, cut in enumerate(section_cuts):
                if len(cut) < 2:
                    continue
                fig, ax = plt.subplots(1, 1, figsize=(fig_w, fig_h))
                fig.patch.set_facecolor("white")

                _render_section_on_ax(ax, design, cut[0], cut[1], renderer_sec)

                drawing_num = standards.auto_number_drawing(design, "section")
                if include_title:
                    standards.draw_title_block(
                        ax, fig, design,
                        drawing_name=f"단면도 {i+1}",
                        drawing_number=drawing_num,
                        scale=scale,
                        paper_size=paper_size,
                    )

                ax.set_aspect("equal")
                plt.tight_layout()
                pdf.savefig(fig, dpi=150)
                plt.close(fig)
                pages_generated += 1

        # 3) 입면도
        if include_elevations:
            renderer_elev = _load("renderer_elevation")
            for direction in elevation_dirs:
                fig, ax = plt.subplots(1, 1, figsize=(fig_w, fig_h))
                fig.patch.set_facecolor("white")

                _render_elevation_on_ax(ax, design, direction, renderer_elev)

                drawing_num = standards.auto_number_drawing(design, "elevation")
                dir_labels = {
                    "front": "정면도", "rear": "배면도",
                    "left": "좌측면도", "right": "우측면도"
                }
                if include_title:
                    standards.draw_title_block(
                        ax, fig, design,
                        drawing_name=dir_labels.get(direction, direction),
                        drawing_number=drawing_num,
                        scale=scale,
                        paper_size=paper_size,
                    )

                ax.set_aspect("equal")
                plt.tight_layout()
                pdf.savefig(fig, dpi=150)
                plt.close(fig)
                pages_generated += 1

    return {
        "success": True,
        "path": output_path,
        "format": "pdf",
        "pages": pages_generated,
        "message": f"PDF 출력 완료: {pages_generated}페이지",
    }


# ============================================================
# SVG 출력
# ============================================================

def export_svg(design, output_path, options=None):
    """SVG 벡터 출력 (단일 도면).
    options:
        floor_id: str (기본 floor_1)
        drawing_type: "floor_plan" | "section" | "elevation"
        scale: "1:100"
        include_title_block: bool
        direction: str (입면도용)
        cut_start/cut_end: list (단면도용)
    """
    if options is None:
        options = {}

    floor_id = options.get("floor_id", "floor_1")
    drawing_type = options.get("drawing_type", "floor_plan")
    scale = options.get("scale", "1:100")
    include_title = options.get("include_title_block", True)

    standards = _load("drawing_standards")
    paper = standards.PAPER_SIZES.get(options.get("paper_size", "A3"),
                                       standards.PAPER_SIZES["A3"])
    fig_w = paper["width_mm"] / 25.4
    fig_h = paper["height_mm"] / 25.4

    # SVG 백엔드
    fig, ax = plt.subplots(1, 1, figsize=(fig_w, fig_h))
    fig.patch.set_facecolor("white")

    if drawing_type == "floor_plan":
        floor = None
        for f in design.get("floors", []):
            if f["id"] == floor_id:
                floor = f
                break
        if not floor:
            plt.close(fig)
            return {"success": False, "error": f"층 '{floor_id}'을(를) 찾을 수 없습니다."}
        _render_floor_plan_on_ax(ax, design, floor, scale, standards)

    elif drawing_type == "section":
        renderer_sec = _load("renderer_section")
        cut_start = options.get("cut_start", [5, 0])
        cut_end = options.get("cut_end", [5, 15])
        _render_section_on_ax(ax, design, cut_start, cut_end, renderer_sec)

    elif drawing_type == "elevation":
        renderer_elev = _load("renderer_elevation")
        direction = options.get("direction", "front")
        _render_elevation_on_ax(ax, design, direction, renderer_elev)

    else:
        plt.close(fig)
        return {"success": False, "error": f"알 수 없는 도면 타입: {drawing_type}"}

    if include_title:
        drawing_num = standards.auto_number_drawing(design, drawing_type)
        standards.draw_title_block(
            ax, fig, design,
            drawing_name=drawing_type,
            drawing_number=drawing_num,
            scale=scale,
            paper_size=options.get("paper_size", "A3"),
        )

    ax.set_aspect("equal")
    plt.tight_layout()
    fig.savefig(output_path, format="svg", dpi=150, bbox_inches="tight")
    plt.close(fig)

    return {
        "success": True,
        "path": output_path,
        "format": "svg",
        "message": "SVG 출력 완료",
    }


# ============================================================
# DXF 출력 (선택적 의존성)
# ============================================================

def export_dxf(design, output_path, options=None):
    """DXF 출력 (AutoCAD 호환). ezdxf 라이브러리 필요.
    options:
        floor_id: str (기본 floor_1)
        scale: "1:100"
    """
    try:
        import ezdxf
    except ImportError:
        return {
            "success": False,
            "error": "DXF 출력에는 ezdxf 라이브러리가 필요합니다. pip install ezdxf 로 설치하세요.",
        }

    if options is None:
        options = {}

    floor_id = options.get("floor_id", "floor_1")
    _geo = _load("geometry_utils")

    floor = None
    for f in design.get("floors", []):
        if f["id"] == floor_id:
            floor = f
            break
    if not floor:
        return {"success": False, "error": f"층 '{floor_id}'을(를) 찾을 수 없습니다."}

    doc = ezdxf.new(dxfversion="R2010")
    msp = doc.modelspace()

    # 레이어 생성
    doc.layers.add("WALLS", color=7)          # 흰색/검정
    doc.layers.add("WALLS_INT", color=8)      # 회색
    doc.layers.add("DOORS", color=30)         # 갈색
    doc.layers.add("WINDOWS", color=150)      # 청색
    doc.layers.add("ROOMS", color=3)          # 녹색
    doc.layers.add("FURNITURE", color=8)      # 회색
    doc.layers.add("DIMENSIONS", color=1)     # 빨강
    doc.layers.add("TEXT", color=7)           # 흰색/검정
    doc.layers.add("COLUMNS", color=4)        # 시안

    # 벽
    for wall in floor.get("walls", []):
        sx, sy = wall["start"]
        ex, ey = wall["end"]
        thickness = wall.get("thickness", 0.2)
        layer = "WALLS" if wall.get("type") == "exterior" else "WALLS_INT"

        # 벽 중심선
        msp.add_line((sx, sy), (ex, ey), dxfattribs={"layer": layer})

        # 벽 두께 표현 (오프셋 라인)
        wlen = math.hypot(ex - sx, ey - sy)
        if wlen > 0.01:
            nx = -(ey - sy) / wlen * thickness / 2
            ny = (ex - sx) / wlen * thickness / 2
            msp.add_line((sx + nx, sy + ny), (ex + nx, ey + ny),
                         dxfattribs={"layer": layer})
            msp.add_line((sx - nx, sy - ny), (ex - nx, ey - ny),
                         dxfattribs={"layer": layer})

    # 방 (폴리라인)
    for room in floor.get("rooms", []):
        verts = _geo.room_vertices(room)
        if len(verts) >= 3:
            pts = [(v[0], v[1]) for v in verts]
            msp.add_lwpolyline(pts, close=True,
                               dxfattribs={"layer": "ROOMS"})

        # 방 이름 텍스트
        bbox = _geo.room_bbox(room)
        cx = (bbox[0] + bbox[2]) / 2
        cy = (bbox[1] + bbox[3]) / 2
        area = _geo.room_area(room)
        text = f"{room.get('name', '')}\n({area:.1f}m²)"
        msp.add_text(text, height=0.2,
                      dxfattribs={"layer": "TEXT", "insert": (cx, cy)})

    # 문
    for door in floor.get("doors", []):
        wall_id = door.get("wall_id")
        wall = None
        for w in floor.get("walls", []):
            if w["id"] == wall_id:
                wall = w
                break
        if not wall:
            continue

        sx, sy = wall["start"]
        ex, ey = wall["end"]
        wlen = math.hypot(ex - sx, ey - sy)
        if wlen < 0.01:
            continue
        dx, dy = (ex - sx) / wlen, (ey - sy) / wlen
        pos = door.get("position", 0)
        dw = door.get("width", 0.9)
        p1 = (sx + dx * (pos - dw / 2), sy + dy * (pos - dw / 2))
        p2 = (sx + dx * (pos + dw / 2), sy + dy * (pos + dw / 2))
        msp.add_line(p1, p2, dxfattribs={"layer": "DOORS"})

    # 창문
    for win in floor.get("windows", []):
        wall_id = win.get("wall_id")
        wall = None
        for w in floor.get("walls", []):
            if w["id"] == wall_id:
                wall = w
                break
        if not wall:
            continue

        sx, sy = wall["start"]
        ex, ey = wall["end"]
        wlen = math.hypot(ex - sx, ey - sy)
        if wlen < 0.01:
            continue
        dx, dy = (ex - sx) / wlen, (ey - sy) / wlen
        pos = win.get("position", 0)
        ww = win.get("width", 1.5)
        p1 = (sx + dx * (pos - ww / 2), sy + dy * (pos - ww / 2))
        p2 = (sx + dx * (pos + ww / 2), sy + dy * (pos + ww / 2))
        msp.add_line(p1, p2, dxfattribs={"layer": "WINDOWS"})

    # 기둥
    for col in floor.get("columns", []):
        cx, cy = col.get("x", 0), col.get("y", 0)
        cw = col.get("width", 0.4)
        cd = col.get("depth", cw)
        shape = col.get("shape", "rect")

        if shape == "round":
            msp.add_circle((cx, cy), radius=cw / 2,
                           dxfattribs={"layer": "COLUMNS"})
        else:
            pts = [
                (cx - cw / 2, cy - cd / 2),
                (cx + cw / 2, cy - cd / 2),
                (cx + cw / 2, cy + cd / 2),
                (cx - cw / 2, cy + cd / 2),
            ]
            msp.add_lwpolyline(pts, close=True,
                               dxfattribs={"layer": "COLUMNS"})

    # 가구 (사각형)
    for furn in floor.get("furniture", []):
        fx, fy = furn.get("x", 0), furn.get("y", 0)
        fw, fd = furn.get("width", 0.5), furn.get("depth", 0.5)
        pts = [
            (fx, fy), (fx + fw, fy),
            (fx + fw, fy + fd), (fx, fy + fd),
        ]
        msp.add_lwpolyline(pts, close=True,
                           dxfattribs={"layer": "FURNITURE"})

    doc.saveas(output_path)

    return {
        "success": True,
        "path": output_path,
        "format": "dxf",
        "message": f"DXF 출력 완료 ({floor_id})",
    }


# ============================================================
# 내부 헬퍼: 기존 렌더러를 ax에 직접 그리기
# ============================================================

def _render_floor_plan_on_ax(ax, design, floor, scale, standards):
    """기존 2D 렌더러의 로직을 재사용하여 ax에 평면도를 그림"""
    renderer_2d = _load("renderer_2d")
    _geo = _load("geometry_utils")
    _mat = _load("materials")
    _dim = _load("renderer_2d_dimensions")
    _sym = _load("renderer_2d_symbols")

    rooms = floor.get("rooms", [])
    walls = floor.get("walls", [])
    is_piloti = floor.get("is_piloti", False)

    room_area = _geo.room_area
    room_bbox = _geo.room_bbox
    room_vertices = _geo.room_vertices

    if not rooms and not is_piloti:
        ax.text(0.5, 0.5, "방이 없습니다", ha="center", va="center",
                transform=ax.transAxes, fontsize=12, color="#888888")
        return

    # 범위 계산
    all_min_x = float('inf')
    all_min_y = float('inf')
    all_max_x = float('-inf')
    all_max_y = float('-inf')

    for room in rooms:
        bbox = room_bbox(room)
        all_min_x = min(all_min_x, bbox[0])
        all_min_y = min(all_min_y, bbox[1])
        all_max_x = max(all_max_x, bbox[2])
        all_max_y = max(all_max_y, bbox[3])

    if all_min_x > all_max_x:
        site = design.get("site", {})
        all_min_x, all_min_y = 0, 0
        all_max_x = site.get("width", 20)
        all_max_y = site.get("depth", 15)

    padding = 2.0
    ax.set_xlim(all_min_x - padding, all_max_x + padding + 3)
    ax.set_ylim(all_min_y - padding - 2, all_max_y + padding)
    ax.set_facecolor("#FAFAFA")
    ax.grid(True, alpha=0.08, linewidth=0.3, color="#CCCCCC")

    # 간략 렌더링 (방 배경, 벽, 라벨, 치수)
    for room in rooms:
        verts = room_vertices(room)
        from matplotlib.patches import Polygon as MplPolygon
        import matplotlib.patheffects as pe

        room_type = room.get("type", "other")
        color = renderer_2d.ROOM_COLORS.get(room_type, "#F5F5F5")
        poly = MplPolygon(verts, closed=True, facecolor=color, edgecolor="#CCCCCC",
                          linewidth=0.5, alpha=0.5, zorder=1)
        ax.add_patch(poly)

        # 라벨
        bbox = room_bbox(room)
        cx = (bbox[0] + bbox[2]) / 2
        cy = (bbox[1] + bbox[3]) / 2
        area = room_area(room)
        label = f"{room.get('name', '')}\n({area:.1f}m²)"
        ax.text(cx, cy, label, ha="center", va="center", fontsize=7,
                fontweight="bold", color="#333333", zorder=8,
                path_effects=[pe.withStroke(linewidth=2, foreground="white")])

    # 벽
    for wall in walls:
        sx, sy = wall["start"]
        ex, ey = wall["end"]
        is_ext = wall.get("type") == "exterior"
        lw = 2.0 if is_ext else 1.0
        color = "#1A1A1A" if is_ext else "#666666"
        ax.plot([sx, ex], [sy, ey], color=color, linewidth=lw, solid_capstyle="round", zorder=5)

    # 치수
    _dim.draw_dimensions(ax, rooms, all_min_x, all_min_y, all_max_x, all_max_y,
                         room_area, room_bbox, walls=walls,
                         user_dimensions=floor.get("dimensions"))


def _render_section_on_ax(ax, design, cut_start, cut_end, renderer_sec):
    """단면도를 ax에 직접 그림 (렌더러 내부 함수 호출)"""
    # 간단히 render_section_view의 내부 로직 일부를 재현
    # 이 버전에서는 임시 파일을 만들지 않고 직접 ax에 그림
    import tempfile
    with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as f:
        tmp_path = f.name

    result = renderer_sec.render_section_view(
        design=design,
        cut_start=cut_start,
        cut_end=cut_end,
        output_path=tmp_path,
        show_dimensions=True,
    )

    if result.get("success"):
        img = plt.imread(tmp_path)
        ax.imshow(img, aspect="auto")
        ax.set_axis_off()

    try:
        os.unlink(tmp_path)
    except Exception:
        pass


def _render_elevation_on_ax(ax, design, direction, renderer_elev):
    """입면도를 ax에 직접 그림"""
    import tempfile
    with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as f:
        tmp_path = f.name

    result = renderer_elev.render_elevation_view(
        design=design,
        direction=direction,
        output_path=tmp_path,
        show_dimensions=True,
    )

    if result.get("success"):
        img = plt.imread(tmp_path)
        ax.imshow(img, aspect="auto")
        ax.set_axis_off()

    try:
        os.unlink(tmp_path)
    except Exception:
        pass


# ============================================================
# 진입점
# ============================================================

def export_drawing(design, output_path, format_type="pdf", options=None):
    """도면 출력 진입점"""
    handlers = {
        "pdf": export_pdf,
        "svg": export_svg,
        "dxf": export_dxf,
    }

    handler = handlers.get(format_type)
    if not handler:
        return {
            "success": False,
            "error": f"지원하지 않는 형식: {format_type}. 사용 가능: {list(handlers.keys())}",
        }

    return handler(design, output_path, options)
