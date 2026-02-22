"""
House Designer - 다각형 기하학 유틸리티
다각형/직사각형 통합 처리, 면적/중심/변 추출, 좌표 정규화
"""

# 부동소수점 허용치 (좌표 비교용)
EPS = 1e-4


def snap(v):
    """좌표를 소수 2자리로 반올림하여 부동소수점 문제 방지"""
    return round(v, 2)


def edge_key(p1, p2):
    """두 점으로 정규화된 edge key 생성. snap 적용."""
    a = (snap(p1[0]), snap(p1[1]))
    b = (snap(p2[0]), snap(p2[1]))
    return (min(a, b), max(a, b))


# --- 다각형 수학 ---

def polygon_area(vertices):
    """Shoelace formula로 다각형 면적 계산.
    vertices: [(x1,y1), (x2,y2), ...] 순서대로.
    """
    n = len(vertices)
    if n < 3:
        return 0.0
    area = 0.0
    for i in range(n):
        j = (i + 1) % n
        area += vertices[i][0] * vertices[j][1]
        area -= vertices[j][0] * vertices[i][1]
    return abs(area) / 2.0


def polygon_centroid(vertices):
    """다각형의 무게중심 계산."""
    n = len(vertices)
    if n == 0:
        return (0, 0)
    if n == 1:
        return (vertices[0][0], vertices[0][1])
    if n == 2:
        return ((vertices[0][0] + vertices[1][0]) / 2,
                (vertices[0][1] + vertices[1][1]) / 2)

    area = 0.0
    cx = 0.0
    cy = 0.0
    for i in range(n):
        j = (i + 1) % n
        cross = vertices[i][0] * vertices[j][1] - vertices[j][0] * vertices[i][1]
        area += cross
        cx += (vertices[i][0] + vertices[j][0]) * cross
        cy += (vertices[i][1] + vertices[j][1]) * cross

    area /= 2.0
    if abs(area) < 1e-10:
        # 퇴화 다각형 — 단순 평균
        avg_x = sum(v[0] for v in vertices) / n
        avg_y = sum(v[1] for v in vertices) / n
        return (avg_x, avg_y)

    cx /= (6.0 * area)
    cy /= (6.0 * area)
    return (cx, cy)


def polygon_edges(vertices):
    """다각형의 변 목록 반환. [(p1, p2), ...]"""
    n = len(vertices)
    edges = []
    for i in range(n):
        j = (i + 1) % n
        p1 = (snap(vertices[i][0]), snap(vertices[i][1]))
        p2 = (snap(vertices[j][0]), snap(vertices[j][1]))
        edges.append((p1, p2))
    return edges


def polygon_bbox(vertices):
    """다각형의 AABB 바운딩 박스 (min_x, min_y, max_x, max_y)"""
    xs = [v[0] for v in vertices]
    ys = [v[1] for v in vertices]
    return (min(xs), min(ys), max(xs), max(ys))


def point_in_polygon(point, vertices):
    """Ray casting 알고리즘으로 점이 다각형 내부에 있는지 검사."""
    px, py = point
    n = len(vertices)
    inside = False
    j = n - 1
    for i in range(n):
        xi, yi = vertices[i]
        xj, yj = vertices[j]
        if ((yi > py) != (yj > py)) and (px < (xj - xi) * (py - yi) / (yj - yi) + xi):
            inside = not inside
        j = i
    return inside


def segments_intersect(p1, p2, p3, p4):
    """두 선분 (p1-p2, p3-p4)이 교차하는지 검사.
    끝점에서 만나는 경우(접하는 경우)는 False로 처리."""
    def cross(o, a, b):
        return (a[0] - o[0]) * (b[1] - o[1]) - (a[1] - o[1]) * (b[0] - o[0])

    d1 = cross(p3, p4, p1)
    d2 = cross(p3, p4, p2)
    d3 = cross(p1, p2, p3)
    d4 = cross(p1, p2, p4)

    if ((d1 > EPS and d2 < -EPS) or (d1 < -EPS and d2 > EPS)) and \
       ((d3 > EPS and d4 < -EPS) or (d3 < -EPS and d4 > EPS)):
        return True
    return False


def polygons_overlap(verts_a, verts_b):
    """두 다각형이 겹치는지 검사.
    변 교차 + 내부 포함 검사. 접하는 것(edge 공유)은 OK."""
    # 1. 변 교차 검사
    edges_a = polygon_edges(verts_a)
    edges_b = polygon_edges(verts_b)
    for ea in edges_a:
        for eb in edges_b:
            if segments_intersect(ea[0], ea[1], eb[0], eb[1]):
                return True

    # 2. 한쪽이 다른 쪽 완전 포함 검사
    # A의 centroid가 B 안에 있거나 B의 centroid가 A 안에 있는 경우
    ca = polygon_centroid(verts_a)
    cb = polygon_centroid(verts_b)
    if point_in_polygon(ca, verts_b) or point_in_polygon(cb, verts_a):
        return True

    return False


# --- 방(room) 통합 처리 ---

def room_vertices(room):
    """방의 꼭짓점 목록 반환. 다각형이면 vertices, 직사각형이면 4개 점 생성."""
    if "vertices" in room and room["vertices"]:
        return [(snap(v[0]), snap(v[1])) for v in room["vertices"]]
    x = snap(room.get("x", 0))
    y = snap(room.get("y", 0))
    w = snap(room.get("width", 0))
    d = snap(room.get("depth", 0))
    return [(x, y), (x + w, y), (x + w, y + d), (x, y + d)]


def room_to_edges(room):
    """방의 변 목록 반환. 직사각형/다각형 통합."""
    verts = room_vertices(room)
    return polygon_edges(verts)


def room_area(room):
    """방의 면적. 직사각형이면 width*depth, 다각형이면 Shoelace."""
    if "vertices" in room and room["vertices"]:
        return polygon_area(room["vertices"])
    return room.get("width", 0) * room.get("depth", 0)


def room_centroid(room):
    """방의 중심점."""
    if "vertices" in room and room["vertices"]:
        return polygon_centroid(room["vertices"])
    x = room.get("x", 0)
    y = room.get("y", 0)
    w = room.get("width", 0)
    d = room.get("depth", 0)
    return (x + w / 2, y + d / 2)


def room_bbox(room):
    """방의 AABB 바운딩 박스 (min_x, min_y, max_x, max_y)."""
    verts = room_vertices(room)
    return polygon_bbox(verts)


def rooms_overlap(room_a, room_b):
    """두 방이 겹치는지 검사. 접하는 것은 OK."""
    verts_a = room_vertices(room_a)
    verts_b = room_vertices(room_b)

    # 빠른 AABB 사전 검사
    bbox_a = polygon_bbox(verts_a)
    bbox_b = polygon_bbox(verts_b)
    if (bbox_a[2] <= bbox_b[0] + EPS or bbox_b[2] <= bbox_a[0] + EPS or
            bbox_a[3] <= bbox_b[1] + EPS or bbox_b[3] <= bbox_a[1] + EPS):
        return False

    # 다각형 or 직사각형 모두 통합 처리
    return polygons_overlap(verts_a, verts_b)


def point_in_room(point, room):
    """점이 방 안에 있는지 검사."""
    verts = room_vertices(room)
    return point_in_polygon(point, verts)


# --- 계단 기하학 헬퍼 ---

def stair_total_run(stair):
    """계단의 총 수평 길이 (디딤판 깊이 × 디딤판 수). L/U턴은 랜딩 포함."""
    num = stair.get("num_treads", 15)
    td = stair.get("tread_depth", 0.28)
    stype = stair.get("type", "straight")
    run = num * td
    if stype == "l_shape":
        # L자: 절반 + 랜딩 + 절반 (직각 방향)
        landing = stair.get("landing_depth", 1.0)
        half = num // 2
        run = half * td + landing
    elif stype == "u_turn":
        landing = stair.get("landing_depth", 1.0)
        half = num // 2
        run = half * td + landing
    return round(run, 3)


def stair_total_rise(stair):
    """계단의 총 높이 (챌면 높이 × 디딤판 수)"""
    return round(stair.get("riser_height", 0.187) * stair.get("num_treads", 15), 3)


def stair_footprint(stair):
    """계단의 바닥 점유 영역 (min_x, min_y, max_x, max_y).
    방향(direction)에 따라 계산."""
    sx, sy = stair.get("start", [0, 0])
    width = stair.get("width", 1.0)
    num = stair.get("num_treads", 15)
    td = stair.get("tread_depth", 0.28)
    direction = stair.get("direction", 0)
    stype = stair.get("type", "straight")
    landing = stair.get("landing_depth", 1.0)
    turn = stair.get("turn_direction", "right")

    if stype == "straight":
        run = num * td
        if direction == 0:    # +Y
            return (sx, sy, sx + width, sy + run)
        elif direction == 90:  # +X
            return (sx, sy, sx + run, sy + width)
        elif direction == 180: # -Y
            return (sx, sy - run, sx + width, sy)
        elif direction == 270: # -X
            return (sx - run, sy, sx, sy + width)

    elif stype == "l_shape":
        half = num // 2
        run1 = half * td
        run2 = (num - half) * td
        if direction == 0:
            if turn == "right":
                return (sx, sy, sx + width + run2, sy + run1 + landing)
            else:
                return (sx - run2, sy, sx + width, sy + run1 + landing)
        elif direction == 90:
            if turn == "right":
                return (sx, sy - run2, sx + run1 + landing, sy + width)
            else:
                return (sx, sy, sx + run1 + landing, sy + width + run2)
        elif direction == 180:
            if turn == "right":
                return (sx - run2, sy - run1 - landing, sx + width, sy)
            else:
                return (sx, sy - run1 - landing, sx + width + run2, sy)
        elif direction == 270:
            if turn == "right":
                return (sx - run1 - landing, sy, sx, sy + width + run2)
            else:
                return (sx - run1 - landing, sy - run2, sx, sy + width)

    elif stype == "u_turn":
        half = num // 2
        run1 = half * td
        # U턴: 두 런이 병렬, 사이에 랜딩
        total_width = width * 2 + 0.1  # 두 런 + 간격
        if direction == 0:
            return (sx, sy, sx + total_width, sy + run1 + landing)
        elif direction == 90:
            return (sx, sy, sx + run1 + landing, sy + total_width)
        elif direction == 180:
            return (sx, sy - run1 - landing, sx + total_width, sy)
        elif direction == 270:
            return (sx - run1 - landing, sy, sx, sy + total_width)

    # Fallback
    run = num * td
    return (sx, sy, sx + width, sy + run)


# --- 선분 교차/교점 ---

def line_segment_intersection(p1, p2, p3, p4):
    """두 선분 (p1-p2)와 (p3-p4)의 교점 좌표 반환. 교차하지 않으면 None."""
    x1, y1 = p1
    x2, y2 = p2
    x3, y3 = p3
    x4, y4 = p4

    denom = (x1 - x2) * (y3 - y4) - (y1 - y2) * (x3 - x4)
    if abs(denom) < EPS:
        return None  # 평행 또는 일치

    t = ((x1 - x3) * (y3 - y4) - (y1 - y3) * (x3 - x4)) / denom
    u = -((x1 - x2) * (y1 - y3) - (y1 - y2) * (x1 - x3)) / denom

    if -EPS <= t <= 1 + EPS and -EPS <= u <= 1 + EPS:
        ix = x1 + t * (x2 - x1)
        iy = y1 + t * (y2 - y1)
        return (ix, iy)
    return None


def line_intersect_rect(p1, p2, rect_min_x, rect_min_y, rect_max_x, rect_max_y):
    """선분과 AABB 직사각형의 교점들 반환 (0~2개)."""
    edges = [
        ((rect_min_x, rect_min_y), (rect_max_x, rect_min_y)),
        ((rect_max_x, rect_min_y), (rect_max_x, rect_max_y)),
        ((rect_max_x, rect_max_y), (rect_min_x, rect_max_y)),
        ((rect_min_x, rect_max_y), (rect_min_x, rect_min_y)),
    ]
    pts = []
    for e1, e2 in edges:
        pt = line_segment_intersection(p1, p2, e1, e2)
        if pt:
            # 중복 제거
            is_dup = False
            for existing in pts:
                if abs(existing[0] - pt[0]) < EPS and abs(existing[1] - pt[1]) < EPS:
                    is_dup = True
                    break
            if not is_dup:
                pts.append(pt)
    return pts


def cut_line_through_design(design, cut_start, cut_end):
    """절단선과 교차하는 모든 벽/창문/문 정보를 추출.
    Returns: {walls: [{wall, entry_pt, exit_pt}], windows: [...], doors: [...]}
    """
    result = {"walls": [], "windows": [], "doors": []}

    for floor in design.get("floors", []):
        floor_elevation = floor.get("elevation", 0)
        floor_height = floor.get("height", 2.8)

        for wall in floor.get("walls", []):
            sx, sy = wall["start"]
            ex, ey = wall["end"]
            pt = line_segment_intersection(cut_start, cut_end, (sx, sy), (ex, ey))
            if pt:
                result["walls"].append({
                    "wall": wall,
                    "intersection": pt,
                    "floor_elevation": floor_elevation,
                    "floor_height": floor_height,
                    "floor_id": floor["id"],
                })

        for win in floor.get("windows", []):
            wall_id = win.get("wall_id")
            wall = None
            for w in floor.get("walls", []):
                if w["id"] == wall_id:
                    wall = w
                    break
            if not wall:
                continue
            wsx, wsy = wall["start"]
            wex, wey = wall["end"]
            wlen = ((wex - wsx)**2 + (wey - wsy)**2)**0.5
            if wlen < 0.01:
                continue
            dx, dy = (wex - wsx) / wlen, (wey - wsy) / wlen
            pos = win.get("position", 0)
            ww = win.get("width", 1.5)
            wp1 = (wsx + dx * (pos - ww / 2), wsy + dy * (pos - ww / 2))
            wp2 = (wsx + dx * (pos + ww / 2), wsy + dy * (pos + ww / 2))
            pt = line_segment_intersection(cut_start, cut_end, wp1, wp2)
            if pt:
                result["windows"].append({
                    "window": win,
                    "intersection": pt,
                    "floor_elevation": floor_elevation,
                    "floor_height": floor_height,
                })

        for door in floor.get("doors", []):
            wall_id = door.get("wall_id")
            wall = None
            for w in floor.get("walls", []):
                if w["id"] == wall_id:
                    wall = w
                    break
            if not wall:
                continue
            wsx, wsy = wall["start"]
            wex, wey = wall["end"]
            wlen = ((wex - wsx)**2 + (wey - wsy)**2)**0.5
            if wlen < 0.01:
                continue
            dx, dy = (wex - wsx) / wlen, (wey - wsy) / wlen
            pos = door.get("position", 0)
            dw = door.get("width", 0.9)
            dp1 = (wsx + dx * (pos - dw / 2), wsy + dy * (pos - dw / 2))
            dp2 = (wsx + dx * (pos + dw / 2), wsy + dy * (pos + dw / 2))
            pt = line_segment_intersection(cut_start, cut_end, dp1, dp2)
            if pt:
                result["doors"].append({
                    "door": door,
                    "intersection": pt,
                    "floor_elevation": floor_elevation,
                    "floor_height": floor_height,
                })

    return result


def furniture_in_room(furn, room):
    """가구(직사각형)가 방 안에 완전히 포함되는지 검사.
    가구의 4 꼭짓점이 모두 방 내부에 있어야 함."""
    fx, fy = furn.get("x", 0), furn.get("y", 0)
    fw, fd = furn.get("width", 0), furn.get("depth", 0)
    corners = [(fx, fy), (fx + fw, fy), (fx + fw, fy + fd), (fx, fy + fd)]
    room_verts = room_vertices(room)

    for corner in corners:
        if not point_in_polygon(corner, room_verts):
            # 경계 위의 점은 허용
            bbox = polygon_bbox(room_verts)
            on_edge = (abs(corner[0] - bbox[0]) < EPS or abs(corner[0] - bbox[2]) < EPS or
                       abs(corner[1] - bbox[1]) < EPS or abs(corner[1] - bbox[3]) < EPS)
            if not on_edge:
                return False
    return True
