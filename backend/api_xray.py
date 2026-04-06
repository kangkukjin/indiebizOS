"""
api_xray.py - System X-Ray 시각화
IndieBiz OS의 전신 상태를 X-ray처럼 시각화하는 독립 웹 페이지.

기능:
- GET /xray/app → Body Map 시각화 HTML 페이지
- GET /xray/data → 시스템 전체 진단 데이터 JSON
- WS /xray/ws → 실시간 이벤트 스트림 (도구 실행, task 완료)
"""

import asyncio
import json
import sqlite3
import logging
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, Any, List, Set

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse, JSONResponse

from runtime_utils import get_base_path

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/xray")

# ============================================================
# WebSocket 실시간 연결 관리
# ============================================================

class _XRayWS:
    """X-Ray WebSocket 상태를 클래스로 캡슐화 (Python 3.14 scoping 호환)"""
    def __init__(self):
        self.clients: Set[WebSocket] = set()
        self.queue: asyncio.Queue = asyncio.Queue(maxsize=100)

_ws = _XRayWS()


def push_xray_event(event_type: str, data: dict):
    """동기 코드에서 X-Ray 이벤트 푸시 (system_tools 등에서 호출)"""
    if not _ws.clients:
        return
    event = {"type": event_type, "ts": datetime.now().strftime("%H:%M:%S"), **data}
    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            loop.call_soon_threadsafe(_ws.queue.put_nowait, event)
        else:
            _ws.queue.put_nowait(event)
    except Exception:
        pass

BASE_PATH = get_base_path()
DATA_PATH = BASE_PATH / "data"


# ============================================================
# 데이터 수집
# ============================================================

def _collect_system_health() -> Dict:
    """World Pulse 건강 데이터 수집"""
    try:
        from world_pulse_health import get_system_health
        return get_system_health()
    except Exception as e:
        logger.error(f"[X-Ray] system_health 수집 실패: {e}")
        return {"overall": "unknown", "error": str(e)}


def _collect_ibl_stats() -> Dict:
    """action_health 테이블 + ibl_nodes.yaml 기반 3단계 건강 상태 집계.

    - verified: action_health에 기록 있고 최근 성공
    - assumed: 기록 없음 (디폴트)
    - failed: 기록 있고 최근 실패
    """
    import yaml

    pulse_db = DATA_PATH / "world_pulse.db"
    if not pulse_db.exists():
        return {"by_node": {}, "slow_actions": [], "failing_actions": [],
                "proprioception": {}, "total_checks": 0}

    try:
        conn = sqlite3.connect(str(pulse_db), timeout=5)
        conn.row_factory = sqlite3.Row

        # 1) 최신 펄스에서 proprioception 추출
        proprioception = {}
        pulse_row = conn.execute(
            "SELECT self_state FROM pulse_log ORDER BY id DESC LIMIT 1"
        ).fetchone()
        if pulse_row:
            self_state = json.loads(pulse_row[0] or "{}")
            proprioception = self_state.get("proprioception", {})

        # 2) action_health에서 7일간 액션별 집계
        cutoff = (datetime.now() - timedelta(days=7)).isoformat()
        rows = conn.execute("""
            SELECT node, action,
                   COUNT(*) as total,
                   SUM(success) as successes,
                   AVG(response_ms) as avg_ms,
                   MAX(CASE WHEN success = 1 THEN timestamp END) as last_success,
                   MAX(CASE WHEN success = 0 THEN timestamp END) as last_failure
            FROM action_health
            WHERE timestamp >= ?
            GROUP BY node, action
        """, (cutoff,)).fetchall()

        # action_health가 비어있으면 기존 self_checks 폴백
        if not rows:
            rows = conn.execute("""
                SELECT node, action,
                       COUNT(*) as total,
                       SUM(success) as successes,
                       AVG(response_ms) as avg_ms,
                       MAX(CASE WHEN success = 1 THEN timestamp END) as last_success,
                       MAX(CASE WHEN success = 0 THEN timestamp END) as last_failure
                FROM self_checks
                WHERE timestamp >= ?
                GROUP BY node, action
            """, (cutoff,)).fetchall()

        total_checks = conn.execute("SELECT COUNT(*) FROM self_checks").fetchone()[0]
        conn.close()

        # 3) ibl_nodes.yaml에서 전체 액션 목록 로드 (assumed 판정용)
        all_registered = set()  # {(node, action), ...}
        nodes_yaml = DATA_PATH / "ibl_nodes.yaml"
        if nodes_yaml.exists():
            try:
                with open(nodes_yaml, "r", encoding="utf-8") as f:
                    nodes_data = yaml.safe_load(f) or {}
                for section_key in ("nodes", "actions"):
                    section = nodes_data.get(section_key, {})
                    if isinstance(section, dict):
                        for node_name, node_val in section.items():
                            if isinstance(node_val, dict):
                                acts = node_val.get("actions", node_val)
                                if isinstance(acts, dict):
                                    for act_name in acts:
                                        all_registered.add((node_name, act_name))
            except Exception:
                pass

        # 4) 액션별 상태 결정
        health_map = {}  # (node, action) → {status, success_rate, avg_ms, total}
        all_actions = []
        for row in rows:
            node, action = row["node"], row["action"]
            total = row["total"]
            successes = row["successes"] or 0
            avg_ms = row["avg_ms"]
            last_success = row["last_success"]
            last_failure = row["last_failure"]

            # 3단계 상태 결정
            if last_success and (not last_failure or last_success > last_failure):
                status = "verified"
            elif last_failure:
                status = "failed"
            else:
                status = "assumed"

            rate = round(successes / total * 100, 1) if total > 0 else 0
            health_map[(node, action)] = {
                "status": status,
                "success_rate": rate,
                "avg_ms": round(avg_ms) if avg_ms else None,
                "total": total,
            }
            all_actions.append({
                "node": node, "action": action,
                "success_rate": rate, "avg_ms": avg_ms, "count": total, "status": status,
            })

        # 5) 노드별 집계 (verified/assumed/failed 카운트 포함)
        node_agg = {}
        known_nodes = set()
        for (n, a), info in health_map.items():
            known_nodes.add(n)
            if n not in node_agg:
                node_agg[n] = {"total_exec": 0, "success_exec": 0, "actions": 0,
                               "ms_list": [], "verified": 0, "assumed": 0, "failed": 0}
            agg = node_agg[n]
            agg["actions"] += 1
            agg["total_exec"] += info["total"]
            agg["success_exec"] += info["total"] * info["success_rate"] / 100
            if info["avg_ms"] is not None:
                agg["ms_list"].append(info["avg_ms"])
            agg[info["status"]] += 1

        # assumed 카운트: 등록되었지만 기록 없는 액션 추가
        for (n, a) in all_registered:
            if (n, a) not in health_map:
                known_nodes.add(n)
                if n not in node_agg:
                    node_agg[n] = {"total_exec": 0, "success_exec": 0, "actions": 0,
                                   "ms_list": [], "verified": 0, "assumed": 0, "failed": 0}
                node_agg[n]["actions"] += 1
                node_agg[n]["assumed"] += 1

        by_node = {}
        for node, agg in node_agg.items():
            t = agg["total_exec"]
            rate = round((agg["success_exec"] / t * 100) if t > 0 else -1, 1)
            avg_ms = round(sum(agg["ms_list"]) / len(agg["ms_list"])) if agg["ms_list"] else 0
            by_node[node] = {
                "count": agg["actions"],
                "success_rate": rate,
                "avg_ms": avg_ms,
                "verified": agg["verified"],
                "assumed": agg["assumed"],
                "failed": agg["failed"],
            }

        # 느린 액션 Top 5
        with_ms = [a for a in all_actions if a["avg_ms"] is not None and a["avg_ms"] > 0]
        with_ms.sort(key=lambda x: x["avg_ms"], reverse=True)
        slow_actions = [{"node": a["node"], "action": a["action"],
                         "avg_ms": round(a["avg_ms"]), "count": a["count"]}
                        for a in with_ms[:5]]

        # 실패 액션 Top 5
        with_fail = [a for a in all_actions if a["status"] == "failed"]
        with_fail.sort(key=lambda x: x["success_rate"])
        failing_actions = [{"node": a["node"], "action": a["action"],
                            "fail_rate": round(100 - a["success_rate"], 1),
                            "count": a["count"]}
                           for a in with_fail[:5]]

        # assumed 액션도 all_actions에 추가 (등록되었지만 기록 없는 것)
        for (n, a) in all_registered:
            if (n, a) not in health_map:
                all_actions.append({
                    "node": n, "action": a,
                    "success_rate": -1, "avg_ms": None, "count": 0, "status": "assumed",
                })

        return {
            "by_node": by_node,
            "all_actions": all_actions,
            "slow_actions": slow_actions,
            "failing_actions": failing_actions,
            "proprioception": proprioception,
            "total_checks": total_checks,
        }
    except Exception as e:
        logger.error(f"[X-Ray] IBL/action_health 통계 수집 실패: {e}")
        return {"by_node": {}, "proprioception": {}, "error": str(e)}


def _collect_project_stats() -> List[Dict]:
    """프로젝트별 대화/태스크 통계"""
    projects_file = BASE_PATH / "projects" / "projects.json"
    if not projects_file.exists():
        return []

    try:
        with open(projects_file, "r", encoding="utf-8") as f:
            projects = json.load(f)
    except Exception:
        return []

    results = []
    for proj in projects:
        if proj.get("type") != "project":
            continue
        proj_path = Path(proj.get("path", ""))
        db_file = proj_path / "conversations.db"
        stat = {"id": proj["id"], "name": proj.get("name", proj["id"]),
                "message_count": 0, "task_total": 0, "task_completed": 0, "task_failed": 0}
        if db_file.exists():
            try:
                conn = sqlite3.connect(str(db_file), timeout=3)
                # 메시지 수
                row = conn.execute("SELECT COUNT(*) FROM messages").fetchone()
                stat["message_count"] = row[0] if row else 0
                # 태스크 통계
                try:
                    rows = conn.execute(
                        "SELECT status, COUNT(*) as cnt FROM tasks GROUP BY status"
                    ).fetchall()
                    for r in rows:
                        status, cnt = r[0], r[1]
                        stat["task_total"] += cnt
                        if status == "completed":
                            stat["task_completed"] = cnt
                        elif status == "failed":
                            stat["task_failed"] = cnt
                except Exception:
                    pass  # tasks 테이블이 없을 수 있음
                conn.close()
            except Exception:
                pass
        results.append(stat)

    # 활동량 순 정렬
    results.sort(key=lambda x: x["message_count"], reverse=True)
    return results


def _collect_package_stats() -> Dict:
    """패키지 상태 요약"""
    tools_dir = DATA_PATH / "packages" / "installed" / "tools"

    tool_names = sorted([d.name for d in tools_dir.iterdir() if d.is_dir() and not d.name.startswith('.')]) if tools_dir.exists() else []

    return {
        "tools": tool_names,
        "tool_count": len(tool_names),
        "total": len(tool_names),
    }


def _collect_self_checks() -> List[Dict]:
    """최근 Self-Check 결과"""
    try:
        from world_pulse_health import get_recent_self_checks
        checks = get_recent_self_checks(limit=30)
        return checks
    except Exception as e:
        logger.error(f"[X-Ray] self_checks 수집 실패: {e}")
        return []


def _collect_cognitive_stats() -> Dict:
    """인지 시스템 통계 — 전체 프로젝트 goals/attempts 집계"""
    total_goals = 0
    goals_by_status: Dict[str, int] = {}

    projects_file = BASE_PATH / "projects" / "projects.json"
    if not projects_file.exists():
        return {"total_goals": 0, "by_status": {}}

    try:
        with open(projects_file, "r", encoding="utf-8") as f:
            projects = json.load(f)
    except Exception:
        return {"total_goals": 0, "by_status": {}}

    for proj in projects:
        if proj.get("type") != "project":
            continue
        db_file = Path(proj.get("path", "")) / "conversations.db"
        if not db_file.exists():
            continue
        try:
            conn = sqlite3.connect(str(db_file), timeout=3)
            rows = conn.execute(
                "SELECT status, COUNT(*) as cnt FROM goals GROUP BY status"
            ).fetchall()
            for r in rows:
                status, cnt = r[0], r[1]
                total_goals += cnt
                goals_by_status[status] = goals_by_status.get(status, 0) + cnt
            conn.close()
        except Exception:
            pass

    return {"total_goals": total_goals, "by_status": goals_by_status}


def _collect_activity_timeline() -> Dict:
    """현재 세션의 완료된 Task + 도구 이력 타임라인 수집

    시스템 시작 시 이전 세션 기록은 정리되므로,
    여기에 남아있는 completed task = 현재 세션에서 실행된 것들.
    """
    projects_file = BASE_PATH / "projects" / "projects.json"
    if not projects_file.exists():
        return {"tasks": [], "pending_count": 0, "by_project": []}

    try:
        with open(projects_file, "r", encoding="utf-8") as f:
            projects = json.load(f)
    except Exception:
        return {"tasks": [], "pending_count": 0, "by_project": []}

    all_tasks = []
    pending_count = 0
    project_summary = {}

    for proj in projects:
        if proj.get("type") != "project":
            continue
        proj_id = proj["id"]
        proj_name = proj.get("name", proj_id)
        db_file = Path(proj.get("path", "")) / "conversations.db"
        if not db_file.exists():
            continue
        try:
            conn = sqlite3.connect(str(db_file), timeout=3)
            conn.row_factory = sqlite3.Row

            # tool_history 컬럼 존재 확인
            cols = [r[1] for r in conn.execute("PRAGMA table_info(tasks)").fetchall()]
            has_tool_history = "tool_history" in cols

            # completed tasks (현재 세션)
            if has_tool_history:
                tasks = conn.execute(
                    """SELECT task_id, original_request, delegated_to, status,
                              result, tool_history, created_at, completed_at
                       FROM tasks WHERE status = 'completed'
                       ORDER BY completed_at DESC"""
                ).fetchall()
            else:
                tasks = conn.execute(
                    """SELECT task_id, original_request, delegated_to, status,
                              result, created_at, completed_at
                       FROM tasks WHERE status = 'completed'
                       ORDER BY completed_at DESC"""
                ).fetchall()

            # pending 카운트
            pc = conn.execute("SELECT COUNT(*) FROM tasks WHERE status = 'pending'").fetchone()[0]
            pending_count += pc

            proj_completed = 0
            for t in tasks:
                td = dict(t)
                td["project_id"] = proj_id
                td["project_name"] = proj_name
                # tool_history JSON 파싱
                th = td.pop("tool_history", None)
                if th:
                    try:
                        td["tools"] = json.loads(th)
                    except Exception:
                        td["tools"] = []
                else:
                    td["tools"] = []
                # 요청 내용 150자 제한
                if td.get("original_request"):
                    td["original_request"] = td["original_request"][:150]
                if td.get("result"):
                    td["result"] = td["result"][:200]
                all_tasks.append(td)
                proj_completed += 1

            if proj_completed > 0 or pc > 0:
                project_summary[proj_id] = {
                    "name": proj_name,
                    "completed": proj_completed,
                    "pending": pc,
                }

            conn.close()
        except Exception as e:
            logger.debug(f"[X-Ray] Task 수집 실패 ({proj_id}): {e}")

    # 시스템 AI 메모리 DB도 수집
    sys_db = DATA_PATH / "system_ai_memory.db"
    if sys_db.exists():
        try:
            conn = sqlite3.connect(str(sys_db), timeout=3)
            conn.row_factory = sqlite3.Row
            cols = [r[1] for r in conn.execute("PRAGMA table_info(tasks)").fetchall()]
            has_th = "tool_history" in cols
            if has_th:
                tasks = conn.execute(
                    """SELECT task_id, original_request, delegated_to, status,
                              result, tool_history, created_at, completed_at
                       FROM tasks WHERE status = 'completed'
                       ORDER BY completed_at DESC"""
                ).fetchall()
            else:
                tasks = conn.execute(
                    """SELECT task_id, original_request, delegated_to, status,
                              result, created_at, completed_at
                       FROM tasks WHERE status = 'completed'
                       ORDER BY completed_at DESC"""
                ).fetchall()
            pc = conn.execute("SELECT COUNT(*) FROM tasks WHERE status = 'pending'").fetchone()[0]
            pending_count += pc
            for t in tasks:
                td = dict(t)
                td["project_id"] = "system_ai"
                td["project_name"] = "시스템 AI"
                th = td.pop("tool_history", None)
                if th:
                    try:
                        td["tools"] = json.loads(th)
                    except Exception:
                        td["tools"] = []
                else:
                    td["tools"] = []
                if td.get("original_request"):
                    td["original_request"] = td["original_request"][:150]
                if td.get("result"):
                    td["result"] = td["result"][:200]
                all_tasks.append(td)
            conn.close()
        except Exception:
            pass

    # 최신순 정렬
    all_tasks.sort(key=lambda x: x.get("completed_at") or x.get("created_at") or "", reverse=True)

    by_project = [{"id": k, "name": v["name"],
                    "completed": v["completed"], "pending": v["pending"]}
                   for k, v in project_summary.items()]
    by_project.sort(key=lambda x: x["completed"], reverse=True)

    return {
        "tasks": all_tasks,
        "pending_count": pending_count,
        "by_project": by_project,
    }


# ============================================================
# API 엔드포인트
# ============================================================

@router.websocket("/ws")
async def xray_websocket(websocket: WebSocket):
    """X-Ray 실시간 이벤트 스트림"""
    await websocket.accept()
    _ws.clients.add(websocket)
    logger.info(f"[X-Ray WS] 클라이언트 연결 (총 {len(_ws.clients)})")

    try:
        while True:
            try:
                event = await asyncio.wait_for(_ws.queue.get(), timeout=0.5)
                dead = set()
                for client in _ws.clients:
                    try:
                        await client.send_json(event)
                    except Exception:
                        dead.add(client)
                _ws.clients -= dead
            except asyncio.TimeoutError:
                pass

            try:
                await asyncio.wait_for(websocket.receive_text(), timeout=0.01)
            except asyncio.TimeoutError:
                pass
    except (WebSocketDisconnect, Exception):
        pass
    finally:
        _ws.clients.discard(websocket)
        logger.info(f"[X-Ray WS] 클라이언트 해제 (총 {len(_ws.clients)})")


@router.get("/body-image")
async def xray_body_image():
    """Body Map 배경 이미지 서빙"""
    from fastapi.responses import FileResponse
    img_path = DATA_PATH / "xray_body.png"
    if img_path.exists():
        return FileResponse(str(img_path), media_type="image/png")
    # 대체: static 폴더
    static_path = BASE_PATH / "backend" / "static" / "xray" / "xray_body.png"
    if static_path.exists():
        return FileResponse(str(static_path), media_type="image/png")
    return JSONResponse({"error": "이미지 없음"}, status_code=404)


@router.get("/goals")
async def xray_goals():
    """Goal Timeline 데이터"""
    return JSONResponse(_collect_activity_timeline())


@router.get("/tools")
async def xray_tools():
    """도구 인벤토리 데이터"""
    return JSONResponse(_collect_tool_inventory())


def _collect_tool_inventory() -> Dict[str, Any]:
    """시스템 AI / 프로젝트 에이전트 도구 현황 수집"""
    import yaml

    # 1) 시스템 AI 최상위 도구
    try:
        from system_ai_tools import get_all_system_ai_tools
        sys_tools = [{"name": t["name"], "description": t.get("description", "")[:80]}
                     for t in get_all_system_ai_tools()]
    except Exception as e:
        sys_tools = [{"name": "error", "description": str(e)}]

    # 2) 프로젝트 에이전트 최상위 도구 (agent_cognitive._build_ibl_tools 구조)
    #    동일한 패키지 소스에서 로딩하므로 여기서도 같은 방식으로 수집
    agent_tool_names = []
    try:
        pkg_base = BASE_PATH / "data" / "packages" / "installed" / "tools"
        lang_tools = [
            ("python-exec", "execute_python"),
            ("nodejs", "execute_node"),
            ("system_essentials", "run_command"),
            ("system_essentials", "todo_write"),
            ("system_essentials", "ask_user_question"),
            ("system_essentials", "enter_plan_mode"),
            ("system_essentials", "exit_plan_mode"),
        ]
        agent_tool_names = ["execute_ibl"]
        for pkg_id, tool_name in lang_tools:
            tool_json = pkg_base / pkg_id / "tool.json"
            if tool_json.exists():
                with open(tool_json, 'r', encoding='utf-8') as f:
                    pkg_data = json.load(f)
                for td in pkg_data.get("tools", []):
                    if td.get("name") == tool_name:
                        agent_tool_names.append(tool_name)
                        break
        agent_tool_names.append("read_guide")
    except Exception:
        pass

    agent_tools = [{"name": n, "description": ""} for n in agent_tool_names]

    # 3) 패리티 확인
    sys_names = sorted([t["name"] for t in sys_tools])
    agt_names = sorted(agent_tool_names)
    tool_parity = sys_names == agt_names

    # 4) IBL 노드별 액션 수
    ibl_nodes = {}
    total_actions = 0
    try:
        nodes_yaml = DATA_PATH / "ibl_nodes.yaml"
        if nodes_yaml.exists():
            with open(nodes_yaml, 'r', encoding='utf-8') as f:
                nodes_data = yaml.safe_load(f)
            # 노드는 nodes: 키 아래에 있음
            nodes_section = nodes_data.get("nodes", nodes_data)
            for node_name, node_info in nodes_section.items():
                if isinstance(node_info, dict) and "actions" in node_info:
                    count = len(node_info["actions"])
                    ibl_nodes[node_name] = {"action_count": count}
                    total_actions += count
    except Exception:
        pass

    # 5) 프로젝트별 에이전트 노드 접근 설정
    all_node_names = list(ibl_nodes.keys())
    projects = []
    try:
        projects_path = BASE_PATH / "projects"
        for project_dir in sorted(projects_path.iterdir()):
            if not project_dir.is_dir() or project_dir.name in ['trash', '.DS_Store']:
                continue
            agents_yaml = project_dir / "agents.yaml"
            if not agents_yaml.exists():
                continue
            try:
                with open(agents_yaml, 'r', encoding='utf-8') as f:
                    data = yaml.safe_load(f)
                agents = []
                for agent in data.get("agents", []):
                    allowed = agent.get("allowed_nodes")
                    has_full = allowed is None or set(allowed) >= set(all_node_names)
                    agents.append({
                        "id": agent.get("id"),
                        "name": agent.get("name"),
                        "active": agent.get("active", True),
                        "allowed_nodes": allowed if allowed else all_node_names,
                        "has_full_access": has_full,
                    })
                if agents:
                    projects.append({
                        "id": project_dir.name,
                        "agents": agents,
                    })
            except Exception:
                continue
    except Exception:
        pass

    # 6) 실행 중 에이전트
    running_keys = set()
    try:
        from agent_runner import AgentRunner
        for info in AgentRunner.get_all_agents():
            key = f"{info.get('project_id', '')}:{info.get('id', '')}"
            running_keys.add(key)
    except Exception:
        pass

    # 실행 중 여부 주입
    for proj in projects:
        for agent in proj["agents"]:
            key = f"{proj['id']}:{agent['id']}"
            agent["running"] = key in running_keys

    return {
        "system_ai_tools": sys_tools,
        "agent_tools": agent_tools,
        "tool_parity": tool_parity,
        "ibl_nodes": ibl_nodes,
        "total_ibl_actions": total_actions,
        "all_node_names": all_node_names,
        "projects": projects,
    }


@router.get("/docs")
async def xray_docs():
    """시스템 문서 파싱 데이터"""
    return JSONResponse(_collect_docs())


def _parse_markdown_file(filepath: Path) -> Dict:
    """마크다운 파일을 섹션/테이블/코드 블록으로 파싱"""
    import os
    text = filepath.read_text(encoding='utf-8')
    lines = text.split('\n')
    modified = datetime.fromtimestamp(os.path.getmtime(filepath)).isoformat()

    sections = []
    current = {"level": 1, "title": filepath.stem, "content": "", "tables": [], "code_blocks": []}
    in_code = False
    code_lang = ""
    code_lines = []
    table_lines = []

    def flush_table():
        nonlocal table_lines
        if len(table_lines) >= 2:
            headers = [c.strip() for c in table_lines[0].strip('|').split('|')]
            rows = []
            for tl in table_lines[2:]:  # skip separator
                rows.append([c.strip() for c in tl.strip('|').split('|')])
            current["tables"].append({"headers": headers, "rows": rows})
        table_lines = []

    for line in lines:
        # 코드 블록
        if line.strip().startswith('```'):
            if in_code:
                current["code_blocks"].append({"lang": code_lang, "content": '\n'.join(code_lines)})
                code_lines = []
                in_code = False
            else:
                flush_table()
                code_lang = line.strip()[3:].strip()
                in_code = True
            continue
        if in_code:
            code_lines.append(line)
            continue

        # 헤더
        if line.startswith('## ') or line.startswith('### ') or line.startswith('# '):
            flush_table()
            if current["content"].strip() or current["tables"] or current["code_blocks"]:
                sections.append(current)
            level = len(line.split(' ')[0])
            title = line.lstrip('#').strip()
            current = {"level": level, "title": title, "content": "", "tables": [], "code_blocks": []}
            continue

        # 테이블
        if '|' in line and line.strip().startswith('|'):
            table_lines.append(line)
            continue
        else:
            flush_table()

        # 일반 텍스트
        current["content"] += line + '\n'

    flush_table()
    if current["content"].strip() or current["tables"] or current["code_blocks"]:
        sections.append(current)

    return {
        "name": filepath.name,
        "path": str(filepath.relative_to(BASE_PATH)),
        "modified": modified,
        "size_lines": len(lines),
        "sections": sections,
    }


def _collect_docs() -> Dict:
    """시스템 문서 전체 파싱"""
    files = []

    # system_docs/
    docs_dir = DATA_PATH / "system_docs"
    if docs_dir.exists():
        for f in sorted(docs_dir.iterdir()):
            if f.is_file() and (f.suffix in ('.md', '.log')):
                try:
                    files.append(_parse_markdown_file(f))
                except Exception as e:
                    files.append({"name": f.name, "error": str(e)})

    # guides/system_structure.md
    guide = DATA_PATH / "guides" / "system_structure.md"
    if guide.exists():
        try:
            files.append(_parse_markdown_file(guide))
        except Exception as e:
            files.append({"name": guide.name, "error": str(e)})

    return {"files": files}


def _collect_mental_health() -> Dict:
    """에피소드 요약 기반 정신 건강 판정

    현재는 고정값. 향후 에피소드 데이터 기반 자동 판정으로 전환 예정.
    - optimal: 해마 적중률 높고, 라운드 수 적고, 평가 달성률 높음
    - good: 전반적으로 양호
    - poor: 라운드 과다, 실패 빈번
    """
    try:
        from episode_logger import get_episode_summaries
        summaries = get_episode_summaries(limit=20)
        # TODO: 에피소드 데이터 기반 자동 판정
        # 현재는 고정값
        return {"status": "good", "episode_count": len(summaries)}
    except Exception:
        return {"status": "good", "episode_count": 0}


@router.get("/data")
async def xray_data():
    """시스템 전체 진단 데이터"""
    return JSONResponse({
        "timestamp": datetime.now().isoformat(),
        "system_health": _collect_system_health(),
        "mental_health": _collect_mental_health(),
        "ibl": _collect_ibl_stats(),
        "projects": _collect_project_stats(),
        "packages": _collect_package_stats(),
        "cognitive": _collect_cognitive_stats(),
        "self_checks": _collect_self_checks(),
    })


@router.get("/episodes")
async def xray_episodes(limit: int = 20):
    """최근 에피소드 목록"""
    try:
        from episode_logger import get_episode_list
        return JSONResponse({"episodes": get_episode_list(limit)})
    except Exception as e:
        return JSONResponse({"episodes": [], "error": str(e)})


@router.get("/episodes/{episode_id}")
async def xray_episode_detail(episode_id: int):
    """특정 에피소드 전체 로그"""
    try:
        from episode_logger import get_episode_detail
        detail = get_episode_detail(episode_id)
        if detail:
            return JSONResponse(detail)
        return JSONResponse({"error": "에피소드를 찾을 수 없습니다"}, status_code=404)
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)


@router.get("/episode-summaries")
async def xray_episode_summaries(limit: int = 50):
    """에피소드 요약 지표 (영구 보존)"""
    try:
        from episode_logger import get_episode_summaries
        return JSONResponse({"summaries": get_episode_summaries(limit)})
    except Exception as e:
        return JSONResponse({"summaries": [], "error": str(e)})


@router.get("/app", response_class=HTMLResponse)
async def xray_app():
    """System X-Ray 시각화 페이지"""
    html_path = DATA_PATH / "xray" / "index.html"
    if html_path.exists():
        return HTMLResponse(content=html_path.read_text(encoding="utf-8"))
    return HTMLResponse(content="<h1>X-Ray HTML not found</h1><p>data/xray/index.html 파일이 필요합니다.</p>", status_code=404)

