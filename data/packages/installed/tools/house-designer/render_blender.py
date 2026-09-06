"""House Designer — Blender/Cycles 오프라인 렌더러 + glTF 내보내기

설계 JSON(design_*.json)을 Blender 씬으로 조립해 Cycles 로 렌더한다.
Three.js 뷰어(templates/3d_viewer.html)와 같은 스키마를 읽되, 목적이 다르다:
뷰어 = 형상 확인(실시간), 이 스크립트 = 완성 컷(오프라인 PBR).

사용법:
  blender --background --python render_blender.py -- <design.json> <out.png>
          [--samples 128] [--res 1600 900] [--view sw|se|nw|ne] [--gltf out.glb]
"""
import bpy
import json
import math
import os
import sys

# ---------------------------------------------------------------- 인자 파싱

def parse_args():
    argv = sys.argv
    argv = argv[argv.index("--") + 1:] if "--" in argv else []
    if len(argv) < 2:
        raise SystemExit("usage: ... -- <design.json> <out.png> [--samples N] [--res W H] [--view sw] [--gltf path]")
    cfg = {
        "design": argv[0], "out": argv[1],
        "samples": 128, "res": (1600, 900), "view": "auto", "gltf": None,
    }
    i = 2
    while i < len(argv):
        a = argv[i]
        if a == "--samples":
            cfg["samples"] = int(argv[i + 1]); i += 2
        elif a == "--res":
            cfg["res"] = (int(argv[i + 1]), int(argv[i + 2])); i += 3
        elif a == "--view":
            cfg["view"] = argv[i + 1]; i += 2
        elif a == "--gltf":
            cfg["gltf"] = argv[i + 1]; i += 2
        else:
            i += 1
    return cfg


# ---------------------------------------------------------------- 색·재질

ROOM_COLORS = {
    "living": "#E8D5B7", "bedroom": "#D5E8D5", "kitchen": "#B7D5E8",
    "bathroom": "#D5B7E8", "dining": "#E8E0B7", "garage": "#D0D0D0",
    "hallway": "#F0F0E0", "closet": "#E0D8D0", "office": "#D0D8E8",
    "laundry": "#C8D8E0", "balcony": "#D8E8D0", "entrance": "#E0E0D0",
    "stairs": "#C0C0C0", "storage": "#D8D0C8", "other": "#E0E0E0",
}

ROOF_COLORS = {
    "shingle": "#5D4E37", "tile": "#8B4513", "metal": "#708090",
    "concrete": "#A0A0A0", "slate": "#4A4A55", "green": "#6B8E5A",
}

WALL_COLORS = {
    "concrete": "#D8D5CC", "brick": "#9C5B45", "wood": "#B08A55",
    "stucco": "#E6E1D6", "stone": "#9A958C", "siding": "#DAD6C8",
}

_MAT_CACHE = {}


def srgb_to_linear(c):
    return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4


def hex_rgba(h, alpha=1.0):
    h = (h or "#CCCCCC").lstrip("#")
    if len(h) == 3:
        h = "".join(ch * 2 for ch in h)
    r, g, b = (int(h[i:i + 2], 16) / 255.0 for i in (0, 2, 4))
    return (srgb_to_linear(r), srgb_to_linear(g), srgb_to_linear(b), alpha)


def _shade(rgba, f):
    return tuple([c * f for c in rgba[:3]] + [1.0])


def make_material(name, hex_color, roughness=0.6, metallic=0.0, transmission=0.0,
                  bump=0.0, pattern=None, tex_scale=1.0):
    """Principled BSDF 재질.

    pattern: 'stucco'(외벽 미장) · 'shingle'(지붕 잇단) · 'grass'(잔디) · None
    텍스처 좌표는 오브젝트 공간(=미터)을 쓴다 — Generated 좌표는 오브젝트 크기로
    정규화돼 2만m 지면에서 노이즈 한 덩이가 '잘린 판'처럼 보였다(2026-09-06 실측).
    """
    key = (name, hex_color, roughness, metallic, transmission, bump, pattern, tex_scale)
    if key in _MAT_CACHE:
        return _MAT_CACHE[key]

    mat = bpy.data.materials.new(name=name)
    mat.use_nodes = True
    nt = mat.node_tree
    bsdf = nt.nodes.get("Principled BSDF")
    bsdf.inputs["Base Color"].default_value = hex_rgba(hex_color)
    bsdf.inputs["Roughness"].default_value = roughness
    bsdf.inputs["Metallic"].default_value = metallic

    for key_name in ("Transmission Weight", "Transmission"):
        if key_name in bsdf.inputs:
            bsdf.inputs[key_name].default_value = transmission
            break
    if transmission > 0:
        for key_name in ("IOR",):
            if key_name in bsdf.inputs:
                bsdf.inputs[key_name].default_value = 1.45
        mat.blend_method = "BLEND"

    if bump > 0:
        tex = nt.nodes.new("ShaderNodeTexNoise")
        tex.inputs["Scale"].default_value = 42.0
        tex.inputs["Detail"].default_value = 8.0
        bump_node = nt.nodes.new("ShaderNodeBump")
        bump_node.inputs["Strength"].default_value = bump
        bump_node.inputs["Distance"].default_value = 0.004
        nt.links.new(tex.outputs["Fac"], bump_node.inputs["Height"])
        nt.links.new(bump_node.outputs["Normal"], bsdf.inputs["Normal"])

        # 알베도·러프니스에도 같은 노이즈를 얹는다 — 균일 단색이 CG 티의 주범
        base = hex_rgba(hex_color)
        dark = tuple([c * 0.82 for c in base[:3]] + [1.0])
        ramp = nt.nodes.new("ShaderNodeValToRGB")
        ramp.color_ramp.elements[0].color = dark
        ramp.color_ramp.elements[1].color = base
        big = nt.nodes.new("ShaderNodeTexNoise")
        big.inputs["Scale"].default_value = 6.0
        big.inputs["Detail"].default_value = 6.0
        nt.links.new(big.outputs["Fac"], ramp.inputs["Fac"])
        nt.links.new(ramp.outputs["Color"], bsdf.inputs["Base Color"])

        rmix = nt.nodes.new("ShaderNodeMapRange")
        rmix.inputs["To Min"].default_value = max(0.05, roughness - 0.12)
        rmix.inputs["To Max"].default_value = min(1.0, roughness + 0.12)
        nt.links.new(tex.outputs["Fac"], rmix.inputs["Value"])
        nt.links.new(rmix.outputs["Result"], bsdf.inputs["Roughness"])

    _MAT_CACHE[key] = mat
    return mat


# ---------------------------------------------------------------- 지오메트리

BOUNDS = {"min": [1e9, 1e9, 0.0], "max": [-1e9, -1e9, 0.0]}


def track(x, y, z):
    BOUNDS["min"][0] = min(BOUNDS["min"][0], x)
    BOUNDS["min"][1] = min(BOUNDS["min"][1], y)
    BOUNDS["max"][0] = max(BOUNDS["max"][0], x)
    BOUNDS["max"][1] = max(BOUNDS["max"][1], y)
    BOUNDS["max"][2] = max(BOUNDS["max"][2], z)


def add_bevel(obj, width=0.012):
    """모든 솔리드에 얇은 모따기 — 각진 실루엣이 빛을 물게 하는 값싼 수단."""
    m = obj.modifiers.new(name="Bevel", type="BEVEL")
    m.width = width
    m.segments = 2
    m.limit_method = "ANGLE"
    m.angle_limit = math.radians(40)


def add_box(name, sx, sy, sz, loc, mat, rot_z=0.0, bevel=True):
    bpy.ops.mesh.primitive_cube_add(size=1, location=loc)
    obj = bpy.context.active_object
    obj.name = name
    obj.scale = (sx, sy, sz)
    obj.rotation_euler = (0, 0, rot_z)
    bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
    obj.data.materials.append(mat)
    if bevel and min(sx, sy, sz) > 0.03:
        add_bevel(obj)
    track(loc[0] + sx / 2, loc[1] + sy / 2, loc[2] + sz / 2)
    track(loc[0] - sx / 2, loc[1] - sy / 2, loc[2])
    return obj


def add_polygon(name, verts2d, z, mat):
    """평면 다각형(바닥 타일)."""
    mesh = bpy.data.meshes.new(name)
    verts = [(vx, vy, z) for vx, vy in verts2d]
    mesh.from_pydata(verts, [], [list(range(len(verts)))])
    mesh.update()
    obj = bpy.data.objects.new(name, mesh)
    bpy.context.collection.objects.link(obj)
    obj.data.materials.append(mat)
    for vx, vy in verts2d:
        track(vx, vy, z)
    return obj


def add_mesh(name, verts, faces, mat, bevel=False):
    mesh = bpy.data.meshes.new(name)
    mesh.from_pydata(verts, [], faces)
    mesh.update()
    obj = bpy.data.objects.new(name, mesh)
    bpy.context.collection.objects.link(obj)
    obj.data.materials.append(mat)
    if bevel:
        add_bevel(obj, 0.02)
    for v in verts:
        track(v[0], v[1], v[2])
    return obj


# ---------------------------------------------------------------- 설계 읽기

def room_vertices(room):
    """다각형이면 vertices, 아니면 x/y/width/depth 사각형."""
    vs = room.get("vertices")
    if vs and len(vs) >= 3:
        return [(float(v[0]), float(v[1])) for v in vs]
    x, y = float(room.get("x", 0)), float(room.get("y", 0))
    w, d = float(room.get("width", 3)), float(room.get("depth", 3))
    return [(x, y), (x + w, y), (x + w, y + d), (x, y + d)]


def room_bbox(room):
    vs = room_vertices(room)
    xs = [v[0] for v in vs]
    ys = [v[1] for v in vs]
    return min(xs), max(xs), min(ys), max(ys)


def auto_walls(rooms):
    """벽 데이터가 없으면 방 외곽선에서 생성 — 두 방이 공유하면 내벽."""
    counts = {}
    order = []
    for room in rooms:
        vs = room_vertices(room)
        for i in range(len(vs)):
            a, b = vs[i], vs[(i + 1) % len(vs)]
            key = tuple(sorted([(round(a[0], 2), round(a[1], 2)), (round(b[0], 2), round(b[1], 2))]))
            if key not in counts:
                counts[key] = 0
                order.append(key)
            counts[key] += 1
    walls = []
    for idx, key in enumerate(order):
        (sx, sy), (ex, ey) = key
        walls.append({
            "id": "auto_%d" % idx, "start": [sx, sy], "end": [ex, ey],
            "type": "interior" if counts[key] > 1 else "exterior",
        })
    return walls


def build_wall_segment(prefix, sx, sy, dx, dy, t0, t1, height, thick, z, angle, mat):
    seg_len = t1 - t0
    if seg_len <= 0.01 or height <= 0.02:
        return
    mid = (t0 + t1) / 2
    cx = sx + dx * mid
    cy = sy + dy * mid
    add_box(prefix, seg_len, thick, height, (cx, cy, z + height / 2), mat, rot_z=angle)


def build_floor(design, floor, cx0, cy0):
    elev = float(floor.get("elevation", 0) or 0)
    h = float(floor.get("height", 2.8) or 2.8)
    is_piloti = bool(floor.get("is_piloti"))
    rooms = floor.get("rooms", []) or []
    fid = floor.get("id", "floor")

    facade = design.get("facade_defaults") or design.get("facade") or {}
    fac_color = facade.get("color") or WALL_COLORS.get(facade.get("material") or "", "#E0DDD0")

    mat_slab = make_material("slab", "#CFC7B8", roughness=0.85, bump=0.15)
    mat_ext = make_material("wall_ext", fac_color, roughness=0.72, bump=0.25)
    mat_int = make_material("wall_int", "#EDE9E1", roughness=0.8, bump=0.1)
    mat_glass = make_material("glass", "#CFE6F5", roughness=0.05, metallic=0.0, transmission=0.9)
    mat_door = make_material("door", "#8A6A4A", roughness=0.45, bump=0.1)

    # 바닥 슬라브
    if rooms:
        xs0, xs1, ys0, ys1 = 1e9, -1e9, 1e9, -1e9
        for r in rooms:
            a, b, c, d = room_bbox(r)
            xs0, xs1, ys0, ys1 = min(xs0, a), max(xs1, b), min(ys0, c), max(ys1, d)
        add_box("%s_slab" % fid, (xs1 - xs0) + 0.24, (ys1 - ys0) + 0.24, 0.22,
                ((xs0 + xs1) / 2 - cx0, (ys0 + ys1) / 2 - cy0, elev - 0.11), mat_slab)

    # 방 바닥
    for r in rooms:
        color = r.get("color") or ROOM_COLORS.get(r.get("type"), "#E0E0E0")
        mat = make_material("room_%s" % (r.get("type") or "other"), color, roughness=0.55)
        verts = [(vx - cx0, vy - cy0) for vx, vy in room_vertices(r)]
        add_polygon("%s_%s" % (fid, r.get("name", "room")), verts, elev + 0.02, mat)

    if is_piloti:
        return

    # 벽
    walls = floor.get("walls") or []
    if not walls and rooms:
        walls = auto_walls(rooms)

    # 벽 데이터가 없어 자동 생성한 경우, 개구부의 wall_id 가 가리키는 벽이 존재하지 않는다.
    # 그냥 두면 창·문이 통째로 사라지므로 긴 외벽부터 차례로 배정한다.
    wall_ids = {w.get("id") for w in walls}

    def wall_len(w):
        return math.hypot(float(w["end"][0]) - float(w["start"][0]),
                          float(w["end"][1]) - float(w["start"][1]))

    exterior_sorted = sorted([w for w in walls if w.get("type") == "exterior"],
                            key=wall_len, reverse=True)
    orphan_slot = 0

    def resolve_wall_id(op):
        nonlocal orphan_slot
        wid = op.get("wall_id")
        if wid in wall_ids:
            return wid
        if not exterior_sorted:
            return wid
        target = exterior_sorted[orphan_slot % len(exterior_sorted)]
        orphan_slot += 1
        print("[render_blender] 경고: 개구부 %s 의 wall_id(%s)가 없어 외벽 %s 에 배정"
              % (op.get("id"), wid, target.get("id")))
        return target.get("id")

    doors_by_wall, wins_by_wall = {}, {}
    for d in floor.get("doors", []) or []:
        doors_by_wall.setdefault(resolve_wall_id(d), []).append(d)
    for w in floor.get("windows", []) or []:
        wins_by_wall.setdefault(resolve_wall_id(w), []).append(w)

    for wi, wall in enumerate(walls):
        sx, sy = float(wall["start"][0]) - cx0, float(wall["start"][1]) - cy0
        ex, ey = float(wall["end"][0]) - cx0, float(wall["end"][1]) - cy0
        length = math.hypot(ex - sx, ey - sy)
        if length < 0.01:
            continue
        dx, dy = (ex - sx) / length, (ey - sy) / length
        angle = math.atan2(dy, dx)
        is_ext = wall.get("type") == "exterior"
        thick = float(wall.get("thickness") or (0.2 if is_ext else 0.12))
        mat = mat_ext if is_ext else mat_int
        if is_ext and wall.get("color"):
            mat = make_material("wall_%d" % wi, wall["color"], roughness=0.72, bump=0.25)

        openings = []
        for d in doors_by_wall.get(wall.get("id"), []):
            dw = float(d.get("width", 0.9))
            pos = float(d.get("position", length / 2))
            openings.append({"s": pos - dw / 2, "e": pos + dw / 2, "kind": "door",
                             "h": min(float(d.get("height", 2.1)), h), "sill": 0.0})
        for w in wins_by_wall.get(wall.get("id"), []):
            ww = float(w.get("width", 1.5))
            pos = float(w.get("position", length / 2))
            openings.append({"s": pos - ww / 2, "e": pos + ww / 2, "kind": "window",
                             "h": float(w.get("height", 1.2)), "sill": float(w.get("sill_height", 0.9))})
        openings.sort(key=lambda o: o["s"])

        name = "%s_wall%d" % (fid, wi)
        if not openings:
            build_wall_segment(name, sx, sy, dx, dy, 0, length, h, thick, elev, angle, mat)
            continue

        prev = 0.0
        for oi, op in enumerate(openings):
            s = max(0.0, op["s"])
            e = min(length, op["e"])
            if e <= s:
                continue
            if s > prev + 0.01:
                build_wall_segment(name, sx, sy, dx, dy, prev, s, h, thick, elev, angle, mat)
            sill, oh = op["sill"], op["h"]
            if sill > 0.05:
                build_wall_segment(name + "_u", sx, sy, dx, dy, s, e, sill, thick, elev, angle, mat)
            above = sill + oh
            if above < h - 0.05:
                build_wall_segment(name + "_o", sx, sy, dx, dy, s, e, h - above, thick, elev + above, angle, mat)
            mid = (s + e) / 2
            px, py = sx + dx * mid, sy + dy * mid
            if op["kind"] == "window":
                add_box("%s_glass%d" % (name, oi), e - s - 0.06, 0.02, oh - 0.06,
                        (px, py, elev + sill + oh / 2), mat_glass, rot_z=angle, bevel=False)
                # 창틀 — 네 개의 얇은 바(가운데를 막지 않는다)
                mat_frame = make_material("frame", "#3F3F3F", roughness=0.4, metallic=0.3)
                fb, ft = 0.06, thick + 0.02
                for dz, fw_, fh_ in ((-(oh - fb) / 2, e - s, fb), ((oh - fb) / 2, e - s, fb)):
                    add_box("%s_fr%d" % (name, oi), fw_, ft, fh_,
                            (px, py, elev + sill + oh / 2 + dz), mat_frame, rot_z=angle, bevel=False)
                for side in (-1, 1):
                    ox = side * ((e - s) - fb) / 2
                    add_box("%s_fv%d" % (name, oi), fb, ft, oh,
                            (px + math.cos(angle) * ox, py + math.sin(angle) * ox,
                             elev + sill + oh / 2), mat_frame, rot_z=angle, bevel=False)
            else:
                add_box("%s_door%d" % (name, oi), e - s - 0.04, 0.045, oh - 0.03,
                        (px, py, elev + oh / 2), mat_door, rot_z=angle)
            prev = e
        if prev < length - 0.01:
            build_wall_segment(name, sx, sy, dx, dy, prev, length, h, thick, elev, angle, mat)

    # 기둥·보
    mat_struct = make_material("struct", "#C8C4BC", roughness=0.8, bump=0.15)
    for ci, col in enumerate(floor.get("columns", []) or []):
        cw = float(col.get("width", 0.4))
        cd = float(col.get("depth", cw))
        add_box("%s_col%d" % (fid, ci), cw, cd, h,
                (float(col.get("x", 0)) - cx0, float(col.get("y", 0)) - cy0, elev + h / 2), mat_struct)
    for bi, beam in enumerate(floor.get("beams", []) or []):
        bs, be = beam.get("start"), beam.get("end")
        if not bs or not be:
            continue
        bx0, by0 = float(bs[0]) - cx0, float(bs[1]) - cy0
        bx1, by1 = float(be[0]) - cx0, float(be[1]) - cy0
        blen = math.hypot(bx1 - bx0, by1 - by0)
        if blen < 0.05:
            continue
        add_box("%s_beam%d" % (fid, bi), blen, float(beam.get("width", 0.3)), float(beam.get("depth", 0.4)),
                ((bx0 + bx1) / 2, (by0 + by1) / 2, elev + h - 0.2), mat_struct,
                rot_z=math.atan2(by1 - by0, bx1 - bx0))

    # 계단 (디딤판만 — 형상 인지용)
    mat_tread = make_material("tread", "#A98457", roughness=0.5, bump=0.2)
    mat_riser = make_material("riser", "#E6E1D6", roughness=0.7)
    for si, st in enumerate(floor.get("stairs", []) or []):
        start = st.get("start") or [st.get("x", 0), st.get("y", 0)]
        x0 = float(start[0]) - cx0
        y0 = float(start[1]) - cy0
        n = int(st.get("num_treads", st.get("steps", 14)) or 14)
        sw = float(st.get("width", 1.0) or 1.0)
        tread = float(st.get("tread_depth", st.get("tread", 0.28)) or 0.28)
        rise = float(st.get("riser_height") or (h / max(n, 1)))
        ang = math.radians(float(st.get("direction", 0) or 0))
        ux, uy = math.cos(ang), math.sin(ang)      # 진행 방향
        px, py = -uy, ux                            # 폭 방향
        for k in range(n):
            off = tread * (k + 0.5)
            tx = x0 + ux * off + px * 0.0
            ty = y0 + uy * off + py * 0.0
            tz = elev + rise * (k + 1)
            add_box("%s_st%d_t%d" % (fid, si, k), tread, sw, 0.05,
                    (tx, ty, tz), mat_tread, rot_z=ang)
            add_box("%s_st%d_r%d" % (fid, si, k), 0.03, sw, rise,
                    (x0 + ux * tread * k, y0 + uy * tread * k, tz - rise / 2), mat_riser, rot_z=ang)


def build_roof(design, cx0, cy0):
    floors = design.get("floors", []) or []
    if not floors:
        return
    solid = [fl for fl in floors if (fl.get("rooms") or []) and not fl.get("is_piloti")]
    if not solid:
        return
    top_floor = max(solid, key=lambda fl: float(fl.get("elevation", 0) or 0))
    top = float(top_floor.get("elevation", 0) or 0) + float(top_floor.get("height", 2.8) or 2.8)

    def bbox_of(fl):
        a0, b0, c0, d0 = 1e9, -1e9, 1e9, -1e9
        for r in fl.get("rooms", []) or []:
            a, b, c, d = room_bbox(r)
            a0, b0, c0, d0 = min(a0, a), max(b0, b), min(c0, c), max(d0, d)
        return a0, b0, c0, d0

    # 경사지붕은 최상층 푸트프린트 위에만 — 아래층의 남는 면은 옥상 데크로
    minx, maxx, miny, maxy = bbox_of(top_floor)
    if minx > 1e8:
        return
    mat_deck = make_material("deck", "#C9C4B8", roughness=0.85, bump=0.25)
    mat_para = make_material("parapet", "#DFDBD0", roughness=0.75, bump=0.2)
    def covered(px, py, floor_above):
        for r in floor_above.get("rooms", []) or []:
            a, b, c, d = room_bbox(r)
            if a - 0.05 <= px <= b + 0.05 and c - 0.05 <= py <= d + 0.05:
                return True
        return False

    # 위층이 덮지 않는 '방'에만 옥상 슬래브 — 층 전체에 데크를 깔면 허공에 뜬 판이 된다
    for fl in solid:
        if fl is top_floor:
            continue
        ftop = float(fl.get("elevation", 0) or 0) + float(fl.get("height", 2.8) or 2.8)
        for ri, r in enumerate(fl.get("rooms", []) or []):
            a, b, c, d = room_bbox(r)
            if covered((a + b) / 2, (c + d) / 2, top_floor):
                continue
            dw, dd = (b - a) + 0.2, (d - c) + 0.2
            dcx, dcy = (a + b) / 2 - cx0, (c + d) / 2 - cy0
            add_box("deck_%s_%d" % (fl.get("id", "f"), ri), dw, dd, 0.16,
                    (dcx, dcy, ftop + 0.08), mat_deck)
            if (b - a) * (d - c) < 8.0:
                continue        # 현관처럼 작은 면은 캐노피 슬래브만 — 난간을 두르면 빈 상자로 보인다
            ph, pt = 0.5, 0.14
            zc = ftop + 0.16 + ph / 2
            add_box("para_a", dw, pt, ph, (dcx, dcy - dd / 2 + pt / 2, zc), mat_para)
            add_box("para_b", dw, pt, ph, (dcx, dcy + dd / 2 - pt / 2, zc), mat_para)
            add_box("para_c", pt, dd, ph, (dcx - dw / 2 + pt / 2, dcy, zc), mat_para)
            add_box("para_d", pt, dd, ph, (dcx + dw / 2 - pt / 2, dcy, zc), mat_para)

    roof = design.get("roof") or {}
    rtype = (roof.get("type") or "hip").lower()
    w = (maxx - minx) + 0.6
    d = (maxy - miny) + 0.6
    rh = float(roof.get("height") or min(min(w, d) * 0.25, 2.5))
    overhang = float(roof.get("overhang", 0.3) or 0.3)
    cx = (minx + maxx) / 2 - cx0
    cy = (miny + maxy) / 2 - cy0
    hw = w / 2 + overhang
    hd = d / 2 + overhang
    direction = (roof.get("direction") or "x").lower()
    if direction == "auto":
        direction = "x" if w >= d else "y"

    color = roof.get("color") or ROOF_COLORS.get(roof.get("material") or "shingle", "#5D4E37")
    mat_roof = make_material("roof", color, roughness=0.78, bump=0.3)

    if rtype == "flat":
        add_box("roof", w + overhang * 2, d + overhang * 2, 0.25, (cx, cy, top + 0.125), mat_roof)
        return

    b = [(cx - hw, cy - hd, top), (cx + hw, cy - hd, top),
         (cx + hw, cy + hd, top), (cx - hw, cy + hd, top)]

    if rtype in ("gable", "gable_glass"):
        if direction == "x":
            ridge = [(cx - hw, cy, top + rh), (cx + hw, cy, top + rh)]
            verts = b + ridge
            faces = [[0, 1, 5, 4], [2, 3, 4, 5], [0, 4, 3], [1, 2, 5]]
        else:
            ridge = [(cx, cy - hd, top + rh), (cx, cy + hd, top + rh)]
            verts = b + ridge
            faces = [[3, 0, 4, 5], [1, 2, 5, 4], [0, 1, 4], [2, 3, 5]]
    else:  # hip / mansard 근사
        inset_x = min(hw * 0.45, hw - 0.5)
        if direction == "x":
            ridge = [(cx - inset_x, cy, top + rh), (cx + inset_x, cy, top + rh)]
        else:
            inset_y = min(hd * 0.45, hd - 0.5)
            ridge = [(cx, cy - inset_y, top + rh), (cx, cy + inset_y, top + rh)]
        verts = b + ridge
        faces = [[0, 1, 5, 4], [2, 3, 4, 5], [0, 4, 3], [1, 2, 5]]

    add_mesh("roof", verts, faces, mat_roof, bevel=True)

    # 처마 코니스 — 벽 상단에 얹힌 얇은 띠 (허공에 뜨지 않도록 벽 안쪽에서 시작)
    add_box("eave", hw * 1.96, hd * 1.96, 0.10, (cx, cy, top - 0.02), mat_roof)


# ---------------------------------------------------------------- 씬 구성

VIEW_AZ = {"sw": 315, "se": 45, "ne": 135, "nw": 225}


def setup_world(sun_elev_deg=27.0, sun_rot_deg=200.0):
    world = bpy.data.worlds.new("World")
    bpy.context.scene.world = world
    world.use_nodes = True
    nt = world.node_tree
    bg = nt.nodes.get("Background")
    sky = nt.nodes.new("ShaderNodeTexSky")
    # 물리 하늘 — Blender 4.x=NISHITA, 5.x=MULTIPLE_SCATTERING 로 개명됨
    valid = [i.identifier for i in sky.bl_rna.properties["sky_type"].enum_items]
    for cand in ("MULTIPLE_SCATTERING", "NISHITA", "HOSEK_WILKIE"):
        if cand in valid:
            sky.sky_type = cand
            break
    else:
        print("[render_blender] 경고: 물리 하늘 타입 없음 — 기본 하늘 사용")
    for attr, val in (("sun_elevation", math.radians(sun_elev_deg)),
                      ("sun_rotation", math.radians(sun_rot_deg)),
                      ("altitude", 200.0)):
        if hasattr(sky, attr):
            setattr(sky, attr, val)
        else:
            print("[render_blender] 경고: 하늘 속성 %s 없음" % attr)
    nt.links.new(sky.outputs[0], bg.inputs[0])
    bg.inputs[1].default_value = 0.30   # 하늘광은 앰비언트로만 — 태양은 아래 SUN 이 맡는다

    bpy.ops.object.light_add(type="SUN", location=(0, 0, 30))
    sun = bpy.context.active_object
    sun.data.energy = 5.5
    sun.data.color = (1.0, 0.94, 0.84)
    sun.data.angle = math.radians(1.2)  # 그림자 경계 — 너무 크면 흐물해진다
    az = math.radians(sun_rot_deg)
    el = math.radians(sun_elev_deg)
    sun.rotation_euler = (math.pi / 2 - el, 0, az)
    return sun


def setup_ground():
    bpy.ops.mesh.primitive_plane_add(size=20000, location=(0, 0, 0))
    g = bpy.context.active_object
    g.name = "ground"
    # 지면은 노이즈 변주를 주지 않는다 — Generated 좌표가 오브젝트 크기로 정규화돼
    # 2만m 평면에서는 노이즈 한 덩이가 '잘린 잔디 판'처럼 보인다
    g.data.materials.append(make_material("ground", "#5E6E42", roughness=0.95))


def scene_bbox(exclude=("ground",)):
    """지면을 끌 전체 메시의 월드 바운딩박스 — 구도 계산의 진실 소스."""
    lo = [1e9, 1e9, 1e9]
    hi = [-1e9, -1e9, -1e9]
    for obj in bpy.context.scene.objects:
        if obj.type != "MESH" or obj.name in exclude:
            continue
        for corner in obj.bound_box:
            wc = obj.matrix_world @ __import__("mathutils").Vector(corner)
            for i in range(3):
                lo[i] = min(lo[i], wc[i])
                hi[i] = max(hi[i], wc[i])
    if lo[0] > 1e8:
        return (-5, -5, 0), (5, 5, 5)
    return tuple(lo), tuple(hi)


def pick_view(design):
    """창·문이 가장 많이 드러나는 방향을 고른다(개구부 없는 뒷면 렌더 방지)."""
    score = {"x_min": 0, "x_max": 0, "y_min": 0, "y_max": 0}
    minx, maxx, miny, maxy = 1e9, -1e9, 1e9, -1e9
    walls_all = []
    for fl in design.get("floors", []) or []:
        for r in fl.get("rooms", []) or []:
            a, b, c, d = room_bbox(r)
            minx, maxx, miny, maxy = min(minx, a), max(maxx, b), min(miny, c), max(maxy, d)
        by_id = {w.get("id"): w for w in (fl.get("walls") or [])}
        for op in (fl.get("windows") or []) + (fl.get("doors") or []):
            w = by_id.get(op.get("wall_id"))
            if w:
                walls_all.append(w)
    if minx > 1e8:
        return "sw"
    tol = 0.6
    for w in walls_all:
        sx, sy = float(w["start"][0]), float(w["start"][1])
        ex, ey = float(w["end"][0]), float(w["end"][1])
        if abs(sy - ey) < 0.01:            # 수평벽 → y 면
            if abs(sy - miny) < tol:
                score["y_min"] += 1
            elif abs(sy - maxy) < tol:
                score["y_max"] += 1
        elif abs(sx - ex) < 0.01:          # 수직벽 → x 면
            if abs(sx - minx) < tol:
                score["x_min"] += 1
            elif abs(sx - maxx) < tol:
                score["x_max"] += 1
    # 두 면을 함께 보는 사분면 점수
    quad = {
        "a": score["x_min"] + score["y_min"],
        "b": score["x_max"] + score["y_min"],
        "c": score["x_max"] + score["y_max"],
        "d": score["x_min"] + score["y_max"],
    }
    best = max(quad, key=lambda k: quad[k])
    return {"a": "sw", "b": "se", "c": "ne", "d": "nw"}[best]


def setup_camera(view="sw", lens=35.0, elev_deg=12.0):
    lo, hi = scene_bbox()
    cx, cy = (lo[0] + hi[0]) / 2, (lo[1] + hi[1]) / 2
    cz = (lo[2] + hi[2]) / 2
    topz = hi[2]
    radius = 0.5 * math.sqrt((hi[0] - lo[0]) ** 2 + (hi[1] - lo[1]) ** 2 + (hi[2] - lo[2]) ** 2)

    scene = bpy.context.scene
    fov_h = 2 * math.atan(18.0 / lens)
    aspect = scene.render.resolution_x / max(scene.render.resolution_y, 1)
    fov_v = 2 * math.atan(math.tan(fov_h / 2) / max(aspect, 1e-6))

    # sw = -x/-y 쪽에서 본다 (설계 좌표 기준)
    # sw = 카메라가 -x/-y 쪽에 선다(=x_min·y_min 면을 본다). dirv 부호로 검산할 것.
    az_r = math.radians(VIEW_AZ.get(view, 315))
    el_r = math.radians(elev_deg)
    dirv = (math.cos(el_r) * math.sin(az_r), -math.cos(el_r) * math.cos(az_r), math.sin(el_r))

    tgt = (cx, cy, cz + (topz - cz) * 0.1)
    fwd = (-dirv[0], -dirv[1], -dirv[2])

    def cross(a, b):
        return (a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0])

    def norm(a):
        m = math.sqrt(sum(c * c for c in a)) or 1.0
        return (a[0] / m, a[1] / m, a[2] / m)

    def dot(a, b):
        return sum(x * y for x, y in zip(a, b))

    right = norm(cross(fwd, (0, 0, 1)))
    up = norm(cross(right, fwd))

    # 바운딩박스 8꼭짓점이 모두 화면에 들어오는 최소 거리 (여백 8%)
    margin = 0.86
    dist = radius
    for gx in (lo[0], hi[0]):
        for gy in (lo[1], hi[1]):
            for gz in (lo[2], hi[2]):
                v = (gx - tgt[0], gy - tgt[1], gz - tgt[2])
                a, b, c = dot(v, dirv), dot(v, right), dot(v, up)
                dist = max(dist,
                           a + abs(b) * margin / math.tan(fov_h / 2),
                           a + abs(c) * margin / math.tan(fov_v / 2))

    px = tgt[0] + dist * dirv[0]
    py = tgt[1] + dist * dirv[1]
    pz = tgt[2] + dist * dirv[2]

    bpy.ops.object.camera_add(location=(px, py, pz))
    cam = bpy.context.active_object
    cam.data.lens = lens
    cam.data.clip_start = 0.05
    cam.data.clip_end = 100000.0   # 기본 100m 는 지면을 직선으로 잘라 '잔디 판'을 만든다

    target = bpy.data.objects.new("cam_target", None)
    bpy.context.collection.objects.link(target)
    target.location = (cx, cy, cz + (topz - cz) * 0.1)
    c = cam.constraints.new(type="TRACK_TO")
    c.target = target
    c.track_axis = "TRACK_NEGATIVE_Z"
    c.up_axis = "UP_Y"

    bpy.context.scene.camera = cam
    return cam


def setup_render(out_path, samples, res):
    scene = bpy.context.scene
    scene.render.engine = "CYCLES"
    try:
        scene.cycles.device = "GPU"
        prefs = bpy.context.preferences.addons["cycles"].preferences
        prefs.compute_device_type = "METAL"
        prefs.get_devices()
        for dev in prefs.devices:
            dev.use = True
    except Exception:
        scene.cycles.device = "CPU"

    scene.cycles.samples = samples
    scene.cycles.use_denoising = True
    scene.cycles.max_bounces = 8
    scene.render.resolution_x, scene.render.resolution_y = res
    scene.render.resolution_percentage = 100
    scene.render.film_transparent = False
    scene.render.image_settings.file_format = "PNG"
    scene.render.filepath = out_path
    try:
        scene.view_settings.view_transform = "AgX"
    except Exception:
        try:
            scene.view_settings.view_transform = "Filmic"
        except Exception:
            pass
    for look in ("AgX - Medium High Contrast", "Medium High Contrast", "None"):
        try:
            scene.view_settings.look = look
            break
        except Exception:
            continue
    scene.view_settings.exposure = -0.9   # 밝게 두면 AgX 가 원경 지면을 탈색시켜 '잘린 잔디 판'처럼 보인다


def main():
    cfg = parse_args()
    with open(cfg["design"], "r", encoding="utf-8") as f:
        design = json.load(f)

    bpy.ops.wm.read_factory_settings(use_empty=True)

    floors = design.get("floors", []) or []
    minx, maxx, miny, maxy = 1e9, -1e9, 1e9, -1e9
    for fl in floors:
        for r in fl.get("rooms", []) or []:
            a, b, c, d = room_bbox(r)
            minx, maxx, miny, maxy = min(minx, a), max(maxx, b), min(miny, c), max(maxy, d)
    if minx > 1e8:
        raise SystemExit("설계에 방이 없습니다 — 렌더할 형상이 없음")
    cx0, cy0 = (minx + maxx) / 2, (miny + maxy) / 2

    view = cfg["view"]
    if view == "auto":
        view = pick_view(design)
        print("[render_blender] 개구부가 가장 많이 보이는 방향 선택: %s" % view)
    # 태양은 카메라 방위에서 55도 비껴 세운다 — 정면 역광·정면광 둘 다 형태를 죽인다
    setup_world(sun_rot_deg=(VIEW_AZ.get(view, 315) + 55) % 360)
    setup_ground()
    for fl in floors:
        build_floor(design, fl, cx0, cy0)
    build_roof(design, cx0, cy0)

    setup_render(cfg["out"], cfg["samples"], cfg["res"])   # 화각 계산이 해상도를 읽으므로 카메라보다 먼저
    setup_camera(view)

    if cfg["gltf"]:
        os.makedirs(os.path.dirname(os.path.abspath(cfg["gltf"])), exist_ok=True)
        bpy.ops.export_scene.gltf(filepath=cfg["gltf"], export_format="GLB")
        print("[render_blender] glTF: %s" % cfg["gltf"])

    os.makedirs(os.path.dirname(os.path.abspath(cfg["out"])), exist_ok=True)
    bpy.ops.render.render(write_still=True)
    print("[render_blender] PNG: %s" % cfg["out"])


if __name__ == "__main__":
    main()
