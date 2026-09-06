"""Poly Haven CC0 자산 받아오기 (키 불필요, 상업 사용 허용)

절차적 노이즈로 재질·하늘·나무를 손으로 지어 넣는 것은 재발명이다.
실무 표준은 CC0 라이브러리에서 실측 PBR 세트·HDRI·모델을 받아 쓰는 것(2026-09-06 검증).

캐시: data/render_assets/polyhaven/<type>/<id>/
출처 표기: Poly Haven(polyhaven.com) — CC0. 산출물 보고에 함께 싣는다.
"""
import json
import os
import urllib.request

API = "https://api.polyhaven.com"
_HERE = os.path.dirname(os.path.abspath(__file__))
_BASE = os.path.abspath(os.path.join(_HERE, "..", "..", "..", "..", ".."))   # …/indiebizOS
CACHE = os.path.join(_BASE, "data", "render_assets", "polyhaven")

TIMEOUT = 60


def _log(msg):
    print("[render_assets] %s" % msg)


def _download(url, dest):
    """캐시가 있으면 그대로, 없으면 받아 저장. 실패하면 None(정직한 퇴화)."""
    if os.path.exists(dest) and os.path.getsize(dest) > 0:
        return dest
    os.makedirs(os.path.dirname(dest), exist_ok=True)
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "indiebizOS-house-designer/1.0"})
        with urllib.request.urlopen(req, timeout=TIMEOUT) as r, open(dest + ".part", "wb") as f:
            f.write(r.read())
        os.replace(dest + ".part", dest)
        return dest
    except Exception as e:
        _log("다운로드 실패 %s — %s" % (url, e))
        if os.path.exists(dest + ".part"):
            os.remove(dest + ".part")
        return None


def _api(path):
    try:
        req = urllib.request.Request(API + path, headers={"User-Agent": "indiebizOS-house-designer/1.0"})
        with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
            return json.load(r)
    except Exception as e:
        _log("API 실패 %s — %s" % (path, e))
        return None


def _cached_json(path, key):
    """API 응답도 캐시 — 렌더마다 네트워크를 치지 않는다."""
    meta_path = os.path.join(CACHE, "_api", key + ".json")
    if os.path.exists(meta_path):
        try:
            with open(meta_path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    data = _api(path)
    if data is not None:
        os.makedirs(os.path.dirname(meta_path), exist_ok=True)
        with open(meta_path, "w", encoding="utf-8") as f:
            json.dump(data, f)
    return data


# ---------------------------------------------------------------- 텍스처

# Poly Haven 맵 이름 → 역할
TEX_MAPS = {"Diffuse": "diffuse", "nor_gl": "normal", "Rough": "roughness",
            "AO": "ao", "Displacement": "displacement"}


def fetch_texture(asset_id, res="2k", fmt="jpg"):
    """PBR 텍스처 세트를 받는다.

    반환: {"diffuse": path, "normal": path, "roughness": path, "ao": path,
            "size_m": (가로m, 세로m)}  — 실패하면 None
    size_m 은 실측 치수(mm)에서 온 것이라 텍스처를 미터 단위로 깔 수 있다.
    """
    files = _cached_json("/files/%s" % asset_id, "files_%s" % asset_id)
    if not files:
        return None

    info = _cached_json("/info/%s" % asset_id, "info_%s" % asset_id) or {}
    dims = info.get("dimensions") or [2000, 2000]      # mm
    out = {"size_m": (max(dims[0], 1) / 1000.0, max(dims[1], 1) / 1000.0),
           "asset_id": asset_id, "source": "Poly Haven (CC0)"}

    for ph_name, role in TEX_MAPS.items():
        node = files.get(ph_name)
        if not node:
            continue
        entry = node.get(res) or node.get("2k") or node.get("1k")
        if not entry:
            continue
        f = entry.get(fmt) or entry.get("jpg") or entry.get("png")
        if not f or not f.get("url"):
            continue
        dest = os.path.join(CACHE, "textures", asset_id,
                            os.path.basename(f["url"]))
        got = _download(f["url"], dest)
        if got:
            out[role] = got

    return out if out.get("diffuse") else None


# ---------------------------------------------------------------- HDRI

def fetch_hdri(asset_id, res="2k"):
    """HDRI 파노라마(.hdr) 경로 — 실패하면 None."""
    files = _cached_json("/files/%s" % asset_id, "files_%s" % asset_id)
    if not files or "hdri" not in files:
        return None
    entry = files["hdri"].get(res) or files["hdri"].get("2k") or files["hdri"].get("1k")
    if not entry:
        return None
    f = entry.get("hdr") or entry.get("exr")
    if not f or not f.get("url"):
        return None
    dest = os.path.join(CACHE, "hdris", asset_id, os.path.basename(f["url"]))
    return _download(f["url"], dest)


# ---------------------------------------------------------------- 모델

def fetch_model(asset_id, res="1k"):
    """glTF 모델 + 딸린 텍스처·bin 을 받아 .gltf 경로를 돌려준다."""
    files = _cached_json("/files/%s" % asset_id, "files_%s" % asset_id)
    if not files or "gltf" not in files:
        return None
    entry = (files["gltf"].get(res) or files["gltf"].get("1k") or {}).get("gltf")
    if not entry or not entry.get("url"):
        return None

    root = os.path.join(CACHE, "models", asset_id)
    main = _download(entry["url"], os.path.join(root, os.path.basename(entry["url"])))
    if not main:
        return None

    # include 는 {상대경로: {url, ...}} — gltf 가 참조하는 bin·텍스처
    for rel, meta in (entry.get("include") or {}).items():
        url = meta.get("url") if isinstance(meta, dict) else None
        if url:
            _download(url, os.path.join(root, rel.replace("/", os.sep)))
    return main


# ---------------------------------------------------------------- 기본 자산표

# 건축 외관에 쓰는 기본 세트 (전부 Poly Haven CC0)
DEFAULTS = {
    # 구름이 있으면서 태양이 살아 있는 하늘. 실측(2026-09-06, hdri_sun_probe)에서
    # 태양/평균 휘도비가 150,974배 — 그림자가 또렷하다. 부분운 kloppenheim_06 은
    # 33배(태양이 구름 뒤)라 그림자가 통째로 사라졌다.
    "hdri": "autumn_field_puresky",
    "wall": "concrete_wall_008",              # 외벽 (2.7m 타일 — 결이 커야 25m 거리에서 보인다)
    "apron": "concrete_floor_02",             # 기단·데크 포장
    "roof": "clay_roof_tiles_02",             # 기와
    "ground": "aerial_grass_rock",            # 잔디 지면 — 항공 촬영본(15m 타일)
    "trees": ["island_tree_02", "island_tree_01", "tree_small_02"],
    "grass": ["grass_medium_01", "grass_medium_02"],   # 파티클로 흩뿌릴 풀 지오메트리
    "shrubs": ["shrub_01", "shrub_02", "shrub_04", "wild_rooibos_bush"],
    "rocks": ["rock_07", "rock_09", "namaqualand_boulder_03"],
}


# ---------------------------------------------------------------- 일괄 선적재
#
# 왜 묶음으로 받나: 실측(2026-09-06)에서 텍스처 2k 5맵 세트는 3~20MB, HDRI 4k 는
# 17~28MB 라 수십 종을 받아도 수백 MB 다. 반면 모델은 지오메트리(.bin)가 본체라
# 편차가 100배다 — fir_tree_01 487MB, pine_tree_01 958MB 인데 shrub_02 는 2MB.
# 그래서 텍스처·HDRI 는 넉넉히 통째로, 모델은 크기를 보고 고른다.

PACK = {
    "textures": [
        # 외벽
        "concrete_wall_008", "white_stucco", "beige_wall_001", "brick_wall_001",
        "painted_plaster_wall", "wood_planks", "weathered_planks",
        "box_profile_metal_sheet", "cliff_side",
        # 지붕
        "clay_roof_tiles_02", "grey_roof_tiles", "red_slate_roof_tiles_01",
        "corrugated_iron",
        # 지면·포장
        "aerial_grass_rock", "leafy_grass", "concrete_floor_02", "asphalt_02",
        "bicolour_gravel", "brick_pavement", "pavement_02",
    ],
    "hdris": [
        "kloppenheim_06_puresky",        # 부분운 낮 (기본)
        "kloofendal_43d_clear_puresky",  # 맑음
        "overcast_soil_puresky",         # 흐림 — 그림자 없는 균질 조명
        "qwantani_puresky",              # 늦은 오후
        "belfast_sunset_puresky",        # 일몰
        "autumn_field_puresky",          # 낮 저각
        "table_mountain_1_puresky",      # 정오 강한 대비
        "rogland_clear_night",           # 야경
    ],
    "models": [
        # 나무 — 100MB 이하만 (fir_tree_01 487MB·pine_tree_01 958MB 는 제외)
        "island_tree_01", "island_tree_02", "island_tree_03", "tree_small_02",
        "quiver_tree_02", "dead_tree_trunk", "tree_stump_01",
        # 하부식생
        "grass_medium_01", "grass_medium_02", "grass_bermuda_01",
        "shrub_01", "shrub_02", "shrub_03", "shrub_04", "wild_rooibos_bush",
        "fern_02", "weed_plant_02", "periwinkle_plant",
        # 지물
        "rock_07", "rock_09", "stone_01", "boulder_01",
        "namaqualand_boulder_03", "namaqualand_stones_01", "rock_moss_set_01",
        "potted_plant_01", "potted_plant_04",
    ],
}


def _size_of(asset_id, kind, res):
    """내려받지 않고 API 메타데이터로 바이트 수만 계산. 실패하면 (0, 사유)."""
    files = _cached_json("/files/%s" % asset_id, "files_%s" % asset_id)
    if not files:
        return 0, "메타 조회 실패"
    if kind == "textures":
        tot = 0
        for ph_name in TEX_MAPS:
            node = files.get(ph_name) or {}
            entry = node.get(res) or node.get("2k") or {}
            f = entry.get("jpg") or entry.get("png")
            if f:
                tot += f.get("size", 0)
        return tot, None if tot else "맵 없음"
    if kind == "hdris":
        entry = (files.get("hdri") or {}).get(res) or (files.get("hdri") or {}).get("4k") or {}
        f = entry.get("hdr") or entry.get("exr") or {}
        return f.get("size", 0), None if f else "hdr 없음"
    if kind == "models":
        entry = ((files.get("gltf") or {}).get(res) or (files.get("gltf") or {}).get("1k") or {}).get("gltf")
        if not entry:
            return 0, "gltf 없음"
        inc = sum(v.get("size", 0) for v in (entry.get("include") or {}).values())
        return entry.get("size", 0) + inc, None
    return 0, "알 수 없는 종류"


def _fetch_one(asset_id, kind, res):
    if kind == "textures":
        return fetch_texture(asset_id, res=res)
    if kind == "hdris":
        return fetch_hdri(asset_id, res=res)
    return fetch_model(asset_id, res=res)


def prefetch(kinds=("textures", "hdris", "models"), res=None, budget_mb=None,
             dry_run=False, workers=6, ids=None):
    """자산표를 한 번에 받아 캐시에 채운다.

    크기를 먼저 전부 계산해 보여주고, budget_mb 를 넘기면 큰 것부터 잘라낸다.
    이미 캐시에 있는 것은 건너뛴다(멱등).
    """
    res_default = {"textures": "2k", "hdris": "4k", "models": "1k"}
    plan = []
    for kind in kinds:
        r = res or res_default[kind]
        for aid in (ids or PACK.get(kind, [])):
            size, err = _size_of(aid, kind, r)
            plan.append({"id": aid, "kind": kind, "res": r, "size": size, "error": err})

    ok = [p for p in plan if not p["error"]]
    bad = [p for p in plan if p["error"]]
    total = sum(p["size"] for p in ok)

    dropped = []
    if budget_mb:
        limit = budget_mb * 1e6
        for p in sorted(ok, key=lambda x: -x["size"]):
            if total <= limit:
                break
            ok.remove(p)
            dropped.append(p)
            total -= p["size"]

    _log("계획: %d건 / %.0f MB (%s)" % (len(ok), total / 1e6,
         ", ".join("%s %d" % (k, sum(1 for p in ok if p["kind"] == k)) for k in kinds)))
    for p in sorted(ok, key=lambda x: -x["size"])[:5]:
        _log("  최대: %-30s %6.0f MB" % (p["id"], p["size"] / 1e6))
    for p in dropped:
        _log("  예산 초과로 제외: %-24s %6.0f MB" % (p["id"], p["size"] / 1e6))
    for p in bad:
        _log("  받을 수 없음: %-24s %s" % (p["id"], p["error"]))

    if dry_run:
        return {"planned": ok, "skipped": bad, "dropped": dropped,
                "total_bytes": total, "downloaded": []}

    import concurrent.futures as _cf
    done, failed = [], []
    with _cf.ThreadPoolExecutor(max_workers=workers) as ex:
        futs = {ex.submit(_fetch_one, p["id"], p["kind"], p["res"]): p for p in ok}
        for fut in _cf.as_completed(futs):
            p = futs[fut]
            try:
                got = fut.result()
            except Exception as e:
                got, p["error"] = None, str(e)
            (done if got else failed).append(p)
            _log("  [%d/%d] %s %s" % (len(done) + len(failed), len(ok),
                                      "OK  " if got else "실패", p["id"]))

    _log("완료: 성공 %d · 실패 %d" % (len(done), len(failed)))
    return {"planned": ok, "skipped": bad, "dropped": dropped,
            "total_bytes": total, "downloaded": done, "failed": failed}


if __name__ == "__main__":
    import sys
    argv = sys.argv[1:]
    kinds = ("textures", "hdris", "models")
    res, budget, dry = None, None, False
    i = 0
    while i < len(argv):
        a = argv[i]
        if a == "--kinds":
            kinds = tuple(argv[i + 1].split(",")); i += 2
        elif a == "--res":
            res = argv[i + 1]; i += 2
        elif a == "--budget":
            budget = float(argv[i + 1]); i += 2
        elif a in ("--dry-run", "-n"):
            dry = True; i += 1
        else:
            i += 1
    prefetch(kinds=kinds, res=res, budget_mb=budget, dry_run=dry)
