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
검사는 톱레벨+함수-안 import 전부 — 함수 안으로 숨겨도 의존은 의존이다.

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
        "phone_jobs", "r2_client", "runtime_utils", "safe_store",
        "thread_context", "thumbnails",
    },
    "data": {
        "agent_registry", "body_trust", "boot_status", "business_manager",
        "calendar_manager", "conversation_db", "face_config", "file_index", "focus_map",
        "forage_memory", "health_sync", "ibl_registry", "ibl_usage_db", "install_approvals",
        "multi_chat_db", "node_registry", "notification_manager",
        "notify_dispatch", "peer_cards", "project_manager", "red_grant",
        "red_watchdog", "switch_manager", "system_ai_memory", "system_docs",
        "warehouse_catalog", "warehouse_directory", "warehouse_items",
        "websocket_manager", "xray_stream",
    },
    "ibl": {
        # ★api_engine·api_pipeline·api_transforms 는 이름만 api_* — FastAPI 라우터가
        # 아니라 api_registry.yaml 실행 엔진이다(APIRouter 0). 프리픽스 규칙보다 이
        # 명시 배정이 우선한다. 디렉토리화 때 개명 후보.
        "api_engine", "api_pipeline", "api_transforms",
        "capability_card", "channel_engine", "event_engine", "ibl_access",
        "ibl_engine", "ibl_executors", "ibl_ops", "ibl_param_vocab",
        "ibl_parser", "ibl_parser_blocks", "ibl_parser_values", "ibl_routing",
        "ibl_safety", "ibl_translate", "package_manager", "tool_context",
        "tool_loader", "tool_selector", "trigger_engine", "workflow_engine",
    },
    "cognition": {
        "agent_cognitive", "agent_communication", "agent_goals",
        "agent_pipeline", "agent_runner", "ai_agent", "android_agent",
        "body_ask", "cognitive_consciousness", "cognitive_distill",
        "cognitive_eval", "cognitive_recall", "cognitive_trace",
        "consciousness_agent", "forage_consolidation", "goal_evaluator",
        "ibl_description_audit", "ibl_usage_generator", "ibl_usage_rag",
        "memory_consolidation", "prompt_builder", "routing_system", "switch_runner",
        "system_ai_core", "system_ai_plans", "system_ai_runner",
        "system_ai_tools", "system_hooks", "system_tools",
        "system_tools_delegate", "system_tools_ibl", "vocab_crystallization",
        "world_pulse", "world_pulse_collectors", "world_pulse_health",
    },
    "services": {
        "android_calibrate", "auto_response", "business_sync",
        "calendar_actions", "calendar_html", "cdn_provision",
        "channel_poller", "ffmpeg_provision", "gen_newspaper",
        "generate_newspaper", "hippocampus_provision", "indienet",
        "indienet_common", "indienet_publish", "indienet_relay",
        "indienet_social", "multi_chat_manager", "nas_music", "nas_subtitle",
        "nas_webapp", "nostr_phone_bridge", "phone_notifications",
        "report_html", "scheduler", "warehouse_adapters", "warehouse_feed",
        "warehouse_likes", "web_collector",
    },
    "surface": {"public_face", "face_provision"},
}
SURFACE_PREFIX = ("api_", "launcher_", "portal_")
ASSEMBLY = {"api", "boot_common"}
EXEMPT_PREFIX = ("test_", "migrate_")
EXEMPT = {"prompt_benchmark", "ibl_opus_bulk_gen", "ibl_synthetic_generator",
          "ibl_synthetic_opus", "ibl_embedding_trainer", "_slide_proto"}

# 2026-08-05 동결 부채 47간선 — ⑦ 절단이 진행되며 줄어든다. 신규 추가 금지.
# 절단 완료 시 항목 삭제(남아 있는데 위반이 사라졌으면 이 가드가 삭제를 요구한다).
BASELINE = {
    "auto_response -> portal_base",
    "auto_response -> portal_warehouse",
    "calendar_manager -> calendar_actions",
    "calendar_manager -> calendar_html",
    "channel_engine -> api_gmail",
    "channel_engine -> channel_poller",
    "channel_engine -> indienet",
    "ibl_engine -> consciousness_agent",
    "ibl_engine -> world_pulse_health",
    "ibl_executors -> agent_runner",
    "ibl_executors -> goal_evaluator",
    "node_registry -> agent_runner",
    "package_manager -> ibl_usage_generator",
    "package_manager -> world_pulse_health",
    "trigger_engine -> auto_response",
    "trigger_engine -> channel_poller",
    "warehouse_likes -> portal_base",
    "warehouse_likes -> portal_warehouse",
    "world_pulse_collectors -> channel_poller",
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


def build_graph(backend_dir):
    """backend 평면 모듈 그래프 — 톱레벨+함수-안 import 전부."""
    mods = {f[:-3] for f in os.listdir(backend_dir) if f.endswith(".py")}
    graph = {}
    for name in sorted(mods):
        try:
            with open(os.path.join(backend_dir, name + ".py"),
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


def main() -> int:
    graph = build_graph(BACKEND)
    viol, unassigned, into_assembly = find_violations(graph)
    errors = []

    if unassigned:
        errors.append(
            "층 미배정 모듈 — check_backend_layers.py 의 LAYERS 에 배정할 것:\n"
            + "\n".join(f"  {m}" for m in unassigned))
    if into_assembly:
        errors.append(
            "조립 루트(api/boot_common)를 import — 조립은 아무도 참조하지 않는다:\n"
            + "\n".join(f"  {e}" for e in into_assembly))

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
    print(f"[OK] backend 층 가드 통과 (모듈 {len(graph)} · 동결 부채 {len(viol)}건)")
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
