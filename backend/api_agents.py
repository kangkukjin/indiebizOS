"""
api_agents.py - 에이전트 관련 API
IndieBiz OS Core
"""

import uuid
import threading
from datetime import datetime
from typing import Dict, Any
from pathlib import Path

from fastapi import APIRouter, HTTPException, BackgroundTasks, Request
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

# 에이전트 런너 관리 (프로젝트별)
agent_runners: Dict[str, Dict[str, Any]] = {}


class AgentCommand(BaseModel):
    command: str
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


def get_agent_runners():
    """agent_runners 반환"""
    return agent_runners


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

        return {"agents": agents}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ============ 에이전트 시작/중지 ============

@router.post("/projects/{project_id}/agents/{agent_id}/start")
async def start_agent(project_id: str, agent_id: str, background_tasks: BackgroundTasks):
    """에이전트 시작"""
    from agent_runner import AgentRunner

    try:
        project_path = project_manager.get_project_path(project_id)
        agents_file = project_path / "agents.yaml"

        if not agents_file.exists():
            raise HTTPException(status_code=404, detail="에이전트 설정을 찾을 수 없습니다.")

        with open(agents_file, 'r', encoding='utf-8') as f:
            data = yaml.safe_load(f)

        # 에이전트 찾기
        agent_config = None
        for agent in data.get("agents", []):
            if agent.get("id") == agent_id:
                agent_config = agent
                break

        if not agent_config:
            raise HTTPException(status_code=404, detail=f"에이전트 '{agent_id}'를 찾을 수 없습니다.")

        # 러너 저장소 초기화
        if project_id not in agent_runners:
            agent_runners[project_id] = {}

        # 이미 실행 중인지 확인
        if agent_id in agent_runners[project_id]:
            runner = agent_runners[project_id][agent_id].get("runner")
            if runner and runner.running:
                return {"status": "already_running", "agent_id": agent_id}

        # 공통 설정 로드
        common_config = data.get("common", {})

        # 프로젝트 경로 추가
        agent_config["_project_path"] = str(project_path)
        agent_config["_project_id"] = project_id

        # AgentRunner 생성 및 시작
        runner = AgentRunner(agent_config, common_config)
        runner.start()

        # 저장
        agent_runners[project_id][agent_id] = {
            "runner": runner,
            "config": agent_config,
            "running": True,
            "started_at": datetime.now().isoformat()
        }

        print(f"[에이전트 시작] {agent_config['name']}")

        return {"status": "started", "agent_id": agent_id}
    except HTTPException:
        raise
    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/projects/{project_id}/agents/{agent_id}/stop")
async def stop_agent(project_id: str, agent_id: str):
    """에이전트 중지"""
    try:
        if project_id in agent_runners and agent_id in agent_runners[project_id]:
            runner = agent_runners[project_id][agent_id].get("runner")
            if runner:
                runner.stop()
                print(f"[에이전트 중지] {runner.config.get('name', agent_id)}")
            del agent_runners[project_id][agent_id]
            return {"status": "stopped", "agent_id": agent_id}

        return {"status": "not_running", "agent_id": agent_id}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/projects/{project_id}/agents/{agent_id}/reset-session")
async def reset_agent_session(project_id: str, agent_id: str):
    """Claude Code 세션 매핑 클리어 — 다음 호출이 fresh 세션으로 시작.

    누적된 도구 결과·resume 컨텍스트를 끊고 싶을 때 사용.
    Claude Code provider가 아니면 no-op이지만 200 OK 반환 (안전).
    """
    try:
        from providers.claude_code import clear_session_for_agent
        # registry_key 형식: "{project_id}:{agent_id}"
        key = f"{project_id}:{agent_id}"
        clear_session_for_agent(key)
        return {"ok": True, "message": "새 세션을 시작했습니다.", "key": key}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/projects/{project_id}/cancel_all")
async def cancel_all_agents(project_id: str):
    """프로젝트의 모든 에이전트 작업 중단 (에이전트는 유지, 현재 작업만 취소)"""
    try:
        cancelled = []

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

def _run_agent_command(project_id: str, agent_id: str, runner, command: str):
    """에이전트 명령 처리 코어 — 동기/백그라운드 양쪽이 공유.

    응답 텍스트를 반환하고, 사용자/AI 메시지를 conversations.db에 저장한다.
    백그라운드 경로에서는 자체 스레드에서 돌므로 스레드 컨텍스트를 여기서 설정/정리한다.
    """
    from conversation_db import ConversationDB
    from thread_context import set_current_agent_id, set_current_agent_name, set_current_project_id, clear_all_context

    try:
        project_path = project_manager.get_project_path(project_id)
        agent_name = runner.config.get("name", agent_id)

        # 스레드 컨텍스트 설정 (call_agent 등에서 발신자 정보로 사용)
        set_current_agent_id(agent_id)
        set_current_agent_name(agent_name)
        set_current_project_id(project_id)

        # 대화 DB
        db = ConversationDB(str(project_path / "conversations.db"))

        # 사용자 및 에이전트 ID
        user_id = db.get_or_create_agent("user", "human")
        target_agent_id = db.get_or_create_agent(agent_name, "ai_agent")

        # 히스토리 로드
        history = db.get_history_for_ai(target_agent_id, user_id)

        # 사용자 메시지 저장
        db.save_message(user_id, target_agent_id, command)

        # AI 응답 생성
        response = runner.ai.process_message_with_history(
            message_content=command,
            from_email="user@gui",
            history=history,
            reply_to="user@gui"
        )

        # AI 응답 저장
        db.save_message(target_agent_id, user_id, response)
        return response
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
    # 에이전트 실행 중인지 확인 — 두 경로 모두 즉시 검증해서 빠른 피드백을 준다
    if project_id not in agent_runners or agent_id not in agent_runners[project_id]:
        raise HTTPException(status_code=400, detail="에이전트가 실행 중이 아닙니다.")

    runner_info = agent_runners[project_id][agent_id]
    runner = runner_info.get("runner")

    if not runner or not runner.ai:
        raise HTTPException(status_code=400, detail="에이전트 AI가 준비되지 않았습니다.")

    if cmd.background:
        def _worker():
            try:
                _run_agent_command(project_id, agent_id, runner, cmd.command)
            except Exception:
                import traceback
                traceback.print_exc()
        threading.Thread(target=_worker, daemon=True).start()
        return {"status": "started"}

    try:
        response = _run_agent_command(project_id, agent_id, runner, cmd.command)
        return {"response": response}
    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))


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
    """새 에이전트 생성"""
    try:
        project_path = project_manager.get_project_path(project_id)
        agents_file = project_path / "agents.yaml"

        if not agents_file.exists():
            data = {"agents": [], "common": {}}
        else:
            with open(agents_file, 'r', encoding='utf-8') as f:
                data = yaml.safe_load(f) or {"agents": [], "common": {}}

        # 새 ID
        new_id = f"agent_{uuid.uuid4().hex[:8]}"

        new_agent = {
            "id": new_id,
            "name": agent_data.name,
            "type": agent_data.type,
            "active": True,
            "ai": {
                "provider": agent_data.provider,
                "model": agent_data.model
            }
        }

        if agent_data.api_key:
            new_agent["ai"]["api_key"] = agent_data.api_key

        # Phase 16: allowed_nodes 우선, 하위 호환으로 allowed_tools도 지원
        if agent_data.allowed_nodes is not None:
            new_agent["allowed_nodes"] = agent_data.allowed_nodes
            new_agent["ibl_only"] = True
        elif agent_data.allowed_tools is not None:
            new_agent["allowed_tools"] = agent_data.allowed_tools

        if agent_data.type == "external" and agent_data.channel:
            new_agent["channel"] = agent_data.channel
            if agent_data.email:
                new_agent["email"] = agent_data.email

        data["agents"].append(new_agent)

        with open(agents_file, 'w', encoding='utf-8') as f:
            yaml.dump(data, f, allow_unicode=True, default_flow_style=False)

        if agent_data.role:
            role_file = project_path / f"agent_{agent_data.name}_role.txt"
            role_file.write_text(agent_data.role, encoding='utf-8')

        # 응답에는 키를 되돌려 보내지 않는다 (요청자는 이미 키를 가졌지만,
        # 프록시/로깅 표면에 평문 키가 새지 않도록 일관되게 마스킹)
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
    """에이전트 업데이트"""
    try:
        project_path = project_manager.get_project_path(project_id)
        agents_file = project_path / "agents.yaml"

        if not agents_file.exists():
            raise HTTPException(status_code=404, detail="에이전트 설정을 찾을 수 없습니다.")

        with open(agents_file, 'r', encoding='utf-8') as f:
            data = yaml.safe_load(f)

        agent_found = False
        for i, agent in enumerate(data.get("agents", [])):
            if agent.get("id") == agent_id:
                agent_found = True
                old_name = agent.get("name", "")

                agent["name"] = agent_data.name
                agent["type"] = agent_data.type
                agent["ai"] = {
                    "provider": agent_data.provider,
                    "model": agent_data.model
                }

                if agent_data.api_key:
                    agent["ai"]["api_key"] = agent_data.api_key

                # Phase 16: allowed_nodes 우선, 하위 호환으로 allowed_tools도 지원
                if agent_data.allowed_nodes is not None:
                    agent["allowed_nodes"] = agent_data.allowed_nodes
                    agent["ibl_only"] = True
                    agent.pop("allowed_tools", None)  # 구 필드 제거
                elif agent_data.allowed_tools is not None:
                    agent["allowed_tools"] = agent_data.allowed_tools

                if agent_data.type == "external" and agent_data.channel:
                    agent["channel"] = agent_data.channel
                    if agent_data.email:
                        agent["email"] = agent_data.email

                data["agents"][i] = agent

                if agent_data.role is not None:
                    role_file = project_path / f"agent_{agent_data.name}_role.txt"
                    role_file.write_text(agent_data.role, encoding='utf-8')

                    if old_name and old_name != agent_data.name:
                        old_role_file = project_path / f"agent_{old_name}_role.txt"
                        if old_role_file.exists():
                            old_role_file.unlink()

                break

        if not agent_found:
            raise HTTPException(status_code=404, detail=f"에이전트 '{agent_id}'를 찾을 수 없습니다.")

        with open(agents_file, 'w', encoding='utf-8') as f:
            yaml.dump(data, f, allow_unicode=True, default_flow_style=False)

        return {"status": "updated", "agent_id": agent_id}

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/projects/{project_id}/agents/{agent_id}")
async def delete_agent(project_id: str, agent_id: str):
    """에이전트 삭제"""
    try:
        project_path = project_manager.get_project_path(project_id)
        agents_file = project_path / "agents.yaml"

        if not agents_file.exists():
            raise HTTPException(status_code=404, detail="에이전트 설정을 찾을 수 없습니다.")

        with open(agents_file, 'r', encoding='utf-8') as f:
            data = yaml.safe_load(f)

        agent_name = None
        for i, agent in enumerate(data.get("agents", [])):
            if agent.get("id") == agent_id:
                agent_name = agent.get("name")
                del data["agents"][i]
                break

        if agent_name is None:
            raise HTTPException(status_code=404, detail=f"에이전트 '{agent_id}'를 찾을 수 없습니다.")

        with open(agents_file, 'w', encoding='utf-8') as f:
            yaml.dump(data, f, allow_unicode=True, default_flow_style=False)

        # 관련 파일 삭제
        for suffix in ["_role.txt", "_note.txt"]:
            file = project_path / f"agent_{agent_name}{suffix}"
            if file.exists():
                file.unlink()

        return {"status": "deleted", "agent_id": agent_id}

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
