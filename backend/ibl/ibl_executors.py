"""
ibl_executors.py - IBL 엔진 실행 모듈

노드 실행(info/store/exec/output), 출력 핸들러(gui/file/open/clipboard/download),
Goal 프로세스 관리, 제어 흐름(condition/case) 함수를 담당합니다.

ibl_engine.py에서 분리된 모듈로, 순환 의존을 피하기 위해
execute_ibl 등은 함수 내부에서 지연 임포트합니다.
"""

import os
import re
import json
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


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

    # ★B11 (2026-08-17 상상훈련 12회차): 코퍼스 교본이 가르치는 `path`(전체 저장 경로)를
    # 핸들러가 안 읽어 침묵 무시 — "outputs/파일.html" 지정이 저장소 outputs/download 로
    # 뭉개졌다(파일명 상실+프로젝트 스코핑 미적용). path 를 1순위로 받는다:
    # 절대/~ 는 그대로, 상대 경로는 프로젝트 기준(write 와 동일 규약).
    raw_path = params.get("path")
    if raw_path:
        save_path = os.path.expanduser(str(raw_path))
        if not os.path.isabs(save_path):
            save_path = os.path.join(project_path or ".", save_path)
        os.makedirs(os.path.dirname(save_path) or ".", exist_ok=True)
    else:
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
        # UA 없는 urlretrieve 는 다수 사이트(한겨레 등)가 403 (2026-08-16 6회차 실측) —
        # crawl 과 같은 부류의 평범한 브라우저 UA 로 요청한다.
        req = urllib.request.Request(url, headers={
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                          "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36"})
        with urllib.request.urlopen(req, timeout=60) as resp, open(save_path, "wb") as f:
            while True:
                chunk = resp.read(1 << 16)
                if not chunk:
                    break
                f.write(chunk)
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


def _nest(step: Any, tool_input: dict) -> Any:
    """중첩 실행할 step 에 깊이를 +1 해서 실어 보낸다 (2026-08-15 고차 문장).

    문장을 값으로 받는 자리(if/case/[table:each])가 공통으로 쓰는 한 줄.
    step 이 dict 가 아니면(문자열 IBL 코드 등) 그대로 돌려준다 — 호출자가 파싱한다.
    """
    if not isinstance(step, dict):
        return step
    return {**step, "_depth": (tool_input.get("_depth") or 0) + 1}


def _run_branch(action: Any, tool_input: dict, project_path: str, agent_id: str) -> Any:
    """if/case 분기 몸 실행 — 단일 액션(dict)과 **파이프(steps 리스트)** 둘 다.

    ★2026-08-16 상상훈련 9회차: 파서는 분기 몸의 파이프를 steps 리스트로 담는데
    실행기가 dict 만 가정해 `'list' object has no attribute 'get'` 으로 죽었다 —
    문법이 허용하는 모양(블록 속 파이프)을 실행기가 전부 받아야 한다.
    """
    if isinstance(action, list):
        from workflow_engine import execute_pipeline
        depth = (tool_input.get("_depth") or 0) + 1
        steps = [({**s, "_depth": depth} if isinstance(s, dict) else s) for s in action]
        return execute_pipeline(steps, project_path, agent_id=agent_id)
    from ibl_engine import execute_ibl
    return execute_ibl(_nest(action, tool_input), project_path, agent_id)


def _execute_condition(tool_input: dict, project_path: str, agent_id: str) -> Any:
    """
    if/else 조건문 실행

    각 분기의 조건을 평가하고, 매칭되는 분기의 action을 실행한다.
    """
    branches = tool_input.get("branches", [])
    # ★2026-08-15: 조건 평가 실패를 삼키지 않는다. 옛 코드는 `except: continue` 로 다음
    # 분기에 넘어가 "모든 조건 불일치"라는 *정상 메시지*로 끝났다 — 조건이 거짓이어서
    # 안 걸린 건지 평가가 터진 건지 호출자가 구별할 수 없었다(침묵 실패 계열).
    cond_errors = []

    for branch in branches:
        condition = branch.get("condition")
        action = branch.get("action")

        if condition is None:
            # else 분기
            # ★B10 (2026-08-17 상상훈련 11회차): 앞선 조건 평가가 실패했다면(cond_errors)
            # else 실행은 "그 조건이 거짓이었다"는 단정이 된다 — B8(읽기 실패=조용한 거짓)이
            # 한 층 위에서 재발한 모양. 판정 불능 상태에선 else 를 보류하고 정직 실패로.
            if cond_errors:
                return {
                    "success": False,
                    "error": f"조건 평가 실패 {len(cond_errors)}건 — 판정 불능이라 else 분기를 보류했습니다"
                             "(else 실행=조건 거짓의 단정).",
                    "condition_errors": cond_errors,
                }
            if action:
                return _run_branch(action, tool_input, project_path, agent_id)
            return {"message": "else 분기 실행 (action 없음)"}

        # 조건 평가: sense 노드 실행
        try:
            sense_result = _evaluate_sense_condition(condition, project_path, agent_id)
        except Exception as e:
            cond_errors.append({"condition": condition, "error": str(e)})
            continue  # 이 분기는 판정 불능 — 다음 분기로 가되 위에 기록해 둔다

        if sense_result:
            if action:
                return _run_branch(action, tool_input, project_path, agent_id)
            return {"message": f"조건 충족: {condition}"}

    if cond_errors:
        # 어느 분기도 안 걸렸는데 평가 실패가 있었다면 그건 성공이 아니다.
        return {
            "success": False,
            "error": f"조건 평가 실패 {len(cond_errors)}건 — 어느 분기도 실행하지 못했습니다.",
            "condition_errors": cond_errors,
        }
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

    # source에서 sense 값 가져오기 — ★B10-case (2026-08-17 상상훈련 11회차 판정):
    # "값을 읽지 못함"(오타 경로·실행 실패=판정 불능)과 "필드는 실존하되 값이 null"
    # (정당한 부재 — 예: 데스크탑의 battery)을 구별한다. 전자에 default 를 실행하면
    # "어느 패턴과도 불일치"라는 단정이 된다(B10 else 위장의 case 짝). 후자는 default 가
    # 부재의 의미를 받는 정당한 용법이라 보존.
    sense_value, read_error = _get_sense_value_checked(source, project_path, agent_id)

    if read_error is not None:
        return {
            "success": False,
            "error": f"case source '{source}' 판정 불능 — {read_error} "
                     "default 실행을 보류했습니다(default 실행=값 불일치의 단정).",
        }

    if sense_value is not None:
        action = select_case_branch(sense_value, branches, default)
    else:
        action = default

    if action:
        return _run_branch(action, tool_input, project_path, agent_id)

    return {"message": f"case문 실행 완료 (source={source}, value={sense_value})"}


# ── [table:each] — 문장을 값으로 받는 유일한 변환자 (2026-08-15 고차 문장 M2) ──────────
# 왜 이 낱말이 필요했나: table 의 다른 13 변환자는 전부 데이터→데이터라, "찾은 것 *각각에*
# 대해 ~해라"를 이 언어로 쓸 방법이 없었다. 그래서 문장이 늘 "가져와서 정리해 사람에게"
# 2단에서 끝났고(코퍼스 실측: 파이프 평균 길이 2.45·2단이 72%), 항목 단위 싱크
# (notify_user·channel_send·delegate·publish)는 파이프에 한 번도 들어오지 못했다
# (미조합 액션 68/150 의 다수가 이 부류). 설계 정본: docs/HIGHER_ORDER_SENTENCE_DESIGN.md
_EACH_DEFAULT_LIMIT = 20

# 스칼라 행(문자열·숫자)을 dict 로 감쌀 때 쓰는 필드 이름.
# ★출력 감싸기와 $it 치환이 *같은* 이름을 봐야 한다 — 두 자리가 어긋나면
#   결과 행이 `{"value": "가", "_error": "행에 없는 필드: value"}` 처럼
#   필드를 보여주면서 없다고 말하는 자기모순이 난다(2026-08-17 실측 버그).
_EACH_SCALAR_FIELD = "value"
_EACH_MAX_SUBSTEPS = 200


def _each_escape(value: Any) -> str:
    """치환 값을 IBL 문자열 리터럴 안에 안전하게 넣을 형태로 만든다.

    파서(`ibl_parser_values._extract_string`)는 따옴표 안에서 `\\` 다음 글자를 리터럴로
    받으므로, 백슬래시와 양쪽 따옴표만 이스케이프하면 '…' / "…" 어느 쪽에 놓여도 문자열이
    조기 종료되지 않는다(제목에 따옴표가 든 행이 문장을 깨뜨리던 부류의 차단).
    """
    if value is None:
        return ""
    if isinstance(value, (dict, list)):
        s = json.dumps(value, ensure_ascii=False)
    else:
        s = str(value)
    return s.replace("\\", "\\\\").replace('"', '\\"').replace("'", "\\'")


def _each_substitute(sentence: str, row: Any, var: str) -> Tuple[str, list]:
    """문장 안의 `$it.필드` / `$it` 를 행 값으로 치환. 반환: (치환된 문장, 없는 필드 목록).

    ★없는 필드는 조용히 빈 값으로 만들지 않고 목록으로 돌려준다 — 호출자가 그 행을
    실패로 표시한다(빈 문자열로 밀어 넣으면 "성공처럼 보이는 오동작"이 된다).
    ★필드 패턴은 유니코드(`[^\\W\\d]\\w*`) — 옛 `[A-Za-z_]` 전용은 `$it.없는필드` 같은
    한글 필드가 매칭 밖이라 `$it` 만 치환되고 `.필드` 가 리터럴 잔존했다(F14-1, 14회차 실측:
    빈/쓰레기 쿼리가 _ok:true 로 완주).
    """
    missing: list = []

    def _sub(m):
        field = (m.group(1) or "").lstrip(".")
        if not field:
            return _each_escape(row)
        if isinstance(row, dict):
            if field not in row:
                missing.append(field)
                return m.group(0)
            return _each_escape(row.get(field))
        # 스칼라 행: 호출자가 출력에서 {_EACH_SCALAR_FIELD: row} 로 감싸므로
        # `$it.value` 도 그 값 자체로 푼다(`$it` 와 같은 뜻). 그 밖의 필드는 정직하게 없음.
        if field == _EACH_SCALAR_FIELD:
            return _each_escape(row)
        missing.append(field)
        return m.group(0)

    pattern = re.compile(r"\$" + re.escape(var) + r"((?:\.[^\W\d]\w*)?)")
    return pattern.sub(_sub, sentence), missing


def _each_foreign_vars(do: str, var: str) -> list:
    """do 문장 안에서 **해석되지 않을** `$변수` 이름 목록 (F14-1, 2026-08-20 14회차).

    행 참조(`$<var>`)·예약어 `$items`·do 안에서 자기 할당된 변수는 정상.
    그 밖의 `$이름` 은 어떤 행에서도 치환되지 않고 리터럴로 하류에 흘러간다 —
    14회차 실측: `as:"google"` 지정 후 `$it.title` 이 통째로 구글 검색어가 되어
    무관한 결과 30건이 success 로 완주했다(유령 변수의 침묵 통과).
    ★외부 파이프의 `$변수` 는 each 실행 전에 상위 해석기가 이미 치환하므로,
    여기 남은 것은 전부 오타/참조명 불일치다.
    """
    assigned = set(re.findall(r"\$([^\W\d]\w*)\s*=", do))
    foreign = []
    for m in re.finditer(r"\$([^\W\d]\w*)", do):
        name = m.group(1)
        if name == var or name == "items" or name in assigned:
            continue
        if name not in foreign:
            foreign.append(name)
    return foreign


def _stamp_depth(steps: Any, depth: int) -> None:
    """파싱된 step 들에 중첩 깊이를 찍는다(병렬 branches·폴백 체인 포함)."""
    if not isinstance(steps, list):
        return
    for st in steps:
        if not isinstance(st, dict):
            continue
        st["_depth"] = depth
        for key in ("branches", "_fallback_chain"):
            _stamp_depth(st.get(key), depth)


def _each_input_rows(params: dict) -> Tuple[Optional[list], Any]:
    """입력 통화(items)를 꺼낸다. 반환: (행 목록 또는 None, 파싱된 봉투).

    규약은 data-ops 변환자와 **같다**(2026-08-15 대칭 수리): 파이프 입력(`_prev_result`)이
    먼저이고, 그게 없을 때만 params 에서 통화를 직접 받는다 — 단독 호출·자가점검·
    리터럴 씨앗 지원. 옛 each 는 `_prev_result` 만 읽어, 다른 13 변환자가 전부 받는
    `items: [...]` 리터럴을 혼자 거부했다("받은 봉투: str"). 하필 문형을 곱셈으로 바꾸는
    유일한 고차 변환자가 항상 앞에 생산자를 요구하던 셈이다.
    """
    prev = params.get("_prev_result")
    obj = prev
    if isinstance(prev, str):
        s = prev.strip()
        obj = None
        if s.startswith("{") or s.startswith("["):
            try:
                obj = json.loads(s)
            except Exception:
                obj = prev          # JSON 아닌 문자열 — 아래에서 통화 없음으로 진단된다
        elif s:
            obj = prev
    if obj is None:                  # 파이프 입력 없음 → params 에서 통화 수용
        if params.get("items") is not None:
            obj = {"items": params["items"]}
        elif params.get("table") is not None:
            obj = {"table": params["table"]}

    if isinstance(obj, dict):
        from common.currency import derive_items
        obj = derive_items(obj)
        rows = obj.get("items")
        return (rows if isinstance(rows, list) else None), obj
    if isinstance(obj, list):
        return obj, obj
    return None, obj


def _execute_table_each(params: dict, project_path: str, agent_id: str = None) -> Any:
    """[table:each]{do, as, limit, on_error} — items 의 각 행에 IBL 문장을 적용.

    통화 계약: items → items. 각 출력 행 = 원 행 + `_ok` + (`_error` | `_result`).
    원 행을 보존하므로 `>> [table:filter]{where: {_ok: false}}` 로 실패만 추릴 수 있다.
    """
    from ibl_parser import parse as ibl_parse, IBLSyntaxError
    from workflow_engine import execute_pipeline

    do = params.get("do")
    if isinstance(do, list):
        do = "\n".join(str(x) for x in do if str(x).strip())
    if not do or not str(do).strip():
        return {"success": False, "items": [], "count": 0,
                "error": "each: do(각 행에 적용할 IBL 문장)가 필요합니다. "
                         "예) [table:each]{do: \"[self:notify_user]{message: '$it.title'}\"}"}
    do = str(do)
    var = (str(params.get("as") or "it").lstrip("$").strip()) or "it"

    # ★유령 변수 사전 차단 (F14-1): 어떤 행에서도 치환되지 않을 `$이름` 은 저작 오류라
    # 행 단위가 아니라 문장 단위로 즉시 거절한다 — 모든 행이 같은 이유로 실패할 운명이고,
    # 옛 동작(리터럴 잔존→하류 실행)은 "성공처럼 보이는 오동작"이었다.
    foreign = _each_foreign_vars(do, var)
    if foreign:
        return {"success": False, "items": [], "count": 0,
                "error": (f"each: do 안에 해석되지 않는 변수 "
                          f"{', '.join('$' + f for f in foreign)} — 행 참조 이름은 '${var}'"
                          f"{' (as 로 지정됨)' if var != 'it' else ''} 입니다. "
                          f"행 값은 '${var}.필드' 로 참조하세요.")}

    rows, envelope = _each_input_rows(params)
    if rows is None:
        shape = (list(envelope.keys())[:8] if isinstance(envelope, dict)
                 else type(envelope).__name__)
        return {"success": False, "items": [], "count": 0,
                "error": f"each: 입력에서 items 통화를 찾지 못했습니다. 받은 봉투: {shape} — "
                         f"each 는 목록의 각 행에 문장을 적용합니다. 파이프(>>) 뒤에 놓거나, "
                         f"단독으로 쓰려면 items 를 직접 주세요. "
                         f'예: [table:each]{{items: [{{"city": "서울"}}], do: "[sense:weather]{{city: \'$it.city\'}}"}}'}

    try:
        limit = int(params.get("limit") if params.get("limit") is not None else _EACH_DEFAULT_LIMIT)
    except (TypeError, ValueError):
        limit = _EACH_DEFAULT_LIMIT
    if limit < 0:
        limit = _EACH_DEFAULT_LIMIT
    on_error = str(params.get("on_error") or "continue").strip().lower()
    depth = int(params.get("_depth") or 0)

    target = rows[:limit]
    skipped = max(0, len(rows) - len(target))
    out_items: list = []
    ok_n = err_n = substeps = 0
    halted: Optional[str] = None

    for idx, row in enumerate(target):
        base = dict(row) if isinstance(row, dict) else {_EACH_SCALAR_FIELD: row}

        sentence, missing = _each_substitute(do, row, var)
        if missing:
            err_n += 1
            avail = sorted(row.keys())[:12] if isinstance(row, dict) else [_EACH_SCALAR_FIELD]
            out_items.append({**base, "_ok": False,
                              "_error": (f"행에 없는 필드: {', '.join(sorted(set(missing)))} "
                                         f"(행 필드: {avail})")})
            if on_error == "stop":
                halted = "on_error"
                break
            continue

        try:
            steps = ibl_parse(sentence)
        except IBLSyntaxError as e:
            err_n += 1
            out_items.append({**base, "_ok": False, "_error": f"IBL 문법 오류: {e}"})
            if on_error == "stop":
                halted = "on_error"
                break
            continue

        substeps += len(steps)
        if substeps > _EACH_MAX_SUBSTEPS:
            halted = "budget"
            break

        _stamp_depth(steps, depth + 1)
        try:
            res = execute_pipeline(steps, project_path, agent_id=agent_id)
        except Exception as e:  # 실행기 자체가 터진 경우도 행 단위로 정직하게
            res = {"success": False, "error": f"{type(e).__name__}: {e}"}

        final = res.get("final_result") if isinstance(res, dict) else res
        if isinstance(final, str):
            s2 = final.strip()
            if s2.startswith("{") or s2.startswith("["):
                try:
                    final = json.loads(s2)
                except Exception:
                    pass

        if isinstance(res, dict) and not res.get("success", True):
            err_n += 1
            out_items.append({**base, "_ok": False,
                              "_error": res.get("error") or "실행 실패",
                              "_result": final})
            if on_error == "stop":
                halted = "on_error"
                break
        else:
            ok_n += 1
            out_items.append({**base, "_ok": True, "_result": final})

    # 중단 시 남은 행은 '처리 안 함'으로 정직하게 집계 (조용히 사라지지 않게)
    if halted:
        skipped += len(target) - len(out_items)

    out: Dict[str, Any] = {
        "items": out_items,
        "count": len(out_items),
        "ok_count": ok_n,
        "error_count": err_n,
    }
    notes = []
    if skipped:
        if halted == "budget":
            notes.append(f"하위 스텝 예산({_EACH_MAX_SUBSTEPS}) 초과로 중단 — {skipped}건 미처리")
        elif halted == "on_error":
            notes.append(f"on_error=stop 으로 중단 — {skipped}건 미처리")
        else:
            notes.append(f"limit={limit} 로 앞에서 잘랐습니다 — {skipped}건 미처리")
        out["skipped"] = skipped
    # 전 행 실패만 상위로 전파한다. 부분 실패는 파이프를 끊지 않되 반드시 보이게 한다.
    if out_items and ok_n == 0:
        out["success"] = False
        out["error"] = (f"each: {err_n}건 전부 실패 — 첫 오류: "
                        f"{out_items[0].get('_error')}")
    elif not out_items:
        if not rows:
            # ★F17 (2026-08-17 상상훈련 12회차): 입력 0행은 실수가 아니라 정당한 빈손 —
            # 0회 실행=성공(공허 참)으로 0건 통화를 내려 파이프가 완주하게 한다.
            # take/filter 는 빈손을 통과시키는데 each 만 실패로 파이프를 끊던 비대칭
            # (검색 0건 >> each >> flatten 이 step 3 에서 죽던 실측, P14 빈손 계약 정합).
            out["success"] = True
            out["message"] = "each: 입력 0행 — 실행 0회 (빈 목록)"
        else:
            out["success"] = False
            out["error"] = f"each: limit={limit} 로 처리한 행이 없습니다 — limit 을 확인하세요."
    else:
        out["success"] = True
        if err_n:
            notes.append(f"{err_n}/{len(out_items)}건 실패 (성공 {ok_n}) — _ok:false 행의 _error 참조")
    if notes:
        out["message"] = " / ".join(notes)
    return out


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

    # F13-4 (2026-08-19 상상훈련 13회차): 검침판으로 — 판정 불능 사유(필드 경로 부재 시
    # 사용 가능한 필드 목록 동반)를 버리지 않고 오류문에 싣는다.
    value, _read_err = _get_sense_value_checked(source_expr, project_path, agent_id)

    if value is None:
        # ★2026-08-16 상상훈련 9회차: 비교 연산이 있는데 좌변 값을 못 읽었다면(경로 오타·
        # 필드 부재) "조건 거짓"과 "읽기 실패"는 다른 상태다 — 조용한 거짓으로 접으면
        # goal.md 의 낡은 경로(.current_price)가 항상-거짓으로 몇 달을 살았듯 오독이
        # 영속한다. 예외로 던져 _execute_condition 의 cond_errors 정직 채널을 태운다.
        # 연산자 없는 불리언 평가는 None=falsy 유지(부재의 거짓은 정당한 의미).
        if op is not None:
            raise ValueError(
                f"조건 좌변 '{source_expr}' 에서 값을 읽지 못했습니다 — "
                + (_read_err if _read_err else
                   "필드 경로를 확인하세요(예: stock quote 는 .data.current_price — "
                   "봉투 최상위가 아닙니다)."))
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


_FIELD_MISSING = object()  # 경로 부재 표지 — "값이 null"(정당한 부재)과 구별 (★B10-case)


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
    판정 불능 사유가 필요한 호출자는 _get_sense_value_checked 를 쓴다.
    """
    value, _err = _get_sense_value_checked(source, project_path, agent_id)
    return value


def _get_sense_value_checked(source: str, project_path: str, agent_id: str) -> Tuple[Any, Optional[str]]:
    """_get_sense_value 의 검침판 — (값, 판정불능 사유)를 돌려준다.

    ★B10-case (2026-08-17 상상훈련 11회차): 판정 불능(파싱 실패·실행 예외·필드 경로
    부재)과 "필드는 실존하되 값이 null"(정당한 부재)을 구별한다 — 후자는 (None, None).
    옛 코드는 셋 다 None 으로 접어 case 의 default 가 판정 불능을 "불일치"로 단정했다.
    """
    parsed = _parse_source_ref(source)
    if parsed is None:
        return None, f"source 표현을 해석하지 못했습니다: '{source}'."
    node, action, params, field = parsed

    try:
        from ibl_engine import execute_ibl
        step = {"_node": node, "action": action, "params": params}
        result = execute_ibl(step, project_path, agent_id)
    except Exception as e:
        return None, f"'{node}:{action}' 실행 실패: {e}."

    # 핸들러 다수가 JSON *문자열* 봉투를 반환한다 — 파싱 없이 점 추출하면 문자열에
    # 막혀 None → 조건이 조용히 거짓이 된다(센서 필드 조건 전멸 부류).
    if isinstance(result, str):
        try:
            _p = json.loads(result)
            if isinstance(_p, (dict, list)):
                result = _p
        except Exception:
            pass

    if field is not None:
        value = _extract_dotted_field_checked(result, field)
        if value is _FIELD_MISSING:
            # F13-4 (2026-08-19 상상훈련 13회차): 사용 가능한 경로를 동반한다 —
            # filter/sort 오류문 선례. 없으면 자가교정에 단독 프로브 1왕복이 더 든다.
            hints = _field_path_hints(result)
            hint_txt = f" 사용 가능한 필드: {hints}" if hints else ""
            return None, (f"필드 경로 '.{field}' 가 결과에 없습니다 — 경로를 확인하세요"
                          f"(예: stock quote 는 .data.current_price — 봉투 최상위가 아닙니다).{hint_txt}")
        return value, None

    if isinstance(result, dict):
        return result.get("value", result.get("result", str(result))), None
    return result, None


def _field_path_hints(result: Any, max_paths: int = 24) -> List[str]:
    """조건 소스 결과에서 쓸 수 있는 점 경로 후보 — 최상위 + 1단 중첩 (F13-4).

    스칼라 값 경로만 후보로 낸다(dict 중간 노드는 자식 경로가 대신 말한다).
    items 같은 리스트 키는 경로 폭발이라 이름만 싣는다.
    """
    hints: List[str] = []
    if not isinstance(result, dict):
        return hints
    for k, v in result.items():
        if not isinstance(k, str) or k.startswith("_"):
            continue
        if isinstance(v, dict):
            sub = [f"{k}.{sk}" for sk, sv in v.items()
                   if isinstance(sk, str) and not isinstance(sv, (dict, list))]
            hints.extend(sub if sub else [k])
        else:
            hints.append(k)
        if len(hints) >= max_paths:
            break
    return hints[:max_paths]


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
    value = _extract_dotted_field_checked(result, field_path)
    return None if value is _FIELD_MISSING else value


def _extract_dotted_field_checked(result: Any, field_path: str) -> Any:
    """점 표기 추출의 검침판 — 경로 부재는 _FIELD_MISSING, 값이 진짜 null 이면 None.

    중간 노드가 null 이거나 dict 가 아니면 그 아래 경로는 "부재"다(★B10-case).
    """
    current = result
    for key in field_path.split('.'):
        if not isinstance(current, dict) or key not in current:
            return _FIELD_MISSING
        current = current[key]
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
