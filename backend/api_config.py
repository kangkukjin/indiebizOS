"""
api_config.py - 설정/프로필/스케줄러 API
IndieBiz OS Core
"""

import json
from pathlib import Path
from datetime import datetime
from typing import Dict, Any

from fastapi import APIRouter, HTTPException, BackgroundTasks
import yaml

from scheduler import get_scheduler

router = APIRouter()

# 경로 설정
BACKEND_PATH = Path(__file__).parent
from runtime_utils import get_data_path as _get_data_path
DATA_PATH = _get_data_path()

SYSTEM_MEMO_PATH = DATA_PATH / "system_ai_memo.txt"
SCHEDULE_CONFIG_PATH = DATA_PATH / "program_schedule.json"
SYSTEM_AI_CONFIG_PATH = DATA_PATH / "system_ai_config.json"

# 매니저 인스턴스
project_manager = None


def init_manager(pm):
    """매니저 인스턴스 초기화"""
    global project_manager
    project_manager = pm


# ============ 설정 API ============

@router.get("/config")
async def get_config():
    """시스템 설정 조회 (전역)"""
    try:
        config_path = BACKEND_PATH / "config.yaml"
        if not config_path.exists():
            return {"config": {}}

        with open(config_path, 'r', encoding='utf-8') as f:
            config = yaml.safe_load(f)

        # API 키는 마스킹
        if 'ai' in config:
            for provider in config['ai']:
                if 'api_key' in config['ai'][provider]:
                    key = config['ai'][provider]['api_key']
                    if key:
                        config['ai'][provider]['api_key'] = key[:8] + '...' + key[-4:]

        return {"config": config}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.put("/config")
async def update_config(config: Dict[str, Any]):
    """시스템 설정 업데이트"""
    try:
        config_path = BACKEND_PATH / "config.yaml"

        existing = {}
        if config_path.exists():
            with open(config_path, 'r', encoding='utf-8') as f:
                existing = yaml.safe_load(f) or {}

        existing.update(config)

        with open(config_path, 'w', encoding='utf-8') as f:
            yaml.dump(existing, f, allow_unicode=True, default_flow_style=False)

        return {"status": "updated"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/projects/{project_id}/config")
async def get_project_config(project_id: str):
    """프로젝트별 설정 조회"""
    try:
        project_path = project_manager.get_project_path(project_id)

        result = {
            "system_ai": {},
            "common_settings": "",
            "agents": [],
            "default_tools": [],
        }

        # project.json에서 default_tools 로드
        project_json = project_path / "project.json"
        if project_json.exists():
            with open(project_json, 'r', encoding='utf-8') as f:
                project_data = json.load(f)
                result['default_tools'] = project_data.get('default_tools', [])

        agents_file = project_path / "agents.yaml"
        if agents_file.exists():
            with open(agents_file, 'r', encoding='utf-8') as f:
                data = yaml.safe_load(f) or {}

            if 'system_ai' in data:
                sys_ai = data['system_ai'].copy()
                if sys_ai.get('api_key'):
                    key = sys_ai['api_key']
                    sys_ai['api_key'] = key[:8] + '...' + key[-4:] if len(key) > 12 else '***'
                result['system_ai'] = sys_ai

            if 'agents' in data:
                agents = []
                for agent in data['agents']:
                    agent_copy = agent.copy()
                    if agent_copy.get('ai', {}).get('api_key'):
                        key = agent_copy['ai']['api_key']
                        agent_copy['ai'] = agent_copy['ai'].copy()
                        agent_copy['ai']['api_key'] = key[:8] + '...' + key[-4:] if len(key) > 12 else '***'
                    agents.append(agent_copy)
                result['agents'] = agents

            if 'common' in data:
                result['common'] = data['common']

        common_file = project_path / "common_settings.txt"
        if common_file.exists():
            result['common_settings'] = common_file.read_text(encoding='utf-8')

        return {"config": result}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.put("/projects/{project_id}/config")
async def update_project_config(project_id: str, config: Dict[str, Any]):
    """프로젝트별 설정 업데이트"""
    try:
        project_path = project_manager.get_project_path(project_id)
        agents_file = project_path / "agents.yaml"

        if agents_file.exists():
            with open(agents_file, 'r', encoding='utf-8') as f:
                data = yaml.safe_load(f) or {}
        else:
            data = {}

        if 'system_ai' in config:
            if 'system_ai' not in data:
                data['system_ai'] = {}
            new_sys_ai = config['system_ai']
            if new_sys_ai.get('api_key', '').endswith('...'):
                new_sys_ai['api_key'] = data.get('system_ai', {}).get('api_key', '')
            data['system_ai'].update(new_sys_ai)

        if 'common' in config:
            if 'common' not in data:
                data['common'] = {}
            data['common'].update(config['common'])

        with open(agents_file, 'w', encoding='utf-8') as f:
            yaml.dump(data, f, allow_unicode=True, default_flow_style=False)

        # default_tools를 project.json에 저장
        if 'default_tools' in config:
            project_json = project_path / "project.json"
            if project_json.exists():
                with open(project_json, 'r', encoding='utf-8') as f:
                    project_data = json.load(f)
            else:
                project_data = {}

            project_data['default_tools'] = config['default_tools']

            with open(project_json, 'w', encoding='utf-8') as f:
                json.dump(project_data, f, ensure_ascii=False, indent=2)

        return {"status": "updated"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ============ 프로필 API ============

class ProfileUpdate:
    def __init__(self, content: str):
        self.content = content

@router.get("/profile")
async def get_profile():
    """시스템 메모 조회"""
    try:
        content = ""
        if SYSTEM_MEMO_PATH.exists():
            content = SYSTEM_MEMO_PATH.read_text(encoding='utf-8')
        return {"content": content}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.put("/profile")
async def update_profile(profile: Dict[str, str]):
    """시스템 메모 업데이트"""
    try:
        SYSTEM_MEMO_PATH.parent.mkdir(parents=True, exist_ok=True)
        SYSTEM_MEMO_PATH.write_text(profile.get('content', ''), encoding='utf-8')
        return {"status": "updated"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ============ 스케줄러 API ============

def load_schedule_config() -> dict:
    """스케줄 설정 로드"""
    if SCHEDULE_CONFIG_PATH.exists():
        try:
            with open(SCHEDULE_CONFIG_PATH, 'r', encoding='utf-8') as f:
                return json.load(f)
        except:
            pass
    return {"tasks": []}


def save_schedule_config(config: dict):
    """스케줄 설정 저장"""
    SCHEDULE_CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(SCHEDULE_CONFIG_PATH, 'w', encoding='utf-8') as f:
        json.dump(config, f, ensure_ascii=False, indent=2)


@router.get("/scheduler/tasks")
async def get_scheduler_tasks():
    """스케줄러 작업 목록"""
    try:
        config = load_schedule_config()
        return {"tasks": config.get("tasks", [])}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/scheduler/actions")
async def get_scheduler_actions():
    """사용 가능한 스케줄러 작업 종류"""
    return {
        "actions": [
            {"id": "custom", "name": "사용자 정의"},
        ]
    }


@router.post("/scheduler/tasks")
async def create_scheduler_task(task: Dict[str, Any]):
    """스케줄러 작업 추가"""
    try:
        config = load_schedule_config()

        task_id = f"task_{int(datetime.now().timestamp())}"
        new_task = {
            "id": task_id,
            "name": task.get("name", ""),
            "description": task.get("description", ""),
            "time": task.get("time", "09:00"),
            "enabled": task.get("enabled", True),
            "action": task.get("action", "custom"),
            "last_run": None
        }

        config["tasks"].append(new_task)
        save_schedule_config(config)

        return new_task
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.put("/scheduler/tasks/{task_id}")
async def update_scheduler_task(task_id: str, task: Dict[str, Any]):
    """스케줄러 작업 수정"""
    try:
        config = load_schedule_config()

        for t in config["tasks"]:
            if t["id"] == task_id:
                for key in ["name", "description", "time", "action", "enabled"]:
                    if key in task:
                        t[key] = task[key]

                save_schedule_config(config)
                return t

        raise HTTPException(status_code=404, detail="Task not found")
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/scheduler/tasks/{task_id}")
async def delete_scheduler_task(task_id: str):
    """스케줄러 작업 삭제"""
    try:
        config = load_schedule_config()
        original_len = len(config["tasks"])
        config["tasks"] = [t for t in config["tasks"] if t["id"] != task_id]

        if len(config["tasks"]) < original_len:
            save_schedule_config(config)
            return {"status": "deleted", "task_id": task_id}

        raise HTTPException(status_code=404, detail="Task not found")
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/scheduler/tasks/{task_id}/toggle")
async def toggle_scheduler_task(task_id: str):
    """스케줄러 작업 활성화/비활성화 토글"""
    try:
        config = load_schedule_config()

        for t in config["tasks"]:
            if t["id"] == task_id:
                t["enabled"] = not t.get("enabled", True)
                save_schedule_config(config)
                return {"status": "toggled", "enabled": t["enabled"]}

        raise HTTPException(status_code=404, detail="Task not found")
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/scheduler/tasks/{task_id}/run")
async def run_scheduler_task(task_id: str, background_tasks: BackgroundTasks):
    """스케줄러 작업 즉시 실행"""
    try:
        config = load_schedule_config()

        for t in config["tasks"]:
            if t["id"] == task_id:
                # TODO: 백그라운드에서 실행
                return {"status": "started", "task_id": task_id}

        raise HTTPException(status_code=404, detail="Task not found")
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ============ 시스템 AI 설정 API ============

def get_default_system_ai_config() -> dict:
    """기본 시스템 AI 설정"""
    return {
        "enabled": True,
        "provider": "anthropic",
        "model": "claude-sonnet-4-20250514",
        "apiKey": "",
        "role": ""
    }


@router.get("/system-ai")
async def get_system_ai_config():
    """전역 시스템 AI 설정 조회"""
    try:
        if SYSTEM_AI_CONFIG_PATH.exists():
            with open(SYSTEM_AI_CONFIG_PATH, 'r', encoding='utf-8') as f:
                config = json.load(f)
        else:
            config = get_default_system_ai_config()
        return {"config": config}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.put("/system-ai")
async def update_system_ai_config(config: Dict[str, Any]):
    """전역 시스템 AI 설정 저장"""
    try:
        config_dict = {
            "enabled": config.get("enabled", True),
            "provider": config.get("provider", "anthropic"),
            "model": config.get("model", "claude-sonnet-4-20250514"),
            "apiKey": config.get("apiKey", ""),
            "role": config.get("role", "")
        }
        with open(SYSTEM_AI_CONFIG_PATH, 'w', encoding='utf-8') as f:
            json.dump(config_dict, f, ensure_ascii=False, indent=2)
        return {"status": "saved", "config": config_dict}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ============ Ollama 제어 ============

ollama_process = None
ollama_running = False


@router.get("/ollama/status")
async def get_ollama_status():
    """Ollama 상태 확인"""
    import subprocess
    global ollama_running

    try:
        check = subprocess.run(
            ['curl', '-s', 'http://localhost:11434/api/tags'],
            capture_output=True,
            timeout=2
        )
        ollama_running = check.returncode == 0
        return {"running": ollama_running}
    except:
        ollama_running = False
        return {"running": False}


@router.post("/ollama/start")
async def start_ollama():
    """Ollama 서버 시작"""
    import subprocess
    import time
    global ollama_process, ollama_running

    try:
        # 이미 실행 중인지 확인
        check = subprocess.run(
            ['curl', '-s', 'http://localhost:11434/api/tags'],
            capture_output=True,
            timeout=2
        )
        if check.returncode == 0:
            ollama_running = True
            return {"status": "already_running", "running": True}
    except:
        pass

    try:
        ollama_process = subprocess.Popen(
            ['ollama', 'serve'],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL
        )

        # 서버 준비 대기 (최대 10초)
        for i in range(20):
            time.sleep(0.5)
            try:
                check = subprocess.run(
                    ['curl', '-s', 'http://localhost:11434/api/tags'],
                    capture_output=True,
                    timeout=1
                )
                if check.returncode == 0:
                    ollama_running = True
                    return {"status": "started", "running": True}
            except:
                continue

        return {"status": "timeout", "running": False}
    except FileNotFoundError:
        raise HTTPException(status_code=500, detail="ollama가 설치되어 있지 않습니다. https://ollama.com 에서 설치하세요.")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/ollama/stop")
async def stop_ollama():
    """Ollama 서버 중지"""
    import subprocess
    global ollama_process, ollama_running

    try:
        if ollama_process:
            ollama_process.terminate()
            ollama_process.wait(timeout=5)
            ollama_process = None

        # pkill로 확실히 종료
        subprocess.run(['pkill', '-f', 'ollama serve'], stderr=subprocess.DEVNULL)

        ollama_running = False
        return {"status": "stopped", "running": False}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/ollama/models")
async def get_ollama_models():
    """설치된 Ollama 모델 목록 조회"""
    import subprocess
    import json

    try:
        result = subprocess.run(
            ['curl', '-s', 'http://localhost:11434/api/tags'],
            capture_output=True,
            timeout=5
        )
        if result.returncode == 0:
            data = json.loads(result.stdout.decode())
            models = [m["name"] for m in data.get("models", [])]
            return {"models": models, "running": True}
        return {"models": [], "running": False}
    except:
        return {"models": [], "running": False}


# ============ 자동 도구 배분 API ============

@router.post("/projects/{project_id}/auto-assign-tools")
async def auto_assign_tools(project_id: str):
    """시스템 AI를 사용하여 에이전트들에게 도구 자동 배분"""
    try:
        project_path = project_manager.get_project_path(project_id)
        agents_file = project_path / "agents.yaml"

        if not agents_file.exists():
            raise HTTPException(status_code=404, detail="에이전트 설정을 찾을 수 없습니다.")

        with open(agents_file, 'r', encoding='utf-8') as f:
            data = yaml.safe_load(f)

        # 에이전트 정보 수집
        agents_info = []
        for agent in data.get('agents', []):
            # 역할 파일 로드
            role_file = project_path / f"agent_{agent['name']}_role.txt"
            role = ""
            if role_file.exists():
                role = role_file.read_text(encoding='utf-8')

            agents_info.append({
                'name': agent['name'],
                'role': role or '역할 미정의'
            })

        if not agents_info:
            return {"status": "no_agents", "message": "배분할 에이전트가 없습니다."}

        # 자동 배분 실행
        try:
            from tool_selector import SystemDirector

            director = SystemDirector(project_path)
            success = director.force_reallocate_tools(agents_info)

            if success:
                return {
                    "status": "success",
                    "message": "도구 배분이 완료되었습니다.",
                    "assignments": director.assignment_map
                }
            else:
                raise HTTPException(status_code=500, detail="도구 배분에 실패했습니다.")
        except ImportError as e:
            raise HTTPException(status_code=500, detail=f"tool_selector 모듈을 찾을 수 없습니다: {e}")

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/projects/{project_id}/init-tools")
async def init_tools_if_needed(project_id: str):
    """
    프로젝트 열 때 호출 - allowed_tools가 없는 에이전트만 자동 배분
    (이미 allowed_tools가 있으면 스킵)
    """
    try:
        project_path = project_manager.get_project_path(project_id)
        agents_file = project_path / "agents.yaml"

        if not agents_file.exists():
            return {"status": "skip", "message": "에이전트 설정 파일 없음"}

        with open(agents_file, 'r', encoding='utf-8') as f:
            data = yaml.safe_load(f) or {}

        # allowed_tools가 None인 에이전트만 필터링
        agents_needing_tools = []
        for agent in data.get('agents', []):
            if agent.get('allowed_tools') is None:
                # 역할 파일 로드
                role_file = project_path / f"agent_{agent['name']}_role.txt"
                role = ""
                if role_file.exists():
                    role = role_file.read_text(encoding='utf-8')

                agents_needing_tools.append({
                    'name': agent['name'],
                    'role': role or '역할 미정의'
                })

        if not agents_needing_tools:
            return {"status": "skip", "message": "모든 에이전트에 도구가 이미 배분됨"}

        # 자동 배분 실행 (allowed_tools가 None인 에이전트만)
        try:
            from tool_selector import SystemDirector

            director = SystemDirector(project_path)
            director.reallocate_tools(agents_needing_tools)

            return {
                "status": "success",
                "message": f"{len(agents_needing_tools)}개 에이전트에 도구 배분 완료",
                "agents": [a['name'] for a in agents_needing_tools]
            }
        except ImportError:
            return {"status": "error", "message": "tool_selector 모듈 없음"}

    except Exception as e:
        return {"status": "error", "message": str(e)}


