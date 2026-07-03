"""
ibl_engine.py - IBL 노드-액션 실행 엔진

[node:action]{params} 모델을 파싱하고 적절한 백엔드로 라우팅합니다.

사용법:
    from ibl_engine import execute_ibl, list_ibl_nodes, list_actions

    # 노드 도구 실행
    result = execute_ibl({"action": "search", "params": {"query": "임대차"}}, ".")

    # 노드 목록
    nodes = list_ibl_nodes()

    # 노드별 액션 목록
    actions = list_actions("sense")

모듈화:
- ibl_routing.py: 라우팅 로직, 시스템 명령, 에이전트 관리
- ibl_executors.py: 노드 실행, 출력 핸들러, Goal 관리, 제어 흐름
"""

import os
import json
import asyncio
import threading
import yaml
from pathlib import Path
from typing import Any, Dict, List, Optional


# === Persistent 이벤트 루프 (async 핸들러용) ===
# browser-action 등 async 도구가 파이프라인에서 연속 호출될 때,
# 같은 이벤트 루프를 공유해야 Playwright 객체가 유효함.
_persistent_loop: Optional[asyncio.AbstractEventLoop] = None
_persistent_thread: Optional[threading.Thread] = None


def _get_persistent_loop() -> asyncio.AbstractEventLoop:
    """async 핸들러 전용 이벤트 루프를 반환 (없으면 생성)"""
    global _persistent_loop, _persistent_thread

    if _persistent_loop and not _persistent_loop.is_closed():
        return _persistent_loop

    _persistent_loop = asyncio.new_event_loop()

    def _run_loop(loop):
        asyncio.set_event_loop(loop)
        loop.run_forever()

    _persistent_thread = threading.Thread(target=_run_loop, args=(_persistent_loop,), daemon=True)
    _persistent_thread.start()
    return _persistent_loop


# === 노드 레지스트리 로딩 ===

_nodes: Optional[Dict] = None
_nodes_path: Optional[Path] = None


def _get_nodes_path() -> Path:
    """ibl_nodes.yaml 경로"""
    global _nodes_path
    if _nodes_path:
        return _nodes_path
    env_path = os.environ.get("INDIEBIZ_BASE_PATH")
    if env_path:
        _nodes_path = Path(env_path) / "data" / "ibl_nodes.yaml"
    else:
        _nodes_path = Path(__file__).parent.parent / "data" / "ibl_nodes.yaml"
    return _nodes_path


def _merge_api_registry_actions(nodes_config: Dict):
    """api_registry의 node 필드 기반 노드 액션 자동 병합.

    api_registry.yaml 도구에 node/action_name이 선언되어 있으면
    해당 노드의 actions dict에 in-place 병합한다.
    YAML 앵커(&id005 등)가 가리키는 동일 dict를 직접 변경하므로
    nodes 섹션에도 자동 반영된다.
    """
    try:
        from api_engine import _load_registry
    except ImportError:
        return

    registry = _load_registry()
    tools = registry.get("tools", {})

    for tool_name, tool_cfg in tools.items():
        node_name = tool_cfg.get("node")
        if not node_name:
            continue

        action_name = tool_cfg.get("action_name", tool_name)
        node_cfg = nodes_config.get(node_name)
        if not node_cfg:
            continue

        actions = node_cfg.get("actions")
        if actions is None:
            actions = {}
            node_cfg["actions"] = actions

        # 수동 정의가 이미 있으면 덮어쓰지 않음
        if action_name in actions:
            continue

        action = {"router": "api_engine", "tool": tool_name}
        if tool_cfg.get("description"):
            action["description"] = tool_cfg["description"]
        if tool_cfg.get("target_key"):
            action["target_key"] = tool_cfg["target_key"]

        actions[action_name] = action


# 폰 프로파일(#3 runs_on) — runnable 액션 집합 캐시.
_phone_runnable_cache = {"loaded": False, "set": None}


def _phone_runnable(node: str, action: str) -> bool:
    """폰 프로파일이면 phone_manifest.runnable_actions 막을 적용. PC면 항상 True."""
    if os.environ.get("INDIEBIZ_PROFILE") != "phone":
        return True
    if not _phone_runnable_cache["loaded"]:
        s = None
        try:
            base = os.environ.get("INDIEBIZ_BASE_PATH") or os.path.join(os.path.dirname(__file__), "..")
            with open(os.path.join(base, "data", "phone_manifest.json"), "r", encoding="utf-8") as f:
                s = set(json.load(f).get("runnable_actions") or [])
        except Exception:
            s = None  # 매니페스트 없으면 가드 비활성(안전)
        _phone_runnable_cache["set"] = s
        _phone_runnable_cache["loaded"] = True
    rs = _phone_runnable_cache["set"]
    return True if rs is None else (f"{node}:{action}" in rs)


def _forward_to_phone(phone_url: str, node: str, action: str, params: dict,
                      agent_id: str = None) -> Dict:
    """분산 IBL(#2) — phone_only 액션을 폰 /ibl/execute 로 HTTP 포워드(몸=폰).

    맥(두뇌)에서 도는 에이전트가 [limbs:phone] 같은 폰 전용 동작을 만나면, 맥에서
    `from java` 로 실패(graceful 거부)하는 대신 폰이 실제 네이티브 effector(진동·알림·
    TTS 등)를 구동하게 보낸다. 호출부는 INDIEBIZ_PHONE_URL 설정 시에만 이 함수를 부르므로,
    여기선 항상 dict 를 돌려준다(폰 미도달도 명확한 에러 dict — 맥서 USB-ADB 하라는 오인 회피).

    agent_id: 빌림은 호출하는 주체가 액션 주체(설계결정 §6.4) — 호출자 신원을 폰에 전파해
    폰이 system_ai 로 떨구지 않고 진짜 호출자로 기록한다(폰 honor는 phone_api 측, 미설정이면 무해).
    """
    code = f"[{node}:{action}]"
    if params:
        code += json.dumps(params, ensure_ascii=False)
    payload = {"code": code}
    if agent_id:
        payload["agent_id"] = agent_id
    try:
        import requests
        headers = {"Content-Type": "application/json"}
        token = os.environ.get("INDIEBIZ_PHONE_TOKEN")
        if token:
            headers["X-Phone-Token"] = token  # #3 인에이블러(폰 인증) 대비 — 미설정이면 미동봉
        r = requests.post(f"{phone_url.rstrip('/')}/ibl/execute",
                          json=payload, headers=headers, timeout=30)
    except Exception as e:
        return {"error": f"[{node}:{action}]은 폰에서 실행되는 동작인데 폰({phone_url})에 "
                         f"연결할 수 없습니다. 폰 백엔드가 켜져 있는지 확인하세요. "
                         f"({e.__class__.__name__})",
                "phone_unreachable": True}
    if r.status_code != 200:
        return {"error": f"폰 실행 실패 (HTTP {r.status_code})",
                "detail": r.text[:300], "phone_forward": True}
    try:
        result = r.json()
    except Exception:
        return {"result": r.text, "_forwarded_to": "phone"}
    if isinstance(result, dict):
        result.setdefault("_forwarded_to", "phone")
        # ★빌림-완성(대칭): 맥이 phone_only(sense:see 사진 등)를 빌리면, 폰이 만든 파일을
        # 맥 로컬로 가져온다. 폰 /launcher/file 에서 같은 토큰으로 받음(폰 미도달/미인증 시 graceful).
        result = _pull_remote_artifacts(
            result, phone_url.rstrip('/'),
            {"X-Phone-Token": token} if token else {})
    return result


# 분산 IBL — 맥(연합 두뇌) 위임 세션 캐시(원격 런처 인증). 폰 프로세스 내 모듈 전역.
_mac_session_cache = {"session": None}


def _forward_to_mac(node: str, action: str, params: dict, agent_id: str = None,
                    mac_url: str = None) -> Dict:
    """분산 IBL — 폰서 못 도는 액션을 맥 /ibl/execute 로 단건 포워드(머리=맥).

    `_forward_to_phone`(맥→폰)의 대칭(폰→맥). 이게 "액션이 진짜 실행 단위" 의 핵심:
    execute_ibl 은 합성 code(&/>>/??)의 leaf 액션마다 호출되므로(workflow_engine), 각
    액션이 여기서 개별적으로 로컬/맥을 결정한다 → 혼합 code 도 액션별로 쪼개져 실행.

    맥은 원격 런처 인증 뒤에 있어 세션 로그인 필요(INDIEBIZ_MAC_URL + INDIEBIZ_MAC_PASSWORD).
    project_id=앱모드 로 프로젝트 경로 확보. 신원은 호출자 agent_id 를 전파한다(설계결정 §6.4
    — 빌림은 호출하는 주체가 액션 주체). 미동봉이면 맥서 앱모드 기본(system_ai)으로 떨어지는데,
    그건 폰-자아가 자기 신원을 잃는 버그였다(PHONE_SELF_HOSTING_HANDOFF §6.2). 엔진은 맥에서도
    도므로(INDIEBIZ_PROFILE!=phone) 이 경로는 폰에서만 진입 → 재포워드 루프 없음.

    mac_url: 다중 노드 라우팅이 레지스트리서 찾은 compute-class 노드 주소를 넘김. 미지정이면
    레거시 단수 env(INDIEBIZ_MAC_URL) — 폰 자기등록 전 호환."""
    mac_url = (mac_url or os.environ.get("INDIEBIZ_MAC_URL") or "").rstrip("/")
    if not mac_url:
        return {"error": f"[{node}:{action}]은 집 PC(맥)에서 실행되는 액션인데 위임 대상이 "
                         "설정돼 있지 않습니다. (집 PC가 켜져 있고 INDIEBIZ_MAC_URL 이 설정돼 있어야 합니다.)",
                "mac_unreachable": True}
    code = f"[{node}:{action}]"
    if params:
        code += json.dumps(params, ensure_ascii=False)
    payload = {"code": code, "project_id": "앱모드"}
    if agent_id:
        payload["agent_id"] = agent_id  # 호출자 신원 전파 — 맥서 폰-자아로 기록(미동봉 시만 system_ai 폴백)
    password = os.environ.get("INDIEBIZ_MAC_PASSWORD")
    import requests

    def _post():
        headers = {"Content-Type": "application/json"}
        sess = _mac_session_cache.get("session")
        if sess:
            headers["X-Launcher-Session"] = sess
        return requests.post(f"{mac_url}/ibl/execute", json=payload, headers=headers, timeout=120)

    def _login() -> bool:
        if not password:
            return False
        try:
            r = requests.post(f"{mac_url}/launcher/auth/login",
                              json={"password": password}, timeout=15)
            if r.status_code == 200:
                sid = (r.json() or {}).get("session_id")
                if sid:
                    _mac_session_cache["session"] = sid
                    return True
        except Exception:
            pass
        return False

    try:
        r = _post()
        if r.status_code in (401, 403) and password:  # 세션 만료/미로그인 → 1회 재로그인
            if _login():
                r = _post()
    except Exception as e:
        return {"error": f"[{node}:{action}]은 집 PC(맥)에서 실행되는데 맥({mac_url})에 "
                         f"연결할 수 없습니다. 집 PC가 켜져 있는지 확인하세요. ({e.__class__.__name__})",
                "mac_unreachable": True}
    if r.status_code != 200:
        return {"error": f"집 PC 위임 실패 (HTTP {r.status_code})",
                "detail": r.text[:300], "mac_forward": True}
    try:
        result = r.json()
    except Exception:
        return {"result": r.text, "_forwarded_to": "mac"}
    if isinstance(result, dict):
        result.setdefault("_forwarded_to", "mac")
        # ★빌림-완성: mac_only 는 "폰서 못 함"이 아니라 "맥서 실행되는, 빌려오는 액션"이다.
        # 폰서 호출하면 맥이 만든 산출 파일이 폰으로 돌아와야 정상(폰 프로파일에서만 풀).
        if os.environ.get("INDIEBIZ_PROFILE") == "phone":
            sess = _mac_session_cache.get("session")
            result = _pull_remote_artifacts(result, mac_url, {"X-Launcher-Session": sess} if sess else {})
    return result


def _pull_remote_artifacts(result: dict, remote_url: str, headers: dict) -> dict:
    """포워드 결과 안의 *원격* 파일 경로를 로컬로 내려받아 경로 재작성 (빌림-완성, 양방향 공용).

    ★빌림은 양쪽 다다 — 폰이 mac_only 를, 맥이 phone_only 를 빌리고, 어느 방향이든 산출
    파일은 *부른 몸*으로 돌아와야 한다(그게 정상). 원격 /launcher/file 로 바이트를 받아
    (포워드와 같은 인증 헤더 재사용) 로컬 outputs 에 쓰고, file/path 류 필드를 로컬 경로로 바꾼다.
    chart 처럼 중첩(data.path)도 있어 재귀 _walk 로 어느 깊이든 탐색."""
    try:
        from runtime_utils import get_base_path
        local_out = os.path.join(str(get_base_path()), "outputs")
        os.makedirs(local_out, exist_ok=True)
    except Exception:
        return result
    import requests
    # 파일 경로를 담는 흔한 키들 — 최상위뿐 아니라 중첩(chart는 data.path)도 있어 재귀 탐색.
    FILE_KEYS = ("file", "path", "output_path", "output", "image", "chart_path",
                 "mp3", "mp4", "audio", "video", "pdf", "png")

    def _pull_one(v):
        if not (isinstance(v, str) and v and os.path.isabs(v)):
            return None
        if os.path.exists(v):  # 이미 폰 로컬(anywhere 가 로컬 실행한 경우)
            return None
        try:
            r = requests.get(f"{remote_url}/launcher/file", params={"path": v},
                             headers=headers, timeout=60)
            if r.status_code == 200 and r.content:
                dest = os.path.join(local_out, os.path.basename(v))
                with open(dest, "wb") as f:
                    f.write(r.content)
                return dest
        except Exception:
            pass
        return None

    def _walk(obj):
        if isinstance(obj, dict):
            for k, v in list(obj.items()):
                if k in FILE_KEYS and isinstance(v, str):
                    nd = _pull_one(v)
                    if nd:
                        obj[k] = nd
                else:
                    _walk(v)
        elif isinstance(obj, list):
            for it in obj:
                _walk(it)

    _walk(result)
    return result


# ============ 다중 노드 분산 라우팅 ============
# 폰 수를 고정하지 않는다 — device_registry 라이브 테이블(자기등록+heartbeat)로 "지금 연결된
# 노드"를 동적 조회해 원격 액션의 대상을 고른다. 설계: docs/MULTINODE_TOPOLOGY_DESIGN.md

def _forward_to_node(entry: dict, node: str, action: str, params: dict,
                     agent_id: str = None) -> Dict:
    """레지스트리 항목(노드)으로 포워드. 인증 방식은 항목의 auth/능력으로 분기."""
    url = (entry.get("url") or "").rstrip("/")
    auth = entry.get("auth")
    caps = entry.get("capabilities") or []
    if auth == "x_phone_token" or "phone-class" in caps:
        if not url:
            return {"error": f"노드 '{entry.get('alias')}'의 주소를 모릅니다(미등록).",
                    "node_unreachable": True}
        return _forward_to_phone(url, node, action, params, agent_id=agent_id)
    # compute-class(맥/허브)
    return _forward_to_mac(node, action, params, agent_id=agent_id, mac_url=url or None)


def _resolve_and_maybe_forward(node, action, action_config, params,
                               target_alias, agent_id):
    """능력으로 로컬/원격을 판정하고, 원격이면 연결된 노드 중 대상을 고른다.

    반환: 원격으로 처리했으면 결과/에러/되물음 dict, 로컬 실행이면 None.
    선택 우선순위: 명시 @주소 > 자기-가능(로컬) > (능력 후보) 1대 > 주(主)기기 > 모호하면 되물음.
    레지스트리 미가용/후보 없음이면 레거시 단수 env 로 폴백(현 단일-폰 셋업 무회귀).
    """
    profile = os.environ.get("INDIEBIZ_PROFILE", "")
    try:
        import device_registry as dr
    except Exception:
        dr = None

    # 1. 명시 주소 @alias 최우선
    if target_alias:
        if dr is None:
            return {"error": f"노드 주소지정(@{target_alias})을 쓸 수 없습니다(레지스트리 미가용)."}
        entry = dr.get_by_alias(target_alias)
        if entry is None:
            live = dr.live_aliases()
            return {"error": f"'@{target_alias}' 노드를 찾을 수 없습니다. 지금 연결된 노드: "
                             f"{', '.join(live) if live else '없음'}",
                    "live_nodes": live}
        if entry.get("self"):
            return None  # 자기 자신 → 로컬 실행
        return _forward_to_node(entry, node, action, params, agent_id)

    # 2. 능력 기반 자동 — 먼저 "로컬에서 되는가?"
    if profile == "phone":
        if _phone_runnable(node, action):
            return None  # 폰 로컬
        req = dr.COMPUTE_CLASS if dr else "compute-class"
    else:
        if action_config.get("runs_on") != "phone_only":
            return None  # 맥/데스크탑 로컬
        req = dr.PHONE_CLASS if dr else "phone-class"

    # 3. 원격 후보 = 그 능력 가진 라이브 노드
    cands = dr.live_with_capability(req) if dr else []
    if not cands:
        # 레거시 env 폴백 (폰 자기등록 전 호환)
        if req == "compute-class":
            return _forward_to_mac(node, action, params, agent_id=agent_id)
        purl = os.environ.get("INDIEBIZ_PHONE_URL")
        if purl:
            return _forward_to_phone(purl, node, action, params, agent_id=agent_id)
        return None  # 폰 없음 → 로컬 핸들러가 phone_only graceful 거부

    if len(cands) == 1:
        return _forward_to_node(cands[0], node, action, params, agent_id)

    # 4. 후보 2+ → 주(主)기기 있으면 그것, 없으면 되물음
    primary = [c for c in cands if c.get("primary")]
    if len(primary) == 1:
        return _forward_to_node(primary[0], node, action, params, agent_id)
    return {
        "needs_node_choice": True,
        "message": f"[{node}:{action}]을(를) 어느 기기에서 실행할까요?",
        "options": [c.get("alias") for c in cands],
        "hint": f"[{node}:{action}]@<별칭> 으로 지정하세요.",
    }


def _load_nodes_config() -> Dict:
    """노드 정의 로드 (캐싱)"""
    global _nodes
    if _nodes is not None:
        return _nodes

    path = _get_nodes_path()
    if not path.exists():
        _nodes = {"nodes": {}}
        return _nodes

    with open(path, "r", encoding="utf-8") as f:
        _nodes = yaml.safe_load(f) or {"nodes": {}}

    # api_registry에서 node 바인딩된 액션 자동 병합
    _merge_api_registry_actions(_nodes.get("nodes", {}))

    return _nodes


def reload_nodes():
    """노드 정의 강제 리로드 (실행기 측 캐시 전부).

    ibl_engine._nodes + ibl_executors._nodes_cache(파생 캐시)를 함께 무효화한다.
    /packages/reload 가 ibl_access(카탈로그) 캐시만 비우던 누락을 메운다 — src/nodes 변경이
    backend 재시작 없이 실행 경로에도 반영되도록.
    """
    global _nodes
    _nodes = None
    _load_nodes_config()
    # ibl_executors 가 _load_nodes_config 결과의 nodes 섹션을 별도 캐싱하므로 함께 비운다.
    try:
        import ibl_executors
        ibl_executors._nodes_cache = None
    except Exception:
        pass


def get_node_actions(node_name: str) -> set:
    """특정 노드의 유효한 액션 이름 set 반환"""
    config = _load_nodes_config()
    nodes = config.get("nodes", {})
    node_def = nodes.get(node_name, {})
    actions = node_def.get("actions", {})
    return set(actions.keys())


# === 하위 모듈 import (re-export) ===
from ibl_routing import (
    _route_api_engine, _route_handler, _route_system,
    _execute_launcher_command, _discover_nodes, _search_guide,
    _delegate_workflow, _agent_ask, _agent_ask_sync,
    _agent_list, _agent_info, _route_driver, _route_by_config,
)
from ibl_executors import (
    _load_nodes, _execute_node,
    _execute_info_node, _execute_store_node, _execute_exec_node,
    _output_gui, _output_file, _extract_path_from_prev,
    _output_open, _output_clipboard, _output_download,
    _execute_output_node,
    _goal_list, _goal_status, _goal_kill,
    _log_attempt, _get_attempts, _summarize_attempts,
    _execute_goal_block, _execute_condition, _execute_case,
    _evaluate_sense_condition, _get_sense_value,
)


# === 공개 API ===

def list_ibl_nodes() -> List[Dict]:
    """사용 가능한 노드 목록"""
    reg = _load_nodes_config()
    result = []
    for name, config in reg.get("nodes", {}).items():
        result.append({
            "node": name,
            "description": config.get("description", ""),
            "actions": list(config.get("actions", {}).keys()),
        })
    return result


def list_actions(node: str) -> List[Dict]:
    """특정 노드의 액션 목록"""
    reg = _load_nodes_config()
    node_config = reg.get("nodes", {}).get(node)
    if not node_config:
        return []

    result = []
    for name, config in node_config.get("actions", {}).items():
        info = {
            "action": name,
            "description": config.get("description", ""),
            "router": config.get("router", ""),
        }
        if config.get("tool"):
            info["mapped_tool"] = config["tool"]
        if config.get("phase"):
            info["phase"] = config["phase"]
        result.append(info)
    return result


# === async-safe 핸들러 오프로드 ===
# MCP/ClaudeCode 경로에서는 execute_ibl이 '실행 중인 이벤트 루프' 위에서 호출된다.
# 그 컨텍스트에서 패키지 핸들러가 asyncio.run()·Playwright sync API를 쓰면
# "asyncio.run() cannot be called from a running event loop"로 죽는다(media_producer,
# lecture_workspace 등). 해결: handler/driver 라우터 실행을 '루프 없는 워커 스레드'로 넘긴다.
#  - 루프가 없으면(동기 프로바이더 등) 오프로드 안 함 → 기존과 100% 동일.
#  - thread_context(threading.local)는 스냅샷→워커 복원해 allowed_nodes 등 보존.
#  - delegate(system 라우터)/channel/workflow 등은 손대지 않음 → AI·위임 경로 무영향.
_offload_pool = None


def _get_offload_pool():
    """핸들러 오프로드용 스레드풀 (지연 생성)."""
    global _offload_pool
    if _offload_pool is None:
        import concurrent.futures
        _offload_pool = concurrent.futures.ThreadPoolExecutor(
            max_workers=8, thread_name_prefix="ibl_offload"
        )
    return _offload_pool


def _run_router_safely(fn, *args, **kwargs):
    """실행 중인 이벤트 루프 위라면 루프 없는 워커 스레드에서 fn을 실행한다.

    핸들러/드라이버 내부의 asyncio.run()/sync_playwright()가 충돌 없이 동작하도록.
    루프가 없으면 그대로 인라인 실행(기존 동작 유지).
    """
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return fn(*args, **kwargs)  # 루프 없음 → 인라인 (변화 없음)

    # 실행 중인 루프 위 → 워커 스레드로 오프로드 (+ thread_context 전파)
    import thread_context as _tc
    snap = _tc.snapshot()

    def _worker():
        _tc.restore(snap)
        return fn(*args, **kwargs)

    return _get_offload_pool().submit(_worker).result()


def execute_ibl(tool_input: dict, project_path: str, agent_id: str = None) -> Any:
    """
    IBL 노드 도구 실행

    Args:
        tool_input: {
            "action": "search",      # 필수: 액션 이름
            "params": {...},         # 파라미터
            ...기타 노드별 파라미터
        }
        project_path: 프로젝트 경로 (필수, 호출자가 명시 전달)
        agent_id: 에이전트 ID

    Returns:
        실행 결과
    """
    # Phase 26: Goal Block 실행
    if tool_input.get("_goal"):
        return _execute_goal_block(tool_input, project_path, agent_id)

    # Phase 26: 조건문 (if/else) 실행
    if tool_input.get("_condition"):
        return _execute_condition(tool_input, project_path, agent_id)

    # Phase 26: Case문 실행
    if tool_input.get("_case"):
        return _execute_case(tool_input, project_path, agent_id)

    # Phase 12: 노드 타입 모드
    node_type = tool_input.get("_node_type")
    if node_type:
        return _execute_node(node_type, tool_input, project_path, agent_id)

    action = tool_input.get("action")
    if not action:
        node = tool_input.get("_node")
        if node:
            reg = _load_nodes_config()
            nc = reg.get("nodes", {}).get(node, {})
            actions = list(nc.get("actions", {}).keys())
            return {
                "error": f"action 파라미터가 필요합니다. [node:action] 형식으로 호출하세요.",
                "node": node,
                "available_actions": actions[:20],
                "example": f'[{node}:{actions[0]}]{{...}}' if actions else None,
                "hint": f"총 {len(actions)}개 액션 사용 가능"
            }
        return {"error": "action 파라미터가 필요합니다.", "available_nodes": [d["node"] for d in list_ibl_nodes()]}

    # 노드는 tool_name에서 결정됨 (ibl_api -> api, ibl_web -> web 등)
    # 이 함수는 노드가 이미 결정된 상태로 호출됨
    node = tool_input.get("_node")
    if not node:
        return {"error": "_node이 설정되지 않았습니다. handler.py를 통해 호출해주세요."}

    reg = _load_nodes_config()
    node_config = reg.get("nodes", {}).get(node)
    if not node_config:
        return {"error": f"알 수 없는 노드: {node}", "available_nodes": [d["node"] for d in list_ibl_nodes()]}

    action_config = node_config.get("actions", {}).get(action)
    if not action_config:
        available = list(node_config.get("actions", {}).keys())
        return {"error": f"노드 '{node}'에 '{action}' 액션이 없습니다.",
                "available_actions": available}

    router = action_config.get("router")
    params = tool_input.get("params", {})

    # 중앙 파라미터 별칭 정규화 — 비-handler 라우터(system/workflow_engine/channel_engine/
    # trigger_engine 등)도 액션의 aliases 선언(레지스트리) 적용받게. handler/driver는
    # _route_by_config 에서 한 번 더 적용되나 정규 키 우선이라 멱등. (예: self:trigger 의 id→trigger_id)
    from ibl_routing import _normalize_param_aliases
    params = _normalize_param_aliases(node, action, params, action_config)

    # default_input 병합: 액션에 정의된 기본값을 params에 적용 (사용자 값 우선)
    default_input = action_config.get("default_input")
    if default_input and isinstance(default_input, dict):
        for k, v in default_input.items():
            if k not in params:
                params[k] = v

    # === 다중 노드 분산 라우팅 ===
    # 능력(runs_on)으로 로컬/원격을 판정하고, 원격이면 "지금 연결된" 노드 중 대상을 고른다
    # (명시 @주소 > 자기-가능 > 후보1대 > 주(主)기기 > 모호하면 되물음). 폰 수를 고정하지 않음 —
    # device_registry 라이브 테이블 동적 조회. 합성 code 의 각 leaf 가 이 chokepoint 를 거쳐
    # 액션별로 따로 라우팅된다(weather=로컬·world_bank=맥, [sense:here]@폰2=폰2). 레지스트리
    # 미가용/후보없음이면 레거시 단수 env 폴백(현 단일-폰 셋업 무회귀).
    _dist = _resolve_and_maybe_forward(node, action, action_config, params,
                                       tool_input.get("target_node"), agent_id)
    if _dist is not None:
        return _dist

    # 라우터별 실행 + 개별 액션 기록 (X-Ray용)
    import time as _time
    _action_start = _time.time()
    _action_success = True
    result = None

    try:
        if router == "api_engine":
            mapped_tool = action_config.get("tool")
            result = _route_api_engine(action, params, project_path,
                                     mapped_tool=mapped_tool)
        elif router == "handler":
            mapped_tool = action_config.get("tool")
            # Phase 30: scope 선언 (workspace/system/project). 미지정 시 project.
            scope = action_config.get("scope", "project")
            result = _run_router_safely(_route_handler, mapped_tool, params, project_path, agent_id, scope=scope)
        elif router == "system":
            func_name = action_config.get("func")
            result = _route_system(func_name, params, project_path, agent_id=agent_id)
        elif router == "workflow_engine":
            from workflow_engine import execute_workflow_action
            result = execute_workflow_action(action, params, project_path)
        elif router == "channel_engine":
            from channel_engine import execute_channel_action
            result = execute_channel_action(action, params, project_path, agent_id=agent_id)
        elif router == "web_collector":
            from web_collector import execute_web_collect_action
            result = execute_web_collect_action(action, params, project_path)
        elif router in ("event_engine", "trigger_engine"):
            from trigger_engine import execute_trigger
            result = execute_trigger(action, params, project_path)
        elif router == "driver":
            driver_type = action_config.get("driver", "sqlite")
            dn = action_config.get("driver_node")
            result = _run_router_safely(_route_driver, driver_type, node, action, params, project_path, driver_node=dn)
        elif router == "stub":
            phase = action_config.get("phase", "?")
            return {
                "error": f"[{node}:{action}]은 Phase {phase}에서 구현 예정입니다.",
                "node": node, "action": action, "status": "not_implemented",
            }
        else:
            return {"error": f"알 수 없는 라우터: {router}"}

        # 결과에서 성공/실패 판단
        if isinstance(result, dict):
            if result.get("success") is False:
                _action_success = False
            elif result.get("error"):  # error 키가 있고 값이 비어있지 않은 경우
                _action_success = False
    except Exception:
        _action_success = False
        raise
    finally:
        _action_ms = round((_time.time() - _action_start) * 1000)
        try:
            from thread_context import append_tool_call
            append_tool_call(f"ibl:{node}:{action}", {"node": node, "action": action, "params": params},
                             _action_success, node=node, action=action, duration_ms=_action_ms)
        except Exception:
            pass
        try:
            from api_xray import push_xray_event
            push_xray_event("tool", {
                "node": node, "action": action,
                "success": _action_success, "ms": _action_ms,
                "agent": agent_id or "",
            })
        except Exception:
            pass
        # action_health 기록 (실사용 및 self_check 모두)
        try:
            from world_pulse_health import record_action_health
            from thread_context import is_health_check_mode
            _src = "self_check" if agent_id == "__self_check__" or is_health_check_mode() else "usage"
            record_action_health(node, action, _action_success, _action_ms, source=_src)
        except Exception:
            pass

    # 후처리 (postprocess): 액션 YAML에 정의된 전처리(예: compress=AI 노이즈 제거) 수행
    # 건너뛰는 경우:
    #  - 자가점검(__self_check__): AI 호출 비용 절감
    #  - params._raw=true: 앱·GUI 등 구조화 원본이 필요한 호출 (요약은 에이전트 소비용)
    postprocess = action_config.get("postprocess")
    _raw = bool((tool_input.get("params") or {}).get("_raw"))
    if postprocess and result is not None and agent_id != "__self_check__" and not _raw:
        result = _postprocess(result, action, postprocess)

    return result


# === 후처리 시스템 (Postprocessing) ===
# 액션의 YAML 정의에 postprocess 필드를 두어 결과를 전처리한다.
# 감각기관이 원시 데이터를 전처리해서 뇌에 보내는 것과 같은 원리.

_DEFAULT_COMPRESS_THRESHOLD = 1500
_DEFAULT_COMPRESS_PROMPT = "불필요한 메타데이터, 중복, 광고성 문구, 포맷팅 잔해를 제거하라. 실질적 정보는 모두 보존하라. URL은 보존하라."
_COMPRESS_SYSTEM_PROMPT = "너는 노이즈 제거기이다. 도구 출력에서 쓸모없는 부분만 걸러내고 실질적 정보는 모두 보존한다. 요약하거나 판단하지 마라."


def _postprocess(result: Any, action: str, config: dict) -> Any:
    """액션 결과를 후처리한다. config는 YAML의 postprocess 필드."""
    pp_type = config.get("type")
    if pp_type == "compress":
        return _pp_compress(result, action, config)
    else:
        print(f"[IBL] 알 수 없는 postprocess 유형: {pp_type} ({action})")
        return result


def _compress_text(text: str, action: str, config: dict) -> Any:
    """경량 AI로 텍스트 한 덩이의 노이즈를 제거한다. 실패 시 None."""
    prompt_instruction = config.get("prompt", _DEFAULT_COMPRESS_PROMPT)
    try:
        from consciousness_agent import lightweight_ai_call
        compressed = lightweight_ai_call(
            prompt=f"다음은 [{action}] 액션의 실행 결과이다. {prompt_instruction}\n\n{text}",
            system_prompt=_COMPRESS_SYSTEM_PROMPT,
            role="background"
        )
        if compressed:
            print(f"[IBL] postprocess:compress ({action}): {len(text)}자 → {len(compressed)}자")
            return compressed
    except Exception as e:
        print(f"[IBL] postprocess:compress 실패 ({action}): {e}")
    return None


def _pp_compress(result: Any, action: str, config: dict) -> Any:
    """경량 AI로 도구 출력의 '긴 자유 텍스트'만 압축한다 — 통화 보존이 원칙.

    압축은 통화(records/table/blocks) *아래/옆*에서만 일어나야 한다. 그래서:
      - dict면 config.field 가 가리키는 텍스트 필드 하나만 압축하고 나머지 구조는 보존.
        field 미지정 dict 는 손대지 않는다(통화 dict 를 통째로 문자열화 → 파괴하던 옛 버그 방지).
      - handler 가 format_json 으로 JSON '문자열'을 반환하면, field 지정 시 파싱→필드압축→재직렬화.
      - 구조 없는 bare 문자열만 통째로 압축(레거시, 통화 없음).
    """
    threshold = config.get("threshold", _DEFAULT_COMPRESS_THRESHOLD)
    field = config.get("field")

    # JSON 문자열(format_json 반환)이면 dict 로 파싱해 필드 단위 압축 시도
    parsed_from_str = False
    obj = result
    if isinstance(result, str) and field:
        try:
            obj = json.loads(result)
            parsed_from_str = isinstance(obj, dict)
        except (json.JSONDecodeError, ValueError):
            parsed_from_str = False

    # dict: 지정 필드만 압축, 통화/구조 보존
    if isinstance(obj, dict):
        if not field:
            return result  # 필드 미지정 — 통화 파괴 위험이라 손대지 않음
        text = obj.get(field)
        if not isinstance(text, str) or len(text) < threshold:
            return result
        compressed = _compress_text(text, action, config)
        if compressed is None:
            return result
        obj[field] = compressed
        return json.dumps(obj, ensure_ascii=False) if parsed_from_str else obj

    # bare 문자열(구조 없음) — 레거시 전체 압축
    if isinstance(result, str):
        if len(result) < threshold:
            return result
        return _compress_text(result, action, config) or result

    return result
