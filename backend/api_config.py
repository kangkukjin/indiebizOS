"""
api_config.py - 설정/프로필/스케줄러 API
IndieBiz OS Core
"""

import os
import json
from pathlib import Path
from datetime import datetime
from typing import Dict, Any

from fastapi import APIRouter, HTTPException, BackgroundTasks
import yaml

from scheduler import get_scheduler
from runtime_utils import get_base_path as _get_base_path

router = APIRouter()

# 경로 설정
BACKEND_PATH = Path(__file__).parent
from runtime_utils import get_data_path as _get_data_path
DATA_PATH = _get_data_path()
ENV_PATH = _get_base_path() / ".env"

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


# ============ 소유자 식별 정보 API ============

def _read_env_value(key: str) -> str:
    """`.env` 파일에서 특정 키 값 읽기"""
    if not ENV_PATH.exists():
        return ""
    for line in ENV_PATH.read_text(encoding='utf-8').splitlines():
        line = line.strip()
        if line.startswith(f"{key}="):
            return line[len(key) + 1:]
    return ""


def _write_env_value(key: str, value: str):
    """`.env` 파일에서 특정 키 값 업데이트 (없으면 추가)"""
    if not ENV_PATH.exists():
        ENV_PATH.write_text(f"{key}={value}\n", encoding='utf-8')
        return

    lines = ENV_PATH.read_text(encoding='utf-8').splitlines()
    found = False
    for i, line in enumerate(lines):
        if line.strip().startswith(f"{key}="):
            lines[i] = f"{key}={value}"
            found = True
            break
    if not found:
        lines.append(f"{key}={value}")

    ENV_PATH.write_text('\n'.join(lines) + '\n', encoding='utf-8')

    # 환경변수도 즉시 반영
    os.environ[key] = value


@router.get("/owner-identities")
async def get_owner_identities():
    """소유자 식별 정보 조회"""
    try:
        emails = _read_env_value("OWNER_EMAILS")
        nostr_pubkeys = _read_env_value("OWNER_NOSTR_PUBKEYS")
        system_ai_gmail = _read_env_value("SYSTEM_AI_GMAIL")
        return {
            "owner_emails": emails,
            "owner_nostr_pubkeys": nostr_pubkeys,
            "system_ai_gmail": system_ai_gmail
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.put("/owner-identities")
async def update_owner_identities(data: Dict[str, str]):
    """소유자 식별 정보 업데이트"""
    try:
        if "owner_emails" in data:
            _write_env_value("OWNER_EMAILS", data["owner_emails"])
        if "owner_nostr_pubkeys" in data:
            _write_env_value("OWNER_NOSTR_PUBKEYS", data["owner_nostr_pubkeys"])
        if "system_ai_gmail" in data:
            _write_env_value("SYSTEM_AI_GMAIL", data["system_ai_gmail"])

        # channel_poller의 소유자 캐시 갱신
        try:
            from channel_poller import _poller_instance
            if _poller_instance:
                from channel_poller import _load_owner_identities
                _poller_instance._owner_identities = _load_owner_identities()
        except Exception:
            pass

        return {"status": "updated"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ============ 설정 내보내기/가져오기 API ============

import io
import tempfile
import shutil
import zipfile
from fastapi import UploadFile, File
from fastapi.responses import StreamingResponse


@router.post("/config/export")
async def export_config():
    """
    설정 및 프로젝트를 ZIP 파일로 내보내기

    포함:
    - projects/ 폴더 (agents.yaml, agent_*_role.txt, project.json 등)
    - data/system_ai_state/system_ai_role.txt (시스템 AI 역할)
    - 소유자 정보 (.env에서 OWNER_* 만)

    제외:
    - API 키, OAuth 토큰
    - .db 파일 (대화 기록)
    - tokens/ 폴더
    """
    try:
        base_path = _get_base_path()
        projects_path = base_path / "projects"

        # 메모리에 ZIP 파일 생성
        zip_buffer = io.BytesIO()

        with zipfile.ZipFile(zip_buffer, 'w', zipfile.ZIP_DEFLATED) as zf:
            exported_files = 0

            # 1. 프로젝트 폴더 복사 (민감 정보 제외)
            if projects_path.exists():
                for project_dir in projects_path.iterdir():
                    if not project_dir.is_dir():
                        continue

                    # 복사할 파일 패턴
                    include_patterns = [
                        "agents.yaml",
                        "project.json",
                        "config.yaml",
                        "agent_*_role.txt",
                        "agent_*_note.txt",
                        "README.md",
                    ]

                    for pattern in include_patterns:
                        for matched_file in project_dir.glob(pattern):
                            if matched_file.is_file():
                                try:
                                    arcname = f"projects/{project_dir.name}/{matched_file.name}"

                                    if matched_file.name == "agents.yaml":
                                        # agents.yaml에서 API 키 제거
                                        content = _get_agents_yaml_without_secrets(matched_file)
                                        zf.writestr(arcname, content)
                                    else:
                                        zf.write(matched_file, arcname)

                                    exported_files += 1
                                except Exception as e:
                                    print(f"[export] 파일 복사 실패: {matched_file} - {e}")

                    # 하위 디렉토리 복사 (agent_roles 등, 대화기록 제외)
                    include_dirs = ["agent_roles"]
                    exclude_extensions = {".db", ".db-shm", ".db-wal", ".sqlite", ".sqlite3"}
                    for dir_name in include_dirs:
                        sub_dir = project_dir / dir_name
                        if sub_dir.exists() and sub_dir.is_dir():
                            for sub_file in sub_dir.rglob("*"):
                                if sub_file.is_file() and sub_file.suffix.lower() not in exclude_extensions:
                                    try:
                                        rel_path = sub_file.relative_to(project_dir)
                                        arcname = f"projects/{project_dir.name}/{rel_path}"
                                        zf.write(sub_file, arcname)
                                        exported_files += 1
                                    except Exception as e:
                                        print(f"[export] 하위 파일 복사 실패: {sub_file} - {e}")

            # 2. 시스템 AI 역할 프롬프트
            system_ai_state = DATA_PATH / "system_ai_state"
            if system_ai_state.exists():
                for file_name in ["system_ai_role.txt", "system_ai_note.txt"]:
                    src = system_ai_state / file_name
                    if src.exists():
                        arcname = f"data/system_ai_state/{file_name}"
                        zf.write(src, arcname)
                        exported_files += 1

            # 3. 소유자 정보 (민감 정보 제외)
            if ENV_PATH.exists():
                owner_info = {}
                for line in ENV_PATH.read_text(encoding='utf-8').splitlines():
                    line = line.strip()
                    if line.startswith("OWNER_EMAILS="):
                        owner_info["OWNER_EMAILS"] = line.split("=", 1)[1]
                    elif line.startswith("OWNER_NOSTR_PUBKEYS="):
                        owner_info["OWNER_NOSTR_PUBKEYS"] = line.split("=", 1)[1]

                if owner_info:
                    zf.writestr("owner_info.json", json.dumps(owner_info, ensure_ascii=False, indent=2))
                    exported_files += 1

            # 내보낼 파일이 없는 경우
            if exported_files == 0:
                raise HTTPException(status_code=400, detail="내보낼 설정이 없습니다.")

        # 버퍼 위치를 처음으로
        zip_buffer.seek(0)

        filename = f"indiebiz-config-{datetime.now().strftime('%Y%m%d')}.zip"

        return StreamingResponse(
            zip_buffer,
            media_type='application/zip',
            headers={
                'Content-Disposition': f'attachment; filename="{filename}"'
            }
        )

    except HTTPException:
        raise
    except Exception as e:
        print(f"[export] 오류: {e}")
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"내보내기 실패: {str(e)}")


def _get_agents_yaml_without_secrets(src: Path) -> str:
    """agents.yaml에서 API 키 등 민감 정보 제거 후 문자열 반환"""
    with open(src, 'r', encoding='utf-8') as f:
        data = yaml.safe_load(f) or {}

    # system_ai에서 API 키 제거
    if 'system_ai' in data and 'api_key' in data['system_ai']:
        data['system_ai']['api_key'] = ""

    # 각 에이전트에서 API 키 제거
    for agent in data.get('agents', []):
        if 'ai' in agent and 'api_key' in agent['ai']:
            agent['ai']['api_key'] = ""
        # OAuth 정보도 제거
        if 'client_id' in agent:
            del agent['client_id']
        if 'client_secret' in agent:
            del agent['client_secret']

    return yaml.dump(data, allow_unicode=True, default_flow_style=False)


def _copy_agents_yaml_without_secrets(src: Path, dst: Path):
    """agents.yaml에서 API 키 등 민감 정보 제거 후 복사"""
    content = _get_agents_yaml_without_secrets(src)
    with open(dst, 'w', encoding='utf-8') as f:
        f.write(content)


@router.post("/config/import")
async def import_config(file: UploadFile = File(...)):
    """
    ZIP 파일에서 설정 및 프로젝트 가져오기

    - 기존 프로젝트와 병합 (같은 이름은 덮어쓰기)
    - API 키는 가져오지 않음 (사용자가 직접 설정)
    - projects.json 마스터 목록 자동 업데이트
    """
    try:
        base_path = _get_base_path()
        projects_path = base_path / "projects"
        projects_path.mkdir(exist_ok=True)

        # 업로드된 파일을 임시 저장
        with tempfile.NamedTemporaryFile(delete=False, suffix='.zip') as tmp:
            upload_content = await file.read()
            tmp.write(upload_content)
            tmp_path = tmp.name

        projects_imported = 0
        imported_project_names = []

        try:
            with tempfile.TemporaryDirectory() as temp_dir:
                # ZIP 압축 해제
                with zipfile.ZipFile(tmp_path, 'r') as zf:
                    zf.extractall(temp_dir)

                temp_path = Path(temp_dir)

                # 1. 프로젝트 가져오기
                import_projects = temp_path / "projects"
                if import_projects.exists():
                    for project_dir in import_projects.iterdir():
                        if not project_dir.is_dir():
                            continue

                        target_project = projects_path / project_dir.name

                        # 기존 프로젝트가 있으면 병합, 없으면 생성
                        is_new_project = not target_project.exists()
                        if is_new_project:
                            target_project.mkdir()

                        # 파일 및 하위 디렉토리 복사 (기존 API 키 보존)
                        for item in project_dir.iterdir():
                            if item.is_file():
                                if item.name == "agents.yaml" and (target_project / "agents.yaml").exists():
                                    # 기존 agents.yaml의 API 키 보존하며 병합
                                    _merge_agents_yaml(item, target_project / "agents.yaml")
                                else:
                                    shutil.copy2(item, target_project / item.name)
                            elif item.is_dir():
                                # 하위 디렉토리도 복사 (agent_roles 등)
                                target_subdir = target_project / item.name
                                if target_subdir.exists():
                                    shutil.rmtree(target_subdir)
                                shutil.copytree(item, target_subdir)

                        imported_project_names.append(project_dir.name)
                        projects_imported += 1

                # 2. projects.json 마스터 목록 업데이트
                projects_json_path = projects_path / "projects.json"
                existing_projects = []
                if projects_json_path.exists():
                    try:
                        with open(projects_json_path, 'r', encoding='utf-8') as pf:
                            existing_projects = json.load(pf)
                    except Exception:
                        existing_projects = []

                existing_names = {p.get("name") for p in existing_projects}

                for proj_name in imported_project_names:
                    if proj_name not in existing_names:
                        # 새 프로젝트를 목록에 추가
                        project_info = {
                            "id": proj_name,
                            "name": proj_name,
                            "type": "project",
                            "path": str(projects_path / proj_name),
                            "created_at": datetime.now().isoformat(),
                            "icon_position": [100 + len(existing_projects) * 20, 100 + len(existing_projects) * 20],
                            "parent_folder": None,
                            "last_opened": None
                        }
                        existing_projects.append(project_info)
                        print(f"[import] 프로젝트 목록에 추가: {proj_name}")

                with open(projects_json_path, 'w', encoding='utf-8') as pf:
                    json.dump(existing_projects, pf, ensure_ascii=False, indent=2)

                # 3. 시스템 AI 상태 가져오기
                import_state = temp_path / "data" / "system_ai_state"
                if import_state.exists():
                    target_state = DATA_PATH / "system_ai_state"
                    target_state.mkdir(parents=True, exist_ok=True)

                    for state_file in import_state.iterdir():
                        if state_file.is_file():
                            shutil.copy2(state_file, target_state / state_file.name)

                # 4. 소유자 정보 가져오기 (기존 값이 없을 때만)
                owner_info_file = temp_path / "owner_info.json"
                if owner_info_file.exists():
                    with open(owner_info_file, 'r', encoding='utf-8') as oi_f:
                        owner_info = json.load(oi_f)

                    # 기존 값이 없을 때만 설정
                    if owner_info.get("OWNER_EMAILS") and not _read_env_value("OWNER_EMAILS"):
                        _write_env_value("OWNER_EMAILS", owner_info["OWNER_EMAILS"])
                    if owner_info.get("OWNER_NOSTR_PUBKEYS") and not _read_env_value("OWNER_NOSTR_PUBKEYS"):
                        _write_env_value("OWNER_NOSTR_PUBKEYS", owner_info["OWNER_NOSTR_PUBKEYS"])

        finally:
            # 임시 파일 삭제
            os.unlink(tmp_path)

        return {
            "status": "success",
            "projects_imported": projects_imported,
            "message": f"{projects_imported}개 프로젝트를 가져왔습니다."
        }

    except zipfile.BadZipFile:
        raise HTTPException(status_code=400, detail="유효하지 않은 ZIP 파일입니다.")
    except Exception as e:
        print(f"[import] 오류: {e}")
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))


def _merge_agents_yaml(src: Path, dst: Path):
    """agents.yaml 병합 (기존 API 키 보존)"""
    # 기존 파일 읽기
    with open(dst, 'r', encoding='utf-8') as f:
        existing = yaml.safe_load(f) or {}

    # 새 파일 읽기
    with open(src, 'r', encoding='utf-8') as f:
        new_data = yaml.safe_load(f) or {}

    # 기존 API 키 백업
    existing_api_keys = {}
    if 'system_ai' in existing and existing['system_ai'].get('api_key'):
        existing_api_keys['system_ai'] = existing['system_ai']['api_key']

    for agent in existing.get('agents', []):
        if agent.get('ai', {}).get('api_key'):
            existing_api_keys[agent['name']] = agent['ai']['api_key']

    # 새 데이터로 덮어쓰기
    merged = new_data.copy()

    # API 키 복원
    if 'system_ai' in merged and 'system_ai' in existing_api_keys:
        merged['system_ai']['api_key'] = existing_api_keys['system_ai']

    for agent in merged.get('agents', []):
        if agent['name'] in existing_api_keys:
            if 'ai' not in agent:
                agent['ai'] = {}
            agent['ai']['api_key'] = existing_api_keys[agent['name']]

    # 저장
    with open(dst, 'w', encoding='utf-8') as f:
        yaml.dump(merged, f, allow_unicode=True, default_flow_style=False)
