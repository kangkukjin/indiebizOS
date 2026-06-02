"""
House Designer v4 - 2D 평면도 렌더러
matplotlib를 사용하여 전문 건축 도면 수준의 컬러 평면도 PNG 생성
v3: 채운 벽 다각형, 전문 심볼, 건축 표준 치수선, 계단/난간 지원
v4: 레이어 관리 시스템 통합 (가시성/스타일 제어)
"""
import math
import os
import importlib.util

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.patches as patches
import matplotlib.patheffects as pe

# geometry_utils 임포트
_pkg_dir = os.path.dirname(os.path.abspath(__file__))
_gu_path = os.path.join(_pkg_dir, "geometry_utils.py")
_spec = importlib.util.spec_from_file_location("geometry_utils", _gu_path)
_gu = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_gu)
snap = _gu.snap
room_vertices = _gu.room_vertices
room_to_edges = _gu.room_to_edges
room_area = _gu.room_area
room_centroid = _gu.room_centroid
room_bbox = _gu.room_bbox
edge_key = _gu.edge_key

# materials 임포트
_mat_path = os.path.join(_pkg_dir, "materials.py")
_mspec = importlib.util.spec_from_file_location("materials", _mat_path)
_mat = importlib.util.module_from_spec(_mspec)
_mspec.loader.exec_module(_mat)
get_2d_color = _mat.get_2d_color
get_2d_hatch = _mat.get_2d_hatch

# v3 심볼/치수 모듈 임포트
_sym_path = os.path.join(_pkg_dir, "renderer_2d_symbols.py")
_sspec = importlib.util.spec_from_file_location("renderer_2d_symbols", _sym_path)
_sym = importlib.util.module_from_spec(_sspec)
_sspec.loader.exec_module(_sym)
draw_fixture = _sym.draw_fixture
draw_door_symbol = _sym.draw_door
draw_window_symbol = _sym.draw_window
draw_stairs_2d = _sym.draw_stairs_2d
draw_balcony_railing = _sym.draw_balcony_railing

_dim_path = os.path.join(_pkg_dir, "renderer_2d_dimensions.py")
_dspec = importlib.util.spec_from_file_location("renderer_2d_dimensions", _dim_path)
_dim = importlib.util.module_from_spec(_dspec)
_dspec.loader.exec_module(_dim)
draw_dimensions = _dim.draw_dimensions

# v4: 지붕 2D 렌더러 임포트
_roof_path = os.path.join(_pkg_dir, "renderer_2d_roof.py")
if os.path.exists(_roof_path):
    _rspec = importlib.util.spec_from_file_location("renderer_2d_roof", _roof_path)
    _roof = importlib.util.module_from_spec(_rspec)
    _rspec.loader.exec_module(_roof)
    draw_roof_plan = _roof.draw_roof_plan
else:
    draw_roof_plan = None

# layer_manager 임포트
_lm_path = os.path.join(_pkg_dir, "layer_manager.py")
_lmspec = importlib.util.spec_from_file_location("layer_manager", _lm_path)
_lm = importlib.util.module_from_spec(_lmspec)
_lmspec.loader.exec_module(_lm)
is_layer_visible = _lm.is_layer_visible
get_layer_style = _lm.get_layer_style
filter_elements_by_layers = _lm.filter_elements_by_layers

# 한글 폰트
try:
    from matplotlib import font_manager
    for fname in ["/System/Library/Fonts/Supplemental/AppleGothic.ttf",
                  "/System/Library/Fonts/AppleSDGothicNeo.ttc",
                  "/Library/Fonts/NanumGothic.ttf"]:
        if os.path.exists(fname):
            font_manager.fontManager.addfont(fname)
            prop = font_manager.FontProperties(fname=fname)
            matplotlib.rcParams["font.family"] = prop.get_name()
            break
    else:
        matplotlib.rcParams["font.family"] = "sans-serif"
except Exception:
    matplotlib.rcParams["font.family"] = "sans-serif"

matplotlib.rcParams["axes.unicode_minus"] = False

SCALE = 60  # 미터당 픽셀


# ============================================================
# 메인 렌더 함수
# ============================================================

def render_floor_plan(design, floor_id="floor_1", output_path=None,
                      show_dimensions=True, show_furniture=True, show_labels=True):
    floor = None
    for f in design.get("floors", []):
        if f["id"] == floor_id:
            floor = f
            break
    if not floor:
        return {"success": False, "error": f"층 '{floor_id}'을(를) 찾을 수 없습니다."}

    # v4: 레이어 기반 요소 필터링
    filtered = filter_elements_by_layers(design, floor)
    rooms = filtered["rooms"]
    columns = filtered["columns"]
    beams = filtered["beams"]
    stairs = filtered["stairs"]
    is_piloti = floor.get("is_piloti", False)

    # 레이어 가시성을 파라미터에 반영
    show_dimensions = show_dimensions and filtered["show_dimensions"]
    show_furniture = show_furniture and is_layer_visible(design, "furniture")
    show_labels = show_labels and filtered["show_labels"]
    show_grid = filtered["show_grid"]

    if not rooms and not columns and not beams and not stairs:
        return {"success": False, "error": "방이나 구조 요소가 없어서 평면도를 생성할 수 없습니다."}

    # 영역 계산
    all_min_x, all_min_y = float('inf'), float('inf')
    all_max_x, all_max_y = float('-inf'), float('-inf')
    for room in rooms:
        bbox = room_bbox(room)
        all_min_x = min(all_min_x, bbox[0])
        all_min_y = min(all_min_y, bbox[1])
        all_max_x = max(all_max_x, bbox[2])
        all_max_y = max(all_max_y, bbox[3])
    for col in columns:
        pos = col.get("position")
        if pos:
            cx, cy = pos[0], pos[1]
        else:
            cx, cy = col.get("x", 0), col.get("y", 0)
        csize = col.get("size", [col.get("width", 0.4), col.get("depth", 0.4)])
        cw = max(csize[0], csize[1])
        all_min_x = min(all_min_x, cx - cw)
        all_min_y = min(all_min_y, cy - cw)
        all_max_x = max(all_max_x, cx + cw)
        all_max_y = max(all_max_y, cy + cw)
    for beam in beams:
        for pt in [beam.get("start", [0, 0]), beam.get("end", [0, 0])]:
            all_min_x = min(all_min_x, pt[0])
            all_min_y = min(all_min_y, pt[1])
            all_max_x = max(all_max_x, pt[0])
            all_max_y = max(all_max_y, pt[1])
    if not rooms:
        site = design.get("site", {})
        sw = site.get("width", 20)
        sd = site.get("depth", 15)
        all_min_x = min(all_min_x, 0)
        all_min_y = min(all_min_y, 0)
        all_max_x = max(all_max_x, sw)
        all_max_y = max(all_max_y, sd)

    padding = 2.5  # v3: 더 넓은 여백 (치수선/축척바 공간)
    plot_w = all_max_x - all_min_x + padding * 2
    plot_h = all_max_y - all_min_y + padding * 2 + 1.5  # 축척바 공간

    fig_w = max(plot_w * SCALE / 100, 7)
    fig_h = max(plot_h * SCALE / 100, 6)
    fig, ax = plt.subplots(1, 1, figsize=(fig_w, fig_h))
    ax.set_xlim(all_min_x - padding, all_max_x + padding + 1.5)  # 방위표 공간
    ax.set_ylim(all_min_y - padding - 1.5, all_max_y + padding)
    ax.set_aspect("equal")
    ax.set_facecolor("#FAFAFA")
    fig.patch.set_facecolor("#FFFFFF")

    # 그리드 (v4: 레이어 가시성/스타일)
    if show_grid:
        grid_style = get_layer_style(design, "grid")
        grid_alpha = 0.12
        grid_color = "#CCCCCC"
        grid_lw = 0.3
        if grid_style:
            grid_alpha = grid_style.get("opacity", 0.12)
            if grid_style.get("color"):
                grid_color = grid_style["color"]
            if grid_style.get("lineweight"):
                grid_lw = grid_style["lineweight"]
        ax.grid(True, alpha=grid_alpha, linewidth=grid_lw, color=grid_color)
    else:
        ax.grid(False)

    # 0) 필로티 바닥 슬래브 표시
    if is_piloti and not rooms:
        site = design.get("site", {})
        sw = site.get("width", 20)
        sd = site.get("depth", 15)
        slab = patches.Rectangle(
            (0, 0), sw, sd,
            linewidth=1.5, edgecolor="#999999", facecolor="#E8E8E8",
            alpha=0.2, linestyle="--", zorder=0
        )
        ax.add_patch(slab)
        ax.text(sw / 2, sd / 2, "필로티 (개방 공간)", ha="center", va="center",
                fontsize=10, color="#888888", fontstyle="italic", zorder=1,
                path_effects=[pe.withStroke(linewidth=2, foreground="white")])

    # v4: 레이어 스타일 조회
    room_layer_style = get_layer_style(design, "rooms")
    room_opacity_mult = room_layer_style.get("opacity", 1.0) if room_layer_style else 1.0

    # 1) 방 그리기
    for room in rooms:
        _draw_room(ax, room, is_piloti, opacity_mult=room_opacity_mult)

    # 2) 벽 그리기 (v3: 채운 다각형, v4: 레이어)
    walls = filtered["walls"]
    doors = filtered["doors"]
    windows = filtered["windows"]

    # 벽이 없으면 방에서 자동 생성 (벽 레이어가 표시일 때만)
    if not walls and rooms and is_layer_visible(design, "walls"):
        walls = _auto_generate_walls(rooms)

    wall_map = {w["id"]: w for w in walls}
    door_map = {}
    for d in doors:
        wid = d.get("wall_id")
        if wid not in door_map:
            door_map[wid] = []
        door_map[wid].append(d)

    window_map = {}
    for w in windows:
        wid = w.get("wall_id")
        if wid not in window_map:
            window_map[wid] = []
        window_map[wid].append(w)

    for wall in walls:
        wall_id = wall["id"]
        wall_doors = door_map.get(wall_id, [])
        wall_windows = window_map.get(wall_id, [])
        _draw_filled_wall(ax, wall, wall_doors, wall_windows)

    # 3) 문 심볼 (v3 전문, v4: 레이어)
    for door in doors:
        draw_door_symbol(ax, door, wall_map)

    # 4) 창문 심볼 (v3 전문, v4: 레이어)
    for win in windows:
        draw_window_symbol(ax, win, wall_map)

    # 5) 기둥
    for col in columns:
        _draw_column(ax, col)

    # 6) 보
    for beam in beams:
        _draw_beam(ax, beam)

    # 7) 계단 (v3)
    for stair in stairs:
        draw_stairs_2d(ax, stair)

    # 8) 발코니 난간 (v3)
    for room in rooms:
        if room.get("type") == "balcony" and room.get("railing"):
            edges = room_to_edges(room)
            draw_balcony_railing(ax, room, edges)

    # 9) 가구 (v3 전문 심볼, v4: 레이어)
    if show_furniture:
        for furn in filtered["furniture"]:
            draw_fixture(ax, furn)

    # 10) 라벨
    if show_labels:
        for room in rooms:
            _draw_room_label(ax, room)

    # 11) 치수 (v3 전문)
    if show_dimensions:
        draw_dimensions(ax, rooms, all_min_x, all_min_y, all_max_x, all_max_y,
                        room_area, room_bbox,
                        walls=walls,
                        user_dimensions=floor.get("dimensions"))

    # 12) 축선 그리드 (v4)
    _draw_grid_lines(ax, design, all_min_x, all_min_y, all_max_x, all_max_y)

    # 13) 지붕 평면도 (v4, 최상층에만 표시)
    if draw_roof_plan and design.get("roof"):
        top_level = max(f["level"] for f in design["floors"])
        if floor.get("level", 0) == top_level:
            draw_roof_plan(ax, design, rooms, all_min_x, all_min_y, all_max_x, all_max_y)

    # 타이틀
    piloti_tag = " [필로티]" if is_piloti else ""
    title = f"{design['name']} - {floor['name']}{piloti_tag}"
    ax.set_title(title, fontsize=12, fontweight="bold", pad=10)
    ax.set_xlabel("m", fontsize=8)
    ax.set_ylabel("m", fontsize=8)
    ax.tick_params(labelsize=7)

    plt.tight_layout()
    fig.savefig(output_path, dpi=150, bbox_inches="tight", facecolor=fig.get_facecolor())
    plt.close(fig)

    return {"success": True, "path": output_path, "format": "png"}


# ============================================================
# 방 그리기
# ============================================================

def _draw_room(ax, room, is_piloti=False, opacity_mult=1.0):
    """방을 다각형/직사각형으로 그리기 (v4: opacity_mult로 레이어 투명도 반영, 바닥재 해칭)"""
    color = room.get("color", "#E0E0E0")
    alpha = (0.3 if is_piloti else 0.55) * opacity_mult

    # 바닥재 해칭 패턴
    floor_mat = room.get("floor_material", "")
    hatch = _floor_material_hatch(floor_mat)

    if "vertices" in room and room["vertices"]:
        verts = room["vertices"]
        polygon = patches.Polygon(
            verts, closed=True,
            linewidth=0, facecolor=color, alpha=alpha, hatch=hatch, zorder=1
        )
        ax.add_patch(polygon)
    else:
        rect = patches.Rectangle(
            (room["x"], room["y"]), room["width"], room["depth"],
            linewidth=0, facecolor=color, alpha=alpha, hatch=hatch, zorder=1
        )
        ax.add_patch(rect)


# ============================================================
# v3: 채운 벽 다각형 (핵심 품질 개선)
# ============================================================

def _wall_polygon_coords(sx, sy, ex, ey, thickness):
    """벽 중심선에서 두께만큼 확장한 사각형 좌표 반환"""
    wall_len = math.hypot(ex - sx, ey - sy)
    if wall_len < 0.01:
        return None
    dx = (ex - sx) / wall_len
    dy = (ey - sy) / wall_len
    nx, ny = -dy * thickness / 2, dx * thickness / 2
    return [
        (sx + nx, sy + ny), (ex + nx, ey + ny),
        (ex - nx, ey - ny), (sx - nx, sy - ny),
    ]


def _draw_filled_wall(ax, wall, doors, windows):
    """v3: 벽을 채운 다각형으로 그리기 (문/창 위치 분할)"""
    sx, sy = wall["start"]
    ex, ey = wall["end"]
    wall_len = math.hypot(ex - sx, ey - sy)
    if wall_len < 0.01:
        return

    is_ext = wall.get("type") == "exterior"
    thickness = wall.get("thickness", 0.2 if is_ext else 0.12)

    # 재질 기반 스타일
    material = wall.get("material")
    if is_ext and material:
        fill_color = get_2d_color(material)
        hatch = get_2d_hatch(material)
        edge_color = "#1A1A1A"
    elif is_ext:
        fill_color = "#2A2A2A"
        hatch = ""
        edge_color = "#1A1A1A"
    else:
        fill_color = "#888888"
        hatch = ""
        edge_color = "#666666"

    alpha = 0.85 if is_ext else 0.6

    dx = (ex - sx) / wall_len
    dy = (ey - sy) / wall_len

    # 개구부 수집
    openings = []
    for d in doors:
        pos = d.get("position", 0)
        w = d.get("width", 0.9)
        openings.append((pos - w / 2, pos + w / 2))
    for w in windows:
        pos = w.get("position", 0)
        ww = w.get("width", 1.5)
        openings.append((pos - ww / 2, pos + ww / 2))
    openings.sort()

    # 벽 세그먼트 계산 (개구부 제외)
    segments = []
    prev = 0
    for op_start, op_end in openings:
        op_start = max(0, op_start)
        op_end = min(wall_len, op_end)
        if op_start > prev + 0.01:
            segments.append((prev, op_start))
        prev = op_end
    if prev < wall_len - 0.01:
        segments.append((prev, wall_len))

    # 개구부가 없으면 전체 벽
    if not openings:
        segments = [(0, wall_len)]

    # 각 세그먼트를 채운 다각형으로
    for seg_start, seg_end in segments:
        s_sx = sx + dx * seg_start
        s_sy = sy + dy * seg_start
        s_ex = sx + dx * seg_end
        s_ey = sy + dy * seg_end
        coords = _wall_polygon_coords(s_sx, s_sy, s_ex, s_ey, thickness)
        if not coords:
            continue

        wall_patch = patches.Polygon(
            coords, closed=True,
            linewidth=0.8 if is_ext else 0.5,
            edgecolor=edge_color,
            facecolor=fill_color,
            alpha=alpha,
            hatch=hatch,
            zorder=3
        )
        ax.add_patch(wall_patch)


# ============================================================
# 벽 자동 생성
# ============================================================

def _auto_generate_walls(rooms):
    """방 경계에서 벽을 생성 (다각형/직사각형 통합)"""
    walls = []
    counter = 0
    edge_set = {}

    for room in rooms:
        edges = room_to_edges(room)
        for start, end in edges:
            key = edge_key(start, end)
            if key not in edge_set:
                edge_set[key] = 0
            edge_set[key] += 1

    for (start, end), count in edge_set.items():
        counter += 1
        walls.append({
            "id": f"wall_{counter}",
            "start": list(start),
            "end": list(end),
            "thickness": 0.12 if count > 1 else 0.2,
            "type": "interior" if count > 1 else "exterior",
        })
    return walls


# ============================================================
# 기둥/보
# ============================================================

def _draw_column(ax, col):
    """기둥 표시 (사각=rect/square, 원형=circle/round)"""
    # position 키 또는 x,y 키 호환
    pos = col.get("position")
    if pos:
        x, y = pos[0], pos[1]
    else:
        x, y = col.get("x", 0), col.get("y", 0)
    size = col.get("size", [col.get("width", 0.4), col.get("depth", 0.4)])
    w, d = size[0], size[1]
    shape = col.get("shape", "rect")

    if shape in ("round", "circle"):
        radius = max(w, d) / 2
        circle = patches.Circle(
            (x, y), radius,
            linewidth=1.5, edgecolor="#333333", facecolor="#A0A0A0",
            alpha=0.8, zorder=6
        )
        ax.add_patch(circle)
        ax.plot([x - radius * 0.5, x + radius * 0.5], [y, y],
                color="#333333", linewidth=0.5, zorder=7)
        ax.plot([x, x], [y - radius * 0.5, y + radius * 0.5],
                color="#333333", linewidth=0.5, zorder=7)
    else:
        rect = patches.Rectangle(
            (x - w / 2, y - d / 2), w, d,
            linewidth=1.5, edgecolor="#333333", facecolor="#A0A0A0",
            alpha=0.8, zorder=6
        )
        ax.add_patch(rect)
        ax.plot([x - w / 2, x + w / 2], [y - d / 2, y + d / 2],
                color="#333333", linewidth=0.5, zorder=7)
        ax.plot([x - w / 2, x + w / 2], [y + d / 2, y - d / 2],
                color="#333333", linewidth=0.5, zorder=7)


def _draw_beam(ax, beam):
    """보를 점선으로 표시"""
    start = beam.get("start", [0, 0])
    end = beam.get("end", [0, 0])
    ax.plot([start[0], end[0]], [start[1], end[1]],
            color="#666666", linewidth=2.0, linestyle=(0, (5, 3)),
            zorder=4)
    mx = (start[0] + end[0]) / 2
    my = (start[1] + end[1]) / 2
    ax.text(mx, my, "B", ha="center", va="center", fontsize=5,
            color="#666666", fontweight="bold", zorder=5,
            path_effects=[pe.withStroke(linewidth=1.5, foreground="white")])


# ============================================================
# 바닥재 해칭
# ============================================================

def _floor_material_hatch(material):
    """바닥 재질에 따른 matplotlib 해칭 패턴"""
    hatch_map = {
        "wood": "//",
        "tile": "++",
        "marble": "xx",
        "stone": "..",
        "carpet": "oo",
        "concrete": "",
    }
    return hatch_map.get(material, "")


# ============================================================
# 라벨
# ============================================================

def _draw_room_label(ax, room):
    """적응형 방 라벨 (다각형 지원)"""
    cx, cy = room_centroid(room)
    area = room_area(room)

    if "vertices" in room and room["vertices"]:
        bbox = room_bbox(room)
        min_dim = min(bbox[2] - bbox[0], bbox[3] - bbox[1])
    else:
        min_dim = min(room.get("width", 0), room.get("depth", 0))

    if min_dim < 1.5:
        label = room["name"]
        fontsize = max(5, min(7, min_dim * 3))
    elif min_dim < 3.0:
        label = f"{room['name']}\n({area:.0f}m\u00b2)"
        fontsize = max(6, min(8, min_dim * 2))
    else:
        floor_mat = room.get("floor_material", "")
        mat_tag = f"\n[{floor_mat}]" if floor_mat and floor_mat != "concrete" else ""
        if "vertices" in room and room["vertices"]:
            label = f"{room['name']}\n({area:.1f}m\u00b2){mat_tag}"
        else:
            label = f"{room['name']}\n{room.get('width',0)}x{room.get('depth',0)}m\n({area:.1f}m\u00b2){mat_tag}"
        fontsize = max(7, min(10, min_dim * 1.8))

    ax.text(cx, cy, label, ha="center", va="center", fontsize=fontsize,
            fontweight="bold", color="#333333", zorder=8,
            path_effects=[pe.withStroke(linewidth=2, foreground="white")])


# ============================================================
# 축선(Grid Line) 렌더링
# ============================================================

def _draw_grid_lines(ax, design, min_x, min_y, max_x, max_y):
    """축선 그리드를 2D 평면도에 표시 (점선 + 원형 라벨)"""
    grid = design.get("column_grid")
    if not grid:
        return
    x_axes = grid.get("x_axes", [])
    y_axes = grid.get("y_axes", [])
    if not x_axes and not y_axes:
        return

    origin = grid.get("origin", [0, 0])
    ox, oy = origin[0], origin[1]
    ext = 1.2  # 축선 연장 길이
    circle_r = 0.4  # 라벨 원 반지름

    # X축선 (세로선)
    for xa in x_axes:
        xv = ox + xa["value"]
        ax.plot([xv, xv], [min_y - ext, max_y + ext],
                color="#CC4444", linewidth=0.6, linestyle=(0, (8, 6)),
                alpha=0.5, zorder=2)
        # 하단 원형 라벨
        circle = patches.Circle((xv, min_y - ext - circle_r - 0.1), circle_r,
            linewidth=1.0, edgecolor="#CC4444", facecolor="white", zorder=9)
        ax.add_patch(circle)
        ax.text(xv, min_y - ext - circle_r - 0.1, xa["label"],
                ha="center", va="center", fontsize=5.5, color="#CC4444",
                fontweight="bold", zorder=10)

    # Y축선 (가로선)
    for ya in y_axes:
        yv = oy + ya["value"]
        ax.plot([min_x - ext, max_x + ext], [yv, yv],
                color="#CC4444", linewidth=0.6, linestyle=(0, (8, 6)),
                alpha=0.5, zorder=2)
        # 좌측 원형 라벨
        circle = patches.Circle((min_x - ext - circle_r - 0.1, yv), circle_r,
            linewidth=1.0, edgecolor="#CC4444", facecolor="white", zorder=9)
        ax.add_patch(circle)
        ax.text(min_x - ext - circle_r - 0.1, yv, ya["label"],
                ha="center", va="center", fontsize=5.5, color="#CC4444",
                fontweight="bold", zorder=10)
