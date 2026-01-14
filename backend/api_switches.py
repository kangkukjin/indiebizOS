"""
api_switches.py - 스위치 관련 API
IndieBiz OS Core
"""

from fastapi import APIRouter, HTTPException, BackgroundTasks

from api_models import SwitchCreate, PositionUpdate, RenameRequest

router = APIRouter()

# 매니저 인스턴스는 api.py에서 주입받음
switch_manager = None


def init_manager(sm):
    """매니저 인스턴스 초기화"""
    global switch_manager
    switch_manager = sm


# ============ 스위치 API ============

@router.get("/switches")
async def list_switches():
    """모든 스위치 목록"""
    try:
        switches = switch_manager.list_switches()
        return {"switches": switches}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/switches")
async def create_switch(switch: SwitchCreate):
    """새 스위치 생성 - 프로젝트 설정을 완전히 복사하여 독립적으로 저장"""
    import yaml
    from project_manager import ProjectManager

    try:
        config = switch.config.copy() if switch.config else {}
        project_id = config.get("projectId")
        agent_name = config.get("agentName")

        # 프로젝트에서 설정 복사
        if project_id:
            pm = ProjectManager()
            project_path = pm.get_project_path(project_id)
            agents_file = project_path / "agents.yaml"

            if agents_file.exists():
                with open(agents_file, 'r', encoding='utf-8') as f:
                    project_config = yaml.safe_load(f) or {}

                # 에이전트 찾기
                agents = project_config.get("agents", [])
                agent = None
                for a in agents:
                    if a.get("name") == agent_name or a.get("id") == agent_name:
                        agent = a
                        break

                if not agent and agents:
                    agent = agents[0]

                # 에이전트 설정 복사
                if agent:
                    config["agent_name"] = agent.get("name", agent_name)
                    config["agent_role"] = agent.get("role_description", "")
                    config["tools"] = agent.get("allowed_tools", [])

                    # AI 설정: 에이전트 내부 설정 우선, 없으면 common에서
                    agent_ai = agent.get("ai", {})
                    if agent_ai.get("api_key"):
                        config["ai"] = {
                            "provider": agent_ai.get("provider", "anthropic"),
                            "api_key": agent_ai.get("api_key", ""),
                            "model": agent_ai.get("model", "claude-sonnet-4-20250514")
                        }
                    else:
                        # common에서 AI 설정 가져오기
                        ai_provider = project_config.get("common", {}).get("default_ai", "anthropic")
                        ai_settings = project_config.get("ai", {}).get(ai_provider, {})
                        config["ai"] = {
                            "provider": ai_provider,
                            "api_key": ai_settings.get("api_key", ""),
                            "model": ai_settings.get("model", "claude-sonnet-4-20250514")
                        }

                # 공통 프롬프트 복사
                config["common_prompt"] = project_config.get("common", {}).get("common_prompt", "")

        result = switch_manager.create_switch(
            name=switch.name,
            command=switch.command,
            config=config,
            icon=switch.icon,
            description=switch.description
        )
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/switches/{switch_id}")
async def get_switch(switch_id: str):
    """특정 스위치 조회"""
    switch = switch_manager.get_switch(switch_id)
    if not switch:
        raise HTTPException(status_code=404, detail="Switch not found")
    return switch


@router.delete("/switches/{switch_id}")
async def delete_switch(switch_id: str):
    """스위치 삭제"""
    if switch_manager.delete_switch(switch_id):
        return {"status": "deleted", "switch_id": switch_id}
    raise HTTPException(status_code=404, detail="Switch not found")


@router.put("/switches/{switch_id}/position")
async def update_switch_position(switch_id: str, position: PositionUpdate):
    """스위치 아이콘 위치 업데이트"""
    try:
        switch_manager.update_position(switch_id, position.x, position.y)
        return {"status": "updated", "switch_id": switch_id}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/switches/{switch_id}/execute")
async def execute_switch(switch_id: str, background_tasks: BackgroundTasks):
    """스위치 실행 - 저장된 설정을 그대로 사용 (프로젝트 독립적)"""
    from switch_runner import SwitchRunner

    switch = switch_manager.get_switch(switch_id)
    if not switch:
        raise HTTPException(status_code=404, detail="Switch not found")

    # 스위치에 저장된 설정 그대로 사용 (이미 생성 시 복사됨)
    config = switch.get("config", {})

    # AI 설정이 없으면 에러
    if not config.get("ai", {}).get("api_key"):
        raise HTTPException(
            status_code=400,
            detail="스위치에 AI 설정이 없습니다. 스위치를 다시 생성해주세요."
        )

    # 스위치 실행 (백그라운드)
    runner = SwitchRunner(switch)

    def on_complete(result):
        print(f"[Switch] {switch.get('name')} 완료: {result.get('success')}")

    runner.run_async(callback=on_complete)

    switch_manager.record_run(switch_id)

    return {"status": "started", "switch_id": switch_id, "switch_name": switch.get("name")}


@router.put("/switches/{switch_id}/rename")
async def rename_switch(switch_id: str, request: RenameRequest):
    """스위치 이름 변경"""
    try:
        result = switch_manager.rename_switch(switch_id, request.new_name)
        if not result:
            raise HTTPException(status_code=404, detail="스위치를 찾을 수 없습니다.")
        return {"status": "renamed", "item": result}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/switches/{switch_id}/copy")
async def copy_switch(switch_id: str):
    """스위치 복사"""
    try:
        result = switch_manager.copy_switch(switch_id)
        if not result:
            raise HTTPException(status_code=404, detail="스위치를 찾을 수 없습니다.")
        return {"status": "copied", "item": result}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/switches/{switch_id}/trash")
async def move_switch_to_trash(switch_id: str):
    """스위치를 휴지통으로 이동"""
    try:
        result = switch_manager.move_to_trash(switch_id)
        if not result:
            raise HTTPException(status_code=404, detail="스위치를 찾을 수 없습니다.")
        return {"status": "trashed", "item": result}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
