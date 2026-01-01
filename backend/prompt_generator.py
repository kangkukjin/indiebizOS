"""
prompt_generator.py - 프롬프트 자동 생성기
IndieBiz OS Core

에이전트 팀의 역할 프롬프트를 AI로 자동 생성합니다.
"""

from typing import Dict, List, Any
from pathlib import Path


class PromptGenerator:
    """프롬프트 생성기"""

    def __init__(self, ai_config: dict):
        """
        Args:
            ai_config: AI 설정 {"provider": "anthropic", "api_key": "...", "model": "..."}
        """
        self.ai_config = ai_config
        self._client = None
        self._init_client()

    def _init_client(self):
        """AI 클라이언트 초기화"""
        provider = self.ai_config.get("provider", "anthropic")
        api_key = self.ai_config.get("api_key", "")

        if not api_key:
            print("[PromptGenerator] API 키 없음")
            return

        try:
            if provider == "anthropic":
                import anthropic
                self._client = anthropic.Anthropic(api_key=api_key)
            elif provider == "openai":
                import openai
                self._client = openai.OpenAI(api_key=api_key)
        except ImportError as e:
            print(f"[PromptGenerator] 라이브러리 없음: {e}")

    def generate_prompts(
        self,
        project_purpose: str,
        agents: List[Dict[str, str]]
    ) -> Dict[str, Any]:
        """
        프롬프트 생성

        Args:
            project_purpose: 프로젝트 목적 (예: "IT 뉴스레터 발행팀")
            agents: 에이전트 목록 [{"name": "집사", "type": "external", "description": "총괄 지휘자"}]

        Returns:
            {
                "common_settings": "공통 설정 텍스트",
                "agent_roles": {"집사": "역할 텍스트", ...}
            }
        """
        if not self._client:
            return {"error": "AI 클라이언트가 초기화되지 않았습니다."}

        # 에이전트 목록 정리
        agent_list = "\n".join([
            f"- {a['name']}: {a.get('description', a.get('type', 'internal'))}"
            for a in agents
        ])

        prompt = f"""다음 프로젝트의 에이전트 팀을 위한 프롬프트를 생성해주세요.

## 프로젝트 목적
{project_purpose}

## 에이전트 구성
{agent_list}

## 요청사항

1. **공통 설정 (common_settings.txt)**
   - 모든 에이전트가 공유하는 규칙
   - call_agent(agent_name, message)로 다른 에이전트에게 작업 위임하는 방법
   - 파일 경로 규칙, 에러 처리 방법

2. **각 에이전트 역할**
   - 구체적인 역할과 책임
   - 어떤 상황에서 누구에게 위임해야 하는지
   - 사용해야 할 도구 (있다면)

응답 형식:
```common_settings
(공통 설정 내용)
```

```role:{{"에이전트이름"}}
(해당 에이전트의 역할)
```

각 에이전트마다 role 블록을 작성해주세요.
"""

        try:
            provider = self.ai_config.get("provider", "anthropic")
            model = self.ai_config.get("model", "claude-sonnet-4-20250514")

            if provider == "anthropic":
                response = self._client.messages.create(
                    model=model,
                    max_tokens=4096,
                    messages=[{"role": "user", "content": prompt}]
                )
                text = response.content[0].text
            elif provider == "openai":
                response = self._client.chat.completions.create(
                    model=model,
                    messages=[{"role": "user", "content": prompt}],
                    max_tokens=4096
                )
                text = response.choices[0].message.content
            else:
                return {"error": f"지원하지 않는 프로바이더: {provider}"}

            # 파싱
            return self._parse_response(text)

        except Exception as e:
            return {"error": f"생성 실패: {str(e)}"}

    def _parse_response(self, text: str) -> Dict[str, Any]:
        """응답 파싱"""
        result = {
            "common_settings": "",
            "agent_roles": {}
        }

        lines = text.split("\n")
        current_section = None
        current_agent = None
        buffer = []

        for line in lines:
            if line.strip().startswith("```common_settings"):
                current_section = "common"
                buffer = []
            elif line.strip().startswith("```role:"):
                # 이전 섹션 저장
                if current_section == "common":
                    result["common_settings"] = "\n".join(buffer).strip()
                elif current_section == "role" and current_agent:
                    result["agent_roles"][current_agent] = "\n".join(buffer).strip()

                # 새 에이전트
                current_section = "role"
                # role:집사 또는 role:{"집사"} 형식 지원
                agent_part = line.split("role:")[-1].strip().strip("`").strip("{").strip("}").strip('"').strip("'")
                current_agent = agent_part
                buffer = []
            elif line.strip() == "```":
                # 섹션 종료
                if current_section == "common":
                    result["common_settings"] = "\n".join(buffer).strip()
                elif current_section == "role" and current_agent:
                    result["agent_roles"][current_agent] = "\n".join(buffer).strip()
                current_section = None
                current_agent = None
            elif current_section:
                buffer.append(line)

        return result

    def save_to_project(self, project_path: str, prompts: Dict[str, Any]) -> bool:
        """
        생성된 프롬프트를 프로젝트에 저장

        Args:
            project_path: 프로젝트 폴더 경로
            prompts: generate_prompts의 결과
        """
        try:
            path = Path(project_path)

            # 공통 설정 저장
            common = prompts.get("common_settings", "")
            if common:
                (path / "common_settings.txt").write_text(common, encoding='utf-8')

            # 에이전트별 역할 저장
            for agent_name, role in prompts.get("agent_roles", {}).items():
                role_file = path / f"agent_{agent_name}_role.txt"
                role_file.write_text(role, encoding='utf-8')

            return True
        except Exception as e:
            print(f"[PromptGenerator] 저장 실패: {e}")
            return False
