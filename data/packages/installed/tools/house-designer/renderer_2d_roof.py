"""
House Designer v4 - 지붕 2D 평면도 렌더러
평면도 위에 지붕선(용마루, 처마, 경사 방향)을 표시
"""
import math
import matplotlib.patches as patches
import matplotlib.patheffects as pe


def draw_roof_plan(ax, design, rooms, all_min_x, all_min_y, all_max_x, all_max_y):
    """평면도 위에 지붕 평면 표시"""
    roof = design.get("roof", {})
    roof_type = roof.get("type", "hip")
    overhang = roof.get("overhang", 0.3)
    direction = roof.get("direction", "x")

    if roof_type == "flat":
        _draw_flat_roof(ax, all_min_x, all_min_y, all_max_x, all_max_y, overhang)
    elif roof_type == "gable" or roof_type == "gable_glass":
        _draw_gable_roof(ax, all_min_x, all_min_y, all_max_x, all_max_y,
                         overhang, direction)
    elif roof_type == "hip":
        _draw_hip_roof(ax, all_min_x, all_min_y, all_max_x, all_max_y,
                       overhang, direction)
    elif roof_type == "mansard":
        _draw_mansard_roof(ax, all_min_x, all_min_y, all_max_x, all_max_y,
                           overhang)


def _draw_flat_roof(ax, x1, y1, x2, y2, overhang):
    """평지붕: 처마선(점선) + 옥상 접근 표시"""
    ox, oy = overhang, overhang
    # 처마선
    eave = patches.Rectangle(
        (x1 - ox, y1 - oy), (x2 - x1) + ox * 2, (y2 - y1) + oy * 2,
        linewidth=1.2, edgecolor="#888888", facecolor="none",
        linestyle=(0, (8, 4)), zorder=9
    )
    ax.add_patch(eave)


def _draw_gable_roof(ax, x1, y1, x2, y2, overhang, direction):
    """박공 지붕: 용마루선(점선) + 경사 방향 화살표 + 처마선"""
    ox, oy = overhang, overhang
    w = x2 - x1
    h = y2 - y1

    # 처마선
    eave = patches.Rectangle(
        (x1 - ox, y1 - oy), w + ox * 2, h + oy * 2,
        linewidth=1.2, edgecolor="#888888", facecolor="none",
        linestyle=(0, (8, 4)), zorder=9
    )
    ax.add_patch(eave)

    # 용마루선
    if direction == "x":
        # Y축 방향 용마루 (건물 중앙 가로선)
        mid_y = (y1 + y2) / 2
        ax.plot([x1 - ox, x2 + ox], [mid_y, mid_y],
                color="#666666", linewidth=1.5, linestyle=(0, (5, 3)), zorder=10)
        # 경사 방향 화살표 (양쪽)
        _draw_slope_arrow(ax, (x1 + x2) / 2, mid_y + h * 0.15, 0, -90)
        _draw_slope_arrow(ax, (x1 + x2) / 2, mid_y - h * 0.15, 0, 90)
    else:
        # X축 방향 용마루 (건물 중앙 세로선)
        mid_x = (x1 + x2) / 2
        ax.plot([mid_x, mid_x], [y1 - oy, y2 + oy],
                color="#666666", linewidth=1.5, linestyle=(0, (5, 3)), zorder=10)
        _draw_slope_arrow(ax, mid_x + w * 0.15, (y1 + y2) / 2, 0, 0)
        _draw_slope_arrow(ax, mid_x - w * 0.15, (y1 + y2) / 2, 0, 180)


def _draw_hip_roof(ax, x1, y1, x2, y2, overhang, direction):
    """사방경사 지붕: 용마루선 + 4개 골선(능선) + 처마선"""
    ox, oy = overhang, overhang
    w = x2 - x1
    h = y2 - y1

    # 처마선
    eave = patches.Rectangle(
        (x1 - ox, y1 - oy), w + ox * 2, h + oy * 2,
        linewidth=1.2, edgecolor="#888888", facecolor="none",
        linestyle=(0, (8, 4)), zorder=9
    )
    ax.add_patch(eave)

    # 용마루선 (건물 중앙 짧은 축)
    inset = min(w, h) * 0.3
    if w >= h:
        ridge_y = (y1 + y2) / 2
        r_x1 = x1 + inset
        r_x2 = x2 - inset
        ax.plot([r_x1, r_x2], [ridge_y, ridge_y],
                color="#666666", linewidth=1.5, linestyle=(0, (5, 3)), zorder=10)
        # 능선 (4개 대각선)
        for cx, cy in [(x1 - ox, y1 - oy), (x1 - ox, y2 + oy),
                       (x2 + ox, y1 - oy), (x2 + ox, y2 + oy)]:
            rx = r_x1 if cx < (x1 + x2) / 2 else r_x2
            ax.plot([cx, rx], [cy, ridge_y],
                    color="#999999", linewidth=0.8, linestyle=(0, (3, 3)), zorder=10)
    else:
        ridge_x = (x1 + x2) / 2
        r_y1 = y1 + inset
        r_y2 = y2 - inset
        ax.plot([ridge_x, ridge_x], [r_y1, r_y2],
                color="#666666", linewidth=1.5, linestyle=(0, (5, 3)), zorder=10)
        for cx, cy in [(x1 - ox, y1 - oy), (x1 - ox, y2 + oy),
                       (x2 + ox, y1 - oy), (x2 + ox, y2 + oy)]:
            ry = r_y1 if cy < (y1 + y2) / 2 else r_y2
            ax.plot([cx, ridge_x], [cy, ry],
                    color="#999999", linewidth=0.8, linestyle=(0, (3, 3)), zorder=10)

    # 경사 방향 화살표 (4방향)
    cx, cy = (x1 + x2) / 2, (y1 + y2) / 2
    arrow_offset = min(w, h) * 0.15
    _draw_slope_arrow(ax, cx, cy + arrow_offset, 0, -90)  # 위
    _draw_slope_arrow(ax, cx, cy - arrow_offset, 0, 90)   # 아래
    _draw_slope_arrow(ax, cx + arrow_offset, cy, 0, 0)    # 오른쪽
    _draw_slope_arrow(ax, cx - arrow_offset, cy, 0, 180)  # 왼쪽


def _draw_mansard_roof(ax, x1, y1, x2, y2, overhang):
    """맨사드 지붕: 이중 처마선 + 내부 평면"""
    ox, oy = overhang, overhang
    w = x2 - x1
    h = y2 - y1

    # 외부 처마선
    eave = patches.Rectangle(
        (x1 - ox, y1 - oy), w + ox * 2, h + oy * 2,
        linewidth=1.2, edgecolor="#888888", facecolor="none",
        linestyle=(0, (8, 4)), zorder=9
    )
    ax.add_patch(eave)

    # 내부 처마선 (맨사드 꺾임점)
    inset = min(w, h) * 0.2
    inner = patches.Rectangle(
        (x1 + inset, y1 + inset), w - inset * 2, h - inset * 2,
        linewidth=1.0, edgecolor="#999999", facecolor="none",
        linestyle=(0, (5, 3)), zorder=10
    )
    ax.add_patch(inner)

    # 경사 연결선 (4개 모서리)
    corners_outer = [(x1 - ox, y1 - oy), (x2 + ox, y1 - oy),
                     (x2 + ox, y2 + oy), (x1 - ox, y2 + oy)]
    corners_inner = [(x1 + inset, y1 + inset), (x2 - inset, y1 + inset),
                     (x2 - inset, y2 - inset), (x1 + inset, y2 - inset)]
    for co, ci in zip(corners_outer, corners_inner):
        ax.plot([co[0], ci[0]], [co[1], ci[1]],
                color="#999999", linewidth=0.6, linestyle=(0, (3, 3)), zorder=10)


def _draw_slope_arrow(ax, x, y, length_scale, angle_deg):
    """경사 방향 화살표"""
    arrow_len = 0.4
    rad = math.radians(angle_deg)
    dx = arrow_len * math.cos(rad)
    dy = -arrow_len * math.sin(rad)
    ax.annotate("", xy=(x + dx, y + dy), xytext=(x, y),
                arrowprops=dict(arrowstyle="->", color="#888888", lw=0.8),
                zorder=10)
