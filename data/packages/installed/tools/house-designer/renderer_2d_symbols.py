"""
House Designer v4 - 2D 건축 심볼 렌더러
전문 건축 도면 수준의 가구/문/창/계단/난간 심볼
(나선형/Winder 계단 포함)
"""
import math
import matplotlib.patches as patches
from matplotlib.patches import Arc, FancyBboxPatch, Ellipse, Circle
import matplotlib.patheffects as pe
import matplotlib.transforms as transforms


# ============================================================
# 유틸리티
# ============================================================

def _rot_transform(ax, cx, cy, angle):
    """회전 변환 생성"""
    if angle == 0:
        return None
    return transforms.Affine2D().rotate_deg_around(cx, cy, angle) + ax.transData


def _add_patch(ax, patch, rot_t=None):
    if rot_t:
        patch.set_transform(rot_t)
    ax.add_patch(patch)


# ============================================================
# 가구 심볼 디스패처
# ============================================================

FIXTURE_DISPATCH = {}

def draw_fixture(ax, furn):
    """가구 타입별 전문 건축 심볼로 렌더링"""
    x, y = furn.get("x", 0), furn.get("y", 0)
    w, d = furn.get("width", 1), furn.get("depth", 1)
    rot = furn.get("rotation", 0)
    ftype = furn.get("type", "")
    name = furn.get("name", "")

    cx, cy = x + w / 2, y + d / 2
    rot_t = _rot_transform(ax, cx, cy, rot)

    fn = FIXTURE_DISPATCH.get(ftype)
    if fn:
        fn(ax, x, y, w, d, rot_t)
    else:
        _generic_box(ax, x, y, w, d, rot_t, name)

    # 라벨 (심볼 위에 표시)
    fontsize = max(4.5, min(6.5, min(w, d) * 2.5))
    ax.text(cx, cy, name, ha="center", va="center", fontsize=fontsize,
            color="#444444", fontweight="bold", zorder=8,
            path_effects=[pe.withStroke(linewidth=1.5, foreground="white")])


def _generic_box(ax, x, y, w, d, rot_t, name=""):
    """미지원 가구 — 기존 점선 박스"""
    rect = patches.Rectangle((x, y), w, d, linewidth=1.0,
        edgecolor="#888888", facecolor="#D0D0D0", alpha=0.3,
        linestyle="--", zorder=5)
    _add_patch(ax, rect, rot_t)


# ============================================================
# 위생 설비 심볼
# ============================================================

def _toilet(ax, x, y, w, d, rot_t):
    """변기: 타원형 볼 + 직사각 탱크"""
    tank_d = d * 0.3
    bowl_d = d * 0.7
    # 탱크 (뒤쪽)
    tank = patches.Rectangle((x, y + bowl_d), w, tank_d,
        linewidth=1.0, edgecolor="#666666", facecolor="#E8E8F0", zorder=5)
    _add_patch(ax, tank, rot_t)
    # 볼 (앞쪽, 타원)
    bowl = Ellipse((x + w / 2, y + bowl_d / 2), w * 0.85, bowl_d * 0.9,
        linewidth=1.0, edgecolor="#666666", facecolor="#F0F0F8", zorder=5)
    _add_patch(ax, bowl, rot_t)
    # 시트 링
    seat = Ellipse((x + w / 2, y + bowl_d / 2), w * 0.65, bowl_d * 0.65,
        linewidth=0.5, edgecolor="#999999", facecolor="none", zorder=6)
    _add_patch(ax, seat, rot_t)

FIXTURE_DISPATCH["toilet"] = _toilet


def _sink(ax, x, y, w, d, rot_t):
    """세면대: 직사각 카운터 + 타원 보울"""
    # 카운터
    counter = patches.Rectangle((x, y), w, d,
        linewidth=1.0, edgecolor="#666666", facecolor="#E0E0E8", zorder=5)
    _add_patch(ax, counter, rot_t)
    # 보울
    bowl = Ellipse((x + w / 2, y + d * 0.45), w * 0.6, d * 0.5,
        linewidth=0.8, edgecolor="#4488CC", facecolor="#D8E8F0", zorder=6)
    _add_patch(ax, bowl, rot_t)
    # 수전
    ax.plot([x + w / 2, x + w / 2], [y + d * 0.75, y + d * 0.9],
            color="#888888", linewidth=1.5, zorder=7)

FIXTURE_DISPATCH["sink"] = _sink


def _bathtub(ax, x, y, w, d, rot_t):
    """욕조: 둥근 모서리 직사각형"""
    # 외부
    outer = FancyBboxPatch((x, y), w, d,
        boxstyle="round,pad=0.05", linewidth=1.2,
        edgecolor="#4488AA", facecolor="#D8EAF0", zorder=5)
    _add_patch(ax, outer, rot_t)
    # 내부 (약간 안쪽)
    margin = min(w, d) * 0.1
    inner = FancyBboxPatch((x + margin, y + margin), w - 2 * margin, d - 2 * margin,
        boxstyle="round,pad=0.03", linewidth=0.8,
        edgecolor="#6699AA", facecolor="#E8F4F8", zorder=6)
    _add_patch(ax, inner, rot_t)
    # 배수구
    drain = Circle((x + w / 2, y + d * 0.15), min(w, d) * 0.04,
        linewidth=0.5, edgecolor="#666666", facecolor="#AAAAAA", zorder=7)
    _add_patch(ax, drain, rot_t)

FIXTURE_DISPATCH["bathtub"] = _bathtub


def _shower(ax, x, y, w, d, rot_t):
    """샤워부스: 사각형 + 대각선 물줄기 패턴"""
    # 외부
    rect = patches.Rectangle((x, y), w, d,
        linewidth=1.0, edgecolor="#4488AA", facecolor="#E0F0F4", alpha=0.5, zorder=5)
    _add_patch(ax, rect, rot_t)
    # 대각 물줄기 패턴
    num_lines = max(3, int(min(w, d) / 0.3))
    for i in range(num_lines):
        frac = (i + 1) / (num_lines + 1)
        lx = x + w * frac
        ax.plot([lx, lx - w * 0.15], [y + d * 0.2, y + d * 0.8],
                color="#88BBDD", linewidth=0.4, alpha=0.5, zorder=6)
    # 배수구
    drain = Circle((x + w / 2, y + d / 2), min(w, d) * 0.05,
        linewidth=0.5, edgecolor="#666666", facecolor="#CCCCCC", zorder=7)
    _add_patch(ax, drain, rot_t)

FIXTURE_DISPATCH["shower"] = _shower


# ============================================================
# 주방 설비 심볼
# ============================================================

def _kitchen_sink(ax, x, y, w, d, rot_t):
    """주방 싱크: 이중 보울"""
    # 카운터
    counter = patches.Rectangle((x, y), w, d,
        linewidth=1.0, edgecolor="#666666", facecolor="#D8D8D8", zorder=5)
    _add_patch(ax, counter, rot_t)
    # 좌측 보울
    b1 = Ellipse((x + w * 0.3, y + d / 2), w * 0.35, d * 0.55,
        linewidth=0.8, edgecolor="#4488CC", facecolor="#E0ECF4", zorder=6)
    _add_patch(ax, b1, rot_t)
    # 우측 보울
    b2 = Ellipse((x + w * 0.7, y + d / 2), w * 0.35, d * 0.55,
        linewidth=0.8, edgecolor="#4488CC", facecolor="#E0ECF4", zorder=6)
    _add_patch(ax, b2, rot_t)

FIXTURE_DISPATCH["kitchen_sink"] = _kitchen_sink


def _stove(ax, x, y, w, d, rot_t):
    """가스레인지: 2x2 버너 원"""
    rect = patches.Rectangle((x, y), w, d,
        linewidth=1.0, edgecolor="#666666", facecolor="#E8E0D8", zorder=5)
    _add_patch(ax, rect, rot_t)
    # 4개 버너
    r = min(w, d) * 0.15
    positions = [
        (x + w * 0.3, y + d * 0.35),
        (x + w * 0.7, y + d * 0.35),
        (x + w * 0.3, y + d * 0.65),
        (x + w * 0.7, y + d * 0.65),
    ]
    for bx, by in positions:
        burner = Circle((bx, by), r,
            linewidth=1.0, edgecolor="#CC5555", facecolor="none", zorder=6)
        _add_patch(ax, burner, rot_t)
        # 내부 원
        inner = Circle((bx, by), r * 0.5,
            linewidth=0.5, edgecolor="#CC5555", facecolor="none", zorder=6)
        _add_patch(ax, inner, rot_t)

FIXTURE_DISPATCH["stove"] = _stove


def _refrigerator(ax, x, y, w, d, rot_t):
    """냉장고: 직사각 + 냉동실 구분선"""
    rect = patches.Rectangle((x, y), w, d,
        linewidth=1.2, edgecolor="#666666", facecolor="#D0D0D0", zorder=5)
    _add_patch(ax, rect, rot_t)
    # 냉동실 구분 (상단 30%)
    div_y = y + d * 0.7
    ax.plot([x + 0.02, x + w - 0.02], [div_y, div_y],
            color="#888888", linewidth=1.0, zorder=6)
    # 손잡이
    handle_x = x + w * 0.85
    ax.plot([handle_x, handle_x], [y + d * 0.15, y + d * 0.55],
            color="#999999", linewidth=2.0, solid_capstyle="round", zorder=6)
    ax.plot([handle_x, handle_x], [y + d * 0.75, y + d * 0.9],
            color="#999999", linewidth=2.0, solid_capstyle="round", zorder=6)

FIXTURE_DISPATCH["refrigerator"] = _refrigerator


def _washing_machine(ax, x, y, w, d, rot_t):
    """세탁기: 직사각 + 원형 드럼"""
    rect = patches.Rectangle((x, y), w, d,
        linewidth=1.0, edgecolor="#666666", facecolor="#E0E0E0", zorder=5)
    _add_patch(ax, rect, rot_t)
    drum = Circle((x + w / 2, y + d / 2), min(w, d) * 0.3,
        linewidth=1.0, edgecolor="#888888", facecolor="#F0F0F0", zorder=6)
    _add_patch(ax, drum, rot_t)

FIXTURE_DISPATCH["washing_machine"] = _washing_machine


# ============================================================
# 가구 심볼
# ============================================================

def _bed(ax, x, y, w, d, rot_t):
    """침대: 매트리스 + 베개"""
    # 매트리스
    mat = patches.Rectangle((x, y), w, d,
        linewidth=1.0, edgecolor="#6B8E23", facecolor="#D4E6B0", alpha=0.5, zorder=5)
    _add_patch(ax, mat, rot_t)
    # 베개 영역 (상단)
    pillow_h = min(d * 0.18, 0.4)
    pillow_y = y + d - pillow_h
    pillow_margin = w * 0.08
    # 베개 1
    p1 = FancyBboxPatch((x + pillow_margin, pillow_y),
        w / 2 - pillow_margin * 1.5, pillow_h * 0.8,
        boxstyle="round,pad=0.02", linewidth=0.6,
        edgecolor="#8B9E5A", facecolor="#E8F0D8", zorder=6)
    _add_patch(ax, p1, rot_t)
    # 베개 2
    p2 = FancyBboxPatch((x + w / 2 + pillow_margin * 0.5, pillow_y),
        w / 2 - pillow_margin * 1.5, pillow_h * 0.8,
        boxstyle="round,pad=0.02", linewidth=0.6,
        edgecolor="#8B9E5A", facecolor="#E8F0D8", zorder=6)
    _add_patch(ax, p2, rot_t)
    # 이불 라인
    ax.plot([x + w * 0.1, x + w * 0.9], [y + d * 0.4, y + d * 0.4],
            color="#8B9E5A", linewidth=0.5, zorder=6)

for bt in ["bed_single", "bed_double", "bed_queen", "bed_king"]:
    FIXTURE_DISPATCH[bt] = _bed


def _sofa(ax, x, y, w, d, rot_t):
    """소파: 좌석 + 등받이 + 팔걸이"""
    back_d = d * 0.2
    arm_w = w * 0.08
    seat_w = w - arm_w * 2
    seat_d = d - back_d
    # 등받이
    back = patches.Rectangle((x, y + seat_d), w, back_d,
        linewidth=1.0, edgecolor="#8B6914", facecolor="#C8A050", alpha=0.5, zorder=5)
    _add_patch(ax, back, rot_t)
    # 좌석
    seat = patches.Rectangle((x + arm_w, y), seat_w, seat_d,
        linewidth=0.8, edgecolor="#8B6914", facecolor="#D4B870", alpha=0.4, zorder=5)
    _add_patch(ax, seat, rot_t)
    # 좌측 팔걸이
    la = patches.Rectangle((x, y), arm_w, seat_d,
        linewidth=0.8, edgecolor="#8B6914", facecolor="#B89840", alpha=0.5, zorder=6)
    _add_patch(ax, la, rot_t)
    # 우측 팔걸이
    ra = patches.Rectangle((x + w - arm_w, y), arm_w, seat_d,
        linewidth=0.8, edgecolor="#8B6914", facecolor="#B89840", alpha=0.5, zorder=6)
    _add_patch(ax, ra, rot_t)
    # 쿠션 구분선
    num_cushions = max(2, round(seat_w / 0.7))
    cw = seat_w / num_cushions
    for i in range(1, num_cushions):
        cx = x + arm_w + cw * i
        ax.plot([cx, cx], [y + 0.05, y + seat_d - 0.05],
                color="#A08030", linewidth=0.4, zorder=6)

FIXTURE_DISPATCH["sofa"] = _sofa


def _table(ax, x, y, w, d, rot_t):
    """테이블/책상: 상판 + 다리 표시"""
    # 상판
    top = patches.Rectangle((x, y), w, d,
        linewidth=1.0, edgecolor="#8B4513", facecolor="#D2B48C", alpha=0.4, zorder=5)
    _add_patch(ax, top, rot_t)
    # 4 다리 (모서리 작은 사각형)
    leg_s = min(w, d) * 0.06
    for lx, ly in [(x + leg_s, y + leg_s), (x + w - leg_s * 2, y + leg_s),
                   (x + leg_s, y + d - leg_s * 2), (x + w - leg_s * 2, y + d - leg_s * 2)]:
        leg = patches.Rectangle((lx, ly), leg_s, leg_s,
            linewidth=0.5, edgecolor="#6B3410", facecolor="#8B5A2B", zorder=6)
        _add_patch(ax, leg, rot_t)

for tt in ["dining_table", "desk", "coffee_table"]:
    FIXTURE_DISPATCH[tt] = _table


def _chair(ax, x, y, w, d, rot_t):
    """의자: 좌석 + 등받이"""
    back_d = d * 0.15
    seat_d = d - back_d
    seat = patches.Rectangle((x, y), w, seat_d,
        linewidth=0.8, edgecolor="#A08060", facecolor="#DEB887", alpha=0.4, zorder=5)
    _add_patch(ax, seat, rot_t)
    back = patches.Rectangle((x, y + seat_d), w, back_d,
        linewidth=0.8, edgecolor="#A08060", facecolor="#C8A060", alpha=0.5, zorder=5)
    _add_patch(ax, back, rot_t)

FIXTURE_DISPATCH["chair"] = _chair


def _wardrobe(ax, x, y, w, d, rot_t):
    """옷장: 직사각 + 문 구분선 + 손잡이"""
    rect = patches.Rectangle((x, y), w, d,
        linewidth=1.2, edgecolor="#4A4A4A", facecolor="#C8C0B8", alpha=0.4, zorder=5)
    _add_patch(ax, rect, rot_t)
    # 문 구분선 (중앙)
    ax.plot([x + w / 2, x + w / 2], [y + 0.02, y + d - 0.02],
            color="#888888", linewidth=0.6, zorder=6)
    # 손잡이 2개
    handle_r = min(w, d) * 0.03
    h1 = Circle((x + w / 2 - handle_r * 3, y + d / 2), handle_r,
        linewidth=0.5, edgecolor="#666666", facecolor="#AAA", zorder=7)
    h2 = Circle((x + w / 2 + handle_r * 3, y + d / 2), handle_r,
        linewidth=0.5, edgecolor="#666666", facecolor="#AAA", zorder=7)
    _add_patch(ax, h1, rot_t)
    _add_patch(ax, h2, rot_t)

FIXTURE_DISPATCH["wardrobe"] = _wardrobe


def _bookshelf(ax, x, y, w, d, rot_t):
    """책장: 직사각 + 선반 수평선"""
    rect = patches.Rectangle((x, y), w, d,
        linewidth=1.0, edgecolor="#A0511A", facecolor="#E8D0B0", alpha=0.4, zorder=5)
    _add_patch(ax, rect, rot_t)
    num_shelves = max(3, int(d / 0.3))
    for i in range(1, num_shelves):
        sy = y + d * i / num_shelves
        ax.plot([x + 0.02, x + w - 0.02], [sy, sy],
                color="#C08040", linewidth=0.4, zorder=6)

FIXTURE_DISPATCH["bookshelf"] = _bookshelf


def _tv_stand(ax, x, y, w, d, rot_t):
    """TV 스탠드: 가구 + TV 패널"""
    stand = patches.Rectangle((x, y), w, d,
        linewidth=0.8, edgecolor="#333333", facecolor="#4A4A4A", alpha=0.3, zorder=5)
    _add_patch(ax, stand, rot_t)
    # TV (얇은 직사각)
    tv_w = w * 0.85
    tv = patches.Rectangle((x + (w - tv_w) / 2, y + d * 0.7), tv_w, d * 0.15,
        linewidth=1.0, edgecolor="#222222", facecolor="#333333", alpha=0.6, zorder=6)
    _add_patch(ax, tv, rot_t)

FIXTURE_DISPATCH["tv_stand"] = _tv_stand


# ============================================================
# 문 심볼
# ============================================================

def draw_door(ax, door, wall_map):
    """문 타입별 전문 심볼 렌더링"""
    wall_id = door.get("wall_id")
    if wall_id not in wall_map:
        return
    wall = wall_map[wall_id]
    sx, sy = wall["start"]
    ex, ey = wall["end"]
    wall_len = math.hypot(ex - sx, ey - sy)
    if wall_len < 0.01:
        return

    dx = (ex - sx) / wall_len
    dy = (ey - sy) / wall_len
    pos = door.get("position", wall_len / 2)
    width = door.get("width", 0.9)
    door_type = door.get("type", "single")

    # 힌지 위치
    hinge_x = sx + dx * (pos - width / 2)
    hinge_y = sy + dy * (pos - width / 2)
    tip_x = sx + dx * (pos + width / 2)
    tip_y = sy + dy * (pos + width / 2)

    angle = math.degrees(math.atan2(dy, dx))
    nx, ny = -dy, dx  # 벽 법선

    if door_type == "sliding":
        _draw_sliding_door(ax, hinge_x, hinge_y, tip_x, tip_y, dx, dy, nx, ny, width)
    elif door_type == "double":
        _draw_double_door(ax, hinge_x, hinge_y, tip_x, tip_y, dx, dy, nx, ny, width, angle)
    elif door_type == "pocket":
        _draw_pocket_door(ax, hinge_x, hinge_y, tip_x, tip_y, dx, dy, nx, ny, width)
    elif door_type == "bifold":
        _draw_bifold_door(ax, hinge_x, hinge_y, tip_x, tip_y, dx, dy, nx, ny, width)
    else:
        _draw_single_door(ax, hinge_x, hinge_y, width, angle, nx, ny)


def _draw_single_door(ax, hx, hy, width, angle, nx, ny):
    """여닫이문: 문짝 선 + 실선 호"""
    # 문짝 패널 라인
    panel_ex = hx + nx * width
    panel_ey = hy + ny * width
    ax.plot([hx, panel_ex], [hy, panel_ey],
            color="#6B4226", linewidth=1.5, solid_capstyle="round", zorder=7)
    # 스윙 호 (실선)
    arc = Arc((hx, hy), width * 2, width * 2,
              angle=angle, theta1=0, theta2=90,
              color="#6B4226", linewidth=0.8, zorder=7)
    ax.add_patch(arc)


def _draw_double_door(ax, hx, hy, tx, ty, dx, dy, nx, ny, width, angle):
    """양여닫이: 양쪽에서 열리는 문"""
    mid_x = (hx + tx) / 2
    mid_y = (hy + ty) / 2
    hw = width / 2
    # 좌측 문짝
    p1x = mid_x + nx * hw
    p1y = mid_y + ny * hw
    ax.plot([hx, hx + nx * hw], [hy, hy + ny * hw],
            color="#6B4226", linewidth=1.5, zorder=7)
    arc1 = Arc((hx, hy), hw * 2, hw * 2,
               angle=angle, theta1=0, theta2=90,
               color="#6B4226", linewidth=0.8, zorder=7)
    ax.add_patch(arc1)
    # 우측 문짝
    ax.plot([tx, tx + nx * hw], [ty, ty + ny * hw],
            color="#6B4226", linewidth=1.5, zorder=7)
    arc2 = Arc((tx, ty), hw * 2, hw * 2,
               angle=angle + 180, theta1=0, theta2=90,
               color="#6B4226", linewidth=0.8, zorder=7)
    ax.add_patch(arc2)


def _draw_sliding_door(ax, hx, hy, tx, ty, dx, dy, nx, ny, width):
    """미닫이: 두 줄 평행선 + 화살표"""
    off = 0.06
    # 상단 레일
    ax.plot([hx + nx * off, tx + nx * off], [hy + ny * off, ty + ny * off],
            color="#4488AA", linewidth=1.8, zorder=7)
    # 하단 레일
    ax.plot([hx - nx * off, tx - nx * off], [hy - ny * off, ty - ny * off],
            color="#4488AA", linewidth=1.8, zorder=7)
    # 중앙 화살표
    mx = (hx + tx) / 2
    my = (hy + ty) / 2
    arr_len = width * 0.2
    ax.annotate("", xy=(mx + dx * arr_len, my + dy * arr_len),
                xytext=(mx - dx * arr_len, my - dy * arr_len),
                arrowprops=dict(arrowstyle="->", color="#4488AA", lw=1.0),
                zorder=7)


def _draw_pocket_door(ax, hx, hy, tx, ty, dx, dy, nx, ny, width):
    """포켓도어: 벽 안으로 들어가는 문"""
    # 문짝 (벽 안으로 밀어넣은 형태)
    pocket_x = hx - dx * width
    pocket_y = hy - dy * width
    ax.plot([hx, pocket_x], [hy, pocket_y],
            color="#6B4226", linewidth=1.5, linestyle="--", zorder=7)
    # 벽 속 포켓 표시
    off = 0.1
    pocket_rect = patches.Rectangle(
        (min(hx, pocket_x) - abs(nx) * off, min(hy, pocket_y) - abs(ny) * off),
        abs(pocket_x - hx) + abs(nx) * off * 2 if abs(dx) > 0.5 else off * 2,
        abs(pocket_y - hy) + abs(ny) * off * 2 if abs(dy) > 0.5 else off * 2,
        linewidth=0.5, edgecolor="#999999", facecolor="none",
        linestyle=":", zorder=6)
    ax.add_patch(pocket_rect)


def _draw_bifold_door(ax, hx, hy, tx, ty, dx, dy, nx, ny, width):
    """접이식: 지그재그 패턴"""
    num_folds = 4
    fold_w = width / num_folds
    for i in range(num_folds):
        frac = i / num_folds
        frac_next = (i + 1) / num_folds
        x1 = hx + dx * width * frac
        y1 = hy + dy * width * frac
        x2 = hx + dx * width * frac_next
        y2 = hy + dy * width * frac_next
        # 교대로 안/밖 꺾임
        offset = 0.15 if i % 2 == 0 else -0.15
        mid_x = (x1 + x2) / 2 + nx * offset
        mid_y = (y1 + y2) / 2 + ny * offset
        ax.plot([x1, mid_x, x2], [y1, mid_y, y2],
                color="#6B4226", linewidth=1.2, zorder=7)


# ============================================================
# 창문 심볼
# ============================================================

def draw_window(ax, window, wall_map):
    """전문 건축 창문 심볼"""
    wall_id = window.get("wall_id")
    if wall_id not in wall_map:
        return
    wall = wall_map[wall_id]
    sx, sy = wall["start"]
    ex, ey = wall["end"]
    wall_len = math.hypot(ex - sx, ey - sy)
    if wall_len < 0.01:
        return

    dx = (ex - sx) / wall_len
    dy = (ey - sy) / wall_len
    pos = window.get("position", wall_len / 2)
    width = window.get("width", 1.5)

    cx = sx + dx * pos
    cy = sy + dy * pos
    hw = width / 2
    x1 = cx - dx * hw
    y1 = cy - dy * hw
    x2 = cx + dx * hw
    y2 = cy + dy * hw
    nx, ny = -dy, dx

    # 창틀 두께
    frame_t = 0.1

    # 외곽 프레임 (두꺼운 직사각형)
    frame_pts = [
        (x1 + nx * frame_t, y1 + ny * frame_t),
        (x2 + nx * frame_t, y2 + ny * frame_t),
        (x2 - nx * frame_t, y2 - ny * frame_t),
        (x1 - nx * frame_t, y1 - ny * frame_t),
    ]
    frame = patches.Polygon(frame_pts, closed=True,
        linewidth=1.2, edgecolor="#4488CC", facecolor="#D8EEF8",
        alpha=0.5, zorder=7)
    ax.add_patch(frame)

    # 유리 중심선
    ax.plot([x1, x2], [y1, y2],
            color="#4488CC", linewidth=0.8, zorder=8)

    # 중앙 머리언(mullion) — 분할선
    if width > 1.0:
        ax.plot([cx + nx * frame_t, cx - nx * frame_t],
                [cy + ny * frame_t, cy - ny * frame_t],
                color="#4488CC", linewidth=0.6, zorder=8)


# ============================================================
# 계단 심볼
# ============================================================

def draw_stairs_2d(ax, stair):
    """계단 2D 전문 심볼: 트레드 라인 + 번호 + 방향 화살표"""
    stype = stair.get("type", "straight")
    sx, sy = stair.get("start", [0, 0])
    direction = stair.get("direction", 0)
    width = stair.get("width", 1.0)
    num_treads = stair.get("num_treads", 15)
    tread_depth = stair.get("tread_depth", 0.28)
    landing_depth = stair.get("landing_depth", 1.0)
    turn_dir = stair.get("turn_direction", "right")

    if stype == "straight":
        _draw_straight_stairs(ax, sx, sy, direction, width, num_treads, tread_depth)
    elif stype == "l_shape":
        _draw_l_stairs(ax, sx, sy, direction, width, num_treads, tread_depth,
                       landing_depth, turn_dir)
    elif stype == "u_turn":
        _draw_u_stairs(ax, sx, sy, direction, width, num_treads, tread_depth,
                       landing_depth, turn_dir)
    elif stype == "spiral":
        _draw_spiral_stairs(ax, stair)
    elif stype == "winder":
        _draw_winder_stairs(ax, sx, sy, direction, width, num_treads, tread_depth, stair)


def _dir_vectors(direction):
    """방향 각도에서 전진/좌측 벡터"""
    rad = math.radians(direction)
    fwd = (math.sin(rad), math.cos(rad))     # 전진 방향 (0도=+Y)
    right = (math.cos(rad), -math.sin(rad))   # 우측 방향
    return fwd, right


def _draw_straight_stairs(ax, sx, sy, direction, width, num_treads, tread_depth):
    """직선 계단"""
    fwd, right = _dir_vectors(direction)
    total_run = num_treads * tread_depth

    # 외곽 사각형 좌표
    corners = [
        (sx, sy),
        (sx + right[0] * width, sy + right[1] * width),
        (sx + right[0] * width + fwd[0] * total_run, sy + right[1] * width + fwd[1] * total_run),
        (sx + fwd[0] * total_run, sy + fwd[1] * total_run),
    ]
    outline = patches.Polygon(corners, closed=True,
        linewidth=1.2, edgecolor="#555555", facecolor="#F0F0F0", alpha=0.3, zorder=5)
    ax.add_patch(outline)

    # 트레드 라인
    for i in range(num_treads + 1):
        t = i * tread_depth
        lx1 = sx + fwd[0] * t
        ly1 = sy + fwd[1] * t
        lx2 = sx + right[0] * width + fwd[0] * t
        ly2 = sy + right[1] * width + fwd[1] * t
        lw = 0.8 if i == 0 or i == num_treads else 0.4
        ax.plot([lx1, lx2], [ly1, ly2], color="#666666", linewidth=lw, zorder=6)

    # 트레드 번호 (1, 5, 10 등 주요 번호만)
    for i in range(num_treads):
        if i == 0 or i == num_treads - 1 or i % 5 == 0:
            t = (i + 0.5) * tread_depth
            tx = sx + right[0] * width / 2 + fwd[0] * t
            ty = sy + right[1] * width / 2 + fwd[1] * t
            ax.text(tx, ty, str(i + 1), ha="center", va="center",
                    fontsize=4, color="#888888", zorder=7)

    # 방향 화살표 + "UP" 라벨
    arr_start_t = total_run * 0.3
    arr_end_t = total_run * 0.8
    arr_sx = sx + right[0] * width / 2 + fwd[0] * arr_start_t
    arr_sy = sy + right[1] * width / 2 + fwd[1] * arr_start_t
    arr_ex = sx + right[0] * width / 2 + fwd[0] * arr_end_t
    arr_ey = sy + right[1] * width / 2 + fwd[1] * arr_end_t
    ax.annotate("", xy=(arr_ex, arr_ey), xytext=(arr_sx, arr_sy),
                arrowprops=dict(arrowstyle="->", color="#CC0000", lw=1.5), zorder=8)
    # "UP" 라벨
    label_t = total_run * 0.55
    label_x = sx + right[0] * width * 0.15 + fwd[0] * label_t
    label_y = sy + right[1] * width * 0.15 + fwd[1] * label_t
    rot_angle = direction
    ax.text(label_x, label_y, "UP", ha="center", va="center",
            fontsize=5, color="#CC0000", fontweight="bold", rotation=rot_angle, zorder=8,
            path_effects=[pe.withStroke(linewidth=1, foreground="white")])


def _draw_l_stairs(ax, sx, sy, direction, width, num_treads, tread_depth,
                   landing_depth, turn_dir):
    """L자 계단: 첫 번째 런 + 랜딩 + 두 번째 런"""
    fwd, right = _dir_vectors(direction)
    treads_per_run = num_treads // 2
    remainder = num_treads - treads_per_run * 2

    # 첫 번째 런
    _draw_straight_stairs(ax, sx, sy, direction, width, treads_per_run, tread_depth)

    # 랜딩 위치
    run1_end = treads_per_run * tread_depth
    lx = sx + fwd[0] * run1_end
    ly = sy + fwd[1] * run1_end

    # 랜딩 사각형
    landing_corners = [
        (lx, ly),
        (lx + right[0] * width, ly + right[1] * width),
        (lx + right[0] * width + fwd[0] * landing_depth, ly + right[1] * width + fwd[1] * landing_depth),
        (lx + fwd[0] * landing_depth, ly + fwd[1] * landing_depth),
    ]
    landing_patch = patches.Polygon(landing_corners, closed=True,
        linewidth=1.0, edgecolor="#555555", facecolor="#E8E8E8", alpha=0.3, zorder=5)
    ax.add_patch(landing_patch)
    # 대각선 (랜딩 표시)
    ax.plot([landing_corners[0][0], landing_corners[2][0]],
            [landing_corners[0][1], landing_corners[2][1]],
            color="#BBBBBB", linewidth=0.5, zorder=5)

    # 두 번째 런 (90도 회전)
    turn_angle = 90 if turn_dir == "right" else -90
    dir2 = direction + turn_angle
    run2_sx = lx + fwd[0] * landing_depth
    run2_sy = ly + fwd[1] * landing_depth
    if turn_dir == "right":
        run2_sx += right[0] * width
        run2_sy += right[1] * width
    _draw_straight_stairs(ax, run2_sx, run2_sy, dir2,
                          width, treads_per_run + remainder, tread_depth)


def _draw_u_stairs(ax, sx, sy, direction, width, num_treads, tread_depth,
                   landing_depth, turn_dir):
    """U턴 계단: 두 개의 병렬 런 + 랜딩"""
    fwd, right = _dir_vectors(direction)
    treads_per_run = num_treads // 2
    remainder = num_treads - treads_per_run * 2

    # 첫 번째 런
    _draw_straight_stairs(ax, sx, sy, direction, width, treads_per_run, tread_depth)

    # 랜딩
    run1_end = treads_per_run * tread_depth
    lx = sx + fwd[0] * run1_end
    ly = sy + fwd[1] * run1_end
    total_w = width * 2 + 0.1  # 두 런 사이 간격
    landing_corners = [
        (lx, ly),
        (lx + right[0] * total_w, ly + right[1] * total_w),
        (lx + right[0] * total_w + fwd[0] * landing_depth,
         ly + right[1] * total_w + fwd[1] * landing_depth),
        (lx + fwd[0] * landing_depth, ly + fwd[1] * landing_depth),
    ]
    landing_patch = patches.Polygon(landing_corners, closed=True,
        linewidth=1.0, edgecolor="#555555", facecolor="#E8E8E8", alpha=0.3, zorder=5)
    ax.add_patch(landing_patch)

    # 두 번째 런 (180도 반전, 옆에 위치)
    dir2 = direction + 180
    offset = width + 0.1
    run2_sx = lx + fwd[0] * landing_depth + right[0] * offset
    run2_sy = ly + fwd[1] * landing_depth + right[1] * offset
    _draw_straight_stairs(ax, run2_sx, run2_sy, dir2,
                          width, treads_per_run + remainder, tread_depth)


# ============================================================
# 나선형(Spiral) 계단 심볼
# ============================================================

def _draw_spiral_stairs(ax, stair):
    """나선형 계단: 원형 외곽 + 부채꼴 디딤판 + 중심 기둥 + 방향 화살표"""
    center = stair.get("center", stair.get("start", [0, 0]))
    cx, cy = center[0], center[1]
    radius = stair.get("radius", 1.5)
    inner_r = stair.get("inner_radius", 0.15)
    num_treads = stair.get("num_treads", 12)
    total_angle = stair.get("total_angle", 360)
    rotation = stair.get("rotation", "cw")
    start_angle = stair.get("direction", 0)  # 시작 각도

    # 외부 원 (외곽)
    outer_circle = Circle((cx, cy), radius,
        linewidth=1.2, edgecolor="#555555", facecolor="#F0F0F0", alpha=0.3, zorder=5)
    ax.add_patch(outer_circle)

    # 중심 기둥
    if inner_r > 0.01:
        center_post = Circle((cx, cy), inner_r,
            linewidth=1.0, edgecolor="#444444", facecolor="#888888", alpha=0.5, zorder=7)
        ax.add_patch(center_post)

    # 부채꼴 디딤판 구분선
    angle_per_tread = total_angle / num_treads
    direction_sign = -1 if rotation == "cw" else 1

    for i in range(num_treads + 1):
        angle = start_angle + direction_sign * angle_per_tread * i
        rad = math.radians(angle)
        x1 = cx + inner_r * math.cos(rad)
        y1 = cy + inner_r * math.sin(rad)
        x2 = cx + radius * math.cos(rad)
        y2 = cy + radius * math.sin(rad)
        lw = 0.8 if i == 0 or i == num_treads else 0.4
        ax.plot([x1, x2], [y1, y2], color="#666666", linewidth=lw, zorder=6)

    # 트레드 번호 (주요 번호만)
    mid_r = (radius + inner_r) / 2
    for i in range(num_treads):
        if i == 0 or i == num_treads - 1 or i % 4 == 0:
            angle = start_angle + direction_sign * angle_per_tread * (i + 0.5)
            rad = math.radians(angle)
            tx = cx + mid_r * math.cos(rad)
            ty = cy + mid_r * math.sin(rad)
            ax.text(tx, ty, str(i + 1), ha="center", va="center",
                    fontsize=3.5, color="#888888", zorder=7)

    # 방향 화살표 (외측 호를 따라)
    arr_frac_start = 0.4
    arr_frac_end = 0.7
    arr_r = radius * 0.75
    a_start = start_angle + direction_sign * total_angle * arr_frac_start
    a_end = start_angle + direction_sign * total_angle * arr_frac_end
    r_start = math.radians(a_start)
    r_end = math.radians(a_end)
    ax.annotate("",
        xy=(cx + arr_r * math.cos(r_end), cy + arr_r * math.sin(r_end)),
        xytext=(cx + arr_r * math.cos(r_start), cy + arr_r * math.sin(r_start)),
        arrowprops=dict(arrowstyle="->", color="#CC0000", lw=1.5,
                        connectionstyle=f"arc3,rad={0.3 * direction_sign}"),
        zorder=8)

    # "UP" 라벨
    label_angle = start_angle + direction_sign * total_angle * 0.55
    label_rad = math.radians(label_angle)
    label_r = radius * 0.55
    ax.text(cx + label_r * math.cos(label_rad), cy + label_r * math.sin(label_rad),
            "UP", ha="center", va="center", fontsize=5, color="#CC0000",
            fontweight="bold", zorder=8,
            path_effects=[pe.withStroke(linewidth=1, foreground="white")])


# ============================================================
# Winder(부채꼴) 계단 심볼
# ============================================================

def _draw_winder_stairs(ax, sx, sy, direction, width, num_treads, tread_depth, stair):
    """Winder 계단: 직선부 + 부채꼴 회전부 + 직선부"""
    fwd, right = _dir_vectors(direction)
    winder_count = stair.get("winder_count", 3)
    turn_angle = stair.get("turn_angle", 90)
    turn_dir = stair.get("turn_direction", "right")
    treads_before = stair.get("treads_before", (num_treads - winder_count) // 2)
    treads_after = stair.get("treads_after", num_treads - winder_count - treads_before)

    # --- 1) 첫 번째 직선부 ---
    if treads_before > 0:
        _draw_straight_stairs(ax, sx, sy, direction, width, treads_before, tread_depth)

    # --- 2) Winder(부채꼴) 회전부 ---
    run1_end = treads_before * tread_depth
    wx = sx + fwd[0] * run1_end
    wy = sy + fwd[1] * run1_end

    # 회전 중심점 (안쪽 모서리)
    if turn_dir == "right":
        pivot_x = wx + right[0] * width
        pivot_y = wy + right[1] * width
    else:
        pivot_x = wx
        pivot_y = wy

    # 기준 각도 계산 (진행 방향에서 벽 쪽으로)
    base_angle = math.degrees(math.atan2(fwd[1], fwd[0]))
    if turn_dir == "right":
        base_angle = math.degrees(math.atan2(-right[1], -right[0]))
    else:
        base_angle = math.degrees(math.atan2(right[1], right[0]))

    sign = -1 if turn_dir == "right" else 1
    angle_step = turn_angle / winder_count

    # 부채꼴 외곽 호
    arc_patch = Arc((pivot_x, pivot_y), width * 2, width * 2,
                    angle=0, theta1=base_angle, theta2=base_angle + sign * turn_angle,
                    color="#555555", linewidth=1.2, zorder=5)
    ax.add_patch(arc_patch)

    # 부채꼴 디딤판 구분선
    for i in range(winder_count + 1):
        angle = math.radians(base_angle + sign * angle_step * i)
        x1 = pivot_x
        y1 = pivot_y
        x2 = pivot_x + width * math.cos(angle)
        y2 = pivot_y + width * math.sin(angle)
        lw = 0.8 if i == 0 or i == winder_count else 0.4
        ax.plot([x1, x2], [y1, y2], color="#666666", linewidth=lw, zorder=6)

    # Winder 배경 (부채꼴 영역)
    winder_verts = [(pivot_x, pivot_y)]
    num_arc_pts = winder_count * 4
    for i in range(num_arc_pts + 1):
        angle = math.radians(base_angle + sign * turn_angle * i / num_arc_pts)
        winder_verts.append((pivot_x + width * math.cos(angle),
                            pivot_y + width * math.sin(angle)))
    winder_verts.append((pivot_x, pivot_y))
    winder_bg = patches.Polygon(winder_verts, closed=True,
        linewidth=0.5, edgecolor="#555555", facecolor="#F0F0F0", alpha=0.3, zorder=4)
    ax.add_patch(winder_bg)

    # Winder 트레드 번호
    mid_r = width * 0.5
    for i in range(winder_count):
        angle = math.radians(base_angle + sign * angle_step * (i + 0.5))
        tx = pivot_x + mid_r * math.cos(angle)
        ty = pivot_y + mid_r * math.sin(angle)
        ax.text(tx, ty, str(treads_before + i + 1), ha="center", va="center",
                fontsize=3.5, color="#888888", zorder=7)

    # --- 3) 두 번째 직선부 ---
    if treads_after > 0:
        turn_sign = 1 if turn_dir == "right" else -1
        dir2 = direction + turn_sign * turn_angle
        # 두 번째 런 시작점 계산
        end_angle = math.radians(base_angle + sign * turn_angle)
        run2_sx = pivot_x + width * math.cos(end_angle)
        run2_sy = pivot_y + width * math.sin(end_angle)
        _draw_straight_stairs(ax, run2_sx, run2_sy, dir2, width, treads_after, tread_depth)


# ============================================================
# 발코니 난간 심볼
# ============================================================

def draw_balcony_railing(ax, room, exterior_edges):
    """발코니 방의 외벽을 난간으로 표시"""
    railing = room.get("railing")
    if not railing:
        return

    for (sx, sy), (ex, ey) in exterior_edges:
        wall_len = math.hypot(ex - sx, ey - sy)
        if wall_len < 0.1:
            continue
        # 난간 선 (점선)
        ax.plot([sx, ex], [sy, ey],
                color="#666666", linewidth=2.0, linestyle=(0, (3, 2)), zorder=7)
        # 발루스터 틱마크
        num_posts = max(2, int(wall_len / 0.15))
        ddx = (ex - sx) / wall_len
        ddy = (ey - sy) / wall_len
        nx, ny = -ddy, ddx
        tick_len = 0.08
        for i in range(num_posts + 1):
            frac = i / num_posts
            px = sx + ddx * wall_len * frac
            py = sy + ddy * wall_len * frac
            ax.plot([px - nx * tick_len, px + nx * tick_len],
                    [py - ny * tick_len, py + ny * tick_len],
                    color="#666666", linewidth=0.6, zorder=7)
