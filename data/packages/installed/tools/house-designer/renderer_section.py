"""
House Designer v4 - 단면도 렌더러
절단선 기준으로 건물 횡단면 PNG 생성
재질 해칭, 슬라브, 계단 단면, 창문/문 표시, 층고 치수, GL/FL 마커
"""
import math
import os
import importlib.util

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.patches as patches
import matplotlib.patheffects as pe

_pkg_dir = os.path.dirname(os.path.abspath(__file__))


def _load(name):
    path = os.path.join(_pkg_dir, f"{name}.py")
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


_gu = _load("geometry_utils")
_mat = _load("materials")

room_vertices = _gu.room_vertices
room_bbox = _gu.room_bbox
line_segment_intersection = _gu.line_segment_intersection
cut_line_through_design = _gu.cut_line_through_design
get_2d_color = _mat.get_2d_color
get_2d_hatch = _mat.get_2d_hatch

# 한글 폰트 (renderer_2d와 동일)
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

SLAB_THICKNESS = 0.2  # 슬라브 두께 (m)
SCALE = 60


def render_section_view(design, cut_start, cut_end, output_path,
                        view_direction="right", show_dimensions=True):
    """단면도 PNG 생성.
    cut_start, cut_end: [x, y] 평면 좌표 (절단선)
    view_direction: 'right' 또는 'left' (절단면을 어느 방향에서 보는지)
    """
    floors = design.get("floors", [])
    if not floors:
        return {"success": False, "error": "층이 없어 단면도를 생성할 수 없습니다."}

    cs = tuple(cut_start)
    ce = tuple(cut_end)
    cut_len = math.hypot(ce[0] - cs[0], ce[1] - cs[1])
    if cut_len < 0.01:
        return {"success": False, "error": "절단선 길이가 너무 짧습니다."}

    # 절단선 방향 벡터
    dx = (ce[0] - cs[0]) / cut_len
    dy = (ce[1] - cs[1]) / cut_len

    # 교차 정보 수집
    cut_data = cut_line_through_design(design, cs, ce)

    # 건물 전체 높이 계산
    total_height = 0
    for floor in floors:
        elev = floor.get("elevation", 0)
        h = floor.get("height", 2.8)
        total_height = max(total_height, elev + h)

    roof = design.get("roof", {})
    roof_height = roof.get("height", 2.0) if roof.get("type", "flat") != "flat" else 0
    total_height += roof_height + SLAB_THICKNESS

    # 교차점의 절단선 위 위치(t값) 계산
    def project_to_cut(pt):
        """점을 절단선 위에 투영 -> 시작점으로부터의 거리"""
        return (pt[0] - cs[0]) * dx + (pt[1] - cs[1]) * dy

    # 플롯 영역
    padding_h = 2.0
    padding_v = 1.5
    fig_w = max((cut_len + padding_h * 2) * SCALE / 100, 8)
    fig_h = max((total_height + padding_v * 3) * SCALE / 100, 6)

    fig, ax = plt.subplots(1, 1, figsize=(fig_w, fig_h))
    ax.set_xlim(-padding_h, cut_len + padding_h)
    ax.set_ylim(-padding_v, total_height + padding_v)
    ax.set_aspect("equal")
    ax.set_facecolor("#FAFAFA")
    fig.patch.set_facecolor("#FFFFFF")
    ax.grid(True, alpha=0.08, linewidth=0.3, color="#CCCCCC")

    # 1) 지반선 (GL)
    _draw_ground_line(ax, cut_len, padding_h)

    # 2) 층 슬라브
    for floor in floors:
        elev = floor.get("elevation", 0)
        _draw_slab(ax, 0, cut_len, elev, floor, design, cs, ce, dx, dy)

    # 최상층 천장 슬라브
    top_floor = max(floors, key=lambda f: f.get("elevation", 0))
    top_elev = top_floor.get("elevation", 0) + top_floor.get("height", 2.8)
    _draw_slab_line(ax, 0, cut_len, top_elev)

    # 3) 절단된 벽체
    for wall_info in cut_data["walls"]:
        t_pos = project_to_cut(wall_info["intersection"])
        _draw_section_wall(ax, t_pos, wall_info)

    # 4) 절단된 창문
    for win_info in cut_data["windows"]:
        t_pos = project_to_cut(win_info["intersection"])
        _draw_section_window(ax, t_pos, win_info)

    # 5) 절단된 문
    for door_info in cut_data["doors"]:
        t_pos = project_to_cut(door_info["intersection"])
        _draw_section_door(ax, t_pos, door_info)

    # 6) 계단 단면
    for floor in floors:
        for stair in floor.get("stairs", []):
            _draw_section_stair(ax, stair, floor, cs, ce, dx, dy, project_to_cut)

    # 7) 지붕 프로파일
    if roof.get("type", "flat") != "flat":
        _draw_section_roof(ax, design, cut_len, top_elev, roof)

    # 8) 치수
    if show_dimensions:
        _draw_section_dimensions(ax, floors, total_height, cut_len, roof_height)

    # 타이틀
    title = f"{design['name']} - 단면도"
    ax.set_title(title, fontsize=12, fontweight="bold", pad=10)
    ax.set_xlabel("m", fontsize=8)
    ax.set_ylabel("m", fontsize=8)
    ax.tick_params(labelsize=7)

    plt.tight_layout()
    fig.savefig(output_path, dpi=150, bbox_inches="tight", facecolor=fig.get_facecolor())
    plt.close(fig)

    return {"success": True, "path": output_path, "format": "png"}


# ============================================================
# 지반선
# ============================================================

def _draw_ground_line(ax, cut_len, padding):
    """GL(지반선) 그리기"""
    # 지반 해칭 영역
    ground_depth = 0.5
    ground = patches.Rectangle(
        (-padding, -ground_depth), cut_len + padding * 2, ground_depth,
        linewidth=0, facecolor="#D4C8A0", alpha=0.3, hatch="//", zorder=0
    )
    ax.add_patch(ground)

    # GL 선
    ax.plot([-padding, cut_len + padding], [0, 0],
            color="#666666", linewidth=2.0, zorder=5)

    # GL 마커
    ax.text(-padding + 0.2, -0.15, "GL", fontsize=7, fontweight="bold",
            color="#666666", va="top", zorder=6)


# ============================================================
# 슬라브
# ============================================================

def _draw_slab(ax, x_start, x_end, elevation, floor, design, cs, ce, dx, dy):
    """층 슬라브 그리기 (절단 폭에 맞춰)"""
    # 해당 층의 방 범위를 절단선에 투영
    rooms = floor.get("rooms", [])
    if not rooms:
        return

    min_t = float('inf')
    max_t = float('-inf')
    for room in rooms:
        bbox = room_bbox(room)
        corners = [
            (bbox[0], bbox[1]), (bbox[2], bbox[1]),
            (bbox[2], bbox[3]), (bbox[0], bbox[3]),
        ]
        for c in corners:
            t = (c[0] - cs[0]) * dx + (c[1] - cs[1]) * dy
            min_t = min(min_t, t)
            max_t = max(max_t, t)

    if min_t > max_t:
        return

    min_t = max(0, min_t)
    max_t = min(x_end, max_t)

    slab = patches.Rectangle(
        (min_t, elevation - SLAB_THICKNESS), max_t - min_t, SLAB_THICKNESS,
        linewidth=1.0, edgecolor="#333333", facecolor="#A0A0A0",
        alpha=0.6, zorder=3
    )
    ax.add_patch(slab)


def _draw_slab_line(ax, x_start, x_end, elevation):
    """슬라브 상단선"""
    ax.plot([x_start, x_end], [elevation, elevation],
            color="#555555", linewidth=1.5, zorder=4)


# ============================================================
# 절단 벽체
# ============================================================

def _draw_section_wall(ax, t_pos, wall_info):
    """절단된 벽체를 단면에 표시"""
    wall = wall_info["wall"]
    elev = wall_info["floor_elevation"]
    height = wall_info["floor_height"]
    thickness = wall.get("thickness", 0.2)
    material = wall.get("material")
    is_ext = wall.get("type") == "exterior"

    if is_ext and material:
        fill = get_2d_color(material)
        hatch = get_2d_hatch(material)
    elif is_ext:
        fill = "#2A2A2A"
        hatch = ""
    else:
        fill = "#888888"
        hatch = ""

    wall_rect = patches.Rectangle(
        (t_pos - thickness / 2, elev), thickness, height,
        linewidth=1.2 if is_ext else 0.8,
        edgecolor="#1A1A1A" if is_ext else "#555555",
        facecolor=fill,
        alpha=0.85 if is_ext else 0.6,
        hatch=hatch,
        zorder=6
    )
    ax.add_patch(wall_rect)


# ============================================================
# 절단 창문
# ============================================================

def _draw_section_window(ax, t_pos, win_info):
    """절단된 창문 단면"""
    win = win_info["window"]
    elev = win_info["floor_elevation"]
    sill = win.get("sill_height", 0.9)
    win_h = win.get("height", 1.2)
    width = win.get("width", 1.5)

    # 창문 배경 (밝은 하늘색)
    win_rect = patches.Rectangle(
        (t_pos - 0.08, elev + sill), 0.16, win_h,
        linewidth=1.0, edgecolor="#4488AA", facecolor="#C8E8F8",
        alpha=0.7, zorder=7
    )
    ax.add_patch(win_rect)

    # 유리 라인
    mid_y = elev + sill + win_h / 2
    ax.plot([t_pos - 0.06, t_pos + 0.06], [mid_y, mid_y],
            color="#4488AA", linewidth=0.5, zorder=8)

    # sill (하단 선반)
    ax.plot([t_pos - 0.15, t_pos + 0.15], [elev + sill, elev + sill],
            color="#333333", linewidth=1.5, zorder=8)

    # head (상단)
    ax.plot([t_pos - 0.12, t_pos + 0.12], [elev + sill + win_h, elev + sill + win_h],
            color="#333333", linewidth=1.0, zorder=8)


# ============================================================
# 절단 문
# ============================================================

def _draw_section_door(ax, t_pos, door_info):
    """절단된 문 단면"""
    door = door_info["door"]
    elev = door_info["floor_elevation"]
    door_h = 2.1  # 문 높이 표준
    door_w = door.get("width", 0.9)

    # 문 개구부 (빈 공간)
    opening = patches.Rectangle(
        (t_pos - 0.08, elev), 0.16, door_h,
        linewidth=0.8, edgecolor="#888888", facecolor="#FAFAFA",
        alpha=0.9, zorder=7
    )
    ax.add_patch(opening)

    # 문틀 상단
    ax.plot([t_pos - 0.12, t_pos + 0.12], [elev + door_h, elev + door_h],
            color="#333333", linewidth=1.5, zorder=8)


# ============================================================
# 계단 단면
# ============================================================

def _draw_section_stair(ax, stair, floor, cs, ce, dx, dy, project_fn):
    """절단선과 계단이 교차하면 단면 표시"""
    from geometry_utils import stair_footprint
    fp = stair_footprint(stair)  # (min_x, min_y, max_x, max_y)

    # 절단선이 계단 footprint를 지나는지 확인
    corners = [(fp[0], fp[1]), (fp[2], fp[1]), (fp[2], fp[3]), (fp[0], fp[3])]
    edges = [
        (corners[0], corners[1]), (corners[1], corners[2]),
        (corners[2], corners[3]), (corners[3], corners[0])
    ]

    intersections = []
    for e1, e2 in edges:
        pt = line_segment_intersection(cs, ce, e1, e2)
        if pt:
            intersections.append(pt)

    if len(intersections) < 2:
        return  # 절단선이 계단을 가로지르지 않음

    elev = floor.get("elevation", 0)
    num_treads = stair.get("num_treads", 15)
    riser_h = stair.get("riser_height", 0.187)
    tread_d = stair.get("tread_depth", 0.28)

    t1 = project_fn(intersections[0])
    t2 = project_fn(intersections[1])
    t_start = min(t1, t2)
    t_end = max(t1, t2)

    # 계단 단면 그리기 (지그재그)
    stair_width = t_end - t_start
    step_width = stair_width / max(num_treads, 1)

    for i in range(num_treads):
        x = t_start + i * step_width
        y = elev + i * riser_h

        # 디딤판 (수평선)
        ax.plot([x, x + step_width], [y + riser_h, y + riser_h],
                color="#555555", linewidth=1.0, zorder=5)
        # 챌면 (수직선)
        ax.plot([x, x], [y, y + riser_h],
                color="#555555", linewidth=1.0, zorder=5)

    # 마지막 챌면
    ax.plot([t_end, t_end], [elev + (num_treads - 1) * riser_h, elev + num_treads * riser_h],
            color="#555555", linewidth=1.0, zorder=5)


# ============================================================
# 지붕 프로파일
# ============================================================

def _draw_section_roof(ax, design, cut_len, top_elev, roof):
    """지붕 단면 프로파일"""
    roof_type = roof.get("type", "hip")
    roof_h = roof.get("height", 2.0)

    # 건물 폭 범위 계산
    site = design.get("site", {})
    bw = site.get("width", 10)

    # 건물 실제 범위 (모든 방의 x 범위)
    min_x = float('inf')
    max_x = float('-inf')
    for floor in design.get("floors", []):
        for room in floor.get("rooms", []):
            bbox = room_bbox(room)
            min_x = min(min_x, bbox[0])
            max_x = max(max_x, bbox[2])
    if min_x > max_x:
        min_x, max_x = 0, bw

    mid = (min_x + max_x) / 2
    overhang = roof.get("overhang", 0.3)

    if roof_type in ("gable", "gable_glass"):
        # 박공: 삼각형
        pts = [
            (min_x - overhang, top_elev),
            (mid, top_elev + roof_h),
            (max_x + overhang, top_elev),
        ]
        tri = patches.Polygon(pts, closed=True, linewidth=1.5,
                               edgecolor="#333333", facecolor="#8B7355",
                               alpha=0.4, zorder=4)
        ax.add_patch(tri)

    elif roof_type == "hip":
        # 사방경사: 사다리꼴 단면
        ridge_half = (max_x - min_x) * 0.3
        pts = [
            (min_x - overhang, top_elev),
            (mid - ridge_half, top_elev + roof_h),
            (mid + ridge_half, top_elev + roof_h),
            (max_x + overhang, top_elev),
        ]
        trap = patches.Polygon(pts, closed=True, linewidth=1.5,
                                edgecolor="#333333", facecolor="#8B7355",
                                alpha=0.4, zorder=4)
        ax.add_patch(trap)

    elif roof_type == "mansard":
        # 맨사드: 꺾인 형태
        knee = roof_h * 0.6
        pts = [
            (min_x - overhang, top_elev),
            (min_x + 0.5, top_elev + knee),
            (mid, top_elev + roof_h),
            (max_x - 0.5, top_elev + knee),
            (max_x + overhang, top_elev),
        ]
        poly = patches.Polygon(pts, closed=True, linewidth=1.5,
                                edgecolor="#333333", facecolor="#8B7355",
                                alpha=0.4, zorder=4)
        ax.add_patch(poly)


# ============================================================
# 치수
# ============================================================

def _draw_section_dimensions(ax, floors, total_height, cut_len, roof_height):
    """단면도 치수선: FL 레벨 마커 + 층고"""
    dim_color = "#CC0000"
    dim_x = cut_len + 0.8  # 치수선 x 위치

    # GL 레벨
    ax.text(dim_x + 0.3, 0, "GL ±0.00", fontsize=6, color="#666666",
            fontweight="bold", va="center", zorder=10)

    prev_elev = 0
    for floor in sorted(floors, key=lambda f: f.get("elevation", 0)):
        elev = floor.get("elevation", 0)
        height = floor.get("height", 2.8)
        top = elev + height

        # FL 마커 (층 바닥 레벨)
        ax.plot([0, dim_x + 0.1], [elev, elev],
                color="#999999", linewidth=0.3, linestyle="--", zorder=2)
        level_text = f"FL +{elev:.2f}" if elev > 0 else "FL ±0.00"
        ax.text(dim_x + 0.3, elev, level_text, fontsize=6, color=dim_color,
                fontweight="bold", va="center", zorder=10,
                path_effects=[pe.withStroke(linewidth=1.5, foreground="white")])

        # 층고 치수 (세로)
        mid_y = elev + height / 2
        ax.annotate("", xy=(dim_x, top), xytext=(dim_x, elev),
                    arrowprops=dict(arrowstyle="<->", color=dim_color,
                                    lw=0.8, shrinkA=0, shrinkB=0), zorder=9)
        ax.text(dim_x + 0.15, mid_y, f"{height:.2f}",
                fontsize=5.5, color=dim_color, va="center", rotation=90,
                fontweight="bold", zorder=10,
                path_effects=[pe.withStroke(linewidth=1.5, foreground="white")])

    # 최상층 천장 레벨
    top_floor = max(floors, key=lambda f: f.get("elevation", 0))
    top_elev = top_floor.get("elevation", 0) + top_floor.get("height", 2.8)
    ax.text(dim_x + 0.3, top_elev, f"FL +{top_elev:.2f}", fontsize=6,
            color=dim_color, fontweight="bold", va="center", zorder=10,
            path_effects=[pe.withStroke(linewidth=1.5, foreground="white")])

    # 전체 높이
    if roof_height > 0:
        total = top_elev + roof_height
        ax.text(dim_x + 0.3, total, f"최고 +{total:.2f}", fontsize=6,
                color="#666666", fontweight="bold", va="center", zorder=10)
