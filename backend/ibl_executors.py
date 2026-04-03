"""
ibl_executors.py - IBL 엔진 실행 모듈

노드 실행(info/store/exec/output), 출력 핸들러(gui/file/open/clipboard/download),
Goal 프로세스 관리, 제어 흐름(condition/case) 함수를 담당합니다.

ibl_engine.py에서 분리된 모듈로, 순환 의존을 피하기 위해
execute_ibl 등은 함수 내부에서 지연 임포트합니다.
"""

import os
import json
from pathlib import Path
from typing import Any, Dict, Optional


_nodes_cache: Optional[Dict] = None


def _load_nodes() -> Dict:
    """nodes: 섹션 로드 (캐싱)"""
    global _nodes_cache
    if _nodes_cache is not None:
        return _nodes_cache
    from ibl_engine import _load_nodes_config
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
    from ibl_engine import _route_by_config

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

    params = tool_input.get("params", {})
    return _route_by_config(action_config, params, source, action,
                            project_path, agent_id)


def _execute_store_node(node_config, tool_input, project_path, agent_id):
    """store 노드 실행: ibl_store(store='health', action='summary')"""
    from ibl_engine import _route_by_config, _route_driver

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

    params = tool_input.get("params", {})
    router = action_config.get("router")
    if router == "driver":
        driver_type = action_config.get("driver", "sqlite")
        dn = action_config.get("driver_node")  # Phase 22: 하위 핸들러 지정
        return _route_driver(driver_type, store, action, params, project_path, driver_node=dn)

    return _route_by_config(action_config, params, store, action,
                            project_path, agent_id)


def _execute_exec_node(node_config, tool_input, project_path, agent_id):
    """exec 노드 실행: ibl_exec(action='python')"""
    from ibl_engine import _route_by_config

    action = tool_input.get("action")
    if not action:
        executors = list(node_config.get("executors", {}).keys())
        programs = list(node_config.get("programs", {}).keys())
        return {
            "error": "action 파라미터가 필요합니다.",
            "executors": executors,
            "programs": programs,
        }

    params = tool_input.get("params", {})

    # executors (python, node, shell)
    executors = node_config.get("executors", {})
    if action in executors:
        config = executors[action]
        return _route_by_config(config, params, "exec", action,
                                project_path, agent_id)

    # programs (remotion, video, slides, image, music)
    programs = node_config.get("programs", {})
    if action in programs:
        config = programs[action]
        return _route_by_config(config, params, "exec", action,
                                project_path, agent_id)

    available = list(executors.keys()) + list(programs.keys())
    return {"error": f"알 수 없는 exec 액션: {action}", "available": available}


# ============================================================
# Phase 13: 출력 노드 함수들
# ============================================================

def _output_gui(content: str, params: dict, project_path: str) -> Any:
    """UI에 결과를 HTML/카드/테이블로 표시"""
    content = params.get("content", content or "")
    format_type = params.get("format", "html")  # html, card, table, markdown
    title = params.get("title", "결과")

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


def _output_file(path: str, params: dict, project_path: str) -> Any:
    """결과를 파일로 저장"""
    if not path:
        return {"error": "path(파일 경로)가 필요합니다."}

    content = params.get("content", "")
    encoding = params.get("encoding", "utf-8")

    # 상대경로면 outputs/ 폴더 기준
    file_path = path
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


def _extract_path_from_prev(prev_result: str) -> Optional[str]:
    """_prev_result JSON에서 파일 경로 또는 URL을 추출

    1차: 명시적 키 매칭 (file, path, url 등)
    2차: 값 패턴 매칭 (*_path, *_file, *_url 키 또는 http/파일경로 값)
    """
    if not prev_result:
        return None
    try:
        data = json.loads(prev_result)
        if isinstance(data, dict):
            # 1차: 명시적 키 매칭 (우선순위순)
            for key in ("file", "path", "url", "opened",
                        "output_file", "output_path", "report_path",
                        "html_path", "file_path", "filepath"):
                val = data.get(key)
                if val and isinstance(val, str):
                    return val
            # 2차: *_path, *_file, *_url 패턴 키 검색
            for key, val in data.items():
                if isinstance(val, str) and val and (
                    key.endswith("_path") or key.endswith("_file") or key.endswith("_url")
                ):
                    return val
            # 3차: 값이 http:// 또는 / 로 시작하는 첫 번째 문자열
            for key, val in data.items():
                if isinstance(val, str) and val and (
                    val.startswith("http://") or val.startswith("https://") or
                    (val.startswith("/") and "." in val.split("/")[-1])
                ):
                    return val
    except (json.JSONDecodeError, TypeError):
        pass
    return None


def _output_open(path: str, params: dict, project_path: str = ".") -> Any:
    """URL을 브라우저로, 파일을 Finder로 열기

    파이프라인에서 사용 시: >> [self:open]
    _prev_result에서 file/path/url 필드를 자동 추출하여 열어준다.
    상대경로는 project_path 기준으로 절대경로로 자동 변환된다.
    """
    import subprocess
    import platform
    from pathlib import Path

    # 파이프라인 자동 추출: path가 비어있으면 _prev_result에서 경로 추출
    if not path and "_prev_result" in params:
        extracted = _extract_path_from_prev(params.get("_prev_result", ""))
        if extracted:
            path = extracted
        else:
            prev = params.get("_prev_result", "")
            return {"error": "열 대상을 찾을 수 없습니다. 이전 step이 file/path/url 키를 포함한 결과를 반환해야 합니다.",
                    "hint": "파이프라인: [도구]{...} >> [self:open] — 이전 도구가 경로/URL을 반환해야 동작합니다.",
                    "_prev_result_preview": prev[:300] if prev else "(empty)"}

    if not path:
        return {"error": "path가 필요합니다. URL 또는 파일 경로를 지정하세요."}

    if path.startswith("http://") or path.startswith("https://"):
        # URL → 브라우저
        if platform.system() == "Darwin":
            subprocess.Popen(["open", path])
        elif platform.system() == "Windows":
            subprocess.Popen(["start", path], shell=True)
        else:
            subprocess.Popen(["xdg-open", path])
        return {"ok": True, "opened": path, "type": "url"}
    else:
        # 상대경로 → 절대경로 변환 (project_path 기준)
        file_path = Path(path)
        if not file_path.is_absolute():
            file_path = (Path(project_path) / file_path).resolve()
        path = str(file_path)

        # 파일/폴더 → Finder/Explorer
        if platform.system() == "Darwin":
            subprocess.Popen(["open", path])
        elif platform.system() == "Windows":
            subprocess.Popen(["explorer", path])
        else:
            subprocess.Popen(["xdg-open", path])
        return {"ok": True, "opened": path, "type": "file"}


def _output_clipboard(content: str, params: dict) -> Any:
    """결과를 클립보드에 복사"""
    content = params.get("content", content or "")
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


def _output_download(url: str, params: dict, project_path: str) -> Any:
    """URL에서 파일 다운로드"""
    if not url:
        return {"error": "url(다운로드 URL)이 필요합니다."}

    import urllib.request
    from urllib.parse import urlparse

    filename = params.get("filename")
    if not filename:
        parsed = urlparse(url)
        filename = os.path.basename(parsed.path) or "download"

    save_dir = params.get("save_dir")
    if not save_dir:
        base = os.environ.get("INDIEBIZ_ROOT", os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        save_dir = os.path.join(base, "outputs")
    os.makedirs(save_dir, exist_ok=True)

    save_path = os.path.join(save_dir, filename)

    try:
        urllib.request.urlretrieve(url, save_path)
        return {"ok": True, "path": save_path, "size": os.path.getsize(save_path)}
    except Exception as e:
        return {"error": f"다운로드 실패: {str(e)}"}


def _execute_output_node(node_config, tool_input, project_path):
    """output 노드 실행: ibl_output(action='gui', params={...})
    Phase 19: output → orchestrator로 통합됨. 라우터 내부 구현은 유지."""
    from ibl_engine import _route_system

    action = tool_input.get("action")
    actions = node_config.get("actions", {})
    action_config = actions.get(action)
    if not action_config:
        return {
            "error": f"알 수 없는 output 액션: {action}",
            "available": list(actions.keys()),
        }

    func_name = action_config.get("func")
    params = tool_input.get("params", {})
    return _route_system(func_name, params, project_path)


# ===========================================================================
# Phase 26: Goal 프로세스 관리 함수
# ===========================================================================

def _goal_list(params: dict, project_path: str = "") -> dict:
    """등록된 목표 목록 조회 (상태별 필터 가능)"""
    try:
        from conversation_db import ConversationDB
        db_path = str(Path(project_path) / "conversations.db")
        db = ConversationDB(db_path)
        status_filter = params.get("status")  # "active", "pending", "achieved" 등
        goals = db.list_goals(status=status_filter)

        if not goals:
            return {"success": True, "goals": [], "message": "등록된 목표가 없습니다."}

        result_goals = []
        for g in goals:
            result_goals.append({
                "goal_id": g["goal_id"],
                "name": g["name"],
                "status": g["status"],
                "current_round": g["current_round"],
                "max_rounds": g["max_rounds"],
                "cumulative_cost": g["cumulative_cost"],
                "max_cost": g["max_cost"],
                "every_frequency": g.get("every_frequency"),
                "deadline": g.get("deadline"),
                "created_at": g.get("created_at"),
            })

        return {
            "success": True,
            "goals": result_goals,
            "total": len(result_goals),
        }
    except Exception as e:
        return {"error": f"목표 목록 조회 실패: {str(e)}"}


def _goal_status(goal_id: str, params: dict, project_path: str = "") -> dict:
    """목표 상태 및 진행도 상세 조회"""
    if not goal_id:
        return {"error": "goal_id가 필요합니다."}

    try:
        from conversation_db import ConversationDB
        db_path = str(Path(project_path) / "conversations.db")
        db = ConversationDB(db_path)
        goal = db.get_goal(goal_id)

        if not goal:
            return {"error": f"목표를 찾을 수 없습니다: {goal_id}"}

        # rounds_data JSON 파싱
        rounds_data = []
        if goal.get("rounds_data"):
            try:
                rounds_data = json.loads(goal["rounds_data"])
            except (json.JSONDecodeError, TypeError):
                pass

        progress_pct = 0
        if goal["max_rounds"] > 0:
            progress_pct = round(goal["current_round"] / goal["max_rounds"] * 100, 1)

        cost_pct = 0
        if goal["max_cost"] > 0:
            cost_pct = round(goal["cumulative_cost"] / goal["max_cost"] * 100, 1)

        return {
            "success": True,
            "goal_id": goal["goal_id"],
            "name": goal["name"],
            "status": goal["status"],
            "success_condition": goal.get("success_condition"),
            "progress": {
                "current_round": goal["current_round"],
                "max_rounds": goal["max_rounds"],
                "progress_pct": progress_pct,
            },
            "cost": {
                "cumulative_cost": goal["cumulative_cost"],
                "max_cost": goal["max_cost"],
                "cost_pct": cost_pct,
            },
            "time": {
                "deadline": goal.get("deadline"),
                "every_frequency": goal.get("every_frequency"),
                "until_condition": goal.get("until_condition"),
                "within_duration": goal.get("within_duration"),
            },
            "rounds_history": rounds_data[-5:],  # 최근 5라운드만
            "created_at": goal.get("created_at"),
            "started_at": goal.get("started_at"),
            "completed_at": goal.get("completed_at"),
        }
    except Exception as e:
        return {"error": f"목표 상태 조회 실패: {str(e)}"}


def _goal_kill(goal_id: str, params: dict, project_path: str = "") -> dict:
    """실행 중인 목표 취소/중단"""
    if not goal_id:
        return {"error": "goal_id가 필요합니다."}

    try:
        from conversation_db import ConversationDB
        db_path = str(Path(project_path) / "conversations.db")
        db = ConversationDB(db_path)
        goal = db.get_goal(goal_id)

        if not goal:
            return {"error": f"목표를 찾을 수 없습니다: {goal_id}"}

        if goal["status"] in ("achieved", "expired", "limit_reached", "cancelled"):
            return {
                "success": False,
                "message": f"이미 종료된 목표입니다 (상태: {goal['status']})",
            }

        reason = params.get("reason", "사용자 요청에 의한 취소")
        db.update_goal_status(goal_id, "cancelled")

        return {
            "success": True,
            "goal_id": goal_id,
            "name": goal["name"],
            "previous_status": goal["status"],
            "new_status": "cancelled",
            "reason": reason,
            "rounds_completed": goal["current_round"],
            "total_cost": goal["cumulative_cost"],
        }
    except Exception as e:
        return {"error": f"목표 취소 실패: {str(e)}"}


# ============ Phase 26b: 시도 기록 (전략 전환 + 라운드 메모리) ============

def _log_attempt(params: dict, project_path: str = ".") -> dict:
    """
    시도 기록 저장

    필수 파라미터:
        task_id: 태스크 ID (같은 작업의 시도를 묶는 키)
        approach_category: 접근 범주 (예: "cv2_direct_import", "pillow_fallback", "ffmpeg_cli")
        description: 구체적으로 무엇을 시도했는지

    선택 파라미터:
        result: "success" 또는 "failure" (기본값: "failure")
        lesson: 이 시도에서 배운 점
    """
    task_id = params.get("task_id", "")
    category = params.get("approach_category", params.get("category", ""))
    description = params.get("description", "")

    if not task_id or not category or not description:
        return {"error": "task_id, approach_category, description은 필수입니다."}

    result = params.get("result", "failure")
    lesson = params.get("lesson")

    try:
        from conversation_db import ConversationDB
        from thread_context import get_current_agent_id
        db_path = str(Path(project_path) / "conversations.db")
        db = ConversationDB(db_path)
        agent_id = get_current_agent_id() or "unknown"

        round_num = db.log_attempt(
            task_id=task_id,
            agent_id=agent_id,
            approach_category=category,
            description=description,
            result=result,
            lesson=lesson
        )

        # 연속 실패 횟수 확인 → 전략 전환 경고
        consecutive = db.get_consecutive_failures(task_id, category)
        failed_categories = db.get_failed_categories(task_id, threshold=3)

        response = {
            "success": True,
            "round_num": round_num,
            "approach_category": category,
            "result": result,
        }

        if consecutive >= 3:
            response["warning"] = (
                f"⚠ '{category}' 접근이 {consecutive}회 연속 실패했습니다. "
                f"이 접근을 포기하고 근본적으로 다른 방법으로 전환하세요."
            )
            response["escalation_required"] = True

        if failed_categories:
            response["exhausted_categories"] = failed_categories
            all_cats = [row["approach_category"] for row in
                        db.get_attempt_history(task_id, limit=100)]
            unique_cats = set(all_cats)
            active_cats = unique_cats - set(failed_categories)
            if not active_cats:
                response["all_exhausted"] = True
                response["warning"] = (
                    "⚠ 시도한 모든 접근 범주가 실패 임계값을 넘었습니다. "
                    "사용자에게 상황을 보고하고 판단을 요청하세요."
                )

        return response
    except Exception as e:
        return {"error": f"시도 기록 실패: {str(e)}"}


def _get_attempts(params: dict, project_path: str = ".") -> dict:
    """
    시도 이력 조회

    파라미터:
        task_id: 태스크 ID (필수)
        limit: 최대 조회 수 (기본 20)
    """
    task_id = params.get("task_id", "")
    if not task_id:
        return {"error": "task_id가 필요합니다."}

    limit = int(params.get("limit", 20))

    try:
        from conversation_db import ConversationDB
        db_path = str(Path(project_path) / "conversations.db")
        db = ConversationDB(db_path)
        history = db.get_attempt_history(task_id, limit=limit)
        failed_categories = db.get_failed_categories(task_id, threshold=3)

        return {
            "task_id": task_id,
            "total_attempts": len(history),
            "attempts": history,
            "exhausted_categories": failed_categories,
            "summary": _summarize_attempts(history, failed_categories)
        }
    except Exception as e:
        return {"error": f"시도 이력 조회 실패: {str(e)}"}


def _summarize_attempts(history: list, failed_categories: list) -> str:
    """시도 이력 요약 생성"""
    if not history:
        return "시도 이력 없음"

    # 카테고리별 통계
    cat_stats = {}
    for h in history:
        cat = h.get("approach_category", "unknown")
        if cat not in cat_stats:
            cat_stats[cat] = {"success": 0, "failure": 0}
        if h.get("result") == "success":
            cat_stats[cat]["success"] += 1
        else:
            cat_stats[cat]["failure"] += 1

    parts = [f"총 {len(history)}회 시도:"]
    for cat, stats in cat_stats.items():
        status = "🚫 포기" if cat in failed_categories else "진행중"
        parts.append(
            f"  - {cat}: 성공 {stats['success']}회, 실패 {stats['failure']}회 [{status}]"
        )

    if failed_categories:
        parts.append(f"포기된 접근: {', '.join(failed_categories)}")

    return "\n".join(parts)


# ===========================================================================
# Phase 26: Goal/Condition/Case 실행 함수
# ===========================================================================

def _execute_goal_block(tool_input: dict, project_path: str, agent_id: str) -> dict:
    """
    Goal Block 실행 — agent_runner의 execute_goal에 위임

    파서가 생성한 _goal dict를 받아 agent_runner에 전달한다.
    활성 에이전트가 없으면 DB에 Goal만 생성한다.
    """
    from agent_runner import AgentRunner

    goal_name = tool_input.get("name", "unnamed")

    # 활성 에이전트 찾기
    agent = None
    for aid, a in AgentRunner.agent_registry.items():
        if a.running and (
            str(a.project_path) in str(project_path) or
            (agent_id and aid == agent_id)
        ):
            agent = a
            break

    if agent:
        return agent.execute_goal(tool_input)

    # 에이전트 없으면 DB에만 생성 (나중에 approve로 활성화)
    try:
        from conversation_db import ConversationDB
        import os, uuid
        from datetime import datetime

        db_path = os.path.join(project_path, "conversations.db")
        db = ConversationDB(db_path)
        goal_id = f"goal_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:6]}"
        db.create_goal(goal_id, tool_input)

        return {
            "goal_id": goal_id,
            "status": "pending",
            "name": goal_name,
            "message": f"Goal '{goal_name}' 생성됨. 활성 에이전트가 없어 대기 상태."
        }
    except Exception as e:
        return {"error": f"Goal 생성 실패: {str(e)}"}


def _execute_condition(tool_input: dict, project_path: str, agent_id: str) -> Any:
    """
    if/else 조건문 실행

    각 분기의 조건을 평가하고, 매칭되는 분기의 action을 실행한다.
    """
    branches = tool_input.get("branches", [])

    for branch in branches:
        condition = branch.get("condition")
        action = branch.get("action")

        if condition is None:
            # else 분기
            if action:
                from ibl_engine import execute_ibl
                return execute_ibl(action, project_path, agent_id)
            return {"message": "else 분기 실행 (action 없음)"}

        # 조건 평가: sense 노드 실행
        try:
            sense_result = _evaluate_sense_condition(condition, project_path, agent_id)
            if sense_result:
                if action:
                    from ibl_engine import execute_ibl
                    return execute_ibl(action, project_path, agent_id)
                return {"message": f"조건 충족: {condition}"}
        except Exception as e:
            continue  # 조건 평가 실패 시 다음 분기로

    return {"message": "모든 조건 불일치, 실행할 분기 없음"}


def _execute_case(tool_input: dict, project_path: str, agent_id: str) -> Any:
    """
    case문 실행

    source에서 sense 값을 가져온 후 분기를 선택하여 action 실행.
    """
    from goal_evaluator import select_case_branch

    source = tool_input.get("source", "")
    branches = tool_input.get("branches", [])
    default = tool_input.get("default")

    # source에서 sense 값 가져오기
    sense_value = _get_sense_value(source, project_path, agent_id)

    if sense_value is not None:
        action = select_case_branch(sense_value, branches, default)
    else:
        action = default

    if action:
        from ibl_engine import execute_ibl
        return execute_ibl(action, project_path, agent_id)

    return {"message": f"case문 실행 완료 (source={source}, value={sense_value})"}


def _evaluate_sense_condition(condition: str, project_path: str, agent_id: str) -> bool:
    """
    조건 표현식에서 sense 노드 실행 후 비교

    Args:
        condition: "sense:kospi < 2400" 형태

    Returns:
        조건 충족 여부
    """
    import re

    # sense 참조 추출
    match = re.match(r'(sense:\w+)', condition)
    if not match:
        return False

    sense_ref = match.group(1)
    sense_value = _get_sense_value(sense_ref, project_path, agent_id)

    if sense_value is None:
        return False

    # 비교 연산자 추출
    op_match = re.search(r'(==|!=|>=|<=|>|<)\s*(.+)$', condition)
    if not op_match:
        return bool(sense_value)

    op = op_match.group(1)
    compare_raw = op_match.group(2).strip().strip("'\"")

    try:
        sv = float(sense_value)
        cv = float(compare_raw)
        if op == "==": return sv == cv
        if op == "!=": return sv != cv
        if op == ">":  return sv > cv
        if op == ">=": return sv >= cv
        if op == "<":  return sv < cv
        if op == "<=": return sv <= cv
    except (ValueError, TypeError):
        ss = str(sense_value)
        if op == "==": return ss == compare_raw
        if op == "!=": return ss != compare_raw

    return False


def _get_sense_value(source: str, project_path: str, agent_id: str) -> Any:
    """
    sense 참조 (예: "sense:kospi")에서 실제 값 가져오기
    """
    parts = source.split(":")
    if len(parts) != 2:
        return None

    node, action = parts[0], parts[1]

    try:
        from ibl_engine import execute_ibl
        step = {"_node": node, "action": action, "params": {}}
        result = execute_ibl(step, project_path, agent_id)

        if isinstance(result, dict):
            return result.get("value", result.get("result", str(result)))
        return result
    except Exception:
        return None
