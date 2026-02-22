"""
House Designer v4 - 입면도 렌더러
4방향(전면/후면/좌측/우측) 외관 투영 PNG 생성
외벽 윤곽선, 재질 해칭, 창문/문 표시, 지붕 프로파일, 층 레벨선, 전체 높이 치수
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
snap = _gu.snap
get_2d_color = _mat.get_2d_color
get_2d_hatch = _mat.get_2d_hatch

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

SLAB_THICKNESS = 0.2
SCALE = 60

# 방향 설정: direction -> (축, 방향, 라벨)
# front: -Y 방향에서 봄 (X축이 수평), rear: +Y에서 봄
# left: -X 방향에서 봄 (Y축이 수평), right: +X에서 봄
DIRECTION_MAP = {
    "front": {"h_axis": "x", "d_axis": "y", "d_dir": -1, "label": "정면도 (전면)"},
    "rear":  {"h_axis": "x", "d_axis": "y", "d_dir": 1,  "label": "배면도 (후면)"},
    "left":  {"h_axis": "y", "d_axis": "x", "d_dir": -1, "label": "좌측면도"},
    "right": {"h_axis": "y", "d_axis": "x", "d_dir": 1,  "label": "우측면도"},
}


def render_elevation_view(design, direction="front", output_path=None,
                           show_dimensions=True):
    """입면도 PNG 생성.
    direction: 'front', 'rear', 'left', 'right'
    """
    floors = design.get("floors", [])
    if not floors:
        return {"success": False, "error": "층이 없어 입면도를 생성할 수 없습니다."}

    dir_info = DIRECTION_MAP.get(direction)
    if not dir_info:
        return {"success": False, "error": f"방향은 front/rear/left/right 중 하나여야 합니다."}

    h_axis = dir_info["h_axis"]  # 수평축
    d_axis = dir_info["d_axis"]  # 깊이축
    d_dir = dir_info["d_dir"]    # 깊이 방향

    # 건물 전체 범위 계산
    bld_range = _building_range(design)

    # 수평 범위
    if h_axis == "x":
        h_min, h_max = bld_range["min_x"], bld_range["max_x"]
    else:
        h_min, h_max = bld_range["min_y"], bld_range["max_y"]

    total_width = h_max - h_min

    # 전체 높이
    total_height = 0
    for floor in floors:
        elev = floor.get("elevation", 0)
        h = floor.get("height", 2.8)
        total_height = max(total_height, elev + h)

    roof = design.get("roof", {})
    roof_h = roof.get("height", 2.0) if roof.get("type", "flat") != "flat" else 0
    total_height_with_roof = total_height + roof_h

    # 플롯
    padding_h = 2.0
    padding_v = 1.5
    fig_w = max((total_width + padding_h * 2) * SCALE / 100, 8)
    fig_h = max((total_height_with_roof + padding_v * 3) * SCALE / 100, 6)

    fig, ax = plt.subplots(1, 1, figsize=(fig_w, fig_h))
    ax.set_xlim(h_min - padding_h, h_max + padding_h)
    ax.set_ylim(-padding_v, total_height_with_roof + padding_v)
    ax.set_aspect("equal")
    ax.set_facecolor("#F5F8FA")
    fig.patch.set_facecolor("#FFFFFF")
    ax.grid(True, alpha=0.08, linewidth=0.3, color="#CCCCCC")

    # 1) 지반선
    _draw_ground_line(ax, h_min, h_max, padding_h)

    # 2) 층별 외벽 그리기
    for floor in sorted(floors, key=lambda f: f.get("elevation", 0)):
        _draw_elevation_floor(ax, design, floor, h_axis, d_axis, d_dir, h_min, h_max)

    # 3) 층별 창문/문
    for floor in sorted(floors, key=lambda f: f.get("elevation", 0)):
        _draw_elevation_openings(ax, floor, h_axis, d_axis, d_dir, h_min)

    # 4) 층 레벨선
    _draw_level_lines(ax, floors, h_min, h_max, padding_h)

    # 5) 지붕 프로파일
    if roof.get("type", "flat") != "flat":
        _draw_elevation_roof(ax, design, h_min, h_max, total_height, roof, h_axis)

    # 6) 치수
    if show_dimensions:
        _draw_elevation_dimensions(ax, floors, h_min, h_max, total_height,
                                    total_height_with_roof, padding_h)

    # 타이틀
    title = f"{design['name']} - {dir_info['label']}"
    ax.set_title(title, fontsize=12, fontweight="bold", pad=10)
    ax.set_xlabel("m", fontsize=8)
    ax.set_ylabel("m", fontsize=8)
    ax.tick_params(labelsize=7)

    plt.tight_layout()
    fig.savefig(output_path, dpi=150, bbox_inches="tight", facecolor=fig.get_facecolor())
    plt.close(fig)

    return {"success": True, "path": output_path, "format": "png"}


# ============================================================
# 건물 범위
# ============================================================

def _building_range(design):
    """건물 전체의 x/y 범위 계산"""
    min_x = float('inf')
    min_y = float('inf')
    max_x = float('-inf')
    max_y = float('-inf')

    for floor in design.get("floors", []):
        for room in floor.get("rooms", []):
            bbox = room_bbox(room)
            min_x = min(min_x, bbox[0])
            min_y = min(min_y, bbox[1])
            max_x = max(max_x, bbox[2])
            max_y = max(max_y, bbox[3])

    if min_x > max_x:
        site = design.get("site", {})
        min_x, min_y = 0, 0
        max_x = site.get("width", 20)
        max_y = site.get("depth", 15)

    return {"min_x": min_x, "min_y": min_y, "max_x": max_x, "max_y": max_y}


# ============================================================
# 지반선
# ============================================================

def _draw_ground_line(ax, h_min, h_max, padding):
    """GL 선"""
    ground = patches.Rectangle(
        (h_min - padding, -0.5), (h_max - h_min) + padding * 2, 0.5,
        linewidth=0, facecolor="#D4C8A0", alpha=0.3, hatch="//", zorder=0
    )
    ax.add_patch(ground)
    ax.plot([h_min - padding, h_max + padding], [0, 0],
            color="#666666", linewidth=2.0, zorder=5)
    ax.text(h_min - padding + 0.2, -0.15, "GL", fontsize=7,
            fontweight="bold", color="#666666", va="top", zorder=6)


# ============================================================
# 층별 외벽
# ============================================================

def _draw_elevation_floor(ax, design, floor, h_axis, d_axis, d_dir, h_min, h_max):
    """한 층의 외벽을 입면도로 투영"""
    elev = floor.get("elevation", 0)
    height = floor.get("height", 2.8)
    walls = floor.get("walls", [])
    is_piloti = floor.get("is_piloti", False)

    # 외벽 중 보이는 면(d_axis 방향의 가장 앞쪽) 필터
    exterior_walls = [w for w in walls if w.get("type") == "exterior"]

    # 외벽을 수평축(h_axis)에 투영
    facade = design.get("facade_defaults", {})
    default_material = facade.get("material", "concrete")

    if is_piloti:
        # 필로티: 기둥만 그리기
        for col in floor.get("columns", []):
            cx = col.get("x", 0)
            cy = col.get("y", 0)
            cw = col.get("width", 0.4)
            h_pos = cx if h_axis == "x" else cy

            col_rect = patches.Rectangle(
                (h_pos - cw / 2, elev), cw, height,
                linewidth=1.0, edgecolor="#333333", facecolor="#A0A0A0",
                alpha=0.7, zorder=4
            )
            ax.add_patch(col_rect)
        return

    # 보이는 외벽 찾기: d_axis 기준으로 가장 앞(d_dir 방향) 벽
    visible_walls = _filter_visible_walls(exterior_walls, h_axis, d_axis, d_dir)

    for wall_info in visible_walls:
        wall = wall_info["wall"]
        h_start = wall_info["h_start"]
        h_end = wall_info["h_end"]
        material = wall.get("material", default_material)

        fill = get_2d_color(material) if material else "#C0BEB5"
        hatch = get_2d_hatch(material) if material else ""

        wall_rect = patches.Rectangle(
            (h_start, elev), h_end - h_start, height,
            linewidth=1.2, edgecolor="#333333", facecolor=fill,
            alpha=0.7, hatch=hatch, zorder=3
        )
        ax.add_patch(wall_rect)

    # 외벽이 없으면 전체 폭에 기본 벽 그리기
    if not visible_walls:
        wall_rect = patches.Rectangle(
            (h_min, elev), h_max - h_min, height,
            linewidth=1.2, edgecolor="#333333", facecolor=get_2d_color(default_material),
            alpha=0.5, hatch=get_2d_hatch(default_material), zorder=3
        )
        ax.add_patch(wall_rect)


def _filter_visible_walls(exterior_walls, h_axis, d_axis, d_dir):
    """외벽 중 보이는 면에 해당하는 벽 필터링 + 수평축 투영"""
    result = []
    h_idx = 0 if h_axis == "x" else 1
    d_idx = 0 if d_axis == "x" else 1

    for wall in exterior_walls:
        sx, sy = wall["start"]
        ex, ey = wall["end"]

        s = [sx, sy]
        e = [ex, ey]

        # 벽이 d_axis에 수직인지 확인 (즉, h_axis 방향으로 뻗는 벽)
        d_diff = abs(s[d_idx] - e[d_idx])
        h_diff = abs(s[h_idx] - e[h_idx])

        if d_diff < 0.01 and h_diff > 0.01:
            # h_axis 방향으로 뻗는 벽 = 입면에서 보이는 벽
            h_start = min(s[h_idx], e[h_idx])
            h_end = max(s[h_idx], e[h_idx])
            d_pos = s[d_idx]

            result.append({
                "wall": wall,
                "h_start": h_start,
                "h_end": h_end,
                "d_pos": d_pos,
            })

    # d_dir 방향으로 가장 앞쪽 벽만 (같은 h 범위에서)
    if not result:
        return result

    if d_dir > 0:
        # 가장 큰 d_pos
        max_d = max(r["d_pos"] for r in result)
        result = [r for r in result if abs(r["d_pos"] - max_d) < 0.5]
    else:
        # 가장 작은 d_pos
        min_d = min(r["d_pos"] for r in result)
        result = [r for r in result if abs(r["d_pos"] - min_d) < 0.5]

    return result


# ============================================================
# 창문/문
# ============================================================

def _draw_elevation_openings(ax, floor, h_axis, d_axis, d_dir, h_min):
    """입면도에 창문/문 표시"""
    elev = floor.get("elevation", 0)
    height = floor.get("height", 2.8)
    walls = floor.get("walls", [])
    wall_map = {w["id"]: w for w in walls}

    h_idx = 0 if h_axis == "x" else 1
    d_idx = 0 if d_axis == "x" else 1

    # 보이는 외벽에 부착된 창문/문만 표시
    visible_wall_ids = set()
    for wall in walls:
        if wall.get("type") != "exterior":
            continue
        sx, sy = wall["start"]
        ex, ey = wall["end"]
        s = [sx, sy]
        e = [ex, ey]
        if abs(s[d_idx] - e[d_idx]) < 0.01 and abs(s[h_idx] - e[h_idx]) > 0.01:
            visible_wall_ids.add(wall["id"])

    # 창문
    for win in floor.get("windows", []):
        wid = win.get("wall_id")
        if wid not in visible_wall_ids:
            continue
        wall = wall_map.get(wid)
        if not wall:
            continue

        w_pos = _opening_h_position(wall, win.get("position", 0), h_axis)
        w_width = win.get("width", 1.5)
        w_height = win.get("height", 1.2)
        sill_h = win.get("sill_height", 0.9)

        # 창문 사각형
        win_rect = patches.Rectangle(
            (w_pos - w_width / 2, elev + sill_h), w_width, w_height,
            linewidth=1.0, edgecolor="#4488AA", facecolor="#C8E8F8",
            alpha=0.6, zorder=5
        )
        ax.add_patch(win_rect)

        # 십자 분할선
        cx = w_pos
        cy = elev + sill_h + w_height / 2
        ax.plot([w_pos - w_width / 2, w_pos + w_width / 2], [cy, cy],
                color="#4488AA", linewidth=0.5, zorder=6)
        ax.plot([cx, cx], [elev + sill_h, elev + sill_h + w_height],
                color="#4488AA", linewidth=0.5, zorder=6)

    # 문
    for door in floor.get("doors", []):
        wid = door.get("wall_id")
        if wid not in visible_wall_ids:
            continue
        wall = wall_map.get(wid)
        if not wall:
            continue

        d_pos = _opening_h_position(wall, door.get("position", 0), h_axis)
        d_width = door.get("width", 0.9)
        door_h = 2.1

        door_rect = patches.Rectangle(
            (d_pos - d_width / 2, elev), d_width, door_h,
            linewidth=1.0, edgecolor="#8B6914", facecolor="#DEB887",
            alpha=0.6, zorder=5
        )
        ax.add_patch(door_rect)

        # 문 패널 라인
        ax.plot([d_pos, d_pos], [elev, elev + door_h],
                color="#8B6914", linewidth=0.5, zorder=6)


def _opening_h_position(wall, position, h_axis):
    """벽 위 개구부의 수평축(h_axis) 위치 계산"""
    sx, sy = wall["start"]
    ex, ey = wall["end"]
    wlen = math.hypot(ex - sx, ey - sy)
    if wlen < 0.01:
        return sx if h_axis == "x" else sy

    t = position / wlen
    if h_axis == "x":
        return sx + t * (ex - sx)
    else:
        return sy + t * (ey - sy)


# ============================================================
# 층 레벨선
# ============================================================

def _draw_level_lines(ax, floors, h_min, h_max, padding):
    """층 바닥 레벨 점선"""
    for floor in floors:
        elev = floor.get("elevation", 0)
        ax.plot([h_min - padding * 0.5, h_max + padding * 0.5], [elev, elev],
                color="#AAAAAA", linewidth=0.4, linestyle="--", zorder=1)


# ============================================================
# 지붕 프로파일
# ============================================================

def _draw_elevation_roof(ax, design, h_min, h_max, top_elev, roof, h_axis):
    """지붕 입면도 프로파일"""
    roof_type = roof.get("type", "hip")
    roof_h = roof.get("height", 2.0)
    overhang = roof.get("overhang", 0.3)
    mid = (h_min + h_max) / 2

    if roof_type in ("gable", "gable_glass"):
        direction = roof.get("direction", "x")
        if (direction == "x" and h_axis == "x") or (direction == "z" and h_axis == "y"):
            # 능선 방향과 수직 -> 삼각형
            pts = [
                (h_min - overhang, top_elev),
                (mid, top_elev + roof_h),
                (h_max + overhang, top_elev),
            ]
        else:
            # 능선 방향과 평행 -> 사각형
            pts = [
                (h_min - overhang, top_elev),
                (h_min - overhang, top_elev + roof_h),
                (h_max + overhang, top_elev + roof_h),
                (h_max + overhang, top_elev),
            ]
        poly = patches.Polygon(pts, closed=True, linewidth=1.5,
                                edgecolor="#333333", facecolor="#8B7355",
                                alpha=0.4, zorder=4)
        ax.add_patch(poly)

    elif roof_type == "hip":
        ridge_half = (h_max - h_min) * 0.2
        pts = [
            (h_min - overhang, top_elev),
            (mid - ridge_half, top_elev + roof_h),
            (mid + ridge_half, top_elev + roof_h),
            (h_max + overhang, top_elev),
        ]
        poly = patches.Polygon(pts, closed=True, linewidth=1.5,
                                edgecolor="#333333", facecolor="#8B7355",
                                alpha=0.4, zorder=4)
        ax.add_patch(poly)

    elif roof_type == "mansard":
        knee = roof_h * 0.6
        pts = [
            (h_min - overhang, top_elev),
            (h_min + 0.5, top_elev + knee),
            (h_min + 1.0, top_elev + roof_h),
            (h_max - 1.0, top_elev + roof_h),
            (h_max - 0.5, top_elev + knee),
            (h_max + overhang, top_elev),
        ]
        poly = patches.Polygon(pts, closed=True, linewidth=1.5,
                                edgecolor="#333333", facecolor="#8B7355",
                                alpha=0.4, zorder=4)
        ax.add_patch(poly)

    elif roof_type == "flat":
        pass  # 이미 처리됨


# ============================================================
# 치수
# ============================================================

def _draw_elevation_dimensions(ax, floors, h_min, h_max, top_elev,
                                total_height, padding):
    """입면도 치수: 전체 폭, 전체 높이, 층고"""
    dim_color = "#CC0000"

    # 전체 폭 (하단)
    y_dim = -0.8
    ax.plot([h_min, h_max], [y_dim, y_dim], color=dim_color, linewidth=0.8, zorder=9)
    for tx in [h_min, h_max]:
        ax.plot([tx, tx], [y_dim - 0.1, 0], color=dim_color, linewidth=0.4, zorder=9)
        tick_s = 0.1
        ax.plot([tx - tick_s, tx + tick_s], [y_dim - tick_s, y_dim + tick_s],
                color=dim_color, linewidth=1.0, zorder=10)
    width = h_max - h_min
    ax.text((h_min + h_max) / 2, y_dim - 0.25, f"{width:.2f}",
            ha="center", va="top", fontsize=7, color=dim_color,
            fontweight="bold", zorder=10,
            path_effects=[pe.withStroke(linewidth=2, foreground="white")])

    # 전체 높이 (우측)
    x_dim = h_max + 0.8
    ax.annotate("", xy=(x_dim, total_height), xytext=(x_dim, 0),
                arrowprops=dict(arrowstyle="<->", color=dim_color,
                                lw=0.8, shrinkA=0, shrinkB=0), zorder=9)
    ax.text(x_dim + 0.2, total_height / 2, f"{total_height:.2f}",
            va="center", fontsize=7, color=dim_color, fontweight="bold",
            rotation=90, zorder=10,
            path_effects=[pe.withStroke(linewidth=2, foreground="white")])

    # 층별 FL 마커 (좌측)
    x_fl = h_min - 0.5
    for floor in sorted(floors, key=lambda f: f.get("elevation", 0)):
        elev = floor.get("elevation", 0)
        height = floor.get("height", 2.8)
        level_text = f"+{elev:.1f}" if elev > 0 else "±0.0"
        ax.text(x_fl, elev, f"FL {level_text}", fontsize=5.5,
                color="#666666", fontweight="bold", va="center", ha="right",
                zorder=10, path_effects=[pe.withStroke(linewidth=1.5, foreground="white")])

    # 최상층 레벨
    ax.text(x_fl, top_elev, f"FL +{top_elev:.1f}", fontsize=5.5,
            color="#666666", fontweight="bold", va="center", ha="right",
            zorder=10, path_effects=[pe.withStroke(linewidth=1.5, foreground="white")])
