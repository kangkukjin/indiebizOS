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


def get_installed_packages() -> List[Dict[str, Any]]:
    """설치된 패키지 목록 반환 (패키지 단위 정보 포함)"""
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

    def _build_package_assignment_prompt(self, agents_info: List[Dict[str, str]]) -> str:
        """패키지 단위 배분을 위한 프롬프트 생성 (Chain-of-Thought 적용)"""
        packages = get_installed_packages()

        # 패키지 설명 구성
        packages_desc = []
        for pkg in packages:
            tools_list = ", ".join(pkg["tools"][:5])
            if len(pkg["tools"]) > 5:
                tools_list += f" 외 {len(pkg['tools']) - 5}개"
            packages_desc.append(
                f"📦 {pkg['id']} ({pkg['tool_count']}개 도구)\n"
                f"   설명: {pkg['description'] or '(설명 없음)'}\n"
                f"   도구: {tools_list}"
            )
        packages_text = "\n\n".join(packages_desc)

        # 에이전트 설명 구성
        agents_desc = "\n".join([
            f"👤 {a['name']}\n   역할: {a['role']}"
            for a in agents_info
        ])

        prompt = f'''도구 패키지를 에이전트에게 배분해야 합니다.

## 설치된 도구 패키지
{packages_text}

## 에이전트 목록
{agents_desc}

## 배분 규칙
1. **패키지 단위로 배분**: 패키지 안의 도구들은 함께 움직입니다. 개별 도구가 아닌 패키지 ID를 배분하세요.
2. **역할 매칭**: 에이전트의 역할과 패키지의 목적이 일치해야 합니다.
3. **중복 허용**: 여러 에이전트가 같은 패키지를 가질 수 있습니다.
4. **최소 배분**: 역할에 필요 없는 패키지는 배분하지 마세요.

## 단계별로 생각하세요
1단계: 각 에이전트의 핵심 업무가 무엇인지 파악하세요.
2단계: 각 패키지가 어떤 종류의 작업에 필요한지 분류하세요.
3단계: 에이전트별로 필요한 패키지를 매칭하세요.
4단계: 매칭 결과를 검증하세요 - 이 도구들로 에이전트가 역할을 수행할 수 있나요?

## 예시
에이전트 "유튜버"의 역할이 "유튜브 콘텐츠 제작 및 관리"라면:
→ youtube 패키지 (영상 다운로드, 자막 추출)
→ web-search 패키지 (트렌드 조사)

## 반환 형식 (JSON만 반환)
{{
  "배분표": {{
    "에이전트이름": ["패키지id1", "패키지id2"],
    ...
  }}
}}
'''
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
