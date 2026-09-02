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
  surface   HTTP 라우터·런처·포털·공개면 (api_*/launcher_*/portal_* 프리픽스 자동)
  (assembly api.py·boot_common = 조립 루트 — 뭐든 import 해도 되지만, 아무도 이들을
   import 하면 안 된다)

같은 층 안의 순환은 이 가드의 대상이 아니다(디렉토리화 뒤 같은 디렉토리 안 문제).
층을 *가로지르는* 순환은 차단한다(cross_layer_cycles — 2026-08-05 ⑦ 후반부에 0 달성).
검사는 톱레벨+함수-안 import 전부 — 함수 안으로 숨겨도 의존은 의존이다.

물리 이동(2026-08-05) 후: 층=디렉토리(backend/base·datastore·ibl·cognition·services·
surface). 모듈 이름은 평면 유지(boot_paths 가 sys.path 에 층 디렉토리 등재) — 이 가드가
위치=선언 일치까지 검사한다.

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

LAYERS = {
    "base": {
        "desktop_notify", "device_registry", "doc_ir", "document_converter",
        "episode_logger", "hls_ladder", "korean_utils", "limb_keys",
        "logging_utils", "mime_compat", "model_resolver", "nip17", "nip44",
        "phone_jobs", "quiescent_reload", "r2_client", "reload_gate", "repeat_guard", "runtime_utils", "safe_store",
        "steer_inbox", "thread_context", "thumbnails", "window_requests", "write_ledger",
    },
    "data": {
        "agent_registry", "body_trust", "boot_status", "business_manager",
        "calendar_manager", "conversation_db", "decision_ledger", "face_config", "file_index", "focus_map",
        "forage_memory", "guide_registry", "health_sync", "ibl_registry", "ibl_usage_db",
        "install_approvals",
        "multi_chat_db", "node_registry", "notification_manager",
        "notify_dispatch", "peer_cards", "project_manager", "pulse_db", "red_apply",
        "red_grant", "red_report", "red_watchdog", "service_status", "switch_manager", "system_ai_memory",
        "system_docs",
        "warehouse_catalog", "warehouse_directory", "warehouse_items",
        "websocket_manager", "xray_stream",
    },
    "ibl": {
        # ★api_engine·api_pipeline·api_transforms 는 이름만 api_* — FastAPI 라우터가
        # 아니라 api_registry.yaml 실행 엔진이다(APIRouter 0). 프리픽스 규칙보다 이
        # 명시 배정이 우선한다. 디렉토리화 때 개명 후보.
        "api_engine", "api_pipeline", "api_transforms",
        "capability_card", "channel_engine", "event_engine", "ibl_access", "ibl_control_blocks",
        "ibl_engine", "ibl_envelope", "ibl_executors", "ibl_exec_output", "ibl_exec_goal",
        "ibl_honesty", "ibl_traceback", "ibl_quality", "ibl_pipe_types",
        "ibl_exec_each", "ibl_exec_sense", "ibl_ops", "ibl_param_vocab",
        "ibl_progress",
        "ibl_predicates",
        "ibl_parser", "ibl_parser_blocks", "ibl_parser_values", "ibl_routing",
        "ibl_safety", "ibl_translate", "package_manager", "tool_context",
        "tool_loader", "tool_selector", "trigger_engine", "workflow_engine",
        "workflow_parallel", "workflow_fallback", "workflow_contract",
        "workflow_binding", "workflow_verdict",
    },
    "cognition": {
        "agent_cognitive", "agent_communication", "agent_goals",
        "agent_pipeline", "agent_runner", "ai_agent",
        "body_ask", "cognitive_consciousness", "cognitive_distill",
        "cognitive_eval", "cognitive_recall", "cognitive_trace", "history_checkpoint",
        "consciousness_agent", "data_ownership", "derived_freshness", "distill_queue", "doc_drift", "fixture_sweeps", "forage_consolidation", "goal_evaluator", "guide_audit", "guide_feedback",
        "ibl_description_audit", "corpus_vocab_audit", "ibl_usage_generator", "ibl_usage_rag",
        "memory_consolidation", "prompt_builder", "repair_verdict_distill",
        "routing_system", "switch_runner",
        "system_ai_core", "system_ai_plans", "system_ai_runner",
        "system_ai_tools", "system_hooks", "system_tools",
        "system_tools_delegate", "system_tools_ibl", "vocab_crystallization",
        "vocab_overlap_audit",
        "world_pulse", "world_pulse_collectors", "world_pulse_health",
    },
    "services": {
        "android_calibrate", "auto_response", "business_sync",
        "calendar_actions", "calendar_html", "cdn_provision",
        "channel_poller", "ffmpeg_provision", "gen_newspaper",
        "generate_newspaper", "hippocampus_provision", "indienet",
        "ingest_engine",
        "indienet_common", "indienet_publish", "indienet_relay",
        "indienet_social", "multi_chat_manager", "nas_music", "nas_subtitle",
        "nas_webapp", "nostr_phone_bridge", "oneshot_facade",
        "phone_notifications",
        "report_html", "scheduler", "warehouse_adapters", "warehouse_feed",
    },
    # warehouse_likes: /like 라우트 보유 = 창고 공개면의 일부(⑨가 방향을 명시한
    # portal_warehouse 와의 상호 순환도 같은 층 안이 맞다)
    "surface": {"public_face", "face_provision", "warehouse_likes"},
}
SURFACE_PREFIX = ("api_", "launcher_", "portal_")
ASSEMBLY = {"api", "boot_common"}
EXEMPT_PREFIX = ("test_", "migrate_")
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
    "ibl_engine -> consciousness_agent",
    "ibl_executors -> goal_evaluator",
    "package_manager -> ibl_usage_generator",
}


def layer_of(m: str):
    """모듈의 층 이름 / 'ASSEMBLY' / None(검사 밖) / 'UNASSIGNED'."""
    if m in ASSEMBLY:
        return "ASSEMBLY"
    if m.startswith(EXEMPT_PREFIX) or m in EXEMPT:
        return None
    for name in ORDER:
        if m in LAYERS[name]:
            return name          # 명시 배정이 프리픽스 규칙보다 우선 (api_engine 부류)
    if m.startswith(SURFACE_PREFIX):
        return "surface"
    return "UNASSIGNED"


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
        dirs[:] = [d for d in dirs if d not in _SKIP_DIRS]
        for f in files:
            if f.endswith(".py"):
                rel = os.path.relpath(os.path.join(dirpath, f), backend_dir)
                out[f[:-3]] = rel.replace(os.sep, "/")
    return out


def build_graph(backend_dir):
    """backend 평면 모듈 그래프 — 톱레벨+함수-안 import 전부."""
    paths = module_paths(backend_dir)
    mods = set(paths)
    graph = {}
    for name in sorted(mods):
        try:
            with open(os.path.join(backend_dir, paths[name]),
                      encoding="utf-8") as f:
                tree = ast.parse(f.read())
        except (OSError, SyntaxError, UnicodeDecodeError):
            continue
        deps = set()
        for n in ast.walk(tree):
            for t in _import_targets(n):
                if t in mods and t != name:
                    deps.add(t)
        graph[name] = deps
    return graph


def misplaced_modules(backend_dir):
    """물리 위치 ≠ 층 선언 — 디렉토리가 곧 선언이 되도록 강제 (물리 이동 후)."""
    bad = []
    for name, rel in sorted(module_paths(backend_dir).items()):
        lay = layer_of(name)
        d = os.path.dirname(rel)
        if lay in ("ASSEMBLY", "UNASSIGNED"):
            expect = ""          # 조립 루트·미배정은 backend 루트
        elif lay is None:
            expect = ""          # 검사 밖(test_/migrate_/생성기)도 루트
        else:
            expect = LAYER_DIR_OF[lay]
        if name in ("boot_paths", "conftest"):
            expect = ""          # 부트스트랩은 루트가 정위치
        if d != expect:
            bad.append(f"{name}: {d or '(루트)'} 에 있으나 층 선언은 {expect or '(루트)'}")
    return bad


def find_violations(graph):
    """(위반 간선 리스트, 미배정 모듈 리스트, 조립 루트 역참조 리스트)."""
    rank = {n: i for i, n in enumerate(ORDER)}
    viol, unassigned, into_assembly = [], [], []
    for m in sorted(graph):
        lm = layer_of(m)
        if lm == "UNASSIGNED":
            unassigned.append(m)
            continue
        if lm is None or lm == "ASSEMBLY":
            continue
        for t in sorted(graph[m]):
            lt = layer_of(t)
            if lt == "ASSEMBLY":
                into_assembly.append(f"{m} -> {t}")
                continue
            if lt in (None, "UNASSIGNED"):
                continue
            if rank[lt] > rank[lm]:
                viol.append(f"{m} -> {t}")
    return viol, unassigned, into_assembly


def cross_layer_cycles(graph):
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
        layers = {layer_of(m) for m in comp}
        layers.discard(None)
        if len(layers) > 1:
            bad.append((sorted(layers, key=lambda x: (x is None, str(x))), sorted(comp)))
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
PURE_CORE_ROOTS = ["ibl_parser", "ibl_envelope", "ibl_predicates", "ibl_ops",
                   "api_transforms"]
# backend 아래 서브패키지: common 만 코어가 기대도 되는 잎 기질(통화·변수표기·HTML 유틸).
_LEAF_PKG = "common"
_HOST_PKGS = ("drivers", "providers", "channels")


def _core_module_paths(backend_dir):
    """폐포 검사용 경로표 — 평면 모듈 + 서브패키지(common/drivers/providers/channels)."""
    out = dict(module_paths(backend_dir))
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
    except (OSError, SyntaxError, UnicodeDecodeError):
        return set()
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


def pure_core_leaks(backend_dir, roots=PURE_CORE_ROOTS):
    """뿌리의 전이 폐포가 숙주에 닿은 자리 — (모듈, 도달 경로) 목록. 없으면 폐포 크기만."""
    known = _core_module_paths(backend_dir)
    roots = [r for r in roots if r in known]
    seen, order = set(roots), list(roots)
    parent = {r: None for r in roots}
    bad, i = [], 0
    while i < len(order):
        m = order[i]
        i += 1
        # 판정: common.* 은 허용, ibl 층 모듈은 허용, 그 밖은 숙주 도달 = 위반
        if m.startswith(f"{_LEAF_PKG}."):
            pass
        elif m.startswith(_HOST_PKGS) or layer_of(m) != "ibl":
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
    except (OSError, SyntaxError, UnicodeDecodeError):
        return []
    out = []
    for n in ast.walk(tree):
        if isinstance(n, ast.ImportFrom) and n.level == 0 and n.module:
            mod = n.module.split(".")[-1]
            privs = [a.name for a in n.names
                     if a.name.startswith("_") and a.name != "*"]
            if privs:
                out.append((n.lineno, mod, privs))
    return out


def private_symbol_leaks(backend_dir, pkg_tools=PKG_TOOLS):
    """ibl 층(+사전 이음매)의 사적 심볼을 층 밖에서 import 하는 자리 목록."""
    guarded = set(LAYERS["ibl"]) | SEAM_MODULES
    bad = []

    for name, rel in sorted(module_paths(backend_dir).items()):
        lay = layer_of(name)
        if lay is None:            # test_*/migrate_* 등 검사 밖 — 화이트박스 시험은 정당
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
    graph = build_graph(BACKEND)
    viol, unassigned, into_assembly = find_violations(graph)
    errors = []

    misplaced = misplaced_modules(BACKEND)
    if misplaced:
        errors.append(
            "물리 위치 ≠ 층 선언 — 디렉토리가 곧 선언이다. git mv 또는 LAYERS 갱신:\n"
            + "\n".join(f"  {m}" for m in misplaced))

    spanning = cross_layer_cycles(graph)
    if spanning:
        errors.append(
            "층을 가로지르는 순환 — 매듭의 재발. 등록(의존 역전)이나 데이터 하향으로\n"
            "끊을 것 (2026-08-05 ⑦ 후반부에 0 달성, 후퇴 금지):\n"
            + "\n".join(f"  [{' + '.join(map(str, ls))}] {', '.join(ms[:8])}"
                        f"{' …' if len(ms) > 8 else ''}" for ls, ms in spanning))

    if unassigned:
        errors.append(
            "층 미배정 모듈 — check_backend_layers.py 의 LAYERS 에 배정할 것:\n"
            + "\n".join(f"  {m}" for m in unassigned))
    if into_assembly:
        errors.append(
            "조립 루트(api/boot_common)를 import — 조립은 아무도 참조하지 않는다:\n"
            + "\n".join(f"  {e}" for e in into_assembly))

    core_bad, core_n = pure_core_leaks(BACKEND)
    if core_bad:
        errors.append(
            "순수 코어(문법·통화 계약)가 숙주에 닿았다 — 표준은 몸을 몰라야 한다.\n"
            "도달 경로(오른쪽이 뿌리). 숙주 의존은 코어 밖(엔진·실행기)으로 옮길 것:\n"
            + "\n".join(f"  {v}" for v in core_bad))

    leaks = private_symbol_leaks(BACKEND)
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
    # 가짜 그래프로 판정 로직 검증
    fake = {
        "logging_utils": set(),            # base
        "conversation_db": {"api_xray"},   # data -> surface (baseline 에 있음)
        "ibl_engine": {"logging_utils"},   # 아래로 — 정상
        "api_xray": {"ibl_engine"},        # 위에서 아래로 — 정상
        "api_new": {"api"},                # 조립 루트 역참조
    }
    viol, unassigned, into_asm = find_violations(fake)
    assert viol == ["conversation_db -> api_xray"], viol
    assert into_asm == ["api_new -> api"], into_asm
    assert unassigned == [], unassigned
    # 미배정 감지
    v2, un2, _ = find_violations({"totally_new_module": set()})
    assert un2 == ["totally_new_module"], un2
    # 층 판정
    assert layer_of("api_anything") == "surface"
    assert layer_of("test_foo") is None
    assert layer_of("migrate_bar") is None
    assert layer_of("api") == "ASSEMBLY"
    assert layer_of("ibl_parser") == "ibl"
    # 교차층 순환 검출: data ↔ surface 인공 순환
    fake_cyc = {"conversation_db": {"api_xray"}, "api_xray": {"conversation_db"}}
    bad = cross_layer_cycles(fake_cyc)
    assert len(bad) == 1 and set(bad[0][1]) == {"conversation_db", "api_xray"}, bad
    # 같은 층 안 순환은 허용 (파서 쌍 부류)
    fake_ok = {"ibl_parser": {"ibl_parser_blocks"}, "ibl_parser_blocks": {"ibl_parser"}}
    assert cross_layer_cycles(fake_ok) == [], "같은 층 순환이 오탐"
    # 물리 위치 = 층 선언 (물리 이동 후 불변식)
    assert misplaced_modules(BACKEND) == [], misplaced_modules(BACKEND)[:5]
    # 사적 심볼 월경: 판정 로직 + 실측 0 (A부가 부채를 0으로 만들었다 — 후퇴 금지)
    import tempfile as _tf
    with _tf.TemporaryDirectory() as td:
        os.makedirs(os.path.join(td, "cognition"))
        os.makedirs(os.path.join(td, "ibl"))
        with open(os.path.join(td, "cognition", "body_ask.py"), "w") as f:
            f.write("def f():\n    from ibl_access import _secret\n")   # 층 밖 → 잡힌다
        with open(os.path.join(td, "ibl", "ibl_engine.py"), "w") as f:
            f.write("from ibl_access import _friend\n")                 # 층 안 → 규칙 밖
        found = private_symbol_leaks(td, pkg_tools=os.path.join(td, "없는패키지"))
        assert len(found) == 1 and "body_ask.py:2" in found[0], found
    assert private_symbol_leaks(BACKEND) == [], private_symbol_leaks(BACKEND)[:5]
    # 순수 코어 폐포: 판정 로직(직접·전이·common 허용) + 실측 닫힘
    with _tf.TemporaryDirectory() as td:
        for d in ("ibl", "datastore", "common"):
            os.makedirs(os.path.join(td, d), exist_ok=True)
        w = lambda d, f, s: open(os.path.join(td, d, f), "w").write(s)  # noqa: E731
        w("common", "currency.py", "")
        w("datastore", "conversation_db.py", "")
        w("ibl", "ibl_registry.py", "")
        # ① common 만 기대는 뿌리 = 정상
        w("ibl", "ibl_envelope.py", "from common.currency import x\n")
        assert pure_core_leaks(td, roots=["ibl_envelope"]) == ([], 2), \
            pure_core_leaks(td, roots=["ibl_envelope"])
        # ② 숙주 직접 도달 = 잡힌다
        w("ibl", "ibl_ops.py", "def f():\n    from conversation_db import x\n")
        bad, _ = pure_core_leaks(td, roots=["ibl_ops"])
        assert bad == ["conversation_db ← ibl_ops"], bad
        # ③ 전이 도달도 잡힌다 (파서 → 엔진 → 사전)
        w("ibl", "ibl_engine.py", "from ibl_registry import x\n")
        w("ibl", "ibl_parser.py", "from ibl_engine import x\n")
        bad, _ = pure_core_leaks(td, roots=["ibl_parser"])
        assert bad == ["ibl_registry ← ibl_engine ← ibl_parser"], bad
    core_bad, core_n = pure_core_leaks(BACKEND)
    assert core_bad == [], core_bad
    assert core_n >= len(PURE_CORE_ROOTS), core_n
    # 실그래프: 교차층 순환 0 이어야 한다 (2026-08-05 달성 불변식)
    graph0 = build_graph(BACKEND)
    assert cross_layer_cycles(graph0) == [], "실그래프에 교차층 순환 존재"
    # 실그래프에서 BASELINE 정합(신규 0 · 부실 0)이어야 자기모순이 없다
    graph = build_graph(BACKEND)
    viol, unassigned, into_asm = find_violations(graph)
    assert not unassigned, f"미배정: {unassigned}"
    assert not [v for v in viol if v not in BASELINE], "self-test: 새 위반 존재"
    assert not (BASELINE - set(viol)), "self-test: 부실 BASELINE 존재"
    print("[OK] check_backend_layers self-test 통과")
    return 0


if __name__ == "__main__":
    sys.exit(self_test() if "--self-test" in sys.argv else main())
