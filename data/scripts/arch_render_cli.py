#!/usr/bin/env python3
"""arch_render — 설계 JSON → Blender/Cycles 렌더 + glTF (등록 스크립트 래퍼)

헤드리스 Blender 를 부르는 얼은 때 — IBL 에서 [self:script]{op:"run", id:"arch_render"} 로 부른다.
인자(args): <design.json 경로 또는 design_id> [--out PNG] [--samples N] [--res W H]
              [--view auto|sw|se|ne|nw] [--gltf PATH] [--no-gltf]
표준출력은 {items:[{...}]} JSON — IBL 통화로 바로 흐른다.
"""
import json
import os
import subprocess
import sys
import glob

HERE = os.path.dirname(os.path.abspath(__file__))
BASE = os.path.dirname(os.path.dirname(HERE))          # …/indiebizOS

# 렌더러 본체는 house-designer 패키지에 산다(설치/미설치 어느 쪽이든 찾는다)
RENDERER_CANDIDATES = [
    os.path.join(HERE, "render_blender.py"),
    os.path.join(BASE, "data/packages/installed/tools/house-designer/render_blender.py"),
    os.path.join(BASE, "data/packages/not_installed/tools/house-designer/render_blender.py"),
]
RENDERER = next((p for p in RENDERER_CANDIDATES if os.path.exists(p)), RENDERER_CANDIDATES[1])

BLENDER_CANDIDATES = [
    "/Applications/Blender.app/Contents/MacOS/Blender",
    "/usr/local/bin/blender",
    "/opt/homebrew/bin/blender",
    "blender",
]


def find_blender():
    for c in BLENDER_CANDIDATES:
        if os.path.isabs(c) and os.path.exists(c):
            return c
    from shutil import which
    return which("blender")


def resolve_design(arg):
    """경로면 그대로, design_id 면 프로젝트 outputs 에서 찾는다."""
    if os.path.exists(arg):
        return os.path.abspath(arg)
    for pattern in ("outputs/house-designs/%s.json" % arg,
                    "outputs/house-designs/*%s*.json" % arg,
                    "**/house-designs/%s.json" % arg):
        hits = sorted(glob.glob(pattern, recursive=True))
        if hits:
            return os.path.abspath(hits[-1])
    return None


def fail(msg, **extra):
    out = {"success": False, "error": msg, "items": []}
    out.update(extra)
    print(json.dumps(out, ensure_ascii=False))
    sys.exit(1)


def read_stdin_args():
    """[self:script] 는 args 를 JSON 객체로 stdin 에 넣어 준다.

    stdin 이 tty 도 아니고 닫히지도 않은 파이프면(하네스·에이전트 셸) read() 가 영원히 막힌다 —
    2026-09-06 실측: 렌더가 시작도 못 한 채 10분 대기. 데이터가 있을 때만 읽는다."""
    if sys.stdin is None or sys.stdin.isatty():
        return {}
    try:
        import select
        if not select.select([sys.stdin], [], [], 0.3)[0]:
            return {}
    except Exception:
        pass
    raw = sys.stdin.read().strip()
    if not raw:
        return {}
    try:
        data = json.loads(raw)
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def main():
    argv = sys.argv[1:]
    params = read_stdin_args()

    # stdin JSON({design, samples, res, view, out, gltf}) 과 CLI argv 둘 다 받는다
    if not argv and params:
        argv = [str(params.get("design") or params.get("design_id") or "")]
        if params.get("samples"):
            argv += ["--samples", str(params["samples"])]
        if params.get("view"):
            argv += ["--view", str(params["view"])]
        res = params.get("res")
        if isinstance(res, (list, tuple)) and len(res) == 2:
            argv += ["--res", str(res[0]), str(res[1])]
        if params.get("out"):
            argv += ["--out", str(params["out"])]
        if params.get("gltf"):
            argv += ["--gltf", str(params["gltf"])]
        if params.get("no_gltf"):
            argv += ["--no-gltf"]
        if params.get("sun"):
            argv += ["--sun", str(params["sun"])]
        if params.get("force"):
            argv += ["--force"]

    if not argv or not argv[0]:
        fail("설계 JSON 경로 또는 design_id 가 필요합니다 (args: {design: \"...\"})")

    design = resolve_design(argv[0])
    if not design:
        fail("설계 파일을 찾지 못했습니다: %s" % argv[0])

    opts = argv[1:]
    base = os.path.splitext(design)[0]
    out_png = base + "_cycles.png"
    gltf = base + ".glb"
    passthrough = []

    i = 0
    while i < len(opts):
        a = opts[i]
        if a == "--out":
            out_png = os.path.abspath(opts[i + 1]); i += 2
        elif a == "--gltf":
            gltf = os.path.abspath(opts[i + 1]); i += 2
        elif a == "--no-gltf":
            gltf = None; i += 1
        elif a in ("--samples", "--view", "--hdri", "--trees", "--grass", "--sun"):
            passthrough += [a, opts[i + 1]]; i += 2
        elif a in ("--no-trees", "--no-grass", "--no-planting", "--force"):
            passthrough += [a]; i += 1
        elif a == "--res":
            passthrough += [a, opts[i + 1], opts[i + 2]]; i += 3
        else:
            i += 1

    blender = find_blender()
    if not blender:
        fail("Blender 를 찾지 못했습니다 — brew install --cask blender 로 설치하세요")
    if not os.path.exists(RENDERER):
        fail("렌더러 모듈이 없습니다: %s" % RENDERER)

    cmd = [blender, "--background", "--python", RENDERER, "--", design, out_png] + passthrough
    if gltf:
        cmd += ["--gltf", gltf]

    proc = subprocess.run(cmd, capture_output=True, text=True, timeout=1800)
    gate_lines = [l.strip() for l in (proc.stdout or "").splitlines() if l.startswith("[render_gate]")]
    if proc.returncode == 3:
        # 렌더 예산·변화 없음 관문(render_gate) — 실패가 아니라 "멈추고 보여라"는 판정. 사유를 그대로 싣는다.
        fail("렌더 관문 거절 — " + (gate_lines[-1].replace("[render_gate] ", "") if gate_lines else "예산 초과"),
             gate="budget", note="현재 최선 그림을 사용자에게 보이고 판정을 받아라. 강행은 args: {force: true}")
    if proc.returncode != 0 or not os.path.exists(out_png):
        tail = "\n".join((proc.stderr or proc.stdout or "").strip().splitlines()[-12:])
        fail("렌더 실패 (exit %s)" % proc.returncode, detail=tail)

    picked = ""
    for line in proc.stdout.splitlines():
        if "방향 선택" in line:
            picked = line.strip().split(":")[-1].strip()

    item = {
        "design": design,
        "png": out_png,
        "png_mb": round(os.path.getsize(out_png) / 1e6, 2),
        "view": picked or "sw",
        "engine": "Blender Cycles",
    }
    if gltf and os.path.exists(gltf):
        item["glb"] = gltf
        item["glb_mb"] = round(os.path.getsize(gltf) / 1e6, 2)
    if gate_lines:
        item["gate"] = gate_lines[-1].replace("[render_gate] ", "")    # 직전 대비 변화 Δ·예산 잔량 — 멈출지 판단하는 자
    item["next"] = ("그림을 사용자에게 보여라: 답에 ![외관](" + out_png + ") 한 줄. 판정은 "
                    "[engines:image_read]{op: \"critic\", criteria: \"archviz_draft|archviz|archviz_final\"} 로 단계에 맞게.")

    print(json.dumps({"success": True, "items": [item], "count": 1}, ensure_ascii=False))


if __name__ == "__main__":
    main()
