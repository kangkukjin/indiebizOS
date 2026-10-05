"""
api_agents.py - 에이전트 관련 API
IndieBiz OS Core
"""

import uuid
import threading
from datetime import datetime
from typing import Dict, Any
from pathlib import Path

from fastapi import APIRouter, HTTPException, BackgroundTasks, Request, Body
from pydantic import BaseModel
import copy
import yaml


# ai 설정 안에서 절대 클라이언트로 내보내면 안 되는 비밀 키들
_AI_SECRET_FIELDS = ("api_key", "apiKey", "token", "access_token", "secret", "api_secret")


def _redact_agent_secrets(agent):
    """단일 에이전트 dict에서 API 키 등 비밀을 비파괴적으로 제거.

    응답 직렬화 직전에만 호출 — 원본(agents.yaml 로드본)을 건드리지 않도록 deepcopy.
    키 존재 여부는 `has_api_key` 불리언으로만 노출(UI가 '키 설정됨' 표시에 사용).
    """
    safe = copy.deepcopy(agent)
    ai = safe.get("ai")
    if isinstance(ai, dict):
        safe["has_api_key"] = bool(ai.get("api_key"))
        for field in _AI_SECRET_FIELDS:
            if field in ai:
                ai[field] = ""
    return safe


def _redact_agents_secrets(agents):
    """에이전트 목록 응답에서 민감 정보(API 키 등) 일괄 제거"""
    return [_redact_agent_secrets(a) for a in agents]

router = APIRouter()

# 매니저 인스턴스
project_manager = None

# 에이전트 런너 등기부는 agent_registry(데이터층)가 정본 — 여기서는 같은 dict 를
# 공유해 조작만 한다 (2026-08-05 감사 ⑦. 재바인딩 금지 — 항목 조작만).
from agent_registry import agent_runners, get_agent_runners  # noqa: F401


class AgentImage(BaseModel):
    base64: str
    media_type: str = "image/png"


class AgentCommand(BaseModel):
    command: str
    images: list[AgentImage] | None = None
    origin: str | None = None
    # True면 즉시 반환(fire-and-forget) — 영상 생성 등 수 분짜리 작업이 터널 타임아웃(524)에
    # 걸리지 않도록. 응답은 평소처럼 conversations.db에 저장되니 호출 측이 메시지를 폴링해서 받는다.
    background: bool = False


class AgentNote(BaseModel):
    note: str


class AgentRole(BaseModel):
    role: str


class AgentUpdate(BaseModel):
    name: str
    type: str = "external"
    provider: str = "anthropic"
    model: str = "claude-sonnet-4-20250514"
    api_key: str = None
    role: str = None
    allowed_tools: list = None  # deprecated (하위 호환)
    allowed_nodes: list = None  # Phase 16: IBL 노드 기반
    channel: str = None
    email: str = None
    channels: list = None


def init_manager(pm):
    """매니저 인스턴스 초기화"""
    global project_manager
    project_manager = pm


# ============ 에이전트 조회 ============

@router.get("/projects/{project_id}/agents")
async def get_project_agents(project_id: str, request: Request):
    """프로젝트의 에이전트 목록"""
    try:
        project_path = project_manager.get_project_path(project_id)
        agents_file = project_path / "agents.yaml"

        if not agents_file.exists():
            return {"agents": []}

        with open(agents_file, 'r', encoding='utf-8') as f:
            data = yaml.safe_load(f)

        agents = data.get("agents", [])

        # API 키 등 비밀은 어떤 클라이언트(데스크탑/원격 터널/폰 컴패니언 프록시)에도
        # 평문으로 내보내지 않는다. 자율주행 JS는 id/name/role만 쓰고, 데스크탑 편집
        # 폼은 비대칭 PUT(빈 키=기존 유지)이라 실제 키 없이도 동작한다.
        # is_external_request는 Host 헤더 기반이라 LAN 프록시를 놓칠 수 있어 항상 마스킹.
        agents = _redact_agents_secrets(agents)

        # 표시용 실효 모델 — per-agent yaml 모델은 폐지됨(기어가 단독 결정). 카드/설정 UI가
        # 옛 ai.provider 대신 *기어가 실제로 해소한* 모델을 보이도록 effective_model 부착.
        # _resolve_execution_config 과 동일 경로: resolve("execution", "{project}:{agent_id}")
        # → 에이전트 핀(overrides) 우선, 없으면 현재 기어의 실행 축 티어.
        try:
            from model_resolver import resolve
            for a in agents:
                aid = a.get("id")
                pin_key = f"{project_id}:{aid}" if aid else None
                d = resolve("execution", agent_id=pin_key)
                a["effective_model"] = {
                    "provider": d.get("provider"), "model": d.get("model"),
                    "tier": d.get("tier"), "source": d.get("source"),
                }
        except Exception as e:
            print(f"[api_agents] effective_model 해소 실패(무시): {e}")

        # 실행 상태 부착 — 등기부(메모리)가 진실. 화면의 runningAgents 가 이걸로 재동기화
        # 해야 백엔드 재기동 후 '실행 중' 거짓 표시 드리프트가 사라진다 (2026-08-10).
        runners = agent_runners.get(project_id, {})
        for a in agents:
            info = runners.get(a.get("id"))
            r = info.get("runner") if info else None
            a["running"] = bool(r and getattr(r, "running", False))
            # 폴링 스레드 실생존 (2026-08-15, 5라운드 감사의 관측 갭) — running 플래그는
            # 스레드가 죽어도 True 로 남을 수 있다(cancel_all 좀비 부류). 죽은 스레드와
            # 산 스레드를 구별하는 유일한 창.
            _th = getattr(r, "thread", None) if r else None
            a["thread_alive"] = bool(_th and _th.is_alive())
            # 폴링 하트비트 — thread_alive 가 "살아 있나"라면 이건 "실제로 돌고 있나".
            # 행이 걸린 스레드(alive 지만 순회 정지)까지 가르는 창.
            a["last_poll_at"] = getattr(r, "last_poll_at", None) if r else None

        return {"agents": agents}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ============ 에이전트 시작/중지 ============

@router.post("/projects/{project_id}/agents/{agent_id}/start")
async def start_agent(project_id: str, agent_id: str, background_tasks: BackgroundTasks):
    """에이전트 시작 — 구현은 agent_lifecycle.start_agent([others:agents]{op:start} 와 같은 함수)."""
    import agent_lifecycle
    try:
        return agent_lifecycle.start_agent(project_id, agent_id)
    except KeyError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/projects/{project_id}/agents/{agent_id}/stop")
async def stop_agent(project_id: str, agent_id: str):
    """에이전트 중지 — 구현은 agent_lifecycle.stop_agent."""
    import agent_lifecycle
    try:
        return agent_lifecycle.stop_agent(project_id, agent_id)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/projects/{project_id}/agents/{agent_id}/reset-session")
async def reset_agent_session(project_id: str, agent_id: str):
    """CLI 프로바이더 세션 매핑 클리어 — 다음 호출이 fresh 세션으로 시작.

    누적된 도구 결과·resume 컨텍스트를 끊고 싶을 때 사용.
    CLI 프로바이더(claude_code·codex)가 아니면 no-op이지만 200 OK 반환 (안전).
    """
    try:
        from providers import clear_cli_sessions_for_agent
        # registry_key 형식: "{project_id}:{agent_id}"
        key = f"{project_id}:{agent_id}"
        clear_cli_sessions_for_agent(key)
        return {"ok": True, "message": "새 세션을 시작했습니다.", "key": key}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/projects/{project_id}/cancel_all")
async def cancel_all_agents(project_id: str):
    """프로젝트의 모든 에이전트 작업 중단 (에이전트는 유지, 현재 작업만 취소)"""
    try:
        cancelled = []
        from repair_continuation import cancel_pending
        cancel_pending(project_id)

        if project_id in agent_runners:
            for agent_id, runner_info in list(agent_runners[project_id].items()):
                runner = runner_info.get("runner")
                if runner:
                    runner.cancel()
                    cancelled.append(agent_id)
            # 주의: 레지스트리를 비우지 않음 - 에이전트는 유지되고 다음 메시지를 받을 수 있어야 함

        return {"status": "cancelled", "cancelled_agents": cancelled}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/projects/{project_id}/presence")
def project_window_presence(project_id: str, body: dict = Body(default={})):
    """프로젝트 창 존재 하트비트 — 조종실 '액티브 프로젝트'가 '창 열림=활성'을 self-healing
    으로 판단하게 한다(System AI presence 와 동형). open=false 는 닫힘 beacon(즉시 부재)."""
    from thread_context import mark_project_window
    mark_project_window(project_id, bool(body.get("open", True)))
    return {"status": "ok"}


@router.post("/projects/{project_id}/stop_all")
async def stop_all_agents(project_id: str):
    """프로젝트의 모든 에이전트 완전 중지 (프로젝트 전환 시 사용)"""
    try:
        stopped = []

        if project_id in agent_runners:
            for agent_id, runner_info in list(agent_runners[project_id].items()):
                runner = runner_info.get("runner")
                if runner:
                    agent_name = runner.config.get('name', agent_id)
                    runner.stop()  # cancel()이 아닌 stop()으로 완전 중지
                    stopped.append({"agent_id": agent_id, "name": agent_name})
                    print(f"[에이전트 중지] {agent_name}")

            del agent_runners[project_id]

        return {"status": "stopped", "stopped_agents": stopped}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ============ 에이전트 명령 ============

def _command_origin(origin):
    from thread_context import REHEARSAL_ORIGINS
    if origin is not None and origin not in REHEARSAL_ORIGINS:
        raise HTTPException(status_code=400, detail="origin은 'training'만 지정할 수 있습니다.")
    return origin or "user"


def _run_agent_command(project_id: str, agent_id: str, runner, command: str, origin=None, *, continuation=None, images=None,
                       task_id=None):
    """에이전트 명령 처리 코어 — 동기/백그라운드 양쪽이 공유.

    응답 텍스트를 반환하고, 사용자/AI 메시지를 conversations.db에 저장한다.
    백그라운드 경로에서는 자체 스레드에서 돌므로 스레드 컨텍스트를 여기서 설정/정리한다.
    task_id 를 주면(백그라운드 접수의 선발급) 그 작업을 쓴다 — 이미 행이 있으면 다시 만들지 않는다.
    """
    from conversation_db import ConversationDB
    from thread_context import (set_current_agent_id, set_current_agent_name,
                                set_current_project_id, set_task_origin, set_user_input,
                                set_current_task_id, clear_called_agent, clear_all_context)
    from uuid import uuid4

    task_origin = _command_origin(origin)
    rehearsal = task_origin == "training"
    contact_type = "rehearsal" if rehearsal else "gui"
    task_id = continuation["resume_task_id"] if continuation else (task_id or f"task_{uuid4().hex}")
    db = None
    user_id = target_agent_id = None
    response_saved = False
    try:
        project_path = project_manager.get_project_path(project_id)
        agent_name = runner.config.get("name", agent_id)

        # 스레드 컨텍스트 설정 (call_agent 등에서 발신자 정보로 사용)
        set_current_agent_id(agent_id)
        set_current_agent_name(agent_name)
        set_current_project_id(project_id)
        if rehearsal:
            set_task_origin(task_origin)
        else:
            set_task_origin("user")
        set_user_input(command)  # 쓰기 관문 원장·episode 조인이 읽는 행위자 칸 (WS 경로와 대칭)
        set_current_task_id(task_id)
        clear_called_agent()

        # 에피소드 로깅 — 이 엔드포인트는 원격 런처 자율주행 탭이 프로젝트 에이전트에게
        # 보내는 HTTP 경로인데, start/end 가 WebSocket 핸들러(api_websocket)에만 배선돼
        # 있어 주행기록 사각지대였다(/system-ai/chat 의 _process() 봉합과 같은 한 쌍).
        # 동기·백그라운드 모두 이 함수 한 덩어리를 한 스레드에서 지나므로 여기 한 곳이면
        # 두 경우를 다 덮는다.
        try:
            from episode_logger import EpisodeLogger
            EpisodeLogger.start_episode(agent_name, command, project_id=project_id, task_id=task_id)
        except Exception:
            pass

        # 대화 DB
        db = ConversationDB(str(project_path / "conversations.db"))
        if not db.get_task(task_id):
            db.create_task(task_id, "user@gui", contact_type, command, agent_name,
                           parent_task_id=continuation["task_id"] if continuation else None)

        # 사용자 및 에이전트 ID
        user_id = db.get_or_create_agent("user", "human")
        target_agent_id = db.get_or_create_agent(agent_name, "ai_agent")

        # 히스토리 로드
        history = db.get_history_for_ai(target_agent_id, user_id, rehearsal=rehearsal)

        # 사용자 메시지 저장
        if not continuation:
            db.save_message(user_id, target_agent_id, command, images=images, contact_type=contact_type)

        # AI 응답 생성 — 인지 파이프라인 제너레이터를 drain 하는 블로킹 어댑터.
        #
        # ★2026-08-25 합류: 여기는 폰 원격런처 자율주행 탭이 프로젝트 에이전트에게 말을 거는
        # **사람의 채팅 표면**인데, 사람 표면 중 혼자만 cognitive_stream 을 우회해
        # process_message_with_history 를 직접 불렀다. 그래서 이 표면의 턴은 태그가 읽히는
        # 자리(cognitive_consciousness._tag_override)를 아예 지나지 않아 REPAIR 분류·의식
        # 각성·모델 승격·RED 그랜트가 통째로 없었다 — 실측 ep1915: '…고쳐줘. #repair' 인데
        # 런타임 로그에 [무의식] 분류 0줄, 그랜트 미발급으로 [self:edit] 이 RED 에 거절됐다.
        # 사용자는 태그를 붙였는데 그 표면에는 태그를 읽는 코드가 없었던 것.
        #
        # 헌법(2026-08-05, 커밋 6caa2ea)이 origin='user' 진입점 넷 중 하나로 이미 지목한
        # 표면이다("에이전트 명령 HTTP"). WS×2·/system-ai/chat 과 같은 드라이버로 합류시킨다.
        # 기어 동기화도 파이프라인 0단계라 여기서 따로 부르지 않는다.
        from agent_pipeline import drain_stream
        from repair_continuation import resume_context, cancelled as repair_cancelled
        result = drain_stream(runner.cognitive_stream(command, history, images=images, agent_name=agent_name,
                                                      extra_role=resume_context(continuation) if continuation else "",
                                                      cancel_check=(lambda: repair_cancelled(continuation)) if continuation else None,
                                                      utterance_author="owner"))
        response = result.get("final") or result.get("error") or ""

        # AI 응답 저장
        db.save_message(target_agent_id, user_id, response, contact_type=contact_type)
        response_saved = True
        task = db.get_task(task_id) or {}
        if result.get("error") or result.get("cancelled"):
            with db.get_connection() as conn:
                conn.execute("UPDATE tasks SET status=?, result=?, completed_at=CURRENT_TIMESTAMP WHERE task_id=?",
                             ("failed" if result.get("error") else "cancelled", response, task_id))
                conn.commit()
        elif not task.get("pending_delegations"):
            db.complete_task(task_id, response)
        if continuation:
            from thread_context import get_goal_eval_outcome
            return {"response": response, "evaluation": get_goal_eval_outcome(),
                    "cancelled": result.get("cancelled"), "error": result.get("error")}
        return response
    except Exception as exc:
        if db is not None:
            from logging_utils import mask_secrets
            error = mask_secrets(str(exc))
            with db.get_connection() as conn:
                conn.execute("UPDATE tasks SET status='failed', result=?, completed_at=CURRENT_TIMESTAMP WHERE task_id=?",
                             (error, task_id))
                # 백그라운드 명령의 호출자는 대화 폴링으로 응답을 받는다.
                # 실패 상태와 사용자에게 보일 응답을 같은 트랜잭션에 남긴다.
                if user_id is not None and target_agent_id is not None and not response_saved:
                    conn.execute("INSERT INTO messages (from_agent_id, to_agent_id, content, contact_type) "
                                 "VALUES (?, ?, ?, ?)",
                                 (target_agent_id, user_id,
                                  "요청 처리 중 오류가 발생해 작업이 중단되었습니다.\n" + error, contact_type))
                conn.commit()
        raise
    finally:
        try:
            from episode_logger import EpisodeLogger
            EpisodeLogger.end_episode()
        except Exception:
            pass
        finally:
            clear_all_context()


@router.post("/projects/{project_id}/agents/{agent_id}/command")
def send_agent_command(project_id: str, agent_id: str, cmd: AgentCommand):
    # ★ 동기(def) 엔드포인트로 둔다 (async 아님). _run_agent_command 는 LLM 파이프라인 전체를
    # 동기로 블로킹한다. async 로 두면 수 분짜리 작업이 이벤트 루프를 통째로 막아, 같은 백엔드의
    # 다른 요청(NAS 파일 탐색 등)이 그동안 처리되지 못한다. def 로 두면 FastAPI 가 스레드풀에서
    # 실행해 루프가 자유로워진다(시스템 AI /system-ai/chat 과 같은 설계).
    """에이전트에게 명령 전송.

    cmd.background=True 면 즉시 반환하고 별도 스레드에서 처리한다(폰 원격런처용 — 영상 생성 등
    수 분짜리 작업이 Cloudflare 터널 100초 타임아웃에 걸려 524가 뜨던 문제 해결). 응답은
    평소처럼 conversations.db에 저장되므로 호출 측이 메시지를 폴링해서 받아간다.
    """
    _command_origin(cmd.origin)  # 백그라운드 접수 전에 거절한다.
    # 에이전트 실행 중인지 확인 — 두 경로 모두 즉시 검증해서 빠른 피드백을 준다
    if project_id not in agent_runners or agent_id not in agent_runners[project_id]:
        raise HTTPException(status_code=400, detail="에이전트가 실행 중이 아닙니다.")

    runner_info = agent_runners[project_id][agent_id]
    runner = runner_info.get("runner")

    if not runner or not runner.ai:
        raise HTTPException(status_code=400, detail="에이전트 AI가 준비되지 않았습니다.")

    image_args = {"images": [image.model_dump() for image in cmd.images]} if cmd.images else {}
    if cmd.background:
        # 작업 선발급(2026-10-05): 접수증에 task_id·status_url 을 싣는다. 실행 전에 행을 남겨
        # 즉시 조회가 되고, 워커의 예외는 _run_agent_command 가 failed 로 기록한다.
        task_id = f"task_{uuid.uuid4().hex}"
        try:
            from conversation_db import ConversationDB
            project_path = project_manager.get_project_path(project_id)
            db = ConversationDB(str(project_path / "conversations.db"))
            db.create_task(task_id, "user@gui", "rehearsal" if cmd.origin == "training" else "gui",
                           cmd.command, runner.config.get("name", agent_id))
        except Exception as exc:
            raise HTTPException(status_code=500, detail=f"작업 접수 실패: {exc}")

        def _worker():
            try:
                _run_agent_command(project_id, agent_id, runner, cmd.command, cmd.origin, task_id=task_id, **image_args)
            except Exception:
                import traceback
                traceback.print_exc()
        threading.Thread(target=_worker, daemon=True).start()
        from delegation_tasks import status_url
        return {"status": "started", "accepted": True, "task_id": task_id, "state": "queued",
                "task_ref": {"owner": project_id, "task_id": task_id},
                "status_url": status_url(project_id, task_id, agent_id)}

    try:
        response = _run_agent_command(project_id, agent_id, runner, cmd.command, cmd.origin, **image_args)
        return {"response": response}
    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/projects/{project_id}/agents/{agent_id}/tasks/{task_id}")
def get_agent_task(project_id: str, agent_id: str, task_id: str, wait: int = 0):
    """접수한 작업의 상태·결과 조회 (2026-10-05). 실행을 만들지 않는 GET.

    경로의 agent 를 믿지 않고 저장된 delegated_to 와 대조한다(id 또는 이름). wait 는 서버 상한
    (delegation_tasks.HTTP_WAIT_MAX)으로 제한된 대기. 결과 전문은 종료 상태에서만."""
    from delegation_tasks import HTTP_WAIT_MAX, task_view, wait_for_task
    try:
        project_path = project_manager.get_project_path(project_id)
    except Exception as exc:
        raise HTTPException(status_code=404, detail=f"프로젝트를 찾을 수 없습니다: {exc}")
    names = {agent_id}
    try:
        agents_file = project_path / "agents.yaml"
        if agents_file.exists():
            with open(agents_file, 'r', encoding='utf-8') as f:
                for agent in (yaml.safe_load(f) or {}).get("agents", []) or []:
                    if agent.get("id") == agent_id or agent.get("name") == agent_id:
                        names |= {agent.get("id"), agent.get("name")}
    except Exception:
        pass
    runner_info = (agent_runners.get(project_id) or {}).get(agent_id) or {}
    runner = runner_info.get("runner")
    if runner is not None:
        names |= {runner.config.get("id"), runner.config.get("name")}
    bounded = max(0, min(int(wait or 0), HTTP_WAIT_MAX))
    view = wait_for_task(project_id, task_id, bounded, agent_id) if bounded else task_view(project_id, task_id, agent_id)
    if view is None or view.get("delegated_to") not in names:
        raise HTTPException(status_code=404, detail=f"작업을 찾을 수 없습니다: {task_id}")
    return view


# ============ 에이전트 노트/역할 ============

@router.get("/projects/{project_id}/agents/{agent_id}/note")
async def get_agent_note(project_id: str, agent_id: str):
    """에이전트 메모 조회"""
    try:
        project_path = project_manager.get_project_path(project_id)
        agents_file = project_path / "agents.yaml"

        if not agents_file.exists():
            return {"note": ""}

        with open(agents_file, 'r', encoding='utf-8') as f:
            data = yaml.safe_load(f)

        for agent in data.get("agents", []):
            if agent.get("id") == agent_id:
                agent_name = agent.get("name", agent_id)
                note_file = project_path / f"agent_{agent_name}_note.txt"
                if note_file.exists():
                    return {"note": note_file.read_text(encoding='utf-8')}
                return {"note": ""}

        return {"note": ""}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.put("/projects/{project_id}/agents/{agent_id}/note")
async def save_agent_note(project_id: str, agent_id: str, note_data: AgentNote):
    """에이전트 메모 저장"""
    try:
        project_path = project_manager.get_project_path(project_id)
        agents_file = project_path / "agents.yaml"

        if not agents_file.exists():
            raise HTTPException(status_code=404, detail="에이전트 설정을 찾을 수 없습니다.")

        with open(agents_file, 'r', encoding='utf-8') as f:
            data = yaml.safe_load(f)

        for agent in data.get("agents", []):
            if agent.get("id") == agent_id:
                agent_name = agent.get("name", agent_id)
                note_file = project_path / f"agent_{agent_name}_note.txt"
                note_file.write_text(note_data.note, encoding='utf-8')

                return {"status": "saved"}

        raise HTTPException(status_code=404, detail=f"에이전트 '{agent_id}'를 찾을 수 없습니다.")
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/projects/{project_id}/agents/{agent_id}/role")
async def get_agent_role(project_id: str, agent_id: str):
    """에이전트 역할 조회"""
    try:
        project_path = project_manager.get_project_path(project_id)
        agents_file = project_path / "agents.yaml"

        if not agents_file.exists():
            raise HTTPException(status_code=404, detail="에이전트 설정을 찾을 수 없습니다.")

        with open(agents_file, 'r', encoding='utf-8') as f:
            data = yaml.safe_load(f)

        for agent in data.get("agents", []):
            if agent.get("id") == agent_id:
                agent_name = agent.get("name", agent_id)
                role_file = project_path / f"agent_{agent_name}_role.txt"

                role = ""
                if role_file.exists():
                    role = role_file.read_text(encoding='utf-8')

                return {"role": role, "agent_name": agent_name}

        raise HTTPException(status_code=404, detail=f"에이전트 '{agent_id}'를 찾을 수 없습니다.")
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.put("/projects/{project_id}/agents/{agent_id}/role")
async def update_agent_role(project_id: str, agent_id: str, role_data: AgentRole):
    """에이전트 역할 저장"""
    try:
        project_path = project_manager.get_project_path(project_id)
        agents_file = project_path / "agents.yaml"

        if not agents_file.exists():
            raise HTTPException(status_code=404, detail="에이전트 설정을 찾을 수 없습니다.")

        with open(agents_file, 'r', encoding='utf-8') as f:
            data = yaml.safe_load(f)

        for agent in data.get("agents", []):
            if agent.get("id") == agent_id:
                agent_name = agent.get("name", agent_id)
                role_file = project_path / f"agent_{agent_name}_role.txt"
                role_file.write_text(role_data.role, encoding='utf-8')

                return {"status": "saved", "agent_name": agent_name}

        raise HTTPException(status_code=404, detail=f"에이전트 '{agent_id}'를 찾을 수 없습니다.")
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ============ 에이전트 CRUD ============

@router.post("/projects/{project_id}/agents")
async def create_agent(project_id: str, agent_data: AgentUpdate):
    """새 에이전트 생성 — 구현은 agent_lifecycle.create_agent([others:agents]{op:create} 와 같은 함수)."""
    import agent_lifecycle
    try:
        new_agent = agent_lifecycle.create_agent(project_id, agent_data.name, type=agent_data.type, role=agent_data.role,
                                                 allowed_nodes=agent_data.allowed_nodes, allowed_tools=agent_data.allowed_tools,
                                                 channel=agent_data.channel, email=agent_data.email)
        return {"status": "created", "agent": _redact_agent_secrets(new_agent)}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


class RoleDescriptions(BaseModel):
    descriptions: dict


@router.put("/projects/{project_id}/agents/role-descriptions")
async def update_role_descriptions(project_id: str, data: RoleDescriptions):
    """에이전트 역할 설명 일괄 업데이트"""
    try:
        project_path = project_manager.get_project_path(project_id)
        agents_file = project_path / "agents.yaml"

        if not agents_file.exists():
            raise HTTPException(status_code=404, detail="에이전트 설정을 찾을 수 없습니다.")

        with open(agents_file, 'r', encoding='utf-8') as f:
            yaml_data = yaml.safe_load(f)

        updated_agents = []
        for agent in yaml_data.get("agents", []):
            agent_name = agent.get("name")
            if agent_name in data.descriptions:
                agent["role_description"] = data.descriptions[agent_name]
                updated_agents.append(agent_name)

        with open(agents_file, 'w', encoding='utf-8') as f:
            yaml.dump(yaml_data, f, allow_unicode=True, default_flow_style=False)

        return {"status": "updated", "updated_agents": updated_agents}

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.put("/projects/{project_id}/agents/{agent_id}")
async def update_agent(project_id: str, agent_id: str, agent_data: AgentUpdate):
    """에이전트 업데이트(이름 바꾸기 포함) — 구현은 agent_lifecycle.update_agent."""
    import agent_lifecycle
    try:
        agent_lifecycle.update_agent(project_id, agent_id, name=agent_data.name, type=agent_data.type, role=agent_data.role,
                                     allowed_nodes=agent_data.allowed_nodes, allowed_tools=agent_data.allowed_tools,
                                     channel=agent_data.channel, email=agent_data.email)
        return {"status": "updated", "agent_id": agent_id}
    except KeyError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/projects/{project_id}/agents/{agent_id}")
async def delete_agent(project_id: str, agent_id: str):
    """에이전트 삭제 — 구현은 agent_lifecycle.delete_agent(러너가 돌고 있으면 먼저 중지)."""
    import agent_lifecycle
    try:
        agent_lifecycle.stop_agent(project_id, agent_id)
        name = agent_lifecycle.delete_agent(project_id, agent_id)
        return {"status": "deleted", "agent_id": agent_id, "name": name}
    except KeyError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
