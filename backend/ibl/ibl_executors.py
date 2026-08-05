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
from typing import Any, Dict, Optional, Tuple


_nodes_cache: Optional[Dict] = None


def _load_nodes() -> Dict:
    """nodes: 섹션 로드 (캐싱)"""
    global _nodes_cache
    if _nodes_cache is not None:
        return _nodes_cache
    from ibl_registry import _load_nodes_config
    data = _load_nodes_config()
    _nodes_cache = data.get("nodes", {})
    return _nodes_cache


# (2026-08-05 감사 D11) 옛 노드타입 디스패치(_execute_node/_execute_info_node/
# _execute_store_node/_execute_exec_node)는 삭제 — 트리거 노드명 info/store/exec/output 이
# 레지스트리에 존재하지 않아 도달 불가였고, 도달해도 config type 부재로 오류만 반환했다.

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

    # WebSocket으로 프론트엔드에 전송 (동기·스레드 안전 헬퍼 — 워커 스레드에서 호출됨)
    try:
        from websocket_manager import broadcast_message
        broadcast_message({"type": "ibl_output", "data": result})
    except Exception:
        pass

    return {"ok": True, "output": result}


# (_output_file 은 2026-08-05 어휘 압축으로 삭제 — 파일 저장 정본은 [self:write]
#  (system_essentials write_file): RED 쓰기 안전판 경유 + 파이프 _prev_result 폴백.
#  이 함수는 안전판을 우회했고 파이프 입력도 무시해 빈 파일을 쓰던 반쪽 싱크였다.)


def _extract_path_from_prev(prev_result: str) -> Optional[str]:
    """_prev_result JSON에서 파일 경로 또는 URL을 추출

    1차: 명시적 키 매칭 (file, path, url 등)
    2차: 값 패턴 매칭 (*_path, *_file, *_url 키 또는 http/파일경로 값)
    """
    if not prev_result:
        return None
    _KEYS = ("file", "path", "url", "opened",
             "output_file", "output_path", "report_path",
             "html_path", "file_path", "filepath")
    try:
        data = json.loads(prev_result)
        if isinstance(data, dict):
            # 0차: items 통화 — file_find/list 등이 반환한 items[0]에서 경로 추출.
            # "방금 찾은 파일을 읽기"(file_find | take 1 >> read) 조합을 개통한다.
            items = data.get("items")
            if isinstance(items, list) and items and isinstance(items[0], dict):
                for key in _KEYS:
                    val = items[0].get(key)
                    if val and isinstance(val, str):
                        return val
            # 1차: 명시적 키 매칭 (우선순위순)
            for key in _KEYS:
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
        # ★pbcopy 는 LC_CTYPE locale 로 stdin 을 해석한다 — 백엔드 프로세스(런처/Electron 기동)엔
        # UTF-8 locale 이 없어 한글이 mojibake 로 박히던 함정. UTF-8 을 명시해야 비ASCII 가 살아남는다.
        env = {**os.environ, "LC_CTYPE": "en_US.UTF-8"}
        p = subprocess.Popen(["pbcopy"], stdin=subprocess.PIPE, env=env)
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
        base = os.environ.get("INDIEBIZ_ROOT", os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
        save_dir = os.path.join(base, "outputs")
    os.makedirs(save_dir, exist_ok=True)

    save_path = os.path.join(save_dir, filename)

    try:
        urllib.request.urlretrieve(url, save_path)
        return {"ok": True, "path": save_path, "size": os.path.getsize(save_path)}
    except Exception as e:
        return {"error": f"다운로드 실패: {str(e)}"}


# (2026-08-05) _execute_output_node 삭제 — 유일 호출자가 위의 죽은 _execute_node 였다.
# 출력 동작의 정본은 func:output_op(_output_gui/_output_clipboard). 파일 저장은 [self:write].


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
    조건식 평가 — case/if의 source 표현 + 비교 연산.

    지원하는 형태:
        node:action <op> value
        node:action{params} <op> value
        node:action{params}.field <op> value
        node:action.field <op> value
        node:action                    (불리언 평가, 연산자 없음)

    sense뿐 아니라 self/limbs/others/engines 모두 허용한다.
    비교 연산자는 {}/[]/문자열 밖의 첫 번째 것을 사용한다.
    """
    op_info = _find_top_level_comparison_op(condition)
    if op_info:
        op_start, op_end, op = op_info
        source_expr = condition[:op_start].strip()
        compare_raw = condition[op_end:].strip().strip("'\"")
    else:
        source_expr = condition.strip()
        op = None
        compare_raw = None

    value = _get_sense_value(source_expr, project_path, agent_id)

    if value is None:
        return False

    if op is None:
        return bool(value)

    try:
        sv = float(value)
        cv = float(compare_raw)
        if op == "==": return sv == cv
        if op == "!=": return sv != cv
        if op == ">":  return sv > cv
        if op == ">=": return sv >= cv
        if op == "<":  return sv < cv
        if op == "<=": return sv <= cv
    except (ValueError, TypeError):
        ss = str(value)
        if op == "==": return ss == compare_raw
        if op == "!=": return ss != compare_raw

    return False


def _get_sense_value(source: str, project_path: str, agent_id: str) -> Any:
    """
    case/if의 source 표현을 평가하여 실제 값 반환.

    지원하는 형태:
        node:action                      예: self:time
        node:action{params}              예: sense:price{symbol: "^KS11"}
        node:action{params}.field        예: sense:price{symbol: "^KS11"}.close
        node:action.field                예: self:time.hour

    sense뿐 아니라 self/limbs/others/engines 모두 허용한다.
    field가 지정된 경우 결과 dict에서 점 표기법으로 추출하고,
    없으면 기존 동작(`value` → `result` → str)을 유지한다.
    """
    parsed = _parse_source_ref(source)
    if parsed is None:
        return None
    node, action, params, field = parsed

    try:
        from ibl_engine import execute_ibl
        step = {"_node": node, "action": action, "params": params}
        result = execute_ibl(step, project_path, agent_id)
    except Exception:
        return None

    if field is not None:
        return _extract_dotted_field(result, field)

    if isinstance(result, dict):
        return result.get("value", result.get("result", str(result)))
    return result


def _parse_source_ref(source: str) -> Optional[Tuple[str, str, Dict, Optional[str]]]:
    """
    case/if의 source 참조식을 (node, action, params, field)로 분해.

    유효하지 않으면 None.
    """
    import re

    src = source.strip()
    m = re.match(r'^(\w+):(\w+)', src)
    if not m:
        return None
    node, action = m.group(1), m.group(2)
    rest = src[m.end():]

    params: Dict[str, Any] = {}
    if rest.startswith('{'):
        from ibl_parser import _extract_bracket_raw, _parse_params
        body, end_pos = _extract_bracket_raw(rest, 0, '{', '}')
        if body is None:
            return None
        try:
            params = _parse_params('{' + body + '}') or {}
        except Exception:
            params = {}
        rest = rest[end_pos + 1:]

    field: Optional[str] = None
    rest = rest.strip()
    if rest.startswith('.'):
        fm = re.match(r'^\.(\w+(?:\.\w+)*)\s*$', rest)
        if fm:
            field = fm.group(1)

    return (node, action, params, field)


def _extract_dotted_field(result: Any, field_path: str) -> Any:
    """중첩 dict에서 점 표기법으로 필드 추출 ('close', 'data.price')."""
    if result is None:
        return None
    current = result
    for key in field_path.split('.'):
        if isinstance(current, dict):
            current = current.get(key)
        else:
            return None
        if current is None:
            return None
    return current


def _find_top_level_comparison_op(text: str) -> Optional[Tuple[int, int, str]]:
    """
    조건식에서 {}/[]/문자열 밖의 첫 비교 연산자 위치 찾기.

    좌→우 스캔. 2자 연산자(==, !=, >=, <=)를 먼저 시도.
    """
    depth = 0
    in_string = False
    string_char: Optional[str] = None
    i = 0
    n = len(text)
    while i < n:
        c = text[i]
        if in_string:
            if c == '\\' and i + 1 < n:
                i += 2
                continue
            if c == string_char:
                in_string = False
            i += 1
            continue
        if c == '"' or c == "'":
            in_string = True
            string_char = c
            i += 1
            continue
        if c in '{[':
            depth += 1
            i += 1
            continue
        if c in '}]':
            depth -= 1
            i += 1
            continue
        if depth == 0:
            two = text[i:i+2]
            if two in ('==', '!=', '>=', '<='):
                return (i, i + 2, two)
            if c == '>' or c == '<':
                return (i, i + 1, c)
        i += 1
    return None
