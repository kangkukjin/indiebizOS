"""
ibl_exec_goal.py — Goal 원장 조작(list/status/kill/delete)·시도 기록·Goal 블록 실행.

2026-08-23 ibl_executors.py 에서 이사(1500줄 규칙). 재수출 = ibl_executors.
"""
import os
import re
import json
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


def _goal_list(params: dict, project_path: str = "") -> dict:
    """등록된 목표 목록 조회 (상태별 필터 가능)"""
    try:
        from conversation_db import ConversationDB
        db_path = str(Path(project_path) / "conversations.db")
        db = ConversationDB(db_path)
        status_filter = params.get("status")  # "active", "pending", "achieved" 등
        goals = db.list_goals(status=status_filter)

        if not goals:
            return {"success": True, "goals": [], "items": [], "count": 0,
                    "message": "등록된 목표가 없습니다."}

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
            # 통화 병기 (V13-1, 2026-08-19 상상훈련 13회차): goals 키만으로는 어떤 table
            # 변환자도 뒤에 못 붙는다. title=칸 규약 병기, 원명(name 등)은 보존.
            "items": [{"title": g["name"], **g} for g in result_goals],
            "count": len(result_goals),
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


def _goal_delete(goal_id: str, params: dict, project_path: str = "") -> dict:
    """종결된 목표를 원장에서 삭제 (F9-② 2026-08-16 상상훈련 4회차).

    kill(취소=상태 전환)과 다르다 — delete 는 행 자체를 지운다. **종결 상태만**
    (achieved/expired/limit_reached/cancelled) 허용: 살아있는 목표는 kill 먼저 —
    실행 중인 것을 조용히 증발시키면 스케줄·평가 루프가 유령을 쫓는다.
    """
    if not goal_id:
        return {"error": "goal_id가 필요합니다."}

    try:
        from conversation_db import ConversationDB
        db_path = str(Path(project_path) / "conversations.db")
        db = ConversationDB(db_path)
        goal = db.get_goal(goal_id)

        if not goal:
            return {"error": f"목표를 찾을 수 없습니다: {goal_id}"}

        _terminal = ("achieved", "expired", "limit_reached", "cancelled")
        if goal["status"] not in _terminal:
            return {"success": False,
                    "error": f"살아있는 목표는 삭제할 수 없습니다 (상태: {goal['status']}). "
                             f"먼저 [self:goal]{{op: \"kill\", goal_id: \"{goal_id}\"}} 로 종료하세요."}

        ok = db.delete_goal(goal_id)
        if not ok:
            return {"error": f"목표 삭제 실패: {goal_id}"}
        return {
            "success": True,
            "goal_id": goal_id,
            "name": goal["name"],
            "deleted_status": goal["status"],
            "message": f"목표 '{goal['name']}' 원장에서 삭제 완료",
        }
    except Exception as e:
        return {"error": f"목표 삭제 실패: {str(e)}"}


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
    from agent_registry import runner_registry

    goal_name = tool_input.get("name", "unnamed")

    # 활성 에이전트 찾기
    agent = None
    for aid, a in runner_registry.items():
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

