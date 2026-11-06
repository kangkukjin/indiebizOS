#!/usr/bin/env python3
"""backend 층 가드 — 아래층이 위층을 import 하는 새 간선을 차단 (감사 부채 ⑦).

배경(2026-08-05 재측정): backend 216모듈의 진짜 순환은 개수가 아니라 **한 덩어리
67모듈 매듭**이고, 함수-안 import(전체의 79%)가 그것을 보이지 않게 만드는 장치였다.
디렉토리화(물리 이동)에 앞서 층을 *선언*하고, 층을 거스르는 간선을 집합으로 끊는다.
이 가드는 그 선언을 기계 검사로 고정한다: **기존 위반은 BASELINE 동결, 새 위반만 차단.**

층 (아래 → 위. import 는 같은 층 또는 아래층으로만):
  base      순수 유틸·암호·저수준 인프라 — 위를 전혀 모른다
  data      DB·등기부·상태 저장·연결 허브
  ibl       IBL 언어·실행 엔진·도구 적재
  cognition 인지·에이전트·시스템AI·자기점검
  services  폴러·스케줄러·연동·제작
  surface   HTTP 라우터·런처·포털·공개면 (실제 surface 폴더 소속)
  (assembly api.py·boot_common = 조립 루트 — 뭐든 import 해도 되지만, 아무도 이들을
   import 하면 안 된다)

같은 층 안의 순환은 이 가드의 대상이 아니다(디렉토리화 뒤 같은 디렉토리 안 문제).
층을 *가로지르는* 순환은 차단한다(cross_layer_cycles — 2026-08-05 ⑦ 후반부에 0 달성).
검사는 톱레벨+함수-안 import 전부 — 함수 안으로 숨겨도 의존은 의존이다.

물리 이동(2026-08-05) 후: 층=디렉토리(backend/base·datastore·ibl·cognition·services·
surface). 모듈 이름은 평면 유지(boot_paths 가 sys.path 에 층 디렉토리 등재) — 이 가드가
경로에서 소속을 파생하고 동명·잘못된 위치를 검사한다.

사용: python3 scripts/check_backend_layers.py
      python3 scripts/check_backend_layers.py --self-test
의존성: 없음(stdlib AST만). 실패 시 exit 1.
"""
import ast
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BACKEND = os.path.join(ROOT, "backend")

ORDER = ["base", "data", "ibl", "cognition", "services", "surface"]

ASSEMBLY = {"api", "boot_common", "file_script_cli", "code_analysis_cli"}
#: 층 배정 밖 — 시험과 **원장 일회성 유지보수 스크립트**(migrate_/retire_). 폰 번들의
#: _force_exclude_glob 과 같은 부류를 가리킨다(data/bodies/android.json) — 두 자리가 갈리면
#: 한쪽만 통과하는 모듈이 생긴다. 부류는 파일별로 전개하지 않는다(2026-09-07 retire_ 추가).
EXEMPT_PREFIX = ("test_", "migrate_", "retire_")
EXEMPT = {"prompt_benchmark", "ibl_opus_bulk_gen", "ibl_synthetic_generator",
          "ibl_synthetic_opus", "ibl_embedding_trainer",
          "boot_paths", "conftest"}  # 부트스트랩 — backend 루트가 정위치

# 동결 부채 — 시작 47간선(⑦ 전반부) → 7간선(⑦ 후반부, 2026-08-05). 신규 추가 금지.
# 절단 완료 시 항목 삭제(남아 있는데 위반이 사라졌으면 이 가드가 삭제를 요구한다).
# 잔여 7건은 전부 한 방향 상향 읽기 — 교차층 *순환*은 0 (cross_layer_cycles 가 지킨다).
BASELINE = {
    "auto_response -> portal_base",
    "auto_response -> portal_warehouse",
    "channel_engine -> api_gmail",
    "channel_engine -> indienet",
}


def layer_of(m: str, layers):
    """호출자가 수집한 경로표만 사용한다. 이름 접두사는 층을 추론하지 않는다."""
    return layers.get(m, "UNASSIGNED")


def module_layers(paths):
    directory_layers = {directory: layer for layer, directory in LAYER_DIR_OF.items()}
    result = {}
    for name, relative in paths.items():
        directory = os.path.dirname(relative)
        if name in ASSEMBLY:
            result[name] = "ASSEMBLY"
        elif name.startswith(EXEMPT_PREFIX) or name in EXEMPT:
            result[name] = None
        else:
            result[name] = directory_layers.get(directory, "UNASSIGNED")
    return result


def _import_targets(node):
    if isinstance(node, ast.Import):
        return [a.name.split(".")[0] for a in node.names]
    if isinstance(node, ast.ImportFrom) and node.level == 0:
        return [(node.module or "").split(".")[0]]
    return []


# 물리 이동(2026-08-05 ⑦) 후 층 디렉토리. "data" 는 런타임 폴더와 충돌해 datastore.
LAYER_DIR_OF = {"base": "base", "data": "datastore", "ibl": "ibl",
                "cognition": "cognition", "services": "services", "surface": "surface"}
_SKIP_DIRS = {"__pycache__", "common", "drivers", "providers", "static", "channels",
              "assets", "checkpoints", "data", "outputs", "projects", "testdata", "tokens"}


def module_paths(backend_dir):
    """{모듈명: 상대경로} — 층 디렉토리까지 재귀 (모듈 이름은 평면 유일)."""
    out = {}
    for dirpath, dirs, files in os.walk(backend_dir):
        dirs[:] = sorted(d for d in dirs if d not in _SKIP_DIRS)
        for f in sorted(files):
            if f.endswith(".py"):
                rel = os.path.relpath(os.path.join(dirpath, f), backend_dir)
                rel = rel.replace(os.sep, "/")
                if f[:-3] in out:
                    raise ValueError(f"동명 backend 모듈: {out[f[:-3]]} / {rel}")
                out[f[:-3]] = rel
    return out


def build_graph(backend_dir, paths=None):
    """backend 평면 모듈 그래프 — 톱레벨+함수-안 import 전부."""
    paths = module_paths(backend_dir) if paths is None else paths
    mods = set(paths)
    graph = {}
    for name in sorted(mods):
        try:
            with open(os.path.join(backend_dir, paths[name]),
                      encoding="utf-8") as f:
                tree = ast.parse(f.read())
        except (OSError, SyntaxError, UnicodeDecodeError) as exc:
            raise ValueError(f"검사 입력 해석 실패: {paths[name]}: {exc}") from exc
        deps = set()
        for n in ast.walk(tree):
            for t in _import_targets(n):
                if t in mods and t != name:
                    deps.add(t)
        graph[name] = deps
    return graph


def misplaced_modules(backend_dir, paths=None, layers=None):
    """층의 직속 파일 및 루트에만 둘 수 있는 예외·조립 파일을 확인한다."""
    paths = module_paths(backend_dir) if paths is None else paths
    layers = module_layers(paths) if layers is None else layers
    bad = []
    for name, rel in sorted(paths.items()):
        layer = layer_of(name, layers)
        directory = os.path.dirname(rel)
        if layer == "UNASSIGNED":
            bad.append(f"{rel}: 일반 모듈은 지정 층 폴더 바로 아래에 있어야 합니다")
        elif (layer is None or layer == "ASSEMBLY") and directory:
            bad.append(f"{rel}: 예외·조립 모듈은 backend 루트에 있어야 합니다")
    return bad


def find_violations(graph, layers):
    """(위반 간선 리스트, 미배정 모듈 리스트, 조립 루트 역참조 리스트)."""
    rank = {n: i for i, n in enumerate(ORDER)}
    viol, unassigned, into_assembly = [], [], []
    for m in sorted(graph):
        lm = layer_of(m, layers)
        if lm == "UNASSIGNED":
            unassigned.append(m)
            continue
        if lm is None or lm == "ASSEMBLY":
            continue
        for t in sorted(graph[m]):
            lt = layer_of(t, layers)
            if lt == "ASSEMBLY":
                into_assembly.append(f"{m} -> {t}")
                continue
            if lt in (None, "UNASSIGNED"):
                continue
            if rank[lt] > rank[lm]:
                viol.append(f"{m} -> {t}")
    return viol, unassigned, into_assembly


def cross_layer_cycles(graph, layers):
    """층을 가로지르는 순환(SCC) 목록 — 2026-08-05 ⑦ 후반부에 0 이 됐다. 재발=차단.

    같은 층 안의 순환(인지 클러스터·파서 쌍 부류)은 같은 미래 디렉토리 안 문제라
    허용한다. 층을 *가로지르는* 순환만 이 검사의 대상 — 그것이 '한 덩어리 매듭'의
    재료였고, 디렉토리 이동의 전제(층=이동 단위)를 깬다.
    """
    import sys as _sys
    _sys.setrecursionlimit(10000)
    idx, low, on, st, out, c = {}, {}, set(), [], [], [0]

    def walk(v):
        idx[v] = low[v] = c[0]; c[0] += 1
        st.append(v); on.add(v)
        for w in graph.get(v, ()):
            if w not in graph:
                continue
            if w not in idx:
                walk(w); low[v] = min(low[v], low[w])
            elif w in on:
                low[v] = min(low[v], idx[w])
        if low[v] == idx[v]:
            comp = []
            while True:
                w = st.pop(); on.discard(w); comp.append(w)
                if w == v:
                    break
            if len(comp) > 1:
                out.append(comp)

    for v in list(graph):
        if v not in idx:
            walk(v)
    bad = []
    for comp in out:
        component_layers = {layer_of(m, layers) for m in comp}
        component_layers.discard(None)
        if len(component_layers) > 1:
            bad.append((sorted(component_layers, key=lambda x: (x is None, str(x))), sorted(comp)))
    return bad


# ── 순수 코어 폐포 가드 (2026-08-24, IBL 경계 후속) ──────────────────────────────
# 헌법 "표준 = 문법 + 기능어 코어"는 지금까지 *어휘* 층에서만 기계적으로 강제됐다
# (STANDARD_CORE_NODES — scripts/iblbuild_validators.py). 이 가드가 그것을 *코드* 층까지
# 내린다: 문법·통화 계약은 숙주(DB·에이전트·HTTP·설정)를 몰라야 한다.
#
# ★파일 목록을 손으로 유지하지 않는다 — 뿌리에서 출발한 **전이 폐포**를 검사한다.
#   1500줄 규칙으로 파서가 또 쪼개져도 새 파일이 폐포에 자동으로 들어오므로, "가드가
#   조용히 안 보는 파일"이 생길 수 없다(2026-08-24 교훈: 사람이 고른 범위는 반드시 샌다).
#
# 불변식: 뿌리의 전이 폐포는 **ibl 층 모듈 + backend/common/** 밖으로 나가지 않는다.
#   직접이든 전이든 숙주에 닿으면 실패한다 — 예컨대 파서가 ibl_engine 을 import 하면
#   엔진이 끌고 오는 ibl_registry(data 층)에서 걸린다.
# 비-뿌리: ibl_control_blocks·ibl_exec_each 는 뿌리가 아니다. 층-밖 의존은 0이지만
#   ibl_engine·ibl_executors·workflow_engine 을 끌어와 실제로는 엔진 한복판이다
#   (2026-08-24 실측 — "의존 0인 9파일"은 *층-밖* 0이었지 분리 가능이 아니었다).
PURE_CORE_ROOTS = ["ibl_v2_parser", "ibl_envelope", "ibl_ops",
                   "api_transforms"]
# backend 아래 서브패키지: common 만 코어가 기대도 되는 잎 기질(통화·변수표기·HTML 유틸).
_LEAF_PKG = "common"
_HOST_PKGS = ("drivers", "providers", "channels")


def _core_module_paths(backend_dir, paths=None):
    """폐포 검사용 경로표 — 평면 모듈 + 서브패키지(common/drivers/providers/channels)."""
    out = dict(module_paths(backend_dir) if paths is None else paths)
    for pkg in (_LEAF_PKG,) + _HOST_PKGS:
        d = os.path.join(backend_dir, pkg)
        if not os.path.isdir(d):
            continue
        for f in sorted(os.listdir(d)):
            if f.endswith(".py") and f != "__init__.py":
                out[f"{pkg}.{f[:-3]}"] = f"{pkg}/{f}"
    return out


def _closure_deps(path, known):
    """이 파일이 import 하는 저장소 안 모듈 — 톱레벨·함수-안 전부."""
    try:
        with open(path, encoding="utf-8") as f:
            tree = ast.parse(f.read())
    except (OSError, SyntaxError, UnicodeDecodeError) as exc:
        raise ValueError(f"검사 입력 해석 실패: {path}: {exc}") from exc
    deps = set()
    for n in ast.walk(tree):
        names = []
        if isinstance(n, ast.Import):
            names = [a.name for a in n.names]
        elif isinstance(n, ast.ImportFrom) and n.level == 0 and n.module:
            names = [n.module]
        for name in names:
            if name in known:                    # common.ibl_vars 부류
                deps.add(name)
            elif name.split(".")[0] in known:    # 평면 모듈
                deps.add(name.split(".")[0])
    return deps


def pure_core_leaks(backend_dir, roots=PURE_CORE_ROOTS, *, paths=None, layers=None):
    """뿌리의 전이 폐포가 숙주에 닿은 자리 — (모듈, 도달 경로) 목록. 없으면 폐포 크기만."""
    paths = module_paths(backend_dir) if paths is None else paths
    layers = module_layers(paths) if layers is None else layers
    known = _core_module_paths(backend_dir, paths)
    roots = [r for r in roots if r in known]
    seen, order = set(roots), list(roots)
    parent = {r: None for r in roots}
    bad, i = [], 0
    while i < len(order):
        m = order[i]
        i += 1
        # common.*·ibl 층과 순수 파일 형식 경계(ibl_edition)는 허용. 그 밖은 숙주 도달이다.
        # ibl_edition의 전이 의존도 아래에서 계속 검사한다.
        if m.startswith(f"{_LEAF_PKG}."):
            pass
        elif m.startswith(_HOST_PKGS) or (layer_of(m, layers) != "ibl" and m != "ibl_edition"):
            chain, x = [], m
            while x:
                chain.append(x)
                x = parent[x]
            bad.append(" ← ".join(chain))
            continue          # 숙주 안쪽까지 파고들지 않는다 (첫 도달점만 신고)
        for d in sorted(_closure_deps(os.path.join(backend_dir, known[m]), known)):
            if d not in seen:
                seen.add(d)
                parent[d] = m
                order.append(d)
    return bad, len(order)


# ── 사적 심볼 월경 가드 (2026-08-24, IBL 경계 C부) ───────────────────────────────
# 층 안 친구-모듈끼리 언더스코어를 나눠 쓰는 것은 결함이 아니다 — 1500줄 규칙으로 한
# 유기체를 파일만 나눈 자리다(engine↔executors↔routing, parser 3종, workflow 3종).
# 결함은 **ibl 층 밖에서 ibl 층의 사적 심볼을 찌르는 것**: 사적 심볼은 계약이 아니라서,
# 언어와 숙주가 섞이는 자리가 어디인지 아무도 선언한 적이 없다는 뜻이 된다.
# A부(2026-08-24)가 부채를 0으로 만들었으므로 동결 목록 없이 새 위반을 즉시 실패시킨다.
SEAM_MODULES = {"ibl_registry"}   # datastore 에 살지만 언어가 소비하는 '사전 이음매'
PKG_TOOLS = os.path.join(ROOT, "data", "packages", "installed", "tools")


def _private_imports(path):
    """(줄번호, 모듈, [사적심볼…]) — 톱레벨·함수-안 전부."""
    try:
        with open(path, encoding="utf-8") as f:
            tree = ast.parse(f.read())
    except (OSError, SyntaxError, UnicodeDecodeError) as exc:
        raise ValueError(f"검사 입력 해석 실패: {path}: {exc}") from exc
    out = []
    for n in ast.walk(tree):
        if isinstance(n, ast.ImportFrom) and n.level == 0 and n.module:
            mod = n.module.split(".")[-1]
            privs = [a.name for a in n.names
                     if a.name.startswith("_") and a.name != "*"]
            if privs:
                out.append((n.lineno, mod, privs))
    return out


def private_symbol_leaks(backend_dir, pkg_tools=None, *, paths=None, layers=None):
    """ibl 층(+사전 이음매)의 사적 심볼을 층 밖에서 import 하는 자리 목록."""
    paths = module_paths(backend_dir) if paths is None else paths
    layers = module_layers(paths) if layers is None else layers
    if pkg_tools is None:
        pkg_tools = os.path.join(os.path.dirname(backend_dir), "data/packages/installed/tools")
    guarded = {name for name, layer in layers.items() if layer == "ibl"} | SEAM_MODULES
    bad = []

    for name, rel in sorted(paths.items()):
        lay = layer_of(name, layers)
        if lay is None:            # test_*/migrate_*/retire_* 등 검사 밖 — 화이트박스 시험은 정당
            continue
        if lay == "ibl" or name in SEAM_MODULES:
            continue               # 층 안(친구-모듈) 공유는 규칙 밖
        for lineno, mod, privs in _private_imports(os.path.join(backend_dir, rel)):
            if mod in guarded:
                bad.append(f"backend/{rel}:{lineno}: from {mod} import "
                           f"{', '.join(privs)}")

    for dirpath, dirs, files in os.walk(pkg_tools):
        dirs[:] = [d for d in dirs if d != "__pycache__"]
        for f in files:
            if not f.endswith(".py"):
                continue
            full = os.path.join(dirpath, f)
            for lineno, mod, privs in _private_imports(full):
                if mod in guarded:
                    rel = os.path.relpath(full, ROOT).replace(os.sep, "/")
                    bad.append(f"{rel}:{lineno}: from {mod} import "
                               f"{', '.join(privs)}")
    return bad


def main() -> int:
    paths = module_paths(BACKEND)
    layers = module_layers(paths)
    graph = build_graph(BACKEND, paths)
    viol, unassigned, into_assembly = find_violations(graph, layers)
    errors = []

    misplaced = misplaced_modules(BACKEND, paths, layers)
    if misplaced:
        errors.append(
            "층 폴더 경계 위반 — 모듈을 소유 층의 직속 경로에 둘 것:\n"
            + "\n".join(f"  {m}" for m in misplaced))

    spanning = cross_layer_cycles(graph, layers)
    if spanning:
        errors.append(
            "층을 가로지르는 순환 — 매듭의 재발. 등록(의존 역전)이나 데이터 하향으로\n"
            "끊을 것 (2026-08-05 ⑦ 후반부에 0 달성, 후퇴 금지):\n"
            + "\n".join(f"  [{' + '.join(map(str, ls))}] {', '.join(ms[:8])}"
                        f"{' …' if len(ms) > 8 else ''}" for ls, ms in spanning))

    if unassigned:
        errors.append(
            "층 미배정 모듈 — backend의 소유 층 폴더로 이동할 것:\n"
            + "\n".join(f"  {m}" for m in unassigned))
    if into_assembly:
        errors.append(
            "조립 루트(api/boot_common)를 import — 조립은 아무도 참조하지 않는다:\n"
            + "\n".join(f"  {e}" for e in into_assembly))

    core_bad, core_n = pure_core_leaks(BACKEND, paths=paths, layers=layers)
    if core_bad:
        errors.append(
            "순수 코어(문법·통화 계약)가 숙주에 닿았다 — 표준은 몸을 몰라야 한다.\n"
            "도달 경로(오른쪽이 뿌리). 숙주 의존은 코어 밖(엔진·실행기)으로 옮길 것:\n"
            + "\n".join(f"  {v}" for v in core_bad))

    leaks = private_symbol_leaks(BACKEND, paths=paths, layers=layers)
    if leaks:
        errors.append(
            "ibl 층의 사적 심볼을 층 밖에서 import — 사적 심볼은 계약이 아니다.\n"
            "정의처에서 공개명으로 승격하고 전 호출처를 함께 고칠 것 (동결 목록 없음):\n"
            + "\n".join(f"  {v}" for v in leaks))

    new = [v for v in viol if v not in BASELINE]
    stale = sorted(BASELINE - set(viol))
    if new:
        errors.append(
            "새 층 위반 — 아래층이 위층을 import 한다. 로직을 아래로 내리거나\n"
            "등록(의존 역전)으로 끊을 것 (BASELINE 추가 금지):\n"
            + "\n".join(f"  {v}" for v in new))
    if stale:
        errors.append(
            "BASELINE 에 남았지만 위반이 사라진 간선 — 항목을 삭제해 래칫을 조일 것:\n"
            + "\n".join(f"  {v}" for v in stale))

    if errors:
        print("[FAIL] backend 층 가드")
        for e in errors:
            print("\n" + e)
        return 1
    print(f"[OK] backend 층 가드 통과 (모듈 {len(graph)} · 동결 부채 {len(viol)}건 · "
          f"ibl 사적 심볼 월경 0건 · 순수 코어 폐포 {core_n}모듈 닫힘)")
    return 0


def self_test() -> int:
    import tempfile
    from pathlib import Path
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        def write(relative, content=""):
            path = root / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(content, encoding="utf-8")
        write("base/foundation.py")
        write("datastore/records.py", "import api_surface")
        write("surface/api_surface.py", "import records")
        write("ibl/api_new.py", "import foundation")
        write("ibl/new_language.py")
        write("cognition/consumer.py", "from new_language import _private")
        write("api.py")
        write("surface/entry.py", "import api")
        paths = module_paths(td)
        layers = module_layers(paths)
        graph = build_graph(td, paths)
        assert layers["api_new"] == "ibl"
        assert misplaced_modules(td, paths, layers) == []
        assert find_violations(graph, layers) == (["records -> api_surface"], [], ["entry -> api"])
        assert cross_layer_cycles(graph, layers) == [(["data", "surface"], ["api_surface", "records"])]
        assert len(private_symbol_leaks(td)) == 1
        write("common/value.py")
        write("ibl/root.py", "from common.value import x")
        assert pure_core_leaks(td, roots=["root"]) == ([], 2)
        write("ibl/root.py", "import api_new")
        write("ibl/api_new.py", "import records")
        assert pure_core_leaks(td, roots=["root"])[0] == ["records ← api_new ← root"]
        write("unexpected/nested.py")
        write("plain.py")
        write("surface/test_wrong.py")
        assert len(misplaced_modules(td)) == 3
        write("surface/records.py")
        try:
            module_paths(td)
        except ValueError as exc:
            assert "datastore/records.py" in str(exc) and "surface/records.py" in str(exc)
        else:
            raise AssertionError("동명 파일을 덮어썼다")
        (root / "surface/records.py").unlink()
        write("ibl/broken.py", "def ???")
        try:
            build_graph(td)
        except ValueError as exc:
            assert "ibl/broken.py" in str(exc)
        else:
            raise AssertionError("구문 오류를 누락했다")
    assert main() == 0
    print("[OK] check_backend_layers self-test 통과")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(self_test() if "--self-test" in sys.argv else main())
    except (ValueError, OSError) as exc:
        print(f"[FAIL] backend 층 가드: {exc}")
        sys.exit(1)
