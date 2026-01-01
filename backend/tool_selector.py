"""
tool_selector.py - 지능형 도구 선택 및 관리 시스템
IndieBiz OS Core

AI 감독관(Director)을 통해 에이전트의 역할에 맞는 도구를 배분합니다.
설치된 도구 패키지에서 도구 목록을 가져옵니다.
"""

import re
import yaml
import json
from pathlib import Path
from typing import List, Dict, Any

# 경로 설정
BACKEND_PATH = Path(__file__).parent
DATA_PATH = BACKEND_PATH.parent / "data"
INSTALLED_TOOLS_PATH = DATA_PATH / "packages" / "installed" / "tools"


def get_installed_tools() -> List[Dict[str, Any]]:
    """설치된 도구 목록 반환 (tool.json에서 로드)"""
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

    return tools


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

    def _call_ai(self, prompt: str) -> str:
        """시스템 AI 설정을 사용하여 AI 호출"""
        provider = self.config.get('provider', 'google')
        api_key = self.config.get('apiKey') or self.config.get('api_key')
        model = self.config.get('model', 'gemini-2.0-flash')
        role = self.config.get('role') or '너는 IndieBiz 시스템 AI야. 에이전트들의 역할과 도구 설명을 분석해서 최적의 배분표를 작성해야 해.'

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

    def reallocate_tools(self, agents_info: List[Dict[str, str]]):
        """
        allowed_tools가 None인 에이전트에게만 도구를 배분합니다.
        """
        installed_tools = get_installed_tools()
        tools_desc = "\n".join([f"- {t.get('name')}: {t.get('description', '')}" for t in installed_tools])

        agents_desc = "\n".join([f"[{a['name']}]\n역할: {a['role']}" for a in agents_info])

        prompt = f'''
다음은 우리 시스템의 '설치된 도구'와 '에이전트' 목록이야. 전문성을 고려해서 도구를 배분해줘.

[규칙]
1. 각 에이전트의 '역할'에 꼭 필요한 도구만 할당해.
2. 실행 도구(제작, 검색 등)는 전문가 에이전트에게 몰아주고, 집사(관리자)는 조율 도구(이메일, 메시지 등) 위주로 배분해.
3. 결과는 반드시 배분표 JSON만 반환해.

[설치된 도구 목록]
{tools_desc}

[에이전트 목록]
{agents_desc}

[반환 형식]
{{
  "배분표": {{
    "에이전트이름": ["도구이름1", "도구이름2"],
    ...
  }}
}}
'''
        response = self._call_ai(prompt)
        if not response:
            return False

        try:
            json_str = re.search(r'\{.*\}', response, re.DOTALL).group()
            data = json.loads(json_str)
            self.assignment_map = data.get("배분표", {})
            print(f"✅ [감독관] 도구 배분 완료: {list(self.assignment_map.keys())}")

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
        installed_tools = get_installed_tools()
        tools_desc = "\n".join([f"- {t.get('name')}: {t.get('description', '')}" for t in installed_tools])

        agents_desc = "\n".join([f"[{a['name']}]\n역할: {a['role']}" for a in agents_info])

        prompt = f'''
다음은 우리 시스템의 '설치된 도구'와 '에이전트' 목록이야. 전문성을 고려해서 도구를 배분해줘.

[규칙]
1. 각 에이전트의 '역할'에 꼭 필요한 도구만 할당해.
2. 실행 도구(제작, 검색 등)는 전문가 에이전트에게 몰아주고, 집사(관리자)는 조율 도구(이메일, 메시지 등) 위주로 배분해.
3. 결과는 반드시 배분표 JSON만 반환해.

[설치된 도구 목록]
{tools_desc}

[에이전트 목록]
{agents_desc}

[반환 형식]
{{
  "배분표": {{
    "에이전트이름": ["도구이름1", "도구이름2"],
    ...
  }}
}}
'''
        response = self._call_ai(prompt)
        if not response:
            return False

        try:
            json_str = re.search(r'\{.*\}', response, re.DOTALL).group()
            data = json.loads(json_str)
            self.assignment_map = data.get("배분표", {})
            print(f"✅ [감독관] 도구 재배분 완료: {list(self.assignment_map.keys())}")

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
