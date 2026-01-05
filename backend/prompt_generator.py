"""
PromptGenerator - 자동 프롬프트 생성 모듈
IndieBiz OS Core

단계별 코드 강제 방식:
1. 초안 생성 (Draft) - AI로 프롬프트 초안 생성
2. 규격 검증 (Validate) - 필수 규격 검증
"""

import json
import re
from pathlib import Path
from typing import Dict, List, Tuple, Any
from dataclasses import dataclass


@dataclass
class GeneratedPrompts:
    """생성된 프롬프트 결과"""
    common_settings: str
    agent_roles: Dict[str, str]


class PromptGenerator:
    """자동 프롬프트 생성기 - 단계별 코드 강제"""

    # 작업 수행 절차 (모든 에이전트 공통)
    WORK_PROCEDURE = """## 작업 수행 절차 (필수)

### 1. 계획 단계
복잡한 작업을 받으면 바로 실행하지 말고 먼저 계획을 세우세요:
- 이 작업을 완료하려면 어떤 단계가 필요한가?
- 각 단계에서 어떤 도구를 사용할 것인가?
- 실패할 수 있는 지점은 어디인가?

### 2. 실행 단계
한 번에 하나씩 실행하고 결과를 확인하세요:
- 도구 호출 전: 입력값이 올바른지 검토
- 도구 호출 후: 결과가 예상대로인지 확인
- 파일 생성 후: 실제 생성되었는지 확인

### 3. 검증 단계
작업이 끝나면 결과를 검증하세요:
- 생성한 파일이 존재하는가?
- 코드가 문법 오류 없이 작성되었는가?
- 요청한 기능이 모두 포함되었는가?

### 4. 에러 복구
실패하면 포기하지 말고:
- 에러 메시지를 읽고 원인 파악
- 다른 방법으로 재시도 (최대 2회)
- 그래도 실패하면 사용자에게 상황과 대안 설명"""

    # Few-shot 예시: 멀티 에이전트용 공통 설정
    EXAMPLE_COMMON_SETTINGS_MULTI = """## 위임 체인 시스템 (핵심)

이 시스템은 **자동 보고 체인**을 사용합니다:
- 작업을 위임하면 시스템이 자동으로 위임 관계를 추적합니다
- 작업이 완료되면 시스템이 자동으로 결과를 위임 체인을 따라 보고합니다
- **에이전트는 자기 일만 하면 됩니다. 보고는 시스템이 자동 처리합니다.**

## 에이전트 간 통신 (call_agent)
- call_agent는 **비동기**입니다. 호출 후 응답을 기다리지 않습니다.
- 다른 에이전트 도움이 필요하면 call_agent를 호출하세요.
- 결과 보고를 직접 할 필요 없습니다 (시스템 자동 처리).

## 위임 원칙 (중요)
**자신이 가진 도구로 처리 가능한 작업은 직접 수행하세요.**
1. 작업 요청을 받으면 먼저 자신의 도구 목록 확인
2. 해당 도구가 있으면 → 직접 처리
3. 해당 도구가 없으면 → `call_agent`로 위임

{work_procedure}

## 파일 경로 규칙
파일 생성/전달 시 **반드시 전체 경로** 포함:
- 예: `파일: /outputs/report.html`

## 응답 형식
[작업 완료]
- 수행 내용: (구체적인 작업)
- 결과: (결과물 또는 상태)
- 파일 경로: (생성된 파일이 있는 경우)

[오류 발생]
- 문제: (무엇이 잘못되었는지)
- 원인: (추정 원인)
- 제안: (다음 단계)

## 도구 사용 원칙
- 도구는 작업에 필요할 때만 호출
- 단순 질문에는 도구 없이 직접 응답"""

    # Few-shot 예시: 싱글 에이전트용 공통 설정 (위임 관련 내용 제외)
    EXAMPLE_COMMON_SETTINGS_SINGLE = """## 작업 원칙

**자신이 가진 도구로 작업을 수행하세요.**
1. 작업 요청을 받으면 먼저 자신의 도구 목록 확인
2. 적절한 도구를 선택하여 작업 수행
3. 작업에만 집중하세요. 보고는 시스템이 자동 처리합니다.

{work_procedure}

## 파일 경로 규칙
파일 생성/전달 시 **반드시 전체 경로** 포함:
- 예: `파일: /outputs/report.html`

## 응답 형식
[작업 완료]
- 수행 내용: (구체적인 작업)
- 결과: (결과물 또는 상태)
- 파일 경로: (생성된 파일이 있는 경우)

[오류 발생]
- 문제: (무엇이 잘못되었는지)
- 원인: (추정 원인)
- 제안: (다음 단계)

## 도구 사용 원칙
- 도구는 작업에 필요할 때만 호출
- 단순 질문에는 도구 없이 직접 응답"""

    EXAMPLE_ORCHESTRATOR_ROLE = """# 집사 - 총괄 지휘자

## 역할
사용자의 요청을 분석하고, 적절한 에이전트에게 작업을 배분합니다.

## 위임 원칙 (중요)

**자신이 가진 도구로 처리 가능한 작업은 직접 수행하세요.**
1. 작업 요청을 받으면 먼저 자신의 도구 목록 확인
2. 해당 도구가 있으면 → 직접 처리
3. 해당 도구가 없으면 → `call_agent`로 위임

## 위임 방법

자신에게 없는 도구가 필요할 때만 `call_agent`를 사용하세요:
```
call_agent("에이전트이름", "작업 내용")
```

**시스템 자동화**:
- 위임하면 시스템이 자동으로 관계를 추적합니다
- 작업 완료 시 시스템이 자동으로 결과를 전달합니다
- 보고를 요청하거나 기다릴 필요 없습니다

## 파일 경로 규칙
파일 전달 시 **반드시 전체 경로** 포함:
예: "파일: /outputs/newsletter.html" """

    EXAMPLE_WORKER_ROLE = """# 대장장이 - 개발 전문가

## 역할
코드 작성, 스크립트 실행, 기술적 문제 해결을 담당합니다.

## 작업 방식

**시스템 자동화**:
- 작업 완료 시 시스템이 자동으로 요청자에게 결과를 전달합니다
- 보고를 직접 할 필요 없습니다 (시스템 자동 처리)
- 작업에만 집중하세요

**파일 경로 규칙**:
결과물이 파일인 경우, 응답에 전체 경로를 포함하세요:
```
작업 완료. 파일: /outputs/result.html
```

## 주의사항
- 실행 전 코드 검토 (무한루프 방지)
- 에러 발생 시 원인과 해결 방안 함께 보고"""

    # 싱글 에이전트용 역할 예시
    EXAMPLE_SINGLE_AGENT_ROLE = """# {agent_name}

## 역할
{role_description}

## 작업 방식

**시스템 자동화**:
- 작업 완료 시 시스템이 자동으로 사용자에게 결과를 전달합니다
- 보고를 직접 할 필요 없습니다 (시스템 자동 처리)
- 작업에만 집중하세요

**파일 경로 규칙**:
결과물이 파일인 경우, 응답에 전체 경로를 포함하세요:
```
작업 완료. 파일: /outputs/result.html
```

## 주의사항
- 도구를 사용하기 전에 적절한 도구인지 확인
- 에러 발생 시 원인과 해결 방안 함께 보고"""

    # 코딩 전문 에이전트 감지용 키워드
    CODING_AGENT_KEYWORDS = ["코딩", "개발", "프로그램", "대장장이"]

    # 코딩 전문 에이전트에게 필수로 주입할 추가 규칙
    CODING_AGENT_RULES = """
## 코드 실행 안전 규칙 (필수)

### 금지 명령어
다음 명령어는 절대 실행하지 마세요:
- `rm -rf`, `rmdir /s` - 재귀 삭제
- `format`, `mkfs` - 디스크 포맷
- `dd if=` - 디스크 직접 쓰기
- `chmod 777`, `chmod -R 777` - 위험한 권한 변경

### 코드 실행 전 체크리스트
1. **무한루프 방지**: 모든 루프에 종료 조건 또는 최대 반복 횟수 설정
2. **리소스 제한**: 대용량 파일/데이터 처리 시 청크 단위로 처리
3. **타임아웃 설정**: 외부 API 호출, 네트워크 요청에 타임아웃 필수
4. **예외 처리**: try-except로 에러 핸들링

### 파일 작업 규칙
- **백업 우선**: 기존 파일 수정 전 `.bak` 백업 생성
- **경로 검증**: 상대 경로 사용, 프로젝트 디렉토리 외부 접근 금지
- **인코딩 명시**: 파일 읽기/쓰기 시 `encoding='utf-8'` 명시
"""

    def __init__(self, backend_path: str = None):
        if backend_path is None:
            backend_path = Path(__file__).parent
        self.backend_path = Path(backend_path)
        self.data_path = self.backend_path.parent / "data"

    def _get_common_settings_example(self, agent_count: int) -> str:
        """에이전트 수에 따라 적절한 공통 설정 예시 반환"""
        if agent_count > 1:
            return self.EXAMPLE_COMMON_SETTINGS_MULTI.format(work_procedure=self.WORK_PROCEDURE)
        else:
            return self.EXAMPLE_COMMON_SETTINGS_SINGLE.format(work_procedure=self.WORK_PROCEDURE)

    def _load_system_ai_config(self) -> dict:
        """전역 시스템 AI 설정 로드"""
        config_path = self.data_path / "system_ai_config.json"
        if config_path.exists():
            try:
                with open(config_path, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except:
                pass
        return {}

    def _call_ai(self, prompt: str, system_prompt: str = "프롬프트 전문가입니다. JSON으로 응답하세요.") -> str:
        """시스템 AI 호출"""
        config = self._load_system_ai_config()
        provider = config.get('provider', 'google')
        api_key = config.get('apiKey') or config.get('api_key')
        model = config.get('model', 'gemini-2.0-flash')

        if not api_key:
            raise ValueError("시스템 AI API 키가 설정되지 않았습니다.")

        try:
            if provider in ['google', 'gemini']:
                from google import genai
                from google.genai import types
                client = genai.Client(api_key=api_key)
                response = client.models.generate_content(
                    model=model,
                    contents=prompt,
                    config=types.GenerateContentConfig(
                        system_instruction=system_prompt
                    )
                )
                return response.text

            elif provider == 'anthropic':
                import anthropic
                client = anthropic.Anthropic(api_key=api_key)
                resp = client.messages.create(
                    model=model,
                    max_tokens=4096,
                    system=system_prompt,
                    messages=[{"role": "user", "content": prompt}]
                )
                return resp.content[0].text

            elif provider in ['openai', 'gpt']:
                import openai
                client = openai.OpenAI(api_key=api_key)
                resp = client.chat.completions.create(
                    model=model,
                    messages=[
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": prompt}
                    ]
                )
                return resp.choices[0].message.content

        except Exception as e:
            raise ValueError(f"AI 호출 실패: {e}")

        return ""

    def _is_coding_agent(self, agent: Dict[str, str]) -> bool:
        """에이전트가 코딩 전문가인지 판별"""
        role_text = (
            agent.get('role_description', '') + ' ' +
            agent.get('role', '') + ' ' +
            agent.get('name', '')
        ).lower()

        for keyword in self.CODING_AGENT_KEYWORDS:
            if keyword in role_text:
                return True
        return False

    def _get_coding_agents(self, agents: List[Dict[str, str]]) -> List[str]:
        """코딩 전문 에이전트 이름 목록 반환"""
        return [a.get('name', '') for a in agents if self._is_coding_agent(a)]

    def _fix_json_string(self, json_str: str) -> str:
        """JSON 문자열 내부의 줄바꿈을 이스케이프"""
        result = []
        in_string = False
        escape_next = False

        for char in json_str:
            if escape_next:
                result.append(char)
                escape_next = False
                continue

            if char == '\\':
                result.append(char)
                escape_next = True
                continue

            if char == '"':
                in_string = not in_string
                result.append(char)
                continue

            if in_string and char == '\n':
                result.append('\\n')
            elif in_string and char == '\r':
                result.append('\\r')
            elif in_string and char == '\t':
                result.append('\\t')
            else:
                result.append(char)

        return ''.join(result)

    def _parse_json_response(self, response: str) -> Dict:
        """AI 응답에서 JSON 추출"""
        # 방법 1: ```json 블록 추출
        json_match = re.search(r'```json\s*(.*?)\s*```', response, re.DOTALL)
        if json_match:
            json_str = json_match.group(1)
            try:
                return json.loads(json_str)
            except json.JSONDecodeError:
                try:
                    fixed = self._fix_json_string(json_str)
                    return json.loads(fixed)
                except:
                    pass

        # 방법 2: ``` 블록 추출
        code_match = re.search(r'```\s*(.*?)\s*```', response, re.DOTALL)
        if code_match:
            json_str = code_match.group(1)
            try:
                return json.loads(json_str)
            except:
                try:
                    fixed = self._fix_json_string(json_str)
                    return json.loads(fixed)
                except:
                    pass

        # 방법 3: { } 블록 직접 추출
        brace_match = re.search(r'\{[\s\S]*\}', response)
        if brace_match:
            json_str = brace_match.group(0)
            try:
                return json.loads(json_str)
            except:
                try:
                    fixed = self._fix_json_string(json_str)
                    return json.loads(fixed)
                except:
                    pass

        raise ValueError(f"JSON 파싱 실패. 응답 형식이 올바르지 않습니다.")

    def _build_agents_info(self, agents: List[Dict[str, str]]) -> str:
        """에이전트 목록을 상세하게 포맷팅"""
        lines = []
        for a in agents:
            name = a.get('name', '?')
            agent_type = a.get('type', 'internal')
            role_desc = a.get('role_description') or a.get('role', '')
            line = f"- **{name}** ({agent_type}): {role_desc}"
            lines.append(line)
        return "\n".join(lines)

    def _build_agent_list_for_prompt(self, agents: List[Dict[str, str]]) -> str:
        """프롬프트에 포함할 에이전트 목록 문자열 생성"""
        lines = []
        for a in agents:
            name = a.get('name', '?')
            agent_type = a.get('type', 'internal')
            role_desc = a.get('role_description') or a.get('role', '')
            lines.append(f"  - {name} ({agent_type}): {role_desc}")
        return "\n".join(lines)

    def _step1_generate_draft(
        self,
        project_purpose: str,
        agents: List[Dict[str, str]]
    ) -> GeneratedPrompts:
        """Step 1: AI로 프롬프트 초안 생성"""
        agents_info = self._build_agents_info(agents)
        agent_count = len(agents)
        is_multi_agent = agent_count > 1

        # 에이전트 수에 따라 다른 예시 사용
        common_settings_example = self._get_common_settings_example(agent_count)

        if is_multi_agent:
            # 멀티 에이전트: 위임 관련 내용 포함
            agent_list_text = self._build_agent_list_for_prompt(agents)
            delegation_rules = """
### 핵심 메시지 (반드시 포함)
프롬프트에 다음 내용을 **반드시 포함**하세요:
- "보고는 시스템이 자동 처리합니다" (자동 보고 체인)
- "작업에만 집중하세요"
- "파일 생성 시 전체 경로 명시"

### 절대 금지
다음 내용은 프롬프트에 **절대로 포함하지 마세요**:
- "완료되면 알려주세요", "보고해주세요" 등 수동 보고 요청
- 복잡한 보고 절차 지시

1. **에이전트 목록을 그대로 포함**:
```
## 협업 에이전트
{agent_list}
```

2. **파일 경로 규칙 (운반책 원칙)**:
   - 파일 생성/전달 시 반드시 전체 경로 포함
   - 예: "파일: /outputs/report.html"
""".format(agent_list=agent_list_text)

            role_examples = f"""
### 오케스트레이터(집사) 역할 예시:
```
{self.EXAMPLE_ORCHESTRATOR_ROLE}
```

### 워커(대장장이) 역할 예시:
```
{self.EXAMPLE_WORKER_ROLE}
```
"""
        else:
            # 싱글 에이전트: 위임 관련 내용 제외
            agent = agents[0] if agents else {}
            agent_name = agent.get('name', '에이전트')
            role_desc = agent.get('role_description') or agent.get('role', '사용자 요청 처리')

            delegation_rules = """
### 핵심 메시지 (반드시 포함)
프롬프트에 다음 내용을 **반드시 포함**하세요:
- "보고는 시스템이 자동 처리합니다"
- "작업에만 집중하세요"
- "파일 생성 시 전체 경로 명시"

### 절대 금지
다음 내용은 프롬프트에 **절대로 포함하지 마세요**:
- "완료되면 알려주세요", "보고해주세요" 등 수동 보고 요청
- 복잡한 보고 절차 지시

### 파일 경로 규칙:
- 파일 생성/전달 시 반드시 전체 경로 포함
- 예: "파일: /outputs/report.html"
"""

            single_role_example = self.EXAMPLE_SINGLE_AGENT_ROLE.format(
                agent_name=agent_name,
                role_description=role_desc
            )
            role_examples = f"""
### 에이전트 역할 예시:
```
{single_role_example}
```
"""

        prompt = f"""다음 정보를 기반으로 에이전트의 **실제로 작동하는** 상세한 프롬프트를 생성하세요.

## 프로젝트 목적
{project_purpose}

## 에이전트 목록 ({agent_count}명)
{agents_info}

---

## 좋은 프롬프트 예시 (Few-shot)

아래는 잘 작성된 프롬프트의 예시입니다. **이 형식과 상세함을 따라하세요.**

### 공통 설정 예시:
```
{common_settings_example}
```
{role_examples}
---

## 생성 규칙
{delegation_rules}
---

## 출력 형식 (JSON)
```json
{{
  "common_settings": "공통 설정 (위 예시처럼 상세하게, 500자 이상)",
  "agent_roles": {{
    "에이전트이름": "역할 프롬프트 (위 예시처럼 상세하게, 각 에이전트 500자 이상)"
  }}
}}
```

**중요**: 예시보다 짧거나 모호하면 안 됩니다. 예시 수준의 상세함을 유지하세요.
"""

        response = self._call_ai(prompt)
        data = self._parse_json_response(response)

        # 코딩 에이전트에 규칙이 누락된 경우 강제 주입
        agent_roles = data.get("agent_roles", {})
        coding_agents = self._get_coding_agents(agents)

        for agent_name in coding_agents:
            if agent_name in agent_roles:
                role = agent_roles[agent_name]
                if "코드 실행 안전 규칙" not in role:
                    agent_roles[agent_name] = role + "\n\n" + self.CODING_AGENT_RULES

        return GeneratedPrompts(
            common_settings=data.get("common_settings", ""),
            agent_roles=agent_roles
        )

    def _step2_validate(self, prompts: GeneratedPrompts, agent_count: int = 1) -> Tuple[bool, List[str]]:
        """Step 2: 필수 규격 검증"""
        errors = []

        # 공통 설정 검증
        if not prompts.common_settings:
            errors.append("공통 설정이 비어있습니다")
        else:
            # 멀티 에이전트일 때만 call_agent 키워드 검증
            if agent_count > 1:
                if "call_agent" not in prompts.common_settings:
                    errors.append("공통 설정에 'call_agent' 규칙이 없습니다")

            # 작업 수행 절차 관련 키워드 검증
            if "계획" not in prompts.common_settings and "실행" not in prompts.common_settings:
                errors.append("공통 설정에 작업 수행 절차가 없습니다")

            if len(prompts.common_settings) < 300:
                errors.append(f"공통 설정이 너무 짧습니다 (현재 {len(prompts.common_settings)}자)")

        # 개별 역할 검증
        if not prompts.agent_roles:
            errors.append("에이전트 역할이 정의되지 않았습니다")
        else:
            for name, role in prompts.agent_roles.items():
                if not role:
                    errors.append(f"{name}의 역할이 비어있습니다")
                elif len(role) < 200:
                    errors.append(f"{name}의 역할 설명이 너무 짧습니다")

        return len(errors) == 0, errors

    def generate(
        self,
        project_purpose: str,
        agents: List[Dict[str, str]],
        ai_config: Dict = None,
        max_fix_attempts: int = 2
    ) -> GeneratedPrompts:
        """
        프롬프트 자동 생성

        Args:
            project_purpose: 프로젝트 목적
            agents: 에이전트 목록 [{"name": "이름", "role": "역할", "type": "external/internal"}]
            ai_config: AI 설정 (미사용, 시스템 AI 설정 사용)
            max_fix_attempts: 검증 실패 시 재시도 횟수
        """
        agent_count = len(agents)

        # Step 1: 초안 생성
        print(f"[Step 1] 초안 생성 중... (에이전트 {agent_count}명)")
        prompts = self._step1_generate_draft(project_purpose, agents)

        # Step 2: 규격 검증
        print("[Step 2] 규격 검증 중...")
        is_valid, errors = self._step2_validate(prompts, agent_count)
        if not is_valid:
            print(f"[Step 2] 검증 경고: {errors}")
            # 검증 실패해도 진행 (경고만)

        print("[완료] 프롬프트 생성 완료")
        return prompts

    def validate(self, prompts: GeneratedPrompts, agent_count: int = 1) -> List[str]:
        """외부용 검증 함수"""
        _, errors = self._step2_validate(prompts, agent_count)
        return errors

    def save_to_project(self, prompts: GeneratedPrompts, project_path: str) -> Dict[str, str]:
        """생성된 프롬프트를 프로젝트에 저장"""
        project_path = Path(project_path)
        saved_files = {}

        # common_settings.txt 저장
        common_path = project_path / "common_settings.txt"
        common_path.write_text(prompts.common_settings, encoding='utf-8')
        saved_files["common_settings"] = str(common_path)

        # 에이전트별 역할 저장
        for agent_name, role in prompts.agent_roles.items():
            role_path = project_path / f"agent_{agent_name}_role.txt"
            role_path.write_text(role, encoding='utf-8')
            saved_files[f"role_{agent_name}"] = str(role_path)

        return saved_files
