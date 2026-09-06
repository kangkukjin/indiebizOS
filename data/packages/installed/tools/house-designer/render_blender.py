"""House Designer — Blender/Cycles 오프라인 렌더러 + glTF 내보내기

설계 JSON(design_*.json)을 Blender 씬으로 조립해 Cycles 로 렌더한다.
Three.js 뷰어(templates/3d_viewer.html)와 같은 스키마를 읽되, 목적이 다르다:
뷰어 = 형상 확인(실시간), 이 스크립트 = 완성 컷(오프라인 PBR).

사용법:
  blender --background --python render_blender.py -- <design.json> <out.png>
          [--samples 128] [--res 1600 900] [--view sw|se|nw|ne] [--gltf out.glb]
"""
import bpy
import importlib.util
import json
import math
import os
import random
import sys

# Poly Haven CC0 자산(텍스처·HDRI·나무) — 없으면 절차적 재질로 정직하게 퇴화한다
_PKG_DIR = os.path.dirname(os.path.abspath(__file__))
try:
    _ra_spec = importlib.util.spec_from_file_location(
        "render_assets", os.path.join(_PKG_DIR, "render_assets.py"))
    render_assets = importlib.util.module_from_spec(_ra_spec)
    _ra_spec.loader.exec_module(render_assets)
except Exception as _e:                                   # pragma: no cover
    print("[render_blender] 경고: render_assets 로드 실패(%s) — 절차적 재질로 진행" % _e)
    render_assets = None

try:
    _rg_spec = importlib.util.spec_from_file_location(
        "render_gate", os.path.join(_PKG_DIR, "render_gate.py"))
    render_gate = importlib.util.module_from_spec(_rg_spec)
    _rg_spec.loader.exec_module(render_gate)
except Exception as _e:                                   # pragma: no cover
    print("[render_blender] 경고: render_gate 로드 실패(%s) — 예산 관문 없이 진행" % _e)
    render_gate = None

ASSET_CREDITS = []
USING_HDRI = False        # HDRI 조명이면 노출 기준이 달라진다(setup_render 가 읽는다)

# ---------------------------------------------------------------- 인자 파싱

def parse_args():
    argv = sys.argv
    argv = argv[argv.index("--") + 1:] if "--" in argv else []
    if len(argv) < 2:
        raise SystemExit("usage: ... -- <design.json> <out.png> [--samples N] [--res W H] [--view sw] [--gltf path]")
    cfg = {
        "design": argv[0], "out": argv[1],
        "samples": 128, "res": (1600, 900), "view": "auto", "gltf": None,
        # 잔디 스캐터는 기본 끔 — 이 자산(Poly Haven grass_medium)은 25m 거리에서
        # 풀포기로 분해되지 않으면서 지면만 탁하게 만들고 건물 그림자를 덮었다
        # (2026-09-06 실측). 필요하면 --grass 7 처럼 명시해서 켠다.
        "hdri": None, "trees": 7, "grass": 0.0, "planting": True,
        # 조명 표준(2026-09-06): HDRI 위에 태양 램프를 항상 정렬해 세운다(아크비즈 관행). HDRI 텍셀의 태양은
        # 4k 등장방형에서 몇 픽셀이라 클램프·디노이즈에 깎여 그림자가 흐려진다 — 실측(ep2910)에서 태양/평균
        # 15만 배 HDRI 로도 접지 그림자가 '사실상 없음'으로 판독됐다. always|auto(약할 때만)|off
        "sun": "always",
        "force": False,     # 렌더 예산·변화 없음 관문 우회(명시)
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
        elif a == "--hdri":
            cfg["hdri"] = argv[i + 1]; i += 2
        elif a == "--trees":
            cfg["trees"] = int(argv[i + 1]); i += 2
        elif a == "--no-trees":
            cfg["trees"] = 0; i += 1
        elif a == "--grass":
            cfg["grass"] = float(argv[i + 1]); i += 2      # 클럼프/m^2
        elif a == "--no-grass":
            cfg["grass"] = 0.0; i += 1
        elif a == "--no-planting":
            cfg["planting"] = False; i += 1
        elif a == "--sun":
            cfg["sun"] = argv[i + 1]; i += 2                # always|auto|off
        elif a == "--force":
            cfg["force"] = True; i += 1
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


def pbr_material(name, asset_id, fallback_hex, roughness=0.7, bump=0.2,
                 scale_mult=1.0, res="2k", tint=None, disp_scale=0.03):
    """Poly Haven PBR 텍스처 세트로 재질을 만든다 (실패 시 절차적 재질로 퇴화).

    UV 없이 쓰려고 박스 투영(projection='BOX')을 쓴다 — 상자·다각형 어디에나 붙는다.
    텍스처 크기는 실측 치수(size_m)라 미터 단위로 정확히 반복시킬 수 있다.
    """
    cache_key = ("ph", asset_id, res, round(scale_mult, 3), tint, round(disp_scale, 4))
    if cache_key in _MAT_CACHE:
        return _MAT_CACHE[cache_key]

    tex = render_assets.fetch_texture(asset_id, res=res) if render_assets else None
    if not tex:
        print("[render_blender] 경고: 자산 %s 를 못 받아 절차적 재질로 대체" % asset_id)
        return make_material(name, fallback_hex, roughness=roughness, bump=bump)

    if asset_id not in ASSET_CREDITS:
        ASSET_CREDITS.append(asset_id)

    mat = bpy.data.materials.new(name="%s_%s" % (name, asset_id))
    mat.use_nodes = True
    nt = mat.node_tree
    bsdf = nt.nodes.get("Principled BSDF")

    coord = nt.nodes.new("ShaderNodeTexCoord")
    mapping = nt.nodes.new("ShaderNodeMapping")
    sx = 1.0 / max(tex["size_m"][0] * scale_mult, 0.05)
    sy = 1.0 / max(tex["size_m"][1] * scale_mult, 0.05)
    mapping.inputs["Scale"].default_value = (sx, sy, sx)
    nt.links.new(coord.outputs["Object"], mapping.inputs["Vector"])

    def image_node(path, non_color):
        img = nt.nodes.new("ShaderNodeTexImage")
        img.image = bpy.data.images.load(path, check_existing=True)
        img.projection = "BOX"
        img.projection_blend = 0.25
        img.extension = "REPEAT"
        if non_color:
            img.image.colorspace_settings.name = "Non-Color"
        nt.links.new(mapping.outputs["Vector"], img.inputs["Vector"])
        return img

    diff = image_node(tex["diffuse"], False)

    # 설계가 지정한 색은 텍스처를 *덮지 않고* 곱해서 입힌다
    # (색이 있다고 절차적 단색으로 갈아타면 재질이 통째로 사라진다 — 2026-09-06 실측)
    color_src = diff.outputs["Color"]
    if tint:
        tmix = nt.nodes.new("ShaderNodeMix")
        tmix.data_type = "RGBA"
        tmix.blend_type = "MULTIPLY"
        tmix.inputs["Factor"].default_value = 0.85
        nt.links.new(diff.outputs["Color"], tmix.inputs[6])
        tmix.inputs[7].default_value = hex_rgba(tint)
        color_src = tmix.outputs[2]

    if tex.get("ao"):
        ao = image_node(tex["ao"], True)
        mix = nt.nodes.new("ShaderNodeMix")
        mix.data_type = "RGBA"
        mix.blend_type = "MULTIPLY"
        mix.inputs["Factor"].default_value = 0.6
        nt.links.new(color_src, mix.inputs[6])               # A(Color)
        nt.links.new(ao.outputs["Color"], mix.inputs[7])     # B(Color)
        nt.links.new(mix.outputs[2], bsdf.inputs["Base Color"])
    else:
        nt.links.new(color_src, bsdf.inputs["Base Color"])

    if tex.get("roughness"):
        rough = image_node(tex["roughness"], True)
        nt.links.new(rough.outputs["Color"], bsdf.inputs["Roughness"])
    else:
        bsdf.inputs["Roughness"].default_value = roughness

    if tex.get("normal"):
        nor = image_node(tex["normal"], True)
        nmap = nt.nodes.new("ShaderNodeNormalMap")
        nmap.inputs["Strength"].default_value = 1.0
        nt.links.new(nor.outputs["Color"], nmap.inputs["Color"])
        nt.links.new(nmap.outputs["Normal"], bsdf.inputs["Normal"])

    # 변위 맵 → Displacement(BUMP) : 노멀맵만으로는 안 생기는 '요철 음영'이 여기서 온다
    if tex.get("displacement"):
        disp_img = image_node(tex["displacement"], True)
        disp = nt.nodes.new("ShaderNodeDisplacement")
        disp.inputs["Scale"].default_value = disp_scale
        disp.inputs["Midlevel"].default_value = 0.5
        out_node = nt.nodes.get("Material Output")
        nt.links.new(disp_img.outputs["Color"], disp.inputs["Height"])
        if out_node:
            nt.links.new(disp.outputs["Displacement"], out_node.inputs["Displacement"])
            mat.displacement_method = "BUMP"

    _MAT_CACHE[cache_key] = mat
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

    mat_slab = pbr_material("slab", render_assets.DEFAULTS.get("apron", "") if render_assets else "",
                            "#CFC7B8", roughness=0.85, bump=0.15)
    mat_ext = pbr_material("wall_ext", render_assets.DEFAULTS["wall"] if render_assets else "",
                           fac_color, roughness=0.72, bump=0.25, tint=fac_color, scale_mult=1.6)
    mat_int = make_material("wall_int", "#EDE9E1", roughness=0.8, bump=0.1)
    # 유리 파라미터 A/B/C 실측(2026-09-06, 창 영역 픽셀 평균):
    #   투과 1.0·거의 무색 = 76/87/68 (실내 암부가 그대로 비쳐 더 검어짐 — 내가 만든 퇴보)
    #   투과 0.9·연한 하늘색 = 106/121/112  ← 되돌린 값
    #   투과 0.25·짙은 색 = 133/152/150 (밝아지지만 판독기는 '칠한 판'으로 읽음)
    # 셋 다 '유리'로는 안 읽힌다 — 원인은 셰이더가 아니라 비칠 것이 없다는 것
    # (매끈한 하늘 그라데이션만 반사되어 단색 면이 된다). 반사할 주변과 실내
    # 디테일이 생기기 전까지는 이 값이 최선이다.
    mat_glass = make_material("glass", "#CFE6F5", roughness=0.05, metallic=0.0, transmission=0.9)
    mat_door = make_material("door", "#8A6A4A", roughness=0.45, bump=0.1)

    # 바닥 슬라브
    if rooms:
        xs0, xs1, ys0, ys1 = 1e9, -1e9, 1e9, -1e9
        for r in rooms:
            a, b, c, d = room_bbox(r)
            xs0, xs1, ys0, ys1 = min(xs0, a), max(xs1, b), min(ys0, c), max(ys1, d)
        # 1층 슬래브는 기초처럼 땅에 묻는다 — 잔디 위에 얹힌 얇은 판으로 보이지 않게
        depth = 0.9 if abs(elev) < 0.01 else 0.22
        add_box("%s_slab" % fid, (xs1 - xs0) + 0.5, (ys1 - ys0) + 0.5, depth,
                ((xs0 + xs1) / 2 - cx0, (ys0 + ys1) / 2 - cy0, elev - depth / 2 + 0.06), mat_slab)

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

    # 실내 방향 — 유리 뒤에 어두운 면을 두어야 창이 '회색 스티커'가 아니라 창으로 읽힌다
    if rooms:
        _bb = [room_bbox(r) for r in rooms]
        fcx = sum((b[0] + b[1]) / 2 for b in _bb) / len(_bb) - cx0
        fcy = sum((b[2] + b[3]) / 2 for b in _bb) / len(_bb) - cy0
    else:
        fcx = fcy = 0.0
    mat_dark = make_material("interior_dark", "#1C1F24", roughness=0.9)

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
            mat = pbr_material("wall_tinted",
                               render_assets.DEFAULTS["wall"] if render_assets else "",
                               wall["color"], roughness=0.72, bump=0.25,
                               tint=wall["color"], scale_mult=1.6)

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
                nx, ny = -math.sin(angle), math.cos(angle)          # 벽 법선
                if (fcx - px) * nx + (fcy - py) * ny < 0:
                    nx, ny = -nx, -ny                              # 실내 쪽으로 뒤집는다
                add_box("%s_int%d" % (name, oi), (e - s) + 0.3, 0.06, oh + 0.3,
                        (px + nx * 0.5, py + ny * 0.5, elev + sill + oh / 2),
                        mat_dark, rot_z=angle, bevel=False)
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
    mat_roof = pbr_material("roof", render_assets.DEFAULTS["roof"] if render_assets else "",
                            color, roughness=0.78, bump=0.3)

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


def _import_gltf(path):
    """glTF 를 불러와 새로 생긴 최상위 오브젝트들을 돌려준다."""
    before = set(bpy.context.scene.objects)
    try:
        bpy.ops.import_scene.gltf(filepath=path)
    except Exception as e:
        print("[render_blender] 경고: 모델 임포트 실패 %s — %s" % (os.path.basename(path), e))
        return []
    return [o for o in bpy.context.scene.objects if o not in before]


def _world_height(objs):
    """오브젝트 묶음의 월드 좌표 높이(m). 부모/자식 스케일을 모두 반영한다."""
    import mathutils
    lo, hi = 1e9, -1e9
    for o in objs:
        if o.type != "MESH":
            continue
        for c in o.bound_box:
            z = (o.matrix_world @ mathutils.Vector(c)).z
            lo, hi = min(lo, z), max(hi, z)
    return max(hi - lo, 1e-3) if hi > -1e8 else 1.0


_SRC_CACHE = {}


def _asset_source(asset_id):
    """자산 하나를 인스턴싱 소스 컬렉션으로 만든다 -> (컬렉션, 원본높이m).

    컬렉션을 씬에서 떼어 두므로 원본 자체는 렌더되지 않고, 배치는 빈
    오브젝트(컬렉션 인스턴스)로만 한다 — 복제본마다 메시를 베끼지 않아
    수천 개를 심어도 메모리가 늘지 않는다(아크비즈 표준).
    """
    if asset_id in _SRC_CACHE:
        return _SRC_CACHE[asset_id]
    path = render_assets.fetch_model(asset_id) if render_assets else None
    objs = _import_gltf(path) if path else []
    if not objs:
        _SRC_CACHE[asset_id] = (None, 1.0)
        return None, 1.0

    bpy.context.view_layer.update()
    h = _world_height(objs)
    coll = bpy.data.collections.new("src_" + asset_id)
    for o in objs:
        for c in list(o.users_collection):
            c.objects.unlink(o)
        coll.objects.link(o)
    if asset_id not in ASSET_CREDITS:
        ASSET_CREDITS.append(asset_id)
    _SRC_CACHE[asset_id] = (coll, h)
    return coll, h


def _place(coll, src_h, x, y, target_h, rot_z, name):
    """컬렉션 인스턴스 하나를 심는다. 이름은 구도 계산에서 제외되는 tree_ 규약."""
    e = bpy.data.objects.new(name, None)
    e.instance_type = "COLLECTION"
    e.instance_collection = coll
    e.empty_display_size = 0.2
    e.location = (x, y, 0.0)
    e.rotation_euler = (0.0, 0.0, rot_z)
    s = target_h / src_h
    e.scale = (s, s, s)
    bpy.context.collection.objects.link(e)


def add_entourage(view="sw", count=7, seed=7):
    """주변 나무 — Poly Haven CC0 모델을 받아 배치한다(직접 만들지 않는다).

    카메라가 보는 방향(정면 사분면)은 비워 두어 건물을 가리지 않게 한다.
    """
    if not render_assets:
        return 0
    lo, hi = scene_bbox()
    cx, cy = (lo[0] + hi[0]) / 2, (lo[1] + hi[1]) / 2
    radius = 0.5 * math.hypot(hi[0] - lo[0], hi[1] - lo[1])

    sources = [s for s in (_asset_source(a)
                           for a in render_assets.DEFAULTS.get("trees", [])) if s[0]]
    if not sources:
        print("[render_blender] 경고: 나무 모델을 못 받아 엔투라지 없이 렌더")
        return 0

    rnd = random.Random(seed)
    cam_az = VIEW_AZ.get(view, 315)
    placed = 0
    for i in range(count):
        for _ in range(12):                          # 정면 사분면을 피해 각도 뽑기
            az = rnd.uniform(0, 360)
            if abs(((az - cam_az + 180) % 360) - 180) > 95:
                break        # 건물 뒤쪽 반구에만 — 옆에 세우면 프레임 가장자리에서 잘린다
        dist = radius * rnd.uniform(2.6, 4.6)   # 가까우면 수관이 프레임 밖으로 잘린다
        coll, src_h = sources[i % len(sources)]
        _place(coll, src_h,
               cx + dist * math.sin(math.radians(az)),
               cy - dist * math.cos(math.radians(az)),
               rnd.uniform(7.0, 11.0), rnd.uniform(0, 6.28), "tree_%d" % i)
        placed += 1
    print("[render_blender] 엔투라지: 나무 %d 그루 (Poly Haven CC0)" % placed)
    return placed


def add_planting(bbox, seed=13, shrubs=10, rocks=4):
    """기초식재 — 건물 외곽선을 따라 관목·바위를 붙인다.

    맨 잔디에 건물만 서 있으면 축소 모형으로 읽힌다. 기단부에 스케일 단서를 준다.
    """
    if not render_assets:
        return 0
    (x0, y0, _), (x1, y1, _) = bbox
    rnd = random.Random(seed)
    placed = 0

    def perimeter_point(off_lo, off_hi):
        off = rnd.uniform(off_lo, off_hi)
        side = rnd.choice("NSEW")
        if side in "NS":
            return rnd.uniform(x0 - off, x1 + off), (y1 + off if side == "N" else y0 - off)
        return (x1 + off if side == "E" else x0 - off), rnd.uniform(y0 - off, y1 + off)

    for kind, n, h_lo, h_hi, off_lo, off_hi in (
            ("shrubs", shrubs, 0.8, 1.6, 0.6, 1.8),
            ("rocks", rocks, 0.4, 0.9, 2.0, 4.5)):
        srcs = [s for s in (_asset_source(a)
                            for a in render_assets.DEFAULTS.get(kind, [])) if s[0]]
        if not srcs:
            print("[render_blender] 경고: %s 모델 없음 — 건너뜀" % kind)
            continue
        for i in range(n):
            coll, src_h = srcs[i % len(srcs)]
            px, py = perimeter_point(off_lo, off_hi)
            _place(coll, src_h, px, py, rnd.uniform(h_lo, h_hi),
                   rnd.uniform(0, 6.28), "tree_%s_%d" % (kind, i))
            placed += 1
    print("[render_blender] 기초식재: 관목·바위 %d 점" % placed)
    return placed


def add_groundcover(bbox, seed=17, density=7.0, cap=20000, extent=2.2):
    """잔디 지오메트리 — 평면 텍스처만으로는 원경에서 늘어져 보인다.

    파티클 헤어로도 해 봤으나 이 조합(Blender 5.2 · glTF 소스 · 컬렉션 인스턴싱)에서
    입자는 45,000개가 생기는데 렌더에는 한 포기도 나오지 않았다(2026-09-06 실측:
    지면 픽셀 평균 89.3 → 87.8). 나무·관목에서 이미 도는 컬렉션 인스턴스 경로로
    되돌린다 — 검증된 길이 영리한 길보다 낫다.
    """
    if not render_assets:
        return 0
    srcs = [s for s in (_asset_source(a)
                        for a in render_assets.DEFAULTS.get("grass", [])) if s[0]]
    if not srcs:
        print("[render_blender] 경고: 잔디 모델 없음 — 지면 텍스처로만 진행")
        return 0

    (x0, y0, _), (x1, y1, _) = bbox
    cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
    half = max(x1 - x0, y1 - y0) * extent / 2 + 8.0
    area = max((half * 2) ** 2 - (x1 - x0) * (y1 - y0), 1.0)
    want = int(min(cap, max(400, area * density)))

    rnd = random.Random(seed)
    placed = 0
    for i in range(want * 2):                     # 발자국에 걸린 표본은 버리므로 여유
        if placed >= want:
            break
        px = cx + rnd.uniform(-half, half)
        py = cy + rnd.uniform(-half, half)
        if x0 - 0.5 <= px <= x1 + 0.5 and y0 - 0.5 <= py <= y1 + 0.5:
            continue                              # 건물 발자국 안에는 심지 않는다
        coll, src_h = srcs[rnd.randrange(len(srcs))]
        _place(coll, src_h, px, py, rnd.uniform(0.16, 0.30),
               rnd.uniform(0, 6.28), "tree_grass_%d" % i)
        placed += 1
    print("[render_blender] 잔디: 클럼프 %d 포기 (반경 %.0fm, %.1f 포기/m^2)"
          % (placed, half, placed / area))
    return placed


def _hdri_sun(asset_id):
    """HDRI 안의 태양을 실측한다 → (방향벡터, 태양/평균 휘도비).

    분석은 1k 판으로 한다(4k 는 800만 화소라 느리고 방향 정밀도는 같다).
    등장방형(equirectangular) 매핑: u→방위, v→고도.
    """
    import mathutils
    path = render_assets.fetch_hdri(asset_id, res="1k") if render_assets else None
    if not path:
        return None, 0.0
    img = bpy.data.images.load(path, check_existing=True)
    w, h = img.size
    if not w or not h:
        return None, 0.0
    buf = [0.0] * (w * h * 4)
    img.pixels.foreach_get(buf)

    best, best_i, total = -1.0, 0, 0.0
    for i in range(0, len(buf), 4):
        lum = 0.2126 * buf[i] + 0.7152 * buf[i + 1] + 0.0722 * buf[i + 2]
        total += lum
        if lum > best:
            best, best_i = lum, i
    mean = total / (w * h)
    p = best_i // 4
    u, v = ((p % w) + 0.5) / w, ((p // w) + 0.5) / h
    # ★Cycles 의 등장방형 조회는 u = -atan2(y, x)/2pi + 0.5 — 방위 부호가 뒤집혀 있다.
    #   부호를 빠뜨리면 하늘을 정반대로 돌려 태양이 카메라 뒤로 가고 그림자가
    #   통째로 건물 뒤에 숨는다(2026-09-06 실측: +36.4도 방향은 캄캄, -36.4도에서 태양 발견).
    phi, theta = -(u - 0.5) * 2 * math.pi, (v - 0.5) * math.pi
    d = mathutils.Vector((math.cos(theta) * math.cos(phi),
                          math.cos(theta) * math.sin(phi),
                          math.sin(theta)))
    return d, best / max(mean, 1e-6)


# 이 비 아래면 태양이 구름에 가려 그림자가 서지 않는다(실측: 맑은 하늘 9만~19만,
# 부분운 kloppenheim_06 은 33 — 2026-09-06 hdri_sun_probe).
SUN_RATIO_MIN = 500.0


SUN_MODE = "always"       # parse_args 가 채운다: always(표준)|auto(약할 때만)|off


def _guard_hdri_sun(hdri_id, hdri_rot_deg):
    """HDRI 태양 방향에 SUN 램프를 세운다 — 기본 always(아크비즈 표준: HDRI 는 환경광, 그림자는 태양 램프).

    auto 는 옛 규칙(HDRI 태양이 약할 때만 보정). ep2910 실측: 태양/평균 15만 배 HDRI(autumn_field_puresky)로도
    렌더에서는 접지 그림자가 '사실상 없음' — 텍셀 태양은 클램프·디노이즈·AgX 에 깎인다. 램프는 깎이지 않는다."""
    import mathutils
    if SUN_MODE == "off":
        print("[render_blender] 태양 램프 off (--sun off)")
        return None
    d, ratio = _hdri_sun(hdri_id)
    if d is None:
        print("[render_blender] 경고: HDRI 태양 실측 실패 — 보정 없이 진행")
        return None
    if SUN_MODE == "auto" and ratio >= SUN_RATIO_MIN:
        print("[render_blender] HDRI 태양 실측: 평균 대비 %.0f배 — 그림자 충분(auto)" % ratio)
        return None

    # 매핑 노드가 텍스처 좌표를 +rot 만큼 돌리므로, 텍셀 방향을 -rot 로 되돌려야 월드 방향
    d.rotate(mathutils.Euler((0.0, 0.0, -math.radians(hdri_rot_deg))))
    if d.z < 0.08:
        d.z = 0.35                      # 지평선 아래 태양은 그림자를 못 만든다
        d.normalize()
    bpy.ops.object.light_add(type="SUN", location=(0, 0, 40))
    sun = bpy.context.active_object
    sun.data.energy = 3.2
    sun.data.color = (1.0, 0.95, 0.87)
    sun.data.angle = math.radians(1.0)
    sun.rotation_euler = (-d).to_track_quat("-Z", "Y").to_euler()
    print("[render_blender] HDRI 태양(평균 대비 %.0f배) 방향에 SUN 램프 정렬 — 고도 %.0f도, 모드 %s"
          % (ratio, math.degrees(math.asin(d.z)), SUN_MODE))
    return sun


def orient_hdri_for_view(hdri_id, view, off_deg=100.0):
    """태양이 카메라 축에서 off_deg 만큼 비껴 서도록 하늘을 돌릴 각도(도)를 푼다.

    태양을 카메라 뒤에 두면 그림자가 통째로 건물 뒤로 숨어 화면에 안 나온다
    (실측 2026-09-06: 그림자 0). 옆으로 비껴야 그림자가 프레임 안으로 눕는다.
    매핑 노드는 조회 벡터를 +rot 만큼 돌리므로 텍스처 방위 = 월드 방위 + rot,
    따라서 rot = 텍스처방위 − 목표월드방위.
    """
    d, ratio = _hdri_sun(hdri_id)
    if d is None:
        return (VIEW_AZ.get(view, 315) + 55) % 360
    tex_az = math.degrees(math.atan2(d.y, d.x))
    # 카메라는 건물에서 VIEW_AZ 방위(나침반식)에 선다 — setup_camera 와 같은 식
    cam_az = VIEW_AZ.get(view, 315)
    cam_math_az = math.degrees(math.atan2(-math.cos(math.radians(cam_az)),
                                          math.sin(math.radians(cam_az))))
    rot = (tex_az - (cam_math_az + off_deg)) % 360
    print("[render_blender] 하늘 정위: 태양 고도 %.0f도 · 카메라에서 %.0f도 비껴 세움 "
          "(HDRI 회전 %.0f도, 태양/평균 %.0f배)"
          % (math.degrees(math.asin(max(min(d.z, 1.0), -1.0))), off_deg, rot, ratio))
    return rot


def setup_world(sun_elev_deg=27.0, sun_rot_deg=200.0, hdri_id=None, hdri_rot_deg=0.0):
    """월드 조명. 1순위=Poly Haven HDRI(실촬 하늘, 아크비즈 표준), 실패 시 절차적 하늘+태양."""
    world = bpy.data.worlds.new("World")
    bpy.context.scene.world = world
    world.use_nodes = True
    nt = world.node_tree
    bg = nt.nodes.get("Background")

    hdri = None
    if render_assets and hdri_id:
        hdri = render_assets.fetch_hdri(hdri_id, res="4k") or render_assets.fetch_hdri(hdri_id)
    if hdri:
        env = nt.nodes.new("ShaderNodeTexEnvironment")
        env.image = bpy.data.images.load(hdri, check_existing=True)
        coord = nt.nodes.new("ShaderNodeTexCoord")
        mapping = nt.nodes.new("ShaderNodeMapping")
        mapping.inputs["Rotation"].default_value = (0, 0, math.radians(hdri_rot_deg))
        nt.links.new(coord.outputs["Generated"], mapping.inputs["Vector"])
        nt.links.new(mapping.outputs["Vector"], env.inputs["Vector"])
        nt.links.new(env.outputs["Color"], bg.inputs[0])
        bg.inputs[1].default_value = 1.0
        global USING_HDRI
        USING_HDRI = True
        if hdri_id not in ASSET_CREDITS:
            ASSET_CREDITS.append(hdri_id)
        print("[render_blender] HDRI 조명: %s" % os.path.basename(hdri))
        return _guard_hdri_sun(hdri_id, hdri_rot_deg)

    print("[render_blender] 경고: HDRI 를 못 받아 절차적 하늘+태양으로 진행")
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


def _fade_to_horizon(mat, start=90.0, end=450.0):
    """먼 지면을 서서히 투명하게 만들어 하늘과 만나는 하드 에지를 지운다.

    유한한 지면 평면은 하늘과 칼로 자른 듯한 직선 경계를 만든다(판독기 지적,
    2026-09-06). 카메라 거리에 따라 Transparent 로 섞으면 그 자리에 배경
    HDRI 가 그대로 드러나 지평선이 녹는다.
    """
    nt = mat.node_tree
    out = next((n for n in nt.nodes if n.type == "OUTPUT_MATERIAL"), None)
    if not out or not out.inputs["Surface"].links:
        print("[render_blender] 경고: 지면 재질에 출력이 없어 지평선 페이드 생략")
        return
    src = out.inputs["Surface"].links[0].from_socket
    cam = nt.nodes.new("ShaderNodeCameraData")
    rng = nt.nodes.new("ShaderNodeMapRange")
    rng.clamp = True
    rng.inputs["From Min"].default_value = start
    rng.inputs["From Max"].default_value = end
    nt.links.new(cam.outputs["View Distance"], rng.inputs["Value"])
    tr = nt.nodes.new("ShaderNodeBsdfTransparent")
    mix = nt.nodes.new("ShaderNodeMixShader")
    nt.links.new(rng.outputs["Result"], mix.inputs[0])
    nt.links.new(src, mix.inputs[1])
    nt.links.new(tr.outputs["BSDF"], mix.inputs[2])
    nt.links.new(mix.outputs["Shader"], out.inputs["Surface"])


def setup_ground():
    bpy.ops.mesh.primitive_plane_add(size=20000, location=(0, 0, 0))
    g = bpy.context.active_object
    g.name = "ground"
    # 잔디는 실촬 PBR 세트(2m 타일)를 미터 단위로 반복시킨다
    mat = pbr_material("ground", render_assets.DEFAULTS["ground"] if render_assets else "",
                       "#5E6E42", roughness=0.95, bump=0.0, scale_mult=1.5,
                       tint="#8FBF63")         # 항공 잔디가 마른 흙으로 읽혀 초록으로 그레이딩
    g.data.materials.append(mat)
    _fade_to_horizon(mat)


def scene_bbox(exclude=("ground", "lawn")):
    """지면을 끌 전체 메시의 월드 바운딩박스 — 구도 계산의 진실 소스."""
    lo = [1e9, 1e9, 1e9]
    hi = [-1e9, -1e9, -1e9]
    for obj in bpy.context.scene.objects:
        if obj.type != "MESH" or obj.name in exclude:
            continue
        if obj.name.startswith("tree_") or obj.hide_render:
            continue        # 엔투라지·숨긴 원본은 구도의 기준이 아니다 (건물이 작아진다)
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


def setup_camera(view="sw", lens=35.0, elev_deg=9.0):
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
    # 절차적 하늘은 밝게 두면 원경이 탈색되고, HDRI 는 자체 노출이 있어 덜 깎아야 한다
    scene.view_settings.exposure = -0.15 if USING_HDRI else -0.9


def _thumb_loader(path, size):
    """render_gate 용 픽셀 읽기 — bpy 로 회색 썸네일."""
    try:
        img = bpy.data.images.load(path, check_existing=False)
        img.scale(size[0], size[1])
        buf = [0.0] * (size[0] * size[1] * 4)
        img.pixels.foreach_get(buf)
        gray = [0.2126 * buf[i] + 0.7152 * buf[i + 1] + 0.0722 * buf[i + 2] for i in range(0, len(buf), 4)]
        bpy.data.images.remove(img)
        return gray
    except Exception as e:
        print("[render_gate] 썸네일 실패(%s): %s" % (path, e))
        return None


def _gate_dir():
    base = render_assets.CACHE if (render_assets and hasattr(render_assets, "CACHE")) else None
    return os.path.dirname(str(base)) if base else os.path.join(_PKG_DIR, "_render")


def main():
    global SUN_MODE
    cfg = parse_args()
    SUN_MODE = cfg.get("sun") or "always"
    with open(cfg["design"], "r", encoding="utf-8") as f:
        design = json.load(f)
    # 렌더 예산·변화 없음 관문(2026-09-06) — 셀 수 있으면 관문이 실패시킨다
    _ledger = None
    if render_gate:
        _gdir = _gate_dir()
        _ledger = render_gate.load_ledger(_gdir)
        _view_key = cfg["view"] if cfg["view"] != "auto" else pick_view(design)
        _ok, _why = render_gate.check_before(_ledger, os.path.abspath(cfg["design"]), _view_key, force=cfg["force"])
        print("[render_gate] %s" % _why)
        if not _ok:
            raise SystemExit(3)

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
    # 태양은 카메라 방위에서 50도 비껴 세운다 — 정면 역광·정면광 둘 다 형태를 죽이고,
    # 카메라 뒤에 두면 그림자가 건물 뒤로 숨는다
    hdri_id = cfg.get("hdri") or (render_assets.DEFAULTS["hdri"] if render_assets else None)
    setup_world(sun_rot_deg=(VIEW_AZ.get(view, 315) + 55) % 360,
                hdri_id=hdri_id,
                hdri_rot_deg=orient_hdri_for_view(hdri_id, view) if hdri_id else 0.0)
    setup_ground()
    for fl in floors:
        build_floor(design, fl, cx0, cy0)
    build_roof(design, cx0, cy0)

    setup_render(cfg["out"], cfg["samples"], cfg["res"])   # 화각 계산이 해상도를 읽으므로 카메라보다 먼저
    setup_camera(view)                                     # 구도는 건물 기준 (조경 제외)

    bbox = scene_bbox()                 # 조경의 기준선 — 건물만 (지면·잔디밭 제외)
    if cfg.get("trees"):
        add_entourage(view, count=cfg["trees"])
    if cfg.get("planting"):
        add_planting(bbox)
    if cfg.get("grass"):
        add_groundcover(bbox, density=cfg["grass"])

    if cfg["gltf"]:
        os.makedirs(os.path.dirname(os.path.abspath(cfg["gltf"])), exist_ok=True)
        bpy.ops.export_scene.gltf(filepath=cfg["gltf"], export_format="GLB")
        print("[render_blender] glTF: %s" % cfg["gltf"])

    os.makedirs(os.path.dirname(os.path.abspath(cfg["out"])), exist_ok=True)
    bpy.ops.render.render(write_still=True)
    print("[render_blender] PNG: %s" % cfg["out"])
    if render_gate and _ledger is not None:
        _entry = render_gate.record_after(_ledger, os.path.abspath(cfg["design"]), cfg["view"] if cfg["view"] != "auto" else view,
                                          cfg["out"], _thumb_loader)
        render_gate.save_ledger(_gate_dir(), _ledger)
        print(render_gate.note(_entry))
    if ASSET_CREDITS:
        print("[render_blender] 자산 출처: Poly Haven (CC0) — %s" % ", ".join(ASSET_CREDITS))


if __name__ == "__main__":
    main()
