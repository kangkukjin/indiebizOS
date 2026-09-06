"""
House Designer v4 - 전문 건축 치수선 렌더러
건축 표준 치수선 (틱마크/연장선), 축척 바, 방위표
v4: 다각형 방 치수, 연속 치수 체인, 사용자 지정 치수선, FL 레벨 마커
"""
import math
import matplotlib.patches as patches
import matplotlib.patheffects as pe


# ============================================================
# 전문 치수선 (메인 진입점)
# ============================================================

def draw_dimensions(ax, rooms, min_x, min_y, max_x, max_y, room_area_fn, room_bbox_fn,
                    walls=None, user_dimensions=None):
    """전문 건축 치수선: 외곽 + 개별 방 + 축척 바 + 방위표"""

    # 1) 외곽 치수선
    _draw_outer_dimensions(ax, min_x, min_y, max_x, max_y)

    # 2) 개별 방 치수선
    for room in rooms:
        if "vertices" in room and room["vertices"]:
            _draw_polygon_room_dimensions(ax, room)
        else:
            _draw_room_dimensions(ax, room)

    # 3) 연속 치수 체인 (벽-개구부)
    if walls:
        _draw_continuous_chain(ax, walls, min_x, min_y, max_x, max_y)

    # 4) 사용자 지정 치수선
    if user_dimensions:
        for dim in user_dimensions:
            _draw_user_dimension(ax, dim)

    # 5) 축척 바
    _draw_scale_bar(ax, min_x, min_y, max_x, max_y)

    # 6) 방위표
    _draw_north_arrow(ax, max_x, max_y)


# ============================================================
# 외곽 치수선 (건축 표준: 연장선 + 틱마크)
# ============================================================

def _draw_outer_dimensions(ax, min_x, min_y, max_x, max_y):
    """외곽 치수: 연장선 + 45도 틱마크 + 치수 텍스트"""
    total_w = max_x - min_x
    total_h = max_y - min_y
    offset = 0.8
    ext_len = 0.3  # 연장선 돌출 길이
    tick_size = 0.12  # 틱마크 크기

    dim_color = "#CC0000"
    dim_lw = 0.8
    fontsize = 7

    # --- 하단 가로 치수 ---
    y_dim = min_y - offset

    # 연장선 (벽에서 치수선까지)
    ax.plot([min_x, min_x], [min_y, y_dim - ext_len],
            color=dim_color, linewidth=0.4, zorder=9)
    ax.plot([max_x, max_x], [min_y, y_dim - ext_len],
            color=dim_color, linewidth=0.4, zorder=9)

    # 치수선
    ax.plot([min_x, max_x], [y_dim, y_dim],
            color=dim_color, linewidth=dim_lw, zorder=9)

    # 틱마크 (45도 슬래시)
    for tx in [min_x, max_x]:
        ax.plot([tx - tick_size, tx + tick_size],
                [y_dim - tick_size, y_dim + tick_size],
                color=dim_color, linewidth=1.2, zorder=10)

    # 치수 텍스트
    ax.text((min_x + max_x) / 2, y_dim - 0.3, f"{total_w:.2f}",
            ha="center", va="top", fontsize=fontsize, color=dim_color,
            fontweight="bold", zorder=10,
            path_effects=[pe.withStroke(linewidth=2, foreground="white")])

    # --- 좌측 세로 치수 ---
    x_dim = min_x - offset

    # 연장선
    ax.plot([min_x, x_dim - ext_len], [min_y, min_y],
            color=dim_color, linewidth=0.4, zorder=9)
    ax.plot([min_x, x_dim - ext_len], [max_y, max_y],
            color=dim_color, linewidth=0.4, zorder=9)

    # 치수선
    ax.plot([x_dim, x_dim], [min_y, max_y],
            color=dim_color, linewidth=dim_lw, zorder=9)

    # 틱마크
    for ty in [min_y, max_y]:
        ax.plot([x_dim - tick_size, x_dim + tick_size],
                [ty - tick_size, ty + tick_size],
                color=dim_color, linewidth=1.2, zorder=10)

    # 치수 텍스트
    ax.text(x_dim - 0.3, (min_y + max_y) / 2, f"{total_h:.2f}",
            ha="right", va="center", fontsize=fontsize, color=dim_color,
            fontweight="bold", rotation=90, zorder=10,
            path_effects=[pe.withStroke(linewidth=2, foreground="white")])


# ============================================================
# 개별 직사각형 방 치수선
# ============================================================

def _draw_room_dimensions(ax, room):
    """개별 직사각형 방의 치수 (건축 표준 틱마크)"""
    rx, ry = room["x"], room["y"]
    rw, rd = room["width"], room["depth"]
    dim_color = "#777777"
    dim_font = 5
    tick_s = 0.06
    inset = 0.2

    # 하단 가로 치수
    dim_y = ry + inset
    ax.plot([rx + inset, rx + rw - inset], [dim_y, dim_y],
            color=dim_color, linewidth=0.4, zorder=6)
    # 틱마크
    for tx in [rx + inset, rx + rw - inset]:
        ax.plot([tx - tick_s, tx + tick_s], [dim_y - tick_s, dim_y + tick_s],
                color=dim_color, linewidth=0.7, zorder=6)
    ax.text(rx + rw / 2, dim_y + 0.12, f"{rw:.1f}",
            ha="center", va="bottom", fontsize=dim_font, color=dim_color, zorder=7,
            path_effects=[pe.withStroke(linewidth=1, foreground="white")])

    # 좌측 세로 치수
    dim_x = rx + inset
    ax.plot([dim_x, dim_x], [ry + inset, ry + rd - inset],
            color=dim_color, linewidth=0.4, zorder=6)
    for ty in [ry + inset, ry + rd - inset]:
        ax.plot([dim_x - tick_s, dim_x + tick_s], [ty - tick_s, ty + tick_s],
                color=dim_color, linewidth=0.7, zorder=6)
    ax.text(dim_x + 0.12, ry + rd / 2, f"{rd:.1f}",
            ha="left", va="center", fontsize=dim_font, color=dim_color,
            rotation=90, zorder=7,
            path_effects=[pe.withStroke(linewidth=1, foreground="white")])


# ============================================================
# 다각형 방 치수선 (v4 신규)
# ============================================================

def _draw_polygon_room_dimensions(ax, room):
    """다각형 방 각 변의 길이를 표시"""
    verts = room.get("vertices", [])
    if len(verts) < 3:
        return

    dim_color = "#888888"
    dim_font = 4.5
    offset_dist = 0.25  # 치수 텍스트 오프셋

    n = len(verts)
    for i in range(n):
        x1, y1 = verts[i]
        x2, y2 = verts[(i + 1) % n]

        edge_len = math.hypot(x2 - x1, y2 - y1)
        if edge_len < 0.3:
            continue  # 너무 짧은 변은 스킵

        # 변 중점
        mx = (x1 + x2) / 2
        my = (y1 + y2) / 2

        # 변에 수직인 외향 방향 (텍스트 오프셋용)
        dx = x2 - x1
        dy = y2 - y1
        # 외향 노멀: 반시계 방향 가정 시 오른쪽이 외향
        nx = dy / edge_len
        ny = -dx / edge_len

        tx = mx + nx * offset_dist
        ty = my + ny * offset_dist

        # 변 각도
        angle = math.degrees(math.atan2(dy, dx))
        # 읽기 쉽도록 회전 보정
        if angle > 90:
            angle -= 180
        elif angle < -90:
            angle += 180

        ax.text(tx, ty, f"{edge_len:.1f}",
                ha="center", va="center", fontsize=dim_font,
                color=dim_color, rotation=angle, zorder=7,
                path_effects=[pe.withStroke(linewidth=1, foreground="white")])


# ============================================================
# 연속 치수 체인 (v4 신규)
# ============================================================

def _draw_continuous_chain(ax, walls, min_x, min_y, max_x, max_y):
    """하단에 벽 분할 연속 치수 체인
    외벽의 X축 분할점을 기준으로 연속 치수를 표시"""
    dim_color = "#0066AA"
    offset = 1.4  # 외곽 치수보다 더 바깥에
    tick_size = 0.08
    fontsize = 5.5

    # 하단 가로 체인: Y축 최소인 외벽의 X 분할점 수집
    bottom_walls = []
    for wall in walls:
        if wall.get("type") != "exterior":
            continue
        sx, sy = wall["start"]
        ex, ey = wall["end"]
        # 하단 수평 벽 (y 값이 min_y 근처)
        if abs(sy - min_y) < 0.3 and abs(ey - min_y) < 0.3 and abs(sx - ex) > 0.1:
            bottom_walls.append((min(sx, ex), max(sx, ex)))

    if not bottom_walls:
        return

    # X 좌표 정렬, 분할점 수집
    x_points = set()
    for ws, we in bottom_walls:
        x_points.add(round(ws, 2))
        x_points.add(round(we, 2))
    x_points = sorted(x_points)

    if len(x_points) < 2:
        return

    y_dim = min_y - offset

    # 연장선
    for xp in x_points:
        ax.plot([xp, xp], [min_y, y_dim - 0.1],
                color=dim_color, linewidth=0.3, zorder=8)

    # 체인 치수선
    ax.plot([x_points[0], x_points[-1]], [y_dim, y_dim],
            color=dim_color, linewidth=0.6, zorder=8)

    # 분할점 틱마크 + 구간 치수
    for i, xp in enumerate(x_points):
        ax.plot([xp - tick_size, xp + tick_size],
                [y_dim - tick_size, y_dim + tick_size],
                color=dim_color, linewidth=0.8, zorder=9)

        # 구간 치수 텍스트
        if i < len(x_points) - 1:
            seg_len = x_points[i + 1] - x_points[i]
            if seg_len > 0.5:  # 너무 짧은 구간은 생략
                mid_x = (x_points[i] + x_points[i + 1]) / 2
                ax.text(mid_x, y_dim - 0.2, f"{seg_len:.2f}",
                        ha="center", va="top", fontsize=fontsize, color=dim_color,
                        zorder=9,
                        path_effects=[pe.withStroke(linewidth=1, foreground="white")])


# ============================================================
# 사용자 지정 치수선 (v4 신규)
# ============================================================

def _draw_user_dimension(ax, dim):
    """사용자 지정 두 점 사이 치수선
    dim: {"start": [x1, y1], "end": [x2, y2], "offset": 0.5, "label": ""}
    """
    start = dim.get("start", [0, 0])
    end = dim.get("end", [0, 0])
    offset = dim.get("offset", 0.5)
    label = dim.get("label", "")

    x1, y1 = start
    x2, y2 = end
    length = math.hypot(x2 - x1, y2 - y1)
    if length < 0.01:
        return

    # 방향 벡터, 법선 벡터
    dx = (x2 - x1) / length
    dy = (y2 - y1) / length
    nx = -dy * offset
    ny = dx * offset

    # 치수선 위치 (오프셋 적용)
    ds_x = x1 + nx
    ds_y = y1 + ny
    de_x = x2 + nx
    de_y = y2 + ny

    dim_color = "#990099"
    tick_size = 0.1

    # 연장선
    ax.plot([x1, ds_x], [y1, ds_y], color=dim_color, linewidth=0.3, zorder=8)
    ax.plot([x2, de_x], [y2, de_y], color=dim_color, linewidth=0.3, zorder=8)

    # 치수선
    ax.plot([ds_x, de_x], [ds_y, de_y], color=dim_color, linewidth=0.7, zorder=8)

    # 틱마크
    for tx, ty in [(ds_x, ds_y), (de_x, de_y)]:
        ax.plot([tx - dx * tick_size + nx * 0.3, tx + dx * tick_size - nx * 0.3],
                [ty - dy * tick_size + ny * 0.3, ty + dy * tick_size - ny * 0.3],
                color=dim_color, linewidth=1.0, zorder=9)

    # 텍스트
    text = label if label else f"{length:.2f}"
    mid_x = (ds_x + de_x) / 2
    mid_y = (ds_y + de_y) / 2
    angle = math.degrees(math.atan2(dy, dx))
    if angle > 90:
        angle -= 180
    elif angle < -90:
        angle += 180

    ax.text(mid_x, mid_y, text,
            ha="center", va="center", fontsize=6, color=dim_color,
            fontweight="bold", rotation=angle, zorder=10,
            path_effects=[pe.withStroke(linewidth=1.5, foreground="white")])


# ============================================================
# FL 레벨 마커 (v4 신규 — 단면도에서도 사용)
# ============================================================

def draw_floor_level_marker(ax, x, elevation, label=None):
    """FL 레벨 마커: 삼각형 + 레벨 텍스트
    단면도/입면도에서 사용"""
    dim_color = "#CC0000"
    tri_size = 0.15

    # 삼각형 마커
    tri = patches.Polygon([
        (x, elevation),
        (x - tri_size, elevation - tri_size),
        (x + tri_size, elevation - tri_size),
    ], closed=True, facecolor=dim_color, edgecolor=dim_color,
        linewidth=0.5, zorder=10)
    ax.add_patch(tri)

    # 레벨 텍스트
    text = label if label else (f"FL +{elevation:.2f}" if elevation > 0 else "FL ±0.00")
    ax.text(x, elevation - tri_size - 0.1, text,
            ha="center", va="top", fontsize=5.5, color=dim_color,
            fontweight="bold", zorder=10,
            path_effects=[pe.withStroke(linewidth=1.5, foreground="white")])


# ============================================================
# 축척 바
# ============================================================

def _draw_scale_bar(ax, min_x, min_y, max_x, max_y):
    """우측 하단 축척 바 (1m + 5m 마커)"""
    bar_y = min_y - 1.5
    bar_x_start = max_x - 6.0
    bar_color = "#333333"
    bar_lw = 2.0
    tick_h = 0.15
    fontsize = 5.5

    # 5m 바
    bar_5m_end = bar_x_start + 5.0
    ax.plot([bar_x_start, bar_5m_end], [bar_y, bar_y],
            color=bar_color, linewidth=bar_lw, solid_capstyle="butt", zorder=10)

    # 시작 틱
    ax.plot([bar_x_start, bar_x_start], [bar_y - tick_h, bar_y + tick_h],
            color=bar_color, linewidth=1.0, zorder=10)
    ax.text(bar_x_start, bar_y - tick_h - 0.1, "0",
            ha="center", va="top", fontsize=fontsize, color=bar_color, zorder=10)

    # 1m 틱
    x_1m = bar_x_start + 1.0
    ax.plot([x_1m, x_1m], [bar_y - tick_h, bar_y + tick_h],
            color=bar_color, linewidth=1.0, zorder=10)
    ax.text(x_1m, bar_y - tick_h - 0.1, "1m",
            ha="center", va="top", fontsize=fontsize, color=bar_color, zorder=10)

    # 5m 끝 틱
    ax.plot([bar_5m_end, bar_5m_end], [bar_y - tick_h, bar_y + tick_h],
            color=bar_color, linewidth=1.0, zorder=10)
    ax.text(bar_5m_end, bar_y - tick_h - 0.1, "5m",
            ha="center", va="top", fontsize=fontsize, color=bar_color, zorder=10)

    # 채움 패턴 (1m 단위 흑백 교대)
    for i in range(5):
        color = bar_color if i % 2 == 0 else "#FFFFFF"
        rect = patches.Rectangle((bar_x_start + i, bar_y - tick_h * 0.5),
            1.0, tick_h, linewidth=0.5, edgecolor=bar_color,
            facecolor=color, zorder=10)
        ax.add_patch(rect)


# ============================================================
# 방위표 (North Arrow)
# ============================================================

def _draw_north_arrow(ax, max_x, max_y):
    """우측 상단 방위 화살표"""
    cx = max_x + 0.8
    cy = max_y - 0.3
    arrow_len = 0.6
    arrow_w = 0.15
    color = "#333333"

    # 화살표 (위 방향 = 북쪽)
    ax.annotate("", xy=(cx, cy + arrow_len), xytext=(cx, cy),
                arrowprops=dict(arrowstyle="-|>", color=color, lw=1.5,
                                mutation_scale=10), zorder=10)

    # 좌측 반 삼각형 (채움)
    tri = patches.Polygon([
        (cx, cy + arrow_len),
        (cx - arrow_w, cy + arrow_len * 0.3),
        (cx, cy + arrow_len * 0.45),
    ], closed=True, facecolor=color, edgecolor=color, linewidth=0.5, zorder=10)
    ax.add_patch(tri)

    # 우측 반 삼각형 (비어있음)
    tri2 = patches.Polygon([
        (cx, cy + arrow_len),
        (cx + arrow_w, cy + arrow_len * 0.3),
        (cx, cy + arrow_len * 0.45),
    ], closed=True, facecolor="white", edgecolor=color, linewidth=0.5, zorder=10)
    ax.add_patch(tri2)

    # "N" 글자
    ax.text(cx, cy + arrow_len + 0.15, "N",
            ha="center", va="bottom", fontsize=8, fontweight="bold",
            color=color, zorder=10)
