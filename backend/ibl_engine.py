"""
ibl_engine.py - IBL 노드-액션 실행 엔진

IBL Phase 4의 핵심.
[node:action](target) { params } 모델을 파싱하고 적절한 백엔드로 라우팅합니다.

사용법:
    from ibl_engine import execute_ibl, list_ibl_nodes, list_actions

    # 노드 도구 실행
    result = execute_ibl({"action": "call", "target": "search_laws", "params": {"query": "임대차"}}, ".")

    # 노드 목록
    nodes = list_ibl_nodes()

    # 노드별 액션 목록
    actions = list_actions("api")
"""

import os
import json
import asyncio
import yaml
from pathlib import Path
from typing import Any, Dict, List, Optional


# === Phase 22: 구 노드명 → 새 노드명 역호환 매핑 ===
# AI가 이전 대화 이력이나 학습된 패턴으로 구 노드명을 사용할 때 자동 변환
_LEGACY_NODE_MAP = {
    # Phase 19-21 통합 (정보 노드 → informant → source)
    "finance": "source",
    "culture": "source",
    "study": "source",
    "legal": "source",
    "statistics": "source",
    "commerce": "source",
    "location": "source",
    "informant": "source",
    # Phase 20-21 통합 (데이터 노드 → librarian → source)
    "librarian": "source",
    "photo": "source",
    "blog": "source",
    "memory": "source",
    "health": "source",
    # Phase 22 통합 (기기 → interface)
    "browser": "interface",
    "android": "interface",
    "desktop": "interface",
    # Phase 22 통합 (미디어 → stream)
    "youtube": "stream",
    "radio": "stream",
    # Phase 22 리네임
    "orchestrator": "system",
    "creator": "forge",
    # Phase 20 통합 (기타)
    "webdev": "forge",
    "design": "forge",
    "user": "system",
    "workflow": "system",
    "automation": "system",
    "output": "system",
    "filesystem": "system",
}

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
        if tool_cfg.get("target_description"):
            action["target_description"] = tool_cfg["target_description"]

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


def _resolve_verb(node_config: dict, verb: str, params: dict,
                   target: str = "") -> tuple:
    """
    Phase 13: verbs 섹션에서 공통 동사 → 실제 액션으로 해석.

    3-tier resolution의 2단계:
      1단계: actions에서 정확 매칭 (이미 시도됨)
      2단계: verbs 섹션에서 동사 매핑 + type 파라미터로 분기 ← 여기
      3단계: 둘 다 없으면 에러

    Phase 22: target 기반 자동 라우팅 추가.
      AI가 [source:get]("us_price", "PLTR") 형태로 보내는 경우,
      target의 첫 토큰이 verb routes 키와 일치하면 자동 분기.

    Args:
        node_config: 노드 설정 (actions, verbs 포함)
        verb: 공통 동사 (search, get, list, create, delete 등)
        params: 사용자 파라미터 (type 키로 분기)
        target: 대상 문자열 (verb route 키 자동 감지용)

    Returns:
        (action_config, action_name, adjusted_target) 또는 (None, None, None)
    """
    verbs = node_config.get("verbs", {})
    verb_config = verbs.get(verb)
    if not verb_config:
        return None, None, None

    type_hint = params.get("type", "")
    routes = verb_config.get("routes", {})
    adjusted_target = None  # target 조정이 필요한 경우

    if type_hint and type_hint in routes:
        action_name = routes[type_hint]
    else:
        # Phase 22: target에서 verb route 키 자동 감지
        # 예: target="us_price", "PLTR" → route_key="us_price", new_target="PLTR"
        if target and not type_hint:
            # 쉼표로 분리: "us_price", "PLTR" → ["us_price", "PLTR"]
            parts = [p.strip().strip('"').strip("'") for p in target.split(",")]
            if len(parts) >= 2 and parts[0] in routes:
                action_name = routes[parts[0]]
                adjusted_target = ", ".join(parts[1:]).strip().strip('"').strip("'")
            elif len(parts) == 1 and parts[0] in routes:
                # target 자체가 route 키: [source:get]("price") → price 액션
                action_name = routes[parts[0]]
                adjusted_target = ""
            else:
                action_name = verb_config.get("default")
        else:
            action_name = verb_config.get("default")

    if not action_name:
        return None, None, None

    action_config = node_config.get("actions", {}).get(action_name)
    return (action_config, action_name, adjusted_target) if action_config else (None, None, None)


def execute_ibl(tool_input: dict, project_path: str = ".", agent_id: str = None) -> Any:
    """
    IBL 노드 도구 실행

    Args:
        tool_input: {
            "action": "call",        # 필수: 액션 이름
            "target": "search_laws", # 대상 (액션에 따라 다름)
            "params": {...},         # 추가 파라미터
            ...기타 노드별 파라미터
        }
        project_path: 프로젝트 경로
        agent_id: 에이전트 ID

    Returns:
        실행 결과
    """
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
                "example": f'[{node}:{actions[0]}]("검색어")' if actions else None,
                "hint": f"총 {len(actions)}개 액션 사용 가능"
            }
        return {"error": "action 파라미터가 필요합니다.", "available_nodes": [d["node"] for d in list_ibl_nodes()]}

    # 노드는 tool_name에서 결정됨 (ibl_api -> api, ibl_web -> web 등)
    # 이 함수는 노드가 이미 결정된 상태로 호출됨
    node = tool_input.get("_node")
    if not node:
        return {"error": "_node이 설정되지 않았습니다. handler.py를 통해 호출해주세요."}

    reg = _load_nodes_config()
    # Phase 22: 구 노드명 역호환 매핑
    node = _LEGACY_NODE_MAP.get(node, node)
    node_config = reg.get("nodes", {}).get(node)
    if not node_config:
        return {"error": f"알 수 없는 노드: {node}", "available_nodes": [d["node"] for d in list_ibl_nodes()]}

    action_config = node_config.get("actions", {}).get(action)
    if not action_config:
        # Phase 13/22: verb resolution - 공통 동사로 액션 매핑 (target 기반 자동 라우팅 포함)
        params = tool_input.get("params", {})
        raw_target = tool_input.get("target", "")
        action_config, resolved_action, adj_target = _resolve_verb(
            node_config, action, params, target=raw_target)
        if action_config:
            action = resolved_action
            if adj_target is not None:
                tool_input["target"] = adj_target  # target 조정 반영
        else:
            available = list(node_config.get("actions", {}).keys())
            verbs = list(node_config.get("verbs", {}).keys())
            err = {"error": f"노드 '{node}'에 '{action}' 액션/동사가 없습니다.",
                   "available_actions": available}
            if verbs:
                err["available_verbs"] = verbs
            return err

    router = action_config.get("router")
    target = tool_input.get("target", "")
    params = tool_input.get("params", {})

    # 라우터별 실행
    if router == "api_engine":
        mapped_tool = action_config.get("tool")
        yaml_target_key = action_config.get("target_key")
        return _route_api_engine(action, target, params, project_path,
                                 mapped_tool=mapped_tool, target_key=yaml_target_key)
    elif router == "handler":
        mapped_tool = action_config.get("tool")
        yaml_target_key = action_config.get("target_key")
        guide_path = _resolve_guide(
            action_config.get("guide"),
            node_config.get("guide"),
        )
        return _route_handler(mapped_tool, target, params, project_path, agent_id,
                              yaml_target_key=yaml_target_key, guide_path=guide_path)
    elif router == "system":
        func_name = action_config.get("func")
        return _route_system(func_name, target, params, project_path)
    elif router == "workflow_engine":
        from workflow_engine import execute_workflow_action
        return execute_workflow_action(action, target, params, project_path)
    elif router == "channel_engine":
        from channel_engine import execute_channel_action
        return execute_channel_action(action, target, params, project_path)
    elif router == "web_collector":
        from web_collector import execute_web_collect_action
        return execute_web_collect_action(action, target, params, project_path)
    elif router == "event_engine":
        from event_engine import execute_event
        return execute_event(action, target, params, project_path)
    elif router == "driver":
        driver_type = action_config.get("driver", "sqlite")
        dn = action_config.get("driver_node")  # Phase 22: 하위 핸들러 지정
        return _route_driver(driver_type, node, action, target, params, project_path, driver_node=dn)
    elif router == "stub":
        phase = action_config.get("phase", "?")
        return {
            "error": f"[{node}:{action}]은 Phase {phase}에서 구현 예정입니다.",
            "node": node,
            "action": action,
            "status": "not_implemented",
        }
    else:
        return {"error": f"알 수 없는 라우터: {router}"}


# === 라우터 구현 ===

def _route_api_engine(action: str, target: str, params: dict, project_path: str,
                      mapped_tool: str = None, target_key: str = None) -> Any:
    """API 엔진으로 라우팅

    mapped_tool이 지정되면 해당 api_registry 도구를 직접 실행합니다.
    이를 통해 노드 액션(informant:search 등)이 handler.py 없이
    api_registry.yaml + api_engine.py transform으로 직접 동작합니다.
    """
    from api_engine import execute_tool as api_execute, list_registry_tools, is_registry_tool

    # 1) 노드 액션에서 직접 매핑된 api_registry 도구 실행
    if mapped_tool:
        if not is_registry_tool(mapped_tool):
            return {"error": f"api_registry에 등록되지 않은 도구: {mapped_tool}"}
        # target → params 병합 (handler 라우터와 동일한 방식)
        merged_params = dict(params)
        if target and target_key and target_key not in merged_params:
            merged_params[target_key] = target
        return api_execute(mapped_tool, merged_params, project_path)

    # 2) 기존 system:call 등 범용 api_engine 액션
    if action == "list":
        tools = list_registry_tools()
        return {"node": "api", "action": "list", "tools": tools, "count": len(tools)}

    if action == "call":
        if not target:
            tools = list_registry_tools()
            return {
                "error": "target(도구 이름)이 필요합니다.",
                "available_tools": tools,
            }
        if not is_registry_tool(target):
            tools = list_registry_tools()
            return {
                "error": f"레지스트리에 등록되지 않은 도구: {target}",
                "available_tools": tools,
            }
        return api_execute(target, params, project_path)

    return {"error": f"api 노드에 '{action}' 액션이 없습니다."}


def _route_handler(mapped_tool: str, target: str, params: dict,
                   project_path: str, agent_id: str = None,
                   yaml_target_key: str = None, guide_path: str = None) -> Any:
    """handler.py로 위임"""
    from tool_loader import load_tool_handler

    if not mapped_tool:
        return {"error": "매핑된 도구가 없습니다."}

    handler = load_tool_handler(mapped_tool)
    if not handler or not hasattr(handler, "execute"):
        return {"error": f"도구 핸들러를 찾을 수 없습니다: {mapped_tool}"}

    # target을 params에 병합 (도구별로 적절한 키에 매핑)
    merged_params = dict(params)
    if target:
        # Phase 12: YAML target_key 우선, fallback으로 _get_target_key
        target_key = yaml_target_key or _get_target_key(mapped_tool)
        if target_key and target_key not in merged_params:
            merged_params[target_key] = target

    # handler.execute 호출
    import inspect
    sig = inspect.signature(handler.execute)
    if "agent_id" in sig.parameters:
        result = handler.execute(mapped_tool, merged_params, project_path, agent_id)
    else:
        result = handler.execute(mapped_tool, merged_params, project_path)

    # async 핸들러 지원
    if asyncio.iscoroutine(result):
        try:
            # 현재 스레드에 실행 중인 이벤트 루프가 있는지 안전하게 확인
            try:
                loop = asyncio.get_running_loop()
            except RuntimeError:
                loop = None

            if loop and loop.is_running():
                # 이미 실행 중인 루프가 있으면 별도 스레드에서 실행
                import concurrent.futures
                with concurrent.futures.ThreadPoolExecutor() as pool:
                    result = pool.submit(asyncio.run, result).result()
            else:
                # 실행 중인 루프가 없으면 새로 생성하여 실행
                result = asyncio.run(result)
        except RuntimeError as e:
            # 최종 폴백: 새 이벤트 루프 생성
            try:
                new_loop = asyncio.new_event_loop()
                asyncio.set_event_loop(new_loop)
                try:
                    result = new_loop.run_until_complete(result)
                finally:
                    new_loop.close()
            except Exception as e2:
                print(f"[IBL] async 핸들러 실행 실패: {e} → {e2}")
                result = json.dumps({"success": False, "error": f"async 실행 오류: {str(e2)}"})

    # Phase 12: 가이드 메타데이터 첨부
    # YAML guide 필드 우선, 없으면 tool.json guide_file에서 fallback
    if not guide_path:
        from tool_loader import get_tool_guide_path
        guide_path = get_tool_guide_path(mapped_tool)
    if guide_path:
        result = _attach_guide(result, guide_path)

    return result


def _get_target_key(tool_name: str) -> Optional[str]:
    """도구별 target이 매핑될 파라미터 키"""
    _TARGET_KEYS = {
        # web
        "ddgs_search": "query",
        "crawl_website": "url",
        "google_news_search": "query",
        "browser_navigate": "url",
        # fs
        "read_file": "path",
        "write_file": "path",
        "list_directory": "path",
        "glob_files": "pattern",
        "grep_files": "pattern",
        "execute_python": "code",
        "execute_node": "code",
        "run_command": "command",
        # media
        "create_slides": "topic",
        "create_html_video": "topic",
        "line_chart": "title",
        "generate_ai_image": "prompt",
        "compose_and_export": "title",
        "download_youtube_music": "url",
        # youtube
        "get_youtube_info": "url",
        "get_youtube_transcript": "url",
        "list_available_transcripts": "url",
        "summarize_youtube": "url",
        "play_youtube": "query",
        "add_to_queue": "query",
        # informant (finance)
        "yf_stock_price": "symbol",
        "yf_stock_info": "symbol",
        "yf_search_stock": "query",
        "kr_company_info": "corp_name",
        "us_company_profile": "symbol",
        "kr_financial_statements": "corp_name",
        "us_financial_statements": "symbol",
        "kr_disclosures": "corp_name",
        "us_sec_filings": "symbol",
        "company_news": "symbol",
        "yf_stock_news": "symbol",
        "earnings_calendar": "symbol",
        "crypto_price": "coin_id",
        "kr_stock_price": "symbol",
        "us_stock_price": "symbol",
        # informant (location)
        "get_api_ninjas_data": "endpoint",
        "search_restaurants": "query",
        "kakao_navigation": "origin",
        "show_location_map": "query",
        "amadeus_travel_search": "endpoint",
        # shopping
        "search_shopping": "query",
        # web (Phase 3)
        "generate_newspaper": "keywords",
        # android
        "android_device_info": "device_id",
        "android_system_status": "device_id",
        "android_send_sms": "phone_number",
        "android_search_sms": "query",
        "android_make_call": "phone_number",
        "android_search_contacts": "query",
        "android_push_file": "local_path",
        "android_pull_file": "remote_path",
        "android_ui_type_text": "text",
        "android_ui_find_and_tap": "query",
        "android_ui_open_app": "package_name",
        "android_ui_press_key": "keycode",
        # browser
        "browser_click": "ref",
        "browser_type": "ref",
        "browser_evaluate": "expression",
        "browser_press_key": "key",
        "browser_tab_switch": "tab_id",
        # radio
        "search_radio": "name",
        "get_korean_radio": "broadcaster",
        "play_radio": "station_id",
        "set_radio_volume": "volume",
        "remove_radio_favorite": "name",
        # cctv
        "get_cctv_by_name": "keyword",
        "open_cctv": "name",
        "capture_cctv": "url",
        # realestate
        "apt_trade_price": "region_code",
        "apt_rent_price": "region_code",
        "house_trade_price": "region_code",
        "house_rent_price": "region_code",
        "get_region_codes": "city",
        # startup
        "search_kstartup": "keyword",
        "search_mss_biz": "keyword",
        # informant (culture)
        "kopis_quick_search": "keyword",
        "kopis_get_performance": "performance_id",
        "kopis_search_facilities": "keyword",
        "library_quick_search": "keyword",
        "library_get_book_detail": "isbn13",
        "library_search_libraries": "name",
        "kcisa_quick_search": "keyword",
        "kcisa_get_event_detail": "seq",
        # hosting
        "cf_api": "endpoint",
        # desktop (computer-use)
        "computer_type": "text",
        "computer_key": "key",
        # informant (study)
        "search_openalex": "query",
        "search_arxiv": "query",
        "download_arxiv_pdf": "arxiv_id",
        "search_semantic_scholar": "query",
        "search_google_scholar": "query",
        "search_pubmed": "query",
        "download_pubmed_pdf": "pmcid",
        "search_guardian": "query",
        "fetch_world_bank_data": "indicator",
        "search_books": "query",
        # webbuilder
        "site_registry": "site_id",
        "site_snapshot": "site_id",
        "site_live_check": "site_id",
        "create_project": "name",
        "add_component": "project_path",
        "create_page": "project_path",
        "edit_styles": "project_path",
        "preview_site": "project_path",
        "build_site": "project_path",
        "deploy_vercel": "project_path",
        "fetch_component": "component",
        # storage (pc-manager)
        "scan_storage": "path",
        "query_storage": "search_term",
        "annotate_folder": "folder_path",
        "open_file_explorer": "path",
        # viz (visualization)
        "bar_chart": "title",
        "candlestick_chart": "title",
        "pie_chart": "title",
        "scatter_plot": "title",
        "heatmap": "title",
        "multi_chart": "title",
        # media (remotion)
        "create_remotion_video": "composition_code",
    }
    return _TARGET_KEYS.get(tool_name)


def _route_system(func_name: str, target: str, params: dict, project_path: str) -> Any:
    """system_tools 내장 함수 직접 호출"""
    if func_name == "send_notification":
        from system_tools import execute_send_notification
        merged = dict(params)
        if target and "message" not in merged:
            merged["message"] = target
        return execute_send_notification(merged, project_path)

    elif func_name == "call_agent":
        from system_tools import execute_call_agent
        merged = dict(params)
        if target and "agent_id" not in merged:
            merged["agent_id"] = target
        return execute_call_agent(merged, project_path)

    elif func_name == "delegate_workflow":
        return _delegate_workflow(target, params, project_path)

    elif func_name == "discover":
        return _discover_nodes(target, params)

    # Phase 11: 에이전트 노드
    elif func_name == "agent_ask":
        return _agent_ask(target, params, project_path)
    elif func_name == "agent_ask_sync":
        return _agent_ask_sync(target, params, project_path)
    elif func_name == "agent_list":
        return _agent_list(params)
    elif func_name == "agent_info":
        return _agent_info(target)

    # Phase 13: 출력 노드
    elif func_name == "output_gui":
        return _output_gui(target, params, project_path)
    elif func_name == "output_file":
        return _output_file(target, params, project_path)
    elif func_name == "output_open":
        return _output_open(target, params)
    elif func_name == "output_clipboard":
        return _output_clipboard(target, params)
    elif func_name == "output_download":
        return _output_download(target, params, project_path)

    # Phase 17→19: user 노드 함수 (orchestrator로 통합됨, func_name은 유지)
    elif func_name == "ask_user_question":
        from system_tools import execute_ask_user_question
        merged = dict(params)
        if target and "question" not in merged:
            # 단일 질문 shortcut
            merged.setdefault("questions", [{"question": target, "header": "질문", "options": []}])
        return execute_ask_user_question(merged, project_path)

    elif func_name == "request_user_approval":
        from system_tools import execute_request_user_approval
        merged = dict(params)
        if target and "description" not in merged:
            merged["description"] = target
        return execute_request_user_approval(merged, project_path)

    elif func_name == "todo_write":
        from system_tools import execute_todo_write
        merged = dict(params)
        return execute_todo_write(merged, project_path)

    # Phase 17: 시스템 AI 전용 함수 (프로젝트 간 위임)
    elif func_name == "list_project_agents":
        from api_system_ai import _execute_list_project_agents
        return _execute_list_project_agents(params)

    elif func_name == "call_project_agent":
        from api_system_ai import _execute_call_project_agent
        merged = dict(params)
        if target and "agent_id" not in merged:
            merged["agent_id"] = target
        return _execute_call_project_agent(merged)

    elif func_name == "manage_events":
        from api_system_ai import _execute_manage_events
        return _execute_manage_events(params)

    elif func_name == "list_switches":
        from api_system_ai import _execute_list_switches
        return _execute_list_switches(params)

    return {"error": f"알 수 없는 시스템 함수: {func_name}"}


def _discover_nodes(query: str, params: dict) -> Any:
    """노드 디스커버리 (Phase 10)

    키워드로 적합한 노드/액션을 자동 탐색.
    "이 작업을 할 수 있는 노드가 뭐야?"를 해결.
    """
    from node_registry import discover, list_nodes, get_node, node_summary

    if not query:
        # 쿼리 없으면 전체 노드 요약 반환
        return node_summary()

    # discover 실행
    limit = params.get("limit", 10)
    results = discover(query, limit=limit)

    if not results:
        return {
            "query": query,
            "results": [],
            "message": f"'{query}'에 매칭되는 노드를 찾을 수 없습니다.",
            "total_nodes": len(list_nodes()),
        }

    return {
        "query": query,
        "results": results,
        "count": len(results),
        "best_match": results[0]["suggestion"],
    }


def _search_guide(query: str, params: dict) -> Any:
    """가이드 DB 검색 — 복잡한 작업 전에 워크플로우/레시피 확인

    DB(guide_db.json)에서 키워드 매칭 후 data/guides/ 폴더에서 파일 읽기.
    params.read=true (기본) → 첫 번째 매칭 가이드 내용까지 반환
    params.read=false → 목록만 반환
    """
    import json as _json
    from pathlib import Path as _Path

    data_dir = _Path(__file__).parent.parent / "data"
    guide_db_path = data_dir / "guide_db.json"

    if not guide_db_path.exists():
        return {"error": "guide_db.json이 없습니다."}

    with open(guide_db_path, 'r', encoding='utf-8') as f:
        db = _json.load(f)

    guides = db.get("guides", [])

    if not query:
        return {
            "guides": [{"id": g["id"], "name": g["name"], "description": g["description"]} for g in guides],
            "count": len(guides),
            "message": "가이드 전체 목록입니다. 키워드로 검색하세요.",
        }

    # 키워드 매칭
    query_lower = query.lower()
    query_words = query_lower.split()

    scored = []
    for g in guides:
        score = 0
        search_text = " ".join([
            g.get("name", ""),
            g.get("description", ""),
            " ".join(g.get("keywords", [])),
        ]).lower()

        for word in query_words:
            if word in search_text:
                score += 1
            if word in [kw.lower() for kw in g.get("keywords", [])]:
                score += 2

        if score > 0:
            scored.append((score, g))

    scored.sort(key=lambda x: x[0], reverse=True)

    if not scored:
        return {
            "query": query,
            "results": [],
            "message": f"'{query}'에 매칭되는 가이드가 없습니다.",
        }

    results = [{"id": g["id"], "name": g["name"], "description": g["description"], "score": s} for s, g in scored[:5]]

    response = {
        "query": query,
        "results": results,
        "count": len(results),
        "best_match": results[0]["name"],
    }

    # 기본적으로 첫 번째 매칭 가이드 파일을 읽어서 반환
    read_content = params.get("read", True)
    if read_content and scored:
        best = scored[0][1]
        guide_file = best.get("file", "")
        if guide_file:
            guide_path = data_dir / "guides" / guide_file
            if guide_path.exists():
                try:
                    response["guide_content"] = guide_path.read_text(encoding='utf-8')
                    response["guide_name"] = best["name"]
                except Exception:
                    pass

    return response


def _delegate_workflow(target: str, params: dict, project_path: str) -> Any:
    """다른 에이전트에게 IBL 파이프라인을 위임

    Args:
        target: 대상 에이전트 이름 또는 ID
        params: {"steps": [...], "message": "..."} 파이프라인 정의
    """
    if not target:
        return {"error": "target(대상 에이전트)이 필요합니다."}

    steps = params.get("steps", [])
    if not steps:
        return {"error": "params.steps가 필요합니다. 파이프라인 단계를 정의해주세요."}

    # 파이프라인 steps를 JSON으로 직렬화
    steps_json = json.dumps(steps, ensure_ascii=False)
    user_message = params.get("message", "")

    # 위임 메시지 구성
    delegation_msg = f"""다음 IBL 파이프라인을 실행해주세요.

```json
{steps_json}
```

execute_ibl(node="system", action="run_pipeline", params={{"steps": {steps_json}}}) 로 실행하세요."""

    if user_message:
        delegation_msg = f"{user_message}\n\n{delegation_msg}"

    # call_agent으로 위임
    from system_tools import execute_call_agent
    return execute_call_agent(
        {"agent_id": target, "message": delegation_msg},
        project_path
    )


def _agent_ask(target: str, params: dict, project_path: str) -> Any:
    """에이전트에게 질문/위임 [agent:ask](투자/투자컨설팅) (Phase 11)"""
    if not target:
        return {"error": "target(프로젝트/에이전트이름)이 필요합니다."}

    # "프로젝트/에이전트이름" 파싱
    parts = target.split("/", 1)
    if len(parts) == 2:
        project_id, agent_name = parts
    else:
        agent_name = parts[0]
        project_id = Path(project_path).name

    message = params.get("message", params.get("query", ""))
    if not message:
        return {"error": "params.message가 필요합니다."}

    from system_tools import execute_call_agent
    env_path = os.environ.get("INDIEBIZ_BASE_PATH")
    base = Path(env_path) if env_path else Path(__file__).parent.parent
    target_project_path = str(base / "projects" / project_id)
    return execute_call_agent({"agent_id": agent_name, "message": message}, target_project_path)


def _agent_ask_sync(target: str, params: dict, project_path: str) -> Any:
    """에이전트에게 동기 질문 — 응답을 기다려서 반환 (파이프라인용)

    비동기 agent_ask와 달리, 임시 AI 에이전트를 생성하여
    메시지를 처리하고 결과 텍스트를 직접 반환합니다.

    사용: [system:agent_ask_sync]("프로젝트/에이전트") {message: "분석해줘"}
    파이프라인: [source:search_blog]("AI") >> [system:agent_ask_sync]("컨텐츠/컨텐츠") {message: "요약해줘"}
    """
    if not target:
        return {"error": "target(프로젝트/에이전트이름)이 필요합니다."}

    # "프로젝트/에이전트이름" 파싱
    parts_split = target.split("/", 1)
    if len(parts_split) == 2:
        project_id, agent_name = parts_split
    else:
        agent_name = parts_split[0]
        project_id = Path(project_path).name

    message = params.get("message", params.get("query", ""))
    if not message:
        return {"error": "params.message가 필요합니다."}

    # _prev_result가 있으면 message에 첨부
    prev = params.get("_prev_result", "")
    if prev and prev not in message:
        message = f"{message}\n\n--- 이전 단계 결과 ---\n{prev}"

    # agents.yaml에서 대상 에이전트 설정 로드
    env_path = os.environ.get("INDIEBIZ_BASE_PATH")
    base = Path(env_path) if env_path else Path(__file__).parent.parent
    target_project_path = base / "projects" / project_id
    agents_yaml = target_project_path / "agents.yaml"

    if not agents_yaml.exists():
        return {"error": f"프로젝트 '{project_id}'를 찾을 수 없습니다."}

    try:
        import yaml as _yaml
        data = _yaml.safe_load(agents_yaml.read_text(encoding='utf-8'))
    except Exception as e:
        return {"error": f"agents.yaml 로드 실패: {e}"}

    # 에이전트 찾기
    agents = data.get("agents", [])
    agent_config = None
    for ag in agents:
        if ag.get("name") == agent_name or ag.get("id") == agent_name:
            agent_config = ag
            break

    if not agent_config:
        available = [ag.get("name", ag.get("id", "?")) for ag in agents]
        return {"error": f"에이전트 '{agent_name}'을 찾을 수 없습니다.", "available": available}

    ai_config = agent_config.get("ai", {})
    if not ai_config.get("api_key"):
        return {"error": f"에이전트 '{agent_name}'의 API 키가 설정되지 않았습니다."}

    # 임시 AI 에이전트 생성 + 동기 호출
    try:
        from ai_agent import AIAgent
        from prompt_builder import build_agent_prompt
        from ibl_access import build_environment
        from tool_loader import load_tool_schema

        # IBL 도구 로드
        ibl_schema = load_tool_schema("execute_ibl")
        tools = [ibl_schema] if ibl_schema else []

        # 프롬프트 구성
        allowed_nodes = agent_config.get("allowed_nodes")
        system_prompt = build_agent_prompt(
            agent_name=agent_name,
            role=agent_config.get("role_description", ""),
            agent_count=1,
            ibl_only=True,
            allowed_nodes=allowed_nodes,
            project_path=str(target_project_path),
            agent_id=agent_config.get("id", ""),
        )

        agent = AIAgent(
            ai_config=ai_config,
            system_prompt=system_prompt,
            agent_name=agent_name,
            tools=tools,
        )

        # 동기 호출 — AI가 응답할 때까지 대기
        response = agent.process_message_with_history(
            message_content=message,
            from_email="pipeline@system",
            history=[],
        )

        return {
            "success": True,
            "agent": agent_name,
            "project": project_id,
            "response": response,
            "sync": True,
        }

    except Exception as e:
        import traceback
        traceback.print_exc()
        return {"error": f"동기 에이전트 호출 실패: {e}"}


def _agent_list(params: dict) -> Any:
    """에이전트 노드 목록 [agent:list] (Phase 11)"""
    from node_registry import list_nodes
    nodes = list_nodes(include_agents=True)
    agent_nodes = [n for n in nodes if n["type"] == "agent"]

    # 프로젝트 필터
    project_filter = params.get("project")
    if project_filter:
        agent_nodes = [n for n in agent_nodes if n["project_id"] == project_filter]

    return {
        "agents": [{
            "id": n["id"],
            "name": n["agent_name"],
            "project": n["project_id"],
            "description": n["description"],
            "capabilities": n.get("capabilities", []),
            "running": n.get("running", False),
        } for n in agent_nodes],
        "count": len(agent_nodes),
    }


def _agent_info(target: str) -> Any:
    """에이전트 상세 정보 [agent:info](투자/투자컨설팅) (Phase 11)"""
    from node_registry import list_nodes
    nodes = list_nodes(include_agents=True)
    for n in nodes:
        if n["type"] == "agent" and n["id"] == target:
            return n
    return {"error": f"에이전트 '{target}'을 찾을 수 없습니다."}


def _route_driver(driver_type: str, node: str, action: str,
                  target: str, params: dict, project_path: str,
                  driver_node: str = None) -> Any:
    """드라이버 계층으로 라우팅 (Phase 7)

    드라이버는 프로토콜(SQLite, ADB, CDP 등)을 감추고
    통일된 execute(action, target, params) 인터페이스를 제공한다.

    Phase 22: driver_node 파라미터 추가.
    6-Node 통합으로 source/messenger 등 상위 노드가 photo/health/blog/contact/memory
    등의 하위 핸들러를 포함하게 됨. driver_node가 지정되면 실제 드라이버 핸들러명으로 사용.
    """
    # 드라이버 인스턴스 가져오기
    driver_registry = {
        "sqlite": ("drivers.sqlite_driver", "get_driver"),
        # 향후 확장:
        # "adb": ("drivers.adb_driver", "get_driver"),
        # "cdp": ("drivers.cdp_driver", "get_driver"),
        # "stream": ("drivers.stream_driver", "get_driver"),
    }

    entry = driver_registry.get(driver_type)
    if not entry:
        return {"error": f"알 수 없는 드라이버: {driver_type}"}

    module_path, factory_name = entry
    try:
        import importlib
        mod = importlib.import_module(module_path)
        get_driver = getattr(mod, factory_name)
        driver = get_driver()
    except Exception as e:
        return {"error": f"드라이버 로드 실패 ({driver_type}): {str(e)}"}

    # 노드 정보를 params에 전달 (driver_node 우선, 없으면 node)
    params["_node"] = driver_node or node
    if project_path:
        params["project_path"] = project_path

    return driver.execute(action, target, params)


# === Phase 12: 가이드 해결 및 첨부 ===

def _resolve_guide(*candidates) -> Optional[str]:
    """후보 중 첫 번째 유효한 가이드 경로 반환 (action > source > node)"""
    env_path = os.environ.get("INDIEBIZ_BASE_PATH")
    base = Path(env_path) if env_path else Path(__file__).parent.parent
    packages = base / "data" / "packages" / "installed" / "tools"
    for g in candidates:
        if g:
            full = packages / g
            if full.exists():
                return str(full)
    return None


def _attach_guide(result: Any, guide_path: str) -> Any:
    """결과에 가이드 메타데이터 첨부 (_ibl_guide 필드)"""
    if not guide_path:
        return result
    if isinstance(result, dict):
        result["_ibl_guide"] = guide_path
    elif isinstance(result, str):
        # str 결과는 dict로 변환하여 가이드 첨부
        try:
            parsed = json.loads(result)
            if isinstance(parsed, dict):
                parsed["_ibl_guide"] = guide_path
                return parsed
        except (json.JSONDecodeError, TypeError):
            pass
        # JSON 파싱 실패 시 dict 래핑
        return {"content": result, "_ibl_guide": guide_path}
    return result


# === Phase 12: 노드 타입 라우팅 ===

_nodes_cache: Optional[Dict] = None


def _load_nodes() -> Dict:
    """nodes: 섹션 로드 (캐싱)"""
    global _nodes_cache
    if _nodes_cache is not None:
        return _nodes_cache
    data = _load_nodes_config()
    _nodes_cache = data.get("nodes", {})
    return _nodes_cache


def _execute_node(node_type: str, tool_input: dict, project_path: str, agent_id: str) -> Any:
    """노드 타입별 실행 분기"""
    nodes = _load_nodes()
    node_config = nodes.get(node_type)
    if not node_config:
        return {"error": f"알 수 없는 노드: {node_type}", "available": list(nodes.keys())}

    config_type = node_config.get("type")
    if config_type == "info":
        return _execute_info_node(node_config, tool_input, project_path, agent_id)
    elif config_type == "store":
        return _execute_store_node(node_config, tool_input, project_path, agent_id)
    elif config_type == "exec":
        return _execute_exec_node(node_config, tool_input, project_path, agent_id)
    elif config_type == "output":
        return _execute_output_node(node_config, tool_input, project_path)
    return {"error": f"알 수 없는 노드 타입: {config_type}"}


def _execute_info_node(node_config, tool_input, project_path, agent_id):
    """info 타입 노드 실행 (레거시, 현재 미사용 - 7개 정보 노드가 informant로 통합됨)"""
    source = tool_input.get("source")
    if not source:
        sources = node_config.get("sources", {})
        return {
            "error": "source 파라미터가 필요합니다.",
            "sources": {k: v.get("description", "") for k, v in sources.items()},
        }

    source_config = node_config.get("sources", {}).get(source)
    if not source_config:
        return {
            "error": f"알 수 없는 source: {source}",
            "sources": list(node_config.get("sources", {}).keys()),
        }

    action = tool_input.get("action")
    actions = source_config.get("actions", {})
    action_config = actions.get(action)
    if not action_config:
        return {
            "error": f"source '{source}'에 '{action}' 액션이 없습니다.",
            "actions": list(actions.keys()),
        }

    target = tool_input.get("target", "")
    params = tool_input.get("params", {})
    guide_path = _resolve_guide(
        action_config.get("guide"),
        source_config.get("guide"),
        node_config.get("guide"),
    )
    return _route_by_config(action_config, target, params, source, action,
                            project_path, agent_id, guide_path)


def _execute_store_node(node_config, tool_input, project_path, agent_id):
    """store 노드 실행: ibl_store(store='health', action='summary')"""
    store = tool_input.get("store")
    if not store:
        stores = node_config.get("stores", {})
        return {
            "error": "store 파라미터가 필요합니다.",
            "stores": {k: v.get("description", "") for k, v in stores.items()},
        }

    store_config = node_config.get("stores", {}).get(store)
    if not store_config:
        return {
            "error": f"알 수 없는 store: {store}",
            "stores": list(node_config.get("stores", {}).keys()),
        }

    action = tool_input.get("action")
    actions = store_config.get("actions", {})
    action_config = actions.get(action)
    if not action_config:
        return {
            "error": f"store '{store}'에 '{action}' 액션이 없습니다.",
            "actions": list(actions.keys()),
        }

    target = tool_input.get("target", "")
    params = tool_input.get("params", {})
    guide_path = _resolve_guide(
        action_config.get("guide"),
        store_config.get("guide"),
        node_config.get("guide"),
    )

    router = action_config.get("router")
    if router == "driver":
        driver_type = action_config.get("driver", "sqlite")
        dn = action_config.get("driver_node")  # Phase 22: 하위 핸들러 지정
        result = _route_driver(driver_type, store, action, target, params, project_path, driver_node=dn)
        return _attach_guide(result, guide_path) if guide_path else result

    return _route_by_config(action_config, target, params, store, action,
                            project_path, agent_id, guide_path)


def _execute_exec_node(node_config, tool_input, project_path, agent_id):
    """exec 노드 실행: ibl_exec(action='python', target='print(1+1)')"""
    action = tool_input.get("action")
    if not action:
        executors = list(node_config.get("executors", {}).keys())
        programs = list(node_config.get("programs", {}).keys())
        return {
            "error": "action 파라미터가 필요합니다.",
            "executors": executors,
            "programs": programs,
        }

    target = tool_input.get("target", "")
    params = tool_input.get("params", {})

    # executors (python, node, shell)
    executors = node_config.get("executors", {})
    if action in executors:
        config = executors[action]
        guide_path = _resolve_guide(config.get("guide"), node_config.get("guide"))
        return _route_by_config(config, target, params, "exec", action,
                                project_path, agent_id, guide_path)

    # programs (remotion, video, slides, image, music)
    programs = node_config.get("programs", {})
    if action in programs:
        config = programs[action]
        guide_path = _resolve_guide(config.get("guide"), node_config.get("guide"))
        return _route_by_config(config, target, params, "exec", action,
                                project_path, agent_id, guide_path)

    available = list(executors.keys()) + list(programs.keys())
    return {"error": f"알 수 없는 exec 액션: {action}", "available": available}


# ============================================================
# Phase 13: 출력 노드 함수들
# ============================================================

def _output_gui(target: str, params: dict, project_path: str) -> Any:
    """UI에 결과를 HTML/카드/테이블로 표시"""
    content = params.get("content", target or "")
    format_type = params.get("format", "html")  # html, card, table, markdown
    title = params.get("title", target or "결과")

    result = {
        "type": "gui_output",
        "title": title,
        "format": format_type,
        "content": content,
    }

    # WebSocket으로 프론트엔드에 전송
    try:
        from websocket_manager import broadcast_message
        import asyncio
        msg = {"type": "ibl_output", "data": result}
        loop = asyncio.get_event_loop()
        if loop.is_running():
            asyncio.ensure_future(broadcast_message(msg))
        else:
            loop.run_until_complete(broadcast_message(msg))
    except Exception:
        pass

    return {"ok": True, "output": result}


def _output_file(target: str, params: dict, project_path: str) -> Any:
    """결과를 파일로 저장"""
    if not target:
        return {"error": "target(파일 경로)이 필요합니다."}

    content = params.get("content", "")
    encoding = params.get("encoding", "utf-8")

    # 상대경로면 outputs/ 폴더 기준
    file_path = target
    if not os.path.isabs(file_path):
        base = os.environ.get("INDIEBIZ_ROOT", os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        outputs_dir = os.path.join(base, "outputs")
        os.makedirs(outputs_dir, exist_ok=True)
        file_path = os.path.join(outputs_dir, file_path)

    os.makedirs(os.path.dirname(file_path), exist_ok=True)

    with open(file_path, "w", encoding=encoding) as f:
        if isinstance(content, (dict, list)):
            json.dump(content, f, ensure_ascii=False, indent=2)
        else:
            f.write(str(content))

    return {"ok": True, "path": file_path, "size": os.path.getsize(file_path)}


def _output_open(target: str, params: dict) -> Any:
    """URL을 브라우저로, 파일을 Finder로 열기"""
    if not target:
        return {"error": "target(URL 또는 파일 경로)이 필요합니다."}

    import subprocess
    import platform

    if target.startswith("http://") or target.startswith("https://"):
        # URL → 브라우저
        if platform.system() == "Darwin":
            subprocess.Popen(["open", target])
        elif platform.system() == "Windows":
            subprocess.Popen(["start", target], shell=True)
        else:
            subprocess.Popen(["xdg-open", target])
        return {"ok": True, "opened": target, "type": "url"}
    else:
        # 파일/폴더 → Finder/Explorer
        if platform.system() == "Darwin":
            subprocess.Popen(["open", target])
        elif platform.system() == "Windows":
            subprocess.Popen(["explorer", target])
        else:
            subprocess.Popen(["xdg-open", target])
        return {"ok": True, "opened": target, "type": "file"}


def _output_clipboard(target: str, params: dict) -> Any:
    """결과를 클립보드에 복사"""
    content = params.get("content", target or "")
    if not content:
        return {"error": "복사할 내용이 없습니다."}

    import subprocess
    import platform

    text = str(content) if not isinstance(content, str) else content

    if platform.system() == "Darwin":
        p = subprocess.Popen(["pbcopy"], stdin=subprocess.PIPE)
        p.communicate(text.encode("utf-8"))
    elif platform.system() == "Windows":
        p = subprocess.Popen(["clip"], stdin=subprocess.PIPE)
        p.communicate(text.encode("utf-8"))
    else:
        try:
            p = subprocess.Popen(["xclip", "-selection", "clipboard"], stdin=subprocess.PIPE)
            p.communicate(text.encode("utf-8"))
        except FileNotFoundError:
            return {"error": "xclip이 설치되어 있지 않습니다."}

    return {"ok": True, "copied_length": len(text)}


def _output_download(target: str, params: dict, project_path: str) -> Any:
    """URL에서 파일 다운로드"""
    if not target:
        return {"error": "target(다운로드 URL)이 필요합니다."}

    import urllib.request
    from urllib.parse import urlparse

    filename = params.get("filename")
    if not filename:
        parsed = urlparse(target)
        filename = os.path.basename(parsed.path) or "download"

    save_dir = params.get("save_dir")
    if not save_dir:
        base = os.environ.get("INDIEBIZ_ROOT", os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        save_dir = os.path.join(base, "outputs")
    os.makedirs(save_dir, exist_ok=True)

    save_path = os.path.join(save_dir, filename)

    try:
        urllib.request.urlretrieve(target, save_path)
        return {"ok": True, "path": save_path, "size": os.path.getsize(save_path)}
    except Exception as e:
        return {"error": f"다운로드 실패: {str(e)}"}


def _execute_output_node(node_config, tool_input, project_path):
    """output 노드 실행: ibl_output(action='gui', target='제목', params={...})
    Phase 19: output → orchestrator로 통합됨. 라우터 내부 구현은 유지."""
    action = tool_input.get("action")
    actions = node_config.get("actions", {})
    action_config = actions.get(action)
    if not action_config:
        return {
            "error": f"알 수 없는 output 액션: {action}",
            "available": list(actions.keys()),
        }

    func_name = action_config.get("func")
    target = tool_input.get("target", "")
    params = tool_input.get("params", {})
    return _route_system(func_name, target, params, project_path)


def _route_by_config(action_config, target, params, node, action,
                     project_path, agent_id, guide_path=None):
    """YAML 액션 설정 기반 통합 라우팅"""
    router = action_config.get("router")
    if router == "handler":
        mapped_tool = action_config.get("tool")
        yaml_target_key = action_config.get("target_key")
        return _route_handler(mapped_tool, target, params, project_path, agent_id,
                              yaml_target_key=yaml_target_key, guide_path=guide_path)
    elif router == "driver":
        driver_type = action_config.get("driver", "sqlite")
        dn = action_config.get("driver_node")  # Phase 22: 하위 핸들러 지정
        result = _route_driver(driver_type, node, action, target, params, project_path, driver_node=dn)
        return _attach_guide(result, guide_path) if guide_path else result
    return {"error": f"지원하지 않는 라우터: {router}"}
