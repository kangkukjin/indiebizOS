"""
House Designer v4 - 도면 규격 모듈
제목란(Title Block), 도면 자동 번호, 실명 표기, 프로젝트 정보 관리
"""
import os
import importlib.util
from datetime import datetime

import matplotlib.patches as patches
import matplotlib.patheffects as pe

_pkg_dir = os.path.dirname(os.path.abspath(__file__))


def _load(name):
    path = os.path.join(_pkg_dir, f"{name}.py")
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


# ============================================================
# 용지 규격
# ============================================================

PAPER_SIZES = {
    "A4": {"width_mm": 297, "height_mm": 210},       # 가로 (Landscape)
    "A3": {"width_mm": 420, "height_mm": 297},
    "A2": {"width_mm": 594, "height_mm": 420},
    "A1": {"width_mm": 841, "height_mm": 594},
}

# 축척 -> 실제 1m가 도면상 몇 mm
SCALE_MAP = {
    "1:50": 20.0,     # 1m = 20mm
    "1:100": 10.0,    # 1m = 10mm
    "1:200": 5.0,     # 1m = 5mm
}


def get_drawable_area(paper_size="A3", scale="1:100"):
    """주어진 용지/축척에서 실제 그릴 수 있는 영역(m) 계산
    제목란(하단 20mm) 제외"""
    paper = PAPER_SIZES.get(paper_size, PAPER_SIZES["A3"])
    margin = 10  # 10mm 마진
    title_h = 20  # 제목란 높이
    draw_w_mm = paper["width_mm"] - margin * 2
    draw_h_mm = paper["height_mm"] - margin * 2 - title_h
    mm_per_m = SCALE_MAP.get(scale, 10.0)

    return {
        "width_m": draw_w_mm / mm_per_m,
        "height_m": draw_h_mm / mm_per_m,
        "paper_w_mm": paper["width_mm"],
        "paper_h_mm": paper["height_mm"],
        "mm_per_m": mm_per_m,
    }


# ============================================================
# 프로젝트 정보
# ============================================================

def get_project_info(design):
    """설계에서 프로젝트 정보 가져오기 (없으면 기본값)"""
    info = design.get("project_info", {})
    return {
        "project_name": info.get("project_name", design.get("name", "무제")),
        "designer": info.get("designer", ""),
        "company": info.get("company", ""),
        "north_direction": info.get("north_direction", 0),
        "drawing_counter": info.get("drawing_counter", 0),
    }


def set_project_info(design, info_data):
    """프로젝트 정보 설정"""
    if "project_info" not in design:
        design["project_info"] = {}

    valid_keys = ["project_name", "designer", "company", "north_direction", "drawing_counter"]
    for k in valid_keys:
        if k in info_data:
            design["project_info"][k] = info_data[k]

    return {
        "success": True,
        "message": "프로젝트 정보 업데이트됨",
        "project_info": design["project_info"],
    }


# ============================================================
# 도면 자동 번호
# ============================================================

DRAWING_PREFIXES = {
    "floor_plan": "A",
    "section": "A",
    "elevation": "A",
    "structural": "S",
    "mep": "M",
    "site": "C",
}


def auto_number_drawing(design, drawing_type="floor_plan"):
    """도면 자동 번호 생성 (A-01, A-02, S-01 등)
    drawing_counter를 증가시키고 번호 반환"""
    info = design.get("project_info", {})
    counter = info.get("drawing_counter", 0) + 1

    prefix = DRAWING_PREFIXES.get(drawing_type, "A")
    number = f"{prefix}-{counter:02d}"

    if "project_info" not in design:
        design["project_info"] = {}
    design["project_info"]["drawing_counter"] = counter

    return number


# ============================================================
# 제목란 (Title Block)
# ============================================================

def draw_title_block(ax, fig, design, drawing_name="", drawing_number="",
                     scale="1:100", paper_size="A3"):
    """도면 하단에 제목란 그리기
    ax의 좌표계가 이미 m 단위라고 가정, 아래쪽에 제목란 영역을 추가"""
    info = get_project_info(design)
    date_str = datetime.now().strftime("%Y-%m-%d")

    # 제목란 영역 (axes 좌표 기준, 하단)
    x_lim = ax.get_xlim()
    y_lim = ax.get_ylim()
    tb_width = x_lim[1] - x_lim[0]
    tb_height = 1.2  # 제목란 높이 (m 단위로 환산)
    tb_y = y_lim[0] - tb_height - 0.3

    # 외곽 박스
    outer = patches.Rectangle(
        (x_lim[0], tb_y), tb_width, tb_height,
        linewidth=1.5, edgecolor="#333333", facecolor="#FAFAFA",
        zorder=20
    )
    ax.add_patch(outer)

    # 내부 구분선
    col_w = tb_width / 4
    for i in range(1, 4):
        ax.plot([x_lim[0] + col_w * i, x_lim[0] + col_w * i],
                [tb_y, tb_y + tb_height],
                color="#999999", linewidth=0.5, zorder=21)

    # 중간 수평선
    mid_y = tb_y + tb_height / 2
    ax.plot([x_lim[0], x_lim[1]], [mid_y, mid_y],
            color="#999999", linewidth=0.5, zorder=21)

    font_lg = 8
    font_sm = 6
    txt_color = "#333333"
    lbl_color = "#888888"

    # 1열: 프로젝트명 + 회사명
    cx = x_lim[0] + col_w * 0.5
    ax.text(cx, mid_y + tb_height * 0.15, info["project_name"],
            ha="center", va="center", fontsize=font_lg, fontweight="bold",
            color=txt_color, zorder=22)
    ax.text(cx, tb_y + tb_height * 0.2, info.get("company", ""),
            ha="center", va="center", fontsize=font_sm, color=lbl_color, zorder=22)

    # 2열: 도면명 + 설계자
    cx = x_lim[0] + col_w * 1.5
    ax.text(cx, mid_y + tb_height * 0.15,
            drawing_name if drawing_name else "도면",
            ha="center", va="center", fontsize=font_lg, fontweight="bold",
            color=txt_color, zorder=22)
    designer_text = f"설계: {info['designer']}" if info["designer"] else ""
    ax.text(cx, tb_y + tb_height * 0.2, designer_text,
            ha="center", va="center", fontsize=font_sm, color=lbl_color, zorder=22)

    # 3열: 도면번호 + 축척
    cx = x_lim[0] + col_w * 2.5
    ax.text(cx, mid_y + tb_height * 0.15,
            drawing_number if drawing_number else "",
            ha="center", va="center", fontsize=font_lg, fontweight="bold",
            color=txt_color, zorder=22)
    ax.text(cx, tb_y + tb_height * 0.2, f"Scale {scale}",
            ha="center", va="center", fontsize=font_sm, color=lbl_color, zorder=22)

    # 4열: 날짜
    cx = x_lim[0] + col_w * 3.5
    ax.text(cx, mid_y + tb_height * 0.15, date_str,
            ha="center", va="center", fontsize=font_lg, color=txt_color, zorder=22)
    ax.text(cx, tb_y + tb_height * 0.2, paper_size,
            ha="center", va="center", fontsize=font_sm, color=lbl_color, zorder=22)

    # y축 범위 조정
    ax.set_ylim(tb_y - 0.2, y_lim[1])


# ============================================================
# 면적표 삽입 (도면 내)
# ============================================================

def draw_area_table(ax, design, floor_id=None, x_pos=None, y_pos=None):
    """도면 우측에 면적표 삽입"""
    _geo = _load("geometry_utils")
    room_area = _geo.room_area

    floors = design.get("floors", [])
    if floor_id:
        floors = [f for f in floors if f["id"] == floor_id]

    if x_pos is None:
        x_pos = ax.get_xlim()[1] + 0.5
    if y_pos is None:
        y_pos = ax.get_ylim()[1]

    row_h = 0.35
    col_widths = [2.5, 1.2, 1.5]  # 실명, 타입, 면적
    total_w = sum(col_widths)
    font_size = 5.5
    header_color = "#444444"
    line_color = "#AAAAAA"

    # 헤더
    y = y_pos
    header_bg = patches.Rectangle(
        (x_pos, y - row_h), total_w, row_h,
        facecolor="#E8E8E8", edgecolor=header_color, linewidth=0.8, zorder=15
    )
    ax.add_patch(header_bg)

    headers = ["실명", "타입", "면적(m²)"]
    cx = x_pos
    for i, hdr in enumerate(headers):
        ax.text(cx + col_widths[i] / 2, y - row_h / 2, hdr,
                ha="center", va="center", fontsize=font_size,
                fontweight="bold", color=header_color, zorder=16)
        cx += col_widths[i]

    y -= row_h
    grand_total = 0.0

    for floor in floors:
        # 층 구분선
        floor_bg = patches.Rectangle(
            (x_pos, y - row_h), total_w, row_h,
            facecolor="#F0F0F0", edgecolor=line_color, linewidth=0.5, zorder=15
        )
        ax.add_patch(floor_bg)
        ax.text(x_pos + total_w / 2, y - row_h / 2, floor.get("name", floor["id"]),
                ha="center", va="center", fontsize=font_size,
                fontweight="bold", color="#666666", zorder=16)
        y -= row_h

        subtotal = 0.0
        for room in floor.get("rooms", []):
            area = room_area(room)
            subtotal += area

            row_bg = patches.Rectangle(
                (x_pos, y - row_h), total_w, row_h,
                facecolor="white", edgecolor=line_color, linewidth=0.3, zorder=15
            )
            ax.add_patch(row_bg)

            cx = x_pos
            vals = [room.get("name", ""), room.get("type", ""), f"{area:.1f}"]
            for i, val in enumerate(vals):
                ha = "left" if i == 0 else "center"
                px = cx + 0.15 if i == 0 else cx + col_widths[i] / 2
                ax.text(px, y - row_h / 2, val,
                        ha=ha, va="center", fontsize=font_size - 0.5,
                        color="#333333", zorder=16)
                cx += col_widths[i]
            y -= row_h

        # 소계
        sub_bg = patches.Rectangle(
            (x_pos, y - row_h), total_w, row_h,
            facecolor="#F8F8F0", edgecolor=line_color, linewidth=0.5, zorder=15
        )
        ax.add_patch(sub_bg)
        ax.text(x_pos + col_widths[0] / 2, y - row_h / 2, "소계",
                ha="center", va="center", fontsize=font_size,
                fontweight="bold", color="#666666", zorder=16)
        ax.text(x_pos + col_widths[0] + col_widths[1] + col_widths[2] / 2,
                y - row_h / 2, f"{subtotal:.1f}",
                ha="center", va="center", fontsize=font_size,
                fontweight="bold", color="#333333", zorder=16)
        y -= row_h
        grand_total += subtotal

    # 총 합계
    total_bg = patches.Rectangle(
        (x_pos, y - row_h), total_w, row_h,
        facecolor="#E0E0D8", edgecolor=header_color, linewidth=0.8, zorder=15
    )
    ax.add_patch(total_bg)
    ax.text(x_pos + col_widths[0] / 2, y - row_h / 2, "총 면적",
            ha="center", va="center", fontsize=font_size,
            fontweight="bold", color=header_color, zorder=16)
    ax.text(x_pos + col_widths[0] + col_widths[1] + col_widths[2] / 2,
            y - row_h / 2, f"{grand_total:.1f}",
            ha="center", va="center", fontsize=font_size,
            fontweight="bold", color=header_color, zorder=16)


# ============================================================
# 실명 표기 포맷
# ============================================================

def format_room_label(room, include_area=True, include_floor_material=False,
                      include_ceiling_height=False):
    """실명 표기 포맷팅
    Returns: 여러 줄 문자열 (이름 + 면적 + 바닥재 + 천장고)
    """
    _geo = _load("geometry_utils")

    lines = [room.get("name", "")]

    if include_area:
        area = _geo.room_area(room)
        lines.append(f"({area:.1f}m²)")

    if include_floor_material:
        mat = room.get("floor_material", "")
        if mat:
            lines.append(f"바닥: {mat}")

    if include_ceiling_height:
        ch = room.get("ceiling_height")
        if ch:
            lines.append(f"CH: {ch}m")

    return "\n".join(lines)
