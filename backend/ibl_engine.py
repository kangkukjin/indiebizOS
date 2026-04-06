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
    """노드 정의 강제 리로드"""
    global _nodes
    _nodes = None
    _load_nodes_config()


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


def execute_ibl(tool_input: dict, project_path: str = ".", agent_id: str = None) -> Any:
    """
    IBL 노드 도구 실행

    Args:
        tool_input: {
            "action": "search",      # 필수: 액션 이름
            "params": {...},         # 파라미터
            ...기타 노드별 파라미터
        }
        project_path: 프로젝트 경로
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

    # default_input 병합: 액션에 정의된 기본값을 params에 적용 (사용자 값 우선)
    default_input = action_config.get("default_input")
    if default_input and isinstance(default_input, dict):
        for k, v in default_input.items():
            if k not in params:
                params[k] = v

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
            result = _route_handler(mapped_tool, params, project_path, agent_id)
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
            result = _route_driver(driver_type, node, action, params, project_path, driver_node=dn)
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
            _src = "self_check" if agent_id == "__self_check__" else "usage"
            record_action_health(node, action, _action_success, _action_ms, source=_src)
        except Exception:
            pass

    # 후처리 (postprocess): 액션 YAML에 정의된 전처리 수행
    # 자가점검 시에는 건너뜀 (AI 호출 비용 절감)
    postprocess = action_config.get("postprocess")
    if postprocess and result is not None and agent_id != "__self_check__":
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


def _pp_compress(result: Any, action: str, config: dict) -> Any:
    """경량 AI로 도구 출력을 압축한다."""
    # 문자열 변환
    if isinstance(result, dict):
        text = json.dumps(result, ensure_ascii=False)
    elif isinstance(result, str):
        text = result
    else:
        return result

    threshold = config.get("threshold", _DEFAULT_COMPRESS_THRESHOLD)
    if len(text) < threshold:
        return result

    prompt_instruction = config.get("prompt", _DEFAULT_COMPRESS_PROMPT)

    try:
        from consciousness_agent import lightweight_ai_call
        compressed = lightweight_ai_call(
            prompt=f"다음은 [{action}] 액션의 실행 결과이다. {prompt_instruction}\n\n{text}",
            system_prompt=_COMPRESS_SYSTEM_PROMPT
        )
        if compressed:
            print(f"[IBL] postprocess:compress ({action}): {len(text)}자 → {len(compressed)}자")
            return compressed
    except Exception as e:
        print(f"[IBL] postprocess:compress 실패 ({action}): {e}")

    return result
