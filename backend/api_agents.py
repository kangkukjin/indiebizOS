"""
api_agents.py - 에이전트 관련 API
IndieBiz OS Core
"""

import uuid
from datetime import datetime
from typing import Dict, Any
from pathlib import Path

from fastapi import APIRouter, HTTPException, BackgroundTasks
from pydantic import BaseModel
import yaml

router = APIRouter()

# 매니저 인스턴스
project_manager = None

# 에이전트 런너 관리 (프로젝트별)
agent_runners: Dict[str, Dict[str, Any]] = {}


class AgentCommand(BaseModel):
    command: str


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
    allowed_tools: list = None
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
async def get_project_agents(project_id: str):
    """프로젝트의 에이전트 목록"""
    try:
        project_path = project_manager.get_project_path(project_id)
        agents_file = project_path / "agents.yaml"

        if not agents_file.exists():
            return {"agents": []}

        with open(agents_file, 'r', encoding='utf-8') as f:
            data = yaml.safe_load(f)

        return {"agents": data.get("agents", [])}
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


@router.post("/projects/{project_id}/cancel_all")
async def cancel_all_agents(project_id: str):
    """프로젝트의 모든 에이전트 작업 중단"""
    try:
        cancelled = []

        if project_id in agent_runners:
            for agent_id, runner_info in list(agent_runners[project_id].items()):
                runner = runner_info.get("runner")
                if runner:
                    runner.cancel()
                    cancelled.append(agent_id)

            agent_runners[project_id] = {}

        return {"status": "cancelled", "cancelled_agents": cancelled}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ============ 에이전트 명령 ============

@router.post("/projects/{project_id}/agents/{agent_id}/command")
async def send_agent_command(project_id: str, agent_id: str, cmd: AgentCommand):
    """에이전트에게 명령 전송"""
    from conversation_db import ConversationDB

    try:
        # 에이전트 실행 중인지 확인
        if project_id not in agent_runners or agent_id not in agent_runners[project_id]:
            raise HTTPException(status_code=400, detail="에이전트가 실행 중이 아닙니다.")

        runner_info = agent_runners[project_id][agent_id]
        runner = runner_info.get("runner")

        if not runner or not runner.ai:
            raise HTTPException(status_code=400, detail="에이전트 AI가 준비되지 않았습니다.")

        project_path = project_manager.get_project_path(project_id)
        agent_name = runner.config.get("name", agent_id)

        # 대화 DB
        db = ConversationDB(str(project_path / "conversations.db"))

        # 사용자 및 에이전트 ID
        user_id = db.get_or_create_agent("user", "human")
        target_agent_id = db.get_or_create_agent(agent_name, "ai_agent")

        # 히스토리 로드
        history = db.get_history_for_ai(target_agent_id, user_id)

        # 사용자 메시지 저장
        db.save_message(user_id, target_agent_id, cmd.command)

        # AI 응답 생성
        response = runner.ai.process_message_with_history(
            message_content=cmd.command,
            from_email="user@gui",
            history=history,
            reply_to="user@gui"
        )

        # AI 응답 저장
        db.save_message(target_agent_id, user_id, response)

        return {"response": response}
    except HTTPException:
        raise
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

        if agent_data.allowed_tools is not None:
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

        return {"status": "created", "agent": new_agent}

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

                if agent_data.allowed_tools is not None:
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
