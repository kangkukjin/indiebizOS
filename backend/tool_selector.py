"""
tool_selector.py - IBL 노드 배분 시스템 (Phase 18)
IndieBiz OS Core

AI 감독관(Director)을 통해 에이전트의 역할에 맞는 IBL 노드를 배분합니다.
ibl_nodes.yaml에서 노드 목록을 가져와 에이전트별 allowed_nodes를 결정합니다.

Phase 18 변경사항:
  - 개별 도구(allowed_tools) 배분 → IBL 노드(allowed_nodes) 배분
  - 패키지→도구 확장 제거, 노드 이름 그대로 저장
  - AI에게 ibl_nodes.yaml 노드 목록을 보여주고 배분
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
IBL_NODES_PATH = DATA_PATH / "ibl_nodes.yaml"

# 캐시 설정
_tools_cache: List[Dict[str, Any]] = []
_tools_cache_time: float = 0
_packages_cache: List[Dict[str, Any]] = []
_packages_cache_time: float = 0
_nodes_cache: List[Dict[str, Any]] = []
_nodes_cache_time: float = 0
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


def get_ibl_nodes(use_cache: bool = True) -> List[Dict[str, Any]]:
    """IBL 노드 목록 반환 (ibl_nodes.yaml에서 로드, 캐싱 지원)

    Phase 18→19: 감독관이 노드 배분 시 사용하는 노드 정보.
    인프라 노드(system)는 제외.
    """
    global _nodes_cache, _nodes_cache_time

    if use_cache and _nodes_cache and time.time() - _nodes_cache_time < _CACHE_TTL:
        return _nodes_cache

    # 인프라 노드 (항상 허용, 배분 불필요)
    # Phase 19: 6개 노드 → orchestrator로 통합
    # Phase 22: orchestrator → system으로 리네임
    # runtime 노드 제거 - Python/Node.js/Shell은 에이전트 기본 도구로 직접 제공
    INFRA_NODES = {"system"}

    nodes = []
    if not IBL_NODES_PATH.exists():
        return nodes

    try:
        with open(IBL_NODES_PATH, 'r', encoding='utf-8') as f:
            data = yaml.safe_load(f) or {}

        for node_name, node_config in data.get("nodes", {}).items():
            if node_name in INFRA_NODES:
                continue

            actions = node_config.get("actions", {})
            action_names = list(actions.keys())
            desc = node_config.get("description", "")

            nodes.append({
                "id": node_name,
                "description": desc,
                "actions": action_names,
                "action_count": len(action_names)
            })
    except Exception as e:
        print(f"[tool_selector] Failed to load ibl_nodes.yaml: {e}")

    _nodes_cache = nodes
    _nodes_cache_time = time.time()
    return nodes


def get_base_tools() -> List[str]:
    """기초 도구 이름 목록 반환 (시스템 기본 도구) - 레거시 호환"""
    return ["call_agent", "list_agents", "send_notification", "get_project_info"]


class SystemDirector:
    """
    프로젝트의 IBL 노드 배분과 에이전트 조율을 담당하는 시스템 AI

    Phase 18: 개별 도구(allowed_tools) 대신 IBL 노드(allowed_nodes) 단위로 배분.
    AI가 ibl_nodes.yaml의 노드 목록을 보고 에이전트 역할에 맞는 노드를 선택합니다.
    """
    def __init__(self, project_path: Path):
        self.project_path = project_path
        self.config = self._load_system_ai_config()
        self.assignment_map = {}  # agent_name -> [node_names]

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

    # Phase 18: IBL 노드 배분용 시스템 프롬프트
    NODE_DISTRIBUTOR_PROMPT = """You are an IBL node distributor for IndieBiz OS.

Your task: Assign IBL nodes to AI agents based on role relevance.

IBL nodes are functional areas (like "source", "engines", "stream", "interface").
Each node contains actions that agents can execute.
The "system" node is auto-granted to all agents (it includes workflow, automation, output, user, and filesystem capabilities).

Rules:
- Assign node IDs only (NOT individual tool/action names)
- Match node purpose to agent's role description
- Multiple agents can share the same node
- Only assign nodes clearly relevant to the role
- Keep assignments focused: 3-10 nodes per agent is typical

Output: Return only valid JSON in the specified format."""

    def _call_ai(self, prompt: str, system_role: str = None) -> str:
        """시스템 AI 설정을 사용하여 AI 호출"""
        provider = self.config.get('provider', 'google')
        api_key = self.config.get('apiKey') or self.config.get('api_key')
        model = self.config.get('model', 'gemini-2.0-flash')
        role = system_role or self.NODE_DISTRIBUTOR_PROMPT

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

    def _build_node_assignment_prompt(self, agents_info: List[Dict[str, str]]) -> str:
        """Phase 18: IBL 노드 단위 배분을 위한 프롬프트 생성"""
        nodes = get_ibl_nodes()

        # 노드 정보 구성 (설명 + 액션 목록)
        nodes_list = []
        for d in nodes:
            actions_str = ", ".join(d["actions"])
            desc = d['description'] if d['description'] else 'No description'
            nodes_list.append(f"- {d['id']}: {desc}\n  actions: [{actions_str}]")
        nodes_text = "\n".join(nodes_list)

        # 에이전트 정보
        agents_list = [f"- {a['name']}: {a['role']}" for a in agents_info]
        agents_text = "\n".join(agents_list)

        # 유효한 노드 ID 목록
        valid_node_ids = [d['id'] for d in nodes]

        prompt = f"""AVAILABLE NODES:
{nodes_text}

NOTE: The "system" node is auto-granted to all agents.
Do NOT include "system" in your assignments.

AGENTS:
{agents_text}

VALID NODE IDs: {valid_node_ids}

Return JSON:
{{"배분표": {{"agent_name": ["node_id", ...]}}}}"""
        return prompt

    def _extract_json(self, response: str) -> dict:
        """AI 응답에서 JSON을 안전하게 추출"""
        # 1차: 전체 응답을 바로 파싱 시도
        try:
            return json.loads(response.strip())
        except (json.JSONDecodeError, ValueError):
            pass

        # 2차: ```json ... ``` 코드 블록에서 추출
        code_block = re.search(r'```(?:json)?\s*\n?(.*?)\n?```', response, re.DOTALL)
        if code_block:
            try:
                return json.loads(code_block.group(1).strip())
            except (json.JSONDecodeError, ValueError):
                pass

        # 3차: 중괄호 매칭으로 JSON 추출
        start_idx = response.find('{')
        if start_idx == -1:
            raise ValueError("응답에서 JSON을 찾을 수 없습니다")

        depth = 0
        for i in range(start_idx, len(response)):
            if response[i] == '{':
                depth += 1
            elif response[i] == '}':
                depth -= 1
                if depth == 0:
                    json_str = response[start_idx:i + 1]
                    return json.loads(json_str)

        raise ValueError("응답에서 완전한 JSON을 찾을 수 없습니다")

    def _validate_nodes(self, node_assignments: Dict[str, List[str]]) -> Dict[str, List[str]]:
        """AI가 반환한 노드 목록에서 유효하지 않은 노드 제거"""
        valid_ids = {d['id'] for d in get_ibl_nodes()}
        validated = {}
        for agent_name, nodes in node_assignments.items():
            valid = [n for n in nodes if n in valid_ids]
            if valid:
                validated[agent_name] = valid
            if len(valid) != len(nodes):
                removed = set(nodes) - set(valid)
                print(f"   ⚠️ {agent_name}: 유효하지 않은 노드 제거: {removed}")
        return validated

    # ====== Phase 18: IBL 노드 배분 메서드 ======

    def reallocate_nodes(self, agents_info: List[Dict[str, str]]) -> bool:
        """
        allowed_nodes가 None인 에이전트에게만 IBL 노드를 배분합니다.
        """
        prompt = self._build_node_assignment_prompt(agents_info)
        response = self._call_ai(prompt)
        if not response:
            return False

        try:
            data = self._extract_json(response)
            raw_assignments = data.get("배분표", {})

            # 유효성 검사
            self.assignment_map = self._validate_nodes(raw_assignments)
            print(f"✅ [감독관] 노드 배분 완료: {list(self.assignment_map.keys())}")
            for agent, nodes in self.assignment_map.items():
                print(f"   📦 {agent}: {nodes}")

            # agents.yaml에 allowed_nodes 저장 (force=False)
            self._save_allowed_nodes_to_agents_yaml(force=False)
            return True
        except Exception as e:
            print(f"⚠️ [감독관] 배분표 파싱 실패: {e}")
            return False

    def force_reallocate_nodes(self, agents_info: List[Dict[str, str]]) -> bool:
        """
        모든 에이전트의 노드를 강제로 재배분합니다. (기존 설정 덮어쓰기)
        설정 화면의 '자동 배분' 버튼용
        """
        prompt = self._build_node_assignment_prompt(agents_info)
        response = self._call_ai(prompt)
        if not response:
            return False

        try:
            data = self._extract_json(response)
            raw_assignments = data.get("배분표", {})

            # 유효성 검사
            self.assignment_map = self._validate_nodes(raw_assignments)
            print(f"✅ [감독관] 노드 재배분 완료: {list(self.assignment_map.keys())}")
            for agent, nodes in self.assignment_map.items():
                print(f"   📦 {agent}: {nodes}")

            # 강제로 agents.yaml에 저장
            self._save_allowed_nodes_to_agents_yaml(force=True)
            return True
        except Exception as e:
            print(f"⚠️ [감독관] 배분표 파싱 실패: {e}")
            return False

    def _save_allowed_nodes_to_agents_yaml(self, force: bool = False):
        """
        Phase 18: 배분 결과를 agents.yaml의 각 에이전트 allowed_nodes에 저장.
        기존 allowed_tools 필드가 있으면 제거합니다.

        Args:
            force: True면 기존 allowed_nodes도 덮어씀 (자동 배분 버튼용)
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
                    if force or agent.get('allowed_nodes') is None:
                        agent['allowed_nodes'] = self.assignment_map[agent_name]
                        updated = True
                        print(f"   📦 {agent_name}: {self.assignment_map[agent_name]} 노드 배분")

                    # Phase 18: 레거시 allowed_tools 제거
                    if 'allowed_tools' in agent:
                        del agent['allowed_tools']
                        print(f"   🧹 {agent_name}: 레거시 allowed_tools 제거")

            if updated:
                with open(agents_yaml_path, 'w', encoding='utf-8') as f:
                    yaml.dump(data, f, allow_unicode=True, default_flow_style=False)
                print("✅ [감독관] agents.yaml에 노드 배분 저장 완료")
        except Exception as e:
            print(f"⚠️ [감독관] agents.yaml 저장 실패: {e}")

    def get_nodes_for_agent(self, agent_name: str) -> List[str]:
        """에이전트에게 배분된 노드 목록 반환"""
        return self.assignment_map.get(agent_name, [])

    # ====== 레거시 호환 (Phase 18 전환기) ======

    def reallocate_tools(self, agents_info: List[Dict[str, str]],
                         default_tools: List[str] = None) -> bool:
        """레거시 호환: reallocate_nodes()로 위임"""
        print("⚠️ [감독관] reallocate_tools() 호출 → reallocate_nodes()로 전환")
        return self.reallocate_nodes(agents_info)

    def force_reallocate_tools(self, agents_info: List[Dict[str, str]],
                               default_tools: List[str] = None) -> bool:
        """레거시 호환: force_reallocate_nodes()로 위임"""
        print("⚠️ [감독관] force_reallocate_tools() 호출 → force_reallocate_nodes()로 전환")
        return self.force_reallocate_nodes(agents_info)

    def get_tools_for_agent(self, agent_name: str) -> List[str]:
        """레거시 호환: get_nodes_for_agent()로 위임"""
        return self.get_nodes_for_agent(agent_name)


# 전역 감독관 인스턴스
director_instance = None
