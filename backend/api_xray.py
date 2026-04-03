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
    """World Pulse의 self_check_summary에서 노드별 건강도 집계.

    ibl_execution_logs는 아직 기록이 안 되므로,
    실제 데이터가 있는 World Pulse Self-Check 결과를 사용한다.
    """
    pulse_db = DATA_PATH / "world_pulse.db"
    if not pulse_db.exists():
        return {"by_node": {}, "slow_actions": [], "failing_actions": [],
                "proprioception": {}, "total_checks": 0}

    try:
        conn = sqlite3.connect(str(pulse_db), timeout=5)

        # 최신 펄스에서 self_check_summary + proprioception 추출
        row = conn.execute(
            "SELECT self_state FROM pulse_log ORDER BY id DESC LIMIT 1"
        ).fetchone()

        by_node = {}
        slow_actions = []
        failing_actions = []
        proprioception = {}
        all_actions = []

        if row:
            self_state = json.loads(row[0] or "{}")
            proprioception = self_state.get("proprioception", {})
            summary = self_state.get("self_check_summary", {})

            # 노드별 집계
            node_agg = {}
            for key, val in summary.items():
                parts = key.split(":", 1)
                node = parts[0] if len(parts) > 0 else "unknown"
                action = parts[1] if len(parts) > 1 else key

                total = val.get("total", 0)
                rate = val.get("success_rate", 0)
                avg_ms = val.get("avg_response_ms")

                if node not in node_agg:
                    node_agg[node] = {"total": 0, "success": 0, "actions": 0, "ms_list": []}
                node_agg[node]["actions"] += 1
                node_agg[node]["total"] += total
                node_agg[node]["success"] += total * rate / 100
                if avg_ms is not None:
                    node_agg[node]["ms_list"].append(avg_ms)

                all_actions.append({
                    "node": node, "action": action,
                    "success_rate": rate, "avg_ms": avg_ms, "count": total
                })

            for node, agg in node_agg.items():
                t = agg["total"]
                rate = round((agg["success"] / t * 100) if t > 0 else 0, 1)
                avg_ms = round(sum(agg["ms_list"]) / len(agg["ms_list"])) if agg["ms_list"] else 0
                by_node[node] = {
                    "count": agg["actions"],
                    "success_rate": rate,
                    "avg_ms": avg_ms,
                }

            # 느린 액션 Top 5 (avg_ms 기준)
            with_ms = [a for a in all_actions if a["avg_ms"] is not None and a["avg_ms"] > 0]
            with_ms.sort(key=lambda x: x["avg_ms"], reverse=True)
            slow_actions = [{"node": a["node"], "action": a["action"],
                             "avg_ms": round(a["avg_ms"]), "count": a["count"]}
                            for a in with_ms[:5]]

            # 실패율 높은 액션 Top 5
            with_fail = [a for a in all_actions if a["success_rate"] < 100]
            with_fail.sort(key=lambda x: x["success_rate"])
            failing_actions = [{"node": a["node"], "action": a["action"],
                                "fail_rate": round(100 - a["success_rate"], 1),
                                "count": a["count"]}
                               for a in with_fail[:5]]

        # Self-Check 로그에서 전체 횟수
        total_checks = conn.execute("SELECT COUNT(*) FROM self_checks").fetchone()[0]

        conn.close()
        return {
            "by_node": by_node,
            "slow_actions": slow_actions,
            "failing_actions": failing_actions,
            "proprioception": proprioception,
            "total_checks": total_checks,
        }
    except Exception as e:
        logger.error(f"[X-Ray] IBL/Pulse 통계 수집 실패: {e}")
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
    ext_dir = DATA_PATH / "packages" / "installed" / "extensions"

    installed_tools = len(list(tools_dir.iterdir())) if tools_dir.exists() else 0
    installed_ext = len(list(ext_dir.iterdir())) if ext_dir.exists() else 0

    return {
        "tools": installed_tools,
        "extensions": installed_ext,
        "total": installed_tools + installed_ext,
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


@router.get("/data")
async def xray_data():
    """시스템 전체 진단 데이터"""
    return JSONResponse({
        "timestamp": datetime.now().isoformat(),
        "system_health": _collect_system_health(),
        "ibl": _collect_ibl_stats(),
        "projects": _collect_project_stats(),
        "packages": _collect_package_stats(),
        "cognitive": _collect_cognitive_stats(),
        "self_checks": _collect_self_checks(),
    })


@router.get("/app", response_class=HTMLResponse)
async def xray_app():
    """System X-Ray 시각화 페이지"""
    return HTMLResponse(content=_get_xray_html())


# ============================================================
# HTML 페이지
# ============================================================

def _get_xray_html() -> str:
    return """<!DOCTYPE html>
<html lang="ko">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>IndieBiz OS — System X-Ray</title>
<style>
* { margin:0; padding:0; box-sizing:border-box; }
body {
  font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
  background: #0a0e17;
  color: #e0e0e0;
  min-height: 100vh;
  overflow-x: hidden;
}

/* Header */
.header {
  display: flex; align-items: center; justify-content: space-between;
  padding: 16px 24px;
  background: linear-gradient(135deg, #0d1321 0%, #1a1a2e 100%);
  border-bottom: 1px solid #1e293b;
}
.header h1 { font-size: 20px; font-weight: 600; color: #94a3b8; letter-spacing: 2px; }
.header h1 span { color: #22d3ee; }
.header-right { display: flex; align-items: center; gap: 16px; }
.overall-badge {
  padding: 6px 16px; border-radius: 20px; font-size: 13px; font-weight: 600;
  text-transform: uppercase; letter-spacing: 1px;
}
.overall-healthy { background: #064e3b; color: #34d399; }
.overall-degraded { background: #7c2d12; color: #fb923c; }
.overall-warning { background: #78350f; color: #fbbf24; }
.overall-unknown { background: #1e293b; color: #94a3b8; }
.btn-refresh {
  background: #1e293b; border: 1px solid #334155; color: #94a3b8;
  padding: 6px 14px; border-radius: 8px; cursor: pointer; font-size: 13px;
}
.btn-refresh:hover { background: #334155; color: #e2e8f0; }

/* Main Layout */
.main { display: grid; grid-template-columns: 380px 1fr; gap: 0; min-height: calc(100vh - 60px); }

/* Body Map (Left) */
.body-map-panel {
  padding: 20px;
  border-right: 1px solid #1e293b;
  display: flex; flex-direction: column; align-items: center;
}
.body-map-panel h2 { font-size: 14px; color: #64748b; margin-bottom: 16px; letter-spacing: 1px; }

.body-svg { width: 320px; cursor: pointer; }
.body-map-container {
  position: relative; width: 320px; margin: 0 auto;
}
.body-map-container img {
  width: 100%; height: auto; display: block; opacity: 0.85;
}
.body-map-overlay {
  position: absolute; top: 0; left: 0; width: 100%; height: 100%;
  pointer-events: none;
}
.body-map-overlay .overlay-label {
  position: absolute; pointer-events: auto; cursor: pointer;
  padding: 3px 8px; border-radius: 6px; font-size: 11px; font-weight: 600;
  backdrop-filter: blur(4px); transition: all 0.2s;
  white-space: nowrap;
}
.body-map-overlay .overlay-label:hover {
  transform: scale(1.1); z-index: 5;
}
.overlay-value {
  font-size: 10px; font-weight: 400; opacity: 0.7; margin-left: 4px;
}
.body-svg .organ {
  transition: all 0.3s ease;
  cursor: pointer;
  stroke: rgba(255,255,255,0.1);
  stroke-width: 1;
}
.body-svg .organ:hover {
  filter: brightness(1.4);
  stroke: rgba(255,255,255,0.4);
  stroke-width: 2;
}
.body-svg .organ-label {
  font-size: 11px; fill: #94a3b8; pointer-events: none;
  font-family: -apple-system, sans-serif;
}
.body-svg .organ-value {
  font-size: 10px; fill: #64748b; pointer-events: none;
  font-family: -apple-system, sans-serif;
}

/* Color coding */
.color-healthy { fill: #22c55e; }
.color-warning { fill: #f59e0b; }
.color-danger  { fill: #ef4444; }
.color-inactive { fill: #475569; }

/* Legend */
.legend {
  display: flex; gap: 16px; margin-top: 20px; padding: 10px 16px;
  background: #111827; border-radius: 8px;
}
.legend-item { display: flex; align-items: center; gap: 6px; font-size: 11px; color: #94a3b8; }
.legend-dot { width: 8px; height: 8px; border-radius: 50%; }

/* Detail Panel (Right) */
.detail-panel { padding: 20px; overflow-y: auto; }
.detail-panel h2 {
  font-size: 16px; color: #e2e8f0; margin-bottom: 16px;
  padding-bottom: 8px; border-bottom: 1px solid #1e293b;
}

/* Cards */
.card-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(220px, 1fr)); gap: 12px; margin-bottom: 24px; }
.card {
  background: #111827; border: 1px solid #1e293b; border-radius: 10px;
  padding: 14px; transition: border-color 0.2s;
}
.card:hover { border-color: #334155; }
.card-title { font-size: 11px; color: #64748b; text-transform: uppercase; letter-spacing: 1px; margin-bottom: 6px; }
.card-value { font-size: 24px; font-weight: 700; }
.card-sub { font-size: 11px; color: #64748b; margin-top: 4px; }

/* Section */
.section { margin-bottom: 28px; }
.section-title {
  font-size: 13px; color: #94a3b8; text-transform: uppercase; letter-spacing: 1px;
  margin-bottom: 12px; display: flex; align-items: center; gap: 8px;
}
.section-title::after { content: ''; flex: 1; height: 1px; background: #1e293b; }

/* Node bars */
.node-bar-row { display: flex; align-items: center; gap: 10px; margin-bottom: 8px; }
.node-bar-label { width: 70px; font-size: 12px; color: #94a3b8; text-align: right; }
.node-bar-track { flex: 1; height: 22px; background: #1e293b; border-radius: 4px; position: relative; overflow: hidden; }
.node-bar-fill { height: 100%; border-radius: 4px; transition: width 0.6s ease; display: flex; align-items: center; padding-left: 8px; font-size: 10px; color: #fff; font-weight: 600; min-width: fit-content; }
.node-bar-stats { width: 120px; font-size: 11px; color: #64748b; }

/* Table */
.xray-table { width: 100%; border-collapse: collapse; font-size: 12px; }
.xray-table th { text-align: left; padding: 8px 10px; color: #64748b; border-bottom: 1px solid #1e293b; font-weight: 500; }
.xray-table td { padding: 8px 10px; border-bottom: 1px solid #0f172a; }
.xray-table tr:hover td { background: #111827; }

/* Self-Check Timeline */
.timeline { display: flex; flex-wrap: wrap; gap: 4px; }
.timeline-dot {
  width: 14px; height: 14px; border-radius: 3px; cursor: pointer;
  transition: transform 0.15s;
}
.timeline-dot:hover { transform: scale(1.6); z-index: 2; }
.timeline-tooltip {
  position: fixed; background: #1e293b; border: 1px solid #334155;
  border-radius: 8px; padding: 10px 14px; font-size: 12px; color: #e2e8f0;
  pointer-events: none; z-index: 100; max-width: 280px;
}

/* Project bar */
.proj-row { display: flex; align-items: center; gap: 8px; margin-bottom: 6px; }
.proj-name { width: 80px; font-size: 12px; color: #94a3b8; text-align: right; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.proj-bar { flex: 1; height: 16px; background: #1e293b; border-radius: 3px; overflow: hidden; }
.proj-bar-fill { height: 100%; background: #3b82f6; border-radius: 3px; transition: width 0.6s; display: flex; align-items: center; padding-left: 6px; font-size: 9px; color: #fff; }
.proj-count { width: 50px; font-size: 11px; color: #64748b; }

/* Loading */
.loading {
  display: flex; align-items: center; justify-content: center;
  height: 100vh; font-size: 16px; color: #64748b;
}
.loading-spinner {
  width: 24px; height: 24px; border: 2px solid #334155; border-top-color: #22d3ee;
  border-radius: 50%; animation: spin 0.8s linear infinite; margin-right: 12px;
}
@keyframes spin { to { transform: rotate(360deg); } }
@keyframes pulse-glow {
  0%, 100% { opacity: 0.6; }
  50% { opacity: 1; }
}
.pulse-indicator { animation: pulse-glow 2s ease-in-out infinite; }

/* Live Feed */
.live-feed {
  position: fixed; bottom: 0; left: 0; right: 0; z-index: 50;
  background: linear-gradient(180deg, transparent 0%, #0a0e17 20%);
  padding: 8px 24px 12px;
}
.live-feed-inner {
  background: #111827; border: 1px solid #1e293b; border-radius: 8px;
  padding: 8px 12px; max-height: 120px; overflow-y: auto;
}
.live-item {
  display: flex; align-items: center; gap: 8px; padding: 3px 0;
  font-size: 11px; color: #94a3b8; animation: fadeIn 0.3s ease;
}
@keyframes fadeIn { from { opacity: 0; transform: translateY(8px); } to { opacity: 1; transform: none; } }
.live-dot { width: 6px; height: 6px; border-radius: 50%; flex-shrink: 0; }
.live-time { color: #475569; font-family: monospace; font-size: 10px; flex-shrink: 0; }
.live-node { color: #22d3ee; font-weight: 600; }
.live-action { color: #e2e8f0; }
.live-ms { color: #64748b; }
.live-ok { color: #34d399; }
.live-err { color: #fca5a5; }
.live-task { color: #a78bfa; font-weight: 600; }

/* Tabs */
.tab-bar {
  display: flex; gap: 0; background: #0d1321; border-bottom: 1px solid #1e293b;
  padding: 0 24px;
}
.tab-btn {
  padding: 10px 20px; font-size: 13px; color: #64748b; background: none;
  border: none; border-bottom: 2px solid transparent; cursor: pointer;
  transition: all 0.2s; letter-spacing: 0.5px;
}
.tab-btn:hover { color: #94a3b8; }
.tab-btn.active { color: #22d3ee; border-bottom-color: #22d3ee; }
.tab-content { display: none; }
.tab-content.active { display: block; }

/* Goal Timeline */
.goal-filters {
  display: flex; gap: 8px; margin-bottom: 16px; flex-wrap: wrap;
}
.filter-chip {
  padding: 5px 12px; border-radius: 14px; font-size: 11px; cursor: pointer;
  background: #1e293b; color: #94a3b8; border: 1px solid #334155;
  transition: all 0.2s;
}
.filter-chip:hover { border-color: #22d3ee; color: #e2e8f0; }
.filter-chip.active { background: #164e63; border-color: #22d3ee; color: #22d3ee; }

.goal-timeline-container { padding: 20px; }

.goal-item {
  background: #111827; border: 1px solid #1e293b; border-radius: 10px;
  padding: 16px; margin-bottom: 12px; transition: border-color 0.2s;
}
.goal-item:hover { border-color: #334155; }
.goal-header {
  display: flex; align-items: center; justify-content: space-between;
  margin-bottom: 10px; flex-wrap: wrap; gap: 8px;
}
.goal-name { font-size: 14px; font-weight: 600; color: #e2e8f0; }
.goal-project {
  font-size: 11px; padding: 2px 8px; border-radius: 10px;
  background: #1e293b; color: #94a3b8;
}
.goal-meta {
  display: flex; gap: 16px; font-size: 11px; color: #64748b; margin-bottom: 12px;
  flex-wrap: wrap;
}
.goal-meta span { display: flex; align-items: center; gap: 4px; }

/* Status badges */
.status-badge {
  display: inline-block; padding: 2px 10px; border-radius: 10px;
  font-size: 11px; font-weight: 600;
}
.status-completed { background: #064e3b; color: #34d399; }
.status-running { background: #172554; color: #60a5fa; }
.status-failed, .status-exhausted { background: #7f1d1d; color: #fca5a5; }
.status-pending { background: #1e293b; color: #94a3b8; }

/* Round track */
.round-track {
  position: relative; display: flex; align-items: center; gap: 0;
  padding: 8px 0; margin-top: 4px;
}
.round-connector {
  flex: 1; height: 2px; background: #334155; min-width: 20px;
}
.round-connector.success { background: #22c55e; }
.round-connector.failure { background: #ef4444; }
.round-connector.partial { background: #f59e0b; }

.round-node {
  width: 32px; height: 32px; border-radius: 50%; display: flex; align-items: center;
  justify-content: center; font-size: 11px; font-weight: 700; color: #fff;
  cursor: pointer; position: relative; flex-shrink: 0;
  transition: transform 0.15s, box-shadow 0.15s;
}
.round-node:hover {
  transform: scale(1.2);
  box-shadow: 0 0 12px rgba(34, 211, 238, 0.3);
}
.round-node.success { background: #16a34a; }
.round-node.failure { background: #dc2626; }
.round-node.partial { background: #d97706; }
.round-node.pending { background: #475569; }

.round-detail {
  position: absolute; bottom: calc(100% + 8px); left: 50%; transform: translateX(-50%);
  background: #1e293b; border: 1px solid #334155; border-radius: 8px;
  padding: 10px 14px; font-size: 11px; color: #e2e8f0; white-space: nowrap;
  pointer-events: none; z-index: 10; display: none; min-width: 200px;
  max-width: 350px; white-space: normal;
}
.round-node:hover .round-detail { display: block; }
.round-detail-label { color: #64748b; font-size: 10px; margin-bottom: 2px; }
.round-detail-value { color: #e2e8f0; margin-bottom: 6px; }

/* Start/End markers */
.round-start {
  width: 12px; height: 12px; border-radius: 50%; background: #3b82f6;
  flex-shrink: 0;
}
.round-end {
  width: 16px; height: 16px; border-radius: 50%; flex-shrink: 0;
  display: flex; align-items: center; justify-content: center; font-size: 10px;
}
.round-end.completed { background: #16a34a; color: #fff; }
.round-end.exhausted { background: #dc2626; color: #fff; }
.round-end.running { background: #3b82f6; color: #fff; animation: pulse-glow 1.5s infinite; }

/* Stats summary */
.goal-stats-bar {
  display: grid; grid-template-columns: repeat(auto-fill, minmax(140px, 1fr));
  gap: 10px; margin-bottom: 20px;
}
.goal-stat-card {
  background: #111827; border: 1px solid #1e293b; border-radius: 8px;
  padding: 12px; text-align: center;
}
.goal-stat-value { font-size: 22px; font-weight: 700; }
.goal-stat-label { font-size: 10px; color: #64748b; margin-top: 2px; text-transform: uppercase; letter-spacing: 0.5px; }

/* Responsive */
@media (max-width: 768px) {
  .main { grid-template-columns: 1fr; }
  .body-map-panel { border-right: none; border-bottom: 1px solid #1e293b; }
}
</style>
</head>
<body>

<div id="app">
  <div class="loading">
    <div class="loading-spinner"></div>
    시스템 스캔 중...
  </div>
</div>

<script>
const API_BASE = window.location.origin;
let DATA = null;
let tooltip = null;

let GOALS = null;
let currentTab = 'bodymap';
let goalFilter = 'all';

async function fetchData() {
  try {
    const res = await fetch(API_BASE + '/xray/data');
    DATA = await res.json();
    render();
  } catch(e) {
    document.getElementById('app').innerHTML =
      '<div class="loading" style="color:#ef4444">데이터 로드 실패: ' + e.message + '</div>';
  }
}

async function fetchGoals() {
  try {
    const res = await fetch(API_BASE + '/xray/goals');
    GOALS = await res.json();
    renderGoalTimeline();
  } catch(e) {
    document.getElementById('goal-timeline').innerHTML =
      '<div style="padding:40px;color:#ef4444;">Goal 데이터 로드 실패: ' + e.message + '</div>';
  }
}

function switchTab(tab) {
  currentTab = tab;
  document.querySelectorAll('.tab-btn').forEach(b => b.classList.toggle('active', b.dataset.tab === tab));
  document.querySelectorAll('.tab-content').forEach(c => c.classList.toggle('active', c.id === 'tab-' + tab));
  if (tab === 'goals' && !GOALS) fetchGoals();
}

function healthColor(rate) {
  if (rate >= 90) return '#22c55e';
  if (rate >= 70) return '#f59e0b';
  return '#ef4444';
}
function healthClass(rate) {
  if (rate >= 90) return 'color-healthy';
  if (rate >= 70) return 'color-warning';
  return 'color-danger';
}
function overallClass(s) {
  return 'overall-' + (s || 'unknown');
}

function render() {
  const d = DATA;
  const sh = d.system_health || {};
  const ibl = d.ibl || {};
  const projects = d.projects || [];
  const pkg = d.packages || {};
  const cog = d.cognitive || {};
  const checks = d.self_checks || [];
  const prop = ibl.proprioception || {};

  // IBL 노드 건강도 매핑
  const nodes = ibl.by_node || {};
  const nodeKeys = ['sense', 'self', 'limbs', 'others', 'engines'];
  const nodeLabels = { sense: '감각 (Sense)', self: '자아 (Self)', limbs: '팔다리 (Limbs)', others: '타자 (Others)', engines: '엔진 (Engines)' };
  const nodeHealth = {};
  nodeKeys.forEach(k => {
    const n = nodes[k];
    nodeHealth[k] = n ? n.success_rate : -1; // -1 = no data
  });

  // 전체 성공률
  const overallRate = ibl.success_rate || 0;
  const selfCheckRate = sh.self_check_avg_success_rate || 0;

  document.getElementById('app').innerHTML = `
    <div class="header">
      <h1><span>X-RAY</span> &nbsp;IndieBiz OS</h1>
      <div class="header-right">
        <span class="overall-badge ${overallClass(sh.overall)}">${sh.overall || 'unknown'}</span>
        <span id="ws-status" style="font-size:11px;color:#64748b;">&#9679; 연결 중...</span>
        <button class="btn-refresh" onclick="location.reload()">새로고침</button>
      </div>
    </div>

    <div class="tab-bar">
      <button class="tab-btn active" data-tab="bodymap" onclick="switchTab('bodymap')">Body Map</button>
      <button class="tab-btn" data-tab="goals" onclick="switchTab('goals')">Task Timeline</button>
    </div>

    <div id="tab-bodymap" class="tab-content active">
    <div class="main">
      <!-- Body Map -->
      <div class="body-map-panel">
        <h2>BODY MAP</h2>
        ${renderBodyMap(nodeHealth, sh, cog)}
        <div class="legend">
          <div class="legend-item"><div class="legend-dot" style="background:#22c55e"></div>건강</div>
          <div class="legend-item"><div class="legend-dot" style="background:#f59e0b"></div>주의</div>
          <div class="legend-item"><div class="legend-dot" style="background:#ef4444"></div>위험</div>
          <div class="legend-item"><div class="legend-dot" style="background:#475569"></div>비활성</div>
        </div>
      </div>

      <!-- Detail Panel -->
      <div class="detail-panel">
        <!-- 요약 카드 -->
        <div class="card-grid">
          <div class="card">
            <div class="card-title">Self-Check</div>
            <div class="card-value" style="color:${healthColor(selfCheckRate)}">${selfCheckRate}%</div>
            <div class="card-sub">${ibl.total_checks || 0}회 점검 (누적)</div>
          </div>
          <div class="card">
            <div class="card-title">메모리</div>
            <div class="card-value" style="color:${(prop.memory_mb||0) > 1000 ? '#f59e0b' : '#22c55e'}">${prop.memory_mb ? prop.memory_mb + ' MB' : 'N/A'}</div>
            <div class="card-sub">스레드 ${prop.threads || '-'} · CPU ${prop.cpu_percent || 0}%</div>
          </div>
          <div class="card">
            <div class="card-title">디스크 여유</div>
            <div class="card-value" style="color:${(sh.disk_free_gb||0) < 10 ? '#ef4444' : '#22c55e'}">${sh.disk_free_gb != null ? sh.disk_free_gb + ' GB' : 'N/A'}</div>
            <div class="card-sub">시스템 스토리지</div>
          </div>
          <div class="card">
            <div class="card-title">패키지</div>
            <div class="card-value" style="color:#3b82f6">${pkg.total || 0}</div>
            <div class="card-sub">도구 ${pkg.tools || 0} · 확장 ${pkg.extensions || 0}</div>
          </div>
        </div>

        <!-- IBL 노드별 -->
        <div class="section">
          <div class="section-title">IBL 노드 건강도</div>
          ${nodeKeys.map(k => {
            const n = nodes[k] || {};
            const rate = n.success_rate ?? 0;
            const cnt = n.count || 0;
            const avgMs = n.avg_ms || 0;
            const maxBar = Math.max(...nodeKeys.map(nk => (nodes[nk]||{}).count || 1));
            const barW = cnt > 0 ? Math.max(cnt / maxBar * 100, 8) : 0;
            return `<div class="node-bar-row">
              <div class="node-bar-label">${nodeLabels[k] || k}</div>
              <div class="node-bar-track">
                <div class="node-bar-fill" style="width:${barW}%;background:${healthColor(rate)}">${cnt > 0 ? rate + '%' : ''}</div>
              </div>
              <div class="node-bar-stats">${cnt}개 액션 · ${avgMs}ms</div>
            </div>`;
          }).join('')}
        </div>

        <!-- 병목 / 문제 액션 -->
        ${(ibl.slow_actions && ibl.slow_actions.length > 0) || (ibl.failing_actions && ibl.failing_actions.length > 0) ? `
        <div class="section">
          <div class="section-title">병목 및 문제 액션</div>
          <div style="display:grid;grid-template-columns:1fr 1fr;gap:16px;">
            ${ibl.slow_actions && ibl.slow_actions.length > 0 ? `
            <div>
              <div style="font-size:11px;color:#f59e0b;margin-bottom:8px;">느린 액션 (평균 응답시간)</div>
              <table class="xray-table">
                <tr><th>노드:액션</th><th>ms</th><th>횟수</th></tr>
                ${ibl.slow_actions.map(a => `<tr><td>${a.node}:${a.action}</td><td style="color:#f59e0b">${a.avg_ms}</td><td>${a.count}</td></tr>`).join('')}
              </table>
            </div>` : ''}
            ${ibl.failing_actions && ibl.failing_actions.length > 0 ? `
            <div>
              <div style="font-size:11px;color:#ef4444;margin-bottom:8px;">실패율 높은 액션</div>
              <table class="xray-table">
                <tr><th>노드:액션</th><th>실패율</th><th>횟수</th></tr>
                ${ibl.failing_actions.map(a => `<tr><td>${a.node}:${a.action}</td><td style="color:#ef4444">${a.fail_rate}%</td><td>${a.count}</td></tr>`).join('')}
              </table>
            </div>` : ''}
          </div>
        </div>` : ''}

        <!-- 프로젝트 활동 -->
        <div class="section">
          <div class="section-title">프로젝트 활동량</div>
          ${projects.length > 0 ? (() => {
            const maxMsg = Math.max(...projects.map(p => p.message_count || 1));
            return projects.slice(0, 15).map(p => {
              const barW = p.message_count > 0 ? Math.max(p.message_count / maxMsg * 100, 4) : 0;
              return `<div class="proj-row">
                <div class="proj-name" title="${p.name}">${p.name}</div>
                <div class="proj-bar">
                  <div class="proj-bar-fill" style="width:${barW}%">${p.message_count > 10 ? p.message_count : ''}</div>
                </div>
                <div class="proj-count">${p.message_count}건</div>
              </div>`;
            }).join('');
          })() : '<div style="color:#64748b;font-size:12px;">프로젝트 데이터 없음</div>'}
        </div>

        <!-- Self-Check 타임라인 -->
        <div class="section">
          <div class="section-title">Self-Check 타임라인 (최근)</div>
          <div class="timeline" id="timeline">
            ${checks.map((c, i) => {
              const bg = c.success ? '#22c55e' : '#ef4444';
              const ts = c.timestamp || '';
              return `<div class="timeline-dot" style="background:${bg}"
                data-info="${c.node}:${c.action} — ${c.success ? '성공' : '실패'}${c.response_ms ? ' (' + c.response_ms + 'ms)' : ''} — ${ts.slice(5, 16)}"
                onmouseenter="showTip(event)" onmouseleave="hideTip()"></div>`;
            }).join('')}
          </div>
          ${checks.length === 0 ? '<div style="color:#64748b;font-size:12px;margin-top:8px;">Self-Check 데이터 없음</div>' : ''}
        </div>

        <!-- 서비스 상태 -->
        ${sh.services ? `
        <div class="section">
          <div class="section-title">서비스 상태</div>
          <div style="display:flex;flex-wrap:wrap;gap:8px;">
            ${Object.entries(sh.services).map(([name, alive]) =>
              `<div style="padding:6px 12px;border-radius:6px;font-size:12px;background:${alive ? '#064e3b' : '#7f1d1d'};color:${alive ? '#34d399' : '#fca5a5'}">${name}</div>`
            ).join('')}
          </div>
        </div>` : ''}

        <div style="text-align:center;padding:20px;color:#334155;font-size:11px;">
          스캔 시각: ${d.timestamp ? d.timestamp.slice(0, 19).replace('T', ' ') : '-'}
        </div>
      </div>
    </div>
    </div><!-- /tab-bodymap -->

    <div id="tab-goals" class="tab-content">
      <div id="goal-timeline" class="goal-timeline-container">
        <div class="loading"><div class="loading-spinner"></div>Goal 데이터 로딩 중...</div>
      </div>
    </div>
  `;
}

function renderBodyMap(nodeHealth, sh, cog) {
  function labelStyle(rate) {
    if (rate < 0) return 'background:rgba(71,85,105,0.7);color:#94a3b8;';
    if (rate >= 90) return 'background:rgba(6,78,59,0.8);color:#34d399;border:1px solid rgba(34,197,94,0.4);';
    if (rate >= 70) return 'background:rgba(120,53,15,0.8);color:#fbbf24;border:1px solid rgba(245,158,11,0.4);';
    return 'background:rgba(127,29,29,0.8);color:#fca5a5;border:1px solid rgba(239,68,68,0.4);';
  }
  function val(rate) { return rate >= 0 ? rate + '%' : 'N/A'; }

  const cogStatus = cog.total_goals > 0 ? cog.by_status || {} : {};
  const cogTotal = cog.total_goals || 0;
  const cogCompleted = cogStatus.completed || 0;
  const cogRate = cogTotal > 0 ? cogCompleted / cogTotal * 100 : -1;

  // 이미지 + 오버레이 라벨 (% 위치는 이미지 기준)
  return `
    <div class="body-map-container" id="body-map-img">
      <img src="/xray/body-image" alt="Body Map" onerror="this.parentElement.innerHTML=renderBodySVG_fallback();" />
      <div class="body-map-overlay">
        <div class="overlay-label" style="top:5%;left:32%;${labelStyle(cogRate)}" onclick="scrollToSection('cognitive')">
          인지 <span class="overlay-value">${val(cogRate)}</span>
        </div>
        <div class="overlay-label" style="top:8%;left:55%;${labelStyle(nodeHealth.sense)}" onclick="scrollToSection('ibl')">
          Sense <span class="overlay-value">${val(nodeHealth.sense)}</span>
        </div>
        <div class="overlay-label" style="top:35%;left:25%;${labelStyle(nodeHealth.self)}" onclick="scrollToSection('ibl')">
          Self <span class="overlay-value">${val(nodeHealth.self)}</span>
        </div>
        <div class="overlay-label" style="top:55%;left:8%;${labelStyle(nodeHealth.limbs)}" onclick="scrollToSection('ibl')">
          Limbs <span class="overlay-value">${val(nodeHealth.limbs)}</span>
        </div>
        <div class="overlay-label" style="top:22%;right:5%;${labelStyle(nodeHealth.others)}" onclick="scrollToSection('ibl')">
          Others <span class="overlay-value">${val(nodeHealth.others)}</span>
        </div>
        <div class="overlay-label" style="top:55%;right:5%;${labelStyle(nodeHealth.engines)}" onclick="scrollToSection('ibl')">
          Engines <span class="overlay-value">${val(nodeHealth.engines)}</span>
        </div>
      </div>
    </div>`;
}

function renderBodySVG_fallback() {
  // 이미지 로드 실패 시 텍스트 폴백
  return '<div style="padding:40px;text-align:center;color:#64748b;font-size:12px;">Body Map 이미지를 로드할 수 없습니다.<br>data/xray_body.png 파일을 확인하세요.</div>';
}

function renderBodySVG(nodeHealth, sh, pkg, cog) {
  function fill(rate) {
    if (rate < 0) return '#475569';
    if (rate >= 90) return '#22c55e';
    if (rate >= 70) return '#f59e0b';
    return '#ef4444';
  }
  function glow(rate) {
    if (rate < 0) return '';
    if (rate >= 90) return 'filter:drop-shadow(0 0 6px rgba(34,197,94,0.4));';
    if (rate >= 70) return 'filter:drop-shadow(0 0 6px rgba(245,158,11,0.4));';
    return 'filter:drop-shadow(0 0 8px rgba(239,68,68,0.5));';
  }

  const cogStatus = cog.total_goals > 0 ? cog.by_status || {} : {};
  const cogTotal = cog.total_goals || 0;
  const cogCompleted = cogStatus.completed || 0;
  const cogRate = cogTotal > 0 ? cogCompleted / cogTotal * 100 : -1;
  const selfRate = sh.self_check_avg_success_rate ?? -1;

  return `
  <svg viewBox="0 0 360 320" class="body-svg" xmlns="http://www.w3.org/2000/svg">

    <!-- ===== 뇌 외곽 — 해부학적 측면도 ===== -->
    <!-- 대뇌 윤곽 (전두엽 볼록, 측두엽 돌출, 후두엽 둥근곡선) -->
    <path d="M75,135 Q60,120 55,95 Q50,65 65,42 Q80,22 110,15 Q145,8 180,12
             Q215,16 240,28 Q265,42 275,65 Q282,85 278,110
             Q275,130 268,145 Q258,165 240,178
             Q225,188 215,195 L210,198
             Q195,190 175,192 Q155,195 140,200
             Q115,195 95,185 Q78,172 70,155 Z"
          fill="#111827" stroke="#334155" stroke-width="2" />

    <!-- 대뇌 주름 (sulci) — 사실적 곡선 패턴 -->
    <path d="M85,50 Q120,35 160,38 Q200,40 245,35" fill="none" stroke="#1e293b" stroke-width="1.2" />
    <path d="M72,75 Q110,55 155,60 Q200,63 260,55" fill="none" stroke="#1e293b" stroke-width="1.2" />
    <path d="M60,105 Q100,85 150,92 Q200,96 270,85" fill="none" stroke="#1e293b" stroke-width="1" />
    <path d="M62,130 Q100,115 155,122 Q205,128 272,115" fill="none" stroke="#1e293b" stroke-width="1" />
    <path d="M75,155 Q110,142 160,148 Q205,155 255,145" fill="none" stroke="#1e293b" stroke-width="0.8" />
    <!-- 실비우스열 (측두엽과 전두엽 경계) -->
    <path d="M90,165 Q120,155 155,160 Q185,165 210,172" fill="none" stroke="#1e293b" stroke-width="1.5" />
    <!-- 중심구 (전두엽/두정엽 경계) -->
    <path d="M175,18 Q170,50 168,85 Q165,120 170,155" fill="none" stroke="#1e293b" stroke-width="1.3" />

    <!-- 소뇌 (후두엽 아래, 줄무늬 패턴) -->
    <path d="M215,195 Q240,200 255,195 Q270,185 272,170 Q268,178 255,185 Q240,192 225,195 Z"
          fill="#111827" stroke="#334155" stroke-width="1.5" />
    <!-- 소뇌 줄무늬 -->
    <path d="M222,198 Q245,200 262,188" fill="none" stroke="#1e293b" stroke-width="0.8" />
    <path d="M220,194 Q242,196 258,186" fill="none" stroke="#1e293b" stroke-width="0.6" />
    <path d="M218,190 Q238,193 254,183" fill="none" stroke="#1e293b" stroke-width="0.5" />

    <!-- 뇌간 -->
    <path d="M210,198 Q205,210 200,228 Q198,238 200,245" stroke="#334155" stroke-width="5" stroke-linecap="round" fill="none" />

    <!-- ================================================================ -->
    <!-- 기능 영역 매핑 -->
    <!-- ================================================================ -->

    <!-- ===== Sense — 감각 피질 (두정엽 위쪽, 중심구 뒤) ===== -->
    <g class="organ" onclick="scrollToSection('ibl')" style="${glow(nodeHealth.sense)}">
      <path d="M175,18 Q195,20 220,30 Q250,45 265,68 Q272,85 270,105
               L230,110 Q235,90 230,70 Q220,50 200,38 Q185,28 175,25 Z"
            fill="${fill(nodeHealth.sense)}" opacity="0.45" />
      <!-- 감각 입력 신호 -->
      <line x1="282" y1="50" x2="258" y2="55" stroke="${fill(nodeHealth.sense)}" stroke-width="1.5" stroke-dasharray="2,2" opacity="0.5" />
      <line x1="288" y1="75" x2="268" y2="78" stroke="${fill(nodeHealth.sense)}" stroke-width="1.5" stroke-dasharray="2,2" opacity="0.4" />
      <line x1="285" y1="100" x2="270" y2="100" stroke="${fill(nodeHealth.sense)}" stroke-width="1.5" stroke-dasharray="2,2" opacity="0.3" />
      <!-- 감각 파동 -->
      <circle cx="295" cy="72" r="3" fill="${fill(nodeHealth.sense)}" opacity="0.4" />
      <circle cx="295" cy="72" r="7" fill="none" stroke="${fill(nodeHealth.sense)}" stroke-width="0.6" opacity="0.3" />
      <circle cx="295" cy="72" r="12" fill="none" stroke="${fill(nodeHealth.sense)}" stroke-width="0.4" opacity="0.15" />
    </g>
    <text x="305" y="55" class="organ-label">Sense</text>
    <text x="305" y="68" class="organ-value">${nodeHealth.sense >= 0 ? nodeHealth.sense + '%' : ''}</text>

    <!-- ===== Limbs — 운동 피질 (전두엽 뒤쪽, 중심구 앞) ===== -->
    <g class="organ" onclick="scrollToSection('ibl')" style="${glow(nodeHealth.limbs)}">
      <path d="M110,15 Q135,10 165,14 L168,85 Q165,120 170,150
               L130,145 Q130,115 132,85 Q130,55 118,35 Q112,25 110,18 Z"
            fill="${fill(nodeHealth.limbs)}" opacity="0.45" />
      <!-- 운동 출력 화살표 -->
      <line x1="118" y1="20" x2="105" y2="5" stroke="${fill(nodeHealth.limbs)}" stroke-width="1.5" opacity="0.5" />
      <polygon points="103,2 108,0 105,8" fill="${fill(nodeHealth.limbs)}" opacity="0.5" />
      <line x1="122" y1="38" x2="108" y2="28" stroke="${fill(nodeHealth.limbs)}" stroke-width="1.5" opacity="0.4" />
      <polygon points="106,25 111,24 108,31" fill="${fill(nodeHealth.limbs)}" opacity="0.4" />
    </g>
    <text x="130" y="8" text-anchor="middle" class="organ-label">Limbs</text>
    <text x="88" y="18" class="organ-value">${nodeHealth.limbs >= 0 ? nodeHealth.limbs + '%' : ''}</text>

    <!-- ===== 인지 — 전전두엽 (뇌 앞쪽) ===== -->
    <g class="organ" onclick="scrollToSection('cognitive')" style="${glow(cogRate)}">
      <path d="M65,42 Q60,60 58,80 Q55,100 60,120 Q65,135 75,148
               L120,140 Q115,120 115,95 Q115,70 112,50 Q105,35 90,30 Q75,28 65,42 Z"
            fill="${fill(cogRate)}" opacity="0.4" />
      <!-- 신경 연결 점 -->
      <circle cx="88" cy="75" r="3" fill="rgba(255,255,255,0.15)" />
      <circle cx="95" cy="100" r="2.5" fill="rgba(255,255,255,0.12)" />
      <circle cx="82" cy="115" r="2" fill="rgba(255,255,255,0.1)" />
      <line x1="88" y1="75" x2="95" y2="100" stroke="rgba(255,255,255,0.1)" stroke-width="0.8" />
      <line x1="95" y1="100" x2="82" y2="115" stroke="rgba(255,255,255,0.1)" stroke-width="0.8" />
    </g>
    <text x="45" y="60" class="organ-label">인지</text>
    <text x="45" y="73" class="organ-value">${cogRate >= 0 ? Math.round(cogRate) + '%' : 'N/A'}</text>

    <!-- ===== Self — 변연계/시상 (뇌 깊은 중심) ===== -->
    <g class="organ" onclick="scrollToSection('ibl')" style="${glow(nodeHealth.self)}">
      <ellipse cx="170" cy="145" rx="32" ry="20" fill="${fill(nodeHealth.self)}" opacity="0.4" />
      <!-- 시상 -->
      <ellipse cx="160" cy="142" rx="10" ry="7" fill="rgba(255,255,255,0.08)" stroke="rgba(255,255,255,0.1)" stroke-width="0.5" />
      <!-- 해마 -->
      <path d="M175,150 Q185,148 190,152 Q192,158 185,158" fill="none" stroke="rgba(255,255,255,0.12)" stroke-width="1" />
    </g>
    <!-- Self 펄스 -->
    <g class="pulse-indicator">
      <circle cx="170" cy="145" r="3.5" fill="#22d3ee" opacity="0.8" />
    </g>
    <text x="170" y="140" text-anchor="middle" class="organ-label" style="fill:#e2e8f0;font-size:10px;">Self</text>
    <text x="170" y="168" text-anchor="middle" class="organ-value" style="fill:rgba(255,255,255,0.5)">${nodeHealth.self >= 0 ? nodeHealth.self + '%' : ''}</text>

    <!-- ================================================================ -->
    <!-- 외부 장치 (뇌 아래) -->
    <!-- ================================================================ -->

    <!-- ===== Others — 모니터/스크린 ===== -->
    <g class="organ" onclick="scrollToSection('ibl')" style="${glow(nodeHealth.others)}">
      <!-- 연결선 -->
      <path d="M140,200 Q120,230 108,255" stroke="${fill(nodeHealth.others)}" stroke-width="1" stroke-dasharray="3,3" opacity="0.3" />
      <!-- 모니터 프레임 -->
      <rect x="72" y="258" width="70" height="46" rx="4" fill="#0f172a" stroke="${fill(nodeHealth.others)}" stroke-width="1.5" />
      <!-- 스크린 -->
      <rect x="76" y="262" width="62" height="32" rx="2" fill="${fill(nodeHealth.others)}" opacity="0.15" />
      <!-- 파형 (모니터 내용) -->
      <polyline points="80,278 88,272 94,282 100,270 106,280 112,274 118,278 124,272 132,278"
                fill="none" stroke="${fill(nodeHealth.others)}" stroke-width="1.2" opacity="0.5" />
      <!-- 모니터 스탠드 -->
      <line x1="107" y1="304" x2="107" y2="310" stroke="${fill(nodeHealth.others)}" stroke-width="2" opacity="0.4" />
      <line x1="95" y1="310" x2="119" y2="310" stroke="${fill(nodeHealth.others)}" stroke-width="1.5" opacity="0.4" />
    </g>
    <text x="107" y="298" text-anchor="middle" class="organ-value">${nodeHealth.others >= 0 ? nodeHealth.others + '%' : ''}</text>
    <text x="107" y="298" text-anchor="middle" class="organ-label" style="transform:translateY(18px)">Others</text>

    <!-- ===== Engines — 토글 스위치 패널 ===== -->
    <g class="organ" onclick="scrollToSection('ibl')" style="${glow(nodeHealth.engines)}">
      <!-- 연결선 -->
      <path d="M200,245 Q220,255 235,262" stroke="${fill(nodeHealth.engines)}" stroke-width="1" stroke-dasharray="4,4" opacity="0.3" />
      <!-- 패널 -->
      <rect x="230" y="258" width="70" height="46" rx="5" fill="#0f172a" stroke="${fill(nodeHealth.engines)}" stroke-width="1.5" />
      <!-- 기어 -->
      <circle cx="250" cy="275" r="9" fill="none" stroke="${fill(nodeHealth.engines)}" stroke-width="1.5" opacity="0.5" />
      <circle cx="250" cy="275" r="3" fill="${fill(nodeHealth.engines)}" opacity="0.35" />
      ${[0,60,120,180,240,300].map(deg => {
        const r = 12; const cx = 250; const cy = 275;
        const x = cx + r * Math.cos(deg * Math.PI / 180);
        const y = cy + r * Math.sin(deg * Math.PI / 180);
        return '<circle cx="' + x.toFixed(1) + '" cy="' + y.toFixed(1) + '" r="1.5" fill="' + fill(nodeHealth.engines) + '" opacity="0.3"/>';
      }).join('')}
      <!-- 토글 스위치 -->
      <rect x="275" y="268" width="18" height="8" rx="4" fill="#1e293b" stroke="${fill(nodeHealth.engines)}" stroke-width="1" opacity="0.6" />
      <circle cx="288" cy="272" r="3" fill="${fill(nodeHealth.engines)}" opacity="0.5" />
      <rect x="275" y="282" width="18" height="8" rx="4" fill="#1e293b" stroke="${fill(nodeHealth.engines)}" stroke-width="1" opacity="0.6" />
      <circle cx="280" cy="286" r="3" fill="#475569" opacity="0.4" />
    </g>
    <text x="265" y="298" text-anchor="middle" class="organ-value">${nodeHealth.engines >= 0 ? nodeHealth.engines + '%' : ''}</text>
    <text x="265" y="298" text-anchor="middle" class="organ-label" style="transform:translateY(18px)">Engines</text>

  </svg>`;
}

function renderGoalTimeline() {
  if (!GOALS) return;
  const container = document.getElementById('goal-timeline');
  if (!container) return;

  const tasks = GOALS.tasks || [];
  const pending = GOALS.pending_count || 0;
  const byProject = GOALS.by_project || [];

  // 필터 적용
  const filtered = goalFilter === 'all' ? tasks :
    tasks.filter(t => t.project_id === goalFilter);

  // 도구 호출 집계
  let totalTools = 0;
  let totalSuccess = 0;
  tasks.forEach(t => {
    (t.tools || []).forEach(tc => { totalTools++; if (tc.success) totalSuccess++; });
  });

  container.innerHTML = `
    <!-- 세션 통계 -->
    <div class="goal-stats-bar">
      <div class="goal-stat-card">
        <div class="goal-stat-value" style="color:#34d399">${tasks.length}</div>
        <div class="goal-stat-label">완료된 Task</div>
      </div>
      <div class="goal-stat-card">
        <div class="goal-stat-value" style="color:#f59e0b">${pending}</div>
        <div class="goal-stat-label">대기 중</div>
      </div>
      <div class="goal-stat-card">
        <div class="goal-stat-value" style="color:#3b82f6">${totalTools}</div>
        <div class="goal-stat-label">도구 호출</div>
      </div>
      <div class="goal-stat-card">
        <div class="goal-stat-value" style="color:${totalTools > 0 ? healthColor(totalSuccess/totalTools*100) : '#64748b'}">${totalTools > 0 ? Math.round(totalSuccess/totalTools*100) + '%' : '-'}</div>
        <div class="goal-stat-label">도구 성공률</div>
      </div>
    </div>

    ${tasks.length === 0 ? '<div style="padding:60px 20px;text-align:center;color:#64748b;"><div style="font-size:40px;margin-bottom:16px;opacity:0.3;">&#128064;</div><div style="font-size:14px;margin-bottom:8px;">현재 세션에서 완료된 Task가 없습니다.</div><div style="font-size:12px;">시스템을 사용하면 여기에 Task 실행 이력이 표시됩니다.<br>각 Task가 어떤 도구를 사용했는지, 성공/실패 여부를 볼 수 있습니다.</div></div>' : ''}

    ${tasks.length > 0 ? `
    <!-- 프로젝트 필터 -->
    <div class="goal-filters">
      <button class="filter-chip ${goalFilter === 'all' ? 'active' : ''}" onclick="setGoalFilter('all')">전체 (${tasks.length})</button>
      ${byProject.map(p =>
        '<button class="filter-chip ' + (goalFilter === p.id ? 'active' : '') + '" onclick="setGoalFilter(\\'' + p.id + '\\')">' + escHtml(p.name) + ' (' + p.completed + ')</button>'
      ).join('')}
    </div>

    <!-- Task 타임라인 -->
    <div class="section">
      <div class="section-title">Task 실행 이력 (현재 세션, ${filtered.length}건)</div>
      ${filtered.map(t => renderTaskItem(t)).join('')}
    </div>` : ''}
  `;
}

function setGoalFilter(f) {
  goalFilter = f;
  renderGoalTimeline();
}

function renderTaskItem(t) {
  const tools = t.tools || [];
  const toolCount = tools.length;
  const toolSuccess = tools.filter(tc => tc.success).length;
  const createdAt = t.created_at ? t.created_at.slice(0, 16).replace('T', ' ') : '-';
  const totalMs = tools.reduce((s, tc) => s + (tc.ms || 0), 0);

  // 도구 액션 파이프라인 시각화
  let toolsHtml = '';
  if (toolCount > 0) {
    toolsHtml = '<div style="margin-top:8px;padding:8px 10px;background:#0f172a;border-radius:6px;">' +
      tools.map((tc, i) => {
        const ok = tc.success;
        const nodeAction = (tc.node && tc.action) ? tc.node + ':' + tc.action : tc.tool_name || '?';
        const ms = tc.ms || 0;
        const dotColor = ok ? '#22c55e' : '#ef4444';
        const msColor = ms > 3000 ? '#f59e0b' : '#475569';
        return '<div style="display:flex;align-items:center;gap:8px;padding:2px 0;">' +
          '<div style="width:6px;height:6px;border-radius:50%;background:' + dotColor + ';flex-shrink:0;"></div>' +
          '<span style="color:#22d3ee;font-size:11px;font-weight:600;min-width:120px;">' + escHtml(nodeAction) + '</span>' +
          '<span style="color:' + msColor + ';font-size:10px;">' + ms + 'ms</span>' +
          (ok ? '' : '<span style="color:#fca5a5;font-size:10px;">FAIL</span>') +
        '</div>';
      }).join('') +
      '</div>';
  }

  return '<div class="goal-item" style="padding:12px;">' +
    '<div class="goal-header">' +
      '<div style="flex:1;min-width:0;">' +
        '<span class="goal-name" style="font-size:13px;">' + escHtml(t.original_request || t.task_id) + '</span>' +
      '</div>' +
      '<div style="display:flex;gap:6px;align-items:center;flex-shrink:0;">' +
        '<span class="goal-project">' + escHtml(t.project_name) + '</span>' +
      '</div>' +
    '</div>' +
    '<div class="goal-meta">' +
      '<span>' + createdAt + '</span>' +
      (t.delegated_to ? '<span>&#128100; ' + escHtml(t.delegated_to) + '</span>' : '') +
      (toolCount > 0 ? '<span>' + toolSuccess + '/' + toolCount + ' actions · ' + totalMs + 'ms</span>' : '<span style="color:#64748b;">텍스트 응답</span>') +
    '</div>' +
    toolsHtml +
  '</div>';
}

function escHtml(s) {
  if (!s) return '';
  return s.replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;');
}

function scrollToSection(id) {
  // 해당 섹션으로 스크롤
  const sections = document.querySelectorAll('.section-title');
  for (const s of sections) {
    if (id === 'ibl' && s.textContent.includes('IBL')) { s.scrollIntoView({behavior:'smooth'}); return; }
    if (id === 'projects' && s.textContent.includes('프로젝트')) { s.scrollIntoView({behavior:'smooth'}); return; }
    if (id === 'cognitive' && s.textContent.includes('IBL')) { s.scrollIntoView({behavior:'smooth'}); return; }
  }
}

function showTip(e) {
  if (!tooltip) {
    tooltip = document.createElement('div');
    tooltip.className = 'timeline-tooltip';
    document.body.appendChild(tooltip);
  }
  tooltip.textContent = e.target.dataset.info;
  tooltip.style.display = 'block';
  tooltip.style.left = e.clientX + 12 + 'px';
  tooltip.style.top = e.clientY - 40 + 'px';
}
function hideTip() {
  if (tooltip) tooltip.style.display = 'none';
}

// ============ WebSocket 실시간 ============
let ws = null;
let liveFeed = [];
const MAX_FEED = 50;

function connectWS() {
  const proto = location.protocol === 'https:' ? 'wss:' : 'ws:';
  ws = new WebSocket(proto + '//' + location.host + '/xray/ws');

  ws.onopen = () => {
    const el = document.getElementById('ws-status');
    if (el) { el.innerHTML = '&#9679; LIVE'; el.style.color = '#34d399'; }
  };
  ws.onclose = () => {
    const el = document.getElementById('ws-status');
    if (el) { el.innerHTML = '&#9679; 연결 끊김'; el.style.color = '#ef4444'; }
    // 3초 후 재연결
    setTimeout(connectWS, 3000);
  };
  ws.onerror = () => ws.close();

  ws.onmessage = (e) => {
    try {
      const event = JSON.parse(e.data);
      handleLiveEvent(event);
    } catch(err) {}
  };
}

function handleLiveEvent(evt) {
  liveFeed.unshift(evt);
  if (liveFeed.length > MAX_FEED) liveFeed = liveFeed.slice(0, MAX_FEED);
  renderLiveFeed();
}

function renderLiveFeed() {
  let container = document.getElementById('live-feed');
  if (!container) {
    container = document.createElement('div');
    container.id = 'live-feed';
    container.className = 'live-feed';
    document.body.appendChild(container);
  }

  const items = liveFeed.slice(0, 15).map(evt => {
    if (evt.type === 'tool') {
      const dotColor = evt.success ? '#22c55e' : '#ef4444';
      const statusCls = evt.success ? 'live-ok' : 'live-err';
      const statusTxt = evt.success ? 'OK' : 'ERR';
      return '<div class="live-item">' +
        '<div class="live-dot" style="background:' + dotColor + '"></div>' +
        '<span class="live-time">' + evt.ts + '</span>' +
        (evt.agent ? '<span style="color:#64748b;">[' + escHtml(evt.agent) + ']</span>' : '') +
        '<span class="live-node">' + escHtml(evt.node) + '</span>:<span class="live-action">' + escHtml(evt.action) + '</span>' +
        (evt.hint ? '<span style="color:#475569;">(' + escHtml(evt.hint.slice(0, 30)) + ')</span>' : '') +
        '<span class="' + statusCls + '">' + statusTxt + '</span>' +
        '<span class="live-ms">' + evt.ms + 'ms</span>' +
      '</div>';
    } else if (evt.type === 'task_complete') {
      return '<div class="live-item">' +
        '<div class="live-dot" style="background:#a78bfa"></div>' +
        '<span class="live-time">' + evt.ts + '</span>' +
        '<span class="live-task">TASK</span>' +
        '<span class="live-action">' + escHtml((evt.request || '').slice(0, 50)) + '</span>' +
        '<span style="color:#64748b;">&#10132; ' + escHtml(evt.agent || '') + '</span>' +
        (evt.tool_count > 0 ? '<span style="color:#64748b;">' + evt.tool_count + ' tools</span>' : '') +
      '</div>';
    }
    return '';
  }).join('');

  container.innerHTML = '<div class="live-feed-inner">' +
    (items || '<div class="live-item" style="color:#475569;">실시간 이벤트 대기 중...</div>') +
    '</div>';
}

// 초기 로드
fetchData();
connectWS();
</script>
</body>
</html>"""
