"""
system_ai_plans.py - 작업계획서(Plan) 및 스케줄 실행 모듈
IndieBiz OS Core

시스템 AI의 작업계획서 생성, 파싱, 실행, 상태 관리 및
스케줄(지연/반복/특정 시각) 실행 기능을 담당합니다.

주요 기능:
- 작업계획서 레지스트리: fire-and-forget 패턴에서 에이전트 완료 후 다음 단계 자동 트리거
- 작업계획서 생성/파싱/실행/상태 업데이트
- 스케줄 실행: 지연(타이머), 특정 시각, 반복 모드 지원
"""

import json
from pathlib import Path
from typing import Dict
from datetime import datetime

# 경로 설정
BACKEND_PATH = Path(__file__).parent
from runtime_utils import get_base_path as _get_base_path
DATA_PATH = _get_base_path() / "data"


# ============ 작업계획서 실행 레지스트리 ============
# fire-and-forget 패턴에서 에이전트 완료 후 다음 단계를 자동 트리거하기 위한 레지스트리.
# Key: (project_id, agent_id), Value: {"plan_file": str, "step_number": int, "total_steps": int}
import threading as _threading
_active_plan_steps: Dict[tuple, dict] = {}
_plan_steps_lock = _threading.Lock()


def register_plan_step(project_id: str, agent_id: str,
                       plan_file: str, step_number: int, total_steps: int):
    """작업계획서의 현재 실행 중인 단계를 레지스트리에 등록."""
    with _plan_steps_lock:
        _active_plan_steps[(project_id, agent_id)] = {
            "plan_file": plan_file,
            "step_number": step_number,
            "total_steps": total_steps,
        }
    print(f"[PlanRegistry] 등록: ({project_id}/{agent_id}) → 단계 {step_number}/{total_steps}")


def on_agent_plan_step_complete(project_id: str, agent_id: str, result_text: str):
    """에이전트가 작업계획서 단계를 완료했을 때 호출.

    - 레지스트리에서 활성 단계 정보를 꺼냄
    - 계획서 상태를 '완료' 또는 '실패'로 업데이트
    - 다음 '대기' 단계가 있으면 별도 스레드에서 자동 실행
    """
    with _plan_steps_lock:
        key = (project_id, agent_id)
        step_info = _active_plan_steps.pop(key, None)

    if not step_info:
        return  # 이 에이전트에 활성 계획서 단계 없음

    plan_file = step_info["plan_file"]
    step_number = step_info["step_number"]

    # 결과 텍스트 정리 (너무 길면 잘라냄)
    result_summary = (result_text or "")[:2000]

    # 에러인지 확인
    is_error = result_summary.startswith("[오류]")

    # 단계 상태 업데이트
    new_status = "실패" if is_error else "완료"
    _update_plan_status(plan_file, step_number, new_status, result_text=result_summary)
    print(f"[PlanRegistry] 단계 {step_number} {new_status}: {plan_file}")

    if is_error:
        print(f"[PlanRegistry] 단계 실패로 인해 다음 단계 진행하지 않음")
        return  # 실패 시 다음 단계로 진행하지 않음

    # 다음 단계 자동 실행 (별도 스레드)
    def _trigger_next_step():
        import time as _time
        _time.sleep(2)  # 에이전트 정리 시간
        try:
            result = _execute_plan(
                {"file": plan_file, "context": result_summary},
                agent_id=None,
                project_path=None
            )
            result_data = json.loads(result)
            if result_data.get("all_done"):
                print(f"[PlanRegistry] 작업계획서 전체 완료: {plan_file}")
            elif result_data.get("success"):
                print(f"[PlanRegistry] 다음 단계 시작: {result_data.get('step_title')}")
            else:
                print(f"[PlanRegistry] 다음 단계 실행 실패: {result_data.get('error')}")
        except Exception as e:
            import traceback
            traceback.print_exc()
            print(f"[PlanRegistry] 다음 단계 트리거 실패: {e}")

    next_thread = _threading.Thread(target=_trigger_next_step, daemon=True)
    next_thread.start()


def _execute_schedule(params: dict, agent_id: str = None, project_path: str = None) -> str:
    """[self:schedule] — 미래 실행 통합 액션

    "N분 후에 해줘", "매일 9시에 해줘", "내일 3시에 해줘" 모두 이 하나로 처리.
    target_project_id / target_agent_id를 지정하면 다른 에이전트의 스케줄로 등록 (크로스 위임).

    동작 모드 (파라미터에 따라 자동 결정):
    1. minutes/seconds 있으면 → 지연 실행 (타이머 + 캘린더 백업)
    2. date/time만 있으면 → 특정 시각 1회 실행
    3. repeat 있으면 → 반복 실행

    파라미터:
        pipeline: 실행할 IBL 코드 (필수)
        minutes: 지연 시간 (분) — 지연 모드
        seconds: 지연 시간 (초) — 지연 모드
        date: 실행 날짜 (YYYY-MM-DD) — 특정 시각 모드
        time: 실행 시각 (HH:MM) — 특정 시각/반복 모드
        repeat: 반복 유형 (daily/weekly/monthly/yearly/interval)
        title: 이벤트 제목 (선택)
        weekdays: 요일 목록 (weekly일 때, 0=월 ~ 6=일)
        interval_hours: 반복 간격 (interval일 때)
        target_project_id: 대상 에이전트의 프로젝트 ID (크로스 위임 시)
        target_agent_id: 대상 에이전트 ID (크로스 위임 시)
    """
    import threading
    from datetime import datetime, timedelta
    from calendar_manager import get_calendar_manager

    # pipeline 또는 code 둘 다 허용 (AI가 자주 혼동하므로)
    pipeline = params.get("pipeline", "") or params.get("code", "")
    if not pipeline:
        return json.dumps({"success": False, "error": "pipeline은 필수입니다. 실행할 IBL 코드를 지정하세요."}, ensure_ascii=False)

    # 'at' 통합 파라미터: "2026-03-10 09:00" 또는 "09:00" 또는 "2026-03-10T09:00:00"
    # date/time을 각각 지정하지 않아도 at 하나로 처리
    at_param = params.get("at", "")
    if at_param and not params.get("date") and not params.get("time"):
        try:
            at_str = at_param.replace("T", " ")
            if " " in at_str:
                parsed = datetime.fromisoformat(at_param.replace(" ", "T"))
                params["date"] = parsed.strftime("%Y-%m-%d")
                params["time"] = parsed.strftime("%H:%M")
            else:
                # 시간만 지정된 경우: "09:00" → 오늘 날짜
                params["time"] = at_str[:5]
        except (ValueError, TypeError):
            pass

    minutes = params.get("minutes", 0)
    seconds = params.get("seconds", 0)
    repeat = params.get("repeat", "none")
    title = params.get("title", pipeline[:40])
    cm = get_calendar_manager()

    # ── owner 결정: target이 지정되면 크로스 위임, 아니면 셀프 ──
    target_project_id = params.get("target_project_id", "")
    target_agent_id = params.get("target_agent_id", "")

    if target_project_id or target_agent_id:
        # 크로스 위임: 다른 에이전트의 스케줄로 등록
        project_id = target_project_id or "__system_ai__"
        owner_agent = target_agent_id or ""

        # target_agent_id가 없으면 프로젝트의 에이전트를 자동 결정
        if not owner_agent and project_id and project_id != "__system_ai__":
            try:
                import yaml
                from project_manager import ProjectManager
                pm = ProjectManager()
                _proj_path = pm.get_project_path(project_id)
                if _proj_path:
                    _agents_file = _proj_path / "agents.yaml"
                    if _agents_file.exists():
                        with open(_agents_file, 'r', encoding='utf-8') as f:
                            _agents_data = yaml.safe_load(f)
                        _active_agents = [a for a in _agents_data.get("agents", [])
                                          if a.get("active", True)]
                        if len(_active_agents) == 1:
                            # 에이전트가 하나뿐이면 자동 선택
                            owner_agent = _active_agents[0].get("name") or _active_agents[0].get("id", "")
                            print(f"[Schedule] 에이전트 자동 결정: {project_id} → {owner_agent} (유일한 에이전트)")
                        elif len(_active_agents) > 1:
                            # 여러 에이전트가 있으면 첫 번째를 기본으로
                            owner_agent = _active_agents[0].get("name") or _active_agents[0].get("id", "")
                            print(f"[Schedule] 에이전트 자동 결정: {project_id} → {owner_agent} (첫 번째 에이전트, {len(_active_agents)}개 중)")
            except Exception as e:
                print(f"[Schedule] 에이전트 자동 결정 실패: {e}")

        print(f"[Schedule] 크로스 위임: {agent_id} → {project_id}/{owner_agent}")
    else:
        # 셀프: 호출한 에이전트 자신의 스케줄
        # 시스템 AI 판별: agent_id가 "system_ai"이거나, project_path가 data/ 디렉토리인 경우
        _is_system_ai_caller = (agent_id == "system_ai")
        if not _is_system_ai_caller and project_path and project_path != ".":
            from pathlib import Path as _Path
            _pp = _Path(project_path)
            # data 디렉토리면 시스템 AI (projects/ 하위가 아님)
            _is_system_ai_caller = (_pp.name == "data" or _pp.name == "system_ai"
                                    or "projects" not in str(_pp))

        if _is_system_ai_caller:
            project_id = "__system_ai__"
        else:
            # project_path에서 project_id 추출 (예: ".../projects/투자" → "투자")
            project_id = ""
            if project_path and project_path != ".":
                from pathlib import Path as _Path
                project_id = _Path(project_path).name
            if not project_id:
                project_id = "__system_ai__"
        owner_agent = agent_id

    try:
        total_seconds = float(minutes) * 60 + float(seconds)
    except (ValueError, TypeError):
        total_seconds = 0

    # ── 모드 판별 ──
    is_delay = total_seconds > 0
    is_recurring = repeat and repeat != "none"

    if is_delay:
        # ── 지연 모드: N분/초 후 실행 ──
        if total_seconds > 86400:
            return json.dumps({"success": False, "error": "지연은 24시간 이내만 가능합니다."}, ensure_ascii=False)

        execute_at = datetime.now() + timedelta(seconds=total_seconds)
        execute_date = execute_at.strftime("%Y-%m-%d")
        execute_time_hm = execute_at.strftime("%H:%M")
        execute_at_str = execute_at.strftime("%H:%M:%S")

        # 캘린더 이벤트 등록 (영속성)
        event_id = None
        try:
            event = cm.add_event(
                title=title,
                event_date=execute_date,
                event_type="schedule",
                repeat="none",
                event_time=execute_time_hm,
                action="run_pipeline",
                action_params={"pipeline": pipeline},
                owner_project_id=project_id,
                owner_agent_id=owner_agent or ("system_ai" if project_id == "__system_ai__" else ""),
            )
            event_id = event.get("id")
        except Exception as e:
            print(f"[Schedule] 캘린더 등록 실패: {e}")

        # 타이머 시작 (정밀 실행) — owner 컨텍스트에서 실행
        # 크로스 위임 시: 호출자(A)의 path가 아니라 target(B)의 path를 써야 함
        # project_id로 resolve하도록 "."로 설정 → _delayed_run에서 ProjectManager로 해결
        _is_cross = bool(target_project_id or target_agent_id)
        _timer_project_path = "." if _is_cross else (project_path or ".")
        _timer_project_id = project_id
        _timer_agent_id = owner_agent or agent_id

        def _delayed_run():
            try:
                from ibl_parser import parse as ibl_parse
                from workflow_engine import execute_pipeline

                if event_id:
                    try:
                        get_calendar_manager().update_event(event_id, enabled=False)
                    except Exception:
                        pass

                # owner의 project_path에서 실행
                run_path = _timer_project_path
                if run_path == "." and _timer_project_id and _timer_project_id != "__system_ai__":
                    try:
                        from project_manager import ProjectManager
                        pm = ProjectManager()
                        resolved = pm.get_project_path(_timer_project_id)
                        if resolved and resolved.exists():
                            run_path = str(resolved)
                    except Exception:
                        pass

                print(f"[Schedule] ⏰ 타이머 만료, 실행: {pipeline[:80]}... (context: {_timer_project_id}/{_timer_agent_id})")
                steps = ibl_parse(pipeline)
                if steps:
                    result = execute_pipeline(steps, run_path, agent_id=_timer_agent_id)
                    print(f"[Schedule] 완료: success={result.get('success')}")

                    # 결과를 owner의 대화창에 전달
                    if result.get("success") and (_timer_project_id or _timer_agent_id):
                        try:
                            task_for_delivery = {
                                "title": title,
                                "owner_project_id": _timer_project_id,
                                "owner_agent_id": _timer_agent_id,
                                "action_params": {"pipeline": pipeline},
                            }
                            cm._deliver_result_to_chat(task_for_delivery, _timer_agent_id, pipeline, result)
                        except Exception as e:
                            print(f"[Schedule] 결과 전달 실패: {e}")
            except Exception as e:
                print(f"[Schedule] 실행 실패: {e}")

        timer = threading.Timer(total_seconds, _delayed_run)
        timer.daemon = True
        timer.start()

        if minutes >= 1:
            display = f"{int(minutes)}분" + (f" {int(seconds)}초" if seconds else "")
        else:
            display = f"{int(total_seconds)}초"

        print(f"[Schedule] {display} 후 ({execute_at_str}) 실행 예정 — {pipeline[:60]}")

        return json.dumps({
            "success": True,
            "message": f"{display} 후({execute_at_str})에 실행 예약됨",
            "execute_at": execute_at_str,
            "event_id": event_id
        }, ensure_ascii=False)

    else:
        # ── 특정 시각 / 반복 모드 ──
        event_date = params.get("date")
        event_time = params.get("time")

        # start_time 호환: "2026-03-09T17:44:00" 형태 자동 파싱
        start_time = params.get("start_time")
        if start_time and (not event_date or not event_time):
            try:
                parsed = datetime.fromisoformat(start_time)
                if not event_date:
                    event_date = parsed.strftime("%Y-%m-%d")
                if not event_time:
                    event_time = parsed.strftime("%H:%M")
            except (ValueError, TypeError):
                pass

        # time 파라미터에 full datetime이 들어온 경우 정규화
        # "2026-03-10 09:00:00" → date="2026-03-10", time="09:00"
        if event_time and " " in event_time:
            try:
                parsed = datetime.fromisoformat(event_time.replace(" ", "T"))
                if not event_date:
                    event_date = parsed.strftime("%Y-%m-%d")
                event_time = parsed.strftime("%H:%M")
            except (ValueError, TypeError):
                # 공백 뒤만 추출 (fallback)
                event_time = event_time.split()[-1][:5]
        elif event_time and "T" in event_time:
            try:
                parsed = datetime.fromisoformat(event_time)
                if not event_date:
                    event_date = parsed.strftime("%Y-%m-%d")
                event_time = parsed.strftime("%H:%M")
            except (ValueError, TypeError):
                pass
        # HH:MM:SS → HH:MM 정규화
        elif event_time and len(event_time) == 8 and event_time.count(":") == 2:
            event_time = event_time[:5]

        if not event_time and not is_recurring:
            return json.dumps({"success": False, "error": "time(HH:MM) 또는 minutes가 필요합니다."}, ensure_ascii=False)

        if not event_date and not is_recurring:
            event_date = datetime.now().strftime("%Y-%m-%d")

        try:
            event = cm.add_event(
                title=title,
                event_date=event_date,
                event_type="schedule",
                repeat=repeat,
                event_time=event_time,
                action="run_pipeline",
                action_params={"pipeline": pipeline},
                owner_project_id=project_id,
                owner_agent_id=owner_agent or ("system_ai" if project_id == "__system_ai__" else ""),
                weekdays=params.get("weekdays"),
                interval_hours=params.get("interval_hours"),
            )
            event_id = event.get("id")

            if is_recurring:
                msg = f"반복 스케줄 등록됨 ({repeat}, {event_time or '설정됨'})"
            else:
                msg = f"{event_date} {event_time}에 실행 예약됨"

            print(f"[Schedule] 이벤트 등록: {event_id} — {msg}")

            return json.dumps({
                "success": True,
                "message": msg,
                "event_id": event_id
            }, ensure_ascii=False)
        except Exception as e:
            return json.dumps({"success": False, "error": str(e)}, ensure_ascii=False)


def _execute_create_plan(params: dict, agent_id: str = None, project_path: str = None) -> str:
    """[self:create_plan] — 구조화된 작업계획서 생성

    AI가 읽고 실행할 수 있는 형식의 작업계획서를 생성합니다.
    각 단계에 상태 마커가 있어서 실행 후 업데이트되고,
    다음 에이전트는 상태를 보고 자기 차례를 판단합니다.

    파라미터:
        file: 저장할 파일 경로 (필수)
        title: 계획서 제목
        goal: 전체 목표 설명
        steps: 단계 목록 (list of dict)
            각 단계: {
                agent_project_id: 실행할 에이전트의 프로젝트 ID,
                agent_id: 실행할 에이전트 ID,
                title: 단계 제목,
                description: 상세 지시,
                pipeline: 실행할 IBL 코드 (선택),
                on_failure: 실패 시 지시 (선택),
                max_retries: 최대 재시도 횟수 (기본 2)
            }
    """
    from pathlib import Path as _Path
    from datetime import datetime

    plan_file = params.get("file", "")
    title = params.get("title", "작업계획서")
    goal = params.get("goal", "")
    steps = params.get("steps", [])

    if not plan_file:
        return json.dumps({"success": False, "error": "file 파라미터가 필요합니다."}, ensure_ascii=False)
    if not steps:
        return json.dumps({"success": False, "error": "steps 파라미터가 필요합니다."}, ensure_ascii=False)

    # 파일 경로 해석
    file_path = _Path(plan_file)
    if not file_path.is_absolute():
        base = _Path(project_path) if project_path and project_path != "." else DATA_PATH
        file_path = base / plan_file

    # ── 작업계획서 마크다운 생성 ──
    lines = []
    lines.append(f"# {title}")
    lines.append(f"")
    lines.append(f"- **생성**: {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    lines.append(f"- **상태**: 대기중")
    if goal:
        lines.append(f"- **목표**: {goal}")
    lines.append(f"")
    lines.append(f"---")
    lines.append(f"")

    # ── 필수 필드 검증 ──
    errors = []
    for i, step in enumerate(steps, 1):
        agent_proj = step.get("agent_project_id", "")
        agent = step.get("agent_id", "")
        if not agent_proj or not agent:
            errors.append(f"단계 {i}: agent_project_id와 agent_id는 필수입니다. "
                          f"(현재: project='{agent_proj}', agent='{agent}'). "
                          f"[others:list_projects]로 프로젝트/에이전트 목록을 확인하세요.")
    if errors:
        return json.dumps({
            "success": False,
            "error": "작업계획서 단계에 담당 에이전트가 지정되지 않았습니다.",
            "details": errors,
            "hint": "각 step에 agent_project_id(프로젝트 ID)와 agent_id(에이전트 ID)를 반드시 지정하세요. "
                     "read_guide('작업계획서')로 가이드를 읽고, "
                     "[others:list_projects]로 프로젝트/에이전트 목록을 확인하세요."
        }, ensure_ascii=False)

    # ── description 품질 검증 ──
    import re as _re
    quality_warnings = []
    for i, step in enumerate(steps, 1):
        desc = step.get("description", "")
        step_title = step.get("title", f"단계 {i}")

        # 빈 description 체크
        if not desc or len(desc.strip()) < 10:
            quality_warnings.append(
                f"단계 {i}({step_title}): description이 너무 짧습니다 ({len(desc.strip())}자). "
                f"담당 에이전트가 무엇을 해야 하는지 구체적으로 적어주세요.")

        # IBL 코드 패턴 감지
        elif _re.search(r'\[(?:self|sense|limbs|engines|data|others):', desc):
            quality_warnings.append(
                f"단계 {i}({step_title}): description에 IBL 코드가 포함되어 있습니다. "
                f"자연어로 의도를 전달하세요. 담당 에이전트가 실행 방법은 자기 맥락으로 판단합니다.")

        # 제네릭한 description 체크
        elif len(desc.strip()) < 30:
            quality_warnings.append(
                f"단계 {i}({step_title}): description이 짧습니다 ({len(desc.strip())}자). "
                f"더 구체적으로 작성하면 결과 품질이 높아집니다.")

    if quality_warnings:
        # 경고는 반환하되 생성은 계속 진행 (에러가 아닌 경고)
        print(f"[CreatePlan] 품질 경고: {quality_warnings}")

    for i, step in enumerate(steps, 1):
        step_title = step.get("title", f"단계 {i}")
        agent_proj = step.get("agent_project_id", "")
        agent = step.get("agent_id", "")
        desc = step.get("description", "")
        pipeline = step.get("pipeline", "")
        on_failure = step.get("on_failure", "보고하고 중단")
        max_retries = step.get("max_retries", 2)

        lines.append(f"## 단계 {i}: {step_title}")
        lines.append(f"")
        lines.append(f"- **상태**: [ ] 대기")
        lines.append(f"- **담당**: project={agent_proj}, agent={agent}")
        lines.append(f"- **최대재시도**: {max_retries}")
        lines.append(f"- **시도횟수**: 0")
        lines.append(f"")

        if desc:
            lines.append(f"### 지시사항")
            lines.append(f"{desc}")
            lines.append(f"")

        if pipeline:
            lines.append(f"### 실행 코드")
            lines.append(f"```ibl")
            lines.append(f"{pipeline}")
            lines.append(f"```")
            lines.append(f"")

        lines.append(f"### 실패 시")
        lines.append(f"{on_failure}")
        lines.append(f"")

        lines.append(f"### 결과")
        lines.append(f"_(미실행)_")
        lines.append(f"")
        lines.append(f"---")
        lines.append(f"")

    # 실행 가이드
    lines.append(f"## 실행 규칙")
    lines.append(f"")
    lines.append(f"이 계획서는 `[self:execute_plan]`으로 실행합니다.")
    lines.append(f"시스템이 자동으로 순차 실행합니다:")
    lines.append(f"1. 상태가 `[ ] 대기`인 가장 빠른 단계를 찾아 담당 에이전트에게 전달")
    lines.append(f"2. 에이전트는 자기 단계의 지시사항만 받아서 실행")
    lines.append(f"3. 완료되면 시스템이 상태를 업데이트하고 다음 단계로 진행")
    lines.append(f"4. 상태 마커: `[ ] 대기` → `[~] 진행중` → `[v] 완료` 또는 `[x] 실패`")

    content = "\n".join(lines)

    try:
        file_path.parent.mkdir(parents=True, exist_ok=True)
        file_path.write_text(content, encoding='utf-8')
        print(f"[CreatePlan] 작업계획서 생성: {file_path} ({len(steps)}단계)")

        result = {
            "success": True,
            "file": str(file_path),
            "title": title,
            "steps_count": len(steps),
            "message": f"작업계획서 '{title}' 생성 완료 ({len(steps)}단계)"
        }
        if quality_warnings:
            result["quality_warnings"] = quality_warnings
            result["message"] += (
                f" (품질 경고 {len(quality_warnings)}건 — "
                f"read_guide('작업계획서')로 가이드를 참고하여 개선하세요)")
        return json.dumps(result, ensure_ascii=False)
    except Exception as e:
        return json.dumps({"success": False, "error": f"파일 저장 실패: {e}"}, ensure_ascii=False)


def _update_plan_status(file_path: str, step_number: int,
                        status: str, result_text: str = "",
                        increment_retry: bool = False) -> bool:
    """작업계획서의 특정 단계 상태를 업데이트

    Args:
        file_path: 계획서 파일 경로
        step_number: 단계 번호 (1부터)
        status: 새 상태 ("진행중", "완료", "실패")
        result_text: 결과 섹션에 기록할 텍스트
        increment_retry: True면 시도횟수를 +1
    """
    import re
    from pathlib import Path as _Path

    fp = _Path(file_path)
    if not fp.exists():
        return False

    content = fp.read_text(encoding='utf-8')

    # 상태 마커 매핑
    status_markers = {
        "대기": "[ ] 대기",
        "진행중": "[~] 진행중",
        "완료": "[v] 완료",
        "실패": "[x] 실패",
    }
    new_marker = status_markers.get(status, f"[?] {status}")

    # 해당 단계 섹션 찾기
    step_header = f"## 단계 {step_number}:"
    lines = content.split('\n')
    in_target_step = False
    updated = False

    for i, line in enumerate(lines):
        if line.startswith(step_header):
            in_target_step = True
            continue

        if in_target_step and line.startswith("## 단계 "):
            # 다음 단계에 도달
            break

        if in_target_step:
            # 상태 마커 업데이트
            if line.startswith("- **상태**:"):
                lines[i] = f"- **상태**: {new_marker}"
                updated = True

            # 시도횟수 업데이트
            if increment_retry and line.startswith("- **시도횟수**:"):
                try:
                    current = int(line.split(":")[1].strip())
                    lines[i] = f"- **시도횟수**: {current + 1}"
                except (ValueError, IndexError):
                    lines[i] = f"- **시도횟수**: 1"

            # 결과 섹션 업데이트
            if result_text and line.strip() == "_(미실행)_":
                lines[i] = result_text

    # 모든 단계가 완료되었는지 확인 → 전체 상태 업데이트
    all_done = True
    any_failed = False
    for line in lines:
        if "- **상태**: [ ] 대기" in line or "- **상태**: [~] 진행중" in line:
            all_done = False
        if "- **상태**: [x] 실패" in line:
            any_failed = True

    if all_done:
        for i, line in enumerate(lines):
            if line.startswith("- **상태**:") and "완료" not in line and "실패" not in line and "진행중" not in line and "대기" not in line:
                continue
            if line == "- **상태**: 대기중":
                lines[i] = f"- **상태**: {'일부실패' if any_failed else '완료'}"
                break

    if updated:
        fp.write_text('\n'.join(lines), encoding='utf-8')

    return updated


def _parse_plan_steps(plan_content: str) -> list:
    """작업계획서 마크다운을 파싱하여 단계 목록 반환.

    Returns:
        [{"number": 1, "title": "...", "status": "대기",
          "project_id": "...", "agent_id": "...",
          "description": "...", "pipeline": "...",
          "on_failure": "...", "max_retries": 2, "retry_count": 0}, ...]
    """
    import re
    steps = []
    current_step = None
    current_section = None  # "description", "pipeline", "failure", "result"

    for line in plan_content.split('\n'):
        # 새 단계 헤더 감지: ## 단계 N: 제목
        m = re.match(r'^## 단계 (\d+):\s*(.*)', line)
        if m:
            if current_step:
                steps.append(current_step)
            current_step = {
                "number": int(m.group(1)),
                "title": m.group(2).strip(),
                "status": "대기",
                "project_id": "", "agent_id": "",
                "description": "", "pipeline": "",
                "on_failure": "보고하고 중단",
                "max_retries": 2, "retry_count": 0,
            }
            current_section = None
            continue

        if not current_step:
            continue

        # 메타데이터 파싱
        if line.startswith("- **상태**:"):
            if "완료" in line:
                current_step["status"] = "완료"
            elif "실패" in line:
                current_step["status"] = "실패"
            elif "진행중" in line:
                current_step["status"] = "진행중"
            else:
                current_step["status"] = "대기"
        elif line.startswith("- **담당**:"):
            # project=투자, agent=agent_001
            pm = re.search(r'project=(\S+)', line)
            am = re.search(r'agent=(\S+)', line)
            if pm:
                current_step["project_id"] = pm.group(1).rstrip(',')
            if am:
                current_step["agent_id"] = am.group(1).rstrip(',')
        elif line.startswith("- **최대재시도**:"):
            try:
                current_step["max_retries"] = int(line.split(":")[1].strip())
            except (ValueError, IndexError):
                pass
        elif line.startswith("- **시도횟수**:"):
            try:
                current_step["retry_count"] = int(line.split(":")[1].strip())
            except (ValueError, IndexError):
                pass
        # 섹션 감지
        elif line.strip() == "### 지시사항":
            current_section = "description"
        elif line.strip() == "### 실행 코드":
            current_section = "pipeline"
        elif line.strip() == "### 실패 시":
            current_section = "failure"
        elif line.strip() == "### 결과":
            current_section = "result"
        elif line.startswith("## ") or line.startswith("---"):
            current_section = None
        # 섹션 내용 수집
        elif current_section == "description" and line.strip():
            if current_step["description"]:
                current_step["description"] += "\n" + line
            else:
                current_step["description"] = line
        elif current_section == "pipeline" and line.strip() and not line.startswith("```"):
            if current_step["pipeline"]:
                current_step["pipeline"] += "\n" + line
            else:
                current_step["pipeline"] = line
        elif current_section == "failure" and line.strip():
            current_step["on_failure"] = line

    if current_step:
        steps.append(current_step)

    return steps


def _execute_plan(params: dict, agent_id: str = None, project_path: str = None) -> str:
    """[self:execute_plan] — 작업계획서를 읽고 순차 실행

    작업계획서를 파싱하여 다음 대기 단계를 찾고,
    해당 담당 에이전트에게 그 단계의 지시사항만 전달합니다.
    에이전트가 작업을 완료하면, 시스템이 계획서 상태를 업데이트하고
    다음 단계가 있으면 자동으로 다음 담당 에이전트에게 넘깁니다.

    순차 실행 원칙:
    - 한 번에 하나의 단계만 실행
    - 이전 단계가 완료되어야 다음 단계로 진행
    - 에이전트에게는 자기 단계의 지시사항만 전달 (계획서 전체를 던지지 않음)
    - 상태 관리와 단계 전달은 시스템이 처리

    파라미터:
        file: 계획서 파일 경로 (필수)
        context: 이전 단계 결과/추가 컨텍스트 (선택)
    """
    from pathlib import Path as _Path

    plan_file = params.get("file", "")
    extra_context = params.get("context", "")

    if not plan_file:
        return json.dumps({
            "success": False,
            "error": "file 파라미터가 필요합니다."
        }, ensure_ascii=False)

    # ── 계획서 파일 읽기 ──
    file_path = _Path(plan_file)
    if not file_path.is_absolute():
        base = _Path(project_path) if project_path and project_path != "." else DATA_PATH
        file_path = base / plan_file

    if not file_path.exists():
        return json.dumps({
            "success": False,
            "error": f"계획서 파일을 찾을 수 없습니다: {file_path}"
        }, ensure_ascii=False)

    resolved_path = str(file_path)
    try:
        plan_content = file_path.read_text(encoding='utf-8')
    except Exception as e:
        return json.dumps({
            "success": False,
            "error": f"계획서 파일 읽기 실패: {e}"
        }, ensure_ascii=False)

    # ── 계획서 파싱: 다음 실행할 단계 찾기 ──
    steps = _parse_plan_steps(plan_content)
    if not steps:
        return json.dumps({
            "success": False,
            "error": "계획서에서 단계를 파싱할 수 없습니다."
        }, ensure_ascii=False)

    # 상태가 "대기"인 가장 빠른 단계 찾기
    next_step = None
    for step in steps:
        if step["status"] == "대기":
            next_step = step
            break

    if not next_step:
        # 모든 단계가 완료/실패됨
        completed = sum(1 for s in steps if s["status"] == "완료")
        failed = sum(1 for s in steps if s["status"] == "실패")
        return json.dumps({
            "success": True,
            "message": f"작업계획서의 모든 단계가 이미 처리됨 (완료: {completed}, 실패: {failed}, 전체: {len(steps)})",
            "plan_file": resolved_path,
            "all_done": True
        }, ensure_ascii=False)

    step_num = next_step["number"]
    step_title = next_step["title"]
    target_project_id = next_step["project_id"]
    target_agent_id = next_step["agent_id"]
    description = next_step["description"]
    pipeline = next_step["pipeline"]

    print(f"[ExecutePlan] 단계 {step_num}/{len(steps)}: {step_title} → {target_project_id}/{target_agent_id}")

    # ── 담당 에이전트 검증 ──
    if not target_project_id or not target_agent_id:
        _update_plan_status(resolved_path, step_num, "실패",
                            result_text="담당 에이전트가 지정되지 않음 (agent_project_id/agent_id 누락)")
        return json.dumps({
            "success": False,
            "error": f"단계 {step_num}({step_title}): 담당 에이전트가 지정되지 않았습니다. "
                     f"(project='{target_project_id}', agent='{target_agent_id}'). "
                     f"작업계획서를 다시 작성해주세요. "
                     f"read_guide('작업계획서')로 가이드를 참고하세요.",
            "plan_file": resolved_path,
            "step": step_num
        }, ensure_ascii=False)

    # ── 상태를 "진행중"으로 업데이트 ──
    _update_plan_status(resolved_path, step_num, "진행중")

    # ── 에이전트에게 보낼 메시지 구성 (이 단계의 지시사항만) ──
    msg_parts = []
    msg_parts.append(f"## 작업 지시: {step_title}")
    msg_parts.append(f"(작업계획서 '{_Path(resolved_path).stem}' — 단계 {step_num}/{len(steps)})\n")

    if description:
        msg_parts.append(f"### 해야 할 일")
        msg_parts.append(description)
        msg_parts.append("")

    if pipeline:
        msg_parts.append(f"### 실행할 코드")
        msg_parts.append(f"```ibl\n{pipeline}\n```")
        msg_parts.append("")

    if extra_context:
        msg_parts.append(f"### 이전 단계 결과")
        msg_parts.append(extra_context)
        msg_parts.append("")

    msg_parts.append("작업을 완료하면 결과를 보고해주세요.")
    user_message = "\n".join(msg_parts)

    # ── 레지스트리에 현재 단계 등록 (완료 콜백용) ──
    effective_project = target_project_id or "__self__"
    effective_agent = target_agent_id or "__self__"
    register_plan_step(effective_project, effective_agent,
                       resolved_path, step_num, len(steps))

    # ── 담당 에이전트에게 보이는 실행으로 전달 ──
    try:
        from calendar_manager import get_calendar_manager
        cm = get_calendar_manager()

        if not target_project_id or not target_agent_id:
            # 담당 에이전트 정보가 없으면 현재 프로젝트/에이전트로 실행
            is_system_ai = (not project_path or project_path == "." or
                            project_path == str(DATA_PATH))
            if is_system_ai:
                result = cm._execute_visible_system_ai(user_message, {})
            else:
                pp = _Path(project_path)
                result = cm._execute_visible_agent(
                    pp.name, agent_id or "", user_message, {})
        else:
            result = cm._execute_visible_agent(
                target_project_id, target_agent_id, user_message, {})

        if not result.get("success"):
            # 보이는 실행 실패 → 레지스트리 해제, 상태 복원
            with _plan_steps_lock:
                _active_plan_steps.pop((effective_project, effective_agent), None)
            _update_plan_status(resolved_path, step_num, "대기")
            return json.dumps({
                "success": False,
                "error": f"단계 {step_num} 실행 실패: {result.get('error', '알 수 없음')}",
                "plan_file": resolved_path,
                "step": step_num,
                "step_title": step_title
            }, ensure_ascii=False)

        # ── 성공: fire-and-forget으로 에이전트에게 전달됨.
        # 에이전트 완료 시 handle_chat_message_stream → on_agent_plan_step_complete()
        # 콜백이 자동으로 상태 업데이트 및 다음 단계 트리거.
        return json.dumps({
            "success": True,
            "visible": True,
            "plan_file": resolved_path,
            "current_step": step_num,
            "total_steps": len(steps),
            "step_title": step_title,
            "target": f"{target_project_id}/{target_agent_id}",
            "message": f"단계 {step_num}/{len(steps)} '{step_title}'을(를) {target_project_id}/{target_agent_id} 에이전트에게 전달했습니다. 해당 프로젝트 창에서 실행 중입니다."
        }, ensure_ascii=False)

    except Exception as e:
        import traceback
        traceback.print_exc()
        # 레지스트리 해제 및 상태 복원
        with _plan_steps_lock:
            _active_plan_steps.pop((effective_project, effective_agent), None)
        _update_plan_status(resolved_path, step_num, "대기")
        return json.dumps({
            "success": False,
            "error": f"계획서 실행 실패: {e}"
        }, ensure_ascii=False)
