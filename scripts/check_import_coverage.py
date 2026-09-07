#!/usr/bin/env python3
"""의존성 선언 커버리지 감사 — 코드가 import 하는 서드파티가 .venv 에 실재하는가.

왜: 정본 설치 경로(.venv, 2026-08-10) 전환 때 homebrew 3.14 에만 있던 미선언
의존성들이 런타임에 하나씩 터졌다(mcp → MCP 마운트 실패, greenlet ABI → playwright
사망, 전수 감사에서 psutil·openpyxl·python-docx·pyautogui·pyobjc 3종·pytest 추가).
"코드가 쓰는 것 = requirements 가 선언한 것" 은 저자의 기억이 아니라 기계가 증명해야
한다 — check_win_portability(유닉스 stdlib)·build --check(어휘 삼각)와 같은 부류의
정적 그물을 의존성 축에 세운 것.

원리: AST 로 대상 트리의 모든 import 이름(중첩 포함 — lazy import 도 런타임에 터지는
건 같다)을 모으고, 로컬 모듈·stdlib 을 거른 뒤, **.venv 인터프리터**가 repo 밖 cwd 에서
하나씩 실제 import 해 본다. 실패 = 그 이름을 제공하는 배포판이 .venv 에 없거나(선언
누락) 깨져 있음(greenlet ABI 부류 — 이래서 선언 대조가 아니라 실제 import 로 검사한다.
pip 이름↔import 이름 사상표도 불필요해진다).

fresh CI venv 에서 돌리면 "import 가능 ⇔ requirements 에 선언됨" 이 성립하므로
(선언 안 된 건 애초에 설치가 안 됐으니까) 같은 검사가 선언 감사를 겸한다.

판정 3단:
  실패(exit 1) — ModuleNotFoundError/ImportError. 의존성 부재·ABI 파손.
  경고(exit 0) — import 는 됐는데 부작용 예외(헤드리스 리눅스의 DISPLAY 등).
                 모듈은 있으므로 선언 커버리지 관점에선 통과.
  스킵        — 허용목록(폰 전용 java 등)·타 플랫폼 전용(pyobjc 등)·--allow-ml-missing.

호출처: ① CI portability.yml(fresh venv=선언 감사, ML 은 무거워 미설치라
--allow-ml-missing) ② World Pulse 일일 건강 점검(live .venv=실재 감사,
__static__:import_coverage 로 self_checks 합류) ③ bootstrap.py 전체 설치 끝
(fresh 설치 누락 즉시 보고). 기계 판독은 마지막 줄 '@@IMPORT_COVERAGE_JSON@@ {…}'
(ibl_health_check 의 @@HEALTH_JSON@@ 계약과 동형 — rc·마커 부재는 호출측이 러너
실패로 표면화한다).

의존성 0 (stdlib 만) — 어떤 파이썬으로 실행해도 시험은 .venv 인터프리터가 한다.
"""
import argparse
import ast
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

# 감사 대상 = 정본 설치본에서 .venv 로 실행되는 파이썬 전부
SCAN_ROOTS = [
    ROOT / "backend",
    ROOT / "data" / "packages" / "installed",
    ROOT / "scripts",
]
SCAN_FILES = [ROOT / "mcp_server.py"]
SKIP_DIRS = {"__pycache__", "_archive", "node_modules", ".git", ".venv"}

# 별도 인터프리터가 제공하는 이름은 해당 진입 파일에서만 제외한다.
# render_blender.py 는 `blender --background --python` 으로 실행되어 Blender의
# bpy·mathutils 를 쓴다. 다른 .venv 코드의 같은 import 는 계속 결손으로 잡는다.
EXTERNAL_RUNTIME_IMPORTS = {
    "data/packages/installed/tools/house-designer/render_blender.py": {"bpy", "mathutils"},
}

# ── 허용목록 ────────────────────────────────────────────────────────────────
# 이 몸(.venv 데스크탑)에 *원리적으로 없는* 이름만 올린다 — "설치 귀찮음" 은 사유가
# 못 된다(그건 requirements 에 넣어야 할 신호). 항목마다 사유 필수.
ALLOW_MISSING = {
    # 폰 전용 — Chaquopy 런타임의 Java 브리지. 데스크탑 파이썬엔 존재 자체가 불가능
    # (android 패키지 핸들러가 `from java import jclass` 성공 여부로 능력 감지).
    "java": "폰(Chaquopy) 전용 — 데스크탑엔 원리적으로 없음",
    # 폰 전용 — Chaquyopy com.chaquo.python 브리지의 별칭 계열
    "com": "폰(Chaquopy) 전용 Java 네임스페이스",
    "android": "폰(Android API) 전용",
}

# 타 플랫폼 전용 — requirements 의 environment marker 와 짝. 그 플랫폼이면 검사하고,
# 아니면 스킵(설치 자체가 안 되니까).
PLATFORM_ONLY = {
    "objc": "darwin", "Quartz": "darwin", "AppKit": "darwin", "Foundation": "darwin",
    "ApplicationServices": "darwin", "Vision": "darwin", "CoreLocation": "darwin",
    "Cocoa": "darwin",
    "winreg": "win32", "msvcrt": "win32",  # stdlib 이지만 유닉스 인터프리터 목록에 없음
    "win32api": "win32", "win32con": "win32", "win32gui": "win32",
    "win32com": "win32", "pythoncom": "win32",
}

# ML 티어(requirements-ml.txt) 가 제공하는 이름 — CI 는 ~2GB(torch) 라 미설치로 돌므로
# --allow-ml-missing 때만 스킵. 로컬(전체 설치)에선 정상 검사된다.
ML_TIER = {"sentence_transformers", "sqlite_vec", "torch", "transformers"}

# ── 좀비 래칫 ───────────────────────────────────────────────────────────────
# 은퇴한 로컬 모듈을 아직 참조하는 죽은 코드 — 의존성 결손이 아니라 코드 잔재다.
# vocab 압축 경고의 래칫 동결 선례: *기존 건만* 비차단 경고로 동결하고,
# 새로 나타나는 미해소 이름은 전부 실패다. 잔재를 정리하면 여기서도 지울 것 —
# 이 목록은 부채 원장이지 면죄부가 아니다.
# (2026-08-13 완제: ai·tool_android·schedule 3건 — 참조하던 휴면 확장
#  prompt-generator·switch-runner·scheduler 와 죽은 android_agent/api_android 자체를 은퇴)
KNOWN_ZOMBIES: dict = {}


def iter_py_files():
    for root in SCAN_ROOTS:
        if not root.exists():
            continue
        for p in sorted(root.rglob("*.py")):
            if any(part in SKIP_DIRS for part in p.parts):
                continue
            yield p
    for p in SCAN_FILES:
        if p.exists():
            yield p


def local_module_names() -> set:
    """repo 가 스스로 제공하는 모듈 이름 — 시험 대상에서 제외.

    파일 stem + 디렉토리 이름을 넓게 잡는다(backend 는 sys.path 에 얹혀 평평하게
    import 되고, 패키지 핸들러들은 자기 폴더의 형제 모듈을 상대/직접 import 한다).
    과잉 포함 리스크(로컬 이름이 pip 이름을 가림)는 check_module_shadowing.py 가
    별도 축으로 감시한다.
    """
    names = set()
    for p in iter_py_files():
        names.add(p.stem)
    for root in SCAN_ROOTS:
        if not root.exists():
            continue
        for d in root.rglob("*"):
            if d.is_dir() and not any(part in SKIP_DIRS for part in d.parts):
                names.add(d.name)
    # repo 루트 직속 .py (mcp_server 등 진입 파일)
    for p in ROOT.glob("*.py"):
        names.add(p.stem)
    return names


def collect_imports():
    """{최상위 import 이름: [\"상대경로:줄\", …]} — 중첩(함수/try 안) 포함 전수.

    lazy import 도 그 코드가 도는 순간 터지는 건 같으므로 전부 시험한다. 선택적
    폴백(try/except)의 오탐은 허용목록이 거른다 — 위치 기반 면제(가드 안이면 통과)로
    하면 greenlet ABI 처럼 '가드 안에서 조용히 죽어 기능만 사라지는' 부류를 놓친다.
    """
    found = {}
    for path in iter_py_files():
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        except (SyntaxError, UnicodeDecodeError) as e:
            print(f"[warn] parse skip {path.relative_to(ROOT)}: {e.__class__.__name__}")
            continue
        rel = str(path.relative_to(ROOT))
        runtime_imports = EXTERNAL_RUNTIME_IMPORTS.get(path.relative_to(ROOT).as_posix(), set())
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    name = alias.name.split(".")[0]
                    if name not in runtime_imports:
                        found.setdefault(name, []).append(f"{rel}:{node.lineno}")
            elif isinstance(node, ast.ImportFrom) and not node.level and node.module:
                name = node.module.split(".")[0]
                if name not in runtime_imports:
                    found.setdefault(name, []).append(f"{rel}:{node.lineno}")
    return found


def venv_python() -> Path:
    if os.name == "nt":
        return ROOT / ".venv" / "Scripts" / "python.exe"
    p = ROOT / ".venv" / "bin" / "python3"
    return p if p.exists() else ROOT / ".venv" / "bin" / "python"


# 드라이버: .venv 인터프리터에서 이름을 하나씩 import. 스트리밍 프로토콜 —
# 이름마다 @@T@@(시도)→@@R@@(결과) 를 flush 하므로, 세그폴트 등으로 프로세스가
# 통째로 죽어도 부모가 '마지막 @@T@@ 에서 죽었다' 를 안다(침묵 실패 방지).
# stdlib 필터도 여기서 한다 — 기준은 시험하는 그 인터프리터의 목록이어야 하므로.
_DRIVER = r"""
import importlib, json, sys
names = json.load(open(sys.argv[1], encoding="utf-8"))
stdlib = set(sys.stdlib_module_names) | set(sys.builtin_module_names) | {"__future__"}
for name in names:
    if name in stdlib:
        print("@@R@@ " + json.dumps({"name": name, "status": "stdlib"}), flush=True)
        continue
    print("@@T@@ " + name, flush=True)
    try:
        importlib.import_module(name)
        status = {"name": name, "status": "ok"}
    except (ImportError, ModuleNotFoundError) as e:
        status = {"name": name, "status": "fail", "error": f"{e.__class__.__name__}: {e}"}
    except BaseException as e:
        status = {"name": name, "status": "warn", "error": f"{e.__class__.__name__}: {e}"}
    print("@@R@@ " + json.dumps(status), flush=True)
print("@@DONE@@", flush=True)
"""


def run_driver(names, vpy: Path, timeout: int):
    """repo 밖 cwd·PYTHONPATH 무효화로 .venv 만의 실재를 시험한다."""
    env = {k: v for k, v in os.environ.items() if k not in ("PYTHONPATH", "PYTHONSTARTUP")}
    with tempfile.TemporaryDirectory() as td:
        names_file = Path(td) / "names.json"
        names_file.write_text(json.dumps(sorted(names)), encoding="utf-8")
        driver_file = Path(td) / "driver.py"
        driver_file.write_text(_DRIVER, encoding="utf-8")
        proc = subprocess.run(
            [str(vpy), str(driver_file), str(names_file)],
            cwd=td, env=env, capture_output=True, text=True, timeout=timeout,
        )
    results, attempting = {}, None
    for line in (proc.stdout or "").splitlines():
        if line.startswith("@@T@@ "):
            attempting = line[6:].strip()
        elif line.startswith("@@R@@ "):
            try:
                r = json.loads(line[6:])
                results[r["name"]] = r
                attempting = None
            except Exception:
                pass
    done = "@@DONE@@" in (proc.stdout or "")
    if attempting and attempting not in results:
        # import 중 프로세스 사망(세그폴트 부류) — 이것도 실재 결함이다
        tail = (proc.stderr or "").strip()[-200:]
        results[attempting] = {"name": attempting, "status": "fail",
                               "error": f"인터프리터 사망(rc={proc.returncode}): {tail}"}
    return results, done, proc.returncode


def main() -> int:
    ap = argparse.ArgumentParser(description="의존성 선언 커버리지 감사 (.venv 실 import 시험)")
    ap.add_argument("--allow-ml-missing", action="store_true",
                    help="requirements-ml.txt 티어(torch 등 ~2GB) 부재를 허용 — CI 용")
    ap.add_argument("--venv", default=None, help=".venv 파이썬 경로 재지정 (기본: repo/.venv)")
    ap.add_argument("--timeout", type=int, default=420, help="시험 전체 제한 초 (기본 420)")
    args = ap.parse_args()

    vpy = Path(args.venv) if args.venv else venv_python()
    if not vpy.exists():
        print(f"✗ .venv 파이썬 없음: {vpy} — bootstrap.py 로 먼저 설치하세요")
        print("@@IMPORT_COVERAGE_JSON@@ " + json.dumps(
            {"ok": False, "error": "venv 없음", "failures": [], "warnings": []}))
        return 2

    found = collect_imports()
    locals_ = local_module_names()
    skipped = {}
    candidates = {}
    for name, sites in found.items():
        if name in locals_:
            continue
        if name in ALLOW_MISSING:
            skipped[name] = ALLOW_MISSING[name]
        elif name in PLATFORM_ONLY and not sys.platform.startswith(PLATFORM_ONLY[name]):
            skipped[name] = f"{PLATFORM_ONLY[name]} 전용 (현재 {sys.platform})"
        elif args.allow_ml_missing and name in ML_TIER:
            skipped[name] = "ML 티어 — --allow-ml-missing"
        else:
            candidates[name] = sites

    try:
        results, done, rc = run_driver(list(candidates), vpy, args.timeout)
    except subprocess.TimeoutExpired:
        print(f"✗ 시험 타임아웃({args.timeout}s)")
        print("@@IMPORT_COVERAGE_JSON@@ " + json.dumps(
            {"ok": False, "error": f"타임아웃 {args.timeout}s", "failures": [], "warnings": []}))
        return 2

    failures, warnings, zombies, tested = [], [], [], 0
    for name in sorted(candidates):
        r = results.get(name)
        if r is None:
            if not done:  # 사망 지점 이후 미시험분 — 침묵시키지 않는다
                failures.append({"name": name, "error": "미시험(앞선 이름에서 인터프리터 사망)",
                                 "files": candidates[name][:5]})
            continue
        if r["status"] == "stdlib":
            continue
        tested += 1
        if r["status"] == "fail":
            if name in KNOWN_ZOMBIES:  # 래칫 동결분 — 비차단, 그러나 매 실행 표면화
                zombies.append({"name": name, "why": KNOWN_ZOMBIES[name],
                                "files": candidates[name][:5]})
            else:
                failures.append({"name": name, "error": r["error"], "files": candidates[name][:5]})
        elif r["status"] == "warn":
            warnings.append({"name": name, "error": r["error"], "files": candidates[name][:3]})
        elif name in KNOWN_ZOMBIES:
            print(f"  ℹ 래칫 항목 {name} 이 import 성공 — KNOWN_ZOMBIES 에서 제거할 것")

    print(f"대상 파일 스캔 → import 이름 {len(found)}개 (로컬 제외 후 시험 {tested}, 스킵 {len(skipped)})")
    for name, why in sorted(skipped.items()):
        print(f"  · 스킵 {name} — {why}")
    for w in warnings:
        print(f"  ⚠ {w['name']} — import 부작용 예외(모듈은 존재): {w['error'][:140]}")
        for f in w["files"]:
            print(f"      {f}")
    for z in zombies:
        print(f"  ⚠ 좀비 래칫 {z['name']} — {z['why']}")
        for f in z["files"]:
            print(f"      {f}")
    if failures:
        print(f"\n✗ 의존성 결손 {len(failures)}건 — .venv 에 없는/깨진 서드파티:")
        for f in failures:
            print(f"  ✗ {f['name']} — {f['error'][:180]}")
            for site in f["files"]:
                print(f"      {site}")
        print("\n처방: backend/requirements-{core,tools,ml}.txt 에 선언 후 "
              "`.venv/bin/python3 -m pip install -r …` (또는 scripts/bootstrap.py 재실행). "
              "폰/타OS 전용이 확실하면 이 스크립트의 허용목록에 사유와 함께 등재.")
    else:
        print(f"✓ 의존성 커버리지 깨끗 — 서드파티 {tested}개 전부 .venv 에서 import 성공")

    summary = {"ok": not failures, "tested": tested, "skipped": len(skipped),
               "failures": [{"name": f["name"], "error": f["error"][:200], "files": f["files"]}
                            for f in failures],
               "warnings": [{"name": w["name"], "error": w["error"][:200]} for w in warnings],
               "zombies": [z["name"] for z in zombies]}
    print("@@IMPORT_COVERAGE_JSON@@ " + json.dumps(summary, ensure_ascii=False))
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
