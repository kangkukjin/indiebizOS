"""
api_config.py - 설정/프로필 API
IndieBiz OS Core
"""

import os
import json
from pathlib import Path
from datetime import datetime
from typing import Dict, Any

from fastapi import APIRouter, HTTPException, BackgroundTasks
import yaml

from runtime_utils import get_base_path as _get_base_path

router = APIRouter()

# 경로 설정
BACKEND_PATH = Path(__file__).parent
from runtime_utils import get_data_path as _get_data_path
DATA_PATH = _get_data_path()
ENV_PATH = _get_base_path() / ".env"

SYSTEM_MEMO_PATH = DATA_PATH / "system_ai_memo.txt"
SYSTEM_AI_CONFIG_PATH = DATA_PATH / "system_ai_config.json"
LIGHTWEIGHT_AI_CONFIG_PATH = DATA_PATH / "lightweight_ai_config.json"
MIDTIER_AI_CONFIG_PATH = DATA_PATH / "midtier_ai_config.json"
# 하위호환: 기존 unconscious_ai_config.json 경로
UNCONSCIOUS_AI_CONFIG_PATH = DATA_PATH / "unconscious_ai_config.json"

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
        # 수동모드 번역용 본격 원샷 프로바이더 캐시 무효화 (모델 변경 즉시 반영)
        try:
            from consciousness_agent import reset_system_oneshot_provider
            reset_system_oneshot_provider()
        except Exception:
            pass
        return {"status": "saved", "config": config_dict}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ============ 경량 AI 설정 API ============

def get_default_lightweight_ai_config() -> dict:
    """기본 경량 AI 설정"""
    return {
        "enabled": True,
        "provider": "google",
        "model": "gemini-2.5-flash-lite",
        "apiKey": ""
    }


def _load_lightweight_config() -> dict:
    """경량 AI 설정 로드 (하위호환: unconscious_ai_config.json 폴백)"""
    if LIGHTWEIGHT_AI_CONFIG_PATH.exists():
        with open(LIGHTWEIGHT_AI_CONFIG_PATH, 'r', encoding='utf-8') as f:
            return json.load(f)
    elif UNCONSCIOUS_AI_CONFIG_PATH.exists():
        with open(UNCONSCIOUS_AI_CONFIG_PATH, 'r', encoding='utf-8') as f:
            return json.load(f)
    return get_default_lightweight_ai_config()


@router.get("/lightweight-ai")
async def get_lightweight_ai_config():
    """경량 AI 설정 조회"""
    try:
        config = _load_lightweight_config()
        return {"config": config}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.put("/lightweight-ai")
async def update_lightweight_ai_config(config: Dict[str, Any]):
    """경량 AI 설정 저장"""
    try:
        config_dict = {
            "enabled": config.get("enabled", True),
            "provider": config.get("provider", "google"),
            "model": config.get("model", "gemini-2.5-flash-lite"),
            "apiKey": config.get("apiKey", ""),
        }
        with open(LIGHTWEIGHT_AI_CONFIG_PATH, 'w', encoding='utf-8') as f:
            json.dump(config_dict, f, ensure_ascii=False, indent=2)
        return {"status": "saved", "config": config_dict}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# 하위호환: /unconscious-ai 엔드포인트 유지
@router.get("/unconscious-ai")
async def get_unconscious_ai_config_compat():
    """무의식 AI 설정 조회 (하위호환 → 경량 AI로 리다이렉트)"""
    return await get_lightweight_ai_config()


@router.put("/unconscious-ai")
async def update_unconscious_ai_config_compat(config: Dict[str, Any]):
    """무의식 AI 설정 저장 (하위호환 → 경량 AI로 리다이렉트)"""
    return await update_lightweight_ai_config(config)


# ============ 중급 AI 설정 API ============

def get_default_midtier_ai_config() -> dict:
    """기본 중급 AI 설정"""
    return {
        "enabled": True,
        "provider": "google",
        "model": "gemini-2.5-flash",
        "apiKey": ""
    }


@router.get("/midtier-ai")
async def get_midtier_ai_config():
    """중급 AI 설정 조회"""
    try:
        if MIDTIER_AI_CONFIG_PATH.exists():
            with open(MIDTIER_AI_CONFIG_PATH, 'r', encoding='utf-8') as f:
                config = json.load(f)
        else:
            config = get_default_midtier_ai_config()
        return {"config": config}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.put("/midtier-ai")
async def update_midtier_ai_config(config: Dict[str, Any]):
    """중급 AI 설정 저장. 저장 후 provider 캐시 무효화하여 즉시 반영."""
    try:
        config_dict = {
            "enabled": config.get("enabled", True),
            "provider": config.get("provider", "google"),
            "model": config.get("model", "gemini-2.5-flash"),
            "apiKey": config.get("apiKey", ""),
        }
        with open(MIDTIER_AI_CONFIG_PATH, 'w', encoding='utf-8') as f:
            json.dump(config_dict, f, ensure_ascii=False, indent=2)

        # 캐시 무효화 — 다음 호출 시 새 config로 provider 재생성
        try:
            from consciousness_agent import reset_midtier_provider
            reset_midtier_provider()
        except Exception as cache_err:
            print(f"[midtier-ai] 캐시 무효화 경고: {cache_err}")

        return {"status": "saved", "config": config_dict}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ============ 모델 기어 (계기판 변속) ============

# 4축 대표 역할 — 기어별로 각 축이 어느 티어/모델로 도는지 표시용.
_GEAR_AXIS_ROLES = {"분류": "classify", "평가": "evaluate", "실행": "execution", "의식": "consciousness"}


def _describe_gear() -> dict:
    """현재 기어 상태 + 4축이 어느 티어/모델로 해소되는지(UI 표시용)."""
    import model_resolver as M
    gear = M._load_gear()
    axes = {}
    for axis, role in _GEAR_AXIS_ROLES.items():
        d = M.resolve(role)
        axes[axis] = {"tier": d.get("tier"), "provider": d.get("provider"), "model": d.get("model")}
    return {
        "current_gear": M.get_gear(),
        "gears": M.list_gears(),
        "presets": gear.get("presets", {}),
        "axes": axes,
        "tiers": M.TIERS,
        "axis_names": M.AXES,
        "consciousness_enabled": M.consciousness_enabled(),
    }


def _reset_gear_providers():
    """기어/프리셋/핀 변경 후 init-시점 provider 핫리로드 — 다음 호출에서 새 티어로 재구성."""
    for mod, fn in (("consciousness_agent", "reset_consciousness_agent"),
                    ("system_ai_core", "reset_system_ai_runner"),
                    ("consciousness_agent", "reset_midtier_provider"),
                    ("consciousness_agent", "reset_lightweight_provider"),
                    ("consciousness_agent", "reset_system_oneshot_provider")):
        try:
            import importlib
            getattr(importlib.import_module(mod), fn)()
        except Exception as reset_err:
            print(f"[model-gear] {mod}.{fn} 리셋 경고: {reset_err}")


def _list_pinnable_agents() -> list:
    """핀(고정) 대상 에이전트 목록 — 시스템 AI + 전 프로젝트 에이전트. {id,name,project}.

    ★id = 핀 키. 시스템 AI 는 role 'system_ai', 프로젝트 에이전트는 registry_key 형식
    `{project}:{agent_id}` (agent_id 가 프로젝트 간 중복이라 프로젝트로 한정 — _resolve_execution_config 와 일치)."""
    out = [
        {"id": "system_ai", "name": "시스템 AI", "project": "(시스템)"},
        # 포식 브라우저 검색 에이전트 — 핀 키 'forage'(resolve/force_role 과 일치). 미핀 시 기본 경량.
        {"id": "forage", "name": "포식 에이전트", "project": "(포식 브라우저)"},
    ]
    try:
        import yaml
        from runtime_utils import get_base_path
        proj_root = get_base_path() / "projects"
        if proj_root.exists():
            for d in sorted([p for p in proj_root.iterdir() if p.is_dir()], key=lambda p: p.name):
                f = d / "agents.yaml"
                if not f.exists():
                    continue
                try:
                    data = yaml.safe_load(f.read_text(encoding="utf-8")) or {}
                    # 디렉토리명(파일시스템)은 한글이 NFD일 수 있어 NFC로 정규화 — 핀 키가
                    # projects.json·URL(NFC)·resolve 와 일관되게 매칭된다.
                    import unicodedata
                    pname = unicodedata.normalize("NFC", d.name)
                    for a in (data.get("agents") or []):
                        if isinstance(a, dict) and a.get("id"):
                            out.append({"id": f"{pname}:{a['id']}",
                                        "name": a.get("name") or a["id"], "project": pname})
                except Exception:
                    pass
    except Exception as e:
        print(f"[model-gear] 에이전트 열거 경고: {e}")
    return out


@router.get("/model-gear")
async def get_model_gear():
    """현재 모델 기어 + 프리셋 + 4축 해소 결과."""
    try:
        return _describe_gear()
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.put("/model-gear")
async def set_model_gear(body: Dict[str, Any]):
    """기어 변속(절약/균형/최대). set_gear 가 리졸버 provider 캐시를 비우고,
    init-시점 provider(의식·시스템AI 러너)도 리셋해 *재시작 없이* 다음 작업부터 새 티어로 돈다.

    ※ 이미 실행 중인 프로젝트 에이전트/안드로이드 에이전트는 자기 provider 를 들고 있어
      다음 (재)시작에서 반영된다(러닝 중 교체는 범위 밖)."""
    try:
        import model_resolver as M
        name = (body.get("gear") or body.get("current_gear") or "").strip()
        if not name:
            raise HTTPException(status_code=400, detail="gear 값이 필요합니다.")
        if not M.set_gear(name):
            raise HTTPException(status_code=400, detail=f"알 수 없는 기어: {name} (가능: {M.list_gears()})")
        _reset_gear_providers()
        return {"status": "changed", **_describe_gear()}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.put("/model-gear/consciousness")
async def set_model_gear_consciousness(body: Dict[str, Any]):
    """의식 토글 — OFF 면 인지 파이프라인이 THINK 경로를 차단(반사 유지 + 나머지 바로 실행).
    핫리로드(매 _decide_request_type 가 consciousness_enabled() 를 새로 읽음) — 재시작 불요."""
    try:
        import model_resolver as M
        enabled = body.get("enabled")
        if enabled is None:
            raise HTTPException(status_code=400, detail="enabled(bool) 값이 필요합니다.")
        M.set_consciousness(bool(enabled))
        return {"status": "changed", **_describe_gear()}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.put("/model-gear/presets")
async def update_model_gear_presets(body: Dict[str, Any]):
    """기어 프리셋 정의 갱신 — 각 기어(절약/균형/최대 등)가 4축(분류·평가·실행·의식)을
    어느 티어(경량/중급/고급)로 매핑하는지 사용자가 직접 편집. body={presets:{기어:{축:티어}}}."""
    try:
        import model_resolver as M
        presets = body.get("presets")
        if not M.set_presets(presets):
            raise HTTPException(status_code=400,
                                detail=f"잘못된 프리셋. 축은 {M.AXES}, 티어는 {M.TIERS} 만 허용.")
        _reset_gear_providers()
        return {"status": "saved", **_describe_gear()}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/model-gear/overrides")
async def get_model_gear_overrides():
    """에이전트 핀(고정) 현황 + 핀 가능한 에이전트 목록 + 티어 옵션."""
    try:
        import model_resolver as M
        return {
            "overrides": M.get_overrides(),
            "agents": _list_pinnable_agents(),
            "tiers": M.TIERS,
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.put("/model-gear/overrides")
async def update_model_gear_overrides(body: Dict[str, Any]):
    """에이전트/역할 핀 갱신 — 특정 에이전트만 기어 무시하고 티어 고정.
    body={overrides:{agent_id 또는 role: 티어명}}. 빈 값/누락 키는 핀 해제."""
    try:
        import model_resolver as M
        overrides = body.get("overrides", {})
        # 빈 문자열/None 값은 핀 해제로 간주 — 정리
        cleaned = {k: v for k, v in (overrides or {}).items() if v}
        if not M.set_overrides(cleaned):
            raise HTTPException(status_code=400, detail=f"잘못된 핀. 티어는 {M.TIERS} 만 허용.")
        _reset_gear_providers()
        return {"status": "saved", "overrides": M.get_overrides()}
    except HTTPException:
        raise
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

        # 외부 프로세스도 확실히 종료 (psutil, 전 OS — 구 pkill 대체)
        from common.platform_utils import kill_processes_by_marker
        kill_processes_by_marker('ollama serve')

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


# ============ 자동 노드 배분 API (Phase 18) ============

@router.post("/projects/{project_id}/auto-assign-tools")
async def auto_assign_tools(project_id: str):
    """시스템 AI를 사용하여 에이전트들에게 IBL 노드 자동 배분 (Phase 18: allowed_nodes)"""
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

        # Phase 18: IBL 노드 배분 실행
        try:
            from tool_selector import SystemDirector

            director = SystemDirector(project_path)
            success = director.force_reallocate_nodes(agents_info)

            if success:
                return {
                    "status": "success",
                    "message": "노드 배분이 완료되었습니다.",
                    "assignments": director.assignment_map
                }
            else:
                raise HTTPException(status_code=500, detail="노드 배분에 실패했습니다.")
        except ImportError as e:
            raise HTTPException(status_code=500, detail=f"tool_selector 모듈을 찾을 수 없습니다: {e}")

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/projects/{project_id}/init-tools")
async def init_tools_if_needed(project_id: str):
    """
    Phase 18: 프로젝트 열 때 호출 - allowed_nodes가 없는 에이전트만 자동 배분
    (이미 allowed_nodes가 있으면 스킵)
    """
    try:
        project_path = project_manager.get_project_path(project_id)
        agents_file = project_path / "agents.yaml"

        if not agents_file.exists():
            return {"status": "skip", "message": "에이전트 설정 파일 없음"}

        with open(agents_file, 'r', encoding='utf-8') as f:
            data = yaml.safe_load(f) or {}

        # Phase 18: allowed_nodes가 None인 에이전트만 필터링
        agents_needing_nodes = []
        for agent in data.get('agents', []):
            if agent.get('allowed_nodes') is None:
                role_file = project_path / f"agent_{agent['name']}_role.txt"
                role = ""
                if role_file.exists():
                    role = role_file.read_text(encoding='utf-8')

                agents_needing_nodes.append({
                    'name': agent['name'],
                    'role': role or '역할 미정의'
                })

        if not agents_needing_nodes:
            return {"status": "skip", "message": "모든 에이전트에 노드가 이미 배분됨"}

        # Phase 18: IBL 노드 배분 실행
        try:
            from tool_selector import SystemDirector

            director = SystemDirector(project_path)
            director.reallocate_nodes(agents_needing_nodes)

            return {
                "status": "success",
                "message": f"{len(agents_needing_nodes)}개 에이전트에 노드 배분 완료",
                "agents": [a['name'] for a in agents_needing_nodes]
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


# ============ World Pulse (세계 상태 감각) ============

@router.get("/world-pulse/config")
async def get_world_pulse_config():
    """World Pulse 설정 조회"""
    try:
        from world_pulse import get_config
        return get_config()
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.put("/world-pulse/config")
async def update_world_pulse_config(config: Dict[str, Any]):
    """World Pulse 설정 저장"""
    try:
        from world_pulse import save_config
        save_config(config)
        return {"status": "saved"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/world-pulse/refresh")
async def refresh_world_pulse():
    """World Pulse 강제 재수집"""
    try:
        from world_pulse import collect_snapshot, save_snapshot, generate_guide
        snapshot = collect_snapshot()
        if "error" in snapshot:
            return snapshot
        save_snapshot(snapshot)
        generate_guide()
        return {"status": "refreshed", "date": snapshot.get("date")}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/world-pulse/today")
async def get_world_pulse_today():
    """오늘의 World Pulse 스냅샷 조회"""
    try:
        from world_pulse import get_today_pulse
        pulse = get_today_pulse()
        if pulse:
            return pulse
        return {"message": "오늘 수집된 데이터가 없습니다."}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/world-pulse/trend")
async def get_world_pulse_trend(days: int = 7):
    """최근 N일간 World Pulse 추이 조회"""
    try:
        from world_pulse import get_pulse_trend
        return {"days": days, "trend": get_pulse_trend(days)}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/world-pulse/pulses")
async def get_world_pulses(hours: int = 24):
    """최근 N시간 World Pulse 조회"""
    try:
        from world_pulse import get_recent_pulses
        return {"hours": hours, "pulses": get_recent_pulses(hours)}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/world-pulse/self-checks")
async def get_self_checks(limit: int = 20):
    """최근 자가점검 결과 조회"""
    try:
        from world_pulse import get_recent_self_checks
        return {"checks": get_recent_self_checks(limit)}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/world-pulse/episodes")
async def get_episodes(limit: int = 30):
    """주행기록계 — 최근 자율주행/시스템AI 에피소드 목록(요약 지표 포함)."""
    try:
        from episode_logger import get_episode_journal
        return {"episodes": get_episode_journal(limit)}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/world-pulse/episodes/{episode_id}/analysis-prompt")
async def get_episode_analysis_prompt(episode_id: int):
    """지난 주행 분석 요청 프롬프트 — 분석 스위치를 누르면 시스템 AI 창이 이걸 받아
    첫 메시지로 보낸다. 전체 실행 로그를 담되 토큰 과대 방지로 끝부분 위주 캡
    (최근 행동이 결과에 가까움)."""
    try:
        from episode_logger import get_episode_detail
        ep = get_episode_detail(episode_id)
        if not ep:
            raise HTTPException(status_code=404, detail="에피소드를 찾을 수 없습니다(로그가 만료됐을 수 있음).")
        log = ep.get("log") or ""
        CAP = 16000
        if len(log) > CAP:
            log = "…(앞부분 생략)…\n" + log[-CAP:]
        user_msg = ep.get("user_message") or ""
        agent = ep.get("agent") or "?"
        started = ep.get("started_at") or ""
        prompt = (
            "#EXECUTE\n"  # 주행기록 분석은 의식(THINK) 불필요 — 무의식 판정을 EXECUTE로 강제
            f"아래는 지난 자율주행 실행 기록이다(에이전트: {agent}, 시각: {started}).\n"
            f"이 주행을 분석해줘:\n"
            f"1) 사용자가 무엇을 원했고, 시스템이 무슨 판단(반사/숙고/실행)으로 어떻게 처리했나\n"
            f"2) 잘된 점\n"
            f"3) 문제점·헤맨 지점(불필요한 라운드, 잘못된 IBL, 침묵 실패 등)\n"
            f"4) 고칠 것 — 가이드/IBL 어휘/프롬프트 중 무엇을 어떻게 바꾸면 다음에 더 나을지\n"
            f"분석 후, 내가 고치라고 하면 바로 실행해줘.\n\n"
            f"=== 사용자 요청 ===\n{user_msg}\n\n"
            f"=== 실행 로그 ===\n{log}\n"
        )
        return {"episode_id": episode_id, "prompt": prompt}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/world-pulse/health")
async def get_health():
    """시스템 전체 건강 요약"""
    try:
        from world_pulse import get_system_health
        return get_system_health()
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/world-pulse/diagnostic-report")
async def get_diagnostic_report(format: str = "json"):
    """통합 진단 리포트 — AI 비용 0, 순수 SQL 집계

    Query params:
        format: "json" (default) 또는 "md" (마크다운 텍스트)
    """
    try:
        from world_pulse_health import generate_diagnostic_report, format_diagnostic_report_md
        if format == "md":
            from fastapi.responses import PlainTextResponse
            report = generate_diagnostic_report()
            md = format_diagnostic_report_md(report)
            return PlainTextResponse(md, media_type="text/plain; charset=utf-8")
        else:
            return generate_diagnostic_report()
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/world-pulse/run-self-check")
async def trigger_self_check():
    """IBL 건강 점검 수동 트리거 (백그라운드) — 정적+fixture+골든 1회 (AI 0)"""
    import threading
    from world_pulse import run_daily_health_check

    def _run():
        try:
            run_daily_health_check()
        except Exception as e:
            logger.error(f"[WorldPulse] 수동 건강 점검 실패: {e}")

    threading.Thread(target=_run, daemon=True, name="manual-health-check").start()
    return {"status": "started", "message": "IBL 건강 점검이 백그라운드에서 시작되었습니다."}


@router.get("/world-pulse/dashboard")
def world_pulse_dashboard():
    """계기판 상태 — 마지막 IBL 건강 + 핵심 vitals (서비스 alive·디스크). 싸고 즉각(검사 실행 X)."""
    from world_pulse_health import get_ibl_health_status
    ibl = get_ibl_health_status()
    services, disk = {}, None
    try:
        from world_pulse import _collect_self_state
        ss = _collect_self_state()
        services = ss.get("services", {})
        disk = ss.get("disk_free_gb")
    except Exception as e:
        logger.debug(f"[Dashboard] self_state 수집 실패: {e}")
    return {"ibl_health": ibl, "services": services, "disk_free_gb": disk}


@router.post("/world-pulse/ibl-health-check")
def run_ibl_health_check_sync():
    """IBL 건강 점검 동기 실행 — 정적(§1A)+fixture 통화(§1B)+골든 파이프(§1C) 결과 반환 (AI 0).

    수동 모드 '건강확인' 버튼용. sync def 라 FastAPI 가 스레드풀에서 돌려(이벤트 루프 비차단),
    수십 초 걸리는 점검을 끝까지 기다렸다가 GREEN/RED 요약을 돌려준다. self_checks 에도 기록.
    """
    from world_pulse_health import run_ibl_health_check, save_self_check
    try:
        events = run_ibl_health_check()
    except Exception as e:
        logger.error(f"[WorldPulse] IBL 건강 점검 실패: {e}")
        raise HTTPException(status_code=500, detail=str(e))
    for ev in events:
        try:
            save_self_check(ev)
        except Exception:
            pass
    healthy = len(events) > 0 and all(ev.get("success") for ev in events)
    return {"healthy": healthy, "events": events}
