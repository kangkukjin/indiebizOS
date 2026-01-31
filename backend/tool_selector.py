"""
tool_selector.py - 지능형 도구 선택 및 관리 시스템
IndieBiz OS Core

AI 감독관(Director)을 통해 에이전트의 역할에 맞는 도구를 배분합니다.
설치된 도구 패키지에서 도구 목록을 가져옵니다.
"""

import re
import yaml
import json
import time
from pathlib import Path
from typing import List, Dict, Any

# 경로 설정
BACKEND_PATH = Path(__file__).parent
from runtime_utils import get_base_path as _get_base_path
DATA_PATH = _get_base_path() / "data"
INSTALLED_TOOLS_PATH = DATA_PATH / "packages" / "installed" / "tools"

# 캐시 설정
_tools_cache: List[Dict[str, Any]] = []
_tools_cache_time: float = 0
_packages_cache: List[Dict[str, Any]] = []
_packages_cache_time: float = 0
_CACHE_TTL: float = 60.0  # 60초 캐시


def invalidate_tool_cache():
    """도구 캐시 무효화 (패키지 설치/제거 시 호출)"""
    global _tools_cache, _tools_cache_time, _packages_cache, _packages_cache_time
    _tools_cache = []
    _tools_cache_time = 0
    _packages_cache = []
    _packages_cache_time = 0


def get_installed_tools(use_cache: bool = True) -> List[Dict[str, Any]]:
    """설치된 도구 목록 반환 (tool.json에서 로드, 캐싱 지원)"""
    global _tools_cache, _tools_cache_time

    # 캐시가 유효하면 캐시 반환
    if use_cache and _tools_cache and time.time() - _tools_cache_time < _CACHE_TTL:
        return _tools_cache

    tools = []

    if not INSTALLED_TOOLS_PATH.exists():
        return tools

    for pkg_dir in INSTALLED_TOOLS_PATH.iterdir():
        if not pkg_dir.is_dir() or pkg_dir.name.startswith('.'):
            continue

        tool_json = pkg_dir / "tool.json"
        if not tool_json.exists():
            continue

        try:
            with open(tool_json, 'r', encoding='utf-8') as f:
                tool_data = json.load(f)

            # tool.json 형식 처리
            if isinstance(tool_data, list):
                for tool in tool_data:
                    tool["_package_id"] = pkg_dir.name
                    tools.append(tool)
            elif isinstance(tool_data, dict) and "tools" in tool_data:
                for tool in tool_data["tools"]:
                    tool["_package_id"] = pkg_dir.name
                    tools.append(tool)
            elif isinstance(tool_data, dict) and "name" in tool_data:
                tool_data["_package_id"] = pkg_dir.name
                tools.append(tool_data)
        except Exception as e:
            print(f"[tool_selector] Failed to load {tool_json}: {e}")

    # 캐시 업데이트
    _tools_cache = tools
    _tools_cache_time = time.time()

    return tools


def get_installed_packages(use_cache: bool = True) -> List[Dict[str, Any]]:
    """설치된 패키지 목록 반환 (패키지 단위 정보 포함, 캐싱 지원)"""
    global _packages_cache, _packages_cache_time

    # 캐시가 유효하면 캐시 반환
    if use_cache and _packages_cache and time.time() - _packages_cache_time < _CACHE_TTL:
        return _packages_cache

    packages = []

    if not INSTALLED_TOOLS_PATH.exists():
        return packages

    for pkg_dir in INSTALLED_TOOLS_PATH.iterdir():
        if not pkg_dir.is_dir() or pkg_dir.name.startswith('.'):
            continue

        tool_json = pkg_dir / "tool.json"
        if not tool_json.exists():
            continue

        pkg_info = {
            "id": pkg_dir.name,
            "name": pkg_dir.name.replace('-', ' ').replace('_', ' ').title(),
            "description": "",
            "tools": []
        }

        # README에서 패키지 설명 추출
        for doc_file in ['README.md', 'readme.md']:
            doc_path = pkg_dir / doc_file
            if doc_path.exists():
                try:
                    content = doc_path.read_text(encoding='utf-8')
                    lines = content.strip().split('\n')
                    desc_lines = []
                    for line in lines:
                        line = line.strip()
                        if line.startswith('#') or not line:
                            if desc_lines:
                                break
                            continue
                        desc_lines.append(line)
                        if len(desc_lines) >= 2:
                            break
                    if desc_lines:
                        pkg_info["description"] = ' '.join(desc_lines)[:200]
                except:
                    pass
                break

        # tool.json에서 도구 목록 추출
        try:
            with open(tool_json, 'r', encoding='utf-8') as f:
                tool_data = json.load(f)

            tools = []
            if isinstance(tool_data, list):
                tools = tool_data
            elif isinstance(tool_data, dict) and "tools" in tool_data:
                tools = tool_data["tools"]
            elif isinstance(tool_data, dict) and "name" in tool_data:
                tools = [tool_data]

            pkg_info["tools"] = [t.get("name") for t in tools if t.get("name")]
            pkg_info["tool_count"] = len(pkg_info["tools"])
        except:
            pass

        packages.append(pkg_info)

    # 캐시 업데이트
    _packages_cache = packages
    _packages_cache_time = time.time()

    return packages


def get_base_tools() -> List[str]:
    """기초 도구 이름 목록 반환 (시스템 기본 도구)"""
    return ["call_agent", "list_agents", "send_notification", "get_project_info"]


class SystemDirector:
    """
    프로젝트의 도구 배분과 에이전트 조율을 담당하는 시스템 AI
    """
    def __init__(self, project_path: Path):
        self.project_path = project_path
        self.config = self._load_system_ai_config()
        self.assignment_map = {}  # agent_name -> [tool_names]

    def _load_system_ai_config(self) -> dict:
        """전역 시스템 AI 설정 로드"""
        config_path = DATA_PATH / "system_ai_config.json"
        if config_path.exists():
            try:
                with open(config_path, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except:
                pass
        return {}

    # 도구 배분용 시스템 프롬프트
    TOOL_DISTRIBUTOR_PROMPT = """You are a tool package distributor for IndieBiz OS.

Your task: Assign tool packages to AI agents based on role relevance.

Rules:
- Assign by package ID only (packages contain multiple tools)
- Match package purpose to agent's role description
- Multiple agents can share the same package
- Only assign packages clearly relevant to the role
- IMPORTANT: Keep total tools per agent under 50. If exceeding, assign only the most essential packages.

Output: Return only valid JSON in the specified format."""

    def _call_ai(self, prompt: str, system_role: str = None) -> str:
        """시스템 AI 설정을 사용하여 AI 호출"""
        provider = self.config.get('provider', 'google')
        api_key = self.config.get('apiKey') or self.config.get('api_key')
        model = self.config.get('model', 'gemini-2.0-flash')
        role = system_role or self.TOOL_DISTRIBUTOR_PROMPT

        if not api_key:
            print("⚠️ 시스템 AI: API 키가 설정되지 않았습니다.")
            return ""

        try:
            if provider in ['google', 'gemini']:
                from google import genai
                from google.genai import types
                client = genai.Client(api_key=api_key)
                response = client.models.generate_content(
                    model=model,
                    contents=prompt,
                    config=types.GenerateContentConfig(
                        system_instruction=role
                    )
                )
                return response.text

            elif provider == 'anthropic':
                import anthropic
                client = anthropic.Anthropic(api_key=api_key)
                resp = client.messages.create(
                    model=model,
                    max_tokens=2048,
                    system=role,
                    messages=[{"role": "user", "content": prompt}]
                )
                return resp.content[0].text

            elif provider in ['openai', 'gpt']:
                import openai
                client = openai.OpenAI(api_key=api_key)
                resp = client.chat.completions.create(
                    model=model,
                    messages=[
                        {"role": "system", "content": role},
                        {"role": "user", "content": prompt}
                    ]
                )
                return resp.choices[0].message.content

        except Exception as e:
            print(f"⚠️ 시스템 AI 호출 실패: {e}")
        return ""

    def _build_package_assignment_prompt(self, agents_info: List[Dict[str, str]]) -> str:
        """패키지 단위 배분을 위한 프롬프트 생성"""
        packages = get_installed_packages()

        # 패키지 정보를 간결하게 구성
        packages_list = []
        for pkg in packages:
            tools_preview = ", ".join(pkg["tools"][:3])
            if len(pkg["tools"]) > 3:
                tools_preview += f", ... (+{len(pkg['tools']) - 3})"
            desc = pkg['description'][:100] if pkg['description'] else 'No description'
            packages_list.append(f"- {pkg['id']}: {desc} [tools: {tools_preview}]")
        packages_text = "\n".join(packages_list)

        # 에이전트 정보를 간결하게 구성
        agents_list = [f"- {a['name']}: {a['role']}" for a in agents_info]
        agents_text = "\n".join(agents_list)

        # 패키지 ID 목록 (유효성 검사용)
        valid_pkg_ids = [pkg['id'] for pkg in packages]

        prompt = f"""PACKAGES:
{packages_text}

AGENTS:
{agents_text}

VALID PACKAGE IDs: {valid_pkg_ids}

Return JSON:
{{"배분표": {{"agent_name": ["package_id", ...]}}}}"""
        return prompt

    def _expand_packages_to_tools(self, package_assignments: Dict[str, List[str]]) -> Dict[str, List[str]]:
        """패키지 ID 목록을 실제 도구 이름 목록으로 확장"""
        packages = get_installed_packages()
        pkg_tools_map = {pkg["id"]: pkg["tools"] for pkg in packages}

        expanded = {}
        for agent_name, pkg_ids in package_assignments.items():
            tools = []
            for pkg_id in pkg_ids:
                if pkg_id in pkg_tools_map:
                    tools.extend(pkg_tools_map[pkg_id])
            expanded[agent_name] = tools
        return expanded

    def reallocate_tools(self, agents_info: List[Dict[str, str]]):
        """
        allowed_tools가 None인 에이전트에게만 도구를 배분합니다.
        패키지 단위로 배분 후 도구로 확장합니다.
        """
        prompt = self._build_package_assignment_prompt(agents_info)
        response = self._call_ai(prompt)
        if not response:
            return False

        try:
            json_str = re.search(r'\{.*\}', response, re.DOTALL).group()
            data = json.loads(json_str)
            package_assignments = data.get("배분표", {})

            # 패키지 → 도구로 확장
            self.assignment_map = self._expand_packages_to_tools(package_assignments)
            print(f"✅ [감독관] 도구 배분 완료: {list(self.assignment_map.keys())}")
            for agent, tools in self.assignment_map.items():
                print(f"   📦 {agent}: {len(tools)}개 도구")

            # agents.yaml에 allowed_tools 저장 (force=False)
            self._save_allowed_tools_to_agents_yaml(force=False)
            return True
        except Exception as e:
            print(f"⚠️ [감독관] 배분표 파싱 실패: {e}")
            return False

    def force_reallocate_tools(self, agents_info: List[Dict[str, str]]) -> bool:
        """
        모든 에이전트의 도구를 강제로 재배분합니다. (기존 설정 덮어쓰기)
        설정 화면의 '자동 배분' 버튼용
        """
        prompt = self._build_package_assignment_prompt(agents_info)
        response = self._call_ai(prompt)
        if not response:
            return False

        try:
            json_str = re.search(r'\{.*\}', response, re.DOTALL).group()
            data = json.loads(json_str)
            package_assignments = data.get("배분표", {})

            # 패키지 → 도구로 확장
            self.assignment_map = self._expand_packages_to_tools(package_assignments)
            print(f"✅ [감독관] 도구 재배분 완료: {list(self.assignment_map.keys())}")
            for agent, tools in self.assignment_map.items():
                print(f"   📦 {agent}: {len(tools)}개 도구")

            # 강제로 agents.yaml에 저장
            self._save_allowed_tools_to_agents_yaml(force=True)
            return True
        except Exception as e:
            print(f"⚠️ [감독관] 배분표 파싱 실패: {e}")
            return False

    def _save_allowed_tools_to_agents_yaml(self, force: bool = False):
        """
        배분 결과를 agents.yaml의 각 에이전트 allowed_tools에 저장

        Args:
            force: True면 기존 allowed_tools도 덮어씀 (자동 배분 버튼용)
        """
        agents_yaml_path = self.project_path / "agents.yaml"
        if not agents_yaml_path.exists():
            print("⚠️ [감독관] agents.yaml 파일이 없습니다.")
            return

        try:
            with open(agents_yaml_path, 'r', encoding='utf-8') as f:
                data = yaml.safe_load(f) or {}

            agents = data.get('agents', [])
            updated = False

            for agent in agents:
                agent_name = agent.get('name')
                if agent_name and agent_name in self.assignment_map:
                    # force=True면 무조건 덮어쓰기, False면 None인 경우만
                    if force or agent.get('allowed_tools') is None:
                        agent['allowed_tools'] = self.assignment_map[agent_name]
                        updated = True
                        print(f"   📦 {agent_name}: {len(self.assignment_map[agent_name])}개 도구 배분")

            if updated:
                with open(agents_yaml_path, 'w', encoding='utf-8') as f:
                    yaml.dump(data, f, allow_unicode=True, default_flow_style=False)
                print("✅ [감독관] agents.yaml에 도구 배분 저장 완료")
        except Exception as e:
            print(f"⚠️ [감독관] agents.yaml 저장 실패: {e}")

    def get_tools_for_agent(self, agent_name: str) -> List[str]:
        return self.assignment_map.get(agent_name, [])


# 전역 감독관 인스턴스
director_instance = None
